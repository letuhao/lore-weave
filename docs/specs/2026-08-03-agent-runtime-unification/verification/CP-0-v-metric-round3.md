# CP-0 · V-METRIC — verdict, ROUND 3

*Artifact frozen at `9f4096072`, working tree clean. Verified 2026-08-04 against `loreweave_chat` in
`infra-postgres-1`. Subject: the instrument, never the feature. No tracked file was modified; the
one write to the database was a `BEGIN … ROLLBACK` demonstration whose before/after fingerprints are
printed below.*

---

## 1 · Verdict

| | |
|---|---|
| **OVERALL** | 🔴 **FAIL** — but this is the first round in which the corrections are, in part, *right* rather than merely different. Two of the three re-derivations are technically correct; all three still fail to select the population their class name states. |
| **1 · answerable, and unanswerable today** | ⚖️ **PARTIAL PASS**, carried from round 2 and re-checked. `declaration` now present on **35 of 7,482** recorded calls (was 18); still **zero** on the pre-CP-0 side, so the matched pair still joins on tool name. |
| **2 · reproducible from the snapshot alone** | 🔴 **FAIL** — the fingerprint is **not** theatre in principle, and **is** theatre as built. It hashes the primary-key set only. Three `UPDATE`s of exactly the kind this corpus has already received moved `calls_organic` −41.5%, `failures_organic` −27.2% and class 4 from 4.9% → 0.0% while `messages`/`newest`/`corpus_md5` stayed **byte-identical**. Nothing compares it: zero code references, against `run_arms.py`'s `sys.exit` on `catalog_sha256`. And it **expired during this verification** — 5,766 → 5,768, md5 `7fa07…` → `dc3e9…`, every headline number moved. |
| **3 · the four numbers** | 🔴 **FAIL**, with real credit. Class 1's `WITH ORDINALITY` fix is **correct** and I verified the ordering key is sound on this corpus. Class 4's **window date is exactly right** — a clean cut, zero non-nulls before, zero nulls after. Class 2's `'%this turn%'` clause does **not** over-capture; the parent's specific suspicion is **not** borne out. But class 1 is **91.1% our own repeat-breaker**, movable by the constant `REPEAT_READ_CAP = 2`; class 2's `%budget%`/`%not permitted%` clauses capture **real dispatches** because pydantic's boilerplate and the *caller's own argument names* match them, and its blank-argument exclusion deletes 157 rows of the very prose the class is about; class 4 post-window contains **zero** NULLs — all 13 "unclassified" rows are `finish_reason='interrupted'`, a recorded outcome. |
| **4 · the bound the data supports** | 🔴 **FAIL on the claim; the response is honest, not an evasion.** Arming no gate and referring the choice out is the structurally correct move and I credit it without qualification. It nonetheless **concedes** the claim CP-0 exists to establish rather than satisfying it. Of the three options, **B does not work**, **A works only as a posture** (it accumulates toward a bound whose join does not exist), and **C is the only one that could work** — but the property it names is already certified by C2, so as offered it is self-satisfying. |
| **C1–C6 closure criterion** | ⚖️ **SPLIT — C1–C4 legitimate, C5 and C6 reverse-engineered, and the set omits this role's subject entirely.** |

### The falsifier — what I looked for that would have made this PASS

**On class 1**, I set out to find the ordering fix wrong. I tested the new key directly: zero
sessions with tied `created_at` among call-bearing messages, zero `(sequence_num, created_at)`
inversions, and `(created_at, ord)` reproduces round 2's independent `(sequence_num, ord)` count at
**1,116 exactly**. The fix is right. So I attacked the predicate instead and asked what the 1,116
*are*: **1,017 (91.1%) are our own repeat-breaker prose** and **1,020 are the same tool with
byte-identical arguments**. Had that split come back the other way — had most of the 1,116 been
genuine service errors on a tool that had really worked earlier — class 1 would have stood and I
would have passed it.

**On class 2**, I set out to confirm the parent's suspicion that `'%this turn%'` catches genuine
service errors. **It does not.** I printed every distinct string that clause uniquely adds: four
strings, 93 rows, all of them `'X' keeps being called with missing/blank required arguments this
turn — STOP`. That is our middleware. I record this as a finding *for* the builder. The
over-capture is in clauses nobody flagged: `%budget%`, `%not permitted%`, `%blocked%`.

**On class 4**, I set out to find the window date wrong by hours. `min(created_at)` where
`finish_reason IS NOT NULL` is `2026-07-19 10:29:19.51552+00`; rows before the `2026-07-19` boundary
with a non-null value: **0**. NULL rows inside the window: **0**. The cut is clean and the date is
correct. So the class survives its date and dies on its label instead.

**On the fingerprint**, I set out to be wrong that it is insufficient — a content hash *is* the right
instrument, it is what `catalog_sha256` does. I mutated the three fields the derivation actually
reads inside a rolled-back transaction. The fingerprint did not move by one character.

