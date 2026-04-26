# WA_006 — Mortality (Per-Reality Death Mode Config)

> **🪶 THIN-REWRITE NOTICE (2026-04-25 closure pass):** This file was thin-rewritten from 730 lines → ~280 lines as part of the WA folder closure pass. The original draft over-extended into territories owned by other features:
>
> - `pc_mortality_state` aggregate (per-PC state) → **PCS_001** (when designed)
> - LLM death-detection sub-validator (A6 keyword match) → **05_llm_safety**
> - Hot-path mortality check on every turn submission → **PL_001 / PL_002**
> - Respawn sweeper task + sweeper-driven Dying→Alive transitions + move_session_to_channel → **PL_001 / PCS_001**
> - False-positive dispute flow (admin review queue) → **05_llm_safety** + admin-tooling
>
> Those mechanics are NOT redesigned here. WA_006 now owns ONLY the per-reality config layer (which death mode applies in this reality + per-PC overrides). Cross-references in §14 point at where mechanics live.
>
> Original draft history: see commit `8aed4fa` (initial 730-line draft) + commit `de9cf1a` (over-extension marker added) + this thin-rewrite commit. Stable ID `WA_006` retained per foundation I15 — "WA_006 Mortality" still refers to this feature, just shrunk to its legitimate scope.
>
> ---
>
> **Conversational name:** "Mortality" (MOR). Per-reality declaration of what death MODE applies — `Permadeath` (V1 default), `RespawnAtLocation`, `Ghost` — plus per-PC overrides. The DATA + AUTHOR-FACING CONFIG only; the runtime mechanics (state machine, detection, hot-path check, respawn flow) live in PCS_001 / 05_llm_safety / PL_001/002 when those features land.
>
> **Category:** WA — World Authoring
> **Status:** **CANDIDATE-LOCK 2026-04-25** (thin-rewrite + §12 acceptance criteria added closure pass). LOCK granted after the 6 §12 acceptance scenarios have passing integration tests. **2026-04-26 RES_001 downstream Phase 2 update:** §6.5 added — MortalityCauseKind catalog with `Starvation` (RES_001 HungerTick magnitude≥7), `KilledBy` (RES_001 vital_pool Hp=0), `AdminKill` (existing); enum implementation deferred to PCS_001 first design pass.
> **Catalog refs:** **DF4 World Rules** (sub-feature: PC death mode config). Resolves [PC-B1](../../decisions/locked_decisions.md) (PC death behavior config layer only) — the runtime enforcement of death is PCS_001 territory.
> **Builds on:** [WA_003 Forge](WA_003_forge.md) (author UI for editing MortalityConfig — extends Forge's EditAction set), [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §16 RealityManifest (Mortality extends manifest with `mortality_config` field per `_boundaries/02_extension_contracts.md` §2)
> **Mechanics handed off to:**
> - [PCS_001](../06_pc_systems/) — per-PC mortality state aggregate, respawn lifecycle (when PCS_001 ships)
> - [05_llm_safety/](../../05_llm_safety/) — A6 death-detection sub-validator, false-positive dispute flow
> - [PL_001 / PL_002](../04_play_loop/) — hot-path mortality check on turn submission, move_session_to_channel for respawn

---

## §1 User story (config layer only)

**Author Tâm-Anh creates reality `R-tdd-h-2026-04` with default Permadeath:**

She doesn't declare a `mortality_config` in the RealityManifest → reality defaults to `Permadeath` per V1 + locked PC-B1.

**Author Hoài-Linh creates reality `R-fantasy-tutorial` with respawn:**

She wants forgiving deaths for new players. Via Forge (WA_003) → "Mortality config" tab:

```
default_death_mode: RespawnAtLocation {
  spawn_cell: "town_square",
  fiction_delay_days: 1,
  memory_retention: FullMemory,
}
```

Saved → MortalityConfig committed via Forge's EditAction; invalidation broadcast propagates ≤100ms; downstream PCS_001 / PL_001 mechanics consume the new config on next death event.

**Author Tâm-Anh later adds plot armor for protagonist PC:**

Reality stays default Permadeath but author wants `pc_protagonist` to be Ghost-mode instead of Permadeath. Via Forge → "Per-PC overrides" sub-tab → adds `MortalityOverride { pc_id: pc_protagonist, mode: Ghost }`.

**This feature design specifies:** the `mortality_config` aggregate shape, the closed-set DeathMode enum, the V1 default (Permadeath), per-PC overrides via Forge, and the contract that downstream features consume this config when they implement death mechanics. WA_006 does NOT design death detection, state machine, or respawn flow — those are external owners' territory per the thin-rewrite notice.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **DeathMode** | Closed enum: `Permadeath \| RespawnAtLocation { spawn_cell, fiction_delay_days, memory_retention } \| Ghost` | V1: 3 modes. V2+: Reincarnation, NpcConversion deferred. |
| **MortalityConfig** | Per-reality singleton aggregate; declares default DeathMode + per-PC overrides | Default = `Permadeath` if no config row exists (per PC-B1 lock). |
| **MortalityOverride** | Per-(reality, pc_id) override; takes precedence over reality default | Useful for plot-armored protagonists, boss NPCs, etc. |
| **MemoryRetention** | Closed enum: `FullMemory \| LastNDays(u32) \| NoMemory` | V1 default = FullMemory; LastNDays + NoMemory deferred to V2+ (MOR-D7). |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11)

