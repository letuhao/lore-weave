# CP-0 · V-LIVE — round 9 verdict

**Artifact:** `874b3524e` — verified by normalised content hash to be exactly what the container ran,
at the start, after every kill/restart, and at the end. Working tree clean throughout (`git status`
empty; `git diff 874b3524e -- services/chat-service` empty).
**Driven:** the real UI — Playwright-driven Chrome against `http://localhost:5174`, the Studio's
embedded co-author chat panel, logged in as the dev-seed account `claude-test@loreweave.dev`
(`019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`). Model: Gemma-4 26B-A4B QAT (200K) via `lm_studio`.
**Throwaway book:** `VLIVE-R9 Throwaway (CP-0 verification)` — `019fcc92-4121-7ed3-b31a-cced6d470e4e`.
**Sessions:** `019fcc94-4fb8-755e-9981-71137f672563` (A, B), `019fcca0-4733-7b9e-9434-774907f20e8e`,
`019fcca2-a2dc-7a49-ba79-567619e4c87c` (C, D, final A).
**DB:** `loreweave_chat` inside `infra-postgres-1`, queried directly throughout.

---

## Overall verdict: **FAIL**

| item | ruling |
|---|---|
| **P1** — every narrowing registers | **FAIL** — residual still **4 of 315**, the same four, for a **third** round. The new `intent_gate` stage has emitted **zero** records, ever |
| **P3** — the kill path | **FAIL on (a)** — the empty-turn kill is now recorded **nowhere**; P3 is open again. **PASS on (b)** — the round-8 case still holds, and no longer needs the reconciler |
| expired-suspend resolver | **PASS** — 33 resolved, 0 non-expired runs touched, idempotent. `outcome_source` distinguishes it, but only as `reconciler`-vs-`NULL` (see §4) |
| Run A · clean | **PASS** |
| Run B · withheld | **PASS** |
| Run C · cancelled | **PASS** |
| Run D · killed | **FAIL** |
| The defect CP-0 was built for (offered set changes between passes) | **PASS during the turn** — **then DESTROYED by a normal user action.** See §5, the round's most serious finding |

---

## 0. PRECONDITION — the container was stale for the **NINTH** round running

Hashed before driving anything. Repo checkout is CRLF, image is LF, so line endings were normalised
(`tr -d '\r'`) before comparison — without that all 107 files appear to differ.

```
$ cd services/chat-service && find app -name '*.py' | sort | while read f; do
    echo "$(tr -d '\r' < "$f" | sha256sum | cut -d' ' -f1)  $f"; done
$ docker exec infra-chat-service-1 sh -c 'cd /app && ...same...'

PRE-REBUILD diff — 4 of 107 files differ:
  app/db/migrate.py            repo b0af714fef…  container 10f7eda5f2…
  app/main.py                  repo e0adcdfa07…  container 69a183981c…
  app/services/instrument.py   repo 15d3b4d367…  container 5b178c1486…
  app/services/tool_discovery.py repo 5467121523… container cc3b4ba983…
```

Docker reported `Up 30 minutes (healthy)`. **All four differing files are the four this round is
about**: `tool_discovery.py` holds the new `intent_gate` stage, `instrument.py` holds the reconciler
and the expired-suspend resolver, `main.py` holds the startup call, `migrate.py` holds the
`outcome_source` column. Note the container's `main.py` and `instrument.py` hashes are *round 8's*
(`69a183981c…`, `5b178c1486…` appear verbatim in the round-8 verdict). Had I trusted `(healthy)` I
would have re-measured round 8 and reported round 8's result.

```
$ docker compose build chat-service                              → Built
$ docker compose up -d --force-recreate chat-service             → Started
POST-REBUILD: all 107 files IDENTICAL to repo @ 874b3524e
```

Re-hashed after **every** kill and restart below (`cont3`, `cont4`, `cont5`): IDENTICAL each time.
Every result in this document was produced by the frozen artifact.

### The universe is trustworthy

Frozen snapshot vs the **live** federated catalogue (`POST /mcp` → `tools/list` on `ai-gateway`
`localhost:8218`, `X-Internal-Token: dev_internal_token`, the real user id):

```
frozen 315   live 315
frozen-live: []      live-frozen: []
```

Zero drift. Nothing in the neither-bucket can be dismissed as "a tool that no longer exists".

---