**A PASS was available on decision 4 and I withheld it.** The builder's answer to decision 4 is the
most honest artifact in this checkpoint. I withheld the PASS because decision 4 asks what bound the
data supports, and the answer — *none* — is a correct diagnosis of a failed claim, not a satisfied
one.

---

## 2 · The corpus, and what happened to it during this verification

The committed derivation reproduced **line for line** on first run:

```
$ docker exec -i infra-postgres-1 psql -U loreweave -d loreweave_chat -f - \
    < contracts/agent-runtime-baseline/baseline-metrics.sql
== PIN · corpus fingerprint (numbers below are valid ONLY for this fingerprint) ==
 messages |            newest             |            corpus_md5
----------+-------------------------------+----------------------------------
     5766 | 2026-08-04 01:03:56.580788+00 | 7fa0764949af13d461784b8222f0a887

== 0 · POPULATION ==
 calls_raw | calls_organic | failures_raw | failures_organic
-----------+---------------+--------------+------------------
      7467 |          6247 |         4015 |             2835
…
```

Roughly twenty-seven minutes later, unprompted, on the same command:

```
$ diff <(live re-run) contracts/agent-runtime-baseline/baseline-metrics.frozen.txt
4c4
<      5768 | 2026-08-04 01:31:10.054201+00 | dc3e98aa28a80a6758b8443a3265622a
---
>      5766 | 2026-08-04 01:03:56.580788+00 | 7fa0764949af13d461784b8222f0a887
9c9
<       7482 |          6262 |         4028 |             2848
---
>       7467 |          6247 |         4015 |             2835
14,15c14,15
<  organic |     2848 |         1116 |       39.2 |        1302 |      45.7
<  raw     |     4028 |         2296 |       57.0 |        2482 |      61.6
---
>  organic |     2835 |         1116 |       39.4 |        1302 |      45.9
>  raw     |     4015 |         2296 |       57.2 |        2482 |      61.8
21c21
<  organic  |     2283 |              1032 |  45.2 |             0
---
>  organic  |     2270 |              1028 |  45.3 |             0
26c26
<  organic |        2428 |       855 | 35.2
---
>  organic |        2415 |       842 | 34.9
32c32
<  organic |             267 |       219 |             31 |      2 |       2 |           13 |              4.9
---
>  organic |             266 |       219 |             31 |      2 |       1 |           13 |              4.9
```

**Every published class moved inside one verification session.** The file's own comment says *"the
numbers below are valid ONLY for this fingerprint."* By its own rule the frozen file is already
non-comparable, and nothing anywhere will say so. All numbers below are stated at the frozen
fingerprint `7fa0764949af13d461784b8222f0a887` unless marked otherwise.

---

## 3 · Decision 2 — is a fingerprint sufficient, or is it theatre?

**Both, and the distinction is the ruling.** A content hash is exactly the right instrument — it is
what `eval/arms/run_arms.py` already does for the catalog, and it works:

```
eval/arms/run_arms.py:65:    if actual != doc["catalog_sha256"]:
eval/arms/run_arms.py:66:        sys.exit(f"BASELINE HASH MISMATCH — recorded {doc['catalog_sha256'][:16]}, computed "
```

The corpus fingerprint fails on three counts, and only the first is about the hash itself.

### 3.1 It hashes the primary-key set, not the data the derivation reads

`md5(string_agg(message_id ...))` covers **`message_id` and nothing else**. The derivation reads
`tool_calls`, `created_at`, `role`, `is_error`, `finish_reason`, `session_id` — and
`chat_sessions.title`, on which the *entire* decontamination rests. `chat_sessions` is not
fingerprinted at all. There is no `updated_at` on `chat_messages`, so in-place mutation leaves no
trace anywhere.

I demonstrated this with three `UPDATE`s inside a transaction that was rolled back. Each is of a kind
this corpus has already received — the RUNSTATE records an `UPDATE` that moved `finish_reason`.

```sql
BEGIN;
UPDATE chat_messages SET finish_reason='stop'
  WHERE role='assistant' AND finish_reason='interrupted';                       -- UPDATE 13
UPDATE chat_messages SET tool_calls = jsonb_set(tool_calls,'{0,ok}','true'::jsonb)
  WHERE tool_calls IS NOT NULL AND jsonb_array_length(tool_calls)>0;            -- UPDATE 984
UPDATE chat_sessions SET title='F17 monitor verify' WHERE title LIKE 'ds-2026-%'; -- UPDATE 260
```

```
== FP-0 · fingerprint BEFORE ==
     5766 | 2026-08-04 01:03:56.580788+00 | 7fa0764949af13d461784b8222f0a887

== FP-1 · fingerprint AFTER three mutations that change every number below ==
     5766 | 2026-08-04 01:03:56.580788+00 | 7fa0764949af13d461784b8222f0a887

== FP-2 · the numbers, recomputed under the mutation (fingerprint IDENTICAL) ==
 calls_raw | calls_organic | failures_raw | failures_organic
-----------+---------------+--------------+------------------
      7467 |          3653 |         3773 |             2064
 turns_in_window | pct_unclassified
-----------------+------------------
             270 |              0.0
ROLLBACK
== FP-3 · fingerprint AFTER ROLLBACK (must equal FP-0) ==
     5766 | 2026-08-04 01:03:56.580788+00 | 7fa0764949af13d461784b8222f0a887
```

