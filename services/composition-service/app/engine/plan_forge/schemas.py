"""Decoder-enforced shapes for the two PlanForge LLM steps.

## Why this is the load-bearing fix

The LLM propose path is the ONE path that works without the section classifier — it reads the
author's raw markdown and emits the whole spec. Measured 2026-07-28, the classifier does not
generalise (on a second corpus it recovers one kind out of nine and gets that one wrong), so the
LLM path is where quality actually comes from.

And it was the only path that could not enforce a schema. `ProviderPlanForgeLLM.chat` had no
`response_format` parameter at all, so both steps asked for free text, hand-parsed it, and on a
parse failure spent a SECOND 12,000-token call asking the model to repair its own JSON. That
capped everything above it.

Measured before writing any of this (`docs/specs/2026-07-28-poc-material-read.md` §6d): schema
enforcement takes parse failures 2 → 0, leaves answer quality unchanged, and makes a fixed-seed run
reproducible 18/18.

## The shape these schemas take, and why they are not tighter

The spec is large and deeply nested, and a grammar **cannot stop early in a valid place** — under a
budget it keeps emitting structure, so truncation produces JSON no parser can recover (live-observed
at a too-small `max_tokens`). An over-closed schema on a 12k-token spec is therefore a way to
manufacture the exact failure this is meant to remove.

So: close the TOP LEVEL (the keys every consumer reads) and the two genuine enums, and leave the
item objects permissive. The prompts ask for the descriptive fields; the grammar guarantees the
skeleton. `normalize_spec` still runs afterwards, so nothing downstream changes shape.
"""
from __future__ import annotations

from typing import Any

#: An arc's kind, as the prompt already declares it. A value outside this set is one the compiler's
#: banding does not know, so it silently reads as neutral — closing it here means the model cannot
#: produce one rather than producing one that quietly means nothing.
ARC_KINDS = ["setup", "discovery", "power", "transition", "other"]

#: The link graph's relation types, likewise straight from the prompt.
LINK_KINDS = [
    "event_constrains_variable",
    "event_preserves_anchor",
    "event_foreshadows",
    "arc_depends_on_mechanic",
    "variable_governs_tier",
]

_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """An object that REQUIRES its skeleton and tolerates the rest.

    `additionalProperties` is left open on purpose: the prompts ask for optional descriptive fields
    (`source_excerpt`, `exit_state`, `coupled_to_realm`) that a closed shape would forbid, and
    forbidding them would silently strip material the author's document actually contained.
    """
    return {"type": "object", "properties": props, "required": required}


#: Unbounded — and the reason is a correction of my own reasoning, not a result.
#:
#: The materialize step was live-observed emitting a **37,858-character** response at
#: `max_tokens=12000`, failing to parse, and costing a second 12k repair call. Since a grammar
#: cannot stop early in a valid place, "nothing tells it to stop" looked obvious, so `maxItems` went
#: on every array. That run came back much worse — 1 character, 0 events, 0 links — and I was about
#: to record "llama.cpp degrades under nested maxItems" as a finding.
#:
#: **Then I ran the control I should have run first.** Schema-off vs schema-on on the SAME analyze
#: output: 4,950 vs 4,011 characters, byte-identical extraction (4 characters, 2 arcs, 2 events).
#: The schema changes nothing here, and a no-schema run on the other corpus produced the same
#: collapsed output the "bad" bounded run had. **The runaways and the collapses are pre-existing
#: variance in this weak model — largely in the ANALYZE step, which returns 4 arcs / 4 events on one
#: attempt and 1 arc / 0 events on the next — and I had attributed four uncontrolled observations to
#: my own change.**
#:
#: So `maxItems` stays out on honest grounds: unproven benefit, one observed bad run that cannot be
#: attributed to it. And the schema stays in on equally honest grounds: measured neutral here, and
#: measured 2 → 0 on parse failures where the shape is small enough to bind (§6d). The one repair
#: call remains the safety net for the variance, which is what it was always for.
#:
#: The real instability is upstream in `analyze` and is NOT addressed here. It needs its own
#: controlled measurement rather than another confident guess.


def _arr(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


_VARIABLE = _obj({
    "code": _STR, "name": _STR, "range": _STR,
    "transition_rules": _STRS, "not_coupled_to": _STRS,
}, ["code", "name"])

_MECHANIC = _obj({"name": _STR, "rules": _STRS, "planner_secrets": _STRS}, ["name", "rules"])

_ARC = _obj({
    "id": _STR, "title": _STR, "theme": _STR,
    "arc_kind": {"type": "string", "enum": ARC_KINDS},
    "summary": _STR,
}, ["id", "title"])

_EVENT = _obj({
    "id": _STR, "arc_id": _STR, "title": _STR, "synopsis": _STR, "goal": _STR,
    "planner_notes": _STRS,
    "var_deltas": _arr(_obj({"variable": _STR, "delta": _STR, "reason": _STR},
                            ["variable", "delta"])),
}, ["id", "arc_id", "title", "synopsis"])


#: PlanAnalyze v1 — step 1, the read of the author's document.
ANALYZE_SCHEMA: dict[str, Any] = _obj({
    "version": {"type": "integer"},
    "document_summary": _STR,
    "consistency_anchors": _STRS,
    "variables": _arr(_VARIABLE),
    "mechanics": _arr(_MECHANIC),
    "arcs": _arr(_ARC),
    "events": _arr(_EVENT),
    "forbids": _STRS,
    "style_constraints": _STRS,
    "open_questions": _STRS,
}, ["document_summary", "arcs", "events"])


#: NovelSystemSpec v1 — step 2, what `compile_artifacts` reads.
#:
#: `arcs` and `events` are required TOGETHER because the prompt's highest-priority rule is that every
#: declared arc has at least one event: an arc with none cannot be compiled. The grammar cannot
#: express that relation, but it can guarantee both keys exist so the failure is a visible empty
#: rather than a missing key nobody checked.
SPEC_SCHEMA: dict[str, Any] = _obj({
    "version": {"type": "integer"},
    "meta": _obj({
        "title": _STR, "version_label": _STR, "source_checksum": _STR,
        "open_questions": _STRS,
    }, ["title"]),
    "charter": _obj({
        "consistency_anchors": _STRS, "forbids": _STRS, "style_constraints": _STRS,
    }, []),
    "layers": _obj({
        "characters": _arr(_obj({
            "id": _STR, "name": _STR, "role": _STR, "traits": _STRS, "baseline_notes": _STR,
        }, ["id", "name"])),
        "mechanics": _arr(_obj({
            "id": _STR, "name": _STR, "rules": _STRS, "planner_secrets": _STRS,
        }, ["id", "name"])),
        "variables": _arr(_VARIABLE),
    }, ["characters", "mechanics", "variables"]),
    "arcs": _arr(_ARC),
    "events": _arr(_EVENT),
    "links": _arr(_obj({
        "from": _STR, "to": _STR,
        "kind": {"type": "string", "enum": LINK_KINDS},
        "note": _STR,
    }, ["from", "to", "kind"])),
}, ["meta", "charter", "layers", "arcs", "events"])
