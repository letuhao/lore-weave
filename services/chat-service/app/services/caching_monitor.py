"""Prompt-cache cost monitoring (Provider Context Strategy §7–§8).

Caching is NOT free. An explicit-cache provider (Anthropic) bills a WRITE premium
(``cache_creation`` at 1.25×) and a cheap READ (``cache_read`` at 0.1×). If the
cached prefix keeps *changing*, you pay the write premium every turn and never read
it back → net loss ("thrashing"). Automatic-cache providers (OpenAI / LM-Studio /
vLLM / Ollama) have no write charge, so caching there is pure upside and cannot
thrash. This module is the repo's "proven-by-effect" rule applied to $$: caching is
surfaced + measured so it can be shown to actually help.

Everything here is TOKEN-relative — it uses the standard cache-cost multipliers, not
per-token $ pricing — so it needs no pricing lookup on the hot path. ``cost_delta_ratio``
is a signed fraction (positive = saving vs billing every token uncached). Pure +
deterministic: the per-turn ``build_caching_metrics`` feeds the contextBudget frame's
``caching`` section, and the rolling ``detect_thrashing`` is the §7 guardrail.
"""
from __future__ import annotations

from collections.abc import Iterable

# ── per-token cost multipliers, relative to the standard (uncached) input rate ──
# Anthropic explicit cache_control: +25% to write, 90% off to read.
_ANTHROPIC_WRITE_MULT = 1.25
_ANTHROPIC_READ_MULT = 0.10
# Automatic server-side prefix cache (OpenAI/LM-Studio/vLLM/Ollama): NO write charge;
# reads discounted. 0.5 is OpenAI's representative cached-input rate — conservative
# (local backends are effectively free, so this never OVERstates the saving).
_AUTO_WRITE_MULT = 1.0
_AUTO_READ_MULT = 0.5

# strategy labels (spec §8 caching.strategy). "stateful_responses" is reserved for
# Phase 2 — auto-prefix providers are policy-wise STATELESS (chat-service still sends
# the full context; the server caches it invisibly), so they carry the stateless label
# and are distinguished by the `auto_prefix` flag + a non-zero read split.
STRATEGY_STATELESS = "stateless"
STRATEGY_ANTHROPIC_CACHE = "anthropic_cache"
STRATEGY_STATEFUL_RESPONSES = "stateful_responses"  # Phase 2 (not selected yet)

# ── rolling thrashing detector thresholds (§7) ──
_THRASH_MIN_TURNS = 3
_THRASH_HIT_RATIO = 0.5  # read/(read+create) below this over the window ⇒ thrashing


def select_strategy(capabilities: dict[str, bool] | None) -> str:
    """The context-policy strategy label for a provider's declared capabilities.
    Phase 1: anthropic_cache when the provider honors explicit cache_control, else
    stateless (auto-prefix providers are stateless-with-server-side-caching)."""
    caps = capabilities or {}
    if caps.get("prompt_cache_control"):
        return STRATEGY_ANTHROPIC_CACHE
    return STRATEGY_STATELESS


def _mults(capabilities: dict[str, bool] | None) -> tuple[float, float]:
    caps = capabilities or {}
    if caps.get("prompt_cache_control"):
        return _ANTHROPIC_WRITE_MULT, _ANTHROPIC_READ_MULT
    return _AUTO_WRITE_MULT, _AUTO_READ_MULT


def build_caching_metrics(
    *,
    cache_creation_tok: int | None,
    cache_read_tok: int | None,
    input_tok: int | None,
    capabilities: dict[str, bool] | None,
) -> dict:
    """The per-turn ``caching`` section of the contextBudget frame (§8).

    ``input_tok`` is the FULL billed input volume for the turn (the value already on
    the frame's ``used_tokens`` — Anthropic folds its cache split back in, OpenAI's
    prompt_tokens already includes cached), so uncached = input − creation − read
    (floored at 0). All fields are always present (0 / stateless when nothing cached)
    so the Inspector row set is stable. ``thrashing`` is NOT set here — it is a
    rolling-window verdict (see ``detect_thrashing``) folded in by the caller."""
    caps = capabilities or {}
    explicit = bool(caps.get("prompt_cache_control"))
    write_mult, read_mult = _mults(caps)

    create = max(0, int(cache_creation_tok or 0))
    read = max(0, int(cache_read_tok or 0))
    uncached = max(0, int(input_tok or 0) - create - read)
    total = uncached + create + read

    hit_rate = (read / total) if total else 0.0
    # naive = bill every input token at the uncached rate; actual = split by multiplier.
    naive = float(total)
    actual = uncached + create * write_mult + read * read_mult
    cost_delta_ratio = ((naive - actual) / naive) if naive else 0.0
    write_premium_tok = create * (write_mult - 1.0)  # extra paid to WRITE (0 for auto)

    return {
        "strategy": select_strategy(caps),
        # auto_prefix: the server caches automatically (reads may appear on a
        # stateless-labeled turn). False for explicit-cache providers.
        "auto_prefix": bool(caps.get("auto_prefix_cache")) and not explicit,
        "create_tok": create,
        "read_tok": read,
        "uncached_tok": uncached,
        "hit_rate": round(hit_rate, 4),
        "cost_delta_ratio": round(cost_delta_ratio, 4),
        "write_premium_tok": round(write_premium_tok, 1),
        # this-turn honesty signal: did the turn cost MORE than billing it uncached?
        # (Turn-1 cache priming is net_negative but NOT thrashing — see detect_thrashing.)
        "net_negative": (naive - actual) < 0,
    }


def detect_thrashing(
    window: Iterable[tuple[int | None, int | None]],
    *,
    capabilities: dict[str, bool] | None = None,
) -> bool | None:
    """Rolling thrashing verdict (§7). ``window`` = ``(create_tok, read_tok)`` for the
    last N turns (order irrelevant). Returns:

    - ``None``  — no verdict: an auto-cache provider (write premium = 0 ⇒ can't thrash),
      or fewer than ``_THRASH_MIN_TURNS`` turns of data, or the window never wrote.
    - ``True``  — the window paid write premiums but got few reads back
      (read/(read+create) < 0.5): the cached prefix isn't stable → net-negative caching.
    - ``False`` — caching is paying off (reads dominate writes).

    Only explicit-cache providers can thrash; the single-turn priming write that always
    looks net-negative is deliberately NOT flagged because the verdict needs ≥3 turns.
    """
    caps = capabilities or {}
    if not caps.get("prompt_cache_control"):
        return None  # no write premium ⇒ thrashing is impossible

    turns = [(max(0, int(c or 0)), max(0, int(r or 0))) for c, r in window]
    if len(turns) < _THRASH_MIN_TURNS:
        return None  # not enough history for a stable verdict

    tot_create = sum(c for c, _ in turns)
    tot_read = sum(r for _, r in turns)
    if tot_create == 0:
        return False  # never wrote to cache ⇒ nothing to thrash
    return (tot_read / (tot_create + tot_read)) < _THRASH_HIT_RATIO
