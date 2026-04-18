# ── Stage 1: deps ─────────────────────────────────────────────
# Install production dependencies into a cached layer.
FROM python:3.12-slim AS deps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: test ─────────────────────────────────────────────
# CI target: docker build --target test .
# Installs test deps, copies source + tests, runs pytest.
FROM deps AS test

COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

COPY app/ ./app/
COPY eval/ ./eval/
COPY tests/ ./tests/
COPY pytest.ini .

RUN KNOWLEDGE_DB_URL=postgresql://u:p@localhost:5432/knowledge \
    GLOSSARY_DB_URL=postgresql://u:p@localhost:5432/glossary \
    INTERNAL_SERVICE_TOKEN=test_token \
    JWT_SECRET=test_secret_that_is_at_least_32_chars_long \
    python -m pytest tests/unit/ -x -q --tb=short

# ── Stage 3: production ──────────────────────────────────────
# Slim final image — no tests, no test deps.
FROM deps AS production

COPY app/ ./app/

RUN adduser --system --group --no-create-home app \
    && chown -R app:app /app
USER app

ENV PORT=8092
EXPOSE 8092

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8092/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
