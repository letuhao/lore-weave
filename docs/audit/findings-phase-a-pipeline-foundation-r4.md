# Adversarial Design Review — Phase A "Pipeline Foundation" (round 4)

**Spec:** `docs/specs/2026-05-17-tilemap-phase-a-pipeline-foundation.md`
**Reviewer:** adversary (cold-start) · **Round:** 4 · **Date:** 2026-05-17
**Verdict: REJECTED** — 1 BLOCK, 2 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator from the verbatim report. AUDIT_LOG.jsonl round-4 event appended by the sub-agent.)

## Finding 1 — BLOCK — AC-2(b)'s differential oracle is not equivalent to the `would_seal_a_gap` contract for multi-component inputs
- **Location:** §4 AC-2 part (b), against §3 D5 and §6.2.
- **Problem:** `would_seal_a_gap` (D5) returned `true` relative to the *before-count* (`cc(after) > cc(before)` OR elimination). AC-2(b)'s oracle returned `true` iff survivors empty OR `cc(blocked_after) ≥ 2` — no reference to the before-count. Counter-example: `passable` = two disjoint blobs, `blocking` = empty → implementation `false`, oracle `true`. AC-2(b) runs over random masks (overwhelmingly multi-component), so the test fails a spec-correct implementation.
- **Why it matters:** The differential test fails against a correct implementation, or — taken as the contract — mandates an incorrect one. `zone_passable` is routinely multi-component (Penrose `assigned_tiles` is not guaranteed 4-connected; objects carve the zone). Same defect class as the r1 tautology — a property test non-equivalent to the property.
- **Suggested fix:** Make the oracle before-count-aware, or restrict the generator to single-component inputs.
- **Orchestrator note (2026-05-17):** investigating the fix surfaced a deeper issue the finding did not state — D5's own `cc(after) > cc(before)` formula is wrong for multi-component `passable`: one footprint can split component A while entirely eliminating component B, leaving the count unchanged though A was split. D5 was rewritten to a **label-mapping** definition (a `passable`-component whose survivors span ≥2 `blocked_after`-components = a seal), and AC-2(b) to an independent **pairwise-reachability** oracle.

## Finding 2 — WARN — uncapped distance grid still corner-biases the first object in a zone
- **Location:** §3 D10 + §6.3 step 3, against TMP_006 §5.2.
- **Problem:** Before any object exists, `nearest_object_distance` is `INFINITY` everywhere. `OptimizeType::Distance` / `BothDistanceAndCenter` then score every candidate `INFINITY`, the tie-break collapses to lowest-flat-index = a corner. TMP_006 §5.2 makes `BothDistanceAndCenter` the treasure default ("scattered but not all on map edge") and §3.3 places high-tier-first → the first/highest pile of every tier lands in a corner.
- **Why it matters:** Latent quality flaw shipped in `place_and_connect_object`; D10 advertises a correctness property the deliverable lacks for the empty-grid case. Deterministic (TMP-A4 holds) → WARN, not BLOCK.
- **Suggested fix:** First-placement fallback to `Center` scoring; add an AC-6 case.

## Finding 3 — WARN — `search_path` determinism is verified by one same-input-twice fixture
- **Location:** §4 AC-4 + §5, against §3 D6's tie-break contract.
- **Problem:** D6 introduces a dual tie-break (nearest goal among equidistant goals; flat-index among equal-length paths). AC-4 verifies determinism with one input asserted against itself — "falsely green" per lesson 1e524dee; never exercises the tie-break across varied goal configurations.
- **Why it matters:** A goal-selection or path-reconstruction order divergence slips through AC-4 and surfaces as non-reproducible Phase E road geometry.
- **Suggested fix:** Add a tie-break property/parameterised test (≥2 equidistant goals; ≥2 equal-length paths).

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** D5 rewritten (label-mapping connectivity, correct for multi-component `passable`); AC-2 rewritten (multi-component fixtures + independent pairwise-reachability oracle); D10 + §6.3 step 3 + AC-6 (first-placement `Center` fallback); AC-4 (tie-break fixtures). Re-review at round 5.
