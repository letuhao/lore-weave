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

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import proposals as proposals_api
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
        canonical_name="蓬萊",
        content="蓬萊：东海仙山，云雾缭绕。",
        origin="enrichment",
        technique="template",
        provenance_json={"dimensions": {"历史": "上古即为仙山", "地理": "东海之中"}},
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

    async def set_writeback_entity_id(self, *, user_id, project_id, proposal_id, writeback_entity_id):
        # Idempotent: first write wins (mirrors the COALESCE in the real repo).
        if self._p.writeback_entity_id is None:
            self._p = replace(self._p, writeback_entity_id=writeback_entity_id)
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
        self.glossary_write_calls: list[dict] = []
        # Enrichment SUPPLEMENT calls (B1 — entity_enrichments). The supplement
        # REPLACES the old short_description canon-content write (F-C13-2) and the
        # old user-JWT recycle (F-C13-1).
        self.supplement_upserts: list[dict] = []
        self.supplement_deletes: list[dict] = []
        # When set, the FIRST upsert_enrichment_supplement call raises this (then
        # clears) — simulates a transient promote-supplement write failure.
        self.upsert_supplement_error: Exception | None = None

    async def aclose(self):
        pass

    async def book_owner(self, *, book_id):
        return BookOwner(book_id=book_id, owner_user_id=self.owner)

    async def write_entity_through_glossary(self, *, book_id, kind_code, name, attributes):
        self.glossary_write_calls.append(
            {"book_id": book_id, "kind_code": kind_code, "name": name, "attributes": attributes}
        )
        return str(GLOSS)

    async def writeback_enriched_facts(self, *, user_id, project_id, proposal_id, glossary_entity_id, canonical_name, entity_kind, technique, facts):
        self.writeback_calls.append({"proposal_id": proposal_id, "technique": technique, "facts": facts, "canonical_name": canonical_name})
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

    async def upsert_enrichment_supplement(
        self, *, book_id, entity_id, proposal_id, technique, review_status,
        facts, promoted_by=None, promoted_at=None,
    ):
        # Transient-failure injection (only the FIRST promoted write fails, then
        # clears) — proves the promote stands + a re-promote re-upserts.
        if review_status == "promoted" and self.upsert_supplement_error is not None:
            err = self.upsert_supplement_error
            self.upsert_supplement_error = None
            raise err
        self.supplement_upserts.append(
            {
                "book_id": book_id, "entity_id": entity_id, "proposal_id": proposal_id,
                "technique": technique, "review_status": review_status,
                "facts": facts, "promoted_by": promoted_by, "promoted_at": promoted_at,
            }
        )
        return len(facts)

    async def delete_enrichment_supplement(self, *, book_id, entity_id, proposal_id):
        self.supplement_deletes.append(
            {"book_id": book_id, "entity_id": entity_id, "proposal_id": proposal_id}
        )
        return 1

    def promoted_upserts(self) -> list[dict]:
        """The supplement upserts that promoted (review_status='promoted')."""
        return [u for u in self.supplement_upserts if u["review_status"] == "promoted"]


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
    # H0 A1: write-back never writes enriched CONTENT into the glossary canon
    # pre-promote (only identity). Here glossary_entity_id was supplied so no
    # glossary write at all; the assertion guards the no-content-leak invariant.
    for call in ports.glossary_write_calls:
        assert "short_description" not in call.get("attributes", {})
    # B1/F-C13-2: write-back writes the supplement as 'proposed' only — it NEVER
    # promotes it (promote is the sole canon transition).
    assert ports.promoted_upserts() == []


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
    # B1/F-C13-2: write-back writes the supplement 'proposed' (quarantined), never
    # promoted, and never touches short_description.
    assert ports.promoted_upserts() == []


# ── T4 (F-C13-2): write-back RESOLVES the canonical entity + writes the supplement


@pytest.mark.asyncio
async def test_writeback_resolves_canonical_name_not_target_ref():
    """F-C13-2 root-cause fix (B3): write-back must pass the faithful
    ``canonical_name`` (蓬萊) to glossary — NOT the synthetic ``target_ref``
    (loc:蓬萊) that minted a parallel entity. The anchor name resolves the
    EXISTING canonical entity."""
    p = _proposal(status=ReviewStatus.APPROVED, target_ref="loc:蓬萊", canonical_name="蓬萊")
    ports = FakePorts()
    svc = WritebackService(FakeRepo(p), ports)
    await svc.write_back(
        user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,  # force anchor resolution by name
    )
    assert ports.glossary_write_calls
    name = ports.glossary_write_calls[0]["name"]
    assert name == "蓬萊", f"anchor must resolve by canonical_name, got {name!r}"
    assert name != "loc:蓬萊", "the synthetic target_ref must NOT be used as the entity name"
    # the KG quarantine fact-anchor uses the same faithful name.
    assert ports.writeback_calls[0]["canonical_name"] == "蓬萊"


