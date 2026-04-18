"""K16.11 — Monthly budget enforcement.

Helper functions for checking and recording extraction spending.
Budget is tracked per-project on knowledge_projects:
  - monthly_budget_usd: user-set cap (NULL = unlimited)
  - current_month_spent_usd: spending counter
  - current_month_key: "YYYY-MM" string, resets on month rollover

The per-job cap (max_spend_usd on extraction_jobs) is enforced
atomically by try_spend in the repo layer. This module handles
the broader monthly/per-user aggregate checks that happen BEFORE
a job is started.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import asyncpg

__all__ = ["BudgetCheck", "can_start_job", "record_spending"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BudgetCheck:
    allowed: bool
    reason: str
    monthly_spent: Decimal = Decimal("0")
    monthly_budget: Decimal | None = None
    warning: str | None = None  # set when >= 80% of budget


def _current_month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def can_start_job(
    pool: asyncpg.Pool,
    user_id: UUID,
    project_id: UUID,
    estimated_cost: Decimal,
) -> BudgetCheck:
    """Check if a new job can start within the monthly budget.

    Handles month rollover: if current_month_key doesn't match the
    current month, resets current_month_spent_usd to 0 first.
    """
    month_key = _current_month_key()

    row = await pool.fetchrow(
        """
        SELECT monthly_budget_usd, current_month_spent_usd, current_month_key
        FROM knowledge_projects
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id,
    )
    if row is None:
        return BudgetCheck(allowed=False, reason="project not found")

    budget = row["monthly_budget_usd"]
    spent = row["current_month_spent_usd"] or Decimal("0")
    stored_key = row["current_month_key"]

    # Month rollover — reset counter
    if stored_key != month_key:
        await pool.execute(
            """
            UPDATE knowledge_projects
            SET current_month_spent_usd = 0,
                current_month_key = $3,
                updated_at = now()
            WHERE user_id = $1 AND project_id = $2
            """,
            user_id, project_id, month_key,
        )
        spent = Decimal("0")

    # No budget set — unlimited
    if budget is None:
        return BudgetCheck(allowed=True, reason="no monthly budget set",
                           monthly_spent=spent)

    # Check if estimated cost would exceed budget
    projected = spent + estimated_cost
    if projected > budget:
        return BudgetCheck(
            allowed=False,
            reason=f"estimated cost ${estimated_cost} would exceed monthly budget "
                   f"(${spent} spent of ${budget})",
            monthly_spent=spent,
            monthly_budget=budget,
        )

    # Warning at 80%
    warning = None
    if budget > 0 and projected / budget >= Decimal("0.8"):
        warning = f"projected spending ${projected} is >= 80% of monthly budget ${budget}"

    return BudgetCheck(
        allowed=True,
        reason="within budget",
        monthly_spent=spent,
        monthly_budget=budget,
        warning=warning,
    )


async def record_spending(
    pool: asyncpg.Pool,
    user_id: UUID,
    project_id: UUID,
    cost: Decimal,
) -> None:
    """Record spending against the project's monthly counter.

    Called by the worker after each extraction item completes.
    Handles month rollover atomically.
    """
    month_key = _current_month_key()
    await pool.execute(
        """
        UPDATE knowledge_projects
        SET current_month_spent_usd = CASE
              WHEN current_month_key = $3 THEN current_month_spent_usd + $4
              ELSE $4
            END,
            current_month_key = $3,
            actual_cost_usd = actual_cost_usd + $4,
            updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id, month_key, cost,
    )
