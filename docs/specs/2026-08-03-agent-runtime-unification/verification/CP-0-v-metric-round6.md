# CP-0 · V-METRIC — verdict, ROUND 6

*Artifact frozen at `6ca3b71e2`, working tree clean (`git status --porcelain` empty). Verified
2026-08-04 against `loreweave_chat` in `infra-postgres-1`. Subject: the instrument, never the
feature. No tracked file was modified; no write of any kind was made to the database this round —
every query below is read-only. This round is narrow by instruction: class 3, the 28 same-pass
triples, the five unaccounted tools, and a restatement of decision 4.*

**Corpus fingerprint at the time of this verification**

```
$ docker exec -i infra-postgres-1 psql -U loreweave -d loreweave_chat -A -F'|' -c "SELECT ..."
messages|newest|corpus_md5
5862|2026-08-04 04:58:09.556834+00|9cdacf696d9b5ebb6932d3e8e8062d1c
```

**And this time it is the frozen one.** `baseline-metrics.frozen.txt` now opens with
`5862 / 2026-08-04 04:58:09.556834+00 / 9cdacf696d9b5ebb6932d3e8e8062d1c` — byte-identical to the
live corpus. Round 5's standing complaint that the committed frozen output had expired for the
second consecutive round is **closed**: the derivation was re-run at the current corpus and every
published cell in the file now matches what the file's own query produces today. I record this
without being asked, because I raised it twice.

---

## 1 · Verdict

| | |
|---|---|
| **OVERALL** | 🔴 **FAIL** — unchanged in outcome, materially narrower in surface. |
| **(1) class 3 · C7** | 🔴 **RED** — but on **one** of round 5's three counts, not three. The denominator defect is **fully closed** (set-identical to class 1's, zero rows either way). The numerator is where it now fails, and **worse than I reported in round 5**: at least **90 of 841** rows are not identifier failures, not 19. |
| **(2) the 28 same-pass triples** | 🟢 **HISTORICAL ARTIFACT.** All 28 predate the reconciliation. **Zero** offending rows exist after `2026-08-04 03:14:38`, against **609** pass-stamped withheld records of comparable opportunity. The builder is entitled to treat this as history — and is *not* entitled to treat the corpus as clean; 477 of 1,565 withheld records remain uninterpretable. |
| **(3) the five unaccounted tools** | 🟢 **LEGITIMATELY ABSENT — round 5's leg of the refutation is WITHDRAWN.** The five are byte-identical to `INTENT_GATED_SETUP_TOOLS`, filtered out of the turn catalogue *itself* before any narrowing stage runs. **CP-0.2 is complete on its own terms.** |
| **(4) decision-4 restatement** | 🔴 **REVISED, and slightly worse.** The frozen side holds **522** unscripted real errors, not 548, against **743** needed per arm. Deficit **221**. Conclusion unchanged: halving carry-forward is not detectable against this baseline, ever. |

### The falsifier — what I looked for that would have made each of these go the other way

**On class 3** I set out to confirm the fix and close the class. The denominator test I ran was the
strongest available — not "does it produce 1,673" but "is it the *same 1,673 rows*", by symmetric
difference in both directions. It came back `0 / 0`. **Had a single row differed I would have failed
the denominator.** None did, so I turned to the numerator and decomposed every clause, then read the
error strings behind each clause's unique contribution. That is where it failed, and it failed on a
family I did not examine in round 5 — so this is a finding against my own prior work as much as
against the builder's.

**On the 28 triples** I set out to prove them **live**, because that is the more damaging answer and
because a verifier who only ever confirms his own prior findings is not verifying. I looked for one
same-pass overlap in a row written after the last observable deploy boundary. **A single such row
would have made this a live defect.** There are none, across 609 pass-stamped withheld records — an
opportunity within 2% of the pre-period's 623. Then I found the decisive corroboration by accident:
the two worst offenders carry the *identical eleven tools* at 6.2%, which is verbatim the number and
the description in the reconciliation's own docstring. Code written in response to rows cannot
predate them.

**On the five tools** I set out to confirm a recording gap, which is what I implied in round 5. I
found instead a frozenset in `tool_discovery.py` whose five members are exactly the five names, with
a comment stating they are removed from the turn catalogue before anything else reads it. **I
withdraw that leg.** I also found that the premise behind it was never sound: on the median
instrumented turn, advertised ∪ withheld covers ~30–90 of 315 tools, and the turn the partition
claim was built on is the single most-covering turn in the entire corpus.