`calls_organic` −41.5%, `failures_organic` −27.2%, class 4 from 4.9% to 0.0%. **The fingerprint is
byte-identical across all of it.** The comment's stated rule — *"if these three values differ … the
numbers are NOT comparable"* — asserts a converse it has not earned: that if the three values agree,
the numbers *are* comparable. FP-1 is a counterexample.

### 3.2 Nothing compares it

The hash `7fa0764949af13d461784b8222f0a887` appears in exactly two files in the repository:

```
./contracts/agent-runtime-baseline/baseline-metrics.frozen.txt
./docs/plans/2026-08-04-agent-runtime-RUNSTATE.md
```

Zero code references. No checker, no CI step, no comparator. The catalog snapshot has a runner that
**refuses to proceed**; the corpus fingerprint is a line of output. A pin that nothing reads is a
label, and §2 above shows it had already gone stale by the time I read it.

### 3.3 Ruling

**A fingerprint is sufficient in principle and this one is not sufficient in fact.** It detects
insert and delete of messages — genuinely more than round 2 had, and I record the improvement. It
cannot detect any update, and every number in the file is a function of columns it does not cover.
Decision 2 remains **FAIL**, for a narrower and now fully demonstrated reason.

---

## 4 · Decision 3 — are the corrections right, or merely different?

### 4.0 The ordering key itself is sound — I checked before crediting the fix

```sql
WITH m AS (SELECT session_id, message_id, sequence_num, created_at
           FROM chat_messages WHERE tool_calls IS NOT NULL)
SELECT (SELECT count(*) FROM (SELECT session_id, created_at, count(*) c FROM m
          GROUP BY 1,2 HAVING count(*)>1) z) AS sessions_with_tied_created_at_groups,
       (SELECT count(*) FROM m a JOIN m b ON a.session_id=b.session_id
          AND a.sequence_num<b.sequence_num AND a.created_at>b.created_at) AS inverted_pairs;
```
```
 sessions_with_tied_created_at_groups | msgs_in_tied_groups | inverted_pairs
--------------------------------------+---------------------+----------------
                                    0 |                   0 |              0
```

No ties, no inversions, and `(created_at, ord)` returns **1,116** — identical to round 2's
independently-written `(sequence_num, ord)`. **The `WITH ORDINALITY` correction is right.** One
caveat for the record, not a defect today: nothing in the schema enforces this. The unique index is
`(session_id, sequence_num, branch_id)`; `created_at` defaults to `now()` and carries no uniqueness
guarantee, so the key's validity is a property of *this corpus*, not of the table. `branch_id` is
non-zero on 5 messages, which the predicate does not partition on — negligible here, wrong in
principle once branching is used.

### 4.1 🔴 Class 1 — the fix is correct and the predicate still is not the claim. **39.4%**

The claim class is *"a failure on a **declaration** that **already succeeded** in the same session."*
I asked what the 1,116 rows actually are.

```sql
WITH f AS (SELECT * FROM _calls WHERE NOT ok AND organic),
     s AS (SELECT * FROM _calls WHERE ok AND organic),
     j AS (SELECT f.*, EXISTS(SELECT 1 FROM s WHERE s.session_id=f.session_id AND s.tool=f.tool
             AND (s.created_at,s.ord)<(f.created_at,f.ord)) AS strict FROM f)
SELECT count(*) FILTER (WHERE strict) AS carry_forward,
       count(*) FILTER (WHERE strict AND (error ILIKE '%this turn%' OR error ILIKE '%already ran%'
         OR error ILIKE '%You have already called%')) AS cf_that_is_breaker_prose, …
FROM j;
```
```
 carry_forward | cf_that_is_breaker_prose | pct_breaker | cf_genuine_service_error
---------------+--------------------------+-------------+--------------------------
          1116 |                     1017 |        91.1 |                       99
```

**91.1% of class 1 is our own repeat-breaker refusing an identical call.** Three consequences, each
measured:

**(a) The class is tautological on those rows.** The breaker fires *because* an earlier call
occurred. If that earlier call returned `ok=true`, "succeeded earlier in the session" is satisfied by
the breaker's own precondition. It is not evidence that the model failed on a capability it had been
shown to work.

```
== X3 · how many carry-forward "successes" are the SAME tool AND the SAME args as the failure? ==
 carry_forward | same_tool_and_same_args
---------------+-------------------------
          1116 |                    1020
```

91.4% are byte-identical repeats. The phenomenon is *the model looping on one call*, not *the model
forgetting a capability*.

**(b) 14.1% of the numerator is not a declaration.**

```
                 kind                  | carry_forward
---------------------------------------+---------------
 declaration                           |           959
 runtime primitive (not a declaration) |           157
```

All 157 are `find_tools`. Class 2 treats runtime primitives as *not a real dispatch*; class 1 counts
them as declarations that already succeeded. Same file, same corpus, opposite treatment.

