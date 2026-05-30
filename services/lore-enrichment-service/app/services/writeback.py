"""C13 — H0 write-back / promote / retract orchestration.

Ties the proposal repo (lifecycle) + the cross-service write ports (glossary
SSOT + KG quarantine) + the C12 canon-verify gate into the three author actions:

  * :meth:`write_back` — admit an APPROVED proposal's facts to the KG
    QUARANTINED (``source_type='enriched:<technique>'``, ``pending_validation=
    true``, ``confidence<1.0``). Runs C12 canon-verify FIRST (consistency
    annotation; never auto-rejects, never lifts quarantine). Writes the entity
    anchor through the glossary SSOT (Q2). NOT canon.
  * :meth:`promote` — author-only (the caller verified ownership). Writes back
    if not already, then flips the KG facts to canon (``source_type='glossary'``,
    ``confidence=1.0``, ``pending_validation=false``) RETAINING the permanent
    origin marker, and stamps the proposal row's promotion record. Idempotent.
  * :meth:`retract` — route the glossary entity to the recycle-bin (M6,
    reversible soft-delete) + soft-retract the KG facts (``valid_until``).

H0 INVARIANT (airtight): there is NO path here where an enriched proposal reaches
``source_type='glossary'`` / confidence=1.0 WITHOUT :meth:`promote`. write_back
always passes ``confidence<1.0`` + the enriched source_type to the KG port; the
KG endpoint clamps to <1.0 and forces ``pending_validation=true``. Only
:meth:`promote` calls the promote port.

DEFENSE-IN-DEPTH (deferred 050): the write ports neutralize all proposal/LLM text
as DATA before it crosses a service boundary; canon-verify also neutralizes
injection at write-back time. The verify result is folded into provenance but is
ANNOTATION only — it cannot canonize.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.clients.writeback import WritebackPorts, WrittenFact
from app.services.review import (
    ProposalRow,
    ProposalsRepo,
    ReviewStatus,
)

__all__ = [
    "WritebackResult",
    "PromoteResult",
    "RetractResult",
    "NotApprovedError",
    "NotOwnerError",
    "WritebackService",
]


class NotApprovedError(Exception):
    """Write-back / promote requested for a proposal not in ``approved``."""


class NotOwnerError(Exception):
    """Promote requested by a principal who is not the book/project owner (H0
    promotion authority — author-only)."""


@dataclass(frozen=True)
class WritebackResult:
    proposal: dict[str, Any]
    glossary_entity_id: str
    facts: list[WrittenFact]
    canon: bool  # always False — write-back is quarantined


@dataclass(frozen=True)
class PromoteResult:
    proposal: dict[str, Any]
    promoted_entity_id: str
    promoted_by: str
    promoted_at: str
    facts_promoted: int
    canon: bool  # always True after promote


@dataclass(frozen=True)
class RetractResult:
    proposal: dict[str, Any]
    facts_retracted: int
    glossary_recycled: bool


def _location_kind_code(entity_kind: str) -> str:
    """Map the enrichment entity_kind to a glossary kind_code. The demo enriches
    LOCATIONs; glossary's location kind code is 'location'."""
    return "location"


def _anchor_name(proposal: ProposalRow) -> str:
    """The NON-makeup identity used as the entity name / anchor / canonical_name.

    H0 (FIX-1 / WARN-1): enriched ``content`` must NEVER become a canon entity
    name. We resolve the faithful identity in strict order:

      1. ``target_ref`` — the canon entity the proposal enriches (demo path).
      2. ``canonical_name`` — the faithful entity name carried from the Gap
         (new-entity case where there is no pre-existing canon ref).
      3. ``proposal:{proposal_id}`` — a non-makeup SYNTHETIC identifier, used
         only when neither faithful name exists, so the anchor still has a stable
         identity that is provably NOT generated lore.

    ``content[:32]`` (makeup) is intentionally NOT a fallback — that was the leak.
    """
    name = (proposal.target_ref or "").strip() or (proposal.canonical_name or "").strip()
    if name:
        return name
    return f"proposal:{proposal.proposal_id}"


