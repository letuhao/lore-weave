# 16a — Ruleset Field Classification (RLS-Q3 sweep)

> **Status:** PROPOSAL — 2026-07-26. Annex to [`16_ruleset_loader_and_registry.md`](16_ruleset_loader_and_registry.md).
> **What this is:** every field of `_boundaries/02_extension_contracts.md` §2 `RealityManifest`, classified
> by side (RLS-A1), merge strategy (RLS-A4) and lowest permissible layer (RLS-A16 below).
> **Status of each row is PROPOSED, not decided** — the owning feature signs off, and the `_boundaries`
> §2 split lands only after sign-off. Rows marked ⚠ need a decision from their owner rather than a review.
> **Count: 65 top-level fields swept**, not the ~40 estimated in doc 16. One (`combat_seed_visible`)
> leaves the manifest entirely for platform config, along with 4 *sub-fields* of `tilemap_defaults`.
> The 64 that remain: **3 identity · 40 Ruleset · 20 WorldContent · 1 Provenance**.
> **The sweep changed the design in four places** (§2), and the follow-on mutability pass (§6)
> corrected two of `RLS-A17`'s own examples. That is the point of doing it before the split rather
> than during it.

---

## 1. What the sweep changed

Four findings that a per-field pass produced and a top-down design pass did not.

### 1.1 Two buckets are not enough — `authoring_metadata` breaks the digest

`authoring_metadata` (GEO_001b) carries `total_llm_cost_usd`, `total_llm_calls`, `iteration_count`,
`author_user_id`, `authoring_started_at`, `authoring_completed_at`. It is **provenance**: nothing in the
engine reads it, and it changes every time an author touches the reality.

Put it in the Ruleset and RLS-A13's content-addressing breaks in both directions — two realities with
byte-identical rules never dedupe (different `author_user_id`), and re-authoring produces a new digest,
hence a new epoch, hence a spurious *"the rules changed"* signal to every island, for a change that
altered no behaviour whatsoever.

> **RLS-A15 — There is a third side: `Provenance`. It is stored with the reality, excluded from the
> digest, and never reaches an island.** Any field whose value can differ between two behaviourally
> identical realities belongs here.

### 1.2 Operational knobs are mixed into game rules

Five fields are host/ops configuration wearing a manifest field's clothes:

| Field | Why it is not a rule |
|---|---|
| `tilemap_defaults.generation_timeout_seconds` | **wall-clock** |
| `tilemap_defaults.force_directed_max_wall_clock_seconds` | **wall-clock** |
| `tilemap_defaults.force_directed_max_iterations` | host budget, not world behaviour |
| `tilemap_defaults.single_thread` | host execution mode |
| `combat_seed_visible` | dev-mode RNG-seed exposure; affects nothing simulated |

Wall-clock bounds inside a determinism-pinned, digest-addressed artifact is a category error twice
over: the value is nondeterministic by nature, and raising a timeout would register as a **rules
change** with a new epoch. These belong with `multiverse.*` in
[`03_multiverse/09_config_and_refs.md`](03_multiverse/09_config_and_refs.md) — platform config, per
deployment, not per reality.

> **RLS-D13 — Nothing wall-clock-derived may enter the Ruleset.** The remaining `tilemap_defaults`
> fields (`grid_size_per_tier`, `default_template_per_tier`, `default_water_content`,
> `default_monster_strength`, `llm_enabled`, `skip_tier`) are genuine rules and stay. The struct splits.

### 1.3 Some fields cannot be declared above the `reality` layer

`progression_actor_overrides` is `HashMap<ActorRef, …>`. `npc_desires` is `HashMap<NpcId, …>`.
`social_initial_distribution` is `HashMap<ActorRef, i64>`. `canonical_title_holdings` names actors.

A **preset cannot know actor IDs.** A `wuxia` preset declaring `progression_actor_overrides` is not
merely unhelpful, it is unsatisfiable — the IDs it would reference do not exist until a reality is
seeded. Left unstated, the loader would happily merge a preset layer whose keys can never resolve, and
the failure would surface later as a referential-integrity error naming the wrong culprit.

> **RLS-A16 — Every field declares a *lowest permissible layer*.** Instance-keyed fields are
> `reality`-or-below; a declaration at a higher layer is a **load error at the layer that declared
> it**, not a dangling reference discovered three stages later.