**(c) The number is movable by an integer constant with no runtime change.**

```
services/chat-service/app/services/stream_service.py:524:  REPEAT_READ_CAP = 2
services/chat-service/app/services/stream_service.py:4264:  if _prior is not None and _prior[1] >= REPEAT_READ_CAP:
```

Raising `REPEAT_READ_CAP` to 3 deletes a large share of the 1,017 and moves class 1 down without
touching the runtime being evaluated. **This is the standing question answered in the affirmative
for a second time in this class**: the number would move even if nothing being measured changed.

**What the class measures when its own prose is removed from both sides:**

```
 real_failures | carry_forward_real | pct
---------------+--------------------+-----
          1670 |                 99 | 5.9
```

**5.9%**, not 39.4%. Round 2 called 12.6% understated 3.1×; the correction to 39.4% is right against
*that* objection and overshoots the class's own definition by 6.7× against this one. Where the top
of the class comes from:

```
             tool             | failures | carry_forward
------------------------------+----------+---------------
 book_get                     |      502 |           496
 kg_project_create            |      270 |           265
 find_tools                   |      157 |           157
```

**Class 1 and class 2 are now the same 1,017 rows.** The acceptance table treats them as two
independent pooled targets. They are one defect counted twice.

### 4.2 ⚖️ Class 2 — the parent's suspicion is wrong, and the over-capture is elsewhere. **45.3%**

**`'%this turn%'` does not over-capture.** Every distinct string that clause uniquely contributes:

```sql
SELECT left(error,110) AS err, count(*) FROM _calls
WHERE NOT ok AND organic AND NOT (args='{}'::jsonb) AND error ILIKE '%this turn%'
  AND NOT (error ILIKE '%already ran this turn%' OR error ILIKE '%You have already called%'
        OR error ILIKE '%times this turn%')
GROUP BY 1 ORDER BY 2 DESC;
```
```
 'book_chapter_save_draft' keeps being called with missing/blank required arguments this turn — STOP. |  86
 'composition_conformance_run' keeps being called with missing/blank required arguments this turn — … |   3
 'glossary_propose_entities' keeps being called with missing/blank required arguments this turn — ST… |   3
 'glossary_adopt_standards' keeps being called with missing/blank required arguments this turn — ST… |   1
```

93 rows, four strings, all our own middleware. **The clause is clean and the widening was justified.**

**The over-capture is in `%budget%`, `%not permitted%` and `%blocked%`.** Per-clause unique
contribution:

```
           clause           | total | uniq
----------------------------+-------+------
 already ran this turn      |   263 |    0
 Do not ask to run it again |    15 |    0
 You have already called    |   595 |    0
 times this turn            |   636 |    0
 this turn (BROAD)          |   992 |   93
 repeated                   |     0 |    0
 blocked                    |    18 |    3
 not permitted              |    10 |   10
 budget                     |     8 |    8
 cap (SUBSTRING RISK)       |     0 |    0
 meta tool name             |     0 |    0
```

I printed the full text of all 21 uniquely-captured rows. **Every one is a real dispatch that reached
the tool and failed argument validation:**

```
 3 | Error executing tool plan_compile: validation failed — compile blocked
 2 | Error executing tool composition_authoring_run_create: 2 validation errors …
   | args.book_id
   |   Field required [type=missing, input_value={'budget_usd': 10, 'pause_after_each_unit': False}, …]
 1 | Error executing tool composition_conformance_run: 2 validation errors …
   | args.book_id
   |   Extra inputs are not permitted [type=extra_forbidden, input_value='019f63f2-…', input_type=str]
```

Two distinct mechanisms, and both are worse than a stray match:

- **`%budget%` fires on the caller's own argument name.** Pydantic echoes `input_value` into the
  error, so a call carrying `budget_usd: 10` is classified as our own prose because *the model chose
  that argument*. The classifier is reading the model's input, not our output.
- **`%not permitted%` fires on a pydantic constant.** `Extra inputs are not permitted` is library
  boilerplate for `extra_forbidden`. **Every `extra_forbidden` validation failure in the product is
  misclassified** — and argument-shape failure is precisely the mode the new runtime exists to fix.

21 rows is 0.9pp of the class. The magnitude is small; the mechanism is not bounded by it.

**The blank-argument exclusion is wrong in kind, and it moves the number 2.9pp upward.** The header
describes what it removes as *"a harness sweep that calls tools with `'{}'` to probe schemas."* That
characterisation does not survive contact:

```
== C2-I · session spread of the 565 excluded blank-arg failures ==
 sessions_with_blank_arg_failures | blank_arg_failures | blank_arg_in_scripted | blank_arg_in_UNSCRIPTED
----------------------------------+--------------------+-----------------------+-------------------------
                               60 |                565 |                   277 |                     288
```

**51% of the "harness sweep" is in unscripted sessions.** And what they are:

```
== X1 · error text of the excluded rows ==
 find_tools has been called with no `intent` 3 times this turn — STOP calling find_tools again w… |   157
 validating "arguments": validating root: required: missing properties: ["book_id"]               |   110
 validating "arguments": validating root: required: missing properties: ["query"]                 |    99
 Error executing tool composition_get_work: pass project_id or book_id                            |    25
 invalid arguments for translation_coverage — `book_id`: Field required (you sent a dict). Fix t… |    22
```

The largest block — **157 rows** — is *our own breaker prose*, the class's own subject, deleted from
the class's own numerator. The next two blocks are genuine schema-resolution failures, i.e. class 3's
subject. All 565 carry an explicit `args` key set to `{}`; none is a missing-field artefact. This is
not decontamination. It is the removal of an organic failure mode, and it removes it from exactly
the classes it belongs to.

```
== C2-G · class 2 WITHOUT the blank-arg exclusion, same numerator predicate ==
 organic_failures_all | ours | pct
----------------------+------+------
                 2835 | 1201 | 42.4
```

**42.4% without the exclusion, 45.3% with it.** The exclusion moves the class in the flattering
direction.

### 4.3 🔴 The file's own invariant is now violated three ways

The `_calls` comment states the design guarantee: *"both populations, so every class below shares one
definition of 'a call' and cannot drift between metrics."*

```
                               k                                | count
----------------------------------------------------------------+-------
 class1 denominator (all organic failures)                      |  2835
 class2 denominator (blank-arg excluded)                        |  2270
 class3 denominator (meta+already-ran excluded, blank-arg KEPT) |  2415
 class3 blank-arg rows still inside it                          |   408
```

Three denominators, one stated invariant. The header declares the blank-argument exclusion globally,
*before anything is counted*; **exactly one of four classes implements it.** Round 2's finding was
"declared and never implemented"; the fix implemented it in one place and left the declaration
global. The defect moved rather than closing.

### 4.4 🔴 The decontamination itself is unchanged from round 2

`_organic` is byte-identical to the version round 2 ruled on: `F17 monitor verify` plus a
`%[THROWAWAY]%` clause that matches zero sessions.

```sql
SELECT count(*) FILTER (WHERE NOT c.ok) AS organic_failures,
  count(*) FILTER (WHERE NOT c.ok AND (s.title LIKE 'sg-%' OR s.title LIKE 'ds-2026-%'
    OR s.title ~ '^(G-|M-|W-|tle-)' OR s.title ILIKE 'scenario%')) AS scripted_failures_still_in, …
FROM _calls c JOIN chat_sessions s USING(session_id) WHERE c.organic;
```
```
 organic_failures | scripted_failures_still_in | pct
------------------+----------------------------+------
             2835 |                       1539 | 54.3
```

**54.3% of the population the file calls "organic" is scripted harness traffic.** The header still
states *"57.5% of the raw failure population is test-harness traffic"* and still removes 29.4% of it.

### 4.5 ⚖️ Class 3 — unchanged, and round 2's population finding stands. **34.9%**

The predicate was not touched. Recomputed by population:

```
    pop     | real_errors | id_errors | pct
------------+-------------+-----------+------
 scripted   |        1278 |       701 | 54.9
 unscripted |        1150 |       154 | 13.4
```

Sound in construction, contaminated in population, as in round 2. **13.4%** on unscripted traffic
against a published 34.9%. I do not void it; I bound it.

### 4.6 🔴 Class 4 — the window is right, the label is wrong. **4.9%**

**The date is correct and I credit it without reservation:**

```sql
SELECT min(created_at) AS first_non_null_finish_reason,
       count(*) FILTER (WHERE created_at < TIMESTAMPTZ '2026-07-19') AS non_null_BEFORE_window
FROM chat_messages WHERE role='assistant' AND finish_reason IS NOT NULL;
```
```
 first_non_null_finish_reason | non_null_before_window
------------------------------+------------------------
 2026-07-19 10:29:19.51552+00 |                      0
```

Zero non-nulls before the boundary. Window sensitivity confirms the cut is sharp, not tuned:

```
  boundary  | turns | nulls | pct_null
------------+-------+-------+----------
 2026-07-17 |   274 |     4 |      1.5
 2026-07-18 |   274 |     4 |      1.5
 2026-07-19 |   270 |     0 |      0.0
 2026-07-20 |   266 |     0 |      0.0
 2026-07-23 |   163 |     0 |      0.0
```

**And that same table destroys the number.** Inside the window there are **zero NULL `finish_reason`
rows**. So what are the 13 counted as `unclassified`?

```sql
SELECT COALESCE(finish_reason,'<NULL>') AS finish_reason, is_error, count(*)
FROM chat_messages m
WHERE m.role='assistant' AND m.created_at >= TIMESTAMPTZ '2026-07-19'
  AND m.session_id IN (SELECT session_id FROM _organic)
  AND NOT (m.is_error OR m.finish_reason IN ('stop','awaiting_input','error','streaming'))
GROUP BY 1,2 ORDER BY 3 DESC;
```
```
 finish_reason | is_error | count
---------------+----------+-------
 interrupted   | f        |    13
```

