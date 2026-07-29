# S1 + S2 — field classification, and the laws become a crate that cannot do I/O

> **Status:** PLAN 2026-07-29. One continuous XL run, two risk boundaries (one commit each).
> **Spec:** [`26_implementation_architecture.md`](../03_planning/LLM_MMO_RPG/26_implementation_architecture.md)
> §4 (IMP-A5/D2/D3), §5 (IMP-A7/D4), §6 build order · [`16_ruleset_loader_and_registry.md`](../03_planning/LLM_MMO_RPG/16_ruleset_loader_and_registry.md)
> RLS-A4/A16/A17 · [`16a_ruleset_field_classification.md`](../03_planning/LLM_MMO_RPG/16a_ruleset_field_classification.md) §3, §6.
> **Standard that shaped the plan:** [`non-vacuity.md`](../standards/non-vacuity.md) NV-1..6.

---

## 0. The CLARIFY finding — S1 as written cannot be built non-vacuously today

Doc 26's build order puts **S1** before S2, with the exit criterion:

> *"16a's 64 fields wired: layer floors, `Tunable` vs `AdditiveOnly` | **an over-reaching override is
> REFUSED, with a test**"*

**That test cannot fail today, and the reason is structural rather than a matter of effort.** Checked
against source and against 16a's own tables before designing anything:

| Claim | Evidence |
|---|---|
| No field can over-reach its floor | **All 40 Ruleset rows in 16a §3.2 carry floor `pre`** — and `preset` is the lowest *authorable* layer (`engine_default` is the totality base). A floor every field already satisfies refuses nothing. |
| No mutability class can refuse a mutation | The **3 `Frozen`** fields (`lex_config`, `mortality_config`, `initiative_system`) and the **13 `AdditiveOnly`** fields are all **collections or structs that do not exist in `Ruleset`** — zero code occurrences. `ruleset-loader`'s own doc comment says it: *"`Ruleset` has none [no collections]"*. |
| What actually exists | **20 scalar fields** (15 `CombatRules` + 5 `StatRules`), every one of them `Tunable` with floor `pre`. |
| The floors that DO bite | 16a's seven `rea` rows are all **WorldContent** (`progression_actor_overrides`, `npc_desires`, …) — a different side of the split, with no struct, no patch type and no loader. |

So a literal S1 ships **two checks whose subject cannot vary** — `NV-2`, the first of the four shapes,
one day after that standard was written. The register in `non-vacuity.md` exists to stop exactly this.

### 0.1 The decomposition

Per CLAUDE.md's gate — *"decompose a 'blocked' item into the buildable slice + the genuinely-external
remainder"* — S1 splits, and **neither half is deferred vaguely**:

* **S1a — BUILD NOW.** The *registration mechanism*, default-DENY: every rules field carries a
  classification, and **a new field with no classification is a compile error**. Plus the one strategy
  that can refuse something today: `Forbidden` on the identity fields.
* **S1b — lands with `Q1`, trigger named.** The floor + mutability *enforcement arms*. `Q1` introduces
  L2 declared quantities — an **ID-keyed registry with ordinals assigned and never reused**
  ([QTY-A5](../03_planning/LLM_MMO_RPG/35_quantity_architecture.md)), which is `AdditiveOnly` under
  another name and the **first field the ruleset will ever have that a class check can refuse**. That
  is a real trigger, not "later".

**Why S1a is worth building before its enforcement arms:** it is the part that decides what happens to
the *other 44 rows*. Without it they arrive unclassified and default to `Tunable` — doc 16 line 652
says so in as many words (*"Default for an unclassified field: `Tunable`"*), which is **default-allow**,
the exact NV-3 polarity error. With it, a field cannot be added at all until someone classifies it.

---

## 1. S1a — classification that cannot be skipped

### 1.1 Where it lives

`crates/ruleset-core/src/classification.rs`. It is data *about* the ruleset shape, so it belongs with
the shape, and `ruleset-core` has no I/O — the laws may read it without violating IMP-D2.

```rust
pub enum Floor      { EngineDefault, Preset, Book, Reality }   // RLS-A16
pub enum Mutability { Tunable, AdditiveOnly, Frozen }          // RLS-A17
pub enum Strategy   { Replace, Union, ClampMin, Forbidden }    // RLS-A4
pub struct FieldClass { pub name: &'static str, pub floor: Floor,
                        pub mutability: Mutability, pub strategy: Strategy }
```

