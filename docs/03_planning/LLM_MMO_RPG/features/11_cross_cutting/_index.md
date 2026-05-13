# 11_cross_cutting — Index

> **Category:** CC — Cross-cutting
> **Catalog reference:** [`catalog/cat_11_CC_cross_cutting.md`](../../catalog/cat_11_CC_cross_cutting.md) (owns `CC-*` stable-ID namespace)
> **Purpose:** Cross-cutting concerns that span all feature categories — accessibility (CC-6 already MITIGATED via A11Y_POLICY), i18n/l10n, theming, telemetry surface, feature-flag UX.

**Active:** (empty — no agent currently editing)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|

(No features designed yet. First feature will live at `CC_001_<name>.md`.)

---

## Kernel touchpoints (shared across CC features)

- `decisions/locked_decisions.md` — CC-6-D1..D7 (a11y WCAG 2.2 AA, already locked)
- `../../02_governance/A11Y_POLICY.md` — a11y governance + tooling
- `../../02_governance/UI_COPY_STYLEGUIDE.md` — copy + tone + i18n conventions
- `03_multiverse/` MV5-primitive P1 `locale` on reality_registry
- `02_storage/S09_prompt_assembly.md` §12Y — per-locale prompt templates
- `02_storage/SR11_turn_ux_reliability.md` §12AN.10 — registered error codes with per-locale templates

---

## Naming convention

`CC_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
