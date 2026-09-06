# 16 — Ruleset Loader & Registry (design)

> **✅ CORRECTED 2026-07-26 — integration rows added; design conclusions confirmed** (per the
> same-day banner + [`19_reconciliation_register.md`](19_reconciliation_register.md) §12b). The
> sweep **confirmed the central finding** — *"replay cannot reconstruct the rules it ran under"* is
> real, and RLS-A13 is a genuine repair. What was wrong was the **integration mechanics**, now
> fixed:
>
> - **§13** gains the missing rows: `07_event_model/06_per_category_contracts.md` (envelope field +
>   `event_schema_version` 1 → 2) · `11_schema_versioning.md` (permanent upcaster; **legacy
>   sentinel decided** — pre-bump events get `digest = RULESET_UNKNOWN`, explicitly
>   non-replayable-exactly) · `_boundaries/02_extension_contracts.md` §4 + the ownership matrix
>   (`RulesetEpochActivated`, **owner = WA_003 Forge** per §12b REC-29) · the EVT-L16 visibility
>   declaration (internal-filtered, not user-visible) · the EVT-A9/EVT-A10/EVT-L18 amendments.
>   Every LOCKED-file change rides the **REC-53 AMEND bundle**, pending — none is applied here.
> - **RLS-A14** corrected in place (§9): producer is **Forge/admin-cli via the S5 chokepoint**
>   (EVT-P8 forbids everything else); the switch is **N committed durable events, one per channel**,
>   never a bare `QueuedInput`.
>
> §16a (the field classification) was and remains **unaffected** — it touches no EVT contract.

> **Status:** DRAFT — 2026-07-26. Opens and closes the design half of **AUD-F14**.
> **Prefix:** `RLS-*` (registered 2026-07-26; axioms `RLS-A1..A18`, invariant `RLS-I1`, decisions
> `RLS-D1..D23`, questions `RLS-Q1..Q10`).
> **ALL open questions RESOLVED 2026-07-26** — `RLS-Q1..Q10`, §14. **Six of the ten were answered by a
> mechanism that already existed**: the S5 Forge tier discipline · `dp-kernel::upcaster` ·
> `GeographyDelta` + aggregate versioning · `RealityBootstrapper` · the CLAUDE.md tenancy tiers.
> Two design self-corrections are recorded rather than quietly folded in, because both were caught by
> checking code instead of reasoning from the docs: **`RLS-A18` was withdrawn and rewritten** (§2.1 —
> `places`/`map_layout` edits target *aggregates*, so the `content_version` it invented already exists),
> and **`RLS-A17`'s `stat_slots` example was wrong** (§16a §6.2 — `Tunable`, not `AdditiveOnly`).
> **Nothing blocks build-order steps 1–4.** Remaining work is owner sign-off on
> [`16a`](16a_ruleset_field_classification.md), which is review rather than analysis.
> **Annex:** [`16a_ruleset_field_classification.md`](16a_ruleset_field_classification.md) — the `RLS-Q3`
> sweep over all **64** manifest fields. It amended this doc in four places (`RLS-A15` Provenance ·
> `RLS-A16` layer floors · `RLS-D13` no wall-clock in rules · `RLS-D14` the axis is cardinality) and
> opened `RLS-Q8`.
> **Origin:** a read of `chaos-backend-service`'s `actor-core` **Configuration Hub**
> (`ConfigurationProvider` → `Registry` → `Combiner` → `Aggregator`, plus `system_ids.yaml` /
> `dimensions.yaml` / `bucket_priorities.yaml` / `cap_layers.yaml`) against our own design, asking
> whether a platform that promises *many realities, each with its own progression system* has anywhere
> to put that promise.
> **Finding: it does not.** `RealityManifest` is a ~600-line struct whose declared owner is
> *"⚠ Currently unowned"*, composed by an ingestion pipeline that no document specifies, resolved by a
> single rule (*"omit the field → the feature default applies"*), reaching a simulation core whose
> `apply()` signature has no parameter it could arrive through.
> **PO decisions 2026-07-26 (4/4):** split Ruleset from WorldContent · early-bind presets ·
> add `Domain::Rules` · content-addressed digest. All four are folded in below.
> **Not yet done:** `_boundaries/` registration (lock-gated; §14), and the `IF_001` naming question
> (`RLS-Q1`).

---

## 1. The finding that decides the shape

`RealityManifest` holds two populations with nothing in common but a struct.

| | Examples | Size | Who reads it | Change cadence |
|---|---|---|---|---|
| **Rules** | `stat_slots`, `races`, `languages`, `ideologies`, `currencies`, `resource_kinds`, `strike_formula`, `combat_disparity_cap`, progression kinds, item defs, loot tables, ability defs | KB — bounded by author intent | **every** `apply()`, on **every** island | rare, and must change **atomically across the whole reality** |
| **World content** | `places: Vec<PlaceDecl>` (one per cell), `map_layout: Vec<MapLayoutDecl>` (one per channel), `canonical_actors`, `canonical_family_relations`, `canonical_factions`, `tilemap_templates`, `initial_resource_distribution` | MB–GB — scales with world size | **one** island, for **its own** channel | seeded once, then superseded by L3 events |

Treating these uniformly is wrong in both directions. Hydrating `places` into every island wastes
memory proportional to `cells × islands`. Fetching `stat_slots` lazily puts an I/O call inside a
function whose contract is *"no I/O, no ambient clock"*
([`14_sim_core_spec.md` §4.0](14_sim_core_spec.md)).

`chaos-backend` met a weaker form of this and answered it by directory —
`element-core`'s `MultiDirectoryConfigLoader` splits `elements/ · hybrid/ · central/ · mastery/`.
Ours has no partitioning axis at all, so the requirement cannot even be *stated*.

> **RLS-A1 — Rules and content are two artifacts with two loaders.** `RealityManifest` is split into
> **`RealityRuleset`** (small, immutable, versioned, fully hydrated per island) and **`WorldContent`**
> (bulk, seed-once, loaded per-channel on Cold→Hot).
>
> **Amended by RLS-D14 after the §16a sweep:** the axis is **cardinality, not read-time**. Ruleset =
> O(1) in world size, identical for every island; WorldContent = O(cells) / O(actors), loaded with its
> channel. The first formulation ("a field is a Rule if `apply()` can read it") mis-files `PlaceDecl`,
> which carries genuinely runtime-read rules — `combat_safety`, `time_flow_rate_override` — one per
> cell. A rule-shaped field inside a per-channel decl is correct: it arrives with its channel and is
> scoped to it.

> **RLS-A15 — There is a third side, `Provenance`** — stored with the reality, **excluded from the
> digest**, never sent to an island. Discovered by the sweep: `authoring_metadata` carries
> `author_user_id`, `total_llm_cost_usd` and authoring timestamps, so including it would mean two
> behaviourally identical realities never dedupe, and re-authoring would emit a spurious epoch for a
> change that altered nothing. Test: *can this differ between two behaviourally identical realities?*
> → Provenance.

