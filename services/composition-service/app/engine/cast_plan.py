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

from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.llm_budget import unusable, max_tokens_for

logger = logging.getLogger(__name__)


@dataclass
class ProposedChar:
    name: str
    role: str = ""               # protagonist / antagonist / mentor / rival / ally / ...
    archetype: str = ""
    traits: list[str] = field(default_factory=list)
    relationships: str = ""      # free-text ties to other cast ("huynh trưởng of Lâm Uyển")
    summary: str = ""
    is_new: bool = False         # True = invented here (not named in the premise) → a planned introduction


#: A long-running book's roster can be large; the principals are what stop re-invention.
_MAX_KNOWN_CAST = 40

#: How many characters the model is expected to INVENT on top of the roster it was given —
#: the budget signal's second term. Not a guess: the system prompt above enumerates the
#: supporting roles it asks for ("antagonists, allies, mentors, rivals, foils"), so the count
#: is read off the instruction the model actually receives. It is a SIZING input only; nothing
#: enforces it, and the parser accepts whatever comes back.
_INVENTED_CAST_ALLOWANCE = 5


def build_propose_cast_messages(
    premise: str, source_language: str = "auto", genre_tags: list[str] | None = None,
    known_cast: list[str] | None = None, canon: str = "",
) -> tuple[str, str]:
    """(system, user). Language-/genre-aware; names + values in the story's language.

    E6 — `known_cast` and `canon` are what this pass was missing, and their absence was not a
    quality nit but a correctness one:

    · KNOWN_CAST. `is_new` used to mean "not named in the PREMISE". The premise is one arc's
      summary, so for a book with an established cast every character it does not happen to
      mention read as new — the planner proposed INTRODUCING people who have been on the page for
      thirty chapters, and invented fresh names for them. Anchored to the book's actual roster
      instead, `is_new` means what it says.
    · CANON. `package["canon"]` (the charter's consistency anchors) was compiled on every run and
      read by nobody — the one block the author wrote to say "these things are fixed" went nowhere
      near the prompt.

    Both are OPTIONAL: a brand-new book has no roster and may have no anchors, and that case must
    stay exactly as it was rather than gain an empty section that reads as "there is no cast".
    """
    lang = "" if source_language in ("", "auto") else (
        f" Write all names and values in the language with code '{source_language}'."
    )
    genre = f" Genre: {', '.join(genre_tags)}." if genre_tags else ""
    # `is_new` is defined against whatever roster the model was actually GIVEN. With a known cast
    # it means "not in the book"; without one there is nothing to compare to but the premise, and
    # claiming otherwise would ask for a judgement the prompt does not support.
    is_new_rule = (
        'and "is_new" (true ONLY if you invented them — i.e. they are named neither in the '
        'premise nor in the EXISTING CAST below). '
        if known_cast else
        'and "is_new" (true ONLY if you invented them — i.e. not named in the premise). '
    )
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
        + is_new_rule +
        'Return ONLY a JSON array [{"name":...,"role":...,"archetype":...,"traits":[...],'
        '"relationships":...,"summary":...,"is_new":bool}]. No prose around it.' + lang
    )
    # The roster goes in the USER message beside the premise, not the system prompt: it is data
    # about THIS book, not a rule about how to behave. Capped — a long-running book's cast can be
    # large, and the point is to stop re-invention, which the principals already achieve.
    parts = ["PREMISE:\n\n" + premise]
    if known_cast:
        parts.append(
            "EXISTING CAST — these characters ALREADY EXIST in this book. Use their names exactly "
            "as written, do NOT rename or re-invent them, and mark them is_new=false:\n"
            + "\n".join(f"- {n}" for n in known_cast[:_MAX_KNOWN_CAST])
        )
    if canon.strip():
        parts.append(
            "CANON — established facts this arc must not contradict:\n" + canon.strip()[:1500]
        )
    return system, "\n\n".join(parts)


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
    known_cast: list[str] | None = None, canon: str = "",
    max_tokens: int | None = None, trace_id: str | None = None,  # a full cast JSON is verbose — undersizing truncates the array → parse fails
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[ProposedChar]:
    """Propose the cast (named + invented-supporting) from the premise. Returns [] on any
    LLM/parse failure (degrade-safe — the caller keeps the empty-roster path)."""
    # The row this call site truncated on. The prompt asks the model to return EVERY existing
    # cast member (marked is_new=false) plus the supporting cast it invents, so the roster
    # actually sent — capped at `_MAX_KNOWN_CAST`, which is the number that reaches the model
    # — is a real lower bound on the array's length, and `_INVENTED_CAST_ALLOWANCE` covers the
    # five archetypes the system prompt names. Derived from the prompt rather than picked: an
    # established book sends 40 names and used to get the same budget as a blank one.
    # No `language`: STRUCTURED sizes on item count and never reads it (registry test pins it).
    #
    # `context_length` is threaded because the target above can get LARGE — an established
    # book resolves to ~24k output tokens against the old flat 4096 — and a cap the model's
    # window cannot honour is a worse failure than the under-budgeting this fixes. The window
    # clamp (`_MAX_WINDOW_SHARE`) is the mechanism for that and it is unreachable unless the
    # window is passed. Best-effort by design: `resolve_context_length` returns None rather
    # than fabricating, and None simply means no clamp — the pre-existing behaviour.
    max_tokens = max_tokens or max_tokens_for(
        "propose_cast",
        target=len((known_cast or [])[:_MAX_KNOWN_CAST]) + _INVENTED_CAST_ALLOWANCE,
        context_length=await llm.resolve_context_length(model_source, model_ref))
    system, user = build_propose_cast_messages(
        premise, source_language, genre_tags, known_cast=known_cast, canon=canon)
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.4,
                "max_tokens": max_tokens, **no_thinking_fields(),
            },
            job_meta={"usage_purpose": "prose_plan", "extractor": "propose_cast"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("propose_cast LLM error: %s", exc)
        return []
    if (why := unusable(job, "propose_cast")):
        logger.info("propose_cast status=%s → degraded", job.status)
        return []
    content = extract_judge_content(job.result)
    return parse_cast(content)
