# CP-0 · V-METRIC — verdict, ROUND 7

*Artifact frozen at `2ef8f0f7f`, working tree clean. Verified 2026-08-04 against `loreweave_chat`
in `infra-postgres-1`. Subject: the instrument, never the feature. No tracked file was modified and
no write of any kind was made to the database — every query below is read-only. This round is
narrow by instruction: the class-3 predicate (handed to me as a decision), the two withheld-`pass`
changes, and a restatement of decision 4.*

**Corpus fingerprint — identical to round 6, to the character**

```
== PIN · corpus fingerprint ==
 messages |            newest             |            corpus_md5
----------+-------------------------------+----------------------------------
     5862 | 2026-08-04 04:58:09.556834+00 | 9cdacf696d9b5ebb6932d3e8e8062d1c
```

`baseline-metrics.frozen.txt` still reproduces byte-for-byte. **This matters more than it looks**:
the corpus has not received a single new row since round 6, which turns out to be the whole of
ruling (a).

---

## 1 · Verdict

| | |
|---|---|
| **OVERALL** | 🔴 **FAIL** — unchanged in outcome. The instrument improved again; the class it is named for still cannot cross the arm boundary. |
| **class 3 · the predicate I was handed** | 🔴 **THE CLASS CANNOT BE DEFINED SOUNDLY FOR A CROSS-ARM COMPARISON.** It *can* be measured on the frozen corpus, and I measured it: **49.9% (834/1,673)**, proven by exhaustive adjudication of all 200 distinct error strings. **40.4% UNDER-counts by 158 rows / 9.5pp** and over-counts nothing. But the predicate that achieves 49.9% cannot leave this corpus, for two structural reasons, one of which is a deliberate security property. **Class 3 must leave the acceptance set, as class 2 did.** |
| **(a) `len(passes) or None`** | 🟡 **CORRECT REPRESENTATION, INERT IN PRACTICE — and 🔴 the change carries a NEW FALSE ATTRIBUTION.** No new record carries a nonexistent pass, but *vacuously*: zero withheld records have been written since the change. `pass: None` is **unreachable from the production write path**. And the 145 records the comment and the test blame on `max(len,1)` are demonstrably not that defect. |
| **(b) the 332 no-pass records** | 🟢 **INERT for every current number.** No baseline number reads `withheld_tools` — `baseline-metrics.sql` contains zero occurrences of the string. They remain a defect of the CP-0.2 column's own completeness claim, unchanged from round 6. |
| **decision 4** | 🔴 **UNCHANGED. 522 unscripted real errors on a frozen side against 748 needed per arm. Deficit 226.** And the coupling now closes: the only class with a reachable bound is the class I have just ruled unscoreable. |

---

## 2 · CLASS 3 — the decision I was handed

The builder made three attempts (47.0% → 62.1% → 54.7%), reverted to `not found OR uuid OR
placeholder` = **40.4%**, and left the predicate open. It was right to stop. It was reaching for a
better `LIKE` pattern, and no `LIKE` pattern is the answer — but not for the reason it thought.

### 2.1 The move that ends the guessing: the population is enumerable

```
== R7-1 · how many DISTINCT error texts back the 1673 rows? ==
 rows | distinct_errors | null_errors
------+-----------------+-------------
 1673 |             200 |           0
```

**1,673 rows over 200 distinct strings, no NULLs.** Nobody in six rounds had counted this. 200
strings is *readable*. The class never needed a cleverer pattern — it needed somebody to read the
population once and write down the answer. I did that, keyed on the deterministic rank
`row_number() OVER (ORDER BY count(*) DESC, min(error))`, so every assignment is auditable against
the listing (query `R7-2`, all 200 rows, reproduced in §7).

Four labels, defined before I looked at any count:

- **`ID_INVALID`** — a *named* identifier argument was supplied with a syntactically invalid,
  fabricated, or placeholder value. *The model produced something that is not an id.*
- **`ID_UNRESOLVED`** — a supplied identifier did not resolve to an existing/accessible object.
- **`ID_MISSING`** — a required *identifier* argument was absent, or no scope id could be resolved.
- **`NOT_ID`** — everything else.

Plus four **contested** buckets I refuse to fold in silently, itemised in §2.4.