## 1. P1 — **STILL FALSIFIED. Residual 4 of 315, and I found why it will stay 4.**

### The number, redone exactly

Universe = the 315 names in `contracts/agent-runtime-baseline/tools-list.snapshot.json`. For a real
turn, count how many are in **neither** the advertised union nor the withheld set.

| | round 6 | round 7 | round 8 | **round 9** |
|---|---|---|---|---|
| run A turn-level NEITHER | 237 | 4 | 4 | **4** |
| run C turn-level NEITHER | — | — | — | **4** |
| final run A (post-restart) | — | — | — | **4** |
| **run B (world-setup intent)** | — | — | 4 | **0** |

```
=== RUN A (session 019fcc94…, seq 2) ===
passes=4  advertised per pass: {1: 51, 2: 51, 3: 51, 4: 51}
advertised_union=51  (in universe 42, outside universe 9: chat_search_sessions, confirm_action,
  conversation_search, glossary_confirm_action, glossary_propose_entity_edit, load_skill,
  run_subagent, workflow_list, workflow_load  — frontend/meta tools, correctly not in the snapshot)
withheld_records=269  withheld_distinct_tools=269
withheld per pass: {1: 269}
stages: {'domain_not_selected': 174, 'hot_seed': 95}
malformed records (missing tool/stage/reason/pass): 0
withheld JSON bytes: 42885

  TURN-LEVEL NEITHER = 4  (deprecated=0, non-deprecated=4)
  ['glossary_book_sync_apply', 'glossary_plan', 'glossary_propose_batch', 'glossary_propose_kinds']

=== RUN C (session 019fcca2…, seq 5) ===
stages: {'domain_not_selected': 187, 'hot_seed': 84, 'rail_gate': 1}
  TURN-LEVEL NEITHER = 4  — the same four

=== FINAL RUN A (session 019fcca2…, seq 12, after three restarts) ===
stages: {'domain_not_selected': 174, 'hot_seed': 95}
  TURN-LEVEL NEITHER = 4  — the same four
```

The four are exactly `INTENT_GATED_SETUP_TOOLS` minus `glossary_adopt_standards`, as my predecessor
diagnosed. `glossary_adopt_standards` is rail-exempted and **is** advertised — verified, not assumed:

```sql
SELECT p->>'pass', (p->'names') ? 'glossary_adopt_standards'
FROM chat_messages, jsonb_array_elements(advertised_tools) p
WHERE session_id='019fcc94-4fb8-755e-9981-71137f672563' AND sequence_num=2;
 pass | adopt
------+-------
 1    | t
 2    | t
 3    | t
 4    | t
```

### `intent_gate` has emitted zero records — anywhere, ever

```sql
SELECT count(*) FROM chat_messages, jsonb_array_elements(withheld_tools) r
WHERE r->>'stage'='intent_gate';
 count
-------
     0

SELECT r->>'stage', count(*) FROM chat_messages, jsonb_array_elements(withheld_tools) r
WHERE created_at > now() - interval '2 hours' GROUP BY 1 ORDER BY 2 DESC;
        stage        | count
---------------------+-------
 domain_not_selected |  1481
 hot_seed            |   961
 rail_gate           |    54
```

Not one row. The stage exists in the running image (`tool_discovery.py:500` calls
`record_surface_withheld(_n, stage="intent_gate", …)`) and the filter *does* fire — the four tools
are demonstrably absent from the advertised set. The records simply never land.

### The live proof that the gate is the sole cause — a controlled A/B

Run B was a **world-setup-intent** turn. On that path `filter_intent_gated_setup_tools` returns the
catalog unchanged, so the gate does not fire. Same universe, same runtime, same book, same session,
minutes apart:

| | gate fires? | NEITHER |
|---|---|---|
| run A ("read the book, create a chapter") | yes | **4** |
| run B ("set up the world/glossary for this book") | no | **0** |

The residual is not a measurement artefact and it is not a set of tools that "don't exist". It is
exactly the set the intent gate removes, and it disappears the moment the gate stops removing them.
Run B goes further: the model actually *called* `glossary_plan` — one of the four —

```
tool=glossary_plan  source=breaker  source_inferred=t  latency_unmeasured=breaker
pending=t  ok=f  runId=4b6b3906-d7af-4e5b-b8b5-393427bff40e
```