@pytest.mark.asyncio
async def test_writeback_writes_proposed_supplement_not_short_description():
    """F-C13-2: write-back writes the enriched dimensions to the
    entity_enrichments SUPPLEMENT (review_status='proposed') on the resolved
    entity — and NEVER to short_description (original canon stays untouched)."""
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts()
    svc = WritebackService(FakeRepo(p), ports)
    result = await svc.write_back(
        user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=GLOSS,
    )
    # supplement written, proposed, on the resolved entity, carrying the facts.
    assert len(ports.supplement_upserts) == 1
    sup = ports.supplement_upserts[0]
    assert sup["review_status"] == "proposed"
    assert sup["entity_id"] == GLOSS
    assert sup["proposal_id"] == p.proposal_id
    assert sup["promoted_by"] is None
    assert len(sup["facts"]) >= 1
    # write-back writes 'proposed' only — never promotes the supplement, and
    # never touches short_description.
    assert ports.promoted_upserts() == []
    # still quarantined.
    assert result.canon is False


@pytest.mark.asyncio
async def test_promote_writes_promoted_supplement_not_short_description():
    """F-C13-2 (B1 / C4): promote flips the enrichment SUPPLEMENT rows to
    'promoted' on the resolved canonical entity — it does NOT write
    short_description (original canon stays original-authored). The supplement is
    a distinguished `dị bản`, promoted but always tellable-apart."""
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,
    )
    # Exactly one PROMOTED supplement upsert, on the resolved entity, with markers.
    promoted = ports.promoted_upserts()
    assert len(promoted) == 1, "promote must upsert the promoted supplement"
    up = promoted[0]
    assert up["entity_id"] == GLOSS
    assert up["promoted_by"] == OWNER
    assert up["promoted_at"] is not None
    assert len(up["facts"]) >= 1
    # The identity anchor write (extract-entities) must NOT carry content.
    for call in ports.glossary_write_calls:
        assert "short_description" not in call["attributes"]


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
    """A re-promote of an already-promoted proposal re-flips the KG + re-upserts
    the PROMOTED supplement (idempotent ON CONFLICT) — and never re-writes the
    entity anchor, so no duplicate canon entity is minted."""
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
    # The re-promote re-upserts the promoted supplement (idempotent), on GLOSS.
    promoted = ports.promoted_upserts()
    assert len(promoted) == 1
    assert promoted[0]["entity_id"] == GLOSS


# ── re-promote re-upserts the PROMOTED supplement (recovery / idempotency) ──────


@pytest.mark.asyncio
async def test_first_promote_supplement_failure_still_promotes():
    """A transient promoted-supplement write failure on the FIRST promote must NOT
    unwind the promotion — the proposal still becomes PROMOTED (KG canon +
    proposal row hold); the promoted supplement is just not yet written (a
    re-promote re-upserts it)."""
    p = _proposal(status=ReviewStatus.APPROVED)
    repo = FakeRepo(p)
    ports = FakePorts(owner=OWNER)
    ports.upsert_supplement_error = RuntimeError("transient glossary 503")
    svc = WritebackService(repo, ports)
    result = await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
    )
    # Promotion STANDS despite the promoted-supplement write failing.
    assert result.canon is True
    assert repo._p.review_status == "promoted"
    assert repo._p.promoted_entity_id == GLOSS
    # The proposed supplement (from write_back) landed; the PROMOTED one failed.
    assert ports.promoted_upserts() == [], "the failed promote-write left no promoted supplement"


