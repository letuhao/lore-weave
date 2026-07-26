# COMB_004 — Loot & Spoils

> **Conversational name:** "Spoils" (SPO). What an encounter **produces**. Owns the reward-generation law
> (loot tables, seeded rolls), the defeat-finalisation trigger, the loot-rights window that stops
> ninja-looting, and the progression award — the reason a fight is worth having.
>
> **Category:** COMB — Combat (COMB_004)
> **Status:** **DRAFT 2026-07-26**. Resolves the second third of **AUD-F9** ([`../../12_module_coverage_audit.md`](../../12_module_coverage_audit.md))
> — *"no loot/drops (combat resolves and produces nothing). TMP_006 treasure is world-placement, not
> encounter reward."*
> **SPO-Q1..Q9 LOCKED** in this pass; `SPO-A1..A7` axioms codified.
> **Stable IDs in this file:** `SPO-A*` axioms · `SPO-Q*` decisions · `SPO-D*` deferrals · `SPO-V*`
> validators · `AC-SPO-*` acceptance criteria. Owns the `spoils.*` reject namespace.
> **Builds on:** [PL_007](../04_play_loop/PL_007_item.md) **§8.5 "the loot seam"** (the handover this doc
> accepts) + `ItemOrigin::Loot` + `ItemDef` · [PL_007b](../04_play_loop/PL_007b_inventory.md) §10.7
> `CellItemView` + bulk partial-fill · [COMB_001](COMB_001_combat_foundation.md) §4 seed (Q8) + §6
> mortality/KO (Q3) · [EF_001](../00_entity/EF_001_entity_foundation.md) §6.1 holder-death cascade ·
> [RES_001](../00_resource/RES_001_resource_foundation.md) §4.2 cell-owned `resource_inventory` + §7.4 bulk
> harvest · [PROG_001](../00_progression/PROG_001_progression_foundation.md) progression grants ·
> [WA_006](../02_world_authoring/) mortality finalisation · [AIT_001](../16_ai_tier/AIT_001_ai_tier_foundation.md)
> tiers · [TMP_006](../00_tilemap/) treasure (deliberately distinct — §8).
> **Determinism is inviolable** — every roll is seeded from the COMB_001 Q8 family (SPO-A2).

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

An encounter currently resolves and **produces nothing**. Combat costs stamina, HP, items and risk, and
returns no items, no currency and no progression. That is not a balance problem — it is a missing
subsystem, and it makes every locked incentive in the design inert: FAC_001 standing, REP_001 notoriety and
PROG_001 advancement all assume the player has a reason to fight.

Two adjacent things already exist and are **not** this:

| Existing | What it is | Why it is not loot |
|---|---|---|
| **TMP_006 treasure** | tiered treasure *placed in the world* by the tilemap generator | world-placement at generation time; nothing to do with an encounter |
| **EF_001 §6.1 death cascade** | a dead actor's carried and equipped items drop to the cell | the actor's **own gear**, not a *reward* — a bandit with no sword drops nothing |

PL_007 §8.5 explicitly handed this module the seam, reserved `ItemOrigin::Loot`, and stated the substrate
is already in place: *"a dead actor's held items are already `Existing` items with
`location = InCell(death_cell)` … a loot module therefore needs only an interaction and a
reward-generation rule. No PL_007 schema change."* This doc is that interaction and that rule.

### V1 minimum scope

- **`LootTableDecl`** — a RealityManifest extension keyed by `ActorClassRef` (§3), the same key DF07 §9 uses
  for `stat_archetypes`, so an archetype's stats and its drops are declared against one identifier.
- **Independent seeded per-entry rolls** (§4) — inspectable, order-independent, replay-exact; seed role
  `loot` joins COMB_001 Q8's role set.
- **Defeat-finalisation trigger** (§5) — loot rolls at **death finalisation, never at KO** (SPO-A1). This is
  the single most important rule in the doc.
- **The spoils pile** (§6) — generated items land as `InCell` entities beside the cascade-dropped gear;
  fungible spoils land in the **cell-owned** `resource_inventory` RES_001 already supports.
- **`spoils_claim`** (§7) — the loot-rights window, and the **one** new ephemeral structure this doc adds.
- **Progression award** (§9) — the closure of "combat produces nothing" that matters more than items.
- **Anti-farm** (§10) — spawn-group loot budget + `first_kill_only`, composing with COMB_005's respawn epochs.
- **8 V1 rule_ids** in the `spoils.*` namespace + **7 validators** SPO-V1..V7 + **AC-SPO-1..13**.

### V1 NOT shipping

