<!-- CHUNK-META
source: design-track manual seed 2026-04-27 (replaces archived multiverse PO_001 entries)
chunk: cat_03_PO_player_onboarding.md
namespace: PO-*
generated_by: hand-authored (first user-visible feature catalog seed)
-->

## PO — Player Onboarding (first user-visible feature post-foundation closure; 3 V1 onboarding modes; AI-driven character creation)

> First user-visible feature catalog. Owns `PO-*` stable-ID namespace.
> **Replaces archived multiverse PO_001 entries** (2026-04-27 — old `FEATURE_CATALOG.ARCHIVED.md` content superseded by new PO_001 design).
>
> | Sub-prefix | What |
> |---|---|
> | `PO-A*` | Axioms (locked invariants) |
> | `PO-D*` | Per-feature deferrals (V1+ / V2 / V2+ phases) |
> | `PO-Q*` | Open questions (closure pass items) |
> | `PO-C*` | Cross-aggregate consistency rules |

### Core architectural axioms

**PO-A1 (FE-first design discipline):** PO_001 is the first user-visible feature. UX validated BEFORE backend feature spec via wireframes Phase 0 commits (19855a5b + 4c4fd6d7). 12 HTML/CSS/MD files demonstrate concrete UI; 46 V1 actor settings audited across 14 features.

**PO-A2 (3-mode onboarding):** V1 ships 3 onboarding modes per Q1 A LOCKED — `OnboardingMode { Canonical / Custom / XuyenKhong }`. Each targets distinct user persona: Mode A casual/lazy + Mode B builder + Mode C narrative-driven. All 3 use existing PCS_001 primitives (Forge:RegisterPc + Forge:BindPcUser); no new substrate required.

**PO-A3 (3-level Custom PC depth):** Mode B ships 3-level UX progression per Q2 A LOCKED — Basic Wizard 8 steps + Advanced Settings (~46 V1 fields) + AI Character Assistant. Graceful degradation order: AI fail → Advanced manual → Basic defaults.

**PO-A4 (AI Character Assistant V1 active):** Per Q3 A LOCKED — natural-language input via chat-service (Python/FastAPI; LiteLLM provider abstraction); reality-aware constraint checking via knowledge-service; iterative tweak; 6 quick actions. Constraint awareness: skips V1+ deferred fields automatically.

**PO-A5 (PC creation cascade orchestration):** Per Q9 A LOCKED — Forge:CompleteOnboarding triggers synchronous cascade across 14 features same turn (PCS → ACT → EF → IDF×5 → FF → FAC → REP → TIT → PROG → RES → TDIL → SR11). Cross-aggregate validator C-rule PO-C1.

**PO-A6 (Per-reality author-declared):** Onboarding config declared per-reality via RealityManifest.onboarding_config (OPTIONAL V1) — modes_enabled subset + canonical_pcs ref list + ai_assistant_enabled bool + default_spawn_cell. Mirrors PROG-A1 + REP_001 + FAC_001 author-discipline.

**PO-A7 (Single-PC per reality V1):** Per Q5 A LOCKED + PCS-A9 LOCKED — cap=1 V1; PO-D2 deferral covers multi-PC activation when PCS-D3 cap relaxed V1+. Stage 0 schema validator C13 (PCS_001) enforces.

