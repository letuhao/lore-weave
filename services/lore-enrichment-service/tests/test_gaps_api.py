"""D1 — gap auto-detection: coverage-builder unit + detect-gaps endpoint tests.

NO live stack: the glossary coverage read is respx-mocked; the engine + builder
are pure. Proves the C7 engine is now wired to a production path (QC F-C7-1).
"""

from __future__ import annotations

from uuid import uuid4

import jwt as pyjwt
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import gaps as gaps_api
from app.api.gaps import coverages_from_rows
from app.clients.glossary import EntityCoverageRow
from app.config import settings
from app.deps import get_db
from app.db.book_profile import NEUTRAL_PROFILE
from app.gaps.model import Dimension, EntityKind

OWNER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"


@pytest.fixture(autouse=True)
def _stub_book_profile(monkeypatch):
    """de-bias C1: detect resolves the book profile via the DB pool; the stub pool
    can't, so return NEUTRAL (detection/ranking is profile-agnostic here)."""
    async def _neutral(_pool, _book_id):
        return NEUTRAL_PROFILE
    monkeypatch.setattr(gaps_api, "get_book_profile", _neutral)


def _row(name, kind="location", mentions=0, dims=()):
    return EntityCoverageRow(entity_id="e", canonical_name=name, kind=kind,
                             mention_count=mentions, dimensions=tuple(dims))


def test_coverages_from_rows_en_profile_round_trip():
    # de-bias C1 (#5): with an English book profile, detect localizes the dimension
    # table to en, so an entity whose stored dim is the EN label ("Appearance")
    # maps back to the stable id — the SAME consistency generation/storage use.
    from app.db.book_profile import BookProfile

    en = BookProfile(language="en")
    rows = [_row("Jiang Ziya", kind="character", dims=("Appearance", "Abilities"))]
    covs = coverages_from_rows(rows, en)
    assert len(covs) == 1
    assert set(covs[0].present_dimensions) == {"appearance", "abilities"}


def test_coverages_from_rows_is_multi_kind_and_id_or_label_tolerant():
    # De-bias C1 (KB3): every kind is modeled — a CHARACTER is NOT skipped, an
    # unknown kind falls back to GENERIC. Present dims map from either the stable
    # id (KB-A) or the legacy default label; unknown dims drop (no drift). Only an
    # empty canonical_name skips.
    rows = [
        _row("蓬萊", mentions=3, dims=("历史", "features")),   # location, labels
        _row("", mentions=0),                                  # empty name → skip
        _row("孫悟空", kind="character", dims=("appearance",)), # character, stable id
        _row("某物", kind="bogus-kind", dims=("description",)), # unknown kind → GENERIC
        _row("X", dims=("不存在的维度",)),                      # unknown dim dropped
    ]
    covs = coverages_from_rows(rows)
    assert len(covs) == 4  # 蓬萊 + 孫悟空 + 某物 + X (only the empty-name row skips)
    by_name = {c.canonical_name: c for c in covs}
    assert by_name["蓬萊"].entity_kind == EntityKind.LOCATION
    # label 历史 + id-ish 'features' both resolve to stable ids
    assert set(by_name["蓬萊"].present_dimensions) == {Dimension.HISTORY, Dimension.FEATURES}
    assert by_name["孫悟空"].entity_kind == "character"
    assert set(by_name["孫悟空"].present_dimensions) == {"appearance"}
    assert by_name["某物"].entity_kind == "bogus-kind"  # kept; GENERIC dim table
    assert set(by_name["某物"].present_dimensions) == {"description"}
    assert by_name["X"].present_dimensions == ()  # unknown label dropped


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(gaps_api.router)
    # auto-enrich depends on get_db (detect-gaps doesn't); a stub keeps wiring valid
    # — the store + save_job_request are monkeypatched in the test that uses it.
    app.dependency_overrides[get_db] = lambda: object()
    return app