> **RLS-D13 — Nothing wall-clock-derived may enter the Ruleset**, and host/ops knobs are not rules.
> The sweep found five (`generation_timeout_seconds`, `force_directed_max_wall_clock_seconds`,
> `force_directed_max_iterations`, `single_thread`, `combat_seed_visible`). A wall-clock bound inside a
> determinism-pinned artifact is a category error twice over — nondeterministic by nature, and raising
> a timeout would register as a *rules change* with a new epoch. They belong with `multiverse.*`
> platform config.

> **RLS-A16 — Every field declares a *lowest permissible layer*.** Instance-keyed fields
> (`HashMap<ActorRef, …>`, `HashMap<NpcId, …>`) are `reality`-or-below: **a preset cannot know actor
> IDs**, so a preset-layer declaration is unsatisfiable, not merely unhelpful. Violation is a load
> error *at the declaring layer*, which is what makes the diagnostic name the right culprit instead of
> surfacing three stages later as a dangling reference.

> **RLS-A2 — The split is a *classification*, not a rewrite.** Every existing `_boundaries` §2 field
> keeps its shape, its owner and its I14 additive guarantee. What changes is that each row gains a
> side. Features do not redesign anything; they answer one question about each field they own.

---

## 2. The two artifacts

```
RealityRuleset                              WorldContent
  (hot · ~KB · versioned · immutable)         (cold · ~MB-GB · per-channel)
──────────────────────────────────────      ─────────────────────────────────────
  progression_kinds   stat_slots              places[]        map_layout[]
  races  languages  ideologies                canonical_actors[]
  personality_archetypes                      canonical_family_relations[]
  resource_kinds  currencies  prices          canonical_dynasties[]  factions[]
  vital_profiles  stat_archetypes             tilemap_templates
  strike_formula  combat_*  loot_tables       initial_resource_distribution[]
  ability_defs  item_defs  status_table       social_initial_distribution
  lex_config  mortality_config                scene_skeleton_overrides
  travel_defaults  tilemap_defaults           onboarding_config.canonical_pcs
──────────────────────────────────────      ─────────────────────────────────────
  Arc<RealityRuleset> per (reality, epoch)    read at bootstrap AND at every Cold->Hot
  digest pinned into the event envelope       per-channel content_version (RLS-A18)
  hydrated into every island of the reality   mutation is events, never in-place
```

> **RLS-D1 — Ambiguity resolves toward WorldContent.** If a field's side is unclear, it is content
> until a consumer demonstrates a hot-path read. Mis-filing a rule as content costs one lazy load;
> mis-filing content as a rule costs memory on every island in the reality.

**`canonical_factions` was the boundary case this section originally flagged**, on the reasoning that a
faction's *existence* is seed data while its role ladder is a rule. RLS-D14 settles it the other way:
factions are O(1) in world size and every island may need any of them, so `FactionDecl` stays whole on
the Ruleset side. Faction *memberships* are O(actors) and are Content. Three structs do genuinely
split — `tilemap_defaults`, `onboarding_config`, and the COMB_001 combat group — all itemised in
[§16a §3.5](16a_ruleset_field_classification.md).

**Size check (§16a §5), since RLS-A1 rests on it:** a wuxia-preset Ruleset is **~90 KB**, interned by
digest across every island of the reality and every reality sharing the preset. A node hosting 40
realities with distinct rules carries ~3.6 MB. Hydrating whole is affordable. The payload that would
have broken it is `continent_geometries` at `Megaplanet` scale (~16 384 cells), together with `places`
and `map_layout` — all WorldContent. The split is load-bearing at precisely the point the estimate
shows it to be.

### 2.1 The manifest seeds aggregates; aggregates carry the mutable part (RLS-Q6 + RLS-Q10 — RESOLVED)

`RLS-Q6` asked whether WorldContent needs its own versioning *"or is seed-once + L3 supersession
enough."* Answering it took two passes, and the first was wrong in an instructive way.

**First pass (wrong).** WorldContent looked like it was *not* write-once: an island loads its cell's
place data at every Cold→Hot, possibly months later, and that data carries `combat_safety` and
`time_flow_rate_override` (with `time_flow_rate` on the map layout, TDIL-1) — runtime rules read long
after seeding. If they can change between two Cold→Hot transitions, two islands disagree about a
cell's rules, which is the exact failure the Ruleset design exists to prevent. That reasoning
concluded WorldContent needed an invented per-channel `content_version`.

**Second pass (correct), after checking `RLS-Q10` instead of delegating it.** Both write-paths exist —
and both are already events against **aggregates**, not edits to manifest rows:

| Path | Shape | Target |
|---|---|---|
| `Forge:EditPlace { place_id, edit_kind, before, after }` | **EVT-T8** + EVT-T3 delta | `aggregate_type=place` |
| `Forge:EditMapLayout { channel_id, edit_kind, before, after }` | **EVT-T8** + EVT-T3 delta | `aggregate_type=map_layout` |
| `Forge:EditGeographyDelta` | EVT-T8, append-only chain + GEO-V3 order gate | `world_geometry` |

`places` / `map_layout` in the manifest are **seed inputs**: consumed once at bootstrap to emit
`PlaceBorn` / `LayoutBorn`, which birth the aggregates. After bootstrap the manifest rows are never
read again — an island going Hot loads the **aggregate**, through `dp-kernel::load_aggregate`
(snapshot + delta events).

So the original "seed-once" framing was right about the manifest, and my correction over-corrected by
inferring mutability without checking *what* the mutation targets.

> **RLS-A18 (revised) — There are three tiers, and the third is not the loader's business.**
> **Ruleset** — reality-wide rules, not event-sourced, therefore digest-pinned (RLS-A13).
> **WorldContent** — manifest seed inputs, consumed once at bootstrap, genuinely write-once.
> **Runtime aggregates** — `place`, `map_layout`, `world_geometry`; event-sourced, versioned and
> replayable by machinery `dp-kernel` already ships. **No `content_version` needs inventing** — the
> aggregate version is it.

The pleasing consequence: **rule-replay determinism is covered by two complementary mechanisms with no
gap between them.** Reality-wide rules aren't event-sourced, so they need digest-pinning. Per-channel
rules *are* event-sourced, so replaying the aggregate reconstructs them exactly — a stronger guarantee
than digest-pinning, obtained for free. The per-cell rule fields that triggered the first pass' alarm
are the best-covered rules in the system.

This makes six of the eight opening questions answered by mechanisms that already existed.

---

## 3. The provider stack

Chaos's registry is a priority-ordered list of `ConfigurationProvider`s. We adopt the shape and fix
the layer set:

| Priority | Layer | Provided by | Mutable after reality creation? |
|---|---|---|---|
| 0 | `engine_default` | shipped artifact in the engine binary | no — changes with a deploy |
| 10 | `preset` | authoring-time template (`wuxia` / `modern` / `scifi`) | no — see RLS-A3 |
| 20 | `book` | the book's authored manifest contribution | no |
| 30 | `reality` | this reality's own overrides | no |
| 40 | `forge_override` | live author edit via `Forge:*` admin action | **yes — and it is an event** (§9) |

