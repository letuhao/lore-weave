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
    "ally_of", "enemy_of", "member_of", "betrothed_to", "loves",
    "killed", "spared", "betrayed", "parent_of", "sibling_of", "mentor_of",
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


def _entity_schema_hint(kinds: list[str], lang: str) -> str:
    return (
        "Return ONLY one JSON object (no markdown): "
        '{"name":"...","kind":"<' + "|".join(kinds) + '>",'
        '"attributes":{"gender":"...","role":"...","social_class":"...","affiliation":"...",'
        '"personality":"...","description":"...","goals":"...","secrets":"..."},'
        '"relations":[{"target_name":"...","type":"<' + "|".join(RELATION_TYPES) + '>",'
        '"note":"..."}]} '
        "Omit attributes that do not apply to this kind; every value is 1-3 SPECIFIC "
        "sentences with concrete detail. relations.target_name is the OTHER entity's NAME "
        "(never an id). " + _lang_line(lang)
    )


def executor_messages(source_text: str, item_name: str, item_kind: str,
                      kinds: list[str], lang: str = "vi") -> list[dict]:
    """DEPTH, one item — the E1/E3 focused single-shot shape."""
    system = "You are a profile editor for a fiction glossary. " + _entity_schema_hint(kinds, lang)
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
                     kinds: list[str], lang: str = "vi") -> list[dict]:
    """Deep profile → the short attribute set (one cheap call; spec weakness #3)."""
    system = (
        "You distill a long profile into glossary attributes. " + _entity_schema_hint(kinds, lang)
    )
    user = (
        f"LONG PROFILE of {item_name} (kind: {item_kind}):\n{profile_text}\n\n"
        "Distill it into the JSON attribute object. Keep every value faithful to the "
        "profile — no new inventions in this step."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
