# CP-0 · V-METRIC — verdict

**Subject:** the instrument, and the soundness of the numbers it will produce. Not the design.
**Artifact judged:** the repository at commit `327c3e1ed` (see §0.1 — the artifact was mutated
during this verification; the committed state is what is judged).
**Corpus:** `loreweave_chat`, `infra-postgres-1`, read-only. Last message `2026-08-03 17:02:14+00`.

---

## 1 · Verdict

| | verdict |
|---|---|
| **OVERALL** | 🔴 **FAIL** |
| **1 · is each new field answerable, and unanswerable today?** | ⚖️ **PARTIAL PASS** — five of seven fields are genuinely new; `withheld_tools` ships without the denominator that makes it a rate, and without the one stage the field exists for |
| **2 · is the baseline reproducible from the snapshot alone?** | 🔴 **FAIL** — the tool catalog is frozen and verifies; the *arm compositions do not reproduce*; the *four baseline numbers have no committed derivation at all*; the replay needs an unpinned live model |
| **3 · is the sample contaminated, and are the four numbers recomputable?** | 🔴 **FAIL** — one number is unsourced anywhere in the repo, one is not recomputable, one is computed by a definition that contradicts its own wording, one was never frozen; **57.5% of the baseline population is test-harness traffic** |
| **4 · what bound does the data actually support?** | 🔴 **FAIL, and this is the most valuable finding** — at the declaration unit the run's own first brick needs **0.6 – 12 years** to detect the improvements claimed. Longer than the run. |

