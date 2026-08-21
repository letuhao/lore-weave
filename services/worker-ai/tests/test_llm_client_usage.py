"""Token accounting must survive the extraction fan-out.

`extract_pass2` runs the relation/event/fact trio through `asyncio.gather`
(sdks/python/loreweave_extraction/pass2.py), and the precision filter does the
same in `pass2_filter.py`. `gather` wraps each coroutine in a Task and a Task
COPIES the context at creation, so anything a child *rebinds* on a ContextVar
dies with the child.

The Jobs GUI cost hint therefore undercounted: an accumulator held as an
immutable tuple counted only the entity pass (made in the parent's own task) and
silently dropped the whole trio. These tests pin the shape that fixes it — one
mutable accumulator, shared by reference — and would fail against the tuple.
"""

from __future__ import annotations

import asyncio

from app.llm_client import LLMClient, begin_usage_capture


class _FakeJob:
    """Minimal stand-in for loreweave_llm's terminal Job: only `.result` is read."""

    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.result = {
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        }


def _client() -> LLMClient:
    return LLMClient(sdk_client=None)  # no SDK call is made; _record_usage is pure


async def test_usage_recorded_inside_gathered_children_reaches_the_parent():
    """THE REGRESSION. Four calls, one in the parent + three fanned out like the
    trio; the parent must see all four. With a tuple-valued ContextVar the three
    children's tokens are discarded and this reads (100, 10)."""
    client = _client()
    begin_usage_capture()

    client._record_usage(_FakeJob(100, 10))  # entity pass — parent's own task

    async def _child(tokens_in: int, tokens_out: int) -> None:
        client._record_usage(_FakeJob(tokens_in, tokens_out))

    # relations / events / facts — exactly pass2.py's gather
    await asyncio.gather(_child(200, 20), _child(300, 30), _child(400, 40))

    assert client.take_usage() == (1000, 100)


async def test_take_usage_resets_so_the_next_segment_starts_at_zero():
    client = _client()
    begin_usage_capture()
    client._record_usage(_FakeJob(5, 1))
    assert client.take_usage() == (5, 1)
    assert client.take_usage() == (0, 0)


async def test_take_usage_reset_still_collects_from_children_spawned_earlier():
    """`take_usage` must zero the accumulator IN PLACE. If it installed a fresh
    object instead, a child task created before the take still holds the old
    reference and its tokens would vanish."""
    client = _client()
    begin_usage_capture()

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_child() -> None:
        started.set()
        await release.wait()
        client._record_usage(_FakeJob(70, 7))

    task = asyncio.create_task(_slow_child())  # inherits the accumulator as it is now
    await started.wait()

    assert client.take_usage() == (0, 0)  # a take happens while the child is in flight
    release.set()
    await task

    assert client.take_usage() == (70, 7)


async def test_concurrent_jobs_do_not_bill_each_other():
    """Each job installs its OWN accumulator, so two jobs running as separate
    tasks never merge counts — the reason there is no module-level default."""
    client = _client()

    async def _job(tokens: int) -> tuple[int, int]:
        begin_usage_capture()
        client._record_usage(_FakeJob(tokens, tokens // 10))
        await asyncio.sleep(0)  # interleave the two jobs
        client._record_usage(_FakeJob(tokens, tokens // 10))
        return client.take_usage()

    a, b = await asyncio.gather(_job(100), _job(500))
    assert a == (200, 20)
    assert b == (1000, 100)


async def test_recording_without_capture_is_a_noop_not_a_crash():
    """Outside a job (no `begin_usage_capture`) there is nothing to accumulate
    into. That must be silent, and must not invent a process-global counter."""
    client = _client()
    client._record_usage(_FakeJob(9, 9))
    assert client.take_usage() == (0, 0)


async def test_missing_or_malformed_usage_is_ignored():
    client = _client()
    begin_usage_capture()

    class _NoResult:
        result = None

    class _JunkUsage:
        result = {"usage": "not-a-dict"}

    client._record_usage(_NoResult())
    client._record_usage(_JunkUsage())
    assert client.take_usage() == (0, 0)


async def test_openai_style_prompt_completion_token_names_are_accepted():
    """Providers report either input/output_tokens or prompt/completion_tokens."""
    client = _client()
    begin_usage_capture()

    class _OpenAIStyle:
        result = {"usage": {"prompt_tokens": 11, "completion_tokens": 3}}

    client._record_usage(_OpenAIStyle())
    assert client.take_usage() == (11, 3)
