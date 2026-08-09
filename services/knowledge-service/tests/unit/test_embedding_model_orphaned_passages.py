"""D-EMB-MODEL-REF-04 — the two ways a model change could orphan its vectors.

Both were live-verified as BROKEN on 2026-07-23 while executing K7 (`kg_build target=graph`)
against the running stack, and both defeat the SAME guard from opposite ends:

  A. THE PURGE DIDN'T PURGE. `_delete_project_graph`'s `_GRAPH_LABELS` is
     ["Entity","Event","Fact","ExtractionSource"] — no `:Passage`, the node that actually
     carries the embedding vector. So `PUT /embedding-model?confirm=true`, whose entire
     reason to exist is "delete the stale vectors first", deleted everything EXCEPT the
     vectors. Its own inline comment asserted the opposite ("the graph delete above also
     dropped any stale-dimension passages"). Proven by running that exact label loop over a
     synthetic tenant in Neo4j: the `:Passage` node was the only survivor.

  B. THE GUARD ASKED THE WRONG COLUMN. Three call sites tested
     `extraction_status != 'disabled'` as "this project has a graph". But
     `POST /extraction/disable` sets `'disabled'` while explicitly PRESERVING the graph
     (it returns `graph_preserved: true`), so a vector-full project reads as empty, the
     guard opens, and the model swaps with no confirm and no purge.

A defeats the confirm path; B routes around it. Fixing one alone leaves the hole open.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

_USER = uuid4()
_PROJECT = uuid4()


# ── A. the purge must reach :Passage ──────────────────────────────────────────

def _mock_neo4j():
    result = AsyncMock()
    result.single = AsyncMock(return_value={"deleted": 3})
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, session


class TestGraphDeletePassageScope:

    @pytest.mark.asyncio
    async def test_a_model_change_purges_the_passages(self):
        from app.routers.public.extraction import _delete_project_graph

        cm, _ = _mock_neo4j()
        purge = AsyncMock(return_value=7)
        with patch("app.routers.public.extraction.neo4j_session", return_value=cm), \
             patch("app.db.neo4j_repos.passages.delete_all_passages_for_project", purge):
            total = await _delete_project_graph(_USER, _PROJECT, include_passages=True)

        purge.assert_awaited_once()
        assert purge.await_args.kwargs["project_id"] == str(_PROJECT)
        assert total == 4 * 3 + 7, (
            "the passage purge must be COUNTED in the reported deletion total — the route "
            "reports nodes_deleted to the user"
        )

    @pytest.mark.asyncio
    async def test_a_plain_graph_delete_leaves_passages_alone(self):
        """NOT an oversight — the default is deliberate.

        delete-graph and rebuild do not change the vector space, so the existing passages
        stay VALID. They also include chat- and glossary-sourced chunks that extraction
        cannot rebuild, so purging them there would be unrecoverable data loss for no gain.
        """
        from app.routers.public.extraction import _delete_project_graph

        cm, _ = _mock_neo4j()
        purge = AsyncMock(return_value=7)
        with patch("app.routers.public.extraction.neo4j_session", return_value=cm), \
             patch("app.db.neo4j_repos.passages.delete_all_passages_for_project", purge):
            total = await _delete_project_graph(_USER, _PROJECT)

        purge.assert_not_awaited()
        assert total == 4 * 3

    def test_passage_is_not_in_the_label_list(self):
        # Pins the shape the fix relies on: :Passage is purged through the flag, NOT by
        # being added to the label list (which would make the plain delete destructive).
        # The list moved to the maintenance repo with its query (plan T17); the GUARD
        # follows it, because what it protects — a delete/rebuild silently destroying
        # chat- and glossary-sourced chunks extraction cannot rebuild — is unchanged by
        # the move, and was proven live on 2026-07-23.
        from app.db.neo4j_repos.maintenance import PROJECT_GRAPH_LABELS

        assert "Passage" not in PROJECT_GRAPH_LABELS


# ── B. the guard must ask Neo4j, not extraction_status ────────────────────────

def _project(*, status: str, embedding_model: str | None = "old-model"):
    from app.db.models import Project

    return Project(
        project_id=_PROJECT, user_id=_USER, name="T", description="",
        project_type="translation", book_id=uuid4(), instructions="",
        extraction_enabled=False, extraction_status=status,
        extraction_config={}, embedding_model=embedding_model,
        estimated_cost_usd=Decimal("0"), actual_cost_usd=Decimal("0"),
        is_archived=False, version=1,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


class TestPassageExistenceProbe:

    @pytest.mark.asyncio
    async def test_no_neo4j_configured_means_nothing_to_orphan(self):
        from app.db.neo4j_repos.graph_state import project_has_embedded_passages

        with patch("app.config.settings.neo4j_uri", ""):
            assert await project_has_embedded_passages(_USER, _PROJECT) is False

    @pytest.mark.asyncio
    async def test_an_unreachable_neo4j_FAILS_CLOSED(self):
        """The asymmetry that decides the default: a wrong "no vectors" silently destroys
        a project's retrieval; a wrong "has vectors" only routes to the confirm path."""
        from app.db.neo4j_repos.graph_state import project_has_embedded_passages

        with patch("app.config.settings.neo4j_uri", "bolt://x"), \
             patch("app.db.neo4j.neo4j_session", side_effect=RuntimeError("down")):
            assert await project_has_embedded_passages(_USER, _PROJECT) is True

    @pytest.mark.asyncio
    async def test_reports_true_when_a_passage_exists(self):
        from app.db.neo4j_repos.graph_state import project_has_embedded_passages

        cm, _ = _mock_neo4j()
        with patch("app.config.settings.neo4j_uri", "bolt://x"), \
             patch("app.db.neo4j.neo4j_session", return_value=cm), \
             patch("app.db.neo4j_repos.passages.project_has_passages",
                   AsyncMock(return_value=True)):
            assert await project_has_embedded_passages(_USER, _PROJECT) is True

    @pytest.mark.asyncio
    async def test_reports_false_when_the_project_is_empty(self):
        from app.db.neo4j_repos.graph_state import project_has_embedded_passages

        cm, _ = _mock_neo4j()
        with patch("app.config.settings.neo4j_uri", "bolt://x"), \
             patch("app.db.neo4j.neo4j_session", return_value=cm), \
             patch("app.db.neo4j_repos.passages.project_has_passages",
                   AsyncMock(return_value=False)):
            assert await project_has_embedded_passages(_USER, _PROJECT) is False


