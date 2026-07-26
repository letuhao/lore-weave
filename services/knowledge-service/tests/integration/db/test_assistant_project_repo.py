"""WS-1.4 (spec 02 §Q2.2) — the assistant knowledge project get-or-create.

The properties that matter:
  - it is idempotent + race-safe (one assistant project per user — a split would give the
    assistant two half-memories, the same class the one-per-user unique defends);
  - chat_turn_extraction is fail-CLOSED off (D6: the assistant's facts come once a day from
    the confirmed entry, never per chat turn — extracting every turn is the ~100x-spend,
    trusted-canon-about-real-people bug);
  - the assistant project (a project_type='book' bound to the diary) is NEVER handed back to
    a normal book-project flow.

Gated on TEST_KNOWLEDGE_DB_URL (see conftest). Touches a real DB → xdist_group('pg').
"""

import asyncio
from uuid import uuid4

import pytest

from app.db.models import ProjectCreate
from app.db.repositories.projects import ProjectsRepo

pytestmark = pytest.mark.xdist_group("pg")


async def _flags(pool, project_id):
    """The two columns _row_to_project deliberately does not expose."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT is_assistant, chat_turn_extraction_enabled "
            "FROM knowledge_projects WHERE project_id = $1",
            project_id,
        )


@pytest.mark.asyncio
async def test_get_or_create_assistant_project_is_idempotent(pool):
    repo = ProjectsRepo(pool)
    user = uuid4()
    book = uuid4()

    proj, created = await repo.get_or_create_assistant_project(user, book)
    assert created is True
    row = await _flags(pool, proj.project_id)
    assert row["is_assistant"] is True, "the assistant project must be marked is_assistant"
    assert row["chat_turn_extraction_enabled"] is False, (
        "chat-turn extraction must be fail-CLOSED off for the assistant (D6) — the normal "
        "project opts in true, but the assistant extracts from the daily entry, not per turn"
    )

    # A second provision returns the SAME project (never a second assistant memory).
    again, created2 = await repo.get_or_create_assistant_project(user, book)
    assert created2 is False
    assert again.project_id == proj.project_id


@pytest.mark.asyncio
async def test_assistant_project_is_race_safe(pool):
    repo = ProjectsRepo(pool)
    user = uuid4()
    book = uuid4()

    results = await asyncio.gather(
        *[repo.get_or_create_assistant_project(user, book) for _ in range(4)]
    )
    ids = {p.project_id for p, _ in results}
    assert len(ids) == 1, (
        f"concurrent provisions minted {len(ids)} assistant projects — the advisory lock + "
        f"one-per-user unique must converge on exactly one, or the memory splits"
    )
    assert sum(1 for _, created in results if created) == 1, "exactly one call may create"

    async with pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM knowledge_projects WHERE user_id = $1 AND is_assistant", user
        )
    assert n == 1


@pytest.mark.asyncio
async def test_assistant_project_is_not_returned_as_a_normal_book_project(pool):
    # The assistant project is a project_type='book' bound to the diary. A normal
    # book-project resolution for that same book must NOT hand it back (wrong partition,
    # wrong extraction semantics) — mirrors the NOT is_derivative guard.
    repo = ProjectsRepo(pool)
    user = uuid4()
    book = uuid4()

    assistant, _ = await repo.get_or_create_assistant_project(user, book)

    # get_by_book must skip the assistant project.
    assert await repo.get_by_book(book) is None, (
        "get_by_book returned the assistant project as if it were a normal book project"
    )

    # create_or_get for the same book must create a DISTINCT normal project, not reuse the
    # assistant one.
    normal, created = await repo.create_or_get(
        user, ProjectCreate(name="Notes", project_type="book", book_id=book)
    )
    assert created is True
    assert normal.project_id != assistant.project_id
    # ...and now get_by_book resolves the normal one.
    resolved = await repo.get_by_book(book)
    assert resolved is not None and resolved.project_id == normal.project_id


@pytest.mark.asyncio
async def test_assistant_flag_off_for_a_normal_project(pool):
    # Guard the contrast: a normal project keeps chat-turn extraction ON (opt-in true) and is
    # NOT is_assistant — so the fail-closed assistant behavior is a real difference, not a
    # global default flip.
    repo = ProjectsRepo(pool)
    user = uuid4()
    normal = await repo.create(
        user, ProjectCreate(name="Novel", project_type="book", book_id=uuid4())
    )
    row = await _flags(pool, normal.project_id)
    assert row["is_assistant"] is False
    assert row["chat_turn_extraction_enabled"] is True


# ── A2 / D-R17 — the per-turn work-capture CONSENT toggle (canon_capture_enabled) ──


async def _consent(pool, project_id):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT canon_capture_enabled FROM knowledge_projects WHERE project_id = $1",
            project_id,
        )


@pytest.mark.asyncio
async def test_capture_consent_defaults_fail_closed_then_toggles_by_effect(pool):
    repo = ProjectsRepo(pool)
    user, book = uuid4(), uuid4()
    proj, _ = await repo.get_or_create_assistant_project(user, book)

    # Fail-closed by column DEFAULT (D-R17): a fresh assistant project captures NOTHING.
    assert await _consent(pool, proj.project_id) is False

    # Consent ON — proven by EFFECT (the flag the chat gate reads flips true).
    updated = await repo.set_canon_capture_consent(user, proj.project_id, enabled=True)
    assert updated is not None
    assert await _consent(pool, proj.project_id) is True

    # Consent OFF again (E8: off mid-day stops capture next tick).
    await repo.set_canon_capture_consent(user, proj.project_id, enabled=False)
    assert await _consent(pool, proj.project_id) is False


@pytest.mark.asyncio
async def test_capture_consent_is_owner_scoped(pool):
    # A different user cannot flip the owner's consent — the setter is WHERE user_id=$1.
    repo = ProjectsRepo(pool)
    owner, stranger, book = uuid4(), uuid4(), uuid4()
    proj, _ = await repo.get_or_create_assistant_project(owner, book)

    result = await repo.set_canon_capture_consent(stranger, proj.project_id, enabled=True)
    assert result is None, "a non-owner set must not match (owner-scoped)"
    assert await _consent(pool, proj.project_id) is False, "the owner's consent stayed OFF"
