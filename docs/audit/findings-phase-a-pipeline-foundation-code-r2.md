# Adversary Code Review — tilemap-service Phase A: Pipeline Foundation (round 2)

**Verdict: REJECTED** — 1 BLOCK + 2 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator from the verbatim report. AUDIT_LOG.jsonl round-2 code-review event appended by the sub-agent.)

Round 1's three test-coverage gaps (AC-6(b) tie-break, mixed-footprint masks, D10 cross-zone oracle) are genuinely closed by four new tests. The findings below are fresh.

## Finding 1 — BLOCK — AC-9 golden snapshot provenance is unverifiable as committed
- **Location:** `tests/determinism.rs` — `ac9_golden_baseline_byte_identical` + `regenerate_golden_baseline`; `tests/golden/phase_a_baseline.json`.
- **Problem (as reported):** AC-9 / D7 require the golden captured from the *pre-Phase-A* engine. Git showed the golden file untracked (`git log --all` empty) and both the AC-9 test and its regenerator new in Phase A — the Adversary concluded the golden could only reflect the post-Phase-A engine, making the test post-vs-post.
- **Why it matters:** AC-9 is the load-bearing before/after regression gate for the straight-through run; a post-captured golden has the blind spot D7 names.
- **Suggested fix:** Regenerate the golden from a named pre-Phase-A commit; commit the file (it is untracked).

## Finding 2 — WARN — `place_and_connect_object` anchor tie-break ranks on a bare `f32` with no integer key
- **Location:** `object_manager.rs` — `place_and_connect_object` scoring loop; `Candidate`.
- **Problem:** Candidates ranked by an `f32` `score` with `score > b.score`; the lowest-flat-index tie-break is implied by `iter_set` order, not pinned by an explicit key (unlike `pathfind.rs`'s `Frontier`, which pairs `(cost, flat)`). The equal-distance multi-anchor case is untested.
- **Why it matters:** `pathfind.rs` pins its tie-break explicitly; `object_manager.rs` — the other deterministic-tie-break site — left it implicit.
- **Suggested fix:** Carry `flat` on `Candidate`, select by `(score, flat)` via `total_cmp`; add an equal-distance multi-anchor test.

## Finding 3 — WARN — `place_and_connect_object` panics on an out-of-range `zone_idx`
- **Location:** `object_manager.rs` — `place_and_connect_object` indexes `state.zones[zone_idx]`; root cause `build_state.rs` `zone_filtered`.
- **Problem:** An out-of-range `zone_idx` panics with a slice-index panic; the function's contract is `Result<_, PlacementError>` and D12 says Phase A returns typed errors.
- **Why it matters:** A panic in a pure deterministic engine gives the Phase B–E callers no recovery path; an unguarded module boundary.
- **Suggested fix:** Early bounds check → typed error (D12 sanctions adding the `PlacementError` variant).

---
Captured rules: read pre-loaded — Finding 1 = false-green-test class; Findings 2-3 = un-pinned determinism / module-boundary contract hole. Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):**
- **F1** — investigated: the golden *was* captured at BUILD chunk 1 before any engine change, so it is genuinely pre-Phase-A; the Adversary's "post-vs-post tautology" inference was based on git provenance that could not distinguish capture order. To make provenance **mechanically provable**, the golden was regenerated in a throwaway `git worktree` at the pre-Phase-A commit `38a11a12` — the result is **byte-identical** to the committed golden, confirming it. The file is `git add`-ed at COMMIT (it was untracked, a real omission the finding correctly flagged).
- **F2** — `Candidate` now carries `flat`; selection uses an explicit `(score desc, flat asc)` tie-break via `f32::total_cmp` (mirrors `pathfind.rs`'s `Frontier`). New test `equal_score_anchors_break_to_the_lowest_flat_index`.
- **F3** — `place_and_connect_object` now bounds-checks `zone_idx` and returns the new `PlacementError::NoSuchZone(usize)`. New test `out_of_range_zone_idx_is_a_typed_error`.
Re-review at code round 3.
