"""PlanForge auto-bootstrap gate HTTP router tests (POC)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import PlanBootstrapProposal
from app.main import app
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.deps import get_bootstrap_service, get_grant_client_dep

USER = uuid.uuid4()
BOOK = uuid.uuid4()
RUN = uuid.uuid4()
PROPOSAL = uuid.uuid4()


class StubGrant:
    def __init__(self, level=None):
        from app.grant_client import GrantLevel
        self._level = level if level is not None else GrantLevel.EDIT

    async def resolve_grant(self, book_id, caller):
        return self._level


def _record(status="pending", diff=None, applied_results=None):
    return PlanBootstrapProposal(
        id=PROPOSAL, run_id=RUN, book_id=BOOK, created_by=USER,
        status=status, diff=diff or {"new_chapters": []},
        applied_results=applied_results or {},
    )


class StubBootstrapService:
    def __init__(self):
        self.record = _record()

    async def propose(self, created_by, book_id, run_id, bearer):
        if run_id != RUN:
            raise LookupError("run not found")
        return self.record

    async def get(self, book_id, proposal_id):
        return self.record if proposal_id == PROPOSAL else None

    async def approve(self, book_id, proposal_id):
        if proposal_id != PROPOSAL:
            raise LookupError("proposal not found")
        if self.record.status != "pending":
            raise ValueError(f"cannot approve a proposal in status '{self.record.status}'")
        self.record = self.record.model_copy(update={"status": "approved"})
        return self.record

    async def reject(self, book_id, proposal_id):
        self.record = self.record.model_copy(update={"status": "rejected"})
        return self.record

    async def apply(self, created_by, book_id, proposal_id, bearer):
        self.record = self.record.model_copy(update={"status": "applied"})
        return self.record


def _client(grant_level=None):
    stub = StubBootstrapService()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "tok"
    app.dependency_overrides[get_grant_client_dep] = lambda: StubGrant(grant_level)
    app.dependency_overrides[get_bootstrap_service] = lambda: stub
    return TestClient(app), stub


@pytest.fixture
def client():
    c, stub = _client()
    yield c, stub
    app.dependency_overrides.clear()


@pytest.fixture
def view_only_client():
    from app.grant_client import GrantLevel

    c, stub = _client(GrantLevel.VIEW)
    yield c, stub
    app.dependency_overrides.clear()


@pytest.fixture
def no_grant_client():
    from app.grant_client import GrantLevel

    c, stub = _client(GrantLevel.NONE)
    yield c, stub
    app.dependency_overrides.clear()


def test_propose_returns_pending_record(client):
    c, _stub = client
    r = c.post(f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/bootstrap/propose")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_propose_unknown_run_404s(client):
    c, _stub = client
    other_run = uuid.uuid4()
    r = c.post(f"/v1/composition/books/{BOOK}/plan/runs/{other_run}/bootstrap/propose")
    assert r.status_code == 404


def test_approve_then_apply_happy_path(client):
    c, _stub = client
    r = c.post(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"

    r = c.post(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}/apply")
    assert r.status_code == 200 and r.json()["status"] == "applied"


def test_approve_twice_409s(client):
    c, _stub = client
    r = c.post(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}/approve")
    assert r.status_code == 200
    r = c.post(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}/approve")
    assert r.status_code == 409


def test_get_unknown_proposal_404s(client):
    c, _stub = client
    r = c.get(f"/v1/composition/books/{BOOK}/plan/bootstrap/{uuid.uuid4()}")
    assert r.status_code == 404


def test_get_known_proposal_200s(client):
    c, _stub = client
    r = c.get(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}")
    assert r.status_code == 200
    assert r.json()["id"] == str(PROPOSAL)


# ── M1 hardening: negative-path grant coverage (mirrors test_grant_gate.py) ──

def test_propose_view_only_grant_403s(view_only_client):
    c, _stub = view_only_client
    r = c.post(f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/bootstrap/propose")
    assert r.status_code == 403


def test_propose_no_grant_404s(no_grant_client):
    c, _stub = no_grant_client
    r = c.post(f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/bootstrap/propose")
    assert r.status_code == 404


def test_approve_view_only_grant_403s(view_only_client):
    c, _stub = view_only_client
    r = c.post(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}/approve")
    assert r.status_code == 403


def test_apply_view_only_grant_403s(view_only_client):
    c, _stub = view_only_client
    r = c.post(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}/apply")
    assert r.status_code == 403


def test_get_proposal_view_grant_is_allowed(view_only_client):
    # GET only needs VIEW, unlike the mutating endpoints above.
    c, _stub = view_only_client
    r = c.get(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}")
    assert r.status_code == 200


def test_get_proposal_no_grant_404s(no_grant_client):
    c, _stub = no_grant_client
    r = c.get(f"/v1/composition/books/{BOOK}/plan/bootstrap/{PROPOSAL}")
    assert r.status_code == 404
