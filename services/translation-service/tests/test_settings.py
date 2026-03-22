"""Integration tests for settings endpoints using mocked DB pool."""
import datetime
from uuid import UUID, uuid4

from tests.conftest import FakeRecord

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOOK_ID = str(uuid4())

_NOW = datetime.datetime.utcnow()

_PREFS_ROW = FakeRecord({
    "user_id": UUID(USER_ID),
    "target_language": "vi",
    "model_source": "platform_model",
    "model_ref": uuid4(),
    "system_prompt": "You are a translator.",
    "user_prompt_tpl": "Translate {source_language} to {target_language}:\n{chapter_text}",
    "updated_at": _NOW,
})

_BOOK_ROW = FakeRecord({
    "book_id": UUID(BOOK_ID),
    "owner_user_id": UUID(USER_ID),
    "target_language": "en",
    "model_source": "user_model",
    "model_ref": uuid4(),
    "system_prompt": "Custom prompt.",
    "user_prompt_tpl": "Custom: {chapter_text}",
    "updated_at": _NOW,
})


# ── GET /v1/translation/preferences ──────────────────────────────────────────

def test_get_preferences_returns_defaults_when_no_row(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    resp = client.get("/v1/translation/preferences")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == USER_ID
    assert data["target_language"] == "en"
    assert "{chapter_text}" in data["user_prompt_tpl"]


def test_get_preferences_returns_saved_row(client, fake_pool):
    fake_pool.fetchrow.return_value = _PREFS_ROW
    resp = client.get("/v1/translation/preferences")
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_language"] == "vi"
    assert data["model_source"] == "platform_model"


def test_get_preferences_requires_auth(fake_pool):
    """No auth token should return 403."""
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.database.create_pool", new_callable=AsyncMock, return_value=fake_pool),
        patch("app.database.close_pool", new_callable=AsyncMock),
        patch("app.database.get_pool", return_value=fake_pool),
        patch("app.migrate.run_migrations", new_callable=AsyncMock),
    ):
        from app.main import app as _app
        # No dependency overrides — real JWT check applies
        with TestClient(_app, raise_server_exceptions=False) as c:
            resp = c.get("/v1/translation/preferences")
        assert resp.status_code == 403


# ── PUT /v1/translation/preferences ──────────────────────────────────────────

def test_put_preferences_upserts_and_returns_saved(client, fake_pool):
    fake_pool.fetchrow.return_value = _PREFS_ROW
    resp = client.put("/v1/translation/preferences", json={
        "target_language": "vi",
        "model_source": "platform_model",
        "model_ref": str(_PREFS_ROW["model_ref"]),
        "system_prompt": "You are a translator.",
        "user_prompt_tpl": "Translate {source_language} to {target_language}:\n{chapter_text}",
    })
    assert resp.status_code == 200
    assert resp.json()["target_language"] == "vi"
    fake_pool.fetchrow.assert_called_once()


def test_put_preferences_rejects_template_without_chapter_text(client, fake_pool):
    resp = client.put("/v1/translation/preferences", json={
        "target_language": "vi",
        "model_source": "platform_model",
        "model_ref": None,
        "system_prompt": "Translate.",
        "user_prompt_tpl": "No placeholder here.",  # missing {chapter_text}
    })
    assert resp.status_code == 422


# ── GET /v1/translation/books/{book_id}/settings ─────────────────────────────

def test_get_book_settings_returns_defaults_when_no_rows(client, fake_pool):
    fake_pool.fetchrow.return_value = None  # no book row, no user prefs
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_default"] is True
    assert data["book_id"] == BOOK_ID


def test_get_book_settings_returns_book_row_with_is_default_false(client, fake_pool):
    fake_pool.fetchrow.return_value = _BOOK_ROW
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_default"] is False
    assert data["target_language"] == "en"
    assert data["model_source"] == "user_model"


def test_get_book_settings_falls_back_to_user_prefs(client, fake_pool):
    # First call (book row) returns None, second call (user prefs) returns data
    fake_pool.fetchrow.side_effect = [None, _PREFS_ROW]
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_default"] is True
    assert data["target_language"] == "vi"


# ── PUT /v1/translation/books/{book_id}/settings ─────────────────────────────

def test_put_book_settings_saves_and_returns_is_default_false(client, fake_pool):
    fake_pool.fetchrow.return_value = _BOOK_ROW
    resp = client.put(f"/v1/translation/books/{BOOK_ID}/settings", json={
        "target_language": "en",
        "model_source": "user_model",
        "model_ref": str(_BOOK_ROW["model_ref"]),
        "system_prompt": "Custom.",
        "user_prompt_tpl": "Custom: {chapter_text}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_default"] is False
    assert data["book_id"] == BOOK_ID


def test_put_book_settings_rejects_missing_chapter_text(client, fake_pool):
    resp = client.put(f"/v1/translation/books/{BOOK_ID}/settings", json={
        "target_language": "en",
        "model_source": "platform_model",
        "model_ref": None,
        "system_prompt": "Translate.",
        "user_prompt_tpl": "No placeholder.",
    })
    assert resp.status_code == 422
