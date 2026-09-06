# Knowledge-refactor open decisions — the spec that replaces the deferral register

**Reconciles:** **Reading/writing entity or KG knowledge** · **No-Defer-Drift** · **A gate, lint, test, `const` assertion, validator** — this spec RETIRES `D-*` deferrals of the knowledge refactor, which is exactly what No-Defer-Drift requires a spec to do, and each decision it records names the gate that keeps it.

**Status: DECIDED.** Every row below was a `D-*` deferral in
[`docs/plans/2026-08-09-knowledge-architecture-refactor.md`](../plans/2026-08-09-knowledge-architecture-refactor.md).
They are decisions now.

## Why this document exists

**This project has no "blocked" and no "deferred".** A deferral is a decision that has been
described instead of taken, and thirty of them had accumulated — fourteen waiting on a scope
call, six on another task, nine without a stated unblock at all. The register was honest about
each individual gap and dishonest in aggregate: it read as *"tracked"* when it meant *"nobody
has decided."*

So the register is retired. Each row becomes one of exactly three things:

| | meaning | how it appears in the plan |
|---|---|---|
| **DECIDED** | the design is settled; what remains is typing | `📐 SPEC` row citing this file |
| **DONE** | built, with pasted evidence | `[x]` |
| **WITHDRAWN** | measured, and it was not real | struck through, with the measurement |

There is no fourth state. A task that cannot be finished today is still *decided* today — the
decision is what unblocks the typing, and typing is not a reason to leave a question open.

**The rule that replaces "fail closed with a deferral":** a `[~]` task must cite a spec section
that decides it. `scripts/plan-final-verification.py` enforces this. Describing a problem is no
longer a way to keep it open.

---

## 1 · The port

### 1.1 `GraphStore` grows a fact read — **DECIDED · ✅ DONE (A8, 2026-08-13)**
*Replaces `D-PORT-CANNOT-OBSERVE-FACT-STATE`, `D-T42A-PORT-CANNOT-CLOSE-AN-INTERVAL`.*

```python
async def facts_for(
    self, *, user_id: str, subject_id: str, type: str | None = None,
    as_of: int | None = None, limit: int = 100,
) -> list[Fact]: ...
```

**Why this shape.** The port can write a fact and cannot see one, so neither of `merge_fact`'s
contracts is verifiable: the ordinal chain is re-derived *after* the merge (the returned `Fact`
predates it and carries no `subject_id`), and duplication is invisible because the id is
content-derived — an appending store returns the same id a merging one does. One read makes the
chain, the duplication and the as-of window all observable, and it is the shape `relations_for`
already has, so the port gains no new vocabulary.

`as_of=None` reads the head; an integer applies the same half-open story window
(`valid_from <= N < valid_to`) every other timed read uses. A positionless fact is EXCLUDED by
a timed read, exactly as a positionless relation is.

**This also settles the interval question.** T42A said the port could open a story interval and
not close one. It still cannot *set* `valid_to_ordinal` directly, and that stays deliberate — a
raw setter lets a caller write an inconsistent chain. `maintain_chain` is the close, and
`facts_for` is how you check it worked.


**✅ Built in A8.** `facts_for` is on the port and on all three adapters, with four
conformance rules (chain · duplication-COUNT · half-open boundary · positionless excluded):
**72 → 82 passed**. The proof that this was the right read is that A7's vacuous bite —
forcing the fake's `merge_fact` to always create — now reds `3 == 1` on the COUNT rule while
still passing the content-keyed-id rule it was written against.

**One thing the decision did not anticipate, resolved under rule 9.** AGE IMPLEMENTS this
read even though its `merge_fact` raises: rule 9 says an adapter raises what it *cannot*
honour, and a half-open `WHERE` is not `maintain_chain`. The consequence is stated where it
bites — no rule can seed AGE *through the port*, so the two as-of rules seed raw Cypher and
read back through the port, rather than let `AgeGraphStore.facts_for` ship unreachable.
### 1.2 The port does **not** own janitorial work — **DECIDED · ✅ BUILT (A10, 2026-08-14)**
*Replaces `D-MAINTENANCE-IS-NINE-JANITORS`.*

`maintenance` measured out as nine things across eight consumers. They split three ways, and
only one class joins the port:

* **Domain reads → the port.** `project_graph_stats`, `count_nodes_by_label`. A second engine
  must answer these, and callers ask them as questions about the book.
  ⚠️ **Narrowed on build (A10): only `project_graph_stats` shipped.** `count_nodes_by_label`'s
  sole caller was the per-label loop in `jobs/stats_updater.py`, which the new operation
  replaces outright — so once the card is answered in one call there is no demand left, and
  the port's own law is *grows by demand, not by inventory*. Adding it anyway would cost four
  adapters + conformance + the shadow for a method nothing calls. The intent above — *a second
  engine must answer these* — is met by the one operation; the other stays in `neo4j_repos` as
  the Neo4j-internal helper the adapter is free to use.
  ⚠️ **`passage_count` does NOT cross the boundary.** The repo function counts four labels;
  a passage is the vector layer's row (§3.1 moves it to Postgres) and neither the AGE nor the
  Kuzu graph has a passage table. The port answers for the three labels the graph owns.
* **Constants → `app/domain/`.** `COUNTABLE_LABELS`, `PROJECT_GRAPH_LABELS`. Same class as
  `EVENT_ORDER_CHAPTER_STRIDE` and `SUPPORTED_PASSAGE_DIMS`: facts about the corpus, not the
  engine, and leaving them in `neo4j_repos` makes their importers look bound when they are not.
* **Destructive janitors stay ENGINE-SPECIFIC and out of the port.** `delete_orphan_extraction_sources`,
  `invalidate_stale_quarantined_facts`, `reconcile_evidence_count_for_label`,
  `clear_embedding_model_tag`, `delete_project_nodes_by_label`.

**Why the third class is excluded, in one sentence:** a swappable port is a promise that any
adapter can answer it, and a promise to delete orphan nodes in *any* graph engine is a promise
about housekeeping we have no reason to keep — the port exists so T43 can choose an engine on
measurement, and no measurement depends on who collects the garbage.

### 1.3 T17's remaining sweep is re-scoped by class, not by count — **DECIDED**
*Replaces `D-T17-SWEEP-IS-NOT-MECHANICAL`, `D-T17-PORT-SCOPE-UNDECIDED`, `D-T17-BACKFILL-CYPHER`.*

Of the 59 remaining binders: **51 need port operations that do not exist, 5 belong to the
vector layer T25 deletes, 4 are one-shot migration scripts, and the one the port already covers
is a known false match.** File count was never the cost; operation count is.

* **(a) Constants out of the engine layer** — do now, ~12 modules, the A4/A5/A6 shape.
* **(b) Vector-layer readers** — do NOT port. They are deleted by §3.1, not migrated.
* **(c) One-shot migration scripts** (`db/migrations/*`) are declared **out of port scope**.
  They run once, against a known engine, at a known version. Requiring them through a
  swappable port buys substitutability for code that will never be substituted, and the
  backfill Cypher `D-T17-BACKFILL-CYPHER` names is exactly this: it stays.
* **(d) The rest** wait on §1.1 and on identity (T35) — not because T17 is blocked, but
  because those operations' *shapes* are what T35 decides.

**`port-adoption-gate`'s ceiling is therefore not going to zero, and that is correct.** Its
floor is the number that measures this work; the ceiling measures how much is left that *could*
move. A gate whose target is zero would be lying about (b) and (c).

🔴 **CORRECTED 2026-08-22 (A14) — the paragraph below is superseded and its method is why.**
The classes are now DERIVED by `port-adoption-gate --classify` and ratcheted (`class (d) 34/34`):
**34** need a port operation · **7** need only a CONSTANT moved · **3** have only §3.1-deleted names
left · **7** one-shot/benchmark · **3** §1.2 janitors. A13's check was that the four classes sum to
54, which any partition of 54 does; the assignment was never checked. Its conclusion *"nothing in
the 54 is available to pick up"* is **false** — 10 modules move with no port growth at all. The
reasoning kept below (why janitors and one-shot scripts are out forever) still holds.

📊 ~~**MEASURED 2026-08-14 (A13) — the prediction now has its number.**~~ All 54 remaining binders
classified: **28** need a port operation whose shape (d) leaves to T35 · **17** are passage/vector
layer that (b) deletes rather than migrates · **5** are (§1.2) janitors · **4** are (c) one-shot
scripts. So the floor these decisions permit is **9** — the janitors and the scripts, out
forever — and the other 45 are downstream of T35's identity repair and §3.1's passage move.
**54 is not a backlog; it is 9 permanent plus 45 gated**, and nothing in it is available to pick
up today.

### 1.4 AGE refuses rather than half-implements — **DECIDED, and this is the standing rule**
*Replaces `D-AGE-EVENT-WRITE-UNIMPLEMENTED`, `D-AGE-BROWSE-PAGES-IN-PYTHON`, `D-T42-AGE-EVENT-SURFACE`.*

An adapter that cannot honour an operation **raises `NotImplementedError` naming this section**.
It never returns empty, never half-writes, never truncates silently.

The reason is that every alternative is invisible: an empty return reads as *"no such row"*, a
half-merge reads as a working timeline over a book with no history, and a truncated page reports
a `total` that describes the cap rather than the corpus. A refusal is the only failure a caller
cannot mistake for an answer.

**Each refusal is a conformance rule**, so "AGE is skipped here" can never quietly become "AGE
passed". The current refusals — event writes, fact writes, the browse past its scan cap — stand
until T42 settles AGE's write strategy, and are *decided*, not pending.

---

## 2 · The critic and QC-5

### 2.1b `name_grounding` misses invented names built from KNOWN syllables — **DECIDED (T46i, 2026-08-21)**

`D-NAME-GROUNDING-MISSES-DIACRITIC-NAMES` asked someone to *inspect* `audit_names` against
Vietnamese diacritic names and named two suspects. It is **both**, and the second produces the
reported symptom — `name_grounding: "checked"` with `unanchored_names: []` on a draft that
invented a character. Reproduced minimally:

```
known   {"Lam Trach", "Lam Uyen", "To Thanh Dao"}   ->  known_count 8, NOT 3
draft   "The door opened. Thanh Trach Uyen entered, and no one spoke."
result  unanchored: []   near_misses: []              <-  CLEAN, on an invented character
```

🎯 **The cause is word-against-word comparison.** `audit_names` tokenises BOTH sides to words:
the cast becomes its individual syllables (plus the full forms — hence 8 from 3), and the draft
becomes individual capitalised words. Vietnamese names are compositions of a small pool of
recurring syllables, so an invented name assembled from syllables that each appear in some
OTHER character's name matches on every token. `Thanh`, `Trach` and `Uyen` are each real;
`Thanh Trach Uyen` is not, and **nothing in the check ever looks at that string**.

Two amplifiers, neither of them the root cause: `len(word) < 3` drops short syllables outright
(`Vu`, and `Kỵ`/`Vô` in the real corpus), and `_is_name` discounts sentence-initial capitals, <!-- doc-language-gate: ok -- the two-character diacritic syllables ARE the measurement: their length is what the extractor drops -->
removing a run's head. When one syllable IS unknown the check fires but reports the
**fragment** — the author is told `Hac`, not `Trinh Hac Vu`.

📐 **DECIDED — the fix is to compare the capitalised RUN against the known FULL names**, not
syllables against syllables, with the syllable comparison kept as a fallback so a single-word
name still works. Two constraints the implementation must honour, both from the module's own
note that *"a name missing from `known` becomes a false accusation an author reads"*:

1. **A run that matches a known full name anchors ALL of its words** — otherwise every
   multi-word canonical name becomes a false accusation the day this ships.
2. **A run must not be reported when only its head is sentence-initial ambiguity** — "The door
   opened" and "The Grey Wren" are the same shape to a run-joiner, and one of them is prose.

