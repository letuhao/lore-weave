# CP-0 · V-LIVE — round 8 verdict

**Artifact:** `c7dc6195f` — verified by content hash to be what the container ran, start **and** end.
Note: the branch did **not** stay frozen (two commits landed mid-run, one of them in `instrument.py`);
the container did. See §8, "The artifact did not stay frozen — but the container did".
**Driven:** the real UI (Playwright-driven Chrome against `http://localhost:5174`), the Studio's
embedded co-author chat panel. Model: Gemma-4 26B-A4B QAT (200K).
**Throwaway book:** `VLIVE-R8 Throwaway (CP-0 verification)` — `019fcc53-c23d-794e-9ff9-6b59c9cf6f80`
**Session:** `019fcc55-683c-7c0f-8450-3b51e2b7c193`
**DB:** `loreweave_chat` inside `infra-postgres-1`, queried directly throughout.

---

## Overall verdict: **FAIL**

| item | ruling |
|---|---|
| **P1** — every narrowing registers | **FAIL** — residual still **4 of 315**, the same four, unchanged from round 7 |
| **P3** — the kill path | **PASS on (a) and (c)**; **FAIL on (b)**, the dangerous case |
| Run A · clean | **PASS** |
| Run B · withheld | **PASS** |
| Run C · cancelled | **PASS** |
| Run D · killed | **PASS** (first time in eight rounds) |
| The defect CP-0 was built for (offered set changes between passes) | **PASS** — both states recorded |
| `awaiting_input` rows that can never receive input | **5 of 8 exist** — reported below |

The checkpoint does not close. P1 is unmoved, and P3's fix introduces a way to write a **false**
`crashed` onto a turn that succeeded — which I reproduced against a live turn and which was never
corrected.

---

## 0. PRECONDITION — the container was stale for the **EIGHTH** round running

Per the standing instruction I hashed the repo tree against the container **before driving anything**.
Docker reported `Up 29 minutes (healthy)` — the same reassuring string that lied in round 7.

Naive hashing shows all 107 files differing (the checkout is CRLF, the image LF), so line endings were
normalised before comparison:

```
$ cd services/chat-service && for f in $(find app -name '*.py'|sort); do
    printf "%s %s\n" "$(tr -d '\r' < $f | sha256sum | cut -d' ' -f1)" "$f"; done
$ docker exec infra-chat-service-1 sh -c "cd /app && ...same..."

PRE-REBUILD diff — 5 of 107 files differ:
  app/main.py                        69a183981c…  vs  9ca0aff755…
  app/routers/internal.py            b2dd582930…  vs  57332833c0…
  app/services/instrument.py         5b178c1486…  vs  0647c38d7b…
  app/services/stream_service.py     8b8a5f631d…  vs  87b7a9bca0…
  app/services/voice_stream_service.py 0df6bdc3e5… vs  85c435548f…
```

**Every one of the five is a file carrying a round-8 fix.** `instrument.py` holds the reconciler,
`stream_service.py` holds the two new narrowing stages, `main.py` holds the startup call. Had I
trusted `(healthy)`, I would have re-measured round 7's artifact and reported round 7's result.

```
$ docker compose -f infra/docker-compose.yml build chat-service      → Built
$ docker compose -f infra/docker-compose.yml up -d --force-recreate --no-deps chat-service
POST-REBUILD: all 107 files IDENTICAL to repo @ c7dc6195f  ("TREES IDENTICAL")
```

Every result below was produced by the frozen artifact.

### The universe is trustworthy

Frozen snapshot vs the **live** federated catalogue (`POST /mcp` → `tools/list` on `ai-gateway`,
`X-Internal-Token: dev_internal_token`, the real user id):

```
frozen 315   live 315
frozen-live: []      live-frozen: []
```

Zero drift. Nothing in the neither-bucket can be dismissed as "a tool that no longer exists".

---

## 1. P1 — **STILL FALSIFIED**, residual 4 of 315, unchanged

### The number

