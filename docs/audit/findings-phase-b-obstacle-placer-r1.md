# Adversary Design Review — Phase B: ObstaclePlacer + Biomes (round 1)

**Verdict: REJECTED** — 2 BLOCK + 1 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator from the verbatim report. AUDIT_LOG.jsonl round-1 event appended by the sub-agent.)

## Finding 1 — BLOCK — D5 erosion: count-delta wording + batch-blocking can seal a zone
- **Location:** spec D5; AC-5; source TMP_005 §4.3.
- **Problem:** (a) D5 said block a tile when blocking "must not raise the connectivity-component count" — the exact count-delta oracle lesson 9ba274f5 calls wrong; Phase A's `would_seal_a_gap` is split-OR-eliminate label-mapping, not a count. D5 named `would_seal_a_gap` but described a contradictory algorithm. (b) Batch-collecting `to_block` then applying it: two tiles each individually safe can jointly sever a 2-wide corridor. AC-5 asserted the same wrong count-delta oracle.
- **Why it matters:** A false negative ships an unreachable region; a wrong impl + a wrong assertion = falsely green.
- **Suggested fix:** D5 → `would_seal_a_gap(single-tile mask, passable)` evaluated sequentially (each tile re-checked against the mask updated by earlier tiles in the pass); AC-5 → assert the result (post-erosion `Walkable` is one component).

## Finding 2 — BLOCK — D9/AC-9: regenerating the golden snapshot makes the determinism gate tautological
- **Location:** spec D9; AC-9; §5; contradicts `tests/determinism.rs`.
- **Problem:** D9 regenerated `phase_a_baseline.json` from the Phase-B engine; `determinism.rs` documents it as the *pre-change* baseline. Regenerating makes `ac9_golden_baseline_byte_identical` compare the Phase-B engine against a snapshot of itself — a tautology that can never fail, killing the inter-phase drift tripwire roadmap §8 depends on.
- **Why it matters:** The straight-through run's one automated cross-phase safeguard would be silently neutralised.
- **Suggested fix:** Do not regenerate-to-self. Retire the Phase-A golden (its job — verify Phase A's refactor — is done, recorded in commit 2f667516); rely on the phase-agnostic `ac4_same_seed_yields_byte_identical_tilemap`.

## Finding 3 — WARN — D4/D6: ObstaclePlacer bypasses ObjectManager and omits the TMP_003 §3.2 DEPENDENCY(ObjectManager)
- **Location:** spec D4 (`dependencies()`), D6 (fill); TMP_003 §3.2; Phase-A `object_manager.rs`.
- **Problem:** D4's dependency list omits `object_manager` (TMP_003 §3.2 lists it first); D6 hand-rolls placement instead of `place_and_connect_object`, duplicating the seal check and dropping the access-path invariant — without the spec stating this is deliberate.
- **Why it matters:** Two parallel placement paths is a divergence hazard for Phases C-E; the divergence should be a recorded decision.
- **Suggested fix:** State explicitly that obstacle fill is a deliberate distinct path (obstacles are walls — no access path, no scoring); note the §3.2 ObjectManager dependency is structurally satisfied (ObjectManager is a Phase-A service module, not a registered pass).

(Note: the reviewer confirmed `TilemapObjectKind::Obstacle` does NOT break an exhaustive `match` — no such match exists in the codebase.)

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** D5 rewritten (`would_seal_a_gap` single-tile guard, sequential not batch, no count-delta); AC-5 → result invariant; D9 + AC-9 + §5 — Phase-A golden retired (removed, not regenerated), determinism gate is `ac4_same_seed`; D4 + D6 — explicit distinct-path justification for obstacle fill + the structurally-satisfied ObjectManager dependency. Re-review at round 2.
