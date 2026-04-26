"""K20.8 — drift-scenario integration test.

Validates the KSA §7.6 drift prevention rules against live Postgres
(summaries + summary_versions) + live Neo4j (raw :Passage nodes). The
LLM call is mocked so the test is deterministic — the drift guards
being tested here are all **pre-LLM** (edit lock, empty source) and
**post-LLM** (similarity no-op, history capture), neither of which
requires a real model.

Phase 4a-δ: ``regenerate_global_summary`` only accepts ``llm_client``
(loreweave_llm SDK wrapper); the legacy ``provider_client`` kwarg is
gone. Tests script a Job via a fake LLMClient (chat operation).

Scenarios:
  1. User edit lock: manual edit <30 days ago -> skip regen, no write.
  2. Empty source: no Passage nodes -> skip regen, no write, no LLM.
  3. Happy path: fresh passages + no recent edit -> new version, old
     content captured to history.
  4. Similarity no-op: mock LLM returns content matching current ->
     no version bump.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio

from app.db.repositories.summaries import SummariesRepo
from app.jobs.regenerate_summaries import regenerate_global_summary
from loreweave_llm.models import Job


@pytest_asyncio.fixture
async def test_user(pool, neo4j_driver):
    """User id is a real UUID so asyncpg accepts it; the neo4j side
    just treats it as a string. Cleanup: truncate summaries for this
    user; DETACH DELETE Passage nodes for this user."""
    user_id = uuid.uuid4()
    yield user_id
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM knowledge_summaries WHERE user_id = $1", user_id
        )
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (p:Passage {user_id: $user_id}) DETACH DELETE p",
            user_id=str(user_id),
        )


class _FakeLLMClient:
    """Stand-in for ``app.clients.llm_client.LLMClient`` exposing only
    ``submit_and_wait`` — sufficient for ``_invoke_llm_for_summary``."""

    def __init__(self, content: str) -> None:
        self.calls: list[dict[str, Any]] = []
        self._content = content

    async def submit_and_wait(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="chat",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": self._content}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )


def _mock_llm(text: str) -> _FakeLLMClient:
    return _FakeLLMClient(text)


def _neo4j_session_factory(neo4j_driver):
    @asynccontextmanager
    async def factory():
        async with neo4j_driver.session() as s:
            yield s

    return factory


async def _seed_passage(neo4j_driver, *, user_id, text):
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (p:Passage {
              id: $id,
              user_id: $user_id,
              project_id: null,
              source_type: 'chat_turn',
              source_id: $source_id,
              chunk_index: 0,
              text: $text,
              is_hub: false,
              created_at: datetime(),
              updated_at: datetime()
            })
            """,
            id=uuid.uuid4().hex,
            user_id=str(user_id),
            source_id=uuid.uuid4().hex,
            text=text,
        )


@pytest.mark.asyncio
async def test_user_edit_lock_skips_regeneration(pool, neo4j_driver, test_user):
    """A manual-edit row within the last 30 days must block regen —
    no LLM call, no version bump."""
    repo = SummariesRepo(pool)
    # Seed current summary + passages.
    await repo.upsert(test_user, "global", None, "first version content")
    # Manual edit to force a history row with edit_source='manual' and
    # created_at=now() — the upsert path writes history on every update.
    await repo.upsert(test_user, "global", None, "user-authored second version")
    await _seed_passage(neo4j_driver, user_id=test_user, text="raw chat passage")

    before = await repo.get(test_user, "global", None)
    assert before is not None
    before_version = before.version

    fake_llm = _mock_llm("some new bio")
    result = await regenerate_global_summary(
        user_id=test_user,
        model_source="user_model",
        model_ref="gpt-4o-mini",
        pool=pool,
        session_factory=_neo4j_session_factory(neo4j_driver),
        llm_client=fake_llm,
        summaries_repo=repo,
    )

    assert result.status == "user_edit_lock"
    assert fake_llm.calls == []
    after = await repo.get(test_user, "global", None)
    assert after is not None
    assert after.version == before_version


@pytest.mark.asyncio
async def test_empty_source_skips_without_llm(pool, neo4j_driver, test_user):
    """No :Passage nodes -> no_op_empty_source, no LLM call."""
    repo = SummariesRepo(pool)
    # No summary + no passages.
    fake_llm = _mock_llm("unused")
    result = await regenerate_global_summary(
        user_id=test_user,
        model_source="user_model",
        model_ref="gpt-4o-mini",
        pool=pool,
        session_factory=_neo4j_session_factory(neo4j_driver),
        llm_client=fake_llm,
        summaries_repo=repo,
    )
    assert result.status == "no_op_empty_source"
    assert fake_llm.calls == []


