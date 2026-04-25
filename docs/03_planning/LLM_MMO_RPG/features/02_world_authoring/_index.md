# 02_world_authoring — Index

> **Category:** WA — World Authoring
> **Catalog reference:** [`catalog/cat_02_WA_world_authoring.md`](../../catalog/cat_02_WA_world_authoring.md) (owns `WA-*` stable-ID namespace)
> **Purpose (post-2026-04-25 closure pass):** WA's intent is **"validate rules of reality + detect paradox + allow controlled bypass"**. After the closure pass, WA owns the per-reality CONFIG + VALIDATOR layer for axioms, contamination, and death mode. Author UI (Forge) is also WA-scoped because it edits the WA configs. Identity/account/ownership concerns are NOT WA — those moved to `10_platform_business/` (PLT_001 Charter, PLT_002 Succession).
>
> **Folder closure status:** **CLOSED for V1 design 2026-04-25.** All 5 features (WA_001 Lex + WA_002 Heresy + WA_002b lifecycle + WA_003 Forge + WA_006 Mortality) at CANDIDATE-LOCK with §14 (or §12) acceptance criteria. LOCK pending integration tests in downstream services. No further design work in WA folder until V2+ schema bumps or new sibling DF4 sub-features open new design threads.

**Active:** none (folder closed for design)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| WA_001 | **Lex** (LX) | Per-reality World Rules — physics + ability + energy axioms (DF4 sub-feature: physics/ability/energy only). Closed-set AxiomKind (17 entries + Other), Permissive V1 default, deterministic `classify_action` dictionary, validator slot in EVT-V*. §14 acceptance criteria added 2026-04-25 (10 scenarios). | **CANDIDATE-LOCK** 2026-04-25 | [`WA_001_lex.md`](WA_001_lex.md) | e752519 → closure pending |
| WA_002 | **Heresy** (HER) | Contract layer §1-§10: Forbidden Knowledge & Cross-Reality Contamination. Extends LexSchema v1→v2 (`Axiom.allowance: Allowance` enum); per-actor `ContaminationDecl` + budget tracking + EnergySubstrate; WorldStability 5-stage state machine. Resolves LX-D1/D2/D3. Closure-tightened 2026-04-25 (split + acceptance). | **CANDIDATE-LOCK** 2026-04-25 | [`WA_002_heresy.md`](WA_002_heresy.md) | 9c49b09 → closure pending |
| WA_002b | Heresy lifecycle (HER-L) | Lifecycle layer §11-§17: 3 sequences (within-budget allowed / cap-exceeded / admin stage transition) + §14 acceptance criteria (10 scenarios AC-HER-1..10) + deferrals (HER-D1..D12, HER-D8 boundary-tracked) + cross-refs + readiness. | **CANDIDATE-LOCK** 2026-04-25 | [`WA_002b_heresy_lifecycle.md`](WA_002b_heresy_lifecycle.md) | closure pending |
| WA_003 | **Forge** (FRG) | Author Console — UX flow + API contract for editing Lex axioms, declaring Heresy ContaminationDecls, and (with admin escalation) advancing WorldStability stages. RBAC matrix (4 roles × ImpactClass), 12 V1 EditActions + 5 read views, dual-actor approval flow for Tier1 edits, audit log. 📐 Contains design patterns extractable to future CC_NNN cross-cutting feature (RBAC + dual-actor + audit infra) — patterns are V1-essential here, extraction is V2+ optimization not boundary fix. §14 acceptance criteria added 2026-04-25 (10 scenarios). Resolves LX-D4 + HER-D10. | **CANDIDATE-LOCK** 2026-04-25 | [`WA_003_forge.md`](WA_003_forge.md) | 5903ccd → closure pending |
| ~~WA_004~~ → **PLT_001** | (relocated) | Co-Author management. Originally drafted here as WA_004 Charter; relocated 2026-04-25 to `10_platform_business/` because identity/co-author management is platform/account territory, not "validate rules of reality" which is WA's original intent. See [`../10_platform_business/PLT_001_charter.md`](../10_platform_business/PLT_001_charter.md). | RELOCATED 2026-04-25 | (moved) | 301472f → relocate pending |
| ~~WA_005~~ → **PLT_002** | (relocated) | Reality ownership transfer. Originally drafted here as WA_005 Succession; relocated 2026-04-25 to `10_platform_business/` because account-ownership lifecycle is platform/account territory, not WA. See [`../10_platform_business/PLT_002_succession.md`](../10_platform_business/PLT_002_succession.md). | RELOCATED 2026-04-25 | (moved) | 9d8ac58 → relocate pending |
| WA_006 | **Mortality** (MOR) | Per-reality death-mode CONFIG only — closed-set DeathMode (`Permadeath` V1 default, `RespawnAtLocation`, `Ghost`) + per-PC overrides. Mechanics (state machine, A6 detection, hot-path check, respawn flow, dispute UX) explicitly handed off to PCS_001 / 05_llm_safety / PL_001/002 / NPC. §12 acceptance criteria added 2026-04-25 (6 scenarios). Resolves PC-B1 config layer. | **CANDIDATE-LOCK** 2026-04-25 (thin-rewrite from 730 → 403 lines closure pass) | [`WA_006_mortality.md`](WA_006_mortality.md) | 8aed4fa → de9cf1a → closure pending |

