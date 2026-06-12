"""Phase-2 notification i18n: the translation completion notification must carry a
stable i18n_key + params in metadata (client localizes), while keeping the English
title as a fallback. (LW-PLAN notifications i18n.)"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.chapter_worker import _send_translation_notification


def _capture_post():
    """Returns (captured dict, AsyncClient context-manager mock)."""
    captured: dict = {}
    client = MagicMock()

    async def fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        return MagicMock(status_code=200)

    client.post = AsyncMock(side_effect=fake_post)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return captured, cm


@pytest.mark.asyncio
async def test_completed_notification_carries_i18n_key_and_params():
    captured, cm = _capture_post()
    with patch("app.workers.chapter_worker.httpx.AsyncClient", return_value=cm):
        await _send_translation_notification("u1", "j1", "Dracula", "completed", 3, 0)
    meta = captured["json"]["metadata"]
    assert meta["i18n_key"] == "notif.translation.completed"
    assert meta["i18n_params"] == {"count": 3, "book": "Dracula"}
    # English title kept as fallback for older clients.
    assert "Translation complete" in captured["json"]["title"]


@pytest.mark.asyncio
async def test_partial_notification_carries_i18n_key_and_params():
    captured, cm = _capture_post()
    with patch("app.workers.chapter_worker.httpx.AsyncClient", return_value=cm):
        await _send_translation_notification("u1", "j1", "Dracula", "partial", 2, 1)
    meta = captured["json"]["metadata"]
    assert meta["i18n_key"] == "notif.translation.partial"
    assert meta["i18n_params"] == {"done": 2, "failed": 1}


@pytest.mark.asyncio
async def test_failed_notification_carries_i18n_key_and_params():
    captured, cm = _capture_post()
    with patch("app.workers.chapter_worker.httpx.AsyncClient", return_value=cm):
        await _send_translation_notification("u1", "j1", "Dracula", "failed", 0, 1)
    meta = captured["json"]["metadata"]
    assert meta["i18n_key"] == "notif.translation.failed"
    assert meta["i18n_params"] == {"book": "Dracula"}
