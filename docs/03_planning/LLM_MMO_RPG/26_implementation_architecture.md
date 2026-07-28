# 26 — Implementation architecture standard (code vs config, module boundaries, anti-rot)

> **Status:** SEALED 2026-07-28. Governs **how** the game tier gets implemented, not what it does.
> Axioms `IMP-A1..A8`, decisions `IMP-D1..D9`, open `IMP-Q1..Q3`.
> **Prefix `IMP` registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Written after the PO stopped an in-flight implementation with the call: *"không nên implement tiếp
> vì nó sẽ bị sai về mặt kiến trúc … registry loader là để load config, story, quest … nhưng các cơ
> chế chính của game phải hard code — không phải hard code number, mà hard code kiến trúc."*
>
> Evidence base: [16 ruleset loader](16_ruleset_loader_and_registry.md) + [16a field
> classification](16a_ruleset_field_classification.md) · [21 ceilings](21_architecture_ceilings.md)
> (our own step budget) · **and the measured post-mortem of a prior project**, `chaos-backend-service`,
> which the PO built and which this design already borrows from.
>
> 🔒 **SEALED** means the *reasoning* is closed and must not be re-litigated from memory — re-read it. Open questions listed in this file remain open, and the amendment rows are **PROPOSED, not applied**: no feature spec was edited by this arc.


---

## 1. The failure this exists to prevent, with its numbers

> ⚠️ **BANNER CORRECTED 2026-07-28 ([QTY-D7](35_quantity_architecture.md)). The previous version of
> this banner overstated its case and was used as load-bearing evidence; do not quote the old form.**
>
> What it claimed: that a re-measurement (1.384 ns closed / 1.496 ns open / 11.952 ns HashMap) showed
> the open design costs only **1.08×**, so *"the performance argument for the closed-10 decision does
> not stand"*. Two problems, both found by the adversarial audit:
>
> 1. **That re-measurement is UNVERIFIED.** Its own method note records *"probe file written, run,
>    then **deleted**"* ([27a:782](27a_stress_test_agent_reports.md)); no benchmark file for this
>    comparison exists in the repo and `StatId` has zero hits in `.rs`. It is prose, not a harness.
> 2. **The two figures measure different competitors.** 88× is closed-array vs **`HashMap`**;
>    1.08× would be closed-array vs an **interned-ordinal array**. chaos's own *committed* criterion
>    output supports the former (8.2 ns for 50 ordinal reads vs 704.9 ns for 50 `HashMap<u64>` reads).
>    **88× was never an argument against ordinal-interned openness** — it is an argument against a
>    map, and every design this repo is considering keeps the dense array.
>
> **What stands:** the code/config line (IMP-A1); the closed *derived* set; and `CombatStats::from_block`
> projecting once (IMP-A3) so the hot path performs no stat lookup at all. **What changed:** the
> closed-10 decision is re-grounded on [QTY-A3](35_quantity_architecture.md) — laws bind to **roles**,
> and a role must be named to be matched. Openness belongs one layer down, at L2, where it does not
> compete with the dense array at all.

A prior project (`chaos-backend-service`) specified actor stats dynamically — string-keyed, HashMap
backed — and had to retreat to fixed arrays. Its own benchmark, 1 000 000 iterations:

| Operation | HashMap | Direct field | |
|---|---:|---:|---|
| stat access | **125.78 ns** | **1.42 ns** | **88× faster** |
| modification | 1 798.43 ns | 353.26 ns | 5.1× |
| full iteration | 5 571.79 ns | 395.94 ns | 14.1× |

**Put that against our own budget** ([21](21_architecture_ceilings.md)): an island step is
**176–229 ns** and a precondition check is **~4 ns**.

* One HashMap stat read (125 ns) is **~70 % of an entire island step**.
* One damage resolution reads ~8 stats across two actors ⇒ **~1 µs**, or **5× the whole step
  budget**.

So a dynamically-typed stat path does not cost "a bit more" — it moves combat from nanoseconds to
microseconds and makes the CEI-5/CEI-6 ceilings meaningless. **This is not a micro-optimisation
argument. It is a change of order.**

### 1.1 The opposite failure, also observed in the same repo

That repo also ended up with `cache_keys.yaml`, `bucket_display_names.yaml`,
`cap_mode_display_names.yaml` — configuration for *display strings and cache keys*. Config for
config's sake has its own cost: nothing is type-checked, every bug becomes "the data is wrong", and
nobody can say what correct data looks like.

