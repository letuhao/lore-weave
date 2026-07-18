"""Unit tests for kg_project_create (D-KG-LF-PROJECT-CREATE-MCP).

The security-critical property: a book-bound project create is BOOK-OWNER-ONLY,
with no existence oracle (a non-owner gets the same generic refusal). Book-less
create is a personal project (no grant check). Idempotency is delegated to
create_or_get (covered by the projects-repo tests); here we prove the gate +
dispatch wiring through execute_tool with fakes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from loreweave_grants import GrantLevel

from app.tools.executor import ToolContext, execute_tool

_USER = uuid4()
_BOOK = uuid4()


def _mk_ctx(*, user_id=_USER, grant_client=None, projects_repo=None) -> ToolContext:
    return ToolContext(
        user_id=user_id,
        project_id=None,  # project-create runs with no project in scope
        session_id="sess-proj",
        projects_repo=projects_repo or AsyncMock(),
        pending_facts_repo=AsyncMock(),
        embedding_client=AsyncMock(),
        redis=None,
        grant_client=grant_client or AsyncMock(),
        graph_views_repo=AsyncMock(),
        graph_schemas_repo=AsyncMock(),
        triage_repo=AsyncMock(),
        ontology_resolver=AsyncMock(),
        ontology_mutations_repo=AsyncMock(),
    )


def _fake_project(*, book_id=None):
    return SimpleNamespace(
        project_id=uuid4(), name="Dracula KG", project_type="book", book_id=book_id
    )


@pytest.mark.asyncio
async def test_book_bound_create_denied_for_non_owner():
    """A non-owner of the book gets a tool error and NO project is created
    (book-owner-only, no existence oracle)."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.VIEW)  # grantee, not owner
    repo = AsyncMock()
    ctx = _mk_ctx(grant_client=grant, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "Dracula KG", "book_id": str(_BOOK)}
    )
    assert not res.success
    assert "owner" in res.error.lower()
    repo.create_or_get.assert_not_called()


@pytest.mark.asyncio
async def test_book_bound_create_succeeds_for_owner():
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.OWNER)
    repo = AsyncMock()
    proj = _fake_project(book_id=_BOOK)
    repo.create_or_get = AsyncMock(return_value=(proj, True))
    ctx = _mk_ctx(grant_client=grant, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "Dracula KG", "book_id": str(_BOOK)}
    )
    assert res.success, res.error
    assert res.result["project_id"] == str(proj.project_id)
    assert res.result["created"] is True
    assert res.result["book_id"] == str(_BOOK)


@pytest.mark.asyncio
async def test_book_less_create_skips_grant_check():
    """A book-less personal project needs no grant client call."""
    grant = AsyncMock()
    repo = AsyncMock()
    repo.create_or_get = AsyncMock(return_value=(_fake_project(), False))
    ctx = _mk_ctx(grant_client=grant, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "Scratchpad", "project_type": "general"}
    )
    assert res.success, res.error
    assert res.result["created"] is False
    grant.resolve_grant.assert_not_called()


@pytest.mark.asyncio
async def test_bad_book_id_is_tool_error():
    ctx = _mk_ctx()
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "X", "book_id": "not-a-uuid"}
    )
    assert not res.success
    assert "book_id" in res.error.lower()


@pytest.mark.asyncio
async def test_smuggled_scope_arg_rejected():
    """extra='forbid' — a hallucinated user_id/project_id is a tool error, not a
    silent scope override."""
    ctx = _mk_ctx()
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "X", "user_id": "smuggled"}
    )
    assert not res.success


# ── kg_project_list (W0 #4a — the "no project in scope" discovery tool) ────────


def _fake_listed_project(*, name="P", archived=False):
    return SimpleNamespace(
        project_id=uuid4(),
        name=name,
        project_type="book",
        book_id=None,
        is_archived=archived,
    )


