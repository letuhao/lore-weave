"""Planning pipeline · Stage 4 — `grounded_decompose` (the integration).

Stages 0-3 produced the planning inputs (cast, selected motifs + arc roles, the
deliberate tension curve, character arcs + an introduction schedule) — but the one-shot
decompose ignored them. This orchestrator feeds them ALL into the L2 scene decomposition
so the scenes come out grounded:

  - cast roster + scheduled NEW-character introductions (each new figure enters at its
    planned chapter, named — not anonymous);
  - the selected motifs (emphasised per chapter by their arc role) woven into intents;
  - the chapter's tension TARGET band (so scenes aim for it instead of free-running to 100);
  - cross-chapter threading (the typed exit-state, reused from the threaded decompose).

It reuses the engine's L1 map + L2 prompt (now grounding-aware) + the tension curve, and
runs the L2 SEQUENTIALLY so each chapter threads on the prior chapters' exit-state. Pure
orchestration over those pieces — no new LLM-call mechanics.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from app.clients.llm_client import LLMClient
from app.engine.arc_plan import ChapterTension, shape_tension_curve
from app.engine.plan import (
    ChapterPlan, ChapterScenes, DecomposeResult, _llm_json,
    build_chapter_map_messages, build_scene_decompose_messages,
    parse_chapter_exit, parse_chapter_map, parse_scenes, render_story_so_far,
)

logger = logging.getLogger(__name__)


async def map_beats_and_shape(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    premise: str, beats: list[dict[str, Any]], chapters: list[ChapterPlan],
    source_language: str = "auto", l1_max_tokens: int = 2048,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[list[ChapterPlan], list[str], list[ChapterTension]]:
    """27 V2-C4 — PASS 4 (`beats`) as a DISCRETE step: the L1 beat map + the tension curve.

    This used to be the opening third of `grounded_decompose`, reachable only by running the whole
    scene decomposition. Hoisting it out is what makes `beats` a pass a human can BLOCK on (it is a
    `blocking` checkpoint: "what shape does the story take?"), review, and edit — before the
    expensive per-chapter L2 decomposition spends tokens against a shape they were going to reject.

    Returns `(mapped_chapters, unmapped_BEAT_KEYS, curve)` — the middle element is the beats the
    model could not place, NOT chapters (every chapter always comes back; an unplaced one just keeps
    `beat_role=None`). Degrade-safe: an L1 failure leaves every chapter's `beat_role` None, and the
    curve then sits at the neutral mid band — a flat plan, not a crash.
    """
    beat_keys = {b.get("key") for b in beats if isinstance(b.get("key"), str)}
    mapped: list[ChapterPlan] = chapters
    unmapped: list[str] = []
    sys1, usr1 = build_chapter_map_messages(premise, beats, chapters, source_language)
    l1 = await _llm_json(
        llm, system=sys1, user=usr1, max_tokens=l1_max_tokens,
        user_id=user_id, model_source=model_source, model_ref=model_ref,
        trace_id=trace_id, cancel_check=cancel_check,
    )
    if l1 is not None:
        mapped, unmapped = parse_chapter_map(l1, chapters, beat_keys)
    else:
        logger.warning("map_beats_and_shape: L1 degraded — chapters keep beat_role=None")
    return mapped, unmapped, shape_tension_curve([ch.beat_role for ch in mapped])

# Which selected motifs to emphasise for a chapter, by the motif's arc role × the beat.
# The spine/recurring motifs are always live; a foil sharpens during conflict; a climax
# payoff lands at the climax/setback. An un-roled motif is always offered.
_CONFLICT_BEATS = {"rising_conflict", "rising_action", "midpoint", "complications", "setback"}
_CLIMAX_BEATS = {"climax", "crisis", "setback"}


def motifs_for_beat(
    motifs: list[dict[str, str]], beat_role: str | None,
) -> list[dict[str, str]]:
    """Filter the selected arc motifs down to the ones that fit THIS chapter's beat. A
    role-SPECIFIC motif (foil / climax-payoff) is gated to its phase; everything else —
    spine/recurring/empty AND any UNRECOGNISED role — is always offered, so a selected
    motif is never silently dropped from the whole plan by an off-vocabulary role string."""
    role = (beat_role or "").strip().lower()
    out: list[dict[str, str]] = []
    for m in motifs:
        ar = (m.get("arc_role") or "").strip().lower()
        is_foil = "foil" in ar
        is_climax = "climax" in ar or "payoff" in ar
        if is_foil:
            if role in _CONFLICT_BEATS:
                out.append(m)
        elif is_climax:
            if role in _CLIMAX_BEATS:
                out.append(m)
        else:
            out.append(m)  # spine / recurring / empty / UNRECOGNISED → always offered
    return out


def intros_by_chapter(
    char_arcs: list[dict[str, Any]], n_chapters: int,
) -> dict[int, list[str]]:
    """Map each scheduled NEW-character introduction to its chapter (1-based). A character
    with `introduce_at_chapter` in [2, n] is staged there; intro at 1 / None = present from
    the start (not a staged introduction)."""
    out: dict[int, list[str]] = {}
    for c in char_arcs:
        ch = c.get("introduce_at_chapter")
        name = c.get("name")
        if isinstance(ch, int) and 2 <= ch <= n_chapters and isinstance(name, str) and name.strip():
            out.setdefault(ch, []).append(name.strip())
    return out


async def grounded_decompose(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    premise: str, arc_title: str,
    beats: list[dict[str, Any]], chapters: list[ChapterPlan],
    cast: list[dict[str, Any]],
    motifs: list[dict[str, str]], char_arcs: list[dict[str, Any]],
    k_ceiling: int, high_threshold: int, min_scenes: int, max_scenes: int,
    source_language: str = "auto", trace_id: str | None = None,
    l1_max_tokens: int = 2048, l2_max_tokens: int = 2560, skip_l1: bool = False,
    tension_curve: list[ChapterTension] | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> DecomposeResult:
    """L1 map → tension curve → SEQUENTIAL grounded L2 (cast/motifs/tension/intros + the
    cross-chapter threading). Degrades like decompose: an L1 failure leaves beat_role=None;
    an L2 failure for a chapter yields scenes=[] + a warning. Always emits the chapter-exit
    delta (threading on)."""
    beat_purpose = {b.get("key"): b.get("purpose", "") for b in beats if isinstance(b.get("key"), str)}
    beat_keys = {b.get("key") for b in beats if isinstance(b.get("key"), str)}
    cast_index = {
        e["name"].strip().casefold(): str(e["entity_id"])
        for e in cast if e.get("name") and e.get("entity_id")
    }
    cast_names = [e["name"] for e in cast if e.get("name")]

    _llm_kw = dict(user_id=user_id, model_source=model_source, model_ref=model_ref,
                   trace_id=trace_id, cancel_check=cancel_check)

    # L1 — beat map. SKIP it when chapters arrive PRE-MAPPED (any beat_role set) OR when the
    # caller asserts `skip_l1` — in the full pipeline L1 runs ONCE (its result also feeds
    # Stage 3's char arcs), so the orchestrator passes skip_l1=True to keep that invariant
    # even when its L1 DEGRADED to all-None (re-running here would drift the beats out of
    # sync with the intro schedule char arcs were planned against).
    mapped, unmapped = chapters, []
    if skip_l1 or any(ch.beat_role for ch in chapters):
        logger.info("grounded_decompose: chapters pre-mapped / skip_l1 — reusing beat roles (no L1)")
    else:
        sys1, usr1 = build_chapter_map_messages(premise, beats, chapters, source_language)
        l1 = await _llm_json(llm, system=sys1, user=usr1, max_tokens=l1_max_tokens, **_llm_kw)
        if l1 is not None:
            mapped, unmapped = parse_chapter_map(l1, chapters, beat_keys)
        else:
            logger.warning("grounded_decompose L1 degraded — chapters keep beat_role=None")

    # Stage-2 tension curve + Stage-3 introduction schedule, indexed by 1-based chapter.
    #
    # 27 V2-C4 — HONOUR A SUPPLIED CURVE. `beats` (pass 4) is a BLOCKING checkpoint: the human
    # reviews the beat plan and may EDIT the tension curve there. If we recomputed it from the beat
    # roles we would silently discard that edit — the same "a re-run reclaims the author's edit" bug
    # class PF-11 exists to stop, one layer down. So when pass 4 hands us its curve, we use it.
    #
    # `shape_tension_curve` is pure and deterministic, so an UNEDITED curve recomputes identically;
    # the difference is only ever visible when a human has changed something, which is exactly when
    # it must be.
    curve = tension_curve if tension_curve else shape_tension_curve(
        [ch.beat_role for ch in mapped],
    )
    tension_by_idx = {c.chapter_index: c.tension_target for c in curve}
    intro_by_idx = intros_by_chapter(char_arcs, len(mapped))

    # L2 — sequential grounded decomposition with cross-chapter threading.
    results: list[ChapterScenes] = []
    prev_exit = None
    used_advances: list[str] = []
    for i, ch in enumerate(mapped, start=1):
        so_far = render_story_so_far(prev_exit, used_advances)
        sys2, usr2 = build_scene_decompose_messages(
            premise, ch, beat_purpose.get(ch.beat_role, "") if ch.beat_role else "",
            cast_names, min_scenes, max_scenes, source_language, so_far, emit_exit=True,
            tension_target=tension_by_idx.get(i),
            motifs=motifs_for_beat(motifs, ch.beat_role),
            new_intros=intro_by_idx.get(i),
        )
        c = await _llm_json(llm, system=sys2, user=usr2, max_tokens=l2_max_tokens, **_llm_kw)
        if c is None:
            results.append(ChapterScenes(chapter=ch, scenes=[], warning="scene_decompose_degraded"))
            continue
        scenes = parse_scenes(c, cast_index, min_scenes=min_scenes, max_scenes=max_scenes,
                              beat_role=ch.beat_role, k_ceiling=k_ceiling, high_threshold=high_threshold)
        exit_state = parse_chapter_exit(c)
        results.append(ChapterScenes(
            chapter=ch, scenes=scenes,
            warning=None if scenes else "no_scenes_parsed", exit_state=exit_state,
        ))
        if exit_state is not None:
            prev_exit = exit_state
            used_advances.extend(exit_state.advances)

    return DecomposeResult(arc_title=arc_title, chapters=results, unmapped_beats=unmapped)