| Feature | Defer to | Why |
|---|---|---|
| Need/greed rolls, master looter, party loot modes | V1+ (SPO-D1) | needs a party-decision UI; V1 rights are side-scoped and automatic (§7) |
| Corpse containers (loot *from* a body rather than from the floor) | V1+ (SPO-D2 ≡ ITM-D3) | needs `resource_inventory.owner = Item` (RES V1+30d) and EF-D3 container enforcement |
| Randomised item affixes / quality rolls on drop | V1+ (SPO-D3 ≡ ITM-D2) | PL_007 modifiers are authored per def; rolling them needs a generation model |
| Currency-only "bounty" economy, vendor pricing | V1+30d → V2 economy (SPO-D4) | RES_001 §1 defers the economy module; AUD-F11 is an accepted V1 cut |
| Quest-objective drops ("collect 5 wolf pelts") | V2 `13_quests` (SPO-D5) | `LootCondition` reserves the hook; QST_001 owns the objective |
| Bonus loot from over-performance (no-death, speed) | V1+ (SPO-D6) | needs encounter scoring, which nothing owns |
| PvP looting (taking a defeated PC's gear) | V1+ (SPO-D7) | WA_006 + PCS_001 own PC death consequence; item loss is a policy call, not a loot-table one |
| Loot for a **fled** enemy | won't-fix V1 (SPO-D8) | fleeing is escape; rewarding it removes the cost of letting an enemy go |
| Player-visible drop-rate display | V1+30d (SPO-D9) | §11 defines the data; the COMB_001 Q8 `combat_seed_visible` dev flag already exposes rolls in dev |

---

## §2 — Concepts & axioms

| Concept | Maps to | Notes |
|---|---|---|
| **LootTableDecl** | RealityManifest entry keyed by `ActorClassRef` | System-tier, author/admin-only (SPO-A7). |
| **LootEntry** | `{ subject, qty, chance_milli, condition, first_kill_only }` | One independent roll each (§4). |
| **LootSubject** | `Item(ItemDefId) \| Resource(ResourceKind) \| Progression(ProgressionKindId)` | The three things an encounter can yield. |
| **spoils pile** | *not an aggregate* — `InCell` items (EF_001) + the cell's `resource_inventory` (RES_001) | §6. |
| **spoils_claim** | Ephemeral per-(cell, encounter) rights record | §7. **The one new structure in this doc.** |
| **defeat finalisation** | WA_006 mortality resolution, or Untracked group-pool zero | The trigger (§5). |

### Axioms

- **SPO-A1 (Loot rolls at defeat finalisation, never at KO).** COMB_001 Q3 makes HP = 0 a **revivable**
  `knocked_out` state for `ko_duration_rounds` (V1 = 5) before WA_006 `Dying`. Generating loot at KO would
  let a party loot a body and then revive it — minting items from a reversible state. Loot is generated
  exactly once, when mortality **finalises**, and for Untracked bulk groups when the group HP pool reaches
  zero (there is no per-member KO to reverse).
  > **⚠ 2026-07-26 (DF07_002 §1.5 HIGH-1).** "The group HP pool" now has a declaring owner: it is
  > `combat_session.group_pools[group].current` (COMB_001 §2), added by the seam review because this axiom
  > and SPO-A6 both triggered on a value no doc stored. The trigger is `current == 0`; the ceiling comes
  > from DF07 §9 (`archetype.MaxHp × member_count`).
- **SPO-A2 (Every roll is seeded and replay-exact).** Rolls draw from the COMB_001 Q8 seed family with
  `role = loot`: `seed(reality_id, turn_id, actor_id, action_idx, "loot")`. Replaying an encounter
  reproduces byte-identical drops. **This adds one role to COMB_001 Q8's set**
  (`{damage, crit, hit, position}` → `+ loot`) — recorded as closure item 1 (§12).
- **SPO-A3 (Generation is engine-owned; the LLM never rolls, names or narrates a drop into existence).**
  Extends COMB-A1. The narration layer receives the resolved drop list and describes it; prose claiming an
  item that is not in the list is an A6 canon-drift flag, exactly as for damage numbers.
- **SPO-A4 (Loot is additive to the death cascade, never a replacement).** EF_001 §6.1 already drops the
  defeated actor's carried and equipped items. COMB_004 **adds** generated spoils to the same cell. The two
  paths stay separate: a bandit's actual sword falls because they were carrying it; three copper coins
  appear because the table said so. Merging them would make an unarmed enemy undroppable and let a table
  entry silently duplicate real gear.
- **SPO-A5 (Rights are side-scoped, not first-come).** For a bounded window, only the victorious side may
  take the spoils (§7). Without this, any bystander who walks into the cell during the fight takes
  everything, which is a grief vector rather than an emergent outcome.
- **SPO-A6 (Untracked groups roll once per group, not per member).** A 12-bandit `EngineDriver` mob has one
  pooled HP bar (`combat_session.group_pools`, COMB_001 §2 — AC-7 stated the requirement, the field now
  exists); it gets **one** table roll scaled by `group_size`, not twelve. Rolling per member would both
  contradict the pooled model and make untracked mobs the most lucrative content.
- **SPO-A7 (Tables are System-tier).** `LootTableDecl` lives in the RealityManifest, is author/admin-write
  only, and is edited through an audited `Forge:EditLootTable`. A player-writable drop table is a
  cross-tenant defect of the first order — one player's edit would change every player's rewards.

### Event-model mapping

COMB_004 introduces **no new aggregate and no new EVT-T\* category.** It reuses existing owned events:

| Trigger | Event | Owner |
|---|---|---|
| Generated item instantiated | **EVT-T4 System** `EntityBorn` (`entity_type=Item`, `provenance.origin = Loot`) | EF_001 / PL_007 |
| Generated fungible spoils | **EVT-T3 Derived** `aggregate_type=resource_inventory` (owner = Cell) | RES_001 |
| Progression award | **EVT-T3 Derived** `aggregate_type=actor_progression`, `TrainingSource::CombatVictory` | PROG_001 |
| Spoils taken by a claimant | **EVT-T3 Derived** `entity_binding` location change / inventory delta | EF_001 / RES_001 |

> **⚠ 2026-07-26 (DF07_002 §1.5 LOW-6) — the progression award needs a declared source.** PROG_001's
> `TrainingSource` is a **closed** enum (`Action` / `Time` V1; `Mentor` / `Quest` / `CrossActor` V1+), and a
> victory award is none of them — so the row above was writing `actor_progression` through a vocabulary
> that has no slot for it. Added as **`TrainingSource::CombatVictory`**, a schema-additive variant per I14,
> and recorded as a PROG_001 closure item (§12). Routing it through `Action` instead would have been wrong
> in a way that shows up later: `Action` training is per-blow and already fires during the fight, so the
> victory award would have been double-counted against the same curve.
| `spoils_claim` born / expired | rides `CombatSessionResolved` + fiction-clock expiry (§7) | COMB_001 / PL_001 |
| Author edits a table | **EVT-T8** `Forge:EditLootTable` | WA_003 Forge (new sub-action) |

---

## §3 — `LootTableDecl` (RealityManifest extension)

```rust
pub struct RealityManifest {
    // ... existing fields ...

    /// Author-declared drop tables, keyed by actor class — the SAME key DF07 §9 uses for stat_archetypes.
    pub loot_tables: HashMap<ActorClassRef, LootTableDecl>,
}

pub struct LootTableDecl {
    pub entries: Vec<LootEntry>,             // 0..=16 V1 (SPO-V1); empty ⇒ this class drops nothing
    pub group_scaling: GroupScaling,         // how an Untracked group's single roll scales (SPO-A6)
}

pub struct LootEntry {
    pub subject: LootSubject,
    pub qty: QtyRange,                       // { min, max } — inclusive; min == max ⇒ fixed
    pub chance_milli: u16,                   // 0..=1000 ; 1000 = guaranteed
    pub condition: Option<LootCondition>,    // None ⇒ always eligible
    pub first_kill_only: bool,               // anti-farm (§10)
}

pub enum LootSubject {
    Item(ItemDefId),                         // PL_007 catalogue
    Resource(ResourceKind),                  // RES_001 fungible (currency, materials)
    Progression(ProgressionKindId),          // §9 — the award that makes fighting worth it
}

pub enum LootCondition {
    KilledBySide(SideRef),                   // only if that side landed the finishing blow
    MinEncounterRounds(u8),                  // discourages trivial farm kills
    RealityFlag(FlagId),                     // world-state gate (WA_001 / V2 quest hooks)
}

pub enum GroupScaling {
    PerMemberLinear,                         // qty × group_size          (coins)
    SqrtGroup,                               // qty × ⌈√group_size⌉       (default — sub-linear)
    FlatOnce,                                // qty unchanged             (rare drops)
}
```

**Why keyed by `ActorClassRef`.** DF07 §9 already keys `stat_archetypes` by it and ACT_001 already carries
it on `CanonicalActorDecl`. One key means an author declares a `bandit`'s stats and its drops side by side,
and it costs **no new schema anywhere** — SPO-A7 aside, this whole doc's manifest footprint is one map.

**Per-actor override** is deliberately *not* a new field: a named boss whose drop differs from its class
gets its own `ActorClassRef`. Adding a second override path would create two answers to "what does this
actor drop", which is the drift `_boundaries/` exists to prevent.

---

## §4 — The roll law (SPO-Q2 LOCKED)

```pseudo
fn roll_spoils(defeated, session) -> Vec<Award>:
    table = manifest.loot_tables[defeated.actor_class] ?? EMPTY        // no table ⇒ no spoils, no error
    if defeated.actor_kind == Pc:                       return []      // §5 — PC defeat yields no roll
    out   = []
    for (i, entry) in table.entries.enumerate():                       // DECLARED ORDER — stable
        if !condition_met(entry.condition, session):        continue
        if entry.first_kill_only && group_state(defeated.spawn_group).claimed.contains(i): continue
        rng = chacha8(seed(reality_id, turn_id, defeated.actor_id, session.next_action_idx, "loot", i))
        if rng.next_u16_milli() >= entry.chance_milli:      continue    // independent Bernoulli
        qty = entry.qty.min + rng.range(0, entry.qty.max - entry.qty.min)
        qty = scale(qty, table.group_scaling, defeated.group_size, entry.subject)   // SPO-A6 + §4.1
        if qty == 0:                                        continue    // §4.1 — a zero award is no award
        if entry.first_kill_only: group_state(defeated.spawn_group).claimed.insert(i)
        out.push(Award { subject: entry.subject, qty })
    return out
```

### §4.1 Three rules the loop needs that the first draft left implicit

1. **`qty == 0` is skipped, not awarded.** `QtyRange { min: 0, max: 3 }` is a legitimate declaration
   (a *chance of* 1–3 coins layered on a chance-to-drop), and it rolls 0 a quarter of the time. Emitting a
   zero-quantity award mints an `EntityBorn` for nothing and shows the player an empty line in the spoils
   list. Skipped silently — it is not an error.
2. **`GroupScaling` never applies to `Progression`.** `PerMemberLinear` on a progression subject would
   grant 12× advancement for clearing a 12-strong camp, which routes around PROG_001's curves by the
   simplest possible arithmetic and makes bulk untracked mobs the fastest progression in the game.
   **Progression subjects are always `FlatOnce`, regardless of the table's declared scaling** — scaling is
   an *item/currency* concept. ITM-shaped subjects scale; advancement does not.
3. **Progression awards to non-PC victors are dropped.** An untracked NPC has no `actor_progression` row by
   design (DF7 §9), so "award 3 swordsmanship to the winning bandits" has nowhere to write. Tracked NPC
   victors *do* receive it (they have the row). Dropping rather than materialising a row is deliberate:
   materialising on a loot award would promote actors by winning fights nobody watched, which is exactly
   what AIT_001's quantum-observation principle exists to prevent.

### §4.2 `first_kill_only` state — the one thing that is genuinely stored

§10 claims the anti-farm mechanisms are "derived from the epoch, so they need no stored counter". That is
true of the **epoch key** and false of the **claimed set**: `first_kill_only` is a fact about *what has
already happened* within an epoch, and no amount of arithmetic recovers it. Stated plainly rather than
left as a contradiction:

```rust
/// Ephemeral, per materialised spawn group. Lives exactly as long as the group (COMB_005 §9).
pub struct SpawnGroupLootState {
    pub group_id: SpawnGroupId,        // (channel_id, decl_index, epoch) — the epoch IS in the key
    pub claimed: BitSet,               // entry indices already taken by a first_kill_only draw
    pub budget_remaining: u16,         // §10 loot budget
}
```

- **The epoch is in the key**, so a new epoch is a *different* group and starts fresh — no reset logic, no
  cleanup, no drift. That is what §10's "derived" claim was reaching for and stated too strongly.
- **It dies with the group.** An unobserved camp holds nothing (COMB_005 SPN-A4), so this is not durable
  state; it is the same lifetime as the materialised group itself.
- **Consequence, accepted:** if a camp is unloaded and re-observed *within* one epoch, `claimed` is lost
  and a `first_kill_only` entry can fire twice. The alternative — persisting it — buys a durable table,
  a cleanup policy and a time-dilation question, to close an exploit that requires deliberately cycling
  observation of one camp for one extra rare drop per epoch. The **`budget_remaining`** cap (§10) bounds
  the total yield either way, which is why this is a defensible cut rather than an open hole. Recorded as
  **SPO-D10**.

**Independent per-entry rolls, not one weighted pick** (SPO-Q2). A single weighted selection means adding a
new entry silently reduces every existing entry's rate — the classic loot-table footgun, where a designer
adds a cosmetic drop and quietly halves the sword rate. Independent Bernoulli rolls make each entry's
`chance_milli` mean exactly what it says, and adding an entry changes nothing else.

- **The entry index `i` enters the seed**, so entries are mutually independent and reordering the table
  does not permute prior results in a saved world. Iteration is over a `Vec` in declared order — no map, no
  hash iteration (SPO-V6).
- **Integer arithmetic throughout**; `chance_milli` is per-mille, matching DF7's per-mille slots and ABL's
  `mult_milli`. No floats anywhere in the loot path (DF7-A4 discipline).
- **An empty or absent table yields nothing and is not an error** — most actor classes should drop nothing,
  and requiring a table per class would be an authoring tax that produces filler drops.

---

## §5 — The trigger: defeat finalisation (SPO-A1 / SPO-Q1 LOCKED)

```
HP = 0  ──→  PL_006 `knocked_out`  ──(ko_duration_rounds, V1 = 5)──→  WA_006 Dying ──→ finalised
              │                                                                          │
              └── revived within the window ⇒ NO loot, ever ────────────────────────      ▼
                                                                              roll_spoils() ONCE
```

| Path | When loot rolls |
|---|---|
| Tracked actor (PC / Major / Minor NPC) | at **WA_006 mortality finalisation** — after the KO window expires unrevived |
| Untracked bulk group | at **group HP pool = 0** — there is no per-member KO state to reverse (COMB_001 §8 AC-7) |
| Actor **fled** | never (SPO-D8) |
| Actor still `knocked_out` at encounter end | at finalisation if it comes; the encounter resolving does not itself finalise mortality |
| Encounter cancelled (`Forge:CancelCombat`) | never — an admin escape hatch must not mint items |
| **A defeated PC** | **never in V1** — no roll, regardless of any table keyed to the PC's actor class. Their carried gear still drops via the EF_001 §6.1 cascade (that is WA_006/PCS_001's death-consequence policy, not a reward), but COMB_004 generates nothing. Rolling here would be **PvP looting** through the side door, which is SPO-D7 |
| **All hostiles routed** (fled, not defeated) | never — `Resolved:Routed` finalises no mortality (SPO-D8) |
| **Mutual wipe** — both sides reach zero | rolls **do** occur for each defeated actor, and the resulting `spoils_claim` has an **empty `entitled` list** — see §7.1 |

