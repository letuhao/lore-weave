FROM python:3.12-slim
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override only to point at a mirror/proxy you trust (any index: an EU/US
# mirror, a corporate proxy, a local devpi cache) when the PyPI path is unusable:
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
# NOTE: this is NOT the fix for a flaky network — the retry loop below is.
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

# Build context is the repo root (compose sets `context: ..`,
# `dockerfile: services/learning-service/Dockerfile`) to match the other
# Python services.

COPY services/learning-service/requirements.txt .
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
# Q1 (Production Eval + Feedback Flywheel): learning-service now hosts the
# quality plane and imports `loreweave_eval` (the lifted extraction-quality
# scorer: EvalResult, EvalSink, JudgePanel). Install the local SDK — same
# pattern as knowledge-service. It also brings loreweave_llm/extraction, which
# the online-eval consumer (phase Q4) will use to run the judge via the gateway.
COPY sdks/python /sdk
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
COPY services/learning-service/app/ ./app/

ENV PORT=8094
EXPOSE 8094

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8094/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
