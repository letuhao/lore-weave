<!-- CHUNK-META
source: design-track manual seed 2026-04-27
chunk: cat_17_TDIL_time_dilation.md
namespace: TDIL-*
generated_by: hand-authored (architecture-scale catalog seed)
-->

## TDIL — Time Dilation (architecture-scale; 4-clock relativity model)

> Architecture-scale catalog. NOT a foundation tier feature (foundation 6/6 closed at PROG_001). TDIL_001 is Tier 5+ Actor Substrate scaling/architecture feature (mirror AIT_001 / ACT_001 pattern). Owns `TDIL-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `TDIL-A*` | Axioms (locked invariants) |
> | `TDIL-D*` | Per-feature deferrals (V1+30d / V2 / V3 phases) |
> | `TDIL-Q*` | Open questions (closure pass items) |

### Core architectural axioms

**TDIL-A1 (Convention B time_flow_rate):** `time_flow_rate` = proper time per wall time. Default 1.0; >1 faster (Dragon Ball chamber); <1 slower (Tây Du Ký heaven). Range V1 [0.001, 1000.0].

**TDIL-A2 (4-clock model):** Realm clock (per channel; existing PL_001 fiction_clock) + actor_clock (proper time τ integrated) + soul_clock (BodyOrSoul::Soul progressions) + body_clock (BodyOrSoul::Body progressions + future aging V2+).

**TDIL-A3 (Per-turn O(1) Generator semantic):** Generators fire per turn-event with elapsed-time parameter (NOT per-day). Computation = base × elapsed × multiplier (O(1)). Replaces PROG_001/RES_001/AIT_001 day-boundary semantic via closure-pass revisions.

**TDIL-A4 (Channel-bound vs actor-bound discipline):** Channel-bound generators (CellProduction/NPCAutoCollect/CellMaintenance) read wall_advance. Actor-bound generators (HungerTick/CultivationTick/Aging) read appropriate proper-time clock per BodyOrSoul.

**TDIL-A5 (Atomic-per-turn travel):** Actor in EXACTLY ONE channel for entire turn. No mid-turn cross-channel. Travel takes turns; teleport gate V1+ still costs time.

**TDIL-A6 (Per-realm turn streams):** Each channel has independent fiction_clock; advances ONLY when channel actor turn-events occur. Idle channels frozen.

**TDIL-A7 (Cross-realm observation O(1)):** Mortal PC observes heaven NPC after N heaven-turns: 1 calculation regardless of magnitude.

**TDIL-A8 (Worldline monotonicity):** actor_clock / soul_clock / body_clock monotonically increasing V1. Forge edits to past clock values FORBIDDEN PERMANENTLY V1+.

**TDIL-A9 (Replay determinism FREE V1):** Static rates + per-channel turn streams + atomic travel + monotonic clocks = deterministic by construction.

**TDIL-A10 (Xuyên không clock-split):** PCS_001 §S8 mechanic creates new PC with actor_clock=0 + soul_clock=source_a.soul_clock + body_clock=source_b.body_clock. Twin paradox preserved.

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| TDIL-1 | `time_flow_rate: f32` field on MAP_001 MapLayoutDecl (channel-level) | ✅ | V1 | MAP-1 | [TDIL_001 §3.2](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#32-channel-level--cell-level-layering) |
| TDIL-2 | `time_flow_rate_override: Option<f32>` on PF_001 PlaceDecl (cell-level REPLACE semantic) | ✅ | V1 | PF-1 | [TDIL_001 §3.2-3.3](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#33-override-replace-semantic) |
| TDIL-3 | NEW aggregate `actor_clocks` (T2/Reality, owner=Actor; ALWAYS-PRESENT V1) | ✅ | V1 | ACT-1 (actor_core pattern) | [TDIL_001 §4.1](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#41-aggregate-definition) |
| TDIL-4 | 3 actor-side clocks (actor_clock + soul_clock + body_clock; i64 each) | ✅ | V1 | TDIL-3 | [TDIL_001 §4.1](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#41-aggregate-definition) |
| TDIL-5 | InitialClocksDecl on CanonicalActorDecl (V1 OPTIONAL author override) | ✅ | V1 | ACT-1 | [TDIL_001 §4.3](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#43-initialclocksdecl-extension-on-canonicalactordecl) |
| TDIL-6 | Per-turn lockstep advancement V1 | ✅ | V1 | TDIL-3 | [TDIL_001 §5.1](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#51-v1-lockstep-semantic) |
| TDIL-7 | Generator clock-source matrix locked (channel-bound vs actor-bound) | ✅ | V1 | RES_001 + PROG_001 + AIT_001 closure passes | [TDIL_001 §6](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#6-generator-clock-source-matrix-q6-locked) |
| TDIL-8 | Per-turn O(1) Generator semantic (corrects PROG/RES/AIT day-boundary) | ✅ | V1 | TDIL-7 | [TDIL_001 §6.4](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#64-closure-pass-coordination) |
| TDIL-9 | Per-channel turn stream (causally driven; idle = frozen) | ✅ | V1 | PL-1 fiction_clock (existing) | [TDIL_001 §7.1](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#71-per-channel-turn-stream) |
| TDIL-10 | Atomic-per-turn travel (mid-turn cross forbidden) | ✅ | V1 | PL-2 /travel command | [TDIL_001 §7.2](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#72-atomic-per-turn-travel-q7) |
| TDIL-11 | Cross-realm observation O(1) materialization | ✅ | V1 | AIT_001 §7.5 (closure-pass-revised) | [TDIL_001 §7.4](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#74-cross-realm-observation-o1) |
| TDIL-12 | Xuyên không clock-split contract (soul→soul; body→body; actor=0) | ✅ | V1 | PCS_001 §S8 mechanic | [TDIL_001 §8](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#8-xuyên-không-clock-split-contract-q11-locked) |
| TDIL-13 | LLM context dilation hint (~30-50 tokens per dilation-aware actor) | ✅ | V1 | NPC_001 + AIT_001 AssemblePrompt | [TDIL_001 §9](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#9-llm-context-dilation-awareness-q9-locked) |
| TDIL-14 | Replay determinism FREE V1 (static rates) | ✅ | V1 | EVT-A9 | [TDIL_001 §10](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#10-replay-determinism-q10-locked) |
| TDIL-15 | Worldline monotonicity (Forge past-edits FORBIDDEN PERMANENTLY) | ✅ | V1 | TDIL-V4 | [TDIL_001 §10.1](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#101-v1-trivially-deterministic) |
| TDIL-16 | TDIL-V1..V4 validator slots (AtomicTravel + RateBounds + InitialClocks + WorldlineMonotonicity) | ✅ | V1 | PL_005 + RealityManifest | [TDIL_001 §12](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#12-validator-chain) |
| TDIL-17 | `time_dilation.*` RejectReason namespace (4 V1 + 6 V1+30d reservations) | ✅ | V1 | TDIL-1..16 | [TDIL_001 §16](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#16-rejectreason-rule_id-catalog) |
| TDIL-18 | V1+30d — Forge:EditChannelTimeFlowRate (TDIL-D1) | 📦 | V1+ | TDIL-1 | [TDIL_001 §15](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md#15-deferrals-catalog-tdil-d1d16) |
| TDIL-19 | V1+30d — Time chamber DilationTarget enum (BodyOnly/SoulOnly; TDIL-D4) | 📦 | V1+ | TDIL-3 | TDIL-D4 |
| TDIL-20 | V1+30d — Soul wandering (soul_clock advances; body_clock paused; TDIL-D5) | 📦 | V1+ | TDIL-3 + PL_005 SoulProject | TDIL-D5 |
| TDIL-21 | V1+30d — Per-actor subjective_rate_modifier Option B (TDIL-D3) | 📦 | V1+ | TDIL-3 | TDIL-D3 |
| TDIL-22 | V1+30d — Forge:AdvanceChannelClock (TDIL-D2) | 📦 | V1+ | TDIL-A6 | TDIL-D2 |
| TDIL-23 | V1+30d — Combat reaction-speed reads body_clock (TDIL-D9) | 📦 | V1+ | PL_005 closure | TDIL-D9 |
| TDIL-24 | V2+ — Aging integration (TDIL-D6) | 📦 | V2+ | future AGE feature | TDIL-D6 |
| TDIL-25 | V2+ — Cross-realm quest deadlines (TDIL-D7) | 📦 | V2+ | QST_001 | TDIL-D7 |
| TDIL-26 | V2+ — Time travel CTC (TDIL-D8) | 📦 | V2+ | separate feature design | TDIL-D8 |
| TDIL-27 | V3+ — Lorentz-aware combat formula (TDIL-D10) | 📦 | V3+ | DF7-equivalent V2+ | TDIL-D10 |

### V1 minimum delivery

17 V1 catalog entries (TDIL-1..17 all ✅ V1). Architecture-scale companion to AIT_001 + ACT_001.

### V1+30d deferrals (TDIL-18..23 + TDIL-D11..D16)

12 V1+30d items planned for fast-follow window after V1 ship.

### V2+ deferrals (TDIL-24..27)

4 V2/V3+ items tied to future features (AGE / QST_001 / CTC time-travel / DF7-equivalent combat).

### Coordination notes

- **Closure-pass revisions in this commit (mechanical):** PROG_001 Q3f day-boundary → turn-boundary; RES_001 Q4 day-boundary → turn-boundary; AIT_001 §7.5 materialization O(1)
- **PCS_001 brief §S8 reference** to TDIL_001 §8 xuyên không clock-split contract
- **ACT_001 actor_clocks integration** as 5th actor-related aggregate (mirror actor_core ALWAYS-PRESENT pattern)
- **Future feature coordination:** PCS_001 / CULT_001 / AGE V2+ / QST_001 V2 / CTC V2+
- **i18n compliance** throughout per RES_001 §2 cross-cutting pattern
- **Einstein relativity origin** per user direction 2026-04-27; physics analysis verified sound (concept-notes §3)
- **Convention B locked** (`time_flow_rate` = proper time per wall time) — physics-correct + player-friendly UI
