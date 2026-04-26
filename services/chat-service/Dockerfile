FROM python:3.12-slim

WORKDIR /app

# Phase 1c-ii: build context is repo root so we can COPY the local
# loreweave_llm SDK package alongside the service code. Existing
# infra/docker-compose.yml entry sets context to `..` (repo root) and
# dockerfile to `services/chat-service/Dockerfile`.

COPY services/chat-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the local LLM SDK. Service code imports `loreweave_llm` which
# resolves to this package — direct provider-SDK calls (litellm,
# openai-python) are forbidden per CLAUDE.md gateway invariant.
COPY sdks/python /sdk
RUN pip install --no-cache-dir /sdk

COPY services/chat-service/app/ ./app/

ENV PORT=8090
EXPOSE 8090

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