### 1.4 The split axis is locality, not read-time

Doc 16 §1 framed the split as *"a field is a Rule if `apply()` can read it."* The sweep shows that is
almost right and imprecise in a way that matters. `PlaceDecl` carries `combat_safety` and
`time_flow_rate_override` — unambiguously rules, read at runtime — yet `places` is WorldContent,
because there is one per cell and an island needs exactly one of them.

> **RLS-D14 — The axis is cardinality, not read-time.** *Ruleset* = O(1) in world size, hydrated
> whole, identical for every island in the reality. *WorldContent* = O(cells) or O(actors), loaded per
> channel with that channel. A rule-shaped field living inside a per-channel decl is **correct**, not a
> mis-classification — it arrives with its channel and is scoped to it.

This also resolves the `canonical_factions` boundary case that doc 16 §2 flagged and left open: it is
O(factions) but factions are *reality-wide* and every island may need any of them, so it is O(1) in
**world size**. Factions are Ruleset. Faction *memberships* are O(actors) — Content.

---

## 2. Three defects found in passing

Not classification questions; genuine pre-existing bugs the sweep surfaced.

| | Defect | Why layering makes it worse |
|---|---|---|
| **CLS-1** | **`canonical_pcs` is declared twice** — as a top-level field (§2 line 596) *and* as `OnboardingConfigDecl.canonical_pcs` (line 560), with the same stated validation (*"subset of `canonical_actors[kind=Pc]`"*) in both places. | Today it is a redundancy. Under a merge stack it is a **divergence**: a preset can set one and a reality the other, and PO-C2 validates whichever the loader happens to read. → **PO_001 owner: delete one.** The nested one looks correct; the top-level one looks like a leftover. |
| **CLS-2** | **`personality_archetypes` carries a derived cardinality constraint** — IDF_003 requires `opinion_modifier_table` to hold **12×12 = 144 entries**, *"required per PRS-Q9 LOCKED"*. | `UnionByIdOverride` is per-archetype. A reality adding a 13th archetype silently makes every *inherited* archetype's table incomplete (144 ≠ 169), and no per-entry merge rule can notice. → Needs a **post-merge completion rule**: after merge, every archetype's table is filled against the merged archetype set, absent pairs defaulting to `0` (neutral). Recorded as **RLS-D15**. |
| **CLS-3** | **`npc_desires` is superseded and still present.** ACT_001's 2026-04-27 unification moved desires into `CanonicalActorDecl.chorus_metadata.desires` (*"renamed from NpcDesireDecl (NPC_003 ownership transfer)"*), but the top-level `npc_desires: HashMap<NpcId, Vec<NpcDesireDecl>>` was never removed. | Two declaration sites for the same data, one of them stale, about to be given independent merge semantics. → **ACT_001 / NPC_003 owners: confirm removal.** |

---

## 3. The classification

**Side:** `R` Ruleset · `C` WorldContent · `P` Provenance · `X` platform config, remove from manifest · `I` identity.
**Strategy:** per RLS-A4 — `Replace` = `ReplaceWhole` · `Union` = `UnionByIdOverride` · `Clamp{op}` = `NumericClamp` · `Forbid` = `Forbidden`.
**Floor:** lowest layer that may declare it (RLS-A16) — `eng` engine_default · `pre` preset · `book` · `rea` reality.

### 3.1 Identity

| Field | Owner | Side | Strategy | Floor |
|---|---|---|---|---|
| `reality_id` | — | I | `Forbid` | rea |
| `book_canon_ref` | — | I | `Forbid` | book |
| `schema_version` | — | I | `Forbid` | eng |

### 3.2 Ruleset — 40 fields

