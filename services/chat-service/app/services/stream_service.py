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
from collections import Counter
import logging
import re
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
from app.config import settings
from app.db.suspended_runs import (
    delete_suspended_run,
    load_suspended_run,
    save_suspended_run,
)
from app.db.tool_approvals import approve_tool, get_tool_decision, set_tool_decision
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
    generic_frontend_tool_def,
    is_frontend_tool,
)
from app.services.tool_discovery import (
    ALWAYS_ON_CORE_NAMES,
    FIND_TOOLS_DEFAULT_LIMIT,
    FIND_TOOLS_NAME,
    FIND_TOOLS_TOOL,
    TOOL_LIST_NAME,
    TOOL_LIST_TOOL,
    TOOL_LOAD_NAME,
    TOOL_LOAD_TOOL,
    find_tools_result_async,
    group_directory_text,
    hot_tool_names,
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
from app.services.rail_progress import user_abandoned_rail
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
    inline). Returns ``(rail_specs, grant_ok, turn_start_counts, async_tools)`` or the inert
    ``([], False, None, frozenset())`` on any failure — the resume then simply does not drive.
    """
    try:
        from app.client.grant_client import GrantLevel, get_grant_client
        from app.client.registry_workflows_client import get_workflows_client
        from app.db.tool_call_history import succeeded_tool_counts

        wfs = await get_workflows_client().get_workflows(
            str(user_id), book_id=str(book_id), surface="book", mode=permission_mode,
        )
        binding = wfs.mode_binding
        if not (binding and binding.inject_workflows):
            return [], False, None, frozenset()
        visible = {w.get("slug") for w in wfs.workflows if w.get("slug")}
        pinned = [s for s in binding.inject_workflows if s in visible]
        if not pinned:
            return [], False, None, frozenset()
        lvl, _ = await get_grant_client().resolve_access(UUID(str(book_id)), UUID(str(user_id)))
        if lvl < GrantLevel.VIEW:
            return [], False, None, frozenset()
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
        return rail_specs, True, counts, async_tools
    except Exception:  # noqa: BLE001 — the driver is never load-bearing
        logger.warning("resume rail-drive context failed — rail not driven on resume", exc_info=True)
        return [], False, None, frozenset()


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


def _degemmify_tool_args(raw: str) -> str:
    """Strip Gemma 4's native tool-call wrapper/quote tokens, and quote bare
    object keys, so the result is plausible JSON worth a `json.loads` retry.
    A no-op (returns `raw` unchanged) when none of the tokens are present."""
    text = _GEMMA_TOOLCALL_TAIL_RE.sub("", _GEMMA_TOOLCALL_WRAP_RE.sub("", raw))
    text = _GEMMA_QUOTE_TOKEN_RE.sub('"', text)
    return _UNQUOTED_KEY_RE.sub(r' "\1":', text)


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
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        pass
    for candidate in (_degemmify_tool_args(raw), raw):
        if not _braces_balanced(candidate):
            continue
        try:
            parsed = json.loads(repair_json(candidate))
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed:
            return parsed
    logger.warning(
        "tool-call arguments unparseable after repair attempts, degrading to {}: %r",
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


def _advertise_discovery_tools(
    catalog_index: dict[str, dict],
    active_tool_names: set[str],
    extra_frontend: list[dict],
    permission_mode: str = "write",
    has_workflows: bool = False,
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
        out.append(strip_tool_meta(td))

    # Always-on core: prefer the catalog's own def (if a core tool is federated),
    # else the consumer-local find_tools schema or a generic frontend-tool schema
    # (ui_*/confirm/propose). find_tools is NOT federated, so it has no catalog
    # entry — source it from FIND_TOOLS_TOOL.
    for name in ALWAYS_ON_CORE_NAMES:
        if name == FIND_TOOLS_NAME:
            _add(FIND_TOOLS_TOOL)
            continue
        # WS-1a — tool_list/tool_load are consumer-local meta-tools (not federated), like
        # find_tools; source their schemas from the module defs.
        if name == TOOL_LIST_NAME:
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
    for name in active_tool_names:
        td = catalog_index.get(name)
        if (
            restricted and td is not None and tool_tier(td) != "R"
            and not (plan and _is_plan_tool(name))
        ):
            continue
        _add(td)
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
        if name == FIND_TOOLS_NAME or is_frontend_tool(name):
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
    if key not in ("args", "arguments"):
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
})


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


def _inject_context_ids(
    args_obj: dict,
    tool_def: dict | None,
    *,
    book_id: str | None,
    chapter_id: str | None,
    project_id: str | None,
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
    params = tool_def.get("function", {}).get("parameters", {})
    props = params.get("properties", {}) if isinstance(params, dict) else {}
    if not props:
        return args_obj
    for key, val in (("book_id", book_id), ("chapter_id", chapter_id), ("project_id", project_id)):
        if not val or key not in props:
            continue
        supplied = args_obj.get(key)
        if not supplied:
            args_obj[key] = val
            continue
        if isinstance(supplied, str) and not _is_uuid(supplied):
            logger.warning(
                "tool arg %s=%r is not a UUID — the model mistranscribed it; substituting the "
                "turn's known id", key, supplied[:64],
            )
            args_obj[key] = val
    return args_obj


def _is_uuid(v: str) -> bool:
    try:
        UUID(str(v))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _missing_required_names(args_obj: dict, tool_def: dict | None) -> list[str]:
    """The REQUIRED arg names this call is still missing (post context-id injection).
    Unknown tool_def → [] (can't classify → never block a call we can't judge)."""
    if not tool_def:
        return []
    params = tool_def.get("function", {}).get("parameters", {})
    required = params.get("required", []) if isinstance(params, dict) else []
    return [r for r in required if not args_obj.get(r)]


def _missing_required_args(args_obj: dict, tool_def: dict | None) -> bool:
    """True iff this call is still missing a REQUIRED arg (post context-id injection).

    Used to keep the blank-tool-args cap from collateral-damaging a WELL-FORMED call: a
    mid-tier model that spams one malformed tool (e.g. glossary_search without `query`)
    builds the streak, and the cap would then block a DIFFERENT, valid call (e.g.
    glossary_book_ontology_read with book_id present) that would actually succeed. Only a
    call that is ITSELF still missing required args should be short-circuited."""
    return bool(_missing_required_names(args_obj, tool_def))


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
        # ── P-1 step-runner state (Track C) ──────────────────────────────────────
        # turn_succeeded — tools that SUCCEEDED this turn (backend chokepoint only), merged with
        # the turn-start DB counts to tell "the async job already started" from "not yet". Never
        # overrides an artifact verdict (that is compute_rail_progress's job).
        turn_succeeded: Counter = Counter()
        rail_redrive_count = 0           # per-turn cap on how many times the server re-drives
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
                    advertised = _advertise_discovery_tools(
                        cat_index, active_tool_names, extra_fe,
                        permission_mode=permission_mode,
                        has_workflows=bool(turn_workflows),
                    )
                else:
                    advertised = (
                        _filter_tools_for_ask(tools, permission_mode)
                        if permission_mode in ("ask", "plan") else tools
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
                            if _nm and is_frontend_tool(_nm):
                                _fe_tok += _tok
                            else:
                                _mcp_tok += _tok
                        _schema_split = {"frontend": _fe_tok, "mcp": _mcp_tok}
                        yield {"schema_tokens": {
                            "frontend_tool_schemas": _fe_tok,
                            "mcp_tool_schemas": _mcp_tok,
                        }}
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
                            elif is_frontend_tool(_nm):
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
                else:
                    # Ask mode filtered everything out — run the pass tool-free
                    # (an empty tools array 400s on some providers).
                    offered_tools = False
            # M3 — one observability/cancel job id PER pass (each pass is a
            # separate gateway stream; the active pass is what a disconnect aborts).
            stream_job_id = str(uuid4())
            request_kwargs["stream_job_id"] = stream_job_id
            _apply_reasoning_kwargs(request_kwargs, gen_params)
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
            finish_reason: str | None = None
            try:
                async for ev in client.stream(request):
                    if isinstance(ev, TokenEvent):
                        text_parts.append(ev.delta)
                        content_hold += ev.delta
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
                if (
                    settings.rail_driver_enabled
                    and rail_specs
                    and rail_book_id
                    and rail_grant_ok
                    and rail_redrive_count < RAIL_REDRIVE_CAP
                    and not last_iter
                    # G2: the deploy strength "off" disables the drive entirely (the pre-drive rail).
                    and settings.rail_enforcement != "off"
                    # GOV-13 escape hatch: an explicit "skip the plan" / "just write" releases the
                    # hold this turn — governance serves the author, it never imprisons them.
                    and not rail_user_abandoned
                    and write_passes < max_iterations - 1
                    # In flight = a rail tool succeeded THIS turn (the model chose to start it),
                    # OR this is a resume that suspended mid-rail (the confirm executes off the
                    # backend chokepoint, so it never lands in turn_succeeded — but the rail is
                    # unambiguously in flight, so the driver must be allowed to continue it).
                    and (rail_in_flight or (set(turn_succeeded) & _rail_all_step_tools))
                ):
                    # ACP A2 (RW-3): the drive+enforcement DECISION lives in the SDK harness
                    # (decide_rail_drive) — it unifies the fresh re-probe, next_actionable_step, and
                    # the nudge-cap/strength/give-up logic into one verdict. The probe is INJECTED
                    # (RW-11). This loop OWNS the mechanics: inject the directive as a role=user
                    # message, bump the counters, drop the stateful chain head, continue.
                    from app.services.book_state_probe import probe_book_state
                    from loreweave_agent_control import decide_rail_drive
                    _verdict = await decide_rail_drive(
                        probe_fn=probe_book_state,
                        rail_specs=rail_specs, book_id=rail_book_id, user_id=user_id,
                        turn_start_counts=rail_turn_start_counts, turn_succeeded=turn_succeeded,
                        async_tools=rail_async_tools, nudged_out=rail_twice_nudged,
                        nudge_counts=rail_nudge_counts,
                        enforcement_strength=settings.rail_enforcement,
                        required_nudge_cap=settings.rail_required_nudge_cap,
                    )
                if _verdict is not None and _verdict.should_drive:
                    _step = _verdict.step
                    # Record the narration the model just streamed, then the ephemeral directive.
                    # `working` is never persisted (the assistant row persists the yielded
                    # content), so the synthetic user directive never reaches history or the UI.
                    working.append({"role": "assistant", "content": "".join(text_parts)})
                    working.append({"role": "user", "content": _verdict.directive_text})
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
                    include_deprecated = args_obj.get("include_deprecated")
                    if not isinstance(include_deprecated, bool):
                        include_deprecated = True
                    payload = tool_list_result(
                        discovery_catalog or [],
                        category,
                        include_deprecated=include_deprecated,
                        exclude=set(ALWAYS_ON_CORE_NAMES),
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
                    )
                    from app.services.tool_surface import (
                        HOT_SEED_TOKEN_BUDGET,
                        budget_names_by_tokens,
                    )
                    # review-impl #1 (WS-1a): tool_load returns FULL schemas — unlike find_tools
                    # (names only). A tool_load(category="all"/big) would re-inject the exact
                    # catalog bloat the discovery layer exists to prevent. Bound the RETURNED
                    # schemas (not just activation) by the same token ceiling the hot-seed uses;
                    # a single-/few-name load always fits, only a large category truncates.
                    names_to_activate = budget_names_by_tokens(
                        discovery_catalog or [], loaded,
                        token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
                    )
                    if len(names_to_activate) < len(loaded):
                        _keep = set(names_to_activate)
                        payload["tools"] = [t for t in payload["tools"] if t["name"] in _keep]
                        payload["truncated"] = True
                        payload["note"] = (
                            f"Loaded {len(names_to_activate)} of {len(loaded)} tools (token budget). "
                            "Call tool_load with specific names to load the rest."
                        )
                    if not loaded and not payload.get("not_found"):
                        # review-impl #3: nothing requested — guide instead of a silent empty result.
                        payload["note"] = (
                            "No tool was requested — pass `name`, `names`, or a `category` "
                            "(use tool_list to see what's available)."
                        )
                    active_tool_names.update(names_to_activate)
                    if curated and activation_state is not None:
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
                            budget_names_by_tokens,
                            merge_activated_tools,
                        )
                        names_to_activate = budget_names_by_tokens(
                            discovery_catalog or [], step_tools,
                            token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
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
                        catalog_meta=knowledge_client.get_catalog_meta(),
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
                            budget_names_by_tokens,
                        )
                        names_to_activate = budget_names_by_tokens(
                            discovery_catalog or [], matched,
                            token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
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
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": _parse_tool_args(c["arguments"]), "ok": False,
                        "result": None, "error": _deny_err,
                    }}
                    continue

                if is_frontend_tool(c["name"]):
                    # Same gemma {"args":{…}} wrap-repair the backend dispatch does below —
                    # a wrapped frontend-tool payload must be unwrapped BEFORE it is frozen
                    # into the suspended run, or the resume/resolver sees the envelope instead
                    # of the real fields. Load-bearing for the rail: its confirm gate
                    # (glossary_confirm_action) is a frontend tool, and a wrapped confirm_token
                    # would strand the confirm on resume. Protect ui_show_panel's real `args`
                    # param via its schema (generic index for ui_*/propose_*, catalog for
                    # domain confirm tools) — never a bare tool_def=None here.
                    _fe_def = (
                        cat_index.get(c["name"])
                        or plain_index.get(c["name"])
                        or generic_frontend_tool_def(c["name"])
                    )
                    suspended_call = {
                        "id": c["id"],
                        "name": c["name"],
                        "args": _unwrap_wrapped_args(_parse_tool_args(c["arguments"]), _fe_def),
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
                )
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
                _missing_args = _missing_required_names(
                    args_obj, cat_index.get(c["name"]) or plain_index.get(c["name"])
                )
                if _missing_args:
                    blank_tool_args_streak += 1
                    if blank_tool_args_streak >= BLANK_TOOL_ARGS_CAP:
                        _ma_msg = (
                            f"'{c['name']}' keeps being called with missing/blank required "
                            "arguments this turn — STOP. Tell the user you couldn't complete this "
                            "rather than retrying with empty arguments."
                        )
                    else:
                        _ma_msg = (
                            f"'{c['name']}' is missing required argument(s): {_missing_args}. "
                            "These carry the actual CONTENT (not ids the system already fills) — "
                            "e.g. a list of the items to create, or the search text. Read the "
                            "tool's schema for their exact shape, fill them in, and call again. "
                            "Do not call it with only ids or empty arguments."
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
                _prior = read_call_results.get(_read_key) if _read_key is not None else None
                if _prior is not None and _prior[1] >= REPEAT_READ_CAP:
                    _repeat_err = (
                        f"You have already called '{c['name']}' with these exact arguments "
                        f"{_prior[1] + 1} times this turn and it returned the IDENTICAL result "
                        "every time — that result is already above, in this conversation. "
                        "Calling it again cannot tell you anything new. STOP calling it. Read "
                        "the result you already have, and take the NEXT step."
                    )
                    logger.info(
                        "repeated-read breaker: %s returned an unchanged result %d× — short-circuited",
                        c["name"], _prior[1],
                    )
                    working.append({
                        "role": "tool", "tool_call_id": c["id"],
                        "content": tool_result_content({"error": _repeat_err}),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": False, "result": None, "error": _repeat_err,
                    }}
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

                # backend tool — execute via the ai-gateway over MCP (ai-gateway
                # P0: the only tool transport). Tier-A auto-commits here (the
                # "lazy man" path); Tier-W/S domain tools MINT a confirm_token and
                # return it (no write) — the agent then calls the confirm_action
                # frontend tool, which suspends for the human gate.
                # T4c: on an admin surface, pass the RS256 admin token so
                # glossary_admin_* route to /mcp/admin (no X-User-Id; INV-T2).
                envelope = await knowledge_client.mcp_execute_tool(
                    user_id=user_id, session_id=session_id, project_id=project_id,
                    tool_name=c["name"], tool_args=args_obj,
                    admin_token=admin_token,
                )
                ok = bool(envelope.get("success"))
                # P-1 step-runner — the single backend chokepoint where every rail step tool
                # executes. Count a success only for a tool the pinned rail actually names, so
                # the driver's "a rail step succeeded this turn" gate stays honest. (Confirm/
                # frontend tools suspend BEFORE this line and are correctly never counted.)
                if ok and c["name"] in _rail_all_step_tools:
                    turn_succeeded[c["name"]] += 1
                tool_payload = envelope.get("result") if ok else {"error": envelope.get("error")}
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
                    # A tool that actually COMMITTED (Tier-A auto-write) changed the world, so
                    # every earlier read is now potentially stale and re-reading it is
                    # legitimate again. Only Tier-A: a Tier-W/S "propose" writes NOTHING (it
                    # mints a confirm_token), so clearing on it would let the exact loop shape
                    # the breaker exists for — propose → read → propose → read — reset itself
                    # forever. The real write those proposals cause lands later, via the
                    # confirm path, and clears the ledger then.
                    read_call_results.clear()
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
        "compact_summary, compacted_before_seq, message_count, created_at "  # A4 (RV-M5): anchor progress + wrap
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
    # emit structured system content with `cache_control` markers on
    # BOTH the stable-memory prefix AND the session-level system_prompt.
    # Anthropic allows up to 4 cache breakpoints per request; we use 2:
    #   parts[0]: stable memory (L0 + project + Mode-2/3 prefix up to </project>)
    #     → cached; changes only when L0 / project summary / memory-mode flip
    #   parts[1]: volatile memory (Mode-2/3 glossary + facts + passages)
    #     → NOT cached; changes per-message by intent
    #   parts[2]: session system_prompt (persona / tone / instructions)
    #     → cached; stable per-session, doesn't change between turns
    # Non-Anthropic providers and the degraded / unsplit fallback take
    # the plain-string path.
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
        book_context_note = f"You are working inside book_id={_ctx_book_id}."
        if _ctx_chapter_id:
            book_context_note += f" The active chapter is chapter_id={_ctx_chapter_id}."
        if _ctx_project_id:
            book_context_note += (
                f" This book's composition/knowledge project is project_id={_ctx_project_id}"
                " — pass it verbatim to any tool that requires a project_id"
                " (a book_id is NOT a project_id)."
            )
        book_context_note += (
            " Use these exact ids for any tool that requires a book_id or chapter_id."
            " Never ask the user for the book_id and never pass a placeholder."
        )
        book_context_note += _ORIENTATION_SCENT  # 28 AN-9 / AN-C2 — the discovery scent

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
    if not disable_tools and kctx.tool_calling_enabled and not admin_context:
        _turn_catalog = await knowledge_client.get_tool_definitions(user_id=user_id)
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
            tool_defs = await knowledge_client.get_admin_tool_definitions(admin_token)
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
                from app.services.frontend_tools import frontend_tool_defs, _is_panel_nav_intent
                from app.services.tool_discovery import filter_intent_gated_setup_tools
                editor = bool(editor_context)
                book_scoped = bool(editor_context or book_context)
                # F7c M4 — advertise the studio panel navigator only on a navigation-intent
                # turn (unless the gate is disabled). Saves ~880 tok on plain writing turns.
                _panel_nav = (not settings.studio_panel_intent_gated) or _is_panel_nav_intent(user_message_content)
                # N5a-FULL — capability floor: high-impact world-setup tools are dropped from the
                # turn catalog (all three reach-paths) unless this turn is world-setup intent
                # (glossary_shaping injected). Request-scoped autonomy for the co-writer.
                discovery_catalog = filter_intent_gated_setup_tools(catalog, injected_skill_codes)
                discovery_extra_frontend = frontend_tool_defs(
                    editor=editor, book_scoped=book_scoped, studio=bool(studio_context),
                    compact_studio_panel=settings.compact_studio_panel_desc,  # F7c
                    studio_panel_nav=_panel_nav,  # F7c M4 — nav-intent gate
                )
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
                )
                # `tool_defs` is the FIRST-pass advertisement when discovery is on;
                # _stream_with_tools recomputes it each pass (core ∪ extra_fe ∪
                # {seed ∪ discovered}), but a non-empty value flips use_tools True.
                tool_defs = _advertise_discovery_tools(
                    _catalog_index(catalog), discovery_seed_names, discovery_extra_frontend
                )
            else:
                # No discovery: a legacy non-agui tool-calling client (full catalog —
                # it has no find_tools loop), or an agui surface with the gateway down.
                tool_defs = catalog
                if stream_format == "agui" and (editor_context or book_context or studio_context):
                    # Gateway down but still agui: re-advertise the frontend
                    # write-back / studio-nav tools so the surface can still
                    # propose/confirm/navigate (mirrors the resume path's catalog-down branch).
                    from app.services.frontend_tools import frontend_tool_defs, _is_panel_nav_intent
                    tool_defs = tool_defs + frontend_tool_defs(
                        editor=bool(editor_context),
                        book_scoped=bool(editor_context or book_context),
                        studio=bool(studio_context),
                        compact_studio_panel=settings.compact_studio_panel_desc,  # F7c
                        studio_panel_nav=(
                            (not settings.studio_panel_intent_gated)
                            or _is_panel_nav_intent(user_message_content)
                        ),  # F7c M4 — nav-intent gate
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
    ):
        yield line


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

    # RAID C2 (DR-C2 §4) + Track D S-SPEND — the per-user allowlist read, handed to
    # the loop as a callable so _stream_with_tools stays DB-free. ``kind`` selects the
    # consent axis ("mutation" | "spend"); each is a separate row. The loop decides
    # how to degrade on a read error (mutation fails OPEN, spend fails CLOSED).
    # Track C WS-3 — returns the standing DECISION ('allow' | 'deny' | None), so ONE
    # read answers both "may it run?" and "has the user forbidden it?".
    async def _decision_check(tool_name: str, kind: str = "mutation") -> str | None:
        return await get_tool_decision(pool, user_id, tool_name, kind)

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

            chunk_stream = _stream_with_tools(
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
                    "project_id": project_id,
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
            )
        else:
            chunk_stream = _stream_via_gateway(
                model_source=model_source,
                model_ref=model_ref,
                user_id=user_id,
                messages=messages,
                gen_params=gen_params,
            )

        async for chunk_data in chunk_stream:
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
                continue
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
            for line in emitter.finish(
                finish, status="suspended",
                pending={"runId": run_id, "toolCallId": pending["id"],
                         "toolName": pending["name"]},
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
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages "
                    "WHERE session_id = $1 AND branch_id = 0",
                    session_id,
                )
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
                tool_calls_json = (
                    json.dumps(tool_calls_history) if tool_calls_history else None
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
                await conn.execute(
                    """
                    INSERT INTO chat_messages
                      (message_id, session_id, owner_user_id, role, content, content_parts,
                       sequence_num, input_tokens, output_tokens, model_ref, parent_message_id, branch_id, tool_calls,
                       context_breakdown, response_id, exclude_from_memory, local_date)
                    VALUES ($1,$2,$3,'assistant',$4,$5::jsonb,$6,$7,$8,$9,$10, 0, $11::jsonb, $12::jsonb, $13, $14, $15)
                    """,
                    msg_id, session_id, user_id, final_text, content_parts, seq,
                    input_tok, output_tok, model_ref, parent_message_id, tool_calls_json,
                    json.dumps(_ctx_payload), _final_response_id, _exclude_mem,
                    _local_date,  # DBT-11 — bucket by the user's LOCAL day (resolved before acquire)
                )
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

                # Update session stats
                await conn.execute(
                    """
                    UPDATE chat_sessions
                    SET message_count = message_count + 1,
                        last_message_at = now(),
                        updated_at = now()
                    WHERE session_id = $1
                    """,
                    session_id,
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

        # Send custom data annotation (IDs back to frontend)
        data_payload: dict = {"message_id": msg_id}
        if artifacts:
            data_payload["output_id"] = output_id
        if final_reasoning:
            data_payload["has_reasoning"] = True
        for line in emitter.persisted_data(data_payload):
            yield line

        if activation_state and activation_state.get("dirty"):
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
            except Exception:
                logger.warning(
                    "failed to persist activated_tools for session %s",
                    session_id,
                    exc_info=True,
                )

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

    except Exception as exc:
        logger.exception("Stream error for session %s", session_id)
        # Sanitize error message — don't leak internal details
        safe_msg = str(exc)
        if any(kw in safe_msg.lower() for kw in ("traceback", "file ", "/usr/", "password", "secret")):
            safe_msg = "An internal error occurred. Please try again."
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

        # Log usage async (non-blocking)
        if post_finish_state["last_usage"]:
            asyncio.create_task(
                billing.log_usage(
                    user_id=user_id,
                    model_source=model_source,
                    model_ref=model_ref,
                    provider_kind=creds.provider_kind,
                    input_tokens=post_finish_state["input_tok"] or 0,
                    output_tokens=post_finish_state["output_tok"] or 0,
                    session_id=session_id,
                    message_id=msg_id,
                    input_payload={"messages": messages},
                    output_payload={
                        "content": post_finish_state["final_text"],
                        "reasoning": post_finish_state["final_reasoning"] or None,
                    },
                )
            )

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

    susp = await load_suspended_run(pool, run_id, user_id)
    if susp is None or susp.pending_tool_call.get("id") != tool_call_id:
        # Unknown/expired/mismatched — surface a clean AG-UI error.
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
    if not is_approval:
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

    # Re-derive session gen_params + tool defs for the 2nd pass.
    session_row = await pool.fetchrow(
        "SELECT generation_params, project_id, system_prompt, composer_model_source, composer_model_ref, "
        "planner_model_ref, enabled_tools, enabled_skills, activated_tools "
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

    # RAID C2 (DR-C2 §4) — act on the approval outcome BEFORE the 2nd pass:
    #   approved_once   → execute the tool now; feed its REAL result back.
    #   approved_always → persist the allowlist row, then execute.
    #   denied          → feed {"error": "denied by user"} so the model
    #                     self-corrects (no execution).
    # The executed call is surfaced via pre_tool_chunks (tool_call + activity
    # events + persisted history) — C-ACTIVITY parity, undo unchanged.
    pre_tool_chunks: list[dict] | None = None
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
            envelope = await knowledge_client.mcp_execute_tool(
                user_id=user_id, session_id=session_id,
                project_id=str(project_id) if project_id else None,
                tool_name=_tool_name, tool_args=_tool_args,
                admin_token=admin_token,
            )
            _ok = bool(envelope.get("success"))
            _tool_payload = envelope.get("result") if _ok else {"error": envelope.get("error")}
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
            pre_tool_chunks = [_chunk]
        else:
            working.append({
                "role": "tool", "tool_call_id": tool_call_id,
                "content": tool_result_content({"error": "denied by user"}),
            })
            pre_tool_chunks = [{
                "id": tool_call_id, "iteration": 0, "tool": _tool_name,
                "args": _tool_args, "ok": False,
                "result": None, "error": "denied by user",
            }]

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
            # N5a-FULL — same capability floor on the resume path (mirror the fresh turn).
            resume_discovery_catalog = filter_intent_gated_setup_tools(catalog, resume_injected_skills)
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
            )
            tool_defs = _advertise_discovery_tools(
                _catalog_index(catalog), resume_seed_names, resume_extra_frontend
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
    if settings.rail_driver_enabled and susp.book_id:
        _r_rail_specs, _r_rail_grant, _r_rail_counts, _r_rail_async = await _compute_rail_drive_context(
            pool, user_id, susp.book_id, susp.permission_mode, session_id, knowledge_client,
        )

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
        context_ids={"book_id": susp.book_id} if susp.book_id else None,
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
        # NB: the rail_user_abandoned flag is computed INSIDE _emit_chat_turn from its
        # user_message_content (= susp.user_message_content, passed above) before it calls
        # _stream_with_tools — the resume path needs no extra arg here.
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

        # Prefer content; fall back to last meaningful line of reasoning.
        if raw_content:
            title = raw_content.strip().strip('"').strip("'")
        elif raw_reasoning:
            lines = [
                l.strip()
                for l in raw_reasoning.split("\n")
                if l.strip()
                and not l.strip().startswith("Okay")
                and not l.strip().startswith("Let me")
            ]
            title = lines[-1].strip().strip('"').strip("'") if lines else ""
        else:
            title = ""

        if title and len(title) <= 100:
            await pool.execute(
                """
                UPDATE chat_sessions SET title = $2, updated_at = now()
                WHERE session_id = $1 AND title = 'New Chat'
                """,
                session_id, title,
            )
    except Exception:
        logger.debug("Auto-title generation failed for session %s", session_id, exc_info=True)
