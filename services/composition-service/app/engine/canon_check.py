"""A2-S3 — SCORE-style symbolic canon guard (deterministic fast-path).

The cheap, near-free PRIMARY canon gate (spec §5.1 / §9 D2): over the
knowledge `fact-for-check` snapshot (status@P + entities), flag any cast member
that is `gone` at the scene's reading position but **present in the draft text**.

This is a *candidate* contradiction — a gone character named in the prose. The
A2-S3b LLM-judge confirms whether it is an actual contradiction (the entity is
ACTING/present) vs legitimate (flashback, memory, corpse, mourning). Keeping the
symbolic guard over-inclusive is intentional: it is the fast pre-filter, the
judge is the precise (and costly) confirmer.

Pure functions — no LLM, no I/O. The caller (A2-S3b engine wiring) fetches the
snapshot via `knowledge_client.fact_for_check` and feeds it here.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "EVENT_ORDER_CHAPTER_STRIDE",
    "scene_at_order",
    "CanonViolation",
    "gone_cast_in_draft",
]

# Reading-axis stride — the cross-service contract with knowledge-service's
# event_order (= chapter sort_order × stride; CM4). Composition owns this as a
# CONTRACT constant (not an import of a knowledge internal), per the §CM4 note
# "stride = composition cutoff contract".
EVENT_ORDER_CHAPTER_STRIDE = 1_000_000

_SPAN_PAD = 40  # chars of context either side of a match


def scene_at_order(scene_sort_order: int | None) -> int | None:
    """The reading-axis position to check a scene against: the start of its
    chapter on the event_order scale. A death in a STRICTLY-earlier chapter
    (`from_order < sort_order × stride`) makes the entity `gone` for this scene;
    a death within this chapter does not (the character is alive until it
    happens). `None` when the scene's chapter has no resolved sort_order — the
    caller then skips the symbolic guard (advisory only)."""
    if scene_sort_order is None:
        return None
    return scene_sort_order * EVENT_ORDER_CHAPTER_STRIDE


class CanonViolation(BaseModel):
    kind: str = "gone_entity_present"
    source: str = "score_symbolic"   # vs "llm_judge" (A2-S3b)
    entity_id: str
    glossary_entity_id: str | None = None
    name: str | None = None
    status: str = "gone"
    span: str = ""                   # excerpt of the draft around the match
    matched: str = ""                # the name form that matched
    confirmed: bool | None = None    # set by the A2-S3b judge; None = symbolic-only


def _find_span(draft: str, name: str) -> tuple[str, str] | None:
    """Return (matched_name, span_excerpt) if `name` occurs in `draft`. Uses
    word boundaries for ASCII names (avoid 'Al' in 'Always'); plain containment
    for CJK/non-ASCII names (no \\b word boundary in CJK script)."""
    if not name or not name.strip():
        return None
    name = name.strip()
    idx = -1
    if name.isascii():
        m = re.search(r"\b" + re.escape(name) + r"\b", draft, re.IGNORECASE)
        if m:
            idx = m.start()
    else:
        low = draft.lower()
        idx = low.find(name.lower())
    if idx < 0:
        return None
    start = max(0, idx - _SPAN_PAD)
    end = min(len(draft), idx + len(name) + _SPAN_PAD)
    excerpt = ("…" if start > 0 else "") + draft[start:end] + ("…" if end < len(draft) else "")
    return name, excerpt


def gone_cast_in_draft(
    draft: str, snapshot: dict[str, Any] | None,
) -> list[CanonViolation]:
    """Symbolic candidates: every `gone` entity in the snapshot whose name (or
    canonical_name) appears in `draft`. Empty when the snapshot is absent (the
    guard degrades to advisory — a knowledge outage never blocks). De-duped per
    entity (the first matching name form wins)."""
    if not draft or not snapshot:
        return []
    out: list[CanonViolation] = []
    seen: set[str] = set()
    for ent in snapshot.get("entities") or []:
        if not isinstance(ent, dict) or ent.get("status") != "gone":
            continue
        eid = ent.get("entity_id")
        if not eid or eid in seen:
            continue
        for name in (ent.get("name"), ent.get("canonical_name")):
            hit = _find_span(draft, name) if isinstance(name, str) else None
            if hit is None:
                continue
            matched, span = hit
            out.append(CanonViolation(
                entity_id=eid,
                glossary_entity_id=ent.get("glossary_entity_id"),
                name=ent.get("name"),
                status="gone",
                span=span,
                matched=matched,
            ))
            seen.add(eid)
            break
    return out
