# QC-5 — the dogfood acceptance test, run — 2026-08-11

> **Result: FAIL, and not for the reason the plan anticipated.** The acceptance book's
> bi-temporal fact layer is **completely empty** — the canon check has nothing to check against
> for this book, so no re-run of the authoring flow could have produced a meaningful verdict.
> Recorded as a measurement rather than as a deferral, because the answer is determinate.

## What QC-5 asks

> *Re-run the Mị Đế authoring flow end-to-end … **Assert the failure now surfaces:** the trap* <!-- doc-language-gate: ok -- the book title is the cited corpus subject of this acceptance case; translating it would erase the identity the test turns on -->
> *must be attributed to the cast-designated antagonist, **or** the canon check must FAIL —
> `canon_consistency` scoring 5/5 on a misattributed betrayal is the defect, and a pass here
> with 5/5 means the refactor has not landed.*

The criterion is **inverted**: a green run is the failure signal. That makes the substrate
question decisive on its own — if the canon check cannot see roles, a 5/5 is guaranteed and
means nothing.

## The decisive measurement

Book `019f9f2d-f9f1-7037-ba78-8ccc3e19c956` (13 chapters), measured on the dev Postgres:

| | count |
|---|---|
| glossary entities (live) | **32** |
| `entity_facts` — **any** kind | **0** |
| `entity_facts` — `fact_kind='relation'` (roles) | **0** |
| `episodes` | **0** |

For contrast, the fact layer is populated elsewhere — the largest book holds **26 192** facts,
the next **18 620**. So this is not "the feature is unbuilt"; it is **this book was never run
through the fact-producing path.**

## What that means, precisely

1. **The canon check has no substrate for this book.** `fact_for_check` assembles status@P,
   entities, relations and events for the check position. With zero facts and zero episodes
   there is no story-position information at all, so the symbolic guard cannot flag anything
   and the LLM judge is handed an empty context.
2. **A `canon_consistency` of 5/5 on this book would therefore be structurally guaranteed** —
   and the task names exactly that as the defect signal. The refactor has not landed for this
   acceptance case.
3. **Running the full end-to-end authoring flow would not have changed this verdict**, only
   made it more expensive to reach. The flow re-drafts chapters; it does not backfill the fact
   layer for a book that has never had one.

## The role half, which is the case the register actually names

Even with facts present, roles could not be checked at a position: `entity_facts` holds **0**
rows of `fact_kind='relation'` **corpus-wide**, and
`knowledge-service/app/db/neo4j_repos/fact_for_check.py` still documents relations as carrying
datetime validity and being *"NOT position-windowed here"*. That is `D-CANON-CHECK-BLIND-TO-ROLE`
unchanged, and it is what T36 exists to close.

## UPDATE — the fact layer was populated, and the root cause was NOT "nobody ran it"

Chasing the empty substrate produced a better answer than the deferral did.

**The chapters were never published.** All 13 were `editorial_status='draft'`, and extraction
gates on `published` — the start endpoint refuses with *"chapter_range [3,5] matches no
published chapters in this book"*. The comparison book (26 192 facts) is 100/100 published.

**Extraction HAD run on this book — three `chapters` jobs, 2026-07-27/28 — and produced the 32
entities.** So "nobody ran extraction" was wrong. What it never produced was facts.

**There are two writeback callers, and only one can emit facts.** Glossary's contract makes
fact emission conditional: *"ChapterOrdinal … When present (with ChapterID + ContentHash), the
writeback ALSO emits append-only bi-temporal facts … Omitted (legacy caller) → no fact
emission."*

| caller | sends chapter_id / content_hash / chapter_ordinal / writeback_key | can emit facts |
|---|---|---|
| `knowledge-service` `GlossaryClient.propose_entities` | **none of them** | **no** |
| `translation-service` `extraction_worker` | all four | yes |

`glossary_writeback.py` calls `propose_entities(book_id, entities, default_tags,
park_unknown_kinds)` — no chapter context at all. It aggregates candidates **per project**, not
per chapter, so it has no single ordinal to attribute. That is a design mismatch, not a missing
argument.

The correlation across books is exact — a writeback-log row is written on the same
full-payload call:

```
book        writeback_log  episodes  facts
封神演義              129        97   26192     <!-- doc-language-gate: ok -- book id shown as its stored title; the row is corpus evidence -->
(second)               25         0   18620
Mị Đế (before)          0         0       0
```