**Idempotency is the load-bearing property.** `roll_spoils` is called **exactly once** per defeated actor,
guarded by a `spoils_rolled` marker on the actor's mortality finalisation (SPO-V4). A retried or replayed
finalisation must not re-roll — and because the seed is deterministic, a naive re-roll would produce the
*same* items again, i.e. silent duplication that no diff would catch. This is why SPO-V4 is a real
assertion and not paperwork.

---

## §6 — Where spoils land (SPO-A4 / SPO-Q3 LOCKED)

PL_007 §8.5 established the substrate; this doc adds to it rather than replacing it:

| Award subject | Destination | Mechanism |
|---|---|---|
| `Item(def_id)` | an item entity at the defeat cell — `entity_binding.location = InCell(cell)`, `provenance.origin = Loot` | EF_001 `EntityBorn` + PL_007 instance |
| `Resource(kind)` | the **cell's** `resource_inventory` (owner = `EntityRef::Cell`) | RES_001 §4.2 — a V1-valid owner, already supported |
| `Progression(kind)` | awarded **directly to the victors**, never to the floor (§9) | PROG_001 grant |

So the "spoils pile" is not a new object: it is the union of the cascade-dropped gear (EF_001 §6.1) and the
generated drops, viewed through PL_007b's existing `CellItemView`. Taking spoils is PL_007b's **bulk
partial-fill** path — including its `item.inventory.cap_partial` warning when a claimant cannot carry
everything, with the remainder correctly left in the cell rather than destroyed.