| Field | Owner | Strategy | Floor | Note |
|---|---|---|---|---|
| `lex_config` | WA_001 | `Replace` | pre | genre-defining; the preset layer's natural home |
| `contamination_allowances` | WA_002 | `Union` | pre | |
| `mortality_config` | WA_006 | `Replace` | pre | |
| `travel_defaults` | MAP_001 | `Replace` | pre | |
| `resource_kinds` | RES_001 | `Union` | pre | ⚠ `def_id` collision with `item_defs` rejects bootstrap (ITM-V10) — **cross-field, must run post-merge** (§4) |
| `currencies` | RES_001 | `Union` | pre | |
| `vital_profiles` | RES_001 | `Union` | pre | keyed by actor-class; degrades to DF7 `MaxHp`/`MaxStamina` base |
| `producers` | RES_001 | `Union` | pre | keyed `place_type` |
| `prices` | RES_001 | `Union` | pre | keyed `kind`; gains item entries from `ItemDefDecl.price` |
| `cell_storage_caps` | RES_001 | `Union` | pre | keyed `PlaceTypeRef` |
| `cell_maintenance_profiles` | RES_001 | `Union` | pre | keyed `PlaceTypeRef` |
| `desires_prompt_top_n` | NPC_003 | `Replace` | pre | |
| `races` | IDF_001 | `Union` | pre | the canonical preset example (wuxia 5 / modern 1 / scifi 3) |
| `languages` | IDF_002 | `Union` | pre | |
| `personality_archetypes` | IDF_003 | `Union` + **completion rule** | pre | ⚠ CLS-2 / RLS-D15 |
| `origin_packs` | IDF_004 | `Union` | pre | |
| `ideologies` | IDF_005 | `Union` | pre | |
| `canonical_factions` | FAC_001 | `Union` | pre | O(1) in world size → Ruleset per RLS-D14; resolves the doc 16 §2 boundary case |
| `canonical_titles` | TIT_001 | `Union` | pre | `TitleDecl` is policy (succession / multi-hold / vacancy), engine-consulted at runtime |
| `progression_kinds` | PROG_001 | `Union` | pre | ⚠ five `f32` fields → fixed-point (RLS-A8) |
| `progression_class_defaults` | PROG_001 | `Union` | pre | keyed `ActorClassRef` — a class *is* preset-knowable |
| `strike_formula` | PROG_001 | `Replace` | pre | reduced to `damage_floor` + `post_damage_hooks`; terms moved to DF7 |
| `tier_capacity_caps` | AIT_001 | `Clamp{Min}` | pre | a lower layer may impose a ceiling a higher one cannot raise |
| `untracked_templates` | AIT_001 | `Union` | pre | keyed `place_type` |
| `cell_untracked_density` | AIT_001 | `Union` | pre | keyed `PlaceTypeRef` |
| `tier_roster_caps` | AIT_001 | `Replace` | pre | prompt-budget caps |
| `minor_behavior_scripts` | AIT_001 | `Union` | pre | keyed `actor_class` |
| `tilemap_templates` | TMP_001 | `Union` | pre | keyed `ChannelTier` |
| `tilemap_defaults`ᐟ | TMP_001 | `Replace` | pre | ⚠ **splits** — 4 ops fields leave per RLS-D13 |
| `combat_disparity_cap` | COMB_001 | `Clamp{Min}` | pre | anti-grief: a preset floor a reality must not raise |
| `combat_mortality_config` | COMB_001 | `Replace` | pre | |
| `initiative_system` | COMB_001 | `Replace` | pre | V1 fixed = HSR action value |
| `side_default_setup` | COMB_001 | `Replace` | pre | |
| `stat_slots` | DF07 | `Union` | pre | keyed `StatSlot`; closed engine set |
| `stat_archetypes` | DF07 | `Union` | pre | keyed `ActorClassRef` |
| `stat_tuning` | DF07 | `Replace` | pre | |
| `item_defs` | PL_007 | `Union` | pre | System-tier per ITM-A1 — admin-write only, which the layer model already expresses |
| `equip_slot_profile` | PL_007 | `Replace` | pre | |
| `inventory_defaults` | PL_007b | `Replace` | pre | |
| `max_pc_count` *(PCS-D3, V1+)* | PCS_001 | `Replace` | pre | reserved |

### 3.3 WorldContent — 20 fields