**A second, unrelated defect surfaced in the same run.** `pass2_writer` discarded every fact
the LLM produced:

```
pass2_writer: skipping fact with unknown type 'description' (...)
pass2_writer: skipping fact with unknown type 'attribute' (...)
persist-pass2 done  entities=4 relations=5 events=0 facts=0 statuses=0
```

`'attribute'` is one of the six kinds `entity_facts_kind_chk` admits — but `pass2_writer`
validates against the **Neo4j** `FactType` literal (`decision | preference | milestone |
negation | statement | commitment`), a completely disjoint vocabulary for a different store.
The two "fact" concepts share a name and nothing else.

### What was run, and the result

Published chapters 3–5 (the three with prose), then enqueued the fact-emitting path —
`POST /v1/extraction/books/{book}/extract-glossary` with `reasoning_effort: "none"` to avoid
the budget burn recorded in `D-T33-CORPUS-BITE-REASONING-MODEL`. Job `019fee56…` **completed**,
3 chapters, no errors.

| | before | after |
|---|---|---|
| `entity_facts` | 0 | **115** — attribute 101, name 13, alias 1 |
| `episodes` | 0 | **3** |
| `extraction_writeback_log` | 0 | **3** |
| glossary entities | 32 | **46** |

Quality, not just quantity:

```
valid_from_ordinal   3 → 41 facts    4 → 27    5 → 47      (all open intervals)
episode citation     115 / 115
```

Every fact carries the story position of the chapter it came from and cites its immutable
episode. **QC-5's substrate precondition is now met.**

## UPDATE 2 — the role half was blind in TWO ways, and only one was known

The section below ("The role half…") said roles could not be checked because `entity_facts`
holds 0 rows of `fact_kind='relation'`. That is true and it is not the binding constraint.

**The axis half is now fixed** (T36). `:RELATES_TO` has carried a story interval since F3, and
`find_relations_for_entity` has taken `as_of_ordinal` since T18 — `fact_for_check` simply never
passed it. Measured on the dev graph before the fix:

```
:RELATES_TO edges total          905
carrying a story position        619
ALREADY CLOSED (valid_to set)    175   ← handed to the canon check as "currently true"
```

**The consumption half is the real blocker, and it was not in the plan.** The canon check reads
only `entities` + `status` from the snapshot — `check_canon` → `gone_cast_in_draft` →
`gone_entities_referenced`, and the judge prompt is built from the draft plus the *gone*
candidates. The snapshot's `relations` reach no prompt and no symbolic rule; nothing in
composition-service consumes them.

So the guard asks exactly one question — *"is a `gone` entity being treated as present?"* —
while QC-5's criterion asks a different one: *"is the trap attributed to the cast-designated
antagonist?"* A correct, well-windowed role payload changes nothing until something reads it.
**A 5/5 here would still be structurally guaranteed**, now for a locatable reason.

**RT-2 is not a blocker and never was:** §9 O7 (sealed 2026-08-09) records that it *dissolves*,
closed by Q2, in scope. Tracked as `D-T36-GUARD-NEVER-ASKS-ABOUT-ROLES`.

## What would make this test meaningful

In order — each is a precondition of the next:

1. **Populate the fact layer for this book** (extraction over its 13 chapters, producing
   episodes + facts). Without this, nothing else is measurable here.
2. **T36** — roles become relation facts with story intervals, so attribution is checkable at
   a position.
3. **RT-2 answered** — the red team left `D-CANON-CHECK-BLIND-TO-ROLE` open as a scope-honesty
   defect: *"either the bible enters scope, or the register row is re-pointed and the claim
   withdrawn."* This is a decision, not work.
4. **Then** re-run the authoring flow and capture what the task names: the plan artifact, the
   drafted chapters, the critic's per-chapter scores, and the glossary delta.

## Reproducing

```
B=019f9f2d-f9f1-7037-ba78-8ccc3e19c956
psql -d loreweave_glossary -c "SELECT fact_kind, count(*) FROM entity_facts
                                WHERE book_id='$B' GROUP BY fact_kind"
psql -d loreweave_glossary -c "SELECT count(*) FROM episodes WHERE book_id='$B'"
psql -d loreweave_glossary -c "SELECT count(*) FROM glossary_entities
                                WHERE book_id='$B' AND deleted_at IS NULL"
```

An empty first result is the finding.
