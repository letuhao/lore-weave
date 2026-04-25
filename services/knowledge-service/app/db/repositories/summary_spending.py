"""C16 — knowledge_summary_spending repository.

Persists non-project-attributable AI spend (today: scope_type='global'
for L0 summary regeneration) so check_user_monthly_budget can include
it in the user-wide cap calculation.

Project-scope regen records via the existing K16.11 record_spending
path against knowledge_projects.current_month_spent_usd — that branch
has a project_id available and reuses existing infrastructure. This
repo is purely for spend that has no natural project_id.

See ADR docs/03_planning/KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md
for the design rationale and the closing checklist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

import asyncpg

__all__ = ["SummarySpendingRepo", "ScopeType"]


# Closed Literal (C16-BUILD CLARIFY decision Q1/Option α): only
# 'global' is a non-project-attributable scope today. Adding a new
# value requires coordinated migration of:
#   - migrate.py CHECK constraint (scope_type IN (...))
#   - this Literal definition
#   - any caller that passes a hard-coded scope value
ScopeType = Literal["global"]


def _current_month_key() -> str:
    """'YYYY-MM' UTC. Mirrors the same helper in app/jobs/budget.py;
    duplicating is cheaper than introducing a circular import or a
    shared utility module for one 3-line function."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


class SummarySpendingRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        cost: Decimal,
    ) -> None:
        """Atomic UPSERT of summary spend for the current month.

        cost <= 0 is a no-op (mirrors K16.11 record_spending). Month
        rollover is automatic via the PK shape: a new month_key
        creates a new row, no manual reset needed.

        Concurrent writes are safe: K20.3's advisory lock serializes
        the regen scheduler so two concurrent record() calls for the
        same (user, scope, month) shouldn't collide in practice. Even
        if they did, ON CONFLICT spent_usd = $current + $new is
        atomic at SQL level.
        """
        if cost <= 0:
            return
        month_key = _current_month_key()
        await self._pool.execute(
            """
            INSERT INTO knowledge_summary_spending
                (user_id, scope_type, month_key, spent_usd, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (user_id, scope_type, month_key) DO UPDATE SET
                spent_usd  = knowledge_summary_spending.spent_usd + $4,
                updated_at = now()
            """,
            user_id, scope_type, month_key, cost,
        )

    async def current_month_total(self, user_id: UUID) -> Decimal:
        """Sum of this month's spend across all scope_types for the
        user. Used by check_user_monthly_budget to fold summary spend
        into the user-wide cap aggregation.

        Returns Decimal('0') for users with no rows (COALESCE).
        """
        month_key = _current_month_key()
        row = await self._pool.fetchrow(
            """
            SELECT COALESCE(SUM(spent_usd), 0) AS total
            FROM knowledge_summary_spending
            WHERE user_id = $1 AND month_key = $2
            """,
            user_id, month_key,
        )
        return row["total"]