| Field | Owner | Cardinality | Floor | Note |
|---|---|---|---|---|
| `starting_fiction_time` | PL_001 | O(1) | book | O(1) but seed-once and never re-read; Content by RLS-D1 |
| `root_channel_tree` | PL_001 | O(channels) | book | |
| `canonical_actors` | ACT_001 | O(actors) | book | carries TDIL `initial_clocks`, PCS `body_memory_init`, ACT `chorus_metadata` |
| `places` | PF_001 | O(cells) | book | carries per-cell **rules** (`combat_safety`, `time_flow_rate_override`) — correct per RLS-D14 |
| `map_layout` | MAP_001 | O(channels) | book | carries per-channel `time_flow_rate` (TDIL-1) |
| `scene_skeleton_overrides` | CSC_001 | O(cells) | book | |
| `initial_resource_distribution` | RES_001 | O(actors) | rea | |
| `social_initial_distribution` | RES_001 | O(actors) | **rea** | instance-keyed — RLS-A16 |
| `npc_desires` | NPC_003 | O(actors) | **rea** | ⚠ CLS-3 — superseded, expect removal |
| `canonical_dynasties` | FF_001 | O(dynasties) | book | |
| `canonical_family_relations` | FF_001 | O(actors) | **rea** | instance-keyed |
| `canonical_faction_memberships` | FAC_001 | O(actors) | **rea** | instance-keyed |
| `canonical_actor_faction_reputations` | REP_001 | O(actors×factions) | **rea** | instance-keyed |
| `canonical_title_holdings` | TIT_001 | O(actors) | **rea** | instance-keyed |
| `canonical_sessions` | DF05_001 | O(sessions) | book | |
| `onboarding_config`ᐟ | PO_001 | O(1) | book | ⚠ **splits** — see §3.5 |
| `canonical_pcs` | PO_001 | O(actors) | **rea** | ⚠ CLS-1 — duplicate declaration site |
| `progression_actor_overrides` | PROG_001 | O(actors) | **rea** | instance-keyed — a preset cannot know these IDs |
| `continent_geometries` | GEO_001 | O(continents) × huge | book | `CreativeSeed` + append-only `GeographyDelta` chain; the largest single payload |
| `initial_item_distribution` | PL_007 | O(actors) | rea | |

### 3.4 Provenance — 1 field

| Field | Owner | Note |
|---|---|---|
| `authoring_metadata` | GEO_001b | RLS-A15 — stored, excluded from digest, never reaches an island |

### 3.5 Fields that split

Three structs carry both sides and must be divided at the `_boundaries` edit:

```
tilemap_defaults  ->  Ruleset:  grid_size_per_tier · default_template_per_tier
                                default_water_content · default_monster_strength
                                llm_enabled · skip_tier
                      Platform: generation_timeout_seconds
                                force_directed_max_wall_clock_seconds
                                force_directed_max_iterations · single_thread

onboarding_config ->  Ruleset:  modes_enabled · ai_assistant_enabled · onboarding_skin
                                tutorial_steps
                      Content:  canonical_pcs (CLS-1) · default_spawn_cell

combat (§2.Y)     ->  Ruleset:  disparity_cap · mortality_config · initiative_system
                                side_default_setup
                      Platform: combat_seed_visible
```

`canonical_factions` was expected to be the fourth and is not — RLS-D14 keeps `FactionDecl` whole on
the Ruleset side, since a faction's roster is O(1) in world size and its `roles` / `default_relations`
/ `requires_ideology` are all engine-consulted.

---

## 4. Post-merge validators

Nine constraints cannot be evaluated during a per-field merge because they span fields. They run after
the full merge, in the RLS-A9 topological order, and they are the reason that order has to exist.

| # | Constraint | Origin | Fails with |
|---|---|---|---|
| 1 | `item_defs.def_id` ∩ `resource_kinds.kind_id` = ∅ | ITM-V10 / ITM-C2 | `item.def_id_collides_resource_kind` |
| 2 | every `personality_archetypes` pair has an `opinion_modifier_table` entry | CLS-2 / RLS-D15 | completion rule fills with `0`; **no** rejection |
| 3 | `FactionDecl.requires_ideology` ⊆ `ideologies` | FAC_001 | `faction.ideology_unknown` |
| 4 | `TitleBinding::Faction` ⊆ `canonical_factions` | TIT-C4 | `title.binding.faction_unknown` |
| 5 | `TitleBinding::Dynasty` ⊆ `canonical_dynasties` | TIT-C5 | `title.binding.dynasty_unknown` |
| 6 | `StatTerm.kind_id` ⊆ `progression_kinds` | DF07 | `stat.term_kind_unknown` |
| 7 | `ItemDefDecl.grants_ability` ⊆ `ability_defs` | ABL_001 | `item.ability_unknown` |
| 8 | `StatSlotDecl` per-mille slots clamp within `0..=1000` | DF7-A11 | `stat.slot_range_invalid` |
| 9 | `stat_tuning`: `speed_per_tile ≥ 1` · `max_move ≥ 1` · `base_move ≤ max_move` | DF07 §2.Z | `stat.tuning_invalid` |

