# CP-0 · V-METRIC — verdict, ROUND 8

*Artifact frozen at `c7dc6195f`. Verified 2026-08-04 against `loreweave_chat` in `infra-postgres-1`.
Subject: the instrument, never the feature. No tracked file was modified; every query below is
read-only (temp views only, as `baseline-metrics.sql` itself uses). I did not read commit messages
or builder rationale — only the frozen artifacts, the SQL, the harness source, and the database.*

**The claim changed since round 7.** It is no longer a rate comparison. It is six invariants, each
falsified by one counter-example. My mandate is whether that replacement is sound, whether CP-0.6's
completed measurement is honest, whether the four retained rate classes reproduce, and whether the
startup reconciler corrupts measurement.

---

## 0 · Verdict

| | |
|---|---|
| **OVERALL** | 🔴 **FAIL** — and for a different reason than every prior round. The property claim is **the right move in kind**; it escapes the frozen-corpus trap that killed the rate claim and it is genuinely falsifiable at n=1. It fails **as instantiated**: of the four properties CP-0 closes on, **P3 is already satisfied**, **P4 is recorded by the run itself as believed satisfied**, and **P2's gated form is satisfied 118/118 with zero counter-examples**. Only **P1** is genuinely violated today — and its cited residual (*"237 → 4"*) does not reproduce under any denominator I can construct, while its companion sub-claim (*"same-pass overlap **is** 0 everywhere — that part held"*) is **false at 28 rows**. |
| **1 · property claim as replacement** | 🟡 **SOUND IN KIND, UNSOUND AS DELIVERED.** 3 of 6 escape my round-3 self-satisfaction objection (P1, P2-strong, P5). P3 is vacuous today, P4 is declared vacuous by the run, P2's *gated* form is vacuous, and **P6's cited violation is a different proposition from P6 as stated** (trap 2 — a guard proven red over the wrong subject). |
| **2 · CP-0.6 binding format** | 🟢 **THE MEASUREMENT IS SOUND AND THE CONCLUSION IS HONEST**, with one over-claim about the control's strength, one over-*precision* in its own self-criticism (the true bound is **weaker** than ≤63.2%), and one grading blind spot on the exact failure mode the run is named for. Not an over-claim in the damaging direction. |
| **3 · four classes as published observations** | 🟡 **THE STATUS IS HONEST; THE FREEZE IS NOT HELD.** `baseline-metrics.sql` re-runs and the four headline percentages are unchanged — but the **corpus fingerprint has already drifted** (`fe08c89e…` vs the frozen `9cdacf69…`), so by the file's own rule `baseline-metrics.frozen.txt` no longer reproduces. Class 3's status is honest **only because** the board carries my 49.9% beside the published 40.4%; that attachment is load-bearing. |
| **4 · the startup reconciler** | 🔴 **IT DOES NOT MOVE ONE PUBLISHED NUMBER — AND IT CORRUPTS THREE OTHER THINGS.** It cannot touch the four classes (proven by enumeration). It **breaks the freeze signal** (the fingerprint hashes `outcome`, which no class reads, so a *restart with zero traffic* invalidates the freeze). It **manufactures a dated discontinuity**: 223 user rows stamped `crashed`, spread back to 2026-04-03, 100% organic, 86 of them in sessions that demonstrably continued afterwards. And it **destroys the provenance P3 needs** — nothing records whether an outcome came from a terminal path or from the sweep. |

---

## 1 · Corpus pin — and the freeze is already broken

```
== PIN · corpus fingerprint (numbers below are valid ONLY for this fingerprint) ==
 messages |            newest             |            corpus_md5
----------+-------------------------------+----------------------------------
     5905 | 2026-08-04 09:52:54.470467+00 | fe08c89ece5e8f85ed0ff4df9b897698
```

`contracts/agent-runtime-baseline/baseline-metrics.frozen.txt` pins
`5862 · 2026-08-04 04:58:09.556834+00 · 9cdacf696d9b5ebb6932d3e8e8062d1c`.

**43 new messages, 26 new calls, 5 new failures — within five hours of the freeze.** The file's own
rule is unambiguous: *"a differing fingerprint means the numbers are not comparable and nothing may be
concluded from the difference."* I record it as the file instructs, and note that this is not a
builder failure — it is the honest consequence of freezing the output of a live database, which the
header already concedes. It is nonetheless the state of the artifact: **the frozen baseline does not
currently reproduce.**

---

## 2 · Ruling 1 — is the property claim a sound replacement for the rate claim?

The standard is the one I set in round 3 and which the run adopted verbatim: *a property the system
already holds gates nothing.* Each P must be one the **current** runtime demonstrably violates, with
a measured violation. I checked all six.

### 2.1 P1 — *every tool absent from a pass's advertised set registers `{tool, stage, reason, pass}`*

**Cited violation: "237 → 4. Residual: 4 named tools, deterministic."** The violation is real. **The
number is not.** I could not reproduce `4` under any denominator, and I tried three, from the SSOT
outward.