```
== R7-3 · TOTALITY + DISJOINTNESS control ==
 distinct_strings | rows_covered | unlabelled
------------------+--------------+------------
              200 |         1673 |          0

== R7-4 · the adjudication, by label ==
        label         | distinct_strings | rows | pct_of_denom
----------------------+------------------+------+--------------
 ID_INVALID           |               14 |  473 |         28.3
 NOT_ID               |              111 |  470 |         28.1
 ID_UNRESOLVED        |               21 |  361 |         21.6
 ID_MISSING           |               38 |  302 |         18.1
 CONTESTED_NAME       |                3 |   25 |          1.5
 CONTESTED_TYPEWRAP   |                9 |   20 |          1.2
 CONTESTED_DICTWRAP   |                2 |   20 |          1.2
 CONTESTED_CROSSSTORE |                2 |    2 |          0.1
```

Every string labelled exactly once; every row accounted for.

### 2.2 What 40.4% actually does — it is a *recall* failure, not the precision failure I found in round 6

```
== R7-5 · PUBLISHED predicate (not found | uuid | placeholder) vs the adjudication ==
        label         | selected_by_published | missed_by_published | total
----------------------+-----------------------+---------------------+-------
 ID_INVALID           |                   472 |                   1 |   473
 NOT_ID               |                       |                 470 |   470
 ID_UNRESOLVED        |                   204 |                 157 |   361
 ID_MISSING           |                       |                 302 |   302
 CONTESTED_NAME       |                       |                  25 |    25
 CONTESTED_TYPEWRAP   |                       |                  20 |    20
 CONTESTED_DICTWRAP   |                       |                  20 |    20
 CONTESTED_CROSSSTORE |                       |                   2 |     2

== R7-6 · control: published selection totals 676 ==
 published_numerator | denom
---------------------+-------
                 676 |  1673
```

**Zero of the 676 published rows are `NOT_ID`.** The predicate is now *perfectly precise*. Round
6's finding — 85 `unknown kind` rows admitted by our own help text, 5 admitted because `valid` ends
in `id` — is **fully closed, and I withdraw the RED I placed on the numerator's precision.** The
builder's three "failed" attempts were failures of recall dressed up as failures of precision, and
its instinct to stop rather than tune toward my figure was correct.

What it misses:

```
== R7-7 · the 157 ID_UNRESOLVED rows the published predicate MISSES ==
 n  | err
----+--------------------------------------------------------------------------
 72 | entity not accessible
 47 | book not accessible
 33 | no active chapter with that chapter_id in this book — check the chapter_id
  3 | no live row with that code in this book
  2 | none of the given entities are live in this book
```

Five product sentences, 157 rows, every one of them an identifier that did not resolve. Plus one
`ID_INVALID` (`project_id must be a valid id`) and the whole of `ID_MISSING`.

**Answer to the question I was asked, stated plainly: 40.4% UNDER-counts.** By **158 rows / 9.5
percentage points** against the core reading, and by **460 rows / 27.5pp** against the broad one. It
over-counts by nothing.

### 2.3 The predicate, and the figure

A predicate that reproduces the adjudication exactly:

```sql
error ILIKE '%uuid%' OR error ILIKE '%not found%'  OR error ILIKE '%placeholder%'
OR error ILIKE '%not accessible%'          OR error ILIKE '%must be a valid id%'
OR error ILIKE '%no active chapter%'       OR error ILIKE '%no live row with that code%'
OR error ILIKE '%are live in this book%'
```

```
== R7-8 · CANDIDATE GENERALIZABLE CORE predicate, scored against the adjudication ==
        label         | selected | missed | total
----------------------+----------+--------+-------
 ID_INVALID           |      473 |        |   473
 NOT_ID               |          |    470 |   470
 ID_UNRESOLVED        |      361 |        |   361
 ID_MISSING           |          |    302 |   302
 ...contested         |          |     67 |    67
```

**Perfect precision and perfect recall on the core: 834 selected, 0 false positives, 0 misses.**

```
== R7-10 · THE FIGURE: class 3 under each defensible reading ==
 denom | published_num | published_pct | core_num | core_pct | broad_num | broad_pct | widest_num | widest_pct
-------+---------------+---------------+----------+----------+-----------+-----------+------------+------------
  1673 |           676 |          40.4 |      834 |     49.9 |      1136 |      67.9 |       1203 |       71.9
```

