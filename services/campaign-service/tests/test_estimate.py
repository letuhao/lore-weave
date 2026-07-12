"""S5a — campaign cost/time estimate: pure heuristics + the route."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.config import settings
from app import estimate as est
from app.clients.book_client import ChapterRef
from app.clients.provider_registry_client import EstimateUnavailable
from tests.conftest import TEST_USER

BOOK = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TR = str(uuid4())
EX = str(uuid4())


# ── pure: source_tokens_for ───────────────────────────────────────────────

def test_source_tokens_uses_byte_size_and_fallback():
    # bytes_per_token=3, fallback_chars=3000 → fallback chapter ≈ 9000 bytes.
    # [9000 bytes, missing] → (9000 + 9000) / 3 = 6000 tokens.
    assert est.source_tokens_for([9000, 0], settings) == 6000


def test_source_tokens_empty():
    assert est.source_tokens_for([], settings) == 0


# ── pure: build_pricing_items ──────────────────────────────────────────────

def test_build_items_full_matrix_shapes():
    models = {
        est.ROLE_EXTRACTOR: ("user_model", EX),
        est.ROLE_EMBEDDING: ("user_model", str(uuid4())),
        est.ROLE_TRANSLATOR: ("user_model", TR),
        est.ROLE_VERIFIER: ("user_model", str(uuid4())),
        est.ROLE_EVAL_JUDGE: ("user_model", str(uuid4())),
        est.ROLE_RERANKER: ("user_model", str(uuid4())),
    }
    items, metas = est.build_pricing_items(
        source_tokens=1000, chapter_count=2, models=models, cfg=settings)
    labels = {i["label"] for i in items}
    # 5 priced stages (rerank is never token-priced).
    assert labels == {"extraction", "embedding", "translation", "verify", "eval"}
    emb = next(i for i in items if i["label"] == "embedding")
    assert emb["dimension"] == "input_only" and emb["output_tokens"] == 0
    tr = next(i for i in items if i["label"] == "translation")
    assert tr["dimension"] == "text"
    assert tr["output_tokens"] == 1500  # 1000 × 1.5 ratio
    ver = next(i for i in items if i["label"] == "verify")
    # verify reads source + candidate translation = 1000 + (1000×1.5) = 2500.
    assert ver["input_tokens"] == 2500
    assert any(m.stage == "rerank" and m.not_estimated_reason for m in metas)


def test_build_items_verifier_falls_back_to_translator():
    models = {est.ROLE_TRANSLATOR: ("user_model", TR)}  # no verifier
    items, _ = est.build_pricing_items(
        source_tokens=500, chapter_count=1, models=models, cfg=settings)
    ver = next(i for i in items if i["label"] == "verify")
    assert ver["model_ref"] == TR  # inherited the translator model


def test_build_items_skips_unset_roles():
    models = {est.ROLE_TRANSLATOR: ("user_model", TR)}
    items, metas = est.build_pricing_items(
        source_tokens=500, chapter_count=1, models=models, cfg=settings)
    labels = {i["label"] for i in items}
    # translation + verify(fallback) priced; extraction/embedding/eval unset.
    assert labels == {"translation", "verify"}
    skipped = {m.stage for m in metas if m.not_estimated_reason}
    assert {"extraction", "embedding", "eval", "rerank"} <= skipped


# ── pure: assemble_estimate ────────────────────────────────────────────────

def test_assemble_band_and_time():
    items, metas = est.build_pricing_items(
        source_tokens=1000, chapter_count=10,
        models={est.ROLE_TRANSLATOR: ("user_model", TR)}, cfg=settings)
    priced = [
        {"label": "translation", "status": "ok", "estimated_usd": 4.0,
         "provider_kind": "ollama", "is_local": True},
        {"label": "verify", "status": "ok", "estimated_usd": 2.0,
         "provider_kind": "openai", "is_local": False},
    ]
    out = est.assemble_estimate(priced=priced, metas=metas, chapter_count=10, cfg=settings)
    assert out["estimated_usd_high"] == 6.0
    assert out["estimated_usd_low"] == 3.0  # × est_low_factor 0.5
    assert out["estimated_minutes_high"] > 0
    assert out["estimated_minutes_low"] <= out["estimated_minutes_high"]
    assert out["currency"] == "USD"
    # #5 polish — per_stage carries the priced workload (tokens), not just $.
    tr = next(s for s in out["per_stage"] if s["stage"] == "translation")
    assert tr["input_tokens"] == 1000  # source_tokens
    assert tr["output_tokens"] > 0     # source × translation_output_ratio
    # D-FACTORY-EST-PROVIDER-KIND — provider_kind + is_local threaded from the oracle item.
    assert tr["provider_kind"] == "ollama" and tr["is_local"] is True
    vr = next(s for s in out["per_stage"] if s["stage"] == "verify")
    assert vr["provider_kind"] == "openai" and vr["is_local"] is False
    # a not-estimated stage (no model) has zero tokens + no badge
    ex = next(s for s in out["per_stage"] if s["stage"] == "extraction")
    assert ex["input_tokens"] == 0 and ex["output_tokens"] == 0
    assert ex["provider_kind"] is None and ex["is_local"] is False


def test_assemble_unpriced_makes_band_a_floor():
    items, metas = est.build_pricing_items(
        source_tokens=1000, chapter_count=1,
        models={est.ROLE_TRANSLATOR: ("user_model", TR),
                est.ROLE_EXTRACTOR: ("user_model", EX)}, cfg=settings)
    priced = [
        {"label": "translation", "status": "ok", "estimated_usd": 5.0},
        {"label": "extraction", "status": "unpriced", "estimated_usd": 0.0},
        {"label": "verify", "status": "ok", "estimated_usd": 1.0},
    ]
    out = est.assemble_estimate(priced=priced, metas=metas, chapter_count=1, cfg=settings)
    assert out["estimated_usd_high"] == 6.0  # unpriced contributes $0
    assert any("lower bound" in n for n in out["notes"])
    assert any("no pricing" in n for n in out["notes"])
    # review-impl #1: the unpriced extraction stage still RUNS → time must count it
    # (time is driven by stages-with-a-model, not by oracle pricing success).
    assert out["estimated_minutes_high"] > 0


# ── route ───────────────────────────────────────────────────────────────────

def _book_stub(mocker, *, owner=TEST_USER, chapters=None, owner_exc=None):
    inst = MagicMock()
    inst.get_owner_user_id = AsyncMock(return_value=owner, side_effect=owner_exc)
    inst.list_indexed_chapters = AsyncMock(
        return_value=chapters if chapters is not None
        else [ChapterRef("11111111-1111-1111-1111-111111111111", 0, byte_size=9000)])
    inst.aclose = AsyncMock()
    mocker.patch("app.routers.campaigns.BookClient", return_value=inst)
    return inst


def _oracle_stub(mocker, *, items=None, exc=None):
    inst = MagicMock()
    inst.estimate = AsyncMock(return_value=items if items is not None else [], side_effect=exc)
    inst.aclose = AsyncMock()
    mocker.patch("app.routers.campaigns.ProviderRegistryEstimateClient", return_value=inst)
    return inst


def _req(**over):
    p = {"book_id": BOOK,
         "models": {"translator": {"model_source": "user_model", "model_ref": TR}}}
    p.update(over)
    return p


def test_estimate_happy_path(client, mocker):
    _book_stub(mocker)
    _oracle_stub(mocker, items=[
        {"label": "translation", "status": "ok", "estimated_usd": 3.0},
        {"label": "verify", "status": "ok", "estimated_usd": 1.0},
    ])
    resp = client.post("/v1/campaigns/estimate", json=_req())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chapter_count"] == 1
    assert float(body["estimated_usd_high"]) == 4.0
    stages = {s["stage"]: s for s in body["per_stage"]}
    assert stages["translation"]["status"] == "ok"
    assert stages["rerank"]["status"] == "not_estimated"


def test_estimate_no_models_skips_oracle(client, mocker):
    _book_stub(mocker)
    oracle = _oracle_stub(mocker)
    resp = client.post("/v1/campaigns/estimate", json=_req(models={}))
    assert resp.status_code == 200, resp.text
    oracle.estimate.assert_not_called()  # no items → no oracle call
    assert float(resp.json()["estimated_usd_high"]) == 0.0


def test_estimate_denied_without_grant_404(client, mocker, fake_grant):
    # E0-4b: estimate is `view`-gated (any grantee may size a campaign on a shared
    # book). No grant → 404 (anti-oracle). Owner-compare is gone.
    from app.grant_client import GrantLevel
    fake_grant.resolve_grant.return_value = GrantLevel.NONE
    _book_stub(mocker)
    resp = client.post("/v1/campaigns/estimate", json=_req())
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CAMPAIGN_NOT_FOUND"


def test_estimate_no_chapters(client, mocker):
    _book_stub(mocker, chapters=[])
    resp = client.post("/v1/campaigns/estimate", json=_req())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CAMPAIGN_NO_CHAPTERS"


def test_estimate_oracle_unavailable_502(client, mocker):
    _book_stub(mocker)
    _oracle_stub(mocker, exc=EstimateUnavailable("pricing oracle down"))
    resp = client.post("/v1/campaigns/estimate", json=_req())
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "CAMPAIGN_ESTIMATE_UNAVAILABLE"