**The preset layer is the one that does not exist today.** It is described in prose across at least
six features — IDF_001 *"Wuxia ships 5 races; Modern 1; Sci-fi 3"*, IDF_002 4 languages, IDF_003
*"12 archetypes universal across all reality presets"*, FAC_001 5 sects, plus PROG_001 and RES_001 —
and in zero types. Six documents describe a layer the schema cannot represent.

> **RLS-A3 — Presets are authoring-time templates, resolved once (early binding).** At reality
> creation the stack is resolved top-to-bottom, validated, normalized, hashed, and stored as an
> **immutable resolved ruleset**. A later edit to the `wuxia` preset never touches a reality that
> already exists. Replay-safety is then structural rather than procedural: there is no path by which a
> reality's rules change without an event in its own log.

The accepted cost, recorded so it is a decision and not a discovery: **a balance fix cannot be shipped
to 200 live realities.** Each must be re-bound explicitly. The `RebindPreset` admin action that would
do that in bulk is deferred (**RLS-D11**), and it is deferred *knowing* the demand for it will arrive
the first time a preset ships a broken loot table.

### 3.1 Presets are a scoped resource (RLS-Q7 — RESOLVED)

CLAUDE.md's tenancy tiers answer the ownership half outright, and the failure mode is the one that
section was written about — the canonical bug it cites is a **globally unique, user-mutable** row that
one user's edit changed for everyone.

> **RLS-D19 — Presets are a standard three-tier scoped resource.** *System* tier: the
> platform-shipped `wuxia` / `modern` / `scifi` presets — admin-authored, **read-only** to every
> regular user, who *clone* rather than edit. *Per-user* tier: a user's own preset, from a clone or
> from scratch. Constraint is `UNIQUE(owner_user_id, preset_id)`, never `UNIQUE(preset_id)`.

The versioning half dissolves under early binding (RLS-A3). Since a preset is read **only** at reality
creation, a preset edit can affect no existing reality — so preset history would exist purely to answer
*"what did this reality come from?"* And that question already has a strictly better answer: the
**resolved ruleset itself** is stored immutably and content-addressed. Reproducing a year-old reality
needs no preset archaeology; the exact bytes it resolved to are on disk.

> **RLS-D20 — No immutable preset version history in V1.** `preset_ref` + `preset_version` are recorded
> in **Provenance** (RLS-A15) so the lineage is legible. Full preset history is an authoring-convenience
> feature, not a correctness requirement — the third time early binding has paid for itself.

> **RLS-D2 — `engine_default` is an artifact, not prose.** Today every feature states its own defaults
> in its own document (*"Empty → Copper + Food/Water + Wood/Iron/Stone…"*), which makes
> "omit → default" unverifiable and untestable. `engine_default` becomes a real, versioned, committed
> artifact — chaos at least has `actor_core_defaults.yaml` — and the "engine default" claims scattered
> through the feature docs become assertions *against* it.

---

## 4. Merge algebra

Rule #4 of `_boundaries` §2 (*omit → feature default*) is the entire current resolution law. It is
sufficient for exactly two layers and breaks at three.

> **RLS-A4 — Every Ruleset field declares a merge strategy.** A `Vec<RaceDecl>` cannot carry the
> answer to "preset and reality both declared races," so the strategy lives beside the field in the
> contract, not in the type.

| Strategy | Meaning | Typical fields |
|---|---|---|
| `ReplaceWhole` | higher layer wins entirely; lower is discarded | `strike_formula`, `lex_config`, `mortality_config`, `travel_defaults` |
| `UnionById` | merge by stable ID; **collision is an error** | rarely correct — see RLS-D3 |
| `UnionByIdOverride` | merge by stable ID; higher layer's entry **replaces** the lower's | `races`, `languages`, `ideologies`, `progression_kinds`, `item_defs`, `ability_defs` |
| `NumericClamp{op}` | `Min`/`Max` across layers — a lower layer sets a bound a higher one cannot exceed | `combat_disparity_cap`, tier caps |
| `Forbidden` | field is single-layer only; a second declaration fails the load | `schema_version`, `reality_id` |

Chaos's `ConfigurationMergeStrategy` offers ten variants including `Sum`, `Average`, `Multiply` and
`Concat`. We deliberately take a subset.

> **RLS-D3 — No arithmetic merge strategies.** `Sum` / `Average` / `Multiply` across configuration
> layers make the resolved value depend on *how many layers happened to declare it*, which is
> unreviewable by an author and unstable under preset edits. Contribution-style arithmetic already has
> a home — DF7-A3's locked layer order over `StatModifier` — and that is *runtime* stacking of actor
> state, not *load-time* merging of declarations. Keeping the two apart is the point.

### 4.1 Subtraction

`UnionByIdOverride` can add and replace but cannot remove. *"The wuxia preset gives 5 sects, my
reality has 4"* is currently inexpressible, and every layered config system that omits this grows a
workaround later.

> **RLS-A5 — Removal is a tombstone, and tombstones are typed.** A higher layer may emit
> `Tombstone(id)` against a lower layer's entry. A tombstone against an ID that does not exist is a
> **load error, not a no-op** — silent no-op tombstones are how a typo becomes an un-diagnosable
> "why is that sect still here."

### 4.2 Open-ID collision

`ProgressionKindId`, `RaceId` and friends are open author strings, and the design currently holds two
opposite rules for the same symbol: PROG_001 permits `RaceId` collision **across** realities (same
string, different semantics), while a merge stack needs collision **within** a reality to mean
override.

> **RLS-A6 — Collision semantics are scoped: across realities, unrelated; within one resolution
> stack, override.** Both rules stand; they were never in conflict, only unstated. The registry key
> being `(reality_id, epoch)` (§6) is what keeps them apart.

### 4.3 Normalization — a stage nobody owns

DF7 already requires one, without assigning it: `StatTerm.weight` is *"declared as a decimal in the
manifest and stored/evaluated as milli"* (`1.5` → `1500`), because DF7-A4 forbids `f32` anywhere in
the stat path.

> **RLS-A7 — Normalization is a load stage, and the digest is computed over the normalized form.**
> Otherwise the same rules authored as `1.5` and `1.500` produce different digests and look like
> different rulesets to replay.

> **RLS-A8 — The resolved Ruleset is float-free.** All decimals normalize to fixed-point integers
> (milli / per-mille) at load. This closes a live cross-document contradiction: DF7-A4 and TDIL-A9
> both hold that *"floats in a replayed, event-sourced engine are a determinism liability"*, yet
> PROG_001 still declares `rate_per_train_unit: f32`, `difficulty_factor: f32`,
> `training_rate_factor: f32`, `min_damage_factor: f32` and `max_damage_factor: f32`. DF7 fixed the
> stat path and left the *training* path — which feeds replay just as directly — on floats.
> **→ PROG_001 closure item (§13).**

---

## 5. Resolution order and referential integrity

Ruleset fields reference each other densely: `FactionDecl.requires_ideology → ideologies`,
`TitleBinding::Dynasty → canonical_dynasties`, `OnboardingConfigDecl.default_spawn_cell → places`,
`ItemDefDecl.grants_ability → ability_defs`. Per-pair validators exist across
[`_boundaries/03_validator_pipeline_slots.md`](_boundaries/03_validator_pipeline_slots.md) and the
per-feature catalogs (C31, C32, TIT-C2..C7, SPN-V4, DF7-V6). What does not exist is an **order**.

