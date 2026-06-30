"""Planning pipeline · Stage 3 — `plan_character_arcs` (arcs + introduction schedule).

Two holes the one-shot decompose left (planning review): (1) no per-character
trajectory across the arc, and (2) NEW characters appeared anonymously mid-story
("a group", "someone") with no plan for WHERE they enter. This step, given the cast
(Stage 0, each flagged `is_new`) + the ordered beats (Stage 2), produces for each
character an ARC (how they change across the story) and, for a NEW character, the
chapter where it should be INTRODUCED — so Stage 4's decompose can stage the
introduction at a fitting beat instead of inventing an anonymous figure.

Degrade-safe: any LLM/parse failure returns [] (the caller proceeds without arcs).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient

logger = logging.getLogger(__name__)

_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}


@dataclass
class CharacterArc:
    name: str
    role: str = ""
    arc: str = ""                              # the character's trajectory across the story
    introduce_at_chapter: int | None = None    # 1-based chapter to introduce a NEW character;
    #                                            None = present from the start (named in premise)


def build_character_arc_messages(
    premise: str, cast: list[dict[str, Any]], beat_roles: list[str | None],
    source_language: str = "auto",
) -> tuple[str, str]:
    """(system, user). `cast` = [{name, role, is_new}]; `beat_roles` is the ordered
    per-chapter beat sequence (chapter i+1 → beat_roles[i])."""
    lang = "" if source_language in ("", "auto") else (
        f" Write 'arc' in the language with code '{source_language}'."
    )
    n = len(beat_roles)
    system = (
        "You are a story architect planning CHARACTER ARCS for one story. For EACH cast "
        "member return their `arc` — how they change across the story (1-2 sentences) — and "
        "`introduce_at_chapter`: for a NEW character (is_new=true) the 1-based chapter where "
        "they should first ENTER, chosen to fit the beat at that point (allies/rivals during "
        "rising conflict, a final foil near the climax, etc.); for a character already present "
        "in the premise (is_new=false) set it to 1. Use ONLY the given names (do not invent "
        f"characters). The story has {n} chapters. Return ONLY a JSON array "
        '[{"name":...,"arc":...,"introduce_at_chapter":int}]. No prose around it.' + lang
    )
    roster = "\n".join(
        f"- {c['name']} (role: {c.get('role', '?')}, "
        f"{'NEW' if c.get('is_new') else 'in-premise'})" for c in cast if c.get("name")
    )
    beat_line = ", ".join(f"ch{i + 1}:{r or '-'}" for i, r in enumerate(beat_roles))
    user = f"PREMISE:\n{premise}\n\nCAST:\n{roster}\n\nBEAT SEQUENCE:\n{beat_line}"
    return system, user


def parse_character_arcs(
    content: str, valid_names: set[str], n_chapters: int,
) -> list[CharacterArc]:
    """Map the model's arcs back onto the cast by name (drop an unknown/invented name,
    dedup), clamp `introduce_at_chapter` to [1, n_chapters]. Never raises."""
    if not content:
        return []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    folded = {v.casefold(): v for v in valid_names}
    out: list[CharacterArc] = []
    seen: set[str] = set()
    for row in arr if isinstance(arr, list) else []:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str):
            continue
        canon = folded.get(name.strip().casefold())
        if canon is None or canon in seen:
            continue  # unknown/invented/duplicate name → drop (never invent a character)
        seen.add(canon)
        intro = row.get("introduce_at_chapter")
        if isinstance(intro, bool) or not isinstance(intro, int):
            intro_clamped: int | None = None
        else:
            intro_clamped = max(1, min(n_chapters, intro))
        out.append(CharacterArc(
            name=canon,
            arc=str(row.get("arc", "")).strip(),
            introduce_at_chapter=intro_clamped,
        ))
    return out


async def plan_character_arcs(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    premise: str, cast: list[dict[str, Any]], beat_roles: list[str | None],
    source_language: str = "auto", max_tokens: int = 2000,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[CharacterArc]:
    """Per-character arcs + introduction schedule. Returns [] on empty cast or any
    LLM/parse failure (degrade-safe). Carries each cast member's `role` through from
    the input (the LLM only adds arc + introduction)."""
    valid = {c["name"] for c in cast if c.get("name")}
    if not valid:
        return []
    role_by_name = {c["name"]: c.get("role", "") for c in cast if c.get("name")}
    system, user = build_character_arc_messages(premise, cast, beat_roles, source_language)
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.4,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"usage_purpose": "prose_plan", "extractor": "character_arcs"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("plan_character_arcs LLM error: %s", exc)
        return []
    if job.status != "completed":
        logger.info("plan_character_arcs status=%s → degraded", job.status)
        return []
    arcs = parse_character_arcs(extract_judge_content(job.result), valid, len(beat_roles))
    for a in arcs:
        a.role = role_by_name.get(a.name, "")
    return arcs