@pytest.mark.asyncio
@respx.mock
async def test_detect_gaps_endpoint_returns_ranked_gaps():
    book, project = uuid4(), uuid4()
    respx.get(
        f"{settings.glossary_service_url}/internal/books/{book}/enrichment-coverage"
    ).respond(200, json={"entities": [
        {"entity_id": "e1", "canonical_name": "蓬萊", "kind": "location",
         "mention_count": 3, "dimensions": ["历史"]},
        {"entity_id": "e2", "canonical_name": "玉虛宮", "kind": "location",
         "mention_count": 55, "dimensions": []},
    ]})
    bearer = pyjwt.encode({"sub": OWNER}, "x", algorithm="HS256")
    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/detect-gaps",
        json={"book_id": str(book)},
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entities_scanned"] == 2
    assert body["gap_count"] == 2  # both have missing dimensions
    # 玉虛宮 (55 mentions, all 5 dims missing) outranks 蓬萊 (3 mentions, 4 missing).
    assert body["gaps"][0]["canonical_name"] == "玉虛宮"
    assert body["gaps"][0]["rank"] == 1
    assert body["gaps"][0]["present_dimensions"] == []
    # 蓬萊's promoted 历史 maps to the Dimension enum value 'history' (present).
    penglai = next(g for g in body["gaps"] if g["canonical_name"] == "蓬萊")
    assert "history" in penglai["present_dimensions"]
    assert "history" not in penglai["missing_dimensions"]


@pytest.mark.asyncio
async def test_detect_gaps_requires_auth():
    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{uuid4()}/detect-gaps",
        json={"book_id": str(uuid4())},
    )
    assert resp.status_code == 401


# ── auto-enrich (D1 follow-up): detect → create job + persist request + enqueue ─

class _RecordingProducer:
    """Captures the enqueued resume/auto-enrich trigger."""
    def __init__(self):
        self.calls = []

    async def xadd(self, stream, fields, maxlen=None):
        self.calls.append((stream, fields))
        return "1-0"

    async def aclose(self):
        pass


@pytest.mark.asyncio
@respx.mock
async def test_auto_enrich_detects_creates_job_and_enqueues(monkeypatch):
    book, project, jid = uuid4(), uuid4(), uuid4()
    respx.get(
        f"{settings.glossary_service_url}/internal/books/{book}/enrichment-coverage"
    ).respond(200, json={"entities": [
        {"entity_id": "e1", "canonical_name": "玉虛宮", "kind": "location",
         "mention_count": 55, "dimensions": []},
        {"entity_id": "e2", "canonical_name": "蓬萊", "kind": "location",
         "mention_count": 3, "dimensions": ["历史"]},
    ]})

    from app.api import gaps as g
    created, saved, prod = {}, {}, _RecordingProducer()

    class _FakeStore:
        def __init__(self, pool): ...
        async def create_job(self, **kw):
            created.update(kw)
            return str(jid)

    async def _fake_save(*, pool, job_id, request):
        saved["job_id"], saved["request"] = job_id, request

    monkeypatch.setattr(g, "PgProposalStore", _FakeStore)
    monkeypatch.setattr(g, "save_job_request", _fake_save)
    monkeypatch.setattr(g, "make_redis_producer", lambda url: prod)

    bearer = pyjwt.encode({"sub": OWNER}, "x", algorithm="HS256")
    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/auto-enrich",
        json={"book_id": str(book), "embedding_model_ref": str(uuid4()),
              "generation_model_ref": str(uuid4()), "max_gaps": 1},
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["detected"] == 2 and body["enqueued_gaps"] == 1 and body["enqueued"] is True
    # top-N: only the highest-ranked gap (玉虛宮, 55 mentions) is enqueued as a target.
    assert len(saved["request"]["targets"]) == 1
    assert saved["request"]["targets"][0]["canonical_name"] == "玉虛宮"
    # the trigger was enqueued to the worker stream with the new job_id.
    assert prod.calls and prod.calls[0][1]["job_id"] == str(jid)


@pytest.mark.asyncio
async def test_auto_enrich_requires_auth():
    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{uuid4()}/auto-enrich",
        json={"book_id": str(uuid4()), "embedding_model_ref": str(uuid4()),
              "generation_model_ref": str(uuid4())},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
@respx.mock
async def test_detect_gaps_unextracted_book_signals_needs_extraction():
    # de-bias C2 T7: a book with NO extracted entities → needs_extraction=true (a
    # clear "extract first" signal), not a bare empty gap list.
    book, project = uuid4(), uuid4()
    respx.get(
        f"{settings.glossary_service_url}/internal/books/{book}/enrichment-coverage"
    ).respond(200, json={"entities": []})  # unextracted → no entities
    bearer = pyjwt.encode({"sub": OWNER}, "x", algorithm="HS256")
    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/detect-gaps",
        json={"book_id": str(book)},
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entities_scanned"] == 0
    assert body["gap_count"] == 0
    assert body["needs_extraction"] is True
