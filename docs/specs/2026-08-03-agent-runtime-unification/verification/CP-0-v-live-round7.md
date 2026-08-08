# CP-0 · V-LIVE — round 7 verdict

**Artifact under test:** `4a2fc1dc4` (frozen)
**Driven:** the real UI (Playwright-driven Chrome against `http://localhost:5174`), the embedded
book-assistant panel in the Studio. Not the API.
**Throwaway book:** `VLIVE-R7 Throwaway (CP-0 verification)` — `019fcc14-930e-7c55-b10d-17b47bbd30fe`
**Session used:** `019fcc18-2d35-7d47-9edc-823467eb92c5` (all runs A–D, deliberately in one session —
see P3 risk test)
**Account:** `claude-test@loreweave.dev` (`019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)
**Model:** Gemma-4 26B-A4B QAT (lm_studio, local)
**No dogfood data touched.**

## Overall verdict: **FAIL**

| | verdict |
|---|---|
| **P1** — every tool absent from a pass's advertised set registers `{tool, stage, reason, pass}` | **FALSIFIED** (narrowly: 4 of 315, was 237) |
| **P3** — every terminal path writes an outcome | **FALSIFIED** (kill path only; cancel path now correct) |
| **Run A · clean** | **PASS** |
| **Run B · withheld** | **PASS** |
| **Run C · cancelled** | **PASS** (was FAIL in round 6) |
| **Run D · killed** | **FAIL** |
| The defect CP-0 was built for (offered set changes between passes) | **PASS** — both states recorded |

---

## 0. PRECONDITION — the container was stale for the **SEVENTH** round running

Hashed the repo tree against the container **before driving anything**.

```
$ cd services/chat-service && find app -name "*.py" | sort | xargs sha256sum   # repo, 107 files
$ docker exec infra-chat-service-1 sh -c "cd /app && find app -name '*.py' | sort | xargs sha256sum"
$ diff <repo> <container>
89c89  < 5b62228aac643d01… app/services/stream_service.py
       > af802cf29588314b… app/services/stream_service.py
98c98  < e813561e14fb5af2… app/services/tool_surface.py
       > d6b93e957f0b91b3… app/services/tool_surface.py
```

105 of 107 matched; the two that differed were **exactly the two files carrying the P1 and P3 fixes I
was sent to verify**. The direct functional probe:

```
$ docker exec infra-chat-service-1 grep -c 'domain_not_selected' /app/app/services/tool_surface.py
0
$ grep -c 'domain_not_selected' services/chat-service/app/services/tool_surface.py
3
```

The `domain_not_selected` stage — the entire P1 fix — **was not running**. The container's
`stream_service.py` hash `af802cf2…` is the worktree (CRLF) hash of that file at **`db4245eb5`**, per
round 6's own recorded table: i.e. the container was running **exactly the artifact round 6 built and
verified**, three commits behind the frozen artifact. The container reported `Up 37 minutes (healthy)`,
which is why a timestamp check would have passed and a hash check did not.

Remediation, then re-verification:

```
$ docker compose -f infra/docker-compose.yml build chat-service
$ docker compose -f infra/docker-compose.yml up -d --force-recreate --no-deps chat-service
$ <per-file comparison, all 107 files>
POST-REBUILD: all 107 files IDENTICAL to repo @4a2fc1dc4
```

Re-verified again **after** all four runs (the container was killed and restarted during run D):

```
POST-RUN: container still identical to repo @4a2fc1dc4 (107/107)
```

Every result below was produced by the frozen artifact.

### The universe is trustworthy

Before doing any accounting I checked the frozen snapshot against the **live** federated catalogue
(`POST /mcp` → `tools/list` on `ai-gateway`, `X-Internal-Token: dev_internal_token`, real user id):

```
LIVE catalogue size: 315
frozen:              315
frozen minus live (gone since freeze): 0
live minus frozen (new since freeze):  0
```

Zero drift. Every one of the 315 frozen names is a tool that exists right now, so nothing in the
neither-bucket can be dismissed as "a tool that no longer exists".

---

## 1. P1 — **FALSIFIED**, residual 4 of 315 (was 237)

### The number

Accounting redone exactly as in round 6: universe = the 315 names in
`contracts/agent-runtime-baseline/tools-list.snapshot.json`; for a real turn, count how many are in
**neither** the advertised nor the withheld set.

| | round 6 | round 7 |
|---|---|---|
| **run A turn-level NEITHER** | 237 (164 live) | **4** (4 live, 0 deprecated) |
| **run B turn-level NEITHER** | 206 (133 live) | **4** (4 live, 0 deprecated) |

```
runA: passes=4 advertised_union=46 withheld_records=274 withheld_tools=274
   TURN-LEVEL NEITHER = 4  (live=4, deprecated=0)
   ['glossary_book_sync_apply', 'glossary_plan', 'glossary_propose_batch', 'glossary_propose_kinds']
   of those, recorded as domain_not_selected: 0  -> survived domain gate: 4

runB: passes=8 advertised_union=57 withheld_records=287 withheld_tools=268
   TURN-LEVEL NEITHER = 4  (live=4, deprecated=0)
   ['glossary_book_sync_apply', 'glossary_plan', 'glossary_propose_batch', 'glossary_propose_kinds']
   of those, recorded as domain_not_selected: 0  -> survived domain gate: 4
```

**The same four tools, in both runs.** Not query-dependent — round 6's 237 varied with the message
(87 vs 101 candidates); this residual does not. That makes it a deterministic hole, not noise.

These four are genuine candidates by the strictest test available:

- they are in the live catalogue (verified above);
- they are **not** deprecated;
- the `glossary` domain **was** in the selected hot set for both turns — the recorded reason string on
  the 179/162 `domain_not_selected` records reads *"domain not in this turn's hot set (book,
  composition, glossary, knowledge, story)"*, and glossary is in that list;
- so they passed the domain gate, and then vanished with no record at any stage.

The arithmetic closes exactly, which is what makes this precise rather than suggestive. Run A:
315 − 179 `domain_not_selected` = 136 surviving; advertised-in-universe 37 + `hot_seed` 95 = 132;
136 − 132 = **4**. Run B: 315 − 162 = 153 surviving; 48 + 101 = 149; 153 − 149 = **4**.

There is a third drop point between domain selection and `hot_seed` that registers nothing. Per the
falsifier as stated — *any genuine candidate in neither still falsifies P1* — this falsifies P1.

I note without resolving it (I did not read the builder's reasoning): the advertised set contains
`glossary_propose_entity_edit`, which is **not** in the 315-name catalogue at all, while
`glossary_propose_batch` / `glossary_propose_kinds` are in the catalogue and silently dropped. That
pattern is consistent with a glossary-specific rewrite step that substitutes tools without recording
the substitution, but I am reporting the shape, not diagnosing it.

### `world_map_create` — round 6's decisive case, now fully accounted

Round 6's falsifier was `world_map_create`: unrecorded at passes 1–2, then carrying a `token_budget`
withheld record at pass 3. In round 7's run B it is in **exactly one bucket at every one of 8 passes**:

```
pass 1: advertised=True   withheld=NO RECORD
pass 2: advertised=True   withheld=NO RECORD
pass 3: advertised=False  withheld=rail_gate :: rail step already satisfied (mode=done_suppress)
pass 4: advertised=False  withheld=rail_gate :: rail step already satisfied (mode=done_suppress)
pass 5: advertised=False  withheld=rail_gate :: rail step already satisfied (mode=done_suppress)
pass 6: advertised=False  withheld=rail_gate :: rail step already satisfied (mode=done_suppress)
pass 7: advertised=False  withheld=rail_gate :: rail step already satisfied (mode=done_suppress)
pass 8: advertised=False  withheld=rail_gate :: rail step already satisfied (mode=done_suppress)
```

**This is the defect CP-0 exists to catch, and the instrument catches it.** A tool the model was
holding is deleted from the offered set mid-turn, and the record shows both states with a reason. The
whole per-pass sequence for run B:

```
pass1->2: -['world_list']
pass2->3: -['world_map_create']
pass3->4: -['world_map_add_region']
pass4->5: -['world_map_add_marker']
pass5->6: unchanged (53)
pass6->7: -['glossary_list_system_standards']
pass7->8: unchanged (52)
```

### Did the new stage flood the column? No.

The named failure mode — *a record for every tool in the catalogue on every pass* — would be
315 × 8 = 2,520 records for run B. Actual:

```
runA withheld records per pass: {1: 274}                                    total 274
runB withheld records per pass: {1: 263, 2: 1, 3: 2, 4: 3, 5: 4, 6: 4, 7: 5, 8: 5}  total 287
runA stages: domain_not_selected 179, hot_seed 95
runB stages: domain_not_selected 162, hot_seed 101, rail_gate 24
```

The column is **first-occurrence plus delta**: the bulk lands once at pass 1, and later passes carry
only the tools newly dropped at that pass. That is the economical shape, not the flooded one, and it is
what makes the run B trace above readable at a glance. Every record is well-formed —
`0` records across both runs are missing any of `tool`/`stage`/`reason`/`pass`.

**Judgement: the volume is proportionate, with one reservation.** 179 of run A's records are
byte-identical apart from the tool name, and the payload is ~44 KB of JSON on *every* assistant row
(`withheld JSON bytes: 43817` run A, `44638` run B). That is a storage cost carried per message
forever to express one sentence ("these 179 tools were in unselected domains"). It is informative, not
useless — but it is the least information-dense part of the record.

### The ambiguity I am reporting rather than resolving

Because the column is delta-encoded, "what was hidden from the model at pass 5?" is **not** answerable
from pass 5's records alone (run B pass 5 has 4 records); it requires reading all records with
`pass <= 5` cumulatively. That reading is only sound if the offered set shrinks monotonically within a
turn. It did in every turn I drove — every inter-pass delta was removal-only, `+[]` in all 7 run B
transitions and unchanged in all 3 run A transitions — but **the record does not state this
invariant**, and a reader cannot derive it from a single stored turn. Strictly, "every tool absent from
a pass's advertised set registers `{tool, stage, reason, pass}`" is not literally satisfied for passes
≥ 2 (per-pass NEITHER is 267–278). I rule on the turn-level number, as round 6 did, and flag this as
the one place where reconstruction depends on a property I observed rather than one the record asserts.

---

## 2. P3 — **FALSIFIED** on the kill path; the cancel path is fixed

### (a) Cancel before any streamed token — **PASS**

Cancelled at **1,507 ms** via the real UI stop control. Measured TTFT on comparable turns in this
session was 3,667–8,196 ms, and the message list contained no assistant text at the moment of the
click, so this is genuinely inside the pre-first-token window.

```sql
SELECT sequence_num, role, outcome, finish_reason, is_error,
       jsonb_array_length(COALESCE(tool_calls,'[]')) tc, left(content,55)
FROM chat_messages WHERE session_id='019fcc18-2d35-7d47-9edc-823467eb92c5'
  AND sequence_num>=15 ORDER BY sequence_num;
```

```
 sequence_num |   role    |      outcome      | finish_reason | is_error | tc |                          left
--------------+-----------+-------------------+---------------+----------+----+---------------------------------------------
           15 | user      |                   |               | f        |  0 | Write about 600 words describing the marketpl
           16 | assistant | completed         | stop          | f        |  0 | The first light of dawn over Ashfall Reach di
           17 | user      | abandoned_by_user |               | f        |  0 | RUN-C7-CANCEL-PRE-TOKEN: list the chapters, t
```

`abandoned_by_user`, not `interrupted` — it distinguishes *the user abandoned this* from *this broke*.
Round 6's finding is settled. The service log now returns the id it matched:

```
INFO:app.services.stream_service: CP-0.4 orphaned turn: no assistant row, outcome 'abandoned_by_user'
  stamped on user message 019fcc28-de23-7170-befa-d92cbccf81f9 (session 019fcc18-…)
```

and that id is row 17 exactly:

```
              message_id              | sequence_num | role |      outcome
--------------------------------------+--------------+------+-------------------
 019fcc28-de23-7170-befa-d92cbccf81f9 |           17 | user | abandoned_by_user
```

### The new risk the fix introduces — **PASS, and tested at its worst**

The fix targets "the newest user message in the session with `outcome IS NULL`". I ran every turn in
**one** session deliberately, so that by the time of the cancel there were **eight** older user rows
all carrying `outcome IS NULL`, every one of which **had** produced an assistant row. That is the
maximum-hazard case for both halves of the risk.

```sql
SELECT m.sequence_num, m.role, COALESCE(m.outcome,'(null)') AS outcome,
       EXISTS(SELECT 1 FROM chat_messages a WHERE a.session_id=m.session_id
              AND a.role='assistant' AND a.sequence_num=m.sequence_num+1) AS produced_assistant_row,
       left(m.content,38)
FROM chat_messages m WHERE m.session_id='019fcc18-2d35-7d47-9edc-823467eb92c5'
  AND m.role='user' ORDER BY m.sequence_num;
```

```
 sequence_num | role |      outcome      | produced_assistant_row |                  left
--------------+------+-------------------+------------------------+----------------------------------------
            1 | user | (null)            | t                      | List the chapters of this book. Then c
            3 | user | (null)            | t                      | Now switch topic entirely: I want a wo
            5 | user | (null)            | t                      | Write a very long, detailed 3000-word
            7 | user | (null)            | t                      | Compose a 4000-word chapter about the
            9 | user | (null)            | t                      | Please do all of these one at a time u
           11 | user | (null)            | t                      | RUN-C-CANCEL: list the chapters, then
           13 | user | (null)            | t                      | PROBE: list the chapters, then list th
           15 | user | (null)            | t                      | Write about 600 words describing the m
           17 | user | abandoned_by_user | f                      | RUN-C7-CANCEL-PRE-TOKEN: list the chap
```

It stamped **the turn that actually ended** (17) and **overwrote none** of the eight older ones. This
is correct by construction rather than by luck: a normally-completed turn leaves its user row NULL and
carries its outcome on the assistant row, so NULL user rows accumulate — but the turn currently ending
is always the newest, so "newest NULL" always names it.

One residual I could not test deterministically and am therefore only reporting: the selection is
resolved at stamp time, not at turn start. If a stamp were ever to fire after the *next* turn's user
row had been inserted, it would land on the wrong row. I saw no such case; I have no evidence either
way.

### (b) `docker kill` before any tool call — **FAIL**

Armed a DB watcher to fire `docker kill` the instant the user row appeared, so the kill lands before
any tool executes. It did: `Exited (137)`, and the turn had `tool_calls = 0` and no assistant row.

Immediately after the kill, with the service down:

```
 sequence_num | role |      outcome      | finish_reason | tc |                     left
--------------+------+-------------------+---------------+----+-----------------------------------------------
           17 | user | abandoned_by_user |               |  0 | RUN-C7-CANCEL-PRE-TOKEN: list the chapters, t
           18 | user | (null)            |               |  0 | RUN-D7-KILL: list the chapters, then list the
```

Brought the container back (`up -d --no-deps chat-service`, waited for `healthy`) and polled:

```
t+5s … t+60s:            seq18 outcome=(null)   (12 samples)
reload t+6s … t+60s:     seq18=(null)           (10 samples, after a full UI reload/reconnect)
```

No recovery sweep appears in the logs after restart. The killed turn left **no** suspended run either —
the only two rows in `chat_suspended_runs` for this session belong to the two earlier `awaiting_input`
turns:

```
                run_id                |              message_id              |          created_at           |                   left
--------------------------------------+--------------------------------------+-------------------------------+------------------------------------------
 fef37e87-b5be-400d-9d97-e46def9358fd | 6e1aa9ee-764e-41bc-b8a5-94a193a6e00f | 2026-08-04 09:39:20.739336+00 | Please do all of these one at a time usi
 e20086dc-f148-429d-829f-c56ae9c36302 | a3db2041-9f38-47d8-ba6e-8bb36bd57037 | 2026-08-04 09:34:20.400898+00 | Now switch topic entirely: I want a worl
```

Finally I sent a fresh turn in the same session to see whether a later terminal path reconciles the
orphan. It does not — and it correctly did not steal the stamp either:

```
 seq |   role    |      outcome      |                    left
-----+-----------+-------------------+--------------------------------------------
  17 | user      | abandoned_by_user | RUN-C7-CANCEL-PRE-TOKEN: list the chapters
  18 | user      | (null)            | RUN-D7-KILL: list the chapters, then list
  19 | user      | (null)            | POST-KILL-PROBE: just say OK.
  20 | assistant | completed         | OK
```

Row 18 is permanently non-terminal with nothing recorded: no outcome, no assistant row, no suspended
run, no log line. The UI renders it the same way — the message list shows the RUN-D7-KILL user bubble
with no reply beneath it and no error. `outcome IS NULL` on the user row of a killed turn falsifies P3,
and it is precisely run D's stated requirement that the turn "does not sit forever in a non-terminal
state with nothing recorded".

Note the `crashed` outcome exists and is reachable — the constraint allows it and the log shows
`terminal-persist … outcome=crashed` on in-flight saves — so what fails here is the path where the
process dies before it can run its own handler, which is the only path where a crash outcome would
have to be written by something other than the dying process.

---

## 3. Runs A–D

### Run A · clean — **PASS**

Turn: *"List the chapters of this book. Then create a new chapter titled 'Prologue'. Then list the
chapters again to confirm it exists."* (session rows 1–2.)

- `advertised_tools` present, **per pass**: 4 passes, 46 names each.
- every `tool_calls` entry has `source` and `latency_ms`:

```
book_list             source='tool'  latency_ms=119  ok=True  iter=0
book_chapter_create   source='tool'  latency_ms=116  ok=True  iter=1
book_list             source='tool'  latency_ms=63   ok=True  iter=2
missing source: []     missing latency_ms: []
```

- an outcome: `completed` / `finish_reason=stop`.

### Run B · withheld — **PASS**

Turn: *"…I want a world map for this story. Create a world map, then add a region called 'Ashfall
Reach'…"* (session rows 3–4.) 8 passes, 287 withheld records, 6 tool calls, `awaiting_input`.

`withheld_tools` names the tool, the stage and a reason, and is emphatically not an empty array —
three distinct stages appear, including the mid-turn `rail_gate` deletion shown above:

```
{"pass": 1, "tool": "book_audio_generate", "stage": "domain_not_selected",
 "reason": "domain not in this turn's hot set (book, composition, glossary, knowledge, story)"}
{"pass": 3, "tool": "world_map_create", "stage": "rail_gate",
 "reason": "rail step already satisfied (mode=done_suppress)"}
```

### Run C · cancelled — **PASS**

See §2(a). `abandoned_by_user` on the user row, id confirmed against the log.

### Run D · killed — **FAIL**

See §2(b).

---

## 4. The question that decides the verdict

Taking run B's stored record alone, without reading code:

1. **Which tools was the model holding on its second pass?** — `advertised_tools[pass=2].names`, 56
   names, listed verbatim. **Answerable directly.**
2. **Was anything hidden from it?** — Yes: `withheld_tools` with `pass<=2`, giving tool, stage and
   reason for each. **Answerable, but cumulatively** — see the delta-encoding ambiguity in §1.
3. **Did the third result come from a tool or from our own breaker?** — **Answerable directly**, and
   this is the strongest part of the instrument. Run B's sixth call reads:

```json
{"tool": "glossary_adopt_standards", "source": "breaker", "ok": false, "pending": true,
 "latency_ms": null, "latency_unmeasured": "breaker", "source_inferred": true,
 "runId": "e20086dc-f148-429d-829f-c56ae9c36302", "runtime_variant": "legacy"}
```

   while the other five read `"source": "tool"` with a real `latency_ms`. The record does not merely
   distinguish them — it marks the one field it *inferred* (`source_inferred: true`) and explains the
   null latency in-band (`latency_unmeasured: "breaker"`) instead of leaving a silent hole. That is the
   right shape for a degraded reading.
4. **How did the turn end?** — `outcome: awaiting_input`, `finish_reason: awaiting_input`.
   **Answerable directly** — for runs A, B and C. **Not answerable for run D**, where the record is
   absent entirely.

So three of four questions are answerable without inference, and the fourth is answerable for three of
the four turn shapes. The gap is not in what the record says; it is in the turn that leaves no record.

---

## 5. The falsifier

**What I looked for that would have made this FAIL, stated before I ran:**

- **P1** would have been falsified by *any* tool from the frozen 315 that, in a real turn, appeared in
  neither `advertised_tools` nor `withheld_tools` and could not be shown to be a non-candidate (absent
  from the live catalogue). It **was** falsified: 4 such tools, the same 4 in both runs, all live, all
  in a domain that was selected. P1 would have **survived** at zero, or if all four had turned out to
  be catalogue ghosts — I checked the live catalogue precisely to give that escape a chance, and it
  closed (zero drift).
- **P1** would *also* have failed, differently, if the new `domain_not_selected` stage had bought its
  completeness by emitting a record for every tool on every pass. It did not: 287 records across 8
  passes against a flood's 2,520.
- **P3** would have been falsified by `outcome IS NULL` on the user row of either terminal path. Cancel
  came back `abandoned_by_user`; **kill came back NULL**, and stayed NULL through a restart, a UI
  reconnect, two minutes of polling and a subsequent completed turn.
- The **overwrite risk** would have been demonstrated by the cancel stamp landing on any of rows
  1/3/5/7/9/11/13/15 rather than 17, or by any of those eight flipping away from `(null)`. Neither
  happened. I constructed the eight-deep NULL backlog specifically so this test could fail.
- The **CP-0 defect** would have been confirmed still-open if the record had shown only the final
  pass's offered set. It showed all 8, with the removal point and reason for each deleted tool.

---

## 6. Out of scope — things I saw that CP-0 did not ask about

1. **The stop control has no `data-testid` while the send button does.** During a run,
   `[data-testid="chat-send-button"]` is unmounted and replaced by a button whose only identity is
   `title="Dừng tạo (Esc)"`. Probing by testid — the obvious approach — yields *no stop/cancel/abort
   testid anywhere in the DOM*, which reads as "the UI offers no way to cancel before the first token".
   That conclusion would be wrong (the control appears at ~200 ms, long before TTFT), but it is the
   conclusion any testid-driven check reaches. Cheap to fix, and it makes run C automatable.
2. **`terminal-persist` logs the same message id repeatedly with `outcome=crashed`, 0 chars.** e.g.
   `msg a3db2041-…` logged five times (four at 0 chars, one at 117 chars), `msg 6e1aa9ee-…` twice, all
   `outcome=crashed`, for turns that ended up `completed` or `awaiting_input` in the database. No row
   in this session carries `outcome='crashed'`, so the final state is right — but something is invoking
   the terminal-persist path repeatedly per turn and logging a crash outcome each time. Either the
   logging is misleading or the write is redundant; I could not tell which from outside.
3. **The `awaiting_input` breaker turn (run B) left a `chat_suspended_runs` row that outlives the UI
   affordance.** Two such rows sit with `expires_at` six hours out; the confirm card for the first was
   still rendered as `task-confirm`/`task-dismiss` buttons much later in the session. Not a CP-0
   concern, but the interaction between suspended runs and session longevity looked untested.
4. **~44 KB of `withheld_tools` JSON on every assistant row.** Noted in §1 as a reservation rather than
   a defect, but at scale this is the dominant term in the size of `chat_messages`.
5. **The embedded Studio chat panel opens onto a portal-rendered "start new chat" modal** that does not
   appear in the accessibility tree at normal snapshot depth. Only a navigation nuisance, but it made
   the panel look broken (composer absent, zero textareas in the document) until I screenshotted it.

---

## 7. How I drove the system, and what I did not do

Real UI throughout: Playwright-driven Chrome against `http://localhost:5174`, the Studio's embedded
co-author panel, typing into `[data-testid="chat-input-textarea"]` and clicking the real send and stop
controls. No API calls were used to *drive* chat. The one direct HTTP call I made was read-only and not
part of any run: `tools/list` against `ai-gateway` to establish that the frozen 315 still matches the
live catalogue, which the P1 accounting depends on.

Every row above was read by me out of `loreweave_chat` inside `infra-postgres-1` and is pasted, not
described. All runs were in the throwaway book `VLIVE-R7 Throwaway (CP-0 verification)`
(`019fcc14-930e-7c55-b10d-17b47bbd30fe`); no dogfood book was touched.

No run was impossible to perform. Run D performed exactly as instructed and the system failed it.

I did not read the builder's commit messages or notes before running. Where the record left something
open — the delta-encoding invariant in §1, the stamp-timing race in §2(a), the duplicate
`terminal-persist` logging in §6 — I have reported the ambiguity rather than resolving it from source.