**Consequence, stated because it is a design choice and not an accident:** unclaimed spoils **persist in
the world**. They are ordinary `Existing` items in a cell. A party that wipes and returns can recover what
they left. A V1+ decay sweep is SPO-D-adjacent and deliberately not V1 — persistence is the simpler and
more forgiving behaviour, and it needs no timer.

---

## §7 — Loot rights (SPO-A5 / SPO-Q4 LOCKED)

> **The one new structure in this doc.** Everything else reuses an existing owner.

```rust
/// Ephemeral, per-(cell, encounter). Born at CombatSessionResolved; expires by fiction-clock.
pub struct SpoilsClaim {
    pub cell_id: ChannelId,
    pub encounter_id: CombatSessionId,
    pub entitled: Vec<ActorRef>,          // surviving members of the victorious side
    pub subjects: Vec<EntityId | ResourceKind>,   // exactly what this encounter produced
    pub expires_at_fiction_minute: u64,   // default +30 fiction-minutes (manifest-tunable)
}
```

- **Inside the window:** only an `entitled` actor may take a listed subject. Anyone else is rejected
  `spoils.not_entitled`.
- **After expiry:** the claim is dropped and the items become ordinary cell contents — anyone may take
  them. This is what keeps the rule a *courtesy window* rather than permanent ownership, and it means no
  item is ever permanently locked by a party that logged off.
