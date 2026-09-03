# CP-0 · V-METRIC — verdict, ROUND 9

*Artifact frozen at `874b3524e`. Verified 2026-08-04 against `loreweave_chat` in `infra-postgres-1`.
Subject: the instrument, never the feature. No tracked file was modified; every mutation below ran
inside a transaction that was rolled back, and the rollback is verified in-band (`R9-28`). Working
files under `.vmetric-r9/`. I did not read commit messages — I did read `baseline-metrics.sql` at a
prior revision, which is file content and was necessary to attribute the fingerprint drift (§5.3).*

**Standing question, which outranks everything else in my brief:** *would this number look good even
if the thing being measured were broken?* In round 9 it has exactly one affirmative answer, and it is
in a published figure. That is the whole of my FAIL.

---

## 0 · Verdict

| | |
|---|---|
| **OVERALL** | 🔴 **FAIL — and narrowly, for one reason, against a substantially repaired instrument.** Two round-8 findings are **genuinely closed**, verified with working controls: the pin is no longer breakable without traffic (§5.2), and P3 is no longer vacuous (§2.3). The vacuity finding drops from **3 of 4 properties** to **1 of 4**. What fails is a **published number**: the class-4 line reports **39 `awaiting_input`** turns — a state this codebase classifies as a *success* — of which **33 are turns the runtime's own reconciler has already recorded as dead** (`abandoned_by_user`, expired suspend, input can never arrive). The fix was applied to `outcome`; the published figure reads `finish_reason`; they now contradict each other on **84.6%** of that bucket, in the flattering direction. §4.4 |
| **1 · vacuity, re-ruled** | 🟢 **LARGELY REMEDIATED.** P1 ✅, P3 ✅ (**newly** falsifiable — this is what `outcome_source` bought), P4 ✅ (source-side, counter-example available). **P2 remains split**: its board form is violated 119/261, its *gated* form — the one the closure plan actually arms — is satisfied **119/119, zero counter-examples**, unchanged from round 8 and unaddressed by any change in this delta. §2 |
| **2 · does `outcome_source` restore falsifiability?** | 🟡 **YES, ONE-DIRECTIONALLY — and it reaches no query that matters.** It creates a positive marker for sweep-written rows, which is the direction that *finds* violations, and P3 is falsifiable again on 33 rows / 5 in the CP-0 era. But **nothing writes `'path'`** (both write sites emit `'reconciler'`), there was **no backfill**, so **64.8% of all outcomed rows are sweep-written while reading as path-written**, and the column has **zero readers** — 0 occurrences in `baseline-metrics.sql`, no `SELECT` anywhere in the service. §3 |
| **3 · `resolve_expired_suspends` as measurement** | 🟡 **IT MOVES NO PUBLISHED FIGURE, AND IT IS MATERIALLY BETTER THAN THE BRANCH IT SUCCEEDS — but it creates the same dated discontinuity, and it exposes the class-4 defect above.** 28 of its 33 stamps predate the CP-0 era (back to 2026-07-19). Unlike the crash branch it is **filterable** (it marks itself) and its predicate is **a fact the row carries** rather than an inference over five conditions. Its residual defect is attribution, not observation. §4 |
| **4 · does the baseline still reproduce; does the freeze hold?** | 🟡 **THE FOUR FIGURES REPRODUCE EXACTLY. THE FREEZE MECHANISM IS NOW SOUND AND I VERIFIED IT WITH A CONTROL. THE PINNED VALUE IS ORPHANED.** A maximal sweep mutating **2,990 rows** left the fingerprint **bit-identical**, while a single `finish_reason` mutation moved it — round 8's defect is closed and not over-corrected. But `frozen.txt` was generated under the **superseded formula** and never regenerated: I could not reproduce its pin under the new formula, the old formula, or two pre-sweep revert variants. **The artifact ships a pin no version of its own script can produce.** §5 |

**Authority exercised.** I rule the class-4 **`awaiting_input = 39`** figure **unsound as published**
(§4.4). I do *not* extend that to `pct_unrecorded = 0.0%`, which is unaffected. My round-7 ruling on
class 3 (40.4% under-counts; the corpus supports 49.9%) stands unchanged and the board still carries
it correctly.

---

## 1 · Pin, and the operating conditions of this round

```
== PIN · corpus fingerprint (numbers below are valid ONLY for this fingerprint) ==
 messages |            newest            |            corpus_md5
----------+------------------------------+----------------------------------
     5921 | 2026-08-04 10:59:24.34726+00 | 389c28a0e72b49723361efa534a07c58
```

**Two conditions of this round that a reader must know, because both affect what I could observe.**

**(a) `chat-service` restarted during my session**, at `2026-08-04T11:30:38Z`, and that restart is
what *created the column I was sent to rule on*. My first schema read returned no `outcome_source`:

```
$ docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat \
    -c "SELECT column_name FROM information_schema.columns
        WHERE table_name='chat_messages' AND column_name LIKE 'outcome%';"
  column_name
----------------
 outcome
(1 row)
```

Minutes later, after the restart, the same query returned two rows. The migration is idempotent
startup DDL (`ADD COLUMN IF NOT EXISTS`, no ledger table), the deployed image matches source
(`grep -c outcome_source` → migrate.py 2, instrument.py 3, `resolve_expired_suspends` 1), and the
restart applied it. **I record this because it is load-bearing for §3:** the newest message in the
corpus (`10:59:24`) *predates* the column's creation (`11:30:38`). **No traffic has run since the
column existed.** Every conclusion I draw about what the terminal paths write to it is therefore
drawn from source, not from rows — and I say so wherever it applies.