**Sibling DF4 sub-features (separate future WA_* docs):** PvP consent (PC-D2), voice mode lock (C1-D3), session caps (H3-NEW-D1), queue policy (S7-D6), disconnect policy (SR11-D4), turn fairness (SR11-D7), time model mode (MV12-D6). (Death model PC-B1 = WA_006 above.)

---

## What's NOT in WA (post-closure boundary clarity)

The following concerns were either **never WA** or were **relocated out** during the 2026-04-25 closure pass. Recording here so future agents don't accidentally re-add WA features that should live elsewhere.

### Relocated 2026-04-25

| Original | Relocated to | Why not WA |
|---|---|---|
| WA_004 Charter (co-author management) | [`10_platform_business/PLT_001_charter.md`](../10_platform_business/PLT_001_charter.md) | Identity / account / role-grant — platform/account concern, not "validate rules of reality" |
| WA_005 Succession (ownership transfer) | [`10_platform_business/PLT_002_succession.md`](../10_platform_business/PLT_002_succession.md) | Account ownership lifecycle — platform/account concern |

### Handed off to mechanics owners (V1 dependencies)

WA_006 Mortality CONFIG is in this folder. The MECHANICS that consume that config are owned by:

| Mechanic | Owner |
|---|---|
| `pc_mortality_state` aggregate (per-PC state machine) | **PCS_001** (PC substrate, when designed) |
| LLM death-detection sub-validator | **05_llm_safety** (A6 internals) |
| Hot-path mortality check on turn submission | **PL_001 / PL_002** |
| Respawn sweeper + sweeper-driven Dying→Alive transitions | **PL_001 / PCS_001** |
| False-positive dispute flow (admin review queue) | **05_llm_safety** + admin tooling |
| NPC reactions to death | **NPC_001 / NPC_002** |
| Combat damage HP-based death | **PCS_001** + future combat feature |

WA_003 Forge contains design patterns extractable to a future `CC_NNN_authoring_console_pattern.md` (RBAC matrix × ImpactClass + dual-actor approval + audit infra). Those are V1-essential here; the future extraction is V2+ optimization, not boundary fix.

### Patterns governed by `_boundaries/`

Drift watchpoints that span WA + other folders are tracked in [`../../_boundaries/`](../../_boundaries/):

| Watchpoint | Where authoritative |
|---|---|
| LX-D5 Lex slot ordering in EVT-V* | [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) |
| HER-D8 EVT-T11 WorldTick V1+30d activation | [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) |
| TurnEvent envelope additivity (rule_id namespace ownership) | [`_boundaries/02_extension_contracts.md` §1](../../_boundaries/02_extension_contracts.md) |
| RealityManifest envelope (composable extension) | [`_boundaries/02_extension_contracts.md` §2](../../_boundaries/02_extension_contracts.md) |

---

## Closure summary (2026-04-25)

WA folder underwent two passes:

