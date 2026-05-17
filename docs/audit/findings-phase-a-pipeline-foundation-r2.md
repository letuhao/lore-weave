# Adversary Findings — phase-a-pipeline-foundation — review-design round 2

**Verdict: REJECTED** — 3 BLOCK findings.

Adversary cold-start review, round 2, of `docs/specs/2026-05-17-tilemap-phase-a-pipeline-foundation.md`. The sub-agent could not write this file directly (file-write policy); reproduced here by the orchestrator from the sub-agent's verbatim report for audit completeness. The AUDIT_LOG.jsonl round-2 event was appended by the sub-agent.

## Finding 1 (BLOCK) — would_seal_a_gap silently allows total elimination of the walkable area
- **Location:** spec §3 D5; §4 AC-2; §6.2 `connected_components`/`would_seal_a_gap`. Source: TMP_006 §4 + §4.2.
- **Problem:** D5 defined the predicate as "true iff removing the footprint *raises* the component count." A footprint covering the entire walkable area yields before=1, after=0, and `0 > 1` is false → placement wrongly accepted. The formula detects splitting, never elimination. AC-2(b)'s differential oracle had the same blind spot — zero surviving free tiles ⇒ no BFS root ⇒ false.
- **Why it matters:** TMP_006 §4 calls this "the most important invariant in the whole pipeline"; a false negative is a catastrophic UX failure. Routine for a `Hub` zone's single strip or a small `Sea` stub. Every placer B–E routes through this check.
- **Suggested fix:** Return true when `blocked_after.is_empty()` while the region was non-empty, in addition to `count_after > count_before`. Fix AC-2(b)'s oracle for the no-survivor case.

## Finding 2 (BLOCK) — "blocking cells" contract has no primitive and contradicts mirrored TMP_006 §4.2
- **Location:** spec §3 D5 vs §6.3 step 2 vs §4 AC-2 vs §6.2. Source: TMP_006 §4.2.
- **Problem:** Three-way disagreement on the mask passed to `would_seal_a_gap` — D5 prose + TMP_006 §4.2 = whole footprint; §6.3 step 2 + AC-2 = blocking cells only; §6.2 signature took a plain `TileMask` and the only projection `footprint_at` emits all cells. No `blocking_footprint_at` existed.
- **Why it matters:** The two readings give different connectivity verdicts. Contract hole at the boundary consumed by ObstaclePlacer (B) and TreasurePlacer (C). Captured-lesson #2 (a spec that mirrors X must pin X's contract).
- **Suggested fix:** Add `TilemapObjectTemplate::blocking_footprint_at`; state in D5 + §6.2 that `would_seal_a_gap`'s first arg is the blocking-cell mask; extend AC-5; note the deliberate pinned divergence from TMP_006 §4.2.

## Finding 3 (BLOCK) — returned access_path is computed over a mask still containing the object's own tiles
- **Location:** spec §6.3 steps 2 & 4; §6.2 `place_and_connect_object`/`PlacementResult.access_path`; D9. Consumed by Phase E RoadPlacer.
- **Problem:** §6.3 step 2 path-searched over `zone_passable`; pre-placement the candidate footprint's tiles are still `Open` and thus in `zone_passable`, so the returned `access_path` could thread the footprint, which step 4 then sets `Occupied`.
- **Why it matters:** `access_path` is a contractual return; Phase E RoadPlacer routes roads along it → a road crossing the very object it connects to.
- **Suggested fix:** Subtract the candidate footprint from the pathfinding search space; assert `access_path` shares no tile with `footprint_at`.

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** all 3 BLOCK findings folded into the spec — D5, D9, AC-2, AC-5, AC-6, §6.2, §6.3. Plus an **author-found** correction surfaced while fixing D5: `would_seal_a_gap` must operate on the passable region `Walkable ∪ Open`, not Walkable-only `free_paths` — objects are placed on `Open` tiles (disjoint from the `Walkable` skeleton), so a Walkable-only check subtracts nothing and is inert. Re-review at round 3.