@pytest.mark.asyncio
async def test_happy_path_bumps_version_and_writes_history(
    pool, neo4j_driver, test_user
):
    """Fresh passages + no recent manual edit + non-similar LLM output
    -> regenerated: version bumps, the PRE-update content is in
    knowledge_summary_versions."""
    repo = SummariesRepo(pool)
    # Use a direct INSERT to avoid writing a manual-history row (that
    # would trip the edit lock). Mimics how the regen helper will look
    # in production: first regen on a brand-new user has no prior
    # manual edit.
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO knowledge_summaries
              (user_id, scope_type, scope_id, content, token_count, version)
            VALUES ($1, 'global', NULL, $2, 10, 1)
            """,
            test_user, "old prose about fantasy writing",
        )
    await _seed_passage(
        neo4j_driver,
        user_id=test_user,
        text="I want to try modern sci-fi this time.",
    )

    new_content = "User is experimenting with modern sci-fi prose after fantasy."
    fake_llm = _mock_llm(new_content)

    result = await regenerate_global_summary(
        user_id=test_user,
        model_source="user_model",
        model_ref="gpt-4o-mini",
        pool=pool,
        session_factory=_neo4j_session_factory(neo4j_driver),
        llm_client=fake_llm,
        summaries_repo=repo,
    )

    assert result.status == "regenerated", result
    assert result.summary is not None
    assert result.summary.content == new_content
    assert result.summary.version == 2
    assert len(fake_llm.calls) == 1

    # History row captured the PRE-update content. Review-impl H1:
    # regen writes the history row with edit_source='regen' (not
    # 'manual'), otherwise the user_edit_lock would silently fire on
    # the next regen call.
    history = await repo.list_versions(test_user, "global", None, limit=5)
    assert len(history) == 1
    assert history[0].content == "old prose about fantasy writing"
    assert history[0].edit_source == "regen"
    assert history[0].version == 1


@pytest.mark.asyncio
async def test_similarity_no_op_keeps_version(pool, neo4j_driver, test_user):
    """LLM output near-identical to current -> no version bump, no history."""
    repo = SummariesRepo(pool)
    existing = "User prefers formal fantasy prose with Vietnamese influences."
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO knowledge_summaries
              (user_id, scope_type, scope_id, content, token_count, version)
            VALUES ($1, 'global', NULL, $2, 10, 1)
            """,
            test_user, existing,
        )
    await _seed_passage(
        neo4j_driver, user_id=test_user, text="just some chat content",
    )

    # Mock returns same content — jaccard should be 1.0 -> no_op_similarity.
    fake_llm = _mock_llm(existing)
    result = await regenerate_global_summary(
        user_id=test_user,
        model_source="user_model",
        model_ref="gpt-4o-mini",
        pool=pool,
        session_factory=_neo4j_session_factory(neo4j_driver),
        llm_client=fake_llm,
        summaries_repo=repo,
    )

    assert result.status == "no_op_similarity"
    current = await repo.get(test_user, "global", None)
    assert current is not None
    assert current.version == 1  # unchanged
    history = await repo.list_versions(test_user, "global", None, limit=5)
    assert history == []


@pytest.mark.asyncio
async def test_regen_history_row_uses_regen_edit_source(
    pool, neo4j_driver, test_user
):
    """Review-impl H1 regression.

    A successful regen MUST write its pre-update history row with
    ``edit_source='regen'``, not ``'manual'``. Without this, every
    successful regen would silently trip the 30-day user_edit_lock on
    the next call.

    Test plan:
      1. Seed an existing summary and a fresh passage.
      2. Run regen #1 — expect ``regenerated`` status.
      3. Assert the new history row has ``edit_source='regen'``.
      4. Run regen #2 with different content — expect ``regenerated``,
         NOT ``user_edit_lock``. This is the real H1 guard.
    """
    repo = SummariesRepo(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO knowledge_summaries
              (user_id, scope_type, scope_id, content, token_count, version)
            VALUES ($1, 'global', NULL, 'seed bio', 10, 1)
            """,
            test_user,
        )
    await _seed_passage(neo4j_driver, user_id=test_user, text="chat turn 1")

    # Regen #1.
    fake_llm_first = _mock_llm("First distinct regenerated bio output.")
    first = await regenerate_global_summary(
        user_id=test_user,
        model_source="user_model",
        model_ref="gpt-4o-mini",
        pool=pool,
        session_factory=_neo4j_session_factory(neo4j_driver),
        llm_client=fake_llm_first,
        summaries_repo=repo,
    )
    assert first.status == "regenerated", first

    history_after_first = await repo.list_versions(
        test_user, "global", None, limit=5
    )
    assert len(history_after_first) == 1
    assert history_after_first[0].edit_source == "regen"

    # Regen #2 — must NOT be blocked by user_edit_lock. The helper sees
    # a 'regen'-tagged history row from the previous call, not a
    # 'manual' one, so `_has_recent_manual_edit` returns False.
    fake_llm_second = _mock_llm(
        "Second distinct regenerated bio output about a separate topic."
    )
    second = await regenerate_global_summary(
        user_id=test_user,
        model_source="user_model",
        model_ref="gpt-4o-mini",
        pool=pool,
        session_factory=_neo4j_session_factory(neo4j_driver),
        llm_client=fake_llm_second,
        summaries_repo=repo,
    )
    assert second.status == "regenerated", (
        "H1 regression: second regen must not trip user_edit_lock — "
        "but got " + second.status
    )
    # Now two 'regen'-tagged history rows.
    history_after_second = await repo.list_versions(
        test_user, "global", None, limit=5
    )
    assert len(history_after_second) == 2
    assert all(row.edit_source == "regen" for row in history_after_second)


@pytest.mark.asyncio
async def test_manual_edit_still_arms_user_edit_lock(
    pool, neo4j_driver, test_user
):
    """Conjugate of the H1 test: a real user manual edit (via the
    PATCH path which defaults `edit_source='manual'`) MUST still arm
    the user_edit_lock for the next regen.
    """
    repo = SummariesRepo(pool)
    # Two upserts through the default (manual) path -> second write
    # creates a manual history row dated now().
    await repo.upsert(test_user, "global", None, "first manual bio")
    await repo.upsert(test_user, "global", None, "second manual bio with edits")
    await _seed_passage(neo4j_driver, user_id=test_user, text="raw chat")

    fake_llm = _mock_llm("unused — should not be called")
    result = await regenerate_global_summary(
        user_id=test_user,
        model_source="user_model",
        model_ref="gpt-4o-mini",
        pool=pool,
        session_factory=_neo4j_session_factory(neo4j_driver),
        llm_client=fake_llm,
        summaries_repo=repo,
    )
    assert result.status == "user_edit_lock"
    assert fake_llm.calls == []
