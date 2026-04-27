# DF04 World Rules — Concept Notes

> **Status:** CONCEPT 2026-04-27 — captures user decision Option 3 (hybrid: navigation + aggregate sketch) + Option (ii) un-designed sub-features get separate WA_007/008/009 docs when needed. NOT a design doc; the seed material for the eventual `DF04_001_world_rules_overrides.md` design.
>
> **Promotion gate (to DRAFT):** When (a) Q1-Q9 LOCKED via deep-dive (mirror PROG/AIT/TDIL/DF5 pattern), (b) `_boundaries/_LOCK.md` is free, (c) at least 1 un-designed sub-feature surfaces concrete need (V1+30d for first override; V2 for first new sub-feature) → main session drafts `DF04_001_world_rules_overrides.md` in single combined boundary commit.
>
> **Origin:** Original DF04 placeholder marked V1-blocking 2026-04-25. After WA_001/002/006 + DF5 + TDIL closures, scope **substantially hollowed out**. User direction 2026-04-27 chose Option 3 (hybrid concept-notes + aggregate sketch) + Option (ii) (separate WA_* docs for un-designed sub-features).

---

## §1 — Architectural finding: DF04 is UMBRELLA, not atomic feature

WA_001 Lex header explicitly states (commit `a1ce3c8a` zone):

> "**Catalog refs: DF4 World Rules** (sub-feature: physics/ability/energy axioms only). **Sibling DF4 sub-features** (death model PC-B1, PvP consent PC-D2, voice mode lock C1-D3, session caps H3-NEW-D1, queue policy S7-D6, disconnect policy SR11-D4, turn fairness SR11-D7, time model MV12-D6) live in separate WA_* docs to be designed later."

WA_002 Heresy + WA_006 Mortality follow same pattern. **DF04 = the umbrella that organizes all rule sub-features**, not a competing feature.

```
DF4 — World Rules (UMBRELLA)
├── ✅ WA_001 Lex                        — physics/ability/energy axioms          [CANDIDATE-LOCK 2026-04-25]
├── ✅ WA_002 Heresy                      — forbidden-knowledge contamination       [CANDIDATE-LOCK 2026-04-25]
├── ✅ WA_002b Heresy lifecycle           — sequences + AC                          [CANDIDATE-LOCK 2026-04-25]
├── ✅ WA_006 Mortality                   — death mode config                       [CANDIDATE-LOCK 2026-04-25]
├── ✅ TDIL_001                           — time model (MV12-D6 superseded)         [DRAFT 2026-04-27]
├── 🟡 DF04_001 (this concept)            — runtime override aggregate              [CONCEPT 2026-04-27]
├── 📦 WA_007 (when needed)               — PvP consent (PC-D2) V2
├── 📦 WA_008 (when needed)               — Queue policy (S7-D6) V1+30d
├── 📦 WA_009 (when needed)               — Turn fairness (SR11-D7) V2
└── ✅ WA_003 Forge                       — author console (cross-cutting; NOT rule sub-feature)
```

**Boundary discipline:** WA_001/002/006 + TDIL each own their primary aggregate + RealityManifest extension + validator slot. DF04_001 owns ONLY runtime override aggregate for engine-defaulted concerns that DON'T have their own dedicated WA_* doc (yet).

---

## §2 — Hollowing-out check: V1-blocking status DOWNGRADED

Original DF04 V1-blocking concerns have all been resolved:

| Original DF04 concern | Resolved by | Status |
|---|---|---|
| Death behavior (PC-B1) | WA_006 Mortality | ✅ LOCKED |
| Paradox tolerance (PC-E3) | WA_002 Heresy | ✅ LOCKED |
| Time model (MV12-D6) | TDIL_001 | ✅ DRAFT (closure pending) |
| Canon strictness (F1) | WA_001 Lex + 05_llm_safety A6 | ✅ LOCKED |
| Disconnect policy V1 default | DF5 §10 Q10 LOCKED 30s wall-clock grace | ✅ engine default V1; per-reality override = DF4 V1+30d |
| Session caps V1 default | DF5 §10 Q3 LOCKED 8-cap | ✅ engine default V1; per-reality override = DF4 V1+30d |
| Voice mode V1 default | PL-22/23/24 LOCKED mixed default | ✅ engine default V1; per-reality lock C1-D3 = DF4 V2 |
| Quest-eligibility (M3-D3) | NAR-5 designed | 🟡 V3 quest territory; DF4 override scope V3 |

