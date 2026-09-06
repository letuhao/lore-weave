# CP-0 · V-LIVE — verdict

**Verifier:** V-LIVE (running-system verifier). Wrote no code, read no commit messages or builder
notes before driving the system.
**Date driven:** 2026-08-04 (UTC 2026-08-03T23:30 → 2026-08-04T00:25)

---

## 0. Verdict

| | verdict |
|---|---|
| **Overall** | **FAIL** |
| **A · clean** | **PASS** |
| **B · withheld** | **FAIL** |
| **C · cancelled** | **PASS** |
| **D · killed** | **PASS, with a hole** (see D2) |

**Why the overall is FAIL, in one sentence:** the instrument records everything it was built to
record *except* the one narrowing it was founded on — the token budgeter deleted **98 tools** from
one turn's offered set and **28** from another, and `withheld_tools` was `NULL` both times, while a
*different* narrowing (the repeated-failure breaker) recorded correctly on the same build. So the
column is wired and works; the budgeter's drops never reach it.

---

## 1. The falsifier

*What I looked for that would have made this FAIL. Each of these was a live hypothesis I went
looking for, not a box I ticked.*

| # | falsifier | outcome |
|---|---|---|
| F1 | `advertised_tools` records only the **last** pass (a scalar / last-write-wins shape), so a tool present on pass 1 and gone on pass 2 is invisible | **Not found.** It is a per-pass array. I built a turn (`24ace186`) whose offered set goes `27, 27, 27, 26` and the record shows **all four states**, and the diff of pass 3 → pass 4 is exactly `book_list`. |
| F2 | `withheld_tools` is an **empty array / NULL** on a turn where a narrowing demonstrably happened | **FOUND — twice.** See §3-B. This is the finding. |
| F3 | A user cancel is recorded as `interrupted` — i.e. indistinguishable from "this broke" | **Not found.** `outcome = 'abandoned_by_user'`. `interrupted` appears only in `finish_reason`, which is the provider's word, not ours. |
| F4 | A killed turn sits forever non-terminal with nothing recorded | **Not found in the checkpointed case** (`outcome = 'crashed'`, written *before* the container came back). **Found in the un-checkpointed case** — see D2. |
| F5 | `tool_calls[].source` is a decorative constant — everything says `"tool"` | **Not found.** I got three distinct values from real turns: `tool` (real dispatch), `meta` (runtime primitive: `tool_list`, `tool_load`), `breaker` (our own code answered, no tool ran). |
| F6 | The verdict is rendered against a **stale image** | **Actively checked and corrected before any run** — see §2. The container shipped 736-line `migrate.py` with **zero** occurrences of `advertised_tools`, and `loreweave_chat.chat_messages` had none of the four columns. I rebuilt and recreated. |

