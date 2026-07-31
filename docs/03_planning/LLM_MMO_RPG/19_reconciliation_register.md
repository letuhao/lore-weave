# 19 — Reconciliation Register
<!-- design-lint: ok prefix ML — `ML-1..ML-7` are the Multilingual / Anti-Language-Bias rules, owned by docs/standards/multilingual.md on the PLATFORM track. Cited here, not redefined; registering `ML` in this track's id catalog would claim another track's namespace. -->

> **Status:** OPEN — created 2026-07-26. **This is a work register, not a design doc.**
> **Prefix:** `REC-*` (registered 2026-07-26).
>
> **Why it exists.** A verification sweep on 2026-07-26 produced **~150 findings** across four
> sources. They existed only in a session transcript, which by the repo's own rule means they did not
> exist. This file is the durable index. **Nothing here is fixed until its row says so.**
>
> | Source | Findings | Recorded as |
> |---|---|---|
> | DP locked-spec verification of doc `17` | ~16 | banner in [`17`](17_game_data_architecture.md) |
> | `07_event_model` audit of docs `14`/`15`/`16`/`18` | ~20 | banners in [`16`](16_ruleset_loader_and_registry.md), [`18`](18_reality_bootstrap.md) |
> | `02_storage` corpus sweep | ~75 (30 HIGH) | **AUD-F16** + banner in [`02_storage/_index.md`](02_storage/_index.md) |
> | feature-layer cross-document hunt | 48 (13 CRITICAL) | **AUD-F17** |
>
> **The finding count is misleading.** After dedupe they collapse to **~40 root decisions**, because
> several fixes resolve four findings at once. Work the roots, not the rows.

---

## 1. How to use this

Each row is `REC-nn`, with a **type** that determines who can close it:

| Type | Meaning | Who closes |
|---|---|---|
| **EDIT** | The correct answer is known; someone types it | any agent, no gate |
| **LOCK** | EDIT, but the file is `_boundaries/` or CANDIDATE-LOCK | needs a lock cycle |
| **DECISION** | Two defensible answers with different scope cost | **PO** |
| **AMEND** | Changes a LOCKED axiom (`DP-*`, `EVT-*`) | owning-track sign-off |

**Do not batch a DECISION with an EDIT.** Nine of the 13 CRITICALs exist because someone resolved a
scope question inside a feature doc without the other side agreeing.

---

## 2. Priority 0 — the game cannot run

Four findings where the V1 design is not merely inconsistent but **non-functional**. Everything else
waits on these.

### REC-01 · No generated enemy can attack · **DECISION** · AIT_001
`AUD-F17 #1`. AIT-V1 rejects `Strike` for `Minor` **and** `Untracked` unconditionally
(`ai_tier.action_forbidden_for_tier`, `ai_tier.untracked_cannot_initiate`), and every hostile
COMB_005 spawns is one of those by default. The whole encounter layer is unresolvable.
**Decision:** carve out engine-resolved combat from the tier action-gate — the gate exists to stop
*LLM-driven* action from cheap tiers, and an `EngineDriver` bulk resolve is not that. Requires
**AIT-D18 promoted to V1**.

### REC-02 · No second player can onboard · **DECISION** · PCS_001 + PO_001
`AUD-F17 #6`. PCS-A9 counts `pc_user_binding` rows **per reality** and rejects >1; PO_001 Mode A
needs ~5 canonical PCs bindable to different users, and silently reinterprets the cap as per-user.
Validators C13/C34 assert the two "match" while stating different constraints.
**Decision:** pull **PCS-D3 into V1** as a per-`(reality, user)` cap — or PO_001 loses Mode A. The
first is almost certainly right (a single-PC MMO is not the product), but it is a scope change to a
CANDIDATE-LOCK foundation and is not PO_001's to take unilaterally.

### REC-03 · Every combat/ability outcome is contract-illegal · **LOCK** · PL_005b §7
`AUD-F17 #10`. The OutputDecl allowlist is closed (*"aggregate_type not in this table = forbidden"*)
and omits `vital_pool` and `actor_status`; its HP row points at `pc_stats_v1_stub`, which nobody
writes. COMB_001 and ABL_001 both route outcomes there. All three docs CANDIDATE-LOCK.
**Fix:** replace the stub rows with `vital_pool` (RES_001) and `actor_status` (PL_006). The answer is
not in doubt; the lock cycle is.

### REC-04 · Clocks deadlock in unattended channels · **DECISION** · TDIL_001
`AUD-F17 #3` (root), `#2`, `#29`, `#30`. TDIL_001's *"idle = frozen"* plus a V1 advance-source list
where **every source is itself gated on an advance** yields permanent deadlock in any PC-free channel.
Blast radius is severe and non-obvious:
- **`#2`** AIT materialization computes `elapsed = 0` regardless of absence length — the Tây Du Ký
  365× case AIT_001 cites as its motivating example accrues **nothing**.
- **`#29`** DL_001's 1-fiction-hour sweep and 30-fiction-day conversion can never fire, so AC-DL-3
  (*"a cold cell consumes zero CPU"*) and AC-DL-8/13 are mutually unsatisfiable.
- **`#30`** EF_001's 14-fiction-day NPC cold-decay — which exists **specifically** to unload
  player-free cells — can only fire in cells that are not player-free.

**Decision:** TDIL_001 supplies a **non-actor clock-advance source**. Recommended: *lazy advance on
observation* — an observer entering a channel advances its clock to the observation point before
reading. That keeps "zero background compute" (DL-A1) true, makes `elapsed` non-zero, and is the same
quantum-observation move PROG_001 §7 and AIT_001 already use for NPC state. Alternatives (a real
scheduler tick; wall-clock derivation) both break DL-A1.

---

## 3. Priority 1 — V1 depends on someone else's V1+

**The single largest class: 9 of 13 CRITICALs.** Each is one doc shipping a V1 feature on another
doc's deferred item. Every one is a **DECISION** — promote the dependency, or demote the dependent —
and **neither doc can take it alone.**

| REC | Finding | V1 side | V1+ side it needs | Recommended |
|---|---|---|---|---|
| **REC-05** | `#7` | TIT_001 succession cascade (V1 active) | FAC_001 runtime `ChangeRole` / `SetCurrentHead` (V1+, FAC-D11 open) | promote FAC_001 — the cascade is TIT_001's flagship and FAC-D6 was already marked *"resolved by TIT_001 V1"* without lifting FAC_001's restriction |
| **REC-06** | `#8` | TIT_001 succession trigger = NPC death | NPC mortality state (PCS-A1: **PCs only V1**) + NPC death itself (EF_001: **V1+30d**) | **demote** — titles are NPC-held, so the trigger cannot fire at all. Re-base on EF_001 lifecycle `Destroyed` and mark V1+30d. TIT_001's claim to close the WA_006 gap "V1 full" is unreachable |
| **REC-07** | `#11` | ABL_001 out-of-combat abilities | PL_005b admitting `InstrumentRef::Ability` (rejected on **all five** kinds) | promote — ABL-Q2 justifies the whole namespace on *"two V1 callers"* and the second does not exist |
| **REC-08** | `#21` | ABL_001 out-of-combat `StatusApply` | PL_006 `Scheduled:StatusExpire` (V1+30d) | **demote** — COMB_001 already fixed this inside the encounter and handed the out-of-combat case to a scheduler that does not exist. A V1 `duration_rounds: 3` out of combat is currently permanent |
| **REC-09** | `#23` | DF05_001 per-actor POV distill (defining V1 mechanism) | ACT-A6 populating `actor_session_memory` for **PCs** (V1+) | promote ACT-A6 to "all session participants, V1" — and note ACT_001's header simultaneously claims the DF05 closure made *"NO change to ACT_001 schema or invariants"* |
| **REC-10** | `#27` | COMB_004 §16 `BindTier`/`SoulBound`, SPO-Q10..Q14 LOCKED, 6 unqualified V1 ACs | PL_007 `bound_to`, marked *"V1: **ALWAYS None** … Reservation only"* | **demote** COMB_004 §16 to V1+ alongside ITM-D5. Also lifecycle-impossible: §16.3 keeps a soulbound item `HeldBy` a dead actor, against ITM-C4 and PL_007 §8.5 |
| **REC-11** | `#28` | COMB_004 bulk "take spoils" (SPO-V5, AC-SPO-10) | PL_007b bulk partial-fill, gated on *"that module's"* | circular delegation — **COMB_004 defines the V1 take action**, or AC-SPO-10 → V1+30d. PL_007's only V1 acquisition is single-instance `Item:PickUp` |
| **REC-12** | `#13` | COMB_005 engagement-promotion + `demote_after_days`; DL_001 hidden-PC → Major | AIT_001: *"V1: **NO** auto-promotion"*, *"Demotion V1 — **DISABLED**"* | pairs with **REC-01**; if AIT-D18 lands, take AIT-D1/D2 with it. `demote_after_days` appears in no file but COMB_005 |
| **REC-13** | `#34` | PO_001 emits `ActorBorn`/`EntityBorn` per signup, player JWT | both are **bootstrap-only** producers (ACT_001: *"RealityBootstrapper role only"*) | route PO_001 through Forge EVT-T8, **or** ACT_001+EF_001 add a runtime producer claim. Currently a player-scoped JWT mutates `canonical_actors` |

---

## 4. Priority 1 — the onboarding chain (PO_001)

PO_001 carries **five** findings and is the second-worst-affected document after AIT_001.

- **REC-14** `#4` · **DECISION** — `actor_user_session.session_id` is a non-`Option` DF5 `SessionId`,
  but DF5 derives that id from a **PC anchor** (`anchor_pc_id` MUST be `kind=Pc`) and the PC does not
  exist until onboarding completes. PO_001's 17-step cascade has no session-creation step. *Fix:*
  rename to a login-session type distinct from DF5, or make it `Option`.
- **REC-15** `#5` · **EDIT** — PO_001's cascade order (`Forge:RegisterPc` → `ActorBorn` →
  `EntityBorn`) is **inverted at both hops**. PCS_001 and ACT_001 agree with each other
  (`EntityBorn → ActorBorn → PcRegistered`); only PO_001 disagrees. `pc_user_binding`'s FK into
  `actor_core` is written before `actor_core` exists.
- **REC-02** `#6` — the PC cap (above).
- **REC-13** `#34` — bootstrap-only producers (above).
- **REC-16** `#36` · **DECISION** — `session_participation` is declared by both PO_001 and DF05_001
  at the same tier, scope, sparsity and composite key; and the same fact lives in **four** places
  (`ACT_001.current_session_id`, `PCS_001.current_session`, PO_001's row, DF5's) with no writer
  ordering. PCS_001 defines its own field twice with two different meanings, so a DF5 close-cascade
  would log the player out.

---

## 5. Priority 2 — ordering, and the five-way disagreement

### REC-17 · Canonical seed ordering · **LOCK** · one edit fixes four findings
`AUD-F17 #15` `#16` `#38`, `RBS-F1`. **PL_001b §16.2, ACT_001, PCS_001, REP_001 and GEO_001 §11 give
five different orderings, all citing §16.2 as authority.** REP_001's copy omits `ActorBorn` entirely;
three docs name a `MapLayoutBorn` that MAP_001 does not own.

**Fix, in order:**
1. **PF_001 §2.5**: *"emitted alongside"* → *"strictly precedes"*. **This single edit resolves
   RBS-F1, `#16` (CSC_001's zero-width scene-layout window) and `#38` (duplicate `MemberJoined`
   registered to two owners).**
