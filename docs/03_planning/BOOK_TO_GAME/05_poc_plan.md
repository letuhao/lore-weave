# 05 — The POC plan

**Nothing in this folder is built.** This is the ladder of the smallest things that could show the
design is wrong, ordered so the cheapest kill comes first.

The discipline is the one the game tier learned the hard way: *each planner has to be built and
measured; there is no formula, and the architecture only makes building faster.* Every step below has
its expectation written **before** the run, and a stated result that means **stop**.

**Constraint on every step: no new service, no migration, no change to `composition-service` until
POC-B has passed.** Everything runs against artifacts that already exist.

---

## POC-A — can a foreclosure be found at all?

**Kills:** `BTG-A7`, and with it the fidelity charter's ability to mean anything. If *"the book says
there is no ranking"* cannot be found reliably, every fidelity position collapses to *silent ⇒ invent*
and §[`03`](03_fidelity.md) is decoration.

**Why first:** cheapest, and it already has an **answer key written before the question was asked** —
`tests/fixtures/fengshen/fixture_teeth.json`, tooth `I2`, which records both the foreclosure
(寶各有用，未嘗較其次第 in ch65; 書中未嘗分品第 in the wiki) and nine terms that are `absent_everywhere`.

**Run:** over the fixture corpus, ask a deliberate *"does this corpus DENY that X exists?"* pass for a
handful of questions — some genuinely foreclosed (item ranking), some merely silent (how many
cultivation realms), some stated (who wields 打神鞭). Anchors and `locate()` supply the citation, so a
foreclosure that cannot be pointed at is not a foreclosure.

**Measured:** recall on the known foreclosure · **false-positive rate on the merely-silent questions**
(the dangerous direction — a false foreclosure forbids a mechanism the world would happily allow) ·
whether the cited sentence is the right one.

**Stop if:** the silent questions come back "foreclosed". A detector that cannot tell *absent* from
*denied* is worse than none, because it produces confident refusals.

**Then repeat on the 100-chapter corpus**, where the foreclosure is one sentence among 2329 chunks.
The fixture proves the idea; the real corpus proves the retrieval.

---

## POC-B — does an authored concept beat both baselines?

**Kills:** the tier itself. This is the central claim — that a document authored *for the game* is a
better source than either the novel or the wiki.

**Why it can be decisive:** two baselines already exist and both are measured, so the comparison has
nowhere to hide.

| baseline | status |
|---|---|
| hand-written 11-line block | today's best result — but it is *cooked by a human who was not counted as part of the pipeline* |
| raw corpus + model-written queries | measured 2026-08-01: noise floor for derived queries, ~0.47 top-1 for asked ones |

**Run:** hand-author a **deliberately small** game concept — one axis, ~10 entities (Nezha's treasures
plus the power axis is the obvious slice, because the fixture already has teeth there) — then point the
**existing** contract generator at it as its retrieval source and run the four-slot cycle unchanged.

**Measured:** the criteria the pool loop already computes — pass rate, heal rounds needed, compression
(`m < n`), refusal quality — **and `evidence_n`, which is the tell**: if the concept has a table of
contents, `n` is countable, and one of the three stuck problems is closed by construction.

**Stop if:** the authored concept does not beat the raw corpus. That would mean the problem is not the
source material, and the whole tier is aimed at the wrong thing.

**Watch for the confound:** the concept will be authored by the same hand that wrote the 11-line block.
Beating the raw corpus is meaningful; beating the hand-written block is **not**, and must not be
claimed. What the block proves is that cooked material works — POC-B only has to show that a *document*
is at least as good as a *value*, while being editable, countable and re-readable.

---

## POC-C — is the concept→pool seam mechanical or judgemental?

**Kills:** either the contract generator's planner kinds, or the concept's claim to hold answers —
one of the two is redundant if this comes back at an extreme.

**Run:** with POC-B's concept, attempt to derive pool members **mechanically** — no model. Count the
members that come out clean, and inspect every one that does not.

**Measured:** the proportion needing a judgement call, and *what kind* of judgement.

**Reading the result:**

| outcome | what it means |
|---|---|
| ~0% need judgement | the planners are redundant; the concept should emit the pool and the game tier loses a subsystem |
| ~100% need judgement | the concept is not carrying answers, only prose — it is a lore book with extra steps |
| **a stable middle** | the two-layer split of §[`04`](04_planforge_reuse.md) is real, and the seam is where the judgement is |

Only the middle keeps both. This is the one step whose *result* changes the architecture rather than
confirming it, which is why it comes before any code lands in `composition-service`.

---

## POC-D — does a fidelity charter actually refuse something?

**Kills:** `BTG-A8`. A charter that cannot fail is the exact shape this repo has a standard against
(`NV-1`).

**Run:** express one position — *canon-bound on artifacts* — as criteria over provenance, in the same
form the contract generator's per-operation criteria already take, and evaluate POC-B's pool against it.

**Measured:** does it refuse a `PROPOSED` artifact member; does it **pass** the same pool under
*canon-inspired*; does it refuse the mechanism entirely on a foreclosed axis (POC-A's output feeding
`BTG-A7`).

**Bite-test, stated in advance:** delete the foreclosure from the charter and the refusal must
disappear. If it does not, the check is reading something else.

---

## What is deliberately NOT in the POC

* **No `GameConceptSpec` in `composition-service`.** §[`04`](04_planforge_reuse.md) §5 lists what that
  costs — a second spec type through `spec_index`/`compile`/`decompose`/`validate`, a second rule set,
  world-scoped runs. None of it is justified until POC-B and POC-C have reported.
* **No storage decision.** §[`02`](02_world_as_corpus.md) §4 recommends glossary-entities-on-the-bible-book
  and says what would break it. POC-B authors the concept as a **file**, so the storage question stays
  open while the content question is answered.
* **No member-role column on `worlds`.** §[`02`](02_world_as_corpus.md) §5 names it as missing; the POC
  has one world and can name its members by hand.
* **No reference game.** `BTG-A4` argues a reference game is what makes the gaps tractable, and that is
  the most interesting untested claim in this folder — but it needs a second corpus imported and
  role-tagged. It is the natural POC-E and it should not be smuggled into B.

## Order, and why

```
A  foreclosure detectable?        cheap · has an answer key · kills the charter
B  concept beats raw corpus?      reuses everything built · kills the tier
C  seam mechanical or judged?     changes the architecture either way
D  does the charter refuse?       cheap · confirms enforcement
E  does a reference game help?    the most interesting claim, and the least urgent
```

A and B are independent and could run in either order; A is first because it is cheaper and because a
dead charter would change what POC-B should even author.
