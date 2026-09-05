# Supplementary contract — the laws feature #1 states, and nothing enforces

**Status:** supplementary contract · **Date:** 2026-08-04
**Companions:** [`2026-08-02-actor-hub.md`](2026-08-02-actor-hub.md) ·
[`2026-08-02-engine-substrate.md`](2026-08-02-engine-substrate.md) ·
[`2026-08-02-seams-and-triggers.md`](2026-08-02-seams-and-triggers.md)
**Origin:** the completeness ledger — [RUN-STATE §11](../../plans/2026-08-02-actor-substrate-RUN-STATE.md), `D-511`..`D-513`

---

## 1. What this is, and what it is not

The completeness audit found feature #1 **complete against its sealed boundary**:
every obligation proven with a named witness, every refusal a registered seam,
no excess. What it found instead was three defects of the **record**, and one
class underneath them:

> **A property this feature states about itself, which holds because nobody has
> broken it yet.**

That class already has a name here. Substrate §3 wrote it about floats —
*"structurally true today, and unguarded"* — and answered it with `U-9`'s gate.
This document specifies the same answer for the rest, **and nothing else.**

**It does not design feature #2.** Every seam in `seams-and-triggers.md` stays a
seam. What is specified below is the **CHECK**, never the feature's data model —
and where a check cannot be built without deciding a feature's question, it is
not specified either, it is left at its trigger.

## 2. The classification, and the line between A and B

| | |
|---|---|
| **A** | buildable today, **and able to fail today** |
| **B** | specified today, built at a named trigger — because a mechanism built now would be **vacuous** |
| **C** | deliberate refusals, restated so they stop being re-litigated |

**The line is NV-1: can the check fail today?** `S-12` already argues its own
side of it — *"an ordinal space with one member cannot be renumbered, so a check
built today has no failing input."* Building it anyway would produce exactly the
artefact this project has now shipped twenty-seven times: **a check that reports
coverage and silences review.**

---

## 3. Bucket A — build now

### A-1 · The vocabulary leak detector (`D-513`)

**The law**, hub §4: *"The hub never inspects `fold_layer` semantically. It
orders by it and nothing else. **If the hub ever needs to know what a layer
MEANS, a plugin's vocabulary has leaked in.**"*

The second sentence is the rule stating its own failure condition, which is what
makes it gateable rather than aspirational. **Today nothing checks it.**

**Measured before specifying** — the shipped hub reports **zero** findings under
both a narrow and a broadened form of the rule, so the mechanism does not
cry wolf on correct code. The only sightings of a named ordinal in
`actor-hub/src` are one doc comment and one test assertion.

**Scope: a DIRECTORY, recursive** — `crates/actor-hub/src` — never an enumerated
file list. An enumerated list is *default-uncovered*: it says nothing about the
file created tomorrow, which is NV-3 and the reason the float gate carries the
same sentence.

**The shapes it reports**, in production code only, comments stripped:

1. an ordinal or layer **constructed from an integer literal** —
   `FoldLayer::new(3)`, `QuantityOrdinal::new(0)`, `PluginOrdinal::new(1)`;
2. one **compared against an integer literal**, either side, with or without
   `.get()`;
3. a `match` whose **scrutinee is** a layer or ordinal.

**What it must stay silent on**, because these are mechanism and not vocabulary:
a comparison against a **named width constant** (`< MAX_PLUGINS`,
`< MAX_DECLARED_QUANTITIES`) — the rule requires a **literal**, which is what
separates *"is this ordinal in range"* from *"is this ordinal the one I mean"*;
everything under `#[cfg(test)]`, where naming an ordinal is how a test is
written at all; and every comment, where `mana` and `hp` are how the rule is
explained.

**The escape hatch must be able to reach its reason.** The pragma is
`hub-vocabulary-gate: ok — <reason>`, honoured anywhere in the **contiguous
comment block** above the finding, however long that block is. A fixed
one-line lookback window is not acceptable: it shipped in three sibling gates
and is NV-6's own worked example — a reason that does not fit is a reason that
gets deleted, and the exemption survives it.

**Non-vacuity.** The bite is planting `if row.fold_layer == FoldLayer::new(3)`
in `fold.rs`, watching it red, removing it, watching it green — pasted both
ways. The self-test carries one case per shape **and one per silence**, because
a gate with no cry-wolf case is half-tested.

**Wiring:** pre-commit + `gate-self-tests`, and a mutation row per rule in
`gate-bite-harness`, or `gate-wiring-gate` reports it as an orphan.

### A-2 · A source citation must name what DEFINES the thing (`D-512`)

**The defect:** `actor-hub/src/actor.rs` cited `dp-kernel/src/entity_status.rs`
as where `GoneState` ships. Hub §3.3 had already recorded that the type moved to
`crates/entity-existence` — and fixed the contract's copy of the citation while
the source copy went unread.

**Three candidate checks, and only one of them works.** Measured against the
exact defect:

| check | verdict on `D-512` |
|---|---|
| does the cited **file resolve**? | **misses** — the file exists |
| does the file **mention** the symbol? | **misses** — 38 occurrences |
| does the file **DEFINE** the symbol? | **catches** — the only line is `pub use entity_existence::{GoneState, …}` at `:40` |

A gate built on either of the first two would have been written for `D-512`,
shipped, and been unable to catch it. **That is worth more than the gate**: it
is the same measurement discipline that killed the two-phase span half and the
file-read cache earlier the same day.

**So the mechanism has two halves, and the first is a CONVENTION.**

