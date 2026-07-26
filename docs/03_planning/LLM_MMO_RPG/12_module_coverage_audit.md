# 12 — Module-Coverage Audit (design ↔ code)

> **Status:** COMPLETE (2026-07-26). A sweep of the **whole game-module taxonomy** against
> (a) the industry-standard MMO-RPG server module set and (b) **what actually exists in code**,
> rather than what exists in design.
> **Verdict:** design coverage is deep but **uneven and inverted** — the modules furthest from the
> play loop are the most finished; the modules a player touches in the first ninety seconds are
> absent. Separately, the **entire simulation tier has no design at all**, and the authority spine
> that every locked decision routes through (`commit-service`) **has no code**.
> **Why this doc exists:** `10_medium_blast_radius_audit.md` swept for *medium* assumptions. It did
> not ask "is every module that a shipping game needs actually designed?", nor "does the code match
> the design?" Both answers turn out to be no, and neither gap is visible from the feature indexes —
> a namespace with an `_index.md` and no feature doc reads as "present" in every directory listing.
> **Findings** `AUD-F5..F12` (continues the AUD namespace registered 2026-06-20).

---

## 1. Method

Two passes, both mechanical rather than impressionistic:

1. **Design pass** — extract the `Status:` line from all ~60 feature docs under `features/`;
   identify namespaces that hold only an `_index.md` (i.e. reserved-but-unwritten).
2. **Code pass** — enumerate `services/`, `crates/`, `contracts/`; grep for the domain nouns the
   design assumes (`combat_session`, entity/actor bodies, `commit-service`, `contracts/agent/`).

Compared against the canonical MMO-RPG server module taxonomy (engine · entity · spatial · combat ·
progression/economy · AI/NPC · social · meta), cross-checked against published architecture
practice (see §6).

---

## 2. Coverage matrix

🟢 CANDIDATE-LOCK · 🟡 DRAFT · 🟠 CONCEPT/RESERVED · 🔴 nothing · ⚙️ code exists

| Tier | Module | Design | Status |
|---|---|---|---|
| **Engine** | Transport / session | game-server WS edge (PRR-20) | 🟢 ⚙️ |
| | Persistence (events + snapshots) | dp-kernel | 🟢 ⚙️ |
| | **Simulation loop / tick** | — | **🔴** |
| | **Command authority (commit-service)** | DP-A6 (referenced by every tier) | **🔴 no code** |
| | Interest management / AOI | 08 RTM-A6..A8 | 🟢 |
| | Movement authority | 08 RTM-A1..A9 / D1..D10 | 🟢 |
| | Instancing / node handoff | RTM-A4, RTM-Q4 | 🟢 |
| **Entity** | Entity foundation | EF_001 | 🟢 |
| | Actor foundation | ACT_001 | 🟢 |
| | PC substrate | PCS_001 | 🟢 |
| | Identity ×5 | IDF_001–005 | 🟢 |
| | Status effects | PL_006 | 🟢 |
| | **PC stats** | DF07_pc_stats (*self-marked V1-blocking*) | **🔴 placeholder** |
| | **Items / equipment** | EF_001 defers to `PL_007_item.md` | **🔴 never written** |
| | Inventory | RES_001 `resource_inventory`; `inventory_cap` reserved | 🟡 partial |
| **Spatial** | Tilemap | TMP_001–009 | 🟢 ⚙️ |
| | World geometry | GEO_001/001b/002/003/004 | 🟡 |
| | Map · Place · Cell-scene | MAP_001 · PF_001 · CSC_001 | 🟢 |
| | Travel | TVL_001–005 | 🟡 |
| | Pathfinding | TMP_001, TG-D4 | 🟢 ⚙️ |
| **Combat** | Combat foundation | COMB_001 | 🟡 |
| | Tactical grid | COMB_002 | 🟡 |
| | **Threat / aggro** | — | **🔴** |
| | **Loot / drops** | — | **🔴** |
| **Progression** | Progression | PROG_001 | 🟢 |
| | Resource | RES_001 | 🟢 |
| | **Abilities / skills** | — | **🔴** |
| | **Economy / trade** | RES_001 defers to "V2 kinh tế module" | **🔴** |
| | Crafting | 14_crafting | 🟠 V2 |
| **AI / NPC** | Agent decision standard | 11 AGT-A1..A6 | 🟢 |
| | AI tier | AIT_001 | 🟢 |
| | NPC cast · chorus | NPC_001 · NPC_002 | 🟢 |
| | NPC desires | NPC_003 | 🟡 |
| | **Spawning / population** | — | **🔴** |
| | **Daily routine / schedules** | 12_daily_life | **🔴 empty** |
| **Social** | Session / group / chat | DF05_001 | 🟢 |
| | Faction · Family · Reputation · Titles | FAC_001 · FF_001 · REP_001 · TIT_001 | 🟢 |
| | Party | TVL_005 | 🟡 |
| | **SOC · NAR · EM · CC** | namespace only | **🔴 empty** |
| | Guild / organization | 15_organization | 🟠 V3 |
| | **PvP** | — | **🔴** |
| **Meta** | Lex · Heresy · Forge · Mortality | WA_001/002/002b/003/006 | 🟢 |
| | Charter · Succession | PLT_001 · PLT_002/002b | 🟢 |
| | Time dilation | TDIL_001 | 🟢 |
| | Play loop · grammar · interaction | PL_001/001b/002/005/005b/005c | 🟢 |
| | Onboarding | PO_001 | 🟢 |
| | World rules | DF04 (*self-marked V1-blocking*) | 🟠 CONCEPT |
| | Quests | 13_quests | 🟠 V2 |

