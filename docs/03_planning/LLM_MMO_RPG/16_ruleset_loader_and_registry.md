# 16 — Ruleset Loader & Registry (design)

> **Status:** DRAFT — 2026-07-26. Opens and closes the design half of **AUD-F14**.
> **Prefix:** `RLS-*` (registered 2026-07-26; axioms `RLS-A1..A14`, decisions `RLS-D1..D12`, questions `RLS-Q1..Q7`).
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
> (bulk, seed-once, loaded per-channel on Cold→Hot). A field belongs to the Ruleset if `apply()` can
> read it; to WorldContent if only the bootstrapper reads it.

> **RLS-A2 — The split is a *classification*, not a rewrite.** Every existing `_boundaries` §2 field
> keeps its shape, its owner and its I14 additive guarantee. What changes is that each row gains a
> side. Features do not redesign anything; they answer one question about each field they own.

---

## 2. The two artifacts

```
RealityRuleset                              WorldContent
  (hot · ~KB · versioned · immutable)         (cold · ~MB-GB · seed-once)
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
  Arc<RealityRuleset> per (reality, epoch)    per-channel rows, read at bootstrap
  digest pinned into the event envelope       superseded by L3 events thereafter
  hydrated into every island of the reality   never enters an island's hot path
```

The boundary case worth naming: **`canonical_factions` is content, `FactionDecl.roles` is a rule.**
A faction's *existence* is seed data that drifts per reality (L2); the *role ladder and authority
levels* an engine consults are rules. Where a decl mixes both, the split follows the reader, and the
owning feature makes the call at registration time (§14).

> **RLS-D1 — Ambiguity resolves toward WorldContent.** If a field's side is unclear, it is content
> until a consumer demonstrates a hot-path read. Mis-filing a rule as content costs one lazy load;
> mis-filing content as a rule costs memory on every island in the reality.

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
> field order, no floats (RLS-A8), no maps with nondeterministic iteration order. A digest that varies
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

> **RLS-D8 — The switch is atomic per island, coordinated per reality.** An island applies the new
> `Arc` between two `step()` calls, never inside one. Cross-island messages already carry sender
> causality; a message crossing an epoch boundary is delivered under the **receiver's** epoch, which
> is the only choice that keeps each island internally consistent. Whether the *reality* needs a
> barrier — all islands switching before any proceeds — is **RLS-Q4**, and the answer is probably
> "no, and DF7's round-boundary invalidation is the general pattern."

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

> **RLS-Q2 — Rules have no canon lock level.** The four-layer model (L1 axiomatic → L4 flexible) governs
> `entity_attributes` facts via `canon_lock_level`. Rules sit outside it entirely. *"Can an author change
> `stat_slots` on a live reality with 100 PCs mid-encounter?"* has no answer in any document, and it is
> a **product** question before it is a technical one. The technical machinery (§9) supports either
> answer; someone has to choose. Candidate: rules default to L2-equivalent (author-mutable, per-reality,
> emits an epoch) with an author-set `frozen` flag promoting a reality to L1-equivalent.

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
| [`14_sim_core_spec.md`](14_sim_core_spec.md) §4.0 | `Domain` gains `type Rules`; `check` / `apply` gain the parameter (RLS-A12). §10.5 + §10.2 gain the digest rule (RLS-D9). | SC owner |
| [`15_commit_service.md`](15_commit_service.md) | Admission stamps the active `RulesetDigest` into the envelope. Load-time validation is explicitly **not** commit-service's (RLS-A10). | CS owner |
| [`03_multiverse/03_fork_and_cascading.md`](03_multiverse/03_fork_and_cascading.md) | New section: ruleset inheritance per fork type (RLS-D10). | — |
| [`03_multiverse/09_config_and_refs.md`](03_multiverse/09_config_and_refs.md) | Today's `multiverse.*` keys are **platform** config (player caps, split thresholds), a different axis from per-reality rules. Cross-reference so the two are not conflated. | — |
| [`features/00_progression/PROG_001_progression_foundation.md`](features/00_progression/PROG_001_progression_foundation.md) | **Closure item:** five `f32` fields violate DF7-A4 / TDIL-A9 (RLS-A8) → fixed-point. Also: PROG-D6 defers *"Subsystem stacking (chaos-backend Contribution pattern)"*, which **DF7-A3 already shipped** for the derived layer — the row is stale. | PROG owner |
| [`features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md`](features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md) | `StatEpoch.manifest_version` → `RulesetEpoch` from the registry; EC-15's assumed hot-reload now has real machinery (§9). | DF7 owner |
| [`_boundaries/03_validator_pipeline_slots.md`](_boundaries/03_validator_pipeline_slots.md) | Existing *"at RealityManifest bootstrap"* slots re-file as **load-time**, in topological order. | lock |
| [`12_module_coverage_audit.md`](12_module_coverage_audit.md) | **AUD-F14** added. | — |

---

## 14. Open questions

| ID | Question | Blocking? |
|---|---|---|
| **RLS-Q1** | Does this become `features/01_infrastructure/IF_001_reality_manifest.md` (the deferred action named in `_boundaries` §2) or stay a numbered platform doc? Naming, not substance. | no |
| **RLS-Q2** | Canon lock level for rules — can an author mutate rules on a live reality? Product question (§10). | **yes, for `Forge:*`** |
| **RLS-Q3** | Which existing `_boundaries` §2 field goes on which side? ~40 rows, one question each, answered by the owning feature. | yes, for the split |
| **RLS-Q4** | Does an epoch switch need a reality-wide barrier, or is per-island-at-quiescence enough? (§9, RLS-D8 — probably enough.) | no |
| **RLS-Q5** | Engine upgrade invalidates a stored ruleset — reject, quarantine, or auto-upcast? `dp-kernel`'s `upcaster.rs` is the obvious precedent. | no |
| **RLS-Q6** | Does `WorldContent` need its own digest/versioning, or is seed-once + L3 supersession enough? | no |
| **RLS-Q7** | Are preset definitions themselves versioned artifacts, and are they per-tenant or System-tier? (System-tier read-only + admin-authored is the CLAUDE.md-conformant default; user-authored presets are a per-user tier.) | no |

---

## 15. Build order

1. **`RLS-Q3` field classification sweep** — cheap, parallel, unblocks everything. Until each field has
   a side, neither loader has a scope.
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
