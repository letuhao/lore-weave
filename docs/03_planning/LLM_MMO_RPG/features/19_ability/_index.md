# 19_ability — Index

> **Category:** ABL — Abilities (the activatable-effect catalogue: what `Skill` in COMB_001 §3 actually
> refers to, how an ability is acquired, what it costs, and what it is allowed to do).
> **Catalog reference:** `catalog/cat_19_ABL_ability.md` (NOT YET CREATED — defer to CANDIDATE-LOCK).
> **Purpose:** Resolves audit finding **AUD-F10** ([`../../12_module_coverage_audit.md`](../../12_module_coverage_audit.md))
> — *"COMB_001's action set includes `Skill` and COMB_002 references `skill.range`, but no doc defines
> what a skill is, how it's acquired, or its cost model."*

**Active:** ABL_001 — **Ability Foundation** (**DRAFT 2026-07-26**).

---

## Why this folder exists — and why it is not inside `18_combat`

Combat is the **loudest** consumer of abilities, not the only one:

| Caller | Entry point | Status |
|---|---|---|
| COMB_001 §3 | the `Skill` combat verb | **V1 active** — this is what ABL_001 declares |
| PL_005 `Use` (out of combat) | an ability fired outside an encounter (a healing technique, a ritual) | **V1 active** — `usable_out_of_combat` |
| PL_007 item `Use` | today fires PL_007's own `UseEffectDecl`, **not** an ability | **not yet** — see ABL-Q9 |
| Passive abilities from worn gear | would need a `grants_ability` field on PL_007's `EquipDecl` | **proposed only** — that field does **not** exist today |

> **Accuracy note.** PL_007 (parallel track, 2026-07-26) has **no ability concept**: its items declare a
> closed 7-variant `UseEffectDecl` and its `EquipDecl` carries modifiers, not abilities. ABL_001 therefore
> does **not** claim those call sites — it *proposes* unifying them (ABL-Q9 / ABL_001 §4.2), which requires
> the PL_007 owner's agreement. Until then the two vocabularies coexist and overlap, which is redundant but
> not incorrect. The namespace argument below still holds on the first two rows alone.

Homing the catalogue in `18_combat` would make PL_005's out-of-combat `Use` depend on the combat feature;
homing it in `00_progression` would put an *activatable effect* inside a doc that deliberately owns only
*competence values* (PROG_001 §1: no level, no power rating). Its own namespace is the honest placement,
and it mirrors how DF07 was given the derived-stat layer rather than folding it into PROG_001.

---

## The naming trap this folder exists to defuse

PROG_001's `ProgressionType::Skill` and COMB_001's `Skill` verb are **different things with the same word**,
and the concept notes ([`../18_combat/00_CONCEPT_NOTES.md`](../18_combat/00_CONCEPT_NOTES.md) §6) conflate
them: *"V1 skills come from PROG_001 skill kinds"*. They cannot, because a PROG kind is a **number that
grows** (`swordsmanship: 8`) and a combat `Skill` is an **effect you fire** (`rising_dragon_cut`).

ABL_001 §2 fixes the vocabulary: an **Ability** is the activatable; a **progression kind** is what *gates
and scales* it. See ABL-A1.

---

## Feature list

| ID | Conversational name | Title | Status | File |
|---|---|---|---|---|
| ABL_001 | **Ability** (ABL) | **Ability Foundation** — closed `EffectOp` dispatch vocabulary; `PowerTerm` routing damage back through the COMB_001 law-chain; derived known-set (no aggregate); PROG-gated acquisition; encounter-ephemeral cooldowns | DRAFT 2026-07-26 | [`ABL_001_ability_foundation.md`](ABL_001_ability_foundation.md) |

## Exported stable IDs

`ABL-A1..A7` axioms · `ABL-Q1..Q9` locked decisions · `ABL-D1..D11` deferrals · `ABL-V1..V7` validators ·
`AC-ABL-1..13` acceptance criteria · `ability.*` reject namespace.

## Kernel touchpoints

- `_boundaries/01_feature_ownership_matrix.md` — `ABL-*` prefix; **no new aggregate** (ABL-A4); cooldown
  state is a field inside COMB_001's already-ephemeral `combat_session`
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension `abilities: Vec<AbilityDecl>`
  (OPTIONAL; a reality with no abilities is playable — ABL-Q8)
- `00_progression/PROG_001` — `requires: Vec<ProgressionReq>` reads `actor_progression`; **no PROG change**
- `DF/DF07_pc_stats/DF07_001` — `PowerTerm` reads DF07 stat slots from the combat snapshot
- `04_play_loop/PL_007` — `UseEffectDecl` ⊂ `EffectOp` reconciliation **proposed** (ABL §4.2 / ABL-Q9);
  a `grants_ability` field on `EquipDecl` is part of that proposal, **not an existing field**
- `18_combat/COMB_001` — the `Skill` verb; §4 law-chain substitution; `combat_session.cooldowns`
- `18_combat/COMB_002` — `skill.range` resolves to `AbilityDecl.range` under Chebyshev + corner-line LoS
- `18_combat/COMB_003` — the `ModifyThreat` effect op

## Naming convention

`ABL_<NNN>_<short_name>.md`. ABL_001 is the foundation; future ABL_NNN reserved for V1+ extensions
(ability trees, channelled/reaction abilities, AoE shape library).
