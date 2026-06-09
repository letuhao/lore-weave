"""Campaign API tests — ownership verify-once, projection seed, lifecycle."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

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


# ── S5b model matrix: verifier + embedding/reranker ──────────────────────────

VER = "77777777-7777-7777-7777-777777777777"
EMB = "44444444-4444-4444-4444-444444444444"


def _knowledge_stub(mocker, *, exc=None):
    from app.clients.dispatch_clients import EmbeddingConflict, DispatchError  # noqa: F401
    inst = MagicMock()
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
    mocker.patch("app.repositories.update_budget", new_callable=AsyncMock,
                 return_value=_campaign_row(budget_usd=Decimal("10.00")))
    resp = client.patch(f"/v1/campaigns/{CAMP}", json={"budget_usd": "10.00"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget_usd"] == "10.00"


def test_patch_budget_not_found_404(client, mocker):
    mocker.patch("app.repositories.update_budget", new_callable=AsyncMock, return_value=None)
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


def test_get_returns_projection(client, mocker):
    mocker.patch("app.repositories.get_campaign",
                 new_callable=AsyncMock, return_value=_campaign_row())
    mocker.patch("app.repositories.get_campaign_chapters", new_callable=AsyncMock,
                 return_value=[FakeRecord({
                     "chapter_id": UUID(C1), "chapter_sort": 0,
                     "ingest_status": "done", "knowledge_status": "pending",
                     "translation_status": "pending", "eval_status": "pending",
                     "knowledge_attempts": 0, "translation_attempts": 0,
                     "last_error": None,
                 })])
    resp = client.get(f"/v1/campaigns/{CAMP}")
    assert resp.status_code == 200
    assert len(resp.json()["chapters"]) == 1
    assert resp.json()["chapters"][0]["chapter_id"] == C1


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
