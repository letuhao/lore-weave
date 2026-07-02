"""Wiring test for Track 4 P0 salience recording in the context router.

A silent-no-op guard needs a wiring test: prove the /internal/context/build
handler actually calls record_accesses with the surfaced ids (and skips it when
there's no project / nothing surfaced). Without this, the wire could drift and
telemetry would stop while every other test stayed green.
"""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.context.modes.no_project import BuiltContext
from app.routers.context import ContextBuildRequest, build


def _built(surfaced):
    return BuiltContext(
        mode="static", context="<memory/>", recent_message_count=20,
        token_count=1, surfaced_entity_ids=surfaced,
    )


async def _call(req, surfaced, entity_access_repo):
    with patch("app.routers.context.build_context",
               AsyncMock(return_value=_built(surfaced))):
        return await build(
            req,
            summaries_repo=AsyncMock(), projects_repo=AsyncMock(),
            glossary_client=AsyncMock(), embedding_client=AsyncMock(),
            llm_client=AsyncMock(), working_memory_repo=AsyncMock(),
            entity_access_repo=entity_access_repo,
        )


@pytest.mark.asyncio
async def test_records_surfaced_entities_when_project_scoped():
    user_id, project_id = uuid4(), uuid4()
    req = ContextBuildRequest(user_id=user_id, project_id=project_id, message="hi")
    repo = AsyncMock()

    await _call(req, ["e1", "e2"], repo)
    await asyncio.sleep(0)  # let the fire-and-forget task run

    repo.record_accesses.assert_awaited_once_with(
        user_id, project_id, ["e1", "e2"], session_id=None,
    )


@pytest.mark.asyncio
async def test_no_record_when_no_project():
    req = ContextBuildRequest(user_id=uuid4(), project_id=None, message="hi")
    repo = AsyncMock()

    await _call(req, ["e1"], repo)
    await asyncio.sleep(0)

    repo.record_accesses.assert_not_called()


@pytest.mark.asyncio
async def test_no_record_when_nothing_surfaced():
    req = ContextBuildRequest(user_id=uuid4(), project_id=uuid4(), message="hi")
    repo = AsyncMock()

    await _call(req, [], repo)
    await asyncio.sleep(0)

    repo.record_accesses.assert_not_called()