@pytest.mark.asyncio
async def test_project_list_is_owner_scoped_and_shaped():
    """kg_project_list serves the caller's OWN projects through the repo's
    user_id-filtered list, returning the compact discovery shape (id/name/
    type/book) the #4a error directive points the model at."""
    repo = AsyncMock()
    p1, p2 = _fake_listed_project(name="A"), _fake_listed_project(name="B")
    repo.list = AsyncMock(return_value=[p1, p2])
    ctx = _mk_ctx(projects_repo=repo)
    res = await execute_tool(ctx, "kg_project_list", {})
    assert res.success, res.error
    # the repo was queried for THIS caller only (identity from the envelope ctx)
    assert repo.list.await_args.args[0] == _USER
    names = [p["name"] for p in res.result["projects"]]
    assert names == ["A", "B"]
    assert res.result["projects"][0]["project_id"] == str(p1.project_id)
    assert res.result["more"] is False


@pytest.mark.asyncio
async def test_project_list_signals_overflow_and_respects_limit():
    """The repo fetches limit+1 to signal more pages — the tool must slice to
    `limit` and set more=True."""
    repo = AsyncMock()
    repo.list = AsyncMock(return_value=[_fake_listed_project() for _ in range(3)])
    ctx = _mk_ctx(projects_repo=repo)
    res = await execute_tool(ctx, "kg_project_list", {"limit": 2})
    assert res.success, res.error
    assert len(res.result["projects"]) == 2
    assert res.result["more"] is True


# ── kg_project_set_embedding_model (F6 — Track D liveness eval) ──────────────────
#
# The gap this tool closes: an agent could kg_project_create → kg_run_benchmark →
# kg_build_graph, but the ONE step between create and benchmark — setting the project's
# embedding model — existed only as a REST route behind the Build-KG dialog. So every
# agent-created project dead-ended at "run extraction setup once in the ... dialog", an
# instruction a tool-calling model cannot act on. kg_build_graph was, in effect,
# unreachable by an agent.

_PROJECT = uuid4()


def _mk_project_ctx(*, user_id=_USER, projects_repo=None, embedding_client=None) -> ToolContext:
    ctx = _mk_ctx(user_id=user_id, projects_repo=projects_repo)
    return type(ctx)(**{**ctx.__dict__, "project_id": _PROJECT})


def _fake_full_project(*, embedding_model=None, embedding_dimension=None,
                       extraction_status="disabled"):
    return SimpleNamespace(
        project_id=_PROJECT, name="Dracula KG", project_type="book", book_id=_BOOK,
        embedding_model=embedding_model, embedding_dimension=embedding_dimension,
        extraction_status=extraction_status,
    )


@pytest.mark.asyncio
async def test_set_embedding_model_probes_dimension_and_persists(monkeypatch):
    """The caller never knows the vector dimension — the tool probes the model for it
    and stores the pair, exactly as the REST route does."""
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_USER, _BOOK))
    repo.get = AsyncMock(return_value=_fake_full_project())
    repo.update = AsyncMock(
        return_value=_fake_full_project(embedding_model="model-uuid", embedding_dimension=1024)
    )
    monkeypatch.setattr(
        "app.clients.embedding_client.probe_embedding_dimension",
        AsyncMock(return_value=1024),
    )
    ctx = _mk_project_ctx(projects_repo=repo)

    res = await execute_tool(
        ctx, "kg_project_set_embedding_model", {"embedding_model": "model-uuid"}
    )
    assert res.success, res.error
    assert res.result["changed"] is True
    assert res.result["embedding_dimension"] == 1024
    # the model+dimension are written as a PAIR (a model-less-but-dimensioned row is a bug)
    patch = repo.update.await_args.args[2]
    assert patch.embedding_model == "model-uuid"
    assert patch.embedding_dimension == 1024
    # and the agent is told what to do next — no dialog
    assert "kg_run_benchmark" in res.result["note"]


@pytest.mark.asyncio
async def test_set_embedding_model_is_idempotent_same_value(monkeypatch):
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_USER, _BOOK))
    repo.get = AsyncMock(
        return_value=_fake_full_project(embedding_model="m1", embedding_dimension=1024)
    )
    probe = AsyncMock(return_value=1024)
    monkeypatch.setattr("app.clients.embedding_client.probe_embedding_dimension", probe)
    ctx = _mk_project_ctx(projects_repo=repo)

    res = await execute_tool(ctx, "kg_project_set_embedding_model", {"embedding_model": "m1"})
    assert res.success and res.result["changed"] is False
    repo.update.assert_not_awaited()  # no write
    probe.assert_not_awaited()  # and no needless paid/embedding round-trip


