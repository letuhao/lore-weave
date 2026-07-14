"""Tests for the sessions CRUD router."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID, make_session_record

_LEGACY_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "glossary_book_create",
        "description": "old",
        "_meta": {"tier": "A", "visibility": "legacy"},
    },
}


def _patched_catalog(catalog):
    return patch(
        "app.client.knowledge_client.get_knowledge_client",
        return_value=AsyncMock(get_tool_definitions=AsyncMock(return_value=catalog)),
    )


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_returns_201(self, client, mock_pool):
        record = make_session_record()
        mock_pool.fetchrow.return_value = record

        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "title": "My Chat",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Session"
        assert data["session_id"] == TEST_SESSION_ID
        # two DB reads now: the account-behavior seed (get_prefs) + the INSERT.
        assert mock_pool.fetchrow.await_count == 2

    @pytest.mark.asyncio
    async def test_create_session_with_system_prompt(self, client, mock_pool):
        record = make_session_record(system_prompt="You are a translator")
        mock_pool.fetchrow.return_value = record

        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "system_prompt": "You are a translator",
        })
        assert resp.status_code == 201
        assert resp.json()["system_prompt"] == "You are a translator"

    @pytest.mark.asyncio
    async def test_create_session_with_project_ids_persists_set(self, client, mock_pool):
        """Track B B1(2): the multi-KG grounding set round-trips through create
        and the UUID[] is bound as the last INSERT arg."""
        pid_a, pid_b = str(uuid4()), str(uuid4())
        mock_pool.fetchrow.return_value = make_session_record(project_ids=[pid_a, pid_b])
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "project_ids": [pid_a, pid_b],
        })
        assert resp.status_code == 201
        assert resp.json()["project_ids"] == [pid_a, pid_b]
        # INSERT positional tail is (…, project_ids, book_id, session_kind), so project_ids is -3.
        assert list(mock_pool.fetchrow.call_args.args[-3]) == [pid_a, pid_b]

    @pytest.mark.asyncio
    async def test_create_session_project_ids_over_cap_returns_422(self, client, mock_pool):
        """The ≤16 cap mirrors knowledge-service's ContextBuildRequest."""
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "project_ids": [str(uuid4()) for _ in range(17)],
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_session_missing_model_ref_returns_422(self, client, mock_pool):
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_session_with_book_id_persists_it(self, client, mock_pool):
        """D-COMPOSE-SESSION-RESTORE: book_id round-trips through create and is bound
        as the second-to-last INSERT positional (session_kind is now the final one)."""
        book_id = str(uuid4())
        mock_pool.fetchrow.return_value = make_session_record(book_id=book_id)
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "book_id": book_id,
        })
        assert resp.status_code == 201
        assert resp.json()["book_id"] == book_id
        assert mock_pool.fetchrow.call_args.args[-2] == book_id
        # T-4: an ordinary create defaults to a 'chat' session (session_kind is the final arg).
        assert mock_pool.fetchrow.call_args.args[-1] == "chat"

    @pytest.mark.asyncio
    async def test_create_session_without_book_id_defaults_null(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record()
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
        })
        assert resp.status_code == 201
        assert resp.json()["book_id"] is None
        assert mock_pool.fetchrow.call_args.args[-2] is None

    @pytest.mark.asyncio
    async def test_create_session_with_assistant_kind_persists_it(self, client, mock_pool):
        """T-4: the Work Assistant FE creates its session with session_kind='assistant'
        (the discriminator the day-window read / voice gate / search scoping key off)."""
        mock_pool.fetchrow.return_value = make_session_record(session_kind="assistant")
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "session_kind": "assistant",
        })
        assert resp.status_code == 201
        assert mock_pool.fetchrow.call_args.args[-1] == "assistant"

    @pytest.mark.asyncio
    async def test_create_session_rejects_an_unknown_session_kind(self, client, mock_pool):
        """Closed-set enum: an out-of-set session_kind is rejected on write (422), never stored."""
        resp = await client.post("/v1/chat/sessions", json={
            "model_source": "user_model",
            "model_ref": TEST_MODEL_REF,
            "session_kind": "coach",  # not in the closed set yet
        })
        assert resp.status_code == 422


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, client, mock_pool):
        mock_pool.fetch.return_value = []
        resp = await client.get("/v1/chat/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_list_sessions_returns_items(self, client, mock_pool):
        mock_pool.fetch.return_value = [make_session_record(), make_session_record(session_id=str(uuid4()))]
        resp = await client.get("/v1/chat/sessions")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_with_status_filter(self, client, mock_pool):
        mock_pool.fetch.return_value = []
        resp = await client.get("/v1/chat/sessions?status=archived")
        assert resp.status_code == 200
        # Verify the status filter was passed to the query
        call_args = mock_pool.fetch.call_args
        assert "archived" in call_args.args

    @pytest.mark.asyncio
    async def test_list_sessions_with_book_id_filter(self, client, mock_pool):
        """D-COMPOSE-SESSION-RESTORE: ?book_id= is bound and the SQL text
        gains the book_id predicate."""
        mock_pool.fetch.return_value = []
        book_id = str(uuid4())
        resp = await client.get(f"/v1/chat/sessions?book_id={book_id}")
        assert resp.status_code == 200
        call_args = mock_pool.fetch.call_args
        assert book_id in call_args.args
        assert "book_id=" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_list_sessions_book_id_and_cursor_bind_distinct_placeholders(self, client, mock_pool):
        """Regression: book_id must be appended BEFORE cursor so cursor's
        placeholder number always reflects however many filters precede it —
        appending in the wrong order would silently misbind the cursor value
        to the book_id predicate (or vice versa)."""
        mock_pool.fetch.return_value = []
        book_id = str(uuid4())
        resp = await client.get(f"/v1/chat/sessions?book_id={book_id}&cursor=2026-01-01T00:00:00Z")
        assert resp.status_code == 200
        call_args = mock_pool.fetch.call_args
        sql = call_args.args[0]
        args = call_args.args[1:]
        # user_id, status, limit+1, book_id, cursor — 5 positional args, in order.
        assert len(args) == 5
        assert args[3] == book_id
        assert args[4] == "2026-01-01T00:00:00Z"
        assert "book_id=$4" in sql
        assert "last_message_at < $5" in sql


class TestGetSession:
    @pytest.mark.asyncio
    async def test_get_session_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record()
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == TEST_SESSION_ID

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.get(f"/v1/chat/sessions/{uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_session_memory_mode_no_project(self, client, mock_pool):
        """K-CLEAN-5 (D-K8-04): GET response derives memory_mode from
        project_id. With no project linked, mode is 'no_project'."""
        mock_pool.fetchrow.return_value = make_session_record(project_id=None)
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] is None
        assert body["memory_mode"] == "no_project"

    @pytest.mark.asyncio
    async def test_get_session_memory_mode_static(self, client, mock_pool):
        """K-CLEAN-5 (D-K8-04): with a project linked, mode is 'static'.
        `degraded` is not representable on GET — that only ever arrives
        via the per-turn SSE memory-mode event."""
        project_id = str(uuid4())
        mock_pool.fetchrow.return_value = make_session_record(project_id=project_id)
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project_id
        assert body["memory_mode"] == "static"

    @pytest.mark.asyncio
    async def test_get_session_memory_mode_multi(self, client, mock_pool):
        """Track B B1(2): a set of ≥2 grounding projects derives memory_mode
        'multi' on GET (a single link stays 'static')."""
        pids = [str(uuid4()), str(uuid4())]
        mock_pool.fetchrow.return_value = make_session_record(project_ids=pids)
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_ids"] == pids
        assert body["memory_mode"] == "multi"

    @pytest.mark.asyncio
    async def test_get_session_single_project_ids_is_static(self, client, mock_pool):
        """A single-element set is not 'multi' — one KG is the static path."""
        pids = [str(uuid4())]
        mock_pool.fetchrow.return_value = make_session_record(project_ids=pids)
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        assert resp.json()["memory_mode"] == "static"

    @pytest.mark.asyncio
    async def test_get_session_returns_enabled_tool_arrays(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record(
            enabled_tools=["find_tools"],
            enabled_skills=["glossary"],
            activated_tools=["book_list"],
        )
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled_tools"] == ["find_tools"]
        assert body["enabled_skills"] == ["glossary"]
        assert body["activated_tools"] == ["book_list"]


class TestPatchSession:
    @pytest.mark.asyncio
    async def test_patch_session_title(self, client, mock_pool):
        original = make_session_record()
        updated = make_session_record(title="Updated Title")
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "title": "Updated Title",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_patch_session_not_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.patch(f"/v1/chat/sessions/{uuid4()}", json={
            "title": "Nope",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_session_archive(self, client, mock_pool):
        original = make_session_record()
        updated = make_session_record(status="archived")
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "status": "archived",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    @pytest.mark.asyncio
    async def test_patch_session_enabled_tools(self, client, mock_pool):
        original = make_session_record()
        updated = make_session_record(enabled_tools=["book_get_chapter"])
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "enabled_tools": ["book_get_chapter"],
        })
        assert resp.status_code == 200
        assert resp.json()["enabled_tools"] == ["book_get_chapter"]

    @pytest.mark.asyncio
    async def test_patch_session_pinned_legacy_tools_accepts_a_real_legacy_name(self, client, mock_pool):
        original = make_session_record()
        updated = make_session_record(pinned_legacy_tools=["glossary_book_create"])
        mock_pool.fetchrow.side_effect = [original, updated]

        with _patched_catalog([_LEGACY_TOOL_DEF]):
            resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
                "pinned_legacy_tools": ["glossary_book_create"],
            })
        assert resp.status_code == 200
        assert resp.json()["pinned_legacy_tools"] == ["glossary_book_create"]

    @pytest.mark.asyncio
    async def test_patch_session_pinned_legacy_tools_rejects_unknown_name(self, client, mock_pool):
        """SET-6 closed-set: a name that isn't a legacy tool in the LIVE catalog
        (typo, or a discoverable tool someone tried to pin this way) is a 422,
        not a silent drop or a generic 400 — and the write never happens."""
        original = make_session_record()
        mock_pool.fetchrow.side_effect = [original]

        with _patched_catalog([_LEGACY_TOOL_DEF]):
            resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
                "pinned_legacy_tools": ["not_a_real_tool"],
            })
        assert resp.status_code == 422
        assert "not_a_real_tool" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_patch_session_pinned_legacy_tools_clear_skips_validation(self, client, mock_pool):
        """Clearing back to [] must not require a catalog round-trip."""
        original = make_session_record(pinned_legacy_tools=["glossary_book_create"])
        updated = make_session_record(pinned_legacy_tools=[])
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "pinned_legacy_tools": [],
        })
        assert resp.status_code == 200
        assert resp.json()["pinned_legacy_tools"] == []

    @pytest.mark.asyncio
    async def test_patch_session_set_project_ids(self, client, mock_pool):
        """Track B B1(2): PATCH replaces the grounding set; the write flag is
        True and the UUID[] value rides the UPDATE args."""
        pids = [str(uuid4()), str(uuid4())]
        original = make_session_record()
        updated = make_session_record(project_ids=pids)
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "project_ids": pids,
        })
        assert resp.status_code == 200
        assert resp.json()["project_ids"] == pids
        # Index the UPDATE args ABSOLUTELY (args[N] == SQL's $N), never from the end:
        # a negative index silently re-points at a different parameter the moment a new
        # one is appended, which is exactly what happened when the session-tier columns
        # landed. $24 = set_project_ids, $25 = project_ids_value.
        args = mock_pool.fetchrow.call_args.args
        assert args[24] is True
        assert list(args[25]) == pids

    @pytest.mark.asyncio
    async def test_patch_session_clear_project_ids(self, client, mock_pool):
        """An explicit [] clears the set back to the single-project path (write
        flag True, empty value)."""
        original = make_session_record(project_ids=[str(uuid4())])
        updated = make_session_record(project_ids=[])
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "project_ids": [],
        })
        assert resp.status_code == 200
        assert resp.json()["project_ids"] == []
        args = mock_pool.fetchrow.call_args.args
        assert args[24] is True          # present in body → write
        assert list(args[25]) == []

    @pytest.mark.asyncio
    async def test_patch_session_omitted_project_ids_leaves_alone(self, client, mock_pool):
        """Omitting project_ids leaves the column untouched (write flag False)."""
        original = make_session_record(project_ids=[str(uuid4())])
        updated = make_session_record(title="x")
        mock_pool.fetchrow.side_effect = [original, updated]

        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "title": "x",
        })
        assert resp.status_code == 200
        args = mock_pool.fetchrow.call_args.args
        assert args[24] is False         # not in body → leave alone


