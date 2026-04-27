# DF04 — World Rules — Index

> **Status:** **CONCEPT 2026-04-27 — V1-blocking status DOWNGRADED to V1+30d primary** — concept-notes captured at [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md). DF04 = UMBRELLA umbrella that organizes ALL rule sub-features (WA_001 Lex / WA_002 Heresy / WA_006 Mortality / TDIL_001 Time / + un-designed WA_007 PvP / WA_008 Queue / WA_009 Turn fairness). DF04_001 itself owns ONLY runtime override aggregate for engine-defaulted concerns. 6 invariants DF4-A1..A6 proposed. Q1-Q9 PENDING deep-dive.
>
> **Status downgrade rationale:** Original DF04 placeholder marked V1-blocking 2026-04-25 covering death behavior + paradox tolerance + canon strictness + time model + PvP consent + voice mode lock + session caps + disconnect policy + queue policy + turn fairness + quest eligibility. After WA_001/002/006 + DF5 + TDIL closures (2026-04-25 → 2026-04-27), 8 of 11 concerns resolved by other features. Remaining 3 concerns (PvP / Queue / Turn fairness) explicitly defer to V2 (option ii: separate WA_007/008/009 docs when first need surfaces). DF04_001 V1+30d ships with empty placeholder aggregate; first override field (session_caps OR disconnect_grace) lands V1+30d when first author requests customization.
>
> **Scope preview (revised post-hollowing-out):** `reality_rule_overrides` aggregate (T2/Reality, sparse Option fields); cross-rule precedence Lex > Heresy > Mortality > Override; `Forge:EditWorldRuleOverride` admin action; sub-feature migration outbound protocol (DF4-A6).
>
> **Scope size estimate (DRAFT):** ~400-500 lines (smaller than DF5/AIT/TDIL because most architecture already converged via concept-notes + WA_* sub-features owned separately).

**Active:** (empty — concept-notes phase doesn't claim lock; main session captured concept)

---

## DF04 sub-feature map

```
DF4 — World Rules (UMBRELLA)
├── ✅ WA_001 Lex (physics/ability/energy axioms)         [CANDIDATE-LOCK 2026-04-25]
├── ✅ WA_002 Heresy (forbidden-knowledge contamination)  [CANDIDATE-LOCK 2026-04-25]
├── ✅ WA_002b Heresy lifecycle                           [CANDIDATE-LOCK 2026-04-25]
├── ✅ WA_006 Mortality (death mode config)               [CANDIDATE-LOCK 2026-04-25]
├── ✅ TDIL_001 Time Dilation (multi-realm time)          [DRAFT 2026-04-27]
├── 🟡 DF04_001 Runtime override aggregate                [CONCEPT 2026-04-27 — this folder]
├── 📦 WA_007 PvP consent (PC-D2)                         V2 — separate doc when first need
├── 📦 WA_008 Queue policy (S7-D6)                        V1+30d — separate doc when first need
├── 📦 WA_009 Turn fairness (SR11-D7)                     V2 — separate doc when first need
└── ✅ WA_003 Forge (author console; cross-cutting)       [CANDIDATE-LOCK 2026-04-25]
```

---

## When DRAFT work starts

When Q1-Q9 LOCKED + first override use case surfaces (V1+30d trigger):

- `00_CONCEPT_NOTES.md` (✅ already created 2026-04-27)
- `DF04_001_world_rules_overrides.md` (main DRAFT spec ~400-500 lines)
- (V2+ future: when first un-designed sub-feature lands, create `WA_007_pvp_consent.md` etc. as siblings; DF04 stays as umbrella + override aggregate)

DRAFT promotion triggers 6 cross-feature closure-pass-extensions (per `00_CONCEPT_NOTES.md` §9):
- WA_003 Forge (admin action sub-shape)
- DF5 Session/Group Chat (override consumer)
- PL_001 Continuum (disconnect grace consumer)
- PL_002 Grammar (voice mode lock consumer V2)
- RealityManifest (OPTIONAL rule_overrides extension)
- 07_event_model (additive EVT-T3 + EVT-T4 sub-types)

**No closure-pass impact on:** WA_001/002/006 (rule logic unchanged) / TDIL_001 / ACT_001 / PCS_001 / NPC_001..003 / AIT_001 / 06_data_plane.

---

## Reading order

1. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §1 — Architectural finding: DF04 is umbrella
2. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §2 — Hollowing-out check + V1-blocking downgrade rationale
3. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §3 — `reality_rule_overrides` aggregate sketch
4. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §4 — 6 invariants DF4-A1..A6
5. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §8 — Q1-Q9 PENDING deep-dive
6. [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §9 — 6 closure-pass-extensions queued

---

## Pre-CONCEPT history (archived note)

Original placeholder 2026-04-25 marked DF04 as V1-blocking biggest unknown. Designed before WA_*/TDIL/DF5 closures. After 2026-04-27 cascade closures, DF04 scope substantially hollowed out; status downgraded to V1+30d primary. Pre-concept text NOT preserved (superseded entirely by `00_CONCEPT_NOTES.md`).
