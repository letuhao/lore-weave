# Phase 5e-α: build context bumped to repo root so we can COPY the
# Python SDK alongside service code. Mirrors chat-service + translation-
# service patterns. docker-compose.yml passes `context: ..` +
# `dockerfile: services/video-gen-service/Dockerfile`.
FROM python:3.13-slim
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override only to point at a mirror/proxy you trust (any index: an EU/US
# mirror, a corporate proxy, a local devpi cache) when the PyPI path is unusable:
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
# NOTE: this is NOT the fix for a flaky network — the retry loop below is.
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

# SDK install — Phase 5e-α (matches translation-service Phase 4c-α + chat-service pattern).
COPY sdks/python /sdk
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
COPY services/video-gen-service/requirements.txt .
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
COPY services/video-gen-service/app/ app/

ENV HTTP_PORT=8088
EXPOSE 8088

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