| reading | numerator | denominator | value |
|---|---|---|---|
| **published** | 676 | 1,673 | **40.4%** |
| **CORE — invalid id + unresolved id** *(my ruling)* | 834 | 1,673 | **49.9%** |
| broad — core + a required *identifier* argument absent | 1,136 | 1,673 | **67.9%** |
| widest — broad + all four contested families | 1,203 | 1,673 | **71.9%** |

**I rule the core, 49.9%, as the figure this corpus supports for "identifier resolution."**

### 2.4 Why I decline to fold in `ID_MISSING`, and the contested families

I could have taken 67.9% and it would have looked more decisive. I am not taking it, because
`ID_MISSING` cannot be separated from content-argument failures by anything except reading the
field name — and the two sit adjacent at identical volume:

```
110 | validating "arguments": validating root: required: missing properties: ["book_id"]   ← identifier
110 | validating "arguments": validating root: required: missing properties: ["query"]     ← content
```

Same producer, same sentence, same count, opposite classification. Whether `code`, `model_ref`,
`provider_credential_id`, or `base_version` is "an identifier" is a judgement I would be making on
the metric's behalf. **"Failed to supply an id" is also a different failure from "supplied an id
that did not work"** — the class is named *resolution*. I report 67.9% so nobody has to recompute
it, and I decline to publish it.

The four contested families, reported and excluded, with the reason:

| family | rows | why excluded |
|---|---|---|
| `CONTESTED_TYPEWRAP` — `project_id: Input should be a valid string (you sent a list)` | 20 | the id **value was correct**; the model wrapped it in a list. `['019efae6-3797-…']` is a shape failure, not a resolution failure. |
| `CONTESTED_DICTWRAP` — `jobs_get — 'service': Field required (you sent a dict)` | 20 | whole-args dict-wrap: **every** field reads missing, including non-identifiers (`service`, `target_language`). Round 6 flagged this; it stands. |
| `CONTESTED_NAME` — `unknown subagent 'universal'`, `unknown tool` | 25 | a **capability** name failed to resolve, not an object id. Same family as `unknown kind`, which I ruled out in round 6. |
| `CONTESTED_CROSSSTORE` — `edge endpoint(s) are not yet graph nodes: <uuid>` | 2 | the id resolved in the source store; the object is absent from the *target* store. |

### 2.5 🔴 The ruling that matters — the predicate cannot leave this corpus

49.9% is the right number **for the frozen side**. It is not a predicate that can score the new arm,
and the checkpoint's entire purpose is a cross-arm comparison. Three independent reasons, in
increasing order of how permanent they are.

#### (a) 19% of the numerator rests on verbatim product sentences

```
== R7-20 · how much of the CORE numerator rests on VERBATIM PRODUCT SENTENCES? ==
 generic_clauses | fitted_product_sentences | core_total
-----------------+--------------------------+------------
             676 |                      158 |        834
```

Five of the eight clauses are literal sentences the product happens to emit today. I did not derive
them; I **fitted** them, to 200 strings I had already read. That is the ordinary risk. What makes it
concrete is the next point.

#### (b) The vocabulary already changed once, mid-corpus, and the metric moved with it

```
== R7-21 · VOCABULARY INSTABILITY, observed IN this corpus ==
                      variant                       | rows | first_seen | last_seen
----------------------------------------------------+------+------------+------------
 old string: book not accessible                    |   47 | 2026-07-12 | 2026-08-04
 new string: no active chapter with that chapter_id |   33 | 2026-07-26 | 2026-07-26
```

`SESSION_HANDOFF.md:5646` records the change: *"explicit `errChapterNotInBook` on grant-passed
chapter lookups (was a misleading 'book not accessible' that made the agent give up)"*. A **product
improvement** — a clearer error message — silently created 33 rows of a new string that the
published predicate catches under no clause at all.

This is the standing question answered in the affirmative, from the corpus's own history:
**rewording an error string moves this metric, with no change in behaviour and no diff anywhere in
the derivation.** The number would look better if the thing being measured were merely *renamed*.

#### (c) The anti-oracle — 239 of 361 unresolved rows are indistinguishable from authorization failures, **by design**