✅ **IMPLEMENTED 2026-08-21 (T46n).** `extract_name_runs` + a run pass in `audit_names`, additive to the per-word pass. Both constraints above are met and bitten — and the FIRST implementation violated both, which the existing suite caught (seven failures, five real: prose became a name, a sentence-initial adverb joined one, a known plural was reported, and the book's own authored alias was accused). Two mistakes: the head-trim asked *"does this appear lowercased in the corpus"* instead of using `_FUNCTION_WORDS`, and it trimmed the draft side without trimming the known side. Symmetry was the fix.

⛔ **Was NOT implemented in the diagnosing batch, deliberately.** It is a design change across 35 assertions
and 3 production call sites in a check whose false-accusation direction is the one that hurts,
and this was diagnosed at the end of a long run. It is **decided, not deferred**: the shape
above is the fix, and
[`test_name_grounding_diacritic_runs.py`](../../services/composition-service/tests/unit/test_name_grounding_diacritic_runs.py)
pins today's wrong behaviour with messages that name this section, so the fix cannot land
silently and cannot be mistaken for a regression when it does.

### 2.1 The acceptance measurement is **three runs, majority rule** — **DECIDED**
*Replaces `D-QC5-PIPELINE-NOT-REPRODUCIBLE`.*

QC-5 passes when, over **three runs of the same chapter with the same models**:

* **at least two** produce `canon_consistency <= 3` **and** at least one attributed violation, and
* **no run** produces `5/5` with zero raw findings.

**Why majority and not unanimity.** Measured 2026-08-13: three runs gave `severe / warn / ok`
(canon 2 / 4 / 5). Demanding unanimity makes the test fail on a working pipeline; accepting one
run makes it pass on a broken one. The second clause is the one that matters — a clean 5/5 with
*nothing found* is the defect signature, and it must not appear in any of the three.

⚠️ **APPLIED 2026-08-14 (QC-5 C6): the recorded runs FAIL both clauses** — 1 of 3 on clause 1,
and run C is a `5/5` with zero raw findings, which clause 2 exists to make unpassable. Note the
limit honestly: these are the same three runs this section cites as its reason, so the
evaluation scores a rule against its own motivating examples and cannot validate the RULE. It
validates the PIPELINE, and only because the rule fitted to these runs still fails on them. A
fresh three-run measurement on a chapter that did not set the rule is what QC-5 now owes.

🔴 **CLAUSE 1 IS MEASURING THE DRAFTER (2026-08-21, QC-5 C14) — a defect in the criterion, not
in the flow.** Clause 1 requires *">=2 runs with `canon<=3` and at least one attributed
violation"*, which is only satisfiable when the DRAFTER produces a canon violation. Six runs
across two chapters (C7 chapter 5, C13 chapter 12 — the betrayal arc) produced
`canon_consistency=5` every time and **zero** canon violations, so clause 1 scored 0/6.

**The critic is not the problem, and that is measured.** A passage constructed to contradict `R1`
— naming a different betrayer, where `R1` says *"no one else is the betrayer in the trap"* — run
through the real system prompt with the real six rules scores **`canon=1`, attributed to `R1`,
3/3, with zero invented ids**. Same prompt, same model, same rules as the six failing runs; only
the passage changes.

⚠️ **This section forbids the experiment that separates the two**, and that is the actual defect:
*"Each run re-drafts… a fixed-draft experiment would measure a component nobody uses in
isolation."* Sound for measuring the FLOW, wrong as the only measurement — it leaves the
criterion unable to tell a critic that cannot see a violation from a drafter that does not make
one, and it has been reporting the second as the first.

**The PO's choice, now a real one:** seed a known-bad draft so clause 1 has something to attribute
(accepting a fixed-draft arm alongside the end-to-end one), or restate clause 1 against what the
flow does produce. Either changes the acceptance criterion. What is no longer in question is
whether the critic can attribute a violation: it can, 3/3.

✅ **CLAUSE 1 IS SPLIT — PO sign-off 2026-08-21, re-run and scored (QC-5 C16).** The choice
above was taken: restate the criterion against what the flow actually produces, in two arms
that are measured separately and read together.

* **1a — critic capability.** Three runs of a PLANTED violation through the real system
  prompt with the real active rules. Passes when >=2 attribute it with `canon<=3`.
  Re-run 2026-08-21: **3/3, `canon=1`, attributed to `R1`, zero invented ids.**
* **1b — drafter compliance.** Three runs of the flow. Passes when no run produces an
  attributed canon violation **and** no run discards a finding it could not attribute
  (`raw > attributed` is the C10 defect, not a clean draft).

🔴 **1b IS SCORED ONLY WHEN 1a PASSES, and this is the whole point of splitting rather than
relaxing.** "Zero attributed violations" is precisely what a canon-clean drafter and a critic
that attributes NOTHING both produce. Read alone, 1b would have scored a PASS through the very
weeks the critic was inventing rule ids and discarding every finding (`dropped=2 of 2`; `9
discarded across three runs`). A 1b verdict with no planted arm is **UNSCORABLE**, never a pass.

⚠️ **CLAUSE 2 HAD THE SAME HOLE, POINTING THE OTHER WAY, and only the re-run exposed it.**
After the author added `R7` the drafter complied and three flow runs scored **`canon=5,
raw=0`** — byte-identical to the *"clean 5/5 with nothing found"* this clause was written to
catch. Scored as written, the architecture's own success reads as its defect signature. So a
5/5-with-nothing-found is believable only when the measurement shows BOTH:

1. **1a passes** — the critic can attribute a violation that is there; and
2. **a `flow_control` run found something** — the critic is live IN THE FLOW, not merely below
   the seam. This is not redundant with 1a: 1a drives the judge directly with no drafter, so
   it stays green for a flow that never calls the critic at all, in which every run reports
   `raw=0` and reads as a perfectly canon-clean book. In the real measurement the control is
   the PRE-R7 runs on the same chapter and flow, at raw **3 / 6 / 2**.

Without both, clause 2 keeps exactly the teeth it had.

📐 **The criterion is now executable, not prose:** [`scripts/qc5-acceptance-gate.py`](../../scripts/qc5-acceptance-gate.py),
wired into pre-commit by its offline `--selftest` (11 checks) and bitten five ways. Its
load-bearing selftest asserts the 1b **clause row**, not the overall verdict — checking only
the overall answer left the 1a-gating unpinned, and a bite that removed it stayed green.

**Scored on the 2026-08-21 re-run: `1a PASS · 1b PASS · 2 PASS` -> QC-5 PASS.**

✅ **AND RE-SCORED ON AN INDEPENDENT CHAPTER (QC-5 C17) — the verdict now counts.** The first
scoring used the chapter-12 runs that MOTIVATED the clause-2 regate, so it graded a rule
against its own examples. Re-run on **chapter 10**, which has zero prior critic runs and sits
in the betrayal arc so `R1`-`R6` are live over it: three runs, `canon=5`, `raw=0`,
`violations_dropped=0`, `active_rule_count=6`, and one substantive craft note each — C11's
channel routing an out-of-rule finding correctly on a chapter that did not motivate it.
`1a PASS · 1b PASS · 2 PASS` -> **QC-5 PASS**. The ROW stays `[~]`: `plan-verify` refuses a QC
task that certifies open work, and QC-5's section still carries `D-QC5-ROLE-JUDGE-PRECISION`
(spend), `D-QC5-ACCEPTANCE-BOOK-ROLES-UNPLACED`, `D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER` and
`D-T38-MECHANISM-IS-VACUOUS`. The MEASUREMENT and the ROW are different claims; what closes the
row is those deferrals, not another run.

The `flow_control` arm stays the chapter-12 PRE-R7 runs on purpose: it is an INSTRUMENT
CHECK (*"does this flow's critic ever produce a violation record?"*), not evidence about the
chapter under test. The part that had to become independent is the FLOW ARM, and it did.
✅ **DELIVERED 2026-08-21 (QC-5 C7) — chapter 5, and the verdict is still DOES NOT PASS.** Three
runs, same models, same chapter, on lw-iso against local models for $0.18: canon **4 / 5 / 4**,
raw findings **3 / 5 / 1**, attributed **0 / 0 / 0**. Clause 1 scores **0 of 3**; clause 2 holds,
because run B's 5 came with five findings rather than none.

**Both halves are now separable, and they say different things.** The RULE is validated — clause 2
could have fired on run B's 5 and correctly did not, so it discriminates instead of punishing any
high score. The PIPELINE fails worse than on chapter 11: 0 of 3 runs attribute against 1 of 3
there, and **9 findings are discarded across the three runs**. With C3's 7-of-7 that is three
independent chapters showing one shape — the flow detects violations and cannot say whom they are
about.

⚠️ `voice_match` collapsed to 1–2 on all three runs and tripped `critic_severe` twice. It is
outside this rule, and is recorded rather than folded into the verdict.

**Each run re-drafts**, so this measures the pipeline, not the judge alone. That is deliberate:
QC-5's claim is about the flow a user runs, and a fixed-draft experiment would measure a
component nobody uses in isolation.

### 2.2 `active_rules` comes from the canon-rule corpus — **DONE 2026-08-13**
*Replaces `D-QC5-ATTRIBUTION-CHANNEL-UNWIRED`, `D-QC5-FLOW-PRODUCES-NO-CANON-CONSISTENCY`,
`D-QC5-FULL-FLOW-CAPTURE`.* Shipped in C5; a run attributed two violations to real
`canon_rule` ids and the breaker paused it.

### 2.3 The judge's verdict stays per-rule, and the score stays advisory — **DECIDED**
*Replaces `D-QC5-PROSE-JUDGE-VERDICT-NOT-PER-RULE`, `D-QC5-ROLE-JUDGE-PRECISION`.*

`violations[]` keyed by `rule_id` is the enforceable output; the four dimension scores are
advisory and drive severity only. **Precision is preferred to recall on the rule channel**:
`map_rule_tokens` keeps dropping what it cannot attribute, because a finding nobody can
attribute is noise with a citation. `violations_dropped` makes the loss visible, which is what
makes the strictness affordable.

### 2.4 The canon bible is the quality report's source too — **DECIDED**
*Replaces `D-QUALITY-REPORT-CANON-UNANCHORED`.* `engine/canon_bible.py` is the one home; the
quality-report endpoint already calls it after C2. No second rendering path is created.

### 2.5 Name grounding: `truth_source` is reported, and the proxy is not a bug to fix here — **DECIDED**
*Replaces `D-NAME-GROUNDING-USES-PROMPT-PROXY-IN-PRODUCTION`, `D-NAME-GROUNDING-MISSES-DIACRITIC-NAMES`.*

`name_truth_source` rides the envelope (shipped). When it reads `prompt_proxy` the check is a
self-consistency observation and **callers must treat it as such** — that is the fix. Making the
name check canon-backed is §1.1's `facts_for` plus a cast read, and it is scheduled there, not
duplicated here. Diacritic-insensitive matching is a **capitalised-Latin heuristic limit,
accepted**: the CJK/Vietnamese path is the dictionary anchor, not the capitalisation rule.

---

## 3 · The vector layer

### 3.1 A new task wires `VectorStore` into the read path — **DECIDED · ✅ DONE (T24b-a + T24b-b, 2026-08-13)**
*Replaces `D-T42D-GRAPHSTORE-HAS-NO-CALLERS`; unblocks T25.*

Measured: `grep` for constructors of `PgVectorStore` / `Neo4jVectorStore` / `DualWriteVectorStore`
outside `app/adapters/` returns **nothing**. Phase 3 goes build image → write adapter →
dual-write → cut over, and **no task ever wires the port into the read path**, so T25 cannot cut
over anything.

**T24b — wire the three readers** (`context/selectors/passages.py`, `routers/public/drawers.py`,
`search/retriever.py`) onto `VectorStore` through a provider, exactly as `get_graph_store` does
for the graph. T25 then becomes what it claims to be: flip the provider, drop the Neo4j indexes.


**Measured in T24b, and it splits the task in two — DECIDED.** "Wire three readers onto the
port" assumed the port could serve them. It could not serve **any** of the three:

| reader | what the port could not give it |
|---|---|
| `search/retriever.py` | nothing — `vector_hit_to_raw_hit` was built by T25b and has **zero callers** |
| `routers/public/drawers.py` | `project_id` and `created_at`, both fields of the *published* `DrawerSearchHit` |
| `context/selectors/passages.py` | the stored VECTOR — MMR diversity computes hit-to-hit cosine from `hit.vector` |

The third is the sharp one. `VectorHit.vector` has existed since T14 and **no adapter could
ever populate it**: `search()` had no `include_vectors`, so the Neo4j adapter called
`find_passages_by_vector` without it, the repo default `False` won, and `vector=h.vector`
assigned `None` on every hit forever. The port promised a field no caller could obtain. So the
L3 selector was not un-migrated for want of effort — the capability was missing.

So:

* **T24b-a — the port can serve all three readers.** `search(include_vectors=…)`; the two
  drawer fields and `block_index` projected by *both* backends; a `created_at` column plus the
  `ADD COLUMN IF NOT EXISTS` backfill that keeps a pre-T24b deployment working. Done, with
  four bites.
* **T24b-b — flip the three call sites onto `get_vector_store`.** This is where the live
  smoke belongs: a read-path cutover that changes which store answers a user-visible search is
  exactly a batch that crosses a service seam, and QC (b) is not satisfiable from unit tests.
  **Done** — the three call sites are on `get_vector_store` (vector read call sites on the repo
  **3 → 0**), proved in a rebuilt `lw-iso` container against a real Neo4j: `created_at` and
  `project_id` arriving through the migrated reader, `include_vectors=True -> vector len = 1024`,
  and the spoiler window dropping chapters 5 and 9 at a cutoff of 4.

Splitting here rather than shipping half a wiring is the same call `vector_store_provider.py`
already records for the write path — *"the read cutover needs its own task and its own
evidence."* -b is that evidence.

**And the parity is enforced, not asserted.** Neo4j builds its attributes as a dict literal,
Postgres from a column tuple, in two files with nothing relating them — the seven-names-in-a-
Go-const-block shape this repo has a gate for. `test_the_two_real_backends_agree_on_a_passage_hits_attribute_KEYS`
reads the Neo4j keys out of the adapter's **AST** and compares them to `_PASSAGE_ATTRS`, so a
key added to one and not the other reds by name.


### 3.3c `D-T25B-PG-ANCHOR-SCORE` is ANSWERED — join it, do not copy it — **DECIDED (T25p, 2026-08-23)**

§3.3 left entity vector reads on Neo4j because `PgVectorStore` cannot carry `anchor_score`:
it is *"bucket-relative and recomputed on its own schedule, so a copy on the vector row would
be confidently stale"*. **That reasoning is correct and was re-verified before being acted on,
not assumed away.**

Measured on the dev graph (read-only), against the hypothesis that the score is really a
binary anchored/not flag that could simply be copied:

```
anchor_score = 1.0     4310
fractional              394      <- 17/22, 7/11, 4/29 … genuinely recomputed ratios
anchor_score = 0.0      358
```

**The hypothesis is refuted.** 394 entities carry a computed bucket-relative value, so a copy
on the vector row would drift exactly as §3.3 says. The sealed decision stands on its own
terms.

🎯 **What changed is not the reasoning — it is a FACT the reasoning depended on.** §3.3 was
written 2026-08-13, when the authority for `anchor_score` was Neo4j and the vectors were in
Postgres. Two stores, so the only options were *copy it* (stale) or *stay on Neo4j*. Since T54
the graph is AGE, and:

```
KNOWLEDGE_AGE_DB_URL     knowledge-pg:5432/loreweave_knowledge_vectors
KNOWLEDGE_VECTOR_DB_URL  knowledge-pg:5432/loreweave_knowledge_vectors     <- the SAME database
```

**The vectors and the authority are now in one database.** A third option exists that did not
on 2026-08-13: *join it at query time*.

**Proven live on `lw-iso`, backend `age` — one query, one database, the two-layer product:**

```
 entity_id                        |  raw   |    anchor_score    | weighted
----------------------------------+--------+--------------------+----------
 25cc8dde2a8fd9d7e86eeea4ec42aa02 | 1.0000 | 0.7727272727272727 |   0.7727
```

The `anchor_score` there is a real fractional value set on the vertex and read back through
the join — **not** a NULL, deliberately: a NULL result cannot distinguish "the join worked and
the value is absent" from "the join failed", and the first run of this probe returned exactly
that ambiguous NULL.

**Decided.** `PgVectorStore` keeps OMITTING `anchor_score` from its own rows — the staleness
argument is untouched and the `KeyError` safeguard in
`app/context/selectors/glossary.py` stays exactly as it is. The entity search JOINS the score
from the AGE vertex in the same statement, so the value is read from its authority on every
query and can never be stale. No copy, no second round trip, and no port growth: `GraphStore`
does not gain an `entities_by_ids` it would only have needed to work around two databases.

⚠️ **What this does NOT do.** It unblocks T25 step 4; it does not perform it. Building the
joined entity search in `PgVectorStore`, flipping `knowledge_vector_read_primary` for the
entity scope, and deleting the entity/event vector DDL remain the work. It also does not touch
`find_entities_by_vector`'s Neo4j `CALL db.index.vector.queryNodes` — that function is one of
the two `MAX_VECTOR_PROCEDURE_SITES` owners and §3.1 deletes it rather than porting it.

📐 **And this is why a sealed decision gets re-read rather than obeyed.** §3.3 was right for
its facts. Rule 13 says prove which side is wrong from the workload — here neither side was
wrong; the workload moved underneath a correct conclusion, and nothing would have noticed
because the decision reads as settled.


### 3.3 QC-3 is SIGNED OFF — halfvec HNSW replaces StreamingDiskANN — **DECIDED (PO 2026-08-21)**

The checkpoint's owed evidence was delivered (real-corpus recall/latency on both backends,
the rebuild measurement above the parallel-build threshold, and the restore drill), and the
PO signed off. Three dispositions, all now implemented rather than recorded:

1. **Adopt `halfvec_hnsw`.** On the real corpus diskann recalled **0.836** with a worst query
   at **0.500** and was the slowest non-fp16 cell; halfvec_hnsw scored **1.000** at ~41 % of
   the table bytes. It also reaches dims the alternative could not: pgvector caps HNSW at
   2000 dims for `vector` but 4000 for `halfvec`, so 2560 and 3072 gain an exact-free path.

   ⚠️ **The COLUMN stays `vector(dim)`; only the INDEX is halfvec.** The bench cell measured a
   halfvec *column*, but Decision T4 calls these vectors durable primary data and rewriting
   them to fp16 is not reversible — an index is. `DROP INDEX` puts diskann back; a downcast
   column cannot be undone. The one-line grant did not settle this, so it is settled here.

2. **MED-2 → migration ticket.** `PRIMARY KEY (entity_id)` → `PRIMARY KEY (user_id,
   entity_id)`, `ON CONFLICT (entity_id)` → `ON CONFLICT (user_id, entity_id)`, and delete the
   `user_id = EXCLUDED.user_id` assignment that only exists because the conflict target cannot
   carry the tenant. Not taken here: it is a schema change on a live table and rule 7 makes it
   a step of its own. The ticket is a **tripwire, not prose** — two tests assert the current,
   known-wrong shape, so the migration cannot land without deliberately rewriting them.

3. **MED-3 → accept-and-document.** Post-cutover the secondary is Neo4j, so a Neo4j outage
   still fails every ingestion job at its first `ensure_index` — even though pgvector could
   serve alone. Accepted, and documented at the call site rather than in a plan nobody reads
   at 3 a.m. Swallow-and-count was rejected because it buys availability with silence: a
   swallowed `ensure_index` leaves the demoted store accumulating unindexed writes, found
   only when a cutback needs it. Revisit once `read_primary == "postgres"` has soaked.

**LOW-4 was real and is fixed in passing.** `ensure_index` returned the `emb` name that
`ensure_vector_schema` had just dropped, and the name parser rejected `emb_hv` — so the store
built an index it could not drop and advertised one that no longer existed.

### 3.2 The restore drill's recall gap is accepted and documented — **DECIDED**
*Replaces `D-T25B-SOAK`.* `pg_restore` rebuilds the ANN graph rather than copying it, so
post-restore top-10 overlap was 7/10 at 20 000 rows. **Data recovery is promised; *result*
recovery is not.** That is the guarantee, written down. QC-3 still owes one rebuild measurement
above `diskann.min_vectors_for_parallel_build = 65536`, because below it every timing is
single-threaded and there is no defensible RTO — that is a measurement, and it is scheduled in
QC-3, not deferred.

---

🔴 **The dual-write soak was never running, and the record said it was (2026-08-21, T25c).**
`D-T25B-SOAK` marked its first half DONE on 2026-08-12 and its second half *"wall-clock and
cannot be worked, only waited"*. Measured: `KNOWLEDGE_VECTOR_DB_URL` is unset on the dev stack,
the `knowledge_vector_dual_write_total` family is **absent** from `/metrics` (the store is never
constructed, so nothing registers), and the secondary holds **0 rows in all four vector tables**
against 1051 live passages. `infra/docker-compose.yml:1234` passes the variable through from the
invoking shell, and the container was recreated 2026-08-14.

**A wait is a claim in the present tense and gets checked like any other number.** Nine days
elapsed against a switch that was off, and `secondary_failed = 0` read the same throughout.
`scripts/soak-armed-gate.py` now separates the states that were indistinguishable — **DISARMED**
(family absent), **ARMED_IDLE** (present, no writes), **SOAKING**, **FAILING** — so the only
passing state requires writes to have actually landed. Its bite is the design: a probe that
counts `prometheus_client`'s registration-time `_created` gauges reads an unwired service as 1.78
billion successful writes.

⚠️ Restarting the soak writes real vectors to a real Postgres on a shared stack — `OD-2`'s
operational half, re-opened, and a rule-6 write. The ask is narrower than before: the variable
must **outlive a container recreate**, or this recurs.

### 3.3 The vector cutover is PER SCOPE — **DECIDED (T25, 2026-08-13)**

Found by building it: `test_the_provider_keeps_neo4j_as_primary`, a tripwire T25b wrote for
this exact day, redded on the argument swap **before the change shipped**.

`PgVectorStore` deliberately omits `anchor_score` from an entity hit
(`D-T25B-PG-ANCHOR-SCORE`) — it is bucket-relative and recomputed on its own schedule, so a
copy on the vector row would be confidently stale, and the adapter leaves the key OUT rather
than setting it to `None` so a consumer that ranks by it raises instead of multiplying every
score by nothing. **Entity reads rank by it; passage reads do not.**

So `knowledge_vector_read_primary="postgres"` moves **passages only**. Entity reads stay on
Neo4j until `anchor_score` has an answer. A single primary would have forced one of those two
facts to be ignored, and the one that would have been ignored is silent: two-layer retrieval
collapsing to raw cosine reorders every result and raises nothing.

**TIER (rule 4): a deploy ceiling.** One migration state for one deployment. Per-book would
make two books' results incomparable and `vector_shadow_read_overlap` meaningless — it would
average over whichever backend each request happened to pick. A run param would let one
request cut over and the next one back.

**Post-cutover the shadow runs in reverse** (Neo4j compared against pgvector), so the old
store keeps answering alongside the new one and the overlap metric keeps measuring
new-against-old in whichever direction the deployment currently points.

**What is still owed is not code.** Dropping the Neo4j vector indexes (T25 ③) needs the soak
and QC-3's rebuild measurement above `diskann.min_vectors_for_parallel_build = 65536`, without
which there is no defensible RTO. Both are measurements on a running system, and QC-3 is where
the plan runs them.

---

## 4 · Identity, facts and the model

### 4.1 Opaque identity proceeds behind the port — **DECIDED**
*Replaces `D-T35-COLLISION-GROUPS-ARE-GLOSSARY-DEBT`.* T35 re-keys 48 Cypher sites; doing it
after T17's port growth makes it one change instead of forty-eight. Collision groups are
glossary-side debt and are **not** T35's to fix: T35 makes the KG's id opaque, and a glossary
that mints colliding names is a separate defect with its own owner.

**T35a (2026-08-14) — the fix belongs at EVERY writer that mints, not just `merge_entity`.**
Found by building it: `upsert_enriched_anchor` still MERGEd on the recomputed hash, and its
"free the stale glossary claim" statement — which runs first, because
`:Entity(glossary_entity_id)` is UNIQUE — treated the author's own renamed character as the
stale holder. So a write-back after a rename minted a stub **and moved the glossary anchor
onto it**, leaving the real node silently unanchored. Worse than a duplicate, because a
duplicate is visible.

The resolution is `merge_entity`'s, and its `coalesce` order is the safety property: a node
already at the caller's id wins (a strict no-op for every write that works today), and the
anchor holder is consulted only when nothing is at that id. `upsert_enriched_anchor` now
returns the resolved id so the facts attach to the node the anchor actually lives on — the
caller was passing the recomputed hash to the fact `MATCH`, a second defect inside the first.

**Retiring the derivation is not the same as relocating it.** Moving it out of the router and
into the repo left `derived-entity-id-gate` at **5 → 5**. The layer is right now; the count
falls when the derivation goes.

**T35b (2026-08-14) — `glossary_sync.py` was never a minting site; the description was stale.**
`_GLOSSARY_ANCHOR_SYNC_CYPHER` MERGEs on `(user_id, project_id, glossary_entity_id)` and uses
the derived id only in `ON CREATE SET`. A rename finds the same node by anchor, so there is no
second hash to miss — and `ON MATCH SET` *not* rewriting `e.id` is correct, not the defect: an
opaque id that changed on rename would break every join that stored it. True before T17 moved
the MERGE into the repo and keyed it on the anchor; carried forward unmeasured since.
`derived-entity-id-gate` 5 → 4.

**What is actually left of T35** is repointing the **join sites** off `Entity.id`. The three
remaining callers are not migrations: `entities.py` holds the derivation legitimately (minting
is a storage detail), `recanon_honorifics.py` is a one-shot backfill whose purpose is
recomputing ids, and `fake_graph_store.py` mirrors the real adapter by design.

**T35c (2026-08-14) — T35's minting half is CLOSED, and "48 join sites" was the wrong
target.** `Entity.id` is stable: no writer recomputes-and-misses any more, so joining on it is
correct and the readers never needed repointing. The remainder was always writers that MERGE
on a hash of mutable properties, and there were **three**: `merge_entity`, the enrichment
anchor (T35a), and `upsert_glossary_anchor` — the Pass 0 pre-loader that runs on every
extraction pass. Each is now resolve-first.

The pre-loader's own docstring had admitted the defect and described it wrongly: it said a
rename *"creates a NEW node"*, but `:Entity(user_id, project_id, glossary_entity_id)` is
UNIQUE, so the write **raises** and the anchor pre-load stays broken for that entity on every
later pass. Measured, not inferred.

**What T35 does NOT still owe:** the four remaining `derived-entity-id-gate` callers are a
storage-layer mint (`entities.py`), a mint fallback (`enrichment.py`), a one-shot backfill
(`recanon_honorifics.py`) and a test double (`fake_graph_store.py`). None is a migration; the
gate falls only if the derivation is retired outright, which nothing now depends on.

### 4.2 T37's command producer follows T36's shape — **DECIDED**
*Replaces `D-T37-COMPOSITION-COMMAND-PRODUCER`.* The producer writes role facts in the shape
T36 defines. Building it earlier would ship a command surface whose payload is still moving;
that is sequencing, and the sequence is now stated rather than pending.

### 4.2b Roles get TWO producers: planforge and the studio — **DECIDED (PO, 2026-08-14)**

The question T37a could not measure its way to — *which composition surface authors a role* —
answered: **both plan-time and explicit author action.** One transport
(`KalClient.append_role_fact`), two callers.

**Why both, and not the compose-time option.** Emitting at compose time was the simplest
lifecycle (a role fact exists only if prose exists, so nothing ever needs retracting), and it
fails the acceptance case: the guard could not see a role until after the chapter it appears
in was written, so it would never guard that chapter's own first draft. The whole point of
`D-CANON-CHECK-BLIND-TO-ROLE` is catching a misattribution *as it is drafted*.

