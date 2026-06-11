"""Campaign API tests — ownership verify-once, projection seed, lifecycle."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.clients.book_client import ChapterRef, BookNotFound, BookServiceError
from tests.conftest import FakeRecord, TEST_USER

BOOK = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PROJ = "99999999-9999-9999-9999-999999999999"
CAMP = "dddddddd-dddd-dddd-dddd-dddddddddddd"
C1 = "11111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 6, 9, tzinfo=timezone.utc)


def _campaign_row(**over):
    base = {
        "campaign_id": UUID(CAMP),
        "owner_user_id": UUID(TEST_USER),
        "book_id": UUID(BOOK),
        "name": "My Campaign",
        "status": "created",
        "gating_mode": "phase_barrier",
        "stages": ["knowledge", "translation", "eval"],
        "target_language": "vi",
        "knowledge_project_id": UUID(PROJ),
        "knowledge_model_source": "user_model",
        "knowledge_model_ref": None,
        "translation_model_source": "user_model",
        "translation_model_ref": None,
        "verifier_model_source": None,
        "verifier_model_ref": None,
        "eval_judge_model_source": None,
        "eval_judge_model_ref": None,
        "chapter_from": None,
        "chapter_to": None,
        "budget_usd": None,
        "spent_usd": Decimal("0"),
        "total_chapters": 1,
        "error_message": None,
        "created_at": NOW,
        "updated_at": NOW,
        "started_at": None,
        "finished_at": None,
    }
    base.update(over)
    return FakeRecord(base)


def _book_stub(mocker, *, owner=TEST_USER, chapters=None, owner_exc=None, chapters_exc=None):
    inst = MagicMock()
    inst.get_owner_user_id = AsyncMock(
        return_value=owner, side_effect=owner_exc)
    inst.list_published_chapters = AsyncMock(
        return_value=chapters if chapters is not None else [ChapterRef(C1, 0)],
        side_effect=chapters_exc)
    inst.aclose = AsyncMock()
    mocker.patch("app.routers.campaigns.BookClient", return_value=inst)
    # D-CAMPAIGN-KPROJECT-OWNERSHIP: every create now probes project ownership via
    # KnowledgeDispatchClient.verify_project_owner. Default it to owned=True so the
    # existing create tests exercise the book-ownership/chapters paths; the
    # embedding tests re-patch via _knowledge_stub, and the not-owned test overrides.
    kn = MagicMock()
    kn.verify_project_owner = AsyncMock(return_value=True)
    kn.set_campaign_models = AsyncMock(return_value={})
    kn.aclose = AsyncMock()
    mocker.patch("app.routers.campaigns.KnowledgeDispatchClient", return_value=kn)
    return inst


def _payload(**over):
    p = {"book_id": BOOK, "name": "My Campaign", "knowledge_project_id": PROJ,
         "gating_mode": "phase_barrier", "target_language": "vi"}
    p.update(over)
    return p


# ── create ────────────────────────────────────────────────────────────────

def test_create_success(client, mocker):
    _book_stub(mocker)
    mocker.patch("app.repositories.create_campaign",
                 new_callable=AsyncMock, return_value=_campaign_row())
    mocker.patch("app.repositories.seed_campaign_chapters", new_callable=AsyncMock)
    resp = client.post("/v1/campaigns", json=_payload())
    assert resp.status_code == 201, resp.text
    assert resp.json()["campaign_id"] == CAMP
    assert resp.json()["status"] == "created"


def test_create_project_not_owned_400(client, mocker):
    # D-CAMPAIGN-KPROJECT-OWNERSHIP: a project the user doesn't own → fast 400 at
    # create, not a fail-closed mid-dispatch.
    _book_stub(mocker)
    kn = _knowledge_stub(mocker)
    kn.verify_project_owner = AsyncMock(return_value=False)
    resp = client.post("/v1/campaigns", json=_payload())
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "CAMPAIGN_PROJECT_NOT_FOUND"


def test_create_requires_knowledge_project(client, mocker):
    _book_stub(mocker)
    resp = client.post("/v1/campaigns", json=_payload(knowledge_project_id=None))
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CAMPAIGN_NO_KNOWLEDGE_PROJECT"


def test_create_forbidden_when_not_owner(client, mocker):
    _book_stub(mocker, owner="ffffffff-ffff-ffff-ffff-ffffffffffff")
    resp = client.post("/v1/campaigns", json=_payload())
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "CAMPAIGN_FORBIDDEN"


def test_create_book_not_found(client, mocker):
    _book_stub(mocker, owner_exc=BookNotFound(BOOK))
    resp = client.post("/v1/campaigns", json=_payload())
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CAMPAIGN_BOOK_NOT_FOUND"


def test_create_book_service_down(client, mocker):
    _book_stub(mocker, owner_exc=BookServiceError("conn refused"))
    resp = client.post("/v1/campaigns", json=_payload())
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "CAMPAIGN_BOOK_SERVICE_ERROR"


def test_create_no_chapters_in_range(client, mocker):
    _book_stub(mocker, chapters=[])
    resp = client.post("/v1/campaigns", json=_payload())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CAMPAIGN_NO_CHAPTERS"


def test_create_invalid_gating_mode_422(client, mocker):
    _book_stub(mocker)
    resp = client.post("/v1/campaigns", json=_payload(gating_mode="bogus"))
    assert resp.status_code == 422


def test_create_invalid_est_band_422(client, mocker):
    # G1 (review-impl LOW): est_usd_low > est_usd_high is rejected at validation.
    _book_stub(mocker)
    resp = client.post("/v1/campaigns", json=_payload(est_usd_low="10.00", est_usd_high="5.00"))
    assert resp.status_code == 422


# ── S5b model matrix: verifier + embedding/reranker ──────────────────────────

VER = "77777777-7777-7777-7777-777777777777"
EMB = "44444444-4444-4444-4444-444444444444"


def _knowledge_stub(mocker, *, exc=None):
    from app.clients.dispatch_clients import EmbeddingConflict, DispatchError  # noqa: F401
    inst = MagicMock()
    inst.verify_project_owner = AsyncMock(return_value=True)  # D-CAMPAIGN-KPROJECT-OWNERSHIP
    inst.set_campaign_models = AsyncMock(return_value={}, side_effect=exc)
    inst.aclose = AsyncMock()
    mocker.patch("app.routers.campaigns.KnowledgeDispatchClient", return_value=inst)
    return inst


def test_create_threads_verifier_to_repo(client, mocker):
    _book_stub(mocker)
    create = mocker.patch("app.repositories.create_campaign",
                          new_callable=AsyncMock, return_value=_campaign_row())
    mocker.patch("app.repositories.seed_campaign_chapters", new_callable=AsyncMock)
    resp = client.post("/v1/campaigns", json=_payload(
        verifier_model_source="user_model", verifier_model_ref=VER))
    assert resp.status_code == 201, resp.text
    assert create.call_args.kwargs["verifier_model_source"] == "user_model"
    assert str(create.call_args.kwargs["verifier_model_ref"]) == VER


def test_create_threads_eval_judge_to_repo(client, mocker):
    _book_stub(mocker)
    create = mocker.patch("app.repositories.create_campaign",
                          new_callable=AsyncMock, return_value=_campaign_row())
    mocker.patch("app.repositories.seed_campaign_chapters", new_callable=AsyncMock)
    EJ = "88888888-8888-8888-8888-888888888888"
    resp = client.post("/v1/campaigns", json=_payload(
        eval_judge_model_source="user_model", eval_judge_model_ref=EJ))
    assert resp.status_code == 201, resp.text
    assert create.call_args.kwargs["eval_judge_model_source"] == "user_model"
    assert str(create.call_args.kwargs["eval_judge_model_ref"]) == EJ


def test_create_with_embedding_applies_to_project(client, mocker):
    _book_stub(mocker)
    kn = _knowledge_stub(mocker)
    mocker.patch("app.repositories.create_campaign",
                 new_callable=AsyncMock, return_value=_campaign_row())
    mocker.patch("app.repositories.seed_campaign_chapters", new_callable=AsyncMock)
    resp = client.post("/v1/campaigns", json=_payload(
        embedding_model_source="user_model", embedding_model_ref=EMB))
    assert resp.status_code == 201, resp.text
    kn.set_campaign_models.assert_awaited_once()
    assert str(kn.set_campaign_models.call_args.kwargs["embedding_model_ref"]) == EMB


def test_create_no_model_overrides_skips_knowledge_call(client, mocker):
    _book_stub(mocker)
    kn = _knowledge_stub(mocker)
    mocker.patch("app.repositories.create_campaign",
                 new_callable=AsyncMock, return_value=_campaign_row())
    mocker.patch("app.repositories.seed_campaign_chapters", new_callable=AsyncMock)
    resp = client.post("/v1/campaigns", json=_payload())
    assert resp.status_code == 201, resp.text
    kn.set_campaign_models.assert_not_called()  # no embedding/rerank picks → no patch


def test_create_embedding_conflict_409(client, mocker):
    from app.clients.dispatch_clients import EmbeddingConflict
    _book_stub(mocker)
    _knowledge_stub(mocker, exc=EmbeddingConflict("graph exists"))
    # create_campaign must NOT be reached when the project patch conflicts.
    create = mocker.patch("app.repositories.create_campaign", new_callable=AsyncMock)
    resp = client.post("/v1/campaigns", json=_payload(
        embedding_model_source="user_model", embedding_model_ref=EMB))
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CAMPAIGN_EMBEDDING_CONFLICT"
    create.assert_not_called()


# ── S6 progress ──────────────────────────────────────────────────────────────

def _agg(**over):
    base = {
        "total": 10,
        "kn_done": 6, "kn_failed": 1, "kn_skipped": 0,
        "tr_done": 4, "tr_failed": 0, "tr_skipped": 1,
        "ev_done": 3, "ev_failed": 0, "ev_skipped": 0,
    }
    base.update(over)
    return FakeRecord(base)


def test_progress_per_stage_counts(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(total_chapters=10, status="running"))
    mocker.patch("app.repositories.get_campaign_progress", new_callable=AsyncMock,
                 return_value=_agg())
    resp = client.get(f"/v1/campaigns/{CAMP}/progress")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["total_chapters"] == 10
    kn = body["stages"]["knowledge"]
    assert kn["done"] == 6 and kn["failed"] == 1 and kn["skipped"] == 0
    assert kn["in_progress"] == 3  # 10 - 6 - 1 - 0
    tr = body["stages"]["translation"]
    assert tr["in_progress"] == 5  # 10 - 4 - 0 - 1


def _report_row(**over):
    base = {
        "status": "completed", "total_chapters": 10,
        "spent_usd": Decimal("8.50"), "budget_usd": Decimal("12.00"),
        "est_usd_low": Decimal("7.00"), "est_usd_high": Decimal("11.00"),
        "started_at": NOW, "finished_at": NOW, "duration_seconds": 3600,
    }
    base.update(over)
    return FakeRecord(base)


def test_report_summary_and_error_groups(client, mocker):
    # G1: report returns outcome + spent-vs-estimate + error groups bucketed by cause.
    mocker.patch("app.repositories.get_report_row", new_callable=AsyncMock,
                 return_value=_report_row())
    mocker.patch("app.repositories.get_campaign_progress", new_callable=AsyncMock,
                 return_value=_agg())
    mocker.patch("app.repositories.get_failed_error_strings", new_callable=AsyncMock,
                 return_value=[
                     FakeRecord({"last_error": "HTTP 429 rate limit", "n": 3}),
                     FakeRecord({"last_error": "provider 429 again", "n": 2}),
                     FakeRecord({"last_error": "empty body", "n": 1}),
                 ])
    resp = client.get(f"/v1/campaigns/{CAMP}/report")
    assert resp.status_code == 200, resp.text
    b = resp.json()
    assert b["status"] == "completed"
    assert b["duration_seconds"] == 3600
    assert b["est_usd_low"] == "7.00" and b["spent_usd"] == "8.50"
    assert b["stages"]["knowledge"]["done"] == 6
    groups = {g["cause"]: g for g in b["error_groups"]}
    assert groups["rate_limit"]["count"] == 5 and groups["rate_limit"]["remediable"] is True
    assert groups["empty_body"]["count"] == 1 and groups["empty_body"]["remediable"] is False
    # rate_limit (5) sorts before empty_body (1)
    assert b["error_groups"][0]["cause"] == "rate_limit"


def test_report_404_when_not_owned(client, mocker):
    mocker.patch("app.repositories.get_report_row", new_callable=AsyncMock, return_value=None)
    resp = client.get(f"/v1/campaigns/{CAMP}/report")
    assert resp.status_code == 404


def _chap_row(sort, **over):
    base = {
        "chapter_id": "11111111-1111-1111-1111-111111111111", "chapter_sort": sort,
        "ingest_status": "done", "knowledge_status": "done", "translation_status": "failed",
        "eval_status": "pending", "knowledge_attempts": 0, "translation_attempts": 1,
        "last_error": "boom", "eval_fidelity_score": None,
    }
    base.update(over)
    return FakeRecord(base)


def test_chapters_page_returns_items_and_total(client, mocker):
    # D-S6-CHAPTER-PAGING — paginated endpoint returns {items, total}, owner-scoped.
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="running"))
    page = mocker.patch("app.repositories.get_campaign_chapters_page",
                        new_callable=AsyncMock, return_value=([_chap_row(1), _chap_row(2)], 57))
    resp = client.get(f"/v1/campaigns/{CAMP}/chapters?status=all&limit=2&offset=4")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 57 and len(body["items"]) == 2
    # params threaded through
    assert page.call_args.kwargs["status"] == "all"
    assert page.call_args.kwargs["limit"] == 2 and page.call_args.kwargs["offset"] == 4


def test_chapters_page_clamps_and_defaults(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row())
    page = mocker.patch("app.repositories.get_campaign_chapters_page",
                        new_callable=AsyncMock, return_value=([], 0))
    # bogus status → 'attention'; limit over cap → 500; negative offset → 0
    resp = client.get(f"/v1/campaigns/{CAMP}/chapters?status=bogus&limit=9999&offset=-5")
    assert resp.status_code == 200
    assert page.call_args.kwargs["status"] == "attention"
    assert page.call_args.kwargs["limit"] == 500 and page.call_args.kwargs["offset"] == 0


def test_chapters_page_404_when_not_owned(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=None)
    resp = client.get(f"/v1/campaigns/{CAMP}/chapters")
    assert resp.status_code == 404


def test_patch_budget_only_still_works(client, mocker):
    # backward-compat: a budget-only PATCH applies without touching models.
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="running"))
    upd = mocker.patch("app.repositories.update_campaign_fields", new_callable=AsyncMock,
                       return_value=_campaign_row(status="running", budget_usd=Decimal("5")))
    resp = client.patch(f"/v1/campaigns/{CAMP}", json={"budget_usd": "5"})
    assert resp.status_code == 200, resp.text
    # only budget_usd forwarded (no model keys)
    assert set(upd.call_args.args[3].keys()) == {"budget_usd"}


def test_patch_switch_model_on_paused(client, mocker):
    # D-FACTORY-SWITCH-MODEL-RESUME — a paused campaign accepts a model switch.
    new_ref = str(uuid4())
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="paused"))
    upd = mocker.patch("app.repositories.update_campaign_fields", new_callable=AsyncMock,
                       return_value=_campaign_row(status="paused"))
    resp = client.patch(f"/v1/campaigns/{CAMP}",
                        json={"translation_model_source": "user_model", "translation_model_ref": new_ref})
    assert resp.status_code == 200, resp.text
    fields = upd.call_args.args[3]
    assert fields["translation_model_source"] == "user_model"
    assert str(fields["translation_model_ref"]) == new_ref


def test_patch_switch_model_on_running_is_409(client, mocker):
    # a model change on a RUNNING campaign is rejected (pause first).
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="running"))
    upd = mocker.patch("app.repositories.update_campaign_fields", new_callable=AsyncMock)
    resp = client.patch(f"/v1/campaigns/{CAMP}",
                        json={"translation_model_ref": str(uuid4())})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CAMPAIGN_MODELS_LOCKED"
    upd.assert_not_called()  # blocked before the write


def test_patch_empty_body_is_400(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="paused"))
    resp = client.patch(f"/v1/campaigns/{CAMP}", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CAMPAIGN_PATCH_EMPTY"


def test_patch_404_when_not_owned(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=None)
    resp = client.patch(f"/v1/campaigns/{CAMP}", json={"budget_usd": "5"})
    assert resp.status_code == 404


def test_chapters_page_accepts_inflight_status(client, mocker):
    # D-FACTORY-INFLIGHT-PANEL — 'inflight' is a valid status (not clamped to attention)
    # and is threaded to the repo for the "Now processing" panel.
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="running"))
    page = mocker.patch("app.repositories.get_campaign_chapters_page",
                        new_callable=AsyncMock, return_value=([_chap_row(2)], 1))
    resp = client.get(f"/v1/campaigns/{CAMP}/chapters?status=inflight&limit=50")
    assert resp.status_code == 200, resp.text
    assert page.call_args.kwargs["status"] == "inflight"


def test_list_includes_progress_done(client, mocker):
    # #2 polish — the list carries a per-row progress_done (defaults 0 when absent).
    row_with = FakeRecord({**dict(_campaign_row(total_chapters=5)), "progress_done": 3})
    mocker.patch("app.repositories.list_campaigns", new_callable=AsyncMock,
                 return_value=[_campaign_row(total_chapters=10), row_with])
    resp = client.get("/v1/campaigns")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["progress_done"] == 0   # no key in the record → default
    assert body[1]["progress_done"] == 3


def test_rerun_failed_resets_and_rearms(client, mocker):
    # G2: re-run resets failed stages and re-arms a terminal campaign to running.
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="completed"))
    reset = mocker.patch("app.repositories.reset_failed_stages", new_callable=AsyncMock, return_value=3)
    setst = mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/rerun-failed", json={})
    assert resp.status_code == 200, resp.text
    reset.assert_awaited_once()
    setst.assert_awaited_once()
    assert setst.call_args.args[2] == "running"


def test_rerun_failed_passes_chapter_ids(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="failed"))
    reset = mocker.patch("app.repositories.reset_failed_stages", new_callable=AsyncMock, return_value=1)
    mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    cid = "11111111-1111-1111-1111-111111111111"
    resp = client.post(f"/v1/campaigns/{CAMP}/rerun-failed", json={"chapter_ids": [cid]})
    assert resp.status_code == 200, resp.text
    assert str(reset.call_args.args[2][0]) == cid


def test_rerun_failed_nothing_failed_no_rearm(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="completed"))
    mocker.patch("app.repositories.reset_failed_stages", new_callable=AsyncMock, return_value=0)
    setst = mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/rerun-failed", json={})
    assert resp.status_code == 200
    setst.assert_not_awaited()  # nothing failed → no re-arm


def test_rerun_failed_refuses_cancelled(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="cancelled"))
    resp = client.post(f"/v1/campaigns/{CAMP}/rerun-failed", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CAMPAIGN_NOT_RERUNNABLE"


def test_rerun_failed_over_budget(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="failed",
                                            budget_usd=Decimal("5"), spent_usd=Decimal("5")))
    resp = client.post(f"/v1/campaigns/{CAMP}/rerun-failed", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CAMPAIGN_OVER_BUDGET"


def test_progress_404_when_not_owned(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=None)
    resp = client.get(f"/v1/campaigns/{CAMP}/progress")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CAMPAIGN_NOT_FOUND"


# ── S4d budget cap ───────────────────────────────────────────────────────────

def test_create_with_budget_persists_it(client, mocker):
    _book_stub(mocker)
    create = mocker.patch("app.repositories.create_campaign",
                          new_callable=AsyncMock, return_value=_campaign_row(budget_usd=Decimal("5.00")))
    mocker.patch("app.repositories.seed_campaign_chapters", new_callable=AsyncMock)
    resp = client.post("/v1/campaigns", json=_payload(budget_usd="5.00"))
    assert resp.status_code == 201, resp.text
    assert create.call_args.kwargs["budget_usd"] == Decimal("5.00")


def test_create_rejects_nonpositive_budget_422(client, mocker):
    _book_stub(mocker)
    resp = client.post("/v1/campaigns", json=_payload(budget_usd="0"))
    assert resp.status_code == 422


def test_patch_budget_updates(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="running"))
    mocker.patch("app.repositories.update_campaign_fields", new_callable=AsyncMock,
                 return_value=_campaign_row(budget_usd=Decimal("10.00")))
    resp = client.patch(f"/v1/campaigns/{CAMP}", json={"budget_usd": "10.00"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget_usd"] == "10.00"


def test_patch_budget_not_found_404(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=None)
    resp = client.patch(f"/v1/campaigns/{CAMP}", json={"budget_usd": "10.00"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CAMPAIGN_NOT_FOUND"


def test_patch_budget_rejects_nonpositive_422(client, mocker):
    resp = client.patch(f"/v1/campaigns/{CAMP}", json={"budget_usd": "-1"})
    assert resp.status_code == 422


def test_create_rejects_over_ceiling_budget_422(client, mocker):
    _book_stub(mocker)
    resp = client.post("/v1/campaigns", json=_payload(budget_usd="100000000"))
    assert resp.status_code == 422  # >= 10^8 overflows numeric(16,8)


def test_patch_rejects_over_ceiling_budget_422(client, mocker):
    resp = client.patch(f"/v1/campaigns/{CAMP}", json={"budget_usd": "100000000"})
    assert resp.status_code == 422


def test_start_over_budget_409(client, mocker):
    # D-S4D-RESUME-GUARD: resuming a still-over-budget campaign is refused.
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="paused",
                                            budget_usd=Decimal("5"), spent_usd=Decimal("10")))
    resp = client.post(f"/v1/campaigns/{CAMP}/start")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CAMPAIGN_OVER_BUDGET"


def test_start_paused_under_budget_resumes(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 side_effect=[
                     _campaign_row(status="paused", budget_usd=Decimal("10"), spent_usd=Decimal("3")),
                     _campaign_row(status="running", budget_usd=Decimal("10"), spent_usd=Decimal("3")),
                 ])
    mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


# ── get / list ──────────────────────────────────────────────────────────────

def test_get_not_found(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=None)
    resp = client.get(f"/v1/campaigns/{CAMP}")
    assert resp.status_code == 404


def test_get_returns_lightweight_detail(client, mocker):
    # D-S6-CHAPTER-PAGING — the detail no longer embeds chapters (the table fetches
    # them paginated via GET /{id}/chapters); chapters is an empty list here.
    mocker.patch("app.repositories.get_campaign",
                 new_callable=AsyncMock, return_value=_campaign_row())
    resp = client.get(f"/v1/campaigns/{CAMP}")
    assert resp.status_code == 200
    assert resp.json()["campaign_id"] == CAMP
    assert resp.json()["chapters"] == []


# ── start / cancel ───────────────────────────────────────────────────────────

def test_start_created_to_running(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 side_effect=[_campaign_row(status="created"),
                              _campaign_row(status="running")])
    setter = mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    assert setter.call_args.args[2] == "running"


def test_start_rejects_running(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="running"))
    resp = client.post(f"/v1/campaigns/{CAMP}/start")
    assert resp.status_code == 409


def test_cancel_running_to_cancelling(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 side_effect=[_campaign_row(status="running"),
                              _campaign_row(status="cancelling")])
    setter = mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/cancel")
    assert resp.status_code == 200
    assert setter.call_args.args[2] == "cancelling"


def test_cancel_created_immediately_cancelled(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 side_effect=[_campaign_row(status="created"),
                              _campaign_row(status="cancelled")])
    setter = mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/cancel")
    assert resp.status_code == 200
    assert setter.call_args.args[2] == "cancelled"


def test_pause_running_to_paused(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 side_effect=[_campaign_row(status="running"),
                              _campaign_row(status="paused")])
    setter = mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"
    assert setter.call_args.args[2] == "paused"


def test_pause_rejects_non_running(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="created"))
    resp = client.post(f"/v1/campaigns/{CAMP}/pause")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CAMPAIGN_NOT_PAUSABLE"


def test_pause_not_found_404(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock, return_value=None)
    resp = client.post(f"/v1/campaigns/{CAMP}/pause")
    assert resp.status_code == 404


def test_start_resumes_paused(client, mocker):
    # paused → running via the existing start endpoint (resume).
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 side_effect=[_campaign_row(status="paused"),
                              _campaign_row(status="running")])
    setter = mocker.patch("app.repositories.set_campaign_status", new_callable=AsyncMock)
    resp = client.post(f"/v1/campaigns/{CAMP}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    assert setter.call_args.args[2] == "running"


def test_cancel_terminal_409(client, mocker):
    mocker.patch("app.repositories.get_campaign", new_callable=AsyncMock,
                 return_value=_campaign_row(status="completed"))
    resp = client.post(f"/v1/campaigns/{CAMP}/cancel")
    assert resp.status_code == 409


def test_health(client):
    assert client.get("/health").text == "ok"