class TestToolGuardUsesPassagesNotStatus:
    """The regression that motivated the whole fix, at the Tier-A tool — the surface an
    AGENT can reach without a human ever seeing a confirm card."""

    async def _set_model(self, *, status: str, has_passages: bool):
        from app.tools.executor import ToolExecutionError
        from app.tools.project_tools import (
            KgProjectSetEmbeddingModelArgs,
            _handle_kg_project_set_embedding_model,
        )

        ctx = MagicMock()
        ctx.user_id = _USER
        ctx.project_id = _PROJECT
        ctx.projects_repo.get = AsyncMock(return_value=_project(status=status))
        ctx.projects_repo.update = AsyncMock(
            return_value=_project(status=status, embedding_model="new-model"))

        args = KgProjectSetEmbeddingModelArgs(embedding_model="new-model")
        with patch("app.tools.graph_schema_tools._resolve_project_owner_and_level",
                   AsyncMock(return_value=(_USER, 4))), \
             patch("app.db.neo4j_repos.graph_state.project_has_embedded_passages",
                   AsyncMock(return_value=has_passages)), \
             patch("app.clients.embedding_client.probe_embedding_dimension",
                   AsyncMock(return_value=1024)):
            try:
                return "OK", await _handle_kg_project_set_embedding_model(ctx, args)
            except ToolExecutionError as exc:
                return "REFUSED", str(exc)

    @pytest.mark.asyncio
    async def test_disabled_but_graph_PRESERVED_is_refused(self):
        # THE BUG. `POST /extraction/disable` leaves exactly this state: status='disabled',
        # graph intact. Under the old `extraction_status` guard this returned OK and
        # orphaned every vector.
        st, msg = await self._set_model(status="disabled", has_passages=True)
        assert st == "REFUSED", (
            "a project whose vectors are still in Neo4j must be routed to the "
            "confirm-gated purge, whatever its extraction_status says"
        )
        assert "confirm=true" in msg, "the refusal must name the path that unblocks it"

    @pytest.mark.asyncio
    async def test_a_genuinely_empty_project_can_still_be_set(self):
        # The other half — the guard must not become a wall. Without this the ON case
        # above could pass by refusing everything.
        st, _ = await self._set_model(status="disabled", has_passages=False)
        assert st == "OK"

    @pytest.mark.asyncio
    async def test_status_ready_with_no_passages_is_allowed(self):
        # The converse of the bug: 'ready' no longer implies "has vectors" either. The
        # question is only ever "is there something to orphan".
        st, _ = await self._set_model(status="ready", has_passages=False)
        assert st == "OK"
