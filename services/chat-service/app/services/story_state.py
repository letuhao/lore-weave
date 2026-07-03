"""T4 (Context Budget Law) — story_state Core Memory Block: distill, cadence, render.

Pure logic (no I/O) so it is trivially testable. The `story_state` block is a
cached, bounded projection of the message-INDEPENDENT grounding gist (the L0 +
project summary/instructions "story bible" prefix that knowledge build_context
returns as `stable_context`). It exists so a turn whose expensive per-turn
grounding was gated (T5) still carries the load-bearing lore as a SAFETY NET
(sealed #1/#3, D4) — the follow-up "make it darker" never loses the entities the
rewrite needs.

sealed #3: `story_state` only, auto-projected, NO LLM and NO agent-write tool
(so distillation here is deterministic truncation, not summarization).
"""

from __future__ import annotations

import hashlib

from app.services.token_budget import estimate_tokens

STORY_STATE_LABEL = "story_state"

# Bound the block cost (T4 GATE: "block token cost ≤ ceiling"). ~1.2K tokens is a
# generous story-bible gist while staying a small fraction of any window.
STORY_STATE_TOKEN_CAP = 1200

# sealed #5 — refresh cadence in turns when nothing else triggers a refresh.
DEFAULT_CADENCE_TURNS = 5


def source_hash(stable_context: str) -> str:
    """Short stable hash of the grounding source — lets a refresh no-op when the
    story-bible prefix is byte-identical (skip a pointless write + version bump)."""
    return hashlib.sha256((stable_context or "").encode("utf-8")).hexdigest()[:16]


def distill_story_state(
    stable_context: str, *, token_cap: int = STORY_STATE_TOKEN_CAP
) -> tuple[str, int]:
    """Distill the message-independent grounding into the bounded block body.

    Deterministic (no LLM): take `stable_context` and, if it exceeds `token_cap`,
    truncate on a line boundary (keeping whole lines — the story-bible is
    line-structured: entities, facts, instructions). Returns (value, token_estimate).
    """
    text = (stable_context or "").strip()
    if not text:
        return "", 0
    est = estimate_tokens(text)
    if est <= token_cap:
        return text, est
    # Truncate line-wise until under the cap (keep the head — L0/summary leads).
    kept: list[str] = []
    running = 0
    for line in text.splitlines():
        line_tok = estimate_tokens(line) + 1
        if running + line_tok > token_cap:
            break
        kept.append(line)
        running += line_tok
    value = "\n".join(kept).strip()
    if not value:  # a single over-cap line → hard char-truncate as a last resort
        value = text[: token_cap * 4].strip()
    return value, estimate_tokens(value)


def should_refresh(
    *,
    cached_turn: int | None,
    current_turn: int,
    cached_hash: str | None,
    new_hash: str,
    lore_gate: bool = False,
    scene_change: bool = False,
    cadence: int = DEFAULT_CADENCE_TURNS,
) -> bool:
    """sealed #5 — refresh the cache when ANY of: no cache yet · the source content
    changed (hash differs) · an explicit lore-needed gate this turn · a scene/chapter
    change · `cadence` turns elapsed since the last refresh. Else project from cache."""
    if cached_turn is None or cached_hash is None:
        return True                      # nothing cached yet
    if new_hash != cached_hash:
        return True                      # the grounding source changed
    if lore_gate or scene_change:
        return True                      # an explicit trigger
    return (current_turn - cached_turn) >= cadence


def render_story_state_block(value: str) -> str:
    """The projected block text — wrapped so the model reads it as persistent
    session state. Empty string when there is nothing to project (no injection)."""
    v = (value or "").strip()
    return f"<story_state>\n{v}\n</story_state>" if v else ""
