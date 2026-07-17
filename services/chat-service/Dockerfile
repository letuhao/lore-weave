FROM python:3.12-slim
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override ONLY when the local network blocks PyPI (some ISPs reset the
# connection mid-download, which fails any not-yet-cached pip layer):
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

# Phase 1c-ii: build context is repo root so we can COPY the local
# loreweave_llm SDK package alongside the service code. Existing
# infra/docker-compose.yml entry sets context to `..` (repo root) and
# dockerfile to `services/chat-service/Dockerfile`.

COPY services/chat-service/requirements.txt .
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

# Install the local LLM SDK. Service code imports `loreweave_llm` which
# resolves to this package — direct provider-SDK calls (litellm,
# openai-python) are forbidden per CLAUDE.md gateway invariant.
COPY sdks/python /sdk
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk

COPY services/chat-service/app/ ./app/

ENV PORT=8090
EXPOSE 8090

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