Constraints 3–7 are **cross-side** — a Ruleset field referencing another Ruleset field — which is what
makes them evaluable at load. Note by contrast what is *not* here: `OnboardingConfigDecl.default_spawn_cell ∈ places`
(PO-C3), `canonical_pcs ⊆ canonical_actors[kind=Pc]` (PO-C2), `CanonicalActorDecl.spawn_cell ∈ places`
(ACT_001). All three reference **WorldContent**, which by RLS-A1 is not loaded at ruleset-resolution
time.

> **RLS-Q8 (new) — Content-referencing validators need a second gate.** They cannot run at ruleset
> resolution and they must not wait for a cell to go Hot. The natural home is a **seed-time** pass at
> reality bootstrap, after WorldContent lands and before the first session — a third validation time
> alongside load-time (RLS-A10) and admission. This is a gap the sweep opened, not one it closed.

---

## 5. Ruleset size estimate

Sanity-checking RLS-A1's *"hydrate the whole Ruleset into every island"*, using the presets the feature
docs describe (wuxia is the largest):

| Group | Entries | Rough bytes |
|---|---|---|
| identity ×5 (races, languages, ideologies, archetypes, origin packs) | 5 + 4 + 5 + 12 + 0 | ~14 KB — archetypes dominate at 144 matrix entries |
| factions + titles | 5 + 12 | ~8 KB |
| progression kinds | ~6 kinds, one with 24 tiers | ~12 KB |
| stat slots + archetypes + tuning | 10 + ~8 | ~4 KB |
| item defs | ~50–200 | ~40 KB |
| resource/economy (kinds, currencies, prices, producers, caps) | ~30 | ~8 KB |
| combat + AIT + tilemap + misc | — | ~6 KB |
| **total** | | **~90 KB** |

~90 KB per reality, interned by digest across every island of that reality and across every reality
sharing a preset. A node hosting 40 realities with distinct rules carries ~3.6 MB. Hydrating whole is
comfortably affordable, which is the assumption RLS-A1 rests on and had not been checked.

The number that would have broken it is `continent_geometries` — `Megaplanet` scale is ~16 384 cells,
and `places` + `map_layout` + `scene_skeleton_overrides` scale with it. Those are all WorldContent.
**The split is load-bearing at exactly the point the estimate shows it to be.**

---

## 6. Mutability class — all 40 Ruleset fields (RLS-Q9)

Per RLS-A17, the deciding question is **not** importance. It is: *does stored state reference this
declaration by ID?* If yes, an author cannot redefine or remove it without orphaning rows.
`Frozen` is narrower still — reserved for rules whose change would **falsify past events**.

Applying it per field corrected **two of RLS-A17's own illustrative examples** (§6.2).

### 6.1 Assignment

**`Tunable` — 24 fields.** Nothing stored points at them; change re-derives, never orphans.

`travel_defaults` · `contamination_allowances` · `vital_profiles` · `producers` · `prices` ·
`cell_storage_caps` · `cell_maintenance_profiles` · `desires_prompt_top_n` ·
`progression_class_defaults` · `strike_formula` · `tier_capacity_caps` · `untracked_templates` ·
`cell_untracked_density` · `tier_roster_caps` · `minor_behavior_scripts` · `tilemap_defaults`ᐟ ·
`combat_disparity_cap` · `combat_mortality_config` · `side_default_setup` · `stat_slots` ·
`stat_archetypes` · `stat_tuning` · `inventory_defaults` · `max_pc_count`

Three warrant a note:
- **`progression_class_defaults`** is read *only when an actor is created*, to seed initial values.
  Changing it cannot disturb an existing actor.
- **`untracked_templates`** is safe precisely because AIT-A8 makes Untracked NPCs *the absence of an
  aggregate*. There is no stored row to orphan — the quantum-observation model pays off again.
- **`vital_profiles`** is keyed by actor-class and `vital_pool` stores current/max, not a profile ref.
  Removing a profile degrades the class to engine default; nothing dangles.

**`AdditiveOnly` — 13 fields.** Append freely; redefinition and removal are blocked, removal
downgrading to deprecation.

