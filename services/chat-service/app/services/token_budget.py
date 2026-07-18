"""Script-aware token estimation + context-budget accounting (RAID Wave A / A1-A2).

A flat ``chars/4`` heuristic under-counts CJK/Vietnamese by 4-8x (edge #1) — and the
POC is Vietnamese ("Ma Nữ Nghịch Thiên") + Chinese ("万古神帝"). This estimates by
unicode script class: CJK ≈ 1 token/char, Vietnamese-with-diacritics denser than plain
Latin, ASCII ≈ chars/4. It is **provider-agnostic** (works for local lm_studio / Qwen /
Gemma AND Claude) — the measured ``promptTokens`` from the provider usage remains ground
truth; this estimate is the PRE-SEND projection + the per-bucket breakdown the meter
shows (the compaction trigger keys off measured tokens post-turn).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Script-aware token estimation moved to the shared Context Budget kernel (T3.3a,
# `loreweave_context.tokens`). Re-exported here so every existing caller keeps working
# unchanged (compute_budget below, stream_service, compaction, the many importers).
from loreweave_context.tokens import estimate_messages_tokens, estimate_tokens
from loreweave_context.trace import reduction_pct


# ── context-budget accounting (A2) ────────────────────────────────────────────

# Reserve a small safety margin on top of max_tokens so compaction fires before the
# hard LLM_CONTEXT_OVERFLOW guard (input + max_tokens + safety > context_length).
_SAFETY_TOKENS = 512

# ── T2/D3: task-elastic budget target ───────────────────────────────────────
# `compute_target` (the soft-budget band math) moved to the shared Context Budget kernel
# in T3.2 (`loreweave_context.budget`) so the Planner owns it. Re-exported here so every
# existing caller keeps working unchanged: `compute_budget` below (the meter), the
# token-budget tests, and any `from app.services.token_budget import compute_target`.
from loreweave_context.budget import compute_target, scale_by_window  # noqa: E402  (re-export)


@dataclass(frozen=True)
class ContextBudget:
    used_tokens: int
    context_length: int | None      # None → unknown (legacy user_model / local w/o registered ctx)
    max_output_tokens: int
    effective_limit: int | None     # context_length - max_output - safety; None when unknown
    pct: float | None               # used / effective_limit; None when unknown
    target: int | None = None       # T2: soft task-elastic budget (the compaction trigger)
    pct_of_target: float | None = None  # used / target; None when unknown

    def to_event(self) -> dict:
        # STRICTLY ADDITIVE over the original {used_tokens, context_length,
        # effective_limit, pct} keys (FE meter contract). T2 adds target + pct_of_target.
        return {
            "used_tokens": self.used_tokens,
            "context_length": self.context_length,
            "effective_limit": self.effective_limit,
            "pct": round(self.pct, 4) if self.pct is not None else None,
            "target": self.target,
            "pct_of_target": (
                round(self.pct_of_target, 4) if self.pct_of_target is not None else None
            ),
        }


def compute_budget(
    *,
    used_tokens: int,
    context_length: int | None,
    max_output_tokens: int,
    task_weight: float = 1.0,
) -> ContextBudget:
    """Budget from measured/estimated input tokens vs the model's context window.
    NULL context_length (legacy rows) → unknown budget (meter shows '—'). `target`
    is the task-elastic soft budget (T2); `effective_limit` is the near-window hard
    guard (unchanged). `pct` is vs the hard limit; `pct_of_target` is vs the soft one."""
    if context_length is None or context_length <= 0:
        return ContextBudget(used_tokens, None, max_output_tokens, None, None, None, None)
    effective = max(1, context_length - max(0, max_output_tokens) - _SAFETY_TOKENS)
    pct = used_tokens / effective
    target = compute_target(context_length, task_weight=task_weight)
    pct_of_target = (used_tokens / target) if target else None
    return ContextBudget(
        used_tokens, context_length, max_output_tokens, effective, pct,
        target, pct_of_target,
    )


# ── per-category context breakdown (Chat Quality Wave W1) ─────────────────────

# The fixed category vocabulary of the `contextBudget` frame's `breakdown` map.
# Every category is always present in the payload (0 when the part is absent this
# turn) so the FE drill-down renders a stable row set. `memory_knowledge` is the
# one nested entry: {"total": N, "sections": {...}} — the per-section split comes
# from knowledge-service build_context (glossary_entities / facts / passages /
# summaries / instructions / ...).
BREAKDOWN_CATEGORIES: tuple[str, ...] = (
    "system_prompt",           # session persona (chat_sessions.system_prompt)
    "memory_knowledge",        # knowledge-service memory block (total + sections)
    "story_state",             # T4 cached story-bible safety-net block (D4; 0 unless projected)
    "working_memory",          # interview-roleplay anchor (pinned + tail)
    "steering",                # per-book <steering> block (RAID C1)
    "skills",                  # skill L2 bodies + the L1 metadata block (RAID C3)
    "plan_nudge",              # plan-mode system nudge (RAID B2)
    "book_note",               # book/chapter/project id note
    "attached_context",        # per-message attached context
    "history",                 # replayed prior turns
    "tool_results",            # mid-turn role:tool results (this turn)
    "frontend_tool_schemas",   # advertised frontend-tool schemas (FRONTEND_TOOL_NAMES)
    "mcp_tool_schemas",        # advertised server/MCP tool schemas (the rest)
    # T2 forward-declared Inspector categories (§11a). Present (0) until the tier
    # that populates them lands, so the Inspector row set is stable from day one:
    "summary",                 # rolling recall summary (T6 fact-preserving compaction)
    "chapter",                 # whitelisted chapter body — a required contributor (D3)
    "reasoning",               # model reasoning/output budgeted vs the target (D7)
)

# Everything that is in the prompt BEFORE the first user word — the fixed
# overhead the user pays per turn regardless of what they type.
_BASELINE_CATEGORIES: frozenset[str] = frozenset({
    "system_prompt", "memory_knowledge", "story_state", "working_memory", "steering",
    "skills", "plan_nudge", "book_note",
    "frontend_tool_schemas", "mcp_tool_schemas",
})


@dataclass
class ContextBreakdown:
    """Per-category token map for ONE turn, measured at assembly time.

    ``categories`` maps a BREAKDOWN_CATEGORIES key → estimated tokens (script-aware
    ``estimate_tokens``, same heuristic as the budget). ``knowledge_sections`` is the
    per-section split of the ``memory_knowledge`` category, passed through from
    knowledge-service build_context. Mutable on purpose: the tool-schema and
    tool-result buckets are only known later in the turn (advertise chokepoint /
    finish) and are folded in before the frame is emitted."""

    categories: dict[str, int] = field(default_factory=dict)
    knowledge_sections: dict[str, int] = field(default_factory=dict)

    @property
    def baseline_tokens(self) -> int:
        """Tokens present before the first user message: system parts + tool schemas."""
        return sum(
            int(self.categories.get(cat, 0) or 0) for cat in _BASELINE_CATEGORIES
        )

    def to_payload(self) -> dict:
        """The `breakdown` value of the contextBudget frame. Fixed key set —
        every category is present (0 when absent) so the FE row set is stable."""
        out: dict = {}
        for cat in BREAKDOWN_CATEGORIES:
            val = int(self.categories.get(cat, 0) or 0)
            if cat == "memory_knowledge":
                out[cat] = {
                    "total": val,
                    "sections": {k: int(v) for k, v in self.knowledge_sections.items()},
                }
            else:
                out[cat] = val
        return out


def until_compact_pct(pct: float | None) -> float | None:
    """Distance (in pct-of-effective-limit points) from the current usage to the
    compaction trigger — "how much headroom until auto-compact". Reuses the
    trigger ratio from compaction.py (single source for the 0.75). None when the
    budget is unknown; 0.0 once the trigger is reached/passed."""
    if pct is None:
        return None
    # Lazy import, kept defensively: the compaction module (now a re-export shim over
    # loreweave_context.compaction) is a sibling service module; a function-scoped import
    # avoids any import-order coupling at module load.
    from app.services.compaction import COMPACT_TRIGGER_RATIO

    return round(max(0.0, COMPACT_TRIGGER_RATIO - pct), 4)


# ── Inspector telemetry derivation (spec §11a) ───────────────────────────────
# The per-turn contextBudget frame doubles as the Context Compiler · Trace Inspector's
# data source. `intent` + `status_flags` are cheap, HONEST labels derived from signals the
# assembly already has (the T5 gate reason + the compaction/budget outcome) — no new
# classifier, no confabulation. `retrieval_mode` comes from the sealed-decision setting.

# The T5 gate `reason` → a friendly turn-intent label (the Inspector header chip). Maps the
# internal EntityPresence reasons (entity_presence.py) to a short human label; an unknown
# reason falls through to "general" (honest, never invented).
_INTENT_BY_REASON: dict[str, str] = {
    "entity_match": "lore-lookup",
    "lore_intent_bias_include": "lore-discovery",
    "question_bias_include": "question",
    "non_ascii_bias_include": "multilingual",
    "anaphora_bias_include": "follow-up",
    "meta_question": "meta",
    "no_entity_no_anaphora": "status-op",
    "no_entity_set": "general",
    "gate_disabled": "general",
    "empty_message": "general",
}


def derive_intent(entity_presence: dict | None) -> str:
    """A coarse, honest turn-intent label from the T5 gate reason. `general` when the gate
    didn't run / the reason is unknown — never a fabricated category."""
    if not entity_presence:
        return "general"
    return _INTENT_BY_REASON.get(str(entity_presence.get("reason") or ""), "general")


