# CP-0 · V-METRIC — verdict, ROUND 5

*Artifact frozen at `9d16657cb`, working tree clean. Verified 2026-08-04 against `loreweave_chat` in
`infra-postgres-1`. Subject: the instrument, never the feature. No tracked file was modified. Every
write to the database was inside a `BEGIN … ROLLBACK`; before/after fingerprints are printed below
and the closing fingerprint equals the opening one.*

**All numbers in this document are stated at corpus fingerprint**

```
 messages |            newest             |            corpus_md5
----------+-------------------------------+----------------------------------
     5862 | 2026-08-04 04:58:09.556834+00 | 9cdacf696d9b5ebb6932d3e8e8062d1c
```

**which is not the frozen one.** `baseline-metrics.frozen.txt` was taken at `5772` /
`9546bb2c9338d126a2b69018121ae29e`. By the file's own rule — *"the numbers below are valid ONLY for
this fingerprint"* — the committed frozen output is already non-comparable, for the second
consecutive round. It did not drift further during this session.

---

## 1 · Verdict

| | |
|---|---|
| **OVERALL** | 🔴 **FAIL** — and this is the round in which the class predicates largely got *right*. **Three of four classes now pass C7.** The remaining failures are class 3's denominator, the fingerprint's residual blind spot, and a bound the frozen side cannot supply. |
| **1 · answerable, and unanswerable today** | ⚖️ **PARTIAL PASS.** `advertised_tools`, `withheld_tools`, `source` and `outcome` answer real questions that had no answer before, and `source` is now good enough that I used it as independent ground truth to grade class 2. `declaration` is **instrumentation debt** — byte-identical to `tool` on **201/201** rows. `runtime_variant` is `legacy` on **all 5,862** messages and **all 201** instrumented calls. |
| **2 · reproducible from the snapshot alone** | 🔴 **FAIL, narrowed to one demonstrated hole.** The fingerprint is **no longer theatre**: it now moves under all three of round 3's mutations, which I re-ran and print below. It still omits `created_at`, `role` and `session_id` — all read by the derivation. A rolled-back mutation of those three collapsed class 4's window from **316 turns to 1**, moved `interrupted` **19 → 0**, and redistributed class 5's weekly traffic, with the hash **byte-identical**. Still **zero code references**: nothing compares it. |
| **3 · the four numbers** | 🔴 **FAIL, on class 3 alone.** All four reproduce exactly at my fingerprint. **C7 is GREEN on classes 1, 2 and 4** by decomposition. **C7 is RED on class 3**: its "REAL errors" denominator still contains **763 rows (30.9%) of our own breaker prose**, a *different* definition of "real errors" from the one class 1 now uses; on a clean denominator the class is **50.8%**, not 35.7%. |
| **4 · the bound the data supports** | 🔴 **FAIL, and worse than round 3 — because the correction was right.** Correcting carry-forward from 39.4% to 6.0% raises the required sample from **83 to 748 per arm**. The frozen baseline side holds **548** unscripted real errors, and no future traffic adds to a frozen side. **Halving carry-forward is not detectable against this baseline, permanently.** |
| **additional · the partition claim** | 🔴 **REFUTED**, three independent ways. |
| **additional · `latency_unmeasured`** | ✅ **Acceptable for CP-0.3**, with a stated condition. |

### The falsifier — what I looked for that would have made this PASS

**On class 1** I set out to find the new 6.0% numerator contaminated the way the old 39.4% one was.
I decomposed all 101 rows against four separate contaminants and printed every distinct error string
in the numerator. It came back **0 breaker prose, 0 meta tools, 0 null errors, 5 same-args repeats**,
and thirty distinct genuine service and validation failures. **Had one breaker string appeared in
that list I would have failed the class.** None did. I record this as the first class in five rounds
to survive its own decomposition.

**On class 2** I looked for the removed clauses to have been replaced by something equally leaky, and
for the narrowed blank-arg rule to have quietly kept its old reach. Instead I found a stronger test
than prose inspection: the recorded `source` field is now an **independent ground truth** for exactly
this class. Against it the predicate has **zero false positives** — 36 `source='tool'` failures, none
classified as our prose — and **7 false negatives out of 26** `source='breaker'` rows. A single
`source='tool'` row captured as our prose would have failed the class. There were none.

**On class 4** I looked for the `interrupted` reclassification to be a relabelling that hid a NULL.
There are **0 NULL `finish_reason`** rows in the window, **0 unrecognised values**, and `is_error`
overrides nothing. The 0.0% is real. **But I then checked the file's claim that the shim speaks "the
SAME vocabulary the new runtime writes"** — and the instrument writes `outcome='abandoned_by_user'`
for `finish_reason='interrupted'` on **8 of 8** rows, a word the shim can never emit.

**On the fingerprint** I set out to be wrong that it is still insufficient, and I began by proving it
*sufficient* against round 3's own attack — the hash moved. So I asked which fields the derivation
reads that the hash still does not cover, and mutated those instead.

**On the partition claim** I set out to confirm it. My first attempt reproduced the other verifier's
`307` exactly — and that is how I found the error: `307` is `13 + 294`, a count of **records**, not of
**tools**.

**A PASS was available on decision 3 and I withheld it** on one class. Classes 1, 2 and 4 earn it.

---

## 2 · The instrument has produced real rows — ruling on whether the fields work

```
== A1 · NEW-FIELD CENSUS (all chat_messages) ==
 msgs | assistant_msgs | has_advertised | has_withheld | has_outcome | rv_agentruntime | rv_legacy
------+----------------+----------------+--------------+-------------+-----------------+-----------
 5862 |           2720 |             66 |           28 |          67 |               0 |      5862

== A2b · raw element keys present across all tool_calls elements ==
         k          | count
--------------------+-------
 ok                 |  7648
 args               |  7648
 tool               |  7648
 error              |  7612
 iteration          |  7612
 result             |  7612
 id                 |  7607
 activity           |  1148
 source             |   201
 latency_ms         |   201
 runtime_variant    |   201
 declaration        |   201
 source_inferred    |   110
 latency_unmeasured |    78
 pending            |    36
 toolCallId         |    36
 runId              |    36
 task               |    10

== A3 · source value distribution ==
 source  | count
---------+-------
 <NULL>  |  7447
 tool    |    91
 meta    |    84
 breaker |    26

== A4 · outcome value distribution (assistant rows) ==
      outcome      | count
-------------------+-------
 <NULL>            |  2653
 completed         |    51
 abandoned_by_user |     8
 awaiting_input    |     5
 crashed           |     3
```

