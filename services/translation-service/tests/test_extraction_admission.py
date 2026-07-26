"""D-EXTRACTION-ADMISSION-CONTROL — per-user concurrent extraction-job cap.

P5 fair-scheduling is translation-chapter-only and places NO bound on extraction job fan-out,
so the shared create-core enforces a per-user cap on pending|running jobs. Unit-tests the guard
directly (the core, mocking its pre-guard steps) — the reject path is the new behavior; the
under-cap path is the default-safe case (a fresh user's count is 0)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import extraction as ext
from app.grant_client import GrantLevel


def _projection_cm(payload):
    """An httpx.AsyncClient() context manager whose .get() returns a 200 projection."""
    resp = MagicMock()
    resp.status_code = 200
    resp.is_success = True
    resp.json = MagicMock(return_value=payload)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_preguard(monkeypatch):
    """Stub everything the core does BEFORE the admission guard (book projection, profile,
    model context, estimate, grant resolve) so a test reaches the guard deterministically."""
    monkeypatch.setattr(ext, "fetch_extraction_profile",
                        AsyncMock(return_value={"kinds": [{"code": "character",
                                                           "attributes": [{"code": "name"}]}]}))
    monkeypatch.setattr(ext, "get_model_context_window", AsyncMock(return_value=32000))
    monkeypatch.setattr(ext, "estimate_extraction_cost", lambda *a, **k: {"llm_calls": 1})
    monkeypatch.setattr(ext, "resolve_model_name", AsyncMock(return_value="m"))
    gc = MagicMock()
    gc.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)
    monkeypatch.setattr(ext, "get_grant_client", lambda: gc)
    monkeypatch.setattr(ext.httpx, "AsyncClient", lambda **k: _projection_cm({"original_language": "en"}))


@pytest.mark.asyncio
async def test_admission_cap_rejects_at_limit(monkeypatch):
    monkeypatch.setattr(ext.app_settings, "extraction_max_concurrent_jobs_per_user", 2)
    _mock_preguard(monkeypatch)
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=2)  # already AT the cap (2 pending|running)
    payload = ext.CreateExtractionJobPayload(
        chapter_ids=[uuid4()], extraction_profile={"character": {"name": "fill"}}, model_ref=uuid4())
    with pytest.raises(HTTPException) as ei:
        await ext._create_extraction_job_core(db, uuid4(), uuid4(), payload)
    assert ei.value.status_code == 429
    assert ei.value.detail["code"] == "EXTRACT_TOO_MANY_JOBS"


@pytest.mark.asyncio
async def test_admission_cap_disabled_skips_the_count(monkeypatch):
    # cap=0 ⇒ disabled: the guard is skipped entirely, so the count query is never issued
    # (and a huge active count cannot reject). We stop the run right after the guard by making
    # the INSERT tx blow up, and assert it got PAST the guard (no 429) without counting.
    monkeypatch.setattr(ext.app_settings, "extraction_max_concurrent_jobs_per_user", 0)
    _mock_preguard(monkeypatch)
    db = AsyncMock()
    db.fetchval = AsyncMock(side_effect=AssertionError("count query must not run when cap=0"))
    db.acquire = MagicMock(side_effect=RuntimeError("stop-after-guard"))
    payload = ext.CreateExtractionJobPayload(
        chapter_ids=[uuid4()], extraction_profile={"character": {"name": "fill"}}, model_ref=uuid4())
    with pytest.raises(RuntimeError, match="stop-after-guard"):  # reached the INSERT, not a 429
        await ext._create_extraction_job_core(db, uuid4(), uuid4(), payload)
