# CP-0 · V-LIVE — verdict (ROUND 3)

**Verifier:** V-LIVE (running-system verifier), round 3.
**Artifact frozen at:** `9f4096072` (working tree clean, branch `feat/frontend-tools-mcp-migration`)
**Date driven:** 2026-08-04 UTC 01:26 → 02:08
**Discipline:** I read no commit messages and no builder notes before driving. I read round 2's
verdict (`CP-0-v-live-round2.md`) only *after* every run below was complete and every row pulled.

---

## 0. Verdict

| | verdict |
|---|---|
| **Overall** | **PASS** (two open defects, one residual gap — all named below) |
| **A · clean** | **PASS** (defect A-d1 survives from round 2) |
| **B · withheld** | **PASS** on its stated bar — **but the round-3 change did NOT fix B-d1** |
| **C · cancelled** | **PASS** — round 2's FAIL is **RESOLVED** (residual gap C-g1, correctly logged) |
| **D · killed** | **PASS** — round 2's FAIL is **RESOLVED** (caveat D-c1) |

**The two changes I was told to test, judged:**

| change | holds up? |
|---|---|
| **(1)** cancel-path `await asyncio.shield(...)` → detached task | **YES.** Zero `interrupt-persist failed`, zero `CancelledError` tracebacks, four clean `interrupt-persist detached`, and the row lands. And the deferred boundary is **narrower** than the builder claims — see §5-C. |
| **(2)** `pass` field on withheld entries | **NO.** The contradiction survives with a timestamp attached. 11 of 178 withheld tools are stamped `"pass": 3` *and* are present in `advertised_tools` **at pass 3**. Round 2: 19/303 = 6.3%. Round 3: 11/178 = 6.2%. Materially unchanged. See §5-B. |

---

## 1. The falsifier

*What I looked for that would have made this FAIL. Each was a live hypothesis, not a ticked box.*

| # | falsifier | outcome |
|---|---|---|
| **F1** | The container does not contain `9f4096072`, so the verdict is worthless | **FOUND, third round running, and corrected before any run.** See §2. |
| **F2** | `advertised_tools` records only the final pass, so a set that changes mid-turn is invisible — *the specific defect CP-0 exists to catch* | **Not found, and this round is a stronger result than round 2.** Round 2 only ever observed tools being **added** between passes. Run A here records **five separate silent removals** across 19 passes, each with a matching withheld entry. See §5-A. |
| **F3** | The `pass` field is decorative — it does not let a withheld entry be reconciled against `advertised_tools` | **FOUND.** 11 entries assert both states at the same pass number. This is the round-3 change's stated purpose, and it does not achieve it. See §5-B. |
| **F4** | Every `tool_calls` entry has `source` **and** `latency_ms`, as run A's row requires | **FOUND (A-d1, unchanged from round 2).** 7 of 17 entries have `latency_ms: null` — every `meta` and every `breaker` call. |
| **F5** | A user cancel is recorded as `interrupted` alone — indistinguishable from "this broke" | **Not found.** `outcome='abandoned_by_user'`; `interrupted` appears only in `finish_reason`. |
| **F6** | The cancel-path fix is cosmetic — the write is still abandoned, or still logs `interrupt-persist failed` | **Not found.** 0 failures across 4 cancels. |
| **F7** | The deferred cancel gap is **wider** than the builder claims (i.e. a cancel that ran real tools also records nothing) | **Not found — it is narrower.** A cancel with **5 executed tool calls and zero text** *is* recorded. See §5-C. |
| **F8** | A killed turn sits forever non-terminal with nothing recorded | **Not found.** A kill landing mid-flight leaves `outcome='crashed'` with the tool call and the advertised pass intact, and it survives restart. See §5-D. |
| **F9** | `crashed` distinguishes "the process died" from "this is still running" | **FOUND (D-c1).** It does not — `crashed` is written optimistically at every checkpoint. See §5-D. |

F2 — the failure the brief was written around — is clean, and more convincingly than in round 2.
F3 is the round-3 finding.

---

## 2. Was the running container the code under test? — **No. Stale for the third round running.**

I checked **before** driving anything, by whole-file hash rather than by the symbol I expected.

