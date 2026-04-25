# WA_006 — Mortality (Death Model)

> **⚠ OVER-EXTENSION NOTICE (added 2026-04-25, post-DRAFT review):** This feature design was flagged as over-extended into territories owned by other features. Specifically:
>
> | Section | Content | Should be owned by |
> |---|---|---|
> | §3.2 | `pc_mortality_state` aggregate (per-PC state) | **PCS_001** (PC substrate, when designed) |
> | §6.1 | LLM death-detection sub-validator (keyword match in A6 output filter) | **05_llm_safety** (A6 internals) |
> | §6.3 | Hot-path mortality check on every turn submission | **PL_001 / PL_002** (turn submission flow) |
> | §7.2, §10.2 | Respawn sweeper task + sweeper-driven Dying→Alive transition + move_session_to_channel | **PL_001 / PCS_001** (lifecycle + PC state) |
> | §9.1 | False-positive dispute flow (admin review queue) | **05_llm_safety** + admin-tooling |
>
> **Legitimate WA_006 scope** when rewritten will be:
> - §3.1 `mortality_config` aggregate (per-reality singleton; author-declared) ✓
> - §7 closed-set `DeathMode` enum (Permadeath / RespawnAtLocation / Ghost) ✓
> - V1 default = Permadeath ✓
> - Per-PC overrides via Forge ✓
> - Cross-references to where mechanics live (no design of those mechanics here)
>
> **Status:** PROVISIONAL. Pending rewrite to a thin config-only feature (~180 lines instead of 730). Until rewritten, the over-extended sections are advisory only — feature owners (PCS_001, 05_llm_safety, PL_001) may revise when they take over the relevant aggregates / validators / hot paths.
>
> The user explicitly chose to defer the rewrite to keep working momentum; this notice is the marker. See review thread 2026-04-25 in conversation history.
>
> ---
>
> **Conversational name:** "Mortality" (MOR). Per-reality declaration of what happens when a PC dies — Permadeath / RespawnAtLocation / Ghost — plus the death-trigger detection layer (LLM-narrated death or admin-forced) and the post-death state aggregate. Resolves PC-B1 + PC-A3 + PC-E3 locked decisions.
>
> **Category:** WA — World Authoring
> **Status:** DRAFT 2026-04-25
> **Catalog refs:** **DF4 World Rules** (sub-feature: PC death behavior). Resolves [PC-B1](../../decisions/locked_decisions.md) (PC death behavior) + partial [PC-E3](../../decisions/locked_decisions.md) (paradox acceptance — death is the most extreme paradox case).
> **Builds on:** [WA_001 Lex](WA_001_lex.md) (companion validator slot pattern), [WA_002 Heresy](WA_002_heresy.md) (Catastrophic/Shattered cascade may trigger mass death V2+), [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) (uses scaffold; death is committed as a TurnEvent extension), [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) (rejection copy pattern), [05_llm_safety/](../../05_llm_safety/) A6 output filter (where LLM-narrated death detection lives)
> **Defers to:** future PCS_001 for `PcId` + HP/stats system + combat death; future DL_001 for NPC-conversion mode (NPC-8 catalog).

---

## §1 User story (concrete)

**Scenario A — Permadeath in wuxia (V1 default):**

Reality `R-tdd-h-2026-04`. MortalityConfig:
- `default_death_mode: Permadeath`

PC `Lý Minh` is in a brawl. LLM narrates: "Lưỡi đao cứa qua cổ Lý Minh, máu phun ra... anh gục xuống, hơi thở dứt..."

A6 output filter death-detection sub-validator catches the death keywords + scene context → flags `death_trigger: { actor: pc_ly_minh, kind: NarrativeDeath }`. world-service:
1. Commits the LLM PlayerTurn normally (with `outcome=Accepted`)
2. POST-COMMIT: emits a separate `MortalityDeath` event tagged on the actor
3. Updates `pc_mortality_state(pc_ly_minh) = Dead { mode: Permadeath, died_at_turn: N, died_at_cell: C }`
4. Bumps `forge_roles_version` for the user → next session bind shows the PC as dead
5. UI receives via subscribe: scene shows Lý Minh's body; PC's player gets terminal modal: "Lý Minh đã hy sinh. Thực tại này theo chế độ Permadeath — bạn không thể tiếp tục với nhân vật này."

Player can create a NEW PC in the same reality (subject to author rules) but Lý Minh is gone.

**Scenario B — Respawn in a more forgiving fantasy reality:**

Reality `R-fantasy-tutorial`. MortalityConfig:
- `default_death_mode: RespawnAtLocation { spawn_cell: town_square, fiction_delay_days: 1 }`

Same PC dies in a brawl. Death-trigger fires. world-service:
1. Same PlayerTurn commit + MortalityDeath event
2. PC enters `Dying { mode: RespawnAtLocation, will_respawn_at_fiction_time: <current+1d>, spawn_cell }` state
3. PC's session is paused; UI shows "Bạn đã ngã xuống. Hồi sinh sau 1 ngày..."
4. Background sweeper checks every fiction-clock advance; when `will_respawn_at_fiction_time <= current_fiction_clock`, transitions to `Alive` state
5. PC respawns at `spawn_cell`; emits a `MortalityRespawn` event; UI shows "Bạn tỉnh dậy ở quảng trường... ký ức cuối cùng là cảnh máu và đau..."

