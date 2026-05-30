"""C13 — review-gate lifecycle + H0 write-back/promote/retract unit tests.

These exercise the state machine + the WritebackService against an in-memory
fake repo and fake cross-service ports — no DB, no live stack (the real DB
trigger + cross-service contract are covered by the DB tests + the live-smoke).

H0 boundary tests (brief-mandated):
  (a) write-back enters the KG as enriched + quarantine, NOT canon.
  (b) promote → canon RETAINS the permanent origin marker.
  (c) a non-owner CANNOT promote (403 → NotOwnerError).
  (d) reject / retract paths.
  (e) canon-verify (C12) runs BEFORE write-back.
plus illegal-transition, idempotent-promote, approve-is-not-canon.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.clients.writeback import BookOwner, WrittenFact
from app.services.review import (
    IllegalTransitionError,
    ProposalRow,
    ReviewStatus,
    can_transition,
)
from app.services.writeback import (
    NotApprovedError,
    NotOwnerError,
    WritebackService,
)

OWNER = UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
OTHER = UUID("019d5e3c-0000-7e6a-8b27-1344e148bf7c")
PROJECT = UUID("019e7850-aa1c-7cd3-a25c-c2f9ad84fd39")
BOOK = UUID("019e7850-a8d9-78dd-8b2a-f33ccc2396ad")
GLOSS = UUID("019e7850-aa72-78ed-8824-c6466b39498e")


def _proposal(status: str = ReviewStatus.APPROVED, **over) -> ProposalRow:
    now = datetime.now(timezone.utc)
    base = dict(
        proposal_id=uuid4(),
        job_id=uuid4(),
        project_id=PROJECT,
        user_id=OWNER,
        entity_kind="location",
        target_ref="蓬萊",
        content="蓬萊：东海仙山，云雾缭绕。",
        origin="enrichment",
        technique="template",
        provenance_json={"dimensions": {"历史": "上古即为仙山", "地理": "东海之中"}},
        confidence=0.30,
        source_refs_json=[],
        cultural_grounding_ref_id=None,
        review_status=status,
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

    async def set_status(self, *, user_id, project_id, proposal_id, to_status, rejected_reason=None):
        if not can_transition(self._p.review_status, to_status) or to_status == ReviewStatus.PROMOTED:
            raise IllegalTransitionError(self._p.review_status, to_status)
        self._p = replace(self._p, review_status=to_status, rejected_reason=rejected_reason or self._p.rejected_reason)
        return self._p

    async def mark_promoted(self, *, user_id, project_id, proposal_id, promoted_entity_id, promoted_by, promoted_at):
        if self._p.review_status != ReviewStatus.APPROVED:
            raise IllegalTransitionError(self._p.review_status, "promoted")
        self._p = replace(
            self._p,
            review_status=ReviewStatus.PROMOTED,
            promoted_entity_id=promoted_entity_id,
            promoted_by=promoted_by,
            promoted_at=promoted_at,
            promoted_from_proposal_id=self._p.proposal_id,
            original_technique=self._p.technique,
        )
        return self._p

    async def mark_retracted(self, *, user_id, project_id, proposal_id):
        self._p = replace(self._p, rejected_reason="retracted: routed to glossary recycle-bin (reversible)")
        return self._p


class FakePorts:
    """Records every cross-service call so tests can assert the H0 boundary."""

    def __init__(self, owner: UUID = OWNER) -> None:
        self.owner = owner
        self.writeback_calls: list[dict] = []
        self.promote_calls: list[dict] = []
        self.retract_calls: list[dict] = []
        self.recycle_calls: list[dict] = []
        self.glossary_write_calls: list[dict] = []

    async def book_owner(self, *, book_id):
        return BookOwner(book_id=book_id, owner_user_id=self.owner)

    async def write_entity_through_glossary(self, *, book_id, kind_code, name, attributes):
        self.glossary_write_calls.append(
            {"book_id": book_id, "kind_code": kind_code, "name": name, "attributes": attributes}
        )
        return str(GLOSS)

    async def writeback_enriched_facts(self, *, user_id, project_id, proposal_id, glossary_entity_id, canonical_name, entity_kind, technique, facts):
        self.writeback_calls.append({"proposal_id": proposal_id, "technique": technique, "facts": facts})
        # The KG endpoint returns enriched, pending, conf<1.0 — mirror that here.
        return [
            WrittenFact(
                fact_id=f"enr_{i}",
                edge_id=f"enre_{i}",
                dimension=f["dimension"],
                source_type=f"enriched:{technique}",
                confidence=min(float(f["confidence"]), 0.99),
                pending_validation=True,
            )
            for i, f in enumerate(facts)
        ]

    async def promote_enriched_facts(self, *, user_id, proposal_id, promoted_by, promoted_at=None):
        self.promote_calls.append({"proposal_id": proposal_id, "promoted_by": promoted_by})
        return 2

    async def retract_enriched_facts(self, *, user_id, proposal_id):
        self.retract_calls.append({"proposal_id": proposal_id})
        return 2

    async def soft_delete_glossary_entity(self, *, book_id, entity_id, jwt):
        self.recycle_calls.append({"entity_id": entity_id})
        return True


# ── lifecycle DAG ─────────────────────────────────────────────────────────────


def test_legal_transitions():
    assert can_transition("proposed", "author_reviewing")
    assert can_transition("author_reviewing", "approved")
    assert can_transition("approved", "promoted")
    assert can_transition("approved", "rejected")
    # illegal jumps
    assert not can_transition("proposed", "promoted")
    assert not can_transition("proposed", "approved")
    assert not can_transition("promoted", "approved")
    assert not can_transition("rejected", "approved")


@pytest.mark.asyncio
async def test_approve_is_not_canon():
    """approve moves to approved but NEVER canonizes (confidence stays <1.0, no
    promoted markers)."""
    repo = FakeRepo(_proposal(status=ReviewStatus.PROPOSED))
    # proposed → author_reviewing → approved
    p = await repo.set_status(user_id=OWNER, project_id=PROJECT, proposal_id=repo._p.proposal_id, to_status="author_reviewing")
    p = await repo.set_status(user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, to_status="approved")
    assert p.review_status == "approved"
    assert p.confidence < 1.0
    assert p.promoted_entity_id is None
    assert p.promoted_by is None


# ── (a) write-back is QUARANTINED, NOT canon ──────────────────────────────────


@pytest.mark.asyncio
async def test_writeback_enters_quarantined_not_canon():
    p = _proposal(status=ReviewStatus.APPROVED)
    repo = FakeRepo(p)
    ports = FakePorts()
    svc = WritebackService(repo, ports)
    result = await svc.write_back(
        user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
    )
    assert result.canon is False
    assert len(result.facts) >= 1
    for f in result.facts:
        assert f.source_type.startswith("enriched")
        assert f.source_type != "glossary"
        assert f.pending_validation is True
        assert f.confidence < 1.0
    # write-back NEVER calls the promote port (H0).
    assert ports.promote_calls == []
    # the proposal row is still non-canon.
    assert result.proposal["review_status"] == "approved"
    assert result.proposal["promoted_entity_id"] is None
    # H0 A1: write-back never writes enriched CONTENT into a glossary attribute
    # pre-promote (only identity). Here glossary_entity_id was supplied so no
    # glossary write at all; the assertion guards the no-content-leak invariant.
    for call in ports.glossary_write_calls:
        assert "short_description" not in call.get("attributes", {})


@pytest.mark.asyncio
async def test_writeback_writes_identity_only_no_content_leak():
    """H0 A1: when write-back must create the glossary anchor (no entity id
    supplied), it writes IDENTITY ONLY — never the enriched content into a canon
    attribute pre-promote."""
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts()
    svc = WritebackService(FakeRepo(p), ports)
    await svc.write_back(
        user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,  # force anchor creation
    )
    assert ports.glossary_write_calls, "anchor must be created when no id supplied"
    for call in ports.glossary_write_calls:
        assert call["attributes"] == {}, "no enriched content on the canon anchor pre-promote"


@pytest.mark.asyncio
async def test_promote_flows_content_to_glossary_canon():
    """H0 A1: promote (and ONLY promote) flows the enriched content into the
    glossary canonical attribute — the point makeup legitimately becomes canon."""
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,
    )
    # exactly one of the glossary writes carries the content (the post-promote one).
    content_writes = [c for c in ports.glossary_write_calls if "short_description" in c["attributes"]]
    assert content_writes, "promote must canonize the content into the glossary attribute"


@pytest.mark.asyncio
async def test_writeback_requires_approved():
    p = _proposal(status=ReviewStatus.PROPOSED)
    svc = WritebackService(FakeRepo(p), FakePorts())
    with pytest.raises(NotApprovedError):
        await svc.write_back(user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK)


# ── (e) canon-verify runs BEFORE write-back ───────────────────────────────────


@pytest.mark.asyncio
async def test_canon_verify_runs_before_writeback():
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts()
    svc = WritebackService(FakeRepo(p), ports)
    order: list[str] = []

    async def verify(proposal):
        order.append("verify")

    # patch the port to record write order
    orig = ports.writeback_enriched_facts

    async def wrapped(**kw):
        order.append("writeback")
        return await orig(**kw)

    ports.writeback_enriched_facts = wrapped  # type: ignore[assignment]
    await svc.write_back(
        user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        canon_verify=verify,
    )
    assert order == ["verify", "writeback"], order


# ── (b) promote → canon RETAINS the permanent origin marker ───────────────────


@pytest.mark.asyncio
async def test_promote_canonizes_and_retains_origin_marker():
    p = _proposal(status=ReviewStatus.APPROVED)
    repo = FakeRepo(p)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(repo, ports)
    result = await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
    )
    assert result.canon is True
    assert result.facts_promoted == 2
    # the KG promote port was called.
    assert len(ports.promote_calls) == 1
    # PERMANENT origin marker retained on the proposal.
    pr = result.proposal
    assert pr["review_status"] == "promoted"
    assert pr["origin"] == "enrichment"
    assert pr["promoted_from_proposal_id"] == pr["proposal_id"]
    assert pr["original_technique"] == "template"
    assert pr["promoted_by"] == str(OWNER)
    assert pr["promoted_entity_id"] is not None


# ── (c) non-owner CANNOT promote ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_owner_cannot_promote():
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    with pytest.raises(NotOwnerError):
        await svc.promote(
            acting_user_id=OTHER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        )
    # NEVER reached the promote port.
    assert ports.promote_calls == []
    assert ports.writeback_calls == []


@pytest.mark.asyncio
async def test_anonymous_cannot_promote():
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    with pytest.raises(NotOwnerError):
        await svc.promote(
            acting_user_id=None, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        )
    assert ports.promote_calls == []


@pytest.mark.asyncio
async def test_promote_requires_approved():
    p = _proposal(status=ReviewStatus.PROPOSED)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    with pytest.raises(NotApprovedError):
        await svc.promote(acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK)


# ── idempotent promote ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_promote_idempotent_no_duplicate_canon():
    already = _proposal(
        status=ReviewStatus.PROMOTED,
        promoted_entity_id=GLOSS,
        promoted_by=OWNER,
        promoted_at=datetime.now(timezone.utc),
        promoted_from_proposal_id=None,
        original_technique="template",
    )
    already = replace(already, promoted_from_proposal_id=already.proposal_id)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(already), ports)
    result = await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=already.proposal_id, book_id=BOOK,
    )
    assert result.canon is True
    # No second write-back of the entity anchor (no duplicate canon entity).
    assert ports.writeback_calls == []
    assert ports.glossary_write_calls == []


# ── (d) retract path ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retract_routes_to_recycle_bin_and_soft_retracts_kg():
    p = _proposal(
        status=ReviewStatus.PROMOTED,
        promoted_entity_id=GLOSS,
        promoted_by=OWNER,
        promoted_at=datetime.now(timezone.utc),
        original_technique="template",
    )
    p = replace(p, promoted_from_proposal_id=p.proposal_id)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    result = await svc.retract(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=GLOSS, jwt="jwt-token",
    )
    assert result.facts_retracted == 2
    assert result.glossary_recycled is True
    assert ports.retract_calls and ports.recycle_calls
    assert "retracted" in (result.proposal["rejected_reason"] or "")


@pytest.mark.asyncio
async def test_non_owner_cannot_retract():
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    with pytest.raises(NotOwnerError):
        await svc.retract(
            acting_user_id=OTHER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
            glossary_entity_id=GLOSS, jwt="jwt",
        )
    assert ports.retract_calls == []