so these are live, reachable, callable tools that some turns are offered and other turns are not.
That difference is the single most important thing a narrowing record can carry, and it is the one
thing the record does not carry.

### The mechanism (I diagnosed this from the running image only, after measuring)

`record_surface_withheld` is a no-op when its context sink is unset:

```python
# instrument.py:256
def record_surface_withheld(tool: str, *, stage: str, reason: str) -> None:
    sink = surface_withheld.get()
    if sink is None:
        return
```

The sink is armed **after** the gate has already run — on both paths:

| path | gate called at | `surface_withheld.set([])` at | gap |
|---|---|---|---|
| fresh turn | `stream_service.py:5940` | `stream_service.py:6013` | 73 lines |
| resume | `stream_service.py:8001` | `stream_service.py:8016` | 15 lines |

Every `intent_gate` record is discarded before the buffer exists. The comment at line 6007 names this
exact failure — *"Arming it inside `_emit_chat_turn` was 435 lines and one stack frame too late …
every hot-seed narrowing registered nothing — the fourth distinct mechanism by which this same
narrowing has gone unrecorded"* — and the new stage is the fifth, introduced 73 lines above the fix
for the fourth.

### Judging volume, as asked

- **Does `intent_gate` flood?** No. Zero records. Had it worked it would emit at most **5** records
  per turn (the size of `INTENT_GATED_SETUP_TOOLS`) against a 269-record baseline — a ~1.9% increase,
  immaterial next to `domain_not_selected`'s 174.
- **Does it register a tool that WAS offered?** Not testable live, because it registers nothing. From
  the running source, `_exempt = INTENT_GATED_SETUP_TOOLS - set(rail_step_tools)` and only
  `_dropped` (names actually removed) are recorded, so a rail-exempted tool would correctly not be
  registered. In run A `glossary_adopt_standards` was rail-exempted and advertised on all four
  passes; the exemption logic is right. **This is a code-derived answer, not a measured one, and I
  flag it as weaker on that account.**

**P1 ruling: FAIL.** Residual unchanged at 4 of 315 across four independent turns on this artifact.

---

## 2. P3 — the kill path

### (a) Kill mid-turn, before any tool call — **the row is recorded NOWHERE. P3 is open again.**

Timing was made deterministic: a host watcher polled `chat_messages` for the probe's user row and
killed 3 s after it appeared, so the kill is provably inside the turn.

```
user row seen at 12:12:12
killing at   12:12:15
infra-chat-service-1
```

The prompt forbade tools ("Do not call any tools at all"), so the kill is before any tool call by
construction. Resulting state — a user row with no assistant reply at all:

```sql
SELECT message_id, sequence_num, role, outcome, outcome_source, finish_reason, created_at
FROM chat_messages WHERE session_id='019fcca2-a2dc-7a49-ba79-567619e4c87c' AND sequence_num=6;

              message_id              | seq | role | outcome | outcome_source | finish_reason |          created_at
--------------------------------------+-----+------+---------+----------------+---------------+-------------------------------
 019fccb0-4297-7fa5-8466-7009ba24c5c2 |   6 | user |         |                |               | 2026-08-04 12:12:11.286526+00
```

Then, exactly as the brief specifies — restart, wait past the age bound, restart again:

| event | time | result for `019fccb0` |
|---|---|---|
| restart 1 | 12:13 | `outcome` NULL |
| age bound (`older_than_minutes=5`) passes | 12:17:11 | — |
| restart 2 | 12:18:37 | `outcome` NULL |
| restart 3 | 12:19:5x | `outcome` NULL |

```sql
SELECT message_id, role, outcome, outcome_source, finish_reason, now()-created_at AS age
FROM chat_messages WHERE message_id='019fccb0-4297-7fa5-8466-7009ba24c5c2';

              message_id              | role | outcome | outcome_source | finish_reason |      age
--------------------------------------+------+---------+----------------+---------------+---------------
 019fccb0-4297-7fa5-8466-7009ba24c5c2 | user |         |                |               | 00:07:49.4175

SELECT count(*) FROM chat_outputs WHERE message_id='019fccb0-4297-7fa5-8466-7009ba24c5c2';  --> 0
```

Nothing recorded it. Not the reconciler (its user-row branch is gone; the assistant-`streaming`
branch has no assistant row to find), not `chat_outputs`, not the logs. The turn sits non-terminal,
which is the precise defect run D exists to catch: *"the turn does not sit forever in a non-terminal
state with nothing recorded."* It does.

