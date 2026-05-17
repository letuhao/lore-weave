# Adversary Design Review — Phase B: ObstaclePlacer + Biomes (round 2)

**Verdict: REJECTED** — 1 BLOCK + 2 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator. AUDIT_LOG.jsonl round-2 event appended by the sub-agent.)

## Finding 1 — BLOCK — D5 erosion seal-check / AC-5 mismatch
- **Location:** spec D5, AC-5.
- **Problem (as reported):** D5's erosion gate uses `would_seal_a_gap(single-tile, zone_passable)` where `passable = Walkable ∪ Open`; the reviewer argued this refuses absorbing a loose `Open` appendage whenever doing so strands another `Open` tile → "erosion is a no-op", and D5's per-tile gate (over passable) and AC-5's result invariant (over the `Walkable` skeleton) are different properties.
- **Orchestrator assessment:** the "erosion is a no-op" trace is **incorrect** — erosion is iterative and absorbs a loose appendage **tip-first**: in the reviewer's `W|A|B` example B *is* border-adjacent (a grid-edge column), so B erodes first, then A erodes the next pass. The `passable` gate is **correct** and retained; the reviewer's suggested "gate on the `Walkable` skeleton" is **vacuous** (erosion never removes a `Walkable` tile, so such a gate would permit orphaning an `Open` courtyard). **The valid kernel:** AC-5 *was* asserting a trivial property (Walkable-skeleton connectivity, which erosion cannot affect).
- **Fix:** D5 clarified — the `passable` gate, why not the skeleton, and the explicit tip-first iterative peel. AC-5 corrected to the real invariant — the zone's passable region (`Walkable ∪ Open`) gains no connected components across erosion.

## Finding 2 — WARN — xor double-roll skews the Lake/Crater mix; AC-3 vacuous
- **Location:** spec D3, AC-3; TMP_005 §2.3/§4.1.
- **Problem:** §2.3 ships both `Lake xor Crater` and `Crater xor Lake`; §4.1's per-rule coin suppresses twice → `P(neither) = 0.25`. AC-3's "never both" is satisfied by selecting *neither*, so it cannot catch the skew.
- **Fix:** D3 — one decision per `{type, xor_with}` pair (draw once from `{this, other, neither}`, mirror rule reads the record). AC-3 — assert all three outcomes occur, never both, `neither` below 0.25.

## Finding 3 — WARN — retiring the golden leaves no inter-phase tripwire
- **Location:** spec D9, AC-9, §5; roadmap §7/§8.
- **Problem:** D9 (r1 revision) retired the golden entirely; `ac4_same_seed` is intra-run only, not the inter-phase regression tripwire the roadmap names.
- **Fix:** D9 — rebaseline, don't delete: `git mv` the golden to `tilemap_baseline.json`, regenerate content from the Phase-B engine, keep a `golden_baseline_byte_identical` test. A frozen committed artifact — trivially green within Phase B, a genuine gate for Phases C-E (which rebaseline deliberately).

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** D5 clarified (tip-first iterative peel; the `passable` gate is correct, the skeleton gate vacuous); AC-5 corrected to the passable-region invariant; D3 single-draw-per-xor-pair; AC-3 distribution assertion; D9/AC-9/§5 golden rebaselined to `tilemap_baseline.json` (not deleted). Re-review at round 3.