### 1.2 The default-deny mechanism — E0027, not discipline

A `classify!` macro emits the class table **through an exhaustive destructure with no `..`**:

```rust
let CombatRules { hit_base_pm, hit_floor_pm, /* … */ } = rules;
```

Adding a 16th field to `CombatRules` without adding its row makes that pattern incomplete, which is
**Rust error E0027 — a hard compile error, not a warning**. The table and the struct cannot diverge
because the table is *generated from a pattern that must mention every field*.

This is the same mechanism `patch.rs` already uses for `missing_fields`/`apply`, promoted from a
convention to the thing that produces the data.

**The macro destructures the struct; it does NOT generate it.** Reviewed explicitly, because
`CombatRules` is inside the hashed canonical encoding — a macro that emitted the struct could reorder
fields and move the digest. The struct stays hand-written; the macro only reads it.

**Bite-proof (NV-6):** add a field to `CombatRules`, `cargo build`, paste E0027, remove it.

### 1.2b What S1a deliberately does NOT ship

**No floor-check function and no mutability-check function.** All 20 present rows are floor `pre` /
`Tunable`, so such a function would return "permitted" for every input that can exist — a verdict it
could never fail, which is `NV-2` and the precise thing this plan opened by rejecting. The *vocabulary*
(`Floor`, `Mutability`) ships because 16a already assigns those values to 44 fields whose structs land
later, and a transcribed decision is data, not a mechanism. **Declared data with a compile-time totality
proof can fail (E0027); a validator that always says yes cannot.** The enforcement arms are S1b.

### 1.3 The one arm that bites today — `Strategy::Forbidden` on identity

`schema_version` and `law_version` live on `Ruleset` and are **not** in `RulesetPatch`, so a layer
declaring one is currently refused by `deny_unknown_fields` — with the message *"unknown field"*, which
is wrong twice: the field is not unknown, and the author is not told why they may never set it.

**How it refuses, decided in review.** The obvious route — add `schema_version`/`law_version` to
`RulesetPatch` so the validator can see them — is wrong: `RulesetPatch`'s `missing_fields` totality check
would then demand them in `engine_default.toml`, i.e. **add a field so it can be declared, in order to
refuse declaring it.** Instead `parse_layer` parses to `toml::Value` once, checks top-level keys against
the forbidden set, *then* deserializes from that `Value`. One parse, no phantom fields, and the refusal
arrives before `deny_unknown_fields` can give the misleading answer.

It matters more since `Q0a`: **`law_version` is a claim about which engine laws produced a ruleset.**
An author who could set it could make an artifact assert laws it was never built with. The guarantee
holds today only *incidentally*, as a side effect of the field's absence — which is one refactor from
gone. That is `NV-4` waiting to happen, so it gets a named, tested refusal:

```rust
ValidationError::ForbiddenField { field: "schema_version", layer: Layer::Reality }
// "schema_version identifies the ENCODING, not the rules; no layer may declare it (RLS-A4 Forbidden)"
```

**Bite-proof:** a TOML layer with `schema_version = 3` must be refused with `ForbiddenField`, and the
same file without that line must load.

---

## 2. S2 — `game-rules`, and two gates

### 2.1 IMP-Q2 resolved: a crate

> *"Is `game-rules` a crate or a module of commit-service? A crate enforces IMP-D2 mechanically; a
> module is cheaper. **Leaning crate, because the gate is the point.**"*

**Decided: crate.** A module makes IMP-D2 a promise; a crate makes it a link error. Confirmed
achievable — the dependency graph already supports it:

```
sim-core       ZERO dependencies
ruleset-core   sim-core + blake3        no fs / net / io anywhere in src/
game-rules  =  ruleset-core + sim-core  → genuinely pure, today
```

### 2.2 Target shape — every file under the IMP-D3 ceiling

```
crates/game-rules/src/
  lib.rs
  combat/{rng,stats,attack,initiative,outcome}.rs     ← was combat.rs (473)
  stats/{block,modifier,resolve,snapshot}.rs          ← was stats.rs (435)

services/commit-service/src/domain/
  {mod,payload,actor,state,law}.rs                    ← was domain.rs (609)
```

