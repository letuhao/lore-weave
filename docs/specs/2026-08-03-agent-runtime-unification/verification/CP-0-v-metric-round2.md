# CP-0 · V-METRIC — verdict, ROUND 2

*Artifact frozen at `e75ad5d7d`. Verified 2026-08-04 against `loreweave_chat` in `infra-postgres-1`.
Subject: the instrument, never the feature. No tracked file was modified.*

---

## 1 · Verdict

| | |
|---|---|
| **OVERALL** | 🔴 **FAIL** |
| **1 · is each new field answerable, and unanswerable today?** | ⚖️ **PARTIAL PASS** — the seven fields are genuinely absent from the corpus (18 of 7,465 recorded calls carry `source`/`latency_ms`/`declaration`; 16 of 5,754 rows carry `advertised_tools`). One new caveat: `declaration` is byte-identical to `tool` in **18 of 18** live rows, and the baseline side of the matched pair carries **no `declaration` at all** — so the join the field exists for still runs on tool name. Round 1's `withheld_tools` findings were not re-litigated here. |
| **2 · is the baseline reproducible from the snapshot alone?** | 🔴 **FAIL** — the catalog snapshot is real and self-verifying (sha recomputes; arms rebuild from it). The **metrics** derivation is *reproducible today* but **not frozen**: its only input is the live, mutable `loreweave_chat`, with no row pin, no `AS OF` cut-off, and a §5 block keyed on `now()`. `baseline-metrics.frozen.txt` is a frozen **output** of an unfrozen **input**. |
| **3 · is the sample contaminated, and are the four numbers recomputable?** | 🔴 **FAIL** — all four numbers recompute bit-for-bit, and **three of the four are unsound as stated**. Carry-forward 12.6% discards the call ordering the schema records (order-respecting value **39.4%**). Not-a-real-dispatch 16.1% omits the single largest breaker string in the corpus (wider lower bound **42.4%**). No-interpretable-outcome 90.7% is a **column-age artifact**. And the decontamination the header declares is not the one the view implements: it cites 57.4% harness and removes **29.4%**, leaving **1,124 harness failures (39.6%)** inside the population it calls "organic", plus **1,174 blank-argument calls** the header says are excluded and no predicate excludes. |
| **4 · what bound does the data actually support?** | 🔴 **FAIL** — the power arithmetic checks out, and the pooled design **relocates the problem rather than solving it**. The reachability column attributes the *whole product's* traffic to the new arm, which by construction only receives calls to admitted declarations. The declared first declaration `book_list` carries **42 calls / 11 failures** in the entire unscripted corpus — **0.99 failures/week, 6.5 years** to n=334. The pool must carry **≈36% of all product failures** before the gate can open in eight weeks. |

**Round 1's findings: partially resolved, and two were answered in the wrong direction.** The missing
derivation now exists — that was round 1's decision-2 core and it is fixed. But round 1 identified
carry-forward's published 61.8% as *the loosest of four readings* and named the literal
order-respecting reading at 57.1%; the response adopted a **fifth, narrower** reading (earlier
*message* only), which round 1 had already tabulated at 8.8%, and labelled it "strict: success
STRICTLY EARLIER". And round 1 measured our-own-prose at 57.7% with a predicate that included
`%You have already called%`; the new derivation **drops that clause** and reports 16.1%.

### The falsifier — what I looked for that would have made this PASS

I set out to be wrong about the ordering objection. If `_calls` had carried a within-turn ordinal —
or if intra-turn successes were provably absent — the 12.6%/39.4% gap would collapse and class 1
would stand. I ran the ordinal-respecting query (§4.1 Q-O/Q-V): **1,116 of 2,835 organic failures**
follow an earlier success *in the same assistant turn*, recorded, ordered, and discarded. It did not
collapse.

I also set out to be wrong about class 2. If the failures the committed predicate misses had been
genuine service errors that merely mention "this turn", 16.1% would be a defensible lower bound. I
printed all 15 distinct missed strings (§4.2 Q-N). Every one is our own middleware prose.

Third: if `finish_reason` had existed across the whole corpus, 90.7% would be a real measurement of
a real failure mode. It was added on **2026-07-19**; before it, 100% unclassified; after it, **4.6%**
— already inside the "<5%" target the acceptance table sets (§4.4 Q-T).

