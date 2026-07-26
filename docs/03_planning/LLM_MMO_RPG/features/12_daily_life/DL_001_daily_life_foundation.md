# DL_001 — Daily Life Foundation ("Sinh hoạt")

> **Category:** DL — Daily Life (DF1 umbrella)
> **Status:** **DRAFT 2026-07-26** — promoted from an empty namespace. Closes **DF1**
> (*"offline PC/NPC behavior, daily routines, NPC-conversion mechanics, reclaim UX"*) and **AUD-F13**.
> Absorbs **DF8** (*"NPC persona generation from PC history — may merge into DF1"*), which merges here.
> **Axioms** `DL-A1..A8`; decisions `DL-D1..D15`. **All of `DL-Q1..Q3` resolved 2026-07-26** (§10); one
> narrower question opened (`DL-Q4`).
> **Amends locked `B3-D1`** — see §1. Pending `_boundaries/` lock + a `locked_decisions.md` amendment row.

---

## 1. Why this exists, and the B3 reconciliation

DF1 has been deferred since 2026-04-23 and was gated on **B3 "world simulation tick"**, which locked
**B3-D1: *V1 default = frozen. No between-session world activity… matches V1 solo RP scope.*** The PO
decision of 2026-07-26 (AUD-F13) puts daily life in V1, which collides with that head-on.

**The collision is real but narrow, and B3's own reasoning shows the seam.** Everything B3-D3 proposes
to simulate — *"NPC relationship drift, plotline beats, rumor propagation"* — is **LLM-generated**, which
is exactly why B3-D3 carries a `daily_budget_usd` cap and B3-D5 gates it behind paid tiers. B3 was
reasoning about the **cost of generative simulation**, not about whether the world may move at all.

Two further facts make the amendment safe:

- **B3-D1's justification is stale.** *"Matches V1 **solo RP** scope"* predates the 2026-06-20 medium
  correction to a rendered 2D/2.5D **MMO**. A frozen world is coherent for solo text RP; it is much
  harder to defend for a persistent multiplayer world. Audit `10` never re-examined B3 because its four
  auditors swept *feature* docs and B3 lives in `01_problems/`.
- **Deterministic ambient simulation costs ≈0.** Under AGT-A3, `ScriptDriver` and `EngineDriver` are
  cheap CPU, not tokens. B3's budget argument simply does not reach them.

> **DL-A1 — B3-D1 is amended to split by COST, not by phase.** *Deterministic* ambient simulation
> (schedules, replenishment, movement — engine-driven) ships **V1**. *Generative* simulation
> (relationship drift, plotline beats, rumour propagation — LLM-driven) stays **V2+/V3+** under
> **B3-D2/B3-D3 exactly as locked**, and **B3-D5's tier/budget model is unchanged.**

### 1.1 The amendment is much narrower than it first looks

B3-D1 makes two claims, and **DL_001 only touches the second**:

| B3-D1 claim | Under DL_001 |
|---|---|
| *"No between-session world **activity**"* | ✅ **PRESERVED, exactly.** Nothing runs while nobody is there — V1 routines are **evaluated on read**, never ticked forward (DL-D1). Zero background compute. |
| *"NPCs **resume where last session ended**"* | ⚠️ **superseded** — an NPC is wherever its schedule places it at the *current* `fiction_time`, not where it stood when you logged out. |