* **Planforge, at plan time** — when the pipeline designs an arc and decides who betrays
  whom, it appends the role at `valid_from_ordinal = planned chapter × EVENT_ORDER_CHAPTER_STRIDE`.
  Roles then exist *before* the prose, which is what lets the canon check guard draft #1.
* **The studio, on an explicit author declaration** — Q2's *"plan-authored, not extracted"*
  read literally. The author is the authority on a role the plan only implies.

**The consequence the plan-time half owes: a plan revision must CLOSE the roles it no longer
implies.** A fact appended at plan time and never retracted outlives the plan that justified
it, and an as-of read would then hand the guard a role the book abandoned — the same "stale
but confidently served" failure as the 175 already-closed `:RELATES_TO` edges T36 found being
served as currently true. `POST /v1/kal/books/{id}/facts/close` is the mechanism and already
exists (ordinal-aware valid-time close, §12.3.2); wiring it to plan revision is part of the
planforge caller, not a later task.

**The studio half splits by layer.** Its backend surface is buildable now; the UI is T51's,
which §6.5 already sequences after T38 (complete) and T32. So T37b is the planforge caller
plus the studio's backend endpoint; the studio UI rides with T51.

**The acceptance test for both is one number.** T36 measured `relation 0` in `entity_facts`.
T37 is done when a real run turns that into a non-zero count and the canon check reads it.

### 4.2c The plan-time producer needs a STRUCTURED role, and the plan has none — **DECIDED (2026-08-14)**

Measured before building the planforge caller (rule 8), and it re-scopes T37b.
`cast_plan.ProposedChar` carries:

```python
relationships: str = ""      # free-text ties to other cast ("huynh trưởng of Lâm Uyển")  # doc-language-gate: ok -- the code comment verbatim; paraphrasing it would hide that the field holds prose
```

**Free text, not a `(subject, predicate, object)` triple.** `append_role_fact` needs
`attr_or_predicate` and `value` as separate fields, so plan-time authorship has nothing of the
right shape to send. Nothing else in the engine carries a structured tie — `grep` for
`predicate` outside `canon_check.py` returns only unrelated boolean predicates.

This is the same class as the two batches rule 8 already caught this session: *"migrate X"*
that turns out to be *"X has nowhere to go yet."*

**DECIDED: ask the model for the structure it is already producing.** `ProposedChar` grows
`roles: list[{predicate, object}]` alongside `relationships`, and the cast prompt asks for
both. The information is in the model's answer today; it is only being requested as prose.

**Not chosen: parsing the free text into triples.** It would need either an LLM pass (a second
spend on data the first pass already had) or a heuristic, and a heuristic over multilingual
free text is precisely the over-extraction class the plan already records against the
extractor — `"Sự phản bội tại khởi đầu" -[betrayed]->` <!-- doc-language-gate: ok -- a stored node name from the cited corpus; translating it would break the identity the evidence turns on --> is an event phrase promoted to a
character by exactly that kind of parsing. A role fact minted from a mis-parse is worse than
no role fact: it is a canon claim the guard will enforce.

**`relationships` stays.** It is prose the packer already uses for context, and the structured
`roles` field is additive — the two answer different questions and dropping the prose to make
room would degrade the prompt to serve the graph.

⚠️ **This touches an LLM output contract**, so it lands with the cast-plan eval rather than
beside it: a prompt change that shifts `is_new` classification or cast sizing would be a
regression the graph write is not worth. That is the sequencing, and it is why T37b's
planforge half is a prompt-and-eval batch, not a client call.

### 4.3 Causal coverage is measured in QC-6, not before — **DECIDED**

⚠️ **THE TITLE OUTLIVED THE BODY — corrected 2026-08-21 (T33d).** Everything below this note
measures **identity**, and QC-6 was ticked against that table while the causal measurement this
section is NAMED for was never taken. Found by the supersession audit rather than by anyone
reading the section, which is the point: a heading and its body drifted apart and the tick went
to the body.

Taken now, scoped to the one project the causal writer ran on: **32 events, 3 carrying a causal
edge, 4 edges — 9.38 %**. That replaces the retracted global 0.34 %, which divided by residue
from runs that never touched the causal pipeline. It is a **baseline, not a verdict**: with the
reference corpus ruled out there is no target to pass, and causal links are genuinely sparse.
What it buys is that X1 can now argue from a number instead of an artefact.
*Replaces `D-T33-CAUSAL-COVERAGE-UNMEASURED`, `D-QC6-IDENTITY-LIVE-PROOF`.* Both are live
proofs on real data, and QC-6 is where the plan runs them.

**QC-6's DATA criterion is corrected (2026-08-21, QC-6a) — it was the negation of §4.1.** The row
asked for *"a count of nodes whose `e.id` disagrees with a recomputed hash — must be 0"*, which
can only be reached by rewriting `e.id` whenever a name changes. §4.1 retired exactly that:
*"an opaque id that changed on rename would break every join that stored it."* Not an argument —
**measured**: a bite that implements the old criterion, rebuilt into the image and re-run against
the live stack, moves the id three times across rename + re-kind and fails the live proof.

The replacement asserts what the row's prose always asked for, and unlike "must be 0" it is
satisfiable:

| | assertion | measured 2026-08-21 |
|---|---|---|
| **no minted duplicate** | zero `(user_id, project_id, canonical_name, kind)` groups with >1 node | 4872 groups / 4872 nodes, largest **1** |
| **no stale node** | every glossary anchor resolves to exactly one node, and no touched node is left unanchored | 4305 anchors / 4305 anchored nodes |
| **opaque identity** | `e.id` does NOT move across rename or re-kind | proven live, both write paths |

The old count is retained as a **health indicator, not a gate**: under opaque identity it counts
entities renamed since minting (**1847 / 4872**, of which 1846 anchored — the population the
rename path touches). A zero there would mean the derivation had come back.

⚠️ **The "77 known-stale nodes from the 2026-08-02 backfill are reconciled" clause goes with it.**
It described what *that* backfill left behind under derived identity; there is nothing to
reconcile once the id is opaque, and the honorific backfill that *does* re-key nodes is
`D-ML-A5-RECANON-BACKFILL`, a separate operator concern (§4.1 lists it among the legitimate
remaining callers).

### 4.4 T41's relations are not rebuildable from the glossary — **DECIDED, accepted**
*Replaces `D-T41-RELATIONS-NOT-REBUILDABLE`.* The glossary is the SSOT for entities, not edges:
relations and events are extraction-derived. A rebuild restores the entity layer and **must say
so** — `ISOLATED_STACK.md` already documents the resulting graph as entity-complete and
edge-empty. Making relations rebuildable would mean a second SSOT, which is the thing this
refactor exists to remove.

### 4.5 T39 invalidates the TTL cache by event; the LRU is accept-and-document — **DECIDED**
*Replaces `D-T39-NO-COVERAGE-DIGEST-SOURCE`.* There is no coverage digest and building one is
not worth it: `project_graph_stats` is a full scan and a write-path counter is a schema change
for a cache. ~~**The event-driven invalidation shipped in B9 is the answer for both caches** — proven
in-repo, cheaper than a digest, and it makes the LRU's "never cleared" comment false rather
than tolerated.~~ **The event-driven invalidation shipped in B9 is the answer for the TTL
automaton cache.** The TTL stays as the backstop for missed events.

⚠️ **CORRECTED 2026-08-21.** The struck clause above claimed both caches. Measured: `invalidate_anchor_cache` is called from `events/handlers.py:1060`
and `:1464` and reaches **only** `context/anchors.py`. The per-process LRU in
`jobs/glossary_anchor_cache.py` still reads *"per-process, never cleared"* at line 8 and
*"Production code never calls clear (M5 spec)"* at line 104, with **no caller anywhere**.
The comment was never made false.

The digest decision is unaffected — no digest is worth building. The **LRU** is closed by a
different argument than the one given above: it is keyed by `(book_id, chapter_index)`,
bounded to 1000 entries with LRU eviction, and M5 scoped its staleness to *"read-only within
an extraction run"*. That is **accept-and-document**, not invalidate-by-event. The deferral's
claim that the LRU *"has no such bound"* was wrong too — eviction is one.

---

## 5 · Process

### 5.1 T43's shadow keeps its id mapping — **DECIDED**
*Replaces `D-T43-ID-KEYED-OPS-NEED-A-MAPPING`.* Implemented and measured 9 of 9 operations
comparing. The mapping is the design, not a workaround.

### 5.2 T38's mechanism is the gate, and the gate is not vacuous — **DECIDED**
*Replaces `D-T38-MECHANISM-IS-VACUOUS`, `D-T38-KAL-SCOPE-UNDECIDED`.* The reader gate went
**10 call sites → 3** with its baseline shrinking per consumer and a `--selftest` proving it can
red. Its scope is settled: **reads through the KAL, writes are not T38's**, and the three
survivors are two eval scripts plus one DELETE the baseline already labels as out of scope.

### 5.3 CI must build every service image — **DECIDED, and it is a build**
*Replaces `D-NO-CI-BUILDS-ANY-SERVICE-IMAGE`.* No workflow builds any service image, which is
how T30 shipped an unbuildable one — a Go `replace` with no matching `COPY`, invisible until a
local `docker compose build`. `scripts/dockerfile-replace-copy-gate.py` catches that specific
class; it does not prove the images build. **The decision: one CI job that builds every service
image on push.** Until it exists, `ship-green` means "the tests passed", not "the thing runs".

---

## 6 · Sequencing decisions for the rows that were only waiting their turn

Several tasks carried no deferral because nothing was wrong with them — they were simply later
in a chain. Under the old register that read as "untracked"; here it is a decision with a
stated reason.

### 6.1 Phase 5's model order is `T35 → T36 → T37 → T32/T33 → QC-6` — **DECIDED**
Identity first because it re-keys 48 Cypher sites and everything downstream inherits the id;
roles next because the acceptance case turns on them; the producer after the shape it writes;
the two axis tasks after the identity they hang on; QC-6 last because it is the live proof of
all of it.

### 6.1b `glossary_entities.alive` SURVIVES — **DECIDED (T32b, 2026-08-14)**

T32's row required the column's disposition stated explicitly: *"drop the column **or document
why it survives**"*. It survives, and the reason is that the two signals were never the same
truth.

* **`alive` answers "does the AUTHOR want this hidden?"** — an editable toggle on a curated
  entity, the explicit-hide control.
* **`life_status` answers "is this character dead in the STORY at position P?"** — extracted,
  positioned, and half-open on the story axis.

They are orthogonal. A living character an author has retired from the codex is `alive=false`
with no `gone` fact; a character killed in chapter 20 is `alive=true` with one. The design's
*"two sources of truth"* diagnosis was right about the SYMPTOM — seven sites filtering on a
flag nobody sets — and wrong about the cause: the flag is not a broken liveness signal, it is
a different signal that had no data because the feature is unused, not because it is wrong.

**So the reader migration was never "seven sites", it was one.** T32b measured all seven: two
are the WRITES that set the column, one is a SORT key with no position to rank at, one is a
caller-supplied query PARAM, one is a bulk ENUMERATION that must not be story-windowed (an
indexing pass that skipped dead characters would be a data loss dressed as a spoiler fix), and
one is the schema. The single as-of READ is migrated (T32a), by CONJUNCTION —
`alive = true AND NOT gone-at-P` — so both questions are asked and neither is answered by the
other.

⚠️ **What would change this decision:** evidence that authors *want* story-death to hide an
entity from the editor view as well. That is a product observation, not a refactor finding, and
`alive` is where it would land. `scripts/alive-column-deprecation-gate.py` keeps the census with
`MIGRATABLE_FLOOR = 6` asserted, so the column cannot quietly grow a NEW reader without a
decision.

### 6.2 Phase 7's engine order is `T42b → T42c → T42 → T42d → T43 → T41` — **DECIDED**
Image, then bootstrap, then the adapter, then the gate that guards it, then the shadow that
measures it, then the swap. **T43's floor may re-block a cutover after new port operations
land, and that is the floor working** — a new operation starts at zero observations.

### 6.3b T46's FOLD half is scoped OUT, with the measurement — **DECIDED (T46g, 2026-08-21)**

T46's row names four capabilities to move Go → Python. Three are settled: `maintain_chain`'s
pin-aware supersession landed (T46f, parity asymmetries **1 → 0**), the content-addressed
natural key is present on the KG side, and the half-open interval invariant is present and
tested. The fourth — **the `anchor+delta` fold with `folds_since_reground`** — was measured
before building (rule 8) and the measurement killed the batch:

```
PG   canonical_fold_state + fold_handler.go (296 lines) READS AND WRITES the counters —
     working machinery: a debounced batch fold with a deterministic re-ground trigger.
KG   entity_canonical_snapshots: schema ✓  repository ✓  unit + integration tests ✓
                                 PRODUCER ✗  READER ✗  0 rows
     the ONLY importers of the repo are the two test files that test it.
```

🎯 **Porting the counters would be bookkeeping for a consumer that does not exist.** The
re-ground trigger counts folds; the KG performs none. The result would read as parity on the
gate while nothing ran — the failure shape this plan has hit repeatedly, and the one T46's own
*"move it WORKING"* instruction exists to prevent.

⚠️ **And it is the wrong shape regardless.** The two sides solve staleness differently, both
deliberately: Postgres uses counters (`folds_since_reground` / `invalidations_since_reground`)
because its fold is **batch + debounced** and needs a deterministic re-ground trigger; the KG
uses `fact_coverage_at` + `fold_algo_version` — a coverage-keyed **lazy rebuild-on-read** that
is self-healing by construction (B3: a back-filled fact bumps the coverage key and every
snapshot at or after that ordinal goes stale). A counter-driven trigger on a rebuild-on-read
cache has nothing to trigger. This is two designs, not a gap — and the cross-pollination
already runs both ways: Postgres's own `fold_attempts`/`fold_failed_at` comment says it
**mirrors the KG's** `RETRY_BUDGET=3`.

📐 **So the fold half belongs to F3/§12.1 — wiring the KG fold — not to T46's bitemporal**
**port.** T46 owns what `bitemporal-parity-gate` tracks, and that is now at zero asymmetries.

🔔 **The decision carries a tripwire, not a promise.**
[`test_canonical_fold_reachability.py`](../../services/knowledge-service/tests/unit/test_canonical_fold_reachability.py)
fails the moment production code imports the snapshot repo: the fold would then have a
consumer, this measurement would be stale, and the scoping must be re-decided deliberately
instead of by whoever notices first. It carries two controls of its own — the subject still
exists, and the import matcher can actually match — because an emptiness assertion passes just
as happily when its subject was renamed away.

### 6.3 Phase 8 is `T44 → T45 → T46`, after identity — **DECIDED · AMENDED (T46a, 2026-08-14)**
`T46` merges the stores and cannot be done before the id is opaque (§4.1). `T45`'s
scope-dependent valid-time axis (`story_ordinal` | `wall_clock`) is the axis distinction §1.1
relies on; `T44` rewrites the substrate rows those two settle.

**Three amendments from building T44/T45 and measuring T46:**

1. ⚠️ **"Port the machinery Go → Python" is a category error.** Neither implementation is in a
   general-purpose language: Postgres has a stored procedure (`maintain_chain(p_entity, p_attr)`,
   SQL inside a Go migration string) and the KG has Cypher in a Python constant. Each lives with
   the store it maintains, which is where SCOPE-1/SCOPE-2 require it. **The task is choosing the
   merged store's SUBSTRATE and moving both onto it**, not translating a language.