class WritebackService:
    def __init__(
        self,
        repo: ProposalsRepo,
        ports: WritebackPorts,
    ) -> None:
        self._repo = repo
        self._ports = ports

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _facts_from_proposal(proposal: ProposalRow) -> list[dict[str, Any]]:
        """Derive the enriched dimension facts from a proposal.

        A proposal's generated dimensions live in ``provenance_json['dimensions']``
        (dimension-label → content) when present; otherwise the whole ``content``
        is one fact under a generic dimension. Confidence is the proposal's
        (always <1.0) confidence — the H0 quarantine ceiling."""
        conf = float(proposal.confidence)
        dims = proposal.provenance_json.get("dimensions") if proposal.provenance_json else None
        facts: list[dict[str, Any]] = []
        if isinstance(dims, dict) and dims:
            for label, value in dims.items():
                if value:
                    facts.append(
                        {"dimension": str(label), "content": str(value),
                         "confidence": conf}
                    )
        if not facts:
            facts.append(
                {"dimension": "补充", "content": proposal.content, "confidence": conf}
            )
        return facts

    # ── write-back (quarantine) ────────────────────────────────────────────────

    async def write_back(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        proposal_id: UUID,
        book_id: UUID,
        glossary_entity_id: UUID | None = None,
        jwt: str = "",
        canon_verify=None,
    ) -> WritebackResult:
        """Admit an APPROVED proposal's facts to the KG QUARANTINED.

        Steps:
          1. Load the proposal (Q3-scoped). Must be ``approved``.
          2. Run C12 canon-verify (if provided) → fold annotation into provenance
             (consistency note; NEVER auto-rejects, NEVER lifts quarantine).
          3. Write the entity anchor through the glossary SSOT (Q2) → resolve
             glossary_entity_id if not supplied.
          4. Admit the dimension facts to the KG QUARANTINED via the KG port.

        Returns the (still non-canon) proposal + the written facts. H0: nothing
        here canonizes."""
        proposal = await self._repo.get(
            user_id=user_id, project_id=project_id, proposal_id=proposal_id
        )
        if proposal is None:
            raise LookupError("proposal not found")
        if proposal.review_status != ReviewStatus.APPROVED:
            raise NotApprovedError(
                f"proposal is '{proposal.review_status}', must be 'approved' to write back"
            )

        # 2. canon-verify annotation (optional; passed by the API). Annotation
        # only — does not gate the write nor lift quarantine (H0/C12 locked).
        if canon_verify is not None:
            await canon_verify(proposal)

        # 3. Glossary SSOT entity ANCHOR (Q2). H0: write only the entity IDENTITY
        # (name) — NEVER the enriched content. The makeup content stays in the
        # QUARANTINED KG facts until the author promotes; only :meth:`promote`
        # flows enriched content into the glossary canonical attributes. Writing
        # the content into a glossary attribute here would put makeup text onto a
        # canon entity before promotion — an H0 leak (self-adversary A1).
        kind_code = _location_kind_code(proposal.entity_kind)
        anchor_name = _anchor_name(proposal)  # H0: faithful identity, never makeup
        if glossary_entity_id is None:
            entity_id_str = await self._ports.write_entity_through_glossary(
                book_id=book_id,
                kind_code=kind_code,
                name=anchor_name,
                attributes={},  # identity only — no enriched content pre-promote
            )
            glossary_entity_id = UUID(entity_id_str)

        # 3b. Persist the resolved anchor id on the proposal row (FIX-3/NIT-3) so a
        # retract of a quarantined-never-promoted proposal can still locate it.
        # Best-effort: an audit-trail write must not fail the write-back itself.
        try:
            await self._repo.set_writeback_entity_id(
                user_id=user_id,
                project_id=project_id,
                proposal_id=proposal_id,
                writeback_entity_id=glossary_entity_id,
            )
        except Exception:  # noqa: BLE001 — anchor-id bookkeeping is non-fatal
            pass

        # 4. KG quarantine write (the H0 carrier). Always enriched, never canon.
        facts = self._facts_from_proposal(proposal)
        written = await self._ports.writeback_enriched_facts(
            user_id=user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            glossary_entity_id=glossary_entity_id,
            canonical_name=anchor_name,
            entity_kind=proposal.entity_kind,
            technique=proposal.technique,
            facts=facts,
        )
        return WritebackResult(
            proposal=proposal.as_dict(),
            glossary_entity_id=str(glossary_entity_id),
            facts=written,
            canon=False,
        )

    # ── promote (canonization — author-only) ────────────────────────────────────

    async def promote(
        self,
        *,
        acting_user_id: UUID | None,
        project_id: UUID,
        proposal_id: UUID,
        book_id: UUID,
        glossary_entity_id: UUID | None = None,
        jwt: str = "",
        canon_verify=None,
    ) -> PromoteResult:
        """Promote an approved proposal to canon. AUTHOR-ONLY.

        Authorization is decided against the book-service projection
        (``owner_user_id``) — the TRUTH source — NOT against a client claim. A
        non-owner (or anonymous) principal raises :class:`NotOwnerError` (→ 403).

        H0: this is the ONLY path that flips enriched → canon. It RETAINS the
        permanent origin marker (``promoted_from_proposal_id`` / ``promoted_by`` /
        ``promoted_at`` / ``original_technique``) on both the proposal row and the
        KG facts. Idempotent."""
        # 1. Author authorization against book-service truth.
        owner = await self._ports.book_owner(book_id=book_id)
        if acting_user_id is None or acting_user_id != owner.owner_user_id:
            raise NotOwnerError(
                "only the book/project owner may promote enriched lore to canon"
            )

        proposal = await self._repo.get(
            user_id=owner.owner_user_id, project_id=project_id, proposal_id=proposal_id
        )
        if proposal is None:
            raise LookupError("proposal not found")

        # Idempotent: already promoted → flip KG (no-op if already canon) + return.
        if proposal.review_status == ReviewStatus.PROMOTED:
            promoted_at = proposal.promoted_at or datetime.now(timezone.utc)
            n = await self._ports.promote_enriched_facts(
                user_id=owner.owner_user_id,
                proposal_id=proposal_id,
                promoted_by=owner.owner_user_id,
                promoted_at=promoted_at,
            )
            return PromoteResult(
                proposal=proposal.as_dict(),
                promoted_entity_id=str(proposal.promoted_entity_id or ""),
                promoted_by=str(proposal.promoted_by or owner.owner_user_id),
                promoted_at=promoted_at.isoformat(),
                facts_promoted=n,
                canon=True,
            )

        if proposal.review_status != ReviewStatus.APPROVED:
            raise NotApprovedError(
                f"proposal is '{proposal.review_status}', must be 'approved' to promote"
            )

        # 2. Ensure the facts are written back (quarantined) first.
        wb = await self.write_back(
            user_id=owner.owner_user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            book_id=book_id,
            glossary_entity_id=glossary_entity_id,
            jwt=jwt,
            canon_verify=canon_verify,
        )
        resolved_entity_id = UUID(wb.glossary_entity_id)

        # 3. Stamp the proposal row's promotion record (DB trigger enforces the
        # promote-only invariant + permanent origin markers).
        promoted_at = datetime.now(timezone.utc)
        updated = await self._repo.mark_promoted(
            user_id=owner.owner_user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            promoted_entity_id=resolved_entity_id,
            promoted_by=owner.owner_user_id,
            promoted_at=promoted_at,
        )

        # 4. Flip the KG facts to canon RETAINING the origin marker.
        n = await self._ports.promote_enriched_facts(
            user_id=owner.owner_user_id,
            proposal_id=proposal_id,
            promoted_by=owner.owner_user_id,
            promoted_at=promoted_at,
        )

        # 5. NOW (and only now) the content is canon — flow it into the glossary
        # entity's CANONICAL content through the SSOT (Q2 / DEFERRED-053).
        # Pre-promote, write-back wrote only the entity identity (quarantine);
        # this is the point makeup legitimately becomes authored canon.
        #
        # We set the glossary ``short_description`` COLUMN on the resolved
        # entity via the internal canon-content endpoint — NOT extract-entities,
        # which silently no-ops on short_description (it is a column, not an EAV
        # attribute_definition). glossary_sync (C4) then propagates this content
        # to Neo4j as source_type='glossary' canon, keeping the KG entity anchor
        # consistent with the glossary SSOT. The per-dimension KG facts promoted
        # in step 4 carry the structured dimensions; the short_description is the
        # canonical summary — complementary, never divergent.
        try:
            await self._ports.set_glossary_canon_content(
                book_id=book_id,
                entity_id=resolved_entity_id,
                short_description=proposal.content[:480],
            )
        except Exception:  # noqa: BLE001 — content sync is best-effort post-promote
            # The canon state already holds in the KG + proposal row; a glossary
            # content write hiccup must not unwind a successful promotion. The
            # glossary entity_updated reconciler / a re-promote re-converges it.
            pass

        return PromoteResult(
            proposal=updated.as_dict(),
            promoted_entity_id=str(resolved_entity_id),
            promoted_by=str(owner.owner_user_id),
            promoted_at=promoted_at.isoformat(),
            facts_promoted=n,
            canon=True,
        )

    # ── retract (M6 recycle-bin) ────────────────────────────────────────────────

    async def retract(
        self,
        *,
        acting_user_id: UUID | None,
        project_id: UUID,
        proposal_id: UUID,
        book_id: UUID,
        glossary_entity_id: UUID | None,
        jwt: str = "",
    ) -> RetractResult:
        """Retract a promoted/quarantined proposal (reversible).

        Author-only (same truth-source check as promote). Routes the glossary
        entity to the recycle-bin (M6 soft-delete) and soft-retracts the KG facts
        (``valid_until``). The proposal row records the retraction note."""
        owner = await self._ports.book_owner(book_id=book_id)
        if acting_user_id is None or acting_user_id != owner.owner_user_id:
            raise NotOwnerError("only the book/project owner may retract")

        proposal = await self._repo.get(
            user_id=owner.owner_user_id, project_id=project_id, proposal_id=proposal_id
        )
        if proposal is None:
            raise LookupError("proposal not found")

        # KG side: soft-retract the enriched facts (reversible).
        n = await self._ports.retract_enriched_facts(
            user_id=owner.owner_user_id, proposal_id=proposal_id
        )

        # Glossary side: recycle-bin the entity anchor (reversible). Resolve which
        # entity to recycle in order of authority: an explicitly-supplied id, the
        # promotion record, then the write-back anchor id persisted at write-back
        # time (FIX-3/NIT-3) — the last covers a quarantined-never-promoted
        # proposal, whose anchor would otherwise be orphaned.
        recycle_target = (
            glossary_entity_id
            or proposal.promoted_entity_id
            or proposal.writeback_entity_id
        )
        recycled = False
        if recycle_target is not None and jwt:
            recycled = await self._ports.soft_delete_glossary_entity(
                book_id=book_id, entity_id=recycle_target, jwt=jwt
            )

        updated = await self._repo.mark_retracted(
            user_id=owner.owner_user_id, project_id=project_id, proposal_id=proposal_id
        )
        return RetractResult(
            proposal=updated.as_dict(),
            facts_retracted=n,
            glossary_recycled=recycled,
        )
