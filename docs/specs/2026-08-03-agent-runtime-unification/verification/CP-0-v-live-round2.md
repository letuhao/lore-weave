# CP-0 · V-LIVE — verdict (ROUND 2)

**Verifier:** V-LIVE (running-system verifier), round 2.
**Artifact frozen at:** `e75ad5d7d`
**Date driven:** 2026-08-04 UTC 00:45 → 01:07
**Discipline:** I read no commit messages and no builder notes before driving. I read round 1's
verdict (`CP-0-v-live.md`) only *after* every run below was complete and every row was pulled.

---

## 0. Verdict

| | verdict |
|---|---|
| **Overall** | **FAIL** |
| **A · clean** | **PASS** (with one defect, A-d1) |
| **B · withheld** | **PASS** — round 1's finding is **RESOLVED** (with one defect, B-d1) |
| **C · cancelled** | **FAIL** |
| **D · killed** | **FAIL** |

**Round 1's finding is resolved.** Round 1 failed on B: the token budgeter dropped tools and
`withheld_tools` was `NULL`. On this build the budgeter's drops reach the column, exactly and
completely — a `tool_load` whose own result note reads `"Loaded 7 of 310 tools (token budget)"`
produced **303** `withheld_tools` entries, each naming the tool, `stage: "token_budget"`, and a
reason. 310 − 7 = 303. I did not accept the claim; I derived the expected count from the tool's
own output and matched it against the row.

**Why the overall is still FAIL, in one sentence:** the two runs the brief said were the ones that
matter are the two that fail — a turn cancelled before the model emits its first token records
**nothing at all** (the service logs, in its own words, `empty terminal turn recorded nowhere`), and
a turn whose container is killed mid-stream records **nothing at all** and is still non-terminal
minutes after the service is healthy again.

---

## 1. The falsifier

*What I looked for that would have made this FAIL. Each was a live hypothesis, not a ticked box.*