2. 🔴 **The KG is the weaker side, on the capability the row names.** Postgres `maintain_chain`
   is **pin-aware** (`valid_to_pinned = false` — never recompute an author's explicit close); the
   KG has no pin concept at all. Both agree on the strictly-greater bound and on skipping
   invalidated rows. `scripts/bitemporal-parity-gate.py` records this and fails when either side
   moves, **including when they converge** — convergence is the event T46 is waiting for and it
   must not arrive unannounced.

3. ⛔ **The merge waits on `recanon_honorifics --apply`, not on more design.** Identity is
   structurally opaque, but T35e measured **1826 live nodes with a stale `canonical_name`** that
   fork on re-extraction. Merging while 37 % of the graph forks would carry broken identity into
   the destination — which is what §4.1's precondition means in practice.

🔴 **The precondition is a LIVE DEFECT, not sequencing (2026-08-21, T46b).** §6.3 gates the merge
on `recanon_honorifics --apply` because a stale `canonical_name` forks the node on re-extraction.
Measured and then **run**: 1826 of 4866 live entities carry a stale canonical form, 1819 of them
with nothing sitting at the recomputed form — the same population `recanon`'s own `rekeyed=1819`
reports, arrived at independently. Driving the real `persist-pass2` path against a seeded row of
that shape on lw-iso produces **two nodes for one character**.

So any re-extraction of an affected chapter forks it *today*, with no merge involved. It has not
happened yet — the live graph groups 4872 nodes into 4872 `(user, project, canonical_name, kind)`
groups, largest 1 — so the defect is **armed and not fired**, and it fires the moment extraction
re-runs on those books. The repair is `recanon_honorifics --apply`, rehearsed end-to-end in T35g
against a faithful clone (1819 re-keyed / 1 merged / 6 refused / 0 anchors lost, `actions=0` on a
second pass). What is missing is the write, not the code.

✅ **THE WRITE IS DONE (2026-08-21, T46d).** The PO granted it and it ran against the real dev
graph: `rekeyed=1819, merged=1, conflicted=6, actions=1820`, and a second dry-run reports
`rekeyed=0, merged=0, actions=0` with `clean` 3040 -> 4859. Entities 4872 -> 4871, the one
merge. Checked against a 4.27 MB pre-apply APOC snapshot rather than trusted: `ABOUT`
248 -> 248, `RELATES_TO` 1143 -> 1143, `EVIDENCED_BY` 1275 -> 1274 — and that single edge is a
parallel-edge collapse, not a loss (the merged node's only edge pointed at an evidence node its
survivor already held; 0 evidence nodes lost all links). **The armed-and-not-fired fork defect
is therefore disarmed, and re-extraction of an affected chapter is now safe** — which is what
§4.1's precondition was protecting. The 6 refusals are unchanged before and after; they are the
planner declining to guess, not residue.


### 6.3c T46's remaining scope, re-measured — the ENGINE is decided; the TOPOLOGY is the question — **DECIDED · one PO input named (T46h, 2026-08-23)**

🔴 **The RESUME line said T46 was "X1's engine choice, the one PO decision left". It is not, and
that sentence would have sent the next session chasing a decision made the day before.** §8.1
(2026-08-22): *"The engine choice is **AGE**, made here."* X1's contest was scoped as "build both
candidates and let T43 choose"; T43 signed off on 9-of-9 agreement and named no winner, and §8.1
closed that gap explicitly. **Nothing about the engine is owed.** This is the `T17` failure shape
§1.3 records — a pointer outliving the thing it points at — caught after one session rather than
ten.

**Where T46's four named capabilities actually stand:**

```
maintain_chain, pin-aware supersession   ✅ landed T46f — bitemporal-parity 1 -> 0 asymmetries
content-addressed natural key            ✅ present on the KG side
half-open interval invariant             ✅ present and tested
anchor+delta fold + folds_since_reground ⛔ SCOPED OUT with the measurement (§6.3b)
the recanon precondition                 ✅ APPLIED against the real dev graph (T46d)
```

**So the machinery half of the row is complete.** What remains is the second clause of §6.3
amendment 1 — *"choosing the merged store's SUBSTRATE **and moving both onto it**"* — and with
the engine settled the open part is TOPOLOGY. Measured on the running stack:

```
GLOSSARY_DB_URL        postgres:5432/loreweave_glossary
KNOWLEDGE_DB_URL       postgres:5432/loreweave_knowledge
KNOWLEDGE_AGE_DB_URL   knowledge-pg:5432/loreweave_knowledge_vectors     <- a DIFFERENT host
```

⚖️ **Decided here: "merge the stores" does NOT mean one database.** Each service owns its own —
`knowledge-access-gate` exists to enforce exactly that, and moving the KG into
`loreweave_glossary` would put one service's tables under another's owner. The merge §6.3 asks
for is of the two BITEMPORAL IMPLEMENTATIONS onto one substrate kind, and AGE-on-Postgres is
that substrate: both halves are now Postgres, both speak the same bitemporal rules, and T46f
closed the capability gap that made the KG the weaker side.

✅ **ANSWERED (PO, 2026-08-23): the AGE graph STAYS on `knowledge-pg`.** The question was
whether it moves onto the shared `postgres` — an operational call about extensions, resource
profile and backup blast radius, not derivable from this repo.

⚠️ **It came with a constraint that decided most of it.** §3.3c's join reads `anchor_score` from
the graph for the ids a vector search returned, and both DSNs resolve to ONE database
(`knowledge-pg:5432/loreweave_knowledge_vectors`). Moving AGE alone would break the join; the
vectors would have had to move with it. Staying preserves the co-location, isolates the
AGE/pgvector extension surface, and needs no migration.

🔴 **So the live risk is now a SPLIT, and it fails silently** — a resolver pointed at a database
with no graph (or an empty one) answers nothing, `glossary.py` maps that to `0.0`, and two-layer
entity ranking degrades to raw cosine order with no error. `_warn_if_graph_and_vectors_are_split()`
checks it at startup and names that consequence rather than the mismatch (T46i).

**Not owed, explicitly:** the engine (§8.1, AGE), the fold (§6.3b, out), the precondition
(T46d, applied), the parity capability (T46f, closed).


### 6.4 Phase 9 closes the plan: `T47 → T48 → T49` — **DECIDED**
Docs (mandatory under the plan's own `Docs: yes`), then `/aif-verify`, then handoff and
archive. **This is how the plan ends**, and it may not begin until every other row is `[x]` or
cites a decision here.

### 6.5 T51 (frontend) follows T38 and T32 — **DECIDED**
The FE renders against the cast read and the spoiler window; migrating it before those settle
would ship surfaces reading a contract that is still moving. T38 is complete (§5.2); T32 is
sequenced in §6.1.

### 6.6 T40 (`entity_facts` partitioning) follows T39 — **DECIDED · RE-SCOPED TO A TRIGGER (T40a, 2026-08-14)**
~~Partitioning is cheap and safe once the caches that read across books are correct by
construction (§4.5); doing it first would move the data under a cache that is still guessing.~~

**Safe, yes. Cheap, no — and it is not needed yet.** Measured on the live glossary DB:
48 610 rows / 35 MB / 12 books, and the production as-of read is entity-scoped and costs
**8 buffers** on `uq_entity_facts_natural`. Partition pruning reaches one book's partition,
which `idx_entity_facts_book` already does, and the hot path needs neither.

⚠️ **The price:** Postgres requires a partitioned table's UNIQUE keys to CONTAIN the partition
key, and `uq_entity_facts_natural` omits `book_id`. Partitioning therefore re-cuts the
content-addressed natural key the fact writer's idempotency rests on — a change to what *"the
same fact"* means, not a storage tweak.

**So T40 closes on a MECHANISM rather than on a build**: `scripts/entity-facts-growth-gate.py`
fails when the table crosses 500 000 rows unpartitioned (`--live`), and fails the day `book_id`
joins the natural key (static, pre-commit) — because that is the one change that would make
partitioning cheap, and it is otherwise invisible.

## 7 · PO decisions — 2026-08-21

Three calls made in one sitting, after an audit showed the run had **stopped on decisions that
were already made**: §2.2 and §2.3 had settled two of them on 2026-08-13 and the plan headings
never moved. `scripts/superseded-deferral-gate.py` and
`docs/specs/2026-08-21-deferral-supersession-ledger.md` exist so that cannot recur.

### 7.1 T25 ③ — the Neo4j vector indexes are DROPPED on the dev graph — **GRANTED**
The cutover to `halfvec` HNSW in Postgres made them dead weight. The grant is deliberate about
what it authorises: **an index drop, not a data drop**. Neo4j vector indexes are derived from
node properties, so the embeddings survive and the index is recreatable by re-indexing if the
cutover is ever reverted. Rule 6 otherwise bars this write; this section is the exception that
names it.

⚠️ **THE GRANT CANNOT BE SPENT AS WRITTEN — measured the same day it was given, and the reason
matters more than the grant.** A graph-only `DROP INDEX` is **cosmetic**:
`app/db/neo4j_schema.cypher` declares every one of these indexes with
`CREATE VECTOR INDEX … IF NOT EXISTS`, and `app/main.py:167` runs that schema on lifespan
startup. **Proven on lw-iso rather than read from the source**: dropped
`entity_embeddings_384`, restarted `lw-iso-knowledge-service-1`, and the index was `ONLINE`
again within four seconds.

So **T25 ③ is a CODE change, not a database operation** — retiring an index means deleting its
DDL. And that cannot land while production still queries it. Measured by imported symbol,
because the module-level `neo4j_repos` count (54) cannot separate a vector reader from any
other caller, which is how these two stayed invisible:

| module | status |
|---|---|
| `adapters/neo4j_vector_store.py` | sanctioned — it **is** the port's Neo4j implementation |
| `benchmark/flat_knn_rawsearch.py` | **floor** — benchmarks the Neo4j backend on purpose |
| `benchmark/vector_backend_bench.py` | **floor** — comparing the two backends is the point |
| `routers/public/entities.py:584` | 🔴 **LIVE** — public semantic entity search |
| `tools/executor.py:494` | 🔴 **LIVE** — the memory-search tool's semantic leg |

**§3.1 named three readers to migrate and missed both of these.** Its list was
`context/selectors/passages.py`, `routers/public/drawers.py`, `search/retriever.py`.

And the data is not ready either. Dev secondary vs primary, counted with `count(*)` and not
`n_live_tup`:

```
DEV   entity   Neo4j    25   pg entity_vectors_1024    25   ✅ parity
DEV   passage  Neo4j  1051   pg passage_vectors_1024    0   ✗ never landed (skip-gate)
ISO   passage  Neo4j    12   pg passage_vectors_1024   12   ✅ parity (T25g)
```

The passage scope **works** — T25g proved it on lw-iso with exact `count(*)` parity. What has
never happened is a passage write on **dev**, and the reason is correct behaviour: the
content-hash skip-gate refuses to re-embed unchanged text, so no backfill can produce one
without new chapter content.

Migrating `tools/executor.py` onto the port **today** would turn a 1051-passage memory search
into a 0-passage one, silently — the search would still return `200` with an empty semantic
leg. That is worse than not migrating.

**Decided, so this is unfinished rather than undecided:** the grant stands and is **unspent**.
Nothing was dropped on the dev graph, because there is no subset whose drop both survives a
restart and removes no live capability — the eight zero-row indexes are not dead, they are
provisioned capacity for dimensions a project can still select. The precondition is now
tracked by a number rather than by prose: `scripts/port-adoption-gate.py` pins the vector
bypass at **4/4 with a floor of 2**, names the two LIVE readers in its own output, and reds
when a fifth appears or when the count falls without the ceiling moving with it.

### 7.2 The role-attribution judge stays LOCAL, and its precision is documented — **DECIDED**
*Closes `D-QC5-ROLE-JUDGE-PRECISION`, which §2.3 cited loosely — §2.3 is about verdict SHAPE, a
different question.* No paid judge is bought. The measured precision of the local judge is
recorded as **the accepted ceiling**, not as a defect awaiting spend. What makes that
affordable is that `judge_role_attribution` is **off by default**, so the false-positive rate
cannot reach an author; turning it on is a separate decision that would have to re-open this.

### 7.3 QC-5 bounds its nondeterminism at FIVE runs, temperature 0, seeded — **DECIDED**
*Closes the second half of `D-QC5-ATTRIBUTION-CHANNEL-UNWIRED`; the first half was
§2.2, done 2026-08-13.* QC-5's verdicts moved between runs on unchanged inputs (ch12 scored
`1/SEVERE` and `2/warn`), and a single run cannot tell a verdict from a flake. The bound is
**five runs at temperature 0, seeded where the provider supports it**, and the report is the
**distribution**, never one number. Five rather than three because three was already the
shape that produced the disagreement above.

⚠️ Seeding is best-effort by provider. A run that cannot seed still reports five samples and
says so — an unseeded five-run spread is weaker evidence than a seeded one, and conflating
them would be the same green-by-construction move this plan keeps finding.


## 8 · PO decisions — 2026-08-22, after the run-state audit

An audit of the whole run against its ORIGINAL goal — *"make the KAL the SSOT and stop the
scattered glossary/KG access"* — measured three things the plan had stopped tracking. All three
become rows rather than notes, because a gap recorded in prose is how the last three got lost.

### 8.1 The goal is **AGE as the DEFAULT**, not "retire Neo4j" — **DECIDED**

The PO corrected the framing and the code agrees. `graph_store_provider` is already
env-switchable (`KNOWLEDGE_GRAPH_BACKEND=neo4j|age`), so "default" is a one-line change once
the AGE branch is wired. **Neo4j must remain a supported adapter**: T43's shadow harness
compares Neo4j↔AGE and the two backend benchmarks are the only things that can compare engines.
Retiring Neo4j deletes the instrument that proves AGE correct. `port-adoption-gate`'s floor of
**2** was set on 2026-08-21 for exactly this reason.

⚠️ **This also settles a choice QC-7 left unrecorded.** X1 scoped T42 as *"build BOTH candidates
and let T43 choose"*. T42 built AGE and Kuzu; QC-7 signed off `cutover_permitted: True` on 9-of-9
agreement — **and named no winner**. Searched: no X1 decision record, no winner in any spec. The
engine choice is **AGE**, made here, 2026-08-22.

**Kuzu stays a supported adapter** (PO): it already passes the conformance suite, costs nothing
to keep, and a THIRD implementation is what keeps the port honest — two adapters can agree by
sharing a bug, which is T43's own stated risk.

### 8.2 The default flips NOW, without a production shadow — **DECIDED**

QC-7 refused a cutover *"while any port operation has zero shadow observations"*. The PO: **there
is no production**, so there is no live traffic to shadow and waiting for it is waiting for
something that cannot arrive. The bar is met by the evidence that exists rather than waived:
T43 delivered a property-based differential suite (**five seeds × twenty operations**) plus the
shadow comparison, and QC-7 recorded **9 of 9 operations agreeing, zero divergences**. Those ARE
the observations; what they are not is production traffic.

⚠️ Stated so it cannot be misread later: the dev graph is acknowledged residue from ad-hoc runs
(§4.3), so a flip there proves the wiring, not a migration under load. When production exists,
the shadow bar applies again to anything not covered by the differential suite.

### 8.3 INV-KAL's HTTP half must be DERIVED, not hand-listed — **DECIDED**

Measured 2026-08-22: `knowledge-http-surface-gate` guards **7 endpoints**; the two owning
services expose **98** distinct `/internal/*` route literals. composition-service alone reads
knowledge through **13** direct internal paths — `/internal/context/build`,
`/internal/context/glossary-semantic`, `/internal/projects/{id}/fact-for-check` — none of them
guarded. `fact-for-check` was observed firing in live logs while the gate reported PASS.

✅ **The TABLE half is genuinely enforced and is not the gap.** The Neo4j driver is imported by
`knowledge-service` only (9 files); the glossary EAV is referenced outside its owner only by an
allowlisted admin one-shot and test files. No runtime service code reaches either substrate
directly.

**Decided:** the guarded set is derived from the KAL's own federated-read manifest, so a new
federated read is guarded the day it is federated. A hand-list is a scope list, and rule 5 says
a scope list moves with the code — this one did not move for 98 routes.

### 8.4 The migration gets an ANTI-ROT audit set, grounded in defects this run actually hit — **DECIDED**

The PO asked what to audit so the migration does not rot. Every item below is a defect **found
in this plan**, generalised into a check — not a hypothetical:

| rot pattern | where it actually happened | the check |
|---|---|---|
| **Built but unreachable** | T42/T43 closed green with 30 conformance tests passing, and `KNOWLEDGE_GRAPH_BACKEND=age` raises `NotImplementedError`. Permission to cut over was granted and no row ever performed it. | every adapter with a conformance suite must be **selectable from its provider** |
| **Scope list drifts from reality** | the HTTP gate guarded 7 of 98 routes and nothing said so | derive guarded sets from a manifest (§8.3) |
| **A gate goes silent on success** | `port-adoption-gate` matched no branch at its floor: printed nothing, returned 0 | every gate prints its number unconditionally |
| **A criterion that cannot fail** | QC-5 clause 1a scored 5/5 on a draft with nothing planted in it | an acceptance criterion needs a **control arm** |
| **One concept, two readers** | the critic resolved from run params in one seam and settings in another; knowledge read via KAL in one place and direct HTTP in another | single-reader checks on resolution rules |
| **Doubles shaped like deleted code** | five tests stubbed `find_passages_by_vector` and kept passing after the call site moved to the port | when a call site moves to a port, its doubles move with it |
| **Measured on a config the product does not offer** | QC-5 passed with a critic supplied in the request body; the studio path resolved a different one | acceptance runs on the **shipped path** |
| **Documents disagreeing with each other** | 29 supersession claims, 16 unstruck; one deferral in two opposite states; §4.3's title outliving its body | `superseded-deferral-gate` + the supersession ledger |

### 8.5 How the flip lands — TIER, grant, and what happens to the old graph — **DECIDED (PO 2026-08-22)**

**TIER (rule 4): code default + an env pin on dev.** `_DEFAULT_BACKEND = "age"` in
`graph_store_provider`, so a deployment that sets nothing gets AGE; and
`KNOWLEDGE_GRAPH_BACKEND=age` pinned in `infra/.env`, so the shared stack STATES its backend
rather than inheriting it. Two places, deliberately: the code default is the claim, the pin is
the operational fact.

⚠️ **The blast radius is real and was measured, not guessed.** Flipping the code default turned
**41 unit tests into 500s** — their doubles are Neo4j-session shaped. `tests/conftest.py` now
`setdefault`s `KNOWLEDGE_GRAPH_BACKEND=neo4j`, so the suite says which backend it tests. That
pin would otherwise make the real default unobservable, so `test_graph_backend_default.py`
reads the provider CONSTANT rather than the environment.

**GRANT: bootstrapping AGE on dev knowledge-pg is authorised** — `CREATE EXTENSION age` and
`create_graph`. Rule 6 otherwise bars it; this is the exception, and it is narrow: schema
objects on the knowledge Postgres, not data writes to Neo4j or the glossary.

**The dev AGE graph starts EMPTY, by decision.** Neo4j keeps its 4 872 entities; nothing is
migrated. Rebuild-on-demand re-projects entities from the glossary SSOT (~8 ms/entity).
🔴 **Stated because it is a real loss, not a formality:** the rebuild restores IDENTITY only —
extraction-derived relations are not rebuildable (`D-T41`, accepted), so dev's 1 144
`RELATES_TO` and its 4 causal edges do not come back without re-extraction. Acceptable here
*because there is no production* and the dev graph is acknowledged residue (§4.3); it would not
be acceptable later.

**The shared graph `g_shared`, not graph-per-project.** Neo4j holds every project in one
database scoped by `user_id`/`project_id` properties, so `graph_name_for(None)` reproduces the
CURRENT isolation model exactly. Per-project graphs remain available and are what T43's harness
uses. Adopting them at the same moment as the engine swap would mean a later divergence could
not be attributed to either change.


### 8.6 Which of the 9 direct knowledge reads get federated — **DECIDED (T55/d, 2026-08-22)**

§8.3 said *"migrate or explicitly exempt"* and left the per-route call open. `T55/b` built the
ledger and `T55/c` established that the call is **not derivable from imports** — two probes
over the same paths disagreed, 3 of 10 by handler body (misses delegation) and 9 of 10 by
import closure (attributes any graph use anywhere to every route in the module). This section
takes the decision rather than leaving it owed, because a task may be unfinished; it may not be
undecided.

**The criterion is the RESPONSE CONTRACT, not what the handler touches.** INV-KAL governs what
crosses the service boundary, so the question is what a consumer receives — and the answer is
derivable from the OpenAPI schema, which is the boundary written down. Both earlier probes
asked about the handler's internals, which is why both failed.

**The discriminator is not invented here — it is read off the 10 reads the KAL ALREADY
federates:** `entities/search`, `entities/by-ids`, `entities/{}/facts`, `entities/{}/timeline`,
`entities/{}/canonical-snapshot`, `entities/{}/attr-values`, `kg/neighborhood`, `retrieve`,
`state`, `canonical-translation`. Every one returns a **projection of knowledge state** —
entities, relations, events, facts. That is the class, and it already includes pure identity
reads, so "carries valid-time" would be too narrow a test.

#### FEDERATE — 4 routes, each returning knowledge state

| route | response contract | why |
|---|---|---|
| `/internal/projects/{}/fact-for-check` | `FactForCheck{at_order, entities[…status], relations[…valid_from_ordinal, valid_to_ordinal], events[…event_order]}` | The textbook case. **Ordinals are on the wire.** This is the bi-temporal read INV-KAL exists for, and it was observed firing in live logs while the gate reported PASS. |
| `/internal/knowledge/wiki-neighborhood` | `WikiNeighborhoodResponse{name, kind, source_types, relations, total_relations, relations_truncated}` | An entity plus its capped relations — the same shape as the already-federated `kg/neighborhood`. Two routes, one domain question. |
| `/internal/knowledge/timeline` | `TimelineResponse{found, events, count, total}` | Event state, and `entities/{}/timeline` is already federated. Exempting this one would federate an entity's timeline while leaving the project's outside. |
| `/internal/context/glossary-semantic` | `GlossarySemanticResponse{items: GlossaryEntityForContext[entity_id, cached_name, cached_aliases, kind_code, tier, attributes]}` | An entity read reached by semantic search. `entities/search` — the same question by a different retrieval — is already federated, so this is consistency, not expansion. |

#### EXEMPT — 5 routes, none returning knowledge state

| route | response contract | why it is not an INV-KAL read |
|---|---|---|
| `/internal/context/build` | `ContextBuildResponse{mode, context, token_count, stable_context, volatile_context, sections}` | 🎯 **The one worth arguing.** It reads knowledge heavily — that is why the import probe flagged it — but it returns a **rendered prompt with token accounting**, not a projection of state. Federating it would put prompt assembly behind a *read* gateway, and the spoiler window it must honour is applied inside the owning service where the ordinals still exist. A consumer cannot re-window a string. |
| `/internal/context/project-book/{}` | `ProjectBookResponse{book_id}` | One id. Project metadata. |
| `/internal/knowledge/projects/{}/extraction-status` | `{active, last_outcome}` | Operational status of a run. |
| `/internal/knowledge/jobs` | untyped `object` | A job listing. Operational. |
| `/internal/extraction/runs/{}/sample` | `RunSampleResponse{run_id, config_hash, items, source_text}` | Run-attributable extraction provenance for the learning service, keyed by `config_hash` — a record of what a RUN produced, not what the graph holds. |

**Consequence.** The gate's ledger carries the verdict per route, so the four owed federations
are named on every run and the five exemptions carry their reason at the point a reader meets
them. `context/build` is the one to revisit if it ever starts returning `sections` as
structured entity data rather than rendered text — that would move it across the line, and the
ledger entry says so.

⚠️ **What this does NOT decide.** Building the four KAL routes and repointing their consumers
is the work; this section fixes the target so it cannot drift, and nothing here authorises a
change to a consumer service outside this plan's scope.



### 8.7 The remaining three federations need a GRANT primitive, not a route — **DECIDED (T55/f, 2026-08-22)**

§8.6 decided four routes belong behind the KAL. `timeline` shipped (T55/e) because its consumer
already holds a `book_id`. The other three do not, and measuring why turned up something
sharper than a missing route.

**`KalAuthGuard` is book-scoped by construction, not by convention.** Its user-mode arm reads
`req.params?.bookId` and throws `'book scope required'` when it is absent, then gates on
`hasBookAccess(bookId, userId)`:

```
1. SERVICE mode   a valid X-Internal-Token  -> return true          (no book check)
2. USER mode      Bearer JWT -> req.params.bookId REQUIRED
                             -> hasBookAccess(bookId, userId) or 403
```

Measured on the live iso stack against the route shipped in T55/e:

```
USER mode, owner     -> 403 "no grant on this book"
USER mode, stranger  -> 403 "no grant on this book"      (no grants seeded; the arm fires)
SERVICE mode         -> 200                              (internal token, trusted caller)
```

**So a `@Controller('v1/kal/projects/:projectId')` would have NO user-mode authorisation path
at all.** Every JWT request to it would 401 on `'book scope required'`, and the only way to
reach it would be with an internal token — which bypasses the guard entirely. A federated read
surface whose only usable door is the one that skips authorisation is worse than the direct
call it replaces, because it *looks* governed.

**Decided: the remaining three are blocked on `hasProjectAccess(projectId, userId)`, a new
authorisation primitive, and not on route-writing.** Two alternatives were considered and
rejected:

* **Resolve project → book inside the gateway, then reuse `hasBookAccess`.** This is the cheap
  one, and it is domain logic in the gateway — `gateway-domain-logic-gate` exists in this repo
  precisely to keep that out, and the mapping (`knowledge_projects.book_id`) belongs to the
  owning service. A project with no book, or two books, would be decided in the wrong place.
* **Make the consumers carry `book_id`.** composition-service holds a project id because its
  work is project-shaped; `wiki-neighborhood`'s caller holds only a `glossary_entity_id` and
  has neither. Pushing the resolution outward multiplies the lookup across 13 services.

**What this leaves.** Three routes stay `federate` in the ledger with `MAX_FEDERATE_OWED = 3`,
so they are named on every gate run and cannot quietly drop off. The next unit of work is the
grant primitive, and it is a knowledge-gateway/auth question rather than an INV-KAL one.

⚠️ **Not a deferral.** The shape is decided here; what is unfinished is building
`hasProjectAccess` and the controller that uses it. Nothing about the four-route verdict in
§8.6 changes.


## 9 · OWED — the dev vector cutover (T25 ③ step 3)

### 9.1 Deleting the passage vector DDL needs dev on `postgres` first — **PO DECISION OWED**

T25 ③'s remaining step is deleting `passage_embeddings_*` from `neo4j_schema.cypher`. Steps 1,
2 and 5 are done and proven (T25l, T25m, T25n). Step 3 is blocked on a decision that is not
mine to make, and it trips **two** of the run's five stop conditions at once.

**What is proven and what that leaves.**

| | |
|---|---|
| step 1 — the soak | ✅ T25l. `SOAKING`, 533 real writes, `secondary_failed = 0`, iso secondary `passage_vectors_1024` 12 → 545. |
| step 2 — the read cutover | ✅ T25m. `KNOWLEDGE_VECTOR_READ_PRIMARY=postgres` → passage served by `PgVectorStore`, entity still by `Neo4jVectorStore`, both returning real hits. The switch now has a compose surface; it had none before. |
| step 5 — the benchmarks | ✅ T25n. Both ensure `passage_embeddings_<dim>` themselves, same name and options. |
| step 3 — delete the DDL | ⛔ **this section.** |
| step 4 — entity/event DDL | stays, per §3.3, until `D-T25B-PG-ANCHOR-SCORE` has an answer. |

**Why step 3 cannot be taken unilaterally.** Deleting the DDL breaks any deployment still
reading `neo4j`, and dev is one: `knowledge_vector_read_primary` defaults to `neo4j` (T25k) and
dev's secondary holds **zero passage rows** against 1051 passages in the dev graph. Measured on
iso (T25n), a missing index does not degrade the search — `db.index.vector.queryNodes` raises
`ProcedureCallFailed`, so dev semantic search becomes a 500.

Cutting dev over therefore means populating dev's secondary first, and the only path that does
that is a passage ingest, which **MERGEs `:Passage` nodes into the dev graph**. That is a write
to a non-throwaway database, and the 2026-08-21 GRANTS authorise `docker compose up -d
knowledge-service`, `recanon_honorifics --apply`, QC-3's sign-off and QC-5's clause — not this.

So: *a PO decision is owed that GRANTS does not cover*, and *a write to a non-throwaway DB that
GRANTS does not authorise*. Recorded here rather than worked around, and the row stays `[~]`
with its steps individually evidenced rather than being marked blocked.

**The options, stated so they can be chosen between.**

1. **Grant the dev backfill, then flip dev.** `POST /internal/projects/{id}/backfill-passages`
   per project, which re-ingests published chapters from their pinned revisions. It is
   idempotent by content hash, so unchanged chapters skip the re-embed — but it does write
   `:Passage` nodes and it does spend embedding tokens. Then
   `KNOWLEDGE_VECTOR_READ_PRIMARY=postgres` on dev, and step 3 follows.
2. **Flip dev WITHOUT backfilling.** Cheapest and wrong in a specific way: passage search on dev
   silently returns nothing until something re-ingests, because the secondary is empty rather
   than broken. This is the failure shape this plan has caught four times; naming it here so it
   is refused deliberately rather than by accident.
3. **Delete the DDL and leave dev on `neo4j`.** Not viable — that is the 500 above.
4. **Leave step 3 open and take the rest of the queue.** T25 ③ stays the one unfinished part of
   a row whose other parts are evidenced. Nothing else in the plan depends on the DDL being
   gone; the AGE cutover depends on class (d), which is a different population (A14).

**What does NOT block on this.** The AGE default (T54) waits on T17 class (d) — **34** modules
needing port operations, derived and ratcheted by `port-adoption-gate` since A14. None of that
is downstream of the vector DDL.

### 9.1b The 2026-08-24 grant cannot be executed as written — **PO DECISION OWED (T25y, 2026-08-24)**

The PO granted the dev cutover: backfill → `READ_PRIMARY=postgres` → delete the passage DDL.
**Step 1 cannot populate the secondary**, measured on dev's own `/metrics`:

```
soak-armed-gate  ->  DISARMED — neither `knowledge_vector_dual_write_armed` nor the
                     `knowledge_vector_dual_write_total` family is exposed; this service
                     PREDATES the dual-write entirely.
dev Neo4j :Passage 1051 (all embedded)   dev passage_vectors_1024  0
```

A backfill against that container MERGEs `:Passage` and spends embedding tokens for **zero**
secondary rows, which turns step 2 into this section's option 2 — the silent-empty failure it
exists to refuse. Arming dual-write means recreating `infra-knowledge-service-1`, and the dev
stack **is** the sibling `infra` compose project, which the same grant withholds.

**The options, unchanged in kind from §9.1 but now with the blocker named:**

1. **Extend the grant to the container.** Recreate `infra-knowledge-service-1` from a current
   image (the old SOAK grant), confirm `soak-armed-gate` reads `ARMED_IDLE`/`SOAKING`, then
   backfill, flip, delete the DDL. This is the only path that reaches the granted end state.
2. **Withdraw the cutover.** T25 closes on ① ② ④ and steps 1/2/5 of ③, with step 3 recorded as
   deliberately declined — the position the PO took on 2026-08-24 about the data itself.
3. **Do the whole cutover on `lw-iso` instead** and leave dev untouched. Proves the sequence
   end-to-end (T25l/T25m already did on iso) but does not move the DECLARED deployment, so
   `graph-store-migrated-gate` keeps answering about dev.

**What does NOT block on this:** §9.1's closing sentence still holds — *"Nothing else in the
plan depends on the DDL being gone."*

## 10 · T17 class (d) — the shape of the remainder


### 9.2 T25 ④'s DDL deletion is decided by a COUPLING, not by scheduling — **DECIDED (T25t, 2026-08-23)**

§9.1 sent step 3 to the PO because deleting the passage DDL *"breaks any deployment still
reading `neo4j`"*. The obvious reading is that step 4 is the same kind of question and needs the
same kind of answer. **It is not, and the difference is something T25s created rather than
something that was always true.**

**T25s made the entity scope self-guarding:** entity reads move to Postgres only when an
`anchor_score` resolver exists, and the provider supplies one only when
`configured_backend() == "age"`. So a deployment on the Neo4j backend keeps its entity reads on
`Neo4jVectorStore` — which resolves `index_name = f"entity_embeddings_{dim}"`
(`entities.py:1712`) and calls `db.index.vector.queryNodes` on it.

**Measured on `lw-iso`, not reasoned about.** The same query, before and after dropping the
index the DDL creates:

```
with entity_embeddings_1024 present   ->  hits 5
after DROP INDEX entity_embeddings_1024
  -> 52U00: There is no such vector schema index: entity_embeddings_1024
     52N37: Execution of the procedure db.index.vector.queryNodes() failed
```

That is the identical `ProcedureCallFailed` shape §9.1 measured for passages, arrived at
independently.

🎯 **So the DDL is LOAD-BEARING for exactly the deployments the T25s gate keeps on Neo4j.**
Deleting it would break entity search precisely where the design deliberately sends entity
search. The two are one mechanism, and that removes the discretion:

```
backend = age    entity reads -> Postgres (anchor_score joined, §3.3c)   DDL unused
backend = neo4j  entity reads -> Neo4j    (the self-guarding fallback)   DDL REQUIRED
```

**Decided: the ENTITY vector DDL stays until no deployment can take the Neo4j entity
path**

⚠️ **AMENDED 2026-08-23 (T25u) — this said "entity/event", and the event half was wrong.** It
was never measured; it was listed beside the half that had been. Measured since: `(:Event).
embedding_1024` has **no producer and no reader in any language**, the live graphs hold 1186
events / 0 embeddings (dev) and 110 / 0 (iso), and `SHOW INDEXES` reports `event_embeddings_1024`
at **readCount 0, lastRead NULL** on both — against `entity_embeddings_1024` at **753 reads** on
dev, the control that makes the zero meaningful. An index over a property nothing writes protects
no read path, so its exit was never coupled to the backend flip. **`event_embeddings_1024` is
DELETED**; the sentence below is about the entity family only — that is, until the fallback is removed, which is only correct once every deployment is
on AGE. It is not a scheduling call and it is not owed to anyone: the condition is mechanical
and already written down in `read_scopes`.

⚠️ **This is NOT §9.1 being overruled.** §9.1's step 3 genuinely was a PO call: dev's Postgres
held **zero** passage rows against 1051 passages, so flipping emptied the search and someone
had to accept that cost. For entities the equivalent measurement is **25 rows against 25
embedded entities — exact parity** (T25s), so no such cost exists and no such acceptance is
needed. Different facts, different kind of answer.

📐 **What this leaves owed on T25, precisely:** nothing that a decision unblocks. The DDL's exit
is now a consequence of the backend flip rather than a step of its own, and the flip is §8.5's,
already decided. When the last deployment is on AGE the fallback becomes dead code and the DDL
goes with it — a removal, not a cutover.



### 9.3 Two port parameters can never be conformed — **DECIDED (T17 A24, 2026-08-23)**

`GraphStore.resolve_or_merge_entity` declares four parameters beyond the identity tuple.
Measured against the domain model:

```
Entity.version         PRESENT   -> a conformance rule can assert it
Entity.auto_created    PRESENT   -> a conformance rule can assert it
Entity.provenances     absent    -> the port ACCEPTS it and cannot REPORT it
Entity.created_job_id  absent    -> same
```

The port takes `provenance` and `job_id`, both stores write them (`e.provenances` accumulates a
deduped set; `e.created_job_id` is create-only), and **neither comes back through the port's
return type.** So no rule in the adapter-parameterised suite can ever check them — which is
exactly why the AGE adapter accepted and discarded both for as long as it did, and why the
in-memory double does the same today. The fake's own comment had already spotted it: *"`provenances`
is written by the Cypher but is NOT a field on the Entity model, so it never crosses this
boundary. Mirroring it here would be inventing state the real store's RETURN cannot produce."*

⚠️ **AMENDED 2026-08-23 (A28) — the census found FOUR, not two, and the fourth has a different
reason.** `add_evidence.quote` is unassertable because `EvidenceWriteResult` carries only
`created`/`evidence_count`/`mention_count`; `status_at_order.min_evidence` is unassertable
because it filters status TRANSITIONS and **the port has no status writer** — a rule cannot
create the precondition it filters on (`set_status` is a fake-only helper). All four are now
enforced by `port-adoption-gate`'s `port parameters N/94` ratchet, which fails on an
unexplained parameter AND on a stale explanation.

**Decided: they stay write-only side effects, verified PER ADAPTER against the store, not through
the port.** `A23` does this for AGE — it reads `provenances` and `created_job_id` back out of the
graph with a direct query after the write, in a throwaway graph.

⚖️ **The alternative was widening `Entity`, and it is refused for a reason, not skipped.** Adding
`provenances`/`created_job_id` to the domain model would put extraction bookkeeping on the object
every reader of the knowledge graph receives, to make two write-only fields testable. The model is
what crosses the service boundary; attribution metadata is not something a consumer of an entity
should have to ignore. **The asymmetry is real and is now written down instead of being
rediscovered** — a port that accepts what it cannot report will always hide a dropped parameter,
and the next person to add such a parameter should know that this is what they are choosing.
### 10.1 The port does NOT grow to 106 methods — **DECIDED (T61, 2026-08-22)**

**Measured before deciding** (rule 8), from the same classifier `port-adoption-gate` ratchets:

```
class (d)            34 modules
distinct operations  85          the port has 21   ->  106 if all are added
sessions in signature 83 of 85   they are repo functions, not domain calls
by repo module       entities 32 · facts 11 · hierarchy 8 · events 8 · relations 4 ·
                     provenance 4 · enrichment 4 · entity_status 3 · schema_usage 3 ·
                     coref 2 · graph_views 2 · fact_for_check 1 · temporal 1 ·
                     flywheel 1 · project_graph 1
```

**The option that was assumed, and why it is refused.** `D-AGE-DEFAULT-SPLITS-THE-GRAPH-UNTIL-
CLASS-D-MOVES` said *"take class (d) in T35-shaped batches: grow the port operation, migrate
its binders."* At 85 operations that is a **five-fold expansion** of `GraphStore`, each method
costing a Neo4j implementation, an AGE implementation, a fake, and a conformance rule — and it
would make the port a **mirror of `neo4j_repos` with a different import path**. The port's own
docstring refuses exactly this: *"A port grows by demand, not by inventory… every method here
has to be implemented twice plus faked."* A 106-method interface is not a boundary; it is the
concrete layer with an `abstractmethod` decorator.

**DECIDED — substitutability is achieved at TWO levels, not one.**

1. **`GraphStore` stays the DOMAIN boundary** and keeps growing only by demand. It is what T43
   shadow-compares (21 operations, 239/239 agreed, `cutover_permitted: True` — T60), and what
   cross-cutting consumers use. It does **not** absorb the long tail.
2. **The repo layer becomes ENGINE-AGNOSTIC** rather than being replaced. `neo4j_repos` is
   Neo4j-shaped in its *name* and in its *dialect*, not in its *semantics* — its functions are
   already domain-shaped (`find_entities_by_name`, `status_at_order`), which the sealed plan
   observed on day one. What binds it to Neo4j is the Cypher dialect and the session type.

**Why this is now the cheaper and better-evidenced path.** The 2026-08-11 construct probe
priced the dialect gap: ~33 anchoring rewrites onto `coalesce` + pre-`MATCH`, 157
`datetime()` → `timestamp()` renames, 14 `CALL {}` → `LATERAL`/CTE. T57–T60 then demonstrated
the method on the three hardest cases in the codebase — `merge_event`, `update_event_fields`
and `merge_fact` with `maintain_chain` — all three of which had been declared *"no APOC-free
AGE equivalent"* and all three of which are now implemented and agreeing with Neo4j on real
traffic. **A bounded, measured translation beats 85 unmeasured port methods.**

**What this does NOT license.**

* It does not retire `GraphStore`, weaken `INV-KAL`, or permit a consumer to reach a graph
  driver directly. `knowledge-access-gate` and `graph-port-gate` stand unchanged.
* It does not make `port-adoption-gate`'s ceiling meaningless: the ceiling still counts modules
  bound to a **Neo4j-named** package, and that count must still fall as the layer is renamed
  and its dialect neutralised.
* It does not decide the ENGINE. X1 still chooses by measurement, and Kuzu's embedded
  single-handle limit remains *"the single biggest input to the engine choice"*.

**The measurable form of the decision.** Class (d) reaches zero either by a module migrating to
`GraphStore` (as A4/A9/A10 did) **or** by the repo layer it binds becoming engine-agnostic.
`port-adoption-gate` already prints class (d) every run; the second path needs its own ratchet,
and building that ratchet is the next unit rather than another decision.

⚠️ **DISCHARGED 2026-08-24 (T17 A29/A30) — both named binders are gone, and both are now
MEASURED.** This section named exactly two things binding the layer to Neo4j — *"the Cypher
dialect and the session type"* — and added that the ceiling *"counts modules bound to a
Neo4j-named package, and that count must still fall as the layer is renamed"*. State now:

```
Cypher dialect          0/0   ratchet, since T63/T67
session type            0     `neo4j_session` -> `graph_session`, 647 sites (A29)
Neo4j-named package     0     `app/db/neo4j_repos` -> `app/db/graph_repos`, 614 sites (A30)
engine-named binders    0/0   ratchet, NEW — nothing measured this before A30
```

**The ceiling of 54 does NOT move, and saying so first is the point.** It still counts modules
binding the repo layer directly, which is still real port-adoption debt; renaming the package
does not migrate a single module. What the rename discharges is a *different* criterion this
section wrote down and no gate ever read — and an unmeasured criterion is one that comes back
silently, which is precisely what the pinned-session ratchet caught in A29 when it refused to
credit a counter that had fallen to zero. `MAX_ENGINE_NAMED_REPO_BINDERS = 0` is that missing
instrument, with five `--selftest` cases including the substring trap (`age` inside `storage`).

**What this does NOT claim.** Class (d) is still 34, the ceiling is still 54, and the layer is
still reached by 54 modules that a port would reach for them. This closes the NAMING half of
path 2, which this section listed and which was the only half never instrumented.

**Retry/registration:** supersedes the *To unblock* row of
`D-AGE-DEFAULT-SPLITS-THE-GRAPH-UNTIL-CLASS-D-MOVES`, which named only path 1.

### 10.2 The timestamp token is rendered PER ENGINE — **DECIDED (T63, 2026-08-22)**

The 2026-08-11 construct probe listed `datetime()` → `timestamp()` as a **"mechanical
rename"**, and it is 106 of the 151 dialect sites — the single biggest line item in §10.1's
second path. Measured on a throwaway Neo4j 5 before doing any of them:

```
CREATE (a:N {t: datetime()})    chronologically FIRST
CREATE (b:N {t: timestamp()})   chronologically SECOND
CREATE (c:N {t: datetime()})    chronologically THIRD

ORDER BY n.t ASC  ->  old_datetime (DATETIME) · old_datetime2 (DATETIME) · new_timestamp (INTEGER)
```

**Neo4j sorts by TYPE first and raises nothing.** The rename changes the stored type from
`ZONED DATETIME` to `INTEGER`; existing rows keep the old type; and `created_at`/`updated_at`
drive `ORDER BY` at ten or more read sites. Every one would return a silently wrong order on
live data, with new rows pinned to one end regardless of time.

**DECIDED: the token is chosen where the query is built — `datetime()` on Neo4j,
`timestamp()` on AGE.** The stored type stays whatever each engine already uses, and each
engine's reads keep working unchanged.

* **No data migration.** The alternative — one wire type everywhere — rewrites `created_at`
  and `updated_at` on every `:Entity`, `:Fact`, `:Event` and `:Relation` node in every
  deployment, to fix a problem no deployment has.
* **No mixed-type window.** A migration would have one, and §10.1's whole argument for the
  repo-layer path was that it is *bounded*. A rewrite with a silent-wrong-order failure mode
  during the window is not bounded.
* **It is the seam §10.1 asked for**, at its smallest: the repo layer stops naming one
  engine's function, without changing what it stores.

⚠️ **This does NOT generalise to the other five constructs.** `ON CREATE SET` → `coalesce`,
`ON MATCH SET` → unconditional `SET`, `CALL {}` → CTE/`LATERAL` and `FOREACH` → two statements
are all **semantics-preserving on both engines** and were demonstrated as such by T57–T59;
they are rewritten, not tokenised. `datetime()` is the one whose naive translation changes a
STORED TYPE, and it is the only one that gets an indirection. A per-construct decision, because
the measurement was per-construct.

### 10.3 `ON CREATE SET <map>` is the one construct with no `coalesce` form — **DECIDED (T67, 2026-08-22)**

The 2026-08-11 probe's recipe is `ON CREATE SET` → `SET x = coalesce(x, v)`. Measured across
the whole repo layer before applying it:

```
ON CREATE SET branches: 17    per-property: 16    WHOLE-MAP: 1

the whole-map one:  entities.py::_MERGE_REWIRE_EVIDENCED_BY_CYPHER
    MERGE (t)-[e2:EVIDENCED_BY {job_id: props.job_id}]->(ext)
    ON CREATE SET e2 = props
```

`coalesce` takes a VALUE, not a property map. `SET e2 = coalesce(e2, props)` is not a thing,
and the naive unconditional `SET e2 = props` **changes the semantics on Neo4j as well as on
AGE**: first-writer-wins becomes last-writer-wins. Two source edges sharing a `job_id` and
pointing at one `:ExtractionSource` would then have their order decide the winner, where today
the first one keeps it.

**DECIDED: this one becomes two statements in one transaction** — does the target edge exist,
and create it with `props` only if it does not. That is T58's `update_event_fields` pattern,
which the 2026-08-11 probe established is the correct form on AGE anyway (a single-statement
CTE has no guaranteed evaluation order there). It preserves first-writer-wins exactly, on both
engines, and it is one query rather than a class of them.

**Why this is recorded rather than just done.** The recipe table in §10.1 reads as if the six
constructs are six uniform find-and-replaces. Sixteen of seventeen are. The seventeenth is not,
and the failure mode of assuming otherwise is **silent**: a rewired `EVIDENCED_BY` edge taking
the last writer's properties instead of the first's, on both engines, with no error. The recipe
is per-construct; this says it is also per-SHAPE, and the count of shapes is 2.

⚠️ **This is the third time a "mechanical" step in this migration was not.** `datetime()` was a
stored-TYPE change (§10.2), the dialect counter was over-counting prose (T63), and now the
`ON CREATE SET` recipe does not cover its own rarest form. Each was found by measuring before
applying, and each would have been silent afterwards.

## 11 · The spoiler window fails CLOSED on a value it cannot read (T48g)

**Decided 2026-08-23. Cited by T48g.**

`kal-read.controller.ts::neighborhood` is the only KAL read that does not pass its query
through: it hand-picks `hops` / `cap` / `as_of` and RENAMES `as_of` to `as_of_chapter`. The
rename carried a `parseInt` whose comment called it *"a PARSING guard, not a domain one"* and
which dropped anything unreadable. Measured on the real handler, that is what it did:

```
as_of="abc"    -> as_of_chapter=ABSENT (window REMOVED -> latest/all open)
as_of="2abc"   -> as_of_chapter=2
as_of="1e9"    -> as_of_chapter=1
as_of="12.5"   -> as_of_chapter=12
as_of="NaN"    -> as_of_chapter=ABSENT (window REMOVED -> latest/all open)
as_of=" 12"    -> as_of_chapter=12
as_of="0x0c"   -> as_of_chapter=0
```

Proven from the workload, not by analogy (rule 13): knowledge-service's `graph_views.py`
documents *"`as_of_chapter` omitted = latest (all open)"*. Dropping the parameter therefore did
not degrade the window — it **removed** it, returning the present-day graph to a caller who
asked to be held at a story position. The coercions are the quieter half: `1e9` asked for
position one billion and got **1**; `0x0c` asked for 12 and got **0**.

**DECISION — refuse, do not drop.** A non-empty `as_of` that is not an integer is a 400 naming
the value. Absent or empty stays "no window". This matches the contract this gateway already
keeps one route away — `kal-state` *"propagates the service 400 for a missing `as_of` instead of
defaulting it"* — and it matches the platform's posture that a spend- or spoiler-bearing switch
fails closed.

**Blast radius: none, and that is measured rather than argued.** The only caller is
`frontend/src/features/knowledge-temporal/api.ts`, whose `qs()` omits `undefined`/`null`/`''`
and whose `asOf` is typed `number`; `composition-service`'s KAL client names `neighborhood` in a
docstring and has no method for it. So no caller can produce a refused value, which is what makes
this latent rather than live — and is not a reason to leave a spoiler window that fails open.

**What was deliberately NOT decided here.** Whether a well-formed position is in range, or
honourable by the substrate, stays the owning service's call (T26). The guard reads; it does not
judge. A gateway that decided range here would repeat the env-var mistake its own comment
records.

## 12 · QC-5 clause 1a is not satisfiable by the critic family available — DECIDED (C43, 2026-08-24)

**Cited by QC-5 C37–C43.**

1a asks that a PLANTED canon violation be attributed, measured against the SAME draft with
nothing planted. Measured live on 8 real drafts of the acceptance book, through the studio's
route, against rebuilt images: the untouched control flags as often as the plant.

```
                                    planted   control
  qwen2.5-7b   pre-verification      8/8       7/8
  gemma-4-26b  pre-verification      7/8       7/8
```

The two arms are semantically opposite with respect to R1 — the plant replaces the canon
antagonist throughout, so the planted text attributes the trap to a character the rule says is
not the betrayer, and the clean text attributes it to the one the rule names. A critic that
tracked identity would flag one and not the other. Neither model does.

**Six candidate causes, each eliminated by measurement rather than by argument:**

| candidate | result | row |
|---|---|---|
| the verification pass drops the plant | pre-verification the arms are identical | C37 |
| the model tier is too small | the PO-target 26B behaves identically | C38 |
| "contradiction" is undefined in the prompt | counts fell, discrimination did not move | C39 |
| the critique route had no bi-temporal anchor | wired (`present_fact_count` 0→1); 1a unchanged | C40 |
| the bible carried no characters | fixed (8 of 21 entities were nameless); 1a unchanged | C41 |
| the canon rules are un-windowed | the only one that moved a number: R1 is cited on 7 of 8 clean drafts, and removing it takes the clean arm 7/8 → 4/8 | C42 |
| narrative-position framing | **did not replicate** — reported as movement off single runs, flat on re-measurement | C43 |

✅ **A SEVENTH CANDIDATE, PROPOSED BY THE PO AND ELIMINATED BY MEASUREMENT (C44, 2026-08-24).**
The six above are all about the JUDGE. The PO asked the question none of them asks — *"is the
input data explicit about what a canon IS? If there is no explicit definition, how can it be
evaluated as violated?"* — and reading the book's own `canon_rule` rows makes it a real
hypothesis: **only R1 states an exclusion.** R2–R4 are positive membership facts, R5 is a
five-word capability, and R6 (*"spirit energy is this world's power system"*) is a
definition nothing narrative can contradict. C30's adjudication is consistent with it: two of
the four false verdicts **invent a clause and hang it on a real rule id**, and the fabricated
*"and no one can drain his spirit energy"* was attached to R5.

**Tested directly rather than argued.** `scripts/qc5-arm1a-rule-isolation.py` deactivates every
rule but R1 on `lw-iso`, re-runs both arms on 4 real drafts, and restores in a `finally`:

```
active rules 6 -> 1   (every response reported active_rule_count=1)
planted flagged  3/4        control flagged  4/4
```

**The control flags MORE than the plant, on the single exclusive rule the plant targets.** The
unfalsifiable rules are not the false-positive floor — the floor is the judge's treatment of R1
itself, which is exactly what C30's verdicts #1 and #3 described. The hypothesis is refuted and
§12's conclusion is unchanged; what moves is `D-QC5-PROSE-JUDGE-FIRES-ON-CONFORMING-PROSE`,
which now has its sharpest evidence yet: **4/4 on canon-conforming prose with one rule in play.**

**DECIDED — 1a is not satisfiable with this critic family, and the row says so rather than
carrying an open question.** Three real defects were found and fixed on the way (C40/C41/C42),
each a bi-temporal mechanism with no reader, which is this refactor's own subject. None of them
is what 1a is failing on.

**What would change the answer, and neither is a code task.**

1. **A stronger critic class.** The clause is a capability assertion about a judge; both locally
   available tiers fail it. Nothing in the pipeline can compensate for a judge that cannot tell
   the two texts apart.
2. **Rule windows on the acceptance book.** C42 made `from_order`/`until_order` readable and
   measured what a windowed R1 would buy. Authoring them is a judgment about the BOOK — at which
   chapter each rule becomes true — and it also reshapes 1a itself: at a pre-reveal chapter a
   planted "someone else is the betrayer" is not a canon violation, so the plant only means
   something where the rule it contradicts is already in force.

**What this does NOT license.** It does not retract C14 (a blatant hand-built contradiction was
caught 3/3, with no matched control). It does not close QC-5, which stays `[~]`. It does not
make the critic useless: clause 2 passes, the verification pass removes real false positives
(the invented-clause verdict, 3/3), and the OFF switch and verifier role are shipped and
user-controllable.

## 13 · The SOAK grant would point dev's graph at an EMPTY store — DECIDED: option 2, BUILT (T54d/T54e, 2026-08-24)

**Measured on the real stack (rule 1), reads only (rule 6).**

```
dev Neo4j (7688)        Entity 5161 · Event 1186 · Passage 1051 · Fact 404
                        ExtractionSource 172 · EntityStatus 35 · Chapter 21 · Book/Part/Scene 3
                        EVIDENCED_BY 2813 · RELATES_TO 1144 · ABOUT 255 · HAS_CHILD 33
                        CAUSES 2 · PRECEDES 2          == 8 033 nodes / 4 249 relationships
dev AGE (knowledge-pg)  1 graph registered, 0 graphs with entities, 0 entities
infra/.env:17           KNOWLEDGE_GRAPH_BACKEND=age
running container       pre-T54 image: has `neo4j_repos`, NO graph_backend.py, NO age_pool.py
                        startup log shows ONLY "Neo4j driver initialised" — no "AGE pool ready"
migration Neo4j -> AGE  none in the tree  ->  BUILT at T54e
```

⚠️ **T54d's own census was wrong and T54e's batch measurement corrected it.** T54d named
**4 node families and 4 relationship types**; the graph holds **10 and 6**. The 4 249
relationship total was right, so the error was invisible in the number that got quoted. A
migration written from that inventory would have silently left 1 111 Passage/EntityStatus/
structural nodes behind — which is why rule 8 measures the batch before building it.

**Why dev works today, and why that is the trap.** The running container predates the backend
flip: it knows one store and it is the one with the data. `infra/.env` already declares `age`.
The GRANT reads *"SOAK: `docker compose up -d knowledge-service` from infra/. Config is right
(infra/.env:12); the CONTAINER is stale."* The config **is** right for dual-write. The
consequence of acting on it is that every graph read moves to a store with nothing in it.

**What is and is not recoverable.** Entities are re-projectable — `project_glossary_entities_to_nodes`
takes a backend-following session and the glossary is their source. **Events, Facts and the 4,249
relationships are extraction output with no projection and no migration.** They would not be
lost from Neo4j, but they would be unreadable by a service pointed at AGE.

**DECIDED 2026-08-24 — option 2, and it is BUILT (T54e).** The three candidates were:

1. **Pin dev to `neo4j`** — one line, but it re-opens §9.2's DDL-exit condition (the
   `backend declarations 0/0 non-age` ratchet goes to 1) and makes the code's default a lie on
   the only deployment that has data. It fixes the symptom by lowering the claim.
