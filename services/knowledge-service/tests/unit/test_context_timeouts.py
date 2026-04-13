"""Unit tests for K6.1 — per-layer timeouts in the context builder.

If any layer exceeds its budget, the builder skips that layer and
continues with the remaining pieces. Metrics bump by exactly one
per timeout.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from app.context.modes.no_project import build_no_project_mode
from app.context.modes.static import build_static_mode
from app.db.models import Project, Summary
from app.metrics import layer_timeout_total


def _summary(scope: str, scope_id=None, content: str = "content") -> Summary:
    now = datetime.now(timezone.utc)
    return Summary(
        summary_id=uuid4(),
        user_id=uuid4(),
        scope_type=scope,
        scope_id=scope_id,
        content=content,
        token_count=1,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _project(user_id, book_id=None) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id=uuid4(),
        user_id=user_id,
        name="Test Project",
        description="",
        project_type="book",
        book_id=book_id if book_id is not None else uuid4(),
        instructions="be helpful",
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model=None,
        extraction_config={},
        last_extracted_at=None,
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_no_project_l0_timeout_returns_instructions_only(monkeypatch):
    """L0 too slow → bio omitted, builder still returns a valid block."""
    # Shrink the L0 budget so the test is fast.
    monkeypatch.setattr(settings, "context_l0_timeout_s", 0.05)

    slow_repo = AsyncMock()

    async def slow_get(*args, **kwargs):
        await asyncio.sleep(0.5)
        return _summary("global", content="should never appear")

    slow_repo.get = slow_get

    before = layer_timeout_total.labels(layer="l0")._value.get()
    built = await build_no_project_mode(slow_repo, uuid4())
    after = layer_timeout_total.labels(layer="l0")._value.get()

    assert built.mode == "no_project"
    assert "<user>" not in built.context
    assert "<instructions>" in built.context
    assert after == before + 1


@pytest.mark.asyncio
async def test_static_l1_timeout_skips_summary(monkeypatch):
    """L1 too slow → <summary> omitted, project block still emitted."""
    monkeypatch.setattr(settings, "context_l0_timeout_s", 0.5)
    monkeypatch.setattr(settings, "context_l1_timeout_s", 0.05)
    monkeypatch.setattr(settings, "context_glossary_timeout_s", 0.5)

    user_id = uuid4()
    project = _project(user_id)

    repo = AsyncMock()

    async def l1_slow(uid, scope, scope_id):
        if scope == "project":
            await asyncio.sleep(0.5)
            return _summary("project", scope_id, content="slow")
        return None  # L0 returns fast

    repo.get = l1_slow

    glossary_client = AsyncMock()
    glossary_client.select_for_context = AsyncMock(return_value=[])

    before = layer_timeout_total.labels(layer="l1")._value.get()
    built = await build_static_mode(
        repo,
        glossary_client,
        user_id=user_id,
        project=project,
        message="hello",
    )
    after = layer_timeout_total.labels(layer="l1")._value.get()

    assert built.mode == "static"
    assert "<project" in built.context
    assert "<summary>" not in built.context
    assert after == before + 1


@pytest.mark.asyncio
async def test_static_glossary_timeout_skips_glossary(monkeypatch):
    monkeypatch.setattr(settings, "context_l0_timeout_s", 0.5)
    monkeypatch.setattr(settings, "context_l1_timeout_s", 0.5)
    monkeypatch.setattr(settings, "context_glossary_timeout_s", 0.05)

    user_id = uuid4()
    project = _project(user_id, book_id=uuid4())

    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)

    # Patch the selector call site inside static.py so we don't have
    # to fake the full client plumbing.
    async def slow_glossary(*args, **kwargs):
        await asyncio.sleep(0.5)
        return []

    with patch(
        "app.context.modes.static.select_glossary_for_context",
        side_effect=slow_glossary,
    ):
        before = layer_timeout_total.labels(layer="glossary")._value.get()
        built = await build_static_mode(
            repo,
            AsyncMock(),
            user_id=user_id,
            project=project,
            message="hello",
        )
        after = layer_timeout_total.labels(layer="glossary")._value.get()

    assert built.mode == "static"
    assert "<glossary>" not in built.context
    assert after == before + 1
