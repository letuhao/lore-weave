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

⚠️ **APPLIED 2026-08-14 (QC-5 C6): the recorded runs FAIL both clauses** — 1 of 3 on clause 1,
and run C is a `5/5` with zero raw findings, which clause 2 exists to make unpassable. Note the
limit honestly: these are the same three runs this section cites as its reason, so the
evaluation scores a rule against its own motivating examples and cannot validate the RULE. It
validates the PIPELINE, and only because the rule fitted to these runs still fails on them. A
fresh three-run measurement on a chapter that did not set the rule is what QC-5 now owes.

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

## How this file is kept honest

* Every section is cited by the plan row it decides. `plan-final-verification.py` fails a `[~]`
  task that cites nothing.
* A decision that turns out wrong is **struck through with the measurement that killed it**,
  never quietly edited — the same rule the plan uses for its own retractions.
* New questions get a section here on the day they are found. They do not get a deferral,
  because this project does not have deferrals.
