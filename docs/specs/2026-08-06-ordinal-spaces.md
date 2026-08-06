# Ordinal spaces — the register

**Status:** proposed — **NOT sealed** · **Date:** 2026-08-06
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

Measured. `N` is the binary's ceiling; `n` is what a reality declares.

| space | `N` | where | assignment | in the hashed bytes |
|---|---|---|---|---|
| **quantity** | **32** | `ruleset-core/src/quantity.rs` | `QTY-A5` — assigned in declaration order, **never authored**; `never_reuse.rs` guards re-use across epochs | yes — `QuantityTable`, `0..n` only |
| **verb** | **16** | `ruleset-core/src/verb/table.rs` | `CMD-1` — the row's INDEX, append-only, never reused | yes — `VerbTable`, `0..n` only |
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

The correct pattern ships in the same crate, on the neighbouring space:

> *"The width is `LAYER_SLOTS`, **derived from `FoldLayer`'s own integer type** —
> not a literal `256`. … Deriving the length removes the check rather than fixing
> it, which is the stronger move: there is now nothing to keep in step."*

⇒ **Proposed:** `MAX_PLUGINS` derives from `PluginSet`'s own width, and the
`const` assertion below it goes away because there is nothing left to keep in
step. Widening the quantity table then stops silently widening the plugin
ceiling, which today it does — and which nothing would notice.

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
