"""Router tests for Chat & AI settings (spec §6) — mock-pool paths.

Covers ai-prefs GET/PATCH and the effective-settings resolver for the
studio-tool context (no session_id → Session tier skipped). SQL correctness of
the deep-merge/version guard is pinned separately in test_ai_settings_db.py
(real Postgres)."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.routers import ai_settings
from tests.conftest import make_session_record


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


# ── /review-impl fixes: enum discipline + behavior consumption ────────────────
async def test_patch_rejects_bad_context_mode(client, mock_pool):
    resp = await client.patch("/v1/chat/ai-prefs", json={"context": {"mode": "banana"}})
    assert resp.status_code == 422


async def test_patch_rejects_bad_permission_mode(client, mock_pool):
    resp = await client.patch("/v1/chat/ai-prefs", json={"behavior": {"permission_mode": "yolo"}})
    assert resp.status_code == 422


async def test_patch_rejects_bad_reasoning_effort(client, mock_pool):
    resp = await client.patch("/v1/chat/ai-prefs", json={"behavior": {"reasoning_effort": "ultra"}})
    assert resp.status_code == 422


async def test_patch_accepts_valid_enum(client, mock_pool):
    mock_pool._conn.fetchrow.return_value = None
    resp = await client.patch("/v1/chat/ai-prefs", json={"context": {"mode": "off"}})
    assert resp.status_code == 200


# ── D-CHATAI-VOICE-TWO-STORES — the account write door normalizes voice sources ──
async def test_patch_rejects_unknown_voice_source(client, mock_pool):
    # a genuinely-unknown source 422s at the door → proves the router wires
    # normalize_voice_sources (the flat SETTING_ENUMS can't reach nested voice paths).
    resp = await client.patch(
        "/v1/chat/ai-prefs", json={"voice": {"chat": {"tts_source": "banana"}}}
    )
    assert resp.status_code == 422


async def test_patch_accepts_and_coerces_legacy_voice_source(client, mock_pool):
    # legacy 'ai_model' is ACCEPTED (not 422'd) — a live client sending the old word
    # is coerced to canonical 'user_model', never rejected.
    mock_pool._conn.fetchrow.return_value = None
    resp = await client.patch(
        "/v1/chat/ai-prefs", json={"voice": {"stt": {"source": "ai_model"}}}
    )
    assert resp.status_code == 200


# ── WS-4.3 — the per-user audio-retention setting is range-validated at the door ──
async def test_patch_accepts_in_range_audio_retention(client, mock_pool):
    mock_pool._conn.fetchrow.return_value = None
    resp = await client.patch("/v1/chat/ai-prefs", json={"voice": {"audio_retention_hours": 12}})
    assert resp.status_code == 200


async def test_patch_rejects_audio_retention_over_ceiling(client, mock_pool):
    resp = await client.patch("/v1/chat/ai-prefs", json={"voice": {"audio_retention_hours": 999}})
    assert resp.status_code == 422


async def test_create_session_seeds_behavior_from_account(client, mock_pool):
    # HIGH fix: a new session inherits the account behavior defaults so the panel
    # isn't a write-only store. get_prefs (1st fetchrow) then INSERT (2nd).
    prefs_row = {"behavior": {"reasoning_effort": "high", "temperature": 0.9},
                 "grounding": {}, "voice": {}, "context": {"mode": "auto"}, "version": 1}
    session_row = make_session_record(generation_params={"reasoning_effort": "high", "temperature": 0.9})
    mock_pool.fetchrow.side_effect = [prefs_row, session_row]
    resp = await client.post(
        "/v1/chat/sessions",
        json={"model_source": "user_model", "model_ref": str(uuid4())},
    )
    assert resp.status_code == 201
    gp = json.loads(mock_pool.fetchrow.call_args_list[1].args[6])
    assert gp["reasoning_effort"] == "high"
    assert gp["temperature"] == 0.9


async def test_create_session_body_wins_over_account(client, mock_pool):
    prefs_row = {"behavior": {"temperature": 0.9}, "grounding": {}, "voice": {},
                 "context": {}, "version": 1}
    mock_pool.fetchrow.side_effect = [prefs_row, make_session_record()]
    resp = await client.post(
        "/v1/chat/sessions",
        json={"model_source": "user_model", "model_ref": str(uuid4()),
              "generation_params": {"temperature": 0.2}},
    )
    assert resp.status_code == 201
    gp = json.loads(mock_pool.fetchrow.call_args_list[1].args[6])
    assert gp["temperature"] == 0.2  # explicit per-session choice wins


class _FakeComposition:
    def __init__(self, roles):
        self._roles = roles

    async def get_book_model_roles(self, book_id, caller_user_id):
        return self._roles


async def test_effective_settings_book_model_wins_over_account(client, mock_pool, fake_provider, monkeypatch):
    # D-CHATAI-M1B: with a book model set and no session, the Book tier wins over
    # the Account default (Session ▸ Book ▸ Account).
    import app.client.composition_client as cc
    monkeypatch.setattr(cc, "get_composition_client",
                        lambda: _FakeComposition({"chat": {"model_source": "user_model", "model_ref": "book-model"}}))
    mock_pool.fetchrow.return_value = None            # get_prefs → defaults
    fake_provider._default = ("user_model", "acct-model")  # account tier
    fake_provider._live = True
    resp = await client.get(f"/v1/chat/effective-settings?book_id={uuid4()}")
    assert resp.status_code == 200
    chat = resp.json()["models"]["chat"]
    assert chat["effective_value"] == {"model_source": "user_model", "model_ref": "book-model"}
    assert chat["source_tier"] == "book"


async def test_effective_settings_no_book_id_skips_book_tier(client, mock_pool, fake_provider):
    # No book_id → the composition read is skipped entirely; account resolves.
    mock_pool.fetchrow.return_value = None
    fake_provider._default = ("user_model", "acct-model")
    fake_provider._live = True
    resp = await client.get("/v1/chat/effective-settings")
    assert resp.json()["models"]["chat"]["source_tier"] == "account"


# ── deploy capability ceilings (D-WS4C-EFFECTIVE-VALUE) ──────────────────────
async def test_capabilities_reports_canon_capture_ceiling_on(client, monkeypatch):
    # Default deploy ceiling permits capture → deploy_allows True, tier=system.
    monkeypatch.setattr(ai_settings.settings, "canon_capture_enabled", True)
    resp = await client.get("/v1/chat/capabilities")
    assert resp.status_code == 200
    cap = resp.json()["canon_capture"]
    assert cap == {"deploy_allows": True, "source_tier": "system"}


async def test_capabilities_reports_canon_capture_ceiling_off(client, monkeypatch):
    # A deployment kill-switches capture off → deploy_allows False. The consumer
    # ANDs this with its user knob, so a user who toggled ON still sees effective OFF
    # (the "silently-off" bug the boundary rule prevents).
    monkeypatch.setattr(ai_settings.settings, "canon_capture_enabled", False)
    resp = await client.get("/v1/chat/capabilities")
    assert resp.status_code == 200
    assert resp.json()["canon_capture"]["deploy_allows"] is False


async def test_capabilities_requires_auth(monkeypatch):
    # No get_current_user override → the route rejects an unauthenticated caller
    # (it rides the same JWT edge as every /v1/chat route).
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/v1/chat/capabilities")
    assert resp.status_code in (401, 403)
