"""Router tests for Chat & AI settings (spec §6) — mock-pool paths.

Covers ai-prefs GET/PATCH and the effective-settings resolver for the
studio-tool context (no session_id → Session tier skipped). SQL correctness of
the deep-merge/version guard is pinned separately in test_ai_settings_db.py
(real Postgres)."""
from __future__ import annotations

import pytest

from app.routers import ai_settings


class _FakeProvider:
    def __init__(self, default=None, live=True):
        self._default = default
        self._live = live

    async def get_default_model(self, capability, user_id):
        return self._default

    async def is_live(self, model_source, model_ref, user_id):
        return self._live


@pytest.fixture
def fake_provider(monkeypatch):
    prov = _FakeProvider()
    monkeypatch.setattr(ai_settings, "get_provider_client", lambda: prov)
    return prov


async def test_get_ai_prefs_defaults_when_no_row(client, mock_pool):
    mock_pool.fetchrow.return_value = None
    resp = await client.get("/v1/chat/ai-prefs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["context"] == {"mode": "auto"}
    assert body["version"] == 0
    assert body["behavior"] == {}


async def test_patch_ai_prefs_merges_and_bumps_version(client, mock_pool):
    # no existing row → insert; version goes 0 → 1
    conn = mock_pool._conn
    conn.fetchrow.return_value = None
    resp = await client.patch(
        "/v1/chat/ai-prefs", json={"behavior": {"temperature": 0.8}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["behavior"]["temperature"] == 0.8
    assert body["version"] == 1


async def test_patch_ai_prefs_version_conflict_412(client, mock_pool):
    conn = mock_pool._conn
    # existing row at version 5; client sends If-Match: 2 → conflict
    conn.fetchrow.return_value = {
        "behavior": "{}", "grounding": "{}", "voice": "{}",
        "context": '{"mode":"auto"}', "version": 5,
    }
    resp = await client.patch(
        "/v1/chat/ai-prefs",
        json={"behavior": {"temperature": 0.8}},
        headers={"If-Match": "2"},
    )
    assert resp.status_code == 412


async def test_effective_settings_studio_context_skips_session(client, mock_pool, fake_provider):
    # no session_id (studio tool) → Session tier absent; no account defaults →
    # every model role resolves to no_model_configured, behavior shows System.
    mock_pool.fetchrow.return_value = None  # get_prefs → defaults
    resp = await client.get("/v1/chat/effective-settings?book_id=abc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["context_ref"] == {"book_id": "abc", "session_id": None}
    assert body["models"]["chat"]["source_tier"] == "no_model_configured"
    # de-silenced System defaults are visible, not blank
    assert body["behavior"]["reasoning_effort"]["effective_value"] == "off"
    assert body["behavior"]["reasoning_effort"]["source_tier"] == "system"
    assert body["behavior"]["permission_mode"]["effective_value"] == "write"
    assert body["grounding"]["grounding_enabled"]["effective_value"] is True
    assert body["context"]["mode"]["effective_value"] == "auto"


async def test_effective_settings_account_model_resolves(client, mock_pool, fake_provider):
    mock_pool.fetchrow.return_value = None
    fake_provider._default = ("user_model", "acct-model")
    fake_provider._live = True
    resp = await client.get("/v1/chat/effective-settings")
    assert resp.status_code == 200
    body = resp.json()
    chat = body["models"]["chat"]
    assert chat["effective_value"] == {"model_source": "user_model", "model_ref": "acct-model"}
    assert chat["source_tier"] == "account"