- **Scope is narrow by construction:** the claim lists only what *this* encounter produced. Items that were
  already lying in the cell are untouched by it, so a claim can never fence off unrelated world contents.
- **Why ephemeral rather than a field on the item:** an owner field on `entity_binding` would be durable
  state needing cleanup, and PL_007 deliberately keeps location as the single per-item fact (ITM-A5's
  spirit). A claim that expires needs no cleanup — it simply stops being consulted.

### §7.1 Empty and degenerate claims

| Case | Rule |
|---|---|
| **Mutual wipe** — no survivors on the winning side | the claim is created with `entitled = []` and is therefore **vacuously unenforceable**: no one may take the spoils until it expires, after which anyone may. This is the correct outcome — the spoils of a fight nobody survived should be a discoverable prize, and the window gives the wiped party's allies (or a returning, revived member) a fair chance to reach it first |
| **Every entitled actor leaves the cell** | the claim is unaffected — rights are by identity, not by presence. A victor who steps out to heal does not forfeit |
| **An entitled actor dies before claiming** | remains entitled (they may be revived within the KO window); the claim does not re-compute |
| **Two encounters resolve in one cell** | two claims, keyed by `encounter_id`, each listing only its own subjects. They cannot overlap, because a subject is created by exactly one roll |
| **The cell is destroyed before expiry** (PF_001 `StructuralState = Destroyed`) | the claim dies with the cell; its items follow EF_001 §6.1's cascade like any other cell contents. COMB_004 adds no special case |
| **`expires_at_fiction_minute` under time dilation** | read against the **cell's** fiction clock, consistent with COMB_005 SPN-A3 — a 30-minute window means 30 minutes *where the spoils are* |

**Rejected alternative (SPO-Q4):** auto-awarding spoils straight into victors' inventories. It needs no
claim structure at all, but it silently defeats PL_007b's carry-capacity model (awards bypass the cap),
removes the tactical choice of what to carry, and makes the cascade-dropped gear behave differently from
generated drops — two paths again. The window costs one ephemeral record and keeps one path.

---

## §8 — Not TMP_006 treasure