With one layer this was harmless. With five, a reality that overrides `ideologies` can orphan a
preset's factions, and which validator notices first is arbitrary.

> **RLS-A9 — Resolution runs in declared dependency order, and the graph is acyclic by
> construction.** Each Ruleset field declares which fields it references; the loader topologically
> sorts them, merges in that order, and runs each field's referential validators immediately after its
> own merge — so an error names the layer that caused it, not the layer that noticed it.

The sweep enumerated **nine post-merge constraints** that span fields and therefore cannot run during a
per-field merge — the concrete reason RLS-A9's order has to exist rather than being good hygiene. Full
list at [§16a §4](16a_ruleset_field_classification.md); the sharpest is
`item_defs.def_id ∩ resource_kinds.kind_id = ∅` (ITM-V10), which is *"what makes the ITM-A2
representation rule enforced rather than asserted"* and which no per-field merge can see.

> **RLS-D15 — A merge may need a completion rule, not just a strategy.** IDF_003 requires
> `personality_archetypes.opinion_modifier_table` to hold 12×12 = 144 entries. `UnionByIdOverride` is
> per-archetype, so a reality adding a 13th archetype silently leaves every *inherited* archetype's
> table incomplete (144 ≠ 169) and no per-entry rule can notice. After merge, tables are completed
> against the merged archetype set, absent pairs defaulting to `0` (neutral). Completion, not
> rejection — the author did nothing wrong.

### 5.1 Three validation times, and the third already has an actor (RLS-Q8 — RESOLVED)

PO-C2 (`canonical_pcs ⊆ canonical_actors[kind=Pc]`), PO-C3 (`default_spawn_cell ∈ places`) and
ACT_001's `spawn_cell ∈ places` all reference **WorldContent**, which by RLS-A1 is not loaded at
ruleset resolution. They cannot run at load time, and they must not wait for a cell to go Hot — by
then a player is already in it.

So there are three validation times, not two. The third turns out not to need an owner invented for
it: **`RealityBootstrapper` already exists.** It appears across PF_001, MAP_001, TMP_001 and GEO_001
as *"DP-Internal RealityBootstrapper (Synthetic actor)"*, emitting `PlaceBorn`, `LayoutBorn`,
`TilemapBorn` and `GeographyBorn` — running at exactly the required moment, after WorldContent lands
and before the first session, and already emitting the events that presuppose the content is valid.

> **RLS-D23 — `RealityBootstrapper` owns seed-time validation.** Recognition, not invention: it is
> already the actor at that instant, and already the thing whose `*Born` events depend on the answer.

| Time | Owner | Sees | Failure blast radius |
|---|---|---|---|
| **Load** (ruleset resolution) | the loader (§4, §5) | Ruleset only | reality **Unloadable** / creation rejected |
| **Seed** (reality bootstrap) | **`RealityBootstrapper`** | Ruleset **+** WorldContent | creation — or the fork — **rejected** |
| **Admission** (per input) | `commit-service` (CS-A3, CS-D9) | live state | **one turn** rejected |

Seed-time runs once, at creation. A fork that re-seeds re-runs it and a failure rejects the fork —
which is the correct blast radius, since nobody is playing in a reality that does not yet exist.

> **RLS-A10 — Load-time validation is the loader's, admission validation is `commit-service`'s.** The
> two are conflated today under the single phrase *"at RealityManifest bootstrap."* They are different
> pipelines with different blast radii: a load failure makes the **reality unloadable**; an admission
> failure rejects **one turn**. `commit-service` explicitly *"gates admission, not execution"* (CS-A3)
> and *"never chooses which validator stages run"* (CS-D9), so it was never a candidate to own
> bootstrap. Nobody was.

---

## 6. The registry

Chaos's `ConfigurationRegistryImpl` is a process-global `HashMap<String, Arc<dyn ConfigurationProvider>>`.
Copying that shape would be a tenancy defect of exactly the class `CLAUDE.md` exists to prevent: our
island manager co-locates islands from **many realities** in one process (SL-D20b spatial
co-location), and auto-fork siblings *are* separate realities by design.

> **RLS-A11 — The registry is keyed `(RealityId, RulesetEpoch) → Arc<RealityRuleset>`, and many
> versions are live simultaneously.** There is no process-global "current config." A node hosting 40
> realities holds ≥40 rulesets; a reality mid-epoch-switch holds two.

```rust
pub struct RulesetRegistry {
    resolved: DashMap<(RealityId, RulesetEpoch), Arc<RealityRuleset>>,
    digests:  DashMap<RulesetDigest, Arc<RealityRuleset>>,   // dedupe across realities
}
```

The `digests` map is the payoff of content-addressing: 200 realities forked from one preset with no
overrides share **one** `Arc`. Interning is not an optimization here — it is what makes
"every island holds the full ruleset" affordable at multiverse scale.

> **RLS-D4 — `canon_cache.rs` is a precedent for the *shape* and a trap for the *policy*.**
> [`crates/dp-kernel/src/canon_cache.rs`](../../../crates/dp-kernel/src/canon_cache.rs) (1018 LOC) is
> already a per-reality-keyed resolution cache with the right key discipline — *"the `reality_id`
> PREFIX is mandatory."* Its consistency model is not reusable: *"event-driven invalidate is PRIMARY;
> 60s TTL fallback."* Eventually-consistent is correct for LLM prompt facts and fatal for rules — two
> islands inside that 60s window resolve different `stat_slots`, diverge, and replay reproduces
> neither. Rules get **versioned immutable snapshots plus a coordinated switch**, never a TTL.

---

## 7. The Domain seam

Today, rules have no route into simulation:

```rust
fn check(state: &Self::State, p: &Precondition<Self>) -> Result<(), Violation>;
fn apply(state: &mut Self::State, input: &QueuedInput<Self>, rng: &mut DetRng) -> Vec<Self::Event>;
```

Both are associated functions with **no `&self`**, so `Self::State` is the only channel. That leaves
two implementable options and both are bad: carry the whole ruleset in `State` (and therefore in every
checkpoint, migration payload and crash rebuild), or reach a process global — which violates
`apply`'s own *"no I/O, no ambient clock"* contract. Configuration **is** ambient state; the rule
already forbids it without naming it.

> **RLS-A12 — `Domain` gains a `Rules` associated type, passed by reference.**

```rust
pub trait Domain: Sized {
    type Payload;  type State;  type Event;  type ResKind;
    type Rules;                                            // NEW — immutable, Send + Sync

    fn check(state: &Self::State, rules: &Self::Rules,
             p: &Precondition<Self>) -> Result<(), Violation>;

    fn apply(state: &mut Self::State, rules: &Self::Rules,
             input: &QueuedInput<Self>, rng: &mut DetRng) -> Vec<Self::Event>;

    fn externals(events: &[Self::Event]) -> Vec<External>;
}

// Island<D> holds Arc<D::Rules> + RulesetDigest — NOT inside D::State,
// therefore NOT in checkpoints, migration payloads, or snapshot rebuilds.
```