Accounting redone **exactly** as in rounds 6 and 7: universe = the 315 names in
`contracts/agent-runtime-baseline/tools-list.snapshot.json`; for a real turn, count how many are in
**neither** the advertised nor the withheld set.

| | round 6 | round 7 | **round 8** |
|---|---|---|---|
| run A turn-level NEITHER | 237 | 4 | **4** |
| run B turn-level NEITHER | 206 | 4 | **4** |

```
=== RUN A8 (seq 2) ===
passes=4 advertised_union=46 withheld_records=274 withheld_tools=274
advertised per pass: {1: 46, 2: 46, 3: 46, 4: 46}
withheld records per pass: {1: 274}  total 274
stages: {'domain_not_selected': 179, 'hot_seed': 95}
malformed records (missing tool/stage/reason/pass): 0
withheld JSON bytes: 43817

  TURN-LEVEL NEITHER = 4  (deprecated=0, non-deprecated=4)
  ['glossary_book_sync_apply', 'glossary_plan', 'glossary_propose_batch', 'glossary_propose_kinds']
  of those, recorded as domain_not_selected: 0

arithmetic: 315 - 179 domain_not_selected = 136 surviving
            adv-in-universe 37 + other-stage withheld tools 95 = 132
            136 - 132 = 4

=== RUN B8 (seq 4) ===
passes=8 advertised_union=57 withheld_records=287 withheld_tools=268
advertised per pass: {1: 57, 2: 56, 3: 55, 4: 54, 5: 53, 6: 53, 7: 52, 8: 52}
withheld records per pass: {1: 263, 2: 1, 3: 2, 4: 3, 5: 4, 6: 4, 7: 5, 8: 5}  total 287
stages: {'domain_not_selected': 162, 'hot_seed': 101, 'rail_gate': 24}
malformed records: 0
withheld JSON bytes: 44638

  TURN-LEVEL NEITHER = 4  (deprecated=0, non-deprecated=4)
  ['glossary_book_sync_apply', 'glossary_plan', 'glossary_propose_batch', 'glossary_propose_kinds']
```

**The same four tools, in both runs, byte-for-byte the same counts as round 7.** Deterministic, not
query-dependent, in a domain the record's own reason string says *was* selected
(`"domain not in this turn's hot set (book, composition, glossary, knowledge, story)"` — glossary is
in that list).

### The two new stages produced ZERO records

```
run A stages: domain_not_selected 179, hot_seed 95
run B stages: domain_not_selected 162, hot_seed 101, rail_gate 24
catalog_miss:   0 records in either run
permission_tier: 0 records in either run
```

They exist in the deployed artifact — I confirmed the strings are in the running container, not just
the repo:

```
$ docker exec infra-chat-service-1 grep -rn "catalog_miss\|permission_tier" /app/app/
/app/app/services/stream_service.py:1402:   name, stage="catalog_miss",
/app/app/services/stream_service.py:1414:   name, stage="permission_tier",
```

They simply never fire for these tools, because they sit **downstream of the actual drop point**.

### Where the four actually go — located in the running artifact

The `catalog_miss` narrowing is inside `for name in active_tool_names:` and triggers when
`catalog_index.get(name) is None`. But all four tools **are** in the live catalogue (verified: `live -
frozen = []`), so the catalog index has them and that branch is unreachable for them. The drop is
upstream of `active_tool_names` entirely:

```
$ docker exec infra-chat-service-1 sed -n '440,450p' /app/app/services/tool_discovery.py
INTENT_GATED_SETUP_TOOLS: frozenset[str] = frozenset({
    "glossary_adopt_standards",   # adopt genre/kind STANDARDS (the confirmed over-reach)
    "glossary_propose_kinds",     # batch-propose MANY kinds at once (build an ontology)
    "glossary_plan",              # planner: propose a WHOLE ontology behind one card
    "glossary_propose_batch",     # mixed batch ontology ops
    "glossary_book_sync_apply",   # bulk-reconcile adopted standards
})
```

