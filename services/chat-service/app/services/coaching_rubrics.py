"""WS-5.20/5.21 (spec 08 §Scorer) — the coaching-rubric SoT + Scorecard dimension coercion.

A coaching score needs a STANDARD (data), versioned + cited — the free-form
SessionTemplate.rubric ("improvised standards already ship") is replaced by System-tier
`coaching_rubrics`. Two guarantees:
- **No rubric ⇒ no score** (P5-D5): `resolve_active_rubric` returns None when nothing is
  seeded, and the caller REFUSES to score — an improvised standard is worse than none.
- **Dimensions are SERVER-AUTHORITATIVE** (WS-5.21): `coerce_dimensions` rebuilds the scored
  dimension set from the RUBRIC's keys, so the model can neither drop nor invent a dimension —
  it only contributes a 1-5 score per fixed key (the checklist's safe-when-wrong guarantee,
  generalized). The scored subject is always the user.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable

import asyncpg


@dataclass(frozen=True)
class RubricDimension:
    key: str
    label: str
    anchors: dict  # {"1": "...", "5": "..."}


@dataclass(frozen=True)
class CoachingRubric:
    code: str
    version: int
    label: str
    dimensions: tuple[RubricDimension, ...]
    tier: str  # 'quarantine' | 'validated'


def _parse_dimensions(raw) -> tuple[RubricDimension, ...]:
    items = raw if isinstance(raw, list) else json.loads(raw or "[]")
    out = []
    for d in items:
        if isinstance(d, dict) and isinstance(d.get("key"), str):
            out.append(RubricDimension(
                key=d["key"], label=str(d.get("label") or d["key"]),
                anchors=d.get("anchors") if isinstance(d.get("anchors"), dict) else {},
            ))
    return tuple(out)


async def resolve_active_rubric(pool: asyncpg.Pool, code: str) -> CoachingRubric | None:
    """The active System-tier rubric for `code` (highest version). None ⇒ the caller REFUSES
    to score (P5-D5) — never an improvised fallback."""
    row = await pool.fetchrow(
        """
        SELECT code, version, label, dimensions, tier FROM coaching_rubrics
        WHERE code = $1 AND is_active = true
        ORDER BY version DESC LIMIT 1
        """,
        code,
    )
    if row is None:
        return None
    dims = _parse_dimensions(row["dimensions"])
    if not dims:
        return None  # a rubric with no dimensions can't score anything
    return CoachingRubric(
        code=row["code"], version=row["version"], label=row["label"],
        dimensions=dims, tier=row["tier"],
    )


def coerce_dimensions(raw: dict, rubric: CoachingRubric) -> list[dict]:
    """WS-5.21 — build the scored dimensions SERVER-AUTHORITATIVELY from the rubric's keys.
    The model's reply contributes only a clamped 1-5 `score` + optional `note` per KNOWN key;
    a dimension the model omitted is scored None (not dropped), and a dimension the model
    invented is ignored (not surfaced)."""
    reported = {}
    for entry in raw.get("dimensions") or []:
        if isinstance(entry, dict) and isinstance(entry.get("key"), str):
            reported[entry["key"]] = entry
    out = []
    for dim in rubric.dimensions:
        entry = reported.get(dim.key, {})
        score = entry.get("score")
        # Reject bool (an int subclass) AND non-finite floats: Python's JSON decoder accepts the
        # bare tokens NaN/Infinity/-Infinity, which pass the isinstance guard but make int() raise
        # (ValueError/OverflowError). Since card.dimensions is built OUTSIDE evaluate's try/except,
        # an unguarded raise here would surface as a 500 — breaking the "garbled reply ⇒ empty-but-
        # valid scorecard, never a 500" guarantee (C3 cold-review MED). Coerce them to None instead.
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            score = None
        else:
            score = max(1, min(5, int(score)))
        note = entry.get("note")
        out.append({
            "key": dim.key, "label": dim.label,
            "score": score, "note": note if isinstance(note, str) else None,
        })
    return out


# ── WS-5.23 (spec 08 §Scorer, Q4 R3-cite) — coaching-KB citation resolution ───
def unresolved_citations(citations: list[str], resolve: "Callable[[str], bool]") -> list[str]:
    """The coaching knowledge-base = a kind='lore' book of curated CITED frameworks. Each cited
    reference MUST individually resolve before sign-off (a coaching claim with a dangling
    citation is an unsourced opinion). Returns the citations that DON'T resolve — a non-empty
    result BLOCKS sign-off (the caller drops the offending content, never ships it uncited).
    Blank/whitespace citations count as unresolved (an empty citation is not a source)."""
    bad: list[str] = []
    for c in citations:
        if not (c or "").strip():
            bad.append(c)
            continue
        try:
            if not resolve(c):
                bad.append(c)
        except Exception:
            bad.append(c)  # a resolver error = not proven to resolve -> fail closed
    return bad