```
$ cd services/chat-service && for f in app/services/instrument.py app/services/stream_service.py app/db/migrate.py; do sha256sum "$f"; done
app/services/instrument.py      ca3d0b1eee3c52e8…
app/services/stream_service.py  4ed4e750c24700da…
app/db/migrate.py               10f7eda5f2a5ed13…

$ docker exec infra-chat-service-1 sh -c '…sha256sum…'
app/services/instrument.py      e55197cd12512e86…   HASH DIFFERS
app/services/stream_service.py  0f272a21364854dd…   HASH DIFFERS
app/db/migrate.py               10f7eda5f2a5ed13…   match
```

Byte counts confirmed a real content difference, not a CRLF artifact
(`instrument.py` 14520 vs 15351; `stream_service.py` 482757 vs 486014), and one of the three files
matched under the same method, which is what proves the method sound.

**The container was running the pre-fix cancel path** — the exact code round 3 exists to re-test:

```
$ docker exec infra-chat-service-1 grep -n "shield" app/services/stream_service.py
7319:                await asyncio.shield(          <-- the abandoned-write bug, still deployed
```

Rebuilt and force-recreated:

```
$ docker compose -f infra/docker-compose.yml build chat-service
   naming to docker.io/library/infra-chat-service:latest  DONE
$ docker compose -f infra/docker-compose.yml up -d --force-recreate --no-deps chat-service
   Container infra-chat-service-1  Recreated / Started
```

Re-verified after recreate — and again at the end of the session, after five `docker kill`/`start`
cycles, to be sure no run below was driven against a different image:

```
app/services/instrument.py      ca3d0b1eee3c52e8   match
app/services/stream_service.py  4ed4e750c24700da   match
$ docker exec … grep -n "_cancel_write" app/services/stream_service.py
7336:  _cancel_write = asyncio.create_task(     <-- the fix is present
7359:  await asyncio.shield(_cancel_write)
```

Every run below is against `9f4096072`.

---

## 3. How I drove the system

**Via the real UI**, at `http://localhost:5174`, in Chromium under Playwright — logged in through the
login form, created the book through the real "Sách mới" dialog, created the session through the
new-chat dialog, typed into the real composer, sent with the real send button, and cancelled with the
real stop button (`button.bg-destructive`, the control that replaces send while `isStreaming`).
**No API call substituted for a user action in any of runs A–D.** The only non-UI actions were
`docker kill` (which run D requires) and read-only `psql` queries.