---

## 2 · Ruling (1) — CLASS 3

### 2.0 It reproduces exactly

```
$ docker exec -i infra-postgres-1 psql -U loreweave -d loreweave_chat -f - \
    < contracts/agent-runtime-baseline/baseline-metrics.sql

== 3 · IDENTIFIER RESOLUTION, as a share of REAL errors ==
  scope  | real_errors | id_errors | pct
---------+-------------+-----------+------
 organic |        1673 |       841 | 50.3
```

**50.3% (841 / 1,673).** Denominator **1,673**, identical in cardinality to class 1's
`organic_real_errors`. My round-5 prediction was 50.8% (868/1,709); the 27-row numerator difference
is the removed `%missing required%` clause and the 36-row denominator difference is the NULL-error
three-valued-logic hole, which class 1 and class 3 now share. Both differences are accounted for.

### 2.1 ✅ The denominator defect is CLOSED — proven by set identity, not by count

Count identity is not identity. I tested the row sets in both directions:

```
== R6-1 · SET IDENTITY: class1 real-error rows vs class3 denominator rows (organic) ==
 class1_rows | class3_rows | in_c1_not_c3 | in_c3_not_c1
-------------+-------------+--------------+--------------
        1673 |        1673 |            0 |            0
```

**Zero rows in either direction.** The two classes now select the same population, keyed on
`(message_id, ord)`. Round 5's finding — 763 rows (30.9%) of our own breaker prose, and a second,
weaker definition of "REAL errors" living in the same file — is gone:

```
== R6-2 · residual BREAKER PROSE inside the class-3 denominator (must be 0) ==
 denom | you_have_already | times_this_turn | any_this_turn | already_ran | do_not_ask | repeated | meta_tools | source_breaker
-------+------------------+-----------------+---------------+-------------+------------+----------+------------+----------------
  1673 |                0 |               0 |             0 |           0 |         15 |        0 |          0 |              2
```

**0 / 0 / 0 / 0 / 0 on every clause the filter names.** I record the two residues honestly and do
*not* count them against class 3, because they are **shared with class 1, which I ruled GREEN**:

- **15 rows** matching `%Do not ask to run it again%` — class 2 calls this our own prose; class 1's
  real-error filter does not list it, so both class 1 and class 3 retain them. **None of the 15 is
  in class 3's numerator** (R6-4), so they dilute rather than inflate.
- **2 rows** carrying `source='breaker'` — both `missing required argument(s)` texts. **Neither is
  in the numerator** (R6-5).

If these are a defect they are a defect in class 1, which I already passed, and correcting them
moves class 3 *up*, not down.

### 2.2 🔴 The numerator is where C7 fails — and by more than I reported in round 5

```
== R6-3 · CLASS 3 NUMERATOR by clause, with UNIQUE contribution of each ==
 denom | numerator | c_not_found | c_invalid_id | c_uuid | c_placeholder | c_does_not_exist |
  1673 |       841 |         204 |          172 |    472 |            90 |               85 |
 uniq_not_found | uniq_invalid_id | uniq_uuid | uniq_placeholder | uniq_does_not_exist | still_missing_required
            204 |              80 |       380 |                0 |                  85 |                     27
```

Two clauses hold rows whose own error text says they are not identifier failures.

#### (a) 85 rows — `%does not exist%` is matching OUR OWN REMEDIATION SENTENCE

```
== R6-11 · which CLAUSE admits the "unknown kind" rows? ==
 unknown_kind_rows | via_does_not_exist | via_uuid | via_not_found | via_invalid_id | via_placeholder
-------------------+--------------------+----------+---------------+----------------+-----------------
                85 |                 85 |        0 |             0 |              0 |               0

== R6-12 · FULL text of one such row ==
 no entities were created — 4 of 4 item(s) failed. Reasons: unknown kind: character; unknown kind:
 power_system; unknown kind: event. An 'unknown kind' means that category does not exist in this
 book yet — create the categories first (glossary_adopt_standards to adopt the system kinds, or
 glossary_propose_kinds for custom ones), then retry.
```

**All 85 enter through `%does not exist%` and through no other clause.** The failure is
`unknown kind: character` — an ontology **category** that has not been adopted. The phrase that
admits it appears nowhere in the failure; it appears only in the *help text we append to our own
error*: "An 'unknown kind' means that category does not exist in this book yet."