class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_delete_session_success(self, client, mock_pool):
        mock_pool.execute.return_value = "DELETE 1"
        resp = await client.delete(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, client, mock_pool):
        mock_pool.execute.return_value = "DELETE 0"
        resp = await client.delete(f"/v1/chat/sessions/{uuid4()}")
        assert resp.status_code == 404


# ── Chat & AI settings, SESSION tier (spec 2026-07-05 §3.5) ──────────────────
#
# `grounding_enabled`, `voice_overrides` and `context_overrides` existed as columns,
# were READ by the effective-settings resolver, and `grounding_enabled` was consumed
# by the turn itself — but nothing anywhere could WRITE them, so the Session tier of
# the cascade was permanently NULL. These tests pin the write path AND its 3-state
# contract, because "omitted" and "explicitly cleared" must not collapse into each
# other: collapsing them makes it impossible to ever stop overriding.

def _update_args(mock_pool):
    """Positional args of the UPDATE (the 2nd fetchrow). args[N] == SQL's $N."""
    return mock_pool.fetchrow.await_args_list[-1].args


class TestPatchSessionTierGrounding:
    @pytest.mark.asyncio
    async def test_sets_grounding_override(self, client, mock_pool):
        mock_pool.fetchrow.side_effect = [make_session_record(), make_session_record(grounding_enabled=False)]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={"grounding_enabled": False})
        assert resp.status_code == 200
        args = _update_args(mock_pool)
        assert args[28] is True, "presence flag must be set"
        assert args[29] is False
        assert resp.json()["grounding_enabled"] is False

    @pytest.mark.asyncio
    async def test_explicit_null_CLEARS_the_override(self, client, mock_pool):
        """null ⇒ inherit from Book/Account/System. This is the case a naive
        `if value is not None` write path can never express — the user could turn an
        override ON but never back to 'inherit'."""
        mock_pool.fetchrow.side_effect = [make_session_record(), make_session_record(grounding_enabled=None)]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={"grounding_enabled": None})
        assert resp.status_code == 200
        args = _update_args(mock_pool)
        assert args[28] is True, "an explicit null is still a WRITE"
        assert args[29] is None
        assert resp.json()["grounding_enabled"] is None

    @pytest.mark.asyncio
    async def test_omitted_leaves_it_untouched(self, client, mock_pool):
        mock_pool.fetchrow.side_effect = [make_session_record(), make_session_record()]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={"title": "x"})
        assert resp.status_code == 200
        assert _update_args(mock_pool)[28] is False, "omitted must not write"


