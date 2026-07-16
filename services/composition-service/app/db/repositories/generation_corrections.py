"""generation_correction repository — the human-gate signal (V1 flywheel, §3).

`create` inserts a correction row AND emits `composition.generation_corrected`
into the outbox **in one transaction** (mirrors M9 `update_node_commit_aware`),
so the capture and the relayable event can never desync — the outbox is txn-
local. The emitted payload is STRUCTURAL-ONLY (kind, chosen index, change
magnitude, has_guidance/has_raw flags); verbatim prose + guidance text live in
the row (composition is the source of truth), redact-by-default on the wire so a
learning consumer gets the preference signal without the novel text (§3/§5).

SCOPE RULE (package re-key, spec 25 §Repo/service layer): reads key on
`project_id` — access is decided BEFORE the repo, at the gate (E0 grant on the
row's `book_id`). `create` stamps `created_by` (a plain actor stamp — STORED,
never filtered on), derives `book_id` from the correction's generation_job
inside the INSERT, and verifies the job is in THIS project before writing —
the in-DB FK only proves the job exists, not that it is in scope
(D-COMP-M2-XREF-OWNERSHIP).
"""

from __future__ import annotations

import difflib
from uuid import UUID

import asyncpg

from app.db.models import (
    CorrectionKind, CorrectionStats, GenerationCorrection, ModeCorrectionStats,
)
from app.db.repositories import ReferenceViolationError, outbox

# The modes always surfaced by the dashboard (zero-filled if absent) so the FE
# can render the auto-vs-cowrite A/B even before a mode has any generations.
_DASHBOARD_MODES = ("auto", "cowrite")

# BE-9c (F-Q3a) — the ONLY generation operations that produce a CORRECTABLE DRAFT (a passage a human
# accepts / edits / picks-different / regenerates / rejects). The correction-rate denominator MUST
# count just these. `mode='auto'` is ALSO the default for self_heal_propose, quality_report,
# promise_coverage, plan_pipeline, plan_forge_*, decompose_preview, conformance_run, mine_motifs, chat
# — none correctable — so grouping by mode over EVERY job inflates the 'auto' denominator and the
# accept_rate reads falsely high (a lie with a chart on it).
#   ⚠ This is ADDED to the NOT-selection_edit exclusion, NEVER a replacement. `mode` is a per-REQUEST
#   Literal["cowrite","auto"] over the SAME op, so `draft_scene`+cowrite IS already the Stream column
#   and is in this list. The only exclusively-cowrite ops are rewrite/expand/describe = SELECTION
#   EDITS, which the selection_edit exclusion removes. "Enumerating the cowrite ops from engine.py"
#   and adding them here silently reverts this fix and corrupts the very column it charts. The list is
#   these three; NOT selection_edit STAYS.
CORRECTABLE_OPERATIONS = ("draft_scene", "draft_chapter", "stitch_chapter")