### 2.1 ✅ `advertised_tools` — answers its question, and answers it well

Structure is per-pass: `{pass, count, names[], tool_choice}`. The question *"was the tool the model
needed actually offered to it?"* is now directly readable, and it was unanswerable before —
`chat_sessions.activated_tools` is a session-level array with no per-pass, per-turn resolution.

The strongest evidence is that the field survives its own hardest test:

```
== F6 · CAN A CALLED TOOL BE ABSENT FROM BOTH LISTS IN ITS OWN TURN? ==
 calls_in_instrumented_turns | in_advertised | in_withheld | in_neither
-----------------------------+---------------+-------------+------------
                         201 |           201 |          51 |          0
```

**Every one of the 201 recorded calls appears in its own turn's advertised set. Zero appear in
neither.** That is a real, falsifiable observation that could have come back otherwise.

### 2.2 ⚖️ `withheld_tools` — answers its question on the turns that have it

```
== C0 · shape ==
 adv_type | wit_type | count
----------+----------+-------
 array    | array    |    28
 array    |          |    38

== E0 · withheld elements MISSING the pass key ==
 has_pass |       stage        | count
----------+--------------------+-------
 f        | token_budget       |   331
 f        | failure_breaker    |     1
 t        | token_budget       |  1023
 t        | hot_seed           |   197
 t        | failure_breaker    |    12
 t        | suppress_tool_list |     1
```

**38 of 66 instrumented turns carry `advertised_tools` with `withheld_tools` NULL**, and **332 of
1,565 withheld records (21.2%) carry no `pass` key**, so they cannot be attributed to a pass at all.
The field works where present; it is not yet uniformly present.

### 2.3 🔴 The partition claim is REFUTED — three independent ways

> *A verifier separately established that a turn's withheld+advertised now partitions the catalogue
> exactly (307 = 32 advertised ∪ 286 withheld, zero unaccounted).*

The turn is `c92cc5d8-e337-48b6-93ca-e85d5bae5310`. The two cardinalities are right:

```
== E3 · the verifier row c92cc5d8 : exact sets ==
 adv_distinct | wit_rows | wit_distinct | adv_passes
--------------+----------+--------------+------------
           32 |      294 |          286 |         13
```

**(i) 32 ∪ 286 is 317, not 307.**

```
== D1 · PER-TURN name-level partition (top rows) ==
              message_id              | adv_names | wit_names | overlap | union_names
--------------------------------------+-----------+-----------+---------+-------------
 7882d01a-b0a4-4302-9ba5-847b57cb3a2b |        33 |       303 |      19 |         317
 c92cc5d8-e337-48b6-93ca-e85d5bae5310 |        32 |       286 |       1 |         317
 8dad348e-5e5b-4d65-8fc1-92963ed42734 |        65 |       178 |      11 |         232
 82cda3d9-6f07-4cce-9ab9-454e9704b019 |        64 |       178 |      11 |         231
```

`307` is `13 + 294` — the count of **advertised pass-objects plus withheld records**. It is a count
of rows in two JSON arrays, not of tools. My own first pass reproduced `307` by making exactly that
mistake, which is how I identified it: `advertised_tools` elements are *pass objects carrying a
`names[]` array*, not names.

**(ii) The two sets are not disjoint, which is what "partition" means.** At turn level, **15 of 28**
turns that carry both arrays have at least one tool in both, **81 entries** in total. That alone is
defensible — a tool withheld in pass 1 can legitimately be advertised in pass 3. So I tested at the
tightest possible unit, the single pass:

```
== F1 · PER-PASS overlap (a tool BOTH advertised and withheld in the SAME pass) ==
 overlapping_message_pass_tool_triples | distinct_passes_affected
---------------------------------------+--------------------------
                                    28 |                        4

== F9 · the 28 same-pass contradictions (extract) ==
              message_id              | pass |            tool             |    stage     |                 reason
--------------------------------------+------+-----------------------------+--------------+-----------------------------------------
 4ce53500-cd3c-40fd-8f5c-7136ecf7482a |    4 | book_steering_set           | token_budget | did not fit the activation token budget
 82cda3d9-6f07-4cce-9ab9-454e9704b019 |    3 | kg_graph_query              | token_budget | did not fit the activation token budget
 82cda3d9-6f07-4cce-9ab9-454e9704b019 |    3 | memory_search               | token_budget | did not fit the activation token budget
 8dad348e-5e5b-4d65-8fc1-92963ed42734 |    2 | kg_triage_resolve           | token_budget | did not fit the activation token budget
 732760c4-d11f-4e84-bf7d-bd7cd1af394b |    2 | book_chapter_create         | token_budget | did not fit the activation token budget
```

**A tool cannot be both sent to the model and withheld from it in the same pass.** 28 records say
both. In `c92cc5d8` specifically the overlapping tool is `book_update_details`.

**(iii) "Zero unaccounted" is false against the frozen catalogue.** The committed snapshot holds
**315** tools (`summary.tool_count: 315`), not 307:

```
snapshot catalogue : 315
turn adv-union-wit : 317
in turn NOT in snapshot : 7 ['chat_search_sessions', 'confirm_action', 'conversation_search',
                             'load_skill', 'run_subagent', 'workflow_list', 'workflow_load']
in snapshot NOT in turn : 5 ['glossary_adopt_standards', 'glossary_book_sync_apply', 'glossary_plan',
                             'glossary_propose_batch', 'glossary_propose_kinds']
```