**Scenario C — Ghost mode in narrative-driven realities:**

Reality `R-narrative-mystery`. MortalityConfig:
- `default_death_mode: Ghost`

PC dies. Becomes a ghost spectator:
1. `pc_mortality_state = Dead { mode: Ghost, died_at_turn: N }`
2. PC retains read-only access: subscribe streams continue; can see scene events
3. PC cannot submit turns; UI shows "Bạn là một bóng ma. Chỉ có thể quan sát."
4. Other PCs / NPCs cannot interact with the ghost (V1 stub; V2+ may add ghost-NPC interaction)
5. Ghost can be exorcised / freed by world events (V2+ resurrection paths)

**This feature design specifies:** the closed-set DeathMode enum; the death-trigger detection layer (LLM-narrated + admin-forced); the `pc_mortality_state` aggregate state machine; the post-death effects per mode; the V1 default behavior (Permadeath); per-PC overrides (V2+); and integration with existing PC turn-submission flow.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **DeathMode** | Closed enum: `Permadeath \| RespawnAtLocation { spawn_cell, fiction_delay_days } \| Ghost` | V1: 3 modes. V2+: Reincarnation, NpcConversion (depends on PCS_001 / DL_001). |
| **MortalityConfig** | Per-reality declaration of default DeathMode + per-PC overrides | One row per reality. Default = `Permadeath` if no config exists. |
| **MortalityState** | Per-PC current state | `Alive \| Dying { will_respawn_at } \| Dead { mode, died_at } \| Ghost`. |
| **DeathTrigger** | What caused the death | Closed set: `NarrativeDeath` (LLM-detected) \| `AdminForced` \| `WorldShatterCascade` (V2+) \| `CombatDamage` (V2+ — depends on PCS_001 HP system). |
| **DeathTriggerDetector** | A6 output filter sub-validator that scans LLM-narrated turns for death keywords + scene context | V1: deterministic keyword match + LLM-confidence threshold. V2+: dedicated death-classifier model. |
| **RespawnTrigger** | Background sweeper task that wakes PCs in `Dying` state when fiction-clock crosses their respawn time | Hourly sweep cadence V1 (matches WA_005 Succession sweeper pattern). |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11)

| Mortality output | EVT-T* | Producer | Notes |
|---|---|---|---|
| Death detected during PC turn | (the original turn commits as normal) **EVT-T1** PlayerTurn | normal pipeline | Death is a SIDE-EFFECT, not a replacement event. |
| Death event emitted post-commit | **EVT-T3** AggregateMutation on `pc_mortality_state` (causal_ref to the triggering PlayerTurn) | world-service post-validator | New sub-shape: `MortalityDeath { mode, trigger_kind }`. |
| Admin-forced death | **EVT-T8** AdminAction (sub-shape `MortalityAdminKill`) + EVT-T3 mutation as side-effect | admin-cli via S5 dual-actor | Tier1 ImpactClass per WA_003. |
| Respawn (sweeper-triggered) | **EVT-T3** AggregateMutation on `pc_mortality_state` (transition Dying → Alive) | world-service sweeper | New sub-shape: `MortalityRespawn`. PC re-bound to spawn_cell via PL_001 §13 move pattern. |
| Mass-death cascade (Catastrophic / Shattered Heresy stage transition) | per-PC **EVT-T3** AggregateMutations + sweeper batch | world-service responding to WorldStability transition | V2+ only (deferred MOR-D5). |

---

## §3 Aggregate inventory

Two new aggregates.

### 3.1 `mortality_config`

```rust
#[derive(Aggregate)]
#[dp(type_name = "mortality_config", tier = "T2", scope = "reality")]
pub struct MortalityConfig {
    pub reality_id: RealityId,                       // singleton per reality
    pub default_death_mode: DeathMode,
    pub per_pc_overrides: Vec<MortalityOverride>,    // V1: empty Vec by default; author may declare
    pub schema_version: u32,
}

pub enum DeathMode {
    Permadeath,                                       // V1 default for any new reality
    RespawnAtLocation {
        spawn_cell: ChannelId,                        // existing cell channel
        fiction_delay_days: u32,                      // 0..=30 V1
        memory_retention: MemoryRetention,            // FullMemory | LastNDays(u32) | NoMemory
    },
    Ghost,                                            // become spectator; no turn submissions
}

pub enum MemoryRetention {
    FullMemory,                                       // V1 default for RespawnAtLocation
    LastNDays(u32),                                   // V2+
    NoMemory,                                         // V2+
}

pub struct MortalityOverride {
    pub pc_id: PcId,
    pub mode: DeathMode,                              // overrides the default for this specific PC
    pub note: Option<String>,                         // author rationale
}
```