2. **Write the Neo4j → AGE migration** — the only option that makes the declared config true,
   and the only one that lets T25's last step (deleting the entity DDL, gated on *"the last
   deployment leaves the Neo4j backend"*) ever become reachable. **Chosen.**
3. **Re-extract into AGE** — cheapest to write, most expensive to run, and it discards the
   provenance in `ExtractionSource`/`EVIDENCED_BY` unless extraction replays from the same
   sources. It also re-spends the LLM budget that produced 1 186 events.

`app/db/migrations/neo4j_to_age.py`, dry-run by default in the house style of
`recanon_honorifics`.

🔴 **Its first cut wrote to the wrong graphs (T54f, same day).** It built 433 per-project AGE
graphs; the service reads **one** — `db/neo4j.py:184` opens `age_repo_session(age_pool())` with
no project and `graph_store_provider.py:98` builds `AgeGraphStore(pool, graph_name_for(None))`,
both `g_shared`. The 120 populated `p-…` graphs on iso that suggested otherwise belong to T43's
shadow harness. A migration into per-project graphs therefore reproduces the very empty store
this section exists to fix. The destination is now a `layout` parameter defaulting to the
service's topology, with `per_project` kept for the harness, and a DERIVED test reads
`db/neo4j.py`'s AST so the default moves if the service's wiring ever does.

