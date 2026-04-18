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
