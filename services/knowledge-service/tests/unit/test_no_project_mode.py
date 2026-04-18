import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.config import settings
from app.context.formatters.token_counter import estimate_tokens
from app.context.modes.no_project import build_no_project_mode
from app.db.models import Summary


def _summary(content: str) -> Summary:
    now = datetime.now(timezone.utc)
    return Summary(
        summary_id=uuid4(),
        user_id=uuid4(),
        scope_type="global",
        scope_id=None,
        content=content,
        token_count=estimate_tokens(content),
        version=1,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_no_summary_returns_instructions_only():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)

    built = await build_no_project_mode(repo, uuid4())
    assert built.mode == "no_project"
    # D-T2-03: builder now reads settings.recent_message_count, which
    # is the knob shared with chat-service's fallback. Tests use the
    # same source so a tune doesn't require test edits.
    assert built.recent_message_count == settings.recent_message_count
    assert built.token_count > 0
    assert "<user>" not in built.context
    assert "<instructions>" in built.context
    # Valid XML
    ET.fromstring(built.context)


@pytest.mark.asyncio
async def test_with_summary_includes_user_element():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_summary("I am a fantasy novelist writing a 5-book series."))

    built = await build_no_project_mode(repo, uuid4())
    assert "<user>" in built.context
    assert "fantasy novelist" in built.context
    root = ET.fromstring(built.context)
    assert root.tag == "memory"
    assert root.attrib == {"mode": "no_project"}
    user = root.find("user")
    assert user is not None
    assert "fantasy novelist" in (user.text or "")


@pytest.mark.asyncio
async def test_summary_with_xml_characters_is_escaped():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_summary('<script>alert("xss")</script> & friends'))

    built = await build_no_project_mode(repo, uuid4())
    # Raw XML must not contain the unescaped opening tag
    assert "<script>" not in built.context
    assert "&lt;script&gt;" in built.context
    # And the whole block must still be valid XML
    root = ET.fromstring(built.context)
    user = root.find("user")
    assert user is not None
    # ElementTree un-escapes on parse
    assert "<script>" in (user.text or "")


@pytest.mark.asyncio
async def test_whitespace_only_summary_treated_as_missing():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_summary("   \t\n   "))

    built = await build_no_project_mode(repo, uuid4())
    assert "<user>" not in built.context


@pytest.mark.asyncio
async def test_cjk_summary_rendered():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_summary("我是一位武俠小說家"))

    built = await build_no_project_mode(repo, uuid4())
    root = ET.fromstring(built.context)
    user = root.find("user")
    assert user is not None
    assert "武俠小說家" in (user.text or "")
