"""C1 — the generation completion seam harvests REAL tokens (DEFERRED-052).

The provider-registry LLM stream emits a final ``event: usage`` frame
(``input_tokens`` / ``output_tokens`` / ``reasoning_tokens``); ``complete.py``
used to discard it. These tests prove:
  * ``collect_stream_usage`` parses that frame (reasoning folded into output);
  * ``make_complete_fn`` feeds the meter the REAL usage when the frame is present;
  * with NO usage frame it falls back to the platform char-estimate of the
    prompt (input) + the collected text (output) — so generation is ALWAYS metered;
  * the seam still returns the plain completion ``str`` (contract unchanged).

No live stack: the HTTP POST is respx-mocked with a canned SSE body.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.generation.complete import (
    collect_stream_text,
    collect_stream_usage,
    make_complete_fn,
)
from app.jobs.tokens import UsageMeter, estimate_tokens, TokenUsage
from app.strategies.base import StrategyContext


def _ctx() -> StrategyContext:
    return StrategyContext(
        user_id="00000000-0000-0000-0000-000000000001",
        project_id="00000000-0000-0000-0000-000000000002",
        model_ref="00000000-0000-0000-0000-000000000003",
    )


_SSE_WITH_USAGE = (
    'event: token\ndata: {"event":"token","delta":"昆侖山"}\n\n'
    'event: token\ndata: {"event":"token","delta":"是一座仙山"}\n\n'
    'event: usage\ndata: {"event":"usage","input_tokens":120,'
    '"output_tokens":40,"reasoning_tokens":8}\n\n'
    'event: done\ndata: {"event":"done"}\n\n'
)

_SSE_NO_USAGE = (
    'event: token\ndata: {"event":"token","delta":"昆侖山"}\n\n'
    'event: done\ndata: {"event":"done"}\n\n'
)

# A provider that emits the usage frame WITHOUT populating counts (or with zeros).
_SSE_EMPTY_USAGE = (
    'event: token\ndata: {"event":"token","delta":"昆侖山"}\n\n'
    'event: usage\ndata: {"event":"usage"}\n\n'
    'event: done\ndata: {"event":"done"}\n\n'
)

# A hostile/buggy upstream sending negative counts.
_SSE_NEGATIVE_USAGE = (
    'event: token\ndata: {"event":"token","delta":"昆侖山"}\n\n'
    'event: usage\ndata: {"event":"usage","input_tokens":-50,"output_tokens":-9}\n\n'
    'event: done\ndata: {"event":"done"}\n\n'
)


# ── parsing ────────────────────────────────────────────────────────────────

def test_collect_stream_text_still_collects_tokens():
    assert collect_stream_text(_SSE_WITH_USAGE) == "昆侖山是一座仙山"


def test_collect_stream_usage_parses_frame_reasoning_as_output():
    usage = collect_stream_usage(_SSE_WITH_USAGE)
    assert usage is not None
    assert usage.input_tokens == 120
    # reasoning (8) folds into output (40) per the platform billing convention.
    assert usage.output_tokens == 48
    assert usage.total == 168


def test_collect_stream_usage_absent_returns_none():
    assert collect_stream_usage(_SSE_NO_USAGE) is None


def test_collect_stream_usage_clamps_negative_to_zero():
    # A hostile/buggy frame must never produce negative counts (review-impl LOW-2).
    usage = collect_stream_usage(_SSE_NEGATIVE_USAGE)
    assert usage == TokenUsage(input_tokens=0, output_tokens=0)


# ── make_complete_fn meter integration ───────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_complete_fn_feeds_meter_real_usage_and_returns_text():
    respx.post("http://pr.local/internal/llm/stream").respond(
        200, text=_SSE_WITH_USAGE
    )
    meter = UsageMeter()
    complete = make_complete_fn(
        provider_registry_base_url="http://pr.local",
        internal_token="t",
        meter=meter,
    )
    text = await complete("写一段关于昆侖山的设定", _ctx())
    assert text == "昆侖山是一座仙山"  # str contract unchanged
    # the REAL usage frame was harvested into the meter.
    assert meter.usage == TokenUsage(input_tokens=120, output_tokens=48)
    assert meter.total_tokens == 168


@pytest.mark.asyncio
@respx.mock
async def test_complete_fn_estimates_when_no_usage_frame():
    respx.post("http://pr.local/internal/llm/stream").respond(
        200, text=_SSE_NO_USAGE
    )
    meter = UsageMeter()
    complete = make_complete_fn(
        provider_registry_base_url="http://pr.local",
        internal_token="t",
        meter=meter,
    )
    prompt = "写一段关于昆侖山的设定"
    text = await complete(prompt, _ctx())
    assert text == "昆侖山"
    # no usage frame → estimate input from prompt, output from collected text.
    assert meter.usage == TokenUsage(
        input_tokens=estimate_tokens(prompt),
        output_tokens=estimate_tokens("昆侖山"),
    )
    assert meter.total_tokens > 0


@pytest.mark.asyncio
@respx.mock
async def test_complete_fn_empty_usage_frame_falls_back_to_estimate():
    """review-impl MED-1: a usage frame present but with NO counts (total 0) is
    not a real measurement — the gap must fall back to the char-estimate, never
    be metered as 0 tokens (which would silently weaken the cost-cap)."""
    respx.post("http://pr.local/internal/llm/stream").respond(
        200, text=_SSE_EMPTY_USAGE
    )
    meter = UsageMeter()
    complete = make_complete_fn(
        provider_registry_base_url="http://pr.local", internal_token="t", meter=meter
    )
    prompt = "写一段关于昆侖山的设定"
    text = await complete(prompt, _ctx())
    assert text == "昆侖山"
    # estimated (NOT 0) — the empty frame was treated as "no real count".
    assert meter.usage == TokenUsage(
        input_tokens=estimate_tokens(prompt),
        output_tokens=estimate_tokens("昆侖山"),
    )
    assert meter.total_tokens > 0


@pytest.mark.asyncio
@respx.mock
async def test_complete_fn_without_meter_is_noop_and_still_returns_text():
    respx.post("http://pr.local/internal/llm/stream").respond(
        200, text=_SSE_WITH_USAGE
    )
    # no meter passed → back-compat: just returns the text, no metering side effect.
    complete = make_complete_fn(
        provider_registry_base_url="http://pr.local", internal_token="t"
    )
    text = await complete("p", _ctx())
    assert text == "昆侖山是一座仙山"