`filter_intent_gated_setup_tools` removes these **from the turn catalog itself**, at catalog assembly
— before domain selection, before hot-seed, before the advertise loop, and therefore before every
stage the instrument knows about. It is a real, named, deliberate narrowing that registers nothing.

The set closes to the residual exactly. The fifth member is separately accounted:

```
                                   RUN A8              RUN B8
glossary_adopt_standards    advertised=True       advertised=True        (in a bucket — fine)
glossary_propose_kinds      advertised=False  NO RECORD   advertised=False  NO RECORD
glossary_plan               advertised=False  NO RECORD   advertised=False  NO RECORD
glossary_propose_batch      advertised=False  NO RECORD   advertised=False  NO RECORD
glossary_book_sync_apply    advertised=False  NO RECORD   advertised=False  NO RECORD
```

5 gated − 1 advertised = **4 in neither**. That is the whole residual, fully explained.

Per the falsifier as stated — *any genuine candidate in neither still falsifies P1* — **P1 fails.**

### Does the new `catalog_miss` stage flood the column? **No — because it emits nothing.**

The named failure mode (a record per tool per pass = 315 × 8 = 2,520 for run B) did not occur. Volume
is **identical to round 7**:

```
run A: 274 records, 43,817 bytes JSON
run B: 287 records, 44,638 bytes JSON  (first-occurrence + delta: 263 at pass 1, then 1–5 per pass)
```

The column keeps the economical first-occurrence-plus-delta shape. Every record is well-formed (0
missing `tool`/`stage`/`reason`/`pass`). **Judgement: volume is proportionate and unchanged.** But
this is not evidence the new stages are cheap — it is evidence they are inert. A stage that fires zero
times cannot flood anything, and cannot narrow anything either.

### The mid-turn deletion — still caught. This part works.

Run B's offered set shrinks across 8 passes and every removal carries a record:

```
pass1->2: -['world_list']                      pass5->6: unchanged (53)
pass2->3: -['world_map_create']                pass6->7: -['glossary_list_system_standards']
pass3->4: -['world_map_add_region']            pass7->8: unchanged (52)
pass4->5: -['world_map_add_marker']
```
```
{"pass": 3, "tool": "world_map_create", "stage": "rail_gate",
 "reason": "rail step already satisfied (mode=done_suppress)"}
```

Every inter-pass delta was removal-only (`+[]` in all 7 transitions). **This is the defect CP-0 exists
to catch, and the instrument catches it.**

### Two ambiguities I am reporting rather than resolving

1. **The delta encoding is still not self-describing.** Strict per-pass NEITHER is 267–278 for passes
   ≥ 2; only a cumulative reading (`pass <= N`) gives 4. That reading is sound only if the offered set
   shrinks monotonically within a turn. It did in every turn I drove, but **the record does not assert
   the invariant** and a reader cannot derive it from one stored turn. Unchanged from round 7.

2. **The `domain_not_selected` reason string contradicts itself.** 28 `glossary_*` tools in run B carry
   `"domain not in this turn's hot set (book, composition, glossary, knowledge, story)"`. An outsider
   reconstructing from the record alone reads that a tool named `glossary_book_create` was dropped
   because glossary was not selected — while the same sentence lists glossary as selected. The reason
   appears to be a generic template that names the hot set without naming the tool's own domain.

---

## 2. P3 — the kill path is fixed; the fix can invent a crash that never happened

### (a) `docker kill` before any tool call → restart → wait → restart — **PASS**

Armed a DB watcher to fire `docker kill` the instant the user row appeared.

```
2026-08-04T10:51:50.917Z KILLING
2026-08-04T10:51:51.721Z KILLED           (861 ms after the row; no assistant row, tc=0)

 sequence_num | role | outcome | finish_reason | tc |          created_at
--------------+------+---------+---------------+----+-------------------------------
           14 | user |         |               |  0 | 2026-08-04 10:51:50.861388+00
```

**Restart 1** (row age 44 s — inside the age bound):

