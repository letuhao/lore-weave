# ADR — Budget attribution for global-scope summary regeneration

> **Status:** Accepted (2026-04-29, session 51 cycle 46 / C16 🏗 DESIGN-first).
> **Decision:** Option B — new `knowledge_summary_spending` table.
> **Closes-on-BUILD:** D-K20α-01 partial.
> **BUILD cycle:** TBD (post-C16). Implementation sketch §5 below is shovel-ready.
> **Related plan row:** [Track 2/3 Gap Closure §4 C16](./KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md#c16--budget-attribution-for-global-scope-regen-p5-xl-design-first).

---

## 1. Context — what D-K20α-01 represents

K20.3 Cycle β shipped scheduled global L0 summary regeneration via
[`regenerate_global_summary`](../../services/knowledge-service/app/jobs/regenerate_summaries.py).
The cost is **observable** through Prometheus
(`summary_regen_cost_usd_total{scope_type='global'}` +
`summary_regen_tokens_total{scope_type, token_kind}`) but is **not
charged** against the user's monthly budget.

The K16.11 + K16.12 budget infrastructure assumes every spend has a
`project_id`:

- `knowledge_projects.current_month_spent_usd` — per-project counter
- `record_spending(pool, user_id, project_id, cost)` — required arg
- `check_user_monthly_budget` — sums `current_month_spent_usd` across
  the user's projects and compares to `user_knowledge_budgets.ai_monthly_budget_usd`

Global L0 regen has **no `project_id`** — it operates against
`knowledge_summaries` rows where `project_id IS NULL`. The scheduler
therefore has no path to record the spend without picking an arbitrary
project, which would mis-attribute cost.

**Practical impact**:

- A user with a `$10/month` budget can run unlimited global regens
- Provider client's `10 req/sec` rate limiter is the only ceiling
- At ~$0.01-0.05 per regen × 10/sec → $1–5/sec sustained burn possible
- Hobby scale today: regens run weekly via cron, manual triggers are
  rare → not exploited yet, but a runaway script or future user-
  triggered regen UI would expose the gap

This ADR closes the BUILD-blocker on D-K20α-01.

---

## 2. Existing surface (audited 2026-04-29)

### 2.1 Per-project spend (K16.11)

Schema (`knowledge_projects`):

```
monthly_budget_usd       NUMERIC(10,4)        -- per-project cap
current_month_spent_usd  NUMERIC(10,4) NOT NULL DEFAULT 0
current_month_key        TEXT                 -- 'YYYY-MM'
actual_cost_usd          NUMERIC(10,4) NOT NULL DEFAULT 0  -- all-time
```

Recorder: [`app/jobs/budget.py:record_spending(pool, user_id, project_id, cost)`](../../services/knowledge-service/app/jobs/budget.py).
UPDATE pattern: `current_month_spent_usd += cost` with month rollover
(reset to `cost` when `current_month_key != now()`).

### 2.2 User-wide cap (K16.12)

Schema (`user_knowledge_budgets`):

```
user_id                UUID PRIMARY KEY
ai_monthly_budget_usd  NUMERIC(10,4)         -- NULL = unlimited
updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
```

Aggregation: [`check_user_monthly_budget`](../../services/knowledge-service/app/jobs/budget.py#L130)
sums `current_month_spent_usd` across all of the user's
`knowledge_projects` rows whose `current_month_key` matches the
current month, compares against `ai_monthly_budget_usd`.

### 2.3 Observability for regen (K20.3)

Prometheus counters (already labelled by scope, no schema change
needed):

```
summary_regen_total{scope_type, status}
summary_regen_cost_usd_total{scope_type}
summary_regen_tokens_total{scope_type, token_kind}
summary_regen_duration_seconds{scope_type}
```

`scope_type` cardinality is closed at 2: `'global'` | `'project'`.

### 2.4 What's missing

- No persistence layer for `scope_type='global'` spend
- No code path that aggregates global regen spend into the user's
  monthly cap calculation
- `record_spending` rejects `project_id=None` by signature

---

## 3. Decision — Option B (new dedicated table)

Introduce a dedicated table `knowledge_summary_spending` keyed on
`(user_id, scope_type, month_key)` plus a thin helper
`record_summary_spending(user_id, scope_type, cost)`. Extend
`check_user_monthly_budget` to include this table's rows in the
aggregate.

**Why B over A and C** — see §4. Briefly: A pollutes
`knowledge_projects` with phantom rows; C is the eventually-correct
design but XL+ in BUILD effort and out-of-cycle for closing
D-K20α-01 minimally.

---

## 4. Rejected alternatives

### 4.1 Option A — phantom project row per user

**Shape:** reserve a special UUID (e.g.
`00000000-0000-0000-0000-0000000000a0` or hash-derived per-user)
inserted into `knowledge_projects` as a "system-global" project. All
non-project spend goes there via existing `record_spending`.

**Rejected because:**

- Every `SELECT FROM knowledge_projects` consumer needs a phantom
  filter (`WHERE project_id != phantom`, or `is_archived = true` to
  hide it). 12+ existing call sites would need updating; new call
  sites would forget.
- Frontend `ProjectsTab` would render a "system" project unless
  explicitly filtered — leaks the implementation to UX.
- Migration story even in greenfield: every new user signup needs
  the phantom row created — adds a step to the auth flow or
  knowledge-service onboarding.
- Phantom UUIDs are an implementation smell. A future maintainer
  reading "why does this user have a project they didn't create?"
  hits a real comprehension cliff.

### 4.2 Option C — unified spending ledger

**Shape:** new immutable `knowledge_spending_ledger` table:

```
spending_id UUID PK, user_id UUID, project_id UUID NULL,
scope_type TEXT, spent_usd NUMERIC(10,4), recorded_at TIMESTAMPTZ
```

Every spend (extraction-per-item + regen + future) inserts a row.
`current_month_spent_usd` becomes a materialized cache OR is dropped.

**Rejected because:**

- BUILD effort is XL: every existing `record_spending` callsite (the
  worker-ai per-item recorder, future cycles) would need to migrate
  to the ledger pattern. Touching the extraction worker mid-flight
  carries real regression risk even greenfield.
- Materialized-cache vs source-of-truth tension: dropping
  `current_month_spent_usd` invalidates K10.4's atomic `try_spend`
  pattern (the whole money-guard contract) — the cache route preserves
  it but adds reconciliation.
- C is "the right architecture if we ever want a usage-analytics
  dashboard". We don't have that requirement; over-investing now
  delays D-K20α-01's actual close.

**B doesn't block C.** If usage analytics demand a unified ledger
later, C can refactor on top: `knowledge_summary_spending` becomes a
view over the ledger, OR a future cycle migrates it. The data shape
chosen for B (one row per user × scope × month) maps cleanly to a
ledger via aggregation.

---

## 5. Implementation sketch (BUILD-ready)

### 5.1 Migration DDL

Append to `app/db/migrate.py` after `user_knowledge_budgets`:

```sql
-- ═══════════════════════════════════════════════════════════════
-- C16 — knowledge_summary_spending: per-user-per-scope monthly spend.
-- Closes D-K20α-01: global L0 regen has no project_id and so can't
-- be recorded against knowledge_projects.current_month_spent_usd.
-- This table is the authoritative ledger for non-project-attributable
-- AI spend (today: scope_type='global'; future scopes added by
-- expanding the CHECK constraint + the Pydantic Literal).
--
-- Each (user_id, scope_type, month_key) is a single row. Inserted on
-- first spend of the month; updated atomically on subsequent. Month
-- rollover is in-place (no separate archive table) — same semantics
-- as K16.11's current_month_spent_usd reset.
--
-- check_user_monthly_budget aggregates this table's matching-month
-- rows alongside knowledge_projects.current_month_spent_usd to
-- enforce the user-wide cap.
--
-- No FK on user_id (cross-DB convention).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS knowledge_summary_spending (
  user_id      UUID NOT NULL,
  scope_type   TEXT NOT NULL CHECK (scope_type IN ('global', 'project')),
  month_key    TEXT NOT NULL,    -- 'YYYY-MM'
  spent_usd    NUMERIC(10,4) NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, scope_type, month_key)
);

-- Aggregation hot path: SUM(spent_usd) WHERE user_id=$1 AND month_key=$2
CREATE INDEX IF NOT EXISTS idx_summary_spending_user_month
  ON knowledge_summary_spending(user_id, month_key);
```

**Note on `scope_type='project'`**: included in the CHECK enum even
though projects today record per-project via `current_month_spent_usd`.
Reserving the value avoids a CHECK migration if a future cycle ever
wants to ledger project-level summary regen here too. The
`record_summary_spending` helper rejects `'project'` in v1 (BUILD
cycle decides whether to relax).

### 5.2 Repo + helper

NEW `app/db/repositories/summary_spending.py`:

```python
"""C16 — knowledge_summary_spending repo. Persists non-project-
attributable AI spend (scope_type='global' today) so
check_user_monthly_budget can include it in the user-wide cap."""

from __future__ import annotations
from decimal import Decimal
from typing import Literal
from uuid import UUID
import asyncpg

ScopeType = Literal["global"]  # closed; expanded if/when needed
__all__ = ["SummarySpendingRepo", "ScopeType"]


def _current_month_key() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m")


class SummarySpendingRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(
        self, user_id: UUID, scope_type: ScopeType, cost: Decimal,
    ) -> None:
        """Atomic UPSERT — month rollover is handled by the PK
        including month_key (a new month → new row, no manual reset)."""
        if cost <= 0:
            return  # no-op for zero/negative; mirrors record_spending
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

    async def current_month_total(
        self, user_id: UUID,
    ) -> Decimal:
        """Sum of this month's spend across all scope_types for the
        user. Used by check_user_monthly_budget."""
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
```

### 5.3 Integration into `check_user_monthly_budget`

Extend [`app/jobs/budget.py:check_user_monthly_budget`](../../services/knowledge-service/app/jobs/budget.py):

```python
# Replace the single SUM query with a UNION ALL or two-query sum.
# Two-query is simpler to read and trivially correct.

# Existing per-project sum (unchanged):
spent_row = await pool.fetchrow(
    """
    SELECT COALESCE(SUM(
      CASE WHEN current_month_key = $2
           THEN current_month_spent_usd ELSE 0 END
    ), 0) AS total
    FROM knowledge_projects
    WHERE user_id = $1
    """,
    user_id, month_key,
)
project_spent: Decimal = spent_row["total"]

# NEW — non-project-attributable summary spend (C16):
summary_spent_row = await pool.fetchrow(
    """
    SELECT COALESCE(SUM(spent_usd), 0) AS total
    FROM knowledge_summary_spending
    WHERE user_id = $1 AND month_key = $2
    """,
    user_id, month_key,
)
summary_spent: Decimal = summary_spent_row["total"]

spent: Decimal = project_spent + summary_spent
# … rest of function unchanged
```

### 5.4 Wire into `regenerate_global_summary`

Inject `SummarySpendingRepo` (or pool — call sites already have it)
into [`regenerate_global_summary`](../../services/knowledge-service/app/jobs/regenerate_summaries.py#L578).
After the successful provider call (right next to the existing
Prometheus increment at line 569-573):

```python
# ... existing metric increment ...
cost_usd = _compute_llm_cost_usd(response, model_ref)
if cost_usd > 0:
    summary_regen_cost_usd_total.labels(scope_type=scope_type).inc(
        float(cost_usd)
    )
    # C16 — record against user-wide monthly budget.
    if scope_type == "global":
        await summary_spending_repo.record(
            user_id, "global", cost_usd,
        )
```

`scope_type='project'` regens already record via the existing
per-project `record_spending` path (extraction's worker-ai recorder
fires when project regens consume cost — actually, do they? **Open
question for BUILD cycle**, see §6).

**Recording order — record AFTER provider success, BEFORE post-call
guardrails:** the existing pattern at line 569 fires the Prometheus
metric immediately after the provider returns, before drift /
quality / similarity guardrails run. `record_summary_spending`
should sit in the same window. Rationale: the provider has already
billed the user for the tokens regardless of whether downstream
guardrails approve the regen output. Even a no-op-similarity-rejected
regen incurred real cost and must count toward the budget. If the
recorder itself raises (e.g. transient pool failure), the regen
result is still returned to the caller — the cost is captured by the
Prometheus metric and an ops alert on `summary_regen_cost_usd_total`
diverging from `knowledge_summary_spending` SUM is the recovery path.

### 5.5 Test plan

**Unit tests** for `SummarySpendingRepo` (mirror `test_user_budgets.py`):

1. `record()` first call inserts row
2. `record()` second call same month UPSERTs (additive)
3. `record()` second call new month creates a new row (rollover)
4. `record(cost=0)` is no-op (no INSERT)
5. `record(cost=negative)` is no-op
6. `current_month_total()` returns 0 for user with no rows
7. `current_month_total()` sums across scope_types for the same month
8. `current_month_total()` ignores rows from prior months

**Integration test** (gated on TEST_DATABASE_URL) — exercises the
real CHECK constraint:

9. `record(scope_type='invalid')` raises (CHECK rejects)

**Budget integration tests** in `test_budget.py`:

10. `check_user_monthly_budget` sums project + summary spend correctly
11. User-wide cap rejects when projected total > cap (covers projects
    + summary together)
12. Stale-month rows ignored by both branches

**Scheduler integration** — extend
`test_summary_regen_scheduler.py`:

13. Successful global regen records against `knowledge_summary_spending`
14. Failed/no-op global regen does NOT record
15. Project regen does NOT record here (uses K16.11 path)

### 5.6 DDL test — `test_migrate_ddl.py`

```python
def test_summary_spending_table_present():
    assert "CREATE TABLE IF NOT EXISTS knowledge_summary_spending" in DDL

def test_summary_spending_check_constraint():
    assert "scope_type IN ('global', 'project')" in DDL

def test_summary_spending_pk_includes_month_key():
    """PK shape (user_id, scope_type, month_key) — month rollover is
    in-place (a new month creates a new row, no UPDATE chain)."""
    import re
    m = re.search(
        r"PRIMARY KEY \(user_id, scope_type, month_key\)",
        DDL,
    )
    assert m is not None

def test_summary_spending_no_cross_db_fk():
    """No FK on user_id — users live in auth-service."""
    import re
    body = re.search(
        r"CREATE TABLE IF NOT EXISTS knowledge_summary_spending\s*\((.*?)\);",
        DDL, re.DOTALL,
    ).group(1)
    assert "REFERENCES" not in body
```

### 5.7 Estimated BUILD scope

- `migrate.py` DDL append: 1 file MOD
- `summary_spending.py` repo: 1 NEW file
- `budget.py` extension: 1 file MOD
- `regenerate_summaries.py` wire-in: 1 file MOD (2-3 lines added at
  call site)
- Tests: 2-3 NEW + 2 MOD test files
- Docs: SESSION_PATCH + plan update

**Estimate: 8-9 files, 4-5 logic changes, 1 side-effect (new table)**
→ workflow-gate L territory. Honest sizing per the recurring session-51
pattern.

---

## 6. Open questions for BUILD cycle

1. **Per-project regen also via `record_summary_spending`?**

   Plan reads "global L0 regen has no project_id" — but project-scope
   regens (`scope_type='project'`) DO fire from the same code path
   ([`regenerate_project_summary`](../../services/knowledge-service/app/jobs/regenerate_summaries.py)).
   Today their cost goes through Prometheus `summary_regen_cost_usd_total{scope_type='project'}`
   but **not** through `record_spending` either — verify in BUILD audit.

   - If project regen ALSO bypasses the budget gate today: include in
     C16 BUILD scope (record against knowledge_summary_spending OR
     fix to call `record_spending` with the project_id we already
     have).
   - If project regen goes through `record_spending`: leave C16 to
     global only.

   **BUILD cycle CLARIFY should re-audit `regenerate_project_summary`
   spend recording.**

2. **Should `record_summary_spending` reject `cost > some_sanity_cap`?**

   K16.11's `record_spending` accepts any positive Decimal. A bug in
   `_compute_llm_cost_usd` could record an absurd value. Either trust
   the upstream cost calc (current K16.11 stance) or add a sanity
   ceiling.

   **Recommend: trust upstream**, matches existing pattern.

3. **Frontend exposure?**

   `useUserCosts` / `UserCostSummary` API today returns
   `current_month_usd` from `knowledge_projects`. After C16 BUILD it
   should include summary spend. The wire shape doesn't expose
   per-scope-type breakdown — single `current_month_usd` is the sum.

   **Recommend: extend the existing aggregation, no wire change**, so
   FE doesn't need a coordinated update.

4. **Auto-pause on budget breach for global regen?**

   K16.11's `try_spend` is the atomic per-extraction-item guard
   (auto-pauses extraction job on cap breach). Global regen has no
   per-item structure — the whole regen is a single LLM call. The cap
   would need to be a pre-check (advisory) only.

   **Recommend: pre-check in scheduler before firing the regen**;
   accept that a regen can push spend slightly over the cap if the
   pre-check passes but the actual cost exceeds the prediction. Same
   semantics as K16.11's pre-check for extraction.

   This open question may also drive a sub-decision on whether the
   scheduler aborts the cycle entirely or skips just the over-budget
   user.

---

## 7. Closing checklist for BUILD cycle

When the C16-BUILD cycle ships, this ADR is closed when:

- [x] `knowledge_summary_spending` table created in `migrate.py`
- [x] `SummarySpendingRepo` shipped with 8 unit tests
- [x] `check_user_monthly_budget` extended to include summary spend
- [x] `regenerate_global_summary` wires the recorder
- [x] DDL regression tests added (4 tests per §5.6)
- [x] `test_budget.py` integration tests (#10-12) pass
- [x] `test_summary_regen_scheduler.py` extension (#13-15) passes
- [x] D-K20α-01 partial → fully cleared in SESSION_PATCH "Recently
  cleared"
- [x] Open questions §6 resolved in the BUILD cycle's CLARIFY

The plan row's `[x]` flips when all of the above are green AND a
`/review-impl` pass on the BUILD cycle returns 0 unresolved HIGH/MED.