- T2 + RealityScoped: per-reality singleton; small (~5 KB typical).
- Read at every death-trigger detection; cached for 5 minutes per world-service node.
- Default = `Permadeath` if no `MortalityConfig` exists at all (no row in the table).

### 3.2 `pc_mortality_state`

```rust
#[derive(Aggregate)]
#[dp(type_name = "pc_mortality_state", tier = "T2", scope = "reality")]
pub struct PcMortalityState {
    #[dp(indexed)] pub pc_id: PcId,                   // primary key per (reality, pc)
    pub state: MortalityState,
    pub last_transition_at_turn: u64,
    pub last_transition_at_fiction_time: FictionTimeTuple,
    pub history: Vec<MortalityTransition>,            // up to 10 most recent transitions
}

pub enum MortalityState {
    Alive,
    Dying {                                           // RespawnAtLocation mode only
        will_respawn_at_fiction_time: FictionTimeTuple,
        spawn_cell: ChannelId,
        died_at_cell: ChannelId,
        death_trigger: DeathTrigger,
    },
    Dead {                                            // Permadeath mode (terminal)
        mode: DeathMode,                              // always Permadeath here
        died_at_turn: u64,
        died_at_cell: ChannelId,
        death_trigger: DeathTrigger,
    },
    Ghost {                                           // Ghost mode (read-only-spectator; not strictly "dead")
        died_at_turn: u64,
        died_at_cell: ChannelId,
        death_trigger: DeathTrigger,
    },
}

pub enum DeathTrigger {
    NarrativeDeath {                                  // LLM-narrated; A6 detected
        triggering_turn_event_id: u64,                // the PlayerTurn or NPCTurn that contained the death narration
        detection_confidence: f32,                    // 0.0..=1.0; A6's confidence score
    },
    AdminForced {                                     // admin-cli /kill
        admin_user_id: UserId,
        reason: String,
    },
    // V2+ variants (not in V1 closed set):
    // WorldShatterCascade,
    // CombatDamage { final_blow_actor: ActorId },
}

pub struct MortalityTransition {
    pub from_state: MortalityState,
    pub to_state: MortalityState,
    pub at_turn: u64,
    pub at_fiction_time: FictionTimeTuple,
    pub trigger: DeathTrigger,                        // for Alive→Dying/Dead/Ghost; ignored for Dying→Alive (respawn)
}
```

- T2 + RealityScoped: per-PC state; durable; ~2-5 KB per row.
- Default = `Alive` if no row exists (lazy-create on first death).
- Read at every PC turn submission (per §6.3 hot-path check); cached aggressively.

### 3.3 References (no other new aggregates)

- **`forge_audit_log`** (WA_003): MortalityConfig edits + admin kills logged here
- **`actor_binding`** (PL_001 §3.6): updated on respawn (PC moves to spawn_cell)
- **`npc_session_memory`** (R8 / NPC_001): NPCs in the cell remember the death (post-Mortality V2+ adds emotional memory facets)

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `mortality_config` | T2 | T2 | Reality | ~1/turn (cached >95%) for death-trigger lookup | rare (author edits) | Per-reality singleton; durable; eventual consistency on edit OK. |
| `pc_mortality_state` | T2 | T2 | Reality | ~1/turn for active PCs (cached) | rare (transitions only) | Per-PC durable; lazy-created on first death. |

No T0/T1/T3 in this feature. Death is a major canon event but doesn't require T3 atomicity (single-aggregate write per transition; eventual consistency on read OK during the ~1s projection lag).

---

## §5 DP primitives this feature calls

### 5.1 Reads

```rust
// Per turn submission (PL_001 §11 hot path)
let mortality = dp::read_projection_reality::<PcMortalityState>(
    ctx,
    PcMortalityStateId::derive(pc_id),
    wait_for=None, ...
).await?.unwrap_or_default();  // default = Alive

// At death-trigger time
let config = dp::read_projection_reality::<MortalityConfig>(
    ctx,
    MortalityConfigId::singleton(reality_id),
    wait_for=None, ...
).await?.unwrap_or_default();  // default = MortalityConfig { default_death_mode: Permadeath, ... }
```

### 5.2 Writes (death transition)

```rust
// On detected death (post the triggering PlayerTurn commit)
dp::t2_write::<PcMortalityState>(ctx, state_id, MortalityDelta::Transition {
    new_state: MortalityState::Dead { mode: Permadeath, died_at_turn, ... },
    trigger,
}).await?;

// Side-effect EVT-T3 emission via event log:
// (no separate advance_turn here — the t2_write itself commits the channel event with causal_ref)
```

### 5.3 Writes (respawn — sweeper)

```rust
// Sweeper finds PCs in Dying state where will_respawn_at_fiction_time <= current_fiction_clock
dp::t2_write::<PcMortalityState>(ctx, state_id, MortalityDelta::Transition {
    new_state: MortalityState::Alive,
    trigger: /* respawn — uses last transition's trigger for history */,
}).await?;

// Move PC to spawn_cell (PL_001 §13 pattern)
dp::move_session_to_channel(ctx, &spawn_cell).await?;
```