**PO-A8 (Schema-stable / activation-deferred V1+ discipline):** PO_001 V1 declares full schema for V1+ deferred features (auto-save draft / mobile responsive / OAuth / multi-PC roster); activation V1+ via consumer feature milestone. Zero migration V1 → V1+. Pattern matches TIT-A8 + REP_001 deferred-validator approach.

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PO-1 | `actor_user_session` aggregate (T2/Reality, sparse per-(actor, session)) | ✅ | V1 | EF-1, PCS-1, DP-A14 | [PO_001 §3.1](../features/03_player_onboarding/PO_001_player_onboarding.md#31-actor_user_session-t2--reality-scope-sparse--primary) |
| PO-2 | `OnboardingConfigDecl` shape (RealityManifest declaration; OPTIONAL V1) | ✅ | V1 | PO-1, RES-23 (i18n) | [PO_001 §2.1](../features/03_player_onboarding/PO_001_player_onboarding.md#21-onboardingconfigdecl-realitymanifest-declaration) |
| PO-3 | `OnboardingMode` enum (3-variant Canonical/Custom/XuyenKhong) | ✅ | V1 | PO-2 | [PO_001 §2.1](../features/03_player_onboarding/PO_001_player_onboarding.md#21-onboardingconfigdecl-realitymanifest-declaration) |
| PO-4 | `canonical_pcs: Vec<ActorRef>` RealityManifest extension (Mode A picker source) | ✅ | V1 | PO-2, ACT-1 | [PO_001 §4.1](../features/03_player_onboarding/PO_001_player_onboarding.md#41-fields-added-by-po_001) |
| PO-5 | EVT-T8 AdminAction sub-shape `Forge:CompleteOnboarding` (V1 active; orchestrates 14-feature cascade) | ✅ | V1 | PCS-1, ACT-1, EF-1, WA-3 (forge_audit_log) | [PO_001 §5.1](../features/03_player_onboarding/PO_001_player_onboarding.md#51-evt-t8-administrative-sub-shapes-v1) |
| PO-6 | EVT-T8 AdminAction sub-shapes `Forge:CreateOnboardingDraft` + `Forge:UpdateOnboardingDraft` (V1 schema-reserved; V1+30d active per PO-D3) | ✅ schema | V1 | PO-1 | [PO_001 §5.1](../features/03_player_onboarding/PO_001_player_onboarding.md#51-evt-t8-administrative-sub-shapes-v1) |
| PO-7 | EVT-T1 Submitted sub-type `OnboardingCompleted` (narrative milestone for LLM) | ✅ | V1 | EVT-A11, PO-1 | [PO_001 §5.2](../features/03_player_onboarding/PO_001_player_onboarding.md#52-evt-t1-submitted-sub-type--onboardingcompleted) |
| PO-8 | EVT-T3 Derived sub-type `OnboardingDraftUpdated` (V1 schema-reserved; V1+30d active per PO-D3) | ✅ schema | V1 | EVT-A11, PO-1 | [PO_001 §5.3](../features/03_player_onboarding/PO_001_player_onboarding.md#53-evt-t3-derived-sub-type--onboardingdraftupdated-v130d) |
| PO-9 | Mode A canonical PC picker flow (BG3 Origin Character pattern) | ✅ | V1 | PO-3, PO-4 | [PO_001 §9.1](../features/03_player_onboarding/PO_001_player_onboarding.md#91-mode-a-canonical-pc-selection-bg3-origin-character-pattern) |
| PO-10 | Mode B Custom PC 8-step Basic Wizard | ✅ | V1 | PO-3, IDF-1..5, FAC-1, FF-1, ACT-1, PROG-1 | [PO_001 §9.2](../features/03_player_onboarding/PO_001_player_onboarding.md#92-mode-b-custom-pc-complete-cascade-basic-wizard-8-steps) |
| PO-11 | Mode B Advanced Settings (~46 V1 fields edit grid) | ✅ | V1 | PO-10, [ACTOR_SETTINGS_AUDIT.md](../features/03_player_onboarding/wireframes/ACTOR_SETTINGS_AUDIT.md) | [PO_001 §2](../features/03_player_onboarding/PO_001_player_onboarding.md#2--domain-concepts) |
| PO-12 | Mode B AI Character Assistant (chat-service + knowledge-service constraint awareness) | ✅ | V1 | chat-service, knowledge-service, PO-10 | [PO_001 §6](../features/03_player_onboarding/PO_001_player_onboarding.md#6--ai-character-assistant-q3-a-locked) |
| PO-13 | Mode C Xuyên Không Arrival 5-step flow (Disco Elysium amnesia + wuxia transmigration) | ✅ | V1 | PCS-1 (PcBodyMemory), TDIL-1, PO-3 | [PO_001 §9.3](../features/03_player_onboarding/PO_001_player_onboarding.md#93-mode-c-xuyên-không-arrival-cascade) |
| PO-14 | PC creation cascade C-rule PO-C1 (synchronous 14-feature chain on Forge:CompleteOnboarding) | ✅ | V1 | All Tier 5 features | [PO_001 §7](../features/03_player_onboarding/PO_001_player_onboarding.md#7--cross-aggregate-validator-q9-a-locked--immediate-cascade-on-forgecompleteonboarding) |
| PO-15 | RealityManifest 2 OPTIONAL V1 extensions (onboarding_config + canonical_pcs) | ✅ | V1 | PO-2, PO-4 | [PO_001 §4](../features/03_player_onboarding/PO_001_player_onboarding.md#4--realitymanifest-extensions) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| PO-16 | RejectReason `onboarding.*` namespace (7 V1 + 5 V1+ reservations) | ✅ | V1 | RES-* (i18n contract) | [PO_001 §8](../features/03_player_onboarding/PO_001_player_onboarding.md#8--v1-reject-rules-onboarding-namespace) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| PO-17 | RESOLVES PCS-D1 (V1+ runtime login flow PC creation; full V1) | ✅ | V1 | PCS-* | [PO_001 §13.1](../features/03_player_onboarding/PO_001_player_onboarding.md#131-resolves-cross-feature-deferrals) |
| PO-18 | RESOLVES PCS-D10 (V1+ PO_001 Player Onboarding integration; full V1) | ✅ | V1 | PCS-* | [PO_001 §13.1](../features/03_player_onboarding/PO_001_player_onboarding.md#131-resolves-cross-feature-deferrals) |
| PO-19 | Wireframes Phase 0 (12 files HTML/CSS/MD; commits 19855a5b + 4c4fd6d7) | ✅ | V1 | — | [`wireframes/index.html`](../features/03_player_onboarding/wireframes/index.html) |
| PO-20 | ACTOR_SETTINGS_AUDIT.md (46 V1 settings × 14 features inventory) | ✅ | V1 | All Tier 5 features | [`wireframes/ACTOR_SETTINGS_AUDIT.md`](../features/03_player_onboarding/wireframes/ACTOR_SETTINGS_AUDIT.md) |
| PO-21 | First turn drop-in immediate (Q9 LOCKED; SR11 turn UX state machine + LLM scene narration) | ✅ | V1 | SR11, chat-service | [PO_001 §1](../features/03_player_onboarding/PO_001_player_onboarding.md#1--purpose--v1-minimum-scope) |
| PO-22 | Inline tooltips minimal V1 + minimal Tutorial overlay on first turn | ✅ | V1 | UI_COPY_STYLEGUIDE | [PO_001 §1](../features/03_player_onboarding/PO_001_player_onboarding.md#1--purpose--v1-minimum-scope) |
| PO-23 | Email + password account creation V1 (auth-service); OAuth V1+ (PO-D1) | ✅ | V1 | auth-service | [PO_001 §1](../features/03_player_onboarding/PO_001_player_onboarding.md#1--purpose--v1-minimum-scope) |
| PO-24 | Cap=1 PC per reality V1 (PCS-A9 LOCKED); multi-PC V1+ (PO-D2) | ✅ | V1 | PCS-A9 | [PO_001 §1](../features/03_player_onboarding/PO_001_player_onboarding.md#1--purpose--v1-minimum-scope) |
| PO-25 | V1+ — OAuth account creation (PO-D1) | 📦 | V1+ | auth-service OAuth providers | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-26 | V1+ — Multi-PC roster screen (PO-D2; when PCS-D3 cap relaxed) | 📦 | V1+ | PCS-D3 | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-27 | V1+30d — Auto-save per step + draft resume (PO-D3) | 📦 | V1+ | PO-1 | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-28 | V1+30d — Mobile responsive layout (PO-D4) | 📦 | V1+ | PO-19 | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-29 | V1+30d — Richer tutorial overlay (PO-D10) | 📦 | V1+ | UI_COPY_STYLEGUIDE | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-30 | V1+30d — Reality-themed onboarding skin (PO-D11) | 📦 | V1+ | PO-2 | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-31 | V1+30d — Onboarding telemetry analytics (PO-D12) | 📦 | V1+ | analytics infra | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-32 | V2 — Character export/import cross-reality migration (PO-D6) | 📦 | V2 | WA_002 Heresy | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-33 | V2 — Community-shared character templates (PO-D7) | 📦 | V2 | sharing infra | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-34 | V2+ — Reality switcher mid-session (PO-D5) | 📦 | V2+ | PCS-D3 | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-35 | V2+ — AI-generated character portraits (PO-D8) | 📦 | V2+ | image-gen service | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |
| PO-36 | V2+ — Voice-to-text input for AI Assistant (PO-D9) | 📦 | V2+ | speech-to-text infra | [PO_001 §12](../features/03_player_onboarding/PO_001_player_onboarding.md#12--deferrals-catalog-po-d1po-d12) |

### Per-feature deferrals (PO-D*)

| Deferral | Description | Phase |
|---|---|---|
| PO-D1 | V1+ — OAuth account creation (Google + Discord; auth-service provider integration) | V1+ |
| PO-D2 | V1+ — Multi-PC roster screen (when PCS-D3 cap=1 → cap=N relaxed) | V1+ |
| PO-D3 | V1+30d — Auto-save per step + draft resume (actor_user_session.onboarding_draft schema activation) | V1+ |
| PO-D4 | V1+30d — Mobile responsive layout (breakpoints <768px) | V1+ |
| PO-D5 | V2+ — Reality switcher mid-session (no-logout reality change) | V2+ |
| PO-D6 | V2 — Character export/import (cross-reality migration via WA_002 Heresy) | V2 |
| PO-D7 | V2 — Community-shared character templates (social feature) | V2 |
| PO-D8 | V2+ — AI-generated character portraits (image-gen service deferred) | V2+ |
| PO-D9 | V2+ — Voice-to-text input for AI Assistant (speech-to-text infra V2+) | V2+ |
| PO-D10 | V1+30d — Richer tutorial overlay post-creation (~10-15 step interactive) | V1+ |
| PO-D11 | V1+30d — Reality-themed onboarding skin variant | V1+ |
| PO-D12 | V1+30d — Onboarding telemetry analytics (A/B testing + funnel tracking) | V1+ |

### Cross-aggregate consistency rules (PO-C*)

| Rule | Description | Owner-feature | Trigger | Reject rule |
|---|---|---|---|---|
| PO-C1 | PC creation cascade orchestration: Forge:CompleteOnboarding triggers synchronous 14-feature cascade same turn (PCS → ACT → EF → IDF×5 → FF → FAC → REP → TIT → PROG → RES → TDIL → SR11) | PO_001 (orchestrator over 14 features) | Forge:CompleteOnboarding EVT-T8 | (no reject; cascade applies all events atomically) |
| PO-C2 | OnboardingConfigDecl.canonical_pcs subset of canonical_actors[kind=Pc] | PO_001 + ACT_001 | RealityManifest bootstrap | `onboarding.canonical_pc_unauthorized` (V1+ if needed) |
| PO-C3 | OnboardingConfigDecl.default_spawn_cell ∈ RealityManifest.places (cell-tier) | PO_001 + PF_001 | RealityManifest bootstrap | `onboarding.spawn_cell_unauthorized` |
| PO-C4 | Mode B draft_data validation: race_id ∈ canonical_races + faction_id ∈ canonical_factions + spawn_cell ∈ places | PO_001 (delegates to per-feature validators) | Forge:CompleteOnboarding | `onboarding.draft_invalid` |
| PO-C5 | PC cap=1 V1 enforced (per actor_user_session.user_id; matches PCS-C13 cap) | PO_001 + PCS_001 | Forge:CompleteOnboarding | `onboarding.user_already_has_pc` + `onboarding.pc_cap_exceeded` |
| PO-C6 | Mode A canonical PC binding: actor.user_id_init must be None at bind time | PO_001 + PCS_001 | Forge:CompleteOnboarding (Mode A) | `onboarding.canonical_pc_unavailable` |

### Open questions (PO-Q*)

NONE V1. All Q1-Q10 LOCKED via 4-batch deep-dive 2026-04-27 zero revisions:
- Q1 A LOCKED (3 modes V1)
- Q2 A LOCKED (3-level Custom PC)
- Q3 A LOCKED (AI Assistant V1 active)
- Q4 A LOCKED (email + password V1; OAuth V1+)
- Q5 A LOCKED (cap=1 V1 per PCS-A9)
- Q6 A LOCKED (locked-in per session V1)
- Q7 A LOCKED (all-or-nothing V1; auto-save V1+30d)
- Q8 A LOCKED (desktop-only V1; mobile V1+30d)
- Q9 A LOCKED (immediate spawn cell drop-in)
- Q10 A LOCKED (inline tooltips minimal V1)

### V1 minimum delivery

24 V1 catalog entries (PO-1..PO-24 all ✅ V1; PO-6 + PO-8 schema-active V1 + runtime V1+30d). First user-visible feature post-foundation closure.

### V1+30d deferrals (PO-D3 + PO-D4 + PO-D10..D12)

5 V1+30d items planned for the 30-day fast-follow window after V1 ship.

### V1+ deferrals (PO-D1 + PO-D2)

2 V1+ items tied to consumer feature milestones (auth-service OAuth + PCS-D3 cap relaxation).

### V2 + V2+ deferrals (PO-D5..D9)

5 V2/V2+ deferrals tied to cross-reality migration + sharing infra + image-gen + speech-to-text + sub-session migration.

### Coordination / discipline notes

- **First user-visible feature** — PO_001 is the gateway from auth-service login to actual gameplay. UX validated FE-first via wireframes (commits 19855a5b + 4c4fd6d7) before backend feature spec.
- **3-mode architecture (PO-A2)** — Canonical (BG3 Origin pattern) + Custom (BG3 + Cyberpunk lifepath) + XuyenKhong (Disco Elysium amnesia + wuxia transmigration).
- **Mode B 3-level UX progression (PO-A3)** — Basic Wizard 8 steps + Advanced Settings (~46 V1 fields) + AI Character Assistant. Graceful degradation: AI fail → Advanced manual → Basic defaults.
- **AI Assistant V1 active (PO-A4)** — chat-service + LiteLLM + knowledge-service constraint awareness. 6 quick actions (Surprise me / Make tragic / Make cunning / Generate backstory / Validate / Open full screen).
- **PC creation cascade orchestration (PO-A5 + PO-C1)** — synchronous 14-feature cascade on Forge:CompleteOnboarding same turn. Joins existing C1-C25 cross-aggregate consistency rules.
- **Schema-stable / activation-deferred V1+ discipline (PO-A8)** — actor_user_session.onboarding_draft + 2 EVT-T8 schema reserved V1; activation V1+30d.
- **Resolves 2 cross-feature deferrals** — PCS-D1 + PCS-D10 (full V1).
- **No new substrate required** — PO_001 V1 consumes 14 locked features as DECLARATIVE inputs.