WA_006 emits no runtime events. Config edits emit:

| WA_006 path | EVT-T* | Producer | Notes |
|---|---|---|---|
| Author edits MortalityConfig via Forge | **EVT-T8** AdminAction (sub-shape `ForgeEdit { action: EditMortalityConfig \| AddMortalityOverride \| RemoveMortalityOverride, ... }`) | Forge / world-service | Extends WA_003 Forge's EditAction enum. |
| RealityManifest seed (bootstrap) | (no event — embedded in PL_001 §16 bootstrap chain) | knowledge-service ingestion → world-service | Extends PL_001 RealityManifest per `_boundaries/02_extension_contracts.md` §2. |

Runtime events (death triggers, mortality state transitions, respawns) are emitted by PCS_001 / 05_llm_safety / PL when those features ship. Not WA_006.

---

## §3 Aggregate inventory

**One** aggregate. The thin scope.

### 3.1 `mortality_config`

```rust
#[derive(Aggregate)]
#[dp(type_name = "mortality_config", tier = "T2", scope = "reality")]
pub struct MortalityConfig {
    pub reality_id: RealityId,                       // (also from key — singleton per reality)
    pub default_death_mode: DeathMode,
    pub per_pc_overrides: Vec<MortalityOverride>,    // empty Vec by default
    pub schema_version: u32,
}

pub enum DeathMode {
    Permadeath,                                       // V1 default for any new reality
    RespawnAtLocation {
        spawn_cell: ChannelId,                        // existing cell channel
        fiction_delay_days: u32,                      // 0..=30 V1
        memory_retention: MemoryRetention,
    },
    Ghost,                                            // observer-only; no turn submissions
}

pub enum MemoryRetention {
    FullMemory,                                       // V1 default for RespawnAtLocation
    LastNDays(u32),                                   // V2+ (MOR-D7)
    NoMemory,                                         // V2+
}

pub struct MortalityOverride {
    pub pc_id: PcId,                                  // referenced abstractly; PcId type owned by PCS_001
    pub mode: DeathMode,                              // overrides the reality default for this PC
    pub note: Option<String>,                         // ≤500 chars; author rationale
}
```

- T2 + RealityScoped: per-reality singleton; small (~5 KB typical even with 100 overrides).
- Created at reality bootstrap from RealityManifest (per PL_001 §16) OR lazy-default via Forge's first edit.
- Read by downstream features (PCS_001 / 05_llm_safety / PL) when they need to apply the death mode at runtime.
- One row per reality; identified by `reality_id` (singleton like `fiction_clock` and `lex_config`).

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `mortality_config` | T2 | T2 | Reality | ~1 per death event in downstream features (cached) | rare (author edits via Forge) | Per-reality singleton; durable; eventual-consistency on author edit OK. |

No T0/T1/T3. Author edits don't need atomicity with other writes.

---

## §5 DP primitives this feature calls

### 5.1 Reads

```rust
// Downstream features (PCS_001 / 05_llm_safety / PL) read this at death time.
// WA_006 itself doesn't read at hot-path — it's the config DATA.
let config = dp::read_projection_reality::<MortalityConfig>(
    ctx,
    MortalityConfigId::singleton(reality_id),
    wait_for=None, ...
).await?.unwrap_or_default();  // unwrap_or_default = Permadeath fallback
```

