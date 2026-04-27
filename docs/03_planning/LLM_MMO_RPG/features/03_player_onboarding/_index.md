# 03_player_onboarding — Index

> **Category:** PO — Player Onboarding (first user-visible feature; consumes PCS_001 + 13 other Tier 5 features)
> **Catalog reference:** `catalog/cat_03_PO_player_onboarding.md` (planned; created at DRAFT 2/4 commit per established pattern)
> **Purpose:** First-user UX — account creation, first-PC creation (3 V1 modes: Canonical / Custom / Xuyên Không), first-reality-entry, tutorial/tooltips, first-run scenarios. **First user-visible feature; gateway from auth-service to actual gameplay.**

**Active:** PO_001 — **Player Onboarding** (DRAFT 2026-04-27 — Q-LOCKED 4-batch deep-dive 2026-04-27 zero revisions; DRAFT 2/4 commit this commit with boundary updates + catalog seed)

**Folder closure status:** **OPEN — DRAFT 2/4 IN PROGRESS 2026-04-27** — wireframes Phase 0 (commits 19855a5b + 4c4fd6d7) + Phase 0 backend kickoff (commit 9245666c) + DRAFT 2/4 (this commit) complete; next: Phase 3 cleanup (commit 3/4) + CANDIDATE-LOCK closure (commit 4/4).