**All 13 are `finish_reason = 'interrupted'` — a recorded, interpretable, correct outcome.** The
shim's `ELSE 'interrupted'` branch collapses *"we do not know"* into *"we know: interrupted"*, and
the report column is labelled `unclassified`.

- The true post-window rate of **no interpretable outcome is 0.0%**, not 4.9%.
- **4.9% is the genuine interruption rate** wearing the wrong class name.
- The class therefore cannot be scored: a move from 4.9% to <5% could be fewer users pressing stop.
  It cannot distinguish the instrument failing to record from the run genuinely being interrupted —
  which is the one distinction the class exists to make.

Round 2's objection (a column-age artefact) is **resolved**. A different objection now applies to the
same cell: the numerator no longer contains a single instance of the thing the class is named for.

### 4.7 The acceptance table still carries the withdrawn numbers

`docs/plans/2026-08-04-agent-runtime-RUNSTATE.md` holds both sets, unreconciled. Lines 36–39 carry
39.4 / 34.9 / 45.3 / 4.9; lines 105–107, introduced as *"at the newly frozen baselines"*, carry:

```
105:| carry-forward **12.6% → 6.3%** | ≈ **334 failures** | ~1 burst week, or ~7 quiet ones |
106:| not-a-real-dispatch **16.1% → 8%** | ≈ **270 failures** | comparable |
107:| no-interpretable-outcome **90.7% → <5%** | ≈ **30 turns** | days — but this is coverage, not quality |
```

Nothing marks them stale. The `n/arm` figures 334 / 270 / 30 are computed from baselines the run's own
frozen derivation contradicts. No gate is armed, so the operational harm today is nil; a reader
landing on the acceptance table gets three withdrawn numbers presented as current.

---

## 5 · Decision 4 — honest response, failed claim, and whether the options work

### 5.1 The response is honest. This is not an evasion, and I will not call it one.

Three properties distinguish disclosure from evasion, and the artifact has all three:

1. **It gives up something.** No gate is armed. The builder cannot now declare victory on any of the
   four classes. An evasion preserves the option to claim success later; this closes it.
2. **It names its own defect as the reason.** *"A builder selecting its own success metric is the
   defect this entire run exists to avoid, so I am not picking one."* That is the correct structural
   argument, and it is the argument against the builder's own interest.
3. **It states the arithmetic that forces the conclusion**, including the figures from my round-2
   verdict that were adverse to it — the 2.7× inflated reachability, the 6.5-year `book_list`, the
   ≈36% traffic-share threshold — rather than re-deriving friendlier ones.

**But an honest concession of a claim is not a satisfied claim.** CP-0's stated purpose is that
*"the new runtime beats the old one"* becomes computable and falsifiable. The builder's answer is
that it cannot be settled on this corpus. That is decision 4 correctly *answered* and decision 4
**FAILED**. Decision 4 is the one place in this brief where I was told in advance that "longer than
the run" is the most valuable finding; the builder reached it independently, which is to its credit
and does not change the verdict.

### 5.2 The arithmetic at the corrected baselines

Two-proportion, α = .05 two-sided, 80% power:

```
carry-forward 39.4->19.7                     n/arm =     83.0
carry-forward 12.6->6.3 (withdrawn)          n/arm =    337.3
not-a-real-dispatch 45.3->22.65              n/arm =     67.4
not-a-real-dispatch 16.1->8.0 (withdrawn)    n/arm =    252.4
no-interp 4.9->2.45                          n/arm =    924.6
```

The corrected baselines *help*: 337 → **83** and 252 → **67**. Class 4 inverts — halving 4.9%
needs **925 turns**, against the 30 in the acceptance table, a 31× understatement. Detection time at
measured unscripted traffic (206.5 calls/wk, 117.5 failures/wk over 2026-05-18 → 2026-08-04):

```
book_list alone              0.99 fails/wk ->    83.8 wk ( 1.61 yr)   baseline-side failures available: 11
book_get alone              44.79 fails/wk ->     1.9 wk ( 0.04 yr)   baseline-side failures available: 499
top-5 pooled                70.90 fails/wk ->     1.2 wk ( 0.02 yr)
whole unscripted product   117.50 fails/wk ->     0.7 wk ( 0.01 yr)   baseline-side failures available: 1296
```

**The binding constraint is not the new arm — it is the frozen one.** `book_list` has **11 failures
in the entire unscripted corpus**. No amount of future traffic adds to a frozen baseline. For the
declared first declaration the comparison is unreachable *permanently*, not slowly.

### 5.3 Do the three options work?

