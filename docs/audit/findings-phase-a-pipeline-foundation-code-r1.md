# Adversary Code Review — tilemap-service Phase A: Pipeline Foundation (round 1)

**Verdict: REJECTED** — 1 BLOCK + 2 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator from the verbatim report. AUDIT_LOG.jsonl round-1 code-review event appended by the sub-agent.)

Cold-start 2-stage code review. The geometry primitives (`connected_components`, `would_seal_a_gap` label-mapping, Dijkstra `search_path`) and `from_zones` build-state init are correct on inspection — the 5 design-review rounds did their job. Every production diff is new-dormant code, a faithful TerrainPainter refactor, or test-only, so AC-9's no-output-change holds. The 3 defects are at the test-coverage / acceptance-criterion layer.

## Finding 1 — BLOCK — AC-6(b) "shortest access path + tie-break" is untested; the test claiming AC-6 is false-green for it
- **Location:** `services/tilemap-service/src/engine/object_manager.rs` — `places_an_object_marks_occupied_and_returns_an_access_path`; production code `find_access_path`. Spec §4 AC-6, §6.3 step 2(c), D6.
- **Problem:** AC-6 asserts `access_path` "(b) is the shortest among the footprint-adjacent access routes (ties → lower-flat-index start)." The test exercising the access path asserts only `!access_path.is_empty()` and `last().y == 0`. Since `free_paths` is the whole top row, *any* path reaching the top satisfies `y == 0` — a wrong `find_access_path` (longest route / highest-flat `adj` / no tie-break) passes unchanged. False-green for the AC-6(b) property.
- **Why it matters:** AC-6(b) is pinned "required for TMP-A4". The r3 design review BLOCKed on exactly this (`access_path` unpinned); the spec was revised to pin it, but Phase A ships no test that verifies the pinned choice — the r3 fix is unverified. `access_path` rides into Phase D/E road routing.
- **Suggested fix:** A deterministic fixture with ≥2 footprint-adjacent routes of unequal length (assert the shorter is returned) + a fixture with ≥2 equal-length routes from different-flat-index `adj` starts (assert the lower-flat-index start).

## Finding 2 — WARN — `place_and_connect_object` never tested with a mixed (blocking + non-blocking) footprint
- **Location:** `object_manager.rs` — every `place_and_connect_object` test uses an all-blocking template (`unit()`, `two_by_two`). Spec D9 / §6.3.
- **Problem:** D9 routes two masks to different consumers — `blocking_footprint_at` feeds the connectivity reject + commit→`Occupied`; full `footprint_at` feeds `fits`, the `find_access_path` subtraction, and `PlacementResult.footprint`. With an all-blocking template `footprint == blocking`, so the distinction collapses in every test — a mask-swap regression stays green.
- **Why it matters:** The blocking-vs-occupied split is the core of the "never seal a gap" invariant; a swap is a connectivity-correctness bug, and Phase A is the foundation B-E build on.
- **Suggested fix:** A `place_and_connect_object` test with a mixed template — assert the non-blocking footprint tile is not `Occupied` after commit while the blocking tile is, and `PlacementResult.footprint` carries both.

## Finding 3 — WARN — D10's map-wide nearest-object oracle is never tested across zone boundaries
- **Location:** `object_manager.rs` — all tests use the single-zone `build_state` helper. Spec D10.
- **Problem:** D10 rejects TMP_006 §5.1's per-zone grid for a map-wide one, justified by "a border tile can be nearest to an object in the neighbouring zone." That cross-zone behaviour has zero test coverage.
- **Why it matters:** D10 is a pinned correction of a source spec; the map-wide choice drives `Distance`/`BothDistanceAndCenter` scoring. An untested rationale is a latent regression surface for Phase C.
- **Suggested fix:** A two-zone build-state test: place an object in zone 0, assert a zone-1 tile reads a finite `nearest_object_distance` equal to its euclidean distance to the zone-0 anchor.

---
Captured rules: read pre-loaded — rule "vacuous OR-escape / false-green assertions" grounds Finding 1. Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** all 3 fixed by added tests in `object_manager.rs` (production code unchanged — verified correct on inspection): `find_access_path_picks_the_shortest_route_not_the_first_adjacent` + `find_access_path_breaks_equal_length_ties_by_lowest_flat_index_start` (F1, AC-6(b)); `mixed_footprint_marks_only_blocking_cells_occupied` (F2, D9); `nearest_object_distance_oracle_spans_zone_boundaries` (F3, D10). Re-review at code round 2.
