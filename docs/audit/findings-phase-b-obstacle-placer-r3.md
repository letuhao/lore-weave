# Adversary Design Review — Phase B: ObstaclePlacer + Biomes (round 3)

**Verdict: REJECTED** — 1 BLOCK + 2 WARN. (Sub-agent file-write policy-blocked; persisted by the orchestrator. AUDIT_LOG.jsonl round-3 event appended by the sub-agent. The reviewer confirmed r1/r2 BLOCKs resolved and did not re-litigate the passable-mask gate.)

## Finding 1 — BLOCK — D6's `would_seal_a_gap` gate is structurally dead; AC-6/AC-10 assert connectivity vacuously
- **Location:** spec D6, AC-6, AC-10.
- **Problem:** D6 places obstacle objects on `Obstacle`-state tiles; `TileState` is a partition so an `Obstacle` tile ∉ `passable` (`Walkable ∪ Open`). `would_seal_a_gap` subtracts a disjoint mask → no-op → always `false`. AC-6's "no placement seals a gap" is a test that cannot fail. AC-10's "`Walkable` one component" is also vacuous — no Phase-B pass touches a `Walkable` tile.
- **Why it matters:** Phase B's acceptance gate for the pipeline's headline "never seal a gap" invariant is a tautology.
- **Fix:** D6 — drop the dead `would_seal_a_gap` call; state obstacles occupy `Obstacle` tiles (connectivity-neutral by construction); the live connectivity step is D5 erosion. AC-6 — assert fill's real properties (footprint ⊆ `Obstacle` region, largest-first, `biome_object_type` set). AC-10 — reframe to the passable-region invariant; note the `Walkable`-skeleton check is load-bearing only from Phase C.

## Finding 2 — WARN — D3 single-draw distribution unpinned; contradicts AC-3
- **Location:** spec D3, AC-3.
- **Problem:** D3 "draw once from {this, other, neither}" — a uniform draw gives `P(neither)=1/3`, contradicting AC-3's "well below 0.25"; the distribution was never pinned.
- **Fix:** D3 — pin two 50/50 coins (`P(neither)=0.5`, `P(this)=P(other)=0.25`). AC-3 — assert the pinned model.

## Finding 3 — WARN — D5 erosion never fades from inter-zone borders
- **Location:** spec D5; TMP_005 §4.3.
- **Problem:** D5's wall = off-map OR `Obstacle`/`Occupied`; a neighbouring zone's tile is `Open`/`Walkable`, so erosion grows inward only from the grid edge — never the inter-zone boundary §4.3's "zone-boundary fade" promises.
- **Fix:** D5 — a neighbour counts as wall if it is not a member of this zone's `assigned_tiles` (off-map or another zone) or is `Obstacle`/`Occupied`.

---
Captured rules: read pre-loaded; Guardrails relevant: no — `check_guardrails` returned `pass:true`.

**Resolution (orchestrator, 2026-05-17):** D6 — `would_seal_a_gap` call dropped (dead code by construction; documented); AC-6 reframed to fill's real properties; AC-10 reframed to the passable-region invariant. D3 — two-coin model pinned (`P(neither)=0.5`); AC-3 matches. D5 — wall predicate extended to non-`assigned_tiles` neighbours (zone-boundary fade). Re-review at round 4.