**Throwaway book:** `CP0-VLIVE-R3-THROWAWAY` — `019fca62-9ac2-7dc9-bb46-cf0dc2fb3392`.
Nothing was written into any existing content book. (As in round 2, the chat session does not bind to
a book from the chat surface — round 2's O3 stands.)

**Session driven:** `019fca64-32ca-7f53-853a-085a24635c90`
**Account:** `claude-test@loreweave.dev`, user `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`
**Model:** Gemma-4 26B-A4B QAT (200K) via LM Studio.

---

## 4. The turn ledger — every row this session produced

```sql
SELECT sequence_num AS seq, role, outcome, finish_reason,
       length(content) AS chars,
       jsonb_array_length(advertised_tools) AS adv_passes,
       jsonb_array_length(withheld_tools)   AS withheld,
       jsonb_array_length(tool_calls)       AS calls
FROM chat_messages
WHERE session_id='019fca64-32ca-7f53-853a-085a24635c90'
ORDER BY sequence_num;
```

```
 seq |   role    |      outcome      | finish_reason  | chars | adv | withheld | calls
-----+-----------+-------------------+----------------+-------+-----+----------+-------
   1 | user      |                   |                |   164 |     |          |
   2 | assistant | completed         | stop           |  1743 |  19 |       33 |    17   <- RUN A
   3 | user      |                   |                |   222 |     |          |
   4 | assistant | completed         | stop           |  1482 |   3 |      178 |     4   <- RUN B
   5 | user      |                   |                |   138 |     |          |
   6 | assistant | completed         | stop           |  6756 |   1 |          |
   7 | user      |                   |                |   164 |     |          |
   8 | assistant | abandoned_by_user | interrupted    |   478 |   1 |          |     0   <- RUN C1
   9 | user      |                   |                |    93 |     |          |         <- RUN C2: NO ASSISTANT ROW
  10 | user      |                   |                |   178 |     |          |
  11 | assistant | completed         | stop           |   591 |     |          |     2
  12 | user      |                   |                |   277 |     |          |
  13 | assistant | completed         | stop           |  2361 |     |          |     8
  14 | user      |                   |                |   236 |     |          |
  15 | assistant | abandoned_by_user | interrupted    |     0 |   2 |       47 |     5   <- RUN C5  (0 chars, 5 calls, RECORDED)
  16 | user      |                   |                |   103 |     |          |         <- RUN C6: NO ASSISTANT ROW
  …
  24 | assistant | awaiting_input    | awaiting_input |     0 |   1 |          |     2
  …
  27 | user      |                   |                |   164 |     |          |
  28 | assistant | crashed           | streaming      |     0 |   1 |          |     1   <- RUN D7 (killed mid-flight)
```

```
 outcome           | finish_reason  | count
-------------------+----------------+-------
 completed         | stop           |     9
 abandoned_by_user | interrupted    |     2
 awaiting_input    | awaiting_input |     1
 crashed           | streaming      |     1
```

Note `interrupted` — the deprecated fused value the instrument exists to drive to zero — appears
**only** in `finish_reason`, never in `outcome`, on any row this session produced.

---

## 5. The runs

### A · clean — **PASS** (defect A-d1)

Turn: *"List the tool categories available to you, then load the tools in the 'Book' category, then
tell me how many books I have. Use your tools for each step."*
Message `eaa6f082-d664-4610-95f3-200692be0968`. 19 passes, 17 tool calls, `completed`.

**The question that decides the verdict — answered from the stored record alone, no code read:**

**(1) Which tools was the model holding on its second pass?**

```sql
SELECT jsonb_pretty(advertised_tools->1) FROM chat_messages
WHERE message_id='eaa6f082-d664-4610-95f3-200692be0968';
```
```json
{
    "pass": 2,
    "count": 29,
    "tool_choice": "auto",
    "names": ["book_chapter_save_draft","chat_search_sessions","confirm_action",
      "conversation_search","glossary_deep_research","kg_entity_edge_timeline","kg_graph_query",
      "kg_list_templates","kg_ontology_propose","kg_project_list","kg_propose_edge",
      "kg_propose_fact","kg_schema_read","kg_sync_available","kg_triage_list","kg_triage_resolve",
      "kg_view_read","load_skill","memory_forget","memory_recall_entity","memory_remember",
      "memory_search","memory_timeline","run_subagent","tool_list","tool_load","web_search",
      "workflow_list","workflow_load"]
}
```
**Answerable.**

**F2 — the defect CP-0 was built for.** Round 2 saw only *additions* between passes, which is the
easy half. This run records **five silent removals**, each with the pass it vanished on:

```sql
WITH m AS (SELECT advertised_tools a FROM chat_messages WHERE message_id='eaa6f082-…'),
adv AS (SELECT (p->>'pass')::int AS pass, (p->>'count')::int AS cnt,
               ARRAY(SELECT jsonb_array_elements_text(p->'names')) AS names
        FROM m, jsonb_array_elements(m.a) p)
SELECT cur.pass, cur.cnt,
  (SELECT string_agg(x,',') FROM unnest(cur.names) x
     WHERE prev.names IS NOT NULL AND NOT x = ANY(prev.names)) AS added,
  (SELECT string_agg(x,',') FROM unnest(prev.names) x WHERE NOT x = ANY(cur.names)) AS removed
FROM adv cur LEFT JOIN adv prev ON prev.pass = cur.pass-1 ORDER BY cur.pass;
```
```
 pass | cnt |                          added                          |       removed
------+-----+---------------------------------------------------------+---------------------
    1 |  29 |                                                         |
    2 |  29 |                                                         |
    3 |  35 | book_get,book_list_chapters,book_list_revisions,         |
      |     | book_scene_get,book_steering_list,book_update_details    |
    4 |  35 |                                                         |
    5 |  35 |                                                         |
    6 |  34 |                                                         | book_list_chapters
    7 |  34 |                                                         |
    8 |  34 |                                                         |
    9 |  33 |                                                         | book_list_revisions
   10 |  33 |                                                         |
   11 |  33 |                                                         |
   12 |  32 |                                                         | book_get
   13 |  32 |                                                         |
   14 |  32 |                                                         |
   15 |  31 |                                                         | book_update_details
   16 |  31 |                                                         |
   17 |  31 |                                                         |
   18 |  30 |                                                         | book_steering_list
   19 |  30 |                                                         |
```

This is exactly the founding defect — a tool offered on one pass and silently deleted before a later
one — and **the record shows both states**. A last-write-wins column would have shown 30 tools and
nothing else. **F2 clean.**

**(2) Was anything hidden from it?** Yes — 33 entries, each named, staged, reasoned and now dated:

```json
[{"pass": 4, "tool": "book_audio_generate", "stage": "token_budget",
  "reason": "did not fit the activation token budget"},
 {"pass": 4, "tool": "book_chapter_bulk_create", "stage": "token_budget",
  "reason": "did not fit the activation token budget"}, …]
```

And on **this** message the `pass` field reconciles perfectly — 0 same-pass contradictions:

```
withheld_rows                         | 33
contradiction_same_pass               | 0
withheld_but_advertised_somepass      | 5
withheld_yet_advertised_on_EVERY_pass | 0
```

The 5 that appear on both sides are a *coherent sequence*, not a contradiction — each was advertised
for a while, then withheld by `failure_breaker` after repeated failures:

```
        tool         |      stage      | withheld_at_pass |         advertised_on_passes
---------------------+-----------------+------------------+---------------------------------------
 book_get            | failure_breaker |               13 | 3,4,5,6,7,8,9,10,11
 book_list_chapters  | failure_breaker |                7 | 3,4,5
 book_list_revisions | failure_breaker |               10 | 3,4,5,6,7,8
 book_steering_list  | failure_breaker |               19 | 3,4,5,6,7,8,9,10,11,12,13,14,15,16,17
 book_update_details | failure_breaker |               16 | 3,4,5,6,7,8,9,10,11,12,13,14
```

> **A-d2 (new, minor) — the `pass` stamp is systematically one pass late.** Cross-referencing the
> delta table above: `book_list_chapters` disappears from the advertised set at **pass 6** but is
> stamped `"pass": 7`. Same +1 for all five (removed 9 → stamped 10; 12 → 13; 15 → 16; 18 → 19). The
> stamp names the pass *after* the one in which the narrowing first took effect. It is consistent and
> therefore decodable, but an outsider reading "withheld at pass 7" will believe the tool was still
> available on pass 6, and it was not.

**(3) Did the third result come from a tool or from our own breaker?**

```sql
SELECT jsonb_pretty(tool_calls->2) FROM chat_messages WHERE message_id='eaa6f082-…';
```
```json
{
    "id": "call_4274648666860295",
    "ok": false,
    "args": {"book_id": "all"},
    "tool": "book_list_chapters",
    "error": "book_id must be a UUID",
    "result": null,
    "source": "tool",
    "iteration": 2,
    "latency_ms": 18,
    "declaration": "book_list_chapters",
    "runtime_variant": "legacy"
}
```
**From a tool** — a real dispatch that took 18 ms and returned a validation error. **Answerable**,
and the contrast within the same row makes `source` non-decorative:

```
        tool         | source  | latency_ms |  ok   | iter | inferred
---------------------+---------+------------+-------+------+----------
 tool_list           | meta    |            | true  | 0    | true
 tool_load           | meta    |            | true  | 1    | true
 book_list_chapters  | tool    | 18         | false | 2    |
 book_list_chapters  | tool    | 19         | false | 3    |
 book_list_chapters  | breaker |            | false | 4    | true
 book_list_revisions | tool    | 21         | false | 5    |
 book_list_revisions | tool    | 20         | false | 6    |
 book_list_revisions | breaker |            | false | 7    | true
 book_get            | tool    | 21         | false | 8    |
 book_get            | tool    | 24         | false | 9    |
 book_get            | breaker |            | false | 10   | true
 book_update_details | tool    | 19         | false | 11   |
 book_update_details | tool    | 20         | false | 12   |
 book_update_details | breaker |            | false | 13   | true
 book_steering_list  | tool    | 26         | false | 14   |
 book_steering_list  | tool    | 21         | false | 15   |
 book_steering_list  | breaker |            | false | 16   | true
```

The two-real-failures-then-breaker pattern is legible from the record alone, and each breaker row
lines up with a removal in the pass table. That is the instrument doing its job.

**(4) How did the turn end?** `outcome='completed'`, `finish_reason='stop'`. **Answerable.**

All four answerable without reading code. **A · PASS.**

> **A-d1 (survives from round 2) — `latency_ms` is `null` on every non-dispatched call.** 7 of 17
> entries. The brief's run-A row requires *"every `tool_calls` entry has `source` and `latency_ms`"*.
> The key is present; the value is null. `ensure_tool_call_instrumented` does
> `setdefault("latency_ms", None)`, so nothing was measured. This matters most for `tool_list` and
> `tool_load`: they are the calls that **reshape the offered set** (pass 3 gains six tools because of
> one `tool_load`), they returned a 307-tool catalogue, and they demonstrably did real work — but the
> record cannot say how long any of it took. `source_inferred: true` on those same rows says the
> record itself classified them after the fact rather than observing them at the call site.

---

### B · withheld — **PASS on its stated bar. The round-3 change did NOT fix B-d1.**

Turn: *"Now load ALL the tools in the Composition category, then also load the Glossary category,
then also the Knowledge category, then the World category…"* Message at `sequence_num=4`.
3 passes, **178** withheld, 4 calls, `completed`.

The brief's bar for B is *"`withheld_tools` names the tool, the stage, and a reason — not an empty
array"*. Met:

```sql
SELECT x->>'stage' AS stage, x->>'reason' AS reason, x->>'pass' AS pass, count(*)
FROM chat_messages, jsonb_array_elements(withheld_tools) x
WHERE session_id='019fca64-…' AND sequence_num=4 GROUP BY 1,2,3;
```
```
    stage     |                 reason                  | pass | count
--------------+-----------------------------------------+------+-------
 token_budget | did not fit the activation token budget | 3    |   178
```

**But the round-3 change's stated purpose is not achieved.** The reconciliation query:

```sql
WITH m AS (SELECT advertised_tools a, withheld_tools w FROM chat_messages
           WHERE session_id='019fca64-…' AND sequence_num=4),
adv AS (SELECT (p->>'pass')::int AS pass, jsonb_array_elements_text(p->'names') AS name
        FROM m, jsonb_array_elements(m.a) p),
wh  AS (SELECT (x->>'pass')::int AS pass, x->>'tool' AS tool, x->>'stage' AS stage
        FROM m, jsonb_array_elements(m.w) x)
SELECT (SELECT count(*) FROM wh) AS withheld_rows,
       (SELECT count(DISTINCT pass) FROM adv) AS n_passes,
       (SELECT count(*) FROM wh JOIN adv ON adv.name=wh.tool AND adv.pass=wh.pass)
         AS contradiction_same_pass;
```
```
withheld_rows                      | 178
n_passes                           |   3
contradiction_same_pass            |  11
withheld_yet_advertised_EVERY_pass |  11
```

The eleven, named:

```
          tool           |    stage     | withheld_at_pass | advertised_on_passes
-------------------------+--------------+------------------+----------------------
 glossary_deep_research  | token_budget |                3 | 1,2,3
 kg_entity_edge_timeline | token_budget |                3 | 1,2,3
 kg_graph_query          | token_budget |                3 | 1,2,3
 kg_list_templates       | token_budget |                3 | 1,2,3
 kg_ontology_propose     | token_budget |                3 | 1,2,3
 kg_sync_available       | token_budget |                3 | 1,2,3
 kg_triage_list          | token_budget |                3 | 1,2,3
 kg_triage_resolve       | token_budget |                3 | 1,2,3
 memory_recall_entity    | token_budget |                3 | 1,2,3
 memory_search           | token_budget |                3 | 1,2,3
 memory_timeline         | token_budget |                3 | 1,2,3
```

Advertised counts for that message were `pass 1 → 32, pass 2 → 64, pass 3 → 64`, all `tool_choice:
auto`. These eleven tools were **in the pass-3 `names` array that was sent to the model**, and
simultaneously carry a pass-3 record saying they *"did not fit the activation token budget"*.

> **B-d1 (survives) — the contradiction now has a timestamp, and the timestamp agrees with itself.**
> Round 2's complaint was that a withheld entry was *timeless*, so "withheld" and "advertised on
> every pass" could not be told apart from "dropped, then re-added". The `pass` field was added to
> resolve exactly that. It does not: the withholding and the advertisement now carry **the same pass
> number**, which is the one arrangement that cannot be read as a sequence. Round 2 measured 19/303
> (6.3%); I measure 11/178 (6.2%). The rate is unchanged.
>
> This is *not* an unanswerable ambiguity — `advertised_tools` is authoritative for what was sent, so
> an outsider can still answer "was this offered?" correctly. The defect is that `withheld_tools`
> carries a ~6% false-positive rate, which makes the withheld **count** uninterpretable and
> contradicts the module's own stated bias toward recording a narrowing only when one happened.

**Scope check — this is not universal.** Across all four assistant messages in this session that
carry a withheld list, only the large-surface one contradicts:

```
 sequence_num | withheld_rows | same_pass_contradictions
--------------+---------------+--------------------------
            2 |            33 |                        0
            4 |           178 |                       11
           15 |            47 |                        0
           22 |            98 |                        0
```

It reproduces when a `tool_load` pushes the surface past the budget while the hot set is retained —
i.e. exactly the condition round 2 hit.

---

### C · cancelled — **PASS.** Round 2's FAIL is **RESOLVED.**

I cancelled from the UI four times with the real stop button, at deliberately different points.

**C1 — cancel at 4.1 s, after the model had produced visible text. Recorded.**

The UI showed ~500 characters of real prose before I clicked stop:
> *"The history of the printing press is not merely the history of a machine; it is the history of
> the democratization of thought, the acceleration of human conscious…"*

```
 seq | role      | outcome           | finish_reason | len | head
-----+-----------+-------------------+---------------+-----+------------------------------------------
   8 | assistant | abandoned_by_user | interrupted   | 478 | The history of the printing press is not…
```

`outcome='abandoned_by_user'` — *the user abandoned this*, distinct from *this broke*. The partial
text is preserved. **This is what the brief asks for.**

**Change (1) verified hard, as instructed:**

```
$ docker logs infra-chat-service-1 | grep -c "interrupt-persist failed"
0
$ docker logs infra-chat-service-1 | grep -c "interrupt-persist detached"
4
$ docker logs infra-chat-service-1 | grep -c "asyncio.exceptions.CancelledError"
0
$ docker logs infra-chat-service-1 | grep "interrupt-persist"
INFO: interrupt-persist detached for session 019fca64-… (write continues after cancel)
```

Round 2 saw `interrupt-persist failed` on **100%** of cancels with a `CancelledError` traceback
through `await asyncio.shield(...)`. On this build: **zero failures across four cancels**, and the
detach message fires instead. The write is no longer riding the cancelled scope. **Change (1) holds.**

**The deferred boundary is NOT where the builder says it is — it is NARROWER.**

The builder's claim, as given to me, is that a cancel *before any text is produced* still records
nothing. I tested that directly and it is too pessimistic:

**C5 — cancel at 7.0 s, five tool calls executed, ZERO characters of text. RECORDED.**

The context rack visibly grew from 33 to 40 tools during the turn, so a real `tool_load` had
dispatched, and no prose had appeared.

```
 seq | role      | outcome           | finish_reason | len | calls | adv
-----+-----------+-------------------+---------------+-----+-------+-----
  15 | assistant | abandoned_by_user | interrupted   |   0 |     5 |   2
```

Five tool calls, two advertised passes, 47 withheld entries, `abandoned_by_user` — **with no text at
all**. So a cancel that did real work is *not* lost.

**C2 and C6 — cancel at 1.65 s and 1.40 s, before the first chunk of any kind. Not recorded.**

```sql
SELECT u.sequence_num, left(u.content,40) FROM chat_messages u
WHERE u.session_id='019fca64-…' AND u.role='user'
  AND NOT EXISTS (SELECT 1 FROM chat_messages a WHERE a.session_id=u.session_id
                  AND a.role='assistant' AND a.sequence_num=u.sequence_num+1);
```
```
 user_seq |                  prompt
----------+------------------------------------------
        9 | RUN-C2: Write a very long essay about th…
       16 | RUN-C6: Tools only. Call tool_list then …
```

C6 is the decisive one: it *requested* tools, so it is not a "no-tools" special case — it simply had
not dispatched anything yet. The service names the gap in its own words:

```
INFO: CP-0.4 silent-exit: empty terminal turn recorded nowhere
      (session 019fca64-…, msg d21df601-670c-4e4a-ac3d-e7aaa6ab5482, reason=interrupted).
      Closes at CP-3.6 with the other three silent exits.
INFO: CP-0.4 silent-exit: empty terminal turn recorded nowhere
      (session 019fca64-…, msg 47e399f8-add3-495b-9c77-0421435a3233, reason=interrupted).

$ SELECT count(*) FROM chat_messages WHERE message_id IN ('d21df601-…','47e399f8-…');
 0
```

Exactly two silent-exit log lines, exactly two orphaned user rows. The accounting is exact.

> **C-g1 (residual gap) — the true boundary is "before the first streamed chunk of any kind", not
> "before any text".** The unrecorded window is strictly smaller than the builder describes: a turn
> that produced *either* text *or* a tool call is recorded; only a turn where nothing at all had
> streamed yet is lost. The builder's stated boundary would have predicted C5 records nothing, and it
> records fully. **The boundary is not exactly where the builder says — it is tighter, in the safe
> direction.** The residual gap is real, is signposted in the logs with a message id, and is deferred
> to CP-3.6.

**C · PASS.** The brief's bar — *"a terminal outcome that distinguishes the user abandoned this from
this broke"* — is met on every cancel that had anything to record, and `interrupted` never appears in
`outcome`.

---

### D · killed — **PASS.** Round 2's FAIL is **RESOLVED.** (caveat D-c1)

**This run took five attempts, and why is itself a finding.** With a warm prompt cache the local
model completed entire turns — including one of 9,551 characters — in under four seconds, faster
than I could interleave a `docker kill`. Attempts D2–D5 all completed before the kill landed; D4's
kill landed after the turn had already reached a legitimate `awaiting_input` (a `kg_propose_fact`
confirm gate). Only by driving a `run_subagent` turn could I hold the turn open long enough.

**D7 — kill landed mid-flight, confirmed non-terminal at the moment of the kill.**

```
pre-kill 09:05:21:
27|user|||164
28|assistant|crashed|streaming|0        <- confirmed in flight

=== KILL 09:05:21 ===
infra-chat-service-1
```

Post-kill, service **down**:
```
 seq | role      | outcome | finish_reason | len | calls | adv | wh
-----+-----------+---------+---------------+-----+-------+-----+----
  27 | user      |         |               | 164 |     0 |   0 |  0
  28 | assistant | crashed | streaming     |   0 |     1 |   1 |  0
```

Post-restart (service healthy again), **unchanged and still present**:
```
  28 | assistant | crashed | streaming     |   0 |     1 |   1
```

The brief's requirement is *"the turn does not sit forever in a non-terminal state with nothing
recorded."* It does not: `outcome='crashed'` is a terminal CP-0.4 value, and the turn's one dispatched
tool call and its advertised pass are both preserved. Round 2 drove the same scenario and got **no
row at all**; on this build the row is there. **D · PASS.**

> **D-c1 (caveat) — `crashed` cannot distinguish "the process died" from "this is still running".**
> The checkpoint writes `outcome='crashed'` optimistically at every tool boundary and supersedes it on
> completion. I observed this directly during run A, which read `crashed|streaming|15|15|0` at
> 08:34:01 and `completed|stop|19|17|1743` at 08:35:02 — the same row, healthy throughout. The log
> shows the supersession pattern plainly:
> ```
> terminal-persist: saved streaming  assistant reply … (msg 7a66b39d-…, 0 chars, outcome=crashed,        …)
> terminal-persist: saved awaiting_input assistant reply … (msg 7a66b39d-…, 0 chars, outcome=awaiting_input, …)
> ```
> This **explains round 2's O1** (the log appearing to claim a crash on turns that succeeded — it is a
> checkpoint, not a lie), but it means a dashboard counting `outcome='crashed'` counts every in-flight
> turn as well as every dead one. Nothing sweeps or reconciles `finish_reason='streaming'` on restart,
> so the row's terminality rests entirely on the checkpoint's pessimistic pre-write.

