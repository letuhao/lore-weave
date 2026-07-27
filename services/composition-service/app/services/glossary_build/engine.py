"""The glossary-build LLM steps — pure orchestration over an injected ``llm`` callable.

``llm`` is ``async (messages: list[dict], max_tokens: int) -> str`` — the service
layer (M2) binds it to the real SDK via provider-registry (model_ref from run
params, never a literal); unit tests bind fakes.

Bounds (spec, PO-locked): every step is ONE call; invalid JSON gets ONE retry
(with the parse error fed back), then the item/section is SKIPPED with a record.
No step can loop.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from app.services.glossary_build.prompts import (
    RELATION_TYPES,
    batch_messages,
    deep_outline_messages,
    deep_section_messages,
    distill_messages,
    executor_messages,
    planner_messages,
)

Llm = Callable[[list[dict], int], Awaitable[str]]


def parse_json_block(text: str) -> Any:
    """Tolerant parse (LLM schemas tolerate at validation, filter at postprocess)."""
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def _call_json(llm: Llm, messages: list[dict], max_tokens: int) -> Any:
    """One call + ONE retry with the failure named — then None (caller skips)."""
    out = await llm(messages, max_tokens)
    parsed = parse_json_block(out)
    if parsed is not None:
        return parsed
    retry = messages + [
        {"role": "assistant", "content": out[-1500:]},
        {"role": "user", "content": (
            "That was not valid JSON. Return ONLY the JSON, exactly in the requested "
            "shape — no markdown, no commentary."
        )},
    ]
    return parse_json_block(await llm(retry, max_tokens))


async def run_planner(
    llm: Llm, *, source_text: str, kinds: list[str], existing_names: list[str],
    lang: str, max_items: int = 30,
) -> list[dict]:
    """BREADTH: the validated worklist [{name, kind, depth, why}]. Invalid rows and
    duplicates (vs the glossary AND within the list) are filtered, never fatal."""
    raw = await _call_json(
        llm, planner_messages(source_text, kinds, existing_names, lang, max_items), 1600,
    )
    if not isinstance(raw, list):
        return []
    existing_fold = {n.strip().casefold() for n in existing_names}
    seen: set[str] = set()
    out: list[dict] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        kind = str(row.get("kind") or "").strip()
        if not name or kind not in kinds:
            continue
        fold = name.casefold()
        if fold in existing_fold or fold in seen:
            continue
        seen.add(fold)
        depth = row.get("depth") if row.get("depth") in ("standard", "deep") else "standard"
        out.append({"name": name, "kind": kind, "depth": depth,
                    "why": str(row.get("why") or "")[:300]})
        if len(out) >= max_items:
            break
    return out


# A weak model often writes the WORD instead of JSON null. Treated as the same
# declaration — otherwise "chưa xác định" lands in the glossary as canon text.
# Deliberately NOT here: bare "na" (a real Vietnamese noun) — "n/a" covers the
# placeholder without risking a legitimate one-word value.
_NULLISH = {"null", "none", "nil", "n/a", "-", "--", "?", "unknown",
            "không có", "khong co", "chưa có", "chưa xác định", "không rõ"}


def _clean_entity(built: Any, *, name: str, kind: str,
                  allowed: list[str] | None = None) -> dict | None:
    """Validate/filter one built entity: attributes → str map, relations → closed set.

    NO-EMPTY-SHELL INVARIANT (M6): when `allowed` is given (the kind's REAL attribute
    codes), anything outside it is DROPPED — the glossary would silently ignore it
    anyway. If nothing survives, return None so the caller records a SKIP. The old
    code wrote whatever the model produced, which is how a character-shaped payload
    against a `terminology` kind created rows with no name and no attributes.

    DECLARED ABSENCE: an empty value on a field the kind DOES define is reported as
    `absent` (the story has not established it — an authoring prompt for the human at
    CP2, not a defect), while a field never mentioned at all is `missing` (an
    attention drop — the only signal that would justify a repair call). Collapsing
    the two is what makes an auto-fill loop dangerous: it re-asks for things the
    story genuinely has no answer to, and the model obliges by inventing."""
    if not isinstance(built, dict):
        return None
    attrs_in = built.get("attributes")
    allow = {c.casefold() for c in (allowed or [])}
    attrs: dict[str, Any] = {}
    absent: list[str] = []
    for k, v in (attrs_in.items() if isinstance(attrs_in, dict) else []):
        code = str(k)
        if allow and code.casefold() not in allow:
            continue
        if isinstance(v, list):
            # A `tags`-typed field comes back as a JSON array — KEEP it one. The
            # old `str(v)` produced a Python repr ("['a', 'b']") that the glossary
            # then wrapped again, yielding ["['a', 'b']"]: live-caught on aliases.
            items = [str(x).strip() for x in v
                     if str(x).strip() and str(x).strip().casefold() not in _NULLISH]
            if items:
                attrs[code] = items
            else:
                absent.append(code)
        elif v is None or not str(v).strip() or str(v).strip().casefold() in _NULLISH:
            absent.append(code)
        else:
            attrs[code] = str(v).strip()
    if not attrs:
        return None
    seen = {c.casefold() for c in list(attrs) + absent}
    missing = [c for c in (allowed or []) if c.casefold() not in seen]
    relations = []
    for r in (built.get("relations") or []):
        if not isinstance(r, dict):
            continue
        target = str(r.get("target_name") or "").strip()
        rtype = r.get("type")
        if target and rtype in RELATION_TYPES and target.casefold() != name.casefold():
            relations.append({"target_name": target, "type": rtype,
                              "note": str(r.get("note") or "")[:300]})
    return {"name": name, "kind": kind, "attributes": attrs, "relations": relations,
            "absent": absent, "missing": missing}


async def build_standard(
    llm: Llm, *, source_text: str, name: str, kind: str, fields: list[str], lang: str,
    types: dict[str, str] | None = None,
) -> dict | None:
    """DEPTH, one item, single shot (E1/E3) over the kind's REAL fields.
    None ⇒ skip-with-record (never a hollow row)."""
    built = await _call_json(
        llm, executor_messages(source_text, name, kind, fields, lang, types), 2200,
    )
    return _clean_entity(built, name=name, kind=kind, allowed=fields)


async def build_batch(
    llm: Llm, *, source_text: str, names: list[str], kind: str, fields: list[str],
    lang: str, types: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Several SAME-KIND entities in ONE call (one schema). Returns {name: entity}
    for whatever came back clean — a name missing from the result is simply not
    built, and the caller falls back to per-item for it. Measured 3x cheaper with
    mild positional decay; never used for `deep` items or across kinds."""
    arr = await _call_json(
        llm, batch_messages(source_text, names, kind, fields, lang, types), 2600,
    )
    if not isinstance(arr, list):
        return {}
    by_name: dict[str, dict] = {}
    wanted = {n.casefold(): n for n in names}
    for row in arr:
        if not isinstance(row, dict):
            continue
        got = wanted.get(str(row.get("name") or "").strip().casefold())
        if not got:
            continue
        ent = _clean_entity(row, name=got, kind=kind, allowed=fields)
        if ent is not None:
            by_name[got] = ent
    return by_name


