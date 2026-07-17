FROM python:3.12-slim
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override ONLY when the local network blocks PyPI (some ISPs reset the
# connection mid-download, which fails any not-yet-cached pip layer):
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

# Compose slice 3 (mode F) — OCR + PDF rasterisation system deps. Tesseract + the
# platform's target-locale language packs (Simplified/Traditional Chinese, Japanese,
# Vietnamese; English ships with tesseract-ocr) for book-aware scanned-PDF OCR
# (D-COMPOSE-S3-OCR-LANG), and poppler (pdf2image) to rasterise pages. Keep this set
# == app/files/extract._INSTALLED_OCR_LANGS. Service-only: extraction runs in this
# service's /uploads background task; the worker only re-drives the already-ingested
# corpus, so it needs none of this. Absence degrades to text-layer-only (extract.py
# is import/binary-guarded), but the deployed image ships OCR.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
       tesseract-ocr-jpn tesseract-ocr-vie poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Build context = repo root (infra/docker-compose.yml sets `context: ..`), so
# COPY paths are repo-relative.
COPY services/lore-enrichment-service/requirements.txt .
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

# C18 — install the local SDKs so loreweave_obs (setup_tracing +
# current_otel_trace_id) is importable. Mirrors knowledge-service / chat-service
# Dockerfiles (COPY sdks/python + pip install /sdk). Additive: OTel tracing is a
# no-op until OTEL_EXPORTER_OTLP_ENDPOINT is set in the environment.
COPY sdks/python /sdk
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk

COPY services/lore-enrichment-service/app/ ./app/

# LE-PROD-2 P3b — ship the eval-suite TOML so the in-container eval-run route
# (POST /internal/eval/{project}/run) can load it (it lives at repo-root eval/,
# not under app/). The route resolves /app/eval/ first, repo-root in dev.
COPY eval/enrichment-eval-suite.toml ./eval/enrichment-eval-suite.toml

ENV PORT=8093
# C18 — OTLP trace export endpoint. Empty by default → setup_tracing is a no-op
# (dev without the observability stack still runs). The compose/prod env wires a
# real endpoint to enable tracing. NEVER a hardcoded URL here.
ENV OTEL_EXPORTER_OTLP_ENDPOINT=""
EXPOSE 8093

# Liveness probe (constant ok, no DB). DB-readiness is the separate /ready probe
# (DEFERRED-042); an orchestrator gates traffic on /ready but uses /health for
# liveness so a brief DB blip drains traffic without crash-looping the pod.
HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8093/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
