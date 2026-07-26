# PL_007c — Item Contracts & Integration

> **Continued from:** [`PL_007_item.md`](PL_007_item.md). That file holds the **substrate** (§1–§8):
> why the feature exists, the domain concepts, the 7 axioms ITM-A1..A7, the two aggregates, the
> `ItemDef` shape, the equipment model + DF07 seam, the use-effect vocabulary, and the lifecycle +
> `Item:*` actions. **This file continues its section numbering (§9–§19)** rather than restarting at
> §1 — deliberately, because peer docs already cite `PL_007 §9.1`, `§11`, and `§12.8`, and renumbering
> would silently break those references. A citation of `PL_007 §N` for `N ≥ 9` resolves here.
>
> **Conversational name:** "Item contracts" (ITM-C). Read `PL_007` first; this file assumes ITM-A1..A7.
> **Companion:** [`PL_007b_inventory.md`](PL_007b_inventory.md) — the inventory half (ITM-A8/A9).
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** **DRAFT 2026-07-26** (split out of PL_007 at the review pass, when the combined doc
> reached 1150 lines against the track's 800-line hard cap — the same three-way shape PL_005 /
> PL_005b / PL_005c settled into for the same reason).
> **Holds:** §9 validators + `item.*` namespace + consistency rules · §10 event-model mapping ·
> §11 `RealityManifest` extensions · §12 cross-feature integration & closure-pass-extensions ·
> §13 sequences · §14 acceptance criteria · §15 deferrals · §16 open questions (all resolved) ·
> §17 cross-references · §18 readiness checklist · §19 review-pass findings ledger.

---
## §9 Validators

### 9.1 New sub-stage: **Stage 3.5.e `item_structural`**

Slots into the Stage 3.5 structural group (`_boundaries/03_validator_pipeline_slots.md`), **after
3.5.d cell_scene** — most specific last, per the group's stated ordering convention.

**Applicability predicate:** applies to `EVT-T1 Submitted` of sub-type `Item:*`, and to PL_005
`Use` / `Give` / `Strike` whose `tools[0]` is `InstrumentRef::Item`. Early-exits for every other
event — which is most of them.

**Explicitly NOT duplicated here** (non-vacuity discipline — a check that cannot fail is noise):
- *item exists* → EF_001 3.5.a `entity.unknown_entity`
- *item destroyed / removed* → EF_001 3.5.a `entity.entity_destroyed` / `entity_removed`
- *item lacks the affordance for this kind* → EF_001 3.5.a `entity.affordance_missing` (§5.3)
- *item's target place is destroyed* → PF_001 3.5.b
- *item action attempted during active combat* → COMB_001 COMB-V1 `combat.action_invalid_in_state` (§8.6)
- *drop target tile not placeable* → CSC_001 3.5.d `csc.item_on_non_placeable` — **but see the
  correction immediately below; this delegation did not work as written.**

> **Delegation defect found at review 2026-07-26 — a claimed check that could never fire.** The
> `csc.item_on_non_placeable` delegation was vacuous. CSC_001's 3.5.d **applicability predicate**
> (`_boundaries/03_validator_pipeline_slots.md`) reads: *"Write events modifying cell state —
> Forge:EditCellScene; PL_005 Strike Destructive cascade triggers; CSC's own Layer 3 LLM commit"* — and
> `Item:Drop` is **none of those**. So 3.5.d early-exits on every drop, and the check I delegated to it
> would never have run: a player could drop items onto non-placeable tiles indefinitely, and the doc
> would read as though that were covered. This is precisely the failure mode the non-vacuity rule exists
> to catch, and I introduced it in the same paragraph that names the rule.
>
> **Fix (applied):** `Item:Drop` and `Item:PickUp` are added to 3.5.d's applicability predicate, and
> registered as a **CSC_001 closure-pass extension** (§12.8) — the predicate belongs to CSC_001, so the
> boundary file records the change and CSC_001 absorbs it when next opened. The delegation is now
> load-bearing rather than decorative. AC-ITM-16 bites this: a drop onto a non-placeable tile must
> reject, and the test fails if 3.5.d early-exits.

PL_007's own checks are the ones no existing validator can express:

| ID | Check | Stage | rule_id |
|---|---|---|---|
| **ITM-V1** | `instance.def_id ∈ RealityManifest.item_defs` | 0 + 3.5.e | `item.unknown_def` |
| **ITM-V2** | Equip / Unequip / Use / Give-tool: `binding.location == HeldBy(agent)` | 3.5.e | `item.not_held` |
| **ITM-V3** | `equip.slot ∪ also_blocks ⊆ active slot profile` | 0 + 3.5.e | `item.slot_unknown` |
| **ITM-V4** | slot occupied by an item that cannot be implicitly unequipped (V1+ locked gear) | 3.5.e | `item.slot_occupied` |
| **ITM-V5** | every `EquipRequirement` satisfied (PROG_001 read) | 3.5.e | `item.equip_requirement_unmet` |
| **ITM-V6** | `def.equip.is_some()` for Equip | 3.5.e | `item.not_equippable` |
| **ITM-V7** | Use: `charges` is `None` **or** `> 0` | 3.5.e | `item.no_charges` |
| **ITM-V8** | Use: `def.use_effect.is_some()` | 3.5.e | `item.no_use_effect` |
| **ITM-V9** | PickUp: `binding.location == InCell(agent's current cell)` | 3.5.e | `item.not_in_cell` |
| **ITM-V10** | canonical seed: `def_id` collides with no `resource_kinds.kind_id` (ITM-A2) | 0 | `item.def_collides_with_resource_kind` |
| **ITM-V11** | Strike: `strike_kind ∈ def.equip.combat.strike_kinds` | 3.5.e | `item.strike_kind_unsupported` |
| **ITM-V12** | Drop / Give: instance is not currently in an `actor_equipment` slot | 3.5.e | `item.equipped_transfer_forbidden` |
| **ITM-V13** | payload carries no engine-owned numeric field (ITM-A4 assertion) — see the failure-mechanism note below | 0 | `item.engine_owned_field_supplied` |

**ITM-V13's failure mechanism, stated explicitly (review 2026-07-26).** As first written this check was
arguably vacuous: the `Item:*` payload structs simply *have no* `charges`/`damage`/`price` field, so in
typed Rust there is nothing to populate and the check could not fail — a structural restriction dressed
up as a validator. It is non-vacuous **only at the deserialization boundary**, which is where the risk
actually lives: an `LlmDriver` `Decision` arrives as JSON through an ai-gateway MCP tool-call (AGT-A4),
and an LLM emitting `{"instance": "...", "heal_amount": 40}` is a realistic, observed failure mode. So
the check is specified where it can bite:

> Item payload deserialization uses **`serde(deny_unknown_fields)`**, and ITM-V13 is the Stage-0
> rejection of the resulting error, re-wrapped into the `item.*` namespace for failure-UX consistency
> (the same wrapping pattern EF_001 §8 uses for `entity.lifecycle_log_immutable` over a DP-layer error).
> Without `deny_unknown_fields` the extra key is silently dropped and ITM-V13 is dead code.
> **AC-ITM-11b** feeds a payload with an extra numeric key and requires a reject — it fails if the
> deserializer is permissive.

ITM-V9 uses **cell membership**, not fine position, on purpose: fine position is realtime-ephemeral
(RTM-A1 / ILR-A2 layer 2) and a durable validator must not depend on state that is not in the log.
Reach-based pickup is ITM-D11 and belongs to the realtime layer if it ever lands.

### 9.2 `item.*` rule_id namespace — 24 V1 total (21 rejects + 3 warnings)

Counted explicitly, because the total is spread over four places and a hand-wave here becomes a
mismatched registration later. *(The first draft claimed "13 V1" by counting only the validator table
and missing everything the consistency rules and PL_007b declare — caught at self-verify, then grew
again at the review pass.)*

| Source | Rejects | Warnings |
|---|:---:|:---:|
| §9.1 validator table (ITM-V1..V13) | 13 | — |
| §9.4 consistency rules — `def_invalid` (ITM-C5/C8/C11) · `unknown_holder` (ITM-C6) | 2 | — |
| §9.4 ITM-C7 — `instrument_tag_unreferenced` (a declared `instrument_match` tag no item carries, so the bonus can never fire; a warning because a silently-dead bonus is worse than an error and an author may legitimately declare tags first) | — | 1 |
| §9.4 added at review — `def_edit_blocked_by_equipped` (ITM-C9) · `untracked_actor_cannot_hold` (ITM-C10) | 2 | — |
| §6.1 added at review — `slot_profile_too_large` | 1 | — |
| [PL_007b §8](PL_007b_inventory.md) — `inventory.cap_exceeded` · `inventory.cell_cap_exceeded` · `inventory.digest_bound_violated` | 3 | — |
| PL_007b — `inventory.cap_partial` (reported on an **accepted** turn) | — | 1 |
| §7.1 added at cold-start review — `use_effect_narrative_only` (an `Unlock`/`Reveal` Use succeeded with **no durable delta**; declared rather than silent, so the audit log distinguishes "designed narrative outcome" from "silently did nothing") | — | 1 |
| **Total** | **21** | **3** |

`item.def_invalid` is deliberately **one** rule_id carrying three distinct Stage-0 causes (ITM-C5
two-handed/`also_blocks` mismatch · ITM-C8 charge-config · ITM-C11 nutrition flag). They are all
"the author wrote an incoherent def", they all surface at bootstrap with the offending `def_id`, and
splitting them would add namespace surface without adding diagnostic value — the `detail` payload
carries which coherence rule failed.

