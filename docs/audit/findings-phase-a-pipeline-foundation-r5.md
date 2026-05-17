# Adversary cold-start review — Phase A: Pipeline Foundation (round 5, final)

**Spec:** `docs/specs/2026-05-17-tilemap-phase-a-pipeline-foundation.md`
**Reviewer:** adversary (cold-start) · **Round:** 5 · **Date:** 2026-05-17
**Verdict: APPROVED_WITH_WARNINGS** — 3 WARN, 0 BLOCK. (Sub-agent file-write policy-blocked; persisted by the orchestrator. AUDIT_LOG.jsonl round-5 event appended by the sub-agent.)

The four prior rounds' BLOCKs are all genuinely resolved: D5's label-mapping connectivity with an explicit elimination clause, the `blocking_footprint_at` primitive, the `zone_passable − footprint_at` access search, D10's uncapped map-wide grid, the `access_path` pinned in §6.3 step 2c, and the AC-2(b) all-pairs oracle (verified equivalent to D5 in both directions). The design is sound and implementable.

## Finding 1 — WARN — AC-9 names a regression gate that cannot observe "before Phase A"
- **Location:** §4 AC-9 + §3 D7; existing `tests/determinism.rs`.
- **Problem:** AC-9 asserted output "byte-identical before vs after Phase A" but named `tests/determinism.rs`, which only asserts same-seed `a == b` within the *current* code — it never compares to the pre-Phase-A output. A deterministic `terrain_layer` regression from the `TerrainPainter` rewrite stays green.
- **Why it matters:** Lesson-1e524dee failure mode — a property AC gated by a test that cannot see one side. The roadmap's straight-through safety argument (§8) leans on this gate.
- **Suggested fix:** Commit a golden `TilemapView` snapshot from pre-Phase-A `HEAD` and assert byte-identical reproduction.

## Finding 2 — WARN — D6 path tie-break "lower flat-index wins" is undefined for a tile sequence
- **Location:** §3 D6; §4 AC-4; §6.3 step 2c.
- **Problem:** "Lower flat-index wins" is defined for goal selection and `adj` selection but not for choosing among ≥2 equal-cost *paths* — a path is a `Vec<TileCoord>`, not an index. The exact path on a cost tie is decided by `BinaryHeap` pop order, an implementation detail; AC-4's equal-length-path fixture would record incidental output (rubber-stamp).
- **Why it matters:** `search_path` feeds Phase D/E routing; an under-specified path tie-break makes every downstream "deterministic path" assertion inherit the gap.
- **Suggested fix:** Pin the Dijkstra tie-break precisely (frontier keyed `(cost, flat_index)`; predecessor set on first settle, never overwritten on an equal-cost tie).

## Finding 3 — WARN — `would_seal_a_gap` runs per-zone and cannot detect a cross-zone seal
- **Location:** §3 D5 + §6.3 step 2a; §6.2 `zone_passable`; TMP_001 §5.
- **Problem:** The seal-gap check uses one zone's `zone_passable`. The player-walkable graph is map-wide (TMP_001 §5 — Walkable tiles connect across zone borders); a per-zone check has a structural blind spot for a cross-zone seal.
- **Why it matters:** TMP_006 §4 calls a sealed gap "catastrophic UX failure." WARN not BLOCK because the spec mirrors TMP_006 §4.2's per-zone parameter — but "mirrors the source" ≠ "correct."
- **Suggested fix:** Document the per-zone limitation + the reasoning that ConnectionsPlacer's blocked borders (TMP_007 §3.1) keep footprints in-zone, or widen `passable` to map-wide for border-adjacent anchors.

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** all 3 WARN folded into the spec — AC-9 + D7 (committed golden-snapshot gate captured from pre-Phase-A engine, BUILD chunk 1); D6 (Dijkstra tie-break fully pinned — frontier keyed `(cost, flat_index)`, predecessor set on first settle); D5 (per-zone scope paragraph with the blocked-border reasoning + Deferred-to-Phase-D note). Design review closed APPROVED_WITH_WARNINGS after 5 rounds.
