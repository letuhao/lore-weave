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
    async def resolve_grant(self, book_id, caller):
        from app.grant_client import GrantLevel
        return GrantLevel.EDIT


def _record(status="pending", diff=None, applied_results=None):
    return PlanBootstrapProposal(
        id=PROPOSAL, run_id=RUN, book_id=BOOK, owner_user_id=USER,
        status=status, diff=diff or {"new_chapters": []},
        applied_results=applied_results or {},
    )


class StubBootstrapService:
    def __init__(self):
        self.record = _record()

    async def propose(self, owner_user_id, book_id, run_id, bearer):
        if run_id != RUN:
            raise LookupError("run not found")
        return self.record

    async def get(self, owner_user_id, book_id, proposal_id):
        return self.record if proposal_id == PROPOSAL else None

    async def approve(self, owner_user_id, book_id, proposal_id):
        if proposal_id != PROPOSAL:
            raise LookupError("proposal not found")
        if self.record.status != "pending":
            raise ValueError(f"cannot approve a proposal in status '{self.record.status}'")
        self.record = self.record.model_copy(update={"status": "approved"})
        return self.record

    async def reject(self, owner_user_id, book_id, proposal_id):
        self.record = self.record.model_copy(update={"status": "rejected"})
        return self.record

    async def apply(self, owner_user_id, book_id, proposal_id, bearer):
        self.record = self.record.model_copy(update={"status": "applied"})
        return self.record


@pytest.fixture
def client():
    stub = StubBootstrapService()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "tok"
    app.dependency_overrides[get_grant_client_dep] = lambda: StubGrant()
    app.dependency_overrides[get_bootstrap_service] = lambda: stub
    yield TestClient(app), stub
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
