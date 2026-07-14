#!/usr/bin/env python3
"""用于鱼类环境 DNA 多样性分析的 QIIME 2 + BLAST 工作流。"""
from __future__ import annotations

import argparse
import csv
import gzip
import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any



@dataclass
class WorkflowConfig:
    raw: dict[str, Any]
    output_dir: Path
    threads: int


def parse_scalar(value: str) -> Any:
    if value in {"null", "None", "~"}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value.strip('"\'')


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """读取本工作流配置使用的简单两级 YAML。"""
    data: dict[str, Any] = {}
    current_section: str | None = None
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            if not line.startswith(" ") and line.endswith(":"):
                current_section = line[:-1].strip()
                data[current_section] = {}
                continue
            if current_section and line.startswith("  ") and ":" in line:
                key, value = line.strip().split(":", 1)
                data[current_section][key.strip()] = parse_scalar(value.strip())
                continue
            raise ValueError(f"不支持的配置行： {raw_line.rstrip()}")
    return data


def load_config(path: Path) -> WorkflowConfig:
    raw = load_simple_yaml(path)
    project = raw.get("project", {})
    return WorkflowConfig(
        raw=raw,
        output_dir=Path(project.get("output_dir", "results")),
        threads=int(project.get("threads", 1)),
    )


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(output_dir / "workflow.log")],
    )


def require_tools(tools: list[str]) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise SystemExit(f"缺少必需命令： {', '.join(missing)}")


def run_command(command: list[str], dry_run: bool = False) -> None:
    logging.info("$ %s", " ".join(map(str, command)))
    if dry_run:
        return
    subprocess.run(command, check=True)


def fastq_open(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open("r", encoding="utf-8")


def make_manifest(fastq_dir: Path, manifest_path: Path) -> None:
    pairs: dict[str, dict[str, Path]] = {}
    pattern = re.compile(r"(.+?)(?:_S\d+)?(?:_L\d{3})?_R([12])_001\.f(?:ast)?q(?:\.gz)?$")
    for fastq in sorted(fastq_dir.glob("*.f*q*")):
        match = pattern.match(fastq.name)
        if not match:
            continue
        sample_id, read = match.group(1), match.group(2)
        pairs.setdefault(sample_id, {})[read] = fastq.resolve()
    if not pairs:
        raise SystemExit(f"未找到双端 FASTQ 文件目录： {fastq_dir}")
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["sample-id", "forward-absolute-filepath", "reverse-absolute-filepath"])
        for sample_id, reads in pairs.items():
            if "1" not in reads or "2" not in reads:
                raise SystemExit(f"Sample {sample_id} 缺少成对的 R1/R2 文件")
            writer.writerow([sample_id, reads["1"], reads["2"]])


def parse_fasta_headers(fasta: Path) -> dict[str, str]:
    headers: dict[str, str] = {}
    with fastq_open(fasta) as handle:
        for line in handle:
            if line.startswith(">"):
                text = line[1:].strip()
                seq_id, _, description = text.partition(" ")
                taxonomy = description or seq_id
                taxonomy = taxonomy.replace("sample_taxonomy=", "").replace(" ", "_")
                headers[seq_id] = taxonomy
    return headers


def convert_blast_to_taxonomy(blast_tsv: Path, reference_fasta: Path, taxonomy_tsv: Path, cfg: dict[str, Any]) -> None:
    id_to_taxonomy = parse_fasta_headers(reference_fasta)
    min_identity = float(cfg["blast"].get("min_identity", 97.0))
    min_qcov = float(cfg["blast"].get("min_query_coverage", 90.0))
    max_evalue = float(cfg["blast"].get("max_evalue", 1e-20))
    unassigned = cfg.get("taxonomy", {}).get("unassigned_label", "Unassigned")
    best: dict[str, tuple[float, float, float, str]] = {}
    with blast_tsv.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            qseqid = row["qseqid"]
            pident = float(row["pident"])
            qcov = float(row["qcovs"])
            evalue = float(row["evalue"])
            bitscore = float(row["bitscore"])
            if pident < min_identity or qcov < min_qcov or evalue > max_evalue:
                continue
            current = best.get(qseqid)
            if current is None or bitscore > current[0]:
                best[qseqid] = (bitscore, pident, qcov, row["sseqid"])
    with taxonomy_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["Feature ID", "Taxon", "Confidence"])
        for feature_id, (_bitscore, pident, _qcov, subject_id) in sorted(best.items()):
            writer.writerow([feature_id, id_to_taxonomy.get(subject_id, unassigned), f"{pident / 100:.4f}"])