| | ruling |
|---|---|
| **A · ship, publish, gate nothing** | ⚖️ **Works as a posture, not as a path.** It is the only option that changes nothing and lies about nothing. But `asserted_bound: unknown` *"tightens with use"* presupposes the matched-pair join, and that join does not exist: **35 of 7,482** calls carry `declaration`, **zero** on the pre-CP-0 side, and `runtime_variant` is `legacy` on all 5,768 messages. A bound cannot tighten toward a comparison that cannot be computed. A accumulates evidence for a question no query can currently ask. |
| **B · replay the frozen baseline corpus offline** | 🔴 **Does not work, for three independent reasons.** (i) *There is no frozen corpus to replay* — §3 shows the corpus is unpinned and drifted during this verification; B's premise is the thing decision 2 fails on. (ii) *The population is wrong* — 54.3% of it is scripted harness traffic (§4.4), so a replay measures the harness. (iii) *Repeated replays are pseudo-replication.* Re-running the same 42 `book_list` prompts N times samples LLM nondeterminism, not independent user behaviour; between-prompt variance is absent, so nominal confidence intervals would be too narrow and the design would report significance it has not earned. The builder's own §0.12 (a test may reject, never admit) is a fourth reason and the weakest of the four. |
| **C · change the claim to a property** | ⚖️ **The only one that could work — and not as offered.** A property falsifiable at n=1 genuinely escapes the traffic bound, and *"is a narrowing ever unrecorded"* is a real property of the instrument. But it is **already certified by C2** (*"V-LIVE derived 303 expected, found 303"*). Adopting it makes the acceptance criterion something CP-0 has itself declared met — the self-derived denominator (trap 3) promoted from a metric to the gate. C works only if the property is one CP-0 has not already certified, and none is offered. |

**The plain answer, unchanged and now better supported: longer than the run** — and for the declared
first declaration, longer than any run, because the frozen side has 11 rows.

---

## 6 · Ruling on C1–C6 — legitimate exit condition, or reverse-engineered?

**⚖️ SPLIT. C1–C4 are legitimate. C5 and C6 are reverse-engineered. The set as a whole excludes the
subject of this role, and that exclusion is what decides it.**

The test I applied to each row: *is there a state of the world in which this row reads red, and is
that state distinguishable from the deliverable existing?*

| # | ruling | why |
|---|---|---|
| **C1** | ✅ **Legitimate** | Falsifiable and demonstrably *was* red — the RUNSTATE records the approved Tier-A resume dispatch being filed `breaker`, caught and fixed. A criterion that has been observed red is not reverse-engineered. |
| **C2** | ✅ **Legitimate** | `303 expected, 303 found` — the expected count is derived independently of the found count. Could have come back 302. |
| **C3** | ✅ **Legitimate** | `diff = +kg_view_delete` across 4 passes is a positive observation that a mid-turn deletion is recoverable from the record. An empty diff would have been red. |
| **C4** | ✅ **Legitimate** | Was red — the `shield` fix and the `outcome='awaiting_input'` contradiction were both found and both closed. |
| **C5** | 🔴 **Reverse-engineered** | *"the baseline is derivable from committed artifacts, with its queries **and a corpus fingerprint**"*. Round 2 demanded a **pin**; C5 was written afterwards and names **the artifact that was built** instead of the property that was demanded. Its state cell is `✅ baseline-metrics.sql` — the criterion is satisfied by the file existing. §3 shows the fingerprint is byte-identical under mutations that move every number and that it had already expired. **C5 reads green while the property it stands in for is red.** |
| **C6** | 🔴 **Reverse-engineered** | *"the run states what its numbers can and cannot support."* **There is no configuration of the world in which C6 is red.** Any sentence satisfies it; writing it satisfies it. A criterion whose satisfaction condition is the act of writing the criterion is not an exit condition. The *content* of what was written is genuinely good — §5.1 credits it — but C6 does not test that content, and a differently-worded, dishonest paragraph would score the same green. |

**And the decisive point is what is not in the table.** No row of C1–C6 requires any of the four
numbers to be *sound*. C5 requires **derivability**, not correctness — and the preamble makes the
exclusion explicit: *"CP-0 closes when the instrument records honestly — not when the thing it
measures is good, and not when a bound is provable."*

That framing is defensible in the abstract; an instrument checkpoint should not have to prove the
thing it measures. But it does not do the work asked of it here, because **"records honestly" is
exactly this role's subject**, and §4 shows three of four classes do not record what their names say:
class 1 is 91.1% a different phenomenon, class 2 deletes 157 rows of its own subject and captures 21
rows of a real dispatch, and class 4's numerator contains **zero** instances of the thing it is named
for. Those are honesty defects in the record, not bound-provability questions, and C1–C6 has no row
that can see them.

So: **written after two rounds of failure, and constructed such that the role that produced both
failures cannot block closure.** I do not read that as bad faith — C1–C4 are real, and the rule-1/
rule-2 argument about checkpoint scope is one I would accept in another context. I read it as a set
that is **necessary and not sufficient**, and I decline to treat it as the exit condition for this
verification. The missing row, stated so a later round can check it:

> **C7 — each class's predicate selects the population its class name states, demonstrated by
> decomposing the numerator, not asserted by the predicate's construction.**

C7 is red today, on classes 1, 2 and 4, by the decompositions in §4.1, §4.2 and §4.6.

---

## 7 · The traps

