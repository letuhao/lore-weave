"""V1 Phase A3 — the `decompose` planner (F5/DOC: push complexity upstream).

Two top-down LLM levels over the book's EXISTING chapters (composition-only —
the planner never mints chapters):

  L1  arc→chapter map  : assign each existing chapter exactly one structure
                         `beat_role` + a 1-line `intent`, grounded in the premise
                         + the beat's purpose. Surplus beats (B>C) surface as
                         `unmapped_beats`; more chapters than beats (C>B) is fine —
                         consecutive chapters share a beat_role.
  L2  chapter→scenes   : per chapter, conditioned on its intent + beat purpose +
                         premise + cast roster, emit S scenes with
                         {title, intent, tension(0..100), present_entities}.

The output is a PREVIEW tree (not persisted); the endpoint returns it for the
author to accept/edit, then a separate commit call writes the nodes.

Robustness (LLM-schema-tolerate-filter + gateway-response lessons):
  - chapters are keyed by 1-based INDEX in the prompt (not UUID) so the model
    never has to echo a uuid; we map index→chapter_id ourselves.
  - tolerant parse: a malformed scene is dropped, the chapter keeps its good
    scenes; a chapter the model omits in L1 still appears (beat_role=None).
  - present-entity names are resolved against the glossary cast roster; an
    unmatched name is SURFACED (`present_entity_names_unresolved`), never
    silently dropped, and never invented as an id.
  - prompts are abstract + source-language-aware with NO English-only
    illustrative phrases (the CJK-bias lesson).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.adaptive_k import adaptive_k
from app.engine.critic import parse_critique_json

logger = logging.getLogger(__name__)

# Disable hidden thinking on reasoning-model planners (mirrors select.py).
_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}

_L2_CONCURRENCY = 4  # bounded chapter fan-out (don't open C calls at once)


@dataclass
class ChapterPlan:
    chapter_id: str
    title: str
    sort_order: int
    beat_role: str | None
    intent: str


@dataclass
class ScenePlan:
    title: str
    synopsis: str
    tension: int
    present_entity_ids: list[str]
    present_entity_names_unresolved: list[str]
    suggested_k: int


@dataclass
class ChapterScenes:
    chapter: ChapterPlan
    scenes: list[ScenePlan]
    warning: str | None = None


@dataclass
class DecomposeResult:
    arc_title: str
    chapters: list[ChapterScenes] = field(default_factory=list)
    unmapped_beats: list[str] = field(default_factory=list)


def _lang_clause(source_language: str) -> str:
    return "" if source_language in ("", "auto") else (
        f" Write all string values in the language with code '{source_language}'."
    )


# ── L1 — arc→chapter map ───────────────────────────────────────────────

def build_chapter_map_messages(
    premise: str, beats: list[dict[str, Any]], chapters: list[ChapterPlan],
    source_language: str,
) -> tuple[str, str]:
    """(system, user) for the chapter-map call. Chapters listed by 1-based index;
    the model assigns each a beat key + a 1-line intent."""
    system = (
        "You are a story architect. You are given a premise, a story-structure as "
        "an ordered list of beats (each a key and its purpose), and an ordered list "
        "of the book's existing chapters. Assign EVERY chapter exactly one beat key "
        "(the closest structural fit by position and purpose; consecutive chapters "
        "may share a beat when there are more chapters than beats) and write a "
        "one-sentence intent for that chapter grounded in the premise. Return ONLY "
        'a JSON object {"chapters":[{"index":int,"beat":str,"intent":str}],'
        '"unmapped_beats":[str]} where index is the chapter\'s 1-based number and '
        "unmapped_beats lists beat keys that no chapter received." + _lang_clause(source_language)
    )
    beat_lines = "\n".join(f"- {b.get('key')}: {b.get('purpose', '')}" for b in beats)
    chap_lines = "\n".join(
        f"{i}. {c.title or '(untitled)'}" for i, c in enumerate(chapters, start=1)
    )
    user = (
        f"PREMISE:\n{premise}\n\nSTRUCTURE BEATS (in order):\n{beat_lines}\n\n"
        f"CHAPTERS (in order):\n{chap_lines}"
    )
    return system, user


def parse_chapter_map(
    content: str, chapters: list[ChapterPlan], beat_keys: set[str],
) -> tuple[list[ChapterPlan], list[str]]:
    """Apply the model's beat/intent assignments onto the existing chapters by
    index. Every chapter is returned (no drop — an omitted/invalid row keeps
    beat_role=None, intent=''). Only valid beat keys are accepted."""
    obj = parse_critique_json(content) or {}
    by_index: dict[int, dict[str, Any]] = {}
    for row in obj.get("chapters") or []:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if isinstance(idx, bool) or not isinstance(idx, int):
            continue
        by_index[idx] = row
    out: list[ChapterPlan] = []
    for i, c in enumerate(chapters, start=1):
        row = by_index.get(i) or {}
        beat = row.get("beat")
        beat_role = beat if isinstance(beat, str) and beat in beat_keys else None
        intent = row.get("intent")
        out.append(ChapterPlan(
            chapter_id=c.chapter_id, title=c.title, sort_order=c.sort_order,
            beat_role=beat_role,
            intent=intent.strip() if isinstance(intent, str) else "",
        ))
    raw_unmapped = obj.get("unmapped_beats")
    unmapped = [b for b in raw_unmapped if isinstance(b, str) and b in beat_keys] \
        if isinstance(raw_unmapped, list) else []
    return out, unmapped


# ── L2 — chapter→scenes ────────────────────────────────────────────────

def build_scene_decompose_messages(
    premise: str, chapter: ChapterPlan, beat_purpose: str, cast_names: list[str],
    min_scenes: int, max_scenes: int, source_language: str,
) -> tuple[str, str]:
    """(system, user) for one chapter's scene decomposition."""
    system = (
        "You are a story architect breaking ONE chapter into scenes. For each scene "
        "give a short title, a one-to-two sentence intent, a tension level from 0 "
        "(calm/connective) to 100 (climactic/crisis), and which of the listed cast "
        "members are actively present. Use ONLY cast names from the provided roster; "
        "omit a scene's cast entry if none apply. Produce between "
        f"{min_scenes} and {max_scenes} scenes that together fulfil the chapter "
        'intent. Return ONLY a JSON object {"scenes":[{"title":str,"intent":str,'
        '"tension":int,"present":[str]}]}.' + _lang_clause(source_language)
    )
    roster = ", ".join(cast_names) if cast_names else "(none provided)"
    user = (
        f"PREMISE:\n{premise}\n\nCHAPTER INTENT:\n{chapter.intent or chapter.title}\n\n"
        f"STRUCTURAL PURPOSE OF THIS CHAPTER:\n{beat_purpose}\n\nCAST ROSTER:\n{roster}"
    )
    return system, user


