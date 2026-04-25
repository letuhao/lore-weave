# 02_world_authoring — Index

> **Category:** WA — World Authoring
> **Catalog reference:** [`catalog/cat_02_WA_world_authoring.md`](../../catalog/cat_02_WA_world_authoring.md) (owns `WA-*` stable-ID namespace)
> **Purpose:** Features around authoring + managing worlds (book-to-reality setup, canon level assignment, world rules authoring, tier-based permissions).

**Active:** WA_001 Lex (DRAFT 2026-04-25)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| WA_001 | **Lex** (LX) | Per-reality World Rules — physics + ability + energy axioms (DF4 sub-feature: physics/ability/energy only). Closed-set AxiomKind (17 entries + Other), Permissive V1 default, deterministic `classify_action` dictionary, validator slot in EVT-V*. | DRAFT 2026-04-25 | [`WA_001_lex.md`](WA_001_lex.md) | e752519 |
| WA_002 | **Heresy** (HER) | Forbidden Knowledge & Cross-Reality Contamination. Extends LexSchema v1→v2 (`Axiom.allowance: Allowance` enum); per-actor `ContaminationDecl` + budget tracking + EnergySubstrate; WorldStability 5-stage state machine (Stable/Strained/Cracking{1..3}/Catastrophic/Shattered) with admin-driven V1 transitions. Resolves the user's "transmigrator-brings-magic-into-no-magic-world" concern. Resolves LX-D1/D2/D3. | DRAFT 2026-04-25 | [`WA_002_heresy.md`](WA_002_heresy.md) | 9c49b09 |
| WA_003 | **Forge** (FRG) | Author Console — UX flow + API contract for editing Lex axioms, declaring Heresy ContaminationDecls, and (with admin escalation) advancing WorldStability stages. RBAC matrix (4 roles × ImpactClass), 12 V1 EditActions + 5 read views, dual-actor approval flow for Tier1 edits, audit log. Resolves LX-D4 + HER-D10. | DRAFT 2026-04-25 | [`WA_003_forge.md`](WA_003_forge.md) | 5903ccd |
| WA_004 | **Charter** (CHR) | Co-Author management — invitation lifecycle (7d TTL), accept/decline/cancel/expire, revoke (RealityOwner) + resign (self), JWT-refresh on grant change. 2 new aggregates (`coauthor_grant`, `coauthor_invitation`); reuses `forge_audit_log` from WA_003. V1 flat Co-Author role; ownership-transfer deferred to WA_005. Resolves FRG-D5. | DRAFT 2026-04-25 | [`WA_004_charter.md`](WA_004_charter.md) | 301472f |
| WA_005 | **Succession** (SUC) | Reality ownership transfer — multi-stage state machine (Pending 14d → Cooldown 7d → Finalized) with recipient acceptance + admin S5 dual-actor approval + 7-day cancel window. T3 atomic Finalize touches `reality_registry` + `coauthor_grant`. 1 new aggregate (`ownership_transfer`). V1 recipient must be Co-Author; admin approval mandatory; blocked during Catastrophic/Shattered world stages. Resolves CHR-D1. | DRAFT 2026-04-25 | [`WA_005_succession.md`](WA_005_succession.md) | uncommitted |

**Sibling DF4 sub-features (separate future WA_* docs):** death model (PC-B1), PvP consent (PC-D2), voice mode lock (C1-D3), session caps (H3-NEW-D1), queue policy (S7-D6), disconnect policy (SR11-D4), turn fairness (SR11-D7), time model mode (MV12-D6).

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