```
== R7-9 · ID_UNRESOLVED split by whether the string is an ANTI-ORACLE merge ==
                          kind                           | distinct_strings | rows
---------------------------------------------------------+------------------+------
 anti-oracle merged (exists? / yours? indistinguishable) |               14 |  239
 unambiguous non-resolution                              |                7 |  122
```

`services/chat-service/app/services/jobs_skill.py:30-34` states the policy:

> *"Owner-scoped, always — a missing job and someone else's job look identical … If a
> `service`+`job_id` doesn't exist OR belongs to someone else, both cases return the SAME
> `{"success": false, "error": "not found or not accessible"}` (an **anti-oracle, deliberate**)"*

and `services/book-service/internal/api/mcp_server.go:31`:

> *"uniform caller-visible errors (H13 — **no existence oracle**)"*

**66% of the unresolved-identifier numerator comes from strings the product deliberately refuses to
disambiguate.** This is not a predicate defect and it is not fixable by a better pattern: it is a
security property, correctly implemented, that makes class 3's numerator permanently a *blend* of
identifier failures and authorization failures in an unknown ratio. No amount of care in the SQL
can separate them, because the bytes do not carry the distinction.

(In fairness to the class, `stream_service.py:1634-1640` documents that the dominant *cause* here is
id hallucination — *"a weak model invents a VALID-but-WRONG book_id, which `_gate` then refuses as
'not found or not accessible'"*. So the blend is probably identifier-heavy. **Probably** is the
problem. That is an impression, which is the thing CP-0 exists to replace.)

#### The root cause, and it is not the predicate

The 200 strings come from at least five producers with five unrelated vocabularies for the same
semantic failure — chat-service validators (`entity_id must be a UUID`), the Go glossary service
(`validating "arguments": … missing properties: […]`), pydantic (`Field required [type=missing]`),
the `loreweave_mcp` wrapper (`invalid arguments for X — 'field': Field required (you sent a dict)`),
and composition-service (`Error executing tool X: not found or not accessible`). **Class 3 is a
regex over freeform prose emitted by five independent teams.** Every round of this checkpoint has
been an attempt to regex-match a contract that was never written down.

CP-0 added `tool_calls[].source`, `latency_ms`, `runtime_variant` and a mandatory outcome. **It did
not add an error class or code.** So class 3 will be exactly as unmeasurable on the new arm as it is
on the old one, and the two arms' predicates will drift independently as five teams reword five
error vocabularies.

### 2.6 Population contamination — unchanged and still decisive

```
== R7-11 · the corrected class by SCRIPTED / UNSCRIPTED ==
    pop     | real_errors | core | core_pct | broad | broad_pct | published | published_pct
------------+-------------+------+----------+-------+-----------+-----------+---------------
 scripted   |        1151 |  693 |     60.2 |   968 |      84.1 |       565 |          49.1
 unscripted |         522 |  141 |     27.0 |   168 |      32.2 |       111 |          21.3
```

**68.8% of the denominator is scripted harness traffic**, and the corrected class reads **60.2% on
the harness against 27.0% on real usage** — a 2.2× split that decides the published figure. Correcting
the predicate did not fix this; it widened the gap.

### 2.7 Ruling on class 3

**🔴 The class cannot be defined soundly for the comparison CP-0 exists to enable. It must leave the
acceptance set, exactly as class 2 did.**

Stated precisely, so this is not mistaken for a smaller finding:

1. On the **frozen corpus**, class 3 is **49.9% (834/1,673)**, adjudicated string-by-string over all
   200 distinct errors, totality and disjointness proven. The published **40.4% under-counts by 158
   rows (9.5pp)** and over-counts by nothing.
2. That figure is **not portable to the new arm**. 19% of it rests on fitted product sentences; the
   vocabulary demonstrably changed once already inside this corpus, costing 33 rows invisibly; and
   66% of the unresolved bucket is merged with authorization failures by a deliberate anti-oracle.
3. Therefore any cross-arm delta on class 3 is uninterpretable: an apparent improvement is equally
   well explained by a reworded error string or a changed grant, neither of which is the runtime.

**This is the answer the brief anticipated** — *"if the class cannot be defined soundly on this
corpus, say that instead."* It can be *measured* here; it cannot be *compared* across arms. For an
acceptance gate, those are the same failure.

