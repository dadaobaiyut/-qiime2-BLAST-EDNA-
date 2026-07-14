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

WORKDIR /app

COPY edna_qiime2_blast_workflow.py /app/edna_qiime2_blast_workflow.py
COPY edna_web_server.py /app/edna_web_server.py
COPY config.example.yaml /app/config.example.yaml
COPY README.md /app/README.md
COPY index.html /app/index.html
COPY styles.css /app/styles.css
COPY app.js /app/app.js

ENV PYTHONUNBUFFERED=1 \
    EDNA_APP_DIR=/app \
    EDNA_WORKSPACE=/workspace \
    PORT=8000

EXPOSE 8000
CMD ["python", "/app/edna_web_server.py"]
