"""Both-state coverage for `rail_driver_enabled` — the last row of the kill-switch debt.

Why this needed its own file (and why the first attempt was abandoned rather than shipped):
the flag gates a block that is only REACHED when FIVE preconditions hold at once —

  1. the turn is book-scoped (`book_context.book_id` → `_ctx_book_id`),
  2. tool-calling is on and the format is agui (else the workflows fetch never runs),
  3. the registry returns a mode binding that PINS a workflow (`inject_workflows`),
  4. that slug is VISIBLE in the same response (a pin naming an invisible workflow is
     skipped by design),
  5. the caller holds a grant >= VIEW on the book (the probe fails CLOSED).

Mock four of the five and the probe is never called in EITHER state — so an
"OFF ⇒ no probe" assertion passes VACUOUSLY, proving nothing about the lever. That is the
trap this file exists to avoid, so every test here pins the ON case FIRST: the fixture must
be shown to actually reach the probe before its absence means anything.

What the lever is supposed to do (config.py + stream_service): it is a DEPLOY-time
kill-switch over a block that edits an ALWAYS-ON system prompt on every write-mode book
turn — the probe, the grounding block, and the P-1 step-runner drive. OFF must restore the
pre-Phase-2 behavior exactly: no probe, no progress block, no drive context.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_stream_service import _Usage

BOOK_ID = "019d5e3c-7cc5-7e6a-8b27-1344e148beef"

# A real-shaped rail: `compute_rail_progress` parses `done_when`, so the steps must carry
# predicates it understands or the grounding block would be empty for the wrong reason.
RAIL_WF = {
    "slug": "vision-to-book",
    "title": "Turn a story idea into a real book foundation",
    "description": "Build the world, cast, connections and plan.",
    "tier": "system",
    "surfaces": ["book", "editor"],
    "inputs": {},
    "steps": [
        {"id": "categories", "tool": "glossary_adopt_standards",
         "gate": "none", "done_when": "categories > 0"},
        {"id": "cast", "tool": "glossary_propose_entities",
         "gate": "none", "done_when": "cast > 0"},
        {"id": "plan", "tool": "plan_propose_spec",
         "gate": "none", "done_when": "plan > 0"},
    ],
    "notes_md": "Use this when the user is building their book.",
}


def _grant_client(level):
    # NB: `level or DEFAULT` would be WRONG here — GrantLevel is an IntEnum and NONE == 0,
    # so the falsy fallback silently upgrades a no-grant caller to OWNER and the fail-closed
    # test below passes for the wrong reason. (It did, on the first run.)
    c = MagicMock()
    c.resolve_access = AsyncMock(return_value=(level, None))
    return c


async def _run(
    *,
    enabled: bool,
    pinned: bool = True,
    grant=None,
    book_id: str | None = BOOK_ID,
) -> tuple[int, str]:
    """Drive one book-scoped agui turn. Returns ``(probe_call_count, system_prompt_text)``.

    The system text is returned alongside the probe count because the two failure modes are
    different: a probe that never runs (the gate) vs a probe that runs but whose grounding
    never reaches the prompt (the consumer). Asserting only the spy would miss the second.
    """
    from app.client.grant_client import GrantLevel
    from app.services.stream_service import stream_response
    from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID
    from tests.test_stream_service import (
        _make_creds,
        _make_pool_with_conn,
        _patched_knowledge,
    )

    pool, conn = _make_pool_with_conn()
    pool.fetch.return_value = []
    conn.fetchval.return_value = 1
    kc = _patched_knowledge(
        stable="", volatile="", mode="static",
        tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
    )

    wf_client = MagicMock()
    wf_client.get_workflows = AsyncMock(return_value=SimpleNamespace(
        workflows=[RAIL_WF],
        mode_binding=SimpleNamespace(
            mode="write",
            inject_skills=[],
            inject_workflows=["vision-to-book"] if pinned else [],
            seed_tool_categories=[],
        ),
    ))

    # A book with categories but no cast — so the rail has an unmistakable NEXT step, and a
    # progress block with something to say. (Everything else UNKNOWN, the honest default.)
    from loreweave_agent_control.rail import BookState
    probe_spy = AsyncMock(return_value=BookState(categories=12, cast=0, plan=0))

    async def fake_tool_loop(**kwargs):
        yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop",
               "usage": _Usage(1, 1)}

    with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
         patch("app.client.registry_workflows_client.get_workflows_client",
               return_value=wf_client), \
         patch("app.client.grant_client.get_grant_client",
               return_value=_grant_client(grant if grant is not None else GrantLevel.OWNER)), \
         patch("app.db.tool_call_history.succeeded_tool_counts",
               AsyncMock(return_value={})), \
         patch("app.services.book_state_probe.probe_book_state", probe_spy), \
         patch("app.config.settings.rail_driver_enabled", enabled), \
         patch("app.services.stream_service._stream_with_tools",
               side_effect=fake_tool_loop) as loop_mock, \
         patch("app.services.stream_service._stream_via_gateway"):
        async for _ in stream_response(
            session_id=TEST_SESSION_ID, user_message_content="yeah do it",
            user_id=TEST_USER_ID, model_source="user_model",
            model_ref=TEST_MODEL_REF, creds=_make_creds(),
            pool=pool, billing=AsyncMock(), stream_format="agui",
            book_context={"book_id": book_id} if book_id else None,
        ):
            pass

    system_text = " ".join(
        (m["content"] if isinstance(m["content"], str)
         else " ".join(p["text"] for p in m["content"]))
        for m in loop_mock.call_args.kwargs["messages"] if m["role"] == "system"
    )
    return probe_spy.await_count, system_text


# ── the lever ─────────────────────────────────────────────────────────────────

class TestRailDriverEnabled:

    @pytest.mark.asyncio
    async def test_on_probes_the_book_and_grounds_the_rail(self):
        """The ON case is the load-bearing one: it proves the fixture REACHES the gate.

        Without this passing, every OFF assertion below is vacuous.
        """
        calls, text = await _run(enabled=True)
        assert calls == 1, (
            "the fixture did not reach the probe — one of the five preconditions is unmet, "
            "so the OFF tests below would pass for the wrong reason"
        )
        assert "vision-to-book" in text or "glossary_propose_entities" in text, (
            "the probe ran but its grounding never reached the prompt — the block is "
            "computed and thrown away, which is the 'stored but unread' bug shape"
        )

    @pytest.mark.asyncio
    async def test_off_never_probes_the_book(self):
        calls, _ = await _run(enabled=False)
        assert calls == 0, (
            "OFF must restore pre-Phase-2 behavior exactly: no book-state probe, hence no "
            "grounding block on an always-on system prompt"
        )

    @pytest.mark.asyncio
    async def test_off_drops_the_progress_grounding_from_the_prompt(self):
        """Proven by EFFECT on the artifact the lever exists to control — the prompt.

        The spy alone would still pass if a second, unflagged code path re-added the block.
        """
        _, on_text = await _run(enabled=True)
        _, off_text = await _run(enabled=False)
        assert len(off_text) < len(on_text), (
            "with the kill-switch OFF the system prompt must LOSE the progress grounding; "
            "an identical prompt means the flag gates the probe but not its output"
        )

    @pytest.mark.asyncio
    async def test_the_turn_still_completes_with_the_switch_off(self):
        # A kill-switch that breaks the turn is not a kill-switch. OFF is a revert path,
        # not a failure mode.
        _, text = await _run(enabled=False)
        assert text, "the turn produced no system prompt at all with the lever off"


# ── the OTHER preconditions still gate, independently of the flag ─────────────

class TestRailPreconditionsAreNotTheFlag:
    """Each of these would, on its own, produce "no probe" — which is exactly why the
    ON test above must exist. Pinning them here documents that a future failure to probe
    has more than one possible cause, and keeps the fixture honest about which it is."""

    @pytest.mark.asyncio
    async def test_no_book_context_means_no_probe_even_with_the_flag_on(self):
        calls, _ = await _run(enabled=True, book_id=None)
        assert calls == 0

    @pytest.mark.asyncio
    async def test_no_pinned_workflow_means_no_probe_even_with_the_flag_on(self):
        calls, _ = await _run(enabled=True, pinned=False)
        assert calls == 0

    @pytest.mark.asyncio
    async def test_a_caller_without_a_view_grant_is_never_probed(self):
        # The /review-impl HIGH this guard was written for: `_ctx_book_id` is
        # CLIENT-SUPPLIED and the probe fans out to routes that do not grant-check.
        # It must fail CLOSED.
        from app.client.grant_client import GrantLevel

        calls, _ = await _run(enabled=True, grant=GrantLevel.NONE)
        assert calls == 0, (
            "a caller with no grant reached the book-state probe — a client-supplied "
            "book_id would then read another tenant's state into the prompt"
        )