**What would change my ruling:** a structured `tool_calls[].error_class` written by all five
producers against one enum, with the anti-oracle emitting an explicit `unresolved_or_forbidden`
class that admits the merge instead of hiding it. Then the class becomes scoreable and 49.9% becomes
its baseline. Nothing short of that does.

---

## 3 · Ruling (a) — `max(len(passes), 1)` → `len(passes) or None`

### 3.1 No new record carries a nonexistent pass — vacuously

```
== R7-12 · withheld records vs the passes their turn actually recorded ==
 withheld_records | key_absent | explicit_null | numeric_pass | pass_exceeds_passes | pass_on_turn_with_no_passes
------------------+------------+---------------+--------------+---------------------+-----------------------------
             1565 |        332 |             0 |         1233 |                 145 |                           0

== R7-13 · partitioned by whether the record predates the explicit-null fix ==
             era             | records |            first             |             last              | explicit_null | impossible_pass
-----------------------------+---------+------------------------------+-------------------------------+---------------+-----------------
 no explicit null exists yet |    1565 | 2026-08-04 00:24:57.84167+00 | 2026-08-04 04:58:09.556834+00 |             0 |             145
```

**`explicit_null = 0`.** Not one record in the corpus carries `"pass": null`. The last withheld
record is written at `04:58:09.556834` — which *is* the corpus's newest message. **No traffic at all
has been recorded since the change.** So "no NEW record carries a nonexistent pass" is true, and
true for the reason that there are no new records. The fix has **zero live evidence**, and a
verifier who reported it GREEN on this basis would be certifying an empty set.

### 3.2 🔴 `pass: None` is unreachable from the production write path

There is exactly one recorder and exactly two write call sites:

```
$ grep -rn "AdvertisedToolsRecorder()" services/chat-service/app/
  stream_service.py:6423

$ grep -rn "\.record_withheld" services/chat-service/app/
  stream_service.py:6828
  stream_service.py:6832
```

Both sit inside the same branch, **after** `record_pass` (`stream_service.py:6818-6834`):

```python
_adv_ev = chunk_data.get("advertised")
if _adv_ev is not None:
    _advertised.record_pass(_adv_ev.get("names") or [], ...)   # 6820  ← len(_passes) becomes >= 1
    while _surface_sink:                                       # 6826
        _sw = _surface_sink.pop(0)
        _advertised.record_withheld(...)                       # 6828
    for _w in (_adv_ev.get("withheld") or []):
        _advertised.record_withheld(...)                       # 6832
```

By the time either call runs, `len(self._passes) >= 1` **always** — `record_pass([])` still appends.
So `len(self._passes) or None` can never evaluate to `None` in production. The only path that
produces an explicit null is the unit test at `test_cp0_instrument.py:314-318`, which calls
`record_withheld` directly on a fresh recorder.

The implementation comment (`instrument.py:358-359`) says *"when a pass 1 later arrives the drain
re-stamps against it."* **There is no re-stamp.** `record_pass` never touches `_withheld`. What is
actually true — and is the correct and better fact — is that the **drain is ordered after
`record_pass`**, so the stamp is computed with the pass already counted. The outcome is right; the
stated mechanism does not exist.

And the case the fix claims to cover is handled **worse** than the comment says. A turn that never
advertises never enters the `_adv_ev is not None` branch, so the sink is **never drained at all**:
`_withheld` stays empty, `withheld_json()` returns `None`, and those narrowings are **silently
discarded** — not stamped null. A lost record is strictly worse than an honest one, and it is the
real behaviour for exactly the scenario the change was written for.

### 3.3 🔴 The 145 are not the defect the fix names

```
== R7-14 · the 145 impossible-pass records ==
   msg    |          created_at           | passes_recorded | pass_claimed |    stage     | records
----------+-------------------------------+-----------------+--------------+--------------+---------
 d0c8c43b | 2026-08-04 01:50:42.659958+00 |               2 |            3 | token_budget |      47
 18fd5eb4 | 2026-08-04 01:56:48.193117+00 |               2 |            3 | token_budget |      98
```

`instrument.py:353-356` and `test_cp0_instrument.py:309-313` both state:

> *"`max(len, 1)` fabricated a pass 1 for narrowings on turns where **no pass was ever recorded**,
> producing **145** records stamped at a pass that does not exist."*

**That is false on all three observable properties of those 145 records:**

