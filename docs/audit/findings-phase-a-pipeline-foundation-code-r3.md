# Adversary Code Review — tilemap-service Phase A: Pipeline Foundation (round 3, final)

**Verdict: APPROVED_WITH_WARNINGS** — 0 BLOCK + 3 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator from the verbatim report. AUDIT_LOG.jsonl round-3 code-review event appended by the sub-agent.)

Two prior code-review rounds found real BLOCKs, since addressed. Round 3 judged the current code on its own merits. The engine core is sound: `would_seal_a_gap`'s label-mapping is correct for multi-component `passable` (hand-traced against all AC-2(a) fixtures + the independent AC-2(b) all-pairs oracle); `search_path` Dijkstra determinism is fully pinned `(cost, flat)`; the AC-9 golden gate is **not** a tautology — file mtimes confirm the golden predates every Phase A implementation file (this corrects round 2's "post vs post" BLOCK, which was wrong on the temporal point). The 3 remaining issues are genuine weaknesses but none breaks correctness, determinism, a test, or a contract.

## WARN-1 — golden baseline file is git-untracked; AC-9's "committed" mandate not yet met
- **Location:** `tests/golden/phase_a_baseline.json` (untracked); consumed by `determinism.rs` `ac9_golden_baseline_byte_identical` via `include_str!`.
- **Problem:** `git status` reports `?? tests/golden/`. `include_str!` resolves at compile time — an uncommitted golden makes `determinism.rs` fail to compile on a clean clone / CI. A selective `git add` of named files at COMMIT can silently miss a brand-new directory.
- **Why it matters:** AC-9's before/after regression witness would be lost from the repo; `cargo test --workspace` would go red on a fresh checkout.
- **Suggested fix:** Explicitly `git add tests/golden/phase_a_baseline.json` at COMMIT; verify with `git ls-files` before the commit lands.

## WARN-2 — `place_and_connect_object` has an unguarded `search_area` / `grid` dimension precondition
- **Location:** `object_manager.rs` — `place_and_connect_object`, the `fits(...)` guard then `footprint_at(...).expect("fits ⇒ in-bounds")`.
- **Problem:** `fits` bounds-checks against `search_area`'s dimensions; `footprint_at` against `state.grid`. The `expect` is sound only when the two agree. A `search_area` larger than `state.grid` could make `fits` pass where `footprint_at` is `None` → panic. In-tree callers are safe (every `search_area` is built grid-sized by `zone_area_open`/`zone_passable`) → WARN.
- **Why it matters:** A latent panic on an undocumented precondition at the shared entry point Phases B–E will call.
- **Suggested fix:** `debug_assert_eq!` the dimensions + document the precondition.

## WARN-3 — spec D12's "`crate::Error` gains a `Placement` variant" is unimplemented; spec is self-inconsistent
- **Location:** `error.rs` (no Phase A variant added) vs `object_manager.rs` `PlacementError` (module-local enum) vs spec D12 prose vs spec §6.2/D9.
- **Problem:** D12 prose says extend `crate::Error`; §6.2/D9 give a concrete local `PlacementError` enum. The implementation followed §6.2/D9 (the better design) and silently dropped D12's prose.
- **Why it matters:** A Stage-1 spec-compliance gap; the divergence should be a recorded decision, not an unremarked drop.
- **Suggested fix:** Reconcile the spec — confirm the local `PlacementError` enum as the contract, strike D12's `crate::Error` language.

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):**
- **WARN-1** — actioned at COMMIT: `tests/golden/phase_a_baseline.json` will be explicitly `git add`-ed and verified tracked. (No code change.)
- **WARN-2** — `place_and_connect_object` gains a `debug_assert_eq!` on `search_area` vs grid dimensions + a documented precondition.
- **WARN-3** — spec D12 rewritten to confirm the module-local `PlacementError` enum (per §6.2/D9) as the contract; notes the `From<PlacementError>` bridge lands in Phase C.
Code review closed APPROVED_WITH_WARNINGS after 3 rounds.