Three properties fall out, all of which we would otherwise have to build:

- **Checkpoints stay small and stay about the world.** `State` means durable world state again, and
  only that.
- **The version is explicit at the seam**, so an island cannot silently be running rules other than
  the ones its digest claims.
- **`apply` stays pure.** Rules arrive as an argument, which is the only form of configuration a
  deterministic function can legitimately accept.

This amends a contract written the same day it is being amended. That is the cheapest moment it will
ever be available: after `sim-core` S1 ships, this signature is in every domain handler.

---

## 8. Replay

The event log stores events. Rules live outside it. Replay a six-month-old reality today and it
resolves against *today's* rules and produces different damage numbers — the canonical event-sourcing
configuration trap, and one that defeats the conformance/oracle spine already built and passing.

> **RLS-A13 — Every event is pinned to the ruleset that produced it, by content digest.**

```rust
pub struct RulesetDigest(pub [u8; 32]);   // BLAKE3 over the canonical normalized encoding
pub struct RulesetEpoch(pub u32);         // per-reality monotonic; ordering, not identity
```

- The **digest** is identity: same bytes ⇒ same rules ⇒ shareable `Arc`, comparable across realities.
- The **epoch** is ordering: monotonic per reality, so "which came first" needs no hash comparison.
- Resolved rulesets are stored immutably and are **never** GC'd while any event references them.

> **RLS-D5 — Canonical encoding is part of the contract, not an implementation detail.** Deterministic
> field order, **one byte representation per value** (RLS-A8 — reworded 2026-08-02 from *"no floats"*;
> the requirement was never the type but the uniqueness of the encoding, and an unnormalised `NaN` or
> `-0.0` is what actually breaks it, so a canonicalised float satisfies RLS-A8 while a raw one does
> not), no maps with nondeterministic iteration order. A digest that varies
> by serializer version is worse than no digest, because it fails *loudly and wrongly* — every replay
> reports a mismatch that isn't one.

> **RLS-D6 — The envelope carries the digest, not the ruleset.** Full-ruleset-in-event was considered:
> a self-contained log, no external store on the replay path. Rejected on re-emission — 200 realities
> sharing a preset would each write the same kilobytes, repeatedly, forever. Digest + immutable store
> keeps the log small and dedupes globally. The dependency this creates (replay needs the ruleset
> store) is real and is the reason the store is append-only and never pruned.

> **RLS-D7 — Version-number-only was rejected.** A monotonic `ruleset_version` pointing at a mutable
> Postgres row is the cheapest thing to build, and nothing prevents that row from being edited in
> place. The resulting replay divergence is invisible until an oracle disagrees, at which point the
> evidence has been overwritten.

### 8.1 Engine upgrades (RLS-Q5 — RESOLVED)

Under I14, only one upgrade case is real. A **new field with a default** leaves stored rulesets valid
(missing ⇒ default). A **removed or retyped field** is forbidden outright. What remains is a
**validator getting stricter** — an old ruleset that was valid becoming invalid.

Re-validating and rejecting it is the worst available outcome: the digest is referenced by historical
events, so rejection makes history unreplayable. And the ruleset *was* validated — at the moment it
was resolved, against the rules in force then.

> **RLS-D18 — A stored ruleset is never re-validated. It is deserialized, upcast if the struct moved,
> and used.** Resolution-time validators (§4, §5) apply to **new** resolutions only. This is exactly
> the discipline [`dp-kernel::upcaster`](../../../crates/dp-kernel/src/upcaster.rs) already applies to
> events: a stored event written under an old schema is upcast on read, never rewritten and never
> rejected.

Two constraints make that safe, and both are load-bearing:

- **The digest addresses the stored bytes, not the upcast form.** Upcasting produces an in-memory
  representation; stored bytes and digest are immutable. Otherwise an engine upgrade would silently
  re-hash every ruleset and orphan every event that referenced one.
- **A ruleset upcaster must be a pure function of the stored bytes.** A nondeterministic or
  environment-sensitive upcaster reintroduces precisely the drift the digest exists to prevent, one
  layer down and much harder to see.

Where an engine genuinely *cannot* upcast — a rule semantically withdrawn, not merely reshaped — the
reality is **quarantined** (RLS-D12), loudly and operator-visibly. It is never silently reinterpreted.

---

## 9. Rule changes are ordered events

`sim-core`'s correctness claim is a total order, per island, over ingress. A ruleset swap performed by
any other path lands *between* steps at a point nothing defines.

And the capability is already being depended upon: [DF07_002 EC-15](features/DF/DF07_pc_stats/DF07_002_edge_cases_and_closure.md)
asserts that *"a **manifest hot-reload** mid-encounter changes `stat_slots` for everyone"*, and
resolves the case by having `manifest_version` sit in DF7's `StatEpoch` so *"every combatant's snapshot
invalidates together at the next round boundary."* That is the right answer to a question asked of
infrastructure that does not exist. DF7 also happens to be where `manifest_version` currently lives —
as a private field of one feature's cache-invalidation struct, unowned and absent from the manifest
contract.

> **RLS-A14 — A ruleset epoch switch enters each affected island as an ordinary ingress item.**
> `RulesetEpochActivated { reality_id, from_epoch, to_epoch, digest }`, `Producer::Admin`, subject to
> the same `Seq` stamping, the same idempotency and the same generation semantics as any other input.
> No side channel, no ambient swap.
>
> **Corrected 2026-07-26 — two mechanics were under-specified as first written.**
> (1) **Producer:** `RulesetEpochActivated` is EVT-T8 Administrative, and **EVT-P8 forbids every
> non-admin-cli service from emitting T8** — the loader cannot emit it. It is issued by
> **Forge/admin-cli through the S5 dispatch chokepoint** (owner **WA_003 Forge**, §12b REC-29).
> (2) **Durability:** RLS-I1/RLS-D9 require the switch be replayable from the island tail, so it is
> **N committed events, one per affected channel** — durable `event_log` entries, never a bare
> in-memory `QueuedInput`. The "ordinary ingress item" framing survives: each island consumes its
> own committed copy as ingress.

> **RLS-D8 — The switch is atomic per island.** An island applies the new `Arc` between two `step()`
> calls, never inside one. Cross-island messages already carry sender causality; a message crossing an
> epoch boundary is delivered under the **receiver's** epoch — the only choice that keeps each island
> internally consistent.

### 9.1 No reality-wide barrier (RLS-Q4 — RESOLVED)

Asking what actually breaks while two islands of one reality run different epochs:

- **State is unaffected.** Rules govern *derivation*, not storage. An entity handed off mid-switch
  carries the same `actor_progression` raw values either way; only their projection differs, and DF7
  recomputes a block per `StatEpoch` regardless.
- **The contested case cannot arise.** Where rule differences are *visible and adversarial* is combat
  — and **an encounter is always exactly one island**. Everyone in it shares an epoch by construction.
  Same for a cell: two PCs in one cell are in one island whenever they arrived.
- What remains is cosmetic: a player in cell A briefly sees pre-switch numbers while cell B sees
  post-switch. That is a **UX** concern, addressed by broadcasting an announcement, not by stalling
  the simulation.