The removal note in `instrument.py:527` argues the user-row branch could not tell a crash from a
user deleting an assistant reply. That reasoning is sound as far as it goes — but the branch was
removed and **nothing replaced it**, so a killed empty turn now leaves no trace at all. The choice
made was between a value that is sometimes wrong and no value; the third option — a value that is
always right about *something*, e.g. an explicit `unrecorded`/`orphaned` marker distinguishable from
NULL — is not present. (Reporting the gap, not proposing the fix.)

**P3(a) ruling: FAIL — regressed relative to round 8, where this case passed.**

### (b) Kill AFTER a checkpoint exists — **still passes, and no longer needs the reconciler**

A second watcher killed the container the moment an assistant row at `finish_reason='streaming'`
appeared:

```
checkpoint row seen at 12:17:56
infra-chat-service-1
killed at 12:17:56
```

```sql
SELECT message_id, sequence_num, role, outcome, outcome_source, finish_reason,
       length(content) AS len, jsonb_array_length(tool_calls) AS tc, created_at
FROM chat_messages WHERE session_id='019fcca2-a2dc-7a49-ba79-567619e4c87c' AND sequence_num=10;

              message_id              | seq |   role    | outcome | outcome_source | finish_reason | len | tc |          created_at
--------------------------------------+-----+-----------+---------+----------------+---------------+-----+----+-------------------------------
 513b26b7-5acd-484c-82f5-005cecb72f39 |  10 | assistant | crashed |                | streaming     |   0 |  1 | 2026-08-04 12:17:55.322611+00
```

`outcome='crashed'` was already present the instant the process died — written **pessimistically by
the checkpoint itself** at the tool boundary (`stream_service.py:6879`), not by the reconciler.
`outcome_source` is NULL because the path wrote it. The removal of the user-row branch therefore
cannot have broken this case: it never depended on the reconciler.

Corollary, confirming the docstring's own admission: the surviving reconciler branch is **vacuous**.
All 4 rows in the database at `finish_reason='streaming'` already carry an outcome, so the branch
matched nothing on any of my three restarts.

---

## 3. Runs A–D

### Run A · clean — **PASS**

Session `019fcc94-4fb8-755e-9981-71137f672563`, seq 2. `advertised_tools` present per pass (4
passes); every `tool_calls` entry has `source` and `latency_ms`; outcome recorded.

```sql
SELECT c->>'tool', c->>'source', c->>'ok', c->>'latency_ms', left(c->>'result',60)
FROM chat_messages, jsonb_array_elements(tool_calls) c
WHERE session_id='019fcc94-4fb8-755e-9981-71137f672563' AND sequence_num=2;

         tool         | source | ok  | latency_ms |                      result
----------------------+--------+-----+------------+---------------------------------------------------
 book_read            | tool   | t   | 53         | {"book": {"title": "VLIVE-R9 Throwaway (CP-0 ver…
 book_chapter_create  | tool   | t   | 65         | {"chapter_id": "019fcc95-325b-718a-ac9b-9561cd73…
 book_read            | tool   | t   | 82         | {"body": "This is the first sentence of the plac…

outcome=completed  outcome_source=NULL  finish_reason=stop  runtime_variant=legacy
```

**The question that decides the verdict**, answered from the stored record alone:

| question | answer from the record | verifiable? |
|---|---|---|
| which tools on pass 2? | `advertised_tools[pass=2].names` — 51 names, listed in full | **yes** |
| was anything hidden? | `withheld_tools` — 269 records, each with `tool`, `stage`, `reason`, `pass` | **yes, but incompletely** — 4 tools appear in neither array and are invisible to the reader |
| tool or our breaker? | `tool_calls[2].source = 'tool'`, `latency_ms=82` | **yes** |
| how did it end? | `outcome='completed'`, `finish_reason='stop'` | **yes** |

Three of four are answerable without inference. The second is answerable *as far as it goes* — and
the part it silently omits is the part P1 is about. **The inference is the finding**, per the brief.

### Run B · withheld — **PASS**

Session `019fcc94…`, seq 4, pre-decline reading. `withheld_tools` names tool, stage and reason; not
an empty array. 265 records across 3 stages. **The offered set changed between passes and the record
showed both states:**

