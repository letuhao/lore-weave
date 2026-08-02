"""27 V2-C3 · Pass 3 — `propose_world` (the WORLD-design step).

The compiler analogue is the rest of the symbol table. Pass 2 (`cast_plan`) declares WHO; this
declares WHERE and WHAT: the locations, factions, and concepts a scene can refer to. Without it,
pass 6 writes scenes that mention places and orders which exist nowhere in the glossary — the same
"use of an undeclared identifier" failure that anonymous characters were before pass 2 existed
(PF-1).

Deliberately a MIRROR of `cast_plan.py` — same three moves (build messages → tolerant parse →
degrade-safe empty), same thinking suppression, same `LLMError`/non-completed handling. It is a
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

from loreweave_extraction.name_normalize import normalize_entity_name
from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.llm_budget import unusable, max_tokens_for

logger = logging.getLogger(__name__)

#: The glossary kinds pass 3 may propose (PF-7 names exactly these three). A CLOSED SET: a kind
#: outside it would be seeded into the quarantine and then rejected by glossary as unknown — a
#: silent no-op at the far end of a long chain. Filter here, where it is cheap and visible.
WorldKind = Literal["location", "faction", "concept"]
WORLD_KINDS: tuple[str, ...] = ("location", "faction", "concept")

#: The proposal shape, with `kind` closed over WORLD_KINDS. Loose on the descriptive fields — the
#: point is to close the ENUM the parser already filters on, not to dictate the prose beside it.
_WORLD_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": list(WORLD_KINDS)},
                },
                "required": ["name", "kind"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["items"],
}

#: A long-running book's world can be large; the principals are what stop re-invention. Capped
#: PER KIND, not overall: a book with ninety locations and three factions must still show both.
_MAX_KNOWN_WORLD = 40

#: Entities the model is expected to INVENT per kind, on top of whatever roster it was given.
#: Read off the system prompt, which asks it to propose the places, factions and concepts
#: "the story will need but has not named yet" for each of the three `WORLD_KINDS`. A sizing
#: input only — the decoder's schema, not this number, is what bounds the response.
_INVENTED_WORLD_PER_KIND = 3

#: Rendering order for the existing-world roster. Fixed rather than dict order so the same book
#: produces the same prompt on every run.
_WORLD_KIND_LABELS: tuple[tuple[str, str], ...] = (
    ("location", "PLACES"),
    ("faction", "FACTIONS / ORGANISATIONS"),
    ("concept", "CONCEPTS"),
)


@dataclass
class ProposedWorldEntity:
    name: str
    kind: str = "location"       # one of WORLD_KINDS
    summary: str = ""
    #: Free-text ties — "the seat of the Iron Court", "outlawed after the Third Rising".
    relationships: str = ""
    traits: list[str] = field(default_factory=list)
    #: True = invented here. Judged against whatever roster the prompt was GIVEN: the book's
    #: existing world when one is supplied, and only the premise when it is not (E6b).
    is_new: bool = False


def build_propose_world_messages(
    premise: str,
    source_language: str = "auto",
    genre_tags: list[str] | None = None,
    cast_names: list[str] | None = None,
    known_world: dict[str, list[str]] | None = None,
    canon: str = "",
) -> tuple[str, str]:
    """(system, user). Language-/genre-aware; names + values in the story's language.

    The CAST is supplied as context (pass 3 depends on pass 2 — PF-1): a world proposed blind to
    its characters invents a faction for nobody and a home for no one. Naming them is what makes
    "the seat of the Iron Court" resolvable.

    E6b — `known_world` and `canon` are the world-side of the same correctness bug E6 fixed for the
    cast, and this pass had it worse:

    · KNOWN_WORLD. `is_new` meant "not named in the PREMISE", and the premise is ONE arc's summary.
      So on a book forty chapters deep, the capital the story has been set in since chapter three
      came back marked `is_new` — a planned INTRODUCTION of a place the reader already knows, often
      renamed on the way. Anchored to the book's actual world instead, `is_new` means what it says.
    · CANON. Consistency anchors bite harder here than on the cast: "the empire fell in year 300",
      "magic costs blood" are constraints on invented factions and concepts, and pass 3 is the pass
      that invents them.

    The roster is passed BY KIND rather than as one flat list. The cast is flat because they are
    all people; a world is not. Telling the model "Hoa Sơn already exists" without saying it is a
    *location* is how a mountain becomes a character.

    Both are OPTIONAL, and a book with neither must build exactly the prompt it built before —
    an empty "EXISTING WORLD" heading reads as "this book has no world", which is a lie.
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
    # Only the three kinds this pass may propose, in a fixed order, empty buckets dropped. A kind
    # outside WORLD_KINDS would be listed as something the model is then forbidden to return.
    roster: list[tuple[str, list[str]]] = []
    for kind, label in _WORLD_KIND_LABELS:
        names = [str(n).strip() for n in ((known_world or {}).get(kind) or []) if str(n).strip()]
        if names:
            roster.append((label, names[:_MAX_KNOWN_WORLD]))
    # `is_new` is defined against whatever roster the model was actually GIVEN — with none, the
    # premise is the only thing to compare to, and claiming otherwise asks for a judgement the
    # prompt does not support.
    is_new_rule = (
        "`is_new` is true ONLY for entries you invented — i.e. named neither in the premise nor "
        "in the EXISTING WORLD listed below. "
        if roster else
        "`is_new` is true ONLY for entries you invented (not named in the premise). "
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
        + is_new_rule +
        "No prose, no markdown fences, no commentary."
    )
    # The roster and the anchors go in the USER message beside the premise: they are data about
    # THIS book, not rules about how to behave (the `cast_plan` E6 shape).
    parts = [f"PREMISE:\n{premise.strip()}"]
    if roster:
        block = [
            "EXISTING WORLD — these ALREADY EXIST in this book. Use their names exactly as "
            "written, do NOT rename or re-invent them, keep each one under the KIND it is listed "
            "here, and mark them is_new=false:"
        ]
        block += [f"{label}: " + ", ".join(names) for label, names in roster]
        parts.append("\n".join(block))
    if canon.strip():
        parts.append(
            "CANON — established facts this world must not contradict:\n" + canon.strip()[:1500]
        )
    return system, "\n\n".join(parts)


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

    # The SCHEMA-shaped answer: `{"items": [...]}`. `_WORLD_SCHEMA` declares exactly that
    # wrapper — it was introduced to enforce WORLD_KINDS at the decoder — and this parser was
    # left reading a bare array, which is what the PROMPT asks for. So on every provider that
    # honours the grammar, `json.loads` returned a dict, `isinstance(arr, list)` was False,
    # and the whole pass degraded to `[]` through its own tolerant path.
    #
    # MEASURED LIVE 2026-08-02 on gemma-4-26b: `finish_reason=stop`, 2864 characters of
    # perfectly well-formed JSON, zero entities parsed — in BOTH budget arms, so it is not a
    # truncation. Pass 3 is advisory and returns `[]` on any failure, which is exactly why
    # nothing ever reported it: a dead pass and a book with no world to propose look identical
    # from the outside.
    if isinstance(arr, dict):
        inner = arr.get("items")
        if not isinstance(inner, list):
            # Tolerant, in the spirit of the rest of this function: accept a differently-named
            # single list rather than fail on a wrapper key we did not predict. Ambiguous
            # payloads (two lists) are NOT guessed at.
            lists = [v for v in arr.values() if isinstance(v, list)]
            inner = lists[0] if len(lists) == 1 else None
        arr = inner

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
        key = (normalize_entity_name(name), kind)
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
    known_world: dict[str, list[str]] | None = None,
    canon: str = "",
    max_tokens: int | None = None,   # a full world JSON is verbose — undersizing truncates the array → parse fails
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[ProposedWorldEntity]:
    """Propose the world (named + invented) from the premise, given the cast.

    Returns `[]` on ANY LLM/parse failure. Pass 3 is advisory: an empty world plan means grounding
    stays as thin as it was before this pass existed — it must never block the compiler.
    """
    # Counted the way the PROMPT counts: only the three `WORLD_KINDS` buckets are listed, each
    # capped at `_MAX_KNOWN_WORLD`, so the roster that reaches the model — not the dict the
    # caller happens to hold — is the lower bound on the array coming back. A kind outside
    # WORLD_KINDS is dropped from the prompt, so counting it here would budget for entries the
    # model was never asked for. No `language`: STRUCTURED never reads it.
    _known = sum(
        len([n for n in ((known_world or {}).get(kind) or []) if str(n).strip()][:_MAX_KNOWN_WORLD])
        for kind in WORLD_KINDS
    )
    # `context_length` for the same reason as `propose_cast`: this is the largest target in
    # the registry — a book with a full roster in all three kinds reaches the SDK's 32768
    # runaway ceiling — and an output cap the model's window cannot honour trades an
    # under-budget bug for a request that fails outright. None ⇒ no clamp, as before.
    max_tokens = max_tokens or max_tokens_for(
        "propose_world", target=_known + _INVENTED_WORLD_PER_KIND * len(WORLD_KINDS),
        context_length=await llm.resolve_context_length(model_source, model_ref))
    system, user = build_propose_world_messages(
        premise, source_language, genre_tags, cast_names,
        known_world=known_world, canon=canon,
    )
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # WORLD_KINDS enforced at the DECODER. The parser already drops an out-of-set
                # kind; a grammar makes it unemittable, so a dropped entry stops being invisible.
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "world_plan", "schema": _WORLD_SCHEMA},
                },
                "temperature": 0.4,
                "max_tokens": max_tokens,
                **no_thinking_fields(),
            },
            job_meta={"usage_purpose": "prose_plan", "extractor": "propose_world"},
            trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("propose_world LLM error: %s", exc)
        return []
    if (why := unusable(job, "propose_world")):
        logger.info("propose_world status=%s → degraded", job.status)
        return []
    return parse_world(extract_judge_content(job.result))
