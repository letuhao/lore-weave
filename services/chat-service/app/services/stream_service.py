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
import json
import logging
import re
from dataclasses import dataclass
from typing import AsyncGenerator
from uuid import uuid4

import asyncpg
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

from app.client.billing_client import BillingClient
from app.client.knowledge_client import get_knowledge_client
from app.config import settings
from app.db.suspended_runs import (
    delete_suspended_run,
    load_suspended_run,
    save_suspended_run,
)
from app.db.tool_approvals import approve_tool, is_tool_approved
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
    find_tools_result,
    hot_tool_names,
    strip_tool_meta,
    surface_hot_domains,
    tool_tier,
    tool_undo_hint,
)
from app.services.output_extractor import extract_outputs
from app.services.stream_events import make_emitter
from app.services.compaction import compact_messages
from app.services.token_budget import compute_budget
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


def _thinking_pref(thinking: bool | None, gen_params: dict) -> str:
    """Map the per-request `thinking` toggle (+ the session generation_params
    default) to a UserReasoningPref for resolve_reasoning. True → explicit
    "medium" (matches the legacy thinking_llm_fields enabled→medium), False →
    "off"; None falls back to a session-stored `reasoning_effort`/`thinking`
    default, else the platform default "off" (RE-1: thinking is opt-in)."""
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


def _is_plan_tool(name: str) -> bool:
    """A PlanForge planning tool (allowed in PLAN mode on top of the R surface)."""
    return name.startswith(PLAN_TOOL_PREFIX)


def _is_tools_unsupported(exc: LLMError) -> bool:
    """True when an LLMError is the gateway's 'this provider does not
    support tools' rejection — the K21.11 / design-D8 capability
    fallback. Robust to whether the SDK exposes a `.code` attribute."""
    code = getattr(exc, "code", "") or ""
    return "TOOLS_NOT_SUPPORTED" in code or "TOOLS_NOT_SUPPORTED" in str(exc)