```
pass 1 count 60
pass 2 count 59   REMOVED ['glossary_list_system_standards']
```

```sql
SELECT r->>'pass', r->>'tool', r->>'stage', r->>'reason'
FROM chat_messages, jsonb_array_elements(withheld_tools) r
WHERE session_id='019fcc94-4fb8-755e-9981-71137f672563' AND sequence_num=4 AND (r->>'pass')::int=2;

 pass |             tool               |   stage   |                  reason
------+-------------------------------+-----------+-------------------------------------------
 2    | glossary_list_system_standards | rail_gate | rail step already satisfied (mode=done_suppress)
```

This is the founding defect — a tool offered on pass 1 and deleted before pass 2 — and at the moment
the turn ended, it was recorded correctly, in both states, with a reason. **PASS.** What happened to
that record ninety seconds later is §5.

### Run C · cancelled — **PASS**

Stopped mid-stream with the real Stop button (`Dừng tạo (Esc)`), clicked from the page at ~7 s into
the stream.

```sql
SELECT sequence_num, role, outcome, outcome_source, finish_reason, length(content) AS len,
       jsonb_array_length(advertised_tools) AS passes, jsonb_array_length(withheld_tools) AS wh,
       jsonb_array_length(tool_calls) AS tc
FROM chat_messages WHERE session_id='019fcca2-a2dc-7a49-ba79-567619e4c87c' ORDER BY sequence_num;

 seq |   role    |      outcome      | outcome_source | finish_reason | len | passes | wh  | tc
-----+-----------+-------------------+----------------+---------------+-----+--------+-----+----
   3 | user      | abandoned_by_user |                |               | 150 |        |     |
   5 | assistant | abandoned_by_user |                | interrupted   | 638 |      2 | 272 |  2
```

Seq 5 is the strong case: `outcome='abandoned_by_user'` — the semantic answer — carried alongside
`finish_reason='interrupted'` — the mechanical signal. **`interrupted` alone would have been a
defect; it is not alone.** Partial content (638 chars), both passes of `advertised_tools`, 272
withheld records and 2 completed tool calls all survive the cancel.

Seq 3 is the weaker shape: cancelled before any assistant row existed, so the outcome lands on the
**user** row, written in-band (`INFO … CP-0.4 orphaned turn: no assistant row, outcome
'abandoned_by_user' stamped on user message 019fcca4-… ` at `11:59:22`, from `stream_service`, not
the reconciler). Terminal and correct, but that turn's surface is unrecoverable — no
`advertised_tools`, no `withheld_tools`. Noted, not counted as a failure of C's stated criterion.

### Run D · killed — **FAIL**

See §2. (a) fails, (b) passes. Since the brief's criterion for D is *"the turn does not sit forever
in a non-terminal state with nothing recorded"*, and it does, D is a FAIL.

---

## 4. The expired-suspend resolver — **PASS**, with one provenance caveat

Startup log, first boot of the rebuilt image (11:30:40Z):

```
INFO:app.services.instrument: CP-0.4 expired-suspend resolver: 33 turn(s) were advertising
'awaiting_input' with an expired run — input could never arrive, so they are recorded
abandoned_by_user
```

**Are the previously-unreachable rows now resolved?** Yes. My predecessor measured 5 of 8; the
population had grown to 33 by the time I ran, and all 33 were resolved.

**Did it touch any row whose run had NOT expired?** No — zero:

```sql
SELECT m.outcome_source, count(*) AS n,
       count(*) FILTER (WHERE s.run_id IS NULL)        AS no_suspend_row,
       count(*) FILTER (WHERE s.expires_at <= now())   AS run_expired,
       count(*) FILTER (WHERE s.expires_at >  now())   AS run_NOT_expired
FROM chat_messages m LEFT JOIN chat_suspended_runs s ON s.message_id = m.message_id
WHERE m.outcome='abandoned_by_user' GROUP BY 1;

 outcome_source | n  | no_suspend_row | run_expired | run_not_expired
----------------+----+----------------+-------------+-----------------
 reconciler     | 33 |              0 |          33 |               0
                | 13 |             13 |           0 |               0
```

Every reconciler-stamped row has an expired run. Nothing with a live run was touched. And every
remaining `awaiting_input` row has a **live** run, so all 5 can still receive input:

```sql
SELECT m.message_id, m.created_at, s.run_id, s.expires_at, (s.expires_at>now()) AS live
FROM chat_messages m LEFT JOIN chat_suspended_runs s ON s.message_id=m.message_id
WHERE m.outcome='awaiting_input';

              message_id              |          created_at           |                run_id                |          expires_at           | live
--------------------------------------+-------------------------------+--------------------------------------+-------------------------------+------
 ef1844b7-734f-4f20-b7cb-a851fb088e9c | 2026-08-04 11:55:28.050768+00 | 1a5157ae-68f9-4596-99fc-c50c8a38942b | 2026-08-04 17:55:55.425236+00 | t
 c2cd55bb-8cee-4a8a-9a32-43b6a29883c3 | 2026-08-04 11:47:31.5057+00   | beb740a8-0381-4b7c-9d5d-c6ad6c7fa31d | 2026-08-04 17:50:04.267444+00 | t
 a3db2041-9f38-47d8-ba6e-8bb36bd57037 | 2026-08-04 09:33:52.556181+00 | e20086dc-f148-429d-829f-c56ae9c36302 | 2026-08-04 15:34:20.400898+00 | t
 6e1aa9ee-764e-41bc-b8a5-94a193a6e00f | 2026-08-04 09:39:13.482652+00 | fef37e87-b5be-400d-9d97-e46def9358fd | 2026-08-04 15:39:20.739336+00 | t
 c735ab01-0111-489b-98a5-b3756172fa00 | 2026-08-04 10:36:08.29013+00  | b5299636-ca96-4a34-a1bc-b57eeb0113b8 | 2026-08-04 16:36:36.527844+00 | t
```

**Idempotent.** I restarted the service three more times; the resolver logged nothing on any of them
(`docker logs --timestamps | grep expired-suspend` shows the 11:30:40Z line and no other). The
`m.outcome IS DISTINCT FROM $1` guard holds.

**Does `outcome_source` distinguish these from path-recorded outcomes?** Partially — and the gap is
worth stating precisely.

```sql
SELECT outcome, outcome_source, role, count(*) FROM chat_messages
WHERE outcome IS NOT NULL GROUP BY 1,2,3 ORDER BY 1,2,3;

      outcome      | outcome_source |   role    | count
-------------------+----------------+-----------+-------
 abandoned_by_user | reconciler     | assistant |    33
 abandoned_by_user |                | assistant |    11
 abandoned_by_user |                | user      |     2
 awaiting_input    |                | assistant |     5
 completed         |                | assistant |    75
 crashed           |                | assistant |     4
 crashed           |                | user      |   226

SELECT count(*) FROM chat_messages WHERE outcome_source='path';  --> 0
```

- Rows the resolver wrote are unambiguously labelled `reconciler`. **That part works.**
- But the `CHECK` constraint permits `'path'` and **no row anywhere carries it** — the path never
  stamps its own provenance. So "path-recorded" is encoded as NULL, which is also the encoding for
  "written before the column existed" and for "written by a mechanism since deleted".
- Concretely: **226 user rows carry `outcome='crashed'` with `outcome_source = NULL`.** These are the
  false stamps from round 8's now-removed user-row branch — the ones the round-8 verdict flagged as
  having been written across the whole database including the dogfood book. They were not relabelled
  and they are now **indistinguishable from a genuine path-recorded crash**, which is the exact
  question `outcome_source` was added to answer. Nothing will revisit them: the branch that wrote
  them no longer exists.

I rule this **PASS** on the three questions asked, and record the NULL-overloading as a finding.

---

## 5. **The most serious finding of this round: a normal user action DESTROYS the pass history**

This was not something I was asked to look for. I found it because I declined a confirm card.

Run B (session `019fcc94…`, seq 4) ended `awaiting_input` with a confirm card. **Before** I touched
it, my accounting script read the row:

```
=== msg c2cd55bb-8cee-4a8a-9a32-43b6a29883c3 seq=4 outcome=awaiting_input finish_reason=awaiting_input
passes=2 advertised per pass: {1: 60, 2: 59}
withheld_records=265  stages: {'domain_not_selected': 180, 'hot_seed': 84, 'rail_gate': 1}
  TURN-LEVEL NEITHER = 0
  tool_calls=2
    - glossary_list_system_standards  source='tool'     latency_ms=104   ok=true
    - glossary_plan                   source='breaker'  latency_ms=None  pending=true
```