Two rules carry the property translation, both forced by measurement rather than design taste:

* **temporals become epoch millis**, because `cypher_dialect` renders `{NOW}` as `datetime()`
  on Neo4j and `timestamp()` on AGE — one property, two types — and `graph_repos/entities.py:264`
  orders on it;
* **embedding properties are dropped, counted and reported**, because vectors live in pgvector
  under this architecture (§3.3) and a second writable copy is worse than none.

**Two things the REAL data refuted, which no fixture would have.** Running it against iso's
extraction output rather than a seeded graph broke it twice, and both are now rules with tests:

```
1  an unscoped ExtractionSource cited by a scoped Entity   16 edges on iso, 0 on dev
   -> ADOPTED into the referrer's graph (one referrer each, measured); >1 referrer RAISES
2  two RELATES_TO between the SAME pair collapsing to one  183 such pairs on dev, worst 10
   -> the relationship MERGE keys on `id`; RELATES_TO is the only type that has one, and the
      only type with parallel edges — the same list twice, which is why the id IS the key
```

Defect 2 would have dropped **at least 183 relationships on dev with every node count intact**;
`verify`'s `MISSING` vs `EXTRA` split is the only thing that reported it.

**What this does NOT retract.** T54's code is right and iso-proven: one engine-agnostic layer,
both halves reading the same store, `DEFAULT_BACKEND = "age"`. §9.2's DDL reasoning stands. The
gap is not in the architecture — it is that a declared deployment's data never moved, and
nothing in the tree would have said so.

**Still owed to the PO, and it is now ONE thing, not three.** Running `--apply` against dev
writes to a non-throwaway store, which rule 6 reserves and the GRANTS do not cover. The code is
proven; the execution is a decision. Until it runs, the SOAK grant stays unexercised — restarting
`knowledge-service` before the migration still points every graph read at an empty store.

**Everything else about it is now proven END TO END on `lw-iso` (T54h), which rule 1 names as
where code runs.** A rebuilt `knowledge-service` on `KNOWLEDGE_GRAPH_BACKEND=age`, its own
startup log reporting `AGE pool ready (graph=g_shared)`; the migration driven through its
documented command (dry-run → apply → re-run, idempotent); `graph-store-migrated-gate` returning
`MIGRATED`; the HTTP smoke passing on `age`; and finally a real
`GET /v1/knowledge/entities?project_id=…` returning **128 entities the request did not write**,
out of a store that held 35 in total beforehand. What remains owed is the authorisation, not the
confidence.

**T54i then ran the DECLARED deployment's own corpus through it** — dev's 8 033 nodes and 4 249
relationships, read from dev and written to a throwaway: **0 MISSING, 0 EXTRA, 84 s**, 22 764
temporals converted and 1 099 embeddings dropped, every label count matching dev exactly. All
**14 KAL read routes** were then swept (derived from the controller): the three graph-backed ones
that have a downstream carry real migrated rows, including `valid_from_ordinal: 7000000` — the
reading axis surviving as an integer. The sweep also found `POST /v1/kal/books/{bookId}/retrieve`
federating to a knowledge-service route that returns **404**: its documented downstream was never
built, which the controller's own header predicted a cross-service smoke would discover.

**Retry/registration:** blocks the SOAK grant. `soak-armed-gate` verifies dual-write ARMING; it
does not and cannot verify that the store being read has the data — and nothing else in the tree
did either. That absence was the reusable finding: a cutover gate that checks arming and not
CONTENT reads green on an empty destination. **Closed at T54g** by
`scripts/graph-store-migrated-gate.py`, which compares the two stores' per-project censuses and
returns `EMPTY_DECLARED` on dev today (exit 1) and `MIGRATED` on a store that has been migrated
(exit 0) — both measured on live data, in opposite directions.

## 14 · The full gate sweep is RED, and `plan-final-verification` said "every gate is green" (T48, 2026-08-24)

**Measured, not inferred.** `plan-final-verification` runs **6** hand-listed gates and its PASS
line claimed *"...and every gate is green"*. The repo has **113**. `gate-wiring-gate --run-all` —
the sweep CI drives over the same `discovered()` predicate — takes **7m25s** and comes back RED.

**Attribution, because a divergence RECORDED is not a divergence DIAGNOSED (rule 13).** Each red
was run individually and traced to the file it names. Confirmed by re-running the full sweep
after each fix — **12 red -> 10 (the two runner defects) -> 9 (the ratchet)** — so the
attribution below is a measurement of the sweep, not a reading of the code:

| gate | cause | whose |
|---|---|---|
| `qc5-acceptance-gate` | exits 2 bare — argparse requires `--file`/`--selftest` | **the RUNNER** — fixed |
| `soak-armed-gate` | exits 2 bare — requires `--url`/`--file`/`--selftest` | **the RUNNER** — fixed |
| `gate-teeth-gate` | red-ability baseline 42 -> 41 | **this commit** — moved |
| `transitions-validation-lint.sh` | `$'
'`: the WORKING TREE has CRLF | **environment** — the index is `i/lf`, `.gitattributes` says `*.sh text eol=lf`, and it is the only such file. A Linux runner never sees it. |
| `ai-provider-gate` · `gate-number-visibility-gate` · `language-bias-gate` · `llm-budget-ssot-gate` · `pagination-cap-lint` · `projection-coverage-lint` · `raw-sql-lint` · `guard-redability-gate` | real findings in `fake_truth_store.py`, `mirror_truth_handler.go`, `critic.py`, `self_heal.py`, the AGE adapters' pre-existing SQL builders, 7 unprojected glossary events | **other work** — none names a file this plan touched |

**DECIDED.** The two runner defects and the one ratchet this session moved are fixed here. The
remaining eight are real, unacknowledged, and **not this plan's**: every file they name belongs to
work outside the knowledge refactor. They are recorded rather than fixed, because fixing eight
unrelated gates inside a knowledge-architecture row is how a plan stops being about anything —
and recorded rather than ignored, because `gate-wiring-gate`'s own message is right that *"a gate
that is red and unacknowledged is how a whole suite becomes background noise"*.

**What was actually wrong, and it is the instrument.** A verifier that says *"every gate"* while
running six is the exact defect this plan's acceptance names — *"nothing silently dropped"* —
occurring in the thing that checks for it. It now states the number it ran, and asserts the
DELEGATION (that `gate-wiring-gate` reports every gate wired-or-exempt) instead of pretending to
be the sweep. Both properties are pinned by a `--selftest`, because a PASS line is prose and
prose is not run.