**Five catalogue tools are neither advertised nor withheld in that turn** — they are precisely the
"unaccounted" the claim says are zero. The 7 extras are the local runtime primitives, which are not
gateway-federated and are not in the snapshot. Whatever the turn partitions, it is not the frozen
catalogue.

**This is trap 3 in its purest form.** A denominator of 307 derived from the record's own row counts
reads "complete". A denominator of 315 taken from the source of truth reads 5 short.

### 2.4 ✅ `tool_calls[].source` — the most valuable field added, with one caveat

`source` gave me a ground truth for class 2 that no prose analysis could. Caveat, and it is material:

```
== B4 · source vs source_inferred ==
 source  | inferred | count
---------+----------+-------
 tool    | <absent> |    91
 meta    | true     |    84
 breaker | true     |    26
```

**110 of 201 (54.7%) are inferred, not stamped.** Only `source='tool'` is a structural fact recorded
at the dispatch site. `meta` and `breaker` are assigned at the chokepoint by a closed name set
(`instrument.py:222-225`). The record is honest about this — the flag exists — and the inference rule
is a name-set membership test, not prose matching, so it is not circular with the baseline predicate.
I accept it, and note that any future scoring of the new arm on `breaker` rests on an inference for
100% of the rows in that bucket.

### 2.5 ⚖️ `outcome` — answers its question, and exposes a vocabulary gap in class 4

```
== B8 · finish_reason x outcome joint (assistant, outcome non-null) ==
 finish_reason  |      outcome      | count
----------------+-------------------+-------
 stop           | completed         |    51
 interrupted    | abandoned_by_user |     8
 awaiting_input | awaiting_input    |     5
 streaming      | crashed           |     3
```

`baseline-metrics.sql:193-194` states the shim exists *"so the baseline is stated in the SAME
vocabulary the new runtime writes — otherwise the comparison is between two different words."* The
runtime maps `interrupted → abandoned_by_user` on **8 of 8** rows. The shim maps
`interrupted → interrupted`, and has **no branch that can ever emit `abandoned_by_user`**
(`baseline-metrics.sql:216-225`). The two vocabularies agree on three values and disagree on exactly
the one the class was named for. §4.4 below.

### 2.6 🔴 `declaration` and `runtime_variant` — instrumentation debt, not instrumentation

```
== B6 · does declaration ever DIFFER from tool? ==
 with_declaration | declaration_ne_tool
------------------+---------------------
              201 |                   0

== Z1 · TRAP 4 · can the matched pair be joined? ==
 all_calls | with_declaration | agentruntime_msgs | agentruntime_calls
-----------+------------------+-------------------+--------------------
      7648 |              201 |                 0 |                  0
```

`declaration` is byte-identical to `tool` on every row that has it, and absent on the other 7,447. The
brief's decision 1 says plainly: *"A field that duplicates an existing column is instrumentation debt,
not instrumentation."* The matched-pair join it exists to enable is, today, a join on tool name.
`runtime_variant` is `legacy` on all 5,862 messages and all 201 instrumented calls — **zero
`agentruntime` rows exist**, so the new side of every matched pair is empty. **Trap 4 confirmed,
unchanged across four rounds.**

---

## 3 · Ruling on `latency_unmeasured`

**Is an explicit unmeasured marker an acceptable state for CP-0.3, or does it make any
latency-derived number unusable?**

### 3.1 The premise needs correcting first: the marker is not universal

```
== B1 · joint presence of latency_ms and latency_unmeasured ==
 has_latency_ms | has_unmeasured_marker | latency_ms_type | count
----------------+-----------------------+-----------------+-------
 t              | f                     | number          |    89
 t              | t                     | null            |    78
 t              | f                     | null            |    34

== L1 · marker-less null latency vs marked: time ranges ==
   state   | source  | count |             first             |             last
-----------+---------+-------+-------------------------------+-------------------------------
 NO MARKER | meta    |    26 | 2026-08-03 23:50:36.752805+00 | 2026-08-04 01:58:42.169584+00
 NO MARKER | breaker |     7 | 2026-08-04 00:24:57.84167+00  | 2026-08-04 01:58:42.169584+00
 NO MARKER | tool    |     1 | 2026-08-04 02:05:06.994689+00 | 2026-08-04 02:05:06.994689+00
 marked    | meta    |    58 | 2026-08-04 02:42:37.844437+00 | 2026-08-04 04:58:09.556834+00
 marked    | breaker |    19 | 2026-08-04 02:42:37.844437+00 | 2026-08-04 04:13:16.607021+00
 marked    | tool    |     1 | 2026-08-04 03:10:44.412845+00 | 2026-08-04 03:10:44.412845+00
```

**34 of the 112 unmeasured rows (30.4%) carry a bare `null` with no marker.** They all predate
02:42 on 2026-08-04, when the chokepoint shipped. So "the rest carry an explicit marker" holds
forward from that instant, not across the corpus. Within those 34 rows an outsider cannot distinguish
*"not measured here"* from *"the writer forgot"* without knowing a deploy time.

### 3.2 Coverage, and the reason it is not random

```
== L2 · latency coverage over the WHOLE call corpus ==
 all_recorded_calls | has_latency_key | has_a_number | pct_measured
--------------------+-----------------+--------------+--------------
               7648 |             201 |           89 |         1.16

== L4 · is latency measured for FAILED calls at all? ==
 ok | source  | n  | measured
----+---------+----+----------
 t  | meta    | 84 |        0
 t  | tool    | 55 |       53
 f  | tool    | 36 |       36
 f  | breaker | 26 |        0
```

3 of 30 mint sites measure (`grep -c 'yield {"tool_call"'` → **30**; `latency_ms=` passed at
`stream_service.py:4672, 7696, 7837` → **3**). The consequence is visible in L4 and it is not a
sampling issue: **missingness is perfectly confounded with `source`.** Every measured call is
`source='tool'`; **0 of 84 `meta` and 0 of 26 `breaker` calls are measured**. Measured values run
16–120 ms, mean 49.6.

### 3.3 Ruling

