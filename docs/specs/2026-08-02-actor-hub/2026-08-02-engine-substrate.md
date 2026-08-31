# The Engine Substrate — only what feature #1 stands on

**Status:** design contract · **Date:** 2026-08-02 (re-scoped)
**Companions:** [`2026-08-02-actor-hub.md`](2026-08-02-actor-hub.md) ·
[`2026-08-02-seams-and-triggers.md`](2026-08-02-seams-and-triggers.md) ·
[`2026-08-02-actor-dataflow.md`](analysis/2026-08-02-actor-dataflow.md) *(derivation record)*

> ## ⚠ RE-SCOPED — this file was cut by roughly two thirds
>
> **Actor hub is feature #1 of roughly a thousand.** An earlier version specified a value representation for
> money, a power-scale domain, a permille pool model, a unified ceiling, a band-delta primitive and a
> per-feature ruleset structure. **Every one of those serves a feature that does not exist**, and specifying
> them from feature #1's chair is the encroachment this round kept committing.
>
> **What is left is only what the hub cannot be built without.** Everything cut survives in the derivation
> record and the RUN-STATE, and its seam is registered in
> [`2026-08-02-seams-and-triggers.md`](2026-08-02-seams-and-triggers.md). **De-scoped, not lost.**

---

## 1. What this layer is

Everything the hub stands on and may not redefine: what counts as canon, how a value is addressed, and how
contributions combine. **It closes on mechanism and owns no vocabulary.**

## 2. The two SSOTs

| | |
|---|---|
| **RULES** | the pinned ruleset digest plus the content manifest |
| **FACTS** | the event ledger |

**Canon is what is written to the ledger.** State never written is fabricated and may be recomputed
differently tomorrow. **A snapshot is a load accelerator, never a source.**

**Single writer per aggregate/stream** — and the reason is **replay**, not concurrency: two writers make a
re-fold depend on scheduling. **Declared readers** — a sole writer is not enough, because reads form hidden
contracts that break silently. **Every derived copy carries `(reality_id, seq)`.**

## 3. Identity, and why the hashed bytes are integers

`RulesetDigest = blake3(canonical bytes)`.

> **A float inside the hashed bytes lets two machines produce two digests for one ruleset — two realities
> with identical content and different NAMES.** Server authority cannot repair that: what breaks is the
> naming scheme, not the gameplay.

**This is not a precision argument.** A world simulator does not need a bank's exactness. **A digest does not
need precision; it needs reproducibility of bytes.** Two different properties, and only the second is at
stake.

**Structurally true today, and unguarded:** `crates/ruleset-core/src/` contains no `f32`/`f64`. **No gate
prevents one being added** — `U-9`.

## 4. Ordinals — the only address

A declared quantity is addressed by an **ordinal**, assigned once and **never reused**. A name is the
author's; an ordinal is the mechanism's.

**Mechanised:** `crates/ruleset-core/src/never_reuse.rs` walks every prior epoch's table and returns
`OrdinalReuse`. **Only `0..n` is encoded**, so raising a width moves no existing digest, and lowering one is
impossible.

## 5. The fold

```
value(q) = clamp( floor(q),
                  ( base(q) + Σ flat(q) ) × max(0, 1000 + Σ pct(q)) / 1000,
                  ceiling(q) )
```

| term | |
|---|---|
| `q` | a **quantity ordinal** |
| `Σ flat` · `Σ pct` | contributions from modifier rows, **signed** |
| **percent is SUMMED, not chained** | order-independent by construction, and it kills exponential stacking. A chained product is order-dependent and needs a deterministic sort as a patch |
| `max(0, 1000 + Σ pct)` | **load-bearing** — it was once absent, and two −60 % debuffs gave a factor of −0.2 and a negative stat |
| arithmetic | **`i64` accumulator, exactly one division at emit** |
| `base(q)` | **the declaring plugin's declared initial value** — hub §3.4b |
| `floor(q)` · `ceiling(q)` | **NOT CONSULTED by the hub** — see the correction below. The clamp the fold applies is the representation's `i32` emit, reported as `CAPPED`; **the ceiling MODEL belongs to whichever feature declares a bounded quantity** (`U-4`) |

