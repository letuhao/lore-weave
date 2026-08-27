"""Streaming service — emits AI SDK data stream protocol v1 SSE lines.

Phase 1c-ii (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN): all LLM streaming flows
through provider-registry's `/internal/llm/stream` via the
`loreweave_llm` SDK. Direct provider-SDK calls (litellm, openai-python,
anthropic) are forbidden per CLAUDE.md gateway invariant.

Anthropic streaming temporarily emits LLM_STREAM_NOT_SUPPORTED until
the anthropic adapter Stream() impl ships (deferral
D-PHASE-1C-ANTHROPIC).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from contextvars import ContextVar
from collections import Counter
import logging
import re
import time as _time  # CP-0.3 — dispatch latency; was a function-local import in _emit_chat_turn
from dataclasses import dataclass
from typing import AsyncGenerator
from uuid import UUID, uuid4

import asyncpg
from json_repair import repair_json
from loreweave_llm import (
    Client,
    DoneEvent,
    LLMError,
    ReasoningEvent,
    StreamRequest,
    TokenEvent,
    ToolCallEvent,
    UsageEvent,
    infer_reasoning_control,
    no_thinking_fields,
    reasoning_fields,
    resolve_reasoning,
)

from app.client.auth_client import resolve_local_date
from app.client.billing_client import BillingClient
from app.client.knowledge_client import get_knowledge_client
from app.client.known_entities_client import get_known_entities_client
from app.services.canon_capture import CaptureContext, maybe_capture_canon, persist_capture_status
from app.services.context_autodetect import resolve_context_pressure
from app.services.entity_presence import EntityPresence, detect_entity_presence
from app.services.injection_defense import neutralize_injection
from app.services import instrument
from app.services.reasoning_loop_detector import ReasoningLoopDetector
from app.config import settings
from app.db.suspended_runs import (
    delete_suspended_run,
    load_suspended_run,
    save_suspended_run,
)
from app.db.tool_approvals import approve_tool, get_tool_decision, set_tool_decision
from app.db.message_sequence import next_sequence_num
from app.services.id_ledger import IdLedger
from app.services.request_mood import request_mood, standing_grant_applies
from app.db.conversation_search import (
    CONVERSATION_SEARCH_NAME,
    CONVERSATION_SEARCH_TOOL,
    run_conversation_search,
)
from app.db.session_search import (
    CHAT_SEARCH_SESSIONS_NAME,
    CHAT_SEARCH_SESSIONS_TOOL,
    run_chat_search_sessions,
)
from app.db.pool import get_pool
from app.db.session_blocks import project_story_state
from app.models import ProviderCredentials
from app.services.composer import build_composer_messages, is_composer_tool
from app.services.frontend_tools import (
    frontend_tool_def_by_name,
    generic_frontend_tool_def,
    is_browser_executed,
    is_frontend_tool,
    validate_frontend_tool_args,
)
from app.services.tool_surface import answerable_tools
from app.services.tool_discovery import (
    ALWAYS_ON_CORE_NAMES,
    FIND_TOOLS_DEFAULT_LIMIT,
    FIND_TOOLS_NAME,
    FIND_TOOLS_TOOL,
    TOOL_LIST_NAME,
    TOOL_LIST_TOOL,
    TOOL_LOAD_NAME,
    TOOL_LOAD_TOOL,
    declared_lane,
    find_tools_result_async,
    group_directory_text,
    hot_tool_names,
    provider_availability,
    strip_tool_meta,
    surface_hot_domains,
    tool_async,
    tool_list_result,
    tool_load_result,
    tool_paid,
    tool_tier,
    tool_undo_hint,
)
from app.services.workflow_runner import (
    WORKFLOW_LIST_NAME,
    WORKFLOW_LIST_TOOL,
    WORKFLOW_LOAD_NAME,
    WORKFLOW_LOAD_TOOL,
    workflow_list_result,
    workflow_load_result,
)
from app.services.skill_registry import (
    LOAD_SKILL_NAME,
    LOAD_SKILL_TOOL,
    load_skill_result,
)
from app.services.rail_progress import rail_gate_suppressions, user_abandoned_rail
from app.services.subagent_runtime import (
    RUN_SUBAGENT_NAME,
    SUBAGENT_MAX_ITERATIONS,
    SUBAGENT_RESULT_CHAR_CAP,
    build_run_subagent_tool,
    cap_result,
    clamp_permission_mode,
    resolve_scoped_tools,
    tool_name_of,
)
from app.services.output_extractor import extract_outputs
from app.services.stream_events import make_emitter
# T0 / L3 (Context Budget Law §6a, §14a) — the single concise-wire funnel for
# every model-facing tool-result `content` string (ensure_ascii=False + drop-None).
from app.services.tool_result_wire import (
    tool_result_content,
    tool_result_content_capped,
    tool_result_content_capped_ex,
)
from app.services.compaction import (
    compact_messages,
    inject_recovery_hint,
    summary_message,
)
from loreweave_context import (
    Planner,
    TraceAccumulator,
    build_system_message,
    compute_target,
)

# T3.2 — the default Context Budget Planner (stateless policy; one shared instance). Swap
# this (or subclass Planner) to A/B a compaction/budget optimization hypothesis.
_PLANNER = Planner()

# CONSUMER-LOCAL meta tools: dispatched inline here (never federated to a domain service),
# so the main dispatch's schema-aware wrap-repair below never reaches them. A mid-tier model
# (gemma) wraps the whole payload in a lone {"args": {...}} envelope; without repair these see
# intent=""/slug=""/name=None and no-op. None of them declares an `args`/`arguments` param, so
# unwrapping with tool_def=None (see the per-call loop) is safe for the whole set.
_CONSUMER_LOCAL_META_TOOLS = frozenset({
    FIND_TOOLS_NAME, TOOL_LIST_NAME, TOOL_LOAD_NAME,
    WORKFLOW_LIST_NAME, WORKFLOW_LOAD_NAME, RUN_SUBAGENT_NAME,
})
# W3 — compaction tier 2 (compress instead of drop) shares its summarizer with
# the manual /compact route; the factored impl lives in compact_service. Bound
# to the old private name so both in-file call sites stay unchanged.
from app.services.compact_service import (
    persist_auto_compact,
    summarize_for_compaction as _summarize_for_compaction,
)
from app.services.caching_monitor import build_caching_metrics, detect_thrashing
from app.services.stateful_chain import decide_chain
from app.services.token_budget import (
    ContextBreakdown,
    compute_budget,
    context_budget_event,
    derive_intent,
    derive_status_flags,
    estimate_messages_tokens,
    estimate_tokens,
    scale_by_window,
)
from app.services.working_memory import resolve_anchor

logger = logging.getLogger(__name__)


# M3 (chat disconnect-cancel) — DISCONNECT IS HANDLED BY THE CASCADE, NOT AN
# EXPLICIT DELETE. When the client/browser disconnects, GeneratorExit propagates
# into the gateway helper → its `finally: await client.aclose()` closes httpx →
# the gateway's r.Context() cancels → adapter.Stream returns → the gateway's
# (silent) FinalizeStreamStatus marks the observability row 'cancelled' + frees
# the GPU slot. We deliberately do NOT issue an explicit DELETE /internal/llm/jobs
# from here: that path (cancelLlmJob) emits a terminal event → notification-service
# would file a spurious "Chat cancelled" notification on EVERY user stop
# (/review-impl). The DELETE route still exists for callers that WANT that
# (an async chat job, an explicit admin cancel). Chat only needs to MINT + SEND
# stream_job_id so the row exists and the cascade can finalize it.


@dataclass
class _Usage:
    """Mirror the shape of openai's CompletionUsage so existing
    `getattr(last_usage, 'prompt_tokens', None)` call sites keep working
    after the SDK migration."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Prompt-cache split (Provider Context Strategy §7). Summed across a turn's
    # tool-loop iterations, same as prompt_tokens. 0 when the provider reported no
    # cache activity. Feeds the contextBudget `caching` monitoring section.
    cache_creation_tok: int = 0
    cache_read_tok: int = 0


_INLINE_EFFORT_RE = re.compile(
    r"(?:^|\s)/(?P<cmd>no_thinking|no_think|think|effort=(?P<val>none|off|low|medium|high))(?=\s|$)",
    re.IGNORECASE,
)


def parse_inline_effort(text: str) -> tuple[str, str | None]:
    """RE-3 — parse a CHAT-ONLY inline reasoning command from the message and strip
    it before the text reaches the model / is persisted. Returns (stripped, pref):

      /no_think · /no_thinking   → "off"
      /think                     → "medium"
      /effort=none|off|low|medium|high → that effort ("none"→"off")

    Anchored at a whitespace/edge boundary so a '/think' inside a word or code span
    isn't matched. The LAST command wins (sub scans left-to-right, overwriting pref).
    Inline command is the HIGHEST-precedence reasoning signal (> per-msg toggle >
    session > model-default > platform)."""
    if not text:
        return text, None
    pref: str | None = None

    def _sub(m: re.Match) -> str:
        nonlocal pref
        cmd = m.group("cmd").lower()
        if cmd in ("no_think", "no_thinking"):
            pref = "off"
        elif cmd == "think":
            pref = "medium"
        else:  # effort=<val>
            v = (m.group("val") or "").lower()
            pref = "off" if v == "none" else v
        return ""

    stripped = _INLINE_EFFORT_RE.sub(_sub, text).strip()
    return stripped, pref


# W4 — the input-bar effort dropdown's request vocabulary → UserReasoningPref.
# fast ≙ the old Fast pill (off), standard ≙ Think (medium), deep = high.
# This reuses the existing resolve_reasoning/reasoning_fields provider mapping
# (Anthropic adaptive → omit; effort models → reasoning_effort; local template
# models → chat_template_kwargs) — no new provider knob is invented here.
_REQUEST_EFFORT_TO_PREF: dict[str, str] = {
    # Legacy 3-level (kept for back-compat during the FE 5-level convergence).
    "fast": "off",
    "standard": "medium",
    "deep": "high",
    # Unified 5-level effort vocabulary (matches the session-stored default) —
    # identity into UserReasoningPref; resolve_reasoning maps auto→adaptive/omit.
    "off": "off",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "auto": "auto",
}


def _thinking_pref(
    thinking: bool | None,
    gen_params: dict,
    reasoning_effort: str | None = None,
) -> str:
    """Map the per-request reasoning signals (+ the session generation_params
    default) to a UserReasoningPref for resolve_reasoning.

    Precedence (highest first): per-msg `reasoning_effort`
    (fast|standard|deep — the W4 dropdown) > per-msg `thinking` toggle
    (True → "medium", False → "off") > session-stored
    `reasoning_effort`/`thinking` default > platform default "off"
    (RE-1: thinking is opt-in)."""
    if reasoning_effort in _REQUEST_EFFORT_TO_PREF:
        return _REQUEST_EFFORT_TO_PREF[reasoning_effort]
    if thinking is True:
        return "medium"
    if thinking is False:
        return "off"
    stored = gen_params.get("reasoning_effort", gen_params.get("thinking"))
    if isinstance(stored, str) and stored in ("off", "auto", "low", "medium", "high"):
        return stored
    if stored is True:
        return "medium"
    return "off"


def _resolve_and_stash_reasoning(
    gen_params: dict,
    creds: "ProviderCredentials | None",
    *,
    thinking: bool | None = None,
    reasoning_effort: str | None = None,
    inline_pref: str | None = None,
) -> None:
    """Resolve the reasoning pref → provider wire fields and stash them in
    gen_params (in place). MUST run on EVERY path that feeds gen_params into a
    StreamRequest — the session-stored `reasoning_effort` vocabulary
    (off|auto|low|medium|high) is NOT wire vocabulary (none|low|medium|high):
    forwarding it raw crashes StreamRequest validation (review-impl H: a
    session set to "off" 500'd every tool-approval RESUME) and bypasses the
    adaptive-model omit rule."""
    user_pref = inline_pref or _thinking_pref(thinking, gen_params, reasoning_effort)
    # creds=None (voice path — the gateway resolves the model internally):
    # control "none" keeps explicit prefs correct and makes "auto" omit.
    model_control = (
        infer_reasoning_control(creds.provider_kind, creds.provider_model_name)
        if creds is not None else "none"
    )
    directive = resolve_reasoning(
        user_pref=user_pref,  # type: ignore[arg-type]
        model_control=model_control,
    )
    rf = reasoning_fields(directive)
    # Clear any stale stored knobs first so a directive that says "omit"
    # (adaptive / non-reasoning) doesn't leave a session's raw value behind.
    gen_params.pop("reasoning_effort", None)
    gen_params.pop("chat_template_kwargs", None)
    if rf:
        gen_params.update(rf)


def _apply_reasoning_kwargs(request_kwargs: dict, gen_params: dict) -> None:
    """Forward the resolved reasoning fields (stashed in gen_params by
    stream_response) into the StreamRequest kwargs. THIS is the wiring that was
    missing — `_stream_via_gateway`/`_stream_with_tools` never forwarded
    reasoning, so the chat thinking toggle was a live no-op."""
    if gen_params.get("reasoning_effort") is not None:
        request_kwargs["reasoning_effort"] = gen_params["reasoning_effort"]
    if gen_params.get("chat_template_kwargs") is not None:
        request_kwargs["chat_template_kwargs"] = gen_params["chat_template_kwargs"]


async def _stream_via_gateway(
    model_source: str,
    model_ref: str,
    user_id: str,
    messages: list[dict],
    gen_params: dict,
) -> AsyncGenerator[dict, None]:
    """Stream via provider-registry `/internal/llm/stream` using the
    loreweave_llm SDK. Single replacement for the legacy
    `_stream_openai_compatible` and `_stream_litellm` helpers — gateway
    invariant restored.

    Yields dicts of the same shape consumers expected from the legacy
    helpers (`content` / `reasoning_content` / `finish_reason` / `usage`)
    so `stream_response` and `voice_stream_response` don't need
    restructuring.
    """
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
        idle_read_timeout_s=settings.llm_stream_idle_read_timeout_s,
    )
    try:
        max_tokens = gen_params.get("max_tokens")
        if max_tokens is not None and max_tokens <= 0:
            max_tokens = None
        # Build kwargs sparsely so None values don't override SDK schema
        # defaults (StreamRequest.temperature defaults to 0.0; passing
        # None fails pydantic validation).
        request_kwargs: dict = {
            "model_source": model_source,
            "model_ref": model_ref,
            "messages": messages,
        }
        if gen_params.get("temperature") is not None:
            request_kwargs["temperature"] = gen_params["temperature"]
        if gen_params.get("top_p") is not None:
            request_kwargs["top_p"] = gen_params["top_p"]
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
        # M3 — mint a job id so the gateway persists a billing-neutral
        # observability row for this stream + makes it cancellable on disconnect.
        stream_job_id = str(uuid4())
        request_kwargs["stream_job_id"] = stream_job_id
        _apply_reasoning_kwargs(request_kwargs, gen_params)
        request = StreamRequest(**request_kwargs)
        last_usage: _Usage | None = None
        finish_reason: str | None = None
        async for ev in client.stream(request):
            if isinstance(ev, TokenEvent):
                yield {
                    "content": ev.delta,
                    "reasoning_content": "",
                    "finish_reason": None,
                    "usage": None,
                }
            elif isinstance(ev, ReasoningEvent):
                yield {
                    "content": "",
                    "reasoning_content": ev.delta,
                    "finish_reason": None,
                    "usage": None,
                }
            elif isinstance(ev, UsageEvent):
                last_usage = _Usage(
                    prompt_tokens=ev.input_tokens,
                    completion_tokens=ev.output_tokens,
                    cache_creation_tok=ev.cache_creation_tok or 0,
                    cache_read_tok=ev.cache_read_tok or 0,
                )
            elif isinstance(ev, DoneEvent):
                finish_reason = ev.finish_reason
        # Trailing chunk so consumer's billing path picks up usage +
        # finish_reason exactly the way the legacy code did.
        yield {
            "content": "",
            "reasoning_content": "",
            "finish_reason": finish_reason or "stop",
            "usage": last_usage,
        }
    finally:
        # M3 — on disconnect, GeneratorExit unwinds through here; client.aclose
        # closes httpx → the gateway finalizes the observability row 'cancelled'
        # (the silent cascade — see the module note above; no spurious notify).
        await client.aclose()


# ── K21-B: tool-calling loop ────────────────────────────────────────────────

# Max LLM passes per chat turn. Passes 0..N-2 may call tools; the final
# pass is forced tool-free (tool_choice="none") so the loop always
# terminates with a text answer (design D7).
MAX_TOOL_ITERATIONS = 5
# DBT-CHAT-PERSIST — minimum wall-clock between in-turn assistant checkpoints.
# We checkpoint at tool boundaries (not per token) so a long tool-loop turn that
# errors/interrupts/abandons mid-way keeps its work; this throttle bounds the
# write count on a rapid tool loop (a burst of tool calls → at most one write
# per interval). The suspend checkpoint bypasses it (always writes).
_CHECKPOINT_MIN_INTERVAL_S = 1.5
# Glossary-assistant P5 (H11): book-scoped surfaces run a richer multi-step
# workflow (list_kinds → search → get_entity → propose ≈ 4 calls; multi-entity
# tasks need headroom), so the cap is raised there. Per-turn token budget still
# bounds cost. Plain chat keeps the default 5.
GLOSSARY_TOOL_ITERATIONS = 10
# MCP-fanout H9: the universal /chat surface runs multi-step cross-service goals
# (find_tools → read → write across services) so it gets the highest cap. CRUCIAL
# (H9): find_tools calls + Tier-R reads do NOT decrement this budget — only passes
# that actually execute a Tier-A/W write count — so discovery never starves the
# write budget. The forced-final tool-free pass still guarantees termination.
UNIVERSAL_TOOL_ITERATIONS = 20

# MCP-fanout H7: at most this many same-op Tier-A auto-writes per turn before the
# loop escalates to a single batch confirm_action (the enforceable
# injection-damage bound — see spec E2/H7).
TIER_A_SAME_OP_CAP = 5
# MCP-fanout H7 (aggregate): an additional turn-TOTAL ceiling across ALL Tier-A
# ops, so an alternating-op turn (e.g. book_create×5 + chapter_create×5) can't
# slip past the per-op cap and do an unbounded number of auto-writes. Chosen
# > the per-op cap (5) so a single legitimate op never trips the aggregate first,
# but low enough that a high-volume multi-op turn still hits ONE human gate.
TIER_A_AGGREGATE_CAP = 12

# #18 — mechanical planner hard-stop. The planner tool is a heavy (~39s) model call
# that mints a typed PLAN; there is NO ReAct loop in the planner CODE, so the
# "loops forever" is the chat agent re-calling it in a self-recheck cycle, bounded
# only by a SOFT skill rule. This is the mechanical form of that rule: the planner
# may run AT MOST this many times per turn; a further call is short-circuited (no
# execution) with a tool result steering the model to present/confirm the plan it
# already produced. Cross-turn recovery re-plans are a fresh pass (fresh counter),
# so legitimate re-planning after a confirmed plan's failures is never blocked.
PLANNER_TOOLS = frozenset({"glossary_plan"})
PLANNER_CALLS_PER_TURN_CAP = 1

# D-BLANK-TOOL-ARGS-LOOP — mechanical hard-stop for a repeated BLANK/missing-
# required-args tool call within one turn, in EITHER of its two observed
# shapes: (1) find_tools called with no `intent` (no `group`, so not the
# legitimate enumeration path) — `FindToolsAttemptTracker` (tool_discovery.py)
# deliberately never tracks this shape (an empty intent has no wording to
# detect as a near-duplicate of); (2) any generic backend tool call whose
# args fail the domain service's own required-property validation (the
# `validating "arguments": ... required: missing properties: [...]` error
# shape). Both are the EXACT signature of a known upstream LM Studio
# tool-call-parser bug (confirmed 2026-07-08 for both gemma-4-26b-a4b-qat and
# qwen3.6-35b-a3b — the model's structured tool-call channel emits
# `arguments: ""`/`{}` while its own free-text channel still works fine) —
# live-reproduced again post-fix on 2026-07-08 (session 019f4021-71eb...):
# the SAME turn tried `glossary_web_search` 3 times with blank args before
# giving up on its own. A real production session
# (019f4000-43ee-7201-9d45-e2fafc83696d) hit shape (1): 7 then 6 consecutive
# blank find_tools calls across two turns, each getting the identical
# unhelpful note, never escalating, bounded only by `max_total_passes` (15)
# — burning most of a turn's pass budget before the model finally gave up on
# its own. ONE shared counter across both shapes (not two independent ones):
# the real session mixed them — glossary_web_search blank x2 then find_tools
# blank x6 in the SAME turn — so only a shared streak catches that exact
# cross-tool flailing. This is a THIS-TURN, in-memory counter (not
# session-keyed like FindToolsAttemptTracker — a fresh turn gets a fresh
# budget of benign first-attempts) so it needs no new tracked state: the
# first BLANK_TOOL_ARGS_CAP blank/invalid calls still run/get today's
# behavior (a call or two probing the surface is normal); the next one is
# short-circuited with a directive to stop and tell the user, the same shape
# as the #18 planner hard-stop.
BLANK_TOOL_ARGS_CAP = 2

# Track C Phase 2 — how many times the same read may return the SAME RESULT before further
# identical calls are short-circuited.
#
# H7 caps runaway WRITES. Nothing capped a runaway READ, on the theory that a read is harmless.
# Measured live: gemma called `glossary_list_system_standards` 24 times in one S01 run — a
# 44,000-char result (~11k tokens) EACH — and built nothing. A read that eats a third of the
# context window is not harmless.
#
# It counts UNCHANGED RESULTS, not calls, and that distinction is the whole design. POLLING is
# a repeated identical read whose result is SUPPOSED to change: `jobs_get`,
# `translation_job_status` and `composition_get_generation_job` are all Tier-R, and the workflow
# rails explicitly depend on watching an async job to completion ("do NOT begin a dependent step
# until it has finished"). A breaker that counted CALLS would have blocked the second poll and
# stranded every async step in the catalogue. So a poll that returns "still running" → "done"
# never trips this; only a read that keeps handing back the byte-identical answer does.
REPEAT_READ_CAP = 2
# ...and once it fires, SHORT-CIRCUITING THE DISPATCH IS NOT ENOUGH. Measured across the whole
# corpus, with tool_list's separate F18 breaker excluded so the denominator is this breaker's own:
# 598 calls blocked, across 40 sessions and 10 tools — and ALL 598 report "3 times", not one says
# 4, because the count came from the DISPATCH ledger a blocked call never advances. One real
# product turn ("The Tidewright", 2026-07-21) emitted 194 blocked `book_get` calls over 35
# iterations, every one of them claiming it was the 3rd. The model reads "STOP calling it" and calls it again, which is the exact failure the
# repeated-FAILURE breaker already answered by taking the tool OFF THE WIRE, and the exact failure
# F18 records for tool_list ("returning an ERROR framed the repeat as a failure the model 'fixes'
# by retrying HARDER, 28→311 calls"). This breaker was the one that never got the escalation its
# own comment claimed it had. After this many BLOCKED repeats the tool is de-advertised for the
# rest of the turn — the steer gets two chances first, because a model that listens listens early.
REPEAT_READ_DEADVERTISE_CAP = 2

# Idempotent-no-op WRITE breaker cap — how many times a Tier-A write may return a
# `created: False` (made-nothing) result for the SAME (tool, args) before a further
# identical call is short-circuited. 1 = the first call is legitimate (the model learns
# the resource exists and gets its id); the 2nd identical no-op call is the loop and is
# steered forward. Deliberately far tighter than TIER_A_SAME_OP_CAP (5) — that cap is a
# generic runaway-write bound that ends in a human confirm card; this fires 4 calls
# earlier because a repeated NO-OP needs no human gate, just a "you already have it, move
# on" nudge. Only `created is False` trips it, so a real creation (`created: True`) is
# never blocked, and a create with DIFFERENT args (a different resource) has a different
# key and is untouched.
IDEMPOTENT_NOOP_WRITE_CAP = 1

# Repeated-identical-FAILURE breaker cap (2026-07-26) — the mirror of the no-op-write breaker
# above. That one catches a SUCCESSFUL write that changed nothing; this catches a call that
# keeps FAILING with the same error for the SAME (tool, args) — a weak model blind-retrying a
# call it cannot fix (measured live: book_get_chapter ×13 on "no active chapter with that
# chapter_id"; book_update_details ×16 on "no fields to update"). A failed call with FIXED args
# is legitimate (its answer never reached the context — see the read-breaker note below), so the
# key is (tool, EXACT args): only an IDENTICAL repeat is the loop; a retry with different args
# gets a fresh key and runs. After the cap, the next identical call is short-circuited with the
# tool's OWN error text echoed back (it usually names the fix, e.g. "call book_list kind=chapters")
# so the model RECOVERS or stops honestly instead of spinning. Applies to reads AND writes.
REPEATED_FAILURE_CAP = 2   # 2 identical failures tolerated; the 3rd+ identical call is steered

# Completed one-shot CREATE tools → the context-id key whose PRESENCE proves the tool's
# target already exists (so the tool is done and re-advertising it only invites a loop).
# kg_project_create stands up a book's KG/composition project; the FE hoist puts that
# project_id into studio_context, so `project_id` present ⇒ the project exists. Used by the
# `oneshot_deadvertise_mode` = "existence" gate; the reactive modes key on the tool's own
# `created:false` result instead. A small explicit registry (not a heuristic) so only
# genuinely-idempotent one-shot setup tools are ever suppressed.
ONESHOT_CREATE_TOOLS: dict[str, str] = {"kg_project_create": "project_id"}

# ── F18: the tool_list loop breaker (dogfood round-4) ────────────────────────
# `tool_list` returns the COMPLETE category in one shot (no cursor/paging), so a
# re-list of a category the model already listed is provably a loop — the answer is
# already in context. Unlike a generic Tier-R read (bounded by the repeated-read
# breaker above), tool_list is dispatched EARLIER in the tool loop and returned ok=True
# UNCONDITIONALLY, so nothing bounded it: a weak model (gemma) called it 28× in one turn
# and built nothing. Two reverted fixes proved the breaker's usual lever BACKFIRES here —
# returning an ERROR framed the repeat as a failure the model "fixes" by retrying HARDER
# (28→311 calls), and charging budget to force finalization made it HALLUCINATE a
# tool-call as text. So this breaker does neither: on a repeat it AUTO-LOADS the
# category's tools (the real tools the model was circling become callable) and STEERS it
# to use them — forward progress, never a forced stop. Past a per-turn total, tool_list
# is also dropped from the advertised set (tool_load stays, so a specific tool is still
# reachable by name).
TOOL_LIST_CATEGORY_CAP = 1   # 1 legit list per category; the 2nd (same category) is the loop
TOOL_LIST_TOTAL_CAP = 5      # total tool_list calls this turn before it is de-advertised


# ── T7-D1: `include_deprecated` must default the way the model was TOLD it defaults ──
# `tool_list` is dispatched CONSUMER-LOCALLY, right here — the ai-gateway's `handleToolList`
# never runs for a chat turn. Both advertised copies of the schema say `default: false`, with
# prose the model reads directly: "omit to see only the CURRENT tools; set true only when
# migrating off an old tool name." This dispatch defaulted it to True, so omitting the arg
# returned the opposite of the contract.
#
# Measured live 2026-08-13, session 019ff9c5: the model omitted the arg and got 307 tools of
# which 116 were DEPRECATED - 38% of the primary discovery surface was the shrunk-away legacy
# catalog (`book_get` -> `book_read`, `composition_arc_create` -> `composition_arc_edit`, ...),
# handed to a weak model as "the complete list".
#
# This is K22 inverted. K22 found the advertised default (True) disagreeing with the handler
# and corrected the ADVERTISEMENT to False - but pointed its regression guard at ai-gateway's
# handler, so the half that actually executes kept its True and nothing went red for three
# weeks.
#
# A non-boolean is coerced rather than silently dropped: with the default now False, dropping a
# string "true" would re-create the same lie in the other direction, and that string is exactly
# what the one caller the prose invites - an agent migrating off an old tool name - is most
# likely to send.
def _tool_list_include_deprecated(args_obj: dict) -> bool:
    """The wire default for `tool_list(include_deprecated=...)`: FALSE, per the advertised schema."""
    raw = args_obj.get("include_deprecated")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return False

# ── D-REASONING-LOOP: the streaming reasoning-channel loop breaker ────────────
# Every breaker above fires in the TOOL-CALL loop, on an EMITTED call. A model
# that thrashes in the *reasoning stream* WITHOUT emitting a call (live incident:
# gemma oscillating book_update_details⇄propose_record_edit 30+ times on a "rewrite
# the description" ask, zero tool calls, hung until the user hit Stop) trips none
# of them. ReasoningLoopDetector watches the streamed text itself; on a trip we
# abort the pass, inject a steer directive, force reasoning off for the retry,
# and cap the interventions so a persistent loop ends HONESTLY, never a hang.
REASONING_LOOP_INTERVENTION_CAP = 2

# D-SILENT-TURN-NO-CARD-NO-PROSE — the SAME shape as the loop above, degenerate in ONE pass
# rather than across several, which is why ReasoningLoopDetector never trips on it: the model
# emits reasoning-channel content and no call and no prose. Measured, that content is exactly
# 12 characters, the literal `<tool_call|>`, and the correlation is clean — every turn producing
# PROSE has reasoning_length 0; every silent finish_reason='stop' turn has reasoning_length 12.
# So the remedy already chosen above (abort, steer, reasoning OFF for the retry, capped) targets
# exactly this turn's correlate. ONE intervention, not two: a second degenerate pass in the same
# turn is evidence the retry is not working, and the honest end is to stop rather than churn.
DEGENERATE_PASS_INTERVENTION_CAP = 1

# P-1 step-runner — the per-turn cap on how many times the server re-drives the rail after the
# model stops. The vision-to-book rail is 11 steps and a few are already done on the assent
# turn, so ~8 covers a full drive-through; a per-STEP cap of 2 (rail_twice_nudged) bounds a
# model that ignores a given nudge. Together they guarantee an HONEST stop, never a loop.
RAIL_REDRIVE_CAP = 8


async def _compute_rail_drive_context(
    pool, user_id: str, book_id: str, permission_mode: str, session_id: str, knowledge_client,
):
    """Fetch the pinned workflows + grant + turn-start counts + async set for a book, so the
    RESUME path can keep DRIVING the rail past a confirm suspend (the fresh path computes this
    inline). Returns ``(rail_specs, grant_ok, turn_start_counts, async_tools, rail_progress)`` or
    the inert ``([], False, None, frozenset(), [])`` on any failure — the resume then simply does
    not drive. ``rail_progress`` (turn-start RailProgress objects, parallel to rail_specs) feeds
    the advertise chokepoint's action-space gating; empty ⇒ gating inert on resume.
    """
    try:
        from app.client.grant_client import GrantLevel, get_grant_client
        from app.client.registry_workflows_client import get_workflows_client
        from app.db.tool_call_history import succeeded_tool_counts
        from app.services.book_state_probe import probe_book_state
        from app.services.rail_progress import compute_rail_progress

        wfs = await get_workflows_client().get_workflows(
            str(user_id), book_id=str(book_id), surface="book", mode=permission_mode,
        )
        binding = wfs.mode_binding
        if not (binding and binding.inject_workflows):
            return [], False, None, frozenset(), []
        visible = {w.get("slug") for w in wfs.workflows if w.get("slug")}
        pinned = [s for s in binding.inject_workflows if s in visible]
        if not pinned:
            return [], False, None, frozenset(), []
        lvl, _ = await get_grant_client().resolve_access(UUID(str(book_id)), UUID(str(user_id)))
        if lvl < GrantLevel.VIEW:
            return [], False, None, frozenset(), []
        counts = await succeeded_tool_counts(pool, str(session_id))
        catalog = await knowledge_client.get_tool_definitions(user_id=user_id)
        async_tools = frozenset(
            n for n, td in _catalog_index(catalog).items() if tool_async(td)
        ) if catalog else frozenset()
        rail_specs = []
        for slug in pinned:
            wf = next((w for w in wfs.workflows if w.get("slug") == slug), None)
            steps = wf.get("steps") if isinstance(wf, dict) else None
            if isinstance(steps, list) and steps:
                rail_specs.append((slug, steps))
        # Turn-start progress for action-space gating on resume — best-effort; a probe failure
        # leaves progress empty (gating inert) but the rail still drives on counts.
        rail_progress: list = []
        try:
            _bstate = await probe_book_state(str(book_id), str(user_id))
            for slug, steps in rail_specs:
                rail_progress.append(compute_rail_progress(slug, steps, _bstate, counts))
        except Exception:  # noqa: BLE001 — gating is never load-bearing
            rail_progress = []
        return rail_specs, True, counts, async_tools, rail_progress
    except Exception:  # noqa: BLE001 — the driver is never load-bearing
        logger.warning("resume rail-drive context failed — rail not driven on resume", exc_info=True)
        return [], False, None, frozenset(), []


# ACP A2 (RW-3): `_maybe_redrive_rail` (the fresh-probe drive selector) + the inline enforcement
# block moved to the SDK harness `loreweave_agent_control.decide_rail_drive`, which unifies them
# into one verdict. The stream loop calls it with `probe_book_state` INJECTED and owns the loop
# mechanics (see the drive site below). One home for the drive decision — no duplicated selector.


class _ProbeAccessDenied(Exception):
    """The caller has no grant on the pinned rail's book — skip the book-state probe and run
    the rail ungrounded. A sentinel, so the caller distinguishes 'no access' (expected, quiet)
    from a real probe error (logged)."""

# The stable substring across every live-observed instance of this error
# (from the domain service's own JSON-schema validator) — a required
# property (e.g. `query`, `intent`) is missing from the call's arguments.
# Deliberately narrow (not "any tool error") so a tool that fails for a
# real, unrelated reason (auth, not-found, business-rule) never counts
# toward this streak.
_MISSING_REQUIRED_ARGS_MARKER = "required: missing properties"

#: CP-5.4 · the two frontend-validation refusals kept APART, because they are different defects
#: with different fixes. This matches the message `validate_frontend_tool_args` emits for an id
#: field that failed its UUID pattern.
#:
#: 🔴 **NAMED FOR WHAT THIS SITE CAN ACTUALLY KNOW.** It knows one thing: an id-shaped argument is
#: not a UUID, so it did not come from a read. It CANNOT distinguish an invented placeholder from a
#: human NAME the resolver could have substituted — and calling the kind `invented_identifier`
#: would assert the difference rather than observe it. Measured over all 94 non-UUID `entity_id`
#: values in the corpus: **91 contain "placeholder", 3 are `"0"`, and ZERO are names** — so on
#: today's data every one is genuinely unobtainable, and binding CP-5.3's resolver to this tool
#: would have repaired **none** of them. That is why this row types the outcome rather than
#: reaching for resolution.
_UNRESOLVED_ID_RE = re.compile(r"must be a real UUID")

# D-CONFIRM-CARD-NUDGE (dogfood 2026-07-21) — a Tier-W/S propose tool returns a
# SERVER-BUILT confirm card ({confirm_token, descriptor, …}); the FE renders it with
# Confirm/Cancel and the human confirms via the domain endpoint — the model does NOT
# need to do anything more. But a weak model (Gemma) reads the raw token blob as the
# tool result, does not grasp it is PENDING THE HUMAN, and either re-calls the propose
# tool (the observed double-card) or apologizes for a non-existent error. This note is
# appended to the confirm-card tool result so the model writes one short "ready to
# confirm" line and stops. (A prompt guard-line alone has failed weak-model QC before —
# so if this does not hold live, the deterministic follow-up is to also stop advertising
# the just-fired propose tool on the immediately-following pass.)
_CONFIRM_CARD_STOP_NOTE = (
    "\n\n[SYSTEM — CONFIRMATION PENDING: A confirmation card for this change is now shown "
    "to the user with the exact edit, awaiting their approval. Nothing is saved until they "
    "click Confirm. This action is COMPLETE on your side. Do NOT call this tool again, do "
    "NOT call confirm_action yourself, and do NOT say an error occurred. Reply with ONE "
    "short sentence telling the user the change is ready for them to confirm, then stop.]"
)


def _is_confirm_card_result(payload) -> bool:
    """A Tier-W/S propose result that minted a server-built confirm card (has a
    confirm_token + descriptor). Domain-agnostic — matches book/glossary/… alike."""
    return (
        isinstance(payload, dict)
        and bool(payload.get("confirm_token"))
        and bool(payload.get("descriptor"))
    )

# RAID Wave B2 (07S §5b) — PLAN mode. The executable server surface is the ASK
# surface (tier R + find_tools + frontend tools) PLUS the PlanForge planning
# tools, identified by this name prefix (they write plan artifacts — reversible
# plan_runs rows — never prose). The prefix is the M4 federation contract:
# every composition planning tool is `plan_*` through ai-gateway.
PLAN_TOOL_PREFIX = "plan_"

# The plan-mode system nudge — a small static block appended on BOTH system-part
# assembly paths (mirrors skill_metadata_block) so any model in plan mode knows
# the contract: research + plan, never draft prose.
PLAN_MODE_NUDGE = (
    "## Plan mode\n"
    "You are in PLAN mode: research the book with read-only tools and "
    "build/refine the plan via the `plan_*` tools. Do NOT write prose — no "
    "drafting, no chapter text, no manuscript edits. When the user approves "
    "the plan, tell them to switch to Write mode to draft."
)

# Ask mode had no equivalent nudge — a model only discovered the read-only
# restriction reactively, from a rejected tool-call error, instead of upfront the
# way plan mode explains itself. Mirrors PLAN_MODE_NUDGE's shape/placement.
ASK_MODE_NUDGE = (
    "## Ask mode\n"
    "You are in ASK (research) mode: only read-only tools run here. Investigate "
    "and answer freely, but do NOT attempt to create, edit, publish, delete, or "
    "start any job — those calls will be rejected. If the user wants a change "
    "made, tell them to switch to Write mode (or Plan mode to draft a plan first)."
)


def _is_plan_tool(name: str) -> bool:
    """A PlanForge planning tool (allowed in PLAN mode on top of the R surface)."""
    return name.startswith(PLAN_TOOL_PREFIX)


def resolve_grounding_target(
    session_row, project_id: str | None,
) -> tuple[str | None, list[str] | None]:
    """Track B B1(2) — resolve the effective ``(project_id, project_ids)`` for a
    context build from the session's multi-KG grounding set.

    A session may ground on a SET of knowledge projects (world + member books):
      * ≥2 ids → the multi-project union. Returns ``(None, [ids…])`` — we send
        NO single project_id because knowledge-service's salience write-back keys
        on ``req.project_id``; attributing the multi-union's surfaced entities to
        any single project would misattribute them. Per-project multi salience
        write-back is tracked as D-MULTI-SALIENCE-WRITEBACK.
      * exactly 1 id → a set of one is just the single-project path; returns
        ``(that_id, None)`` so single-project salience still learns.
      * 0 ids → the legacy single ``project_id`` column, unchanged:
        ``(project_id, None)``.

    ``project_id`` is the already-resolved legacy single value (str | None).
    """
    ids = [str(p) for p in (session_row.get("project_ids") or [])] if session_row else []
    if len(ids) >= 2:
        return None, ids
    if len(ids) == 1:
        return ids[0], None
    return (str(project_id) if project_id else None), None


def _is_tools_unsupported(exc: LLMError) -> bool:
    """True when an LLMError is the gateway's 'this provider does not
    support tools' rejection — the K21.11 / design-D8 capability
    fallback. Robust to whether the SDK exposes a `.code` attribute."""
    code = getattr(exc, "code", "") or ""
    return "TOOLS_NOT_SUPPORTED" in code or "TOOLS_NOT_SUPPORTED" in str(exc)


# D-TOOLCALL-GEMMA-TOKEN-LEAK — some local models (confirmed: Gemma 4 GGUFs via
# LM Studio/llama.cpp, e.g. google/gemma-4-26b-a4b-qat — see llama.cpp#21316/
# #21680/#22786) emit tool-call arguments wrapped in the model's own native
# tokens instead of standard JSON, e.g. `<|tool_call>call:NAME{query:<|"|>text
# <|"|>}<tool_call|>` — `<|"|>` stands in for a literal `"`, and object keys are
# left unquoted. This is a known upstream llama.cpp/LM-Studio template-parsing
# gap (the C++ server's PEG-grammar fix, llama.cpp PR #21326, has known
# residual cases and isn't universally deployed) — not something a system
# prompt can override, since it's produced by grammar-constrained sampling
# below the level a prompt can reach (confirmed by live A/B test: identical
# malformed output at both "high" and "low" reasoning_effort, and with an
# explicit "use standard JSON quotes" system-prompt instruction).
_GEMMA_TOOLCALL_WRAP_RE = re.compile(r"^\s*<\|tool_call>\s*call\s*:\s*[\w.-]+\s*", re.IGNORECASE)
_GEMMA_TOOLCALL_TAIL_RE = re.compile(r"\s*<tool_call\|>\s*$", re.IGNORECASE)
_GEMMA_QUOTE_TOKEN_RE = re.compile(r"<\|[\"']\|>")
_UNQUOTED_KEY_RE = re.compile(r'(?<=[{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:')

# D-TOOLCALL-GEMMA-INTERIOR-LEAK — ANY of this model family's native control tokens.
# The wrapper strippers above are anchored (`^` / `$`), so they only ever remove ONE
# leading and ONE trailing marker. A marker in the MIDDLE of an args string survives —
# which is the whole bug: see `_split_interior_leaked_tool_calls`.
_LEAK_MARKER_ANY_RE = re.compile(
    r"<\|tool_call>|<tool_call\|>|<\|channel>|<channel\|>", re.IGNORECASE,
)
# A leaked call HEAD inside an args string: `<|tool_call>call:NAME` followed by its `{…}` body.
_LEAK_CALL_HEAD_RE = re.compile(
    r"<\|tool_call>\s*call\s*:\s*([\w.-]+)\s*(?=\{)", re.IGNORECASE,
)


def _has_leak_marker(text: str) -> bool:
    return bool(_LEAK_MARKER_ANY_RE.search(text))


def _is_bare_toolcall_marker_only(text: str, reasoning: str) -> bool:
    """D-SILENT-TURN-NO-CARD-NO-PROSE — is this pass's ENTIRE output one or more
    bare tool-call control tokens and nothing else?

    Every silent `finish_reason='stop'` turn in the recorded population carries
    exactly 12 characters of reasoning, and that content is `<tool_call|>` — the
    closing delimiter, arriving alone. The model abandoned the structured channel
    the way D-TOOLCALL-GEMMA-TOKEN-LEAK describes, but emitted no call to salvage:
    `_extract_leaked_tool_calls` returns [], the pass is treated as "the model
    stopped without a tool call", and the turn ends with nothing for the author.

    The two channels are read TOGETHER because which one the token lands in is not
    a property of the failure — `_split_safe_emit` holds back only the OPENING
    token `<|tool_call>`, so a leaked closing delimiter flushes straight through to
    whichever channel was open.

    PRECISION IS THE HALF THAT MATTERS. Firing on a pass that genuinely said
    something would convert working turns into failures, which is a worse defect
    than the one this names. So it requires BOTH that a marker was present and
    that removing every marker leaves nothing but whitespace: prose carrying a
    marker keeps its prose and is not degenerate, and a pass that is simply empty
    never leaked anything and is a different failure that must not be counted
    under this one."""
    joined = "\n".join((text or "", reasoning or ""))
    if not _LEAK_MARKER_ANY_RE.search(joined):
        return False
    return not _LEAK_MARKER_ANY_RE.sub("", joined).strip()


def _degemmify_tool_args(raw: str) -> str:
    """Strip Gemma 4's native tool-call wrapper/quote tokens, and quote bare
    object keys, so the result is plausible JSON worth a `json.loads` retry.
    A no-op (returns `raw` unchanged) when none of the tokens are present."""
    text = _GEMMA_TOOLCALL_TAIL_RE.sub("", _GEMMA_TOOLCALL_WRAP_RE.sub("", raw))
    text = _GEMMA_QUOTE_TOKEN_RE.sub('"', text)
    return _UNQUOTED_KEY_RE.sub(r' "\1":', text)


def _split_interior_leaked_tool_calls(calls: list[dict]) -> list[dict]:
    """D-TOOLCALL-GEMMA-INTERIOR-LEAK — recover the calls this model concatenated
    INTO one args string, instead of letting the repair layer swallow them.

    Third manifestation in the same defective-decoding family (after
    D-TOOLCALL-GEMMA-TOKEN-LEAK and D-TOOLCALL-DUP-EMPTY-CALL): the model emits
    several tool calls back-to-back in ONE `arguments` payload, separated by its
    own native control tokens, e.g.

        {ops:[…]}<tool_call|><|channel>thought<channel|><|tool_call>call:glossary_propose_entities{items:[…]}

    Because `_degemmify_tool_args` is anchored, the INTERIOR markers survive, and
    `repair_json` then produces **parseable but wrong** JSON — it glues the marker
    text into whatever value it landed next to. Pulled from a live transcript
    (session 019faf5b, seq 16), the model's second, CORRECT call ended up as an
    enum value:

        "type": "create_kinds\\"}]}<tool_call|>…<|tool_call>call:glossary_propose_entities{items:[{description:"

    which the tool rejected as `enum: … does not equal any of [create_kinds …]`.
    So the model was told it sent a bad enum it never wrote, while the call it
    actually wanted was destroyed. It cannot act on that feedback: the turn
    degraded into 10,882 characters of repeated prose until the author hit Stop.

    This splits instead of swallowing: everything before the first interior marker
    stays with the original call, and each `<|tool_call>call:NAME{…}` after it
    becomes its own call. A body runs to the next marker, or to end-of-string when
    the model's output was cut off mid-call (the live case) — a truncated tail
    still parses far enough for the schema to give an HONEST error about the real
    tool. No markers → returns `calls` unchanged, so a well-behaved provider is
    untouched."""
    out: list[dict] = []
    split_from: list[str] = []
    dropped: list[str] = []
    for c in calls:
        raw = c.get("arguments") or ""
        m = _LEAK_MARKER_ANY_RE.search(raw)
        if not m:
            out.append(c)
            continue
        head, tail = raw[:m.start()], raw[m.start():]
        recovered: list[dict] = []
        for hm in _LEAK_CALL_HEAD_RE.finditer(tail):
            nxt = _LEAK_MARKER_ANY_RE.search(tail, hm.end())
            body = tail[hm.end():nxt.start() if nxt else len(tail)]
            recovered.append({
                "id": f"interior-{uuid4()}", "name": hm.group(1), "arguments": body,
            })
            split_from.append(f"{c['name']}→{hm.group(1)}")
        # A BLANK head means the marker was the very first thing the model emitted, so
        # this entry never had arguments of its own. Two different situations, and
        # conflating them re-introduces the silent no-op this whole fix is about:
        #   • we recovered real calls from the tail → the model's intent is fully carried
        #     by those; DROP the empty shell (same contract as the sibling dedupe helpers:
        #     a dropped call never reaches `working`, so the provider is never left
        #     waiting on a result for it);
        #   • we recovered nothing → there is no intent to act on. Keep the args EXACTLY
        #     as they arrived, marker included, so the dispatch guard reports an honest
        #     "your args were corrupted" instead of quietly dispatching `{}` and letting
        #     the tool answer with a misleading "missing required field".
        if not head.strip():
            if recovered:
                dropped.append(c["name"])
            else:
                out.append(c)  # marker intact on purpose — the dispatch guard owns it
        else:
            c["arguments"] = head
            out.append(c)
        out.extend(recovered)
    if split_from or dropped:
        logger.warning(
            "D-TOOLCALL-GEMMA-INTERIOR-LEAK: recovered %d tool call(s) concatenated into "
            "another call's arguments (would otherwise have been swallowed into a value by "
            "json repair): %s%s", len(split_from), split_from,
            f"; dropped {dropped} (marker-only, no args of their own)" if dropped else "",
        )
    return out


_LEAK_MARKER_START = "<|tool_call>"


def _split_safe_emit(buffer: str) -> tuple[str, str]:
    """Split `buffer` into `(flush_now, hold_back)`. `hold_back` starts at the
    earliest position that could be the beginning of the Gemma leak marker
    `_LEAK_MARKER_START` — an exact occurrence, or a partial match at the
    buffer's tail (the marker may still be arriving one token at a time) — so
    a marker split across many small deltas is never partially streamed to the
    client before we know whether it's real prose or a leak. No such position
    → hold nothing, flush everything."""
    pos = buffer.find(_LEAK_MARKER_START)
    if pos != -1:
        return buffer[:pos], buffer[pos:]
    for k in range(min(len(buffer), len(_LEAK_MARKER_START) - 1), 0, -1):
        if buffer[-k:] == _LEAK_MARKER_START[:k]:
            return buffer[:-k], buffer[-k:]
    return buffer, ""


_GEMMA_LEAKED_CALL_RE = re.compile(
    r"<\|tool_call>\s*call\s*:\s*([\w.-]+)\s*(\{.*?\})\s*<tool_call\|>",
    re.IGNORECASE | re.DOTALL,
)


def _extract_leaked_tool_calls(text: str) -> list[tuple[str, str]]:
    """D-TOOLCALL-GEMMA-TOKEN-LEAK cross-channel salvage: when this model
    abandons the structured tool_calls channel entirely and dumps its native
    tool-call tokens into plain content/reasoning text instead (confirmed
    live + llama.cpp#22786 "tool call returned as content"), this recovers
    `(name, raw_args_body)` pairs from that leaked text — `raw_args_body`
    still has the Gemma quote-token mangling and is fed to `_parse_tool_args`
    downstream unchanged, which already knows how to repair it."""
    return [(m.group(1), m.group(2)) for m in _GEMMA_LEAKED_CALL_RE.finditer(text)]


# D-NARRATED-WRITE — one nudge per turn. This guard exists to stop a model talking
# itself out of acting; a cap above 1 would let it become the very loop it prevents.
NARRATED_WRITE_NUDGE_CAP = 1

# A snake_case identifier in prose. Deliberately loose — the CATALOG does the real
# filtering (only a token that IS a registered tool name survives), so this never needs a
# hand-maintained prefix list that would silently rot as domains are added.
_SNAKE_IDENT_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def _narrated_uncalled_writes(
    text: str, *, catalog_index: dict, attempted: set[str],
) -> list[str]:
    """Write tools NAMED in the model's prose that this turn never ATTEMPTED.

    The signal for the "claimed a write it never made" failure — see the call site for
    the live transcript. Three conditions, all mechanical:

    * the token is a REAL tool in this turn's catalog (not a plausible-looking invention —
      an invented name is a different bug with its own honest message at the dispatch
      chokepoint, and must not be confused with this one);
    * its tier is a WRITE (A/W/S). A read named-but-not-called is a DIFFERENT failure with a
      different remedy, and it is NOT harmless — this docstring used to say it was ("nothing
      was claimed to have changed, so there is nothing for the author to go and not find"),
      and DQ-T30 measured the harm directly: the store is untouched and the ANSWER is false.
      It is handled by `_unanswered_data_question_reads` below, keyed on the request rather
      than on the prose;
    * it is absent from `attempted` — successes AND failures both count as attempted,
      because a model that TRIED and got a real error already has honest feedback to
      report, and nudging it there would just be noise.
    """
    named = set(_SNAKE_IDENT_RE.findall(text or ""))
    return sorted(
        nm for nm in named & set(catalog_index)
        if nm not in attempted and tool_tier(catalog_index[nm]) in ("A", "W", "S")
    )


# DQ-T30 — one nudge per turn, for exactly the reason the write twin above is capped at one:
# a guard that exists to stop a model answering without looking must never itself become the
# loop it prevents.
DATA_QUESTION_NUDGE_CAP = 1


def _unanswered_data_question_reads(
    request_text: str | None, *, catalog_index: dict, attempted: set[str],
) -> list[str]:
    """The READ tools whose OWN declared vocabulary answers THIS request, when the turn called
    NONE of them — i.e. the model is about to answer a data question from conversation memory.

    🔴 THE READ-SIDE TWIN OF D-NARRATED-WRITE, AND THE HARM IS THE ANSWER RATHER THAN THE STORE.
    `_narrated_uncalled_writes` catches "claimed a write it never made". This catches "stated the
    data without reading it". The store is untouched, so every write-side guard is silent by
    construction — and the author is told something false about their own book.

    MEASURED 2026-08-13 (session 019ff929, book 019ff8f5), with TWO active canon_rule rows in the
    store. Turn A, rail-driven: the tool ran, the answer was right. Turn B, the rail now complete
    and correctly not driving: ZERO tool calls, answered *"one rule"* — the count from the earlier
    turn. Turn C, told a rule had been added: ZERO tool calls, claimed *"I have checked your
    consistency rules again"*, and INVENTED a plausible second rule paraphrased out of the chapter
    prose. Conversation memory went stale the moment the store changed outside the chat, and
    nothing was accountable for re-reading it.

    Owner's decision on DQ-T30, 2026-08-14: option (c) — **a question naming stored data must be
    answered from a tool call in THIS turn, independent of any rail.** So this guard deliberately
    takes NO rail input. The two rail-scoped options were rejected precisely because a completed
    rail is the case that fails: it is right for a finished rail to stop driving, and wrong for
    the turn to stop reading.

    Mechanical, with no NLP and no tense-guessing — the four conditions are:

    * the request matches the tool's OWN declared synonyms (`answerable_tools`, the same signal
      R1 already trusts to decide the surface). The platform's machine-readable statement that
      this request names stored data; never a keyword list maintained here, which would rot as
      domains are added;
    * the tool's tier is READ. A write matched by the same words is the sister guard's business,
      and nudging a write from a question would be this loop's own worst defect;
    * NONE of those reads is in `attempted` — successes AND failures both count, exactly as the
      sister guard counts them: a model that TRIED and got a real error already has honest
      feedback, and one that read ANY of the answering tools has satisfied (c);
    🔴 THIS DELIBERATELY DOES NOT REQUIRE THE TOOL TO BE ON THE WIRE, AND THE FIRST VERSION DID.
    MEASURED 2026-08-14 on the fixture this docstring describes: turn 1 called
    `composition_list_canon_rules` and answered correctly; the RE-ASK did not, and
    `advertised_tools` for that turn shows the tool was NOT advertised — so the guard fired, told
    the model to call a tool that was not on its surface, and the model took the honest-disclosure
    branch instead ("I did not re-read the book on this turn, so my answer may be stale") while
    thrashing through twelve OTHER composition tools hunting for it.

    That is the same lesson the sister guard already carries in its own words — *"a directive to
    'call it now' is empty if the tool is not on the wire, and OFF-SURFACE is the usual reason the
    model narrated instead of calling in the first place"* — so the CALL SITE arms what it names,
    exactly as the sister guard does. Requiring the tool to be pre-surfaced made the guard silent
    in precisely the case it exists for.

    An answerable read that is withheld is STILL a surfacing defect with its own row (R1's job,
    and the v1/v2 incidents). Arming is a repair at the answer boundary, not a substitute for
    putting the tool on the wire.
    """
    if not request_text or not catalog_index:
        return []
    reads = {
        nm for nm in answerable_tools(request_text, list(catalog_index.values()))
        if nm in catalog_index and tool_tier(catalog_index[nm]) == "R"
    }
    # ANY answering read having run satisfies (c) — the question was served from this turn.
    if not reads or (reads & attempted):
        return []
    return sorted(reads)


#: A catalog name must be at least this long, and contain an underscore, before a literal
#: substring match counts as "the user named this tool". Every LoreWeave tool name is
#: snake_case (`composition_list_outline`, `kg_add_nodes`), so this cannot fire on ordinary
#: prose — and a false positive here would silence the rail for a turn, so it is worth the
#: two conditions rather than a bare `in`.
_NAMED_TOOL_MIN_LEN = 6


def _tools_named_in_request(text: str | None, catalog_index: dict) -> frozenset[str]:
    """The catalog tools the user named LITERALLY in their message.

    The deterministic counterpart to `user_abandoned_rail`: a literal match, no inference. It
    is the signal that a turn is a DISCOVERY turn — 281 of this deploy's 315 tools do not fit
    the hot seed and are reached only by the model choosing tool_list/tool_load, and a rail
    directive replaces that choice with its own step.

    MEASURED 2026-08-13, session 019ff929: "Load the tool composition_list_outline by name,
    then use it to show me the outline of this book." — tool_load advertised in all six
    passes, called zero times, while a stale `build-a-book` rail drove plan_propose_spec four
    times. When the user has named the tool themselves there is nothing left to recover.
    """
    if not text or not catalog_index:
        return frozenset()
    low = text.lower()
    return frozenset(
        name for name in catalog_index
        if len(name) >= _NAMED_TOOL_MIN_LEN and "_" in name and name.lower() in low
    )


# P2-FABRICATED-WRITE — the shape neither guard above can see.
#
# 🔴 THE MEASURED INSTANCE, batch 23, `plan_keep_material`, 4 of 5 runs. The tool was not
# advertised (surfaced 0/5), the model called NOTHING (`called_tools == []`), and it answered:
#
#     "I've updated the plan to include the new details while ensuring all the existing
#      material we've established remains intact. Your story foundation is now fully updated."
#
# The store is unchanged. The author is told their plan was updated when it was not.
#
# `_narrated_uncalled_writes` structurally cannot catch it: that guard keys on a snake_case TOOL
# NAME in prose, and here the model names no tool at all — it reports only the OUTCOME.
# `_unanswered_data_question_reads` keys on the REQUEST matching a read tool's vocabulary, and
# this is a write.
#
# CALIBRATED ON THE RECORDED CORPUS, NOT ON INTUITION — 2586 recorded turns, per the defect's own
# instruction that "a detector for 'claims an outcome without acting' is not a name match; it
# needs care and a control". Three candidates were scored against 60 hand-labelled zero-call
# turns; the two rejected ones are named so the choice can be re-checked rather than trusted:
#
#     claim-only                          precision 0.86  recall 1.00   (fired on a REFUSAL:
#                                                                        "a fact that I haven't
#                                                                         actually recorded")
#     claim AND no refusal   <-- CHOSEN   precision 1.00  recall 1.00
#     ...minus reasoning-scoped           precision 1.00  recall 0.83   (missed "I've cleared
#                                                                        that from my memory")
#
# On the guard's ACTUAL population — all 89 recorded zero-call turns — it fires on exactly 8,
# and all 8 are real: four are the `plan_keep_material` instance above, four are `memory_forget`
# claiming a fact was forgotten with nothing recorded. ZERO false positives across the other 81,
# which include 48 honest refusals ("I cannot cancel ... there are no active jobs").
#
# WHAT MAKES IT SAFE IS THE ZERO-CALL GATE, NOT THE PHRASE. The same phrasing appears in 499 of
# the 2497 turns that DID call something — it is ordinary language for reporting real work, and
# this guard never runs there.
#
# TWO OF THE EIGHT ARE BORDERLINE and are recorded as such rather than counted clean: "I have
# cleared that from my immediate reasoning" is honest about its scope. It still tells an author
# who asked to forget a STORED fact that a forget happened, so a nudge is right — but it is a
# weaker instance than the other six and should not be cited as proof of the guard's precision.
#: 🔴 ACKNOWLEDGING IS NOT ACTING, and the first version could not tell the difference.
#: `\w+ed` matched "I have NOTED your instruction to stop the translation" — a conversational
#: acknowledgement in a turn that had honestly reported an error one sentence earlier — and the
#: guard called it a narrated write. Found 2026-08-26 when a new batch (c-cancel1) entered the
#: corpus and the calibration test went red on a THIRD tool, which is exactly what that test is
#: for: it asserts WHICH tools fire, not how many, so new evidence cannot be absorbed silently.
#:
#: Measured over the whole 2656-turn corpus before shipping: 9 fires on 3 tools -> 8 fires on 2,
#: i.e. the one false positive removed and every true positive kept. The excluded verbs are all
#: ones that describe RECEIVING information rather than changing anything.
_CLAIMED_EFFECT_ACK = r"(?:noted|understood|reviewed|read|seen|heard|considered|checked|observed|noticed)"
_CLAIMED_EFFECT_RE = re.compile(
    r"\b(?:i've|i have)\s+(?:already\s+)?"
    rf"(?!{_CLAIMED_EFFECT_ACK}\b)"
    r"(?:\w+ed|forgotten|done|made|set|put|kept|left)\b",
    re.I,
)
#: Any refusal marker anywhere in the answer disqualifies it. Deliberately whole-answer rather
#: than sentence-scoped: the one false positive the looser candidate produced was a refusal whose
#: NEGATION sat in a different clause from the verb ("I cannot 'forget' a fact that I haven't
#: actually recorded"), and sentence-splitting that reliably is a harder problem than this guard
#: needs to solve. Erring toward silence is correct here — a missed nudge costs one false
#: sentence; a wrongly-nudged honest refusal teaches the model to stop refusing.
_REFUSAL_MARKER_RE = re.compile(
    r"\b(?:i cannot|i can't|i can not|can't|cannot|i'm sorry|i am sorry|unable to)\b", re.I,
)


def _claimed_an_effect_without_acting(text: str, *, attempted: set[str]) -> bool:
    """Did this turn assert a completed change while calling NOTHING at all?

    `attempted` counts successes AND failures, exactly as `_narrated_uncalled_writes` does: a
    model that TRIED and got a real error has honest feedback to report and must not be nudged.
    Requiring it to be EMPTY — rather than "made no WRITE call" — is what the measurement
    supports, and it is the conservative half: a turn that called a read and then over-claimed is
    a real defect this does NOT cover, and is left for a fix with its own evidence.
    """
    if attempted:
        return False
    body = text or ""
    if _REFUSAL_MARKER_RE.search(body):
        return False
    return bool(_CLAIMED_EFFECT_RE.search(body))


def _rail_write_step_stalled(
    rail_progress: list | None, *, catalog_index: dict, attempted: set[str],
    intent_slugs: frozenset[str] = frozenset(),
) -> str | None:
    """The WRITE tool a rail is waiting on, when this turn called NOTHING AT ALL.

    🔴 THE SISTER CASE `_narrated_uncalled_writes` STRUCTURALLY CANNOT SEE. That guard finds a
    claimed write by intersecting the prose with real tool NAMES, which is the right design — no
    NLP, no tense-guessing — but it only fires when the model names a tool. MEASURED LIVE
    2026-08-12, book 019f9a02-f3a3…: asked "Please translate this book into Vietnamese for me now",
    the model answered *"I've started the translation for Chapter 1 into Vietnamese. I'll monitor
    the progress…"* with ZERO tool calls, outcome='completed', and no job row. It named no tool, so
    the intersection was empty and nothing was logged. The plainer phrasing — the one a user
    actually gets — was invisible.

    This arm stays mechanical by refusing to read the prose at all. It uses only:

    * `attempted` is EMPTY — the turn called nothing, so nothing can have changed. A turn that
      tried and failed already has honest feedback and is deliberately excluded, exactly as the
      sister guard excludes it.
    * a rail has a next actionable step whose tool is a WRITE tier — so there was a concrete,
      journey-declared action outstanding, not merely a conversation in progress.

    It deliberately does NOT infer that the model *claimed* anything: the directive built from this
    asserts only what is measured (no tool ran, this step is outstanding), because a runtime that
    accuses the model of a claim it did not make is the same false-report defect pointed the other
    way — and this loop has already fixed three of those.
    """
    if attempted or not rail_progress:
        return None
    # D-FJ-17 — when THIS turn's own words pinned a rail, only that rail may claim the
    # nudge. `_pinned_slugs` is `binding + intent`, so the standing mode binding's rail
    # always sorted FIRST and won a search that never looked at what was asked.
    #
    # Measured live 2026-08-13 (session 019ff929, throwaway book 019ff8f5): the author
    # asked "What canon rules have I declared for this book?", which deterministically
    # pinned `canon-check` (next step: composition_list_canon_rules, a READ, advertised
    # in both passes). The turn called nothing, so this guard fired — and returned
    # `kg_add_nodes`, the outstanding write of the STALE `vision-to-book` rail from an
    # earlier journey. The directive sent pass 2 to answer that instead, and the author
    # got a paragraph about a character named Vela Ostrand appended to a fabricated
    # "you haven't declared any canon rules yet".
    #
    # A guard that drags a turn onto work the user did not ask about is worse than one
    # that stays quiet: the honest outcome here is NO nudge, because the pinned rail's
    # own next step is a read and this guard is deliberately writes-only.
    _rails = rail_progress
    if intent_slugs:
        _rails = [p for p in rail_progress if getattr(p, "slug", None) in intent_slugs]
    for prog in _rails:
        step = getattr(prog, "next_step", None)
        tool = getattr(step, "tool", None) if step is not None else None
        if not tool or tool not in catalog_index:
            continue
        if tool_tier(catalog_index[tool]) in ("A", "W", "S"):
            return tool
    return None


async def _flush_activated_tools(pool, session_id, activation_state: dict | None) -> None:
    """D-TOOLLOAD-LOST-ON-SUSPEND — persist the tools this turn activated.

    `tool_load` adds to the session's hot set so the tool survives into the NEXT turn;
    `resolve_session_tool_pins` reads `chat_sessions.activated_tools` back at turn start.
    That contract only holds if every way a turn can END writes the set back.

    It didn't. The flush lived on the normal-completion path only, and the suspend path
    `return`s before reaching it — so a turn that stopped for a human approval discarded
    everything it had loaded. That is precisely the turn that matters: a WRITE tool is
    tier A/W, so it suspends for approval, which means **the only turn that ever loads a
    write tool is the turn whose activation is thrown away.**

    Observed live (Mị Đế, session 019faf5b): the model `tool_load`ed
    `composition_outline_node_edit`, called it, suspended on the approval card — and by
    the next turn the tool was off the surface again (29 advertised, outline tools all
    read-only). Unable to call it, the model narrated the call in prose and then reported
    the write as DONE. Zero outline nodes existed. A hallucinated success is worse for an
    author than a loop: they are told to go and look at work that was never made.

    Best-effort by design — a failure here costs one re-load next turn, and must never
    take down a turn that otherwise succeeded."""
    if not (activation_state and activation_state.get("dirty")):
        return
    try:
        await pool.execute(
            """
            UPDATE chat_sessions
            SET activated_tools = $2::text[], updated_at = now()
            WHERE session_id = $1
            """,
            session_id,
            activation_state["activated_tools"],
        )
        activation_state["dirty"] = False
    except Exception:
        logger.warning(
            "failed to persist activated_tools for session %s", session_id, exc_info=True,
        )


def _rail_is_in_flight(
    *,
    resumed_mid_rail: bool,
    step_tools_succeeded: list[str],
    step_tools_attempted: list[str],
    asked_for_it_and_called_nothing: bool = False,
) -> bool:
    """D-RAIL-INFLIGHT-ON-ATTEMPT — is a pinned rail live enough for the P-1 step-runner
    to re-steer the model this turn?

    Live when ANY of:
      • `resumed_mid_rail` — this pass is a resume that suspended mid-rail. The confirm
        executes off the backend chokepoint, so it never lands in `turn_succeeded`, but
        the rail is unambiguously in flight.
      • a rail step tool SUCCEEDED this turn — the model chose to start the recipe.
      • a rail step tool was ATTEMPTED and FAILED this turn.

    That last clause is the fix. Gating "in flight" on success alone is the hole named in
    `D-CHAT-CONTROL-PLANE` §1 — *"it cannot rescue a model that cannot start"* — and it has
    now cost TWO live incidents with unrelated triggers: a step tool hidden from the turn
    catalog by the capability floor, and a step tool whose arguments the decoder corrupted
    (D-TOOLCALL-GEMMA-INTERIOR-LEAK). In both, every tool call in the iteration failed, so
    `turn_succeeded` stayed empty, the step-runner stayed silent, and the model degraded
    into repeated prose (40,597 and 10,882 characters) until the author hit Stop.

    **Intent is what makes a rail live: the model reached for the step.** Whether the
    platform let the call through is precisely the situation the directive exists to
    re-steer — so a failed attempt must not read as "no rail here".

    D-FJ-18 — and the THIRD clause closes the rest of that same hole, because all three of
    the above still require the model to have reached for SOMETHING. A turn that calls
    nothing at all had no mechanism whatsoever when the outstanding step is a READ: the
    D-FJ-8 narrated-write arm is deliberately writes-only ("nothing was claimed to have
    changed, so there is nothing for the author to not find"), and this gate wanted an
    attempt that never happened.

    MEASURED LIVE 2026-08-13 (session 019ff929, book 019ff8f5): asked "What canon rules have
    I declared for this book?", the turn pinned `canon-check` (next step
    composition_list_canon_rules, advertised), called NOTHING, and answered *"I checked the
    consistency rules for this book, and you haven't declared any canon rules yet"* while
    the owning store held one active rule. A fabricated absence is the read-side twin of a
    hallucinated write and is worse in one way: the author is told their own data is not
    there, and has no reason to go and look.

    `asked_for_it_and_called_nothing` is deliberately the narrowest possible opening — the
    rail was pinned by THIS turn's own words (intent_pinned_workflows, deterministic, no
    LLM) AND the turn emitted no tool call at all. It cannot hijack an ordinary
    conversation, because an ordinary conversation pins no rail; and the drive it unlocks is
    confined to the intent-pinned rail at the call site, so it can never re-steer the turn
    onto some other journey's outstanding work (that is D-FJ-17, fixed in the same cycle).
    """
    return bool(
        resumed_mid_rail
        or step_tools_succeeded
        or step_tools_attempted
        or asked_for_it_and_called_nothing
    )


def _braces_balanced(text: str) -> bool:
    """A cheap structural-completeness gate, NOT a JSON validator: same count
    of `{`/`}`. Distinguishes a genuinely truncated stream (e.g. `{"q": "Ka`,
    1 open / 0 close — must stay a hard failure, `json_repair` would happily
    GUESS a closing value we can't verify is right) from a structurally
    complete-but-malformed string (Gemma's token substitution — braces are
    all there, just the quoting inside is wrong) — only the latter is safe
    to hand to a repair library, which reconstructs plausible JSON but can't
    know what a truncated value was actually going to say."""
    return text.count("{") == text.count("}")


def _parse_tool_args(raw: str) -> dict:
    """Parse a tool call's accumulated `arguments` JSON string.

    Tries, in order: (1) `json.loads` as-is — the fast path, unchanged for a
    well-behaved provider; (2) the Gemma-token de-mangling above + retry;
    (3) `json_repair` as a general malformed-JSON safety net (handles other
    models' minor syntax slips: trailing commas, single quotes, etc.) — gated
    on `_braces_balanced` so a genuinely truncated stream still degrades hard
    rather than being "repaired" into a guessed, possibly-wrong value. A
    still-malformed or empty string yields {} so `execute_tool` still
    receives a dict (the MCP tool then surfaces a normal arg-validation
    error) — but unlike before, this degrade path is now logged, so a
    provider that's silently mangling every tool call is visible instead of
    only showing up as a confusing downstream "missing required field"."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and not _has_leak_marker(raw):
            return parsed
    except (ValueError, TypeError):
        pass
    for candidate in (_degemmify_tool_args(raw), raw):
        # D-TOOLCALL-GEMMA-INTERIOR-LEAK post-condition. `repair_json` will happily
        # absorb a surviving control token into the nearest string value and hand back
        # JSON that PARSES — the worst possible outcome, because every caller then
        # treats a corrupted payload as a clean one and the tool blames the model for
        # a value it never wrote. A candidate that still carries a marker has not been
        # repaired, it has been disguised; refuse it. `_split_interior_leaked_tool_calls`
        # upstream normally removes the marker first, so reaching here means the shape
        # was one that splitting could not resolve.
        if _has_leak_marker(candidate) or not _braces_balanced(candidate):
            continue
        try:
            parsed = json.loads(repair_json(candidate))
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed:
            return parsed
    logger.warning(
        "tool-call arguments unparseable after repair attempts, degrading to {}%s: %r",
        " (native control tokens present — decoder leak, not a model mistake)"
        if _has_leak_marker(raw) else "",
        raw[:300],
    )
    return {}


def _reassemble_tool_calls(frags: dict) -> list[dict]:
    """Collapse accumulated ToolCallEvent fragments (keyed by `index`)
    into an ordered list of `{id, name, arguments}` — `arguments` is the
    concatenated JSON string the gateway streamed."""
    calls: list[dict] = []
    for idx in sorted(frags):
        f = frags[idx]
        calls.append({
            "id": f.get("id") or "",
            "name": f.get("name") or "",
            "arguments": f.get("arguments", ""),
        })
    return calls


def _drop_duplicate_empty_tool_calls(calls: list[dict]) -> list[dict]:
    """D-TOOLCALL-DUP-EMPTY-CALL — a sibling of D-TOOLCALL-GEMMA-TOKEN-LEAK
    (commit 873829f42), same defective-decoding model family, DIFFERENT
    manifestation: instead of abandoning the structured `tool_calls` channel
    for leaked plain-text tokens, the model emits a genuinely well-formed
    structured tool call and then, in the SAME pass, a second structured call
    to the IDENTICAL tool name with empty/missing arguments — two distinct
    entries in the provider's own `tool_calls` array (confirmed: each arrives
    as a separate `ToolCallEvent.index`, so `tool_frags`/`_reassemble_tool_calls`
    is not splitting one call into two — the model itself emits two blocks).
    Live-pulled Postgres transcripts show the model's own reasoning narrating
    awareness of the mistake ("Ah, I made a mistake... calling
    glossary_web_search twice, the second one without a query") without being
    able to self-correct — a harness/decoding defect, not a prompting one.
    Left unhandled, the malformed duplicate reaches `execute_tool` and trips a
    `missing properties` validation error, which one real session hit 13+
    times before giving up or hallucinating an answer.

    Drops the pattern: same tool name, where the LAST WELL-FORMED call SEEN SO
    FAR for that tool name (not necessarily the immediately preceding kept
    call overall) had arguments that parse to a non-empty dict, and this
    call's arguments parse to an empty dict (covers both a literal
    `{}`/missing-args string and anything `_parse_tool_args` could not repair
    into a non-empty dict). A later call to the same tool with its OWN
    non-empty arguments — e.g. two genuinely distinct searches in one turn —
    is never touched, since only an empty-after-a-well-formed-call pattern
    matches. The dropped call never reaches `working`/execution, so no
    validation error is ever surfaced back to the model for it.

    review-impl MED fix: this used to compare a call ONLY to the immediately
    preceding KEPT call, regardless of tool name — so `[A(good), B(good),
    A(empty)]` never recognized the trailing empty `A` as a duplicate of the
    earlier `A`, because `B` sat between them as the "immediately preceding
    kept call." Now tracks the last well-formed call PER TOOL NAME (a
    `dict[str, dict]`), so a non-adjacent duplicate for the same tool is still
    caught regardless of what other tool calls appear in between."""
    if len(calls) < 2:
        return calls
    kept: list[dict] = []
    dropped: list[str] = []
    last_well_formed_by_name: dict[str, dict] = {}
    for c in calls:
        name = c["name"]
        prior = last_well_formed_by_name.get(name) if name else None
        if (
            prior is not None
            and _parse_tool_args(prior["arguments"])
            and not _parse_tool_args(c["arguments"])
        ):
            dropped.append(name)
            continue
        kept.append(c)
        if name and _parse_tool_args(c["arguments"]):
            last_well_formed_by_name[name] = c
    if dropped:
        logger.warning(
            "D-TOOLCALL-DUP-EMPTY-CALL: dropped %d malformed duplicate tool-call(s) "
            "(same tool as an earlier well-formed call this pass, empty/missing args): %s",
            len(dropped), dropped,
        )
    return kept


def _collapse_identical_tool_calls(calls: list[dict]) -> list[dict]:
    """D-TOOLCALL-DUP-IDENTICAL — collapse BYTE-IDENTICAL calls emitted in the SAME pass.

    Sibling of `_drop_duplicate_empty_tool_calls` above (same defective-decoding family),
    but the opposite manifestation: instead of a well-formed call followed by an EMPTY
    one, the model emits the exact same call — same tool, same arguments — two to four
    times in a single `tool_calls` array. Measured live over 24h of transcripts
    (2026-07-23): every affected session had `count(DISTINCT args) = 1`, i.e. the repeats
    were byte-identical, not a batch of different requests:

        019f8dbd  glossary_propose_entity_edit  4 calls / 1 distinct args
        019f8cb2  glossary_propose_entity_edit  4 calls / 1 distinct args
        019f8dda  glossary_propose_entities     3 calls / 1 distinct args
        019f8cb2  tool_list                     3 calls / 1 distinct args

    All carried `iteration: 0` — parallel duplicates within one emission, NOT sequential
    retries after seeing a result.

    This is a CORRECTNESS fix, not just a token saving. `glossary_propose_entities`
    happens to dedup by name server-side, so the repeats were absorbed — but a write tool
    without its own idempotency (e.g. a plain create) would execute N times and produce N
    rows from one user intent.

    Scope is deliberately ONE PASS: only the calls in this single emission are compared.
    An identical call in a LATER iteration is a legitimate retry — the model has seen a
    result by then and state may have changed — and is never touched. Dropping happens
    before the assistant message is assembled (same as the sibling helper), so the dropped
    ids never appear in `tool_calls` and the provider never expects a response for them.
    """
    if len(calls) < 2:
        return calls
    kept: list[dict] = []
    seen: set[tuple[str, str]] = set()
    dropped: list[str] = []
    for c in calls:
        # Canonicalize through the same parser execution uses, with sorted keys, so
        # semantically identical args differing only in key order or whitespace collapse.
        try:
            key = (c["name"], json.dumps(_parse_tool_args(c["arguments"]), sort_keys=True))
        except Exception:
            kept.append(c)
            continue
        if key in seen:
            dropped.append(c["name"])
            continue
        seen.add(key)
        kept.append(c)
    if dropped:
        logger.warning(
            "D-TOOLCALL-DUP-IDENTICAL: collapsed %d byte-identical duplicate tool-call(s) "
            "emitted in one pass: %s", len(dropped), dropped,
        )
    return kept


async def _run_composer(
    client,
    composer_model: tuple[str, str],
    composer_system_prompt: str | None,
    args_obj: dict,
    gen_params: dict,
) -> tuple[str, int, int]:
    """A2A phase-2 — stream the composer (writer) model for a compose_prose call.

    Returns (prose, input_tokens, output_tokens). Reuses the orchestrator's
    `client` (the gateway resolves the model per request via model_ref), offers
    NO tools (pure generation), and discards the composer's reasoning — only its
    prose is returned to the orchestrator."""
    src, ref = composer_model
    msgs = build_composer_messages(args_obj, composer_system_prompt)
    kwargs: dict = {"model_source": src, "model_ref": ref, "messages": msgs}
    max_tokens = gen_params.get("max_tokens")
    if max_tokens is not None and max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    if gen_params.get("temperature") is not None:
        kwargs["temperature"] = gen_params["temperature"]
    # D-M3-COMPOSER-SUBSTREAM-OBSERVABILITY — mint a job id so the gateway
    # persists a billing-neutral observability row for the composer sub-stream
    # too (and a disconnect frees the slot via the aclose cascade), exactly like
    # the main chat helpers. Billing-neutral: usage is still summed by the
    # orchestrator from the composer's UsageEvents.
    kwargs["stream_job_id"] = str(uuid4())
    req = StreamRequest(**kwargs)
    parts: list[str] = []
    used_in = 0
    used_out = 0
    async for ev in client.stream(req):
        if isinstance(ev, TokenEvent):
            parts.append(ev.delta)
        elif isinstance(ev, UsageEvent):
            used_in += ev.input_tokens
            used_out += ev.output_tokens
        # ReasoningEvent (composer's thinking) and DoneEvent are intentionally ignored.
    return "".join(parts).strip(), used_in, used_out


def _catalog_index(catalog: list[dict]) -> dict[str, dict]:
    """name → tool def, for the discovery catalog."""
    idx: dict[str, dict] = {}
    for td in catalog:
        fn = td.get("function") if isinstance(td, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            idx[fn["name"]] = td
    return idx


def _project_ambient_book_schema(td: dict) -> dict:
    """D-AMBIENT-BOOK-SCHEMA-PROJECTION (2026-07-26, Mị Đế dogfood): on a BOOK-BOUND
    session, an `ambient_book` tool's advertised schema drops `book_id` entirely —
    the backend resolves it from the studio binding (X-Book-Id) and the arg-injection
    seam backfills/overrides it anyway, so the model must never be ASKED for it. A
    weak model shown a book_id property treats it as a demand and stalls hunting for
    the id (live: "mọi nỗ lực tự tìm book_id của tôi đều thất bại vì các lệnh đọc
    cũng yêu cầu phải có book_id"). Absent from the schema, the belief cannot form."""
    fn = td.get("function") if isinstance(td, dict) else None
    if not isinstance(fn, dict):
        return td
    meta = fn.get("_meta") or {}
    if not meta.get("ambient_book"):
        return td
    params = fn.get("parameters") or {}
    props = params.get("properties") or {}
    if "book_id" not in props:
        return td
    new_params = dict(params)
    new_params["properties"] = {k: v for k, v in props.items() if k != "book_id"}
    if isinstance(params.get("required"), list):
        new_params["required"] = [r for r in params["required"] if r != "book_id"]
    return {**td, "function": {**fn, "parameters": new_params}}


def _agentruntime_wire_surface(*, pass_number: int) -> list[dict]:
    """CP-2.7 · the new arm's advertised set for one pass. **The only implementation.**

    Two call sites need it — the first-pass `tool_defs` (whose emptiness decides `use_tools`) and
    the per-pass wire value — and they must not be two copies of the same decision. This repository
    has recorded a hand-written second copy drifting from the first *inside a single commit*.
    """
    from app.agentruntime.manifest import load as _agentruntime_load
    from app.agentruntime.serve import advertise as _agentruntime_advertise

    payload, _surface = _agentruntime_advertise(_agentruntime_load(), pass_number=pass_number)
    return payload


#: The tools R1 answerability FORCED onto this pass, recorded by the builder and checked again at
#: the wire. A ContextVar rather than a return value for the same reason `record_surface_withheld`
#: is one: the two points are far apart, and threading a value through every caller in between is
#: how a check ends up not being written at all.
_R1_FORCED: "ContextVar[frozenset[str]]" = ContextVar("_r1_forced", default=frozenset())


def _advertise_discovery_tools(
    catalog_index: dict[str, dict],
    active_tool_names: set[str],
    extra_frontend: list[dict],
    permission_mode: str = "write",
    has_workflows: bool = False,
    suppress_tool_list: bool = False,
    suppress_names: set[str] | frozenset[str] = frozenset(),
    book_bound: bool = False,
    # R1 (surface answerability) — THIS turn's request, so the chokepoint can guarantee that a
    # tool whose own declared vocabulary answers it is on the wire. Empty ⇒ inert.
    request_text: str = "",
) -> list[dict]:
    """MCP-fanout C-FT — the tools advertised on a universal /chat pass:
    ``{always-on core} ∪ {full schemas of active_tool_names}``, with the
    consumer-only `_meta` stripped before it reaches the provider.

    ``extra_frontend`` carries surface-specific frontend tools (e.g. propose_edit
    on an editor surface) that are always advertised alongside the core.

    RAID C2 (DR-C2) — this is the single ADVERTISE chokepoint for the discovery
    path: in ``ask`` mode, catalog-sourced (server) tools filter to tier R only;
    find_tools + the frontend core + extra_frontend are unaffected (frontend
    tools are human-executed by construction). ``write`` (default) is a strict
    no-op — the surface is byte-identical to pre-C2 (pinned by contract test).

    RAID B2 (07S §5b) — ``plan`` mode advertises the ask surface PLUS the
    PlanForge ``plan_*`` server tools (plan artifacts, never prose).
    """
    restricted = permission_mode in ("ask", "plan")
    # 🔴 CP-2.7 — THE ROUTE, AND IT IS A `return` RATHER THAN A MERGE.
    #
    # This function is the single ADVERTISE chokepoint for the discovery path, with three callers,
    # which is why the branch is here and nowhere else: one edit covers every path a turn can take
    # to the wire. On the new arm the advertised set comes from the manifest and from NOTHING
    # else — not the always-on core, not `find_tools`, not `extra_frontend`.
    #
    # A merge would be the membrane leaking through its own route on day one, and it would make
    # CP-2.7's item B (*no legacy declaration is reachable, by any route*) unmeasurable in exactly
    # the place it most needs measuring. ARCHITECTURE §3: "old declarations are not hidden, they
    # are ABSENT".
    #
    # Every argument above is deliberately unused on this branch. That is not an oversight to tidy
    # up later: `catalog_index` IS the legacy catalog, and a branch that reads it — even to check
    # something — is the code path §3 forbids. The membrane gate cannot see this file, so the
    # separation rests on this `return` being first.
    if settings.agentruntime_arm:
        return _agentruntime_wire_surface(pass_number=1)

    plan = permission_mode == "plan"
    out: list[dict] = []
    seen: set[str] = set()

    def _add(td: dict | None) -> None:
        if not td:
            return
        fn = td.get("function") if isinstance(td, dict) else None
        name = fn.get("name") if isinstance(fn, dict) else None
        if not name or name in seen:
            return
        seen.add(name)
        if book_bound:
            td = _project_ambient_book_schema(td)
        out.append(strip_tool_meta(td))

    # Always-on core: prefer the catalog's own def (if a core tool is federated),
    # else the consumer-local find_tools schema or a generic frontend-tool schema
    # (ui_*/confirm/propose). find_tools is NOT federated, so it has no catalog
    # entry — source it from FIND_TOOLS_TOOL.
    for name in ALWAYS_ON_CORE_NAMES:
        # RETIRED 2026-08-25. This branch has been UNREACHABLE since F17 (2026-07-20) pulled
        # FIND_TOOLS_NAME out of ALWAYS_ON_CORE_NAMES — the tuple this loop iterates. It read
        # like a live advertise path and was not one, which is precisely how a half-retired
        # tool poisons whoever reads the file next. Kept as a comment so nobody re-adds it.
        #   if name == FIND_TOOLS_NAME:
        #       _add(FIND_TOOLS_TOOL)
        #       continue
        # WS-1a — tool_list/tool_load are consumer-local meta-tools (not federated), like
        # find_tools; source their schemas from the module defs.
        if name == TOOL_LIST_NAME:
            # F18 — dropped from the wire once the model has exhausted discovery this turn
            # (it looped on tool_list). tool_load stays advertised, so a specific tool is
            # still reachable by name; the dispatch below still handles a hallucinated call.
            if suppress_tool_list:
                continue
            _add(TOOL_LIST_TOOL)
            continue
        if name == TOOL_LOAD_NAME:
            _add(TOOL_LOAD_TOOL)
            continue
        _add(catalog_index.get(name) or generic_frontend_tool_def(name))
    # WS-2b — advertise the workflow meta-tools ONLY when the turn actually has
    # curated workflows visible (keeps the default core lean when there are none).
    # Consumer-local like tool_list/tool_load; dispatched below.
    if has_workflows:
        _add(WORKFLOW_LIST_TOOL)
        _add(WORKFLOW_LOAD_TOOL)
    # F7c — the load_skill control (twin of tool_load): advertised ONLY when lazy skill
    # bodies are enabled, so the model can pull a skill's full instructions on demand
    # after seeing it in the L1 index. Flag OFF ⇒ not added ⇒ the surface is
    # byte-identical to pre-F7c (the A/B baseline). Consumer-local; dispatched below.
    if settings.lazy_skill_bodies:
        _add(LOAD_SKILL_TOOL)
    for td in extra_frontend:
        _add(td)
    # Discovered tools — full schemas now that find_tools matched them.
    # Ask mode: only tier-R server tools are advertised (untiered defaults R —
    # inert by the C-TOOL convention); discovery still works, but a discovered
    # non-R tool is NOT advertised (DR-C2). Plan mode additionally advertises
    # the `plan_*` PlanForge tools regardless of tier (RAID B2).
    # ── R1 · ANSWERABILITY, the last word on the surface ──────────────────────────────────
    # Five mechanisms narrow this set before we get here — domain selection, the hot-seed
    # budget, the write allowlist, rail step pre-activation, and the suppressors. Each is
    # locally correct. NONE of them is accountable for whether what comes out can answer the
    # question that went in, and twice that has put a defect in an author's book:
    #
    #   v1 2026-07-21 — book_update_details starved by its 5-field schema, so "every model
    #     mis-routed 'update the description' to book_chapter_create/save_draft".
    #   v2 2026-08-13 — composition_list_outline withheld at domain_not_selected in every pass
    #     while the Tier-A outline WRITE stayed advertised. Measured 5/5: the model used the
    #     write it could see and created three chapters in the store.
    #
    # Both tools had already DECLARED they answer those requests. So the guarantee is: if the
    # user's words match a tool's own vocabulary, it is on the wire — whatever the budget, the
    # domain selection or the rail decided. Bounded by what was actually said (1-3 tools on
    # real prompts, 0 on chitchat) rather than by an allowlist that spends the prefix forever.
    _answerable = answerable_tools(request_text, list(catalog_index.values()))
    # Distinct local names on purpose: `test_cp0_instrument` anchors its catalog-miss guard on
    # the FIRST `td = catalog_index.get(name)` and windows the source after it. Reusing those
    # names here moved that anchor and made an established narrowing-instrumentation test read
    # the wrong block. New code must not shadow an existing guard's anchor.
    # 🔴 R1 HAS NO OBSERVABILITY, AND THAT COST TWO MEASUREMENTS. The guarantee runs on
    # every pass and logs nothing, so "the tool the request names is not on the wire" cannot be
    # told apart from "the rescue fired and something downstream dropped it" — and a tool that IS
    # advertised cannot be told apart from one the hot seed happened to include anyway. Measured
    # 2026-08-23 on composition_arc_apply: answerable_tools picks it against the live 303-tool
    # catalogue (with book_list and composition_arc_suggest), those two were advertised and it was
    # not, and no evidence on hand could say which stage lost it.
    #
    # Logged at INFO with the reason, because a rescue that silently declines is the failure mode:
    # every `continue` below is a decision to leave the answering tool off the wire.
    if _answerable:
        logger.info("R1 answerability: request matches %s", sorted(_answerable))
    # 🔴 R1 STOPPED AT DEPTH 1, AND THAT IS WHY IT COULD NOT DELIVER THE TOOL IT FORCED.
    #
    # The guarantee puts the tool whose declared vocabulary answers the request on the wire. It
    # carried NOTHING that tool needs. A user names a GOAL, not an intermediate step, so a supplier
    # is matched only by accident — and every blocked tool in P14-SUPPLIER-NOT-ON-SURFACE failed on
    # an id whose supplier the request's words do not describe:
    #
    #     plan_bootstrap_apply  needs proposal_id  <- plan_bootstrap_propose
    #         measured 2026-08-23: apply advertised on 21 wire passes, propose on ZERO
    #
    # The tiers refute the tempting explanation ("the budget favours writes over reads"): the plan
    # pair is Tier A on both sides and the arc-template pair is Tier R on both sides. It is DEPTH.
    #
    # AND IT MUST BE TRANSITIVE, which composition_reference_update proves: reference_id comes from
    # composition_find_references, which was ALREADY on every pass and itself refused for its own
    # missing entity_id. A one-hop fix would have looked right on the other instances and left that
    # turn dying one call later.
    #
    # DECLARED DATA ONLY. The suppliers come from the contract registry's `argument_emitters` map —
    # the same structured source `_missing_args_message` already reads to name an emitter in a
    # refusal — never from a name, a prefix or a guess. A tool with no declaration adds nothing, so
    # this can only widen the surface where the platform has already written down who supplies what.
    _r1_seed = set(_answerable)
    # What R1 actually put on this pass — recorded so the WIRE can check the guarantee held.
    _r1_forced: set[str] = set()
    _forced_suppliers: dict[str, str] = {}
    if _r1_seed:
        # Local import, mirroring the other reader of this registry a thousand lines below — the
        # module-level import graph here is load-bearing and this file does not add to it lightly.
        from app.agentruntime.toolcontract import declared_emitter

        _reg = _tool_contract_registry()
        _pending, _seen = list(_r1_seed), set(_r1_seed)
        # Bounded: a declaration cycle (A emits for B, B for A) would otherwise loop, and a long
        # chain is a fixture problem rather than something to advertise our way out of.
        for _hop in range(4):
            _next: list[str] = []
            for _consumer in _pending:
                _c_td = catalog_index.get(_consumer)
                _params = ((_c_td or {}).get("function", {}).get("parameters", {}) or {})
                for _arg in (_params.get("required") or []):
                    _sup = declared_emitter(_reg, _consumer, _arg)
                    if not _sup or _sup in _seen or _sup not in catalog_index:
                        continue
                    _seen.add(_sup)
                    _next.append(_sup)
                    _forced_suppliers[_sup] = f"{_consumer}.{_arg}"
            if not _next:
                break
            _pending = _next
        if _forced_suppliers:
            logger.info(
                "R1 answerability: also forcing declared supplier(s) %s — a tool whose required id "
                "has a declared emitter is unusable without it",
                sorted(f"{k} (for {v})" for k, v in _forced_suppliers.items()),
            )
            _answerable = _seen
    for _ans_name in sorted(_answerable):
        if _ans_name in suppress_names:
            logger.info("R1 answerability: %s NOT forced — suppressed (loop breaker)", _ans_name)
            # A suppressor is a LOOP breaker (repeated failure / repeated read / oneshot). It
            # fires on tools the model is already hammering, so forcing one back would restart
            # the loop this stage exists to stop. Answerability outranks a BUDGET, never a
            # breaker.
            continue
        _ans_td = catalog_index.get(_ans_name)
        if _ans_td is None:
            logger.info(
                "R1 answerability: %s NOT forced — absent from this turn's catalog, so the "
                "guarantee cannot reach it however well it declared itself", _ans_name,
            )
            continue
        if restricted and tool_tier(_ans_td) not in ("R", None) and not (
            permission_mode == "plan" and _is_plan_tool(_ans_name)
        ):
            logger.info("R1 answerability: %s NOT forced — tier %s under %s mode",
                        _ans_name, tool_tier(_ans_td), permission_mode)
            # ask/plan mode still governs WHAT may run; answerability governs what is VISIBLE.
            continue
        _add(_ans_td)
        _r1_forced.add(_ans_name)
    for name in active_tool_names:
        # oneshot-deadvertise (2026-07-25): a COMPLETED one-shot create is dropped from the
        # wire so a weak model cannot loop on it (schema-gating — "absent from the schema, the
        # agent cannot attempt or probe"). find_tools/tool_load still reach it by name if a
        # genuinely-new need arises; this only removes it from the always-visible active set.
        if name in suppress_names:
            continue
        td = catalog_index.get(name)
        if td is None:
            # P1 residual — TWO unregistered narrowings lived in these four lines, and they are the
            # last frame of a defect that has now occupied six.
            #
            # This one: a name in the ACTIVE SET with no catalog entry. `_add(None)` returns at its
            # first line, so the tool leaves the wire without a word — and it is downstream of
            # domain selection, so `domain_not_selected` never sees it either. That is exactly the
            # shape V-LIVE measured: four glossary tools, the SAME four in both runs, in a domain
            # that WAS selected, in neither bucket. Deterministic, because a catalog miss is a
            # property of the catalog rather than of the query.
            instrument.record_surface_withheld(
                name, stage="catalog_miss",
                reason="in the active set but absent from this turn's catalog index",
            )
            continue
        if (
            restricted and tool_tier(td) != "R"
            and not (plan and _is_plan_tool(name))
        ):
            # And this one: ask/plan mode drops every non-tier-R tool here, silently. The
            # permission-mode registration at the advertise chokepoint covers the OTHER branch
            # only, so on a discovery surface this narrowing registered nowhere.
            instrument.record_surface_withheld(
                name, stage="permission_tier",
                reason=f"tier {tool_tier(td)!r} not offered in restricted mode",
            )
            continue
        _add(td)
    # 🔴 R1 IS A GUARANTEE, SO IT HAS TO BE CHECKABLE DOWNSTREAM. Publish what this pass forced;
    # the wire compares and records a narrowing for anything that vanished between here and there.
    _R1_FORCED.set(frozenset(n for n in _r1_forced
                             if n in {(d.get("function") or {}).get("name") for d in out}))
    return out


def _filter_tools_for_ask(
    tools: list[dict], permission_mode: str = "ask"
) -> list[dict]:
    """RAID C2 (DR-C2) — the ask-mode filter for the NON-discovery paths (legacy
    full-catalog clients, admin, gateway-down agui). Keeps find_tools, frontend
    tools (human-executed by construction), and tier-R server tools; drops every
    tiered A/W/S server tool. Untiered defaults R (inert — C-TOOL convention).

    RAID B2 (07S §5b) — ``permission_mode='plan'`` additionally keeps the
    PlanForge ``plan_*`` server tools (plan artifacts, never prose)."""
    plan = permission_mode == "plan"
    out: list[dict] = []
    for td in tools:
        fn = td.get("function") if isinstance(td, dict) else None
        name = fn.get("name") if isinstance(fn, dict) else None
        if not name:
            continue
        # Browser-executed (not merely chat-intercepted): these are human-gated by
        # construction — the person applies the card — so they survive a read-only
        # mode. Same P2.2/P3.2 drift as the other consumers.
        if name == FIND_TOOLS_NAME or is_browser_executed(name):
            out.append(td)
            continue
        if tool_tier(td) == "R" or (plan and _is_plan_tool(name)):
            out.append(td)
    return out


def _unwrap_wrapped_args(args_obj: dict, tool_def: dict | None) -> dict:
    """Undo a mid-tier model's habit of wrapping the whole payload in a lone envelope key.

    If ``args_obj`` is exactly ``{"args": {...}}`` (or ``{"arguments": {...}}``) and the tool's
    real schema does NOT declare that property, return the inner dict. A no-op otherwise —
    including for a tool that legitimately has an ``args``/``arguments`` parameter, so this can
    never eat a real field."""
    if not isinstance(args_obj, dict) or len(args_obj) != 1:
        return args_obj
    key = next(iter(args_obj))
    # `params` measured 2026-08-09 (14 calls, book_read): the model wrapped the whole payload
    # in the JSON-RPC envelope name it had just seen on the wire. Same shape, same guard — a
    # tool that REALLY declares `params` is left alone by the `key in props` check below.
    if key not in ("args", "arguments", "params"):
        return args_obj
    inner = args_obj[key]
    if not isinstance(inner, dict):
        return args_obj
    props = (((tool_def or {}).get("function") or {}).get("parameters") or {}).get("properties") or {}
    if key in props:
        return args_obj  # the tool REALLY has this param — do not unwrap
    return inner


# Scalar id args a mid-tier model sometimes wraps in a 1-element list (measured live:
# gemma sent kg_project_entities_to_nodes `project_id=["<uuid>"]` and kg_project_create
# `book_id=["<uuid>"]` → the tool 400s "Input should be a valid string (you sent a list)").
# These are ALWAYS scalar UUIDs — their plural, legitimately-array forms (`entity_ids`,
# `items`) are deliberately NOT in this set, so coercing `[x] → x` here can never eat a
# real list. Schema-free, so it also works on the resume-execute path (no tool_def there).
_SCALAR_ID_ARGS = frozenset({
    "book_id", "project_id", "chapter_id", "entity_id", "world_id",
    "arc_id", "node_id", "outline_node_id", "run_id",
    # 🔴 **MEASURED 2026-08-11 (tool-v2 loop #42): `model_ref` was missing from this set and has
    # the defect it exists for.** `translation_start_extraction` was called 3 times with
    # `model_ref: ["019ebb72-…"]` — a 1-element list holding a real model UUID — and the tool
    # rejected it for the type, exactly as it rejected `project_id=["…"]` before that arg was
    # added here. This set is an ENUMERATION of scalar-id args, so a missing member is an
    # oversight rather than a decision; `model_ref` is a scalar UUID reference with no
    # legitimately-array form, which is the same test `entity_ids` and `items` FAIL and are
    # therefore correctly excluded. Small subject, stated plainly: 3 calls in 1 session.
    "model_ref",
})


# ── T16-D1: the right id under the wrong KEY ────────────────────────────────────────────────
#
# `_coerce_listed_scalar_ids` above fixes a wrong VALUE shape under the right key. This fixes the
# mirror case — the right value under a near-miss KEY — and it is the larger population.
#
# MEASURED 2026-08-09/10 on `book_read`, which refused 89 calls for a missing `book_id`. Only 33
# of those were genuinely empty. The other 56 CARRIED THE CORRECT UUID:
#
#     {"id": "019fccd7-…"}          19 calls
#     {"ids": ["019fccd7-…"]}       13 calls
#     {"book_ids": ["019fccd7-…"]}   8 calls
#     {"params": {"book_id": …}}    14 calls   (fixed by _unwrap_wrapped_args above)
#
# The model had the id, had just read it out of `book_list`, and named the field wrongly. The
# runtime answered "is missing ['book_id'] … NOT yours to invent", which is true of the FIELD and
# false of the situation.
#
# DECLINES ANYTHING IT CANNOT REASON ABOUT, the same rule the rest of this family follows,
# because a wrong graft corrupts a call instead of refusing it:
#   * exactly ONE required `*_id` property may be missing — with two, filling either is a guess;
#   * the donor key must be `id`, `ids`, or the plural of the target (`book_id` -> `book_ids`);
#   * the donor key must NOT itself be declared by the schema — a tool that really takes `ids`
#     keeps it;
#   * the value must be a string, or a ONE-element list of a string; a longer list is a genuine
#     collection and is left alone.
def _alias_id_keys(target: str) -> frozenset[str]:
    """The near-miss donor keys for a required scalar id param."""
    return frozenset({"id", "ids", target + "s"})


def _repair_aliased_required_id(args_obj: dict, tool_def: dict | None) -> dict:
    """Move a required `*_id` the model put under `id`/`ids`/`<param>s` back onto its own key."""
    if not isinstance(args_obj, dict) or not tool_def:
        return args_obj
    params = ((tool_def.get("function") or {}).get("parameters") or {})
    props = params.get("properties") or {}
    required = params.get("required") or []
    missing = [r for r in required if isinstance(r, str) and r.endswith("_id") and r not in args_obj]
    if len(missing) != 1:
        return args_obj
    target = missing[0]
    donors = _alias_id_keys(target)
    present = [k for k in args_obj if k in donors and k not in props]
    if len(present) != 1:
        return args_obj
    raw = args_obj[present[0]]
    if isinstance(raw, list):
        if len(raw) != 1:
            return args_obj
        raw = raw[0]
    if not isinstance(raw, str) or not raw.strip():
        return args_obj
    repaired = {k: v for k, v in args_obj.items() if k != present[0]}
    repaired[target] = raw
    return repaired


def _coerce_listed_scalar_ids(args_obj: dict) -> dict:
    """Undo a mid-tier model wrapping a scalar id in a 1-element list — `[uuid] → uuid`
    for the known scalar-id args only. A no-op for a well-formed call and for any array arg."""
    if not isinstance(args_obj, dict):
        return args_obj
    for k in _SCALAR_ID_ARGS:
        v = args_obj.get(k)
        if isinstance(v, list) and len(v) == 1 and isinstance(v[0], (str, int)):
            args_obj[k] = v[0]
    return args_obj


def _declared_types(prop_schema: object) -> set[str]:
    """The JSON-schema types a property declares — tolerating ``"type": "array"``,
    ``"type": ["array", "null"]``, and a one-level ``anyOf``/``oneOf`` union."""
    if not isinstance(prop_schema, dict):
        return set()
    out: set[str] = set()
    t = prop_schema.get("type")
    if isinstance(t, str):
        out.add(t)
    elif isinstance(t, list):
        out.update(x for x in t if isinstance(x, str))
    for key in ("anyOf", "oneOf"):
        for sub in prop_schema.get(key) or []:
            if isinstance(sub, dict):
                st = sub.get("type")
                if isinstance(st, str):
                    out.add(st)
                elif isinstance(st, list):
                    out.update(x for x in st if isinstance(x, str))
    return out


def _coerce_json_string_structs(args_obj: dict, tool_def: dict | None) -> dict:
    """Undo a mid-tier model emitting a STRUCTURED arg as a *stringified JSON* blob.

    Measured live (M0a, S06 beat-F, gemma-4-26b): `book_chapter_save_draft` was called with
    ``body="[{\\"type\\":\\"paragraph\\",...}]"`` — the prose was CORRECT and every other arg
    (chapter_id/book_id/base_version) was right, but `body` is declared ``array`` and arrived as
    a ``str``, so the schema validator rejected the call. The model's own repair attempt then
    MANGLED the JSON (it spliced the delimiters into a field value: ``"type": "paragraph\\"}],book_id:"``)
    and dropped `chapter_id`, and the blank-args breaker stopped the turn. Net effect: a chapter row
    with ZERO prose — the flagship's 5th artifact never landed, and a count-based check read the
    empty shell as "done".

    This is the 4th enumerated gemma arg-mistranscription class, after the ``{"args": {…}}`` envelope
    wrap and the ``[uuid]`` scalar list-wrap — and it gets the same deterministic repair at the same
    chokepoint.

    SAFE BY CONSTRUCTION: only touches a property the tool's schema declares as ``array``/``object``,
    and only when the value is a ``str`` that ``json.loads`` to *that declared type*. A param declared
    ``array`` can never legitimately hold a string, so this can never eat a real value; anything that
    does not parse, or parses to the wrong type, is left untouched for the validator to reject honestly.
    """
    if not isinstance(args_obj, dict):
        return args_obj
    props = (((tool_def or {}).get("function") or {}).get("parameters") or {}).get("properties") or {}
    if not isinstance(props, dict):
        return args_obj
    for key, val in list(args_obj.items()):
        if not isinstance(val, str):
            continue
        types = _declared_types(props.get(key))
        want = types & {"array", "object"}
        if not want or "string" in types:
            continue  # not a struct param (or legitimately string-able) — hands off
        s = val.strip()
        if not s or s[0] not in "[{":
            continue
        try:
            parsed = json.loads(s)
        except (ValueError, TypeError):
            continue  # not JSON — let the validator reject it honestly
        if (isinstance(parsed, list) and "array" in want) or (
            isinstance(parsed, dict) and "object" in want
        ):
            args_obj[key] = parsed
    return args_obj


def _crosswired_ids(
    key: str, *, book_id: str | None, chapter_id: str | None, project_id: str | None,
) -> frozenset[str]:
    """D-FJ-20 — the OTHER context-ids of this turn, any of which in `key` is a cross-wiring.

    Returns the turn's own ids EXCEPT the one that belongs in `key`, so an exact match means
    the model swapped two ids the server is already holding. Deliberately not a similarity
    check: only an id the server itself supplied can be identified this way, which is what
    makes the substitution safe without knowing the surface.
    """
    known = {"book_id": book_id, "chapter_id": chapter_id, "project_id": project_id}
    return frozenset(
        str(v) for k, v in known.items() if v and k != key and str(v) != str(known.get(key) or "")
    )


def _inject_context_ids(
    args_obj: dict,
    tool_def: dict | None,
    *,
    book_id: str | None,
    chapter_id: str | None,
    project_id: str | None,
    studio: bool = False,
    id_ledger=None,
) -> dict:
    """S02 fix — fill known session context-ids into a backend tool's args when the tool's
    schema ACCEPTS them and the model OMITTED them.

    Measured live blocker (S02 baseline, gemma-4-26b): the book_id is surfaced to the model
    only as a prose system note, so a mid-tier model calls glossary_*/kg_* with ``{}`` →
    ``VALIDATION: missing book_id`` blind-retry loop. A strong model transcribes the UUID; a
    weak one can't. This deterministically supplies the id the SERVER already knows.

    Conservative by design: only fills a MISSING/blank arg (never overrides a VALID value the
    model supplied — respects a deliberate cross-book/other-id call), and ONLY for a key the
    tool declares in its schema (so a tool with ``additionalProperties: false`` is never handed
    an arg it would reject).

    ...with ONE exception, measured 2026-07-11 (S06): a mid-tier model cannot reliably
    TRANSCRIBE a UUID. gemma called glossary_propose_entities with
    ``book_id="019f5239-…-edd7176d056e6"`` — the turn's real book id with one extra character —
    and the tool 400'd ``book_id must be a UUID``. It then repeated the same corruption on a
    later turn. (Same failure mode as its mangling of a 519-char confirm_token.)

    A MALFORMED value cannot be a deliberate cross-book call: a real id is a UUID. So when the
    model supplies something that is not a UUID and the server knows the right one, the server's
    value wins. A valid-but-different UUID is still honored — that IS a deliberate cross-book
    call, and this must not silently redirect it."""
    if not isinstance(args_obj, dict) or not tool_def:
        return args_obj
    fn = tool_def.get("function", {}) if isinstance(tool_def, dict) else {}
    params = fn.get("parameters", {})
    props = params.get("properties", {}) if isinstance(params, dict) else {}
    if not props:
        return args_obj
    # Studio context binding (spec 2026-07-22): an `ambient_book` tool resolves book_id from the
    # envelope (X-Book-Id) server-side. Do NOT backfill book_id as an arg for it — that would pre-empt
    # the envelope (the effect would read scope_source="arg", and book_id could never be dropped from
    # the schema). chapter_id/project_id still backfill (not ambient); non-ambient tools still get book_id.
    _meta = fn.get("_meta") or {}
    ambient_book = bool(_meta.get("ambient_book"))
    ambient_project = bool(_meta.get("ambient_project"))  # composition: resolve project_id from X-Project-Id
    # D-THE-RUNTIME-INJECTS-THE-ARG-THAT-SWITCHES-THE-MODE and
    # D-THE-AMBIENT-PROJECT-IS-THE-WRONG-WORK-AND-THE-RUNTIME-SUPPLIES-IT — arguments a tool
    # declares this backfiller must LEAVE ALONE. This whole function rests on an assumption that is true of almost every tool
    # and not of all of them: that a context id merely SCOPES the call, so supplying one the
    # model forgot can only help. For a tool where the id selects a different code path, filling
    # it changes what the tool DOES, and the model cannot undo it.
    #
    # Measured 2026-08-24 on composition_motif_link_edit, whose `book_id` switches it from "link
    # two motifs you own" to "link two motifs SHARED into that book": the model omitted it, this
    # function put it back, the tool refused because the caller's private motifs are not shared,
    # and its refusal said to call again WITHOUT book_id. The model did exactly that — and the
    # id was injected again. Both runs then died on the repeat-breaker. The remedy a refusal
    # names has to be reachable, or it is worse than no remedy at all.
    _mode_args = _meta.get("no_context_fill")
    _no_fill = {a for a in _mode_args if isinstance(a, str)} if isinstance(
        _mode_args, (list, tuple)) else set()
    for key, val in (("book_id", book_id), ("chapter_id", chapter_id), ("project_id", project_id)):
        if key in _no_fill:
            # The tool declares this argument mode-selecting: absent means something. Never
            # supply it, and never correct one the model supplied — both are the model's call.
            continue
        if key == "book_id" and ambient_book:
            # ambient_book: book_id resolves from X-Book-Id server-side; the model shouldn't
            # pass it. But a weak model DOES — and on a studio turn it invents a well-formed
            # WRONG one. The studio is single-book by design (one book/Work at a time), so a
            # supplied book_id that differs from the studio's book is a hallucination: DROP it
            # so the envelope's ambient book wins, instead of leaving the wrong arg to be
            # honored by resolve_book_scope (valid-arg-wins). Match → harmless, leave as-is.
            _sup = args_obj.get(key)
            if studio and val and _sup and isinstance(_sup, str) and _sup != str(val):
                logger.warning(
                    "ambient_book tool got book_id=%r != the studio's book %s — dropping it "
                    "(the studio works one book at a time)", _sup[:64], str(val),
                )
                args_obj.pop(key, None)
            continue
        if key == "project_id" and ambient_project:
            continue
        if key not in props:
            continue
        if not val:
            # 🔴 NO SUBSTITUTE IS NOT THE SAME AS NO KNOWLEDGE. This used to `continue` on a
            # missing context value, which silently skipped the cross-wire check below — so a
            # value the ledger KNEW was the wrong kind of id was forwarded untouched, and the
            # model got back an opaque "not found or not accessible" for a call the runtime had
            # already recognised as mis-wired.
            #
            # MEASURED 2026-08-24 (batch c-override9, K=5): the turn carries no project_id (it is
            # populated only on studio/editor turns), the model sent
            # composition_list_derivatives{project_id: <this turn's BOOK id>}, and
            # `is_crosswired("project_id", book_id)` returns True — checked directly against the
            # deployed function. The correction could not run for want of a value to put in, and
            # the wrong one went out anyway.
            #
            # The runtime must not SEND an argument it knows is wrong. Dropping it makes the
            # tool's own missing-argument refusal fire instead, which names the declared supplier
            # and arms it — a path that already works — rather than an opaque domain 404. The
            # evidence standard is unchanged and deliberately high: `is_crosswired` is true only
            # for an id THIS TURN published under a DIFFERENT name, which is the same standard the
            # branch below already treats as sufficient to OVERWRITE a value.
            _sup = args_obj.get(key)
            if not (isinstance(_sup, str) and id_ledger is not None
                    and id_ledger.is_crosswired(key, _sup)):
                continue
            # 🔴 NARROWED AFTER A MEASURED SIDE EFFECT. Dropping is only better than forwarding
            # when the refusal that follows can NAME A SUPPLIER — that was the whole argument for
            # it. Where the tool declares no emitter for this argument, the model gets "missing
            # required argument(s)" with nowhere to go, and blank-retries into the breaker.
            #
            # MEASURED 2026-08-24, batch c-override11: composition_list_outline declares no
            # emitter for project_id, its project_id was dropped, and the run looped on
            # "keeps being called with missing/blank required arguments" — a worse failure than
            # the opaque 404 it replaced. composition_entity_override_edit DOES declare
            # project_id <- composition_list_derivatives, and there the drop is exactly right.
            try:
                from app.agentruntime.toolcontract import declared_emitter
                _has_supplier = bool(declared_emitter(
                    _tool_contract_registry(), fn.get("name") or "", key))
            except Exception:  # noqa: BLE001 — a contract lookup must never take the turn down
                _has_supplier = False
            if not _has_supplier:
                logger.info(
                    "tool arg %s=%r is cross-wired (%s) but %s declares no emitter for it — "
                    "forwarding as-is rather than dropping, because the refusal would name "
                    "nowhere to go", key, _sup[:64], id_ledger.describe(_sup),
                    fn.get("name"),
                )
                continue
            logger.warning(
                "tool arg %s=%r is another of this turn's context-ids (%s) and there is no "
                "%s to substitute — DROPPING it so the tool asks and its refusal names the "
                "emitter, rather than sending an id the runtime knows is the wrong kind",
                key, _sup[:64], id_ledger.describe(_sup), key,
            )
            args_obj.pop(key, None)
            continue
        # Coerce to str: `val` is a session context-id that can arrive as a UUID OBJECT
        # (asyncpg returns a uuid column as `uuid.UUID`, e.g. session_row["project_id"]),
        # and `args_obj` is JSON-serialized twice downstream — once onto the MCP wire and
        # again into `tool_calls_history` at terminal-persist. A raw UUID there raises
        # `TypeError: Object of type UUID is not JSON serializable`, which crashed the WHOLE
        # turn with a 500 (found live 2026-07-25: model mistranscribed project_id → this
        # branch substituted the UUID object → persist blew up). Every id here is a string
        # identifier by contract, so str() is both safe and required.
        val_s = str(val)
        supplied = args_obj.get(key)
        if not supplied:
            args_obj[key] = val_s
            continue
        if isinstance(supplied, str) and not _is_uuid(supplied):
            logger.warning(
                "tool arg %s=%r is not a UUID — the model mistranscribed it; substituting the "
                "turn's known id", key, supplied[:64],
            )
            args_obj[key] = val_s
        elif isinstance(supplied, str) and (
            supplied in _crosswired_ids(
                key, book_id=book_id, chapter_id=chapter_id, project_id=project_id,
            )
            # D-XWIRE-RESULT (2026-08-14) — the same cross-wire, but the offending id came from a
            # TOOL RESULT rather than from the request envelope, so D-FJ-20's three-id evidence
            # base could not see it. Measured 3/3: `book_list {kind:"chapters"}` returned
            # `chapter_id: X`, the model then sent `book_chapter_create {book_id: X}`, and the
            # refusal "book not accessible" gave it nothing to correct — it retried the identical
            # call and then wandered into an unrelated book of the user's looking for one that
            # would accept the write. The certainty standard is unchanged: only an id THIS
            # PLATFORM published under a different name, never a guess at an unknown UUID.
            or (id_ledger is not None and id_ledger.is_crosswired(key, supplied))
        ):
            # D-FJ-20 — the model put ANOTHER of this turn's own context-ids in this slot.
            # Not a cross-book call and not a hallucination: a demonstrable cross-wiring of
            # two ids the server is holding for this very turn, so it needs no policy
            # judgement and no surface gate.
            #
            # MEASURED LIVE 2026-08-13 (session 019ff929, EDITOR surface, book 019ff8f5-ae59):
            # the rail drove plan_propose_spec four times, every call carrying
            # book_id="019ff8f5-ee89-75ef-a894-ff9462332bc0" — the CHAPTER open in the editor,
            # confirmed as a row in that book's chapters table. Every call was refused "not
            # found or not accessible", the rail re-drove to its cap, and the author's actual
            # question was answered three times over with the same stale apology.
            #
            # The studio branch below already fixes this exact shape (it names
            # plan_propose_spec) but is STUDIO-SCOPED, because off a studio turn a
            # valid-but-different book_id may be a real cross-book call. That reasoning does
            # not reach here: a value that IS the turn's chapter_id cannot be a book id, on
            # any surface. Kept deliberately narrow — only an exact match against another id
            # the server already knows, never a guess.
            logger.warning(
                "tool arg %s=%r is another of this turn's context-ids (cross-wired) — "
                "substituting the turn's %s", key, supplied[:64], key,
            )
            args_obj[key] = val_s
        elif (
            key == "book_id"
            and studio
            and isinstance(supplied, str)
            and _is_uuid(supplied)
            and supplied != val_s
        ):
            # Studio single-book override (2026-07-25, user decision): a book-scoped tool that
            # is NOT ambient_book (e.g. plan_propose_spec) still requires book_id, and the studio
            # prompt tells the model NOT to pass one — so a weak model invents a VALID-but-WRONG
            # book_id, which _gate then refuses as "not found or not accessible". The writing
            # studio works one book/Work at a time by design, so a book_id that differs from the
            # studio's book is a hallucination, not a deliberate cross-book call: override it to
            # the studio's book (with a warning). This override is STUDIO-SCOPED — off a studio
            # turn a valid-but-different book_id is still honored as a real cross-book call.
            logger.warning(
                "tool arg book_id=%r differs from the studio's book %s — overriding "
                "(the studio works one book at a time; a cross-book target here is a hallucination)",
                supplied[:64], val_s,
            )
            args_obj[key] = val_s
    _drop_crosswired_foreign_ids(
        args_obj, fn, props, _no_fill,
        book_id=book_id, chapter_id=chapter_id, project_id=project_id, id_ledger=id_ledger,
    )
    return args_obj


def _drop_crosswired_foreign_ids(
    args_obj: dict, fn: dict, props: dict, no_fill: set, *,
    book_id: str | None, chapter_id: str | None, project_id: str | None, id_ledger=None,
) -> None:
    """The same cross-wire check, for id arguments that are NOT named book/chapter/project.

    🔴 THE LOOP ABOVE ITERATES OVER EXACTLY THREE ARGUMENT NAMES, so a context-id landing in an
    argument called anything else was never examined at all. The mechanism was not weak here —
    it was ABSENT, and the absence is invisible because the three names cover most tools.

    MEASURED 2026-08-24, composition_authoring_run_manage, K=2 and again in the batch before it:
    the model sent `plan_run_id` = the turn's CHAPTER id. Checked against the deployed function,
    `_inject_context_ids` returned it untouched. A durable gate task was then minted for a run
    the platform already had the evidence to know was unbuildable, the author was shown a card,
    and approving it produced a bare `400 {"code":"action_error"}` — LookupError("plan run not
    found") with the message discarded. Approve-then-fail on a cost-bearing tool, which is the
    same shape D-UNDECLARED-REF filed for composition_generate's model_ref.

    Deliberately the NARROW half of the rule above, and nothing more:
      * only arguments whose name ends in `_id`, so a prose field that happens to hold a UUID
        is never touched;
      * only an EXACT match against an id this turn published under a different name — the
        `_crosswired_ids` / `is_crosswired` standard, never a similarity guess;
      * only where the tool DECLARES AN EMITTER for that argument, because the whole case for
        dropping is that the refusal which follows can name where to get the real value. Where
        it cannot, forwarding an id known to be wrong is still the lesser failure (measured:
        c-override11, where a drop with nowhere to go blank-retried into the breaker);
      * DROP only, never substitute. The correct value is not a context id, so the server has
        nothing to put in its place and must not invent one.
    """
    for key in list(args_obj):
        if key in ("book_id", "chapter_id", "project_id") or key in no_fill:
            continue
        if not key.endswith("_id") or key not in props:
            continue
        supplied = args_obj.get(key)
        if not isinstance(supplied, str) or not supplied:
            continue
        crosswired = supplied in _crosswired_ids(
            key, book_id=book_id, chapter_id=chapter_id, project_id=project_id,
        ) or (id_ledger is not None and id_ledger.is_crosswired(key, supplied))
        if not crosswired:
            continue
        try:
            from app.agentruntime.toolcontract import declared_emitter
            emitter = declared_emitter(_tool_contract_registry(), fn.get("name") or "", key)
        except Exception:  # noqa: BLE001 — a contract lookup must never take the turn down
            emitter = None
        if not emitter:
            logger.info(
                "tool arg %s=%r is cross-wired but %s declares no emitter for it — forwarding "
                "as-is rather than dropping, because the refusal would name nowhere to go",
                key, supplied[:64], fn.get("name"),
            )
            continue
        logger.warning(
            "tool arg %s=%r is another of this turn's context-ids (cross-wired) and %s is not "
            "a context id the server holds — DROPPING it so the tool's own refusal names %s, "
            "rather than minting a card for a call that cannot succeed",
            key, supplied[:64], key, emitter,
        )
        args_obj.pop(key, None)


def _repair_saved_book_id(
    args_obj: object, *, book_id: str | None, studio: bool
) -> object:
    """The `_inject_context_ids` repairs that survive a SUSPEND — applied to the args a
    Tier-A card was approved on, just before the approved dispatch.

    Deliberately narrower than `_inject_context_ids`: the tool's SCHEMA is not available at
    the resume dispatch (`tool_defs` is built further down, after this call), so this only ever
    ADJUSTS a `book_id` the saved args already carry and NEVER adds one. That is the whole
    difference that matters — adding an undeclared arg needs the schema, correcting a present
    one does not.

    Two rules, both lifted verbatim from `_inject_context_ids`:
      * a MALFORMED book_id is a mistranscription, never a deliberate cross-book call;
      * on a STUDIO turn a valid-but-DIFFERENT book_id is a hallucination (the studio works one
        book at a time). Off a studio turn it is honored, exactly as on the streaming path.

    For an `ambient_book` tool the streaming path DROPS a mismatched book_id so the envelope's
    ambient book wins; setting it to the studio's book here is the same outcome by a different
    route, since the envelope carries that same book.
    """
    if not isinstance(args_obj, dict) or not book_id:
        return args_obj
    supplied = args_obj.get("book_id")
    if not supplied or not isinstance(supplied, str):
        return args_obj
    val_s = str(book_id)
    if not _is_uuid(supplied):
        logger.warning(
            "approved tool arg book_id=%r is not a UUID — substituting the suspend's book %s",
            supplied[:64], val_s,
        )
        args_obj["book_id"] = val_s
    elif studio and supplied != val_s:
        logger.warning(
            "approved tool arg book_id=%r differs from the studio's book %s — overriding "
            "(the repair fired before the suspend and was never persisted)",
            supplied[:64], val_s,
        )
        args_obj["book_id"] = val_s
    return args_obj


def _is_uuid(v: str) -> bool:
    try:
        UUID(str(v))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


#: CP-5.3 — the ref/resolver map, loaded once from its registry row.
#:
#: The loader lives HERE rather than in `app.agentruntime.refresolve` because that package may
#: import only stdlib and itself (the membrane gate), and reading a repo path is a boundary
#: concern. `refresolve` stays a pure decision module; this side does the I/O.
#: 🔴 **A DICT RATHER THAN TWO MODULE GLOBALS, AND CP-0'S F-50 GUARD IS WHY.** The first version
#: declared `global _REF_REGISTRY, _REF_REGISTRY_LOADED` and then read the flag in an early-return
#: branch ABOVE the assignment. Python is fine with that — they are module-level — but the guard
#: reads the SHAPE, and the shape is the one that produced F-50: a value read on a path that
#: returns before it is bound. Mutating a dict needs no `global`, so the early read is a plain
#: lookup and the shape is gone rather than argued with.
_REF_REGISTRY_CACHE: dict[str, tuple[dict, dict]] = {}
_VOCAB_REGISTRY_CACHE: dict[str, tuple[dict, dict]] = {}


#: CP-5.4 — the tool-contract registry, read once. Same posture as the ref registry: an absent file
#: is a legitimate empty state (no tool declares a supplier, so every message reads as it did
#: before), and a broken PROGRAM is never absorbed as a bad file.
_TOOL_CONTRACT_CACHE: dict[str, dict] = {}


def _tool_contract_registry() -> dict:
    cached = _TOOL_CONTRACT_CACHE.get("value")
    if cached is not None:
        return cached
    doc: dict = {}
    try:
        from app.agentruntime.manifest import manifest_path
        from app.agentruntime.toolcontract import CONTRACT_REGISTRY_FILENAME

        mpath = manifest_path()
        path = (mpath.parent / CONTRACT_REGISTRY_FILENAME) if mpath is not None else None
        if path is not None and path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
    except (NameError, AttributeError, ImportError):
        raise
    except Exception as exc:
        logger.warning("CP-5.4: tool-contract registry not loaded (%s)", exc)
    _TOOL_CONTRACT_CACHE["value"] = doc
    return doc


def _vocab_registry(lane_of) -> tuple[dict, dict]:
    """`(vocabularies, bindings)`, or two empty dicts — CP-6.1, mirroring `_ref_registry` exactly.

    Same posture and for the same reasons: `lane_of` comes from the turn because the catalogue is
    per-request; a source that cannot be shown to be `lane=read` fails closed, since enumerating a
    vocabulary dispatches a tool the user never asked for; a FAILED load is not cached (one unlucky
    turn must not make the mechanism inert for the whole process); and `NameError`/`AttributeError`/
    `ImportError` re-raise, because those are bugs and swallowing one hid a mechanism that had never
    run once.
    """
    cached = _VOCAB_REGISTRY_CACHE.get("value")
    if cached is not None:
        return cached
    loaded: tuple[dict, dict] = ({}, {})
    cacheable = True
    try:
        from app.agentruntime.manifest import manifest_path
        from app.agentruntime.vocabulary import (
            VOCABULARY_REGISTRY_FILENAME, load_registry as _load_vocab,
        )

        mpath = manifest_path()
        path = (mpath.parent / VOCABULARY_REGISTRY_FILENAME) if mpath is not None else None
        if path is not None and path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
            vocabs, bindings = _load_vocab(doc, lane_of)
            logger.info("CP-6.1: %d vocabular(ies), %d bound parameter(s)",
                        len(vocabs), len(bindings))
            loaded = (vocabs, bindings)
        else:
            logger.info("CP-6.1: no vocabulary registry beside the manifest — the check is inert")
    except (NameError, AttributeError, ImportError):
        raise
    except Exception as exc:
        cacheable = False
        logger.warning("CP-6.1: vocabulary registry not loaded (%s) — inert for THIS TURN", exc)
    if cacheable:
        _VOCAB_REGISTRY_CACHE["value"] = loaded
    return loaded


def _ref_registry(lane_of) -> tuple[dict, dict]:
    """`(resolvers, bindings)`, or two empty dicts.

    `lane_of` maps a TOOL NAME to its lane and is supplied by the turn, because the catalogue is
    per-request — and the lane is not decoration here: `check_resolver` refuses a resolver that is
    not `lane=read`, since resolution dispatches it **without the user asking**.

    **An absent or unloadable registry is a legitimate empty state, not a failure**: it means no
    ref type is declared, so nothing resolves and every call behaves exactly as it does today. A
    resolution layer that could break tool calling by being misconfigured would be a worse defect
    than the one it fixes.
    """
    cached = _REF_REGISTRY_CACHE.get("value")
    if cached is not None:
        return cached
    loaded: tuple[dict, dict] = ({}, {})
    #: 🔴 **A FAILED LOAD IS NOT CACHED, AND THE REASON IS THE LANE LOOKUP.** `lane_of` reads the
    #: TURN's catalogue index, so a first turn whose discovery set happens not to contain
    #: `glossary_search` cannot determine the resolver's lane — `check_resolver` then fails closed,
    #: correctly. Caching that would make resolution inert for the whole PROCESS on the strength of
    #: one unlucky turn. Only a settled answer is cached: a successful load, or a registry that is
    #: genuinely absent.
    cacheable = True
    try:
        from app.agentruntime.manifest import manifest_path
        from app.agentruntime.refresolve import REF_REGISTRY_FILENAME, load_registry

        mpath = manifest_path()
        path = (mpath.parent / REF_REGISTRY_FILENAME) if mpath is not None else None
        if path is not None and path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
            resolvers, bindings = load_registry(doc, lane_of)
            logger.info("CP-5.3: %d ref type(s), %d bound parameter(s)",
                        len(resolvers), len(bindings))
            loaded = (resolvers, bindings)
        else:
            logger.info("CP-5.3: no ref registry beside the manifest — resolution is inert")
    except (NameError, AttributeError, ImportError):
        # 🔴 **THESE ARE BUGS, NOT MISCONFIGURATION, AND SWALLOWING THEM HID A MECHANISM THAT HAD
        # NEVER RUN ONCE.** The first version caught bare `Exception`, and `declared_lane` was
        # never imported into this module — so every process logged one warning and resolution was
        # inert, with the whole suite green. It was found only by a served turn that sent the
        # failing shape and got `entity_id must be a UUID` back with `resolution: null`.
        #
        # A degrade path may absorb a bad FILE. It may not absorb a broken PROGRAM: the two look
        # identical in a log line and could not be more different.
        raise
    except Exception as exc:
        # A malformed or unreadable registry is LOUD in the log and inert at runtime — that is a
        # deliberate posture: a resolution layer that could break tool calling by being
        # misconfigured would be a worse defect than the one it fixes. It is never a silent
        # partial load: `load_registry` refuses the whole document rather than dropping a row,
        # because a dropped resolver leaves its binding in place and never resolving.
        cacheable = False
        logger.warning("CP-5.3: ref registry not loaded (%s) — resolution is inert for THIS TURN; "
                       "it will be retried on the next one", exc)
    if cacheable:
        _REF_REGISTRY_CACHE["value"] = loaded
    return loaded


def _missing_required_names(args_obj: dict, tool_def: dict | None) -> list[str]:
    """The REQUIRED arg names this call is still missing (post context-id injection).
    Unknown tool_def → [] (can't classify → never block a call we can't judge).

    🔴 THIS USED TO BE `not args_obj.get(r)` — A TRUTHINESS TEST WHERE PRESENCE WAS MEANT.

    Measured 2026-08-22 through the real chat path. `settings_model_set_favorite` was asked to
    UNFAVOURITE a model; the model sent `{"user_model_id": "…", "value": false}` — exactly right —
    and this returned `["value"]`, because `not False` is `True`. The repair message then told the
    model to supply the argument it had just supplied, it retried identically, and the blank-args
    cap stopped the turn. On one such turn the model went on to tell the author *"I've deactivated
    Nemotron-3 Nano for you"*: a false claim of a write, caused by a check that threw away the
    correct answer.

    It took a control to see. The obvious reading was that the model omits the boolean when the
    answer is false — "mark as a favourite" (true) passed while "deactivate" and "turn off" (false)
    failed. The RECORDED ARGUMENTS refuted it: the value was always there.

    Swept across the live catalogue, 37 required arguments on 36 tools can legitimately be falsy —
    6 booleans (`false` unreachable), 10 integers (`unit_index: 0` is the FIRST unit), 2 numbers
    (`world_map_add_marker.x: 0` is the left edge of the map), and 19 arrays (`chapters: []` is the
    empty-import case). None of them could be expressed through chat.

    THE RULE NOW: an argument that was SENT is present, whatever its value. Absent or `None` is
    missing. The one exception is the reason this check existed — a required STRING that is empty
    or whitespace really is blank, and catching that is what the blank-args cap is for. It also
    now catches whitespace, which the truthiness version let through.
    """
    if not tool_def:
        return []
    params = tool_def.get("function", {}).get("parameters", {})
    required = params.get("required", []) if isinstance(params, dict) else []
    missing = []
    for r in required:
        if r not in args_obj or args_obj[r] is None:
            missing.append(r)
        elif isinstance(args_obj[r], str) and not args_obj[r].strip():
            missing.append(r)
    return missing


def _missing_required_args(args_obj: dict, tool_def: dict | None) -> bool:
    """True iff this call is still missing a REQUIRED arg (post context-id injection).

    Used to keep the blank-tool-args cap from collateral-damaging a WELL-FORMED call: a
    mid-tier model that spams one malformed tool (e.g. glossary_search without `query`)
    builds the streak, and the cap would then block a DIFFERENT, valid call (e.g.
    glossary_book_ontology_read with book_id present) that would actually succeed. Only a
    call that is ITSELF still missing required args should be short-circuited."""
    return bool(_missing_required_names(args_obj, tool_def))


def _flat_declared_types(spec: dict) -> list | None:
    """The concrete JSON types a property may hold, flattening ONE union level.

    Shared by the two container/type repairs below so they cannot drift apart. Returns None when
    the schema is richer than a flat type set (`items`, `$ref`, `allOf`, nested unions) — the
    caller must then DECLINE rather than guess, which is the safety property both repairs rest on.
    """
    branches = spec.get("anyOf") or spec.get("oneOf")
    if branches is not None:
        if not isinstance(branches, list) or not branches:
            return None
        if not all(isinstance(b, dict) for b in branches):
            return None
        if any("items" in b or "$ref" in b or "anyOf" in b or "oneOf" in b for b in branches):
            return None
        return [t for b in branches for t in (
            b.get("type") if isinstance(b.get("type"), list) else [b.get("type")])]
    if any(k in spec for k in ("items", "allOf", "$ref")):
        return None
    declared = spec.get("type")
    return declared if isinstance(declared, list) else [declared]


_FIELD_PREFIXED_ID = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):([0-9a-fA-F-]{36})$")


def _strip_field_name_prefix_from_ids(args_obj: dict, tool_def: dict | None) -> list[str]:
    """Repair `"user_model_id:019e7f71-…"` -> `"019e7f71-…"` for a string-only param.

    🔴 MEASURED LIVE 2026-08-13 (cycle 5, kg_build's blocker). kg_project_set_embedding_model was
    called with embedding_model="user_model_id:019e7f71-0271-722f-9c9c-3f049c0b26f4" and refused
    "invalid model_ref". CONTROL: the same id WITHOUT the prefix is accepted.

    THE ROOT IS NOT A HALLUCINATION, which is why this is repairable rather than a message problem.
    `settings_list_models` — the tool the refusal itself points the caller to — returns each model as
    an object whose id sits under the KEY `user_model_id`:
    `{..., "user_model_id": "019ebb72-…", "provider_model_name": …}`. The model read the field name
    and emitted KEY:VALUE. The id it needed was present and correct; it serialised the pair.

    Fifth in the argument-form family, same decline-when-uncertain discipline. The condition is
    deliberately tight, because a colon is ordinary punctuation in prose:

    * the value must be EXACTLY `<bare_identifier>:<uuid>` — a title, a URL, "chapter 3: the flood"
      and any prefix that is not an identifier all fail the pattern;
    * the remainder must parse as a UUID, so nothing is stripped off a value whose tail is free text;
    * the param must declare string-only (a param that also accepts an object is not this mistake).
    """
    if not isinstance(args_obj, dict) or not tool_def:
        return []
    params = (tool_def.get("function") or {}).get("parameters") or {}
    props = params.get("properties") if isinstance(params, dict) else None
    if not isinstance(props, dict):
        return []
    deprefixed: list[str] = []
    for name, value in list(args_obj.items()):
        if not isinstance(value, str):
            continue
        m = _FIELD_PREFIXED_ID.match(value.strip())
        if not m or not _is_uuid(m.group(2)):
            continue
        spec = props.get(name)
        if type(spec) is not dict:
            continue
        kinds = _flat_declared_types(spec)
        if kinds is None:
            continue
        real = [t for t in kinds if t != "null"]
        if not real or any(t != "string" for t in real):
            continue
        args_obj[name] = m.group(2)
        deprefixed.append(name)
    return deprefixed


def _unwrap_object_items_for_string_array(args_obj: dict, tool_def: dict | None) -> list[str]:
    """Repair `entity_ids: [{"entity_id": "<uuid>", "status": "active"}]` -> `["<uuid>"]`.

    🔴 MEASURED LIVE 2026-08-12 (journey `entity-triage`, book 019ff4cf) and reproduced deliberately
    on 2026-08-13: glossary_propose_curation was called with op='status_change', status='active' and
    `entity_ids` holding OBJECTS where the schema declares an array of STRINGS, each object
    re-stating the `status` that was already a sibling argument. The validator refuses it before the
    tool runs, and the journey ended with all 11 entities still `draft`.

    Third in the same family, and the safety discipline is the same as its two siblings — a wrong
    unwrap CORRUPTS a write rather than refusing it, so every uncertain shape is DECLINED:

    * the param must declare `type: array` with `items.type` exactly `string` (one union level
      flattened); anything richer is declined;
    * EVERY element must be an object — a mixed list is a shape this rule cannot reason about;
    * each object must carry the parameter's SINGULAR key (`entity_ids` -> `entity_id`) holding a
      non-empty string; no singular key, no repair;
    * 🔴 and an object key that ALSO exists as a top-level sibling argument must AGREE with it. The
      measured payload repeated `status: "active"` next to the sibling `status: "active"` — harmless
      redundancy. A DISAGREEMENT is a real ambiguity about which value the caller meant, and
      dropping the object's copy would silently pick one. Decline instead.
    """
    if not isinstance(args_obj, dict) or not tool_def:
        return []
    params = (tool_def.get("function") or {}).get("parameters") or {}
    props = params.get("properties") if isinstance(params, dict) else None
    if not isinstance(props, dict):
        return []
    fixed: list[str] = []
    for name, value in list(args_obj.items()):
        if not isinstance(value, list) or not value:
            continue
        if not all(isinstance(el, dict) for el in value):
            continue
        spec = props.get(name)
        if type(spec) is not dict:  # shape varies from the sibling repairs ON PURPOSE — identical
            continue                # bodies make a registered falsifier's anchor match twice
        # NOT `_flat_declared_types`: that helper vetoes any schema carrying `items`, which is
        # right for its two SCALAR callers and exactly backwards here — `items` is the thing this
        # rule needs to read. A union (anyOf/oneOf) around an array is declined outright rather
        # than flattened, because the branch that matched is then a guess.
        if spec.get("anyOf") or spec.get("oneOf") or "$ref" in spec or "allOf" in spec:
            continue
        declared = spec.get("type")
        declared_list = declared if type(declared) is list else [declared]
        if "array" not in [t for t in declared_list if t]:
            continue
        items = spec.get("items")
        if not isinstance(items, dict) or items.get("type") != "string":
            continue
        singular = name[:-1] if name.endswith("s") else ""
        if not singular:
            continue
        picked: list[str] = []
        for el in value:
            inner = el.get(singular)
            if not isinstance(inner, str) or not inner.strip():
                picked = []
                break
            # A key that restates a sibling must AGREE with it; a contradiction is ambiguity.
            if any(k in args_obj and k != name and args_obj[k] != v for k, v in el.items()):
                picked = []
                break
            picked.append(inner)
        if not picked:
            continue
        args_obj[name] = picked
        fixed.append(name)
    return fixed


def _stringify_int_args_declared_string(args_obj: dict, tool_def: dict | None) -> list[str]:
    """Repair `chapter: 1` → `chapter: "1"` for a param the schema declares STRING-only.

    🔴 MEASURED LIVE. book_chapter_save_draft declares `chapter` as a string whose OWN description
    says to pass "its NUMBER (e.g. '1', 'chapter 3')" — so the model reads "number", sends the JSON
    number 1, and the gateway rejects the call before the tool ever sees it:
    *validating /properties/chapter: type: 1 has type "integer", want "string"*. Recorded on
    2026-08-04 and again on 2026-08-12, i.e. it recurs; the 2026-08-12 instance came one step after
    the same turn had finally supplied the prose, so the write was blocked on the container of a
    value that was already correct. Same family as D-FJ-7 (the value is right, its TYPE is wrong)
    and repaired with the same discipline.

    DELIBERATELY NARROW, because a wrong coercion corrupts a write rather than refusing it:

    * only when EVERY non-null declared type is `string` — a param that also accepts `integer` is
      not confused, it is being given a legal value;
    * `bool` is declined even though Python calls it an int: `True` -> "True" is a guess about
      intent, not a container slip;
    * `float` is declined: 1.0 -> "1.0" is lossy and ambiguous against a selector like "1";
    * a schema richer than a flat type set is declined outright (see `_flat_declared_types`).
    """
    if not isinstance(args_obj, dict) or not tool_def:
        return []
    params = (tool_def.get("function") or {}).get("parameters") or {}
    props = params.get("properties") if isinstance(params, dict) else None
    if not isinstance(props, dict):
        return []
    coerced: list[str] = []
    for name, value in list(args_obj.items()):
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        spec = props.get(name)
        if type(spec) is not dict:  # shape differs from the sibling ON PURPOSE: identical bodies
            continue                # made a registered falsifier's anchor match twice
        types = _flat_declared_types(spec)
        if types is None:
            continue
        concrete = [t for t in types if t != "null"]
        if not concrete or any(t != "string" for t in concrete):
            continue
        args_obj[name] = str(value)
        coerced.append(name)
    return coerced


def _unwrap_single_element_scalar_args(args_obj: dict, tool_def: dict | None) -> list[str]:
    """Repair `["vi"]` → `"vi"` for a param the schema declares SCALAR. Returns the names repaired.

    🔴 MEASURED LIVE 2026-08-12, journey `translation-pass` (book 019f9a02-f3a3…). The model called
    translation_start_job with `target_language: ["vi"]` and was refused: *"Input should be 'en',
    'vi', … (you sent ['vi'])"*. The refusal is exemplary — it names the legal set AND what was sent
    — and the turn still ended there with the journey unfinished. This is the *typed params* class,
    16.8% of the recorded failure corpus, and a one-element list where a scalar is declared is the
    most mechanical shape in it: the value is already correct, only its container is wrong.

    THE GUARD IS THE WHOLE POINT, because unwrapping the wrong param would silently corrupt a call
    rather than fail it. A param is repaired ONLY when the schema says it cannot be an array:

    * `type` may be a UNION LIST (`["null", "array"]`), so an array member anywhere disqualifies it —
      testing `type != "array"` alone would unwrap a legitimately-list-typed argument.
    * `items`, `anyOf`, `oneOf` and `$ref` mean the schema is richer than this repair can reason
      about, so it declines rather than guesses.
    * A list of length != 1 is never touched: `[]` and `["vi","en"]` are real disagreements about
      cardinality, not a container slip, and they must still reach the refusal.
    """
    if not isinstance(args_obj, dict) or not tool_def:
        return []
    params = (tool_def.get("function") or {}).get("parameters") or {}
    props = params.get("properties") if isinstance(params, dict) else None
    if not isinstance(props, dict):
        return []
    repaired: list[str] = []
    for name, value in list(args_obj.items()):
        if not isinstance(value, list) or len(value) != 1:
            continue
        spec = props.get(name)
        if not isinstance(spec, dict):
            continue
        # `anyOf`/`oneOf` is the SHAPE THE REAL CATALOGUE USES, not an exotic case: pydantic emits
        # `anyOf: [{enum, type: string}, {type: null}]` for every optional enum, which is what
        # translation_start_job.target_language actually declares. Declining all unions would have
        # left this repair unable to fire on the very call that motivated it — a fix that is
        # decoration. So flatten one level and require EVERY branch to be scalar-or-null: a union
        # with an array or object branch is still refused, which keeps the safety property intact.
        branches = spec.get("anyOf") or spec.get("oneOf")
        if branches is not None:
            if not isinstance(branches, list) or not branches:
                continue
            if not all(isinstance(b, dict) for b in branches):
                continue
            types = [t for b in branches for t in (
                b.get("type") if isinstance(b.get("type"), list) else [b.get("type")])]
            if any("items" in b or "$ref" in b or "anyOf" in b or "oneOf" in b for b in branches):
                continue
        else:
            if any(k in spec for k in ("items", "allOf", "$ref")):
                continue
            declared = spec.get("type")
            types = declared if isinstance(declared, list) else [declared]
        # "null" is permitted alongside a scalar (that IS the optional shape), but every remaining
        # member must be scalar and none may be an array.
        concrete = [t for t in types if t != "null"]
        if "array" in types or not concrete or not all(
            t in ("string", "integer", "number", "boolean") for t in concrete
        ):
            continue
        inner = value[0]
        if isinstance(inner, (dict, list)):
            continue
        args_obj[name] = inner
        repaired.append(name)
    return repaired


#: How many recovery tools one refusal may arm. A refusal names the one or two tools that unblock
#: it; a text that "names" more than this is almost certainly prose that happens to contain tool
#: names, and arming a handful of those would spend the surface budget the hot set needs.
_RECOVERY_ARM_CAP = 3


def _tools_named_in_refusal(
    error_text: str, catalog: dict, already_active, *, exclude: str | None = None,
) -> list[str]:
    """Catalogue tools a REFUSAL told the caller to use, and that it cannot currently see.

    🔴 **A REFUSAL THAT NAMES AN UNREACHABLE TOOL IS AN INSTRUCTION THE CALLER CANNOT FOLLOW.**
    Measured live 2026-08-12, journey `kg-build` (session 019ff498-7603…): kg_build refused with
    *"call kg_project_set_embedding_model first (pick one of your embedding models with
    settings_list_models)"*. Both tools are federated -- they are in the gateway's 315-tool list --
    but NEITHER was in that turn's advertised surface, which carried kg_build and not them. The
    model understood the requirement, wrote *"I'll get to work on setting that up now"* three
    times, never called either tool, retried kg_build unchanged, and ended by asking the author
    whether to keep trying. The project's embedding_model was NULL and the account owns an active
    embedding model, so the journey was satisfiable the whole time.

    This is the same decision the dispatch chokepoint already makes for an off-surface tool the
    model DID call ("making it round-trip through tool_list/tool_load to be told 'yes, that one' is
    ceremony a weak model fails") and that D-NARRATED-WRITE makes for a tool the model merely
    NAMED. A tool the RUNTIME named, in the sentence explaining how to proceed, is the strongest of
    the three cases and was the only one not covered.

    Whole-word matching, never substring: `kg_build` occurs inside `kg_build_wiki`, so a substring
    test would arm the wrong tool off its own refusal -- the `mrows.Err()`/`rows.Err()` shape that
    kept a guard green while the check it named was gone.

    🔴 **`exclude` IS THE TOOL THAT JUST FAILED, AND OMITTING IT ARMED THE FAILURE ITSELF.** Caught
    live 2026-08-22 by this function's own log line, on the first batch after the missing-argument
    arm was wired in:

        armed recovery tool(s) ['composition_arc_template_edit'] named in
        composition_arc_template_edit's missing-argument refusal

    Every refusal `_missing_args_message` builds OPENS with the failing tool's name — *"'x' is
    missing required argument(s)"* — so the tool is always a candidate against its own refusal.
    Arming it is not merely a no-op: candidates are ranked longest-name-first into a cap of 3, and a
    tool name is usually among the longest strings in its own refusal, so the failure reliably takes
    a top slot and can push out the supplier the sentence is actually steering toward. The
    instruction says *call world_map_list first*; the arming would spend a slot re-arming
    world_map_delete.

    Passing the failing tool here rather than relying on `already_active` is deliberate: a tool
    dispatched off-surface (the chokepoint one step below auto-loads a catalogue tool the model
    named) is NOT in the active set at the moment its refusal is read.
    """
    if not error_text or not catalog:
        return []
    found = [
        name for name in catalog
        if name not in already_active and name != exclude
        and re.search(rf"\b{re.escape(name)}\b", error_text)
    ]
    # Longest first: when a refusal names both `kg_build` and `kg_build_wiki`, the specific tool is
    # the one it is steering toward. Then a stable order so the armed set is reproducible.
    found.sort(key=lambda n: (-len(n), n))
    return sorted(found[:_RECOVERY_ARM_CAP])


def _arm_tools(
    names,
    *,
    active_tool_names: set,
    activation_state: dict | None,
    discovery_catalog,
    context_length,
) -> list[str]:
    """Put `names` on the wire for the rest of this turn. THE one place that does it.

    🔴 **THE MUTATION WAS COPIED THREE TIMES AND THE THIRD SITE WAS THE ONE THAT DID NOT EXIST.**
    `active_tool_names.update(...)` + `merge_activated_tools(...)` + `dirty = True` appeared
    verbatim under D-NARRATED-WRITE (a tool named in PROSE) and under D-FJ-4 (a tool named in a
    dispatch REFUSAL). The pre-dispatch missing-argument refusal — the largest refusal class on
    this platform, 266 failures over 87 sessions — `continue`s before either, so the sentence
    `_missing_args_message` writes ("call world_map_list first and match it to get the id") armed
    nothing at all. `_missing_args_message`'s own comment claimed otherwise: *"Naming it also ARMS
    it ... so one sentence fixes both the instruction and the reachability."* It did not.

    MEASURED 2026-08-22, 35 live runs over the 7 P3-NAME-TO-ID tools that have a supplier, reading
    `advertised` off each turn's own agentSurface event:

        supplier advertised & called          8
        supplier advertised & NOT called      0    <- the cell "the model will not walk it" needs
        NOT advertised & called               0
        NOT advertised & NOT called          27

    Agreement on 35 of 35 runs, no disagreements. The model walks a supplier chain exactly when it
    can see the supplier. `world_map_delete` was refused with *call world_map_list first*, that tool
    was advertised on 0 of 5 runs, and the turn ended "I'll find the ID for you now. One moment."
    — recorded until now as the model failing to keep its word.

    Returns what it actually armed (already-active names are not re-armed), so a caller can decide
    whether to say anything. It does NOT write the [SYSTEM] note: the three callers are telling the
    model three different things, and one shared sentence would be wrong for two of them.
    """
    from app.services.tool_surface import merge_activated_tools

    fresh = [n for n in names if n not in active_tool_names]
    if not fresh:
        return []
    active_tool_names.update(fresh)
    if activation_state is not None:
        activation_state["activated_tools"] = merge_activated_tools(
            activation_state["activated_tools"], fresh,
            catalog=discovery_catalog, context_length=context_length,
        )
        activation_state["dirty"] = True
    return fresh


#: The reserved all-zero UUID. Never a row in any table here, so an `*_id` argument carrying it is
#: an invention that happens to parse. Compared through UUID() rather than by string so the
#: braced/urn/uppercase spellings cannot slip past a literal match.
def _is_nil_uuid(value: str) -> bool:
    try:
        return UUID(value).int == 0
    except (ValueError, AttributeError, TypeError):
        return False


#: The hex alphabet, in order, for the sequential-run test below.
_HEX_ORDER = "0123456789abcdef"

#: A run of consecutive nibbles this long never occurs in an id this platform has ever issued.
#: MEASURED, not chosen: the longest sequential run across 38,314 distinct UUIDs read out of
#: every uuid column in all eight databases is SIX. Eight leaves a two-nibble margin.
_DEGENERATE_SEQ_RUN = 8


def _is_degenerate_uuid(value: str) -> bool:
    """A syntactically valid UUID that is RECOGNISABLY a placeholder.

    🔴 THE SAME SHAPE AS `_is_nil_uuid`, ONE STEP WIDER, AND MEASURED BEFORE IT SHIPPED.
    `_invented_supplier_ids` tests SYNTAX, so a model that invents a well-formed UUID walks
    straight through it. Measured live twice on different tools and different arguments:

        plan_bootstrap_apply   proposal_id=77777777-7777-7777-7777-777777777777   (2 of 5 runs)
        plan_bootstrap_apply   proposal_id=78965432-1234-5678-90ab-cdef12345678   (1 of 5)
        (and 66966666-6666-6666-6666-666666666666 on a different tool entirely)

    Both rows that record this said the same thing: a shape test is plausible here, and its
    PRECISION against real ids is unknown — "that measurement is the next step, not the fix".

    THE MEASUREMENT, 2026-08-27. Two populations, because the second is the one this function
    actually sees:

                              38,314 real ids      390 GENUINE ids the model passed
        all-digits-identical         2 (both               0
                                     themselves
                                     placeholders)
        sequential run >= 8          0                     0
        --- rejected, and why ---
        distinct hex <= 2           20                     0
        UUID version != 7       11,618                     -

    So the two rules below fire on nothing real in either population. `distinct <= 2` is NOT
    shipped: its 20 are hand-authored sentinels that DO resolve — 00000000-…-00000000000a and
    the like — and a rule that refuses a value which exists is a false refusal even when the
    value is ugly. `version != 7` is refuted outright: 11,618 genuine v4 ids are in the stores,
    exactly as D-FABRICATION-GUARD-IS-BLIND-TO-A-VALID-LOOKING-UUID warned.

    RECALL IS PARTIAL AND THAT IS THE PRICE OF THE PRECISION. Of the nine invented UUIDs found
    in recorded tool arguments these catch seven; `66966666-…-6666` and `76767676-…-7676` have
    two distinct digits and no long run, and reaching them needs the rule that also refuses a
    sentinel. A guard that is right about what it flags is worth more here than one that flags
    more, because a false refusal deletes an argument the model supplied correctly.
    """
    try:
        raw = f"{UUID(value).int:032x}"
    except (ValueError, AttributeError, TypeError):
        return False
    if len(set(raw)) == 1:
        return True
    run = 1
    for i in range(1, len(raw)):
        a, b = _HEX_ORDER.find(raw[i - 1]), _HEX_ORDER.find(raw[i])
        run = run + 1 if (a >= 0 and b == a + 1) else 1
        if run >= _DEGENERATE_SEQ_RUN:
            return True
    return False


#: The ids the RUNTIME fills from the turn. Excluded from the declared-UUID check below because
#: `_inject_context_ids` owns them: it supplies a missing one and SUBSTITUTES a malformed one for
#: the value the server already knows. A non-context id has no such fallback.
_RUNTIME_CONTEXT_IDS = frozenset({"book_id", "chapter_id", "project_id"})

#: Words that appear in a model's fill-me-in stub and never in an identifier this platform issues.
#: Matched case-insensitively on a word-ish boundary, so `PLACEHOLDER`, `unknown_id`,
#: `YOUR_ID_HERE` and `run_12345_placeholder` all hit while a real UUID cannot: hex has no
#: letters past `f`, so "unknown", "placeholder", "provide", "todo" and "example" are unreachable.
#: SCREAMING_SNAKE_CASE — all caps, digits and underscores, with at least one underscore. Both
#: placeholders measured live take this shape ("UNKNOWN_ID_PLEASE_PROVIDE",
#: "REPLACE_WITH_ACTUAL_REFERENCE_ID") and nothing this platform issues does: 0 of 293 real codes
#: contain ANY uppercase letter, and a UUID has no underscore.
_SCREAMING_SNAKE_RE = re.compile(r"[A-Z0-9]*_[A-Z0-9_]*")

_PLACEHOLDER_TOKEN_RE = re.compile(
    r"(?:^|[^a-z])(?:unknown|placeholder|your[_-]?id|id[_-]?here|todo|tbd|example|"
    r"provide|fill[_-]?me|xxx+)(?:[^a-z]|$)",
    re.IGNORECASE,
)


def _declares_uuid(props: dict | None, name: str) -> bool:
    """Does the tool's OWN declaration for this argument say it is a UUID?

    Read from the description because that is where the platform states it — measured across the
    live catalogue, 219 `*_id` properties say UUID in prose and none declares `format: uuid`.
    Until that is fixed at the providers, the description is the only declaration there is, and
    reading it beats inferring from the argument's name.
    """
    if not isinstance(props, dict):
        return False
    spec = props.get(name)
    if not isinstance(spec, dict):
        return False
    if spec.get("format") == "uuid":
        return True
    return "uuid" in str(spec.get("description") or "").lower()


def _name_like_dropped_ids(dropped: dict, *, emitter: str = "",
                           referent_exists: bool = True) -> str:
    """A sentence naming the NAMES the model passed where ids were required — or "" .

    `emitter` is the tool DECLARED to produce the id (argument_emitters); naming it is also what
    ARMS it, since the arming path keys off catalogue names in the refusal text. `referent_exists`
    says whether anything ELSE in the message already named a tool — when both are absent the
    closing instruction is dropped rather than left pointing at nothing. Both default to the old
    behaviour so a caller that has not been taught to resolve them is unchanged.

    🔴 WHY THE VALUE AND NOT JUST THE ARGUMENT NAME. Measured 2026-08-23,
    composition_motif_link_edit over K=5: the model resolved both endpoints to names, the
    whitespace arm of `_invented_supplier_ids` dropped them (correctly — they are not ids), and
    the refusal reported them MISSING. The tool's own description already says "search motifs by
    name with composition_motif_search and pass the id it returns", and the model duly called
    that search — with blank arguments, twice, because the only thing it could have searched FOR
    had just been deleted out of its own call. The turn then died and the failure was recorded
    against the tool for fifteen runs.

    So this returns the value, quoted, as the query to search with. ONLY for values that look
    like a name — whitespace, not a UUID, not SCREAMING_SNAKE. A placeholder like
    `run_12345_placeholder` or `UNKNOWN_ID_PLEASE_PROVIDE` must NOT be echoed back as something
    to search for: that is the invention D-FJ-11 exists to refuse, and repeating it would invite
    a better-formatted one, which is the exact failure its docstring warns about.
    """
    if not isinstance(dropped, dict):
        return ""
    named: list[str] = []
    for nm, val in sorted(dropped.items()):
        if not isinstance(val, str):
            continue
        v = val.strip()
        if not v or _is_uuid(v) or _SCREAMING_SNAKE_RE.fullmatch(v):
            continue
        if not any(ch.isspace() for ch in v):
            continue
        named.append(f"{nm}={v!r}")
    if not named:
        return ""
    head = ("You passed a NAME where an id is required (" + ", ".join(named) + "). That is not "
            "missing — it is the wrong kind of value, and the name is what you search WITH")
    # ── D-THE-ID-REPAIR-SENTENCE-NAMES-A-TOOL-THAT-IS-NOT-THERE ─────────────────────────────
    # 🔴 "THE TOOL NAMED ABOVE" HAD NO REFERENT FOR HALF THE CATALOGUE. The phrase was written
    # for composition_motif_link_edit, whose description really does say "search motifs by name
    # with composition_motif_search". When a description names nothing, the model is told to use
    # a tool that was never named — and it acts on it: measured in c-arcapply K=5, the model got
    # this sentence for composition_arc_template_get and then guessed composition_arc_suggest,
    # finally telling the author it could not find a template its own run had just created.
    #
    # The row's remedy, in its own order: NAME the supplier — the platform holds the catalogue at
    # the moment it writes this — and failing that DROP the clause, because "an instruction with
    # no referent is worse than no instruction, because the model spends its turn acting on it."
    #
    # Re-derived 2026-08-26 over the live catalogue: of 131 tools requiring a non-ambient *_id,
    # 59 name a supplier in prose and 52 now declare an EMITTER, leaving 49 (37%) with no
    # referent of any kind. The emitter map is what makes the first branch possible at all.
    if emitter:
        return f"{head}: look it up with `{emitter}` and pass the id it returns, using that " \
               "exact name as the query."
    if referent_exists:
        return (f"{head}: look it up with the tool named above and pass the id it returns, using "
                "that exact name as the query.")
    # No emitter, and nothing above named a tool. Say what is true and stop — do NOT invent a
    # remedy, and do NOT point at a tool that was never named.
    return (f"{head}. No tool on this surface is declared to resolve it, so do not guess an id: "
            "tell the author you need the id, or a way to identify it that this tool accepts.")


#: Arguments that carry the AUTHOR'S OWN PROSE into their book — the payload slot, not metadata.
#: Deliberately EXCLUDES `description`, `summary`, `notes` and `instructions`: they are short
#: metadata fields, no instance was measured on any of them, and widening a refusal onto fields
#: with no evidence is how a guard starts deleting values that were fine.
DOCUMENT_ARGS = frozenset({
    "content", "body", "text", "markdown", "source_markdown", "draft", "prose",
    "body_markdown", "chapter_body",
})

_CONTENT_NOUN = (r"(?:content|text|story|stories|notes?|details?|idea|ideas|description|"
                 r"descriptions|summary|draft|chapters?|document|manuscript|material)")

#: A document that is a MESSAGE ABOUT NOT HAVING A DOCUMENT. Four arms, each measured:
#: an assertion that content is absent; an assertion about the user; a request TO the author to
#: supply content; and the model narrating its own next step.
_HOLLOW_DOCUMENT = re.compile(
    r"no\s+(?:story\s+|source\s+|such\s+)?" + _CONTENT_NOUN + r"[^.]{0,40}"
    r"(?:provided|available|given|yet)"
    r"|user\s+has\s+(?:not|n't)\s+(?:yet\s+)?provided"
    r"|please\s+provide[^.]{0,60}?" + _CONTENT_NOUN +
    r"|i\s+will\s+ask\s+the\s+user"
    r"|to\s+begin\s+the\s+extraction",
    re.I,
)


def _is_hollow_document(value) -> bool:
    """A document argument whose content is a statement that there is no content.

    🔴 MEASURED 2026-08-27 over `chat_messages.tool_calls`: 508 arguments carrying a document,
    10 of them hollow, across two tools. Eight are `glossary_extract_entities_from_doc`'s
    `source_markdown` — the tool then EXTRACTS ENTITIES from a sentence about the absence of a
    story. The tenth is the one that matters most and the one a narrow rule misses:

        book_chapter_save_draft.body = "I will perform a consistency check on your story.
                                        Please provide the text or specify which chapters
                                        I should analyze."

    That is a CHAPTER BODY. It would be saved into the manuscript as the chapter's prose.

    THE `please provide` ARM IS THE LOOSE ONE AND IT IS THE ONLY ONE THAT REACHES THAT
    INSTANCE — the other nine are caught without it. It is therefore kept, but narrowed to a
    request for CONTENT specifically, so fiction that happens to use the phrase is untouched.
    Measured against the store and against four fiction probes:

        "Please provide the codex," the Regent said            -> not flagged
        She would not provide the text of the oath             -> not flagged
        Please provide the text or specify which chapters      -> FLAGGED

    THE RESIDUAL FALSE-POSITIVE SURFACE, NAMED: a chapter whose dialogue reads "please provide
    the text". None of the 508 recorded documents is one. Tightening cost nothing — the loose
    and narrow rules both flag exactly the same 10.

    This is `_is_nil_uuid`'s sentence one value class wider: a value recognisable as a
    non-value WITHOUT knowing the author's book is knowably not content, and it feeds the same
    drop-then-report-missing path, so the model is told to go and ask rather than to write.
    """
    return isinstance(value, str) and bool(_HOLLOW_DOCUMENT.search(value))


def _hollow_document_args(args_obj: dict) -> list[str]:
    """Document arguments the model filled with a note about having no document."""
    if not isinstance(args_obj, dict):
        return []
    return [name for name, value in args_obj.items()
            if name in DOCUMENT_ARGS and _is_hollow_document(value)]


def _hollow_document_note(dropped: dict) -> str:
    """The sentence for the third state, for a DOCUMENT rather than an id.

    The missing-argument message has three arms — owed / undeclared / model-supplied — and a
    document is model-supplied, so without this it reads "you forgot something". That is the
    one description guaranteed not to help: the model did not forget, it knowingly had nothing
    and put the saying-so in the payload. The honest sentence names what it did and where the
    content actually comes from.
    """
    named = [nm for nm in sorted(dropped) if isinstance(dropped[nm], str)]
    if not named:
        return ""
    return (
        "You passed a note about having no content (" + ", ".join(named) + ") where the "
        "author's own words are required. That is not a document — it is a message to them, "
        "and writing it would put it in their book. Do NOT compose one yourself: ask the "
        "author for their text, or read it from the book, and call this again with what they "
        "actually wrote."
    )


#: Arguments that set a SPEND CEILING. Measured, not guessed: across every recorded tool call
#: in the live store, `budget_usd` on composition_authoring_run_manage is the only money-typed
#: argument in use. `limit` (418 calls, 8 tools) is pagination and `spend` (113 calls, 12 tools)
#: is a BOOLEAN — both would have been swept in by a name-shaped guess.
MONEY_ARGS = frozenset({"budget_usd"})

#: The author saying anything at all about money. Deliberately WIDE: a false negative here
#: refuses a number the author really gave, which is the expensive mistake.
_AUTHOR_MENTIONED_MONEY = re.compile(r"\$|dollar|usd|budget|spend", re.I)


def _author_named_money(messages: list[dict] | None) -> bool:
    """Did the AUTHOR raise money anywhere in this conversation?"""
    for m in messages or ():
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str) and _AUTHOR_MENTIONED_MONEY.search(content):
            return True
    return False


def invented_money_args(args_obj: dict, messages: list[dict] | None) -> list[str]:
    """A spend ceiling the author never mentioned is not the model's to choose.

    🔴 MEASURED 2026-08-27 over every `budget_usd` call in the live store — 16 of them, and the
    discrimination is exact:

        the author mentioned money   7 calls   budget_usd=5, and they had said "5 dollars"
        the author said NOTHING      9 calls   budget_usd = 10 (x4), 5 (x3), 50 (x2)

    Nine invented spend ceilings, no overlap with the seven real ones. The row this closes
    measured three of them by hand and noted what saved the author: the call refused because
    `pause_after_each_unit` was ALSO missing, so nothing was spent — "the guard that saved it
    was an unrelated missing argument, not anything about money". Had the model filled both in,
    a Tier-W card would have been minted for a $50 run nobody asked for, and a confirm card
    defends against the wrong failure here: the author sees a plausible run and the number on
    it is invented.

    THE TEST IS THE AUTHOR'S OWN WORDS, and it is deliberately generous to them — `$`, `dollar`,
    `usd`, `budget` or `spend` anywhere in any user turn is enough to keep the value. A false
    negative refuses a number the author really gave; a false positive merely makes the model
    ask. On the measured population the generous test still separates 9 from 7 cleanly.

    Same drop-then-report-missing path as `_invented_supplier_ids`, so the model is told to ask
    rather than told off.
    """
    if not isinstance(args_obj, dict):
        return []
    if _author_named_money(messages):
        return []
    return [name for name, value in args_obj.items()
            if name in MONEY_ARGS and isinstance(value, (int, float)) and not isinstance(value, bool)]


def _money_arg_note(dropped: dict) -> str:
    """The sentence for a dropped spend ceiling — the generic missing-argument text would call
    it forgotten, and a fabricated budget is not a forgotten one."""
    named = sorted(dropped)
    if not named:
        return ""
    return (
        "You chose a spend ceiling the author never mentioned (" + ", ".join(named) + "). That "
        "is the author's money and their decision, not a default for you to pick. Ask them what "
        "budget they want and call this again with the number they give you."
    )


def _invented_supplier_ids(args_obj: dict, contract: dict | None,
                           tool_def_props: dict | None = None) -> list[str]:
    """`*_id` args the CONTRACT says the runtime owes, which the model filled in with a non-UUID.

    🔴 MEASURED LIVE 2026-08-12, journey `autonomous-drafting` (book 019ff497). The model called
    plan_compile with `run_id="run_12345_placeholder"` and the tool answered *"run_id must be a
    UUID"* — correct about the TYPE, and silent about the thing that matters: `run_id` is a PLAN
    value emitted by plan_propose_spec. It is not the model's to invent at all, so arguing about its
    format invites a better-formatted invention. This is the identical lesson CP-5.4 already learned
    for MISSING arguments ("you forgot something" vs "I owe you this"), one state to the right: the
    argument is PRESENT and fabricated, so the missing-arg path never runs and the honest sentence
    never fires.

    Deliberately narrow, because a false positive here would refuse a legitimate call:

    * only `*_id` names — the convention for an opaque identifier, and the shape a placeholder gets
      invented for;
    * only where the CONTRACT declares the supplier **`plan`**. A `model`-supplied id is the
      caller's to choose and none of this function's business; an UNDECLARED one is D-FJ-2's
      territory — silence, not a guess; and `context` is EXCLUDED deliberately. 🔴 The first draft
      included context and the suite caught it firing on `book_id="b1"`: a context id is injected by
      the runtime upstream of this point and is not guaranteed to be a UUID, so treating a non-UUID
      one as fabricated deleted a value the runtime itself had supplied and broke the dispatch. A
      `plan` id is the one the model has no way to know and therefore the one it invents;
    * only a non-empty string that does not parse as a UUID. A valid UUID is accepted even if it is
      wrong, because *whether it is the right row* is the tool's question, not ours.
    """
    from app.agentruntime.toolcontract import declared_supplier

    if not isinstance(args_obj, dict):
        return []
    out: list[str] = []
    for name, value in args_obj.items():
        # 🔴 `*_ref` IS THE SAME CONVENTION, and leaving it out cost a measured approve-then-fail.
        # composition_generate declares `model_ref` (a UUID at the confirm effect, which does
        # UUID(str(...))) and the model sent "default" on 5 of 5 runs — a Tier-A card was minted
        # every time and approving it produced a bare 400 `action_error`, on the most expensive
        # tool on the platform. The name simply did not end in `_id`, so this loop never looked.
        #
        # ONLY the DECLARED-UUID arm widens. The whitespace arm stays `*_id`-only, because the
        # other `*_ref` on this platform is `image_ref` — a MinIO object key, explicitly not a
        # UUID (world_map_create: "optional MinIO object key of an already-uploaded base image").
        # It declares no UUID, so the declared arm cannot touch it; widening the whitespace arm
        # would have started dropping legitimate object keys. Measured across the catalogue: 21
        # `*_ref` properties, 19 of them `model_ref`, and only 4 declare a UUID at all.
        _identifierish = name.endswith("_id") or name.endswith("_ref")
        if not _identifierish:
            continue
        # 🔴 THE NIL UUID PARSES, SO THE FORMAT TEST BELOW ACCEPTS IT — AND IT IS NEVER A ROW.
        # This function's rule is deliberately "a valid UUID is accepted even if it is wrong,
        # because whether it is the right row is the tool's question". The all-zero UUID is the
        # one value that rule should not cover: it is reserved, no table ever holds it, so it is
        # knowably invented rather than merely possibly-wrong.
        #
        # MEASURED LIVE 2026-08-14, batch 7: asked to draw a region on a map, the model called
        # world_map_add_region 3/3 with map_id="00000000-0000-0000-0000-000000000000" — the
        # polygon was right, the map was never looked up. Because it parses, nothing here fired,
        # and a Tier-A CONFIRM CARD was minted for a call that cannot succeed: the tool answers
        # "map not found" (verified at the boundary). The author is asked to approve a write
        # whose target does not exist.
        #
        # Applies whatever the contract says, and whether or not there IS one, because the value
        # is wrong for every supplier. Feeding it into the existing drop-then-report-missing path
        # gives the model the honest sentence — this argument is required and you have not
        # supplied it — which is the one that makes it go and look the id up.
        # The nil UUID and its family: syntactically valid, knowably invented. Same drop-then-
        # report-missing path, which is the sentence that sends the model to look the id up.
        if isinstance(value, str) and (_is_nil_uuid(value) or _is_degenerate_uuid(value)):
            out.append(name)
            continue
        # 🔴 THE REQUIREMENT IS DECLARED IN PROSE NO VALIDATOR READS. Measured 2026-08-14 across
        # the live catalogue: 219 `*_id` properties over 8 providers say "UUID" in their
        # DESCRIPTION and exactly ZERO declare `format: uuid`. So "Ashfall" is a schema-valid
        # `world_id`, and batch 8 measured precisely that — world_map_create called 3/3 with
        # world_id="Ashfall", the world's NAME, and a Tier-A confirm card minted for a call the
        # service can only reject.
        #
        # The description IS declared data, so reading it is the same move as reading `tier` or
        # `synonyms` rather than inferring from a name.
        #
        # SCOPED AWAY FROM THE CASE THIS FUNCTION ALREADY LEARNED ABOUT. The comment above records
        # that including `context` deleted `book_id="b1"` — a value the RUNTIME injects, which is
        # not guaranteed to be a UUID — and turned 5 tests red. That reasoning holds and is why
        # the three context ids are excluded here by name: the server fills those itself and
        # `_inject_context_ids` already repairs a malformed one by SUBSTITUTING the value it
        # knows. For a non-context id there is nothing to substitute, so the honest move is the
        # one below — drop it and report it missing, which sends the model to look it up.
        # 🔴 AN ID WITH WHITESPACE IN IT IS A NAME. No identifier this platform issues contains a
        # space — not a UUID, not a slug, not a code — so this needs no declaration to be certain,
        # which matters because 277 of 496 `*_id` properties say nothing about their format and are
        # invisible to the declaration arm below (composition alone accounts for 200).
        #
        # MEASURED LIVE 2026-08-14, batch 14: composition_arc_get was called with
        # node_id="The Hollow Keep" — the arc's TITLE — and again with "arc_1". The tool refused
        # correctly, but only after a round trip, and node_id's description says merely "The
        # arc/saga (structure_node) id", so the declaration arm could not see it.
        #
        # Context ids are exempt here too, for the reason recorded below: the runtime injects them
        # and they are not guaranteed to be UUIDs. None of them contains whitespace either, so the
        # exemption costs nothing.
        # 🔴 A NAMED PLACEHOLDER IS NEVER AN IDENTIFIER THIS PLATFORM ISSUES. The whitespace arm
        # below needs a space and the declaration arm needs a description; a value like
        # "UNKNOWN_ID_PLEASE_PROVIDE" has neither, so both miss it.
        #
        # MEASURED LIVE 2026-08-21, batch 21, composition_reference_update, 5 of 5 runs. The
        # reference table is EMPTY on this deployment, so no real id exists — and the model said
        # so in prose ("I need to know which reference you are referring to") while ALSO calling
        # the tool with reference_id="UNKNOWN_ID_PLEASE_PROVIDE" and title=[]. A Tier-A confirm
        # card was minted for it: the author is asked to approve updating a reference whose id is
        # the literal text UNKNOWN_ID_PLEASE_PROVIDE. `reference_id` is advertised as
        # {"title": "Reference Id", "type": "string"} — no description — which is why the
        # declaration arm is blind to it.
        #
        # This is the THIRD placeholder to reach a card: model_ref="default" (batch 18),
        # run_id="run_12345_placeholder" (recorded earlier in this loop), and now this one. The
        # token list is deliberately SMALL and matched on word-ish boundaries: every entry is a
        # word that appears in a filled-in-by-the-model stub and never in a UUID, a slug or a
        # code. A hex id cannot contain any of them.
        # 🔴 A CONTEXT ID IS NOT EXEMPT FROM *THIS* ARM, and the exemption's own reason is why.
        # `_RUNTIME_CONTEXT_IDS` is excluded everywhere else because the RUNTIME injects those
        # values and they are not guaranteed to be UUIDs — dropping one once deleted a value the
        # runtime itself had supplied. That reasoning does not reach a value containing the word
        # `placeholder`: the runtime does not inject those, only a model does.
        #
        # MEASURED 2026-08-27 over every recorded call — 320 non-UUID context ids, of which the
        # token list matches 155:
        #     144  book_id    = "current_book_id_placeholder"
        #       3  book_id    = "placeholder_book_id"
        #       2  chapter_id = "[chapter_id_placeholder]"
        #       2  project_id = "current_project_id_placeholder"
        #       1  book_id    = "YOUR_BOOK_ID_HERE"        …and 3 more
        # Not one of them could have come from the runtime. The other 165 — fixture names,
        # "all", "book_list", a book TITLE — are NOT reached here and still need the
        # declaration-driven arm, which is the one carrying the dispatch risk.
        if (
            _identifierish
            and isinstance(value, str)
            and _PLACEHOLDER_TOKEN_RE.search(value)
        ):
            out.append(name)
            continue
        # 🔴 AND THE WORD LIST WAS TOO NARROW — REFUTED BY THE VERY NEXT RUN. The arm above
        # caught reference_id="UNKNOWN_ID_PLEASE_PROVIDE"; the model's next attempt was
        # "REPLACE_WITH_ACTUAL_REFERENCE_ID", which shares not one word with it. A blacklist is
        # whack-a-mole against text a model invents freely.
        #
        # What the two DO share is shape: SCREAMING_SNAKE_CASE. So the rule is about the alphabet,
        # not the vocabulary — and it is measured, not assumed. Across every code this platform
        # has ever issued (240 motifs, 53 arc templates) exactly ZERO contain an uppercase letter,
        # and a UUID is lowercase hex. So an `*_id` that is not a UUID and carries an uppercase
        # letter is not an identifier this platform issued.
        #
        # NARROWED AFTER THE SUITE CAUGHT ME. My first shape rule was "not a UUID and contains
        # an uppercase letter", and it broke a standing invariant of this very function: the
        # existing test `test_with_no_properties_at_all_nothing_is_claimed` pins that
        # world_id="Ashfall" is NOT dropped when nothing is declared (D-FJ-2 — no declaration, no
        # judgement). "Ashfall" is a NAME, and it would also have caught a legitimate opaque
        # vendor id like "ABC-123". So the rule is SCREAMING_SNAKE_CASE specifically — all caps,
        # digits and underscores, with at least one underscore — which is what both measured
        # placeholders are and what neither a name nor a vendor reference is.
        #
        # `*_id` ONLY, deliberately: the other `*_ref` here is image_ref, a MinIO object key,
        # and object keys may legitimately be mixed-case. It stays with the declaration arm.
        if (
            name.endswith("_id")
            and name not in _RUNTIME_CONTEXT_IDS
            and isinstance(value, str)
            and value.strip()
            and not _is_uuid(value)
            and _SCREAMING_SNAKE_RE.fullmatch(value.strip())
        ):
            out.append(name)
            continue
        # 🔴 THE CONTEXT ID, WORN AS A DOMAIN ID. Every arm above tests for a value that looks
        # WRONG — not a UUID, SCREAMING_SNAKE, whitespace, a placeholder word. This one tests for a
        # value that is perfectly RIGHT and belongs to something else: the turn's ambient book_id,
        # passed as an entity_id / chapter_id / run_id.
        #
        # PROVEN BY IDENTITY, not inference. kg_propose_edge, 2026-08-23, three of three inspected
        # runs: the run's own book_id EQUALS the value the tool refused, passed as BOTH
        # source_entity_id and target_entity_id ("they identify DIFFERENT things and can never be
        # the same id"). It is the most plausible-looking wrong answer available — a real, current,
        # valid UUIDv7 that the runtime itself injected — which is exactly why the model reaches
        # for it when it needs an id it does not have, and exactly why no syntactic arm can see it.
        #
        # PRECISION MEASURED BEFORE SHIPPING, over 16,080 recorded calls: this fires 180 times
        # across 15 tools, and every shape is a wrong argument — glossary_get_entity.entity_id=71,
        # book_chapter_save_draft.chapter_id=38, book_chapter_delete.chapter_id=15 (destructive),
        # composition_authoring_run_review.run_id=13. The one candidate false positive,
        # composition_create_work.project_id, is not one: knowledge_projects has ZERO rows where
        # project_id equals book_id, and composition's own declaration says so in as many words —
        # "book_id = the book. They are DIFFERENT". No legitimate case was found.
        #
        # Scoped to the SAME CALL's own arguments, so it compares a value the model itself paired
        # with that book_id — never a context value fetched from elsewhere.
        if (
            name.endswith("_id")
            and name not in _RUNTIME_CONTEXT_IDS
            and isinstance(value, str)
            and value.strip()
            and any(
                isinstance(args_obj.get(ctx), str)
                and args_obj[ctx].strip() == value.strip()
                for ctx in _RUNTIME_CONTEXT_IDS
            )
        ):
            out.append(name)
            continue
        if (
            name.endswith("_id")  # `*_ref` is deliberately NOT here — see the loop head:
                                  # image_ref is a MinIO object key, not an identifier this
                                  # platform issues, so whitespace in one is not proof of a name.
            and name not in _RUNTIME_CONTEXT_IDS
            and isinstance(value, str)
            and value.strip()
            and any(ch.isspace() for ch in value.strip())
        ):
            out.append(name)
            continue
        if (
            name not in _RUNTIME_CONTEXT_IDS
            and isinstance(value, str)
            and _declares_uuid(tool_def_props, name)
            and not _is_uuid(value)
        ):
            out.append(name)
            continue
        if not contract:
            continue
        if declared_supplier(contract, name) != "plan":
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            UUID(value)
        except (ValueError, AttributeError, TypeError):
            out.append(name)
    return sorted(out)


def _ids_already_returned(history: list[dict] | None, arg: str) -> list[str]:
    """UUID values a tool result earlier in this CONVERSATION returned under key `arg`.

    🔴 THE CONVERSATION, NOT THE TURN. The instance this exists for spans two turns: turn 1 calls
    plan_bootstrap_propose (ok, returns proposal_id) and asks "would you like me to go ahead?";
    turn 2 says "yes" and calls plan_bootstrap_apply WITHOUT it. Anything scanning only the
    current turn sees a model that never held the id — and the refusal then reads as correct.

    Returns EVERY distinct value, so the caller can refuse to guess when there is more than one.
    That is the precision guard: measured over the 4 recorded cases, each session held exactly ONE
    value for the key in question, but a session with two runs would make "the" id a fabrication.
    """
    if not history:
        return []
    pat = re.compile(rf'"{re.escape(arg)}"\s*:\s*"([0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-'
                     rf'[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}})"')
    # Named `values`, not the obvious short name: a four-space-indented annotated-empty-list
    # declaration of a variable called o-u-t is an anchored falsifier string in this file, and a
    # second occurrence makes that anchor ambiguous. The anchor is described, never quoted —
    # quoting it is itself an occurrence, which is how this comment failed the gate once already.
    values: list[str] = []
    for m in history:
        if not isinstance(m, dict) or m.get("role") != "tool":
            continue
        for v in pat.findall(str(m.get("content") or "")):
            if v not in values:
                values.append(v)
    return values


def _owed_args(contract: dict | None, missing: list[str]) -> list[str]:
    """The missing args a contract says the RUNTIME supplies — never the model's to write.

    One home for the rule, because the CALL SITE needs it too: it decides which arguments are
    worth a database read before the refusal is built, and a second copy of the predicate there
    would be free to drift from the one the message actually branches on.
    """
    from app.agentruntime.toolcontract import declared_supplier

    _b = contract if type(contract) is dict else {}
    return [a for a in missing if declared_supplier(_b, a) in ("context", "plan")]


def _missing_args_message(tool: str, missing: list[str], contract: dict | None,
                          tool_def_props: dict | None = None,
                          history: list[dict] | None = None,
                          also_returned: dict[str, list[str]] | None = None) -> str:
    """The refusal for a call still missing required args — keyed off who DECLARES each one.

    CP-5.4 split this into two arms, `context|plan` ("not yours to invent") and everything else
    ("these carry the actual CONTENT"). There is a THIRD case it folded into the second, and the
    fold makes a claim the runtime cannot support: **the tool declares no supplier at all.**

    🔴 MEASURED LIVE 2026-08-12, journey `draw-a-map`. `world_map_create` was called without
    `world_id`, and the refusal read: *"missing required argument(s): ['world_id']. These carry the
    actual CONTENT (not ids the system already fills) — e.g. a list of the items to create, or the
    search text. … Do not call it with only ids or empty arguments."* The one missing argument IS an
    id, so the model was told the thing it was missing was not the thing it was missing, and told
    not to do the thing it needed to do. It stopped calling tools and reported *"I have initialized
    the map"* over a map that was never created. Only **12** of the 315 federated tools carry a
    contract, so the undeclared case is the common one, not the exotic one.

    Being honest here is not a reword: the old sentence asserts a FACT about these arguments
    (*they are not ids*) that is derived from nothing when no contract declares them. This arm
    asserts nothing it cannot know, and names both moves so a caller missing an id has one — which
    is the same standard C-12 sets for a rejection, and the same standard the `context|plan` arm
    already meets.
    """
    from app.agentruntime.toolcontract import declared_emitter, declared_supplier

    block = contract if type(contract) is dict else {}
    owed = _owed_args(block, missing)
    if owed:
        # D-FJ-12 — NAME THE TOOL THAT EMITS IT. "Establish that context first (e.g. list or open
        # the book you mean)" is a book-flavoured example, not an instruction, and a model told only
        # that retried the SAME tool twice. The emitter is declared data (`emitted_by`), so say it.
        #
        # 🔴 THIS COMMENT USED TO END *"Naming it also ARMS it: `_tools_named_in_refusal` keys off
        # catalogue names in the refusal text, so one sentence fixes both the instruction and the
        # reachability."* THAT WAS FALSE FOR EVERY MESSAGE THIS FUNCTION BUILDS. `_tools_named_in_
        # refusal` ran only on the DISPATCH result, and the caller that builds these messages
        # returns before dispatch — so the arming this sentence promised had never once happened
        # here. Measured 2026-08-22: `world_map_delete` refused with *call world_map_list first*
        # and world_map_list was advertised on 0 of 5 runs; across 35 runs the supplier was called
        # on every run it was advertised and on none where it was not (35/35 agreement).
        #
        # It is true NOW because the caller was fixed, not because this function does it — see
        # D-REFUSAL-NAMES-A-TOOL-THE-TURN-CANNOT-SEE at the `_missing_args` arm, which passes this
        # text through `_tools_named_in_refusal` and `_arm_tools`. Naming a tool here is therefore
        # load-bearing for reachability, and a message that names an off-catalogue tool arms
        # nothing: keep the names exact.
        _reg = _tool_contract_registry()
        _emitters = sorted({e for a in owed if (e := declared_emitter(_reg, tool, a))})
        _how = (
            f"Call {' and '.join(_emitters)} first, then call this with the id it returns."
            if _emitters else
            "Establish that context first (e.g. list or open the book you mean, then call this "
            "with the id it returns)."
        )
        # ── D-THE-OWED-REFUSAL-DENIES-AN-ID-THE-MODEL-WAS-JUST-HANDED ──────────────────────
        # 🔴 EVERY CLAUSE BELOW IS TRUE OF THE RUNTIME AND NONE OF IT IS TRUE OF THE TURN when
        # the value is already in the transcript. "NOT yours to invent" is correct and
        # load-bearing; "the runtime supplies it … and has none right now" tells a model HOLDING
        # the id that the id is not its business. The two clauses give opposite instructions.
        #
        # MEASURED over loreweave_chat.chat_messages, swept per SESSION rather than per turn:
        # of 15 `owed` refusals, 4 (27%) fired while the session had already been handed that
        # exact id — plan_compile.run_id twice, plan_bootstrap_apply.proposal_id twice. In all
        # four the session held EXACTLY ONE value for the key, which is why quoting it is safe;
        # where it holds more than one this says nothing, because "the" id would be a guess.
        #
        # 🔴 TWO SOURCES, AND THE SECOND IS THE ONE THAT MATTERS. `history` is the conversation
        # as the MODEL sees it, and a prior turn's tool RESULT is not in it: chat_messages holds
        # zero role='tool' rows — a result is stored on the ASSISTANT row's `tool_calls` column,
        # so rehydration brings back user/assistant text and nothing else. A first fix read only
        # `history`, which covers this turn (where the tool messages are appended live) and NOT
        # the prior one — and fired 0 times in 10 live runs, on a defect whose recorded instance
        # spans exactly two turns. `also_returned` carries what the server's own record holds;
        # the union is what gets the precision guard.
        _prior = also_returned if type(also_returned) is dict else {}
        _held: dict[str, list[str]] = {}
        for _a in owed:
            _seen = _ids_already_returned(history, _a)
            for _v in _prior.get(_a) or []:
                if _v not in _seen:
                    _seen.append(_v)
            # EXACTLY ONE, or say nothing: two values make "the" id a guess, and a guess here is
            # the very failure this branch exists to stop.
            if len(_seen) == 1:
                _held[_a] = _seen
        if _held:
            _one = len(_held) == 1
            _pairs = ", ".join(f"{a}={v[0]}" for a, v in sorted(_held.items()))
            return (
                f"'{tool}' is missing {sorted(_held)} — and YOU ALREADY HAVE "
                f"{'IT' if _one else 'THEM'}: {_pairs} "
                f"{'was' if _one else 'were'} returned by an earlier tool call in this "
                "conversation. Pass that exact value back; do NOT invent one, and do not call "
                "the supplier again to re-fetch what you were already given."
            )
        return (
            f"'{tool}' is missing {owed}, and {'these are' if len(owed) > 1 else 'this is'} "
            f"NOT yours to invent: the runtime supplies "
            f"{'them' if len(owed) > 1 else 'it'} from the current context or an "
            f"active plan, and has none right now. {_how} Do NOT guess a value."
        )
    # ── D-THE-EMITTER-ARM-IS-UNREACHABLE-WITHOUT-A-CONTRACT-ROW ────────────────────────────
    # 🔴 THE SAME FALSEHOOD AS THE COMMENT BELOW, ONE SOURCE LATER. That comment fixed "does
    # not declare" for the tool's own PROPERTY DESCRIPTION and left `argument_emitters` — the
    # one source that answers WHERE to get the value — readable only from the `owed` branch
    # above, which needs a `contracts` row. Measured 2026-08-26 against the registry and the
    # live 316-tool catalogue:
    #
    #     93 declared (tool, arg) emitter pairs · 90 unreachable from a refusal (97%)
    #       53  the emitter names a supplier the description does NOT mention  -> real gain
    #       24  the description already names it                               -> redundant
    #       13  the arg has NO description at all -> today's message says the tool
    #           "does not declare which side supplies them" WHILE AN EMITTER IS DECLARED
    #
    # This is not wording. A tool named in a refusal is ARMED onto the turn by the caller
    # (`_tools_named_in_refusal` -> `_arm_tools`), and this file's own measurement is 35/35
    # agreement: the supplier was called on every run it was advertised and on none where it
    # was not. So an unnameable emitter is an unreachable supplier.
    #
    # A declaration is a fact about the CATALOGUE, not about who owes the value, so it is read
    # for every missing arg — but only ADDED where the description does not already say it,
    # because repeating a supplier the sentence just quoted buys nothing and costs context.
    _emit_map: dict[str, str] = {}
    try:
        _reg_all = _tool_contract_registry()
        for _a in missing:
            _e = declared_emitter(_reg_all, tool, _a)
            if _e:
                _emit_map[_a] = _e
    except Exception:  # noqa: BLE001 — a registry lookup must never take the turn down
        _emit_map = {}

    def _emitter_sentence(said: str) -> str:
        """Name the declared emitters that `said` has not already named."""
        _new = sorted({e for a, e in _emit_map.items() if e not in said})
        if not _new:
            return ""
        return (
            f" {' and '.join(_new)} "
            f"{'emit' if len(_new) > 1 else 'emits'} "
            f"{'these' if len(_emit_map) > 1 else 'this'} — call "
            f"{'them' if len(_new) > 1 else 'it'} first and pass back the id "
            f"{'they return' if len(_new) > 1 else 'it returns'}."
        )

    if any(declared_supplier(block, a) is None for a in missing):
        # 🔴 "DOES NOT DECLARE" WAS CHECKING THE WRONG SOURCE, and it went from merely unhelpful to
        # FALSE the moment a declaration existed. Only 12 of the 315 federated tools carry a
        # contract, so `declared_supplier` is None for almost everything — but the tool's own
        # PROPERTY DESCRIPTION is a declaration too, and on this platform it is usually the ONLY
        # one (219 `*_id` properties state UUID in prose; zero emit `format: uuid`).
        #
        # MEASURED 2026-08-14: composition_generate's `model_ref` was given a description naming
        # its supplier — "list the caller's models with settings_list_models and pass the
        # `model_ref` from there" — and the refusal STILL told the model "this tool does not
        # declare which side supplies them — so do NOT guess a value". The runtime held the answer
        # and said it had none. On 4 of 5 runs the model then abandoned the grounded tool and
        # proposed book_chapter_save_draft with prose it wrote itself; on the 1 run that did call
        # settings_list_models and come back with a real id, it got there in spite of this
        # sentence, not because of it.
        #
        # Quoting the tool's own words asserts nothing the runtime cannot know — it is the same
        # move as reading `tier` or `synonyms` rather than inferring from a name.
        _declared = [
            (a, str((tool_def_props or {}).get(a, {}).get("description") or "").strip())
            for a in missing
        ]
        _declared = [(a, d) for a, d in _declared if d]
        if _declared:
            _lines = "; ".join(f"{a}: {d}" for a, d in _declared)
            return (
                f"'{tool}' is missing required argument(s): {missing}. The tool DOES declare what "
                f"{'these are' if len(_declared) > 1 else 'this is'} — {_lines} — so use that to "
                "obtain the real value and call again."
                + _emitter_sentence(_lines)
                + " Do NOT guess a value and do NOT substitute a placeholder like 'default'."
            )
        if _emit_map:
            # No description, but a DECLARED emitter — the 13 pairs above. Saying "does not
            # declare" here would be the exact falsehood the arm below was written to stop.
            return (
                f"'{tool}' is missing required argument(s): {missing}, and the value is an id "
                f"from another tool — do NOT guess one."
                + _emitter_sentence("")
            )
        # Genuinely undeclared: say so, and give the id move FIRST — that is the class this arm
        # was measured failing on. Never guess a value on the model's behalf.
        return (
            f"'{tool}' is missing required argument(s): {missing}, and this tool does not "
            "declare which side supplies them — so do NOT guess a value. If one of them names "
            "another record (an id), obtain it from the tool that LISTS or SEARCHES those "
            "records and pass back the id it returns; the ambient book is filled in for you, "
            "but nothing else is. Otherwise it is content only you can write: read the tool's "
            "schema for its exact shape, fill it in, and call again."
        )
    return (
        f"'{tool}' is missing required argument(s): {missing}. "
        "These carry the actual CONTENT (not ids the system already fills) — "
        "e.g. a list of the items to create, or the search text. Read the "
        "tool's schema for their exact shape, fill them in, and call again. "
        "Do not call it with only ids or empty arguments."
    )


#: A dispatch refusal that names REQUIRED ARGUMENTS but names no TOOL.
#:
#: 🔴 A FLAT-SUPERSET OP-DISPATCH TOOL MAKES EVERY REPAIR PATH BLIND. 18 catalogue tools declare
#: only `op` as required, because one schema serves several ops — so `_missing_required_names`
#: finds nothing missing, the call DISPATCHES, and the server refuses with the per-op requirement
#: it knew all along. None of the repair machinery above ever runs: no supplier is named, and
#: `_tools_named_in_refusal` arms nothing because the sentence contains no tool name.
#:
#: The server already computed the answer. Measured 2026-08-25 across every service's MCP layer:
#: 45 such refusal strings, all of one shape — `op=create requires from_motif_id, to_motif_id,
#: and kind`.
#:
#: 🔴 THE FIRST REGEX SILENTLY DROPPED THE LAST ARGUMENT OF A THREE-ITEM LIST, because a repeating
#: `,\s*item` group happily consumed ", and" as an item. It parsed, it looked right, and it
#: under-counted exactly the arguments a model most needs named. Three candidates were compared
#: against the real strings before this one was kept.
_PER_OP_REQUIRES_RE = re.compile(
    r"\brequires?\s+([a-z0-9_]+(?:[,\s]+(?:and\s+)?[a-z0-9_]+)*)", re.I)
_ARG_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]*")


def _args_named_in_refusal(text: str, props: dict | None) -> list[str]:
    """Argument names a refusal demands — kept ONLY if the tool actually declares them.

    🔴 THE SCHEMA IS THE PRECISION GUARD, and it is structural rather than textual on purpose.
    A word-matcher over refusal prose will happily report `and`, `a` or `dictionary` as arguments;
    requiring the refusing tool's own schema to declare the token makes that impossible by
    construction instead of by careful wording.

    MEASURED 2026-08-25 on the 70 service refusal strings that are NOT the per-op shape — the
    population where a greedy matcher does its damage: the guard rejects 66 of them outright, and
    the 4 that survive are real ("scope=dirty requires chapter_id", "delete_attribute requires
    genre_code"), where naming the supplier is equally right.
    """
    known = set(props or ())
    if not known:
        return []
    # Named `found` rather than the obvious `out`: the four-space-indented annotated-empty-list
    # declaration of a variable called `out` is the literal anchor of an existing falsifier
    # (test_the_LIVE_placeholder_is_caught), and a second occurrence makes that anchor ambiguous
    # — a stale anchor, which the membrane gate rejects without running a suite. The anchor is
    # DESCRIBED here rather than quoted, because quoting it is itself a second occurrence; that
    # is how this comment failed the gate on its first attempt.
    found: list[str] = []
    for m in _PER_OP_REQUIRES_RE.finditer(text or ""):
        for tok in _ARG_TOKEN_RE.findall(m.group(1)):
            if tok in known and tok not in found:
                found.append(tok)
    return found


def _enum_values(prop: dict) -> list[str]:
    """The closed set a property accepts, including the `anyOf[{enum}, {null}]` shape Pydantic
    emits for an optional enum — which is how EVERY enum on a flat-superset tool is declared, so
    reading only a top-level `enum` would find none of them."""
    if not isinstance(prop, dict):
        return []
    vals = prop.get("enum")
    if not vals:
        for alt in prop.get("anyOf") or []:
            if isinstance(alt, dict) and alt.get("enum"):
                vals = alt["enum"]
                break
    return [str(v) for v in vals] if isinstance(vals, list) else []


def _where_each_argument_comes_from(tool: str, args: list[str], registry: dict,
                                    props: dict | None = None) -> str:
    """One sentence per demanded argument saying where to GET it.

    Three outputs, because there are three situations and one sentence for all of them is the
    defect this file keeps re-learning:

      * an emitter is DECLARED -> name it. Naming it also ARMS it: the caller appends this text
        to the refusal, and `_tools_named_in_refusal` keys off catalogue names in that text. So
        the supplier reaches the wire, which is the difference between an instruction the model
        can follow and one it cannot.
      * the argument is an ENUM -> list the values. It is a choice from a closed set, not a
        lookup and not a question.
      * neither -> take it from the request, or ASK. `composition_authoring_run_manage` op=create
        needs `budget_usd` and `pause_after_each_unit`: how much money to spend and whether to
        pause between units are DECISIONS, no tool can supply them, and the platform's whole
        repair vocabulary is about FINDING values rather than requesting them. Without this the
        turn has no legal move at all — told not to guess and given nowhere to go.

    🔴 THE ENUM ARM EXISTS BECAUSE THE FIRST VERSION OVER-ASKED, caught by running it against the
    real refusal strings in the deployed container before any live run. It told the model to "ASK
    THE AUTHOR" for `composition_motif_link_edit.kind` — an enum of composed_of | precedes |
    variant_of, on a turn whose request said "mark A as coming BEFORE B". Asking the author to
    spell that out is worse than the refusal it replaced.
    ⚠️ AND THE LAST ARM SAYS "take it from the request, or ask" RATHER THAN A FLAT "ask", for the
    same reason one step further: "op=create requires code and name" is answered by the author's
    own sentence on most turns, and a flat instruction to ask would send the model back to a
    user who has already said it.

    Returns "" when there is nothing useful to add, so the caller never appends an empty sentence.
    """
    from app.agentruntime.toolcontract import declared_emitter

    sourced: dict[str, list[str]] = {}
    choose: list[tuple[str, list[str]]] = []
    ask: list[str] = []
    for a in args:
        emitter = None
        try:
            emitter = declared_emitter(registry, tool, a)
        except Exception:  # noqa: BLE001 — a contract lookup must never take the turn down
            emitter = None
        if emitter:
            sourced.setdefault(emitter, []).append(a)
            continue
        vals = _enum_values((props or {}).get(a) or {})
        if vals:
            choose.append((a, vals))
        else:
            ask.append(a)
    parts: list[str] = []
    for emitter, names in sorted(sourced.items()):
        parts.append(
            f"Call {emitter} to get {' and '.join(names)}, then call this again with "
            f"{'them' if len(names) > 1 else 'it'}."
        )
    for a, vals in choose:
        parts.append(f"{a} is a choice from: {' | '.join(vals)}.")
    if ask:
        parts.append(
            f"No tool supplies {' and '.join(ask)} — take "
            f"{'those values' if len(ask) > 1 else 'that value'} from the author's request, or "
            f"ASK THE AUTHOR for {'them' if len(ask) > 1 else 'it'}, then call this again. "
            "Do NOT guess."
        )
    return " ".join(parts)


async def _stream_with_tools(
    model_source: str,
    model_ref: str,
    user_id: str,
    messages: list[dict],
    gen_params: dict,
    tools: list[dict],
    knowledge_client,
    session_id: str,
    project_id: str | None,
    seed_usage: tuple[int, int] | None = None,
    composer_model: tuple[str, str] | None = None,
    composer_system_prompt: str | None = None,
    planner_model_ref: str | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    admin_token: str | None = None,
    # S02 fix — the session's already-resolved {book_id, chapter_id, project_id} (from editor/
    # book/studio context), so backend tool args that OMIT a required context-id get it filled
    # server-side. A mid-tier model doesn't transcribe the id from the prose note (the measured
    # VALIDATION-loop blocker); this supplies it deterministically. See _inject_context_ids.
    context_ids: dict | None = None,
    # CP-3 — the session's live plan, or None. When present, the executor SUPPLIES bound arguments
    # at the dispatch chokepoint and records what each step handed forward. `plan_events_out`
    # collects the events for the caller to persist: STATE has exactly one writer (§0.11), and this
    # loop is not it.
    plan_turn=None,
    plan_events_out: list | None = None,
    discovery_catalog: list[dict] | None = None,
    discovery_extra_frontend: list[dict] | None = None,
    discovery_seed_names: set[str] | None = None,
    curated: bool = False,
    activation_state: dict | None = None,
    surface_tracker=None,
    effective_limit: int | None = None,
    compact_target: int | None = None,
    # Model-context-aware tool-surface budgeting (tool_surface.py's
    # HOT_SEED_TOKEN_BUDGET / ACTIVATED_TOOLS_TOKEN_BUDGET scale up for a session
    # model with a larger real context_length instead of every model getting the
    # same flat cap). None (e.g. the sub-agent nested call) ⇒ the flat default.
    context_length: int | None = None,
    permission_mode: str = "write",
    decision_check=None,
    hooks: list[dict] | None = None,
    subagent_tool: dict | None = None,
    subagent_defs: dict[str, dict] | None = None,
    subagent_depth: int = 0,
    allowed_tool_names: set[str] | None = None,
    trace: "TraceAccumulator | None" = None,
    stateful: bool = False,
    previous_response_id: str | None = None,
    delta_messages: list[dict] | None = None,
    # WS-2b — the curated workflows visible this turn (registry-fetched, degrade-safe).
    # Non-empty ⇒ advertise workflow_list/workflow_load and dispatch them consumer-locally.
    turn_workflows: list[dict] | None = None,
    # P-1 step-runner (Track C) — DRIVE the pinned rail within the turn. rail_specs = the
    # pinned rails' (slug, steps); rail_book_id + rail_grant_ok + rail_turn_start_counts +
    # rail_async_tools come from the turn-start probe/grant. Empty/None ⇒ the driver is inert
    # (exactly today's behavior). See decide_rail_drive (SDK harness) + rail_progress.next_actionable_step.
    rail_specs: list[tuple] | None = None,
    rail_book_id: str | None = None,
    rail_grant_ok: bool = False,
    rail_turn_start_counts=None,
    rail_async_tools: frozenset[str] = frozenset(),
    # Action-space gating (2026-07-26) — the turn-start RailProgress objects for the pinned
    # rails, used with `settings.rail_action_gate_mode` to bind the ADVERTISED tool set to the
    # rail's progress (drop a finished step's tool so a weak model can't repeat it). None/empty
    # ⇒ no gating (the advertise surface is byte-identical). See rail_gate_suppressions.
    rail_progress: list | None = None,
    # D-FJ-17 — the rails THIS turn's user message pinned (intent_pinned_workflows), as
    # distinct from the ones the standing mode binding pins. Empty ⇒ no preference.
    rail_intent_slugs: frozenset[str] = frozenset(),
    # D-FJ-21 — tools this session keeps failing at identically (cross-turn). The rail must
    # not keep driving a step that needs one. See db/tool_call_history.stuck_tools_from_calls.
    rail_stuck_tools: frozenset[str] = frozenset(),
    # R1 — this turn's request, so the advertise chokepoint can guarantee that a tool whose
    # own declared vocabulary answers it reaches the wire. Empty ⇒ inert.
    request_text: str = "",
    # D-FJ-22 — catalog tools the user named literally this turn. See _tools_named_in_request.
    rail_named_tools: frozenset[str] = frozenset(),
    # True on a RESUME that suspended mid-rail: the rail is definitionally in flight, so the
    # driver may fire even though this turn's only action was the (frontend) confirm — which
    # executes off the backend chokepoint and so is not in turn_succeeded.
    rail_in_flight: bool = False,
    # Phase G · G1 (GOV-13): the user's message contains an explicit abandon phrase ("skip the
    # plan", "just write"). The DETERMINISTIC escape hatch — when True the enforcing drive releases
    # the hold this turn instead of re-driving. Never an LLM guess; computed at the call site.
    rail_user_abandoned: bool = False,
) -> AsyncGenerator[dict, None]:
    """K21-B — the tool-calling loop.

    Streams a chat turn that may call knowledge-service memory tools
    mid-response. Yields the same chunk dicts as `_stream_via_gateway`
    (`content` / `reasoning_content` / `finish_reason` / `usage`) plus
    `{"tool_call": {...}}` chunks — one per executed tool call — which the
    caller emits as an SSE event and persists.

    Each loop pass is one `client.stream()` call (a separate gateway
    job — usage is summed across passes, design D10). Passes 0..N-2
    stream with `tool_choice="auto"`; the final pass is forced tool-free
    so the model must answer in text, making the loop self-terminating
    (design D7). A provider that rejects tools triggers a one-shot
    tool-free retry (design D8).

    RAID C2 (DR-C2) — ``permission_mode`` ('ask'|'write'|'plan', default 'write'):
    * ask — the advertised server-tool surface filters to tier R (+find_tools);
      frontend tools stay. Defense-in-depth: a non-R server tool call that slips
      through returns a tool-result error, never executes.
    * write — today's surface, PLUS the prompt-once gate: a Tier-A server tool
      not on the user's allowlist suspends the run with a ``tool_approval``
      pending card. ``decision_check`` is an async ``(tool_name, kind='mutation')
      -> 'allow' | 'deny' | None``; the MUTATION read fails OPEN (a DB blip must
      not brick tool calling). Track D S-SPEND adds an ORTHOGONAL, mode-independent
      SPEND gate on the same card machinery: a PAID tool (``_meta.paid``) that is not
      spend-allowlisted suspends regardless of tier OR mode (a paid Tier-R read
      prompts, including in ask mode); its read fails CLOSED (spend is irreversible).
      A paid Tier-A tool raises ONE card carrying both required consent kinds.

      Track C WS-3 — ``decision_check`` returns a DECISION, not a bool, because a
      standing ``deny`` ("Never allow") must BLOCK the call rather than prompt for it:
      re-raising a card for a tool the user permanently refused is the same consent
      defect the deny-list exists to fix. It is deliberately NOT named
      ``approval_check`` any more — a leftover ``bool(await approval_check(...))``
      would read the string ``"deny"`` as TRUE and silently invert a refusal into a
      grant, so the rename makes any un-migrated caller fail loudly instead.
    * plan (RAID B2, 07S §5b) — the ask surface PLUS the PlanForge ``plan_*``
      tools. ``plan_*`` tools run WITHOUT the C2 Tier-A approval prompt (the
      gate is write-mode-only by design — planning artifacts are the mode's
      whole point and are reversible plan_runs rows); any other non-R server
      tool feeds a plan-mode tool-result error, never executes.
    """
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
        idle_read_timeout_s=settings.llm_stream_idle_read_timeout_s,
    )
    try:
        # Stateful CONTINUE sends the DELTA on pass 0 (the server holds the history);
        # ESTABLISH / stateless send the full `messages`. `messages` (full) is retained
        # for the E1 re-establish fallback below. _initial_working_len marks the end of
        # pass-0 content so E1 can splice full-context + the tool results appended since.
        _continuing = bool(stateful and previous_response_id and delta_messages is not None)
        working: list[dict] = list(delta_messages) if _continuing else list(messages)
        _initial_working_len = len(working)
        # C6: on a resume pass, seed the token totals from the suspended first
        # run so the final usage is summed across both runs (design D10).
        total_input = seed_usage[0] if seed_usage else 0
        total_output = seed_usage[1] if seed_usage else 0
        # Prompt-cache split (§7) summed across this turn's tool-loop iterations, the
        # same way total_input sums the re-sent prompts. Not seeded from a resume — a
        # suspended run's cache split is transport-ephemeral, not billed state.
        total_cache_creation = 0
        total_cache_read = 0
        # Stateful /v1/responses chain (P2 §5/E2). `_chain_id` starts at the head to
        # continue from (None = establish) and advances to each iteration's returned
        # response_id; the FINAL value is the turn's chain head to persist.
        # `_stateful_sent` marks how much of `working` the server already holds, so each
        # stateful iteration sends only the NEW messages (the delta) — the tool-loop
        # re-send collapse (E2). Stateless mode ignores both (sends full `working`).
        _chain_id = previous_response_id
        _stateful_sent = 0
        # P3 §9 — the true single-call context size (the accumulated server-side size in
        # stateful mode), tracked as the LAST completion's input_tokens. Distinct from
        # total_input, which SUMS the tool-loop's re-processing (4 iterations ≈ 4× the
        # real context) and would make the window-boundary guard fire ~4× too early.
        _last_call_input = 0
        # W1/observability (context-explosion fix #5) — count provider completions
        # this turn. `total_input` is the SUM across them (each tool-loop iteration
        # re-sends the full prompt incl. tool schemas), so a turn's input_tokens
        # only makes sense divided by this count. Surfacing it closes the "~103K
        # unaccounted" gap that hid the tool-loop re-send cost.
        llm_call_count = 0
        max_tokens = gen_params.get("max_tokens")
        if max_tokens is not None and max_tokens <= 0:
            max_tokens = None
        tools_supported = True  # D8 — flipped off if the provider rejects tools

        # ── MCP-fanout C-FT/H9: two-stage tool discovery state ───────────────
        # When `discovery_catalog` is provided (universal /chat surface), the
        # pass advertises {core} ∪ {full schemas of active_tool_names}; a
        # find_tools result unions matched names into the active set so the NEXT
        # pass advertises them. H9: only passes that execute a Tier-A/W WRITE
        # decrement the budget — find_tools + Tier-R reads are free — so
        # discovery never starves the write budget.
        discovery = discovery_catalog is not None
        cat_index = _catalog_index(discovery_catalog) if discovery else {}
        extra_fe = discovery_extra_frontend or []
        # RAID C2 — name→def index for the NON-discovery path, so ask-mode
        # defense-in-depth can read a called tool's tier from the caller's defs.
        plain_index = {} if discovery else _catalog_index(tools)
        # C-FT hot set: the surface's own domains are seeded into the active set so
        # their full schemas are advertised on pass 1 (no find_tools round-trip) —
        # the long tail is still discovered on demand. find_tools unions more names
        # in as the agent searches.
        active_tool_names: set[str] = set(discovery_seed_names or ())
        write_passes = 0  # H9 — budget is counted in write passes, not all passes
        # W1 — the advertised tool schemas are token-measured ONCE per turn, on
        # the first pass that offers tools (the advertise chokepoint), split
        # frontend-tools vs server/MCP tools; the consumer folds the chunk into
        # the contextBudget frame at finish.
        schema_tokens_reported = False
        # H7 — same-op Tier-A auto-write counter (resets never within a turn).
        tier_a_op_counts: dict[str, int] = {}
        # #18 — per-turn planner-call counter (mechanical hard-stop on the self-recheck loop).
        planner_call_counts: dict[str, int] = {}
        # D-BLANK-TOOL-ARGS-LOOP — per-turn count of blank/missing-required-args
        # tool calls, SHARED across find_tools-blank-intent and any generic
        # backend tool's validation failure (see BLANK_TOOL_ARGS_CAP above).
        blank_tool_args_streak = 0
        # Track C Phase 2 — the REPEATED-READ breaker. H7's cap bounds runaway WRITES; there
        # was nothing at all bounding a runaway READ, because a read is "harmless". It is not:
        # measured on a live S06/S01 run, gemma called `glossary_list_system_standards`
        # TWENTY-FOUR times in one scenario. Its result is 44,000 chars (~11k tokens) — a
        # THIRD of the turn's whole budget, per call — so each repeat both wasted a pass and
        # crowded the context that would have carried the answer, and the model, unable to
        # see what it had already fetched, fetched it again. The run made 24 tool calls and
        # built nothing.
        #
        # Same tool + same args + already succeeded ⇒ the answer is ALREADY in context. Feed
        # that back as an error instead of re-running it (no silent no-op: the model is told
        # exactly why, and told to use what it has).
        # (tool+args) -> (fingerprint of the last result, how many times that SAME result came back)
        read_call_results: dict[str, tuple[str, int]] = {}
        # Idempotent-no-op WRITE breaker (2026-07-25, kg_project_create loop) — the read
        # breaker above is READS-ONLY by design ("a repeated WRITE is not a loop — six
        # book_create calls create six books"). But a create-or-get write that reports it
        # made NOTHING (`created: False`, e.g. kg_project_create when the book's project
        # already exists) is the one write that IS provably pointless to repeat — the
        # world did not change and the byte-identical call will return the same "already
        # exists" every time. Measured live: gemma re-called kg_project_create ~5×/turn
        # (bounded only by TIER_A_SAME_OP_CAP) on a book whose project already existed,
        # burning a full tool-loop pass each time. Keyed (tool+args) -> count of no-op
        # results this turn; the 2nd identical call is short-circuited with a forward steer.
        noop_write_counts: dict[str, int] = {}
        # Repeated-FAILURE breaker state (2026-07-26): per-turn, per-tool, per-ERROR count of
        # FAILED calls — {tool: {error_sig: count}}. Keyed on the ERROR, not the args, because a
        # weak model varies the args each retry (measured: book_get_chapter ×19, each a DIFFERENT
        # hallucinated chapter_id) yet hits the IDENTICAL error — an (tool,args) key would never
        # repeat and never fire. Same error N times = the model isn't making progress = a loop; a
        # DIFFERENT error (or success) means it changed something, so that key is fresh and runs.
        # A SUCCESS clears the tool's whole map (the loop is broken). Distinct from
        # noop_write_counts (created=false SUCCESSES) and read_call_results (identical SUCCESSES).
        fail_by_tool_error: dict[str, dict[str, int]] = {}
        # D-XWIRE-RESULT — every `*_id` this turn has PUBLISHED to the model, and the key it was
        # published under. Turn-scoped on purpose: it is evidence about what this conversation was
        # told, not a cache of the world, and an id that belonged to a previous turn's book must
        # never authorise a substitution in this one.
        _id_ledger = IdLedger()
        for _k in ("book_id", "chapter_id", "project_id"):
            _id_ledger.note(_k, (context_ids or {}).get(_k))
        # Per-tool count of repeats this turn that the repeated-READ breaker BLOCKED. It cannot
        # live in `read_call_results`: that map only advances after a real dispatch, and a blocked
        # call never reaches one — which is why the breaker's message said "3 times" on the 3rd
        # attempt and still said "3 times" on the 194th. Counting the blocks is what makes both the
        # message true and the de-advertise escalation possible.
        repeat_block_counts: dict[str, int] = {}
        # Tools the repeated-READ breaker took off the wire. A SEPARATE set from
        # `failure_suppress` even though both feed `_suppress`: the withheld column records a
        # stage and a reason per tool, and filing a de-advertised READ under "repeated-failure
        # breaker gave up" would put a false reason in the one column built to stop exactly that.
        # These tools did not fail — they answered, identically, and were asked anyway.
        repeat_read_suppress: set[str] = set()
        # De-advertise escalation — once the breaker fires for a tool, a WEAK model keeps
        # RE-EMITTING the same call and ignoring the steer (measured: book_get_chapter emitted 19×,
        # only 2 dispatched, the rest short-circuited but the model spun anyway). Short-circuiting
        # DISPATCH isn't enough; take the tool OFF THE WIRE so it physically cannot be re-emitted,
        # forcing the model to the fix the error names (a different tool) or an honest answer. Same
        # reactive pattern as the oneshot de-advertise + rail gate. Unioned into `_suppress`.
        failure_suppress: set[str] = set()
        # oneshot-deadvertise (2026-07-25) — the per-turn set of completed one-shot creates to
        # keep OFF the wire (mode="per_turn": populated when the no-op breaker fires; resets each
        # invocation). mode="existence" computes its set from context at each advertise; mode=
        # "session" removes the tool from activation_state instead (persists across turns).
        oneshot_suppress: set[str] = set()
        _oneshot_mode = settings.oneshot_deadvertise_mode
        # Action-space gating mode (2026-07-26) — read once; drives rail_gate_suppressions at the
        # advertise chokepoint below. "off" ⇒ inert. Only ever suppresses a rail STEP tool.
        _rail_gate_mode = settings.rail_action_gate_mode
        # F18 — tool_list exhaustion state (see TOOL_LIST_CATEGORY_CAP). tool_list returns the
        # WHOLE category at once, so a re-list is a loop; track per-category list counts + the
        # per-turn total so a repeat switches to auto-load+steer and a persistent spammer gets
        # tool_list de-advertised (suppress_tool_list is read at the advertise chokepoint below).
        listed_categories: dict[tuple[str, bool], int] = {}
        # CP-0.2 — drops made by the TOKEN BUDGETER, accumulated here and flushed into the next
        # `advertised` chunk. This is the narrowing the column was built for and the one it first
        # shipped without: the other stages (oneshot, rail gate, failure breaker, permission mode)
        # decide at advertise time and were easy to catch there, while the budgeter decides at
        # ACTIVATION time — a different moment, several call sites away — so instrumenting the
        # advertise chokepoint alone captured every narrowing except the one that founded this work.
        _budget_withheld: list[dict] = []
        tool_list_total = 0
        suppress_tool_list = False
        # ── P-1 step-runner state (Track C) ──────────────────────────────────────
        # turn_succeeded — tools that SUCCEEDED this turn (backend chokepoint only), merged with
        # the turn-start DB counts to tell "the async job already started" from "not yet". Never
        # overrides an artifact verdict (that is compute_rail_progress's job).
        turn_succeeded: Counter = Counter()
        rail_redrive_count = 0           # per-turn cap on how many times the server re-drives
        narrated_write_nudges = 0        # D-NARRATED-WRITE — per-turn cap (see the guard)
        data_question_nudges = 0         # DQ-T30 — per-turn cap (see the guard)
        # D-NARRATED-WRITE — every pass's prose, accumulated for the WHOLE turn.
        # `text_parts` is re-created per pass, so scanning it alone misses the common
        # case: the model announces the write in one pass ("I will now create the 5
        # scenes"), reads a few tools, then closes in a later pass whose text no longer
        # repeats the tool name. The claim and the silence are in different passes.
        turn_text_parts: list[str] = []
        turn_attempted: set[str] = set()  # D-NARRATED-WRITE — see the update site
        rail_nudge_counts: Counter = Counter()   # per-step: how many times we've nudged it
        rail_twice_nudged: set[str] = set()      # a step the model ignored twice → give up on it
        # Set when the step-runner injected at least one synthetic '[SYSTEM DIRECTIVE]' nudge
        # this turn. In stateful mode that nudge is chained onto the provider's server-side
        # response chain (working[_stateful_sent:] is sent as a delta) — our own DB history
        # excludes it, but the provider chain would carry it into future turns. So when this is
        # set we DROP the persisted chain head at turn end (yield response_id=None), forcing the
        # next turn to re-establish a fresh chain from nudge-free history. Costs one turn's
        # stateful cache reuse on a (rare) driven turn; keeps the ephemeral nudge ephemeral.
        rail_drove_this_turn = False
        # D-REASONING-LOOP — per-turn steer-intervention counter for a reasoning-channel
        # thrash (a loop emitting NO tool call, invisible to every tool-call breaker).
        # `_suppress_reasoning_next_pass` forces the retry pass to reason OFF so it can't
        # immediately re-enter the same deliberation loop.
        reasoning_loop_interventions = 0
        _suppress_reasoning_next_pass = False
        # D-SILENT-TURN-NO-CARD-NO-PROSE — same counter shape, its own budget.
        degenerate_pass_interventions = 0
        # The rail's own step tools (across all pinned rails) — the "a rail step actually
        # succeeded this turn" gate that keeps the driver SILENT on pure-conversation turns.
        _rail_all_step_tools: set[str] = set()
        for _rs in (rail_specs or []):
            for _st in (_rs[1] if isinstance(_rs, (list, tuple)) and len(_rs) > 1 else []):
                if isinstance(_st, dict) and _st.get("tool"):
                    _rail_all_step_tools.add(str(_st["tool"]))
        # Hard safety bound on TOTAL passes (reads + writes + discovery) so a
        # pathological find_tools/read loop can't spin forever even though those
        # don't count against the write budget.
        max_total_passes = max_iterations * 3

        async def _loop_summarizer(_middle: list[dict]) -> str:
            return await _summarize_for_compaction(
                _middle, model_source=model_source, model_ref=model_ref, user_id=user_id,
            )

        # D-PASS-TEXT-REECHO — all content ACCEPTED (streamed to the user) this turn,
        # across passes. Gemma re-emits its full prior reply VERBATIM at the start of
        # each continuation pass after a tool round, so an N-tool-round turn rendered
        # the same paragraphs N+1 times (measured live: 943→1884 chars, then a 4-copy
        # bubble). Each pass's opening tokens are held while they prefix-match this
        # accumulator; a full match is swallowed, a divergence is flushed unchanged.
        turn_text_so_far = ""
        # D-FJ-19 — True when the PREVIOUS pass ended by injecting a synthetic role=user
        # directive (rail re-drive, narrated-write nudge). Such a pass answers a NEW
        # instruction, so its prose is a separate answer and needs a seam. A pass that merely
        # follows tool RESULTS is a continuation of the same thought and must NOT be broken —
        # pinned by test_one_tool_pass_then_text_pass, where the model streams "Let me check."
        # then " Kai is a knight." and the existing join is already right.
        _directive_before_this_pass = False
        iteration = -1
        while True:
            iteration += 1
            if iteration >= max_total_passes:
                break
            # A4 — the tool loop GROWS `working` each pass (assistant tool_calls +
            # results), so re-compact before every provider call or a long multi-tool
            # turn overflows the window mid-turn. Atom-grouped truncation keeps
            # tool-call/result pairs intact; guarded so it can never break the pass.
            #
            # SKIP in stateful mode (P3 review H2): the full history lives server-side in
            # the /v1/responses chain, NOT in `working` (which holds only the delta), so
            # compacting `working` saves nothing — and it MUTATES `working` to a different
            # length, corrupting the absolute `_stateful_sent`/`_initial_working_len`
            # indices (→ an empty/wrong delta slice that silently drops tool results). The
            # chain's size is instead bounded by decide_chain rule-4 (reestablish_window).
            if effective_limit and not stateful:
                _rc = None
                try:
                    working, _rc = await compact_messages(
                        working, effective_limit=effective_limit,
                        target=compact_target, summarize=_loop_summarizer,
                        add_breadcrumb=settings.compact_breadcrumb_enabled,
                        collapse_duplicates=settings.compact_collapse_duplicates_enabled,
                    )
                    if _rc.triggered:
                        logger.info(
                            "in-loop compaction session=%s pass=%d steps=%s %d→%d overflow=%s",
                            session_id, iteration, _rc.steps,
                            _rc.tokens_before, _rc.tokens_after, _rc.overflowed,
                        )
                except Exception:
                    logger.warning("in-loop compaction skipped (error)", exc_info=True)
                # W1 — surface the compaction to the client (only when it DID
                # something). Yielded outside the guard try so a consumer-side
                # throw is never swallowed as a "compaction error".
                if _rc is not None and _rc.did_work:
                    yield {"compaction": _rc.to_event()}
            # The write budget — NOT the total-pass count — decides the forced
            # tool-free final pass (D7). Once the write budget is spent, the next
            # pass must answer in text.
            last_iter = write_passes >= max_iterations - 1
            # Stateful (P2 §5): send only the messages the server does NOT already hold
            # (working[_stateful_sent:]) chained onto the prior response id. Stateless:
            # send the full working list (today's behavior). `_stateful_sent` is advanced
            # to len(working) right after — before this pass's tool results are appended.
            if stateful:
                _messages_out = working[_stateful_sent:]
                if _stateful_sent > 0:
                    # Continuation pass (P3 review M4): the slice is the new tool
                    # exchanges (non-system). The Responses API does NOT inherit
                    # `instructions` across previous_response_id, so RE-PREPEND the
                    # current system messages (persona/grounding/tool-use rules) or the
                    # model loses them while interpreting tool results mid-turn.
                    _sys = [m for m in working if m.get("role") == "system"]
                    _messages_out = _sys + [
                        m for m in _messages_out if m.get("role") != "system"
                    ]
            else:
                _messages_out = working
            request_kwargs: dict = {
                "model_source": model_source,
                "model_ref": model_ref,
                "messages": _messages_out,
            }
            if stateful:
                request_kwargs["stateful"] = True
                if _chain_id:
                    request_kwargs["previous_response_id"] = _chain_id
                _stateful_sent = len(working)
            if gen_params.get("temperature") is not None:
                request_kwargs["temperature"] = gen_params["temperature"]
            if gen_params.get("top_p") is not None:
                request_kwargs["top_p"] = gen_params["top_p"]
            if max_tokens is not None:
                request_kwargs["max_tokens"] = max_tokens
            # Offer tools unless the provider rejected them (D8) or this
            # is the forced-final pass (D7 — must answer in text).
            offered_tools = tools_supported and not last_iter
            if offered_tools:
                # RAID C2 (DR-C2) — ask-mode filtering happens HERE, at the single
                # per-pass advertise chokepoint: discovery filters inside
                # _advertise_discovery_tools; the plain path through
                # _filter_tools_for_ask. Write mode is a byte-identical no-op.
                if discovery:
                    # oneshot-deadvertise: compute which completed one-shot creates to drop
                    # from THIS advertise, per the configured mode.
                    #   existence — stateless, decided from context (the resource id is already
                    #     present ⇒ the create's target exists ⇒ never advertise it). Decided
                    #     once-per-turn-shape ⇒ prefix-cache-stable (the Manus lesson).
                    #   per_turn  — the reactive per-invocation set the no-op breaker fills.
                    #   session / off — no advertise-time suppression here (session removes the
                    #     tool from active_tool_names upstream; off advertises as before).
                    if _oneshot_mode == "existence":
                        _suppress = {
                            t for t, key in ONESHOT_CREATE_TOOLS.items()
                            if (context_ids or {}).get(key)
                        }
                    elif _oneshot_mode in ("per_turn", "session"):
                        # both reactive modes drop it for the rest of THIS turn once seen;
                        # "session" ALSO removed it from activation_state so it stays gone.
                        _suppress = oneshot_suppress
                    else:
                        _suppress = frozenset()
                    # rail action-space gating (2026-07-26) — bind the advertised tool set to the
                    # rail's progress, advanced by THIS turn's successes (turn_succeeded), so a
                    # finished step's tool leaves the wire mid-turn — the intra-turn repeat killer.
                    # Union with the oneshot suppression; "off" returns empty (byte-identical).
                    if _rail_gate_mode != "off" and rail_progress:
                        _rail_suppress = rail_gate_suppressions(
                            rail_progress, turn_succeeded, _rail_gate_mode
                        )
                        if _rail_suppress:
                            # 🔴 A SATISFIED RAIL STEP MEANS THE RAIL NEED NOT DRIVE IT AGAIN.
                            # IT MUST NOT MEAN THE AUTHOR MAY NO LONGER ASK.
                            #
                            # MEASURED 2026-08-14 (sessions 019ffff4 / 01a00003-5, three runs
                            # each): turn 1 asked "What canon rules have I declared for this
                            # book?", composition_list_canon_rules ran, and the answer was right.
                            # The RE-ASK was then withheld at `rail_gate: rail step already
                            # satisfied (mode=done_suppress)` on EVERY pass — 14 of them — so the
                            # one tool that answers the question was off the wire, and the model
                            # thrashed through twelve OTHER composition tools before answering
                            # from conversation memory. That is DQ-T30's mechanism, and it is
                            # sharper than the DQ's own wording: a completed rail does not merely
                            # stop driving, it actively REMOVES the answering read.
                            #
                            # The gate conflates two claims that are only the same for a WRITE.
                            # "This step is done" -> a second write would duplicate data, so drop
                            # it. For a READ there is nothing to duplicate: re-reading IS the
                            # freshness the author asked for. So a rail-gated READ whose own
                            # declared vocabulary answers THIS request is reclaimed here.
                            #
                            # Deliberately narrow, and reclaimed BEFORE the breakers below rather
                            # than after: `failure_suppress` (gave up after repeated errors) and
                            # `repeat_read_suppress` (hammering the same read) are LOOP breakers
                            # and still win, because those describe a model misbehaving now, not
                            # a journey that finished earlier.
                            _reclaimed_reads = {
                                n for n in _rail_suppress
                                if n in cat_index and tool_tier(cat_index[n]) == "R"
                                and answerable_tools(request_text, [cat_index[n]])
                            }
                            if _reclaimed_reads:
                                logger.info(
                                    "rail gate: reclaiming %s — a satisfied rail step must not "
                                    "take an answering READ off the wire",
                                    sorted(_reclaimed_reads),
                                )
                                _rail_suppress = set(_rail_suppress) - _reclaimed_reads
                            if _rail_suppress:
                                _suppress = set(_suppress) | _rail_suppress
                    # De-advertise escalation — a tool the repeated-failure breaker gave up on is
                    # taken off the wire so a weak model can't keep re-emitting it (dispatch is
                    # already short-circuited; this stops the wasted EMIT passes too).
                    if failure_suppress:
                        _suppress = set(_suppress) | failure_suppress
                    if repeat_read_suppress:
                        _suppress = set(_suppress) | repeat_read_suppress
                    advertised = _advertise_discovery_tools(
                        cat_index, active_tool_names, extra_fe,
                        permission_mode=permission_mode,
                        has_workflows=bool(turn_workflows),
                        suppress_tool_list=suppress_tool_list,
                        suppress_names=_suppress,
                        book_bound=bool((context_ids or {}).get("book_id")),
                        request_text=request_text,
                    )
                else:
                    advertised = (
                        _filter_tools_for_ask(tools, permission_mode)
                        if permission_mode in ("ask", "plan") else tools
                    )
                    # The de-advertise has to hold on THIS branch too. Every suppression above
                    # is wired only into the discovery chokepoint, so a breaker that fires on a
                    # plain (or nested-subagent) turn would take the tool off no wire at all —
                    # a mechanism that runs and changes nothing, which is worse than one that
                    # was never written because it reads as covered. The discovery path records
                    # the drop in the withheld column; this one has no such column, so it logs.
                    #
                    # BOTH breakers, not just the read one. Measured: one session on 2026-07-26
                    # shows the repeated-FAILURE breaker starting mid-session — the 04:47 turn
                    # emitted 30 `book_get_chapter` failures with ZERO steers, and the 05:04 turn
                    # emitted 2 failures then 22 steers. The breaker was working. The
                    # de-advertise beside it was not: 22 blocked emissions across 23 iterations
                    # means the tool never left the wire. `failure_suppress` was discovery-only,
                    # and the earlier fix here covered `repeat_read_suppress` alone — which made
                    # the asymmetry mine. A breaker that says "I took it off the wire" and did
                    # not is the same silent seam either way.
                    _plain_suppress = repeat_read_suppress | failure_suppress
                    if _plain_suppress:
                        _before = len(advertised)
                        advertised = [
                            td for td in advertised
                            if (td.get("function") or {}).get("name")
                            not in _plain_suppress
                        ]
                        if len(advertised) != _before:
                            logger.info(
                                "breaker de-advertise on the plain path: %s",
                                sorted(_plain_suppress),
                            )
                    # P5 REG-P5-01 — a nested subagent sub-run advertises its scoped
                    # set, which carries `_meta` (read by the tier filter just above /
                    # ask-mode). Strip it before the wire. Gated to the nested case so
                    # the top-level non-discovery path stays byte-identical (the
                    # discovery path already strips inside _advertise_discovery_tools).
                    if allowed_tool_names is not None:
                        advertised = [strip_tool_meta(td) for td in advertised]
                # T6/D6 (Context Budget Law) — advertise conversation_search, the
                # recovery net that lets the agent pull a fact back from THIS
                # conversation's raw turns after it scrolled out / was compacted.
                # Appended like run_subagent, but ONLY when the pass already offers
                # tools — a tool-free turn must NOT be forced onto the tool path
                # (test_no_tools_no_schema_chunk) — and only at depth 0 (a nested
                # subagent runs its own scoped surface). Gated on `advertised` here
                # (BEFORE the run_subagent append) so the guard reflects the real
                # tool surface, not run_subagent itself.
                if subagent_depth == 0 and advertised:
                    advertised = list(advertised) + [CONVERSATION_SEARCH_TOOL]
                    # B1 / WS-1.9 — also advertise chat_search_sessions (CROSS-session recall of
                    # what the user told the assistant). Executed only for assistant sessions
                    # (the execute branch gates on session_kind — spec 07 §Q4), so advertising it
                    # everywhere is harmless: a non-assistant session that calls it gets zero.
                    advertised = list(advertised) + [CHAT_SEARCH_SESSIONS_TOOL]
                # P5 REG-P5-01 — advertise run_subagent as an always-on tool at the
                # top level (depth 0 only → a subagent can never spawn another).
                # Injected AFTER the ask/plan filter so delegation stays available in
                # every mode (the nested run is clamped read-only, so it's safe).
                if subagent_tool is not None and subagent_depth == 0:
                    advertised = list(advertised) + [subagent_tool]
                # ── CP-2.7 · THE ARM, AT THE POINT WHERE EVERY PATH HAS ALREADY CONVERGED ──────
                # 🔴 **MEASURED FAILURE, 2026-08-09, ON A REAL TURN AGAINST A REAL MODEL.** The
                # branch used to live only inside `_advertise_discovery_tools`, documented as *"the
                # single ADVERTISE chokepoint … one edit covers every path a turn can take to the
                # wire"*. It was not. A plain tool-calling client takes the `else` arm — a bare
                # `tool_defs = catalog` that never calls the function — and the first served turn on
                # the new arm advertised **318 legacy declarations** while the row was stamped
                # `runtime_variant='agentruntime'`. That is worse than either fault alone: it
                # attributes the legacy surface's behaviour to the new runtime, so the comparison
                # would have been computed over a mislabelled arm.
                #
                # It also had to move BELOW the appends. `conversation_search`,
                # `chat_search_sessions` and `run_subagent` are legacy declarations added after the
                # fork, so a branch placed above them leaks three tools no manifest admitted —
                # CP-2.7 item B (*no legacy declaration is reachable, by ANY route*) fails on a
                # technicality that is not a technicality.
                #
                # `advertised` is final here: every producer and every append is upstream, and the
                # instrument below records exactly what goes to the wire.
                if settings.agentruntime_arm:
                    advertised = _agentruntime_wire_surface(pass_number=iteration + 1)
                # ── D-R1-MATCHED-THE-TOOL-AND-IT-NEVER-REACHED-THE-WIRE ──────────────────────
                # R1 answerability is a GUARANTEE — "a tool whose own declared vocabulary answers
                # the request reaches the wire" — and several fixes are built on it. It was
                # possible for the builder to force a tool and for that tool to be absent here,
                # with nothing in between saying so: every skip INSIDE the builder logs, so the
                # log read "matched" and the tool simply was not on the surface.
                #
                # MEASURED 2026-08-26 (batch c-booksync1, K=5): glossary_book_sync_apply matched
                # on 5/5 (its declared synonym is in the request verbatim), no skip was logged,
                # and it was absent from the advertised set on all 6 passes of every run while its
                # sibling glossary_book_sync_available was present. Calling the builder directly
                # in the deployed container returns the tool, so the drop is downstream of it.
                #
                # This does not FIX the drop — it makes it impossible for the next one to be
                # silent. `advertised` is final at this point (the comment above says so), so a
                # forced name missing here was removed by something that never registered it.
                _r1_promised = _R1_FORCED.get()
                # 🔴 LOG THE KEPT CASE TOO, not only the broken one. This file's own note says
                # "R1 HAS NO OBSERVABILITY, AND THAT COST TWO MEASUREMENTS" — and a check that
                # speaks only on failure cannot tell "the guarantee held" from "the check never
                # ran", which is exactly the ambiguity that cost a third. Measured 2026-08-26:
                # the broken-case warning stayed silent on a batch where the tool was provably
                # absent from the wire, and there was no way to tell which of the two it meant.
                logger.info(
                    "R1 answerability: %d promised for pass %s, %d on the wire (session=%s)",
                    len(_r1_promised), iteration + 1,
                    len(_r1_promised & {
                        (td.get("function") or {}).get("name")
                        for td in advertised if isinstance(td, dict)
                    }), session_id,
                )
                if _r1_promised:
                    _wire_names = {
                        (td.get("function") or {}).get("name")
                        for td in advertised if isinstance(td, dict)
                    }
                    for _lost in sorted(_r1_promised - _wire_names):
                        instrument.record_surface_withheld(
                            _lost, stage="r1_forced_then_dropped",
                            reason="R1 answerability forced it onto this pass and it is absent "
                                   "from the final wire — removed downstream of the builder by a "
                                   "narrowing that registered nothing",
                        )
                        logger.warning(
                            "R1 answerability BROKEN: %s was forced onto pass %s and is NOT on "
                            "the wire (session=%s)", _lost, iteration + 1, session_id,
                        )
                    _R1_FORCED.set(frozenset())
                # ── CP-0.1 / CP-0.2 · THE INSTRUMENT, at the one chokepoint every pass goes through ──
                # Emitted on EVERY pass, deliberately unlike the `schema_tokens` chunk above, which
                # reports once per turn (`schema_tokens_reported`). Once-per-turn is precisely the
                # shape that cannot see the defect this exists for: the tool is present on pass 1 and
                # gone on pass 2, so a single sample — whichever pass it lands on — shows a set that
                # looks entirely unremarkable. The difference between passes IS the finding.
                #
                # Emitted for a tool-FREE pass too (`names: []`). "The model was offered nothing" and
                # "the model was never asked" are different facts, and only one of them is a defect.
                _adv_names: list[str] = []
                for _td in (advertised or []):
                    _fn = _td.get("function") if isinstance(_td, dict) else None
                    _nm = _fn.get("name") if isinstance(_fn, dict) else None
                    if _nm:
                        _adv_names.append(_nm)
                # Every narrowing that ran on this pass registers with WHO decided and WHY. An
                # exclusion with no {tool, stage, reason} is a defect, not a policy (§0.3) — and
                # each stage below is a real suppression already happening today, unrecorded.
                _withheld_now: list[dict] = []
                if discovery:
                    if _oneshot_mode == "existence":
                        _withheld_now += [
                            {"tool": t, "stage": "oneshot_existence",
                             "reason": "target resource already exists in this turn's context"}
                            for t in sorted(_suppress) if t in ONESHOT_CREATE_TOOLS
                        ]
                    elif _oneshot_mode in ("per_turn", "session"):
                        _withheld_now += [
                            {"tool": t, "stage": f"oneshot_{_oneshot_mode}",
                             "reason": "one-shot create already succeeded this turn"}
                            for t in sorted(oneshot_suppress)
                        ]
                    if _rail_gate_mode != "off" and rail_progress:
                        _withheld_now += [
                            {"tool": t, "stage": "rail_gate",
                             "reason": f"rail step already satisfied (mode={_rail_gate_mode})"}
                            for t in sorted(_rail_suppress) if _rail_suppress
                        ]
                    if failure_suppress:
                        _withheld_now += [
                            {"tool": t, "stage": "failure_breaker",
                             "reason": "repeated-failure breaker gave up on this tool"}
                            for t in sorted(failure_suppress)
                        ]
                    if repeat_read_suppress:
                        _withheld_now += [
                            {"tool": t, "stage": "repeat_read_breaker",
                             "reason": "returned the identical result and was re-asked anyway"}
                            for t in sorted(repeat_read_suppress)
                        ]
                    if suppress_tool_list:
                        _withheld_now.append({
                            "tool": TOOL_LIST_NAME, "stage": "suppress_tool_list",
                            "reason": "discovery de-advertised for this surface",
                        })
                # CP-0.2 — the token budgeter's drops, accumulated at ACTIVATION time and flushed
                # here. Outside the `if discovery:` block on purpose: the budgeter runs on the
                # activation path regardless of which advertise branch this pass takes, and gating
                # it on `discovery` would silently drop the narrowing again on every other surface.
                # Drained, not copied, so a drop registers against the pass that caused it.
                if _budget_withheld:
                    _withheld_now += _budget_withheld
                    _budget_withheld = []
                if permission_mode in ("ask", "plan") and not discovery:
                    _filtered_out = sorted(
                        {
                            _f.get("name")
                            for _t in (tools or [])
                            if isinstance(_f := _t.get("function"), dict) and _f.get("name")
                        }
                        - set(_adv_names)
                    )
                    _withheld_now += [
                        {"tool": t, "stage": f"permission_mode_{permission_mode}",
                         "reason": f"write tool not offered in '{permission_mode}' mode"}
                        for t in _filtered_out
                    ]
                # Held, not yielded yet: the existing `schema_tokens` chunk must stay the FIRST
                # side-channel chunk of a tool-bearing turn (test_first_pass_reports_split_schema_
                # tokens asserts that position). An instrument that reorders the stream it observes
                # has changed the thing it measures, so this one waits its turn.
                _adv_ev_pending = {
                    "names": _adv_names,
                    "tool_choice": "auto" if advertised else None,
                    "withheld": _withheld_now,
                }
                if not advertised:
                    # A tool-free pass has no schema_tokens chunk to follow, so it emits here.
                    yield {"advertised": _adv_ev_pending}
                if advertised:
                    request_kwargs["tools"] = advertised
                    request_kwargs["tool_choice"] = "auto"
                    _schema_split: dict[str, int] | None = None
                    if not schema_tokens_reported:
                        schema_tokens_reported = True
                        _fe_tok = 0
                        _mcp_tok = 0
                        for _td in advertised:
                            _fn = _td.get("function") if isinstance(_td, dict) else None
                            _nm = _fn.get("name") if isinstance(_fn, dict) else None
                            _tok = estimate_tokens(json.dumps(_td))
                            # Browser-executed, not merely chat-intercepted — the third
                            # consumer of that distinction (see is_browser_executed). With
                            # is_frontend_tool here, every ui_*/propose_edit schema was
                            # billed to the MCP side, so the W1 frontend/mcp token split
                            # under-reported the UI surface as exactly 0.
                            if _nm and is_browser_executed(_nm):
                                _fe_tok += _tok
                            else:
                                _mcp_tok += _tok
                        _schema_split = {"frontend": _fe_tok, "mcp": _mcp_tok}
                        yield {"schema_tokens": {
                            "frontend_tool_schemas": _fe_tok,
                            "mcp_tool_schemas": _mcp_tok,
                        }}
                    # CP-0.1/0.2 — now, after schema_tokens has kept its first-chunk position. Every
                    # pass emits one, which is the whole point: the once-per-turn `schema_tokens`
                    # above cannot see a surface that CHANGES between passes.
                    yield {"advertised": _adv_ev_pending}
                    # W6 — advertised-surface snapshot at the SAME chokepoint:
                    # split the advertised names core/frontend/activated, group
                    # by owning MCP server, and reuse the W1 token measurement
                    # (never re-estimated — None keeps the tracker's split).
                    # Emits only when the surface actually changed (first pass,
                    # or a later pass after find_tools grew the active set).
                    if surface_tracker is not None:
                        _adv_core: list[str] = []
                        _adv_frontend: list[str] = []
                        _adv_activated: list[str] = []
                        for _td in advertised:
                            _fn = _td.get("function") if isinstance(_td, dict) else None
                            _nm = _fn.get("name") if isinstance(_fn, dict) else None
                            if not _nm:
                                continue
                            if _nm in ALWAYS_ON_CORE_NAMES:
                                _adv_core.append(_nm)
                            elif is_browser_executed(_nm):
                                _adv_frontend.append(_nm)
                            else:
                                _adv_activated.append(_nm)
                        payload_as = surface_tracker.advertised_pass(
                            core=_adv_core,
                            frontend=_adv_frontend,
                            activated=_adv_activated,
                            schema_tokens=_schema_split,
                        )
                        if payload_as is not None:
                            yield {"agent_surface": payload_as}
                        # OBSERVABILITY (F14 agent-behavior monitor) — the exact tool NAMES
                        # advertised to the model on THIS pass. The Agent-runtime panel shows
                        # only COUNTS (core N · frontend N · activated N); when the agent
                        # "refuses" or reaches for the wrong tool, the first question is "did
                        # it even SEE the tool it should have used?" — unanswerable from counts.
                        # INFO so a LOG_LEVEL=INFO deploy records every turn's real surface
                        # (grep for a tool name to see if it was on offer). core NAMES are
                        # logged too, not just the count: F17 retired find_tools FROM the core
                        # set, and "is a (deprecated) core tool still advertised to the model?"
                        # is only answerable from the names — the count alone can't tell
                        # find_tools-gone from some-other-core-tool-added.
                        logger.info(
                            "agent-surface advertised (session=%s): core=%d frontend=%d "
                            "activated=%d | core=%s | frontend=%s | activated=%s",
                            session_id, len(_adv_core), len(_adv_frontend),
                            len(_adv_activated), _adv_core, _adv_frontend, _adv_activated,
                        )
                else:
                    # Ask mode filtered everything out — run the pass tool-free
                    # (an empty tools array 400s on some providers).
                    offered_tools = False
            # CP-0.1 — a pass that offers NO tools is still a pass, and it was recording nothing.
            # The advertise chunk lives inside `if offered_tools:`, so the three ways a pass can run
            # tool-free — the D7 forced-final answer, a provider that rejected tools (D8), and ask
            # mode filtering everything out — left a hole in the per-pass array exactly where the
            # surface CHANGED most sharply. The pass count then under-reports, and a tool present on
            # pass 1 and absent on a tool-free pass 2 reads as "still offered", which is the
            # opposite of the truth and the same failure mode as a scalar column.
            if not offered_tools:
                yield {"advertised": {
                    "names": [],
                    "tool_choice": None,
                    # 🔴 THIS MINTED `tool: "*"` — the sentinel §0.14.3 rejects BY NAME, two
                    # thousand lines from the document forbidding it. A pass offering no tools is a
                    # statement about the PASS, so it carries a scope and no tool, exactly like a
                    # catalogue outage. A sentinel makes every consumer that counts tools return a
                    # wrong answer while still looking correct.
                    "withheld": [{
                        "scope": instrument.SCOPE_PASS, "stage": "pass_offered_no_tools",
                        "reason": ("forced final answer (D7)" if last_iter
                                   else "provider rejected tools (D8) or ask-mode filtered all"),
                    }],
                }}
            # M3 — one observability/cancel job id PER pass (each pass is a
            # separate gateway stream; the active pass is what a disconnect aborts).
            stream_job_id = str(uuid4())
            request_kwargs["stream_job_id"] = stream_job_id
            _apply_reasoning_kwargs(request_kwargs, gen_params)
            if _suppress_reasoning_next_pass:
                # D-REASONING-LOOP — the previous pass looped in the reasoning
                # channel; run THIS steer-retry with thinking DISABLED via the
                # STANDARDIZED no-thinking fields (loreweave_llm.no_thinking_fields:
                # reasoning_effort="none" + chat_template_kwargs.{thinking,
                # enable_thinking:false}). The chat_template_kwargs is what actually
                # suppresses the <think> block on local Qwen3/Gemma (lm_studio/vLLM);
                # reasoning_effort ALONE is ignored (and on Gemma-4 even ENABLES it).
                # (This previously hand-rolled reasoning_effort="none" and POPPED
                # chat_template_kwargs, which stripped the working disable — so the
                # steered retry kept reasoning and re-looped.)
                request_kwargs.update(no_thinking_fields())
                _suppress_reasoning_next_pass = False
            request = StreamRequest(**request_kwargs)

            tool_frags: dict = {}
            text_parts: list[str] = []
            reasoning_parts: list[str] = []  # D-TOOLCALL-GEMMA-TOKEN-LEAK salvage buffer
            # D-TOOLCALL-GEMMA-TOKEN-LEAK cosmetic fix — a leak marker can arrive
            # split across many small deltas; hold back from the earliest point a
            # delta COULD be the start of `<|tool_call>` (exact or partial-at-tail)
            # instead of forwarding every token live, so a confirmed leak never
            # reaches the user's visible content at all. Resolved once the pass
            # ends: dropped if `_extract_leaked_tool_calls` confirms a real leak,
            # flushed as normal content otherwise (a bare `<` in real prose, or a
            # marker that started but never completed, must not be silently lost).
            content_hold = ""
            reasoning_hold = ""
            # D-PASS-TEXT-REECHO — guard only continuation passes with real prior text
            # (a short accumulator is not worth guarding and raises false-hold risk).
            # Matching is whitespace-tolerant at the seams: gemma's re-echo opens with
            # "\n\n" before the copied text (measured live — the exact-prefix first cut
            # missed every real echo because of it), and the copy may drop the turn
            # text's trailing newline. Compare a lstripped probe against the stripped
            # turn text; flush the ORIGINAL buffer on divergence so nothing is lost.
            _turn_norm = turn_text_so_far.strip()
            _echo_scan = iteration > 0 and len(_turn_norm) >= 40
            _echo_buf = ""
            finish_reason: str | None = None
            # D-REASONING-LOOP — one detector per pass, fed BOTH channels. On a trip
            # we abort the stream (hoisted iterator so we can aclose deterministically)
            # and hand off to the steer/cap block after the loop.
            loop_det = ReasoningLoopDetector()
            _looped = False
            _stream_iter = client.stream(request)
            try:
                async for ev in _stream_iter:
                    if isinstance(ev, TokenEvent):
                        if loop_det.feed(ev.delta):
                            _looped = True
                            break
                        _delta = ev.delta
                        if _echo_scan:
                            # D-PASS-TEXT-REECHO — hold the pass's opening tokens while
                            # they verbatim-prefix the text already shown this turn.
                            _echo_buf += _delta
                            _probe = _echo_buf.lstrip()
                            if not _probe:
                                continue  # pure leading whitespace — keep holding
                            if _turn_norm.startswith(_probe):
                                if len(_probe) == len(_turn_norm):
                                    # full re-echo swallowed; stream the rest normally
                                    _echo_scan = False
                                    _echo_buf = ""
                                continue
                            _echo_scan = False
                            if _probe.startswith(_turn_norm):
                                # a delta straddled the echo's end: swallow the echo,
                                # keep only the genuinely-new excess
                                _delta = _probe[len(_turn_norm):].lstrip("\n")
                            else:
                                # diverged → not an echo: flush everything held, unchanged
                                _delta = _echo_buf
                            _echo_buf = ""
                        # D-FJ-19 — a multi-pass turn persists ONE assistant message built by
                        # concatenating every pass's yielded content, and nothing separated
                        # them. Measured live 2026-08-13: "…I can help you set them
                        # up.I checked your consistency rules…" — two answers welded into one
                        # sentence, mid-word to a reader. Any turn the rail re-drives has two
                        # or more passes, so this is the normal shape, not an edge case.
                        # Inserted at the FIRST real delta of a later pass, so a single-pass
                        # turn is byte-identical and an echo-suppressed pass adds nothing.
                        if (
                            not text_parts
                            and _directive_before_this_pass
                            and _delta.strip()
                            and turn_text_so_far.strip()
                            and not turn_text_so_far.endswith("\n")
                        ):
                            _delta = "\n\n" + _delta.lstrip()
                        text_parts.append(_delta)
                        turn_text_so_far += _delta
                        content_hold += _delta
                        flush, content_hold = _split_safe_emit(content_hold)
                        if flush:
                            yield {"content": flush, "reasoning_content": "",
                                   "finish_reason": None, "usage": None}
                    elif isinstance(ev, ReasoningEvent):
                        reasoning_parts.append(ev.delta)
                        reasoning_hold += ev.delta
                        flush, reasoning_hold = _split_safe_emit(reasoning_hold)
                        if flush:
                            yield {"content": "", "reasoning_content": flush,
                                   "finish_reason": None, "usage": None}
                        if loop_det.feed(ev.delta):
                            _looped = True
                            break
                    elif isinstance(ev, ToolCallEvent):
                        slot = tool_frags.setdefault(
                            ev.index, {"id": None, "name": None, "arguments": ""}
                        )
                        if ev.id:
                            slot["id"] = ev.id
                        if ev.name:
                            slot["name"] = ev.name
                        slot["arguments"] += ev.arguments_delta
                    elif isinstance(ev, UsageEvent):
                        total_input += ev.input_tokens
                        total_output += ev.output_tokens
                        total_cache_creation += ev.cache_creation_tok or 0
                        total_cache_read += ev.cache_read_tok or 0
                        _last_call_input = ev.input_tokens
                        llm_call_count += 1
                    elif isinstance(ev, DoneEvent):
                        finish_reason = ev.finish_reason
                        # Stateful (P2 §5/E2): advance the chain head to this pass's
                        # response id so the next tool-loop pass / next turn continues
                        # from it. The final value is the turn's persisted head.
                        if ev.response_id:
                            _chain_id = ev.response_id
            except LLMError as exc:
                # E1 (P2 §6) — a stale previous_response_id: the provider rejected the
                # chain. Re-establish transparently: resend the FULL working context
                # with no chain id, from THIS pass, once. DB is truth; the id was a hint.
                if getattr(exc, "code", "") == "LLM_RESPONSE_CHAIN_NOT_FOUND" and stateful:
                    # Rebuild FULL context (the delta alone would still be history-less)
                    # + any tool results appended since pass 0, then resend from scratch.
                    working = list(messages) + working[_initial_working_len:]
                    _initial_working_len = len(messages)
                    _chain_id = None
                    _stateful_sent = 0
                    continue
                # D8 — provider doesn't support tools: drop tools and
                # retry. Only meaningful when this pass actually offered
                # them; otherwise the error is real and propagates.
                if offered_tools and _is_tools_unsupported(exc):
                    logger.info(
                        "K21-B: provider rejected tools (%s); retrying tool-free",
                        model_ref,
                    )
                    tools_supported = False
                    continue
                raise
            finally:
                # D-REASONING-LOOP — deterministically tear down the aborted stream
                # (we broke out of the async-for; close its generator now rather than
                # leaving the httpx response dangling until GC).
                if _looped:
                    try:
                        await _stream_iter.aclose()
                    except Exception:
                        logger.debug(
                            "D-REASONING-LOOP: stream aclose after abort failed",
                            exc_info=True,
                        )
            # D-REASONING-LOOP — the pass looped in the reasoning/content channel and
            # emitted no usable tool call. Flush held text, then steer (capped) or stop
            # honestly. BEFORE the leaked-call salvage: an aborted loop pass has no
            # legitimate structured call to recover.
            if _looped:
                logger.warning(
                    "D-REASONING-LOOP: session=%s pass=%d aborted a reasoning-channel "
                    "loop (%s) model_ref=%s",
                    session_id, iteration, loop_det.reason, model_ref,
                )
                if trace is not None:
                    trace.add(
                        "compile", "T6", "tools",
                        f"reasoning_loop_aborted:{loop_det.reason[:48]}",
                        is_error=True,
                    )
                if content_hold or reasoning_hold:
                    yield {"content": content_hold, "reasoning_content": reasoning_hold,
                           "finish_reason": None, "usage": None}
                    content_hold = reasoning_hold = ""
                if reasoning_loop_interventions < REASONING_LOOP_INTERVENTION_CAP:
                    reasoning_loop_interventions += 1
                    working.append({
                        "role": "user",
                        "content": (
                            "[SYSTEM DIRECTIVE] You began repeating yourself without making "
                            "progress and the deliberation was cut off. STOP weighing "
                            "alternatives. Choose the single most appropriate tool for the "
                            "user's request and CALL it NOW with the arguments you already "
                            "have — do not explain the choice first. If no tool fits, answer "
                            "the user directly in one short message."
                        ),
                    })
                    # Keep the ephemeral directive out of the persisted provider chain
                    # (same treatment as a rail nudge): drop the chain head at turn end.
                    rail_drove_this_turn = True
                    _suppress_reasoning_next_pass = True
                    continue
                # Cap reached — end the turn honestly, never a silent hang.
                yield {"content": (
                        "\n\nI got stuck deciding how to do that and stopped rather than "
                        "loop. Could you tell me the exact change you want, or rephrase it?"
                    ), "reasoning_content": "", "finish_reason": None, "usage": None}
                break
            # M3 — a disconnect raises GeneratorExit here; it unwinds to the
            # function's `finally: await client.aclose()`, and the gateway finalizes
            # this pass's row via the silent cascade (no explicit DELETE → no notify).

            # D-TOOLCALL-GEMMA-TOKEN-LEAK cross-channel salvage — some local
            # models (confirmed: Gemma 4 GGUFs, llama.cpp#22786 "tool call
            # returned as content") occasionally abandon the structured
            # tool_calls channel entirely and dump their native tool-call
            # tokens into plain content/reasoning text instead. Scan BOTH
            # accumulated channels for that pattern before deciding this pass
            # has no tool calls — deduped, since a retrying model can leak the
            # same call twice in one pass (observed live).
            leaked_calls = list(dict.fromkeys(
                _extract_leaked_tool_calls("".join(text_parts) + "\n" + "".join(reasoning_parts))
            ))
            # /review-impl MED — a leaked name is free-form regex output, not a
            # provider-attested tool_calls id: without this check ANY text that
            # happens to match the marker shape (a hallucination, or untrusted
            # content the model echoed from an earlier tool RESULT — e.g. a web-
            # search snippet, already handled as untrusted DATA at the tool
            # layer but now back in-context) would be treated as a genuine call.
            # Restricting to tools genuinely reachable THIS turn — not a bypass
            # of tier/approval gating below, which still applies uniformly to a
            # salvaged call exactly as it would to a structured one — closes
            # that gap: a name for a tool nobody actually offered this turn is
            # dropped, not executed.
            if leaked_calls:
                _known_names = (
                    active_tool_names if discovery
                    else {
                        fn.get("name") for td in (tools or [])
                        if isinstance(td, dict) and isinstance(fn := td.get("function"), dict)
                    }
                )
                _dropped = [n for n, _ in leaked_calls if n not in _known_names]
                if _dropped:
                    logger.warning(
                        "D-TOOLCALL-GEMMA-TOKEN-LEAK: dropped %d leaked call(s) for a "
                        "tool not offered this turn (model_ref=%s): %s",
                        len(_dropped), model_ref, _dropped,
                    )
                leaked_calls = [(n, b) for n, b in leaked_calls if n in _known_names]
            if leaked_calls:
                logger.warning(
                    "D-TOOLCALL-GEMMA-TOKEN-LEAK: recovered %d leaked tool-call(s) "
                    "from plain content/reasoning text (model_ref=%s): %s",
                    len(leaked_calls), model_ref, [n for n, _ in leaked_calls],
                )
                # Confirmed leak — the held-back text IS the leak (or trails
                # right after it); never forward it to the visible content.
                content_hold = reasoning_hold = ""
            else:
                # No leak confirmed — the hold was a false alarm (real prose
                # that happened to start with `<`, or a marker that started
                # but never completed this pass); flush it as normal content
                # so nothing genuine is silently dropped.
                if content_hold or reasoning_hold:
                    yield {"content": content_hold, "reasoning_content": reasoning_hold,
                           "finish_reason": None, "usage": None}

            # D-NARRATED-WRITE — fold this pass's prose into the turn-level buffer (see
            # its declaration: a claim made in an early pass must still be visible to the
            # guard that runs on the last one).
            turn_text_parts.extend(text_parts)

            # D-SILENT-TURN-NO-CARD-NO-PROSE — name the pass that is about to end
            # the turn saying nothing. `_has_leak_marker` already returns True for
            # this string, so the platform knows it is a control token and still
            # lets the pass fall through as an ordinary "model stopped without a
            # tool call". Logged, NOT remedied: the remedy (retry the pass, since
            # the model's intent was a call) is a mechanism whose benefit has not
            # been measured, and what the author is shown when a turn says nothing
            # is DQ-T33, which is the owner's. Naming it is what makes either
            # decision measurable — until now this shape was only observable by
            # waiting for it.
            if _is_bare_toolcall_marker_only(
                "".join(text_parts), "".join(reasoning_parts)
            ) and not tool_frags and not leaked_calls:
                logger.warning(
                    "D-SILENT-TURN-NO-CARD-NO-PROSE: DEGENERATE PASS — the model's entire "
                    "output this pass was %d character(s) of bare tool-call control token "
                    "(%r) with no call to salvage and nothing for the author. model_ref=%s "
                    "session=%s iteration=%s",
                    len("".join(text_parts)) + len("".join(reasoning_parts)),
                    ("".join(text_parts) + "".join(reasoning_parts))[:64],
                    model_ref, session_id, iteration,
                )
                if degenerate_pass_interventions < DEGENERATE_PASS_INTERVENTION_CAP:
                    degenerate_pass_interventions += 1
                    # The model INTENDED a call — it emitted the opening delimiter for one. Steer
                    # it to make the call plainly, and force reasoning off for the retry, exactly
                    # as D-REASONING-LOOP does for the same trigger shape.
                    working.append({
                        "role": "user",
                        "content": (
                            "[SYSTEM DIRECTIVE] Your last reply was empty — the tool call did "
                            "not come through. Do not explain. Either CALL the tool you were "
                            "about to call, with the arguments you already have, or answer the "
                            "user directly in one short message."
                        ),
                    })
                    rail_drove_this_turn = True
                    _suppress_reasoning_next_pass = True
                    logger.info(
                        "D-SILENT-TURN: retrying the degenerate pass with reasoning OFF "
                        "(session=%s iteration=%s)", session_id, iteration,
                    )
                    continue
                # Cap reached. Fall through: the turn ends and the silent-turn guard below
                # records it `failed`. Deliberately NOT a fabricated reply — putting words in the
                # assistant's mouth here is the mistake this loop keeps finding elsewhere, and
                # what the author should SEE is DQ-T33, still the owner's.

            if not tool_frags and not leaked_calls:
                # ── P-1 step-runner: the model stopped without a tool call. If a pinned rail
                # is IN FLIGHT (a rail step tool actually succeeded this turn — the model chose
                # to start it), the book confirms an outstanding auto-drivable next step, and
                # every guard holds, DRIVE it: re-probe FRESH (the turn-start probe is stale
                # after this turn's writes), decide via next_actionable_step (which STOPs at
                # confirm gates / started async / UNKNOWN artifacts), inject a forceful nudge,
                # and loop ONE more pass. Wholly best-effort — any failure falls through to the
                # normal end-of-turn below, byte-identical to pre-P-1.
                _verdict = None
                # ONE evaluation of the guards, named — so the log below can never disagree with
                # the branch it explains. (Duplicating the condition to log it is how two copies
                # of one decision drift apart.)
                _step_tools_hit = sorted(set(turn_succeeded) & _rail_all_step_tools)
                _step_tools_tried = sorted(set(fail_by_tool_error) & _rail_all_step_tools)
                # D-FJ-18 — the turn asked for this journey in its own words and then called
                # nothing at all. See _rail_is_in_flight; the drive it unlocks is confined to
                # the intent-pinned rail below so it cannot become D-FJ-17 one layer down.
                _asked_and_called_nothing = bool(rail_intent_slugs) and not turn_attempted
                # D-FJ-17 now lives INSIDE decide_rail_drive as precedence rule 3 — the
                # decision can finally state it instead of this loop lying about which rails
                # exist. See loreweave_agent_control.harness.TurnRequest.
                _rail_guards = {
                    "driver_on": bool(settings.rail_driver_enabled),
                    "have_specs": bool(rail_specs),
                    "have_book": bool(rail_book_id),
                    "grant_ok": bool(rail_grant_ok),
                    "redrive_left": rail_redrive_count < RAIL_REDRIVE_CAP,
                    "not_last_iter": not last_iter,
                    # G2: the deploy strength "off" disables the drive entirely (pre-drive rail).
                    "strength_on": settings.rail_enforcement != "off",
                    # GOV-13 escape hatch: an explicit "skip the plan" / "just write" releases the
                    # hold this turn — governance serves the author, it never imprisons them.
                    "not_abandoned": not rail_user_abandoned,
                    "passes_left": write_passes < max_iterations - 1,
                    "in_flight": _rail_is_in_flight(
                        resumed_mid_rail=bool(rail_in_flight),
                        step_tools_succeeded=_step_tools_hit,
                        step_tools_attempted=_step_tools_tried,
                        asked_for_it_and_called_nothing=_asked_and_called_nothing,
                    ),
                }
                if all(_rail_guards.values()):
                    # ACP A2 (RW-3): the drive+enforcement DECISION lives in the SDK harness
                    # (decide_rail_drive) — it unifies the fresh re-probe, next_actionable_step, and
                    # the nudge-cap/strength/give-up logic into one verdict. The probe is INJECTED
                    # (RW-11). This loop OWNS the mechanics: inject the directive as a role=user
                    # message, bump the counters, drop the stateful chain head, continue.
                    from app.services.book_state_probe import probe_book_state
                    from loreweave_agent_control import TurnRequest, decide_rail_drive
                    _verdict = await decide_rail_drive(
                        probe_fn=probe_book_state,
                        rail_specs=rail_specs, book_id=rail_book_id, user_id=user_id,
                        turn_start_counts=rail_turn_start_counts, turn_succeeded=turn_succeeded,
                        async_tools=rail_async_tools, nudged_out=rail_twice_nudged,
                        nudge_counts=rail_nudge_counts,
                        enforcement_strength=settings.rail_enforcement,
                        required_nudge_cap=settings.rail_required_nudge_cap,
                        # TURN OWNERSHIP — the input this decision could not previously see.
                        request=TurnRequest(
                            pinned_rails=rail_intent_slugs,
                            named_tools=rail_named_tools,
                            abandons_rail=bool(rail_user_abandoned),
                        ),
                        stuck_tools=rail_stuck_tools,
                    )
                    if not _verdict.should_drive:
                        # Name the LOSING claimant. A rail that declines silently is
                        # indistinguishable from a rail with nothing to do, and that ambiguity
                        # is why this whole class of defect was a transcript-read.
                        logger.info(
                            "rail step-runner: did not claim the turn — %s",
                            _verdict.declined_reason or "no actionable step",
                        )
                elif _rail_guards["driver_on"] and _rail_guards["have_specs"]:
                    # A step-runner that silently does not fire is indistinguishable from a rail
                    # with nothing to do — and that ambiguity cost a live debugging session: the
                    # rail logged `0/9 steps done, next=…` on every pass while the model improvised
                    # the wrong tool three times and no nudge was ever injected. Name the guard that
                    # held, so the next occurrence is one grep instead of a code read.
                    logger.info(
                        "rail step-runner SKIPPED — held by: %s (step tools this turn: "
                        "succeeded=%s tried-and-failed=%s)",
                        ", ".join(k for k, v in _rail_guards.items() if not v) or "none",
                        _step_tools_hit or "—", _step_tools_tried or "—",
                    )
                if _verdict is not None and _verdict.should_drive:
                    _step = _verdict.step
                    # Record the narration the model just streamed, then the ephemeral directive.
                    # `working` is never persisted (the assistant row persists the yielded
                    # content), so the synthetic user directive never reaches history or the UI.
                    working.append({"role": "assistant", "content": "".join(text_parts)})
                    working.append({"role": "user", "content": _verdict.directive_text})
                    _directive_before_this_pass = True  # D-FJ-19
                    rail_redrive_count += 1
                    rail_drove_this_turn = True  # drop the stateful chain head at turn end
                    logger.info(
                        "rail step-runner: %s %s → %s (redrive %d/%d, strength=%s)",
                        "giving up on" if _verdict.giving_up else "driving",
                        _verdict.slug, _step.tool, rail_redrive_count, RAIL_REDRIVE_CAP,
                        settings.rail_enforcement,
                    )
                    if trace is not None:
                        trace.add("compiler", "T6", "rail",
                                  f"{'giveup' if _verdict.giving_up else 'redrive'}:{_step.tool}")
                    continue  # loop top re-offers the tools; the model calls the next step

                # D-NARRATED-WRITE — the model is about to END the turn having NAMED a
                # write tool in its prose that it never actually CALLED. For an author
                # this is the most damaging failure the loop has: they are told the work
                # is done and sent to go look at it, and it is not there.
                #
                # Live (Mị Đế 019faf5b seq 26 + 32): *"composition_outline_node_create:
                # Tôi đã tạo một Chương 1 … composition_outline_node_edit: Tôi đã tạo và
                # điền chi tiết 5 cảnh"* and *"5 cảnh hiện đang ở trạng thái Draft trong
                # Outline, bạn hãy mở tab Outline để kiểm tra"* — with, respectively, 4
                # and 6 tool calls, every one of them a READ, and zero outline nodes in
                # the database.
                #
                # Detected MECHANICALLY, not by reading intent out of prose: a token that
                # matches a real catalog tool name, whose tier is a write (A/W/S), that
                # this TURN never attempted. No NLP, no claim-parsing, no guessing at
                # tense — and a model that was merely *explaining* a tool loses nothing,
                # because the directive explicitly offers "say plainly you did not run it"
                # as a valid answer. Capped at one nudge per turn so this can never become
                # the loop it exists to prevent.
                _narrated = _narrated_uncalled_writes(
                    "".join(turn_text_parts),
                    catalog_index=cat_index,
                    attempted=turn_attempted,
                )
                # D-FJ-8 — the sister case: the turn called NOTHING and a rail's next write step is
                # still outstanding. Named no tool, so the intersection above is empty.
                _stalled_tool = None
                if not _narrated:
                    _stalled_tool = _rail_write_step_stalled(
                        rail_progress, catalog_index=cat_index, attempted=turn_attempted,
                        intent_slugs=rail_intent_slugs,
                    )
                    if _stalled_tool:
                        _narrated = [_stalled_tool]
                if _narrated:
                    _nw_guards = {
                        "under_cap": narrated_write_nudges < NARRATED_WRITE_NUDGE_CAP,
                        "not_last_iter": not last_iter,
                        "passes_left": write_passes < max_iterations - 1,
                    }
                    if not all(_nw_guards.values()):
                        # A guard that silently declines is indistinguishable from a guard
                        # that saw nothing — and that ambiguity already cost one live
                        # debugging pass here. Name what held.
                        logger.warning(
                            "D-NARRATED-WRITE (session=%s): %s named but never called — "
                            "NOT nudging, held by: %s",
                            session_id, _narrated,
                            ", ".join(k for k, v in _nw_guards.items() if not v),
                        )
                    else:
                        narrated_write_nudges += 1
                        # A directive to "call it now" is empty if the tool is not on the
                        # wire — and OFF-SURFACE is the usual reason the model narrated
                        # instead of calling in the first place. Telling it to `tool_load`
                        # first is ceremony a mid-tier model skips (measured: it kept
                        # reading and re-claiming instead). So ARM the tool here, exactly
                        # as the dispatch chokepoint already does for an off-surface tool
                        # the model *did* call — same decision, one step earlier.
                        _armed = [
                            nm for nm in _narrated
                            if discovery and nm in cat_index and nm not in active_tool_names
                        ]
                        _arm_tools(
                            _armed, active_tool_names=active_tool_names,
                            activation_state=activation_state,
                            discovery_catalog=discovery_catalog,
                            context_length=context_length,
                        )
                        # The two arms must not share one sentence: the stalled-rail arm never read
                        # the prose, so logging "named in prose" for it would assert something
                        # unmeasured — the same false-report shape the directive above is careful
                        # to avoid. Caught by reading this line's own output on a live run.
                        logger.warning(
                            "D-NARRATED-WRITE (session=%s): %s: %s — nudging once "
                            "(armed off-surface: %s)",
                            session_id,
                            ("the turn called NO tool while a rail's next write step is "
                             "outstanding" if _stalled_tool else
                             "the turn is ending with write tool(s) named in prose but never "
                             "called"),
                            _narrated, _armed or "—",
                        )
                        if trace is not None:
                            trace.add("compile", "T6", "tools",
                                      f"narrated_write:{','.join(_narrated)}", is_error=True)
                        working.append({"role": "assistant", "content": "".join(text_parts)})
                        _directive_before_this_pass = True  # D-FJ-19
                        working.append({"role": "user", "content": (
                            # The stalled-rail arm must NOT say "you just described using X" — it
                            # never read the prose and does not know whether anything was claimed.
                            # Asserting a claim the runtime did not measure would be the same
                            # false-report defect this guard exists to stop, pointed the other way.
                            (
                                f"[SYSTEM DIRECTIVE] This turn called no tool at all, and "
                                f"{_stalled_tool} is the next outstanding step of the journey you "
                                "are on — so nothing was written and the author will find "
                                "nothing.\n"
                                if _stalled_tool else
                                "[SYSTEM DIRECTIVE] You just described using "
                                f"{', '.join(_narrated)}, but you did not call "
                                + ("it" if len(_narrated) == 1 else "them")
                                + " — nothing was written and the author will find nothing.\n"
                            )
                            + (
                                f"{', '.join(_armed)} "
                                + ("is" if len(_armed) == 1 else "are")
                                + " now available to you on this turn — no tool_load needed.\n"
                                if _armed else ""
                            )
                            + "Do ONE of these, and nothing else:\n"
                            "(a) call the tool now, for real, with complete arguments; or\n"
                            "(b) if you genuinely cannot, tell the author plainly that you "
                            "did NOT make the change, and why.\n"
                            "Do not re-read anything — you have already read enough. Never "
                            "report a change as done, and never tell the author to go and "
                            "check for it, unless a tool call actually returned a result."
                        )})
                        continue

                # P2-FABRICATED-WRITE — the turn called NOTHING and is ending by telling the
                # author a change was made. No tool is named, so the guard above is silent by
                # construction; the store is untouched, so nothing downstream will contradict it.
                # Measured: `plan_keep_material`, 4 of 5 runs, "I've updated the plan ... Your
                # story foundation is now fully updated" with called_tools == [].
                #
                # Shares NARRATED_WRITE_NUDGE_CAP with the guard above deliberately: both are
                # write-side, and a turn must never collect two write nudges. Runs only when that
                # guard did not claim the slot.
                if (not turn_attempted) and _claimed_an_effect_without_acting(
                    "".join(turn_text_parts), attempted=turn_attempted,
                ):
                    _fw_guards = {
                        "under_cap": narrated_write_nudges < NARRATED_WRITE_NUDGE_CAP,
                        "not_last_iter": not last_iter,
                        "passes_left": write_passes < max_iterations - 1,
                    }
                    if not all(_fw_guards.values()):
                        logger.warning(
                            "P2-FABRICATED-WRITE (session=%s): the turn called nothing and "
                            "claimed an effect — NOT nudging, held by: %s",
                            session_id,
                            ", ".join(k for k, v in _fw_guards.items() if not v),
                        )
                    else:
                        narrated_write_nudges += 1
                        logger.warning(
                            "P2-FABRICATED-WRITE (session=%s): the turn called NO tool and is "
                            "ending with a claim that something was done — nudging once",
                            session_id,
                        )
                        if trace is not None:
                            trace.add("compile", "T6", "tools",
                                      "fabricated_write:zero_calls", is_error=True)
                        working.append({"role": "assistant", "content": "".join(text_parts)})
                        _directive_before_this_pass = True  # D-FJ-19
                        working.append({"role": "user", "content": (
                            # Deliberately does NOT quote the sentence back or name a tool. The
                            # runtime measured two things and may assert only those: that no tool
                            # ran, and that the text reads as a completed change. Telling the
                            # model WHICH claim was wrong would assert a reading of intent this
                            # guard never made — the same false-report shape it exists to stop.
                            "[SYSTEM DIRECTIVE] This turn called no tool at all, and your reply "
                            "reads as though a change was completed. Nothing was written and the "
                            "author will find nothing.\n"
                            "Do ONE of these, and nothing else:\n"
                            "(a) call the tool that actually makes the change, for real, with "
                            "complete arguments; or\n"
                            "(b) tell the author plainly that you did NOT make the change, and "
                            "why.\n"
                            "If what you changed was only your own understanding, say exactly "
                            "that and say their saved data is untouched. Never report a change "
                            "as done unless a tool call actually returned a result."
                        )})
                        continue

                # DQ-T30 — the model is about to END the turn answering a question whose own
                # words match a READ tool's declared vocabulary, having called none of them. The
                # store is untouched, so every write-side guard above is silent by construction,
                # and the failure is in the ANSWER: measured live, "one rule" when the store held
                # two, then a wholly invented second rule. See _unanswered_data_question_reads.
                #
                # Runs only when the write guards did not claim the turn: a narrated write is the
                # more damaging failure and owns the single directive slot when both are true.
                _unread = _unanswered_data_question_reads(
                    request_text,
                    catalog_index=cat_index,
                    attempted=turn_attempted,
                )
                if _unread:
                    _dq_guards = {
                        "under_cap": data_question_nudges < DATA_QUESTION_NUDGE_CAP,
                        "not_last_iter": not last_iter,
                        "passes_left": write_passes < max_iterations - 1,
                    }
                    if not all(_dq_guards.values()):
                        # Same discipline as the sister guard: a guard that declines silently is
                        # indistinguishable from one that saw nothing.
                        logger.warning(
                            "DQ-T30 (session=%s): %s answer(s) this request and none ran — "
                            "NOT nudging, held by: %s",
                            session_id, _unread,
                            ", ".join(k for k, v in _dq_guards.items() if not v),
                        )
                    else:
                        data_question_nudges += 1
                        # ARM what we name. Measured 2026-08-14: the re-ask fired this guard
                        # while `composition_list_canon_rules` was NOT in that turn's
                        # advertised_tools, so option (a) was impossible and the model took (b)
                        # after thrashing through twelve other composition tools looking for it.
                        # Same decision the sister guard already makes, for the same reason.
                        _dq_armed = [
                            nm for nm in _unread
                            if discovery and nm in cat_index and nm not in active_tool_names
                        ]
                        _arm_tools(
                            _dq_armed, active_tool_names=active_tool_names,
                            activation_state=activation_state,
                            discovery_catalog=discovery_catalog,
                            context_length=context_length,
                        )
                        logger.warning(
                            "DQ-T30 (session=%s): the turn is ending with a data question "
                            "answered from memory — %s declare(s) this request and none was "
                            "called; nudging once (armed off-surface: %s)",
                            session_id, _unread, _dq_armed or "—",
                        )
                        if trace is not None:
                            trace.add("compile", "T6", "tools",
                                      f"data_question:{','.join(_unread)}", is_error=True)
                        working.append({"role": "assistant", "content": "".join(text_parts)})
                        _directive_before_this_pass = True  # D-FJ-19
                        working.append({"role": "user", "content": (
                            # It asserts ONLY what was measured — these tools declare this
                            # request, and none of them ran. It does NOT accuse the model of
                            # having claimed anything: the runtime did not read the prose here,
                            # and asserting an unmeasured claim is the false-report defect this
                            # loop has already fixed three times, pointed the other way.
                            "[SYSTEM DIRECTIVE] You are answering a question about stored data "
                            "without having read it on this turn. "
                            f"{', '.join(_unread)} "
                            + ("is" if len(_unread) == 1 else "are")
                            + " available to you right now — no tool_load needed — and "
                            + ("declares" if len(_unread) == 1 else "declare")
                            + " exactly this request.\n"
                            "Anything you remember from earlier in this conversation may be "
                            "out of date — the book can change outside this chat, and a "
                            "journey that has finished no longer re-reads anything.\n"
                            "Do ONE of these, and nothing else:\n"
                            "(a) call the tool now and answer from what it returns; or\n"
                            "(b) if you genuinely cannot, tell the author plainly that you did "
                            "NOT re-read, and that your answer may be stale.\n"
                            "Never state a count, a name, or a detail from this book unless a "
                            "tool call on THIS turn returned it."
                        )})
                        continue

                # No tool calls — this pass IS the final text response.
                yield {"content": "", "reasoning_content": "",
                       "finish_reason": finish_reason or "stop",
                       "llm_call_count": llm_call_count,
                       # Drop the chain head if the step-runner nudged this turn (see
                       # rail_drove_this_turn) — the next turn re-establishes clean.
                       "response_id": None if (rail_drove_this_turn and stateful) else _chain_id,
                       "context_size": _last_call_input,
                       "usage": _Usage(prompt_tokens=total_input,
                                       completion_tokens=total_output,
                                       cache_creation_tok=total_cache_creation,
                                       cache_read_tok=total_cache_read)}
                return

            # The model called tools (structured, or salvaged from leaked
            # native tokens above) — record the assistant turn, execute each
            # call, append the results, and loop.
            calls = _reassemble_tool_calls(tool_frags)
            # D-TOOLCALL-GEMMA-INTERIOR-LEAK — FIRST, before any helper inspects the
            # args: un-concatenate calls the model packed into one args payload. Runs
            # here (one site) rather than inside `_parse_tool_args` (25 call sites)
            # because it changes the NUMBER of calls, not one call's parse.
            calls = _split_interior_leaked_tool_calls(calls)
            # D-TOOLCALL-GEMMA-TOKEN-LEAK — this pass's ENTIRE call set came from
            # the leak scan (tool_frags was empty), typically because this WAS
            # the D7 forced tool-free final pass (offered_tools False this
            # iteration) — the exact pass where a broken-template model is most
            # likely to dump its native tool-call tokens as plain text instead
            # of a structured call. The D7 termination guard below normally
            # treats "tool calls on a no-tools-offered pass" as the model
            # defiantly ignoring the contract and bails out WITHOUT looping —
            # correct for a hallucinated call with nothing behind it, but wrong
            # here: we just executed a real, recovered call and need one more
            # pass (itself force-tool-free, same as any other final pass) so
            # the model can actually use the result instead of the turn ending
            # empty-handed right after the tool call finally succeeded.
            salvaged_this_pass = not calls
            if not calls:
                # tool_frags was empty — every recovered call came from the
                # leak scan; synthesize the same {id, name, arguments} shape
                # `_parse_tool_args` (with its own Gemma-token repair) will
                # parse `arguments` normally at every downstream call site.
                calls = [
                    {"id": f"leaked-{uuid4()}", "name": name, "arguments": body}
                    for name, body in leaked_calls
                ]
            else:
                # Structured calls exist, but one came back with unparseable/
                # empty arguments — if the SAME tool name also leaked into
                # plain text this pass, that leak is the only place the
                # model's real intent survived; prefer it.
                for c in calls:
                    if _parse_tool_args(c["arguments"]):
                        continue
                    for name, body in leaked_calls:
                        if name == c["name"]:
                            c["arguments"] = body
                            break
            # D-TOOLCALL-DUP-EMPTY-CALL — runs AFTER the leak-salvage repair
            # above so a call that leak-salvage just filled in from plain text
            # is no longer "empty" and is correctly kept; only a call that is
            # STILL empty/unparseable immediately after a well-formed call to
            # the identical tool name gets silently dropped here.
            calls = _drop_duplicate_empty_tool_calls(calls)
            # …then collapse byte-identical repeats in the same pass (see the helper: a
            # write tool without its own idempotency would otherwise run N times for one
            # user intent). Order matters — drop the malformed empties first so a
            # `{}`-args call is never the survivor a later well-formed call collapses into.
            calls = _collapse_identical_tool_calls(calls)
            # D-TOOLCALL-HISTORY-ARGS-NOT-JSON — a call's raw `arguments` string
            # can be `""` (the model never streamed anything) or otherwise
            # unparseable. Per the OpenAI tool-calling wire contract,
            # `function.arguments` MUST always be a JSON-parseable string (at
            # minimum `"{}"`) — persisting the raw, possibly-empty string here
            # means the NEXT pass re-sends this malformed entry back to the
            # provider as part of `messages` (see `working` at line ~907, sent
            # verbatim at line ~1039/4143). LM Studio's own chat-history
            # reconstruction then throws `JSON.parse('')` on it (confirmed live,
            # console warning "Failed to parse function call arguments JSON
            # string ''"), independent of which model is loaded — this is a
            # request-payload bug on OUR side, not a per-model defect. Always
            # re-serialize through `_parse_tool_args` (already degrades any
            # empty/malformed string to `{}`) so history is never re-sent with
            # invalid JSON.
            working.append({
                "role": "assistant",
                "content": "".join(text_parts),
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(_parse_tool_args(c["arguments"]))}}
                    for c in calls
                ],
            })

            # ARCH-1 C6 — frontend tool: SUSPEND instead of executing. The first
            # frontend tool call pauses the run; the FE executes it (the user
            # reviews + applies/dismisses) and POSTs the result to the resume
            # endpoint, which re-enters this loop with the result appended. Any
            # backend tools in the SAME pass already ran above? No — execution
            # happens in the loop below, which we have NOT entered yet. So if a
            # pass mixes backend + frontend tools, we execute the backend ones
            # first (so their results are in `working`), THEN suspend on the
            # frontend one. Process calls in order: run backend tools inline,
            # and on the first frontend tool, suspend with the partial state.
            suspended_call: dict | None = None
            pass_did_write = False  # H9 — only a Tier-A/W write decrements budget
            # D-NARRATED-WRITE — every tool the model actually EMITTED this turn, recorded
            # before any gate can drop it. Deliberately NOT `turn_succeeded`: that counter is
            # the rail driver's ledger and only counts a tool the pinned rail names (see the
            # backend chokepoint), so a perfectly good non-rail write is absent from it — and
            # reading it as "tools attempted" would flag a model that DID the work. Caught by
            # `test_a_write_actually_called_never_nudges`; a false accusation right after real
            # work is worse than the silence this guard exists to break.
            turn_attempted.update(c["name"] for c in calls)
            for c in calls:
                # Wrap-repair for CONSUMER-LOCAL meta tools (find_tools/tool_load/workflow_load/
                # run_subagent/*_list). The federated dispatch below unwraps {"args":{…}} with each
                # tool's real schema, but these meta tools parse their own args inline and would
                # otherwise see empty params. Rewrite c["arguments"] once so every downstream
                # _parse_tool_args sees the unwrapped payload. tool_def=None is safe — none of
                # these declares an args/arguments param (verified in their schemas).
                if c["name"] in _CONSUMER_LOCAL_META_TOOLS:
                    _parsed_meta = _parse_tool_args(c["arguments"])
                    _repaired_meta = _unwrap_wrapped_args(_parsed_meta, None)
                    if _repaired_meta is not _parsed_meta:
                        c["arguments"] = json.dumps(_repaired_meta)
                # WS-1a — tool_list is CONSUMER-LOCAL + deterministic: enumerate a
                # category (or all) from the in-memory catalog, deprecated tools
                # LABELED not dropped. No activation (listing ≠ loading), no write.
                if discovery and c["name"] == TOOL_LIST_NAME:
                    args_obj = _parse_tool_args(c["arguments"])
                    category = args_obj.get("category") or None
                    include_deprecated = _tool_list_include_deprecated(args_obj)
                    _norm_cat = category or "all"
                    tool_list_total += 1

                    # F18 — the model ALREADY has this category's complete list (tool_list is
                    # not paginated), so re-listing it is the loop. Don't hand back the same
                    # list; AUTO-LOAD the category's tools (exactly like tool_load) so the real
                    # tools it was circling become callable, and STEER it to use them. Erroring
                    # here backfired (the weak model retried harder, 28→311); this makes forward
                    # progress instead. Past the per-turn total, tool_list is also de-advertised
                    # (suppress_tool_list) — tool_load stays, so a specific tool is still reachable.
                    # T7-D5 — the repeat key must include `include_deprecated`, because the
                    # two values return genuinely DIFFERENT lists. Keyed on the category alone,
                    # `tool_list(book)` followed by `tool_list(book, include_deprecated=true)`
                    # was classified as a loop and answered with a steer asserting "its complete
                    # tool list is above, unchanged" — false, and the request went unanswered.
                    #
                    # MEASURED LIVE 2026-08-13 (session 019ff9fe), asked to compare the two:
                    # the first call returned 16 current tools, the second was refused as a
                    # repeat, and the model built its answer from the steer's auto-loaded set
                    # instead. It produced a table with THE TWO COLUMNS INVERTED — the
                    # deprecated tools under "Current Active", the current ones under "Including
                    # Deprecated" — plus an invented explanation for the discrepancy.
                    #
                    # Harmless before T7-D1, when both values returned the same list and
                    # "unchanged" was true. Once the default started hiding deprecated tools the
                    # two requests diverged and the claim became a lie.
                    #
                    # This does not weaken F18: the flag is a boolean, so a category affords at
                    # most two distinct keys, and TOOL_LIST_TOTAL_CAP still bounds the turn.
                    _list_key = (_norm_cat, include_deprecated)
                    if listed_categories.get(_list_key, 0) >= TOOL_LIST_CATEGORY_CAP:
                        from app.services.tool_surface import (
                            HOT_SEED_TOKEN_BUDGET,
                            budget_names_by_tokens_ex,
                            merge_activated_tools,
                        )
                        _load_payload, loaded = tool_load_result(
                            discovery_catalog or [], category=_norm_cat,
                            unavailable_providers=provider_availability(
                                knowledge_client.get_catalog_meta(user_id)),
                        )
                        # T7-D4 — the breaker must auto-load the SAME set the listing showed.
                        #
                        # `tool_load_result` labels legacy tools rather than dropping them,
                        # which is right for `tool_load` (you ask for a name, you get it, with
                        # its replacement attached). Here nobody asked: this is the runtime
                        # picking tools on the model's behalf and then instructing it to "Call
                        # one of them now". Recorded firing, 2026-08-13:
                        #
                        #   "Its tools are now LOADED and callable: book_chapter_save_draft,
                        #    book_get, book_list_chapters, book_list_revisions, book_scene_get,
                        #    book_steering_list, book_update_details"
                        #
                        # Four of those seven are deprecated. Before T7-D1 both halves showed
                        # legacy and merely agreed; now the listing hides it and the breaker
                        # would steer straight onto it — the runtime recommending the surface
                        # its own listing had just withheld.
                        #
                        # An explicit `include_deprecated=true` is honoured: the caller asked
                        # for the legacy surface, so the breaker keeps loading it.
                        #
                        # `loaded` is a list of NAMES; only the payload carries the
                        # `deprecated` label, so the legacy set is read from there.
                        if not include_deprecated:
                            _legacy_loaded = {
                                _t["name"] for _t in _load_payload.get("tools", [])
                                if _t.get("deprecated")
                            }
                            loaded = [_n for _n in loaded if _n not in _legacy_loaded]
                        names_to_activate, _dropped_by_budget = budget_names_by_tokens_ex(
                            discovery_catalog or [], loaded,
                            token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
                        )
                        # CP-0.2 — register what the budget deleted. Arm E: the budgeter
                        # dropped the one tool the model needed and returned only the
                        # survivors, so the tool left the surface and the record at the same
                        # instant. `find_tools` is cited as the backstop, which is exactly
                        # why it must be recorded: a backstop nobody can see fire is a claim.
                        _budget_withheld.extend(
                            {"tool": _n, "stage": "token_budget",
                             "reason": "did not fit the activation token budget"}
                            for _n in _dropped_by_budget
                        )
                        active_tool_names.update(names_to_activate)
                        if curated and activation_state is not None:
                            activation_state["activated_tools"] = merge_activated_tools(
                                activation_state["activated_tools"], loaded,
                                catalog=discovery_catalog,
                                context_length=context_length,
                            )
                            activation_state["dirty"] = True
                        if tool_list_total >= TOOL_LIST_TOTAL_CAP:
                            suppress_tool_list = True
                        _loaded_names = sorted(names_to_activate)
                        _steer = (
                            f"You already listed '{_norm_cat}' and its complete tool list is "
                            "above, unchanged — tool_list is not paginated, so there is nothing "
                            "more to fetch. Its tools are now LOADED and callable: "
                            f"{', '.join(_loaded_names) or '(none available in this category)'}. "
                            "Call one of them now, or answer the user. Do NOT call tool_list for "
                            "this category again."
                        )
                        if suppress_tool_list:
                            _steer += (
                                " tool_list is now disabled for the rest of this turn; use a tool "
                                "loaded above, or tool_load(name=…) to load a specific tool by name."
                            )
                        payload = {
                            "listed_before": True,
                            "category": _norm_cat,
                            "loaded_tools": _loaded_names,
                            "note": _steer,
                        }
                        if surface_tracker is not None:
                            _act_count = (
                                len(activation_state["activated_tools"])
                                if activation_state is not None
                                else len(active_tool_names)
                            )
                            _payload_as = surface_tracker.activated(_act_count)
                            if _payload_as is not None:
                                yield {"agent_surface": _payload_as}
                        logger.info(
                            "tool_list loop breaker: category=%s re-listed (total=%d this turn) "
                            "— auto-loaded %d tool(s)%s",
                            _norm_cat, tool_list_total, len(_loaded_names),
                            "; tool_list de-advertised" if suppress_tool_list else "",
                        )
                        working.append({
                            "role": "tool", "tool_call_id": c["id"],
                            "content": tool_result_content(payload),
                        })
                        yield {"tool_call": {
                            "id": c["id"], "iteration": iteration, "tool": c["name"],
                            "args": args_obj, "ok": True, "result": payload, "error": None,
                        }}
                        continue

                    # First list of this category (within cap) — the complete, deterministic
                    # enumeration. Deprecated tools LABELED not dropped. No activation, no write.
                    listed_categories[_list_key] = listed_categories.get(_list_key, 0) + 1
                    payload = tool_list_result(
                        discovery_catalog or [],
                        category,
                        include_deprecated=include_deprecated,
                        exclude=set(ALWAYS_ON_CORE_NAMES),
                        unavailable_providers=provider_availability(
                            knowledge_client.get_catalog_meta(user_id)),
                    )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": True, "result": payload, "error": None,
                    }}
                    continue

                # WS-1a — tool_load is CONSUMER-LOCAL: pure schema disclosure (executes
                # nothing), but loading MAKES a tool callable, so — like find_tools's
                # matched names — union the loaded names into the active set (NEXT pass
                # advertises their FULL schemas) under the same token-budget ceiling, and
                # persist for curated sessions. No write → no write-budget hit (H9).
                if discovery and c["name"] == TOOL_LOAD_NAME:
                    args_obj = _parse_tool_args(c["arguments"])
                    _load_name = args_obj.get("name") or None
                    _raw_names = args_obj.get("names")
                    _load_names = _raw_names if isinstance(_raw_names, list) else None
                    _load_category = args_obj.get("category") or None
                    payload, loaded = tool_load_result(
                        discovery_catalog or [],
                        name=_load_name, names=_load_names, category=_load_category,
                        unavailable_providers=provider_availability(
                            knowledge_client.get_catalog_meta(user_id)),
                    )
                    from app.services.tool_surface import (
                        HOT_SEED_TOKEN_BUDGET,
                        budget_names_by_tokens_ex,
                    )
                    # review-impl #1 (WS-1a): tool_load returns FULL schemas — unlike find_tools
                    # (names only). A tool_load(category="all"/big) would re-inject the exact
                    # catalog bloat the discovery layer exists to prevent. Bound the RETURNED
                    # schemas (not just activation) by the same token ceiling the hot-seed uses;
                    # a single-/few-name load always fits, only a large category truncates.
                    names_to_activate, _dropped_by_budget = budget_names_by_tokens_ex(
                        discovery_catalog or [], loaded,
                        token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
                    )
                    # CP-0.2 — register what the budget deleted. Arm E: the budgeter
                    # dropped the one tool the model needed and returned only the
                    # survivors, so the tool left the surface and the record at the same
                    # instant. `find_tools` is cited as the backstop, which is exactly
                    # why it must be recorded: a backstop nobody can see fire is a claim.
                    _budget_withheld.extend(
                        {"tool": _n, "stage": "token_budget",
                         "reason": "did not fit the activation token budget"}
                        for _n in _dropped_by_budget
                    )
                    if len(names_to_activate) < len(loaded):
                        _keep = set(names_to_activate)
                        payload["tools"] = [t for t in payload["tools"] if t["name"] in _keep]
                        payload["truncated"] = True
                        payload["note"] = (
                            f"Loaded {len(names_to_activate)} of {len(loaded)} tools (token budget). "
                            "Call tool_load with specific names to load the rest."
                        )
                    if not loaded and not payload.get("not_found") and not payload.get(
                        "provider_unavailable"
                    ):
                        # review-impl #3: nothing requested — guide instead of a silent empty result.
                        payload["note"] = (
                            "No tool was requested — pass `name`, `names`, or a `category` "
                            "(use tool_list to see what's available)."
                        )
                    active_tool_names.update(names_to_activate)
                    # D-TOOL-LOAD-PERSISTS (2026-07-26, Mị Đế dogfood) — UNGATED like
                    # workflow_load, no longer curated-only. In auto mode a tool_load
                    # evaporated at turn end; the model re-loaded glossary_propose_entities
                    # every turn, found it gone the next, and fell back to the always-
                    # visible frontend edit tool (the placeholder_id loop). An explicit
                    # tool_load is the same strength of signal as workflow_load: the agent
                    # NAMED the tool it needs. Auto-mode re-advertisement is bounded to the
                    # recency tail (assemble_initial_active_names), not the whole set.
                    if activation_state is not None:
                        from app.services.tool_surface import merge_activated_tools
                        activation_state["activated_tools"] = merge_activated_tools(
                            activation_state["activated_tools"], loaded,
                            catalog=discovery_catalog,
                            context_length=context_length,
                        )
                        activation_state["dirty"] = True
                    if surface_tracker is not None:
                        act_count = (
                            len(activation_state["activated_tools"])
                            if activation_state is not None
                            else len(active_tool_names)
                        )
                        payload_as = surface_tracker.activated(act_count)
                        if payload_as is not None:
                            yield {"agent_surface": payload_as}
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": True, "result": payload, "error": None,
                    }}
                    continue

                # WS-2b — workflow_list is CONSUMER-LOCAL + deterministic: enumerate
                # the curated workflows visible this turn (slug/title/description).
                # No activation, no write.
                if c["name"] == WORKFLOW_LIST_NAME and turn_workflows:
                    args_obj = _parse_tool_args(c["arguments"])
                    payload = workflow_list_result(turn_workflows)
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": True, "result": payload, "error": None,
                    }}
                    continue

                # WS-2b — workflow_load is CONSUMER-LOCAL: return one workflow's ordered
                # rail (steps + gates + async annotations + guidance) AND activate its
                # step tools so the next pass advertises their real schemas (reusing the
                # hot-seed token budget, exactly like tool_load). Executes nothing; each
                # step's gate is enforced later by the tool's OWN tier/approval machinery.
                if c["name"] == WORKFLOW_LOAD_NAME and turn_workflows:
                    args_obj = _parse_tool_args(c["arguments"])
                    _slug = str(args_obj.get("slug", "") or "")
                    # Durable async-honesty: the set of step tools the CATALOG marks
                    # _meta.async, so the rail annotates them without the name heuristic.
                    _async_tools = frozenset(
                        n for n, td in cat_index.items() if tool_async(td)
                    ) if discovery else frozenset()
                    payload, step_tools = workflow_load_result(turn_workflows, _slug, _async_tools)
                    if step_tools and discovery:
                        from app.services.tool_surface import (
                            HOT_SEED_TOKEN_BUDGET,
                            budget_names_by_tokens_ex,
                            merge_activated_tools,
                        )
                        names_to_activate, _dropped_by_budget = budget_names_by_tokens_ex(
                            discovery_catalog or [], step_tools,
                            token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
                        )
                        # CP-0.2 — register what the budget deleted. Arm E: the budgeter
                        # dropped the one tool the model needed and returned only the
                        # survivors, so the tool left the surface and the record at the same
                        # instant. `find_tools` is cited as the backstop, which is exactly
                        # why it must be recorded: a backstop nobody can see fire is a claim.
                        _budget_withheld.extend(
                            {"tool": _n, "stage": "token_budget",
                             "reason": "did not fit the activation token budget"}
                            for _n in _dropped_by_budget
                        )
                        active_tool_names.update(names_to_activate)
                        # Persist the step tools REGARDLESS of curated mode. A workflow is an
                        # explicit multi-turn rail; its tools must survive to later turns even
                        # in a naive (non-curated) session, or a multi-turn workflow loses its
                        # step tools after the loading turn (the S03 drain failure). Unlike the
                        # ad-hoc find_tools path (still curated-gated below — an unranked
                        # enumeration must not accrete across turns), workflow_load activates a
                        # SMALL, author-declared, already-token-budgeted set, so persisting it
                        # in auto mode is safe. assemble_initial_active_names re-advertises it.
                        if activation_state is not None:
                            # Persist the FULL requested step-tool set (like tool_load) —
                            # merge_activated_tools re-budgets across the cumulative union,
                            # so passing the this-turn-capped subset would permanently drop
                            # a step tool the cumulative budget could still hold.
                            activation_state["activated_tools"] = merge_activated_tools(
                                activation_state["activated_tools"], step_tools,
                                catalog=discovery_catalog,
                                context_length=context_length,
                            )
                            activation_state["dirty"] = True
                        if len(names_to_activate) < len(step_tools):
                            payload["note"] = (
                                f"Activated {len(names_to_activate)} of {len(step_tools)} step tools "
                                "(token budget); call tool_load for the rest as you reach those steps."
                            )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": True, "result": payload, "error": None,
                    }}
                    continue

                # F7c — load_skill is CONSUMER-LOCAL (twin of tool_load/workflow_load):
                # return one or more skills' full L2 bodies from SYSTEM_SKILLS so the model
                # can follow the workflow it saw in the L1 index. Executes nothing, activates
                # no tools — the body lands as this tool result and persists in message
                # history like any other, so a later turn still has it (subject to compaction).
                if c["name"] == LOAD_SKILL_NAME:
                    args_obj = _parse_tool_args(c["arguments"])
                    _codes = [str(args_obj.get("skill", "") or "")] if args_obj.get("skill") else []
                    _codes += [str(x) for x in (args_obj.get("skills") or []) if x]
                    payload = load_skill_result(_codes)
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": True, "result": payload, "error": None,
                    }}
                    continue

                # MCP-fanout C-FT — find_tools is CONSUMER-LOCAL: it never goes to
                # a domain service. Run the in-memory catalog search, union the
                # matched names into the active set (so the NEXT pass advertises
                # their full schemas), and feed the result back. It carries no
                # write → it does NOT count against the write budget (H9). H6/H10:
                # the result distinguishes "no match" / "weak match" /
                # "provider temporarily unavailable" so the agent never falsely
                # denies a covered capability.
                if discovery and c["name"] == FIND_TOOLS_NAME:
                    args_obj = _parse_tool_args(c["arguments"])
                    intent = str(args_obj.get("intent", "") or "")
                    if surface_tracker is not None:
                        payload_as = surface_tracker.discovering(intent)
                        if payload_as is not None:
                            yield {"agent_surface": payload_as}
                    limit = args_obj.get("limit") or FIND_TOOLS_DEFAULT_LIMIT
                    try:
                        limit = int(limit)
                    except (TypeError, ValueError):
                        limit = FIND_TOOLS_DEFAULT_LIMIT
                    # Part A — optional group scoping (tool-catalog-simplification spec).
                    group = args_obj.get("group") or None

                    # D-FINDTOOLS-BLANK-INTENT-LOOP — the true failure shape is
                    # NO group + blank intent (this is what `_blank_intent_result()`
                    # in tool_discovery.py answers with the same note every time);
                    # `group` set + blank intent is the legitimate enumeration
                    # mode and returns real tools, so it never counts here.
                    if not group and not intent.strip():
                        if blank_tool_args_streak >= BLANK_TOOL_ARGS_CAP:
                            guidance = {
                                "error": "blank_tool_args_capped",
                                "message": (
                                    "find_tools has been called with no `intent` "
                                    f"{blank_tool_args_streak + 1} times this turn — "
                                    "STOP calling find_tools again without a real, "
                                    "non-empty `intent` string. If you cannot form one, "
                                    "tell the user directly that tool discovery is not "
                                    "working right now instead of retrying."
                                ),
                            }
                            logger.warning(
                                "D-BLANK-TOOL-ARGS-LOOP: capped session=%s "
                                "after %d consecutive blank/invalid-args tool calls "
                                "this turn (model_ref=%s, tool=%s)",
                                session_id, blank_tool_args_streak + 1, model_ref, c["name"],
                            )
                            # Inspector — surface the trip as a trace span (same
                            # convention as the D7 overflow span below) so the GUI
                            # shows a degraded-tool-calling turn, not just a log line.
                            if trace is not None:
                                trace.add(
                                    "compile", "T6", "tools",
                                    f"blank_tool_args_capped:{c['name']}",
                                    is_error=True,
                                )
                            working.append({
                                "role": "tool", "tool_call_id": c["id"],
                                "content": tool_result_content(guidance),
                            })
                            yield {"tool_call": {
                                "id": c["id"], "iteration": iteration, "tool": c["name"],
                                "args": args_obj, "ok": False,
                                "result": None, "error": guidance["message"],
                            }}
                            continue
                        blank_tool_args_streak += 1
                    else:
                        blank_tool_args_streak = 0
                    # Design item 1 (2026-07-07 discovery-hardening plan, embeddings
                    # sub-item / OQ4) — `session_id` feeds the retry-cap tracker
                    # (`FindToolsAttemptTracker`) so a repeated/near-duplicate search
                    # in THIS session gets the "stop searching, not supported" note.
                    # review-impl HIGH-2 fix: `model_source`/`model_ref` are NO
                    # LONGER passed here — `find_tools_result_async` used to reuse
                    # THIS TURN's own chat-completion model for the embed call,
                    # which most chat models can't do at all; it now resolves the
                    # user's own configured embedding-capable model independently
                    # (provider-registry `embedding`-capability default), keyed only
                    # by `user_id`. Mandatory fallback inside `search_catalog_semantic()`
                    # means this never ranks worse than the old token-overlap-only
                    # path on an embed failure OR when no embedding model is configured.
                    payload, matched = await find_tools_result_async(
                        discovery_catalog or [], intent, limit,
                        exclude=set(ALWAYS_ON_CORE_NAMES),
                        catalog_meta=knowledge_client.get_catalog_meta(user_id),
                        group=group,
                        session_id=session_id,
                        user_id=user_id,
                    )
                    # review-impl HIGH-3 fix: enumeration mode (`group` set, blank
                    # `intent`) returns EVERY non-legacy tool in a domain unranked —
                    # up to ~56 for composition — and unioning that unbounded set
                    # into `active_tool_names` blew past the token-budget discipline
                    # `merge_activated_tools`/`budget_names_by_tokens` already
                    # enforce for the NEXT-turn persisted `activated_tools` set
                    # (curated mode only); THIS turn's `active_tool_names` (which
                    # controls whose FULL SCHEMA `_advertise_discovery_tools` sends
                    # on the next pass, independent of curated/non-curated mode) had
                    # no budgeting at all. The full unranked list still reaches the
                    # model in `payload["tools"]` (cheap — names+descriptions only);
                    # only what gets its full schema advertised is capped here, same
                    # ceiling the hot-seed uses (see docs/eval/context-budget/
                    # context-explosion-investigation-2026-07-06.md — the exact
                    # explosion class this closes off for the enumeration path too).
                    if payload.get("enumerated"):
                        from app.services.tool_surface import (
                            HOT_SEED_TOKEN_BUDGET,
                            budget_names_by_tokens_ex,
                        )
                        names_to_activate, _dropped_by_budget = budget_names_by_tokens_ex(
                            discovery_catalog or [], matched,
                            token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
                        )
                        # CP-0.2 — register what the budget deleted. Arm E: the budgeter
                        # dropped the one tool the model needed and returned only the
                        # survivors, so the tool left the surface and the record at the same
                        # instant. `find_tools` is cited as the backstop, which is exactly
                        # why it must be recorded: a backstop nobody can see fire is a claim.
                        _budget_withheld.extend(
                            {"tool": _n, "stage": "token_budget",
                             "reason": "did not fit the activation token budget"}
                            for _n in _dropped_by_budget
                        )
                    else:
                        names_to_activate = set(matched)
                    active_tool_names.update(names_to_activate)
                    if curated and activation_state is not None:
                        from app.services.tool_surface import merge_activated_tools
                        activation_state["activated_tools"] = merge_activated_tools(
                            activation_state["activated_tools"], matched,
                            catalog=discovery_catalog,
                            context_length=context_length,
                        )
                        activation_state["dirty"] = True
                    if surface_tracker is not None:
                        act_count = (
                            len(activation_state["activated_tools"])
                            if activation_state is not None
                            else len(active_tool_names)
                        )
                        payload_as = surface_tracker.activated(act_count)
                        if payload_as is not None:
                            yield {"agent_surface": payload_as}
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": True,
                        "result": payload, "error": None,
                    }}
                    continue

                # T6/D6 (Context Budget Law) — conversation_search is CONSUMER-LOCAL
                # (like find_tools): a pure READ over THIS session's raw turns in
                # Postgres — the D6 recovery net (pull back a fact dropped from a
                # compaction summary). It carries no write, so it does NOT decrement
                # the write budget (H9). A DB error / empty result returns a
                # self-correcting payload, never a silent no-op (H6/H10).
                if c["name"] == CONVERSATION_SEARCH_NAME:
                    args_obj = _parse_tool_args(c["arguments"])
                    payload = await run_conversation_search(
                        get_pool(),
                        session_id=session_id,
                        owner_user_id=user_id,
                        args=args_obj,
                    )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    _cs_ok = not payload.get("error")
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": _cs_ok,
                        "result": payload if _cs_ok else None,
                        "error": payload.get("error"),
                    }}
                    continue

                # B1 / WS-1.9 (spec 07 §Q3/§Q4) — chat_search_sessions: CROSS-session recall of what
                # the user told the ASSISTANT. Owner-scoped read (no write budget). GATED to assistant
                # sessions here: a non-assistant (novel/roleplay) session must NOT recall the user's
                # work colleagues (§Q4 — returns zero, self-correcting message). One cheap kind lookup.
                if c["name"] == CHAT_SEARCH_SESSIONS_NAME:
                    args_obj = _parse_tool_args(c["arguments"])
                    _kind = await get_pool().fetchval(
                        "SELECT session_kind FROM chat_sessions WHERE session_id = $1", session_id,
                    )
                    if _kind != "assistant":
                        payload = {"query": str(args_obj.get("query", "")), "count": 0, "hits": [],
                                   "message": "Cross-session recall is only available in your assistant."}
                    else:
                        payload = await run_chat_search_sessions(
                            get_pool(), owner_user_id=user_id, args=args_obj,
                        )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    _cs_ok = not payload.get("error")
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": _cs_ok,
                        "result": payload if _cs_ok else None,
                        "error": payload.get("error"),
                    }}
                    continue

                # P5 REG-P5-01 — run_subagent is CONSUMER-LOCAL (like find_tools):
                # look up the persona, run a nested ISOLATED turn using ONLY its
                # scoped tools, and feed back the synthesized text. Depth 0 only (a
                # subagent can never spawn another). A miss returns a result.error
                # the model can self-correct from (no silent no-op). The nested
                # tokens sum into the turn total (design D10 attribution).
                if (
                    subagent_depth == 0
                    and subagent_defs
                    and c["name"] == RUN_SUBAGENT_NAME
                ):
                    args_obj = _parse_tool_args(c["arguments"])
                    payload, sub_in, sub_out = await _run_subagent_call(
                        args=args_obj,
                        subagent_defs=subagent_defs,
                        full_catalog=(discovery_catalog if discovery else tools) or [],
                        model_source=model_source,
                        model_ref=model_ref,
                        user_id=user_id,
                        gen_params=gen_params,
                        knowledge_client=knowledge_client,
                        session_id=session_id,
                        project_id=project_id,
                        caller_max_iterations=max_iterations,
                        decision_check=decision_check,
                        hooks=hooks,
                        effective_limit=effective_limit,
                        subagent_depth=subagent_depth,
                        caller_permission_mode=permission_mode,
                        context_length=context_length,
                    )
                    total_input += sub_in
                    total_output += sub_out
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(payload),
                    })
                    _sub_ok = not payload.get("error")
                    tool_chunk = {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": _sub_ok,
                        "result": payload if _sub_ok else None,
                        "error": payload.get("error"),
                    }
                    if _sub_ok:
                        # M4 — a visible "subagent ran" activity, grouped distinctly
                        # (name + which tools it used). No undo — a delegate read.
                        tool_chunk["activity"] = {
                            "op": RUN_SUBAGENT_NAME,
                            "summary": f"Ran subagent '{payload.get('subagent', '')}'",
                            "subagent": payload.get("subagent", ""),
                            "tools_used": payload.get("tools_used", []),
                            "undo": {"available": False},
                        }
                    # CP-0.3 — a subagent run IS a real execution (it dispatched tools of its own),
                    # so it is `tool`, not `meta`. `meta` is reserved for the runtime answering out
                    # of its own catalog without anything running.
                    instrument.stamp_tool_call(tool_chunk, source=instrument.SOURCE_TOOL)
                    yield {"tool_call": tool_chunk}
                    continue

                # P5 REG-P5-01 — execute-time scope whitelist (defense-in-depth):
                # inside a nested sub-run, a tool call NOT in the subagent's scoped
                # set NEVER executes — it returns a result.error. Advertise-time
                # scoping already hides these tools; this catches a sub-model that
                # fabricates an out-of-scope (or frontend/meta) name anyway.
                if allowed_tool_names is not None and c["name"] not in allowed_tool_names:
                    args_obj = _parse_tool_args(c["arguments"])
                    scope_err = (
                        f"'{c['name']}' is not available to this subagent — it is "
                        "outside the subagent's tool scope."
                    )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"error": scope_err}),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": scope_err,
                    }}
                    continue

                if surface_tracker is not None:
                    payload_as = surface_tracker.tool_running(c["name"])
                    if payload_as is not None:
                        yield {"agent_surface": payload_as}

                # ── Track C WS-3 — the STANDING REFUSAL ("Never allow") ──────────────
                # Deliberately evaluated FIRST, for EVERY tool, before any other arm can
                # execute or suspend. A refusal is not a prompt: it must hold wherever the
                # tool could run, so it must NOT be nested inside the tier/mode conditions
                # that gate the approval CARD.
                #
                # The first cut of this slice made exactly that mistake — the deny read sat
                # inside `if tier == "A" and permission_mode == "write"`, so a Tier-R tool, a
                # plan-mode `plan_*` tool, and a frontend tool were all listed in the panel
                # under "Blocked — never runs" while the agent went on calling them. That is
                # the very write-only-behavior bug this slice exists to kill, wearing the
                # deny hat. Ordering matters as much as the check: it sits above the frontend
                # -tool suspend, the H7 volume cap and the hook's require_approval arm,
                # because a card the user can click "Always allow" on would otherwise let one
                # click silently overwrite a permanent refusal.
                #
                # ANY deny row blocks the tool, whatever kind it was recorded under: the user
                # was shown the words "Never allow", and a consent surface must mean them.
                _denied_kinds: list[str] = []
                _decision_unreadable = False
                if decision_check is not None:
                    for _dk in ("mutation", "spend"):
                        try:
                            if await decision_check(c["name"], _dk) == "deny":
                                _denied_kinds.append(_dk)
                        except Exception:
                            # An unreadable decision is UNKNOWN — we cannot see whether the
                            # user set "Never allow". We FAIL CLOSED for THIS tool (skip it
                            # with a transient error below), not open: a paid/mutation tool
                            # would re-prompt downstream, but a non-paid Tier-R READ has no
                            # other gate, so treating the error as "not denied" would run a
                            # possibly-denied tool during a DB blip (adversarial-review
                            # RISK-2). Per-tool skip — tools whose reads succeeded are
                            # unaffected, so a blip degrades gracefully without a blanket block.
                            _decision_unreadable = True
                            logger.warning(
                                "standing-decision read failed for %s (kind=%s) — failing CLOSED (skip, retry)",
                                c["name"], _dk, exc_info=True,
                            )
                # Fail CLOSED here ONLY for a tool that has NO downstream prompt arm to
                # catch it: a PAID tool re-prompts on the spend axis and a Tier-A write
                # re-prompts on the mutation axis (both already fail closed on a read
                # error, below). A non-paid, non-Tier-A-write READ hits neither — so if
                # its deny-read was unreadable, THIS is the only place to honor a possible
                # "Never allow". Gating on the tool's own tier/paid avoids regressing the
                # paid/Tier-A prompt paths (which must show a card, not a skip).
                _dl_def = (cat_index if discovery else plain_index).get(c["name"], {})
                _has_downstream_gate = tool_paid(_dl_def) or (
                    tool_tier(_dl_def) == "A" and permission_mode == "write"
                )
                if not _denied_kinds and _decision_unreadable and not _has_downstream_gate:
                    _blip_err = (
                        f"'{c['name']}' was not run: your tool-permission setting could not be "
                        "read just now (a transient error). It was skipped to respect a possible "
                        "'Never allow'. Try again in a moment."
                    )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"error": _blip_err}),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": _parse_tool_args(c["arguments"]), "ok": False,
                        "result": None, "error": _blip_err,
                    }}
                    continue
                if _denied_kinds:
                    _deny_err = (
                        f"'{c['name']}' is blocked: you chose 'Never allow' for it. It was "
                        "NOT run. Do not ask to run it again — either achieve the goal another "
                        "way, or tell the user they can re-enable it in Settings → Tool permissions."
                    )
                    logger.info(
                        "tool %s blocked by a standing deny (kinds=%s)", c["name"], _denied_kinds
                    )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"error": _deny_err}),
                    })
                    # 🔴 **THE SAME CONFLATION AS THE RESUME DENIAL, ONE SITE OVER.** Iteration 2
                    # of the tool-v2 loop typed the human's "no" on the RESUME path
                    # (`denied_by_user`); this is the human's PERMANENT no, and it was still
                    # falling through to the chokepoint's fail-closed default — recorded `failed`
                    # with `call_outcome_inferred`, as if the tool had broken.
                    #
                    # Measured 2026-08-11: 15 calls across 3 sessions, all `glossary_adopt_standards`,
                    # every one typed as a failure. A user choosing "Never allow" is the consent
                    # surface working exactly as designed — it is the clearest refusal in the
                    # product — and it is the one the corpus called a defect.
                    #
                    # `denied_standing` keeps it separable from `denied_by_user`: a decision made
                    # ONCE for all future turns and a decision made about THIS call are different
                    # facts about the user, and merging them would hide which consent surface is
                    # actually being used.
                    yield {"tool_call": instrument.stamp_refused({
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": _parse_tool_args(c["arguments"]), "ok": False,
                        "result": None, "error": _deny_err,
                    }, "denied_standing")}
                    continue

                # D-TOOLCALL-GEMMA-INTERIOR-LEAK — the args STILL carry this model family's
                # native control tokens, so `_split_interior_leaked_tool_calls` could not
                # resolve the shape and `_parse_tool_args` refused the payload. Refuse the
                # call, and do NOT report it as a schema / missing-args mistake: the payload
                # is a DECODER artifact, not what the model wrote. Misattributing it is what
                # made the live incident unrecoverable — the model was told it sent a bad
                # enum value that json repair had synthesized out of a swallowed control
                # token, so no amount of self-correction could reach it and the turn collapsed
                # into 10,882 characters of repeated prose. Name the real fault and ask for
                # ONE call — the shape this decoder gets right.
                #
                # Placed BEFORE the frontend/backend fork on purpose: both sides validate
                # against a schema and would otherwise blame the model. The live incident hit
                # BOTH (`glossary_propose_entity_edit` is a frontend tool,
                # `glossary_propose_batch` a backend one), so a backend-only guard would have
                # fixed half the bug and left the other half looking identical.
                if _has_leak_marker(c.get("arguments") or ""):
                    # Counts toward the existing per-turn cap: the model is blameless, but a
                    # decoder that leaks every pass must still terminate the turn rather than
                    # trade honest errors until MAX_TOOL_ITERATIONS runs out.
                    blank_tool_args_streak += 1
                    _leak_msg = (
                        f"The arguments for '{c['name']}' arrived corrupted — your output "
                        "carried tool-call control tokens inside the JSON, so the payload "
                        "could not be trusted and the call was NOT run. This is a decoding "
                        "fault, not an error in your reasoning: do not change which tool you "
                        "chose, and do not apologise for a wrong argument value. "
                        + (
                            "You have hit the retry limit for this — tell the author plainly "
                            "that the call could not be sent, and stop."
                            if blank_tool_args_streak >= BLANK_TOOL_ARGS_CAP else
                            "Emit exactly ONE tool call, with plain JSON arguments and "
                            "nothing after the closing brace."
                        )
                    )
                    logger.warning(
                        "D-TOOLCALL-GEMMA-INTERIOR-LEAK: refused to dispatch %r with "
                        "marker-bearing args (session=%s, streak=%d): %r",
                        c["name"], session_id, blank_tool_args_streak,
                        (c.get("arguments") or "")[:200],
                    )
                    if trace is not None:
                        trace.add("compile", "T6", "tools",
                                  f"args_corrupted:{c['name']}", is_error=True)
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(
                            {"error": "tool_args_corrupted_by_decoder", "message": _leak_msg}
                        ),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": {}, "ok": False, "result": None, "error": _leak_msg,
                    }}
                    continue

                # DELIBERATELY is_frontend_tool, not is_browser_executed: this asks
                # "does chat-service INTERCEPT and suspend here?". propose_edit/ui_*
                # are browser-executed but route to ai-gateway and are detected from
                # the directive in the RESULT, so they must not be intercepted here.
                if is_frontend_tool(c["name"]):
                    # Same gemma {"args":{…}} wrap-repair the backend dispatch does below —
                    # a wrapped frontend-tool payload must be unwrapped BEFORE it is frozen
                    # into the suspended run, or the resume/resolver sees the envelope instead
                    # of the real fields. Load-bearing for the rail: its confirm gate
                    # (glossary_confirm_action) is a frontend tool, and a wrapped confirm_token
                    # would strand the confirm on resume. Protect ui_show_panel's real `args`
                    # param via its schema (generic index for ui_*/propose_*, catalog for
                    # domain confirm tools) — never a bare tool_def=None here.
                    # Resolve the tool's canonical schema. The by-name map is the
                    # COMPLETE frontend-tool set (Phase 0), so the two book-scoped
                    # glossary tools are validated even when this turn didn't
                    # advertise them (called-but-not-advertised → would otherwise
                    # fail-open and skip the gate).
                    _fe_def = (
                        cat_index.get(c["name"])
                        or plain_index.get(c["name"])
                        or frontend_tool_def_by_name(c["name"])
                    )
                    _fe_args = _unwrap_wrapped_args(_parse_tool_args(c["arguments"]), _fe_def)
                    # D-FE-TOOL-CONTEXT-IDS (2026-07-26, Mị Đế dogfood) — S02 parity for
                    # frontend tools: they are validated BEFORE the backend dispatch's
                    # context-id injection, so the session's known book_id never reached
                    # them and a weak model had to transcribe it itself — it invented one
                    # (live: "mình sẽ sử dụng một ID giả định") → guaranteed validation
                    # failure, every call. Same injector, same conservative rules
                    # (fill-blank + replace-malformed + studio single-book override).
                    _inject_context_ids(
                        _fe_args, _fe_def,
                        book_id=(context_ids or {}).get("book_id"),
                        chapter_id=(context_ids or {}).get("chapter_id"),
                        project_id=(context_ids or {}).get("project_id"),
                        studio=bool((context_ids or {}).get("studio")),
                        id_ledger=_id_ledger,
                    )
                    # Phase 0 (frontend-tools → MCP migration) — the MCP-native
                    # validation seam. A frontend tool used to SUSPEND on its raw
                    # args with no validation, so a mis-shaped call (the reported
                    # 019f771a bug: propose_edit with propose_record_edit's args)
                    # rendered an un-appliable card. Validate against the tool's OWN
                    # canonical inputSchema — the same enforcement a backend MCP tool
                    # already gets — and on a mismatch feed the model the standard
                    # `required: missing properties` signal it knows how to repair,
                    # instead of suspending. Never suspend an un-appliable card.
                    # TOOL-V2 LOOP #5 — the SAME check the backend dispatch runs, run here too.
                    # DQ-5 is the standing lesson: this branch refuses or suspends and never
                    # reaches the backend's pre-dispatch checks, which is exactly how CP-5.3's
                    # resolver became unreachable for frontend tools and how the context-id
                    # injector missed them before it. `glossary_propose_entity_edit` is in the
                    # measured population (book_id == entity_id, 2 calls / 2 sessions), so a
                    # one-sided gate would leave it out by construction. Pure argument check,
                    # no dispatch — running it twice costs nothing and forgetting it costs a
                    # whole surface.
                    # 🔴 D-FJ-11 PARITY, and the next arm this branch was missing. The backend
                    # dispatch drops an `*_id` the model filled with something that is not an
                    # identifier — a NAME, a placeholder, a SCREAMING_SNAKE stub — and then hands
                    # the NAME back as the query to search with. This branch never ran any of it.
                    #
                    # MEASURED 2026-08-23, composition_entity_override_edit at K=5: the model called
                    # glossary_propose_entity_edit with entity_id="Aldric Vane" on all five runs and
                    # got no repair, because that tool is a FRONTEND tool and returns above. The
                    # name-repair sentence fired 0 times in the whole batch.
                    #
                    # This is the same divergence the comments above already record twice — the
                    # context-id injector missed this branch, CP-5.3's resolver became unreachable
                    # through it — so each repair gets hand-ported the run after it is found
                    # missing. Porting this one rather than filing it again.
                    _fe_invented = _invented_supplier_ids(
                        _fe_args, None,
                        ((_fe_def or {}).get("function", {}).get("parameters", {}) or {})
                        .get("properties"),
                    )
                    _fe_dropped = {n: _fe_args.get(n) for n in _fe_invented}
                    for _n in _fe_invented:
                        _fe_args.pop(_n, None)
                    if _fe_invented:
                        logger.info(
                            "dropped non-identifier value(s) %s from FRONTEND tool %s "
                            "(session=%s); values=%s",
                            _fe_invented, c["name"], session_id,
                            {k: (v if isinstance(v, str) and len(v) <= 80 else str(v)[:80])
                             for k, v in _fe_dropped.items()},
                        )
                    from app.agentruntime.toolcontract import (
                        duplicate_identifier as _fe_dup_check,
                        duplicate_identifier_message as _fe_dup_message,
                    )
                    _fe_dupe = _fe_dup_check(_fe_args)
                    _fe_err = (
                        _fe_dup_message(*_fe_dupe) if _fe_dupe is not None
                        else validate_frontend_tool_args(c["name"], _fe_args, _fe_def)
                    )
                    if _fe_err is not None and _MISSING_REQUIRED_ARGS_MARKER in _fe_err:
                        # The dropped NAME is the query the recovery search needs — the same
                        # sentence the backend appends. Without it the model is told only that the
                        # argument is MISSING, and its follow-up search goes out blank.
                        _fe_named = _name_like_dropped_ids(_fe_dropped)
                        if _fe_named:
                            _fe_err = _fe_err + " " + _fe_named
                    if _fe_err is not None:
                        # A missing-required miss feeds the SAME cross-tool blank/
                        # invalid-args streak breaker the backend feeds (mirrors the
                        # reset/increment rule at the backend dispatch site below).
                        if _MISSING_REQUIRED_ARGS_MARKER in _fe_err:
                            blank_tool_args_streak += 1
                        # D-FE-TOOL-LOOP — frontend tools bypassed BOTH loop guards (the
                        # repeated-failure breaker and the blank-args cap both live on the
                        # backend dispatch path, below this branch), so a model that kept
                        # re-emitting the same invalid frontend call looped unbounded.
                        # Measured live (Mị Đế dogfood, session 019f9f2e): ~205 identical
                        # malformed glossary_propose_entity_edit calls in ONE turn while the
                        # backend sibling tripped its breaker at 2. Feed the shared
                        # (tool → error → count) map and short-circuit + de-advertise at the
                        # same cap a backend tool gets.
                        _err_sig = _fe_err[:200]
                        _fe_fails = fail_by_tool_error.setdefault(c["name"], {})
                        _fe_fails[_err_sig] = _fe_fails.get(_err_sig, 0) + 1
                        if _fe_fails[_err_sig] > REPEATED_FAILURE_CAP:
                            _fe_err = (
                                f"'{c['name']}' has already FAILED {_fe_fails[_err_sig]} times "
                                f"this turn with the same invalid arguments: {_err_sig} — "
                                "retrying it keeps hitting the same wall. STOP calling it. "
                                "Fix EXACTLY what that error says is wrong, use a DIFFERENT "
                                "tool, or tell the user plainly what is blocking you."
                            )
                            failure_suppress.add(c["name"])
                            logger.info(
                                "repeated-failure breaker (frontend): %s failed %d× with the "
                                "same validation error this turn — short-circuited + "
                                "de-advertised", c["name"], _fe_fails[_err_sig],
                            )
                        working.append({
                            "role": "tool", "tool_call_id": c["id"],
                            "content": tool_result_content({"error": _fe_err}),
                        })
                        # 🔴🔴 **CP-5.4/5.5 — THE FIFTH INSTANCE OF THE SAME CONFLATION, AND THE
                        # LARGEST SINGLE POPULATION IN THE CORPUS.** `glossary_propose_entity_edit`
                        # is recorded at **101 calls / 12 sessions / 0% success**, and every one of
                        # those rows carries `result: null` with an `error` that is THIS FUNCTION'S
                        # OWN PROSE — the tool never ran. They are runtime REFUSALS wearing a
                        # tool's name, exactly like 5.5's suspensions, 5.4's owed arguments and
                        # 5.7's breaker output, and while they are typed `failed` they inflate the
                        # very corpus every member on this checkpoint is measured against.
                        #
                        # 89 of the 101 sent a model-invented PLACEHOLDER in `entity_id`
                        # (`placeholder_id_1` ×60, `placeholder_id` ×29) — the class 5.3-pilot
                        # separated out and 5.4 owns. It is split from a plain schema miss here so
                        # the two never merge into one number: one says *the model invented a value
                        # it had no way to know*, the other says *the model got the shape wrong*.
                        #
                        # ✖ **AND THIS DOES NOT CLAIM TO CHANGE THE MODEL'S BEHAVIOUR.** The
                        # remedy this defect already received was PROSE — the re-route text a few
                        # lines up in `validate_frontend_tool_args`, added 2026-07-22 after the
                        # same failure was measured at 13 calls. The corpus AFTER that fix is the
                        # 101. What is claimed is what is verifiable: the outcome is typed, the
                        # refusal is counted as a refusal, and the cost was already removed because
                        # nothing was dispatched.
                        _fe_chunk = {
                            "id": c["id"], "iteration": iteration, "tool": c["name"],
                            "args": _fe_args, "ok": False, "result": None, "error": _fe_err,
                        }
                        yield {"tool_call": instrument.stamp_refused(
                            _fe_chunk,
                            "unresolved_identifier" if _UNRESOLVED_ID_RE.search(_fe_err)
                            else "invalid_arguments",
                        )}
                        continue
                    blank_tool_args_streak = 0  # a valid frontend-tool call
                    # A valid call breaks the failure loop — reset the tool's failure map
                    # (mirrors the backend success-clears rule at the dispatch site below).
                    fail_by_tool_error.pop(c["name"], None)
                    suspended_call = {
                        "id": c["id"],
                        "name": c["name"],
                        "args": _fe_args,
                    }
                    break
                args_obj = _parse_tool_args(c["arguments"])
                # gemma arg-wrapping repair — a mid-tier model sometimes wraps the WHOLE
                # payload in a single {"args": {...}} envelope (measured live: it sent
                # glossary_extract_entities_from_doc {"args":{"book_id":…,"source_markdown":…}}
                # against a FLAT schema, so book_id was hidden and the tool got nothing → the
                # cast never landed). Unwrap a lone "args" (or "arguments") wrapper when the
                # tool's real schema does NOT declare that property. General across every
                # backend tool, and a no-op for a well-formed call.
                args_obj = _unwrap_wrapped_args(
                    args_obj, cat_index.get(c["name"]) or plain_index.get(c["name"])
                )
                # Undo a 1-element-list wrapping of a scalar id arg (gemma: project_id=[uuid]).
                _coerce_listed_scalar_ids(args_obj)
                # T16-D1 — and the mirror case: the right id under a near-miss KEY (`id`, `ids`,
                # `<param>s`). Measured on book_read, where 56 of 89 "missing book_id" refusals
                # were carrying the correct UUID all along. Runs AFTER the wrapper unwrap so a
                # `{"params": {...}}` payload is already flat by the time this looks at it.
                args_obj = _repair_aliased_required_id(
                    args_obj, cat_index.get(c["name"]) or plain_index.get(c["name"])
                )
                # Undo a STRUCTURED arg sent as stringified JSON (gemma: save_draft body="[{...}]").
                # Measured live in M0a — this is why the flagship's drafted chapter was always empty.
                _coerce_json_string_structs(
                    args_obj, cat_index.get(c["name"]) or plain_index.get(c["name"])
                )
                # S02 fix — fill the session's known context-ids (book_id/chapter_id/project_id)
                # into this backend tool's args when it declares them and the model left them
                # blank. Done BEFORE the blank-args cap + dispatch so a would-be
                # `VALIDATION: missing book_id` call succeeds on the first try instead of looping.
                _inject_context_ids(
                    args_obj,
                    cat_index.get(c["name"]) or plain_index.get(c["name"]),
                    book_id=(context_ids or {}).get("book_id"),
                    chapter_id=(context_ids or {}).get("chapter_id"),
                    project_id=(context_ids or {}).get("project_id"),
                    studio=bool((context_ids or {}).get("studio")),
                    id_ledger=_id_ledger,
                )
                # ── CP-3 · THE EXECUTOR SUPPLIES THE IDENTIFIER ─────────────────────────────
                # 🔴 **POSITION IS THE WHOLE MECHANISM, AND THE FIRST PLACEMENT WAS WRONG.** This
                # sat just before `mcp_execute_tool`, ~700 lines below — AFTER the
                # missing-required-args interception. So the one case the plan exists to fix, a
                # BLANK first attempt (`book_read {}`), was rejected before the plan could fill it,
                # and the executor only ever saw the model's SECOND, already-correct call.
                # Measured: V-METRIC round 3 read 1/10 first-attempt on the plan arm against 0/10
                # on the control and looked like a null result. It was a placement bug.
                # Ordering now: context-ids -> PLAN -> missing-args -> dispatch.
                # 🔴 **THIS IS BRICK 4, AND IT IS THE LINE THAT MAKES `resolve_arguments` REACHABLE.**
                # Until 2026-08-09 that function had ZERO production callers: the plan reached the
                # model as a system message and the model RETYPED the identifier out of it. Retyping
                # is the failure — `entity_id:019fafa2-…` at step 12, `"0"` at step 16.
                #
                # Per-parameter replacement, plan wins. For a parameter the plan owns, whatever the
                # model typed is DISCARDED; parameters it does not own (the injected context ids
                # above) are untouched. A merge that let the model's value win on a blank would be
                # the fallback-to-asking this whole mechanism exists to refuse.
                _plan_supplied: dict | None = None
                if plan_turn is not None:
                    from app.services.plan_exec import bound_arguments
                    _bound = bound_arguments(plan_turn.spec, plan_turn.state, c["name"])
                    if _bound:
                        # 🔴 **WHAT THE MODEL SENT IS CAPTURED BEFORE IT IS OVERWRITTEN, AND IT GOES
                        # INTO THE ROW.** Without this the recorded call shows only the final value,
                        # so a plan-supplied argument and a model-typed one are THE SAME ROW — the
                        # exact merge `outcome_source` and `tool_calls[].source` each exist to undo.
                        # It also made a measurement wrong: the first call-level V-METRIC graded
                        # `args.book_id` in both arms and read 15/15 for the plan arm, which is
                        # TAUTOLOGICAL — the executor writes that value, so it cannot be wrong. Only
                        # a record that separates the two populations can be graded at all.
                        _plan_supplied = {
                            "params": sorted(_bound),
                            "model_sent": {k: args_obj.get(k) for k in sorted(_bound)},
                            "overrode": sorted(
                                k for k, v in _bound.items()
                                if k in args_obj and args_obj[k] != v
                            ),
                        }
                        logger.info(
                            "CP-3 executor: supplying %s to %s from the plan (model sent %s)",
                            _plan_supplied["params"], c["name"], _plan_supplied["model_sent"],
                        )
                        args_obj.update(_bound)

                # ── TOOL-V2 LOOP #5 · ONE ID IN TWO DIFFERENT ID FIELDS ─────────────────────
                # 🔴 **MEASURED: 135 calls over 7 tools and 19 sessions, and NOT ONE SUCCEEDED.** The largest are
                # `glossary_get_entity` with `book_id == entity_id` (71 calls / 5 sessions) and
                # `book_chapter_save_draft` with `book_id == chapter_id` (38 / 6). Zero successes
                # in 135 is the falsifier for the rule itself: one legitimate call of this shape
                # would be a counter-example, and the corpus has none.
                #
                # It is invisible to every check that already runs. Both values are well-formed
                # UUIDs, so the schema passes, `looks_like_an_id` says no resolution is needed,
                # and `_inject_context_ids` deliberately honours a valid-but-different id as a
                # cross-book call. The call dies at another service, naming the wrong thing:
                # `book_chapter_delete` got *"book not accessible"* for a book that was perfectly
                # accessible — the shared id WAS the book, reused for the chapter it did not have.
                # One session repeated that 14 times, another repeated its version 71.
                #
                # Placed BEFORE resolution because it is a pure argument check with no dispatch:
                # spending a resolver read on a call that cannot succeed either way is the cost
                # §3a is careful about. A REFUSAL, never a repair — the runtime knows both
                # arguments cannot be right and does not know which one is wrong.
                from app.agentruntime.toolcontract import (
                    duplicate_identifier as _dup_check,
                    duplicate_identifier_message as _dup_message,
                )
                _dupe = _dup_check(args_obj)
                if _dupe is not None:
                    _dup_msg = _dup_message(*_dupe)
                    logger.info("loop#5: refused %r — %s and %s are both %s",
                                c["name"], _dupe[0], _dupe[1], _dupe[2])
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(
                            {"error": "duplicate_identifier", "message": _dup_msg}),
                    })
                    yield {"tool_call": instrument.stamp_refused({
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": _dup_msg,
                    }, "duplicate_identifier")}
                    continue

                # ── CP-5.3 · IDENTIFIER RESOLUTION — a NAME in an id field ──────────────────
                # 🔴 **THE MEASURED FAILURE: 338 calls across 11 sessions sent a human name into an
                # id field** (`entity_id: "Ember Codex"`, `"Lâm Uyên"`, `"Count Dracula"`) — 99.5%
                # of every UUID-type failure. The tool answered `entity_id must be a UUID`: loud,
                # and not actionable.
                #
                # ORDER: context-ids -> PLAN -> RESOLUTION -> blank-check -> dispatch. **After the
                # plan on purpose** — a plan-bound argument is authoritative and already proven to
                # travel byte-exact, so re-resolving it would let a search outrank the executor.
                # Before dispatch, because the tool is where the failure currently happens.
                #
                # TWO BRANCHES, NO THIRD (§3a). Exactly one match at the declared quality
                # substitutes; zero or many REFUSE with candidates. The pilot measured ambiguity as
                # real rather than hypothetical — `Dracula` returns four exact matches tied at 0.9,
                # 37.5% of contested calls — so a "pick the best" arm would be a guess deciding a
                # correctness question on more than a third of the traffic.
                _resolution: dict | None = None
                _resolution_refusal: str | None = None
                try:
                    _rslv, _bind = _ref_registry(
                        lambda _n: declared_lane(cat_index.get(_n) or plain_index.get(_n) or {})
                    )
                except Exception:
                    _rslv, _bind = {}, {}
                if _bind:
                    from app.agentruntime.refresolve import (
                        Resolution as _Resolution, apply_resolutions as _apply_res,
                        decide as _ref_decide, pending_for as _ref_pending,
                        refusal_message as _ref_refusal,
                    )
                    _pending = _ref_pending(c["name"], args_obj, _bind, _rslv)
                    _res: list = []
                    for _p in _pending:
                        _rt0 = _time.monotonic()
                        try:
                            _renv = await knowledge_client.mcp_execute_tool(
                                user_id=user_id, session_id=session_id, project_id=project_id,
                                book_id=(context_ids or {}).get("book_id"),
                                tool_name=_p.resolver.tool, tool_args=_p.args,
                                admin_token=admin_token,
                            )
                        except Exception:
                            _renv = None
                        # 🔴 **A RESOLVER DISPATCH IS A REAL EXECUTION AND IS RECORDED AS ONE.**
                        # CP-0.3's positional gate caught this unstamped, and it was right: the
                        # tool genuinely runs. §3a's cost claim is *"~44 extra read dispatches
                        # replace 390 failed calls"* — a trade nobody can check if the numerator
                        # is invisible. It is NOT appended to `working`: the model never asked for
                        # this call and should not have to read it. `resolver_for` keeps the two
                        # populations apart, exactly as `plan_supplied` had to.
                        _rchunk = {
                            "id": f"{c['id']}:resolve:{_p.param}", "iteration": iteration,
                            "tool": _p.resolver.tool, "args": _p.args,
                            "ok": bool(_renv and _renv.get("success")),
                            "result": None, "error": None if _renv else "resolver dispatch failed",
                            "resolver_for": {"tool": c["name"], "param": _p.param,
                                             "sent": _p.name},
                        }
                        instrument.stamp_tool_call(
                            _rchunk, source=instrument.SOURCE_TOOL,
                            latency_ms=int((_time.monotonic() - _rt0) * 1000))
                        yield {"tool_call": _rchunk}
                        if not _renv or not _renv.get("success"):
                            # A resolver that fails is not a licence to guess and not a silent
                            # pass: the argument is left exactly as the model sent it and the
                            # outcome is recorded, so the call fails the way it does today rather
                            # than in a new way nobody can see.
                            _res.append(_Resolution(param=_p.param, ref_type=_p.resolver.ref_type,
                                                    sent=_p.name, outcome="resolver_failed"))
                        else:
                            _res.append(_ref_decide(_p.resolver, _p.param, _p.name,
                                                    _renv.get("result") or {}))
                    if _res:
                        # 🔴 WHAT THE MODEL SENT IS CAPTURED BEFORE THE OVERWRITE, for the reason
                        # `plan_supplied` had to: without it a resolved argument and a model-typed
                        # one are THE SAME ROW and no measurement can tell them apart.
                        _resolution = _apply_res(args_obj, _res)
                        if any(not r.ok for r in _res):
                            _resolution_refusal = _ref_refusal(_res)
                        logger.info("CP-5.3 resolution on %s: %s", c["name"], _resolution)

                if _resolution_refusal:
                    # The REFUSE branch. Still loud — the contract may remove a failure's COST, never
                    # its SIGNAL (§3) — but now actionable: it names what was sent, what happened,
                    # and the candidates, where today the model gets `entity_id must be a UUID`.
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(
                            {"error": "unresolved_reference", "message": _resolution_refusal}),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None,
                        "error": _resolution_refusal, "resolution": _resolution,
                    }}
                    continue

                # ── CP-6.1 · CLOSED-VOCABULARY RESOLUTION — a value outside the book's own set ──
                # 🔴 **MEASURED: `glossary_propose_entities` fails in 51 organic sessions, and 88 of
                # its 109 failures (81%) are `unknown kind`.** The largest remaining defect in the
                # co-writer journey by the honest denominator.
                #
                # 🔴 **AND THE REMEDY IT ALREADY HAS IS PROSE THAT MEASURABLY DID NOT WORK** — the
                # existing message explains the cause correctly and names both repair tools, and the
                # corpus after it is still 88 calls. Third time on this board. Worse, **it names
                # `glossary_propose_kinds`, which is `visibility: legacy`** in its own `_meta`, so
                # the one actionable thing it says points at a deprecated tool.
                #
                # What this adds is not a better sentence: it is **the book's actual vocabulary**,
                # read at dispatch, which a static JSON Schema cannot carry because the legal set
                # differs per book. TWO BRANCHES, NO THIRD — in the set, or refused with the set
                # named. **No fuzzy arm** (PO): `place` is never rewritten to `location`, because a
                # wrong kind is a silent bad write into canon, which is worse than the loud failure
                # it replaces. A normalised near-miss is SUGGESTED (`power_systems` →
                # `power_system`) and never substituted.
                _vocab_refusal: str | None = None
                _vocab_record: dict | None = None
                try:
                    _vocabs, _vbind = _vocab_registry(
                        lambda _n: declared_lane(cat_index.get(_n) or plain_index.get(_n) or {})
                    )
                except Exception:
                    _vocabs, _vbind = {}, {}
                if _vbind:
                    from app.agentruntime.vocabulary import (
                        decide as _vocab_decide, pending_for as _vocab_pending,
                        refusal_message as _vocab_refusal_message,
                    )
                    _vpending = _vocab_pending(c["name"], args_obj, _vbind, _vocabs)
                    _vdecisions: list = []
                    for _vp in _vpending:
                        # 🔴 **EACH ENUMERATION IS A REAL EXECUTION AND IS STAMPED AS ONE — AND
                        # CP-0.3's POSITIONAL GATE CAUGHT THE SECOND ONE UNSTAMPED HERE, exactly as
                        # it caught 5.3's resolver dispatch.** The first draft stamped only the
                        # ontology read and left the standards read invisible, which is how a
                        # mechanism's cost claim becomes uncheckable. Neither is appended to
                        # `working`: the model never asked for either read.
                        _venvs: dict[str, Any] = {}
                        for _which, _vtool, _vargs in (
                            ("source", _vp.vocabulary.source_tool, _vp.source_args),
                            ("standards", _vp.vocabulary.standards_tool, {}),
                        ):
                            if not _vtool:
                                continue
                            _vt0 = _time.monotonic()
                            try:
                                _venv = await knowledge_client.mcp_execute_tool(
                                    user_id=user_id, session_id=session_id, project_id=project_id,
                                    book_id=(context_ids or {}).get("book_id"),
                                    tool_name=_vtool, tool_args=_vargs, admin_token=admin_token,
                                )
                            except Exception:
                                _venv = None
                            _vchunk = {
                                "id": f"{c['id']}:vocab:{_vp.param}:{_which}",
                                "iteration": iteration, "tool": _vtool, "args": _vargs,
                                "ok": bool(_venv and _venv.get("success")),
                                "result": None,
                                "error": None if _venv else "vocabulary source dispatch failed",
                                "vocabulary_for": {"tool": c["name"], "param": _vp.param,
                                                   "sent": list(_vp.sent), "role": _which},
                            }
                            instrument.stamp_tool_call(
                                _vchunk, source=instrument.SOURCE_TOOL,
                                latency_ms=int((_time.monotonic() - _vt0) * 1000))
                            yield {"tool_call": _vchunk}
                            _venvs[_which] = _venv
                        _senv, _stdenv = _venvs.get("source"), _venvs.get("standards")
                        if not _senv or not _senv.get("success"):
                            # A source that fails is not a licence to refuse: the call proceeds
                            # exactly as it does today and fails at the tool if the kind is wrong.
                            # Failing CLOSED here would turn one degraded read into a blocked write.
                            continue
                        _vdecisions.append(_vocab_decide(
                            _vp, _senv.get("result") or {},
                            (_stdenv or {}).get("result") if _stdenv and _stdenv.get("success")
                            else None))
                    if _vdecisions:
                        _vocab_record = {
                            d.param: {"sent": list(d.sent), "outcome": d.outcome,
                                      "unknown": list(d.unknown), "adoptable": list(d.adoptable)}
                            for d in _vdecisions
                        }
                        if any(not d.is_ok for d in _vdecisions):
                            _vocab_refusal = _vocab_refusal_message(_vdecisions)

                if _vocab_refusal:
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(
                            {"error": "unknown_vocabulary_value", "message": _vocab_refusal}),
                    })
                    _vfail = {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None,
                        "error": _vocab_refusal, "vocabulary": _vocab_record,
                    }
                    # 5.7's typing: the tool did not fail, the runtime refused before the wire.
                    yield {"tool_call": instrument.stamp_refused(_vfail, "unknown_vocabulary_value")}
                    continue

                # The chat agent's arc-plan wants a SYNCHRONOUS plan (mode="rules"): a mid-tier
                # model cannot reliably watch a background llm-plan job, so it fires the async
                # job and leaves it unpolled (a §4 "async left unpolled" failure) and the
                # flagship rail never reaches draft-opening. rules mode lands the plan
                # synchronously (spec artifact, status=proposed, no job_id) so the driver
                # continues to the draft in one assent. Unconditional in the CHAT TOOL LOOP
                # (this dispatch) — the dedicated Plan Hub calls plan_propose_spec via its own
                # composition-service API, not this agent loop, so its rich llm planning is
                # unaffected. Earlier a rail-scoped guard fired inconsistently (gemma called the
                # tool on a turn the rail was not pinned → mode="llm" → an unpolled async job).
                if c["name"] == "plan_propose_spec" and args_obj.get("mode") != "rules":
                    args_obj["mode"] = "rules"
                # A2A phase-2: compose_prose → stream the composer model inline
                # and return its prose as the tool result. Usage is summed into
                # the turn (design D10) so both models are billed.
                if is_composer_tool(c["name"]) and composer_model is not None:
                    # Signal the UI before the (often slow) composer streams, so
                    # it can show "✍️ Drafting…" instead of a silent panel.
                    yield {"composing": {"active": True}}
                    try:
                        prose, c_in, c_out = await _run_composer(
                            client, composer_model, composer_system_prompt, args_obj, gen_params,
                        )
                    finally:
                        yield {"composing": {"active": False}}
                    total_input += c_in
                    total_output += c_out
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"prose": prose}),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": True,
                        "result": {"prose": prose}, "error": None,
                    }}
                    continue
                # RAID C2 (DR-C2) — ask-mode defense-in-depth BEHIND the surface
                # filter: a non-R server tool call that somehow reaches execution
                # in ask mode returns a tool-result error the model can
                # self-correct from — it NEVER executes. Tier is read from the
                # def itself (discovery catalog or the caller's plain defs);
                # unknown/untiered tools default R (inert) and pass through.
                # RAID B2 — plan mode mirrors ask, but the `plan_*` PlanForge
                # tools are allowed through (they write plan artifacts, never
                # prose); everything else non-R feeds the plan-mode error.
                if permission_mode in ("ask", "plan"):
                    _ask_td = (cat_index if discovery else plain_index).get(c["name"])
                    _ask_tier = tool_tier(_ask_td) if _ask_td is not None else "R"
                    if _ask_tier != "R" and not (
                        permission_mode == "plan" and _is_plan_tool(c["name"])
                    ):
                        if permission_mode == "plan":
                            ask_err = (
                                f"plan mode — research and planning only; "
                                f"{c['name']} is a tier-{_ask_tier} write tool and "
                                "cannot run here. Build the plan with the plan_* "
                                "tools; switch to Write mode to draft."
                            )
                        else:
                            ask_err = (
                                f"read-only mode — {c['name']} is a tier-{_ask_tier} "
                                "write tool and cannot run in Ask mode. Switch to "
                                "Write mode to run it, or answer from reads only."
                            )
                        working.append({
                            "role": "tool", "tool_call_id": c["id"],
                            "content": tool_result_content({"error": ask_err}),
                        })
                        yield {"tool_call": {
                            "id": c["id"], "iteration": iteration, "tool": c["name"],
                            "args": args_obj, "ok": False,
                            "result": None, "error": ask_err,
                        }}
                        continue

                # MCP-fanout C-TOOL: read the tool's tier (R|A|W|S) from the
                # discovery catalog (main turn) or the plain-defs index (a subagent
                # runs off `tools=scoped`, non-discovery). Legacy/untiered tools
                # default to R (inert) — they never auto-emit an activity/undo and
                # never count as a write. NOTE: this MUST read the real tier in the
                # plain path too — write-delegation (a write-mode subagent) relies on
                # it so the Tier-A allowlist gate below actually fires; hardcoding "R"
                # here would let a subagent auto-commit ANY Tier-A tool unchecked.
                tier = tool_tier((cat_index if discovery else plain_index).get(c["name"], {}))

                # H7 — Tier-A volume caps: STOP auto-applying and escalate to ONE
                # batch confirm_action (the enforceable injection-damage bound) when
                # EITHER ceiling is reached. We suspend on a synthetic confirm_action
                # so the user gates the rest — exactly the H2 batch card.
                #   (1) per-op cap   — beyond TIER_A_SAME_OP_CAP auto-writes of the
                #       SAME op in a turn (bounds a single runaway op).
                #   (2) aggregate cap — beyond TIER_A_AGGREGATE_CAP auto-writes
                #       across ALL ops in a turn (bounds an alternating-op turn that
                #       never trips any single per-op cap; residual was
                #       5×distinct_ops without this).
                if tier == "A":
                    per_op_hit = (
                        tier_a_op_counts.get(c["name"], 0) >= TIER_A_SAME_OP_CAP
                    )
                    aggregate_hit = (
                        sum(tier_a_op_counts.values()) >= TIER_A_AGGREGATE_CAP
                    )
                    if per_op_hit or aggregate_hit:
                        if aggregate_hit and not per_op_hit:
                            reason = (
                                f"Auto-apply ceiling reached: already ran "
                                f"{TIER_A_AGGREGATE_CAP} auto-writes this turn. "
                                f"Confirm to continue."
                            )
                        else:
                            reason = (
                                f"Auto-apply cap reached: already ran {c['name']} "
                                f"{TIER_A_SAME_OP_CAP}× this turn. Confirm to continue."
                            )
                        # A headless sub-run can't raise the batch confirm card — so
                        # instead of a silently-swallowed suspend, return the cap as a
                        # result.error the sub-model can stop on (no-silent-no-op).
                        # The writes already applied are all allowlisted + tenancy-safe;
                        # the cap simply halts further auto-writes (the safe direction).
                        if subagent_depth > 0:
                            _cap_err = (
                                f"{reason} A subagent cannot request batch confirmation — "
                                "stopping further auto-writes. Summarize what was done."
                            )
                            working.append({
                                "role": "tool", "tool_call_id": c["id"],
                                "content": tool_result_content({"error": _cap_err}),
                            })
                            yield {"tool_call": {
                                "id": c["id"], "iteration": iteration, "tool": c["name"],
                                "args": args_obj, "ok": False, "result": None, "error": _cap_err,
                            }}
                            continue
                        suspended_call = {
                            "id": c["id"],
                            "name": "confirm_action",
                            "args": {
                                "confirm_token": "",
                                "descriptor": f"{c['name']}.batch",
                                "title": f"Apply {c['name']} again?",
                                "domain": (c["name"].split("_", 1)[0] or "book"),
                                "items": [args_obj],
                                "_reason": reason,
                            },
                        }
                        break

                # P4 REG-P4-03 — pre_tool_call hook. A declarative `deny` hook blocks
                # this call HERE (before the MCP transport) with a surfaced result.error
                # the model can adapt to — same short-circuit shape as the planner cap
                # below. Declarative only: no code runs, the hook just decides.
                if hooks:
                    from app.services.hook_engine import decide_pre_tool_call

                    _hk_action, _hk_msg = decide_pre_tool_call(hooks, c["name"])
                    if _hk_action == "deny":
                        _denial = {"error": "blocked_by_hook", "message": _hk_msg}
                        working.append({
                            "role": "tool", "tool_call_id": c["id"],
                            "content": tool_result_content(_denial),
                        })
                        yield {"tool_call": {
                            "id": c["id"], "iteration": iteration, "tool": c["name"],
                            "args": args_obj, "ok": False, "result": None, "error": _hk_msg,
                        }}
                        continue
                    if _hk_action == "require_approval":
                        # A subagent runs headless — it cannot surface an approval
                        # suspend (no client to answer it). So a require_approval hook
                        # inside a sub-run does NOT run the tool; it returns a
                        # result.error the sub-model can adapt to (no silent no-op).
                        if subagent_depth > 0:
                            _hk_sub_err = (
                                f"'{c['name']}' requires human approval (hook), which a "
                                "subagent cannot request — it was NOT run. Skip it or use "
                                "a tool that does not require approval."
                            )
                            working.append({
                                "role": "tool", "tool_call_id": c["id"],
                                "content": tool_result_content({"error": _hk_sub_err}),
                            })
                            yield {"tool_call": {
                                "id": c["id"], "iteration": iteration, "tool": c["name"],
                                "args": args_obj, "ok": False, "result": None, "error": _hk_sub_err,
                            }}
                            continue
                        # Force the human approval gate for this call regardless of
                        # tier/mode/allowlist — reuse the same tool_approval suspend
                        # machinery as the C2 write-mode gate below (no new transport).
                        suspended_call = {
                            "id": c["id"],
                            "name": c["name"],
                            "args": {
                                "kind": "tool_approval",
                                "tool": c["name"],
                                "args": args_obj,
                                "tier": tier,
                            },
                        }
                        break

                # #18 — planner hard-stop. The planner (glossary_plan) is a heavy ~39s
                # model call with NO ReAct loop of its own; a weak model loops it in a
                # self-recheck cycle. The FIRST call this turn runs; a 2nd+ call is
                # short-circuited HERE — before the MCP transport — with a tool result
                # that steers the model to present/confirm the plan it already has, rather
                # than burning another planner run. (Kiro-style: logic controls progress.)
                if c["name"] in PLANNER_TOOLS:
                    if planner_call_counts.get(c["name"], 0) >= PLANNER_CALLS_PER_TURN_CAP:
                        guidance = {
                            "error": "planner_already_ran",
                            "message": (
                                f"{c['name']} already ran this turn — do NOT call it again. "
                                "Present the plan you already produced for the user to confirm "
                                "(pass its confirm_token to glossary_confirm_action), or use "
                                "glossary_propose_batch if you already know the exact ops. "
                                "Re-planning in the same turn is disabled to stop a self-recheck loop."
                            ),
                        }
                        working.append({
                            "role": "tool", "tool_call_id": c["id"],
                            "content": tool_result_content(guidance),
                        })
                        yield {"tool_call": {
                            "id": c["id"], "iteration": iteration, "tool": c["name"],
                            "args": args_obj, "ok": False,
                            "result": None, "error": guidance["message"],
                        }}
                        continue
                    planner_call_counts[c["name"]] = planner_call_counts.get(c["name"], 0) + 1

                # D-PLAN-PLANNER-DEFAULT-FE phase 2 + #19: who picks the planner model is a
                # USER/config decision, NEVER the agent's. The glossary_plan tool exposes a
                # model_ref arg, so a weak model can fill it and silently override the user's
                # session pin AND their Settings 'planner' default (glossary only resolves the
                # default when in.ModelRef is empty). chat-service is therefore AUTHORITATIVE:
                # a session pin always wins; otherwise the model's guess is STRIPPED so the
                # downstream resolver applies the per-user Settings default → fallback.
                # D-PLANFORGE-DEFAULT-MODEL — every PlanForge tool with a model_ref arg now
                # mirrors glossary's own fallback (GET /internal/planner-model via
                # composition-service's resolve_planner_model / _resolve_model_ref), so
                # stripping here is safe for all of them: model_ref is optional at every one
                # of these tool schemas now, never a hard-required arg.
                if c["name"] in (
                    "glossary_plan", "plan_propose_spec", "plan_interpret_feedback",
                    "plan_apply_revision", "plan_handoff_autofix", "plan_compile",
                ) and isinstance(args_obj, dict):
                    if planner_model_ref:
                        args_obj["model_ref"] = planner_model_ref
                    else:
                        args_obj.pop("model_ref", None)

                # RAID C2 (DR-C2 §4) — Write-mode prompt-once approval gate: a
                # Tier-A server tool NOT on the user's allowlist suspends the run
                # with a `tool_approval` pending card (reusing the frontend-tool
                # suspend/resume machinery — no new transport). The resume path
                # executes on approve (+persists the row on "always"), or feeds
                # a "denied by user" tool result. An allowlist READ failure fails
                # OPEN (a DB blip must not brick tool calling); only the specific
                # un-allowlisted call gates. Tier-S/W propose/confirm + Tier-A
                # undo are untouched — approval is additive. RAID B2: the gate is
                # write-mode-ONLY by design — in plan mode a Tier-A `plan_*` tool
                # runs without the approval prompt (plan artifacts are reversible
                # plan_runs rows; non-plan_* writes never reach here — the
                # defense-in-depth block above already rejected them).
                # S02 — intercept a call still missing REQUIRED args (post context-id injection)
                # BEFORE it dispatches (reads → a 400) or parks an EMPTY write on the approval card
                # (writes). Give SPECIFIC, actionable guidance naming the missing args; after the
                # per-turn cap, tell the model to stop. The measured mid-tier failure: gemma called
                # glossary_propose_entities with no `entities` and glossary_search with no `query`.
                # D-FJ-7 — repair `["vi"]` → `"vi"` where the schema declares a SCALAR, before the
                # missing-arg check and before dispatch. The value the model chose was already
                # right; only its container was wrong, and a refusal the caller does not recover
                # from ends the journey just as dead as a wrong value would.
                _tool_def_for_args = cat_index.get(c["name"]) or plain_index.get(c["name"])
                _unwrapped = _unwrap_single_element_scalar_args(args_obj, _tool_def_for_args)
                if _unwrapped:
                    logger.info(
                        "unwrapped single-element list arg(s) %s for %s (session=%s) — the schema "
                        "declares them scalar", _unwrapped, c["name"], session_id,
                    )
                # Sibling repair: a JSON NUMBER where the schema declares string-only. Same class,
                # same discipline — see _stringify_int_args_declared_string.
                _deprefixed = _strip_field_name_prefix_from_ids(args_obj, _tool_def_for_args)
                if _deprefixed:
                    logger.info(
                        "stripped a field-name prefix from id arg(s) %s for %s (session=%s)",
                        _deprefixed, c["name"], session_id,
                    )
                _objs = _unwrap_object_items_for_string_array(args_obj, _tool_def_for_args)
                if _objs:
                    logger.info(
                        "unwrapped object-item arg(s) %s for %s (session=%s) — the schema declares "
                        "an array of strings", _objs, c["name"], session_id,
                    )
                _stringified = _stringify_int_args_declared_string(args_obj, _tool_def_for_args)
                if _stringified:
                    logger.info(
                        "stringified integer arg(s) %s for %s (session=%s) — the schema declares "
                        "them string-only", _stringified, c["name"], session_id,
                    )
                # D-FJ-11 — an id the contract says the RUNTIME owes, filled in with a fabricated
                # value. Treated exactly like the missing case, because it IS the missing case with
                # a placeholder written over it: the model does not have this value either way, and
                # arguing about the format only invites a better-formatted invention.
                _invented_ids: list[str] = []
                if _tool_def_for_args:
                    try:
                        from app.agentruntime.toolcontract import resolve_contract as _rc
                        _inv_block, _ = _rc(_tool_def_for_args, _tool_contract_registry())
                        _invented_ids = _invented_supplier_ids(
                            args_obj, _inv_block,
                            ((_tool_def_for_args or {}).get("function", {})
                             .get("parameters", {}) or {}).get("properties"),
                        )
                    except Exception:
                        _invented_ids = []
                    # 🔴 KEEP THE VALUE BEFORE DROPPING IT. Measured 2026-08-23 on
                    # composition_motif_link_edit: the model resolved both endpoints to NAMES
                    # ("Throwaway Loop Alpha Kutomere"), the whitespace arm correctly judged them
                    # not-identifiers and dropped them, and the refusal then said the arguments
                    # were MISSING. The model was never told WHICH VALUE it had passed, so its
                    # follow-up `composition_motif_search` went out with blank arguments — twice —
                    # and the turn died. It had the name and we deleted it before telling it
                    # anything. See _name_like_dropped_ids for what is added back to the sentence.
                    _invented_vals = {n: args_obj.get(n) for n in _invented_ids}
                    if _invented_ids:
                        for _nm in _invented_ids:
                            args_obj.pop(_nm, None)
                        # 🔴 THE OLD LINE NAMED ONE ARM FOR ALL SIX. It said "the contract declares
                        # them context/plan-supplied" no matter which arm fired — placeholder token,
                        # SCREAMING_SNAKE, whitespace-is-a-name, declared-uuid, or the contract arm.
                        # Today it sent me hunting a contract misdeclaration that does not exist, on
                        # a drop the whitespace arm made. A log line that hard-codes one explanation
                        # for a multi-arm decision is a misattributed cause with a timestamp on it.
                        logger.info(
                            "dropped non-identifier value(s) %s from %s (session=%s) — not an id "
                            "this platform issues (name, placeholder, or runtime-owed id the model "
                            "filled in); values=%s",
                            _invented_ids, c["name"], session_id,
                            {k: (v if isinstance(v, str) and len(v) <= 80 else str(v)[:80])
                             for k, v in _invented_vals.items()},
                        )
                # ── THE SAME SENTENCE FOR A DOCUMENT ─────────────────────────────────────
                # D-THE-DOCUMENT-HANDED-TO-AN-EXTRACT-TOOL-IS-A-MESSAGE-ABOUT-HAVING-NO-DOCUMENT.
                # An id the model invents and a document the model invents are the same failure
                # one argument-kind apart, so they take the same path: drop the value, report
                # the argument missing, and say what was actually wrong. Independent of the
                # contract lookup above — a hollow document is wrong for every supplier, and
                # `_tool_def_for_args` being absent must not silence it.
                # ── AND THE SAME SENTENCE FOR THE AUTHOR'S MONEY ─────────────────────────
                # D-THE-MODEL-FABRICATES-A-MONEY-VALUE-ON-A-SPECULATIVE-FIRST-CALL. An id the
                # runtime owes, a document the author owns, and a budget the author decides are
                # the same failure one argument-kind apart. `messages` carries the author's own
                # turns, so no plumbing is added to ask what they said.
                _money_args = invented_money_args(args_obj, messages)
                _money_vals = {n: args_obj.get(n) for n in _money_args}
                if _money_args:
                    for _nm in _money_args:
                        args_obj.pop(_nm, None)
                    logger.info(
                        "dropped invented spend ceiling(s) %s from %s (session=%s) — the author "
                        "never mentioned money; values=%s",
                        _money_args, c["name"], session_id, _money_vals,
                    )
                _hollow_args = _hollow_document_args(args_obj)
                _hollow_vals = {n: args_obj.get(n) for n in _hollow_args}
                if _hollow_args:
                    for _nm in _hollow_args:
                        args_obj.pop(_nm, None)
                    logger.info(
                        "dropped hollow document value(s) %s from %s (session=%s) — a note "
                        "about having no content is not content; values=%s",
                        _hollow_args, c["name"], session_id,
                        {k: (v if isinstance(v, str) and len(v) <= 120 else str(v)[:120])
                         for k, v in _hollow_vals.items()},
                    )
                _missing_args = _missing_required_names(args_obj, _tool_def_for_args)
                if _invented_ids:
                    _missing_args = sorted(set(_missing_args) | set(_invented_ids))
                if _hollow_args:
                    _missing_args = sorted(set(_missing_args) | set(_hollow_args))
                if _money_args:
                    _missing_args = sorted(set(_missing_args) | set(_money_args))
                if _missing_args:
                    blank_tool_args_streak += 1
                    if blank_tool_args_streak >= BLANK_TOOL_ARGS_CAP:
                        _ma_msg = (
                            f"'{c['name']}' keeps being called with missing/blank required "
                            "arguments this turn — STOP. Tell the user you couldn't complete this "
                            "rather than retrying with empty arguments."
                        )
                    else:
                        _ma_msg = None  # built below, once the declared contract is resolved
                    # ── CP-5.4 · WHO OWES THIS ARGUMENT ──────────────────────────────────────
                    # 🔴 One sentence was covering two OPPOSITE situations. Measured over 266
                    # missing-argument failures / 87 sessions: the largest single case is
                    # `book_read` missing `book_id` — **78 calls across 46 sessions** — and
                    # `book_id` is a CONTEXT value the runtime fills from the ambient book and
                    # simply does not have outside a book studio. Telling the model "you are
                    # missing a required argument" reads as *you forgot something* when the truth
                    # is *I owe you this and do not have it*, and the model cannot act on it.
                    # `body`, `items` and `base_version` ARE model-supplied, and for those the
                    # message above is already right.
                    #
                    # The supplier is read from the tool's DECLARED contract (5.1's
                    # `argument_supplier` member), so this is the contract doing work rather than
                    # a table of tool names kept here. All three arms — owed, UNDECLARED and
                    # model-supplied — live in `_missing_args_message` so the undeclared case
                    # cannot silently inherit the model-supplied sentence again.
                    if _ma_msg is None:
                        _c_block = {}
                        try:
                            from app.agentruntime.toolcontract import resolve_contract
                            _c_block, _ = resolve_contract(
                                cat_index.get(c["name"]) or plain_index.get(c["name"]) or {},
                                _tool_contract_registry())
                        except Exception:
                            _c_block = {}
                        # Bound to a local rather than repeating the lookup: an anchored
                        # falsifier counts occurrences of that expression, and a second copy
                        # made it stale. One lookup, one anchor.
                        _ma_props = (
                            (_c_def.get("function", {}).get("parameters", {}) or {})
                            .get("properties") or {}
                        ) if isinstance(_c_def := (
                            cat_index.get(c["name"]) or plain_index.get(c["name"]) or {}
                        ), dict) else {}
                        # `working` carries THIS turn's tool results, and nothing else does —
                        # they are appended to it live and are not persisted until the turn ends.
                        # But a PRIOR turn's result is not in `working` either: chat_messages
                        # holds no role='tool' rows, so rehydration returns user/assistant text
                        # only. The recorded instance handed the id over in turn 1 and dropped it
                        # in turn 2, so the server's own record is the half that carries it —
                        # `tool_call_history` exists for exactly this question, "what have I
                        # already done?", answered from the SERVER's memory, not the model's.
                        # Only the runtime-owed args are looked up: this is a refusal path, but a
                        # per-argument query for `body` or `items` would be pure waste.
                        _ma_prior: dict[str, list[str]] = {}
                        try:
                            from app.db.tool_call_history import ids_returned_under_key
                            for _oa in _owed_args(_c_block, _missing_args):
                                if _vals := await ids_returned_under_key(
                                        get_pool(), str(session_id), _oa):
                                    _ma_prior[_oa] = _vals
                        except Exception:  # noqa: BLE001 — a refusal's wording never takes a turn down
                            logger.warning(
                                "prior-turn id lookup failed for %s (session=%s)",
                                c["name"], session_id, exc_info=True,
                            )
                            _ma_prior = {}
                        _ma_msg = _missing_args_message(
                            c["name"], _missing_args, _c_block, _ma_props,
                            history=working, also_returned=_ma_prior)
                    # ── THE THIRD STATE: YOU PASSED THE WRONG KIND OF THING ──────────────────
                    # CP-5.4 separated "you forgot something" from "I owe you this". A dropped
                    # NAME is neither: the model did supply a value and it was the wrong KIND, and
                    # calling that "missing" is the one description guaranteed not to help. The
                    # name is also the exact query string the recovery search needs, so handing it
                    # back is what makes the refusal actionable rather than merely accurate.
                    # D-THE-ID-REPAIR-SENTENCE-NAMES-A-TOOL-THAT-IS-NOT-THERE — resolve the
                    # referent HERE, where the catalogue and the registry are both in hand, rather
                    # than gesturing at "the tool named above" and hoping something named one.
                    # The emitter is preferred; naming it also ARMS it a few lines below, since
                    # that path keys off catalogue names in this very text.
                    _nl_emitter = ""
                    try:
                        from app.agentruntime.toolcontract import declared_emitter as _de
                        _nl_reg = _tool_contract_registry()
                        _nl_emitter = next(
                            (e for a in sorted(_invented_vals or {})
                             if (e := _de(_nl_reg, c["name"], a))), "")
                    except Exception:  # noqa: BLE001 — a lookup must never take the turn down
                        _nl_emitter = ""
                    # Does anything already in the message name a real tool? If not, the closing
                    # instruction has nowhere to point and is dropped instead of dangling.
                    _nl_referent = bool(_tools_named_in_refusal(
                        _ma_msg or "", cat_index or {}, set(), exclude=c["name"]))
                    _named = _name_like_dropped_ids(
                        _invented_vals, emitter=_nl_emitter, referent_exists=_nl_referent)
                    if _named:
                        _ma_msg = (_ma_msg or "") + " " + _named
                    # The document arm's own sentence — see `_hollow_document_note`. Appended
                    # here for the same reason the name arm is: the generic missing-argument
                    # text would call it forgotten, and it was not forgotten.
                    _hollow_note = _hollow_document_note(_hollow_vals)
                    if _hollow_note:
                        _ma_msg = (_ma_msg or "") + " " + _hollow_note
                    _money_note = _money_arg_note(_money_vals)
                    if _money_note:
                        _ma_msg = (_ma_msg or "") + " " + _money_note
                    # ── D-REFUSAL-NAMES-A-TOOL-THE-TURN-CANNOT-SEE ───────────────────────────
                    # This refusal SAYS "call world_map_list first and match it to get the id".
                    # Until now it armed nothing: `_tools_named_in_refusal` runs on the dispatch
                    # result far below, and this arm `continue`s before reaching it. So the largest
                    # refusal class on the platform issued an instruction naming a tool that was
                    # not on the turn, and the model did the only thing left — retried the same
                    # failing call, then promised the author it would go and look.
                    #
                    # MEASURED over 35 live runs (7 tools, K=5): supplier ADVERTISED and not called
                    # happened ZERO times, supplier absent and not called 27 times, agreement 35/35.
                    # The model walks the chain exactly when it can see the supplier.
                    if discovery:
                        _ma_recovery = _tools_named_in_refusal(
                            _ma_msg or "", cat_index, active_tool_names,
                            exclude=c["name"])
                        if _arm_tools(
                            _ma_recovery, active_tool_names=active_tool_names,
                            activation_state=activation_state,
                            discovery_catalog=discovery_catalog,
                            context_length=context_length,
                        ):
                            _ma_msg = (_ma_msg or "") + (
                                "\n\n[SYSTEM] " + ", ".join(_ma_recovery) + " "
                                + ("is" if len(_ma_recovery) == 1 else "are")
                                + " now available to you on this turn — no tool_load needed. Call "
                                + ("it" if len(_ma_recovery) == 1 else "them")
                                + " to get the value, then retry. Do not repeat the call that just "
                                "failed without changing something."
                            )
                            logger.info(
                                "armed recovery tool(s) %s named in %s's missing-argument refusal "
                                "(session=%s)", _ma_recovery, c["name"], session_id,
                            )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"error": "missing_required_args", "message": _ma_msg}),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": _ma_msg,
                    }}
                    continue

                # ── Track D S-SPEND + RAID C2 (DR-C2 §4) — combined consent gate ──────
                # Two ORTHOGONAL, separately-persisted consents can gate ONE call:
                #   • SPEND  (kind='spend')    — the tool is PAID (_meta.paid): CALLING
                #     it spends real money (external paid search / an LLM research loop).
                #     Orthogonal to tier (a paid READ is tier R) and MODE-INDEPENDENT
                #     (ask restricts mutation, not spend) — so this fires for a Tier-R
                #     paid tool AND in ask mode, where neither the ask-tier filter above
                #     nor the mutation gate reaches. A read failure fails CLOSED (still
                #     prompt): spend is IRREVERSIBLE, so a DB blip must never silently
                #     spend money — the deliberate opposite of the mutation fail-OPEN.
                #   • MUTATE (kind='mutation') — a Tier-A tool auto-commits an undoable
                #     write; in WRITE mode an un-allowlisted one prompts once. A read
                #     failure fails OPEN (a reversible write must not brick tool calling).
                # The resume path executes the approved tool DIRECTLY (no loop re-entry),
                # so ONE call has exactly ONE suspend point: a paid Tier-A tool therefore
                # raises ONE card enumerating BOTH required consents (strictly more
                # informative than two prompts) and, on always-allow, persists a SEPARATE
                # allowlist row per kind — a "may write" grant is never a "may spend" grant.
                # Track C WS-3 — this is now ONLY the PROMPT arm. The standing REFUSAL is
                # evaluated far above (before the frontend-tool suspend, the H7 cap and the
                # hook arm), because a deny must hold everywhere a tool can run, whereas a
                # prompt is legitimately scoped to tier + mode. Each check yields
                # 'allow' (standing grant — proceed silently) or None/anything else
                # (undecided — raise the card); 'deny' can no longer reach here.
                _required_kinds: list[str] = []
                if decision_check is not None:
                    _gate_def = (cat_index if discovery else plain_index).get(c["name"], {})
                    if tool_paid(_gate_def):
                        try:
                            _spend_d = await decision_check(c["name"], "spend")
                        except Exception:
                            logger.warning(
                                "spend-approval read failed for %s — failing CLOSED (prompt)",
                                c["name"], exc_info=True,
                            )
                            _spend_d = None  # irreversible spend → prompt on doubt
                        if _spend_d != "allow":
                            _required_kinds.append("spend")
                    if tier == "A" and permission_mode == "write":
                        try:
                            _mut_d = await decision_check(c["name"])
                        except Exception:
                            # DR-C2 originally failed OPEN here (a DB blip must not brick
                            # tool calling). That degrade is no longer safe as written: the
                            # SAME read now also carries the user's standing refusal, so
                            # "assume allow on error" would let a transient DB fault EXECUTE
                            # a tool the user permanently denied. An unreadable decision is
                            # UNKNOWN — and unknown must resolve to ASK, never to run.
                            # Prompting still honors the original intent (a card is raised,
                            # tool calling is not bricked); it merely refuses to invent a
                            # grant nobody gave.
                            logger.warning(
                                "tool-approval allowlist read failed for %s — degrading to a prompt",
                                c["name"], exc_info=True,
                            )
                            _mut_d = None
                        if _mut_d != "allow":
                            _required_kinds.append("mutation")

                if _required_kinds:
                    # Write-delegation (D-REG-P5-SUBAGENT-WRITE-DELEGATION): a headless
                    # sub-run (subagent_depth>0) cannot raise an approval card, so it must
                    # NOT spend money or auto-commit an un-approved write — it returns a
                    # result.error the sub-model can adapt to (no silent no-op) instead of
                    # suspending (which the parent would otherwise swallow). Tenancy stays
                    # enforced at the tool layer; the sub-run is bounded by its tool_scope.
                    if subagent_depth > 0:
                        _kinds_txt = " and ".join(_required_kinds)
                        _sub_appr_err = (
                            f"'{c['name']}' is not pre-approved for {_kinds_txt}, and a "
                            "subagent cannot request approval — it was NOT run. Delegate "
                            "only tools the user has already allowlisted, or have the user "
                            f"approve '{c['name']}' first."
                        )
                        working.append({
                            "role": "tool", "tool_call_id": c["id"],
                            "content": tool_result_content({"error": _sub_appr_err}),
                        })
                        yield {"tool_call": {
                            "id": c["id"], "iteration": iteration, "tool": c["name"],
                            "args": args_obj, "ok": False, "result": None, "error": _sub_appr_err,
                        }}
                        continue
                    _card_args: dict = {
                        "kind": "tool_approval",
                        "tool": c["name"],
                        "args": args_obj,
                        "tier": tier,
                    }
                    if "spend" in _required_kinds:
                        # S-SPEND wire signal so the FE can render "this costs money" vs
                        # "this modifies data". Added ONLY when money is at stake, so a
                        # pure-mutation card stays byte-identical to the legacy DR-C2 shape.
                        # The existing card keys on kind=="tool_approval" (still renders);
                        # a spend-aware FE reads `spend` / the closed-set `approval_kinds`
                        # ({"spend","mutation"}). The resume path reads `approval_kinds` to
                        # know which allowlist row(s) to persist on always-allow.
                        _card_args["spend"] = True
                        _card_args["approval_kinds"] = list(_required_kinds)
                    suspended_call = {
                        "id": c["id"],
                        "name": c["name"],
                        "args": _card_args,
                    }
                    break

                # ── Track C Phase 2 — the REPEATED-READ breaker ────────────────────────
                # A read the model has ALREADY made, with the SAME arguments, that ALREADY
                # succeeded. Its answer is sitting in the context right now. Re-running it
                # cannot tell the model anything it does not have — it can only burn a pass
                # and push the earlier copy of the same answer further out of the window.
                #
                # Measured, live: 24 identical `glossary_list_system_standards` calls in one
                # S01 run, whose result is 44,000 chars (~11k tokens) EACH. The model could
                # not see what it had already fetched, so it fetched it again, and the very
                # act of fetching it crowded out the fetch before it. Zero artifacts built.
                # H7 bounds runaway WRITES; nothing bounded a runaway READ, on the theory
                # that a read is harmless. A read that eats a third of the context window is
                # not harmless.
                # READS ONLY. A repeated WRITE is not a loop — six `book_create` calls with
                # the same title create six books. Only a read is idempotent enough that
                # asking twice is provably pointless, and only a Tier-R tool is a read.
                _read_key = (
                    f"{c['name']}::{json.dumps(args_obj, sort_keys=True, default=str)}"
                    if tier == "R" else None
                )
                # Idempotent-no-op WRITE breaker — a Tier-A write's identity key (same
                # (tool, args)); populated post-execution only when the result reported
                # `created: False`. Computed here so both the short-circuit below and the
                # record step later share one key. (Distinct from _read_key: a write is
                # never a read, so the two never collide.)
                _noop_write_key = (
                    f"{c['name']}::{json.dumps(args_obj, sort_keys=True, default=str)}"
                    if tier == "A" else None
                )
                # Repeated-FAILURE breaker — ALL tiers (reads loop too: book_get_chapter ×19).
                # Find this tool's most-repeated ERROR this turn; if it has recurred >= cap times,
                # further calls to this tool are the loop (the model keeps hitting the same wall
                # with varied args). Defer a missing/blank-required-args error to the dedicated
                # blank-args breaker below (tailored message + own cap) — division of labour.
                _tool_fails = fail_by_tool_error.get(c["name"], {})
                _dom_err, _dom_n = "", 0
                for _e, _n in _tool_fails.items():
                    if _n > _dom_n:
                        _dom_err, _dom_n = _e, _n
                if _dom_n >= REPEATED_FAILURE_CAP and _MISSING_REQUIRED_ARGS_MARKER not in _dom_err:
                    _fail_steer = (
                        f"'{c['name']}' has already FAILED {_dom_n} times this turn with the same "
                        f"error: {_dom_err} — retrying it (even with different arguments) keeps "
                        "hitting the same wall. STOP calling it. Do EXACTLY what that error says "
                        "to fix it (e.g. if it tells you to look up an id first, call THAT tool "
                        "now), use a DIFFERENT tool, or tell the user plainly what is blocking you."
                    )
                    logger.info(
                        "repeated-failure breaker: %s failed %d× with the same error this turn "
                        "— short-circuited + de-advertised", c["name"], _dom_n,
                    )
                    # Take it OFF the wire next pass so the model stops re-emitting it.
                    failure_suppress.add(c["name"])
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"error": _fail_steer}),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": _fail_steer,
                    }}
                    continue
                if (
                    _noop_write_key is not None
                    and noop_write_counts.get(_noop_write_key, 0) >= IDEMPOTENT_NOOP_WRITE_CAP
                ):
                    _noop_err = (
                        f"'{c['name']}' already ran this turn with these exact arguments and "
                        "reported created=false — the resource ALREADY EXISTS and its id is in "
                        "that earlier result, above. Calling it again creates nothing and changes "
                        f"nothing. STOP calling '{c['name']}'; take that existing id and move on "
                        "to the NEXT step."
                    )
                    logger.info(
                        "idempotent-no-op-write breaker: %s returned created=false already this "
                        "turn — short-circuited the repeat", c["name"],
                    )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"error": _noop_err}),
                    })
                    yield {"tool_call": instrument.stamp_refused({
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": _noop_err,
                    }, "idempotent_noop_write")}
                    continue
                _prior = read_call_results.get(_read_key) if _read_key is not None else None
                if _prior is not None and _prior[1] >= REPEAT_READ_CAP:
                    # Count the BLOCK, not the dispatch — see `repeat_block_counts`. `_prior[1]`
                    # is frozen at the cap for every blocked call, so the attempt number has to
                    # come from here or the message repeats a number that stopped being true.
                    _blocks = repeat_block_counts[c["name"]] = (
                        repeat_block_counts.get(c["name"], 0) + 1
                    )
                    _attempts = _prior[1] + _blocks
                    _deadvertise = _blocks >= REPEAT_READ_DEADVERTISE_CAP
                    _repeat_err = (
                        f"You have already called '{c['name']}' with these exact arguments "
                        f"{_attempts} times this turn and it returned the IDENTICAL result "
                        "every time — that result is already above, in this conversation. "
                        "Calling it again cannot tell you anything new. STOP calling it. Read "
                        "the result you already have, and take the NEXT step."
                    )
                    if _deadvertise:
                        # Off the wire for the rest of the turn, so it cannot be re-emitted at
                        # all. Said plainly, because a model that finds a tool missing without
                        # being told tends to hunt for it instead of moving on.
                        repeat_read_suppress.add(c["name"])
                        _repeat_err += (
                            f" '{c['name']}' is now disabled for the rest of this turn — the "
                            "answer you have is the answer. Use a DIFFERENT tool, or reply to "
                            "the user with what you already know."
                        )
                    logger.info(
                        "repeated-read breaker: %s returned an unchanged result %d× — "
                        "short-circuited (%d blocked repeat(s)%s)",
                        c["name"], _prior[1], _blocks,
                        "; de-advertised" if _deadvertise else "",
                    )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"error": _repeat_err}),
                    })
                    yield {"tool_call": instrument.stamp_refused({
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": _repeat_err,
                        # §3 — the COST is already gone (this short-circuits before dispatch).
                        # The SIGNAL stays: the repeat count keeps rising and the breaker keeps
                        # escalating. What changes is that it stops being typed as a TOOL failure.
                        # That sentence was aspirational until now — the count was frozen at the
                        # cap and nothing escalated, so both halves are recorded here instead.
                        "repeat_count": _attempts,
                        "repeat_blocks": _blocks,
                        "deadvertised": _deadvertise,
                    }, "repeated_read")}
                    continue

                # D-BLANK-TOOL-ARGS-LOOP — same cap as the find_tools breaker
                # above, generalized to ANY backend tool: once the turn has
                # already hit BLANK_TOOL_ARGS_CAP blank/invalid-args failures
                # (of EITHER shape), a further one is short-circuited BEFORE
                # the MCP round trip, not just noted after another failure.
                # S02 refinement — only short-circuit a call we CANNOT confirm is well-formed:
                # a call still missing required args, OR one whose tool has no schema in the
                # catalog to check against (unknown → keep the original safe cap behavior). A
                # KNOWN, well-formed call must never be collateral-blocked by a DIFFERENT tool's
                # malformed spam (the case: glossary_search-without-query streak once blocked a
                # valid ontology_read). Known+missing-required is already intercepted with specific
                # guidance above, so this cap now mainly backstops unknown-schema blank spam.
                _cap_tool_def = cat_index.get(c["name"]) or plain_index.get(c["name"])
                if blank_tool_args_streak >= BLANK_TOOL_ARGS_CAP and (
                    _cap_tool_def is None or _missing_required_args(args_obj, _cap_tool_def)
                ):
                    guidance = {
                        "error": "blank_tool_args_capped",
                        "message": (
                            f"'{c['name']}' has failed with missing/blank required "
                            f"arguments {blank_tool_args_streak + 1} times this turn "
                            "(across one or more tools) — STOP retrying tool calls "
                            "with empty arguments. Tell the user directly that tool "
                            "calling is not working right now instead of retrying."
                        ),
                    }
                    logger.warning(
                        "D-BLANK-TOOL-ARGS-LOOP: capped session=%s after %d "
                        "consecutive blank/invalid-args tool calls this turn "
                        "(model_ref=%s, tool=%s)",
                        session_id, blank_tool_args_streak + 1, model_ref, c["name"],
                    )
                    if trace is not None:
                        trace.add(
                            "compile", "T6", "tools",
                            f"blank_tool_args_capped:{c['name']}",
                            is_error=True,
                        )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(guidance),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False,
                        "result": None, "error": guidance["message"],
                    }}
                    continue

                # ── UNRESOLVABLE-TOOL GUARD ──────────────────────────────────────────
                # Two distinct failures used to look identical here — the call went out,
                # came back an error, and the model was left to guess why:
                #
                #   (a) the tool EXISTS but is not on this turn's surface. The model reached
                #       for it because something TOLD it to — a rail step, or another tool's
                #       own error text ("create the categories first (glossary_adopt_standards
                #       …)"). Nothing ever told it the tool was merely unloaded, so it retried
                #       forever. Measured live: 40,597 characters of one paragraph repeated,
                #       until the user hit Stop.
                #   (b) the tool does NOT exist anywhere — a hallucinated name. Retrying that
                #       can never succeed, so the only useful reply names real neighbours and
                #       tells the model its own reasoning is what needs re-checking.
                #
                # Both are answered HERE, in code, rather than hoped for in a prompt: the
                # existing guidance lives in a skill prompt and only covers `plan_*`,
                # `composition_*` and `book_*` — `glossary_*` (the live wedge) is not in that
                # list, and a mid-tier model ignores prose guidance under pressure anyway.
                if discovery and cat_index and c["name"] not in cat_index:
                    import difflib

                    from app.services.tool_discovery import INTENT_GATED_SETUP_TOOLS
                    # A name absent from the catalog is NOT automatically invented. The
                    # capability floor (N5a-FULL) deliberately REMOVES some real tools from the
                    # turn catalog, so telling the model it hallucinated one of those would be a
                    # false accusation — and would send it hunting for a different tool when the
                    # one it named was right all along. Separate the two cases honestly.
                    _withheld = c["name"] in INTENT_GATED_SETUP_TOOLS
                    _near = difflib.get_close_matches(c["name"], list(cat_index), n=3, cutoff=0.6)
                    if _withheld:
                        _guidance = {
                            "error": "tool_not_available_this_turn",
                            "message": (
                                f"{c['name']!r} is a real tool, but it is not available on this "
                                "turn: it reshapes the book's whole ontology, so it is only "
                                "offered when the author has asked for world-setup. Do NOT keep "
                                "retrying it and do NOT claim you ran it. Tell the author plainly "
                                "that this step needs their go-ahead to set up the book's "
                                "categories, and ask for it."
                            ),
                        }
                    else:
                        _guidance = {
                            "error": "no_such_tool",
                            "message": (
                                f"There is no tool named {c['name']!r}. You invented it — do NOT "
                                "call it again, and do not tell the user you used it. Re-read your "
                                "own reasoning: the step you are on needs a tool that exists."
                                + (f" Closest real names: {', '.join(_near)}." if _near else "")
                                + " Call tool_list to see what this domain really offers, then "
                                "tool_load the exact name before using it."
                            ),
                        }
                    logger.warning(
                        "unresolvable tool %r (session=%s): %s; near=%s",
                        c["name"], session_id,
                        "withheld by the capability floor" if _withheld else "not in any catalog",
                        _near,
                    )
                    if trace is not None:
                        trace.add("compile", "T6", "tools", f"no_such_tool:{c['name']}", is_error=True)
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(_guidance),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False,
                        "result": None, "error": _guidance["message"],
                    }}
                    continue
                # (a) — real tool, just not advertised this turn. Load it and let the call
                # proceed: the model already decided correctly, so making it round-trip through
                # tool_list/tool_load to be told "yes, that one" is ceremony a weak model fails.
                if discovery and c["name"] in cat_index and c["name"] not in active_tool_names:
                    _arm_tools(
                        [c["name"]], active_tool_names=active_tool_names,
                        activation_state=activation_state,
                        discovery_catalog=discovery_catalog,
                        context_length=context_length,
                    )
                    logger.info(
                        "auto-loaded off-surface tool %r (session=%s) — it is in the catalog and "
                        "the model asked for it by name", c["name"], session_id,
                    )

                # backend tool — execute via the ai-gateway over MCP (ai-gateway
                # P0: the only tool transport). Tier-A auto-commits here (the
                # "lazy man" path); Tier-W/S domain tools MINT a confirm_token and
                # return it (no write) — the agent then calls the confirm_action
                # frontend tool, which suspends for the human gate.
                # T4c: on an admin surface, pass the RS256 admin token so
                # glossary_admin_* route to /mcp/admin (no X-User-Id; INV-T2).
                # ── CP-5.10 · THE REGISTRY IS THE ONLY NAME SOURCE ───────────────────────────
                # 🔴 **MEASURED: `glossary_propose_entity_edit` was dispatched 101 TIMES across 12
                # SESSIONS with a 0% success rate, and it is in no catalogue.** A name the model
                # invented, sent to the wire a hundred times. `plan_forge.plan_propose_spec` is the
                # same shape with a namespace prefix bolted on.
                #
                # Everything a turn can legitimately dispatch is in one of these two indexes —
                # `cat_index` is the federated catalogue and `plain_index` the consumer-local
                # tools — and every other path (frontend tools, skills, workflows, the composer)
                # has already been handled ABOVE this line. So a name absent from both cannot be
                # executed by anything; the only question is whether we learn that here or after a
                # round trip and a wasted model pass.
                #
                # Recorded as `refused`, not `failed` (5.7): the tool did not fail, it does not
                # exist. The suggestion comes from the discovery matcher the surface already uses,
                # so the model gets the real name rather than a dead end.
                # 🔴 **FAIL OPEN WHEN WE DO NOT KNOW THE CATALOGUE, AND THIS IS THE OPPOSITE OF
                # THE USUAL DIRECTION FOR A REASON.** Exactly one of these indexes is ever
                # populated (`cat_index` on the discovery path, `plain_index` off it), so BOTH
                # being empty means the catalogue did not load — U-2's outage. Refusing then would
                # answer *"that is not a tool"* for every tool that exists, turning a degraded but
                # working turn into a totally broken one, and the model would have no way to tell
                # the two apart. An unknown name that slips through merely fails at the wire, which
                # is what happened before this check existed.
                _known = cat_index or plain_index
                if _known and c["name"] not in cat_index and c["name"] not in plain_index:
                    _near = [n for n in (list(cat_index) + list(plain_index))
                             if n.endswith(c["name"].split(".")[-1]) or c["name"] in n][:3]
                    _unknown_msg = (
                        f"'{c['name']}' is not a tool. It is not in the catalogue and nothing can "
                        f"execute it — calling it again cannot work."
                        + (f" Did you mean {_near}?" if _near else
                           " Call tool_list to see what exists, then use a name from that list.")
                    )
                    logger.info("CP-5.10: refused undispatchable name %r", c["name"])
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(
                            {"error": "unknown_tool", "message": _unknown_msg}),
                    })
                    yield {"tool_call": instrument.stamp_refused({
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": _unknown_msg,
                    }, "unknown_tool")}
                    continue

                # ── CP-5.8 · THE STATE A TOOL REQUIRES, CHECKED BEFORE DISPATCH ──────────────
                # 🔴 **MEASURED: 414 calls / 82 sessions fail on a missing or wrong scope** — the
                # largest remaining population by the honest denominator. Every failing tool
                # ALREADY DECLARES what it needs (`_meta.scope`: 194 book · 65 user · 33 project ·
                # 23 none) and nothing consulted it, so the model learned the requirement from a
                # round trip and a backend error like `no project in scope`.
                #
                # Gated on `project` only, deliberately. `scope: book` is the SCOPE KEY, not a
                # hard precondition — `book_list` is `scope: book` and is how a model FINDS a
                # book, so refusing it without one would make books unreachable. Verified before
                # building: `kg_project_create` and `kg_project_list` are `scope: user`, so the
                # path to create or find a project stays open under this gate.
                _scope_meta = ((cat_index.get(c["name"]) or plain_index.get(c["name"]) or {})
                               .get("function") or {}).get("_meta") or {}
                if (_scope_meta.get("scope") == "project"
                        and not args_obj.get("project_id")
                        and not (context_ids or {}).get("project_id")
                        and not project_id):
                    _pre_msg = (
                        f"'{c['name']}' works inside a knowledge PROJECT and there is none in "
                        f"scope — it cannot run. Call kg_project_list to find one and pass its id "
                        f"as project_id, or kg_project_create to make one. Calling this again "
                        f"without a project cannot succeed."
                    )
                    logger.info("CP-5.8: refused %r — declares scope=project, none in scope",
                                c["name"])
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content(
                            {"error": "precondition_unmet", "message": _pre_msg}),
                    })
                    yield {"tool_call": instrument.stamp_refused({
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": _pre_msg,
                        "precondition": "project",
                    }, "precondition_unmet")}
                    continue

                # CP-0.3 — the ONE call in this file where a tool genuinely executes. `source='tool'`
                # is defined by having passed through here, not by inspecting the result: that is
                # what makes the "our prose vs a real tool" split exact rather than a text match
                # over breaker phrasing (the earlier attempt at that produced a lower bound which
                # then got reported as a population count).
                _dispatch_t0 = _time.monotonic()
                envelope = await knowledge_client.mcp_execute_tool(
                    user_id=user_id, session_id=session_id, project_id=project_id,
                    # Studio context binding — forward the turn's ambient book so book-scoped
                    # tools resolve book_id from the envelope when the model omits it.
                    book_id=(context_ids or {}).get("book_id"),
                    tool_name=c["name"], tool_args=args_obj,
                    admin_token=admin_token,
                )
                _dispatch_ms = int((_time.monotonic() - _dispatch_t0) * 1000)
                # ext-tasks (T1c(3)) — a capability-gated domain tool opened a durable
                # human gate (returned a task HANDLE, surfaced by mcp_execute_tool as
                # envelope["task"]). Suspend exactly like a frontend tool, but mark it a
                # TASK so resume calls the domain's provide-input tool (derived from the
                # gate tool's provider prefix) instead of a client-side execution. DORMANT
                # until chat-service declares tasks capability (no task comes back before
                # then), so this branch never fires on the current stack.
                _task = envelope.get("task")
                if _task is not None:
                    suspended_call = {
                        "id": c["id"],
                        "name": c["name"],
                        "args": args_obj,
                        "task": _task,
                    }
                    break
                # Phase 2 (P2.2) — propose_edit is now an ai-gateway consumer-local tool
                # that returns a GATED proposal directive instead of suspending as a
                # frontend tool. Detect it and suspend with the SAME shape the legacy
                # frontend-tool suspend created (name=propose_edit, args={operation,text,
                # rationale}) so the FE's ProposeEditCard + the resume driver work
                # unchanged. Client-effect gate: no `task` marker → resumed like a
                # frontend tool (the FE applies the edit + submits applied/dismissed).
                if c["name"] == "propose_edit" and bool(envelope.get("success")):
                    from app.services.task_detect import (  # noqa: PLC0415
                        propose_edit_suspend_args_from_result,
                    )
                    _pe_args = propose_edit_suspend_args_from_result(envelope.get("result"))
                    if _pe_args is not None:
                        suspended_call = {
                            "id": c["id"],
                            "name": "propose_edit",
                            "args": _pe_args,
                        }
                        break
                ok = bool(envelope.get("success"))
                # ── CP-3 · AND THE STEP RECORDS WHAT IT HANDED FORWARD ──────────────────────
                # The declared `emits` paths are read out of the REAL result, so the next step's
                # binding has something to resolve against. Appended to the in-memory STATE
                # immediately, because a two-step plan can run both steps inside ONE turn and the
                # second would otherwise bind against a history that had not been written yet.
                # Persisted by `_emit_chat_turn` — STATE has one writer and it is not this loop.
                if plan_turn is not None:
                    from app.services.plan_exec import observe_call
                    _ev = observe_call(plan_turn.spec, plan_turn.state, c["name"],
                                       ok=ok, result=envelope.get("result"))
                    if _ev is not None:
                        plan_turn.state.append(_ev)
                        if plan_events_out is not None:
                            plan_events_out.append(_ev)
                        logger.info("CP-3 executor: step %d -> %s %s", _ev.step_index, _ev.kind,
                                    sorted(_ev.values) if _ev.values else "")
                # P-1 step-runner — the single backend chokepoint where every rail step tool
                # executes. Count a success only for a tool the pinned rail actually names, so
                # the driver's "a rail step succeeded this turn" gate stays honest. (Confirm/
                # frontend tools suspend BEFORE this line and are correctly never counted.)
                if ok and c["name"] in _rail_all_step_tools:
                    turn_succeeded[c["name"]] += 1
                    # …and the rail just ADVANCED. Its next step's tool is budget-exempt in the
                    # surface seed (D-RAIL-NEXT-STEP-EXEMPT) — but that seed is computed ONCE, at
                    # turn start, from the turn-start probe. A rail that advances WITHIN a turn
                    # therefore leaves the new next step's tool off the wire until the next turn.
                    # Live wedge: the turn opened at 0/9 (next = glossary_list_system_standards,
                    # duly exempted), the model called it, the rail moved to 1/9 (next =
                    # glossary_adopt_standards) — and that tool was never advertised. The model
                    # correctly worked out which tool it needed, could not reach it, and looped.
                    # Re-arm the whole (small, author-declared) step set the moment the rail moves.
                    if discovery and cat_index:
                        _rearm = [
                            t for t in _rail_all_step_tools
                            if t in cat_index and t not in active_tool_names
                        ]
                        if _arm_tools(
                            _rearm, active_tool_names=active_tool_names,
                            activation_state=activation_state,
                            discovery_catalog=discovery_catalog,
                            context_length=context_length,
                        ):
                            logger.info(
                                "rail advanced on %s — re-armed step tools now on the wire: %s",
                                c["name"], ", ".join(sorted(_rearm)),
                            )
                # Repeated-FAILURE breaker — record this failure under (tool → error → count) so a
                # further call that keeps hitting the same error is short-circuited next iteration.
                # A SUCCESS clears the tool's whole map: the loop is broken, so a later failure
                # (e.g. a transient blip) starts fresh rather than inheriting a stale count.
                if not ok:
                    _err_sig = str(envelope.get("error") or "")[:200]
                    fail_by_tool_error.setdefault(c["name"], {})
                    fail_by_tool_error[c["name"]][_err_sig] = (
                        fail_by_tool_error[c["name"]].get(_err_sig, 0) + 1
                    )
                elif c["name"] in fail_by_tool_error:
                    fail_by_tool_error.pop(c["name"], None)
                tool_payload = envelope.get("result") if ok else {"error": envelope.get("error")}
                # D-XWIRE-RESULT — record every `*_id` this result announced, so a later call in
                # the same turn that puts one of them in the WRONG slot is a fact rather than a
                # guess. Successes only: an error payload's ids are the model's own bad input
                # echoed back, and recording those would teach the ledger the mistake.
                if ok:
                    _id_ledger.record(tool_payload)
                # Track C Phase 2 — count SUCCESSFUL identical reads so the repeated-read
                # breaker above can short-circuit the next one. Only successes count: a call
                # that FAILED has not put its answer in the context, so retrying it (with
                # fixed args) is legitimate and must not be blocked.
                if ok and _read_key is not None:
                    # Fingerprint the RESULT, not merely the call. A repeated read is only
                    # pointless when it comes back UNCHANGED — and that distinction is
                    # load-bearing, because POLLING is a repeated identical read whose result
                    # is SUPPOSED to change. `jobs_get`, `translation_job_status` and
                    # `composition_get_generation_job` are all Tier-R, and the workflow rails
                    # explicitly depend on watching an async job to completion. A breaker that
                    # counted calls would have blocked the second poll and stranded every
                    # async step in the catalogue.
                    _fp = hashlib.sha1(
                        json.dumps(tool_payload, sort_keys=True, default=str).encode()
                    ).hexdigest()
                    _seen = read_call_results.get(_read_key)
                    if _seen is not None and _seen[0] == _fp:
                        read_call_results[_read_key] = (_fp, _seen[1] + 1)   # same answer again
                    else:
                        read_call_results[_read_key] = (_fp, 0)              # new answer → reset
                elif ok and tier == "A":
                    # A Tier-A tool result that reports `created: False` COMMITTED NOTHING —
                    # it is a create-or-get that found the resource already there. Record it
                    # for the idempotent-no-op-write breaker (the next identical call is the
                    # loop) and do NOT clear the read ledger, because the world did not change.
                    # A result with `created: True` (or no `created` field at all) is a real
                    # write: clear the read ledger (earlier reads may now be stale) exactly as
                    # before. This split is why the recording is keyed on the RESULT, not the
                    # call — same discipline as the read breaker above.
                    if (
                        _noop_write_key is not None
                        and isinstance(tool_payload, dict)
                        and tool_payload.get("created") is False
                    ):
                        noop_write_counts[_noop_write_key] = (
                            noop_write_counts.get(_noop_write_key, 0) + 1
                        )
                        # oneshot-deadvertise reactive modes — a one-shot create just proved
                        # its target already exists (created:false). Drop it from the surface so
                        # the model stops SEEING it (not just stops the backend dispatch).
                        if c["name"] in ONESHOT_CREATE_TOOLS and _oneshot_mode in ("per_turn", "session"):
                            # transient: off the wire for the rest of THIS invocation.
                            oneshot_suppress.add(c["name"])
                            if _oneshot_mode == "session" and activation_state is not None:
                                # persistent: ALSO remove from the session hot-set so it never
                                # returns this session (the activated_tools that re-advertised
                                # it every turn — the original root cause). dirty ⇒ persisted.
                                _acts = activation_state.get("activated_tools")
                                if isinstance(_acts, list) and c["name"] in _acts:
                                    activation_state["activated_tools"] = [
                                        t for t in _acts if t != c["name"]
                                    ]
                                    activation_state["dirty"] = True
                    else:
                        read_call_results.clear()
                        # A real write means earlier reads may now be stale — which is why the
                        # ledger above resets. The de-advertise has to lift with it, or a tool
                        # blocked for repeating itself would stay off the wire across the very
                        # write that made re-reading it the correct next move. Clearing one and
                        # not the other is the same half-handled transition either way.
                        repeat_block_counts.clear()
                        repeat_read_suppress.clear()
                if ok or _MISSING_REQUIRED_ARGS_MARKER not in str(envelope.get("error") or ""):
                    blank_tool_args_streak = 0
                else:
                    blank_tool_args_streak += 1
                # D7 (single-item overflow): a successful generic tool result is a
                # re-requestable data dump — cap it so one oversized result can't blow the
                # window; the model gets a self-correcting notice to re-call at a smaller
                # scope. Error payloads bypass the cap (already small + the error path).
                if ok:
                    _tool_content, _capped_tokens = tool_result_content_capped_ex(
                        tool_payload, tool_name=c["name"],
                        # Scales up for a session model with a larger real
                        # context_length instead of every model — a 1M-context one
                        # included — getting the same flat cap on one tool result.
                        token_cap=scale_by_window(settings.tool_result_token_cap, context_length),
                    )
                    # Inspector §11 — surface the D7 trip as a trace span so the GUI
                    # shows WHY a tool result was withheld (was log-only before).
                    if _capped_tokens is not None and trace is not None:
                        # is_error per the TraceSpan convention — a D7 withhold is a
                        # reject/self-correcting-error span, not a plain savings span.
                        trace.add(
                            "compile", "T6", "results",
                            f"d7_overflow:{c['name']}",
                            delta=-(_capped_tokens),
                            is_error=True,
                        )
                else:
                    _tool_content = tool_result_content(tool_payload)
                # D-CONFIRM-CARD-NUDGE — a minted confirm card is PENDING THE HUMAN; tell
                # the weak model to stop rather than re-fire the propose tool (double-card)
                # or apologize for a non-error. Applies to the success payload only.
                if ok and _is_confirm_card_result(tool_payload):
                    _tool_content = (_tool_content or "") + _CONFIRM_CARD_STOP_NOTE
                # D-FJ-4 — ARM THE TOOLS THE REFUSAL NAMED. A refusal that says "call X first" is
                # an instruction the model cannot follow when X is off-surface, and it answers by
                # narrating the fix and retrying the same failing call. Same decision the dispatch
                # chokepoint makes for an off-surface tool the model DID call, one step earlier.
                # 🔴 D-A-DOMAIN-REFUSAL-NAMES-A-TOOL-AND-ARMS-NOTHING — THIS WAS GATED ON
                # `not ok`, AND THAT MISSED A WHOLE SHAPE OF REFUSAL.
                # `ok` is the ENVELOPE's status: the CALL succeeded. A tool that dispatches and
                # reports its refusal in the RESULT BODY — the `{"success": False, "error": "…
                # call X first"}` form used throughout composition-service — arrives here with
                # ok=True and armed nothing.
                #
                # MEASURED 2026-08-24, batch c-override12, K=5, from
                # chat_messages.advertised_tools:
                #     composition_entity_override_edit   advertised 5 of 5
                #     composition_list_derivatives       advertised 0 of 5  <- named by its refusal
                # The model was told "Call composition_list_derivatives and pass it THIS SAME
                # project_id" on every run and could not see the tool on any of them; it reached
                # for the composition reads it COULD see and every one refused.
                #
                # Only an EXPLICIT `success is False` counts. Most reads never set the key at
                # all, and treating a missing `success` as failure would scan every ordinary
                # result for tool names.
                _refusal_text = ""
                if not ok:
                    _refusal_text = str(envelope.get("error") or "")
                # 🔴 AND IF THE ENVELOPE'S `error` IS EMPTY, THE TEXT IS IN THE PAYLOAD. Measured
                # 2026-08-24 (c-override-diag): composition_entity_override_edit refused twice
                # with NOT_A_DERIVATIVE — the text is in chat_messages.tool_calls, so it exists —
                # and produced NO line from the diagnostic below, which fires whenever
                # `_refusal_text` is non-empty. The only way through is an empty `_refusal_text`,
                # so `envelope["error"]` was not where that sentence lived. Reading only that one
                # field is why D-FJ-4 armed nothing for this shape long before I touched it.
                if not _refusal_text and isinstance(tool_payload, dict) and (
                        not ok or tool_payload.get("success") is False):
                    _refusal_text = str(tool_payload.get("error") or "")
                if not _refusal_text and isinstance(tool_payload, dict) and (
                        "error" in tool_payload or tool_payload.get("success") is not None):
                    # A payload that CARRIES an error the arming path did not read. This is the
                    # exact blind spot two diagnostic runs could not see into from outside:
                    # composition_entity_override_edit's NOT_A_DERIVATIVE is present in
                    # chat_messages.tool_calls and produced no line here, so the text is in the
                    # payload under a shape this branch does not match. Log the shape, once, so
                    # the next reader does not have to guess it either.
                    logger.info(
                        "%s returned an error payload the arming path did not read: ok=%s "
                        "keys=%s success=%r",
                        c["name"], ok, sorted(tool_payload)[:8], tool_payload.get("success"),
                    )
                if not ok and not _refusal_text:
                    # A failure with no readable text anywhere. Nothing can be armed from it, and
                    # the model gets a refusal it cannot act on either — worth seeing.
                    logger.info(
                        "%s failed with no readable refusal text (envelope keys=%s, payload=%s)",
                        c["name"], sorted(envelope.keys())[:6], type(tool_payload).__name__,
                    )
                # 🔴 THIS PATH USED TO BE SILENT WHEN IT DID NOTHING, AND THAT COST A WHOLE CYCLE.
                # Measured 2026-08-24 (c-override13): the arming log line never appeared, and from
                # outside the process there was no way to tell WHICH of four things was true —
                # the branch was not reached, the text was empty, the named tool was absent from
                # cat_index, or it was already active. Each has a different fix. A mechanism that
                # logs only its successes cannot be diagnosed when it stops succeeding.
                #
                # ── D-A-PER-OP-REFUSAL-NAMES-ARGUMENTS-AND-NO-MOVE ───────────────────────────
                # A flat-superset op-dispatch tool declares only `op` as required, so nothing
                # above this point ever saw a missing argument: the call dispatched and the
                # SERVER refused with the per-op requirement. That refusal names arguments and no
                # TOOL, so the arming below finds nothing and the turn is left with an
                # instruction it cannot act on. Say where each one comes from — which both gives
                # the model a move and puts the supplier's NAME into `_refusal_text`, so the
                # existing arming picks it up instead of needing a second arming path.
                if _refusal_text:
                    # Bound in TWO steps rather than one expression, and not for style: the
                    # single-expression form repeats a string that an anchored falsifier
                    # (test_THE_DECLARATION_IS_THE_SOURCE_NOT_A_TOOL_NAME_LIST) requires to occur
                    # EXACTLY ONCE in this file, and a two-occurrence anchor is a stale anchor.
                    # The membrane gate catches that without running a suite — it caught this.
                    _po_def = cat_index.get(c["name"]) or plain_index.get(c["name"]) or {}
                    _po_props = (
                        (_po_def.get("function", {}).get("parameters", {}) or {})
                        .get("properties") or {}
                    )
                    _po_args = _args_named_in_refusal(_refusal_text, _po_props)
                    # Only when the refusal named NO tool of its own: composition_arc_template_edit
                    # already says "Call composition_arc_template_list to get the id", and adding a
                    # second sentence beside a correct one is noise, not help.
                    _po_already = any(
                        n in _refusal_text for n in (cat_index or {}) if n != c["name"])
                    if _po_args and not _po_already:
                        _po_help = _where_each_argument_comes_from(
                            c["name"], _po_args, _tool_contract_registry(), _po_props)
                        if _po_help:
                            _refusal_text = f"{_refusal_text} {_po_help}"
                            _tool_content = (_tool_content or "") + "\n\n[SYSTEM] " + _po_help
                            logger.info(
                                "per-op refusal from %s named %s and no tool — appended: %s",
                                c["name"], _po_args, _po_help[:160],
                            )
                if _refusal_text and discovery:
                    _recovery = _tools_named_in_refusal(
                        _refusal_text, cat_index, active_tool_names,
                        exclude=c["name"])
                    if not _recovery:
                        logger.info(
                            "%s refused and nothing was armed: refusal=%d chars, "
                            "cat_index=%d tool(s), active=%d, names_in_text=%s",
                            c["name"], len(_refusal_text), len(cat_index or {}),
                            len(active_tool_names or ()),
                            sorted(n for n in (cat_index or {}) if n in _refusal_text)[:5],
                        )
                    if _recovery:
                        _arm_tools(
                            _recovery, active_tool_names=active_tool_names,
                            activation_state=activation_state,
                            discovery_catalog=discovery_catalog,
                            context_length=context_length,
                        )
                        _tool_content = (_tool_content or "") + (
                            "\n\n[SYSTEM] " + ", ".join(_recovery) + " "
                            + ("is" if len(_recovery) == 1 else "are")
                            + " now available to you on this turn — no tool_load needed. Call "
                            + ("it" if len(_recovery) == 1 else "them")
                            + " to clear this, then retry. Do not repeat the call that just failed "
                            "without changing something."
                        )
                        logger.info(
                            "armed recovery tool(s) %s named in %s's refusal (session=%s)",
                            _recovery, c["name"], session_id,
                        )
                working.append({
                    "role": "tool", "tool_call_id": c["id"],
                    "content": _tool_content,
                })
                tool_chunk: dict = {
                    "id": c["id"], "iteration": iteration, "tool": c["name"],
                    "args": args_obj, "ok": ok,
                    "result": envelope.get("result") if ok else None,
                    "error": None if ok else envelope.get("error"),
                }
                # CP-3 — the provenance of the ARGUMENTS, so a plan-supplied call and a
                # model-typed one are not the same row. `overrode` is the load-bearing field: it
                # names the parameters where the model had sent something DIFFERENT, which is the
                # only place the plan changed an outcome rather than filling a blank.
                if _plan_supplied is not None:
                    tool_chunk["plan_supplied"] = _plan_supplied
                # CP-5.3 — the same separation for a RESOLVED argument. Without it a call whose id
                # the runtime looked up and one the model typed correctly are indistinguishable,
                # and the member cannot be measured at all: `model_sent` keeps the NAME, which is
                # the only evidence that resolution changed the outcome rather than filling a blank.
                if _resolution is not None:
                    tool_chunk["resolution"] = _resolution
                # C-ACTIVITY (H16) — a successful Tier-A auto-write emits a visible
                # "agent did X · Undo" activity event. The op summary + undo come
                # from the tool RESULT's `_meta` (undo_hint is NET-NEW per provider;
                # absent → undo unavailable, still surfaced so the write isn't a
                # silent surprise). H17: a FAILED Tier-A is reported as failed (ok=
                # False) so a multi-step goal can't falsely claim whole success.
                if tier == "A":
                    pass_did_write = True
                    tier_a_op_counts[c["name"]] = tier_a_op_counts.get(c["name"], 0) + 1
                    if ok:
                        result = envelope.get("result") or {}
                        result_meta = result.get("_meta") if isinstance(result, dict) else None
                        undo = tool_undo_hint(result_meta)
                        summary = ""
                        if isinstance(result_meta, dict):
                            summary = str(result_meta.get("summary", "") or "")
                        tool_chunk["activity"] = {
                            "op": c["name"],
                            "summary": summary or f"Did {c['name']}",
                            "undo": (
                                {"available": True, "tool": undo.get("tool"),
                                 "args": undo.get("args", {})}
                                if undo else {"available": False}
                            ),
                        }
                # CP-0.3 — latency is the DISPATCH duration, not the branch's wall time: the gap
                # between them is our own overhead, and folding it in would flatter the tool.
                instrument.stamp_tool_call(
                    tool_chunk, source=instrument.SOURCE_TOOL, latency_ms=_dispatch_ms,
                )
                yield {"tool_call": tool_chunk}

            if (
                surface_tracker is not None
                and tool_frags
                and suspended_call is None
            ):
                act_count = (
                    len(activation_state["activated_tools"])
                    if activation_state is not None
                    else len(active_tool_names)
                )
                payload_as = surface_tracker.curated(
                    pinned_count=surface_tracker.pinned_count,
                    hot_seed_count=surface_tracker.hot_seed_count,
                    activated_count=act_count,
                )
                if payload_as is not None:
                    yield {"agent_surface": payload_as}

            if suspended_call is not None:
                # Hand the full conversation + the pending frontend call back to
                # the caller, which persists the suspended run and emits the
                # pending tool-call events + a "suspended" finish. No further
                # passes; the resume request continues the loop.
                # P3 review H1 — in stateful CONTINUE mode `working` is only the DELTA
                # (server holds the history), so persisting it would lose the full
                # conversation the resume needs. Reconstruct the FULL context (the same
                # splice E1 uses) so the resume runs stateless on the complete history.
                _susp_working = (
                    list(messages) + working[_initial_working_len:]
                    if stateful else working
                )
                yield {"suspend": {
                    "working": _susp_working,
                    "pending_tool_call": suspended_call,
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                }}
                return
            # (all-backend-tools case: the inline loop above already executed
            # them and appended results; just continue to the next pass.)
            # MCP-fanout H9: only a pass that actually executed a Tier-A/W WRITE
            # decrements the write budget. A find_tools / Tier-R read pass is
            # free — so discovery + reading never starve the write budget. In the
            # non-discovery (legacy memory-tool) path every tool pass counts, so
            # the cap is byte-identical to the old `for iteration in range(...)`.
            if pass_did_write or not discovery:
                write_passes += 1
            # D7 termination guard: if this pass was the forced tool-free final
            # pass (offered_tools False) yet the model defiantly emitted tool
            # calls, do NOT loop again — fall through to the defensive limit
            # chunk below. (Mirrors the old `for … range(max_iterations)`
            # exhaustion; in the realistic path the final pass has no tool calls
            # and already returned above.)
            # D-TOOLCALL-GEMMA-TOKEN-LEAK exception: a call recovered from the
            # leak scan (`salvaged_this_pass`) is real work we just executed —
            # not a defiant hallucination — so it earns one more pass (itself
            # still force-tool-free, same as any other final pass; bounded by
            # `max_total_passes` regardless) so the model can use the result.
            # Without this, the turn ended empty-handed the instant the tool
            # call finally succeeded — the exact "web search that never
            # actually gets used" gap this fix closes.
            if not offered_tools and not salvaged_this_pass:
                break

        # Write budget exhausted. The final pass is forced
        # tool-free (D7) so this is unreachable in practice — defensive.
        yield {"content": "", "reasoning_content": "",
               "finish_reason": "stop",
               "llm_call_count": llm_call_count,
               "response_id": None if (rail_drove_this_turn and stateful) else _chain_id,
               "context_size": _last_call_input,
               "usage": _Usage(prompt_tokens=total_input,
                               completion_tokens=total_output,
                               cache_creation_tok=total_cache_creation,
                               cache_read_tok=total_cache_read)}
    finally:
        await client.aclose()


async def _run_subagent_call(
    *,
    args: dict,
    subagent_defs: dict[str, dict],
    full_catalog: list[dict],
    model_source: str,
    model_ref: str,
    user_id: str,
    gen_params: dict,
    knowledge_client,
    session_id: str,
    project_id: str | None,
    caller_max_iterations: int,
    decision_check,
    hooks: list[dict] | None,
    effective_limit: int | None,
    subagent_depth: int,
    caller_permission_mode: str,
    context_length: int | None = None,
) -> tuple[dict, int, int]:
    """P5 REG-P5-01 — run ONE subagent as a nested, isolated ``_stream_with_tools``
    turn and return ``(payload, input_tokens, output_tokens)``.

    Isolation invariants:
    * The nested ``messages`` are FRESH — ``[{system: persona}, {user: task}]`` —
      the parent history is NOT included, and the nested messages never enter the
      parent ``working`` array (only this synthesized payload does).
    * The nested tool set is EXACTLY the persona's scoped set (advertise-time
      whitelist); ``allowed_tool_names`` re-enforces it at execute time.
    * The nested run's permission mode is ``clamp_permission_mode(caller)`` —
      ``write`` ONLY when the caller's turn is a write turn, else read-only
      (D-REG-P5-SUBAGENT-WRITE-DELEGATION). A subagent can never EXCEED the caller.
      In write mode it may auto-commit an ALLOWLISTED Tier-A tool within its scope;
      an un-allowlisted Tier-A or a require_approval hook returns a ``result.error``
      (a headless sub-run can't raise the approval card) rather than suspending, and
      Tier-W/S (mint→confirm) writes still cannot complete (confirm_action is a
      frontend tool, excluded from the sub-run's scope). Safety is unchanged:
      tenancy is enforced at the tool layer; consent is what this clamp governs.
    * Depth is bounded: the nested run gets ``subagent_depth+1`` and its scoped set
      excludes ``run_subagent`` — it cannot spawn another subagent.
    """
    name = str(args.get("subagent") or "").strip()
    task = str(args.get("task") or "").strip()
    d = subagent_defs.get(name)
    if d is None:
        avail = ", ".join(sorted(subagent_defs)) or "(none configured)"
        return (
            {"error": f"unknown subagent '{name}'. Available subagents: {avail}"},
            0, 0,
        )
    if not task:
        return ({"error": "the 'task' argument is required — describe the sub-task."}, 0, 0)

    scope_globs = d.get("tool_scope") or []
    scoped = resolve_scoped_tools(full_catalog, scope_globs)
    allowed = {tool_name_of(t) for t in scoped} - {None}
    sub_model_ref = str(d.get("model_ref") or "") or model_ref

    sub_messages = [
        {"role": "system", "content": str(d.get("system_prompt") or "")},
        {"role": "user", "content": task},
    ]

    final_text = ""
    tools_used: list[str] = []
    sub_in = 0
    sub_out = 0
    try:
        nested = _stream_with_tools(
            model_source=model_source,
            model_ref=sub_model_ref,
            user_id=user_id,
            messages=sub_messages,
            gen_params=gen_params,
            tools=scoped,
            knowledge_client=knowledge_client,
            session_id=session_id,
            project_id=project_id,
            max_iterations=min(caller_max_iterations, SUBAGENT_MAX_ITERATIONS),
            permission_mode=clamp_permission_mode(caller_permission_mode),
            decision_check=decision_check,
            hooks=hooks,                     # the caller's hooks still apply
            effective_limit=effective_limit,
            allowed_tool_names=allowed,      # execute-time whitelist
            subagent_depth=subagent_depth + 1,
            # /review-impl MED: the nested run's own tool-surface budgeting
            # (HOT_SEED_TOKEN_BUDGET etc.) should scale by the MODEL THAT RUN
            # ACTUALLY USES, not blindly by the parent's context_length — a
            # subagent def can override model_ref (sub_model_ref above). Only
            # forward it when the subagent is running on the SAME model as the
            # caller; a different model without its own resolved context_length
            # correctly falls back to the flat default rather than misapplying
            # the parent model's window.
            context_length=context_length if sub_model_ref == model_ref else None,
        )
        async for ch in nested:
            if ch.get("content"):
                final_text += ch["content"]
            tc = ch.get("tool_call")
            if tc is not None:
                # Keep only the answer produced AFTER the last tool call.
                final_text = ""
                if tc.get("tool"):
                    tools_used.append(tc["tool"])
            u = ch.get("usage")
            if u is not None:
                # The nested loop sums usage internally; the final chunk carries
                # the cumulative sub-run total.
                sub_in = getattr(u, "prompt_tokens", 0) or 0
                sub_out = getattr(u, "completion_tokens", 0) or 0
            susp = ch.get("suspend")
            if susp is not None:
                # A nested run cannot surface a suspend (no client to execute it).
                # With write-delegation the sub-loop returns a result.error instead
                # of suspending on an approval gate (un-allowlisted Tier-A or a
                # require_approval hook), and frontend tools are scope-excluded — so
                # reaching here is now a defensive last resort. End with whatever the
                # sub-run produced, still attributing its tokens.
                sub_in = susp.get("input_tokens", sub_in) or sub_in
                sub_out = susp.get("output_tokens", sub_out) or sub_out
                break
    except Exception:
        logger.warning("subagent '%s' run failed", name, exc_info=True)
        return ({"error": f"subagent '{name}' failed to run."}, sub_in, sub_out)

    text, truncated = cap_result(
        final_text.strip(),
        char_cap=scale_by_window(SUBAGENT_RESULT_CHAR_CAP, context_length),
    )
    payload: dict = {"subagent": name, "result": text, "tools_used": tools_used}
    if truncated:
        payload["truncated"] = True
    return payload, sub_in, sub_out


#: 28 AN-9 / AN-C2 — the discovery SCENT appended to the studio book_context_note. Static
#: (~1 sentence, no per-turn fetch): names the three orientation reads so a weak model reaches
#: for ONE cheap read instead of stitching 3–6 calls across services, and uses package_tree as
#: the verification read before claiming setup is done (AN-11's F7 honesty guard — exactly what
#: the S06 replay gate measures). It was never built — the false C2/C3 [x] this run's audit found.
#: A module constant so test_orientation_scent can pin it (C2 cannot silently regress again).
_ORIENTATION_SCENT = (
    " For orientation prefer one read over stitching many:"
    " composition_package_tree (the whole book at a glance — spec, manuscript, coverage, runs),"
    " composition_diagnostics (what is wrong), and"
    " composition_find_references (where an entity appears);"
    " read composition_package_tree to verify state before telling the user something is set up."
)


#: D-LAZY-TAIL-UNUSED (2026-08-14) — the sentence that tells the model the surface is PARTIAL.
#:
#: The surfacing architecture is a small budgeted hot seed plus a lazy tail the model reaches
#: through `tool_list`/`tool_load`. Measured across 30 live runs of five ordinary authoring
#: requests: `tool_list` was called ONCE and `tool_load` NEVER — with both advertised on every
#: single run. The tail was not a fallback, it was dead weight, and whatever the deterministic
#: pre-filter put on the wire was the entire reachable catalogue for that turn.
#:
#: Nothing told the model otherwise. `_ORIENTATION_SCENT` names three composition reads; the rest
#: of the note explains ids. The advertised set was presented as simply "the tools", so a model
#: that could not find one for the request did the reasonable thing with what it had — and the
#: reasonable thing is exactly the failure this loop keeps finding: answer from the context block
#: (a queue of one reported as three), or use the nearest write that IS on the wire (three chapters
#: created by a read question).
#:
#: So the last clause is the load-bearing one. It is not "discover more tools"; it is "do not
#: answer a question about the user's data without having called something".
#:
#: 🔴 DEPLOYED, MEASURED, REFUTED — AND IT IS THE THIRD PROSE INTERVENTION TO FAIL THE SAME WAY.
#: Same discriminating fixture (three entities, exactly ONE tagged 'ai-suggested'), K=3, deployed
#: and md5-verified:
#:
#:   baseline                 -> "3 suggested entries"   tool_list 0/3
#:   story_state scope note   -> "you don't have any"    tool_list 0/3   (reverted)
#:   this discovery scent     -> "3 suggested entries"   tool_list 0/3
#:
#: The scent DID change behaviour — the model stopped answering from nothing and called a tool.
#: It called `glossary_search`, which returns EVERY entity, and reported three. It satisfied
#: "call something" by calling the wrong thing, because the right thing was not on the wire.
#:
#: That is the conclusion, and it is worth more than the sentence: PROSE DOES NOT MOVE THIS MODEL
#: OFF THE ADVERTISED SURFACE. Three interventions, zero tool_list calls in 39 runs. Telling the
#: model the surface is partial cannot help when every tool it can actually see is the wrong one.
#: The lever is not the prompt, it is which tools are ON the wire — the declaration gap.
#:
#: Kept as a constant (with its tests) rather than deleted, because it is a clean negative result
#: and the next person WILL propose it. It is not applied.
_DISCOVERY_SCENT = (
    " The tools advertised this turn are a SUBSET chosen from your words, not everything that"
    " exists — a request phrased differently may have no matching tool on the wire even though"
    " one exists. If nothing advertised clearly answers the request, call tool_list (a category,"
    " or \"all\") and then tool_load, before replying. Never answer a question about the user's"
    " own data — counts, lists, what is pending or missing — from memory or from a context block"
    " when no tool returned it; say you are checking, and check."
)


#: U-2 — the outage the model can NAME. Without it the model has no tool left to ask with and every
#: explanation it gives is invented; a verifier watched exactly that, with the model asserting a
#: withheld tool "does not exist at all". The wording says TEMPORARY and says what to do, because
#: "I have no tools" and "you have no tools" produce different replies.
#:
#: **A constant because there are three turn shapes and a verifier found two of them silent.** While
#: this text was inline in one branch, the gate for it could only assert the string literal was
#: present in the module source — which is satisfied by one occurrence and says nothing about the
#: other two paths.
CATALOGUE_UNAVAILABLE_NOTICE = (
    "TOOL CATALOGUE UNAVAILABLE. Your tools could not be loaded for this turn — this is a "
    "temporary outage on our side, NOT a sign that the capability is missing or that the "
    "user's data is absent. Do not claim a tool or feature does not exist, and do not "
    "invent a result. Say plainly that your tools are unreachable right now and that the "
    "user can retry in a moment."
)


async def stream_response(
    session_id: str,
    user_message_content: str,
    user_id: str,
    model_source: str,
    model_ref: str,
    creds: ProviderCredentials,
    pool: asyncpg.Pool,
    billing: BillingClient,
    parent_message_id: str | None = None,
    context: str | None = None,
    thinking: bool | None = None,
    reasoning_effort: str | None = None,
    stream_format: str = "legacy",
    editor_context: dict | None = None,
    book_context: dict | None = None,
    admin_context: dict | None = None,
    admin_token: str | None = None,
    disable_tools: bool = False,
    display_language: str | None = None,
    enabled_tools: list[str] | None = None,
    enabled_skills: list[str] | None = None,
    studio_context: dict | None = None,
    permission_mode: str = "write",
    grounding_enabled: bool = True,
    context_mode: str = "auto",
) -> AsyncGenerator[str, None]:
    """Async generator that yields chat-turn SSE lines.

    ARCH-1 C3: the event serialization is selected per request via
    ``stream_format`` ("legacy" | "agui").

    ARCH-1 C6: ``editor_context`` ({book_id, chapter_id}) — when present (agui +
    editor `<Chat>` panel), the frontend write-back tool (propose_edit) is
    advertised to the LLM; a call to it SUSPENDS the run for client execution
    (see _emit_chat_turn + resume_stream_response).

    ``disable_tools`` — when True, advertise NO tools this turn (memory tools
    AND the editor write-back tool). This is the editor "Compose" mode: the
    user wants the model to write prose to Apply manually, not call tools. Lore
    still reaches the model via the injected context (build_context), only
    tool-*calling* is off — which lets a reasoning model (Qwen 3.5/3.6) draft
    without spending its budget deciding whether to call a tool.

    RAID C2 (DR-C2): ``permission_mode`` ('ask'|'write'|'plan', default 'write')
    — see _stream_with_tools. Compose (disable_tools) is NOT an enum value.
    RAID B2: 'plan' also auto-injects the plan_forge skill (book/editor
    surfaces) and appends the plan-mode system nudge; 'ask' appends its own
    nudge too (no auto-skill) — both on both system-part assembly paths."""

    # CP-0.2 / U-2 — the turn's narrowing sink, armed HERE because this is the first statement of
    # the turn and every later one can narrow. Unconditionally: `disable_tools` and `admin_context`
    # change what is fetched, not whether a narrowing that happens is allowed to register.
    instrument.arm_turn_surface()

    # ── RE-3: parse + STRIP a chat-only inline reasoning command (/no_think etc.)
    # before the message reaches the model or is persisted. The inline override is
    # the highest-precedence reasoning signal (beats the `thinking` toggle below).
    # /review-impl guard: only adopt the stripped text when it's NON-EMPTY — a
    # command-ONLY message ("/no_think") strips to "", and an empty user turn 400s
    # on some providers. In that degenerate case keep the original; the effort
    # override still applies.
    _stripped_msg, _inline_effort = parse_inline_effort(user_message_content)
    if _stripped_msg:
        user_message_content = _stripped_msg

    # ── Load session settings ───────────────────────────────────────────────
    session_row = await pool.fetchrow(
        "SELECT system_prompt, generation_params, project_id, project_ids, composer_model_source, composer_model_ref, "
        "planner_model_ref, working_memory_seed, enabled_tools, enabled_skills, activated_tools, "
        "compact_summary, compacted_before_seq, message_count, created_at, "  # A4 (RV-M5): anchor progress + wrap
        "pinned_legacy_tools, "  # CAT-4 Part D — legacy tools this session deliberately keeps (see drop_superseded_tools)
        "book_id "  # studio context binding — the session's bound book, so _ctx_book_id can fall back to it (X-Book-Id)
        "FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    system_prompt = session_row["system_prompt"] if session_row else None
    gp_raw = session_row["generation_params"] if session_row else {}
    if isinstance(gp_raw, str):
        gp_raw = json.loads(gp_raw)
    gen_params: dict = gp_raw if gp_raw else {}

    # ── RE: resolve reasoning effort and STASH the provider fields in gen_params ──
    # Precedence: inline /command > per-msg `reasoning_effort` (W4 dropdown) >
    # per-msg `thinking` toggle > session > platform.
    _resolve_and_stash_reasoning(
        gen_params, creds,
        thinking=thinking, reasoning_effort=reasoning_effort,
        inline_pref=_inline_effort,
    )

    # asyncpg.Record supports .get() since 0.27; using it lets test mocks
    # that pass a plain dict without project_id continue to work.
    project_id = session_row.get("project_id") if session_row else None
    # ── D-MEMORY-FACT-STORED-UNSCOPED (2026-08-14) — GIVE project_id THE CHAIN ITS SIBLING HAS ──
    #
    # `book_id` is resolved a few lines below from editor_context -> book_context ->
    # studio_context -> the session row. `project_id` had ONE source: the session row. Measured:
    # 417 of 503 book-bound sessions (83%) carry a book and no project, and on every one of them
    # each `ambient_project` tool is told the project is absent — the memory tools, the kg tools,
    # story_search. They do not fail, they degrade silently.
    #
    # Live: memory_remember returned {"remembered": true, "fact_id": …, "confidence": 0.7} and the
    # fact IS in Neo4j — with project_id NULL, one of only 4 such nodes out of 343. Unscoped means
    # unrecallable, so the same session then said "I don't have any information about Mira Solene"
    # about the thing it had just been asked to remember.
    #
    # The invariant: an id the platform can resolve from the turn's OWN context must be resolved
    # before a tool is told it is absent. Deliberately narrow — it fires only when the turn has a
    # book and resolves to THAT book's project, so it can never redirect across scopes (the
    # failure mode `_inject_context_ids` refuses by leaving a valid-but-unknown UUID alone).
    if not project_id:
        _pid_book = (
            (editor_context or {}).get("book_id")
            or (book_context or {}).get("book_id")
            or (studio_context or {}).get("book_id")
            or (session_row.get("book_id") if session_row else None)
        )
        # The FE already hands us the project on a studio turn, and today that value is used ONLY
        # to write the id into the model's prose note — the turn told the MODEL its project id and
        # left its own envelope empty. That inconsistency is what led here.
        project_id = (studio_context or {}).get("project_id")
        if not project_id and _pid_book:
            try:
                from app.services.book_state_probe import project_for_book
                project_id = await project_for_book(str(_pid_book))
            except Exception:  # noqa: BLE001 — a probe failure must leave today's behaviour
                project_id = None                # exactly as it was: None, and fail closed.
        if project_id:
            logger.info(
                "turn project resolved from the book (session row had none): book=%s project=%s",
                _pid_book, project_id,
            )
    # A2A phase-2: optional composer model for in-turn prose delegation.
    composer_src = session_row.get("composer_model_source") if session_row else None
    composer_ref = session_row.get("composer_model_ref") if session_row else None
    composer_model = (composer_src, str(composer_ref)) if composer_src and composer_ref else None
    # D-PLAN-PLANNER-DEFAULT-FE phase 2: optional per-session planner model. When set, it
    # is injected into the agent's glossary_plan call so planning uses this model instead
    # of the per-user provider-registry default (str → the user_model UUID glossary expects).
    planner_ref = session_row.get("planner_model_ref") if session_row else None
    planner_model_ref = str(planner_ref) if planner_ref else None

    knowledge_client = get_knowledge_client()

    # ── K5: build memory block via knowledge-service ────────────────────────
    # Always called — Mode 1 (no project) returns just the user's global
    # bio + a short instruction; Mode 2 (project linked) returns the
    # full L0/L1/glossary block. Failures degrade silently inside the
    # client and return KnowledgeContext(mode="degraded", context="",
    # recent_message_count=50).
    # Track B B1(2) — multi-KG: resolve the effective grounding target (a session
    # may ground on a SET of projects; ≥2 → the union, sent WITHOUT a single
    # project_id to avoid salience misattribution). See resolve_grounding_target.
    _build_project_id, _build_project_ids = resolve_grounding_target(
        session_row, str(project_id) if project_id else None,
    )

    # ── T5 (Context Budget Law D2) — entity-presence intent gate ─────────────
    # Decide whether this turn references book lore; if not (and it isn't an
    # anaphoric/discovery turn), skip the EXPENSIVE grounding retrieval — build_context
    # then serves the LIGHT static path (glossary badges only, no passage vectors /
    # semantic select / LLM). The story_state Core Block (D4) still projects every turn
    # as the safety net, so a false-negative never strips loaded lore; the gate is
    # biased-to-include (opens on any doubt).
    #
    # audit fix (2026-07-04): known-entities is BOOK-scoped, but a session carries the
    # KNOWLEDGE project id — so we resolve the project→book_id first (cached). Passing
    # the raw project_id was the bug that made the gate a silent no-op (it hit a
    # book_id route → [] → always open). A no-book / unresolved project → book_id None
    # → gate stays open (safe).
    # D-LONG-WORK-CONTEXT-MODE — `context.mode` auto-detect (spec
    # 2026-07-06-long-work-auto-detect.md). Resolve the book's known-entity
    # (glossary) size UP FRONT — it's the cheap, already-cached proxy for a
    # big-lore book, and it's the signal `mode=auto` uses to ENABLE the tiers
    # for large books (a 4000-chapter book has a big glossary on turn 1, even
    # with no history). Reused by the T5 gate below, so no extra fetch. The gate
    # runs BEFORE history assembly, so long-conversation pressure is NOT decided
    # here — it stays handled by the adaptive compaction downstream.
    _gate_pid = _build_project_id or (_build_project_ids[0] if _build_project_ids else None)
    _entity_tokens: frozenset[str] = frozenset()
    # WS-4C Half A reuses this SERVER-RESOLVED book id for post-turn canon capture.
    # It is deliberately not `_ctx_book_id` (below), which comes from the FE's
    # editor/book/studio context and is client-supplied: capture WRITES, so its target
    # must be the book knowledge-service resolved from the session's own project.
    # (glossary grant-checks it regardless — this is the belt to that suspenders.)
    _resolved_book_id: str | None = None
    if grounding_enabled and _gate_pid and context_mode != "off":
        try:
            _resolved_book_id = await knowledge_client.resolve_book_id(
                user_id=user_id, project_id=str(_gate_pid)
            )
            if _resolved_book_id:
                _entity_tokens = await get_known_entities_client().get_known_entity_tokens(
                    _resolved_book_id
                )
        except Exception:  # noqa: BLE001 — degrade to gate-open, never break the turn
            _entity_tokens = frozenset()
    _auto = resolve_context_pressure(
        context_mode,
        window=getattr(creds, "context_length", None),
        history_tokens=0,  # gate is pre-history-assembly; long-chat pressure → compaction
        glossary_size=len(_entity_tokens),
    )
    # Effective = AND(deploy ceiling, per-session enablement). The env flags are
    # deploy KILL-SWITCHES (default allow) per the Settings & Config Boundary —
    # `mode=off` force-disables, `auto` enables on the pressure signal, `on`
    # forces on. `_auto.reason` is surfaced to the Inspector (no silent default).
    _ctx_tiers_allowed = _auto.tiers_allowed
    _t5_gate_on = settings.t5_intent_gate_enabled and _ctx_tiers_allowed
    logger.info(
        "context auto-detect: mode=%s tiers_allowed=%s reason=%s pressure=%.2f glossary=%d "
        "(t5_ceiling=%s → t5_gate_on=%s)",
        context_mode, _ctx_tiers_allowed, _auto.reason, _auto.pressure,
        len(_entity_tokens), settings.t5_intent_gate_enabled, _t5_gate_on,
    )
    if not grounding_enabled:
        # Chat & AI settings (spec §3/M3): the user explicitly turned grounding OFF
        # for this turn. This SHORT-CIRCUITS the gate-disabled force-on branch that
        # otherwise makes grounding unconditionally ON (the "always-on, no toggle"
        # silent default). No retrieval is fetched; the T4 story-state net is also
        # gated off below so a cached bible isn't injected behind the user's back.
        _grounding_presence = EntityPresence(False, reason="user_disabled")
    elif _t5_gate_on:
        _grounding_presence = detect_entity_presence(user_message_content, _entity_tokens)
    else:
        # kill-switch / baseline arm: always pull grounding (pre-T5 behavior).
        _grounding_presence = EntityPresence(True, reason="gate_disabled")

    kctx = await knowledge_client.build_context(
        user_id=user_id,
        session_id=session_id,
        project_id=_build_project_id,
        project_ids=_build_project_ids,
        message=user_message_content,
        language=display_language,
        grounding=_grounding_presence.grounding_needed,
        # M1b — forward the editor's open chapter so knowledge's L3 ranker can
        # boost passages near it (working-scope boost). Only editor turns carry
        # editor_context; other surfaces send None → boost inert downstream.
        current_chapter_id=(editor_context or {}).get("chapter_id"),
        context_length=creds.context_length,
    )

    # ── P0-5 (audit Area 3, SEC-4 / ML-4) — neutralize indirect prompt-injection
    # in the retrieved book/graph/knowledge block BEFORE it is spliced into the
    # system prompt. This text (memory, glossary, passages, facts, graph, roleplay
    # anchor) is UNTRUSTED — LLM-generated or user-authored fiction — so it may
    # carry injection ("ignore previous instructions", <|im_start|>system, zero-
    # width/base64 payloads, and the zh/ja/ko/vi equivalents). The model must treat
    # it as DATA, not instructions. Multilingual-safe (Unicode-aware); clean text is
    # returned unchanged so legit CJK/vi content is never mangled. The user's OWN
    # message and session persona/system_prompt are NOT sanitized (that is their
    # input). Mirrors knowledge-service's extraction defense
    # (app/extraction/injection_defense.py). Done here — at the single point the
    # retrieved text enters — so BOTH assembly branches and the token breakdown use
    # the neutralized form.
    kctx.context = neutralize_injection(kctx.context)
    kctx.stable_context = neutralize_injection(kctx.stable_context)
    kctx.volatile_context = neutralize_injection(kctx.volatile_context)
    # NB: `kctx.working_memory` is JSON that resolve_anchor parses — tagging it here
    # would break json.loads and silently drop the anchor. The untrusted fields
    # (goal / redirect_hint) are sanitized below on the RENDERED anchor strings,
    # which also covers the working_memory_seed fallback path.

    # ── T4 (Context Budget Law D4/D5) — story_state Core Memory Block ─────────
    # Maintain the cached, bounded story-bible block (owner-scoped + OCC, see
    # app/db/session_blocks.project_story_state) from the grounding prefix, and project it
    # as a tail block ONLY when this turn has no live grounding (knowledge-service degraded
    # / a future T5-gated-empty mode) — the D4 safety net. Default OFF (settings), so this
    # whole path (incl. the turn-counter query) is skipped in prod. Best-effort: a block
    # failure degrades to "no block", never breaks the turn.
    story_state_block: str | None = None
    if settings.story_state_block_enabled and grounding_enabled and _ctx_tiers_allowed:
        try:
            # The cadence clock: the session's max message sequence — a monotonic
            # per-session counter that advances every turn (granularity is messages,
            # ~2/turn, so the 5-"turn" cadence fires ~every 2-3 conversational turns; it
            # is only the FALLBACK trigger — a source-hash change or lore-gate refreshes
            # sooner). Skipped entirely when the flag is off (zero prod cost).
            _cur_turn = await pool.fetchval(
                "SELECT COALESCE(MAX(sequence_num), 0) FROM chat_messages WHERE session_id = $1",
                session_id,
            )
            story_state_block = await project_story_state(
                pool,
                session_id=session_id,
                owner_user_id=user_id,
                stable_context=kctx.stable_context,
                full_context=kctx.context,
                current_turn=int(_cur_turn or 0),
                lore_gate=settings.t5_intent_gate_enabled and _grounding_presence.grounding_needed,
                context_length=creds.context_length,
                # W1's per-section split, so the safety net can tell "grounding returned lore"
                # from "grounding returned only project instructions" — measured 2026-08-14 as
                # total=50 / sections={instructions: 32} on every turn, with the block standing
                # down and the turn carrying no lore at all.
                sections=getattr(kctx, "sections", None),
            )
        except Exception:  # noqa: BLE001 — degrade to no-block, never break the turn
            logger.warning("story_state block projection skipped (error)", exc_info=True)
            story_state_block = None

    # ── Anchoring (interview-roleplay) — resolve the working_memory anchor ────
    # Prefer the live block from knowledge-service (kctx.working_memory); fall
    # back to the session's frozen working_memory_seed (M3 / degraded EC-4).
    # ("", "") for a non-roleplay session → no injection. Pinned goes in the
    # system block (primacy); tail goes right before the latest user turn
    # (recency). Shared with the voice path (EC-3).
    # A4 (RV-M5) — pass the session facts so the anchor computes the interview progress + wrap
    # (compute_progress): question_count from message_count, elapsed from created_at. A
    # non-interview charter ignores them (no question_target).
    _wm_msg_count = session_row.get("message_count") if session_row else None
    _wm_elapsed = None
    _wm_created = session_row.get("created_at") if session_row else None
    if _wm_created is not None:
        from datetime import datetime, timezone
        _wm_elapsed = max(0, int((datetime.now(timezone.utc) - _wm_created).total_seconds() // 60))
    wm_pinned, wm_tail = resolve_anchor(
        kctx.working_memory,
        session_row.get("working_memory_seed") if session_row else None,
        message_count=_wm_msg_count,
        elapsed_min=_wm_elapsed,
    )
    # P0-5 — the rendered anchor carries untrusted roleplay state (goal /
    # redirect_hint, LLM-written); neutralize injection before it enters the prompt.
    wm_pinned = neutralize_injection(wm_pinned)
    wm_tail = neutralize_injection(wm_tail)

    # ── K-CLEAN-5 (D-K8-04): emit memory_mode to the FE ─────────────────────
    # knowledge-service build_context emits mode="no_project"
    # (Mode 1), mode="static" (Mode 2), or mode="degraded" (client
    # fallback). T01-T19-I1: the original K-CLEAN-5 code checked
    # for "mode_1"/"mode_2" which never matched — every mode
    # silently fell through to the else branch and surfaced as
    # "static", so the FE degraded badge never fired. The e2e
    # suite caught the mismatch. The FE memory_mode vocabulary is
    # already a subset of the backend vocabulary, so forwarding
    # the mode string as-is is both simpler AND the safest fix.
    fe_memory_mode = kctx.mode

    # ── Build message history (size from knowledge_service) ─────────────────
    # W3 — persisted manual compact: when the session carries a compact point
    # (compacted_before_seq), everything before it is represented by the stored
    # compact_summary — fetch only messages AT/after the point and prepend the
    # summary as a synthetic pinned prior-context message (same `<summary>`
    # system-message convention the auto-compaction summarize tier uses). The
    # recent_message_count window still applies to the fetched set.
    history_limit = max(1, kctx.recent_message_count)
    # Context Compiler trace (spec §11) — one accumulator per turn, threaded through the
    # assembly so each tier records what it cut/kept. Its summed savings reconstruct the
    # naive-concat `raw_tokens`; its ordered spans are the Inspector's waterfall. Created
    # here (before C_persist) so the C_persist compaction span is recorded in-order.
    _trace = TraceAccumulator()
    _compact_summary = session_row.get("compact_summary") if session_row else None
    _compacted_before_seq = session_row.get("compacted_before_seq") if session_row else None
    # C_persist (T2 optimization) — before loading history, if the live history exceeds the
    # target, PERSIST a compact so THIS turn AND every later turn load the summary (not raw),
    # instead of re-summarizing every turn (the sweep's 62%-summarizer-overhead regression). A
    # None return (under target / summarizer fail / concurrent compact) leaves the session
    # unchanged — the ephemeral compaction tiers still cap this turn. Threshold =
    # compute_target(context_length) (task_weight=1.0 → surface_max), independent of the
    # ephemeral task-elastic flag.
    if settings.compact_persist_enabled and creds.context_length:
        try:
            _pc = await persist_auto_compact(
                pool, session_id, user_id,
                model_source=model_source, model_ref=model_ref,
                target=compute_target(creds.context_length) or 0,
                keep_recent=8,
                prev_summary=_compact_summary, prev_before_seq=_compacted_before_seq,
                trace=_trace,
            )
            if _pc is not None:
                _compact_summary, _compacted_before_seq = _pc
        except Exception:
            logger.warning("C_persist auto-compact skipped (error)", exc_info=True)
    if _compacted_before_seq is not None:
        rows = await pool.fetch(
            """
            SELECT role, content FROM chat_messages
            WHERE session_id = $1 AND is_error = false AND branch_id = 0
              AND sequence_num >= $3
            ORDER BY sequence_num DESC
            LIMIT $2
            """,
            session_id, history_limit, _compacted_before_seq,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT role, content FROM chat_messages
            WHERE session_id = $1 AND is_error = false AND branch_id = 0
            ORDER BY sequence_num DESC
            LIMIT $2
            """,
            session_id, history_limit,
        )
    messages: list[dict] = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    if _compacted_before_seq is not None and _compact_summary:
        # Pinned (role=system) → the auto-compaction tiers can never drop it.
        messages.insert(0, summary_message(_compact_summary))
    # W1 — measure the replayed history NOW, before the system parts are inserted
    # below, so the breakdown's `history` bucket is exactly the prior turns
    # (includes the just-persisted latest user message).
    _history_tokens = estimate_messages_tokens(messages)

    # ── Compose the system message ──────────────────────────────────────────
    # Order: memory block → session-level system prompt → user's per-message
    # attached context. Memory comes FIRST because it sets durable identity
    # and project state; the session prompt is per-conversation persona on
    # top; per-message context is the most ephemeral.
    #
    # Each part is stripped so a trailing newline in (e.g.) the XML memory
    # block doesn't stack with the "\n\n" separator to produce triple
    # newlines in the final prompt (K5-I3).
    #
    # K18.9 + T2-polish-3 (D-K18.9-01): when the provider is Anthropic
    # AND the memory block came back pre-split by knowledge-service,
    # emit structured system content with `cache_control` markers. Anthropic
    # HARD-caps cache_control at 4 breakpoints (400 otherwise) and caches the
    # CUMULATIVE prefix up to each, so build_system_message uses exactly 2:
    #   BP1 — stable memory prefix (L0 + project + Mode-2/3 prefix up to </project>)
    #     → cached; changes only when L0 / project summary / memory-mode flip
    #   (then) volatile memory (Mode-2/3 glossary + facts + passages) + wm_pinned
    #     → NOT cached; changes per-message by intent
    #   BP2 — the LAST block of the persona+tail region (system_prompt + skills +
    #     steering + workflow + book note); one marker there caches the whole region.
    # D-ANTHROPIC-CACHE-4BP: the old renderer marked EVERY tail block, emitting
    # ~11 breakpoints on a book-scoped turn → Anthropic 400. Non-Anthropic providers
    # (auto-cache) and the degraded / unsplit fallback take the plain-string path.
    # Glossary-assistant P5 + story 04 skill registry: inject selected or
    # surface-default system skills (static + cacheable).
    from app.services.skill_registry import (
        resolve_skills_to_inject_async,
        skill_metadata_block,
        skill_prompts,
    )

    _editor = bool(editor_context)
    _book_scoped = bool(editor_context or book_context)
    _admin = bool(admin_context)
    _studio = bool(studio_context)
    _session_enabled = list(session_row.get("enabled_tools") or []) if session_row else []
    _session_skills = list(session_row.get("enabled_skills") or []) if session_row else []

    # The book this turn is scoped to (FE context). Hoisted ABOVE the skill/workflow
    # resolution because the WS-3 mode binding is resolved per (user, book, mode) and its
    # `inject_skills` must reach `resolve_skills_to_inject_async` below — it is re-used,
    # not recomputed, by the book_context_note further down.
    _ctx_book_id = (
        (editor_context or {}).get("book_id")
        or (book_context or {}).get("book_id")
        or (studio_context or {}).get("book_id")
        # Fall back to the SESSION's bound book (chat_sessions.book_id) — a studio/editor session is
        # book-bound at the row even when the per-turn request contexts omit book_id. Without this the
        # ambient scope (X-Book-Id) is never set for such a session and an ambient tool fail-closes.
        or (str(session_row["book_id"]) if session_row and session_row.get("book_id") else None)
    )

    # WS-2b — fetch the curated workflows visible this turn (System + user + book), and
    # WS-3 (C6) — the mode→capability binding, on the SAME call. Degrade-safe: any failure
    # leaves turn_workflows empty AND the binding None (no workflow_list/_load advertised,
    # no pin, no binding skills — the agent still has raw tools + discovery, i.e. exactly
    # the pre-WS-2b/WS-3 behavior).
    turn_workflows: list[dict] = []
    mode_binding = None
    if stream_format == "agui" and not disable_tools and kctx.tool_calling_enabled:
        try:
            from app.client.registry_workflows_client import get_workflows_client

            _wf_surface = "admin" if _admin else ("editor" if _editor else ("book" if _book_scoped else "chat"))
            _wfs = await get_workflows_client().get_workflows(
                str(user_id), book_id=str(_ctx_book_id or ""), surface=_wf_surface,
                mode=permission_mode,
            )
            turn_workflows = list(_wfs.workflows)
            mode_binding = _wfs.mode_binding
        except Exception:
            logger.warning("workflows fetch failed — no curated workflows this turn", exc_info=True)
            turn_workflows = []
            mode_binding = None

    from app.services.tool_surface import resolve_session_tool_pins
    from app.services.agent_surface import AgentSurfaceTracker

    tool_pins = resolve_session_tool_pins(
        session_row,
        enabled_tools_override=enabled_tools,
        enabled_skills_override=enabled_skills,
    )
    curated_mode = tool_pins.curated_mode
    activation_state = tool_pins.activation_state
    effective_enabled = tool_pins.effective_enabled
    effective_skills = tool_pins.effective_skills

    # Part F / F2 (docs/plans/2026-07-07-intent-skill-router.md) — the async
    # twin computes the IDENTICAL static/structural result first, then
    # additively unions in any skill the embedding-similarity router surfaces
    # for THIS turn's text; `user_id`/`model_source`/`model_ref` are this
    # turn's own already-in-scope values (same reuse discipline as
    # `find_tools_result_async`'s call site) — mandatory fallback inside
    # `resolve_skills_to_inject_async` means this never behaves worse than the
    # old sync-only call on an embed failure.
    injected_skill_codes = await resolve_skills_to_inject_async(
        enabled_skills=effective_skills,
        stream_format=stream_format,
        disable_tools=disable_tools,
        tool_calling_enabled=kctx.tool_calling_enabled,
        editor=_editor,
        book_scoped=_book_scoped,
        admin=_admin,
        # RAID B2 — plan mode auto-injects plan_forge on book/editor surfaces.
        permission_mode=permission_mode,
        studio=_studio,
        intent_text=user_message_content,
        # WS-3 (C6) — the binding's skills, additive + surface-filtered.
        binding_skills=(mode_binding.inject_skills if mode_binding else None),
        user_id=user_id,
        model_source=model_source,
        model_ref=model_ref,
        # F7c — when lazy skill bodies are on, the blanket surface auto-inject is
        # suppressed (L1 index + load_skill instead); pins/mode-bindings/router still
        # inject full L2. OFF ⇒ byte-identical to pre-F7c (the A/B baseline).
        lazy_bodies=settings.lazy_skill_bodies,
    )
    _skill_prompts = skill_prompts(injected_skill_codes)
    glossary_skill: str | None = _skill_prompts.get("glossary")
    if "admin" in _skill_prompts:
        glossary_skill = _skill_prompts["admin"]
    universal_skill: str | None = _skill_prompts.get("universal")
    knowledge_skill: str | None = _skill_prompts.get("knowledge")
    # RAID B2 — the PlanForge skill body (pinned, or auto-injected in plan mode).
    plan_forge_skill: str | None = _skill_prompts.get("plan_forge")
    # Part B (2026-07-07) — composition (pinned, or auto-injected on studio) / translation (pinned only).
    composition_skill: str | None = _skill_prompts.get("composition")
    translation_skill: str | None = _skill_prompts.get("translation")
    # Part B Phase 2 (2026-07-07) — book / settings / jobs (all pinned only, never auto-injected).
    book_skill: str | None = _skill_prompts.get("book")
    settings_skill: str | None = _skill_prompts.get("settings")
    jobs_skill: str | None = _skill_prompts.get("jobs")
    # RAID B2 (+ ask-mode follow-up) — the mode system nudge, appended on BOTH
    # assembly paths below (mirrors skill_meta_block) whenever the turn runs
    # restricted (plan or ask) — write mode is the unrestricted baseline and
    # needs no explanation.
    mode_nudge_block: str | None = (
        PLAN_MODE_NUDGE if permission_mode == "plan"
        else ASK_MODE_NUDGE if permission_mode == "ask"
        else None
    )
    # RAID C3 — L1 skill metadata: a compact "available skills" list injected always
    # (cheap), so the model knows which skills exist on this surface even when only the
    # relevant one's full body (L2) is loaded above.
    # F7c — the L1 index is the model's signal a skill exists whenever it's the ONLY
    # thing injected. When lazy, render it even if the auto-inject list came back empty
    # (the non-curated lazy case) so the model still sees what it can `load_skill`.
    skill_meta_block: str | None = None
    _lazy_skills = settings.lazy_skill_bodies
    if injected_skill_codes or (
        _lazy_skills
        and stream_format == "agui"
        and not disable_tools
        and kctx.tool_calling_enabled
    ):
        skill_meta_block = skill_metadata_block(
            editor=_editor, book_scoped=_book_scoped, admin=_admin, studio=_studio,
            lazy=_lazy_skills,
        )

    # Tool-catalog-simplification Part A — the group directory replaces whole-
    # domain hot-seeding as the model's map of what domains exist. Only worth
    # the tokens when tool-calling is actually live on this turn.
    group_directory_block: str | None = None
    if stream_format == "agui" and not disable_tools and kctx.tool_calling_enabled:
        group_directory_block = group_directory_text()

    surface_tracker = (
        AgentSurfaceTracker()
        if stream_format == "agui" and not disable_tools
        else None
    )

    # Surface the book/chapter ids
    # (glossary ontology adopt/propose, deep-research, propose-edit) fill book_id /
    # chapter_id without a placeholder or asking the user. The FE sends these via
    # editor_context/book_context, but their VALUE was never given to the model —
    # only their PRESENCE gated tool advertising — so the agent passed
    # "YOUR_BOOK_ID_HERE"/"none" and the tool 400'd ("book_id must be a UUID").
    # Carried inside the system message alongside the skills.
    _ctx_chapter_id = (
        (editor_context or {}).get("chapter_id")
        or (studio_context or {}).get("active_chapter_id")
    )
    # CTX-1 — the studio position pointer: the FE hoist already resolved the book's
    # composition Work, so the model is TOLD the project_id instead of foraging for it
    # (a live M-E gate run dead-ended retrying the book_id AS a project_id).
    _ctx_project_id = (studio_context or {}).get("project_id")
    book_context_note: str | None = None
    if _ctx_book_id:
        # Studio context binding (spec 2026-07-22) — do NOT hand the model the book_id UUID. The
        # ambient book rides the envelope (X-Book-Id); tools resolve it (or the server backfills it),
        # so the model transcribing a 36-char UUID is pure token cost + an error surface. Telling it
        # explicitly NOT to pass book_id also stops it inventing a wrong (well-formed) one that the
        # server-side repair can't catch. chapter_id + project_id are NOT ambient — keep giving those.
        book_context_note = (
            "You are working in the CURRENT book. Do NOT pass a book_id to any tool — the system"
            " applies the current book automatically; never ask the user for it and never invent one."
        )
        if _ctx_chapter_id:
            book_context_note += f" The active chapter is chapter_id={_ctx_chapter_id}."
        if _ctx_project_id:
            book_context_note += (
                f" This book's composition/knowledge project is project_id={_ctx_project_id}"
                " — pass it verbatim to any tool that requires a project_id"
                " (a book_id is NOT a project_id)."
            )
        if _ctx_chapter_id:
            book_context_note += (
                " For a tool that requires chapter_id, use the exact id above; never pass a placeholder."
            )
        book_context_note += _ORIENTATION_SCENT  # 28 AN-9 / AN-C2 — the discovery scent
        # _DISCOVERY_SCENT is NOT applied — measured and refuted, see its definition.

    # ── RAID C1 (DR-C1) — per-book steering ─────────────────────────────────
    # Book-scoped turn → fetch the ENABLED steering entries from book-service,
    # select the ones matching this turn (always ∪ #name-mentioned manual/auto
    # ∪ title-matched scene_match), render ONE <steering> system part placed
    # right after the main system prompt on BOTH assembly paths below.
    # Guarded end-to-end: the client degrades to [] and this block swallows
    # everything else — a steering failure never affects the turn.
    steering_block: str | None = None
    if _ctx_book_id:
        try:
            from app.client.book_steering_client import get_book_steering_client
            from app.services.steering import render_steering_block, select_steering

            _steering_entries = await get_book_steering_client().get_steering(str(_ctx_book_id))
            if _steering_entries:
                _active_title = (editor_context or {}).get("chapter_title")
                _steering_selected = select_steering(
                    _steering_entries,
                    message=user_message_content,
                    active_title=_active_title,
                    context_length=creds.context_length,
                )
                steering_block = render_steering_block(_steering_selected) or None
        except Exception:
            logger.warning(
                "steering fetch/render failed for book %s — turn proceeds without steering",
                _ctx_book_id, exc_info=True,
            )
            steering_block = None

    # ── Agent Extensibility Registry (P1, REG-P1-05) — user/book prompt-only skills ──
    # Fetch the caller's + book's registry skills and inject them alongside the
    # built-in SYSTEM_SKILLS: their L1 lines extend the metadata block, their bodies
    # become a system part, and a per-user disable/shadow drops the matching built-in
    # body. Guarded end-to-end — a registry outage degrades to the built-in skills
    # only (the turn is never affected).
    user_skills_block: str | None = None
    if stream_format == "agui" and not disable_tools and kctx.tool_calling_enabled:
        try:
            from app.client.user_skills_client import get_user_skills_client

            _us_surface = "admin" if _admin else ("editor" if _editor else ("book" if _book_scoped else "chat"))
            _uskills = await get_user_skills_client().get_skills(
                str(user_id), book_id=str(_ctx_book_id or ""), surface=_us_surface,
            )
            if _uskills.skills:
                _u_l1 = "\n".join(f"- {s['slug']}: {s.get('description', '')}" for s in _uskills.skills)
                if skill_meta_block:
                    skill_meta_block = skill_meta_block + "\n" + _u_l1
                else:
                    skill_meta_block = "## Available skills\n" + _u_l1
                _u_bodies = [
                    f"## Skill: {s['slug']}\n{s['body_md']}"
                    for s in _uskills.skills if s.get("body_md")
                ]
                if _u_bodies:
                    user_skills_block = "\n\n".join(_u_bodies)
            # Honour per-user disable + shadow of the built-in System skills.
            if _uskills.system_disabled("glossary") or _uskills.shadows("glossary"):
                glossary_skill = None
            if _uskills.system_disabled("universal") or _uskills.shadows("universal"):
                universal_skill = None
            if _uskills.system_disabled("knowledge") or _uskills.shadows("knowledge"):
                knowledge_skill = None
            if _uskills.system_disabled("plan_forge") or _uskills.shadows("plan_forge"):
                plan_forge_skill = None
            if _uskills.system_disabled("composition") or _uskills.shadows("composition"):
                composition_skill = None
            if _uskills.system_disabled("translation") or _uskills.shadows("translation"):
                translation_skill = None
            if _uskills.system_disabled("book") or _uskills.shadows("book"):
                book_skill = None
            if _uskills.system_disabled("settings") or _uskills.shadows("settings"):
                settings_skill = None
            if _uskills.system_disabled("jobs") or _uskills.shadows("jobs"):
                jobs_skill = None
        except Exception:
            logger.warning("user skills fetch/inject failed — built-in skills only", exc_info=True)
            user_skills_block = None

    # The turn's federated tool catalog, fetched ONCE here (it used to be fetched below,
    # AFTER the system prompt was assembled). The PINNED rail needs it: a step's async
    # annotation resolves (1) an authored `async_job`, else (2) the catalog's `_meta.async`,
    # else (3) a NAME HEURISTIC. Rendering the pin without the catalog dropped tier (2), so
    # a pinned rail and a workflow_load'ed rail could disagree about which steps start a
    # background job — the exact pin/load drift reusing `workflow_load_result` was meant to
    # make impossible. (It also saves the duplicate fetch: the block below now reuses this.)
    _turn_catalog: list[dict] = []
    _admin_tool_defs: list[dict] | None = None
    _catalogue_outage = False
    if not disable_tools and kctx.tool_calling_enabled and admin_context:
        # 🔴 U-2's OTHER SIBLING — the admin catalogue was fetched 350 lines BELOW, after the
        # system prompt was already assembled, so an admin turn could not be told about an outage
        # even once the record existed. That is the same reason the user catalogue was moved up to
        # this block (see the note above), applied to the path that was left behind. An admin
        # holding an empty surface is misled by exactly the same silence.
        _admin_tool_defs = await knowledge_client.get_admin_tool_definitions(admin_token)
    elif not disable_tools and kctx.tool_calling_enabled:
        _turn_catalog = await knowledge_client.get_tool_definitions(user_id=user_id)
        # 🔴 U-2, second half. Registering the narrowing is not enough: a verifier watched the
        # model state that a withheld tool "does not exist at all" while the row recorded it
        # correctly — the row was honest and the screen was not. With the whole catalogue gone the
        # model has NO tool left to ask with, not even `find_tools`, so the prompt is the only
        # channel.
        #
        # 🔴 READ FROM THE RECORD, NOT FROM EMPTINESS. The first version of this line was
        # `not _turn_catalog`, which conflates an OUTAGE with a legitimately EMPTY catalogue — a
        # user with no permissions has zero tools and no outage. That is the exact confusion U-2
        # exists to end, reproduced inside U-2's own fix, and three tests caught it by receiving an
        # outage notice on a turn that simply had no tools. The fact comes from the party that knows
        # it failed.
        #
        # Read OUTSIDE the branch that fetched, so it covers whichever catalogue this turn loaded.
        # Gating it on `not admin_context` was how the admin path came to have neither half.
    if not disable_tools and kctx.tool_calling_enabled:
        _catalogue_outage = instrument.catalogue_outage_registered()
    _turn_async_tools = frozenset(
        n for n, td in _catalog_index(_turn_catalog).items() if tool_async(td)
    ) if _turn_catalog else frozenset()

    # WS-3 (C6) — the PINNED rail. The mode binding may pin a workflow; a pinned rail is
    # rendered straight into the prompt (same renderer workflow_load uses, so the two can
    # never drift) and its step tools are pre-activated below. This is the S06 fix:
    # advertising + a "load the matching workflow" directive was NOT enough, because the
    # user never ASKS ("set up my world") — in a real co-writing session they only ASSENT
    # to the agent's own offer ("yeah do it"), and recognising a workflow from an assent is
    # a step a mid-tier model does not reliably take. A pin removes the step.
    pinned_rail_text: str | None = None
    pinned_step_tools: list[str] = []
    _pinned_slugs: list[str] = []
    # P-1 step-runner context — function-scoped so it survives to the _stream_with_tools call
    # even when no rail is pinned (then it stays empty and the loop's re-drive is inert).
    _rail_specs: list[tuple[str, list]] = []
    _rail_turn_start_counts = None
    _rail_grant_ok = False
    # Action-space gating — the turn-start RailProgress objects for the pinned rails, passed to
    # _stream_with_tools so the advertise chokepoint can drop finished steps' tools. Empty ⇒
    # inert (no gating). Parallel to _rail_specs, populated in the same probe block.
    _rail_progress_objs: list = []
    # M2 (all-tracks-clear) — INTENT pinning. The mode binding pins ONE rail per mode
    # (write→vision-to-book), so the OTHER rails (entity-triage, canon-check, kg-build, …) a
    # mid-tier model must DISCOVER, and measured it does so unreliably (S03 0/3, S04 1/3, S09
    # improvises). Map the user's own words to the rail they describe and pin it the SAME way —
    # additive to the binding, filtered to the visible set, deterministic (no LLM). See
    # app/services/intent_workflows.py.
    _binding_slugs = list(mode_binding.inject_workflows) if (mode_binding and mode_binding.inject_workflows) else []
    _intent_slugs: list[str] = []
    if turn_workflows:
        try:
            from app.services.intent_workflows import intent_pinned_workflows
            _vis = {w.get("slug") for w in turn_workflows if w.get("slug")}
            _intent_slugs = intent_pinned_workflows(user_message_content, _vis)
            if _intent_slugs:
                logger.info("intent pinned workflow(s) %s from the user's request", _intent_slugs)
        except Exception:  # noqa: BLE001 — intent pinning is never load-bearing
            logger.warning("intent-workflow pin failed — falling back to binding pins only", exc_info=True)
            _intent_slugs = []
    # D-FJ-21 — the tools this session keeps failing at IDENTICALLY, read from the recorded
    # call history. Cross-turn on purpose: the in-turn repeated-failure breaker and the rail's
    # own nudge counters are BOTH rebuilt every turn, so a step failing twice a turn reset
    # forever (plan_propose_spec, 4 identical refusals across 2 turns, neither breaker fired).
    _rail_stuck_tools: frozenset[str] = frozenset()
    try:
        from app.db.tool_call_history import stuck_tools as _stuck_tools_reader
        _rail_stuck_tools = frozenset(await _stuck_tools_reader(pool, str(session_id)))
        if _rail_stuck_tools:
            logger.info("stuck tools this session (identical failures): %s",
                        sorted(_rail_stuck_tools))
    except Exception:  # noqa: BLE001 — best-effort; "nothing is stuck" is the old behaviour
        logger.warning("stuck-tool read failed", exc_info=True)
    # D-FJ-22 — catalog tools the user named literally. See _tools_named_in_request.
    _named_tools = _tools_named_in_request(user_message_content, _catalog_index(_turn_catalog))
    if _named_tools:
        logger.info("the request names %s — the rail will not claim this turn",
                    sorted(_named_tools))
    _want_slugs = _binding_slugs + [s for s in _intent_slugs if s not in _binding_slugs]
    if turn_workflows and _want_slugs:
        from app.services.workflow_runner import pinned_rail_block

        _visible = {w.get("slug") for w in turn_workflows if w.get("slug")}
        _pinned_slugs = [s for s in _want_slugs if s in _visible]
        # A pin naming a workflow that is not visible on THIS surface cannot run. Never a
        # silent no-op (Agent Extensibility Standard) — say so, and carry on unpinned.
        for _missing in [s for s in _want_slugs if s not in _visible]:
            logger.warning(
                "workflow %r pinned (binding or intent), not visible on this surface — pin skipped", _missing,
            )
        if _pinned_slugs:
            # ── Track C Phase 2 — the RAIL DRIVER ────────────────────────────────────
            # A pinned rail alone still lost the flagship: the model was handed a 12-step
            # recipe and asked to hold it across a 17-turn conversation while doing the
            # emotional work of a co-writing scene, and it dropped it (measured: cast
            # 0/0/0/0 across four identical runs). So compute where the user ACTUALLY is —
            # from the book's own artifacts and from the tool calls the SERVER recorded —
            # and hand the model one named next action instead of asking it to remember.
            #
            # Wholly best-effort: any failure ⇒ no progress block ⇒ the rail renders exactly
            # as it did pre-Phase-2. Grounding must never be able to break a turn.
            _progress_by_slug: dict[str, str] = {}
            # (P-1 step-runner context is captured into the function-scoped _rail_* vars below,
            # where the probe + grant already run, so the tool loop can DRIVE the rail within
            # the turn — not just render WHERE it is.)
            # Deploy-time kill switch. This block edits an ALWAYS-ON system prompt on every
            # write-mode book turn, and a prompt regression is invisible to every unit test
            # in the repo — so it needs an off switch that does not require a code change,
            # and an A/B control that does not require one either. (Settings standard: a
            # deploy-time ceiling/kill-switch is exactly the sanctioned use of an env flag —
            # it gates infrastructure, not a per-user choice.)
            if _ctx_book_id and settings.rail_driver_enabled:
                try:
                    from app.client.grant_client import GrantLevel, get_grant_client
                    from app.db.tool_call_history import succeeded_tool_counts
                    from app.services.book_state_probe import probe_book_state
                    from app.services.rail_progress import (
                        compute_rail_progress,
                        render_progress_block,
                    )

                    # /review-impl HIGH — `_ctx_book_id` is CLIENT-SUPPLIED (book_context in
                    # the request body). The probe fans it out to five internal routes, four
                    # of which do not grant-check the caller. So verify access ONCE here
                    # before the probe runs — one check closes all five sources. Fails CLOSED
                    # (a book-service blip → NONE → no probe), which is correct: an
                    # unverifiable book must not have its state read into the prompt.
                    _lvl, _ = await get_grant_client().resolve_access(
                        UUID(str(_ctx_book_id)), UUID(str(user_id))
                    )
                    if _lvl < GrantLevel.VIEW:
                        logger.info(
                            "rail progress: caller %s has no grant on book %s — probe skipped",
                            user_id, _ctx_book_id,
                        )
                        raise _ProbeAccessDenied

                    _bstate, _ran = await asyncio.gather(
                        probe_book_state(str(_ctx_book_id), str(user_id)),
                        succeeded_tool_counts(pool, str(session_id)),
                    )
                    # The probe + grant succeeded → the loop may DRIVE the rail this turn.
                    _rail_grant_ok = True
                    _rail_turn_start_counts = _ran
                    if _bstate.any_known or _ran:
                        for _slug in _pinned_slugs:
                            _wf = next(
                                (w for w in turn_workflows if w.get("slug") == _slug), None
                            )
                            _steps = _wf.get("steps") if isinstance(_wf, dict) else None
                            if not isinstance(_steps, list) or not _steps:
                                continue
                            _rail_specs.append((_slug, _steps))
                            _prog = compute_rail_progress(_slug, _steps, _bstate, _ran)
                            _rail_progress_objs.append(_prog)
                            _progress_by_slug[_slug] = render_progress_block(_prog)
                            logger.info(
                                "rail %s: %d/%d steps done, next=%s (book=%s)",
                                _slug,
                                sum(1 for s in _prog.steps if s.done),
                                len(_prog.steps),
                                _prog.next_step.tool if _prog.next_step else "—",
                                _ctx_book_id,
                            )
                except _ProbeAccessDenied:
                    pass  # no grant → run the rail ungrounded (the pre-Phase-2 behavior)
                except Exception:  # noqa: BLE001 — grounding is never load-bearing
                    logger.warning("rail progress unavailable — rail runs ungrounded", exc_info=True)

            pinned_rail_text, pinned_step_tools = pinned_rail_block(
                turn_workflows, _pinned_slugs, _turn_async_tools,
                progress_by_slug=_progress_by_slug,
            )

    # WS-5 — STEER a mid-tier model to USE an authored workflow rail. Advertising
    # workflow_list is not enough: gemma had it advertised yet never called it and
    # reconstructed the steps wrong (measured on S01 — proposed entities before any
    # category existed). When the turn has curated workflows, name them and tell the
    # agent to load + follow the matching one FIRST. General across every workflow;
    # degrade-safe (empty string when there are none, so no directive is injected).
    # A PINNED workflow is excluded here: its full rail is already in context, so telling
    # the agent to workflow_load it would be a wasted round-trip.
    workflow_directive_block: str | None = None
    if turn_workflows:
        # F7c — when lazy, list SLUG + short title only; the full description (the fat)
        # is pulled on demand by workflow_load, which the directive already tells the model
        # to call FIRST. Off ⇒ full description inline (byte-identical pre-F7c baseline).
        _lazy_wf = settings.lazy_workflow_directive
        _wf_lines = "\n".join(
            (
                f"- {w.get('slug')}: {w.get('title') or ''}".rstrip()
                if _lazy_wf
                else f"- {w.get('slug')}: {w.get('description') or w.get('title') or ''}".rstrip()
            )
            for w in turn_workflows
            if w.get("slug") and w.get("slug") not in _pinned_slugs
        )
        if _wf_lines:
            _other = "OTHER " if _pinned_slugs else ""
            workflow_directive_block = (
                f"{_other}READY-MADE WORKFLOWS you can run for this book — ordered recipes for "
                "common multi-step jobs:\n"
                f"{_wf_lines}\n"
                "If the user's request matches one of these (e.g. setting up / building / organizing "
                "their world, glossary, or plan), call workflow_load(\"<slug>\") FIRST and then follow "
                "its steps IN ORDER — do NOT improvise your own tool sequence for a job a workflow "
                "already covers. Following the rail is how you avoid getting the order wrong."
            )

    use_anthropic_cache = (
        creds.provider_kind == "anthropic"
        and kctx.stable_context.strip() != ""
    )
    # A1 / T3.1 (Context Budget kernel) — ONE ordered tail-block list, rendered either way
    # by `loreweave_context.build_system_message` (was two lockstep `if` ladders — the A1
    # footgun). Order is LOAD-BEARING and unchanged: steering → built-in skills (glossary/
    # knowledge/universal/plan_forge) → user skills → plan-mode nudge → skill catalog →
    # group directory → book note. Cache path (Anthropic) marks the cacheable prefix; plain
    # path joins with \n\n.
    _tail_blocks = [
        story_state_block,   # T4 — cached story-bible safety net (only set when live grounding is empty)
        steering_block,      # RAID C1 — per-book steering, right after the system prompt
        glossary_skill,
        knowledge_skill,
        universal_skill,
        plan_forge_skill,    # RAID B2 — PlanForge flow (pinned or plan-mode)
        composition_skill,   # Part B (2026-07-07) — pinned, or auto-injected on studio
        translation_skill,   # Part B (2026-07-07) — pinned only
        book_skill,          # Part B Phase 2 (2026-07-07) — pinned only
        settings_skill,      # Part B Phase 2 (2026-07-07) — pinned only
        jobs_skill,          # Part B Phase 2 (2026-07-07) — pinned only
        user_skills_block,   # REG-P1-05 — user/book registry skills (L2 bodies)
        mode_nudge_block,    # RAID B2 (+ask-mode) — plan/ask mode nudge
        skill_meta_block,    # RAID C3 — L1 available-skills catalog
        group_directory_block,  # tool-catalog-simplification Part A — domain map for find_tools(group=...)
        workflow_directive_block,  # WS-5 — prefer an authored workflow rail over improvising
        pinned_rail_text,    # WS-3 (C6) — the mode's PINNED rail, already in context
        book_context_note,
        CATALOGUE_UNAVAILABLE_NOTICE if _catalogue_outage else None,
    ]
    _system_content = build_system_message(
        use_cache=use_anthropic_cache,
        kctx_context=kctx.context,
        kctx_stable=kctx.stable_context,
        kctx_volatile=kctx.volatile_context,
        # Pinned anchor (primacy) — uncached in the cache path: it sits in the prefix the
        # NEXT breakpoint (system_prompt) caches; content-addressed caching just MISSES from
        # here when the executive changes `state` (never stale, re-processed; anchor is small).
        wm_pinned=wm_pinned,
        system_prompt=system_prompt,
        tail_blocks=_tail_blocks,
    )
    if _system_content:
        messages.insert(0, {"role": "system", "content": _system_content})

    # Inject per-message context as a system message right before the last user message
    if context:
        messages.insert(-1, {"role": "system", "content": f"The user has attached the following context:\n\n{context}"})

    # Tail anchor (recency) — inserted LAST so it sits closest to the latest user
    # turn, where attention weights it most (beats lost-in-the-middle). EC-3/EC-7.
    if wm_tail:
        messages.insert(-1, {"role": "system", "content": wm_tail})

    # ── W1: per-category context breakdown ───────────────────────────────────
    # Measured ONCE per turn, at assembly, over the EXACT strings injected above
    # (cheap — estimate_tokens is a linear char scan). The tool-schema buckets are
    # measured later at the advertise chokepoint and the tool-result bucket at
    # finish; both are folded into this object before the frame is emitted.
    if use_anthropic_cache:
        _mem_tokens = estimate_tokens(kctx.stable_context.strip()) + estimate_tokens(
            kctx.volatile_context.strip()
        )
    else:
        _mem_tokens = estimate_tokens((kctx.context or "").strip())
    context_breakdown = ContextBreakdown(
        categories={
            "system_prompt": estimate_tokens(system_prompt.strip() if system_prompt else ""),
            "memory_knowledge": _mem_tokens,
            "working_memory": estimate_tokens(wm_pinned) + estimate_tokens(wm_tail),
            "steering": estimate_tokens(steering_block),
            "skills": sum(
                estimate_tokens(s)
                for s in (
                    glossary_skill, knowledge_skill, universal_skill,
                    plan_forge_skill, composition_skill, translation_skill,
                    book_skill, settings_skill, jobs_skill,
                    skill_meta_block, user_skills_block,
                )
                if s
            ),
            # Category key stays "plan_nudge" (FE Inspector contract — see
            # token_budget.BREAKDOWN_CATEGORIES) though it now also carries the
            # ask-mode nudge; renaming the wire key isn't warranted for this fix.
            # bundles the mode nudge + the WS-5 workflow-preference directive + the WS-3
            # PINNED rail (all three are just-in-time steering; folded here to avoid a new
            # FE Inspector wire key). The pinned rail is the largest of the three and is
            # ALWAYS-ON for its mode, so it must be counted — an unaccounted always-on
            # block is exactly what the Context Budget Law exists to catch.
            "plan_nudge": (
                estimate_tokens(mode_nudge_block)
                + estimate_tokens(workflow_directive_block)
                + estimate_tokens(pinned_rail_text)
            ),
            "story_state": estimate_tokens(story_state_block),  # T4 — safety-net block (0 unless projected)
            "book_note": estimate_tokens(book_context_note),
            "attached_context": (
                estimate_tokens(
                    f"The user has attached the following context:\n\n{context}"
                )
                if context
                else 0
            ),
            "history": _history_tokens,
        },
        knowledge_sections=dict(kctx.sections or {}),
    )

    # ── Phase 1c-ii: gateway resolves api_key / base_url / model_string
    # internally; service no longer needs them. We keep `creds.provider_kind`
    # for the Anthropic cache_control branch above.

    # ── K21-B: resolve tools ─────────────────────────────────────────────────
    # Offer tool-calling when the project hasn't opted out
    # (kctx.tool_calling_enabled) AND knowledge-service serves the tool
    # schemas. A fetch failure → empty list → the turn runs tool-free.
    #
    # MCP-fanout C-FT — DISCOVERY IS THE STANDARD for every agui surface (admin
    # excepted). The full federated catalog is never shipped: it grows without
    # bound as domains / MCP tools are added (P0 — thousands of tools), and a
    # 35k-token tool dump overflows small-context models. Instead each turn
    # advertises the always-on core + the SURFACE'S OWN domains (the "hot set",
    # seeded into the discovery active-set so they're callable on pass 1), and the
    # agent find_tools-searches the long tail on demand. The hot set keeps a
    # surface's skill working (it names its domain's tools directly) while every
    # other domain stays lazy:
    #   universal (no editor/book) → ∅ hot (pure discovery)
    #   book-scoped (book_context) → glossary tools hot
    #   editor (editor_context)    → glossary + composition + book tools hot
    # Admin uses its own small System-tier catalog, fully advertised (no
    # discovery). F2: legacy (non-agui) clients get NO frontend tools and never
    # discover/suspend — they fall through to the plain or full-catalog path.
    discovery_eligible = (
        stream_format == "agui"
        and not bool(admin_context)
        and not disable_tools
        and kctx.tool_calling_enabled
    )
    tool_defs: list[dict] = []
    discovery_catalog: list[dict] | None = None
    discovery_extra_frontend: list[dict] | None = None
    discovery_seed_names: set[str] | None = None
    if not disable_tools and kctx.tool_calling_enabled:
        if admin_context:
            # T4c — ADMIN surface (cms chat): advertise ONLY the System-tier admin
            # catalog from the SEPARATE /mcp/admin endpoint. Curation E17/INV-T6:
            # the book/user /mcp catalog and its frontend write-back tools are
            # NEVER fetched here, so admin sessions can't see them and book/user
            # sessions never reach /mcp/admin. No admin token / fetch failure →
            # empty list → the turn runs tool-free. (Never the discovery path —
            # the admin catalog is small + fully advertised.)
            # Already fetched at the top of the turn, so the outage can reach the system prompt
            # (U-2). Re-fetching here would double the call AND leave this the only reader.
            tool_defs = list(_admin_tool_defs or ())
            # The generic class-C confirm frontend tool, so the agent can surface
            # the System confirm card (suspend → human Confirm → the FE POSTs to
            # /v1/glossary/actions/admin/confirm). Only when there ARE admin tools.
            if stream_format == "agui" and tool_defs:
                from app.services.frontend_tools import GLOSSARY_CONFIRM_ACTION_TOOL
                tool_defs = tool_defs + [GLOSSARY_CONFIRM_ACTION_TOOL]
        else:
            # REG-P2-03 — pass user_id so the gateway appends this user's external-MCP
            # federation overlay (u_/b_/s_ tools) into the turn catalog.
            catalog = _turn_catalog  # already fetched above (the pin needed it)
            # Discovery needs a catalog to search. When the gateway is unreachable
            # (catalog == []), there is nothing to find_tools over → fall back to the
            # plain path rather than spin up a discovery loop with only frontend tools.
            if discovery_eligible and not catalog:
                discovery_eligible = False
            if discovery_eligible:
                from app.services.frontend_tools import frontend_tool_defs
                from app.services.tool_discovery import filter_intent_gated_setup_tools
                editor = bool(editor_context)
                book_scoped = bool(editor_context or book_context)
                # N5a-FULL — capability floor: high-impact world-setup tools are dropped from the
                # turn catalog (all three reach-paths) unless this turn is world-setup intent
                # (glossary_shaping injected). Request-scoped autonomy for the co-writer.
                # …with the PINNED rail's own step tools exempt: the rail is rendered into the
                # prompt naming them, so filtering one out splits guidance from capability and
                # leaves an instruction the model cannot satisfy (see the filter's docstring —
                # this is the Mị Đế 40k-character loop).
                # CP-0.2 — the sink is armed at the TOP of this function, not here. It was armed on
                # this line for one round: above the intent gate, which was then believed to be the
                # turn's first narrowing. It was not — U-2 added an earlier one (the catalogue fetch,
                # 380-odd lines above), and a verifier measured the outage going unrecorded on a real
                # turn. Re-arming here now would DISCARD that record, which is the failure the sixth
                # recurrence's own comment predicted. See `instrument.arm_turn_surface`.
                # DQ-T31 — …and the DECLARATION arm: a gated tool whose own declared synonyms
                # answer this request is exempt, and only that tool. This is the ONLY place it
                # can be done: R1 answerability rescues the tool into the one-off build (which
                # is handed the UNFILTERED catalog), but the per-pass build reads
                # `discovery_catalog` and replaces that list on the first pass — so the rescue
                # lands in a list that is discarded. Restoring the tool BEFORE the removal is
                # what lets R1's own promise hold for it.
                discovery_catalog = filter_intent_gated_setup_tools(
                    catalog, injected_skill_codes, set(pinned_step_tools or ()),
                    request_text=user_message_content,
                )
                # ── D-SUPERSEDED-TOOL-COMPETES-WITH-ITS-REPLACEMENT ───────────────────────
                # CAT-4 states the invariant in tool_discovery: "A legacy tool must never be
                # discoverable: excluded from search_catalog() and from every domain hot-seed."
                # Both of those do exclude it. THIS catalog — the one actually advertised to the
                # model — did not, so a superseded tool sat on the wire beside its replacement.
                #
                # MEASURED 2026-08-14, batch 17: 5 of the 54 distinct tools advertised across the
                # batch were legacy, and every one was the direct predecessor of a tool under
                # test. The model then called the predecessor on 3 of 5 scenarios — it is the more
                # specific name for the exact ask — so three unified tools scored 0/5 while
                # nothing was actually wrong with them.
                #
                # CORRECTED 2026-08-25/26: this used to read "The rule is narrower than
                # 'drop every legacy tool': only when the named replacement is present".
                # The rule was WIDENED on 2026-08-25 — every legacy tool is dropped, with
                # or without a replacement. The old text is preserved in
                # drop_superseded_tools' docstring, labelled as history.
                from app.services.tool_discovery import drop_superseded_tools
                discovery_catalog, _superseded = drop_superseded_tools(
                    discovery_catalog, set(session_row.get("pinned_legacy_tools") or ())
                    if session_row else set(),
                )
                if _superseded:
                    logger.info(
                        "superseded gate: withholding %d legacy tool(s) whose replacement is on "
                        "the same wire: %s", len(_superseded), sorted(_superseded)[:8],
                    )
                # GUI-nav tools deprecated 2026-07-25 — only the editor/book_scoped frontend
                # tools (propose_edit / glossary) are advertised now.
                discovery_extra_frontend = frontend_tool_defs(editor=editor, book_scoped=book_scoped)
                from app.services.tool_surface import discovery_seed_for_surface
                # The union of step tools across the turn's visible workflows — the ONLY
                # activated_tools re-advertised in auto mode (so a persisted rail survives
                # across turns, but stale find_tools accumulations from a prior curated
                # phase do NOT leak into the auto surface). Empty when no workflows visible.
                _wf_step_tools = {
                    str(s.get("tool") or "")
                    for wf in (turn_workflows or [])
                    for s in (wf.get("steps") or [])
                    if isinstance(s, dict) and s.get("tool")
                }
                # D-DOMAIN-HOTSET-NOT-STICKY — re-seed the domains the RECENT conversation
                # actually called into, so auto mode stops forgetting the working domain
                # across turns (the book domain the writer used two turns ago stays hot on a
                # low-signal follow-up like "Option 3, go with that"). Read-only, bounded
                # lookback, decays naturally; degrades to no stickiness on any error.
                _sticky_domains: set[str] = set()
                try:
                    from app.services.tool_discovery import engaged_domains_from_tool_calls
                    _tc_rows = await pool.fetch(
                        "SELECT tool_calls FROM chat_messages "
                        "WHERE session_id = $1 AND role = 'assistant' AND tool_calls IS NOT NULL "
                        "ORDER BY sequence_num DESC LIMIT 8",
                        session_id,
                    )
                    _sticky_domains = engaged_domains_from_tool_calls(
                        [r["tool_calls"] for r in _tc_rows]
                    )
                except Exception:  # noqa: BLE001 — stickiness is best-effort; never break the turn
                    _sticky_domains = set()
                # Budget priority (2026-07-26): the DONE rail step tools, so the rail's
                # token budget is spent on the steps still to do (not on completed early steps
                # that would starve `plan_propose_spec` et al.).
                # v2 (D-RAIL-REPEAT-BUDGET): computed DIRECTLY from progress — ALL done steps,
                # INCLUDING `repeat` ones. The gate function now exempts repeat steps (they must
                # stay advertisable: "add MORE characters" re-invokes a done save-cast), but for
                # BUDGET priority a done-but-repeatable step still yields to never-done steps —
                # tool_surface reorders these to the back of the queue instead of dropping them.
                _rail_done_tools = {
                    s.tool
                    for p in (_rail_progress_objs or [])
                    for s in p.steps
                    if s.done and s.tool
                }
                # Within the done group, a REPEATABLE done step outranks a one-shot done
                # step for budget: the one-shots are advertise-suppressed by the gate
                # anyway, so budget spent on them is pure waste — while a repeat step
                # (save-cast: "add MORE characters") is the one a user actually re-invokes.
                _rail_repeat_done_tools = {
                    s.tool
                    for p in (_rail_progress_objs or [])
                    for s in p.steps
                    if s.done and s.tool and s.repeat
                }
                # D-RAIL-NEXT-STEP-EXEMPT — the tool of each rail's NEXT actionable step is
                # budget-exempt in the surface seed: the step being driven must be callable.
                _rail_next_tools = {
                    p.next_step.tool
                    for p in (_rail_progress_objs or [])
                    if getattr(p, "next_step", None) is not None
                }
                # NOT re-armed here: the sink is armed before catalog assembly above. Setting a
                # fresh list at this point would DISCARD the intent gate's records — which is how
                # the previous fix managed to be a no-op even where it was armed.
                discovery_seed_names = discovery_seed_for_surface(
                    discovery_catalog,  # N5a-FULL — seed from the filtered catalog too
                    pins=tool_pins,
                    editor=editor,
                    book_scoped=book_scoped,
                    studio=bool(studio_context),
                    context_length=creds.context_length,
                    permission_mode=permission_mode,
                    workflow_step_tools=_wf_step_tools,
                    binding_categories=(mode_binding.seed_tool_categories if mode_binding else None),
                    pinned_step_tools=pinned_step_tools,
                    rail_done_step_tools=_rail_done_tools,
                    rail_repeat_done_step_tools=_rail_repeat_done_tools,
                    rail_next_step_tools=_rail_next_tools,
                    sticky_domains=_sticky_domains,
                    # D-SKILL-NAMED-TOOLS-RIDE — the tools these injected skill prompts
                    # name directly must be on the wire (budget-exempt).
                    injected_skill_codes=injected_skill_codes,
                )
                # `tool_defs` is the FIRST-pass advertisement when discovery is on;
                # _stream_with_tools recomputes it each pass (core ∪ extra_fe ∪
                # {seed ∪ discovered}), but a non-empty value flips use_tools True.
                tool_defs = _advertise_discovery_tools(
                    _catalog_index(catalog), discovery_seed_names, discovery_extra_frontend,
                    book_bound=bool(_ctx_book_id),
                    request_text=user_message_content,
                )
            else:
                # No discovery: a legacy non-agui tool-calling client (full catalog —
                # it has no find_tools loop), or an agui surface with the gateway down.
                tool_defs = catalog
                if stream_format == "agui" and (editor_context or book_context or studio_context):
                    # Gateway down but still agui: re-advertise the frontend
                    # write-back / studio-nav tools so the surface can still
                    # propose/confirm/navigate (mirrors the resume path's catalog-down branch).
                    from app.services.frontend_tools import frontend_tool_defs
                    tool_defs = tool_defs + frontend_tool_defs(
                        editor=bool(editor_context),
                        book_scoped=bool(editor_context or book_context),
                    )
        # A2A phase-2: advertise compose_prose only when a composer model is
        # configured for this session (orchestrator → writer delegation).
        if composer_model is not None:
            from app.services.composer import compose_prose_defs
            tool_defs = tool_defs + compose_prose_defs()
    use_tools = bool(tool_defs)

    # ── Stream the turn ──────────────────────────────────────────────────────
    # The Stream/persist/finish body is shared with the C6 resume path via
    # _emit_chat_turn — both a fresh turn and a resumed (post-frontend-tool)
    # turn run the same consume→persist→finish logic.
    # WS-4C Half A — carry the capture inputs into the post-turn block. `_build_project_id`
    # is None on a MULTI-project turn, so `book_id` is None there: capture writes into one
    # book's inbox and a union of projects has no single book to choose.
    _canon_capture_ctx = CaptureContext(
        book_id=_resolved_book_id if _build_project_id else None,
        project_enables=kctx.canon_capture_enabled,
        grounding_enabled=grounding_enabled,
    )

    async for line in _emit_chat_turn(
        session_id=session_id,
        user_message_content=user_message_content,
        user_id=user_id,
        model_source=model_source,
        model_ref=model_ref,
        creds=creds,
        pool=pool,
        billing=billing,
        parent_message_id=parent_message_id,
        project_id=str(project_id) if project_id else None,
        canon_capture_ctx=_canon_capture_ctx,
        stream_format=stream_format,
        editor_context=editor_context,
        # S02 fix — the ids resolved above from editor/book/studio context (book-scoped
        # surfaces carry book_id in book_context, which is NOT threaded further down).
        context_ids={
            "book_id": _ctx_book_id,
            "chapter_id": _ctx_chapter_id,
            "project_id": _ctx_project_id or (str(project_id) if project_id else None),
            # Studio single-book flag — a studio turn works ONE book at a time, so a
            # book-scoped tool arg whose book_id differs from this one is a hallucination to
            # override (see _inject_context_ids). Only set on a real studio turn.
            "studio": studio_context is not None,
        },
        admin_token=admin_token,
        messages=messages,
        gen_params=gen_params,
        tool_defs=tool_defs,
        use_tools=use_tools,
        knowledge_client=knowledge_client,
        fe_memory_mode=fe_memory_mode,
        msg_id=str(uuid4()),
        seed_usage=None,
        composer_model=composer_model,
        composer_system_prompt=system_prompt,
        planner_model_ref=planner_model_ref,
        # Iteration budget by surface (H9 / H11): universal /chat = 20 (find_tools
        # + reads uncounted), book-scoped + editor + admin (cms) = 10, plain = 5.
        # `discovery_catalog is not None and no book/editor` ≡ the universal surface.
        max_iterations=(
            UNIVERSAL_TOOL_ITERATIONS
            if (discovery_catalog is not None and not (editor_context or book_context))
            else GLOSSARY_TOOL_ITERATIONS if (editor_context or book_context or admin_context)
            else MAX_TOOL_ITERATIONS
        ),
        discovery_catalog=discovery_catalog,
        discovery_extra_frontend=discovery_extra_frontend,
        discovery_seed_names=discovery_seed_names,
        curated=curated_mode,
        activation_state=activation_state,
        surface_tracker=surface_tracker,
        injected_skills=injected_skill_codes,
        effective_enabled_count=len(effective_enabled) if curated_mode else 0,
        hot_seed_count=len(discovery_seed_names or ()),
        permission_mode=permission_mode,
        context_breakdown=context_breakdown,
        # T5 — the intent-gate decision, surfaced in the contextBudget frame.
        entity_presence=_grounding_presence.as_telemetry(),
        # Context Compiler trace (§11) — carries any C_persist span already recorded; the
        # in-turn compaction + T0 wire spans are appended inside _emit_chat_turn.
        trace=_trace,
        turn_workflows=turn_workflows,
        pinned_step_tools=pinned_step_tools,
        # P-1 step-runner — the pinned rails' (slug, steps) + turn-start probe/grant.
        rail_specs=_rail_specs or None,
        rail_grant_ok=_rail_grant_ok,
        rail_turn_start_counts=_rail_turn_start_counts,
        rail_async_tools=_turn_async_tools,
        # Action-space gating — turn-start RailProgress for the pinned rails (parallel to
        # _rail_specs); the advertise chokepoint drops finished steps' tools per the gate mode.
        rail_progress=_rail_progress_objs or None,
        rail_intent_slugs=frozenset(_intent_slugs),
        rail_stuck_tools=_rail_stuck_tools,
        request_text=user_message_content,
        rail_named_tools=_named_tools,
    ):
        yield line


#: Strong references to in-flight cancel-path writes. asyncio holds only a WEAK reference to a task
#: created with create_task, so a write detached during cancellation can be garbage-collected
#: mid-flight — losing exactly the turn the detach existed to save. Discarded on completion.
_DETACHED_CANCEL_WRITES: set = set()


async def _persist_terminal_assistant(
    pool: asyncpg.Pool,
    *,
    msg_id: str,
    session_id: str,
    user_id: str,
    parent_message_id: str | None,
    model_ref: str | None,
    content: str,
    reasoning: str,
    tool_calls_history: list[dict] | None,
    finish_reason: str,
    is_error: bool,
    error_detail: str | None,
    # CP-0 — the instrument. Optional at the signature so no caller can fail to compile, but
    # `outcome` is derived rather than left NULL when a caller omits it: a terminal path that
    # records no outcome is the exact hole CP-0.4 exists to close, and defaulting to NULL would
    # reproduce it under a new column name.
    outcome: str | None = None,
    advertised_tools: list[dict] | None = None,
    withheld_tools: list[dict] | None = None,
    # CP-0.7 — **`runtime_variant` IS NOT A PARAMETER.** It was one, defaulting to `legacy`, and no
    # caller ever passed it: this path handles error, interrupt and abandoned-suspend, which are
    # exactly the terminal shapes a hand-passed label misses. `current_runtime_variant` argues the
    # asymmetry — a missing label protects the new arm from false CREDIT but not from a missing
    # FAILURE, so the arm measures safer than it is, by construction. Derived below.
) -> bool:
    """DBT-CHAT-PERSIST — persist an assistant reply that ended WITHOUT a clean
    finish (an error mid-stream, a user interrupt, or an abandoned/expired
    frontend-tool suspend) so the streamed content is not lost.

    The normal end-of-turn write (the rich INSERT in `_emit_chat_turn`) only runs
    on success; this is its terminal-path sibling. Idempotent on `message_id`
    (ON CONFLICT DO UPDATE) so a double-materialization — e.g. an expired resume
    AND the sweep both firing — can't duplicate or double-count. Best-effort:
    never raises (it runs on error/cancel paths that must not add a second
    failure). Returns True iff a row was written/updated.

    Skips a truly-empty turn (no content and no reasoning and no tool calls): the
    user message stands alone and a blank assistant bubble would be noise.
    """
    # 🔴 **F-50 — HOISTED, AND THE BUG WAS THAT THEY WERE NOT.** Both were computed 90 lines below,
    # on the far side of the early return that reads `_withheld_json`. So **every** empty terminal
    # turn raised `UnboundLocalError` inside the orphan-stamp, was caught by the best-effort
    # `except Exception` that exists so an error path cannot add a second failure, and recorded
    # nothing at all — at a **100% rate**, from `497d6995f` (2026-08-06) until this line.
    #
    # The commit that broke it was the fix for the *previous* finding on this same statement: a
    # verifier measured `withheld_tools` being calculated and dropped here, so `withheld_tools` was
    # added to the UPDATE — reading a name bound two branches later. **The repair for that finding
    # therefore never ran once.** Found by CP-2's in-process live turn against a real connection;
    # invisible to the suite, because the exception is swallowed and no test called this function
    # with the empty shape.
    #
    # They are pure functions of the parameters, so computing them before the branch is free and
    # removes the ordering hazard rather than documenting it.
    _advertised_json = json.dumps(advertised_tools) if advertised_tools else None
    _withheld_json = json.dumps(withheld_tools) if withheld_tools else None
    if not content and not reasoning and not tool_calls_history:
        # CP-0.4, KNOWN HOLE, DELIBERATELY NOT CLOSED HERE. This is a terminal path that records
        # nothing at all — an empty turn leaves no row, so it has no outcome, and it is invisible to
        # every query CP-0 installs. It is one of the four silent exits, and they close as ONE
        # mechanism at CP-3 (a plan that ends anywhere but done_when names what is live and hands it
        # to a human), not as four patches. Closing it here would mean writing a blank assistant
        # bubble into the UI, which is a product change this checkpoint has no business making.
        # Logged so the hole is countable in the meantime rather than merely known.
        # ── P3 · CLOSED HERE, and the earlier deferral was a wrong assumption of mine ──────────
        # I recorded this as unfixable-before-CP-3.6 because writing a row means a blank assistant
        # bubble in the UI. That assumed the outcome needs an ASSISTANT row. It does not: `outcome`
        # is a column on `chat_messages`, not a property of a role, and the USER'S row already
        # exists for every one of these turns — it is what makes them *orphaned* rather than absent.
        #
        # So the turn's fate is stamped on the message that is already there. No bubble is created,
        # no product behaviour changes, and the two paths that recorded NOTHING — a cancel before
        # the first token, and a process death before any checkpoint — now record what happened to
        # the user's request. That is P3's whole claim: every terminal path writes an outcome.
        #
        # What this does NOT do is give the turn a reply. Materialising abandoned work into
        # something a human can resume is still CP-3.6's mechanism, and still one mechanism rather
        # than four patches. This closes the RECORDING hole, which is CP-0's half of it.
        _orphan_outcome = outcome or instrument.outcome_for_finish_reason(
            finish_reason, is_error=is_error
        )
        # 🔴 NOT `parent_message_id`. Measured live: that id is a UUIDv4 present in NO row on this
        # path, so the UPDATE matched nothing and 0 of 3,154 user rows ever carried an outcome —
        # while the log confidently reported "no parent to stamp" and the parent plainly existed,
        # 0.3s earlier in the same session. The guard reported the absence of a row it had failed
        # to look for.
        #
        # Anchored on the SESSION instead, which is the identifier this path actually holds: the
        # newest user message with no outcome yet. `ORDER BY sequence_num DESC LIMIT 1` in a
        # subquery, so a session with several unanswered user turns stamps the one this turn was
        # for, not all of them.
        try:
            async with pool.acquire() as conn:
                _stamped = await conn.fetchval(
                    # 🔴 `withheld_tools` TOO. The caller computes `withheld_json()` and hands it in,
                    # and this branch wrote only the outcome — so the value was **calculated and
                    # dropped** on exactly the turn shape a catalogue outage produces (no content,
                    # no tool calls, because the model had nothing to work with). Measured by a
                    # verifier: `wrote_row=False, carries_outage=False`. The orphan-stamp mechanism
                    # exists so a turn with no assistant row still records what happened to it; a
                    # narrowing is part of what happened to it.
                    # 🔴 `incoming='$3::jsonb'` — F-50's SECOND layer. The default emits
                    # `EXCLUDED.withheld_tools`, which exists only in an `ON CONFLICT DO UPDATE`;
                    # this is a plain UPDATE, so Postgres refused every execution with
                    # `missing FROM-clause entry for table "excluded"`. The bound parameter IS the
                    # incoming value here.
                    "UPDATE chat_messages SET outcome = $2, "
                    f"       {instrument.segment_merge_sql('withheld_tools', incoming='$3::jsonb')} "
                    "WHERE message_id = ("
                    "  SELECT message_id FROM chat_messages "
                    "  WHERE session_id = $1 AND role = 'user' AND outcome IS NULL "
                    "  ORDER BY sequence_num DESC LIMIT 1) "
                    "RETURNING message_id",
                    session_id, _orphan_outcome, _withheld_json,
                )
            if _stamped is not None:
                logger.info(
                    "CP-0.4 orphaned turn: no assistant row, outcome '%s' stamped on user "
                    "message %s (session %s)",
                    _orphan_outcome, _stamped, session_id,
                )
                return False
            logger.info(
                "CP-0.4 orphaned turn: no un-outcomed user message to stamp (session %s) — the "
                "one remaining shape, and it is countable rather than silent.",
                session_id,
            )
        except Exception:  # noqa: BLE001 — best-effort; this runs on error/cancel paths
            logger.warning(
                "CP-0.4 orphan-stamp failed (session %s)", session_id, exc_info=True,
            )
        logger.info(
            "CP-0.4 silent-exit: empty terminal turn with NO parent to stamp (session %s, msg %s, "
            "reason=%s) — the one remaining shape, and it is countable.",
            session_id, msg_id, finish_reason,
        )
        return False
    parts: dict = {}
    if reasoning:
        parts["reasoning"] = reasoning
        parts["reasoning_length"] = len(reasoning)
    content_parts = json.dumps(parts) if parts else None
    # CP-0.3 — the chokepoint. Every recorded call carries a source, a declaration identity and a
    # runtime variant by the time it is persisted, whichever of the 30-odd mint sites produced it.
    if tool_calls_history:
        tool_calls_history = [
            instrument.ensure_tool_call_instrumented(tc) for tc in tool_calls_history
        ]
    tool_calls_json = json.dumps(tool_calls_history) if tool_calls_history else None
    _outcome = outcome or instrument.outcome_for_finish_reason(finish_reason, is_error=is_error)
    # `_advertised_json` / `_withheld_json` are bound at the top of the function — see F-50.
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # D-AN-ABORTED-TURNS-DETACHED-WRITE-RACES-THE-RETRYS-SEQUENCE — this is the
                # DETACHED writer: an aborted turn's reply is persisted after cancel, and the
                # client's retry races it. One lock, held to COMMIT, covers both.
                seq = await next_sequence_num(conn, session_id)
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO chat_messages
                      (message_id, session_id, owner_user_id, role, content, content_parts,
                       sequence_num, model_ref, parent_message_id, branch_id, tool_calls,
                       is_error, error_detail, finish_reason,
                       outcome, advertised_tools, withheld_tools, runtime_variant, outcome_source)
                    VALUES ($1,$2,$3,'assistant',$4,$5::jsonb,$6,$7,$8,0,$9::jsonb,$10,$11,$12,
                            $13,$14::jsonb,$15::jsonb,$16,'path')
                    ON CONFLICT (message_id) DO UPDATE SET
                      content = EXCLUDED.content,
                      content_parts = EXCLUDED.content_parts,
                      tool_calls = EXCLUDED.tool_calls,
                      is_error = EXCLUDED.is_error,
                      error_detail = EXCLUDED.error_detail,
                      finish_reason = EXCLUDED.finish_reason,
                      outcome = EXCLUDED.outcome,
                      -- CP-0.4 — a terminal path SAYS SO. Nothing wrote 'path', so a swept row and
                      -- a path-written row were distinguishable only by the sweep's own marker —
                      -- one-directional, and 64.8% of outcomed rows read as path-written when they
                      -- were not. The distinction only bites if BOTH sides declare themselves.
                      outcome_source = 'path',
                      -- CP-0.1/0.2 — this row is upserted several times per turn (a checkpoint at
                      -- each tool boundary, then the terminal handler) AND across turns (a resume
                      -- builds a fresh recorder for the same message_id). Those two need opposite
                      -- things from a merge, which is why both previous versions were wrong:
                      -- COALESCE erased the resumed turn's earlier passes, and the concatenation
                      -- that fixed it duplicated every pass a checkpoint had already written.
                      -- The expression is built ONE PLACE — `instrument.segment_merge_sql` — and
                      -- interpolated at both upsert sites, because two hand-maintained copies of a
                      -- merge rule is how the class-4 predicate and the sweep came to contradict
                      -- each other in the same commit (F-45).
                      {instrument.segment_merge_sql("advertised_tools")},
                      {instrument.segment_merge_sql("withheld_tools")},
                      runtime_variant = EXCLUDED.runtime_variant
                    RETURNING (xmax = 0) AS inserted
                    """,
                    msg_id, session_id, user_id, content, content_parts, seq,
                    model_ref, parent_message_id, tool_calls_json,
                    is_error, error_detail, finish_reason,
                    _outcome, _advertised_json, _withheld_json,
                    instrument.current_runtime_variant(),
                )
                # Only bump the session counter on a genuine INSERT (xmax=0), never
                # when ON CONFLICT took the UPDATE branch (already counted).
                if row is not None and row["inserted"]:
                    await conn.execute(
                        "UPDATE chat_sessions SET message_count = message_count + 1, "
                        "last_message_at = now(), updated_at = now() WHERE session_id = $1",
                        session_id,
                    )
        logger.info(
            "terminal-persist: saved %s assistant reply for session %s (msg %s, %d chars, "
            "outcome=%s, runtime=%s)",
            finish_reason, session_id, msg_id, len(content), _outcome,
            instrument.current_runtime_variant(),
        )
        return True
    except Exception:  # noqa: BLE001 — best-effort; runs on error/cancel paths
        logger.warning(
            "terminal-persist FAILED for session %s (msg %s, reason=%s)",
            session_id, msg_id, finish_reason, exc_info=True,
        )
        return False


async def _materialize_abandoned_suspend(pool: asyncpg.Pool, susp) -> bool:
    """DBT-CHAT-PERSIST — turn an abandoned frontend-tool suspend (its card
    expired, or its resume was refused/errored) into a visible 'interrupted'
    assistant message so the whole turn does not silently vanish on reload.

    Reconstructs the model's visible PROSE from the suspended `working`
    conversation (a pure tool-call turn often has none); when there is no prose,
    falls back to the pending tool's rationale (or its name) so the bubble still
    says *something*. Reuses the same message_id the resume would have written
    under, so a later successful path stays idempotent. Best-effort."""
    prose_parts = [
        m["content"].strip()
        for m in (susp.working or [])
        if m.get("role") == "assistant"
        and isinstance(m.get("content"), str)
        and m["content"].strip()
    ]
    content = "\n\n".join(prose_parts)
    if not content:
        pend = susp.pending_tool_call or {}
        args = pend.get("args") if isinstance(pend.get("args"), dict) else {}
        rationale = args.get("rationale") if isinstance(args.get("rationale"), str) else None
        content = (rationale or "").strip() or f"(A “{pend.get('name') or 'change'}” suggestion was proposed here.)"
    return await _persist_terminal_assistant(
        pool,
        msg_id=susp.message_id,
        session_id=susp.session_id,
        user_id=susp.owner_user_id,
        parent_message_id=susp.parent_message_id,
        model_ref=susp.model_ref,
        content=content,
        reasoning="",
        tool_calls_history=None,
        finish_reason="interrupted",
        is_error=False,
        error_detail=None,
        # CP-0.4 — an ABANDONED frontend-tool suspend: the confirm card expired, or its resume was
        # refused. The user was asked and never answered, so this is the user walking away, not a
        # fault. Deliberately not `failed`: the turn did exactly what it should have and then waited.
        outcome=instrument.OUTCOME_ABANDONED_BY_USER,
    )


async def _mark_suspend_abandoned(pool: asyncpg.Pool, susp) -> None:
    """DBT-CHAT-PERSIST — a suspended run is being abandoned (its card expired /
    the resume was refused). Preferred path: the suspend checkpoint already wrote
    a rich provisional row ('awaiting_input') for this msg_id — just flip its badge
    to 'interrupted' so the reply stays (with its prose + tools + the now-dead
    card) but reads as incomplete. Only if NO provisional exists (the best-effort
    suspend checkpoint failed) do we reconstruct from `working`. Never clobbers a
    row that already resolved to 'stop'/'error'/'interrupted'. Best-effort."""
    try:
        row = await pool.fetchrow(
            "SELECT finish_reason FROM chat_messages WHERE message_id = $1",
            susp.message_id,
        )
        if row is None:
            await _materialize_abandoned_suspend(pool, susp)
        elif row["finish_reason"] == "awaiting_input":
            # CP-0.4 — `outcome` moves WITH `finish_reason`. Updating one and not the other left
            # `awaiting_input` — a SUCCESS state — on a run the same statement was declaring
            # abandoned, so an abandoned suspend would have been counted as a turn that correctly
            # stopped to ask. A column that disagrees with its neighbour is worse than a missing one:
            # it answers confidently and wrongly. The user was asked and never came back, which is
            # `abandoned_by_user`, not a failure.
            await pool.execute(
                "UPDATE chat_messages SET finish_reason = 'interrupted', outcome = $2 "
                "WHERE message_id = $1",
                susp.message_id, instrument.OUTCOME_ABANDONED_BY_USER,
            )
        # else: already resolved — leave it.
    except Exception:  # noqa: BLE001 — best-effort recovery path
        logger.warning(
            "mark-suspend-abandoned failed for msg %s", susp.message_id, exc_info=True,
        )


class TurnCeilingExceeded(Exception):
    """DQ-T56(1) — the turn as a whole outran ``llm_turn_ceiling_s``.

    Deliberately a plain ``Exception`` and NOT a ``CancelledError``: the turn
    handler's cancel arm means "the client went away", records
    ``abandoned_by_user`` and re-raises. A ceiling expiry is neither of those —
    nobody abandoned anything, the platform gave up — so it must land in its own
    arm and say so.
    """

    def __init__(self, elapsed_s: float, ceiling_s: float) -> None:
        self.elapsed_s = elapsed_s
        self.ceiling_s = ceiling_s
        # `.1f`, not `.0f`. This string is what lands in `error_detail`, and at any ceiling
        # under a second the rounded form reads "turn ran 0s, past its 0s ceiling" — measured
        # in the deployed container the first time this was exercised. Production values are
        # whole minutes and would never have shown it.
        super().__init__(
            f"turn ran {elapsed_s:.1f}s, past its {ceiling_s:.1f}s ceiling"
        )


def _humanize_seconds(seconds: float) -> str:
    """How long the turn ran, in words an author reads once and believes.

    🔴 **THE FIRST VERSION LIED, AND THE LIVE RUN IS WHAT CAUGHT IT.** It was
    ``max(1, int(round(elapsed / 60)))`` with the word "minute(s)" after it, so a
    turn that ran **20 seconds** told the author it had been "ended after 1
    minute(s)". At the production ceiling of 900s it would have read "15
    minute(s)" and been right, which is exactly why no unit test and no reading of
    the code found it — the defect only appears below 90 seconds. Five real turns
    against a 20s ceiling printed it five times.

    The whole point of half (2) of DQ-T56 is that the row SAYS what happened. A
    row that says it truthfully at one ceiling and falsely at another is not that.
    """
    seconds = max(0.0, float(seconds))
    if seconds < 90:
        return f"{int(round(seconds))} seconds"
    minutes = int(round(seconds / 60.0))
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


async def _aclose_quietly(iterator) -> None:
    """Close a half-consumed async iterator without letting cleanup mask the
    reason we are closing it."""
    aclose = getattr(iterator, "aclose", None)
    if aclose is None:
        return
    try:
        await aclose()
    except Exception:  # noqa: BLE001 — the ceiling is the story; cleanup is not
        logger.warning("turn-ceiling: closing the stalled stream failed", exc_info=True)


async def _bounded_turn_stream(stream, *, started_at: float, ceiling_s: float):
    """DQ-T56(1) — **THE ONE CHOKEPOINT.** Yield a turn's chunks, and raise
    `TurnCeilingExceeded` once the turn as a whole has run past `ceiling_s`.

    It belongs here and nowhere else because `_emit_chat_turn` consumes the
    provider through exactly ONE `async for` — both branches (`_stream_with_tools`
    and `_stream_via_gateway`) funnel into it, and both the fresh turn and the
    resume path delegate to `_emit_chat_turn`. So every provider await a turn can
    make passes through this loop, and bounding it here bounds all of them.

    🔴 **THE BOUND IS ON THE AWAIT, NOT ON THE CHUNK, AND THAT IS THE WHOLE
    DESIGN.** The failure this closes is a provider that goes SILENT — measured
    live as one pass advertised, then three minutes of nothing. A deadline checked
    when a chunk arrives never runs, because no chunk arrives. So `remaining` is
    computed before each `__anext__` and imposed ON it.

    The clock starts at the turn's `stream_start`, so time the CONSUMER spends
    between chunks is charged to the turn too — which is correct for a ceiling on
    the turn *as a whole*, and is the difference between this and an idle cap.

    `ceiling_s <= 0` passes chunks straight through, so disabling it restores the
    previous behaviour exactly rather than approximately.
    """
    if not ceiling_s or ceiling_s <= 0:
        async for item in stream:
            yield item
        return

    iterator = stream.__aiter__()
    while True:
        remaining = ceiling_s - (_time.monotonic() - started_at)
        if remaining <= 0:
            await _aclose_quietly(iterator)
            raise TurnCeilingExceeded(_time.monotonic() - started_at, ceiling_s)
        try:
            item = await asyncio.wait_for(iterator.__anext__(), remaining)
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError:
            # `wait_for` has already cancelled the pending `__anext__`, which
            # unwinds the tool loop and releases the provider connection.
            await _aclose_quietly(iterator)
            raise TurnCeilingExceeded(_time.monotonic() - started_at, ceiling_s) from None
        yield item


async def _emit_chat_turn(
    *,
    session_id: str,
    user_message_content: str,
    user_id: str,
    model_source: str,
    model_ref: str,
    creds: ProviderCredentials,
    pool: asyncpg.Pool,
    billing: BillingClient,
    parent_message_id: str | None,
    project_id: str | None,
    stream_format: str,
    editor_context: dict | None,
    messages: list[dict],
    gen_params: dict,
    tool_defs: list[dict],
    use_tools: bool,
    knowledge_client,
    admin_token: str | None = None,
    fe_memory_mode: str | None,
    msg_id: str,
    seed_usage: tuple[int, int] | None,
    composer_model: tuple[str, str] | None = None,
    composer_system_prompt: str | None = None,
    planner_model_ref: str | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    discovery_catalog: list[dict] | None = None,
    discovery_extra_frontend: list[dict] | None = None,
    discovery_seed_names: set[str] | None = None,
    curated: bool = False,
    activation_state: dict | None = None,
    surface_tracker=None,
    injected_skills: list[str] | None = None,
    effective_enabled_count: int = 0,
    hot_seed_count: int = 0,
    permission_mode: str = "write",
    pre_tool_chunks: list[dict] | None = None,
    context_breakdown: ContextBreakdown | None = None,
    entity_presence: dict | None = None,
    trace: "TraceAccumulator | None" = None,
    is_resume: bool = False,
    # WS-4C Half A — the turn-scoped facts post-turn canon capture needs (resolved book id,
    # the project's toggle, the turn's grounding flag). Resolved in stream_response; None on
    # the RESUME path, which rebuilds no knowledge context — capture then fails CLOSED.
    canon_capture_ctx: "CaptureContext | None" = None,
    # S02 fix — the session's already-resolved {book_id, chapter_id, project_id} (from
    # editor/book/studio context in stream_response). Only editor_context is otherwise
    # threaded here, so a BOOK-scoped surface's book_id would be invisible to arg-injection
    # without this. Falls back to editor_context when absent (the resume caller).
    context_ids: dict | None = None,
    # WS-2b — curated workflows visible this turn; threaded into the tool loop so
    # workflow_list/workflow_load are advertised + dispatched. Empty on the resume caller.
    turn_workflows: list[dict] | None = None,
    # WS-3 — the PINNED rail's step tools, so the SUSPEND path can persist them.
    pinned_step_tools: list[str] | None = None,
    # P-1 step-runner — the pinned rails' (slug, steps) + the turn-start probe/grant, threaded
    # to the tool loop so it can DRIVE the rail within the turn. Empty on the resume caller.
    rail_specs: list[tuple] | None = None,
    rail_grant_ok: bool = False,
    rail_turn_start_counts=None,
    rail_async_tools: frozenset[str] = frozenset(),
    rail_in_flight: bool = False,
    # Action-space gating — turn-start RailProgress objects for the pinned rails (parallel to
    # rail_specs); forwarded to the tool loop's advertise chokepoint. None on the resume caller.
    rail_progress: list | None = None,
    # D-FJ-17 — the rails THIS turn's user message pinned, forwarded so the stalled-write
    # nudge cannot drag the turn onto an unrelated rail's outstanding step.
    rail_intent_slugs: frozenset[str] = frozenset(),
    #: D-FJ-21 / D-FJ-22 — the other two turn-ownership inputs (see _stream_with_tools).
    rail_stuck_tools: frozenset[str] = frozenset(),
    # R1 — this turn's request, so the advertise chokepoint can guarantee that a tool whose
    # own declared vocabulary answers it reaches the wire. Empty ⇒ inert.
    request_text: str = "",
    rail_named_tools: frozenset[str] = frozenset(),
) -> AsyncGenerator[str, None]:
    """Shared Stream→persist→finish body for a chat turn (fresh OR C6 resume).

    Consumes chunks from the LLM (tool loop or plain), emits AG-UI/legacy events,
    persists the assistant message, and runs post-turn best-effort work. When the
    tool loop yields a ``suspend`` chunk (a frontend tool awaiting client
    execution), this persists the suspended run instead and emits a "suspended"
    finish — NO assistant message is written (the turn isn't done yet).

    RAID C2: ``pre_tool_chunks`` — tool_call chunks a resume path already
    executed BEFORE re-entering the loop (an approved Tier-A tool). Emitted +
    persisted here so the FE sees the tool_call/activity events with full
    C-ACTIVITY parity (approval is additive; undo unchanged)."""
    full_content: list[str] = []
    full_reasoning: list[str] = []
    tool_calls_history: list[dict] = []
    # CP-3 — bound at the TOP of the turn, not inside the branch that fills them. The branch is
    # nested and the persistence site is not, so a turn that took any other path reached the
    # persistence block with `_plan_turn` unbound and raised `UnboundLocalError` — caught by 11
    # existing stream tests, which is the reason the initialisation lives up here.
    _plan_turn = None
    _plan_events: list = []
    # CP-0.1/0.2 — the turn's instrument. Created here, at the top of the turn, because a recorder
    # created lazily at the first advertise would miss a turn that was narrowed to nothing before
    # the model ever saw a surface — which is precisely the case worth catching.
    _advertised = instrument.AdvertisedToolsRecorder()
    _loop_finish_reason: str | None = None  # CP-0.4 — the loop's own terminal reason
    # CP-0.2 — arm the request-scoped sink so narrowings decided OUTSIDE this function (surface
    # assembly, two frames up) still register. Drained into the recorder at each advertise.
    # ADOPT, never replace: surface assembly ran before this generator's body started and its
    # narrowings are already in the sink. Setting a fresh list here would discard exactly the
    # records this field exists to carry.
    _surface_sink = instrument.surface_withheld.get()
    if _surface_sink is None:
        _surface_sink = []
        instrument.surface_withheld.set(_surface_sink)
    # Bind it, so `withheld_json()` drains on EVERY terminal path rather than only on the one that
    # happens to advertise. Three of the four live turn shapes persisted `NULL` while the sink held
    # the row, because the drain lived behind an event a tool-free turn never emits.
    _advertised.bind_sink(_surface_sink)
    # W1 — advertised tool-schema tokens, reported once by the tool loop's
    # first pass ({"schema_tokens": ...} chunk); folded into the contextBudget
    # frame + the persisted context_breakdown at finish.
    _fe_schema_tok = 0
    _mcp_schema_tok = 0
    last_usage = None
    _llm_call_count = 1  # observability fix #5 — provider completions this turn
    _final_response_id: str | None = None  # P2 §5 — stateful chain head to persist
    _ctx_size: int = 0  # P3 §9 — true single-call context size (window-boundary guard)
    import time as _time
    stream_start = _time.monotonic()
    time_to_first_token: float | None = None
    # C6: set when the tool loop suspends on a frontend tool.
    suspend_state: dict | None = None

    # ARCH-1 C3: select the wire-event serializer for this request.
    emitter = make_emitter(stream_format, thread_id=session_id, message_id=msg_id)

    # AG-UI requires a RUN_STARTED before any other event (no-op in legacy mode).
    for line in emitter.open_run():
        yield line

    # K-CLEAN-5: emit memory_mode first (skipped on resume — the FE already has
    # it from run 1, so fe_memory_mode is None there).
    if fe_memory_mode is not None:
        for line in emitter.memory_mode(fe_memory_mode):
            yield line

    if surface_tracker is not None:
        payload = surface_tracker.curated(
            pinned_count=effective_enabled_count,
            hot_seed_count=hot_seed_count,
            activated_count=len(activation_state["activated_tools"]) if activation_state else 0,
        )
        if payload is not None:
            for line in emitter.agent_surface(payload):
                yield line
        payload = surface_tracker.skill_injected(injected_skills or [])
        if payload is not None:
            for line in emitter.agent_surface(payload):
                yield line

    # RAID C2 — a resume path may have executed an approved Tier-A tool before
    # re-entering the loop: surface those calls (tool_call + activity events)
    # and record them for the persisted tool_calls history.
    for _pre_tc in (pre_tool_chunks or []):
        tool_calls_history.append(_pre_tc)
        for line in emitter.tool_call(_pre_tc):
            yield line
        _pre_activity = _pre_tc.get("activity")
        if _pre_activity is not None:
            for line in emitter.activity(_pre_activity):
                yield line

    # RAID Wave A4 — provider-agnostic compaction: keep the assembled prompt under the
    # model's window BEFORE sending (works for local lm_studio/Qwen/Gemma AND Claude; the
    # Anthropic server-side overlay is A5). GUARDED — any error falls back to the
    # un-compacted messages so a bug here can never break the turn. summarize=None →
    # deterministic micro-evict of tool results + hard-truncate (no LLM in the path).
    # T3.2 — the Context Budget **Planner** (POLICY) computes the compaction plan for THIS
    # turn: a grounding turn (lore/continuity/discovery/anaphora) stays roomy (task_weight
    # 1.0 → surface_max); a status-op / smalltalk turn uses the leaner
    # `compact_light_task_weight` so it compacts sooner. grounding_needed rides in via the
    # T5 `entity_presence` telemetry (the EntityPresence object lives in the caller
    # stream_response); missing/None → True (roomy/safe, biased-to-include). When the flag
    # is OFF the plan's target is None → compaction keeps the flat 0.75×window trigger
    # (byte-identical pre-T2). Swap `_PLANNER` (or its `plan`) to A/B a compaction policy;
    # its safety net when ON is the D6 recovery layer (breadcrumb + summary + story_state).
    _plan = _PLANNER.plan(
        grounding_needed=bool((entity_presence or {}).get("grounding_needed", True)),
        context_length=creds.context_length,
        task_elastic_enabled=settings.compact_task_elastic_enabled,
        light_task_weight=settings.compact_light_task_weight,
    )
    _compact_target = _plan.compact_target

    _eff_limit: int | None = None
    _compaction = None
    try:
        _eff_limit = compute_budget(
            used_tokens=0,
            context_length=creds.context_length,
            max_output_tokens=int(gen_params.get("max_tokens") or 0),
        ).effective_limit
        if _eff_limit:
            async def _summarizer(_middle: list[dict]) -> str:
                # tier 2 runs the session's OWN model to compress the old turns.
                return await _summarize_for_compaction(
                    _middle, model_source=model_source, model_ref=model_ref, user_id=user_id,
                )
            messages, _compaction = await compact_messages(
                messages, effective_limit=_eff_limit,
                target=_compact_target, summarize=_summarizer,
                add_breadcrumb=settings.compact_breadcrumb_enabled,
                collapse_duplicates=settings.compact_collapse_duplicates_enabled,
            )
            # T6/D6 — when compaction summarized/dropped earlier turns THIS turn, inject
            # the recovery hint so the model reaches for conversation_search to pull back a
            # specific fact the lossy summary may have dropped, instead of guessing/omitting
            # (the "net built but unused" gap the T2 light-target A/B found). Placed right
            # after the leading pinned/system block (incl. the <summary>) so it reads as
            # guidance about that summary.
            if settings.compact_recovery_hint_enabled and _compaction.did_work:
                inject_recovery_hint(messages)
            if _compaction.triggered:
                logger.info(
                    "compaction fired session=%s steps=%s tokens %d→%d overflow=%s",
                    session_id, _compaction.steps,
                    _compaction.tokens_before, _compaction.tokens_after,
                    _compaction.overflowed,
                )
            # Context Compiler trace (§11) — the in-turn ephemeral compaction span.
            # delta = tokens_after − tokens_before (negative = SAVED), folded into raw_tokens.
            if trace is not None and _compaction.did_work:
                trace.add(
                    "compiler", "T6", "history",
                    f"ephemeral compaction ({_compaction.steps} step(s)) "
                    f"{_compaction.tokens_before}→{_compaction.tokens_after} tok"
                    + (" · overflow" if _compaction.overflowed else ""),
                    delta=int(_compaction.tokens_after - _compaction.tokens_before),
                    is_error=bool(_compaction.overflowed),
                )
    except Exception:  # never let compaction break the turn
        logger.warning("compaction skipped (error)", exc_info=True)
    # W1 — surface pre-send compaction to the client when it DID something
    # (previously log-only). Outside the guard try so a consumer-side throw
    # is never mis-swallowed as a compaction error.
    if _compaction is not None and _compaction.did_work:
        for line in emitter.compaction(_compaction.to_event()):
            yield line

    turn_succeeded = False
    post_finish_state: dict | None = None
    # DBT-CHAT-PERSIST — flips True once the assistant row is durably written (the
    # clean-finish INSERT below OR a terminal-path write). Guards the error/interrupt
    # handlers from double-persisting a turn that already saved.
    _persisted = False
    # DBT-CHAT-PERSIST — monotonic timestamp of the last in-turn checkpoint (0 = none
    # yet), used to throttle tool-boundary checkpoints.
    _last_checkpoint = 0.0

    # RAID C2 (DR-C2 §4) + Track D S-SPEND — the per-user allowlist read, handed to
    # the loop as a callable so _stream_with_tools stays DB-free. ``kind`` selects the
    # consent axis ("mutation" | "spend"); each is a separate row. The loop decides
    # how to degrade on a read error (mutation fails OPEN, spend fails CLOSED).
    # Track C WS-3 — returns the standing DECISION ('allow' | 'deny' | None), so ONE
    # read answers both "may it run?" and "has the user forbidden it?".
    # R5 — the mood of THIS request is a consent input. Computed once, from the user's own
    # words, by a literal matcher (see request_mood); `unknown` is the default and behaves
    # exactly as before.
    _turn_mood = request_mood(user_message_content)

    # 🔴 `unknown` MOOD LET A WEEKS-OLD WRITE GRANT APPLY TO A PLAIN QUESTION — THE MATCHER'S
    # FAIL-OPEN DEFAULT. R5 above is right and it works when it fires: "How far along is the
    # translation for this book?" is read `inspect` and the standing grant is set aside. But
    # `request_mood` is a literal matcher over phrasings, and two measured questions fell through
    # it to `unknown`, which lets the grant stand:
    #
    #     "Who is Mira Solene?"                          -> unknown -> grant APPLIES
    #     "What canon rules have I declared for this book?" -> unknown -> grant APPLIES
    #
    # Both were measured reaching for Tier-A WRITES on 3 of 3 runs (glossary_entity_set_attributes,
    # kg_project_create). The harness clears standing approvals, which is the only reason those
    # surfaced as cards instead of writes; the dogfood account holds 46 of them.
    #
    # Widening the phrase list would fix those two sentences and leave the class — the next
    # unrecognised question is the next incident. So the second signal is the platform's OWN
    # DECLARATION, the same one R1 already trusts to decide the surface: if every tool whose
    # declared vocabulary matches this request is a READ, the request's own words say it is a
    # question, whatever the mood matcher made of the phrasing. It is not a guess and there is no
    # list here to rot.
    #
    # Narrow by construction: EMPTY matches nothing (chitchat is unchanged), and a single matched
    # WRITE stands the whole thing down — "Add a chapter called X" matches the CREATE tools and
    # keeps its grant exactly as before.
    _cat_by_name = _catalog_index(list(discovery_catalog or []))
    _turn_answerable = answerable_tools(user_message_content, list(discovery_catalog or []))
    _turn_reads_only = bool(_turn_answerable) and all(
        n in _cat_by_name and tool_tier(_cat_by_name[n]) == "R" for n in _turn_answerable
    )

    async def _decision_check(tool_name: str, kind: str = "mutation") -> str | None:
        """The standing decision, moderated by what this turn actually asked for.

        🔴 MEASURED 5/5, 2026-08-13: asked "Show me the outline I've planned for this book",
        the turn called composition_outline_node_edit (Tier A) and CREATED three chapters.
        The store went from 7 outline nodes to 10. No card was shown, because a standing
        "always allow" from 2026-07-30 — granted two weeks earlier while the author was
        genuinely building — still applied.

        A consent granted while asking a tool to WRITE is not consent for a turn that asked
        to LOOK. On an unambiguous inspect turn the standing mutation grant is set aside and
        the Tier-A gate does its job: the call is not blocked, it is ASKED. A deny is never
        set aside — a standing refusal must hold in every mood.
        """
        _decision = await get_tool_decision(pool, user_id, tool_name, kind)
        if _decision != "allow":
            # A DENY is never set aside — a standing refusal must hold in every mood.
            return _decision
        _mood_ok = standing_grant_applies(_turn_mood, kind=kind)
        # The declaration arm covers what the phrasing matcher missed, and only for MUTATION:
        # `spend` already fails closed, and widening a second axis on this evidence would be
        # asserting more than was measured.
        _reads_only_block = kind == "mutation" and _turn_reads_only
        if _mood_ok and not _reads_only_block:
            return _decision
        # WARNING, not info: setting aside a consent the author explicitly granted is a
        # security-relevant event, and its absence from the log is what made this fix
        # unverifiable for a whole measurement cycle — INFO was not being emitted, so "no line"
        # meant nothing. An operator must be able to see WHY a card appeared for a tool they
        # had allowed.
        logger.warning(
            "standing %s grant for %s set aside — this turn asked to LOOK, not to change "
            "(mood=%s, answerable-are-all-reads=%s: %s) — the Tier-A gate will raise a card",
            kind, tool_name, _turn_mood, _turn_reads_only, sorted(_turn_answerable) or "—",
        )
        return None

    # P4 REG-P4-03 — resolve the user's declarative hooks once per turn (degrade-safe
    # []). pre_turn inject_text hooks are folded into the system prompt now (steering
    # style); pre_tool_call deny/require_approval are evaluated inside the loop.
    _turn_hooks: list[dict] = []
    try:
        from app.client.registry_hooks_client import get_hooks_client
        from app.services.hook_engine import collect_injections

        _turn_hooks = await get_hooks_client().get_hooks(str(user_id), book_id=str(project_id or ""))
        _pre_injections = collect_injections(_turn_hooks, "pre_turn")
        if _pre_injections and messages:
            # Insert as a just-in-time system directive immediately BEFORE the final
            # (user) message — higher salience than folding into a large system prompt.
            _inj = {"role": "system", "content": "\n".join(_pre_injections)}
            _pos = len(messages) - 1 if messages[-1].get("role") == "user" else len(messages)
            messages.insert(_pos, _inj)
    except Exception:  # noqa: BLE001 — hooks are a guardrail, never load-bearing
        logger.warning("hook resolution failed (unhooked turn)", exc_info=False)

    # P5 REG-P5-01 — resolve the user's + book's enabled subagent personas once per
    # turn (degrade-safe []). When ≥1 exists, advertise `run_subagent` (a closed-set
    # enum of their names) so the model can delegate a bounded sub-task to a scoped,
    # isolated nested turn. Resolved HERE (in the shared body) so BOTH the fresh and
    # the resume path get it. The tool routes through _stream_with_tools even when no
    # other tools are on (a subagents-only surface still needs the loop).
    _subagent_defs_map: dict[str, dict] = {}
    _subagent_tool: dict | None = None
    try:
        from app.client.registry_subagents_client import get_subagents_client

        _subs = await get_subagents_client().get_subagents(
            str(user_id), book_id=str(project_id or "")
        )
        # First-seen wins — the resolver already shadowed by tier, so its order is
        # authoritative; dedup defensively.
        for _sa in _subs:
            _subagent_defs_map.setdefault(_sa["name"], _sa)
        _subagent_tool = build_run_subagent_tool(list(_subagent_defs_map.keys()))
    except Exception:  # noqa: BLE001 — a capability, never load-bearing
        logger.warning("subagent resolution failed (no delegation)", exc_info=False)

    # Chain-decision defaults — read UNCONDITIONALLY later (the `_caching` frame at
    # the bottom of this function) regardless of which branch below runs, so both
    # must see them. The plain-gateway (`else`) branch below never had its own
    # stateful/chain logic (no tools → nothing to decide), so without this hoisted
    # default it left `_chain_reason` etc. unbound — an UnboundLocalError on every
    # non-tool-calling turn (review-impl catch, 2026-07-06).
    _stateful, _prev_rid, _delta_msgs, _chain_reason = False, None, None, "stateless"
    try:
        # D-RESUME-TOOLS-DROPPED (found 2026-07-07, live-repro'd) — the stateful-
        # chain decision and "does this turn use _stream_with_tools at all" are
        # two SEPARATE questions that a single combined condition here used to
        # conflate: `if (use_tools or ...) and not is_resume:` skipped BOTH the
        # chain decision AND the entire _stream_with_tools call on every resume,
        # silently falling to the plain no-tools `_stream_via_gateway` path even
        # when a resumed turn genuinely has tools to offer (e.g. re-advertising
        # `propose_edit` after a frontend-tool suspend, or with no project so no
        # memory tools) — exactly the regression `resume_stream_response`'s own
        # comment two screens up describes fixing, silently re-broken by this
        # gate. Only the INNER chain-decision sub-block may skip on resume.
        if use_tools or _subagent_tool is not None:
            if not is_resume:
                # P3 review H1 — a RESUME runs STATELESS over the full saved working
                # (the suspend reconstructed the complete context). A delta rebuild
                # here would drop the assistant tool_call + the frontend tool result
                # the resume appended → the model would never see the tool outcome
                # (re-suspend loop). The resumed turn persists response_id=None, so
                # the NEXT turn cleanly re-establishes the chain (rule-1).
                #
                # ── Stateful /v1/responses chain decision (P2 §5a) ──────────────
                # Read the latest assistant turn for this session/branch and decide:
                # stateless / stateful-establish / stateful-continue. Degrade-safe —
                # any error falls back to stateless (full context). Only build the
                # delta when continuing from a valid head (system blocks carry the
                # fresh grounding → the gateway lifts them to `instructions`; the
                # user turn is the input).
                try:
                    _latest_asst = await pool.fetchrow(
                        """
                        SELECT response_id, model_ref::text AS model_ref, input_tokens, sequence_num,
                               (context_breakdown->'caching'->>'context_size')::int AS context_size
                        FROM chat_messages
                        WHERE session_id=$1 AND role='assistant' AND branch_id=0
                        ORDER BY sequence_num DESC LIMIT 1
                        """,
                        session_id,
                    )
                    _comp_seq = await pool.fetchval(
                        "SELECT compacted_before_seq FROM chat_sessions WHERE session_id=$1",
                        session_id,
                    )
                    _eff = compute_budget(
                        used_tokens=0,
                        context_length=creds.context_length,
                        max_output_tokens=int(gen_params.get("max_tokens") or 0),
                    ).effective_limit
                    _stateful, _prev_rid, _chain_reason = decide_chain(
                        capabilities=getattr(creds, "capabilities", None),
                        latest_assistant=dict(_latest_asst) if _latest_asst else None,
                        current_model_ref=str(model_ref),
                        compacted_before_seq=_comp_seq,
                        effective_limit=_eff,
                    )
                    if _stateful and _prev_rid:
                        _last_user = next(
                            (m for m in reversed(messages) if m.get("role") == "user"), None
                        )
                        _delta_msgs = [m for m in messages if m.get("role") == "system"]
                        if _last_user is not None:
                            _delta_msgs.append(_last_user)
                except Exception:
                    logger.warning("stateful chain decision skipped — stateless", exc_info=True)
                    _stateful, _prev_rid, _delta_msgs, _chain_reason = False, None, None, "stateless"

            # ── CP-3 · THE REQUEST PATH · resume half ──────────────────────────────────────
            # 🔴 **ARM-GATED, AND THE OFF BRANCH TOUCHES NOTHING.** The legacy arm is CP-2's
            # control group (§7), and CP-1.9 established that a control moved by a change nobody
            # decided invalidates the comparison before it starts. With the flag off, `messages` is
            # the same object it was.
            #
            # S3-M4: a second message during a live plan ROUTES INTO IT. The plan is prepended as a
            # system message so the identifiers it carries are in front of the model BEFORE it
            # chooses a call — which is the whole claim: the conversation evicts them, the plan does
            # not.
            if settings.agentruntime_arm:
                from app.services.plan_turn import live_plan_for_turn, plan_message
                _plan_turn = await live_plan_for_turn(pool, session_id)
                if _plan_turn is not None:
                    messages = [plan_message(_plan_turn), *messages]
                    logger.info(
                        "CP-3 request path: session %s routed into live plan %s (%d step(s), "
                        "%d event(s), resume=%s)",
                        session_id, _plan_turn.plan_id, len(_plan_turn.spec.steps),
                        len(_plan_turn.state.events), _plan_turn.is_resume,
                    )

            chunk_stream = _stream_with_tools(
                plan_turn=_plan_turn,
                plan_events_out=_plan_events,
                model_source=model_source,
                model_ref=model_ref,
                user_id=user_id,
                messages=messages,
                gen_params=gen_params,
                tools=tool_defs,
                knowledge_client=knowledge_client,
                session_id=session_id,
                project_id=project_id,
                seed_usage=seed_usage,
                composer_model=composer_model,
                composer_system_prompt=composer_system_prompt,
                planner_model_ref=planner_model_ref,
                max_iterations=max_iterations,
                admin_token=admin_token,
                # S02 fix — hand the already-resolved context-ids down so backend tool args
                # get them filled server-side. Use the dict stream_response resolved (book/
                # studio-aware); fall back to editor_context alone (the resume caller passes none).
                context_ids=context_ids or {
                    "book_id": (editor_context or {}).get("book_id"),
                    "chapter_id": (editor_context or {}).get("chapter_id"),
                    # str(): project_id here is session_row["project_id"], a uuid.UUID from
                    # asyncpg — keep it a string identifier (mirrors the sibling dict at ~4988
                    # and the _inject_context_ids coercion) so it stays JSON-serializable.
                    "project_id": str(project_id) if project_id else None,
                },
                discovery_catalog=discovery_catalog,
                discovery_extra_frontend=discovery_extra_frontend,
                discovery_seed_names=discovery_seed_names,
                curated=curated,
                activation_state=activation_state,
                surface_tracker=surface_tracker,
                effective_limit=_eff_limit,
                compact_target=_compact_target,
                context_length=creds.context_length,
                permission_mode=permission_mode,
                decision_check=_decision_check,
                hooks=_turn_hooks,
                subagent_tool=_subagent_tool,
                subagent_defs=_subagent_defs_map,
                trace=trace,
                stateful=_stateful,
                previous_response_id=_prev_rid,
                delta_messages=_delta_msgs,
                turn_workflows=turn_workflows,
                # P-1 step-runner — drive the pinned rail within this turn. book_id comes from
                # the same context_ids the arg-injection uses (book-scoped surfaces set it).
                rail_specs=rail_specs or None,
                rail_book_id=(context_ids or {}).get("book_id"),
                rail_grant_ok=rail_grant_ok,
                rail_turn_start_counts=rail_turn_start_counts,
                rail_async_tools=rail_async_tools,
                rail_in_flight=rail_in_flight,
                rail_user_abandoned=user_abandoned_rail(user_message_content),
                rail_progress=rail_progress,
                rail_intent_slugs=rail_intent_slugs,
                rail_stuck_tools=rail_stuck_tools,
                request_text=request_text,
                rail_named_tools=rail_named_tools,
            )
        else:
            chunk_stream = _stream_via_gateway(
                model_source=model_source,
                model_ref=model_ref,
                user_id=user_id,
                messages=messages,
                gen_params=gen_params,
            )

        # DQ-T56(1) — the whole-turn ceiling wraps the ONE place a turn awaits the
        # provider. `stream_start` is the turn's own clock, set before the first
        # emitted line, so the bound covers every pass of the tool loop and not
        # just the pass that happens to be running.
        async for chunk_data in _bounded_turn_stream(
            chunk_stream,
            started_at=stream_start,
            ceiling_s=settings.llm_turn_ceiling_s,
        ):
            # ARCH-1 C6: a suspend chunk — a frontend tool is awaiting client
            # execution. Capture it, stop consuming, and handle below.
            if chunk_data.get("suspend") is not None:
                suspend_state = chunk_data["suspend"]
                break
            # K21-B: a tool_call chunk → record it for persistence + emit
            # the SSE indicator. It carries no text/usage, so skip the rest.
            tool_call = chunk_data.get("tool_call")
            if tool_call is not None:
                tool_calls_history.append(tool_call)
                for line in emitter.tool_call(tool_call):
                    yield line
                # MCP-fanout C-ACTIVITY (H16) — a Tier-A auto-write attaches an
                # `activity` block to its tool_call chunk; surface it as the
                # visible "agent did X · Undo" strip.
                activity = tool_call.get("activity")
                if activity is not None:
                    for line in emitter.activity(activity):
                        yield line
                # DBT-CHAT-PERSIST — checkpoint the turn's progress at this tool
                # boundary so a later error/interrupt/abandon can't lose the work
                # already done (the reported failure: a long tool-loop turn that
                # produced a card, then died before the clean finish). Throttled
                # + upserts by msg_id; the clean finish overwrites 'streaming' →
                # 'stop'. Best-effort — _persist_terminal_assistant never raises.
                _now_ckpt = _time.monotonic()
                if _now_ckpt - _last_checkpoint >= _CHECKPOINT_MIN_INTERVAL_S:
                    _last_checkpoint = _now_ckpt
                    # NB: do NOT set _persisted — the turn isn't finished. The row
                    # now exists, but the terminal/clean-finish handlers must still
                    # UPDATE it (upsert by msg_id) to the final finish_reason.
                    await _persist_terminal_assistant(
                        pool,
                        msg_id=msg_id, session_id=session_id, user_id=user_id,
                        parent_message_id=parent_message_id, model_ref=model_ref,
                        content="".join(full_content),
                        reasoning="".join(full_reasoning),
                        tool_calls_history=tool_calls_history or None,
                        finish_reason="streaming", is_error=False, error_detail=None,
                        # CP-0.4 — a mid-turn checkpoint records `crashed` PESSIMISTICALLY. If the
                        # process dies now, this is what the row keeps, and that is the correct
                        # reading: nothing else will ever run to correct it. The clean finish and
                        # every terminal handler overwrite it. The failure mode this avoids is the
                        # opposite default — a checkpoint that writes 'completed' optimistically and
                        # leaves a dead turn looking successful, which is the one shape of wrongness
                        # nobody ever investigates.
                        outcome=instrument.OUTCOME_CRASHED,
                        advertised_tools=_advertised.advertised_json(),
                        withheld_tools=_advertised.withheld_json(),
                    )
                continue
            # CP-0.1/0.2 — one entry per model pass, appended. This chunk carries no user-visible
            # payload and emits no SSE line: it exists so the record of what the model was holding
            # survives the turn, which is the one thing no column answers today.
            _adv_ev = chunk_data.get("advertised")
            if _adv_ev is not None:
                _advertised.record_pass(
                    _adv_ev.get("names") or [],
                    tool_choice=_adv_ev.get("tool_choice"),
                )
                # Drain the request-scoped sink HERE so assembly-time narrowings are stamped with
                # the pass they belong to. `withheld_json()` drains again on every terminal path —
                # this call is for the pass number, not for the delivery, because a turn that never
                # advertises never reaches this line and is exactly the turn a catalogue outage
                # produces. See `AdvertisedToolsRecorder.absorb`.
                _advertised.absorb(_surface_sink)
                # 🔴 ONE DISPATCH, NOT TWO. This branch handled `pass` and the legacy `"*"` and
                # **not `catalogue`** — a second dispatch over the same enum, drifting from the
                # first the moment a scope was added. Latent only because no catalogue row travels
                # this channel today, which is exactly what "latent" meant about the P0 as well.
                # Routed through the recorder's own `absorb`, so there is one place that knows the
                # enum.
                _legacy = [
                    {**_w, "scope": instrument.SCOPE_PASS} if _w.get("tool") == "*" else _w
                    for _w in (_adv_ev.get("withheld") or [])
                ]
                _advertised.absorb(_legacy)
                continue
            # CP-0.4 / F-17 — the loop REPORTS its terminal reason and this consumer was dropping
            # it on the floor. I had recorded "the signal does not exist here"; one grep showed it
            # arrives on every content chunk and no code reads it. Captured now so the outcome is
            # DERIVED from what the loop said, instead of a constant asserting success.
            if chunk_data.get("finish_reason"):
                _loop_finish_reason = chunk_data["finish_reason"]
            # W1 — tool-schema token measurement from the loop's first pass.
            schema_tokens = chunk_data.get("schema_tokens")
            if schema_tokens is not None:
                _fe_schema_tok = int(schema_tokens.get("frontend_tool_schemas", 0))
                _mcp_schema_tok = int(schema_tokens.get("mcp_tool_schemas", 0))
                continue
            # W1 — in-loop (mid-turn) compaction did work → surface it.
            compaction_ev = chunk_data.get("compaction")
            if compaction_ev is not None:
                for line in emitter.compaction(compaction_ev):
                    yield line
                continue
            # A2A phase-2: composer drafting on/off → transient UI indicator.
            composing = chunk_data.get("composing")
            if composing is not None:
                for line in emitter.composing(composing["active"]):
                    yield line
                continue
            agent_surface = chunk_data.get("agent_surface")
            if agent_surface is not None:
                for line in emitter.agent_surface(agent_surface):
                    yield line
                continue
            reasoning = chunk_data["reasoning_content"]
            content = chunk_data["content"]
            if chunk_data.get("usage"):
                last_usage = chunk_data["usage"]
            if chunk_data.get("llm_call_count") is not None:
                _llm_call_count = chunk_data["llm_call_count"]
            # Stateful (P2 §5) — the turn's chain head to persist on the assistant row.
            if chunk_data.get("response_id"):
                _final_response_id = chunk_data["response_id"]
            # P3 §9 — the true single-call context size (accumulated server-side size),
            # for the window-boundary guard (NOT the summed billing total).
            if chunk_data.get("context_size"):
                _ctx_size = chunk_data["context_size"]

            # Track time to first token (reasoning or content)
            if time_to_first_token is None and (reasoning or content):
                time_to_first_token = (_time.monotonic() - stream_start) * 1000  # ms

            if reasoning:
                full_reasoning.append(reasoning)
                for line in emitter.reasoning_delta(reasoning):
                    yield line
            if content:
                full_content.append(content)
                for line in emitter.text_delta(content):
                    yield line

        # ARCH-1 C6: SUSPEND path — a frontend tool was called. Persist the
        # suspended run (so the resume request can rehydrate it) and emit the
        # pending tool-call events + a "suspended" finish. NO assistant message
        # is written; the logical turn completes on resume.
        if suspend_state is not None:
            run_id = str(uuid4())
            pending = suspend_state["pending_tool_call"]
            # P-1 — strip the step-runner's synthetic nudges before persisting: they are
            # ephemeral driver messages ("[SYSTEM DIRECTIVE …]"), never part of the real
            # conversation, and must not leak into the resumed context or history.
            _susp_working = [
                m for m in suspend_state["working"]
                if not (
                    m.get("role") == "user"
                    and isinstance(m.get("content"), str)
                    and m["content"].startswith("[SYSTEM DIRECTIVE")
                )
            ]
            await save_suspended_run(
                pool,
                run_id=run_id,
                session_id=session_id,
                owner_user_id=user_id,
                message_id=msg_id,
                working=_susp_working,
                pending_tool_call=pending,
                input_tokens=suspend_state["input_tokens"],
                output_tokens=suspend_state["output_tokens"],
                model_source=model_source,
                model_ref=model_ref,
                parent_message_id=parent_message_id,
                user_message_content=user_message_content,
                permission_mode=permission_mode,
                # WS-3 — carry the PINNED rail's tools across the suspend. The rail's TEXT
                # rides along for free (it's in the system message inside `working`), but
                # without this the resumed pass re-derives the tool surface with no book_id
                # to re-fetch the binding, and the agent reads a recipe naming tools it
                # cannot call. W6's first confirm gate is step 3 of 12.
                pinned_step_tools=pinned_step_tools,
                # P-1 — carry the rail's book so the resume can keep driving past the confirm.
                book_id=(context_ids or {}).get("book_id"),
                # TOOL DEEP-DIVE (2026-08-13) — and carry whether this was a STUDIO turn. The
                # book alone is not the same fact: a plain book-surface turn also has a book,
                # and the single-book override must not fire there.
                studio=bool((context_ids or {}).get("studio")),
                # TOOL DEEP-DIVE (2026-08-24) — and carry the OTHER TWO context ids, closing
                # the hole the note above opened by fixing only `studio`. `_crosswired_ids`
                # identifies a mis-wired id by exact match against the turn's OTHER ids, so
                # with chapter_id absent on the resume it has nothing to match: a chapter id
                # sent as `book_id` sails through and the book-scope check refuses it.
                # Measured (c-gbuild5): every run resumed through an approval card and on 4 of 4
                # failing calls the book_id EQUALLED that run's chapter_id — the author was told
                # "I'm having a technical issue accessing the book's database" and the writes
                # they asked for did not happen, on a book that was fine.
                chapter_id=(context_ids or {}).get("chapter_id"),
                project_id=(context_ids or {}).get("project_id"),
            )
            # DBT-CHAT-PERSIST — persist the reply produced UP TO the suspend as a
            # visible message NOW (prose so far + the completed tools + the pending
            # card), so a reload during the wait shows it and an abandoned/expired/
            # refused resume can't lose it — the exact reported failure. Reuses the
            # shared msg_id, so a successful resume UPSERTs this row to the final
            # 'stop' reply. finish_reason='awaiting_input' shows NO failure badge
            # (the card itself is the affordance); if the run is later abandoned the
            # resume-expired path flips it to 'interrupted'.
            # 🔴 **CP-5.5 — THE TURN ALREADY GOT THIS RIGHT AND THE CALL INSIDE IT DID NOT.**
            # Twelve lines below, `outcome=OUTCOME_AWAITING_INPUT` carries the note *"asking the
            # user is a SUCCESS state (§0.5), not a stall … counting it as a failure would score
            # the correct behaviour as the defect."* This record — the very call that did the
            # asking — was written `ok: False` with no message, so the lesson held at the turn
            # level and was inverted one field away.
            #
            # Measured: **all 41 of the "failures with no message" §1 files under the error
            # contract are these**, not one of them a tier-R read, and 38 sit in turns the human
            # never returned to. `stamp_deferred` makes the call say what the turn already says.
            _pending_record = instrument.stamp_deferred({
                "tool": pending.get("name"),
                # `ok` is retained UNCHANGED: the FE and the resume driver read it, and this row
                # is about adding the typed fact beside it, not about breaking every consumer to
                # deliver it. `call_outcome` is what a measurement reads from here on.
                "ok": False,
                "pending": True,
                "runId": run_id,
                "toolCallId": pending.get("id"),
                "args": pending.get("args"),
            })
            # ext-tasks (T1c(3.e)) — carry the durable-task info so a reload renders
            # the confirm card (title/preview from inputRequests). None for a normal
            # frontend-tool suspend (omitted below), so this is dormant there.
            if pending.get("task") is not None:
                _pending_record["task"] = pending["task"]
            await _persist_terminal_assistant(
                pool,
                msg_id=msg_id, session_id=session_id, user_id=user_id,
                parent_message_id=parent_message_id, model_ref=model_ref,
                content="".join(full_content),
                reasoning="".join(full_reasoning),
                tool_calls_history=[*tool_calls_history, _pending_record],
                finish_reason="awaiting_input", is_error=False, error_detail=None,
                # CP-0.4 — asking the user is a SUCCESS state (§0.5), not a stall. A model that
                # stops to ask when it does not know is doing the thing we want; counting it as a
                # failure would score the correct behaviour as the defect.
                outcome=instrument.OUTCOME_AWAITING_INPUT,
                advertised_tools=_advertised.advertised_json(),
                withheld_tools=_advertised.withheld_json(),
            )
            # close any open assistant/reasoning message first
            for line in emitter.close_message():
                yield line
            for line in emitter.tool_call_pending(pending):
                yield line
            finish = {"type": "finish-message", "finishReason": "tool_calls",
                      "usage": {"promptTokens": suspend_state["input_tokens"],
                                "completionTokens": suspend_state["output_tokens"]},
                      "timing": {}}
            # D-TOOLLOAD-LOST-ON-SUSPEND — the suspend is a real end-of-turn, so it owes
            # the same activation flush as a normal finish. Without it, the tools this
            # turn loaded to REACH the approval are gone by the time the author approves.
            await _flush_activated_tools(pool, session_id, activation_state)
            for line in emitter.finish(
                finish, status="suspended",
                pending={"runId": run_id, "toolCallId": pending["id"],
                         "toolName": pending["name"],
                         # ext-tasks (T1c(3.e)) — the FE reads pendingToolCall.task to
                         # render the confirm card; absent (None) for a normal suspend.
                         **({"task": pending["task"]} if pending.get("task") is not None else {})},
            ):
                yield line
            for line in emitter.done():
                yield line
            return

        # ARCH-1 C3: token stream is done — close the open assistant/reasoning
        # message so its END frames the content, before the run-level
        # persisted/finish events (no-op in legacy mode).
        for line in emitter.close_message():
            yield line

        response_time_ms = (_time.monotonic() - stream_start) * 1000
        final_text = "".join(full_content)
        final_reasoning = "".join(full_reasoning)

        # ── D-SILENT-TURN-NO-CARD-NO-PROSE ────────────────────────────────────────────────
        # A turn that produces no user-visible text is not a completed turn.
        #
        # MEASURED 2026-08-14 over 347 recorded runs: 21 turns across 8 tools ended with NO
        # prose, NO confirm card and no approval — composition_arc_get 5, glossary_curation_list
        # 3, plan_compile 3, jobs_get 3, translation_job_status 3, settings_model_delete 2,
        # jobs_list 1, memory_recall_entity 1. Every one was stored outcome='completed',
        # is_error=false, finish_reason='stop', so every count that reads outcomes saw a success
        # while the author saw an empty reply. The commonest trigger is a tool returning an
        # argument-repair message ("... is missing required argument(s) ... do NOT guess a
        # value"): the model reads it, declines to guess — correctly — and then says nothing.
        #
        # THE CONTROL, which is why this is scoped to `full_content` and not to "no tool
        # result": 113 of those 347 turns had no prose, but 92 SUSPENDED ON A CONFIRM CARD,
        # where the card IS the output and prose is legitimately absent. Those never reach this
        # site — the awaiting_input handler persists them — so this guard cannot see them, and
        # scoping it here rather than at a shared helper is what keeps the two apart.
        #
        # is_error is the seam the row model already has for this: `outcome_for_finish_reason`
        # takes it, so the outcome becomes `failed` while `finish_reason` keeps reporting
        # whatever the loop actually reported. That preserves F-19 — the two still derive from
        # one signal and the row does not contradict itself — while making the turn countable.
        # What this does NOT do is invent a reply; putting words in the assistant's mouth here
        # would be this loop's own "prose is not the lever" mistake in service code.
        _silent_turn = not final_text.strip()
        if _silent_turn:
            logger.warning(
                "silent turn: session=%s produced NO user-visible text with no confirm card "
                "after %d tool call(s) (last: %s) — recording outcome=failed, because a turn the "
                "author experiences as the product doing nothing is not a completion",
                session_id, len(tool_calls_history),
                tool_calls_history[-1].get("name") if tool_calls_history else None,
            )

        # ── CP-3 · THE REQUEST PATH · create half ──────────────────────────────────────────
        # A fenced ```plan block in the reply creates the session's plan, or revises it as a new
        # VERSION when one is live. Arm-gated, and outside the persist transaction below: adopting a
        # plan must never be able to lose the assistant message that proposed it.
        #
        # 🔴 **A REJECTION IS LOGGED WITH ITS LOCUS, NEVER SWALLOWED.** The worst outcome available
        # here is a model that believes it has a plan while the service has none — every later turn
        # then binds against a plan that does not exist, and the failure surfaces at a step nobody
        # can trace back to the parse.
        # CP-3 — persist what the executor observed, BEFORE any adoption can supersede the plan
        # those events belong to. A `step_emitted` written against a superseded plan is a fact
        # filed under the wrong version, which is the shape §0.11 splits SPEC and STATE to prevent.
        if _plan_turn is not None and _plan_events:
            try:
                from app.db import plans as _plan_db
                async with pool.acquire() as _pc:
                    for _ev in _plan_events:
                        await _plan_db.append_event(_pc, UUID(_plan_turn.plan_id), _ev)
                logger.info("CP-3 executor: persisted %d plan event(s) for %s",
                            len(_plan_events), _plan_turn.plan_id)
            except Exception:  # noqa: BLE001 — a plan must never cost the user their reply
                logger.warning("CP-3 plan event persistence failed", exc_info=True)

        _plan_adoption = None
        if settings.agentruntime_arm:
            from app.services.plan_turn import adopt_plan_from_reply
            try:
                _plan_adoption = await adopt_plan_from_reply(pool, session_id, final_text)
            except Exception:  # noqa: BLE001 — a plan must never cost the user their reply
                logger.warning("CP-3 plan adoption failed", exc_info=True)
            else:
                if _plan_adoption.rejected_with:
                    logger.warning(
                        "CP-3 request path: session %s proposed a plan that was REJECTED — %s",
                        session_id, _plan_adoption.rejected_with,
                    )
                elif _plan_adoption.adopted:
                    logger.info(
                        "CP-3 request path: session %s adopted plan %s v%d",
                        session_id, _plan_adoption.plan_id, _plan_adoption.version,
                    )

        # ── Persist assistant message ───────────────────────────────────────
        # K13.2: wrap the three INSERTs + outbox event in one transaction
        # so chat.turn_completed is only emitted when the message persists
        # successfully. Rollback on any error discards both the message and
        # the event.
        # DBT-11 — resolve the local day BEFORE the transaction: resolve_local_date can
        # hit auth on a cache miss, and holding this conn+transaction across an external
        # call would risk pool starvation on an auth hiccup.
        _local_date = await resolve_local_date(user_id)
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Branch-scoped like send_message/voice: after an edit re-branch,
                # a global MAX would jump the assistant PAST branched-away seqs
                # (and past a W3 compact boundary) while user messages stay low
                # — the review-impl H1 asymmetric-visibility bug.
                # D-AN-ABORTED-TURNS-DETACHED-WRITE-RACES-THE-RETRYS-SEQUENCE — this is the
                # DETACHED writer: an aborted turn's reply is persisted after cancel, and the
                # client's retry races it. One lock, held to COMMIT, covers both.
                seq = await next_sequence_num(conn, session_id)
                input_tok = getattr(last_usage, "prompt_tokens", None) if last_usage else None
                output_tok = getattr(last_usage, "completion_tokens", None) if last_usage else None

                # Store metadata in content_parts JSONB
                parts: dict = {}
                if final_reasoning:
                    parts["reasoning"] = final_reasoning
                    parts["reasoning_length"] = len(final_reasoning)
                parts["response_time_ms"] = round(response_time_ms)
                if time_to_first_token is not None:
                    parts["time_to_first_token_ms"] = round(time_to_first_token)
                content_parts = json.dumps(parts) if parts else None
                # K21-B: tool-call history for UI replay — NULL when the
                # turn made no tool calls.
                # CP-0.3 — the clean-finish chokepoint, the sibling of the one in
                # _persist_terminal_assistant. Both INSERT sites pass through it, so there is no
                # route from a mint site to the tool_calls column that skips the source stamp.
                tool_calls_json = (
                    json.dumps([
                        instrument.ensure_tool_call_instrumented(_tc)
                        for _tc in tool_calls_history
                    ])
                    if tool_calls_history else None
                )

                # ── W1: finalize the per-turn context frame payload ─────────
                # Fold the runtime-measured buckets (tool schemas from the
                # advertise chokepoint, this turn's tool RESULTS) into the
                # assembly-time breakdown, then build the ONE payload that is
                # both persisted (context_breakdown JSONB) and emitted as the
                # contextBudget CUSTOM frame below. Old keys stay byte-identical.
                # T0 review MED-1: meter the SAME bytes the model saw — through the
                # tool_result_content funnel (ensure_ascii=False + prune_none), NOT the
                # old raw json.dumps (ensure_ascii=True) which over-counts VI/CJK 2-3x +
                # counts dropped nulls. Else the attribution meter contradicts the L3 cut.
                # Meter the funnel (compiled) bytes AND the naive ensure_ascii=True /
                # no-prune bytes side-by-side, so the difference is the T0 wire-hygiene
                # saving (unicode-unescape + null-drop) — the one cut chat can measure locally.
                _tool_results_tok = 0
                _tool_results_raw_tok = 0
                for _tc in tool_calls_history:
                    _payload = _tc.get("result") if _tc.get("ok") else {"error": _tc.get("error")}
                    _tool_results_tok += estimate_tokens(tool_result_content(_payload))
                    _tool_results_raw_tok += estimate_tokens(
                        json.dumps(_payload, ensure_ascii=True, default=str)
                    )
                if context_breakdown is not None:
                    context_breakdown.categories["frontend_tool_schemas"] = _fe_schema_tok
                    context_breakdown.categories["mcp_tool_schemas"] = _mcp_schema_tok
                    context_breakdown.categories["tool_results"] = _tool_results_tok

                # ── Context Compiler trace (§11) — finalize the Inspector telemetry ──
                _tr = trace if trace is not None else TraceAccumulator()
                _wire_saved = _tool_results_raw_tok - _tool_results_tok
                if trace is not None and _wire_saved > 0:
                    _tr.add(
                        "compiler", "T0", "results",
                        "wire hygiene: serialize ensure_ascii=false + drop nulls",
                        delta=-_wire_saved,
                    )
                _trace_payload = _tr.to_payload()
                # D-CHAT-CONTEXT-METER-OVERCOUNT (2026-07-09): the context-budget
                # METER (used_tokens/raw_tokens below, what the GUI ContextMeter
                # renders) must show TRUE current occupancy — this turn's actual
                # context size — not input_tok, which is the SUM of input across
                # every completion in this turn's tool-loop (each iteration
                # re-sends the full prompt). That sum is real provider BILLING
                # (correctly kept as-is for chat_messages.input_tokens,
                # billing.log_usage, and the cache hit-rate math below, all of
                # which are legitimately sum-based) but is NOT how full the
                # context window is. Using it here made a 54-tool-call turn (30
                # completions) render "935,676 / 200,000 (469%)" on a real
                # single-call context size of 34K — a 27x inflation that scales
                # with llm_call_count, not with actual context pressure.
                # `_ctx_size` (P3 §9) is the true last-completion input size,
                # already tracked for the stateful chain's window-boundary guard;
                # fall back to input_tok only when it's genuinely unavailable
                # (no UsageEvent fired this turn, e.g. an all-cached resume).
                _occupancy_tok = _ctx_size if _ctx_size else int(input_tok or 0)
                _raw_tokens = _occupancy_tok + _tr.saved()
                _status_flags = derive_status_flags(
                    grounding_needed=(
                        entity_presence.get("grounding_needed")
                        if entity_presence else None
                    ),
                    compacted=any(s["tier"] == "T6" for s in _trace_payload),
                    elastic=(_plan.task_weight < 1.0),
                    overflowed=bool(_compaction is not None and _compaction.overflowed),
                    wire=(trace is not None and _wire_saved > 0),
                )
                # ── Prompt-cache monitoring section (§7–§8) ─────────────────
                # Build the per-turn caching metrics from this turn's cache split
                # (summed across the tool-loop) + the provider's declared caching
                # capabilities, then fold in the rolling thrashing verdict. Surfaced
                # on the frame + persisted so caching is PROVEN-BY-EFFECT, not silent.
                _caps = getattr(creds, "capabilities", None) or {}
                _cache_create = getattr(last_usage, "cache_creation_tok", 0) if last_usage else 0
                _cache_read = getattr(last_usage, "cache_read_tok", 0) if last_usage else 0
                _caching = build_caching_metrics(
                    cache_creation_tok=_cache_create,
                    cache_read_tok=_cache_read,
                    input_tok=int(input_tok or 0),
                    capabilities=_caps,
                )
                # Rolling thrashing verdict — only meaningful for explicit-cache
                # providers (auto-cache can't thrash → detect_thrashing returns None,
                # so skip the query entirely for local/OpenAI). Read the last few
                # persisted splits for this session and fold THIS turn in.
                _thrashing = None
                if _caps.get("prompt_cache_control"):
                    try:
                        _rows = await conn.fetch(
                            """
                            SELECT (context_breakdown->'caching'->>'create_tok')::int AS c,
                                   (context_breakdown->'caching'->>'read_tok')::int AS r
                            FROM chat_messages
                            WHERE session_id=$1 AND role='assistant' AND branch_id=0
                              AND context_breakdown ? 'caching'
                            ORDER BY sequence_num DESC LIMIT 5
                            """,
                            session_id,
                        )
                        _window = [(_cache_create, _cache_read)] + [
                            (row["c"], row["r"]) for row in _rows
                        ]
                        _thrashing = detect_thrashing(_window, capabilities=_caps)
                    except Exception:  # degrade-safe: monitoring never breaks a turn
                        _thrashing = None
                _caching["thrashing"] = _thrashing
                # P3 §9 — persist the true single-call context size (accumulated
                # server-side size in stateful mode) so the next turn's head-validity
                # window guard (§5a rule-4) reads it, NOT the summed tool-loop billing.
                if _ctx_size:
                    _caching["context_size"] = _ctx_size
                # P3 §9 — the chain action this turn (continue / establish_first /
                # reestablish_{stateless_prev,model_switch,compaction,window}), so a
                # re-chain is visible + attributable in the Inspector.
                _caching["chain_action"] = _chain_reason

                _ctx_payload = context_budget_event(
                    compute_budget(
                        used_tokens=_occupancy_tok,
                        context_length=creds.context_length,
                        max_output_tokens=int(gen_params.get("max_tokens") or 0),
                    ),
                    context_breakdown,
                    # T5 — the intent-gate decision for this turn (grounding_needed +
                    # matched tokens + reason), threaded in from the assembly path in
                    # stream_response. None on the resume/degraded paths that skip the gate.
                    entity_presence=entity_presence,
                    # Inspector telemetry (§11a): the naive-concat baseline, the ordered
                    # compile-trace spans, the derived status chips, the sealed retrieval
                    # mode, and the coarse turn-intent label.
                    trace=_trace_payload,
                    raw_tokens=_raw_tokens,
                    status_flags=_status_flags,
                    retrieval_mode=settings.retrieval_mode,
                    intent=derive_intent(entity_presence),
                    llm_call_count=_llm_call_count,
                    caching=_caching,
                )

                # WS-2.9 (spec 09 §Q6) — a "don't remember this" turn (grounding OFF) is flagged so the
                # distiller's day-window read excludes it. Persist the flag on BOTH the assistant reply
                # and its parent user message (the user's own words are the sensitive half).
                _exclude_mem = bool(canon_capture_ctx and not canon_capture_ctx.grounding_enabled)
                # DBT-CHAT-PERSIST — UPSERT, not a plain INSERT. In-turn checkpoints
                # (each tool boundary + the suspend point) write this same msg_id
                # with finish_reason='streaming'/'awaiting_input'; the clean finish
                # OVERWRITES that row with the full reply + 'stop'. sequence_num is
                # NOT updated (keep the checkpoint's slot). RETURNING (xmax=0) tells
                # us whether this was a genuine INSERT so message_count is bumped
                # exactly once (a checkpoint already counted it).
                _ins_row = await conn.fetchrow(
                    f"""
                    INSERT INTO chat_messages
                      (message_id, session_id, owner_user_id, role, content, content_parts,
                       sequence_num, input_tokens, output_tokens, model_ref, parent_message_id, branch_id, tool_calls,
                       context_breakdown, response_id, exclude_from_memory, local_date, finish_reason,
                       outcome, advertised_tools, withheld_tools, runtime_variant, outcome_source)
                    VALUES ($1,$2,$3,'assistant',$4,$5::jsonb,$6,$7,$8,$9,$10, 0, $11::jsonb, $12::jsonb, $13, $14, $15, $20,
                            $16,$17::jsonb,$18::jsonb,$19,'path')
                    ON CONFLICT (message_id) DO UPDATE SET
                      content = EXCLUDED.content,
                      content_parts = EXCLUDED.content_parts,
                      input_tokens = EXCLUDED.input_tokens,
                      output_tokens = EXCLUDED.output_tokens,
                      model_ref = EXCLUDED.model_ref,
                      tool_calls = EXCLUDED.tool_calls,
                      context_breakdown = EXCLUDED.context_breakdown,
                      response_id = EXCLUDED.response_id,
                      exclude_from_memory = EXCLUDED.exclude_from_memory,
                      local_date = EXCLUDED.local_date,
                      finish_reason = EXCLUDED.finish_reason,
                      is_error = false,
                      error_detail = NULL,
                      -- CP-0.4 — the clean finish is the ONE path that may assert completion, and it
                      -- overwrites whatever a mid-turn checkpoint left here (a 'crashed' derived from
                      -- 'streaming'). The reverse never happens: a checkpoint COALESCEs instead.
                      outcome = EXCLUDED.outcome,
                      outcome_source = 'path',
                      -- F-48 — segment-scoped replace, from `instrument.segment_merge_sql`. The
                      -- terminal handler re-sends the recorder's FULL list, and every mid-turn
                      -- checkpoint sent it too; unconditional concatenation therefore stored each
                      -- pass once per write. Measured on the real recorder: a 3-pass turn with 2
                      -- checkpoints stored 7 entries numbered [1,2,1,2,1,2,3]. Replacing only this
                      -- writer's own segment makes the write idempotent while still preserving a
                      -- RESUME's separate segment, which is what the concatenation was protecting.
                      {instrument.segment_merge_sql("advertised_tools")},
                      {instrument.segment_merge_sql("withheld_tools")},
                      runtime_variant = EXCLUDED.runtime_variant
                    RETURNING (xmax = 0) AS inserted
                    """,
                    msg_id, session_id, user_id, final_text, content_parts, seq,
                    input_tok, output_tok, model_ref, parent_message_id, tool_calls_json,
                    json.dumps(_ctx_payload), _final_response_id, _exclude_mem,
                    _local_date,  # DBT-11 — bucket by the user's LOCAL day (resolved before acquire)
                    # F-17 — DERIVED from the loop's own terminal reason, no longer a constant.
                    #
                    # This bound `completed` unconditionally while the repeated-failure breaker's
                    # exit reaches the same INSERT, so a turn cut short by the breaker recorded a
                    # success. I had written that fixing it needed a signal the consumer did not
                    # carry — that was wrong, and checking cost one grep: the loop emits
                    # `finish_reason` on every content chunk and nothing read it.
                    #
                    # HONEST LIMIT, because deriving is not the same as distinguishing: this now
                    # reflects whatever the loop reports, and if the breaker exit reports `stop`
                    # like any other completion, the recorded outcome is unchanged. What is fixed is
                    # that the value is no longer ASSERTED — a distinct terminal reason now flows
                    # through instead of being overwritten. Whether the breaker produces one is a
                    # live question for a verifier, not something to settle by reading the code I
                    # just wrote.
                    instrument.outcome_for_finish_reason(
                        _loop_finish_reason or "stop", is_error=_silent_turn),
                    json.dumps(_advertised.advertised_json()) if _advertised.advertised_json() else None,
                    json.dumps(_advertised.withheld_json()) if _advertised.withheld_json() else None,
                    # CP-0.7 — DERIVED, never the constant. This is the CLEAN-FINISH path: the
                    # largest population by far, and while it wrote a literal the column could not
                    # record an agentruntime turn at all. Measured 2026-08-09: 5,975 rows, every one
                    # `legacy`, on a column whose whole premise is that the arms are separable.
                    instrument.current_runtime_variant(),
                    # F-19 — `finish_reason` and `outcome` now derive from THE SAME signal. Pinning
                    # 'stop' here while the outcome varied made the row contradict itself, which is
                    # worse than either value alone being wrong: a reader cannot tell which half to
                    # believe. This is the verifier's satisfiable gate, applied.
                    _loop_finish_reason or "stop",
                )
                _did_insert = bool(_ins_row and _ins_row["inserted"])
                if _exclude_mem and parent_message_id:
                    # The parent user message was persisted earlier (POST /messages) without knowing the
                    # turn's grounding choice; back-fill the flag so the user's own words are excluded too.
                    await conn.execute(
                        "UPDATE chat_messages SET exclude_from_memory = true "
                        "WHERE message_id = $1 AND owner_user_id = $2",
                        parent_message_id, user_id,
                    )

                # Extract and persist output artifacts
                artifacts = extract_outputs(final_text)
                output_id = str(uuid4())
                for i, artifact in enumerate(artifacts):
                    oid = output_id if i == 0 else str(uuid4())
                    await conn.execute(
                        """
                        INSERT INTO chat_outputs
                          (output_id, message_id, session_id, owner_user_id,
                           output_type, content_text, language, title)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        oid, msg_id, session_id, user_id,
                        artifact.output_type, artifact.content_text,
                        artifact.language, artifact.title,
                    )

                # Update session stats. DBT-CHAT-PERSIST — only bump message_count
                # when this was a genuine INSERT; if an in-turn checkpoint already
                # created the row it was counted then (the UPSERT took the UPDATE
                # branch). last_message_at/updated_at refresh either way.
                await conn.execute(
                    """
                    UPDATE chat_sessions
                    SET message_count = message_count + CASE WHEN $2 THEN 1 ELSE 0 END,
                        last_message_at = now(),
                        updated_at = now()
                    WHERE session_id = $1
                    """,
                    session_id, _did_insert,
                )

                # K13.2: emit chat.turn_completed outbox event.
                # aggregate_type drives the Redis Stream name via outbox-relay:
                # 'chat' -> loreweave:events:chat (knowledge-service consumer).
                outbox_payload = {
                    "user_id": str(user_id),
                    "project_id": str(project_id) if project_id else None,
                    "session_id": str(session_id),
                    "message_id": str(msg_id),
                    "user_message_id": str(parent_message_id) if parent_message_id else None,
                    "user_content_len": len(user_message_content) if user_message_content else 0,
                    "assistant_content_len": len(final_text),
                }
                await conn.execute(
                    """
                    INSERT INTO outbox_events
                      (event_type, aggregate_type, aggregate_id, payload)
                    VALUES ('chat.turn_completed', 'chat', $1, $2::jsonb)
                    """,
                    msg_id, json.dumps(outbox_payload),
                )

        # DBT-CHAT-PERSIST — the assistant row + its outbox event are committed;
        # the turn is durable, so the terminal-path handlers must NOT re-persist.
        _persisted = True

        # Send custom data annotation (IDs back to frontend)
        data_payload: dict = {"message_id": msg_id}
        if artifacts:
            data_payload["output_id"] = output_id
        if final_reasoning:
            data_payload["has_reasoning"] = True
        for line in emitter.persisted_data(data_payload):
            yield line

        await _flush_activated_tools(pool, session_id, activation_state)

        if surface_tracker is not None:
            payload = surface_tracker.idle()
            if payload is not None:
                for line in emitter.agent_surface(payload):
                    yield line

        # Finish event — includes timing metrics
        finish = {
            "type": "finish-message",
            "finishReason": "stop",
            "usage": {
                "promptTokens": input_tok or 0,
                "completionTokens": output_tok or 0,
            },
            "timing": {
                "responseTimeMs": round(response_time_ms),
                "timeToFirstTokenMs": round(time_to_first_token) if time_to_first_token is not None else None,
            },
        }
        # RAID Wave A2 + W1 — emit the per-turn context frame (the SAME payload
        # persisted to chat_messages.context_breakdown above): measured input
        # tokens vs the model's window + the per-category breakdown. Advisory;
        # NULL context_length → pct=None and the meter shows "—". No try/except:
        # both emitters implement context_budget (legacy no-ops) and the payload
        # was already built on the persist path.
        for line in emitter.context_budget(_ctx_payload):
            yield line
        for line in emitter.finish(finish):
            yield line

        # The turn is durably persisted and finished; everything below is
        # best-effort post-turn work that must NOT be able to emit another
        # terminator. Carry the values it needs out of the try.
        turn_succeeded = True
        post_finish_state = {
            "final_text": final_text,
            "final_reasoning": final_reasoning,
            "input_tok": input_tok,
            "output_tok": output_tok,
            "last_usage": last_usage,
        }

    except (asyncio.CancelledError, GeneratorExit):
        # DBT-CHAT-PERSIST — user interrupt / client disconnect. Neither is an
        # `Exception`, so the handler below never caught them and there is no
        # `finally`, so the streamed-so-far reply was silently lost. Persist the
        # partial as an "interrupted" turn so it survives reload with a badge,
        # then re-raise so cancellation still propagates (never swallow it).
        #
        # `shield` so the write completes even though THIS request task is being
        # cancelled; await-only (no yield) is safe inside GeneratorExit cleanup.
        if not _persisted:
            try:
                # CP-0.4 — DETACH, then shield. `await asyncio.shield(coro)` is not enough here and
                # measured as failing on EVERY cancel: this handler is already unwinding a
                # CancelledError, so the next `await` re-raises it immediately — frequently before
                # the wrapped coroutine has been scheduled at all. The write was abandoned and the
                # except branch below logged "interrupt-persist failed", which is why every cancel
                # produced that line while the only surviving row came from a later fallback.
                #
                # Creating the task FIRST schedules it independently of this task's fate, and the
                # strong reference keeps it from being garbage-collected mid-flight (a bare
                # create_task result is weakly held by the loop). Then shield the await, so being
                # cancelled again costs us the acknowledgement, never the write.
                _cancel_write = asyncio.create_task(
                    _persist_terminal_assistant(
                        pool,
                        msg_id=msg_id, session_id=session_id, user_id=user_id,
                        parent_message_id=parent_message_id, model_ref=model_ref,
                        content="".join(full_content),
                        reasoning="".join(full_reasoning),
                        tool_calls_history=tool_calls_history,
                        finish_reason="interrupted", is_error=False, error_detail=None,
                        # CP-0.4 — `finish_reason` stays 'interrupted' (the FE badge and every
                        # existing reader depend on it; nothing is deleted). `outcome` is where the
                        # truth goes: CancelledError/GeneratorExit here means the user stopped the
                        # turn or the client went away, which is NOT a failure. Fusing the two is
                        # what made the run's own `interrupted` baseline uninterpretable — a metric
                        # containing both "the user changed their mind" and "we lost the turn"
                        # cannot move in a direction that means anything.
                        outcome=instrument.OUTCOME_ABANDONED_BY_USER,
                        advertised_tools=_advertised.advertised_json(),
                        withheld_tools=_advertised.withheld_json(),
                    )
                )
                _DETACHED_CANCEL_WRITES.add(_cancel_write)
                _cancel_write.add_done_callback(_DETACHED_CANCEL_WRITES.discard)
                await asyncio.shield(_cancel_write)
            except asyncio.CancelledError:
                # Expected, and NOT a failure: we were cancelled again while waiting for the
                # acknowledgement. The detached task owns the write and is still running. Logging
                # this as a failure is what made every cancel look broken when most were not.
                logger.info(
                    "interrupt-persist detached for session %s (write continues after cancel)",
                    session_id,
                )
            except BaseException:  # noqa: BLE001 — cleanup must never mask the cancel
                logger.warning(
                    "interrupt-persist failed for session %s", session_id, exc_info=True,
                )
        raise

    except TurnCeilingExceeded as ceiling_exc:
        # ── DQ-T56(2) · A VISIBLE END ────────────────────────────────────────────────────────
        # This arm exists so the ceiling does NOT fall through to the generic error handler
        # below. That handler persists `content="".join(full_content)` — which on the failure
        # this closes is the EMPTY STRING, because a turn that hung before its first token
        # produced nothing. `_persist_terminal_assistant` skips a truly-empty turn and stamps
        # the outcome onto the USER's row instead, and the author is left with their own
        # message standing alone and the turn's fate in a column only the database can read.
        # That is exactly the outcome the owner decided against.
        #
        # 🔴 THE OBJECTION THE CODE RECORDED IS HONOURED, NOT OVERRULED. The empty-turn skip
        # says a blank assistant bubble "would be noise" and that writing one is a product
        # change that checkpoint had no business making. Both remain true: what goes in is not
        # a blank bubble, it is a row that SAYS the turn did not complete and why. The change
        # is made deliberately, by decision, and only on this path.
        logger.warning(
            "turn-ceiling: session %s ran %.0fs past a %.0fs ceiling (%d tool calls so far)",
            session_id, ceiling_exc.elapsed_s, ceiling_exc.ceiling_s, len(tool_calls_history),
        )
        _ceiling_note = (
            f"This turn did not complete. The model stopped responding, so it was ended after "
            f"{_humanize_seconds(ceiling_exc.elapsed_s)} rather than left running with nothing "
            "to show. Your message is still here — send it again to retry."
        )
        if tool_calls_history:
            # Never claim nothing happened. By the time the ceiling fires, tools may already
            # have run and written, and a message implying otherwise would be a lie the author
            # acts on.
            _ceiling_note += (
                " Any tool calls already made in this turn ran, and their effects stand."
            )
        _partial = "".join(full_content)
        _ceiling_content = f"{_partial}\n\n{_ceiling_note}" if _partial else _ceiling_note
        if not _persisted:
            await _persist_terminal_assistant(
                pool,
                msg_id=msg_id, session_id=session_id, user_id=user_id,
                parent_message_id=parent_message_id, model_ref=model_ref,
                content=_ceiling_content,
                reasoning="".join(full_reasoning),
                tool_calls_history=tool_calls_history,
                # `error` + is_error is the shape the FE already badges "incomplete"; inventing
                # a new finish_reason here would change how every existing reader renders this
                # row to say something `error_detail` and the content already say.
                finish_reason="error", is_error=True,
                error_detail=str(ceiling_exc),
                # Reusing `failed` rather than minting a 7th outcome: the turn DID fail, and
                # `failed` is not the kind of fusion `interrupted` was — nothing about a
                # ceiling expiry is a success or a user choice. A new enum value would mean a
                # forward-only migration against the column's CHECK constraint plus every
                # reader of a closed vocabulary, to record what `error_detail` states exactly.
                outcome=instrument.OUTCOME_FAILED,
                advertised_tools=_advertised.advertised_json(),
                withheld_tools=_advertised.withheld_json(),
            )
        # Close any open assistant/reasoning message, then deliver the note as CONTENT rather
        # than only as an error frame: an error frame is a banner the FE may render and drop,
        # while the persisted row above is what a reload shows. Both now say the same thing.
        for line in emitter.text_delta(
            _ceiling_note if not _partial else f"\n\n{_ceiling_note}"
        ):
            yield line
        for line in emitter.close_message():
            yield line
        for line in emitter.error(str(ceiling_exc)):
            yield line

    except Exception as exc:
        logger.exception("Stream error for session %s", session_id)
        # Sanitize error message — don't leak internal details
        safe_msg = str(exc)
        if any(kw in safe_msg.lower() for kw in ("traceback", "file ", "/usr/", "password", "secret")):
            safe_msg = "An internal error occurred. Please try again."
        # DBT-CHAT-PERSIST — persist whatever the model already streamed before
        # the throw so the turn is not lost on reload; is_error marks it and the
        # FE badges it "incomplete". (Covers the reported case: a mid-turn BE
        # error on a frontend-tool turn used to drop the whole reply.)
        if not _persisted:
            await _persist_terminal_assistant(
                pool,
                msg_id=msg_id, session_id=session_id, user_id=user_id,
                parent_message_id=parent_message_id, model_ref=model_ref,
                content="".join(full_content),
                reasoning="".join(full_reasoning),
                tool_calls_history=tool_calls_history,
                finish_reason="error", is_error=True, error_detail=safe_msg,
                outcome=instrument.OUTCOME_FAILED,
                advertised_tools=_advertised.advertised_json(),
                withheld_tools=_advertised.withheld_json(),
            )
        for line in emitter.error(safe_msg):
            yield line

    # ── Post-turn best-effort side-effects (auto-title + billing) ────────────
    # Runs OUTSIDE the try so a failure here can never emit error/RUN_ERROR
    # after finish/RUN_FINISHED. Both branches schedule background tasks (which
    # swallow their own errors); only the auto-title count read touches the DB,
    # so it is guarded.
    if turn_succeeded and post_finish_state is not None:
        current_count = None
        is_roleplay = False
        try:
            _pf_row = await pool.fetchrow(
                "SELECT message_count, working_memory_seed IS NOT NULL AS is_roleplay "
                "FROM chat_sessions WHERE session_id = $1",
                session_id,
            )
            if _pf_row is not None:
                current_count = _pf_row["message_count"]
                is_roleplay = _pf_row["is_roleplay"]
        except Exception:
            logger.warning(
                "auto-title count lookup failed for session %s (post-finish)",
                session_id, exc_info=True,
            )
        # Executive cadence (M5): every N assistant turns on a roleplay session,
        # fire a best-effort executive pass to refresh working_memory.state.
        if (
            is_roleplay
            and current_count is not None
            and current_count % EXECUTIVE_EVERY_N_TURNS == 0
        ):
            asyncio.create_task(
                _fire_executive_tick(session_id, user_id, model_source, model_ref, pool)
            )
        if current_count is not None and current_count <= 2:
            asyncio.create_task(
                _auto_generate_title(
                    session_id=session_id,
                    user_id=user_id,
                    user_message=user_message_content,
                    assistant_message=post_finish_state["final_text"][:500],
                    model_source=model_source,
                    model_ref=model_ref,
                    pool=pool,
                )
            )

        # WS-4C Half A — canon auto-capture. Every Nth turn, the entities this exchange
        # newly NAMED land in the book's glossary review inbox as ai-suggested drafts
        # (human-gated; never canon). Closes F4's write side: the glossary is re-read into
        # the context block every turn, so a name coined at turn 3 survives to turn 40.
        #
        # `_capture_book_id` is the book knowledge-service resolved from the session's own
        # project — never the FE-supplied `_ctx_book_id`. None on a multi-project turn:
        # capture writes into ONE book's inbox and a union of projects has no single book.
        _capture_decision = maybe_capture_canon(
            ctx=canon_capture_ctx,
            user_id=str(user_id),
            assistant_turn_count=current_count,
            user_message=user_message_content,
            assistant_message=post_finish_state["final_text"],
            # The session's own live BYOK model. Passing it explicitly matters:
            # provider-registry's planner-default resolution returns nothing for an account
            # with no `user_default_models` row, which is the common case.
            model_ref=model_ref if model_source == "user_model" else None,
        )
        # WS-1.6 (spec 05 §Q7) — persist the decision so the assistant home strip can render
        # capture visibly ON/OFF *with a reason*, not just trust it is on. Best-effort +
        # awaited (a single indexed UPDATE at turn-end); persist swallows its own errors.
        await persist_capture_status(pool, session_id, _capture_decision)

        # BILLING — do NOT record chat usage here (F11, 2026-07-21). provider-registry's
        # stream billing (`stream_billing.go` → RecordUsage, TotalCostUSD: actual) is the
        # SOLE authoritative biller: it records EACH tool-loop pass at the model's real
        # per-mtok price ("matches reconcile"). This turn-level log_usage was a redundant
        # SECOND writer that (a) summed input across every re-sent pass (input_tok is the
        # tool-loop SUM — 550,704 for a 16-pass turn vs a real ~34K context), and (b) sent
        # NO cost, so usage-billing's token fallback re-priced it at ~$2/1M instead of the
        # model's $0.10 — a double-charge at ~20× on the summed tokens (spend =
        # SUM(total_cost_usd) FROM usage_logs, so both writers counted). Voice STT/TTS still
        # bills via billing.log_usage from voice.py (its own per-second/char cost, a lane
        # provider-registry does not meter). See docs/eval/co-writer-onboarding-dogfood-2026-07-21.md F11.

    for line in emitter.done():
        yield line


async def resume_stream_response(
    *,
    session_id: str,
    user_id: str,
    run_id: str,
    tool_call_id: str,
    outcome: str | None,
    applied_text: str | None,
    result: dict | None = None,
    creds: ProviderCredentials,
    pool: asyncpg.Pool,
    billing: BillingClient,
    stream_format: str = "agui",
    admin_token: str | None = None,
) -> AsyncGenerator[str, None]:
    """ARCH-1 C6 — resume a suspended run after the FE executed a frontend tool.

    Loads the suspended run (scoped to user), appends the tool result to the
    rehydrated conversation, re-derives tool defs, and streams the 2nd LLM pass
    via the shared _emit_chat_turn. Yields an AG-UI RUN_ERROR if the suspended
    run is missing/expired."""
    from app.services.frontend_tools import frontend_tool_defs
    from app.db.suspended_runs import load_suspended_run_any

    # CP-0.2 / U-2 — the resumed turn's narrowing sink, armed before its first decision. A resume
    # re-derives its whole surface from scratch (WS-3), so it narrows as much as a fresh turn does.
    instrument.arm_turn_surface()

    susp = await load_suspended_run(pool, run_id, user_id)
    if susp is None or susp.pending_tool_call.get("id") != tool_call_id:
        # Unknown/expired/mismatched — surface a clean AG-UI error.
        #
        # DBT-CHAT-PERSIST — but do NOT let the trapped reply vanish. The run may
        # be expired (TTL) or its resume otherwise refused; either way the whole
        # assistant turn (prose + the proposed card) was never written to
        # chat_messages, so a reload shows nothing. Materialize whatever the
        # abandoned run still holds into a visible 'interrupted' message first
        # (works on an EXPIRED row — load_suspended_run_any ignores the TTL),
        # then drop the dead run so a retry can't double-materialize.
        abandoned = await load_suspended_run_any(pool, run_id, user_id)
        if abandoned is not None and abandoned.pending_tool_call.get("id") == tool_call_id:
            await _mark_suspend_abandoned(pool, abandoned)
            await delete_suspended_run(pool, run_id)
        emitter = make_emitter(stream_format, thread_id=session_id, message_id=str(uuid4()))
        for line in emitter.open_run():
            yield line
        for line in emitter.error("This suggestion has expired. Please ask again."):
            yield line
        for line in emitter.done():
            yield line
        return

    # Append the frontend tool's result (the human's apply decision) so the
    # agent can acknowledge it in the 2nd pass.
    working = list(susp.working)
    # RAID C2 (DR-C2 §4) — a `tool_approval` suspend resumes with
    # approved_once | approved_always | denied; its tool result is the REAL
    # server execution (or the denial), computed below once knowledge_client +
    # project_id are in scope — NOT the generic outcome echo.
    _approval_args = susp.pending_tool_call.get("args")
    is_approval = (
        isinstance(_approval_args, dict)
        and _approval_args.get("kind") == "tool_approval"
    )
    # ext-tasks (T1c(3.c)) — a durable-gate suspend (step b marked pending["task"]).
    # Like an approval, its tool result is the REAL execution (call the domain's
    # provide-input tool below once knowledge_client is in scope), NOT the outcome echo.
    is_task = (not is_approval) and bool(susp.pending_tool_call.get("task"))
    #: The resolution row for a plain frontend suspension — see the block below. `None` on the
    #: approval and task paths, which record their REAL execution instead.
    _fe_resolved_chunk: dict | None = None
    if not is_approval and not is_task:
        if result is not None:
            # MCP fan-out (C-NAV): a ui_* nav resolve — feed the structured result
            # (e.g. {"navigated": true}) back verbatim as the tool result.
            result_payload: dict = result
        else:
            result_payload = {"outcome": outcome if outcome is not None else "dismissed"}
            if applied_text is not None:
                result_payload["applied_text"] = applied_text
        working.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": tool_result_content(result_payload),
        })
        # ── TOOL-V2 LOOP #3 · THE OTHER HALF OF CP-5.5 ───────────────────────────────────
        # 🔴 The human's decision arrived HERE and, until now, went only into `working` — prose
        # for the model to read, and nothing a measurement can see. The suspension's own row
        # stays `deferred` forever, so "the user applied the edit" and "the user walked away"
        # are the same row.
        #
        # Measured on `glossary_propose_entity_edit`: proven end to end on a throwaway book —
        # glossary_search → glossary_get_entity → propose with a real entity_id, attr_value_id
        # and base_version → apply-edit 200 → the description changes in the database — and it
        # reads **0 successes in 101 calls**, because a frontend tool suspends and `ok:true` is
        # written only where a dispatch returns. Any queue ranking tools by success puts working
        # tools at the top of its broken list. This loop's own queue did exactly that.
        _fe_resolved_chunk = instrument.stamp_tool_call(
            instrument.resolve_deferred({
                "id": f"{tool_call_id}:resolved", "iteration": 0,
                "tool": str(susp.pending_tool_call.get("name") or ""),
                "args": susp.pending_tool_call.get("args") or {},
                # `ok` mirrors the typed outcome for the readers that predate C-14. It is the
                # derived field here, not the authority — that inversion is the whole row.
                "ok": outcome in ("applied_saved", "applied", "action_done", "accept",
                                  "confirmed") or (outcome is None and result is not None),
                "result": None, "error": None,
            }, outcome, had_result=result is not None),
            source=instrument.SOURCE_TOOL,
        )

    # Re-derive session gen_params + tool defs for the 2nd pass.
    session_row = await pool.fetchrow(
        "SELECT generation_params, project_id, system_prompt, composer_model_source, composer_model_ref, "
        "planner_model_ref, enabled_tools, enabled_skills, activated_tools, "
        "book_id "  # studio context binding — a confirm-RESUMED ambient tool needs the session's book (X-Book-Id)
        "FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    gp_raw = session_row["generation_params"] if session_row else {}
    if isinstance(gp_raw, str):
        gp_raw = json.loads(gp_raw)
    gen_params: dict = gp_raw if gp_raw else {}
    # Resolve reasoning on the RESUME path too (review-impl H): the raw
    # session-stored `reasoning_effort` ("off"/"auto") is not wire vocabulary —
    # unresolved it crashed StreamRequest on every tool-approval resume.
    _resolve_and_stash_reasoning(gen_params, creds)
    project_id = session_row.get("project_id") if session_row else None
    # A2A phase-2: keep compose_prose available on resume too (the agent may
    # delegate prose again after the user's apply/dismiss).
    composer_src = session_row.get("composer_model_source") if session_row else None
    composer_ref = session_row.get("composer_model_ref") if session_row else None
    composer_model = (composer_src, str(composer_ref)) if composer_src and composer_ref else None
    composer_system_prompt = session_row.get("system_prompt") if session_row else None
    planner_resume_ref = session_row.get("planner_model_ref") if session_row else None
    planner_model_ref = str(planner_resume_ref) if planner_resume_ref else None

    from app.services.skill_registry import resolve_skills_to_inject_async
    from app.services.tool_surface import resolve_session_tool_pins, discovery_seed_for_surface
    from app.services.agent_surface import AgentSurfaceTracker

    tool_pins = resolve_session_tool_pins(session_row)
    resume_surface_tracker = (
        AgentSurfaceTracker() if stream_format == "agui" else None
    )
    # Part F / F2 — same router wiring as the fresh-turn call site
    # (stream_response above); the resumed turn's own text/model is carried on
    # `susp` (SuspendedRun), the same values the 2nd LLM pass itself replays.
    resume_injected_skills = await resolve_skills_to_inject_async(
        enabled_skills=tool_pins.effective_skills,
        stream_format=stream_format,
        disable_tools=False,
        tool_calling_enabled=True,
        editor=True,
        book_scoped=True,
        admin=bool(admin_token),
        # RAID B2 — the resume continues under the suspended turn's mode.
        permission_mode=susp.permission_mode,
        # Conservative superset, matching the resume `discovery_seed_for_surface` call
        # below (editor=True, book_scoped=True, studio=True) — the resume doesn't know
        # the exact original surface, so it re-seeds/re-injects the union of everything.
        studio=True,
        intent_text=susp.user_message_content,
        user_id=user_id,
        model_source=susp.model_source,
        model_ref=susp.model_ref,
        lazy_bodies=settings.lazy_skill_bodies,  # F7c — same lazy discipline as the fresh path
    )

    knowledge_client = get_knowledge_client()

    # ext-tasks (T1c(3.c)) — resume-DRIVE the durable gate: on the human's decision,
    # call the domain's provide-input tool (the gate ACCEPT runs the real write there
    # and returns {status, result}); feed that back as the tool result so the 2nd pass
    # acknowledges the REAL outcome. The provide-input tool is domain-unique
    # (<prefix>_task_provide_input, gateway-routable — see the routing fix), derived from
    # the gate tool's provider prefix. Accept outcomes confirm; anything else declines.
    _task_chunk: dict | None = None
    if is_task:
        _task = susp.pending_tool_call.get("task") or {}
        _gate = str(susp.pending_tool_call.get("name") or "")
        _provide_tool = (_gate.split("_", 1)[0] + "_task_provide_input") if "_" in _gate else "task_provide_input"
        _accepted = outcome in (
            "applied_saved", "action_done", "accept", "applied", "approved_once", "confirmed",
        )
        # CP-0.3 — the THIRD real dispatch, and until now the only one recording NOTHING: it fed
        # `working` and never produced a tool_calls entry, so a durable human-gated task resolving
        # left no trace in the turn's history at all. Not merely unclassified — absent.
        _task_t0 = _time.monotonic()
        _tenv = await knowledge_client.mcp_execute_tool(
            user_id=user_id, session_id=session_id, project_id=project_id,
            tool_name=_provide_tool,
            tool_args={"task_id": _task.get("taskId"), "accepted": _accepted},
            admin_token=admin_token,
        )
        _task_ms = int((_time.monotonic() - _task_t0) * 1000)
        _tres = _tenv.get("result") if _tenv.get("success") else {"error": _tenv.get("error")}
        _task_chunk = instrument.stamp_tool_call({
            "id": tool_call_id, "iteration": 0, "tool": _provide_tool,
            "args": {"task_id": _task.get("taskId"), "accepted": _accepted},
            "ok": bool(_tenv.get("success")),
            "result": _tenv.get("result") if _tenv.get("success") else None,
            "error": None if _tenv.get("success") else _tenv.get("error"),
        }, source=instrument.SOURCE_TOOL, latency_ms=_task_ms)
        working.append({
            "role": "tool", "tool_call_id": tool_call_id,
            "content": tool_result_content(_tres if _tres is not None else {}),
        })

    # RAID C2 (DR-C2 §4) — act on the approval outcome BEFORE the 2nd pass:
    #   approved_once   → execute the tool now; feed its REAL result back.
    #   approved_always → persist the allowlist row, then execute.
    #   denied          → feed {"error": "denied by user"} so the model
    #                     self-corrects (no execution).
    # The executed call is surfaced via pre_tool_chunks (tool_call + activity
    # events + persisted history) — C-ACTIVITY parity, undo unchanged.
    # CP-0.3 — carry the ext-task dispatch into the recorded history. `pre_tool_chunks` is the
    # existing channel for "a tool ran before the loop re-entered"; the task path simply never used
    # it, which is why its execution was invisible rather than mislabelled.
    pre_tool_chunks: list[dict] | None = [
        _c for _c in (_fe_resolved_chunk, _task_chunk) if _c is not None
    ] or None
    # Bound HERE, at function scope, and populated only in the approval branch. It is READ by
    # the seed derivation far below, which runs on resume paths that never took that branch —
    # declaring it where it is populated would NameError on every confirm-only resume. (Same
    # class as the tool_calls_history slip caught earlier this session: a diagnostic that breaks
    # only on the turn it exists to serve.)
    # 🔴 THE TEXT IS CAPTURED HERE AND RESOLVED LATER, AND THE ORDER IS THE WHOLE POINT. My
    # first version resolved names at the dispatch site — which runs BEFORE `catalog` is fetched
    # (L~11332), so the `and catalog` guard was false every time and the collection silently did
    # nothing. Measured: three suspended runs of composition_entity_override_edit, zero
    # carry-forward log lines. Resolution now happens beside the seed, where the catalogue
    # exists.
    _resume_refusal: str = ""
    _resume_refused_tool: str = ""
    if is_approval:
        _appr = _approval_args if isinstance(_approval_args, dict) else {}
        _tool_name = str(_appr.get("tool") or susp.pending_tool_call.get("name") or "")
        _tool_args = _appr.get("args") if isinstance(_appr.get("args"), dict) else {}
        # Same scalar-id list-unwrap the main dispatch does — the frozen consent args can carry
        # gemma's project_id=[uuid] (measured: connect-people 400'd "you sent a list").
        _coerce_listed_scalar_ids(_tool_args)
        _decision = outcome if outcome in ("approved_once", "approved_always", "denied", "denied_always") else "denied"

        # Track C WS-3 — the resume path is the ONE execution site that does not run
        # through the in-loop gate, so it must re-check the standing decision itself. A
        # card can sit suspended indefinitely; if the user opened Settings in the
        # meantime and blocked the tool, the stale card must not still execute it — and
        # clicking "Always allow" on it must not silently overwrite the refusal they just
        # made. The refusal is the LATER, more deliberate act; it wins.
        _standing_deny = False
        try:
            for _k in ("mutation", "spend"):
                if await get_tool_decision(pool, user_id, _tool_name, _k) == "deny":
                    _standing_deny = True
                    break
        except Exception:  # unreadable ⇒ unknown, not refused (never hard-block on a blip)
            logger.warning(
                "resume: standing-decision read failed for %s", _tool_name, exc_info=True
            )
        # denied_always is EXCLUDED from this downgrade: it is strictly MORE restrictive
        # than an existing partial deny (it persists a deny on every kind the card carried),
        # so downgrading it to one-shot "denied" would suppress its persist block and drop
        # the other kinds — e.g. a paid tool already mutation-denied would never get its
        # SPEND deny, and the "Never allow" the user clicked silently evaporates for spend.
        # It never executes regardless (absent from the approve set below), so keeping it
        # only ADDS the missing deny rows.
        if _standing_deny and _decision not in ("denied", "denied_always"):
            logger.info(
                "resume: %s was blocked by a standing deny — ignoring stale outcome %r",
                _tool_name, _decision,
            )
            _decision = "denied"

        # The consent kinds the card carried (both approved_always and denied_always
        # persist a standing row per kind). Legacy DR-C2 cards carry no `approval_kinds`
        # → default to ["mutation"] (the mutation kind persists via the legacy 2-arg call
        # shape, kept identical so existing allowlist rows/tests are unaffected).
        _appr_kinds = _appr.get("approval_kinds")
        if not isinstance(_appr_kinds, list) or not _appr_kinds:
            _appr_kinds = ["mutation"]
        if _decision == "approved_always":
            # S-SPEND — persist a SEPARATE allow row per required consent kind (a paid
            # Tier-A always-allow persists BOTH spend and mutation).
            for _k in _appr_kinds:
                try:
                    if _k == "mutation":
                        await approve_tool(pool, user_id, _tool_name)
                    else:
                        await approve_tool(pool, user_id, _tool_name, _k)
                except Exception:
                    # The human approved THIS call; a failed allowlist write only
                    # means they may be prompted again — still execute.
                    logger.warning(
                        "always-allow persist failed for %s (kind=%s) — executing anyway",
                        _tool_name, _k, exc_info=True,
                    )
        elif _decision == "denied_always":
            # D3 (PO sign-off) — "Never allow" ON THE CARD: persist a standing DENY per
            # consent kind the card carried, then fall through to the denied path below
            # (feed the model "denied by user", execute NOTHING). Denying the mutation
            # kind alone already blocks the tool (D6: any deny row blocks), but a paid
            # tool's card carries spend too, so deny every kind for a complete refusal.
            # A failed persist only means the user may be prompted again — never execute.
            for _k in _appr_kinds:
                try:
                    await set_tool_decision(pool, user_id, _tool_name, _k, "deny")
                except Exception:
                    logger.warning(
                        "never-allow persist failed for %s (kind=%s)",
                        _tool_name, _k, exc_info=True,
                    )
        if _decision in ("approved_once", "approved_always"):
            # CP-0.3 — the SECOND real dispatch in this service. Missing it filed a genuine,
            # user-approved Tier-A WRITE as `breaker`, i.e. as our own refusal prose — inverting the
            # one distinction the field exists to make, and doing it on the highest-consequence
            # calls in the product (the ones that change data after a human said yes).
            # 🔴 TOOL DEEP-DIVE (2026-08-13) — THE APPROVED CALL BYPASSED EVERY ARGUMENT
            # REPAIR. This is the second real dispatch in the service, and it handed the model's
            # RAW saved args straight to the executor: no context-id fill, no malformed-UUID
            # substitution, no studio single-book override. So the highest-consequence calls in
            # the product — the ones a human just said yes to — were the ONLY ones running
            # unrepaired.
            #
            # MEASURED LIVE 2026-08-12, book 019ff497: the model called plan_bootstrap_propose
            # with a correct run_id and book_id=019ff497-e068-… (the book's KNOWLEDGE PROJECT
            # id). The streaming pass logged the override — "differs from the studio's book …
            # overriding" — the call suspended on its Tier-A card, the author approved it, and
            # composition-service was then asked for /internal/books/019ff497-e068-…/access.
            # The repair happened, was never persisted, and the approved write failed as "not
            # found or not accessible" on a book the author owns and had open.
            _repair_saved_book_id(_tool_args, book_id=susp.book_id, studio=bool(susp.studio))
            _resume_t0 = _time.monotonic()
            envelope = await knowledge_client.mcp_execute_tool(
                user_id=user_id, session_id=session_id,
                project_id=str(project_id) if project_id else None,
                # Studio context binding — a confirm-replayed book tool that resolved book_id
                # from the envelope on pass 1 must still get the ambient book here (as a str).
                book_id=(str(session_row["book_id"]) if session_row and session_row.get("book_id") else None),
                tool_name=_tool_name, tool_args=_tool_args,
                admin_token=admin_token,
            )
            _resume_ms = int((_time.monotonic() - _resume_t0) * 1000)
            _ok = bool(envelope.get("success"))
            _tool_payload = envelope.get("result") if _ok else {"error": envelope.get("error")}
            # 🔴 THE RESUME PATH HAD NONE OF THE MAIN LOOP'S GUARDS, AND THIS IS THE SECOND ONE
            # IT COST. (The first: R1 answerability was inert on every resumed turn because
            # _emit_chat_turn was called without request_text.) A Tier-A tool SUSPENDS for
            # approval and executes HERE, not in the main loop — so its refusal never reached
            # the D-FJ-4 arming, and the tool it names stayed off the wire.
            #
            # MEASURED 2026-08-24 (c-override12, K=5). composition_entity_override_edit refused
            # with NOT_A_DERIVATIVE naming composition_list_derivatives, and
            # chat_messages.withheld_tools shows that tool withheld 5 of 5 for BOTH
            # domain_not_selected and hot_seed. Every tool that DID reach the main loop's arming
            # diagnostic is Tier R.
            #
            # Collected here and unioned into the seed below, because a resume RE-DERIVES ITS
            # SURFACE FROM SCRATCH (WS-3) — arming the live set would be discarded moments later.
            _resume_refusal = ""
            if not _ok:
                _resume_refusal = str(envelope.get("error") or "")
            if not _resume_refusal and isinstance(_tool_payload, dict) and (
                    not _ok or _tool_payload.get("success") is False):
                _resume_refusal = str(_tool_payload.get("error") or "")
            if _resume_refusal:
                # Resolved below, beside the seed — the catalogue does not exist yet here.
                _resume_refused_tool = _tool_name
            working.append({
                "role": "tool", "tool_call_id": tool_call_id,
                "content": tool_result_content(_tool_payload),
            })
            _chunk: dict = {
                "id": tool_call_id, "iteration": 0, "tool": _tool_name,
                "args": _tool_args, "ok": _ok,
                "result": envelope.get("result") if _ok else None,
                "error": None if _ok else envelope.get("error"),
            }
            if _ok:
                # C-ACTIVITY (H16) parity with the in-loop Tier-A path: the
                # approved write is visible + undoable, never a silent surprise.
                _result = envelope.get("result") or {}
                _result_meta = _result.get("_meta") if isinstance(_result, dict) else None
                _undo = tool_undo_hint(_result_meta)
                _summary = ""
                if isinstance(_result_meta, dict):
                    _summary = str(_result_meta.get("summary", "") or "")
                _chunk["activity"] = {
                    "op": _tool_name,
                    "summary": _summary or f"Did {_tool_name}",
                    "undo": (
                        {"available": True, "tool": _undo.get("tool"),
                         "args": _undo.get("args", {})}
                        if _undo else {"available": False}
                    ),
                }
            instrument.stamp_tool_call(
                _chunk, source=instrument.SOURCE_TOOL, latency_ms=_resume_ms,
            )
            pre_tool_chunks = [_chunk]
        else:
            working.append({
                "role": "tool", "tool_call_id": tool_call_id,
                "content": tool_result_content({"error": "denied by user"}),
            })
            # Explicitly `breaker`, not left to inference: a user denial is OUR refusal, and this is
            # the branch where the two are one line apart. Stating it removes the only place where a
            # reader could mistake the classifier's default for a decision.
            #
            # ── TOOL-V2 LOOP #2 · AND THE OUTCOME MUST BE STATED HERE TOO ────────────────────
            # 🔴 **MEASURED: 21 calls across 17 sessions and 4 tools are a human saying no, and
            # every one of them is recorded as a tool FAILURE.** `source` was stamped here; the
            # typed outcome was not, so `ensure_tool_call_instrumented` fell through to its
            # fail-closed default (`ok is not True` ⇒ `failed`, `error_class` ⇒ unclassifiable)
            # and flagged it `call_outcome_inferred`. The row then says the tool broke.
            #
            # It did not break. It never ran. `kg_propose_edge` reads 0 successes in 17 calls and
            # **14 of those 17, across 12 of its 14 sessions, are this branch** — a Tier-A tool
            # that has literally never been permitted to dispatch. Its "0% success rate" was
            # measuring the approval card, not the tool.
            #
            # This is the SAME conflation for the third time: a suspension recorded `ok:false`
            # (5.5), 52.4% of failures being our own breaker prose (`stamp_refused`), and now a
            # denial. The vocabulary already had the word — `refused` is defined as "a call the
            # RUNTIME declined to make", and the line above already argues a user denial is ours.
            # `refusal_kind` keeps it separable from the breaker refusals, so "the human said no"
            # and "we short-circuited a repeat" can never merge into one number.
            pre_tool_chunks = [instrument.stamp_tool_call(
                instrument.stamp_refused({
                    "id": tool_call_id, "iteration": 0, "tool": _tool_name,
                    "args": _tool_args, "ok": False,
                    "result": None, "error": "denied by user",
                }, "denied_by_user"),
                source=instrument.SOURCE_BREAKER,
            )]

    resume_discovery_catalog: list[dict] | None = None
    resume_extra_frontend: list[dict] | None = None
    resume_seed_names: set[str] | None = None
    tool_defs: list[dict] = []
    if admin_token:
        # T4c — resuming an ADMIN-surface run: re-derive the admin catalog from
        # /mcp/admin and re-advertise ONLY glossary_confirm_action. Curation
        # holds on resume too: never the book/user catalog or its write-back
        # tools, never discovery, never compose_prose. (The admin re-presents
        # X-Admin-Token on the tool-results request.)
        tool_defs = await knowledge_client.get_admin_tool_definitions(admin_token)
        if stream_format == "agui" and tool_defs:
            from app.services.frontend_tools import GLOSSARY_CONFIRM_ACTION_TOOL
            tool_defs = tool_defs + [GLOSSARY_CONFIRM_ACTION_TOOL]
        use_tools = bool(tool_defs)
    else:
        catalog: list[dict] = []
        try:
            # REG-P2-03 — per-user overlay in the resumed turn's catalog too.
            catalog = await knowledge_client.get_tool_definitions(user_id=user_id)
        except Exception:
            catalog = []
        # The editor tool stays advertised on resume (the agent may propose again).
        # Append it WHENEVER agui — mirror the fresh path (stream_response), which
        # adds the frontend tool regardless of whether memory tools are present.
        # Gating on `tool_defs` was a bug: with no memory tools (no project) the
        # frontend tool was dropped AND the run fell through to the no-tools gateway
        # path, which ignores seed_usage → resume usage was NOT summed across the two
        # runs (caught by C6 live smoke). Going through _stream_with_tools keeps the
        # seed and re-advertises the tool.
        # MCP-fanout C-FT: on an agui resume re-enable two-stage discovery when the
        # catalog is non-empty, so a generic confirm_action / ui_* suspend can resume
        # into a fully-capable turn (find more tools, confirm again) — not just the
        # glossary frontend tools. The generic ui_*/confirm/propose tools come in via
        # the always-on core; the glossary write-back tools are advertised alongside
        # (a book-scoped suspend may still propose a glossary edit).
        tool_defs = list(catalog)
        if stream_format == "agui" and catalog:
            from app.services.tool_discovery import filter_intent_gated_setup_tools
            # N5a-FULL — same capability floor on the resume path (mirror the fresh turn),
            # INCLUDING the pinned rail's step-tool exemption. `susp.pinned_step_tools` exists
            # precisely because a resume re-derives its surface from scratch (WS-3); dropping
            # the exemption here would strand a rail at its FIRST confirm gate — the same
            # failure WS-3 was written to fix, re-entered through the capability floor.
            # CP-0.2 — armed at the top of this function, not here: the catalogue fetch 26 lines
            # above is a narrowing too, and re-arming here would discard whatever it registered.
            # DQ-T31 — the declaration arm survives the suspend, for the SAME reason
            # `pinned_step_tools` does. A resume re-derives its surface from scratch, so
            # without this a tool the author's own words named would be present on the pass
            # that raised the confirm card and GONE on the pass that acts on the approval —
            # the resumed turn reading an instruction it can no longer satisfy, which is the
            # failure WS-3 was written to fix. `user_message_content` is the original request,
            # carried on the suspend record precisely so a resume can re-derive from it.
            resume_discovery_catalog = filter_intent_gated_setup_tools(
                catalog, resume_injected_skills, set(susp.pinned_step_tools or ()),
                request_text=susp.user_message_content,
            )
            # The generic frontend tools (core) + the glossary write-back tools, both
            # available on resume; _stream_with_tools advertises {core} ∪ {discovered}
            # ∪ extra_frontend per pass.
            resume_extra_frontend = (
                frontend_tool_defs(editor=False, book_scoped=False)
                + frontend_tool_defs(editor=True, book_scoped=True)
            )
            # Resume uses editor superset for frontend tools; discovery seed respects
            # session curated pins when enabled_tools is non-empty (story 04 S2).
            # Resume superset includes the studio hot domains — a suspend raised on the
            # studio compose surface must resume with its composition family still hot.
            # NOT re-armed here: the sink was armed before catalog assembly above, and setting a
            # fresh list would DISCARD the intent gate's records — which is how the previous fix
            # managed to be a no-op even where it was armed.
            # Resolve the resumed tool's refusal HERE, where `catalog` exists. See the capture
            # site above the dispatch for why it cannot be done there.
            _resume_refusal_named: set[str] = set()
            if _resume_refusal and catalog:
                _resume_refusal_named = set(_tools_named_in_refusal(
                    _resume_refusal, _catalog_index(catalog), set(),
                    exclude=_resume_refused_tool))
                if _resume_refusal_named:
                    logger.info(
                        "resumed %s refused and named %s — carrying them into the re-derived "
                        "surface so the instruction can be followed",
                        _resume_refused_tool, ", ".join(sorted(_resume_refusal_named)),
                    )
            resume_seed_names = discovery_seed_for_surface(
                resume_discovery_catalog,  # N5a-FULL — seed from the filtered catalog too
                pins=tool_pins,
                editor=True,
                book_scoped=True,
                studio=True,
                context_length=creds.context_length,
                permission_mode=susp.permission_mode,
                # WS-3 — re-advertise the PINNED rail's step tools. The rail's TEXT is
                # already in the resumed prompt (it lives in the system message inside
                # `working`), so WITHOUT this the model reads an ordered recipe naming
                # tools it cannot call — and W6's first confirm gate is step 3 of 12, so
                # the flagship rail broke at its very first gate. Captured at suspend time
                # because the resume has no book_id to re-resolve the binding with.
                pinned_step_tools=susp.pinned_step_tools,
                # D-SKILL-NAMED-TOOLS-RIDE — same guarantee on the resume pass.
                injected_skill_codes=resume_injected_skills,
                # …and the same guarantee for the RUNTIME's own instruction: a refusal from the
                # tool this resume just executed must not name a tool the re-derived surface
                # then withholds. See the collection site above the dispatch.
                refusal_named_tools=_resume_refusal_named,
            )
            tool_defs = _advertise_discovery_tools(
                _catalog_index(catalog), resume_seed_names, resume_extra_frontend,
                book_bound=bool(susp.book_id),
                # A resume is still answering the ORIGINAL request — the suspended run
                # carries it. Dropping it here would make the post-approval pass the one
                # surface in the system that cannot answer the question it was suspended on.
                request_text=susp.user_message_content,
            )
        elif stream_format == "agui":
            # No catalog (gateway down) → no discovery, but still re-advertise the
            # frontend write-back tools so the suspended run resumes through the tool
            # path (seed_usage summed) rather than the no-tools gateway path.
            tool_defs = (
                frontend_tool_defs(editor=False, book_scoped=False)
                + frontend_tool_defs(editor=True, book_scoped=True)
            )
        if composer_model is not None:
            from app.services.composer import compose_prose_defs
            tool_defs = tool_defs + compose_prose_defs()
        use_tools = bool(tool_defs)

    # Delete the suspended run up front — the 2nd pass owns the turn now.
    await delete_suspended_run(pool, run_id)

    # P-1 step-runner — if this suspend carried a rail book, re-fetch the rail context so the
    # resumed turn KEEPS DRIVING the rail (e.g. after a categories confirm applies, drive on to
    # the cast, connections, plan, draft). Without this the rail stalls at the confirm (measured
    # 2/5). Degrade-safe: no book / any failure ⇒ inert, resume behaves as before.
    _r_rail_specs, _r_rail_grant, _r_rail_counts, _r_rail_async = [], False, None, frozenset()
    _r_rail_progress: list = []
    if settings.rail_driver_enabled and susp.book_id:
        (
            _r_rail_specs, _r_rail_grant, _r_rail_counts, _r_rail_async, _r_rail_progress,
        ) = await _compute_rail_drive_context(
            pool, user_id, susp.book_id, susp.permission_mode, session_id, knowledge_client,
        )

    # 🔴 U-2's THIRD PATH, and it had NEITHER half. A resume re-derives its whole surface from
    # scratch (WS-3), so it hits the same catalogue fetch and the same outage — and the notice
    # existed only on the fresh-turn prompt. The resumed model would then explain a missing
    # capability with nothing to explain it from, which is the founding defect on a different turn
    # shape. The rehydrated conversation has no tail_blocks to hang this on, so it is appended as
    # its own system message.
    if instrument.catalogue_outage_registered():
        working = list(working) + [
            {"role": "system", "content": CATALOGUE_UNAVAILABLE_NOTICE},
        ]

    async for line in _emit_chat_turn(
        session_id=session_id,
        user_message_content=susp.user_message_content,
        user_id=user_id,
        model_source=susp.model_source,
        model_ref=susp.model_ref,
        creds=creds,
        pool=pool,
        billing=billing,
        parent_message_id=susp.parent_message_id,
        project_id=str(project_id) if project_id else None,
        stream_format=stream_format,
        editor_context={"resumed": True},  # truthy so the frontend tool stays advertised
        admin_token=admin_token,  # T4c: keep admin routing on the resume pass
        messages=working,
        gen_params=gen_params,
        tool_defs=tool_defs,
        use_tools=use_tools,
        knowledge_client=knowledge_client,
        fe_memory_mode=None,  # already sent in run 1
        msg_id=susp.message_id,  # share the assistant message id across both runs
        seed_usage=(susp.input_tokens, susp.output_tokens),
        composer_model=composer_model,
        composer_system_prompt=composer_system_prompt,
        planner_model_ref=planner_model_ref,
        # H9/H11: an agui resume continues a frontend-tool turn → keep a rich cap
        # (universal when discovery is on, else the book-scoped cap) so the
        # post-Apply/Confirm follow-up isn't truncated.
        max_iterations=(
            UNIVERSAL_TOOL_ITERATIONS if resume_discovery_catalog is not None
            else GLOSSARY_TOOL_ITERATIONS if stream_format == "agui"
            else MAX_TOOL_ITERATIONS
        ),
        discovery_catalog=resume_discovery_catalog,
        discovery_extra_frontend=resume_extra_frontend,
        discovery_seed_names=resume_seed_names,
        curated=tool_pins.curated_mode,
        activation_state=tool_pins.activation_state,
        surface_tracker=resume_surface_tracker,
        injected_skills=resume_injected_skills,
        effective_enabled_count=len(tool_pins.effective_enabled) if tool_pins.curated_mode else 0,
        hot_seed_count=len(resume_seed_names or ()),
        # RAID C2 — the resume continues under the mode the turn started with;
        # the approved/denied tool result (if any) is surfaced first.
        permission_mode=susp.permission_mode,
        pre_tool_chunks=pre_tool_chunks,
        is_resume=True,  # P3 review H1 — resume runs stateless over the full saved context
        # P-1 step-runner — keep driving the rail on the resumed turn. context_ids carries the
        # rail's book (also lets arg-injection fill book_id on the resumed writes).
        #
        # 🔴 …AND THE `studio` FLAG, WHICH THIS DICT USED TO DROP. `_inject_context_ids` reads
        # `context_ids["studio"]` to decide whether a valid-but-DIFFERENT book_id is a
        # hallucination to override or a legitimate cross-book call to honor. Rebuilt with
        # book_id alone, it defaulted to False, so the single-book override was dead on every
        # resumed turn — measured 2026-08-12: after an approval the model called
        # composition_package_tree and plan_propose_spec with the book's knowledge-project id
        # and no override fired, while the same wrong id HAD been overridden one pass earlier.
        context_ids=(
            {
                "book_id": susp.book_id,
                "studio": bool(susp.studio),
                # …AND THE OTHER TWO IDS, 2026-08-24. This dict has now lost a field THREE
                # times — `studio` (fixed 2026-08-12), then chapter_id and project_id — each
                # time because it is rebuilt BY HAND from a suspension row rather than carried.
                # Absent chapter_id is not a missing nicety: it is what let a chapter id go out
                # as `book_id` on every resumed turn, which the book-scope check then refuses.
                "chapter_id": susp.chapter_id,
                "project_id": susp.project_id,
            }
            if susp.book_id
            else None
        ),
        rail_specs=_r_rail_specs or None,
        rail_grant_ok=_r_rail_grant,
        rail_turn_start_counts=_r_rail_counts,
        rail_async_tools=_r_rail_async,
        # A resume is "in flight" ONLY when the suspend was itself a rail STEP — not merely a
        # suspend on a book that happens to have a rail pinned (review MED: `bool(_r_rail_specs)`
        # alone would drive the rail on an unrelated propose_edit / approval suspend, exactly the
        # unprompted-start regression the fresh path's "a rail tool succeeded this turn" gate
        # exists to prevent). The suspended tool must be one of the rail's own step tools.
        rail_in_flight=bool(_r_rail_specs)
        and (susp.pending_tool_call or {}).get("name") in set(susp.pinned_step_tools or []),
        # Action-space gating on resume — turn-start progress recomputed by the rail-drive context.
        rail_progress=_r_rail_progress or None,
        # NB: the rail_user_abandoned flag is computed INSIDE _emit_chat_turn from its
        # user_message_content (= susp.user_message_content, passed above) before it calls
        # _stream_with_tools — the resume path needs no extra arg for THAT one.
        #
        # 🔴 R1 IS A DIFFERENT ARGUMENT, AND OMITTING IT MADE THE GUARANTEE INERT ON EVERY
        # RESUMED TURN. `_emit_chat_turn(request_text="")` is the documented off switch ("Empty
        # ⇒ inert"), and the per-pass advertise chokepoint is reached only through here — so
        # from the approval onward, no tool could be rescued onto the wire by its own declared
        # vocabulary. The one-off `_advertise_discovery_tools` call above passes the same text
        # and says why: "A resume is still answering the ORIGINAL request." That was true for
        # its first tool_defs and false for every pass after it.
        #
        # MEASURED 2026-08-23, K=5: asked to "Back up ... cite where it says ...",
        # glossary_create_evidence (which DECLARES both "back up" and "cite where") was
        # advertised on every pass before the card and on none after it, 5 runs of 5 — the
        # resume re-seeds with studio=True and the composition family took its slot at an
        # unchanged 41-tool budget. Displacement by domain selection is precisely what R1
        # overrules; it just never saw the request.
        request_text=susp.user_message_content,
    ):
        yield line


# Interview-roleplay (M5) — executive cadence. Every N assistant turns, fire a
# best-effort executive pass that updates working_memory.state; the window is the
# last K turns sent to knowledge-service so it needn't call back into chat.
EXECUTIVE_EVERY_N_TURNS = 4
EXECUTIVE_TURN_WINDOW = 12


async def _fire_executive_tick(
    session_id: str, user_id: str, model_source: str, model_ref: str, pool: asyncpg.Pool,
) -> None:
    """Gather the recent-turns window and run one executive pass (best-effort).

    Passes the session's own model — the executive runs on it. A failure is
    swallowed: the anchor still holds from the existing block / seed, so a missed
    tick only delays the next state update."""
    try:
        rows = await pool.fetch(
            """
            SELECT role, content FROM chat_messages
            WHERE session_id=$1 AND is_error=false AND branch_id=0
            ORDER BY sequence_num DESC LIMIT $2
            """,
            session_id, EXECUTIVE_TURN_WINDOW,
        )
        recent = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
        await get_knowledge_client().tick_working_memory(
            session_id=session_id, user_id=user_id,
            model_source=model_source, model_ref=model_ref, recent_turns=recent,
        )
    except Exception:
        logger.warning("executive tick failed for session %s", session_id, exc_info=True)


# Phrases a title-gen model echoes instead of producing a title — the prompt
# leaking back ("The system instruction says…", "Generate a concise title…") or
# a refusal. A candidate containing one is rejected outright.
_TITLE_ECHO_MARKERS = (
    "generate a concise title",
    "the system instruction",
    "here is the title",
    "here's the title",
    "title:",
    "as an ai",
    "i cannot",
)
# Leading list/enumeration/markdown noise a model prepends: "4.", "1)", "- ",
# "* ", "#", "> ", a bullet glyph.
_TITLE_LEADING_NOISE = __import__("re").compile(r"^\s*(?:[-*#>•·]+|\d+[.)])\s*")


def _sanitize_title(raw: str) -> str:
    """Turn a raw title-gen output into a usable title, or "" if it is
    degenerate. Fixes the live bug where a model emitting ``"4."``, ``"* Eerie
    Lighthouse…"`` or the prompt echo was saved verbatim as the chat title.

    Rules: first non-empty line only; strip leading list/number/markdown markers
    and wrapping quotes/emphasis; reject an echo of the prompt, a pure
    punctuation/number fragment, or anything under 2 words."""
    if not raw:
        return ""
    line = next((l.strip() for l in raw.splitlines() if l.strip()), "")
    prev = None
    while line != prev:  # peel repeatedly: "* 1. Title" -> "Title"
        prev = line
        line = _TITLE_LEADING_NOISE.sub("", line)
        line = line.strip().strip("`*_\"'").strip()
    line = " ".join(line.split())
    low = line.lower()
    if any(m in low for m in _TITLE_ECHO_MARKERS):
        return ""
    # must carry real words: >= 2 whitespace-separated tokens with a letter
    word_tokens = [t for t in line.split() if any(c.isalpha() for c in t)]
    if len(word_tokens) < 2:
        return ""
    return line if len(line) <= 100 else ""


async def _auto_generate_title(
    session_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
    model_source: str,
    model_ref: str,
    pool: asyncpg.Pool,
) -> None:
    """Generate a short title via the LLM gateway. Phase 1c-ii: routes
    through `loreweave_llm.Client.stream()` and accumulates tokens
    instead of calling AsyncOpenAI/litellm directly. Title generation is
    short enough (≤200 tokens) that streaming-then-collect is cheap."""
    title_messages = [
        {
            "role": "system",
            "content": "Generate a concise title (max 6 words) for this conversation. "
            "Return ONLY the title, no quotes, no explanation. "
            "Do NOT think or reason — just output the title directly.",
        },
        {"role": "user", "content": user_message[:300]},
        {"role": "assistant", "content": assistant_message[:300] if assistant_message else "(responded)"},
        {"role": "user", "content": "Title:"},
    ]
    try:
        client = Client(
            base_url=settings.provider_registry_internal_url,
            auth_mode="internal",
            internal_token=settings.internal_service_token,
            user_id=user_id,
            idle_read_timeout_s=settings.llm_stream_idle_read_timeout_s,
        )
        try:
            request = StreamRequest(
                model_source=model_source,
                model_ref=model_ref,
                messages=title_messages,
                temperature=0.3,
                max_tokens=200,  # Extra budget for thinking models
            )  # noqa — title gen has explicit non-None values, no kwargs sparsity needed
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            async for ev in client.stream(request):
                if isinstance(ev, TokenEvent):
                    content_parts.append(ev.delta)
                elif isinstance(ev, ReasoningEvent):
                    reasoning_parts.append(ev.delta)
        finally:
            await client.aclose()

        raw_content = "".join(content_parts).strip()
        raw_reasoning = "".join(reasoning_parts).strip()

        # Prefer content; fall back to the last meaningful line of reasoning.
        # Both run through _sanitize_title, which strips list/markdown noise and
        # REJECTS a degenerate candidate (the "4." / prompt-echo bug) → "".
        title = _sanitize_title(raw_content)
        if not title and raw_reasoning:
            lines = [
                l.strip()
                for l in raw_reasoning.split("\n")
                if l.strip()
                and not l.strip().startswith("Okay")
                and not l.strip().startswith("Let me")
            ]
            title = _sanitize_title(lines[-1]) if lines else ""

        if title:  # _sanitize_title already enforced len <= 100 + non-degenerate
            await pool.execute(
                """
                UPDATE chat_sessions SET title = $2, updated_at = now()
                WHERE session_id = $1 AND title = 'New Chat'
                """,
                session_id, title,
            )
    except Exception:
        logger.debug("Auto-title generation failed for session %s", session_id, exc_info=True)
