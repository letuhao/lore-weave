"""Authoring-run HTTP router tests (RAID Wave D2) — mirrors the plan_forge
router test style (stub service + stub grant via dependency_overrides)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.clients.book_client import BookClientError
from app.db.models import AuthoringRun, AuthoringRunUnit
from app.deps import get_authoring_run_service, get_book_client_dep, get_grant_client_dep
from app.main import app
from app.middleware.jwt_auth import get_current_user
from app.services.authoring_run_service import (
    ActiveRunOverlapError,
    TransitionConflictError,
)

USER = uuid.uuid4()
BOOK = uuid.uuid4()
PLAN = uuid.uuid4()
RUN = uuid.uuid4()
CH1, CH2 = uuid.uuid4(), uuid.uuid4()

AUTH = {"Authorization": "Bearer test-jwt"}


def _run(status="draft", **over) -> AuthoringRun:
    base = dict(
        run_id=RUN, owner_user_id=USER, book_id=BOOK, plan_run_id=PLAN, level=3,
        scope=[str(CH1), str(CH2)], budget_usd=Decimal("1.00"),
        spent_usd=Decimal("0"), tool_allowlist=["book_write_draft"],
        params={"model_source": "user_model", "model_ref": str(uuid.uuid4())},
        breaker_state={}, status=status, current_unit=0,
        created_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
    )
    base.update(over)
    return AuthoringRun(**base)


class StubGrant:
    async def resolve_grant(self, book_id, caller):
        from app.grant_client import GrantLevel

        return GrantLevel.EDIT


class StubBook:
    def __init__(self):
        self.restores: list[tuple] = []

    async def list_chapters(self, book_id, bearer, *, limit=200):
        return [
            {"chapter_id": str(CH1), "title": "", "sort_order": 1},
            {"chapter_id": str(CH2), "title": "", "sort_order": 2},
        ]

    async def restore_revision(self, book_id, chapter_id, revision_id, bearer):
        self.restores.append((book_id, chapter_id, revision_id, bearer))
        return {"draft_version": 3}


def _unit(unit_index=0, status="drafted", **over) -> AuthoringRunUnit:
    base = dict(
        run_id=RUN, unit_index=unit_index, chapter_id=CH1, status=status,
        pre_revision_id=uuid.uuid4(), post_revision_id=uuid.uuid4(),
        cost_usd=Decimal("0.02"),
        created_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
    )
    base.update(over)
    return AuthoringRunUnit(**base)


class StubService:
    def __init__(self):
        self.runs = {RUN: _run()}
        self.gate_error: Exception | None = None
        self.review_error: Exception | None = None
        self.revert_all_result: dict = {
            "reverted_unit_indexes": [1, 0], "failed_unit_index": None,
            "error": None, "run_status": "closed", "closed": True,
        }

    async def create(self, owner_user_id, book_id, **kwargs):
        if kwargs.get("plan_run_id") != PLAN:
            raise LookupError("plan run not found")
        return self.runs[RUN]

    async def get(self, owner_user_id, run_id):
        return self.runs.get(run_id)

    async def list(self, owner_user_id, book_id, *, limit=20):
        return list(self.runs.values())

    async def gate(self, owner_user_id, run_id, *, book_chapter_ids):
        self.seen_chapter_ids = book_chapter_ids
        if self.gate_error is not None:
            raise self.gate_error
        return _run(status="gated")

    async def start(self, owner_user_id, run_id):
        return _run(status="running")

    async def pause(self, owner_user_id, run_id):
        raise TransitionConflictError("pause requires status=running, run is draft")

    async def resume(self, owner_user_id, run_id):
        return _run(status="running")

    async def close(self, owner_user_id, run_id):
        return _run(status="closed")

    # ── D3 — report + review ────────────────────────────────────────────

    async def get_any(self, run_id):
        return self.runs.get(run_id)

    async def unit_report(self, run):
        if run.status not in ("report_ready", "failed", "paused", "closed"):
            raise TransitionConflictError(f"report requires …, run is {run.status}")
        return [
            {"unit_index": 0, "chapter_id": str(CH1), "status": "drafted",
             "pre_revision_id": str(uuid.uuid4()), "post_revision_id": str(uuid.uuid4()),
             "cost_usd": "0.02", "error_message": None, "downstream_unit_indexes": [1]},
            {"unit_index": 1, "chapter_id": str(CH2), "status": "drafted",
             "pre_revision_id": str(uuid.uuid4()), "post_revision_id": str(uuid.uuid4()),
             "cost_usd": "0.02", "error_message": None, "downstream_unit_indexes": []},
        ]

    async def accept_unit(self, owner_user_id, run_id, unit_index):
        if self.review_error is not None:
            raise self.review_error
        return _unit(unit_index=unit_index, status="accepted")

    async def reject_unit(self, owner_user_id, run_id, unit_index, *, restore):
        if self.review_error is not None:
            raise self.review_error
        # exercise the router-bound restore closure (proves BookClient + the
        # caller's bearer are wired through)
        await restore(BOOK, CH1, PRE_REV)
        return _unit(unit_index=unit_index, status="rejected"), [1], True

    async def revert_all(self, owner_user_id, run_id, *, restore):
        if self.review_error is not None:
            raise self.review_error
        await restore(BOOK, CH2, PRE_REV)
        return self.revert_all_result


PRE_REV = uuid.uuid4()


@pytest.fixture
def stub():
    return StubService()


@pytest.fixture
def book():
    return StubBook()


@pytest.fixture
def client(stub, book):
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_grant_client_dep] = lambda: StubGrant()
    app.dependency_overrides[get_book_client_dep] = lambda: book
    app.dependency_overrides[get_authoring_run_service] = lambda: stub
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_body(**over):
    body = {
        "book_id": str(BOOK), "plan_run_id": str(PLAN), "level": 3,
        "scope": [str(CH1), str(CH2)], "budget_usd": "1.00",
        "tool_allowlist": ["book_write_draft"],
        "params": {"model_source": "user_model", "model_ref": str(uuid.uuid4())},
    }
    body.update(over)
    return body


def test_create_201(client):
    r = client.post("/v1/composition/authoring-runs", json=_create_body(), headers=AUTH)
    assert r.status_code == 201
    assert r.json()["status"] == "draft"
    assert r.json()["run_id"] == str(RUN)


def test_create_unknown_plan_404(client):
    r = client.post(
        "/v1/composition/authoring-runs",
        json=_create_body(plan_run_id=str(uuid.uuid4())), headers=AUTH,
    )
    assert r.status_code == 404


def test_create_level_out_of_range_422(client):
    r = client.post(
        "/v1/composition/authoring-runs", json=_create_body(level=2), headers=AUTH,
    )
    assert r.status_code == 422  # Literal[3,4] — the dial's autonomous levels only


def test_gate_200_passes_book_chapter_set(client, stub):
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/gate", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "gated"
    assert stub.seen_chapter_ids == {str(CH1), str(CH2)}


def test_gate_unknown_run_404(client):
    r = client.post(
        f"/v1/composition/authoring-runs/{uuid.uuid4()}/gate", headers=AUTH,
    )
    assert r.status_code == 404


def test_gate_validation_maps_400(client, stub):
    stub.gate_error = ValueError("budget_usd must be > 0")
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/gate", headers=AUTH)
    assert r.status_code == 400
    assert "budget_usd" in r.json()["detail"]


def test_gate_overlap_maps_409(client, stub):
    stub.gate_error = ActiveRunOverlapError("another authoring run is already active")
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/gate", headers=AUTH)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "active_run_overlap"


def test_gate_wrong_state_maps_409(client, stub):
    stub.gate_error = TransitionConflictError("gate requires status=draft")
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/gate", headers=AUTH)
    assert r.status_code == 409


def test_start_200(client):
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/start", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "running"


def test_pause_wrong_state_409(client):
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/pause", headers=AUTH)
    assert r.status_code == 409


def test_resume_and_close(client):
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/resume", headers=AUTH)
    assert r.status_code == 200
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/close", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_get_200_and_foreign_404(client):
    r = client.get(f"/v1/composition/authoring-runs/{RUN}", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["scope"] == [str(CH1), str(CH2)]
    r = client.get(f"/v1/composition/authoring-runs/{uuid.uuid4()}", headers=AUTH)
    assert r.status_code == 404


def test_list_requires_book_id_and_returns_items(client):
    r = client.get("/v1/composition/authoring-runs", headers=AUTH)
    assert r.status_code == 422  # book_id query is required
    r = client.get(f"/v1/composition/authoring-runs?book_id={BOOK}", headers=AUTH)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


# ── D3 — Run Report ─────────────────────────────────────────────────────────


def test_report_200_with_units_and_dependency_note(client, stub):
    stub.runs[RUN] = _run(status="report_ready")
    r = client.get(f"/v1/composition/authoring-runs/{RUN}/report", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["run"]["status"] == "report_ready"
    assert [u["unit_index"] for u in body["units"]] == [0, 1]
    assert body["units"][0]["downstream_unit_indexes"] == [1]
    assert body["dependencies"]["model"] == "sequential_thread"


def test_report_unknown_run_404(client):
    r = client.get(
        f"/v1/composition/authoring-runs/{uuid.uuid4()}/report", headers=AUTH,
    )
    assert r.status_code == 404


def test_report_wrong_status_409(client, stub):
    # default stub run is draft — not reportable yet
    r = client.get(f"/v1/composition/authoring-runs/{RUN}/report", headers=AUTH)
    assert r.status_code == 409


# ── D3 — accept / reject ────────────────────────────────────────────────────


def test_accept_unit_200(client):
    r = client.post(
        f"/v1/composition/authoring-runs/{RUN}/units/0/accept", headers=AUTH,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"


def test_accept_unit_unknown_404_and_conflict_409(client, stub):
    stub.review_error = LookupError("unit not found")
    r = client.post(
        f"/v1/composition/authoring-runs/{RUN}/units/9/accept", headers=AUTH,
    )
    assert r.status_code == 404
    stub.review_error = TransitionConflictError("accept requires unit status=drafted")
    r = client.post(
        f"/v1/composition/authoring-runs/{RUN}/units/0/accept", headers=AUTH,
    )
    assert r.status_code == 409


def test_reject_unit_200_restores_with_caller_bearer_and_warns_cascade(client, stub, book):
    r = client.post(
        f"/v1/composition/authoring-runs/{RUN}/units/0/reject", headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["reverted"] is True
    assert body["cascade_warning"]["downstream_unit_indexes"] == [1]
    # the router bound BookClient.restore_revision with the CALLER's bearer
    assert book.restores == [(BOOK, CH1, PRE_REV, "test-jwt")]


def test_reject_restore_failure_maps_502_unit_left_drafted(client, stub):
    stub.review_error = BookClientError(502, "BOOK_SERVICE_UNAVAILABLE")
    r = client.post(
        f"/v1/composition/authoring-runs/{RUN}/units/0/reject", headers=AUTH,
    )
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "RESTORE_FAILED"
    assert "left drafted" in r.json()["detail"]["detail"]


# ── D3 — Revert-All ─────────────────────────────────────────────────────────


def test_revert_all_200_closes_run(client, stub, book):
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/revert-all", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["reverted_unit_indexes"] == [1, 0]  # reverse unit order
    assert body["closed"] is True
    assert book.restores and book.restores[0][3] == "test-jwt"


def test_revert_all_partial_failure_maps_502(client, stub):
    stub.revert_all_result = {
        "reverted_unit_indexes": [1], "failed_unit_index": 0,
        "error": "book-service 502", "run_status": "report_ready", "closed": False,
    }
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/revert-all", headers=AUTH)
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["code"] == "REVERT_ALL_PARTIAL"
    assert detail["reverted_unit_indexes"] == [1]
    assert detail["failed_unit_index"] == 0


def test_revert_all_wrong_status_409(client, stub):
    stub.review_error = TransitionConflictError("revert-all requires run status in …")
    r = client.post(f"/v1/composition/authoring-runs/{RUN}/revert-all", headers=AUTH)
    assert r.status_code == 409
