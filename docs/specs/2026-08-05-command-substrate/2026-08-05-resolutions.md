# Resolutions — clearing the open questions

> # 🔴 QUARANTINED — DO NOT BUILD FROM THIS
>
> **This round's Phase 0 is FALSE.** Its §0 states *"In code: nothing… In design: two
> things, and both are refused."* A cold-start review found **4 017 lines of directly
> relevant prior design**, three days older, in this same `docs/specs/` tree, which
> this round never opened:
>
> | | lines | what it already contains |
> |---|---|---|
> | `../2026-08-02-command-interaction-structure.md` | 415 | **`from: Offered \| Any // THR-A4`** — the offer concept this round presents as its central invention, already a declared field · The Sims smart objects, already sourced to `D-2` · deterministic lockstep, already concluding *"a command is data by necessity, not by taste"* |
> | `../2026-08-02-command-interaction-dataflow.md` | 877 | the specification proper |
> | `../../plans/2026-08-02-command-interaction-RUN-STATE.md` | 796 | decisions **`CMD-1`..`CMD-9`** — which this round's `CMD-D1`..`CMD-D7` collide with, one letter apart, same subject |
> | `../2026-08-02-item-data-structure.md` | 611 | *"the substrate under **ownership, inventory, equipment and transfer**"* — the holder graph this round declares a 🔴 BLOCKER with *"today there is no outside"* |
> | `../2026-08-02-item-dataflow.md` | 1 318 | its specification |
>
> **How it happened, precisely:** every absence claim in this round was a `grep` over
> `crates/` and `services/`, reported as a repo-scoped conclusion. **`docs/specs/` was
> never searched.** That is the exact defect Phase 0 exists to prevent, performed by a
> section that claims to BE Phase 0 — and it is the same shape as the actor-hub round
> that designed feature #1 without auditing what already modelled an actor.
>
> **RECONCILED 2026-08-05** — read [`2026-08-05-reconciliation.md`](2026-08-05-reconciliation.md)
> **FIRST.** It adjudicates every claim here against the prior rounds: most of this
> folder is duplicate, the 🔴 BLOCKER is WITHDRAWN, `CMD-D1`'s seal is VOID, and five
> items survive. The prior round's own run state records that the PO **declined to seal**
> `CMD-1`..`CMD-6` and **directed a round of prior art** — which is, accidentally, what
> this round performed, blind to the round that asked for it.
>
> **Nothing here is authoritative on its own.**
> Individual findings may survive; the framing ("feature #2", "nothing implements
> this", the blocker, the decision ids) does not.



**Status:** DESIGN. Six questions closed, one BLOCKER found.
**Date:** 2026-08-05, after the contract and the extensibility round.

The contract and `2026-08-05-extensibility.md` left seven things open. Six close
here — most of them because a decision already sealed forces the answer, which is
the good kind of resolution. The seventh turned out not to be a question at all: it
is a **blocker under one of the contract's own precondition kinds.**

---

## `CMD-D2` · Collision is a BUILD ERROR. Amendment is ADDITIVE. — closes §8.4

The open question was *"when feature B touches feature A's command, is that an
OVERRIDE or a CONTRIBUTION?"*

**Neither, because the question conflated two different operations.**

| operation | answer |
|---|---|
| two bundles declare the **same command id** — a collision | the **ruleset build FAILS** |
| B wants to **change** A's command — an amendment | an explicit amendment record that only **ADDS** preconditions and effects |
| B wants A's command **gone** | remove A's bundle from the ruleset — an explicit act, recorded in the ruleset |

### Why we get an answer nobody else gets

Last-loaded-wins exists because a system that composes **at launch must produce
something**. It cannot fail: the player is waiting. So it picks a winner, silently,
and the ecosystem pays for it with hand-written compatibility patches forever.

**We pre-compose** (extensibility §8.3, refused load-time composition). A ruleset is
built once into a pinned content address. **A build can fail.** That single
difference dissolves the whole problem: a collision does not need a winner, it needs
an error message. There is no patch economy because there is nothing to patch around.

And origin-namespaced ids (Idea 3) make true collisions rare in the first place — a
command id carries its declaring bundle, so two bundles cannot accidentally choose
the same one. A collision then means someone *deliberately* claimed another
bundle's id, which is exactly the case that should stop a build.

### Why amendment is additive, not replacement

The actor hub already settled the analogous question for quantities: contributions
fold, they do not overwrite, and no plugin can silently erase another's effect. The
same reasoning applies to a verb's *constraints* even though it does not apply to a
verb's *identity*:

- a verb is not a sum, so its **definition** — name, parameters, resolution — is
  owned by exactly one bundle and cannot be redefined by another
- its **preconditions and effects** are lists, and lists add

So a feature can say *"this command additionally requires X"* or *"this command
additionally causes Y"* without owning the command. It can never say *"this command
is now something else"*. GAS works this way already: a `GameplayEffect` adds
*Activation Blocked* tags to an ability it never authored.

**Consequence to accept:** amendments cannot express *"and drop A's precondition"*.
That is deliberate. A removal is exactly the silent-erasure this rule exists to
prevent, and a bundle that genuinely needs A's command without A's constraint should
declare its own command, not quietly weaken someone else's.

---

## `CMD-D3` · The registry runs in commit-service — forced, not chosen

Offers are computed from **live island state at tick T** (contract §3, §6). The
island lives in commit-service, which hosts `sim-core` natively (`CS-A5`) and owns
admission. Nothing else is in a position to answer the question.

The other two candidates are excluded by rules already sealed, not by preference:

- **game-server** holds no authority — *"the room is a lens"*, `CWC-A1`. Computing
  offers there would make the transport tier an authority on what may be done.
- **world-service** owns projections and rebuild — derived read models, not live
  island state. Offers computed from a projection would be stale by construction.

**Delivery is separate from computation.** commit-service computes and publishes;
game-server projects offers to clients exactly as it already projects committed
events. That keeps the lens a lens.

---

## `CMD-D4` · `offer_id` is a keyed MAC, not a lookup — closes the bearer-token risk

The contract said an offer must be **bound**, not merely unguessable, and flagged it
as the design's most fragile claim. The concrete mechanism:

```
offer_id = MAC_k( ruleset_digest ‖ reality ‖ tick ‖ subject ‖ provider
                  ‖ command_id ‖ digest(parameter domains) )
```

`offer-entitlement` (contract §5) then **recomputes and compares**. That is what
"re-derived, not looked up" means in practice, and it buys three things:

1. **Stateless.** There is no table of live offers to leak, grow unboundedly, or
   evict wrongly. A design that stored offers would have made the store the new
   attack surface.
2. **Expiry is free.** `tick` is in the input, so a leaked id is worthless on the
   next tick without any cleanup job.
3. **Tampering is detected, not just rejected.** Changing the subject, the provider
   or a parameter domain changes the MAC input, so a mismatch names *which* field
   was altered rather than only that something was.

**What this does NOT solve, stated:** a leak **within the same tick** is still
authority for that tick. Shortening a tick is not a security control. If that window
ever matters, the answer is binding the session into the MAC input — which is
already the intent of *"minted for a (session, subject) pair"* and should be
written into the input list when sessions exist.

---

## `CMD-D5` · No order queue in the substrate — queuing is a DRIVER concern

An order queue (*"move here, then attack that"*) belongs to whoever is deciding, not
to the thing that validates.

Offers are per-tick and expire (`CMD-D4` puts `tick` in the id). A queued command
**must** be re-validated against fresh offers when its turn comes, because the world
moved — that is the same reasoning as contract §6. So a queue held in the substrate
would have to re-derive everything anyway, while adding per-subject state the
substrate currently does not carry.

A driver that wants a queue holds a plan and submits one item per tick against that
tick's offers. It gets queuing; the substrate stays stateless with respect to
intent, and an abandoned plan costs nothing.

**Replay is unaffected** — the ledger records invocations, and a plan that was never
invoked was never a fact.

---

## `CMD-D6` · Parameter domains stay `Enumerated`-only — with the admission test

Kept closed, and now with a criterion rather than a mood.

The first genuinely likely need is a quantity — *"transfer how many"* — which wants
`Range`. **A new domain kind is admitted only when both hold:**

1. a real declared command needs it (not a hypothetical), and
2. **the engine clamps it.** An unclamped range is a free parameter wearing a type,
   and a free parameter is the hole `THR-A4` exists to close.

Test 2 is the one that matters. `Enumerated` is safe because the engine authored
every member. A `Range` is safe only if the engine also authored the bounds *and*
enforces them — a driver that can send `999999` into an unclamped range has the same
authority a raw `item_id` would have given it.

---

## `CMD-D7` · Multi-subject commands stay out — and the reason is CONSENT

A two-party act (a ritual, a trade, a carry) is not one subject spending a turn. It
needs the **second subject's driver to agree**, and agreement is a negotiation with
its own states: offered, accepted, withdrawn, timed out.

That is a protocol, not a command. Folding it into a command would put a negotiation
state machine inside the thing whose entire job is to be stateless between ticks
(`CMD-D5`).

**Out of scope until a consent feature exists.** Recorded so that the first
two-party act does not get modelled as a command by default.

---

## 🔴 BLOCKER · `LinkExists` stands on nothing — nobody owns the holder graph

Not an open question. A **defect in the contract's own precondition alphabet**,
found while closing the others.

The contract declares five precondition relation kinds (§7): `ResourceAtLeast`,
`LinkExists`, `TagPresent`, `Adjacent`, `ValueAtLeast`. `LinkExists` means *"the
subject holds the provider"* / *"the provider is in that container"* — and it is the
precondition the contract's own worked example depends on. *"Consume the teleport
scroll you are holding"* is `LinkExists` and nothing else.

**Measured 2026-08-05: no holder graph exists.** No containment, no inventory, no
entity-to-entity holding relation anywhere in `crates/` or `services/` or the
per-reality schema. The only `holder` in the codebase is the **channel writer
lease** in `dp-kernel/src/channel.rs` — who holds the right to write to a channel,
an unrelated concept that happens to share a word.

So:

- **one of five precondition kinds is unimplementable today**
- **the motivating scenario of the whole design cannot be expressed**
- *"who owns inventory"* was listed as a deferred side question. It is not a side
  question. It is a **prerequisite** — the command substrate cannot express its own
  worked example until something owns the holder graph.

It is also the one thing the island cannot own: an item leaving an actor's hands is
`External` by `sim-core`'s own definition — an effect that leaves the island and
needs commit-service authorisation. So the holder graph lives outside the island,
and today there is no outside.

**This is now the top item, ahead of any implementation.** A substrate whose
precondition alphabet contains a letter with no substrate is not ready to be built
against.

---

## Still open, deliberately

**The wire shape of an offer.** Refused on purpose: designing a wire format with
zero declared commands is the *declared-general-with-one-instance* trap this repo
has now hit four times in one day. It is decided by the first real command, not
before it.
