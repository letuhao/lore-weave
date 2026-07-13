"""DBT-11 / D-R14 — AuthClient.get_user_timezone: sourcing, caching, fail-safe.

Proves the tz SOURCE side of local_date bucketing (the tz→day math is covered by
test_local_date_helper): a 200 with a timezone is returned + cached; a missing key or
a failure degrades to None (⇒ compute_local_date → UTC), and the write never blocks.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.client.auth_client import AuthClient, resolve_local_date


def _mock_client(status: int, body: dict | None = None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body or {}
    http = AsyncMock()
    http.get.return_value = resp
    http.__aenter__ = AsyncMock(return_value=http)
    http.__aexit__ = AsyncMock(return_value=False)
    return http


@pytest.mark.asyncio
@patch("app.client.auth_client.build_internal_client")
async def test_returns_timezone_and_caches_it(mock_cls):
    http = _mock_client(200, {"user_id": "u1", "timezone": "Asia/Tokyo"})
    mock_cls.return_value = http

    c = AuthClient()
    assert await c.get_user_timezone("u1") == "Asia/Tokyo"
    # A second call for the same user is served from cache — no second fetch.
    assert await c.get_user_timezone("u1") == "Asia/Tokyo"
    http.get.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.client.auth_client.build_internal_client")
async def test_missing_timezone_key_is_none_and_negatively_cached(mock_cls):
    http = _mock_client(200, {"user_id": "u1", "display_name": "X"})  # no timezone
    mock_cls.return_value = http

    c = AuthClient()
    assert await c.get_user_timezone("u1") is None
    assert await c.get_user_timezone("u1") is None  # negative result cached too
    http.get.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.client.auth_client.build_internal_client")
async def test_blank_timezone_is_treated_as_unset(mock_cls):
    mock_cls.return_value = _mock_client(200, {"timezone": ""})
    assert await AuthClient().get_user_timezone("u1") is None


@pytest.mark.asyncio
@patch("app.client.auth_client.build_internal_client")
async def test_non_200_degrades_to_none(mock_cls):
    mock_cls.return_value = _mock_client(503)
    assert await AuthClient().get_user_timezone("u1") is None


@pytest.mark.asyncio
@patch("app.client.auth_client.build_internal_client")
async def test_transport_exception_degrades_to_none(mock_cls):
    mock_cls.side_effect = RuntimeError("auth down")
    # Must NOT raise into the message-write path.
    assert await AuthClient().get_user_timezone("u1") is None


@pytest.mark.asyncio
@patch("app.client.auth_client.get_auth_client")
async def test_resolve_local_date_uses_the_users_timezone(mock_get):
    client = AsyncMock()
    client.get_user_timezone.return_value = "Asia/Tokyo"
    mock_get.return_value = client
    # Late 23:30 UTC on the 10th → Tokyo is already the 11th. resolve_local_date
    # uses "now", so we can only assert it's a date; the tz math is unit-tested
    # separately. Here we assert it doesn't crash and returns a date.
    assert isinstance(await resolve_local_date("u1"), date)
    client.get_user_timezone.assert_awaited_once_with("u1")
