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
COPY infra/python-constraints.txt /constraints.txt
RUN set -eu; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir -i "$PIP_INDEX_URL" -c /constraints.txt /sdk; then exit 0; fi; \
      echo "pip attempt $i/5 failed — retrying in 5s"; \
      sleep 5; \
    done; \
    echo "pip: all 5 attempts failed"; exit 1
COPY scripts/verify-python-mcp.sh /usr/local/bin/verify-python-mcp
RUN /usr/local/bin/verify-python-mcp
COPY services/chat-service/app/ ./app/

# CP-1 / M1 — the agent-runtime manifest is a shipped ARTIFACT, not a build-time nicety.
# `load()` treats an absent manifest as EMPTY, which is the correct fail-safe and is also
# indistinguishable from a correctly-empty one — so while CP-1 admits nothing, omitting the file
# looks exactly like shipping it. That stops being true at CP-4, when the first declaration is
# admitted and an absent file would silently serve an empty surface instead of the real one.
# Copy it now, while the two states still agree and the mistake is cheap.
COPY contracts/agent-runtime-manifest.json ./contracts/agent-runtime-manifest.json

# 🔴 **CP-5 — AND THE SAME MISTAKE WAS ONE LINE AWAY FROM SHIPPING AGAIN.** The comment above
# says an absent artifact is INDISTINGUISHABLE from a correctly-empty one. Both CP-5 registries
# fail exactly that way: `promotion` treats a missing tool-contract registry as *no tool declares
# a contract* (so nothing can ever be promoted), and `stream_service._ref_registry` treats a
# missing ref registry as *no ref type is declared* (so resolution is silently inert) — each is a
# legitimate empty state at load, and each is a dead mechanism in production.
#
# That is the `agentruntime_arm` shape a third time: a flag with no compose entry,
# `sweep_expired_runs` with no caller, `resolve_arguments` with no production caller. The repo
# tests could not see it — they read the checkout, and the checkout always has the files.
# `test_THE_DOCKERFILE_SHIPS_EVERY_CONTRACT_THE_RUNTIME_READS` is what makes this a gate.
COPY contracts/agent-runtime-tool-contracts.json ./contracts/agent-runtime-tool-contracts.json
COPY contracts/agent-runtime-ref-resolvers.json ./contracts/agent-runtime-ref-resolvers.json
# 🔴 **CP-6.1 SHIPPED WITHOUT THIS LINE AND THEREFORE NEVER RAN.** Measured 2026-08-11: the
# registry was absent from /app/contracts in the deployed image, `path.exists()` was False, the
# loader returned an empty registry, and the whole closed-vocabulary block was skipped in silence.
# A forced live turn — an unknown kind on the exact bound parameter — went to the wire and failed
# at the backend with the old message; `refusal_kind` was never stamped, and corpus-wide
# `unknown_vocabulary_value` had fired ZERO times since the checkpoint closed.
# The guard above (`test_THE_DOCKERFILE_SHIPS_EVERY_CONTRACT_THE_RUNTIME_READS`) EXISTED and
# did not catch it, because its file list was TYPED BY HAND. It now DERIVES the list from
# the runtime's own `*_REGISTRY_FILENAME` constants, so a new registry is covered the
# moment it exists rather than when somebody remembers.
COPY contracts/agent-runtime-vocabularies.json ./contracts/agent-runtime-vocabularies.json

ENV PORT=8090
EXPOSE 8090

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
