# ── Stage 1: deps ─────────────────────────────────────────────
# Build context is repo root (set in docker-compose.yml) so we can COPY the
# local SDKs alongside the service code. Mirrors knowledge-service.
FROM python:3.12-slim AS deps
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override ONLY when the local network blocks PyPI (some ISPs reset the
# connection mid-download, which fails any not-yet-cached pip layer):
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app
COPY services/composition-service/requirements.txt .
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

# Local SDKs (loreweave_obs / loreweave_llm / loreweave_eval / …). Direct
# provider-SDK calls are forbidden per the CLAUDE.md gateway invariant.
COPY sdks/python /sdk
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk

# ── Stage 2: test ─────────────────────────────────────────────
# CI target: docker build --target test .
FROM deps AS test
ARG PIP_INDEX_URL=https://pypi.org/simple

COPY services/composition-service/requirements-test.txt .
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements-test.txt

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