async def build_deep(
    llm: Llm, *, source_text: str, name: str, kind: str, fields: list[str], lang: str,
    types: dict[str, str] | None = None, max_sections: int = 8,
) -> tuple[dict | None, list[dict]]:
    """DEPTH x10 (E4): outline → steer one section per call (varied craft, same
    conversation) → distill to attributes. Returns (entity|None, sections).

    Degrade-safe: a failed outline falls back to build_standard's shape (the run
    keeps its no-silent-seam guarantee — the fallback is recorded by the caller
    via the empty sections list)."""
    outline_msgs = deep_outline_messages(source_text, name, kind, lang)
    outline = await _call_json(llm, outline_msgs, 900)
    plan = [
        p for p in (outline if isinstance(outline, list) else [])
        if isinstance(p, dict) and str(p.get("section") or "").strip()
    ][:max_sections]
    if not plan:
        return await build_standard(
            llm, source_text=source_text, name=name, kind=kind, fields=fields,
            lang=lang, types=types,
        ), []

    convo = outline_msgs + [{"role": "assistant", "content": json.dumps(plan, ensure_ascii=False)}]
    sections: list[dict] = []
    for i, p in enumerate(plan):
        convo.append(deep_section_messages(str(p["section"]), str(p.get("focus") or ""), i))
        text = (await llm(convo, 800)).strip()
        convo.append({"role": "assistant", "content": text})
        if text:
            sections.append({"section": str(p["section"]), "text": text})

    profile = "\n\n".join(f"[{s['section']}]\n{s['text']}" for s in sections)
    distilled = await _call_json(
        llm, distill_messages(name, kind, profile, fields, lang, types), 2200,
    )
    entity = _clean_entity(distilled, name=name, kind=kind, allowed=fields)
    if entity is None and sections:
        # Distill failed but the profile exists — keep a minimal honest entity so the
        # long-form work is never silently lost (description = first section).
        # Distill failed but the profile exists — keep it under a field the kind
        # ACTUALLY has, or the salvage would itself be a silently-dropped write.
        _fallback = "description" if "description" in fields else (fields[0] if fields else "")
        entity = ({"name": name, "kind": kind,
                   "attributes": {_fallback: sections[0]["text"][:1500]}, "relations": [],
                   "absent": [], "missing": [f for f in fields if f != _fallback]}
                  if _fallback else None)
    return entity, sections
