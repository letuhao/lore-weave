"""27 V2-C3 · Pass 3 — `propose_world` (the WORLD-design step).

The compiler analogue is the rest of the symbol table. Pass 2 (`cast_plan`) declares WHO; this
declares WHERE and WHAT: the locations, factions, and concepts a scene can refer to. Without it,
pass 6 writes scenes that mention places and orders which exist nowhere in the glossary — the same
"use of an undeclared identifier" failure that anonymous characters were before pass 2 existed
(PF-1).

Deliberately a MIRROR of `cast_plan.py` — same three moves (build messages → tolerant parse →
degrade-safe empty), same `_NO_THINK` suppression, same `LLMError`/non-completed handling. It is a
sibling, not a fork: if the two ever need to diverge, that is a decision to make explicitly, not a
drift to discover.

Degrade-safe by construction: ANY LLM or parse failure returns `[]`. Pass 3 is ADVISORY (PF-6), and
its glossary seeding may lag (PF-7), so an empty world plan must never block the compiler — it just
means grounding stays thinner, which is exactly the behaviour that existed before this pass.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient

logger = logging.getLogger(__name__)

_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}

#: The glossary kinds pass 3 may propose (PF-7 names exactly these three). A CLOSED SET: a kind
#: outside it would be seeded into the quarantine and then rejected by glossary as unknown — a
#: silent no-op at the far end of a long chain. Filter here, where it is cheap and visible.
WorldKind = Literal["location", "faction", "concept"]
WORLD_KINDS: tuple[str, ...] = ("location", "faction", "concept")


@dataclass
class ProposedWorldEntity:
    name: str
    kind: str = "location"       # one of WORLD_KINDS
    summary: str = ""
    #: Free-text ties — "the seat of the Iron Court", "outlawed after the Third Rising".
    relationships: str = ""
    traits: list[str] = field(default_factory=list)
    is_new: bool = False         # True = invented here (not named in the premise)


def build_propose_world_messages(
    premise: str,
    source_language: str = "auto",
    genre_tags: list[str] | None = None,
    cast_names: list[str] | None = None,
) -> tuple[str, str]:
    """(system, user). Language-/genre-aware; names + values in the story's language.

    The CAST is supplied as context (pass 3 depends on pass 2 — PF-1): a world proposed blind to
    its characters invents a faction for nobody and a home for no one. Naming them is what makes
    "the seat of the Iron Court" resolvable.
    """
    lang = "" if source_language in ("", "auto") else (
        f" Write all names and values in the language with code '{source_language}'."
    )
    genre = f" Genre: {', '.join(genre_tags)}." if genre_tags else ""
    cast = ""
    if cast_names:
        cast = (
            " The cast of this story is: " + ", ".join(cast_names[:40])
            + ". Tie the world to THEM — where they are from, what they belong to, what they want."
        )
    system = (
        "You are a story-bible architect designing the WORLD of a novel from its premise. "
        "Do TWO things: (1) EXTRACT every place, faction/organisation, and named concept "
        "(a magic system, an order, a law, a technology) that the premise NAMES; and "
        "(2) PROPOSE the ones the story will need but has not named yet — inventing "
        "genre-appropriate names."
        + genre + cast + lang +
        " Return ONLY a JSON array. Each item: "
        '{"name": str, "kind": "location"|"faction"|"concept", "summary": str, '
        '"relationships": str, "traits": [str], "is_new": bool}. '
        "`is_new` is true ONLY for entries you invented (not named in the premise). "
        "No prose, no markdown fences, no commentary."
    )
    user = f"PREMISE:\n{premise.strip()}"
    return system, user


def parse_world(content: str) -> list[ProposedWorldEntity]:
    """Tolerant parse — mirrors `parse_cast`.

    A model that was asked for bare JSON will still sometimes wrap it in a fence, prepend a
    sentence, or emit one object per line. Every one of those is a well-formed answer badly
    packaged, and throwing it away would degrade the pass for a formatting quibble. Anything we
    genuinely cannot read yields `[]`, which is the degrade-safe path.
    """
    if not content or not content.strip():
        return []
    text = content.strip()
    # Strip a ```json fence if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()

    arr: Any = None
    try:
        arr = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Fall back to the first bracketed array in the blob…
        m = re.search(r"\[.*\]", text, re.S)
        if m:
            try:
                arr = json.loads(m.group(0))
            except (json.JSONDecodeError, ValueError):
                arr = None
    if arr is None:
        # …else JSONL: one object per line.
        rows: list[dict] = []
        for line in text.splitlines():
            line = line.strip().rstrip(",")
            if not line.startswith("{"):
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(row, dict):
                rows.append(row)
        arr = rows

    if not isinstance(arr, list) or not arr:
        return []

    def _as_bool(v: Any) -> bool:
        # A model sometimes emits the STRING "false", and bool("false") is True. Coerce textual
        # negatives, or every proposed entity is marked as newly invented.
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() not in ("", "false", "no", "0", "none", "null")
        return bool(v)

    out: list[ProposedWorldEntity] = []
    seen: set[tuple[str, str]] = set()
    for row in arr:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        kind = str(row.get("kind", "location")).strip().lower()
        if kind not in WORLD_KINDS:
            # An unknown kind is not a reason to drop a real entity — the model named something
            # real and mislabelled it. Default to `concept`, the widest of the three, rather than
            # discarding it or seeding a kind glossary will silently reject.
            kind = "concept"
        # Dedupe on (name, kind): the same word can legitimately be a place AND a faction
        # ("Ironhold" the fortress, "Ironhold" the house). Deduping on name alone would lose one.
        key = (name.strip().casefold(), kind)
        if key in seen:
            continue
        seen.add(key)
        traits = row.get("traits")
        traits = (
            [t.strip() for t in traits if isinstance(t, str) and t.strip()]
            if isinstance(traits, list) else []
        )
        out.append(ProposedWorldEntity(
            name=name.strip(),
            kind=kind,
            summary=str(row.get("summary", "")).strip(),
            relationships=str(row.get("relationships", "")).strip(),
            traits=traits,
            is_new=_as_bool(row.get("is_new", False)),
        ))
    return out


def world_attributes(e: ProposedWorldEntity) -> dict[str, str]:
    """Map a proposed world entity onto the glossary attribute codes, so the DEPTH — not just the
    name — is persisted and reaches drafting grounding (the `cast_attributes` precedent).

    Only non-empty fields are emitted; an attribute the target kind does not define is dropped by
    glossary, so this stays additive.
    """
    attrs: dict[str, str] = {}
    if e.summary:
        attrs["description"] = e.summary
    if e.relationships:
        attrs["relationships"] = e.relationships
    if e.traits:
        attrs["properties"] = "; ".join(e.traits)
    return attrs


async def propose_world(
    llm: LLMClient,
    *,
    user_id: str,
    model_source: str,
    model_ref: str,
    premise: str,
    source_language: str = "auto",
    genre_tags: list[str] | None = None,
    cast_names: list[str] | None = None,
    max_tokens: int = 4000,   # a full world JSON is verbose — undersizing truncates the array → parse fails
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[ProposedWorldEntity]:
    """Propose the world (named + invented) from the premise, given the cast.

    Returns `[]` on ANY LLM/parse failure. Pass 3 is advisory: an empty world plan means grounding
    stays as thin as it was before this pass existed — it must never block the compiler.
    """
    system, user = build_propose_world_messages(
        premise, source_language, genre_tags, cast_names,
    )
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "text"},
                "temperature": 0.4,
                "max_tokens": max_tokens,
                **_NO_THINK,
            },
            job_meta={"usage_purpose": "prose_plan", "extractor": "propose_world"},
            trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("propose_world LLM error: %s", exc)
        return []
    if job.status != "completed":
        logger.info("propose_world status=%s → degraded", job.status)
        return []
    return parse_world(extract_judge_content(job.result))
