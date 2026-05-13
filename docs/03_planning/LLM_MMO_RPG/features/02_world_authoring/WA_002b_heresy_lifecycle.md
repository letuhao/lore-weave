# WA_002b — Heresy Lifecycle (Sequences + Acceptance Criteria)

> **Continued from:** [`WA_002_heresy.md`](WA_002_heresy.md). That file holds the contract layer (§1-§10): user story, domain concepts, EVT mapping, aggregate inventory, tier+scope, DP primitives, validator pipeline integration, WorldStability state machine, pattern choices, failure-mode UX, cross-service handoff. This file holds the dynamic layer (§11-§17): worked sequences, acceptance criteria, deferrals, cross-references, readiness.
>
> **Conversational name:** "Heresy lifecycle" (HER-L). Read [`WA_002_heresy.md`](WA_002_heresy.md) FIRST — this file assumes you know the aggregates, validator slot, state machine, and pattern choices.
>
> **Category:** WA — World Authoring
> **Status:** **CANDIDATE-LOCK 2026-04-25** (split from WA_002 to honor 800-line cap during closure pass; §14 acceptance criteria added — 10 scenarios)
> **Stable IDs in this file:** none new — all aggregates/concepts defined in WA_002 (root). This file references them.
> **Builds on:** WA_002 §1-§10. Same DP contracts (DP-A1..A19, DP-T0..T3, DP-R1..R8, DP-K1..K12, DP-Ch1..Ch53) + Lex (WA_001) + LexConfig schema v1→v2 bump.

---

## §11 Sequence: contamination allowed (Scenario A — within budget)

```text
PC `pc_protagonist` in reality `R-modern-earth-2026` types:
    "Tôi giơ tay, hô: Hỏa cầu thuật!"

LexConfig:
    energy_system: None
    axioms: [{ MagicSpells, AllowedWithBudget(template) }]
    default_disposition: Restrictive

ActorContaminationDecl(pc_protagonist, MagicSpells):
    budget: { max_per_fiction_day: 3, max_total_lifetime: 100 }
    energy_substrate: ConvertWorldEnergy { efficiency: 0.10 }
    cascade_on_exceeded: RejectAndStrainWorld

ActorContaminationState(pc_protagonist, MagicSpells):
    usage_today: 1   (already used once today)
    usage_lifetime: 47

CurrentFictionClock: 2026-thu-day10-Tý-sơ

──────────────────────────────────
gateway → roleplay → LLM → world-service
    schema, capability, A5, A6-sanitize all pass
    │
    ▼
★ lex_check ★
    classify: kinds = [MagicSpells]
    axiom MagicSpells → Allowance::AllowedWithBudget(template)
    → defer to Heresy
    │
    ▼
★ heresy_check ★
    read decl: budget {3/day, 100/life}, ConvertWorldEnergy@0.10, RejectAndStrainWorld
    read state: today=1, lifetime=47, day_marker=2026-thu-day10
    daily reset? day_marker == current → no reset
    daily check: 1 < 3 ✓
    lifetime check: 47 < 100 ✓
    pass
    queue post-commit: [
      IncrementContaminationState(today+1, lifetime+1),
      AddWorldStrain(amount=strain_calc(0.10, Tier1Spell))
    ]
    │
    ▼
A6 output filter, canon-drift pass
    │
    ▼
advance_turn(PlayerTurn, outcome=Accepted)
    turn_number advances
    fiction_clock advances by ~5s
    │
    ▼
post-commit side-effects:
    t2_write ActorContaminationState(usage_today=2, usage_lifetime=48)
    t2_write WorldStability strain += 9   (assuming strain_calc returns 9)

UI:
    PC's TurnEvent renders:
      "Lý Minh giơ tay. Lửa hồng bùng nổ giữa không trung — không khí xung quanh
       như chùng xuống một nhịp lạ."
      (LLM is briefed with energy_substrate=ConvertWorldEnergy → narrates the
       world-strain hint)
```

---

## §12 Sequence: contamination exceeded (Scenario A2 — cascade=RejectAndStrainWorld)

