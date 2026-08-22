# Ordinal spaces — the register

**Reconciles:** Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3** · **Actor hub** — 🔴 **not done
when written.** `DP-A7` fixes a cache-key format (`dp:{reality_id}:{tier}:{aggregate_type}:…`)
that is itself an ordinal-bearing namespace this register never counted, and `DP-T0..T3` is a
closed engine set of exactly the kind §6 enumerates. Neither appears in this document.

**Status:** measurement — **§4c (`LIM-1`) is SEALED and BUILT**; everything else is
proposed · **Date:** 2026-08-06
**Companions:** [command hub](2026-08-06-command-hub.md) *(sealed)* ·
[actor hub](2026-08-02-actor-hub/2026-08-02-actor-hub.md) ·
[RUN-STATE](../plans/2026-08-06-game-tier-build-RUN-STATE.md)

> This file **counts what exists**. Every number in it was measured at
> `11dda028c`, not remembered. Where it proposes anything, it says so.

---

## 1. Why this exists

Three measurements, taken together:

```
docs/specs/2026-08-02-command-interaction-dataflow.md:653
  O-CI-5 · A sixth ordinal space, against §27.4's stated objection.

docs/specs/2026-08-02-command-interaction-dataflow.md:252
  🔴 CORRECTED — I wrote "a sixth ordinal space" and the honest count is TEN.
```

**One document says six, then corrects itself to ten, and does not list either
set.** `AF-8` separately found `RefKindMask` *"unpriced and outside the six
ordinal spaces"* — outside a set nobody had enumerated. And `M2` shipped a `cue`
ordinal with **no width constant, no repin log and no argument**, while every
neighbouring space in the same tier carries all three.

A count that moves by four inside one file is not a count. It is the tell that
**the word is naming two different things**, and §2 is that distinction.

## 2. The distinction that explains the disagreement

> **An ordinal space is a numbering. Who may add a number to it is the question
> that splits the word in two — and the two halves have opposite costs.**

| | **AUTHOR-EXTENSIBLE** | **CLOSED ENGINE SET** |
|---|---|---|
| who adds a member | **content** — an author writes a row | **the engine** — a release |
| what the width is | a named constant in the binary (`N`) | the variant count |
| what is hashed | **`n`, the declared count** — never `N` | the discriminant of each member used |
| cost of one more | a line of TOML | a schema bump, a codec arm, a mirror on every consumer |
| cost of removing one | **impossible** — `QTY-A10(c)` | impossible, same |

Counting these together is why six became ten: the second kind is large and
grows quietly, and it is not what `O-CI-5`'s objection was about. **`§27.4`
objected to a new AUTHOR-EXTENSIBLE space**, which is a real cost on every
reality; a new closed engine set is a cost on the engine only.

And measurement found a **third** kind that neither half describes — §5.

## 3. The register — AUTHOR-EXTENSIBLE

Measured. `N` is the binary's **capacity**; `n` is what a reality declares —
and since `LIM-1` (§4c) the reality also declares its own **limit** on `n`, in
`[limits]`. This table is now `OrdinalSpace` in `ruleset-core/src/limits.rs`
rather than only prose; a new space that does not appear there fails to compile
in four places.

| space | `N` | `[limits]` key | where | assignment | in the hashed bytes |
|---|---|---|---|---|---|
| **quantity** | **32** | `quantities` | `ruleset-core/src/quantity.rs` | `QTY-A5` — assigned in declaration order, **never authored**; `never_reuse.rs` guards re-use across epochs | yes — `QuantityTable`, `0..n` only |
| **verb** | **64** *(was 16 — §4c)* | `verbs` | `ruleset-core/src/verb/table.rs` | `CMD-1` — the row's INDEX, append-only, never reused | yes — `VerbTable`, `0..n` only |
| **tier within a kind** | **64** | `ruleset-core/src/progression/mod.rs` | a decode bound, not a layout one | via the progression digest |
| **cue** | **= verb** | `ruleset-core/src/verb/table.rs` | authored on a verb row, **PER-REALITY** (PO, sealed 2026-08-06). `QTY-A14` applies: cue 3 in one reality means nothing in another | yes — inside `VerbTable`'s rows |