**A PASS was available on decision 2 and I withheld it**: the derivation reproduces exactly. I
withheld it because reproducing today is not freezing, and the file's own §5 is keyed on `now()`.

---

## 2 · Decision 1 — answerable, and unanswerable today

```sql
SELECT count(*) FILTER (WHERE advertised_tools IS NOT NULL) AS advertised_rows,
       count(*) FILTER (WHERE withheld_tools   IS NOT NULL) AS withheld_rows,
       count(*) FILTER (WHERE outcome          IS NOT NULL) AS outcome_rows,
       count(*) FILTER (WHERE runtime_variant <> 'legacy')  AS non_legacy_rows,
       count(*) AS all_rows FROM chat_messages;
```
```
 advertised_rows | withheld_rows | outcome_rows | non_legacy_rows | all_rows
-----------------+---------------+--------------+-----------------+----------
              16 |             2 |           16 |               0 |     5754
```
```sql
SELECT count(*) AS calls,
  count(*) FILTER (WHERE tc ? 'source') AS has_source,
  count(*) FILTER (WHERE tc ? 'latency_ms') AS has_latency,
  count(*) FILTER (WHERE tc ? 'declaration') AS has_declaration
FROM chat_messages m CROSS JOIN LATERAL jsonb_array_elements(m.tool_calls) tc
WHERE m.tool_calls IS NOT NULL;
```
```
 calls | has_source | has_latency | has_declaration
-------+------------+-------------+-----------------
  7465 |         18 |          18 |              18
```

No pre-existing column answers these. `chat_sessions.enabled_tools` / `activated_tools` exist but are
**session-level** (30 / 20 sessions of 829) and cannot record a per-pass advertised set, which is the
one thing arm E's silent deletion requires. Fields are new. **Not instrumentation debt.**

**The caveat, and it bears on decision 4.** Every live row has `declaration == tool`:

```
        tool         | source  |     declaration     |   rv   | latency | inferred
---------------------+---------+---------------------+--------+---------+----------
 tool_list           | meta    | tool_list           | legacy |         | true
 book_list           | tool    | book_list           | legacy | 78      |
 book_read           | tool    | book_read           | legacy | 71      |
 …                   |         |                     |        |         |
 book_list           | breaker | book_list           | legacy |         | true
```

`declaration` stops duplicating `tool` only once consolidation begins (CP-4). Until then it is a
copy. More importantly, the **pre-CP-0 side carries none**, so the matched pair joins on tool name —
and the run's own binding consequence #2 confirms the supersession edge that would make the join
meaningful does not exist:

```
superseded_by targets: composition_arc_edit×6, composition_authoring_run_manage×5, …, web_search×1
total tools with superseded_by: 54     book_list superseded_by count: 0
```

---

## 3 · Decision 2 — reproducible, but not frozen

### 3.1 The catalog snapshot verifies, and the arms rebuild from it

```
recomputed sha: eec0470b5a5a4f8a181f9515d1d654908250b72ad519567449955b554711ab6e
matches: True        n tools: 315        book_list present: True
```
```
$ python eval/arms/run_arms.py --dry-run
arm A:   1 tools, ~   286 tok, book_list=PRESENT | 1 tool — the answer, alone
arm B:   0 tools, ~     0 tok, book_list=ABSENT  | fixed envelope; schema arrives as conversation text
arm C:  35 tools, ~  7770 tok, book_list=PRESENT | every book_* tool including retired (17 retired)
arm D:  18 tools, ~  4834 tok, book_list=PRESENT | current-only — retired removed
arm E:   6 tools, ~  1405 tok, book_list=ABSENT  | exactly what the token budget left; budgeter dropped 29
```

The decisive structural variable reproduces (`book_list` absent in E, 29 dropped). The published
compositions still do not match exactly — arm C 7,770 tok / 17 retired against a documented 7,921 /
19; arm D 18 tools / 4,834 tok against 16 / 4,661. Round 1's finding here is **narrowed, not
closed**. The scores (1/1, 3/3, 0/3) remain n≤3, which the run itself rules "never evidence".

### 3.2 🔴 The metrics baseline is not frozen — its input is a live database

