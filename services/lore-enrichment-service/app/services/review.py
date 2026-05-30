"""C13 — proposal review repository + lifecycle state machine.

The review gate mirrors knowledge-service ``pending_facts`` (Q1): list / approve
(≈confirm) / reject / edit, PLUS the H0 author-only ``promote`` and a ``retract``.

LIFECYCLE (the C2 DAG — enforced here AND by the DB trigger, defence-in-depth):

    proposed         → author_reviewing | rejected
    author_reviewing → approved | rejected | proposed
    approved         → promoted | rejected | author_reviewing
    promoted         → (terminal — only retraction touches it, via valid_until)
    rejected         → (terminal)

H0 boundaries enforced here:
  * approve moves to ``approved`` but NEVER touches ``source_type`` / ``confidence``
    / ``pending_validation`` — it is NOT canonization.
  * the ONLY transition to ``promoted`` is via :meth:`mark_promoted`, which the
    promote handler calls AFTER the author check + write-back. The promote write
    stamps ``promoted_entity_id/by/at`` + the permanent origin markers
    (``promoted_from_proposal_id`` / ``original_technique``); the DB trigger
    rejects a ``promoted`` row without them.
  * every method filters on ``user_id`` + ``project_id`` (Q3 scoping) so a
    cross-scope caller sees None (→ 404, no existence oracle), mirroring
    pending_facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

__all__ = [
    "ReviewStatus",
    "IllegalTransitionError",
    "ProposalRow",
    "ProposalsRepo",
    "LEGAL_TRANSITIONS",
]


# ── Lifecycle DAG (single source of truth, mirrors the C2 SQL trigger) ──────────
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"author_reviewing", "rejected"}),
    "author_reviewing": frozenset({"approved", "rejected", "proposed"}),
    "approved": frozenset({"promoted", "rejected", "author_reviewing"}),
    "promoted": frozenset(),
    "rejected": frozenset(),
}


class ReviewStatus(str):
    PROPOSED = "proposed"
    AUTHOR_REVIEWING = "author_reviewing"
    APPROVED = "approved"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class IllegalTransitionError(ValueError):
    """A requested review_status transition is not in the legal DAG."""

    def __init__(self, frm: str, to: str) -> None:
        super().__init__(f"illegal review_status transition {frm} -> {to}")
        self.frm = frm
        self.to = to


def can_transition(frm: str, to: str) -> bool:
    return to in LEGAL_TRANSITIONS.get(frm, frozenset())


@dataclass(frozen=True)
class ProposalRow:
    proposal_id: UUID
    job_id: UUID
    project_id: UUID
    user_id: UUID
    entity_kind: str
    target_ref: str | None
    canonical_name: str | None
    content: str
    origin: str
    technique: str
    provenance_json: dict[str, Any]
    confidence: float
    source_refs_json: list[Any]
    cultural_grounding_ref_id: UUID | None
    review_status: str
    writeback_entity_id: UUID | None
    promoted_entity_id: UUID | None
    promoted_by: UUID | None
    promoted_at: datetime | None
    promoted_from_proposal_id: UUID | None
    original_technique: str | None
    rejected_reason: str | None
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable shape matching the OpenAPI EnrichmentProposal."""
        return {
            "proposal_id": str(self.proposal_id),
            "job_id": str(self.job_id),
            "project_id": str(self.project_id),
            "user_id": str(self.user_id),
            "entity_kind": self.entity_kind,
            "target_ref": self.target_ref,
            "canonical_name": self.canonical_name,
            "content": self.content,
            "origin": self.origin,
            "technique": self.technique,
            "provenance_json": self.provenance_json,
            "confidence": float(self.confidence),
            "source_refs_json": self.source_refs_json,
            "cultural_grounding_ref_id": (
                str(self.cultural_grounding_ref_id)
                if self.cultural_grounding_ref_id else None
            ),
            "review_status": self.review_status,
            "writeback_entity_id": (
                str(self.writeback_entity_id) if self.writeback_entity_id else None
            ),
            "promoted_entity_id": (
                str(self.promoted_entity_id) if self.promoted_entity_id else None
            ),
            "promoted_by": str(self.promoted_by) if self.promoted_by else None,
            "promoted_at": (
                self.promoted_at.isoformat() if self.promoted_at else None
            ),
            "promoted_from_proposal_id": (
                str(self.promoted_from_proposal_id)
                if self.promoted_from_proposal_id else None
            ),
            "original_technique": self.original_technique,
            "rejected_reason": self.rejected_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


_COLS = """
  proposal_id, job_id, project_id, user_id, entity_kind, target_ref,
  canonical_name, content, origin, technique, provenance_json, confidence,
  source_refs_json, cultural_grounding_ref_id, review_status,
  writeback_entity_id, promoted_entity_id, promoted_by, promoted_at,
  promoted_from_proposal_id, original_technique, rejected_reason,
  created_at, updated_at
"""


def _row(r: asyncpg.Record) -> ProposalRow:
    import json

    def _json(v: Any, default: Any) -> Any:
        if v is None:
            return default
        if isinstance(v, (dict, list)):
            return v
        return json.loads(v)

    return ProposalRow(
        proposal_id=r["proposal_id"],
        job_id=r["job_id"],
        project_id=r["project_id"],
        user_id=r["user_id"],
        entity_kind=r["entity_kind"],
        target_ref=r["target_ref"],
        canonical_name=r["canonical_name"],
        content=r["content"],
        origin=r["origin"],
        technique=r["technique"],
        provenance_json=_json(r["provenance_json"], {}),
        confidence=float(r["confidence"]),
        source_refs_json=_json(r["source_refs_json"], []),
        cultural_grounding_ref_id=r["cultural_grounding_ref_id"],
        review_status=r["review_status"],
        writeback_entity_id=r["writeback_entity_id"],
        promoted_entity_id=r["promoted_entity_id"],
        promoted_by=r["promoted_by"],
        promoted_at=r["promoted_at"],
        promoted_from_proposal_id=r["promoted_from_proposal_id"],
        original_technique=r["original_technique"],
        rejected_reason=r["rejected_reason"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class ProposalsRepo:
    """Per-user/per-project (Q3) proposal store. Every read/write filters on
    ``user_id`` so a cross-user caller gets None (→ 404 at the router)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        review_status: str | None = None,
        job_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ProposalRow], int]:
        params: list[Any] = [user_id, project_id]
        preds = ["user_id = $1", "project_id = $2"]
        if review_status is not None:
            params.append(review_status)
            preds.append(f"review_status = ${len(params)}")
        if job_id is not None:
            params.append(job_id)
            preds.append(f"job_id = ${len(params)}")
        where = " AND ".join(preds)
        async with self._pool.acquire() as conn:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM enrichment_proposal WHERE {where}", *params
            )
            rows = await conn.fetch(
                f"""SELECT {_COLS} FROM enrichment_proposal WHERE {where}
                    ORDER BY created_at DESC, proposal_id DESC
                    LIMIT ${len(params)+1} OFFSET ${len(params)+2}""",
                *params, limit, offset,
            )
        return [_row(r) for r in rows], int(total or 0)

    async def get(
        self, *, user_id: UUID, project_id: UUID, proposal_id: UUID
    ) -> ProposalRow | None:
        async with self._pool.acquire() as conn:
            r = await conn.fetchrow(
                f"""SELECT {_COLS} FROM enrichment_proposal
                    WHERE user_id = $1 AND project_id = $2 AND proposal_id = $3""",
                user_id, project_id, proposal_id,
            )
        return _row(r) if r else None

    async def set_status(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        proposal_id: UUID,
        to_status: str,
        rejected_reason: str | None = None,
    ) -> ProposalRow:
        """Transition review_status (NON-promote states only). Validates the DAG
        in-app before the DB trigger does, so an illegal jump is a clean 409 not
        a raw asyncpg error. NEVER touches the canon-distinguishing columns."""
        current = await self.get(
            user_id=user_id, project_id=project_id, proposal_id=proposal_id
        )
        if current is None:
            raise LookupError("proposal not found")
        if to_status == ReviewStatus.PROMOTED:
            raise IllegalTransitionError(current.review_status, to_status)
        if not can_transition(current.review_status, to_status):
            raise IllegalTransitionError(current.review_status, to_status)
        async with self._pool.acquire() as conn:
            r = await conn.fetchrow(
                f"""UPDATE enrichment_proposal
                    SET review_status = $4,
                        rejected_reason = COALESCE($5, rejected_reason)
                    WHERE user_id = $1 AND project_id = $2 AND proposal_id = $3
                    RETURNING {_COLS}""",
                user_id, project_id, proposal_id, to_status, rejected_reason,
            )
        return _row(r)

    async def edit_content(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        proposal_id: UUID,
        content: str,
    ) -> ProposalRow:
        """Author edits the makeup content before promotion. NEVER changes
        origin / confidence / review_status — still enriched, still non-canon.
        Only editable while not yet terminal (rejected/promoted → 409)."""
        current = await self.get(
            user_id=user_id, project_id=project_id, proposal_id=proposal_id
        )
        if current is None:
            raise LookupError("proposal not found")
        if current.review_status in (ReviewStatus.PROMOTED, ReviewStatus.REJECTED):
            raise IllegalTransitionError(current.review_status, "edit")
        async with self._pool.acquire() as conn:
            r = await conn.fetchrow(
                f"""UPDATE enrichment_proposal
                    SET content = $4
                    WHERE user_id = $1 AND project_id = $2 AND proposal_id = $3
                    RETURNING {_COLS}""",
                user_id, project_id, proposal_id, content,
            )
        return _row(r)

    async def mark_promoted(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        proposal_id: UUID,
        promoted_entity_id: UUID,
        promoted_by: UUID,
        promoted_at: datetime,
    ) -> ProposalRow:
        """The ONLY path to ``review_status='promoted'`` (H0). Requires the
        proposal be in ``approved`` (else 409 via IllegalTransitionError). Stamps
        the promotion record + permanent origin markers; the DB trigger also
        enforces that promoted rows carry promoted_entity_id/by/at.

        Idempotent: a re-call when already ``promoted`` with the SAME
        promoted_entity_id is a no-op returning the current row (no duplicate
        canon)."""
        current = await self.get(
            user_id=user_id, project_id=project_id, proposal_id=proposal_id
        )
        if current is None:
            raise LookupError("proposal not found")
        if current.review_status == ReviewStatus.PROMOTED:
            # Idempotent re-promote: same entity → no-op; different → conflict.
            if current.promoted_entity_id == promoted_entity_id:
                return current
            raise IllegalTransitionError(current.review_status, "promoted")
        if current.review_status != ReviewStatus.APPROVED:
            raise IllegalTransitionError(current.review_status, "promoted")
        async with self._pool.acquire() as conn:
            r = await conn.fetchrow(
                f"""UPDATE enrichment_proposal
                    SET review_status = 'promoted',
                        promoted_entity_id = $4,
                        promoted_by = $5,
                        promoted_at = $6,
                        promoted_from_proposal_id = proposal_id,
                        original_technique = technique
                    WHERE user_id = $1 AND project_id = $2 AND proposal_id = $3
                    RETURNING {_COLS}""",
                user_id, project_id, proposal_id,
                promoted_entity_id, promoted_by, promoted_at,
            )
        return _row(r)

    async def set_writeback_entity_id(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        proposal_id: UUID,
        writeback_entity_id: UUID,
    ) -> ProposalRow:
        """Persist the glossary anchor id resolved at write-back time (FIX-3).

        This is NOT the promotion record (that is trigger-guarded and may only be
        set at promote) — it records WHICH glossary entity the quarantined facts
        anchored on, so a retract of a quarantined-never-promoted proposal can
        still locate + recycle the anchor. Idempotent: only fills when empty (the
        first write-back wins; re-writes keep the original anchor)."""
        async with self._pool.acquire() as conn:
            r = await conn.fetchrow(
                f"""UPDATE enrichment_proposal
                    SET writeback_entity_id = COALESCE(writeback_entity_id, $4)
                    WHERE user_id = $1 AND project_id = $2 AND proposal_id = $3
                    RETURNING {_COLS}""",
                user_id, project_id, proposal_id, writeback_entity_id,
            )
        if r is None:
            raise LookupError("proposal not found")
        return _row(r)

    async def mark_retracted(
        self, *, user_id: UUID, project_id: UUID, proposal_id: UUID
    ) -> ProposalRow:
        """Record retraction in the proposal's ``rejected_reason`` (audit) — the
        actual reversible removal happens in glossary recycle-bin + KG
        valid_until. A promoted proposal stays ``promoted`` (its canon was
        retracted, not the lifecycle); a non-promoted approved one is rejected.

        We do NOT invent a new lifecycle state (the C2 DAG is locked); retraction
        is recorded as an annotation so the row remains queryable."""
        current = await self.get(
            user_id=user_id, project_id=project_id, proposal_id=proposal_id
        )
        if current is None:
            raise LookupError("proposal not found")
        note = "retracted: routed to glossary recycle-bin (reversible)"
        async with self._pool.acquire() as conn:
            r = await conn.fetchrow(
                f"""UPDATE enrichment_proposal
                    SET rejected_reason = $4
                    WHERE user_id = $1 AND project_id = $2 AND proposal_id = $3
                    RETURNING {_COLS}""",
                user_id, project_id, proposal_id, note,
            )
        return _row(r)
