"""K20.3 β — integration test for the global eligibility UNION SQL.

Unit tests mock the connection and seed users directly into a
``FakeConn.users`` list, which bypasses the real SQL entirely. A
regression swapping ``UNION`` for ``UNION ALL`` or shifting the
``scope_type = 'global'`` predicate would pass every unit test.

This test hits the real Postgres (skipped when the conftest pool is
unavailable) and seeds real rows across 5 user scenarios:

  A. global summary, no projects          → included
  B. no summary, 1 non-archived project   → included
  C. global summary + archived project    → included (via summaries)
  D. no summary + only archived project   → excluded
  E. global summary + non-archived project → included ONCE (UNION dedup)
"""

from __future__ import annotations

from uuid import uuid4

import pytest

# Private constant, imported deliberately for the integration contract
# test — a rename would break this and deserve reviewer attention.
from app.jobs.summary_regen_scheduler import (
    _LIST_GLOBAL_ELIGIBLE_USERS_SQL,
)


@pytest.mark.asyncio
async def test_global_eligibility_union_semantics(pool):
    """Lock the UNION eligibility contract at the SQL layer.

    The pool fixture TRUNCATEs knowledge_projects + knowledge_summaries
    at start-of-test (see conftest), so this test owns the full seed
    set and counts are deterministic.
    """
    user_a = uuid4()  # summary only
    user_b = uuid4()  # project only
    user_c = uuid4()  # summary + archived project
    user_d = uuid4()  # archived project only (should NOT appear)
    user_e = uuid4()  # summary + non-archived project (UNION dedup)

    async with pool.acquire() as conn:
        # Users A, C, E have a global summary row.
        for user_id in (user_a, user_c, user_e):
            await conn.execute(
                """
                INSERT INTO knowledge_summaries
                  (user_id, scope_type, scope_id, content)
                VALUES ($1, 'global', NULL, 'seed bio')
                """,
                user_id,
            )
        # Users B, E have a non-archived project; users C, D have
        # archived-only projects.
        for user_id, is_archived in (
            (user_b, False),
            (user_c, True),
            (user_d, True),
            (user_e, False),
        ):
            await conn.execute(
                """
                INSERT INTO knowledge_projects
                  (user_id, name, description, project_type, instructions,
                   extraction_enabled, extraction_status, is_archived,
                   extraction_config, estimated_cost_usd, actual_cost_usd,
                   version)
                VALUES ($1, 'p', '', 'book', '', false, 'disabled', $2,
                        '{}'::jsonb, 0, 0, 1)
                """,
                user_id,
                is_archived,
            )

        rows = await conn.fetch(_LIST_GLOBAL_ELIGIBLE_USERS_SQL)

    result_ids = {row["user_id"] for row in rows}
    assert str(user_a) in result_ids, "user_a (summary-only) missing"
    assert str(user_b) in result_ids, "user_b (project-only) missing"
    assert str(user_c) in result_ids, "user_c (summary + archived project) missing"
    assert str(user_d) not in result_ids, "user_d (archived-only) leaked into result"
    assert str(user_e) in result_ids, "user_e (dual-source) missing"
    # UNION dedup: user_e should appear exactly ONCE even though they
    # show up in both subqueries. A regression swapping to UNION ALL
    # would put them in twice and this assertion fails.
    user_e_count = sum(1 for row in rows if row["user_id"] == str(user_e))
    assert user_e_count == 1, (
        f"user_e appeared {user_e_count} times — UNION dedup broken"
    )


@pytest.mark.asyncio
async def test_global_eligibility_result_is_ordered(pool):
    """Lock the deterministic ordering contract — the sweep iterates
    in user_id order so crash-and-restart resumes predictably."""
    # Seed 3 users with UUIDs chosen to make string-sort order stable
    # regardless of uuidv4 randomness: we pass explicit UUIDs.
    from uuid import UUID
    user_low = UUID('00000000-0000-0000-0000-000000000001')
    user_mid = UUID('00000000-0000-0000-0000-000000000005')
    user_hi = UUID('00000000-0000-0000-0000-000000000009')

    async with pool.acquire() as conn:
        # Insert in a different order than expected sort to catch a
        # regression that dropped the outer ORDER BY.
        for user_id in (user_hi, user_low, user_mid):
            await conn.execute(
                """
                INSERT INTO knowledge_summaries
                  (user_id, scope_type, scope_id, content)
                VALUES ($1, 'global', NULL, 'seed bio')
                """,
                user_id,
            )
        rows = await conn.fetch(_LIST_GLOBAL_ELIGIBLE_USERS_SQL)

    ordered_ids = [row["user_id"] for row in rows]
    assert ordered_ids == sorted(ordered_ids), (
        "eligibility result not ordered by user_id — crash-resume "
        "semantics break"
    )