This is the same defect class the round-5 correction was about — **our own prose deciding a metric**
— relocated from the denominator into the numerator. The file's stated reason for removing
`%missing required%` was that "the error text itself says they are not ids." The error text here
says the failing thing is a *category*. The rule was applied to a 27-row clause and not to an 85-row
one.

**I missed this in round 5.** Round 5's `I2` reported `does_not_exist = 87` and I did not decompose
it. The family was present then and I record that as my error, not a regression.

#### (b) 5 rows — `%invalid%id%` is not an identifier test, and I proved it

```
== R6-14 · PATTERN PROBE: does %invalid%id% fire on text with NO identifier at all? ==
 a_valid_list | b_no_second_valid | c_provide | d_trailing_only | e_real_id_field
--------------+-------------------+-----------+-----------------+-----------------
 t            | f                 | t         | f               | t
```

`'invalid arguments — Input should be a valid list' ILIKE '%invalid%id%'` → **true**, because the
word **`valid` ends in `id`**. The pattern means "contains *invalid*, and later contains the bigram
*id*" — which any second `valid`, `invalid`, or `provide` satisfies. It is not a test for an
identifier. The rows it catches on that basis alone:

```
== R6-17 (extract) · uniq-invalid_id rows naming NO id field at all ==
 invalid arguments for kg_list_templates — `scope.literal['system','user']`: Input should be
 'system' or 'user' (you sent a str); `scope.list[literal['system','user']]`: Input should be a
 valid list (you sent a str). Fix the argument and call the tool again.                       | 5
```

An enum-value error on a `scope` field. No identifier is named, mentioned, or implied.

#### (c) 64 rows — the family the builder just removed, under a different phrasing

```
== R6-13 · "you sent a dict" family ==
 invalid arguments for translation_coverage — `book_id`: Field required (you sent a dict).      | 22
 invalid arguments for jobs_get — `service`: Field required (you sent a dict); `job_id`: Field
   required (you sent a dict).                                                                  | 19
 invalid arguments for translation_job_status — `job_id`: Field required (you sent a dict).      | 13
 invalid arguments for translation_start_extraction — `book_id`: ...; `chapter_ids`: ...         |  7
 invalid arguments for translation_list_versions — `book_id`: ...; `chapter_id`: ...             |  2
 invalid arguments for translation_segment_status — `book_id`: ...; `chapter_id`: ...;
   `target_language`: Field r...                                                                 |  1
```

`Field required` **is** pydantic's phrasing of "missing required argument". These 64 rows are the
same failure mode as the 27 removed under `%missing required%`, admitted through `%invalid%id%`
instead. And `(you sent a dict)` shows what actually happened: the model wrapped its arguments, so
*every* field reads as missing — which is why `jobs_get` names **`service`**, not an identifier, in
19 of the 64, and `translation_segment_status` names `target_language`.

I hold this one as a judgement call rather than an error, and I report the class both ways.

### 2.3 The corrected values

```
== R6-19 · CLASS 3 exact corrected variants ==
 denom | published_num | published_pct | num_less_hard | pct_less_hard | num_less_all | pct_less_all
-------+---------------+---------------+---------------+---------------+--------------+--------------
  1673 |           841 |          50.3 |           751 |          44.9 |          687 |         41.1
```

| reading | numerator | denominator | value |
|---|---|---|---|
| **published** | 841 | 1,673 | **50.3%** |
| less the 90 **unambiguous** non-identifier rows (85 unknown-kind + 5 enum) | 751 | 1,673 | **44.9%** |
| less those **and** the 64 `Field required` shape failures | 687 | 1,673 | **41.1%** |

### 2.4 Population contamination — unchanged, and now heavier

```
== R6-20 · CLASS 3 by SCRIPTED vs UNSCRIPTED, on the NEW denominator ==
    pop     | real_errors | id_errors | pct_published | id_corrected | pct_corrected
------------+-------------+-----------+---------------+--------------+---------------
 scripted   |        1151 |       690 |          59.9 |          637 |          55.3
 unscripted |         522 |       151 |          28.9 |          114 |          21.8
```

**68.8% of the new denominator (1,151 / 1,673) is scripted harness traffic**, up from round 5's
53.2% — removing the breaker prose removed proportionally more unscripted rows than scripted ones.
The class reads **59.9% on the harness against 28.9% on real usage**. The published figure is a
blend of two populations at a ratio nothing controls, and the ratio moved this round without anyone
choosing to move it.

### 2.5 Ruling on (1)

**🔴 C7 RED on class 3.** Precisely which rows do not belong, as instructed:

1. **85 rows** whose error is `no entities were created — … unknown kind: <X>`, admitted **solely**
   by `%does not exist%` matching the explanatory clause *"An 'unknown kind' means that category
   does not exist in this book yet"* that we append to our own error. The failing object is an
   ontology category, not an identifier. **10.1% of the numerator.**
2. **5 rows** whose error is `invalid arguments for kg_list_templates — scope.literal[…]: Input
   should be 'system' or 'user'`, admitted by `%invalid%id%` matching the `id` inside the word
   `valid`. No identifier appears in the row.
3. **Contested, reported separately: 64 rows** of `Field required (you sent a dict)` — pydantic's
   spelling of the `%missing required%` family removed this round, of which at least 20 name a
   non-identifier field (`service`, `target_language`) as equally missing.

**The denominator half of round 5's RED is withdrawn in full.** It is fixed, and fixed properly —
set identity, not count agreement. Class 3 is the one class where I have now failed the same number
twice for different reasons, and the honest summary is that each round found a real defect one layer
deeper than the last.

---

## 3 · Ruling (2) — THE 28 SAME-PASS TRIPLES

### 3.1 The offenders, dated

```
== R6-21 · SAME-PASS overlap triples ==
 triples | distinct_passes | distinct_messages |           earliest            |           latest
---------+-----------------+-------------------+-------------------------------+-----------------------------
      28 |               4 |                 4 | 2026-08-04 01:37:44.872631+00 | 2026-08-04 03:14:38.1422+00

== R6-22 · the offending MESSAGES ==
              message_id              |          created_at           | overlap_triples |    stages
--------------------------------------+-------------------------------+-----------------+--------------
 82cda3d9-6f07-4cce-9ab9-454e9704b019 | 2026-08-04 01:37:44.872631+00 |              11 | token_budget
 8dad348e-5e5b-4d65-8fc1-92963ed42734 | 2026-08-04 02:50:41.281961+00 |              11 | token_budget
 732760c4-d11f-4e84-bf7d-bd7cd1af394b | 2026-08-04 03:04:56.594666+00 |               1 | token_budget
 4ce53500-cd3c-40fd-8f5c-7136ecf7482a | 2026-08-04 03:14:38.1422+00   |               5 | token_budget
```

```
== R6-36 · CONTROL: are there ANY offending rows after 2026-08-04 03:14:38? ==
 offending_rows_after_last_offender
------------------------------------
                                  0
```

### 3.2 Deploy boundaries established from the data alone

I did not read a commit log. Every boundary below is the first appearance of a structural key in the
written rows:

```
== R6-26 · FIRST appearance of every tool_calls element key ==
 source / declaration / latency_ms / runtime_variant  |  2026-08-03 23:47:17   ← instrument v1
 source_inferred                                       |  2026-08-03 23:50:36
 latency_unmeasured                                    |  2026-08-04 02:42:37   ← D4

== R6-27 · FIRST appearance of every withheld_tools element key ==
 stage / reason / tool                                 |  2026-08-04 00:24:57   ← D2 (withheld v1)
 pass                                                  |  2026-08-04 01:31:10   ← D3 (pass key)

== R6-29 · withheld STAGE vocabulary over time ==
 failure_breaker    |   13 | first 2026-08-04 00:24:57
 token_budget       | 1354 | first 2026-08-04 00:48:24
 hot_seed           |  197 | first 2026-08-04 04:06:34   ← D5
 suppress_tool_list |    1 | first 2026-08-04 04:56:28   ← D6
```

`D5 = 2026-08-04 04:06:34.352759` is corroborated by a second, independent signature in the same
row: it is the first message in the corpus whose withheld records carry `pass = 1`, and every
message after it does so, while **no** message before it does:

```
== R6-43 (extract) · min withheld pass stamp per message ==
 01:31 eaa6f082 min 4 | 01:37 82cda3d9 min 3 | 01:50 d0c8c43b min 3 | 01:56 18fd5eb4 min 3
 02:42 cda298e8 min 3 | 02:50 8dad348e min 2 | 03:04 732760c4 min 2 | 03:14 4ce53500 min 4
 03:19 ba80e424 min 7 | 04:06 c92cc5d8 min 1 | 04:13 bbae64a7 min 1 | … min 1 thereafter, always
```

`pass = 1` is what `max(len(self._passes), 1)` produces for a narrowing decided during **surface
assembly, before any pass exists** — the `ContextVar` request-scoped sink. Its first appearance and
`hot_seed`'s first appearance are the same message, to the microsecond. **D5 is a real deploy.**