@pytest.mark.asyncio
async def test_repromote_reupserts_promoted_supplement_after_failure():
    """Recovery path: promote (promoted-supplement write fails) leaves the
    proposal PROMOTED with the supplement not-yet-promoted — then a SECOND promote
    (the idempotent branch) re-upserts the promoted supplement. A re-promote is
    the real recovery surface (no reconciler exists)."""
    p = _proposal(status=ReviewStatus.APPROVED)
    repo = FakeRepo(p)
    ports = FakePorts(owner=OWNER)
    ports.upsert_supplement_error = RuntimeError("transient glossary 503")
    svc = WritebackService(repo, ports)

    # First promote: promoted-supplement write fails transiently.
    await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
    )
    assert repo._p.review_status == "promoted"
    assert ports.promoted_upserts() == [], "first promote left the supplement un-promoted"

    # Second promote (idempotent branch): the error cleared; the promoted
    # supplement is re-upserted for real.
    result = await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
    )
    assert result.canon is True
    promoted = ports.promoted_upserts()
    assert len(promoted) == 1, "re-promote re-upserts the promoted supplement"
    assert promoted[0]["entity_id"] == GLOSS


@pytest.mark.asyncio
async def test_repromote_supplement_write_failure_stands():
    """Robustness: if the promoted-supplement write fails transiently on a
    re-promote, the promotion still stands (KG re-flipped, no raise) — the error
    is logged and the NEXT re-promote remains the retry surface."""
    already = _proposal(
        status=ReviewStatus.PROMOTED,
        promoted_entity_id=GLOSS,
        promoted_by=OWNER,
        promoted_at=datetime.now(timezone.utc),
        original_technique="template",
    )
    already = replace(already, promoted_from_proposal_id=already.proposal_id)
    ports = FakePorts(owner=OWNER)
    ports.upsert_supplement_error = RuntimeError("transient glossary write 503")
    svc = WritebackService(FakeRepo(already), ports)
    result = await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=already.proposal_id, book_id=BOOK,
    )
    # No raise; promotion stands; KG re-flipped.
    assert result.canon is True
    assert len(ports.promote_calls) == 1
    # The write was attempted and failed (caught) → no promoted supplement recorded.
    assert ports.promoted_upserts() == []


# ── (d) retract path ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retract_soft_deletes_supplement_and_preserves_entity():
    """F-C13-1 fix: retract soft-deletes the enrichment SUPPLEMENT for the
    proposal over the INTERNAL token (no user JWT) + soft-retracts the KG facts.
    The canonical entity is NEVER deleted (recycling the whole entity was the
    F-C13-1 bug)."""
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
        glossary_entity_id=GLOSS,  # NOTE: no jwt — retract no longer needs one
    )
    assert result.facts_retracted == 2
    assert result.supplement_retracted == 1
    assert ports.retract_calls, "KG facts soft-retracted"
    assert ports.supplement_deletes, "supplement soft-deleted"
    sd = ports.supplement_deletes[0]
    assert sd["entity_id"] == GLOSS
    assert sd["proposal_id"] == p.proposal_id
    assert "retracted" in (result.proposal["rejected_reason"] or "")


@pytest.mark.asyncio
async def test_retract_prefers_proposal_entity_over_wrong_client_id():
    """review-impl MED-2: retract resolves the supplement entity from the
    proposal's OWN promotion record, NOT a (possibly wrong/stale) client-supplied
    glossary_entity_id — else a bad id would soft-delete 0 rows and orphan the
    real supplement while reporting success (the F-C13-1 'looks-done' class)."""
    p = _proposal(
        status=ReviewStatus.PROMOTED,
        promoted_entity_id=GLOSS,  # authoritative — the supplement lives here
        promoted_by=OWNER,
        promoted_at=datetime.now(timezone.utc),
        original_technique="template",
    )
    p = replace(p, promoted_from_proposal_id=p.proposal_id)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    wrong = UUID("019e0000-0000-7000-8000-000000000bad")
    await svc.retract(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=wrong,  # caller passes a WRONG id
    )
    assert ports.supplement_deletes, "supplement must be soft-deleted"
    # the proposal's promoted_entity_id wins, NOT the wrong client id.
    assert ports.supplement_deletes[0]["entity_id"] == GLOSS
    assert ports.supplement_deletes[0]["entity_id"] != wrong


@pytest.mark.asyncio
async def test_non_owner_cannot_retract():
    p = _proposal(status=ReviewStatus.APPROVED)
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    with pytest.raises(NotOwnerError):
        await svc.retract(
            acting_user_id=OTHER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
            glossary_entity_id=GLOSS,
        )
    assert ports.retract_calls == []
    assert ports.supplement_deletes == []


# ── FIX-1 (WARN-1): makeup content NEVER becomes the entity name/anchor ─────────