🔴 **CORRECTED 2026-08-30 (T48n) — the attribution above was a READING, not a measurement, and it was wrong.** Re-run file by file: `raw-sql-lint` named six sites in **this plan's own AGE adapters**, `language-bias-gate` named **this plan's in-memory double**, and `ai-provider-gate`'s 38 findings were **all** inside `frontend/dist-s01`/`dist-s6` — build output its `EXCLUDE_DIRS` matched by exact name only. All three are discharged in T48n; the remaining six are re-attributed by a FILE LIST so the next reader can check the claim instead of inheriting it.

**Retry/registration:** the six belong to whoever owns those files. `gate-wiring-gate --run-all`
already names them on every CI run; nothing here suppresses them, and no `KNOWN_RED` row was added
— an acknowledgement list that absorbs other people's defects is how they stop being defects.

## 15 · Two KAL routes federate to downstreams nobody built — DECIDED: refuse by name (T55b, 2026-08-24)

**Measured** by probing every declared downstream directly, derived from `kal-read.controller.ts`:
**12 of 14 exist, 2 do not.**

| KAL route | downstream | what answered |
|---|---|---|
| `GET /v1/kal/books/{bookId}/search` | glossary `/internal/books/{id}/entities/search` | `404 page not found` — Go's default router |
| `POST /v1/kal/books/{bookId}/retrieve` | knowledge `/internal/books/{id}/retrieve` | `{"detail":"Not Found"}` — FastAPI's default |

**The diagnosis, not just the divergence (rule 13).** A handler that means *absent* says so in its
service's own vocabulary — glossary answers `{"code":"GLOSS_NOT_FOUND"}`. A router with no such
path answers about ITSELF, in its framework's words. The KAL was forwarding the second as the
first, so an author asking for search results was told their book had none.

**DECIDED — the KAL refuses by name (rule 9), and does NOT try to implement the two features.**
`isUnroutedDownstream` classifies a framework 404 and the seam raises **501** naming the path it
federates to, so the next reader knows what to build. Building `entities/search` and `retrieve`
is glossary-service's and knowledge-service's work respectively — features, not wiring, and not
this plan's. What was this plan's is that the KAL stopped misreporting them.

**The controls carry the risk here, not the cases.** A classifier that claimed "unrouted" too
readily would turn every genuine *"this entity is not in this book"* into *"not implemented"* — a
worse lie, because the caller would stop asking for rows that are absent today and present
tomorrow. Four of the seven tests are controls, and the bite that made the classifier
over-claim reddened exactly those four while all three positive cases stayed green.

**Retry/registration:** `kal-read-surface-live-smoke` reports `NO-ROUTE` for each, so the count
is visible on every run. It falls to zero when someone builds them.

## 16 · Gates ratchet; deferrals do not — DECIDED: a third gate (T48l, 2026-08-24)

**Cited by plan row `T48`.**

**Measured** by the run-state audit, on a plan whose own numbers were sound —
`plan-verify` PASS (69 tasks, 63 done, 6 tracked, 0 untouched, every open row citing a
decision), progress block matching the checkboxes, both existing deferral gates green.
**Four deferrals were nonetheless advertising as OPEN under rows the plan has ticked `[x]`,
and three of them are contradicted by a number their own gate prints on every single run:**

| deferral | row | its premise | what the gate prints today |
|---|---|---|---|
| `D-AGE-DEFAULT-SPLITS-THE-GRAPH-UNTIL-CLASS-D-MOVES` | T54 `[x]` | class (d) 34 must move before AGE can be the default | `class (d) 32/32 — port-adoption debt; NOT an engine blocker since T54c` |
| `D-T42D-GRAPHSTORE-HAS-NO-CALLERS` | T42d `[x]` | zero adopters, 71 binders, floor 11 | `53 bind graph_repos (ceiling 53); 21 import GraphStore (floor 21)` |
| `D-T25-INDEX-RETIREMENT-BLOCKED-BY-TWO-LIVE-READERS` | T46 `[x]` | `vector bypass 4/4 — 2 LIVE reader(s) still block` | `vector bypass 2/2 (floor 2) — no LIVE reader left` |
| `D-T42A-PORT-CANNOT-CLOSE-AN-INTERVAL` | T42a `[x]` | the upper bound is unconformable | §9.3 accepted it 6 days earlier; the heading still said OPEN |

**The diagnosis, not the divergence (rule 13).** Every one of these installed a mechanism, and
**every mechanism works** — `port-adoption-gate` has printed the discharging number on each of
those commits. What does not exist is anything that CLOSES a deferral when its own cited number
crosses. A gate ratchets by construction: its floor is in the file the code is in, so rule 5
drags it along. A deferral is prose in a journal, and prose has no ratchet.