**Conclusion:** DF04 **NOT V1-blocking anymore** after upstream features locked. Demoted to V1+30d primary scope (override aggregate); V2 for un-designed sub-features.

---

## §3 — DF04 V1+30d scope: `reality_rule_overrides` aggregate

### §3.1 What DF04 owns exclusively

DF04 owns the runtime override aggregate for engine-defaulted concerns that:
1. Have engine defaults LOCKED in upstream features (DF5 / PL / TDIL)
2. Need per-reality customization without dedicated WA_* doc
3. Do NOT redefine — just allow override

```rust
#[derive(Aggregate)]
#[dp(type_name = "reality_rule_overrides", tier = "T2", scope = "reality")]
pub struct RealityRuleOverrides {
    pub reality_id: RealityId,                          // primary key (1:1 with reality)
    pub schema_version: u8,                             // = 1 V1+30d; bumped for V2+ migration
    pub last_updated_fiction_time: FictionTime,

    // ─── DF5 Session engine defaults — per-reality override (V1+30d) ──
    pub session_caps_override: Option<SessionCapsOverride>,
    pub disconnect_grace_override: Option<DisconnectGraceOverride>,

    // ─── PL voice mode lock (V2 — C1-D3) ──────────────────────────────
    pub voice_mode_lock: Option<VoiceModeLock>,

    // ─── V2+ un-designed sub-features (placeholder; will move to WA_007/008/009 own aggregate) ──
    // PvP consent (WA_007 V2): pub pvp_consent_policy: Option<...>
    // Queue policy (WA_008 V1+30d): pub queue_policy: Option<...>
    // Turn fairness (WA_009 V2): pub turn_fairness_policy: Option<...>
    // ↑ these MIGRATE OUT of this aggregate when their own WA_* doc lands
}

pub struct SessionCapsOverride {
    pub max_participants: u8,                           // V1 default 8; override 2..=12 V1+30d
    pub max_concurrent_per_cell: u32,                   // V1 default 50; override 10..=200
    pub reason: I18nBundle,                             // author's "why" — surfaces in admin UI
}

pub struct DisconnectGraceOverride {
    pub grace_duration_wall_seconds: u32,               // V1 default 30; override 0..=600
    pub reason: I18nBundle,
}

pub enum VoiceModeLock {
    Locked(VoiceMode),                                  // force all PCs to single mode (terse/novel/mixed)
    AllowList(Vec<VoiceMode>),                          // PC chooses from subset
    Free,                                               // engine default — PC chooses any
}
```

### §3.2 What DF04 does NOT own

- ❌ Lex axioms — `WA_001` owns
- ❌ Heresy weight + budget — `WA_002` owns
- ❌ Mortality config (`MortalityConfig`) — `WA_006` owns
- ❌ Time dilation (`actor_clocks` + `time_flow_rate`) — `TDIL_001` owns
- ❌ Forge admin UX — `WA_003` owns (DF04 admin actions ride on Forge)
- ❌ Rule REGISTRY navigation — DF04 concept-notes IS the navigation; no aggregate

### §3.3 V1+30d minimum scope

**Aggregate fields V1+30d:** `session_caps_override` + `disconnect_grace_override` only.
**V2+ additive (without breaking V1+30d):** `voice_mode_lock` (C1-D3 follow-up).
**V2 separate WA_* docs:** PvP consent (WA_007), Queue policy (WA_008), Turn fairness (WA_009).

**Ship V1+30d nếu:** session-caps OR disconnect-grace customization needed by author. Defer Q9 below until first author requests it.

---

## §4 — Invariants DF4-A1..A6