```
healthy at 10:52:35
 sequence_num | role | outcome | finish_reason |       age
--------------+------+---------+---------------+-----------------
           14 | user |         |               | 00:00:44.344387
(no reconciler log line -> stamped 0+0)
```

Correctly spared. **Restart 2** (row age 5 m 20 s — past the bound):

```
row 14 now past the age bound at 10:57:11
=== RESTART 2 ===  healthy at 10:57:21
INFO:app.services.instrument: CP-0.4 crash reconciler: stamped 0 assistant + 1 user rows left
  non-terminal by a process that died before it could record its own outcome

 sequence_num | role | outcome | finish_reason |       age
--------------+------+---------+---------------+-----------------
           14 | user | crashed |               | 00:05:30.023978
```

The turn that killed the process now carries a terminal outcome. Round 7's `outcome IS NULL` across 22
polls is fixed. **PASS.**

### (b) THE DANGEROUS CASE — **FAIL**

I ran `reconcile_crashed_turns` from a **second process** against the live DB while a turn was
genuinely in flight (the service up, streaming) — the rolling-restart / second-replica shape.

```
=== live turn detected at 10:50:00.839 ===
>>> PROBE 1: default age bound (5 min) against a LIVE turn
--- BEFORE reconcile(older_than_minutes=5) ---
  seq=12 user      outcome=NULL      fr=NULL   age=0:00:00.531535
>>> reconciler returned: {"assistant": 0, "user": 1}
--- AFTER ---
  seq=12 user      outcome=NULL      fr=NULL   age=0:00:00.551677     ← spared, correctly

>>> PROBE 2: age bound DISABLED (0 min) against the SAME live turn
--- BEFORE reconcile(older_than_minutes=0) ---
  seq=12 user      outcome=NULL      fr=NULL   age=0:00:00.991278
>>> reconciler returned: {"assistant": 0, "user": 1}
--- AFTER ---
  seq=12 user      outcome=crashed   fr=NULL   age=0:00:01.020165     ← STAMPED WHILE LIVE
```

The turn then **finished normally**, and the false stamp was never corrected:

```
 sequence_num |   role    |  outcome  | finish_reason | tc |                       c
--------------+-----------+-----------+---------------+----+-----------------------------------
           12 | user      | crashed   |               |  0 | RUN-E8-LIVE: One at a time using…
           13 | assistant | completed | stop          |  5 | I have completed the requested st…
```

Row 12 says the user's turn crashed. It did not — it completed four seconds later with five
successful tool calls. **Nothing reconciles the stamp back.**

**The finding is not that I passed 0.** It is what passing 0 proves: **the age bound is the only thing
standing between the reconciler and a live turn. There is no liveness check of any kind** — no lease,
no heartbeat, no run-id, no "is a process currently serving this session". The reconciler cannot tell
a turn in flight from a turn whose process died; it infers deadness purely from wall-clock age. The
docstring is candid that erring early "invents a fact", and this is exactly that fact being invented.

**How exposed is the default?** Two branches, and they are very different:

*Assistant branch* — structurally safe. Sampled a live turn 21 times; the in-flight assistant row is
always already terminal-stamped, never `outcome IS NULL`:

```
distinct in-flight shapes observed (assistant row):
  seq=16 assistant outcome=crashed   fr=streaming  ASSIST_PRED=false
  seq=16 assistant outcome=completed fr=stop       ASSIST_PRED=false
ASSIST_PRED=true samples: 0 / 21
```

The row is written pessimistically as `crashed`/`streaming` during the turn and overwritten on
termination — a genuinely good design, and it is why the reconciler's assistant branch reports
`0 assistant` on **every** startup including the 223-row backfill. That branch only ever catches
legacy-shaped rows; on current-shape rows it is inert.

*User branch* — the live exposure. The window is `[user row inserted → assistant row inserted]`,
measured across all seven completed turns in my session:

```
 user_seq | asst_seq | gap_before_assistant_row_exists
        1 |        2 | 00:00:04.874512        9 |       10 | 00:00:04.529359
        3 |        4 | 00:00:04.266130       12 |       13 | 00:00:04.720250
        5 |        6 | 00:00:04.793972       15 |       16 | 00:00:04.602756
        7 |        8 | 00:00:04.276212
```

~4.3–4.9 s here, so the default 5-minute bound covers it with a wide margin **on this stack**. A false
stamp needs a turn whose *first* model response takes longer than 5 minutes to produce an assistant
row, at the moment a second process starts. That is not exotic: this repo has a standing note that LLM
pipelines run without timeouts, the stated hosting direction is self-hosted → cloud (multi-replica,
rolling restarts), and the reconciler is unscoped — it sweeps **every session of every user**, not the
one being restarted.

I could not manufacture a >5-minute first-token latency with the local model, so I cannot claim to have
observed a false stamp under the shipped default. What I *can* state as measured fact: **the guard is
purely temporal, a live turn inside the window is stamped, and the stamp is never withdrawn.** Round 8
asked me to "reason about and test the age bound"; the bound holds, and it is all there is.

### (c) No relabel of completed turns; idempotent — **PASS**

Restart 3, immediately after restart 2, with nothing new orphaned:

```
=== BASELINE terminal-row hash ===
c8fe360822dbeb3336b62180dfb91fb8
 crashed 229 | completed 71 | abandoned_by_user 11 | awaiting_input 8

=== RESTART 3 ===  healthy
(no reconciler log line -> stamped 0+0)

=== AFTER ===
c8fe360822dbeb3336b62180dfb91fb8
 crashed 229 | completed 71 | abandoned_by_user 11 | awaiting_input 8
```

Hash identical, every count identical, reconciler silent. The `outcome IS NULL` guard makes it
idempotent, and `finish_reason='streaming'` keeps it off completed rows. No double-stamp.

### The backfill, reported without a ruling

The first startup on the rebuilt image swept the whole database in one unbounded pass:

```
INFO: CP-0.4 crash reconciler: stamped 0 assistant + 223 user rows left non-terminal by a process
      that died before it could record its own outcome
```

226 user rows now read `crashed`, spanning `2026-04-03` … `2026-08-04`; 89 of them have a later row of
some kind, i.e. the user kept typing after an unanswered turn. The predicate looks defensible (a user
message that never got an assistant reply *is* an unrecorded failure), but note it conflates "the
process died" with "the model errored and nothing was written", and it rewrote four months of history
in one shot with no dry-run and no scoping.

---

## 3. `awaiting_input` rows that can never receive input — **5 of 8 exist**

`load_suspended_run` filters `WHERE run_id = $1 AND owner_user_id = $2 AND expires_at > now()`, and
runs expire after 6 hours. The only cleanup, `sweep_expired_runs`, has **zero callers** in the running
artifact:

```
$ docker exec infra-chat-service-1 grep -rn "sweep_expired_runs" /app/app/ --include=*.py
/app/app/db/suspended_runs.py:187:async def sweep_expired_runs(pool: asyncpg.Pool) -> int:
/app/app/services/instrument.py:513:  ``sweep_expired_runs`` is in, with a docstring claiming it runs
                                      periodically and zero callers.
```

So an `awaiting_input` turn whose suspended run has expired is unresumable **and** never cleaned:

