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
