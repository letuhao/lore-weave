"""
Tests for LW-73: compact model prompt customisation.

Covers:
- config: DEFAULT_COMPACT_SYSTEM_PROMPT / DEFAULT_COMPACT_USER_PROMPT_TPL exist
- _LANG_NAMES: expanded to cover new codes (spot-checks)
- _lang_name(): falls back to raw code for unknown entries
- _SafeFormatMap: {history_text} substituted correctly; unknown keys preserved
- _compact_history: uses job's compact_system_prompt when provided
- _compact_history: falls back to DEFAULT_COMPACT_SYSTEM_PROMPT when field is absent/empty
- _compact_history: compact_user_prompt_tpl substitutes {history_text}
- settings endpoints: compact prompt fields included in GET/PUT
- jobs: compact prompt fields snapshotted into translation_jobs on creation
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from tests.conftest import FakeRecord

USER_ID   = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOOK_ID   = str(uuid4())
MODEL_REF = str(uuid4())

# ── Config constants ───────────────────────────────────────────────────────────

def test_default_compact_system_prompt_is_defined():
    from app.config import DEFAULT_COMPACT_SYSTEM_PROMPT
    assert isinstance(DEFAULT_COMPACT_SYSTEM_PROMPT, str)
    assert len(DEFAULT_COMPACT_SYSTEM_PROMPT) > 20
    assert "Translation Memo" in DEFAULT_COMPACT_SYSTEM_PROMPT


def test_default_compact_user_prompt_tpl_contains_history_text():
    from app.config import DEFAULT_COMPACT_USER_PROMPT_TPL
    assert "{history_text}" in DEFAULT_COMPACT_USER_PROMPT_TPL


# ── _LANG_NAMES expansion ──────────────────────────────────────────────────────

def test_lang_names_contains_all_legacy_codes():
    """Core codes that existed before LW-73 must still be present."""
    from app.workers.session_translator import _LANG_NAMES
    for code in ("en", "vi", "ja", "zh", "ko", "fr", "de", "ar", "hi", "ru"):
        assert code in _LANG_NAMES, f"Missing legacy code: {code}"


def test_lang_names_contains_new_codes():
    """Codes that were NOT in the 45-entry dict must now be present."""
    from app.workers.session_translator import _LANG_NAMES
    for code in ("bo", "jv", "ka", "ht", "lb", "mg", "mi", "nv", "sa", "tg"):
        assert code in _LANG_NAMES, f"Missing new code: {code}"


def test_lang_names_script_variant_codes():
    """Script variant codes (lowercase) must be present."""
    from app.workers.session_translator import _LANG_NAMES
    for code in ("az-arab", "az-cyrl", "bs-cyrl", "sr-latn", "uz-latn"):
        assert code in _LANG_NAMES, f"Missing script variant: {code}"


def test_lang_names_keys_are_lowercase():
    from app.workers.session_translator import _LANG_NAMES
    for key in _LANG_NAMES:
        assert key == key.lower(), f"Key not lowercase: {key!r}"


def test_lang_name_returns_name_for_known_code():
    from app.workers.session_translator import _lang_name
    assert _lang_name("vi") == "Vietnamese"
    assert _lang_name("ja") == "Japanese"
    assert _lang_name("EN") == "English"       # case-insensitive lookup


def test_lang_name_falls_back_to_code_for_unknown():
    from app.workers.session_translator import _lang_name
    assert _lang_name("xx-unknown") == "xx-unknown"


# ── _SafeFormatMap ─────────────────────────────────────────────────────────────

def test_safe_format_map_substitutes_known_key():
    from app.workers.session_translator import _SafeFormatMap
    result = "History: {history_text}".format_map(_SafeFormatMap({"history_text": "ABC"}))
    assert result == "History: ABC"


def test_safe_format_map_preserves_unknown_keys():
    from app.workers.session_translator import _SafeFormatMap
    result = "A={some_key} B={history_text}".format_map(
        _SafeFormatMap({"history_text": "X"})
    )
    assert result == "A={some_key} B=X"


def test_safe_format_map_empty_mapping_preserves_all_placeholders():
    from app.workers.session_translator import _SafeFormatMap
    tpl = "{a} + {b}"
    result = tpl.format_map(_SafeFormatMap({}))
    assert result == "{a} + {b}"


# ── _compact_history: uses custom prompts from job msg ─────────────────────────

# Phase 4c-β: legacy httpx.AsyncClient + JWT-based mocks replaced with a
# loreweave_llm SDK FakeLLMClient mirror. _compact_history now consumes
# llm_client + user_id (no client/token kwargs).

from typing import Any
from loreweave_llm.models import Job, JobError


class _CompactFakeLLMClient:
    """Minimal stand-in for app.llm_client.LLMClient — captures
    submit_and_wait kwargs and returns a single completed memo Job."""

    def __init__(self, memo_text: str = "[memo]") -> None:
        self.calls: list[dict[str, Any]] = []
        self._memo_text = memo_text

    async def submit_and_wait(self, **kwargs: Any) -> Job:
        self.calls.append(kwargs)
        return Job(
            job_id="00000000-0000-0000-0000-0000000000c0",
            operation="translation",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": self._memo_text}],
                "usage": {"input_tokens": 5, "output_tokens": 5},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )


@pytest.mark.asyncio
async def test_compact_history_uses_custom_system_prompt():
    """When msg has compact_system_prompt set, the compact call must use it."""
    custom_sys = "YOU ARE A SPECIAL COMPACT BOT"
    msg = {
        "model_source": "platform_model",
        "model_ref": str(uuid4()),
        "compact_model_source": None,
        "compact_model_ref": None,
        "compact_system_prompt": custom_sys,
        "compact_user_prompt_tpl": "{history_text}",
        "user_id": USER_ID,
    }
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]

    fake = _CompactFakeLLMClient()

    from app.workers.session_translator import _compact_history
    await _compact_history(
        llm_client=fake,
        session_history=history,
        old_memo="",
        msg=msg,
        user_id=USER_ID,
    )

    assert len(fake.calls) == 1
    messages = fake.calls[0]["input"]["messages"]
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert len(system_msgs) == 1
    assert system_msgs[0]["content"] == custom_sys


@pytest.mark.asyncio
async def test_compact_history_falls_back_to_default_when_field_empty():
    """Empty compact_system_prompt falls back to DEFAULT_COMPACT_SYSTEM_PROMPT."""
    from app.config import DEFAULT_COMPACT_SYSTEM_PROMPT

    msg = {
        "model_source": "platform_model",
        "model_ref": str(uuid4()),
        "compact_model_source": None,
        "compact_model_ref": None,
        "compact_system_prompt": "",       # empty → use default
        "compact_user_prompt_tpl": "",     # empty → use default
        "user_id": USER_ID,
    }
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]

    fake = _CompactFakeLLMClient()

    from app.workers.session_translator import _compact_history
    await _compact_history(
        llm_client=fake,
        session_history=history,
        old_memo="",
        msg=msg,
        user_id=USER_ID,
    )

    messages = fake.calls[0]["input"]["messages"]
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert system_msgs[0]["content"] == DEFAULT_COMPACT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_compact_history_falls_back_when_field_absent():
    """Missing compact_system_prompt key falls back to DEFAULT_COMPACT_SYSTEM_PROMPT."""
    from app.config import DEFAULT_COMPACT_SYSTEM_PROMPT

    msg = {
        "model_source": "platform_model",
        "model_ref": str(uuid4()),
        "compact_model_source": None,
        "compact_model_ref": None,
        # compact_system_prompt absent
        "user_id": USER_ID,
    }
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]

    fake = _CompactFakeLLMClient()

    from app.workers.session_translator import _compact_history
    await _compact_history(
        llm_client=fake,
        session_history=history,
        old_memo="",
        msg=msg,
        user_id=USER_ID,
    )

    messages = fake.calls[0]["input"]["messages"]
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert system_msgs[0]["content"] == DEFAULT_COMPACT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_compact_history_custom_user_prompt_tpl_substitutes_history():
    """Custom compact_user_prompt_tpl wraps {history_text} in custom text."""
    msg = {
        "model_source": "platform_model",
        "model_ref": str(uuid4()),
        "compact_model_source": None,
        "compact_model_ref": None,
        "compact_system_prompt": "Sys",
        "compact_user_prompt_tpl": "WRAP: {history_text} :ENDWRAP",
        "user_id": USER_ID,
    }
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]

    fake = _CompactFakeLLMClient()

    from app.workers.session_translator import _compact_history
    await _compact_history(
        llm_client=fake,
        session_history=history,
        old_memo="",
        msg=msg,
        user_id=USER_ID,
    )

    messages = fake.calls[0]["input"]["messages"]
    user_msgs = [m for m in messages if m["role"] == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"].startswith("WRAP:")
    assert ":ENDWRAP" in user_msgs[0]["content"]
    assert "hello" in user_msgs[0]["content"]   # actual history text included


@pytest.mark.asyncio
async def test_compact_history_history_text_in_user_message():
    """The session history must appear inside the user message of the compact call."""
    msg = {
        "model_source": "platform_model",
        "model_ref": str(uuid4()),
        "compact_model_source": None,
        "compact_model_ref": None,
        "compact_system_prompt": "",
        "compact_user_prompt_tpl": "",
        "user_id": USER_ID,
    }
    history = [
        {"role": "user",      "content": "SOURCE CHUNK TEXT"},
        {"role": "assistant", "content": "TRANSLATED CHUNK TEXT"},
    ]

    fake = _CompactFakeLLMClient()

    from app.workers.session_translator import _compact_history
    await _compact_history(
        llm_client=fake,
        session_history=history,
        old_memo="",
        msg=msg,
        user_id=USER_ID,
    )

    messages = fake.calls[0]["input"]["messages"]
    user_msgs = [m for m in messages if m["role"] == "user"]
    combined = user_msgs[0]["content"]
    assert "SOURCE CHUNK TEXT" in combined
    assert "TRANSLATED CHUNK TEXT" in combined


# ── Settings endpoints: compact prompt fields ──────────────────────────────────

_NOW = __import__("datetime").datetime.utcnow()

_PREFS_ROW_WITH_COMPACT = FakeRecord({
    "user_id":               UUID(USER_ID),
    "target_language":       "vi",
    "model_source":          "platform_model",
    "model_ref":             UUID(MODEL_REF),
    "system_prompt":         "Translate.",
    "user_prompt_tpl":       "Translate {source_language} to {target_language}:\n{chapter_text}",
    "compact_model_source":  None,
    "compact_model_ref":     None,
    "compact_system_prompt": "Custom compact system.",
    "compact_user_prompt_tpl": "Summarise: {history_text}",
    "chunk_size_tokens":     2000,
    "invoke_timeout_secs":   300,
    "updated_at":            _NOW,
})


def test_get_preferences_includes_compact_prompt_fields(client, fake_pool):
    """GET /preferences must return compact_system_prompt and compact_user_prompt_tpl."""
    fake_pool.fetchrow.return_value = _PREFS_ROW_WITH_COMPACT
    resp = client.get("/v1/translation/preferences")
    assert resp.status_code == 200
    data = resp.json()
    assert data["compact_system_prompt"] == "Custom compact system."
    assert data["compact_user_prompt_tpl"] == "Summarise: {history_text}"


def test_get_preferences_defaults_new_fields_to_empty_string(client, fake_pool):
    """When no row exists, compact prompts default to empty string."""
    fake_pool.fetchrow.return_value = None
    resp = client.get("/v1/translation/preferences")
    assert resp.status_code == 200
    data = resp.json()
    assert data["compact_system_prompt"] == ""
    assert data["compact_user_prompt_tpl"] == ""


def test_put_preferences_accepts_compact_prompt_fields(client, fake_pool):
    """PUT /preferences must accept and upsert compact_system_prompt."""
    fake_pool.fetchrow.return_value = _PREFS_ROW_WITH_COMPACT
    resp = client.put("/v1/translation/preferences", json={
        "target_language":         "vi",
        "model_source":            "platform_model",
        "model_ref":               MODEL_REF,
        "system_prompt":           "Translate.",
        "user_prompt_tpl":         "{chapter_text}",
        "compact_system_prompt":   "My compact sys.",
        "compact_user_prompt_tpl": "Compact: {history_text}",
    })
    assert resp.status_code == 200
    fake_pool.fetchrow.assert_called_once()
    # Verify the SQL call included the new fields (check call args contain expected strings)
    call_args = fake_pool.fetchrow.call_args
    assert "compact_system_prompt" in call_args[0][0]
    assert "compact_user_prompt_tpl" in call_args[0][0]


def test_put_preferences_new_fields_default_to_empty_string_when_omitted(client, fake_pool):
    """Omitting compact prompt fields in the PUT body defaults them to ''."""
    fake_pool.fetchrow.return_value = _PREFS_ROW_WITH_COMPACT
    resp = client.put("/v1/translation/preferences", json={
        "target_language": "vi",
        "model_source":    "platform_model",
        "model_ref":       MODEL_REF,
        "system_prompt":   "Translate.",
        "user_prompt_tpl": "{chapter_text}",
        # compact_system_prompt and compact_user_prompt_tpl omitted
    })
    assert resp.status_code == 200
    # The positional args to fetchrow should include two empty strings for the new fields
    call_args = fake_pool.fetchrow.call_args[0]
    assert "" in call_args   # empty string present in args


def test_put_book_settings_accepts_compact_prompt_fields(client, fake_pool):
    """PUT /books/{id}/settings must accept compact prompt fields."""
    _BOOK_ROW = FakeRecord({
        "book_id":               UUID(BOOK_ID),
        "owner_user_id":         UUID(USER_ID),
        "target_language":       "en",
        "model_source":          "platform_model",
        "model_ref":             UUID(MODEL_REF),
        "system_prompt":         ".",
        "user_prompt_tpl":       "{chapter_text}",
        "compact_model_source":  None,
        "compact_model_ref":     None,
        "compact_system_prompt": "Book compact sys.",
        "compact_user_prompt_tpl": "Book: {history_text}",
        "chunk_size_tokens":     2000,
        "invoke_timeout_secs":   300,
        "updated_at":            _NOW,
    })
    fake_pool.fetchrow.return_value = _BOOK_ROW
    resp = client.put(f"/v1/translation/books/{BOOK_ID}/settings", json={
        "target_language":         "en",
        "model_source":            "platform_model",
        "model_ref":               MODEL_REF,
        "system_prompt":           ".",
        "user_prompt_tpl":         "{chapter_text}",
        "compact_system_prompt":   "Book compact sys.",
        "compact_user_prompt_tpl": "Book: {history_text}",
    })
    assert resp.status_code == 200


# ── Jobs: compact prompt fields snapshotted ────────────────────────────────────

_BOOK_SETTINGS_W_COMPACT = FakeRecord({
    "book_id":               UUID(BOOK_ID),
    "owner_user_id":         UUID(USER_ID),
    "target_language":       "vi",
    "model_source":          "platform_model",
    "model_ref":             UUID(MODEL_REF),
    "system_prompt":         "Translate.",
    "user_prompt_tpl":       "{chapter_text}",
    "compact_model_source":  None,
    "compact_model_ref":     None,
    "compact_system_prompt": "JOB COMPACT SYS",
    "compact_user_prompt_tpl": "JOB: {history_text}",
    "chunk_size_tokens":     2000,
    "invoke_timeout_secs":   300,
    "updated_at":            _NOW,
})

_JOB_ROW = FakeRecord({
    "job_id":                UUID(str(uuid4())),
    "book_id":               UUID(BOOK_ID),
    "owner_user_id":         UUID(USER_ID),
    "status":                "pending",
    "target_language":       "vi",
    "model_source":          "platform_model",
    "model_ref":             UUID(MODEL_REF),
    "system_prompt":         "Translate.",
    "user_prompt_tpl":       "{chapter_text}",
    "compact_model_source":  None,
    "compact_model_ref":     None,
    "compact_system_prompt": "JOB COMPACT SYS",
    "compact_user_prompt_tpl": "JOB: {history_text}",
    "chunk_size_tokens":     2000,
    "invoke_timeout_secs":   300,
    "chapter_ids":           [UUID(str(uuid4()))],
    "total_chapters":        1,
    "completed_chapters":    0,
    "failed_chapters":       0,
    "error_message":         None,
    "started_at":            None,
    "finished_at":           None,
    "created_at":            _NOW,
})


def test_create_job_snapshots_compact_prompt_fields(client, fake_pool):
    """POST /books/{id}/jobs must snapshot compact prompt fields into translation_jobs."""
    import httpx as _httpx
    from unittest.mock import AsyncMock

    _book_resp = MagicMock(spec=_httpx.Response)
    _book_resp.status_code = 200
    _book_resp.is_success = True
    _book_resp.json.return_value = {"owner_user_id": USER_ID}

    fake_pool.fetchrow.side_effect = [
        _BOOK_SETTINGS_W_COMPACT,  # _resolve_effective_settings → book settings
        _JOB_ROW,                  # INSERT INTO translation_jobs RETURNING *
    ]
    fake_pool.execute.return_value = None

    with patch("app.routers.jobs.httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__  = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(return_value=_book_resp)

        resp = client.post(
            f"/v1/translation/books/{BOOK_ID}/jobs",
            json={"chapter_ids": [str(uuid4())]},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["compact_system_prompt"] == "JOB COMPACT SYS"
    assert data["compact_user_prompt_tpl"] == "JOB: {history_text}"

    # Verify the INSERT SQL included the new column names
    insert_call = fake_pool.fetchrow.call_args_list[1]
    sql = insert_call[0][0]
    assert "compact_system_prompt" in sql
    assert "compact_user_prompt_tpl" in sql


def test_create_job_publish_includes_compact_prompt_fields(client, fake_pool):
    """The RabbitMQ publish payload must include compact_system_prompt."""
    import httpx as _httpx
    from unittest.mock import AsyncMock, patch as _patch

    _book_resp = MagicMock(spec=_httpx.Response)
    _book_resp.status_code = 200
    _book_resp.is_success = True
    _book_resp.json.return_value = {"owner_user_id": USER_ID}

    fake_pool.fetchrow.side_effect = [
        _BOOK_SETTINGS_W_COMPACT,
        _JOB_ROW,
    ]
    fake_pool.execute.return_value = None

    published_payloads: list[dict] = []

    async def _fake_publish(routing_key, payload):
        published_payloads.append(payload)

    with patch("app.routers.jobs.httpx.AsyncClient") as mock_http, \
         patch("app.routers.jobs.publish", side_effect=_fake_publish):
        mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_http.return_value.__aexit__  = AsyncMock(return_value=False)
        mock_http.return_value.get = AsyncMock(return_value=_book_resp)

        resp = client.post(
            f"/v1/translation/books/{BOOK_ID}/jobs",
            json={"chapter_ids": [str(uuid4())]},
        )

    assert resp.status_code == 201
    assert published_payloads, "publish must have been called"
    job_payload = published_payloads[0]
    assert "compact_system_prompt" in job_payload
    assert "compact_user_prompt_tpl" in job_payload
    assert job_payload["compact_system_prompt"] == "JOB COMPACT SYS"