**Why neither existing gate sees them.** `stale-deferral-gate` fires when a deferral's own
`Retry when` says it is closed; none of these says that — they name CONDITIONS (*"when class (d)
moves"*, *"when the floor rises"*, *"when the two live readers go"*) that came true elsewhere.
`superseded-deferral-gate` needs a spec claiming to replace the id; none does. Both are green
and both are right.

**DECIDED — the check is STRUCTURAL, because the semantic one is not writable.** Comparing each
deferral's cited metric against its gate's live reading is the check one would want, and it
would be a keyword heuristic over prose in four shapes naming numbers four gates format four
ways — which `stale-deferral-gate`'s own docstring already records as measured-unreliable. So
`scripts/discharged-deferral-gate.py` asks a question with a yes/no answer:

> a deferral heading that advertises OPEN must not sit inside a row marked `[x]`.

A deferral is an **obligation**. The plan is a journal, so a row's span legitimately carries
other rows' evidence — but an obligation filed under a finished row is unfindable, which is
exactly how these four survived. Three honest fixes: strike it with the measurement that
discharged it; mark it `ACCEPTED` **with the § that accepted it**; or move it under the open row
it belongs to.

**The escape hatch is itself falsifiable (rule 3).** A bare `ACCEPTED` would be a magic word
that silences any finding, so it is honoured only alongside a `§` citation, and selftest case 7
is the control that pins it — **BITE W** drops the citation requirement and reds exactly that
case. **BITE V** drops the ticked-row guard and reds exactly the two controls (an open deferral
under a `[~]` row, and under an untouched one) while every positive case stays green, which is
the shape an over-reporting gate would pass.

**Cost of leaving them open, since it is not hypothetical.** `D-AGE-DEFAULT-SPLITS…` made T17
read as the critical path to this plan's goal for five days, and its TITLE is the false premise
— T54c answered it by name two days after it was written. The plan already records what this
class costs, about a different id: *"the mechanism that made a settled question read as open for
eight days and stopped a run on a decision nobody owed."*

**Retry/registration:** `discharged-deferral-gate` runs in `.githooks/pre-commit` and is
discovered by `gate-wiring-gate` (113 → 114). Its count is zero today and goes non-zero the
moment a row is ticked over an open obligation.

## 17 · `AgeGraphStore.events_page` counts in Python — **ACCEPTED, with a priced trigger (T17 A33, 2026-08-24)**

**Cited by plan row `T17`.** Surfaced by `discharged-deferral-gate` when T17 was ticked — the
gate built two cycles earlier refused the commit that would have left three obligations under a
finished row, and this is the one of the three that was not already superseded by §1.3.

**The limitation is real and correctly described.** `AgeGraphStore.events_page` filters, sorts
and slices in Python over a bounded scan, because AGE has no single-statement shape returning
both the page and the unpaged `total`, and two statements can disagree under concurrent writes.

**DECIDED — accept it, and the acceptance is PRICED rather than asserted.** Its own re-open
condition is *"a real corpus approaches 5 000 events in one browse window"*. Measured on dev
2026-08-24, the largest project in the store holds **418** events — an order of magnitude below
the cap, on the biggest corpus that exists. The bounded scan is not a latent outage; it is a
shape that would become one at a scale nothing in this system is near.

**Why not fix it now.** The two available fixes are a `WITH collect(e) AS all …` shape returning
`size(all)` beside the slice, or two statements inside one transaction so the pair is at least
mutually consistent. Both are real work on a read path that is correct at every corpus size that
exists, and §1.4's standing rule is that an adapter refuses rather than half-implements — this
adapter neither refuses nor half-implements, it is simply doing the work in the wrong layer.

**Re-open trigger, unchanged and now measurable:** one project's browse window reaching 5 000
events. The cap makes that loud rather than silent, which is why acceptance is safe.

## 18 · C31's precision result does not generalise — the PO's own conditional has fired (C45, 2026-08-24)

**Cited by plan row `QC-5`.**

C31 is the PO's precision spend and its evidence was *"a narrow passage-aware SECOND pass keeps
a planted violation 4/4 while dropping 2/2 clean and **14/14 historical false positives** — on a
26B verifier."* **Those 14 are the false positives that motivated building it.** Rule 3 asks for
a case the detector was not derived from; this repo already names the failure —
`detector-fitted-to-its-motivating-examples-is-green-by-construction`.

**Measured on a held-out set, live, through the shipped route against the running image:**

```
critic 019eb620 (7B)   verifier 51ea9fd7 (26B, the PO's target tier) — DISTINCT, and resolved
4 untouched control drafts · raw 5 · attributed 5 · verifier dropped 0
                                            HELD-OUT-MISS
```

**No adjudication is needed and that is the design.** The control arm is the flow's *unmodified*
draft. R1 says the canon antagonist IS the betrayer and no one else is, and the untouched draft
attributes the trap to exactly that character — so the control is canon-conforming with respect
to R1 **by construction**, and every surviving R1 attribution on it is a false positive by the
experiment's design rather than by anyone's reading. One example, verbatim: the flagged span is
*"He was no longer the cousin who kept himself humbly in his brother's shadow"* and the reason
merely restates R1. The verifier's own prompt says *"Restating the rule is not a contradiction"*
— it kept it anyway.

**DECIDED — the finding, and it is not a new PO question.** C31's decision was conditional in
the PO's own words: *"**Spend on precision first**; if precision cannot be reached, default the
judge OFF behind an explicit user-controlled setting on the FE."* Precision was spent on,
measured in-sample at 14/14 and **held-out at 0/5**. The conditional's second branch is what the
measurement points at.

✅ **DECIDED AND BUILT — the PO chose the NARROW control (2026-08-30, C46).** Four options were
put: flip `critic_enabled`, a narrow channel switch, measurement-only, or an auto-gate. The PO
took the narrow one, and it is what the evidence supports: C45 indicted the `violations[]`
channel and faulted neither the four dimension scores nor the craft notes QC-5 C17 valued.

`canon_violations_enabled` — TIER first (rule 4): per-book Work setting beside `critic_model_ref`
and `critic_enabled`, run params as override, the same precedence order the other two use.
**Default FALSE.** `judge_prose` takes `emit_canon_violations`, and **its parameter default is
the product default** — C34 found the verifier role passed at one call site of three, so a caller
that forgets here must fail SAFE. Emitting is opt-in.

Never silent: `violations_withheld_count` and `canon_violations_suppressed` ride the envelope,
because *"the judge found nothing"* and *"the judge was not allowed to say"* need opposite
responses. Live, against a rebuilt image: `raw 1 · withheld 1 · suppressed true · violations []
· craft_notes 1`.

**Re-enabling is a MEASUREMENT, not an opinion:** `qc5-verifier-heldout` returns
`HELD-OUT-HOLDS` only when a distinct verifier drops every false positive on drafts it was not
derived from. That is the condition for a book to turn the channel back on.

**~~What is not taken here is the shipped default~~** — superseded by the decision above. The
reasoning it recorded still stands for `critic_enabled` itself, which is UNCHANGED: `critic_policy.critic_enabled` documents its own TRUE as
*"deliberately: flipping the shipped default is a product decision, not a consequence of adding
the control"*, and n=5 on one book is thin evidence for a fleet-wide flip. So the measurement is
recorded and WIRED — `scripts/qc5-verifier-heldout.py`, selftested and bitten — so that
"precision was reached" can never again be asserted from the set the detector was built on.

**Re-open/registration:** re-run `qc5-verifier-heldout --run` against any candidate verifier. The
verdict is `HELD-OUT-HOLDS` only when a distinct verifier drops every false positive on drafts it
was not derived from.

## 19 · T25 closes on the COUPLING; the dev cutover moves to merge-to-main — DECIDED (PO, 2026-08-30)

**Cited by plan row `T25`.**

T25 had no open deferral left and still could not close on its own terms: its exit is deleting
the passage vector DDL, and T25z made that a **mechanical predicate** —
`passage read-primary declarations 2/2 non-postgres` must reach 0. Under the PO's iso-only
decision (2026-08-24) dev never flips, so it sits at 2 indefinitely, and T48/T49 stay blocked
behind a row that is finished in every sense except a condition nothing in this plan can meet.

**DECIDED — close on the coupling, exactly as §9.2 did for the ENTITY DDL.** That section's
words apply unchanged: *"it is not a scheduling call and it is not owed to anyone: the condition
is mechanical and already written down."* T25 closes on what is proven — ① the backup path, ②
the cutover switch, ③ steps 1/2/5, ④ the event index deleted on a measured zero-read — with the
passage DDL's exit as a CONSEQUENCE that `port-adoption-gate` prints on every run. The gate goes
red the day a deployment declares `postgres` and the DDL has not followed.

**The dev cutover is not abandoned; it is RESCHEDULED to merge-to-main (PO, 2026-08-30):**
*"close it, and add other task when we merge to main branch, we will retire old infra."* At that
point the sibling `infra` stack is retired rather than worked around, which removes both blockers
T25y measured at once — the container that predates the dual-write, and the instruction to leave
that stack alone.

**OWED AT MERGE-TO-MAIN, and it is a list, not a gesture:**

1. Retire the sibling `infra` compose project; stand dev up from this checkout.
2. `backfill-passages` per project so the Postgres secondary is non-empty — **measure passage
   search before AND after**, because an empty secondary fails SILENTLY (§9.1 option 2, the
   shape this plan has caught five times).
3. `KNOWLEDGE_VECTOR_READ_PRIMARY=postgres` in `infra/.env.example` and the compose default.
4. Delete `passage_embeddings_1024` from `neo4j_schema.cypher` — only once
   `port-adoption-gate` reports `passage read-primary declarations 0/0`.
5. Re-run `architecture-live-proof --run` against the new dev; leg 2's censuses come from it.

## 20 · A `MIGRATED` verdict over an EMPTY other-census — DECIDED: `SOLE_STORE`, and the STORE leg still passes (T48z, 2026-08-30)

**Found by running the goal's own proof**, not by reading it. `architecture-live-proof`'s STORE
leg passed on iso with:

```
PASS  2 STORE  the declared store holds the corpus  rc=0
      [graph-store-migrated-gate] OK — MIGRATED: the declared store holds all 0 project(s)
      the other store does
```

`graph-store-migrated-gate` returned `MIGRATED` because AGE's census covers every project in
Neo4j's census, and Neo4j's census on iso is `{}`. **The set of projects compared was zero.**

### Why this was not simply a bug in the verdict

`(declared=full, other={})` is the *post-migration* shape: you migrate, then you empty the old
store. The gate's own selftest encoded that on purpose. So `MIGRATED` there is defensible.

What is **not** defensible is that the same three words are produced by three different worlds:

| input | what actually happened |
|---|---|
| `other = {…5 projects…}`, all present in declared | a migration was verified |
| `other = {}` | the old store was emptied — **or never existed** |
| `other` census file absent | nobody looked |

The third already had an honest name: `ONE_STORE`, INDETERMINATE, *"there is nothing to compare
against"*. **An empty census carries exactly the same comparison evidence as an absent one**, and
was the only one of the three that read as the success of a comparison.

### Decision

1. `other_has == ∅` now returns **`SOLE_STORE`**, INDETERMINATE, whose reason states that nothing
   was compared and that this shape *"is the post-migration shape AND what a store that never had
   a second one looks like — these are not distinguishable from censuses alone."*
2. `MIGRATED` now reports its comparison size — *"a comparison over N project(s), not over none"*
   — so the count is on the wire rather than inferable from a sentence.
3. **The proof's STORE leg still PASSES on `SOLE_STORE`, deliberately.** The leg claims *the
   declared store holds the corpus*, not *a migration was verified*. `SOLE_STORE` is only
   reachable when the declared census is non-empty — an empty declared store is already
   `EMPTY_DECLARED` or `BOTH_EMPTY`, both distinct readings — so the leg's actual claim is
   entailed. What was wrong was the label, not the pass.

A stricter leg was considered and rejected: making the STORE leg fail on INDETERMINATE would make
the proof unprovable on a legitimate single-store deployment, which iso is (AGE 648 projects /
5683 entities, Neo4j 0). That would trade a misleading green for a permanent red on a correct
system.

**Retry when:** a deployment runs two populated stores — then `MIGRATED` becomes reachable with a
non-zero comparison size, and the distinction this section draws starts carrying real weight.

## 21 · The auth boundary IS a proof leg — T48u's exclusion REVERSED (T48ap, 2026-08-30)

T48u built `kal-auth-boundary-live-smoke` and deliberately kept it out of
`architecture-live-proof`, in writing:

> *"Not added as a proof leg, deliberately. `architecture-live-proof` is about the ARCHITECTURE
> — backend, store, surface, port, spine. This is an access-control property of one gateway, and
> folding it in would make a green architecture proof depend on a JWT secret and a stranger's
> token being to hand."*

**The reasoning was sound and its premise expired.** At the time, a leg without its inputs was
an unsolved problem — the proof would have needed a JWT to return anything at all. Since then
two legs have been added that face exactly the same constraint and are handled by mechanism
rather than by exclusion:

| leg | needs | without it |
|---|---|---|
| 2 STORE | two censuses | `SKIP`, reported |
| 6 AXIS | one census | `SKIP`, reported |
| 7 AUTH | a stranger JWT | `SKIP`, reported |

`--min-legs` then makes the shrink visible, and a caller who cannot supply the token gets a
smaller proof that SAYS it is smaller — which is the behaviour T48u actually wanted.

### What the exclusion cost

T48ao measured it: `kal-auth-boundary-live-smoke` appeared **exactly once** in the whole
repository, as `--selftest` in the pre-commit hook. **The only live check of the KAL's grant
boundary ran when somebody remembered to run it**, and between T48u and T48ap nobody did. The
fixture had even rotted — the stranger JWT was gone from disk, and the smoke correctly reported
`BLANKET-REFUSAL` on the empty one rather than pretending.

That is the same defect the same session found twice more: `glossary-ordinal-axis-gate` wired
and never fed (T48ao), and `COVERED_ELSEWHERE` citing a check nothing verified (T48an). A
control that exists and is never exercised is indistinguishable from one that does not exist.

### Decision

**Leg 7.** The auth smoke joins the proof, skipping when no stranger JWT is supplied. The
argument that a security property is "not architecture" is rejected on its own terms: the KAL is
the security boundary on the user path — its own docstring says the BFF does no grant check —
so whether that boundary discriminates is a property OF the architecture, not adjacent to it.

**Retry when:** never — this is a reversal, not a deferral. If a future run finds the leg
skipping in CI because no token is minted there, the answer is to mint one, not to drop the leg.

## How this file is kept honest

* Every section is cited by the plan row it decides. `plan-final-verification.py` fails a `[~]`
  task that cites nothing.
* A decision that turns out wrong is **struck through with the measurement that killed it**,
  never quietly edited — the same rule the plan uses for its own retractions.
* New questions get a section here on the day they are found. They do not get a deferral,
  because this project does not have deferrals.

## 22 · PERF-3's helper signal passes a whole FILE — DECIDED: left as-is, and the price of changing it measured (T48ay, 2026-08-30)

**The question.** `pagination-cap-lint`'s Go leg decides a list query is bounded if the file
containing it mentions `clampLimit` or `parseLimitOffset` **anywhere**. That is a file-level
signal for a per-query property: one helper call in a 3000-line `server.go` vouches for every
other `LIMIT $N` in it, including one that caps nothing.

**Measured before deciding** (rule 8), by routing the helper signal through the same
`_go_capped_in_scope()` resolver the new inline signal uses:

```
39   raw findings if the helper signal were function-scoped
31   already carried by the BASELINE
 8   would newly RED CI — all eight in book-service:
        mcp_tools_read.go:353   toolBookGetChapter
        search.go:36,46,49,64,85,100,126   (seven file-scope SQL constants)
```

The first-pass estimate was "32 across four services"; that came from a prototype whose constant
resolver did not handle the `const` keyword, and it is wrong in both directions. The numbers
above are the shipped resolver's.

**DECIDED — the helper signal stays file-level; the new inline signal is function-scoped.**

Seven of the eight are not demonstrated defects. They are file-scope SQL constants in
`search.go` that no function names, so the resolver cannot show they are capped and **fails
closed** — a resolution failure costs a finding and never hides one (pinned by the
`file-scope SQL const that NO function references` selftest case). Turning that into eight red
lines in book-service, on a commit from the knowledge refactor, would hand that service's owners
a batch that is mostly an instrument's blind spot rather than their bug. Same call as T48aw,
where a new lint leg was made advisory for the same reason and the same domain boundary.

What this does **not** do is inherit the looseness into new work. The inline-cap signal added in
T48ay is function-scoped from birth: a `LIMIT` is judged by its enclosing function, and a
file-scope SQL constant by **every** function naming it — if any one of them fails to cap, the
site is a finding, because that caller is the one reaching the database unbounded. A new signal
has no back-compat reason to be loose.

**How this stops being a decision and becomes a fix**, in order:

1. Teach the constant resolver the `search.go` shape — constants assembled or referenced
   indirectly — so the seven either resolve to a capping function or become real findings. This
   is the only step that needs new code, and it is the one that decides whether the batch is 8
   or 1.
2. ~~Verify `toolBookGetChapter` by hand: it is a real per-function verdict today, not a blind
   spot.~~ **DONE 2026-08-30, and the claim was WRONG — it is a blind spot too.**
   `mcp_tools_read.go:353` caps in its own function:

   ```go
   const maxChapterBlocks = 300                       // :246
   if limit <= 0 || limit > maxChapterBlocks { limit = maxChapterBlocks }
   ```

   `GO_INLINE_CAP` requires `\d+` on **both** sides of the comparison and the assignment, so a
   cap written against a NAMED CONSTANT is invisible to it. The batch is therefore **8 false
   positives, not 7 blind spots plus 1 verdict** — which strengthens the decision above and
   weakens the case for step 3: pointing the helper signal at `_go_capped_in_scope()` today
   would red eight sites and none of them is a defect.

   The narrower fix this exposes is its own step: teach `GO_INLINE_CAP` to resolve a
   package-level `const NAME = <int>` on either side. A *variable* must NOT be accepted — the
   whole point of the signal is that the bound is knowable at the call site, and
   `limit = someVar` is not.
3. ~~Point `GO_CLAMP_SIGNALS` at `_go_capped_in_scope()` — one call site — and refresh the
   BASELINE by intersection, never `--regen`.~~ **MEASURED 2026-08-30 (L6) — the batch is 2,
   not 8, and BOTH survivors are the same false positive. Step 3 is NOT taken.**

   Step 1 landed: `GO_INLINE_CAP` now resolves a package-level `const NAME = <int>` (single
   and block form) on either side, and a `//` comment no longer counts as a query — three of
   the five findings a stricter signal produced were `search.go` documenting its own
   placeholders (`// $3 = escaped ILIKE pattern   $4 = limit`), the instrument reporting on
   its own prose. Three BASELINE rows were dead and are pruned by intersection.

   With the instrument honest, step 3 would newly red **two** sites:

   ```
   search.go::LIMIT $4 OFFSET $5        lexicalSearchSQL -> runLexicalSearch (no cap)
                                        …whose CALLERS call parseLimitOffset
   server.go::LIMIT $… OFFSET $…        buildBookListQueries (no cap)
                                        …whose caller listBooksByLifecycle calls it
   ```

   **Both are query BUILDERS whose cap lives one hop up, in the caller** — and the repo
   actively wants that shape: L5 extracted `buildBookListQueries` precisely so the page query
   and the COUNT cannot drift apart. Function-scoping the helper signal would penalise the
   structure this plan spent a cycle introducing.

   So step 3 needs a step 0 that §22 did not know about: `_go_capped_in_scope` already follows
   a file-scope SQL const to the functions that name it, and it would have to follow a query
   BUILDER to the functions that call it — one level up the same idea. That is a real
   extension, not a flag flip, and it is what a future cycle would build. Recorded with the
   number rather than left as "8 findings, mostly noise".

The three background sweepers already in the BASELINE (`dek_shred_sweeper`, `reparse_sweeper`,
`epub_asset_retention`) are verified non-defects with server-set batch sizes and keep their rows
through all of this.

**Not a deferral.** The rule PERF-3's Go leg enforces today is: *a page cap is recognised
per-file by helper name, or per-function by an inline bound.* That sentence is what the lint
checks, its `--selftest` pins both halves and the direction the resolver fails in, and this
section records the narrower rule it could enforce with the price attached.

## 23 · T33 closes on ITS OWN bite; the labelling sheet answers a different question — DECIDED (2026-08-30)

**Cited by plan row `T33`.**

Two things have been treated as one, and separating them is what unblocks the row.

**What T33's row actually asks.** Its criteria are: widen `causal_edges.py` from `causes/enables`
to `causes | precedes`; copy the `motif_link` cycle guard to the event DAG; make `unknown` a
first-class answer; and one bite — ***"run over the corpus → edge count non-zero **and** the
graph acyclic"***. The row's own note from 2026-08-14 says the code and the unit evidence are
done and *"what remains is the live run, not another row."*

**That live run has now happened**, on `lw-iso`, against the planted corpus:

```
edges_written                                   2
cycles through a node back to itself            0
ordered edges that are NOT strictly forward     0
event_order                       1000001, 1000002, 1000003   (chapter x stride)
```

**What the labelling sheet asks is a different, harder question:** not *"does the pass emit a
non-zero acyclic set"* but *"are its judgements CORRECT"*. That is accuracy, it needs ground
truth from a person, and **the row's bite never asked for it.** The sheet (T33f–T33h) is a
richer instrument built later; treating it as T33's exit condition is what left the row open
while its stated criteria were met.

**DECIDED — T33 closes on the criteria it states, and the accuracy question stays open under
its own name.** Not a downgrade: the bite is the same one the row has carried since it was
written, and it is now measured on real data rather than asserted.

**Still owed, and recorded here so it cannot be lost with the row:**

* `docs/measurements/2026-08-24-t33-causal-labelling-sheet.md` — 20 pairs, every `LABEL:`
  blank, `labelled_by:` unsigned. `--score` refuses an assistant signature and **that guard
  is untouched**: a detector graded against labels its own author wrote is green by
  construction.
* The PLANTED arm cannot substitute for it, and its own design said so before it ran. It also
  cannot be scored **at beat granularity**: extraction yielded **7 events from 16 designed
  beats**, and `DESIGN.md`'s pre-committed mapping rule is that a chapter whose event count
  differs from its beat count is *reported as ambiguous, not silently re-aligned*. Writing a
  new design at event granularity **after** seeing those events is exactly the drift the
  SHA-256 binding exists to prevent, so it is not a repair — a fresh corpus with a design
  authored first is.

**What the planted arm did deliver**, which is why it was worth running: the pass reported
`edges_written: 0` while the model had answered correctly in bare-identifier JSON, and the
parser dropped two real causal edges in silence. **A zero there is indistinguishable from
"there is no causation in this text" — the exact signature of T33's own stop condition.** The
row would have closed on a number that described a parse bug. Fixed, tested, and re-measured
live (0 → 2).

**`D-T33-CAUSAL-COVERAGE-UNMEASURED` — ACCEPTED here, not discharged.** Its question is
*"the bite is one book, the graph is eight projects"*: does the pass produce useful causal
edges across the whole corpus, not just where it was pointed. That is a COVERAGE question,
it is the accuracy question in another coat, and **nothing in this run measured it** — the
planted arm is two authored chapters. Its own `To unblock` mechanism (a synthetic reference
corpus with hand-authored ground truth) was retracted in 2026-08-21 by the plan that was
supposed to carry it, and §4.3 had already moved corpus-wide coverage to QC-6.

It is recorded here rather than struck because striking it would assert a measurement that
does not exist. It travels with the 20 labels above: both ask *is this pass any good*, and
neither is answered by *does it emit a non-zero acyclic set*.

## 24 · `event_order`'s two writers — one race was impossible, the other was real and unguarded (L3, 2026-08-30)

**Cited by leftovers row `L3`.**

**The question the row asked.** `b6c8fde13` fixed the deterministic collision: the
within-chapter index continues from the band's maximum instead of restarting at 0. It said
plainly what it did NOT close — *"two jobs extracting the same chapter at the SAME time both
read that maximum and both write above it."* L3 asked for that to be closed, or accepted with
the blast radius **measured, not assumed**.

**Measured, and the answer inverts the question.** `event_order` has exactly two writers:

| writer | under the one-active-job invariant? |
|---|---|
| `pass2_writer.write_pass2_extraction` | **yes** — it runs only inside an extraction job |
| `run_orders_backfill` (`POST /internal/projects/{id}/backfill-orders`) | **no** — nothing checked |

**Two extractions cannot race.** `idx_extraction_jobs_one_active_per_project` is a UNIQUE
partial index on `(project_id) WHERE status IN ('pending','running','paused')` — so a second
concurrent `POST /extraction/start` fails its INSERT and the endpoint answers 409. Read out
of the live database rather than out of the migration file:

```
CREATE UNIQUE INDEX idx_extraction_jobs_one_active_per_project
  ON public.extraction_jobs USING btree (project_id)
  WHERE (status = ANY (ARRAY['pending','running','paused']))
```

⚠️ Checking it took two tries and the first one nearly produced the wrong answer: the index
is on `loreweave_knowledge` (5555), and querying `loreweave_knowledge_vectors` (5556, the
AGE store) returned **empty** — which reads exactly like "the invariant does not exist". The
wrong-store defect this plan has now hit four times.

The events consumer was checked too, because its own comments say it runs *"OUTSIDE the
one-active-job-per-project extraction lock"*. It **retracts evidence** and never calls
`merge_event`, so it cannot assign an `event_order` and is not a third writer.

**The backfill was the real hole, and it is worse than an overlap: the two writers DISAGREE.**
`run_orders_backfill` assigns `base + idx` over `sorted(event_ids)` — dense from 0 — while
`pass2_writer` continues from the band's current maximum. Run together they produce two
numberings of one chapter and the reading axis is whatever interleaving won. That is not a
crash: `event_order` is the spoiler cutoff, the timeline, `list_events_in_order` and the
causal pass's forward-only filter, and a duplicate there is a stable sort quietly falling
back to row order.

**DECIDED — the backfill endpoint takes the same invariant.** It answers **409** while a
`pending`/`running`/`paused` job holds the project, naming the job, and the status tuple is
one constant so the guard and the index cannot drift apart. The 404 for an unknown project
still wins, so a caller naming a project that does not exist hears that rather than a
conflict about a job it could not have started.

**What this does NOT claim.** The guard is a READ, so a job starting inside the check→act
window is still possible; the index remains the thing that makes the extraction side
unambiguous. It closes the case that was actually reachable — firing a backfill at a project
that is visibly busy — and narrows the rest to a window measured in milliseconds. Stated
here rather than left for someone to discover in the code.

## 25 · The 51 `event_order` collisions are ACCEPTED — renumbering buys uniqueness, not correctness (L2, 2026-08-30)

**Cited by leftovers row `L2`.**

**Measured on `lw-iso`, 2026-08-30:** 1224 ordered events; **51 colliding
`(project_id, event_order)` pairs**, 102 events, 6 projects. All written before `b6c8fde13`
stopped `pass2_writer` restarting its within-chapter index at 0.

**The row's own premise was wrong, and measuring is what showed it.** L2 said
*"`backfill_orders.py` already exists and already imports the shared stride, so the cost of
the first option is measurable rather than guessed."* The backfill selects
`WHERE e.chapter_id IS NOT NULL`, and **0 of the 102 affected events carry `chapter_id`** —
104 of 1320 events store-wide do. The existing tool reaches **none** of them. A live
`POST /backfill-orders` on the worst project returned `events_ordered: 0`, which is what sent
me to look.

**DECIDED — ACCEPT, and freeze the number.** Not because repair is expensive, but because
repair does not produce a correct order:

* **There is no narrative source to renumber FROM.** The extractor's emission order produced
  these values and is not narrative: T33k measured `盤古開天闢地` — the creation of the
  universe — sitting at position 18 of 20 in one chapter.
* **The backfill's own scheme is `sorted(event_ids)`** — id order, arbitrary in a different
  way. Renumbering would trade one deterministic wrong order for another across 102 nodes.
* **The spoiler cutoff is untouched.** Every collision is *within* a chapter band, and the
  cutoff is `before_order N × EVENT_ORDER_CHAPTER_STRIDE` — a within-band clash cannot move
  it. Checked, not assumed: 0 collisions span two bands, which is structural since a single
  `event_order` value lives in exactly one band.
* **Nothing uses `event_order` as an identity.** No dict keyed on it, no upsert, no join.
  `motif_beat`'s *"`:Event` nodes keyed by `event_order`"* means ORDERED BY, not keyed.

**WHAT ACTUALLY BROKE, AND IS NOW FIXED.** Four call sites order by `event_order` and they
did not agree on the tie-break: `events.py` ×2 on `e.title ASC`, `timeline.py` on `e.id`, and
`fact_for_check._EVENTS_AT_OR_BEFORE_CYPHER` on **nothing at all** — a bare
`ORDER BY e.event_order DESC` in front of a `LIMIT`. On colliding data, which event survives
the cut is whatever the store returns, so the same canon check could see a different evidence
set on two runs and neither run was wrong to look at. That is the concrete harm of the 51,
and it is a determinism bug rather than an ordering one.

It now tie-breaks on `e.id`, not `e.title`: **a title is editable**, and ordering history by a
field the user can change means renaming an event silently reorders the evidence behind a past
check. The two `events.py` sites keep `title` for now — unifying all four moves public
ordering and deserves its own cycle rather than riding along here. The divergence is recorded
so it is a known choice rather than an accident.

**The freeze is a RATCHET, not a comment.** `scripts/event-order-collision-gate.py` counts
the pairs against `MAX_COLLIDING_PAIRS = 51`: shrink-only, red on growth, because a new
collision means the writer regressed. It needs the live graph, so it is registered
`NEEDS_STACK` and prints `SKIP … needs a live stack` in `--run-all` rather than being
invisible (L4).

## 26 · `D-T33-CAUSAL-COVERAGE-UNMEASURED` is DISCHARGED — three numbers, never one (L1, 2026-08-30)

**Cited by leftovers row `L1`; discharges the deferral §23 recorded as ACCEPTED.**

§23 held it open because *"nothing in this run measured it"*. It is measured now, by
`scripts/causal-coverage-gate.py`, and the shape of the answer is why it stayed unmeasured
for so long: **the question is three questions, and §4.3's retracted `0.34 %` was one of them
answered with another's denominator.**

```
REACH       : 3/82   = 3.66 %   of projects holding any event
YIELD       : 131/1277 = 10.26 % of CANDIDATE PAIRS (one 12-event window, stride 6)
CONSISTENCY : 0 of 131 edges lie outside every window
```

**REACH is an OPERATIONS fact, not a quality one.** The causal pass is triggered by
`POST /internal/…/causal-edges`; a project without edges is one nobody ran it on. Reporting
3.66 % as "coverage" would be §4.3's retracted number wearing a new hat — a ratio over
residue, dividing by 79 projects the pass was never pointed at.

**YIELD is the quality number, and its denominator is the DESIGN'S.** `infer_causal_edges`
slides a 12-event window with stride 6 over `list_events_in_order`, and `parse_edges` keeps
only pairs inside one window; a pair that never shared a window was never offered to the
model. Over the pairs it actually considered, the pass labels **10.26 %**. Answering §23's
words — *"does the pass produce useful causal edges across the whole corpus, not just where
it was pointed"* — it produces them wherever it IS pointed, at roughly one pair in ten, and it
has been pointed at three projects.

**CONSISTENCY is the assertion with teeth.** `parse_edges` cannot emit an edge whose endpoints
never share a window, so a non-zero means something else wrote ordered edges or the ordering
moved underneath them. It is 0 of 131, and `MAX_UNEXPLAINED_EDGES = 0` reds on growth.

⚠️ **Two caveats, in the tool's own output rather than here alone.** The candidate set is
computed from the corpus NOW while the edges were emitted against the corpus THEN, so YIELD
drifts as a project grows. And `event_order` may be NULL: `list_events_in_order` sorts
`coalesce(event_order, INT64_MAX)` then title, so null-order events are in the window like any
other — **excluding them was this script's first bug**, and it turned `0 unexplained` into
`3`. Reproduced deliberately as a bite, because measuring the wrong denominator is precisely
what this deferral is about.

**What this does NOT say.** It is coverage, not accuracy. Whether the 10.26 % it labels are
labelled CORRECTLY is the 32-pair sheet's question, still awaiting a signature under §23.
Two different questions, and §4.3 exists because they were once answered with one number.

## 27 · The 4355 legacy graphs were TEST RESIDUE, and a 120-graph sample said the opposite (L7, 2026-08-30)

**Cited by leftovers row `L7`.**

```
graphs BEFORE 4356 (g_shared + 4355)     AFTER 1
registry      472 projects known to the product
classified    real 0 · fixture 3810 · empty 545
cost removed  4355 vertex tables / 68 MB  ->  1 table / 16 kB
```

**They were not "pre-migration shape".** Their contents say what they are — an `Entity` named
`Kai` with facts `an outer disciple` / `an inner disciple`, under `user_id: u-e3cb628932f4`
and `project_id: p-e3cb628932f4`. That is this repo's standard integration fixture. Each test
run created a throwaway graph and never dropped it.

**A SAMPLE WOULD HAVE DESTROYED DATA — twice over, in two different ways.**

* A seeded 120-graph sample reported **0 real, 109 synthetic, 11 empty**. The full census with
  the same rule reported **142 real**. Dropping on the sample's authority would have taken
  them.
* Then the 142 turned out to be `p-inject` and `p-0e3d1764591e-second` — fixture ids that no
  id-SHAPE rule classifies correctly. A `^[pu]-[0-9a-f]+$` regex called them REAL; the
  earlier "anything that is not a UUID is residue" rule would have called a future id format
  RESIDUE and dropped it.

**So the classifier asks the REGISTRY, not the id.** `knowledge_projects` answers the actual
question — *is this a project the product knows about?* — and it is a fact rather than a
pattern. 472 rows; `p-inject` is not among them, `019fefde-…` is. With the registry as the
authority: **0 of 4355 graphs held a project the product knows about.**

`registered_projects()` REFUSES an empty or unreadable registry rather than returning an empty
set, because "nothing is registered" and "the query failed" would classify the entire store as
droppable and differ by 4355 graphs.

**THE COST OF LEAVING THEM WAS NOT DISK.** 68 MB is unremarkable. The sharp edge is that a
single ordinary maintenance query across 4355 schemas **exceeds `max_locks_per_transaction`**
(`ERROR: out of shared memory`), so counting rows in one statement was impossible and the
census had to batch. After the sweep that statement runs. A schema count at which routine DBA
work starts failing is a better argument than megabytes.

**DECIDED — dropped on `lw-iso` only, and the tool cannot do otherwise.** `--drop` refuses any
target that is not `(25556, loreweave_knowledge_vectors)`, checked BEFORE any query. `g_shared`
is never a candidate. `scripts/legacy-graph-sweep.py` is a maintenance command and deliberately
NOT named `*-gate`: a check CI runs must never be able to drop a graph.

**Verified after:** `g_shared` is the only graph left, and the numbers §25 and §26 measured are
unchanged — `51` colliding pairs at the ceiling, `REACH 3/82`, `YIELD 131/1277`,
`CONSISTENCY 0 of 131`. The sweep touched nothing the product reads.
