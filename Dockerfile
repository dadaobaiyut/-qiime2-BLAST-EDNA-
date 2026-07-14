# 以 QIIME 2 官方 Docker 镜像作为基础镜像。
# 可在构建时覆盖版本，例如：
# docker build --build-arg QIIME_IMAGE=quay.io/qiime2/qiime2:2026.4 -t qiime2-blast-edna:zh .
ARG QIIME_IMAGE=quay.io/qiime2/qiime2:2026.4
FROM ${QIIME_IMAGE}

USER root

# BLAST+ 用于本地鱼类参考库注释；ca-certificates 用于容器内访问 HTTPS 资源。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ncbi-blast+ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY edna_qiime2_blast_workflow.py /opt/edna-workflow/edna_qiime2_blast_workflow.py
COPY config.example.yaml /opt/edna-workflow/config.example.yaml
COPY README.md /opt/edna-workflow/README.md

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "/opt/edna-workflow/edna_qiime2_blast_workflow.py"]
CMD ["--help"]