### 3.3 The partition

```
== R6-35b · PARTITION of offending rows by created_at ==
                     label                     | messages | pass_stamped_records | same_pass_overlaps | offending_messages | pct
-----------------------------------------------+----------+----------------------+--------------------+--------------------+------
 A · 01:31->03:14  pass-key era, pre-clean-run |        8 |                  623 |                 28 |                  4 | 4.49
 B · 03:19->04:06  gap                         |        1 |                    1 |                  0 |                  0 | 0.00
 C · 04:06:34+      hot_seed deploy onward     |       16 |                  609 |                  0 |                  0 | 0.00
```

**Opportunity is equal within 2%**: 623 pass-stamped withheld records before, 609 after
(ratio 0.978). This is the test that matters — a clean post-period proves nothing if the post-period
had no material to fail on. It had the same material.

```
== R6-38 · message-level hypergeometric ==
  P(all 4 offending messages land in the 8 pre-messages by chance) = C(8,4)/C(25,4) = 70/12650 = 0.00553

== R6-39 · record-level binomial, pooled rate, ignoring clustering ==
  pooled same-pass rate over both eras = 28/1232 = 0.02273
  expected same-pass overlaps in the 609 post-04:06 records = 13.8
  P(observe 0 | pooled rate) = 8.310e-07
```

I report the **message-level p = 0.0055** as the honest figure; overlaps cluster within a message,
so the record-level `8.3e-07` overstates the evidence.

### 3.4 The decisive corroboration — the reconciliation was written *about* these rows

```
== R6-34 · are the offending tool NAMES the same set across the two 178-record turns? ==
 82cda3d9 | glossary_deep_research, kg_entity_edge_timeline, kg_graph_query, kg_list_templates,
            kg_ontology_propose, kg_sync_available, kg_triage_list, kg_triage_resolve,
            memory_recall_entity, memory_search, memory_timeline
 8dad348e | glossary_deep_research, kg_entity_edge_timeline, kg_graph_query, kg_list_templates,
            kg_ontology_propose, kg_sync_available, kg_triage_list, kg_triage_resolve,
            memory_recall_entity, memory_search, memory_timeline

== R6-33 (extract) · rate per message ==
 01:37 82cda3d9 | 178 records | 11 overlaps | 6.2%
 02:50 8dad348e | 178 records | 11 overlaps | 6.2%
```

`instrument.py:378-405` states the reconciliation's own evidence: *"Three rounds of live
verification found the same **eleven tools** recorded as withheld while advertised on every pass
(**6.3% → 6.2% → 6.2%**, unchanged, **the same names each time**)."*

**Eleven tools. 6.2%. The identical name set on both turns.** These are those rows. A function whose
docstring cites a measurement cannot have been running when the measurement was taken.

### 3.5 Ruling on (2)

**🟢 HISTORICAL ARTIFACT.** All 28 triples were written **before** the reconciliation shipped, in the
window `01:37:44 → 03:14:38`, which is bounded above by the observable deploy at `04:06:34`. The
builder is entitled to treat these rows as history and **not** as an open defect.

**The builder is not, however, entitled to treat the frozen corpus as clean.** The rows are still in
it, and two further residues are structurally unrepairable by the reconciliation:

```
== R6-37b · the NO-PASS withheld records (EXISTS, no fan-out) ==
 no_pass_records | also_advertised_somewhere_in_turn |            first             |             last
-----------------+-----------------------------------+------------------------------+-------------------------------
             332 |                                30 | 2026-08-04 00:24:57.84167+00 | 2026-08-04 00:53:12.140674+00
```

- **332 records carry no `pass` key** (all before D3). `withheld_json` keeps them by design —
  `by_pass.get(None, set())` is empty, so nothing is ever dropped. **30 of them name a tool that is
  advertised somewhere in the same turn** and can never be reconciled.
- **145 records are stamped at a pass that does not exist** — `d0c8c43b` (47 records, all `pass 3`,
  turn has 2 passes) and `18fd5eb4` (98 records, same). These are the `len + 1` off-by-one era that
  `record_withheld`'s own comment documents. They are also kept, for the same reason.

**477 of 1,565 withheld records (30.5%) are therefore either uninterpretable or unreconcilable.**
That is a property of the frozen artifact, not of the current code.