**✅ Acceptable for CP-0.3 — with one condition, and I state it as a fact rather than a fix.**

An explicit null with a reason is strictly better than a fabricated 0, and `instrument.py:226-231`
argues that correctly. The marker does **not** make latency-derived numbers unusable in general.

It **does** make one specific number unusable, and it is the one the field's own comment names.
`instrument.py:227-228` says the point is *"how long this call cost the turn"*, and explicitly that
*"a `meta` call is not free: `tool_list` and `find_tools` read a 315-tool catalog, and a breaker still
costs a model pass."* Those two populations have **zero measurements between them**. So:

- Any mean, percentile or total over `latency_ms` is a statistic about **`source='tool'` dispatches
  only** — 44.3% of instrumented calls, **1.16% of the corpus**.
- It may not be presented as per-turn cost, because the components the comment identifies as the
  expensive ones are systematically absent.
- **Nothing is void today.** `baseline-metrics.sql` does not reference `latency_ms` anywhere; no CP-0
  class derives from it. There is no number to withdraw.

---

## 4 · Decision 3 and C7, class by class

The committed derivation reproduced exactly at my fingerprint:

```
$ docker exec -i infra-postgres-1 psql -U loreweave -d loreweave_chat -f - \
    < contracts/agent-runtime-baseline/baseline-metrics.sql

== 0 · POPULATION ==
 calls_raw | calls_organic | failures_raw | failures_organic
-----------+---------------+--------------+------------------
      7648 |          6428 |         4072 |             2892

== 1 · CARRY-FORWARD (strict: success STRICTLY EARLIER) ==
        scope        | failures | carry_strict | pct_strict | carry_loose | pct_loose
---------------------+----------+--------------+------------+-------------+-----------
 organic             |     2892 |         1119 |       38.7 |        1305 |      45.1
 organic_real_errors |     1673 |          101 |        6.0 |         263 |      15.7
 raw                 |     4072 |         2299 |       56.5 |        2485 |      61.0

== 2 · NOT-A-REAL-DISPATCH ==
  scope   | failures | not_real_dispatch |  pct  | of_which_meta
----------+----------+-------------------+-------+---------------
 raw-only |     1180 |              1180 | 100.0 |          1180
 organic  |     2892 |              1198 |  41.4 |           157

== 3 · IDENTIFIER RESOLUTION, as a share of REAL errors ==
  scope  | real_errors | id_errors | pct
---------+-------------+-----------+------
 organic |        2472 |       883 | 35.7

== 4 · TERMINAL OUTCOME, WINDOWED on column age ==
  scope  | assistant_turns | completed | awaiting_input | failed | crashed | interrupted_recorded | unrecorded | pct_unrecorded
---------+-----------------+-----------+----------------+--------+---------+----------------------+------------+----------------
 raw     |               4 |         4 |              0 |      0 |       0 |                    0 |          0 |            0.0
 organic |             312 |       252 |             36 |      2 |       3 |                   19 |          0 |            0.0
```

### 4.1 ✅ Class 1 — C7 **GREEN**. **6.0%** (101 / 1,673)

The class name is *"a failure on a declaration that already succeeded in the same session."* I
decomposed the numerator against every contaminant round 3 found, plus two more:

```
== G1 · DECOMPOSE the numerator ==
 numerator | still_our_own_prose | meta_tools | same_tool_same_args_repeat | null_error
-----------+---------------------+------------+----------------------------+------------
       101 |                   0 |          0 |                          5 |          0
```

Round 3 measured **1,017 / 1,116 (91.1%)** breaker prose and **157 (14.1%)** runtime primitives.
Both are now **zero**. Byte-identical repeats fell from **91.4% to 5.0%**. And every distinct error
string in the numerator is a genuine failure:

```
== G3 · every distinct error string IN the numerator (top rows of 30) ==
 the row changed since you read it (409) — re-read glossary_book_ontology_read and retry     |    17
 no fields to update                                                                         |    16
 book not accessible                                                                         |     5
 a row with this code already exists                                                          |     5
 no entities were created — 1 of 1 item(s) failed. Reasons: unknown kind: cultivation_system |     5
 Error executing tool composition_get_outline_node: not found or not accessible              |     4
 validating "arguments": validating root: unexpected additional properties ["limit"]          |     4
 'glossary_propose_entities' is missing required argument(s): ['items']...                    |     3
 chapter_id must be a UUID                                                                    |     2
 invalid arguments for kg_schema_read — `project_id`: Input should be a valid string...       |     2
```

**Not one breaker string in thirty.** The class also no longer moves with `REPEAT_READ_CAP`: raising
it changes the *excluded* set, not the numerator. **C7 GREEN.**

Two things I record without voiding the number:

**(a) A three-valued-logic hole silently drops 36 rows.** The real-error filter is
`NOT (error ILIKE … OR tool IN …)`. When `error IS NULL` and the tool is not a primitive, that whole
expression is `NULL`, so the row is dropped from *both* numerator and denominator:

```
== H0 · NULL-ERROR failures ==
 organic_failures | error_is_null | null_err_nonmeta
------------------+---------------+------------------
             2892 |            36 |               36
```

A failure carrying no error text is a failure. Class 2 keeps these 36 rows (and counts them as real
dispatches); class 1 discards them. 2.2% of the denominator, and inconsistent between two classes
that the file's own `_calls` comment says *"cannot drift between metrics."*

**(b) The file publishes 38.7% alongside 6.0%.** Only 6.0% survives C7. The RUNSTATE acceptance table
line 36 carries **6.0%**, which is the correct selection.

### 4.2 ✅ Class 2 — C7 **GREEN** on precision, disclosed lower bound on recall. **41.4%** (1,198 / 2,892)

The removed clauses are gone and I verified their replacements do not leak. Per-clause decomposition:

```
== H2 · CLASS 2 per-clause UNIQUE contribution ==
 denominator | numerator | n_already_ran | n_do_not_ask | n_you_have_already | n_times_this_turn |
        2892 |      1198 |           263 |           15 |                595 |               821 |
 n_this_turn_broad | n_repeated | n_meta_tool | uniq_repeated | uniq_this_turn_broad | uniq_meta_tool
              1183 |          0 |         157 |             0 |                   99 |              0
```

The numerator is exactly `%this turn%` ∪ `%Do not ask to run it again%` (1,183 + 15 = 1,198).
`%repeated%` matches **0 rows** — a dead clause. The meta-tool clause contributes **0 unique** rows:
every one of the 157 `find_tools` rows also carries breaker prose, and there are **zero** meta-tool
failures without a prose match (`H4` returned empty), so it cannot over-capture a genuine primitive
failure.

**The decisive test is against the recorded `source`, which is what that field was added for:**

```
== H5 · CROSS-CHECK class 2 against the recorded source field ==
 source  | failures | classified_not_real_dispatch
---------+----------+------------------------------
 tool    |       36 |                            0
 breaker |       26 |                           19
```

**Zero false positives on 36 real dispatches. 19 of 26 breaker rows caught — 7 missed.** Round 3's
finding was 21 real dispatches captured by `%budget%` / `%not permitted%` / `%blocked%`; that is now
**0**. The 7 misses:

```
== H6 · the 7 source=breaker failures the prose predicate MISSES ==
          tool           |                        err                         | count
-------------------------+----------------------------------------------------+-------
 confirm_action          |                                                    |     3
 kg_propose_fact         |                                                    |     2
 book_chapter_save_draft | 'book_chapter_save_draft' is missing required a...  |     1
 book_steering_list      | 'book_steering_list' is missing required argum...   |     1
```

Five of seven carry **no error text at all** — the same NULL-error hole as §4.1(a). The class is
labelled *"LOWER BOUND pre-CP-0"* in the file, and it is measurably one: recall ≈73%, precision
100%. **The predicate selects only rows that are not a real dispatch. C7 GREEN.**

**One defect, and it is in the header rather than the number.** The blank-argument exclusion was
narrowed to `NOT (args='{}' AND NOT organic)`. It removes nothing:

```
== H1 · does the blank-arg exclusion remove ANY row? ==
 all_failures | blank_arg_failures | blank_arg_AND_nonorganic_REMOVED | blank_arg_organic_KEPT
--------------+--------------------+----------------------------------+------------------------
         4072 |                569 |                                0 |                    569
```

All 569 blank-argument failures are in organic sessions, so the clause is a no-op. The number is
correct — round 3 asked for those rows back and they are back. But `baseline-metrics.sql:44-47` still
declares blank-argument calls as an excluded contamination *"before anything is counted."* Round 3's
item 5 has inverted rather than closed: **declared globally, implemented nowhere that fires.**

### 4.3 🔴 Class 3 — C7 **RED**. Published **35.7%**; **50.8%** on a clean denominator

The predicate was not touched this round, and it is the one class where the round-3 corrections to
its neighbours have now made it inconsistent with them.

**(a) The denominator is 30.9% our own prose.** Class 3 excludes only `%already ran this turn%` and
the meta tools. Class 1's new real-error filter excludes four prose patterns:

```
== I1 · CLASS 3 denominator: how much of "REAL errors" is still OUR OWN PROSE? ==
 class3_real_errors | still_you_have_already_called | still_times_this_turn | still_any_this_turn | still_other_breaker_prose
--------------------+-------------------------------+-----------------------+---------------------+---------------------------
               2472 |                           595 |                   664 |                 763 |                       763
```

**763 of 2,472 rows (30.9%) are breaker prose.** The file now contains **two different populations
both called "REAL errors"** — 1,673 for class 1, 2,472 for class 3 — and the class-3 header states
its own rationale as *"an id-resolution rate computed over a population that is majority breaker
output measures the breaker, not the model."* By its own argument it should use class 1's filter.
Applying it:

```
== I4 · CLASS 3 with ALL breaker prose removed from the denominator ==
 real_errors_strict | id_errors | pct
--------------------+-----------+------
               1709 |       868 | 50.8
```

**50.8%, not 35.7%.** The published number is **diluted 15.1pp by our own prose sitting in its
denominator.** Note the direction: this class is *understated*, which is why it survived four rounds
unexamined.

**(b) The numerator contains rows that are not identifier failures.**

```
== I2 · CLASS 3 numerator by clause ==
 denominator | numerator | not_found | invalid_id | uuid | placeholder | does_not_exist | missing_required | UNIQ_missing_required
        2472 |       883 |       204 |        172 |  485 |          90 |             87 |               27 |                    27

== I3 · what %missing required% UNIQUELY adds — is it an IDENTIFIER? ==
 'book_chapter_save_draft' is missing required argument(s): ['chapter_id']...   |     5
 'book_chapter_save_draft' is missing required argument(s): ['body']...         |     5
 'composition_conformance_run' is missing required argument(s): ['args']...     |     4
 'glossary_propose_entities' is missing required argument(s): ['items']...      |     3
 'book_chapter_save_draft' is missing required argument(s): ['base_version', 'body']... |     2
 'book_chapter_save_draft' is missing required argument(s): ['base_version']... |     2
 'glossary_propose_entities' is missing required argument(s): ['items']...      |     2
 'composition_outline_node_edit' is missing required argument(s): ['op']...     |     1
 'glossary_adopt_standards' is missing required argument(s): ['book_id']...     |     1
 'book_chapter_save_draft' is missing required argument(s): ['chapter_id', 'base_version']... |     1
 'book_steering_list' is missing required argument(s): ['book_id']...           |     1
```

`%missing required%` uniquely adds 27 rows, of which **roughly 19 are missing *content* arguments** —
`['body']`, `['items']`, `['args']`, `['op']`, `['base_version']`. The error text itself says so:
*"These carry the actual CONTENT (not ids the system already fills)."* **The class's own numerator
contains rows whose error message states they are not identifier failures.** Small — 2.2% of 883 —
but it is exactly the C7 question, and the answer is no.

**(c) Population contamination is unchanged.**

