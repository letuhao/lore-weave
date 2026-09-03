"""D-ONE-PASS-RECORDED-TWICE-WHEN-THE-SURFACE-FILTERS-TO-EMPTY.

`advertised_tools` is documented as ONE ENTRY PER MODEL PASS. In `_stream_with_tools` three
separate statements can emit that chunk, and two of them could fire for the SAME pass:

    offered_tools = tools_supported and not last_iter
    if offered_tools:
        ...
        if not advertised:
            yield {"advertised": _adv_ev_pending}        # (1) fires: the surface is empty
        if advertised:
            ...
        else:
            offered_tools = False                        # <- reassigned, mid-pass
    if not offered_tools:
        yield {"advertised": {...}}                      # (2) fires too, because of (1)'s branch

`offered_tools` is not a constant across the block. When ask/plan mode filters every tool out,
the `else` flips it False on a pass that has ALREADY emitted, and one model call is recorded
twice, under two different `pass` numbers.

WHY IT MATTERS — the DENOMINATOR. "advertised in N of M passes" reads M from this column, and M
was one too many whenever this fired. It also masks the opposite defect: D-THE-PERSISTED-PER-PASS-
RECORDER-DROPS-A-PASS-ON-THE-SECOND-TURN compares this column against the "agent-surface
advertised" log line, which prints only for TOOL-BEARING passes — so a spurious empty entry can
cover a genuinely lost pass.

MEASURED 2026-08-28 over the live store: at most 1 adjacent empty-name pair across the 5,759
messages carrying the column, and that pair may be two genuine tool-free passes. So the path is
real by construction and very rare in practice. This is a correctness guard, not a fix for an
observed measurement error.

🔴 THESE TESTS DRIVE THE REAL GENERATOR. An assertion about the source text would have passed
against the broken code too — the bug is not a missing line, it is two live lines whose guards
overlap, and only running the block can tell them apart.
"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services import stream_service as ss  # noqa: E402
from tests.conftest import TEST_MODEL_REF  # noqa: E402


class _OneTextPass:
    """A provider that answers with plain text, so the loop runs exactly ONE pass — any second
    `advertised` chunk is therefore a duplicate of the same pass, not a second pass."""

    def __init__(self, **kw):
        pass

    async def aclose(self):
        pass

    def stream(self, request):
        from loreweave_llm import DoneEvent, TokenEvent

        async def gen():
            yield TokenEvent(delta="done")
            yield DoneEvent(finish_reason="stop")

        return gen()


async def _advertised_chunks(*, tools, permission_mode):
    kc = AsyncMock()
    kc.get_catalog_meta = MagicMock(return_value={})
    out = []
    with patch.object(ss, "Client", _OneTextPass):
        async for c in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "hi"}],
            gen_params={"max_tokens": 100}, tools=tools,
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode=permission_mode,
        ):
            if c.get("advertised") is not None:
                out.append(c["advertised"])
    return out


@pytest.mark.asyncio
async def test_a_pass_whose_surface_filters_to_EMPTY_records_exactly_one_entry():
    """THE DEFECT'S OWN PATH. `ask` mode drops every tiered write, so a catalog holding only a
    Tier-A tool filters to an empty surface — which is what makes both emit sites fire."""
    tools = [{"type": "function",
              "function": {"name": "book_purge", "description": "", "parameters": {},
                           "_meta": {"tier": "A", "scope": "book"}}}]
    chunks = await _advertised_chunks(tools=tools, permission_mode="ask")
    assert len(chunks) == 1, (
        f"one model pass produced {len(chunks)} advertised entries: {chunks!r} — the per-pass "
        "record double-counts, so every 'N of M passes' denominator read from this column is "
        "one too many on this path"
    )


@pytest.mark.asyncio
async def test_a_tool_free_turn_still_records_its_pass():
    """The guard must not silence the legitimate emit. A pass that offers no tools is still a
    pass, and recording nothing for it is the defect CP-0.1 fixed — a tool present on pass 1 and
    absent on a tool-free pass 2 would otherwise read as 'still offered'."""
    chunks = await _advertised_chunks(tools=[], permission_mode="write")
    assert len(chunks) == 1, (
        f"a tool-free pass recorded {len(chunks)} entries; it must record exactly one"
    )
    assert chunks[0]["names"] == []


@pytest.mark.asyncio
async def test_a_normal_tool_bearing_pass_is_unchanged():
    """Write mode is the path every real turn takes; the guard must be a no-op there."""
    tools = [{"type": "function",
              "function": {"name": "book_read", "description": "", "parameters": {},
                           "_meta": {"tier": "R", "scope": "book"}}}]
    chunks = await _advertised_chunks(tools=tools, permission_mode="write")
    assert len(chunks) == 1
    assert "book_read" in chunks[0]["names"]