I re-ran the committed file:

```
$ docker exec -i infra-postgres-1 psql -U loreweave -d loreweave_chat -f - \
    < contracts/agent-runtime-baseline/baseline-metrics.sql
```

Output matched `baseline-metrics.frozen.txt` **line for line**, all five blocks. That is a real
improvement over round 1 and I record it as such.

It is nonetheless not a freeze. The only input is `loreweave_chat`, which is a shared dev database
still taking writes — 21 organic calls and 22 assistant turns landed in the current week alone. There
is:

- no snapshot of the rows, no row-count assertion, no content hash (contrast `catalog_sha256`, which
  the arm runner *refuses* to proceed past on mismatch);
- **no `AS OF` cut-off** — every class counts to `max(created_at)`, which advances;
- a §5 block keyed on `now() - interval '10 weeks'`, so that table is **guaranteed** to differ next
  month with no code change and no notice.

A baseline that reproduces because nobody has used the product this week is a memory with a
timestamp. The catalog got the treatment; the corpus did not.

---

## 4 · Decision 3 — contamination and the four numbers

### 4.0 🔴 The decontamination declared is not the decontamination implemented

The file's header states two exclusions. `_organic` implements one and a half:

```sql
CREATE OR REPLACE TEMP VIEW _organic AS
SELECT m.* FROM chat_messages m JOIN chat_sessions s ON s.session_id = m.session_id
WHERE COALESCE(s.title,'') NOT ILIKE '%F17 monitor verify%'
  AND COALESCE(s.title,'') NOT ILIKE '%[THROWAWAY]%';
```

`%[THROWAWAY]%` matches **zero** sessions. The whole decontamination is four sessions containing
four messages:

```
       title        | sessions | msgs_with_calls | assistant_msgs
--------------------+----------+-----------------+----------------
 F17 monitor verify |        4 |               4 |              4
```

**Blank-argument calls are declared excluded and no predicate excludes them.** Still inside
"organic":

```
 organic_calls | blank_arg_calls | blank_arg_failures | organic_failures | sessions_with_blank
---------------+-----------------+--------------------+------------------+---------------------
          6243 |            1174 |                565 |             2835 |                 213
```

565 blank-argument failures are 19.9% of the class-1/class-2 denominator.

**The header cites a harness share it then does not remove.** It says *"57.5% of the raw failure
population is test-harness traffic"* — a figure from round 1, computed with harness =
`F17 ∪ sg-% ∪ ds-2026-% ∪ ^(G-|M-)`:

```sql
WITH c AS (SELECT COALESCE((tc->>'ok')::boolean,false) AS ok,
    (s.title='F17 monitor verify' OR s.title LIKE 'sg-%' OR s.title LIKE 'ds-2026-%'
     OR s.title ~ '^(G-|M-)') AS harness_r1,
    (s.title ILIKE '%F17 monitor verify%') AS removed_by_committed_sql
  FROM chat_messages m JOIN chat_sessions s USING(session_id)
  CROSS JOIN LATERAL jsonb_array_elements(m.tool_calls) tc WHERE m.tool_calls IS NOT NULL)
SELECT count(*) FILTER (WHERE NOT ok) AS raw_failures, …;
```
```
 raw_failures | harness_failures_r1_defn | pct_harness_cited | actually_removed | pct_actually_removed | harness_left_in_organic
--------------+--------------------------+-------------------+------------------+----------------------+-------------------------
         4015 |                     2304 |              57.4 |             1180 |                 29.4 |                    1124
```

**1,124 harness failures — 39.6% of the 2,835 "organic" denominator — remain in it.** The scripted
families are not marginal:

```
             klass              | sessions | calls | failures
--------------------------------+----------+-------+----------
 scripted probe (still counted) |      301 |  3702 |     1339
 unclassified                   |      220 |  2240 |     1290
 F17 (excluded by builder)      |        4 |  1220 |     1180
 scenario (still counted)       |       27 |   301 |      206
```

That they are scripted is not an inference. `ds-*` and `sg-*` sessions replay canned prompts:

```
             title              |            owner_user_id             |  created_at
--------------------------------+--------------------------------------+-------------
 ds-2026-07-09-S02-baseline-S02a | 019d5e3c-…-1344e148bf7c              | 2026-07-09
--- sample user message ---
 Add these to my book: a character called Lâm Uyên, a young sect heir. And a term 'Chân Linh' …
 Show me Lâm Uyên.
```

Corpus context confirmed: **one dogfooding user** (762 of 828 sessions), 7 users, and
**3 rows in `message_feedback`** against 2,669 assistant turns (0.11%). There is no ground-truth
channel; every number below is defined in terms of `ok`, and C-5 exists because `ok=true` can be a
lie (**trap 1 stands, unaddressed**).

---

### 4.1 🔴 Class 1 — carry-forward. Published **12.6% organic** (was 61.8%)

Reproduces exactly. **And it does not compute what its own comment says.**

The comment: *"the success must PRECEDE the failure."* The `_calls` view stamps every element of an
assistant message's `tool_calls` array with the **message's** `created_at`, so all calls in one turn
are simultaneous and `s.created_at < f.created_at` **can never be satisfied within a turn**. The
predicate is therefore "succeeded in a strictly earlier assistant *message*" — a reading round 1
tabulated at 8.8% and did not endorse. The array position is recorded and is discarded.

```sql
WITH calls AS (
  SELECT m.session_id, m.sequence_num, ord, tc->>'tool' AS tool,
         COALESCE((tc->>'ok')::boolean,false) AS ok,
         (COALESCE(s.title,'') NOT ILIKE '%F17 monitor verify%') AS organic
  FROM chat_messages m JOIN chat_sessions s USING(session_id)
  CROSS JOIN LATERAL jsonb_array_elements(m.tool_calls) WITH ORDINALITY AS t(tc,ord)
  WHERE m.tool_calls IS NOT NULL),
seq AS (SELECT *, row_number() OVER (PARTITION BY session_id ORDER BY sequence_num, ord) rn FROM calls),
fo  AS (SELECT session_id, tool, min(rn) first_ok FROM seq WHERE ok GROUP BY 1,2),
j   AS (SELECT s.*, f.first_ok FROM seq s LEFT JOIN fo f USING (session_id, tool))
SELECT … ;
```
```
  scope  | fails | earlier_msg | pct_earlier_msg | earlier_call | pct_earlier_call | anywhere | pct_anywhere
---------+-------+-------------+-----------------+--------------+------------------+----------+--------------
 organic |  2835 |         357 |            12.6 |         1116 |             39.4 |     1302 |         45.9
 raw     |  4015 |         357 |             8.9 |         2296 |             57.2 |     2482 |         61.8
```

**1,116 organic failures follow a recorded, ordered, earlier success in the same turn and are counted
as not-carry-forward.** The order-respecting figure is **39.4%**, not 12.6% — 3.1× the published
number. The headline "61.8% → 12.6%" also silently fuses two different changes: decontamination
(61.8% → 45.9% on the same reading) and a change of predicate (45.9% → 12.6%).

Direction matters and it is not neutral. A baseline understated 3.1× makes any honest later
measurement of the new runtime read as a catastrophic regression; and because the acceptance table
sets the gate at 12.6% → 6.3%, the required n is computed from a rate that does not describe the
phenomenon.

### 4.2 🔴 Class 2 — not-a-real-dispatch. Published **16.1%, "lower bound"**

Reproduces exactly. The bound is so far below the truth that it cannot serve as a comparison anchor.

The most common error string in the entire organic failure population is our own breaker prose, and
the committed predicate does not match it:

```
                                      err                                       | count
--------------------------------------------------------------------------------+-------
 You have already called 'book_get' with these exact arguments 3 times this turn |   495
 entity_id must be a UUID                                                        |   337
 'kg_project_create' already ran this turn with these exact arguments …          |   263
 find_tools has been called with no `intent` 3 times this turn — STOP …          |   157
 validating "arguments": … required: missing properties: ["book_id"]             |   110
 'book_chapter_save_draft' keeps being called with missing/blank required args … |    86
```

Every distinct string the committed predicate misses (top 15 of the 745):