```
== I6 · scripted share of the population the file calls "organic" ==
 organic_failures | scripted_still_in | pct
------------------+-------------------+------
             2892 |              1539 | 53.2

== I5 · CLASS 3 by SCRIPTED vs UNSCRIPTED ==
    pop     | real_errors | id_errors | pct
------------+-------------+-----------+------
 scripted   |        1278 |       701 | 54.9
 unscripted |        1194 |       182 | 15.2
```

**53.2% of the population the file calls "organic" is scripted harness traffic** (`sg-`, `ds-2026-`,
`G-`/`M-`/`W-`/`tle-`, `scenario%`), and the class reads **54.9% on it against 15.2% on real usage** —
a 3.6× split that decides the published figure. Round 3 measured 54.3% / 13.4%. Unchanged.

**C7 RED on class 3, on all three counts.** I do not void it; I bound it: **15.2% on unscripted
traffic, 50.8% on a denominator consistent with class 1's.** The published 35.7% is a blend of two
populations at a ratio nothing controls.

### 4.4 ✅ Class 4 — C7 **GREEN** on the published cell; the vocabulary claim is 🔴 false. **0.0%** (0 / 316)

The reclassification is correct and I verified it could have come back otherwise:

```
== I7 · NULLs inside the window, and the is_error ordering ==
 in_window_assistant_turns | finish_reason_NULL | null_but_is_error | is_error_true | is_error_OVERRIDES_a_finish_reason | unknown_value
---------------------------+--------------------+-------------------+---------------+------------------------------------+---------------
                       316 |                  0 |                 0 |             2 |                                  0 |             0

== I8 · window boundary re-check ==
        first_non_null        | non_null_before
------------------------------+-----------------
 2026-07-19 10:29:19.51552+00 |               0

== I9 · finish_reason x is_error in window ==
 finish_reason  | is_error | count
----------------+----------+-------
 stop           | f        |   256
 awaiting_input | f        |    36
 interrupted    | f        |    19
 streaming      | f        |     3
 error          | t        |     2
```

Zero NULLs, zero unrecognised values, and the `is_error` branch — which is evaluated *first* and could
have masked an absent `finish_reason` — overrides nothing, because both `is_error` rows already carry
`finish_reason='error'`. **The `unrecorded` bucket selects exactly "no recorded outcome" and is
genuinely empty. C7 GREEN.** Round 3's objection is fully closed.

**Two consequences the number carries:**

- **0.0% is not scoreable in the improving direction.** The RUNSTATE marks it ⛔ *already met*, which
  is the correct label. It can only regress.
- **The vocabulary claim at `baseline-metrics.sql:193-194` is false**, per §2.5. The shim maps
  `interrupted → 'interrupted'`; the runtime writes `abandoned_by_user` for that same
  `finish_reason` on 8/8 rows and the shim has no branch that emits it. So the *other* published
  cell — `interrupted_recorded = 19` — is stated in a vocabulary the new arm does not use, and a
  cross-arm comparison of it would read the new arm as 0 by construction. This does not touch the
  0.0% and I do not void it; I record that the cell beside it is not comparable.

---

## 5 · Decision 2 — is the new fingerprint sufficient, or still theatre?

### 5.1 It is no longer theatre. Round 3's exact attack now fails.

```
== FPB-0 · before ==
 9cdacf696d9b5ebb6932d3e8e8062d1c
BEGIN
UPDATE 19       -- UPDATE chat_messages SET finish_reason='stop' WHERE finish_reason='interrupted'
== FPB-1 · after ROUND-3 mutation 1 (finish_reason) — does it move NOW? ==
 a5340c2f543170bd9ce705a869f81a20
ROLLBACK
BEGIN
UPDATE 260      -- UPDATE chat_sessions SET title='F17 monitor verify' WHERE title LIKE 'ds-2026-%'
== FPB-2 · after ROUND-3 mutation 3 (session title) — does it move NOW? ==
 44d6ace0aba4376e1bd25f3a593a0fcf
ROLLBACK
== FPB-3 · after rollback ==
 9cdacf696d9b5ebb6932d3e8e8062d1c
```

**Both move.** Round 3 said the hash *"did not change one character"* under exactly these; it changes
now. `chat_sessions.title` is covered, and the entire decontamination rests on it. This is a real fix
and I credit it in full.

### 5.2 It is still insufficient, and I demonstrated the residual hole

The derivation reads seven columns of `chat_messages`. The hash covers four: `message_id`,
`finish_reason`, `outcome`, `is_error`, `tool_calls`. It does **not** cover `created_at`, `role` or
`session_id` — the window key, the row-type filter, and the entire link to the decontamination table.

```
== FP-0 · fingerprint BEFORE ==
     5862 | 2026-08-04 04:58:09.556834+00 | 9cdacf696d9b5ebb6932d3e8e8062d1c
BEGIN
UPDATE 315   -- created_at -= 30 days for in-window assistant turns (max(created_at) preserved)
UPDATE 19    -- role='tool' where finish_reason='interrupted'
== FP-1 · fingerprint AFTER two mutations of fields the derivation READS ==
     5862 | 2026-08-04 04:58:09.556834+00 | 9cdacf696d9b5ebb6932d3e8e8062d1c
== FP-2 · class 4 recomputed under the mutation ==
 assistant_turns_in_window | interrupted
---------------------------+-------------
                         1 |           0
== FP-3 · class 5 weekly traffic recomputed under the mutation ==
    week    | calls
------------+-------
 2026-08-03 |     7
 2026-07-13 |  2427
 2026-07-06 |  1828
 2026-06-29 |   371
ROLLBACK
== FP-4 · fingerprint AFTER ROLLBACK (must equal FP-0) ==
     5862 | 2026-08-04 04:58:09.556834+00 | 9cdacf696d9b5ebb6932d3e8e8062d1c
```

Class 4's denominator went from **316 to 1**, `interrupted` from **19 to 0**, and class 5's weekly
traffic — the input to every sample-size figure in the run — redistributed across weeks. **All three
of `messages`, `newest` and `corpus_md5` are byte-identical.** `newest` is preserved because moving
rows backward does not change a maximum.