`commit-service` keeps `pub use game_rules::{combat, stats};` in `lib.rs`, so every existing
`commit_service::combat::…` import stays valid — one definition, two paths, the pattern `StatSlot`
already uses. Blast radius is 3 test files, not 30.

### 2.3 The gates — both default-DENY, because NV-3 is the shape we keep shipping

**`scripts/crate-purity-gate.py`.** The first draft of this gate was *"transitive deps ⊆ {ruleset-core,
sim-core}"* and **design review killed it**: `combat.rs:426,433` derive `serde::Serialize` on `Side` and
`EncounterOutcome`, and `ruleset-core` pulls `blake3`. A whole-transitive-tree allowlist would therefore
have to enumerate serde's and blake3's own trees — brittle against a version bump, which pushes the next
author to widen it rather than think. Worse, it would have failed on the honest case and passed nothing
extra: **the threat is a law that can reach a file, not a law that can hash.**

Four rules instead, each chosen for its polarity:

| | Rule | Polarity |
|---|---|---|
| **R1** | **workspace-internal** transitive deps ⊆ `{ruleset-core, sim-core}` | **deny-by-default** — catches the named threat (`ruleset-loader`) *and* every sibling crate written tomorrow. Transitive, so `game-rules → ruleset-core → ruleset-loader` fails; a direct-deps check would pass it. |
| **R2** | **direct external** deps ⊆ `{serde}`, each with a written reason | **deny-by-default**, low-churn: only direct deps, so a serde patch bump does not churn it |
| **R3** | no `std::fs` / `std::net` / `std::process` / `std::env` / `SystemTime` / `Instant` in `crates/game-rules/src/` | **deny-by-default over the CAPABILITY** — this is the rule that actually states IMP-D2. A law that reads a file must name a path to do it. |
| **R4** | no known async/I-O runtime anywhere in the transitive tree (`tokio`, `sqlx`, `redis`, `reqwest`, `hyper`, `tonic`) | belt-and-braces denylist; cheap, and it is the only one that is default-allow — stated as such rather than dressed up |

`serde` is allowed as a **derive/trait dependency, not a format**: doc 26's *"no serde of external
formats"* bans `serde_json`/`toml`/`bincode` in the laws, which R2 enforces by omission. Recorded in the
allowlist so the distinction survives the next reader.

**`scripts/file-ceiling-gate.py`** — IMP-D3's 400 lines, scoped by **directory**, not by file list:
`crates/{game-rules,ruleset-core,ruleset-loader,sim-core}/` + `services/commit-service/`. The 6
over-ceiling files S2 does not own get allowlist rows **carrying their reason** — visible debt, the
`IMP-D8` pattern. A file created tomorrow in those directories is covered on its first line.

**Bite-proofs:** inject `ruleset-loader` into `game-rules`' Cargo.toml → red; add a transitively-reached
crate → red; append 200 lines to a covered file → red; each restored after.

---

## 3. Slices, in order

| # | Slice | Done when |
|---|---|---|
| **1** | S1a — `classification.rs`, `classify!`, 20 rows, `Forbidden` on identity | E0027 bite-proof pasted; `ForbiddenField` refuses a real TOML and its absence loads |
| **2** | S2a — `crates/game-rules`, code moved + split, re-export shim | workspace builds; **the ruleset digest has not moved** |
| **3** | S2b — `domain.rs` → `src/domain/` | every file S2 owns is ≤400 |
| **4** | S2c — both gates + pre-commit wiring | 4 bite-proofs pasted; 0 findings on the real tree |
| **5** | docs — 26 (IMP-Q2 resolved, S1/S2 rows), 16a (§6 S1a/S1b), handoff | the tables no longer describe work that is done or scope that changed |

## 4. Invariants this run must not break

* **The ruleset digest must not move.** Slices 2–3 are pure code motion; a moved byte would prove
  otherwise. Checked against the golden digest test, which is why it is an acceptance criterion and not
  an afterthought.
* **Zero behavioural delta.** The laws are covered by 28 tests including two bite-proofs (Lex-clamp-last,
  damage-band). All green, same count, no test edited except its import path.
* **IMP-D2 both directions.** `game-rules` must not reach `ruleset-loader`; the host may, and does.
* **No new `*_ENABLED` env flag, no new table, no provider call, no secret.** This run touches none of
  the ENFORCED standards' surfaces — stated so the `/review-impl` standards gate has a claim to check
  rather than an absence to infer.
