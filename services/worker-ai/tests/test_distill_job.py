"""WS-1.8 (spec 06) — the distiller ORCHESTRATOR (read -> distill -> write).

Proves the read/distill/write flow and every terminal status with fake clients + a fake model, so
no branch depends on a live stack: written, low-signal no_entry, giant-paste oversized, a kept-day
supplement signal, a day-window transport failure, and a write failure. Also proves the write
receives the rendered entry body (not raw messages) and that `truncated` propagates.
"""

from __future__ import annotations

import json

from app import distill_job
from app.distiller import GIANT_PASTE_CHARS


class FakeChat:
    def __init__(self, messages, truncated=False, fail=False):
        self._messages = messages
        self._truncated = truncated
        self._fail = fail
        self.calls: list[dict] = []

    async def get_day_window(self, *, user_id, book_id, local_date, limit):
        self.calls.append({"user_id": user_id, "book_id": book_id, "local_date": local_date, "limit": limit})
        if self._fail:
            return None
        return self._messages, self._truncated


class FakeBook:
    def __init__(self, result=None):
        self._result = result if result is not None else {"chapter_id": "ch-1", "created": True}
        self.writes: list[dict] = []

    async def write_diary_entry(self, **kwargs):
        self.writes.append(kwargs)
        return self._result


class FakeLLM:
    """Answers map calls ('MESSAGES:') with canned facts, reduce ('FACTS:') with a canned entry."""

    def __init__(self, map_facts, reduce_obj=None):
        self._map_facts = map_facts
        self._reduce_obj = reduce_obj or {"summary": "A good day.", "decisions": ["Ship v2."]}

    async def __call__(self, prompt: str) -> str:
        if "FACTS:" in prompt and "MESSAGES:" not in prompt:
            return json.dumps(self._reduce_obj)
        return json.dumps({"facts": self._map_facts})


class FakeKnowledge:
    def __init__(self, fail=False):
        self._fail = fail
        self.calls: list[dict] = []

    async def queue_diary_facts(self, *, user_id, book_id, entry_date, facts):
        self.calls.append({"user_id": user_id, "book_id": book_id, "entry_date": entry_date, "facts": facts})
        if self._fail:
            raise RuntimeError("inbox down")
        return {"queued": len(facts)}


def _msg(role, content, tools=None):
    return {"role": role, "content": content, "tool_names": tools or []}


async def test_written_flow_passes_rendered_body_to_the_write_seam():
    chat = FakeChat([_msg("user", "Met Minh about the redesign.")], truncated=True)
    book = FakeBook()
    llm = FakeLLM(map_facts=[{"kind": "decision", "text": "Ship v2.", "provenance": "user"}])

    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=llm, chat_client=chat, book_client=book,
    )

    assert out["status"] == "written"
    assert out["chapter_id"] == "ch-1"
    assert out["facts_found"] == 1
    assert out["truncated"] is True  # propagated from the read
    # The write got the RENDERED entry body (sections), never the raw messages.
    assert len(book.writes) == 1
    w = book.writes[0]
    assert w["book_id"] == "b1" and w["owner_user_id"] == "u1"
    assert w["entry_date"] == "2026-03-10" and w["entry_zone"] == "UTC"
    assert w["journal_kind"] == "primary" and w["language"] == "en"
    assert "A good day." in w["body"] and "## Decisions" in w["body"]
    assert "Met Minh" not in w["body"]  # the transcript is NOT copied into the entry


async def test_written_flow_queues_facts_to_the_kg_inbox():
    # WS-2.3: after the entry is written, the day's facts are DIVERTED to the pending-facts inbox.
    chat = FakeChat([_msg("user", "Met Minh; froze the Q3 budget.")])
    book = FakeBook()
    know = FakeKnowledge()
    llm = FakeLLM(map_facts=[
        {"kind": "decision", "text": "froze the Q3 budget", "provenance": "user"},
        {"kind": "person", "text": "Minh", "provenance": "user"},
    ])
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=llm, chat_client=chat, book_client=book, knowledge_client=know,
    )
    assert out["status"] == "written" and out["facts_queued"] == 2
    assert len(know.calls) == 1
    c = know.calls[0]
    assert c["user_id"] == "u1" and c["book_id"] == "b1" and c["entry_date"] == "2026-03-10"
    assert {f["kind"] for f in c["facts"]} == {"decision", "person"}


async def test_fact_queue_failure_does_not_fail_the_written_day():
    # BEST-EFFORT: the entry is already durably written, so an inbox failure must NOT fail the distill
    # or lose the day — the facts are a reviewable enrichment, retried on the next distill.
    chat = FakeChat([_msg("user", "Froze the budget.")])
    book = FakeBook()
    llm = FakeLLM(map_facts=[{"kind": "decision", "text": "froze the budget", "provenance": "user"}])
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=llm, chat_client=chat, book_client=book, knowledge_client=FakeKnowledge(fail=True),
    )
    assert out["status"] == "written" and out["facts_queued"] == 0  # entry stands; inbox failure swallowed


async def test_low_signal_day_writes_nothing():
    chat = FakeChat([_msg("user", "ok"), _msg("user", "sure")])
    book = FakeBook()
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=FakeLLM(map_facts=[]), chat_client=chat, book_client=book,
    )
    assert out["status"] == "no_entry" and out["reason"] == "low_signal"
    assert book.writes == []  # never wrote a stub