1. **Boundary shrink (commit `4be727d` + `2cf52a3`):** WA_004 + WA_005 relocated to `10_platform_business/`; WA_003 + WA_006 marked over-extended.
2. **Closure pass (this commit):** §14 (or §12) acceptance criteria added to WA_001 / WA_002b / WA_003 / WA_006; WA_002 split into root + lifecycle to honor 800-line cap; WA_006 thin-rewritten from 730 → 403 lines (mechanics handed off to mechanics owners); WA_003 over-extension reframed as "patterns-for-future-extraction" (V1-essential, V2+ optimization).

After closure, WA folder has 5 active design docs all at CANDIDATE-LOCK:

| File | Lines | Acceptance |
|---|---|---|
| WA_001 Lex | ~656 | §14: 10 scenarios |
| WA_002 Heresy (root) | ~597 | (in WA_002b) |
| WA_002b Heresy lifecycle | ~277 | §14: 10 scenarios |
| WA_003 Forge | ~798 | §14: 10 scenarios |
| WA_006 Mortality | ~403 | §12: 6 scenarios |

Total: ~2,730 lines across 5 files. All under 800-line cap. All boundary-clean per `_boundaries/01_feature_ownership_matrix.md`.

LOCK granted to each feature when its acceptance scenarios pass integration tests in downstream services.

---

## Extension pattern — adding a future WA sub-feature

WA folder is **CLOSED for V1 design** but the extension pattern is documented here so future agents can add WA sub-features when a consumer feature opens that needs a per-reality author override.

### When to add a WA_NNN sub-feature

A new sub-feature belongs in WA **if AND ONLY IF all of:**

1. The concern is a per-reality CONFIG that authors declare
2. The concern is consumed by some OTHER feature (the "consumer") at runtime
3. V1 ships a hardcoded default in the consumer that the WA_NNN author override CHANGES
4. The override semantics fit WA's intent: **"validate rules of reality / detect paradox / allow controlled bypass"**

If 1-3 are true but 4 is not, the feature likely belongs elsewhere:
- **Identity / account / role** → `10_platform_business/` (PLT)
- **Cross-cutting UX / a11y / i18n** → `11_cross_cutting/` (CC)
- **NPC behavior** → `05_npc_systems/` (NPC)
- **PC stats / lifecycle** → `06_pc_systems/` (PCS)

### Canonical recipe (model: [WA_006 Mortality thin-rewrite](WA_006_mortality.md))

A WA_NNN sub-feature is a thin doc (~150-400 lines) following this skeleton:

```
§1   User story (author scenarios only — what configs the author writes)
§2   Domain concepts (closed enum + Config struct + Override struct)
§2.5 EVT-T* mapping (config edits → EVT-T8 ForgeEdit; runtime events
                      OWNED BY CONSUMER, not this feature)
§3   Aggregate inventory — ONE aggregate: <feature>_config (T2 Reality singleton)
§4   Tier+scope table (single row)
§5   DP primitives (config reads + Forge-routed writes only)
§6   Closed-set enum (V1 modes; later modes = V2+ deferred via schema bump)
§7   Pattern choices (V1 default; per-PC/per-actor overrides; UI via Forge;
                       mechanics elsewhere)
§8   Failure UX (config edit validation only; not runtime mechanics)
§9   Cross-service handoff (Forge-routed config edits)
§10  Sequence: bootstrap with config; sequence: per-PC/per-actor override added
§11  (optional) more sequences for nuanced cases
§12  Acceptance criteria (~5-8 scenarios for the config layer ONLY)
§13  Open questions deferred (point each at the right consumer)
§14  Cross-references — explicit "Mechanics owned by:" section pointing
     at the consumer feature(s)
§15  Implementation readiness checklist
```