@pytest.mark.asyncio
async def test_writeback_null_target_ref_uses_canonical_name_not_makeup():
    """H0 FIX-1: with target_ref=None, the anchor name is the faithful Gap
    canonical_name — NEVER the makeup content[:32]."""
    makeup = "这是凭空捏造的地点描述，绝不可成为实体名称：仙宫秘境云海深处。"
    p = _proposal(
        status=ReviewStatus.APPROVED,
        target_ref=None,
        canonical_name="昆侖虛",  # faithful name carried from the Gap
        content=makeup,
    )
    ports = FakePorts()
    svc = WritebackService(FakeRepo(p), ports)
    await svc.write_back(
        user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,  # force anchor creation
    )
    assert ports.glossary_write_calls, "anchor must be created"
    for call in ports.glossary_write_calls:
        assert call["name"] == "昆侖虛"
        assert call["name"] != makeup[:32]
        assert makeup[:32] not in call["name"]
    # the KG canonical_name must also be the faithful name, never makeup.
    assert ports.writeback_calls
    assert ports.writeback_calls[0]["canonical_name"] == "昆侖虛"
    assert ports.writeback_calls[0]["canonical_name"] != makeup[:32]


@pytest.mark.asyncio
async def test_writeback_null_target_ref_no_canonical_name_uses_synthetic_id():
    """H0 FIX-1: with NEITHER target_ref NOR canonical_name, the anchor falls back
    to the non-makeup synthetic 'proposal:{id}', never the makeup content[:32]."""
    makeup = "凭空捏造的描述文本，不得成为名称。"
    p = _proposal(
        status=ReviewStatus.APPROVED,
        target_ref=None,
        canonical_name=None,
        content=makeup,
    )
    ports = FakePorts()
    svc = WritebackService(FakeRepo(p), ports)
    await svc.write_back(
        user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,
    )
    assert ports.glossary_write_calls
    for call in ports.glossary_write_calls:
        assert call["name"] == f"proposal:{p.proposal_id}"
        assert makeup[:32] not in call["name"]
        assert call["name"] != makeup[:32]


@pytest.mark.asyncio
async def test_promote_null_target_ref_faithful_name_supplement_not_makeup():
    """H0 FIX-1 + B1: on promote the glossary entity NAME stays the faithful
    identity (北俱蘆洲); the enrichment becomes a PROMOTED supplement on that
    entity — never short_description, and the makeup never becomes the name."""
    makeup = "捏造的地点描述不可作为实体名。"
    p = _proposal(
        status=ReviewStatus.APPROVED,
        target_ref=None,
        canonical_name="北俱蘆洲",
        content=makeup,
    )
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    await svc.promote(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,
    )
    # The enrichment is canonized as a PROMOTED supplement (B1)…
    assert ports.promoted_upserts(), "promote must upsert the promoted supplement"
    # …but the entity NAME (anchor) is always the faithful identity, never makeup,
    # and no makeup is written into short_description (extract-entities attrs).
    for c in ports.glossary_write_calls:
        assert c["name"] == "北俱蘆洲", "the entity NAME is always the faithful identity"
        assert c["name"] != makeup[:32]
        assert "short_description" not in c["attributes"]


# ── FIX-3 (NIT-3): retract locates the anchor of a quarantined-never-promoted ───


@pytest.mark.asyncio
async def test_writeback_persists_anchor_id_for_later_retract():
    """FIX-3: write-back persists the resolved glossary anchor id on the proposal
    row so a later retract (no explicit id, never promoted) can find it."""
    p = _proposal(status=ReviewStatus.APPROVED, writeback_entity_id=None)
    repo = FakeRepo(p)
    svc = WritebackService(repo, FakePorts())
    await svc.write_back(
        user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,  # anchor minted → id must be persisted
    )
    assert repo._p.writeback_entity_id == GLOSS


@pytest.mark.asyncio
async def test_retract_quarantined_never_promoted_locates_anchor_via_writeback_id():
    """FIX-3 / NIT-3: a proposal that was written-back (quarantined) but NEVER
    promoted has no promoted_entity_id. Retract with no explicit id must still
    soft-delete the supplement, located via the persisted writeback_entity_id."""
    p = _proposal(
        status=ReviewStatus.APPROVED,   # approved + written-back, never promoted
        promoted_entity_id=None,
        writeback_entity_id=GLOSS,      # persisted at write-back time
    )
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    result = await svc.retract(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,  # caller supplies NOTHING — must use persisted id
    )
    assert result.supplement_retracted == 1
    assert ports.supplement_deletes, "supplement must be soft-deleted even when never promoted"
    assert ports.supplement_deletes[0]["entity_id"] == GLOSS