**(b) The startup sweep fired in front of me**, which is the only reason I can date its writes:

```
$ docker logs infra-chat-service-1 --since 20m | grep -i instrument
INFO:app.services.instrument: CP-0.4 expired-suspend resolver: 33 turn(s) were advertising
'awaiting_input' with an expired run — input could never arrive, so they are recorded
abandoned_by_user
```

`reconcile_crashed_turns` logged nothing, which under its own `if stamped_assistant or stamped_user`
guard means it stamped **zero**. Its docstring predicts exactly that (*"currently VACUOUS … it drains
the pre-CP-0 backlog once, then stamps nothing"*), and the prediction held. Recorded in the builder's
favour.

---

## 2 · Ruling 1 — re-ruling the vacuity finding, per property

The standard is unchanged and is the one the run adopted from me: **a property the system already
holds gates nothing.** For each of P1–P4 I asked: is there a row or a measurement, available *today*,
showing the current runtime violates it?

### 2.1 P1 — *every tool absent from a pass's advertised set registers `{tool, stage, reason, pass}`*

**✅ LIVE COUNTER-EXAMPLES, ABUNDANT. NOT VACUOUS.** Catalog control first — the SSOT is the frozen
snapshot (`catalog_sha256 eec0470b…`, `frozen_at 2026-08-03T23:01:35`, **315** tools):

```
== R9-11 · catalog control (SSOT = frozen tools-list.snapshot.json) ==
 catalog_tools
---------------
           315

== R9-14 · P1 · (a) SSOT denominator: catalog - advertised - withheld = UNREGISTERED narrowings ==
 message_passes | unregistered_narrowings | passes_with_a_hole | distinct_tools
----------------+-------------------------+--------------------+----------------
            291 |                   76671 |                289 |            313

== R9-15 · P1 · (c) NARROWEST reading: advertised at an EARLIER pass, absent now, NO withheld record now ==
 unregistered_mid_turn_deletions | distinct_tools | turns
---------------------------------+----------------+-------
                             478 |              7 |     5

== R9-16 · P1 · withheld records missing any of the four keys ==
 records | no_tool | no_stage | no_reason | no_pass
---------+---------+----------+-----------+---------
    6390 |       0 |        0 |         0 |     332

== R9-17 · P1 · turns that advertise but record NO withheld at all ==
 turns_with_advertised | of_which_no_withheld_column
-----------------------+-----------------------------
                    92 |                          38
```

**Denominator stated: 291 message-passes** (every `(message_id, pass)` that carries an advertised
record), against a **315-tool** catalog. **289 of 291 passes have a hole.** `{tool, stage, reason}` is
complete on all 6,390 records; `pass` is absent on **332** (the unchanged historical block). **38 of
92** advertising turns record no withholding at all.

**The board's companion sub-claim is still false, at the same 28 rows.** RUNSTATE's path-to-closure
row states: *"Same-pass overlap **is** 0 everywhere — that part held."*

```
== R9-12 · P1 · same-pass OVERLAP (a tool BOTH advertised AND withheld at the same pass) ==
 overlap_rows | messages
--------------+----------
           28 |        4

== R9-13 · P1 · the overlap rows by stage ==
    stage     | count
--------------+-------
 token_budget |    28
```

**28 rows, 4 messages, every one at `stage = token_budget`** — the same tool recorded as *advertised
at pass p* and *withheld at pass p*. Those two records cannot both be true. **Unchanged from round 8,
and unaddressed by this delta.** The board's `237 → 4` residual likewise remains unreproducible: the
most charitable reading I can construct gives **478 occurrences over 7 tools in 5 turns**.

**Ruling: P1 is a real gate. Its stated position on the board is still not a measurement.**

### 2.2 P2 — *a call's `source` is assigned structurally, never inferred*

```
== R9-18 · P2 · tool_calls[].source distribution + source_inferred marker (ALL rows) ==
  source  | has_inferred_key | inferred_val |  n
----------+------------------+--------------+------
 <absent> | f                | -            | 7447
 tool     | f                | -            |  142
 meta     | t                | true         |   87
 breaker  | t                | true         |   32

== R9-19 · P2 · denominator = calls carrying a source at all ==
 calls_with_source | inferred | pct_inferred |             first             |             last
-------------------+----------+--------------+-------------------------------+------------------------------
               261 |      119 |         45.6 | 2026-08-03 23:47:17.022868+00 | 2026-08-04 10:59:24.34726+00
```

**Board form: ✅ violated. 119 of 261 = 45.6% inferred.** Denominator stated: **261**, every recorded
`tool_calls[]` element carrying a `source` key at all; the 7,447 pre-CP-0 elements carry none and
cannot be scored. **NOT VACUOUS.**

**Gated form — the one the closure plan actually arms (*"an inferred row must mark itself"*):**

```
== R9-20 · P2 · GATED form: is any inferred row UNMARKED? (0 = gated form vacuous) ==
 source  |  n  | marked_inferred | unmarked
---------+-----+-----------------+----------
 tool    | 142 |               0 |      142
 meta    |  87 |              87 |        0
 breaker |  32 |              32 |        0
```

**119 inferred, 119 marked, 0 unmarked. Satisfied 100% at n=261. 🔴 STILL VACUOUS.** This is
round 8's finding repeated verbatim at a larger n, and **nothing in this delta addressed it.**

And it remains **unfalsifiable by construction**, which is the deeper objection: `source_inferred` is
written by the same code that performs the inference. A call inferred at a site that believes itself
structural leaves no trace — it lands among the 142 unmarked `tool` rows, indistinguishable from a
genuinely structural one. The counter-example that would falsify weak-P2 is invisible to the
instrument. **This is the same defect I identify in `outcome_source` at §3.2; the artifact has now
built it twice.**

### 2.3 P3 — *every terminal path writes an outcome* — 🟢 **NO LONGER VACUOUS. THIS IS THE FIX.**

Round 8's test still returns zero, and would still have ruled P3 vacuous:

```
== R9-21 · P3 · CP-0-era (>= 2026-08-03 23:47) assistant turns lacking an outcome ==
 assistant_turns | no_outcome | no_outcome_aged
-----------------+------------+-----------------
              93 |          0 |               0
```

**But `outcome_source` creates a counter-example class that did not exist in round 8**, and it is
populated. P3 says every *terminal path* writes an outcome; a row marked `'reconciler'` is precisely
a row where **no terminal path did** and a sweep repaired the record afterwards:

```
== R9-22 · P3 · THE NEW COUNTER-EXAMPLE CLASS: outcome written by a SWEEP, not a terminal path ==
    src     |  n  | in_cp0_era
------------+-----+------------
 <NULL>     | 315 |         94
 reconciler |  33 |          5

== R9-37 · P3 · the CP-0-era counter-examples, enumerated ==
              message_id              |   role    | finish_reason  |      outcome      | outcome_source |          created_at
--------------------------------------+-----------+----------------+-------------------+----------------+-------------------------------
 7a66b39d-a61e-496b-b80a-286243a339f2 | assistant | awaiting_input | abandoned_by_user | reconciler     | 2026-08-04 01:58:42.169584+00
 9aba6fe4-511d-49dc-b865-95408a3b0344 | assistant | awaiting_input | abandoned_by_user | reconciler     | 2026-08-04 03:01:47.80691+00
 732760c4-d11f-4e84-bf7d-bd7cd1af394b | assistant | awaiting_input | abandoned_by_user | reconciler     | 2026-08-04 03:04:56.594666+00
 bfdcc100-8ee3-4466-9d72-60acb7a5bced | assistant | awaiting_input | abandoned_by_user | reconciler     | 2026-08-04 04:13:16.607021+00
 bbae64a7-a33f-42fd-a99c-3e369b7246d5 | assistant | awaiting_input | abandoned_by_user | reconciler     | 2026-08-04 04:13:16.607021+00
```

**33 counter-examples corpus-wide, 5 of them in the CP-0 era, each one nameable.** Round 8's sharpest
finding — *"the reconciler makes P3's number look perfect while removing the ability to check the
property"* — is **answered**. The number no longer looks perfect: it looks like 5, and you can list
them. **I record this as the single clearest repair in this delta.**

### 2.4 P4 — *no CP-0 column is bound to a constant at any INSERT*

**✅ COUNTER-EXAMPLE AVAILABLE. NOT VACUOUS.** Source-side, so it is V-CODE's ruling and not mine; I
record what my subject can contribute. The site is `stream_service.py:7495`, and **its own comment
names two distinct terminal conditions collapsed into one constant**:

```python
# CP-0.4 — … CancelledError/GeneratorExit here means the user stopped the turn
# or the client went away, which is NOT a failure.
outcome=instrument.OUTCOME_ABANDONED_BY_USER,
```

*"the user stopped the turn"* and *"the client went away"* are two conditions; the constant is one
value. Under V-CODE's own narrowed gate — *an INSERT reachable from more than one terminal condition
must derive both fields from one signal* — that is a counter-example on its face.

**What I can add from the data: the resulting population carries no field that separates them.**

```
== R9-38 · P4 · the path-written abandoned_by_user population ==
   role    | finish_reason |     src     | is_error | n
-----------+---------------+-------------+----------+----
 assistant | interrupted   | <NULL>=path | f        | 10
 user      |               | <NULL>=path | f        |  1
```

**11 rows, one shape, two causes, no discriminator.** A deliberate cancel and a dropped client are
the same row. **P4 has an available counter-example and gates something.**

### 2.5 Ruling 1, stated

| | live counter-example **today**, on evidence I reproduced? | round 8 | round 9 |
|---|---|---|---|
| **P1** | ✅ 76,671 unregistered / 289 of 291 passes; 28 same-pass contradictions; 332 pass-less | 🟢 real gate | 🟢 **real gate** (number still unreproducible) |
| **P2 · board form** | ✅ 119 of 261 inferred | 🟢 real gate | 🟢 **real gate** |
| **P2 · gated form** | ❌ **satisfied 119/119**, falsifier unobservable by construction | 🔴 vacuous | 🔴 **still vacuous — unaddressed** |
| **P3** | ✅ **33 sweep-written rows, 5 in the CP-0 era, enumerated** | 🔴 vacuous | 🟢 **NEWLY FALSIFIABLE** |
| **P4** | ✅ `stream_service.py:7495`; 11 rows, two causes, no discriminator | 🔴 vacuous | 🟢 **real gate** |

**Round 8: three of four properties had no available counter-example. Round 9: one.** And the one is
not a property CP-0 stated — it is the *weakened* form the closure plan substitutes for P2. **The
vacuity finding is largely remediated, and I withdraw it for P3 and P4 without qualification.**

---

## 3 · Ruling 2 — does `outcome_source` restore falsifiability?

**Yes in the direction that matters, and it is a real repair. But it is one-sided, unbackfilled, and
unread.** Three findings, in ascending order of severity.

### 3.1 The fraction

```
== R9-2 · outcome_source fractions among rows that HAVE an outcome ==
 with_outcome | src_path | src_reconciler | src_null | pct_reconciler
--------------+----------+----------------+----------+----------------
          348 |        0 |             33 |      315 |            9.5
```

**Denominator stated: 348**, every row carrying a non-NULL `outcome`. **9.5% are `'reconciler'`.**

**And `'path'` is written zero times.** That is not an artifact of the corpus — it is the code:

```
$ grep -rn "outcome_source" services/chat-service/app/ --include=*.py
instrument.py:520:  "WITH t AS (UPDATE chat_messages SET outcome = $1, outcome_source = 'reconciler' "
instrument.py:567:  — and ``outcome_source`` marks it as swept, never as the terminal path having recorded it.
instrument.py:578:  "  SET outcome = $1, outcome_source = 'reconciler' "
```

**Two write sites, both emitting `'reconciler'`. No site anywhere writes `'path'.'** The terminal
paths in `stream_service.py` (lines 6230, 6299, 7302, …) write `outcome` and leave `outcome_source`
NULL. So the column is a **one-sided marker**, and `NULL` does not mean *"a terminal path wrote
this"* — it means *"neither of these two sweeps wrote this"*, which additionally covers every row
predating the column and every future sweep that forgets to mark itself.

*Recorded in the builder's favour:* no traffic has run since the column existed (§1a), so the absence
of `'path'` rows is **not** evidence that a path would fail to write one. It is evidence that **no
code path exists that would** — which is the stronger statement, and it comes from source, not rows.

### 3.2 The fraction that is actually right is not 9.5% — it is 25%

There was **no backfill**, and the corpus still contains the 226 user rows the *removed* branch
stamped. They are sweep-written by construction, and they carry `outcome_source IS NULL`:

```
== R9-5 · the 226 user rows stamped crashed: what outcome_source do they carry? ==
                     src                      | count
----------------------------------------------+-------
 <NULL> = indistinguishable from path-written |   226

== R9-39 · SUMMARY · provenance of every outcome value in the corpus ==
                             provenance                             |  n  | pct
--------------------------------------------------------------------+-----+------
 B · UNMARKED sweep-written (removed branch; reads as path-written) | 226 | 64.8
 D · unmarked, presumed path-written                                |  87 | 24.9
 A · marked sweep-written (P3 counter-example)                      |  33 |  9.5
 C · ambiguous (checkpoint constant OR crash sweep)                 |   3 |  0.9
```

**64.8% of all outcomed rows are sweep-written and read as path-written.** The column that exists to
record provenance records the **wrong** provenance on nearly two-thirds of the corpus — and the error
runs in the **flattering** direction: a sweep's repair reads as a terminal path's success. Only
**24.9%** of outcomed rows are honestly presumed path-written.

Removing the user branch stopped the *bleeding*; it did not remove the *blood*. The 226 rows are the
same dated discontinuity round 8 measured — still spread across 26 days from 2026-04-03, still with
**89 of them in sessions that demonstrably continued afterwards**:

```
== R9-3 · the 226 user rows stamped crashed: date spread ==
 2026-04-03 | 1     2026-07-07 | 12    2026-07-12 | 36
 2026-04-04 | 2     2026-07-08 | 15    2026-07-13 |  9
 2026-05-30 | 2     2026-07-09 | 32    2026-07-14 |  8
 2026-06-01 | 3     2026-07-10 |  2    2026-07-15 | 35
 2026-06-02 | 6     2026-07-11 | 12    2026-07-18 |  8
 …                                     2026-08-04 |  5      [26 rows]

== R9-4 · ... do they sit in sessions that CONTINUED after them? ==
              shape               | count
----------------------------------+-------
 row is last in session           |   137
 session continued after this row |    89
```

**A one-line backfill (`UPDATE … SET outcome_source='reconciler' WHERE role='user' AND
outcome='crashed'`) would move this from 64.8% wrong to 0% wrong.** I do not propose fixes; I record
that the gap is not inherent to the design, only to the delivery.

### 3.3 Does the distinction survive into any query that matters? **No. It has zero readers.**

```
$ grep -c "outcome_source" contracts/agent-runtime-baseline/baseline-metrics.sql
0
```

**Zero occurrences in the published instrument.** And no `SELECT` anywhere in the service — the only
non-write references are three assertions in `test_cp0_instrument.py` that string-match the
**writer's own SQL text**:

```
test_cp0_instrument.py:880:  assert "outcome_source = 'reconciler'" in sql, "a swept row must be distinguishable"
test_cp0_instrument.py:911:  assert src.count("outcome_source = 'reconciler'") >= 1, (
test_cp0_instrument.py:1049: assert "outcome_source = 'reconciler'" in sql, (
```

**Those tests assert that the writer emits a literal. They do not assert that any consumer
distinguishes anything** — there is no consumer. The query that makes P3 falsifiable (`R9-22`) is one
**I** wrote, for this verdict. Nothing in the artifact runs it, and nothing would go red if the
column stopped being written tomorrow.

### 3.4 Ruling 2, stated

| question | ruling |
|---|---|
| can you now distinguish a terminal path from a sweep? | 🟡 **In one direction only.** `'reconciler'` positively identifies a sweep; `NULL` identifies nothing |
| what fraction of outcomes are `'reconciler'`? | **9.5% (33/348).** The honest sweep-written fraction is **≥74.4% (259/348)** once the 226 unbackfilled rows are counted |
| does the distinction survive into any query that matters? | 🔴 **No.** 0 occurrences in `baseline-metrics.sql`, no readers in the service, tests assert the writer's string |
| does it restore falsifiability for P3? | 🟢 **Yes — and this is the delta's clearest repair.** 33 counter-examples, 5 in the CP-0 era, each nameable (`R9-37`) |

**The column is sound in kind and half-delivered.** It is enough to *refute* P3, which is what a
property gate needs. It is not enough to *certify* P3, because absence of the marker is not evidence
of a path — the identical defect as `source_inferred` at §2.2.

---

## 4 · Ruling 3 — `resolve_expired_suspends` as a measurement question

I applied the same four tests I applied to the crash reconciler in round 8: does it move a published
figure, does it create a discontinuity, does it invalidate before/after, and is its value **observed
or asserted**.

### 4.1 It moves no published figure — proven by enumeration, not inspection

```
$ grep -n "outcome" contracts/agent-runtime-baseline/baseline-metrics.sql
36:  -- `outcome` is deliberately NOT hashed. No class below reads it, …
263: -- 'interrupted' is a RECORDED outcome, not an absent one. …
```

**Both are comments.** Class 4's derivation reads `finish_reason` and `is_error` and nothing else:

```sql
CASE WHEN m.is_error THEN 'failed'
     WHEN m.finish_reason = 'stop' THEN 'completed'
     WHEN m.finish_reason = 'awaiting_input' THEN 'awaiting_input'
     …
```

Classes 1–3 read `tool_calls`. **No class reads `outcome` or `outcome_source`.** The resolver writes
only those two columns and never touches `finish_reason`. **Zero published figures move.** ✅

### 4.2 It creates the same dated discontinuity — but a filterable one

```
== R9-6 · the 33 expired-suspend rows: date spread of created_at ==
     d      | count
------------+-------
 2026-07-19 |     1      2026-07-27 |  2
 2026-07-20 |     4      2026-07-29 |  3
 2026-07-21 |     1      2026-08-02 |  2
 2026-07-25 |    13      2026-08-04 |  5
 2026-07-26 |     2

== R9-7 · the 33: how many predate the CP-0 era? ==
          oldest_row          |          newest_row           | n  | predate_cp0_era
------------------------------+-------------------------------+----+-----------------
 2026-07-19 10:29:19.51552+00 | 2026-08-04 04:13:16.607021+00 | 33 |              28
```

**28 of 33 (84.8%) predate the CP-0 era**, back to 2026-07-19, and all 33 were written today at
11:30. **This is the same shape as the crash reconciler's 223→226**: a value stamped in August onto
rows dated in July, by a mechanism that did not exist on those dates. **Any comparison of the outcome
distribution bucketed on `created_at` is distorted by it.**

**Two things make it materially better than the branch it succeeds, and I weight them:**

1. **It is filterable.** Every one of the 33 carries `outcome_source='reconciler'`, so
   `WHERE outcome_source IS DISTINCT FROM 'reconciler'` recovers the pre-sweep distribution exactly.
   The legacy 226 cannot be filtered (§3.2). **The discontinuity is now *declared* rather than
   *hidden* — which is the whole difference between a contaminant and a covariate.**
2. **Its predicate is a fact the row carries about itself**, not an inference. `expires_at <= now()`
   is checked against `chat_suspended_runs`, and `load_suspended_run` filters `expires_at > now()`,
   so an expired run is *provably* unresumable. I verified all 33:

```
== R9-10 · do those rows still have an EXPIRED suspended run (input can never arrive)? ==
 n  | expired | still_live
----+---------+------------
 33 |      33 |          0
```

**33 of 33 expired, 0 live.** Contrast the removed branch's *"no later assistant row"*, which round 8
showed was equally the shape of an abandoned message, an unfollowed branch, a client-side failure —
and which the builder's own comment now concedes was satisfiable by a user **deleting** a reply.
**This is not that defect.**

### 4.3 The residual: the state is observed, the agent is asserted

`expires_at <= now()` establishes exactly one thing: **input can never arrive.** It does not establish
*who* caused that. `abandoned_by_user` attributes the cause to the **user**, and the same expiry is
equally consistent with the confirmation card never rendering, a client crash, a lost tool result, or
a frontend that dropped the AG-UI resume. **The state is measured; the agent is inferred.**

This is a **weaker** version of the crash-branch defect, not the same one — the vocabulary is closed
and `abandoned_by_user` is its only member meaning *"ended without completing, and not our fault"*,
so the choice is partly forced. But *"not our fault"* is precisely the unverified half. **I record it
as an attribution caveat, not as grounds to reject the mechanism.**

**One structural hazard, currently unexercised.** The crash reconciler guards with
`WHERE outcome IS NULL`. The resolver does **not** — it guards with `outcome IS DISTINCT FROM $1`,
which means it will **overwrite a path-written outcome** on any `awaiting_input` row with an expired
run. It is idempotent (after the first stamp the predicate is false) and today the exposure is zero:

```
== R9-32 · would the resolver OVERWRITE a path-written outcome today? ==
 rows_resolver_would_overwrite
-------------------------------
                             0

== R9-31 · resolver CLOBBER exposure, by current outcome ==
      outcome      | n  | with_expired_run | with_live_run | no_run_row
-------------------+----+------------------+---------------+------------
 abandoned_by_user | 33 |               33 |             0 |          0
 <NULL>            |  3 |                0 |             0 |          3
 awaiting_input    |  3 |                0 |             3 |          0
```

**0 rows exposed.** But the guard's absence means a future path-written outcome on such a row is
silently reverted **and its `outcome_source` flipped from NULL to `'reconciler'`** — turning a
P3-*satisfying* row into a P3-*violating* one in the record. Nothing detects it. Flagged, not scored.

### 4.4 🔴 The finding — the resolver fixed `outcome`, and the published figure reads `finish_reason`

This is my FAIL, and it is the standing question answered in the affirmative.

The published class-4 line reports **39 `awaiting_input`** turns. This codebase classifies that state
as a **success** — `migrate.py` states it verbatim: *"A SUCCESS state, not a stall: a model that stops
to ask is behaving correctly, and counting it as failure punishes the behaviour we want."*

The resolver changed `outcome` on 33 of those rows. It did **not** change `finish_reason`. Class 4
reads `finish_reason`:

```
== R9-8 · class-4 population: assistant rows finish_reason=awaiting_input (>=2026-07-19) x outcome ==
      outcome      |    src     | count
-------------------+------------+-------
 abandoned_by_user | reconciler |    33
 <NULL>            | <NULL>     |     3
 awaiting_input    | <NULL>     |     3

== R9-9 · THE DISAGREEMENT ==
 rows_class4_calls_awaiting_input_but_outcome_says_abandoned
-------------------------------------------------------------
                                                          33
```

**33 of the 39 turns the published baseline counts as a success are turns the same instrument's own
`outcome` column records as dead — verified unresumable, 33 of 33 with expired runs (`R9-10`).**

**Denominator stated: 39**, the `awaiting_input` bucket of class 4 (all 39 are organic — the raw
scope reports 0). **84.6% of that bucket is contradicted by the runtime's own record.**

The direction matters. The error runs **toward the flattering reading**: dead turns counted as
successes. And it is the exact defect the frozen artifact is named for — *a success label on a dead
turn* — **repaired in the column and left standing in the published figure.**

**Ruling: I exercise my authority and rule the class-4 `awaiting_input = 39` figure UNSOUND as
published.** I do **not** extend this to `pct_unrecorded = 0.0%`, which reads a different predicate
and is unaffected; nor to classes 1–3, which read `tool_calls`. Any PASS resting on class 4's
*distribution* is void; a PASS resting on its *coverage* is not.

### 4.5 Ruling 3, stated

| question | ruling |
|---|---|
| does it distort the outcome distribution? | 🟡 **Yes — 33 rows, 28 of them backdated before the CP-0 era — but the distortion is *declared*, and filterable via `outcome_source`** |
| does it create a discontinuity? | 🟡 **Yes, the same shape as the crash reconciler — and unlike it, reversible by a `WHERE` clause** |
| does it make a before/after comparison invalid? | 🟡 **For anything bucketed on `created_at` reading `outcome`: yes, unless filtered.** The filter exists for these 33 and **not** for the legacy 226, so the outcome distribution as a whole remains unusable |
| is the value observed or asserted? | 🟢 **The state is observed** (33/33 expired, provably unresumable). 🟡 **The agent is asserted** — *"by_user"* is one of at least four causes |
| **any other measurement effect?** | 🔴 **Yes, and it is the round's finding: it repaired `outcome` and left `finish_reason` alone, so the published class-4 figure still labels 33 dead turns a success** (§4.4) |

---

## 5 · Ruling 4 — does the baseline reproduce, and does the freeze hold?

### 5.1 The four figures reproduce exactly. Raw output, in full.

```
== PIN · corpus fingerprint ==
 messages |            newest            |            corpus_md5
----------+------------------------------+----------------------------------
     5921 | 2026-08-04 10:59:24.34726+00 | 389c28a0e72b49723361efa534a07c58

== 0 · POPULATION ==
 calls_raw | calls_organic | failures_raw | failures_organic
-----------+---------------+--------------+------------------
      7708 |          6488 |         4078 |             2898

== 1 · CARRY-FORWARD (strict: success STRICTLY EARLIER) ==
        scope        | failures | carry_strict | pct_strict | carry_loose | pct_loose
---------------------+----------+--------------+------------+-------------+-----------
 organic             |     2898 |         1120 |       38.6 |        1306 |      45.1
 organic_real_errors |     1674 |          101 |        6.0 |         263 |      15.7
 raw                 |     4078 |         2300 |       56.4 |        2486 |      61.0

== 2 · NOT-A-REAL-DISPATCH, as a share of failures (LOWER BOUND pre-CP-0) ==
  scope   | failures | not_real_dispatch |  pct  | of_which_meta
----------+----------+-------------------+-------+---------------
 raw-only |     1180 |              1180 | 100.0 |          1180
 organic  |     2898 |              1200 |  41.4 |           157

== 3 · IDENTIFIER RESOLUTION, as a share of REAL errors ==
  scope  | real_errors | id_errors | pct
---------+-------------+-----------+------
 organic |        1674 |       676 | 40.4

== 4 · TERMINAL OUTCOME, through the CP-0.4 shim, WINDOWED on column age ==
  scope  | assistant_turns | completed | awaiting_input | failed | crashed | interrupted_recorded | unrecorded | pct_unrecorded
---------+-----------------+-----------+----------------+--------+---------+----------------------+------------+----------------
 raw     |               4 |         4 |              0 |      0 |       0 |                    0 |          0 |            0.0
 organic |             338 |       273 |             39 |      2 |       3 |                   21 |          0 |            0.0

== 5 · WEEKLY TRAFFIC (the ceiling on any bound) ==
    week    | calls | failures
------------+-------+----------
 2026-08-03 |   266 |       71
 2026-07-27 |   102 |       64
 2026-07-20 |  1494 |     1169
 2026-07-13 |  2431 |      528
 2026-07-06 |  1828 |      966
 2026-06-29 |    72 |       17
 2026-06-22 |   126 |       38
 2026-06-15 |   157 |       41
 2026-06-08 |     1 |        0
 2026-06-01 |     6 |        1
```

### 5.2 🟢 The freeze MECHANISM is now sound — and I proved it with a working control

Round 8's finding was that the pin *hashed `outcome`*, so a restart with **zero traffic** invalidated
the baseline. `outcome` is now excluded, with the reasoning written into the file. **I tested the
exclusion adversarially rather than reading it**: inside one transaction I fired **both** sweeps with
their age and expiry guards **removed**, plus the deleted user branch at full width, then rolled back.

```
== R9-24 · FREEZE IMMUNITY TEST · fingerprint BEFORE ==
 messages |            corpus_md5
----------+----------------------------------
     5921 | 389c28a0e72b49723361efa534a07c58

== R9-25 · rows mutated inside the transaction ==
 rows_now_carrying_outcome_source
----------------------------------
                             2990

== R9-26 · fingerprint AFTER the maximal sweep (same tx) ==
 messages |            corpus_md5
----------+----------------------------------
     5921 | 389c28a0e72b49723361efa534a07c58

== R9-27 · CONTROL · the pin must still MOVE on a change it IS supposed to catch ==
 corpus_md5_after_finish_reason_mutation
-----------------------------------------
 86235ad642504d32462cb8fd18b9195a

== R9-28 · POST-ROLLBACK · confirm nothing persisted ==
 rows_carrying_outcome_source
------------------------------
                           33
```

**2,990 rows mutated; the fingerprint did not change one character. One `finish_reason` mutated on a
single row; the fingerprint moved.** The exclusion is exactly as wide as it needs to be and no wider
— **round 8's defect is closed, and the correction did not overshoot into round 3's under-sensitivity.**
This is the cleanest result in the delta and I record it without qualification.

### 5.3 🔴 But the pinned VALUE is orphaned — no version of the script can produce it

`frozen.txt` pins `9cdacf696d9b5ebb6932d3e8e8062d1c` at **5,862** messages. Today's run gives
`389c28a0…` at **5,921**. Fifty-nine new messages would explain that. **They do not.**

The row set at the freeze timestamp reproduces **exactly** — so nothing was deleted:

```
== R9-30 · rows added since the freeze ==
 new_messages
--------------
           59

== R9-29 · fingerprint over ONLY rows that existed at the freeze timestamp ==
 messages_at_freeze |      md5_historical_subset
--------------------+----------------------------------
               5862 | 08bdb025acc454a5531811474bdc488a
```

**5,862 — the pinned count, to the row. But the hash is `08bdb025…`, not `9cdacf69…`.** So I checked
whether `frozen.txt` was generated under the *superseded* formula. It was — at revision
`2ef8f0f7f25a1f9e6ac1a27cc1ec15cd71776ace` the file reads:

```sql
(SELECT string_agg(message_id::text || coalesce(finish_reason,'') || coalesce(outcome,'')
                   || is_error::text || coalesce(tool_calls::text,''), ',' ORDER BY message_id)
 FROM chat_messages)
```

`coalesce(outcome,'')` — the term now removed. I then tried to reproduce the pin under the **old**
formula, and under two reconstructions of the pre-sweep `outcome` state:

```
== R9-33 · OLD formula (hashes `outcome`) over the historical 5,862-row subset ==
 5a3aedf9d8e04f88a9f7bdc64db709b6

== R9-34 · OLD formula, with the 33 sweep stamps reverted to NULL ==
 7e6284491dca1147e99b4666639b1962

== R9-35 · OLD formula, with the 33 stamps reverted to 'awaiting_input' ==
 63d60e71474bd49d56956eb079f3256d
```

**None reproduces `9cdacf69…`.** The pinned value is unreachable under the current formula, under the
superseded formula, and under two reverted states. **`baseline-metrics.frozen.txt` was not regenerated
when `baseline-metrics.sql` changed, so the artifact ships a pin that no version of its own script can
produce.** By the file's own rule — *"a differing fingerprint means the numbers are not comparable and
nothing may be concluded from the difference"* — the pin can now only ever read *differing*, forever,
for a reason that has nothing to do with the corpus.

**This is a different failure from round 8's and it is less serious.** Round 8: the mechanism was
wrong. Round 9: **the mechanism is right and the record is stale.** Regenerating `frozen.txt` under
the shipped formula closes it. I record the distinction because the two would otherwise read as the
same unresolved finding across two rounds, and they are not.

### 5.4 The figures against the frozen file

| class | today | denominator | frozen.txt | moved? |
|---|---|---|---|---|
| 1 · carry-forward over real errors | **6.0%** | **101 / 1,674** | 6.0% (101/1,673) | pct held, denominator +1 |
| 2 · not-a-real-dispatch (organic) | **41.4%** | **1,200 / 2,898** | 41.4% (1,198/2,892) | pct held, both moved |
| 3 · identifier resolution (organic) | **40.4%** | **676 / 1,674** | 40.4% (676/1,673) | pct held, denominator +1 |
| 4 · no recorded outcome (windowed ≥ 2026-07-19) | **0.0%** | **0 / 338** | 0.0% (0/312) | pct held, +26 turns |
| 4b · **`awaiting_input` bucket** | **39** | **39 organic** | 36 | 🔴 **33 of 39 are dead turns — §4.4** |
| — corpus fingerprint | `389c28a0e72b49723361efa534a07c58` | 5,921 msgs | `9cdacf696d…` / 5,862 | 🔴 **unreachable, §5.3** |

**All four percentages are stable to the decimal across three rounds and ~60 messages of new traffic.
That stability is real and I credit it.** My round-7 ruling on class 3 stands unchanged (40.4%
under-counts by 158 rows; the corpus supports **49.9%**), and the board carries it correctly.

### 5.5 What the traffic still supports — unchanged

`== 5 ·` shows the last two weeks at **266** and **102** organic calls. At that rate the arithmetic
from my brief is unchanged and unchallenged: `3/3` bounds a failure rate only at **≤63.2%** against a
54.2% baseline, and **≤10% requires 29 consecutive successes.** **This is why the move from a rate to
a property remains correct in kind** — no accumulation of this traffic answers a rate question inside
this run, and a property needs n=1. Nothing in this delta changes that, and nothing needed to.

---

## 6 · My stated falsifier

*What I looked for that would have made each ruling go the other way.*

1. **Ruling 1 — vacuity.** I re-ran round 8's exact tests hoping to find them **still** at zero,
   because a second round of vacuity would have been the more damaging finding and the easier
   verdict. **P3 moved off zero** (`R9-22`: 33 rows, 5 in the CP-0 era) and I ruled against my own
   prior. **Overturned by:** `R9-22` returning `reconciler = 0`, or `R9-37` returning no CP-0-era
   rows. Neither did. **Re-confirmed for weak-P2 by** `R9-20`: `unmarked = 0` across all 119 inferred
   calls — if that becomes non-zero I withdraw the vacuity ruling on P2 as well.
2. **Ruling 2 — `outcome_source`.** I set out to confirm it works, and it half does. **The single
   query that decided it was `grep -rn "outcome_source" services/chat-service/app/`** — had any site
   written `'path'`, the column would be two-sided and I would have ruled it a complete repair.
   **Overturned by:** one `'path'` writer, or a backfill of the 226 (`R9-5`), or one `SELECT` in
   `baseline-metrics.sql`. All three are absent; any one of them changes the ruling.
3. **Ruling 3 — the resolver.** I applied round 8's crash-reconciler tests verbatim, expecting to
   find the same defect wearing a new name, **and I ruled against that expectation**: its predicate is
   a fact the row carries (`R9-10`, 33/33 expired) and its stamps are filterable. **Overturned by:**
   any of the 33 having a live run — `R9-10` says zero — or `outcome` appearing in a class derivation,
   which `grep` puts at zero. **What I found instead** was the disagreement at `R9-9`, which I was not
   looking for: I ran `R9-8` to confirm the resolver had *not* touched class 4, and the confirmation
   that it had not **is** the finding, because class 4 still publishes the pre-fix reading.
4. **Ruling 4 — the freeze.** I did not read the exclusion and accept it. I **fired both sweeps with
   their guards removed inside a transaction**, mutating 2,990 rows, specifically to break the pin —
   and it held (`R9-26`). I then ran a **control** (`R9-27`) because a hash that never moves is
   worthless, and it moved on one `finish_reason`. **Overturned by:** the fingerprint changing at
   `R9-26` (it did not), or **failing** to change at `R9-27` (it changed). **Separately re-confirmed
   as broken:** I tried **four** formulas to reproduce `9cdacf69…` (`R9-29`, `R9-33`, `R9-34`,
   `R9-35`) because reproducing it would have made the pin GREEN. None does.
5. **The FAIL itself.** My FAIL rests on one number, so I tried hardest to break it. **Overturned
   by:** any of the 33 rows having a live suspended run (`R9-10`: 0 of 33), or class 4 reading
   `outcome` rather than `finish_reason` (`grep`: `outcome` appears twice in the SQL, both comments),
   or the 33 not being inside the class-4 window (`R9-8` restricts to `>= 2026-07-19` and
   `role='assistant'`, matching the class-4 predicate exactly). **The figure survives every
   construction I could put on it, so I rule it unsound.**

---

*Authority exercised. I rule the class-4 **`awaiting_input = 39`** figure **unsound as published**:
33 of 39 are turns the instrument's own `outcome` column records as dead, verified unresumable, and
the error runs toward the flattering reading. Any PASS resting on class 4's **distribution** is void.
`pct_unrecorded = 0.0%` and classes 1–3 are unaffected, and my round-7 ruling on class 3 (40.4%
under-counts; the corpus supports 49.9%) stands unchanged.*

*I **withdraw** round 8's vacuity ruling for **P3** and **P4** — both now carry live, nameable
counter-examples. I **sustain** it for the **gated form of P2**, satisfied 119/119 at n=261 and
untouched by this delta. I **sustain** the finding that the board's `same-pass overlap is 0` claim is
false, unchanged at **28 rows**, all at `token_budget`.*

*Recorded in fairness, and it is the larger half of this round. Three of the four changes I was sent
to rule on do what they claim. `outcome_source` genuinely restores P3's falsifiability and I could
not have found those five counter-examples without it. Removing the user branch was the right call
over narrowing it, and the builder's own comment states the decisive reason — a user deleting a reply
would have been recorded as a crash — which is a defect found against interest. Excluding `outcome`
from the hash fixed the pin exactly, and I could not break it with 2,990 mutated rows while my control
still fired on one. `resolve_expired_suspends` is the first sweep in this checkpoint whose predicate
is a fact the row carries about itself rather than a guess over five conditions. The instrument is
materially sounder than it was at round 8. What defeats it is that the repair stopped one column
short of the number that gets published — and a published number is the only part anyone reads.*
