"""K18.8 — unit tests for the Mode 3 dispatcher flip.

The dispatcher in `app.context.builder` routes by
`project.extraction_enabled`. This commit (K18 commit 3) removes the
`NotImplementedError` branch and wires Mode 3 through the full
builder. These tests lock the routing so a future refactor can't
accidentally un-flip the switch.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.context.builder import ProjectNotFound, build_context
from app.db.models import Project


USER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _project(*, extraction_enabled: bool = True) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id=uuid4(),
        user_id=USER_ID,
        name="Test",
        description="",
        project_type="book",
        book_id=None,
        instructions="",
        extraction_enabled=extraction_enabled,
        extraction_status="disabled",
        embedding_model=None,
        extraction_config={},
        last_extracted_at=None,
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_no_project_routes_to_mode1(monkeypatch):
    m1 = AsyncMock(return_value=MagicMock(mode="no_project"))
    monkeypatch.setattr("app.context.builder.build_no_project_mode", m1)

    await build_context(
        summaries_repo=MagicMock(),
        projects_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project_id=None,
        message="hi",
    )
    m1.assert_awaited_once()


@pytest.mark.asyncio
async def test_extraction_disabled_routes_to_mode2(monkeypatch):
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(return_value=_project(extraction_enabled=False))

    m2 = AsyncMock(return_value=MagicMock(mode="static"))
    m3 = AsyncMock(return_value=MagicMock(mode="full"))
    monkeypatch.setattr("app.context.builder.build_static_mode", m2)
    monkeypatch.setattr("app.context.builder.build_full_mode", m3)

    await build_context(
        summaries_repo=MagicMock(),
        projects_repo=projects_repo,
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project_id=uuid4(),
        message="hi",
    )
    m2.assert_awaited_once()
    m3.assert_not_called()


@pytest.mark.asyncio
async def test_extraction_enabled_routes_to_mode3(monkeypatch):
    """K18.8 — this is the flip. Before this commit it raised
    NotImplementedError; now it runs Mode 3."""
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(return_value=_project(extraction_enabled=True))

    m2 = AsyncMock(return_value=MagicMock(mode="static"))
    m3 = AsyncMock(return_value=MagicMock(mode="full"))
    monkeypatch.setattr("app.context.builder.build_static_mode", m2)
    monkeypatch.setattr("app.context.builder.build_full_mode", m3)

    emb = MagicMock()
    result = await build_context(
        summaries_repo=MagicMock(),
        projects_repo=projects_repo,
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project_id=uuid4(),
        message="hi",
        embedding_client=emb,
    )
    m3.assert_awaited_once()
    m2.assert_not_called()
    # Embedding client threads through.
    _, kwargs = m3.await_args
    assert kwargs["embedding_client"] is emb


@pytest.mark.asyncio
async def test_missing_project_raises_not_found(monkeypatch):
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(return_value=None)

    with pytest.raises(ProjectNotFound):
        await build_context(
            summaries_repo=MagicMock(),
            projects_repo=projects_repo,
            glossary_client=MagicMock(),
            user_id=USER_ID,
            project_id=uuid4(),
            message="hi",
        )


# ── T5 (Context Budget Law D2): grounding intent gate routing ───────────────


@pytest.mark.asyncio
async def test_grounding_false_routes_full_eligible_to_static(monkeypatch):
    """The gate: an extraction-enabled (full-mode) project with grounding=False
    serves the LIGHT static path — skipping the expensive passage/semantic/LLM
    retrieval — instead of full mode. Default (grounding=True) still routes full."""
    p1 = _project(extraction_enabled=True)
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(return_value=p1)
    static = AsyncMock(return_value=MagicMock(mode="static"))
    full = AsyncMock(return_value=MagicMock(mode="full"))
    monkeypatch.setattr("app.context.builder.build_static_mode", static)
    monkeypatch.setattr("app.context.builder.build_full_mode", full)

    await build_context(
        summaries_repo=MagicMock(), projects_repo=projects_repo,
        glossary_client=MagicMock(), user_id=USER_ID, project_id=uuid4(),
        message="give me a plan", embedding_client=MagicMock(), grounding=False,
    )
    static.assert_awaited_once()
    full.assert_not_called()
    _, kwargs = static.await_args
    assert kwargs["project"] is p1


@pytest.mark.asyncio
async def test_grounding_false_routes_multi_to_light_first_project(monkeypatch):
    """A multi-KG union with grounding=False skips the expensive cross-project rank
    and serves the light static path for the first resolved project."""
    p1, p2 = _project(), _project()
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(side_effect=[p1, p2])
    multi = AsyncMock(return_value=MagicMock(mode="multi"))
    static = AsyncMock(return_value=MagicMock(mode="static"))
    monkeypatch.setattr("app.context.builder.build_multi_project_mode", multi)
    monkeypatch.setattr("app.context.builder.build_static_mode", static)

    await build_context(
        summaries_repo=MagicMock(), projects_repo=projects_repo,
        glossary_client=MagicMock(), user_id=USER_ID, project_id=None,
        message="what can you do", project_ids=[p1.project_id, p2.project_id],
        grounding=False,
    )
    static.assert_awaited_once()
    multi.assert_not_called()
    _, kwargs = static.await_args
    assert kwargs["project"] is p1


@pytest.mark.asyncio
async def test_grounding_false_with_no_project_still_mode1(monkeypatch):
    """No project + grounding=False → still the cheapest no_project mode (the gate
    doesn't change the no-project path)."""
    m1 = AsyncMock(return_value=MagicMock(mode="no_project"))
    monkeypatch.setattr("app.context.builder.build_no_project_mode", m1)
    await build_context(
        summaries_repo=MagicMock(), projects_repo=MagicMock(),
        glossary_client=MagicMock(), user_id=USER_ID, project_id=None,
        message="hi", grounding=False,
    )
    m1.assert_awaited_once()


# ── K21.12-BE (design D9): ContextBuildResponse carries the flag ────────────


def test_context_build_response_carries_tool_calling_enabled():
    """D9 — ContextBuildResponse is model_validate'd from BuiltContext
    via from_attributes, so the new tool_calling_enabled field must
    flow through to the HTTP response shape chat-service consumes.
    Both states round-trip; an older BuiltContext lacking the attribute
    falls back to the response default `True`."""
    from app.context.modes.no_project import BuiltContext
    from app.routers.context import ContextBuildResponse

    built_off = BuiltContext(
        mode="full", context="<memory/>", recent_message_count=20,
        token_count=3, tool_calling_enabled=False,
    )
    resp_off = ContextBuildResponse.model_validate(built_off)
    assert resp_off.tool_calling_enabled is False

    built_on = BuiltContext(
        mode="static", context="<memory/>", recent_message_count=50,
        token_count=3, tool_calling_enabled=True,
    )
    resp_on = ContextBuildResponse.model_validate(built_on)
    assert resp_on.tool_calling_enabled is True


def test_context_build_response_carries_canon_capture_enabled():
    """WS-4C Half A — the capture toggle crosses to chat-service on this same
    `model_validate(from_attributes)` wire. If the field is ever renamed on either
    side, from_attributes silently falls back to the response DEFAULT and capture
    goes permanently, silently off with nothing red. Pin both states + the default.

    The default is FALSE, unlike tool_calling_enabled's True: capture spends the
    user's BYOK tokens, so an unset value must never be read as consent."""
    from app.context.modes.no_project import BuiltContext
    from app.routers.context import ContextBuildResponse

    built_on = BuiltContext(
        mode="full", context="<memory/>", recent_message_count=20,
        token_count=3, canon_capture_enabled=True,
    )
    assert ContextBuildResponse.model_validate(built_on).canon_capture_enabled is True

    built_off = BuiltContext(
        mode="full", context="<memory/>", recent_message_count=20,
        token_count=3, canon_capture_enabled=False,
    )
    assert ContextBuildResponse.model_validate(built_off).canon_capture_enabled is False

    # A BuiltContext that never sets it (an older builder, or a renamed attribute)
    # must fail CLOSED, not inherit "spend the user's money".
    class _Legacy:
        mode, context, recent_message_count, token_count = "full", "", 20, 3

    assert ContextBuildResponse.model_validate(_Legacy()).canon_capture_enabled is False

    # Defaulting half: a builder result that never set the field still
    # validates, and the response defaults the flag to True.
    built_default = BuiltContext(
        mode="no_project", context="<memory/>", recent_message_count=50,
        token_count=3,
    )
    assert ContextBuildResponse.model_validate(
        built_default
    ).tool_calling_enabled is True


# ── Track B B1(2): multi-project (multi-KG) dispatch ─────────────────


@pytest.mark.asyncio
async def test_multiple_projects_route_to_multi_mode(monkeypatch):
    """>=2 readable projects union via the multi-project mode (not the single full mode)."""
    p1, p2 = _project(), _project()
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(side_effect=[p1, p2])
    multi = AsyncMock(return_value=MagicMock(mode="multi"))
    full = AsyncMock(return_value=MagicMock(mode="full"))
    monkeypatch.setattr("app.context.builder.build_multi_project_mode", multi)
    monkeypatch.setattr("app.context.builder.build_full_mode", full)

    await build_context(
        summaries_repo=MagicMock(), projects_repo=projects_repo,
        glossary_client=MagicMock(), user_id=USER_ID, project_id=None,
        message="hi", project_ids=[p1.project_id, p2.project_id],
    )
    multi.assert_awaited_once()
    full.assert_not_called()
    _, kwargs = multi.await_args
    assert kwargs["projects"] == [p1, p2]


@pytest.mark.asyncio
async def test_single_project_in_list_routes_to_single_mode(monkeypatch):
    """A project_ids of length 1 still uses the richer single-project full mode."""
    p1 = _project(extraction_enabled=True)
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(return_value=p1)
    multi = AsyncMock()
    full = AsyncMock(return_value=MagicMock(mode="full"))
    monkeypatch.setattr("app.context.builder.build_multi_project_mode", multi)
    monkeypatch.setattr("app.context.builder.build_full_mode", full)

    await build_context(
        summaries_repo=MagicMock(), projects_repo=projects_repo,
        glossary_client=MagicMock(), user_id=USER_ID, project_id=None,
        message="hi", project_ids=[p1.project_id],
    )
    full.assert_awaited_once()
    multi.assert_not_called()


@pytest.mark.asyncio
async def test_multi_skips_stale_ids_but_unions_the_readable(monkeypatch):
    """A stale/foreign id in the set is filtered; the >=2 readable ones still union."""
    p1, p2 = _project(), _project()
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(side_effect=[p1, None, p2])  # middle id is stale
    multi = AsyncMock(return_value=MagicMock(mode="multi"))
    monkeypatch.setattr("app.context.builder.build_multi_project_mode", multi)
    monkeypatch.setattr("app.context.builder.build_full_mode", AsyncMock())

    await build_context(
        summaries_repo=MagicMock(), projects_repo=projects_repo,
        glossary_client=MagicMock(), user_id=USER_ID, project_id=None,
        message="hi", project_ids=[p1.project_id, uuid4(), p2.project_id],
    )
    multi.assert_awaited_once()
    _, kwargs = multi.await_args
    assert kwargs["projects"] == [p1, p2]


@pytest.mark.asyncio
async def test_multi_all_stale_raises_not_found(monkeypatch):
    """If NONE of the requested projects resolve, it is a 404 (like the single path)."""
    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(return_value=None)
    monkeypatch.setattr("app.context.builder.build_multi_project_mode", AsyncMock())

    with pytest.raises(ProjectNotFound):
        await build_context(
            summaries_repo=MagicMock(), projects_repo=projects_repo,
            glossary_client=MagicMock(), user_id=USER_ID, project_id=None,
            message="hi", project_ids=[uuid4(), uuid4()],
        )
