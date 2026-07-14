# QIIME2-BLAST-eDNA 中文版

一个面向鱼类 eDNA 扩增子数据的可复现工作流模板，串联 **QIIME 2** 质控/ASV 构建与 **BLAST** 物种注释，输出鱼类多样性分析常用结果。

> 目标：让用户准备好原始双端测序文件、元数据表、鱼类参考序列库后，用一个配置文件启动完整分析。

## 功能

- 导入 Casava 1.8 格式双端测序数据到 QIIME 2。
- 使用 DADA2 去噪、合并双端序列、去嵌合体并生成 ASV 表和代表序列。
- 导出 ASV 序列并用本地 BLAST 数据库进行物种注释。
- 根据 BLAST 命中阈值生成物种注释 TSV。
- 导入 BLAST 注释到 QIIME 2 并生成物种组成柱状图。
- 生成核心多样性结果（α/β 多样性、PCoA、Emperor 可视化）。
- 自动生成 `manifest.tsv`、运行日志和结果目录。

## 目录结构

```text
.
├── README.md
├── index.html
├── styles.css
├── app.js
├── config.example.yaml
└── edna_qiime2_blast_workflow.py
```

## 环境要求

请在已经安装 QIIME 2 和 BLAST+ 的环境中运行；工作流脚本仅使用 Python 标准库。推荐用 conda/mamba：

```bash
mamba create -n edna-fish -c qiime2 -c conda-forge -c bioconda qiime2 blast
mamba activate edna-fish
```

也可以在已有 QIIME 2 环境中补充安装：

```bash
mamba install -c bioconda -c conda-forge blast
```

## 输入文件

### 1. FASTQ 文件

默认支持 Casava 1.8 命名格式，例如：

```text
sampleA_S1_L001_R1_001.fastq.gz
sampleA_S1_L001_R2_001.fastq.gz
sampleB_S2_L001_R1_001.fastq.gz
sampleB_S2_L001_R2_001.fastq.gz
```

### 2. 元数据表

QIIME 2 元数据 TSV，例如：

```text
sample-id	group	site
sampleA	control	lake1
sampleB	impact	lake2
```

第一列必须为 `sample-id`。

### 3. 鱼类参考库

准备一个参考 FASTA，序列表头建议包含物种名或可解析的分类信息，例如：

```text
>NC_001 sample_taxonomy=k__Eukaryota;p__Chordata;c__Actinopteri;o__Cypriniformes;f__Cyprinidae;g__Cyprinus;s__Cyprinus_carpio
ACGT...
```

首次运行时工作流会自动执行 `makeblastdb`。如果已经建好库，也可以在配置中直接提供 BLAST 数据库前缀。



## Docker 本地网页运行方式

如果你使用 Docker，不需要登录服务器或进入 conda/QIIME 2 环境。构建并启动本地网站后，直接在浏览器上传测序文件、元数据和参考库即可生成配置并启动分析。

```bash
# 1. 构建包含 QIIME 2、BLAST+、网页和工作流脚本的镜像
docker build -t qiime2-blast-edna:zh .

# 2. 启动本地网页
docker run --rm -it -p 8000:8000 -v "$PWD":/workspace qiime2-blast-edna:zh
```

然后打开 `http://localhost:8000`，在网页中完成：

1. 上传双端 FASTQ 文件；
2. 上传 `metadata.tsv`；
3. 上传鱼类参考 FASTA；
4. 点击“上传并生成配置”；
5. 点击“预览命令”或“开始分析”。

也可以用 Docker Compose 一条命令启动本地网站：

```bash
docker compose up app
```

容器会把当前项目目录挂载到 `/workspace`，上传文件会保存到 `uploads/`，分析结果会保存到 `results/`，运行日志会保存到 `web_workflow.log`。默认基础镜像为 `quay.io/qiime2/qiime2:2026.4`，如需固定其他 QIIME 2 版本，可在构建时传入 `--build-arg QIIME_IMAGE=...`。

如果仍想用命令行方式运行，也可以：

```bash
docker compose run --rm workflow-dry-run
docker compose run --rm workflow
```

## 网站界面

本仓库现在提供静态网站入口，可用于展示流程并在线生成 `config.yaml`：

```bash
python -m http.server 8000
```

然后在浏览器打开 `http://localhost:8000`。网站不会在浏览器中直接运行大型测序计算，而是帮助整理参数、复制配置，并指导用户在本地或服务器 QIIME 2 环境中运行命令行工作流。

## 快速开始

1. 复制示例配置：

```bash
cp config.example.yaml config.yaml
```

2. 修改 `config.yaml` 中的路径和参数。

3. 运行完整工作流：

```bash
python edna_qiime2_blast_workflow.py run --config config.yaml
```

4. 如果只想预览将要运行的命令：

```bash
python edna_qiime2_blast_workflow.py run --config config.yaml --dry-run
```

## 主要输出

默认输出到 `results/`：

- `manifest.tsv`：自动生成的 QIIME 2 清单文件。
- `demux-paired-end.qza` / `demux.qzv`：导入后的原始序列和质量概览。
- `table.qza`、`rep-seqs.qza`、`denoising-stats.qza`：DADA2 结果。
- `blast/asv_vs_fish.tsv`：BLAST 原始注释结果。
- `blast/taxonomy.tsv`：转换后的 QIIME 2 taxonomy 表。
- `taxonomy.qza`、`taxa-bar-plots.qzv`：注释结果和物种组成可视化。
- `core-metrics/`：核心多样性分析结果。
- `workflow.log`：完整命令运行日志。

## 配置说明

见 [`config.example.yaml`](config.example.yaml)。关键参数包括：

- `input.fastq_dir`：FASTQ 文件目录。
- `input.metadata`：元数据 TSV。
- `reference.fasta`：鱼类参考 FASTA；或设置 `reference.blast_db_prefix`。
- `dada2.trunc_len_f` / `dada2.trunc_len_r`：根据 `demux.qzv` 质量图调整。
- `blast.min_identity`、`blast.min_query_coverage`、`blast.max_evalue`：控制注释可信度。
- `diversity.sampling_depth`：核心多样性抽平深度。

## 典型调参建议

- 先用 `--dry-run` 检查路径与命令。
- 首次真实运行后打开 `demux.qzv` 查看质量图，再调整 DADA2 截断长度。
- 鱼类 eDNA 常见片段较短，应使用与引物区域匹配的本地鱼类参考库；参考库质量会直接影响物种注释准确性。
- 对 BLAST 注释建议同时设置相似度、查询覆盖度和期望值阈值，并人工复核生态上异常的物种。

## 注意

本项目提供的是自动化工作流框架，不随仓库分发商业或受限数据库。请确保参考库来源合法，并根据研究区域补充本地鱼类物种序列。
