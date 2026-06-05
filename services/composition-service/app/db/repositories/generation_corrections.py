"""generation_correction repository — the human-gate signal (V1 flywheel, §3).

`create` inserts a correction row AND emits `composition.generation_corrected`
into the outbox **in one transaction** (mirrors M9 `update_node_commit_aware`),
so the capture and the relayable event can never desync — the outbox is txn-
local. The emitted payload is STRUCTURAL-ONLY (kind, chosen index, change
magnitude, has_guidance/has_raw flags); verbatim prose + guidance text live in
the row (composition is the source of truth), redact-by-default on the wire so a
learning consumer gets the preference signal without the novel text (§3/§5).

SECURITY (M5 isolation): `create` is user_id-scoped and verifies the job is the
caller's in THIS project before writing — the in-DB FK only proves the job
exists, not that it belongs to the caller (D-COMP-M2-XREF-OWNERSHIP).
"""

from __future__ import annotations

import difflib
from uuid import UUID

import asyncpg

from app.db.models import CorrectionKind, GenerationCorrection
from app.db.repositories import ReferenceViolationError, outbox

_SELECT_COLS = """
  id, user_id, project_id, job_id, kind, chosen_candidate_index, guidance,
  changed_blocks, raw_before, raw_after, regenerated_to_job_id, created_at
"""


def count_changed_blocks(before: str, after: str) -> int:
    """Coarse edit magnitude: # of non-equal line-level blocks between two texts.

    Pure + deterministic (difflib opcodes over line lists). It is the
    `change_magnitude` the learning preference store records — NOT the prose
    itself, so it survives the redact-by-default policy. Identical text → 0.
    """
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    sm = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    return sum(1 for tag, *_ in sm.get_opcodes() if tag != "equal")


def _row_to_correction(row: asyncpg.Record) -> GenerationCorrection:
    return GenerationCorrection.model_validate(dict(row))


class GenerationCorrectionsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        user_id: UUID,
        project_id: UUID,
        job_id: UUID,
        *,
        kind: CorrectionKind,
        chosen_candidate_index: int | None = None,
        guidance: str | None = None,
        changed_blocks: int | None = None,
        raw_before: str | None = None,
        raw_after: str | None = None,
        regenerated_to_job_id: UUID | None = None,
        winner_index: int | None = None,
        candidate_count: int | None = None,
    ) -> GenerationCorrection:
        """Insert a correction + emit the relayable event, atomically.

        Raises ReferenceViolationError when `job_id` is not the caller's job in
        `project_id` (the router maps it to 404). The row insert and the outbox
        emit share one transaction: if either fails, neither is persisted (no
        capture without a relayable event, no orphan event without a capture).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                owned = await conn.fetchval(
                    "SELECT 1 FROM generation_job "
                    "WHERE user_id = $1 AND id = $2 AND project_id = $3",
                    user_id, job_id, project_id,
                )
                if owned is None:
                    raise ReferenceViolationError(
                        f"job {job_id} is not the caller's job in project {project_id}"
                    )
                # §8.3 chain: the regenerated-to job must ALSO be the caller's in
                # this project — the FK only proves existence, so without this a
                # correction could point at a foreign job (D-COMP-M2-XREF-OWNERSHIP,
                # /review-impl MED#2).
                if regenerated_to_job_id is not None:
                    chain_owned = await conn.fetchval(
                        "SELECT 1 FROM generation_job "
                        "WHERE user_id = $1 AND id = $2 AND project_id = $3",
                        user_id, regenerated_to_job_id, project_id,
                    )
                    if chain_owned is None:
                        raise ReferenceViolationError(
                            f"regenerated_to_job_id {regenerated_to_job_id} is not the caller's job"
                        )
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO generation_correction
                      (user_id, project_id, job_id, kind, chosen_candidate_index,
                       guidance, changed_blocks, raw_before, raw_after,
                       regenerated_to_job_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    RETURNING {_SELECT_COLS}
                    """,
                    user_id, project_id, job_id, kind, chosen_candidate_index,
                    guidance, changed_blocks, raw_before, raw_after,
                    regenerated_to_job_id,
                )
                corr = _row_to_correction(row)
                # STRUCTURAL-ONLY payload (redact-by-default §5): no verbatim prose
                # and no guidance text on the wire — the learning consumer needs the
                # preference SHAPE (which candidate, how big the edit, the kind), not
                # the novel. raw prose stays in the row for an opted-in path later.
                await outbox.emit(
                    conn,
                    aggregate_id=project_id,
                    event_type=outbox.GENERATION_CORRECTED,
                    payload={
                        "correction_id": str(corr.id),
                        "job_id": str(job_id),
                        "project_id": str(project_id),
                        "kind": kind,
                        # winner_index (i) + chosen_candidate_index (j) + k let the
                        # learning consumer reconstruct the structural preference
                        # `cand_j ≻ winner_i` WITHOUT reading composition's DB
                        # (separate service/DB) — §8.2 resolved toward capture-time
                        # structural shape on the wire. Prose stays redacted (§5).
                        "winner_index": winner_index,
                        "chosen_candidate_index": chosen_candidate_index,
                        "candidate_count": candidate_count,
                        "changed_blocks": changed_blocks,
                        "has_guidance": guidance is not None,
                        "has_raw_prose": raw_before is not None or raw_after is not None,
                        "regenerated_to_job_id": (
                            str(regenerated_to_job_id) if regenerated_to_job_id else None
                        ),
                    },
                )
                return corr

    async def list_for_job(
        self, user_id: UUID, job_id: UUID
    ) -> list[GenerationCorrection]:
        """Corrections recorded on a job (newest first), user-scoped."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"SELECT {_SELECT_COLS} FROM generation_correction "
                f"WHERE user_id = $1 AND job_id = $2 ORDER BY created_at DESC",
                user_id, job_id,
            )
        return [_row_to_correction(r) for r in rows]