### 5.4 Admin force-kill

```rust
// Admin via S5 dual-actor
dp::advance_turn(ctx, &ChannelId::reality_root(reality_id),
    TurnEvent::AdminAction { sub_shape: MortalityAdminKill { ... } }, ...).await?;
// Then proceeds same as detected death path.
```

---

## §6 Death-trigger detection layer

Death is detected by ONE of two paths in V1:

### 6.1 LLM-narrated death (most common path)

Lives inside A6 output filter (PL-20 catalog). When PL_001 / PL_003 commits a PlayerTurn or NPCTurn with `narrator_text`, A6 runs a sub-validator:

```text
fn detect_death(narrator_text: &str, scene_state: &SceneState, current_actors: &[ActorId])
    -> Option<DeathDetection>
{
    // V1: deterministic keyword match + LLM confidence
    let death_keywords_vi = ["chết", "ngã xuống", "tắt thở", "hơi thở dứt", "máu phun", "qua đời", ...];
    let death_keywords_en = ["died", "perished", "fell dead", "killed", "slain", ...];

    let matches: Vec<_> = find_keyword_matches(narrator_text, death_keywords_vi, death_keywords_en);
    if matches.is_empty() { return None; }

    // For each match, identify the SUBJECT actor
    for match in matches {
        let subject = identify_subject_actor(match, scene_state, current_actors);
        if let Some(actor) = subject {
            return Some(DeathDetection {
                actor,
                detection_confidence: 0.85,                        // V1 fixed; V2+ classifier-driven
                triggering_excerpt: narrator_text[match.range].to_string(),
            });
        }
    }
    None
}
```

V2+ (MOR-D6): replace deterministic keyword match with a dedicated death-classifier LLM call. V1 keyword approach has false-positive risk ("PC laughed to death" idiom) — mitigation: false-positive correction flow §9.

### 6.2 Admin force-kill

```text
admin-cli operator → POST /v1/admin/.../mortality/force-kill
    body: { pc_id, reason }
    │
S5 dual-actor: requires operator B approval within 5min
    │
on approval:
    advance_turn at reality root: AdminAction MortalityAdminKill
    proceeds as detected death (same post-commit handler)
```

### 6.3 Hot-path check on every turn submission

Before processing a PC turn (PL_001 §11), world-service checks `pc_mortality_state`:

```text
on POST /v1/turn:
    let state = read_projection_reality::<PcMortalityState>(pc_id);
    match state.state {
        Alive    => proceed normally,
        Dying    => return TurnEvent { outcome: Rejected { reason: "Bạn đã ngã xuống. Hồi sinh sau ..." } },
        Dead     => return TurnEvent { outcome: Rejected { reason: "Nhân vật này đã chết." } },
        Ghost    => return TurnEvent { outcome: Rejected { reason: "Bạn là bóng ma — chỉ có thể quan sát." } },
    }
```

Adds ~5 ms p99 to every turn submission (1 cache-hit read).

---

## §7 Death modes (V1 closed set)

### 7.1 Permadeath (V1 default)

- PC enters `Dead { mode: Permadeath }` — terminal state
- Player's session for this PC is closed
- UI shows terminal modal: "<PC name> đã hy sinh. Bạn không thể tiếp tục với nhân vật này."
- Player retains LoreWeave account; can create a new PC if reality permits
- PC's grant (in WA_004 Charter sense) is preserved as historical record
- NPCs in the cell may emit reactive Chorus events (per NPC_002) on the death

### 7.2 RespawnAtLocation

- PC enters `Dying { will_respawn_at_fiction_time, spawn_cell }`
- Player's session is paused (read-only; cannot submit turns)
- UI shows: "Bạn đã ngã xuống. Hồi sinh sau {fiction_delay_days} ngày..."
- Background sweeper checks hourly: when current fiction-clock crosses `will_respawn_at_fiction_time`, transitions to `Alive`
- PC re-bound to `spawn_cell` (PL_001 §13 move flow); MemberJoined emitted
- LLM generates wakeup narration (similar to PL_001 §12 sleep wakeup pattern, marked `flavor: true` per EVT-A8)
- Memory retention per `MortalityConfig.RespawnAtLocation.memory_retention` (V1 default `FullMemory`)

### 7.3 Ghost

- PC enters `Ghost` — non-terminal but non-active
- Player's session retains read-only access:
  - Subscribe streams continue
  - Can see scene events
  - Cannot submit turns
- UI shows: "Bạn là một bóng ma. Chỉ có thể quan sát."
- Other actors cannot interact with the ghost in V1 (V2+ may add)
- V2+ exorcism / resurrection quest may transition Ghost → Alive (deferred MOR-D2)

### 7.4 V1 / V2+ split

| Mode | V1 status |
|---|---|
| `Permadeath` | ✓ V1 default |
| `RespawnAtLocation` | ✓ V1 |
| `Ghost` | ✓ V1 (basic — observer only) |
| `Reincarnation { keep_memory: bool }` | V2+ (MOR-D3) |
| `NpcConversion` | V2+ (depends on DL_001 NPC routine + DF1) |