> **RLS-D17 — No barrier. The island is the consistency boundary, and it already is the one that
> matters.** A reality-wide barrier would stall every island on the slowest one, to buy consistency
> across a seam no player can observe.

> **RLS-I1 (invariant) — Island epoch is monotonic.** An island never moves backwards. A rebuild from a
> checkpoint pinned at epoch 3 while the reality sits at 5 replays forward through the intervening
> `RulesetEpochActivated` items in its tail (RLS-D9) rather than adopting 5 directly — so the island
> passes through the same sequence a live island did, and lands in the same state.

> **RLS-D9 — Migration and crash recovery carry the digest.** §10.5 rebuilds an island as
> *snapshot + events since*. If the epoch advanced in between, the island resurrects running new rules
> over old state, silently. The rebuild therefore resolves the digest **pinned in the last event
> replayed**, not "current," and then processes any `RulesetEpochActivated` in the tail like any other
> input. Migration (`Dissolving{Migrating}`) ships the digest with the handoff; the target node
> resolves that exact ruleset or **refuses the handoff**.

---

## 10. Fork semantics

[`03_multiverse/03_fork_and_cascading.md`](03_multiverse/03_fork_and_cascading.md) contains **zero**
occurrences of "manifest." Forking is fully specified for events and projections and entirely
unspecified for rules.

> **RLS-D10 — Fork copies the digest, never re-resolves.**

| Fork type | Ruleset | Why |
|---|---|---|
| **Auto-fork** (capacity shard) | inherits the parent's digest verbatim | Today's *"fresh from book"* seed rule is about *state*. Applied to *rules* it means: if the book's manifest changed since the parent was seeded, the capacity shard silently plays by different rules than its sibling. That is a bug, not a feature — auto-fork exists to add player capacity, not to branch balance. |
| **User-fork, snapshot** | inherits the parent's digest verbatim | Continuity is the entire point of the fork. |
| **User-fork, fresh** | re-resolves the stack at creation time | The author asked for a new world; new rules are expected, and the digest records exactly which. |
| **Auto-rebase at depth N** | inherits the rebased-from digest | Rebase flattens lineage while preserving state (§12.3); rules must travel with the state they govern. |

### 10.1 Rule mutability (RLS-Q2 — RESOLVED)

The four-layer model (L1 axiomatic → L4 flexible) governs `entity_attributes` facts via
`canon_lock_level`; rules sat outside it entirely. *"Can an author change `stat_slots` on a live
reality with 100 PCs?"* had no answer anywhere.

**The question was mis-framed as one question.** It is one *per field*, and the axis that decides it is
not importance — it is **whether stored state references the declaration**.

- Changing `combat_disparity_cap` affects only future computation. Nothing stored points at it. Not
  just safe to change mid-play — plausibly *urgent*, since it is the anti-grief cap.
- Deleting a `progression_kinds` entry that a hundred `actor_progression` rows reference by `kind_id`
  is destructive in a way no epoch mechanism makes safe. The rows do not stop existing.

Forbidding mutation outright is not available: an author who ships a broken loot table would have a
permanently broken reality and no remedy but forking, which abandons all L3 history. The product
premise also settles the fairness objection — in a book-authored world the author **is** the game
master, and a reality is their world, not a competitive ladder.