### 5.3 Nothing compares it, and it has already expired

```
$ grep -rn "corpus_md5|corpus fingerprint|9546bb2c9338d126a2b69018121ae29e"
contracts\agent-runtime-baseline\baseline-metrics.frozen.txt
contracts\agent-runtime-baseline\baseline-metrics.sql
docs\specs\...\CP-0-v-metric-round3.md
```

**Zero code references**, against `eval/arms/run_arms.py:65` which `sys.exit`s on a
`catalog_sha256` mismatch. And the frozen output is stale again: `5772 / 9546bb2c…` in
`baseline-metrics.frozen.txt` against `5862 / 9cdacf69…` live. Every published cell moved between the
freeze and my run — class 3 `35.3 → 35.7`, class 4's window `269 → 312` turns, class 1's real-error
denominator `1,649 → 1,673`. **Decision 2 FAIL**, on a strictly smaller surface than round 3.

---

## 6 · Decision 4 — what bound the data supports, at the *corrected* baselines

### 6.1 Correcting class 1 made the bound worse, and that is the finding

Two-proportion, α = .05 two-sided, 80% power. Supply is measured, not assumed:

```
== T1 · UNSCRIPTED traffic rate ==
   first    |    last    | weeks | calls | failures | calls_per_wk | fails_per_wk
------------+------------+-------+-------+----------+--------------+--------------
 2026-05-18 | 2026-08-04 | 11.09 |  2466 |     1353 |        222.3 |        122.0

== T2 · unscripted REAL errors (class 1's denominator supply) ==
 real_errors_unscripted | per_wk
------------------------+--------
                    548 |   49.4

== T3 · class 1 on UNSCRIPTED real errors only ==
 real_errors | carry | pct
-------------+-------+-----
         548 |    53 | 9.7
```

```
target                                                   n/arm  supply/wk  weeks/arm   years
class1 carry-forward  6.0% -> 3.0% (halve)               748.4       49.4       15.1    0.29
class1 carry-forward  6.0% -> 1.0% (-5pp)                210.9       49.4        4.3    0.08
class1 unscripted     9.7% -> 4.85% (halve)              449.0       49.4        9.1    0.17
class3 ident 35.3% -> 25.3% (-10pp)                      330.3       49.4        6.7    0.13
class3 ident 35.3% -> 17.65% (halve)                      96.9       49.4        2.0    0.04
class3 unscripted 15.2% -> 7.6% (halve)                  273.3       49.4        5.5    0.11
class2 nrd 41.6% -> 20.8% (halve) [not scoreable]         76.7      122.0        0.6    0.01
```

**Round 3 computed 83 per arm for carry-forward at 39.4%. At the corrected 6.0% it is 748.** A
smaller true rate is harder to halve. The correction was right and it cost an order of magnitude of
statistical power — this is the honest consequence of the fix and it must be stated beside it.

**And the binding constraint is the frozen side, which cannot grow.** The baseline holds **548**
unscripted real errors in total. The requirement is **748 per arm**. `548 < 748`, so **halving
carry-forward on unscripted traffic is not detectable against this frozen baseline — ever**, not
slowly. It becomes reachable only by scoring against the full 1,673 "organic" real errors, of which
**53.2% is scripted harness traffic** (§4.3c) — i.e. by measuring the harness.

Class 4 is 0.0%; no improvement is expressible. Class 2 is marked ⛔ *not scoreable across arms* by
the run itself. **Class 3 is the only class with a reachable bound (≈97/arm to halve), and it is the
one class that fails C7.**

### 6.2 The brief's two arithmetic facts, checked rather than accepted

```
 0 failures in   3 trials -> 95% upper bound  63.2%
 0 failures in  10 trials -> 95% upper bound  25.9%
 0 failures in  29 trials -> 95% upper bound   9.8%
 0 failures in  30 trials -> 95% upper bound   9.5%
```

Both confirmed. `3/3` bounds a failure rate at **≤63.2%**, useless against a 54.2% baseline; **≤10%
needs 29 consecutive successes**.

### 6.3 The acceptance table still carries three withdrawn numbers

`docs/plans/2026-08-04-agent-runtime-RUNSTATE.md` lines 36–39 publish the corrected figures — 6.0%,
35.3%, 41.6%, 0.0%. Lines 133–139, under the heading *"What the pooled comparison needs, **at the
newly frozen baselines**"*, still read:

```
137:| carry-forward **12.6% → 6.3%** | ≈ **334 failures** | ~1 burst week, or ~7 quiet ones |
138:| not-a-real-dispatch **16.1% → 8%** | ≈ **270 failures** | comparable |
139:| no-interpretable-outcome **90.7% → <5%** | ≈ **30 turns** | days — but this is coverage, not quality |
```

All three baselines are contradicted by the same document's own lines 36–39, and the `n` figures
334 / 270 / 30 are computed from them. **Round 3's item 6 is unfixed, and the label "at the newly
frozen baselines" now makes it an active misstatement rather than a stale one.** No gate is armed, so
the operational harm is nil; a reader landing on the table gets three withdrawn numbers presented as
current.

---

## 7 · The traps

| trap | finding |
|---|---|
| **1 · scoring on `ok=true`** | 🔴 **Live, but materially reduced.** Class 1's success side is still `ok=true` (3,576 rows, none carrying error text). What changed is the exposure: byte-identical repeats fell from 91.4% to **5.0%** of the numerator, so the tautology round 3 identified is gone. The ground-truth channel has not moved: **3 rows in `message_feedback` against 2,720 assistant turns** (0.11%), 7 users, 835 sessions. |
| **2 · guard red over the wrong subject** | ⚖️ **Substantially closed.** Round 3's instance — `%budget%` firing on a caller's own argument name, `%not permitted%` on a pydantic constant — is **gone**, verified at 0 false positives against 36 `source='tool'` failures. The residual is class 3, whose numerator contains 19 rows whose own error text says they are content arguments, not identifiers. |
| **3 · self-derived denominator** | 🔴 **Live, and it is where the partition claim failed.** `307` is derived from the record's own row counts and reads "complete"; the source of truth is **315** and leaves **5 tools unaccounted**. |
| **4 · the comparison that cannot be computed** | 🔴 **Confirmed, unchanged.** `declaration` == `tool` on **201/201**, absent on the other 7,447. `runtime_variant='legacy'` on **all 5,862** messages and **all 201** instrumented calls. **Zero `agentruntime` rows exist.** |