| | **TMP_006 treasure** | **COMB_004 spoils** |
|---|---|---|
| Generated at | tilemap generation | encounter resolution |
| Seeded on | `(reality_id, channel_id, template_id)` | `(reality_id, turn_id, actor_id, action_idx, "loot")` |
| Keyed by | zone treasure tier | `ActorClassRef` |
| Owner | TMP_001 | COMB_004 |
| Rights | none — world contents | `spoils_claim` window (§7) |

They meet in exactly one place: both end as `InCell` items read through PL_007b's `CellItemView`. Neither
generator knows the other exists, and neither should — the audit's phrasing (*"TMP_006 treasure is
world-placement, not encounter reward"*) is recorded here as a locked boundary rather than a passing remark.

---

## §9 — Progression award (SPO-Q5 LOCKED)

The audit's *"combat resolves and produces nothing"* is more true of **progression** than of items: without
this section, a reality with no `loot_tables` gains literally nothing from fighting, and PROG_001
advancement has no combat pathway at all.

- `LootSubject::Progression(kind_id)` awards `qty` raw value to the **victorious participants**, applying
  PROG_001's existing curves, soft caps and `derives_from` scaling. **No new grant mechanism** — it routes
  through the same path `Forge:GrantProgression` uses, so caps and curves cannot be bypassed by fighting.
- **Awarded to participants, not to the floor.** Progression is non-transferable by PROG_001's own axiom
  (its §178 rejection of RES_001 reuse rests on exactly this), so it cannot sit in a cell.
- **Split rule (locked):** every surviving victorious participant receives the **full** declared amount —
  not a share. Splitting would punish grouping, and PROG_001 has no notion of a partial contribution.
  Anti-farm is handled by §10, not by division.
- **KO'd-but-revived participants count**; fled participants do not.
- A reality wanting purely narrative advancement simply declares no `Progression` entries — combat then
  yields items only, which is a valid and explicitly supported configuration (SPO-Q8).

---

## §10 — Anti-farm (SPO-Q6 LOCKED)

Two mechanisms, both cheap and both composing with COMB_005's spawn epochs:

1. **`first_kill_only`** — an entry that fires once per `spawn_group` per **respawn epoch** (COMB_005 §
   epoch model). Rare/unique drops use it; a boss's signature blade cannot be farmed by re-clearing.
2. **Spawn-group loot budget** — a `spawn_group` carries a `loot_budget` that decrements per roll within an
   epoch; at zero, only `chance_milli = 1000` guaranteed entries fire. This bounds the *total* yield of a
   camp without needing per-actor cooldowns or a diminishing-returns curve.

Both are **derived from the epoch**, so they need no stored counter that could drift — the same
seed-and-epoch discipline COMB_005 uses for population. `MinEncounterRounds` (§3) is the third, softest
lever: it makes trivially-fast kills ineligible for the good entries without banning them outright.

---

## §11 — Failure-mode UX (`spoils.*` namespace)

| Reject rule | Stage | User-facing message (I18nBundle `default`) | When |
|---|---|---|---|
| `spoils.not_entitled` | 2 validate | "That is not yours to take yet." | non-entitled actor takes a claimed subject inside the window (§7) |
| `spoils.claim_expired` | — | (informational) | not a reject — the claim lapsed and the take proceeds |
| `spoils.table_entry_invalid` | 0 schema | (schema-level) | `chance_milli > 1000`, `qty.min > qty.max`, `qty.max == 0`, or > 16 entries |
| `spoils.progression_scaling_forbidden` | 0 schema | (schema-level) | a `Progression` subject in a table declaring `PerMemberLinear` / `SqrtGroup` — advancement never scales with group size (§4.1 rule 2) |
| `spoils.subject_unknown` | 0 schema | (schema-level) | `ItemDefId` ∉ `item_defs`, `ResourceKind` ∉ `resource_kinds`, or `ProgressionKindId` ∉ `progression_kinds` |
| `spoils.class_unknown` | 0 schema | (schema-level) | a `loot_tables` key is not a declared `ActorClassRef` |
| `spoils.already_rolled` | commit | (ops-level) | a second `roll_spoils` for one defeat finalisation (SPO-V4) |
| `spoils.roll_on_ko_forbidden` | commit | (ops-level) | a roll attempted while the actor is `knocked_out` (SPO-A1 guard) |
| `spoils.condition_unresolvable` | 0 schema | (schema-level) | `LootCondition::RealityFlag` names an undeclared flag |

Per RES_001 §2, every `spoils.*` reject carries `RejectReason.user_message: I18nBundle` with an English
`default` plus a Vietnamese translation from day one.

**Player-visible data contract (UI is SPO-D9):** on resolution, the victors see the drop list (names and
quantities) and their progression award. Drop **rates** are not shown (SPO-D9); the COMB_001 Q8
`combat_seed_visible` dev flag already exposes the underlying rolls in development. The narration layer
receives the resolved list and **must not** name an item outside it (SPO-A3 / A6 canon-drift).

---

## §12 — Closure-pass-extensions