### 5.2 Writes (only via Forge EditAction)

```rust
// At RealityManifest bootstrap (PL_001 §16.2 t3_write_multi extension)
dp::t2_write::<MortalityConfig>(ctx, MortalityConfigId::singleton(reality_id),
    MortalityDelta::Initialize { default_mode, ... }).await?;

// Author edits via Forge (WA_003 EditAction extension)
dp::t2_write::<MortalityConfig>(ctx, ..., MortalityDelta::EditDefaultMode { ... }).await?;
dp::t2_write::<MortalityConfig>(ctx, ..., MortalityDelta::AddOverride { pc_id, mode, note }).await?;
dp::t2_write::<MortalityConfig>(ctx, ..., MortalityDelta::RemoveOverride { pc_id }).await?;
```

Author edits emit invalidation broadcast (DP-X*) so all consuming services pick up new config within ≤100 ms.

---

## §6 Closed-set DeathMode (V1)

V1 ships 3 modes. Adding a 4th requires a superseding decision in [`../../decisions/locked_decisions.md`](../../decisions/locked_decisions.md).

| Mode | V1 status | Used when |
|---|---|---|
| `Permadeath` | ✅ V1 default (per PC-B1 lock) | Wuxia, classic RPG, narrative-stakes-matter realities |
| `RespawnAtLocation { spawn_cell, fiction_delay_days, memory_retention }` | ✅ V1 | Forgiving fantasy, tutorials, casual realities |
| `Ghost` | ✅ V1 (basic — observer only) | Narrative-driven mysteries, post-mortem participation |
| `Reincarnation { keep_memory }` | V2+ deferred (MOR-D3) | RPG with reincarnation cycles |
| `NpcConversion` | V2+ deferred (MOR-D4) | Depends on DL_001 NPC routine + DF1 |

Per-PC overrides can use any V1 mode independently of the reality default. E.g., reality default `Permadeath` + protagonist PC override `Ghost` is valid and useful.

### §6.5 MortalityCauseKind catalog (downstream coordination — 2026-04-26 RES_001 DRAFT)

WA_006 is config-only (per thin-rewrite); the state machine + actual `cause_kind` enum implementation lives in **PCS_001** (deferred). However, WA_006 SHOULD catalog the V1 cause kinds that downstream features will emit, so PCS_001 (when designed) implements a complete enum without missing variants.

V1 cause kinds (RESERVED — to be implemented by PCS_001 when it ships):

| `cause_kind` variant | Emitter feature | Trigger | Notes |
|---|---|---|---|
| `KilledBy { attacker_ref: ActorRef }` | RES_001 (vital_pool Hp=0 from PL_005 Strike kind) | Hp depleted to 0 via combat damage | Standard combat death. Attacker recorded for legal/social fallout (V1+). |
| `Starvation` | **RES_001 (HungerTick Generator magnitude≥7)** | Actor not eating for ~7+ fiction-days; Hungry status magnitude 7 threshold | **NEW 2026-04-26 RES_001 DRAFT downstream — added to WA_006 catalog.** Triggered by `Scheduled:HungerTick` (RES_001 §7.2). |
| `AdminKill { admin_ref }` | WA_006 (`MortalityAdminKill` AdminAction sub-shape) | Admin force-kills via Forge | Already V1 per WA_006 thin-rewrite. |
| `Suicide { method }` | (V1+ deferred — reserved) | PC-initiated death | V1+30d feature. |
| `EnvironmentalHazard { hazard_kind }` | (V1+ deferred — reserved) | Falling, drowning, fire, etc. | V1+30d feature; depends on environmental hazard system. |

**Implication:** RES_001 emits `MortalityTransitionTrigger { actor: ActorRef, cause_kind: MortalityCauseKind }` events. The `MortalityCauseKind` enum is currently UNDEFINED (PCS_001 will own it). For V1 scaffolding, downstream consumers can stub-handle the event by inspecting `cause_kind` discriminator. Full state machine integration locks at PCS_001 first design pass.

**Boundary:** WA_006 reserves the cause kind catalog (config-adjacent — authors may want to know which death sources can fire); PCS_001 owns the actual enum + state machine consumption. Pattern matches "WA_006 owns DeathMode catalog; PCS_001 owns state machine application" already established in thin-rewrite.

---

## §7 Pattern choices

### 7.1 V1 default = Permadeath