async def test_a_day_of_only_a_giant_paste_is_oversized_and_not_written():
    big = _msg("user", "x" * (GIANT_PASTE_CHARS + 1))
    chat = FakeChat([big])
    book = FakeBook()
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=FakeLLM(map_facts=[{"kind": "e", "text": "nope"}]),
        chat_client=chat, book_client=book,
    )
    assert out["status"] == "oversized" and out["reason"] == "giant_paste"
    assert out["oversized_count"] == 1
    assert book.writes == []


async def test_a_giant_paste_alongside_a_real_day_still_writes_the_entry():
    # The T38 fix at the orchestrator level: a real day + a paste → the entry IS written and the
    # paste is surfaced (oversized_count) for the attach-offer, not dropped.
    big = _msg("user", "x" * (GIANT_PASTE_CHARS + 1))
    chat = FakeChat([_msg("user", "Met Minh."), big])
    book = FakeBook()
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=FakeLLM(map_facts=[{"kind": "e", "text": "a fact"}]),
        chat_client=chat, book_client=book,
    )
    assert out["status"] == "written" and out["oversized_count"] == 1
    assert len(book.writes) == 1


async def test_day_window_unavailable_is_retryable_error_not_an_empty_entry():
    chat = FakeChat([], fail=True)
    book = FakeBook()
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=FakeLLM(map_facts=[]), chat_client=chat, book_client=book,
    )
    assert out["status"] == "error" and out["reason"] == "day_window_unavailable"
    assert out["retryable"] is True
    assert book.writes == []  # a read failure must NEVER produce an entry


async def test_kept_day_returns_kept_so_caller_supplements():
    chat = FakeChat([_msg("user", "Met Minh.")])
    book = FakeBook(result={"kept": True})
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=FakeLLM(map_facts=[{"kind": "e", "text": "a fact"}]),
        chat_client=chat, book_client=book,
    )
    assert out["status"] == "kept"


async def test_a_model_outage_is_retryable_and_never_drops_the_day():
    # Finding 1 at the orchestrator level: a map/reduce provider outage → status error + retryable,
    # and NOTHING is written (the day is retried later, not silently lost as a low-signal no-entry).
    async def boom(_prompt):
        raise RuntimeError("LLM_CIRCUIT_OPEN")

    chat = FakeChat([_msg("user", "A busy, productive day.")])
    book = FakeBook()
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=boom, chat_client=chat, book_client=book,
    )
    assert out["status"] == "error" and out["reason"] == "map_failed" and out["retryable"] is True
    assert book.writes == []


async def test_write_failure_is_a_retryable_error():
    chat = FakeChat([_msg("user", "Met Minh.")])
    book = FakeBook(result={"error": "HTTP 503", "retryable": True})
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=FakeLLM(map_facts=[{"kind": "e", "text": "a fact"}]),
        chat_client=chat, book_client=book,
    )
    assert out["status"] == "error" and out["reason"] == "write_failed" and out["retryable"] is True


# ── the SDK LLM adapter (the provider-gateway path) ───────────────────────────


class _FakeJob:
    def __init__(self, status, result=None, error=None):
        self.status = status
        self.result = result
        self.error = error


class FakeSubmitter:
    def __init__(self, job):
        self._job = job
        self.calls: list[dict] = []

    async def submit_and_wait(self, **kwargs):
        self.calls.append(kwargs)
        return self._job


async def test_distill_llm_adapter_sends_a_chat_job_and_returns_the_content():
    sub = FakeSubmitter(_FakeJob("completed", result={"messages": [{"role": "assistant", "content": "hi there"}]}))
    call = distill_job.make_distill_llm(sub, user_id="u1", model_source="user_model", model_ref="m1")
    text = await call("some prompt")
    assert text == "hi there"
    k = sub.calls[0]
    assert k["operation"] == "chat" and k["model_ref"] == "m1" and k["user_id"] == "u1"
    assert k["input"]["messages"][0]["content"] == "some prompt"
    assert k["input"]["chat_template_kwargs"]["thinking"] is False  # anti-reasoning-burn


async def test_distill_llm_adapter_raises_on_a_failed_job():
    sub = FakeSubmitter(_FakeJob("failed", error="LLM_CIRCUIT_OPEN"))
    call = distill_job.make_distill_llm(sub, user_id="u1", model_source="user_model", model_ref="m1")
    try:
        await call("x")
    except RuntimeError as e:
        assert "failed" in str(e)
    else:
        raise AssertionError("a non-completed job must raise so the day degrades, not fabricates")


async def test_distill_llm_adapter_end_to_end_with_the_core():
    # The adapter + the pure core together: a fake submitter that answers map vs reduce by prompt.
    class RoutingSubmitter:
        async def submit_and_wait(self, **kwargs):
            prompt = kwargs["input"]["messages"][0]["content"]
            if "FACTS:" in prompt and "MESSAGES:" not in prompt:
                body = json.dumps({"summary": "Distilled via the gateway path."})
            else:
                body = json.dumps({"facts": [{"kind": "event", "text": "a real fact", "provenance": "user"}]})
            return _FakeJob("completed", result={"messages": [{"content": body}]})

    llm = distill_job.make_distill_llm(RoutingSubmitter(), user_id="u1", model_source="user_model", model_ref="m1")
    chat = FakeChat([_msg("user", "Something happened today.")])
    book = FakeBook()
    out = await distill_job.distill_and_write(
        user_id="u1", book_id="b1", entry_date="2026-03-10", entry_zone="UTC",
        language="en", llm=llm, chat_client=chat, book_client=book,
    )
    assert out["status"] == "written"
    assert "Distilled via the gateway path." in book.writes[0]["body"]