| # | Target | Change | Status |
|---|---|---|---|
| 1 | **COMB_001 §4** | Q8 seed roles extended `{damage, crit, hit, position}` → **`+ loot`**; §6 mortality gains the defeat-finalisation loot hook (SPO-A1) | applied this cycle |
| 2 | **PL_007 §4.3** | `ItemOrigin::Loot` promoted from V1+ reservation to **V1 active** — its consumer now exists (PL_007 §8.5 anticipated exactly this) | declared |
| 3 | **PL_007b §10.7** | the loot module inherits `CellItemView` + bulk partial-fill as predicted; **no new inventory surface** — confirmed, no change needed | confirmed |
| 4 | **WA_006** | mortality finalisation calls `roll_spoils` once, guarded by `spoils_rolled` (SPO-V4) | declared |
| 5 | **WA_003 Forge** | new audited admin sub-action `Forge:EditLootTable` (SPO-A7) | declared |
| 6 | **COMB_005** | `spawn_group` carries `loot_budget` + the epoch key `first_kill_only` reads (§10) | applied in COMB_005 this cycle |
| 7 | **PROG_001** | combat progression award routes through the existing grant path; **no PROG_001 schema change** (§9) | declared |

---

## §13 — Validators

| ID | Stage | Check |
|---|---|---|
| **SPO-V1** | 0 schema | table well-formed: `entries.len() ≤ 16`; `chance_milli ≤ 1000`; `qty.min ≤ qty.max`; `group_scaling` valid |
| **SPO-V2** | 0 schema | every `LootSubject` and `LootCondition` reference resolves (item def / resource kind / progression kind / reality flag) |
| **SPO-V3** | 0 schema | every `loot_tables` key is a declared `ActorClassRef` (shared with DF07 §9 `stat_archetypes` — a class with stats but no table is fine; a table with no class is not) |
| **SPO-V4** | commit | **`roll_spoils` is called at most once per defeat finalisation**, and never while `knocked_out` (SPO-A1) |
| **SPO-V5** | 2 validate | claim enforcement: inside the window only `entitled` actors take listed subjects; after expiry the claim is not consulted |
| **SPO-V6** | replay | rolls iterate `entries` as a `Vec` in declared order with the entry index in the seed ⇒ byte-identical drops on replay |
| **SPO-V7** | commit | conservation, per PL_007 ITM-A2's one-representation rule: an `Item` award produces **exactly one** `EntityBorn` and **zero** `resource_inventory` deltas; a `Resource` award produces **exactly one** inventory delta and **zero** entities. An award that produces both, or neither, fails |

> **SPO-V4 and SPO-V7 are the non-vacuous pair.** SPO-V4 can fail in a way nothing else would catch:
> because the seed is deterministic, a double-invoked finalisation (a retry, a replay, a revive-then-die
> sequence that clears the marker) rolls the **same** items again — silent duplication that produces a
> plausible-looking world with no diff to notice. Its bite-test is a deliberately re-entered finalisation.
> SPO-V7 can fail because `LootSubject` has two award paths that write to **different owners** (EF_001
> `entity_binding` vs RES_001 `resource_inventory`): a subject that resolves down both — the natural bug if
> an author gives an `ItemDefId` and a `resource_kinds` id the same string — mints the reward twice.
> PL_007's ITM-V10/ITM-C2 already rejects that collision at canonical seed, and **SPO-V7 is the commit-time
> assertion that the guarantee actually held**, which is exactly the kind of check that stops being true
> when someone adds a third award path. Both are assertions about real failure modes, not structural
> restatements.

---

## §14 — Acceptance criteria (AC-SPO-1..13)

1. **Empty table is silent** — an actor class with no `loot_tables` entry is defeated: no drops, no
   progression, **no error and no log noise**.
2. **Determinism** — the same encounter replayed produces byte-identical drops, quantities and progression
   awards (SPO-A2).
3. **Independent rolls** — adding a 5th entry at `chance_milli = 100` leaves the other four entries'
   observed rates unchanged over a large sample (SPO-Q2).
4. **Seed independence** — two entries with identical `chance_milli` do not correlate across many kills
   (the entry index is in the seed, §4).
5. **No loot at KO (bite test)** — an actor is downed and revived within `ko_duration_rounds`: **zero**
   drops generated, ever. Forcing a roll while `knocked_out` trips SPO-V4 / `spoils.roll_on_ko_forbidden`.
6. **Loot at finalisation** — the same actor left unrevived past the KO window rolls exactly once at WA_006
   finalisation.
7. **Idempotency (bite test)** — re-entering finalisation (retry or replay) produces **no second set** of
   items; removing the `spoils_rolled` guard makes SPO-V4 fail and duplicates the drop.
8. **Cascade + spoils are additive** — a bandit carrying a sword drops that sword (EF_001 §6.1) **and** the
   table's coins; an unarmed bandit drops only the coins (SPO-A4).
9. **Rights window** — inside the window a non-participant taking a listed item is rejected
   `spoils.not_entitled`; after expiry the same take succeeds.
10. **Carry cap interaction** — a victor whose inventory cannot hold everything gets PL_007b's partial fill
    with `item.inventory.cap_partial`, and the remainder **stays in the cell** rather than being destroyed.
11. **Untracked group parity** — a 12-bandit group rolls **once** with `SqrtGroup` scaling (⌈√12⌉ = 4×), not
    12 times (SPO-A6).
