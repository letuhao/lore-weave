# Value-model analysis — for any feature that needs a number spanning orders of magnitude

> ## THIS IS ANALYSIS, NOT A DECISION
>
> Kept because it cost real effort and a later feature can reuse it instead of re-deriving it.
> **It binds nobody.** The owning feature may take any of it, amend it, or discard it outright.
>
> **What is DECIDED lives in the contracts** — [`2026-08-02-actor-hub.md`](../2026-08-02-actor-hub.md) and
> [`2026-08-02-engine-substrate.md`](../2026-08-02-engine-substrate.md) — and the measured seams live in
> [`2026-08-02-seams-and-triggers.md`](../2026-08-02-seams-and-triggers.md).

> **What this file is.** The pre-seal engine-substrate draft. Its §§5, 8, 9, 10 and 12 — **power creep as a
> DOMAIN error rather than a width error · the log domain and its measured limits · permille pools · a
> unified ceiling model · band deltas · per-feature ruleset structure** — were cut from the contract because
> **they serve features that do not exist yet.** They are kept whole because the day one does exist, this is
> the analysis it would otherwise have to redo. **The industry precedent for numeric squishes and the
> measured overflow points are the parts worth reading first.**

**Status:** design contract · **Date:** 2026-08-02 · **Supersedes as SSOT:** the substrate-scoped parts of
[`2026-08-02-actor-dataflow.md`](2026-08-02-actor-dataflow.md), retained as the derivation record.

> **Named `engine-substrate`, not `substrate`.** This repo already uses *"the substrate under
> `<domain>`"* as a house style for a domain's foundation document — the actor round and the **item** round
> both do. **This document is a different thing: the layer beneath EVERY domain.** An unscoped title would
> have been one name for two concepts.

**Companions:** [`2026-08-02-actor-hub.md`](../2026-08-02-actor-hub.md) ·
[`2026-08-02-handoffs-to-features.md`](2026-08-02-feature-notes.md)

> **Why this document exists.** Classifying the round's decisions by owner gave **17 hub · 101 substrate ·
> 23 feature · 38 process = 179 assignments over 178 rows** — one row is deliberately counted twice, because
> it genuinely splits (the fold is the hub's, its primitive is the substrate's). **The shape, not the
> arithmetic, is the point: the hub is under a tenth of it.** The round's spec was therefore **a substrate
> spec with an actor chapter**, and calling it an actor spec is what let feature-owned decisions land in it.
> *(The bare figure "178" against those four buckets was flagged as not summing — `V-SEAL/F-7`.)*

---

## 1. What the substrate is

Everything the hub and every plugin **stand on**, and which none of them may redefine: identity of rules,
what counts as canon, how a number is represented, how numbers combine, and who may write what.

**It is not a feature and has no vocabulary of its own.** It closes on **mechanism**; every name belongs to
an author or a plugin.

## 2. The two SSOTs, and only two

| | |
|---|---|
| **RULES** | the pinned ruleset digest plus the content manifest |
| **FACTS** | the event ledger |

> **Canon is what is written to the ledger.** State that was never written is fabricated and may be
> recomputed differently tomorrow. **A snapshot is a load accelerator and never a source.**

**Single writer per aggregate/stream** — and the reason is **replay**, not concurrency: two writers make the
order of a re-fold depend on scheduling. **Declared readers** — a sole writer is not enough, because reads
form hidden contracts that break silently.

**Every derived copy carries `(reality_id, seq)`.** One rule, applied everywhere a copy exists; not one rule
per copy site.

## 3. Identity, and why it forces integers

A ruleset is **content-addressed**: `RulesetDigest = blake3(canonical bytes)`.

> **A float inside the hashed bytes lets two machines produce two digests for one ruleset — two realities
> with identical content and different NAMES.** Server authority cannot repair that, because what breaks is
> the naming scheme, not the gameplay.

**This is not a precision argument.** A world simulator does not need a bank's exactness. **A digest does
not need precision; it needs reproducibility of bytes.** Two different properties, and only the second is at
stake.

> **The precedent this argument used to cite does NOT reach it (`V-SEAL/F-15`).** The repo did delete a
> byte-identical pin over a 1-ULP MSVC/glibc divergence — but that was a **CI regression golden over
> procedurally generated `f32` geometry** (`world-gen/src/flatworld.rs:1546-1550`), not a content-addressed
> ruleset, and **nothing was renamed**. Worse for the argument: **the remedy there was an epsilon band**
> (`:1422-1424`), which is precisely what a digest cannot use. **The conclusion stands on its own** — the
> shipped `RulesetDigest` hashes an all-integer `Ruleset` (`ruleset.rs:233`, `:64-110`) — **but it stands
> without that story.**