---

## 8 · The bound table

| class | published | reproduces? | C7 | value on the population the name states | denominator | contamination handling | n/arm for the claimed improvement |
|---|---|---|---|---|---|---|---|
| **carry-forward** | **6.0%** (101/1,673) | ✅ exact at my fingerprint, not at the frozen one | 🟢 **GREEN** | **6.0%** — 0 breaker prose, 0 meta tools, 0 null errors, 5 same-args repeats in 101 | real errors = 1,673; **36 NULL-error failures silently dropped** by three-valued logic | F17 only; blank-arg no longer excluded anywhere | **748** to halve (was 83 at the withdrawn 39.4%) — **frozen side supplies 548** |
| **not-a-real-dispatch** | **41.4%** (1,198/2,892) | ✅ exact | 🟢 **GREEN** (lower bound, declared) | **41.4%**; 0 false positives on 36 `source='tool'` failures, 19/26 recall on `source='breaker'` | 2,892 = all organic failures; blank-arg exclusion removes **0** rows while still declared in the header | `%repeated%` dead (0 rows); meta clause adds 0 unique | 77 — but the run marks it ⛔ not scoreable across arms |
| **identifier resolution** | **35.7%** (883/2,472) | ✅ exact | 🔴 **RED** | **50.8%** (868/1,709) on class 1's real-error definition; **15.2%** (182/1,194) on unscripted traffic | 2,472, of which **763 (30.9%) is our own breaker prose** — a second, different "REAL errors" | none beyond `%already ran this turn%`; **53.2% of "organic" is scripted** | 97 to halve — the only reachable bound in the set |
| **no-recorded-outcome** | **0.0%** (0/316) | ✅ exact; window date verified to the hour | 🟢 **GREEN** | **0.0%** — 0 NULLs, 0 unknown values, `is_error` overrides nothing | in-window assistant turns = 316 | column-age artefact resolved; `interrupted` correctly reclassified as recorded | **not expressible** — 0.0% cannot improve; the adjacent `interrupted=19` cell is stated in a vocabulary the runtime does not write |

---

## 9 · What must change for a PASS, stated as facts not fixes

Recorded so a later round can be checked against something. Round 3's items 1, 2 and 3 are **closed**.

1. Class 3's denominator calls 2,472 rows "REAL errors" while class 1 calls 1,673 rows the same
   thing; 763 of the difference is our own breaker prose, and removing it moves the class from 35.7%
   to 50.8%. Its numerator additionally contains 19 rows whose own error text states they are content
   arguments, not identifiers.
2. The corpus fingerprint does not cover `created_at`, `role` or `session_id`. A rolled-back mutation
   of the first two moved class 4 from 316 turns to 1 and left the hash byte-identical. Nothing in
   the repository compares the hash, and it has expired twice in two rounds.
3. A tool is recorded as both advertised and withheld in the **same pass** on 28 (message, pass, tool)
   triples. 21.2% of withheld records carry no `pass` key. Five tools of the frozen 315 are neither
   advertised nor withheld in the turn offered as the exact-partition proof.
4. `declaration` equals `tool` on 201 of 201 rows and is absent on 7,447; `runtime_variant` is
   `legacy` on every row in the database. The matched-pair join CP-0 exists to enable has no rows on
   its new side and, where it has rows, is a join on tool name.
5. A failure with `error IS NULL` is dropped from class 1 by three-valued logic and kept by class 2
   (36 rows), against the `_calls` comment that the classes "cannot drift between metrics."
6. `baseline-metrics.sql:44-47` declares the blank-argument exclusion globally; the implemented
   clause removes 0 of 569 such rows.
7. `baseline-metrics.sql:193-194` claims the shim states the baseline in the runtime's vocabulary;
   the runtime writes `abandoned_by_user` where the shim writes `interrupted`, on 8 of 8 rows.
8. RUNSTATE lines 133–139 present 12.6% / 16.1% / 90.7% as *"the newly frozen baselines"*, all three
   contradicted by lines 36–39 of the same file.
9. The frozen baseline holds 548 unscripted real errors; halving carry-forward at its corrected 6.0%
   requires 748 per arm.

---

*Authority exercised, and mostly **not** in the direction of voiding. I rule **class 3 (35.7%)**
unsound as published — its denominator is 30.9% our own prose and its population is 53.2% harness
traffic; I bound it at **15.2%** unscripted and **50.8%** on a consistent denominator. I rule the
claim that a turn's advertised and withheld sets **partition the catalogue exactly** to be **false**:
the union is 317 not 307, the sets overlap within a single pass on 28 triples, and 5 of the frozen
315 tools are unaccounted. Any PASS resting on either is void.*

*I **withdraw** round 3's rulings against **class 1** and **class 4**: both now select the population
their names state, demonstrated by decomposition rather than asserted by construction. I rule
**class 2** sound as the lower bound it declares itself to be, verified against an independent ground
truth rather than against its own prose. **C7 is GREEN on three of four classes** — the first time any
class has passed it.*

*Recorded in fairness: the carry-forward correction is right and cost the run an order of magnitude of
statistical power, which is what an honest correction to a smaller true rate does; the fingerprint now
defeats the exact attack that broke it in round 3; `source` has become good enough to grade the
classifier that predates it; and `latency_unmeasured` is the right call for a field that cannot be
measured everywhere. The instrument is materially better than it was. It is not yet frozen, one class
still does not measure what it is named for, and the comparison the checkpoint exists to enable still
has zero rows on its new side.*