**My falsifier for this ruling, stated so a later round can execute it:** *one* same-pass overlap in
any row with `created_at > 2026-08-04 04:06:34.352759` overturns "historical" and makes it live.
Query `R6-36` with that bound is the test.

---

## 4 · Ruling (3) — THE FIVE UNACCOUNTED TOOLS

### 4.1 Corpus-wide, only four of the frozen 315 are unaccounted — and one of the five is not

```
== R6-41 · do the 5 appear ANYWHERE in advertised / withheld / tool_calls? ==
           name           | ever_advertised | ever_withheld | times_called_all_time
--------------------------+-----------------+---------------+-----------------------
 glossary_adopt_standards | t               | f             |                    75
 glossary_book_sync_apply | f               | f             |                     0
 glossary_plan            | f               | f             |                     6
 glossary_propose_batch   | f               | f             |                    15
 glossary_propose_kinds   | f               | f             |                     6

== R6-44 · frozen-snapshot tools NEVER advertised and NEVER withheld anywhere in the corpus: 4 ==
    glossary_book_sync_apply
    glossary_plan
    glossary_propose_batch
    glossary_propose_kinds
```

`glossary_adopt_standards` **is** advertised, in three turns. Round 5's "five unaccounted" was
therefore never a property of the instrument; it was a property of **one turn**.

### 4.2 The five ARE a named set in the code — and they are removed before any narrowing runs

`services/chat-service/app/services/tool_discovery.py:442-448`:

```
INTENT_GATED_SETUP_TOOLS: frozenset[str] = frozenset({
    "glossary_adopt_standards",   # adopt genre/kind STANDARDS (the confirmed over-reach)
    "glossary_propose_kinds",     # batch-propose MANY kinds at once (build an ontology)
    "glossary_plan",              # planner: propose a WHOLE ontology behind one card
    "glossary_propose_batch",     # mixed batch ontology ops
    "glossary_book_sync_apply",   # bulk-reconcile adopted standards
})
```

**Byte-identical to round 5's five names.** Its comment states the mechanism: *"these are filtered
out of the turn catalog **ITSELF** (the one object all three reach-paths read) UNLESS the turn is
world-setup intent — signalled by `glossary_shaping` being injected (pinned OR the intent router
matched the message)."*

And the turn the partition claim was made about had the gate closed:

```
== R6-52 · session skill/pin state ==
   msg    |          created_at           | enabled_skills | pinned_legacy_tools | shaping_pinned | n_activated | setup_tools_activated
----------+-------------------------------+----------------+---------------------+----------------+-------------+-----------------------
 c92cc5d8 | 2026-08-04 04:06:34.352759+00 | {}             | {}                  | f              |           0 |                     0
```

**They are legitimately absent from the turn's candidate set before any narrowing runs.** They were
never in the object the narrowing stages operate on, so there is nothing for a withheld record to
report. **This is not a recording gap.**

### 4.3 The premise behind the question was itself wrong

```
== R6-51 · distinct advertised | distinct withheld, per instrumented turn (extract) ==
 23:47 03e0ca0b | 30 |   0        03:12 56bd4103 | 32 |   0
 00:04 6b1dc5c4 | 50 |   0        03:14 4ce53500 | 37 |  28
 00:53 7882d01a | 33 | 303        03:18 9662922b | 51 |   0
 01:37 82cda3d9 | 64 | 178        04:06 c92cc5d8 | 32 | 286   ← the partition-claim turn
 02:50 8dad348e | 65 | 178        04:13 bbae64a7 | 23 |  36
 03:04 732760c4 | 38 |  28        04:58 43566df8 | 42 | 121
```

On the **median** instrumented turn, advertised ∪ withheld covers roughly **30–90 of 315** tools —
200 to 280 are in neither list, routinely. `c92cc5d8` (32 + 286) is the **single most-covering turn
in the corpus**. "Five unaccounted" was an artifact of selecting the one turn where the number
happened to be small enough to look like a completeness statement.

`withheld_tools` records the narrowings performed by the four instrumented stages — `token_budget`,
`hot_seed`, `failure_breaker`, `suppress_tool_list`. It was never a complement of the advertised set
against the catalogue, and `withheld_json`'s own docstring says so: *"The column answers 'was this
tool absent from the model's surface on that pass' — nothing about which stage wanted it gone."*

### 4.4 Ruling on (3)

**🟢 LEGITIMATELY ABSENT. CP-0.2 is COMPLETE on its own terms.** I **withdraw** round 5's third leg
of the partition refutation. The other two legs stand unchanged: the union is **317**, not 307
(`307` is `13 + 294`, a count of records in two JSON arrays); and the same-pass overlap was real,
now dated as historical per §3.

