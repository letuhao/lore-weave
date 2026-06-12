"""Chapter single-pass assembly (LOOM chapter-assembly-modes, B2).

The `chapter` mode generates a whole chapter in ONE drafter pass from the A3
decompose plan (the chapter's scene nodes), instead of per-scene + stitch. These
are PURE helpers — build the combined chapter outline + the union cast + a
synthetic in-memory pack node (NEVER persisted) keyed at the chapter's reading
position. The router orchestrates pack → single draft → chapter-level canon
check/reflect around them (mirrors the auto path, at chapter granularity).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.models import OutlineNode

# story_order = chapter.sort_order * STRIDE + scene_idx (chapter-major, scene-minor;
# stable + collision-free for ≤STRIDE scenes/chapter). MUST match plan.py's
# decompose_commit assignment — imported there so the two never drift.
STORY_ORDER_CHAPTER_STRIDE = 1000


def union_cast(scenes: list[OutlineNode]) -> list[UUID]:
    """The chapter's cast = every scene's pov_entity_id + present_entity_ids,
    deduped, first-seen order preserved (deterministic for the canon check + the
    pack `present` lens)."""
    seen: set[UUID] = set()
    out: list[UUID] = []
    for sc in scenes:
        for eid in ([sc.pov_entity_id] if sc.pov_entity_id else []) + list(sc.present_entity_ids):
            if eid not in seen:
                seen.add(eid)
                out.append(eid)
    return out


def build_combined_synopsis(chapter_intent: str, scenes: list[OutlineNode]) -> str:
    """Combine the chapter intent + each scene's beat (title/synopsis/tension) in
    reading order into one outline the drafter writes the whole chapter from.
    Empty parts are skipped so a sparse plan still produces a clean prompt."""
    lines: list[str] = []
    intent = (chapter_intent or "").strip()
    if intent:
        lines.append(intent)
    beats: list[str] = []
    for i, sc in enumerate(scenes, start=1):
        title = (sc.title or "").strip()
        synopsis = (sc.synopsis or "").strip()
        head = f"{i}. {title}".rstrip()
        body = f"{head} — {synopsis}" if synopsis else head
        if sc.tension is not None:
            body = f"{body} (tension {sc.tension})"
        beats.append(body)
    if beats:
        lines.append("Scenes in order:")
        lines.extend(beats)
    return "\n".join(lines)


def build_chapter_pack_node(
    *,
    chapter_id: UUID,
    chapter_sort: int | None,
    chapter_intent: str,
    chapter_title: str,
    scenes: list[OutlineNode],
) -> dict[str, Any]:
    """The synthetic in-memory pack node for chapter mode (MED-1) — NEVER
    persisted. Carries the chapter's reading position (story_order = sort×STRIDE,
    the chapter opening), the union cast, and the combined synopsis so the packer
    grounds at the chapter position with strictly-prior context. `id=None` so any
    log line / lens keyed on node id reads as synthetic."""
    story_order = chapter_sort * STORY_ORDER_CHAPTER_STRIDE if chapter_sort is not None else None
    return {
        "id": None,
        "chapter_id": chapter_id,
        "story_order": story_order,
        "present_entity_ids": union_cast(scenes),
        "pov_entity_id": None,
        "beat_role": None,
        "goal": (chapter_intent or "").strip(),
        "synopsis": build_combined_synopsis(chapter_intent, scenes),
        "title": chapter_title or "",
    }