12. **Progression award** — a kill declaring `Progression(swordsmanship, 3)` grants 3 raw value to **every**
    surviving victor, through PROG_001's curves and caps — not a split, and not bypassing the soft cap (§9).
13. **Anti-farm** — a `first_kill_only` entry fires once per spawn group per respawn epoch; re-clearing the
    camp within the same epoch yields the guaranteed entries only (§10).

---

## §15 — Edge cases (resolved 2026-07-26)

An adversarial pass over §4–§9. Rows 1–4 were live defects; the rest were unanswered questions.

| # | Case | Resolution |
|---|---|---|
| 1 | **`first_kill_only` needs stored state**, contradicting §10's "no stored counter" claim | `SpawnGroupLootState` named explicitly (§4.2); the *epoch key* is derived, the *claimed set* is not, and the over-strong claim is corrected |
| 2 | **`qty` rolls 0** from `QtyRange { min: 0, .. }` | skipped, not awarded (§4.1 rule 1) |
| 3 | **Group scaling multiplies progression** — 12× advancement for a 12-strong camp | progression subjects are always `FlatOnce` (§4.1 rule 2) |
| 4 | **Progression award to an untracked victor** with no `actor_progression` row | dropped, not materialised — materialising would promote actors for unobserved fights (§4.1 rule 3) |
| 5 | **A defeated PC** — does the hostile side loot them? | no roll in V1; gear still drops via EF_001 cascade. Rolling would be PvP looting through the side door (§5, SPO-D7) |
| 6 | **Mutual wipe** — `entitled` is empty | claim exists but is vacuously unenforceable until expiry, then open to all (§7.1) |
| 7 | **Routed** — all hostiles fled | no finalisation, no loot (§5, SPO-D8) |
| 8 | **Cell destroyed before the claim expires** | claim dies with the cell; contents follow EF_001 §6.1. No special case (§7.1) |
| 9 | **Claim expiry under time dilation** | read against the cell's fiction clock, per SPN-A3 (§7.1) |
| 10 | **Camp unloaded and re-observed inside one epoch** → `claimed` lost | accepted, bounded by `budget_remaining`; recorded as **SPO-D10** (§4.2) |
| 11 | **Two encounters resolving in one cell** | two claims keyed by `encounter_id`; subjects cannot overlap (§7.1) |
| 12 | **An `ItemDefId` colliding with a `resource_kinds` id** would award down both paths | already rejected at canonical seed by PL_007 ITM-V10/ITM-C2; SPO-V7 is the commit-time assertion that it held (§13) |

## §15.1 — Open questions resolved (were SPO-QO1/QO2)

**SPO-QO1 — should unclaimed spoils decay? RESOLVED: no, and the reasoning is stronger than "simpler".**
The worry was cell litter. But decay requires a timer per item, which is the *one* thing the whole loot
design avoids — and it introduces a class of bug that is invisible until it is infuriating: a player who
leaves spoils to make a second trip returns to find them gone, with no in-fiction explanation. Persistent
world contents are also what makes a wipe recoverable (§6), which is a deliberate forgiveness property.
Litter is bounded in practice by `budget_remaining` (§10) and by the fact that spoils only generate where
something died. **Closed as won't-fix.** If a specific cell ever does accumulate visibly, that is a spawn
tuning problem (COMB_005), not a loot lifetime problem.

**SPO-QO2 — `MinEncounterRounds` or a damage-taken threshold as the trivial-kill guard? RESOLVED: keep
`MinEncounterRounds`, and the alternative is actively worse.** A damage-taken threshold sounds like a
better proxy for "was this a real fight", but it rewards *playing badly* — an efficient party that wins
without being hit would be denied the good drops, and the optimal strategy becomes deliberately taking
damage before finishing. Round count has no such perverse gradient: it measures how long the enemy
survived, which is a property of the *enemy*, not of how carelessly the player fought. **Closed.**

## §15.2 — Deferred (SPO-D1..D10)

See the §1 "V1 NOT shipping" table for SPO-D1..D9; **SPO-D10** (persisting `first_kill_only` across an
unload/re-observe inside one epoch) is added by §4.2. **No open questions remain.**

## §16 — Cross-references

- Audit finding — [`12_module_coverage_audit.md`](../../12_module_coverage_audit.md) AUD-F9
- **The seam this doc accepts** — [`PL_007`](../04_play_loop/PL_007_item.md) §8.5, `ItemOrigin::Loot`
- Taking spoils / carry cap — [`PL_007b`](../04_play_loop/PL_007b_inventory.md) §10.7, `CellItemView`
- Seed family + KO semantics — [`COMB_001`](COMB_001_combat_foundation.md) §4 (Q8), §6 (Q3)
- Death cascade (the other half of the pile) — [`EF_001`](../00_entity/EF_001_entity_foundation.md) §6.1
- Cell-owned fungibles — [`RES_001`](../00_resource/RES_001_resource_foundation.md) §4.2, §7.4
- Progression grants — [`PROG_001`](../00_progression/PROG_001_progression_foundation.md)
- Spawn groups + epochs (anti-farm key) — [`COMB_005`](COMB_005_encounter_spawning.md)
- World treasure (distinct) — [`TMP_006`](../00_tilemap/) · Mortality — [`WA_006`](../02_world_authoring/)