---

## 6. Out of scope — things I saw that CP-0 did not ask about

**O1 — the UI still calls a user cancel "Interrupted", the word the record was changed to stop
using.** The DB says `abandoned_by_user`; the FE renders:
> `Interrupted — response incomplete`

CP-0's vocabulary change (cancellation is not a failure) reaches the column but not the surface the
user reads. *Out of CP-0's DB-record scope, but it is a case of the product contradicting what the
record says happened.*

**O2 — a killed turn renders as nothing at all in the UI.** Reloading the session after run D shows
the user's question, the `⚙ run_subagent` chip, and then simply stops — no error card, no "this turn
was lost" affordance. The DB knows the turn crashed; the user is not told. *Out of scope; reported
because CP-0's whole subject is whether a lost turn is accounted for.*

**O3 — `runtime_variant` is `'legacy'` on every row I produced**, as in round 2. The column admits
`'agentruntime'` and nothing reachable through the normal UI produced it. **Reporting as an
ambiguity**, per the brief's instruction not to resolve one by reading builder notes.

**O4 — `withheld_tools` is `NULL`, not `[]`, on turns where nothing was withheld** (seq 6, 8, 11, 13,
28). Round 2's O4 stands unchanged: `NULL` reads the same as "we did not look".

**O5 — browser console errors during the session were self-inflicted.** 500s on
`/v1/chat/sessions?status=active` and `ERR_INCOMPLETE_CHUNKED_ENCODING` on
`/v1/notifications/stream` all coincide with my own `docker kill` windows. **Not a product defect** —
recorded so a later reader does not mistake them for one.