**(a) Against the SSOT — the frozen 315-tool catalog** (`tools-list.snapshot.json`,
`catalog_sha256 eec0470b5a5a4f8a181f9515d1d654908250b72ad519567449955b554711ab6e`, 315 tools
confirmed). This is P1 read literally: a tool in the catalog, not advertised at pass *p*, must carry
a withheld record at pass *p*.

```
== R8-8 · catalog control ==
 catalog_tools
---------------
           315

== R8-9 · P1 · per (message,pass): catalog - advertised - withheld = UNREGISTERED narrowings ==
 message_passes | unregistered_narrowings | passes_with_a_hole
----------------+-------------------------+--------------------
            251 |                   67567 |                249
```

**67,567 unregistered narrowings over 251 message-passes. 249 of 251 passes have a hole.** `R8-10`
returns ~290 distinct tool names, led by `glossary_propose_kinds` (249 passes),
`catalog_get_book`/`plan_*`/`registry_*`/`settings_*` (241 each).

**(b) Against the runtime's own universe** — tools this turn ever advertised *or* withheld at any
pass. This is the self-derived denominator, and trap 3 says it always reads better:

```
== R8-17 · P1 · SELF-DERIVED denominator: universe = tools this TURN ever advertised or withheld ==
 message_passes | unregistered | passes_with_hole
----------------+--------------+------------------
            251 |        12873 |              123
```

**12,873, over ~290 distinct tools** (`R8-18`). Still not 4.

**(c) The narrowest reading I can defend** — the mid-turn deletion the field exists to catch: a tool
advertised at an *earlier* pass of this turn, absent at this pass, with no withheld record at this
pass. This is the most charitable construction available:

```
== R8-26 · P1 · NARROWEST reading: advertised at an EARLIER pass, absent now, NO withheld record ==
 unregistered_mid_turn_deletions | distinct_tools | turns
---------------------------------+----------------+-------
                              80 |              7 |     5

== R8-27 · P1 · the same, by tool ==
        tool         | occurrences
---------------------+-------------
 book_list_chapters  |          26
 book_list_revisions |          20
 book_update_details |          15
 book_get            |          14
 book_steering_list  |           2
 tool_list           |           2
 book_list           |           1
```

**7 tools, 80 occurrences, 5 turns.** The closest I get to *"4 named tools, deterministic"* is
**seven**, and only by choosing the reading that flatters it most.

**And the sub-claim beside it is refuted outright.** The board states: *"Same-pass overlap **is** 0
everywhere — that part held."*

```
== R8-11 · P1 · same-pass OVERLAP (advertised AND withheld at the same pass) ==
 overlap_rows
--------------
           28
```

```
== R8-16 · P1 · the 28 same-pass OVERLAP rows, detailed ==
              message_id              | pass |            tool             |    stage
--------------------------------------+------+-----------------------------+--------------
 4ce53500-cd3c-40fd-8f5c-7136ecf7482a |    4 | book_steering_set           | token_budget
 4ce53500-cd3c-40fd-8f5c-7136ecf7482a |    4 | book_structure_edit         | token_budget
 4ce53500-cd3c-40fd-8f5c-7136ecf7482a |    4 | book_structure_part_archive | token_budget
 4ce53500-cd3c-40fd-8f5c-7136ecf7482a |    4 | book_structure_read         | token_budget
 4ce53500-cd3c-40fd-8f5c-7136ecf7482a |    4 | book_task_provide_input     | token_budget
 732760c4-d11f-4e84-bf7d-bd7cd1af394b |    2 | book_chapter_create         | token_budget
 82cda3d9-6f07-4cce-9ab9-454e9704b019 |    3 | glossary_deep_research      | token_budget
 …  (11 more at msg 82cda3d9, pass 3)
 8dad348e-5e5b-4d65-8fc1-92963ed42734 |    2 | glossary_deep_research      | token_budget
 …  (10 more at msg 8dad348e, pass 2)
                                                          [28 rows]
```

**28 rows across 4 messages, every one at `stage = token_budget`**: the same tool is recorded as
both *advertised at pass p* and *withheld at pass p*. Those two records cannot both be true. This is
not a residual — it is a **contradiction inside the field**, at the one stage that does the largest
narrowing, and the board asserts it does not exist.

Two supporting counts, for completeness:

```
== R8-12 · P1 · withheld records missing any of the four keys ==
 records | no_tool | no_stage | no_reason | no_pass
---------+---------+----------+-----------+---------
    4438 |       0 |        0 |         0 |     332

== R8-13 · P1 · turns that advertise but record NO withheld at all ==
 turns_with_advertised | of_which_no_withheld_column
-----------------------+-----------------------------
                    85 |                          38
```

`{tool, stage, reason}` is complete; `pass` is absent on **332 of 4,438** records (the historical
block, unchanged from rounds 6 and 7). And **38 of 85 advertising turns record no withholding at
all** — against a 315-tool catalog and observed pass-1 pools of 21–324 (`R8-19`), a turn that
advertises 33 tools and registers zero withholdings is a hole, not a policy.

**Ruling on P1: the property is genuinely violated — it is the one P that is not vacuous — but the
magnitude attached to it is unreproducible, and the "same-pass overlap is 0" claim beside it is
false.** P1 is a real gate. Its stated position on the board is not a measurement.