```
              session_id              | seq |    outcome     |          expires_at           | run_expired | later_rows
--------------------------------------+-----+----------------+-------------------------------+-------------+------------
 019fca64-32ca-7f53-853a-085a24635c90 |  24 | awaiting_input | 2026-08-04 07:58:42.182895+00 | t           |          4
 019fcaa6-10b2-76e4-84ae-842e4198b250 |  10 | awaiting_input | 2026-08-04 09:02:13.172164+00 | t           |         16
 019fcaa6-10b2-76e4-84ae-842e4198b250 |  12 | awaiting_input | 2026-08-04 09:05:09.674787+00 | t           |         14
 019fcac6-8c70-70f4-9593-2822dba0e97d |   6 | awaiting_input | 2026-08-04 09:20:54.622601+00 | t           |          0
 019fcaf2-7716-7cf7-8a6a-424d2edf99d2 |   4 | awaiting_input | 2026-08-04 10:13:16.601843+00 | t           |          0
 019fcc18-2d35-7d47-9edc-823467eb92c5 |   4 | awaiting_input | 2026-08-04 15:34:20.400898+00 | f           |         16
 019fcc18-2d35-7d47-9edc-823467eb92c5 |  10 | awaiting_input | 2026-08-04 15:39:20.739336+00 | f           |         10
 019fcc55-683c-7c0f-8450-3b51e2b7c193 |   4 | awaiting_input | 2026-08-04 16:36:36.527844+00 | f           |         10
```

**Yes — five.** The two with `later_rows = 0` (sessions `019fcac6…` and `019fcaf2…`) are the purest
case: the conversation ends on a turn labelled "waiting for you", whose run object cannot be loaded and
will never be swept. 9 of 12 rows in `chat_suspended_runs` are past `expires_at` and still present, the
oldest since 2026-07-30.

This is an outcome that *looks* non-terminal and is in fact terminal-and-dead. It is the mirror of the
defect P3 just fixed: P3 closed "no outcome at all"; this is "an outcome that misdescribes the state".

---

## 4. Runs A–D

### Run A · clean — **PASS**

*"RUN-A8: List the chapters of this book. Then create a new chapter titled 'Prologue'. Then list the
chapters again to confirm it exists."* (rows 1–2.)

```
 sequence_num |   role    |  outcome  | finish_reason | runtime_variant | tc | adv_recs | wh_recs
            1 | user      |           |               | legacy          |    |          |
            2 | assistant | completed | stop          | legacy          |  3 |        4 |     274
```
```
book_list             src=tool lat=70 ok=true iter=0
book_chapter_create   src=tool lat=90 ok=true iter=1
book_list             src=tool lat=58 ok=true iter=2
missing source: 0   missing latency_ms: 0
```

`advertised_tools` present per pass (4 passes × 46 names); every `tool_calls` entry has `source` and
`latency_ms`; outcome `completed`/`stop`.

### Run B · withheld — **PASS**

*"RUN-B8: Now switch topic entirely: I want a world map… Create a world map, then add a region called
'Ashfall Reach', then add a marker in it called 'The Cinder Gate'…"* (rows 3–4.) 8 passes, 287 withheld
records across 3 stages, 6 tool calls, `awaiting_input`. Emphatically not an empty array:

```
{"pass": 1, "tool": "book_audio_generate", "stage": "domain_not_selected",
 "reason": "domain not in this turn's hot set (book, composition, glossary, knowledge, story)"}
{"pass": 3, "tool": "world_map_create", "stage": "rail_gate",
 "reason": "rail step already satisfied (mode=done_suppress)"}
```

### Run C · cancelled — **PASS**

Stopped mid-stream from the real UI (`button[title="Dừng tạo (Esc)"]`) after 7 tool calls:

```
 sequence_num |   role    |      outcome      | finish_reason | tc |                       c
            9 | user      |                   |               |  0 | RUN-C8-CANCEL-B: One at a time using tools
           10 | assistant | abandoned_by_user | interrupted   |  7 |
```

`abandoned_by_user`, not bare `interrupted` — the record distinguishes *the user abandoned this* from
*this broke*. The UI agrees: the bubble reads "Interrupted — response incomplete".

### Run D · killed — **PASS**

Covered in §2(a). `docker kill` 861 ms after the user row, before any tool call; the row is terminal
(`crashed`) after the reconciler's second startup. First round in eight where run D passes.

---

## 5. The question that decides the verdict

From run A's stored record **alone**, without reading code:

1. **Which tools was the model holding on its second pass?** — `advertised_tools[1].names`, 46 names.
   Directly readable. ✅
