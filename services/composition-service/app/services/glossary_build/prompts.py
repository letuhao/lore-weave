"""Prompts for the glossary-build planner/executor — promoted from the POC
(eval/glossary_build_poc.py, results in the spec). All output contracts are JSON;
language adapts to the book's source language via ``lang`` (the POC ran 'vi').

POC-locked rules baked in:
- The planner ENUMERATES ONLY (E3: enumerate-only found 13 entities where the
  detail-everything call found 9 and collapsed to 1-2 attrs/entity).
- The executor builds ONE item per call (depth held at the E1 baseline).
- The deep loop (E4, 10x depth) outlines sections first, then steers ONE section
  per call with a VARIED craft instruction (the fixed instruction produced a
  formulaic "Mâu thuẫn nội tâm..." scaffold in every section — spec weakness #1).
"""
from __future__ import annotations

# Closed sets — Frontend-Tool-Contract discipline applies wherever these cross a
# schema boundary later (M2 exposes them as enums).
RELATION_TYPES = [
    # character ↔ character
    "ally_of", "enemy_of", "member_of", "betrothed_to", "loves",
    "killed", "spared", "betrayed", "parent_of", "sibling_of", "mentor_of",
    # concept ↔ concept / concept ↔ character. Added after the live wizard run
    # (2026-07-27): with only the character verbs available, the model was FORCED
    # into false edges for lore terms — "Chân Linh mentor_of Lâm Uyên" (it is his
    # soul layer, not a mentor) and "Chữ ký tần số enemy_of Lâm Uyên". A closed set
    # with no fitting member does not produce silence; it produces a wrong answer.
    "part_of", "property_of", "created_by", "related_to",
]
DEPTHS = ["standard", "deep"]

_LANG_LINE = {
    "vi": "Viết toàn bộ nội dung bằng tiếng Việt.",
    "en": "Write all content in English.",
}


def _lang_line(lang: str) -> str:
    return _LANG_LINE.get(lang, f"Write all content in the language with code '{lang}'.")