| Field | Referenced by |
|---|---|
| `resource_kinds` | `resource_inventory` balances, by `kind_id` |
| `currencies` | balances |
| `races` | `actor_core.race_id` |
| `languages` | `SoulLayer.native_language` / `BodyLayer.native_language`, `actor` language sets |
| `personality_archetypes` | actor archetype ref **+** the 144-entry matrix (CLS-2 / RLS-D15) |
| `origin_packs` | `actor_origin.origin_pack_id` |
| `ideologies` | `actor_ideology_stance.stances` |
| `canonical_factions` | `actor_faction_membership`, `TitleBinding::Faction` |
| `canonical_titles` | `actor_title_holdings.title_id` |
| `progression_kinds` | `actor_progression` instances, by `kind_id` — **the canonical case** |
| `item_defs` | every item instance, by `def_id` |
| `equip_slot_profile` | equipped items reference slot names |
| `tilemap_templates` | `TilemapBorn { template_id }` records the template a tilemap was born from |

**`Frozen` — 3 fields.** Change would falsify past events.

| Field | What a change would rewrite |
|---|---|
| `lex_config` | the world's axioms — which past turns were legitimately accepted or rejected. The genuine L1 analogue. |
| `mortality_config` | switching permadeath → respawn retroactively changes what **every past death meant** |
| `initiative_system` | turn-order semantics. V1 has exactly one value (HSR action value), so `Frozen` costs nothing now and forecloses a V1+ footgun. |

### 6.2 Two corrections to RLS-A17's examples

Writing the axiom top-down produced two illustrative assignments the per-field pass overturns. Both
are recorded rather than quietly fixed, because both show the axiom working as intended.

- **`stat_slots` is `Tunable`, not `AdditiveOnly`.** RLS-A17 listed it among the ID-keyed registries.
  It is not one: `StatSlot` is a **closed engine enum**, so an author declares decls for slots that
  already exist rather than minting IDs. Removing a decl degrades that slot to its engine default —
  a safe fallback, not an orphan. The ID-keyed constraint that *does* apply lives one level down, on
  `progression_kinds`, which `StatSlotDecl.terms` reference.
- **`canonical_factions` and `canonical_titles` are `AdditiveOnly`.** RLS-A17 named them but the
  reason is worth pinning: `TitleBinding::Faction` and `actor_title_holdings` reference both by ID,
  so `VacancySemantic::Destroyed` (*"RealityManifest entry removed for fallen empires"*, TIT_001 Q9)
  is **already a deprecation in disguise** — the title stops being grantable while historical holdings
  keep resolving. TIT_001 reached RLS-A17's answer independently, for one field, two months earlier.

### 6.3 Forge tier, derived

Class determines S5 tier with no further judgement (RLS-D16):

| Action | Class | Tier |
|---|---|---|
| edit | `Tunable` | ordinary Forge action, audit only |
| append | `AdditiveOnly` | **Tier 2 Griefing** — 50+ char reason |
| deprecate | `AdditiveOnly` | **Tier 1 Destructive** |
| any edit | `Frozen` | rejected at the validator; never tiered |

---

## 7. Sign-off

Each owner reviews their own rows. A row is decided when its owner accepts side + strategy + floor; the
`_boundaries` §2 split lands when all are decided.

| Owner | Rows | Needs a decision, not just review |
|---|---|---|
| PO_001 | 2 | **CLS-1** — delete one `canonical_pcs`; split `onboarding_config` |
| IDF_003 | 1 | **CLS-2** — accept the RLS-D15 completion rule |
| ACT_001 / NPC_003 | 2 | **CLS-3** — confirm `npc_desires` removal |
| TMP_001 | 2 | split `tilemap_defaults`; accept 4 fields leaving for platform config |
| COMB_001 | 5 | `combat_seed_visible` → platform; accept `Clamp{Min}` on disparity cap |
| PROG_001 | 4 | `f32` → fixed-point (RLS-A8); PROG-D6 is stale |
| RES_001 | 8 | review only |
| DF07 · PL_007 · PL_007b | 6 | review only |
| AIT_001 | 5 | review only |
| FAC_001 · TIT_001 · FF_001 · REP_001 | 7 | FAC_001: accept `canonical_factions` as Ruleset (RLS-D14) |
| GEO_001 / 001b | 2 | accept `authoring_metadata` as Provenance (RLS-A15) |
| WA_001/002/006 · MAP_001 · PF_001 · CSC_001 · PL_001 · DF05_001 · PCS_001 | 12 | review only |
