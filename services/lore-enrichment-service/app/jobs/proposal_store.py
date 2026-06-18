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
from loreweave_jobs import emit_job_event

from app.gaps.model import is_zh
from app.generation.provenance import EnrichedFact
from app.jobs.job_events import JOB_KIND, JOB_SERVICE, canonical_status, job_error
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
    rejected_reason: str | None = None


def _dimensions_from_facts(facts: list[EnrichedFact]) -> dict[str, str]:
    """Collapse C11 enriched facts into a {dimension-label: content} map (the
    generated lore, keyed by its Chinese dimension). Insertion order preserved
    (C6 declaration order from the generator)."""
    return {f.dimension: f.content for f in facts}


def _content_from_facts(
    canonical_name: str, facts: list[EnrichedFact], *, language: str = "zh"
) -> str:
    """Render the proposal ``content`` text from the generated facts — a
    human-readable summary, one line per dimension. The structured map lives in
    provenance; this is the display/edit surface (what C13 edit/write-back treats as
    the proposal body).

    De-bias (LE-PROD-2 P2): the header + the label separator are LANGUAGE-AWARE so a
    non-Chinese book's proposal body isn't a zh-flavored '「name」补全：' with fullwidth
    colons. ``language`` defaults to ``zh`` (the Fengshen demo — no regression); the
    runner passes the per-book profile language."""
    if is_zh(language):
        lines = [f"{f.dimension}：{f.content}" for f in facts]
        return f"「{canonical_name}」补全：\n" + "\n".join(lines)
    lines = [f"{f.dimension}: {f.content}" for f in facts]
    return f"{canonical_name} — enrichment:\n" + "\n".join(lines)


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
    review_status: str = "proposed",
    rejected_reason: str | None = None,
    language: str = "zh",
) -> dict[str, Any]:
    """Assemble the H0-safe column values for one ``enrichment_proposal`` insert.

    Shared by both the Pg + in-memory stores so the persisted shape is identical.
    H0 enforced here: origin fixed to 'enrichment', confidence passed through (the
    generator already constrains it < 1.0; the DB CHECK is the backstop). The
    generated dimensions + verify annotation are folded into provenance_json
    (annotation only — never a canon marker).

    ``review_status`` defaults to ``'proposed'`` (the H0 lifecycle entry). C3
    auto-reject passes ``'rejected'`` + a ``rejected_reason`` to persist an
    egregious proposal as a terminal, audited, NEVER-surfaced row — this is still
    NOT canon (rejected is suppression, not promotion; origin stays 'enrichment',
    confidence < 1.0, pending_validation True). The DB transition trigger guards
    UPDATEs only, so a direct INSERT at 'rejected' (in the CHECK vocabulary) is
    legal.
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
        "content": _content_from_facts(canonical_name, facts, language=language),
        "origin": "enrichment",  # H0: never 'glossary'
        "technique": technique,
        "provenance_json": provenance,
        "confidence": confidence,  # H0: < 1.0 (checked above + DB CHECK)
        "source_refs_json": source_refs,
        # H0: 'proposed' lifecycle entry by default; 'rejected' (C3 auto-reject)
        # is terminal suppression, still never canon. Insert-time only — a real
        # status TRANSITION still goes through the DB trigger.
        "review_status": review_status,
        "rejected_reason": rejected_reason,
        "pending_validation": True,
    }


class ProposalStore(Protocol):
    """The persistence seam the runner needs."""

    async def create_job(
        self,
        *,
        user_id: str,
        project_id: str,
        book_id: str | None = None,
        technique: str,
        entity_kind: str | None,
        max_spend: float | None,
        estimated_cost: float,
        model_name: str | None = None,
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
        only_if_status: tuple[str, ...] | None = None,
    ) -> bool: ...

    async def read_job_status(self, *, job_id: str) -> str | None: ...


class PgProposalStore:
    """asyncpg-backed :class:`ProposalStore` writing the real C2 tables."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_job(
        self,
        *,
        user_id: str,
        project_id: str,
        book_id: str | None = None,
        technique: str,
        entity_kind: str | None,
        max_spend: float | None,
        estimated_cost: float,
        model_name: str | None = None,
    ) -> str:
        async with self._pool.acquire() as conn:
            async with conn.transaction():  # INSERT + emit_job_event atomic (H1)
                job_id = await conn.fetchval(
                    """INSERT INTO enrichment_job
                         (project_id, user_id, book_id, technique, entity_kind, status,
                          max_spend_usd, estimated_cost_usd)
                       VALUES ($1,$2,$3,$4,$5,'pending',$6,$7)
                       RETURNING job_id""",
                    UUID(project_id), UUID(user_id),
                    UUID(book_id) if book_id else None,
                    technique, entity_kind,
                    max_spend, estimated_cost,
                )
                # Unified Job Control Plane P1 — emit the initial 'pending' lifecycle
                # event on the SAME conn as the INSERT (genuinely-new row only).
                await emit_job_event(
                    conn, service=JOB_SERVICE, job_id=str(job_id),
                    owner_user_id=str(user_id), kind=JOB_KIND, status="pending",
                    # P4 — NO actual spend yet at create (cost_usd is ACTUAL spend, set
                    # from actual_cost_usd on transitions); the estimate rides params so
                    # it is still visible without masquerading as spend. D-JOBS-P4-LORE-MODEL:
                    # the model NAME is resolved OUT-OF-TX by the caller (the ref lives in a
                    # separate enrichment_job_request row) and passed in; emitted ONLY here
                    # on create — the projection's COALESCE keeps it across status events.
                    cost_usd=None,
                    model=model_name,
                    params={
                        "technique": technique,
                        "entity_kind": entity_kind,
                        "max_spend_usd": float(max_spend) if max_spend is not None else None,
                        "estimated_cost_usd": (
                            float(estimated_cost) if estimated_cost is not None else None
                        ),
                    },
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
                      provenance_json, confidence, source_refs_json, review_status,
                      rejected_reason)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13::jsonb,$14,$15)
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
                fields.get("rejected_reason"),
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
            rejected_reason=fields.get("rejected_reason"),
        )

    async def mark_job_status(
        self,
        *,
        job_id: str,
        status: str,
        actual_cost: float | None = None,
        proposals_total: int | None = None,
        error_message: str | None = None,
        only_if_status: tuple[str, ...] | None = None,
    ) -> bool:
        """Write the job's status (+ optional cost/total/error) and emit the
        transition atomically (H1). Returns True iff a row was updated.

        ``only_if_status`` (M2, HIGH-1) makes the write a CAS: the UPDATE only
        applies when the CURRENT status is one of the given values. The runner
        uses it so its lifecycle writes (running/paused/completed/failed) can
        NEVER clobber a status the control endpoint already moved to
        cancelled/paused — a lost CAS (returns False) means an external action
        won the race, and the runner yields."""
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
        where = "WHERE job_id = $1"
        if only_if_status is not None:
            params.append(list(only_if_status))
            where += f" AND status = ANY(${len(params)}::text[])"
        async with self._pool.acquire() as conn:
            async with conn.transaction():  # UPDATE + emit_job_event atomic (H1)
                row = await conn.fetchrow(
                    f"UPDATE enrichment_job SET {', '.join(sets)} "
                    f"{where} RETURNING user_id, status, error_message, actual_cost_usd",
                    *params,
                )
                if row is None:
                    # No row updated: either no such job, or the CAS guard didn't
                    # match (an external transition won). Nothing to emit.
                    return False
                # Unified Job Control Plane P1 — emit the status transition on the SAME
                # conn as the UPDATE (H1). Skip a status with no canonical JobStatus.
                cstatus = canonical_status(row["status"])
                if cstatus is not None:
                    # P4 — carry the CHANGING actual cost (params set once at create).
                    _cost = row["actual_cost_usd"]
                    await emit_job_event(
                        conn, service=JOB_SERVICE, job_id=str(job_id),
                        owner_user_id=str(row["user_id"]), kind=JOB_KIND, status=cstatus,
                        cost_usd=float(_cost) if _cost is not None else None,
                        error=job_error(row["error_message"]) if cstatus == "failed" else None,
                    )
        return True

    async def read_job_status(self, *, job_id: str) -> str | None:
        """The current persisted status (M2) — used by the runner to detect an
        external cancel/pause that landed between gaps. None if no such row."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT status FROM enrichment_job WHERE job_id = $1", UUID(job_id)
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
        book_id: str | None = None,
        technique: str,
        entity_kind: str | None,
        max_spend: float | None,
        estimated_cost: float,
        model_name: str | None = None,
    ) -> str:
        job_id = str(uuid4())
        self.jobs[job_id] = {
            "user_id": user_id,
            "project_id": project_id,
            "book_id": book_id,
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
            rejected_reason=fields.get("rejected_reason"),
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
        only_if_status: tuple[str, ...] | None = None,
    ) -> bool:
        job = self.jobs.setdefault(job_id, {})
        if only_if_status is not None and job.get("status") not in only_if_status:
            # CAS guard lost — an external transition won (M2). No write.
            return False
        job["status"] = status
        if actual_cost is not None:
            job["actual_cost"] = actual_cost
        if proposals_total is not None:
            job["proposals_total"] = proposals_total
        if error_message is not None:
            job["error_message"] = error_message
        return True

    async def read_job_status(self, *, job_id: str) -> str | None:
        job = self.jobs.get(job_id)
        return job.get("status") if job is not None else None
