"""Production gate-status READER (RAID C16, DEFERRED-054 + DEFERRED-055).

Binds the :data:`~app.strategies.factory.GateStatusReader` seam to the real
persisted eval data: it reads the LATEST ``enrichment_eval_runs`` row for a
(project, suite_version) via the C15 :class:`~app.db.repositories.eval_runs.EvalRunsRepo`
and projects it onto a :class:`~app.strategies.factory.LiveGateStatus`.

This is the SAME read the ``/internal/eval/{project}/gate-status`` route performs
(``EvalRunsRepo.get_latest`` → ``p2_p3_unlocked = bool(row.passed)``), so the
gate-aware factory enforces against the identical live signal the route exposes —
there is one source of truth for "is P2/P3 unlocked for this project", not two.

FRESHNESS bound (WARN-2 / DEFERRED-055): ``get_latest`` has NO recency filter, so
a passing run from arbitrarily long ago would otherwise keep P2/P3 unlocked
forever — a passing eval against a since-changed corpus is a stale green. This
reader treats a passing row OLDER than ``max_age_seconds`` as LOCKED (fail-closed
on staleness): the eval must be RE-RUN against the current corpus to re-unlock the
higher-cost tier. ``max_age_seconds <= 0`` disables the bound (any passing run
stays valid — not recommended in production).

Fail-CLOSED: cross-user isolation in ``get_latest`` means another user's project
returns ``None`` → a LOCKED status; a stale passing row → LOCKED; a malformed id /
read error is caught by the factory's ``read_gate`` wrapper (also → LOCKED). A DB
outage / a stale pass can NEVER unlock the higher-cost tier.

NO model names, NO secrets — only the gate boolean + composite for audit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.config import settings
from app.db.repositories.eval_runs import EvalRunsRepo
from app.strategies.factory import GateStatusReader, LiveGateStatus

__all__ = ["make_eval_runs_gate_reader"]


def make_eval_runs_gate_reader(
    repo: EvalRunsRepo, *, max_age_seconds: float | None = None
) -> GateStatusReader:
    """Build a :data:`GateStatusReader` backed by the C15 ``EvalRunsRepo``.

    Reads the latest persisted eval run for (user, project, suite_version) and
    returns its gate verdict. No run → LOCKED (fail-closed). A passing run older
    than ``max_age_seconds`` is treated as STALE → LOCKED (WARN-2/DEFERRED-055).
    ``max_age_seconds`` defaults to ``settings.gate_max_age_seconds``; ``<= 0``
    disables the bound. The returned callable is the production seam the
    :class:`~app.strategies.factory.GateAwareStrategyFactory` injects; tests pass a
    fake reader (or this one with a tuned ``max_age_seconds``) instead.
    """
    if max_age_seconds is None:
        max_age_seconds = settings.gate_max_age_seconds

    async def _read(
        user_id: str, project_id: str, suite_version: str
    ) -> LiveGateStatus:
        row = await repo.get_latest(
            user_id=UUID(user_id),
            project_id=UUID(project_id),
            suite_version=suite_version,
        )
        if row is None:
            # No eval run for this project/suite (or cross-user) → fail-closed.
            return LiveGateStatus.locked(suite_version)

        unlocked = bool(row.passed)
        # FRESHNESS: a PASSING run older than the bound is stale → LOCKED. A
        # failing row is already locked, so the age check only matters for a pass.
        if unlocked and max_age_seconds > 0:
            age = (datetime.now(timezone.utc) - row.created_at).total_seconds()
            if age > max_age_seconds:
                # Stale green: re-run the eval against the current corpus to
                # re-unlock P2/P3. Carry the composite for the audit trail.
                return LiveGateStatus(
                    has_run=True,
                    p2_p3_unlocked=False,
                    suite_version=row.suite_version,
                    composite=row.composite,
                    passed=False,
                )
        return LiveGateStatus(
            has_run=True,
            p2_p3_unlocked=unlocked,
            suite_version=row.suite_version,
            composite=row.composite,
            passed=row.passed,
        )

    return _read