def planner_messages(source_text: str, kinds: list[str], existing_names: list[str],
                     lang: str = "vi", max_items: int = 30) -> list[dict]:
    """BREADTH ONLY — enumerate what to build; forbid detail (the E2/E3 lesson)."""
    existing = ", ".join(existing_names) if existing_names else "(none)"
    system = (
        "You are the build planner for a fiction glossary. Return ONLY a JSON array "
        '(no markdown): [{"name":"...","kind":"<one of: ' + "|".join(kinds) + '>",'
        '"depth":"<standard|deep>","why":"one short sentence"}]. '
        "deep = a major entity deserving a full profile (protagonists, central factions, "
        "the power system); standard = everything else. Do NOT write detailed attributes "
        f"— enumerate only. At most {max_items} items. " + _lang_line(lang)
    )
    user = (
        f"STORY CONTEXT:\n{source_text}\n\n"
        "List EVERY entity worth a glossary entry that this text establishes "
        "(characters, factions/organizations, events, terminology, power systems, "
        f"relationships, locations, items). Already in the glossary — skip these: {existing}."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ── field selection (measured, eval/schema_recall_poc.py) ────────────────────
#
# NARROW_THRESHOLD: a schema with at most this many fields is already focused —
# cutting it gains NOTHING (terminology 4→2 measured identical, 123 ch/field
# both ways). Wider than this and narrowing pays: power_system 7→3 gained +66%
# depth (88 → 146 ch/field). So slice by threshold, never mechanically.
NARROW_THRESHOLD = 4
# How many fields a WIDE schema is cut down to for a standard build. A `deep`
# build always gets the full schema — its steered sections have room for breadth.
WIDE_CORE_FIELDS = 4
# Kinds this narrow can be built several-at-a-time in ONE call (one schema, no
# context-switching): measured 3x cheaper with only mild decay across positions
# (98/89/87 ch/field) — nothing like the 7→1 collapse of mixed-kind batching.
BATCH_MAX = 3


# Information density by field type. `sort_order` is a FORM-LAYOUT signal (short
# scalars first, prose last, because that is how a form should READ) — using it to
# decide what MATTERS inverts the priority: measured live, slicing `item` by
# sort_order kept name/aliases/type/owner and dropped BOTH `description` and
# `symbolic_meaning`, i.e. every field that carries actual meaning. Prose first.
_TYPE_RANK = {"textarea": 0, "text": 1, "richtext": 0, "tags": 2, "number": 2}


def _rank(d: dict) -> tuple:
    return (not d.get("is_required"),                       # required always first
            _TYPE_RANK.get(str(d.get("field_type") or "text"), 1),
            d.get("sort_order") or 0)


def select_fields(defs: list[dict], *, deep: bool) -> list[str]:
    """The attribute codes to ask for. A deep build takes everything; a standard
    build narrows a WIDE schema, keeping required + the most INFORMATION-DENSE
    fields (prose before scalars before tag lists) rather than form order."""
    codes = [str(d.get("code")) for d in defs if d.get("code")]
    if deep or len(codes) <= NARROW_THRESHOLD:
        return codes
    ranked = sorted((d for d in defs if d.get("code")), key=_rank)
    required = [str(d["code"]) for d in ranked if d.get("is_required")]
    return [str(d["code"]) for d in ranked][:max(WIDE_CORE_FIELDS, len(required))]


def _field_spec(fields: list[str], types: dict[str, str] | None = None) -> str:
    """Render the JSON skeleton, carrying each field's SHAPE.

    Distinct from the `auto_fill_prompt` the POC rejected: that was human PROSE
    guidance (it diluted attention, 123 → 96 chars/field). This is a structural
    marker — a `tags` field must come back as a JSON array, a `textarea` as a
    paragraph. Live-caught: with no shape marker the model returned a list for
    `aliases` and the postprocess stringified it into "['a', 'b']"."""
    types = types or {}
    out = []
    for c in fields:
        t = types.get(c, "text")
        if t == "tags":
            out.append(f'"{c}": ["...", "..."]')
        elif t in ("textarea", "richtext"):
            out.append(f'"{c}": "... (2-4 câu)"')
        else:
            out.append(f'"{c}": "..."')
    return ", ".join(out)


# Declared absence. Fiction is not a form to be filled: a kind can define an
# attribute the story has simply not established yet, and FORCING a value there is
# strictly worse than leaving it empty — the glossary is the SSOT, so an invented
# `owner` becomes canon and propagates to KG → plan → draft. So the model is given
# an explicit way to say "nothing here", which lets the platform tell a real
# authoring gap (declared) apart from an attention drop (silently missing). Worded
# with a HIGH bar on purpose: an escape hatch that is too easy becomes laziness.
_ABSENT_RULE = (
    "If the story establishes NOTHING for a field, return null for that field — "
    "never invent one. null is ONLY for a field with no basis in the text at all; "
    "it is not a way to avoid work. "
)


def _entity_schema_hint(fields: list[str], lang: str,
                        types: dict[str, str] | None = None) -> str:
    """The output contract for ONE entity.

    POC finding (2026-07-27): injecting each field's authored `auto_fill_prompt`
    made quality WORSE (123 → 96 chars/field) and cost 20% more tokens — the hints
    are written for humans and dilute attention. So: field codes + SHAPE only.
    """
    spec = _field_spec(fields, types)
    return (
        "Return ONLY one JSON object (no markdown): "
        '{"attributes":{ ' + spec + ' },'
        '"relations":[{"target_name":"...","type":"<' + "|".join(RELATION_TYPES) + '>",'
        '"note":"..."}]} '
        "Use EXACTLY those attribute keys — no others, and keep each value in the "
        "shape shown (an array stays an array). Values are SPECIFIC, with concrete "
        "detail. " + _ABSENT_RULE +
        "relations.target_name is the OTHER entity's NAME (never an id). "
        + _lang_line(lang)
    )


def executor_messages(source_text: str, item_name: str, item_kind: str,
                      fields: list[str], lang: str = "vi",
                      types: dict[str, str] | None = None) -> list[dict]:
    """DEPTH, one item — the E1/E3 focused single-shot shape, over the kind's REAL fields."""
    system = ("You are a profile editor for a fiction glossary. "
              + _entity_schema_hint(fields, lang, types))
    user = (
        f"STORY CONTEXT:\n{source_text}\n\n"
        f"Build a DETAILED profile for exactly ONE entity: {item_name} (kind: {item_kind})."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ── deep loop (E4) ──────────────────────────────────────────────────────────────

def deep_outline_messages(source_text: str, item_name: str, item_kind: str,
                          lang: str = "vi") -> list[dict]:
    system = (
        "You are a profile editor for a fiction glossary. Follow exactly the step you "
        "are asked for — no skipping ahead, no repeating content. " + _lang_line(lang)
    )
    user = (
        f"STORY CONTEXT:\n{source_text}\n\n"
        f"We will build a DEEP profile for {item_name} (kind: {item_kind}), step by step.\n"
        "STEP 1 — OUTLINE: return ONLY a JSON array of 5-7 items "
        '[{"section":"short section label","focus":"the core question this section must answer"}]. '
        "Do NOT write the detailed content in this step."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# Varied craft instructions (spec weakness #1: a FIXED instruction produced the
# same closing scaffold in every section). Rotated by section index.
_CRAFT = [
    "Ground it in concrete sensory/physical detail (names, numbers, habits, objects).",
    "Show it through behavior and choices, not adjectives — what they DO under pressure.",
    "Anchor it in the story's established canon and never contradict prior sections.",
    "Include one specific inner contradiction or cost — but vary HOW you reveal it.",
    "Tie it to at least one OTHER named entity of the story and what changed between them.",
]


def deep_section_messages(section: str, focus: str, index: int) -> dict:
    """The next steering turn (appended to the running conversation)."""
    craft = _CRAFT[index % len(_CRAFT)]
    return {"role": "user", "content": (
        f'NEXT STEP — write the DETAIL for section "{section}" (focus: {focus}).\n'
        f"Write 4-7 SPECIFIC sentences. {craft} "
        "Stay consistent with the sections already written. Write ONLY this section."
    )}


def distill_messages(item_name: str, item_kind: str, profile_text: str,
                     fields: list[str], lang: str = "vi",
                     types: dict[str, str] | None = None) -> list[dict]:
    """Deep profile → the short attribute set (one cheap call; spec weakness #3)."""
    system = ("You distill a long profile into glossary attributes. "
              + _entity_schema_hint(fields, lang, types))
    user = (
        f"LONG PROFILE of {item_name} (kind: {item_kind}):\n{profile_text}\n\n"
        "Distill it into the JSON attribute object. Keep every value faithful to the "
        "profile — no new inventions in this step."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def batch_messages(source_text: str, names: list[str], item_kind: str,
                   fields: list[str], lang: str = "vi",
                   types: dict[str, str] | None = None) -> list[dict]:
    """Several entities of the SAME kind in ONE call, sharing ONE schema.

    Measured 3x cheaper than per-item with only mild positional decay, BECAUSE the
    schema never changes mid-call. NEVER mix kinds here: the E2 collapse (7 attrs on
    the first entity, 1 on the last) came from making the model context-switch."""
    spec = _field_spec(fields, types)
    system = (
        "You are a profile editor for a fiction glossary. Return ONLY a JSON ARRAY, "
        'one element per entity: {"name":"...","attributes":{ ' + spec + ' },'
        '"relations":[{"target_name":"...","type":"<' + "|".join(RELATION_TYPES) + '>",'
        '"note":"..."}]} '
        "Use EXACTLY those attribute keys, keeping each value in the shape shown. "
        "Values are SPECIFIC, with concrete detail. " + _ABSENT_RULE +
        "relations.target_name is the OTHER entity's NAME (never an id). " + _lang_line(lang)
    )
    user = (f"STORY CONTEXT:\n{source_text}\n\n"
            f"Build a profile for EACH of these {len(names)} entities (all of kind "
            f"{item_kind}): " + ", ".join(names) + ".")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