2. **Was anything hidden from it?** — 274 `withheld_tools` records, each with `tool`, `stage`, `reason`,
   `pass`. Readable, **but cumulatively** — the delta encoding means pass 2's own records are empty and
   the reader must accumulate `pass <= 2`. ⚠️ (§1, ambiguity 1)
3. **Did the third result come from a tool or from our own breaker?** — `tool_calls[2].source = "tool"`.
   Unambiguous, and the mechanism demonstrably works: run B's sixth entry reads
   `glossary_adopt_standards src=breaker ok=false source_inferred=true`, so the record both names the
   breaker *and* flags the one field it inferred. ✅
4. **How did the turn end?** — `outcome='completed'`, `finish_reason='stop'`. ✅

Three of four clean; one requires an accumulation the record does not tell you to perform.

---

## 6. The falsifier

**What I looked for that would have made this FAIL, and did:**

- **P1:** any name in the frozen 315 that, for a real turn, appears in **neither** `advertised_tools`
  nor `withheld_tools` — no matter how defensible its exclusion. I found 4, named them, confirmed
  they are live and non-deprecated, confirmed their domain was selected, and traced the drop to
  `filter_intent_gated_setup_tools` at catalog assembly. Had the count been 0, or had the four carried
  a `catalog_miss` record, P1 would have passed.
- **P3(a):** `outcome IS NULL` on the user row of a killed turn surviving a restart past the age
  bound. It did not — row 14 came back `crashed`. That is a pass.
- **P3(b):** a row belonging to a turn that was **not** dead receiving a `crashed` stamp. It did, at
  age 1.02 s, and the turn went on to complete. Had the reconciler consulted anything other than
  wall-clock age — a lease, a heartbeat, a live run-id — that stamp would have been impossible and
  P3(b) would have passed.
- **P3(c):** any change to the terminal-row hash across a second reconciler run. None — identical.

**What would change my P1 ruling:** a `withheld_tools` record naming any of the four with a stage and
a reason. Any stage. The objection is not that they are withheld — gating world-setup tools behind an
intent signal is clearly deliberate — it is that the deliberate act leaves no trace, which is the exact
class of defect CP-0 was built to make impossible.

---

## 7. Out of scope — things I saw that CP-0 did not ask about

1. **The stop control has no `data-testid`.** I had to locate it by
   `button[title="Dừng tạo (Esc)"]` — a localised string. An e2e that targets it is language-coupled,
   which this repo has been bitten by before.
2. **A killed turn renders as a bare user bubble with no reply and no error.** The record now knows the
   turn crashed; the UI still shows nothing. The `crashed` outcome has no rendering:
   `…RUN-D8-KILL: list the chapters… / 5:44:42 PM /` then straight to the composer.
3. **`sweep_expired_runs` has zero callers** (§3) — carrying a docstring that says it runs periodically.
4. **The book-create dialog's title field double-fills** under a programmatic `fill()` followed by
   `pressSequentially`, producing `"…verification)…verification)"`. Cosmetic, but it means the field
   is not fully controlled.
5. **The reconciler is globally scoped.** It sweeps every session of every user on any process start.
   For a single-tenant dev box that is fine; for the stated cloud direction it means one replica
   booting rewrites outcomes for every tenant.

---

## 8. How I drove the system, and what I did not do

Real UI throughout: Playwright-driven Chrome against `http://localhost:5174`, the Studio's embedded
co-author chat panel, logged in as the dev-seed account (`claude-test@loreweave.dev`,
`019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`). Messages were submitted through the composer; run C was
cancelled with the real stop button; run D was a real `docker kill` of `infra-chat-service-1`.

**Two things were not done through the UI, and I flag both as weaker:**

- The **concurrent-reconciler probe** in §2(b) ran `reconcile_crashed_turns` from a second Python
  process inside the container against the live pool. There is no UI or API path that triggers the
  reconciler on demand — it runs only in the startup lifespan — so simulating a second replica
  required calling it directly. This is a finding in itself: the reconciler has no operational surface,
  no dry-run, and no way to observe what it *would* stamp.