**One bounded residual I do not close, stated with its falsifier.** In `9662922b`, `ba80e424` and
`bfdcc100` (03:18–03:20), `glossary_adopt_standards` is advertised on **every pass** while
`enabled_skills = {}`, `pinned_legacy_tools = {}` and `activated_tools = ∅` — and it is in
`DISCOVER_ONLY_HIGH_IMPACT`, so it cannot be hot-seeded. The only remaining path onto that wire is
the intent router opening the gate, which would have admitted **all five** to the turn catalogue:

```
== R6-48 · turns advertising glossary_adopt_standards ==
 03:18 9662922b passes 1-9 | adopt_standards t | plan f | propose_batch f | propose_kinds f | book_sync_apply f
 03:19 ba80e424 passes 1-7 | adopt_standards t | plan f | propose_batch f | propose_kinds f | book_sync_apply f
 03:20 bfdcc100 passes 1-6 | adopt_standards t | plan f | propose_batch f | propose_kinds f | book_sync_apply f
```

Yet the other four appear in neither list, and `9662922b` and `bfdcc100` carry **no withheld records
at all**. *Falsifier:* a withheld record naming `glossary_plan`, `glossary_propose_batch` or
`glossary_book_sync_apply` in a gate-open turn closes this; its continued absence across future
world-setup turns makes it a narrowing that registers nowhere.

**Separately, on the snapshot's scope, which is a fact rather than a defect:**

```
== R6-45 · corpus tools NOT in the frozen snapshot: 9 ==
    chat_search_sessions, confirm_action, conversation_search, glossary_confirm_action,
    glossary_propose_entity_edit, load_skill, run_subagent, workflow_list, workflow_load
```

The snapshot is `user_overlay: false`, frozen `2026-08-03T23:01:35` — the **gateway** catalogue only.
It therefore excludes the seven local runtime primitives *and* two chat-service frontend tools
registered in `frontend_tools.py:640`, one of which, `glossary_propose_entity_edit`, was called
**101 times** and is the tool behind class 3's `placeholder_id` errors. The frozen 315 is not the
live surface, in either direction.

---

## 5 · Decision-4 restatement — REVISED

Round 5 stated: *the frozen side holds 548 unscripted real errors against ~748 needed per arm.* Both
figures move slightly this round, and both move in the wrong direction.

```
== R6-49 · unscripted supply on the class-1 real-error predicate (now shared with class 3) ==
 unscripted_real_errors | scripted_real_errors | total_real_errors
------------------------+----------------------+-------------------
                    522 |                 1151 |              1673

== R6-50 · class 1 carry-forward on UNSCRIPTED real errors ==
 unscripted_real_errors | carry | pct
------------------------+-------+------
                    522 |    53 | 10.2
```

```
== R6-53 · two-proportion sample size, alpha=.05 two-sided, power=80% ==
target                                           n/arm     supply  weeks/arm
class1 carry-forward 6.0% -> 3.0% (halve)        743.2       47.1       15.8
class1 carry-forward 6.0% -> 1.0%                208.7       47.1        4.4
class1 UNSCRIPTED 10.2% -> 5.1% (halve)          428.4       47.1        9.1
class3 published 50.3% -> 25.15% (halve)          57.1       47.1        1.2
class3 corrected 44.9% -> 22.45% (halve)          68.4       47.1        1.5
class3 UNSCRIPTED 28.9% -> 14.5% (halve)         126.4       47.1        2.7

== R6-54 · the frozen side cannot grow ==
  unscripted real errors in the FROZEN baseline (class-1 predicate, organic) = 522
  n/arm required to halve class-1 carry-forward at 6.0%                      = 743.2
  deficit                                                                    = 221.2
```

**Restated: the frozen side holds 522 unscripted real errors — not 548 — against 743 needed per
arm.** The 26-row reduction is a consequence of this round's own fix: the real-error predicate is
now shared, and the shared version is stricter than the one I used in round 5. The correction was
right and it cost supply, exactly as the carry-forward correction did in round 5.

**The conclusion is unchanged and is now slightly harder:** `522 < 743`. No future traffic adds to a
frozen side. **Halving carry-forward on unscripted traffic is not detectable against this baseline
— ever, not slowly.** It becomes reachable only by scoring against the full 1,673 "organic" real
errors, of which **68.8% is scripted harness traffic** (§2.4) — i.e. by measuring the harness. That
share rose from 53.2% to 68.8% this round, so the escape route got worse too.

