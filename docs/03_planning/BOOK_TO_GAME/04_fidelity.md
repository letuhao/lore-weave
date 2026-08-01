# 04 — Fidelity: recorded distance, not permission

> *A game is created from an original story, but how closely it can follow that story is a question
> that has to be answered — and the human should be the one to answer it. How can they?*

**This document was rewritten after its first draft got the direction backwards.** The first version
treated fidelity as a *gate*: high fidelity meant the game may not have a mechanism the source denies.
The PO corrected it, and the correction is the load-bearing fact of the whole tier:

> *What we intend to build is the AUTHORING piece — not the logic piece that says "the book doesn't
> have this, so we can't do that."*

---

## 1. The correcting case: a book with no system at all

Most books have no game system. Cultivation fiction is the **easy** case — it arrives with realms,
breakthroughs, treasures and a ladder already in it, which is why every worked example in this project
so far has been 封神演義, and why the design quietly assumed a system was there to be found.

Take a book that has none: a family saga, a detective novel, a war story. Making an RPG from it is
impossible **unless someone invents the game concept**. There is nothing to extract. The source
supplies a world, a cast, a tone and a set of events — and every mechanical statement has to be
authored.

> **`BTG-A7`** *(replaces the first draft's version, which was wrong).* **Invention is the normal case,
> not the exception.** The tier's value is highest exactly where the source is thinnest, and a design
> that treats invention as a fallback for when extraction fails is optimised for its rarest input. A
> game concept is **authored**; the source **constrains and inspires** it; it does not contain it.

The first draft's claim — *"high fidelity plus a foreclosure means the game may not have that mechanism
at all"* — is the logic piece talking. It would make the tool refuse to work on most of its inputs.

## 2. So what is a foreclosure for?

The distinction is still real and still worth detecting. Its **consequence** is what changes.

The corpus stands in one of three relations to any question:

| | canon | what the author learns |
|---|---|---|
| **STATES** it | has an answer | *take it, or depart from it knowingly* |
| **SILENT** on it | has no answer | *invent freely; canon is untouched* |
| **FORECLOSES** it | says *there is no answer* | *invent if the game needs it — and know you are contradicting a specific sentence, which is here* |

封神演義 does not merely fail to rank its treasures. It says so: **寶各有用，未嘗較其次第** (*each
treasure has its use; their order was never compared*), echoed in the reference wiki as
**書中未嘗分品第**.

A game almost certainly still wants item grades. The author should add them — and should **know** they
are departing at that exact sentence, so the departure is a decision rather than an accident.

> **`BTG-A8`** *(replaces the first draft's version).* **A foreclosure is a flag for the author, never
> a prohibition.** Its value is that it converts an invisible contradiction into a visible one. Without
> detection, a nine-grade ladder gets bolted onto a world that explicitly refused ranking and nobody
> ever knows. With detection, the same ladder can be added deliberately, with the contradiction on the
> record.
>
> It remains the sharpest tooth in the existing fixture (`fixture_teeth.json`, `I2`) — but what it
> tests is *did you notice*, not *did you obey*.

## 3. What a fidelity position actually is

Not a permission system. A **statement of how far this adaptation intends to sit from its source, per
axis, with the distance recorded fact by fact.**

Per-axis, because the same game is routinely faithful in one respect and free in another. A retelling
where you play Nezha needs the cast closed and cares little about geography; a sandbox in the same
setting needs generative rosters and would be ruined by a fixed timeline.

**The axes are the pool's slots, grouped**, so the list grows with the contract instead of drifting
beside it:

| axis | slots it groups (today) |
|---|---|
| **cast** | actor / faction slots |
| **artifacts** | `item_archetype`, `instrument_tag`, `equip_slot` |
| **power** | `progression_kind`, `progression_stage` |
| **geography** | place slots (unregistered) |
| **register** | cross-cutting |

An axis with no slots is one the game does not condition on, and asking a human to rule on it would be
asking for a decision with no consequence.

A position then sets **what the author is expected to do**, and what the record must show:

| position | expectation of the author | what the record must carry |
|---|---|---|
| **retelling** | take what canon states; invent only to fill gaps | every departure, individually |
| **anchored** | extend canon by rule; keep its shape | which facts are `DERIVED`, and from what |
| **inspired** | invent freely; keep the world recognisable | which facts are `PROPOSED`, and any contradiction |
| **setting-only** | the source is a palette | nothing beyond attribution |

> **`BTG-A9`.** The charter is checkable, and what it checks is **disclosure, not obedience**. *"This
> game is a retelling on cast"* becomes: *every cast fact that is not `CITED` must name what it departs
> from.* A fact may always be invented; an invented fact that **hides its status** is the defect. That
> is a criterion of exactly the shape the contract generator's per-operation criteria already take
> (`BLD-A1`), and it can fail — which the first draft's version, a rule forbidding content, could only
> do by making the tool refuse ordinary work.

## 4. How the human decides

A human cannot answer *"how canon-bound should the power system be?"* in the abstract. They can answer
it when shown **what each position asks them to write**, on this corpus.

Four computed things per axis — and note the change of verb from the first draft: these describe *work
to do*, not *permission granted*.

**① Coverage — what canon supplies.** Of the slots on this axis, how many can be filled from `CITED`
evidence? The provenance census (`app/gamegen/census.py`) projected per axis; it already computes
*chosen vs defaulted* and *book-grounded vs proposed*.

**② Foreclosures — where canon says no.** Named, with the sentence and its citation. The
highest-value thing the tier can show, and nothing looks for it today.

**③ The authoring load of each position.**

> *`power`, **retelling**: 2 of 5 slots have canon answers. You will be inventing 3, and one of them —
> item ranking — contradicts ch65, shown here. **anchored**: those 2, plus 2 derivable from the
> breakthrough scenes in ch12/ch47; 1 still invented. **inspired**: invent all 5 and keep the register.*

**④ What a game of this kind usually does.** The comparison a human actually reasons with. It arrives
as `PROJECTED` — a pattern, never a fact (`BTG-A5`) — and is a suggestion to accept or refuse. This is
the material that makes a **systemless source workable at all**, and it is why
§[`02`](02_world_as_corpus.md) argues a reference game belongs in the world.

> **`BTG-A10`.** The decision is not elicited by a question; it is elicited by a **consequence**
> computed before the question is asked. The same finding the game tier reached from the other
> direction (`ASK-A2`: never ask for a number — ask for the structure that determines it, compute the
> number, show the derivation).

## 5. Revision must cost something visible

A charter will change once the human sees what a retelling actually produces. That must not silently
leave a concept authored under the old position.

The mechanism exists one tier down and is the same code: the concept is content-addressed, everything
derived pins the digest, and changing the charter changes the digest — so downstream artifacts declare
themselves stale by comparison rather than by anyone remembering.

## 6. Open questions this document does not settle

1. **Who owns the axis list?** Derived from the pool's slots, which keeps it grounded — but two
   candidates (chronology, outcome) may be constraints on *play* rather than on the contract, in which
   case they belong elsewhere and this document should say so rather than carry them.
2. **Is foreclosure detectable at acceptable cost?** The evidence for *"the book denies ranking"* is one
   sentence in one chapter, and similarity search returns the thousand places ranking is merely not
   discussed. §[`06`](06_poc_plan.md) POC-A measures it. Note the stakes are now **lower** than the
   first draft implied: a missed foreclosure costs an unrecorded departure, not a wrongly-forbidden
   mechanism.
3. **Does a fidelity position belong to the world, the game, or the run?** Two games from one novel is
   the obvious case, which implies it is not world-level. Left open.
