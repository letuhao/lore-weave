# Knowledge-refactor open decisions — the spec that replaces the deferral register

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
### 1.2 The port does **not** own janitorial work — **DECIDED**
*Replaces `D-MAINTENANCE-IS-NINE-JANITORS`.*

`maintenance` measured out as nine things across eight consumers. They split three ways, and
only one class joins the port:

* **Domain reads → the port.** `project_graph_stats`, `count_nodes_by_label`. A second engine
  must answer these, and callers ask them as questions about the book.
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

### 2.1 The acceptance measurement is **three runs, majority rule** — **DECIDED**
*Replaces `D-QC5-PIPELINE-NOT-REPRODUCIBLE`.*

QC-5 passes when, over **three runs of the same chapter with the same models**:

* **at least two** produce `canon_consistency <= 3` **and** at least one attributed violation, and
* **no run** produces `5/5` with zero raw findings.

**Why majority and not unanimity.** Measured 2026-08-13: three runs gave `severe / warn / ok`
(canon 2 / 4 / 5). Demanding unanimity makes the test fail on a working pipeline; accepting one
run makes it pass on a broken one. The second clause is the one that matters — a clean 5/5 with
*nothing found* is the defect signature, and it must not appear in any of the three.

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

### 3.2 The restore drill's recall gap is accepted and documented — **DECIDED**
*Replaces `D-T25B-SOAK`.* `pg_restore` rebuilds the ANN graph rather than copying it, so
post-restore top-10 overlap was 7/10 at 20 000 rows. **Data recovery is promised; *result*
recovery is not.** That is the guarantee, written down. QC-3 still owes one rebuild measurement
above `diskann.min_vectors_for_parallel_build = 65536`, because below it every timing is
single-threaded and there is no defensible RTO — that is a measurement, and it is scheduled in
QC-3, not deferred.

---

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

### 4.2 T37's command producer follows T36's shape — **DECIDED**
*Replaces `D-T37-COMPOSITION-COMMAND-PRODUCER`.* The producer writes role facts in the shape
T36 defines. Building it earlier would ship a command surface whose payload is still moving;
that is sequencing, and the sequence is now stated rather than pending.

### 4.3 Causal coverage is measured in QC-6, not before — **DECIDED**
*Replaces `D-T33-CAUSAL-COVERAGE-UNMEASURED`, `D-QC6-IDENTITY-LIVE-PROOF`.* Both are live
proofs on real data, and QC-6 is where the plan runs them.

### 4.4 T41's relations are not rebuildable from the glossary — **DECIDED, accepted**
*Replaces `D-T41-RELATIONS-NOT-REBUILDABLE`.* The glossary is the SSOT for entities, not edges:
relations and events are extraction-derived. A rebuild restores the entity layer and **must say
so** — `ISOLATED_STACK.md` already documents the resulting graph as entity-complete and
edge-empty. Making relations rebuildable would mean a second SSOT, which is the thing this
refactor exists to remove.

### 4.5 T39 invalidates by event, both caches — **DECIDED**
*Replaces `D-T39-NO-COVERAGE-DIGEST-SOURCE`.* There is no coverage digest and building one is
not worth it: `project_graph_stats` is a full scan and a write-path counter is a schema change
for a cache. **The event-driven invalidation shipped in B9 is the answer for both caches** —
proven in-repo, cheaper than a digest, and it makes the LRU's "never cleared" comment false
rather than tolerated. The TTL stays as the backstop for missed events.

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

### 6.2 Phase 7's engine order is `T42b → T42c → T42 → T42d → T43 → T41` — **DECIDED**
Image, then bootstrap, then the adapter, then the gate that guards it, then the shadow that
measures it, then the swap. **T43's floor may re-block a cutover after new port operations
land, and that is the floor working** — a new operation starts at zero observations.

### 6.3 Phase 8 is `T44 → T45 → T46`, after identity — **DECIDED**
`T46` merges the stores and cannot be done before the id is opaque (§4.1). `T45`'s
scope-dependent valid-time axis (`story_ordinal` | `wall_clock`) is the axis distinction §1.1
relies on; `T44` rewrites the substrate rows those two settle.

### 6.4 Phase 9 closes the plan: `T47 → T48 → T49` — **DECIDED**
Docs (mandatory under the plan's own `Docs: yes`), then `/aif-verify`, then handoff and
archive. **This is how the plan ends**, and it may not begin until every other row is `[x]` or
cites a decision here.

### 6.5 T51 (frontend) follows T38 and T32 — **DECIDED**
The FE renders against the cast read and the spoiler window; migrating it before those settle
would ship surfaces reading a contract that is still moving. T38 is complete (§5.2); T32 is
sequenced in §6.1.

### 6.6 T40 (`entity_facts` partitioning) follows T39 — **DECIDED**
Partitioning is cheap and safe once the caches that read across books are correct by
construction (§4.5); doing it first would move the data under a cache that is still guessing.

## How this file is kept honest

* Every section is cited by the plan row it decides. `plan-final-verification.py` fails a `[~]`
  task that cites nothing.
* A decision that turns out wrong is **struck through with the measurement that killed it**,
  never quietly edited — the same rule the plan uses for its own retractions.
* New questions get a section here on the day they are found. They do not get a deferral,
  because this project does not have deferrals.
