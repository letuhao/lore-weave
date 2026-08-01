# DF07 — Actor Stat Block (was "PC Stats & Capabilities") — Index

> **Status:** **DRAFT 2026-07-26** — [`DF07_001_actor_stat_block.md`](DF07_001_actor_stat_block.md).
> Resolves **AUD-F6** ("PC stats absent — V1-blocking"; [`12_module_coverage_audit.md`](../../../12_module_coverage_audit.md))
> and the PCS_001 `pc_stats_v1_stub` deferral (PCS-Q4 / PCS-D4).
> **Scope change vs the 2026-04-23 placeholder:** the placeholder predates PROG_001, RES_001, PL_006 and
> COMB_001/002. Inventory, relationships and death outcomes have since been absorbed by RES_001 /
> ACT_001 / PCS_001 + WA_006. What remained unowned — and what DF7 now owns — is the **derived-stat
> layer**: the closed set of engine-consumed stat slots and the deterministic law that resolves author-declared
> PROG_001 progression + equipment + PL_006 status into them. See DF07_001 §1.

**Active:** (empty — no agent currently editing)

---

## Files

| File | Contents | Status |
|---|---|---|
| [`DF07_001_actor_stat_block.md`](DF07_001_actor_stat_block.md) | The law — stat-slot closed set · resolution order · RealityManifest extensions · consumer bindings (COMB / RES / PL_006 / PL_007 / AIT) · `stat.*` rejects · validators · AC | DRAFT 2026-07-26, **closure-corrected** |
| [`DF07_002_edge_cases_and_closure.md`](DF07_002_edge_cases_and_closure.md) | Adversarial pass against the 6 same-day consumers: 4 law defects (EC-1..EC-4) · 11 edge cases (EC-5..EC-15) · DF7-A12..A14 · DF7-Q12..Q14 · AC-DF7-16..21 | CLOSURE PASS 2026-07-26 |

## Exported stable IDs

`DF7-A1..A14` axioms · `DF7-Q1..Q14` locked decisions · `DF7-D1..D15` deferrals · `DF7-V1..V6` validators ·
`AC-DF7-1..21` acceptance criteria · `EC-1..EC-15` edge cases · `stat.*` reject namespace (10 V1 rule_ids) ·
`StatSlot` closed enum · `StatModifier` / `ModifierOp` / `ModifierSource` + the `EquipmentStats` trait
(PL_007 §6.3 implements it).

## Prior placeholder context (superseded, kept for traceability)

- **PC-C3** "simple state-based (no RPG mechanics)" / **F4** "minimal RPG mechanics" — reconciled in
  DF07_001 §10 DF7-Q2: the engine slot set is closed and small (10 slots); authors add *no* new mechanics,
  they only declare how their existing PROG_001 kinds project into slots. No D&D class/level system.
- **R8** PC-NPC relationship edge → owned by ACT_001 `actor_actor_opinion` (not DF7).
- **SR11** TurnState + PresenceState → owned by PL_001 / DF05_001 (not DF7).
- **MV12** fiction_ts snapshots → DF7 stat blocks are *derived*, so time-travel state needs no stat snapshot;
  replay recomputes from the inputs (DF7-A2).
- **DF5** designed 2026-04-27 (CANDIDATE-LOCK); **DF4** still CONCEPT — DF7 takes no dependency on DF4
  beyond the Lex clamp hook (DF07_001 §6.4).
