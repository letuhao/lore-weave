# ── Stage 1: deps ─────────────────────────────────────────────
# Build context is repo root (set in docker-compose.yml) so we can COPY the
# local SDKs alongside the service code. Mirrors knowledge-service.
FROM python:3.12-slim AS deps
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override only to point at a mirror/proxy you trust (any index: an EU/US
# mirror, a corporate proxy, a local devpi cache) when the PyPI path is unusable:
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
# NOTE: this is NOT the fix for a flaky network — the retry loop below is.
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app
COPY services/composition-service/requirements.txt .
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
# Local SDKs (loreweave_obs / loreweave_llm / loreweave_eval / …). Direct
# provider-SDK calls are forbidden per the CLAUDE.md gateway invariant.
COPY sdks/python /sdk
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
# ── Stage 2: test ─────────────────────────────────────────────
# CI target: docker build --target test .
FROM deps AS test
ARG PIP_INDEX_URL=https://pypi.org/simple

COPY services/composition-service/requirements-test.txt .
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements-test.txt; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
COPY services/composition-service/app/ ./app/
COPY services/composition-service/tests/ ./tests/
COPY services/composition-service/pytest.ini .

RUN COMPOSITION_DB_URL=postgresql://u:p@localhost:5432/composition \
    INTERNAL_SERVICE_TOKEN=test_token \
    JWT_SECRET=test_secret_that_is_at_least_32_chars_long \
    python -m pytest tests/unit/ -x -q --tb=short

# ── Stage 3: production ───────────────────────────────────────
FROM deps AS production

COPY services/composition-service/app/ ./app/

EXPOSE 8093
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8093"]
