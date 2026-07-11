"""WS-1.3 / review-impl — the chat_turn_extraction_enabled backfill must run EXACTLY ONCE.

`migrate.py` runs on EVERY service start. `chat_turn_extraction_enabled` is a USER SETTING —
a person can turn per-turn chat extraction OFF for one of their projects.

An UNGATED backfill therefore re-runs forever and silently flips that setting back ON at the
next restart: a privacy toggle undone by a reboot, with no event and nothing in any log.

This is the SAME failure the kg_indexed backfill was marker-gated to prevent (RUN-STATE D-R7),
made again one slice later, after the lesson had been written down. Hence a test, not a comment.

Rule this pins: **a backfill that touches a column a HUMAN can change must run exactly once.**
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.migrate import DDL, run_migrations

pytestmark = pytest.mark.xdist_group("pg")


async def _seed_project(pool, *, is_assistant: bool, chat_enabled: bool):
    project_id, user_id = uuid4(), uuid4()
    await pool.execute(
        """
        INSERT INTO knowledge_projects
          (project_id, user_id, name, project_type, is_assistant, chat_turn_extraction_enabled)
        VALUES ($1, $2, 'p', 'book', $3, $4)
        """,
        project_id, user_id, is_assistant, chat_enabled,
    )
    return project_id


async def _flag(pool, project_id) -> bool:
    return await pool.fetchval(
        "SELECT chat_turn_extraction_enabled FROM knowledge_projects WHERE project_id=$1",
        project_id,
    )


@pytest.mark.asyncio
async def test_a_restart_does_not_re_enable_a_setting_the_user_turned_off(pool):
    """THE ONE THAT MATTERS.

    The user deliberately disables per-turn chat extraction on their novel project. The
    service restarts (migrations run again). Their choice must survive.
    """
    # The backfill already ran once on this DB (the pool fixture runs run_migrations), so
    # the marker is present — which is exactly the state a real deployment is in.
    project = await _seed_project(pool, is_assistant=False, chat_enabled=True)
    try:
        # The user turns it OFF.
        await pool.execute(
            "UPDATE knowledge_projects SET chat_turn_extraction_enabled=false WHERE project_id=$1",
            project,
        )
        assert await _flag(pool, project) is False

        # The service restarts. Migrations run again.
        await run_migrations(pool)

        assert await _flag(pool, project) is False, (
            "a RESTART silently re-enabled per-turn chat extraction on a project the user had "
            "explicitly turned it OFF for. A privacy setting must not be undone by a reboot — "
            "and nothing would have logged it. Marker-gate the backfill."
        )
    finally:
        await pool.execute("DELETE FROM knowledge_projects WHERE project_id=$1", project)


@pytest.mark.asyncio
async def test_the_backfill_DOES_run_once_on_a_legacy_database(pool):
    """The other half: the backfill must actually WORK the first time.

    A pre-WS-1.3 project was extracting chat turns unconditionally. Adding the column with
    DEFAULT false would silently switch that off for every existing user, so the one-time
    backfill has to turn it on. Reconstructed here by clearing the marker, which is the
    state a real database is in the moment before the upgrade runs.
    """
    project = await _seed_project(pool, is_assistant=False, chat_enabled=False)
    try:
        await pool.execute(
            "DELETE FROM knowledge_data_migration WHERE id='chat_turn_extraction_backfill_v1'"
        )
        await pool.execute(DDL)

        assert await _flag(pool, project) is True, (
            "the one-time backfill did not run on a legacy row — every existing user would "
            "silently stop extracting chat knowledge"
        )
        # And the marker is back, so it will not run again.
        assert await pool.fetchval(
            "SELECT count(*) FROM knowledge_data_migration WHERE id='chat_turn_extraction_backfill_v1'"
        ) == 1
    finally:
        await pool.execute("DELETE FROM knowledge_projects WHERE project_id=$1", project)


@pytest.mark.asyncio
async def test_the_backfill_never_switches_the_assistant_on(pool):
    """Even on its one legitimate run, the ASSISTANT project must stay OFF.

    Its facts come once a day from the confirmed entry (D6). Turning per-turn extraction on
    for it would canonize an entire unreviewed 8-hour work conversation.
    """
    assistant = await _seed_project(pool, is_assistant=True, chat_enabled=False)
    try:
        await pool.execute(
            "DELETE FROM knowledge_data_migration WHERE id='chat_turn_extraction_backfill_v1'"
        )
        await pool.execute(DDL)

        assert await _flag(pool, assistant) is False, (
            "the backfill switched per-turn extraction ON for the ASSISTANT project — every "
            "turn of the user's all-day work session would be extracted as trusted canon"
        )
    finally:
        await pool.execute("DELETE FROM knowledge_projects WHERE project_id=$1", assistant)
