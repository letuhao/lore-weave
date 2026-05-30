"""Production gate-status READER (RAID C16, DEFERRED-054).

Binds the :data:`~app.strategies.factory.GateStatusReader` seam to the real
persisted eval data: it reads the LATEST ``enrichment_eval_runs`` row for a
(project, suite_version) via the C15 :class:`~app.db.repositories.eval_runs.EvalRunsRepo`
and projects it onto a :class:`~app.strategies.factory.LiveGateStatus`.

This is the SAME read the ``/internal/eval/{project}/gate-status`` route performs
(``EvalRunsRepo.get_latest`` → ``p2_p3_unlocked = bool(row.passed)``), so the
gate-aware factory enforces against the identical live signal the route exposes —
there is one source of truth for "is P2/P3 unlocked for this project", not two.

Fail-CLOSED: cross-user isolation in ``get_latest`` means another user's project
returns ``None`` → a LOCKED status; a malformed id / read error is caught by the
factory's ``read_gate`` wrapper (also → LOCKED). A DB outage can NEVER unlock the
higher-cost tier.

NO model names, NO secrets — only the gate boolean + composite for audit.
"""

from __future__ import annotations

from uuid import UUID

from app.db.repositories.eval_runs import EvalRunsRepo
from app.strategies.factory import GateStatusReader, LiveGateStatus

__all__ = ["make_eval_runs_gate_reader"]


def make_eval_runs_gate_reader(repo: EvalRunsRepo) -> GateStatusReader:
    """Build a :data:`GateStatusReader` backed by the C15 ``EvalRunsRepo``.

    Reads the latest persisted eval run for (user, project, suite_version) and
    returns its gate verdict. No run → LOCKED (fail-closed). The returned callable
    is the production seam the :class:`~app.strategies.factory.GateAwareStrategyFactory`
    injects; tests pass a fake instead.
    """

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
        return LiveGateStatus(
            has_run=True,
            p2_p3_unlocked=bool(row.passed),
            suite_version=row.suite_version,
            composite=row.composite,
            passed=row.passed,
        )

    return _read
