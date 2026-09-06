# A5 — Feature Demand Census: what every feature needs from an event / causality layer

**Corpus:** `docs/03_planning/LLM_MMO_RPG/features/**` (35 folders) + the requirements corpus in
`docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md` §28–§29 + architecture docs 26/29/31/32/33/34/35 and the
shared registries in `_boundaries/`. **`07_event_model/` was deliberately NOT read** — a sibling agent
owns it. Everything below is what the *consumers* demand, stated in their own words.

**Path convention.** All `doc:line` citations below are relative to
`D:\Works\source\lore-weave-game-foundation\docs\03_planning\LLM_MMO_RPG\features\`
unless the path starts with `docs/` or a bare number (`31_…`, `33_…`), which are relative to
`D:\Works\source\lore-weave-game-foundation\docs\03_planning\LLM_MMO_RPG\` and
`D:\Works\source\lore-weave-game-foundation\` respectively.

---

## 0 · THE HEADLINE, BEFORE THE TABLE

Three findings frame everything else, and each is stated by the corpus itself, not by me.

**(1) The corpus already knows the verb layer is the missing half, and has said so four times
independently.** `31_world_simulation_architecture.md:48` — *"**WSA-F1 — the ontology does not supply
WHEN.** … a general moment vocabulary: on-hit, on-enter, on-death, on-threshold-crossed,
on-day-boundary. **Without it, nothing can happen except when a player acts.**"* Four role-played
authors, blind, converged on the same thing: `docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md:5782` — *"**What
is missing, entirely, is the VERB layer. Nothing an author declares can HAPPEN.**"*; `:5917` — *"My
book is not a set of ladders. It is **what happens when a number crosses a line** … what I can declare
is a beautifully-validated character sheet for a world where nothing yet happens."*

**(2) The demand is overwhelmingly for *memory*, not for *delivery*.** Of the ~270 distinct demands
below, the great majority carry an explicit durability requirement in the feature's own words, and
they name three different reasons for it: **audit** (an operator must be able to ask "why?"),
**replay** (byte-identical reproduction), and **fiction** (a later decision reads it). Only a small
minority are happen-only, and — this is the sharp part — **several features go out of their way to
say a thing must NOT be recorded** (`18_combat/COMB_005_encounter_spawning.md:151` — *"A respawn is
not an event; it is the passage of fiction time changing the answer to a pure function. Nothing is
written, nothing is scheduled, nothing can drift."*). A design that treats "event" as "anything that
changes" will over-record exactly where these features bought their cheapness.

**(3) There are already TWO independent orderings of causality in the corpus, and they have never been
mapped to each other.** `_boundaries/03_validator_pipeline_slots.md:25-109` defines a **10-stage
validator pipeline** (0 · 1 · 2 · 3 · 3.5.a–e · 4 · 5 · 6 · 7 · 8 · 9 · commit · post-commit
side-effects). `33_trigger_group_order.md:60-70` defines an **8-group resolution law** (G1 ADMIT ·
G2 AUTHORISE · G3 REPLACE · G4 APPLY · G5 LIFECYCLE · G6 REACT · G7 IMPRINT · G8 DERIVE) with a
locked order and six named swap-bugs. Both claim to order the same thing. `_boundaries/03:7` even
says its own ordering is *"the working consensus"* pending the event-model track. **Reconciling these
two is a prerequisite for this design round, not an output of it.**

**(4) The single most-repeated unmet demand is not "notify me" — it is "do these N writes across N
feature-owned aggregates atomically, or none of them."** It appears as an acceptance criterion
(`PF_001:656-661`), as a named-and-deferred missing primitive (`GEO_003:700` — `Forge:BundleDeltas`),
as an all-or-nothing precondition across N actors (`TVL_005:458`), as a same-commit destroy-and-clear
(`PL_007_item.md:714-725`), as a 4-op multi-aggregate finalize (`PLT_002:316-323`), and as a
five-step single-transaction session close (`DF05_001:325`). **A design that answers "publish a
message" answers this wrong six times.**

---

## PART 1 — THE DEMAND TABLE

One row per demand. Durability column: **D** = must be remembered (queryable later / in a chronicle /
affects a later decision / auditable / replayable) · **E** = must merely happen · **D\*** = ephemeral
store but replay-reconstructible and checkpointed · **d** = derived, never stored.

### 1.1 Entity lifecycle and the holder cascade (EF_001, PL_007, PF_001)

| feature | demand, as a capability | trigger | consequence it must cause | durable? | doc:line |
|---|---|---|---|---|---|
| EF_001 | An entity's *state* is a declared ordinal and the *machine* is engine mechanism — **a settlement declares `thriving \| declining \| abandoned \| razed` and the engine runs it without knowing what "abandoned" means** | any declared transition | validate against the declared set; reject one that is not in it | **D** (append-only log) | `00_entity/EF_001_entity_foundation.md:407-428` |
| EF_001 | A lifecycle transition and its **entire cascade land in a single atomic write** | holder/parent transitions | held + contained + embedded entities transition together; `reason_kind = HolderCascade`; `causal_ref` → trigger event | **D** | `EF_001:475-486` |
| EF_001 | Destruction and admin-removal cascade **differently, on purpose** | `→ Destroyed` vs `→ Removed` | Destroyed ⇒ held items **drop to ground**, stay `Existing` ("the items survive their owner"); Removed ⇒ held items **cascade-remove** ("this never existed") | **D** | `EF_001:481-484` |
| EF_001 | A destroyed entity's location is **frozen for audit** while scene-roster queries must not see it | lifecycle ≠ Existing | binding keeps last cell for *"where did Lý Minh die?"*; `MemberLeft` emitted so presence excludes it | **D** | `EF_001:182` |
| EF_001 | Every lifecycle transition is appended with a **typed causal ref and a reason** | any transition | `entity_lifecycle_log` row `{state_before, state_after, fiction_time, causal_ref, reason_kind}` | **D** (append-only, immutable — `entity.lifecycle_log_immutable`) | `EF_001:197-218`, `:551` |
| EF_001 | A suspended NPC re-loads **inside the same write transaction as the PC's move**, not eventually | PC enters the cell | NPC `Suspended→Existing` + `MemberJoined` + presence Active, all before validators see post-move state | **D** | `EF_001:720` |
| EF_001 | An LLM may **propose** an entity into existence, gated by author review before it becomes real | LLM suggestion | `EVT-T6 Proposal EntitySpawnProposal` → Forge gate → `EVT-T4` | **D** | `EF_001:91` |
| EF_001 | Cycles in the holder graph are refused at write time | proposed location change | `entity.cyclic_holder_graph` | **D** | `EF_001:486`, `:557` |
| PL_007 | An item's charges hitting zero **destroys it in the same commit as the Use that spent them** | last charge spent | one commit: vital delta + `charges 1→0` + `Existing→Destroyed` + one lifecycle-log entry whose `causal_ref` is that Use | **D** | `04_play_loop/PL_007c_integration.md:371-373`, `PL_007_item.md:711-712` |
| PL_007 | **An item breaking must clear its equipment slot in the same transaction, or a destroyed item keeps applying its bonuses** | item `→ Destroyed`/`Removed` | clear every `actor_equipment` slot holding it + bump `equipment_version`; multi-slot items clear primary and `blocked_by_primary` together | **D** | `PL_007_item.md:714-725`, `PL_007c:404-408` |
| PL_007 | A holder dying must clear equipment **inside** the EF_001 cascade batch, not after it | holder `→ Destroyed` | one atomic batch: N `entity_binding` moves + `actor_equipment` cleared + `equipment_version` bump | **D** | `PL_007c:318-329`, `_boundaries/03_validator_pipeline_slots.md:137` |
| PL_007 | An item **never suspends alone; it follows its holder** and its slot survives | holder cold-decays | item `→ Suspended` in lockstep, `actor_equipment` row retained, restore re-arms | **D** | `PL_007_item.md:639-654`, `PL_007c:449-455` |
| PL_007 | An author edit to a definition must be **blocked while live instances depend on it** | `Forge:EditItemDef` with an equipped instance | `item.def_edit_blocked_by_equipped` | **D** | `PL_007c:149` |
| PL_007 | Affordances are **materialised at birth and are not retroactive**; a later def edit reports how many live instances kept the old set | `Forge:EditItemDef` | audit-visible retained-instance count, not a reject | **D** (audit) | `PL_007c:148` |
| PL_007 | On a **multiverse fork**, instance + equipment + binding rows copy bit-exactly and provenance survives — *"a forked sword remembers being forged in the parent"* | snapshot fork | paired copy; post-fork def edits are local to the forking reality | **D** | `PL_007_item.md:759-768` |

### 1.2 Threshold — a number crossed a line

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| RES_001 | A pool reaching zero emits a **trigger, not a death** — the three-layer model is already in the naming | `current_value == 0` + `OnZeroEffect::EmitMortalityTrigger` | `MortalityTransitionTrigger { actor, cause_kind }` → WA_006 | **D** | `00_resource/RES_001_resource_foundation.md:286-289`, `:345-349`, `:624` |
| RES_001 | A pool reaching zero may instead **apply a status** | Stamina = 0 | `OnZeroEffect::ApplyStatus(Exhausted)` | **D** | `RES_001:347` |
| RES_001 | Hunger crossing magnitude 7 kills | `Scheduled:HungerTick` increments to ≥7 | `MortalityTransitionTrigger { cause_kind: Starvation }` | **D** | `RES_001:559-560`, `04_play_loop/PL_006_status_effects.md:226` |
| DF07/RES | **A max-value decrease clamps the current value and must NOT fire the zero-effect** — *"a clamp must never kill; only damage does"* | `MaxHp` recomputed downward | `VitalMaxRecomputed { kind, old_max, new_max }`; growth does not heal, clamp does not kill | **D** | `RES_001:296-300`, `DF/DF07_pc_stats/DF07_001_actor_stat_block.md:595-608` |
| COMB_001 | **A vital reaching zero is reversible** — KO for `ko_duration_rounds`, then Dying | `HP == 0` | `knocked_out` status; on expire → WA_006 `Dying` | **D** | `18_combat/COMB_001_combat_foundation.md:238-239` |
| COMB_004 | **Loot is generated exactly once, at defeat finalisation, never at KO** | mortality finalisation (Tracked) or `group_pool == 0` (Untracked) | `roll_spoils()` once, guarded by a `spoils_rolled` marker | **D** | `18_combat/COMB_004_loot_and_spoils.md:91-99`, `:277-302` |
| COMB_004 | A retried finalisation must not re-roll — *"because the seed is deterministic, a naive re-roll would produce the same items again, i.e. **silent duplication that no diff would catch**"* | replay / retry | `spoils.already_rolled` | **D** | `COMB_004:300-302` |
| PROG_001 | A growing number crossing a tier ceiling causes a **qualitative jump** | `raw_value == tier_max` at a training tick | tier advances, `raw_value` resets, `ProgressionDelta::TierAdvance` **plus** a `BreakthroughAdvance` cascade-trigger for downstream subscribers | **D** | `00_progression/PROG_001_progression_foundation.md:549-551`, `:1090-1107` |
| PROG_001 | A breakthrough may **consume an item and require a place** at the instant it fires | `AtMaxPlus { item_consumption, location_required }` | pill consumed + tier advanced + 2 events, all-or-nothing | **D** | `PROG_001:330-339`, `:1396-1399` |
| COMB_003 | A **relative** margin, not an absolute one, switches a target | `challenger > current × switch_margin_pct/100` | target switch; below margin no switch (anti-flicker) | **D\*** | `18_combat/COMB_003_threat_and_targeting.md:202-221` |
| COMB_006/004 | A power **ratio** crossing a line has two complementary consequences that may never both fire | `ratio ≥ threshold` | `cap_applies` (damage capped) xor `cap_waived` (binding severable) | **D** | `18_combat/COMB_006_pvp_and_stakes.md:240-258`, `COMB_004:707-736` |
| COMB_004 | Accumulated deaths wear a binding to a break point | Nth death | `durability -= bind_sunder_per_death`; at 0 the binding breaks, item drops at *that death's place* | **D** | `COMB_004:658-681` |
| combat concept | A scripted reaction fires when a pool crosses a **percentage** line | `OnHpThreshold { below_pct: 30 }` | pre-canned `ActionDecl`; `priority` breaks multi-trigger ties | E | `18_combat/00_CONCEPT_NOTES.md:516-532` |
| WA_002 | A budget counter crossing its cap changes the **world's** state, not the actor's | contamination usage > cap | strain bump → `world_stability` stage advance | **D** | `02_world_authoring/WA_002_heresy.md:288-300` |
| spec §28 | *"A village where grain crossing zero proposes FAMINE, which drains population, which drops the settlement tier, which lets the machine transition to `abandoned` — **that is a chronicle. Everything between those two sentences is one table with no rows.**"* | grain → 0 | multi-hop threshold → status → lifecycle chain | **D** | `docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md:6033-6036` |
| spec §2.6.2 | A threshold **proposes** a status, never applies one, and must declare a **hysteresis floor** or it flaps | band entered/exited | `ThresholdDecl { quantity, enter, exit, proposes: StatusOrdinal, order }`; `\|exit−enter\| ≥ 1000/ceiling` refused at declare time | **D** (hashed manifest) | `docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md:224-246` |
| spec §2.6.2 | *"`AtValue(0)` exists because **'exactly zero' is the case this whole document was written for** and a percentage cannot express it when the ceiling is absent or zero"* | exact-value band | `Band::AtValue(0)` | **D** | `docs/specs/…-actor-dataflow.md:245-246` |

### 1.3 Status — a condition applied / cleared on an entity

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| PL_006 | A status is **applied with a magnitude, a source and a stack policy**, uniformly across PCs and NPCs | Interaction outcome / world-rule / Generator / admin | `ApplyStatus { flag, magnitude, expires_at_fiction_ts, source_event_id, source_kind }`; policy ∈ `{Sum, ReplaceIfHigher, Coexist}` per flag | **D** | `04_play_loop/PL_006_status_effects.md:38-43`, `:80-113`, `:190-198` |
| PL_006 | Every status instance **records what caused it**, so an operator can ask *"what made Lý Minh Drunk?"* and a remedy can dispel selectively | apply | `StatusSource` enum + `source_event_id`; enables forensic audit, selective dispel, replay traceability | **D** | `PL_006:232-238` |
| PL_006 | A status **auto-expires at a fiction-time**, fired by a scheduler that does not exist in V1 | `fiction_clock` crosses `expires_at_fiction_ts` | `EVT-T5 Generated::Scheduled:StatusExpire`, `causal_refs = [original Apply]`, RNG seeded from causal refs | **D** | `PL_006:230`, `:381-400` |
| PL_006 | A status must be **refused on a dead target**, through the entity layer's canonical rule, not its own | apply on `lifecycle ≠ Existing` | `entity.lifecycle_dead` at stage 3.5.a — *deliberately re-allocated away from `status.target_dead` to avoid a duplicate rule* | E | `PL_006:249`, `:255`, `:267` |
| PL_006/DF07 | A status must map to **stat modifiers**, and must **never resize a pool by the back door** | flag applied | `Wounded` degrades output, **never `MaxHp`** — otherwise *"a status silently deals damage, breaking COMB_001's status-applies-AFTER-damage invariant"* | **D** | `PL_006:206-213`, `DF07_001:576-579` |
| PL_006/DF07 | The same status must not be counted in **two layers** | registering a resolution-time flag as a stat modifier | validator DF7-V6 reds | **D** | `PL_006:213`, `DF07_001:240-246` |
| COMB_001 | Round-scoped statuses must be **decremented by someone** — PL_006 V1 has no auto-expire at all | round boundary | engine decrements `knocked_out`/`defending`/`slowed`/`hasted`/`stunned` + ABL durations; expiry reported in `CombatRoundDelta` | **D** | `COMB_001:189-197`, `DF07_002:109-115` |
| spec §2.6.3 | A status carries a **stack policy, an expiry form, a magnitude unit and a closed effect set** | declared | `StackPolicy{Replace\|Stack{max}\|Refresh\|Ignore}` · `ExpiryForm{Rounds\|UntilCleared\|WhileProposed}` · effects ∈ `{PoolDelta, StatModifier, BlockActions}` | **D** (hashed) | `docs/specs/…-actor-dataflow.md:248-268` |
| spec §2.6.10 | A **reaction may veto a proposed status, and only a proposed one** — *"that is the whole reason the propose/apply split exists"* | `Proposed(status)` | `Veto` legal only on `Proposed`; `Applied`/`Cleared` subscription points fixed now, effect vocabulary deferred | **D** | `docs/specs/…-actor-dataflow.md:374-385` |
| AIT_001 | **Status effects on an Untracked actor are emitted and then discarded with the actor** | Strike on an Untracked | *"status events for Untracked are emitted but discarded … no persistence"* | E | `16_ai_tier/AIT_001_ai_tier_foundation.md:1117` |

### 1.4 Lifecycle of non-entity aggregates (world stability, sessions, transfers, titles)

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| WA_002 | A **world-stability stage advance broadcasts to every descendant channel and every live session**, and changes how every subsequent LLM prompt is assembled | admin (V1) / threshold (V2+) | T3 write + `WorldTick` at reality root → bubble-up emits derivative ambient events at continent/town/cell → UI banner → persona prompts carry `world_stability=…` | **D** | `02_world_authoring/WA_002_heresy.md:288-300`, `:441-450`, `WA_002b_heresy_lifecycle.md:156-165` |
| WA_002 | `Shattered` is **terminal, monotonic, and retroactively invalidates other features' in-flight state machines** | stage = Shattered | contaminating actions rejected; *"pending transfers in flight forced-abort"* | **D** | `WA_002:435-439`, `WA_002b:196` |
| WA_002 | The world keeps a **bounded chronicle inside the aggregate** — 16 most recent stage transitions | any stage change | `world_stability.stage_history: Vec<StageTransition>` (silently truncates) | **D** | `WA_002:201` |
| PLT_002 | A **multi-day, multi-party ownership transfer** whose two approvals may arrive in any order | initiate | `Pending`(14d TTL) → `Cooldown`(7d) → `Finalized` \| `Aborted`(6 reasons); *"Order doesn't matter; both must say yes"* | **D** | `10_platform_business/PLT_002_succession.md:256-331`, `:305-306` |
| PLT_002 | **Nothing happening for 7 days is itself the trigger** | cooldown elapse | hourly sweeper finds `cooldown_entered_at + 7d < now` → Finalize; no new approvals | **D** | `PLT_002:312`, `:610-628` |
| PLT_002 | Finalize is a **4-op atomic write across four aggregates including the meta registry** | finalize | `t3_write_multi`[transfer, `reality_registry.owner_id`, grant create, grant delete] + roles_version bumps | **D** | `PLT_002:316-323` |
| PLT_002 | A failed finalize must leave the machine **resumable**, retry hourly, escalate at 24h | DB error mid-commit | state stays `Cooldown` | **D** | `PLT_002:499-501`, `PLT_002b:134` |
| DF05 | Session close is a **5-step cascade in a single Postgres transaction**; mid-cascade failure rolls everything back | last PC leaves | `Closing` → per-actor LLM distill → `Closed` | **D** | `DF/DF05_session_group_chat/DF05_001_session_foundation.md:306-325` |
| DF05 | A closed session is **immutable** — *"cannot reopen session for 'objective truth'"* | Closed | reject `session.closed_session_immutable` | **D** | `DF05_001:151`, `:260-263` |
| TIT_001 | **A title vacates when its holder dies, and cascades to an heir synchronously, in the same turn** | WA_006 mortality event | per title: resolve heir → delete old holding → insert new → update the *faction* aggregate's role → emit `TitleSuccessionTriggered` (+`…Completed` iff an heir exists) | **D** | `00_titles/TIT_001_title_foundation.md:364-388`, `:391-471` |
| TIT_001 | Heir eligibility is evaluated **at succession time**, not designation time | cascade runs | dead heir ⇒ `HeirIneligible`, `to_actor_id: None` | **D** | `TIT_001:411-418` |
| TIT_001 | A vacancy has author-chosen semantics, **one of which mutates the world declaration** | no eligible heir | `PersistsNone` \| `Disabled` \| **`Destroyed` ⇒ `canonical_titles[title_id]` removed — RealityManifest mutated** | **D** | `TIT_001:455-470` |
| TIT_001 | The cascade must be **replay-deterministic** — *"fully deterministic — no RNG V1"* | any succession | — | **D** | `TIT_001:473-475` |
| FAC_001 | A faction's head changes because the old head died | death of the actor at `authority_level=100` | `SetCurrentHead` on the faction aggregate, driven by TIT_001 | **D** | `00_faction/FAC_001_faction_foundation.md:90`, `:484-508` |
| FF_001 | Death **marks the node deceased but preserves the edges as history** | WA_006 death | `MarkDeceased`; *"lao_ngu still has tieu_thuy in children_actor_ids — historical"* | **D** | `00_family/FF_001_family_foundation.md:98`, `:453-477` |
| FF_001 | A marriage writes **both** actors' nodes from one action | marriage turn | two `AddSpouse` EVT-T3 from one T1, `causal_refs=[T1]` | **D** | `FF_001:426-449` |
| spec §2.6.4 | A lifecycle machine is declared, and **its transitions trigger on a STATUS** | `OnStatus(StatusOrdinal) \| OnAdmin \| OnCascade` | `MachineDecl { states, initial, transitions, cascade: state → CascadePolicy }` where policy ∈ `{Drop, Cascade, Suspend, Keep}` | **D** (hashed) | `docs/specs/…-actor-dataflow.md:270-297` |
| spec §2.6.4 | **An unbounded cascade is a hang, authored in content** — a state the cascade can reach must not cycle back into it | resolve-time well-formedness | refuse the machine | **D** | `docs/specs/…-actor-dataflow.md:293-294` |
| spec `O-111` | A transition carries **no value effects**, so *"refounded: reset grain, keep fertility"* is **not expressible even on paper** | — | design gap named | — | `docs/specs/…-actor-dataflow.md:6084` |

### 1.5 Scheduled — fires at a fiction-time

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| RES_001 | Four day-boundary generators, **ordered against each other by a coordinator** | fiction-day boundary crossed | `CellProduction` → `NPCAutoCollect` → `CellMaintenance` → `HungerTick`, in that order, *"so the owner has a fresh balance"* | **D** | `RES_001:769-790` |
| RES_001 | A multi-day jump **batch-emits every skipped day deterministically** | travel of 5 fiction-days | 5 days' production emitted; *"Multiple actors/turns within same fiction-day → no double-trigger (Generator dedup by day-marker)"* | **D** | `RES_001:494-502` |
| RES_001 | Each generator is **replay-deterministic by declared seed** | any fire | RNG seeds per EVT-A9 | **D** | `RES_001:790-800` |
| RES_001 | Generators must be **cycle-free within a fiction-day** | any fire | *"They emit T5 events; T5 events do NOT cascade to T6/T1/T3 within same day"* | **D** | `RES_001:798-802` |
| RES_001 | Deterministic **food-priority order** when several foods qualify | HungerTick | author-declared `consumable_priority`, default = declaration order | **D** | `RES_001:563` |
| PL_006 | Auto-expire fires from a `FictionTimeMarker` trigger source | clock crosses expiry | `Scheduled:StatusExpire` | **D** | `PL_006:386-400` |
| PL_005c | A respawn beat fires N fiction-days after death | `state = Dying` | `EVT-T5 Generated::Scheduled:Mortality:Respawn` → `Dying → Alive` at spawn cell + `MemberJoined` + session move | **D** | `04_play_loop/PL_005c_interaction_integration.md:215-224` |
| WA_006 | Death behaviour is a per-reality config read **at the moment of death**, with a per-PC override shadowing it | any death | `RespawnAtLocation { spawn_cell, fiction_delay_days, memory_retention }` ⇒ a deferred respawn scheduled N fiction-days out | **D** | `02_world_authoring/WA_006_mortality.md:102-110`, `:293-302` |
| PROG_001 | `Scheduled:CultivationTick` runs **5th and last** in the day-boundary chain, reading end-of-day state | day boundary | cultivation sees post-status state | **D** | `PROG_001:1037-1050` |
| REP_001 | Reputation **drifts toward 0 with the passage of fiction-time, with nothing happening** | fiction-time elapse | `DecayTick { score_change }` — mechanism unresolved: *"lazy-on-read vs session-end vs scheduled cron"* | **D** | `00_reputation/REP_001_reputation_foundation.md:139`, `:311-312` |
| WA_002 | The daily contamination budget resets **lazily on next read**, from a clock other players advanced | day rollover | `day_marker < current day ⇒ usage_today = 0` | **D** | `WA_002:187`, `:355-359` |
| PLT_001 | An invitation expires after 7 days by an **hourly sweeper**, and the expiry is audited but emits **no event** | TTL elapse | invitation deleted + audit `outcome=Expired`; *"may be captured as ForgeAuditEntry without EVT-T8"* | **D** (audit only) | `10_platform_business/PLT_001_charter.md:380-387` |
| WA_003 | A Tier1 edit becomes a **pending intention with a 5-min TTL that must expire silently and unaudited** | no second approver | `pending_edit` dropped; *"ForgeAuditEntry NOT logged"* | **E, by design** | `02_world_authoring/WA_003_forge.md:304-312`, `:732` |
| DL_001 | An offline body **accrues vitals and can die of them**, evaluated by a **coarse 1-fiction-hour sweep** | sweep boundary | death commits with a **definite `died_at` and an owner** — *"which a sweep gives and lazy-on-observation does not"* → WA_006 + loot + succession | **D** | `12_daily_life/DL_001_daily_life_foundation.md:206-222` |
| DL_001 | The **grace expiry is itself a recorded event**, *"so replay does not re-time it"* | 5-min wall-clock disconnect grace | recorded per SL-A6 | **D** | `DL_001:225-228` |
| doc 34 | A locus publishes `next_wake` — *"the fiction-time at which its own trajectory crosses its next declared threshold"* — and **there is no tick** | trajectory computed | island wakes loci in `next_wake` order | **D** | `34_when_the_world_runs.md:85-86` |
| doc 34 | **Every committed delta to a locus's quantities must recompute its `next_wake`** — coupling invalidates predictions | any delta | unconditional invalidation (WSA-L2) | **D** | `34_when_the_world_runs.md:139` |
| 13_quests (reservation) | A **standing predicate** fires when a quest precondition becomes true | *"calibration / turn / event match"* | `Scheduled:QuestTrigger` reserved as EVT-T5 | **D** | `13_quests/00_V2_RESERVATION.md:33` |

### 1.6 Interaction — one entity acts on another

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| PL_005 | An interaction carries a **4-role payload** (agent / tool / direct_targets / indirect_targets) and splits **proposed** from **actual** outputs | any of the 5 V1 kinds | `proposed_outputs` = the agent's intent; `actual_outputs` = the world-rule-derived outcome, populated by the validator pre-commit | **D** | `04_play_loop/PL_005b_interaction_contracts.md:28-44` |
| PL_005 | A consequence is a typed `OutputDecl { target, aggregate_type, delta, estimated_severity }` — **severity is an input to the axiom layer** | derivation | Lex evaluates severity; audit records it | **D** | `PL_005b:39-44` |
| PL_005c | Every derived consequence carries `causal_refs = [Submitted event_id]`, and **a side-effect failure does NOT roll back the parent** | post-commit | dead-letter + SEV2 + an operator reconcile command; *"No automatic compensation in V1"* | **D** | `PL_005c:101-109`, `:311-339` |
| PL_005c | A **rejected** interaction is still a committed event, and Chorus must filter it out | reject | `outcome=Rejected` committed via `t2_write` (not `advance_turn`); turn number unchanged | **D** | `PL_005c:162-164`, `PL_001b_continuum_lifecycle.md:231-235` |
| PL_005c | An interaction drives **opinion drift with per-kind calibration** | Speak/Give/Strike/Examine/Use | `OpinionDelta(trust, stance_tags)`; Strike Lethal = −50 *"regardless of outcome (intent matters)"* | **D** | `PL_005c:250-265` |
| PL_005c | Opinion drift from one interaction **immediately affects subsequent reaction priority in the same scene** | any drift | Chorus Tier-2 reads it at the next SceneRoster | **D** | `PL_005c:267-269` |
| PL_007 | Item actions are `EVT-T1 Submitted`, **not** new interaction kinds, because *"they have none of the interaction shape — no direct_targets, no bystanders, no narration requirement"* | PickUp/Drop/Equip/Unequip | 4 sub-types; payload carries an instance/slot reference and **no numbers** | **D** | `PL_007_item.md:656-672` |
| PL_007 | **An LLM must not be able to supply an engine-owned number** | JSON arriving over the ai-gateway MCP boundary | `serde(deny_unknown_fields)` → `item.engine_owned_field_supplied`; *"an LLM emitting `{"instance": "...", "heal_amount": 40}` is a realistic, observed failure mode"* | **D** | `PL_007c:76-89`, `:383-389` |
| ABL_001 | **No path may reduce a vital outside the damage law-chain** — harm made unrepresentable by type | any effect op | `VitalRestore { amount: u32 }`; harm must be `Damage { power }` which passes the chain, the hit roll, the disparity cap and the PvP predicate | **D** | `19_ability/ABL_001_ability_foundation.md:274-283`, `PL_007c:231-258` |
| COMB_003 | Threat accrual reads `damage_applied`, **never the rolled figure** | overkill / overheal | 400 damage onto 12 HP accrues 12 | **D** | `COMB_003:131-133` |
| COMB_003 | The safety guard sits **at accrual, not at selection** — *"a protected actor never gets a table row, so no driver can route around it"* | any threat write | refuse the write | **D** | `COMB_003:302-320`, `:372` |
| FF_001 | Marriage/adoption must be refused against a dead target | stage 7 world-rule | `family.deceased_target` — reads another feature's lifecycle state | E | `FF_001:300` |
| REP_001 | **Killing a faction member changes standing with that faction, and fans out to rival/allied factions** — attenuated, loop-guarded, depth-bounded | PL_005 Strike | `Delta` then `CascadeDelta { score_change, source_event, source_faction }` with `{attenuation_factor, max_depth, loop_prevention: VisitedSet}` | **D** | `REP_001:137-138`, `:303`, `:430-434` |
| COMB_006 | **Every PvP kill is a social act that writes durable sentiment** | kill | REP notoriety scaled by channel + standing; FAC standing; ACT `actor_actor_opinion` | **D** | `COMB_006:105-107`, `:262-273` |

### 1.7 Ambient / world — something happens with no single actor

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| doc 31 | **The world may act deterministically when a ledger cannot balance** — this is the one non-player trigger the exchange model supplies | conservation cannot hold | the world acts; `DL-A1/DL-D1` must be amended to permit it | **D** | `31_world_simulation_architecture.md:48-53`, `:204`, `:273` |
| doc 31 | *"Field state has no home in the three currencies"* — weather, temperature, gas, light, fertility, contamination: **state owned by nobody and held about nobody** | — | recovered by treating a cell as an entity that owns quantities; sub-cell continuous lattice stays refused **by name** | **D** | `31_world_simulation_architecture.md:56-78` |
| doc 32 | Diffusion is **a conserved transfer between adjacent locus-actors** — cell A gives 5 heat to cell B — *"which is EXC-L1 applied to neighbours, not a new mechanism"*, at a coarse cadence | time-driven | Class C batch work | **D** | `31_…:70-78` |
| doc 32 | **A place is an actor**: *"a trap is a place reacting; a village can regard you and be regarded"* | any WHEN | `EntityId::Place` + `ActorId::Locus`, on the AIT existence ladder so an unvisited cell is Untracked and takes no turns | **D** | `32_locus_as_actor.md:147-153`, `EF_001:302-326`, `:365` |
| doc 34 | **A village starves unwitnessed, in one event**; a locus at equilibrium publishes no wake and costs nothing | trajectory crossing | one closed-form event | **D** | `34_when_the_world_runs.md:258` |
| WA_002 | An ambient consequence must reach **every descendant channel** as derivative events | stage change | bubble-up aggregator emits at continent/town/cell | **D** | `WA_002:441-450` |
<!-- doc-language-gate: ok -- genre terminology and cited corpus spans. CLAUDE.md allows non-English where the text IS the subject matter: domain terms with no English equivalent (glossed in English on first use) and spans quoted from the corpus. The exposition around them is English. -->
| SPIKE_01 | Ambient scene texture (*"tiếng chân ai đó ngoài hiên"*) — *"lightweight texture; not full NPC sim; ~1 per few turns"* | scene | `scene.ambient_events[]` | E | `_spikes/SPIKE_01_two_sessions_reality_time.md:361` |
| SPIKE_02 | **World events (raid / plague / festival) — *"Event hook missing"*** | — | named as a gap against RimWorld/GW2 dynamic events | **D** | `_spikes/SPIKE_02_reference_games_gap_analysis.md:155` |
| spec §29.4 | *"a famine that is itself an actor, born, moving across a province, dissipating"* · *"天道 pressure rising as cultivators ascend, making tribulations harsher **for everyone**"* — filed under **"world scope (no owner yet)"** | — | 4 blind wishes with no receiving feature | **D** | `docs/specs/…-actor-dataflow.md:6159` |

### 1.8 Narrative / generated — an LLM or a generator proposes an occurrence

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| PL_005c | A generator subscribes to committed events, evaluates a **deterministic-RNG-seeded probability**, and may emit | `CommittedEventOf { category: Submitted, sub_type_filter: Interaction:* }` | 4 named examples: `PoliceCallout` (0.95) · `GriefDrift` (0.8/0.4) · `RumorSeed` (0.5) · `WitnessReport` (0.7 per witness) | **D** | `PL_005c:273-300` |
| PL_005c | Every generator declares **per-second / per-minute / burst caps** at registration — *"police don't respond to a flood of strikes"* | registration | `EmitRateLimit` | **D** | `PL_005c:301-303` |
| PL_005c | Generator graphs must have **static + runtime cycle detection**, cascade depth cap 16 | registration + run | *"If GriefDrift's opinion delta triggers an NPC's Strike (vengeance), that's a cascade"* | **D** | `PL_005c:305-307` |
| NPC_002 | An LLM-proposed reaction is an `EVT-T6 Proposal` that **must pass a 7-stage validator chain before it becomes real** | trigger event | reject ⇒ the reaction never existed; the rejection is auditable | **D** | `05_npc_systems/NPC_002_chorus.md:79`, `:417-425` |
| NPC_002 | The trigger's *meaning* is extracted **deterministically, not by LLM** | every trigger | `extract_knowledge_tags(narrator_text)` drives relevance | E | `NPC_002:229`, `:472-473` |
| DF05 | The LLM's distilled memory must be **cached in the event payload** so replay reads the cache and never re-calls the model | session close | payload carries facts + model id + provider + prompt-template version + attempt count | **D** | `DF05_001:729-775` |
| DF05 | A **stale** distill must be detectable and regenerable, and the old version stays valid *for its fiction-moment* | template/model version change | background regen for future queries; two truths for one event | **D** | `DF05_001:755-775` |
| AIT_001 | Untracked flavour is **explicitly NOT replay-deterministic** — *"replay regenerates with possibly different LLM output (acceptable since flavor is presentation only)"* | first interaction | session-cached, discarded | **E** | `AIT_001:375-399`, `:1327` |
| SPIKE_01 | **Narration during a time-skip is flavour, not an event** — *"LLM narration during /travel or /sleep is flavor unless explicitly marked `emit=true`"* | `/sleep`, `/travel` | flavour = non-canonical + re-generatable; structural delta (money, location, state) = canonical event | **D/E split** | `SPIKE_01:580`, `:406`, `:585` |
| SPIKE_01 | `turn.time_advancement` must be a **distinct event type** from `turn.player_action` | fast-forward | *"time-advancement events don't emit narrative as canonical; only structural deltas are canonical"* | **D** | `SPIKE_01:578` |
| doc 34 | **History is fabricated on observation, and fabrication is a deterministic FUNCTION, never a draw** | attention arrives | `history(entity, window) = f(entity_id, window, ruleset_digest, committed_events_in_window)` | **D** | `34_when_the_world_runs.md:322-328` |
| doc 34 | The generative layer **must never be load-bearing**; commit exactly what the player could falsify | surfacing | WSA-A24/A26/A28 | **D** | `34_when_the_world_runs.md:382`, `:484`, `:510` |
| EF_001 | An LLM-suggested entity spawn is a proposal behind an author-review gate | LLM | `EVT-T6 EntitySpawnProposal` | **D** | `EF_001:91` |

### 1.9 Derived / reactive — a projection must update because something else changed

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| DF07 | A stat block is a **pure function of (manifest, progression, equipment, status, archetype), never stored as truth** — *"never repaired by hand"* | any input changes | cache invalidated by a 5-field `StatEpoch`; on replay an equal epoch must produce a byte-identical block or the replay **fails** | **d** + **D** (epoch checkpointed) | `DF07_001:166-169`, `:659-676` |
| DF07 | Equipment contributions appear/vanish on **exactly** `Item:Equip` / `Item:Unequip` / the EF_001 destroy-cascade, *"and at no other time"* | those three edges | `equipment_version` bump ⇒ epoch change ⇒ re-resolve at the **next round boundary** | **D** | `DF07_001:552-556` |
| DF07 | A manifest hot-reload mid-encounter invalidates **every** combatant together | `manifest_version` change | all snapshots refresh at the same round boundary; already-resolved rounds keep their numbers | **D** | `DF07_002:144` |
| ABL_001 | The **known-ability set is derived live every turn — deliberately not snapshotted**; losing a requirement loses the ability | progression/equipment/debuff change | ability enters or leaves the legal set next turn; nothing stored, nothing to clean up | **d** | `ABL_001:435-451`, `:466-467` |
| PL_007b | The player-facing inventory is a **derived view over two stores**, rebuildable at any time, with ≤1s projection lag | either store changes | `ITM-A8` | **d** | `04_play_loop/PL_007b_inventory.md:72-83` |
| PL_007b | LLM context must be **fixed-size regardless of inventory size** — an actor with 5 items and one with 500 produce digests within a constant factor | prompt assembly | bounded digest; `item.inventory.digest_bound_violated` asserts against the *computed* bound, never a literal | **D** (validator) | `PL_007b:225-229`, `:279-281`, `:396` |
| PL_001 | The UI re-renders from **cache-invalidation broadcasts**, not from durable subscriptions | any aggregate delta | DP-X invalidation → re-render | E | `PL_006:148`, `:172` |
| REP_001 | A reputation change must **invalidate downstream caches** — Chorus Tier-4 priority + Lex gate | any rep write | subscription-driven invalidation | E | `REP_001:245-249` |
| doc 31 | **L4 derivation never writes and is never stored** — capability, stat block, standing fold | any read | *"derived-never-stored, raised to a system rule"* | **d** | `31_…:99-121` |
| doc 31 | `REP_001` is *"the scalability mechanism of WSA-A4"*: individual imprint is read at close range, **aggregated imprint at distance, as a fold updated as a Class C batch** — *"a refactor into a live query over opinion rows would reintroduce a cross-island scan"* | distance | eventual consistency, read locally, O(1) capability derivation | **D** | `31_…:139-153`, `:221` |
| doc 33 | `G8 DERIVE` — *"invalidate + re-resolve snapshots, capability"* — is the **last group**, and swapping it with G7 means *"capability is derived from stale standing — the very next action ignores what just happened"* | end of resolution | ordered last | **D** | `33_trigger_group_order.md:69`, `:94` |

### 1.10 Observation, memory, and time — the demands that do not fit the other shapes

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| AIT_001 | **Observation is what materialises state** — NPC data updates only when observed | PC observes a Tracked NPC after absence | one-shot delta per progression kind + a recorded `ActorProgressionMaterialized` event, *"not a silent read-side mutation"* | **D** | `AIT_001:672-696` |
| TDIL_001 | **An observation is a write**: any read of an unattended channel first advances that channel's clock, committed as part of the observing event's turn | actor entry / cross-realm read / AIT materialization / DL read | `ObservationAdvance` — *"recorded, not re-derived"* | **D** | `17_time_dilation/TDIL_001_time_dilation_foundation.md:329`, `:331-360` |
| TDIL_001 | Without it, an unwitnessed period **literally did not happen** — the pre-fix bug: *"a 365× realm accrued nothing; sweeps never fired"* | absence | — | — | `TDIL_001:316-324` |
| doc 34 | **The observer set is CLOSED** — `Player` · `Agent` · `EventGenerator`; *"Nothing 'happens' in the world — things are found to have happened when someone looks"* | — | WSA-A18/A19 | **D** | `34_…:213-218` |
| doc 34 | **`occurred_at` ≠ `recorded_at`** — an event caused by a crossing carries the *crossing's* fiction-time, not the observation's; every such event is bitemporal | lazy crossing | *"The event's content becomes observation-independent; only its position in the log varies with who looked when"* | **D** | `34_…:263-270` |
| doc 34 | **Observation is READ-ONLY with respect to what is true** — *"an observation that changes an outcome … makes the world depend on attention, and is the one failure mode this whole model must forbid"* | any observe | WSA-L3; test WSA-T4 runs the same scenario on two observation schedules and asserts identical `occurred_at` | **D** | `34_…:272-302` |
| doc 34 | Lazy observation is sound **only while a trajectory is self-contained** — the moment a crossing has cross-entity effects, laziness becomes a **dependency closure that can span the map** | coupled loci | *"Cutting that closure is the EventGenerator's actual job … for coupled loci it is a correctness requirement"* | **D** | `34_…:239-248` |
| DF05 | **Each participant gets their own subjective summary; two participants of the same conversation may remember different facts — *"This is feature, not bug"*** | session close | N LLM calls → 3–5 `MemoryFact` per actor | **D** | `DF05_001:354-369` |
| DF05 | Memories **bleed across sessions but not across realities** | persona assembly | top-K 10–20 by salience across all past sessions; reality-scoped | **D** | `DF05_001:614-661` |
| DF05 | Memory must be **erasable and rewritable retroactively** — purge, regen, and **anonymise a PC's name inside other actors' memories** — while the audit of the operation can never be deleted | GDPR / admin | 4 post-close Forge actions + `forge_audit_log` | **D (audit-grade)** | `DF05_001:884-908`, `:922-930` |
| DF05 | Memory is **freezable**: on death, frozen at death fiction-time; Forge-audit access only | mortality → Dead | frozen record | **D** | `DF05_001:931-936`, `WA_006:5` |
| NPC_002 | **An eligible observer that is filtered out emits no event at all, and that absence must be auditable** | cap / hash-quantile filter | *"tracked in audit by NOT having an event with her as actor for trigger 105"* | **D (by absence)** | `NPC_002:552` |
| NPC_001 | An NPC's prompt must list **other actors redacted by visibility** — it must not be told about actors it cannot perceive | persona assembly | scene context omits unseen actors | E | `05_npc_systems/NPC_001_cast.md:292` |
| DF05 | Two PCs in the same cell in **separate sessions must not see each other's events** | concurrent sessions | strict per-session visibility | **D** | `DF05_001:667`, `:1251-1259` |
<!-- doc-language-gate: ok -- genre terminology and cited corpus spans. CLAUDE.md allows non-English where the text IS the subject matter: domain terms with no English equivalent (glossed in English on first use) and spans quoted from the corpus. The exposition around them is English. -->
| NPC_002 | **Cascade depth 1**: an NPC's reaction may not trigger another NPC in this batch — the second-order reaction must **surface on the next PC turn**, not be dropped | NPC insults NPC | *"on my next turn, I see Du sĩ glare back"* | **D** (must survive to next turn) | `NPC_002:314-322`, `:576-584` |
| NPC_002 | A reaction batch must be **idempotent on `trigger_event_id`** and resumable from `committed_count` after a writer-node crash | crash | resume, never duplicate | **D** | `NPC_002:377`, `:442` |
| NPC_002 | Ordering must be **deterministic and replayable** — tier → fairness rotation on `last_reacted_turn` → `hash(npc_id, trigger_event_id)`; even the "random" intent is seeded | batch resolution | `last_reacted_turn` is persisted selection state | **D** | `NPC_002:246-258` |
| AIT_001 | An **ephemeral actor with no aggregate must still emit lifecycle events**, *"for audit symmetry"* | cell entry / leave / session end / promotion | `Generated:UntrackedNpcSpawn` / `…Discarded` with a 6-variant reason enum | **D** | `AIT_001:351-354`, `:481-509` |
| AIT_001 | Identity of an unstored actor is **derived, not stored** | generation | `blake3(reality, cell, fiction_day, slot)` — replay regenerates the same id, stats and name | **D by determinism** | `AIT_001:216-226` |
| AIT_001 | **Promotion crystallises an ephemeral actor into a persistent one, preserving its id** | `Forge:PromoteUntrackedToTracked` / COMB engagement / DL conversion | writes `npc_core` + `actor_progression` + `actor_clocks`; emits `TrackingTierTransition` with `from_tier = None`; **soft-fail-at-cap: queue, never reject** | **D** | `AIT_001:404-473`, `:189-202` |
| TDIL_001 | An actor carries **three proper-time clocks** (actor / soul / body) and each generator binds to a *named* one | every turn | production reads wall time, hunger reads `body_clock`, cultivation reads soul-or-body — *the same turn produces different elapsed for different consequences* | **D** | `TDIL_001:153-177`, `:272-297` |
| TDIL_001 | One event may **split a worldline into two clocks** | `PcTransmigrationCompleted` | `actor_clock=0`, `soul_clock` from A, `body_clock` from B; both remain valid; old worldline preserved as terminated | **D** | `TDIL_001:414-448`, `06_pc_systems/PCS_001_pc_substrate.md:797-838`, `:816` |
| TDIL_001 | Cross-channel events are ordered **by causation, not absolute time** — *"simultaneity is not defined"* | any cross-channel pair | causal refs are the ordering | **D** | `17_time_dilation/00_CONCEPT_NOTES.md:116`, `:148` |
| TDIL_001 | **Edits to past clock values are permanently forbidden** | Forge | `time_dilation.past_clock_edit_forbidden` | **D** | `TDIL_001:493`, `:568` |
| WA_001 | Rule changes are **non-retroactive**; already-committed events stay canon | author flips an axiom | past events unchanged; only future proposals gated | **D** | `WA_001_lex.md:368-375` |
| PL_001b | A rejected turn **commits an event but does not advance the turn number or the fiction clock** | reject | committed via `t2_write`, tagged with the current (un-incremented) turn number | **D** | `PL_001b:231-235`, `:305` |
| PL_001b | **One idempotency window, 5 minutes, everywhere** — the prior split produced a zone where a retry was simultaneously a new turn and a duplicate: *"the worst possible split"* | client retry | gateway cache + `turn_idempotency_log` + bus retention all at 5 min | **D** | `PL_001b:201`, `:206` |
| PL_001b | A reality is bootstrapped by a **manifest that five-plus features extend**, and activation is one atomic multi-write with cross-feature validation | `RealityManifest` received | `t3_write_multi`: clock + channels + places + layouts + scene layouts + bindings, then `RealityActivated`; a missing `PlaceDecl` rejects activation | **D** | `PL_001b:317-377` |
| PL_001b | **Lazy cell creation** must derive place + map layout + scene layout deterministically and emit their births | first `/travel` into an undeclared cell | `derive_lazy_place` + `derive_lazy_map_layout` (golden-angle spiral, *"replay-safe per EVT-A9 — NOT random"*) + `ensure_cell_scene_layout` (blake3 seed) + `LayoutBorn` + `SceneLayoutBorn` | **D** | `PL_001b:379-478` |
| PO_001 | A single admin event must **orchestrate a 14-feature cascade in one turn**, all causal-ref'd to it, fully deterministic, replayable | `Forge:CompleteOnboarding` | 17-step chain *"all within same turn-event commit window"* | **D** | `03_player_onboarding/PO_001_player_onboarding.md:187-193`, `:497-527` |

### 1.11 Place, map, scene, travel — the spatial family (cuts across shapes 3, 4, 6, 8)

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| PF_001 | **A place has a durable structural state machine** — `Pristine \| Damaged \| Destroyed \| Restored` — and `Restored` is deliberately distinct from `Pristine` *"to preserve audit precision (rebuilt-after-destruction differs from original-untouched)"* | PL_005 Strike with sufficient cumulative damage · Forge · V1+ scheduled catastrophe | `EVT-T3 Derived aggregate_type=place` structural-state delta | **D** | `00_place/PF_001_place_foundation.md:44`, `:283-327` |
| PF_001 | Forbidden transitions are enforced at write time — `Destroyed → Pristine` must go via `Restored` | any transition | `place.invalid_structural_transition` | **D** | `PF_001:318-327` |
| PF_001 | **A place being destroyed emits a dedicated cascade-trigger event enumerating its occupants in a deterministic sort order**, then fires consumer cascades in that order | `→ Destroyed` | single atomic batch: (1) place delta → (2) `PlaceDestroyed { place_id, occupants: Vec<EntityId> }` sorted by `(entity_type_discriminator_u8, entity_id_uuid_bytes)` *"for replay-determinism"* → (3) consumer cascades in occupant order → (4) cell-resident cascade | **D** | `PF_001:335-341`, `:64-67` |
| PF_001 | A place carries a **freeform narrative drift accumulator** distinguished from the closed state enum *"for queryability — operators ask 'is tavern operational?' via StructuralState; LLM ingests drift JSON for descriptive flavor"* | author edit or V1+ in-fiction LLM proposal | `narrative_drift` delta, treated as **opaque** — *"do NOT extract structured fields server-side V1"* | **D** | `PF_001:45`, `:155-159`, `:65` |
| PF_001 | *"PC Strikes the wall enough times → tavern damaged → references to fixtures behind that wall now fail → **cascade into EF_001 lifecycle**"* | cumulative damage | dangling-reference prevention is the stated reason the feature exists | **D** | `PF_001:31` |
| CSC_001 | A scene layout is **deterministic from a hash of place state and time**, so the same inputs re-render byte-identically | first PC entry / bootstrap | `procedural_seed = blake3(reality_id, cell_id, structural_state, fiction_time_bucket)`; ChaCha8, *"NOT thread-local random"*; `SceneLayoutBorn` emitted | **D** | `00_cell_scene/CSC_001_cell_scene_composition.md:73`, `:183`, `:272`, `:93` |
| CSC_001 | The scene must **re-derive when the place's structural state changes** — the state is an input to the seed | structural change | *"Cached forever until structural change"* | **D** | `CSC_001:93`, `:185` |
| CSC_001 | An **LLM-generated zone assignment is a cache invalidated by the occupant set changing** or by a prompt-template version bump | entity entry/exit at the cell; `prompt_template_version` mismatch | re-call; `layer3_source: CanonicalDefault \| LlmGenerated { model, attempts, generated_at }` tracks provenance *"for audit + cache invalidation"* | **D** | `CSC_001:186-188`, `:78` |
| CSC_001 | The LLM call is **async (2–30s) and occupants may change mid-call** — a race policy is required | Layer 3 in flight | explicit PC race-condition policy; `csc.layer3_occupant_set_changed` reserved | **D** | `CSC_001:458`, `_boundaries/02_extension_contracts.md:132` |
| MAP_001/PL_001b | A **lazily created cell must derive its map position deterministically, never randomly** | first `/travel` to an undeclared place | golden-angle spiral by sibling count, *"clamped 50..950 with margin; replay-safe per EVT-A9 — NOT random"*; `LayoutBorn` emitted | **D** | `04_play_loop/PL_001b_continuum_lifecycle.md:438-450` |
| TVL_001 | **A journey is a durable, resumable aggregate advanced by a scheduled tick**, with at most one active per actor | `Travel:Initiate` (an `EVT-T1 Submitted`, *"regular gameplay, not Forge admin"*) | `actor_travel_state { progress_fraction, expected_arrival_fiction_time, last_tick_event_id }` advanced by `EVT-T5 Scheduled:TravelTick`; second initiate → `travel.actor_already_traveling` | **D** (row retained after `Arrived` *"for audit"*) | `00_travel/TVL_001_travel.md:30`, `:34`, `:38`, `:50`, `:96-97`, `:117` |
| TVL_001 | Journeys exist **only for Tracked-tier actors** — Untracked NPCs have no row, *"per AIT-A8 quantum-observation discipline"* | tier | sparse aggregate | **D** | `TVL_001:30` |
| TVL_001 | Arrival is **computed, not scheduled** — it happens when `progress_fraction` reaches 1.0 | tick | causal-ref to the tick that crossed it | **D** | `TVL_001:50` |
| TVL_004 | **An encounter fires from a deterministic pre-rolled schedule when a tick crosses a scheduled progress point, and PAUSES the journey** | tick crossing `trigger_progress_fraction` | `EVT-T3` creates `travel_encounter` (Pending) + journey paused; *"NOT a player event — the encounter is system-generated from the deterministic schedule"* | **D** | `00_travel/TVL_004_travel_encounters.md:24`, `:35`, `:53` |
| TVL_004 | The encounter's identity, its kind roll, its LLM prompt seed **and** its outcome roll all derive from one seed | schedule | `EncounterId = blake3(journey_id, encounter_seed, trigger_progress_fraction)` — *"replay-deterministic"* | **D** | `TVL_004:33`, `:89`, `:133` |
| TVL_004 | **The LLM narrates the situation and proposes the outcome; the engine clamps it before applying** | Pending → Resolving → Resolved | `EVT-T6 Encounter:SceneNarration` (*"Ephemeral narration … NOT canonical state"*) → player `EVT-T1 Encounter:Resolve` → `EVT-T3` apply, *"every field engine-clamped to the encounter-table entry's `OutcomeBounds`"* | **D** (state) / **E** (narration) | `TVL_004:54-57`, `:130` |
| TVL_004 | Resolving an encounter **shifts the journey's arrival time later by exactly the fiction-time it consumed** | resume | *"the encounter delayed the trip"*; next `Scheduled:TravelTick` resumes advancement | **D** | `TVL_004:131`, `:59` |
| TVL_004 | An admin may **skip a stuck encounter but may not author its outcome** — *"forcing a bespoke outcome would bypass the LLM-propose + engine-clamp path"* | `Forge:ResolveEncounter` | Skip-only; journey resumes untouched, no outcome applied | **D** | `TVL_004:58` |
| TVL_004 | At most one unresolved encounter per journey, guaranteed by the schedule's own spacing | invariant | `travel_encounter` with `status ∈ {Pending, Resolving}` ≤1 per journey; encounters never fire at 0.0 or 1.0 | **D** | `TVL_004:125`, `:127` |
| GEO_002 | **A province may be merged, split into N successors, or transferred between states** — *"a border province switches allegiance after siege"*, *"a civil war producing 3 successor states is one delta, not 2 separate splits"* | Forge admin (V1+30d) | `MergeProvinces` · `SplitProvince(Vec<ProvincePartition>)` · `TransferProvinceToState`; partition cap 8 | **D** | `00_geography/GEO_002_political_layer.md:24-25`, `:100` |
| GEO_002 | **An LLM may propose a political evolution from observed strategic events, gated by author review** | V2+ | `EVT-T6 POL:NarrativePoliticalEdit` — *"LLM proposes Merge/Split/Transfer based on observed strategic events (siege successes, dynastic deaths via TIT_001)"*; Forge reviews and materialises via T8 | **D** | `GEO_002:58` |
| GEO_002 | A generator feature-flag flip **mid-life on an existing reality is FORBIDDEN** — it changes derived world state | config | flag affects only new realities at bootstrap | **D** | `GEO_002:453` |
| GEO_002 | Downstream visual layers **subscribe durably to geometry events** | province centroid change | `dp.subscribe_channel_events_durable::<WorldGeometryEvent>` → MAP_001 border overlay redraw | **D** | `GEO_002:409`, `:587` |
| SPIKE_02 | *"Disaster / world events (raid / plague / festival)"* — **"Event hook missing"**; *"Travel encounters (random event between cells) — MAP traversal hook"*; *"Time-limited events (Halloween / Lunar New Year) — Calendar bind"*; *"Notifications when world event happens — Push surface"* | — | four named gaps against reference MMOs | **D** | `_spikes/SPIKE_02_reference_games_gap_analysis.md:155`, `:163`, `:238`, `:261` |

### 1.12 The spatial family, continued — ordering, determinism, fork, and demands for ABSENCE

| feature | demand | trigger | consequence | durable? | doc:line |
|---|---|---|---|---|---|
| PF_001 | **Birth strictly precedes membership** — *"It STRICTLY PRECEDES cell-channel `MemberJoined`; it does not emit it"* | bootstrap phase 3 vs 6 vs 7 | an ordering window that a third feature must insert into | **D** | `PF_001:62`, `:561-584` |
| CSC_001 | **A birth must be insertable BETWEEN two events owned by third parties** — after `place.place_type` is readable, before `MemberJoined` | first PC entry | `ensure_cell_scene_layout` wedged into PL_001's travel sequence as a **synchronous RPC step**, explicitly because *"Subscribe is read-only per DP convention"* | **D** | `CSC_001:820-843`, `:822` |
| PF_001 | Fixture seeds materialise **in the same atomic batch as place birth**, with derived deterministic ids | place birth | per-fixture `entity_binding` + `EntityBorn`; `seed_uid = UUIDv5(reality_id, place_id, slot_id)` | **D + byte-deterministic** | `PF_001:401-408`, `:669` |
| PF_001 | Damage **bubbles UP** — a destroyed fixture re-evaluates its container's structural state | EnvObject `Existing → Destroyed` | place `Pristine → Damaged` via a *"cascade hook"* | **D** | `PF_001:601-613` |
| PF_001 | The down-cascade fires **only** on transitions ending in `Destroyed` — *the only thing preventing a down/up cycle*, and it is prose, not a mechanism | any transition | non-Destroyed transitions must not propagate | **prose rule, no mechanism** | `PF_001:329-333` |
| GEO_001 | **A biome override cascades within a BOUNDED neighbourhood** — recompute `is_coast` for the cell + ≤12 neighbours, then re-run the water-network stage scope-bounded | `SetBiomeOverride` | post-delta state must satisfy fresh-world invariants | **D** | `GEO_001_world_geometry.md:524` |
| GEO_001 | **A cascade that cannot be computed must be BLOCKED, not approximated** — a water↔land flip can re-partition the global Ocean-vs-Lake component, and naval adjacency is *derived, not stored* | water↔land override | hard reject `geography.biome_override_water_transition_v1` | **D** | `GEO_001:524`, `:536-561` |
| GEO_002 | A derived summary is recomputed and **written back unconditionally, even if unchanged** — *"an 'if changed' guard would introduce a mode-stability question"* | `SetCultureRegion` over 47 cells | every intersecting state's `culture_tag` rewritten | **D** | `GEO_002_political_layer.md:351-366` |
| GEO_004 | **One route's creation creates another route** — a navigable segment of an emitted road auto-emits a RiverNavigation route tagged with the parent's rank | stage 7 emission | secondary emission with a provenance backlink | **D** | `GEO_004_route_network_generator.md:244-249` |
| GEO_004 | **A cascade is DETECTED and deliberately NOT enforced** — removing a route that orphans a settlement warns ops only, because *"admin may intentionally isolate a settlement"* | `RemoveRoute` | dashboard signal, no reject | E | `GEO_004:320-322` |
| GEO_001 | **Ordered append with optimistic concurrency** — `prev_delta_id == last_delta_event_id`; rewriting a past delta is forbidden; a retry with the same prev is idempotent, a retry after success is rejected | delta submit | `geography.delta_order_violation`; *"Replay = base + deltas in order. No destructive regeneration"* | **D (the log IS the record)** | `GEO_001:256-257`, `:487`, `:498` |
| GEO_003 | **A documented DEADLOCK is asserted as correct behaviour** — moving a state capital is *"GENUINELY IMPOSSIBLE… Both possible orderings deadlock"*, and an acceptance criterion asserts the deadlock | admin moves a capital | hard reject either way; escape is rebootstrap | — | `GEO_003_settlement_generator.md:322-331`, `:683` |
| GEO_003 | **A transactional multi-delta primitive is a recognised MISSING capability** — `Forge:BundleDeltas`, an atomic `Vec<GeographyDeltaKind>` with an all-or-nothing validator transaction | sequences passing through invalid intermediate states | deferred V2+ | — | `GEO_003:700-701` |
| TVL_001 | **An in-flight process must VETO a substrate edit that would invalidate it** — a cross-feature validator owned by travel, registered in the route pipeline | admin `RemoveRoute` on a route with an active journey | `route.remove_blocked_by_active_journey` | **D** | `TVL_001:258`, `:279` |
| TVL_002 | **…but the veto deliberately does NOT extend to PLANNED future segments** — *"would let a single long composite journey veto admin route edits across a wide swath of the graph (operationally unacceptable)"* | admin removes a future segment's route | allowed; the composite must self-heal or strand | policy | `TVL_002_composite_travel.md:540` |
| TVL_002 | **A frozen plan must RE-PLAN mid-flight when reality moved under it**, capped, with a terminal failure state | next segment fails validation at handoff | Dijkstra from the current cell, splice the tail, `replan_count++`, cap 3 ⇒ `Stranded` | **D** | `TVL_002:235-257` |
| TVL_005 | **A journey's arrival must cascade to N actors who have no journey row of their own** | leader's `Travel:Arrive` | every member's cell set + journey ref cleared, **routed through the standard cell-change cascade so session and interaction layers see it**; CI-gated | **D** | `TVL_005_group_party_travel.md:119`, `:209-213`, `:520` |
| TVL_002/005 | **A parent cascade step must be conditionally SUPPRESSED by a descendant feature to avoid double-charging** | `Party:Travel` / per-segment initiate | deliberately skips the parent's provisions deduction so the per-member cascade is *"the SINGLE authoritative deduction"* — with no mechanism naming the suppression | **D** | `TVL_005:188`, `TVL_002:196` |
| TMP_001/006 | **Pre-commit veto over a HYPOTHETICAL** — simulate the placement and reject if it would increase the connected-component count, ~100× per zone | any object/obstacle candidate | `would_seal_a_gap()`; candidate rejected, next tried | E per attempt | `TMP_001_tilemap_foundation.md:595`, `TMP_006_treasure_and_objects.md:208-219` |
| TMP_001 | **A rejected mutation must be a NON-occurrence**, and a failed generation must leave **no aggregate and no birth event** — *"a timed-out job produces no tilemap, never a differently-truncated one"* | validator reject / job timeout | reject envelope only; `tilemap.generation_timeout` | **absence asserted** | `TMP_001:677`, `:695`, `:581` |
| TMP_001/MAP_001 | **A derived view must PARTIALLY re-derive — *"partial update, not full regenerate"*** — and must explicitly **not** emit the birth events | `Forge:EditMapLayout{UpdatePosition}` | anchors recomputed; `kind: ChildCellAnchorUpdated`; **no `TilemapBorn`, no `ZonesPlaced`** | **D (absence asserted)** | `TMP_001:422-427`, `:650`, `MAP_001_map_foundation.md:41`, `:834` |
| TMP_001/005 | **A regeneration mode carries a PARTIALITY axis** | `Forge:RegenTilemap` | `CosmeticOnly` re-runs one stage preserving geometry byte-for-byte vs `FullRebootstrap` destroy-and-recreate; `CosmeticOnly` **refused** if an upstream aggregate changed (`tilemap.regen_mode_incompatible`) | **D** | `TMP_001:659-668`, `:494` |
| TMP_008 | **A global version bump must invalidate every cached LLM output at once** — no event, no target set, no way to observe completion | `prompt_template_version` increment | forced re-call across all cells of all realities | **D field, global sweep** | `CSC_001:643`, `TMP_008b_llm_contract_spec.md:789` |
| TMP_008 | **An author veto REVERSES an already-applied machine decision and cascades backwards** into downstream caches | `Forge:VetoLlmClassification` | L3 digest changes → L4 invalidated → re-narration | **D** | `TMP_008_llm_integration.md:200`, `:120` |
| TMP_008 | **Out-of-taxonomy or canon-contradicting LLM output routes to an APPROVAL QUEUE instead of auto-applying** | unlisted kind; oracle contradiction | `Forge:ApproveCanonKind`; an accepted-but-not-yet-effective state | **D pending state** | `TMP_008:158`, `:214` |
| TMP_008b | **A proposal is NOT atomic — partial acceptance in one logical apply** — *"49 LLM classifications + 1 fallback, not 50 fallbacks"* | validation errors on a subset | valid entries commit, failing subset retried, residue defaulted; `attempts` + `fallback_count` recorded | **D** | `TMP_008b:322-392` |
| GEO_004 | **A NEW invariant is retro-enforced on already-persisted worlds by writing SYNTHETIC deltas into the audit log** — the system writes its own history, idempotently, in cohorts, with a `reason` naming the migration | a generator ships on a pre-existing reality | machine-authored `RemoveRoute` deltas | **D, audit-graded** | `GEO_004:312-316` |
| GEO_001–004 / TVL_001–005 | **A world is PINNED to a generator version for life** — mid-life pipeline upgrade and feature-flag flips are both FORBIDDEN | attempted flip | `geography.pipeline_version_mismatch` | **D** | `GEO_001:98`, `:258`, `TVL_001:361` |
| GEO_001 / TVL_001–005 / PF/CSC/TMP | **A snapshot fork copies in-flight process state bit-exactly, then the branches diverge with no cross-cascade** — active journeys, composites, pinned encounter schedules, parties, mounts, and `geography_deltas[..fork_point]` | fork | CI gate: *"base + deltas at fork-point = child's initial state"*; parent's post-fork deltas do **not** reach the child | **D** | `GEO_001:571-586`, `TVL_001:253-256`, `TVL_004:323-326` |
| GEO_001–004 | **…except an L2 canon edit, which reaches parent AND child *unless* the child holds an L3 delta on the same object** | L2 canon edit | per-object, lineage-aware, conditionally-suppressed fan-out | **D** | `GEO_001:582`, `GEO_002:515` |
| PF/MAP/TMP/SPIKE_03 | **Per-observer knowledge — one world, different visible state per PC** | PC examines / moves | `discovered_connections` / `discovered_nodes` / `discovered_tiles`, each queryable per PC | **D per-PC — and deferred four times, independently** | `PF_001:47`, `:686`, `MAP_001:262-267`, `:794`, `TMP_001:506`, `_spikes/SPIKE_03_tilemap_world_view.md:263` |
| TMP_003/005/007 | **A second, non-event causality system inside generation** — a declarative happens-before DAG with cross-subject barriers, plus zone A calling a method on zone B's live instance under two write locks, plus runtime producer→consumer registration | generation | *"three honest admissions that the messaging model could not express the requirement"* | E | `TMP_003_pipeline_modificators.md:21`, `:78-82`, `TMP_007_connections_and_guards.md:158`, `:214-224`, `TMP_005_biome_and_obstacles.md:305-318` |
| TMP_008 | **Cost is a correctness property** — ~$0.038/tilemap, ~$3.23/reality initial, ~$8.50/reality/year; the seasonal invalidation wave is ~$1.30 per refresh across 85 tilemaps | duplicate delivery / over-eager invalidation | *"idempotency here is not hygiene; it is the cost model"* | **D** | `TMP_008:137`, `:140-145` |

---

## PART 2 — THE PATTERN EXTRACTION

The eight shapes you proposed are all real and all attested. But the evidence says **the count is
eleven**, and — more importantly — **two of your eight are not siblings of the others**: one is a
*modifier* that applies to every shape, and one is a *layer* underneath all of them. The three I am
adding are not refinements; each has its own mechanism, its own failure mode, and at least one
feature that exists only to serve it.

### The eleven shapes

| # | shape | what makes it distinct | strongest evidence |
|---|---|---|---|
| **1** | **Threshold** — a monotone quantity crossed a declared band | needs hysteresis, exactly-once firing, and a *proposal*, not an application | `docs/specs/…-actor-dataflow.md:224-246`; `RES_001:559`; `PROG_001:549`; `COMB_004:91` |
| **2** | **Status** — a named condition applied/stacked/expired on an entity | needs a stack policy, a magnitude, a source, an expiry form, and a **veto point** | `PL_006:38-43`; `docs/specs/…:248-268`, `:374-385` |
| **3** | **Lifecycle** — a durable state transition with a declared cascade | needs a declared machine, an atomic cascade, an append-only reason log | `EF_001:407-486`; `docs/specs/…:270-297` |
| **4** | **Scheduled** — fires at a fiction-time | needs a coordinator order, day-boundary dedup, batch catch-up, determinism | `RES_001:769-802`; `PL_006:381-400`; `34_…:85` |
| **5** | **Interaction** — one entity acts on another | needs the 4-role payload, proposed-vs-actual split, validator pipeline | `PL_005b:28-44`; `PL_005c:14-110` |
| **6** | **Ambient / world** — a consequence with no single actor | needs a holder for conservation, and either a locus-actor or a field model | `31_…:56-78`; `32_…:147-153`; `SPIKE_02:155` |
| **7** | **Narrative / generated** — an LLM or a generator proposes an occurrence | needs a propose→validate→commit gate, seeded probability, rate caps, cycle detection | `PL_005c:273-307`; `NPC_002:79`; `34_…:322-328` |
| **8** | **Derived / reactive** — a projection must update because something else changed | needs epoch/version invalidation, **must not be stored as truth**, resolves last | `DF07_001:166-169`; `ABL_001:435-451`; `33_…:69` |
| **9** | **Observation** ⭐ NEW | *the act of looking is itself the causal event.* Not a read: it commits a clock advance, materialises accrued state, and fabricates history. It has a **closed observer set** and a law forbidding it from changing outcomes | `34_…:213-218`, `:272-302`; `TDIL_001:329-360`; `AIT_001:672-696` |
| **10** | **Existence-tier transition** ⭐ NEW | promotion/demotion between "not modelled at all" and "has an aggregate". Distinct from lifecycle: lifecycle moves an entity *within* being; this moves it *into and out of being modelled*, and must **backfill a history the entity never had** | `AIT_001:404-473`; `DL_001:236-276`; `31_…:209`, `:256` |
| **11** | **Admin / authoring** ⭐ NEW | a human edits the world. Distinct in every dimension: multi-approver, TTL'd intentions, non-atomic audit, may **mutate the declarative manifest itself**, and a rejected/expired one is deliberately *not* recorded | `WA_003:304-312`, `:379-386`; `TIT_001:455-470`; `PLT_002:256-331` |

### The two of your eight that are not siblings

- **(a) is a modifier, not a shape, in one specific sense.** *Threshold* is genuinely its own shape —
  but the corpus's own keystone finding is that **threshold does not cause anything directly**: it
  *proposes a status*, and only a status can trigger a lifecycle transition. `docs/specs/…:6086` —
  *"**`TransitionDecl.trigger` is `OnStatus(StatusOrdinal)`, so LIFECYCLE QUEUES BEHIND STATUSES.**
  Razed · abandoned · refounded · annexed — every existence move waits on `threshold_sets` →
  `statuses`."* So shapes 1 → 2 → 3 are a **fixed pipeline**, not three peers. Any design that lets a
  threshold fire a lifecycle transition directly is building a second, undeclared path.
- **(h) sits underneath all the others.** Derived/reactive is not a kind of event; it is what must
  happen **after** every other kind, exactly once, in the last group. `33_…:69` puts `G8 DERIVE` last
  and names the bug for getting it wrong. Treating it as a peer shape invites the double-counting
  class that DF07, COMB and PL_007 each guard against separately (see Part 3, K8).

### The orthogonal axes every shape must also carry

These are not shapes; they cut across all eleven, and each is separately load-bearing:

1. **Reality vs record** — `occurred_at` vs `recorded_at` (`34_…:263`).
2. **Canonical vs flavour** — *"LLM narration during /travel or /sleep is flavor unless explicitly
   marked `emit=true`"* (`SPIKE_01:580`).
3. **Aspect scope** — a trigger is scoped to the **aspect** it acts through (body / soul /
   held-by-others), so a body-scoped trigger on a body-dead actor is discarded while a soul-scoped one
   still fires (`33_…:143-162`).
4. **Same-commit vs post-commit vs deferred-to-boundary vs human-gated** — four different answers are
   demanded for consequences of comparable magnitude (Part 3, K3).
5. **Durable vs ephemeral-but-checkpointed vs derived vs deliberately-unrecorded** — four storage
   classes, all attested (Part 4).
6. **Partiality of invalidation** — `CosmeticOnly` vs `FullRebootstrap`, *"partial update — not full
   regenerate"*, and the global-sweep opposite where one version bump invalidates every cached output
   in every reality (`MAP_001:41`, `:834`, `TMP_001:659-668`, `CSC_001:643`).
7. **Insertion point** — several features need their occurrence to land **between two events owned by
   third parties** (`PF_001:62` strictly precedes `MemberJoined`; `CSC_001:822` must run in that gap),
   and one of them had its window silently closed to zero width by the other's emission schedule
   (`PF_001:62`). This is an ordering demand a subscription model cannot express, and the corpus's
   answer was to abandon events and wedge in a synchronous RPC.
8. **Lineage** — on a fork, in-flight process state copies bit-exactly and then diverges with no
   cross-cascade, **except** an L2 canon edit, which reaches both branches *unless* the child holds an
   L3 delta on the same object: a per-object, lineage-aware, conditionally-suppressed fan-out
   (`GEO_001:571-586`, `:582`).

---

## PART 3 — THE CONFLICTS

### K1 · Two independent orderings of causality, neither mapped to the other

`_boundaries/03_validator_pipeline_slots.md:25-109` — stages 0–9 with a 5-substage structural group
and a post-commit side-effect table (`:122-137`). `33_trigger_group_order.md:60-70` — eight ordered
groups G1–G8 with six named swap-bugs (`:87-95`) and a shuffle test (`:114-125`). They order the same
thing at different granularities and use different vocabulary for the same positions (stage 1
"capability check" vs G2 "AUTHORISE"; post-commit side-effects vs G5 LIFECYCLE + G6 REACT + G7 IMPRINT
+ G8 DERIVE). `_boundaries/03:7` concedes it is only *"the working consensus"*. **This is the single
most consequential thing to reconcile in this round.**

### K2 · The death event that at least six features subscribe to is disclaimed by the feature that owns death

`WA_006_mortality.md:75` — *"WA_006 emits **no runtime events**."* and `:82` — *"Runtime events (death
triggers, mortality state transitions, respawns) are emitted by PCS_001 / 05_llm_safety / PL when
those features ship. **Not WA_006.**"* Against that: `TIT_001:370` binds its succession cascade to
*"WA_006 mortality EVT-T3 actor_dies"*; `FF_001:98` consumes *"Death event (consumed from WA_006
mortality)"*; `FAC_001:487` says *"WA_006 emits death event"*; `REP_001` concept notes drive a rep
cascade off it; `DF05` cascades session close and POV-distill off it; `COMB_004` fires loot at
"mortality finalisation". **Six features subscribe to an event whose declared owner says it does not
exist.**

### K3 · Four incompatible answers to "when does a consequence run", for consequences of the same magnitude

| feature | policy | why | cite |
|---|---|---|---|
| TIT_001 | **synchronous, same turn** | *"delayed succession breaks story flow"* | `TIT_001:37`, `:600`, `00_titles/00_CONCEPT_NOTES.md:320-325` |
| WA_002 | **queued post-commit** | side-effects queued during validation, applied after | `WA_002:381-388` |
| WA_002 | **never automatic** | *"Auto-cascade is dangerous during prototype — runaway dynamics could shatter realities accidentally"* | `WA_002:429-433` |
| REP_001 | **no cascade at all in V1** | *"Cascade design space is wide"* | `REP_001:300-304` |
| COMB/DF07 | **deferred to the next round boundary** | a mid-round change must not alter that round's damage | `COMB_001:322-324`, `DF07_001:671-672` |
| COMB_005 | **held until another machine finishes** | an aggro during an active session is deferred, not joined | `COMB_005:339-354` |

### K4 · Ownership of the same real-world occurrence is split by actor type

`TIT_001:372-387` (self-documented): *"As locked, this trigger **cannot fire for the actors that
actually hold titles**: sect-masters, emperors and patriarchs are NPCs, and **NPCs have no mortality
state**"* — `pc_mortality_state` is PC-only and sparse; *"AC-TIT-6's own setup references a row that
cannot exist"*. The fix re-bases the NPC path on **EF_001 lifecycle `Destroyed`**. So "this actor
died" is published through **two different mechanisms depending on whether the actor is a PC**.
Mirrored in `PL_005c:211-213` (NPC mortality is a `liveness_flag` placeholder) and in `AIT_001:759`
(an Untracked killed by a PC is recorded as `CellLeave`, *the wrong reason*).

### K5 · One death fans out to at least five graphs with no defined order, and the order is semantic

Family (`FF_001:471-474`) + titles/factions (`TIT_001:391-471`) + reputation (`REP_001` concept `:221`)
+ session POV-distill (`WA_006:5`) + loot/severance/drop-cascade (`COMB_004:277-302`, `:686-706`,
`:40`) + equipment clearing (`PL_007c:318-329`). Three separate features each claim the
death→opinion cascade: `WA_006:374` assigns it to NPC_001, `FF_001:571` to NPC_002-reading-FF,
`FAC_001:603` to NPC_002-reading-FAC. And the ordering is **not incidental**: if `MarkDeceased` lands
after the succession cascade's `is_actor_alive(heir)` check, **a dead heir inherits**; if the EF_001
drop cascade runs before `SeverBinding`, the item severance was meant to transfer is already on the
floor and inside somebody else's claim (`COMB_004:686-706` vs `EF_001:481`).

### K6 · "A rejection is durable" vs "a rejection is not logged" — two opposite policies

Lex/Heresy: a rejection is a committed `TurnEvent{outcome: Rejected}` in the audit log
(`WA_001:490-503`, `:524`; `PL_001b:231-235`). Forge: *"Rejected edits NOT logged here"*
(`WA_003:148`) and an expired Tier1 pending edit is discarded with *"ForgeAuditEntry NOT logged"*
(`WA_003:312`, `:732`). Meanwhile `33_…:170` (TRG-L2) rules that a discarded trigger **must not be
silent** — *"Silence here would be XST-D2's bug class — a degrade path that absorbs the failure and
reports success."* Three positions on one question.

### K7 · Audit atomicity: four features assume an atomicity their host aggregate disclaims

FAC (`:525-529`), FF (`:493-497`), REP (`:455-461`), TIT (`:355-361`) all specify the audit entry as
part of a **3-write atomic** transaction. WA_003 — which *owns* `forge_audit_log` — locks the
opposite: *"`t2_write LexConfig` and `t2_write ForgeAuditEntry` are SEPARATE writes, NOT in
`t3_write_multi`"* (`WA_003:379-386`), with an acceptance criterion that explicitly tests the loss
path (`:739`). Combined with `REP_001:479` and `PLT_001:373`, both of which **hard-delete** and rely
on the audit log as the only record, a lost audit write leaves no record of the prior value anywhere.

### K8 · Double-counting is a recurring class, guarded case-by-case rather than structurally

Five instances, five ad-hoc guards: stat-layer vs resolution-time (`DF07_001:779`); the disparity cap
vs the Lex clamp — *"the two must not be merged (double-capping)"* (`DF07_001:590-591`);
`GroupScaling` × `Progression` (`COMB_004:220-227`); `Action` vs `CombatVictory` training
(`COMB_004:134-140`); and `ITM-C11`, where an author declaring rations as an *item* rather than a
*resource* makes a PC **starve to death while holding food** (`PL_007c:151`). Nothing in the causality
layer prevents the sixth.

### K9 · Features invent their own event vocabulary rather than using a shared one

- **Five different words for "a condition fired an action"**: `CombatTrigger`
  (`18_combat/00_CONCEPT_NOTES.md:516-532` — *the only place in the whole combat family where a general
  condition→action trigger vocabulary appears, and it never became a normative type*) ·
  `TriggerPattern` and `EventPattern` (`AIT_001:574`, `:598` — two unrelated vocabularies **inside one
  document**) · `TriggerContext` (`NPC_002:561`) · `TrainingRuleDecl.source` (`35_…:495`, described as
  *"the author's WHEN seam"* and the **only** one that exists).
- **Three unrelated "tick"s with no shared scheduler noun**: `DecayTick` (REP), `WorldTick` (WA_002),
  `HungerTick`/`CultivationTick`/`StatusTick` (RES/PROG/PL_006).
- **Two invalidation vocabularies for one job**: `InvalidationTrigger`
  (`18_combat/00_CONCEPT_NOTES.md:1093-1100`) vs DF07's `StatEpoch` — and the former names an
  HP-percentage trigger the latter's version tuple **cannot express**.
- **A `*Born` convention that one feature breaks**: `FactionBorn`, `FamilyBorn`, `ReputationBorn`,
  `EntityBorn`, `LayoutBorn`, `SceneLayoutBorn`, `ItemInstanceBorn`, `SessionBorn` — but
  `TitleGranted` for the same concept (`TIT_001:257`).
- **`EVT-T8 AdminAction` vs `EVT-T8 Administrative`** — both names live in the same corpus after a
  rename that only some docs applied (`PLT_001:76` vs `:80-86`; `WA_003:112-117`; `FAC/FF/REP/TIT`).
- **`ThreatEvent` is named an event and then explicitly denied to be one** (`COMB_003:83`).
- **`materialisation` means two opposite things**: latch-and-do-nothing (`COMB_005:237-259`) vs
  replay-N-days-and-emit-a-batch (`PROG_001:688-734`). Likewise **`epoch`** means three things
  (`COMB_005:112`, `DF07_001:659`, `DF07_001:131`).

### K10 · The corpus's own register says the trigger vocabulary is unbuilt, was double-named, and was mis-filed as a text edit

`19_reconciliation_register.md:598` — thirteen rows *"are unbuilt subsystems wearing the costume of a
table row, and that mislabelling is the likeliest reason they have not moved: a **row** reads like a
ten-minute edit, so nobody schedules it as the multi-week work it is."* Verified absent from the
codebase on 2026-07-30: **`TriggerPoint`, `StatusInstance`, `HasTags`, `replacement_priority`,
`Reproject`, `sub_index` — zero occurrences each** (`:604`). `WSA-R18` and `XST-R9` were *the same
work under two ids*, and doc 31's own row cited the other in its reference column (`:631-634`).

### K11 · A feature assumed a check that could not fire — twice, in the same corpus

`PL_007c:43-56`: the `csc.item_on_non_placeable` delegation was **vacuous** — CSC_001's applicability
predicate matched no `Item:*` sub-type, so *"a player could drop items onto non-placeable tiles
indefinitely, and the doc would read as though that were covered."* Fixed in
`_boundaries/03_validator_pipeline_slots.md:152-160`. And `ABL_001:698-707`: ABL-V4 *"ran ~1.5 stages
before the EF_001 lifecycle verdict … that its own dead-target check consumes — under a pipeline that
forbids skips"*, and *"the `ability.*` namespace currently has no row in
`_boundaries/03_validator_pipeline_slots.md`."* **Cross-feature causal ordering is being fixed by
hand, per document.**

### K12 · Cell-scoped events vs session-scoped visibility

NPC_002's whole model is cell-scoped (`NPC_002:61`, `:187`). DF05 then declares session-scoped
visibility: 95% of the cell is ambient and sees nothing (`DF05_001:480-484`), an actor is in ≤1
session, and cross-session visibility is forbidden (`:667`). DF05 defers "PC shouts to cell" to V3+
(`:1374`) — i.e. **the cell-wide event has been designed out** while a CANDIDATE-LOCK feature still
assumes it. DF05's own closure note calls this *"additive scoping"* (`NPC_002:5`); it is not additive,
it changes the observer set.

### K13 · Snapshot-vs-live is decided four different ways inside one round

Stats: snapshot, refreshed only at a round boundary (`DF07_001:614-618`). Ability *scaling*: snapshot
(`DF07_002:93-102`). Ability *legality*: live, every turn, **explicitly asymmetric**
(`ABL_001:565-578`). Threat/targeting: live, every accrual. And `actor_progression` is **written
mid-encounter** by Action training (`DF07_002:95-97`). So one aggregate has two visibilities inside a
single round depending on the consumer — correct as designed, but it means the causality layer must
support read-through-snapshot and read-live against the same aggregate and know which is which.

### K14 · Cascade depth 1 forbids three features that are already designed

`NPC_002:314-322` forbids an NPC event from triggering another NPC event. But DL's V3 rumour
propagation is by definition NPC→NPC information flow (`DL_001:163`), DF5-D9 wants autonomous NPC-NPC
continuation (`DF05_001:1371`), and NPC_003 V2 wants an NPC to *initiate* a session off its own desire
(`NPC_003_desires.md:5`). All three are second-order causality the cap structurally forbids, and no
doc says how the cap lifts.

### K15 · Two different cascade protocols for the same job

EF_001's cascade is *"computed in a **single atomic write** alongside the trigger transition"*, with a
helper (`cascade_lifecycle_transition()`) called by transition writers and a flat cascade table
(`EF_001:475-486`). PF_001's cascade is a **4-step ordered batch** with an explicit intermediate
cascade-trigger event that enumerates occupants in a deterministic sort order, and consumer cascades
firing *in occupant-list order* (`PF_001:335-341`). PL_007 then registers a hook that must run
**inside** the EF_001 batch, not after it (`_boundaries/03_validator_pipeline_slots.md:137`). Three
different shapes — an atomic helper, an ordered batch with a published intermediate event, and an
in-batch hook — for what is architecturally one mechanism. And a place being destroyed cascades *into*
EF_001 lifecycle (`PF_001:31`, `:67`), so the two protocols compose at runtime without a defined
interleaving.

### K16 · The declared layer does not execute

`docs/specs/…-actor-dataflow.md:5770` (`O-99`) — *"**The declared layer does not execute** … a
reality's declared pools, regen shapes and progression kinds round-trip a digest and are read by
nothing. *'The manifest accepts it'* has never meant *'the engine runs it'*."* And `O-112` — `granted`
has **zero occurrences in `crates/`**, so `D-4` (*an actor may lack a given pool*) *"is a drawing, not
a field"* (`:6085`). Any causality design that assumes the declaration surface is live is designing
against a document, not a system.

### K17 · The atomicity/subscribe contradiction — stated as an acceptance criterion

PF_001 demands the destruction cascade — *including PCS_001 and NPC_001 mortality writes* — be *"a
single atomic batch … commit-or-rollback together (Postgres transaction)"* with *"No intermediate
state observable to readers in same reality"*, and states it **twice as an acceptance criterion**
(`PF_001:337`, `:656-661`). In the same document, consumers *"are **NOT** silently triggered — they
**subscribe** to the dedicated `PlaceDestroyed` sub-shape"* (`:352`) via a DP durable subscribe
(`:511`). Subscription is asynchronous, at-least-once and cross-service; the transaction spans both.
GEO reaches the same wall from the other side and names the missing primitive — `Forge:BundleDeltas`,
*"atomic `Vec<GeographyDeltaKind>` with all-or-nothing validator transaction"*, deferred V2+
(`GEO_003:700`). **This is the most-repeated unmet demand in the whole corpus.**

### K18 · The cascade census omits the derived layers that depend on it

`PlaceDestroyed.occupants` enumerates *"ALL entities at the cell"* (`PF_001:340`) and never mentions
`cell_scene_layout` or `map_layout`. Yet `structural_state` is a **hash input** to CSC's
`procedural_seed` (`CSC_001:73`) and drives MAP's status overlay (`MAP_001:418-425`). Two derived views
must react to a cascade whose contract does not list them — and MAP has **no `place` subscription at
all**: the join is a **client-side dual subscription** with server-side merge deferred
(`MAP_001:612-648`, `:800`). *"A place burned down, re-render the map node"* is currently a browser
responsibility with no server-side causal link.

### K19 · The log is load-bearing for NPC memory, and the biggest occurrences are kept out of it

`SPIKE_01:481`, `:582` elects **event-log replay** as *the* mechanism for an NPC remembering what it
said: *"event-log replay filtered by `actor_id=X AND target_pc=Y AND event_type=npc_speech`"*. The same
document rules that time-skip narration, travel encounters and paused-mode routines are **not events**
(`:512`, `:580`, `:585`). **A 23-day journey produces four log entries.** An NPC cannot remember
anything that happened during a skip.

### K20 · Retroactive canonisation breaks fiction-time log ordering, and a consumer already depends on that ordering

`SPIKE_01:445` rules the traveller's departure *"pure LLM flavor"*; `:457` has an NPC state it next
morning; `:463` declares NPC utterance binding canon; `:562` records it as canonical. So the log must
accept an entry whose `fiction_ts` **precedes its emission** — and K19's replay-filtered NPC memory is
exactly a consumer that assumes fiction-time order equals log order. There is no write path, no
ordering rule, and no rule for two NPCs promoting contradictory versions of the same absent event.

### K21 · Five different reconciliations of LLM output with engine state, none shared

(a) **Clamp-and-apply silently**, with the clamp as a CI invariant (`TVL_004:261-268`, `:583`).
(b) **Snapshot-hash and abort** if the world moved during a 2–30s call — hand-rolled optimistic
concurrency inside one feature, and the abort is **log-only**, so replay cannot reproduce the decision
*not* to write (`CSC_001:425-464`, `:462`).
(c) **Partial acceptance** — *"49 LLM classifications + 1 fallback, not 50 fallbacks"* (`TMP_008b:322-367`).
(d) **Approval queue** — an accepted-but-not-yet-effective state (`TMP_008:214`), with a later veto that
**reverses an already-applied decision and cascades backwards** (`:200`).
(e) **No validation at all** — an NPC's utterance *becomes* canon by being spoken (`SPIKE_01:463`).
Add DF05's frozen-in-payload policy (`DF05_001:729-775`) and AIT's explicitly-non-deterministic flavour
(`AIT_001:1327`) and there are **seven**.

### K22 · Two naming grammars, ad-hoc `kind:` strings, and seven words for invalidation

- **Two grammars.** World-substrate uses noun-past-participle: `PlaceBorn`, `EntityBorn`, `LayoutBorn`,
  `SceneLayoutBorn`, `TilemapBorn`, `GeographyBorn`, `PlaceDestroyed`. Travel and the geography-LLM path
  use `Subject:Verb`: `Travel:Initiate`, `Encounter:Resolve`, `Party:Form`, `GEO:CreativeSeedExtension`,
  `POL:NarrativePoliticalEdit`. No reconciliation. (`PF_001:62`, `MAP_001:90`, `TMP_001:146`,
  `TVL_001:49-52`, `GEO_002:58`.)
- **`LayoutBorn` vs `SceneLayoutBorn`** are two different things one word apart — a map node vs a cell
  interior.
- **No `*Changed` event exists anywhere.** All change is `EVT-T3 Derived, aggregate_type=<x> (field
  delta)` — *the delta kind is the aggregate name, and the field is untyped prose in a Notes column.*
  Only `PlaceDestroyed` is named; `PlaceDamaged` and `PlaceRestored` are anonymous field deltas
  (`PF_001:331`, `:462`).
- **Ad-hoc `kind:` strings on EVT-T3 with no enum declared**: `GenerationCompleted`,
  `ChildCellAnchorUpdated`, `BiomeRerolled`, `FullRebootstrap`, and two **English sentences in quotes**
  — `"L3 classification applied"`, `"L4 narration applied"` — in the same slot (`TMP_001:549`, `:650`,
  `:659`, `:668`, `TMP_008:179-181`).
- **Seven words for one invalidation family, none defined**: *invalidate* · *refresh* · *regenerate* ·
  *re-derive* · *reroll* · *recompute* · *cache miss* — and MAP alone adds a **partiality axis**
  nobody else has (`MAP_001:834`).
- **Pause is signalled three ways**: by the *existence of an unresolved row* (`TVL_004:36`, `:394`), by
  a reality field `time_model_mode: paused` (`SPIKE_01:33`), and by an RPC that must run at a specific
  point (`CSC_001:822`). There is no shared notion of *"this process is suspended."*
- **Isomorphic enums invented four times**: `PoliticalSeedMode` / `SettlementSeedMode` /
  `RouteSeedMode`, all `Canonical|Procedural|Hybrid`; each doc says it *"mirrors"* the previous rather
  than sharing it (`GEO_002:119`, `GEO_003:105`, `GEO_004:118`).
- **Discovery/fog-of-war has four names in four docs for one concept, deferred four times** — and
  `MAP_001:794` admits two of the deferrals are the same item filed twice.

### K23 · Cache keys that nothing emits

Scene and narration caches key on `structural_state`, `season` and `fiction_time_bucket`
(`CSC_001:73`, `TMP_008:119`, `MAP_001:418`). But `SPIKE_01`'s calibration set is day/month/year —
**there is no `season_passes`**, no season field on the reality, and `fiction_time_bucket` is **never
given a bucket width**. `structural_state` is a cache key in three documents and owned by one that does
not know it is being used that way. Related: `TMP_008:119` consumes a *"war declared → wartime"*
world-state feed **that nothing in the corpus produces**.

### K24 · Publication is irrevocable, and several features demand that it not be

`TMP_001:536` publishes `TilemapBorn` at pipeline step 4; `:695` requires that a step-5 failure leave
**no `TilemapBorn` at all**. `:632` asserts exactly 85 births; `:668` re-emits a birth for a channel
that already has one. A partial re-derive must emit `ChildCellAnchorUpdated` and explicitly **not**
`TilemapBorn`/`ZonesPlaced` (`:650`). `TMP_002` falls back to grid-only placement and *produces* a
tilemap on convergence failure while `TMP_001:695` says none is produced — **different event streams
for one trigger**. All of this needs commit-scoped emission (a transactional outbox), not a publish
call inside the generator.

---

## PART 4 — WHAT MUST BE DURABLE, PER THE FEATURES' OWN WORDS

Four storage classes are attested, and the corpus is explicit about all four.

### 4.1 Durable because the EVENT LOG IS the memory — features refuse to build their own

- `FAC_001:78` — *"Per EVT-A10: channel event stream **IS** the audit log (no separate
  `faction_event_log` aggregate)."*
- `FF_001:10`, `:265-266` — *"No separate `family_event_log` aggregate per Q5 LOCKED — channel event
  stream IS the audit log."* The concept notes record the **rejected** alternative and why it was
  wanted: *"Replay-deterministic source-of-truth for graph state derivation"*
  (`00_family/00_CONCEPT_NOTES.md:176-182`).
- `REP_001:596` — same clause. But `REP-D15` immediately re-opens it: *"rep history audit trail |
  Separate aggregate **vs event log query** (analytics over rep changes)"* (`:572`).
- `WA_003:739` — the audit log is the recovery mechanism of last resort: *"reconciliation tooling can
  replay the missing audit from the EVT-T8 AdminAction event log via `correlation_event_id` lookup."*
- `PLT_001:373` — *"revocation deletes the `coauthor_grant` row. **History is in `forge_audit_log`
  only.**"*
- `PL_001b:292-303` — the operator's debugging query is a raw SQL scan of `channel_events` filtered on
  `outcome = 'Rejected'`.

### 4.2 Durable because REPLAY must be byte-identical

- `COMB_001:325-327` — *"the same encounter replays byte-identically in damage, target choices,
  spoils and population. **Any one of the four failing localises the defect to exactly one sibling.**"*
- `DF07_001:673-676` — *"on replay, if the epoch is equal, the recomputed block MUST be byte-identical;
  a mismatch is `stat.snapshot_epoch_mismatch` and **fails the replay**."*
- `DF05_001:769` — *"read cached `facts` directly … **DO NOT re-LLM-call**."*
- `NPC_002:553` — *"Replay reproduces: same NPCs, same intents, same order, same narration."*
- `DL_001:306` — *"Replaying a V1 daily-life day produces byte-identical state."*
- `TIT_001:475` — *"Cascade is fully deterministic — no RNG V1. Replay determinism preserved."*
- `34_…:296-302` (WSA-T4) — *"Run a scenario twice with different observation schedules. Assert:
  identical final state, and identical `occurred_at` on every event — only `recorded_at` and log order
  may differ. **This is the sharpest single test in the world tier.**"*
- `33_…:114-125` (TRG-T1, the shuffle test) — *"Submit the same triggers to a group in a shuffled
  registration order; assert the committed event stream is byte-identical … it reds on any
  group-internal operation that is secretly order-sensitive."*
- `GEO_001:365`, `:368` — *"Same `(master_seed, creative_seed, generator_pipeline_version)` →
  **bitwise-identical** `world_geometry` aggregate … Replay CI gate verifies: same seed → same
  aggregate **bytes**."*
- `PF_001:340`, `:350` — occupants sorted *"for replay-determinism … ensures multi-PC scenes destroy
  PCs in the same order on replay."* **The sorted vector is literally a workaround: it persists the
  decided order.**
- `CSC_001:331-334` — *"Same `(skeleton, seed, params)` → byte-identical Layer 2 output … **No
  floating-point arithmetic in critical path** … `HashMap` iteration NOT used in critical path."*
  `MAP_001:310`, `:325` — `sin`/`cos` were **withdrawn after shipping**; *"the only contract is
  bit-identical output for the same `n_existing` on every platform and every replay."*
  `TMP_001:581` — wall-clock must never be an algorithm input: *"a timed-out job produces no tilemap,
  never a differently-truncated one."*
- **Identity itself must be replayable** — ids are hash derivations of their causal inputs:
  `JourneyId = blake3(actor_id ‖ route_id ‖ fiction_clock_at_initiate)` (`TVL_001:31`),
  `EncounterId = blake3(journey_id ‖ seed ‖ progress)` (`TVL_004:33`),
  `seed_uid = UUIDv5(reality_id, place_id, slot_id)` (`PF_001:133`).
- `GEO_001:487`, `:530` — *"Replay = base + deltas in order. No destructive regeneration"*, with a CI
  gate proving *"base + deltas at fork-point = child's initial state."*

### 4.3 Durable because a LATER DECISION or a CHRONICLE reads it

- `PROG_001` / `00_progression/00_CONCEPT_NOTES.md:776` — a breakthrough is *"Emitted on tier advance
  for downstream consumers (NPC reaction / quest gate V2 / **narrative beat V1+**)."*
- `NPC_003_desires.md:94` — *"Satisfied desires **REMAIN** in the Vec (not removed) **for forensic /
  canon-history reasons**"* so the LLM can reference past achievements.
- `FF_001:639` — *"refs preserved (lao_ngu still has tieu_thuy in children_actor_ids — **historical**
  for V1+ NPC_002 cascade traversal)."*
- `DL_001:252` (DL-D8) — *"Whatever the NPC did **is canon and is not rolled back**"* — and `:273` —
  a converted PC carries a `WasPlayerCharacter` marker *"so NPC_002 Chorus can prompt it **with its own
  history**."*
- `DF05_001:614-651` — memories bleed across sessions so *"alice reminds the PC of a promise made last
  week."*
- `ACT_001:342-343` — `recent_event_refs: Vec<EventId>` (LRU ≤5) exists so the LLM can **reference the
  past**; `:345` — `secret_held` exists so a fact can be **revealed later**.
- `EF_001:182` — the frozen location exists for *"where did Lý Minh die?"*.
- `PL_006:234-238` — source tracking exists for *"what made Lý Minh Drunk?"*, selective dispel, and
  replay traceability.
- `WA_002:201` — `world_stability.stage_history` is a chronicle **inside** an aggregate, bounded at 16
  and silently truncating.
- `COMB_004:238-240` — *"`first_kill_only` is a fact about what has already happened within an epoch,
  and **no amount of arithmetic recovers it**."*
- `COMB_005:101-111` — the cleared-camp bit had to be added because *"a player walking out of a cleared
  camp and back in respawned the identical bandits within the same epoch."*
- `WA_006:5` / `DF05_001:931-936` — on death memory is **frozen, not deleted**; *"retention same as
  alive."*
- `DF05_001:904` — the audit of an erasure *"**CANNOT be deleted** (audit-grade integrity for GDPR
  compliance)."*

### 4.4 Ephemeral-but-checkpointed, derived, and deliberately-unrecorded

These are the rows a naive design will get wrong by over-recording.

- **Ephemeral + checkpointed:** `COMB_001:130-134` — *"In-memory + per-round checkpoint
  (replay-recoverable) … not in the canonical event log beyond the lifecycle + round deltas; the
  outcomes (HP/status/KO) commit to the durable aggregates."*
- **Derived, never stored:** `DF07_001:264` — DF7 *"introduces no new aggregate, no new EVT-T\*
  category, and no new event sub-type. **It is a law, not a store.**"* `ABL_001:435-451` — the
  known-ability set is derived live, *"nothing stored, nothing to clean up."* `31_…:116-121` — L4
  derivation *"never writes"*.
- **Deliberately not an event:** `COMB_005:151-153` — *"**A respawn is not an event**; it is the
  passage of fiction time changing the answer to a pure function. Nothing is written, nothing is
  scheduled, nothing can drift."* `COMB_003:83` — *"`ThreatEvent` … **Not a stored event** — a
  resolution-time call."*
- **Deliberately not durable:** `AIT_001:1327` — Untracked flavour *"regenerates with possibly
  different LLM output (acceptable since flavor is presentation only)"*; `AIT_001:1117` — Untracked
  status events *"emitted but discarded … no persistence"*; `DF05_001:944` — on reality close the POV
  distill is *"SKIPPED (cost-saving)"*, i.e. the memory of the final sessions is intentionally lost;
  `WA_003:732` — an expired pending edit's audit entry is *"NOT logged"*.
- **Deliberately not canon:** `SPIKE_01:580`, `:585`, `:406` — *"LLM narration during /travel or /sleep
  is **flavor** unless explicitly marked `emit=true`"*; *"Flavor (LLM dreams, travel encounters) =
  non-canonical, re-generatable each retell. Structural (money −8, location change) = canonical events
  emitted."*
- **Deliberately silent:** `PL_006:252` — `status.dispel_not_present` is a *"silent no-op + audit-log;
  not user-facing reject."* Balanced against `33_…:170` (TRG-L2): a discarded trigger **must** be a
  recorded event, *"it must not be silent."*
- **A whole authoring session that is deliberately not event-sourced:** `GEO_001b_authoring_flow.md:39`,
  `:61` — *"AuthoringSession iterations are BFF-held UX state, **not event-sourced** … The ONLY durable
  record is the final accepted CreativeSeed embedded in `GeographyBorn`"*; rejected drafts evaporate.
  **But its cost is durable** — every LLM call appends to a user cost ledger summed into the authoring
  metadata (`GEO_001b:56`, `:92-93`). *The money is remembered; the reasoning is not.*
- **Dry-run — run every validator and report violations with no writes and no events:**
  `TMP_003:428`, `TMP_004_template_authoring.md:471`.
- **Progress that is streamed outside the event taxonomy entirely:** `GenerationStarted /
  Progress / Completed` ride the channel alongside durable deltas but *"outside the EVT-T\* taxonomy"*
  (`TMP_003:399-404`) — and `GenerationCompleted` exists **both** as a durable delta (`TMP_001:549`)
  **and** as a progress message (`TMP_003:402`).
- **Non-rejecting observability signals, read back across runs:** `tilemap.density_reduced`,
  `tilemap.biome_fallback_used` are INFO-grade, degrade-and-continue, surfaced to an author **trend**
  dashboard (`TMP_001:496`, `TMP_006:342`) — durable precisely because the value is in the trend.
- **The notable absence:** across the entire tilemap set there is **no chronicle / history / timeline /
  narrative-log demand at all**. Durability there is audit + cache-key + replay, never *narrative
  memory* — even though the narration layer is about a place's character and wants to change when a war
  starts (`TMP_008:119`).

---

## PART 5 — THE FIVE HARDEST DEMANDS UNDER A NAIVE DESIGN

By "naive" I mean the obvious shape: publish a typed message when something changes; subscribers
handle it independently, at-least-once, in arrival order.

### H1 · A threshold that must fire exactly once, from a state that is REVERSIBLE — and whose duplicate is invisible

`HP == 0` is **not** death; it is a 5-round revivable state (`COMB_001:238-239`). A bus that publishes
`PoolReachedZero` mints loot from a state the party then reverses (`COMB_004:91-99`). The real trigger
is *finalisation* — a **timeout on a reversible state** — guarded by an idempotency marker whose
failure mode is invisible: *"because the seed is deterministic, a naive re-roll would produce the same
items again, i.e. **silent duplication that no diff would catch**"* (`COMB_004:300-302`).
**At-least-once delivery, the default of every message bus, is precisely wrong here.** And the same
logical trigger has two different firing rules by tier: the Untracked path has no reversible state and
fires on `group_pool == 0` directly (`COMB_004:95-99`).

### H2 · Same-commit atomicity spanning aggregates owned by different features

*"An item breaks and its modifiers must vanish in the same commit"* is the corpus's own worked example
(`PL_007_item.md:714-725`), and it is one of at least six: `roll_spoils` must produce exactly one
`EntityBorn` **xor** one inventory delta, across EF_001 and RES_001 (`COMB_004:492`); a breakthrough
consumes a pill, advances a tier, resets a value and emits two events all-or-nothing
(`PROG_001:1396-1399`); ability costs are *checked whole, deducted whole, exactly once, and not at all
on any rejected path* (`ABL_001:484-491`); the holder-death cascade moves N bindings **and** clears
equipment **and** bumps `equipment_version` in one batch (`PL_007c:318-329`); succession finalize is a
4-op write across four aggregates including the meta registry (`PLT_002:316-323`); reality bootstrap is
a single `t3_write_multi` across six feature-owned tables with cross-feature validation
(`PL_001b:352-377`). A bus gives eventual consistency, partial application and message loss — the four
states these rules exist to make unrepresentable. And note `PL_005c:311-339` accepts the opposite for
*derived* consequences: *"Side-effect failure does NOT roll back parent … **No automatic compensation
in V1**"*, with a manual operator reconcile. **So the layer must support both, and know which is
which.**

**And the corpus states the contradiction directly, twice.** PF_001 requires the destruction cascade —
whose participants are *subscribers in other features* — to be one Postgres transaction with *"No
intermediate state observable"*, as an acceptance criterion (`PF_001:337`, `:656-661`), while in the
same file those participants *"subscribe"* via a durable, at-least-once, cross-service channel
(`:352`, `:511`). GEO names the missing primitive and defers it (`GEO_003:700`). TVL_005 needs it
across N actors: a rejected party departure must leave *"no journey created and no member's provisions
deducted"* (`TVL_005:458`). **The multi-hop version is worse:** PF mandates its step 3 before step 4
*because* *"dropped items from dying PCs are captured by the cell-resident cascade"* (`PF_001:341-350`)
— so this is not a notification, it is **a sequential fold over a set that each step edits**.

### H3 · Observation as a write, with `occurred_at` ≠ `recorded_at`, in a dependency closure

Every "just look at the world" call is potentially a write: `ObservationAdvance` commits inside the
observing turn (`TDIL_001:353`), AIT materialisation emits a recorded batch of per-day deltas
including **a breakthrough that "happened" 18 days ago** (`PROG_001:688-734`), and DL says routine
evaluation may run inline on cell activation (`DL_001:285`). Three things break a bus at once:
(i) the event's canonical time is **not** its delivery time — it must carry the crossing's fiction-time
(`34_…:263-270`); (ii) the state is a function of *when someone looked*, and the corpus's sharpest test
forbids that from changing outcomes (`34_…:272-302`); (iii) laziness is sound only for a
**self-contained** trajectory — *"Village A collapses ⇒ refugees reach B, a trade route dies, land
falls vacant … the closure can span the map"* (`34_…:239-248`). Cutting that closure is a **correctness
requirement**, not a scheduler nicety.

### H4 · A single death fanning out to five feature-owned graphs where the ORDER is semantic, not incidental

See K5. Two concrete inversions, both named in the corpus: if `MarkDeceased` (`FF_001:98`) lands after
the succession cascade's `is_actor_alive(heir)` check (`TIT_001:411-418`), **a dead heir inherits**;
if the EF_001 drop cascade (`EF_001:481`) runs before `SeverBinding` (`ABL_001:201-208`,
`COMB_004:686-706`), the item severance was meant to transfer is already on the floor and inside
somebody else's `SpoilsClaim`. Add that three features each claim the death→opinion cascade
(`WA_006:374`, `FF_001:571`, `FAC_001:603`) with no de-duplication, that reputation must **fan out
across the faction graph with attenuation, a depth bound and a visited-set carried across hops**
(`REP_001:303`, `:430-434` — on a bus each hop is an independent message with no shared visited set, so
`A hostile B, B hostile A` loops forever), and that TIT's cascade **reads FF while FF is being updated
by the same death**.

### H5 · Consequences that must be HELD — deferred to a boundary, to another machine's completion, or to a human

A bus delivers now. These demand otherwise, and each names a specific bug for delivering early:

- **To the next round boundary** — mid-round equipment/progression/status changes must not alter that
  round's damage (`COMB_001:322-324`); mid-action refresh is **forbidden** (`DF07_001:671-672`).
- **Until another state machine finishes** — an aggro that fires during an active session is *held*,
  not joined (`COMB_005:339-354`); population is never re-sampled while a session is active (`:507`).
- **To the next PC turn** — a second-order NPC reaction is suppressed by the depth-1 cap but must
<!-- doc-language-gate: ok -- genre terminology and cited corpus spans. CLAUDE.md allows non-English where the text IS the subject matter: domain terms with no English equivalent (glossed in English on first use) and spans quoted from the corpus. The exposition around them is English. -->
  **resurface**, not be dropped: *"on my next turn, I see Du sĩ glare back"* (`NPC_002:314-322`).
- **To a human** — a Tier1 Forge edit becomes a pending intention with a 5-minute TTL requiring a
  second approver (`WA_003:304-312`); a succession waits 7 fiction-agnostic days in cooldown and
  finalises because *nothing happened* (`PLT_002:312`).
- **Retried once, then dropped with an expiry** — failed Chorus reactions accumulate as a bounded,
  prioritised, expiring reaction debt (`NPC_002:376`).
- **Never automatically** — *"Auto-cascade is dangerous during prototype"* (`WA_002:429-433`).

This is a **hold-and-apply-at-boundary queue with per-place suppression, a fiction-time horizon and a
human gate** — structurally the opposite of publish-on-change.

### Runners-up, any of which could displace one of the five

- **Un-saying a thing other actors already remember.** `Forge:AnonymizePcInSessions` rewrites a PC's
  name **inside other actors' memories** (`DF05_001:894`), purge deletes facts, regen replaces LLM
  output — while the audit of the operation is undeletable (`:904`). And the world-tier version is
  stranger still: a shipping generator **writes synthetic deltas into every pre-existing reality's
  audit log** to retro-enforce a new invariant, idempotently, in cohorts (`GEO_004:312-316`) — *the
  system authoring its own history* — while mid-life recomputation is simultaneously **forbidden**
  (`GEO_001:258`).
- **Demands for ABSENCE.** A rejected edit must produce no event and no cascade (`TMP_001:677`); a
  failed generation must leave no birth event — *"a timed-out job produces no tilemap, never a
  differently-truncated one"* (`:581`, `:695`); a partial re-derive must emit one `kind:` and
  explicitly **not** the birth events (`:650`). On a bus, **publication is irrevocable**; this needs
  commit-scoped emission, not a publish call inside the producer.
- **Duplicate delivery is a billing event.** ~$0.038/tilemap, ~$3.23/reality initial,
  ~$8.50/reality/year, ~$1.30 per seasonal refresh across 85 tilemaps (`TMP_008:137-145`), plus two
  LLM calls per encounter per journey (`TVL_004:555`). At-least-once delivery, a retry storm, or an
  over-eager invalidation cascade converts a bus-reliability property into money. **Idempotency here
  is not hygiene; it is the cost model.**
- **Fan-out size is a function of DURATION, not of the action.** `/wait 3 years` emits ~1095
  `day_passes` + 36 `month_passes` + 3 `year_passes` (`SPIKE_01:510`). Any subscriber doing real work
  per day-boundary — NPC routines, resource generators, decay — turns one player command into
  thousands of cascading handlers inside a single turn.
- **Two sessions observing one world at different fiction-clocks.** `SPIKE_01:584` asserts, untested,
  that *"real fiction_ts advances globally"* while `:317` pauses the reality at zero players. These are
  incompatible the moment two sessions exist: if one player's 23-day travel advances a global clock,
  the other is carried forward without consent; if it does not, the clock is not global. Deferred as
  MV12-D9 (`:634`) — and TVL_005's party lockstep guarantee (`TVL_005:38`, `:490`) is built on top of
  the unresolved model.

---

## COVERAGE

**Fully covered:** `00_entity` · `00_progression` · `00_resource` · `00_actor` · `00_faction` ·
`00_family` · `00_reputation` · `00_titles` · `00_identity` · `04_play_loop` (all 10 files) ·
`05_npc_systems` · `06_pc_systems` · `12_daily_life` · `16_ai_tier` · `17_time_dilation` ·
`18_combat` (all 7) · `19_ability` · `02_world_authoring` · `10_platform_business` ·
`DF/DF05_session_group_chat` · `DF/DF07_pc_stats` · `03_player_onboarding` · `_spikes/SPIKE_01` ·
`_spikes/SPIKE_02` · `docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md` §2.6, §28, §29 · docs 26/29/31/32/33/34/35
· `_boundaries/01`, `_boundaries/03`, `19_reconciliation_register.md`.

**Empty stubs — no features designed, namespace reservations only** (verified by `ls` + `wc -l`):
`07_social/` (45-line index, *"No features designed yet"*) · `08_narrative_canon/` (36) ·
`09_emergent/` (37) · `11_cross_cutting/` (37). Each names kernel machinery a causality layer will
have to serve — `08:23` L3→L2 canonization + *"M4 propagation"*; `09:22-25` snapshot fork + cascading
read, 9-state reality lifecycle, *"6-state closure machine, 120-day floor"*, severance/orphan worlds;
`07:33` `session.membership_changed` + `presence.update` — but demand nothing directly.

**Reservation notes only, no design:** `13_quests/` · `14_crafting/` · `15_organization/` (each an
index + a `00_V2_RESERVATION.md` with an explicit "do not design here"). `13_quests` nonetheless
**reserves live event hooks** (`Scheduled:QuestTrigger`, `QuestOutcome`, `Scheduled:QuestAdvance` —
`13_quests/00_V2_RESERVATION.md:33-35`), i.e. the *shape* is pre-committed before the mechanism exists.

**Also fully covered:** `00_place` · `00_map` · `00_cell_scene` · `00_travel` (all 5) · `00_geography`
(all 5) · `00_tilemap` (TMP_001/003/005/006/007/008/008b in full; TMP_002/004/009 grep-skimmed for
causality terms and read around every hit) · `_spikes/SPIKE_03`.

**Not covered (deliberately):** `docs/03_planning/LLM_MMO_RPG/07_event_model/` — assigned to a sibling
agent, so **every EVT-T\* claim in this report is as the consuming feature asserts it, not as the event
model defines it**. `_spikes/SPIKE_04_geo_procgen_validation.md` and
`00_identity/_research_character_systems_market_survey.md` were not opened (no causality demands found
on a keyword sweep). `_boundaries/99_changelog.md` (4273 lines) was not read.