2. **PL_001b §16.2** restated as the single normative list.
3. ACT_001, PCS_001, REP_001, GEO_001 §11 corrected to it; `MapLayoutBorn` → `LayoutBorn`.
4. Adopt [`18` §3.2](18_reality_bootstrap.md)'s 8-phase DAG as the expansion of §16.2.

### REC-18 · Encounter id / grid cycle · **EDIT** · COMB_001
`#17`. The arena seeds on `blake3(reality_id, encounter_id)` at formation step 2, but `encounter_id`
belongs to the `CombatSession` created at step 5, which needs the grid from step 2. *Fix:* state that
the id is allocated at step 1 (COMB_001's preference) rather than reseeding.

### REC-19 · Mutually-referencing connections un-bootstrappable · **EDIT** · MAP_001 + PF_001
`#37`. Both validate `to_channel` / connection targets **at write time**, but bootstrap materialises
rows one decl at a time — so in any mutually-referencing pair (both docs' own canonical examples)
the first written references a row that does not exist. *Fix:* state end-of-batch referential
evaluation. Note this is the same class as RLS-A9 and `18` §3.2.

---

## 6. Priority 2 — phantom references

Three places where a doc builds on something that is not there. These are cheap to fix and alarming
to have found.

- **REC-20** `#44` · **LOCK** — **`AIT_001 §7.5` does not exist.** It is the Tracked-NPC
  materialization formula that REC-04 turns on. AIT_001's own status block and TDIL_001 §17.3 both
  record it as revised. **A lock cycle recorded an edit that was never made** — the most serious
  process finding of the day. *Fix:* write §7.5; TDIL_001 re-verifies before its lock stands.
- **REC-21** `#45` · **EDIT** — **`combat_reaction_table` has zero repo-wide hits.** COMB_001,
  COMB_003 (THR-V2), ABL_001 and AIT_001 §7.2 all build V1 validators or drivers on it. AIT_001's
  nearest real field is `reaction_table: Vec<ReactionDecl>` with no combat variants in V1.
- **REC-22** `#47` · **EDIT** — COMB_001 `§12.1`'s `round_fiction_seconds`, which REC-08's conversion
  needs, exists only in `00_CONCEPT_NOTES.md`, which COMB_001 marks non-normative. *Fix:* promote it
  into COMB_001 §7's manifest list.

---

## 7. Priority 2 — determinism

All three break a replay contract another doc relies on.

- **REC-23** · **EDIT** · TMP_001 — force-directed layout terminates on `min(1000 iterations, **5 s
  wall-clock**)` while TMP-A4 / AC-TMP-2 require byte-identical output from the same seed.
  *(Note: RLS-D13 already moved these wall-clock knobs out of the Ruleset for the same reason.)*
- **REC-24** · **EDIT** · MAP_001 §5 — lazy-cell position uses `f32` `cos`/`sin`, the exact pattern
  GEO_001 §5 and CSC_001 §5.2 both ban.
- **REC-25** · **EDIT** · PROG_001 — five `f32` fields (`rate_per_train_unit`, `difficulty_factor`,
  `training_rate_factor`, `min_damage_factor`, `max_damage_factor`) contradict DF7-A4 and TDIL-A9.
  Already filed as `RLS-A8`.

---

## 8. Priority 3 — ownership, registration, counts

- **REC-26** `#24` · **LOCK** — NPC_001's header transfers three aggregates to ACT_001, but its
  **normative body, its `dp::t2_write` calls and its JWT write claims** still grant world-service
  ownership. Two owners for `npc`, `npc_session_memory`, `npc_pc_relationship_projection`.
- **REC-27** `#46` · **EDIT** — `ability.*` is registered at **three different sizes** (ABL_001 §1
  says 12, its §11 lists 14, `02_extension_contracts` §1.4 says 14, COMB_001 says 12), and **two
  different validators are both labelled `ABL-V8`** under a header declaring `ABL-V*` stable.
- **REC-28** · **LOCK** — `commit-service` has **no ownership-matrix row at all**, and there is no
  EVT-A4 producer role for `sim-core`/the island despite SC-A4 making it the authoritative writer.
- **REC-29** · **LOCK** — `RulesetEpochActivated` (RLS-A14) needs registration in
  `02_extension_contracts` **§4** *and* the ownership matrix. **Blocked by a knot doc `16` created
  itself:** EVT-A11 demands one owning *feature*, and RLS-D21 made `16` a platform doc with no
  feature identity. *Decision:* WA_003 Forge owns it (it already owns admin rule-edits), or the
  matrix accepts a platform-doc owner.
- **REC-30** `#42` · **EDIT** — GEO-D5 and MAP-D6 give two different V1+ derivation sources for
  `map_layout.position` with no precedence rule, and MAP_001 carries neither the cross-reference nor
  the row GEO_001 claims it has. If GEO-D5 activates, TMP-A6's premise goes false with no amendment.

---

## 9. Priority 3 — validator pipeline

- **REC-31** `#19` · **LOCK** · `_boundaries/03_validator_pipeline_slots.md` — PL_005b runs
  world-rule at 7 and canon-drift at 8; the locked doc has canon-drift at 7, causal-ref at 8,
  world-rule at **9**. Canon-drift can only compare narration against a `ResolutionResult` if the
  derivation stage already ran — true in PL_005b's order, **false in the locked one**. The boundary's
  own tie-break would make ABL_001 §8.3 and AC-COMB-10 unsatisfiable. *Fix: the boundary doc adopts
  world-rule-before-canon-drift and renumbers.*
- **REC-32** `#18` · **EDIT** · ABL_001 — ABL-V4 claims a stage owned by `05_llm_safety` and runs
  1.5 stages **before** the EF_001 lifecycle verdict its own dead-target predicate consumes, under a
  pipeline that forbids skips. `ability.*` has no row in the stage→namespace matrix.
- **REC-33** `#39` · **EDIT** · IDF_002 — uses a stage numbering that maps its world-rule check onto
  `05_llm_safety`'s canon-drift slot, so `language.*` rejects fire at a slot registered to
  `canon_drift.*`.

---

## 10. Priority 3 — remaining feature contradictions

| REC | Finding | Summary | Type |
|---|---|---|---|
| **REC-34** | `#9` | TVL_001 reads/writes `vital_pool.hunger` / `.thirst`; `VitalKind` is engine-fixed `{Hp, Stamina, Mana}`. Hunger is a PL_006 `StatusFlag`; thirst does not exist (RES-D5). The HIGH-4 fix landed in prose but not in the struct, cascade or ACs — **8 residual sites** | EDIT |
| **REC-35** | `#43` | TVL_001 cites `StackPolicy::Replace` (not a variant; actual is `ReplaceIfHigher`, and the stated behaviour is its negation) and "Tier 0" magnitude, outside PL_006's validated `1..=10` — would reject at Stage 0 | EDIT |
| **REC-36** | `#14` | TIT_001's `SuccessionRule::Eldest` has **no age or birth-order data anywhere** in the actor substrate; TDIL `body_clock` defaults to 0 for all canonical actors. FF_001 and TIT_001 also disagree on what `Eldest` reads | DECISION — add a birth-order key, or drop `Eldest` to V1+ |
| **REC-37** | `#20` | COMB_001 composes a **flat 50%** disparity cap with a WA_001 Lex axiom, but V1 axioms are **boolean** — *"no budgets, no tiers"*, V2+ adds `AllowedWithBudget`. `lex_check` returns no value to compose | DECISION |
| **REC-38** | `#12` | COMB_005 spawning is a pure function with **no stored kill record**, and AIT_001 discards Untracked on PC exit — so walking out and back respawns the identical bandits. AC-SPN-4 unsatisfiable; COMB_004's `first_kill_only` anti-farm rests on it | DECISION — one stored cleared-flag, or drop AC-SPN-4 |
| **REC-39** | `#26` | COMB_005 says spawn-group members carry *"zero per-actor state"*; AIT_001 §5.3 generates per-slot ids, names, sampled stats and a runtime cache. Two stat sources with no arbitration (DF07 `stat_archetypes` vs AIT `progression_kinds`); `HostileSpawnDecl` carries an `ActorClassRef` the generator cannot consume | EDIT (both) |
| **REC-40** | `#25` | NPC_002's Chorus tier filter is claimed *"preserved"* but its body has no tier check and takes `&Npc`, which Untracked never has. AIT_001 §7.3's guard dereferences `.tracking_tier` before concluding the row is absent | EDIT (both) |
| **REC-41** | `#35` | TDIL_001 asserts promotion "crystallizes" `actor_clocks`; AIT_001 §5.6 writes only `npc_core` + `actor_progression`, so a promoted NPC has no clocks — which TDIL §6.1 immediately requires. AIT §5.6 also still writes the field TDIL §17.1 says it replaced | EDIT (AIT_001) |
| **REC-42** | `#32` | RES-Q1 is answered **twice, incompatibly, in one file** — §4.1 *"derived, not declared per class"* vs §16 *"deferred to consumers, per-actor-class declarations"*; §12.6 instructs PCS_001 to take a write path DF7-A2 forbids | EDIT (RES_001) |
| **REC-43** | `#33` | RES_001's NPC-peasant 50/50 default is **unreachable by any DF07 path** — a Tracked NPC has `actor_progression`, so it resolves through the reality-global `MaxHp` base and gets the PC's 100 | EDIT |
| **REC-44** | `#40` | WA_001 assigns the ability-cost axis (`EnergyKind`) to a future doc; ABL_001 ships it V1 against RES_001 vitals. A reality may legally set `energy_system: Qi` while every ability costs `Mana` | EDIT |
| **REC-45** | `#41` | PL_005b makes item×reality the **CRITICAL primary Lex reject path**; ABL_001 rules that axis *"backwards"*; WA_001 has no item concept to gate on | EDIT (PL_005b) |
| **REC-46** | `#48` | COMB_004 §4.2 defines `SpawnGroupLootState` (two stored fields) while its own §10 says *"no stored counter"* and COMB_005 grants exactly one | EDIT (both) |
| **REC-47** | `#31` | DL_001's `/hide` pauses `body_clock` citing TDIL-D5 as *"precedent"*; TDIL-D5 is a **deferral**, and per-clock pausing is what TDIL V1 explicitly forbids | EDIT (DL_001) |

---

## 11. Priority 2 — `02_storage` corpus (AUD-F16) — ✅ **NOTED-COMPLETE 2026-07-26**

> **All 33 remaining files carry tailored superseding notes as of 2026-07-26 evening** (agent pass;
> every claimed root verified against file content before stamping — zero mismatches). The corpus is
> now safe to read: every stale file declares what supersedes it and where the current design lives.
> **What "closed" does NOT mean here:** the underlying rewrites (Rust codegen target for R03, the
> meta-library Rust client for C03, island-aware runbooks for SR03/SR07, the S08 GDPR gap for island
> memory + Class A checkpoints) are real follow-on work owned by the storage track — the notes make
> them *visible*, not done. The S08 GDPR item deserves a DEFERRED row of its own.

~75 claims, ~30 HIGH, **10 root causes** — banner already applied to
[`02_storage/_index.md`](02_storage/_index.md). This is a **storage-track pass**, not a doc edit, and
the roots are listed there. Sequenced separately because it touches a different track.

**One item is a blocker for `18` and must not wait:**

### REC-48 · `C05` CAS map rejects the bootstrap lifecycle · **EDIT** · `C05_lifecycle_cas.md`
§12Q.6's valid-transition map has **no `provisioning`, `seeding` or `failed` states**. [`18`](18_reality_bootstrap.md)
§1 declares the lifecycle *"CAS-protected per §12Q"*. An implementer of `AttemptStateTransition()`
from the actual map would reject the entire bootstrap sequence.

---

## 12. My own docs (16 / 17 / 18)

Full itemisation is in each doc's banner. Summary:

| REC | Doc | Items | Nature |
|---|---|---|---|
| **REC-49** | [`17`](17_game_data_architecture.md) | ~12 | `ReadFreshness` is prohibited by DP-X1; GDA-A6 deletes the locked `t1_read` primitive; GDA-Q1 false (DP-Ch33 locks ≤2 s); GDA-D8 rewrites a locked transition; B1 omits the mandatory CP tier-policy fetch; 4 DP-R violations. **Audit half stands; designed flows do not.** |
| **REC-50** | [`18`](18_reality_bootstrap.md) | ~8 | `*Born` are **EVT-T5, not T4** (inherited from CS-D9's own error); EVT-T5 **requires causal-refs** and phase 1 has no parent — a hard blocker; `ArchiveReplay` violates EVT-A3/A10; RBS-A3 is a DP-A16 **amendment request**, not a decision |
| **REC-51** | [`16`](16_ruleset_loader_and_registry.md) | ~6 | Conclusions **confirmed correct**; integration missing — RLS-A13 needs EVT-L18/EVT-A10 amendments, RLS-A12 needs an EVT-A9 carve-out, and the 7-step envelope-bump procedure was omitted entirely |
| **REC-52** | `15` (not mine) | 4 | §3's origin table contradicts §7b.2; CS-D2 vs EVT-A5; CS-D9's *"every path"* is not in EVT-V5; CS-D10 shared stream vs EVT-L4 causes cross-island head-of-line blocking |

### REC-53 · EVT amendments · **AMEND** · event-model track
The one genuinely axiom-level bundle: EVT-L18 replay-input list · EVT-A10 *"sufficient"* qualifier ·
EVT-A9 carve-out for `&D::Rules` · envelope `event_schema_version` **1 → 2** with a permanent upcaster
and an explicit legacy sentinel · a seed-origin **causal-ref exemption** · a **restore/import**
concept (none exists) · EVT-G2 trigger kind for bootstrap. Also EVT-G2's own pre-existing defect:
it cites `RealityActivated` / `ChannelDissolved` as trigger sub-types absent from EVT-T4's closed set.

---

## 11a. Priority 1 — the LLM decision path (fifth sweep, 2026-07-26 evening)

A dedicated end-to-end audit of the money path (docs 11 · 13 · 14 · 15 · 07 · S09 vs the two CLAUDE.md
platform invariants). **Verdict: the invariants are acknowledged exactly once (AGT-A4/D4) and inherited
once (foundation I2); everywhere the path is actually mechanized, provider-registry and the MCP tool
surface vanish, replaced by an unnamed "host" and a bus.** `contracts/agent/` confirmed absent on disk.

| REC | Sev | Finding | Type |
|---|---|---|---|
| **REC-54** | **HIGH — week one** | **The commit-service-host → LlmDriver dispatch hop has no named transport or service.** `14` §11: the Llm handle resolves *"via the host"*; post-CS-A5 the host is commit-service (Rust, writer node) — and **no decision-path doc names provider-registry-service**. The prompt-to-provider call for an NPC decision is **unowned**. First line of S5 code. | DECISION |
| **REC-55** | **HIGH — week one** | **Decision return path doubly specified, and the MCP landing zone does not exist.** AGT-A2/A4 site MCP tools on *"combat-service, interaction-service"* — **neither exists** in the service map or language-rule.yaml — vs the EVT-T6 proposal bus (`07`/`15`). CS-A1 makes commit-service a non-addressable *role*, so MCP-first compliance currently rests on an unbuilt bridge. Pick one path. | DECISION |
| **REC-56** | **HIGH — week one** | **LlmDriver host language triple-contradiction:** `11` §8 *"python/roleplay"* vs `language-rule.yaml:31` `roleplay-service: rust` (**lint-ENFORCED**) vs `03_service_map.md:31` *"Go"*; `07`'s *"Python LLM-Originator"* + DP-A6 assume Python. A scaffold fails the lint or the docs. | DECISION |
| **REC-57** | MED-HIGH | `contracts/agent/` **doesn't exist**; `DecisionHandle` appears once with zero fields and **silently contradicts locked AGT-D1** (`decide → Decision`); `FallbackAction` defined nowhere; fallback content specified for exactly two contexts (*"Defend in combat, silence in dialogue"*) — no registry for movement/trade/social. | EDIT + AMEND (AGT-D1) |
| **REC-58** | MED | **The proposal bus is prefetch-blind.** EVT-L2 has no admitted-but-parked state; a prefetched decision invalidated at execution (`Outcome::Discarded`, SL-D25 calls ≤25% waste *routine*) is inexpressible on a bus whose every non-Validated ending is dead-letter/audit material; EVT-L4's *"commit before next"* predates CS-A3 and cannot be obeyed for a parked proposal. | AMEND (EVT-L2/L4) |
| **REC-59** | MED | **NPC LLM spend has no payer and no unit.** AGT-D5 is a concurrency cap, not a meter; its budget is per-reality/session while `user_cost_ledger` is per-user; PLT-4's BYOK-only free tier leaves *"whose key does a Major NPC burn?"* unanswered anywhere. | DECISION |
| **REC-60** | MED | Decisions ride `intent=npc_reply` (NPC_002) — S09's Intent enum and 12Y.7 budget table have **no decision/tool-selection intent**; `DecisionContext` ↔ `PromptContext` never mapped; `ContextResolver` (GDA-D16) assigned to no host. | EDIT |
| **REC-61** | LOW | `13` §3 labels ai-gateway MCP as the transport for `decide()` dispatch — conflates LLM-invokes-tools (AGT-A4) with host-invokes-driver. | EDIT |
| **REC-62** | LOW | `17` R3 cites *"`15` §10.5"* — that section is in `14`. | EDIT |

---

## 11b. Priority 1 — error taxonomy (sixth sweep, 2026-07-26 evening)

**Nine or ten error families, one fully-specified player path, and no owner of cross-layer mapping
anywhere** — the closest mechanism is quickstart checklist item 6, which pushes DpError→UX onto every
feature individually, which is why PL_001 §9 and PL_005 §9 exist as mutually-unaware local tables.
Of the 8 layers a turn can die at, **the player's view is specified at exactly one** (validator
rejection, EVT-V4 → `RejectReason.user_message`).

| REC | Sev | Finding | Type |
|---|---|---|---|
| **REC-63** | **HIGH** | **The sim-core → player half of CS-D5 is a type-shaped hole.** `DiscardReason`, `Violation` and `Fallback::Notify`'s `Reason` are referenced throughout `14` and **enumerated nowhere**; the discard path has no player rendering, no transport, no copy. S2/S3 implementer invents a whole vocabulary + delivery channel on the spot. | EDIT (`14` owner) |
| **REC-64** | **HIGH** | **No error return channel exists post-pivot.** The specified rejection UX rides the world-service-era gateway-HTTP ack; `15` consumes from a bus and never states how `Rejected` / `Discarded` / DpError reaches the Colyseus WS client. Layers 4 and 5 of the player table are stranded on this. | DECISION |
| **REC-65** | MED-HIGH | **DpError enum drift**: DP-K3 is LOCKED at 21 variants; 5+ docs mint satellites (`CausalRef*` ×4, `ResumeTokenExpired`, `AggregatorStuck`, `ChannelAlreadyDissolved` duplicating `ChannelAlreadyInState`, `OwnershipTransferAlreadyActive`). No rule for which variants may become player-facing rule_ids; single declared bridge is `capability.*`. | AMEND (DP) |
| **REC-66** | MED-HIGH | **`RejectReason` has two incompatible shapes in circulation** — the §1 locked struct `{rule_id, user_message, detail}` vs enum-variant syntax (`RejectReason::WorldRuleViolation{...}`) in PL_001 §7, PL_001b §15, PL_005 §9. A builder cannot tell which is the real type. | EDIT (PL_001 owner) |
| **REC-67** | MED | **Loader/author errors: no namespace, no shape, no channel.** `ruleset.*` absent from §1.4; RLS-D12's *"surfaced to its author"* is prose. (Doc 16's own gap — fold into REC-51.) | EDIT |
| **REC-68** | MED | **Hot-path gate rejections fall between EVT-V4 and nothing** — gates are pre-pipeline and rejection-only; whether a gate reject commits an auditable Rejected event is undefined (EVT-V2's own forbidden `silent_drop` question). | AMEND (EVT-V5) |
| **REC-69** | MED | **Duplicate-detection windows disagree across 4 vocabularies**: 60 s gateway cache vs 5 min sim-core `seen` vs unstated bus — a retry between 60 s and 5 min is a *new turn* to the gateway and a *duplicate* to sim-core. Rate-limit exists in 4 families with no equivalence stated. | DECISION |

---

## 11c. Priority 1 — client wire contract (seventh sweep, 2026-07-26 evening)

Ground truth checked against **code**: `crates/contracts-ws` is chat-era (envelope v1, close codes,
authz — *"ws.ping/pong/refresh/close"* + one `chat.message` fixture); `game-server` is echo-era by its
own comment. **Zero repo hits** for `ruleset_digest`, `resume_token`, first-frame, movement intents,
or turn submission. No frontend game code exists; no Colyseus client dependency.

| REC | Sev | Finding | Type |
|---|---|---|---|
| **REC-70** | **HIGH — blocks first playable** | **No client wire contract exists for anything the game needs.** W0/W1/W2, RTM movement (move-input delta · position patch · snap-back · mode-flip) and turn submission have zero DTOs in design or code — `17` B5 supplies field *lists* keyed to server aggregates, and most of those aggregates have no code either. | design work (new) |
| **REC-71** | **HIGH — blocks first playable** | **Two parallel WS transports, two reconnect mechanisms, no composition rule.** Gateway WS (envelope v1 + `resume_token` catch-up) vs Colyseus (own protocol + `reconnectionToken` + 30 s seat reservation, live today). GDA-A7 makes the room a projection but nothing says **which transport carries W0/W1/W2 and the event stream to the browser.** Until this seam is picked, no client can be written. | DECISION |
| **REC-72** | **HIGH — blocks reconnect** | **Resume-token plurality contradiction**: W0 returns a *single* token; DP-Ch18 specifies **per-channel cursors** (`from_tokens: HashMap<ChannelId, u64>`, cell + up to 5 ancestors). Singular vs map is a wire decision nobody made. | EDIT (`17` B5) |
| **REC-73** | MED-HIGH | **`InventoryDigest` is the wrong artifact class for W1** — ITM-A9 defines it as a ≤29-line *prompt-injection text block*; W1 ships it as the client's inventory. A renderable summary and an LLM digest are different shapes. Ditto *"entity roster with render state"* — "render state" appears exactly once in the repo, in the W1 row itself. | EDIT (`17` B5) |
| **REC-74** | MED | **No client-side state model at all**: no local-store spec, no epoch-switch invalidation, nothing on what survives reconnect beyond stream catch-up; GDA-D6's mandated cross-session digest cache has no storage design and sits against CLAUDE.md's own no-localStorage rule (IndexedDB decision unstated). | design work (new) |
| **REC-75** | MED | **No browser-client versioning story**: envelope v1 hard-rejects with no negotiation; event upcasters stop at service consumers; W0 carries no client version/capability field; no force-upgrade signal. The moment `event_schema_version` 2 lands (REC-53) with any client in the field, this is a live incident. Cheap now: client version in W0 + a stated *"server upcasts to latest before fanout"* rule. | EDIT |
| **REC-76** | LOW-MED | **i18n client contract unstated** — three resolutions coexist (narration pre-resolved · `RejectReason.user_message` ships the whole bundle · W1/W2 locale-sliced), no per-message-class rule, no locale-switch-mid-session story. And **PO_001, the FE-first feature, has no frozen API contract** in `contracts/api/` despite the contract-first rule. | EDIT |

---

## 12a. Closed

**2026-07-26 evening batch — all 11 PO decisions applied** (REC-04 confirmed by the PO as matching
the platform's original lazy-evaluation performance principle):

| REC | Closed | What was done |
|---|---|---|
| **REC-04** | 2026-07-26 | **TDIL_001 §7.1a `ObservationAdvance` (TDIL-A11)**: fourth clock-advance source — observation lazily advances the channel clock against the reality's rate-1.0 baseline (`last_baseline_sync` field), THEN reads. Zero background compute preserved (DL-A1 / B3-D1a literally true); §7.4's O(1) formula now receives non-zero elapsed; deterministic (recorded per SL-A6). Also flagged the §7.4 phantom `AIT_001 §7.5` citation inline (REC-20 remains open — AIT must still write the section). **Unblocks #2/#29/#30 downstream.** |
| **REC-01** | 2026-07-26 | **AIT_001 §9.3 AIT-A16 engine-combat carve-out**: `EngineDriver`/`ScriptDriver` actions inside an active `combat_session` bypass the tier gate — the gate contains *LLM-driven* action (token cost), which an engine bulk-resolve is not. LlmDriver from cheap tiers still rejected. AIT-D18 combat variants → V1. **Generated enemies can attack.** |
| **REC-12** | 2026-07-26 | **AIT_001 §4.4/§4.5 split promotion**: the promotion **mechanism** (incl. `actor_clocks` crystallization — also closing #35's missing clock write) is V1 with exactly two callers (COMB_005 engagement · DL_001 conversion), soft-fail-at-cap queueing; the significance **heuristic** stays V1+30d. Demotion: one V1 path (encounter-promoted Minors, `demote_after_days`, evaluated lazily via TDIL-A11); canonical Tracked permanent. |
| **REC-05** | 2026-07-26 | **FAC_001**: `ChangeRole` + `SetCurrentHead` promoted to V1 as **cascade-only writes** (TIT_001 succession + Forge); free-form membership churn stays V1+ per FAC-D11. §8.11's corpse-head scenario now resolvable. |
| **REC-06** | 2026-07-26 | **TIT_001 §7.1**: NPC-death succession trigger → **V1+30d** re-based on EF_001 lifecycle `Destroyed` (NPCs have no mortality state — PCS-A1). V1 triggers: PC-holder death + Forge. Cascade machinery stays V1. *"V1 full"* claim corrected; AC-TIT-6 re-tagged. |
| **REC-07** | 2026-07-26 | **PL_005b §6.2**: `InstrumentRef::Ability` → ✅ on `Use` (exactly 1, XOR Item), validated by ABL_001's own chain. ABL_001's second V1 caller now exists; closed kind-set preserved. |
| **REC-08** | 2026-07-26 | **ABL_001 §7.3**: out-of-combat duration-bearing `StatusApply` → **V1+30d with `Scheduled:StatusExpire`**; V1 rejects with new `ability.status_needs_combat_v1`. Instant effects unaffected. Conversion contract retained for V1+30d; expiry will evaluate at observation per TDIL-A11. |
| **REC-09** | 2026-07-26 | **ACT_001 ACT-A6 amended**: `actor_session_memory` populates for **all session participants V1** (PCs included) — DF05's defining mechanism required it. The false *"NO change to ACT_001"* closure claim withdrawn explicitly. Schema unchanged. |
| **REC-10** | 2026-07-26 | **COMB_004 §16 Binding Contest → V1+**, activating with PL_007 ITM-D5 (`bound_to` is *"ALWAYS None, reservation only"* V1). Six ACs re-tagged; the §16.3 ITM-C4 lifecycle violation flagged for the V1+ activation pass. Design retained intact. |
| **REC-11** | 2026-07-26 | **COMB_004 §8.5**: circular bulk-take delegation resolved — **NEW EVT-T1 sub-type `Item:TakeSpoils`**, COMB_004-owned: CellItemView-resolved, claim-window-honouring, cap-partial-filling, batched `entity_binding` transitions. No new aggregate. Registration rides the next lock cycle. |
| **REC-49 / 50 / 51 / 52** | 2026-07-26 | **Docs 17 / 18 / 16 / 15 correction passes applied** (agent, per banners + §12b). `17`: `ReadFreshness` withdrawn for the locked tier model; GDA-A6 rebuilt on `t1_read`; B5 ack-early per DP-Ch31 with per-channel `from_tokens`, DTOs, `client_protocol`; R2 over DP primitives with **ack-by-tier** (GDA-F11 partition adopted); B1 gains the mandatory tier-policy fetch. `18`: `*Born` re-anchored EVT-T5; **the phase-1 causal-ref blocker discharged without amendment** — EVT-L13 verified to allow T5→T8 refs, so the seed-root pattern (RBS-D8) works as written; ArchiveReplay rewritten as an exemption-gated restore-import with a documented fallback; RBS-A3 explicitly routed as a DP-A16 amendment request. `16`: five missing integration rows added incl. the `RULESET_UNKNOWN` legacy sentinel and WA_003 ownership; RLS-A14 producer corrected (Forge/admin-cli via S5; N durable events). `15`: §3 origin table superseded by the three-class model; CS-D9's T4→T5 correction; gates scoped to turn-bearing paths; CS-D10 gains the EVT-L4 head-of-line revisit trigger. **All LOCKED-file changes marked pending-AMEND in place; none applied.** |
| **REC-02 / 14 / 16 / 25 / 36 / 63 / 64-spec** | 2026-07-26 | Applied inline (see §12b): PCS-A9 per-(reality,user) · `LoginSessionId` newtype + session-fact single-writer · PROG f32 → milli-units + PROG-D6 retired · `Eldest` → V1+ pending FF_001 `birth_order` · `DiscardReason` closed enum + `turn.outcome` frame in `14`. |
| **AUD-F16 corpus** | 2026-07-26 | All 33 remaining `02_storage` files stamped with tailored superseding notes (agent; every root verified against content — zero mismatches). §11 header updated; S08 GDPR gap flagged for a DEFERRED row. |
| **REC-13 + REC-15** | 2026-07-26 | **PO_001 cascade rewritten**: whole chain routes through `Forge:CompleteOnboarding` (EVT-T8, service-account producer) — no more player-JWT emission of bootstrap-only events, no more per-signup `canonical_actors` mutation (runtime row instead, manifest stays a seed artifact per GDA-D3). **Order corrected** to the foundations' agreed `EntityBorn → ActorBorn → … → PcRegistered → BindPcUser` (both hops were inverted; the FK was written before its target existed). |
| **REC-17** | 2026-07-26 | **PF_001 §2.5** `PlaceBorn` clause corrected — *"emitted alongside `MemberJoined`"* → **strictly precedes**, membership moved to bootstrap phase 7, with the circularity, the CSC_001 zero-width window and the duplicate-emission registration all cited inline. **PF_001 §14.1** gained a matching note recording that §5 step 5 had been right all along and §2.5 was the defect. **Clears 4 findings** (`#15` partly, `#16`, `#38`, `RBS-F1`). *Remaining under REC-17: restating PL_001b §16.2 as normative and correcting the other four docs to it — needs the lock.* |
| **REC-48** | 2026-07-26 | **`C05_lifecycle_cas.md` §12Q.6** — added the 7 missing entry transitions (`provisioning`, `seeding`, `failed`, plus `archived → provisioning` for restore), flagging `seeding → failed` as the one most likely to be dropped and the one that matters: without it a manifest defect strands the reality in `seeding` with no diagnostic. **Unblocks `18`.** |
| **REC-03** | 2026-07-26 | **PL_005b §7** — `vital_pool` (RES_001) and `actor_status` (PL_006) added to the closed allowlist; `pc_stats_v1_stub` and `(V1+ pc_inventory)` withdrawn with rationale (DF7-A2 made the stat layer a projection with no aggregate; PL_007b made inventory a read-view); `entity_binding` added for the `Item:PickUp` path. **Combat and ability outcomes are now contract-legal.** |
| **REC-28** *(partial)* | 2026-07-26 | Recorded on the aggregate table under a real lock claim: `commit-service` has **no ownership row**, and EVT-A4's **closed 7-role producer set has no role for `sim-core`/the island** despite SC-A4. **Deliberately recorded rather than invented** — adding a producer role is EVT-A12 point (e), an event-model AMEND. Surfaced a live sub-conflict: **two claimed writers for `fiction_clock`** (EVT-V6 → pipeline executor; SC-A4 → the island). Full closure needs REC-53. |
| **prefix registration** | 2026-07-26 | `RLS-*` · `GDA-*` · `RBS-*` · `REC-*` registered in the ownership matrix under a genuine claim — **correcting five doc headers that had asserted the registration for hours without it happening.** Logged as the **fourth** instance of the `_LOCK.md` record-correction defect, by a session that had read the first three. |
| **REC-22** | 2026-07-26 | **PL_005b §3.5** — the mandated proposed negative `HpDelta` on every Strike withdrawn, per COMB_001 §9.1's 2026-06-20 reversal that this doc never absorbed. Strike now proposes intent only; the engine computes the number. |

---

## 12b. Decision resolutions — 2026-07-26 late (clear-state pass)

Under the PO's standing "clear all" directive, every remaining DECISION row is resolved below with
rationale. **A resolution recorded here is design state; the application edit in the owning doc is
batch work** (agents, tracked per row).

| REC | Resolution | Rationale |
|---|---|---|
| **REC-02** | ✅ **applied** — PCS-A9 amended to per-`(reality, user)` cap; PCS-D3's cap form pulled into V1; reject id superseded per I15 | the per-reality reading made a multiplayer game single-player; PO_001's own reject table had already assumed per-user; the multiverse capacity bound was always `player_cap`, not this axiom |
| **REC-14** | `actor_user_session.session_id` becomes **`login_session_id: LoginSessionId`** — a PO_001-owned newtype, NOT a DF5 `SessionId`; `Option<SessionId> current_chat_session` added separately if needed | the DF5 id is derived from a PC anchor that cannot exist during onboarding; renaming kills the type-level lie rather than papering it with `Option` |
| **REC-16** | **DF05_001 owns `session_participation`; PO_001's duplicate declaration is withdrawn.** The "current session" fact lives in **ACT_001 `current_session_id` alone**; PCS_001's `current_session` and PO_001's copy become read-throughs; PCS_001 keeps only login semantics (per REC-14) | one fact, one writer — the four-copy spread had no coherence ordering and a close-cascade would have logged players out |
| **REC-29** | **WA_003 Forge owns `RulesetEpochActivated`** (EVT-T8 sub-shape + matrix row) | Forge already owns admin rule-edits and the S5 dispatch chokepoint (EVT-P8); inventing a matrix schema change for platform-doc owners is a bigger amendment for zero gain |
| **REC-36** | **`SuccessionRule::Eldest` demotes to V1+**, shipping when FF_001 adds a `birth_order: u16` key (explicit author-declared, not derived from clocks) | no age/birth data exists anywhere in the substrate and TDIL clocks default to 0; `Designated` + `Vacate` cover V1 (consistent with REC-06's PC+Forge trigger scope) |
| **REC-37** | **COMB_001 drops the Lex axiom from the Q4 disparity-cap composition for V1** — the 50% cap is engine-only config; the axiom name stays registered as a V2+ reservation for when WA_001 ships typed (`AllowedWithBudget`) axioms | WA_001 V1 axioms are boolean by LOCKED decision; `lex_check` returns no value to compose; changing WA_001's type system for one consumer is the tail wagging the dog |
| **REC-38** | **COMB_005 adds the one stored flag**: `spawn_group_cleared: Set<(SpawnDeclId, epoch)>` on the cell's island state, checkpointed with it | AC-SPN-4 (a cleared camp stays cleared this epoch) is correct gameplay and unsatisfiable without one bit of state; "zero stored state" yields to "one stored set", already half-conceded by COMB_004's budget_remaining (REC-46) |
| **REC-54/55/56** | **The LLM decision path, resolved end-to-end:** (a) **ai-gateway is the LLM-Originator** — `07`'s "Python LLM-Originator (roleplay-service)" role transfers to ai-gateway, killing the language triple-contradiction (roleplay-service exits the game loop entirely, consistent with AUD-F16 root 7); (b) **the LlmDriver lives in commit-service (Rust)** and dispatches `DecisionContext` to ai-gateway; (c) **ai-gateway runs the tool-loop** with the model **via provider-registry** (BYOK resolution — both platform invariants now named in the game path); (d) **AGT's tools are proposal-schemas, not executable endpoints** — per AGT-A6 *"a Decision is a Proposal"*, a tool-call never executes anything; it IS the EVT-T6 payload, validated at admission. So no `combat-service`/`interaction-service` needs to exist — **AGT-A2 amends** from "sited on the owning domain service" to "declared in `contracts/agent/` (to be scaffolded), served as schemas by ai-gateway, executed by nobody"; (e) the return path stays the proposal bus unchanged | satisfies MCP-first (exposed + invoked through ai-gateway) and provider-gateway (single SDK home) without inventing services; keeps sim-core pure and the bus semantics intact; AGT-D4's "no carve-out needed" claim becomes true instead of aspirational |
| **REC-59** | **The reality owner (author) pays for NPC decisions**; players pay only for their own PC-assist calls. AGT-D5's per-reality budget = the author's cap, enforced before dispatch; `user_cost_ledger` rows for NPC decisions carry `user_id = reality_owner`, unit = one dispatch (proposal), metered via the existing `provider.call.completed` → usage-billing path | in a book-authored world the author IS the game master and already pays for world-gen (GEO_001b precedent); per-player NPC billing is unattributable when one NPC serves five players; PLT-4 BYOK-only free tier then reads coherently: a free-tier author's world runs NPCs on the author's key |
| **REC-64** | **NEW s2c frame `turn.outcome`** on the game transport: `{ turn_ref, outcome: Accepted \| Rejected{RejectReason} \| Discarded{reason_class, user_message: I18nBundle} }`, emitted by commit-service post-admission/post-step alongside the patch broadcast. `Fallback::Notify` resolves to this frame. `DiscardReason` gets a small closed enum in `14` (Duplicate / PreconditionFailed{Precondition} / Superseded / Expired) with per-class default copy | the bus consumed the request, so the *response* must be a push, not an HTTP ack; one frame, one envelope family (RejectReason's I18nBundle), closes error layers 4+5 for the player |
| **REC-69** | **One idempotency window: 5 minutes, everywhere** — gateway cache aligns up to sim-core's SC-D3 window; bus retention already exceeds it. Stated as the single client-retry contract | the 60 s gateway window created a 60s–5min zone where a retry was simultaneously a new turn and a duplicate; SC-D3's window was chosen against the client retry horizon, which is the right anchor |
| **REC-71/72/73/75** | **Colyseus carries the game** — W0/W1/W2, `turn.outcome`, patch broadcast, and the event stream all ride the game-server room protocol; the gateway WS remains platform/chat only (PRR-20 already sanctioned the second entry). **Resume is the DP-Ch18 per-channel map** (`from_tokens: HashMap<ChannelId,u64>`) carried in W0 — the singular token in `17` B5 corrects to the map. **W1 ships a client DTO layer, not aggregates**: `InventoryDigest` is replaced in W1 by a renderable `InventorySummary` DTO (the prompt digest keeps its LLM job); *"entity roster with render state"* becomes a named `RosterEntry` DTO. **W0 gains `client_protocol: u16`** + the rule *"server upcasts events to latest before fanout"* | one transport for one latency domain; the room is already the projection (GDA-A7), so giving it the payload avoids a second delivery path; DTO-vs-aggregate is the lesson of REC-73 generalized |
| **REC-20** | ✅ **unblocked and assigned**: AIT_001 §7.5 now has its dependency (TDIL-A11) — the section is the O(1) materialization formula over `ObservationAdvance`-supplied elapsed. Write rides the batch pass | the phantom existed because the formula had nothing to stand on; now it does |

Application status: REC-02 applied inline; the rest dispatched to the batch agents (below) with this
table as the specification. **AMEND rows (REC-53, 58, 65, 68 + AGT-A2/AGT-D1) remain the one
category not closable by this session alone** — they change LOCKED DP/EVT/AGT contracts and are
packaged as a single amendment bundle for the owning tracks' next lock cycles; the bundle is fully
specified across this register and the doc banners, so it is *decision-complete* even though its
application is gated.

## 13. Execution order

1. **REC-04** (clocks) and **REC-01** (enemy attack) — everything about the running game depends on
   these two, and both are DECISIONs. Nothing else in P0/P1 is worth editing first.
2. **REC-17** — one PF_001 edit clears four findings. Cheapest high-value item on the list.
3. **REC-48** — unblocks `18`.
4. **REC-03**, **REC-15**, **REC-20**, **REC-21**, **REC-22** — known-answer edits.
5. The REC-05..REC-13 dependency-inversion table — **one PO sitting** rather than nine.
6. **REC-53** EVT amendments, then **REC-49/50/51** (my docs depend on the outcome).
7. **REC-11** `02_storage` corpus pass.
8. P3 remainder.

**Do not start step 6 before step 5.** Several of my docs' corrections depend on scope answers in the
dependency-inversion table.

---

## 15. End state — 2026-07-26 close

**Applied and verified** (inline + four agent passes, every claim checked against file content):

- All **4 P0s** — the game runs on paper: enemies attack (REC-01), players onboard (REC-02), combat
  outcomes are contract-legal (REC-03), clocks advance (REC-04/TDIL-A11).
- All **9 dependency inversions** (REC-05..13) + the onboarding chain (REC-14/15/16).
- All **24 mechanical rows** (batch A) — including the two phantom references now *real*
  (`AIT_001 §7.5` written; `combat_reaction_table` declared) and the five-way ordering disagreement
  reduced to one normative list.
- **Docs 15/16/17/18** corrected per banners (batch B); one AMEND item **discharged by verification**
  (EVT-L13 permits T5→T8 refs — checked, not assumed).
- **All 33 `02_storage` files** stamped (batch C, zero mismatches).
- All **13 DECISION rows** resolved with rationale (§12b), including the LLM path end-to-end
  (ai-gateway as Originator · author-pays · Colyseus carries the game · one 5-min idempotency window).
- Gap-fill batch (REC-19/23/24/60/69) ✅ **applied 22:53** — end-of-batch referential validation at
  bootstrap (MAP+PF, per RBS-D6) · wall-clock removed from force-directed termination (fixed
  iterations; 5 s becomes a host job-timeout that **fails, never truncates**) · MAP §5 lazy positions
  → i32 milli-units with table trig · NEW `agent_decision` intent (8K/1K) in S09 + NPC_002 redirect ·
  one 5-minute idempotency window (PL_001b §14, four residual sites struck). Nothing skipped.

**Remaining — three categories, all explicitly gated, none silent:**

| Category | Contents | Gate |
|---|---|---|
| **AMEND bundle** | REC-53 (EVT-L18/A10/A9 + envelope v2 + restore-import exemption + EVT-G2/G4 bootstrap rows) · REC-58 (bus parked-state) · REC-65 (DpError drift) · REC-68 (gate-reject audit) · AGT-A2/D1 · DP-A16 lease · DP-Ch33-adjacent hotset default | owning tracks' lock cycles — **decision-complete, application-gated** |
| **Boundary registrations** | `Item:TakeSpoils` · `ruleset.*` namespace (REC-67) · `agent_decision` intent row · ability.* count sync (16) · `RulesetEpochActivated` under WA_003 | next `_boundaries` lock claim — one batch |
| **New design surfaces** | **REC-70/74: the client wire contract** (W0/W1/W2 DTOs, movement frames, turn submission, client state model) — the one genuinely *undesigned* surface left, now with every server-side decision it depends on made · `contracts/agent/` scaffold (REC-57) · S08 GDPR gap (island memory + Class A checkpoints) → DEFERRED row | next design cycle — "doc 20" and the SDK scaffolds |

**The claim "the design is on clear state" means, precisely:** every known contradiction is either
fixed in place, resolved-and-applied, or sitting in one of the three gated queues above with its
resolution already written. **Nothing is open without an owner and a stated next step.**

## 15a. Build-phase amendments — 2026-07-27 (POC-1/POC-2 findings, recorded same-day)

Three rows opened by the first BUILD contact with the design. All three are the healthy direction
of drift — code teaching the docs — and each was applied in the build commit that found it; what
remains is the owning docs' own text, gated as marked.

### REC-77 · **REC-54c: ai-gateway has NO LLM surface — the LlmDriver originates** · **AMEND** · supersedes §12b REC-54/55/56 (a)+(c)

Surface research against the running code (2026-07-27 01:05: ai-gateway's 5 controllers, the Go
gateway router, chat-service's client code) falsifies the §12b premise that ai-gateway can
originate LLM calls: **ai-gateway is MCP tool-federation ONLY.** The platform's sanctioned chain —
used by chat-service (Python) and tilemap-service (Rust) alike — is *caller → `loreweave_llm` SDK →
provider-registry `/internal/llm/stream`*; the agentic loop is always the caller's code.
**Amendment:** (a) the **LlmDriver (commit-service) is the LLM-Originator**; (c) the driver runs
the (single-shot) tool-call via the SDK. Unchanged: (b) LlmDriver in commit-service · (d) AGT tools
are proposal-schemas in `contracts/agent/` executing nothing (so MCP-first has no executable tool
in scope; provider-gateway is satisfied directly) · (e) return path = proposal bus.
**Applied in code** (`services/commit-service`, commit `e94fb6650`); doc-15/11 text updates ride
the next editing pass of those docs. *Lesson: verify a REC resolution's factual premise against
code before building on it.*

### REC-78 · **`DiscardReason` is a 5-variant set** · **AMEND** · REC-63 note

S1b panic containment added **`Quarantined`** (SC-A9: the pill's fate is a recorded outcome,
never silent) to REC-63's four-variant enumeration. Kernel + tests shipped (`df7a3ce69`);
doc-14 §5's enum listing gains the fifth variant at its next editing pass.

### REC-79 · **Candidate lists must separate IDENTITY from STATE** · **EDIT** · THR-A4 / COMB_003

POC-2 live finding (validity 50% → 83% on fix): offered as a combined label
(`"hostile-2 (healthy)"`), the model echoes the identity token and **strips the state
descriptor**, so every strike rejects as target-not-offered. THR-A4's top-K vague-labelled
candidate list must therefore offer **`{id, condition}` as separate fields**, with the tool's
`target` matching `id` verbatim. `contracts/agent/vocabularies/combat_v1.json` + the LlmDriver
already comply (commit `e94fb6650`); COMB_003's candidate-list shape gains the field split when
that doc next opens (owner: COMB track).

## 15b. Contradiction sweep — 2026-07-30 (map-architecture arc, doc [36](36_map_architecture.md))

**Why this section exists.** The PO asked a direct question — *"mấy cái PROPOSED đó là gì? có ảnh hưởng
tới chúng ta không? PROPOSED rồi chả dùng, có khi lại bị trôi và kiến trúc thì rot"* — and then set the
scope precisely: ***"clear là clear spec cho rõ ràng chứ không phải implement; có mấy cái quyết định nó
bị mâu thuẫn giữa các spec."*** This section is that clearing. **It resolves TEXT, not code.**

**Numbering continues from REC-79** (§15a). Rows here are contradictions **between specs** — one doc
saying one thing and another doc, or the shipped code, saying the opposite.

### Live contradictions found

| # | The two sides | Resolution | State |
|---|---|---|---|
| **REC-80** | `GEO_001` §2 scopes `world_geometry` **per CONTINENT channel** ⟷ [`GEO_WORLD_TIER_REDESIGN`](GEO_WORLD_TIER_REDESIGN.md) (LOCKED 2026-05-20) says the generator *"is structurally a **region** generator; this spec defines the **world** tier above it"* ⟷ shipped `crates/world-gen/src/hierarchy.rs` emits **one sphere containing many continents** | **The redesign and the code win.** `world_geometry` belongs to a `MapKind::World` node; a continent is a *product* of world generation, not its container. `GEO_001` is still **DRAFT**, so no lock claim is needed | ⬜ annotation applied 2026-07-30; §2 text edit is `SPG-R3` |
| **REC-81** | **Four** different tier ladders: shipped geographic (World→Continent→Subcontinent→Region) ⟷ shipped political (World→Realm→State→Province→County) ⟷ `MAP_001` `ChannelTier` (Continent→Country→District→Town→Cell) ⟷ its own demo `MAP_GUI_v2.html` (continent→country→**region**→cell) | **All four retired in favour of a relation.** Closed `MapKind` set + a **containment matrix** validated on write (`SPG-A3`). Political structure is an `owner_*` **attribute**, not a tier — the split [`FLAT_TO_3D`](FLAT_TO_3D_MIGRATION_PLAN.md) §C already chose and the code already implements | ⬜ annotation applied; `SPG-R1` |
| **REC-82** | `RTM-D Q4` **instanced dedicated combat scene** ⟷ `SPG-A16`/`SPG-D1` **fight in place where the space allows** (PO decision 2026-07-29) | **Reversed, on the `AUD-F1` precedent** — that reversal's justification applies verbatim: the original reason was *token cost*, and the medium correction dissolved it. Combat always resolves on a tactical grid; only the grid's **source** varies (Domain floor plan vs derived world field), so it is one mechanism, not two code paths | ⬜ recorded; `SPG-R8` |
| **REC-83** | `WSA-D3` *"a locus is **NOT** `ActorId::Synthetic`"* ⟷ `ACT_001`'s `actor.synthetic_actor_forbidden`, which as written blocks a locus from being observer or target of an opinion | **`WSA-D3` wins** — `Synthetic` denotes an actor *outside* the fiction; a village is inside it, can be regarded and can regard. The rule must be **narrowed**, not the axiom weakened | ⬜ `WSA-R21` (new `ActorId::Locus`) + `WSA-R22` (narrow the rule); both touch closed enums ⇒ own claim |
| **REC-84** | Three identity enums with **three different variant sets** (`EntityId` = Pc·Npc·Item·EnvObject ⟷ `EntityRef` = Actor·**Cell**·Item·Faction ⟷ `ActorId` = Pc·Npc·Synthetic·Admin), **plus** `entity_binding.cell_owner`'s doc-comment referencing `EntityType::Cell` — **a variant that does not exist** | **Phantom reference** (this register's §6 class). The drift is *evidence for* the change, not against it: `RES_001` needed `cell_owner` and `EntityRef` needed `Cell`, so the economy work discovered locus-as-entity empirically and worked around the type system | ⬜ `WSA-R19` (add `EntityId::Place`) + `WSA-R20` (fix the comment). **`SPG-R10` must land WITH `WSA-R19`** — `EntityId::Place` and `SpaceNode.holder` are one seam from two directions |
| **REC-85** | `WSA-D1` *"continuous fields are out of scope"* (doc 31) ⟷ `WSA-D2` *"no longer out of scope — coarse-cadence conserved transfer between locus-actors"* (doc 32) | **`WSA-D2` supersedes.** Only **sub-cell** continuous resolution (a true fluid lattice inside one cell) stays refused, and it is refused **by name** rather than by omission | ⬜ `WSA-R24` — doc 31 still states `WSA-D1` unqualified |
| **REC-86** | `DL-D1` routines *"evaluated, never ticked"* ⟷ `EXC-F3` *"the world acts when a ledger cannot balance"* | **Both survive.** DL-D1's ban was for **token-cost** reasons that do not apply to a deterministic accumulator; the fix is a **third row** (deterministic + accumulating), not a weakening | ⬜ `WSA-R01` |
| **REC-87** ⚠️ **PARTLY WRONG — corrected by [REC-96](#rec-96--the-second-row-retired-by-reading-its-target)**. The contradiction is real but this row named the wrong obstacle: `PCS-A4` and `Q9`'s `cap=1` are **not** it. See REC-96 for the precise finding. | `PCS-A4` *"single `pc_user_binding` V1"* + the PC concept-note `cap=1` validator ⟷ **possession is a core mechanic** (PO 2026-07-29: *"kiến trúc ban đầu không giới hạn ở chỗ điều khiển phải strict với 1 actor"*) | **Cardinality opens.** `ACT_001`'s L3 is already *dynamic* and `AGT-A3`'s drivers are already runtime-swappable — the seam is right; the shape is wrong. `control_source` is an **enum on the actor** and cannot name *which* controller nor hold two bodies. Required: a binding `(controller_id, actor_id, since, authority)` | ⬜ `SPG-R6` + `SPG-R7` |
| **REC-88** | `DF7-A5`'s stated rationale — percentages sum *"so the result is order-independent"* | **The rationale is simply wrong**: multiplication commutes too. The real rule is *one commutative operator per stage; stages ordered*. The **behaviour is correct**; only the justification is false — which is worse than a wrong behaviour, because it teaches the next author the wrong principle | ⬜ `WSA-R03` — cheap, no lock |
| **REC-89** | `00_VISION.md` §8 says this track *"is not on the roadmap"* and stages V1 as *"solo RP"* ⟷ the track has been **built for months** and `DL_001` already had to argue around the staging table | **Stale in two ways.** Needs a correction banner pointing at [28](28_product_definition.md) — exactly the way its own §0 corrected the *"text-based"* framing | ⬜ `WSA-R13` — cheap, no lock |

### Process findings from the same sweep

| # | Finding | State |
|---|---|---|
| **REC-90** | **15 of 25 `WSA-R*` amendment ids were ungreppable.** Docs 31 and 32 wrote their rows as bare `**R01**` … `**R24**`, without the `WSA-` prefix. **An id that cannot be grepped cannot be tracked** — this is rot at the infrastructure layer, not the discipline layer, and no amount of care fixes it. Corpus-wide greppable amendment ids: **37 → 52** | ✅ **FIXED 2026-07-30** — both files re-prefixed |
| **REC-91** | **Three rows were already SHIPPED while still reading as open.** `XST-R1` (`resolve.rs:110`, `factor = (1000+pct).max(0)`, with its kill-mutation named inline) · `XST-R2` (`combat.rs:49`, `i128` chain + `MAX_HIT` as a digest-hashed ruleset constant) · `XST-R3` (`combat.rs:32`, band inclusive `850..=1150`). All three were delivered by the `ruleset-core` F1/F2 arc, **not** by anyone working these rows. This is the `D-PUBLISHER-DROPS-RULESET-PIN` class — **debt already paid that keeps ringing** — and it is worse than unpaid debt, because it makes real work look like backlog and hides how much is genuinely left | ✅ **CLOSED 2026-07-30** with file:line evidence in doc 27 |
| **REC-92** ⚙️ **PARTLY DISCHARGED 2026-07-30 00:5x** — second `_boundaries` claim, made specifically to fix this: **`Item:TakeSpoils` and the `ruleset.*` namespace are now registered**; `agent_decision` + `ability.*` verified already present; `RulesetEpochActivated` correctly still blocked on the REC-29 knot. **What remains open is the MECHANISM**, not the batch. | **§15's own gated batch did not run at its gate.** §15 routed five boundary registrations to *"next `_boundaries` lock claim — one batch"*. A `_boundaries` claim **did** occur (2026-07-30, `SPG` registration) and **did not do the batch**: `Item:TakeSpoils` and the `ruleset.*` namespace (REC-67) are still absent from the matrix (`agent_decision` and `ability.*` are present; `RulesetEpochActivated` remains correctly blocked on the REC-29 ownership knot). **Root cause is the gate's shape, not the claimant's care:** *"the next lock claim"* names an **occasion**, not an **owner**, so it is nobody's, and the claimant has no reason to read this file. This is §14's finding arriving one more time, and it argues for the same remedy — a check, not a convention | ⬜ **OPEN** — 2 registrations owed, plus a mechanism so an occasion-gated item cannot be missed again |

### REC-93 — an amendment row retired the day it was written, by checking it before applying it

`SPG-R2` proposed narrowing `DP-Ch1`'s `Channel.level_name: String` to the closed `MapKind` set. It was
marked **verified** and queued for a lock claim, because `12_channel_primitives.md` is LOCKED. Reading
the target before editing it killed the row:

> [`DP-A13`](06_data_plane/02_invariants.md): *"**DP is agnostic to `level_name` semantics; feature/book
> layer interprets level names**… The tree shape is **per-reality** (book-specific) — a reality declares
> its own levels via a book schema."*

Applying it would have (a) pushed a **game-domain** concept into the **data plane**, breaking the exact
invariant DP-A13 exists to state, and (b) destroyed **per-reality vocabulary** — a wuxia reality could
no longer name a level `phủ` or `châu`. And DP's agnosticism is systematic, not incidental: `DP-A17` is
agnostic to turn semantics, `metadata` is *"a feature-level bag; DP does not interpret"*, and
`CausalityToken` is opaque to feature code by construction.

**The finding survives; only the mechanism was wrong** — the same shape as `WSA-R02` (finding stands,
mechanism replaced) and `XST-R6` (retired in favour of a better home). A free string where a closed set
is required *is* a defect; it was diagnosed one layer too low. **`SPG-R1` already fixes it correctly**:
`MapKind` lives on `map_layout`, a *feature* aggregate keyed by `channel_id` — the same layer that
`SPG-A2`'s ruleset-extensible whitelist occupies.

**Net result: two fields, two jobs.** `Channel.level_name` is the reality's own word (DP, untouched);
`map_layout.kind` is the structural kind the engine understands (feature layer). **No DP change, no lock
claim, and the design is better than the amendment would have made it.**

> **Process note.** This is the first row in this register **retired by its own author on the day of
> writing**, and it is worth stating why it was caught: the row was not applied from the table. The
> target was opened first. Every prior instance of this class in the corpus — `GDA-A5` prohibited by
> `DP-X1`, `GDA-A6` deleting the locked `t1_read`, `RBS`'s `*Born` mis-typed as EVT-T4 — was found by a
> **verification agent reading specs the docs had only been *grepped* against.** Same root cause, same
> remedy, one layer earlier.

### REC-96 — the second row retired by reading its target

**`SPG-R7` RETIRED, and `REC-87` above is corrected.** That row asserted that `PCS-A4` plus the `cap=1`
validator *"closes it exactly where possession needs it open"*. Opening both sources shows **neither
half held**:

| Claimed obstacle | What it actually is |
|---|---|
| `PCS-A4` *"single `pc_user_binding` V1"* | A **packaging** decision — one cohesive aggregate holding `user_id` + `current_session` + `body_memory`. It says nothing about control cardinality. |
| `Q9` `cap=1` | **PC-per-REALITY**, not per-controller. Recorded reason: *"single PC narrative"* vs *"multi-PC for charter coauthors"* — a **narrative scope** call. It was even shaped as `Vec<PcId>` + a validator *specifically* so relaxing it is *"a single-line validator change, no schema migration"* (`PCS-D3`). |

And possession does not need Q9 touched at all: **a 分身 need not be a `Pc`.** With a binding it can be
`ActorId::Npc` driven by a **User** controller — `ActorId` is L2 *kind* (stable), control is L3
*dynamic*, and `ACT-A2` already separates them.

**The real blocker was narrower and different: a `user_id` FIELD ON THE BODY.** `pc_user_binding`
encoded the control relation **1:1 inside the body's own aggregate**, which makes one controller
holding two bodies unrepresentable regardless of any cap. `SPG-R6` removes exactly that by extracting
`control_binding` — and **Q9 stays locked**, untouched.

> **Process note — this is the second time in one arc.** `SPG-R2` died the same way (REC-93): written,
> marked *verified*, queued for a claim, then killed by opening `DP-A13`. Both rows were **mine**, both
> were **marked verified**, and both were wrong in the same specific manner — **a plausible reading of a
> target that was grepped rather than read**. That is the exact root cause the corpus already recorded
> for `GDA-A5`, `GDA-A6` and `RBS`'s mis-typed `*Born`, where verification agents caught it *after* the
> docs shipped. Two catches now argue the habit is worth naming: **open the target before you act on the
> row, not after** — the amendment table is an index, never evidence.

### What "clear" means for the rest

The 52 amendment rows split four ways, and **only three of the four can be cleared by editing text**:

- **Already resolved** (~6) — `XST-R1/R2/R3` (above), `XST-R6` retired → `QTY-D4`, `XST-R7` adopted → `QTY-D11`, `WSA-R02` mechanism replaced → `QTY-D5`. **Mark and stop re-reading them.**
- **Cheap text corrections** (~12) — `WSA-R03`/`R13`/`R20`/`R24`, `WSA-R09..R12` (recontextualisations), `SPG-R4/R8/R9`. No lock, no schema.
- **Schema / locked-file edits** (~18) — `SPG-R1/R2/R3/R5/R6/R7/R10/R11/R12`, `WSA-R01/R05/R06/R07/R08/R19/R21/R22/R23`. Each needs its owning claim; `SPG-R2` (`DP-Ch1` `level_name: String` → `MapKind`) and `WSA-R19`/`R21` touch **LOCKED** files.
- **⚠ NOT amendments at all** (~13) — `WSA-R14` **the ledger** · `WSA-R15` capability derivation · `WSA-R16` **the PC time budget** · `WSA-R17` the balancing cell · `WSA-R18` the trigger vocabulary · `XST-R4/R5/R8/R9/R10/R11/R12/R13`. Verified absent from the codebase (`TriggerPoint`, `StatusInstance`, `HasTags`, `replacement_priority`, `Reproject`, `sub_index` — **zero occurrences**). **These are unbuilt subsystems wearing the costume of a table row**, and that mislabelling is the likeliest reason they have not moved: a *row* reads like a ten-minute edit, so nobody schedules it as the multi-week work it is. **They must be re-homed as build-track items under their real names — not ticked, not silently carried.** Clearing the *spec* here means saying plainly that they are undesigned-and-unbuilt; it does not mean implementing them.

## 15c. Re-homed — rows that are NOT amendments (2026-07-30)

**The mislabelling is the finding.** Thirteen rows sit in amendment tables while being **unbuilt
subsystems**. Every subject below was grepped against the codebase on 2026-07-30 and is **absent**:
`TriggerPoint`, `StatusInstance`, `HasTags`, `replacement_priority`, `Reproject`, `sub_index` — zero
occurrences each.

A *row in a table* reads like a ten-minute edit. Nobody schedules a row as the multi-week work it
actually is, and that — not neglect — is the likeliest reason none of these moved in the two days
since they were written. **They are re-homed here under their real names.** They are not ticked, not
closed, and not silently carried; they are **restated as build-track items** so the amendment tables
stop overstating how much is a text edit away.

| Was | Real name | Size | Note |
|---|---|---|---|
| `WSA-R14` | **The ledger** — conservation assertion, declared sources/sinks, and the bite test that a source-less 10 coins goes red | **large, new subsystem** | [`EXC-F2`](30_exchange_model_and_dataflow.md): the engine has the *transaction*, not the *ledger*. **Has a retrofit deadline** — impossible once content is balanced against a leaky economy, because then *the leaks are the balance* |
| `WSA-R15` | **Capability derivation** — `(holdings × imprint fold × self) → allowed actions`, epoch-stamped, never stored | medium | Closes the ONT loop's missing arrow. A derivation, not a subsystem — but still unwritten |
| `WSA-R16` | **The PC time budget** | medium | [`EXC-A2`](30_exchange_model_and_dataflow.md) makes every action cost time; NPCs have `ScheduledActionDecl` and **the player has nothing**. Without it, living in the world has no cost and therefore no decisions |
| `WSA-R17` | **The balancing cell** — one locus with production, consumption, stockpile, four-rung escalation | medium | The world-tier equivalent of *"one REAL encounter"*. Depends on `WSA-R14` |
| `WSA-R18` | **The trigger vocabulary** | medium-large | ⚠ **DUPLICATE of `XST-R9`** — see below |
| `XST-R4` | RNG `sub_index` + reserved roles (`shuffle`/`draw`/`cost`/`trigger_order`/`ailment`) | small **now**, expensive later | The reservation is the cheap part and it has not been taken |
| `XST-R5` | Saturation / negative-Σpct / clamp-fired **signals** | small | Partially present: saturation signals exist in `dp-kernel`, **not** in the stat path where the silent class lives. Directly the repo's own [non-vacuity discipline](../../standards/non-vacuity.md) |
| `XST-R8` | Interned tag bitset `[u64; 4]` + `Precondition::HasTags(mask)` | medium | |
| `XST-R9` | Closed `TriggerPoint` + `Reaction { when, guard, then }` with a **depth budget** | medium-large | ⚠ **Same work as `WSA-R18`** |
| `XST-R10` | `EffectOp` **combinators** (`Seq` / `Repeat` / `IfElse`) in a flat arena | medium | *"The only proposal that actually answers `XST-F7`"* — a closed `match` becomes a closed **grammar**. Tightening cannot fix F7 |
| `XST-R11` | A `REPLACE` stage + declared `replacement_priority: i16` | medium | Keeps the locked 4-step chain intact. **`WSA-F5(a)` says reaction ORDER still has to be declared** even after doc 32 — so this stays required |
| `XST-R12` | Status **instances** (severity / stacks / expiry), `StatusFlag` bitmask **derived** | medium | Bitmask stays the ~1 ns hot path |
| `XST-R13` | Typed side-tables + a budgeted `Reproject { dirty_slots }` step | medium | *"Converts a rotting invariant into a visible cost"* — and then **measure** it |

### REC-94 — the duplicate resolved, and the survivor turned out to be much smaller

**`WSA-R18` RETIRED 2026-07-30 → `XST-R9`.** They were the same work under two ids, proposed by two
registers three days apart, and doc 31's own row *cites* `XST-R9` in its reference column — so the
duplication was visible at the moment of writing and still produced a second id. `XST-F1`'s class in
the **register** layer: two indexes of one corpus, neither reading the other.

**And retiring it exposed that the survivor had already shrunk.** `XST-R9` was scoped *medium-large*
as *"design a closed `TriggerPoint` + `Reaction` with a depth budget"*. [`WSA-A11`](32_locus_as_actor.md)
(SEALED) collapses the trigger problem into the actor problem — *"every WHEN is **some actor took a
turn**"* — so:

- **there is no second dialect to design**; the existing turn seam generalises, which is exactly what
  `WSA-R18` said it wanted and what `PRD-F2` warned a bespoke trigger dialect would violate;
- **the depth budget is discharged by unification, not construction** — a reaction *is* a turn, turns
  are budgeted, so reaction depth is bounded by machinery that already exists;
- **`WSA-Q4`/`Q5` (when a locus takes its turn) are RESOLVED** in [`34`](34_when_the_world_runs.md):
  `next_wake` in closed form, no tick, no cadence, and a locus at equilibrium costs nothing.

**Residue, re-scoped to small-medium:** (a) `XST-R11`'s declared `replacement_priority` — still
required, because [`WSA-F5(a)`](32_locus_as_actor.md) states plainly that interleaved turns give *an*
order, not the *right* one (the Gisela case: two reactions, two orders, 7 vs 8); (b) naming the closed
`TriggerPoint` set the scheduler dispatches on. **Net: one id retired, and the surviving estimate fell
by roughly a tier** — which is the payoff of deduplicating before scheduling rather than after.

### REC-95 — the ledger's deadline given a mechanism instead of an adjective

`WSA-R14` is the only Class-D row carrying a **deadline** rather than a priority, and the deadline is
one-way: *"impossible once content is balanced against a leaky economy, because then **the leaks are the
balance**"* — remove them afterwards and every number an author tuned breaks. Calling that *"urgent"* in
prose is precisely the intent-not-mechanism failure this corpus keeps paying for.

**Registered as `D-LEDGER-BEFORE-BALANCE`** in the machine-read registry (game handoff §0) with a
`PROSE_ONLY` row in `scripts/deferral-gate.py` naming its wake-up trigger: **the first commit that
balances content against the economy** — a price table, a drop table, a production rate, a reward curve.

It is honestly prose-only rather than mechanised, and the reason is the `NV-2` shape: **there is no
ledger to assert against, so a check would have no possible violation.** What makes it mechanisable is
the ledger itself — `WSA-R14`'s own bite test is *a source-less 10 coins goes red*. Until then the row's
job is to be **printed on every run** so the deadline cannot pass quietly.

**Bite-tested, not asserted:** with the declaration in place `deferral-gate` exits **0**; with it removed
it exits **1** and names `D-LEDGER-BEFORE-BALANCE` as *"NO mechanism and no declared reason"*. Registry
now tracks **13** ids, 4 mechanised.

**What "clear the spec" means for these thirteen:** stating plainly, where a reader will hit it, that
they are **undesigned-and-unbuilt** — not implementing them, and not leaving them dressed as pending
edits. Two carry a *deadline* rather than a priority (`WSA-R14`'s retrofit window; `XST-R4`'s
reservation) and those two are the ones that get more expensive by waiting rather than merely staying
undone.

## 14. The process finding

Two of the four sweeps found the same thing at different layers, and it is not carelessness:

> **Documents are locked individually; correctness is a property of the set.**

`AUD-F16`: ~40 storage docs carry `MITIGATED` / `LOCKED` / `ACCEPTED` while describing an
architecture superseded on 2026-07-26. **A status marker records when a question was closed, not
whether the answer still holds**, and nothing re-opens a closed doc when its dependency changes.

`AUD-F17`: nine of thirteen CRITICALs are a locked doc depending on another locked doc's V1+
deferral, a section that does not exist, or an allowlist it contradicts. **REC-20 is the sharpest
case — a lock cycle recorded an edit that was never made.**

Better per-document review cannot catch either class. Both need a check that runs **across** the set:
a dependency lint (does any V1 item depend on a V1+ item?), a symbol lint (does every cited section
and struct exist?), and a re-open rule (when doc X changes, what did X's dependents assume?). Filed
here rather than in a feature doc because it is a **workflow** change, and it belongs with whoever
owns `agentic-workflow/`.

---

### REC-97 — a row marked APPLIED that never was, and the same lesson pointed the other way

**`_boundaries/01_feature_ownership_matrix.md` claimed *"Applied so far: `SPG-R1` · `SPG-R3` · `SPG-R5`"*.
All three claims were false.** Found the way the previous two were found — by opening the targets instead
of trusting the table:

| Row | Matrix said | Target said | Truth |
|---|---|---|---|
| `SPG-R1` | applied | `MAP_001:20` — *"**PROPOSED, not applied**; no schema in this file was edited. Annotation only"* | **half-applied** — `:94` and `:488` **had** renamed the field; ~70 dependent sites had not |
| `SPG-R3` | applied | `GEO_001:13` — *"**until** `SPG-R3` **is applied**"*, `:21` *"Annotation only"* | not applied (target correct) |
| `SPG-R5` | applied | `CSC_001:25` — *"`SPG-R5` is **PROPOSED, not applied**"* | not applied (target correct) |

Two were honest annotations **mislabelled by the matrix**. The third is the dangerous one.

**A half-rename is worse than no rename.** `MAP_001` carried *both* vocabularies with nothing marking
which sites were outstanding, while the matrix reported coverage — the same shape as a check that cannot
fail. The retired `ChannelTier` survived at **~91 sites across 22 files**, including **four fields of the
`RealityManifest` machine contract**, a ruleset field key, two catalogue rows marked ✅ delivered, and two
acceptance criteria — one of which, **`AC-MAP-3`, asserted `match` exhaustiveness over an enum that no
longer existed**, so it could not fail. `MAP_001:20` also disagreed with `MAP_001:94`: one file, two
answers, neither matching the matrix's third.

**The symmetry with REC-93 and REC-96 is the point.** Both of those retired a row marked *verified* that
died on contact with its target. This is the same failure **pointed the other way** — a row marked
*applied* that never was. Three instances, one root cause: **the amendment table is an INDEX, never
EVIDENCE.**

**And the miss it exposed in my own prior pass.** `SPG-R2` was retired for pushing `MapKind` *into* DP
(`DP-A13`). That pass never looked for a consumer **depending on** DP knowing `MapKind` — and there was
one: `map.tier_field_mismatch`, whose validator *"computes tier from DP channel-tree at write-time"*. Two
individually-correct decisions (`SPG-R1`, `DP-A13`) jointly made a third rule unimplementable — the
**adjacent-decision** shape from [`non-vacuity.md`](../../standards/non-vacuity.md), found only on the
second visit to the same seam. Resolved by making `map_layout.kind` **authoritative rather than derived**
and re-targeting the check to `map.containment_violation` (`allowed(parent.kind, child.kind)`), which is
also the answer to `SPG-Q1`.

**Mechanised, because intent is not a mechanism.** `amendment-rot-gate.py` **check D** — a retired
identifier may appear only on a line citing its retirement — armed with an **empty allowlist**, because
an enumerated exemption list is silent about the site added tomorrow. Seeding it with the ~70 sites as
they stood would have been the *default-uncovered* anti-pattern. It found **21 live uses the manual sweep
had missed**, including five in doc 36 itself, and its bite-test proves the escape hatch **reaches its
reason**: a line citing `SPG-R1` passes, a bare mention does not.

**Two smaller findings, recorded so they are not re-discovered.** (a) `GEO_001` declared `WorldScale` as
*"closed 5 V1"* with cell counts `1024/2048/8192/12288/16384` — round powers of two — while the shipped
generator had **six** variants and `1024/2025/8281/12321/16384/501264`. `design-lint`'s `count` check
exists for exactly this and did not fire: its `COUNT_FORMS` require the adjacency `` `X` (N variants) ``
and *"closed 5 V1"* walks past it. Now covered by the phrasing-independent `scale-band` check.
(b) `PL_005:568` recorded a **fifth** ladder — `Country/Region/Province/District/Cell` — matching neither
`MAP_001`'s designed set nor the three others `SPG-F2` catalogued. Five mutually-inconsistent ladders is
the strongest available evidence for `SPG-F2`'s conclusion that the enum was never load-bearing.

**⚠ POSTSCRIPT, added the same day — check D's FIRST version had the defect it was built to catch.**
The PO asked *"did you clear those rots?"* instead of accepting a green gate, and the answer turned out
to be **no**:

1. **`check_retired_identifiers` reused `_track_docs()`, which EXCLUDES `_boundaries/`.** That exclusion
   is *correct* for checks A/B/C — the matrix **is** the inventory, so scanning it for prefix
   registration would be circular — and check D inherited it **silently**. `_boundaries/` is where the
   **machine contracts** live. The gate reported OK while `02_extension_contracts.md` still carried
   `invalid_channel_tier (per MAP-2 ChannelTier::Continent)` — both retired names — in its live rule_id registry. This is the
   second shape in [`non-vacuity.md`](../../standards/non-vacuity.md) — **"the scope never reaches it"** —
   occurring **inside the check written to prevent that class**. A green gate whose scope omits the
   highest-value directory is worse than no gate: it certifies the one place a reader most wants checked.

2. **Widening the scope exposed two rots the manual sweep had never touched**, both in the ownership
   matrix itself:
   - **`map_layout` row (line 44) — the FIRST rot reported in this arc and the LAST one fixed.** It still
     read *"covers all tiers (continent through cell). Owns 5-variant retired-`ChannelTier` closed enum +
     author-positioned **absolute u32 (0..=1000)** per-tier viewport"* — every clause retired. The arc
     corrected line 229's *"Applied so far"* claim, swept fifteen feature docs, and left the row it
     started from untouched. Nothing but a widened gate would have found that.
   - **`world_geometry` row Tier×Scope** read *"continent per MAP-2 retired-`ChannelTier` per HIGH-2 fix"* — the
     `SPG-R3` scope inversion, sitting in the inventory.

3. **Two further precision defects in the check, both found by running it rather than reasoning about it.**
   *(a)* Line-wide citation matching: the `geography.*` namespace row is **12 401 characters**, so one
   unrelated `was` anywhere on it would have exempted every claim it contains. Fixed with a 160-character
   proximity window. *(b)* `\bwas\b` was spelled lowercase-only, so `SPIKE_04`'s *"it **WAS** — MAP_001
   §3 ChannelTier enum had 5 V1 variants"* passed. A citation vocabulary that depends on capitalisation
   is a hole with a spellcheck.

**All four are now bite-tested in `--selftest`, including the scope itself**: reverting
`_retired_scan_docs()` to `_track_docs()` makes the selftest fail with the reason spelled out. That is the
only durable form of this lesson — the first version's docstring already *claimed* an empty allowlist and
full coverage, and **intent is not a mechanism** even when the intent is specifically about mechanisms.


---

### REC-98 — the third half-application, and the point where a sweep stops being the answer

**`WSA-R19` was half-applied, and doc 32's blanket status line was false for three of the six rows it
covered.** Found by opening the targets rather than trusting a register — the same habit that produced
REC-93, REC-96 and REC-97, now four for four.

| Row | doc 32:14 said | The target said | Truth |
|---|---|---|---|
| `WSA-R19` | *"still PROPOSED, not applied"* | `EF_001` §5: `EntityId { …, Place(PlaceId) }` | **half-applied** |
| `WSA-R21` | *"still PROPOSED"* | `NPC_001_cast:67`: *"`Locus` **ADDED** 2026-07-30"* | **APPLIED** |
| `WSA-R22` | *"still PROPOSED"* | `ACT_001:205`: *"— **NARROWED** 2026-07-30"* | **APPLIED** |

**A blanket status over a RANGE of rows is the shape that goes stale silently**, because nothing has to
be true of all six for the sentence to keep reading plausibly. `SPG-R1`'s *"Applied so far"* (REC-97) was
the same construction pointed the other way. **And my own release note in `63d122b36` repeated it** — it
asserted these rows were unapplied and cited `EF_001:67`/`:131` as *"self-consistent and honest"*. Those
two lines were stale; `EF_001:352` was current. **I read the table instead of the code, one layer down
from the error I had just finished writing up.**

`EF_001` carried the applied change in §5 and contradicted it in **five** places: the domain-concepts
table (*"4 variants V1"*), the `WSA-R19`-pending doc-comment, the exhaustiveness rationale (*"all 4
variants"*), a missing `Place` row in the §5.1 variant table, and **`AC-EF-1`, an acceptance criterion
describing a `match` over 4 variants that would not compile against the 5-variant enum** — the same
vacuous shape `AC-MAP-3` had in REC-97.

**Three occurrences is where the answer stops being another careful sweep.** The mechanism is
`design-lint`'s `count` check, extended to close its own documented hole:

> *"KNOWN LIMIT: it can only check enums that EXIST in code."*

`EntityId` is spec-only, so *"4 variants V1"* sat beside a five-variant declaration **in the same file**
with nothing able to look. The check now parses enums out of the corpus's own ` ```rust ` blocks,
**per file**, and compares claims against the declaration in that same document.

**Four things the build had to learn from running it, not from reasoning about it:**

1. **Cross-document comparison was cut at design review.** Three docs declare `pub enum ActorId`, and two
   are legitimately different types — the data plane's `{Player, Npc}` versus the feature layer's
   `{Pc, Npc, Synthetic, Admin, Locus}`. A cross-doc arity check would have false-positived on its first
   run. Per-file has no homonym problem because two files never meet. (`D-SPEC-CODE-ENUM-PARITY`.)
2. **The first working version did not catch the defect it was built for.** `COUNT_FORMS` requires the
   number and the symbol to be adjacent; `EF_001:67` is `| **EntityId** | … | 4 variants V1`, a table cell
   away. A **loose** form was added, made safe by a constraint the corpus-wide check could never have: the
   symbol must name an enum **this file declares**, and **exactly one** such name may appear on the line.
   The historical false positives cannot survive that — *"(the §11 variant"* names no enum, and the
   mis-attribution case needs two candidates.
3. **Running it over the corpus found two more false-positive classes and one more real defect.**
   Version-partitioned enums (`MemoryQuery`: *"V1 4 variants; V2+ adds…"* against a 6-variant block) have
   **no single arity**, so they are excluded — detected on the RAW body *before* comment stripping,
   because the version markers live in exactly the comments the stripper removes. A historical claim
   (`TVL_003`: *"TVL_001 built `TravelMode` 2-variant"*) took the sanctioned pragma. And
   `GEO_001b`'s summary said *"14 variants"* against a **16**-variant declaration — a genuine drift in a
   file this arc never touched.
4. **Teaching the matcher past tense was rejected on ML-4 grounds.** A tense-detecting rule is
   language-biased by construction and would fail on this corpus's Vietnamese prose. The pragma is the
   right hatch precisely because it is language-neutral.

Net: **4 count claims corrected across 3 files, 2 of them defects no human had reported**, and the class
now has a check instead of a habit.
