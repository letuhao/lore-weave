"""Searchable index over NovelSystemSpec for fuzzy feedback scope location."""

from __future__ import annotations

import re
from typing import Any


def build_spec_index(spec: dict[str, Any], section_map: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    char = ((spec.get("layers") or {}).get("characters") or [None])[0]
    if char:
        entries.append(
            {
                "path": "layers.characters[0]",
                "label_vn": "Nhân vật / character seed",
                "section_id": "1.3",
                "keywords": ["nhân vật", "character", "traits", "baseline", "§1"],
                "excerpt_preview": (char.get("baseline_notes") or "")[:300],
            }
        )

    for m in (spec.get("layers") or {}).get("mechanics") or []:
        mid = m.get("id", "mechanic")
        entries.append(
            {
                "path": f"layers.mechanics[{mid}]",
                "label_vn": m.get("name", mid),
                "section_id": "3.4",
                "keywords": ["mechanic", "đạo hóa", "công pháp", mid],
                "excerpt_preview": " ".join((m.get("rules") or [])[:2])[:300],
            }
        )

    for e in spec.get("events", []):
        if e.get("arc_id") != "arc_2":
            continue
        eid = e.get("id", "")
        title = e.get("title", "")
        num_m = re.search(r"(\d+)", title)
        event_num = num_m.group(1) if num_m else ""
        entries.append(
            {
                "path": f"events[{eid}]",
                "label_vn": title,
                "section_id": f"event_{event_num}" if event_num else "",
                "keywords": [
                    title.lower(),
                    f"event {event_num}",
                    f"event{event_num}",
                    eid,
                ],
                "excerpt_preview": (e.get("synopsis") or "")[:300],
            }
        )

    for s in section_map:
        sid = str(s.get("section_id", ""))
        if sid.startswith("1."):
            entries.append(
                {
                    "path": f"source:{sid}",
                    "label_vn": s.get("title", sid),
                    "section_id": sid,
                    "keywords": [sid, s.get("title", "").lower()],
                    "excerpt_preview": (s.get("excerpt") or "")[:300],
                }
            )

    return entries


def _score_hit(query: str, entry: dict[str, Any]) -> float:
    q = query.lower()
    score = 0.0
    label = (entry.get("label_vn") or "").lower()
    if label and label in q:
        score += 3.0
    for kw in entry.get("keywords") or []:
        kwl = str(kw).lower()
        if kwl and kwl in q:
            score += 2.0
    path = entry.get("path", "")
    if path.split("[")[-1].rstrip("]") in q:
        score += 1.5
    preview = (entry.get("excerpt_preview") or "").lower()
    for token in re.findall(r"[\w\u00C0-\u1EF9]+", q):
        if len(token) > 2 and token in preview:
            score += 0.5
    return score


def search_index(query: str, index: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    scored = [(e, _score_hit(query, e)) for e in index]
    scored = [(e, s) for e, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [{**e, "score": s} for e, s in scored[:top_k]]


def spec_slice_for_paths(spec: dict[str, Any], paths: list[str], max_chars: int = 4000) -> str:
    """Extract a small JSON slice for interpret/refine prompts."""
    import json

    out: dict[str, Any] = {}
    for p in paths:
        if p.startswith("events["):
            eid = p.split("[", 1)[1].rstrip("]")
            for e in spec.get("events", []):
                if e.get("id") == eid:
                    out[p] = e
        elif p == "layers.characters[0]":
            chars = (spec.get("layers") or {}).get("characters") or []
            if chars:
                out[p] = chars[0]
        elif p.startswith("layers.mechanics"):
            mid = p.split("[", 1)[1].rstrip("]") if "[" in p else ""
            for m in (spec.get("layers") or {}).get("mechanics") or []:
                if m.get("id") == mid:
                    out[p] = m
    blob = json.dumps(out, ensure_ascii=False, indent=2)
    return blob[:max_chars]
