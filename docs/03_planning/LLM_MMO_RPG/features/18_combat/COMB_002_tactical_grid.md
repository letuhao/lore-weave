# COMB_002 — Tactical-Grid Combat (design)

> **Status:** DRAFT — 2026-06-20. Detailed design for the **tactical-grid combat layer** introduced
> by decision **AUD-F1** ([`10_medium_blast_radius_audit.md`](../../10_medium_blast_radius_audit.md)),
> which reversed COMB_001's abstract/no-zone-graph V1 stance under the rendered 2D/2.5D medium.
> **This unblocks COMB_001 DRAFT promotion.** Builds on the COMB_001 locked combat model (action set,
> HSR action-value initiative, 4-step damage law-chain, 3-layer LLM-zero-math architecture, Q1–Q9) —
> **none of which this changes.** It adds the spatial layer those decisions deferred.
> **Decisions** `TG-D1..D8`; axioms `TG-A1..A4`. Pending `_boundaries/` lock for the COMB-owned
> `tactical_grid` aggregate before promotion.

---

## 1. The spine — engine owns *space*, the LLM owns *intent*

COMB_001 §139 deferred the grid for one reason: grid tactics is *"TOKEN-EXPENSIVE for LLM narration"*
(every unit × turn × cell). That cost only exists **if the LLM reasons over cells**. It does not have to.

> **TG-A1 — LLM-zero-space (extends the locked LLM-zero-math axiom).** The LLM **never** computes or
> emits grid coordinates. It selects **intent** — *which action, which target, and a bounded tactical
> positioning stance* — and the **engine owns 100% of spatial computation** (pathfinding, movement,
> range, line-of-sight, AoE). Token cost is **flat regardless of grid size**, which is exactly why the
> §139 objection dissolves under the rendered medium.

This is the load-bearing axiom; everything else slots under it.

---

## 2. The battlefield

> **TG-A2 — The combat grid is the instanced encounter's tile space** (RTM-Q4 dedicated scene). It is a
> **square** grid reusing the existing substrate, so combat needs no new geometry engine:
> - **Cell combats** → the **CSC_001 16×16** cell interior; fixtures become obstacles (Counter / Table /
>   Fireplace / Window block; Chair is passable). `TileState` (Walkable / Obstacle / Occupied) is reused.
> - **Wilderness combats** → a **deterministically generated 16×16 arena** (§7), terrain-flavored from the
>   parent TMP_001 tile (forest → trees, mountain → rocks as obstacles). Reuses TMP_001 pathfinding.

**Square vs hex:** HoMM3's battlefield is 15×11 **hex**. We use **square** to reuse CSC_001 / TMP_001
(both square) — adopting HoMM3's *design lessons* (speed→movement range, obstacles on the field,
melee-vs-ranged distinction) without a hex substrate. Default size **16×16** (CSC parity); configurable.

---

## 3. Action economy — separate move + action budgets (FFT / XCOM model)

> **TG-A3 — Each turn grants a movement budget AND one action, spendable in either order.** When an
> actor's turn comes up (HSR action-value pop — **initiative unchanged from COMB_001 Q7**), it may:
> - **Move** up to `move_range` tiles (one path, A*), and
> - take **one action** from the locked COMB_001 set (Strike / Defend / Skill / UseItem / Flee),
>
> in **either order** (move→act or act→move). This is the Final Fantasy Tactics / XCOM action economy.
> The old §11.2 Front/Back **2-row metaphor is retired** — positioning is now literal (§5).