class TestPatchSessionTierJsonbOverrides:
    @pytest.mark.asyncio
    async def test_voice_overrides_deep_merge_preserves_siblings(self, client, mock_pool):
        """The same `apply_patch` the account blob uses: patching one nested leaf must
        not clobber its siblings (spec §3.1 field-by-field, the RES-3 finding)."""
        existing = make_session_record(voice_overrides={"chat": {"tts_voice_id": "a", "tts_speed": 1.5}})
        mock_pool.fetchrow.side_effect = [existing, existing]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "voice_overrides": {"chat": {"tts_voice_id": "b"}},
        })
        assert resp.status_code == 200
        args = _update_args(mock_pool)
        assert args[30] is True
        assert json.loads(args[31]) == {"chat": {"tts_voice_id": "b", "tts_speed": 1.5}}

    @pytest.mark.asyncio
    async def test_null_leaf_clears_just_that_leaf(self, client, mock_pool):
        existing = make_session_record(voice_overrides={"chat": {"tts_voice_id": "a", "tts_speed": 1.5}})
        mock_pool.fetchrow.side_effect = [existing, existing]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "voice_overrides": {"chat": {"tts_voice_id": None}},
        })
        assert resp.status_code == 200
        assert json.loads(_update_args(mock_pool)[31]) == {"chat": {"tts_speed": 1.5}}

    @pytest.mark.asyncio
    async def test_explicit_null_clears_the_whole_category(self, client, mock_pool):
        existing = make_session_record(context_overrides={"mode": "off"})
        mock_pool.fetchrow.side_effect = [existing, make_session_record(context_overrides=None)]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={"context_overrides": None})
        assert resp.status_code == 200
        args = _update_args(mock_pool)
        assert args[32] is True and args[33] is None
        assert resp.json()["context_overrides"] == {}

    @pytest.mark.asyncio
    async def test_jsonb_from_a_string_column_is_still_merged(self, client, mock_pool):
        """asyncpg hands JSONB back as a str under some codecs — a merge that assumed
        dict would raise, and the whole override would be lost."""
        existing = make_session_record(context_overrides='{"mode": "on"}')
        mock_pool.fetchrow.side_effect = [existing, existing]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "context_overrides": {"trigger_ratio": 0.8},
        })
        assert resp.status_code == 200
        assert json.loads(_update_args(mock_pool)[33]) == {"mode": "on", "trigger_ratio": 0.8}