**Scope of the claim, stated so it is not over-read:**

| layer | float acceptable? |
|---|---|
| hashed ruleset bytes | ❌ **no — integer, mandatory** |
| runtime fold arithmetic | ✅ defensible in principle — this system is server-authoritative, with no lockstep, no rollback and no verification replay |

**We keep integers at runtime anyway, for a different reason: ONE ARITHMETIC.** Integer hashed bytes plus a
float runtime fold is two numeric models and a conversion boundary — the place where *"the declared cap is
1000 and the display shows 999.9999"* lives.

## 4. Ordinals — the only address

A declared quantity is addressed by an **ordinal**, assigned once and **never reused**. A name is the
author's; an ordinal is the mechanism's.

> **`QuantityOrdinal` is the only address in the value space.** Anything that today addresses a value by a
> closed engine-named slot is addressing it wrongly — the address is mechanism, the name is vocabulary, and
> a closed slot enum is an address wearing a name's clothes.

## 5. Value representation

### 5.1 One value per ordinal, and the DOMAIN says how to read it

> **⚠ RE-DERIVED after adversarial verification.** An earlier draft introduced a `Scaled { value, scale }`
> type as *"one shape for everything that spans realms"*, unifying pools, money and cultivation magnitude.
> **Two verification lenses found five of its six operations broken or underspecified**, and the re-derivation
> found why: **it conflated a REPRESENTATION question with a DOMAIN question.** Examined against what each
> case actually needs, the three do not want one type — and **only one of them belongs to this layer at all.**

```
one declared quantity  ->  one i32 per entity        //  the DOMAIN says how to read it
```

| case | stored as | why no combined type |
|---|---|---|
| **a pool's `current`** | **permille `i32`**, Linear | it is a fraction of its own capacity; it never spans decades |
| **a pool's capacity** | **a separate quantity ordinal**, itself Linear or Log `i32` | a capacity is a quantity, not a field of another one |
| **cultivation magnitude** | **milli-log `i32`**, Log domain | the only operation is *adding logs* (= multiplying magnitudes); **exact decade-crossing addition never arises** |
| **money** | needs exactness **and** unbounded range in one value | ⇒ **the only real case — and money is 身外之物, so it is the OWNERSHIP round's, not this layer's** |

**A permille is a UNIT of a Linear quantity, not a third domain member.** It is declared by the pool row
that owns the ordinal, so the fold needs no third arithmetic.

### 5.1.1 When ownership does need it, the answer is a solved problem — written here so it is not re-invented

**Decade-quantised exponent with a normalised mantissa** — the shape every arbitrary-precision decimal
library has used since the 1960s:

```
{ mantissa: i32, exp10: i16 }        //  value = mantissa × 10^exp10

canonical:  mantissa == 0  =>  exp10 == 0
            else            100_000_000 <= |mantissa| <= 999_999_999      // exactly nine digits
```

| operation | |
|---|---|
| **compare** | sign, then `exp10`, then mantissa — **exact and total**, because equal exponents mean the same decade |
| **add** | align to the **larger** exponent, shift the smaller mantissa right, accumulate in `i64`, renormalise. **The loss is bounded and explicit**: an exponent gap of 9 or more absorbs the smaller operand entirely, and that absorption **emits** (§11) |
| **multiply** | add exponents, multiply mantissas in `i64`, renormalise |
| ~~`band_delta`~~ | **NOT an operation of this type.** `band_delta` belongs to §10, over **Log-domain milli-log** values, where it is a subtraction — *nothing asks for the band gap between two purses*. It was carried here from the deleted unifying type, and §10 claims the name exclusively |

**Why the earlier version failed, recorded because the failure is instructive.** Its exponent was a
**milli**-log, so it was not quantised to decades — and without that invariant `compare` is simply false:
`{value: 1, scale: 500}` denotes 3.162 and `{value: 4, scale: 0}` denotes 4, yet scale-first ranks the first
higher. Under decade quantisation **that state is not representable at all**, which is the repair.

**And the general lesson:** the milli-log exponent was not a feature that needed guarding. **It was the
defect** — invented in place of a known representation, and every one of the operation failures followed
from it.

### 5.2 Why a LOG DOMAIN at all — power creep is a DOMAIN error, not a width error

