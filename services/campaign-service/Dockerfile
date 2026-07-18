# Auto-Draft Factory S1 — campaign-service. Build context is the repo root
# (set in docker-compose.yml) so we can COPY the local SDKs alongside the
# service code. Reference impl: services/translation-service/Dockerfile.
FROM python:3.12-slim
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override only to point at a mirror/proxy you trust (any index: an EU/US
# mirror, a corporate proxy, a local devpi cache) when the PyPI path is unusable:
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
# NOTE: this is NOT the fix for a flaky network — the retry loop below is.
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

COPY services/campaign-service/requirements.txt .
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
# Install the local SDKs (loreweave_obs for tracing parity with the other
# Python services). campaign-service makes NO direct provider calls — it
# only drives the existing per-service job APIs over internal-token.
COPY sdks/python /sdk
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
COPY services/campaign-service/app/ ./app/

ENV PORT=8095
EXPOSE 8095

HEALTHCHECK --interval=5s --timeout=3s --start-period=15s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8095/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