> **The cue's width is DERIVED, not chosen**, and it is the pattern §4 says
> `MAX_PLUGINS` should have used. Every cue in existence comes from a verb row
> and there is exactly one per row, so a reality with `N` verbs cannot need an
> `N+1`th distinct cue. Deriving it removes the thing to keep in step.
>
> **There is deliberately no cue TABLE.** A reality declares cue *numbers* and
> nothing else; the words live in presentation content, in whatever language the
> reader asked for. `AUTHOR-1` decides it — a second table to write is a cost
> that buys only what a presentation file already holds.
>
> ⚠️ **When a non-verb emitter arrives** — a status lapsing, an encounter ending
> — the derivation stops being true and must change in one place with a reason.
> `a_cue_past_the_declared_space_is_refused` asserts the equality, so that change
> cannot be silent.

**And three constants that are ALIASES of `quantity`, two of them correctly:**

| alias | argued as | verdict |
|---|---|---|
| `MAX_DECLARED_RESOURCES` | *"a pool **is** a quantity — one identity, one ordinal"* | ✅ **the same space.** Correct, and the module argues it at length |
| `MAX_DECLARED_PROGRESSION_KINDS` | *"a progression kind **is** a declared quantity"* | ✅ **the same space.** Same argument, made explicitly |
| `MAX_PLUGINS` | *"tied on purpose, so the two ceilings move together instead of drifting apart"* (`D-255`) | 🔴 **a DIFFERENT space, aliased for a reason that is not identity** — see §4 |

## 4. What the register catches on its first run

**`MAX_PLUGINS` derives its width from the wrong thing, and the right derivation
already exists eight files away.**

A plugin is not a quantity. `MAX_DECLARED_RESOURCES` and
`MAX_DECLARED_PROGRESSION_KINDS` are aliases because *the thing IS a quantity* —
one identity, one ordinal, and `QTY-A5` exists to stop two numbering schemes for
one identity. `MAX_PLUGINS` is aliased for a different reason: *"so the two
ceilings move together"*. That is exactly the shape `MAX_DECLARED_VERBS`' own
doc refuses:

> *"A verb is a different thing in a different ordinal space, so tying the two
> would be a **coincidence pretending to be an invariant**."*

**The number 32 is right; the derivation is wrong.** The plugin ceiling is forced
by `PluginSet` being a `u32` bitmask — 32 bits, 32 plugins — and the crate
already states that in a `const` assertion directly below the alias. So the
width has a real source and is aliased to an unrelated one.

> 🔴 **CORRECTION to this section's first draft, 2026-08-06.** It ended *"widening
> the quantity table silently widens the plugin ceiling today, and nothing would
> notice."* **The second half is FALSE.** The `const` assertion below the alias
> notices: its own comment records it **measured failing at 16 and at 64**, with
> `error[E0080]` naming the line. It is neither vacuous nor unbitten, and calling
> it absent was the register repeating the error the register exists to catch.
>
> **The real defect is smaller and of a different kind — a COUPLING, not a
> safety hole**, and measuring both numbers is what shows it:
>
> | | where 32 comes from |
> |---|---|
> | `MAX_DECLARED_QUANTITIES` | **CHOSEN.** Doc 35 §4.2 measured the per-actor array: `[i32;32]` puts `Actor` at ≈280 B, `[i32;64]` at ≈408 B. `quantity.rs` adds *"raising it is cheap and does not move any existing digest"* |
> | `MAX_PLUGINS` | **FORCED.** `PluginSet(u32)` holds exactly 32 bits |
>
> The alias makes the FORCED number look as though it follows the CHOSEN one. So
> an author raising quantities to 64 — which `quantity.rs` calls cheap — hits a
> compile error in `actor-hub`. The error is correct and the shape is backwards:
> the quantity table is blocked by a bitmask that has nothing to do with it, and
> the only ways through are widening `PluginSet` to a `u64` (an unrelated change)
> or breaking the alias.
>
> **The proposed fix is unchanged and its reason is now sharper:** deriving
> `MAX_PLUGINS` from `PluginSet`'s own width DECOUPLES them. Quantities go to 64
> and simply work; plugins stay at 32 because that is what a `u32` holds. And the
> assertion goes away because it can no longer fail — which is exactly what
> `LAYER_SLOTS` says deriving a width is for. There is no reason plugins must not
> exceed quantities: `PluginDecl` permits a plugin that declares **no** quantities
> at all, so the two spaces have no relationship to preserve.

The correct pattern ships in the same crate, on the neighbouring space:

> *"The width is `LAYER_SLOTS`, **derived from `FoldLayer`'s own integer type** —
> not a literal `256`. … Deriving the length removes the check rather than fixing
> it, which is the stronger move: there is now nothing to keep in step."*

⇒ **Proposed:** `MAX_PLUGINS` derives from `PluginSet`'s own width, and the
`const` assertion below it goes away because there is nothing left to keep in
step.

## 4b. `MAX_DECLARED_VERBS = 16` is the one ceiling that is genuinely too tight

**PO, 2026-08-06:** *"it should not be hardcoded, because every reality is a
different size — hardcode it and there is no way to widen or narrow it later."*

**Two thirds of that is already answered by `QTY-A6`, and the last third is a
real mistake of mine.**

| | |
|---|---|
| **the size ALREADY varies per reality** | `n` is in the hashed bytes, `N` is in the binary. Only `0..n` is encoded, so a reality declaring 4 and one declaring 20 already differ in the artifact |
| **widening is a RECOMPILE, not a migration** | it moves **no existing digest**, because the tail was never encoded |
| **narrowing is forbidden by DATA, not by laziness** | a stored ordinal 40 becomes unreadable (`QTY-A10(c)`). The widening direction is the reversible one |
| **the array WIDTH is the part that is fixed, and it is priced** | making it per-reality costs `Copy` on `Actor`, makes `size_of` **16 bytes for every `n`** — the `QTY-A6 ⊥ QTY-A12` trap, which kills the guard — and adds a pointer chase to the fold. `QTY-A6.1` already took this trade: `O(n)` **per ACTOR** is what must be cheap |

**And here the objection lands on something real.** `MAX_DECLARED_VERBS = 16` is
a literal I chose, and the argument written for it explains why it is *cheap*,
not why it is *16*. Worse:

> **The cost that constrains quantities is per-ACTOR. The verb table is
> per-RULESET, interned once.** `[i32; 32]` on `Actor` is 128 B × every resident
> actor — 1.28 MB at ten thousand. `[VerbDecl; 16]` on `Ruleset` is 1088 B **once
> per reality.** Raising verbs 16 → 64 costs ~3.2 KB resident per reality and
> **zero encoded bytes.**

**Sixteen verbs is small for a game** — a modest one has more than sixteen
actions. ⇒ **I applied a per-actor discipline to a per-reality table**, and this
is the one ceiling in the tier that could actually bite an author.

**The only thing that resists widening it is `size_of::<Ruleset>() <= 3696`**,
which would go to roughly 6960 at 64. That assertion firing is the guard doing
its job: it forces this conversation rather than letting the number drift. A
repin with a reason is the whole mechanism.

Note that `MAX_DECLARED_CUES` is derived from this constant, so raising it
widens the cue space too, correctly and automatically.

## 4c. `LIM-1` — SEALED 2026-08-06. The ceiling moved to the manifest

**PO, immediately after reading §4b:**

> *"A hard ceiling should be pushed out for the reality manifest to decide,
> because we only build a world engine. A hardcoded number should be DATA and
> INGESTED, not a magic number inside the world engine. That is rot — if you find
> it, fix it rather than skip it."*

That reframes §4b's finding. §4b treated `16` as *the wrong number*; the PO's
reading is that it was **the wrong kind of thing**, and raising it would have
fixed one instance of a defect the tier has everywhere.

### The defect, in one sentence the engine used to say

```
40 declared quantities exceeds this engine's capacity of 32
```

**The engine is answering a question that is not its to answer** — *how big may
this world be?* — with a number chosen by whoever wrote the crate. Every reality
on the platform inherited one developer's guess, and could say nothing in either
direction: a small reality could not declare itself small, a large one could not
declare itself large without a code change to a crate it does not own.

One number was doing two incompatible jobs:

| | who decides | what it means | how it changes |
|---|---|---|---|
| **capacity** — `OrdinalSpace::capacity()` | the engine | *this binary's inline array is `N` wide* | rebuild |
| **limit** — `Limits`, from `[limits]` in the manifest | **the reality** | *this world declares at most `n`* | edit a `.toml` |

**Only the second was ever a design decision, and it was living in the wrong
repository.**

### What shipped

`crates/ruleset-core/src/limits.rs` — `OrdinalSpace` (the register in §3, now in
code) and `Limits`, folded through `RulesetPatch::apply` from a `[limits]` block.
Three refusals with **two audiences**, which is the whole point of the split:

| refusal | says | audience |
|---|---|---|
| `AtLimit` | *`brace` does not fit: your world declares 1 verb* | the author, in the file they are editing |
| `BelowDeclared` | *this layer narrows to 2 and 3 are already declared* | the author, across layers |
| `AboveCapacity` | *you asked for 200; this build holds 64 — rebuild* | whoever deploys. **Not** a design verdict |

Applied **before** the rows of its own layer, so an author raises a ceiling and
spends it in one file. Enforced per row, so the message names the row that did
not fit rather than a count.

### Three decisions inside it, each with its reason

**Limits are NOT in the digest.** A limit is read once, at ingest, and never
again — no law reads it, no step reads it, and a resolved `Ruleset` is immutable.
`RLS-A15`'s precedent (same rules, different provenance ⇒ same digest) applies
unchanged, and a divergence is still visible where it matters: if two realities
with identical rows declare different limits and an author adds a row to each,
the one that accepted has a different ROW SET, which *is* hashed. The digest
moves when the behaviour does, not before. `QTY-A10(c)` settles the tie — hashing
is irreversible, would move every existing reality's digest, and would record a
number nothing reads. `Limits` therefore has **no `CanonEncode` impl**: the same
structural exclusion `Provenance` uses, so including it would not compile.

**Limits are not stored on `Ruleset` either.** They are a fold accumulator in
`resolve`. After the fold there is nothing left for them to constrain, so a field
would be a shape nobody reads.

**Capacity stays a compile-time constant, deliberately.** It is an inline array
width, so runtime data means a heap allocation — forbidden by name
(`QTY-A6 ⊥ QTY-A12`). A per-deployment knob (`option_env!`) dodges the allocation
and is refused for a sharper reason: **two nodes of one cluster built with
different capacities would disagree about whether a manifest is valid.** A world
that loads on one node and is refused on its neighbour is worse than a rebuild.

### And §4b's number, now that it means something else

`MAX_DECLARED_VERBS` 16 → **64**, and the repin `size_of::<Ruleset>() <= 3696`
→ **6960** (measured: `VerbDecl` 68 B, `VerbTable` 1090 → 4356). The assertion
refused the change and forced the entry to be written, which is the entry above
it demonstrated rather than restated — *"the assertion is not here to forbid
growth."* **The repin is not what changed; the authority is.**

**What the register catches that a raise would not have:** raising 16 → 64 fixes
one constant. `LIM-1` fixes the *class* — every author-extensible space now has a
manifest key, and `OrdinalSpace`'s four exhaustive matches make a new space a
compile error until it is given one.

## 5. The third kind the measurement found — RUNTIME-DERIVED

Two numberings are neither authored nor a closed engine set. **They are computed
at boot and are NOT in the hashed ruleset.**

| space | derived from | in the digest |
|---|---|---|
| **plugin ordinal** | `RealityRules::resolve` — one plugin per feature; `M1` declares exactly one, `COMBAT_PLUGIN = 0`, a `const` in `binding.rs` | **no** |
| **fold layer** | the feature's `PluginDecl::fold_layers`; `M1` declares one, `BASE_LAYER = 0` | **no** |

> ⚠️ **This is worth stating rather than discovering.** `RLS-A13` says an event is
> pinned to the rules that produced it, and an actor's stored quantity array is
> indexed by an ordinal that is partly **not in that pin**. Today it cannot vary —
> the derivation is two constants and one plugin — so there is no live defect.
> **The hazard is that it cannot vary *yet*.** The day a reality's plugin set is
> content rather than a constant, two realities could share a digest and derive
> different plugin ordinals, and a stored `attached` bitmask would name a
> different feature. That is `QTY-A14` (*an ordinal is meaningless without its
> `(reality, digest)`*) arriving in a space the digest does not cover.
>
> **Not fixed here, and not deferred silently: it is the first thing this
> register exists to have said out loud.**

## 6. The register — CLOSED ENGINE SETS

Measured variant counts. Each is a set an author picks from and never adds to,
and each extension is an engine release plus a mirror on every consumer.

