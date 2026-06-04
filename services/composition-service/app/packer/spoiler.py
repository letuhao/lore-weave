"""Two-axis spoiler cutoff (§2.2) — the spoiler-safety guarantee.

In-world axis (true cutoff, L1b): keep events whose `chronological_order` is
strictly before the scene's `story_order`. The timeline query already applies
`before_chronological=story_order`; this is a defensive re-filter (fail-closed if
the query was ever issued unscoped).

Reading-order axis (approximation, L4): a retrieved passage only knows its
chapter (`source_id`/`chapter_index`), not in-world time. Keep hits whose chapter
reading position (`sort_order`) is strictly before the scene's chapter position;
drop hits at/after it. A hit with NO resolvable position is **conservative-dropped
and COUNTED** (`l4_dropped_no_position`) so a dead filter is visible, not a silent
no-op (the enrichment no-silent-caps lesson). Both axes FAIL CLOSED when the
scene's own position is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


def filter_inworld_events(
    events: list[dict[str, Any]], story_order: int | None,
) -> tuple[list[dict[str, Any]], int]:
    """L1b: keep events with `chronological_order < story_order`. Returns
    (kept, dropped). `story_order=None` → no safe cutoff → drop all (fail
    closed; the lens shouldn't even query timeline in that case)."""
    if story_order is None:
        return [], len(events)
    kept = [
        e for e in events
        if isinstance(e.get("chronological_order"), int)
        and e["chronological_order"] < story_order
    ]
    return kept, len(events) - len(kept)


@dataclass
class L4FilterResult:
    kept: list[dict[str, Any]]
    dropped_no_position: int   # → logged as l4_dropped_no_position
    dropped_future: int        # at/after the scene's reading position


def filter_reading_order(
    hits: list[dict[str, Any]],
    scene_sort_order: int | None,
    position_for: Callable[[dict[str, Any]], int | None],
) -> L4FilterResult:
    """L4: keep hits whose chapter position is strictly before the scene's.
    `position_for(hit)` returns the hit's reading position (chapter_index, or a
    resolved sort_order) or None. A None position → conservative-drop + count.
    `scene_sort_order=None` (scene's chapter unplaceable) → drop all hits as
    no-position (fail closed)."""
    if scene_sort_order is None:
        return L4FilterResult([], len(hits), 0)
    kept: list[dict[str, Any]] = []
    no_pos = 0
    future = 0
    for h in hits:
        pos = position_for(h)
        if pos is None:
            no_pos += 1
            continue
        if pos >= scene_sort_order:
            future += 1
            continue
        kept.append(h)
    return L4FilterResult(kept, no_pos, future)