class TestPatchSessionTierEnumGate:
    """The session row is the SECOND write door onto settings the turn consumes. An
    out-of-set value stored here would be silently read as the default by every
    consumer — a value-shaped silent no-op. Same closed sets as the account patch."""

    @pytest.mark.asyncio
    async def test_bad_context_mode_is_422_not_stored(self, client, mock_pool):
        mock_pool.fetchrow.side_effect = [make_session_record(), make_session_record()]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "context_overrides": {"mode": "sometimes"},
        })
        assert resp.status_code == 422
        assert "auto" in resp.text and "sometimes" in resp.text, "self-correcting message"

    @pytest.mark.asyncio
    async def test_bad_reasoning_effort_is_422(self, client, mock_pool):
        mock_pool.fetchrow.side_effect = [make_session_record(), make_session_record()]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "generation_params": {"reasoning_effort": "extreme"},
        })
        assert resp.status_code == 422

    # ── D-CHATAI-VOICE-TWO-STORES — the session door also normalizes voice sources ──
    @pytest.mark.asyncio
    async def test_legacy_voice_source_coerced_to_user_model_when_stored(self, client, mock_pool):
        existing = make_session_record(voice_overrides={})
        mock_pool.fetchrow.side_effect = [existing, existing]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "voice_overrides": {"stt": {"source": "ai_model", "model_ref": "s1"}},
        })
        assert resp.status_code == 200
        stored = json.loads(_update_args(mock_pool)[31])
        assert stored["stt"]["source"] == "user_model"  # coerced, not stored verbatim
        assert stored["stt"]["model_ref"] == "s1"        # sibling preserved

    @pytest.mark.asyncio
    async def test_bad_voice_source_is_422(self, client, mock_pool):
        mock_pool.fetchrow.side_effect = [make_session_record(), make_session_record()]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "voice_overrides": {"chat": {"tts_source": "telepathy"}},
        })
        assert resp.status_code == 422
        assert "telepathy" in resp.text

    @pytest.mark.asyncio
    async def test_valid_values_pass(self, client, mock_pool):
        mock_pool.fetchrow.side_effect = [make_session_record(), make_session_record()]
        resp = await client.patch(f"/v1/chat/sessions/{TEST_SESSION_ID}", json={
            "context_overrides": {"mode": "off"},
            "generation_params": {"reasoning_effort": "high"},
        })
        assert resp.status_code == 200
