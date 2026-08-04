FROM python:3.12-slim
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override only to point at a mirror/proxy you trust (any index: an EU/US
# mirror, a corporate proxy, a local devpi cache) when the PyPI path is unusable:
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
# NOTE: this is NOT the fix for a flaky network — the retry loop below is.
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

# Phase 1c-ii: build context is repo root so we can COPY the local
# loreweave_llm SDK package alongside the service code. Existing
# infra/docker-compose.yml entry sets context to `..` (repo root) and
# dockerfile to `services/chat-service/Dockerfile`.

COPY services/chat-service/requirements.txt .
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
# Install the local LLM SDK. Service code imports `loreweave_llm` which
# resolves to this package — direct provider-SDK calls (litellm,
# openai-python) are forbidden per CLAUDE.md gateway invariant.
COPY sdks/python /sdk
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
COPY services/chat-service/app/ ./app/

# CP-1 / M1 — the agent-runtime manifest is a shipped ARTIFACT, not a build-time nicety.
# `load()` treats an absent manifest as EMPTY, which is the correct fail-safe and is also
# indistinguishable from a correctly-empty one — so while CP-1 admits nothing, omitting the file
# looks exactly like shipping it. That stops being true at CP-4, when the first declaration is
# admitted and an absent file would silently serve an empty surface instead of the real one.
# Copy it now, while the two states still agree and the mistake is cheap.
COPY contracts/agent-runtime-manifest.json ./contracts/agent-runtime-manifest.json

ENV PORT=8090
EXPOSE 8090

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
