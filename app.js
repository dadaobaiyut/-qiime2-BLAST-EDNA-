const form = document.querySelector('#config-form');
const output = document.querySelector('#yaml-output');
const copyButton = document.querySelector('#copy-config');

function value(name) {
  return form.elements[name].value.trim();
}

function renderConfig() {
  const yaml = `project:
  name: ${value('projectName')}
  output_dir: ${value('outputDir')}
  threads: ${value('threads')}

input:
  fastq_dir: ${value('fastqDir')}
  metadata: ${value('metadata')}
  qiime_input_format: CasavaOneEightSingleLanePerSampleDirFmt

manifest:
  make_manifest: false

reference:
  fasta: ${value('referenceFasta')}
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

form.addEventListener('input', renderConfig);
copyButton.addEventListener('click', async () => {
  await navigator.clipboard.writeText(output.textContent);
  copyButton.textContent = '已复制';
  setTimeout(() => { copyButton.textContent = '复制'; }, 1400);
});

renderConfig();