**Authority exercised.** Per the verifier README (*"V-METRIC ruling a number unsound voids any V-LIVE
`PASS` that rests on it"*): **the `65.7%` prose-as-tool-error baseline is ruled unsound (§4.3), the
`61.8%` carry-forward baseline is ruled unsound as worded (§4.1), the `≈57%` identifier baseline is
ruled not recomputable (§4.2), and the `interrupted` baseline is ruled not frozen (§4.4).** Any PASS
resting on any of these four is void.

### The falsifier — what I looked for that would have made this PASS

I looked for **one committed artifact that pins the four baseline numbers to a derivation** — a
script, a SQL file, a JSON of numerator/denominator/predicate — such that an outsider could re-run it
in twelve months and get the identical figure. If `contracts/agent-runtime-baseline/` had contained a
`baseline-metrics.json` next to `tools-list.snapshot.json`, with the four counts, their denominators,
and the exact predicate for each class, decisions 2 and 3 would have passed. It contains the tool
catalog and nothing else. The four numbers exist only as prose in markdown, and I reproduced two of
them, contradicted one, and could not source the fourth.

Secondarily: I looked for the four numbers to be **stable under a reasonable restatement of their own
wording**. They are not — the carry-forward class spans 8.8% → 61.8% across four defensible readings
of the word *"already"* (§4.1), and the prose class moves 57.7% → 24.4% on **identical rows** under
CP-0's own new classifier (§4.3). A metric that moves 33pp on unchanged data because the classifier
changed cannot bound anything.

---

## 0 · Two integrity findings, recorded first

### 0.1 The artifact was modified while the verifiers were running

At the start of this verification the working tree matched `HEAD` for `stream_service.py`. Mid-run it
did not, and the change is materially responsive to a finding published by a *concurrent* verifier
(`CP-0-v-code.md` F-1) during my session.

```
$ git show HEAD:services/chat-service/app/services/stream_service.py | grep -n "budget_names_by_tokens_ex\|budget_names_by_tokens("
2900:                        names_to_activate = budget_names_by_tokens(
3006:                    names_to_activate = budget_names_by_tokens(
3098:                        names_to_activate = budget_names_by_tokens(
3267:                        names_to_activate = budget_names_by_tokens(

$ git diff --stat services/chat-service/app/services/stream_service.py
 .../chat-service/app/services/stream_service.py    | 90 +++++++++++++++++++---
 1 file changed, 78 insertions(+), 12 deletions(-)
```

The three γ verifiers were therefore not judging the same artifact. I judge `HEAD`, which is the
state the checkpoint was opened and committed at. **This is a protocol finding, not a code finding:**
a checkpoint whose subject changes under concurrent verification has not been verified.

I modified no tracked file. The only file I created (`eval/arms/results/`) I removed after reading it.

### 0.2 The instrument has never produced a single row

Every CP-0 field is present in the live schema and **empty**.

```sql
SELECT count(*) AS total_messages,
       count(*) FILTER (WHERE advertised_tools IS NOT NULL) AS adv_notnull,
       count(*) FILTER (WHERE withheld_tools IS NOT NULL) AS withheld_notnull,
       count(*) FILTER (WHERE outcome IS NOT NULL) AS outcome_notnull,
       count(*) FILTER (WHERE finish_reason IS NOT NULL) AS finish_notnull,
       count(*) FILTER (WHERE runtime_variant='agentruntime') AS variant_new,
       count(*) FILTER (WHERE tool_calls IS NOT NULL) AS with_tool_calls,
       min(created_at) AS first, max(created_at) AS last
FROM chat_messages;
```
```
 total_messages | adv_notnull | withheld_notnull | outcome_notnull | finish_notnull | variant_new | with_tool_calls |             first             |             last
----------------+-------------+------------------+-----------------+----------------+-------------+-----------------+-------------------------------+-------------------------------
           5720 |           0 |                0 |               0 |            249 |           0 |             973 | 2026-04-03 15:29:15.770751+00 | 2026-08-03 17:02:14.800675+00
```

Consequence for my mandate: every statement about the instrument's *behaviour* below rests on source
reading and on unit tests over in-memory objects. **Not one test in
`services/chat-service/tests/test_cp0_instrument.py` asserts that a row lands in Postgres carrying
these fields.** The write path is unexercised. That is not by itself a FAIL — CP-0 opened today — but
it means the instrument's *output* cannot be verified at all, only its *intent*.

---

## 2 · Decision 1 — is each field answerable, and unanswerable today?

**The "no answer today" half is established for five fields by one query.** Every key that exists in
any of the 7,447 historical `tool_calls[]` elements:

```sql
SELECT jsonb_object_keys(e) AS key, count(*)
FROM chat_messages m, jsonb_array_elements(m.tool_calls) e GROUP BY 1 ORDER BY 2 DESC;
```
```
    key     | count
------------+-------
 ok         |  7447
 args       |  7447
 tool       |  7447
 error      |  7416
 iteration  |  7416
 result     |  7416
 id         |  7411
 activity   |  1129
 pending    |    31
 runId      |    31
 toolCallId |    31
 task       |    10
```

**No `source`. No `latency_ms`. No `declaration`. No `runtime_variant`. No `duration`. No
`error_class`.** Twelve keys, seven of them universal.

| field | question it answers | has no answer today? | verdict |
|---|---|---|---|
| `advertised_tools` | *"when the model failed to call X, was X on the wire?"* | ✅ **yes.** The only surrogate is `chat_sessions.enabled_tools/activated_tools` — populated on **29 / 826** and **18 / 826** sessions respectively, mutated in place, **no history**. Reading it for a July turn returns today's value | ✅ new, not debt |
| `withheld_tools` | *"which filter, at which stage, deleted the most reachable capability?"* | ✅ yes, no column and no log row | ⚠️ **see below — ships without its denominator and without its founding stage** |
| `tool_calls[].source` | *"of what the model saw as an error, how much did a tool actually produce?"* | ✅ yes | ⚠️ **see §4.3 — it re-partitions the baseline it is compared to** |
| `latency_ms` | *"which admitted declaration is slow?"* | ✅ yes, no duration key exists | ⚠️ partial: stamped at `stream_service.py:4599` with `_dispatch_ms`, **but the subagent dispatch site `:3415` stamps `SOURCE_TOOL` with no latency**, so `latency_ms` is `None` there. Coverage denominator will be self-derived |
| mandatory `outcome` | *"what fraction of turns reached a defined terminal state?"* | ⚖️ **partly duplicates `finish_reason`** (249/2,653 = 9.4% populated), but the vocabulary genuinely differs (`abandoned_by_user`, `crashed`) | ⚠️ **"mandatory" is not enforced.** The DDL is `CHECK (outcome IS NULL OR outcome IN (...))` — NULL is legal. Mandatoriness is a convention in six call sites, not a constraint |
| `runtime_variant` | *"which runtime produced this?"* | ✅ yes | ✅ `NOT NULL DEFAULT 'legacy'` is the correct fail-safe direction |
| declaration identity | *"which capability ran, when one declaration supersedes several tool names?"* | ⚖️ **today it is a pure duplicate of `tool`** — `instrument.py:103`, `chunk["declaration"] = declaration or chunk.get("tool")`. It becomes non-redundant only when a consolidating declaration is admitted | ⚠️ **and see §5 — the map it needs does not exist in the frozen baseline** |

### 2.1 🔴 `withheld_tools` ships without its denominator

`AdvertisedToolsRecorder.record_pass` accepts `manifest_revision` (`instrument.py:172,187-188`).
**No caller anywhere passes it:**

```
$ grep -rn manifest_revision services/chat-service
services\chat-service\app\services\instrument.py:172:        manifest_revision: str | None = None,
services\chat-service\app\services\instrument.py:187:        if manifest_revision is not None:
services\chat-service\app\services\instrument.py:188:            entry["manifest_revision"] = manifest_revision
```

The repo's own pre-build analysis (`situations/S6-observation.md` §1.2 Q2b, §2.10) named this exactly:
*"`withheld_tools` needs a companion `manifest_revision` on the same row. Without it the field records
events but supports no rate, and every §5 question is a rate question."* The field was written into
the recorder and never wired. **`withheld_tools` is an event log with a moving denominator.**

### 2.2 🔴 The one stage `withheld_tools` exists to catch does not register

At the committed `HEAD`, the registered stages are exactly six:

```
$ git show HEAD:services/chat-service/app/services/stream_service.py | grep -n '"stage":'
2167:  {"tool": t, "stage": "oneshot_existence",
2173:  {"tool": t, "stage": f"oneshot_{_oneshot_mode}",
2179:  {"tool": t, "stage": "rail_gate",
2185:  {"tool": t, "stage": "failure_breaker",
2191:  {"tool": TOOL_LIST_NAME, "stage": "suppress_tool_list",
2204:  {"tool": t, "stage": f"permission_mode_{permission_mode}",
```

**The token budgeter is not among them.** All four production call sites at `HEAD` call the
non-reporting `budget_names_by_tokens` and discard the drops (query in §0.1). `budget_names_by_tokens_ex`
— the reporting variant CP-0.2 added — is reached at `HEAD` only from `eval/arms/run_arms.py:118` and
from the unit test.

This matters more than a missing stage. The DDL comment for the column states its purpose:

> *"the token budgeter silently deleted the one tool the model needed mid-turn (POC arm E, 0/3), and
> nothing recorded that the offered set had changed"* — `migrate.py:311-313`

**The founding defect of the entire effort is the one narrowing the field does not register.** A
`withheld_tools` dashboard at `HEAD` would show six stages and a clean absence where arm E's deletion
happened — which is indistinguishable from "the budgeter never dropped anything." That is the exact
shape of the standing question: *this number looks good precisely because the thing being measured is
broken.*

(The working-tree mutation described in §0.1 appears to address this. It is not what was committed at
the checkpoint, and I do not credit it.)

### 2.3 The audit's own count of narrowing mechanisms is 18

`README.md` of the spec: *"Runtime … exists — **18 filters, 13 of them silent**."* Six register.
The RUNSTATE invariant is *"Every withholding registers. An exclusion with no `{tool, stage, reason}`
is a defect."* **6 / 18 = 33%.** Note the denominator here comes from the audit (the SSOT), not from
what was built — had I taken the denominator from the six stages that ship, coverage would read 100%.
That is trap 3, and it is live in this checkpoint.

---

## 3 · Decision 2 — is the baseline reproducible from the snapshot alone?

### 3.1 ✅ The catalog snapshot is real and self-verifying

```
$ python -c "...hash the snapshot..."
top keys: ['_comment', 'frozen_at', 'gateway', 'user_overlay', 'catalog_sha256', 'summary', 'tools']
n tools: 315
recorded: eec0470b5a5a4f8a181f9515d1d654908250b72ad519567449955b554711ab6e
computed: eec0470b5a5a4f8a181f9515d1d654908250b72ad519567449955b554711ab6e
frozen_at = 2026-08-03T23:01:35.436757+00:00
gateway   = http://localhost:8218
user_overlay = False
summary = {'tool_count': 315, 'deprecated_count': 75, 'deprecated_structural_count': 54,
           'deprecated_prose_only_count': 21, ...}
```

Content hash verifies. `run_arms.py:64-68` refuses to run on mismatch. Good, and better than the
prior state.

**One population caveat:** `user_overlay = False`. The freeze script's own docstring says *"the
baseline must include what a REAL turn saw, and a real turn carries a user"* (`freeze-tool-catalog.py:63-65`).
The frozen surface is the no-user surface. It is a defensible choice; it is not the one the script
argues for, and it is not stated as a limitation in the snapshot.

### 3.2 🔴 The arm compositions do **not** reproduce

Published (`poc/P1-P2-findings.md:856-862`) against replayed-from-snapshot today:

```
$ python eval/arms/run_arms.py --dry-run
arm A:   1 tools, ~   286 tok, book_list=PRESENT | 1 tool — the answer, alone
arm B:   0 tools, ~     0 tok, book_list=ABSENT  | fixed envelope; schema arrives as conversation text
arm C:  35 tools, ~  7770 tok, book_list=PRESENT | every book_* tool including retired (17 retired)
arm D:  18 tools, ~  4834 tok, book_list=PRESENT | current-only — retired removed
arm E:   6 tools, ~  1405 tok, book_list=ABSENT  | exactly what the token budget left; budgeter dropped 29
```

| arm | published | replayed from the frozen snapshot | agrees? |
|---|---|---|---|
| C | 35 tools, **19 retired**, **7,921 tok** | 35 tools, **17 retired**, **7,770 tok** | ❌ retired count, tokens |
| D | **16** current-only, **4,661 tok** | **18** current-only, **4,834 tok** | ❌ |
| E | **exactly the 7** the budget left | **6** tools | ❌ |

**The snapshot pins a catalog that is not the catalog the published results were produced against.**
It froze on 2026-08-03, after the drift the freeze exists to defeat had already occurred. The freeze
makes the baseline reproducible *from now on*; it does **not** make the published A–E numbers
reproducible, which is what CP-0.5 is written to claim (`freeze-tool-catalog.py:7-14`, RUNSTATE 0.5).

### 3.3 ⚖️ The scores reproduce; the mechanism does not

I replayed arms A and E against the live model, then deleted the untracked output.

```
$ python eval/arms/run_arms.py --arms A,E
arm A:   1 tools, ~   286 tok, book_list=PRESENT
   trial 1: PASS called=['book_list']
   => 1/1
arm E:   6 tools, ~  1405 tok, book_list=ABSENT
   trial 1: FAIL called=['book_list_chapters']
   trial 2: FAIL called=['book_list_chapters']
   trial 3: FAIL called=['book_list_chapters']
   => 0/3
```
```
model: google/gemma-4-26b-a4b-qat  baseline_sha: eec0470b5a5a4f8a
A 1/1 tools=['book_list']
    {'correct': True,  'called': ['book_list'],          'args': ['{"kind":"books"}'],  'named_missing_tool_in_args': False}
E 0/3 tools=['book_chapter_save_draft','book_get','book_list_chapters','book_scene_get','book_steering_list','book_update_details']
    {'correct': False, 'called': ['book_list_chapters'], 'args': ['{"book_id":"all"}'], 'named_missing_tool_in_args': False}
    {'correct': False, 'called': ['book_list_chapters'], 'args': ['{"book_id":"all"}'], 'named_missing_tool_in_args': False}
    {'correct': False, 'called': ['book_list_chapters'], 'args': ['{"book_id":"all"}'], 'named_missing_tool_in_args': False}
```

**A: 1/1 reproduces. E: 0/3 reproduces.** That is a genuine result and I credit it.

But the script's own headline signature detector reads **False on all three E trials**. The published
arm-E finding, restated verbatim in the script's docstring (`run_arms.py:16-19`), is *"the model put
the NAME OF THE MISSING TOOL into an argument"* — `book_list_revisions{"book_id": "book_list"}`.
Today the model calls `book_list_chapters{"book_id":"all"}` three times. The score is the same; the
evidence for the mechanism is gone. **`named_missing_tool_in_args` is a field that will read 0 forever
and be believed** unless someone re-reads the trials.

### 3.4 🔴 Two unpinned dependencies inside the "frozen" baseline

1. **The model.** `ARMS_BASE_URL=http://localhost:1234/v1`, `ARMS_MODEL=google/gemma-4-26b-a4b-qat`,
   `TEMPERATURE=0.2`. No weights hash, no build id, no seed. The script's own docstring concedes it
   (*"The only live dependency is the model itself"*), but a control group whose only live dependency
   is the thing being measured is not frozen. A quantised local model reloaded next quarter is a
   different arm and there is no way to detect that.
2. **The budgeter.** `run_arms.py:115-120` does `sys.path.insert(REPO/services/chat-service)` and
   imports `budget_names_by_tokens_ex` from the **live source tree**. Arm E's composition is therefore
   a function of code that CP-2.3 and CP-1 are scheduled to change. The catalog is pinned; the
   mechanism that selects from it is not.

### 3.5 🔴 The four baseline numbers have **no committed derivation whatsoever**

This is the decisive item and it is not close. `contracts/agent-runtime-baseline/` contains exactly
one file:

```
$ ls -la contracts/agent-runtime-baseline/
-rw-r--r-- 795482 tools-list.snapshot.json
```

There is no baseline-metrics artifact, no SQL, no script. The four numbers the *whole run is scored
against* live only as markdown prose. `eval/arms/results/` did not exist before I ran the script, so
even the catalog arms had never been replayed.

**A baseline you cannot re-derive is a memory, not a control group** — which is the exact sentence
CP-0.5 was written to answer, applied to the four numbers instead of the catalog. CP-0.5 froze the
wrong artifact. §4 shows what that costs.

---

## 4 · Decision 3 — contamination and recomputation of the four numbers

**The corpus is stable.** The headline volume reproduces exactly, so drift is not a confound:

```sql
SELECT count(*) AS calls,
       count(*) FILTER (WHERE (e->>'ok')::bool) AS ok_true,
       count(*) FILTER (WHERE NOT (e->>'ok')::bool) AS ok_false,
       count(DISTINCT m.message_id) AS turns, count(DISTINCT m.session_id) AS sessions
FROM chat_messages m, jsonb_array_elements(m.tool_calls) e;
```
```
 calls | ok_true | ok_false | turns | sessions
-------+---------+----------+-------+----------
  7447 |    3437 |     4010 |   973 |      550
```

### 4.0 🔴 Contamination: **57.5% of the baseline failures are test-harness traffic**

The brief names a 37-session harness with ~580 blank-argument calls. What is actually in the corpus is
larger and differently shaped. Blank-argument concentration:

```sql
WITH c AS (SELECT m.session_id, s.title, coalesce(e->>'args','') AS args
           FROM chat_messages m JOIN chat_sessions s USING (session_id),
                jsonb_array_elements(m.tool_calls) e),
     per AS (SELECT session_id, title, count(*) calls,
                    count(*) FILTER (WHERE args IN ('','{}','null')) blank FROM c GROUP BY 1,2)
SELECT count(*) AS sessions_all_blank, sum(calls) AS calls FROM per WHERE blank=calls AND calls>0;
```
```
 sessions_all_blank | calls
--------------------+-------
                 66 |   905
```

66 sessions in which *every* call has blank arguments, 905 calls — of which the `sg-*` scenario
harness is 29 sessions / 476 calls, 100% blank-args. Separately, `ds-2026-*` is 260 sessions / 2,594
calls. The largest single contaminant is not in the brief at all:

```sql
WITH c AS (SELECT s.title, (e->>'ok')::bool ok, coalesce(e->>'error','') err
           FROM chat_messages m JOIN chat_sessions s USING (session_id),
                jsonb_array_elements(m.tool_calls) e)
SELECT title, count(*) calls, count(*) FILTER (WHERE NOT ok) errors,
       count(*) FILTER (WHERE NOT ok AND err ILIKE '%You have already called tool_list%') tool_list_breaker
FROM c GROUP BY 1 ORDER BY 4 DESC LIMIT 4;
```
```
       title        | calls | errors | tool_list_breaker
--------------------+-------+--------+-------------------
 F17 monitor verify |  1220 |   1180 |              1180
 The Tidewright     |   249 |    233 |                 0
 Scenario2          |   225 |    194 |                 0
 New Chat           |   219 |    153 |                 0
```

> **All 1,180 `tool_list` breaker fires — the single largest error class in the corpus, 29.4% of every
> failure the baseline is computed over — come from FOUR sessions of a verification harness named
> "F17 monitor verify".**

The whole-corpus split, harness vs organic, computed once for all three recomputable classes:

```sql
WITH calls AS (
  SELECT m.session_id, s.title, m.sequence_num, ord, e->>'tool' AS tool,
         (e->>'ok')::bool AS ok, coalesce(e->>'error','') AS err
  FROM chat_messages m JOIN chat_sessions s USING (session_id),
       jsonb_array_elements(m.tool_calls) WITH ORDINALITY AS t(e, ord)),
tagged AS (SELECT *,
  (title='F17 monitor verify' OR title LIKE 'sg-%' OR title LIKE 'ds-2026-%' OR title ~ '^(G-|M-)') AS harness,
  (err ILIKE '%You have already called%' OR err ILIKE '%already ran this turn%'
   OR err ILIKE '%has already FAILED%' OR err ILIKE '%keeps being called with missing/blank%'
   OR err ILIKE '%STOP calling find_tools%') AS breaker FROM calls),
seq AS (SELECT *, row_number() OVER (PARTITION BY session_id ORDER BY sequence_num, ord) rn FROM tagged),
firstok AS (SELECT session_id, tool, min(rn) ok_rn FROM seq WHERE ok GROUP BY 1,2)
SELECT harness, count(*) calls, count(*) FILTER (WHERE NOT ok) fails, ...
```
```
 harness | calls | fails | breaker_fails | breaker_pct | cf_anywhere | cf_anywhere_pct | cf_earlier | cf_earlier_pct
---------+-------+-------+---------------+-------------+-------------+-----------------+------------+----------------
 f       |  2869 |  1706 |           887 |        52.0 |        1000 |            58.6 |        859 |           50.4
 t       |  4578 |  2304 |          1428 |        62.0 |        1477 |            64.1 |       1432 |           62.2
 (all)   |  7447 |  4010 |          2315 |        57.7 |        2477 |            61.8 |       2291 |           57.1
```

> **2,304 / 4,010 = 57.5% of the failures in the frozen baseline come from harness sessions.**

The new runtime will be measured on organic traffic. Comparing organic-new against a baseline that is
majority-synthetic is a population mismatch on every class, and it runs in the flattering direction:
harness sessions are 62.0% breaker and 64.1% carry-forward, organic sessions are 52.0% and 58.6%.
**Roughly 6pp and 3pp of "improvement" are available before the new runtime does anything.**

Also, per the brief: **one dogfooding user** — confirmed. 759 of 826 sessions (91.9%) belong to one
`owner_user_id`; 7 users exist. `message_feedback` has **3 rows** against 2,653 assistant turns
(0.11%). There is no ground-truth channel; every number below is defined in terms of `ok`.

---

### 4.1 🔴 Class 1 — carry-forward. Asserted **61.8% (2,477 / 4,010)**

**Recomputed: the asserted figure is exactly reproducible, and it does not compute what its own
wording says.**

The claim is *"a failure on a declaration that **already** succeeded in the same session."*

```sql
WITH calls AS (SELECT m.session_id, m.sequence_num, ord, e->>'tool' tool, (e->>'ok')::bool ok
               FROM chat_messages m,
                    jsonb_array_elements(m.tool_calls) WITH ORDINALITY AS t(e, ord)),
seq AS (SELECT *, row_number() OVER (PARTITION BY session_id ORDER BY sequence_num, ord) rn FROM calls),
firstok AS (SELECT session_id, tool, min(rn) first_ok_rn FROM seq WHERE ok GROUP BY 1,2)
SELECT count(*) FILTER (WHERE NOT s.ok) total_fails,
       count(*) FILTER (WHERE NOT s.ok AND f.first_ok_rn < s.rn)   AS strictly_earlier,
       count(*) FILTER (WHERE NOT s.ok AND f.first_ok_rn IS NOT NULL) AS anywhere_in_session
FROM seq s LEFT JOIN firstok f USING (session_id, tool);
```
```
 total_fails | fail_after_earlier_success | pct_strict_earlier | fail_tool_ok_anywhere | pct_anywhere
-------------+----------------------------+--------------------+-----------------------+--------------
        4010 |                       2291 |               57.1 |                  2477 |         61.8
```

And, per message-sequence rather than per-call ordinality:

```
             variant              | fails | carry | pct
----------------------------------+-------+-------+------
 earlier MESSAGE (seq strictly <) |  4010 |   352 |  8.8
 same-or-earlier MESSAGE (seq <=) |  4010 |  2408 | 60.0
```

**Four defensible readings of the same sentence:**

| reading | count | % of 4,010 |
|---|---|---|
| the tool succeeded in a strictly earlier assistant **turn** | **352** | **8.8%** |
| the tool succeeded strictly earlier in call order (the literal reading of *"already"*) | **2,291** | **57.1%** |
| the tool succeeded at `sequence_num ≤` this failure's — RT6's published method | **2,408** | **60.0%** |
| the tool succeeded **anywhere in the session, including afterwards** | **2,477** | **61.8%** ← the frozen baseline |

**The published 61.8% is the loosest of the four and the only one that is not order-respecting.** It
counts a failure at call 5 as "carry-forward" when the tool's only success is at call 50 — i.e. it
counts *failed-then-succeeded* as *succeeded-then-failed*. The inflation over the literal reading is
186 rows, +4.7pp. The repo contains a third figure (RT6-A1-4: 2,408 / 60.0%) which no downstream
document uses.

**Why this is a FAIL and not a quibble.** There is no committed predicate. The claim is *"strictly
lower than 61.8%."* Recomputing the new runtime with the literal reading of *"already"* yields 57.1%
on the **unchanged old data** — a 4.7pp "improvement" available by writing a more correct query. At
the declaration unit (§6), 4.7pp is larger than any effect this run can detect in under a year.

**Trap 1 applies here directly.** The numerator's *"already succeeded"* is `ok=true`, and C-5 exists
because `ok=true` can be a lie (a tool returns success against a substituted object). A wrong-object
success is counted as a success, which makes every subsequent failure on that tool "carry-forward". A
runtime that substitutes *less* produces fewer `ok=true` firsts and therefore a lower carry-forward
rate **without fixing anything about carrying values forward**. **CP-0 ships no wrong-object
detector** — `situations/S6-observation.md` §2.2 identified it as required before P5 ships; it is not
among items 0.1–0.7. So the class most central to the run is defined on the one signal the run's own
contract says is unreliable, with no way to bound the error.

### 4.2 🔴 Class 2 — identifier resolution. Asserted **≈57% of real (non-breaker) errors**

**Recomputed: not recomputable. There is no committed classifier, and plausible rules span 49%–68%.**

Source figure (`poc/P1-P2-findings.md:519`): *"960 of 1,688 — 57% — are identifier-resolution
failures."* The predicate is nowhere. My reconstruction:

```sql
WITH f AS (SELECT coalesce(e->>'error','') err FROM chat_messages m, jsonb_array_elements(m.tool_calls) e
           WHERE NOT (e->>'ok')::bool),
nb AS (SELECT * FROM f WHERE NOT (err ILIKE '%You have already called%' OR err ILIKE '%already ran this turn%'
       OR err ILIKE '%has already FAILED%' OR err ILIKE '%keeps being called with missing/blank%'
       OR err ILIKE '%STOP calling find_tools%'))
SELECT count(*) real_errors, ... FROM nb;
```
```
 real_errors | uuid_shape | field_required | missing_props | notfound | ident_narrow | ident_wide
-------------+------------+----------------+---------------+----------+--------------+------------
        1695 |        444 |            125 |           267 |      321 |          836 |       1157
```

| rule | numerator | denominator | % |
|---|---|---|---|
| UUID-shape + `Field required` + `missing properties` | 836 | 1,695 | **49.3%** |
| ...plus `not found` / `not accessible` | 1,157 | 1,695 | **68.3%** |
| **published** | 960 | 1,688 | **56.9%** |

My denominator (1,695) does not match the published one (1,688), and the doc elsewhere gives 1,658 for
the same population. **A 19pp band around a claim that asks for "strictly lower".**

**And CP-0 makes this class *worse*, not better.** The instrument adds `source`, which fixes the
*denominator* (real vs breaker). It adds **no `error_class` field** — no C-7 taxonomy, nothing. So the
*numerator* stays a regex over English error strings on both arms. The new runtime's stated purpose
includes rewriting those strings (C-7, "a remedy sentence"). **A metric whose numerator is a regex over
text the treatment is designed to rewrite will improve by construction.** Change `entity_id must be a
UUID` to a structured `terminal_permanent` payload and the identifier-resolution share falls toward
zero with the failure rate unchanged. That is the standing question answered in the affirmative.

### 4.3 🔴 Class 3 — our own prose as a tool error. Asserted **65.7% of failures**

**Recomputed: 65.7% does not exist anywhere in this repository as a measurement, and CP-0's own
classifier moves the recomputable figure by 33.3pp on identical rows.**

**(a) The number is unsourced.** Every occurrence in the repo:

```
$ grep -rn "65\.7" .
CP-0-V-METRIC-PROMPT.md:26 | situations/S6-observation.md:201,554 | situations/S3-execute-recovery.md:124
DESIGN-HYPOTHESIS.md:258   | ARCHITECTURE.md:220,309,867         | RUNSTATE.md:32
services/chat-service/app/services/instrument.py:29
services/chat-service/tests/test_cp0_instrument.py:131
services/chat-service/app/db/migrate.py:370
```

Every one is a restatement. **None is a derivation.** The *measuring* documents say something else:

- `poc/P1-P2-findings.md:60,71` — *"Of 3,976 errors carrying text, **58%** … **2,318 of 3,976**"*
- `redteam/RT5-can-we-even-measure.md:202` — *"**58%** of `ok=false` records are our own loop-breaker prose"*
- `situations/S1-contract.md:48` — *"**2,344 / 4,010 (58.5%)**"*, with a full itemisation

`65.7` first appears in `DESIGN-HYPOTHESIS.md:258` with no working, and propagates from there into the
DDL comment, the instrument docstring, the test docstring, and the frozen baseline table. **An
unsourced number was hard-coded into the migration that creates the instrument.**

My recomputation of the itemised predicate:

```
 total_fails | p_already_called | p_already_ran | p_already_failed | p_blank_args | p_find_tools | breaker_union_5 | pct
-------------+------------------+---------------+------------------+--------------+--------------+-----------------+------
        4010 |             1775 |           263 |               27 |           93 |          157 |            2315 | 57.7
```

**2,315 / 4,010 = 57.7%.** Consistent with 58% / 58.5%. Not with 65.7%.

**(b) 🔴 The killer: CP-0.3's own classifier moves this number 33.3pp on unchanged data.**

`instrument.py:113-117` defines `RUNTIME_PRIMITIVES = {find_tools, tool_list, tool_load,
conversation_search, chat_search_sessions, load_skill, workflow_list, workflow_load}` and routes their
results to `source='meta'`, **not** `source='breaker'`.

```sql
WITH f AS (SELECT e->>'tool' tool, coalesce(e->>'error','') err
           FROM chat_messages m, jsonb_array_elements(m.tool_calls) e WHERE NOT (e->>'ok')::bool),
t AS (SELECT *, (<the 5 breaker patterns>) AS prose_breaker,
       tool IN ('find_tools','tool_list','tool_load','conversation_search','chat_search_sessions',
                'load_skill','workflow_list','workflow_load') AS is_runtime_primitive FROM f)
SELECT count(*) total_fails,
       count(*) FILTER (WHERE prose_breaker) prose_breaker_old_method,
       count(*) FILTER (WHERE prose_breaker AND is_runtime_primitive) prose_and_primitive,
       count(*) FILTER (WHERE prose_breaker AND NOT is_runtime_primitive) breaker_after_meta_split
FROM t;
```
```
 total_fails | prose_breaker_old_method | old_pct | would_be_meta | prose_and_primitive | breaker_after_meta_split | new_pct_same_data
-------------+--------------------------+---------+---------------+---------------------+--------------------------+-------------------
        4010 |                     2315 |    57.7 |          1337 |                1337 |                      978 |              24.4
```

> **On identical rows, the same population reads 57.7% under the baseline method and 24.4% under the
> new instrument's classifier.** 1,337 failures — `tool_list` (1,180) and `find_tools` (157) — move
> from *"our own prose"* into *"a runtime primitive answered."*

The claim to be proven is *"our own prose counted as a tool error, **strictly lower** than 65.7%."*
The baseline arm can only ever be prose-matched (the 7,447 historical rows have no `source`, and
`instrument.py`'s own docstring says re-labelling by prose *"produced a lower bound that was then
reported as a population count"*). The new arm will be measured with `source='breaker'`. **The new
runtime wins this class by 41.3pp before it serves a request** — 65.7% asserted vs 24.4% mechanical.

This is the single clearest instance of the standing question in the checkpoint. `situations/S6-observation.md`
§2.7 predicted it exactly, before the build: *"7,447 historical rows can never be re-labelled — `source`
is knowable only at emission time — so every new-runtime number will be strictly richer and **not
comparable** to the control."* CP-0 shipped the field and did not address the incomparability.

### 4.4 🔴 Class 4 — turns ending `interrupted`. Asserted **"to be frozen at CP-0"**

**Recomputed: 11 / 2,653 = 0.41%. It was not frozen, and it is not interpretable.**

```sql
SELECT coalesce(finish_reason,'(null)') finish_reason, count(*),
       round(100.0*count(*)/sum(count(*)) OVER (),2) pct
FROM chat_messages WHERE role='assistant' GROUP BY 1 ORDER BY 2 DESC;
```
```
 finish_reason  | count |  pct
----------------+-------+-------
 (null)         |  2404 | 90.61
 stop           |   205 |  7.73
 awaiting_input |    31 |  1.17
 interrupted    |    11 |  0.41
 error          |     2 |  0.08
```

Three findings:

1. **No committed artifact freezes this value.** Grepping the whole spec directory for `interrupted`
   returns discussion and no frozen figure. The RUNSTATE row still reads *"to be frozen at CP-0"* and
   CP-0's item list (0.1–0.7) contains no item that freezes it. **A deliverable of the checkpoint was
   not delivered.**
2. **90.6% of the population is NULL.** A rate over a 9.4%-populated column is not a rate.
3. 🔴 **The migration shim would move it from 0.41% to ~91%.** `instrument.py:243-258`:
   ```python
   match finish_reason:
       case "stop": return OUTCOME_COMPLETED
       ...
       case _:      return OUTCOME_INTERRUPTED
   ```
   `None` falls to `case _`. Read the historical rows through the shim and `interrupted` becomes
   2,404 + 11 = 2,415 / 2,653 = **91.0%**. The new arm never routes through the shim — its write
   sites set `outcome` directly. **Same metric name, two mechanisms, two arms.** Whatever the new
   runtime does, it beats a 91% baseline; whatever it does, it will struggle to beat 0.41%. Neither
   comparison means anything, and nothing in the checkpoint says which one will be used.

`ARCHITECTURE.md:276-278` already concedes the metric is *"uninterpretable until cancel has a terminal
state of its own."* CP-0 added `abandoned_by_user` — going forward. It did not, and cannot, split the
historical `interrupted` rows. So the baseline for class 4 is permanently uninterpretable and the
checkpoint did not record a number for it.

### 4.5 The mandatory-outcome coverage metric will be a self-derived denominator (trap 3)

RUNSTATE 0.4 concedes: *"one known hole left open: an empty terminal turn writes no row."* A coverage
percentage computed as `rows_with_outcome / rows_written` **cannot see the turns that wrote no row** —
which is precisely the population the field exists to find. It will read 100%. The correct denominator
is turns *started*, and nothing counts those. Combined with `CHECK (outcome IS NULL OR ...)` — NULL is
legal — "mandatory" is enforced by neither the schema nor the denominator.

---

## 5 · Trap 4 — the comparison that cannot be computed

**This alone is a `FAIL` under the brief's own terms, "regardless of how complete the schema looks."**

The stated unit (RUNSTATE §"The measurement unit is the DECLARATION"): *"calls to declaration **D on
the new runtime** against **D (or its predecessor) in the frozen baseline**."*

The join needs three things on the baseline side. It has one.

| the join needs | on the new arm | on the frozen baseline (7,447 historical calls) |
|---|---|---|
| the declaration identity | ✅ `declaration` | ⚠️ only `tool`; `declaration` does not exist (§2 key census) |
| **a predecessor map** *tool → declaration* | — | 🔴 **does not exist for the run's own first brick** |
| the real-vs-breaker split | ✅ `source` | 🔴 does not exist; prose-matching only, and it re-partitions (§4.3b) |
| latency | ⚠️ partial | 🔴 does not exist |

**The predecessor map, checked against the frozen snapshot.** Brick 2 is `book_list`, chosen because
*"it supersedes three legacy tools, so it exercises consolidation, our primary migration operation."*

```
$ python -c "...read tools-list.snapshot.json..."
tools declaring superseded_by: 54
pointing at book_list: []

book_list:          _meta keys=['scope','synonyms','tier']              superseded_by=None  visibility=None
book_list_chapters: _meta keys=['scope','synonyms','tier','visibility'] superseded_by=None  visibility='legacy'
book_list_revisions:_meta keys=['scope','synonyms','tier','visibility'] superseded_by=None  visibility='legacy'
book_get:           _meta keys=['scope','synonyms','tier','visibility'] superseded_by=None  visibility='legacy'
book_list_scenes:   NOT IN SNAPSHOT
```

> **Zero of the 315 frozen tools declare `superseded_by: book_list`.** The three tools `book_list` is
> said to supersede are marked `visibility: legacy` and name no successor. The map that the first
> matched pair requires **is not in the frozen artifact**, and a map written by hand later is exactly
> the unpinned dependency the freeze exists to eliminate.

`instrument.py:90-96` states the field's purpose: *"the new declaration's calls join against its
predecessors' calls in the frozen baseline. Without it the run accumulates traffic that cannot answer
its own question."* The field ships. **The other half of the join does not.**

Note the map is not merely absent — it is *known* absent. CP-0.5's own finding (RUNSTATE, after item
0.7) records that `superseded_by` is the only retirement key in the whole surface and 21 retirements
are prose-only. That finding was reported as a prerequisite for the third-party sunset window. It is
also, unreported, a prerequisite for the run's central comparison.

**Verdict on trap 4: FAIL.** No amount of accumulated traffic answers the question for brick 2.

### Trap 2 — is the guard red over the right subject?

Checked, and the unit tests are **sound** where they exist. `test_the_reporting_variant_does_not_change_what_is_kept`
compares `budget_names_by_tokens` against `budget_names_by_tokens_ex` across five budgets — the right
subject (the instrument must not move the thing it measures). `test_dropped_names_are_returned_not_discarded`
asserts `dropped` is non-empty first, so it cannot pass vacuously.
`test_the_vocabulary_matches_the_database_constraint` parses the DDL and compares to the Python
constants — the right subject (drift between the two halves).

**What no test covers:** that any of it reaches Postgres. Every assertion is over an in-memory
`AdvertisedToolsRecorder` or a dict. Combined with §0.2 (zero rows), **the guards are red-able over
the recorder and untested over the record.**

---

## 6 · Decision 4 — the bound the data actually supports

### 6.1 The two stated arithmetic facts — both check out

```
one-sided 95% upper bound from 3/3 :  1 - 0.05^(1/3) = 0.6316   ->  63.2%   ✅
n for <=10% at 95%                 :  ln(0.05)/ln(0.9) = 28.43  ->  29      ✅
54.2% baseline sits inside [0, 63.2%]                                        ✅
```

### 6.2 The traffic rate — and it is worse than the brief's headline

```sql
WITH c AS (SELECT date_trunc('week', m.created_at)::date wk, count(*) calls
           FROM chat_messages m, jsonb_array_elements(m.tool_calls) e GROUP BY 1)
SELECT wk, calls FROM c ORDER BY wk DESC LIMIT 10;
```
```
     wk     | calls          |  weeks_with_traffic | total | mean_wk | median_wk
------------+-------         |  -------------------+-------+---------+-----------
 2026-08-03 |     5          |                  11 |  7447 |   677.0 |     102.0
 2026-07-27 |   102
 2026-07-20 |  2714
 2026-07-13 |  2431
 2026-07-06 |  1828
 2026-06-29 |    72
 2026-06-22 |   126
 ...
```

The brief's **~414 calls/week** is `7,447 / 18 weeks`. The distribution is not remotely uniform: three
weeks (2026-07-06 … 07-20) carry **6,973 / 7,447 = 93.6%**, and those are the weeks containing the
harness runs. **Median week: 102 calls. Last two weeks: 102 and 5.**

### 6.3 🔴 At the declaration unit, detection takes years

The comparison unit is the **declaration**, and the new runtime starts with one. Brick 2's actual rate:

```sql
SELECT e->>'tool' tool, count(*) calls, count(*) FILTER (WHERE (e->>'ok')::bool) ok,
       min(m.created_at)::date first, max(m.created_at)::date last
FROM chat_messages m, jsonb_array_elements(m.tool_calls) e
WHERE e->>'tool' IN ('book_list','book_list_chapters','book_list_revisions','book_get','tool_list')
GROUP BY 1 ORDER BY 2 DESC;
```
```
        tool        | calls | ok  |   first    |    last
--------------------+-------+-----+------------+------------
 tool_list          |  1747 | 567 | 2026-07-09 | 2026-08-03
 book_get           |   561 |  59 | 2026-06-21 | 2026-07-21
 book_list_chapters |   160 |  59 | 2026-06-21 | 2026-08-03
 book_list          |    43 |  35 | 2026-06-20 | 2026-07-26
```

> **`book_list` — the run's chosen first declaration — has 43 calls in the entire corpus. ~3.9
> calls/week. 8 failures total, ever. ~0.73 failures/week.**

One-sample test against a known baseline `p0`, α=.05 two-sided, power=.80:

| class | `p0` | detect −10pp | detect −20pp | detect −30pp |
|---|---|---|---|---|
| carry-forward | 61.8% | 189 failures = **5.0 yr** | 47 = **1.2 yr** | 21 = **0.6 yr** |
| prose-as-error | 65.7% | 182 failures = **4.8 yr** | 46 = **1.2 yr** | 20 = **0.5 yr** |
| identifier resolution | 57% | 194 non-breaker failures = **12.2 yr** | 48 = **3.0 yr** | 21 = **1.3 yr** |

*(at `book_list`'s observed 0.73 failures/week; the identifier row additionally scales by the 42%
non-breaker share.)*

**The claim as written is worse than any row above.** It says only *"strictly lower."* An unbounded
effect size requires an unbounded sample. Until a minimum detectable effect is named per class,
**no sample size can satisfy the claim** — and each of the four classes has a definitional band (§4)
wider than 10pp, so even a 10pp target is inside the noise of *how the metric is defined*.

### 6.4 🔴 The admission cadence is arithmetically impossible

RUNSTATE §L4: *"Throughput is a first-class metric here: **≈13 admissions/week** keeps pace with the
model cadence."* §4.2: 29 consecutive successes per declaration to assert ≤10%.

```
13 admissions/wk x 29 consecutive successes = 377 successful calls/week needed, product-wide
available: mean week  414 calls x 46.2% ok = 191 successes/wk  ->  1.97x short
           median week 102 calls x 46.2% ok =  47 successes/wk  ->  8.0x  short
```

And *consecutive* is the binding word. At `book_list`'s own observed success rate:

```
P(29 consecutive successes | p = 35/43 = 0.814) = 0.0026
```

**One chance in 385 that brick 2 ever clears its own admission gate**, at 3.9 calls/week — 7.4 weeks
of perfect traffic for a single shot with a 0.26% hit rate.

### 6.5 The answer the brief asked for, plainly

> **Longer than the run.** For the run's own first declaration, detecting a 10pp improvement in the
> headline carry-forward class takes **five years** of traffic at the observed rate; the identifier
> class takes **twelve**. The admission gate the design sets for itself is **2× to 8× above** the
> product's entire successful-call volume, and brick 2 clears it with probability **0.0026**.
>
> **This run cannot measure what it is claiming, at any point in its planned life, by a factor of
> roughly 50–600× in sample size.** That is not fixed by better instrumentation; it is a traffic
> problem, and the only remedies are a named minimum detectable effect, pooling across declarations
> (which forfeits the matched-pair design), or a synthetic task set — none of which CP-0 contains.

---

## 7 · The bound table

Denominator stated for every row. "Population correct?" asks whether the population the number is
computed over is the population the claim is about.

| class | asserted | **recomputed** | denominator | contamination handling | population correct? | N needed for the claim |
|---|---|---|---|---|---|---|
| **carry-forward** | 61.8% (2,477) | **61.8% (2,477)** reproduces exactly — but the literal reading of *"already"* gives **57.1% (2,291)**, RT6's method **60.0% (2,408)**, earlier-turn **8.8% (352)** | 4,010 `ok=false` `tool_calls[]` elements | harness = 2,304/4,010 = **57.5%**; organic-only = **58.6%** (anywhere) / **50.4%** (earlier) | 🔴 **no** — majority synthetic; and rests on `ok=true` with no wrong-object detector (C-5) | 189 failures for −10pp = **5.0 yr** at brick 2's rate |
| **identifier resolution** | ≈57% (960/1,688) | 🔴 **not recomputable.** 49.3% (836/1,695) narrow, 68.3% (1,157/1,695) wide | non-breaker failures — my count 1,695, published 1,688 and 1,658 in the same document | prose-classified on both arms; harness share unmeasurable without a fixed predicate | 🔴 **no** — no committed classifier; numerator is a regex over text C-7 will rewrite | 194 non-breaker failures for −10pp = **12.2 yr** |
| **prose as tool error** | 65.7% | 🔴 **65.7% has no derivation in the repo.** The measured figure is **57.7% (2,315/4,010)**; the repo's own sources say 58% / 58.5%. Under CP-0's own classifier the same rows read **24.4% (978/4,010)** | 4,010 failures | **1,180 of the 2,315 (51%) come from 4 sessions of "F17 monitor verify"** | 🔴 **no** — half the class is one test harness, and the two arms use different classifiers | 182 failures for −10pp = **4.8 yr**; but the class moves 33.3pp on reclassification alone |
| **`interrupted`** | "to be frozen at CP-0" | 🔴 **never frozen.** Current value **11 / 2,653 = 0.41%**; through the CP-0 shim the same rows read **2,415 / 2,653 = 91.0%** | 2,653 assistant rows, **90.6% NULL** | n/a — the metric is uninterpretable before decontamination is even reached | 🔴 **no** — `ARCHITECTURE.md:276` concedes it | undefined — no baseline exists to test against |

---

## 8 · Summary of the FAIL

CP-0's stated job is *"prove each field answers a question that has no answer today, and prove the
baseline is reproducible from the snapshot alone."*

The first half largely holds: five of seven fields are genuinely new, and the key census proves it.

The second half does not, and the failure is structural rather than incidental. **CP-0 froze the tool
catalog and left the four numbers unfrozen** — no predicate, no denominator, no script. As a result:

- one of the four (**65.7%**) does not exist as a measurement anywhere in the repository, and has been
  compiled into the migration comment, the instrument docstring, and the test docstring;
- one (**≈57%**) has no classifier and spans 19pp under plausible restatements;
- one (**61.8%**) computes something other than what it says, and the literal reading is 4.7pp lower on
  unchanged data;
- one (**`interrupted`**) was a deliverable of this checkpoint and was not delivered;
- **57.5% of the population all four are computed over is test-harness traffic**, and 51% of the
  prose class is four sessions of one verification harness;
- the new instrument's own classifier moves the prose class **33.3pp on identical rows**, in the
  direction that flatters the new runtime;
- the matched-pair join the run depends on **cannot be constructed for its own first declaration**, and
- at the declaration unit the run needs **0.6 to 12 years** to detect the improvements it claims.

Answering the standing question directly: **yes — every one of these four numbers would look good even
if the thing being measured were broken**, and for three of them I can name the mechanism and the
magnitude.

---

*Queries run against `infra-postgres-1` / `loreweave_chat` as `loreweave`, read-only. Arms replayed via
`python eval/arms/run_arms.py`; the untracked `eval/arms/results/` it produced was removed. No tracked
file was modified by this verification.*