| set | members | where |
|---|---|---|
| `StatSlot` | **10** | `ruleset-core/src/slots.rs` — `DF7-A1`; doc 31 `R02` proposes making it ruleset-declared, **PROPOSED, not applied** |
| `RefusalReason` | **6** | `commit-service/src/domain/payload.rs` — mirrored in `turn.schema.json` and the TS consumer |
| `EngineRole` | **4** | `ruleset-core/src/resource/mod.rs` — `M1` |
| `RegenType` | **3** | `ruleset-core/src/resource/mod.rs` |
| `TargetRole` | **2** | `ruleset-core/src/verb/mod.rs` — `M2` |
| `ZeroBehaviour` | **2** | `ruleset-core/src/resource/mod.rs` — **no consumer yet**, `D-ZERO-BEHAVIOUR-UNREAD` |
| `OpKind` | **2** | `ruleset-core/src/modifier.rs` |
| `DomainEventType` | **10** | `contracts/game-wire/turn.schema.json` — the contract is the SSOT; both languages mirror against it, never against each other (`FATAL-1`) |

## 7. Unpriced — the two the register was written to find

| | |
|---|---|
| ~~**`cue`**~~ | ✅ **PRICED 2026-08-06 — see §3.** The PO sealed **per-reality**, and the width is `MAX_DECLARED_CUES`, **derived** from `MAX_DECLARED_VERBS`. It was unpriced because nothing counted ordinal spaces, which is what this register exists to be |
| **`RefKindMask`** | Named in the design, **0 occurrences in code**. `AF-8` found it *"unpriced and outside the six ordinal spaces"*; this register is what it was outside OF. It belongs to the OFFER stage, which is unbuilt |

## 8. How a row says which space it addresses

**Today it does not have to, because there is one.** Every `EffectRow`,
`RequirementRow`, `ModifierRow` and `DerivationRow` addresses the QUANTITY space
and nothing else, so the space is implied by the field's type.

That is why `EffectRow` has no `kind` discriminant — [the command hub's §3
closure rule](2026-08-06-command-hub.md): *one primitive per BUILT DOOR*, and one
door is open.

> **Proposed, and this is the part that unblocks the features:** the second door
> is where a row first has to NAME its space, and the shape is already fixed by
> everything above — **a row is `{ space, ordinal, operand }`**, where `space` is
> a member of a closed engine set and `ordinal` is meaningless without it
> (`QTY-A14`). `Delta` today is that row with `space` implied.
>
> A feature therefore opens a door by **claiming a space and declaring what its
> ordinals mean** — and the substrate learns neither. That is the same coupling
> the actor hub already has with its plugins, one level up, and it is why the
> features are not circularly dependent: see §9.

## 9. What this settles about the feature ordering

The features look mutually dependent when the coupling is stated in NOUNS — *the
substrate needs statuses; statuses need the substrate.* Stated in SHAPE it is not
a cycle:

> **A feature and the substrate are coupled only through an ordinal space.** The
> substrate declares the space and the row shape; the feature declares what an
> ordinal MEANS; content assigns the name. **Neither needs the other to exist
> first.**

This project has already done it twice without naming it as a rule:

- **`actor-hub` shipped with ZERO consumers.** It folds quantities without
  knowing what a quantity means, and the first feature arrived two months later
  (`M1`).
- **`M2`'s substrate resolves verbs** without knowing what a verb means; the
  first verb arrived as a row in a TOML file.

Both are held by shipped gates rather than by intent — `hub-vocabulary-gate` (the
hub names no ordinal) and `engine-vocabulary-gate` (the engine names no
quantity). **The rule is not new. Only this statement of it is.**

⇒ The remaining work stratifies rather than cycling:

| tier | needs | items |
|---|---|---|
| **0** | nobody | this register · arity · a second relation (`at_most`) · the roll's verb term · the `submitter_class` contradiction |
| **1** | one external fix | roles + offer ← the subject source (`ChannelRoom.ts:375` binds every unmapped authenticated user to one actor) |
| **2** | a feature to exist | status relations · a price that is not a quantity · `O-CI-4`'s reachable subject · six effect doors |

Tier 2 gets **seams, never implementations.**

## 10. What this file does NOT decide

- **Whether `MAX_PLUGINS` is repinned.** §4 argues the derivation is wrong and
  proposes the fix; the edit is not made here.
- **How many spaces there should BE.** This counts what exists. `O-CI-5`'s
  question — whether a new author-extensible space is worth its cost — is
  unchanged and still the PO's.
- **The row shape's second field.** §8 proposes `{ space, ordinal, operand }`
  and says why; it is not sealed, and no code carries it.