- `move_range` = engine-computed from the actor's **speed** stat (configurable; default `base_move +
  ⌊speed / K⌋`, clamped). Fast units act *more often* (AV) **and** reach *farther* (move_range), as in
  HoMM3 — tunable if double-dipping speed proves too strong.
- "No Move verb V1" (COMB_001 §6) is **superseded**: movement is a turn *phase*, not a competing verb —
  the one-action-per-turn rule (Strike/Skill/…) is preserved exactly.

---

## 4. Movement

- **Pathfinding:** A* on the grid (TMP_001 already ships A*/Dijkstra). Orthogonal step cost 1, diagonal
  cost 1.5 (avoids the free-diagonal shortcut). Obstacles + Occupied tiles block; the path must be ≤
  `move_range` total cost.
- **Occupancy:** one actor per tile (V1; 2-tile units are V1+, mirroring HoMM3's 2-hex creatures).
- **Determinism:** A* tie-breaks by `(g, tile_index)` so identical inputs → identical path (TG-A4 / §8).

---

## 5. Range & line-of-sight

- **Distance metric:** Chebyshev (`max(|dx|, |dy|)`) for attack range — simple, readable on a square grid.
- **Melee:** range 1 (adjacent, incl. diagonals). Ranged / skills: `skill.range` tiles.
- **Line-of-sight:** corner-to-corner line check (the D&D/tactics method — clear if *any* attacker-corner
  → target-corner line misses all Obstacle tiles). Blocking obstacles = CSC fixtures (Counter / Table /
  Fireplace / Window) + arena terrain (trees / rocks / walls).
- **Cover (V1 = binary):** LoS is clear or blocked; melee needs adjacency, ranged needs range **and**
  clear LoS. **Soft cover** (partial obstruction → accuracy/damage penalty, XCOM-style) is **V1+**.
- **"Back-row safety" is now emergent** — a ranged unit behind obstacles is simply unreachable by melee
  and may be LoS-blocked from ranged. The §11.2 row modifier is no longer needed.

---

## 6. NPC positioning — bounded tactical intent (honoring "LLM picks destination")

> **TG-A4 — NPC positioning is LLM-chosen *intent*, engine-resolved *tile*.** A Major NPC's
> AIDecisionLayer (NPC_002 Chorus) outputs `{ action, target, stance }` where `stance` is a **bounded
> vocabulary**, not coordinates:
>
> | `stance` | Engine resolution (influence-map + pathfinding) |
> |---|---|
> | `CloseToMelee(target)` | path to nearest tile adjacent to target, within move_range |
> | `KiteAtRange(target)` | path to a tile that holds `skill.range` + clear LoS, maximizing distance |
> | `Flank(target)` | path to a tile opposite the target's nearest ally (V1+ may add facing bonus) |
> | `TakeCover` | path to a tile with the most LoS-blocking obstacles toward live enemies |
> | `Hold` / `Regroup` | stay / move toward allied centroid |
>
> The engine scores candidate tiles via an **influence map** (per the turn-based-AI literature) and
> A*-paths to the best, deterministically. The LLM gets positional agency (kite/flank/cover) at **flat
> token cost** — never reasoning over raw cells.

- **Minor NPC:** scripted proximity AI — move toward nearest enemy, attack if in range (the literature's
  baseline). **Untracked:** engine bulk-resolve, no movement nuance.
- **PC:** UI — the client shows reachable tiles (move_range) + valid targets (range + LoS); player clicks
  a destination and/or a target. (Camera/HUD for this is the client-build track, not this doc.)

> *Note on AUD-F1:* you chose "LLM picks destination" over engine-only pathfinding. TG-A4 honors that —
> NPCs choose **how** to position — via a bounded stance vocabulary rather than literal per-tile output,
> to keep the §139 token cost flat. If literal per-tile LLM movement is wanted instead, that's a one-line
> change to TG-A4 (and reopens the token-cost tradeoff).

---

## 7. Wilderness arena generator

For encounters not inside a cell, a **COMB-owned deterministic arena generator**:
- **Seed:** `blake3(reality_id, encounter_id)` → ChaCha8Rng (same pattern as CSC_001 / TMP_001).
- **Skeleton + scatter:** a small set of hand-authored 16×16 arena skeletons (open / chokepoint /
  scattered-cover) + seeded **obstacle scatter** whose *kind* is flavored by the parent TMP_001
  `TerrainKind` (Forest → trees, Mountain → rocks, Swamp → mire-as-difficult-terrain).
- **Connectivity invariant:** never fully wall off a combatant's start area (reuse TMP_001's "never seal a
  gap" connected-components check).
- Replay-deterministic: identical `(reality_id, encounter_id)` → byte-identical arena.

---

## 8. Determinism (preserves TDIL-A9 replay)

All spatial computation is engine-deterministic and seeded:
- Pathfinding tie-broken by tile index; LoS is a pure geometric function; influence-map tie-broken by a
  seeded key `(reality_id, turn_id, actor_id, action_idx, "position")` (same family as the locked combat
  RNG seed, COMB_001 Q8). Same inputs → identical movement, targeting, and arena. The 3-layer architecture
  is intact: engine resolves space + math; LLM picks intent (Layer 2) and narrates post-resolution
  (Layer 3, now including positions in its read-only context).

---

## 9. Decisions & prior-art

| # | Decision | Resolution |
|---|---|---|
| **TG-D1** | Grid topology | Square (reuse CSC_001/TMP_001); HoMM3 hex noted, not adopted (substrate is square). |
| **TG-D2** | Grid size | 16×16 default (CSC parity); configurable. |
| **TG-D3** | Action economy | Separate **move + action** budgets, either order (FFT/XCOM). HSR initiative unchanged. |
| **TG-D4** | Movement | A*, orthogonal 1 / diagonal 1.5, ≤ move_range; one actor/tile (2-tile units V1+). |
| **TG-D5** | Range / LoS | Chebyshev range; corner-line LoS vs Obstacle tiles; **binary** cover V1 (soft cover V1+). |
| **TG-D6** | NPC positioning | LLM picks **bounded stance** (TG-A4); engine resolves tile via influence-map + A*. Minor = proximity script. |
| **TG-D7** | Wilderness arena | Deterministic generator (skeleton + terrain-flavored obstacle scatter), seeded, 16×16. |
| **TG-D8** | LLM-zero-space | LLM never emits coordinates (TG-A1); engine owns all spatial math. |

**Prior art surveyed (2026-06-20):**
[HoMM3 combat — 15×11 hex, speed=movement, battlefield obstacles](https://heroes.thelazy.net/index.php/Combat) ·
[FFT — square grid, CT initiative, move+act each turn](https://turnbasedlovers.com/lists/17-games-like-final-fantasy-tactics/) ·
[Turn-based tactics (action economy, flanking, terrain)](https://grokipedia.com/page/Turn-based_tactics) ·
[Line of sight in video games (corner-line, shadowcasting)](https://en.wikipedia.org/wiki/Line_of_sight_(video_games)) ·
[Tactical grid LoS / cover deep-dive](https://vocal.media/education/creating-tactical-combat-systems-for-grid-based-rp-gs-a-deep-dive) ·
[Designing AI for turn-based strategy (influence maps, proximity)](https://www.gamedeveloper.com/design/designing-ai-algorithms-for-turn-based-strategy-games)

---

## 10. What this changes in COMB_001 (apply at DRAFT promotion)

- §6 "No Move verb V1" → **superseded** by TG-A3 (move is a turn phase).
- §11.1 "abstract arena (no zone graph)" + §11.3 "V2+ zone-graph tactics" → **V1 tactical grid** (this doc).
- §11.2 Front/Back 2-row damage modifier → **retired** (positioning is literal; range/LoS replaces it).
- PL_005 Strike/Skill payload gains engine-resolved positioning context (no new player-supplied field —
  consistent with the LLM-zero-math `damage_amount` removal).
- Unchanged: action set verbs, HSR action-value (Q7), 4-step damage law-chain, Q1–Q9, 3-layer architecture.

## 11. Deferred (V1+)

Retaliation/counter-attack (HoMM3 signature), elevation/height (FFT), soft cover, AoE shapes, 2-tile
units, facing/flanking bonuses, zone-of-control. All slot onto this grid additively when wanted.

## 12. Cross-references

- AUD-F1 + audit — [`10_medium_blast_radius_audit.md`](../../10_medium_blast_radius_audit.md)
- Combat foundation — [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) (action set, initiative, damage, layers)
- Instanced scene / handoff — [`08_realtime_movement_authority.md`](../../08_realtime_movement_authority.md) (RTM-Q4)
- Grid substrate — [`features/00_cell_scene/CSC_001_cell_scene_composition.md`](../00_cell_scene/CSC_001_cell_scene_composition.md), [`features/00_tilemap/TMP_001_tilemap_foundation.md`](../00_tilemap/TMP_001_tilemap_foundation.md)
- Decisions / IDs — [`decisions/locked_decisions.md`](../../decisions/locked_decisions.md) · [`00_foundation/06_id_catalog.md`](../../00_foundation/06_id_catalog.md)
