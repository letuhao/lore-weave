"""Build traceability links from events (shared by rules and LLM paths)."""

from __future__ import annotations

import re
from typing import Any


def normalize_planner_notes(events: list[dict[str, Any]]) -> None:
    for ev in events:
        notes = ev.get("planner_notes", [])
        if isinstance(notes, str):
            ev["planner_notes"] = [notes.strip()] if notes.strip() else []
        elif notes is None:
            ev["planner_notes"] = []


def _note_links(ev: dict[str, Any], note: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    nl = note.lower()
    if any(k in nl for k in ("baseline", "dry humor", "hài hước", "ha =", "ha=")):
        out.append(
            {
                "from": ev["id"],
                "to": "charter.consistency_anchors",
                "kind": "event_preserves_anchor",
                "note": note,
            }
        )
    if any(k in nl for k in ("thr", "tiền kiếp", "past life", "resonance")):
        out.append(
            {
                "from": ev["id"],
                "to": "THR",
                "kind": "event_foreshadows",
                "note": note,
            }
        )
    if re.search(r"\bpa\b|perfection addiction|perfection", nl):
        out.append(
            {
                "from": ev["id"],
                "to": "PA",
                "kind": "event_constrains_variable",
                "note": note,
            }
        )
    if re.search(r"\bha\b|humanity anchor", nl):
        out.append(
            {
                "from": ev["id"],
                "to": "HA",
                "kind": "event_constrains_variable",
                "note": note,
            }
        )
    if re.search(r"\bcd\b|corruption debt", nl):
        out.append(
            {
                "from": ev["id"],
                "to": "CD",
                "kind": "event_constrains_variable",
                "note": note,
            }
        )
    if not out:
        out.append(
            {
                "from": ev["id"],
                "to": "planner_note",
                "kind": "event_preserves_anchor",
                "note": note,
            }
        )
    return out


def build_links_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ev in events:
        for nd in ev.get("var_deltas", []):
            key = (ev["id"], nd.get("variable", ""), "event_constrains_variable")
            if key in seen:
                continue
            seen.add(key)
            links.append(
                {
                    "from": ev["id"],
                    "to": nd.get("variable", ""),
                    "kind": "event_constrains_variable",
                    "note": nd.get("reason", ""),
                }
            )
        for note in ev.get("planner_notes", []):
            for link in _note_links(ev, note):
                key = (link["from"], link["to"], link["kind"])
                if key in seen:
                    continue
                seen.add(key)
                links.append(link)
    return links


def merge_links(existing: list[dict[str, Any]], auto: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(existing)
    seen = {(l["from"], l.get("to"), l.get("kind")) for l in existing}
    for link in auto:
        key = (link["from"], link.get("to"), link.get("kind"))
        if key not in seen:
            merged.append(link)
            seen.add(key)
    return merged
