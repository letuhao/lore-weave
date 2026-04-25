# PL_005c — Interaction Cross-Feature Integration

> **Continued from:** [`PL_005_interaction.md`](PL_005_interaction.md) (root, conceptual layer §1-§19) + [`PL_005b_interaction_contracts.md`](PL_005b_interaction_contracts.md) (contracts, §1-§12 per-kind payload schemas + OutputDecl taxonomy + acceptance scenarios). This file holds the **cross-feature integration layer** (§1-§11): how Interaction events flow through validator pipeline + NPC_002 Chorus consumption + PCS_001 mortality side-effects + NPC_001 opinion drift + V1+ Generator triggers (butterfly cascades) + failure compensation + replay determinism + V1 minimum implementation scope.
>
> **Conversational name:** "Interaction integration" (INT-I). Read PL_005 + PL_005b FIRST — this file shows how those contracts COMPOSE with consumer features.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** DRAFT 2026-04-26 (Phase 3 of PL_005 design)
> **Stable IDs:** none new — references PL_005 §2 + PL_005b §1 domain concepts. No boundary lock claim needed (no new aggregate types or sub-types introduced).
> **Builds on:** PL_005 + PL_005b. Same DP contracts + same Event-model mappings.

---

## §1 Validator pipeline integration (per-kind chain detail)

