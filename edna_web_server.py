#!/usr/bin/env python3
"""本地鱼类 eDNA 分析网站：上传文件、生成配置并启动工作流。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(os.environ.get("EDNA_APP_DIR", "/app" if Path("/app").exists() else ".")).resolve()
WORKSPACE = Path(os.environ.get("EDNA_WORKSPACE", "/workspace" if Path("/workspace").exists() else ".")).resolve()
UPLOAD_DIR = WORKSPACE / "uploads"
FASTQ_DIR = UPLOAD_DIR / "fastq"
REFERENCE_DIR = UPLOAD_DIR / "reference"
RESULTS_DIR = WORKSPACE / "results"
CONFIG_PATH = WORKSPACE / "config.yaml"
LOG_PATH = WORKSPACE / "web_workflow.log"
WORKFLOW_SCRIPT = APP_DIR / "edna_qiime2_blast_workflow.py"

state = {
    "running": False,
    "returncode": None,
    "started_at": None,
    "finished_at": None,
    "message": "尚未运行",
}
process_lock = threading.Lock()


def json_response(handler: SimpleHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def safe_name(filename: str) -> str:
    name = Path(filename or "uploaded_file").name
    return "".join(ch for ch in name if ch.isalnum() or ch in ".-_+") or "uploaded_file"


def parse_content_disposition(value: str) -> dict[str, str]:
    parts = [part.strip() for part in value.split(";")]
    parsed: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, raw = part.split("=", 1)
            parsed[key.strip().lower()] = raw.strip().strip('"')
    return parsed


def parse_multipart(headers, body: bytes) -> tuple[dict[str, str], dict[str, list[tuple[str, bytes]]]]:
    content_type = headers.get("Content-Type", "")
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("请求不是 multipart/form-data。")
    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    delimiter = ("--" + boundary).encode("utf-8")
    fields: dict[str, str] = {}
    files: dict[str, list[tuple[str, bytes]]] = {}
    for part in body.split(delimiter):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].rstrip(b"\r\n")
        header_blob, sep, content = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        part_headers = {}
        for line in header_blob.decode("utf-8", "replace").split("\r\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                part_headers[key.lower()] = value.strip()
        disposition = parse_content_disposition(part_headers.get("content-disposition", ""))
        name = disposition.get("name")
        if not name:
            continue
        filename = disposition.get("filename")
        if filename:
            files.setdefault(name, []).append((safe_name(filename), content))
        else:
            fields[name] = content.decode("utf-8", "replace").strip()
    return fields, files


def save_uploaded_file(item: tuple[str, bytes], target_dir: Path) -> Path:
    filename, content = item
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name(filename)
    target.write_bytes(content)
    return target


def write_config(fields: dict[str, str], metadata_path: Path, reference_path: Path) -> None:
    def field(name: str, default: str) -> str:
        value = fields.get(name, default)
        return str(value).strip() or default

    text = f"""project:
  name: {field('projectName', 'fish_edna_local')}
  output_dir: results
  threads: {field('threads', '4')}

input:
  fastq_dir: uploads/fastq
  metadata: {metadata_path.relative_to(WORKSPACE)}
  qiime_input_format: CasavaOneEightSingleLanePerSampleDirFmt

manifest:
  make_manifest: false

reference:
  fasta: {reference_path.relative_to(WORKSPACE)}
  blast_db_prefix: null
  db_type: nucl

dada2:
  trunc_len_f: {field('truncF', '220')}
  trunc_len_r: {field('truncR', '180')}
  trim_left_f: 0
  trim_left_r: 0
  chimera_method: consensus

taxonomy:
  header_parser: simple
  unassigned_label: Unassigned

blast:
  task: blastn
  max_target_seqs: 10
  max_evalue: 1e-20
  min_identity: {field('identity', '97.0')}
  min_query_coverage: {field('coverage', '90.0')}

diversity:
  sampling_depth: {field('samplingDepth', '1000')}
  metadata_category: group
"""
    CONFIG_PATH.write_text(text, encoding="utf-8")


def run_workflow(dry_run: bool = False) -> None:
    with process_lock:
        state.update({"running": True, "returncode": None, "started_at": time.time(), "finished_at": None, "message": "正在运行"})
    command = ["python", str(WORKFLOW_SCRIPT), "run", "--config", str(CONFIG_PATH)]
    if dry_run:
        command.append("--dry-run")
    with LOG_PATH.open("ab") as log:
        log.write(("\n\n$ " + " ".join(command) + "\n").encode("utf-8"))
        proc = subprocess.Popen(command, cwd=WORKSPACE, stdout=log, stderr=subprocess.STDOUT)
        returncode = proc.wait()
    with process_lock:
        state.update({
            "running": False,
            "returncode": returncode,
            "finished_at": time.time(),
            "message": "运行完成" if returncode == 0 else "运行失败，请查看日志",
        })


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path).path
        if parsed == "/":
            return str(APP_DIR / "index.html")
        return str(APP_DIR / parsed.lstrip("/"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path).path
        if parsed == "/api/status":
            payload = dict(state)
            payload["config_exists"] = CONFIG_PATH.exists()
            payload["log_tail"] = LOG_PATH.read_text(encoding="utf-8", errors="replace")[-5000:] if LOG_PATH.exists() else ""
            json_response(self, payload)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path).path
        if parsed == "/api/upload":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                fields, files = parse_multipart(self.headers, self.rfile.read(content_length))
            except Exception as exc:
                json_response(self, {"ok": False, "message": f"上传解析失败：{exc}"}, 400)
                return
            FASTQ_DIR.mkdir(parents=True, exist_ok=True)
            REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
            saved_fastq = [save_uploaded_file(item, FASTQ_DIR) for item in files.get("fastqFiles", [])]
            metadata_items = files.get("metadataFile", [])
            reference_items = files.get("referenceFile", [])
            metadata = save_uploaded_file(metadata_items[0], UPLOAD_DIR) if metadata_items else None
            reference = save_uploaded_file(reference_items[0], REFERENCE_DIR) if reference_items else None
            if not saved_fastq or metadata is None or reference is None:
                json_response(self, {"ok": False, "message": "请上传 FASTQ、元数据 TSV 和参考 FASTA 文件。"}, 400)
                return
            write_config(fields, metadata, reference)
            json_response(self, {"ok": True, "message": "文件已上传，配置已生成。", "fastq_count": len(saved_fastq), "config": CONFIG_PATH.read_text(encoding="utf-8")})
            return
        if parsed == "/api/run" or parsed == "/api/dry-run":
            with process_lock:
                if state["running"]:
                    json_response(self, {"ok": False, "message": "已有任务正在运行。"}, 409)
                    return
            if not CONFIG_PATH.exists():
                json_response(self, {"ok": False, "message": "请先上传文件并生成配置。"}, 400)
                return
            dry_run = parsed == "/api/dry-run"
            thread = threading.Thread(target=run_workflow, kwargs={"dry_run": dry_run}, daemon=True)
            thread.start()
            json_response(self, {"ok": True, "message": "任务已启动。"})
            return
        json_response(self, {"ok": False, "message": "未知接口。"}, 404)


def main() -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), Handler)
    print(f"本地网站已启动：http://localhost:{server.server_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