| ID | Invariant | Why |
|---|---|---|
| **DF4-A1 (Umbrella discipline)** | DF04 holds ONLY runtime overrides for engine-defaulted concerns. Each rule sub-feature owns its primary aggregate + RealityManifest extension separately | Avoid double-ownership conflicts with WA_001/002/006 + TDIL |
| **DF4-A2 (Override is optional)** | Every override field is `Option<T>`. None = use engine default. Authors opt-in per concern | Backward compat; sparse storage; reality-creation simplicity |
| **DF4-A3 (No retroactive overrides)** | Override changes apply prospectively from `last_updated_fiction_time`. Past turns unaffected | Replay-determinism per EVT-A9 |
| **DF4-A4 (Cross-rule precedence: Lex > Heresy > Mortality > Override)** | Higher-precedence rule wins on conflict. WA_001 Lex axioms override anything; DF04 overrides cannot violate Lex | Author canon supremacy |
| **DF4-A5 (Forge audit-grade)** | Override edits via `Forge:EditWorldRuleOverride` only; full audit per WA_003; cannot edit without admin role | Reality integrity |
| **DF4-A6 (Sub-feature migration outbound)** | When un-designed sub-feature gets dedicated WA_* doc (e.g., WA_007 PvP), its override field MIGRATES OUT of `reality_rule_overrides` to that sub-feature's own aggregate. Schema version bump. | Avoid `reality_rule_overrides` becoming god-object as sub-features mature |

---

## §5 — Override resolution semantics (runtime read path)

Engine reads engine-default + DF04 override at runtime; combine:

```rust
fn resolve_session_cap(reality_id: RealityId) -> u8 {
    let override_row = read_t2(reality_rule_overrides, reality_id);
    match override_row.and_then(|r| r.session_caps_override) {
        Some(o) => o.max_participants,
        None => DF5_DEFAULT_SESSION_CAP,  // 8
    }
}
```

**Performance:** override aggregate cached per-reality (DP-K6 subscribe pattern). Read overhead ~1µs per check; same as other reality-scoped aggregates.

**Validation at write-time:** override values must pass DF4-A4 precedence check:
- `session_caps_override.max_participants` MUST satisfy `2 <= n <= 12` (engine sanity bounds; reject `world_rule.session_cap_out_of_bounds`)
- `disconnect_grace_override.grace_duration_wall_seconds` MUST satisfy `0 <= n <= 600` (10 min max; reject `world_rule.grace_out_of_bounds`)
- `voice_mode_lock.Locked(m)` MUST be valid VoiceMode variant (already type-checked)
- Cross-feature: override cannot contradict WA_001 Lex axiom (e.g., Lex axiom "no PC death" + override grace=0 = OK; both consistent)

---

## §6 — Event mapping

| Event | EVT-T* | Sub-type | Producer |
|---|---|---|---|
| Override aggregate born (canonical seed at bootstrap) | EVT-T4 System | `RealityRuleOverridesBorn` | RealityBootstrapper |
| Override field set/updated | EVT-T3 Derived | `aggregate_type=reality_rule_overrides` Update | world-service via Forge |
| Forge edit override | EVT-T8 AdminAction | `Forge:EditWorldRuleOverride { field, before, after, reason }` | WA_003 Forge |
| Sub-feature migration outbound (DF4-A6) | EVT-T8 AdminAction | `Forge:MigrateOverrideToSubFeature { field, target_aggregate }` | engine schema upgrade |
| Reality close cascade | EVT-T3 Derived | `aggregate_type=reality_rule_overrides` Update (state=Frozen) | EM-7 cascade |

**No new EVT-T* category.** Maps cleanly onto existing taxonomy.

---

## §7 — V-tier scope cut

| Feature | V1 | V1+30d | V2 | V3 |
|---|---|---|---|---|
| `reality_rule_overrides` aggregate (empty schema; placeholder) | ✅ | | | |
| `session_caps_override` field | | ✅ | | |
| `disconnect_grace_override` field | | ✅ | | |
| `voice_mode_lock` field (C1-D3) | | | ✅ | |
| `Forge:EditWorldRuleOverride` admin action | | ✅ | | |
| Bulk override operations across realities | | | ✅ | |
| Override migration tooling (DF4-A6) | | | ✅ | |
| WA_007 PvP consent — separate doc | | | ✅ | |
| WA_008 Queue policy — separate doc | | ✅ | | |
| WA_009 Turn fairness — separate doc | | | ✅ | |
| Quest eligibility override (M3-D3) | | | | ✅ |
| accept_player_quests toggle (F3-D6) | | | | ✅ |

