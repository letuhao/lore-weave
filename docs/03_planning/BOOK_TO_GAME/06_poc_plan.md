# 06 — The POC plan

**Nothing in this folder is built.** This is the ladder of the smallest things that could show the
design is wrong, ordered so the cheapest kill comes first.

The discipline is the one the game tier learned the hard way: *each planner has to be built and
measured; there is no formula, and the architecture only makes building faster.* Every step below has
its expectation written **before** the run, and a stated result that means **stop**.

**Constraint on every step: no new service, no migration, no change to `composition-service` until
POC-B has passed.** Everything runs against artifacts that already exist.

> ⚠ **PREREQUISITE, discovered 2026-08-01 after this plan was written.** The world this track built —
> 封神演義（原著）, 100 chapters — has **0 glossary entities and no knowledge project**. Extraction was
> skipped on purpose under the old plan, where the pool loop read the novel directly. Under the current
> design the glossary IS the subject matter, so **`POC-B`, `POC-C` and `POC-F` are blocked** until a
> live world has been extracted. **`POC-A` is not blocked** — it is a search over the self-contained
> fixture corpus and can run today.
>
> Satisfying the prerequisite is itself informative: what a real glossary of a 100-chapter classical
> Chinese novel actually contains — how many entities, which kinds, which of the 49 declared edge types
> fire — is the first honest input this design has ever had.

---

## POC-A — can a foreclosure be found at all?

**Kills:** `BTG-A8` — the charter's most useful signal. If *"the book says there is no ranking"* cannot
be found, a departure that contradicts a specific sentence becomes indistinguishable from one that
contradicts nothing, and the record §[`04`](04_fidelity.md) promises the human is incomplete.

**The stakes are lower than the first draft claimed**, and the correction matters for how this is read:
a missed foreclosure costs an **unrecorded departure**, not a wrongly-forbidden mechanism. The author
invents either way. So POC-A is about the *quality of the record*, not about permission.

**Why first:** cheapest, and it already has an **answer key written before the question was asked** —
`tests/fixtures/fengshen/fixture_teeth.json`, tooth `I2`, which records both the foreclosure
(寶各有用，未嘗較其次第 in ch65; 書中未嘗分品第 in the wiki) and nine terms that are `absent_everywhere`.

**Run:** over the fixture corpus, ask a deliberate *"does this corpus DENY that X exists?"* pass for a
handful of questions — some genuinely foreclosed (item ranking), some merely silent (how many
cultivation realms), some stated (who wields 打神鞭). Anchors and `locate()` supply the citation, so a
foreclosure that cannot be pointed at is not a foreclosure.

**Measured:** recall on the known foreclosure · **false-positive rate on the merely-silent questions** ·
whether the cited sentence is the right one.

The false-positive direction is the dangerous one, and under the corrected semantics the harm is
specific: a false foreclosure tells the author *"you are contradicting canon here"* when they are not.
It does not block them — nothing blocks them — but it puts a fiction in the record, and a record with
fictions in it stops being read. **A charter is only worth having if its departures are true.**

**Stop if:** the silent questions come back "foreclosed". A detector that cannot tell *absent* from
*denied* produces confident noise, and noise in the one artifact the human is supposed to trust is
worse than an empty artifact.

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

**Run:** hand-author **one gameplay design document for one element family** (`03_two_jobs.md` §4d) —
items is the obvious first family, because the fixture already has teeth there and the pool already has
three item slots to compile into. Deliberately small: the unique treasures the book names, **plus the
common item families the book does not have and a game needs anyway**. Then point the **existing**
contract generator at that document as its source and run the cycle unchanged.

The second half of that sentence is the test. A document containing only what the book contains is a
summary, and summaries are what §[`01`](01_the_missing_tier.md) measured failing. What makes an item
document a *design* document is the invented common families — the things there are enough of to drop,
craft and trade.

**Measured:** the criteria the pool loop already computes — pass rate, heal rounds needed, compression
(`m < n`), refusal quality — **and `evidence_n`, which is the tell**: if the document has a table of
contents, `n` is countable, and one of the three stuck problems is closed by construction.

**Also measured, and it decides §4b's caveat:** how much of the document the compiler could read
*without* judgement. This is the per-family parseability question, and items is the family most likely
to look easy — so a good result here must NOT be generalised to quests.

**Stop if:** the authored concept does not beat the raw corpus. That would mean the problem is not the
source material, and the whole tier is aimed at the wrong thing.

**Watch for the confound:** the concept will be authored by the same hand that wrote the 11-line block.
Beating the raw corpus is meaningful; beating the hand-written block is **not**, and must not be
claimed. What the block proves is that cooked material works — POC-B only has to show that a *document*
is at least as good as a *value*, while being editable, countable and re-readable.

---

## POC-C — does the concept decide enough that structuring needs no judgement?

**Kills:** `BTG-A13`/`BTG-A14` — the claim that authoring and structuring can be cleanly separated at
all.