> **⚠ CORRECTED 2026-08-02, at the build.** This row said the ceiling model is **UNWRITTEN**, and that is
> **false against the tree**. `ruleset-core` ships `ResourceDecl { quantity, min, base, ceiling: CeilingBinding, … }`
> (`ruleset-core/src/resource/mod.rs:122-137`), held by `ResourceTable` over **the same ordinal space** this
> fold addresses, carried by every `Ruleset`, and already validated — `ResourceError::BadBounds` refuses a
> `base` outside `[min, ceiling]`.
>
> **The true statement is narrower: the hub does not CONSULT it.** `HubRegistry` takes the initial value
> from the attaching plugin's own `QuantityDecl`, and the fold clamps with nothing but the `i32` emit — so a
> reality can declare `ceiling: Fixed(1000)` and the fold will resolve 10 500 with no `CAPPED` record.
>
> That is a **deliberate refusal, not an oversight**: reconciling `QuantityDecl.initial` against
> `ResourceDecl.base` decides *what a pool is*, which is the resource feature's question. The consequence is
> registered as `S-18` rather than hidden. **"UNWRITTEN" is the easiest claim to make without measuring, and
> this one was made about a type in the hub's own direct dependency.**

**This is `resolve_block` generalised from a fixed slot table to ordinals** — the fold that has already been
debugged, since the `max(0, …)` floor exists because it was once missing.

## 6. Contributions

> **A contribution is DATA, never executable logic.** A plugin submits rows; the fold applies them; neither
> can run the other's code.

A conditional contribution's condition is a **declared threshold**, never a predicate grammar. **Staleness is
made impossible rather than detectable:** a modifier row is written and removed in the same transaction as
the fact that justifies it.

## 7. Nothing silent

| situation | verb |
|---|---|
| a contribution the fold cannot apply | **REFUSED**, with an event |
| a value bound by a clamp | **CAPPED**, with an event — already the practice: *"a bound ceiling is a fact in the log rather than a number nobody can explain"* |

**Two verbs, because feature #1 has two situations.** Absorption, cross-domain refusal and width refusal were
specified for value models this round no longer owns; **they return with the features that need them.**

## 8. Garbage collection

**`EntityId` is a bare `u64`** (`sim-core/src/types.rs:17`) and **carries no generation** — the generation
lives beside it, in `entities: BTreeMap<EntityId, Gen>` (`island/mod.rs:41`).

**Detection is already wired:** `Precondition::EntityAlive { id, generation }` refuses when
`self.entities.get(id) != Some(generation)` (`:424-430`), and the island-level pass discards as `Superseded`
at `:301`. **`IslandOwns` (`:449-455`) carries no generation — it detects removal, not staleness.**

⇒ **A bare `EntityId` is a dangling handle.** Staleness is detectable only when a caller carries the `Gen`
and threads it through a `Precondition`. **That threading is open work** (`U-8`).

## 9. The discriminator — mechanism or vocabulary

> **A closed set is MECHANISM if the engine's arithmetic DIFFERS PER MEMBER.**
> **It is A FEATURE'S VOCABULARY IN COSTUME if the engine treats members UNIFORMLY and only one feature
> knows their names.**

Without it, *"the engine closes on mechanism"* is unfalsifiable — any closure can be called mechanism after
the fact.

**Applied and measured, it returns a verdict on three of nineteen closed sets:** `ModifierOp` **cleared**
(`resolve.rs:84` versus `:95` — the arithmetic genuinely differs), `ModifierSource` and `StatSlot`
**convicted**. **Everything declaration-only is UNCLASSIFIED, not cleared**, because a test that cannot fail
for a subject says nothing about it. **The reduced reach is stated rather than hidden.**

**Corollary, learned expensively:** *opening* a god-list does not decouple it. **Coupling is fixed by
OWNERSHIP — whose part declares the row — not by openness.**

## 10. What this layer does NOT specify

**Value representations beyond one `i32` per ordinal · domains · scales · pools and regeneration · ceiling
models · band deltas · currency · per-feature ruleset structure.**

Each is a real question, each was worked through in the derivation record, and **each belongs to a feature
that does not exist yet.** Their seams are registered in
[`2026-08-02-seams-and-triggers.md`](2026-08-02-seams-and-triggers.md).

> **Feature #1's job is to make adding feature #2 cheap — not to pre-empt it.**
