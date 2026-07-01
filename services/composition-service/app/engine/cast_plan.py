"""Planning pipeline · Stage 0 — `propose_cast` (the cast-design step).

The one-shot `decompose` never *proposes* a cast: it only resolves names that already
exist in the glossary, so on a fresh book the roster is empty and every scene's present
cast is blank (the planning-review hole). This step fills it: from the PREMISE the LLM

  1. EXTRACTS every named character (role, relationships) — the premise already names them; and
  2. PROPOSES the supporting cast the arc will need (antagonists, allies, mentors, rivals)
     that isn't named yet — inventing genre-appropriate names.

The result is seeded into the glossary BEFORE planning, so `_cast_roster` is non-empty
and the scene-decompose can populate `present_entity_ids` + plan new-character
introductions. Degrade-safe: any LLM/parse failure returns [] (the caller keeps today's
empty-roster behavior — never blocks).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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
class ProposedChar:
    name: str
    role: str = ""               # protagonist / antagonist / mentor / rival / ally / ...
    archetype: str = ""
    traits: list[str] = field(default_factory=list)
    relationships: str = ""      # free-text ties to other cast ("huynh trưởng of Lâm Uyển")
    summary: str = ""
    is_new: bool = False         # True = invented here (not named in the premise) → a planned introduction


def build_propose_cast_messages(
    premise: str, source_language: str = "auto", genre_tags: list[str] | None = None,
) -> tuple[str, str]:
    """(system, user). Language-/genre-aware; names + values in the story's language."""
    lang = "" if source_language in ("", "auto") else (
        f" Write all names and values in the language with code '{source_language}'."
    )
    genre = f" Genre: {', '.join(genre_tags)}." if genre_tags else ""
    system = (
        "You are a story-bible architect designing the CAST for a novel from its premise. "
        "Do TWO things: (1) EXTRACT every character NAMED in the premise — with their role "
        "and relationships; (2) PROPOSE the supporting cast the arc will still need "
        "(antagonists, allies, mentors, rivals, foils) that the premise does NOT yet name — "
        "invent a fitting, genre-appropriate name for each." + genre +
        " Respect the premise's naming convention (do not rename existing characters). "
        "For EACH character return a JSON object: "
        '"name", "role" (protagonist/antagonist/mentor/rival/ally/foil/...), "archetype", '
        '"traits" (a short list), "relationships" (ties to other cast), "summary" (one line), '
        'and "is_new" (true ONLY if you invented them — i.e. not named in the premise). '
        'Return ONLY a JSON array [{"name":...,"role":...,"archetype":...,"traits":[...],'
        '"relationships":...,"summary":...,"is_new":bool}]. No prose around it.' + lang
    )
    return system, "PREMISE:\n\n" + premise


def parse_cast(content: str) -> list[ProposedChar]:
    """Tolerant parse of the cast JSON array. Drops a row with no usable name; dedups by
    folded name (first wins). Never raises."""
    if not content:
        return []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    arr: list = []
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list):
                arr = parsed
        except (json.JSONDecodeError, ValueError):
            arr = []
    if not arr:
        # salvage a TRUNCATED array (token cap cut the closing ]) — parse each complete
        # top-level {...} object individually so a verbose cast never silently yields [].
        for obj in re.findall(r"\{[^{}]*\}", content, re.DOTALL):
            try:
                row = json.loads(obj)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(row, dict):
                arr.append(row)
    if not arr:
        return []
    def _as_bool(v: Any) -> bool:
        # JSON true/false → bool; but a model sometimes emits the STRING "false"/"no",
        # and bool("false") is True — coerce those textual negatives to False.
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() not in ("", "false", "no", "0", "none", "null")
        return bool(v)

    out: list[ProposedChar] = []
    seen: set[str] = set()
    for row in arr if isinstance(arr, list) else []:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        key = name.strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        traits = row.get("traits")
        traits = [t.strip() for t in traits if isinstance(t, str) and t.strip()] \
            if isinstance(traits, list) else []
        out.append(ProposedChar(
            name=name.strip(),
            role=str(row.get("role", "")).strip(),
            archetype=str(row.get("archetype", "")).strip(),
            traits=traits,
            relationships=str(row.get("relationships", "")).strip(),
            summary=str(row.get("summary", "")).strip(),
            is_new=_as_bool(row.get("is_new", False)),
        ))
    return out


def cast_attributes(c: ProposedChar) -> dict[str, str]:
    """Map a proposed character's designed fields onto the glossary CHARACTER kind's
    attribute codes (`role`, `personality`, `relationships`, `description`) so the cast's
    DEPTH — not just its name — is persisted + reaches drafting grounding (D-PLAN-CAST-ATTRS).
    Only non-empty fields are emitted; an unknown kind's attrs are dropped by the glossary."""
    attrs: dict[str, str] = {}
    if c.role:
        attrs["role"] = c.role
    if c.relationships:
        attrs["relationships"] = c.relationships
    personality = list(c.traits)
    if c.archetype:
        personality.append(c.archetype)
    if personality:
        attrs["personality"] = "; ".join(personality)
    if c.summary:
        attrs["description"] = c.summary
    return attrs


async def propose_cast(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    premise: str, source_language: str = "auto", genre_tags: list[str] | None = None,
    max_tokens: int = 4000, trace_id: str | None = None,  # a full cast JSON is verbose — undersizing truncates the array → parse fails
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[ProposedChar]:
    """Propose the cast (named + invented-supporting) from the premise. Returns [] on any
    LLM/parse failure (degrade-safe — the caller keeps the empty-roster path)."""
    system, user = build_propose_cast_messages(premise, source_language, genre_tags)
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.4,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"usage_purpose": "prose_plan", "extractor": "propose_cast"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("propose_cast LLM error: %s", exc)
        return []
    if job.status != "completed":
        logger.info("propose_cast status=%s → degraded", job.status)
        return []
    content = extract_judge_content(job.result)
    return parse_cast(content)