def _parse_tool_args(raw: str) -> dict:
    """Parse a tool call's accumulated `arguments` JSON string. A
    malformed or empty string yields {} so `execute_tool` still receives
    a dict (knowledge-service then surfaces an arg-validation error)."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
        _add(catalog_index.get(name) or generic_frontend_tool_def(name))
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
    discovery_catalog: list[dict] | None = None,
    discovery_extra_frontend: list[dict] | None = None,
    discovery_seed_names: set[str] | None = None,
    curated: bool = False,
    activation_state: dict | None = None,
    surface_tracker=None,
    effective_limit: int | None = None,
    permission_mode: str = "write",
    approval_check=None,
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
      pending card. ``approval_check`` is an async ``(tool_name) -> bool``;
      a raising check fails OPEN (a DB blip must not brick tool calling).
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
    )
    try:
        working: list[dict] = list(messages)
        # C6: on a resume pass, seed the token totals from the suspended first
        # run so the final usage is summed across both runs (design D10).
        total_input = seed_usage[0] if seed_usage else 0
        total_output = seed_usage[1] if seed_usage else 0
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
        # H7 — same-op Tier-A auto-write counter (resets never within a turn).
        tier_a_op_counts: dict[str, int] = {}
        # #18 — per-turn planner-call counter (mechanical hard-stop on the self-recheck loop).
        planner_call_counts: dict[str, int] = {}
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
            if effective_limit:
                try:
                    working, _rc = await compact_messages(
                        working, effective_limit=effective_limit, summarize=_loop_summarizer,
                    )
                    if _rc.triggered:
                        logger.info(
                            "in-loop compaction session=%s pass=%d steps=%s %d→%d overflow=%s",
                            session_id, iteration, _rc.steps,
                            _rc.tokens_before, _rc.tokens_after, _rc.overflowed,
                        )
                except Exception:
                    logger.warning("in-loop compaction skipped (error)", exc_info=True)
            # The write budget — NOT the total-pass count — decides the forced
            # tool-free final pass (D7). Once the write budget is spent, the next
            # pass must answer in text.
            last_iter = write_passes >= max_iterations - 1
            request_kwargs: dict = {
                "model_source": model_source,
                "model_ref": model_ref,
                "messages": working,
            }
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
                    )
                else:
                    advertised = (
                        _filter_tools_for_ask(tools, permission_mode)
                        if permission_mode in ("ask", "plan") else tools
                    )
                if advertised:
                    request_kwargs["tools"] = advertised
                    request_kwargs["tool_choice"] = "auto"
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
            finish_reason: str | None = None
            try:
                async for ev in client.stream(request):
                    if isinstance(ev, TokenEvent):
                        text_parts.append(ev.delta)
                        yield {"content": ev.delta, "reasoning_content": "",
                               "finish_reason": None, "usage": None}
                    elif isinstance(ev, ReasoningEvent):
                        yield {"content": "", "reasoning_content": ev.delta,
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
                    elif isinstance(ev, DoneEvent):
                        finish_reason = ev.finish_reason
            except LLMError as exc:
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

            if not tool_frags:
                # No tool calls — this pass IS the final text response.
                yield {"content": "", "reasoning_content": "",
                       "finish_reason": finish_reason or "stop",
                       "usage": _Usage(prompt_tokens=total_input,
                                       completion_tokens=total_output)}
                return

            # The model called tools — record the assistant turn, execute
            # each call, append the results, and loop.
            calls = _reassemble_tool_calls(tool_frags)
            working.append({
                "role": "assistant",
                "content": "".join(text_parts),
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
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
                    payload, matched = find_tools_result(
                        discovery_catalog or [], intent, limit,
                        exclude=set(ALWAYS_ON_CORE_NAMES),
                        catalog_meta=knowledge_client.get_catalog_meta(),
                    )
                    active_tool_names.update(matched)
                    if curated and activation_state is not None:
                        from app.services.tool_surface import merge_activated_tools
                        activation_state["activated_tools"] = merge_activated_tools(
                            activation_state["activated_tools"], matched,
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
                        "content": json.dumps(payload),
                    })
                    yield {"tool_call": {
                        "id": c["id"], "iteration": iteration, "tool": c["name"],
                        "args": args_obj, "ok": True,
                        "result": payload, "error": None,
                    }}
                    continue
                if surface_tracker is not None:
                    payload_as = surface_tracker.tool_running(c["name"])
                    if payload_as is not None:
                        yield {"agent_surface": payload_as}
                if is_frontend_tool(c["name"]):
                    suspended_call = {
                        "id": c["id"],
                        "name": c["name"],
                        "args": _parse_tool_args(c["arguments"]),
                    }
                    break
                args_obj = _parse_tool_args(c["arguments"])
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
                        "content": json.dumps({"prose": prose}),
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
                            "content": json.dumps({"error": ask_err}),
                        })
                        yield {"tool_call": {
                            "id": c["id"], "iteration": iteration, "tool": c["name"],
                            "args": args_obj, "ok": False,
                            "result": None, "error": ask_err,
                        }}
                        continue

                # MCP-fanout C-TOOL: read the tool's tier (R|A|W|S) from the
                # discovery catalog. Legacy/untiered tools default to R (inert) —
                # they never auto-emit an activity/undo and never count as a write.
                tier = tool_tier(cat_index.get(c["name"], {})) if discovery else "R"

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
                            "content": json.dumps(guidance),
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
                if c["name"] == "glossary_plan" and isinstance(args_obj, dict):
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
                if tier == "A" and permission_mode == "write" and approval_check is not None:
                    _allowed = True
                    try:
                        _allowed = bool(await approval_check(c["name"]))
                    except Exception:
                        logger.warning(
                            "tool-approval allowlist read failed for %s — failing open",
                            c["name"], exc_info=True,
                        )
                        _allowed = True
                    if not _allowed:
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
                tool_payload = envelope.get("result") if ok else {"error": envelope.get("error")}
                working.append({
                    "role": "tool", "tool_call_id": c["id"],
                    "content": json.dumps(tool_payload),
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
                yield {"suspend": {
                    "working": working,
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
            if not offered_tools:
                break

        # Write budget exhausted. The final pass is forced
        # tool-free (D7) so this is unreachable in practice — defensive.
        yield {"content": "", "reasoning_content": "",
               "finish_reason": "stop",
               "usage": _Usage(prompt_tokens=total_input,
                               completion_tokens=total_output)}
    finally:
        await client.aclose()


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
    surfaces) and appends the plan-mode system nudge on both assembly paths."""

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
        "SELECT system_prompt, generation_params, project_id, composer_model_source, composer_model_ref, "
        "planner_model_ref, working_memory_seed, enabled_tools, enabled_skills, activated_tools "
        "FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    system_prompt = session_row["system_prompt"] if session_row else None
    gp_raw = session_row["generation_params"] if session_row else {}
    if isinstance(gp_raw, str):
        gp_raw = json.loads(gp_raw)
    gen_params: dict = gp_raw if gp_raw else {}

    # ── RE: resolve reasoning effort and STASH the provider fields in gen_params ──
    # The `thinking` toggle was previously accepted and dropped (a live no-op). Map
    # it (+ the session default) to a reasoning pref, resolve against the model's
    # reasoning-control style (adaptive Anthropic → omit & self-decide; effort
    # models → send reasoning_effort; non-reasoning → omit), and stash the wire
    # fields so both _stream_via_gateway and _stream_with_tools forward them.
    # Precedence: inline /command > per-msg `thinking` toggle > session > platform.
    _user_pref = _inline_effort or _thinking_pref(thinking, gen_params)
    _directive = resolve_reasoning(
        user_pref=_user_pref,  # type: ignore[arg-type]
        model_control=infer_reasoning_control(creds.provider_kind, creds.provider_model_name),
    )
    _rf = reasoning_fields(_directive)
    # Clear any stale stored knobs first so a directive that says "omit" (adaptive /
    # non-reasoning) doesn't leave a previous run's reasoning_effort in gen_params.
    gen_params.pop("reasoning_effort", None)
    gen_params.pop("chat_template_kwargs", None)
    if _rf:
        gen_params.update(_rf)

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
    kctx = await knowledge_client.build_context(
        user_id=user_id,
        session_id=session_id,
        project_id=str(project_id) if project_id else None,
        message=user_message_content,
        language=display_language,
    )

    # ── Anchoring (interview-roleplay) — resolve the working_memory anchor ────
    # Prefer the live block from knowledge-service (kctx.working_memory); fall
    # back to the session's frozen working_memory_seed (M3 / degraded EC-4).
    # ("", "") for a non-roleplay session → no injection. Pinned goes in the
    # system block (primacy); tail goes right before the latest user turn
    # (recency). Shared with the voice path (EC-3).
    wm_pinned, wm_tail = resolve_anchor(
        kctx.working_memory,
        session_row.get("working_memory_seed") if session_row else None,
    )

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
    history_limit = max(1, kctx.recent_message_count)
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
        resolve_skills_to_inject,
        skill_metadata_block,
        skill_prompts,
    )

    _editor = bool(editor_context)
    _book_scoped = bool(editor_context or book_context)
    _admin = bool(admin_context)
    _session_enabled = list(session_row.get("enabled_tools") or []) if session_row else []
    _session_skills = list(session_row.get("enabled_skills") or []) if session_row else []

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

    injected_skill_codes = resolve_skills_to_inject(
        enabled_skills=effective_skills,
        stream_format=stream_format,
        disable_tools=disable_tools,
        tool_calling_enabled=kctx.tool_calling_enabled,
        editor=_editor,
        book_scoped=_book_scoped,
        admin=_admin,
        # RAID B2 — plan mode auto-injects plan_forge on book/editor surfaces.
        permission_mode=permission_mode,
    )
    _skill_prompts = skill_prompts(injected_skill_codes)
    glossary_skill: str | None = _skill_prompts.get("glossary")
    if "admin" in _skill_prompts:
        glossary_skill = _skill_prompts["admin"]
    universal_skill: str | None = _skill_prompts.get("universal")
    knowledge_skill: str | None = _skill_prompts.get("knowledge")
    # RAID B2 — the PlanForge skill body (pinned, or auto-injected in plan mode).
    plan_forge_skill: str | None = _skill_prompts.get("plan_forge")
    # RAID B2 — the plan-mode system nudge, appended on BOTH assembly paths
    # below (mirrors skill_meta_block) whenever the turn runs in plan mode.
    plan_mode_block: str | None = (
        PLAN_MODE_NUDGE if permission_mode == "plan" else None
    )
    # RAID C3 — L1 skill metadata: a compact "available skills" list injected always
    # (cheap), so the model knows which skills exist on this surface even when only the
    # relevant one's full body (L2) is loaded above.
    skill_meta_block: str | None = None
    if injected_skill_codes:  # only when skills are in play (agui + tools on)
        skill_meta_block = skill_metadata_block(
            editor=_editor, book_scoped=_book_scoped, admin=_admin,
        )

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
    _ctx_book_id = (editor_context or {}).get("book_id") or (book_context or {}).get("book_id")
    _ctx_chapter_id = (editor_context or {}).get("chapter_id")
    book_context_note: str | None = None
    if _ctx_book_id:
        book_context_note = f"You are working inside book_id={_ctx_book_id}."
        if _ctx_chapter_id:
            book_context_note += f" The active chapter is chapter_id={_ctx_chapter_id}."
        book_context_note += (
            " Use these exact ids for any tool that requires a book_id or chapter_id."
            " Never ask the user for the book_id and never pass a placeholder."
        )

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
                )
                steering_block = render_steering_block(_steering_selected) or None
        except Exception:
            logger.warning(
                "steering fetch/render failed for book %s — turn proceeds without steering",
                _ctx_book_id, exc_info=True,
            )
            steering_block = None

    use_anthropic_cache = (
        creds.provider_kind == "anthropic"
        and kctx.stable_context.strip() != ""
    )
    if use_anthropic_cache:
        parts: list[dict] = []
        stable = kctx.stable_context.strip()
        parts.append({
            "type": "text",
            "text": stable,
            "cache_control": {"type": "ephemeral"},
        })
        volatile = kctx.volatile_context.strip()
        if volatile:
            parts.append({"type": "text", "text": volatile})
        if wm_pinned:
            # Pinned anchor (primacy). No cache_control of its own; it sits in
            # the prefix the NEXT breakpoint (system_prompt) caches. Caching is
            # content-addressed, so when the executive changes `state` the anchor
            # text changes and the cache simply MISSES from here — never stale,
            # just re-processed (the anchor is small; the cost is negligible).
            parts.append({"type": "text", "text": wm_pinned})
        if system_prompt and system_prompt.strip():
            parts.append({
                "type": "text",
                "text": system_prompt.strip(),
                "cache_control": {"type": "ephemeral"},
            })
        if steering_block:  # RAID C1 — per-book steering, right after the system prompt
            parts.append({"type": "text", "text": steering_block, "cache_control": {"type": "ephemeral"}})
        if glossary_skill:
            parts.append({"type": "text", "text": glossary_skill, "cache_control": {"type": "ephemeral"}})
        if knowledge_skill:
            parts.append({"type": "text", "text": knowledge_skill, "cache_control": {"type": "ephemeral"}})
        if universal_skill:
            parts.append({"type": "text", "text": universal_skill, "cache_control": {"type": "ephemeral"}})
        if plan_forge_skill:  # RAID B2 — PlanForge flow (pinned or plan-mode)
            parts.append({"type": "text", "text": plan_forge_skill, "cache_control": {"type": "ephemeral"}})
        if plan_mode_block:  # RAID B2 — plan-mode nudge (no prose until Write)
            parts.append({"type": "text", "text": plan_mode_block, "cache_control": {"type": "ephemeral"}})
        if skill_meta_block:  # RAID C3 — L1 available-skills catalog
            parts.append({"type": "text", "text": skill_meta_block, "cache_control": {"type": "ephemeral"}})
        if book_context_note:
            parts.append({"type": "text", "text": book_context_note, "cache_control": {"type": "ephemeral"}})
        messages.insert(0, {"role": "system", "content": parts})
    else:
        system_parts: list[str] = []
        if kctx.context:
            stripped = kctx.context.strip()
            if stripped:
                system_parts.append(stripped)
        if wm_pinned:
            system_parts.append(wm_pinned)
        if system_prompt:
            stripped = system_prompt.strip()
            if stripped:
                system_parts.append(stripped)
        if steering_block:  # RAID C1 — per-book steering, right after the system prompt
            system_parts.append(steering_block)
        if glossary_skill:
            system_parts.append(glossary_skill)
        if knowledge_skill:
            system_parts.append(knowledge_skill)
        if universal_skill:
            system_parts.append(universal_skill)
        if plan_forge_skill:  # RAID B2 — PlanForge flow (pinned or plan-mode)
            system_parts.append(plan_forge_skill)
        if plan_mode_block:  # RAID B2 — plan-mode nudge (no prose until Write)
            system_parts.append(plan_mode_block)
        if skill_meta_block:  # RAID C3 — L1 available-skills catalog
            system_parts.append(skill_meta_block)
        if book_context_note:
            system_parts.append(book_context_note)
        if system_parts:
            messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

    # Inject per-message context as a system message right before the last user message
    if context:
        messages.insert(-1, {"role": "system", "content": f"The user has attached the following context:\n\n{context}"})

    # Tail anchor (recency) — inserted LAST so it sits closest to the latest user
    # turn, where attention weights it most (beats lost-in-the-middle). EC-3/EC-7.
    if wm_tail:
        messages.insert(-1, {"role": "system", "content": wm_tail})

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
            catalog = await knowledge_client.get_tool_definitions()
            # Discovery needs a catalog to search. When the gateway is unreachable
            # (catalog == []), there is nothing to find_tools over → fall back to the
            # plain path rather than spin up a discovery loop with only frontend tools.
            if discovery_eligible and not catalog:
                discovery_eligible = False
            if discovery_eligible:
                from app.services.frontend_tools import frontend_tool_defs
                editor = bool(editor_context)
                book_scoped = bool(editor_context or book_context)
                discovery_catalog = catalog
                discovery_extra_frontend = frontend_tool_defs(
                    editor=editor, book_scoped=book_scoped, studio=bool(studio_context)
                )
                from app.services.tool_surface import discovery_seed_for_surface
                discovery_seed_names = discovery_seed_for_surface(
                    catalog,
                    pins=tool_pins,
                    editor=editor,
                    book_scoped=book_scoped,
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
                    from app.services.frontend_tools import frontend_tool_defs
                    tool_defs = tool_defs + frontend_tool_defs(
                        editor=bool(editor_context),
                        book_scoped=bool(editor_context or book_context),
                        studio=bool(studio_context),
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
        stream_format=stream_format,
        editor_context=editor_context,
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
    ):
        yield line


async def _summarize_for_compaction(
    messages: list[dict], *, model_source: str, model_ref: str, user_id: str,
) -> str:
    """Compaction tier 2 — compress a run of OLDER turns into a dense synopsis so the
    prompt fits the window (compress instead of drop). Provider-agnostic via the LLM
    gateway (works for local lm_studio / Qwen / Gemma AND Claude). A failure RAISES —
    ``compact_messages`` catches it and falls back to deterministic truncation so a
    flaky summarizer can never poison the turn (edge #2)."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content")
        if isinstance(content, list):  # content parts
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        if not content:  # a tool-call turn with no prose — represent it compactly
            tcs = m.get("tool_calls") or []
            names = ", ".join(tc.get("function", {}).get("name", "tool") for tc in tcs)
            content = f"(called {names})" if names else ""
        lines.append(f"{role}: {content}")
    transcript = "\n".join(lines)

    summary_messages = [
        {"role": "system", "content": (
            "You compress the EARLIER part of an ongoing conversation into a dense, "
            "factual synopsis so it fits in context. Preserve named entities, decisions "
            "made, facts established, open threads, and any state the assistant must "
            "keep. Omit pleasantries. Output ONLY the synopsis prose — no preamble, no "
            "headers, and do NOT reason aloud."
        )},
        {"role": "user", "content": f"Conversation excerpt to compress:\n\n{transcript}\n\nSynopsis:"},
    ]
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
    )
    try:
        request = StreamRequest(
            model_source=model_source, model_ref=model_ref,
            messages=summary_messages, temperature=0.2, max_tokens=700,
        )
        parts: list[str] = []
        async for ev in client.stream(request):
            if isinstance(ev, TokenEvent):
                parts.append(ev.delta)
    finally:
        await client.aclose()
    return "".join(parts).strip()


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
    last_usage = None
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
    _eff_limit: int | None = None
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
                messages, effective_limit=_eff_limit, summarize=_summarizer,
            )
            if _compaction.triggered:
                logger.info(
                    "compaction fired session=%s steps=%s tokens %d→%d overflow=%s",
                    session_id, _compaction.steps,
                    _compaction.tokens_before, _compaction.tokens_after,
                    _compaction.overflowed,
                )
    except Exception:  # never let compaction break the turn
        logger.warning("compaction skipped (error)", exc_info=True)

    turn_succeeded = False
    post_finish_state: dict | None = None

    # RAID C2 (DR-C2 §4) — the per-user Tier-A allowlist read, handed to the
    # loop as a callable so _stream_with_tools stays DB-free. The loop wraps it
    # fail-OPEN (a read error must not brick tool calling).
    async def _approval_check(tool_name: str) -> bool:
        return await is_tool_approved(pool, user_id, tool_name)

    try:
        if use_tools:
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
                discovery_catalog=discovery_catalog,
                discovery_extra_frontend=discovery_extra_frontend,
                discovery_seed_names=discovery_seed_names,
                curated=curated,
                activation_state=activation_state,
                surface_tracker=surface_tracker,
                effective_limit=_eff_limit,
                permission_mode=permission_mode,
                approval_check=_approval_check,
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
            await save_suspended_run(
                pool,
                run_id=run_id,
                session_id=session_id,
                owner_user_id=user_id,
                message_id=msg_id,
                working=suspend_state["working"],
                pending_tool_call=pending,
                input_tokens=suspend_state["input_tokens"],
                output_tokens=suspend_state["output_tokens"],
                model_source=model_source,
                model_ref=model_ref,
                parent_message_id=parent_message_id,
                user_message_content=user_message_content,
                permission_mode=permission_mode,
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
        async with pool.acquire() as conn:
            async with conn.transaction():
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages WHERE session_id = $1",
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

                await conn.execute(
                    """
                    INSERT INTO chat_messages
                      (message_id, session_id, owner_user_id, role, content, content_parts,
                       sequence_num, input_tokens, output_tokens, model_ref, parent_message_id, branch_id, tool_calls)
                    VALUES ($1,$2,$3,'assistant',$4,$5::jsonb,$6,$7,$8,$9,$10, 0, $11::jsonb)
                    """,
                    msg_id, session_id, user_id, final_text, content_parts, seq,
                    input_tok, output_tok, model_ref, parent_message_id, tool_calls_json,
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
        # RAID Wave A2 — emit the context budget (measured input tokens vs the model's
        # window) so the FE meter can warn before the next turn. Advisory; NULL
        # context_length → the event carries pct=None and the meter shows "—".
        try:
            _budget = compute_budget(
                used_tokens=int(input_tok or 0),
                context_length=creds.context_length,
                max_output_tokens=int(gen_params.get("max_tokens") or 0),
            )
            for line in emitter.context_budget(_budget.to_event()):
                yield line
        except Exception:  # never let budget accounting break the finish path
            pass
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
            "content": json.dumps(result_payload),
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
    project_id = session_row.get("project_id") if session_row else None
    # A2A phase-2: keep compose_prose available on resume too (the agent may
    # delegate prose again after the user's apply/dismiss).
    composer_src = session_row.get("composer_model_source") if session_row else None
    composer_ref = session_row.get("composer_model_ref") if session_row else None
    composer_model = (composer_src, str(composer_ref)) if composer_src and composer_ref else None
    composer_system_prompt = session_row.get("system_prompt") if session_row else None
    planner_resume_ref = session_row.get("planner_model_ref") if session_row else None
    planner_model_ref = str(planner_resume_ref) if planner_resume_ref else None

    from app.services.skill_registry import resolve_skills_to_inject
    from app.services.tool_surface import resolve_session_tool_pins, discovery_seed_for_surface
    from app.services.agent_surface import AgentSurfaceTracker

    tool_pins = resolve_session_tool_pins(session_row)
    resume_surface_tracker = (
        AgentSurfaceTracker() if stream_format == "agui" else None
    )
    resume_injected_skills = resolve_skills_to_inject(
        enabled_skills=tool_pins.effective_skills,
        stream_format=stream_format,
        disable_tools=False,
        tool_calling_enabled=True,
        editor=True,
        book_scoped=True,
        admin=bool(admin_token),
        # RAID B2 — the resume continues under the suspended turn's mode.
        permission_mode=susp.permission_mode,
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
        _decision = outcome if outcome in ("approved_once", "approved_always", "denied") else "denied"
        if _decision == "approved_always":
            try:
                await approve_tool(pool, user_id, _tool_name)
            except Exception:
                # The human approved THIS call; a failed allowlist write only
                # means they may be prompted again — still execute.
                logger.warning(
                    "always-allow persist failed for %s — executing anyway",
                    _tool_name, exc_info=True,
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
                "content": json.dumps(_tool_payload),
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
                "content": json.dumps({"error": "denied by user"}),
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
            catalog = await knowledge_client.get_tool_definitions()
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
            resume_discovery_catalog = catalog
            # The generic frontend tools (core) + the glossary write-back tools, both
            # available on resume; _stream_with_tools advertises {core} ∪ {discovered}
            # ∪ extra_frontend per pass.
            resume_extra_frontend = (
                frontend_tool_defs(editor=False, book_scoped=False)
                + frontend_tool_defs(editor=True, book_scoped=True)
            )
            # Resume uses editor superset for frontend tools; discovery seed respects
            # session curated pins when enabled_tools is non-empty (story 04 S2).
            resume_seed_names = discovery_seed_for_surface(
                catalog,
                pins=tool_pins,
                editor=True,
                book_scoped=True,
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