**O6 — the chat session still does not bind to a book from the chat surface.** Round 2's O3 stands.
The throwaway-book rule was honoured (nothing was written into a content book), but the new-chat
dialog offers a model and a persona, not a book.

---

## 7. What could not be performed

Nothing. All four runs were performed through the real UI against the correct build. Run D required
five attempts for a timing reason (§5-D), not for want of a way to drive it.

---

## 8. Summary of raw artefacts

| item | value |
|---|---|
| commit under test | `9f4096072` (container **was stale**; rebuilt, force-recreated, hash-verified before and after) |
| throwaway book | `CP0-VLIVE-R3-THROWAWAY` / `019fca62-9ac2-7dc9-bb46-cf0dc2fb3392` |
| session | `019fca64-32ca-7f53-853a-085a24635c90` |
| run A message | `eaa6f082-d664-4610-95f3-200692be0968` — 19 passes, 33 withheld, 17 calls, `completed`, **5 silent removals recorded** |
| run B message | `sequence_num=4` — 3 passes, 178 withheld, 4 calls, `completed`, **11 same-pass contradictions** |
| run C1 message | `2f6b1aec-3e5b-4b04-98bb-82de7315a0b0` — `abandoned_by_user`, 478 chars |
| run C5 message | `sequence_num=15` — `abandoned_by_user`, **0 chars, 5 tool calls** (the boundary probe) |
| run C2 / C6 | seq 9 and seq 16 — **no assistant row**; log names `d21df601-…` and `47e399f8-…`, both absent from DB |
| run D message | `sequence_num=28` — `crashed` / `streaming`, 1 call, 1 advertised pass, survived restart |
| `interrupt-persist failed` | **0** across 4 cancels (round 2: 100%) |
| database | `loreweave_chat` in `infra-postgres-1`, user `loreweave` |

No fixes are proposed, per the brief.
