"""T2-close-5 / D-K16.2-01 — per-token USD rates for cost preview.

The extraction-start endpoint uses these to produce the preview
dialog's low/high cost estimate. Values are AVERAGES across each
provider's input/output pricing at the time of pin — preview
accuracy of ±30 % is plenty given the final estimate range is
already widened by 0.7–1.3×.

**This is preview-only.** The real cost guard is K10.4's atomic
`try_spend` in the job runner, which uses actual token counts
from the provider's usage response. Drift in these rates never
causes a budget overrun — it only makes the dialog's "between
$X and $Y" range wrong.

Matching order (in `cost_per_token`):
  1. Exact match on `model_ref`
  2. Longest-prefix match (so `gpt-4o-mini` wins over `gpt-4o`
     for `gpt-4o-mini-2024-07-18`)
  3. Fallback to the legacy `$2 / million tokens` default

Updating a rate is a code change. That's the trade-off the plan
deferral called out: if the provider-registry ever grows a real
pricing table, swap this module for a dynamic lookup (the
`cost_per_token` call site doesn't need to know).
"""
from __future__ import annotations

from decimal import Decimal

__all__ = ["cost_per_token"]


# Rates pinned 2026-04-19. Update when provider pricing shifts.
# A rate of 0 means self-hosted / free marginal cost.
_USD_PER_TOKEN: dict[str, Decimal] = {
    # ── OpenAI (https://openai.com/pricing, average of in/out) ──
    "gpt-4o-mini": Decimal("0.00000030"),  # BEFORE gpt-4o — longer prefix wins
    "gpt-4o": Decimal("0.000005"),
    "gpt-4-turbo": Decimal("0.000015"),
    "gpt-3.5-turbo": Decimal("0.0000010"),
    "o1-mini": Decimal("0.0000030"),
    "o1-preview": Decimal("0.000030"),
    "o1": Decimal("0.000030"),
    "text-embedding-3-small": Decimal("0.00000002"),
    "text-embedding-3-large": Decimal("0.00000013"),
    # ── Anthropic (https://www.anthropic.com/pricing) ──
    "claude-opus-4": Decimal("0.000030"),
    "claude-sonnet-4": Decimal("0.000006"),
    "claude-haiku-4": Decimal("0.000002"),
    "claude-3-5-sonnet": Decimal("0.000006"),
    "claude-3-5-haiku": Decimal("0.000002"),
    "claude-3-opus": Decimal("0.000030"),
    # ── Local / self-hosted (no marginal cost) ──
    "bge-": Decimal("0"),
    "nomic-embed": Decimal("0"),
    "llama-": Decimal("0"),
    "qwen": Decimal("0"),
    "mistral": Decimal("0"),
    "gemma": Decimal("0"),
    "phi-": Decimal("0"),
    # (ollama/ and lm_studio/ prefixes cover everything hosted there
    # by convention — provider_model_name in BYOK rarely carries the
    # prefix, but we catch it defensively.)
    "ollama/": Decimal("0"),
    "lm_studio/": Decimal("0"),
}

# Legacy default — ~$2 / million tokens. Used for unknown models so
# the preview shows SOMETHING rather than $0 for a model we don't
# recognise. Conservative enough that users who see it know to
# compare against their provider's real pricing.
_FALLBACK_USD_PER_TOKEN = Decimal("0.000002")


# Sorted once at module load: longest-prefix first so the iteration
# in `cost_per_token` picks `gpt-4o-mini` before `gpt-4o` for the
# string `gpt-4o-mini-2024-07-18`.
_SORTED_KEYS: list[str] = sorted(_USD_PER_TOKEN.keys(), key=len, reverse=True)


def cost_per_token(model_ref: str) -> Decimal:
    """Return the per-token USD rate for a model reference string.

    Matching order:
      1. Exact match (fast path for explicit pins).
      2. Longest-prefix match (handles versioned names like
         `gpt-4o-2024-08-06` or `claude-sonnet-4-5-20250929`).
      3. Fallback to `_FALLBACK_USD_PER_TOKEN` — preserves the
         previous "conservative guess" behaviour for unknown models.

    Inputs are lower-cased and stripped before matching because
    model-ref strings that land here come from a free-text Pydantic
    field (`StartJobRequest.llm_model`) rather than a canonical
    provider-registry row. Without normalization, `"GPT-4o"` or
    `" gpt-4o "` would silently fall through to the fallback.

    Empty string / None-ish inputs also hit the fallback rather than
    raising — preview is a non-critical path.
    """
    if not model_ref:
        return _FALLBACK_USD_PER_TOKEN
    normalized = model_ref.strip().lower()
    if not normalized:
        return _FALLBACK_USD_PER_TOKEN
    if normalized in _USD_PER_TOKEN:
        return _USD_PER_TOKEN[normalized]
    for key in _SORTED_KEYS:
        if normalized.startswith(key):
            return _USD_PER_TOKEN[key]
    return _FALLBACK_USD_PER_TOKEN