Per [`07_event_model/05_validator_pipeline.md`](../../07_event_model/05_validator_pipeline.md) framework + [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) current ordering, every Interaction event flows through the fixed pipeline. Per [PL_005b §8](PL_005b_interaction_contracts.md#8-per-kind-validator-subset), each kind has specific behavior at the world-rule stage. This section spells out the FULL chain with stage-by-stage details for each kind.

### 1.1 Common chain (all kinds)

```
incoming Interaction:<Kind> candidate (from EVT-T6 Proposal validation OR direct EVT-T1 Submitted from Orchestrator)
   │
[stage 0] schema validate
   ├─► verify InteractionPayloadBase fields populated (agent / tools / direct_targets / ...)
   ├─► verify kind-specific extension fields populated
   └─► verify proposed_outputs entries reference valid aggregate_types per PL_005b §7 taxonomy
   │
[stage 1] capability check (DP-K9)
   ├─► JWT carries `produce: [Submitted]` claim
   ├─► JWT carries `can_advance_turn @ level=cell`
   └─► For each proposed OutputDecl, JWT carries `write: aggregate_type @ tier @ scope`
   │
[stage 2] A5 intent classification
   ├─► confirm Submitted/Interaction:* matches actor type (Pc → free narrative or command-driven; Npc → orchestrator-driven)
   └─► PL_005 always Story or Command intent (per A5-D1 closed set)
   │
[stage 3] A6 sanitize (input layer)
   ├─► narrator_text + utterance.raw_text scanned for jailbreak patterns
   └─► Speak Whisper: extra audit-log per privacy V1+
   │
[stage 4] ★ lex_check ★ (WA_001) — KIND-SPECIFIC SEVERITY
   ├─► Speak: no-op (Speak mundane in V1 realities)
   ├─► Strike: check StrikeKind axiom-allowed in this reality (Slash with sword OK; firearm in Wuxia REJECTS)
   ├─► Give: no-op (Give mundane)
   ├─► Examine: no-op (Examine mundane)
   ├─► Use: ★ CRITICAL ★ — item × reality compatibility per LexConfig.axioms; e.g. spell scroll in Reality 2 sci-fi REJECTS with `interaction.use.lex_forbidden`
   │
[stage 5] ★ heresy_check ★ (WA_002 — V1+ contamination)
   └─► Currently no-op for V1 Interaction; V2+ contamination budget tracking on cross-reality items
   │
[stage 6] A6 output filter
   └─► narrator_text + utterance scanned for cross-PC leak / persona-break / NSFW
   │
[stage 7] world-rule physics — KIND-SPECIFIC ACTUAL_OUTPUTS DERIVATION
   ├─► Speak: ActualOutputs typically empty; canon_drift_flags populated by A6 detector
   ├─► Strike: read mortality_config + pc_stats_v1_stub.hp(target); compute clamped HpDelta;
   │           if hp would reach 0, derive MortalityTransition per mortality_config (Permadeath →
   │           Dead; RespawnAtLocation → Dying with respawn_at_fiction_time + spawn_cell; Ghost → Ghost)
   ├─► Give: read npc_pc_relationship_projection (recipient → agent); compute opinion delta scaled by GiveIntent;
   │         opinion delta typically small positive for Gift, smaller for Bribe, larger for Tribute
   ├─► Examine: if target canonical, invoke Oracle (PL-16) for fact answer; populate oracle_query_id
   ├─► Use: per-item effect derivation (heal potion → HpDelta+, key → lock transition,
   │        wine → status_flag(Drunk)); item × target compatibility check
   │
[stage 8] canon-drift check
   ├─► Speak: A6 body-knowledge mismatch detector flags drift (SPIKE_01 turn 5 — Lý Minh quotes book his body shouldn't know)
   ├─► Strike/Give/Use: typically no canon-drift unless tool/effect contradicts L1/L2/L3 facts
   └─► Examine: drift if Oracle returns conflicting fact (rare; A3 deterministic)
   │
[stage 9] causal-ref integrity (EVT-A6)
   ├─► If kind = Interaction (NPC reaction batch) — REQUIRED causal_refs to triggering event
   └─► If kind = Interaction from PC submission — optional causal_refs
   │
[commit] dp::advance_turn(ctx, &cell, turn_data: TurnEvent { sub_shape: "Interaction:<Kind>", payload, ... })
                 → Submitted event_id (T1)
   │
[post-commit side-effects per EVT-V6]
   ├─► For each entry in actual_outputs, emit EVT-T3 Derived via Aggregate-Owner role:
   │     ├─► npc_pc_relationship_projection delta → NPC_001 owner-service emits
   │     ├─► pc_mortality_state transition → PCS_001 owner-service emits
   │     ├─► pc_stats_v1_stub HpDelta or StatusFlagDelta → PCS_001 owner-service emits
   │     └─► oracle_audit_log entry → DP-internal / 05_llm_safety A3 owner emits
   ├─► Each Derived event carries causal_refs = [Submitted event_id]
   └─► Side-effect failure does NOT roll back parent (per §6 below)
```

### 1.2 Kind-specific Validation timing summary

| Kind | Most-likely-reject stage | Primary actual_outputs source |
|---|---|---|
| **Speak** | stage 8 (canon-drift flag, but NOT hard-reject) OR stage 0 (empty utterance) | A6 detector populates canon_drift_flags |
| **Strike** | stage 4 (Lex axiom) OR stage 7 (target Mortality≠Alive) | physics: HpDelta clamped + MortalityTransition |
| **Give** | stage 7 (recipient refused via opinion threshold) | opinion delta calculation |
| **Examine** | stage 0 (target_not_in_cell) OR stage 7 (target_not_visible — V1+ stealth) | Oracle query |
| **Use** | **stage 4 (Lex CRITICAL)** OR stage 7 (target incompatible) | per-item effect (Lex-derived) |

---

## §2 NPC_002 Chorus consumption flow

NPC_002 Chorus is the primary consumer of committed Interaction events as Triggers for multi-NPC reactions. Per [NPC_002 §7](../05_npc_systems/NPC_002_chorus.md#7) + [NPC_002 §11](../05_npc_systems/NPC_002_chorus.md#11), Chorus orchestrator runs on the cell's writer node (per DP-A16) and subscribes to channel events filtered by `Interaction:*` sub-shapes.

### 2.1 Sequence

```
1. PL_005 Interaction commits via dp::advance_turn → Submitted event_id (T1)

2. NPC_002 Chorus orchestrator consumes T1 from durable subscribe:
     - Trigger event = T1 (any Interaction:* sub-shape)
     - Read SceneRoster (per NPC_002 §6.1): all ActorId currently in cell
     - For each NPC in roster, evaluate priority (NPC_002 §6 algorithm):
         Tier 1: filtered out (per NPC_002 §11 — rare, e.g., illiterate NPC for literacy slip)
         Tier 2: high opinion + relationship → primary candidates
         Tier 3: knowledge match (Du sĩ for book quote — SPIKE_01 turn 5)
         Tier 4: ambient (silent acknowledgment — Lão Ngũ for SPIKE_01 turn 5)
     - Cap reactions at V1=3 candidates per NPC_002 §3.2 ChorusBatchState
     - Emit reaction batch:
         For each candidate:
           a. Build NPCTurnProposal payload (sub-shape NPCTurn:<reaction_intent>)
           b. Emit EVT-T6 Proposal (LLM-Originator role per roleplay-service)
           c. roleplay-service runs LLM with persona prompt (NPC_001 persona assembly)
           d. Validator pipeline runs on proposal (same chain as PL_005 §1)
           e. On Validated: commit fresh EVT-T1 Submitted/NPCTurn (carries causal_refs=[T1])
     - Reactions commit sequentially under single held turn-slot per NPC_002 §3.2 batched mode
     - Each NPCTurn may itself be an Interaction (NPC_001 Speak / Strike / etc.) — V1 cascade depth = 1

3. UI multiplex stream delivers original Interaction T1 + N reaction NPCTurns in order
   (per DP-A15 per-channel total ordering + NPC_002 batched-slot semantics)
```

### 2.2 Cascade depth boundary

Per [DP-Ch29](../../06_data_plane/16_bubble_up_aggregator.md#dp-ch29--cascading--loop-prevention-rules) bubble-up cascade cap (16 levels) generalized via [EVT-G3](../../07_event_model/12_generation_framework.md#evt-g3--cycle-detection-static--runtime) to all Generators + Orchestrators. NPC_002 Chorus enforces V1 cap = 1 (an NPC reaction does NOT trigger further Chorus reactions); V2+ may raise.

### 2.3 Rejected Interaction → Chorus behavior

If PL_005 Interaction rejects (per EVT-V4 — committed via t2_write with outcome=Rejected; turn_number unchanged), the rejected event STILL appears in channel event log as a Submitted with `outcome=Rejected`. Chorus orchestrator filters these out (per NPC_002 §11 — rejected interactions don't elicit reactions; PC sees soft-fail UX directly per PL_005 §9). This is consistent with [EVT-V4](../../07_event_model/05_validator_pipeline.md#evt-v4--rejection-path-semantics-resolves-mv12-d11) rejection-path semantics.

---

## §3 PCS_001 mortality side-effect flow

When Interaction:Strike actual_outputs contain MortalityTransition (when target hp would reach 0), PCS_001 owner-service consumes the Derived event and updates `pc_mortality_state` aggregate. Per [PCS_001 brief §S4](../06_pc_systems/00_AGENT_BRIEF.md), the state machine is closed-set: `Alive` / `Dying { will_respawn_at_fiction_time, spawn_cell }` / `Dead { died_at_turn, died_at_cell }` / `Ghost { died_at_turn, died_at_cell }`.

### 3.1 Strike Lethal sequence (mortality flow)

```
1. PL_005 Interaction:Strike commits with actual_outputs = [
     OutputDecl { target: Actor(target_pc), aggregate: pc_stats_v1_stub, delta: HpDelta(-30) },
     OutputDecl { target: Actor(target_pc), aggregate: pc_mortality_state,
                  delta: MortalityTransition { from: Alive, to: <derived_per_mortality_config> } }
   ]
   → Submitted event_id T1

2. PCS_001 owner-service (Aggregate-Owner role) consumes the Derived events:
   a. dp::t2_write::<PcStatsV1Stub>(ctx, target_pc, HpDelta(-30))  → T2
      (causal_refs=[T1])
      Result: target_pc.hp = 0
   b. dp::t2_write::<PcMortalityState>(ctx, target_pc, MortalityTransition { ... })  → T3
      (causal_refs=[T1])
      Result: target_pc state transitions per mortality_config:
        - Permadeath: state = Dead { died_at_turn, died_at_cell }
        - RespawnAtLocation { spawn_cell, fiction_delay_days }: state = Dying { ... }
                                                                  → V1+30d scheduler triggers respawn
        - Ghost: state = Ghost { ... }

3. UI receives T1 + T2 + T3 via multiplex stream:
   Renders Strike narration → HP bar drops to 0 → death/dying overlay per state

4. Downstream consequences (V1+):
   - If state=Dying: scheduler (per EVT-T5 Generated::Scheduled) fires respawn at fiction_delay_days
   - If state=Dead: NPC_002 Chorus may emit grief reactions from co-present NPCs
   - V1+ Generator: GriefDrift opinion delta on family/faction members elsewhere
```

### 3.2 mortality_config source-of-truth boundary

PL_005 / PL_005b derive ActualOutputs.MortalityTransition variant **at validator stage 7** (world-rule physics) by reading `mortality_config` (singleton aggregate per WA_006). PCS_001 owner-service executes the transition; PCS_001 does NOT re-decide the variant. This atomic boundary (B4 decision) keeps mortality outcome deterministic + replay-correct.

If `mortality_config` updates after a Strike was scheduled but before commit (admin-edits via Forge mid-action), the validator MUST use the config snapshot at validate time (DP-K2 SessionContext supplies snapshot ref). V2+ may add `mortality_config_version_at_strike` to MortalityTransition delta for forensic audit.

### 3.3 NPC mortality (V1 placeholder per B1)

For target=NPC, PCS_001 doesn't apply (PCS_001 is PC-only per brief). V1 placeholder uses `npc.flexible_state.liveness_flag` per [PL_005 §17 INT-D2](PL_005_interaction.md#17-open-questions-deferred--landing-point) — Strike on NPC with hp=0 → AggregateMutation on `npc.flexible_state` flipping liveness flag. Full NPC mortality state machine deferred to future `NPC_003_mortality.md`. Migration path when NPC_003 ships: existing liveness flags migrate to NPC_003's full state machine.

### 3.4 V1+ Respawn flow (deferred)

When state=Dying AND `mortality_config.default_death_mode = RespawnAtLocation { spawn_cell, fiction_delay_days, memory_retention }`:

- Scheduler (V1+30d per [EVT-L11](../../07_event_model/08_scheduled_events.md#evt-l11--phasing-v1--v130d--v2)) fires Respawn beat at `current_fiction_ts + fiction_delay_days`
- Respawn beat → EVT-T5 Generated::Scheduled with sub-type `Mortality:Respawn`
- PCS_001 owner-service consumes → transitions Dying → Alive at spawn_cell
- DP-internal `MemberJoined` + `move_session_to_channel` per DP-A18

V1 (no scheduler) cannot do auto-respawn; only Permadeath functional in V1.

---

## §4 NPC_001 opinion drift flow

When Interaction (Speak / Give / Strike / sometimes Examine) actual_outputs contain OpinionDelta on `npc_pc_relationship_projection`, NPC_001 owner-service consumes the Derived event and updates the projection.

### 4.1 Sequence

```
1. PL_005 Interaction commits with actual_outputs = [
     OutputDecl { target: Actor(npc_id), aggregate: npc_pc_relationship_projection,
                  delta: OpinionDelta(reaction_to=pc_id, trust=+1, stance_tags_add=["respectful"]) }
   ]
   → Submitted event_id T1

2. NPC_001 owner-service (Aggregate-Owner role) consumes Derived:
   dp::t2_write::<NpcPcRelationshipProjection>(ctx, (npc_id, pc_id), OpinionDelta(...))  → T2
   (causal_refs=[T1])

3. Subsequent NPC turns (via NPC_002 Chorus) read updated opinion via NpcOpinion::for_pc:
   - Higher trust → NPC may speak more openly, share information
   - Lower trust → NPC may refuse Give, Strike less likely to elicit help
```

### 4.2 Opinion delta calibration per Interaction kind

| Kind | Default opinion delta | Modifier |
|---|---|---|
| **Speak** (Quote/Statement) | none typically | A6 canon-drift flag may produce small negative if SPIKE_01-style mismatch |
| **Speak** (Cry/Whisper) | small | depends on content (insult vs compliment — V1+ sentiment classifier) |
| **Give** Gift | +2 trust + stance "grateful" | scaled by gift_count vs NPC's economic state |
| **Give** Payment | +1 trust + stance "transactional" | smaller than Gift |
| **Give** Bribe | +1 trust + stance "compromised" | smaller magnitude; flag as ethically suspect |
| **Give** Tribute | +3 trust + stance "honored" | formal context |
| **Strike** Lethal | -50 trust + stance "hostile" + remove "trusted" | regardless of outcome (intent matters) |
| **Strike** Stun/Restrain | -10 trust + stance "wary" | smaller than Lethal |
| **Examine** | none typically | exception: examining NPC's secret possessions → -2 trust + stance "intrusive" |
| **Use** (item on NPC) | per-item effect | heal potion = +5 trust; offensive scroll = -50 |

V1 default magnitudes locked here; V1+ may add per-NPC-personality modifiers (introvert NPCs more sensitive to Speak; warriors less sensitive to Strike).

### 4.3 Opinion read in subsequent NPC reactions

Per [NPC_002 §6](../05_npc_systems/NPC_002_chorus.md#6) priority algorithm Tier 2 reads opinion via `NpcOpinion::for_pc(npc_id, pc_id) → OpinionScore`. Opinion drift from one Interaction immediately affects subsequent Chorus priority within the same scene.

---

## §5 V1+ Generator triggers (butterfly cascades — architecture sketch)

Per [EVT-G framework](../../07_event_model/12_generation_framework.md), downstream cascades from Interaction events live in EVT-T5 Generated category, fired by registered Generators with conditional/probability triggers. These are V1+ — full implementation when consumer features ship.

### 5.1 Pattern (replay-deterministic per EVT-A9)

Each Generator subscribes to Interaction events as trigger source per [EVT-G2](../../07_event_model/12_generation_framework.md#evt-g2--trigger-source-taxonomy) kind (a) `CommittedEventOf { category: Submitted, sub_type_filter: Interaction:* }`. On match, runs deterministic-RNG-seeded condition + probability evaluation:

```
fn on_event(triggering_event: SubmittedEvent) -> Vec<EmitDecision> {
  if !matches_trigger_filter(&triggering_event) { return vec![]; }
  let rng = dp::deterministic_rng(channel_id, channel_event_id);
  let probability = compute_probability(&triggering_event);
  if rng.gen_range(0.0..1.0) < probability {
    vec![EmitDecision::Emit { ... }]
  } else { vec![] }
}
```

### 5.2 V1+ example Generators (deferred to consumer features)

| Generator | logical_id | Trigger | Probability | Output sub-type |
|---|---|---|---|---|
| **PoliceCallout** | `investigation:PoliceCallout` | EVT-G2 (a) Submitted/Interaction:Strike with StrikeIntent=Lethal AND scene `cell.metadata.has_authority_witness=true` | 0.95 (high — authorities respond to lethal violence) | EVT-T5 Generated::Investigation `PoliceCallout { suspect: agent, victim: target }` — emits at country/district level |
| **GriefDrift** | `relationship:GriefDrift` | EVT-G2 (b) StateThresholdOn { aggregate=pc_mortality_state, predicate: Dead } | 0.8 if family_relationship_strong, 0.4 otherwise | EVT-T5 Generated::Relationship `GriefOpinionDelta { mourner: family_member, deceased: pc_id }` — opinion drift on faction members elsewhere in reality |
| **RumorSeed** | `gossip:RumorSeed` | EVT-G2 (a) Submitted/Interaction:Speak with canon_drift_flags non-empty | 0.5 (depends on cell traffic) | EVT-T5 Generated::BubbleUp `RumorBubble { topic: drift_topic, seed_event: T1 }` — propagates to ancestor channels |
| **WitnessReport** | `interaction:WitnessReport` | EVT-G2 (a) Submitted/Interaction:Strike OR Submitted/Interaction:Use with severity≥Major AND indirect_targets non-empty | 0.7 per witness (loops per indirect_target) | EVT-T5 Generated::Witness `WitnessTestimony { witness: indirect_target, observed_event: T1 }` |

### 5.3 Generator capacity governance

Per [EVT-G4](../../07_event_model/12_generation_framework.md#evt-g4--per-generator-capacity-governance) tiered enforcement. Each Generator declares per_second / per_minute / burst caps at registration. Example for PoliceCallout: `EmitRateLimit { per_second: 1, per_minute: 10, burst: 3 }` — police don't respond to flood of strikes; ceiling reflects realistic enforcement bandwidth.

### 5.4 Cycle detection across Interaction → Generator → ?

Per [EVT-G3](../../07_event_model/12_generation_framework.md#evt-g3--cycle-detection-static--runtime) static + runtime. If GriefDrift's opinion delta triggers an NPC's Strike (vengeance), that's a cascade. V1+ cascade depth cap = 16 (matches DP-Ch29). Specific cycle examples + Generator graph topology audited at registration time per `_boundaries/_LOCK.md` claim.

---

## §6 Failure compensation flow

Per [EVT-V7 dead-letter framework](../../07_event_model/05_validator_pipeline.md#evt-v7--dead-letter-framework) + [EVT-A10 event as universal SSOT](../../07_event_model/02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25), the event log is append-only canonical. Partial failures during Interaction commit + side-effect emission do NOT roll back the parent Submitted commit. Compensation is event-driven.

### 6.1 Failure scenarios + handling

| Failure point | Handling |
|---|---|
| **Validator stage 0-9 fail** | Submitted commit with `outcome=Rejected` per EVT-V4; turn_number unchanged; PC sees soft-fail UX; no side-effects fire (parent NEVER committed Accepted) |
| **dp::advance_turn fails (DP-internal error mid-commit)** | Idempotency cache (PL_001 §14) returns existing event_id on retry; if first commit truly failed, retry succeeds; if first commit partially completed, DP-Ch11 channel_event_id allocation prevents duplicate |
| **First Derived event commits but second fails** | Parent Submitted T1 committed Accepted; T2 (HpDelta) committed; T3 (MortalityTransition) failed → dead-letter (EVT-V7); audit-log SEV2; **state inconsistency window** until operator reconciles |
| **All Derived events fail (network outage to Aggregate-Owner)** | Parent T1 committed; all Deriveds dead-lettered; UI sees parent but state not reflected in projections; **operator-driven reconcile via admin-cli** (V1+ admin command) |
| **Chorus reaction fails mid-batch** | Parent T1 committed; some NPCTurn reactions committed; failed reactions dead-lettered + audit; UI sees partial reaction batch (with audit-log entry visible to ops); next Interaction may re-trigger |

### 6.2 Operator-driven reconcile (V1+ admin command)

When dead-letter accumulates Derived failures, operator runs admin-cli command (specific design deferred to V1+ per INT-CON-D5):

```
admin-cli interaction reconcile --reality_id=<id> --since_event_id=<id>
```

Command:
1. Reads dead-letter entries for failed Derived events
2. For each entry, attempts replay against current projection state
3. If replay succeeds (idempotent commit), commits Derived; clears dead-letter entry
4. If replay fails (state diverged — e.g., target already Dead from another path), audit-logs + escalates SEV1

**No automatic compensation in V1.** Append-only canonical event log + manual reconcile is the V1 model. V2+ may add automatic compensation Generators.

### 6.3 Idempotency boundary

Per uniform [EVT-P*](../../07_event_model/04_producer_rules.md) idempotency key shape `(producer_service, client_request_id, target_channel)`:

- PC submission retry → gateway idempotency cache (PL_001 §14) catches duplicates before reaching commit
- Aggregate-Owner Derived emission retry → `(aggregate_owner, parent_event_id, target_aggregate_id)` composite ensures exactly-once even on transient failure
- Chorus reaction retry → `(orchestrator, trigger_event_id, npc_id)` composite per NPC_002 §3.2 ChorusBatchState

---

## §7 Replay determinism for Interaction

Per [EVT-A9 RNG determinism](../../07_event_model/02_invariants.md#evt-a9--probabilistic-generation-determinism-new-2026-04-25) + [EVT-A10 universal SSOT](../../07_event_model/02_invariants.md#evt-a10--event-as-universal-source-of-truth-new-2026-04-25), replay reproduces same observable state given same input event log + same fiction-clock state + same RNG seed.

### 7.1 Determinism scope for Interaction

| Layer | Bit-deterministic? | Notes |
|---|---|---|
| **Validator pipeline outcome** | ✅ | Given same input payload + same projection state at validate time + same Lex config + same A6 detector version, validator produces same Accept/Reject decision |
| **ActualOutputs derivation** | ✅ | World-rule physics is pure-function over input state + Lex config; no RNG used in derivation (EVT-A9 forbids); same input → same output |
| **Chorus reaction selection** | ✅ | NPC_002 §6 priority algorithm uses `dp::deterministic_rng(channel_id, T1.channel_event_id)` for tie-breaking; replay produces same N candidates in same order |
| **Chorus reaction LLM content** | ❌ | LLM output is non-deterministic; replay regenerates flavor narration per EVT-A8 from `flavor_text_audit_id` audit-log pointer |
| **V1+ Generator probability gates** | ✅ | Each Generator uses `dp::deterministic_rng(channel_id, T1.channel_event_id)` per EVT-A9; same input → same emit decision |

### 7.2 Replay-test corpus (CI gate)

Per [EVT-S5 replay against migrated schemas](../../07_event_model/11_schema_versioning.md#evt-s5--replay-against-migrated-schemas), schema bumps run replay-test gate. PL_005 + PL_005b suggest test corpus segments:

- **SPIKE_01 turn 5** (Speak with literacy slip) — verify ActualOutputs.canon_drift_flags reproducible
- **SPIKE_01 turn 8** (Give for lodging) — verify opinion delta + Chorus key-grant reaction reproducible
- **Synthetic Strike scenario** (V1+) — verify HpDelta clamp + MortalityTransition derivation reproducible
- **Synthetic Use:LexForbidden scenario** — verify Lex rejection reproducible across reality configs

---

## §8 V1 minimum implementation scope

What MUST work for PL_005 + PL_005b CANDIDATE-LOCK:

### 8.1 Vertical-slice path (top priority)

| AC ID | Scenario | Consumer features needed |
|---|---|---|
| **AC-INT-1** (PL_005 §16) | SPIKE_01 turn 5 SPEAK MULTI-NPC | NPC_001 + NPC_002 + WA_001 (no-op for Speak) |
| **AC-INT-SPK-1..4** (PL_005b §9.1) | All Speak edge cases | Same as AC-INT-1 |
| **AC-INT-2** + **AC-INT-GIV-1..3** | SPIKE_01 turn 8 GIVE + edge cases | NPC_001 + NPC_002 (no Item aggregate per B2; opinion-only outcomes) |
| **AC-INT-3** + **AC-INT-EXM-1..2** | EXAMINE Oracle + DeepStudy | A3 World Oracle (PL-16) integration |
| **AC-INT-4** + **AC-INT-USE-1** | SELF-USE wine | PCS_001 stat stub (status_flag) |
| **AC-INT-5** + **AC-INT-USE-3** | LEX REJECT | WA_001 Lex deployed with realistic axioms |
| **AC-INT-6** | TARGET UNREACHABLE | PL_001 cell state + entity_binding integration |

**Vertical-slice = 13 V1-testable scenarios from 22 total.** Minimum viable Interaction implementation runs against SPIKE_01 fixtures + small Lex test config.

### 8.2 Deferred to consumer features

| AC ID | Defers to |
|---|---|
| AC-INT-STK-1..3 (Strike scenarios) | V1+ combat feature + full PCS_001 mortality flow |
| AC-INT-USE-2 (heal potion) | V1+ Item substrate + per-item effect catalog |
| AC-INT-USE-4 (key on lock) | V1+ Item substrate + lock state aggregate |

### 8.3 V1 hardcoded simplifications

- NPC mortality = npc.flexible_state.liveness_flag placeholder (per B1) until NPC_003 ships
- Item refs = glossary-entity-id pointers only (per B2); no runtime Item aggregate
- Strike Stun/Restrain → reject as "intent_unsupported" V1
- Examine Hidden focus → reject V1
- Use:Combine → reject V1
- Multi-target Strike sweep → reject V1 (single direct_target only)

### 8.4 Vertical-slice acceptance gate

PL_005 + PL_005b → **CANDIDATE-LOCK** when all 13 V1-testable scenarios pass integration tests in world-service + roleplay-service deployed against SPIKE_01 fixture reality.

PL_005 + PL_005b → **LOCK** when V1+ scenarios pass after consumer features (Item aggregate, NPC_003 mortality, full combat) ship.

---

## §9 Phase 3 deferrals + landing points

Beyond [PL_005 §17](PL_005_interaction.md#17-open-questions-deferred--landing-point) (INT-D1..D9) + [PL_005b §10](PL_005b_interaction_contracts.md#10-phase-2-deferrals--landing-points) (INT-CON-D1..D8):

| ID | Question | Defer to |
|---|---|---|
| **INT-INT-D1** | Operator reconcile admin-cli command shape | V1+ admin tooling design |
| **INT-INT-D2** | mortality_config_version_at_strike forensic field | V2+ when schema versioning observed in production |
| **INT-INT-D3** | V1+ Respawn flow (Dying → Alive transition triggered by V1+30d scheduler) | PCS_001 design + scheduler service ship |
| **INT-INT-D4** | Generator graph topology audit at registration time | When first V1+ Generator (PoliceCallout / GriefDrift / RumorSeed / WitnessReport) ships |
| **INT-INT-D5** | Per-NPC-personality modifiers on opinion delta calibration | V1+ NPC personality system |
| **INT-INT-D6** | LLM sentiment classifier for Speak content (insult vs compliment) | V1+ NLP feature |
| **INT-INT-D7** | Cross-cell coordination when V2+ allows cross-cell Interaction | V2+ per INT-D8 in PL_005 §17 |
| **INT-INT-D8** | Idempotency-key composite at Aggregate-Owner level for Derived events | V1+ when concrete owner-service implements |

---

## §10 Cross-references

- [`PL_005 Interaction`](PL_005_interaction.md) — root file (§1-§19): conceptual layer + 4-role pattern + 5 V1 kind list + sequences
- [`PL_005b Interaction contracts`](PL_005b_interaction_contracts.md) — contracts (§1-§12): per-kind payload schemas + OutputDecl taxonomy + acceptance scenarios
- [`07_event_model/02_invariants.md`](../../07_event_model/02_invariants.md) EVT-A1..A12 — taxonomy + extensibility + RNG determinism (A9) + universal SSOT (A10)
- [`07_event_model/05_validator_pipeline.md`](../../07_event_model/05_validator_pipeline.md) EVT-V1..V7 — pipeline framework (V4 rejection-path; V6 post-commit side-effects; V7 dead-letter)
- [`07_event_model/08_scheduled_events.md`](../../07_event_model/08_scheduled_events.md) EVT-L11 — phasing for V1+30d scheduler (Respawn beat)
- [`07_event_model/11_schema_versioning.md`](../../07_event_model/11_schema_versioning.md) EVT-S5 — replay-test CI gate
- [`07_event_model/12_generation_framework.md`](../../07_event_model/12_generation_framework.md) EVT-G1..G6 — Generator Framework (G2 trigger sources / G3 cycle / G4 capacity / G5 coordinator)
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — sub-type ownership + aggregate ownership SSOT
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) §1.4 — `interaction.*` rule_id namespace
- [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) — current validator stage ordering
- [`PL_001 Continuum`](PL_001_continuum.md) §3.6 + §14 — entity_binding + idempotency cache
- [`PL_001b lifecycle`](PL_001b_continuum_lifecycle.md) §15 — rejection-path + idempotency
- [`PL_002 Grammar`](PL_002_command_grammar.md) — command-driven Interactions
- [`NPC_001 Cast`](../05_npc_systems/NPC_001_cast.md) — ActorId enum + NpcOpinion::for_pc
- [`NPC_002 Chorus`](../05_npc_systems/NPC_002_chorus.md) §6 + §11 — priority algorithm + multi-NPC reaction batching
- [`WA_001 Lex`](../02_world_authoring/WA_001_lex.md) — validator slot at stage 4; CRITICAL for Use kind
- [`WA_006 Mortality`](../02_world_authoring/WA_006_mortality.md) — mortality_config input to Strike outcomes
- [`PCS_001 brief`](../06_pc_systems/00_AGENT_BRIEF.md) §S4-S5 — pc_mortality_state + pc_stats_v1_stub aggregates
- [`SPIKE_01`](../_spikes/SPIKE_01_two_sessions_reality_time.md) turns 5 + 8 — replay-test corpus

---

## §11 Implementation readiness checklist

PL_005 + PL_005b + PL_005c combined satisfy DP-R2 + 22_feature_design_quickstart.md complete spec:

PL_005 (root, conceptual layer):
- [x] §1-§19 — see PL_005 §19 readiness checklist

PL_005b (contracts):
- [x] §1-§12 — see PL_005b §12 readiness checklist

PL_005c (this file, integration):
- [x] §1 Validator pipeline integration per kind (full chain detail)
- [x] §2 NPC_002 Chorus consumption flow (sequence + cascade depth + rejected-Interaction handling)
- [x] §3 PCS_001 mortality side-effect flow (Strike Lethal → MortalityTransition → state machine + V1 NPC placeholder + V1+ Respawn)
- [x] §4 NPC_001 opinion drift flow (sequence + per-kind opinion delta calibration + read-in-subsequent-reactions)
- [x] §5 V1+ Generator triggers (4 example Generators + capacity governance + cycle detection)
- [x] §6 Failure compensation (5 failure scenarios + operator reconcile + idempotency boundary)
- [x] §7 Replay determinism (5-layer scope table + replay-test CI corpus suggestions)
- [x] §8 V1 minimum implementation scope (vertical-slice 13 testable scenarios + deferred to consumer features + V1 hardcoded simplifications + acceptance gate)
- [x] §9 Phase 3 deferrals INT-INT-D1..D8 (8 items)
- [x] §10 Cross-references
- [x] §11 Readiness (this section)

**Status transition:** PL_005 + PL_005b + PL_005c all DRAFT 2026-04-26 → **CANDIDATE-LOCK** when 13 V1-testable acceptance scenarios pass integration tests against SPIKE_01 fixtures → **LOCK** when V1+ scenarios pass after consumer features ship.

**Total acceptance scenarios:** 22 (6 PL_005 + 16 PL_005b). V1-testable: 13. V1+ deferred: 9.

**Total deferral IDs:** INT-D1..D9 (PL_005) + INT-CON-D1..D8 (PL_005b) + INT-INT-D1..D8 (PL_005c) = 25 deferrals across 3 files; each cites concrete landing point.

**Next** (when CANDIDATE-LOCK granted): integration-test harness spec + admin-cli reconcile command design + V1+ Generator first concrete instance (likely RumorSeed for SPIKE_01 turn 5 canon-drift propagation) — but those are V1+ work, not PL_005 design scope.
