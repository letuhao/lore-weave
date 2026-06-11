#!/usr/bin/env python3
"""Unit tests for ai-provider-gate.py Rule 1b (model-backend env-var) detection.

Run: python -m pytest scripts/test_ai_provider_gate.py

The detector is deliberately narrow — it must flag a model-backend wired as a
per-service env var (the D-RERANK-NOT-BYOK mistake) while NOT flagging the sea
of legit infra env vars (INTERNAL_SERVICE_TOKEN, *_SERVICE_URL, *_DB_URL) nor
non-env-var uses (DB columns, log tokens, module constants). These tests pin
both directions so a future tweak can't silently widen or narrow it.
"""
import importlib.util
import os

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "ai_provider_gate",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai-provider-gate.py"),
)
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


# ── should FLAG: a model backend read as platform config ──────────────────
@pytest.mark.parametrize("line", [
    'url = os.getenv("RERANK_URL")',
    'rerank = os.environ.get("RERANK_SERVICE_TOKEN", "")',
    'model = os.environ["RERANK_MODEL"]',
    'base = os.getenv("EMBED_BASE_URL")',
    'tok = os.getenv("STT_API_KEY")',
    'ep = os.getenv("TTS_ENDPOINT")',
    'host = os.getenv("OLLAMA_HOST")',
    'm = os.getenv("LMSTUDIO_MODEL")',
    'm = os.getenv("LM_STUDIO_MODEL")',
    'const u = process.env.RERANK_URL',
    'const t = process.env["EMBED_SERVICE_TOKEN"]',
    'u := os.Getenv("RERANK_ENDPOINT")',
    'm = os.getenv("LOCAL_RERANK_MODEL")',
])
def test_flags_model_backend_env(line):
    assert gate.model_backend_env_names(line), f"expected a hit in: {line}"


# ── should NOT flag: legit infra env vars + non-env-var uses ───────────────
@pytest.mark.parametrize("line", [
    # infra / service-to-service env vars — prefix is a SERVICE, not a model capability
    'tok = os.getenv("INTERNAL_SERVICE_TOKEN")',
    'u = os.getenv("BOOK_SERVICE_URL")',
    'u = os.getenv("PROVIDER_REGISTRY_SERVICE_URL")',
    'u = os.getenv("KNOWLEDGE_SERVICE_URL")',
    'db = os.getenv("DATABASE_URL")',
    'db = os.getenv("TEST_CAMPAIGN_DB_URL")',
    'ep = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")',
    'u = os.getenv("MINIO_EXTERNAL_URL")',
    'u = os.getenv("LLM_GATEWAY_INTERNAL_URL")',
    'const u = process.env.AUTH_SERVICE_URL',
    # NOT an env access — DB column / struct field / log token / module constant
    'EMBEDDING_MODEL = Column(String)',
    'logger.warning("EXTRACTION_REASONING_MODEL job=%s", job_id)',
    'OLLAMA_URL = "http://localhost:11434"',
    'embedding_model: Mapped[str]',
    # model-capability prefix but a non-config suffix → not config wiring
    'path = os.getenv("RERANK_MODEL_PATH")',
])
def test_ignores_non_backend_env(line):
    assert not gate.model_backend_env_names(line), f"false positive in: {line}"


# ── the live tree must be clean (the gate stays green after adding 1b) ─────
def test_full_scan_is_clean():
    """Rule 1b must not introduce a regression: a full scan must still pass.
    If this fails, either a real violation exists (fix it) or the pattern got
    too broad (a legit env var leaked in — tighten it)."""
    backend = []
    for full, rel in gate.iter_full_scan():
        if gate.is_allowlisted(rel):
            continue
        backend += [v for v in gate.scan_file(full, rel) if v[0] == "model-backend-env"]
    assert backend == [], f"Rule 1b flagged: {[(r, n, l) for _, n, r, l in backend]}"