I then clicked **Từ chối** (Decline) — the ordinary UI button on the confirm card. Immediately after,
the **same message row**:

```
=== msg c2cd55bb-8cee-4a8a-9a32-43b6a29883c3 seq=4 outcome=awaiting_input finish_reason=awaiting_input
passes=1 advertised per pass: {1: 57}
withheld_records=266
  tool_calls=2
```

```sql
SELECT p->>'pass', p->>'count', (p->'names') ? 'glossary_list_system_standards' AS has_gls
FROM chat_messages, jsonb_array_elements(advertised_tools) p
WHERE message_id='c2cd55bb-8cee-4a8a-9a32-43b6a29883c3';
 pass | count | has_gls
------+-------+---------
 1    | 57    | f

SELECT c->>'tool', c->>'source', c->>'ok', c->>'latency_ms', c->>'latency_unmeasured'
FROM chat_messages, jsonb_array_elements(tool_calls) c
WHERE message_id='c2cd55bb-8cee-4a8a-9a32-43b6a29883c3';
           tool           | source  | ok |latency_ms| latency_unmeasured
--------------------------+---------+----+----------+--------------------
 glossary_plan            | breaker | f  |          | breaker
 glossary_adopt_standards | breaker | f  |          | breaker
```

What the resume path did to a row that had already recorded a real turn:

| | before decline | after decline |
|---|---|---|
| passes recorded | **2** (60 → 59) | **1** (57) |
| the pass-1→pass-2 deletion of `glossary_list_system_standards` | recorded, with stage + reason | **erased** |
| `glossary_list_system_standards` in pass 1 | present | **absent** |
| the executed tool call (`source='tool'`, `latency_ms=104`, `ok=true`, real result) | recorded | **erased** |
| tool calls now shown | 1 tool + 1 breaker | 2 breakers, both `ok=false` |

An outsider reading this row today would conclude the model was offered 57 tools on a single pass,
never successfully called a tool, and only ever hit two breaker confirms. **All three are false.**
The record was not merely truncated — it was replaced with a coherent, plausible, wrong account.

`AdvertisedToolsRecorder`'s own docstring in the running image states the invariant this violates:

> **One entry per model pass, appended, never replaced.** The founding defect of this effort is a
> tool that was offered on pass 1 and silently deleted before pass 2; a recorder that keeps only the
> latest state cannot show it… A last-write-wins column would have shown arm E as though the tool
> had never been offered at all.

The resume path is a last-write-wins column. The specific artefact CP-0 was built to preserve was
destroyed by a user clicking Decline — not by a crash, not by a race, by the product working.

I am reporting this under P1/the founding-defect test rather than as a separate item because it is
the same defect at a later moment: run B's two-state record **passed** when the turn ended and
**failed** ninety seconds later. Any measurement of `advertised_tools` taken after a resume is
measuring the resume, not the turn — which means every prior round's numbers for suspended turns are
suspect in the same way, if they were read after a confirm was answered.

---

## 6. Out of scope, but you asked me to report it

1. **A live suspended run with no UI affordance to satisfy it.** After the decline, the DB held a new
   pending confirm for `glossary_adopt_standards` (`run_id beb740a8-…`, expires 17:50:04Z), but the
   panel rendered only a `Confirm / Set up your book's world` header with an empty body and **no
   allow/decline buttons** — before and after a full page reload. The run can only end by expiring,
   at which point the resolver will record it `abandoned_by_user`. This is plausibly how
   `awaiting_input` rows become unreachable in the first place; it is at least how one of the five
   live ones in §4 got there. Out of CP-0's scope, but it manufactures CP-0's input data.
2. **The UI contradicts the record.** Immediately after the decline, the transcript still showed the
   `⚙ glossary_list_system_standards` call chip that the database had just erased. After a reload
   (re-reading from the DB) the chip was gone. The stored record and the user's own screen disagreed
   about what the assistant had done.
3. **`infra-video-gen-worker-1` is `(unhealthy)`** and has been for 2 days. Untouched by me,
   unrelated to CP-0.
4. **Two of my four kill attempts mis-fired** because my host tool-call round-trip is ~15 s, far
   longer than the ~4 s I assumed, so a `sleep N; docker kill` armed before the send fired *before*
   the send. I discarded those attempts and re-ran with a DB-triggered watcher (kill on the
   appearance of the target row), which is deterministic. Only the deterministic runs are reported
   above. Container hashes were re-verified after every one of these restarts.