```
 You have already called 'book_get' … 3 times this turn                  | 495
 'book_chapter_save_draft' keeps being called with missing/blank … STOP. |  86
 You have already called 'kg_list_templates' … 3 times this turn         |  36
 You have already called 'glossary_book_ontology_read' … 3 times         |  23
 'book_get_chapter' has already FAILED 2 times this turn …               |  22
 You have already called 'composition_get_work' … 3 times this turn      |  20
 'glossary_search' has failed with missing/blank required args 3 times   |  18
 You have already called 'composition_get_outline_node' … 3 times        |  12
 … (7 more, all the same shape)
```

```
 organic_failures | committed_pred | pct_committed | wider_pred | pct_wider | missed_by_committed
------------------+----------------+---------------+------------+-----------+---------------------
             2835 |            456 |          16.1 |       1201 |      42.4 |                 745
```

**16.1% → a wider lower bound of 42.4%, a 26.3pp miss.** Two of the predicate's eight clauses
(`%repeated%`, `%cap%`) fire **zero** times; `%cap%` was flagged as a leak risk and is in fact dead.

**This is trap 2 and trap 4 together.** The new arm does not classify by prose. `instrument.py`
assigns `source` structurally at the dispatch site and treats *any* unstamped non-primitive as
`breaker`:

```python
if chunk.get("source") not in TOOL_CALL_SOURCES:
    name = chunk.get("tool") or ""
    chunk["source"] = SOURCE_META if name in RUNTIME_PRIMITIVES else SOURCE_BREAKER
    chunk["source_inferred"] = True
```

So the baseline arm is measured by a prose matcher that recovers ~38% of the class, and the new arm
by a complete structural classifier that additionally absorbs any unstamped dispatch site. The
file's own comment identifies exactly this hazard for `meta` and fixes it by scoring both arms on
NOT-A-REAL-DISPATCH — but that fix assumes the two arms' classifiers identify the same set, and they
demonstrably do not. **The class is not comparable across arms at any sample size.**

### 4.3 ⚖️ Class 3 — identifier resolution. Published **34.9% of real errors**

Reproduces exactly (842 / 2,415). Predicate decomposition:

```
 real_errors | not_found | invalid_id | uuid | placeholder | not_exist | missing_required | blank_arg_real_errors
-------------+-----------+------------+------+-------------+-----------+------------------+-----------------------
        2415 |       204 |        172 |  446 |          90 |        87 |               25 |                   408
```

I could not fault the predicate itself — the `%uuid%` clause is dominated by genuine
identifier failures (`entity_id must be a UUID`, `got 'placeholder_id_1'`), and `%missing required%`
contributes only 25 rows, none from blank-argument calls. **The number is not unsound in
construction.** It is unsound in *population*: the signal is 90% scripted probe.

```sql
SELECT CASE WHEN s.title ILIKE '%F17 monitor verify%' OR s.title ~ '^(ds-20|sg-|tle-|G-|M-|W-)'
              OR s.title ILIKE 'scenario%' THEN 'scripted probe' ELSE 'unscripted' END AS pop,
       count(*) AS id_resolution_errors
FROM chat_messages m JOIN chat_sessions s USING(session_id)
CROSS JOIN LATERAL jsonb_array_elements(m.tool_calls) tc
WHERE m.tool_calls IS NOT NULL AND NOT COALESCE((tc->>'ok')::boolean,false)
  AND (tc->>'error' ILIKE '%uuid%' OR tc->>'error' ILIKE '%placeholder%') GROUP BY 1;
```
```
      pop       | id_resolution_errors
----------------+----------------------
 scripted probe |                  402
 unscripted     |                   44
```

Recomputed on unscripted traffic only, the class is **12.4%** (141 / 1,137), not 34.9%.

One internal inconsistency worth recording: class 3's denominator strips only meta tools and
`%already ran this turn%`, while class 2's "our own prose" set is broader. The two classes therefore
use different definitions of "our prose" in the same file that says every class shares one
definition of a call. It is 36 rows (1.5%) — small, but it is drift, not rounding.

### 4.4 🔴 Class 4 — no-interpretable-outcome. Published **90.7%**

Reproduces exactly. **It measures the age of a column.**