@pytest.mark.asyncio
async def test_changing_model_on_a_built_graph_is_refused_not_silently_orphaning(monkeypatch):
    """D-EMB-MODEL-REF-04: changing the model on a project that already has a graph would
    leave its passages in Neo4j tagged with the OLD model while retrieval queries the NEW
    vector space — silent zero-recall. That path deletes vectors, so it stays a
    confirm-gated REST op; this Tier-A tool must refuse and say where to go."""
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_USER, _BOOK))
    repo.get = AsyncMock(
        return_value=_fake_full_project(
            embedding_model="old", embedding_dimension=1024, extraction_status="completed"
        )
    )
    monkeypatch.setattr(
        "app.clients.embedding_client.probe_embedding_dimension", AsyncMock(return_value=1024)
    )
    ctx = _mk_project_ctx(projects_repo=repo)

    res = await execute_tool(ctx, "kg_project_set_embedding_model", {"embedding_model": "new"})
    assert not res.success
    assert "orphan" in res.error and "confirm=true" in res.error
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_dimension_is_rejected_before_any_write(monkeypatch):
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_USER, _BOOK))
    repo.get = AsyncMock(return_value=_fake_full_project())
    monkeypatch.setattr(
        "app.clients.embedding_client.probe_embedding_dimension", AsyncMock(return_value=777)
    )
    ctx = _mk_project_ctx(projects_repo=repo)

    res = await execute_tool(ctx, "kg_project_set_embedding_model", {"embedding_model": "weird"})
    assert not res.success
    assert "777" in res.error and "vector index" in res.error
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_failure_names_the_discovery_tool(monkeypatch):
    """A bad ref must not surface a raw provider error — it must tell the model how to
    find a real embedding model."""
    from app.clients.embedding_client import EmbeddingError

    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_USER, _BOOK))
    repo.get = AsyncMock(return_value=_fake_full_project())
    monkeypatch.setattr(
        "app.clients.embedding_client.probe_embedding_dimension",
        AsyncMock(side_effect=EmbeddingError("not an embedding model")),
    )
    ctx = _mk_project_ctx(projects_repo=repo)

    res = await execute_tool(ctx, "kg_project_set_embedding_model", {"embedding_model": "chat-m"})
    assert not res.success
    assert "settings_list_models" in res.error
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_owner_cannot_set_the_projects_embedding_model():
    """A book collaborator resolves an EDIT grant but is NOT the project owner — the repo
    update is owner-scoped, so the tool refuses before it writes (no oracle)."""
    other = uuid4()
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(other, _BOOK))  # owner is someone else
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)
    ctx = _mk_ctx(user_id=_USER, grant_client=grant, projects_repo=repo)
    ctx = type(ctx)(**{**ctx.__dict__, "project_id": _PROJECT})

    res = await execute_tool(ctx, "kg_project_set_embedding_model", {"embedding_model": "m"})
    assert not res.success
    assert "owner" in res.error
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_graph_error_names_the_unblocking_tools_not_a_dialog():
    """The F6 regression. kg_build_graph's precondition error is the ONLY instruction a
    tool-calling model gets; it used to say 'run extraction setup once in the Build
    Knowledge Graph dialog' — which an agent cannot do, and which named no tool."""
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_USER, _BOOK))
    repo.get = AsyncMock(return_value=_fake_full_project(embedding_model=None))
    ctx = _mk_project_ctx(projects_repo=repo)

    res = await execute_tool(
        ctx, "kg_build_graph", {"llm_model": str(uuid4()), "scope": "glossary_sync"}
    )
    assert not res.success
    assert "kg_project_set_embedding_model" in res.error
    assert "kg_run_benchmark" in res.error
    assert "dialog" not in res.error.lower()