- The **`older_than_minutes=0` probe** is a parameter no deployment sets. I used it to determine
  whether anything besides the age bound protects a live turn. It does not.

All runs were in the throwaway book `VLIVE-R8 Throwaway (CP-0 verification)`
(`019fcc53-c23d-794e-9ff9-6b59c9cf6f80`), created for this round. Nothing was written to the dogfood
book — with one exception I must declare: the **startup reconciler's 223-row backfill and my two probe
runs stamped `crashed` on pre-existing orphaned user rows across the whole database, including the
dogfood book**. That was not avoidable — the reconciler is unscoped and fires on every start — but it
is a mutation of historical data outside my throwaway book and the reader should know it happened.

### The artifact did not stay frozen — but the container did

The brief said the artifact was FROZEN at `c7dc6195f`. It was not. **Two commits landed on the branch
while I was mid-run**, both touching the code under test:

```
1488b8ad2  committed=2026-08-04T17:41:56+07:00 (10:41:56Z)  fix(cp-0): the sweep was impersonating a
             terminal path — P3 read as satisfied because the record was repaired, not the path
54d25b2c1  committed=2026-08-04T17:54:09+07:00 (10:54:09Z)  fix(cp-0): the reconciler's halves were
             inverted — the branch with evidence was vacuous, the branch that fired was a guess
```

The first landed while I was driving run C; the second between my restart 1 and restart 2. I found
them only during post-run cleanup — I did not read them before or during measurement, and I am not
crediting or discounting them here.

**My results are unaffected, and I verified that rather than assuming it.** The image was built once
at the start from `c7dc6195f` and never rebuilt; restarts 2 and 3 used `--force-recreate` against the
existing image. Re-hashing the container at the end, after every test:

```
file                                  frozen(c7dc6195f)  HEAD(54d25b2c1)   container
app/main.py                           69a183981c3857ce   69a183981c3857ce  69a183981c3857ce  ==FROZEN
app/routers/internal.py               b2dd582930eb947f   b2dd582930eb947f  b2dd582930eb947f  ==FROZEN
app/services/instrument.py            5b178c14869d212d   260b38b586256081  5b178c14869d212d  ==FROZEN  <- HEAD drifted
app/services/stream_service.py        8b8a5f631d7cd51c   8b8a5f631d7cd51c  8b8a5f631d7cd51c  ==FROZEN
app/services/tool_discovery.py        cc3b4ba983ba92f2   cc3b4ba983ba92f2  cc3b4ba983ba92f2  ==FROZEN
app/services/voice_stream_service.py  0df6bdc3e55849bc   0df6bdc3e55849bc  0df6bdc3e55849bc  ==FROZEN
```

`instrument.py` — the reconciler, the subject of §2 — is the one file the new commits changed, and the
container carried the **frozen** version throughout. Every ruling above applies to `c7dc6195f` and to
nothing else. **§2's P3 rulings do not apply to `54d25b2c1`**, which by its own subject line rewrites
the two reconciler branches; that artifact is unverified and needs its own round.

**A second, avoidable problem:** both commits swept my scratch directory `.vlive8/` — nine throwaway
shell and Python files — into the repository, which means they were staged with a blanket `git add`
rather than an explicit path list. I have removed them from the index (`git rm -r --cached .vlive8`)
and from disk; that deletion is left **staged and uncommitted** for whoever owns those commits to
resolve. I did not rewrite history. This repo already has a standing rule about verifying the
*committed* file list rather than the staged one; this is that rule going unheeded, and it happened to
capture a verifier's working files in the middle of the verification they were running.

I did not read the builder's commit messages or notes before running. I read source only *after*
measuring, and only to locate mechanisms I had already observed live (§1's
`INTENT_GATED_SETUP_TOOLS`, §2's reconciler predicate, §3's `sweep_expired_runs`). Where the record
left something ambiguous — the delta encoding, the self-contradicting `domain_not_selected` reason —
I have reported the ambiguity rather than resolving it from source.