| the claim | the records |
|---|---|
| stamped **pass 1** | stamped **pass 3** |
| on turns that **never advertised** | on turns with **2 recorded passes** |
| by the pre-pass sink (`hot_seed`) | stage is **`token_budget`** |

The 145 are the `len + 1` **off-by-one** — the defect the *adjacent* comment at `instrument.py:344-349`
correctly describes and which was fixed separately. The count `145` was carried across from a true
finding and re-attached to a different cause.

This is the repository's own recorded trap, committed fresh into a test docstring: *a number that
survives by being repeated*. It is the same failure mode as the `65.7%` that `baseline-metrics.sql`
was written to stop, and it now sits in the test file that is supposed to be the guard.

### 3.4 Ruling on (a)

**🟡 The representation is right. The change is inert. The attribution is wrong.**

- **Is explicit null the right representation?** **Yes**, and unambiguously so. `null` is the honest
  answer to "which pass did this narrowing shape?" when no pass exists, and it is strictly better
  than a fabricated `1`, which — as round 6 established — reads downstream as a *confirmed*
  withholding. `withheld_json`'s reconciliation treats `None` and a missing key identically
  (`by_pass.get(w.get("pass"), set())` → empty → always keep), so nothing downstream breaks.
- **Does it change any number?** No. It cannot fire in production, and if it could, the
  reconciliation behaves identically either way. It removes a false claim from a future corpus; it
  removes nothing from this one.
- **Does it clean the 145?** No. Those are a different defect with a different cause, and the code
  now asserts otherwise in two places.

**Falsifier, executable by a later round:** run `R7-12` after any new traffic. `explicit_null > 0`
proves the path is reachable and I withdraw §3.2. `pass_exceeds_passes > 145` proves a live
regression. Both are `0` and `145` today, against a corpus that has not grown.

---

## 4 · Ruling (b) — the 332 records that carry no `pass` at all

### 4.1 They cannot contaminate any current number, and I can show it exhaustively

`withheld_tools` is read in exactly three files across the entire repository:

```
$ grep -rln "withheld_tools" --include=*.sql --include=*.py --include=*.go --include=*.ts --include=*.tsx
  services/chat-service/app/db/migrate.py            ← DDL
  services/chat-service/app/services/stream_service.py ← the write site
  services/chat-service/tests/test_cp0_instrument.py ← tests

$ grep -c "withheld" contracts/agent-runtime-baseline/baseline-metrics.sql
  0
```

**Zero occurrences in the derivation.** The four baseline classes read `chat_messages.tool_calls`,
`finish_reason`, `outcome`, `is_error`, and `chat_sessions.title`, and nothing else. No published
number can move by one row on account of the 332 — nor of the 145, nor of the whole `withheld_tools`
column. I verified this by enumerating the column's consumers rather than by inspecting the SQL and
concluding it "looked like" it did not read the column.

### 4.2 What they *do* contaminate

