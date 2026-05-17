# Adversary Findings — Phase A: Pipeline Foundation (round 1)

**Task:** `phase-a-pipeline-foundation` · **Phase:** review-design · **Round:** 1
**Reviewer:** adversary (cold-start) · **Spec under review:** `docs/specs/2026-05-17-tilemap-phase-a-pipeline-foundation.md`

## Verdict: REJECTED

Three BLOCK findings. Any BLOCK forces REJECTED. All three compound into Phases B-E,
exactly the failure mode the roadmap section 9 flags as the top Phase-A risk.

---

### Finding 1 - BLOCK - AC-2's connectivity property test is a tautology; the "most important invariant" is effectively single-fixture

**Location:** spec section 4 AC-2 ("a footprint placement never *lowers* the count") and section 3 D5 / section 6.2 `connected_components` + `would_seal_a_gap`.

**Problem.** `would_seal_a_gap` per D5/TMP_006 section 4.2 is `connected_components(free_paths.subtract(footprint)) > connected_components(free_paths)`. AC-2 backs this with one fixture (the TMP_006 section 4.1 corridor split) **plus** the property test *"a footprint placement never lowers the count."* That property is a mathematical tautology: removing tiles from an undirected graph can only keep the component count equal or raise it - it can never lower it. The assertion therefore holds for **every possible implementation** of `would_seal_a_gap`: one that always returns `false`, one that always returns `true`, or one with the `>` comparison inverted to `<`. The property test exercises nothing about the function under test.

**Why it matters.** TMP_006 section 4 calls this "the most important invariant in the whole pipeline" and the roadmap (section 9 risk row 1, section 7) explicitly mandates *property-style tests* on `would_seal_a_gap` precisely because "a bug there compounds into B-E silently." With AC-2 as written, the invariant is validated by a single corridor-split fixture and a no-op property - directly the captured-rule-1 failure ("a single-seed/single-input test for a universal property is falsely green"). An off-by-one in the component comparison, a flood-fill that mis-handles the footprint's own non-`free_paths` cells, or a wrong handedness of the inequality would all ship green and silently seal gaps in every B/C/D/E placement.

**Suggested fix.** Replace AC-2's tautological property with a *generative* one that can fail: over many random `(free_paths, footprint)` pairs, assert `would_seal_a_gap` agrees with an independent reference (recompute `connected_components` before and after the subtraction by a second code path, or assert against a brute-force BFS reachability check on the resulting mask). Add positive cases (footprint that *does* split a region across multiple seeds/topologies) and negative cases (footprint that removes a dead-end stub - count unchanged). The property must be one a buggy implementation fails.

---

### Finding 2 - BLOCK - `search_path` (D6) does not pin the A* heuristic-admissibility precondition and diverges from TMP_007 section 5's multi-source signature

**Location:** spec section 3 D6, section 6.2 `search_path` signature, section 6.3 step 2; against TMP_007 section 5 and TMP_003 section 3.4.

**Problem (two coupled holes at the same boundary).**
1. **Admissibility unpinned.** D6 specifies "A* with a Manhattan-distance heuristic" and a caller-supplied `cost: impl Fn(TileCoord, TileCoord) -> f32`. A* returns a *shortest* path only when its heuristic is admissible - never exceeds the true remaining cost. A raw Manhattan heuristic is admissible only when every per-step `cost_fn` value is at least 1. The spec places **no lower bound on `cost_fn`'s return value**; section 6.2's own comment says RoadPlacer passes "terrain cost" and TMP_007 section 5 describes a "curved cost function" weighting tiles by border distance - both naturally produce fractional/relative weights below 1. If any edge cost can drop below the heuristic's per-step unit, A* expands nodes out of order and returns a **non-optimal or wrong path with no error** - a determinism-adjacent correctness defect inherited by Phase D (connection routing) and Phase E (roads/MST).
2. **Signature divergence from the mirrored spec.** TMP_007 section 5's contract is `search_path(area, target, cost_fn)` - **no `start`** - because connection routing searches from `target` outward to the zone's *entire* `free_paths` set (multi-source). D6 adds a single `start: TileCoord`. D6's own section 6.3 step 2 needs the multi-source form ("a footprint-adjacent passable tile has a `search_path` *from the zone's `free_paths`*" - `free_paths` is a `TileMask`, not a point). A single-`start` signature forces every caller to loop `search_path` over each free-path tile - cost order |free_paths| times an A* search per candidate anchor - a perf cliff and an API redesign in Phase D.

