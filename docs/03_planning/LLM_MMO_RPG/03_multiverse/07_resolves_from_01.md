<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 07_resolves_from_01.md
byte_range: 45156-46497
sha256: c7b712d3ef72af94471762ebb5d18e1962f0b7d10ceb56091e1bed1389f97766
generated_by: scripts/chunk_doc.py
-->

## 10. What this resolves from 01_OPEN_PROBLEMS

| Problem | Status after multiverse model | Reason |
|---|---|---|
| **A2 Temporal consistency cross-player** | `PARTIAL` | Players in different realities having different NPC state is *correct* by construction. Players in the *same* reality still need per-PC memory discipline (A1), but cross-reality consistency is no longer a contradiction. |
| **C4 Author canon vs player-emergent narrative** | `PARTIAL` | Four-layer canon resolves the tension: L1/L2 is author canon; L3 is emergent; canonization is the explicit bridge. Narratives don't compete. |
| **F1 Locked beliefs vs flexible behaviors** | `PARTIAL` | L1 = locked (globally enforced). L2 = seeded default (drifts). L3/L4 = emergent. Author decides per-attribute at authoring time. |
| **R1 Event volume explosion** (from 02 risks) | `MITIGATED` | Per-reality event streams are bounded by reality's player cap + lifespan. Shared ancestor events are not duplicated — inherited by reference (fork_point cutoff). |
| **R8 Snapshot size drift** (from 02) | `PARTIAL` | Per-reality snapshots smaller than unbounded-world snapshots. NPC memory bounded by reality's player population. |

`PARTIAL` rather than `SOLVED` because the model gives a clean frame; implementation still must get memory, performance, and UX right.