A **count** is additive, bounded within a band, and must be exact. A **scale** is multiplicative, unbounded,
and only its ratios matter. Storing a scale as a count is what detonates, and **no integer width repairs it,
because the growth is exponential and every width is linear in bits.**

Measured: ×10 per realm overflows `i64` at realm 19; ×100 per realm overflows at realm 10; twenty realms at
×100 is 10⁴⁰. And `f64`'s **exact-integer** range is only 9.0 × 10¹⁵ — about **1000× less than `i64`** — so
past 2⁵³ two different magnitudes compare equal and a gain of 1 becomes a gain of 0, silently.

**In the log domain the same ladder is small:** 20 realms ×100 → **40 000 milli-log**; 100 realms ×1000 →
**300 000**. An `i32` milli-log spans about **two million orders of magnitude in four bytes**, multiplication
is **integer addition** (exact, deterministic, hashable), and the magnitude is **never materialised**.

**The industry's escape hatch is unavailable to us.** A shipped AAA MMO stored health in a signed 32-bit int,
hit it (a raid boss could overflow to negative health, and a later boss was designed to heal repeatedly so
its maximum pool could stay smaller), and has **squished its numbers four times**. **A squish changes
declared numbers, which changes canonical bytes, which renames every reality that ever existed.**

### 5.3 A pool never needs cross-band range

Every pool operation — spend, regen, threshold, floor check — is **within one actor**. **Damage is the only
cross-actor pool operation**, and a law may refuse it across bands. Therefore:

```
capacity : a LOG-domain quantity, milli-log           <- REQUIRED; see note (1)
current  : i32 PERMILLE of capacity, floor_pm..1000   <- never grows; floor_pm may be NEGATIVE (debt)
cost     : a LOG-domain quantity, milli-log

delta = cost_log - capacity_log
  delta < -absorb_threshold  ->  0 permille, ABSORBED + an event    (§11 - never "free", never silent)
  delta > 0                  ->  REFUSED                            (exceeds the whole CAPACITY)
  otherwise                  ->  permille = exp10_table(delta)      // delta in [-3000, 0], BOUNDED
```

> **⚠ THREE CONSTRAINTS THIS BLOCK CARRIES — each found by regression audit, each stated rather than
> assumed.**
>
> **(1) A pool's capacity must be LOG-domain.** §5.1's table says *"Linear **or** Log"*; **this arithmetic
> is Log-only** — for a Linear capacity there is no `capacity_log` to subtract. **A Linear-capacity pool is
> UNWRITTEN** (`U-12`), not supported-by-omission.
>
> **(2) `floor_pm` is a PERMILLE and is NOT the shipped `ResourceDecl.min`.** `min` is an **absolute** pool
> value, validated against `base` and a `Fixed(i32)` ceiling **in the same units** (`resource/table.rs:89`,
> `:96`, `:102`). Using it directly as a permille bound is unit-incoherent — the same declared `min = -50`
> would be a different fraction of every actor's capacity. **The debt case is real and survives; the
> conversion is UNWRITTEN** (`U-13`).
>
> **(3) This block consumes the LOG FOLD, which §9 records as UNWRITTEN** — and so does §8's fold-time
> ceiling clamp. **Neither is decided mechanism until `U-1` lands.**

**The only exponentiation is over a bounded range** — and `absorb_threshold` is **fixed at 3000, not authorable** (written as a parameter, the table index would be unbounded) — a 3001-entry table, exact, deterministic and hashable,
engine arithmetic in the same class as the `/1000` divisor. **Subtraction happens in the linear permille
domain, so the log domain's weak case never arises.**