---

## 7. The falsifier

**P1** — I would have ruled PASS if a real turn's advertised ∪ withheld sets had covered all 315
frozen names, or if the residual had been non-empty but every member carried an `intent_gate` record
naming stage and reason. I looked for `intent_gate` records specifically, across the whole database
and not just my turns: **zero**. And I built a control that would have falsified my own conclusion —
if the residual had stayed at 4 on the world-setup turn (where the gate provably does not fire), my
attribution to the gate would have been wrong. It went to **0**. Same universe, same runtime, one
variable.

**P3(a)** — I would have ruled PASS if `019fccb0-4297-7fa5-8466-7009ba24c5c2` had carried *any*
outcome after a restart past the age bound. I gave it three restarts and 7m49s, well past the 5-minute
bound, and checked `chat_outputs` as well in case the record lived elsewhere. Nothing. I also
deliberately tested the case that *would* have made a blanket "P3 is broken" claim wrong — the
kill-after-checkpoint case — and it passed, so the failure is specific and I have said so.

**Run C** — I would have ruled FAIL had the terminal state been bare `interrupted` with no outcome.
It was `outcome='abandoned_by_user'` beside `finish_reason='interrupted'`.

**§5** — I would have dismissed the pass-history loss as my own measurement error if the *before*
reading had come from a different row, a different session, or a cached result. It is the same
`message_id` (`c2cd55bb-8cee-4a8a-9a32-43b6a29883c3`), read by the same script against the same live
database, minutes apart, with one UI click between the two readings.

**What would change this verdict:** an `intent_gate` record appearing in `withheld_tools` on a
non-world-setup turn (P1); an outcome on a killed empty turn after a restart past the age bound
(P3a); and a resumed turn whose `advertised_tools` still contains the pre-suspend passes (§5).

---

## 8. How I drove the system

Real UI throughout: Playwright-driven Chrome at `http://localhost:5174`, the Studio's embedded
co-author chat panel (opened via the command palette, `Studio: Mở Trò chuyện đồng tác giả`). Book
created through the real "Sách mới" dialog. Messages submitted through the real composer. Run C used
the real Stop button. Run D used a real `docker kill` of `infra-chat-service-1`.

**Two things were not done through the UI, and I flag both as weaker:**

- The **kill timing** was driven by a host-side watcher polling `loreweave_chat`, because my
  tool-call round-trip (~15 s) is longer than a whole turn (~5 s) and I could not otherwise land a
  kill inside the window. The kill itself is a real `docker kill`; only its trigger is scripted.
- The **live catalogue comparison** in §0 used `POST /mcp` against `ai-gateway` on `localhost:8218`
  directly. There is no UI surface that lists the federated catalogue.

Everything was written into the throwaway book `VLIVE-R9 Throwaway (CP-0 verification)`
(`019fcc92-4121-7ed3-b31a-cced6d470e4e`). Chapters created: `R9 Alpha`
(`019fcc95-325b-718a-ac9b-9561cd73eef3`) and whatever the probe turns created before being killed.
Nothing was written to the dogfood book by me. **One exception I must declare, as round 8 did:** the
expired-suspend resolver is unscoped and fires on every start, so its 33-row sweep touched
`awaiting_input` rows across the whole database, not only my book. That was unavoidable — it runs in
the startup lifespan with no dry-run and no operational surface — but it is a mutation of historical
data outside my throwaway book and the reader should know it happened.

Working files were kept under `.vlive/r9/` (gitignored, per instruction). `.playwright-mcp/` is also
gitignored. `git status` is clean.

---

## 9. Ambiguity I am reporting rather than resolving

The reconciler's removed user-row branch and the `resolve_expired_suspends` resolver were introduced
together, and both bear on "a turn nobody ever finishes". After the removal, the two mechanisms cover
*expired suspends* and *checkpointed crashes* but leave *un-checkpointed crashes* uncovered — a gap
that did not exist in round 8. Whether that gap is intentional (accepting no-record over a wrong
record) or an oversight is not something I can determine from the running system, and I did not read
the builder's reasoning to settle it. I am recording it as a gap in the instrument either way,
because the claim under test is about what the record lets an outsider reconstruct, and for this
shape of turn the answer is currently *nothing*.