Key rules:
- Aggregate count: **exactly 1** (the per-reality config singleton)
- Author UI: **always via Forge** (extends WA_003's EditAction enum)
- Mechanics: **never designed here** — explicit handoff to consumer
- Schema versioning: closed enum + `schema_version: u32` for future additions

### 7 known V1+ candidate sub-features

Each below has a locked design-decision but is NOT V1-blocking (V1 ships hardcoded defaults; DF4 author override is V2+):

| Future WA_NNN | Locked decision | Consumer that will trigger design | V1 default location |
|---|---|---|---|
| `WA_NNN_pvp_consent` | PC-D2 | PvP feature (V2+ — depends on combat) | "enabled within session" hardcoded |
| `WA_NNN_voice_mode_lock` | C1-D3 | PL-22 voice mode (PL_NNN future) | V1 default "mixed" |
| `WA_NNN_session_caps` | H3-NEW-D1, H3-NEW-D5 | PL_004 Session lifecycle (future) | V1 hardcoded 6 PCs / 4 NPCs / 10 total |
| `WA_NNN_queue_policy` | S7-D6 | PL_004 Session lifecycle (future) | V1 default; reality_registry.queue_policy reserved |
| `WA_NNN_disconnect_policy` | SR11-D4 | PL_004 / SR11 turn UX | V1 default `proceed-if-turn-complete` |
| `WA_NNN_turn_fairness` | SR11-D7 | PL_004 / SR11 turn UX | V1 hardcoded FIFO + tier-bump + 30% cap |
| `WA_NNN_time_model` | MV12-D6 | PL_001 Continuum + scheduled-events V1+30d | V1 paused-when-solo locked in PL_001 |

**Time model (MV12-D6) is the only one with a clean WA fit.** The others have stronger affinity to their consumer (PvP→combat, voice→PL-22, session caps→PL_004, etc.) — when those consumer features open, their author may choose to put the override in their own folder instead of pulling a WA_NNN. Either is acceptable; the boundary folder will record the chosen home.

### Pre-flight checklist (before drafting a new WA_NNN)

1. **Lock-claim** [`../../_boundaries/_LOCK.md`](../../_boundaries/_LOCK.md) per [`_boundaries/00_README.md`](../../_boundaries/00_README.md)
2. **Check ownership matrix** [`../../_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) to confirm no conflict with existing aggregates
3. **Confirm consumer is ready** — the runtime consumer feature must exist (or be co-designed); without a consumer, the config is dead
4. **Choose ID** — next free `WA_NNN` (WA_007 is the next free slot; WA_004/005 retired per foundation I15)
5. **Cite extension contracts** — if the new feature extends shared schemas (TurnEvent, RealityManifest, capability JWT), follow [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md)
6. **Reference WA_006 Mortality as canonical example** in the file's intro
7. **Lock-release** after committing both the new feature file AND the boundary matrix update

### Anti-patterns (don't do these)

- ❌ **Multiple aggregates per WA_NNN** — if you need >1 aggregate, the feature is too big OR it's mechanics (which doesn't belong in WA)
- ❌ **Designing the runtime mechanics here** — that's the consumer's job; WA_NNN is config-only
- ❌ **Reusing a retired ID** (WA_004 / WA_005) — foundation I15 stable-ID retirement rule
- ❌ **Skipping acceptance criteria** — even thin sub-features need §12-style acceptance for the config layer
- ❌ **Forgetting Forge integration** — author UI MUST go through WA_003 Forge's EditAction extension; do NOT build a custom UI per sub-feature
- ❌ **Author UI as a new aggregate** — Forge's `forge_audit_log` covers it; reuse, don't redefine

### When in doubt: don't add a WA_NNN

If the case is borderline, the safer answer is "this feature lives in <consumer's category>". WA's closure means the bar for adding new features here is HIGHER, not lower. The pattern is here for genuine "validate rules of reality" cases that emerge V2+; everything else has a better home.

---

## Kernel touchpoints (shared across WA features)

- `03_multiverse/01_four_layer_canon.md` — L1/L2/L3/L4 canon layers; world authors assign L1 axioms at world creation
- `03_multiverse/02_lifecycle_and_seeding.md` — reality lifecycle states; world author creates + owns reality
- `decisions/locked_decisions.md` — WA4-D1..D5 (category heuristics L1/L2 defaults)
- `02_storage/C03_meta_registry_ha.md` — reality_registry is the meta-layer for author ownership

---

## Naming convention

`WA_<NNN>_<short_name>.md` — e.g., `WA_001_world_template_schema.md`, `WA_002_canon_axiom_editor.md`. Sequence increments per-category (next free number).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