1. A file citation in a source doc comment names its subject:
   `entity-existence/src/lib.rs#GoneState`. The hub has **six** such citations
   across five targets; converting them is the whole cost.
2. The gate resolves the path — **crate-relative and repo-relative both**, since
   `entity-existence/src/lib.rs` is really `crates/entity-existence/src/lib.rs`
   and a resolver that tries only one of the two cries wolf on all five — then
   requires a **definition** of the named symbol: `pub enum` / `pub struct` /
   `pub fn` / `pub trait` / `pub type` / `pub const`. **A `pub use` is not a
   definition**, and that is the entire discriminating power.

**Non-vacuity depends on step 1 happening first.** With zero symbol-bearing
citations the gate has no subject and is vacuous by construction; with the six
converted it has six, and the bite is repointing one at a re-exporting file.

**Honest limit, inherited:** this proves a citation names a file that **defines**
the symbol. It never proves the sentence around it is true. `citation-gate`
states the same limit about documents and it is not weaker here.

---

## 4. Bucket B — specified now, built at a named trigger

Each of these is a real law with no mechanism. **None can be given one today
without the mechanism being vacuous**, so what is fixed here is the *shape* of
the future check, so that the feature that trips the trigger does not
re-derive it.

| # | Seam | The law with no mechanism | The mechanism it must get | Why not today | Trigger |
|---|---|---|---|---|---|
| **B-1** | `S-12` | hub §3.4 — a plugin ordinal is *"assigned once and never reused"*; `never_reuse.rs` mechanises the **quantity** space and nothing mechanises the **plugin** space | the same walk over prior epochs' plugin tables, returning the `OrdinalReuse` shape already defined for quantities — **one mechanism, two spaces**, not a second design | **an ordinal space with one member cannot be renumbered**, so the check has no failing input | `M-8`, when plugin #2 is declared |
| **B-2** | `S-11` | `QTY-A14` — *"any datum that leaves the island carrying an ordinal MUST carry the digest that gives it meaning"*; `QuantityOrdinal` derives `PartialEq`/`Ord`/`Hash` over a bare `u16`, so reality A's `3` **equals** reality B's `3` | the carrier is a pair — ordinal **plus** the ruleset digest — and the check is that no ordinal crosses a reality boundary unpaired | there is **no crossing** yet; the type is correct inside one reality, which is the only place it is used | whichever feature first moves a quantity across a reality boundary — the crossing `S-9` names for identity |
| **B-3** | `S-16` | substrate §2 — *"every derived copy carries `(reality_id, seq)`"*; `FoldReport` carries neither, because a **pure crate has access to neither** | the stamp is applied by whoever persists or transmits the report, and the check belongs at that write — **not** inside the hub, which would have to invent a reality to stamp with | no host persists a fold result yet | whichever host first persists or transmits one — the same host that owns the ledger write |
| **B-4** | `S-17` | substrate §8 — *"a bare `EntityId` is a dangling handle"*; staleness is detectable only when a caller threads the `Gen` through a `Precondition`, and `Actor` holds no `Gen` | the threading is `U-8`'s, at the substrate; **the hub deliberately did not invent a second generation**, and must not | there is no caller doing the threading to check | `M-15` / `U-8` |
| **B-5** | `S-14` / `U-2` | hub §4 — the clamp channel is **not** a fold layer, and a `u8` layer ordinal cannot express *"and also a clamp channel"*. A declared ceiling already exists (`S-18`); what is missing is the channel that submits one **per actor** | a second ordered channel with intersect semantics and floor-wins on contradiction — the shipped shape, already cased in `capping.rs` for the representation's clamp | specifying the submission channel decides **what a bounded quantity is**, which is the resource feature's question | the first feature that declares a bounded quantity |

---

## 5. Bucket C — refusals, restated so they stop coming back

These are **not** gaps and must not be re-opened as ones. Each was decided, and
each is re-stated here because a refusal with no written reason gets re-litigated
by the next reader.

| Seam | The refusal |
|---|---|
| `S-13` | Derivations resolve in **one pass** against modifier-only values. A derivation **of** a derivation is not expressible, and adding one needs a dependency order the hub does not have. This is the shipped shape, not a shortcut. |
| `S-15` | After attach initialises a quantity, **nothing in the hub writes it again** — no damage, no regeneration, no expenditure, no progression verb. Whatever changes a stored quantity also decides what event records the change, and that is the declaring feature's. **This is the boundary working.** |
| `S-18` | The hub **does not consult** `ResourceDecl`'s ceiling. A reality may declare `ceiling: Fixed(1000)` and the fold will resolve 10 500 with no `Capped` record. Reconciling `QuantityDecl.initial` against `ResourceDecl.base` decides **what a pool is** — answering that from feature #1's chair is the encroachment this round exists to stop. |

---

## 6. Acceptance

**A-1 and A-2 are done when**, for each: the rule is wired pre-commit and into
`gate-self-tests`; a mutation row exists per rule in `gate-bite-harness` and
reds; the bite-test output is pasted both ways in the RUN-STATE; and the
cry-wolf surface is **measured on the shipped tree**, not asserted.

**B-1..B-5 are done when** their triggers fire — and the check that they were
not quietly forgotten is that each id already appears in
`seams-and-triggers.md`, whose rows the deferral machinery reads. **This
document adds no new tracking; it adds the shape the trigger will need.**

> **Feature #1's job is to make adding feature #2 cheap — not to pre-empt it.**
> A mechanism specified before its subject exists is pre-emption wearing a
> gate's costume, which is why five of these ten are deliberately unbuilt.