**V1 ship:** empty aggregate placeholder only (so RealityBootstrapper can create row). No fields populated. No `Forge:EditWorldRuleOverride` admin yet. Reality just uses engine defaults across the board.

**V1+30d ship:** add session_caps_override + disconnect_grace_override + Forge edit; first 2 author-requested overrides land.

---

## §8 — Q1-Q9 PENDING (3-batch deep-dive expected)

Status: PENDING — to be LOCKED via deep-dive when promotion to DRAFT scheduled.

| Q# | Question | Default proposal |
|---|---|---|
| **Q1** | Override aggregate scope — single `reality_rule_overrides` row vs per-rule-feature override fields scattered? | Single row (this concept) — simpler reads; sparse Option fields |
| **Q2** | Override semantics — full replace vs delta vs additive? | Full replace per field — `Option<T>` field reads None=default, Some=override; no merging logic |
| **Q3** | Override authoring path — RealityManifest at bootstrap vs Forge runtime only? | Both — RealityManifest declares initial overrides; Forge edits at runtime; both write to same aggregate |
| **Q4** | Cross-rule precedence — confirm DF4-A4 order Lex > Heresy > Mortality > Override? | YES default; Lex supreme; override cannot violate Lex axiom |
| **Q5** | Validation timing — write-time only vs runtime check on each consumer read? | Write-time (DP validator slot); runtime reads trust validated state |
| **Q6** | Per-reality default vs global default fallback chain | Global engine constant → reality_rule_overrides field if Some → consumer reads single value |
| **Q7** | Override schema versioning — how add new fields without breaking V1+30d realities? | `schema_version` field on aggregate; new fields = additive Option<T>; old realities migrate lazily on first override touch |
| **Q8** | Migration outbound (DF4-A6) — when WA_007 PvP lands, how move pvp_consent field out cleanly? | One-shot `Forge:MigrateOverrideToSubFeature` admin action; deletes field from this aggregate; new aggregate inherits value |
| **Q9** | Un-designed sub-features placeholder strategy — list-only vs mini-spec inline? | LIST-ONLY V1 per user choice (option ii); WA_007/008/009 docs created when first need surfaces |

**Batch suggestion (3 batches):**
- Batch 1 (Q1+Q2+Q3): Aggregate scope + semantics + authoring
- Batch 2 (Q4+Q5+Q6): Precedence + validation + default chain
- Batch 3 (Q7+Q8+Q9): Versioning + migration + sub-feature strategy

---

## §9 — Closure-pass impact (light)

DF04 design will trigger closure-pass-extensions on:

| Feature | Closure-pass scope | Magnitude |
|---|---|---|
| **WA_003 Forge** | Add `Forge:EditWorldRuleOverride` AdminAction sub-shape; add `Forge:MigrateOverrideToSubFeature` (V2+) | LOW |
| **DF5 Session/Group Chat** | DRAFT spec references DF04 override path for session_caps + disconnect_grace per-reality customization | LOW |
| **PL_001 Continuum** | Disconnect grace consumer queries DF04 override aggregate | LOW |
| **PL_002 Grammar** | Voice mode lock consumer queries DF04 (V2 territory) | LOW |
| **RealityManifest** | OPTIONAL `rule_overrides` extension at bootstrap | LOW |
| **07_event_model** | Register `aggregate_type=reality_rule_overrides` EVT-T3; `RealityRuleOverridesBorn` EVT-T4 | LOW |

**Total closure-pass-extension scope: 6 features touched, all LOW magnitude.** No CANDIDATE-LOCK reopens. Single combined boundary commit feasible.

**NO impact on:**
- WA_001 Lex (axiom system unchanged)
- WA_002 Heresy (weight system unchanged)
- WA_006 Mortality (config schema unchanged)
- TDIL_001 (clock model unchanged)
- ACT_001 / PCS_001 / NPC_001..003 (actor substrate unchanged)
- AIT_001 (tier system unchanged)
- 06_data_plane (kernel unchanged)