**V1+ priority signal:**
- PCS_001 PCS-D1 LOCKED: "V1+ runtime login flow PC creation → PO_001 Player Onboarding feature when concrete"
- PCS_001 PCS-D10 LOCKED: "V1+ PO_001 Player Onboarding integration → UI flow consumes PCS_001 primitives"
- PCS_001 _index.md kernel touchpoint: "PO_001 V1+ Player Onboarding — PC creation form UI consumes PCS_001 primitives (Forge:RegisterPc + Forge:BindPcUser)"
- 99_changelog.md 2026-04-27 (TIT_001 closure): "PO_001 Player Onboarding (UI flow consumes PCS_001 primitives)" listed as #1 next-priority candidate
- User direction 2026-04-27: "ok, tiếp tục với PO_001 — nhưng trước đó nên thiết kế FE trước; thảo luận FE sau đó chúng ta quyết định draft html trước khi đi sâu vào thiết kế tính năng" (FE-first approach)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (wireframes) | **wireframes/** — 12 files HTML/CSS/audit MD | DRAFT 2026-04-27 — FE-first design: 8 HTML screens (landing + reality select + path choice + 3 modes + advanced + AI Assistant + confirm + first turn) + shared wuxia ink-wash + reality-themed accent CSS + ACTOR_SETTINGS_AUDIT.md (46 V1 settings × 14 features) + index navigation hub | [`wireframes/index.html`](wireframes/index.html) | 19855a5b → 4c4fd6d7 |
| (concept) | **00_CONCEPT_NOTES.md** — PO_001 brainstorm + Q1-Q10 + cross-feature audit | CONCEPT 2026-04-27 — captures user framing post-wireframes + 10-dimension scope analysis + Q1-Q10 placeholder for batched deep-dive + 14-feature integration audit | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit Phase 0) |
| (research) | **01_REFERENCE_GAMES_SURVEY.md** — reference games survey | DRAFT 2026-04-27 — 9-system survey: BG3 (PRIMARY anchor) + Cyberpunk 2077 (lifepath) + Disco Elysium (amnesia) + AI Dungeon (custom prompt) + NovelAI (writer mode) + FFXIV (MMO standard) + Lost Ark (class-first) + Pathfinder Wrath (deep customization) + Persona series (cinematic). Anchor: BG3 dual-mode + Disco Elysium amnesia + AI Dungeon freedom hybrid | [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) | (this commit Phase 0) |
| PO_001 | **Player Onboarding** (PO) | (planned) — First-user UX feature with 3 V1 onboarding modes (Canonical PC / Custom PC / Xuyên Không Arrival); consumes PCS_001 Forge:RegisterPc + Forge:BindPcUser cascade; integrates IDF_001..005 + FAC_001 + REP_001 + TIT_001 + PROG_001 + ACT_001 + RES_001 + PF_001 + TDIL_001; uses M7 progressive disclosure + SR11 first-turn UX. ~700-900 line DRAFT planned. RESOLVES PCS-D1 + PCS-D10. 4-commit cycle. | **CONCEPT** Phase 0 2026-04-27 | (planned `PO_001_player_onboarding.md`) | (planned DRAFT 2/4) |

---

## Why this folder kicks off FE-first

Per user direction 2026-04-27: "thiết kế FE trước - thảo luận FE sau đó chúng ta quyết định draft html trước khi đi sâu vào thiết kế tính năng" (FE-first approach).

PO_001 is THE first user-visible feature. UX validates BEFORE backend feature spec lock-in. Wireframes Phase 0 commit 19855a5b + 4c4fd6d7 demonstrate concrete UI:
- 8 main screens (landing/reality select/path choice/3 modes/advanced/AI Assistant/confirm/first turn)
- 3 V1 onboarding modes anchored on BG3 + Disco Elysium + AI Dungeon hybrid
- ~46 V1 actor settings audited across 14 owning features
- AI Assistant with reality-aware constraint checking + iterative tweak

Concept notes phase formalizes:
1. User framing (post-wireframes review)
2. Worked examples (Wuxia 3-mode walkthrough + Modern Saigon variant)
3. Gap analysis (10 dimensions)
4. Boundary intersections (14 locked features touched)
5. Critical Q1-Q10 for V1 minimum scope
6. Reference materials slot

---

## Kernel touchpoints (shared across PO features)

- `03_multiverse/06_M_C_resolutions.md` §9.6 — M7 progressive disclosure (M7-D1..D5); onboarding enforces tier defaults via Mode B "Skip → use defaults" CTA
- `02_storage/S11_service_to_service_auth.md` — auth-service; first account creation via api-gateway-bff
- `02_storage/S12_websocket_security.md` — first WS connection + ticket exchange
- `02_storage/SR11_turn_ux_reliability.md` §12AN — first turn UX (turn state machine visible from turn 1; PO_001 §05 first turn screen renders SR11 state machine)
- `02_governance/UI_COPY_STYLEGUIDE.md` — tooltip + first-run copy governance
- `_boundaries/01_feature_ownership_matrix.md` — actor_user_session aggregate added at DRAFT 2/4
- `_boundaries/02_extension_contracts.md` §1.4 — `onboarding.*` rule_id namespace
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension for onboarding_config (per-reality mode availability)
- `00_pc_systems/PCS_001_pc_substrate.md` PCS-D1 + PCS-D10 — PO_001 RESOLVES (runtime login flow PC creation + UI integration)
- `00_actor/ACT_001_actor_foundation.md` — CanonicalActorDecl shape consumed by Mode A canonical PC picker
- `00_identity/IDF_001..005` — race + language + personality + origin + ideology decls consumed in Mode B custom wizard
- `00_family/FF_001_family_foundation.md` — family relations input in Mode B advanced
- `00_faction/FAC_001_faction_foundation.md` — initial faction membership in Mode B
- `00_reputation/REP_001_reputation_foundation.md` — initial reputation rows (default Neutral; advanced mode allows per-faction set)
- `00_titles/TIT_001_title_foundation.md` — V1+ origin pack default_titles via TIT-D10
- `00_progression/PROG_001_progression_foundation.md` — initial progression values per ClassDefaultDecl
- `00_resource/RES_001_resource_foundation.md` — initial vital pools + currencies + items
- `17_time_dilation/TDIL_001_time_dilation_foundation.md` — actor_clocks initialized at PC creation
- `00_entity/EF_001_entity_foundation.md` — entity_binding cell membership at spawn
- `02_world_authoring/WA_003_forge.md` — Forge admin handlers (Forge:RegisterPc + Forge:BindPcUser via 3-write atomic pattern)
- `chat-service` (Python/FastAPI) — AI Character Assistant V1 dependency (LLM via LiteLLM)

---

## 3-mode onboarding architecture

Per wireframes commit 19855a5b + 4c4fd6d7 + concept notes Q1 LOCKED (anticipated):

| Mode | Pattern reference | UX | Backend cascade |
|---|---|---|---|
| **(A) Canonical PC** | BG3 Origin Character | Pick from preset PC roster (5 pre-declared canonical_actors[kind=Pc]) | Forge:BindPcUser to existing PC |
| **(B) Custom PC** | BG3 Custom + Cyberpunk lifepath | 8-step wizard (basic) → Advanced settings (~46 fields) → AI Assistant (natural-language) | Forge:RegisterPc + Forge:BindPcUser cascade |
| **(C) Xuyên Không Arrival** | Disco Elysium amnesia + wuxia transmigration | 5-step soul/body/leakage wizard | Forge:RegisterPc with body_memory_init populated + Forge:BindPcUser |

All 3 modes converge to common post-flow: Confirm & Bind → First Turn (SR11 state machine).

---

## Naming convention

`PO_<NNN>_<short_name>.md`. Sequence per-category. PO_001 is the foundation; future PO_NNN reserved for V1+/V2 extensions (PO_002 V1+ reality switcher / multi-PC roster / OAuth integration / mobile-first responsive variant).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

PO_001 is **first user-visible feature** post-foundation closure. Resolves 2 V1+ deferrals from PCS_001:

- **PCS-D1** (PCS_001): V1+ runtime login flow PC creation → PO_001 V1 RESOLVES (account creation + Forge:BindPcUser via UI)
- **PCS-D10** (PCS_001): V1+ PO_001 Player Onboarding integration → PO_001 V1 RESOLVES (UI flow consumes PCS_001 primitives Forge:RegisterPc + Forge:BindPcUser)

**Boundary discipline (anticipated; locked at DRAFT):**
- PO_001 V1 = first-user UX flow (account → reality select → mode pick → PC creation → confirm → first turn); consumes 14 locked features as DECLARATIVE inputs
- PO_001 V1+ = OAuth integration (Google/Discord) + multi-PC roster (when PCS_001 cap=1 relaxed via PCS-D3) + mobile-first responsive
- V2+ reality switcher within session + character export/import + community-shared character templates + AI-generated character portraits
- Cross-feature: chat-service (Python/FastAPI) integration for AI Character Assistant V1 LLM calls
- Synthetic actors forbidden V1 (consistent with universal substrate discipline)