They are not inert with respect to the claim CP-0.2 makes about itself. All 332 predate the `pass`
key (`00:24:57 → 00:53:12`, per round 6's `R7`-equivalent), and **30 of them name a tool that is
advertised somewhere in the same turn** — a contradiction that can never be resolved, because the
field that would resolve it did not exist when they were written. With the 145, that is
**477 of 1,565 withheld records (30.5%) uninterpretable or unreconcilable**, unchanged from round 6.

### 4.3 Ruling on (b)

**🟢 INERT HISTORICAL ROWS for every one of the four baseline numbers**, proven by enumerating the
column's consumers, not by inspection. The builder may treat them as history.

**🔴 They remain a live defect of the CP-0.2 column's own completeness**, and the builder may not
describe `withheld_tools` as clean while 30.5% of it cannot be reconciled by construction. That is a
property of the frozen artifact, not of the current code — and it is the second consecutive round in
which I have had to say the same sentence.

---

## 5 · Decision-4 restatement, against the current predicate

```
== R7-0 · denominator + scripted split control ==
 denom | scripted | unscripted
-------+----------+------------
  1673 |     1151 |        522

== R7-15 · UNSCRIPTED real-error supply rate ==
 unscripted_real_errors |   first    |    last    | per_week
------------------------+------------+------------+----------
                    522 | 2026-05-18 | 2026-08-04 |     47.1

== R7-16 · class 1 carry-forward on UNSCRIPTED real errors ==
 unscripted_real_errors | carry | pct
------------------------+-------+------
                    522 |    53 | 10.2
```

```
== R7-17 · two-proportion sample size, alpha=.05 two-sided, power=80% ==
target                                          n/arm  supply/wk  weeks/arm
class1 carry-forward  6.0% -> 3.0% (halve)      748.4       47.1       15.9
class1 UNSCRIPTED    10.2% -> 5.1% (halve)      425.2       47.1        9.0
class3 PUBLISHED     40.4% -> 20.2% (halve)      80.1       47.1        1.7
class3 CORE          49.9% -> 24.9% (halve)      57.6       47.1        1.2
class3 BROAD         67.9% -> 34.0% (halve)      32.9       47.1        0.7
class3 CORE unscript 27.0% -> 13.5% (halve)     137.9       47.1        2.9

== R7-18 · the FROZEN side holds 522 unscripted real errors and cannot grow ==
  class1 carry-forward  6.0% -> 3.0%    n/arm=  748.4   DEFICIT 226.4
```

**Restated: the frozen side holds 522 unscripted real errors against 748 needed per arm. Deficit
226.** (Round 6 said 743.2 against the same 522; the 5-row difference is my z-value, and the
conclusion is identical.) The frozen side is frozen — **no future traffic adds to it.** Halving
carry-forward on unscripted traffic is **not detectable against this baseline, ever, not slowly.**
It becomes reachable only by scoring against the full 1,673, of which **68.8% is harness traffic** —
i.e. by measuring the harness.

**And the correction to class 3 tightens the trap rather than loosening it.**

| class | status | n/arm to halve |
|---|---|---|
| 1 · carry-forward | 🟢 sound | **748** — supply 522, permanently short |
| 2 · not-a-real-dispatch | ⛔ *not scoreable across arms* (declared by the run itself) | — |
| 3 · identifier resolution | ⛔ **not scoreable across arms — this round's ruling** | **58** — the only reachable bound in the set |
| 4 · no-recorded-outcome | 🟢 sound, and **0.0%** | no improvement is expressible |

**The only class whose bound this product's traffic can reach is the only class that cannot be
compared across arms.** That coupling has now survived four rounds, and this round closes it in the
worst direction: I resolved class 3's number and the resolution is what disqualifies it.

Finally, the new side is still empty:

```
== R7-19 · the NEW arm: rows by runtime_variant ==
 runtime_variant | assistant_turns | turns_with_tool_calls
-----------------+-----------------+-----------------------
 legacy          |            2720 |                  1014
```

**One value. Zero rows on the arm the comparison is with.** Trap 4 from the brief — *"the comparison
that cannot be computed"* — remains unfalsified after seven rounds.

---

## 6 · Stated falsifier

**What I looked for that would have made each ruling go the other way.**

1. **Class 3.** I set out to *hand the builder a working predicate*, which is what I was asked for,
   and I built one: `R7-8` achieves perfect precision and perfect recall on 834 rows. **Had it
   generalized, this would have been GREEN at 49.9%** and the class would have closed. I then tried
   to break my own predicate and succeeded three ways: 158 of its 834 rows come only from fitted
   product sentences; the corpus contains a mid-corpus rename that already cost 33 rows silently;
   and 239 rows sit behind a deliberate anti-oracle that merges "does not exist" with "not yours."
   **Overturned by:** a structured `error_class` enum on `tool_calls[]`, written by all five
   producers. Not by a better regex — I have now demonstrated that the best possible regex is
   insufficient, which is a stronger statement than any of my previous three RED rulings.

2. **Round 6's numerator RED — WITHDRAWN.** I looked for the 90 bad rows again and they are gone:
   `R7-5` shows **zero** `NOT_ID` rows in the published 676. I record this as a full withdrawal, not
   a grudging one; the builder fixed precisely what I asked and its instinct to stop tuning was
   right.

3. **Ruling (a).** I set out to confirm the fix GREEN. **Overturned by** finding `explicit_null = 0`
   against a corpus with no new rows, then tracing both write call sites and establishing that
   `pass: None` cannot be reached in production, then querying the 145 and finding they claim pass 3
   on 2-pass turns at `token_budget` — contradicting the cause the code and the test now assert.
   **Re-overturned by:** any row with `"pass": null`, or any evidence that `record_withheld` is
   reachable before `record_pass`. Query `R7-12`.

4. **Ruling (b).** I set out to prove the 332 contaminate a published number, because that is the
   more damaging answer. **A single occurrence of `withheld` in `baseline-metrics.sql` would have
   done it.** There are zero, and the column has exactly three consumers, none of them a metric.
   I ruled against my own preferred finding.

5. **Decision 4.** **Overturned by:** unscripted real errors on the frozen side exceeding 748. They
   number 522 and the side is frozen, so no observation can ever overturn it. That is the finding.

---

## 7 · Appendix — the adjudication key

The full 200-string listing (`R7-2`) and the label assignment are reproducible with:

```sql
CREATE OR REPLACE TEMP VIEW _errk AS
SELECT error, count(*) AS n,
       row_number() OVER (ORDER BY count(*) DESC, min(error)) AS k
FROM _real GROUP BY error;
```

with `_real` = the class-3 denominator exactly as `baseline-metrics.sql` defines it. Label
assignment by rank `k`:

| label | ranks |
|---|---|
| `ID_INVALID` | 1, 6, 10, 29, 38, 45, 56, 89, 90, 91, 116, 147, 164, 200 |
| `ID_UNRESOLVED` | 4, 5, 7, 8, 11, 17, 18, 27, 28, 35, 43, 51, 55, 69, 76, 86, 102, 130, 134, 138, 141 |
| `ID_MISSING` | 2, 12, 15, 16, 19, 25, 31, 33, 36, 37, 42, 50, 61, 67, 71, 72, 73, 78, 83, 84, 87, 88, 93, 94, 103, 104, 112, 113, 115, 119, 120, 126, 127, 128, 131, 132, 140, 148 |
| `CONTESTED_TYPEWRAP` | 57, 58, 65, 70, 85, 122, 129, 150, 152 |
| `CONTESTED_DICTWRAP` | 21, 153 |
| `CONTESTED_NAME` | 14, 167, 168 |
| `CONTESTED_CROSSSTORE` | 143, 144 |
| `NOT_ID` | all remaining 111 ranks |

Totality and disjointness are asserted by `R7-3` (200 / 1,673 / 0 unlabelled) and must be re-run
before the mapping is reused — the rank key is stable only at corpus fingerprint
`9cdacf696d9b5ebb6932d3e8e8062d1c`.

---

*Authority exercised. I rule **class 3 not scoreable across arms** and hold that it must leave the
acceptance set, as class 2 already has. Any PASS resting on a cross-arm class-3 delta is void. On
the frozen side alone the class is **49.9% (834/1,673)** — the published **40.4% under-counts by
158 rows, 9.5 percentage points**, and over-counts by nothing.*

*I **withdraw** round 6's numerator RED in full. The 85 `unknown kind` rows and the 5 rows admitted
because `valid` ends in `id` are gone, and the predicate is now perfectly precise. The builder's
decision to stop after three attempts rather than tune toward my figure was the correct call, and I
record that its three "failures" were failures of recall it had diagnosed as failures of precision —
which is why more tuning would not have converged.*

*I rule the `pass` representation **correct and inert**: an explicit null is the right way to say
"no pass existed", it is strictly better than a fabricated 1, and it cannot be produced by the
product — both `record_withheld` call sites run after `record_pass`. I rule the **attribution
false**: the 145 impossible-pass records claim pass 3 on 2-pass turns at stage `token_budget`, and
the comment and test that now blame `max(len,1)` for them are wrong on all three observable
properties. A true count re-attached to the wrong cause is how `65.7%` survived four rounds, and it
has just been written into the guard.*

*I rule the 332 no-pass records **inert for every published number**, proven by enumerating the
three consumers of `withheld_tools` and confirming the derivation contains the string zero times.*

*Recorded in fairness: this checkpoint's instrument has improved in every round I have verified, and
this round's class-3 numerator is the cleanest the metric has been. The finding is not that the
builder failed to write the predicate. It is that the predicate was never writable — class 3 is a
regex over freeform prose emitted by five independent producers, two of which deliberately refuse to
say what happened. The number CP-0 is named for cannot be compared across arms until the error
carries a class instead of a sentence, and the comparison the checkpoint exists to enable still has
zero rows on its new side.*