---

## §10 — Reference / file hygiene

- **Author:** main session 2026-04-27 (post DF5 concept-notes COMPLETE; Architecture-scale closure deferred)
- **Origin commit:** TBD (concept-notes phase, no boundary lock yet)
- **Creates new files:**
  - `features/DF/DF04_world_rules/00_CONCEPT_NOTES.md` (this file)
- **Modifies:**
  - `features/DF/DF04_world_rules/_index.md` — status Placeholder → CONCEPT
- **Does NOT touch:**
  - `_boundaries/` files (no lock claimed)
  - Other catalog files (no IDs minted yet — DF4-* deferred to DRAFT)
  - SESSION_PATCH.md (concept-notes doesn't gate phase)
  - WA_001/002/006 / TDIL / DF5 / etc. — all locked, no reopens needed
- **Blocks:**
  - Nothing — V1+30d primary; no V1 ship dependency
- **Unblocked by:** DF5 concept-notes (already COMPLETE 2026-04-27); WA_001/002/006 (CANDIDATE-LOCK)
- **Estimated time to DRAFT (post-Q-deep-dive):** ~3-4 hours combined (smaller spec ~400-500 lines; 6 closure-pass-extensions LOW magnitude)

---

## §11 — Status footer

**Last updated:** 2026-04-27 (CONCEPT NEW)

**Phase:** Concept brainstorm captured + 6 invariants DF4-A1..A6 proposed + aggregate sketch + Q1-Q9 PENDING.

**Status downgrade noted:** original DF04 placeholder marked V1-blocking; after WA_001/002/006 + DF5 + TDIL closures, DF04 is **V1+30d primary** (override aggregate); V2+ for un-designed sub-features. SESSION_HANDOFF.md agenda may need update to reflect this.

**Promotion gate (to DRAFT):**
- ❌ Q1-Q9 NOT yet LOCKED (deep-dive when first override use case surfaces)
- ✅ `_boundaries/_LOCK.md` free
- ❌ NOT consumed by other features yet (no V1 ship dependency)
- 🟡 DRAFT not urgent — wait for first author-requested override OR V1+30d planning trigger

**Cross-feature DRAFT-time coordination (when promotion gate met):**
1. [ ] Single combined `[boundaries-lock-claim+release]` commit
2. [ ] DF04 spec creation (~400-500 lines `DF04_001_world_rules_overrides.md`)
3. [ ] Coordinate with 6 closure-pass extensions (WA_003 / DF5 / PL_001 / PL_002 / RealityManifest / 07_event_model)
4. [ ] V1+30d backend implementation (just session_caps + disconnect_grace overrides)

**Architectural decisions LOCKED 2026-04-27:**
- §1 DF04 = umbrella, NOT atomic feature
- §2 V1-blocking status DOWNGRADED to V1+30d
- §3 Single `reality_rule_overrides` aggregate scope (light, sparse)
- §3.2 Out-of-scope items strictly avoided (WA_*/TDIL/ACT own their domains)
- §4 6 invariants DF4-A1..A6 proposed
- §5 Override resolution semantics (runtime read; DP-K6 cached)
- DF04 sub-features get separate WA_007/008/009 docs (option ii) — NOT inline-spec'd

**Risk callouts:**
- Q1 single aggregate vs scattered — premature optimization risk if V2+ needs many fields
- DF4-A6 migration outbound — need clear protocol when first WA_007 lands; reserved for that phase
- Override schema versioning Q7 — additive policy; bumping schema_version requires cascade migration
- Nothing here blocks V1; DF04 truly demoted

---

**Concept-notes phase READY for promotion when first override use case surfaces. Most decisions converged via this concept-notes capture. Q-deep-dive expected to complete in 3 batches with mostly approve-recommendation responses (similar to TDIL pattern). Sub-features tracking in §1 architecture map; un-designed (PvP / Queue / Turn fairness) parked with explicit V2/V1+30d tier per option (ii).**
