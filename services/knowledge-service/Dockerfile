# ── Stage 1: deps ─────────────────────────────────────────────
# Install production dependencies into a cached layer.
#
# Phase 4a-α: build context is repo root (set in docker-compose.yml)
# so we can COPY the local SDKs alongside the service code. Reference
# impl: services/chat-service/Dockerfile (Phase 1c-ii).
FROM python:3.12-slim AS deps

WORKDIR /app
COPY services/knowledge-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the local SDKs. The pyproject ships two top-level packages:
#   - loreweave_llm — gateway client (streaming + async jobs)
#   - loreweave_extraction — Pass 2 extraction library (Phase 4b-α)
# Service code imports both. Direct provider-SDK calls (litellm,
# openai, anthropic) are forbidden per CLAUDE.md gateway invariant.
COPY sdks/python /sdk
RUN pip install --no-cache-dir /sdk

# ── Stage 2: test ─────────────────────────────────────────────
# CI target: docker build --target test .
# Installs test deps, copies source + tests, runs pytest.
FROM deps AS test

COPY services/knowledge-service/requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

COPY services/knowledge-service/app/ ./app/
COPY services/knowledge-service/eval/ ./eval/
COPY services/knowledge-service/tests/ ./tests/
COPY services/knowledge-service/pytest.ini .

RUN KNOWLEDGE_DB_URL=postgresql://u:p@localhost:5432/knowledge \
    GLOSSARY_DB_URL=postgresql://u:p@localhost:5432/glossary \
    INTERNAL_SERVICE_TOKEN=test_token \
    JWT_SECRET=test_secret_that_is_at_least_32_chars_long \
    python -m pytest tests/unit/ -x -q --tb=short

# ── Stage 3: production ──────────────────────────────────────
# Slim final image — no tests, no test deps.
FROM deps AS production

COPY services/knowledge-service/app/ ./app/

RUN adduser --system --group --no-create-home app \
    && chown -R app:app /app
USER app

ENV PORT=8092
EXPOSE 8092

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8092/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
