"""V3 semantic chunker (M3, G5) — dialogue/scene-aware grouping pre-pass.

``tag_groups(blocks)`` assigns each top-level block a *group id* so the batch
builder can avoid splitting a coherent unit (a dialogue exchange, a paragraph
cluster) across two LLM calls. Deterministic, no model dependency.

Grouping rule (spec §3):
  - a *scene boundary* block (``heading`` / ``horizontalRule``) starts a new
    group;
  - a *dialogue run* — consecutive blocks whose text carries a dialogue marker —
    forms its own group;
  - otherwise consecutive paragraphs cluster together.

A new group id is emitted whenever the block kind is a scene boundary OR differs
from the previous block's kind. The result is fed to
``build_batch_plan(group_ids=...)``; when omitted the batcher keeps
byte-identical V2 behaviour.
"""
from __future__ import annotations

from ..block_classifier import extract_translatable_text

# Scene-boundary block types — each starts a fresh group.
_SCENE_TYPES = frozenset({"heading", "horizontalRule"})

# Characters that mark spoken dialogue (CJK corner brackets, curly + straight
# double quotes). A leading em/en dash also opens a line of speech.
_DIALOGUE_MARKS = ("「", "」", "『", "』", "“", "”", '"')
_DIALOGUE_LEAD = ("—", "–")  # — em dash / – en dash


def _has_dialogue(text: str) -> bool:
    if not text:
        return False
    if any(m in text for m in _DIALOGUE_MARKS):
        return True
    return text.lstrip().startswith(_DIALOGUE_LEAD)


def _kind(block: dict, text: str) -> str:
    if block.get("type", "") in _SCENE_TYPES:
        return "scene"
    if _has_dialogue(text):
        return "dialogue"
    return "para"


def tag_groups(blocks: list[dict]) -> dict[int, int]:
    """Map each block position-index → group id (see module docstring)."""
    groups: dict[int, int] = {}
    gid = -1
    prev_kind: str | None = None
    for i, block in enumerate(blocks):
        kind = _kind(block, extract_translatable_text(block))
        if kind == "scene" or kind != prev_kind:
            gid += 1
        groups[i] = gid
        prev_kind = kind
    return groups