| trap | finding |
|---|---|
| **1 · scoring on `ok=true`** | 🔴 **Unaddressed, and now load-bearing.** Class 1's numerator is `ok=true`, and 1,020 of its 1,116 rows pair a success with a byte-identical repeat. `message_feedback` holds **3 rows against 2,675 assistant turns** (0.11%) across **7 users / 830 sessions**. There is no ground-truth channel and no attempt to build one. |
| **2 · guard red over the wrong subject** | 🔴 **Live, and narrowed.** Round 2's version (prose matcher vs structural classifier) is unchanged. The new instance is sharper: `%budget%` and `%not permitted%` fire on pydantic boilerplate and on the *caller's own argument names*, so the baseline classifier can be tripped by what the model chose to send. |
| **3 · self-derived denominator** | 🔴 **Live, relocated.** Class 4's column-age denominator is fixed — genuinely. It reappears in option C, which proposes as the acceptance criterion a property C2 has already certified. |
| **4 · the comparison that cannot be computed** | 🔴 **Confirmed, unchanged.** `declaration` on **35 of 7,482** calls, **zero** pre-CP-0; `runtime_variant='legacy'` on all 5,768 messages. `book_list`'s frozen side holds **11 failures**, which no future traffic increases. |

---

## 8 · The bound table

| class | published | reproduces? | value on the population the name states | denominator | contamination handling | n/arm for the claimed improvement |
|---|---|---|---|---|---|---|
| **carry-forward** | **39.4%** (1,116/2,835) | ✅ exact; ordering key independently verified sound | **5.9%** (99/1,670) once our own prose leaves both sides; 91.1% of the published numerator is the repeat-breaker, 14.1% is a runtime primitive | organic failures = 2,835, of which **1,539 (54.3%) are scripted harness** | F17 only; blank-arg **not** excluded here though the header says it is | 83 (was 337 at the withdrawn 12.6%) — but 91% of the class moves with `REPEAT_READ_CAP` |
| **not-a-real-dispatch** | **45.3%** (1,028/2,270) | ✅ exact | **42.4%** without the blank-arg exclusion; 21 rows are real dispatches captured by `%budget%` / `%not permitted%` / `%blocked%` | 2,270 = 2,835 − 565 blank-arg, of which **288 are unscripted** and 157 are the class's own subject | blank-arg excluded **here only**, of four classes | 67 (was 252) |
| **identifier resolution** | **34.9%** (842/2,415) | ✅ exact; predicate untouched | **13.4%** unscripted (154/1,150) | real errors = 2,415, with 408 blank-arg rows still inside | different "our prose" set from class 2 | not stated |
| **no-interpretable-outcome** | **4.9%** (13/266) | ✅ exact; window date verified correct to the hour | **0.0%** — zero NULLs in the window; all 13 are `finish_reason='interrupted'`, a recorded outcome | in-window assistant turns = 266 | column-age contaminant **resolved**; the label is now the defect | **925** to halve 4.9%, against 30 in the acceptance table |

---

## 9 · What must change for a PASS, stated as facts not fixes

Recorded so round 4 can be checked against something. Round 2's list is superseded; items 1, 3 and 4
below are its 1, 3 and 4 in corrected form.

1. Class 1 must exclude our own breaker prose from its numerator, or be renamed to what 91.1% of it
   is. A class whose value tracks `REPEAT_READ_CAP` is not a property of the runtime.
2. Class 2's `%budget%`, `%not permitted%` and `%blocked%` clauses match pydantic boilerplate and
   caller-supplied argument names; and its blank-argument exclusion removes 157 rows of the class's
   own subject from the class's own numerator.
3. Class 4's numerator contains zero instances of *no interpretable outcome*. The shim's
   `ELSE 'interrupted'` cannot distinguish "unrecorded" from "interrupted", and the class needs the
   two separated before either can be scored.
4. The corpus fingerprint must hash the columns the derivation reads — `tool_calls`, `finish_reason`,
   `is_error`, `role`, `created_at`, and `chat_sessions.title` — and something must **compare** it,
   as `run_arms.py` compares `catalog_sha256`.
5. The header's declared decontamination and the implemented decontamination must be the same set.
   Three classes, three denominators, one stated invariant.
6. The acceptance table at RUNSTATE lines 105–107 carries three withdrawn numbers under the heading
   *"at the newly frozen baselines"*.

---

*Authority exercised. I rule **class 1 (39.4%)**, **class 2 (45.3%)** and **class 4 (4.9%)** unsound
as stated — not for the reasons round 2 gave, all three of which were correctly addressed, but
because in each case the numerator does not contain the population the class name asserts. Any `PASS`
resting on those three numbers, including one given by another role, is void. Class 3 (34.9%) is
sound in construction and contaminated in population; I bound it at 13.4% and do not void it.*

*Recorded in fairness: the `WITH ORDINALITY` correction is right, the `2026-07-19` window is right to
the hour, `'%this turn%'` does not over-capture, the corpus fingerprint is a real improvement over
having none, and arming no gate is the correct response to an unsettleable claim. This round's
corrections moved toward the truth. They have not yet arrived at it.*
