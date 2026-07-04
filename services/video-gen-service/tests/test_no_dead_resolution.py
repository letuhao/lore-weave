"""Phase 5e-α regression-locks: ensure the legacy direct-credential-resolve
path stays removed from app/routers/generate.py.

Mirrors chat-service's `test_voice_no_dead_resolution.py` pattern. Source-
grep approach (vs runtime mock) because the migration deletes the
code paths entirely — runtime tests can't observe absent code.
"""

from __future__ import annotations

from pathlib import Path

GENERATE_PY = (
    Path(__file__).resolve().parent.parent / "app" / "routers" / "generate.py"
)


def _source() -> str:
    return GENERATE_PY.read_text(encoding="utf-8")


def test_internal_credentials_endpoint_not_called():
    """The legacy `/internal/credentials/...` direct-call path was
    deleted in Phase 5e-α. Re-adding it would bypass the unified
    gateway and re-introduce the broken singular-path bug from 5d.
    """
    src = _source()
    assert "/internal/credentials" not in src, (
        "app/routers/generate.py references /internal/credentials — "
        "Phase 5e-α moved credential resolution into the gateway via "
        "loreweave_llm.Client. Re-introducing this call bypasses the "
        "unified gateway invariant. Remove the call or update this "
        "regression-lock with rationale."
    )


def test_provider_registry_url_legacy_env_not_referenced():
    """The legacy `PROVIDER_REGISTRY_URL` env var (used only by the
    deleted `resolve_credentials` function) was dropped in 5e-α per
    /review-impl(DESIGN) MED#2. The SDK uses `provider_registry_internal_url`
    via Settings; this env name should NOT appear in router code under
    any access pattern.

    /review-impl(QC) LOW#3 — strengthened from the original 2-form check
    to catch ALL idioms (os.getenv / os.environ / os.environ.get /
    `from os import getenv` / settings.provider_registry_url) by simply
    asserting the quoted env-name string literal is absent. The new
    `PROVIDER_REGISTRY_INTERNAL_URL` env contains `PROVIDER_REGISTRY_URL`
    as substring, so we look for the env name in QUOTED form: `"PROVIDER_REGISTRY_URL"`
    with the closing-quote that distinguishes it from
    `"PROVIDER_REGISTRY_INTERNAL_URL"`.
    """
    src = _source()
    # Match the quoted env name with closing quote — won't false-positive
    # on PROVIDER_REGISTRY_INTERNAL_URL because that has _INTERNAL_URL"
    # after the substring.
    assert '"PROVIDER_REGISTRY_URL"' not in src, (
        "app/routers/generate.py references the legacy PROVIDER_REGISTRY_URL "
        "env var (quoted string detected). Phase 5e-α removed this in favor "
        "of settings.provider_registry_internal_url. Re-introducing reads "
        "of the legacy var bypasses the unified gateway abstraction. "
        "Remove the reference or update this regression-lock with rationale."
    )
    # Also catch raw settings access if someone re-adds the field to config.py.
    assert "settings.provider_registry_url" not in src, (
        "app/routers/generate.py reads settings.provider_registry_url "
        "(legacy non-internal Settings field). The 5e-α config.py "
        "intentionally exposes only provider_registry_internal_url; "
        "re-adding the legacy field is a drift signal."
    )


def test_loreweave_llm_sdk_imported():
    """Positive lock: the SDK MUST be imported in generate.py. If a
    future refactor drops the import (e.g., back to direct httpx),
    this test fails fast.
    """
    src = _source()
    assert "from loreweave_llm import" in src, (
        "app/routers/generate.py must import from loreweave_llm — "
        "Phase 5e-α migrated to the SDK."
    )


def test_client_referenced_in_route():
    """Positive lock: `Client(` construction MUST exist in the route.
    Catches a regression where someone imports the SDK but reverts to
    the direct-httpx path.
    """
    src = _source()
    assert "Client(" in src, (
        "app/routers/generate.py must construct a loreweave_llm.Client — "
        "Phase 5e-α SDK-based migration."
    )


# ──────────────────────────────────────────────────────────────────────
# Phase 5f grep-locks
# ──────────────────────────────────────────────────────────────────────


def test_models_endpoint_removed():
    """G1: the dead `/models` endpoint was removed. It had zero FE
    callers and always returned an empty list. Re-adding it (with the
    old `ModelsResponse(models=[])` wrong-kwarg bug) is a drift signal.
    """
    src = _source()
    # Match the quoted route literal `/models` (either quote style) —
    # NOT a bare substring, which would false-positive on prose
    # mentioning the removed route.
    assert '"/models"' not in src and "'/models'" not in src, (
        "app/routers/generate.py declares a /models route — Phase 5f "
        "G1 removed the dead endpoint. Remove it again or update this lock."
    )
    assert "def list_models" not in src, (
        "app/routers/generate.py defines list_models — Phase 5f G1 "
        "removed it."
    )


def test_jwt_decode_verifies_signature():
    """G3: the incoming JWT MUST be signature-verified, not blind-decoded.
    Positive lock: the shared `verify_access_token` verifier (P3 SDK-first —
    HS256-pinned, `exp` required, `sub`→UUID; replaces the inline `jwt.decode`).
    Negative locks: the old unverified `urlsafe_b64decode` path is gone, AND the
    inline `jwt.decode(` was removed in favor of the shared SDK verifier.
    """
    src = _source()
    assert "verify_access_token(" in src, (
        "app/routers/generate.py must call the shared verify_access_token() — "
        "P3 routed JWT verification through the loreweave_authn SDK (still "
        "signature-verifying + HS256-pinned)."
    )
    assert "jwt.decode(" not in src, (
        "app/routers/generate.py hand-rolls jwt.decode() — P3 (SDK-first) "
        "replaced it with the shared loreweave_authn verify_access_token()."
    )
    assert "urlsafe_b64decode" not in src, (
        "app/routers/generate.py uses urlsafe_b64decode — Phase 5f G3 "
        "replaced the unverified base64 payload decode with a real verifier. "
        "Re-introducing it bypasses signature verification."
    )