So the V1 world does not *simulate* between sessions; it **computes what it looks like now**. That
distinction also settles the related locked decision **MV12-D4** (*"V1 reality is paused when 0
players"*): pausing is irrelevant to a system that stores no forward state. A paused reality and a
running one produce the same answer, because the answer is a function of `fiction_time`, not of elapsed
ticks.

This is why the V1 layer is safe to ship against B3's intent rather than merely against its letter: B3
was protecting **cost** and **offline compute**, and DL-D1 spends neither.

---

## 2. The spine — the AI tier *is* the cost gradient

> **DL-A2 — Daily life is not one system. It is three, selected by `AIT_001` tier**, because the tier
> already encodes exactly the cost gradient B3 cared about.

| Tier | Daily-life treatment | Cost | Phase |
|---|---|---|---|
| **Untracked** | **none needed** — regenerated deterministically per `(cell, fiction_day)` | 0 | **V1 (free)** |
| **Minor** | `ScheduledActionDecl` routines, engine-run | cheap CPU | **V1** |
| **Major** | goal/relationship drift, narrative beats | LLM tokens | **V2+ / V3+** |

**The Untracked row is the pleasant surprise.** AIT_001's Untracked ID is already
`blake3(reality_id || cell_id || fiction_day || slot_index)` — **`fiction_day` is in the seed**. So the
ambient crowd *already* differs from day to day, deterministically, with no simulation whatsoever:
different villagers on Tuesday than Monday, reproducible on replay, zero cost. Nothing to build.

> **DL-A3 — V1 daily life is mostly composition, not invention.** Every V1 mechanism already exists
> under another name:

| V1 need | Already exists as |
|---|---|
| NPC routines | **AIT_001 `ScheduledActionDecl`** inside `MinorBehaviorScript` (Q7b) |
| ambient crowd variation | **AIT_001** deterministic `fiction_day` seed |
| ambient economy | **RES_001**'s four generators — `Scheduled:CellProduction`, `NPCAutoCollect`, `CellMaintenance`, `HungerTick` |
| the clock routines run on | **TDIL_001** per-turn O(1) generators (TDIL-A3) |
| where it executes | **Class C `sim-rtsim`** ([13](../../13_simulation_loop.md) SL-A2, [14](../../14_sim_core_spec.md) §3) |
| driver swap for PC→NPC | **AGT-A3** runtime-swappable drivers |

DL_001's job is therefore to **drive and sequence** these, plus own the two genuinely new things:
**offline-PC semantics** (§5) and **PC↔NPC conversion** (§6).

---

## 3. V1 — the deterministic layer

> **DL-A4 — A V1 routine is a pure function of `(actor_class, fiction_time, cell)`.** No LLM, no
> persisted per-NPC plan, no accumulated state. It is *evaluated*, never *simulated forward*.

```
ScheduledActionDecl {              // AIT_001 Q7b — extended here, not invented
  window:   FictionTimeWindow,     // e.g. Dawn..Midday
  location: PlaceRef,              // where this class is during the window
  activity: ActivityKind,          // Work | Rest | Socialise | Travel | Sleep
}
```

### 3.1 Variation without state (DL-Q3 → DL-D15)

> **DL-D15 — Routines are declared per `actor_class` and varied per NPC by a deterministic jitter.**
> The dichotomy "per-class (cheap, uniform) vs per-NPC (varied, stateful)" is false — variation can be
> *derived* rather than *stored*:
>
> ```
> effective_window = declared_window + (hash(npc_id) % jitter_range)
> ```
>
> The blacksmith rests at dusk + 7 min, the baker at dusk − 12 min. Reproducible on replay, **zero stored
> state, still O(1)** — so **DL-D1 survives intact**. This is the same seeded-determinism pattern already
> used by TMP_001, CSC_001, COMB_002's arena generator and AIT_001's Untracked IDs; no new mechanism.

**Evaluation, not simulation (DL-D1).** "Where is the blacksmith at dusk?" is answered by evaluating the
declaration for the current `fiction_time` — an O(1) lookup — rather than by having ticked the
blacksmith through the day. Consequences: cold cells cost nothing (SL-D10), a returning player sees a
consistent world without any catch-up pass, and replay is trivially deterministic.

| V1 rule (`sim-rtsim`) | Does |
|---|---|
| `npc_schedule` | evaluates `ScheduledActionDecl` for Minor NPCs on cell activation |
| `ambient_activity` | picks an idle animation/emote from the activity kind (presentation only) |
| `replenish_resources` | drives RES_001's existing four generators |
| `offline_vitals` | **coarse sweep** (default 1 fiction-hour) over offline unhidden bodies; may commit death (DL-D13, §5.1) |
| `cleanup` | discards Untracked per AIT_001 Q6a-b |

> **DL-A5 — Class C never writes game state directly.** Its rules emit **Proposals** through the
> `sim-rtsim` → `sim-core` sync seam (SL-A4 dispatch/ingest); `commit-service` authorises them
> ([15](../../15_commit_service.md) CS-A5). No carve-out for background work.

**Explicitly NOT in V1** (holds the AUD-F11 line): NPC-to-NPC trade, price formation, vendor
inventories, `giao thương` UI. `replenish_resources` moves *quantities* through existing RES_001
production; it does not create a market. **Player-facing trade stays deferred.**

---

## 4. V2 and V3 — the generative layers (B3-D2 / B3-D3 unchanged)

> **DL-A6 — Generative daily life is opt-in per reality and budget-capped, exactly as B3 locked.**
> DL_001 changes *nothing* about B3-D2/D3/D5; it only states what they simulate once DL exists.

**V2 — lazy-when-visited (B3-D2).** On first entry to a region after a gap > 24 h (configurable), one
LLM call produces a summary of what changed for **Major** NPCs there. Cached per-region until the next
reality-clock update. Bounded: 1 call per region visit.

| V2 rule | Does |
|---|---|
| `major_drift_summary` | the single lazy call; writes a `DriftSummary` |
| `pc_persona_seed` | **DF8 merged here** — seeds an NPC persona from a converted PC's history (§6) |

**V3 — scheduled tick (B3-D3).** Nightly/weekly cron under `multiverse.simulation.daily_budget_usd`,
skipped if the reality is idle > `simulation.idle_skip_days` (default 7). Advances NPC relationship
drift (within R8-L4 decay), plotline beats, rumour propagation.

| V3 rule | Does |
|---|---|
| `relationship_drift` | REP_001/FF_001 deltas within R8-L4 bounds |
| `plotline_beats` | narrative beats for Major NPCs |
| `rumour_propagation` | information spread across the channel tree |
| `ambient_economy` | **price/production feedback — needs AUD-F11's deferred module first** |

> **DL-D2 — `ambient_economy` is V3, gated on the AUD-F11 economy module.** V1's
> `replenish_resources` is production only. This is the line that stops DL drifting into the deferred
> `kinh tế` module.

---

## 5. The offline PC (PC-B2)

Locked: *"Visible, vulnerable; user should `/hide`; **LLM does not act**."* DL_001 supplies the detail.

> **DL-A7 — An offline PC is a *present but inert* entity.** It keeps full world presence — occupies its
> tile, is targetable, is damageable — but has **no driver**. Under AGT-A3 that is not a special case: an
> actor with no driver simply never produces a Decision. Its turn arrives, no decision is dispatched, the
> deadline fires, and **AGT-A2's context fallback (`Defend`) commits.** Nothing new to build.

| State | Presence | Driver | Vulnerable |
|---|---|---|---|
| Online | full | `HumanDriver` | yes |
| **Offline, unhidden** | full | **none** → AGT-A2 fallback | **yes** |
| **Offline, hidden** (`/hide`) | withdrawn from AOI | none | **no** |
| **Converted** (§6) | full | `LlmDriver` | yes |

**`/hide` (DL-D3)** removes the PC from AOI (RTM-A6..A8) and from targeting, at the cost of starting the
conversion clock (§6). It is the player's *"I am logging off safely"* action, and it is deliberately a
trade: safety now, NPC-conversion risk later.

### 5.1 Offline vitals — coarse sweep (DL-Q1 → DL-D13)

> **DL-D13 — An offline *unhidden* PC accrues vitals and **can die of them**. ~~`/hide` pauses
> `body_clock`; an unhidden body does not.~~ ~~Hiding reuses the **TDIL-D5** precedent (a paused body
> accrues no hunger), so it is a precedented state rather than a special case.~~**
>
> **⚠ CORRECTED 2026-07-26 (REC-47 / AUD-F17 #31): the "TDIL-D5 precedent" claim is superseded —
> TDIL-D5 is a DEFERRAL, not a precedent, and per-clock pausing is exactly what TDIL V1 explicitly
> forbids.** A hidden PC's vitals immunity does not come from pausing `body_clock`. **V1
> implements `/hide` immunity as a status/driver rule:** the hidden state carries an
> **`offline_vitals` exemption flag** — the coarse `offline_vitals` sweep simply skips flagged
> bodies. Same player-visible behaviour (a hidden PC never starves), zero clock machinery.
> **Per-clock pausing stays V1+30d, landing with TDIL-D5 itself** — if/when TDIL ships it, DL_001
> may swap the exemption flag for a genuine `body_clock` pause with no behaviour change.

> **The evaluation cadence is COARSE — default 1 fiction-hour, configurable — not per-turn.** Offline
> bodies are swept in bulk by the `offline_vitals` Class C rule; they never enter the per-turn generator
> path that active actors use.

**Coarse granularity costs no fidelity.** RES_001's generators are already elapsed-time-multiplied under
**TDIL-A3** (`delta = base_rate × elapsed_time × multiplier`, O(1) regardless of magnitude). So one
sweep with `elapsed = 1h` produces **numerically the same result** as sixty per-turn evaluations. The
only thing discretised is *when the death threshold is observed to be crossed*:

| | |
|---|---|
| **Accepted** | a PC whose hunger would reach zero at `T+3.2h` is recorded dead at the `T+4h` sweep — a **delayed trigger**, deliberately |
| **Accepted** | between sweeps, an observer may briefly see a body that is "already" doomed |
| **Why it is fine** | death is a *committed event* with consequences (loot, WA_006, PLT_002 succession, faction notification); it needs a definite `died_at` and an owner, which a sweep gives and lazy-on-observation does not |

Cost is bounded by construction: offline bodies are a far smaller set than NPCs, the per-body evaluation
is O(1), and the sweep is Class C — so it can never block Class A or B (SL-A2).

**DL-D4 — logout does not auto-hide.** A player who disconnects without `/hide` leaves a vulnerable
body, which is what PC-B2 says ("*user should /hide*"). A grace window (`offline_grace`, default 5 min
wall-clock) covers accidental disconnects before vulnerability applies; it is recorded as an event, per
SL-A6, so replay does not re-time it.

---

## 6. PC → NPC conversion and reclaim (PC-B3, DF8)

Locked: *"Prolonged hidden PC auto-converts to NPC; leaves hiding; **LLM takes over**."*

> **DL-A8 — Conversion is a driver swap, not a migration.** AGT-A3 already makes an actor's driver a
> runtime-swappable field, so `HumanDriver → LlmDriver` **is** the conversion. The actor keeps its
> `EntityId`, aggregates, inventory, relationships and history. Nothing is copied, nothing is recreated,
> and reclaim is the same swap in reverse.

```
Online ──logout──▶ Offline ──/hide──▶ Hidden ──T_convert──▶ Converted(LlmDriver)
   ▲                                    │                          │
   └──────────── reclaim ───────────────┴──────────────────────────┘
```

| # | Decision | Resolution |
|---|---|---|
| **DL-D5** | Conversion trigger | Hidden continuously for `T_convert` **fiction-days** (RealityManifest, engine default 30). Fiction-time, not wall-clock, so TDIL dilation applies coherently. |
| **DL-D6** | Tier on conversion | Promotes to **Major** (it has `actor_progression`, history and relationships — Minor cannot represent it). Counts against `TierCapacityCaps` Major ≤ 20; **on overflow, conversion is deferred, never dropped** — the PC stays Hidden. |
| **DL-D7** | Persona seed (**DF8**) | Persona is generated from the PC's own history — IDF_003 personality, REP_001 standing, FF_001/FAC_001 ties, recent canonical events. **V2** (needs an LLM); until then a converted PC runs a `ScriptDriver` stub with its declared personality. |
| **DL-D8** | Reclaim | Player returns → driver swaps back to `HumanDriver`, **immediately**, at the actor's current position and state. Whatever the NPC did is canon and is **not** rolled back. |
| **DL-D9** | Reclaim conflict | If the converted NPC died while converted, reclaim follows **WA_006 Mortality** for that reality — DL_001 adds no separate death rule. |
| **DL-D10** | Consent | Conversion is disclosed at onboarding (PO_001) and is a **World Rule** (DF4) toggle per reality — a reality may set `pc_conversion_enabled = false`, in which case hidden PCs stay hidden indefinitely. |

### 6.1 Mortality of a converted PC (DL-Q2 → resolved by DL-A8)

> **A converted PC keeps its PC mortality class.** This needs no new rule: **DL-A8** says conversion is a
> *driver swap, not a migration*, so the entity does not change what it **is** — only who decides for it.
> Mortality is a property of the entity and the reality's **WA_006** configuration, never of the driver.
> Permadeath reality → a converted PC can permadie. Protective reality → protection continues.

Consent already sits at the right level: **DL-D10** makes conversion a World Rule toggle, disclosed at
onboarding (PO_001). But that covers *whether* conversion happens, not *what the driver then does with
your character*, so:

> **DL-D14 — The converted driver runs a RISK-AVERSE tool set.** A converted PC's `allowed_tools`
> (AGT-A2) excludes combat *initiation*: it defends, travels, works, trades and talks, but never starts a
> fight. This is a bounded-vocabulary constraint on an existing mechanism — no new subsystem — and it
> closes the unfairness of an LLM picking a fight the owner never would.

**DL-D11 — the converted PC is narratively legible.** It carries a `WasPlayerCharacter` marker so
NPC_002 Chorus can prompt it with its own history rather than a generic persona. This is what makes the
mechanic *interesting* rather than merely a cost optimisation: the world fills with characters who used
to be someone's protagonist.

---

## 7. Where it runs

`sim-rtsim` (Class C), per [14 §3](../../14_sim_core_spec.md). V1 ships four rules; V2 adds two; V3 adds
four. The `sync.rs` seam is the only path back into `sim-core`, and every rule's output is a Proposal
(DL-A5).

**DL-D12 — routine evaluation is Class A-cheap, so it may run inline on cell activation** rather than as
a Class C job: evaluating `ScheduledActionDecl` is an O(1) table lookup (DL-D1). Only replenishment and
the V2/V3 generative rules are genuinely background.

---

## 8. Acceptance criteria (V1)

| # | Scenario |
|---|---|
| **AC-DL-1** | A Minor NPC with a `ScheduledActionDecl` is at its `Work` location at midday and its `Rest` location at dusk, without any tick having run in between. |
| **AC-DL-2** | Entering the same cell on two different `fiction_day`s yields a *different but reproducible* Untracked crowd. |
| **AC-DL-3** | A cold cell consumes zero CPU: no `npc_schedule` evaluation occurs until a PC activates it. |
| **AC-DL-4** | `replenish_resources` moves RES_001 quantities over elapsed fiction-time with O(1) cost regardless of dilation (TDIL-A3). |
| **AC-DL-5** | An offline unhidden PC is targetable and damageable; its turn resolves via AGT-A2 fallback, not by stalling the encounter. |
| **AC-DL-6** | An offline PC inside `offline_grace` is **not** vulnerable; the grace expiry is a recorded event and replays identically. |
| **AC-DL-7** | `/hide` removes the PC from AOI and from valid target sets. |
| **AC-DL-8** | A PC hidden for `T_convert` fiction-days converts to a Major NPC, retaining `EntityId`, inventory and relationships. |
| **AC-DL-9** | Conversion at Major cap defers rather than dropping; the PC stays Hidden and converts when a slot frees. |
| **AC-DL-10** | Reclaim restores `HumanDriver` at the NPC's current position; actions taken while converted remain canon. |
| **AC-DL-11** | A reality with `pc_conversion_enabled = false` never converts a hidden PC. |
| **AC-DL-12** | Replaying a V1 daily-life day produces byte-identical state (no LLM in the V1 path). |
| **AC-DL-13** | An offline **unhidden** PC left long enough starves to death; the death commits at a **sweep boundary**, carries a definite `died_at`, and triggers WA_006 + loot + succession normally. |
| **AC-DL-14** | An offline **hidden** PC never starves, however long it is hidden (~~`body_clock` paused, TDIL-D5~~ **`offline_vitals` exemption flag — REC-47 2026-07-26**; per-clock pausing is V1+30d with TDIL-D5). |
| **AC-DL-15** | One `offline_vitals` sweep with `elapsed = 1h` yields **exactly** the vital values sixty per-turn evaluations would (TDIL-A3 O(1) elapsed multiplication) — coarse granularity is numerically lossless. |
| **AC-DL-16** | A converted PC in a permadeath reality can die permanently; in a protective reality it cannot. Identical outcomes to the same character played by its owner. |
| **AC-DL-17** | A converted PC's driver cannot **initiate** combat (DL-D14 tool set), but does defend when attacked. |
| **AC-DL-18** | Two Minor NPCs of the same `actor_class` in the same cell keep **different** routine offsets, reproducibly across replays, with no per-NPC state stored (DL-D15). |

## 9. Deferred

| ID | Item | Phase |
|---|---|---|
| **DL-DF1** | `major_drift_summary` lazy generative pass | V2 (B3-D2) |
| **DL-DF2** | `pc_persona_seed` from PC history (DF8) | V2 |
| **DL-DF3** | relationship drift · plotline beats · rumour propagation | V3 (B3-D3) |
| **DL-DF4** | `ambient_economy` price/production feedback | V3, gated on AUD-F11 |
| **DL-DF5** | NPC-to-NPC trade, vendors, `giao thương` | deferred with AUD-F11 |
| **DL-DF6** | Sleep/fatigue as mechanics rather than presentation | V1+ |
| **DL-DF7** | Lazy-materialise offline death on *observation* as well as on sweep (belt-and-braces with DL-D13) | V1+, only if the sweep window proves visible in play |

## 10. Open questions

**All three resolved 2026-07-26.**

| # | Question | Resolution |
|---|---|---|
| ~~**DL-Q1**~~ | ~~Does an offline PC accrue `HungerTick`?~~ | ✅ **DL-D13** — yes, and it **can kill**; evaluated on a **coarse sweep** (default 1 fiction-hour), not per-turn. §5.1. |
| ~~**DL-Q2**~~ | ~~Can a converted PC die permanently?~~ | ✅ **Follows from DL-A8** — it keeps its **PC mortality class**; a driver swap does not change what the entity *is*. Plus **DL-D14** risk-averse tool set. §6.1. |
| ~~**DL-Q3**~~ | ~~Per-class or per-NPC routines?~~ | ✅ **DL-D15** — per-class declaration **+ deterministic per-NPC jitter**. Variation without state; DL-D1 intact. §3.1. |

### Newly opened

| # | Question |
|---|---|
| **DL-Q4** | Should the coarse sweep (DL-D13) also cover *converted* PCs and Major NPCs, or do they get vitals through the normal per-turn path once active? Likely the latter, but the boundary between "unattended body" and "active NPC" needs stating once NPC vitals exist. |

## 11. Cross-references

- DF1 / DF8 deferrals — [`decisions/deferred_DF01_DF15.md`](../../decisions/deferred_DF01_DF15.md)
- PC-B2 / PC-B3 / B3-D1..D5 — [`decisions/locked_decisions.md`](../../decisions/locked_decisions.md)
- AI tiers, `ScheduledActionDecl`, Untracked generation — [`../16_ai_tier/AIT_001_ai_tier_foundation.md`](../16_ai_tier/AIT_001_ai_tier_foundation.md)
- Resource generators — [`../00_resource/RES_001_resource_foundation.md`](../00_resource/RES_001_resource_foundation.md)
- Clocks / dilation — [`../17_time_dilation/TDIL_001_time_dilation_foundation.md`](../17_time_dilation/TDIL_001_time_dilation_foundation.md)
- Drivers / fallback — [`../../11_agent_decision_standard.md`](../../11_agent_decision_standard.md)
- Class C placement — [`../../13_simulation_loop.md`](../../13_simulation_loop.md) · [`../../14_sim_core_spec.md`](../../14_sim_core_spec.md)
- Authority — [`../../15_commit_service.md`](../../15_commit_service.md)
- Mortality — [`../02_world_authoring/WA_006_mortality.md`](../02_world_authoring/WA_006_mortality.md)
- Audit findings AUD-F11 / AUD-F13 — [`../../12_module_coverage_audit.md`](../../12_module_coverage_audit.md)