def _resolve_cast(
    names: list[Any], cast_index: dict[str, str],
) -> tuple[list[str], list[str]]:
    """(resolved glossary ids, unresolved names). Match by folded name; dedupe ids
    preserving order; unmatched names surfaced, never invented."""
    ids: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for n in names:
        if not isinstance(n, str) or not n.strip():
            continue
        eid = cast_index.get(n.strip().casefold())
        if eid is None:
            unresolved.append(n.strip())
        elif eid not in seen:
            seen.add(eid)
            ids.append(eid)
    return ids, unresolved


def parse_scenes(
    content: str, cast_index: dict[str, str], *,
    min_scenes: int, max_scenes: int, beat_role: str | None,
    k_ceiling: int, high_threshold: int,
) -> list[ScenePlan]:
    """Tolerant scene parse: drop malformed scenes, clamp to max_scenes, resolve
    cast, compute suggested_k via adaptive_k. May return fewer than min_scenes if
    the model under-produced (the caller flags an empty chapter)."""
    obj = parse_critique_json(content) or {}
    out: list[ScenePlan] = []
    for row in obj.get("scenes") or []:
        if not isinstance(row, dict):
            continue
        title = row.get("title")
        intent = row.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            continue  # a scene with no intent is unusable — drop it
        t = row.get("tension")
        if isinstance(t, bool) or not isinstance(t, int):
            tension = 50  # neutral default (0..100) when the model omits/garbles it
        else:
            tension = max(0, min(100, t))  # 0..100 scale (outline_node.tension)
        present = row.get("present")
        ids, unresolved = _resolve_cast(present if isinstance(present, list) else [], cast_index)
        out.append(ScenePlan(
            title=title.strip() if isinstance(title, str) and title.strip() else intent.strip()[:60],
            synopsis=intent.strip(),
            tension=tension,
            present_entity_ids=ids,
            present_entity_names_unresolved=unresolved,
            suggested_k=adaptive_k(beat_role, tension, k_ceiling=k_ceiling,
                                   high_threshold=high_threshold),
        ))
        if len(out) >= max_scenes:
            break
    return out