Class 4 is 0.0% and no improvement is expressible. Class 2 is marked ⛔ *not scoreable across arms*
by the run itself. **Class 3 remains the only class with a reachable bound (57–126 per arm depending
on population), and it remains the one class that fails C7.** That coupling has now survived three
rounds.

---

## 6 · Summary of the four classes at this fingerprint

| class | published | reproduces? | C7 this round | change from round 5 |
|---|---|---|---|---|
| **1 · carry-forward** | **6.0%** (101/1,673) | ✅ exact, **and now at the frozen fingerprint** | 🟢 GREEN | unchanged |
| **2 · not-a-real-dispatch** | **41.4%** (1,198/2,892) | ✅ exact | 🟢 GREEN (declared lower bound) | unchanged |
| **3 · identifier resolution** | **50.3%** (841/1,673) | ✅ exact | 🔴 **RED** — 90 of 841 numerator rows are not identifier failures; 44.9% corrected, 41.1% strictest | denominator **fixed**; numerator defect **larger** than round 5 found |
| **4 · no-recorded-outcome** | **0.0%** (0/316) | ✅ exact | 🟢 GREEN | unchanged |

---

## 7 · Stated falsifier

**What I looked for that would have made this round PASS, and what would overturn each ruling:**

1. **Class 3 GREEN** was available and I withheld it. I would have granted it had the numerator
   decomposition come back clean, and I ran that test the same way I ran class 1's in round 5 — every
   clause's unique contribution, every distinct error string read. It came back with 85 rows admitted
   by our own remediation sentence and 5 by a pattern that matches the letters `id` inside the word
   `valid`. **Overturned by:** a demonstration that `unknown kind: <X>` is an identifier failure. The
   error text asserts the opposite.

2. **The 28 triples ruled HISTORICAL** — I set out to prove them live. **Overturned by:** a single
   same-pass (message, pass, tool) triple with `created_at > 2026-08-04 04:06:34.352759`. Query
   `R6-36` with that bound; today it returns `0` against 609 records of equal opportunity.

3. **The five tools ruled LEGITIMATELY ABSENT** — I set out to confirm my own round-5 implication of
   a recording gap and found a frozenset naming exactly those five, removed from the turn catalogue
   before any stage reads it. **Overturned by:** any turn where one of the five is *withheld* rather
   than absent, which would prove they do enter the candidate set. None exists in 66 instrumented
   turns.

4. **Decision 4** — **overturned by:** unscripted real errors on the frozen side exceeding 743. They
   number 522 and the side is frozen, so no observation can ever overturn it. That is the finding.

---

*Authority exercised. I rule **class 3 (50.3%)** unsound as published: at minimum 90 of its 841
numerator rows are not identifier failures, 85 of them admitted by a phrase that appears only in
help text we append to our own error message. I bound the class at **44.9%** on a numerator purged
of the unambiguous non-identifiers, **41.1%** on the strictest reading, and **28.9% / 21.8%** on
unscripted traffic. Any PASS resting on 50.3% is void.*

*I **withdraw** two of my own prior findings. Class 3's denominator defect — 763 rows of breaker
prose and a second definition of "REAL errors" — is **fully closed**, proven by set identity in both
directions rather than by count agreement. And the claim that five catalogue tools are "unaccounted"
is **withdrawn**: they are `INTENT_GATED_SETUP_TOOLS`, removed from the turn catalogue before any
narrowing stage runs, and the turn I measured it on is the single most-covering turn in the corpus.
CP-0.2 is complete for what it claims to record.*

*I rule the 28 same-pass triples a **historical artifact**, not a live defect, and I say so having
tried to prove the opposite: the reconciliation's own docstring cites eleven tools at 6.2%, and two
of the four offending rows carry that exact eleven-name set at exactly 178 records and 11 overlaps.
The builder may close it. The builder may not describe the corpus as clean while 477 of 1,565
withheld records remain unreconcilable by construction.*

*Recorded in fairness: the frozen output is no longer stale — it was re-run and now matches the live
corpus byte for byte, closing a complaint I raised in two consecutive rounds. The class-3 denominator
fix is the cleanest correction this checkpoint has produced, and it was verified by the strongest
test I could construct rather than the one that would have passed most easily. The instrument keeps
getting better; the number it is named for still counts our own prose, and the comparison the
checkpoint exists to enable still has zero rows on its new side.*
