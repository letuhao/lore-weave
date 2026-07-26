# WS-5 W3 `entity-triage` — authored; blocked on a cross-turn activation mechanism gap

**Date:** 2026-07-11 · **model:** gemma-4-26b-a4b-qat · **scenario:** S03 "clean up the suggestions".

## What shipped

- **The `entity-triage` System workflow** (`agent-registry migrate.go`) — a C3 rail:
  `list_ai_suggestions → propose_status_change (keep/reject, confirm) → propose_merge (combine, confirm)
   → list_ai_suggestions (re-check drained)`. `notes_md` is **prescriptive**: it names exactly which tool
  does what (keep/reject = `status_change`; combine = `merge`) and explicitly forbids using
  `propose_entity_edit`/rename or `propose_entities` for triage — because that was the measured failure.
- **The inbox-visibility half now works.** The S03 baseline's "invisible pile" was largely a *stale-data*
  artifact: the current extraction + auto-capture paths DO tag entities `ai-suggested`
  (`extraction_handler.go:524`, `capture_canon_handler.go`), so real suggestions are visible; the 26
  untagged Dracula drafts were legacy. Tagging the fixture (what current extraction produces) makes the
  pile a valid 27-item suggestions list with real duplicates (3× "Dracula" + "Count Dracula") and junk
  ("Gothic Atmosphere"). **With it, the agent discovers + loads the workflow and lists the pile correctly**
  ("I've found 27 suggested items… real items… potential keeps…").

## Why S03 still doesn't drain — a mechanism gap, not the workflow

Across every S03 run the agent lists the pile, then reaches for `glossary_propose_entity_edit` (renaming
"Dracula"→"Count Dracula" to "combine"; editing a Status field to "reject") or `glossary_propose_entities`
(create) — **never** the rail's `status_change`/`merge`. The prescriptive notes forbidding `entity_edit`
did not change this. Root cause, traced through the tool surface:

- `workflow_load` activates the step tools for the LOADING turn (`active_tool_names`), and S01 proved that
  works **in-turn**. But S03 is multi-turn (list in T0, keep/reject in T1).
- **In a naive (non-curated) session, cross-turn activation is dropped.**
  `assemble_initial_active_names` (`tool_surface.py:341-342`) returns **only the hot-seed** when
  `not curated` — `activated_tools` are ignored. And `workflow_load` only *persists* its activation
  `if curated` (`stream_service.py:1669`). A naive session (`enabled_skills=[]`) is **not** curated
  (`is_curated([], []) == False`), so the workflow's `status_change`/`merge` evaporate after T0.
- The glossary **hot-seed** carries the read/create tools but **trims the Tier-W triage writes**
  (`status_change`/`merge`) — the same "write tools trimmed from the hot path" class as the S06 baseline's
  D3 lever. So without a persisted activation, the agent literally cannot see them and falls back to the
  create/edit tools that ARE advertised.

So `entity-triage` is authored correctly and its first step works; the drain is blocked by the discovery
mechanism, not by the workflow.

## The fix (Track A mechanism — scoped, not done here)

Two changes make cross-turn workflows work for a naive user; both are load-bearing discovery-surface edits
that need the workflow-gate + a discovery-eval pass, so they are deliberately NOT slipped into W3:

1. **Persist workflow activation regardless of curated** — `stream_service.py:1669`
   `if curated and activation_state is not None:` → drop the `curated` gate (the persist-to-session at
   `:4337` is already ungated).
2. **Re-advertise activations in auto mode** — `tool_surface.py:341-342`
   `if not curated: return set(hot_seed_names)` → `… return set(hot_seed_names) | set(activated_tools)`.
   This makes a tool the agent explicitly activated (via find_tools / tool_load / workflow_load) stay
   available on later turns in auto mode — arguably a correctness fix for auto-mode discovery generally,
   not just workflows. Guard the growth with the existing `merge_activated_tools` budget.

A cheaper interim lever (same as S06 D3): get the glossary Tier-W triage tools onto the hot path (an
always-hot allowlist / reserved write sub-budget) so they survive the read-first trim.

## Status

- `entity-triage` workflow: **authored + committed** (rail + prescriptive notes; both System workflows now
  seed).
- S03 outcome: **inbox visible + pile listed ✅; drain ❌** pending the cross-turn activation fix.
- This is the concrete, second scenario pointing at the **auto-mode cross-turn activation gap** — a good
  candidate for the next Track A mechanism pass (it unblocks W3 and every multi-turn workflow at once).