A `PASS` on F1/F3/F5 with a `FAIL` on F2 is not a wash: F2 is the *specific* failure the brief told
me to hunt ("a tool the model needed was silently deleted from the offered set mid-turn, and nothing
in production recorded it").

---

## 2. Was the running container actually the code under test? — **No, initially. I fixed it.**

The stack was up (containers `infra-*`), but `chat-service` had not been rebuilt. Verified
explicitly *before* driving anything:

```
$ docker exec infra-chat-service-1 sh -c "wc -l /app/app/db/migrate.py; grep -c 'advertised_tools' /app/app/db/migrate.py"
736 /app/app/db/migrate.py
0

$ (host) migrate.py = 744 lines

$ docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -c "\d chat_messages"
   ... no advertised_tools, no withheld_tools, no outcome, no runtime_variant ...
```

Rebuilt and force-recreated:

```
$ docker compose -f infra/docker-compose.yml build chat-service
   => naming to docker.io/library/infra-chat-service:latest  DONE
$ docker compose -f infra/docker-compose.yml up -d --force-recreate chat-service
   Container infra-chat-service-1  Started
```

Re-verified:

```
$ docker exec infra-chat-service-1 sh -c "grep -c 'advertised_tools' /app/app/db/migrate.py /app/app/services/stream_service.py"
/app/app/db/migrate.py:1
/app/app/services/stream_service.py:10

$ docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -c \
    "SELECT column_name,data_type FROM information_schema.columns WHERE table_name='chat_messages'
     AND column_name IN ('advertised_tools','withheld_tools','outcome','runtime_variant','tool_calls');"
   column_name    | data_type
------------------+-----------
 tool_calls       | jsonb
 advertised_tools | jsonb
 withheld_tools   | jsonb
 outcome          | text
 runtime_variant  | text
(5 rows)
```

Every row below was produced **after** this rebuild. `runtime_variant` reads `legacy` on all of
them, which is the honest label for this build.

---

## 3. The four runs

### How I drove it — §4 requires this up front

**UI, through a real browser** (Playwright driving `http://localhost:5174`), logged in through the
normal login form as the repo's dev-seed agent account `claude-test@loreweave.dev`. Every message
was typed into the real chat composer and sent with the real send button; the cancel in run C was
the real red stop button (`bg-destructive` + `lucide-square`) rendered by
`frontend/src/features/chat/components/ChatInputBar.tsx`. **No chat API was called directly.**

The only API calls I made were setup and read-back: registering a scratch account before I found the
seed account (see §5.4), and `psql` against `loreweave_chat` to read rows.

**Throwaway book:** `[THROWAWAY] CP-0 v-live 2026-08-04`, `book_id =
019fc9fd-4515-71b2-ab66-b4feed41d85f`, created through the UI's "Sách mới" dialog at the start of the
session. No existing content book was written to. The one write that happened (a chapter named
"CP0 Chapter One") landed in that throwaway book.

**Sessions used:**
- `019fc9fe-9888-7a56-8a48-3cb6466806fb` — runs A, B(budget), C
- `019fca22-ce9a-7b83-86a6-2a98db5fda97` — run D1 (kill before any checkpoint)
- `019fca25-4934-7c45-b00e-6b0532c56788` — run D2 (kill after a checkpoint), B(breaker)

**Model:** `google/gemma-4-26b-a4b-qat` via LM Studio (`lm_studio` BYOK, `user_model_id
019ebb72-27a2-72f3-a42d-d2d0e0ded179`), the account's default chat model.

---

### A · clean — **PASS**

Two turns qualify. The second is the interesting one because it produced three tool results of two
different provenances.

**A1** — "Step 1: call `book_list` … Step 2: call `book_read` on the book titled
`[THROWAWAY] CP-0 v-live 2026-08-04`…"

```sql
SELECT message_id, role, outcome, runtime_variant,
       jsonb_array_length(COALESCE(advertised_tools,'[]')) AS adv_passes,
       jsonb_array_length(COALESCE(tool_calls,'[]'))       AS tc_n
FROM chat_messages
WHERE session_id='019fc9fe-9888-7a56-8a48-3cb6466806fb' ORDER BY sequence_num;
```
```
-[ RECORD 3 ]---+------------------------------------------------
message_id      | 03e0ca0b-107b-41db-91fa-a8c30c2f348c
role            | assistant
content         | The book titled "[THROWAWAY] CP-0 v-live 2026-08-04" is in **English** (`en`) an…
is_error        | f
outcome         | completed
runtime_variant | legacy
adv_passes      | 3
tc_n            | 2
```

`advertised_tools` (abridged — full 30 names repeated identically for passes 1–3):

```sql
SELECT jsonb_pretty(advertised_tools) FROM chat_messages
WHERE message_id='03e0ca0b-107b-41db-91fa-a8c30c2f348c';
```
```json
[
    { "pass": 1, "count": 30, "tool_choice": "auto",
      "names": ["book_chapter_create","book_chapter_save_draft","book_list","book_read","book_search",
                "chat_search_sessions","confirm_action","conversation_search","glossary_deep_research",
                "kg_entity_edge_timeline","kg_graph_query","kg_list_templates","kg_ontology_propose",
                "kg_propose_edge","kg_propose_fact","kg_schema_read","kg_sync_available","kg_triage_list",
                "kg_triage_resolve","load_skill","memory_recall_entity","memory_remember","memory_search",
                "memory_timeline","run_subagent","tool_list","tool_load","web_search","workflow_list",
                "workflow_load"] },
    { "pass": 2, "count": 30, "tool_choice": "auto", "names": [ …identical 30… ] },
    { "pass": 3, "count": 30, "tool_choice": "auto", "names": [ …identical 30… ] }
]
```

`tool_calls`:

```sql
SELECT jsonb_pretty(jsonb_agg(jsonb_build_object(
         'tool',e->>'tool','source',e->>'source','latency_ms',e->'latency_ms',
         'iteration',e->'iteration','ok',e->'ok','declaration',e->'declaration',
         'runtime_variant',e->>'runtime_variant','args',e->'args',
         'result_prefix',left(e->>'result',180))))
FROM chat_messages m, jsonb_array_elements(m.tool_calls) e
WHERE m.message_id='03e0ca0b-107b-41db-91fa-a8c30c2f348c';
```
```json
[
    { "ok": true, "args": {"kind":"books"}, "tool": "book_list", "source": "tool",
      "iteration": 0, "latency_ms": 78, "declaration": "book_list", "runtime_variant": "legacy",
      "result_prefix": "{\"kind\": \"books\", \"page\": {\"total\": 188, … \"books\": [{\"title\": \"[THROWAWAY] CP-0 v-live 2026-" },
    { "ok": true, "args": {"book_id":"019fc9fd-4515-71b2-ab66-b4feed41d85f"}, "tool": "book_read",
      "source": "tool", "iteration": 1, "latency_ms": 71, "declaration": "book_read",
      "runtime_variant": "legacy",
      "result_prefix": "{\"book\": {\"title\": \"[THROWAWAY] CP-0 v-live 2026-08-04\", \"book_id\": \"019fc9fd-…" }
]
```

**A2** (`ba550c1b-ba5f-407f-a2a6-5cc7fd112bc5`) — "Do exactly three tool calls, in this order:
(1) `tool_list`, (2) `book_list`, (3) `book_read`…". Three results, two provenances:

```json
[
  {"tool":"tool_list","source":"meta","latency_ms":null,"has_latency_key":true,"iteration":0,
   "keys":["args","declaration","error","id","iteration","latency_ms","ok","result",
           "runtime_variant","source","source_inferred","tool"]},
  {"tool":"book_list","source":"tool","latency_ms":67,"iteration":0},
  {"tool":"book_read","source":"tool","latency_ms":68,"iteration":0}
]
```

#### The question that decides the verdict, answered from run A's record alone

| question | answered from the record? | the answer |
|---|---|---|
| Which tools was the model holding on its **second pass**? | **Yes** | `advertised_tools[pass=2].names` — the 30 names listed above, `tool_choice: "auto"`. No code read required. |
| Was anything **hidden** from it? | **Yes, vacuously — and that is the problem** | `withheld_tools IS NULL`. In *this* turn nothing was withheld, so the record is correct. But §3-B shows a turn where 98 tools were withheld and the column reads exactly the same `NULL`. **The field cannot be used to answer this question, because its "nothing was withheld" and its "I failed to record what was withheld" are the same value.** |
| Did the **third result** come from a tool or from our own breaker? | **Yes** | A2's third entry: `book_read`, `source: "tool"`, `latency_ms: 68`. And in the run-B breaker turn the third entry reads `source: "breaker"`, `latency_ms: null`. The two populations are separated in the record itself. |
| How did the turn **end**? | **Yes** | `outcome: "completed"`. |

Three of four answerable without inference. The second is answerable only in form.

**Criteria check:** `advertised_tools` present per pass ✅ · every `tool_calls` entry has `source` ✅ ·
every entry has `latency_ms` ⚠️ (the *key* is always present, but the **value is `null` for
`meta`-sourced results** — `tool_list`, `tool_load`; those entries also carry `source_inferred: true`,
i.e. the label was inferred at the write site rather than stamped at dispatch) · outcome present ✅.
I do not treat the null latency as a failure — the honest `source_inferred` flag means the record
tells you it inferred rather than pretending — but it is a real edge and I am reporting it.

---

### B · withheld — **FAIL**

I reached the withheld state two different ways. **One records. One does not. The one that does not
is the founding case.**

#### B1 — the token budgeter (**FAIL**, reproduced twice)

Turn: *"I need the composition tools. Call `tool_load` with `category="composition"` to load every
tool in that category…"* (typed into the composer, sent with the send button)

```sql
SELECT message_id, outcome,
       (SELECT jsonb_agg(jsonb_build_object('pass',p->'pass','count',p->'count'))
          FROM jsonb_array_elements(m.advertised_tools) p) AS passes,
       COALESCE(jsonb_array_length(withheld_tools),-1) AS wh_len,     -- -1 == NULL
       (SELECT jsonb_agg(jsonb_build_object('tool',e->>'tool','source',e->>'source',
                                            'note',left(e->>'result',110)))
          FROM jsonb_array_elements(m.tool_calls) e) AS calls
FROM chat_messages m
WHERE session_id='019fc9fe-9888-7a56-8a48-3cb6466806fb' AND role='assistant'
ORDER BY sequence_num DESC LIMIT 1;
```
```
af00f5e8-7973-4c00-add3-481bbc8ff295 | completed
  passes  | [{"pass": 1, "count": 23}, {"pass": 2, "count": 32}]
  wh_len  | -1                                             <-- withheld_tools IS NULL
  calls   | [{"tool":"tool_load","source":"meta", …}]
```

The tool's **own stored result** says what happened:

```sql
SELECT withheld_tools IS NULL AS wh_null, left(e->>'result',700)
FROM chat_messages m, jsonb_array_elements(m.tool_calls) e
WHERE m.message_id='af00f5e8-7973-4c00-add3-481bbc8ff295';
```
```
t | {"note": "Loaded 9 of 107 tools (token budget). Call tool_load with specific names to load the rest.", "tools": [...
```

**98 tools were deleted by the token budgeter. `withheld_tools` is `NULL`.**

The offered-set diff confirms only 9 arrived:

```sql
SELECT p->'pass', (SELECT string_agg(x::text, ',' ORDER BY x::text)
                     FROM jsonb_array_elements_text(p->'names') x)
FROM chat_messages m, jsonb_array_elements(m.advertised_tools) p
WHERE m.message_id='af00f5e8-7973-4c00-add3-481bbc8ff295';
```
```
1|book_chapter_create,book_chapter_save_draft,book_list,book_read,book_search,chat_search_sessions,
  confirm_action,conversation_search,glossary_deep_research,jobs_cancel,jobs_get,jobs_list,jobs_pause,
  jobs_summary,load_skill,run_subagent,tool_list,tool_load,translation_job_control,
  translation_job_status,web_search,workflow_list,workflow_load
2|…same 23…,composition_arc_get,composition_arc_template_get,composition_authoring_run_get,
  composition_authoring_run_list,composition_get_derivative_context,composition_get_mine_job,
  composition_get_outline_node,composition_list_derivatives,composition_motif_get
```

**Reproduced with a different category** (`6b1dc5c4-48d1-42e1-b008-9c3e54919711`, *"call `tool_load`
with `category="knowledge"`"*):

```
6b1dc5c4-48d1-42e1-b008-9c3e54919711 | completed
  passes | [{"pass":1,"count":46},{"pass":2,"count":50},{"pass":3,"count":50}]
  wh_len | -1                                             <-- NULL again
  calls  | [{"tool":"tool_load","source":"meta",
             "note":"{\"note\": \"Loaded 8 of 36 tools (token budget). Call tool_load with specific names to load the rest.\", \"tools\":"}]
```

**28 more tools deleted. `withheld_tools` `NULL` again.** Both turns had a *subsequent* advertise
pass (pass 2, and passes 2–3), so there was a flush point available and it produced nothing.

I am not diagnosing the mechanism — that is the code verifier's job, and the brief tells me to report
rather than resolve. What I can say from the running system: the drop is real, it is large, it is
reproducible across two categories, and it is unrecorded.

#### B2 — the repeated-failure breaker (**records correctly**; this is the control that makes B1 a real finding)

Turn: *"Call `book_list` with `kind="chapters"` and NO `book_id`. It will fail. Call it again exactly
the same way. Then a third time, then a fourth time…"*

```sql
SELECT message_id, outcome,
       (SELECT jsonb_agg(jsonb_build_object('pass',p->'pass','count',p->'count'))
          FROM jsonb_array_elements(m.advertised_tools) p) AS passes,
       jsonb_pretty(withheld_tools) AS wh,
       (SELECT jsonb_agg(jsonb_build_object('i',e->'iteration','tool',e->>'tool',
                                            'source',e->>'source','ok',e->'ok'))
          FROM jsonb_array_elements(m.tool_calls) e) AS calls
FROM chat_messages m
WHERE session_id='019fca25-4934-7c45-b00e-6b0532c56788' AND role='assistant'
ORDER BY sequence_num DESC LIMIT 1;
```
```
24ace186-d752-403b-bcb6-6538f753863b | completed
passes | [{"pass":1,"count":27},{"pass":2,"count":27},{"pass":3,"count":27},{"pass":4,"count":26}]
wh     | [
           {
               "tool": "book_list",
               "stage": "failure_breaker",
               "reason": "repeated-failure breaker gave up on this tool"
           }
         ]
calls  | [{"i":0,"ok":false,"tool":"book_list","source":"tool"},
          {"i":1,"ok":false,"tool":"book_list","source":"tool"},
          {"i":2,"ok":false,"tool":"book_list","source":"breaker"}]
```

`{tool, stage, reason}` — not an empty array. And the deletion is visible in the pass array:

```sql
SELECT 'PASS3-vs-PASS4 diff: ' || (SELECT string_agg(x,',')
         FROM (SELECT jsonb_array_elements_text(p3->'names')
               EXCEPT SELECT jsonb_array_elements_text(p4->'names')) s(x))
FROM (SELECT advertised_tools->2 AS p3, advertised_tools->3 AS p4
      FROM chat_messages WHERE message_id='24ace186-d752-403b-bcb6-6538f753863b') t;
```
```
PASS3-vs-PASS4 diff: book_list
```

Full `tool_calls`, showing the tool→breaker handover:

```json
[
  {"iteration":0,"tool":"book_list","source":"tool","latency_ms":22,"ok":false,
   "error":"kind=chapters needs book_id — pass the book whose chapters to list"},
  {"iteration":1,"tool":"book_list","source":"tool","latency_ms":19,"ok":false,
   "error":"kind=chapters needs book_id — pass the book whose chapters to list"},
  {"iteration":2,"tool":"book_list","source":"breaker","latency_ms":null,"ok":false,
   "error":"'book_list' has already FAILED 2 times this turn with the same error: kind=chapters needs book_id — pass the book whose chapters to list — retrying it"}
]
```

**This is the brief's "offered set changes between passes" test, and it PASSES**: the set shrinks
mid-turn (27→26), the record shows **both** states, the withholding names tool/stage/reason, and the
result that came from our own code is labelled `breaker` rather than masquerading as a tool error.

#### Why B is nonetheless FAIL

The brief's run-B row says *"a turn where the **tool budget** drops something"*. The tool budget
dropped 98 tools and then 28 tools, and in both cases `withheld_tools` was `NULL`. That the breaker
stage works proves the column, the write path and the persistence are all fine — which makes the
budgeter's silence a specific, isolated, reproducible defect rather than an unfinished feature.

#### DB-wide, every turn produced on this build

```sql
SELECT count(*) AS assistant_rows, count(advertised_tools) AS with_adv,
       count(withheld_tools) AS with_withheld, count(outcome) AS with_outcome
FROM chat_messages WHERE role='assistant';
```
```
 assistant_rows | with_adv | with_withheld | with_outcome
----------------+----------+---------------+--------------
           2667 |       14 |             0 |           14
```
```sql
SELECT outcome, count(*) FROM chat_messages
WHERE role='assistant' AND outcome IS NOT NULL GROUP BY outcome ORDER BY 2 DESC;
```
```
      outcome      | count
-------------------+-------
 completed         |    12
 abandoned_by_user |     1
 crashed           |     1
```

That snapshot was taken *before* the B2 breaker turn ran. Re-run at the end of the session:

```
 assistant_rows | with_adv | with_withheld | with_outcome
----------------+----------+---------------+--------------
           2668 |       15 |             1 |           15

      outcome      | count
-------------------+-------
 completed         |    13
 abandoned_by_user |     1
 crashed           |     1
```

B2 is the 15th instrumented row and is **the first and only non-null `withheld_tools` in the entire
database** — across 15 turns that included two demonstrable 98-tool and 28-tool budget deletions.
The ~2653 rows with nothing set are pre-CP-0 history, which is expected. `interrupted` — the
deprecated bucket, "the metric to drive to zero" — has **zero** rows, which is the right answer.

---

### C · cancelled — **PASS**

Prompt: *"Count from 1 to 600. Output one number per line…"*. Let it stream ~8 s, then clicked the
real red stop button in the composer.

```sql
SELECT sequence_num, message_id, role, outcome, finish_reason, is_error, error_detail,
       length(content) AS len, left(content,80) AS head, runtime_variant,
       jsonb_array_length(COALESCE(advertised_tools,'[]')) AS passes, created_at
FROM chat_messages WHERE session_id='019fc9fe-9888-7a56-8a48-3cb6466806fb'
ORDER BY sequence_num DESC LIMIT 2;
```
```
-[ RECORD 1 ]---+---------------------------------------------
sequence_num    | 21
message_id      | af70b7fd-8a8f-4ede-98ba-d62d84dace47
role            | assistant
outcome         | abandoned_by_user
finish_reason   | interrupted
is_error        | f
error_detail    |
len             | 1830
head            | 1 \n 2 \n 3 \n … 30
runtime_variant | legacy
passes          | 1
created_at      | 2026-08-04 00:11:18.447358+00
```

`outcome = 'abandoned_by_user'` — *the user abandoned this*, cleanly distinct from `failed` and from
`crashed`. `finish_reason = 'interrupted'` is the provider's word for why generation stopped and is
correctly **not** the outcome. The partial 1830 characters the user did see are retained.

---

### D · killed — **PASS, with a hole**

`docker kill infra-chat-service-1` mid-turn, then `docker start`.

#### D2 — kill **after** a tool call (the checkpointed case) — **PASS**

Session `019fca25-4934-7c45-b00e-6b0532c56788`. Prompt: *"First call `book_list` with
`kind="books"`. After the tool returns, count from 1 to 3000…"*. I waited in-page until the
`book_list` chip rendered (tool done, 00:21:32Z), then killed at 00:22:00Z while the counting was
streaming.

Queried **immediately after the kill, container still down**:

```
$ docker kill infra-chat-service-1 && psql … "SELECT sequence_num, role, outcome, length(content),
    tool_calls IS NOT NULL, advertised_tools IS NOT NULL FROM chat_messages
    WHERE session_id='019fca25-4934-7c45-b00e-6b0532c56788' ORDER BY sequence_num;"
1|user||143|f|f
2|assistant|crashed|0|t|t
```

After `docker start`:

```
-[ RECORD 1 ]---+---------------------------------------------
sequence_num    | 2
message_id      | c73b6322-0ae1-453c-92ba-9fe26211e2cd
role            | assistant
outcome         | crashed
finish_reason   | streaming
is_error        | f
len             | 0
runtime_variant | legacy
adv             | [ { "pass": 1, "count": 32, "tool_choice": "auto",
                      "names": ["book_list","chat_search_sessions","confirm_action","conversation_search",
                                "jobs_cancel","jobs_get","jobs_list","jobs_pause","jobs_summary",
                                "kg_entity_edge_timeline","kg_graph_query","kg_list_templates",
                                "kg_ontology_propose","kg_propose_edge","kg_propose_fact","kg_schema_read",
                                "kg_sync_available","kg_triage_list","kg_triage_resolve","load_skill",
                                "memory_recall_entity","memory_remember","memory_search","memory_timeline",
                                "run_subagent","tool_list","tool_load","translation_job_control",
                                "translation_job_status","web_search","workflow_list","workflow_load"] } ]
tc              | [ { "id":"call_4274648666860285", "ok":true, "args":{"kind":"books"},
                      "tool":"book_list", "error":null,
                      "result":{"kind":"books","page":{"total":188,…},
                                "books":[{"title":"[THROWAWAY] CP-0 v-live 2026-08-04",
                                          "book_id":"019fc9fd-4515-71b2-ab66-b4feed41d85f", …}, …]} } ]
```
```sql
SELECT e->>'tool', e->>'source', e->'latency_ms', e->>'runtime_variant'
FROM chat_messages m, jsonb_array_elements(m.tool_calls) e
WHERE m.message_id='c73b6322-0ae1-453c-92ba-9fe26211e2cd';
```
```
book_list|tool|86|legacy
```

The turn does **not** sit in a non-terminal state, and an outsider can reconstruct from this row
alone: 32 tools offered on pass 1 (named), `book_list` really ran (`source: tool`, 86 ms), the turn
died mid-stream (`outcome: crashed`, `finish_reason: streaming`), and no answer text was produced.

Notably the `crashed` outcome was **already in the row while the container was dead** — it is written
at the checkpoint, not reconstructed by a sweeper on restart. That is the right shape: it survives a
`SIGKILL` that no cleanup handler would.

#### D1 — kill **before** the first checkpoint — **the hole**

Session `019fca22-ce9a-7b83-86a6-2a98db5fda97`. Prompt: *"Count from 1 to 3000…"* — a pure-text
turn, no tool call, so no checkpoint. Streaming began 00:18:46Z; killed 00:19:04Z (18 s in).

After restart, the entire record of that turn is:

```sql
SELECT sequence_num, message_id, role, outcome, finish_reason, is_error, error_detail,
       length(content) AS len, left(content,60) AS head, runtime_variant,
       advertised_tools IS NOT NULL AS has_adv, created_at
FROM chat_messages WHERE session_id='019fca22-ce9a-7b83-86a6-2a98db5fda97' ORDER BY sequence_num;
```
```
-[ RECORD 1 ]---+-------------------------------------------------------------
sequence_num    | 1
message_id      | 019fca23-1959-7c5d-b33d-d5b85d33fb24
role            | user
outcome         |
finish_reason   |
is_error        | f
error_detail    |
len             | 112
head            | Count from 1 to 3000. Output one number per line and nothing
runtime_variant | legacy
has_adv         | f
created_at      | 2026-08-04 00:18:45.720728+00
```

Nothing else, anywhere:
```sql
SELECT * FROM chat_suspended_runs WHERE session_id='019fca22-…';            -- (0 rows)
SELECT count(*) FROM chat_outputs o JOIN chat_messages m USING (message_id)
  WHERE m.session_id='019fca22-…';                                          -- 0
SELECT session_id, status, updated_at FROM chat_sessions WHERE session_id='019fca22-…';
  -- status = active, updated_at = 00:18:45 (the user message)
```

18 seconds of generation, an offered surface, a kill — **no row, no `crashed`, no outcome**. Reloading
the session in the browser shows the user's message followed by nothing: no error, no badge, no
spinner. I score D as PASS because the brief's stated bar ("does not sit forever in a non-terminal
state with nothing recorded") is met — it does not *sit*, it simply is not there — but the checkpoint's
own claim covers "turns nobody ever finishes", and a text-only turn killed before its first tool call
is exactly such a turn and leaves no trace.

---

## 4. Also report what you were not asked about *(explicitly out of CP-0 scope)*

**4.1 — A failed turn is recorded nowhere, and the service says so in its own log.** *(out of scope;
the service names CP-3.6 as its owner — I did not read the plan, this is the log line verbatim)*

My very first turn hit an upstream LLM error. Result:

```
loreweave_llm.errors.LLMUpstreamError: {"event": "error", "code": "LLM_UPSTREAM_ERROR"}
INFO:app.services.stream_service: CP-0.4 silent-exit: empty terminal turn recorded nowhere
  (session 019fc9fe-9888-7a56-8a48-3cb6466806fb, msg d26540b3-51d8-467f-acd3-ccfc51caf075,
   reason=error). Closes at CP-3.6 with the other three silent exits.
```

The DB confirms the log: only the user row exists, `outcome` NULL, no assistant row. Combined with
D1 above, **two of the three "abnormal end" shapes I hit (upstream error; crash before first
checkpoint) produce no record at all**, while the two that CP-0 instruments (user cancel; crash after
a checkpoint) produce good ones. I flag this because CP-0's claim as written to me covers "turns that
fail" — whether the failing-turn case belongs to CP-0 or to a later checkpoint is an **ambiguity I am
reporting rather than resolving**, per the brief.

**4.2 — A cold LM Studio model reliably fails the first turn.** *(out of scope, environmental)* The
first request against a not-yet-loaded model exceeds the gateway's patience and surfaces as
`LLM_UPSTREAM_ERROR`; the same request succeeds once the model is resident. A direct
`POST http://localhost:1234/v1/chat/completions` for the same model took long enough to load that my
own 180 s client timeout fired once. A user's first message of the day therefore fails with an
unexplained error and, per 4.1, is not recorded.

**4.3 — `latency_ms` is `null` for every `meta`-sourced result.** *(borderline in-scope; reported for
completeness)* `tool_list` and `tool_load` entries carry `latency_ms: null` and an extra
`source_inferred: true`. The `source_inferred` flag is good practice — the record admits the label was
inferred at the write site rather than stamped at dispatch — but it does mean the runtime primitives
are the one population whose cost is invisible, and they are not cheap (`tool_load` ran a 107-tool
budget pass).

**4.4 — The notifications SSE stream drops with `ERR_INCOMPLETE_CHUNKED_ENCODING`.** *(out of scope)*
Repeatedly in the browser console: `GET /v1/notifications/stream?token=… net::ERR_INCOMPLETE_CHUNKED_ENCODING`.
No visible product impact during my runs.

**4.5 — I created a scratch account before finding the seed account.** *(housekeeping)* Before I
noticed the login form pre-fills the repo's dev-seed agent account, I registered
`cp0live@test.com` (`user_id 019fc9f8-29dd-71ea-98de-5ab5f12a7451`) and gave it one `lm_studio`
provider credential (`019fc9f9-9e8f-7b20-a6e4-4947cca880ef`) and one `user_model`
(`019fc9fa-0fcd-79b5-a08d-4ef7e94e6616`). **I never drove a chat turn as that account** — every run
above is `claude-test@loreweave.dev`. Those three rows are inert leftovers in `loreweave_auth` /
`loreweave_provider_registry`; delete them at your convenience.

**4.6 — There is no UI path to the other withholding stages.** *(observability finding, per the
brief's §5)* `oneshot_deadvertise_mode` and `rail_action_gate_mode` gate the `oneshot_existence` /
`oneshot_per_turn` / `oneshot_session` / `rail_gate` withholding stages, and the session-settings
panel exposes neither (I read the whole panel: models, system prompt, reasoning effort, temperature,
top-p, max tokens, grounding, project memory, long-work context mode, voice). The permission-mode
toggle in the composer would not leave `Ghi` (write) on click, so I could not reach
`permission_mode_ask` either. **Consequence: four of the seven withholding stages cannot be exercised
by a user or a UI-driven verifier at all.** I therefore verified two stages live — `token_budget`
(fails) and `failure_breaker` (passes) — and can say nothing about the other five.

---

## 5. Runs I could not perform, and why

None of A–D was impossible. Two narrower things were:

1. **A mid-turn deletion via the `oneshot_*` or `rail_gate` stages** — no UI path (4.6). I reached
   the same *shape* (offered set shrinks between passes; both states recorded) through the
   `failure_breaker` stage instead, which I consider an adequate substitute for the brief's specific
   test, and I have said plainly which stage produced it.
2. **A `permission_mode_ask` withholding** — the composer's permission toggle would not switch.

Both are recorded above as observability findings, since observability is this checkpoint's subject.

---

## 6. Everything I ran, in order

1. Verified the deployed image did **not** contain the code under test; rebuilt + `--force-recreate`;
   verified the four columns landed. (§2)
2. Logged into the UI as the dev-seed agent account; created the throwaway book
   `[THROWAWAY] CP-0 v-live 2026-08-04`.
3. Run A (×2), including a three-result turn spanning `meta` and `tool` provenance.
4. Run B via the token budgeter (×2 categories) → **NULL**; run B via the repeated-failure breaker →
   **records**, and the offered set visibly shrinks 27→26 with both states retained.
5. Run C — real stop button mid-stream → `abandoned_by_user`.
6. Run D — `docker kill` after a checkpoint → `crashed` (written while the container was dead);
   `docker kill` before any checkpoint → nothing.
7. Read every row back out of `loreweave_chat` with the queries pasted above.

No fixes proposed, per the brief.