Same setup as §11, but `usage_today=3` already (PC has used the daily allowance).

```text
★ heresy_check ★
    daily check: 3 >= 3 → DailyBudgetExceeded
    cascade = RejectAndStrainWorld
    return Err(HeresyViolation::DailyBudgetExceeded {
        actor: pc_protagonist, kind: MagicSpells,
        current: 3, cap: 3,
        cascade: RejectAndStrainWorld,
    })
    │
    ▼
PL_001 §15 rejection path:
    build TurnEvent {
        actor: pc_protagonist,
        intent: Speak,
        narrator_text: None,
        outcome: Rejected { reason: WorldRuleViolation {
            rule_id: "heresy.budget_daily.MagicSpells",
            detail: "Hôm nay bạn đã dùng ma pháp đủ rồi. Hãy đợi đến mai."
        }},
        ...
    }
    dp::t2_write::<TurnEvent>(...) → turn_number unchanged

    POST-REJECT side-effect (per cascade=RejectAndStrainWorld):
        t2_write WorldStability strain += 3   (smaller bump than successful use)

UI:
    Modal: "⚠ Hôm nay bạn đã dùng ma pháp đủ rồi. Hãy đợi đến mai."
    (PC may try a different action freely; turn-slot already released by validator pipeline.)

(No LLM call was made — heresy_check rejected before A6 output filter.)
```

---

## §13 Sequence: stage transition (V1 admin-driven)

After 200 strain accumulated, operator decides reality should advance:

```text
admin-cli operator:
    lw admin world-stability advance \
        --reality R-modern-earth-2026 \
        --to "Cracking{1}" \
        --reason "uncontrolled MagicSpells use; warning shot"

S5 dual-actor enforcement:
    operator A initiates → operator B approves within 60s
    capability check ✓

world-service:
    ① t3_write WorldStability {
         current_stage: Cracking { stage: 1 },
         strain_accumulator: 217,
         stage_entered_at_turn: <current_turn>,
         stage_entered_at_fiction_time: <current_fiction>,
         stage_entered_by: AdminId(<op_a>),
         stage_history: append({from: Strained, to: Cracking{1}, ...}),
       }
    ② advance_turn(
         &ChannelId::reality_root(R-modern-earth-2026),
         turn_data: TurnEvent::WorldTick {
             kind: StabilityTransition,
             from: Strained, to: Cracking{1},
             reason: "uncontrolled MagicSpells use",
         },
         causal_refs: [<admin_action_event_id>]
       )
    ③ emit EVT-T8 AdminAction
    │
    ▼
DP bubble-up aggregators at each channel level emit derivative ambient events
    (continent: "the very air is unsettled"; cells: NPC ambient updates)
    │
    ▼
UI multiplex stream delivers Cracking{1} event
    Banner: (none — stage 1 is "subtle"; only NPC narration changes)
    NPC narration prompts now include `world_stability=Cracking{1}` for tone shift
```

---

## §14 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service can pass these scenarios. Each scenario is one row in the integration test suite. LOCK is granted after all 10 pass.

### 14.1 Happy-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-HER-1 WITHIN-BUDGET ALLOWED** | Setup §11 (PC `pc_protagonist`, MagicSpells with `usage_today=1`, budget 3/day + 100/life, `ConvertWorldEnergy{efficiency: 0.10}`, cascade `RejectAndStrainWorld`); PC submits a Fireball turn. | `heresy_check` passes; PlayerTurn commits with `outcome=Accepted`; post-commit side-effects fire: `ActorContaminationState.usage_today=2, usage_lifetime=48`; `WorldStability.strain_accumulator += strain_calc(0.10, Tier1Spell)`. UI sees turn rendered with world-strain narrative hint. |
| **AC-HER-2 NO DECL → LEX FORBIDS** | Reality has `LexConfig { MagicSpells: AllowedWithBudget(template) }` but NO matching `ContaminationDecl` for the requesting PC. | Lex returns `AllowedWithBudget`, defers to Heresy; Heresy reads no matching ContaminationDecl; falls back to Lex template behavior — per §1 Scenario B logic, request is rejected as if Forbidden (Heresy doesn't grant the actor an exception they don't have). Reject `rule_id: "heresy.no_decl.MagicSpells"`. PC effectively a mortal in this reality without an explicit declaration. |
| **AC-HER-3 LEX FORBIDDEN SHORT-CIRCUITS** | Reality has `LexConfig { MagicSpells: Forbidden }` (NOT AllowedWithBudget); PC tries Fireball. | Lex rejects directly with `rule_id: "lex.ability_forbidden.magic_spells"`; Heresy validator NEVER consulted (per §6.1 slot ordering: Lex → Forbidden → reject; AllowedWithBudget → defer to Heresy). |

