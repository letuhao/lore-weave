"""Rule-based "when to think" scorer (§Architecture.2).

For `effort`-controlled reasoning models, decides reasoning_effort from signals
the packer ALREADY computes — no extra LLM call, sub-millisecond, deterministic
(mirrors vLLM "When to Reason" / the GPT-5 router idea, but rule-based). The
creative-writing ↔ coding analogy: continue-a-line is boilerplate (low/none),
planning a beat or weaving heavy canon is architecture (high).

The `llm_judge` engine (a small pre-call rating difficulty, Better-Qwen3 style)
is intentionally NOT implemented here in V0 — `resolve` exposes the seam; it lands
in V1 if the rule-based scorer underperforms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from loreweave_llm import ReasoningEffort, bucket_effort

Effort = ReasoningEffort

# Operations that are inherently structural/architectural (think) vs mechanical.
_HEAVY_OPS = {"plan_beat", "weave_canon", "draft_scene", "outline_scene"}
_LIGHT_OPS = {"continue", "rewrite_line", "expand_inline", "describe"}

# Author guidance that signals they want deliberate reasoning.
_REASONING_MARKERS = re.compile(
    r"\b(think|carefully|complex|reconcile|foreshadow|consistent|plan|because|"
    r"why|implication|subtext|twist|reveal|callback|setup|payoff)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReasoningSignals:
    """Cheap signals lifted from the pack result + the request."""
    operation: str = "draft_scene"
    n_canon_rules: int = 0
    n_present_entities: int = 0
    has_reveal_gate: bool = False
    tension: int | None = None  # 0..100
    guide: str = ""


def score_effort(signals: ReasoningSignals) -> Effort:
    """Weighted score → bucketed effort. Tunable; weights chosen so a plain
    continue scores low and a canon-heavy / reveal-gated / high-tension scene
    scores high."""
    s = signals
    score = 0

    op = (s.operation or "").lower()
    if op in _HEAVY_OPS:
        score += 2
    elif op in _LIGHT_OPS:
        score -= 1

    # Canon load — the more rules the model must respect without contradiction,
    # the more reasoning pays off.
    if s.n_canon_rules >= 5:
        score += 2
    elif s.n_canon_rules >= 1:
        score += 1

    # A reveal_gate scene is a spoiler/consistency minefield → reason.
    if s.has_reveal_gate:
        score += 2

    # Many present entities = more relationships to keep straight.
    if s.n_present_entities >= 4:
        score += 1

    # High dramatic tension → the turn matters; deliberate.
    if s.tension is not None and s.tension >= 70:
        score += 1

    # Author explicitly asked for deliberate reasoning — a strong signal that
    # should lift even an otherwise-light operation to at least `low`.
    if s.guide and _REASONING_MARKERS.search(s.guide):
        score += 2

    # Generic monotone bucketer lives in the SDK (reusable by other services).
    return bucket_effort(score)