> **No number in an actor's state grows LINEARLY, ever.** Capacity grows **in the log domain**, where a
> realm is `+1000` milli-log rather than a factor of ten; everything the runtime spends, compares or clamps
> is a bounded permille. *(An earlier draft said "no number grows, ever" — capacity is a number in the
> actor's state and it does grow. The claim needed its domain.)*

**The floor is not zero.** `ResourceDecl.min` is `i32` and its comment says why — *"signed because a pool
may model debt"* (`resource/mod.rs:125-126`) — so a permille range fixed at `0..1000` would silently delete a
case the shipped model supports on purpose. **But `min` is ABSOLUTE and `floor_pm` is a PERMILLE, so the
floor is DERIVED from `min`, never equal to it** — note (2) above.

### 5.4 Width

| | width |
|---|---|
| **declared** numbers (in the ruleset, few rows) | **`u64` to READ** — see below; an earlier draft's `i64` could not hold what already ships |
| **stored** per-entity values | `i32` |
| the **fold** accumulator | `i64` |

**A declared number exceeding `i32` is REFUSED at declaration**, with a message naming the mechanism the
author should have used instead.

> **⚠ CORRECTED — the earlier resolution was itself wrong.** It said *"`i64` to READ, `i32` to ADMIT"*, on
> the grounds that `i64` could hold the caps that ship. **It cannot: those fields are `u64`**
> (`progression/mod.rs:135, 141, 193, 197, 226` — and `:193`, not the `:194` previously cited), and
> `decode_cap` reads `r.u64()?` **unbounded**, so `(i64::MAX, u64::MAX]` is genuinely reachable on disk.
> An `i64` field reproduces the exact failure the split was written to avoid, one octave up.
>
> **DECIDED: `u64` to READ, `i32` to ADMIT.** The decoder is lossless over everything a prior schema could
> have written; the validator refuses a **new** declaration above `i32`. **Wide to read, narrow to admit —
> with a width that can actually read.** **That refusal is the power-creep guard** — it cannot be argued past, which
a style guideline never could.

## 6. The fold

```
value(q) = clamp( floor(q),
                  ( base(q) + Σ flat(q) ) × max(0, 1000 + Σ pct(q)) / 1000,
                  ceiling(q) )
```

| | |
|---|---|
| `q` | a `QuantityOrdinal` |
| `Σ flat` · `Σ pct` | contributions from modifier rows **and** derivation rows, **signed** |
| **percent is SUMMED, not chained** | summation is order-independent by construction, and it kills exponential stacking. A chained product is order-dependent and needs a deterministic sort as a patch |
| `max(0, 1000 + Σ pct)` | **the floor is load-bearing** — it was once absent, and two −60 % debuffs produced a factor of −0.2 and a negative stat |
| arithmetic | `i64` accumulator, **exactly one division at emit** |

**Ordering:** derivation rows form a DAG over ordinals, checked acyclic at declaration and evaluated in
**topological order by ordinal** — deterministic because ordinals are assigned and never reused, so the
traversal depends on neither declaration order nor map iteration.

> **⚠ CORRECTED (`V-SEAL/F-13`).** An earlier draft placed derivations *"after base values and before
> modifiers"*. **That inverts a shipped fix.** The existing move-range derivation — nominated as the first
> `DerivationRow` — runs **after the modifier loop and after the first clamp pass**: `resolve.rs:117` closes
> the loop, `:130` derives, `:131-133` re-clamps, and it reads the **finalised** Speed (`block.rs:76`). The
> ordering is a recorded correction, `XST-D6`: *"the derivation used to be the LAST statement… a Lex clamp
> of max = 2 on MoveRange produced 5… Deriving and THEN re-clamping restores DF7-A3."*
>
> **Run before modifiers, `MoveRange` would derive from an unmodified Speed and discard every Progression,
> Equipment and Status contribution to it** — the exact silent-drop class `XST-D6` and `XST-D7` were both
> filed against.

**Derivations run AFTER modifiers, and are followed by a re-clamp.**

## 7. Contributions

> **A contribution is DATA, never executable logic.** This is the whole decoupling: a plugin submits rows;
> the fold applies them; neither can run the other's code.

A conditional contribution's condition is a **declared threshold**, never a predicate grammar.

**Staleness is made impossible rather than detectable:** a modifier row is written and removed in the same
transaction as the fact that justifies it.

## 8. Ceilings — one model

```
Ceiling {
  rule:   SoftCap | HardCap | TierBased | Unbounded,     // classification DEFERRED - see §14; nothing computes with these yet
  source: Fixed(i32) | Derived(QuantityOrdinal),         // the signed arrow
                                                        // OMITTED from the canonical encoding when rule is
                                                        // TierBased or Unbounded - a zero filler would give
                                                        // one set of rules two digests
}
```

Two incompatible ceiling models exist in the current code — a soft/hard/tier-based one in progression and a
slot-or-constant one in resources — with **no shared vocabulary and no conversion**: a pool cannot be
soft-capped, and a progression kind cannot bind its cap to a derived value. **They collapse into the above
without losing a SHAPE** — every soft/hard/tier-based/unbounded case and every fixed/derived source
survives. **What is narrowed is RANGE**: caps currently declarable in `(i32::MAX, u64::MAX]` are
**REFUSED** at declaration under §5.4 — §11's verb, not a second word for it. **That is the power-creep guard doing its job, and it is a migration cost — stated
here rather than discovered later** (`V-SEAL/F-16`).

**Validation splits, because a derived ceiling is per-entity and therefore not knowable at declaration:**

| check | when |
|---|---|
| **acyclicity** of the derivation graph | declaration — it is a property of the rules, identical for every entity |
| **`base ≤ ceiling`**, **derived** ceilings only | **fold time, as a clamp** — the ceiling is per-entity |
| `Fixed` bounds, **including `base ≤ ceiling`** | **declaration — and this ALREADY SHIPS**: `resource/table.rs:89-94` (`base < min`), `:95-101` (`max < min`) and `:102-107` (`base > max`, *"an actor would spawn clamped"*). **It must not be retired.** *(An earlier draft cited `:229-233` and `:242-247`; the file is 238 lines and the first is `slot_from_u32` — the substance held, the evidence had not been opened.)* |

## 9. Domains

```
QuantityDomain { Linear, Log }        // closed: the engine's arithmetic differs per member
```

**Cross-domain contribution is REFUSED, not converted.** An automatic conversion is where an explosion
sneaks back in.

**There is no third member.** A permille is a **unit** of a `Linear` quantity, declared by the pool row that
owns the ordinal — not a domain.

> **⚠ UNWRITTEN, and stated rather than claimed: §6's fold is LINEAR-ONLY.** Applying it to a `Log` quantity
> would multiply a milli-log magnitude by a percent factor, which is meaningless — *"+10 %"* on a magnitude
> must **add milli-log**. **The Log branch does not exist yet**, and until it does, this closure has not
> earned §14's verdict. **It is UNWRITTEN work, not a decided mechanism**, and it is on the slice board.

## 10. Bands — the engine owns Δ and nothing else

```
band_delta(a, b) -> i32 milli-log
```

**That is the entire surface.** What a law does with Δ is the law's:

| law | its reading of Δ |
|---|---|
| combat | **refuse** when Δ is very negative |
| teaching | **require** Δ large and **positive** — opposite sign |
| trade | **no threshold at all** |
| social | **a modifier, not a refusal** |

**These are four readings of one number, not one threshold with four values.** Putting a threshold in the
substrate would make every future law inherit combat's semantics.

## 11. Nothing silent

| situation | verb | and it emits |
|---|---|---|
| a cost exceeding the whole **capacity** | **REFUSED** | an event |
| a cost exceeding **`current`** but within capacity | **`ZeroBehaviour`** — `Clamp` or `BlockCosts` — is **DECLARED** at `resource/mod.rs:107-114` and, per §14's own measurement, **read by no computation**: the declaration ships, **the behaviour does not** | **UNWRITTEN** (`U-11`) |
| a contribution crossing domains | **REFUSED** | an error at declaration |
| a declared number exceeding `i32` | **REFUSED** | an error at declaration |
| a payment too small to register — **including a cost below the resolution floor, which an earlier draft called *"free"*** | **ABSORBED**, with a zero charge | **an event** — a vanished payment is a fact somebody will ask about, and *free* was a second vocabulary for one situation |
| a transfer overflowing a ceiling | **CLAMPED** | **an event** — the excess is where a plugin's consequence attaches |
| a value bound by a cap | **CAPPED** | an event, already the practice: *"a bound ceiling is a fact in the log rather than a number nobody can explain"* |

**A refusal and an absorption are different on purpose.** Refusing a payment too small to matter would break
trade, which is the law that wants no threshold at all.

## 12. Ruleset structure

**A ruleset is a SET of per-feature parts**, each content-addressed, each with **its own `law_version`** —
not one struct with a field per feature.

The current shape inlines `combat`, `stats`, `quantities` and `resources` while holding `progression` as an
optional digest. **The digest form is already the fix, applied once and not generalised.** Its consequences
today: combat is not declinable, and a combat balance patch moves **every** reality's digest, including
realities with no combat.

## 13. Garbage collection

> **⚠ CORRECTED (`V-SEAL/F-8`) — the previous text was wrong in both directions.** It said *"an id carries a
> generation"* and *"only its detection half needs wiring"*.

**`EntityId` is a bare `u64`** (`sim-core/src/types.rs:17`) and **carries no generation** — the generation
lives *beside* it, in `entities: BTreeMap<EntityId, Gen>` (`sim-core/src/island/mod.rs:41`), with `depart`
returning `(Gen, D::Portable)` and `arrive` returning a `Gen`.

**And detection is ALREADY WIRED**, which was the half declared missing: `island/mod.rs:424-430`,
`Precondition::EntityAlive { id, generation }` refuses when `self.entities.get(id) != Some(generation)`, and
the island-level pass discards as `Superseded` at `:301`. *(An earlier draft cited `:92-100` — the doc
comment above `bump_island_gen`, i.e. prose that happens to live in a source file.)*

**`IslandOwns` at `:449-455` is the OPPOSITE case, and an earlier draft called it *"the same shape"*:** it is
`if !self.entities.contains_key(id)`, **with no generation at all** — so it detects removal, not staleness.
**It is evidence FOR the paragraph below, not a second instance of detection.**

⇒ **A bare `EntityId` IS a dangling handle.** Staleness is detectable only when a caller separately carries
the `Gen` and threads it through a `Precondition`. **That threading — not the detection — is the open work.**

## 14. The discriminator — how to tell mechanism from vocabulary

> **A closed set is MECHANISM if the engine's arithmetic DIFFERS PER MEMBER.**
> **It is A FEATURE'S VOCABULARY IN COSTUME if the engine treats members UNIFORMLY and only one feature
> knows their names.**

Without it, *"the engine closes on mechanism"* is unfalsifiable — any closure can be called mechanism after
the fact.

> **⚠ CORRECTED (`V-SEAL/F-6`).** An earlier draft claimed the test *"clears the operation, regeneration,
> cap-rule and curve enums"*. **Re-measured: only `ModifierOp` is genuinely cleared** (`resolve.rs:84` Flat
> versus `:95` Percent — the arithmetic really differs). **`RegenType`, `ZeroBehaviour`, `CapRule` and
> `CurveKind` have NO engine arithmetic at all** — every non-test use is parse, encode, decode or validate;
> `regen_rate`, `rate_milli` and `difficulty_milli` are declared, hashed, and **read by no computation**.
>
> **So the test cannot FAIL for those four, which makes citing them vacuous by this repo's own standard** —
> and the standard is one this document itself invokes. **They are unclassified, not cleared**, and they
> will be classifiable only once something computes with them.