Per PC-B1 locked decision: a reality without `MortalityConfig` defaults to Permadeath. Authors opt INTO softer modes via Forge.

### 7.2 Per-PC overrides additive only

Per-PC overrides DO NOT modify the reality default; they SUPPLEMENT it. `MortalityConfig.per_pc_overrides: Vec<MortalityOverride>` is queried by `pc_id`; if no match, reality default applies.

### 7.3 Author UI is Forge (WA_003)

WA_006 does not design its own UI. Forge's EditAction enum extends with:
- `EditMortalityConfig { default_mode }`
- `AddMortalityOverride { pc_id, mode, note }`
- `RemoveMortalityOverride { pc_id }`

Forge's RBAC matrix governs who can edit (RealityOwner / Co-Author per ImpactClass — Major for default mode change; Minor for adding overrides).

### 7.4 Mechanics not designed here

The runtime DeathTrigger detection, MortalityState aggregate, hot-path turn check, respawn sweeper, dispute flow, and NPC death-reaction integration ALL live in their respective feature owners' design docs (PCS_001 / 05_llm_safety / PL_001/002 / NPC_002). WA_006 only provides the CONFIG that those features consume.

---

## §8 Failure-mode UX

| Failure | When | UX | Recovery |
|---|---|---|---|
| Author tries to set `RespawnAtLocation { spawn_cell }` to a non-existent cell | Validation at Forge EditAction time | Toast: "Spawn cell không tồn tại. Hãy chọn cell hợp lệ." | Author picks valid cell |
| `fiction_delay_days` out of range (V1 0..=30) | Validation | Toast: "Số ngày phải trong khoảng 0..30." | Author corrects |
| Per-PC override added for non-existent PC | Validation | Toast: "PC không tồn tại trong reality này." | Author selects from autocomplete |
| Concurrent author edits | Last-write-wins (per Forge §9) | Standard Forge concurrent-edit handling | Auto-reload |
| Removing all overrides while a Ghost-PC is still "Ghost" mid-life | Deletion is allowed — runtime mechanics handle the implication when next death event fires (uses new default) | (no UX issue here; runtime concern) | n/a |

---

## §9 Cross-service handoff

```text
Author in Forge → POST /v1/forge/realities/{R}/edits
    body: { action: EditMortalityConfig { default_mode: ... }, reason: "..." }
    │
gateway-bff → world-service:
    Forge RBAC check (Major / Minor / Tier1 per Forge §6)
    t2_write MortalityConfig
    advance_turn at reality root with EVT-T8 AdminAction ForgeEdit
    t2_write ForgeAuditEntry
    │
    ▼
DP cache invalidation broadcast (~100ms propagation)
    │
    ▼
Downstream consumers (PCS_001 / 05_llm_safety / PL_001/002) refresh their cache
on next death event for this reality
```

Wall-clock: edit propagation ≤100ms via DP cache invalidation; downstream reads see new config on subsequent death events.

---

## §10 Sequence: author creates RespawnAtLocation reality

```text
T0: Hoài-Linh creates reality `R-fantasy-tutorial`
    RealityManifest carries (knowledge-service ingestion):
      mortality_config: {
        default_death_mode: RespawnAtLocation {
          spawn_cell: "town_square",
          fiction_delay_days: 1,
          memory_retention: FullMemory,
        },
        per_pc_overrides: [],
      }

T0+50ms: world-service bootstraps (PL_001 §16):
    t3_write_multi atomic [
      RealityRegistry::Create,
      ChannelTree::Create (per PL_001),
      MortalityConfig::Initialize { default_death_mode, per_pc_overrides: [] },
      LexConfig::Initialize (if any),
      ...
    ]

T0+200ms: Reality activated; PCs may bind sessions.

────── later, first PC death occurs ──────

T+30d: PC `Hero_Alice` dies in dungeon (LLM narrates death)
    → PCS_001 / 05_llm_safety / PL detection mechanics fire
    → mechanics read MortalityConfig(R-fantasy-tutorial)
    → decode: default_death_mode = RespawnAtLocation { spawn_cell: town_square,
              fiction_delay_days: 1, memory_retention: FullMemory }
    → mechanics apply: Alice → Dying state with respawn at town_square in 1 fiction-day
    (mechanics are NOT WA_006 territory; this is just where the config gets consumed)
```

---

## §11 Sequence: per-PC override added

