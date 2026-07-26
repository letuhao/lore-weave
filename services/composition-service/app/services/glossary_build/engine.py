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


def _clean_entity(built: Any, *, name: str, kind: str) -> dict | None:
    """Validate/filter one built entity: attributes → str map, relations → closed set."""
    if not isinstance(built, dict):
        return None
    attrs_in = built.get("attributes")
    attrs = {
        str(k): str(v).strip()
        for k, v in (attrs_in.items() if isinstance(attrs_in, dict) else [])
        if v and str(v).strip()
    }
    if not attrs:
        return None
    relations = []
    for r in (built.get("relations") or []):
        if not isinstance(r, dict):
            continue
        target = str(r.get("target_name") or "").strip()
        rtype = r.get("type")
        if target and rtype in RELATION_TYPES and target.casefold() != name.casefold():
            relations.append({"target_name": target, "type": rtype,
                              "note": str(r.get("note") or "")[:300]})
    return {"name": name, "kind": kind, "attributes": attrs, "relations": relations}


async def build_standard(
    llm: Llm, *, source_text: str, name: str, kind: str, kinds: list[str], lang: str,
) -> dict | None:
    """DEPTH, one item, single shot (E1/E3). None ⇒ skip-with-record."""
    built = await _call_json(
        llm, executor_messages(source_text, name, kind, kinds, lang), 2200,
    )
    return _clean_entity(built, name=name, kind=kind)


async def build_deep(
    llm: Llm, *, source_text: str, name: str, kind: str, kinds: list[str], lang: str,
    max_sections: int = 8,
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
            llm, source_text=source_text, name=name, kind=kind, kinds=kinds, lang=lang,
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
        llm, distill_messages(name, kind, profile, kinds, lang), 2200,
    )
    entity = _clean_entity(distilled, name=name, kind=kind)
    if entity is None and sections:
        # Distill failed but the profile exists — keep a minimal honest entity so the
        # long-form work is never silently lost (description = first section).
        entity = {"name": name, "kind": kind,
                  "attributes": {"description": sections[0]["text"][:1500]}, "relations": []}
    return entity, sections