```sql
SELECT COALESCE(finish_reason,'<NULL>') AS fr, count(*), min(created_at)::date, max(created_at)::date
FROM chat_messages WHERE role='assistant' GROUP BY 1 ORDER BY 2 DESC;
```
```
       fr       | count | first_seen | last_seen
----------------+-------+------------+------------
 <NULL>         |  2404 | 2026-04-03 | 2026-07-18
 stop           |   219 | 2026-07-19 | 2026-08-04
 awaiting_input |    31 | 2026-07-19 | 2026-08-02
 interrupted    |    12 | 2026-07-21 | 2026-08-04
 error          |     2 | 2026-07-21 | 2026-07-25
 streaming      |     1 | 2026-08-04 | 2026-08-04
```

`finish_reason` was written from **2026-07-19**. Every NULL is a turn that predates the column, and
the shim maps NULL → `interrupted`. Split on that date:

```
             era             | turns | unclassified |  pct
-----------------------------+-------+--------------+-------
 before it existed           |  2404 |         2404 | 100.0
 since finish_reason shipped |   261 |           12 |   4.6
```

**The acceptance table's target is 90.7% → <5%. Live data already sits at 4.6%, three weeks before
CP-0 opened, with no contribution from the new runtime.** The number is not a measurement of a
failure mode; it is a measurement of when a column was added. The run does label it *coverage, never
a quality win* — that hedge is correct and I credit it — but it is still carried in the acceptance
table as one of three pooled targets, where it is satisfied by rows already in the database. This is
the standing question answered in the affirmative: **this number would look good even if the thing
being measured were broken.**

### 4.5 Every published number moves 2.8×–4.6× under the decontamination the header claims

Recomputed on unscripted traffic (F17 ∪ `ds-`/`sg-`/`tle-`/`G-`/`M-`/`W-` ∪ `scenario*` removed;
n = 2,285 calls / 1,296 failures):

| class | published | unscripted | ratio |
|---|---|---|---|
| carry-forward (order-respecting) | 12.6% | **58.1%** | 4.6× |
| carry-forward (as-published predicate) | 12.6% | 20.8% | 1.7× |
| not-a-real-dispatch (committed predicate) | 16.1% | 12.5% | 0.8× |
| not-a-real-dispatch (wider lower bound) | 16.1% | **61.0%** | 3.8× |
| identifier resolution | 34.9% | **12.4%** | 0.36× |
| no-interpretable-outcome | 90.7% | **4.6%** (post-column) | 0.05× |

The header's claim that decontamination moves *every organic figure in the flattering direction* is
itself wrong: identifier resolution moves 2.8× the other way.

---

## 5 · Decision 4 — the bound the data supports

### 5.1 The power arithmetic checks out

Two-proportion, α = .05 two-sided, 80% power, `n = (z_{α/2}√(2p̄q̄) + z_β√(p₁q₁+p₂q₂))² / Δ²`:

```
target                                                n/arm (mine)  RUNSTATE
carry-forward  12.6 -> 6.3                                   337.3       334
not-a-real-dispatch 16.1 -> 8.0                              252.4       270
no-interpretable-outcome 90.7 -> 5.0                           3.9        30
```

Rows 1–2 agree within rounding. Row 3 is conservative by ~8×, harmless. The two stated facts also
hold: `3/3` bounds a failure rate at ≤63.2% (one-sided 95% Clopper–Pearson upper bound, `0.05^(1/3)`)
against 54.2%, and ≤10% needs 29 consecutive successes (`0.9^29 = 0.047`).

**But the numbers fed in are the ones §4 rules unsound.** At the order-respecting carry-forward rate
(39.4% → 19.7%) the requirement is **83/arm**, not 334; at the wider not-a-real-dispatch bound
(42.4% → 21.2%) it is **75/arm**, not 270. The arithmetic is right and its inputs are not.

### 5.2 🔴 The traffic figure that makes the design look reachable is harness traffic

The acceptance table reads *"at organic traffic (mean 624, median 114 calls/wk, ~40% failing) — ~1
burst week, or ~7 quiet ones."* Mean 624 reproduces from §5 of the frozen output. The burst weeks
that produce it are scripted sweeps:

```
    week    | unscripted_calls | unscripted_failures | scripted_calls
------------+------------------+---------------------+----------------
 2026-08-03 |               23 |                   8 |              0
 2026-07-27 |              102 |                  64 |              0
 2026-07-20 |              981 |                 701 |           1733
 2026-07-13 |               29 |                   2 |           2402
 2026-07-06 |              816 |                 427 |           1012
 2026-06-29 |               72 |                  17 |              0
 2026-06-22 |              126 |                  38 |              0
 2026-06-15 |              122 |                  35 |             35
 2026-06-08 |                1 |                   0 |              0
 2026-06-01 |                6 |                   1 |              0
```

Unscripted mean is **228 calls/wk**, not 624 — the published mean is inflated **2.7×**. Over the
unscripted window (2026-05-18 → 2026-08-04, 11.14 weeks): **205 calls/wk, 116 failures/wk**,
product-wide across all 124 observed tools. That is consistent with the brief's ~414/wk only if
harness traffic is counted as product traffic.

A separate figure in the same section — *"377 successful calls/week against **191 mean / 47
median** available"* — I could not reproduce from any window:

```
    window     | n_weeks | mean_succ | median_succ
---------------+---------+-----------+-------------
 all weeks     |      11 |     310.0 |        55.0
 last 10 weeks |      10 |     340.8 |        71.5
```

The conclusion it supports (withdraw ≈13 admissions/week) is conservative, so this is a provenance
defect, not an error of direction — but it is another number without its query.

### 5.3 🔴 The pooled design relocates the problem

Pooling is arithmetically sound and the reachability column mis-attributes its input. **The new arm
only receives calls to admitted declarations.** The table computes accrual as if the new arm
received the whole product's traffic.

Per-declaration unscripted volume:

```
              tool              | calls | failures | calls_per_week | fails_per_week
--------------------------------+-------+----------+----------------+----------------
 book_get                       |   552 |      496 |           30.7 |           27.6
 find_tools                     |   313 |      157 |           17.4 |            8.7
 glossary_book_ontology_read    |   138 |       46 |            7.7 |            2.6
 glossary_web_search            |   122 |      103 |            6.8 |            5.7
 glossary_propose_entities      |   106 |       48 |            5.9 |            2.7
 book_chapter_save_draft        |    97 |       92 |            5.4 |            5.1
 …
 book_list                      |    42 |       11 |            2.3 |            0.6
```

```
book_list (declaration #1)      42 calls   11 fails ->  0.99 fails/wk ->  338.3 weeks (6.51 yr) to n=334/arm
book_get                       552 calls  496 fails -> 44.51 fails/wk ->    7.5 weeks (0.14 yr)
top-5 failing declarations    1015 calls  785 fails -> 70.45 fails/wk ->    4.7 weeks (0.09 yr)
if the pool were the ENTIRE product:                                        2.9 weeks
pool must carry 36% of all product failures to reach n=334 in 8 weeks
book_list's share of product failures: 0.85%
```

**Three consequences.**

1. **The run's own first declaration cannot open the gate.** `book_list` is 0.85% of product
   failures — **6.5 years** to n=334, materially worse than the 5.0 years the per-declaration design
   was withdrawn for. Pooling does not help a pool of one, which the run correctly states; it also
   does not help a pool of two if the two are chosen for architectural cleanliness rather than
   volume.
2. **The threshold is a traffic share, not a declaration count.** The binding consequence *"the
   pooled gate cannot open until ≥2 declarations are admitted"* states a floor that is not the
   binding constraint. The real threshold is **≈36% of all product failures inside the pool** for an
   eight-week close. With `book_list` first, that is most of the catalog — i.e. the end of the
   migration, not a gate that governs it.
3. **The pooled comparison is a mix comparison, and the party being measured chooses the mix.** The
   baseline arm is the frozen full-catalog mixture over 124 tools; the new arm is a hand-picked
   subset. Carry-forward varies from 0.6 to 27.6 failures/week and from near-zero to near-total
   across tools, so the pooled rate is a weighted average whose weights are the admission order.
   Admitting low-carry-forward declarations first lowers the pooled rate with no runtime change.
   Unless the baseline is re-restricted to the same admitted set — and the run does not say it is —
   this is Simpson's paradox with the partition under the builder's control. If the baseline *is*
   re-restricted, then for `book_list` the baseline side has **11 failures in total**, which cannot
   support n=334 at any future date.