```text
T+60d: Tâm-Anh decides protagonist `pc_yangguo` should have plot armor (Ghost mode
       instead of reality default Permadeath).

Forge UI → "Mortality config" → "Per-PC overrides" → "+ Add override"
    pick PC: pc_yangguo
    pick mode: Ghost
    note: "Protagonist; plot armor through arc 3"

POST /v1/forge/.../edits
    body: { action: AddMortalityOverride { pc_id: pc_yangguo, mode: Ghost,
                                            note: "..." } }

world-service:
    Forge RBAC: RealityOwner + Minor (adding override is Minor) = Ok solo
    t2_write MortalityConfig (delta: AddOverride)
    advance_turn EVT-T8 AdminAction ForgeEdit
    t2_write ForgeAuditEntry

UI: "✓ Saved. pc_yangguo will now go to Ghost mode on death (overriding reality default Permadeath)."

────── later, pc_yangguo dies ──────

PCS_001 / 05_llm_safety / PL mechanics fire:
    read MortalityConfig
    look up overrides: pc_yangguo → mode = Ghost
    apply Ghost state to pc_yangguo (instead of reality default Permadeath)
```

---

## §12 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service + Forge can pass these scenarios. Each is one row in the integration test suite. LOCK granted after all 6 pass.

### 12.1 Config-layer scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-MOR-1 BOOTSTRAP DEFAULT PERMADEATH** | Reality created via RealityManifest WITHOUT `mortality_config` field. | `read_projection_reality::<MortalityConfig>` returns None (or DefaultRow); `unwrap_or_default()` → `Permadeath`. PC-B1 default honored. |
| **AC-MOR-2 BOOTSTRAP WITH RESPAWN** | RealityManifest carries `mortality_config: { default_death_mode: RespawnAtLocation { spawn_cell, fiction_delay_days: 1, memory_retention: FullMemory } }`. | `MortalityConfig` row created at bootstrap; subsequent reads return the configured RespawnAtLocation; downstream consumers can decode all three RespawnAtLocation fields. |
| **AC-MOR-3 PER-PC OVERRIDE ADDED** | RealityOwner via Forge adds `MortalityOverride { pc_id: pc_protagonist, mode: Ghost, note: "plot armor" }`. | Forge RBAC accepts Minor solo; `t2_write MortalityConfig` commits with override appended; ForgeAuditEntry logged; subsequent override-lookup for `pc_protagonist` returns `Ghost`. |
| **AC-MOR-4 INVALIDATION BROADCAST** | Author flips reality `default_death_mode` from `Permadeath` to `RespawnAtLocation` via Forge; downstream consumer reads on different node within 100ms. | DP cache invalidation broadcast propagates; second-node read returns new config; no stale-cache mismatch. |
| **AC-MOR-5 RBAC ENFORCED** | ReadOnly user attempts `EditMortalityConfig` POST. | Forge rejects with `CapabilityDenied`; UI toast surfaces; no write committed. |
| **AC-MOR-6 OVERRIDE REMOVAL** | Author calls `RemoveMortalityOverride { pc_id: pc_protagonist }`. | Override entry removed from `MortalityConfig.per_pc_overrides`; ForgeAuditEntry logs removal; subsequent override-lookup for `pc_protagonist` returns None → reality default applies. |

**Lock criterion:** all 6 scenarios have a corresponding integration test that passes. Until then, status is `CANDIDATE-LOCK` (post-thin-rewrite + acceptance criteria) → `LOCKED` (after tests).

---

## §13 Open questions deferred (post thin-rewrite)

All previous MOR-D1..D12 deferrals are PRESERVED but most are now explicitly **NOT WA_006 territory** — they belong to the mechanics owners.

| ID | Question | Owner |
|---|---|---|
| MOR-D1 | HP / stats system → combat damage as DeathTrigger | **PCS_001** when designed |
| MOR-D2 | Resurrection / exorcism quests for Ghost mode | V2+ — depends on quest engine |
| MOR-D3 | Reincarnation mode | V2+ WA_006 schema bump (closed-set extension) |
| MOR-D4 | NpcConversion mode | V2+ — depends on DL_001 / DF1 |
| MOR-D5 | Mass-death cascade on WorldStability Catastrophic / Shattered | V2+ — extends WA_002 Heresy |
| MOR-D6 | Replace keyword-match death detection with classifier model | **05_llm_safety** when V2+ |
| MOR-D7 | RespawnAtLocation memory retention modes (LastNDays, NoMemory) | V2+ WA_006 schema bump |
| MOR-D8 | Player-initiated death commands (/yield, /end-character) | **PL_002 Grammar** future |
| MOR-D9 | Multi-language death keyword dictionary | **05_llm_safety** ops |
| MOR-D10 | Per-fiction-time-window respawn caps | V2+ WA_006 + **PCS_001** |
| MOR-D11 | Death triggering NPC opinion shifts | **NPC_001 Cast** (NpcOpinion extension) |
| MOR-D12 | Ghost-NPC interaction | **NPC_002 Chorus** future |

