"""22 SC8 / B3 — the outline_node MCP create/update args carry the eight SC4
authored-intent fields, validated AT THE SCHEMA, and create_node persists them.

Two layers:
  1. Schema (pure pydantic, no DB): an out-of-range value_shift / non-positive
     target_words / an unversioned exit_state key is a clean 422 at the arg model
     — it NEVER reaches the DB CHECK (the mcp-tool-io IN-2 guarantee). Runs
     regardless of TEST_COMPOSITION_DB_URL.
  2. Round-trip (throwaway PG): OutlineRepo.create_node writes all eight fields —
     including the exit_state ::jsonb envelope — and they read back byte-for-byte.
"""

from __future__ import annotations

import json
import os
import uuid

import asyncpg
import pytest
from pydantic import ValidationError

import app.mcp.server as srv
from app.db.migrate import run_migrations
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo

# Shares the dev/throwaway PG when run under -n auto (serialized onto one worker).
pytestmark = pytest.mark.xdist_group("pg")

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")


# ── schema layer — 422 at the arg model, never the DB CHECK ────────────────────


def test_create_args_reject_value_shift_out_of_range():
    for bad in (200, -101, 101):
        with pytest.raises(ValidationError):
            srv._NodeCreateArgs(project_id="p", kind="scene", value_shift=bad)


def test_create_args_reject_nonpositive_target_words():
    for bad in (0, -10):
        with pytest.raises(ValidationError):
            srv._NodeCreateArgs(project_id="p", kind="scene", target_words=bad)


def test_create_args_reject_unversioned_exit_state_key():
    # SceneExitState is extra='forbid' — a smuggled key is rejected at the schema.
    with pytest.raises(ValidationError):
        srv._NodeCreateArgs(
            project_id="p", kind="scene", exit_state={"v": 1, "bogus": "x"},
        )


def test_update_args_reject_out_of_range():
    with pytest.raises(ValidationError):
        srv._NodeUpdateArgs(
            project_id="p", node_id="n", expected_version=1, value_shift=200,
        )
    with pytest.raises(ValidationError):
        srv._NodeUpdateArgs(
            project_id="p", node_id="n", expected_version=1, target_words=0,
        )


def test_create_args_accept_full_valid_intent():
    a = srv._NodeCreateArgs(
        project_id="p", kind="scene", conflict="man vs self", outcome="pyrrhic",
        value_shift=-40, stakes="his throne", target_words=1200, story_time="dawn",
        exit_state={"v": 1, "characters": "shaken", "advances": ["betrayal revealed"]},
    )
    assert a.value_shift == -40 and a.target_words == 1200
    assert a.conflict == "man vs self" and a.stakes == "his throne"
    assert a.exit_state is not None and a.exit_state.advances == ["betrayal revealed"]
    # the boundary values are inclusive (SMALLINT CHECK BETWEEN -100 AND 100)
    srv._NodeCreateArgs(project_id="p", kind="scene", value_shift=100)
    srv._NodeCreateArgs(project_id="p", kind="scene", value_shift=-100)


# ── round-trip layer — create_node persists the eight fields (incl. ::jsonb) ────


@pytest.fixture
async def pool():
    if not _DSN:
        pytest.skip("set TEST_COMPOSITION_DB_URL to a throwaway DB to run")
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=2)
    try:
        await run_migrations(p)  # idempotent (IF NOT EXISTS) — ensures the SC4 cols
        yield p
    finally:
        await p.close()


async def test_create_node_persists_sc4_intent(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await WorksRepo(pool).create(user, project, book)  # book_id source for the INSERT
    loc = uuid.uuid4()
    node = await OutlineRepo(pool).create_node(
        project, created_by=user, kind="scene", title="S",
        chapter_id=uuid.uuid4(),  # outline_chapter_required: a scene must carry one
        location_entity_id=loc, story_time="the third dawn",
        conflict="man vs self", outcome="pyrrhic", value_shift=-40,
        stakes="his throne", target_words=1200,
        exit_state={"v": 1, "characters": "shaken", "advances": ["betrayal"]},
    )
    row = await pool.fetchrow(
        """
        SELECT location_entity_id, story_time, conflict, outcome, value_shift,
               stakes, target_words, exit_state
        FROM outline_node WHERE id = $1
        """,
        node.id,
    )
    assert row["location_entity_id"] == loc
    assert row["story_time"] == "the third dawn"
    assert row["conflict"] == "man vs self"
    assert row["outcome"] == "pyrrhic"
    assert row["value_shift"] == -40
    assert row["stakes"] == "his throne"
    assert row["target_words"] == 1200
    es = row["exit_state"]
    es = json.loads(es) if isinstance(es, str) else es
    assert es == {"v": 1, "characters": "shaken", "advances": ["betrayal"]}


async def test_create_node_defaults_sc4_intent_when_omitted(pool):
    # A create with no SC4 args leaves the NOT-NULL text cols '' and the nullable
    # cols NULL (never a spurious CHECK trip) — the decompose/plain-create path.
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await WorksRepo(pool).create(user, project, book)
    node = await OutlineRepo(pool).create_node(
        project, created_by=user, kind="chapter", title="C",
        chapter_id=uuid.uuid4(),  # outline_chapter_required: a chapter must carry one
    )
    row = await pool.fetchrow(
        """
        SELECT conflict, outcome, stakes, location_entity_id, story_time,
               value_shift, target_words, exit_state
        FROM outline_node WHERE id = $1
        """,
        node.id,
    )
    assert row["conflict"] == "" and row["outcome"] == "" and row["stakes"] == ""
    assert row["location_entity_id"] is None and row["story_time"] is None
    assert row["value_shift"] is None and row["target_words"] is None
    assert row["exit_state"] is None
