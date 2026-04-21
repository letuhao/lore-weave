"""K16.12 — User-wide AI budget repository.

Tracks the per-user monthly AI spend cap in
``user_knowledge_budgets``. Per-project caps live on
``knowledge_projects.monthly_budget_usd`` and are owned by
``app.jobs.budget``. Both caps are advisory pre-checks; the
money-critical guard is still ``extraction_jobs.max_spend_usd`` via
``ExtractionJobsRepo.try_spend`` (K10.4).

SECURITY RULE: every public method takes ``user_id`` and scopes the
SQL on it. Upsert trusts the caller's authenticated user_id; router
layer gets it from JWT.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import asyncpg

__all__ = ["UserBudgetsRepo"]


class UserBudgetsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, user_id: UUID) -> Decimal | None:
        """Return the user's monthly AI budget cap, or ``None`` if the
        user has never set one or explicitly cleared it.

        No distinction is made between "no row" and "row with NULL" —
        both mean "no cap" to callers. The row persists across clears
        so ``updated_at`` can be inspected for audit trails.
        """
        row = await self._pool.fetchrow(
            """
            SELECT ai_monthly_budget_usd
            FROM user_knowledge_budgets
            WHERE user_id = $1
            """,
            user_id,
        )
        if row is None:
            return None
        return row["ai_monthly_budget_usd"]

    async def upsert(self, user_id: UUID, budget: Decimal | None) -> None:
        """Create-or-update the user's cap.

        Passing ``None`` clears the cap (column goes NULL, row kept).
        Idempotent — repeated writes with the same value only bump
        ``updated_at``.
        """
        await self._pool.execute(
            """
            INSERT INTO user_knowledge_budgets (user_id, ai_monthly_budget_usd)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
              SET ai_monthly_budget_usd = EXCLUDED.ai_monthly_budget_usd,
                  updated_at = now()
            """,
            user_id,
            budget,
        )