---

## §14 Cross-references

**Mechanics owners (V1):**
- [PCS_001](../06_pc_systems/) — owns `pc_mortality_state` aggregate, respawn lifecycle, hot-path turn check (when designed)
- [05_llm_safety/](../../05_llm_safety/) — owns A6 death-detection sub-validator + false-positive dispute flow
- [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) — owns turn submission flow + move_session_to_channel for respawn
- [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) — owns hot-path mortality check + (future MOR-D8) death-related commands

**Companion / consumer:**
- [WA_001 Lex](WA_001_lex.md) — sibling per-reality config feature
- [WA_002 Heresy](WA_002_heresy.md) — sibling; V2+ MOR-D5 connects to Catastrophic/Shattered cascade
- [WA_003 Forge](WA_003_forge.md) — author UI; extends EditAction with MortalityConfig operations
- [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §16 — RealityManifest extension point per `_boundaries/02_extension_contracts.md` §2
- [NPC_002 Chorus](../05_npc_systems/NPC_002_chorus.md) — V2+: NPCs may react to PC deaths (MOR-D11/D12)

**Reference:**
- [decisions/locked_decisions.md](../../decisions/locked_decisions.md) — PC-A3, PC-B1, PC-E3 (config layer locked here; runtime in mechanics owners)
- [decisions/deferred_DF01_DF15.md](../../decisions/deferred_DF01_DF15.md) — DF4 World Rules umbrella
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — `mortality_config` ownership = WA_006; `pc_mortality_state` ownership = PCS_001 (when designed)

---

## §15 Implementation readiness checklist

- [x] **§2** Domain concepts (DeathMode, MortalityConfig, MortalityOverride, MemoryRetention)
- [x] **§2.5** EVT-T* mapping (config edits via Forge → EVT-T8 ForgeEdit; runtime events owned by other features)
- [x] **§3** Aggregate inventory — 1 aggregate (`mortality_config`)
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives by name (config reads + Forge-routed writes)
- [x] **§6** Closed-set DeathMode V1 (Permadeath default + RespawnAtLocation + Ghost; Reincarnation/NpcConversion V2+ deferred)
- [x] **§7** Pattern choices (V1 default Permadeath; per-PC overrides additive; UI via Forge; mechanics elsewhere)
- [x] **§8** Failure UX (config edit validation only)
- [x] **§9** Cross-service handoff (Forge-routed config edits)
- [x] **§10/§11** Sequences (bootstrap with RespawnAtLocation; per-PC override added)
- [x] **§12** Acceptance criteria (6 scenarios for the config layer)
- [x] **§13** Deferrals — most explicitly handed off to mechanics owners
- [x] **§14** Cross-references with explicit mechanics ownership map

**Status transition:** DRAFT (`8aed4fa`) → PROVISIONAL (`de9cf1a` over-extension marker) → **CANDIDATE-LOCK** (this thin-rewrite, ~280 lines from original 730).

LOCK granted after all 6 §12 acceptance scenarios have passing integration tests.

**Resolves:** PC-B1 config-layer ✓ (runtime enforcement is PCS_001's territory).

**Deferred to mechanics owners:** MOR-D1, D6, D8, D9, D10, D11, D12 each explicitly point at the right feature when it lands.

**Next** (when this doc locks): downstream features (PCS_001 / 05_llm_safety / PL_001/002 / NPC_001/002) implement the mechanics that consume this config; book-ingestion pipeline (knowledge-service) extends RealityManifest with `mortality_config` field per `_boundaries/02_extension_contracts.md` §2; admin-cli Forge UI exposes the EditMortalityConfig actions. Vertical-slice target: hypothetical reality boots with RespawnAtLocation + 1 per-PC Ghost override; 6 §12 acceptance scenarios reproduce deterministically.
