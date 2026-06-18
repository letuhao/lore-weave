"""Compose HTTP handler — slice 1 (spine + mode D draft, mode A gap).

Exercises POST .../compose via TestClient + dependency overrides (NOT the store
directly). The store + save_job_request + redis producer are fakes (mirroring
test_auto_enrich_api), so no live stack. Asserts the handler's branch behaviour
read from app/api/compose.py:

  * draft (existing) → 202 + technique='compose_draft' + the request persists
    input_source/seed_text/expand_mode + the target;
  * draft (NEW entity) → target_ref persisted as None (anchor minted at promote);
  * draft without draft_text / without target / bad expand_mode → 400;
  * gap → 202 with the chosen technique + targets; compose_draft via gap → 400;
  * future sources (context/files/intent) → 400; unknown source → 400;
  * no auth → 401.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import compose as compose_api
from app.db.book_profile import NEUTRAL_PROFILE
from app.deps import get_db

OWNER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"


class _RecordingProducer:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def xadd(self, stream, fields, maxlen=None):
        self.calls.append((stream, fields))
        return "1-0"

    async def aclose(self):
        self.closed = True


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(compose_api.router)
    app.dependency_overrides[get_db] = lambda: object()
    return app


def _bearer(sub: str = OWNER) -> str:
    return pyjwt.encode({"sub": sub}, "x", algorithm="HS256")


def _patch_store(monkeypatch, *, jid, created, saved, producer):
    class _FakeStore:
        def __init__(self, pool):
            ...

        async def create_job(self, **kw):
            created.update(kw)
            return str(jid)

    async def _fake_save(*, pool, job_id, request):
        saved["job_id"] = job_id
        saved["request"] = request

    monkeypatch.setattr(compose_api, "PgProposalStore", _FakeStore)
    monkeypatch.setattr(compose_api, "save_job_request", _fake_save)
    monkeypatch.setattr(compose_api, "make_redis_producer", lambda url: producer)


def _post(body: dict, *, project=None, auth=True):
    project = project or uuid4()
    headers = {"Authorization": f"Bearer {_bearer()}"} if auth else {}
    return TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/compose", json=body, headers=headers
    )


def _base(**over) -> dict:
    body = {
        "book_id": str(uuid4()),
        "input_source": "draft",
        "embedding_model_ref": str(uuid4()),
        "generation_model_ref": str(uuid4()),
        "draft_text": "碧遊宮乃通天教主道場。",
        "expand_mode": "rewrite",
        "target": {"mode": "existing", "canonical_name": "碧遊宮",
                   "entity_kind": "location", "target_ref": "loc:biyou"},
    }
    body.update(over)
    return body


# ── mode D — draft (existing) ────────────────────────────────────────────────
def test_draft_existing_202_persists_seed_and_mode(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = _post(_base(expand_mode="add_only"))
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == str(jid)
    assert body["input_source"] == "draft"
    assert body["technique"] == "compose_draft"
    assert body["enqueued"] is True

    # job row carries the compose_draft technique + the target's kind.
    assert created["technique"] == "compose_draft"
    assert created["entity_kind"] == "location"
    # persisted request carries the compose-specific fields the worker re-drives.
    req = saved["request"]
    assert req["input_source"] == "draft"
    assert req["seed_text"] == "碧遊宮乃通天教主道場。"
    assert req["expand_mode"] == "add_only"
    assert req["technique"] == "compose_draft"
    assert len(req["targets"]) == 1
    assert req["targets"][0]["canonical_name"] == "碧遊宮"
    assert req["targets"][0]["target_ref"] == "loc:biyou"
    assert len(prod.calls) == 1


def test_draft_rewrite_clears_present_dimensions(monkeypatch):
    # /review-impl MED: rewrite expands ALL dims — present_dimensions is cleared so
    # _gap_from_target never drops a well-covered existing entity to a silent no-op.
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = _post(_base(
        expand_mode="rewrite",
        target={"mode": "existing", "canonical_name": "碧遊宮", "entity_kind": "location",
                "target_ref": "loc:biyou",
                "present_dimensions": ["历史", "地理", "文化", "features", "inhabitants"]},
    ))
    assert resp.status_code == 202, resp.text
    # present cleared → all dims become "missing" → all get rewritten (no silent no-op)
    assert saved["request"]["targets"][0]["present_dimensions"] == []
    assert saved["request"]["targets"][0]["target_ref"] == "loc:biyou"  # still existing


def test_draft_add_only_keeps_explicit_present_dimensions(monkeypatch):
    # add_only with FE-supplied present is respected verbatim (no glossary derivation).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = _post(_base(
        expand_mode="add_only",
        target={"mode": "existing", "canonical_name": "碧遊宮", "entity_kind": "location",
                "target_ref": "loc:biyou", "present_dimensions": ["历史"]},
    ))
    assert resp.status_code == 202, resp.text
    assert saved["request"]["targets"][0]["present_dimensions"] == ["历史"]


# ── /review-impl #1 — add_only derives the existing entity's present dims server-side ──
def _patch_coverage(monkeypatch, *, rows, raises=False):
    """Fake the glossary coverage read the add_only path uses to derive present dims."""
    class _FakeGlossary:
        def __init__(self, **_kw):
            ...

        async def list_enrichment_coverage(self, *, book_id, limit):
            if raises:
                raise RuntimeError("glossary down")
            return rows

        async def aclose(self):
            ...

    async def _neutral(_pool, _book_id):
        return NEUTRAL_PROFILE

    monkeypatch.setattr(compose_api, "GlossaryClient", _FakeGlossary)
    monkeypatch.setattr(compose_api, "get_book_profile", _neutral)


def _cov_row(name: str, dims: list[str]):
    return SimpleNamespace(canonical_name=name, kind="location", mention_count=5, dimensions=dims)


def test_draft_add_only_existing_derives_present_from_glossary(monkeypatch):
    # The FE composer sends no present_dimensions; the BE derives the entity's covered
    # dims so add_only ADDS only the genuinely-missing ones (not regenerate all).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    # NEUTRAL profile → zh-default location labels; 历史/地理 map to ids history/geography.
    _patch_coverage(monkeypatch, rows=[_cov_row("碧遊宮", ["历史", "地理"])])

    resp = _post(_base(
        expand_mode="add_only",
        target={"mode": "existing", "canonical_name": "碧遊宮", "entity_kind": "location",
                "target_ref": "loc:biyou"},  # NO present_dimensions from the FE
    ))
    assert resp.status_code == 202, resp.text
    assert saved["request"]["targets"][0]["present_dimensions"] == ["history", "geography"]


def test_draft_add_only_glossary_error_degrades_to_empty(monkeypatch):
    # A glossary failure must NOT fail the compose — degrade to present=[] (generate all).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_coverage(monkeypatch, rows=[], raises=True)

    resp = _post(_base(
        expand_mode="add_only",
        target={"mode": "existing", "canonical_name": "碧遊宮", "entity_kind": "location",
                "target_ref": "loc:biyou"},
    ))
    assert resp.status_code == 202, resp.text
    assert saved["request"]["targets"][0]["present_dimensions"] == []


def test_draft_rewrite_does_not_call_glossary(monkeypatch):
    # rewrite clears present (expand all) WITHOUT a coverage call — the fake raises if hit.
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_coverage(monkeypatch, rows=[], raises=True)  # would blow up if called

    resp = _post(_base(
        expand_mode="rewrite",
        target={"mode": "existing", "canonical_name": "碧遊宮", "entity_kind": "location",
                "target_ref": "loc:biyou"},
    ))
    assert resp.status_code == 202, resp.text
    assert saved["request"]["targets"][0]["present_dimensions"] == []


def test_draft_bad_target_mode_422(monkeypatch):
    # /review-impl LOW: a typo'd target.mode is rejected (422) — never silently
    # mis-routed onto the existing path.
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post(_base(
        target={"mode": "New", "canonical_name": "新天地", "entity_kind": "generic"},
    ))
    assert resp.status_code == 422
    assert created == {} and prod.calls == []


def test_draft_new_entity_target_ref_none(monkeypatch):
    # mode='new' → target_ref persisted None (anchor minted at PROMOTE, H0-clean).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = _post(_base(
        target={"mode": "new", "canonical_name": "新天地", "entity_kind": "generic"},
    ))
    assert resp.status_code == 202, resp.text
    assert created["entity_kind"] == "generic"
    t = saved["request"]["targets"][0]
    assert t["canonical_name"] == "新天地"
    assert t["target_ref"] is None       # NEW → no glossary write at compose time
    assert t["present_dimensions"] == []  # all dims missing → generate all


def test_draft_without_embedding_model_ref_202(monkeypatch):
    # D-COMPOSE-S1-EMBED-REF: mode D needs no embed model (no retrieval) → 202, and
    # the persisted request carries embedding_model_ref=None (the worker ignores it).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    body = _base()
    body.pop("embedding_model_ref")
    resp = _post(body)
    assert resp.status_code == 202, resp.text
    assert saved["request"]["embedding_model_ref"] is None


def test_draft_too_large_413(monkeypatch):
    # D-COMPOSE-S1-DRAFT-CAP: an oversized draft is refused (use a file upload).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post(_base(draft_text="字" * 50_001))
    assert resp.status_code == 413
    assert created == {} and prod.calls == []


def test_gap_without_embedding_model_ref_400(monkeypatch):
    # The gap path keeps the auto-enrich contract — an embed model is required.
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post({
        "book_id": str(uuid4()),
        "input_source": "gap",
        "generation_model_ref": str(uuid4()),
        "technique": "retrieval",
        "gap_targets": [{"mode": "existing", "canonical_name": "玉虛宮"}],
    })
    assert resp.status_code == 400
    assert created == {} and prod.calls == []


def test_draft_missing_draft_text_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post(_base(draft_text="   "))
    assert resp.status_code == 400
    assert created == {} and prod.calls == []


def test_draft_missing_target_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    body = _base()
    body.pop("target")
    resp = _post(body)
    assert resp.status_code == 400


def test_draft_bad_expand_mode_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post(_base(expand_mode="obliterate"))
    assert resp.status_code == 400


# ── mode A — gap ─────────────────────────────────────────────────────────────
def test_gap_202_with_targets(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = _post({
        "book_id": str(uuid4()),
        "input_source": "gap",
        "embedding_model_ref": str(uuid4()),
        "generation_model_ref": str(uuid4()),
        "technique": "retrieval",
        "gap_targets": [
            {"mode": "existing", "canonical_name": "玉虛宮", "entity_kind": "location",
             "target_ref": "loc:yuxu", "present_dimensions": ["历史"]},
        ],
    })
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["technique"] == "retrieval"
    assert body["enqueued_targets"] == 1
    req = saved["request"]
    assert req["input_source"] == "gap"
    assert req["targets"][0]["present_dimensions"] == ["历史"]
    assert "seed_text" not in req  # gap is not a draft


def test_gap_with_compose_draft_technique_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post({
        "book_id": str(uuid4()),
        "input_source": "gap",
        "embedding_model_ref": str(uuid4()),
        "generation_model_ref": str(uuid4()),
        "technique": "compose_draft",
        "gap_targets": [{"mode": "existing", "canonical_name": "玉虛宮"}],
    })
    assert resp.status_code == 400


# ── mode C — paste-context ───────────────────────────────────────────────────
def _patch_ingest(monkeypatch, *, recorder, raises=None):
    """Fake the synchronous corpus ingest the context branch performs so the handler
    branch (validation + request shape) is tested without a live embed/store."""
    async def _fake_ingest(*, pool, principal, project_id, book_id, text,
                           embedding_model_ref, store_license, persist=False):
        recorder["called"] = True
        recorder["text"] = text
        recorder["store_license"] = store_license
        recorder["persist"] = persist
        if raises is not None:
            raise raises
        return ["corpus-ctx-1"]

    monkeypatch.setattr(compose_api, "_ingest_context", _fake_ingest)


def _ctx_base(**over) -> dict:
    body = {
        "book_id": str(uuid4()),
        "input_source": "context",
        "embedding_model_ref": str(uuid4()),
        "generation_model_ref": str(uuid4()),
        "context_text": "蓬萊乃東海仙山，仙人所居。",
        "context_license": "public_domain",
        # present supplied → skips the glossary coverage derivation (tested separately).
        "target": {"mode": "existing", "canonical_name": "蓬萊", "entity_kind": "location",
                   "target_ref": "loc:penglai", "present_dimensions": ["历史"]},
    }
    body.update(over)
    return body


def test_context_202_ingests_and_persists(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)

    resp = _post(_ctx_base())
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["input_source"] == "context"
    assert body["technique"] == "retrieval"  # default for context
    assert rec["called"] is True
    assert rec["text"] == "蓬萊乃東海仙山，仙人所居。"
    assert rec["store_license"] == "public_domain"
    req = saved["request"]
    assert req["input_source"] == "context"
    assert req["context_corpus_ids"] == ["corpus-ctx-1"]
    assert req["context_license"] == "public_domain"
    assert req["targets"][0]["present_dimensions"] == ["历史"]  # supplied present preserved
    assert "seed_text" not in req  # context is not a draft
    assert len(prod.calls) == 1


def test_context_persist_corpus_threads_persist_flag(monkeypatch):
    # #7 save-to-corpus: persist_corpus=true → _ingest_context(persist=True) so the
    # corpus is kept (untagged) instead of ephemeral; default is ephemeral (persist=False).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)

    assert _post(_ctx_base(persist_corpus=True)).status_code == 202
    assert rec["persist"] is True

    rec2: dict = {}
    _patch_ingest(monkeypatch, recorder=rec2)
    assert _post(_ctx_base()).status_code == 202  # omitted → default ephemeral
    assert rec2["persist"] is False


def test_context_requested_dimensions_enriches_only_chosen(monkeypatch):
    # #1 dimension picker: requested_dimensions → present = the kind's full set MINUS
    # the requested ids, so the worker's derived missing = exactly the chosen dims.
    # Overrides the coverage-derivation entirely (coverage fake raises if hit).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_coverage(monkeypatch, rows=[], raises=True)  # NEUTRAL profile; coverage must NOT be hit
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)

    resp = _post(_ctx_base(
        target={"mode": "existing", "canonical_name": "蓬萊", "entity_kind": "location",
                "target_ref": "loc:penglai", "requested_dimensions": ["history"]},
    ))
    assert resp.status_code == 202, resp.text
    present = saved["request"]["targets"][0]["present_dimensions"]
    assert "history" not in present                      # the chosen dim is enriched (missing)
    assert "geography" in present and "features" in present  # the rest marked present (skipped)


def test_context_owned_maps_to_licensed(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    resp = _post(_ctx_base(context_license="owned"))
    assert resp.status_code == 202, resp.text
    # 'owned' is stored as 'licensed' (author-owned ⇒ re-cook-admissible).
    assert rec["store_license"] == "licensed"
    assert saved["request"]["context_license"] == "licensed"


def test_context_public_domain_hyphen_accepted(monkeypatch):
    # /review-impl #3: parity with licensing.py — the hyphen spelling is admissible.
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    resp = _post(_ctx_base(context_license="public-domain"))
    assert resp.status_code == 202, resp.text
    assert rec["store_license"] == "public_domain"


def test_context_persists_embedding_model_ref(monkeypatch):
    # /review-impl #4 (grounding-alignment invariant): the retrieval query is
    # re-embedded with this model_ref, so it MUST round-trip into the request — else
    # the query vectors wouldn't match the ingested corpus vectors and grounding
    # would silently fail.
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_ingest(monkeypatch, recorder={})
    embed = str(uuid4())
    resp = _post(_ctx_base(embedding_model_ref=embed))
    assert resp.status_code == 202, resp.text
    assert saved["request"]["embedding_model_ref"] == embed


def test_context_recook_technique_202(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_ingest(monkeypatch, recorder={})
    resp = _post(_ctx_base(technique="recook"))
    assert resp.status_code == 202, resp.text
    assert resp.json()["technique"] == "recook"


def test_context_new_entity_target_ref_none(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_ingest(monkeypatch, recorder={})
    resp = _post(_ctx_base(
        target={"mode": "new", "canonical_name": "新仙山", "entity_kind": "generic"},
    ))
    assert resp.status_code == 202, resp.text
    t = saved["request"]["targets"][0]
    assert t["target_ref"] is None and t["present_dimensions"] == []


@pytest.mark.parametrize("lic", ["copyrighted", "banana", ""])
def test_context_inadmissible_license_403(monkeypatch, lic):
    # default-deny: copyrighted / unrecognised / blank → 403, no ingest, no job.
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    resp = _post(_ctx_base(context_license=lic))
    assert resp.status_code == 403, resp.text
    assert rec == {} and created == {} and prod.calls == []


def test_context_too_large_413(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    resp = _post(_ctx_base(context_text="字" * 50_001))
    assert resp.status_code == 413
    assert rec == {} and created == {} and prod.calls == []


def test_context_missing_embed_400(monkeypatch):
    # context embeds the paste → embedding_model_ref required (unlike draft).
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    body = _ctx_base()
    body.pop("embedding_model_ref")
    resp = _post(body)
    assert resp.status_code == 400
    assert rec == {} and created == {}


def test_context_missing_text_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_ingest(monkeypatch, recorder={})
    resp = _post(_ctx_base(context_text="   "))
    assert resp.status_code == 400


def test_context_missing_target_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_ingest(monkeypatch, recorder={})
    body = _ctx_base()
    body.pop("target")
    resp = _post(body)
    assert resp.status_code == 400


def test_context_compose_draft_technique_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    resp = _post(_ctx_base(technique="compose_draft"))
    assert resp.status_code == 400
    assert rec == {}  # rejected before ingest


# ── mode F — attach files ────────────────────────────────────────────────────
def _patch_fetch_upload(monkeypatch, *, rows: dict):
    """Fake compose_api.fetch_upload: upload_id str → record dict (or None)."""
    async def _fake(pool, user_id, uid):
        return rows.get(str(uid))
    monkeypatch.setattr(compose_api, "fetch_upload", _fake)


def _up(status="ready", text="蓬萊乃東海仙山。", lic="public_domain"):
    return {"status": status, "extracted_text": text, "license_asserted": lic}


def _files_base(upload_ids, **over) -> dict:
    body = {
        "book_id": str(uuid4()),
        "input_source": "files",
        "embedding_model_ref": str(uuid4()),
        "generation_model_ref": str(uuid4()),
        "upload_ids": upload_ids,
        "target": {"mode": "new", "canonical_name": "新仙山", "entity_kind": "location"},
    }
    body.update(over)
    return body


def test_files_persist_corpus_threads_persist_flag(monkeypatch):
    # #7: files mode threads persist_corpus through to _ingest_context like context.
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    u1 = str(uuid4())
    _patch_fetch_upload(monkeypatch, rows={u1: _up()})
    assert _post(_files_base([u1], persist_corpus=True)).status_code == 202
    assert rec["persist"] is True


def test_files_202_ingests_ready_uploads(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    u1, u2 = str(uuid4()), str(uuid4())
    _patch_fetch_upload(monkeypatch, rows={u1: _up(), u2: _up(lic="licensed")})

    resp = _post(_files_base([u1, u2]))
    assert resp.status_code == 202, resp.text
    assert resp.json()["technique"] == "retrieval"
    assert rec["called"] is True
    req = saved["request"]
    assert req["input_source"] == "files"
    assert req["context_corpus_ids"] == ["corpus-ctx-1", "corpus-ctx-1"]  # one per upload
    assert req["upload_ids"] == [u1, u2]


def test_files_not_ready_409(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_ingest(monkeypatch, recorder={})
    u1 = str(uuid4())
    _patch_fetch_upload(monkeypatch, rows={u1: _up(status="processing")})
    resp = _post(_files_base([u1]))
    assert resp.status_code == 409
    assert created == {}


def test_files_not_found_404(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    _patch_ingest(monkeypatch, recorder={})
    _patch_fetch_upload(monkeypatch, rows={})  # nothing → 404
    resp = _post(_files_base([str(uuid4())]))
    assert resp.status_code == 404


def test_files_missing_upload_ids_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post(_files_base([]))  # empty list
    assert resp.status_code == 400


def test_files_missing_embed_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    body = _files_base([str(uuid4())])
    body.pop("embedding_model_ref")
    resp = _post(body)
    assert resp.status_code == 400


def test_files_all_empty_text_422(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    rec: dict = {}
    _patch_ingest(monkeypatch, recorder=rec)
    u1 = str(uuid4())
    _patch_fetch_upload(monkeypatch, rows={u1: _up(text="   ")})  # ready but no text
    resp = _post(_files_base([u1]))
    assert resp.status_code == 422
    assert rec == {} and created == {}  # nothing ingested, no job


# ── mode B — intent (the compose branch: a CONFIRMED target → fabrication/retrieval) ──
def _intent_base(**over) -> dict:
    body = {
        "book_id": str(uuid4()),
        "input_source": "intent",
        "generation_model_ref": str(uuid4()),
        "target": {"mode": "new", "canonical_name": "姜子牙", "entity_kind": "character"},
    }
    body.update(over)
    return body


def test_intent_202_fabrication_default(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post(_intent_base(intent_text="the kings advisor"))  # no technique → fabrication
    assert resp.status_code == 202, resp.text
    assert resp.json()["technique"] == "fabrication"
    req = saved["request"]
    assert req["input_source"] == "intent" and req["intent_resolved"] is True
    # review-impl #1: the original intent is persisted for the audit trail.
    assert req["intent_text"] == "the kings advisor"


def test_intent_missing_target_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    body = _intent_base()
    body.pop("target")
    assert _post(body).status_code == 400


def test_intent_retrieval_without_embed_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    # retrieval grounds on a corpus → embed required; fabrication wouldn't be.
    assert _post(_intent_base(technique="retrieval")).status_code == 400


def test_intent_compose_draft_technique_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    assert _post(_intent_base(technique="compose_draft")).status_code == 400


# ── mode B — resolve-intent endpoint (Phase 3 M2 — async) ─────────────────────
# The endpoint now creates a 'pending' compose task + enqueues a resume-stream
# trigger → 202 + task_id; the resolver LLM call runs in the worker
# (compute_intent_resolve, covered in test_compose_task.py).

def _patch_intent_task(monkeypatch, *, task_id="22222222-2222-7222-8222-222222222222",
                       enqueued=True):
    created: dict = {}

    async def _create(pool, *, kind, user_id, project_id, book_id, request):
        created.update(kind=kind, user_id=user_id, project_id=project_id,
                       book_id=book_id, request=request)
        return task_id

    async def _enqueue(*, task_id, kind, user_id, project_id):
        created["enqueued_kind"] = kind
        return enqueued

    monkeypatch.setattr(compose_api, "create_compose_task", _create)
    monkeypatch.setattr(compose_api, "enqueue_compose_task", _enqueue)
    return created


def _post_resolve(body: dict, *, project=None, auth=True):
    project = project or uuid4()
    headers = {"Authorization": f"Bearer {_bearer()}"} if auth else {}
    return TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/compose/resolve-intent", json=body, headers=headers
    )


def test_resolve_intent_202_creates_task(monkeypatch):
    created = _patch_intent_task(monkeypatch)
    book, proj = uuid4(), uuid4()
    r = _post_resolve(
        {"book_id": str(book), "intent_text": "the king's advisor",
         "generation_model_ref": str(uuid4())},
        project=proj,
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["task_id"] == "22222222-2222-7222-8222-222222222222"
    assert body["status"] == "pending"
    assert created["kind"] == "intent_resolve"
    assert created["project_id"] == str(proj)
    assert created["book_id"] == str(book)
    assert created["request"]["intent_text"] == "the king's advisor"
    assert created["enqueued_kind"] == "intent_resolve"


def test_resolve_intent_requires_auth():
    assert _post_resolve({"book_id": str(uuid4()), "intent_text": "x",
                          "generation_model_ref": str(uuid4())}, auth=False).status_code == 401


# ── unknown source + auth ─────────────────────────────────────────────────────


def test_unknown_source_400(monkeypatch):
    jid = uuid4()
    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)
    resp = _post(_base(input_source="telepathy"))
    assert resp.status_code == 400


def test_compose_requires_auth():
    resp = _post(_base(), auth=False)
    assert resp.status_code == 401