### 14.2 Failure-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-HER-4 DAILY BUDGET EXCEEDED** | Setup §12 (same as §11 but `usage_today=3`); PC submits Fireball. | `heresy_check` returns `Err(DailyBudgetExceeded { current: 3, cap: 3, cascade: RejectAndStrainWorld })`; PL_001 §15 rejection path commits TurnEvent `outcome=Rejected` with `rule_id: "heresy.budget_daily.MagicSpells"`; `turn_number` UNCHANGED; `fiction_clock` UNCHANGED; POST-REJECT side-effect adds smaller strain bump (per cascade RejectAndStrainWorld). |
| **AC-HER-5 LIFETIME BUDGET EXCEEDED** | Setup similar; `usage_lifetime=100, cap=100`. | `heresy_check` returns `Err(LifetimeBudgetExceeded { current: 100, cap: 100, cascade: RejectAndStrainWorld })`; rejection path with `rule_id: "heresy.budget_lifetime.MagicSpells"`. PC permanently unable to use this contamination kind in this reality; V2+ may add reset/recovery quests. |
| **AC-HER-6 ALLOW-AND-STRAIN CASCADE** | Author opts into `cascade_on_exceeded: AllowAndStrainWorld` (dangerous mode); PC at `usage_today=3, cap=3` submits Fireball. | `heresy_check` detects cap exceeded but cascade says ALLOW; pipeline continues; PlayerTurn commits with `outcome=Accepted`; post-commit side-effects increment ContaminationState (now `usage_today=4, lifetime+=1`) AND apply 2× strain bump (penalty for over-cap use). The "burn it down" mode works as documented in §8. |
| **AC-HER-7 DAILY RESET ON DAY BOUNDARY** | PC at `usage_today=3, day_marker=2026-thu-day10`; fiction-clock advances to `2026-thu-day11-Tý-sơ` via other PCs' turns; PC submits Fireball. | `heresy_check` reads state, computes `state.day_marker.day_of_season < current_fiction_clock.day_of_season` → applies daily reset (`usage_today=0, day_marker=2026-thu-day11`); subsequent budget check `0 < 3` passes; Fireball allowed; ContaminationState updates to `usage_today=1, day_marker=day11`. |

### 14.3 Boundary scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-HER-8 STAGE TRANSITION ADMIN-DRIVEN** | Setup §13 (strain_accumulator=217, current_stage=Strained); operator A initiates `lw admin world-stability advance --to "Cracking{1}"`; operator B approves within 60s. | S5 dual-actor enforcement passes; `t3_write WorldStability { current_stage: Cracking{1}, strain_accumulator: 217, stage_history: [..., {from: Strained, to: Cracking{1}, by: op_a, approver: op_b}] }`; advance_turn at reality root with WorldTick payload; bubble-up propagates to all descendant cells; NPC narration prompts thereafter include `world_stability=Cracking{1}` for tone shift. |
| **AC-HER-9 CONCURRENT CONTAMINATION** | Two PCs (`pc_a`, `pc_b`) in same reality both submit Fireball turns simultaneously (within 50ms). | Each turn's heresy_check reads state, increments independently; world-service serializes the two POST-COMMIT writes to `WorldStability.strain_accumulator` correctly (no race; final strain = base + strain_a + strain_b, not lost-update). Verified by `read_projection_reality::<WorldStability>` returning the accumulated total. |
| **AC-HER-10 SHATTERED TERMINAL** | WorldStability is `Shattered` (terminal); PC submits any contaminating action. | Heresy detects `world_stability.current_stage == Shattered`; rejects with `rule_id: "heresy.world_shattered"`; reality is unplayable per §7.3 monotonic-terminal property. New transfers (PLT_002 Succession) blocked; pending transfers in flight forced-abort. V2+ canon-fork (DF8) is the only recovery path. |

