"""The intent-FSM's ONE LLM step: propose N candidates for a single slot.

Bounds, inherited verbatim from `glossary_build/engine.py` because they are what make a weak model
usable at all: **one call; invalid JSON gets ONE retry with the parse error fed back; then the slot
is `proposal_failed` and SAID SO. No step can loop.**

The step proposes; it never applies. The author is the only thing that turns a candidate into a
value, so a bad proposal costs a glance — it can never become canon on its own.

## Why the prompt is built from the registry, not written per slot

`slots.py` owns the question text and the closed set. A prompt module with its own copy would drift
the moment a slot is added or a beat vocabulary changes per book, and the drift would be invisible:
the model would answer a question the machine is no longer asking.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from app.services.intent_fsm.slots import SlotSpec, choices_for, render

Llm = Callable[[list[dict], int], Awaitable[str]]

_CAND_MAX = 24  # a candidate is a phrase, not a paragraph — a long one is a rewrite, not a choice


def parse_json_block(text: str) -> Any:
    """Tolerant parse — LLM schemas tolerate at validation and filter at postprocess."""
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


def _filled_block(filled: dict[str, Any], lang: str) -> str:
    """What the author has ALREADY settled on this node.

    This is the mechanism behind spec §5's claim that each answer narrows the next: by the time an
    open slot is asked, the model is transforming a partly-specified chapter rather than inventing
    one. Rendering it is therefore not decoration — it is the constraint.
    """
    if not filled:
        return ""
    lines = "\n".join(f"- {k}: {v}" for k, v in filled.items() if str(v).strip())
    if not lines:
        return ""
    head = "ĐÃ CHỐT (do tác giả quyết định — không được mâu thuẫn)" if lang == "vi" \
        else "ALREADY SETTLED BY THE AUTHOR (do not contradict)"
    return f"\n{head}:\n{lines}\n"


def _canon_block(canon: list[str], lang: str) -> str:
    if not canon:
        return ""
    head = "NHÂN VẬT / THỰC THỂ CÓ THẬT trong truyện" if lang == "vi" \
        else "REAL ENTITIES that exist in this story"
    return f"\n{head}: {', '.join(canon[:60])}\n"


def build_messages(
    spec: SlotSpec, *, node: dict[str, Any], filled: dict[str, Any],
    canon: list[str], beats: list[dict[str, Any]], n: int, lang: str = "vi",
) -> list[dict[str, str]]:
    """The single message pair for one slot.

    A closed slot is asked as a PICK (the model returns members of a given set); an open slot is
    asked as a short phrase grounded in what is already settled. The difference is the whole
    experiment of spec §10 Q1, so it lives in one visible branch rather than in prompt prose.
    """
    choices = choices_for(spec.name, beats=beats)
    title = str(node.get("title") or "").strip()
    synopsis = str(node.get("synopsis") or "").strip()
    kind = str(node.get("kind") or "chapter")

    if lang == "vi":
        system = (
            "Bạn là trợ lý biên tập. Bạn KHÔNG viết truyện và KHÔNG quyết định thay tác giả — "
            "bạn chỉ đề xuất vài phương án ngắn để tác giả chọn hoặc sửa. "
            "Chỉ trả về JSON, không giải thích."
        )
        head = f"{kind.upper()}: {title}" + (f"\nTóm tắt: {synopsis}" if synopsis else "")
        ask = f"CÂU HỎI: {spec.question}"
    else:
        system = (
            "You are an editorial assistant. You do NOT write the story and you do NOT decide for "
            "the author — you only offer a few short options for them to pick or correct. "
            "Return JSON only, no commentary."
        )
        head = f"{kind.upper()}: {title}" + (f"\nSynopsis: {synopsis}" if synopsis else "")
        ask = f"QUESTION: {spec.question}"

    if choices:
        rule = (
            f"Chọn tối đa {n} phương án, MỖI phương án PHẢI nằm trong danh sách sau: "
            f"{json.dumps(choices, ensure_ascii=False)}"
            if lang == "vi" else
            f"Pick at most {n} options. EVERY option MUST be a member of this list: "
            f"{json.dumps(choices, ensure_ascii=False)}"
        )
    else:
        rule = (
            f"Đề xuất {n} phương án KHÁC NHAU, mỗi phương án là MỘT cụm từ ngắn "
            f"(tối đa {_CAND_MAX} từ). Không viết văn."
            if lang == "vi" else
            f"Propose {n} DIFFERENT options, each a short phrase (at most {_CAND_MAX} words). "
            f"Do not write prose."
        )

    shape = (
        'Trả về đúng: {"candidates": [{"value": ..., "why": "một câu ngắn"}]}'
        if lang == "vi" else
        'Return exactly: {"candidates": [{"value": ..., "why": "one short sentence"}]}'
    )

    user = "\n".join(x for x in (
        head,
        _filled_block(filled, lang),
        _canon_block(canon, lang),
        "",
        ask,
        rule,
        shape,
    ) if x != "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def clean_candidates(
    raw: Any, spec: SlotSpec, *, choices: list[Any], n: int,
) -> list[dict[str, Any]]:
    """Validate, coerce and de-duplicate the model's output.

    A closed slot DROPS anything outside its set rather than passing it through — the value would
    fail the column's own constraint later, and an author shown an option that cannot be applied has
    been offered a broken choice. A candidate that fails coercion is likewise dropped, not repaired:
    guessing what the model meant is how a machine starts authoring.

    Returning `[]` is a legitimate, meaningful result — the caller records `proposal_failed` and the
    slot stays UNASKED-and-said-so. It is never a silent skip.
    """
    rows = raw.get("candidates") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return []
    allowed = {render(spec.name, c) for c in choices} if choices else None
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        value = row.get("value") if isinstance(row, dict) else row
        why = str(row.get("why") or "")[:200] if isinstance(row, dict) else ""
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        try:
            coerced = spec.coerce(value)
        except Exception:  # noqa: BLE001 — a candidate that will not fit the column is not a candidate
            continue
        key = render(spec.name, coerced)
        if allowed is not None and key not in allowed:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append({"value": coerced, "why": why})
        if len(out) >= n:
            break
    return out


async def propose(
    llm: Llm, spec: SlotSpec, *, node: dict[str, Any], filled: dict[str, Any],
    canon: list[str], beats: list[dict[str, Any]], n: int = 3, lang: str = "vi",
) -> tuple[list[dict[str, Any]], int, bool]:
    """One slot's proposal. Returns ``(candidates, llm_calls, retried)``.

    The call count and the retry flag are returned rather than logged because the POC has to PROVE
    the one-call/one-retry bound held (spec §8) — a bound that is only asserted in a docstring is
    not a bound.
    """
    choices = choices_for(spec.name, beats=beats)
    messages = build_messages(spec, node=node, filled=filled, canon=canon, beats=beats,
                              n=n, lang=lang)
    raw_text = await llm(messages, 700)
    parsed = parse_json_block(raw_text)
    cands = clean_candidates(parsed, spec, choices=choices, n=n)
    if cands:
        return cands, 1, False

    retry = messages + [
        {"role": "assistant", "content": raw_text[-1200:]},
        {"role": "user", "content": (
            "That was not usable. Return ONLY the JSON object in the requested shape — "
            "no markdown, no commentary."
        )},
    ]
    cands = clean_candidates(parse_json_block(await llm(retry, 700)), spec, choices=choices, n=n)
    return cands, 2, True
