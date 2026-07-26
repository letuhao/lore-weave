# Plan — Deep arc-conformance as a Tier-W job (`D-W10-ARC-CONFORMANCE-DEEP-JOB`)

**Problem (from the SUCCESSION /review-impl, MED):** the `GET …/conformance?scope=arc&deep=true&model_ref=…`
path runs ~120 LLM calls (tag-threads + tag-motifs + infer-causal-edges over the book's events)
**synchronously on a GET** → it will time out on a real book. The spec says arc-conformance is a
Tier-W 202+poll job; the `engine/motif_conformance_run.py` worker stub is its frozen home (it
currently raises `not yet implemented`). The synchronous GET deep+model_ref path is **not reachable
from the UI today** (no model_ref source) — so this gates the FE model-picker: don't ship
UI-triggered deep-tagging until it's a job.

**Scope (L, single-service — composition):** make the deep arc overlay a background job. The full
Tier-W seam already exists end-to-end (MCP `composition_conformance_run` → confirm effect
`_execute_conformance_run` → enqueue → consumer dispatch → `run_conformance_run` → poll
`composition_get_mine_job`); the frozen envelope just needs `arc_template_id` / `model_ref` /
`model_source` threaded, and the worker body filled.

## Build steps

1. **NEW `engine/arc_conformance_orchestrate.py`** — `async compute_arc_report(*, reader, mrepo,
   knowledge, user_id, project_id, book_id, arc, deep, model_ref, model_source)`: the EXACT compute
   currently inline in the GET `scope=arc` branch (arc_bindings → realized rows + order →
   `build_arc_conformance`; on `deep` → tag-threads/tag-motifs/infer-causal-edges (only with a
   model_ref) → read motif-beats + causal-motif-pairs → `build_deep_report`). Takes its
   reader/mrepo/knowledge **injected** (duck-typed) so it imports only the pure builders — no
   router import → no cycle. DRYs the router and the worker.

2. **`routers/conformance.py`** — the GET `scope=arc` branch calls `compute_arc_report` (after its
   own H13 arc-visibility check). Behavior-identical; the synchronous deep+model_ref path stays for
   tests/small books but the FE will use the job.

3. **`engine/motif_conformance_run.py`** — fill `run_conformance_run` for `scope='arc'`: resolve
   work (WorksRepo) + arc (ArcTemplateRepo.get_visible, H13) → construct ConformanceTraceReader +
   MotifRepo from the pool → `compute_arc_report(deep=True, model_ref=input.model_ref, …)` → return
   the report as the job result. `scope='chapter'` stays a terminal ValueError (the cheap
   synchronous GET trace already serves chapter; the chapter extract-diff is a separate unbuilt
   defer — decomposed remainder, not built here).

4. **Envelope threading** — `mcp/server.py` `_ConformanceRunArgs` += `arc_template_id`,
   `model_ref`, `model_source` (+ arc-scope IDOR: arc visible to caller, model_ref required); payload
   carries them. `routers/actions.py` `_execute_conformance_run` spec += the three fields.

5. **Tests** — worker handler (fake pool/reader/knowledge): arc coarse-only (no model_ref) + arc
   deep (model_ref tags then builds overlay) + chapter terminal error + foreign-arc 404-equiv;
   `compute_arc_report` shared-path parity; confirm-effect spec carries the new fields; MCP arg shape.
   Provider-gate clean (the worker passes model_ref through; no SDK/literal).

## Genuinely-next remainder (decomposed, NOT built here)
- **FE model-picker** — propose `composition_conformance_run` (arc + model_ref) → poll → render the
  deep overlay. The model source from CompositionPanel is the last bit (already a tracked FE slice).
- **Chapter extract-diff** — the §14.4 per-scene re-extract diff (folds into
  `D-MOTIF-CONFORMANCE-ENGINE-WIRING`); a different storm, not this one.
