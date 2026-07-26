"""Waivers source for the tool-liveness manifest (D-TRACKD-REACCOUNT, 2026-07-15).

The WS-D4 Exit criterion (TRACK-D-COMPLETION.md) requires that a tool which is not
`executes:true` carry an **explicit `waived` + reason IN THE MANIFEST** — not in a prose
table. `manifest.py.build()` reads this dict and stamps `waived:{reason, gate}` onto any
tool whose merged `executes` is not `true`. That makes a deliberate waive
machine-distinguishable from an un-probed `null` (the exact gap the 2026-07-15 cold-start
audit found: 13 waives lived only in prose, byte-indistinguishable from "never checked").

`gate` is a CLOSED enum (spec §5 OQ-2):
  - external        : depends on an upstream service / public data this repo doesn't own.
  - upstream-drift  : needs a drifted-standard state to exercise (can't be freshly seeded).
  - needs-resweep   : callable in code TODAY but the last matrix predates the fix / the
                      sweep didn't reach it; a post-M0a re-sweep is expected to flip it to
                      executes:true. (This is where the audit's rationalized/mislabeled
                      waives go — honest "stale null", not a false "genuine external waive".)
  - deferred-build  : needs an in-repo fixture (a hand-authored multi-FK seed) not yet
                      written. Buildable work, not a blocker — tracked, not pretended-done.

A tool listed here that later returns `executes:true` from a real sweep simply stops being
stamped (the manifest's `executes:true` wins; `build()` only stamps non-true tools). Do NOT
add a tool here to silence a genuine `executes:false` — that is a BROKEN tool the ship gate
must keep rejecting; a waiver never covers `false`.
"""
from __future__ import annotations

GATES = frozenset({"external", "upstream-drift", "needs-resweep", "deferred-build"})

# tool_name -> {"reason": <human>, "gate": <enum>}
WAIVERS: dict[str, dict[str, str]] = {
    # ── needs-resweep: NL-provable by a real model, but the $0 DETERMINISTIC sweep can't drive
    #    the effect. Flips on an NL-matrix re-run, not a cheap capability sweep. ──
    "book_chapter_save_draft": {
        "gate": "needs-resweep",
        "reason": "NL-PROVEN: M0a (463091c6a) fixed the uncallable json.RawMessage=array-of-bytes schema, "
                  "and this session's flagship (a real gemma run, book 019f6571) called it and landed real "
                  "prose (chapters_with_prose=1). The 2026-07-15 deterministic re-sweep still can't attribute "
                  "the call ('rejected for a reason we cannot attribute to the tool' — it lacks the "
                  "base_version precondition the NL rail sets up). The 2026-07-10 matrix predates M0a, so "
                  "executes:null is STALE — an NL-matrix re-run flips it to true.",
    },
    "glossary_extract_entities_from_doc": {
        "gate": "needs-resweep",
        "reason": "paid=True, but a paid tool on a LOCAL model is $0 (spend-correction §). The 2026-07-15 "
                  "re-sweep scored it 'paid or not authorable — effect not verified at $0' because the "
                  "deterministic sweep skips paid effect-verification; an NL run on a local model reaches it.",
    },
    # ── deferred-build: the 2026-07-15 re-sweep verdict was "required arg needs authored/
    #    structured input" — the $0 deterministic sweep cannot synthesize the seed; buildable ──
    "composition_get_generation_job": {
        "gate": "deferred-build",
        "reason": "2026-07-15 re-sweep: 'required arg needs authored/structured input' — needs a "
                  "generation job seeded first (a local job is $0). Buildable fixture not yet written.",
    },
    "composition_get_mine_job": {
        "gate": "deferred-build",
        "reason": "2026-07-15 re-sweep: 'required arg needs authored/structured input' — same seeded-job "
                  "precondition as composition_get_generation_job.",
    },
    "kg_schema_edit": {
        "gate": "deferred-build",
        "reason": "2026-07-15 re-sweep: 'required arg needs authored/structured input' — the sweep's "
                  "confirm-resolver reaches the gate but can't author the schema-edit payload.",
    },
    "kg_sync_apply": {
        "gate": "deferred-build",
        "reason": "2026-07-15 re-sweep: 'required arg needs authored/structured input' — same as kg_schema_edit.",
    },
    "kg_triage_schema_write": {
        "gate": "deferred-build",
        "reason": "2026-07-15 re-sweep: 'required arg needs authored/structured input' — same as kg_schema_edit.",
    },
    # ── deferred-build: needs an in-repo hand-authored multi-FK seed (buildable, not written) ──
    "glossary_create_evidence": {
        "gate": "deferred-build",
        "reason": "needs an entity_attribute_values row + a matching attr_def_id to attach evidence to.",
    },
    "glossary_propose_restore_revision": {
        "gate": "deferred-build",
        "reason": "needs an entity_revisions snapshot to restore from (a prior edit history).",
    },
    "composition_arc_apply": {
        "gate": "deferred-build",
        "reason": "needs an arc_templates row seeded to apply.",
    },
    "composition_arc_import_analyze": {
        "gate": "deferred-build",
        "reason": "needs an import_sources row (an imported document) to analyze.",
    },
    # ── genuinely external: depends on state this repo doesn't own ──
    "catalog_get_book": {
        "gate": "external",
        "reason": "needs a PUBLIC book published through sharing-service — an external publish state, "
                  "not something the sweep can seed on the author's own private library.",
    },
    "glossary_book_sync_apply": {
        "gate": "upstream-drift",
        "reason": "syncs a book's adopted standards against an UPSTREAM standard that has since drifted; "
                  "requires a drifted-standard state that can't be freshly seeded (decide-when-reached).",
    },
}


def waiver_for(tool: str) -> dict[str, str] | None:
    """Return {reason, gate} for a waived tool, or None. Used by manifest.build()."""
    w = WAIVERS.get(tool)
    if w is None:
        return None
    if w["gate"] not in GATES:  # defence-in-depth against a typo'd gate
        raise ValueError(f"waiver for {tool!r} has invalid gate {w['gate']!r}; must be one of {sorted(GATES)}")
    return {"reason": w["reason"], "gate": w["gate"]}
