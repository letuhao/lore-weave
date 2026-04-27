# Phase 4c-α: build context is the repo root (set in docker-compose.yml)
# so we can COPY the local SDKs alongside the service code. Reference
# impl: services/knowledge-service/Dockerfile (Phase 4a-α) +
# services/worker-ai/Dockerfile (Phase 4b-γ).
FROM python:3.12-slim

WORKDIR /app

COPY services/translation-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the local SDKs. The pyproject ships two top-level packages:
#   - loreweave_llm — gateway client (streaming + async jobs)
#   - loreweave_extraction — Pass 2 extraction library (unused here
#     for now, but installed via the shared pyproject)
# Translation-service uses loreweave_llm; the gateway invariant
# (CLAUDE.md) forbids direct provider-SDK calls (litellm, openai).
COPY sdks/python /sdk
RUN pip install --no-cache-dir /sdk

COPY services/translation-service/app/ ./app/

ENV PORT=8087
EXPOSE 8087

HEALTHCHECK --interval=5s --timeout=3s --start-period=15s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8087/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