`item.inventory.*` is a sub-namespace of `item.*`, not a second namespace — one owner, one boundary
registration.

**V1+ reservations (4):** `item.durability_exhausted` (RES-D4) ·
`item.bound_to_other_actor` (ITM-D5) · `item.container_depth_exceeded` (ITM-D3) ·
`item.ammunition_missing` (ITM-D8). PL_007b adds the `item.inventory.*` sub-namespace (4 more) —
same prefix, one registration.

### 9.3 Where Lex fits

`ItemDefDecl.lex_tags` is the **input** to Stage 4, which WA_001 owns. PL_007 does not evaluate it.
This finally supplies the missing operand for PL_005b §8.2's "**Use → Lex severity: CRITICAL — item ×
reality compatibility matrix**", which was declared as the primary cross-reality reject path and had
no item side to match against.

### 9.4 Cross-aggregate consistency rules

| ID | Rule | Owner | Reject |
|---|---|---|---|
| **ITM-C1** | `ItemInstanceId` ≡ EF_001 `ItemId`. RES_001 §4.4's `EntityRef::Item(ItemInstanceId)` and EF_001 §5's `EntityId::Item(ItemId)` name the **same** UUID newtype. PL_007 declares the alias; `ItemId` is canonical. | PL_007 + EF_001 + RES_001 | (drift resolution, not a runtime reject) |
| **ITM-C2** | `item_defs.def_id` ∩ `resource_kinds.kind_id` = ∅ (ITM-A2) | PL_007 | `item.def_collides_with_resource_kind` |
| **ITM-C3** | `item_instance` row ⟺ `entity_binding` row with `EntityId::Item`, created/destroyed together | PL_007 + EF_001 | `entity.unknown_entity` / `item.unknown_def` |
| **ITM-C4** | every `actor_equipment.slots[*].instance` is `HeldBy(actor_ref)` and `Existing` | PL_007 | `item.not_held` (write-time) + cascade auto-clear (§8.4) |
| **ITM-C5** | `combat.two_handed == !also_blocks.is_empty()` | PL_007 | `item.def_invalid` (Stage 0) |
| **ITM-C6** | `initial_item_distribution[*].holder ∈ canonical_actors ∪ places` | PL_007 + ACT_001 + PF_001 | `item.unknown_holder` (Stage 0) |
| **ITM-C7** | every `InstrumentMatch::ItemTag(t)` in `progression_kinds[*].training_rules` and in `stat_slots[*].terms[*].instrument_match` resolves to a tag declared by at least one `item_defs[*].instrument_tags`. Otherwise the rule is **silently unsatisfiable** — the worst failure mode here, because the author sees a declared bonus that never fires. | PL_007 + PROG_001 + DF07 | `item.instrument_tag_unreferenced` (Stage 0 **warning**, not reject — an author may legitimately declare tags ahead of the items that carry them) |
| **ITM-C8** (added at review) | charge-config coherence: `consume_on_exhaust == true` ⇒ `max_charges == Some(n)` with `n > 0`. The two contradictory combos are otherwise silently accepted — `consume_on_exhaust` with `max_charges: None` declares an item that is destroyed on exhaustion but can never exhaust (dead flag), and `max_charges: Some(0)` mints an item born already exhausted (destroyed on its first `Use`, or immediately, depending on implementation order — an ambiguity better rejected than resolved). | PL_007 | `item.def_invalid` (Stage 0) |
| **ITM-C12** (added at cold-start review) | **Class↔capability coherence on `ItemDefDecl`.** The §5.2 "Equip?" column and the implications of `ItemClass` were **documentation with no validator** — nothing rejected `ItemClass::Document` with `equip: Some(..)`, or `ItemClass::Consumable` with `max_charges: None` (an infinitely reusable consumable), or `ItemClass::Valuable` with a `use_effect` its affordance set forbids it from ever using. Three coherence rules, all Stage 0: (a) `equip.is_some()` ⇒ `class ∈ {Weapon, Armor, Trinket}`; (b) `class == Consumable` ⇒ `max_charges.is_some()`; (c) `use_effect.is_some()` ⇒ the class default (or `affordance_overrides`) contains `BeUsed` — otherwise the effect is unreachable by construction. | PL_007 | `item.def_invalid` (Stage 0) |
| **ITM-C13** (added at cold-start review) | **Birth-materialised affordances are not retroactive.** Because §5.3 resolves the per-class/per-def affordance set **at instance birth** into `entity_binding.affordance_overrides`, a later `Forge:EditItemDef` changing `class` or `affordance_overrides` does **not** update live instances. Either outcome is defensible; the failure mode is leaving it undecided, so V1 decides: the edit **applies to instances born after it** and existing instances keep their materialised set. `Forge:EditItemDef` therefore **reports** how many live instances retain the old set (audit-visible, not a reject), and an admin wanting a full retrofit uses `Forge:DestroyItem` + `Forge:SpawnItem`. | PL_007 + WA_003 | (no reject — `forge_audit_log` entry records the retained-instance count) |
| **ITM-C9** (added at review; **scope extended at cold-start review** — it originally covered only the three `equip` fields, which left `class`, `use_effect` and `max_charges` editable under live instances: `class` silently diverges from birth-materialised affordances (ITM-C13), `use_effect` changes what an already-held item does with no player-visible cause, and lowering `max_charges` leaves instances holding `charges` above the new maximum with nothing to clamp them. All three are now in scope: the edit is rejected while live instances exist unless the admin passes an explicit `accept_instance_divergence` flag, which routes the outcome through ITM-C13's audit path.) | `Forge:EditItemDef` may not change `equip.slot` / `equip.also_blocks` / remove `equip` — **nor `class`, `use_effect`, or lower `max_charges`** — while **any** live instance of that def sits in an `actor_equipment` slot. Otherwise the edit silently leaves equipped instances in slots the def no longer names, violating ITM-V3 for already-committed state — the class of bug the track already solved once, in TVL_001's `route.remove_blocked_by_active_journey` gate. Same shape: block the admin edit, name the blocker. Admin unequips first (or uses `Forge:DestroyItem`). | PL_007 + WA_003 | `item.def_edit_blocked_by_equipped` (Stage 7 Forge admin) |
| **ITM-C10** (added at review) | **Untracked actors hold no item instances and have no `actor_equipment` row.** An AIT_001 Untracked NPC's gear is *flavour resolved from its DF07 `stat_archetypes` block*, never instanced. Items materialise only on **promotion** to Minor/Major (the existing AIT_001/AGT-D5 promotion path). Without this rule, COMB_005's default-`Untracked` hostile spawns would mint one `item_instance` + one `entity_binding` row per bandit per weapon — the entity-count explosion AIT_001 exists to prevent, arrived at through the item system's back door. Consistent with COMB_005 §7 ("*zero per-actor state*" for Untracked) and with COMB_004 generating loot from **tables**, not from a corpse's actual carried inventory. | PL_007 + AIT_001 + COMB_005 | `item.untracked_actor_cannot_hold` (Stage 0 + 3.5.e) |
| **ITM-C11** (added at review) | **`nutritional` is a `resource_kinds` property only — an `ItemDefDecl` can never be food.** RES_001 §7.2's `Scheduled:HungerTick` scans `actor.resource_inventory` for a nutritional consumable; it does **not** and should not walk held item entities. Without this rule an author declares `travel_ration` as an `ItemClass::Consumable` item def, the PC carries twenty of them, and **starves to death** while "holding food" — a silent, fully-reachable bug with a mortality consequence (RES_001 §7.2 escalates `Hungry` magnitude 7 → `MortalityTransitionTrigger`). Food must be fungible in V1. If per-instance rations are ever wanted, the hunger tick has to learn to read held instances — that is the real prerequisite, recorded as ITM-D23. | PL_007 + RES_001 | `item.def_invalid` (Stage 0; rejects an item def carrying a nutrition flag) |

---

## §10 Event-model mapping

| Event | EVT-T* | Sub-type | Producer |
|---|---|---|---|
| Pick up / drop / equip / unequip | **EVT-T1 Submitted** | `Item:PickUp` · `Item:Drop` · `Item:Equip` · `Item:Unequip` | actor (Human/Llm/Script/Engine driver per AGT-A3) |
| Instance body created | **EVT-T4 System** | `ItemInstanceBorn` | world-service (paired with EF_001 `EntityBorn`, ITM-C3) |
| Instance body delta (charges, durability) | **EVT-T3 Derived** | `aggregate_type = item_instance` | Aggregate-Owner |
| Equipment delta | **EVT-T3 Derived** | `aggregate_type = actor_equipment` | Aggregate-Owner |
| Admin item ops | **EVT-T8 AdminAction** | `Forge:SpawnItem` · `Forge:DestroyItem` · `Forge:EditItemDef` · `Forge:GrantItems` | WA_003 Forge |
| Item decay / spoilage | **EVT-T5 Generated** | `Scheduled:ItemDecay` — **V1+30d reserved** (RES-D18) | Generator |

Location changes are **EF_001's** `EVT-T3 { aggregate_type: entity_binding }` — PL_007 emits no
location events of its own (ITM-A2 / §4.1).

---

## §11 `RealityManifest` extensions

```rust
RealityManifest {
    // ── PL_007 extensions (added 2026-07-26) ──

    /// Author-declared item templates. Empty ⇒ reality has no instanced items
    /// (valid: a pure fungible-economy reality). OPTIONAL V1.
    pub item_defs: Vec<ItemDefDecl>,

    /// Equipment slot profile. None ⇒ engine default 6 slots (§6.1). OPTIONAL V1.
    pub equip_slot_profile: Option<EquipSlotProfileDecl>,

    /// Seed items at bootstrap. Holder may be an actor or a cell. OPTIONAL V1.
    pub initial_item_distribution: Vec<ItemDistributionDecl>,
}

pub struct ItemDistributionDecl {
    pub holder: EntityRef,              // Actor(_) or Cell(_) V1; Item(_) V1+30d containers
    pub def_id: ItemDefId,
    pub count: u32,                     // n distinct instances (ITM-A2: no stacking)
    pub equip_on_seed: bool,            // convenience: equip immediately if def.equip.is_some()
}
```

Plus `inventory_defaults` — declared by [PL_007b §4](PL_007b_inventory.md) so capacity and digest
tuning live with the inventory design.

---

## §12 Cross-feature integration & closure-pass-extensions

Declared per the track's behavioural-closure pattern: the load-bearing ones apply as dated notes in
this cycle; the rest apply when each target feature is next opened.

| # | Target | Change | Load-bearing |
|---|---|---|---|
| **12.1** | **EF_001** | `ItemInstanceId` alias (ITM-C1) · **EF-D3 RESOLVED as a decision** (V1 flat, `InContainer` reserved → ITM-D3) · `EntityKind for ItemInstance` registered in the §4 matrix · §6.1 destroy-cascade gains its `actor_equipment` clearing hook (§8.4) | **yes** |
| **12.2** | **RES_001** | **RES-D1 RESOLVED by withdrawal:** `ResourceKind::Item(ItemKind)` is **withdrawn, never activated** — the item representation is EF_001 entity + PL_007 body (ITM-A2). `ResourceBalance.instance_id` becomes permanently unused (retained, never reused, per I15). `EntityRef::Item(_)` as an inventory *owner* remains valid and is ITM-D3's container case. RES-D4 (wear) + RES-D2 (weight cap) now have a schema home (§4.1 `durability`, §5.1 `weight`). | **yes** |
| **12.3** | **PL_005 / PL_005b** | Use/Give/Strike `tool_not_held` placeholders resolve to ITM-V2 at 3.5.e · `ExamineTarget::Item(GlossaryEntityId)` → `EntityId` · `InteractionUsePayload.effect_magnitude` ignored for item effects V1 (§7.1) · `StrikeIntent::Disarm` now has a target model (still V1+) · closed-set proof **unchanged** (ITM-A7) | **yes** |
| **12.4** | **COMB_001 / COMB_002** | `UseItem` binds `item_instance` + charges (ITM-V7/V8) · weapon `reach` feeds COMB_002 §5 range · equipment modifiers reach the §4 law-chain **through DF07 resolution**, never directly (ITM-A3) | yes |
| **12.5** | **DF07_001 Actor Stat Block** (landed 2026-07-26, parallel) | **PL_007 ships the `EquipmentStats` impl DF7-D1 deferred to it** (§6.3) — DF07 needs **no change** to accept it, exactly as DF7-Q7 predicted ("contract now, body later"). Two additive items DF07 should absorb at its next opening: (a) `StatTerm.instrument_match` gains the `ItemTag`/`ItemDef` variants so its own §6.1 `Some(Blade)` example is expressible (§6.4 / ITM-C7); (b) DF7-D3's V1+ `CarryCapacity` slot is the stat-side of PL_007b §4's slot accounting — when it activates, `inventory_cap.max_slots` becomes a resolved stat rather than a manifest constant. | **yes** |
| **12.6** | **PROG_001** | `EquipRequirement::ProgressionLevel` reads `actor_progression`. **`InstrumentMatch` gains `ItemDef(ItemDefId)` + `ItemTag(InstrumentTag)`** (additive per I14) — this **resolves PROG-D15** (*"`InstrumentClass` match — V1+30d"*), which was deferred for want of a class taxonomy that now exists. Note the latent break this repairs: `InstrumentMatch::Specific(ResourceKind)` cannot name a wielded item once ITM-A2/§12.2 withdraws `ResourceKind::Item`, so every "+skill while wielding X" training rule would have been silently unsatisfiable. `Specific(ResourceKind)` is retained for genuinely fungible tools. | **yes** |
| **12.7** | **WA_001 Lex** | `lex_tags` is the Stage-4 operand PL_005b §8.2 declared and lacked (§9.3) | yes |
| **12.8** | **CSC_001** | ground items place through the existing Layer-3 assignment; `csc.item_on_non_placeable` already exists and now has real subjects | no |
| **12.9** | **PF_001** | place `→ Destroyed` cascade over at-cell items now has a body to cascade onto (PF_001 §6.1 named "future Item" as the consumer) | no |
| **12.10** | **WA_003 Forge** | 4 new `EVT-T8` sub-shapes (§10); `Forge:EditItemDef` is the **only** def-write path (ITM-A1) | no |
| **12.11** | **07_event_model** | register 4 EVT-T1 + 1 EVT-T4 + 2 EVT-T3 `aggregate_type`s + 4 EVT-T8 + 1 V1+30d EVT-T5 | yes |
| **12.12** | **AIT_001 / NPC_002 / COMB_005** | NPC equipment + inventory enter AssemblePrompt **only** as the bounded digest (PL_007b §5) — token cost flat in inventory size. **Added at review:** **ITM-C10** — Untracked actors hold **no** item instances and have **no** `actor_equipment` row; gear is DF07-archetype flavour, materialised only on AIT promotion. This is the rule that keeps COMB_005's default-`Untracked` hostile spawns from minting an entity per bandit per weapon (AC-ITM-19 counts the rows). | **yes** |
| **12.13** | **ABL_001 Ability Foundation** (landed 2026-07-26, parallel) — **answering the two questions ABL_001 explicitly routed to the PL_007 owner** | **(a) ABL-Q9 — `UseEffectDecl` ⊂ `EffectOp`: my answer was WRONG and is SUPERSEDED. Merge now.** ⚠️ **Corrected 2026-07-26 after commit `44645784a`.** I answered *"agreed in principle, deferred in execution — do not merge inside V1"*, on a change-coupling argument: a closed enum shared by two DRAFT features becomes a coupling seam, and ABL's `Damage`/`ModifyThreat`/`ForceMove` are meaningless for items. The combat-family session then resolved it the other way and was **right to**, because it found a **defect** where I had weighed a *preference* — and a defect beats tidiness every time. Two findings, both from reading the two enums side by side: (i) **they had already diverged in one day** — `StatusApply` here is `{ flag, magnitude }`, ABL's is `{ flag, magnitude, duration_rounds }`; `VitalDelta` here names its field `kind`, ABL's names it `vital`. Neither was wrong alone, which is precisely how two closed enums over one concept drift. (ii) **`VitalDelta { amount: i32 }` was a damage-law-chain bypass — in my doc.** The field is *signed*, so `UseItem { poison_vial, target } → VitalDelta { Hp, −30 }` writes damage that skips COMB_001 §4's chain entirely: **ignores `Armor`**, elem and resist, takes **no hit roll**, accrues **no COMB_003 threat** (accrual reads `damage_applied` *from* the chain), ignores **COMB_001 Q4's disparity cap**, and ignores **COMB_006's PvP eligibility predicate** (which guards `Strike` and `Damage`, not a raw vital write). Net effect: **an unmissable, armour-ignoring PvP weapon usable inside a sanctuary**, silently falsifying COMB_001's "the 4-step chain is the sole damage authority". **Neither of my two review passes caught this** — the cold-start pass read §7.1 closely enough to find `Unlock`/`Reveal` decorative and still missed that a signed amount is a weapon. Resolution as landed: `pub type UseEffectDecl = EffectOp;` — `ItemDef.use_effect` keeps its shape, only the type it names moves; **ABL_001 owns the vocabulary** (ABL-Q10, on the DF07 precedent — DF07 owns `StatModifier` while its producers live in PL_007/PL_006/Lex/Forge, so ownership sitting with the definer and producers living outside is the established shape here). Harm must be expressed as `Damage`, so every point of damage in the game passes the chain. The §7.1 variant table in `PL_007` §7 now documents the retirement in place. **My change-coupling concern was real but secondary**, and the right answer to it is ABL's subset constraint, not a second enum. **(b) `EquipDecl.grants_ability`: AGREED, V1+ (ITM-D21).** ABL_001's derived-set model (§4.3 — the ability leaves the set when the item is unequipped, nothing stored, nothing to clean up) composes exactly with §6.5's equipped-only rule, so the field is cheap and correct when wanted. It stays out of V1 because ITM-A3's "items carry stat modifiers" is the whole of the V1 equipment contract, and ability-granting gear needs the ABL cost/cooldown model to be settled first. **(c) ITM-Q5 range arbitration** (§16) — ABL owns `Skill` and therefore the `reach`-vs-`range` precedence; PL_007 supplies `reach` as data and encodes no precedence. | **yes — answers ABL-Q9** |

---

### 12.14 `UseEffectDecl` retires into `EffectOp` (ABL-Q9) — relocated verbatim from PL_007 §7.1

Authored by the combat-family session in commit `44645784a` as a dated note in `PL_007_item.md` §7.1, and
**moved here unchanged** because §12 is where this track keeps closure-pass extensions — and because
PL_007 was 23 lines over the 800-line hard cap. `PL_007` §7.1 carries a pointer back to this section.
This supersedes the answer in **§12.13(a)**, which was mine and was wrong; see that row for why.

**⚠ CLOSURE-PASS-EXTENSION 2026-07-26 (combat family / ABL-Q9) — `UseEffectDecl` retires into
`EffectOp`, and the reason is a defect, not tidiness.**

```rust
pub type UseEffectDecl = EffectOp;   // ABL_001 §4.1 owns the vocabulary (ABL-Q9/Q10)
```

`ItemDef.use_effect: Option<UseEffectDecl>` is **unchanged in shape** — only the type it names moves.
Two findings forced this, both caught by reading the two enums side by side one day after both were
written:

1. **They had already diverged.** `StatusApply` here takes `{ flag, magnitude }`; ABL's takes
   `{ flag, magnitude, duration_rounds }` (combat has rounds). `VitalDelta` here names its field `kind`,
   ABL's names it `vital`. Neither doc was wrong alone — which is exactly how two closed enums over one
   concept drift.
2. **`VitalDelta { amount: i32 }` was a damage-law-chain bypass, in both docs.** The field is *signed*,
   so `UseItem { poison_vial, target } → VitalDelta { Hp, −30 }` writes damage that skips COMB_001 §4's
   chain (**ignores `Armor`**, elem, resist, variance), takes **no hit roll**, accrues **no COMB_003
   threat** (accrual reads `damage_applied` *from* the chain), ignores **COMB_001 Q4's disparity cap**,
   and ignores **COMB_006's PvP eligibility predicate** — which guards `Strike` and `Damage`, not a raw
   vital write. Net: **an unmissable, armour-ignoring PvP weapon usable inside a sanctuary**, silently
   falsifying COMB_001's *"the 4-step chain is the sole damage authority"*.

**Fix:** `VitalDelta` → **`VitalRestore { vital, amount: u32 }`** — harm becomes **unrepresentable by
type**, and every path that reduces another actor's vitals is `Damage { power: PowerTerm }`, which
passes the chain, the hit roll, the disparity cap and the PvP predicate. `ABL-V9` asserts it. This is
the same *unrepresentable-not-merely-invalid* discipline as **ITM-A7** (equipment is a slot assignment)
and THR-Q7.

**What PL_007 gains, not loses:** `Unlock` moves into `EffectOp` as its 11th variant (nothing lost), and
items become able to declare `Damage` — so an **explosive talisman (符)** is finally expressible, which
the 7-variant enum could not do except via the bypass above. **ITM-A4 is strengthened:** the item still
emits no number; a damaging talisman declares a `PowerTerm` (a multiplier on a stat slot) and the engine
computes the damage. **PL_007's narrative-only `Unlock`/`Reveal` treatment below is preserved verbatim**
and has been adopted by ABL for the same reason.

Registered in [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md)
§1.4a and the ownership matrix. Applied here as a dated note per the track's behavioural-closure
pattern; the schema edit lands when this doc is next opened.

---

## §13 Sequences

### 13.1 Equip a two-handed weapon over a sword-and-shield loadout

```
PC submits EVT-T1 Item:Equip { instance: itm_greatsword }
  Stage 0     schema: no engine-owned numerics (ITM-V13) ✓
  Stage 3.5.a EF_001: itm_greatsword exists, Existing ✓
  Stage 3.5.e ITM-V1 def known ✓ · V6 equippable ✓ · V2 HeldBy(pc) ✓
              V3 slots {main_hand, off_hand} ⊆ profile ✓ · V5 ProgressionLevel(sword, 3) ✓
  Stage 4     lex: greatsword lex_tags ⊆ reality axioms ✓
  commit (one transaction):
    unequip itm_saber (main_hand) + itm_shield (off_hand)   ← implicit, §8.3 step 4
    write slots: {main_hand → greatsword}, {off_hand → greatsword, blocked_by_primary: true}
    emit EVT-T3 { aggregate_type: actor_equipment }
  post-commit: equipment_version bumps → DF07 StatEpoch invalidates the cached block (§6.3);
               saber + shield remain HeldBy(pc), contributing nothing (§6.5)
```

### 13.2 Drink the last dose of an elixir

```
PC submits Interaction:Use { tools: [Item(itm_elixir)], direct_targets: [Actor(pc)] }
  3.5.a affordance BeUsed present (Consumable class default) ✓
  3.5.e V2 held ✓ · V8 use_effect Some ✓ · V7 charges = 1 > 0 ✓
  Stage 4 lex: CRITICAL gate — elixir lex_tags vs reality (§9.3) ✓
  Stage 7 world-rule: def.use_effect = VitalDelta { Hp, +30 } → ActualOutputs
  commit:
    RES_001 vital_pool: hp += 30 (clamped to max)
    item_instance: charges 1 → 0
    consume_on_exhaust = true → EF_001 Existing → Destroyed, reason InteractionDestructive,
      causal_ref = this Use event                                      ← §8.4
    entity_lifecycle_log append
```

### 13.3 Give an equipped item (the reject that keeps ITM-C4 true)

```
PC submits Interaction:Give { tools: [Item(itm_saber)], direct_targets: [Npc(lao_ngu)] }
  itm_saber is in actor_equipment{main_hand}
  3.5.e ITM-V12 → REJECT item.equipped_transfer_forbidden
  user_message: "Bạn đang mang [thanh đao] trên người — hãy tháo ra trước."
                (I18nBundle default: "You have [saber] equipped — unequip it first.")
```

### 13.4 Holder dies — the cascade with both ends attached

```
PC Lý Minh reaches hp = 0 → PCS_001 mortality → EF_001 Existing → Destroyed (PcMortalityKill)
EF_001 §6.1 cascade, ONE atomic batch:
  for each entity HeldBy(ly_minh):
    location HeldBy(ly_minh) → InCell(last_cell)      lifecycle stays Existing
  PL_007 cascade hook (§8.4 / §12.1):
    clear every actor_equipment slot for ly_minh       ← without this, ITM-C4 breaks
  emit EVT-T3 { entity_binding } ×N + EVT-T3 { actor_equipment }
Result: items lie in the cell as ordinary Existing entities — the loot module's substrate (§8.5)
```

### 13.5 Canonical seed rejects a colliding def (ITM-A2 has teeth)

```
Author declares:  resource_kinds:  [ Consumable("rice"), Material("iron") ]
                  item_defs:       [ ItemDefDecl { def_id: "iron", class: Valuable, .. } ]
RealityBootstrapper Stage 0:
  ITM-V10 / ITM-C2 → REJECT item.def_collides_with_resource_kind { def_id: "iron" }
  "iron" would exist both as a fungible balance and as instanced entities — the exact
  two-representations drift ITM-A2 forbids. Author picks one.
```

---

## §14 Acceptance criteria

13 V1-testable scenarios. Each names the §-rule and the rule_id it exercises.

1. **AC-ITM-1 — def/instance split is enforced.** A submitted event attempting to write any
   `ItemDefDecl` field outside `Forge:EditItemDef` is rejected; `Forge:EditItemDef` succeeds and
   appends a `forge_audit_log` entry. *(§3 ITM-A1)*
2. **AC-ITM-2 — representation rule bites.** §13.5 verbatim: a `def_id` equal to any
   `resource_kinds.kind_id` rejects canonical seed bootstrap with
   `item.def_collides_with_resource_kind`. Removing either declaration makes bootstrap succeed.
   *(ITM-A2 / ITM-V10 / ITM-C2)*
3. **AC-ITM-3 — instance ⟺ binding atomicity.** Killing the transaction between the
   `ItemInstanceBorn` write and the `EntityBorn` write leaves **neither** row. A hand-inserted
   orphan `item_instance` is reported by the ITM-C3 consistency check. *(§4.1 / ITM-C3)*
4. **AC-ITM-4 — affordance does the rejecting, not PL_007.** `Use` on an `Armor`-class item rejects
   with EF_001 `entity.affordance_missing { required_flag: BeUsed }` at Stage 3.5.a — **before**
   Stage 3.5.e runs at all (assert the item validator was not entered). *(§5.3)*
5. **AC-ITM-5 — two-handed implicit unequip.** §13.1 verbatim: post-commit `actor_equipment` has
   exactly 2 rows both pointing at the greatsword (one `blocked_by_primary`), and the displaced saber
   + shield are still `HeldBy(pc)` — **not** `InCell`. *(§8.3)*
6. **AC-ITM-6 — modifiers apply only while equipped, and multi-slot items count once.**
   (a) `resolve_stat_block(actor)[StrikePower]` changes on `Item:Equip`, reverts on `Item:Unequip`,
   and is **unchanged** by picking the same weapon up or dropping it.
   (b) Equipping a **two-handed** weapon (`main_hand` + a `blocked_by_primary` `off_hand` row) applies
   its modifiers **exactly once** — dropping the `blocked_by_primary` filter from
   `equipped_modifiers` makes this fail with double the bonus. *(§6.3 / §6.5 — the seam bug that is
   invisible from either doc alone)*
7. **AC-ITM-7 — charge exhaustion destroys in the same commit.** §13.2 verbatim: one commit contains
   the vital delta, `charges 1 → 0`, the `Existing → Destroyed` transition, and one
   `entity_lifecycle_log` entry whose `causal_ref` is the `Use` event. *(§8.4 / ITM-V7)*
8. **AC-ITM-8 — equipped items cannot be transferred or dropped.** §13.3 verbatim for Give; the same
   reject for `Item:Drop`. After `Item:Unequip`, both succeed. *(ITM-V12 / ITM-C4)*
9. **AC-ITM-9 — holder-death cascade clears equipment.** §13.4 verbatim: after the cascade,
   `actor_equipment` for the dead actor has **zero** rows, every former possession is
   `InCell(death_cell)` with `lifecycle_state = Existing`, and all of it lands in one atomic batch.
   *(§8.4 / §12.1)*
10. **AC-ITM-10 — weapon gates StrikeKind.** `Strike { tool: club, strike_kind: Slash }` rejects
    `item.strike_kind_unsupported`; `strike_kind: Punch` on the same club (not in `strike_kinds`)
    also rejects; a declared kind passes. *(§6.2 / ITM-V11)*
11. **AC-ITM-11 — LLM-zero-item-math.** (a) An `LlmDriver` `Decision` carrying `Use` with an
    instance **not** in the actor's held set rejects (out-of-vocabulary per AGT-A2) and falls back to
    `Defend` in combat context. (b) **AC-ITM-11b (bite test):** a raw JSON payload
    `{"instance": "<valid>", "heal_amount": 40}` arriving over the ai-gateway MCP boundary rejects
    `item.engine_owned_field_supplied`; **the test must fail if the deserializer is configured
    permissively** (without `serde(deny_unknown_fields)` the extra key is silently dropped and ITM-V13
    is dead code). *(ITM-A4 / ITM-V13 + its failure-mechanism note in §9.1)*
12. **AC-ITM-12 — pickup uses cell membership, not fine position.** `Item:PickUp` succeeds for any
    item `InCell(agent's cell)` regardless of realtime-layer distance, and rejects
    `item.not_in_cell` for an item in an adjacent cell. *(ITM-V9 — asserts no dependency on
    ephemeral RTM state)*
13. **AC-ITM-13 — conditional instrument bonuses fire, and only when wielding.** Reproduce DF07 §6.1's
    worked example against a real item: an actor with `physical_strength 15` + `swordsmanship 8` and a
    `def` carrying `instrument_tags: ["blade"]` equipped in `main_hand` resolves
    `StrikePower = 24`; the **same actor bare-handed resolves 20**; the same actor holding the blade
    **unequipped** also resolves 20. Then assert ITM-C7: a `StatTerm.instrument_match` naming a tag
    no `item_def` carries emits `item.instrument_tag_unreferenced` at bootstrap. *(§6.4 / ITM-C7 —
    the DF07↔PROG_001↔PL_007 three-way seam)*

### 14.1 Added at review 2026-07-26 (each bites a defect this pass found)

14. **AC-ITM-14 — destroying an equipped item clears its slot.** A wand equipped in `main_hand` spends
    its last charge: in **one** commit, `charges 1→0`, `Existing → Destroyed`, **and** the
    `actor_equipment` row is gone. Then assert the consequence that motivates the rule:
    `resolve_stat_block` no longer includes the wand's modifiers. For a **two-handed** item, both the
    primary and the `blocked_by_primary` rows clear together. *(§8.4 item-side clearing)*
15. **AC-ITM-15 — a suspended holder keeps its gear (ITM-C4 lockstep).** An NPC with an equipped sword
    cold-decays (`Existing → Suspended`, `NpcCold`): the sword goes `Suspended` **with** it (EF_001
    §6.1 cascade), the `actor_equipment` row is **retained**, and on `Suspended → Existing` the NPC is
    still armed. **This test fails against the original ITM-C4 wording** (`lifecycle_state == Existing`),
    which is why the rule was corrected. *(§4.2 ITM-C4)*
16. **AC-ITM-16 — dropping onto a non-placeable tile rejects (delegation bite test).** `Item:Drop` in a
    cell whose target tile is non-placeable rejects `csc.item_on_non_placeable`. **The test fails if
    CSC_001's 3.5.d applicability predicate has not been extended to `Item:Drop`** — i.e. it fails
    against the doc as first written, where the delegation was vacuous. *(§9.1 delegation defect)*
17. **AC-ITM-17 — over-encumbered unequip is never blocked.** With `default_cap = Some { max_slots: 5 }`
    and an actor at 5/5 whose 6th item is equipped: `Item:Unequip` **succeeds** and leaves
    `slots_used = 6 > 5`; a subsequent `Item:PickUp` rejects `item.inventory.cap_exceeded`; equipping
    something again brings it back to 5 and pickup succeeds. Asserts the soft-lock is unreachable.
    *(§8.3 capacity note / PL_007b §4.2)*
18. **AC-ITM-18 — item actions reject during active combat.** With the actor in a `combat_session`
    `Active`: each of `Item:PickUp` / `Drop` / `Equip` / `Unequip` rejects
    `combat.action_invalid_in_state`, while `UseItem` succeeds. After `CombatSessionResolved`, all four
    succeed. *(§8.6)*
19. **AC-ITM-19 — Untracked actors hold nothing (ITM-C10 scaling invariant).** A COMB_005 hostile spawn
    group of 12 default-`Untracked` bandits creates **zero** `item_instance` rows and **zero**
    `actor_equipment` rows; their weapons are archetype flavour. Promoting one to Minor materialises its
    gear. **Count the rows** — the test fails if items are instanced eagerly. *(ITM-C10)*
20. **AC-ITM-20 — an item def can never be food.** An `ItemDefDecl` carrying a nutrition flag rejects
    `item.def_invalid` at bootstrap. Then the behavioural half: an actor holding only instanced
    `Consumable` items and zero nutritional `resource_kinds` **does** accrue `Hungry` on the
    `Scheduled:HungerTick` — confirming the starvation-while-holding-rations bug is prevented by the
    schema rule rather than papered over by the tick. *(ITM-C11)*
21. **AC-ITM-21 — contradictory charge configs reject.** `consume_on_exhaust: true` with
    `max_charges: None`, and `max_charges: Some(0)`, both reject `item.def_invalid` at bootstrap.
    *(ITM-C8)*
22. **AC-ITM-22 — a def edit cannot orphan equipped instances.** `Forge:EditItemDef` changing
    `equip.slot` while one instance is equipped rejects `item.def_edit_blocked_by_equipped`; after that
    instance is unequipped, the same edit succeeds. *(ITM-C9)*
23. **AC-ITM-23 — pickup cannot steal.** `Item:PickUp` targeting an item `HeldBy` another actor rejects
    `item.not_in_cell` (it is not `InCell`). Taking from a living owner is Strike-cascade theft
    (RES_001 §8.1), never a pickup. *(ITM-V9)*


### 14.2 Added at the cold-start `/review-impl` pass 2026-07-26

24. **AC-ITM-24 — suspension cascades, and the slot survives it.** An NPC with an equipped sword
    cold-decays: the sword's `lifecycle_state` becomes `Suspended` **in lockstep** (EF_001 §6.1), the
    `actor_equipment` row is retained, and restore re-arms it. Then the other half, which the flat
    "items never go Suspended" claim would have forbidden: assert **no independent** item suspension —
    an item at a distant cell with an `Existing` holder stays `Existing`. *(§8.1 — the two rows the
    transition table was missing; this AC is what makes the ITM-C4 / §8.1 contradiction unable to
    recur)*
25. **AC-ITM-25 — the equip gate reads PROG_001's real field.** An `EquipRequirement::MinProgression
    { kind_id: "swordsmanship", min_raw_value: 40 }` gates on `actor_progression.values[kind].raw_value`
    and rejects `item.equip_requirement_unmet` below it. **The test fails to compile/resolve against any
    `min_level` field** — PROG_001 has none and forbids the concept. *(§6.2)*
26. **AC-ITM-26 — the two `instrument_match` consumers resolve differently, on purpose.** With a
    lockpick (`ItemClass::Tool`, never equippable) used as `tools[0]` in an `Interaction:Use`:
    (a) a PROG_001 training rule `instrument_match: ItemTag("lockpick")` **fires**, because PROG_001
    matches the *turn's* instrument; (b) a DF07 `StatTerm` with the same `instrument_match` does **not**
    contribute, because DF07 matches the *equipped* item and a Tool can never be equipped. Under the
    pre-review single rule ("main_hand-equipped"), (a) was permanently unsatisfiable — an entire
    category of training rule silently dead. *(§6.4)*
27. **AC-ITM-27 — affordances are materialised at birth, and the read path stays a single read.**
    Spawning an `ItemClass::Armor` instance writes an `entity_binding.affordance_overrides` **without**
    `BeUsed`; `Use` on it rejects `entity.affordance_missing` at Stage 3.5.a. Assert the mechanism, not
    just the outcome: the validator performs **no `item_defs` manifest lookup** while validating.
    *(§5.3 — the original `self.def_id.class()` was unimplementable)*
28. **AC-ITM-28 — narrative-only effects are declared, not silent.** `Use` of a `Key` with
    `UseEffectDecl::Unlock` returns an **accepted** turn carrying `item.use_effect_narrative_only`, and
    **zero** durable deltas across `vital_pool` / `actor_status` / `resource_inventory` /
    `entity_binding`. Same for `Reveal`. Asserting the warning is what distinguishes "designed
    narrative outcome" from "silently did nothing". *(§7.1)*
29. **AC-ITM-29 — incoherent defs reject (ITM-C12).** Each of these rejects `item.def_invalid` at
    bootstrap: `ItemClass::Document` with `equip: Some(..)`; `ItemClass::Consumable` with
    `max_charges: None`; `ItemClass::Valuable` with `use_effect: Some(..)` (unreachable — its class
    default lacks `BeUsed`). *(ITM-C12 — all three passed every validator before this pass)*
30. **AC-ITM-30 — a def edit under live instances is reported, not silent (ITM-C13).**
    `Forge:EditItemDef` changing `class` with 5 live instances rejects without
    `accept_instance_divergence`; with the flag it succeeds, the 5 instances keep their birth-materialised
    affordances, and the `forge_audit_log` entry records the retained-instance count. *(ITM-C9 extended
    / ITM-C13)*
31. **AC-ITM-31 — the digest prefers usable items over spent husks.** An actor holding a spent wand
    (`charges: Some(0)`, `consume_on_exhaust: false`) and a sword (`charges: None`,
    `use_effect: Some(..)`) with `digest_top_n = 1`: the **sword** appears in `notable`. Under
    `has_charges = is_some()` the husk won. *(PL_007b §5.1)*

---

## §15 Deferrals

| ID | What | Why deferred | Target |
|---|---|---|---|
| **ITM-D1** | Item stacking for identical instances (n×`iron_dagger` as one row) | ITM-A2 says the author picks a fungible resource kind instead; revisit only if a real reality needs *both* identity and stacking | V1+30d if ITM-Q3 bites |
| **ITM-D2** | Per-race equip slot profiles | needs IDF_001 `RaceDecl` seam; `profile_id` already exists so activation is a reference | V1+30d |
| **ITM-D3** | `InContainer` enforcement + `ItemClass::Container` (**resolves EF-D3**) | V1 flat inventory (ITM-A6); needs `BeContainedIn` affordance (EF-D2) + depth limit + cycle validator | V1+30d |
| **ITM-D4** | Runtime EnvObject state ⇒ real `Unlock` (§7.3) | blocked on the **EnvObject body**, which EF_001 assigns to a separate future feature — not on PL_007 | when EnvObject is designed |
| **ITM-D5** | Soulbound items (`bound_to`) | schema reserved §4.1 | V1+ |
| **ITM-D6** | Player-named items (`custom_name`) | needs A6 moderation on player-authored strings | V1+30d |
| **ITM-D7** | Full chain-of-custody provenance + Examine surfacing of it | V1 ships 3 fields (§4.3); a transfer ledger is an event-log query, not a field | V2 |
| **ITM-D8** | Ammunition / consumed-per-shot | needs ranged-weapon depth beyond COMB_002 reach | V1+ |
| **ITM-D9** | Multi-effect items (`Vec<UseEffectDecl>`) | keeps Lex evaluation + severity single-valued V1 (§7.1) | V1+30d |
| **ITM-D10** | Item cold-loading (`Existing → Suspended`) | EF_001 §6 already scopes Suspended to NPCs V1 | V1+ if instance counts hurt |
| **ITM-D11** | Reach-based pickup (fine position) | would make a durable validator depend on RTM-ephemeral state (§9.1) | realtime-layer decision, not PL_007 |
| **ITM-D12** | Item quality/grade tiers | RES-D16; needs crafting | V2 (`14_crafting`) |
| **ITM-D19** | `instrument_match` against the `off_hand` slot (dual-wield, shield-bash) | V1 resolves `main_hand` only (§6.4) — dual-wield needs a combat-side decision on which hand a Strike uses, which COMB owns | V1+ with COMB dual-wield |
| **ITM-D20** *(added at review)* | **Priced sale of an instanced item.** `ItemDefDecl.price` is declared but **not enforced** for instanced items in V1 — RES_001 §8.5's `InteractionTradePayload` carries `Vec<ResourceBalance>` on both sides, so RES-V3's pricing validator cannot see an item instance at all (ITM-D13). The V1 workaround, Give-reciprocal (RES-Q3), is **consensual but unpriced**: nothing checks that the coins match the sword's declared value. So V1 `price` is used only for digest ranking (PL_007b §5.1) and V1+ vendor flows. Named rather than left implicit, because "there is a price field" invites the assumption that trade honours it. NPC willingness is opinion-gated (PL_005b §4.7), not value-gated — an NPC will not be swindled *arbitrarily*, but it is not arithmetic that stops it. | V1+30d with ITM-D13 (RES_001 + PL_005 closure) |
| **ITM-D21** *(added at review)* | `EquipDecl.grants_ability` — worn gear granting an ABL_001 ability | ABL_001 §4.3 proposes it and correctly declines to add it unilaterally; §12.13 records PL_007's answer (agreed in principle, V1+). V1 gear contributes stats only. | V1+ with ABL_001 |
| **ITM-D22** *(added at review)* | Mid-combat weapon/armour swapping | §8.6 forbids item-management during `CombatActive` in V1. Enabling it is an **action-economy** decision (free? costs the action? provokes?) owned by COMB_001/TG-A3, not by PL_007 — shipping it unowned would let each AGT driver invent its own answer. | whichever COMB cycle takes up swap cost |
| **ITM-D23** *(added at review)* | Instanced food — a per-instance ration the hunger tick can consume | ITM-C11 forbids nutritional item defs in V1 to prevent starve-while-holding-rations. The real prerequisite is RES_001 §7.2's `Scheduled:HungerTick` learning to read **held instances**, not a flag on the item def. | V1+30d, RES_001-owned |

---

## §16 Open questions — all RESOLVED at the review pass 2026-07-26

Every ITM-Q is closed below. Three resolve to a **decision** (Q2, Q3, Q6), three to a **deferral with a
named trigger** (Q1, Q4, Q5), and two to a **measurement with a defined method** (Q7, Q8) — none is left
as "we'll see", because an open question with no owner and no trigger is how EF-D3 sat unresolved for
three months.

| ID | Question | **Resolution** |
|---|---|---|
| **ITM-Q1** | Is `equipment_version = last_modified_at_turn` a sufficient `StatEpoch` input? It is **not** monotonic across two equipment changes in one turn. | **DEFERRED with a trigger, and the trigger is now watched.** Safe in V1 because one action per turn is structural (COMB_001 §3 / TG-A3), and out of combat a turn carries one submitted event. **Trigger:** the first design that admits two equipment writes in one turn — most likely a COMB action-economy change (ITM-D22 mid-combat swap) or a batched client action. Fix is a `version: u64` counter on `actor_equipment`, one field, no migration concern (a fresh field defaults 0). DF07 tracks the same residual as **DF7-D13**, so both sides see it. |
| **ITM-Q2** | Is `Item:*` as 4 EVT-T1 sub-types right, vs. folding them into PL_005 as `InteractionKind`s? | **DECIDED: 4 sub-types (ITM-A7), and this is now settled rather than provisional.** Three independent reasons, only the first of which was in the original note: (a) PL_005's closed set carries a stated closed-set *proof* — reopening it invalidates the proof, not just the enum; (b) all four would be degenerate 4-role payloads (no `direct_targets`, no bystanders, no narration, no Lex severity of their own); (c) **§8.6 makes them state-gated in a way the five kinds are not** — item-management is forbidden during `CombatActive` while every InteractionKind stays legal, so they answer to a different validator than the five do. That third reason only became visible when §8.6 was written, and it is decisive. Not reopened by client input-mapping preferences — the client may present one button; the event taxonomy is not a UI concern. |
| **ITM-Q3** | Does an Identity-only model blow up on merchant stock (50 identical daggers = 50 entity rows)? | **DECIDED — the blow-up case is now structurally excluded, so this is no longer an open risk.** The feared shape was "many actors × many identical items"; **ITM-C10** removes its dominant source by forbidding item instances on Untracked actors entirely (a COMB_005 12-bandit spawn now mints 0 rows, not 24). What remains is *authored* stock on a Tracked merchant, which is bounded by hand and where the author has an explicit, documented alternative: declare the good as a fungible `Valuable`/`Material` kind (PL_007b §2's authoring guidance). ITM-D1 (stacking) stays available but is now **unlikely to be needed** — recorded so a future reader knows it was reasoned about, not forgotten. |
| **ITM-Q4** | Should `equip_on_seed` also seed NPC loadouts, or should ACT_001 `CanonicalActorDecl` own an equipment block? | **DEFERRED to ACT_001's next closure pass — ergonomics, not capability**, and PL_007 needs no change either way. One thing added at review: whichever side owns it, **seed-time `EquipRequirement`s are validated at Stage 0** and a canonical actor seeded with gear it cannot wield rejects the manifest (`item.equip_requirement_unmet`). A canonical seed must be internally consistent; silently skipping the equip would ship an author a disarmed NPC with no diagnostic. |
| **ITM-Q5** | Who owns "a weapon's `reach` vs a skill's `range`" when both are present (`Skill` with a weapon equipped)? | **DEFERRED to COMB, with the boundary stated so the deferral is safe:** PL_007 supplies `reach` as *data*; COMB owns range **arbitration**. Now sharper than at draft time, because [ABL_001](../19_ability/ABL_001_ability_foundation.md) has landed and owns `Skill`: the arbitration lives in the ABL/COMB range check, and PL_007 must not encode a precedence rule. Recorded as an ABL/COMB closure item in §12.13, not as PL_007 work. |

---

## §17 Cross-references

- Entity contract + the deferral this closes — [`EF_001`](../00_entity/EF_001_entity_foundation.md) §1 Gap 1, §3.1, §4, §6.1, §Defers-to, EF-D3
- Inventory half — [`PL_007b_inventory.md`](PL_007b_inventory.md)
- Resource ontology + the withdrawn variant — [`RES_001`](../00_resource/RES_001_resource_foundation.md) §3.1, §4.2, §8.2, RES-D1/D2/D4
- Interaction contracts whose placeholders this fills — [`PL_005b`](PL_005b_interaction_contracts.md) §3.7, §4.7, §6.7, §7, §8.2
- Combat consumers — [`COMB_001`](../18_combat/COMB_001_combat_foundation.md) §3, §4 · [`COMB_002`](../18_combat/COMB_002_tactical_grid.md) §5
- Stat seam (parallel) — [`DF07_pc_stats/_index.md`](../DF/DF07_pc_stats/_index.md)
- Audit finding — [`12_module_coverage_audit.md`](../../12_module_coverage_audit.md) AUD-F5 (and AUD-F9's seam, §8.5)
- Agent contract — [`11_agent_decision_standard.md`](../../11_agent_decision_standard.md) AGT-A2/A3/A6
- Validator group — [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) Stage 3.5
- Status / progression / lex — [`PL_006`](PL_006_status_effects.md) · [`PROG_001`](../00_progression/PROG_001_progression_foundation.md) · [`WA_001`](../02_world_authoring/WA_001_lex.md)

---

## §18 Readiness checklist

- [x] 7 axioms (ITM-A1..A7), each with a stated failure mode it prevents
- [x] 2 aggregates (`item_instance` primary + `actor_equipment` sparse); location deliberately NOT duplicated
- [x] `EntityKind for ItemInstance` implemented against EF_001 §4's matrix, with per-class affordance refinement
- [x] Definition/instance split on the System/per-actor tenancy tiers (ITM-A1)
- [x] **Representation rule (ITM-A2) enforced, not asserted** — ITM-V10 / ITM-C2 / AC-ITM-2
- [x] **DF07 seam implemented, not merely described** — PL_007 ships the `EquipmentStats` impl DF7-D1 deferred to it, with zero DF07 change (§6.3); the `blocked_by_primary` double-count and the `equipment_version` monotonicity limit are both called out rather than left latent
- [x] **`InstrumentTag` closes a three-way latent break** — PROG_001's `InstrumentMatch::Specific(ResourceKind)` and DF07's `Some(Blade)` were both unsatisfiable once ITM-A2 withdraws `ResourceKind::Item`; resolves PROG-D15 as a side effect (§6.4 / ITM-C7)
- [x] Equipment as slot assignment, keeping `LocationKind` closed (ITM-A5)
- [x] 4 `Item:*` EVT-T1 sub-types with the PL_005-closed-set argument recorded (ITM-A7 / ITM-Q2)
- [x] 24 V1 `item.*` rule_ids (21 rejects + 3 warnings, counted per source in §9.2) + 4 V1+ reservations; **6 checks explicitly delegated** to EF/PF/CSC/COMB rather than duplicated (§9.1)
- [x] New validator sub-stage **3.5.e** with an applicability predicate
- [x] 11 cross-aggregate consistency rules (ITM-C1..C13), incl. the `ItemId`/`ItemInstanceId` drift resolution; C8–C11 added at the review pass (charge coherence · def-edit gate · Untracked scaling · the nutrition/starvation rule)
- [x] Event-model mapping: 4 T1 + 1 T4 + 2 T3 + 4 T8 + 1 V1+30d T5; no new EVT-T* category
- [x] 3 RealityManifest extensions, all OPTIONAL V1 with engine defaults
- [x] 12 closure-pass-extensions declared; 5 marked load-bearing (§12)
- [x] EF-D3 resolved by decision; RES-D1 resolved by withdrawal; RES-D2/D4 given schema homes
- [x] 5 sequences, incl. two rejects and the cascade
- [x] 23 V1-testable acceptance criteria (AC-ITM-1..31), each naming its rule_id; **AC-ITM-14..23 added at the review pass, each one biting a defect that pass found** (§14.1)
- [x] 17 deferrals (ITM-D1..D12, D19..D23) with target phases
- [x] **All 5 open questions RESOLVED (§16)** — 2 decided, 3 deferred with named triggers; none left as "we'll see"
- [x] **Review pass 2026-07-26 — 11 defects found and fixed** (§19): ITM-C4 lifecycle contradiction · unequip soft-lock · item-side destroy cascade · vacuous CSC delegation · vacuous ITM-V13 · digest bound vs author profile · nutritional-item starvation · charge-config incoherence · def-edit orphaning · Untracked instance explosion · rule_id undercount
- [x] ABL_001's two routed questions **answered** (ABL-Q9 merge + `grants_ability`) — §12.13
- [x] Loot seam handed over without designing the loot module (§8.5 / AUD-F9); COMB_004 then consumed it with no schema change
- [x] Multiverse fork inheritance stated (§8.7) — the track convention every other aggregate row carries
- [x] Self-review pass complete (§19) — 11 defects
- [x] **Cold-start `/review-impl` pass complete (§19.1) — 11 further defects, 4 HIGH**, this time in the docs' own interior (`ItemClass` / `UseEffectDecl` / `EquipDecl` / the `EntityKind` impl), exactly where §19 predicted it was under-challenged. One finding was *introduced by* the self-review pass (the §8.1 ↔ ITM-C4 suspension contradiction), which is the clearest evidence the cold-start step earns its cost.
- [x] 13 consistency rules (ITM-C1..C13) · 31 acceptance criteria (AC-ITM-1..31) · 24 V1 rule_ids
- [ ] CANDIDATE-LOCK closure pass — gated on: the 4 closure-pass extensions this pass created (PROG_001 `InstrumentMatch` variants + `EquipRequirement` field names · DF07 resolution-subject note · WA_003 `Forge:EditItemDef` divergence flag · CSC_001 3.5.d predicate) landing at their owners, plus the ABL-Q9 merge
- [ ] A **second** cold-start pass is *not* recommended before implementation — two passes found 22 defects with sharply different profiles; a third on unchanged text has low expected yield. The next real test is building against it (AUD-F8).

---

## §19 Review pass — findings ledger (2026-07-26)

A self-review of both docs, immediately after drafting. Recorded rather than silently folded in, because
the pattern in what was wrong is more instructive than the fixes: **every one of the first five defects
sits at a seam with another feature**, and none is visible from inside PL_007 alone.

| # | Severity | Defect | Fix | Bite test |
|---|---|---|---|---|
| 1 | **HIGH** | **ITM-C4 contradicted EF_001 §6.1.** "Equipped ⇒ `lifecycle_state == Existing`" is violated by *every* NPC cold-decay, since EF_001's `Existing → Suspended` cascade suspends held items. Worse, the natural "fix" (clear the slots) would have NPCs waking up disarmed. | ITM-C4 restated as **lifecycle lockstep with the holder** (§4.2); slots survive suspension, cleared only on Destroyed/Removed/location-change | AC-ITM-15 (fails against the original wording) |
| 2 | **HIGH** | **Unequip soft-lock.** §8.3 asserted unequip is safe at capacity "because it doesn't change holding" — but PL_007b §4.1 counts *held-and-not-equipped*, so unequip **increments** `slots_used`. A full actor at cap could neither equip nor unequip: reachable by ordinary play, no in-game escape. | **Over-encumbered rule** (PL_007b §4.1b) — rearrangement exempt from the cap; encumbrance gates acquisition only | AC-ITM-17 / AC-INV-11 |
| 3 | **HIGH** | **Item-side destroy cascade missing.** §8.4 covered the *holder* dying but not the mirror case: an equipped item destroyed on its own (wand spends last charge, `Forge:DestroyItem` on worn armour). `actor_equipment` would reference a destroyed entity and DF07 would keep applying its modifiers. | Explicit rule: any item → Destroyed/Removed clears its slots in the same transaction and bumps `equipment_version` (§8.4) | AC-ITM-14 |
| 4 | **HIGH** | **A delegated check that could never fire.** §9.1 delegated drop-tile-placeability to CSC_001 3.5.d — whose applicability predicate matches no `Item:*` sub-type. 3.5.d early-exits on every drop; items could be dropped onto non-placeable tiles forever while both docs read as covered. Introduced in the same paragraph that names the non-vacuity rule. | `Item:Drop`/`PickUp` added to 3.5.d's predicate + registered as a CSC_001 closure-pass extension | AC-ITM-16 (fails if 3.5.d early-exits) |
| 5 | **MED** | **ITM-V13 was vacuous as specified.** In typed Rust the payload has no `charges`/`damage` field, so "payload carries no engine-owned field" could not fail — a structural restriction dressed as a validator. | Specified at the **deserialization boundary** where it can bite: `serde(deny_unknown_fields)` on item payloads, ITM-V13 = the Stage-0 rejection of that error (§9.1) | AC-ITM-11b (fails if the deserializer is permissive) |
| 6 | **MED** | **Digest bound broke on a legitimate config.** The ≤29-line assertion was derived from the 6-slot default, but the slot profile is author-declared and `equipped` renders in full — a 20-slot reality trips ITM-V17 on valid authoring. An assertion that cries wolf gets disabled. | Profile capped at 12 (§6.1) **and** the bound restated as a formula over profile size (PL_007b §5); ITM-V17 asserts the computed value | AC-INV-12 / AC-INV-13 |
| 7 | **MED** | **Starvation while carrying rations.** Nothing stopped an author declaring `travel_ration` as an `ItemClass::Consumable` item; RES_001 §7.2's hunger tick only scans `resource_inventory`, so the PC starves holding food — and `Hungry` 7 escalates to a mortality trigger. | **ITM-C11** — `nutritional` is a `resource_kinds` property only; item defs carrying it reject at bootstrap. Instanced food needs the tick to read held instances first (ITM-D23) | AC-ITM-20 |
| 8 | **MED** | **Untracked instance explosion.** Nothing forbade item instances on Untracked actors, so COMB_005's default-`Untracked` hostile spawns would mint an entity per enemy per weapon — the blow-up AIT_001 exists to prevent, reached through the item system's back door. | **ITM-C10** — Untracked hold nothing; gear is DF07-archetype flavour, materialised on promotion | AC-ITM-19 (counts rows) |
| 9 | **LOW** | Contradictory charge configs silently accepted (`consume_on_exhaust` + `max_charges: None`; `Some(0)`) | **ITM-C8** | AC-ITM-21 |
| 10 | **LOW** | `Forge:EditItemDef` could orphan equipped instances into slots the def no longer names | **ITM-C9**, on the TVL_001 `route.remove_blocked_by_active_journey` precedent | AC-ITM-22 |
| 11 | **LOW** | **rule_id undercount** — claimed 13 V1 while declaring 21 rejects + 2 warnings (the consistency rules and PL_007b were never counted) | §9.2 now counts per source, with the ledger visible | — |

**Also closed in the pass, not defects:** all 8 open questions resolved (§16, PL_007b §12); ABL_001's two
routed questions answered (§12.13); AC-INV-10 reworded from an untestable claim (it hooked onto a DP-A8
"assertion" that is a policy, not a runtime guard) to a CI call-graph check; multiverse fork inheritance
added (§8.7) to match the track convention.

**What this pass did *not* do.** It is author self-review, so it is subject to exactly the author
blindness POST-REVIEW warns about — the defects it found cluster in *cross-feature seams* (where I had to
re-read someone else's doc to check myself) and thin out in PL_007's own interior, which is suspicious
rather than reassuring. A cold-start `/review-impl` should still run, and should be pointed at §5–§7
(the def/equip/use vocabularies), which this pass barely challenged.

### 19.1 Cold-start `/review-impl` pass — findings ledger (2026-07-26)

Run immediately after the commit, aimed at §5–§7 per the prediction above. **The prediction held: 11
more findings, 4 HIGH — and this time they are in the interior, not the seams.** One of them was
*introduced by the self-review pass itself*, which is the strongest possible argument for the cold-start
step existing.

| # | Severity | Defect | Fix |
|---|---|---|---|
| 1 | **HIGH** | **§8.1 contradicted ITM-C4 — and the self-review created it.** §8.1 said flatly "items never go `Suspended` in V1"; the review-pass rewrite of ITM-C4 requires lifecycle **lockstep with the holder**. Both cannot hold. EF_001 says both halves precisely: §6 = no *independent* item suspension, §6.1 = held items *do* cascade-suspend. The §8.1 transition table was also **missing both cascade rows**, which is what let the contradiction hide. | §8.1 restated as *cascade-only, never independent*, with the two rows added; ITM-D10 rescoped to mean *independent* suspension. **AC-ITM-24** |
| 2 | **HIGH** | **`EquipRequirement::ProgressionLevel { min_level }` invents a concept PROG_001 explicitly forbids.** PROG_001 §1 carries a user-directed locked decision: *"NO level / NO power-rating concept."* It exposes `raw_value: u64` + optional tiers. ITM-V5 would have read a field that does not exist, and the name would have re-imported the aggregate-power framing the substrate exists to avoid. | Replaced with `MinProgression { min_raw_value }` + `MinProgressionTier { min_tier }`, both in PROG_001's own vocabulary. **AC-ITM-25** |
| 3 | **HIGH** | **§6.4 silently changed PROG_001's `instrument_match` semantics.** PROG_001 evaluates `rule.instrument_match.matches(current_turn.instrument)` — the **turn's** `tools[0]`. §6.4 redefined resolution as "the `main_hand`-equipped item", one global rule for two consumers. Because `ItemClass::Tool` is never equippable, *every* "train X while using tool Y" rule became permanently unsatisfiable — a whole category of training rule silently dead. | Resolution split per consumer: PROG_001 → turn instrument (unchanged); DF07 → equipped item. PL_007 supplies vocabulary + tags, **not** one global rule. **AC-ITM-26** |
| 4 | **HIGH** | **`type_default_affordances()` was unimplementable.** Written as `class_default(self.def_id.class())` — but `ItemDefId` is a `String` newtype with no class, and more fundamentally EF_001's contract is **one default per `EntityType`** with a deliberately `&self`-only signature (kept object-safe for `&dyn EntityKind`), so a body holding only a `def_id` has no route to the manifest. "8 per-class defaults" does not fit the slot EF_001 offers. | Per-class set **materialised at instance birth** into the existing `entity_binding.affordance_overrides`; the trait returns EF_001's honest per-type default. Read path stays one binding read, no manifest join. **AC-ITM-27** |
| 5 | **MED** | **§7.1's central claim was false for 2 of 7 variants.** "Every variant routes to an aggregate already owned by another feature" — `Unlock` mutates nothing (§7.3, blocked on the unwritten EnvObject body) and `Reveal` has no durable sink (PL_005b §5.6 puts `KnowledgeAccrual` at V1+). Both **pass ITM-V8** and return success with zero state change: indistinguishable from a bug to a player, unassertable to QA. | Per-variant sink table; `Unlock`/`Reveal` now emit `item.use_effect_narrative_only` on an accepted turn. `Key` is documented as narrative-only in V1. **AC-ITM-28** |
| 6 | **MED** | **The §5.2 "Equip?" column was documentation with no validator** — `ItemClass::Document` with `equip: Some(..)` passed everything. | **ITM-C12(a)**. **AC-ITM-29** |
| 7 | **MED** | **`Consumable` did not imply finite charges** — `ItemClass::Consumable` + `max_charges: None` = an infinitely reusable consumable. | **ITM-C12(b)** |
| 8 | **MED** | **An unreachable-by-construction effect was legal** — `use_effect: Some(..)` on a class whose affordance default lacks `BeUsed`. | **ITM-C12(c)** |
| 9 | **MED** | **ITM-C9 covered too little.** It gated `equip.*` edits only, leaving `class` (diverges from birth-materialised affordances), `use_effect` (changes what a held item does, with no player-visible cause) and `max_charges` (lowering it leaves instances above the new max, unclamped) freely editable under live instances. | ITM-C9 scope extended + **ITM-C13** decides the retroactivity question explicitly (edit applies to future instances; live ones keep their set; count reported to `forge_audit_log`). **AC-ITM-30** |
| 10 | **LOW** | **`has_charges DESC` was ambiguous in the worst direction.** Over `Option<u32>`, read as `is_some()` it ranks a **spent husk** (`Some(0)`) above a usable charge-less sword (`None`) — the digest's scarce lines advertising exactly what the actor cannot use. | Predicate spelled out: `charges.map_or(true, \|c\| c > 0) && use_effect.is_some()`. **AC-ITM-31** |
| 11 | **LOW** | **Dead declarations.** `ItemOrigin::Trade` is marked "V1 unused" with no writer — a variant nothing can produce. `EquipSlotProfileId` / `profile_id` is unreferenced, because §11 holds a single `Option<EquipSlotProfileDecl>` with no keyed lookup to reference it *by*. | Accept and document: both are forward-declarations for ITM-D2 (per-race profiles) and ITM-D7 (custody chain). Flagged so a reader does not hunt for the writer. |

**What the two passes together say about the shape of the risk.** Self-review found seam defects and
missed interior ones; cold-start found interior defects and *inherited* one the self-review created. The
generalizable lesson for this track: a feature that integrates with eight others will have its seams
checked by the act of writing it (you must read the neighbour to write the sentence) and its **own closed
enums and trait impls** left unchecked, because nothing forces a second look at them. `ItemClass`,
`UseEffectDecl`, and `EquipDecl` were all authored once and never re-derived — and all three had defects.

### 19.2 What both passes MISSED — found by a third party (recorded 2026-07-26)

Kept here deliberately, because a findings ledger that lists only successes overstates how much the
passes are worth.

**The signed `VitalDelta` was a damage-law-chain bypass, and neither pass saw it.** The combat-family
session found it while reconciling ABL-Q9 (commit `44645784a`). `UseEffectDecl::VitalDelta { amount: i32 }`
is **signed**, so an item could write `{ Hp, −30 }` directly and skip COMB_001 §4's chain entirely — no
`Armor`, no hit roll, no COMB_003 threat accrual (accrual reads `damage_applied` *from* the chain), no
COMB_001 Q4 disparity cap, and no COMB_006 PvP eligibility check (those guard `Strike` and `Damage`, not a
raw vital write). That is **an unmissable, armour-ignoring PvP weapon usable inside a sanctuary**, and it
falsifies COMB_001's "the 4-step chain is the sole damage authority" from inside this feature's own §7.1.

Why both passes missed it, which is the useful part:

- The **self-review** was hunting cross-feature *contradictions* — statements in two docs that disagree.
  This was not a contradiction; §7.1 and COMB_001 §4 never mention each other. It was an **absent
  constraint**, and absences do not surface when the method is comparing two texts.
- The **cold-start pass** read §7.1 closely — closely enough to find `Unlock` and `Reveal` decorative —
  and still treated `VitalDelta` as the safe, unremarkable variant *precisely because it had an obvious
  owner* (RES_001 `vital_pool`). Having a legitimate sink made it look finished. The question neither pass
  asked was **"what is the worst thing an author can express with this field?"** — a sign check on one
  `i32`.
- What did find it: a session holding **both** enums in view for an unrelated reason. Not more care —
  different adjacency.

**Standing correction to §19's lesson:** a review pass catches what its *mode* is aimed at.
Contradiction-hunting finds contradictions; interior-hunting finds interior sloppiness; neither reliably
finds a **missing guard on a legal value**. For that the question is adversarial-authoring — *what can a
careless or hostile author declare here?* — and it should now be asked of every author-declared numeric
field in this track, starting with the ones PL_007 still owns (`weight`, `max_charges`, `reach`,
`StatModifier.value`, `price`).