**The plain answer the brief asks for: longer than the run.** At the pooled unit the gate is
reachable in ~3 weeks *only once the pool is the whole product*, and with the declared first
declaration it is 6.5 years. The problem has moved from "the unit is too small" to "the unit is large
enough only when the work is already finished."

---

## 6 · The traps

| trap | finding |
|---|---|
| **1 · scoring on `ok=true`** | 🔴 **Unaddressed.** Class 1's numerator is *"already succeeded"* = `ok=true`; classes 2 and 3 denominate on `NOT ok`. A runtime that substitutes a wrong object *less* produces fewer `ok=true` firsts and a lower carry-forward rate without fixing carry-forward. `message_feedback` has **3 rows / 2,669 turns** — there is no ground-truth channel to break the tie. |
| **2 · guard red over the wrong subject** | 🔴 **Live.** Class 2's baseline classifier (prose match, recovers ≈38% of the class) and the new arm's classifier (`instrument.py`, structural, complete) identify different sets. Any movement in that class is an artifact of which classifier ran. |
| **3 · self-derived denominator** | 🔴 **Live for class 4.** The 90.7% denominator is all assistant turns ever, 90% of which predate the column being counted. Post-column the rate is 4.6% — the target is met by construction. |
| **4 · the comparison that cannot be computed** | 🔴 **Confirmed, unchanged from round 1.** `declaration` is absent from every pre-CP-0 row; `book_list` has **zero** `superseded_by` edges in the frozen snapshot; the run acknowledges this as binding consequence #2 and defers it to CP-4. As of `e75ad5d7d` the join does not exist. |

---

## 7 · The bound table

| class | published | my recompute (same predicate) | my recompute (sound predicate / population) | denominator | contamination handling | n/arm for the claimed improvement |
|---|---|---|---|---|---|---|
| carry-forward | 12.6% organic | **12.6%** (357 / 2,835) — reproduces | **39.4%** order-respecting organic; **58.1%** unscripted | organic failures = 2,835, of which **1,124 (39.6%) are harness** | F17 only (29.4% of raw failures); 1,174 blank-arg calls left in | 334 published / 337 mine; **83** at the order-respecting rate |
| not-a-real-dispatch | 16.1% (LB) | **16.1%** (456 / 2,835) — reproduces | **42.4%** wider LB organic; **61.0%** unscripted | same 2,835 | same | 270 published / 252 mine; **75** at the wider LB |
| identifier resolution | 34.9% | **34.9%** (842 / 2,415) — reproduces | **12.4%** unscripted (141 / 1,137) | real errors = 2,415; 90% of the UUID/placeholder signal is scripted probe | same; denominator uses a *different* "our prose" set than class 2 | not stated in the acceptance table |
| no-interpretable-outcome | 90.7% | **90.7%** (2,416 / 2,664) — reproduces | **4.6%** on turns where `finish_reason` existed | all assistant turns ever; 2,404 predate the column | none needed — the contaminant is time, not sessions | 30 published / 4 mine; **already met** |

---

## 8 · What must change for a PASS, stated as facts not fixes

Recorded so a later round can be checked against something:

1. Class 1's predicate must respect the recorded call order, or the class must be renamed to what it
   measures ("failed on a tool that succeeded in an earlier turn").
2. Class 2 cannot be scored across arms while the two arms use different classifiers; the gap is
   26.3pp on identical rows, larger than the effect being claimed.
3. Class 4's baseline must be restricted to turns where `finish_reason` existed, or dropped from the
   acceptance table.
4. The corpus must be pinned the way the catalog is — a row-count or content hash and an `AS OF`
   cut-off — or `frozen.txt` is an output without an input.
5. The pooled gate needs a stated **traffic-share** precondition, not a declaration count, and the
   baseline arm must be restricted to the admitted set or the mix is chosen by the measured party.

---

*Authority exercised: under the brief's clause, I rule **class 1 (12.6%)**, **class 2 (16.1%)** and
**class 4 (90.7%)** unsound as stated. Any PASS resting on those three numbers — including one given
by another role — is void. Class 3 (34.9%) is sound in construction and contaminated in population;
I do not void it, I bound it.*