**Why it matters.** This is captured-rule-2 in its sharpest form: the spec says "A* over a tile mask (TMP_007 section 5)" but does not pin the contract details an implementer needs - the cost-function lower bound, the heuristic scaling, and the multi-source search surface. Both holes are cheap to fix now and costly to retrofit once B-E build on the wrong signature.

**Suggested fix.** (a) State the admissibility precondition explicitly: either require `cost_fn >= 1.0` for every edge (document it, debug-assert it), or scale the Manhattan heuristic by the minimum edge cost, or - per TMP_007 section 5's own "A* **or Dijkstra**" - drop the heuristic and specify Dijkstra (uniform-cost), which is admissible for any non-negative `cost_fn`. (b) Adopt the TMP_007 section 5 multi-source shape: accept a set of sources (`&TileMask` or `&[TileCoord]`) so connection/footprint-access routing is one search, not a loop.

---

### Finding 3 - BLOCK - D2/section 6.4 build-state init marks `Sea`-zone water tiles `Open`, handing Phase B/C placers open water as object-placement candidate area

**Location:** spec section 3 D2, section 4 AC-1, section 6.4 `from_zones`; helpers `zone_area_open` / `zone_passable` in section 6.2.

**Problem.** The D2/section 6.4 init rule is: `free_paths` tile -> `Walkable`; else `Forbidden`-zone tile -> `Obstacle`; else -> `Open`. `Sea` zones are not `Forbidden`, so every non-`free_paths` tile of a `Sea` zone is initialized `Open`. AC-1 enshrines this verbatim: "`Forbidden`-zone non-free tiles -> `Obstacle`; all other assigned tiles -> `Open`." Per TMP_001 section 5, `Open` means "passable; **can host objects**; Modificator candidate area." Phase A's published helper `zone_area_open` (= assigned intersect Open) is exactly what TMP_006 section 3.4 feeds TreasurePlacer as `search_area`, and TMP_005 section 4 feeds ObstaclePlacer. So in Phase B/C a `Sea` zone's open water becomes valid candidate area for treasure piles and obstacle fill.

**Why it matters.** The modificators that would re-classify water - `WaterAdopter` / `WaterProxy` (TMP_003 section 2.3) - are explicitly V2/cut in the roadmap (section 2 out-of-scope). Nothing else in Phase A distinguishes water from land `TileState`. The build-state init and its `zone_area_open` / `zone_passable` helpers are Phase A's *foundation contract*; B and C inherit it. Leaving Sea tiles `Open` either ships treasures/obstacles in open water or forces every later placer to special-case `ZoneRole::Sea` at the call site - a workaround layered over a wrong foundation, and exactly the "Phase-A foundation bug compounds into B-E" risk the roadmap section 9 calls out. `connected_components` / `would_seal_a_gap` run over masks that would also count water `Open` tiles as walkable-adjacent area.

**Suggested fix.** Decide `Sea`-zone tile init in Phase A explicitly rather than letting it fall through to `Open`. Options: initialize non-`free_paths` `Sea` tiles to `Obstacle` (water is impassable to land placement - symmetric with the `Forbidden` argument D2 already makes), or add a dedicated build-internal water marking. Whichever is chosen, pin it in D2 and AC-1 so `zone_area_open` never returns water tiles to a land placer, and state how `Sea` zones interact with the connectivity check.

---

Captured rules: read pre-loaded; Guardrails relevant: no - Phase A does no push / DB migration / destructive op (check_guardrails returned pass: true, 6 rules, none matched).