| # | falsifier | outcome |
|---|---|---|
| **F1** | The container does not contain `e75ad5d7d`, so the verdict is worthless | **FOUND, and corrected before any run.** See §2. This is why F1 is first: round 1 hit it too. |
| **F2** | `withheld_tools` is `NULL`/empty on a turn where the **token budgeter** demonstrably dropped tools (round 1's finding) | **Not found.** Two independent turns, drop counts derived from the `tool_load` result note *before* looking at the column: 36−8=**28** → 28 rows; 310−7=**303** → 303 rows. All `stage='token_budget'`. |
| **F3** | `withheld_tools` is populated but **vacuous** — no tool name, or a single blanket stage/reason with no per-tool identity | **Not found.** Each element is `{tool, stage, reason}` with a real tool name. |
| **F4** | The withheld list is *not falsifiable against* the advertised list — i.e. it is a decorative dump | **FOUND (partial).** 10 of 28, and 19 of 303, "withheld" tools were simultaneously in `advertised_tools` on **every** pass. See B-d1. |
| **F5** | `advertised_tools` records only the final pass, so a set that changes mid-turn is invisible — *the specific defect CP-0 exists to catch* | **Not found.** Run A records 4 passes and the pass 2→3 diff is exactly `+kg_view_delete`; run B records 3 passes and the pass 1→2 diff is exactly `+book_update_details, +glossary_entity_set_attributes, +glossary_propose_entities`. Both states are present. |
| **F6** | `tool_calls[].source` is a decorative constant | **Not found.** Real values differ by origin: `kg_project_list` → `source:"tool"`, `latency_ms:80`; `tool_load` → `source:"meta"`, `source_inferred:true`. |
| **F7** | Every `tool_calls` entry has `source` **and** `latency_ms`, as run A's row requires | **FOUND.** `latency_ms` is `null` on every `meta` call. See A-d1. |
| **F8** | A user cancel is recorded as `interrupted` alone — indistinguishable from "this broke" | **Not found where a row exists.** `outcome='abandoned_by_user'`, `finish_reason='interrupted'`. But see F9. |
| **F9** | A cancelled turn sits with **nothing** recorded | **FOUND.** Cancel before first token → no assistant row at all. See §C. |
| **F10** | A killed turn sits forever non-terminal with nothing recorded | **FOUND.** See §D. |

F2 is resolved; F5 — the failure the brief was written around — is clean. F9 and F10 are the
findings, and they are on the two runs the brief flagged as decisive.

---

## 2. Was the running container the code under test? — **No. I rebuilt it.**

The brief warned that round 1 found a stale container. It was stale again. I checked **before**
driving anything, and I checked by a whole-file property, not by the symbol I expected to find.

```
$ cd services/chat-service && for f in ...; do
    repo=$(tr -d '\r' < "$f" | sha256sum); cont=$(docker exec infra-chat-service-1 sh -c "tr -d '\r' < /app/$f" | sha256sum)
  done
=== app/services/instrument.py    repo lines: 281   cont lines: 263   HASH DIFFERS
=== app/services/stream_service.py repo lines: 8102  cont lines: 8028  HASH DIFFERS
=== app/db/migrate.py              repo lines: 809   cont lines: 807   HASH DIFFERS
    app/services/token_budget.py                                       match
    app/services/tool_surface.py                                       match
```

Line endings were normalised (`tr -d '\r'`) before hashing, so this is a real content difference,
not a CRLF artifact — and two of the five files matched under the same normalisation, which is what
proves the method sound.

```
$ docker compose -f infra/docker-compose.yml build chat-service
   naming to docker.io/library/infra-chat-service:latest  DONE
$ docker compose -f infra/docker-compose.yml up -d --force-recreate --no-deps chat-service
   Container infra-chat-service-1  Recreated / Started
```

Re-verified by hashing the **entire** Python tree, not the files I happened to suspect:

```
$ find app -name '*.py' | sort | while read f; do tr -d '\r' < "$f" | sha256sum; done | sha256sum
repo tree: 6ed3703aa8ea77453270622bf676aace85f0fee74e5515cc6056ae4bb44d7c59
cont tree: 6ed3703aa8ea77453270622bf676aace85f0fee74e5515cc6056ae4bb44d7c59
```

Identical. Every run below is against `e75ad5d7d`.

---

## 3. How I drove the system

**Via the real UI**, at `http://localhost:5174`, in Chromium under Playwright — logged in through
the login form, created the session through the new-chat dialog, typed into the real composer, sent
with the real send button, and cancelled with the real stop button (`button.bg-destructive`, the
control that replaces send while `isStreaming`). No API call substituted for a user action in any
of runs A–D.

The **only** thing I did through the API was create the throwaway book (setup, not a run) and mint
a token to read nothing. Book creation via `POST /v1/books`.

**Throwaway book:** `CP0-VLIVE-R2-THROWAWAY` — `019fca3c-97a2-7182-a5b3-42b493c17a89`. Nothing was
written into any existing content book. (The chat session did not bind to it; see §6-O3.)

**Session driven:** `019fca3d-a8ba-7d88-84d5-549560835891`
**Account:** `claude-test@loreweave.dev`, user `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`
**Model:** Gemma-4 26B-A4B QAT (200K) via LM Studio — the account's default chat model.

---

## 4. The turn ledger — every row this session produced

```sql
SELECT sequence_num AS seq, role, outcome, finish_reason, runtime_variant AS rt,
       length(content) AS chars,
       jsonb_array_length(advertised_tools) AS adv_passes,
       jsonb_array_length(withheld_tools)   AS withheld,
       jsonb_array_length(tool_calls)       AS calls
FROM chat_messages
WHERE session_id='019fca3d-a8ba-7d88-84d5-549560835891'
ORDER BY sequence_num;
```

```
 seq |   role    |      outcome      | finish_reason |   rt   | chars | adv_passes | withheld | calls
-----+-----------+-------------------+---------------+--------+-------+------------+----------+-------
   1 | user      |                   |               | legacy |   220 |            |          |
   2 | assistant | completed         | stop          | legacy |   694 |          4 |       28 |     2   <- RUN A
   3 | user      |                   |               | legacy |   167 |            |          |
   4 | assistant | completed         | stop          | legacy |    60 |          3 |      303 |     2   <- RUN B
   5 | user      |                   |               | legacy |   244 |            |          |
   6 | assistant | completed         | stop          | legacy |  7968 |          1 |          |
   7 | user      |                   |               | legacy |   289 |            |          |       <- RUN C-1: NO ASSISTANT ROW
   8 | user      |                   |               | legacy |   168 |            |          |
   9 | assistant | completed         | stop          | legacy |   862 |          1 |          |
  10 | user      |                   |               | legacy |   144 |            |          |
  11 | assistant | completed         | stop          | legacy |  1527 |          1 |          |
  12 | user      |                   |               | legacy |    67 |            |          |
  13 | assistant | abandoned_by_user | interrupted   | legacy |   264 |          1 |          |       <- RUN C-2: recorded
  14 | user      |                   |               | legacy |   117 |            |          |       <- RUN D: NO ASSISTANT ROW
(14 rows)
```

Seq 7 and seq 14 are the findings. Both are user messages with **no assistant row at all** — a
question the user asked and a turn the record cannot account for.

---

## 5. The runs

### A · clean — **PASS** (defect A-d1)

Turn: *"Use the tool_list tool to list the tool categories you have available, then use tool_load to
load the 'knowledge' category…"* Message `b3fe8e50-4f3f-406c-a8b6-7a62b0507256`. Completed normally
in the UI; the assistant answered and the FE showed a `⚙ tool_list ⚙ tool_load` chip.

**The question that decides the verdict — answered from the stored record alone, no code read:**

**(1) Which tools was the model holding on its second pass?**

```sql
SELECT e->>'pass', e->>'count', e->>'tool_choice', jsonb_array_length(e->'names')
FROM chat_messages m, jsonb_array_elements(m.advertised_tools) e
WHERE m.message_id='b3fe8e50-4f3f-406c-a8b6-7a62b0507256';
```
```
1|29|auto|29
2|29|auto|29
3|30|auto|30
4|30|auto|30
```
Pass 2, verbatim from the row — 29 tools:
```json
["book_chapter_save_draft","chat_search_sessions","confirm_action","conversation_search",
 "glossary_deep_research","kg_entity_edge_timeline","kg_graph_query","kg_list_templates",
 "kg_ontology_propose","kg_project_list","kg_propose_edge","kg_propose_fact","kg_schema_read",
 "kg_sync_available","kg_triage_list","kg_triage_resolve","kg_view_read","load_skill",
 "memory_forget","memory_recall_entity","memory_remember","memory_search","memory_timeline",
 "run_subagent","tool_list","tool_load","web_search","workflow_list","workflow_load"]
```
**Answerable.** And the set *changes*: the pass 2 → pass 3 diff is exactly one tool added.
```sql
SELECT 'ADDED: '||t FROM (SELECT t FROM p WHERE pass=3 EXCEPT SELECT t FROM p WHERE pass=2) a
UNION ALL SELECT 'REMOVED: '||t FROM (SELECT t FROM p WHERE pass=2 EXCEPT SELECT t FROM p WHERE pass=3) b;
-- ADDED at pass3: kg_view_delete
```
This is the specific defect CP-0 was built for — an offered set that changes between passes — and
the record shows **both** states, not just the last. **F5 clean.**

**(2) Was anything hidden from it?** Yes — 28 tools, each named, staged and reasoned:
```json
[{"tool":"kg_add_nodes","stage":"token_budget","reason":"did not fit the activation token budget"},
 {"tool":"kg_adopt_template","stage":"token_budget","reason":"did not fit the activation token budget"},
 {"tool":"kg_build","stage":"token_budget","reason":"did not fit the activation token budget"}, …]
```
**Answerable** — with the caveat in B-d1.

**(3) Did the third result come from a tool or from our own breaker?** Run A made two calls, not
three, so I answer the question's substance: *can origin be told apart from the record?* Yes.
```json
[{"id":"call_...289","ok":true,"args":{"category":"all"},"tool":"tool_list","source":"meta",
  "iteration":0,"latency_ms":null,"declaration":"tool_list","runtime_variant":"legacy","source_inferred":true},
 {"id":"call_...290","ok":true,"args":{"category":"knowledge"},"tool":"tool_load","source":"meta",
  "iteration":1,"latency_ms":null,"declaration":"tool_load","runtime_variant":"legacy","source_inferred":true}]
```
Both are `source:"meta"` — our own runtime primitives, not a dispatched tool. Run B supplies the
contrast: `kg_project_list` → `"source":"tool"`, `"latency_ms":80`, and **no** `source_inferred`
flag. So the record does distinguish "a tool answered" from "our own code answered".
**Answerable.**

**(4) How did the turn end?** `outcome='completed'`, `finish_reason='stop'`. **Answerable.**

All four answerable without reading code. **A · PASS.**

> **A-d1 — `latency_ms` is `null` on every `meta` call.** Run A's row in the brief requires *"every
> `tool_calls` entry has `source` and `latency_ms`"*. Both of run A's entries have `latency_ms:
> null`. Only the dispatched-tool path times itself. An outsider cannot say how long the runtime
> spent inside `tool_load` — and `tool_load` is the call that reshapes the offered set, so it is
> precisely the one whose cost matters. Related: `source_inferred: true` means the record itself
> declares that `source` on these rows was **guessed after the fact**, not observed at the call
> site. A field that flags itself as inferred is honest, but it is not an observation.

---

### B · withheld — **PASS. Round 1's finding is RESOLVED.** (defect B-d1)

I tested the exact case round 1 failed on, and I derived the expected number from the system's own
output *before* reading the column, so the check could come out wrong.

**B-1 (inside run A):** `tool_load(category="knowledge")`. The tool's own result note:
```sql
SELECT (e->'result'->>'note') FROM chat_messages m, jsonb_array_elements(m.tool_calls) e
WHERE m.message_id='b3fe8e50-...' AND e->>'tool'='tool_load';
-- Loaded 8 of 36 tools (token budget). Call tool_load with specific names to load the rest.
```
36 − 8 = **28** expected drops. `jsonb_array_length(withheld_tools)` = **28**. Every one
`stage='token_budget'`.

**B-2 (dedicated):** *"Now call tool_load with category 'all' to load every available tool. After
that, actually call the kg_project_list tool…"* Message `7882d01a-b0a4-4302-9ba5-847b57cb3a2b`.
```
-- Loaded 7 of 310 tools (token budget). Call tool_load with specific names to load the rest.
```
310 − 7 = **303** expected drops.
```sql
SELECT e->>'stage', e->>'reason', count(*) FROM chat_messages m, jsonb_array_elements(m.withheld_tools) e
WHERE m.message_id='7882d01a-b0a4-4302-9ba5-847b57cb3a2b' GROUP BY 1,2;
-- token_budget|did not fit the activation token budget|303
```
```json
[{"tool":"book_audio_generate","stage":"token_budget","reason":"did not fit the activation token budget"},
 {"tool":"book_chapter_bulk_create","stage":"token_budget","reason":"did not fit the activation token budget"},
 {"tool":"book_chapter_create","stage":"token_budget","reason":"did not fit the activation token budget"}]
```
**Not an empty array. Names the tool, the stage, and a reason.** Round 1's `NULL` is gone, in the
one case round 1 named. And the offered set changed across passes here too — 30 → 33 → 33, diff
`+book_update_details, +glossary_entity_set_attributes, +glossary_propose_entities`.

Run B also produced the real-tool contrast that makes `source` non-decorative:
```json
{"id":"call_...292","ok":true,"tool":"kg_project_list","source":"tool","iteration":1,
 "latency_ms":80,"declaration":"kg_project_list","runtime_variant":"legacy"}
```

> **B-d1 — the withheld list has no pass, and it contradicts the advertised list.**
> `advertised_tools` is per-pass; `withheld_tools` is a flat bag with **no `pass` field**. So the
> record cannot say *when* a tool was withheld. Worse, the two lists disagree:
> ```sql
> WITH wh  AS (SELECT e->>'tool' AS t FROM m, jsonb_array_elements(m.withheld_tools) e),
>      adv AS (SELECT DISTINCT n#>>'{}' AS t FROM m, jsonb_array_elements(m.advertised_tools) p,
>                                              jsonb_array_elements(p->'names') n)
> SELECT count(*) FROM wh JOIN adv USING (t);
> -- run A: 10 of 28   run B: 19 of 303
> ```
> Run A lists `kg_graph_query`, `kg_triage_list`, `memory_search` (and 7 more) as **withheld with
> reason "did not fit the activation token budget"** while those same tools are in
> `advertised_tools` on **all four passes**. An outsider reconstructing "what was hidden from the
> model" gets 10 false positives out of 28 — 36% — and has no `pass` field with which to reconcile
> them. The column is populated; it is not yet self-consistent.

---

### C · cancelled — **FAIL**

I cancelled from the UI twice, with the real stop button, at different points in the stream.

**C-2 (cancel after ~3.6 s, model had emitted text) — recorded correctly.**
```
13|assistant|abandoned_by_user|interrupted|264 chars|advertised_tools: 1 pass, 24 tools
```
`outcome='abandoned_by_user'` distinguishes *the user abandoned this* from *this broke*.
`interrupted` appears only in `finish_reason`, which is the provider's word. This is what the brief
asks for, and it works.

**C-1 (cancel after ~8 s, before the model emitted its first token) — recorded nothing.**

Seq 7 is a user message with **no assistant row**. The service says so itself:
```
00:57:42.954  INFO  CP-0.4 silent-exit: empty terminal turn recorded nowhere
              (session 019fca3d-…, msg 451a02b9-3539-44e7-8b84-7fa143ea1460, reason=interrupted).
              Closes at CP-3.6 with the other three silent exits.
00:57:42.958  WARNING  interrupt-persist failed for session 019fca3d-…
```
```sql
SELECT count(*) FROM chat_messages WHERE message_id='451a02b9-3539-44e7-8b84-7fa143ea1460';
-- 0
```
The message id the log names was never written. Minutes later the UI shows the user's question with
nothing after it — no reply, no error card, no trace.

**Two further things I did not expect and am reporting as part of C, not around it:**

1. **`interrupt-persist failed` fires on *both* cancels** — the one that recorded and the one that
   did not. The primary persist path fails 100% of the time on cancel; C-2 only survived because a
   *fallback* (`terminal-persist`) caught it. The failure is a `CancelledError` propagating through
   what was meant to protect the write:
   ```
   Traceback (most recent call last):
     File "/app/app/services/stream_service.py", line 7319, in _emit_chat_turn
       await asyncio.shield(
   asyncio.exceptions.CancelledError: Cancelled via cancel scope … by <Task … RequestResponseCycle.run_asgi() …>
   ```
   A shield around the write does not save it when the enclosing cancel scope is the thing being
   cancelled. So the durability of a cancelled turn's record rests entirely on the fallback, and the
   fallback declines when there is no text.
2. **The record's completeness is conditional on the model having produced output.** A cancel is a
   user action; whether it leaves a trace should not depend on whether a token happened to arrive
   first. As it stands, the faster the user is, the less the record knows.

**C · FAIL.** The claim covers "turns nobody ever finishes". Half the cancels I performed left
nothing to reconstruct, and the service logs that outcome as a known, deferred gap.

---

### D · killed — **FAIL**

I sent a long-output turn through the UI, confirmed streaming had started (stop button present after
52 ms), and killed the container mid-stream.

```
01:03:56.72  streaming started (UI stop control present)
01:04:15.05  $ docker kill infra-chat-service-1
01:04:15.57  infra-chat-service-1
01:04:31.27  Application startup complete.   (service back)
01:04:37     health: healthy
```

Brought it back and waited. **Nothing was ever recorded.**
```sql
SELECT sequence_num, role, outcome, length(content), created_at
FROM chat_messages WHERE session_id='019fca3d-…' AND sequence_num>=12 ORDER BY sequence_num;
-- 12|user|NULL|67
-- 13|assistant|abandoned_by_user|264
-- 14|user|NULL|117          <- the killed turn's question
-- (no seq 15)
```
Checked again at 01:06:55 — 2.5 minutes after the service was healthy — still no seq 15. No
`chat_suspended_runs` row for this session. No `crashed` outcome. Reloading the session in the
browser shows the user's question and nothing after it.

The brief's requirement for D is: *"the turn does not sit forever in a non-terminal state with
nothing recorded."* It does exactly that. **D · FAIL.**

For completeness: the DB does contain one `crashed` row —
`c73b6322-0ae1-453c-92ba-9fe26211e2cd`, session `019fca25-…`, `finish_reason='streaming'`, 0 chars,
`00:21:34`. That session is **round 1's** D2 run, not mine. So `crashed` is reachable when the run
was checkpointed before the kill; my un-checkpointed kill reached nothing. Round 1 recorded this as
"PASS, with a hole (D2)". I drove straight into the hole, and on this build it is not closed — which
is why I score D as FAIL rather than as a caveat: a kill that happens to land before a checkpoint is
not an exotic case, it is the ordinary one.

---

## 6. Out of scope — things I saw that CP-0 did not ask about

**O1 — the log claims an `outcome=crashed` save on turns that completed successfully.**
*Out of CP-0's scope but directly about the trustworthiness of the outcome field.* On both run A and
run B — normal turns the user watched succeed — the service logged, twice each:
```
00:48:24.994  terminal-persist: saved streaming assistant reply … (msg b3fe8e50-…, 0 chars, outcome=crashed, runtime=legacy)
00:48:30.754  terminal-persist: saved streaming assistant reply … (msg b3fe8e50-…, 0 chars, outcome=crashed, runtime=legacy)
00:53:12.147  terminal-persist: saved streaming assistant reply … (msg 7882d01a-…, 0 chars, outcome=crashed, runtime=legacy)
00:53:21.171  terminal-persist: saved streaming assistant reply … (msg 7882d01a-…, 0 chars, outcome=crashed, runtime=legacy)
```
Both messages are `outcome='completed'` with 694 and 60 chars in the database. So the log says
"saved … outcome=crashed, 0 chars" for turns that are recorded completed. Either the write was a
no-op and the log over-claims, or it wrote and was overwritten. **I am reporting the contradiction,
not resolving it** — resolving it would mean reading the builder's code, which this brief forbids
me. An operator triaging from logs would conclude two healthy turns crashed.

**O2 — `runtime_variant` is `'legacy'` on every row I produced.** All 14. The column admits
`'agentruntime'`, and nothing I could reach through the normal UI produced it. I cannot tell from
the running system whether that is expected at CP-0 or whether the new runtime is simply not on this
path. **Reporting as an ambiguity**, per the brief's instruction not to resolve one by reading notes.

**O3 — the chat session never bound to the throwaway book.** I created
`CP0-VLIVE-R2-THROWAWAY` per the standing rule, but the new-chat dialog offers a model and a
quick-start persona, not a book, and `chat_suspended_runs.book_id` was never exercised. So the rule
was honoured (nothing was written into a content book), but there was no UI path by which a chat
turn attaches to a specific book from the chat surface. Noted as an observation about the surface,
not a CP-0 defect.

**O4 — `withheld_tools` is `NULL`, not `[]`, on turns where nothing was withheld** (seq 6, 9, 11,
13). Those turns advertised 24–30 of ~310 existing tools. Whether the un-advertised remainder is
"withheld" or merely "lazily not loaded" is a modelling question the record does not answer, and
`NULL` reads the same as "we did not look". **Ambiguity, reported not resolved.**

---

## 7. What could not be performed

Nothing. All four runs were performed through the real UI against the correct build. Runs C and D
failed on their merits, not for want of a way to drive them — which is itself the point: the
observability gap is in the record, not in my access to it.

---

## 8. Summary of raw artefacts

| item | value |
|---|---|
| commit under test | `e75ad5d7d` (container tree-hash verified identical to repo) |
| throwaway book | `CP0-VLIVE-R2-THROWAWAY` / `019fca3c-97a2-7182-a5b3-42b493c17a89` |
| session | `019fca3d-a8ba-7d88-84d5-549560835891` |
| run A message | `b3fe8e50-4f3f-406c-a8b6-7a62b0507256` — 4 passes, 28 withheld, 2 calls, `completed` |
| run B message | `7882d01a-b0a4-4302-9ba5-847b57cb3a2b` — 3 passes, 303 withheld, 2 calls, `completed` |
| run C-1 | seq 7 — **no assistant row**; log names `451a02b9-3539-44e7-8b84-7fa143ea1460`, absent from DB |
| run C-2 message | `cc526581-dd6e-4b79-9339-82767deafe8b` — `abandoned_by_user` / `interrupted`, 264 chars |
| run D | seq 14 — **no assistant row**, 2.5 min after service healthy |
| database | `loreweave_chat` in `infra-postgres-1`, user `loreweave` |

No fixes are proposed, per the brief.
