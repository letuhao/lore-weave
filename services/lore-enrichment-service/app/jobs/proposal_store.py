"""Job + proposal PERSISTENCE for the C14 runner (the INSERT path).

C13 (``app.services.review.ProposalsRepo``) owns proposal READS + lifecycle
TRANSITIONS but never CREATES a job or a proposal — generation/orchestration
(C14) is where rows are first written. This module is that write seam:

  * :meth:`create_job` inserts one ``enrichment_job`` row (status='pending', the
    C8 state-machine entry state) and returns its id.
  * :meth:`persist_proposal` inserts one ``enrichment_proposal`` row from a C11
    generation result + the C12 verify annotation. **H0 BY CONSTRUCTION**: the
    insert always writes ``origin='enrichment'`` (≠ glossary), ``confidence<1.0``,
    ``review_status='proposed'``, and folds the generated dimensions under
    ``provenance_json['dimensions']`` + the verify annotation under
    ``provenance_json['canon_verify']`` — never a canon marker. The DB CHECK +
    H0 trigger are the backstop; this seam never even attempts a canon write.

A :class:`PgProposalStore` writes to the real Postgres (asyncpg). An in-memory
:class:`InMemoryProposalStore` lets the runner unit tests exercise the full
orchestration with no DB (the persisted shape is asserted on the captured rows).

Boundaries: NO model names, NO cross-service writes (that is C13 write-back), NO
LLM/HTTP. Pure persistence of already-generated, already-verified proposals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg

from app.generation.provenance import EnrichedFact
from app.verify.wiring import AnnotatedVerify

__all__ = [
    "PersistedProposal",
    "ProposalStore",
    "PgProposalStore",
    "InMemoryProposalStore",
    "build_proposal_fields",
]


@dataclass(frozen=True)
class PersistedProposal:
    """The identity + H0 markers of a persisted proposal (insert result).

    ``deduped`` is True when this row already existed (a resume/re-run hit the
    per-gap UNIQUE(job_id, gap_ref) and the existing row was reloaded instead of
    a new insert) — the runner uses it to avoid double-counting on resume."""

    proposal_id: str
    job_id: str
    canonical_name: str
    origin: str
    technique: str
    review_status: str
    confidence: float
    pending_validation: bool
    dimensions: dict[str, str]
    deduped: bool = False


def _dimensions_from_facts(facts: list[EnrichedFact]) -> dict[str, str]:
    """Collapse C11 enriched facts into a {dimension-label: content} map (the
    generated lore, keyed by its Chinese dimension). Insertion order preserved
    (C6 declaration order from the generator)."""
    return {f.dimension: f.content for f in facts}


def _content_from_facts(canonical_name: str, facts: list[EnrichedFact]) -> str:
    """Render the proposal ``content`` text from the generated facts — a
    human-readable Chinese summary, one line per dimension. The structured map
    lives in provenance; this is the display/edit surface (what C13 edit/write-back
    treats as the proposal body)."""
    lines = [f"{f.dimension}：{f.content}" for f in facts]
    return f"「{canonical_name}」补全：\n" + "\n".join(lines)


def build_proposal_fields(
    *,
    user_id: str,
    project_id: str,
    entity_kind: str,
    canonical_name: str,
    target_ref: str | None,
    technique: str,
    confidence: float,
    facts: list[EnrichedFact],
    verify: AnnotatedVerify | None,
    source_refs: list[dict[str, Any]],
    base_provenance: dict[str, Any] | None = None,
    gap_ref: str | None = None,
) -> dict[str, Any]:
    """Assemble the H0-safe column values for one ``enrichment_proposal`` insert.

    Shared by both the Pg + in-memory stores so the persisted shape is identical.
    H0 enforced here: origin fixed to 'enrichment', review_status to 'proposed',
    confidence passed through (the generator already constrains it < 1.0; the DB
    CHECK is the backstop). The generated dimensions + verify annotation are
    folded into provenance_json (annotation only — never a canon marker).
    """
    if not 0.0 < confidence < 1.0:
        # Defensive: the H0 carrier can never hold canon confidence. Refuse to
        # build a row that the DB CHECK would reject anyway (fail loud, early).
        raise ValueError(
            f"H0 violation: proposal confidence must be in (0, 1.0), got {confidence}"
        )
    dimensions = _dimensions_from_facts(facts)
    provenance: dict[str, Any] = dict(base_provenance or {})
    provenance["technique"] = technique
    provenance["dimensions"] = dimensions
    if verify is not None:
        # Verify annotation (C12) — consistency note, NOT a canon admission.
        provenance.update(verify.provenance_patch)
    return {
        "user_id": user_id,
        "project_id": project_id,
        "entity_kind": entity_kind,
        "target_ref": target_ref,
        # The per-gap dedupe key (target_ref or canonical_name): UNIQUE(job_id,
        # gap_ref) makes a re-run idempotent (WARN-1). Falls back to the
        # canonical_name when there is no target_ref (a faithful identity, never
        # makeup content).
        "gap_ref": gap_ref or target_ref or canonical_name,
        "canonical_name": canonical_name,
        "content": _content_from_facts(canonical_name, facts),
        "origin": "enrichment",  # H0: never 'glossary'
        "technique": technique,
        "provenance_json": provenance,
        "confidence": confidence,  # H0: < 1.0 (checked above + DB CHECK)
        "source_refs_json": source_refs,
        "review_status": "proposed",  # H0: lifecycle entry, never canon
        "pending_validation": True,
    }


class ProposalStore(Protocol):
    """The persistence seam the runner needs."""

    async def create_job(
        self,
        *,
        user_id: str,
        project_id: str,
        technique: str,
        entity_kind: str | None,
        max_spend: float | None,
        estimated_cost: float,
    ) -> str: ...

    async def persist_proposal(
        self, *, job_id: str, fields: dict[str, Any]
    ) -> PersistedProposal: ...

    async def mark_job_status(
        self,
        *,
        job_id: str,
        status: str,
        actual_cost: float | None = None,
        proposals_total: int | None = None,
        error_message: str | None = None,
    ) -> None: ...


class PgProposalStore:
    """asyncpg-backed :class:`ProposalStore` writing the real C2 tables."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_job(
        self,
        *,
        user_id: str,
        project_id: str,
        technique: str,
        entity_kind: str | None,
        max_spend: float | None,
        estimated_cost: float,
    ) -> str:
        async with self._pool.acquire() as conn:
            job_id = await conn.fetchval(
                """INSERT INTO enrichment_job
                     (project_id, user_id, technique, entity_kind, status,
                      max_spend_usd, estimated_cost_usd)
                   VALUES ($1,$2,$3,$4,'pending',$5,$6)
                   RETURNING job_id""",
                UUID(project_id), UUID(user_id), technique, entity_kind,
                max_spend, estimated_cost,
            )
        return str(job_id)

    async def persist_proposal(
        self, *, job_id: str, fields: dict[str, Any]
    ) -> PersistedProposal:
        """Insert one proposal, IDEMPOTENT per (job_id, gap_ref) (WARN-1).

        ON CONFLICT DO NOTHING against the UNIQUE(job_id, gap_ref) index makes a
        resume/re-run that re-processes an already-persisted gap a no-op: the
        existing row is reloaded (``deduped=True``) instead of inserting a
        duplicate. So a re-run can never DUPLICATE proposals."""
        gap_ref = fields["gap_ref"]
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO enrichment_proposal
                     (job_id, project_id, user_id, entity_kind, target_ref,
                      gap_ref, canonical_name, content, origin, technique,
                      provenance_json, confidence, source_refs_json, review_status)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13::jsonb,$14)
                   ON CONFLICT (job_id, gap_ref) WHERE gap_ref IS NOT NULL
                     DO NOTHING
                   RETURNING proposal_id""",
                UUID(job_id), UUID(fields["project_id"]), UUID(fields["user_id"]),
                fields["entity_kind"], fields["target_ref"], gap_ref,
                fields["canonical_name"],
                fields["content"], fields["origin"], fields["technique"],
                json.dumps(fields["provenance_json"], ensure_ascii=False),
                fields["confidence"],
                json.dumps(fields["source_refs_json"], ensure_ascii=False),
                fields["review_status"],
            )
            deduped = row is None
            if deduped:
                # The gap already has a proposal for this job — reload it (the
                # ON CONFLICT skipped the insert). Idempotent: no duplicate row.
                row = await conn.fetchrow(
                    """SELECT proposal_id FROM enrichment_proposal
                       WHERE job_id = $1 AND gap_ref = $2""",
                    UUID(job_id), gap_ref,
                )
        return PersistedProposal(
            proposal_id=str(row["proposal_id"]),
            job_id=job_id,
            canonical_name=fields["canonical_name"],
            origin=fields["origin"],
            technique=fields["technique"],
            review_status=fields["review_status"],
            confidence=float(fields["confidence"]),
            pending_validation=bool(fields["pending_validation"]),
            dimensions=dict(fields["provenance_json"].get("dimensions", {})),
            deduped=deduped,
        )

    async def mark_job_status(
        self,
        *,
        job_id: str,
        status: str,
        actual_cost: float | None = None,
        proposals_total: int | None = None,
        error_message: str | None = None,
    ) -> None:
        sets = ["status = $2"]
        params: list[Any] = [UUID(job_id), status]
        if actual_cost is not None:
            params.append(actual_cost)
            sets.append(f"actual_cost_usd = ${len(params)}")
        if proposals_total is not None:
            params.append(proposals_total)
            sets.append(f"proposals_total = ${len(params)}")
        if error_message is not None:
            params.append(error_message)
            sets.append(f"error_message = ${len(params)}")
        sets.append("updated_at = now()")
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"UPDATE enrichment_job SET {', '.join(sets)} WHERE job_id = $1",
                *params,
            )


@dataclass
class InMemoryProposalStore:
    """In-memory :class:`ProposalStore` for runner unit tests (no DB).

    Captures created jobs + persisted proposals so a test can assert the full
    orchestration emitted the right H0-stamped rows without a Postgres."""

    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    proposals: list[PersistedProposal] = field(default_factory=list)
    raw_fields: list[dict[str, Any]] = field(default_factory=list)
    #: (job_id, gap_ref) → proposal_id of an already-persisted gap (dedupe).
    _by_gap: dict[tuple[str, str], str] = field(default_factory=dict)

    async def create_job(
        self,
        *,
        user_id: str,
        project_id: str,
        technique: str,
        entity_kind: str | None,
        max_spend: float | None,
        estimated_cost: float,
    ) -> str:
        job_id = str(uuid4())
        self.jobs[job_id] = {
            "user_id": user_id,
            "project_id": project_id,
            "technique": technique,
            "entity_kind": entity_kind,
            "max_spend": max_spend,
            "estimated_cost": estimated_cost,
            "status": "pending",
        }
        return job_id

    async def persist_proposal(
        self, *, job_id: str, fields: dict[str, Any]
    ) -> PersistedProposal:
        # Mirror the Pg UNIQUE(job_id, gap_ref) idempotency (WARN-1): a re-run
        # that re-persists a gap reloads the existing proposal (deduped=True)
        # instead of appending a duplicate.
        gap_ref = fields["gap_ref"]
        existing_id = self._by_gap.get((job_id, gap_ref)) if gap_ref else None
        if existing_id is not None:
            for prior in self.proposals:
                if prior.proposal_id == existing_id:
                    return PersistedProposal(
                        proposal_id=prior.proposal_id,
                        job_id=prior.job_id,
                        canonical_name=prior.canonical_name,
                        origin=prior.origin,
                        technique=prior.technique,
                        review_status=prior.review_status,
                        confidence=prior.confidence,
                        pending_validation=prior.pending_validation,
                        dimensions=dict(prior.dimensions),
                        deduped=True,
                    )
        self.raw_fields.append(fields)
        p = PersistedProposal(
            proposal_id=str(uuid4()),
            job_id=job_id,
            canonical_name=fields["canonical_name"],
            origin=fields["origin"],
            technique=fields["technique"],
            review_status=fields["review_status"],
            confidence=float(fields["confidence"]),
            pending_validation=bool(fields["pending_validation"]),
            dimensions=dict(fields["provenance_json"].get("dimensions", {})),
        )
        self.proposals.append(p)
        if gap_ref:
            self._by_gap[(job_id, gap_ref)] = p.proposal_id
        return p

    async def mark_job_status(
        self,
        *,
        job_id: str,
        status: str,
        actual_cost: float | None = None,
        proposals_total: int | None = None,
        error_message: str | None = None,
    ) -> None:
        job = self.jobs.setdefault(job_id, {})
        job["status"] = status
        if actual_cost is not None:
            job["actual_cost"] = actual_cost
        if proposals_total is not None:
            job["proposals_total"] = proposals_total
        if error_message is not None:
            job["error_message"] = error_message
