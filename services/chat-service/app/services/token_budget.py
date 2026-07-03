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

# tokens-per-character factors by script class (empirical BPE approximations; the goal
# is "not 4-8x wrong for CJK/VN", not exactness — the provider usage is ground truth).
_F_CJK = 1.05          # Han / Kana / Hangul — roughly one token per glyph (often 1-2)
_F_VIETNAMESE = 0.55   # Latin + Vietnamese diacritics tokenize far denser than English
_F_LATIN = 0.25        # ASCII letters/digits — the classic chars/4
_F_OTHER = 0.45        # everything else (symbols, other scripts) — a middle guess


def _char_factor(cp: int) -> float:
    # CJK Unified + Ext-A, Kana, Hangul, CJK symbols/compat — the dense scripts.
    if (
        0x4E00 <= cp <= 0x9FFF      # CJK Unified Ideographs
        or 0x3400 <= cp <= 0x4DBF   # CJK Ext-A
        or 0x3040 <= cp <= 0x30FF   # Hiragana + Katakana
        or 0xAC00 <= cp <= 0xD7AF   # Hangul syllables
        or 0xF900 <= cp <= 0xFAFF   # CJK compat ideographs
        or 0x3000 <= cp <= 0x303F   # CJK symbols/punct
        or 0x20000 <= cp <= 0x2FA1F  # CJK Ext-B..F + compat supplement
    ):
        return _F_CJK
    # Vietnamese: Latin Extended Additional (precomposed VN vowels) + combining marks.
    if 0x1EA0 <= cp <= 0x1EFF or 0x0300 <= cp <= 0x036F or cp in (0x0110, 0x0111):
        return _F_VIETNAMESE
    # ASCII letters/digits/space/punct + Latin-1/Extended-A (accented European).
    if cp < 0x0250:
        return _F_LATIN
    return _F_OTHER


def estimate_tokens(text: str | None) -> int:
    """Script-aware token estimate for a string. Not exact — but not 4-8x wrong on
    CJK/Vietnamese the way ``len(text)//4`` is."""
    if not text:
        return 0
    total = 0.0
    for ch in text:
        total += _char_factor(ord(ch))
    # small per-message structural overhead (role/formatting tokens); floor at 1.
    return max(1, round(total))


def estimate_messages_tokens(messages: list[dict] | None) -> int:
    """Estimate the input tokens for a chat `messages` array (role + content)."""
    if not messages:
        return 0
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):  # content parts (text blocks)
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total += estimate_tokens(part["text"])
        # Assistant tool-call turns carry the weight in tool_calls (function name +
        # arguments JSON), often with content=None — count them or a tool-heavy turn
        # is badly under-estimated (matters on the resume / tool-loop path).
        for tc in (m.get("tool_calls") or []):
            fn = tc.get("function") or {}
            total += estimate_tokens(fn.get("name"))
            total += estimate_tokens(fn.get("arguments"))
        total += 4  # per-message role/delimiter overhead (OpenAI-style)
    return total


# ── context-budget accounting (A2) ────────────────────────────────────────────

# Reserve a small safety margin on top of max_tokens so compaction fires before the
# hard LLM_CONTEXT_OVERFLOW guard (input + max_tokens + safety > context_length).
_SAFETY_TOKENS = 512


@dataclass(frozen=True)
class ContextBudget:
    used_tokens: int
    context_length: int | None      # None → unknown (legacy user_model / local w/o registered ctx)
    max_output_tokens: int
    effective_limit: int | None     # context_length - max_output - safety; None when unknown
    pct: float | None               # used / effective_limit; None when unknown

    def to_event(self) -> dict:
        return {
            "used_tokens": self.used_tokens,
            "context_length": self.context_length,
            "effective_limit": self.effective_limit,
            "pct": round(self.pct, 4) if self.pct is not None else None,
        }


def compute_budget(
    *,
    used_tokens: int,
    context_length: int | None,
    max_output_tokens: int,
) -> ContextBudget:
    """Budget from measured/estimated input tokens vs the model's context window.
    NULL context_length (legacy rows) → unknown budget (meter shows '—')."""
    if context_length is None or context_length <= 0:
        return ContextBudget(used_tokens, None, max_output_tokens, None, None)
    effective = max(1, context_length - max(0, max_output_tokens) - _SAFETY_TOKENS)
    pct = used_tokens / effective
    return ContextBudget(used_tokens, context_length, max_output_tokens, effective, pct)


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
)

# Everything that is in the prompt BEFORE the first user word — the fixed
# overhead the user pays per turn regardless of what they type.
_BASELINE_CATEGORIES: frozenset[str] = frozenset({
    "system_prompt", "memory_knowledge", "working_memory", "steering",
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
    # Lazy import: compaction.py imports estimate_messages_tokens from this
    # module, so a top-level import here would be a cycle.
    from app.services.compaction import COMPACT_TRIGGER_RATIO

    return round(max(0.0, COMPACT_TRIGGER_RATIO - pct), 4)


def context_budget_event(
    budget: ContextBudget, breakdown: ContextBreakdown | None = None
) -> dict:
    """The full contextBudget frame payload — STRICTLY ADDITIVE over
    ContextBudget.to_event(): the original {used_tokens, context_length,
    effective_limit, pct} keys are byte-identical (FE meter contract); W1 adds
    until_compact_pct always, and breakdown + baseline_tokens when the caller
    measured the parts (the fresh-turn assembly path)."""
    payload = budget.to_event()
    payload["until_compact_pct"] = until_compact_pct(budget.pct)
    if breakdown is not None:
        payload["breakdown"] = breakdown.to_payload()
        payload["baseline_tokens"] = breakdown.baseline_tokens
    return payload