### 2.2 P2 — *a call's `source` is assigned structurally, never inferred*

**Cited violation: 110 of 201 carry `source_inferred`.** Real, and it has grown with the corpus:

```
== R8-6 · P2: tool_calls[].source distribution, and source_inferred marker ==
  source  | has_inferred_key | inferred_val |  n
----------+------------------+--------------+------
 <absent> | f                | -            | 7447
 tool     | f                | -            |  109
 meta     | t                | true         |   87
 breaker  | t                | true         |   31

== R8-7 · P2 denominator: calls that carry a source at all (post-CP-0 rows) ==
 calls_with_source | inferred |             first             |             last
-------------------+----------+-------------------------------+------------------------------
               227 |      118 | 2026-08-03 23:47:17.022868+00 | 2026-08-04 09:42:20.99062+00
```

**118 of 227 = 52.0% inferred** (the board's 110/201 = 54.7% at its own pin; same fact). Denominator
stated: **227**, being every recorded `tool_calls[]` element that carries a `source` key at all —
7,447 pre-CP-0 elements carry none and cannot be scored. **P2 as written on the board is genuinely
violated.**

**But that is not the property that will be gated.** The path-to-closure row weakens it to: *"Gated
so the residual stays countable: **an inferred row must mark itself**."* Under that form:

```
== R8-22 · P2 · post-CP-0 calls: marked-vs-unmarked inference ==
 source  |  n  | marked_inferred | unmarked
---------+-----+-----------------+----------
 tool    | 109 |               0 |      109
 meta    |  87 |              87 |        0
 breaker |  31 |              31 |        0
```

**118 inferred, 118 marked, 0 unmarked. The gated form is already satisfied, 100%, at n=227.** This
is my round-3 objection recurring verbatim: *C works only if the property is one CP-0 has not already
certified.* The strong P2 is a real gate; the weak P2 the closure plan actually arms is
self-satisfying.

**And the weak form is not falsifiable from the record.** `source_inferred` is written by the same
code that performs the inference. A call inferred by a site that believes itself structural leaves
**no trace at all** — it appears in the 109 unmarked `tool` rows, indistinguishable from a genuinely
structural one. The counter-example that would falsify weak-P2 is, by construction, invisible to the
instrument. Only source review can decide it, and §0.12 says a test may reject but never admit.

### 2.3 P3 — *every terminal path writes an outcome* — 🔴 **ALREADY SATISFIED. VACUOUS.**

The board reads *"Kill path still **FAILS**: a killed process cannot write its own outcome."* On the
frozen artifact, on live rows, in the CP-0 era, that is no longer true:

```
== R8-20 · P3 · POST-CP-0 assistant turns (>= 2026-08-03 23:47) lacking an outcome ==
 assistant_turns | no_outcome | no_outcome_aged
-----------------+------------+-----------------
              86 |          0 |               0

== R8-21 · P3 · POST-CP-0 user turns lacking an outcome AND lacking a later assistant row ==
 orphan_user_turns
-------------------
                 0

== R8-3 · assistant rows still non-terminal (no outcome) by finish_reason ==
       fr       |  n   | no_outcome |   first    |    last
----------------+------+------------+------------+------------
 <NULL>         | 2404 |       2404 | 2026-04-03 | 2026-07-18
 stop           |  272 |        205 | 2026-07-19 | 2026-08-04
 awaiting_input |   38 |         31 | 2026-07-19 | 2026-08-04
 interrupted    |   20 |         11 | 2026-07-21 | 2026-08-04
 streaming      |    3 |          0 | 2026-08-04 | 2026-08-04
 error          |    2 |          2 | 2026-07-21 | 2026-07-25
```

**Zero counter-examples in the CP-0 era.** Every `streaming` row is stamped. The residual
un-outcomed rows are all pre-CP-0 history, which the property was never about. **A property with
zero available counter-examples on the corpus it will be gated against is not a gate.**

Two further measurement objections, which matter more than the vacuity:

1. **Satisfaction is produced by a mechanism that does not satisfy the stated property.** P3 says
   *every **terminal path** writes an outcome*. `reconcile_crashed_turns` is not a terminal path — it
   is a startup sweep that writes an outcome the dead turn never recorded. The property is true of
   the *rows*; it remains false of the *paths*, and the instrument cannot tell the two apart (§4).
2. **Falsification depends on when you look, not on how the runtime behaves.** The sweep runs only at
   startup with a 5-minute floor. Between a kill and the next restart, a counter-example exists;
   after the restart it does not. A property whose falsifier the system itself erases on a schedule
   nobody records is not falsifiable at n=1 in the sense the claim requires.

### 2.4 P4 — *no CP-0 column is bound to a constant at any INSERT*

Source-side; **not measurable from the database, and I decline to rule on V-CODE's subject.** I record
only what the board itself says: *"🟢 **believed satisfied** under the verifier's OWN narrowed
gate … the last site is reachable from **exactly one** condition."* **A property recorded as
satisfied at the freeze gates nothing**, by the standard the run adopted from me. If V-CODE confirms
it, P4 joins P3 as a vacuous member of the four CP-0 closes on. Flagged, not ruled.

### 2.5 P5 — *a step's `emits` binds to the next step's `accepts` without the model retyping it*

**Cited violation: the 0/101 tool sending `placeholder_id_1` ×60.** Real and measured:

```
== R8-14 · P5 · placeholder identifiers in recorded args ==
 calls_with_placeholder_id | turns |   first    |    last
---------------------------+-------+------------+------------
                        89 |    15 | 2026-07-22 | 2026-07-26

== R8-15 · P5 · the placeholder error strings ==
             tool             | n
------------------------------+----
 glossary_propose_entity_edit | 93
 glossary_propose_entities    |  6
 book_chapter_save_draft      |  4
 glossary_adopt_standards     |  2
 book_chapter_create          |  1
```

**89 recorded calls carrying a placeholder identifier across 15 turns**; 93 rows on
`glossary_propose_entity_edit` match `%placeholder%`. Genuinely violated, genuinely measured. The
one caveat: it is **historical** (2026-07-22 → 07-26, nothing since), so a counter-example is not
currently being produced by live traffic. **CP-3's, not CP-0's.**

### 2.6 P6 — *a declaration named by a live plan step is advertised while that step is current*

**The cited violation is a different proposition from the property.** The citation — *"12 rails point
at 30 dead tools behind a gate that fails open"* — traces to `ARCHITECTURE.md:770 / 844 / 871` and
`DECLARATION-BACKLOG.md:100`, where it is the evidence for **C-11 / M5, *resolvable references***: a
reference to a non-admitted declaration must be unresolvable. P6 as stated on the board is about
**advertisement timing** — is the named declaration *advertised while its step is current*. Those are
different failures: a rail can point at a dead tool with no plan step current at all, and a live step
can name a perfectly resolvable declaration that is nevertheless withheld at that pass.

**This is trap 2 from my brief — a guard proven red over a neighbouring subject.** P6 may well be
violated; the evidence offered does not show it. **CP-2's, not CP-0's**, so it does not block this
checkpoint — but it must not be recorded as "measured".

### 2.7 Ruling 1, stated

| | property genuinely violated **today**, on evidence I reproduced? | verdict |
|---|---|---|
| **P1** | ✅ yes — but the cited residual (4) does not reproduce (I get 67,567 / 12,873 / 80-over-7), and *"same-pass overlap is 0"* is **false at 28 rows** | 🟡 **real gate, unreliable number** |
| **P2 (board form)** | ✅ yes — 118/227 inferred | 🟢 real gate |
| **P2 (closure form)** | ❌ **already satisfied 118/118**, and its falsifier is unobservable by construction | 🔴 **vacuous** |
| **P3** | ❌ **already satisfied** — 0 counter-examples in 86 CP-0-era turns; satisfied by a sweep, not by a terminal path | 🔴 **vacuous** |
| **P4** | ❌ recorded by the run as *believed satisfied* | 🔴 **vacuous unless V-CODE overturns** |
| **P5** | ✅ yes — 89 calls / 15 turns, though historical | 🟢 real gate (CP-3's) |
| **P6** | ⚠️ evidence is for a **different property** (C-11 resolvability) | 🔴 **trap 2** |

**Is the property claim sound as a replacement for the rate claim? In kind, yes — and I say so
without qualification.** It is the only one of the three options that escapes a frozen control group,
it needs no sample size, and it measures the mechanism rather than its shadow. Rate class 1 *is* P5
failing and rate class 2 *is* P2 failing; that mapping is correct.

**As delivered, no.** CP-0 closes on P1–P4. **P3 is satisfied, P4 is declared satisfied, and the P2
that will actually be armed is satisfied.** That leaves **one** live gate out of four, and it is the
one whose published magnitude I could not reproduce under three denominators. The replacement has
inherited the defect it was designed to avoid, in three of the four places where it counts.

---

## 3 · Ruling 2 — CP-0.6, the binding-format measurement

Verified against `eval/arms/binding_format.py` and
`eval/arms/results/binding-format-20260804T035320Z.json` (5 arms × 3 trials = 15 calls,
`gemma-4-26b-a4b-it-uncensored-apex-quality`, T=0.2, `max_tokens=600`).

### 3.1 What is sound — and it is most of it

- **Graded in code, on the argument actually sent.** `grade()` reads
  `tool_calls[].function.arguments.chapter_id` and compares to a constant. No LLM judge; no
  `ok=true` anywhere in the chain; `text` is captured but not scored. This is the correct answer to
  the repository's own *"a check whose seed and control agree is theatre"*.
- **The decoy control is real and it fires.** `DECOY_ID = 0198f3c1-77aa-7b41-9c2e-000000000000`
  shares its first three segments with `CHAPTER_ID` and is placed **after** it in the prompt.
  `sent_decoy` is graded separately from `exact`. A nearest-token copier fails this arm. **This is
  the single best thing in the measurement** — without it, five 3/3s would be uninterpretable, and
  the FINDING says exactly that.
- **The bound arithmetic is correct.** 1 − 0.05^(1/3) = **63.16%** → *"≤63.2%"*. The harness writes
  the bound into its own output file (`_bound`) rather than into prose, which is the right place for
  it.
- **`no_call = 0` in all 15 trials**, so `max_tokens=600` did not truncate; the ceiling is not an
  artifact of the budget.

### 3.2 The stated conclusion, ruled clause by clause

| clause | ruling |
|---|---|
| *"it discriminates NOTHING"* | 🟢 **HONEST.** 5/5 arms at ceiling. Zero variance between arms. Correct, and correctly refuses to rank. |
| *"3/3 bounds failure only at ≤63.2%"* | 🟡 **HONEST IN DIRECTION, OVER-PRECISE IN MAGNITUDE — and the error runs against them.** See §3.3. |
| *"the task is too easy to reach the regime CP-3 cares about"* | 🟢 **HONEST**, and verifiable from the harness: one binding, one step, one tool, a prompt of a few hundred tokens, no compression. It is a *design inference*, not a measured one — no harder arm was run — and should be labelled as such, but it is not an over-claim. |
| *"the model is genuinely resolving the binding, not copying the nearest identifier"* | 🔴 **OVER-CLAIM, in the flattering direction.** See §3.4. |

### 3.3 The bound is *weaker* than ≤63.2%, because the trials are not independent

**All 15 trials — five arms, three each — are byte-identical.** Same `called`, same
`chapter_id_sent`, `exact: true`, and `text: ""` in every single one. At T=0.2 on a fixed prompt this
is a near-deterministic decode, and the harness passes no seed.

`1 − 0.05^(1/n)` assumes **n independent Bernoulli trials**. With intra-arm correlation at or near 1,
the effective n is ~1, whose 95% bound is **≤95%**, not ≤63.2%. So the FINDING's most self-critical
sentence is *still* stating a tighter bound than the data supports.

The consequence is larger than the number: **the run observed zero variance anywhere**, so no arm
could have been distinguished from any other **at any n** on this task. That is a stronger version of
the FINDING's own conclusion, and it should replace it.

### 3.4 The control rules out less than it is credited with

The decoy is labelled **`cover_asset_id`**, and the correct value is labelled **`chapter_id`** — the
same string as the tool's required parameter. A model doing pure **parameter-name matching** (find
the key spelled `chapter_id`, copy its value) passes the decoy arm without resolving any binding.
What the control demonstrates is *"not nearest-token copying."* What the FINDING claims is *"genuinely
resolving the binding."* The second does not follow from the first.

The adversarial version costs nothing: label the decoy `chapter_id` too (a superseded step-1 attempt,
say) so name-matching and binding-resolution give different answers. As built, the arm cannot separate
them.

*(Partial credit where it is due: the `prose` arm carries no `chapter_id:` label at all — the id is
buried in narration — and still scored 3/3. So the model does more than key-matching in at least one
arm. That is a real result, and it belongs in the FINDING more than the decoy sentence does.)*

### 3.5 A blind spot on the run's own headline failure mode

```python
"invented": bool(sent) and sent not in (CHAPTER_ID, DECOY_ID)
            and not re.fullmatch(r"[0-9a-f-]{36}", str(sent) or ""),
```

A **fabricated but UUID-shaped** identifier is graded `exact=False`, `sent_decoy=False`,
`invented=False`, `no_call=False` — **it lands in no bucket, and the four reported columns do not sum
to n.** That is precisely the production failure the run cites from `stream_service.py:1634`: *"a weak
model invents a VALID-but-WRONG book_id."* The instrument that exists to study identifier
hallucination cannot see identifier hallucination when it is well-formed.

It did not bite here — every trial was exact, so the hole is unexercised. It is a defect of the
instrument, not of the result.

### 3.6 Ruling 2, stated

**🟢 The measurement is sound and its conclusion is honest — it is not an over-claim in the
damaging direction.** It reports a null result as a null result, refuses to rank on it, states its
own bound, and tells CP-3 not to spend the checkpoint on this evidence. That is the correct output.

**Three corrections, none of which reverse it:**
1. The honest bound is **weaker** than ≤63.2% — the trials are not independent (zero observed
   variance across 15 identical outputs), so the effective n is ~1 and the bound ~≤95%.
2. *"genuinely resolving the binding"* over-reads the control; what is shown is *"not nearest-token
   copying."*
3. `invented` cannot detect a well-formed fabricated UUID — the failure mode the run is named for.

---

## 4 · Ruling 3 — the four rate classes as published observations

### 4.1 It reproduces mechanically. Raw output, in full.

```
== 0 · POPULATION ==
 calls_raw | calls_organic | failures_raw | failures_organic
-----------+---------------+--------------+------------------
      7674 |          6454 |         4077 |             2897

== 1 · CARRY-FORWARD (strict: success STRICTLY EARLIER) ==
        scope        | failures | carry_strict | pct_strict | carry_loose | pct_loose
---------------------+----------+--------------+------------+-------------+-----------
 organic             |     2897 |         1120 |       38.7 |        1306 |      45.1
 organic_real_errors |     1674 |          101 |        6.0 |         263 |      15.7
 raw                 |     4077 |         2300 |       56.4 |        2486 |      61.0

== 2 · NOT-A-REAL-DISPATCH, as a share of failures (LOWER BOUND pre-CP-0) ==
  scope   | failures | not_real_dispatch |  pct  | of_which_meta
----------+----------+-------------------+-------+---------------
 raw-only |     1180 |              1180 | 100.0 |          1180
 organic  |     2897 |              1200 |  41.4 |           157

== 3 · IDENTIFIER RESOLUTION, as a share of REAL errors ==
  scope  | real_errors | id_errors | pct
---------+-------------+-----------+------
 organic |        1674 |       676 | 40.4

== 4 · TERMINAL OUTCOME, through the CP-0.4 shim, WINDOWED on column age ==
  scope  | assistant_turns | completed | awaiting_input | failed | crashed | interrupted_recorded | unrecorded | pct_unrecorded
---------+-----------------+-----------+----------------+--------+---------+----------------------+------------+----------------
 raw     |               4 |         4 |              0 |      0 |       0 |                    0 |          0 |            0.0
 organic |             331 |       268 |             38 |      2 |       3 |                   20 |          0 |            0.0

== 5 · WEEKLY TRAFFIC (the ceiling on any bound) ==
    week    | calls | failures
------------+-------+----------
 2026-08-03 |   232 |       70
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

### 4.2 The figures, with denominators, against the frozen file

| class | today | denominator | frozen.txt | moved? |
|---|---|---|---|---|
| 1 · carry-forward over real errors | **6.0%** | **101 / 1,674** | 6.0% (101/1,673) | pct held, **denominator +1** |
| 2 · not-a-real-dispatch (organic) | **41.4%** | **1,200 / 2,897** | 41.4% (1,198/2,892) | pct held, **both moved** |
| 3 · identifier resolution (organic) | **40.4%** | **676 / 1,674** | 40.4% (676/1,673) | pct held, **denominator +1** |
| 4 · no recorded outcome (windowed ≥ 2026-07-19) | **0.0%** | **0 / 331** | 0.0% (0/312) | pct held, **+19 turns** |
| — corpus fingerprint | `fe08c89ece5e8f85ed0ff4df9b897698` | 5,905 msgs | `9cdacf696d…` / 5,862 | 🔴 **DIFFERENT** |

**The percentages are stable; the pin is not.** By the file's own rule the two runs are not
comparable, and I report the stability as an observation rather than as a reproduction.

### 4.3 Is "published observation" an honest status for numbers I previously ruled unsound?

**Yes — for three of the four, and conditionally for the fourth.**

- **Class 1 (6.0%)** — honest. The predicate is defended, the strict/loose split is published beside
  it, and the correction that made it *harder* to prove was applied against interest. No objection.
- **Class 4 (0.0%)** — honest, and correctly labelled as **coverage**, not a quality win. It is
  unimprovable by construction and the board says so. See §5 for the one way it could become
  dishonest.
- **Class 2 (41.4%)** — honest **only with its ⛔ label attached**. It is derived from error-prose
  signatures on the frozen side and structurally on the new side; those are different instruments.
  As a within-arm diagnostic it is fine. The label must not be dropped.
- **Class 3 (40.4%)** — **honest only because the board carries my adjudicated 49.9% beside it.**
  RUNSTATE line 97 reads *"40.4% (676/1,673) — verifier's optimum 49.9%"*, and the SQL comment states
  the predicate is unresolved and left open. **That attachment is load-bearing.** My round-7 ruling
  stands unchanged: **40.4% under-counts by 158 rows / 9.5pp and over-counts by nothing**; the figure
  this corpus supports is **49.9% (834/1,673)**, adjudicated across all 200 distinct error strings.
  Publishing 40.4% alone, without the 49.9% and without the ⛔ not-scoreable-across-arms label, would
  be publishing a number the file's own board records as unresolved — the `65.7%` failure mode
  exactly.

**The general ruling, and it is the part that is not obvious:** demoting a gate to a *published
observation* removes the **arm-comparison** requirement. It does **not** remove the **reproducibility**
requirement. An observation whose fingerprint no longer exists is a rumour with a decimal point — the
precise thing `baseline-metrics.sql` was written to stop. `frozen.txt` does not currently reproduce
(§1), and §5 shows the fingerprint can now be invalidated by a service restart with no traffic at
all. **The status is honest; the pin that makes it meaningful is not held.**

---

## 5 · Ruling 4 — the startup reconciler's effect on measurement

`instrument.reconcile_crashed_turns` (`services/chat-service/app/services/instrument.py:490-546`),
called from `main.py:94-95` at startup, stamps `outcome='crashed'` on two shapes older than 5
minutes: assistant rows still at `finish_reason='streaming'`, and user rows with no later assistant
row. This is a **measurement** question only; correctness is V-CODE's and V-LIVE's.

### 5.1 It cannot move any of the four published numbers — proven by enumeration, not inspection

`outcome` occurs in `baseline-metrics.sql` exactly **twice**:

```
$ grep -n "outcome" contracts/agent-runtime-baseline/baseline-metrics.sql
36:         (SELECT string_agg(message_id::text || coalesce(finish_reason,'') || coalesce(outcome,'')
258:              -- 'interrupted' is a RECORDED outcome, not an absent one. …
```

Line 36 is **the fingerprint**. Line 258 is **a comment**. Class 4 maps from `finish_reason` and
`is_error` only, and filters `role='assistant'`. Classes 1–3 read `tool_calls`. **No class reads the
`outcome` column.**

```
== R8-24 · rows created BEFORE the freeze carrying a crashed outcome ==
   role    | count
-----------+-------
 assistant |     3
 user      |   223
```

The 223 are **user** rows, which class 4 never counts. The 3 assistant rows are
`finish_reason='streaming'`, which the shim maps to `crashed` **independently of the column** — and
`frozen.txt` already printed `crashed = 3`. **Zero baseline figures move.** ✅

### 5.2 It breaks the freeze signal — a restart with no traffic invalidates the fingerprint

The fingerprint md5 **includes `coalesce(outcome,'')`**. The reconciler runs at **every startup** and
writes that column on historical rows.

```
== R8-23 · FINGERPRINT sensitivity: hash WITH vs WITHOUT the outcome term, over the PRE-FREEZE row set ==
           with_outcome           |         without_outcome          | prefreeze_rows_carrying_outcome
----------------------------------+----------------------------------+---------------------------------
 b0f725fe49e3c20a26c24a502f7e67c7 | 015c7789fee48518efe4035c2dd5751d |                             290
```

The two hashes differ, and **290 rows created before the freeze timestamp now carry an outcome
value**. So: **`docker restart infra-chat-service-1`, zero new messages, and the corpus fingerprint
changes** — declaring the baseline non-comparable on the strength of a column no class reads.

This is round 3's *"the fingerprint was theatre"* defect **inverted**. It was under-sensitive then
(it hashed only the primary-key set and missed a mutation of `finish_reason`); it is **over-sensitive
now**. Both failures have the same consequence: **the alarm stops carrying information.** An alarm
that fires on restarts trains its reader to dismiss it, which is exactly how the next real mutation
gets through.

### 5.3 It manufactures a dated discontinuity in the outcome distribution

```
== R8-1 · outcome distribution by role ==
   role    |      outcome      |  n   |   first    |    last
-----------+-------------------+------+------------+------------
 assistant | <NULL>            | 2653 | 2026-04-03 | 2026-08-03
 assistant | completed         |   67 | 2026-08-03 | 2026-08-04
 assistant | abandoned_by_user |    9 | 2026-08-04 | 2026-08-04
 assistant | awaiting_input    |    7 | 2026-08-04 | 2026-08-04
 assistant | crashed           |    3 | 2026-08-04 | 2026-08-04
 user      | <NULL>            | 2942 | 2026-04-03 | 2026-08-04
 user      | crashed           |  223 | 2026-04-03 | 2026-08-04
 user      | abandoned_by_user |    1 | 2026-08-04 | 2026-08-04
```

`R8-2` spreads those 223 across **27 distinct days from 2026-04-03 to 2026-08-04** (peaks: 07-12 ×36,
07-15 ×35, 07-09 ×32). Their `created_at` places them squarely in the legacy arm's history. **The
value was written in August, by a sweep that did not exist on those dates.**

**Any before/after or arm-vs-arm comparison of the outcome distribution bucketed by `created_at` is
invalid.** The legacy arm now reads 223 crashes it never recorded, and the number will keep growing
at every restart as more history qualifies. A "crash rate improved" reading of any such comparison
would be an artifact of the sweep's ship date.

**And `crashed` is asserted, not observed.** The predicate for a user row is *no later assistant row*
— which is equally the shape of an abandoned message, a branch that was never continued, a send that
failed client-side, and a user who simply closed the tab.

```
== R8-29 · do the 223 crashed user rows sit in sessions that later continued? ==
              shape               |  n
----------------------------------+-----
 row is last in session           | 137
 session continued after this row |  86
```

**86 of 223 sit in sessions that demonstrably continued after that row.** The session did not die.
Calling those rows `crashed` records a fact about the process that the data does not support — the
run's own most-repeated defect (*"asserting something I had not checked"*), relocated from prose into
a column.

Two mitigating facts, recorded in fairness:

```
== R8-25 · the 223 crashed user rows by session title (contamination check) ==
   pop   |  n
---------+-----
 organic | 223

== R8-28 · user rows stamped crashed that DO have a LATER assistant row (false crash) ==
 falsely_crashed
-----------------
               0
```

None are harness contamination, and **no row is currently mis-stamped against the reconciler's own
predicate**. But the stamp is **write-once** (`WHERE outcome IS NULL`) over a predicate that is **not
monotone** — a later assistant row can appear at any time, and the `crashed` stamp will never be
withdrawn. Today the count is 0; nothing detects it if it becomes non-zero.

### 5.4 It destroys the provenance that P3 needs

```
== R8-30 · is there any column recording WHO wrote outcome? ==
 column_name
-------------
 outcome
```

**One column. No `outcome_source`, no `outcome_written_at`, no flag.** So from the data it is
impossible to distinguish:

- a turn whose **terminal path** wrote `crashed` (P3 satisfied), from
- a turn whose outcome was **guessed by a startup sweep three days later** (P3 violated, and
  compensated).

`R8-32` shows the CP-0-era rows where both signals exist and agree — `stop→completed` ×67,
`interrupted→abandoned_by_user` ×9, `awaiting_input` ×7, `streaming→crashed` ×3 — but agreement is
not provenance, and the 3 `crashed` rows are exactly the ones the sweep writes.

**P3 is the property CP-0 closes on, and the instrument cannot answer it.** That is the sharpest
measurement finding in this round: the reconciler makes P3's *number* look perfect (§2.3: 0 of 86)
while removing the ability to check the *property*. It is the standing question answered in the
affirmative — **this number would look good even if the thing being measured were broken**, because
the sweep repairs the record rather than the path.

### 5.5 Ruling 4, stated

| question | ruling |
|---|---|
| does it corrupt any baseline figure? | 🟢 **NO** — proven by enumerating the column's consumers; `outcome` appears in the derivation only inside the fingerprint |
| does it create a discontinuity in the outcome distribution? | 🔴 **YES** — 223 `crashed` stamps dated 2026-04-03 → 2026-08-04, written in August, 86 of them in sessions that continued |
| does it make a before/after comparison invalid? | 🔴 **YES for anything bucketed on `created_at`.** A comparison windowed on the CP-0 era (≥ 2026-08-03 23:47) survives — but cannot then distinguish sweep from terminal path |
| any other measurement effect? | 🔴 **the freeze signal**: the fingerprint hashes `outcome`, so a restart with zero traffic invalidates the baseline pin |

---

## 6 · My stated falsifier

*What I looked for that would have made each ruling go the other way.*

1. **Ruling 1 — the property claim.** I set out to confirm that option C had been implemented against
   my own round-3 objection, and **it would have passed** had P1–P4 each carried a live
   counter-example. I looked for one per property and found: P1 yes (many), P2-strong yes,
   P2-as-gated **none in 227**, P3 **none in 86**, P4 declared satisfied by the run itself.
   **Overturned by:** a single CP-0-era assistant turn with a NULL outcome (`R8-20`), or a single
   `tool_calls[]` element that is inferred but unmarked (`R8-22`). Both are `0`. If either becomes
   non-zero, P3 / weak-P2 stop being vacuous and I withdraw that half of the ruling.
2. **P1's number.** I tried three denominators in order of decreasing strictness specifically to find
   the one that yields `4`, because reproducing the builder's figure would have made this GREEN. The
   most charitable reading available gives **7 tools / 80 occurrences**. **Overturned by:** a stated
   denominator, in the artifact, under which `4` is computable. There is none, and the
   `same-pass overlap = 0` claim is refuted at 28 rows regardless of denominator.
3. **Ruling 2 — CP-0.6.** I set out to find an over-claim in the flattering direction, because a
   null result quietly dressed as a win is the classic failure here. **I did not find one** — the
   FINDING under-claims on its headline and refuses to rank. What I found instead was an over-claim
   about the *control* and an over-*precision* in its own self-criticism that runs **against** the
   builder. **Overturned by:** any arm below 3/3 (there is none), or an `invented` count that the
   grader's UUID-shape escape had suppressed (all 15 were exact, so the hole is unexercised).
4. **Ruling 3 — reproduction.** I ran `baseline-metrics.sql` myself against the live database rather
   than reading `frozen.txt`. **A matching fingerprint would have made this a clean reproduction.**
   It differs (`fe08c89e…` vs `9cdacf69…`, 5,905 vs 5,862 messages), so I report stability of the
   percentages and non-reproduction of the pin, which are different findings.
5. **Ruling 4 — the reconciler.** I set out to prove it **corrupts a published number**, which is the
   more damaging answer, and I ruled **against my own preferred finding**: a single occurrence of
   `outcome` outside the fingerprint in `baseline-metrics.sql` would have done it, and there is none.
   **Overturned by:** adding any class that reads `outcome`, which would make every one of the 223
   retroactive stamps a live contaminant on the instant. **Re-confirmed by:** `R8-30` — one column,
   no provenance, so P3 is undecidable from the record.

---

*Authority exercised. I do **not** rule any of the four published figures unsound in this round — my
round-7 ruling on class 3 stands unchanged (40.4% under-counts by 158 rows; the corpus supports
49.9%) and the board carries it correctly. I rule that **P3 and the gated form of P2 are vacuous**,
that **P4 is vacuous unless V-CODE overturns the run's own "believed satisfied"**, that **P6's
citation proves a different property than P6 states**, and that **P1's cited residual of 4 does not
reproduce under any denominator while its companion "same-pass overlap is 0" is false at 28 rows.***

*Any PASS resting on "CP-0 closes on P1–P4" is therefore void as long as three of those four have no
available counter-example. The property claim is the right instrument; three of its six dials are
currently painted on.*

*Recorded in fairness, and it is not a formality: the move from a rate to a property is the correct
response to a frozen control group that cannot supply n, and CP-0.6 is the most honestly reported
null result this checkpoint has produced — it refuses to rank on evidence that cannot rank, states
its own bound rather than hiding it, and its single error of precision runs against the builder's
interest. The reconciler is likewise the right mechanism for a process that cannot record its own
death. What it costs is provenance, and provenance is the whole of P3.*