**Totals:** ~60 design docs — ~38 CANDIDATE-LOCK, ~14 DRAFT, 3 RESERVED, 6 empty namespaces.

---

## 3. Findings

| ID | Subject | Severity | Detail / action |
|---|---|---|---|
| ~~**AUD-F5**~~ | ~~Item / equipment module absent~~ | ~~STRUCTURAL — V1-blocking~~ | ✅ **RESOLVED 2026-07-26** — `features/04_play_loop/PL_007_item.md` written (DRAFT), the file `EF_001 §Defers-to` had always named. Closes EF_001 §1 "Gap 1 — PL_005 nợ Item"; PL_005's Speak/Strike/Give/Examine/Use can now resolve their Item tool/target. |
| ~~**AUD-F6**~~ | ~~PC stats absent~~ | ~~STRUCTURAL — V1-blocking~~ | ✅ **RESOLVED 2026-07-26** — `features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md` (DRAFT, 468 lines) promoted from placeholder and **re-scoped** to the derived-stat projection layer between PROG_001's open author schema and the engine's closed slot set. **No new aggregate** (DF7-A2). Ships the closed `StatSlot` enum (10 V1), the `StatModifier` cross-feature contract, and takes `StatTerm` ownership over from PROG_001 §9.2. Registered via a `[boundaries-lock-claim+release]` cycle (`DF7-*` prefix, `stat.*` namespace). Unblocks COMB_001 leaving DRAFT. |
| **AUD-F7** | **No simulation-loop / tick module** | **STRUCTURAL** | The taxonomy has no owner for: what advances the world, at what cadence, in what order, and how a decision that takes seconds (LLM) coexists with movement that must resolve in milliseconds. 08 RTM defines movement *authority* but not the *loop*; COMB_001 defines *initiative within* an encounter but not the scheduler that hosts encounters. This is the single largest design hole. → **Design it (in progress; successor doc).** |
| **AUD-F8** | **`commit-service` has no code** | **IMPLEMENTATION GAP** | DP-A6 names it sole writer; RTM-A5 routes transitions through it; AGT-A6 makes every Decision a Proposal it authorizes. `services/` has no such directory. Every locked authority decision currently routes through a service that does not exist. → **Critical path for any V1 build.** |
| **AUD-F9** | **Combat loop has no ends** | **STRUCTURAL** | No **spawning/population** (nothing puts enemies in the world), no **threat/aggro** (COMB_002's TG-A4 stance-picker has no target-priority model to pick *whom* to close on), no **loot/drops** (combat resolves and produces nothing). TMP_006 treasure is world-placement, not encounter reward. → **Three small docs; all block a playable encounter.** |
| **AUD-F10** | **No abilities/skills module** | **STRUCTURAL** | COMB_001's action set includes `Skill` and COMB_002 references `skill.range`, but no doc defines what a skill *is*, how it's acquired, or its cost model. PROG_001 covers advancement, not the ability catalogue. |
| **AUD-F11** | **No economy/trade module** | GAP (V1-optional) | RES_001 §1 explicitly defers "complex resource economy + giao thương + kinh tế module" to V1+30d/V2. Acceptable as a V1 cut — recorded so it is a *decision*, not an oversight. |
| **AUD-F12** | **Four empty namespaces** | GAP (scope-dependent) | `07_social` (SOC), `08_narrative_canon` (NAR), `09_emergent` (EM), `11_cross_cutting` (CC), plus `12_daily_life` (DL) hold `_index.md` only. NAR + EM are load-bearing for the *stated vision* (emergent narrative) and their absence is not visible from any index. → **Decide explicitly: V1 scope or deferred.** |

---

## 4. The structural pattern

**Design depth is inversely correlated with proximity to the play loop.**

Identity, lineage, faction, reputation, titles, heresy, succession, time-dilation — all 🟢, several with
companion concept-notes *and* reference-game surveys. Items, stats, spawning, loot, aggro, abilities —
the objects a player touches within ninety seconds of logging in — are 🔴.

This is the predictable consequence of designing **top-down from a narrative vision**: the interesting
questions are at the top, and the substrate feels "obvious" until something needs to consume it. It is
cheap to correct — AUD-F5 and AUD-F6 are roughly two documents — but it is **not** cheap to leave
uncorrected, because COMB_001 and PL_005 are both at DRAFT *on top of* the missing substrate.

---

## 5. Design ↔ code divergence

The second inversion: **the code is deepest where the design is thinnest, and absent where the design is deepest.**

| | Design | Code |
|---|---|---|
| Data platform (events, snapshots, projections, outbox, PII, capacity) | thin | **very deep** — `crates/dp-kernel` (32 modules) |
| Tilemap / procedural generation | deep (10 docs) | **deep** — full `services/tilemap-service` engine |
| WS edge / session | moderate | **present** — `services/game-server` (859 LOC: auth, tickets, rate-limit, audit, `EchoRoom`) |
| Game simulation (entity bodies, combat, actors) | deep | **zero** — no `combat_session`, no entity/actor body anywhere |
| `commit-service` | deep | **zero** |
| `contracts/agent/` (AGT SDK) | registered in `_boundaries` | **not scaffolded** |

`services/game-server` is a hardened WebSocket edge with an echo room in it. There is no game inside
the game server.

**The generalizable read:** what exists is a **data platform**, not a game engine. Event sourcing +
snapshot tables is the *persistence tier* — built to an unusually high standard — with none of the tier
that is supposed to sit on top of it.

---

## 6. Industry cross-check

The module taxonomy and the persistence-tier read were checked against published practice:

- **[MMO Architecture: Source of Truth, Dataflows, I/O bottlenecks](https://prdeving.wordpress.com/2023/09/29/mmo-architecture-source-of-truth-dataflows-i-o-bottlenecks-and-how-to-solve-them/)** — the DB is a *persistence medium*, not the source of truth; live world state is in memory, persisted selectively (write-behind). Directly relevant to AUD-F7: an event-sourced store must be a **sink** of the simulation loop, never its hot path.
- **[What Game Engines Know About Data That Databases Forgot](https://nockawa.github.io/blog/what-game-engines-know-about-data/)** — per-component durability classes (transient / periodic-snapshot / fully-durable) instead of one uniform persistence model. Maps onto the three-layer position stack already locked in ILR-A2.
- **[Gambetta — Client-Server Game Architecture](https://www.gabrielgambetta.com/client-server-game-architecture.html)** + **[Client-Side Prediction and Server Reconciliation](https://www.gabrielgambetta.com/client-side-prediction-server-reconciliation.html)** — authority model + predict/reconcile. Independently matches RTM-A2/A3.
- **[Game Programming Patterns — Game Loop](https://gameprogrammingpatterns.com/game-loop.html)** — the loop owns update ordering; fixed timestep for determinism.
- **[Colyseus — Rooms](https://docs.colyseus.io/room)** / **[State Synchronization](https://docs.colyseus.io/state)** — room lifecycle + patch-rate model the game-server transport already assumes.

**Where the design already agrees with practice:** RTM-A3 (realtime layer never writes kernel state),
RTM-A2 (predict → validate → reconcile), AGT-A6 (Decision is a Proposal), ILR-A2 (three-layer position
stack). These were reached independently and should **not** be re-litigated — they are the correct
answers. The gap is that none of them is built.

---

## 7. Recommended order

Derived from the blocking relationships above, not from module size:

1. ~~**AUD-F7**~~ — ✅ simulation loop designed → [`13_simulation_loop.md`](13_simulation_loop.md) + [`14_sim_core_spec.md`](14_sim_core_spec.md)
2. ~~**AUD-F5 + AUD-F6**~~ — ✅ `PL_007_item` + `DF07_001_actor_stat_block` landed 2026-07-26
3. **AUD-F8** — `commit-service` *(critical path; nothing above the kernel can be built without it)* ← **now the top blocker**
4. **AUD-F9** — spawning · threat · loot *(close the encounter loop)*
5. **AUD-F10** — abilities/skills
6. **AUD-F12** — explicit V1 scope call on SOC / NAR / EM / CC / DL

AUD-F11 stands as an accepted V1 cut.

> **Audit status 2026-07-26:** 3 of 8 findings resolved (F5, F6, F7). The two **V1-blocking** ones are
> both closed. `sim-core` **S1 is unblocked**; `S2` is unblocked by F6/F5; `S3` still waits on **F8**.

---

## 8. Cross-references

- Medium audit (predecessor) — [`10_medium_blast_radius_audit.md`](10_medium_blast_radius_audit.md)
- Movement authority — [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md)
- Interaction / position stack — [`09_interaction_layer_reconciliation.md`](09_interaction_layer_reconciliation.md)
- Agent decision standard — [`11_agent_decision_standard.md`](11_agent_decision_standard.md)
- Entity contract + Item deferral — [`features/00_entity/EF_001_entity_foundation.md`](features/00_entity/EF_001_entity_foundation.md)
- Combat — [`features/18_combat/`](features/18_combat/)
- Decisions / IDs — [`decisions/locked_decisions.md`](decisions/locked_decisions.md) · [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md)