@pytest.mark.asyncio
async def test_retract_orphan_when_no_anchor_id_anywhere():
    """Guard: with no supplied id, no promoted_entity_id, and no writeback_entity_id
    (e.g. never written back), retract does NOT touch the glossary (nothing to
    locate) — and must not raise. The KG soft-retract still runs."""
    p = _proposal(
        status=ReviewStatus.APPROVED,
        promoted_entity_id=None,
        writeback_entity_id=None,
    )
    ports = FakePorts(owner=OWNER)
    svc = WritebackService(FakeRepo(p), ports)
    result = await svc.retract(
        acting_user_id=OWNER, project_id=PROJECT, proposal_id=p.proposal_id, book_id=BOOK,
        glossary_entity_id=None,
    )
    assert result.supplement_retracted == 0
    assert ports.supplement_deletes == []
    assert ports.retract_calls, "KG facts still soft-retracted"


# ── F-C13-1: API-LEVEL retract test (drives the real FastAPI handler) ───────────
# The QC found F-C13-1 was MASKED because every retract unit test called
# WritebackService.retract directly with a hand-supplied jwt the real handler
# never had. This test exercises the actual POST handler end-to-end (principal
# extraction + repo dep + ports) to prove retract works WITHOUT any JWT threading.


def _api_client(repo, ports):
    """A TestClient over just the proposals router, with the repo dep overridden
    and _make_ports patched to the fake (no live stack / DB)."""
    app = FastAPI()
    app.include_router(proposals_api.router)
    app.dependency_overrides[proposals_api.get_repo] = lambda: repo
    proposals_api._make_ports = lambda: ports  # type: ignore[attr-defined]
    return TestClient(app)


def _owner_bearer() -> str:
    """A bearer whose unverified `sub` is the book owner (the handler decodes sub
    without signature verification at this stage)."""
    return pyjwt.encode({"sub": str(OWNER)}, "irrelevant", algorithm="HS256")


@pytest.mark.asyncio
async def test_api_retract_soft_deletes_supplement_without_jwt_threading():
    """F-C13-1 capstone (unit): the real retract HANDLER soft-deletes the
    supplement and returns the supplement_retracted shape — proving retract no
    longer depends on a user JWT being threaded (the old structural dead-code)."""
    p = _proposal(
        status=ReviewStatus.PROMOTED,
        promoted_entity_id=GLOSS,
        promoted_by=OWNER,
        promoted_at=datetime.now(timezone.utc),
        original_technique="template",
    )
    p = replace(p, promoted_from_proposal_id=p.proposal_id)
    ports = FakePorts(owner=OWNER)
    client = _api_client(FakeRepo(p), ports)

    resp = client.post(
        f"/v1/lore-enrichment/proposals/{p.proposal_id}/retract",
        params={"project_id": str(PROJECT)},
        json={"book_id": str(BOOK), "glossary_entity_id": str(GLOSS)},
        headers={"Authorization": f"Bearer {_owner_bearer()}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["facts_retracted"] == 2
    assert body["supplement_retracted"] == 1
    assert "glossary_recycled" not in body, "the broken recycle flag is gone"
    # The supplement delete fired over the internal port (no JWT was threaded).
    assert ports.supplement_deletes and ports.supplement_deletes[0]["entity_id"] == GLOSS


@pytest.mark.asyncio
async def test_api_retract_non_owner_is_403():
    """The real handler rejects a non-owner principal (book-owner truth check)."""
    p = _proposal(status=ReviewStatus.PROMOTED, promoted_entity_id=GLOSS, promoted_by=OWNER,
                  promoted_at=datetime.now(timezone.utc), original_technique="template")
    p = replace(p, promoted_from_proposal_id=p.proposal_id)
    ports = FakePorts(owner=OWNER)
    client = _api_client(FakeRepo(p), ports)
    other_bearer = pyjwt.encode({"sub": str(OTHER)}, "irrelevant", algorithm="HS256")
    resp = client.post(
        f"/v1/lore-enrichment/proposals/{p.proposal_id}/retract",
        params={"project_id": str(PROJECT)},
        json={"book_id": str(BOOK), "glossary_entity_id": str(GLOSS)},
        headers={"Authorization": f"Bearer {other_bearer}"},
    )
    assert resp.status_code == 403, resp.text
    assert ports.supplement_deletes == []