def derive_status_flags(
    *,
    grounding_needed: bool | None,
    compacted: bool = False,
    elastic: bool = False,
    overflowed: bool = False,
    wire: bool = False,
) -> list[str]:
    """The turn's status chips (§11a). Only flags an outcome the assembly actually observed:
    `included`/`gated` from the T5 gate decision (omitted when the gate didn't run →
    grounding_needed None), `compacted` when compaction did work, `elastic` when the soft
    target was task-weighted below 1.0, `overflow` when a result was size-rejected, `wire`
    when T0 serialization actually saved bytes. Order is stable for the FE."""
    flags: list[str] = []
    if grounding_needed is True:
        flags.append("included")
    elif grounding_needed is False:
        flags.append("gated")
    if compacted:
        flags.append("compacted")
    if elastic:
        flags.append("elastic")
    if overflowed:
        flags.append("overflow")
    if wire:
        flags.append("wire")
    return flags


def context_budget_event(
    budget: ContextBudget,
    breakdown: ContextBreakdown | None = None,
    entity_presence: dict | None = None,
    *,
    trace: list[dict] | None = None,
    raw_tokens: int | None = None,
    status_flags: list[str] | None = None,
    retrieval_mode: str | None = None,
    intent: str | None = None,
    llm_call_count: int | None = None,
    caching: dict | None = None,
) -> dict:
    """The full contextBudget frame payload — STRICTLY ADDITIVE over
    ContextBudget.to_event(): the original {used_tokens, context_length,
    effective_limit, pct} keys are byte-identical (FE meter contract); W1 adds
    until_compact_pct always, and breakdown + baseline_tokens when the caller
    measured the parts (the fresh-turn assembly path). T5 adds `entity_presence`
    (the intent-gate decision + matched tokens) when the caller ran the gate — the
    signal the Inspector reads to show WHY grounding was (not) pulled, and to compute
    the false-negative rate (grounding_needed=false turns that still called a
    memory/story search) from the persisted per-turn frames + tool_calls.

    Inspector telemetry (spec §11a, additive; supplied only on the fresh-assembly path):
    `raw_tokens` (naive-concat baseline = compiled + Σ savings) + derived `reduction_pct`,
    the ordered `trace` spans (already ``TraceSpan.to_payload`` dicts), `status_flags`,
    `retrieval_mode`, and `intent`. Each rides WITH the breakdown (the Inspector reads only
    turns that carry one), so resume/degraded frames simply omit them."""
    payload = budget.to_event()
    payload["until_compact_pct"] = until_compact_pct(budget.pct)
    if breakdown is not None:
        payload["breakdown"] = breakdown.to_payload()
        payload["baseline_tokens"] = breakdown.baseline_tokens
    if entity_presence is not None:
        payload["entity_presence"] = entity_presence
    if raw_tokens is not None:
        payload["raw_tokens"] = int(raw_tokens)
        payload["reduction_pct"] = reduction_pct(int(raw_tokens), budget.used_tokens)
    if trace is not None:
        payload["trace"] = trace
    if status_flags is not None:
        payload["status_flags"] = status_flags
    if retrieval_mode is not None:
        payload["retrieval_mode"] = retrieval_mode
    if intent is not None:
        payload["intent"] = intent
    if llm_call_count is not None:
        # Observability (context-explosion fix #5): the number of provider
        # completions this turn made (each tool-loop iteration re-sends the full
        # prompt incl. tool schemas — the SUM of their input IS the real billed
        # cost, tracked separately on chat_messages.input_tokens). `used_tokens`
        # (D-CHAT-CONTEXT-METER-OVERCOUNT, 2026-07-09) is the true occupancy of
        # the LAST completion, not that sum — llm_call_count is what makes the
        # gap between the two legible in the Inspector (billed ≈ used_tokens ×
        # llm_call_count, roughly, when the loop keeps resending a similar size).
        payload["llm_call_count"] = int(llm_call_count)
    if caching is not None:
        # Prompt-cache monitoring section (Provider Context Strategy §7–§8): the
        # per-turn strategy + cache-token split + derived hit-rate / cost-delta /
        # write-premium, plus the rolling thrashing verdict. Built by
        # `caching_monitor.build_caching_metrics` (+ detect_thrashing) so caching is
        # PROVEN-BY-EFFECT — surfaced to the Inspector, not a stored-but-unread blob.
        payload["caching"] = caching
    return payload
