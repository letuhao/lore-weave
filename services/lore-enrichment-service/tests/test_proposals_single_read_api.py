"""HTTP-layer tests for GET /v1/lore-enrichment/proposals/{proposal_id}.

The single-read handler is the GAP: the service/repo + the action handlers
(approve/reject/edit/promote/write-back/retract) are exercised elsewhere
(``test_review_gate.py``). Here we drive ONLY the FastAPI handler via
``TestClient`` + ``app.dependency_overrides[get_repo]`` to cover the HTTP seam:

  * Q3 / IDOR guard — a cross-user OR cross-project lookup returns None from the
    scoped repo, so the handler 404s (NO existence oracle: same body whether the
    row is missing or merely out-of-scope).
  * 200 with the EnrichmentProposal shape for the owned row.
  * 401 for an anonymous principal (no/invalid bearer).

No live stack: the repo is a fake mirroring ``ProposalsRepo.get`` scoping and the
principal is injected via an unverified bearer (the C3 contract-freeze posture —
``principal.py`` decodes ``sub`` without signature verification).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import proposals as proposals_api
from app.services.review import ProposalRow, ReviewStatus

OWNER = UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
OTHER = UUID("019d5e3c-0000-7e6a-8b27-1344e148bf7c")
PROJECT = UUID("019e7850-aa1c-7cd3-a25c-c2f9ad84fd39")
OTHER_PROJECT = UUID("019e7850-bbbb-7cd3-a25c-c2f9ad84fd39")


def _proposal(status: str = ReviewStatus.PROPOSED, **over) -> ProposalRow:
    now = datetime.now(timezone.utc)
    base = dict(
        proposal_id=uuid4(),
        job_id=uuid4(),
        project_id=PROJECT,
        user_id=OWNER,
        entity_kind="location",
        target_ref="蓬萊",
        canonical_name="蓬萊",
        content="蓬萊：东海仙山，云雾缭绕。",
        origin="enrichment",
        technique="template",
        provenance_json={"dimensions": {"历史": "上古即为仙山"}},
        confidence=0.30,
        source_refs_json=[],
        cultural_grounding_ref_id=None,
        review_status=status,
        writeback_entity_id=None,
        promoted_entity_id=None,
        promoted_by=None,
        promoted_at=None,
        promoted_from_proposal_id=None,
        original_technique=None,
        rejected_reason=None,
        created_at=now,
        updated_at=now,
    )
    base.update(over)
    return ProposalRow(**base)


class FakeRepo:
    """Mirrors ``ProposalsRepo.get`` scoping: the row is returned ONLY when the
    user_id AND project_id AND proposal_id all match — any cross-scope lookup
    returns None (the IDOR guard the real fetchrow WHERE clause enforces)."""

    def __init__(self, proposal: ProposalRow) -> None:
        self._p = proposal

    async def get(self, *, user_id, project_id, proposal_id):
        if (
            self._p.user_id == user_id
            and self._p.project_id == project_id
            and self._p.proposal_id == proposal_id
        ):
            return self._p
        return None


def _api_client(repo) -> TestClient:
    """A TestClient over just the proposals router with the repo dep overridden
    (no DB / live stack). Single-read touches no cross-service ports, so no
    ``_make_ports`` patch is needed."""
    app = FastAPI()
    app.include_router(proposals_api.router)
    app.dependency_overrides[proposals_api.get_repo] = lambda: repo
    return TestClient(app)


def _bearer(user_id: UUID) -> str:
    """A bearer whose unverified `sub` is ``user_id`` (the principal dependency
    decodes `sub` without signature verification at this stage)."""
    return pyjwt.encode({"sub": str(user_id), "exp": 4102444800}, "test_jwt_secret", algorithm="HS256")


def _get(client: TestClient, proposal_id, project_id, *, bearer: str | None):
    headers = {"Authorization": f"Bearer {bearer}"} if bearer is not None else {}
    return client.get(
        f"/v1/lore-enrichment/proposals/{proposal_id}",
        params={"project_id": str(project_id)},
        headers=headers,
    )


# ── 200: owned row ─────────────────────────────────────────────────────────────


def test_get_proposal_owned_returns_200_with_shape():
    p = _proposal()
    client = _api_client(FakeRepo(p))
    resp = _get(client, p.proposal_id, PROJECT, bearer=_bearer(OWNER))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # the handler returns proposal.as_dict() verbatim — assert the load-bearing
    # identity + scoping fields round-trip as the JSON EnrichmentProposal shape.
    assert body["proposal_id"] == str(p.proposal_id)
    assert body["project_id"] == str(PROJECT)
    assert body["user_id"] == str(OWNER)
    assert body["entity_kind"] == "location"
    assert body["canonical_name"] == "蓬萊"
    assert body["review_status"] == ReviewStatus.PROPOSED
    assert body["confidence"] == pytest.approx(0.30)


# ── 404: IDOR guard (no existence oracle) ────────────────────────────────────────


def test_get_proposal_cross_user_returns_404():
    """A different authenticated user querying the OWNER's proposal id gets the
    scoped repo's None → 404. The id exists, but the IDOR guard never confirms
    that (same body as a truly-missing id)."""
    p = _proposal()
    client = _api_client(FakeRepo(p))
    # OTHER is authenticated, but scope (user_id) does not match → repo.get None.
    resp = _get(client, p.proposal_id, PROJECT, bearer=_bearer(OTHER))
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "proposal not found"


def test_get_proposal_cross_project_returns_404():
    """Owner asking for a real (owned) proposal id but under the WRONG project_id
    gets None → 404 — project_id is part of the scope key, not a hint."""
    p = _proposal()
    client = _api_client(FakeRepo(p))
    resp = _get(client, p.proposal_id, OTHER_PROJECT, bearer=_bearer(OWNER))
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "proposal not found"


def test_get_proposal_unknown_id_returns_404_same_body():
    """A truly-unknown proposal id returns the SAME 404 body as the cross-scope
    miss — proving the no-existence-oracle property (the responses are
    indistinguishable to the caller)."""
    p = _proposal()
    client = _api_client(FakeRepo(p))
    resp = _get(client, uuid4(), PROJECT, bearer=_bearer(OWNER))
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "proposal not found"


# ── 401: anonymous / invalid principal ───────────────────────────────────────────


def test_get_proposal_anonymous_returns_401():
    """No Authorization header → anonymous principal (user_id None) → 401, before
    any repo read."""
    p = _proposal()
    client = _api_client(FakeRepo(p))
    resp = _get(client, p.proposal_id, PROJECT, bearer=None)
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"] == "auth required"


def test_get_proposal_garbage_token_returns_401():
    """A bearer with no recoverable `sub` decodes to an anonymous principal
    (user_id None) → 401, not 404 — the unverified-decode posture still treats a
    sub-less token as anonymous."""
    p = _proposal()
    client = _api_client(FakeRepo(p))
    # a well-formed JWT with NO `sub` claim → _extract_user_id returns None.
    no_sub = pyjwt.encode({"foo": "bar"}, "test_jwt_secret", algorithm="HS256")
    resp = _get(client, p.proposal_id, PROJECT, bearer=no_sub)
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"] == "auth required"
