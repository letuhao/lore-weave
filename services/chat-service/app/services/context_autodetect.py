"""Long-work context auto-detect (D-LONG-WORK-CONTEXT-MODE).

`context.mode = "auto"` should ENABLE the expensive Context-Budget tiers (T5
intent-gate + T4 story-state) exactly when the context is actually large —
otherwise "auto" is a silent no-op (it was, before this). This is the
Planner-owned adaptive decision the spec intended (D8).

Pure + biased-to-include (mirrors the T5 gate): enable on ANY strong signal so
a false-negative never strips management from a genuinely large turn. Two
signals, either trips:
  - history pressure — a long conversation already fills the window;
  - glossary size — a large, richly-extracted book (the short-conversation-
    but-huge-book case: a 4000-chapter book has a big lore vocabulary on turn 1).

The result is ANDed with the deploy ceiling (env kill-switch) at the call site,
per the Settings & Configuration Boundary: env = ceiling, this = the enablement.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AutoDetectResult",
    "resolve_context_pressure",
    "HISTORY_FRACTION",
    "GLOSSARY_LARGE",
]

# Enable tiers when the conversation history alone is >= this fraction of the
# model window (the "expected_history" half of the original 0.6×window proposal).
HISTORY_FRACTION = 0.6
# ...or when the book's known-entity (glossary) vocabulary is at least this big
# — a cheap, already-cached proxy for "big-lore book" that trips even on turn 1
# of a fresh chat about a huge book (the case history-pressure alone misses).
GLOSSARY_LARGE = 300


@dataclass(frozen=True)
class AutoDetectResult:
    """The per-turn auto-detect decision. `pressure` is the history fraction
    (for telemetry); `reason` names the tripping signal so the Inspector can
    show WHY tiers were on/off (no silent hidden default)."""

    tiers_allowed: bool
    pressure: float
    reason: str
    source: str  # "user" (on/off) | "auto"


def resolve_context_pressure(
    mode: str,
    *,
    window: int | None,
    history_tokens: int,
    glossary_size: int,
    history_fraction: float = HISTORY_FRACTION,
    glossary_large: int = GLOSSARY_LARGE,
) -> AutoDetectResult:
    """Decide whether the Context-Budget tiers should be ALLOWED this turn.

    `mode`: the resolved per-session context mode ("off" | "auto" | "on").
    `window`: the model's context length (None/0 ⇒ unknown ⇒ history signal
      can't be computed; fall back to the glossary signal only).
    `history_tokens`: estimated tokens of the conversation history so far.
    `glossary_size`: count of known-entity tokens for the book (0 if no book /
      unresolved).

    Returns the decision + the signals behind it. The caller ANDs
    `tiers_allowed` with the deploy env ceiling.
    """
    if mode == "off":
        return AutoDetectResult(False, 0.0, "user_off", "user")
    if mode == "on":
        return AutoDetectResult(True, 0.0, "user_on", "user")

    # mode == "auto" (or any unrecognized value → treat as auto, biased-to-include).
    history_pressure = (
        history_tokens / window if window and window > 0 else 0.0
    )
    history_trips = history_pressure >= history_fraction
    glossary_trips = glossary_size >= glossary_large

    if history_trips and glossary_trips:
        reason = "auto_history+glossary"
    elif history_trips:
        reason = "auto_history"
    elif glossary_trips:
        reason = "auto_glossary"
    else:
        reason = "auto_below_threshold"

    return AutoDetectResult(
        tiers_allowed=history_trips or glossary_trips,
        pressure=round(history_pressure, 4),
        reason=reason,
        source="auto",
    )