---

## §8 Pattern choices

### 8.1 V1 default = Permadeath

Locked V1: a reality without `MortalityConfig` defaults to Permadeath. Reasons:
- Per PC-B1 locked decision
- Aligns with classic RPG / wuxia narrative stakes (death = real)
- Encourages authors to opt INTO softer modes explicitly via Forge

### 8.2 Death is an EVT-T3 side-effect, NOT a replacement event

The triggering PlayerTurn / NPCTurn commits NORMALLY (with `outcome=Accepted`). Death is a separate EVT-T3 AggregateMutation with `causal_ref` to the triggering event. This:
- Preserves the LLM narration for canon
- Keeps `turn_number` advancing as expected
- Allows multiple deaths in one narrative beat (e.g., LLM narrates "all three guards fell" → 3 separate EVT-T3 mutations causal_ref'ing the same triggering turn)

### 8.3 LLM-narrated death detection is keyword-based V1

Locked V1: detection uses a deterministic keyword dictionary (~50 entries Vietnamese + ~50 English). False-positive risk acceptable because:
- Player can dispute via §9 false-positive correction (admin reverses within 5 minutes)
- Death is a major event — over-detection is preferable to under-detection (false negative = "I died but game says I'm alive")
- V2+ replaces with classifier model (MOR-D6)

### 8.4 Hot-path check is mandatory; cannot be skipped

Every PC turn submission MUST check `pc_mortality_state` before validators. Reasons:
- Prevents Dead/Ghost PCs from submitting turns and bypassing the rejection path
- ~5 ms cost per turn is acceptable
- Lazy-default `Alive` keeps the code simple (no row = Alive)

### 8.5 Per-PC overrides are author-only, V1 trivial

`MortalityConfig.per_pc_overrides` is set by RealityOwner/Co-Author via Forge (using extended EditAction). V1 use case: author declares a "boss NPC" with different death rules, OR a "protagonist PC with plot armor" given Ghost mode while everyone else is Permadeath.

V2+ may add: dynamic per-PC override based on quest state, achievement unlocks, etc.

### 8.6 Ghost is non-terminal but blocks turn submission

Locked V1: Ghost state retains LoreWeave account access but blocks turn submission. The ghost can be observed by NPCs (V2+ memory facet) but cannot directly interact. V1 ghost-PC-relationship is asymmetric: ghost sees living, living doesn't see ghost.

V2+ adds: ghost-NPC interaction (NPC dialog with the ghost, exorcism rituals). MOR-D2 captures.

### 8.7 Respawn memory retention V1 default = FullMemory

Locked V1: RespawnAtLocation default memory = `FullMemory` (PC remembers everything that happened before death). Reasons:
- Simplest implementation (no memory truncation logic)
- Most respawning RPGs retain memory by default
- Authors who want amnesia / fresh-start respawn can configure via Forge (V2+)

V2+: `LastNDays(n)` and `NoMemory` modes (MOR-D7).

### 8.8 No /yield or /die command in V1

V1 doesn't expose a player command for self-induced death. Death must come through narrative or admin path. Reasons:
- Player intent ambiguity (typo / accident / regret)
- Adds attack surface
- Players who want to "exit" can simply abandon the session; their PC remains alive in the world

V2+ may add `/yield` (in combat) or `/end-character` (with confirmation); deferred MOR-D8.

---

## §9 Failure-mode UX

| Failure | When | UX | Recovery |
|---|---|---|---|
| `MortalityHotPathReject` (turn submitted while Dead/Dying/Ghost) | PC's state ≠ Alive | Modal per state: "Nhân vật đã chết." / "Đang hồi sinh, đợi {time} nữa..." / "Bạn là bóng ma, không thể hành động" | Wait for respawn (Dying), or create new PC (Dead — Permadeath) |
| `FalsePositiveDeathDetection` | A6 keyword detector flags death incorrectly (e.g., LLM narrated "PC laughed to death" idiom) | Player can dispute within 5 minutes via "Dispute death" button | If disputed: world-service marks PC as `Alive` again + emits MortalityRevive (audit-log); admin reviews |
| `RespawnLocationDissolved` | spawn_cell channel was dissolved between death and respawn | Sweeper falls back to reality root channel + emits operator-alert | Operator manually relocates PC via S5 admin action |
| `DeathDuringPause` | Reality-wide pause (DP-Ch35) was active when LLM emitted death narration | Death detection still fires (pause doesn't gate detection); but the t2_write to mortality_state respects the pause | Once pause lifts, the death takes effect retroactively |
| `MultipleDeathsOneTurn` | LLM narrates 3 deaths in one beat ("all guards fell") | All 3 mortality_state writes fire (separate EVT-T3 mutations causal_ref'ing same turn) | Each PC handled independently per their `default_death_mode` |
| `AdminKillCapabilityDenied` | Non-admin tries `force-kill` | Toast: "Chỉ admin mới có thể buộc nhân vật chết." | (out of role) |
| `PermadeathInPermadeathReality` (no recovery) | PC dies in Permadeath reality | Terminal modal; player must create new PC | (no recovery) |

### 9.1 False-positive death-detection correction flow

This is the most common UX concern. After death detection:

```text
T0:   A6 detects death keywords in LLM-narrated turn
      world-service writes pc_mortality_state.Dead
      UI shows terminal modal

T0+5s: Modal also shows "Đây là nhầm lẫn? Tranh chấp ngay."

(within 5 minutes)
Player clicks "Dispute death":
    POST /v1/forge/.../mortality/dispute
    body: { pc_id, dispute_reason }
    │
world-service:
    creates pending_dispute T1 row
    notifies admin queue
    UI shows: "Đang chờ admin xem xét. Bạn có thể tiếp tục chơi nếu đã hồi sinh."

(meanwhile: PC remains in Dead state pending review)

Admin reviews narration excerpt:
  IF false-positive confirmed:
    revert mortality_state to last Alive snapshot
    emit MortalityRevive event (audit-log)
    notify player + restore session
  IF death stands:
    notify player; modal shows admin's reasoning
    (no revert; PC remains dead per intended narrative)

V1 dispute window: 5 minutes from death event. After 5 min, dispute is harder
(requires full admin review, not the fast-path).
```

V2+ may add: classifier-based death detection (MOR-D6) reduces false-positive rate enough to remove dispute-flow, OR formalizes dispute as a multi-step quest-recovery flow (MOR-D2).

---

## §10 Cross-service handoff

### 10.1 Death detection flow (LLM-narrated)

```text
PC submits turn → roleplay-service → A5 → A6 sanitize → LLM → A6 output filter
    │
A6 output filter pipeline:
    canon-drift check ✓
    NSFW check ✓
    ★ death-detection sub-validator (THIS FEATURE) ★
        scan narrator_text for death keywords
        if matched + subject identified:
            attach DeathDetection { actor, confidence, excerpt } to the proposal envelope
    │
    ▼
world-service consumer:
    main pipeline: schema → capability → A5 → A6 → Lex → Heresy → A6 filter → canon-drift → causal-ref
    on Accept:
        advance_turn(PlayerTurn { ... })  → channel_event_id = N
    │
    POST-COMMIT (in-process; same handler):
    if DeathDetection attached:
        for each detected actor:
            read MortalityConfig (cached)
            determine effective DeathMode (per-PC override OR default)
            t2_write PcMortalityState transition (Alive → Dying/Dead/Ghost) with causal_ref [N]
            bump forge_roles_version for the PC's user (if Dead/Dying — invalidate session)
            emit advance_turn at reality root with EVT-T3 sub-shape MortalityDeath (for bubble-up)
```

### 10.2 Respawn flow (sweeper)

```text
Sweeper task (every 1 hour wall-clock):
    query PcMortalityState WHERE state=Dying AND will_respawn_at_fiction_time <= current_fiction_clock
    for each:
        t2_write PcMortalityState { Alive }
        dp::move_session_to_channel(ctx, spawn_cell) — if PC has active session bound
        IF PC has no active session: just update state; PC respawns next time user logs in
        emit EVT-T3 MortalityRespawn at reality root
        notify user (V1: in-app banner on next session bind; V2+ push)
```

### 10.3 Admin force-kill flow

```text
Admin op_A → POST /v1/admin/.../mortality/force-kill
    S5 dual-actor: op_B approves
    │
world-service:
    advance_turn at reality root: AdminAction MortalityAdminKill { pc_id, reason }
    proceed as detected death path (POST-COMMIT mortality_state write)
```

---

## §11 Sequence: PC dies via narrative, Permadeath mode

```text
Reality: R-tdd-h-2026-04 (default Permadeath; no per-PC overrides)
PC: Lý Minh, currently Alive, in cell:yen_vu_lau

T0:    Lý Minh submits turn: "/verbatim Tôi rút đao đối đầu với du sĩ"
T0:    LLM narrates: "...lưỡi đao của du sĩ cứa qua cổ Lý Minh, máu phun ra... anh gục xuống, hơi thở dứt..."
T0:    A6 output filter pipeline:
         keyword match: "máu phun" + "hơi thở dứt" + "gục xuống" → 3 matches
         subject identification: "Lý Minh" + the narrator's "anh" pronoun → actor = pc_ly_minh
         DeathDetection { actor: pc_ly_minh, confidence: 0.92, excerpt: "..." }
         attached to LLMProposal envelope
T0:    world-service main pipeline:
         all validators pass → Accepted
         advance_turn(PlayerTurn { ... }) → channel_event_id = 1247
T0+30ms:  POST-COMMIT handler:
            read MortalityConfig: default Permadeath, no override for pc_ly_minh
            determine mode: Permadeath
            t2_write PcMortalityState {
              pc_id: pc_ly_minh,
              state: Dead { mode: Permadeath, died_at_turn: 1247, died_at_cell: yen_vu_lau,
                            death_trigger: NarrativeDeath { triggering_turn_event_id: 1247, confidence: 0.92 } },
              last_transition_at_turn: 1247,
              ...
            }
            advance_turn at reality root: EVT-T3 MortalityDeath { pc_id, mode, ... }
              (this propagates via bubble-up to NPCs in cell — they may react via NPC_002 Chorus on next turn)

T0+50ms:  UI receives via subscribe stream:
            - PlayerTurn rendered (full LLM narration)
            - then EVT-T3 MortalityDeath event
          UI modal: "⚠ Lý Minh đã hy sinh. Thực tại theo chế độ Permadeath — bạn không thể tiếp tục với nhân vật này."
          [Tranh chấp tử vong (5 phút)]  [Tạo nhân vật mới]  [Quay lại trang chính]

(meanwhile, NPC_002 Chorus orchestrator at cell yen_vu_lau picks up trigger 1247:
   priority algorithm runs; Tier-1 candidates = {Lão Ngũ, Tiểu Thúy, du sĩ}
   each may emit a reaction NPCTurn — "Du sĩ wipes blade", "Tiểu Thúy gasps",
   "Lão Ngũ silently observes" — per PL_003 Chorus pattern)

T+5min:  Dispute window closes. PC permanently Dead.
```

---

## §12 Sequence: PC dies and respawns (RespawnAtLocation mode)

```text
Reality: R-fantasy-tutorial
MortalityConfig: default RespawnAtLocation { spawn_cell: town_square, fiction_delay_days: 1, memory_retention: FullMemory }
PC: Hero_Alice, currently Alive in cell:dungeon_boss_room
Current fiction time: 1450-mùa-thu-day10-Tý-sơ

T0: LLM narrates Alice's death in boss fight
    DeathDetection fires
    advance_turn(PlayerTurn { final battle narration }) → event_id = 5601

T0+30ms: POST-COMMIT:
         read MortalityConfig: default RespawnAtLocation
         determine mode: RespawnAtLocation { spawn_cell: town_square, days: 1 }
         compute will_respawn_at = 1450-mùa-thu-day11-Tý-sơ
         t2_write PcMortalityState {
           state: Dying { will_respawn_at_fiction_time, spawn_cell: town_square,
                          died_at_cell: dungeon_boss_room, ... },
           ...
         }
         emit EVT-T3 MortalityDeath at reality root

T0+50ms: UI shows: "⚔ Bạn đã ngã xuống ở phòng boss. Hồi sinh ở quảng trường thành phố sau 1 ngày..."
         Session enters read-only mode; can observe events but cannot submit turns

────── Game world advances; other PCs continue play ──────

(suppose fiction-clock advances 1 day worth via other PCs' turns or scheduled events)

Sweeper at hourly wall-clock cadence:
  query PcMortalityState WHERE state=Dying AND will_respawn_at_fiction_time <= current_fiction
  finds Alice
  t2_write PcMortalityState { state: Alive } (transition Dying→Alive)
  dp::move_session_to_channel(town_square) for Alice's bound session
  emit EVT-T3 MortalityRespawn

Alice's UI: "🌅 Bạn tỉnh dậy ở quảng trường thành phố. Ký ức cuối cùng là cảnh máu và đau ở phòng boss..."
  (LLM-generated wakeup narration, marked flavor=true per EVT-A8)
  Session re-enters write mode; turn submission re-enabled
```

---

## §13 Sequence: false-positive dispute

```text
LLM narrates: "Lý Minh laughed so hard he could die" (idiomatic phrase, NOT actual death)

A6 keyword match: "die" → triggers DeathDetection { confidence: 0.88 } (V1 keyword-based; can't disambiguate idiom)

Death pipeline fires; UI shows terminal modal.

Player immediately clicks "Tranh chấp tử vong (5 phút)":
    POST /v1/forge/.../mortality/dispute
    body: { pc_id: pc_ly_minh, dispute_reason: "It's an idiom — Lý Minh không thực sự chết" }

world-service:
  creates pending_dispute T1 row (5min TTL)
  flag PC's mortality_state.dispute_pending = true
  notify admin queue
  UI: "Đang chờ admin xem xét... Bạn có thể tiếp tục chơi nếu admin xác nhận hồi sinh."

Admin reviews narrator excerpt within 5 min:
  Reads "laughed so hard he could die" → idiom, not real death
  Approves dispute:
    t2_write PcMortalityState { state: Alive } (revert)
    emit MortalityRevive event
    notify player

UI: "✓ Admin đã xác nhận đây là cách nói bóng. Lý Minh vẫn còn sống."
    Session re-enters normal write mode.

Audit log: dispute resolved, MortalityRevive committed, admin reviewer recorded.
```

---

## §14 Open questions deferred

| ID | Question | Defer to |
|---|---|---|
| MOR-D1 | HP / stats system — combat damage as DeathTrigger | PCS_001 (PC stats) + future combat feature |
| MOR-D2 | Resurrection / exorcism quests for Ghost mode | V2+ — depends on quest engine |
| MOR-D3 | Reincarnation mode (PC respawns as different character) | V2+ |
| MOR-D4 | NpcConversion mode (PC body becomes an NPC) | V2+ — depends on DL_001 NPC routines + DF1 |
| MOR-D5 | Mass-death cascade on WorldStability Catastrophic / Shattered | V2+ — extends WA_002 Heresy |
| MOR-D6 | Replace keyword-match death detection with classifier model | V2+ — needs LLM infrastructure for cheap classifier calls |
| MOR-D7 | RespawnAtLocation memory retention modes (LastNDays, NoMemory) | V2+ |
| MOR-D8 | Player-initiated death commands (/yield, /end-character) | V2+ — needs careful UX to prevent accidental loss |
| MOR-D9 | Multi-language death keyword dictionary (Chinese for wuxia, beyond Vi+En) | V2+ ops; expand `i18n_death_keywords` resource |
| MOR-D10 | Per-fiction-time-window respawn caps (N respawns per fiction-week) | V2+ |
| MOR-D11 | Death triggering NPC opinion shifts (PC who killed many NPCs gets reputation) | V2+ — extends NPC_001 NpcOpinion |
| MOR-D12 | Ghost-NPC interaction (V2+ exorcism, dialogue, etc.) | V2+ — extends NPC_002 Chorus |

---

## §15 Cross-references

- [WA_001 Lex](WA_001_lex.md) — Mortality is a separate validator slot; Lex catches forbidden-ability use that would have killed the PC, before Mortality
- [WA_002 Heresy](WA_002_heresy.md) — V2+ Mass-death cascade on Catastrophic / Shattered (MOR-D5)
- [WA_003 Forge](WA_003_forge.md) — author edits MortalityConfig via existing EditAction patterns; new sub-shape EditMortalityConfig added to the closed set
- [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) — turn submission hot-path (§6.3 Mortality check); §13 move_session_to_channel pattern reused for respawn
- [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) — rejection copy table format
- [NPC_001 Cast](../05_npc_systems/NPC_001_cast.md) — `actor_binding` updated on respawn
- [NPC_002 Chorus](../05_npc_systems/NPC_002_chorus.md) — NPCs may react to death via Chorus (Tier-1 priority — directly addressed by death event)
- [05_llm_safety/](../../05_llm_safety/) — A6 output filter (PL-20) where death-detection sub-validator lives
- [07_event_model/03_event_taxonomy.md](../../07_event_model/03_event_taxonomy.md) — EVT-T3 AggregateMutation (death events); EVT-T8 AdminAction (admin force-kill)
- [decisions/locked_decisions.md](../../decisions/locked_decisions.md) — PC-A3, PC-B1, PC-E3 (this feature implements the runtime enforcement)
- [decisions/deferred_DF01_DF15.md](../../decisions/deferred_DF01_DF15.md) — DF4 World Rules umbrella

---

## §16 Implementation readiness checklist

- [x] **§2** Domain concepts (DeathMode, MortalityConfig, MortalityState, DeathTrigger, DeathTriggerDetector, RespawnTrigger)
- [x] **§2.5** EVT-T* mapping (death = EVT-T3 side-effect on triggering EVT-T1/T2; admin kill = EVT-T8 + EVT-T3)
- [x] **§3** Aggregate inventory (2 new: `mortality_config`, `pc_mortality_state`)
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** Death-trigger detection (V1 keyword-match in A6 output filter; admin force-kill path; hot-path mortality check on turn submission)
- [x] **§7** V1 closed-set DeathMode (Permadeath default + RespawnAtLocation + Ghost)
- [x] **§8** Pattern choices (V1 default Permadeath, death = side-effect not replacement, keyword detection V1, hot-path mandatory, no /yield V1)
- [x] **§9** Failure-mode UX (7 cases) + §9.1 dispute flow for false-positive correction
- [x] **§10** Cross-service handoff (detection / respawn sweeper / admin force-kill)
- [x] **§11** Sequence: Permadeath via narrative
- [x] **§12** Sequence: Respawn cycle
- [x] **§13** Sequence: false-positive dispute
- [x] **§14** Deferrals (MOR-D1..D12)

**Deferred:** acceptance criteria (intentionally not in V1 of this doc).

**Resolves:** PC-B1 (PC death behavior) ✓, partial PC-E3 (paradox / death extreme case) ✓.

**Status:** DRAFT 2026-04-25.

**Drift watchpoint:** §6.1 keyword-based detection has known false-positive risk (idioms, hyperbole); §9.1 dispute flow mitigates but doesn't eliminate. V2+ classifier replacement (MOR-D6) is the proper fix.

**Next** (when this doc locks): A6 output filter adds death-detection sub-validator; world-service implements mortality state machine + respawn sweeper + admin force-kill handler; Forge UI exposes MortalityConfig editor (extends WA_003 EditAction set); admin console exposes dispute review queue. Vertical-slice target: SPIKE_01 reality booted with Permadeath default; Lý Minh's hypothetical death scenario reproduces deterministically.
