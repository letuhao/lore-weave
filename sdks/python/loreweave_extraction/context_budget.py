"""Model-context-aware budgeting for extraction LLM calls.

Why this exists
---------------

The Pass-2 extractors (entity / relation / event / fact / summarize_level)
historically used a hardcoded ``ChunkingConfig(strategy="paragraphs",
size=15)``. That works for an English chapter on a generous-context
cloud model, but fails at the seams that real local deployments hit:

- **Local-quantized 35B models** typically load with 24-32K context to
  fit in 24GB VRAM. A Chinese / Vietnamese 15-paragraph chunk packs
  4× more tokens than English (CJK ≈ 400 tok/para vs English ≈ 100),
  so a multilingual fixture can blow through 12K of input alone.

- **Slot-allocating servers** (llama.cpp / LM Studio / vLLM) reserve
  ``max_tokens`` per slot. Three parallel R+E+F gather calls × 4096
  max_tokens × per-slot KV overhead can exceed the loaded context
  window → ``failed to find a memory slot for batch`` →
  ``purging slot N with 2838 tokens`` errors observed live.

- **Cloud models** also cap context (gpt-4o = 128K, claude-haiku =
  200K). The pipeline must be context-aware to work across the
  deployment matrix, not just on the model the developer happened to
  test against.

Design
------

A single ``ContextBudget`` dataclass owns all the per-model arithmetic:

  - ``input_budget_for(system_prompt_tokens)`` — tokens left over for
    the user message after subtracting the system prompt, max_tokens,
    and a safety margin.

  - ``max_paragraphs_per_chunk(system_prompt_tokens, lang)`` —
    paragraph count that fits the input budget, respecting language-
    aware token density (CJK packs more tokens per paragraph).

  - ``max_parallel_slots()`` — how many concurrent extractor calls
    the model_context can plausibly host without slot purging.

Token estimation is a cheap char-based heuristic (no tiktoken dep —
the SDK stays self-contained). Production-tuned, not exact.

Callers
-------

  - Extractors (entity / relation / event / fact / summarize_level)
    accept an optional ``context_budget`` kwarg. When passed, they
    use the computed chunk size; when omitted, they fall back to the
    legacy ``size=15`` for backward-compat.

  - ``pass2_orchestrator.gather_relations_events_facts`` builds the
    budget once per chapter, threads it to all three extractors, and
    uses ``max_parallel_slots()`` to bound the asyncio.gather degree.

  - Provider-registry's job submit handler pre-flights a chunk-fit
    check against the model's registered ``context_length`` and
    rejects 400 BAD_REQUEST when the request would overflow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final, Literal

__all__ = [
    "ContextBudget",
    "Language",
    "estimate_text_tokens",
    "estimate_paragraph_count",
    "DEFAULT_MODEL_CONTEXT",
    "DEFAULT_MAX_OUTPUT_TOKENS",
]

Language = Literal["en", "zh", "ja", "ko", "vi", "auto"]

# Conservative default for unknown / unregistered models. 8K matches
# the smallest commonly-deployed cloud chat models (gpt-3.5-turbo).
# Real models always set this explicitly via user_models.context_length.
DEFAULT_MODEL_CONTEXT: Final[int] = 8192

# Output ceiling for extraction JSON. Matches the constant the four
# extractors set in their input dicts. Bumping here doesn't change the
# request budget — the extractor's own ``max_tokens`` is the wire
# value; this is the budget calculator's assumption.
DEFAULT_MAX_OUTPUT_TOKENS: Final[int] = 4096

# Per-language token density estimates (tokens / paragraph).
# Tuned empirically: English BPE ≈ 1.3 tok/word × ~75 words/para;
# Chinese/Japanese ~1.5 tok/char × ~150 chars/para; Vietnamese
# diacritics + space-separated words ~2 tok/word × ~80 words/para.
# Conservative bias — better to overstate density (smaller chunks)
# than understate (overflow context).
_PARA_TOKENS_BY_LANG: Final[dict[Language, int]] = {
    "en": 110,
    "zh": 380,
    "ja": 380,
    "ko": 250,
    "vi": 180,
    # "auto" resolves to max() at compute time — safest default
    "auto": 380,
}

# Per-character token density for the raw estimator. Charset-aware
# so a CJK string doesn't get counted as 1 token / 4 chars (English
# BPE default) when each character is actually ~1.5 tokens.
_CHAR_TOKEN_BUDGET_EN = 4.0   # chars / token
_CHAR_TOKEN_BUDGET_CJK = 0.7  # chars / token (each char ≈ 1.4 tokens)

# Per-slot KV-cache overhead estimate (tokens). Beyond the
# input + max_tokens, llama.cpp / vLLM reserve some bookkeeping for
# attention state. Tuned conservative; real overhead varies by model
# arch + quantization. Used only for max_parallel_slots arithmetic.
_PER_SLOT_OVERHEAD: Final[int] = 1024


def _detect_lang_simple(text: str) -> Language:
    """Cheap CJK/non-CJK detection. Counts CJK chars in a 400-char
    prefix; if >25% CJK, returns "zh" (used as a proxy for all CJK
    since per-char density is similar). Otherwise "en".

    Production replacement: language-detection from book-service +
    pass-through via project metadata. This is the local default for
    when the caller doesn't supply language.
    """
    if not text:
        return "en"
    sample = text[:400]
    cjk_count = sum(
        1 for c in sample
        # CJK Unified, Hiragana, Katakana, Hangul ranges
        if "぀" <= c <= "ヿ" or "一" <= c <= "鿿"
        or "가" <= c <= "힯"
    )
    if cjk_count > len(sample) * 0.25:
        return "zh"
    return "en"


def estimate_text_tokens(text: str, lang: Language | None = None) -> int:
    """Estimate token count for ``text`` using a charset-aware
    char/token heuristic. Faster + deterministic vs tiktoken; close
    enough for budget arithmetic (the safety_margin absorbs the slop).

    Production callers needing exact counts (e.g. billing) should use
    the tokenizer; this is for chunk-sizing only.
    """
    if not text:
        return 0
    resolved = lang or _detect_lang_simple(text)
    if resolved in ("zh", "ja", "ko"):
        return math.ceil(len(text) / _CHAR_TOKEN_BUDGET_CJK)
    return math.ceil(len(text) / _CHAR_TOKEN_BUDGET_EN)


def estimate_paragraph_count(text: str) -> int:
    """Count non-empty paragraphs (blank-line-separated) in ``text``.
    Matches the gateway's chunker.go ``chunkByParagraphs`` definition
    so the chunk-size math stays consistent end-to-end."""
    if not text or not text.strip():
        return 0
    return sum(1 for p in text.split("\n\n") if p.strip())


@dataclass(frozen=True)
class ContextBudget:
    """Per-call context budget arithmetic.

    Caller obligations:
      - ``model_context``: the model's loaded context window (NOT the
        full architectural max — local quants often load smaller).
      - ``max_output_tokens``: what the extractor will set in its
        ``input.max_tokens``. Must match the wire value or budget
        math is wrong.
      - ``safety_margin_pct``: headroom for KV overhead, tokenizer
        slop, prompt-substitution growth. 0.15 = 15% conservative
        default.
    """

    model_context: int
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    safety_margin_pct: float = 0.15
    # Approximation of per-slot KV overhead beyond input+output.
    # Overridable for testing; default fits llama.cpp 7B-70B range.
    per_slot_overhead_tokens: int = _PER_SLOT_OVERHEAD

    def __post_init__(self) -> None:
        if self.model_context <= 0:
            raise ValueError(f"model_context must be > 0, got {self.model_context}")
        if self.max_output_tokens <= 0:
            raise ValueError(f"max_output_tokens must be > 0, got {self.max_output_tokens}")
        if not 0 <= self.safety_margin_pct < 1.0:
            raise ValueError(
                f"safety_margin_pct must be in [0, 1), got {self.safety_margin_pct}"
            )

    @property
    def safety_margin(self) -> int:
        """Absolute token headroom subtracted from the input budget."""
        return int(self.model_context * self.safety_margin_pct)

    def input_budget_for(self, system_prompt_tokens: int) -> int:
        """Tokens available for the user message (chunk text) after
        accounting for the system prompt + reserved output + safety.

        Returns max(0, ...) so callers can detect "no budget left"
        as a zero — they should reject such requests before
        submitting (a chunk_size of zero is meaningless).
        """
        used = system_prompt_tokens + self.max_output_tokens + self.safety_margin
        return max(0, self.model_context - used)

    def max_paragraphs_per_chunk(
        self,
        system_prompt_tokens: int,
        lang: Language = "auto",
    ) -> int:
        """Compute the largest paragraph count whose token sum fits
        within ``input_budget_for(system_prompt_tokens)``.

        Returns at least 1 — a chunk of one paragraph that itself
        overflows is the caller's problem (we never silently
        emit a chunk_size that mathematically can't fit a single
        paragraph, but we don't guarantee the chosen size always
        fits the WORST paragraph either).
        """
        budget = self.input_budget_for(system_prompt_tokens)
        if budget <= 0:
            return 1
        per_para = _PARA_TOKENS_BY_LANG[lang]
        return max(1, budget // per_para)

    def max_parallel_slots(self) -> int:
        """Estimate the number of concurrent slot reservations the
        loaded context window can host without purging.

        Each slot reserves (max_output_tokens + per_slot_overhead +
        a workload-proportional share of the system prompt). We use
        a conservative input estimate of ~3K tokens since extraction
        system prompts run 1.5-2.5K.

        Caps at 3 because the orchestrator only fires 3 concurrent
        extractors (R/E/F gather); no caller wants more than that.
        """
        per_slot_input_estimate = 3000
        per_slot = (
            per_slot_input_estimate
            + self.max_output_tokens
            + self.per_slot_overhead_tokens
        )
        raw = max(1, self.model_context // per_slot)
        return min(3, raw)

    def fits_input(self, input_tokens: int, system_prompt_tokens: int = 0) -> bool:
        """Predicate: would ``input_tokens`` (chunk text) fit alongside
        the system prompt + max_output + safety in this model's
        context? Used by gateway pre-flight."""
        return input_tokens <= self.input_budget_for(system_prompt_tokens)


def _build_budget_for_model(
    model_context: int | None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> ContextBudget:
    """Convenience constructor with safe defaults. Caller passes None
    when model context is unknown (legacy code paths, tests)."""
    return ContextBudget(
        model_context=model_context or DEFAULT_MODEL_CONTEXT,
        max_output_tokens=max_output_tokens,
    )