# ── orchestration ──────────────────────────────────────────────────────

async def _llm_json(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    system: str, user: str, max_tokens: int, trace_id: str | None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> str | None:
    """One blocking chat completion returning the raw content, or None on
    error / non-completion / empty (the caller degrades)."""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.4,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"usage_purpose": "prose_plan", "extractor": "decompose"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("decompose LLM error: %s", exc)
        return None
    if job.status != "completed":
        logger.info("decompose status=%s → degraded", job.status)
        return None
    content = extract_judge_content(job.result)
    return content if content.strip() else None


async def decompose(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    premise: str, arc_title: str,
    beats: list[dict[str, Any]], chapters: list[ChapterPlan],
    cast: list[dict[str, Any]],
    k_ceiling: int, high_threshold: int, min_scenes: int, max_scenes: int,
    source_language: str = "auto", trace_id: str | None = None,
    l1_max_tokens: int = 2048, l2_max_tokens: int = 1536,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> DecomposeResult:
    """L1 chapter-map (1 call) → L2 scenes (per chapter, bounded concurrency).
    Degrades per-level: an L1 failure leaves every chapter beat_role=None (scenes
    still attempt); an L2 failure for a chapter yields scenes=[] + a warning."""
    beat_keys = {b.get("key") for b in beats if isinstance(b.get("key"), str)}
    beat_purpose = {b.get("key"): b.get("purpose", "") for b in beats if isinstance(b.get("key"), str)}
    cast_index = {
        e["name"].strip().casefold(): str(e["entity_id"])
        for e in cast if e.get("name") and e.get("entity_id")
    }
    cast_names = [e["name"] for e in cast if e.get("name")]

    # L1 — map beats onto existing chapters.
    mapped, unmapped = chapters, []
    sys1, usr1 = build_chapter_map_messages(premise, beats, chapters, source_language)
    l1 = await _llm_json(llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
                         system=sys1, user=usr1, max_tokens=l1_max_tokens, trace_id=trace_id,
                         cancel_check=cancel_check)
    if l1 is not None:
        mapped, unmapped = parse_chapter_map(l1, chapters, beat_keys)
    else:
        logger.warning("decompose L1 degraded — chapters keep beat_role=None")

    # L2 — decompose each chapter into scenes (bounded fan-out).
    sem = asyncio.Semaphore(_L2_CONCURRENCY)

    async def one_chapter(ch: ChapterPlan) -> ChapterScenes:
        async with sem:
            sys2, usr2 = build_scene_decompose_messages(
                premise, ch, beat_purpose.get(ch.beat_role, "") if ch.beat_role else "",
                cast_names, min_scenes, max_scenes, source_language,
            )
            c = await _llm_json(llm, user_id=user_id, model_source=model_source,
                                model_ref=model_ref, system=sys2, user=usr2,
                                max_tokens=l2_max_tokens, trace_id=trace_id,
                                cancel_check=cancel_check)
        if c is None:
            return ChapterScenes(chapter=ch, scenes=[], warning="scene_decompose_degraded")
        scenes = parse_scenes(c, cast_index, min_scenes=min_scenes, max_scenes=max_scenes,
                              beat_role=ch.beat_role, k_ceiling=k_ceiling,
                              high_threshold=high_threshold)
        warning = None if scenes else "no_scenes_parsed"
        return ChapterScenes(chapter=ch, scenes=scenes, warning=warning)

    results = await asyncio.gather(*(one_chapter(ch) for ch in mapped))
    return DecomposeResult(arc_title=arc_title, chapters=list(results), unmapped_beats=unmapped)