**Reframed after the two-jobs correction.** The first draft asked whether the derivation was
"mechanical or judgemental" and treated *mechanical* as a discovery that would delete a subsystem.
§[`03`](03_two_jobs.md) settles that: **mechanical is the design goal.** The generators are supposed to
be deterministic. What is genuinely unknown is whether an authored document leaves them enough to work
with.

**Run:** with POC-B's concept, derive pool members with a **deterministic** structurer — no invention
allowed. Every place it cannot proceed is a `BTG-A14` finding: *the concept did not decide this.*

**Measured:** the **rate** and the **kind** of under-decision.

| kind of finding | what it means | what it costs |
|---|---|---|
| *the concept never mentions X* | authoring gap | send back to the author — normal, expected |
| *the concept says X in prose the structurer cannot pin down* | the handoff needs to be addressable (§[`03`](03_two_jobs.md) §5) | fixable in the handoff, not in either side |
| *the structurer wants a value nobody had reason to state* | the contract is asking for something the world does not have | a slot-registry problem, in the game tier |

**Stop if:** the third kind dominates. That would mean the contract is driving the concept rather than
the other way round, and the tier is being shaped by a schema instead of by a world.

**Explicitly NOT a failure:** a high rate of the first kind on the first pass. An authored document is
*expected* to be incomplete early — the return path is the product, not a defect. What matters is
whether the findings are **actionable by a human**, which is a judgement to be made by reading them.

---

## POC-D — does the charter refuse an UNDISCLOSED invention?

**Kills:** `BTG-A9`. A charter that cannot fail is the exact shape this repo has a standard against
(`NV-1`).

**What it must and must not check** — this is where the correction bites hardest. The charter checks
**disclosure, not obedience.** A `PROPOSED` artifact must be *allowed* under every position, because
the author may always invent. What must fail is a `PROPOSED` fact on a *retelling* axis that **does not
name what it departs from**.

**Run:** express one position — *retelling on artifacts* — as criteria over provenance, in the same
form the contract generator's per-operation criteria already take, and evaluate POC-B's pool against it.

**Measured, in three cases that must not collapse:**

| the fact | expected |
|---|---|
| `CITED` artifact | passes everywhere |
| `PROPOSED` artifact that names its departure | **passes**, including under *retelling* |
| `PROPOSED` artifact that names nothing | **fails** under *retelling*, passes under *inspired* |

**Bite-tests, stated in advance:** remove the departure note from the second case and it must go red —
that is the check's whole subject. And set the axis to *inspired*: the same fact must go green, or the
position is not being read and the charter is one rule wearing four names.

**Stop if:** the second row fails. A charter that refuses invention has reproduced the mistake this
folder was corrected for, in code.

---

## What is deliberately NOT in the POC

* **No `GameConceptSpec` in `composition-service`.** §[`05`](05_planforge_reuse.md) §5 lists what that
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
A  foreclosure detectable?           cheap · has an answer key · quality of the RECORD
B  authored concept beats raw corpus? reuses everything built · kills the tier
C  does the concept decide enough?    tests the authoring/structuring separation
D  does the charter refuse anything?  cheap · confirms disclosure is enforceable
E  does a reference game help?        the claim that makes a SYSTEMLESS source workable
F  does the KG yield an invariant?    the Lore Bible's whole premise, and it is SQL
```

**POC-F, added with §[`07`](07_lore_bible.md).** Two claims, both SQL and neither needing a model,
which makes this the cheapest step on the ladder and the one whose failure would be most expensive to
find late:

1. **The sweep has a real denominator.** Enumerate the glossary for the world, per kind, and confirm
   the number is stable, closed and countable — `5,431 / 5,412 described / 5,109 attributed / 4,943
   chapter-linked` on the stack today. This is `evidence_n`, the thing that had no definition against a
   corpus, and either it is a list or the spine of §[`07`](07_lore_bible.md) does not exist.
2. **A systemic claim can be recovered from typed edges.** The sharpest form: *the realm ladder falls
   out of `BREAKS_THROUGH_TO` edges even though no chapter lists the realms in order.*

**Scale is explicitly NOT what this measures**, and after the PO's correction that is the point rather
than a caveat: the problem was never *can we read enough of the book* — it is *is the list closed and
can we visit every element*. What POC-F must not be allowed to prove is a cost claim.

A and B are independent; A is first because it is cheaper and because what it finds changes what POC-B
should author.

**One re-ordering to consider.** `BTG-A7` says the tier's value is highest where the source is
thinnest, and every step above uses 封神演義 — a cultivation novel, the **easy** case, which ships with
a system. A second source with no system at all (a family saga, a detective novel) would test the tier
where it actually has to earn its place, and would probably be more informative than E. It is not
scheduled here because it needs a second corpus imported and the design does not yet say what a
systemless run even looks like — but a plan that only ever measures the easy case is a plan that will
be surprised later, and this paragraph exists so that surprise is at least expected.
