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
    # ── needs-resweep: callable in code now; the 2026-07-10 matrix is stale (pre-M0a) ──
    "book_chapter_save_draft": {
        "gate": "needs-resweep",
        "reason": "M0a (463091c6a) fixed the uncallable json.RawMessage=array-of-bytes schema; "
                  "the flagship now calls it and lands real prose (2026-07-15, book 019f6571 "
                  "chapters_with_prose=1). The matrix predates M0a, so executes:null is STALE.",
    },
    "glossary_extract_entities_from_doc": {
        "gate": "needs-resweep",
        "reason": "paid=True, but a paid tool on a LOCAL model is $0 (see the spend-correction §). "
                  "Buildable-at-$0 — was mislabeled 'paid/blocked'; a local re-sweep flips it.",
    },
    "composition_get_generation_job": {
        "gate": "needs-resweep",
        "reason": "polls a generation job; a job run on a local model is $0 (Phase 3b planned exactly "
                  "this). Buildable-at-$0, not blocked; needs a job seeded then a re-sweep.",
    },
    "composition_get_mine_job": {
        "gate": "needs-resweep",
        "reason": "same as composition_get_generation_job — local generation job = $0, re-sweep flips it.",
    },
    "kg_schema_edit": {
        "gate": "needs-resweep",
        "reason": "adoption lands on a confirm the harness confirm-resolver (confirm.py) can drive; "
                  "kg_adopt_template is already proven, so this should be reachable on a re-sweep.",
    },
    "kg_sync_apply": {
        "gate": "needs-resweep",
        "reason": "same confirm path as kg_schema_edit; reachable via the harness confirm-resolver on re-sweep.",
    },
    "kg_triage_schema_write": {
        "gate": "needs-resweep",
        "reason": "same confirm path as kg_schema_edit; reachable via the harness confirm-resolver on re-sweep.",
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
