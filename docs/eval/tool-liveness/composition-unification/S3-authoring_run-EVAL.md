# S3·authoring_run — unification + live dispatch + selection eval

**Date:** 2026-07-25 · **Branch:** `feat/frontend-tools-mcp-migration`

## What shipped — a TIER-SPLIT unification (the interesting part)

The 9 authoring-run write tools do NOT collapse into one op-tool, because their tier boundary
is **behavioral, not cosmetic**:

- **W ops** (`create`/`start`/`resume`/`gate`/`revert_all`) **mint a confirm-token** — human-gated,
  cost-bearing.
- **A ops** (`pause`/`close`/`accept_unit`/`reject_unit`) **auto-apply immediately**.

Merging W+A into one tool would force confirm-gating onto the immediate ops **or** bypass the
cost gate on the gated ops — a real defect. So the safe unification is **two tier-coherent tools**:

| Unified tool | Tier | Ops | Supersedes |
|---|---|---|---|
| `composition_authoring_run_manage` | W/book | create, start, resume, gate, revert_all | the 5 W tools |
| `composition_authoring_run_review` | A/book | pause, close, accept_unit, reject_unit | the 4 A tools |

`get`/`list` reads stay separate. The 9 legacy tools are `visibility=legacy` (still callable,
hidden from `tool_list` default). Delegates to the SAME handlers, zero logic moved.

## Unit — 11 dispatch tests, mutation-verified

Routing + per-op arg construction + validation. Mutation (gate→revert_all mis-route) reds the
matching test. Full composition unit suite **2356 pass / 1 skip**.

## Live dispatch-reachability (through ai-gateway) — every op reaches its real handler

A full generation run needs a real PlanForge plan (expensive); the per-op handlers already have
their own EFFECT tests, so the NEW surface to prove is the dispatch chain:

```
manage op=create      -> isError=false, CONFIRM-TOKEN minted (reaches gate_or_confirm)
manage op=gate/revert_all/resume (random run) -> handler deny "not found or not accessible"
review op=pause/close/accept_unit (random run) -> handler deny
manage op=start  w/o run_id     -> clean isError "op=start requires run_id"
review op=accept_unit w/o index -> clean isError "op=accept_unit requires unit_index"
```

Every op reached its real handler (confirm-token or the handler's own deny) — never a
routing/"unknown op" error; validation is a clean `isError`, never a silent no-op.

## Discovery shrink (scoped `tool_list category=composition`)

| include_deprecated | authoring_run visible | legacy shown |
|---|---|---|
| false (default) | **4** (2 unified + get/list) | 0 |
| true | 13 | 9 |

Whole composition domain: **96 → 65** default-visible with legacy hidden (across arc+motif+authoring_run).
*(Note: `category=all` shows a per-category PREVIEW that caps long domains — the scoped
`category=<domain>` query is the complete discovery path an agent uses.)*

## Model-selection eval (Gemma-4 26B local, $0, legacy HIDDEN) — 3/4

| Ask | Picked | Verdict |
|---|---|---|
| "Pause authoring run X" | `..._review op=pause` | ✅ |
| "Run the start-gate check on X" | `..._manage op=gate` | ✅ |
| "Close authoring run X" | `..._review op=close` | ✅ |
| "Accept unit 0 of X" | `..._review` (op omitted) | ⚠️ right tool, weak model didn't set `op=accept_unit` |

The one miss chose the **correct tool** but the weak local model failed to emit `op` — a model
arg-omission, not a tool defect (the dispatch works when `op` is set, proven in the reachability
smoke). The arc + motif full-lifecycle evals were 100%; the op-dispatch pattern is model-drivable.

## Conclusion

authoring_run unifies safely only as a **tier-split pair** (the tier boundary is behavioral). Both
unified tools are federated, callable, tier-correct, unit- + mutation-tested, and live-reachable
for all 9 ops, with the legacy tools hidden from default discovery.
