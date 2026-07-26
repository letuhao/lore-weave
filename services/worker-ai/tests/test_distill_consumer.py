"""A1 / P-10 — the assistant.distill consumer's decode + run-pipeline logic (fakes, no Redis).

Proves the message → params → distill_and_write path, the ack contract (malformed → ack-drop;
retryable → leave un-acked; terminal → ack), and bytes-vs-str Redis field tolerance.
"""

from __future__ import annotations

import json

from app import distill_consumer as dc


class FakeChat:
    def __init__(self, messages, truncated=False):
        self._messages = messages
        self._truncated = truncated
        self.calls = []

    async def get_day_window(self, *, user_id, book_id, local_date, limit):
        self.calls.append({"user_id": user_id, "book_id": book_id, "local_date": local_date})
        return self._messages, self._truncated


class FakeBook:
    def __init__(self, kept=False):
        self.writes = []
        self._kept = kept

    # WS-3.3 — the pre-LLM kept-gate the pipeline checks before the map-reduce (distill_job.py). The stub
    # was missing this method, reddening the suite at HEAD; default False → the pipeline proceeds.
    async def diary_day_kept(self, **kwargs):
        return self._kept

    async def write_diary_entry(self, **kwargs):
        self.writes.append(kwargs)
        return {"chapter_id": "ch-1", "created": True}


class _Job:
    def __init__(self, status, result=None, error=None):
        self.status = status
        self.result = result
        self.error = error


class RoutingSubmitter:
    """Answers map (MESSAGES:) vs reduce (FACTS:) by prompt; raises if `boom`."""

    def __init__(self, boom=False):
        self._boom = boom
        self.calls = 0

    async def submit_and_wait(self, **kwargs):
        self.calls += 1
        if self._boom:
            raise RuntimeError("LLM_CIRCUIT_OPEN")
        prompt = kwargs["input"]["messages"][0]["content"]
        if "FACTS:" in prompt and "MESSAGES:" not in prompt:
            body = json.dumps({"summary": "A live-wired day.", "decisions": ["Ship it."]})
        else:
            body = json.dumps({"facts": [{"kind": "decision", "text": "Ship it.", "provenance": "user"}]})
        return _Job("completed", result={"messages": [{"content": body}]})


def _fields(**over):
    f = {
        "user_id": "u1", "book_id": "b1", "entry_date": "2026-03-10", "entry_zone": "UTC",
        "language": "en", "model_source": "user_model", "model_ref": "m1",
    }
    f.update(over)
    return f


async def test_a_valid_message_runs_the_pipeline_and_acks():
    chat = FakeChat([{"role": "user", "content": "Met Minh; decided to ship.", "tool_names": []}])
    book = FakeBook()
    ack = await dc.run_one_distill_message(
        chat_client=chat, book_client=book, llm_client=RoutingSubmitter(), fields=_fields(),
    )
    assert ack is True
    assert len(book.writes) == 1
    w = book.writes[0]
    assert w["book_id"] == "b1" and w["owner_user_id"] == "u1" and w["entry_date"] == "2026-03-10"
    assert "A live-wired day." in w["body"]


async def test_bytes_keyed_fields_from_real_redis_decode():
    # Real Redis returns bytes keys AND values — the decoder must tolerate both.
    raw = {k.encode(): str(v).encode() for k, v in _fields().items()}
    chat = FakeChat([{"role": "user", "content": "did a thing", "tool_names": []}])
    book = FakeBook()
    ack = await dc.run_one_distill_message(
        chat_client=chat, book_client=book, llm_client=RoutingSubmitter(), fields=raw,
    )
    assert ack is True and len(book.writes) == 1


async def test_a_malformed_message_is_acked_and_never_runs_the_pipeline():
    chat = FakeChat([])
    book = FakeBook()
    sub = RoutingSubmitter()
    ack = await dc.run_one_distill_message(
        chat_client=chat, book_client=book, llm_client=sub, fields=_fields(model_ref=""),  # missing
    )
    assert ack is True  # dropped as poison
    assert book.writes == [] and sub.calls == 0 and chat.calls == []


async def test_a_retryable_distill_error_leaves_the_message_un_acked():
    # A total model outage → distill_and_write returns status=error/retryable → do NOT ack (redeliver).
    chat = FakeChat([{"role": "user", "content": "a busy day", "tool_names": []}])
    book = FakeBook()
    ack = await dc.run_one_distill_message(
        chat_client=chat, book_client=book, llm_client=RoutingSubmitter(boom=True), fields=_fields(),
    )
    assert ack is False
    assert book.writes == []  # nothing written; the day is retried, not dropped


async def test_a_low_signal_day_acks_without_writing():
    # An empty day is a terminal (non-retryable) state → ack, no entry, no infinite redelivery.
    chat = FakeChat([])  # no messages → empty_day
    book = FakeBook()
    ack = await dc.run_one_distill_message(
        chat_client=chat, book_client=book, llm_client=RoutingSubmitter(), fields=_fields(),
    )
    assert ack is True and book.writes == []


# B2 (D-DISTILL-WINDOW-MODEL-AWARE) — the consumer resolves the model's context length and passes the
# adapted window into distill_and_write (best-effort: default 12k when unknown / no provider / on error).
from unittest.mock import AsyncMock, patch  # noqa: E402


class _Provider:
    def __init__(self, ctx):
        self._ctx = ctx
    async def get_context_length(self, model_source, model_ref):
        return self._ctx


class _BoomProvider:
    async def get_context_length(self, model_source, model_ref):
        raise RuntimeError("provider-registry down")


async def _window_for(provider):
    with patch("app.distill_consumer.distill_and_write",
               new=AsyncMock(return_value={"status": "written"})) as m:
        kwargs = dict(chat_client=FakeChat([]), book_client=FakeBook(),
                      llm_client=RoutingSubmitter(), fields=_fields())
        if provider is not _MISSING:
            kwargs["provider_client"] = provider
        await dc.run_one_distill_message(**kwargs)
    return m.await_args.kwargs["window"]


_MISSING = object()


async def test_window_shrinks_for_a_small_context_model():
    assert await _window_for(_Provider(8_000)) == 8_000 - 2_048 - 2_048  # 3904


async def test_window_defaults_when_ctx_unknown():
    assert await _window_for(_Provider(None)) == 12_000


async def test_window_defaults_when_no_provider_client():
    assert await _window_for(_MISSING) == 12_000


async def test_window_defaults_when_resolve_raises():
    assert await _window_for(_BoomProvider()) == 12_000