**Lock criterion:** all 10 scenarios have a corresponding integration test that passes. Until then, status is `CANDIDATE-LOCK` (post-acceptance criteria) → `LOCKED` (after tests).

---

## §15 Open questions deferred

| ID | Question | Defer to |
|---|---|---|
| HER-D1 | Auto-cascade thresholds for stage transitions (V1 admin-only) | V2+ ops; needs prototype telemetry to tune thresholds |
| HER-D2 | Strain decay over fiction-time (natural healing) | V2+; needs MV12-D10 NPC routine model + FictionClock tick subscription |
| HER-D3 | Recovery quests (narrative path to lower stage) | V2+; depends on quest engine landing |
| HER-D4 | NPC contamination support (canonical NPC transmigrators) | V2+; CanonicalActorDecl extension |
| HER-D5 | Energy cost validation (mana cost vs PC mana pool) | depends on PCS_001 + DF7 PC stats |
| HER-D6 | Per-fiction-week / per-fiction-month budget windows | V2+ extension to BudgetSpec |
| HER-D7 | Multi-actor strain aggregation (N transmigrators in same reality compound risk) | V2+ — needs cross-actor accounting model |
| HER-D8 | EVT-T11 WorldTick V1+30d activation; for V1 stage transitions, may emit as EVT-T8 AdminAction only | **Tracked in [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) §6.1 / §6 drift-resolutions** (V1 = AdminAction-only; V1+30d = WorldTick activation per event-model agent's Phase 4 `08_scheduled_events.md`). The boundary folder is the single source of truth; this row is audit-trail. |
| HER-D9 | LexSchema v1 → v2 migration sequencing (deploy v2 readers before any v2 writer) | implementation phase ops (NOT a design boundary — operational concern only; not tracked in `_boundaries/`) |
| HER-D10 | Author UI for editing ContaminationDecl + WorldStability monitoring | Resolved by [WA_003 Forge](WA_003_forge.md) (PROVISIONAL — generic patterns may extract to future CC_NNN_*) |
| HER-D11 | Shattered reality lifecycle: PC extraction protocol; reality archival | DF8 canon-fork (V3+) |
| HER-D12 | Cross-reality contamination accounting (multi-reality transmigrator) | DF12 (withdrawn V1; not currently planned) |

---

## §16 Cross-references

- [WA_002 Heresy](WA_002_heresy.md) — root file (§1-§10): contract layer
- [WA_001 Lex](WA_001_lex.md) — companion feature; provides `AxiomKind` closed set + `Allowance` enum extension point + `classify_action` shared function
- [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) — §15 rejection path contract; reality root channel for WorldTick emission; `fiction_clock` for daily reset
- [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) — reject copy table format (Vietnamese + English)
- [NPC_002 Chorus](../05_npc_systems/NPC_002_chorus.md) — V2+: NPC reactions to `world_stability` stage; their persona prompts include stage hint
- [05_llm_safety/](../../05_llm_safety/) — A6 canon-drift sibling; canon-drift may catch contamination narratives that bypass classification
- [07_event_model/02_invariants.md](../../07_event_model/02_invariants.md) — EVT-A3 (validated events for canonical writes), EVT-A6 (causal-refs)
- [07_event_model/03_event_taxonomy.md](../../07_event_model/03_event_taxonomy.md) — EVT-T3 AggregateMutation (state increments + strain bump), EVT-T8 AdminAction (stage transitions V1), EVT-T11 WorldTick (stage transitions V1+30d/V2+)
- [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) — slot ordering for Heresy proposed §6.1 + drift-resolution authority for HER-D8
- [decisions/deferred_DF01_DF15.md](../../decisions/deferred_DF01_DF15.md) — DF4 World Rules umbrella (this is a sub-feature)
- [decisions/locked_decisions.md](../../decisions/locked_decisions.md) — PC-A3, PC-E3 paradox-allowance (relates to Heresy permissive cases)
- [02_storage/S05_admin_command_classification.md] — S5 admin action policy (stage transitions via admin path)
- [03_multiverse/01_four_layer_canon.md](../../03_multiverse/) — L1/L2/L3/L4 canon layers; `world_stability=Shattered` likely promotes to L1 frozen
- [features/_spikes/SPIKE_01_two_sessions_reality_time.md](../_spikes/SPIKE_01_two_sessions_reality_time.md) — Lý Minh xuyên không scenario; concrete grounding (though V1 SPIKE_01 doesn't have hard-contamination because TĐĐH allows wuxia abilities natively)

---

## §17 Implementation readiness checklist

Combined check across WA_002 (root) + WA_002b (this file). Both files together satisfy every required item per DP-R2 + 22_feature_design_quickstart.md §"Required feature doc contents":

WA_002 (root):

- [x] **§2** Domain concepts (Allowance, ContaminationDecl, ContaminationState, BudgetSpec, EnergySubstrate, CascadeOnExceeded, WorldStability)
- [x] **§2.5** EVT-T* mapping (validator + EVT-T3 side-effects + EVT-T11/T8 stage transitions)
- [x] **§3** Aggregate inventory (3 new + 1 schema bump): `actor_contamination_decl` (T2/Reality), `actor_contamination_state` (T2/Reality), `world_stability` (T3/Reality), `lex_config` schema v2
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** Validator pipeline integration (slot AFTER Lex; algorithm spec; cascade behavior table)
- [x] **§7** WorldStability state machine (5 stages; Shattered terminal; V1 admin-driven transitions; thresholds advisory only V1)
- [x] **§8** Pattern choices (V1 budget-only; cascade data-only; explicit author decls; PC-primary; monotonic strain)
- [x] **§9** Per-violation Vietnamese + English reject copy + stage transition banner copy
- [x] **§10** Cross-service handoff (validator hot path; stage admin path; LexSchema migration)

WA_002b (this file):

- [x] **§11** Sequence: contamination allowed (within budget)
- [x] **§12** Sequence: contamination exceeded (RejectAndStrainWorld cascade)
- [x] **§13** Sequence: V1 admin-driven stage transition
- [x] **§14** Acceptance criteria (10 scenarios across happy-path / failure-path / boundary)
- [x] **§15** Deferrals (HER-D1..D12); HER-D8 hybrid-tracked in `_boundaries/`; HER-D9 implementation-phase concern only
- [x] **§16** Cross-references (incl. authoritative pointer at `_boundaries/03_validator_pipeline_slots.md`)

**Status transition:** DRAFT (2026-04-25 first commit `9c49b09`) → split (2026-04-25 closure pass) → **CANDIDATE-LOCK** (2026-04-25 after §14 acceptance criteria locked).

LOCK granted after all 10 §14 acceptance scenarios have a passing integration test.

**Resolves WA_001 deferrals:** LX-D1 (per-actor exception system) ✓, LX-D2 (budget model) ✓, LX-D3 (cascade-consequence) ✓.

**Drift watchpoints active:**
- HER-D8 — V1 emission path (AdminAction vs WorldTick) — boundary-folder authoritative
- HER-D9 — LexSchema migration — implementation/ops concern
- LX-D5 (inherited from WA_001) — Lex slot ordering with event-model Phase 3

**Next** (when this doc locks): world-service implements `heresy_check` validator + queued post-commit side-effects + admin-stage-transition handler; book-ingestion pipeline (knowledge-service) extends RealityManifest with `contamination_allowances`; admin-cli adds `lw admin world-stability advance` subcommand. Vertical-slice target: hypothetical reality with one transmigrator-PC declared → 3 successful spells + 1 over-budget reject + 1 admin-triggered stage transition reproduces deterministically, matching AC-HER-1 + AC-HER-4 + AC-HER-8.
