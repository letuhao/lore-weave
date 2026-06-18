# Plan — WX Recovery+Filter decouple (Wave 4, `D-WX-RECOVERY-FILTER-DECOUPLE`)

**Goal.** Extend the decoupled extraction path (entity→trio→persist) to the optional
**recovery** + **filter** stages, so projects that configure either no longer fall back
to the synchronous `extract_pass2`. The pure SM transitions and the SDK
`build_*`/`parse_*`/`apply_*` seams already exist; this wires the async shell + the
consumer + the runner.

## Pipeline (unchanged DAG)

```
entity ─▶ trio(rel/event/fact) ─▶ [recovery] ─▶ [filter*] ─▶ persist
                                   (N batches)   (cat×batch)
```
Stages gated on `has_recovery` / `has_filter` (project config). worker-ai has **no
glossary access** ⇒ recovery Tier-1+2 promotes nothing ⇒ all unmatched names go to
Tier-3 LLM batches (matches the sync path's behaviour there).

## Shell (`decoupled_extract.py`)

- **Recovery** (`assemble_recovery`, `fold_recovery_terminal`):
  - `assemble_recovery(rs)` — reconstruct candidates, run `prepare_recovery` inline
    (Tier-1+2, no LLM), snapshot the post-trio `entities`/`relations` as the immutable
    recovery base, seed accumulators (`recovery_promoted=[]`, `recovery_name_verdict={}`,
    `recovery_batch_names`), and `build_recovery_batches(still_unmatched, text, cfg)` →
    `{batch_key: submit_kwargs}`. No unmatched ⇒ empty map (dispatcher advances).
  - `fold_recovery_terminal(rs, batch_key, job)` — `parse_recovery_job` → `_parse_decisions`
    → `apply_recovery_batch` into the accumulators → `finalize_recovery(base, promoted,
    name_verdict)` to recompute `entities`/`relations` (idempotent/monotonic from the base
    each fold) → SM `fold_recovery_task`.
- **Filter** (`assemble_filter`, `fold_filter_terminal`, `finalize_filter`):
  - `assemble_filter(rs)` — for each `cfg.categories` with items,
    `build_filter_category_batches(cat, items, text, cfg)` → `{task_key=f:cat:start:
    submit_kwargs}`; seed `filter_batch_meta` (category+batch_start+n) + `filter_n_input`.
  - `fold_filter_terminal(rs, task_key, job)` — `parse_filter_job` → `_parse_verdicts`
    → map local→global idx → SM `fold_filter_task` (accumulates `filter_verdicts`).
  - `finalize_filter(rs, cfg)` — per category `compute_filter_kept` + stitch the kept
    items into `entities`/`relations`/`events` (facts unfiltered). Applied when filter
    completes (SM → PERSIST).

Config (`EntityRecoveryConfig`/`PrecisionFilterConfig`) is serialized to/from rs as
plain dicts (`_recovery_cfg`/`_filter_cfg`) + reconstructed in the shell.

## Consumer (`llm_extract_consumer.py`)

- `_dispatch_next(llm_client, rs)` — after a fold advances the stage, loop submitting the
  next fan-out (RECOVERY then FILTER) under the row lock (fast fire-and-forget POSTs, like
  the entity→trio transition); return `(rs, inflight_ids)` on the first stage with work, or
  `(rs, None)` = persist when it reaches PERSIST (empty recovery/filter advance through).
- **TRIO completion** now calls `_dispatch_next` (was: straight to persist) → submit
  recovery/filter under the lock + `_persist_inflight`, or finalize outside the lock.
- **RECOVERY / FILTER branches** mirror TRIO: `SELECT … FOR UPDATE`, claim the stage,
  `fold_*_terminal`, (filter: `finalize_filter` on completion), `_dispatch_next`, persist
  inflight under the lock or finalize outside. Idempotent on dup terminal (the SM folds
  are no-ops once a batch is folded; the FOR UPDATE serialises multi-replica/sweeper races).

## Runner (`runner.py`)

- `_start_decoupled_chunk` — seed `has_recovery`/`has_filter` from the run snapshot (was
  hardcoded `False`) + `_recovery_cfg`/`_filter_cfg` dicts.
- Drop the `run_snapshot.precision_filter is None and run_snapshot.entity_recovery is None`
  gate in `process_job` so recovery/filter projects also take the decoupled branch.

## Tests

- Shell: `assemble_recovery` (batches + empty short-circuit), `fold_recovery_terminal`
  (promote + abstract-drop via finalize), `assemble_filter` (cat×batch keys), 
  `fold_filter_terminal` + `finalize_filter` (kept stitch, partial_policy).
- Consumer: trio-complete → recovery submit; recovery-complete → filter submit;
  filter-complete → persist; empty recovery advances to filter; FOR-UPDATE skip on
  superseded.
- Config serde round-trip through rs.

## Out of scope / notes

- `filter_status`/`filter_coverage` + the recovery/filter `on_decision` metric handlers
  are NOT wired on the decoupled path — but this is **exact parity**: worker-ai's sync
  `_extract_and_persist` calls `extract_pass2` WITHOUT `on_recovery_decision`/
  `on_filter_decision` and passes only the candidate LISTS (not `filter_status`) to
  `persist_pass2`. So nothing downstream consumes them on either path. Not a regression.
- Live-smoke = `D-WX-LIVE-SMOKE` extended to a recovery/filter-configured project
  (needs the stack + a project with `extraction_config`).