> **RLS-A17 — Every Ruleset field carries a mutability class, and removal is never removal.**
>
> | Class | May Forge change it on a live reality? | Default group |
> |---|---|---|
> | `Tunable` | yes — freely, emits an epoch | scalars and tables nothing references by ID: `combat_disparity_cap`, `stat_tuning`, `prices`, `tier_roster_caps`, `desires_prompt_top_n`, `cell_untracked_density`, `inventory_defaults` |
> | `AdditiveOnly` | **append yes, redefine/remove no** | ID-keyed registries live state points at: `progression_kinds`, `races`, `languages`, `ideologies`, `item_defs`, `canonical_titles`, `canonical_factions` |
> | `Frozen` | no, after the first session | rules whose change would **falsify past events**: `lex_config` (the world's axioms — the genuine L1 analogue), `mortality_config` (switching permadeath→respawn retroactively changes what every past death meant), `initiative_system` |
>
> **Removal downgrades to deprecation, always.** A Forge removal of an `AdditiveOnly` entry marks it
> *deprecated* — no longer grantable, existing instances keep resolving. This is what live MMOs
> actually do with withdrawn items and talents, and it is the only option that does not orphan state.

`Frozen` is deliberately small — 3 of 40. It is not "important rules": `stat_slots` is as load-bearing
as anything in the engine and is `Tunable`, because changing a slot's terms re-derives a projection,
whereas changing `mortality_config` rewrites the meaning of history.

Per-field assignment for all 40 is at [`16a §6`](16a_ruleset_field_classification.md) — **24 `Tunable`
· 13 `AdditiveOnly` · 3 `Frozen`** — and it corrected the `stat_slots` example this axiom was first
written with (§16a §6.2).

> **RLS-D16 — Rule mutation is a Forge action under the *existing* S5 tier discipline.** No new
> governance mechanism. GEO_001's `GeographyDelta` already requires `reason: I18nBundle` at *"50+ char
> per S5 Tier 2 Griefing discipline; Tier 1 Destructive for SetBiomeOverride + RemoveRoute"*, and
> WA_003 Forge already supplies the audit trail. Rule mutations slot in by class: `Tunable` → ordinary
> Forge action · `AdditiveOnly` append → Tier 2 (Griefing, reason required) · deprecation → **Tier 1
> (Destructive)** · `Frozen` → rejected at the validator, not tiered.

**Default for an unclassified field: `Tunable`.** The alternative bricks realities over typos.

An author-set reality-wide `rules_frozen` flag — promoting everything to `Frozen` for a reality that
wants hardcore/competitive guarantees — is a natural extension and is **not** V1 (RLS-D22, deferred).

---

## 11. Failure policy

Chaos answers cold-start failure by refusing to boot: `load_all_configs` returns `Err` and the service
does not start. We cannot: one malformed reality must not take down a node hosting forty others.

> **RLS-D12 — Failure is per-reality quarantine, never process failure.** A reality whose ruleset
> fails to resolve enters `Unloadable{reason}`: no islands spawn, sessions are refused with a
> diagnosable error, and the reality is surfaced to its author. Neighbouring realities on the same
> node are unaffected. A resolution failure during a **live epoch switch** is different and stricter —
> the switch is abandoned and the reality **continues on the previous epoch**, because the alternative
> is evicting live players over an author's typo.

Worth stating plainly, since the whole document argues for early binding: this failure mode is rare by
construction. Early-bound rulesets are validated at creation, and a stored resolved ruleset cannot
spontaneously become invalid — only an engine upgrade that changes validation can do that. Which is
**RLS-Q5**: what happens when `engine_default` v2 rejects a ruleset resolved and stored under v1.

---

## 12. Load path, end to end

```
reality creation                         island Cold -> Hot
────────────────                         ──────────────────
 1 gather layers 0..40                    1 island manager reads reality's
   (engine_default, preset, book,           current (reality_id, epoch)
    reality)                              2 registry: Arc<RealityRuleset>
 2 topo-sort fields (RLS-A9)                 (interned by digest, RLS-A11)
 3 merge per declared strategy            3 WorldContent: this channel's
   (RLS-A4) + tombstones (A5)                rows only, lazily (RLS-A1)
 4 normalize to fixed-point (A7/A8)       4 Island<D> constructed with
 5 referential validators, in order          Arc<D::Rules> + digest
 6 BLAKE3 over canonical encoding         5 every emitted event pinned to
 7 store immutably; assign epoch 1           that digest (RLS-A13)
   -> failure here = never created,       -> failure here = this reality
      not Unloadable                          Unloadable; others unaffected
```

The asymmetry in the failure column is deliberate: creation-time failure is a **rejected request** with
an author sitting in front of it, and load-time failure is an **operational state** with players
sitting in front of it.

---

## 13. What this changes elsewhere

| Doc | Change | Gate |
|---|---|---|
| [`_boundaries/02_extension_contracts.md`](_boundaries/02_extension_contracts.md) §2 | Split into §2a `RealityRuleset` / §2b `WorldContent`; every field gains **side** + **merge strategy** columns; extension rules gain #6 (declare side) and #7 (declare strategy). Owner changes from *"⚠ Currently unowned"* to this document. | lock |
| [`07_event_model/06_per_category_contracts.md`](07_event_model/06_per_category_contracts.md) *(row added 2026-07-26)* | Envelope gains the `ruleset_digest` field via the EVT-A12(c) named extension point; `event_schema_version` **1 → 2** as a required field (EVT-S1/S4); two-phase rollout, consumers before producers (EVT-S2); no single-layer bump (EVT-S6/DP-C5); replay-invariance CI gate (EVT-S5). | EVT owner — **LOCKED, pending AMEND (REC-53 bundle)** |
| [`07_event_model/11_schema_versioning.md`](07_event_model/11_schema_versioning.md) *(row added 2026-07-26)* | **Permanent** v1→v2 upcaster (EVT-S3). Legacy sentinel **decided**: pre-bump events upcast with `digest = RULESET_UNKNOWN` (a named sentinel constant) and are **explicitly non-replayable-exactly** — there is no correct default, because pre-bump events genuinely ran under unknown rules; the sentinel makes that loss legible instead of silent. | EVT owner — **LOCKED, pending AMEND (REC-53 bundle)** |
| [`_boundaries/02_extension_contracts.md`](_boundaries/02_extension_contracts.md) §4 + [`_boundaries/01_feature_ownership_matrix.md`](_boundaries/01_feature_ownership_matrix.md) *(row added 2026-07-26)* | Register the `RulesetEpochActivated` EVT-T8 sub-shape + matrix row, **owner = WA_003 Forge** (§12b REC-29 — Forge already owns admin rule-edits and the S5 chokepoint; EVT-A11 demands one owning feature, and this doc, per RLS-D21, deliberately is not one). | lock |
| EVT-L16 visibility declaration *(row added 2026-07-26)* | `RulesetEpochActivated` is **internal-filtered, not user-visible** — players get the RLS-D17 broadcast announcement, never the raw admin event. Declared with the sub-type registration (the quickstart checklist blocks on TBD). | with the §4 registration |
| `07_event_model/` EVT-A9 · EVT-A10 · EVT-L18 *(row added 2026-07-26)* | The three amendments RLS-A12/A13 require: an **EVT-A9 carve-out** for `&D::Rules` (justified by immutability + digest pinning); **EVT-A10/EVT-L18** add the digest-addressed ruleset store to the closed replay-input list (digest pinning is a second, non-event-sourced replay input and must be amended in, not merely cited). | EVT owner — **LOCKED, pending AMEND (REC-53 bundle)** |
| [`14_sim_core_spec.md`](14_sim_core_spec.md) §4.0 | `Domain` gains `type Rules`; `check` / `apply` gain the parameter (RLS-A12). §10.5 + §10.2 gain the digest rule (RLS-D9). | SC owner |
| [`15_commit_service.md`](15_commit_service.md) | Admission stamps the active `RulesetDigest` into the envelope. Load-time validation is explicitly **not** commit-service's (RLS-A10). | CS owner |
| [`03_multiverse/03_fork_and_cascading.md`](03_multiverse/03_fork_and_cascading.md) | New section: ruleset inheritance per fork type (RLS-D10). | — |
| [`03_multiverse/09_config_and_refs.md`](03_multiverse/09_config_and_refs.md) | Today's `multiverse.*` keys are **platform** config (player caps, split thresholds), a different axis from per-reality rules. Cross-reference so the two are not conflated. | — |
| [`features/00_progression/PROG_001_progression_foundation.md`](features/00_progression/PROG_001_progression_foundation.md) | **Closure item:** five `f32` fields violate DF7-A4 / TDIL-A9 (RLS-A8) → fixed-point. Also: PROG-D6 defers *"Subsystem stacking (chaos-backend Contribution pattern)"*, which **DF7-A3 already shipped** for the derived layer — the row is stale. | PROG owner |
| [`features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md`](features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md) | `StatEpoch.manifest_version` → `RulesetEpoch` from the registry; EC-15's assumed hot-reload now has real machinery (§9). | DF7 owner |
| [`_boundaries/03_validator_pipeline_slots.md`](_boundaries/03_validator_pipeline_slots.md) | Existing *"at RealityManifest bootstrap"* slots re-file as **load-time**, in topological order. | lock |
| [`features/03_player_onboarding/PO_001_player_onboarding.md`](features/03_player_onboarding/PO_001_player_onboarding.md) | **CLS-1:** `canonical_pcs` is declared **twice** — top-level §2 field *and* `OnboardingConfigDecl.canonical_pcs`, with the same stated validation in both. A redundancy today; a **divergence** under layered merge. Delete one. | PO owner |
| [`features/00_identity/IDF_003_personality.md`](features/00_identity/IDF_003_personality.md) | **CLS-2:** the 12×12=144 `opinion_modifier_table` requirement needs the RLS-D15 completion rule to survive merging. | IDF owner |
| [`features/00_actor/ACT_001_actor_foundation.md`](features/00_actor/ACT_001_actor_foundation.md) | **CLS-3:** top-level `npc_desires` was superseded by `ChorusMetadataDecl.desires` at the 2026-04-27 unification and never removed. | ACT / NPC_003 |
| [`features/00_tilemap/TMP_001_tilemap_foundation.md`](features/00_tilemap/TMP_001_tilemap_foundation.md) · [`features/18_combat/COMB_001_combat_foundation.md`](features/18_combat/COMB_001_combat_foundation.md) | **RLS-D13:** 5 wall-clock / host / dev-mode knobs leave the manifest for platform config. | TMP / COMB |
| [`features/00_place/PF_001_place_foundation.md`](features/00_place/PF_001_place_foundation.md) · [`features/00_map/MAP_001_map_foundation.md`](features/00_map/MAP_001_map_foundation.md) | **No change required** — `RLS-Q10` checked both and found `Forge:EditPlace` / `Forge:EditMapLayout` already EVT-T8 + EVT-T3 against aggregates (§2.1). Worth one cross-reference noting that the per-cell rule fields they carry are replay-covered by aggregate replay, not by the ruleset digest. | optional |
| [`03_multiverse/01_four_layer_canon.md`](03_multiverse/01_four_layer_canon.md) | Cross-reference RLS-A17: rules now have a mutability model that *parallels* L1/L2 without being it — `Frozen` is the L1 analogue, `Tunable`/`AdditiveOnly` the L2 analogue, and the deciding axis is state-reference, not authorial intent. | — |
| [`12_module_coverage_audit.md`](12_module_coverage_audit.md) | **AUD-F14** added. | — |

---

## 14. Open questions — all resolved 2026-07-26

The pass that closed these is worth recording in one line, because it repeated: **five of the eight
were answered by a mechanism that already exists** (the S5 Forge tier discipline, `upcaster.rs`,
`GeographyDelta`, `RealityBootstrapper`, the CLAUDE.md tenancy tiers). Only `RLS-Q2` needed a genuine
product judgement, and only its *default* was actually open.

| ID | Resolution |
|---|---|
| ~~**RLS-Q1**~~ | **Stays a numbered platform doc.** `14` (sim-core) and `15` (commit-service) set the precedent for infrastructure that has no feature lifecycle: no catalog, no stable-ID namespace, no player-facing acceptance scenarios, no DRAFT→CANDIDATE-LOCK promotion. Creating `features/01_infrastructure/` for a single doc adds a namespace to carry a filename. → **RLS-D21:** the `_boundaries` §2 *"Pending action: create `IF_001_reality_manifest.md`"* is **retired**, pointed at this document. Its substance — *the envelope needs an owner* — is satisfied. |
| ~~**RLS-Q2**~~ | **Mutable, per-field, with removal downgraded to deprecation** → RLS-A17 + RLS-D16 (§10.1). The question was mis-framed as one question; it is one *per field*. |
| ~~**RLS-Q3**~~ | **Swept** → [`16a`](16a_ruleset_field_classification.md). **65 fields swept**; 1 leaves for platform config (plus 4 sub-fields of `tilemap_defaults`); the 64 remaining split **3 identity · 40 Ruleset · 20 Content · 1 Provenance**. Amended the design in four places (A15, A16, D13, D14) and opened Q8. **Proposed, awaiting owner sign-off** (§16a §7). |
| ~~**RLS-Q4**~~ | **No barrier needed** → RLS-D17 (§9.1). The island is already the consistency boundary. |
| ~~**RLS-Q5**~~ | **Never re-validate a stored ruleset; upcast on read** → RLS-D18 (§8.1). Exactly `upcaster.rs`'s discipline. |
| ~~**RLS-Q6**~~ | **Per-channel versioning, not global — and the premise was wrong** → RLS-A18 (§2.1). WorldContent is *not* write-once. |
| ~~**RLS-Q7**~~ | **Standard three-tier scoped resource; no preset history needed** → RLS-D19 (§3.1). Early binding makes preset history redundant. |
| ~~**RLS-Q8**~~ | **`RealityBootstrapper` owns seed-time validation** → RLS-D23 (§5.1). The actor already exists and already runs at exactly that moment. |

### 14.1 The two follow-ons, also resolved

| ID | Resolution |
|---|---|
| ~~**RLS-Q9**~~ | **Assigned for all 40 Ruleset fields** → [`16a §6`](16a_ruleset_field_classification.md). **24 `Tunable` · 13 `AdditiveOnly` · 3 `Frozen`.** The pass **corrected two of RLS-A17's own examples** (§16a §6.2) — `stat_slots` is `Tunable`, not `AdditiveOnly`, because `StatSlot` is a closed engine enum, so removing a decl degrades to the engine default rather than orphaning anything; the ID-keyed constraint lives one level down on `progression_kinds`. |
| ~~**RLS-Q10**~~ | **Both write-paths exist and both are already event-shaped** — and checking rather than delegating **overturned my own RLS-A18** (§2.1). They target *aggregates* (`aggregate_type=place` / `=map_layout`), not manifest rows, so no `content_version` needs inventing: `dp-kernel` aggregate versioning already is it. |

**No open questions remain.** What is left is owner sign-off on [`16a`](16a_ruleset_field_classification.md)
— review, not analysis — plus the three pre-existing defects the sweep surfaced (CLS-1, CLS-2, CLS-3),
which are also owner calls. Nothing blocks build-order steps 1–4.

### 14.2 What the question pass is worth recording for

Eight questions, and **six were answered by a mechanism that already existed** in the design or the
code: the S5 Forge tier discipline (Q2), `dp-kernel::upcaster` (Q5), `GeographyDelta` + aggregate
versioning (Q6/Q10), `RealityBootstrapper` (Q8), and the CLAUDE.md tenancy tiers (Q7). Two of the
remaining answers came from noticing a question was mis-posed: Q2 was one question per field rather
than one question, and Q6's premise was simply false.

The generalizable read for the rest of this design: **when this document reaches for a new mechanism,
that is the signal to go looking for the existing one first.** Two of the four things I invented in
the first draft — a per-channel `content_version` and a rules canon-lock model — already existed under
other names. Both were withdrawn on contact with the code.

---

## 15. Build order

1. ~~**`RLS-Q3` field classification sweep**~~ — ✅ **done 2026-07-26**, [`16a`](16a_ruleset_field_classification.md).
   Remaining is **owner sign-off**, not analysis ([`16a §7`](16a_ruleset_field_classification.md)).
2. **`Domain::Rules` trait change** — the cheapest it will ever be, and it expires when S1 ships.
3. **`engine_default` artifact** (RLS-D2) — makes every "engine default" claim in the feature docs
   testable, and is the one layer with no upstream dependency.
4. **Resolver + digest** (§4, §8) — pure function, trivially unit-testable, no infrastructure.
5. **Registry** (§6) — needs 4.
6. **Epoch switch as ingress** (§9) — needs `sim-core` S1.
7. **Preset layer** — content work, needs 3–5.

Steps 1–4 have **no dependency on AUD-F8**, which remains the top implementation blocker. This design
does not compete with it for the critical path.

---

## 16. Prior art

| Source | Taken | Rejected |
|---|---|---|
| `chaos-backend-service` `actor-core::config` | provider stack with integer priority; per-key merge rules; registry/aggregator separation | process-global registry (single-tenant — RLS-A11); arithmetic merge strategies (RLS-D3); `load_config_files` is a `// TODO` and `load_default_merge_rules` logs *"not yet implemented"* — the shape is the contribution, not the code |
| `chaos-backend-service` `element-core` | multi-directory split as an early form of RLS-A1 | fixed `supported_systems` YAML — our author-declared `ProgressionKindDecl` is strictly more open |
| `dp-kernel::canon_cache` | per-reality key discipline; cache-aside structure | TTL/eventual consistency for rules (RLS-D4) |
| `dp-kernel::upcaster` | schema evolution precedent for RLS-Q5 | — |
| Nix / Bazel content-addressing | digest as identity; interning identical closures | — |
