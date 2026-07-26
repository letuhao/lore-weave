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
> **Findings** `AUD-F5..F14` (continues the AUD namespace registered 2026-06-20). `F13` (V1 world
> liveness) and `F14` (ruleset loader / registry) were added 2026-07-26, after the original sweep.

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
| | Command authority (commit-service) | **15** CS-A1..A5 / CS-D1..D7 *(DP-A6 was mis-cited here — it names "the Rust game layer", not a commit-service)* | 🟡 DRAFT 2026-07-26 · **no code** |
| | Interest management / AOI | 08 RTM-A6..A8 | 🟢 |
| | Movement authority | 08 RTM-A1..A9 / D1..D10 | 🟢 |
| | Instancing / node handoff | RTM-A4, RTM-Q4 | 🟢 |
| **Entity** | Entity foundation | EF_001 | 🟢 |
| | Actor foundation | ACT_001 | 🟢 |
| | PC substrate | PCS_001 | 🟢 |
| | Identity ×5 | IDF_001–005 | 🟢 |
| | Status effects | PL_006 | 🟢 |
| | **PC stats** | DF07_pc_stats (*self-marked V1-blocking*) | **🔴 placeholder** |
| | Items / equipment | **PL_007** (the file EF_001 §Defers-to named) | 🟡 DRAFT 2026-07-26 |
| | Inventory | **PL_007b** — `actor_inventory_view` union over RES_001 balances + EF_001 `HeldBy`; `inventory_cap` accounting defined | 🟡 DRAFT 2026-07-26 |
| **Spatial** | Tilemap | TMP_001–009 | 🟢 ⚙️ |
| | World geometry | GEO_001/001b/002/003/004 | 🟡 |
| | Map · Place · Cell-scene | MAP_001 · PF_001 · CSC_001 | 🟢 |
| | Travel | TVL_001–005 | 🟡 |
| | Pathfinding | TMP_001, TG-D4 | 🟢 ⚙️ |
| **Combat** | Combat foundation | COMB_001 | 🟢 |
| | Tactical grid | COMB_002 | 🟢 |
| | Threat / aggro | COMB_003 | 🟡 |
| | Loot / drops | COMB_004 | 🟡 |
| | Spawning / encounter formation | COMB_005 | 🟡 |
| **Progression** | Progression | PROG_001 | 🟢 |
| | Resource | RES_001 | 🟢 |
| | Abilities / skills | ABL_001 | 🟡 |
| | **Economy / trade** | RES_001 defers to "V2 kinh tế module" | **🔴** |
| | Crafting | 14_crafting | 🟠 V2 |
| **AI / NPC** | Agent decision standard | 11 AGT-A1..A6 | 🟢 |
| | AI tier | AIT_001 | 🟢 |
| | NPC cast · chorus | NPC_001 · NPC_002 | 🟢 |
| | NPC desires | NPC_003 | 🟡 |
| | Spawning / population | AIT_001 (ambient, pre-existing) + COMB_005 (hostile) | 🟡 |
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
| ~~**AUD-F5**~~ | ~~Item / equipment module absent~~ | ~~STRUCTURAL — V1-blocking~~ | ✅ **RESOLVED 2026-07-26** — `features/04_play_loop/PL_007_item.md` written (DRAFT), the file `EF_001 §Defers-to` had always named. Closes EF_001 §1 "Gap 1 — PL_005 nợ Item"; PL_005's Speak/Strike/Give/Examine/Use can now resolve their Item tool/target. **The "Inventory 🟡 partial" row closes with it** via `PL_007b_inventory.md`: the two half-schemas that pointed at each other (RES_001's reserved `ResourceKind::Item` vs EF_001 AC-EF-10's "inventory *is* a `HeldBy` read-view") are resolved by ITM-A2 picking the entity representation and **withdrawing** `ResourceKind::Item` (RES-D1), with a bootstrap validator making the choice enforceable. Two latent breaks were found only because all three docs finally exist at once: the `ItemId`/`ItemInstanceId` spelling drift (ITM-C1) and `InstrumentMatch::Specific(ResourceKind)` becoming unable to name a wielded weapon (ITM-C7, which also resolves PROG-D15). |
| ~~**AUD-F6**~~ | ~~PC stats absent~~ | ~~STRUCTURAL — V1-blocking~~ | ✅ **RESOLVED 2026-07-26** — `features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md` (DRAFT, 468 lines) promoted from placeholder and **re-scoped** to the derived-stat projection layer between PROG_001's open author schema and the engine's closed slot set. **No new aggregate** (DF7-A2). Ships the closed `StatSlot` enum (10 V1), the `StatModifier` cross-feature contract, and takes `StatTerm` ownership over from PROG_001 §9.2. Registered via a `[boundaries-lock-claim+release]` cycle (`DF7-*` prefix, `stat.*` namespace). Unblocks COMB_001 leaving DRAFT. |
| **AUD-F7** | **No simulation-loop / tick module** | **STRUCTURAL** | The taxonomy has no owner for: what advances the world, at what cadence, in what order, and how a decision that takes seconds (LLM) coexists with movement that must resolve in milliseconds. 08 RTM defines movement *authority* but not the *loop*; COMB_001 defines *initiative within* an encounter but not the scheduler that hosts encounters. This is the single largest design hole. → **Design it (in progress; successor doc).** |
| **AUD-F8** | **`commit-service` has no design *and* no code** | **DESIGN + IMPLEMENTATION GAP** *(re-classified 2026-07-26)* | ⚠️ **This row originally said "IMPLEMENTATION GAP", implying the design was done. It was not.** `commit-service` had **no design doc and no ownership-matrix row** (grep: zero matches) — only a name used across 16 files as though the service existed. Worse, the row cited **DP-A6 as its design**, but DP-A6 is *"Python is event-producer-only"* and names the authoritative writer as **"the Rust game layer"** — it never mentions a commit-service. → **Design pass done 2026-07-26:** [`15_commit_service.md`](15_commit_service.md). **Finding: the semantics were never missing** (EVT-A5/A7, EVT-V1..V7, EVT-L1..L6, EVT-P\*, DP-A15/A16/A17, DP-R7 fully specify the behaviour); only the *service shape* was. Now specified: co-located role on the DP-A16 writer node (`CS-A1`), wrapping `sim-core` on both sides — admission validation before, durability after (`CS-A2`). **Remaining: `CS-Q1` host shape, then implementation.** |
| ~~**AUD-F9**~~ | ~~Combat loop has no ends~~ | ~~STRUCTURAL~~ | ✅ **RESOLVED 2026-07-26** — three docs, as predicted, all in `features/18_combat/`. **`COMB_005_encounter_spawning.md`** (spawning): the key finding is that AIT_001 *already owned* population (`cell_untracked_density`, `Generated:UntrackedNpcSpawn`, tier caps) — what was missing was *hostility, engagement and respawn*, so COMB_005 layers on it (SPN-A1) rather than adding a second population owner. Respawn is **epoch arithmetic**, not timers (`floor(fiction_day / period)`), which makes it replay-exact and time-dilation-safe with no stored roster. It also finally builds the **NewbieZone validator COMB_001 §9 item 8 declared and never wrote** (SPN-V4) — at *schema* stage, so a boss in a newbie zone makes the reality unloadable rather than being clamped at runtime. **`COMB_003_threat_and_targeting.md`** (threat): deterministic, seedless integer accrual + **switch-margin hysteresis** (without which near-tied threats flicker every round and read as broken AI), a closed `TargetSelector` enum replacing the concept notes' bare `"lowest_hp_hostile"` string, and a **top-K vague-labelled candidate list** that gives an LlmDriver real target agency at flat token cost — the third LLM-containment axis after zero-math and zero-space. **`COMB_004_loot_and_spoils.md`** (loot): independent per-entry seeded rolls (a single weighted pick silently re-rates every existing entry when one is added), and the load-bearing rule that loot generates **at defeat finalisation, never at KO** — because COMB_001 Q3 KO is revivable for 5 rounds, so rolling at HP=0 would let a party loot a body and then revive it. It also carries the **progression award**, without which a reality with no loot tables still gains nothing from fighting. Built on the seam PL_007 §8.5 explicitly handed over. **Net new aggregates: zero.** |
| ~~**AUD-F10**~~ | ~~No abilities/skills module~~ | ~~STRUCTURAL~~ | ✅ **RESOLVED 2026-07-26** — `features/19_ability/ABL_001_ability_foundation.md` (DRAFT), a new namespace rather than a COMB doc because PL_005 `Use` and PL_007 `grants_ability` call it too. **The finding underneath the finding:** the concept notes' *"V1 skills come from PROG_001 skill kinds"* is a **category error**, not a shortcut — a PROG kind is a number that grows (`swordsmanship: 8`), a combat `Skill` is an effect you fire, and taking the sentence literally left `skill_id` with no declaring type and `combat.skill_unknown` with nothing to check (ABL-A1). Ships a closed 9-variant `EffectOp` dispatch vocabulary (every variant routing into an already-owned aggregate) and **`PowerTerm`** — the mechanism by which an offensive ability changes damage *without emitting a number*, substituting into COMB_001 §4 step 1 so the 4-step chain stays the sole damage authority (ABL-A3). Known-ability set is **derived**, not stored (ABL-A4, mirroring DF7-A2); cooldowns are `combat_session` fields. **One open cross-track item:** ABL-Q9 proposes merging PL_007's `UseEffectDecl` into `EffectOp` — *proposed, not applied*, pending that doc's owner. |
| **AUD-F11** | **No economy/trade module** | GAP — ⚠️ **PARTIALLY REOPENED 2026-07-26 by AUD-F13** | RES_001 §1 defers "complex resource economy + giao thương + kinh tế module" to V1+30d/V2, and that was accepted as a V1 cut. **AUD-F13's full-DL decision pulls *ambient* economy into V1** (NPCs producing and consuming via `sim-rtsim`), which touches the same RES_001 surface. The two are separable and the boundary must now be stated explicitly: **ambient economy simulation** (NPC-driven, background, Class C — **in V1** via DL) vs **player-facing trade** (vendors, prices, giao thương UI — **still deferred**). Without that line drawn, DL design will drift into the deferred module. |
| ~~**AUD-F12**~~ | ~~Five empty namespaces~~ | ⚠️ **LARGELY WITHDRAWN 2026-07-26 — the finding was wrong on its central claim.** It asserted *"NAR + EM are load-bearing for the stated vision (emergent narrative)"*. **EM is not about emergent narrative**: its index reads *"reality fork, world travel (DF6 **deferred V3+**), reality closure UX, severance (DF14)"* — multi-reality lifecycle, explicitly V3+. The finding inferred each namespace's content from its **name** instead of reading its `_index.md`, which is exactly the failure mode this audit was written to catch. Reading them: **SOC** is *deliberately hollowed* (*"SOC-6 parties and SOC-7 global chat are explicitly out-of-scope — sessions replace both"* — DF05 absorbed it); **NAR**'s mechanism is *locked in S13* (DF3 pre-spec) with only the L3→L2 promotion **UX** open; **CC** is client/ops cross-cutting with a11y *already MITIGATED* via A11Y_POLICY; **DL** self-declares *"DF1 umbrella (V2), V1 scope probably minimal"*. **All five are empty by design, with recorded reasons — not by oversight.** Residue → **AUD-F13**. |
| **AUD-F13** | **How alive is the V1 world?** *(residue of AUD-F12)* | ✅ **RESOLVED 2026-07-26 (PO): FULL DAILY LIFE IN V1.** The whole DL/DF1 umbrella — scheduled NPC routines, ambient world activity, resource replenishment, ambient economy, PC→NPC conversion — ships in V1, and **Class C (`sim-rtsim`) ships complete**. This **promotes DL from V2 to V1**, against its own `_index.md` (*"umbrella for DF1 big feature (V2). V1 scope probably minimal"*), so that index needs a dated re-scope note. **Consequences: (1)** the DL feature tier is currently an **empty namespace** — it must be designed before S6 can be built; **(2)** stage **S6 grows from a thin seam to the full `sim-rtsim` rule set**; **(3)** it **partially reopens AUD-F11** — see that row. *Original text: DL self-declares "V1 scope probably minimal", and "probably" is the unresolved word. It decides whether Class C ships in V1 at all; AIT_001 + ILR-A3 already cover ambient placement, so the question was whether V1 needs scheduled routines on top.* | DL self-declares *"V1 scope **probably** minimal"*, and "probably" is the unresolved word. It decides whether **Class C (`sim-rtsim`) ships in V1 at all**: with no ambient routines there is almost nothing for the background tier to simulate, and SL-D8's stage **S6** loses its content. Partially covered already — AIT_001 handles ambient/Untracked NPCs and ILR-A3 zone-places them — so the real question is narrow: **does V1 need scheduled NPC *routines* (day/night, work/rest, movement between cells), or is ambient zone-placement enough?** Veloren's `rtsim` (`simulate_npcs`, `replenish_resources`) is the shape if the answer is yes. |
| **AUD-F14** | **No ruleset loader, no registry — and `RealityManifest` conflates rules with world content** | **STRUCTURAL** *(added 2026-07-26)* | Surfaced by reading `chaos-backend-service`'s `actor-core` **Configuration Hub** (`ConfigurationProvider` priority stack → `Registry` → `Combiner` per-key merge rules → `Aggregator`) against ours. **The platform promises many realities each with its own progression system, and has nowhere to put that promise.** `_boundaries` §2 `RealityManifest` declares its own owner as *"⚠ Currently unowned"*, is *"composed at book-ingestion time"* by a pipeline no document specifies, and resolves by a single rule — *"omit the field → the feature default applies"* — sufficient for two layers, broken at three. Four consequences, each independently sufficient to force a redesign later: **(a)** the struct mixes reality-wide *rules* (`stat_slots`, `races`, formulas — KB, read in every `apply()`) with per-channel *content* (`places[]`, `map_layout[]` — one entry per cell), so no loader can be scoped; **(b)** `Domain::check`/`apply` are associated fns with **no `&self` and no config parameter** ([`14_sim_core_spec.md` §4.0](14_sim_core_spec.md)) — rules can only arrive via `State` (and thus every checkpoint / migration payload / crash rebuild) or via a global, which `apply`'s own *"no I/O, no ambient clock"* contract forbids; **(c)** **replay cannot reconstruct the rules it ran under** — the log holds events, rules live outside it, so a six-month-old replay resolves against *today's* rules and defeats the conformance/oracle spine already built and passing; **(d)** the **preset tier exists in prose across ≥6 features** (IDF_001/002/003, FAC_001, PROG_001, RES_001 — *"Wuxia ships 5 races; Modern 1; Sci-fi 3"*) **and in zero types**. Plus four smaller live defects found on the same pass: fork semantics for rules are unwritten ([`03_fork_and_cascading.md`](03_multiverse/03_fork_and_cascading.md) has **zero** "manifest" matches, so an auto-fork sibling can silently get different rules); `manifest_version` exists only as a private field of DF7's `StatEpoch`, while [DF07_002 EC-15](features/DF/DF07_pc_stats/DF07_002_edge_cases_and_closure.md) already depends on a *"manifest hot-reload"* nothing designs; [`canon_cache.rs`](../../../crates/dp-kernel/src/canon_cache.rs)'s *"60s TTL fallback"* is the right key discipline but a **trap** as a rules policy (two islands inside that window diverge unreplayably); and PROG_001's five `f32` fields contradict DF7-A4 / TDIL-A9. → **Design pass done 2026-07-26:** [`16_ruleset_loader_and_registry.md`](16_ruleset_loader_and_registry.md) (`RLS-A1..A14`, `RLS-D1..D12`, `RLS-Q1..Q7`; 4 PO decisions locked: split Ruleset/WorldContent · early-bind presets · `Domain::Rules` · content-addressed digest). **Remaining: the `RLS-Q3` field-classification sweep, then the `_boundaries` §2 split.** Build-order steps 1–4 do **not** contend with AUD-F8 for the critical path. |

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
3. **AUD-F8** — `commit-service`: ✅ **designed 2026-07-26** ([`15_commit_service.md`](15_commit_service.md); CS-Q1 host shape resolved) — **implementation is now the sole top blocker**; nothing above the kernel can be built without it
4. ~~**AUD-F9**~~ — ✅ spawning · threat · loot → `COMB_005` · `COMB_003` · `COMB_004`, 2026-07-26
5. ~~**AUD-F10**~~ — ✅ abilities/skills → `ABL_001` (`features/19_ability/`), 2026-07-26
6. **AUD-F12** — explicit V1 scope call on SOC / NAR / EM / CC / DL
7. **AUD-F14** — ruleset loader / registry: ✅ **designed 2026-07-26** ([`16_ruleset_loader_and_registry.md`](16_ruleset_loader_and_registry.md)) — its build-order steps 1–4 (field classification · `Domain::Rules` · `engine_default` artifact · resolver+digest) are **independent of F8** and can run in parallel with commit-service implementation. Step 2 is time-sensitive: the `Domain` trait change is cheap now and expensive once `sim-core` S1 ships.