_SELECT_COLS = """
  id, created_by, project_id, job_id, kind, chosen_candidate_index, guidance,
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
        project_id: UUID,
        job_id: UUID,
        *,
        created_by: UUID,
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

        Raises ReferenceViolationError when `job_id` is not a job in
        `project_id` (the router maps it to 404). `book_id` is derived from the
        job row inside the INSERT (it can never be NULL; callers do not thread
        it). The row insert and the outbox emit share one transaction: if either
        fails, neither is persisted (no capture without a relayable event, no
        orphan event without a capture).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                owned = await conn.fetchval(
                    "SELECT 1 FROM generation_job "
                    "WHERE id = $1 AND project_id = $2",
                    job_id, project_id,
                )
                if owned is None:
                    raise ReferenceViolationError(
                        f"job {job_id} is not a job in project {project_id}"
                    )
                # §8.3 chain: the regenerated-to job must ALSO be in this
                # project — the FK only proves existence, so without this a
                # correction could point at a foreign job (D-COMP-M2-XREF-OWNERSHIP,
                # /review-impl MED#2).
                if regenerated_to_job_id is not None:
                    chain_owned = await conn.fetchval(
                        "SELECT 1 FROM generation_job "
                        "WHERE id = $1 AND project_id = $2",
                        regenerated_to_job_id, project_id,
                    )
                    if chain_owned is None:
                        raise ReferenceViolationError(
                            f"regenerated_to_job_id {regenerated_to_job_id} is not a job in this project"
                        )
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO generation_correction
                      (created_by, project_id, book_id, job_id, kind, chosen_candidate_index,
                       guidance, changed_blocks, raw_before, raw_after,
                       regenerated_to_job_id)
                    SELECT $1, $2, j.book_id, $3, $4, $5, $6, $7, $8, $9, $10
                    FROM generation_job j WHERE j.id = $3 AND j.project_id = $2
                    RETURNING {_SELECT_COLS}, book_id
                    """,
                    created_by, project_id, job_id, kind, chosen_candidate_index,
                    guidance, changed_blocks, raw_before, raw_after,
                    regenerated_to_job_id,
                )
                if row is None:
                    raise ReferenceViolationError(
                        f"job {job_id} is not a job in project {project_id}"
                    )
                book_id = row["book_id"]
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
                        # actor identity for the learning corrections store (it is
                        # keyed per correcting user, NOT NULL). `created_by` is the
                        # acting caller — the owner of the preference signal. The
                        # wire key stays `user_id` (the consumer's contract).
                        "user_id": str(created_by),
                        "book_id": str(book_id) if book_id else None,
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

    async def correction_stats(
        self, project_id: UUID
    ) -> CorrectionStats:
        """Per-Work, per-mode correction-rate signal (the V1 eval-gate, §6).

        Denominator = COMPLETED generations of that mode; numerators = the
        author's corrections on them. accept_rate is derived (not mined) so it
        stays H2-safe. Both modes are always returned (zero-filled) for the
        auto-vs-cowrite A/B; within a Work the author is fixed, so the comparison
        cancels per-author edit-happiness (§6 M6)."""
        rows = await self._pool.fetch(
            """
            SELECT
              j.mode,
              count(DISTINCT j.id) FILTER (WHERE j.status = 'completed') AS generations,
              -- DISTINCT job (a job with multiple corrections counts ONCE, so a
              -- rate can't exceed 1.0) and gated to COMPLETED generations (so the
              -- numerator is always a subset of the denominator — accept_rate can
              -- never go negative). /review-impl slice-5 MED#1+#2.
              count(DISTINCT c.job_id) FILTER (WHERE j.status = 'completed')                          AS corrected_jobs,
              count(DISTINCT c.job_id) FILTER (WHERE j.status = 'completed' AND c.kind = 'edit')           AS edit_n,
              count(DISTINCT c.job_id) FILTER (WHERE j.status = 'completed' AND c.kind = 'pick_different')  AS pick_n,
              count(DISTINCT c.job_id) FILTER (WHERE j.status = 'completed' AND c.kind = 'regenerate')      AS regen_n,
              count(DISTINCT c.job_id) FILTER (WHERE j.status = 'completed' AND c.kind = 'reject')          AS reject_n,
              avg(c.changed_blocks) FILTER (WHERE j.status = 'completed' AND c.kind = 'edit')              AS avg_edit_mag
            FROM generation_job j
            LEFT JOIN generation_correction c
              -- double-filter: the project leg stays on BOTH joined re-keyed
              -- tables (the kinds-bug rule).
              ON c.job_id = j.id AND c.project_id = j.project_id
            WHERE j.project_id = $1
              -- BE-9c (F-Q3a): count ONLY correctable-draft operations. Without this the
              -- denominator includes plan passes / quality reports / self-heal / coverage /
              -- conformance / decompose (all default mode='auto'), so accept_rate reads a lie.
              AND j.operation = ANY($2::text[])
              -- /review-impl: T3.2 selection edits run mode='cowrite' but are NOT
              -- part of the draft-correction flywheel (no correction is captured),
              -- so they'd inflate the cowrite `generations` denominator and drag its
              -- correction rate down — corrupting the cowrite-vs-auto eval signal.
              -- Exclude them (audit-shared-table-consumers on a new row-type). ADDED TO
              -- the allowlist above, never replaced (F-Q3a).
              AND NOT coalesce((j.input->>'selection_edit')::boolean, false)
            GROUP BY j.mode
            """,
            project_id,
            list(CORRECTABLE_OPERATIONS),
        )
        by_mode_raw = {r["mode"]: r for r in rows}

        def _rate(n: int, gens: int) -> float | None:
            return (n / gens) if gens else None

        stats: list[ModeCorrectionStats] = []
        for mode in _DASHBOARD_MODES:
            r = by_mode_raw.get(mode)
            gens = int(r["generations"]) if r else 0
            if r is None:
                stats.append(ModeCorrectionStats(mode=mode, generations=0, corrected_jobs=0))
                continue
            stats.append(ModeCorrectionStats(
                mode=mode,
                generations=gens,
                corrected_jobs=int(r["corrected_jobs"]),
                # accept-as-is leaves NO correction row (H2): a completed generation
                # with no correction was accepted as-is (or abandoned — conflated).
                accept_rate=_rate(gens - int(r["corrected_jobs"]), gens),
                edit_rate=_rate(int(r["edit_n"]), gens),
                pick_different_rate=_rate(int(r["pick_n"]), gens),
                regenerate_rate=_rate(int(r["regen_n"]), gens),
                reject_rate=_rate(int(r["reject_n"]), gens),
                avg_edit_magnitude=float(r["avg_edit_mag"]) if r["avg_edit_mag"] is not None else None,
            ))
        return CorrectionStats(project_id=project_id, by_mode=stats)

    async def list_for_job(
        self, project_id: UUID, job_id: UUID
    ) -> list[GenerationCorrection]:
        """Corrections recorded on a job (newest first), project-scoped."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"SELECT {_SELECT_COLS} FROM generation_correction "
                f"WHERE project_id = $1 AND job_id = $2 ORDER BY created_at DESC",
                project_id, job_id,
            )
        return [_row_to_correction(r) for r in rows]