**Both failures come from the same missing decision: nobody drew the line.** This document draws it.

---

## 2. IMP-A1 — the line

> **Code owns SHAPE. Config owns VALUES.**
>
> The boundary is *not* "is it data". It is **who may add a new variant**: if adding one requires an
> engine release, it is a closed set and lives in code. If an author may add one without touching
> the engine, it is content and is loaded.

This is already how the specs are written; it has simply never been stated as the implementation
rule. `DF7-A1` says authors declare *how their kinds project into* slots and never add a slot.
`AGT-A2` closes the tool vocabulary. `ABL_001` ships a closed 9-variant `EffectOp`. `PL_006` closes
`StatusFlag`. Every one of these is the same decision made independently — IMP-A1 names it.

### IMP-A2 — the three-question classifier

Applied to every new field, before it is written:

1. **Is it read on the hot path** (per action, per tick, inside `apply`)? → it must be reachable by
   **array index or enum match**. Never a map lookup. *(§1's numbers.)*
2. **Can an author add a new KIND of it without an engine release?** → yes ⇒ content, loaded.
   no ⇒ closed set, in code.
3. **Is it a NUMBER inside an already-known shape?** → config, loaded, and it must not be a literal
   in the engine.

The three are ordered deliberately: (1) can veto (2). A thing authors would like to extend, but
which is read per-action, gets the **projection treatment** below rather than a hot-path map.

### IMP-A3 — projection, not hot-path polymorphism

**This is where LoreWeave already improves on the prior project, and it should be preserved
deliberately rather than by accident.**

`chaos-backend-service` settled on a *Hybrid*: core resources in an array, custom/modder resources in
a HashMap — **and the HashMap stayed on the hot path** for anything custom.

DF07 does something strictly better: an author declares how *their* progression kinds **project into
the closed slot set**, and that projection runs **at resolution time (cold)**, producing a dense
`[i32; 10]` that the hot path reads by index. Extensibility is paid for **once per snapshot**, not
once per read.

> **IMP-A3 — extensibility is resolved into a fixed shape ahead of the hot path, never dispatched
> inside it.** If a feature seems to need open-ended lookup during `apply`, the correct move is to
> add a resolution step, not a map.

---

## 3. IMP-A4 — what is loaded, concretely

Loaded (registry/config — the PO's *"config, story, quest … things well-suited to generation"*):

| Loaded | Why it qualifies |
|---|---|
| Stat **values** — slot bases, archetype blocks, clamps, tuning | numbers inside a known shape (Q3) |
| Ruleset **numbers** — damage constants, `ko_duration_rounds`, TTLs, budgets | same |
| **Content** — items, abilities *as data*, NPC archetypes, spawn tables, loot tables | authors add these freely (Q2) |
| **Narrative** — story, quests, dialogue, place descriptions | generation-friendly, never hot-path |
| Per-slot **declarations** — how author kinds project into slots (`StatSlotDecl`, `StatTerm`) | resolved cold (A3) |

Hardcoded (**architecture**, not numbers):

| In code | Why |
|---|---|
| `StatSlot` (10), `StatBlock = [i32; 10]` | hot path, closed set |
| `CombatPayload`, `EffectOp`, `StatusFlag`, `DiscardReason`, `Precondition` | closed dispatch vocabularies |
| The damage law-chain, initiative, hit/dodge — the **order and structure** | laws, not values; order is LOCKED for V1+ |
| The `Domain` trait, the island step, admission stages | the engine itself |

**IMP-D1 — a law's STRUCTURE is code; a law's CONSTANTS are config.** The 4-step chain's *order* is
locked in `combat.rs`; `strike_power`, the variance band and `crit_mult` come from the ruleset. This
is the distinction the PO drew and it is the one that keeps both failures away at once.

---

## 4. IMP-A5..A6 — module boundaries

Today `commit-service/src/domain.rs` is **539 lines** holding payloads, events, `Actor`, `State`,
`Rules`, the `Domain` impl, `apply`, `check`, and helpers. That is the rot starting, and it starts
exactly this way — nothing is wrong yet, and every next addition has an obvious home in the file
that already exists.

**IMP-A5 — one crate per stable boundary, one module per concern.** The target shape:

```
crates/
  ruleset-core/       types: Manifest, Ruleset, Digest, Provenance      (no I/O)
  ruleset-loader/     provider stack, presets, interning, validation     (I/O)
  game-rules/         the LAWS: combat chain, initiative, stat resolution
                      — pure, no I/O, no serde of external formats
services/commit-service/
  src/domain/         the Domain impl: payload, events, state, apply, check
  src/admission/      stages
  src/manager/        supervisor
```

**IMP-D2 — `game-rules` must not depend on `ruleset-loader`.** Laws take a resolved `Rules` by
reference (RLS-A12) and know nothing about where it came from. A law that can read a file is a law
that can be slow, fallible, and untestable.

**IMP-D3 — ceilings, enforced not aspired:** a source file over **400 lines**, or a module with more
than one of {types, laws, I/O, orchestration}, is a gate finding. Ceilings are arbitrary; *having*
one is not — an unbounded file has no moment at which anyone is obliged to split it.

---

## 5. IMP-A7 — anti-rot has to be mechanical

This repo's whole meta-pattern is **rule + SoT + gate + test**. Aspirational rules decay; the
`ai-provider-gate` and `design-lint` are the proof that mechanical ones do not.

**IMP-D4 — `scripts/hot-path-gate.py`**: a `HashMap`/`BTreeMap` lookup inside the island step path
(`Domain::apply`, `Domain::check`, `game-rules`) is a finding. Allowlist entries carry a reason.
*(Note: `BTreeMap` on `CombatState.actors` is a keyed collection over entities, not a per-stat
lookup — the gate targets stat/attribute access, and this distinction must be encoded, not assumed.)*

**IMP-D5 — `scripts/no-magic-game-constant.py`**: a numeric literal used as a game value outside the
loader is a finding. Same shape as the provider gate that already blocks hardcoded model names.
Bootstrapping: the existing literals get an explicit allowlist with a `TODO(IMP)` and shrink to zero
as the loader lands — visible debt rather than invisible debt.

**IMP-D6 — the digest must become real.** ✅ **DONE 2026-07-28 (F1).** `RulesetDigest([0u8; 32])`
appeared in **15 places**. An all-zero digest means RLS-A13's pin is inert: two realities with
different rules produce indistinguishable events, and replay cannot detect that the rules changed
underneath it.

> **What the fix taught, worth keeping:** the literal survived because it *looks like a value*.
> Nothing distinguished *"the loader is not wired here yet"* (a bug) from *"this domain genuinely has
> no content ruleset"* (the kernel harness), so both were spelled the same way and neither was
> visible. The resolution is the same one `MAX_HIT` got in the damage chain: **a declared zero has a
> name and a reason; an emergent one is a number nobody can explain.** `RulesetDigest::UNPINNED` is
> the named case, `scripts/zero-digest-gate.py` bans the anonymous literal repo-wide and bans
> `UNPINNED` outside `crates/sim` + tests. The gate did not wait for the loader — F1's own exit
> criterion is what it enforces.

---

## 6. IMP-A8 — build order, and what "done" means at each step

The PO's order — **foundation → SDK → standard → detail** — with an evidence-based exit for each.
Nothing advances on "the code is written".

| # | Layer | Delivers | Done when |
|---|---|---|---|
| **F1** ✅ **2026-07-28** | `ruleset-core` | Ruleset + REAL digest + Provenance. **No `Manifest`** — a manifest with no resolver is a shape with no consumer; it lands with F2. **`D1`'s constant sourcing was pulled forward into F1**: a digest over a struct holding no game constants is *worse* than an inert one, because it answers "did the rules change?" with a confident No | **met** — `v3_two_different_rulesets_are_distinguishable`; zero-digest count is **0 everywhere**, not just outside tests (the harness case is the NAMED `RulesetDigest::UNPINNED`, scope-checked by `scripts/zero-digest-gate.py`) |
| **F2.1** ✅ **2026-07-28** | `ruleset-loader` | layer stack · TOML artifacts · normalization · load-time validation · the content-addressed **immutable store** · the canonical **decoder**. **Deferred with reasons:** tombstones + `UnionById*` (no collections in `Ruleset` to merge yet), presets-as-scoped-DB-resource, the `(reality, epoch)` registry, `forge_override`-as-event | **met** — `a_reality_loads_its_ruleset_from_a_file_and_the_digest_follows` reads a real `.toml` from disk; the digest was already landing in the envelope since the `B` slice |
| **S1** | field classification | 16a's 64 fields wired: layer floors, `Tunable` vs `AdditiveOnly` | an over-reaching override is REFUSED, with a test |
| **S2** | `game-rules` extraction | laws move out of `domain.rs`, take `Rules` by ref | `game-rules` has no I/O dependency, enforced by a gate |
| **D1** | detail | `default_value` / `archetype_melee` / `CombatRules` read from the ruleset | the magic-constant allowlist is empty for combat + stats |

**IMP-D7 — slices 1–2 are kept, not reverted.** The laws are correct, spec-quoted and covered by 28
tests including two bite-proofs (Lex-clamp-last; damage-band). They already read through `CombatStats`
/ `CombatRules` rather than embedding literals *inside* the formulas — so the wrong thing is the
**source** of three values, in three named places, and D1 replaces exactly those. Reverting would
discard the tested laws to fix a supply chain.

**IMP-D8 — but the debt is made loud immediately.** Those three sites get `TODO(IMP-D5)` plus an
allowlist row, so "we already have it, let's just continue" stops being frictionless. That is the
real risk in keeping them, and it is a discipline problem rather than a technical one.

> **Closed 2026-07-28 (F1).** The `TODO(IMP-D5)` sites are gone: `MAX_HIT`, the hit floor/ceiling and
> base, the variance band, the elemental/resist/defend factors, the four action-value multipliers,
> the ten slot defaults, the move-range tuning and the melee archetype all resolve from
> `Ruleset::engine_default()` and are hashed. **`scripts/no-magic-game-constant.py` (IMP-D5) is still
> unbuilt** — it is now *possible*, which it was not before, and it is what would keep the count at
> zero. Also unbuilt: **IMP-D4** `hot-path-gate.py`, and **IMP-D3**'s 400-line ceiling has no gate
> (`domain.rs` 592 · `combat.rs` 456 today — both already over before F1, and F1 grew them; the split
> is `S2`).

**IMP-D9 — no new game feature until F1+F2 land.** Slices 3–5 of the encounter plan (threat, grid,
abilities) are on hold. Each would otherwise add its own literals to the pile, and each is a
*consumer* of the ruleset — building consumers before the supply chain is precisely the inversion
that prompted this document.

> **IMP-D9 EXTENDED 2026-07-28 — the hold now also covers `stat_archetypes`, templates and F3, and it
> extends to `Q0` ([35 §12](35_quantity_architecture.md)).** F1+F2 landed and the F-track was about to
> continue into content. A four-audit review found the same inversion one layer down: all three of
> those slices bind content to a **derived set that cannot grow**. Moving `SLOT_COUNT` today makes
> every stored `.canon` undecodable (`canon.rs:213-226`) and reds the golden digest with no legal
> repin, and `upcaster.rs` versions *event* schemas, not rules.
>
> `Q0` — a **length-declared canonical encoding** plus `upcast_rules` plus the epoch-switch path
> ([QTY-A10/A11](35_quantity_architecture.md)) — is what converts every future L1 addition from a
> spine break into an ordered event. **It must land before any production reality is created**,
> because after that the same change is a data migration across live realities.
>
> This is the same call IMP-D9 already makes, applied to itself: **do not build consumers of a supply
> chain that cannot be extended.**

---

## 7. Open

| Id | Question |
|---|---|
| ~~**IMP-Q1**~~ ✅ | Ruleset format. **RESOLVED 2026-07-28: TOML** (`IMP-D10`). YAML rejected — its scalar coercion (`no` → bool, `1.0` vs `1`, sexagesimals) is a determinism hazard in an artifact whose whole job is to be hashed, and it is what the prior project drowned in. JSON rejected — **no comments**, and a rules file's most valuable content is *why this number*. RON rejected — unreadable to anyone who does not already write Rust, and rulesets are meant to be authored by non-engineers. TOML: comments, unambiguous scalars, **line-oriented diffs** (the stated criterion), already a pinned workspace dep. Its weakness is deep nesting — a real cost the day `Ruleset` grows collections, and cheaper than any of the three failure modes above |
| **IMP-Q2** | Is `game-rules` a crate or a module of commit-service? A crate enforces IMP-D2 mechanically; a module is cheaper. Leaning crate, because the gate is the point |
| **IMP-Q3** | Hot-reload of rules — out of scope for V1? Digest-pinning (RLS-A13) implies rules change only between realities/versions, which suggests no |