It **convicts** a closed slot table and a per-feature field in a shared ruleset struct.

**Corollary, learned the expensive way:** *opening* a god-list does not decouple it. A flat global list of
names that every feature must edit is the same coupling whether the names are an enum or strings — and if
nothing reads the list, it is worse, because the compiler can no longer notice. **Coupling is fixed by
OWNERSHIP — whose part declares the row — not by openness.**

## 15. The clearing list

| | | gate |
|---|---|---|
| **`C-0`** | **the signed arrow** — a declared quantity may contribute **negatively** to another's ceiling or value | **PO decision; gates `C-1` and `C-2`** |
| `C-1` | `Ruleset` → per-feature parts, content-addressed, `law_version` per part | after `C-0` |
| `C-2` | one address — everything re-keys from a closed slot table to `QuantityOrdinal`; the slot table leaves the hub | after `C-0` |
| `C-3` | **split the substrate from the actor hub** | ✅ **this document** |
| `C-4` | the manifest's four declaration kinds | — |
| `C-5` | array-length coupling in the delta classes · the actor-kind question | — |
| `C-6` | `DerivationRow` — the derivation seam, with the existing move-range derivation as its first row | new build |
| `C-7` | one ceiling model (§8) | after `C-0` |
| `C-8` | `QuantityDomain` as a declared property (§9) | — |
| ~~`C-9`~~ | ~~the ownership feature has no folder~~ **RETRACTED** — the claim measured the PLANNING FOLDERS (35, correctly, with no ownership folder) and concluded about the REPO; `docs/specs/2026-08-02-item-data-structure.md` exists. **Reconciliation deferred by the PO.** (`V-SEAL/F-9` caught this contract still listing it as open while the handoff retracted it.) | — |

**`C-0` is the gate.** Everything structural queues behind one decision — and the argument for it changed
class: it began as expressiveness (*"a ceiling cannot derive from a declared quantity"*), which is
deferrable, and became **structure** (*split the ruleset into parts and the resource part imports the combat
part, in the hashed bytes, through a decoder*), which is not.

**And the cost is asymmetric in time:** the compiler performs `C-2` with you today across a bounded set of
call sites in four crates. **After any reality is pinned it becomes a data migration plus every author's
manifest**, and the compiler cannot help at all.
