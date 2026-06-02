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
)

from app.client.billing_client import BillingClient
from app.client.knowledge_client import get_knowledge_client
from app.config import settings
from app.db.suspended_runs import (
    delete_suspended_run,
    load_suspended_run,
    save_suspended_run,
)
from app.models import ProviderCredentials
from app.services.frontend_tools import is_frontend_tool
from app.services.output_extractor import extract_outputs
from app.services.stream_events import make_emitter

logger = logging.getLogger(__name__)


@dataclass
class _Usage:
    """Mirror the shape of openai's CompletionUsage so existing
    `getattr(last_usage, 'prompt_tokens', None)` call sites keep working
    after the SDK migration."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


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
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
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
        await client.aclose()


# ── K21-B: tool-calling loop ────────────────────────────────────────────────

# Max LLM passes per chat turn. Passes 0..N-2 may call tools; the final
# pass is forced tool-free (tool_choice="none") so the loop always
# terminates with a text answer (design D7).
MAX_TOOL_ITERATIONS = 5


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

        for iteration in range(MAX_TOOL_ITERATIONS):
            last_iter = iteration == MAX_TOOL_ITERATIONS - 1
            request_kwargs: dict = {
                "model_source": model_source,
                "model_ref": model_ref,
                "messages": working,
            }
            if gen_params.get("temperature") is not None:
                request_kwargs["temperature"] = gen_params["temperature"]
            if max_tokens is not None:
                request_kwargs["max_tokens"] = max_tokens
            # Offer tools unless the provider rejected them (D8) or this
            # is the forced-final pass (D7 — must answer in text).
            offered_tools = tools_supported and not last_iter
            if offered_tools:
                request_kwargs["tools"] = tools
                request_kwargs["tool_choice"] = "auto"
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
            for c in calls:
                if is_frontend_tool(c["name"]):
                    suspended_call = {
                        "id": c["id"],
                        "name": c["name"],
                        "args": _parse_tool_args(c["arguments"]),
                    }
                    break
                # backend tool — execute inline (existing path, below)
                args_obj = _parse_tool_args(c["arguments"])
                if settings.use_mcp_tools:
                    envelope = await knowledge_client.mcp_execute_tool(
                        user_id=user_id, session_id=session_id, project_id=project_id,
                        tool_name=c["name"], tool_args=args_obj,
                    )
                else:
                    envelope = await knowledge_client.execute_tool(
                        user_id=user_id, session_id=session_id, project_id=project_id,
                        tool_name=c["name"], tool_args=args_obj,
                    )
                ok = bool(envelope.get("success"))
                tool_payload = envelope.get("result") if ok else {"error": envelope.get("error")}
                working.append({
                    "role": "tool", "tool_call_id": c["id"],
                    "content": json.dumps(tool_payload),
                })
                yield {"tool_call": {
                    "id": c["id"], "iteration": iteration, "tool": c["name"],
                    "args": args_obj, "ok": ok,
                    "result": envelope.get("result") if ok else None,
                    "error": None if ok else envelope.get("error"),
                }}

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

        # MAX_TOOL_ITERATIONS exhausted. The final pass is forced
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
    disable_tools: bool = False,
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
    without spending its budget deciding whether to call a tool."""

    # ── Load session settings ───────────────────────────────────────────────
    session_row = await pool.fetchrow(
        "SELECT system_prompt, generation_params, project_id FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    system_prompt = session_row["system_prompt"] if session_row else None
    gp_raw = session_row["generation_params"] if session_row else {}
    if isinstance(gp_raw, str):
        gp_raw = json.loads(gp_raw)
    gen_params: dict = gp_raw if gp_raw else {}
    # asyncpg.Record supports .get() since 0.27; using it lets test mocks
    # that pass a plain dict without project_id continue to work.
    project_id = session_row.get("project_id") if session_row else None

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
        if system_prompt and system_prompt.strip():
            parts.append({
                "type": "text",
                "text": system_prompt.strip(),
                "cache_control": {"type": "ephemeral"},
            })
        messages.insert(0, {"role": "system", "content": parts})
    else:
        system_parts: list[str] = []
        if kctx.context:
            stripped = kctx.context.strip()
            if stripped:
                system_parts.append(stripped)
        if system_prompt:
            stripped = system_prompt.strip()
            if stripped:
                system_parts.append(stripped)
        if system_parts:
            messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

    # Inject per-message context as a system message right before the last user message
    if context:
        messages.insert(-1, {"role": "system", "content": f"The user has attached the following context:\n\n{context}"})

    # ── Phase 1c-ii: gateway resolves api_key / base_url / model_string
    # internally; service no longer needs them. We keep `creds.provider_kind`
    # for the Anthropic cache_control branch above.

    # ── K21-B: resolve memory tools ─────────────────────────────────────────
    # Offer tool-calling when the project hasn't opted out
    # (kctx.tool_calling_enabled) AND knowledge-service serves the tool
    # schemas. A fetch failure → empty list → the turn runs tool-free.
    tool_defs: list[dict] = []
    if not disable_tools and kctx.tool_calling_enabled:
        tool_defs = await knowledge_client.get_tool_definitions()
        # ARCH-1 C6: advertise the editor write-back frontend tool ONLY for the
        # editor <Chat> panel (agui + editor_context present). Other clients
        # (standalone chat page, voice) never see it, so the memory_* path is
        # unaffected.
        if stream_format == "agui" and editor_context:
            from app.services.frontend_tools import frontend_tool_defs
            tool_defs = tool_defs + frontend_tool_defs()
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
        messages=messages,
        gen_params=gen_params,
        tool_defs=tool_defs,
        use_tools=use_tools,
        knowledge_client=knowledge_client,
        fe_memory_mode=fe_memory_mode,
        msg_id=str(uuid4()),
        seed_usage=None,
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
    fe_memory_mode: str | None,
    msg_id: str,
    seed_usage: tuple[int, int] | None,
) -> AsyncGenerator[str, None]:
    """Shared Stream→persist→finish body for a chat turn (fresh OR C6 resume).

    Consumes chunks from the LLM (tool loop or plain), emits AG-UI/legacy events,
    persists the assistant message, and runs post-turn best-effort work. When the
    tool loop yields a ``suspend`` chunk (a frontend tool awaiting client
    execution), this persists the suspended run instead and emits a "suspended"
    finish — NO assistant message is written (the turn isn't done yet)."""
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

    turn_succeeded = False
    post_finish_state: dict | None = None

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
        try:
            current_count = await pool.fetchval(
                "SELECT message_count FROM chat_sessions WHERE session_id = $1",
                session_id,
            )
        except Exception:
            logger.warning(
                "auto-title count lookup failed for session %s (post-finish)",
                session_id, exc_info=True,
            )
            current_count = None
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
    outcome: str,
    applied_text: str | None,
    creds: ProviderCredentials,
    pool: asyncpg.Pool,
    billing: BillingClient,
    stream_format: str = "agui",
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
    result_payload = {"outcome": outcome}
    if applied_text is not None:
        result_payload["applied_text"] = applied_text
    working.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result_payload),
    })

    # Re-derive session gen_params + tool defs for the 2nd pass.
    session_row = await pool.fetchrow(
        "SELECT generation_params, project_id FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    gp_raw = session_row["generation_params"] if session_row else {}
    if isinstance(gp_raw, str):
        gp_raw = json.loads(gp_raw)
    gen_params: dict = gp_raw if gp_raw else {}
    project_id = session_row.get("project_id") if session_row else None

    knowledge_client = get_knowledge_client()
    tool_defs: list[dict] = []
    try:
        tool_defs = await knowledge_client.get_tool_definitions()
    except Exception:
        tool_defs = []
    # The editor tool stays advertised on resume (the agent may propose again).
    # Append it WHENEVER agui — mirror the fresh path (stream_response), which
    # adds the frontend tool regardless of whether memory tools are present.
    # Gating on `tool_defs` was a bug: with no memory tools (no project) the
    # frontend tool was dropped AND the run fell through to the no-tools gateway
    # path, which ignores seed_usage → resume usage was NOT summed across the two
    # runs (caught by C6 live smoke). Going through _stream_with_tools keeps the
    # seed and re-advertises the tool.
    if stream_format == "agui":
        tool_defs = tool_defs + frontend_tool_defs()
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
        messages=working,
        gen_params=gen_params,
        tool_defs=tool_defs,
        use_tools=use_tools,
        knowledge_client=knowledge_client,
        fe_memory_mode=None,  # already sent in run 1
        msg_id=susp.message_id,  # share the assistant message id across both runs
        seed_usage=(susp.input_tokens, susp.output_tokens),
    ):
        yield line


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
