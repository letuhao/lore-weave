# 02_world_authoring — Index

> **Category:** WA — World Authoring
> **Catalog reference:** [`catalog/cat_02_WA_world_authoring.md`](../../catalog/cat_02_WA_world_authoring.md) (owns `WA-*` stable-ID namespace)
> **Purpose:** Features around authoring + managing worlds (book-to-reality setup, canon level assignment, world rules authoring, tier-based permissions).

**Active:** WA_001 Lex (DRAFT 2026-04-25)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| WA_001 | **Lex** (LX) | Per-reality World Rules — physics + ability + energy axioms (DF4 sub-feature: physics/ability/energy only). Closed-set AxiomKind (17 entries + Other), Permissive V1 default, deterministic `classify_action` dictionary, validator slot in EVT-V*. | DRAFT 2026-04-25 | [`WA_001_lex.md`](WA_001_lex.md) | uncommitted |

**Companion (not yet drafted):** WA_002 Forbidden Knowledge & Cross-Reality Contamination — adds AllowedWithBudget axiom variant + contamination tracking + cascade-consequence model on top of Lex.

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
