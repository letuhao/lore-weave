# Adversary Review — Phase A: Pipeline Foundation (round 3)

**Spec under review:** `docs/specs/2026-05-17-tilemap-phase-a-pipeline-foundation.md`
**Reviewer:** adversary (cold-start) · **Round:** 3 · **Date:** 2026-05-17
**Verdict: REJECTED** — 2 BLOCK + 1 WARN. (Sub-agent file-write was policy-blocked; persisted by the orchestrator from the sub-agent's verbatim report. AUDIT_LOG.jsonl round-3 event appended by the sub-agent.)

Rounds 1–2's six findings appear addressed (Dijkstra replaces A\*, `goals` mask, `blocking_footprint_at` API, footprint-subtracted access search, the `1→0` elimination clause + a sound differential oracle). Two distinct correctness flaws remain, both in the `ObjectManager` core.

## Finding 1 — BLOCK — `nearest_object_distance` is a 20-tile-capped grid but used as an unbounded oracle
- **Location:** spec §3 D10; §6.2 (`const INFLUENCE_RADIUS = 20.0`); §6.3 step 2(b) + step 3.
- **Problem:** D10 lowered only tiles within a 20-tile influence radius; tiles farther than 20 from every object permanently read `INFINITY`. §6.3 step 3 `OptimizeType::Distance` score *is* that value, so on a sparse region all far anchors tie at `INFINITY` and the flat-index tie-break picks the lowest-index anchor — not the farthest. §6.3 step 2(b) rejects when `nearest_object_distance < min_distance`; `min_distance` had no upper bound, so `min_distance > 20` makes a too-close placement (true distance 25, grid reads `INFINITY`) wrongly accepted.
- **Why it matters:** Bites the common Phase C case — high-value treasure tiers are sparse by design (TMP_006 §1); `Distance` scoring degenerates to "lowest flat-index anchor", contradicting TMP_006 §5.2 ("maximize distance from existing objects") and §5.1. AC-6's small-grid fixtures never exceed 20 tiles, so the defect ships green.
- **Suggested fix:** Either make the grid a true oracle (update all tiles each placement, drop the cap) or pin `min_distance ≤ INFLUENCE_RADIUS` and rank `Distance` with a metric the capped grid can support. State it; add an AC on a grid larger than the cap.

## Finding 2 — BLOCK — `PlacementResult.access_path` is never assigned / unpinned
- **Location:** spec §6.3 step 2(c) & step 4; §6.2 `PlacementResult`; AC-6.
- **Problem:** Step 2(c) computed `search_path` per footprint-adjacent `adj` only as a reject filter (anchor survives if ≥1 `adj` reaches `free_paths`). Step 4 said only "Return `PlacementResult`" — never stating which `adj`'s path becomes `access_path`, no tie-break, not stated to be shortest.
- **Why it matters:** Two correct implementations emit different `access_path` → different Phase E road segments → breaks TMP-A4 byte-identity. AC-9 cannot catch it (`access_path` is first exercised in Phase C, after the hole is frozen into the foundation). Recurring "contract hole at a boundary" pattern (captured lessons 2c94cf3c, 4b229319).
- **Suggested fix:** Pin the selection rule in §6.3 (e.g. shortest path over all surviving `adj`, ties broken by lower-flat-index `adj`); add it to AC-6.

## Finding 3 — WARN — `choose_guard`'s `None` is incoherent with its terrain-keyed table
- **Location:** spec §3 D11; §6.2 `choose_guard`; AC-7.
- **Problem:** D11 specified a `TerrainKind → guard-flavor` table and asserted "`None` is valid (unguarded for low-value piles)". A table keyed solely on `TerrainKind` is either total (always `Some`) or has gaps (`None` only for an unmapped terrain). TMP_006 §5.3 defines `None` as strength-driven ("no creature at this strength"); the low-value-pile gate is `needs_guard`/`min_guard_value` (Phase C), outside `choose_guard`. AC-7's `None` clause is untestable against a total table.
- **Why it matters:** Not a Phase-A correctness blocker, but an unpinned contract Phase C inherits. Captured lesson 4b229319 ("mirrors X — pin X's contract").
- **Suggested fix:** Make the table total over all 10 `TerrainKind` and make `choose_guard` infallible (drop the `Option`), or define a concrete `None` trigger consistent with §5.3. Align AC-7.

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** all 3 folded into the spec — D10 (uncapped map-wide oracle, `INFLUENCE_RADIUS` removed), D11 + AC-7 (`choose_guard` infallible, total table), §6.3 step 2(c)+4 + AC-6 (`access_path` pinned: shortest, tie-break lower-flat-index start). Re-review at round 4.