def run_workflow(config_path: Path, dry_run: bool) -> None:
    cfg = load_config(config_path)
    setup_logging(cfg.output_dir)
    if not dry_run:
        require_tools(["qiime", "blastn", "makeblastdb"])
    raw = cfg.raw
    input_cfg = raw["input"]
    reference_cfg = raw["reference"]
    blast_cfg = raw["blast"]
    dada2_cfg = raw["dada2"]
    diversity_cfg = raw["diversity"]

    fastq_dir = Path(input_cfg["fastq_dir"])
    metadata = Path(input_cfg["metadata"])
    manifest = cfg.output_dir / "manifest.tsv"
    blast_dir = cfg.output_dir / "blast"
    blast_dir.mkdir(parents=True, exist_ok=True)

    if raw.get("manifest", {}).get("make_manifest", False):
        make_manifest(fastq_dir, manifest)

    db_prefix = reference_cfg.get("blast_db_prefix")
    reference_fasta = Path(reference_cfg["fasta"]) if reference_cfg.get("fasta") else None
    if not db_prefix:
        if reference_fasta is None:
            raise SystemExit("必须设置 reference.fasta 或 reference.blast_db_prefix")
        db_prefix = str(blast_dir / "fish_reference")
        run_command(["makeblastdb", "-in", str(reference_fasta), "-dbtype", reference_cfg.get("db_type", "nucl"), "-out", db_prefix], dry_run)

    import_input = str(fastq_dir if input_cfg["qiime_input_format"] == "CasavaOneEightSingleLanePerSampleDirFmt" else manifest)
    run_command(["qiime", "tools", "import", "--type", "SampleData[PairedEndSequencesWithQuality]", "--input-path", import_input, "--input-format", input_cfg["qiime_input_format"], "--output-path", str(cfg.output_dir / "demux-paired-end.qza")], dry_run)
    run_command(["qiime", "demux", "summarize", "--i-data", str(cfg.output_dir / "demux-paired-end.qza"), "--o-visualization", str(cfg.output_dir / "demux.qzv")], dry_run)
    run_command(["qiime", "dada2", "denoise-paired", "--i-demultiplexed-seqs", str(cfg.output_dir / "demux-paired-end.qza"), "--p-trunc-len-f", str(dada2_cfg["trunc_len_f"]), "--p-trunc-len-r", str(dada2_cfg["trunc_len_r"]), "--p-trim-left-f", str(dada2_cfg.get("trim_left_f", 0)), "--p-trim-left-r", str(dada2_cfg.get("trim_left_r", 0)), "--p-chimera-method", dada2_cfg.get("chimera_method", "consensus"), "--p-n-threads", str(cfg.threads), "--o-table", str(cfg.output_dir / "table.qza"), "--o-representative-sequences", str(cfg.output_dir / "rep-seqs.qza"), "--o-denoising-stats", str(cfg.output_dir / "denoising-stats.qza")], dry_run)
    run_command(["qiime", "tools", "export", "--input-path", str(cfg.output_dir / "rep-seqs.qza"), "--output-path", str(blast_dir / "rep-seqs")], dry_run)

    blast_out = blast_dir / "asv_vs_fish.tsv"
    outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qcovs"
    run_command([blast_cfg.get("task", "blastn"), "-query", str(blast_dir / "rep-seqs" / "dna-sequences.fasta"), "-db", db_prefix, "-out", str(blast_out), "-outfmt", outfmt, "-max_target_seqs", str(blast_cfg.get("max_target_seqs", 10)), "-evalue", str(blast_cfg.get("max_evalue", 1e-20)), "-num_threads", str(cfg.threads)], dry_run)

    taxonomy_tsv = blast_dir / "taxonomy.tsv"
    if not dry_run:
        if reference_fasta is None:
            raise SystemExit("需要 reference.fasta 才能将 BLAST ID 转换为 taxonomy.tsv")
        convert_blast_to_taxonomy(blast_out, reference_fasta, taxonomy_tsv, raw)
    run_command(["qiime", "tools", "import", "--type", "FeatureData[Taxonomy]", "--input-format", "TSVTaxonomyFormat", "--input-path", str(taxonomy_tsv), "--output-path", str(cfg.output_dir / "taxonomy.qza")], dry_run)
    run_command(["qiime", "taxa", "barplot", "--i-table", str(cfg.output_dir / "table.qza"), "--i-taxonomy", str(cfg.output_dir / "taxonomy.qza"), "--m-metadata-file", str(metadata), "--o-visualization", str(cfg.output_dir / "taxa-bar-plots.qzv")], dry_run)
    run_command(["qiime", "diversity", "core-metrics", "--i-table", str(cfg.output_dir / "table.qza"), "--m-metadata-file", str(metadata), "--p-sampling-depth", str(diversity_cfg["sampling_depth"]), "--output-dir", str(cfg.output_dir / "core-metrics")], dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 QIIME 2 + BLAST 鱼类环境 DNA 工作流", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="显示帮助信息")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="运行完整工作流")
    run_parser.add_argument("--config", required=True, type=Path, help="YAML 配置文件")
    run_parser.add_argument("--dry-run", action="store_true", help="只打印命令，不实际执行")
    args = parser.parse_args()
    if args.command == "run":
        run_workflow(args.config, args.dry_run)


if __name__ == "__main__":
    main()
