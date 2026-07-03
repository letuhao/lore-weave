"""W3 — manual steerable compact.

Three surfaces:
  1. POST /v1/chat/sessions/{id}/compact — owner gate, nothing-to-compact,
     happy path (persist + counts), summarizer failure → 502 + unchanged,
     re-compact folds the prior summary, request validation.
  2. The history-loader splice in stream_response — a compacted session
     fetches only sequence_num >= compacted_before_seq and prepends the
     stored summary as the `<summary>` system message.
  3. The shared summary-message convention (compaction.summary_message).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.compaction import summary_message
from tests.conftest import (
    TEST_MODEL_REF,
    TEST_SESSION_ID,
    TEST_USER_ID,
    FakeRecord,
    make_session_record,
)


def _msg_row(seq: int, role: str = "user", content: str | None = None) -> FakeRecord:
    return FakeRecord({
        "sequence_num": seq,
        "role": role,
        "content": content or f"message {seq}",
    })


def _compact_session_record(**overrides):
    return make_session_record(
        compact_summary=overrides.pop("compact_summary", None),
        compacted_before_seq=overrides.pop("compacted_before_seq", None),
        **overrides,
    )


class TestCompactRoute:
    @pytest.mark.asyncio
    async def test_not_owner_returns_404(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None  # owner-scoped SELECT found nothing
        resp = await client.post(f"/v1/chat/sessions/{uuid4()}/compact", json={})
        assert resp.status_code == 404
        mock_pool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nothing_to_compact_returns_409(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record()
        # 8 messages ≤ keep_recent default 8 → droppable empty
        mock_pool.fetch.return_value = [_msg_row(i) for i in range(1, 9)]
        resp = await client.post(f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={})
        assert resp.status_code == 409
        assert "nothing to compact" in resp.json()["detail"]
        mock_pool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_happy_path_persists_and_returns_counts(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record()
        mock_pool.fetch.return_value = [_msg_row(i) for i in range(1, 13)]  # 12 msgs
        summarizer = AsyncMock(return_value="dense synopsis of the early plot")

        with patch("app.routers.sessions.summarize_for_compaction", summarizer):
            resp = await client.post(
                f"/v1/chat/sessions/{TEST_SESSION_ID}/compact",
                json={"instructions": "keep all plot promises and character names"},
            )

        assert resp.status_code == 200
        body = resp.json()
        # 12 msgs, keep_recent 8 → 4 compacted; first KEPT message is seq 5.
        assert body["compacted_message_count"] == 4
        assert body["compacted_before_seq"] == 5
        assert body["summary_tokens"] > 0
        assert body["tokens_before_estimate"] > body["tokens_after_estimate"] > 0

        # the summarizer got the droppable middle + the user's instructions verbatim
        args, kwargs = summarizer.await_args
        assert [m["content"] for m in args[0]] == [f"message {i}" for i in range(1, 5)]
        assert kwargs["instructions"] == "keep all plot promises and character names"
        assert kwargs["model_source"] == "user_model"
        assert kwargs["model_ref"] == TEST_MODEL_REF
        assert kwargs["user_id"] == TEST_USER_ID

        # persisted: UPDATE with the summary + the first-kept seq
        update_call = mock_pool.execute.await_args
        assert "UPDATE chat_sessions SET compact_summary" in update_call.args[0]
        assert "dense synopsis of the early plot" in update_call.args
        assert 5 in update_call.args

    @pytest.mark.asyncio
    async def test_keep_recent_override(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record()
        mock_pool.fetch.return_value = [_msg_row(i) for i in range(1, 13)]
        with patch("app.routers.sessions.summarize_for_compaction", AsyncMock(return_value="s")):
            resp = await client.post(
                f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={"keep_recent": 2},
            )
        assert resp.status_code == 200
        assert resp.json()["compacted_message_count"] == 10
        assert resp.json()["compacted_before_seq"] == 11

    @pytest.mark.asyncio
    async def test_summarizer_failure_returns_502_session_unchanged(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record()
        mock_pool.fetch.return_value = [_msg_row(i) for i in range(1, 13)]
        with patch(
            "app.routers.sessions.summarize_for_compaction",
            AsyncMock(side_effect=RuntimeError("provider down")),
        ):
            resp = await client.post(f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={})
        assert resp.status_code == 502
        assert "session unchanged" in resp.json()["detail"]
        mock_pool.execute.assert_not_awaited()  # never persist a failed compact

    @pytest.mark.asyncio
    async def test_blank_summary_rejected(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record()
        mock_pool.fetch.return_value = [_msg_row(i) for i in range(1, 13)]
        with patch("app.routers.sessions.summarize_for_compaction", AsyncMock(return_value="")):
            resp = await client.post(f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={})
        assert resp.status_code == 502
        mock_pool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_recompact_folds_prior_summary_and_skips_covered_rows(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record(
            compact_summary="old synopsis", compacted_before_seq=5,
        )
        # only seq >= 5 exist in the fetch result (the SQL filters)
        mock_pool.fetch.return_value = [_msg_row(i) for i in range(5, 17)]
        summarizer = AsyncMock(return_value="new folded synopsis")

        with patch("app.routers.sessions.summarize_for_compaction", summarizer):
            resp = await client.post(f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["compacted_before_seq"] == 9  # 12 rows, keep 8 → first kept = seq 9
        assert body["compacted_message_count"] == 4  # real messages only, not the fold

        # the messages query was scoped to the un-covered tail
        fetch_sql = mock_pool.fetch.await_args.args[0]
        assert "sequence_num >= $2" in fetch_sql
        assert 5 in mock_pool.fetch.await_args.args

        # the prior summary rides in as the FIRST summarizer message (the fold)
        summarized = summarizer.await_args.args[0]
        assert summarized[0] == summary_message("old synopsis")
        assert summarized[1]["content"] == "message 5"

    @pytest.mark.asyncio
    async def test_concurrent_compact_race_returns_409(self, client, mock_pool):
        """The final UPDATE is guarded on the marker read at start — a compact
        that landed during the seconds-long summarizer call must NOT be
        last-write-wins clobbered."""
        mock_pool.fetchrow.return_value = _compact_session_record()
        mock_pool.fetch.return_value = [_msg_row(i) for i in range(1, 13)]
        mock_pool.execute.return_value = "UPDATE 0"  # marker moved under us
        with patch("app.routers.sessions.summarize_for_compaction", AsyncMock(return_value="s")):
            resp = await client.post(f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={})
        assert resp.status_code == 409
        assert "another compact landed" in resp.json()["detail"]
        # the guard is NULL-safe (IS NOT DISTINCT FROM) and carries the prev marker
        update_call = mock_pool.execute.await_args
        assert "compacted_before_seq IS NOT DISTINCT FROM $5" in update_call.args[0]
        assert update_call.args[-1] is None  # never-compacted session → NULL guard

    @pytest.mark.asyncio
    async def test_recompact_guard_carries_prev_marker(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record(
            compact_summary="old synopsis", compacted_before_seq=5,
        )
        mock_pool.fetch.return_value = [_msg_row(i) for i in range(5, 17)]
        mock_pool.execute.return_value = "UPDATE 1"
        with patch("app.routers.sessions.summarize_for_compaction", AsyncMock(return_value="s")):
            resp = await client.post(f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={})
        assert resp.status_code == 200
        assert mock_pool.execute.await_args.args[-1] == 5  # guard = the marker we read

    @pytest.mark.asyncio
    async def test_request_validation(self, client, mock_pool):
        # instructions over the ~500-char cap → 422
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={"instructions": "x" * 501},
        )
        assert resp.status_code == 422
        # keep_recent must be >= 1
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={"keep_recent": 0},
        )
        assert resp.status_code == 422


class TestCompactClear:
    """``{"clear": true}`` wipes the stored compact (summary + marker)."""

    @pytest.mark.asyncio
    async def test_clear_nulls_marker_and_returns_cleared(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record(
            compact_summary="old synopsis", compacted_before_seq=5,
        )
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/compact", json={"clear": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cleared"] is True
        assert body["compacted_before_seq"] is None
        assert body["compacted_message_count"] == 0
        update_call = mock_pool.execute.await_args
        assert "compact_summary=NULL" in update_call.args[0]
        assert "compacted_before_seq=NULL" in update_call.args[0]
        # clear never reads messages or calls the summarizer
        mock_pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clear_mutually_exclusive_with_compact_args(self, client, mock_pool):
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/compact",
            json={"clear": True, "instructions": "keep names"},
        )
        assert resp.status_code == 422
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/compact",
            json={"clear": True, "keep_recent": 4},
        )
        assert resp.status_code == 422
        mock_pool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clear_not_owner_returns_404(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.post(
            f"/v1/chat/sessions/{uuid4()}/compact", json={"clear": True},
        )
        assert resp.status_code == 404
        mock_pool.execute.assert_not_awaited()


class TestSessionSerializerExposesCompactMarker:
    @pytest.mark.asyncio
    async def test_get_session_returns_compacted_before_seq(self, client, mock_pool):
        mock_pool.fetchrow.return_value = _compact_session_record(
            compact_summary="a synopsis", compacted_before_seq=7,
        )
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["compacted_before_seq"] == 7
        # the summary text itself stays server-side (payload hygiene)
        assert "compact_summary" not in body

    @pytest.mark.asyncio
    async def test_get_session_never_compacted_is_null(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record()
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}")
        assert resp.status_code == 200
        assert resp.json()["compacted_before_seq"] is None


# ── History-loader splice ────────────────────────────────────────────────────

from contextlib import asynccontextmanager  # noqa: E402

from app.services.stream_service import stream_response  # noqa: E402
from tests.test_stream_service import _make_chunk, _make_creds  # noqa: E402


def _make_pool(session_row: dict):
    pool = AsyncMock()
    conn = AsyncMock()

    @asynccontextmanager
    async def fake_acquire():
        yield conn

    @asynccontextmanager
    async def fake_transaction():
        yield

    pool.acquire = fake_acquire
    conn.transaction = fake_transaction
    pool.fetchrow.return_value = session_row
    pool.fetchval.return_value = 5  # skip auto-title
    conn.fetchval.return_value = 3
    return pool, conn


def _capture_gateway(captured: dict):
    """A _stream_via_gateway replacement that records its kwargs."""
    def factory(**kwargs):
        captured.update(kwargs)

        async def gen():
            yield _make_chunk("ok")
            yield _make_chunk(None)
        return gen()
    return factory


class TestHistorySplice:
    @pytest.mark.asyncio
    async def test_compacted_session_splices_summary_and_filters_seq(self):
        pool, _conn = _make_pool({
            "system_prompt": None,
            "generation_params": {},
            "compact_summary": "the hero met the villain in chapter one",
            "compacted_before_seq": 42,
        })
        pool.fetch.return_value = [_msg_row(43, role="user", content="latest question")]
        captured: dict = {}

        with patch(
            "app.services.stream_service._stream_via_gateway",
            MagicMock(side_effect=_capture_gateway(captured)),
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="latest question",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        # the history query was seq-scoped to the un-compacted tail
        history_calls = [
            c for c in pool.fetch.await_args_list if "FROM chat_messages" in c.args[0]
        ]
        assert history_calls, "history fetch did not run"
        sql = history_calls[0].args[0]
        assert "sequence_num >= $3" in sql
        assert 42 in history_calls[0].args

        # the summary rides as a `<summary>` system message BEFORE the history
        msgs = captured["messages"]
        summary_idx = next(
            i for i, m in enumerate(msgs)
            if m["role"] == "system" and "<summary>" in (m.get("content") or "")
        )
        assert "the hero met the villain in chapter one" in msgs[summary_idx]["content"]
        latest_idx = next(i for i, m in enumerate(msgs) if m.get("content") == "latest question")
        assert summary_idx < latest_idx

    @pytest.mark.asyncio
    async def test_uncompacted_session_takes_the_plain_path(self):
        pool, _conn = _make_pool({
            "system_prompt": None,
            "generation_params": {},
            "compact_summary": None,
            "compacted_before_seq": None,
        })
        pool.fetch.return_value = [_msg_row(1, role="user", content="hello")]
        captured: dict = {}

        with patch(
            "app.services.stream_service._stream_via_gateway",
            MagicMock(side_effect=_capture_gateway(captured)),
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="hello",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        history_calls = [
            c for c in pool.fetch.await_args_list if "FROM chat_messages" in c.args[0]
        ]
        assert history_calls
        assert "sequence_num >=" not in history_calls[0].args[0]
        assert all(
            "<summary>" not in (m.get("content") or "")
            for m in captured["messages"] if isinstance(m.get("content"), str)
        )


def test_summary_message_convention():
    msg = summary_message("  a synopsis  ")
    assert msg == {"role": "system", "content": "<summary>\na synopsis\n</summary>"}


class TestSummarizerThinkingOff:
    """The summary call must DISABLE hidden thinking (live-caught: gemma spent
    the whole max_tokens budget on ReasoningEvents and returned EMPTY prose)."""

    @pytest.mark.asyncio
    async def test_stream_request_carries_reasoning_off_fields(self):
        from loreweave_llm import TokenEvent

        from app.services.compact_service import summarize_for_compaction

        captured: dict = {}

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            def stream(self, request):
                captured["request"] = request

                async def _gen():
                    yield TokenEvent(delta="synopsis text")

                return _gen()

            async def aclose(self):
                return None

        with patch("app.services.compact_service.Client", _FakeClient):
            out = await summarize_for_compaction(
                [{"role": "user", "content": "hello"}],
                model_source="user_model", model_ref=str(uuid4()),
                user_id=TEST_USER_ID,
            )
        assert out == "synopsis text"
        req = captured["request"]
        # thinking OFF on the wire — reasoning tokens must not eat the budget
        assert req.reasoning_effort == "none"
        assert req.chat_template_kwargs == {"thinking": False, "enable_thinking": False}