AUD-F11 stands as an accepted V1 cut.

> **Audit status 2026-07-26 (end of day):** **5 of 8 findings resolved** (F5, F6, F7, F9, F10). Both
> **V1-blocking** findings are closed, and the combat tier is closed end-to-end — **COMB_001 and COMB_002
> are at CANDIDATE-LOCK**, promoted because every symbol their formulas and action set referenced now has
> a declaring owner. `sim-core` **S1** and **S2** are unblocked; **S3 still waits on F8**, which is now the
> only structural blocker left.
>
> **The §4 pattern is measurably corrected.** The audit's thesis was that *design depth is inversely
> correlated with proximity to the play loop* — identity/lineage/politics all 🟢 while items, stats,
> spawning, loot and aggro were 🔴. As of today every module a player touches in the first ninety seconds
> is designed. What remains is not a *design* inversion but the **design ↔ code** one of §5: the game
> tier is now specified in depth and still has **zero** implementation.
>
> **Two things worth carrying forward, both found only because the docs finally exist together:**
> (a) the `Skill` verb was a **category error**, not a missing doc (AUD-F10) — the kind of defect that is
> invisible while the referenced module is absent, because nothing can contradict a name that resolves to
> nothing; (b) COMB_005 nearly duplicated AIT_001's population ownership, and the correct scope was only
> visible by reading AIT_001's existing `cell_untracked_density` first. Both argue for reading the
> *consumer* docs before writing a *producer* doc.
>
> **Not closed, and deliberately so:** **PvP** appears in the §2 taxonomy as 🔴 and stays there — it needs
> a consent/rules/anti-grief model rather than a combat one, and is recorded as `COMB-Q3`.

---

## 8. Cross-references

- Medium audit (predecessor) — [`10_medium_blast_radius_audit.md`](10_medium_blast_radius_audit.md)
- Movement authority — [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md)
- Interaction / position stack — [`09_interaction_layer_reconciliation.md`](09_interaction_layer_reconciliation.md)
- Agent decision standard — [`11_agent_decision_standard.md`](11_agent_decision_standard.md)
- Entity contract + Item deferral — [`features/00_entity/EF_001_entity_foundation.md`](features/00_entity/EF_001_entity_foundation.md)
- Combat — [`features/18_combat/`](features/18_combat/)
- Decisions / IDs — [`decisions/locked_decisions.md`](decisions/locked_decisions.md) · [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md)
