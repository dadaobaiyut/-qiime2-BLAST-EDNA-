const form = document.querySelector('#config-form');
const output = document.querySelector('#yaml-output');
const copyButton = document.querySelector('#copy-config');
const uploadButton = document.querySelector('#upload-data');
const dryRunButton = document.querySelector('#dry-run');
const runButton = document.querySelector('#run-workflow');
const statusOutput = document.querySelector('#status-output');

function value(name) {
  return form.elements[name].value.trim();
}

function renderConfig() {
  const yaml = `project:
  name: ${value('projectName')}
  output_dir: results
  threads: ${value('threads')}

input:
  fastq_dir: uploads/fastq
  metadata: uploads/metadata.tsv
  qiime_input_format: CasavaOneEightSingleLanePerSampleDirFmt

manifest:
  make_manifest: false

reference:
  fasta: uploads/reference/fish_reference.fasta
  blast_db_prefix: null
  db_type: nucl

dada2:
  trunc_len_f: ${value('truncF')}
  trunc_len_r: ${value('truncR')}
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
  min_identity: ${value('identity')}
  min_query_coverage: ${value('coverage')}

diversity:
  sampling_depth: ${value('samplingDepth')}
  metadata_category: group
`;
  output.textContent = yaml;
}

async function postForm(url) {
  const response = await fetch(url, { method: 'POST', body: new FormData(form) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || '请求失败');
  return payload;
}

async function postJson(url) {
  const response = await fetch(url, { method: 'POST' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || '请求失败');
  return payload;
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/status');
    if (!response.ok) return;
    const status = await response.json();
    statusOutput.textContent = `状态：${status.message}\n返回码：${status.returncode ?? '无'}\n\n最近日志：\n${status.log_tail || '暂无日志'}`;
  } catch (_error) {
    statusOutput.textContent = '静态预览模式：启动 Docker Web 服务后可查看任务状态。';
  }
}

form.addEventListener('input', renderConfig);
copyButton.addEventListener('click', async () => {
  await navigator.clipboard.writeText(output.textContent);
  copyButton.textContent = '已复制';
  setTimeout(() => { copyButton.textContent = '复制'; }, 1400);
});

uploadButton.addEventListener('click', async () => {
  try {
    const payload = await postForm('/api/upload');
    output.textContent = payload.config;
    statusOutput.textContent = payload.message;
  } catch (error) {
    statusOutput.textContent = error.message;
  }
});

dryRunButton.addEventListener('click', async () => {
  try {
    const payload = await postJson('/api/dry-run');
    statusOutput.textContent = payload.message;
  } catch (error) {
    statusOutput.textContent = error.message;
  }
});

runButton.addEventListener('click', async () => {
  try {
    const payload = await postJson('/api/run');
    statusOutput.textContent = payload.message;
  } catch (error) {
    statusOutput.textContent = error.message;
  }
});

renderConfig();
refreshStatus();
setInterval(refreshStatus, 3000);
