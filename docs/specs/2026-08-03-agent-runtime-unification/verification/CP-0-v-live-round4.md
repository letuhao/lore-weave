# CP-0 · V-LIVE — verdict (ROUND 4)

**Verifier:** V-LIVE (running-system verifier), round 4.
**Artifact frozen at:** `8aa01a77a` (branch `feat/frontend-tools-mcp-migration`; `services/chat-service` working tree clean).
**Date driven:** 2026-08-04 UTC 02:37 → 03:35.
**Discipline:** I read no commit messages and no builder notes before driving. I read my own round-3
verdict before starting (I was told to re-test its findings). I read
`app/services/stream_service.py` **only after runs A–D were complete**, and only to learn the
mechanic that gates the tool-free pass so I could try to *reach* it — never to resolve an ambiguity
in a verdict. That read is disclosed in §5-claim-2.

---

## 0. Verdict

| | verdict |
|---|---|
| **Overall** | **FAIL** — on claim (4). See §5-claim-4 and the reasoning in §0.1. |
| **A · clean** | **PASS** on the brief's stated bar (defects A-d1′, A-d3 noted) |
| **B · withheld** | **PASS** on the brief's stated bar — **B-d1 survives, rate unchanged for the third round** |
| **C · cancelled** | **PASS** (new defect C-d2) |
| **D · killed** | **PASS** (caveat D-c1 survives) |

### The four claims I was told to test hardest

| # | claim | verdict |
|---|---|---|
| **1** | the `pass` stamp is no longer one pass late | **FIXED** — exactly, five for five. **But the 11/178 same-pass overlap is UNTOUCHED**: 6.2%, identical tools, identical count to round 3. |
| **2** | a tool-free pass now emits `names=[]` + a `pass_offered_no_tools` withheld entry | **CANNOT DETERMINE — unreachable.** The emitter is present in the running container. Zero instances exist in the entire database, and I could not reach the path in **seven** attempts across two surfaces. A testability finding, not a pass. |
| **3** | voice + proactive assistant rows now carry an outcome | **SPLIT.** Proactive: **FIXED** (`outcome='completed'`). Voice: **UNREACHABLE** — it fails at `STT model not configured` before persisting anything, and writes **no row at all**. |
| **4** | the surface-assembly / hot-seed narrowing now arrives in `withheld_tools` via the ContextVar | **FAIL — fourth round running.** Across all 16 assistant rows I produced, **not one** withheld entry is stamped at pass 1, while 256–286 of the 307-tool catalogue were dropped there every single turn. |

### 0.1 Why overall is FAIL when A–D all pass

The four runs meet the bars the brief wrote for them. The **checkpoint claim** does not:

> *"…an outsider can reconstruct what the model was offered, **what was withheld and why**…"*

On run A the record says **33** tools were withheld. The true number is **311** — 33 recorded plus
278 dropped, unrecorded, by surface assembly before pass 1. An outsider reading the column does not
get an *incomplete* answer; they get a **confidently wrong** one, off by roughly 10×, with nothing in
the record to signal the omission. That is worse than a null. Claim (4) is the specific thing I was
asked to confirm, it is the thing that has failed by a different mechanism in every round, and it
fails again.

---

## 1. The falsifier

*What I looked for that would have made this FAIL. Each was a live hypothesis, not a ticked box.*

| # | falsifier | outcome |
|---|---|---|
| **F1** | The container does not contain `8aa01a77a`, so the verdict is worthless | **FOUND, fourth round running, corrected before any run.** See §2. |
| **F2** | `advertised_tools` records only the final pass, so a set that changes mid-turn is invisible — *the defect CP-0 exists to catch* | **Not found.** Run A records five silent removals with both states preserved. See §5-A. |
| **F3** | The `pass` stamp still names the pass *after* the narrowing took effect | **Not found — FIXED.** Removed at 6/9/12/15/18, stamped 6/9/12/15/18. See §5-claim-1. |
| **F4** | The off-by-one fix silently left the same-pass contradiction in place | **FOUND.** 11/178 = 6.2%, the same eleven tools as round 3. See §5-claim-1b. |
| **F5** | `withheld_tools` accounts for only the late narrowings and misses the big one | **FOUND — this is the round-4 finding.** 0 of 16 turns record anything at pass 1. See §5-claim-4. |
| **F6** | A tool-free pass still records nothing | **Could not be falsified either way — the path is unreachable.** Zero instances DB-wide. See §5-claim-2. |
| **F7** | The proactive row still lands with a NULL outcome | **Not found — FIXED.** See §5-claim-3a. |
| **F8** | The voice row still lands with a NULL outcome | **Could not test — voice writes no row at all on this deployment.** See §5-claim-3b. |
| **F9** | A user cancel is recorded as `interrupted` alone — indistinguishable from "this broke" | **Not found.** `outcome='abandoned_by_user'`; `interrupted` appears only in `finish_reason`, on every row this session. |
| **F10** | `abandoned_by_user` is written for turns the user did **not** abandon | **FOUND (C-d2).** A turn killed by a browser connection drop is recorded as a user abandonment. See §5-C. |
| **F11** | A killed turn sits forever non-terminal with nothing recorded | **Not found.** See §5-D. |
| **F12** | `tool_calls` double-counts | **FOUND (A-d3).** Run A: 18 entries, 17 distinct iterations. See §5-A. |

F5 is the round-4 finding. F3 is the round-4 fix. F4 is the round-4 non-fix.

---

## 2. Was the running container the code under test? — **No. Stale for the fourth round running.**

I checked **before** driving anything, by whole-tree hash with line-ending normalisation (so a CRLF
artifact could not masquerade as a difference), over all 107 `.py` files:

```
$ find app -name '*.py' -type f | sort | while read f; do
    printf "%s  %s\n" "$(tr -d '\r' < "$f" | sha256sum | cut -d' ' -f1)" "$f"; done > repo.txt
$ docker exec infra-chat-service-1 sh -c "cd /app && …same…" > cont.txt
$ diff repo.txt cont.txt
43c43
< 57332833c0edffaa2ecc796d1b8372c4e87d35fe…  app/routers/internal.py
> 17e350672965156621f441a0c92bf62cd7b3ecd7…  app/routers/internal.py
71c71
< 876f8377e07f381e0ea7d00a3d313a18cfc9f728…  app/services/instrument.py
> ca3d0b1eee3c52e8f61e6b31fae31a5a92fb985a…  app/services/instrument.py
89c89
< a893570a716203026dc653c3996491024d1a7a2b…  app/services/stream_service.py
> 17336206446857418f9cf41dd47d8d908b827d8c…  app/services/stream_service.py
98c98
< ac90827de9a3fe4e9c0986b2176789b936933ac6…  app/services/tool_surface.py
> 317e5df034d27d80abc937f1975b1365554e87e8…  app/services/tool_surface.py
102c102
< 4b87d6166af6a20cc637414cdebda32d137cd8cf…  app/services/voice_stream_service.py
> 2be26fd32e97ed253a45794047ebeb905f2af9c8…  app/services/voice_stream_service.py
```

**Five files differed — and they are exactly the five files CP-0 round 4 changed**
(`instrument.py`, `stream_service.py`, `tool_surface.py`, `voice_stream_service.py`,
`internal.py`). 102 of 107 files matched under the identical method, which is what proves the method
sound rather than universally noisy. Note that `instrument.py` in the *container* hashed to
`ca3d0b1e…` — **the exact hash round 3 recorded as the freshly-built round-3 artifact.** The
container had never been rebuilt since.

Rebuilt and force-recreated, then re-verified:

```
$ docker compose build chat-service        → naming to docker.io/library/infra-chat-service:latest  DONE
$ docker compose up -d --force-recreate --no-deps chat-service   → Recreated / Started
$ diff repo.txt cont2.txt
IDENTICAL - container now matches repo @ 8aa01a77a
```

Re-verified a third time after run D's `docker kill` / `docker start` cycle:
`IMAGE STILL MATCHES REPO`. **Every run below is against `8aa01a77a`.**

> **This is the fourth consecutive round in which the deployed container was not the artifact under
> test.** It is no longer a one-off; a verifier who skipped this step in any round would have
> published a verdict about different code.

---

## 3. How I drove the system

**Via the real UI**, at `http://localhost:5174`, in Chromium under Playwright. Logged in through the
existing session; created the book through the real "Sách mới" dialog; created both chat sessions
through the real new-chat dialog; typed every prompt with real keystrokes into the real composer;
armed the proactive gate with the real toggle on `/assistant`; enabled voice mode through the real
toggle and its real consent dialog.

**Two disclosed deviations, both forced and both narrow:**

1. **Send and stop clicks were dispatched page-side** (`element.click()` on the real
   `[data-testid="chat-send-button"]` and the real `button.bg-destructive` stop control), not via
   Playwright's trusted-event click. Reason: the MCP round trip is ~15–20 s, and with a warm prompt
   cache the local model finished entire turns in under that — three cancel attempts failed purely
   on latency before I changed technique. The elements and their React handlers are the real ones.
2. **The proactive turn and the voice turn were driven through their HTTP endpoints**, because
   neither has an on-demand UI trigger (proactive fires on a cron; voice needs a microphone with
   speech, which this harness cannot supply). For proactive I armed the gate **through the real UI
   first**, and I verified the gate is load-bearing by disabling it and re-firing — the endpoint
   returned `{"proactive": false, "reason": "not_enabled"}`. Both are declared as the weaker result
   the brief warns about.

**Throwaway book:** `CP0-VLIVE-R4-THROWAWAY` — `019fcaa4-856f-7206-8bc3-d3a81d71e065`.
Nothing was written into any existing content book. (The 22 chapters in it are probe debris from my
own forced-final attempts; the book exists to absorb exactly that.)

**Sessions driven:**
- `019fcaa6-10b2-76e4-84ae-842e4198b250` — universal `/chat` surface (runs A–D)
- `019fcac6-8c70-70f4-9593-2822dba0e97d` — book-scoped studio surface (claim-2 attempts)
- `019fcad4-0346-7621-ab18-3b8d90b1313a` — created by the proactive turn

**Account:** `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`. **Model:** Gemma-4 26B-A4B QAT (200K) via LM Studio.
**Database:** `loreweave_chat` in `infra-postgres-1`, user `loreweave`.

---

## 4. The turn ledger — every row this session produced

```sql
SELECT sequence_num seq, role, outcome, finish_reason, length(content) chars,
       jsonb_array_length(advertised_tools) adv, jsonb_array_length(withheld_tools) wh,
       jsonb_array_length(tool_calls) calls
FROM chat_messages WHERE session_id='019fcaa6-10b2-76e4-84ae-842e4198b250' ORDER BY sequence_num;
```

```
 seq |   role    |      outcome      | finish_reason  | chars | adv | wh  | calls
-----+-----------+-------------------+----------------+-------+-----+-----+-------
   1 | user      |                   |                |   159 |     |     |
   2 | assistant | completed         | stop           |  2637 |  19 |  33 |    18   <- RUN A
   3 | user      |                   |                |   273 |     |     |
   4 | assistant | completed         | stop           |  1138 |   2 | 178 |     5   <- RUN B
   5 | user      |                   |                |   398 |     |     |
   6 | assistant | abandoned_by_user | interrupted    |     0 |   6 |     |     5   <- C-d2 (NOT a user cancel)
   7 | user      |                   |                |   458 |     |     |
   8 | assistant | completed         | stop           |   963 |   7 |     |    20
   9 | user      |                   |                |   315 |     |     |
  10 | assistant | awaiting_input    | awaiting_input |     0 |   7 |     |     7
  11 | user      |                   |                |   308 |     |     |
  12 | assistant | awaiting_input    | awaiting_input |     0 |   7 |  28 |     7
  13 | user      |                   |                |   170 |     |     |
  14 | assistant | completed         | stop           |  8886 |   1 |     |
  15 | user      |                   |                |   196 |     |     |
  16 | assistant | completed         | stop           |  3185 |   1 |     |
  17 | user      |                   |                |   164 |     |     |
  18 | assistant | completed         | stop           |  8886 |   1 |     |
  19 | user      |                   |                |   260 |     |     |
  20 | assistant | completed         | stop           |   531 |   2 |     |     1
  21 | user      |                   |                |   227 |     |     |
  22 | assistant | abandoned_by_user | interrupted    |   456 |   1 |     |         <- RUN C (real UI stop)
  23 | user      |                   |                |   240 |     |     |
  24 | assistant | completed         | stop           |   963 |   6 |     |     5
  25 | user      |                   |                |   313 |     |     |
  26 | assistant | crashed           | streaming      |     0 |   4 |  28 |     4   <- RUN D (killed mid-flight)
```

Outcome tally across **both** sessions plus the proactive turn:

```
      outcome      | finish_reason  |    initiated_by     | count
-------------------+----------------+---------------------+-------
 completed         | stop           | user                |    10
 awaiting_input    | awaiting_input | user                |     3
 abandoned_by_user | interrupted    | user                |     2
 completed         | stop           | assistant_proactive |     1   <- CLAIM 3
 crashed           | streaming      | user                |     1
```

**Every assistant row this session carries an outcome. `interrupted` never appears in `outcome`
on any of them** — only in `finish_reason`. (The column's CHECK constraint still *admits*
`'interrupted'` as an outcome value; nothing writes it. Noted, not scored.)

---

## 5. The runs and the four claims

### A · clean — **PASS** on the brief's stated bar

Turn: *"RUN-A: List the tool categories available to you, then load the tools in the 'Book' category,
then tell me how many books I have. Use your tools for each step."*
Message `cda298e8-21f7-4b86-bce7-a1bda17d54e1`. 19 passes, 33 withheld, 18 call entries, `completed`.

**F2 — the defect CP-0 was built for. Clean.** Five silent mid-turn removals, both states preserved:

```sql
WITH m AS (SELECT advertised_tools a FROM chat_messages WHERE message_id='cda298e8-…'),
adv AS (SELECT (p->>'pass')::int pass, (p->>'count')::int cnt,
               ARRAY(SELECT jsonb_array_elements_text(p->'names')) names
        FROM m, jsonb_array_elements(m.a) p)
SELECT cur.pass, cur.cnt,
  (SELECT string_agg(x,',') FROM unnest(cur.names) x
     WHERE prev.names IS NOT NULL AND NOT x = ANY(prev.names)) AS added,
  (SELECT string_agg(x,',') FROM unnest(prev.names) x WHERE NOT x = ANY(cur.names)) AS removed
FROM adv cur LEFT JOIN adv prev ON prev.pass = cur.pass-1 ORDER BY cur.pass;
```
```
 pass | cnt |                       added                        |       removed
------+-----+----------------------------------------------------+---------------------
    1 |  29 |                                                    |
    2 |  29 |                                                    |
    3 |  35 | book_get,book_list_chapters,book_list_revisions,   |
      |     | book_scene_get,book_steering_list,book_update_details |
    4 |  35 |                                                    |
    5 |  35 |                                                    |
    6 |  34 |                                                    | book_list_chapters
    7 |  34 |                                                    |
    8 |  34 |                                                    |
    9 |  33 |                                                    | book_list_revisions
   10 |  33 |                                                    |
   11 |  33 |                                                    |
   12 |  32 |                                                    | book_get
   13 |  32 |                                                    |
   14 |  32 |                                                    |
   15 |  31 |                                                    | book_update_details
   16 |  31 |                                                    |
   17 |  31 |                                                    |
   18 |  30 |                                                    | book_steering_list
   19 |  36 | book_chapter_create,book_chapter_restore_revision, |
      |     | book_chapter_set_kg_exclude,book_chapter_update_meta, |
      |     | book_steering_set,book_structure_edit              |
```

A last-write-wins column would show 36 tools and nothing else. **F2 clean.**

#### The question that decides the verdict — answered from the stored record alone

**(1) Which tools was the model holding on its second pass?**

```sql
SELECT jsonb_pretty(advertised_tools->1) FROM chat_messages WHERE message_id='cda298e8-…';
```
```json
{
    "pass": 2, "count": 29, "tool_choice": "auto",
    "names": ["book_chapter_save_draft","chat_search_sessions","confirm_action","conversation_search",
      "glossary_deep_research","kg_entity_edge_timeline","kg_graph_query","kg_list_templates",
      "kg_ontology_propose","kg_project_list","kg_propose_edge","kg_propose_fact","kg_schema_read",
      "kg_sync_available","kg_triage_list","kg_triage_resolve","kg_view_read","load_skill",
      "memory_forget","memory_recall_entity","memory_remember","memory_search","memory_timeline",
      "run_subagent","tool_list","tool_load","web_search","workflow_list","workflow_load"]
}
```
**Answerable, exactly.**

**(2) Was anything hidden from it?** The record answers **33** — and that answer is **wrong**. See
§5-claim-4. What the record *does* get right is the 33 it names, each with tool, stage, reason and a
now-correct pass. Zero same-pass contradictions on this message:

```
withheld_rows | n_passes | contradiction_same_pass
--------------+----------+-------------------------
           33 |       19 |                       0
```

**(3) Did the third result come from a tool or from our own breaker?**

```sql
SELECT jsonb_pretty((tool_calls->2) - 'result') FROM chat_messages WHERE message_id='cda298e8-…';
```
```json
{
    "id": "call_4274648666861276",
    "ok": false,
    "args": {"book_id": "all"},
    "tool": "book_list_chapters",
    "error": "book_id must be a UUID",
    "source": "tool",
    "iteration": 2,
    "latency_ms": 24,
    "declaration": "book_list_chapters",
    "runtime_variant": "legacy"
}
```
**From a tool** — a real dispatch, 24 ms, validation error. **Answerable.** The contrast inside the
same row is what makes `source` non-decorative:

```
 iter |        tool         | source  | latency_ms |  ok   | inferred
------+---------------------+---------+------------+-------+----------
    0 | tool_list           | meta    |            | true  | true
    1 | tool_load           | meta    |            | true  | true
    2 | book_list_chapters  | tool    | 24         | false |
    3 | book_list_chapters  | tool    | 20         | false |
    4 | book_list_chapters  | breaker |            | false | true
    5 | book_list_revisions | tool    | 16         | false |
    6 | book_list_revisions | tool    | 22         | false |
    7 | book_list_revisions | breaker |            | false | true
    8 | book_get            | tool    | 20         | false |
    9 | book_get            | tool    | 17         | false |
   10 | book_get            | breaker |            | false | true
   11 | book_update_details | tool    | 25         | false |
   12 | book_update_details | tool    | 19         | false |
   13 | book_update_details | breaker |            | false | true
   14 | book_steering_list  | tool    | 19         | false |
   15 | book_steering_list  | tool    | 22         | false |
   16 | book_steering_list  | breaker |            | false | true
   16 | book_steering_list  | breaker |            | false | true   <- A-d3: DUPLICATE
```

The two-real-failures-then-breaker pattern is legible from the record alone, and each breaker row
lines up with a removal in the pass table.

**(4) How did the turn end?** `outcome='completed'`, `finish_reason='stop'`. **Answerable.**

> **A-d1′ (round 3's A-d1, now materially improved) — `latency_ms` is still `null` on every
> non-dispatched call (7 of 18), but the null is now *explained*.** Both `meta` and `breaker` entries
> carry a new sibling field:
> ```json
> { "tool": "tool_list", "source": "meta", "latency_ms": null,
>   "source_inferred": true, "latency_unmeasured": "meta" }
> { "tool": "book_list_chapters", "source": "breaker", "latency_ms": null,
>   "source_inferred": true, "latency_unmeasured": "breaker" }
> ```
> An outsider can now distinguish *"we did not measure this, and here is the class of call it was"*
> from *"we measured it and lost the number"*. The brief's literal bar (*every entry has `source`
> and `latency_ms`*) is met in the key-present sense. **I record this as resolved in substance.**

> **A-d3 (NEW) — `tool_calls` double-counts a breaker short-circuit.** Run A stores **18 entries for
> 17 distinct iterations**: `book_steering_list` / `source=breaker` / `iteration=16` appears twice,
> with two different call ids (`call_…861303` and `call_…861845`, a gap suggesting the second was
> appended much later, on or near the final pass). Round 3's equivalent run stored 17 entries with no
> duplicate. Anything counting tool calls from this column over-reports; anything joining on
> `iteration` gets a fan-out.

---

### B · withheld — **PASS on the stated bar. B-d1 survives, unchanged for the third round.**

Turn: *"RUN-B: Now load ALL the tools in the Composition category, then also load the Glossary
category, then also the Knowledge category, then the World category, then the Campaign category…"*
Message `8dad348e-5e5b-4d65-8fc1-92963ed42734`. 2 passes, **178** withheld, 5 calls, `completed`.

The brief's bar — *"names the tool, the stage, and a reason — not an empty array"* — is met:

```
    stage     | pass | count
--------------+------+-------
 token_budget | 2    |   178      reason: "did not fit the activation token budget"
```

---

### 5-claim-1 · the `pass` stamp — **the off-by-one is FIXED, exactly**

Round 3 measured the stamp landing one pass **after** the pass the narrowing actually shaped
(dropped at 6, stamped 7; five for five). On `8aa01a77a`:

```sql
WITH m AS (SELECT advertised_tools a, withheld_tools w FROM chat_messages WHERE message_id='cda298e8-…'),
adv AS (SELECT (p->>'pass')::int pass, jsonb_array_elements_text(p->'names') name FROM m, jsonb_array_elements(m.a) p),
wh  AS (SELECT (x->>'pass')::int pass, x->>'tool' tool, x->>'stage' stage FROM m, jsonb_array_elements(m.w) x)
SELECT wh.tool, wh.stage, wh.pass AS withheld_at_pass,
       (SELECT string_agg(adv.pass::text,',' ORDER BY adv.pass) FROM adv WHERE adv.name=wh.tool) AS advertised_on_passes
FROM wh WHERE wh.stage='failure_breaker' ORDER BY wh.pass;
```
```
        tool         |      stage      | withheld_at_pass |         advertised_on_passes
---------------------+-----------------+------------------+---------------------------------------
 book_list_chapters  | failure_breaker |                6 | 3,4,5
 book_list_revisions | failure_breaker |                9 | 3,4,5,6,7,8
 book_get            | failure_breaker |               12 | 3,4,5,6,7,8,9,10,11
 book_update_details | failure_breaker |               15 | 3,4,5,6,7,8,9,10,11,12,13,14
 book_steering_list  | failure_breaker |               18 | 3,4,5,6,7,8,9,10,11,12,13,14,15,16,17
```

Cross-reference against the delta table in §5-A: the tools vanish from the advertised set at passes
**6, 9, 12, 15, 18** and are now stamped **6, 9, 12, 15, 18**. Every tool's
`advertised_on_passes` ends at exactly `withheld_at_pass − 1`. The stamp now names the pass the
narrowing shaped, and the two arrays reconcile with no gap and no overlap. **Five for five. Fixed.**

### 5-claim-1b · did the fix resolve the 11/178 overlap? — **No. Untouched.**

```sql
WITH m AS (SELECT advertised_tools a, withheld_tools w FROM chat_messages WHERE message_id='8dad348e-…'),
adv AS (SELECT (p->>'pass')::int pass, jsonb_array_elements_text(p->'names') name FROM m, jsonb_array_elements(m.a) p),
wh  AS (SELECT (x->>'pass')::int pass, x->>'tool' tool FROM m, jsonb_array_elements(m.w) x)
SELECT (SELECT count(*) FROM wh) withheld_rows,
       (SELECT count(DISTINCT pass) FROM adv) n_passes,
       (SELECT count(*) FROM wh JOIN adv ON adv.name=wh.tool AND adv.pass=wh.pass) contradiction_same_pass,
       round(100.0*(SELECT count(*) FROM wh JOIN adv ON adv.name=wh.tool AND adv.pass=wh.pass)
             /(SELECT count(*) FROM wh),1) pct;
```
```
 withheld_rows | n_passes | contradiction_same_pass | pct
---------------+----------+-------------------------+-----
           178 |        2 |                      11 | 6.2
```

The eleven, named — **the same eleven tools as round 3, to the name**:

```
          tool           |    stage     | withheld_at_pass | advertised_on_passes
-------------------------+--------------+------------------+----------------------
 glossary_deep_research  | token_budget |                2 | 1,2
 kg_entity_edge_timeline | token_budget |                2 | 1,2
 kg_graph_query          | token_budget |                2 | 1,2
 kg_list_templates       | token_budget |                2 | 1,2
 kg_ontology_propose     | token_budget |                2 | 1,2
 kg_sync_available       | token_budget |                2 | 1,2
 kg_triage_list          | token_budget |                2 | 1,2
 kg_triage_resolve       | token_budget |                2 | 1,2
 memory_recall_entity    | token_budget |                2 | 1,2
 memory_search           | token_budget |                2 | 1,2
 memory_timeline         | token_budget |                2 | 1,2
```

| round | measurement | rate |
|---|---|---|
| 2 | 19 / 303 | 6.3% |
| 3 | 11 / 178 | 6.2% |
| **4** | **11 / 178** | **6.2%** |

> **B-d1 (survives, third round) — the off-by-one fix could not have resolved this, and the record
> shows why.** These eleven are advertised on **every** pass of the turn. There is no stamp value
> that avoids the collision: the fix moved the stamp from pass 3 to pass 2, and pass 2 is still a
> pass on which all eleven were in the `names` array sent to the model. The two fields make
> contradictory assertions about the same tool at the same pass. `advertised_tools` remains
> authoritative for "was this offered?", so an outsider can still get that right — but the withheld
> **count** carries a ~6% false-positive rate and cannot be totalled.

---

### 5-claim-2 · the tool-free pass — **CANNOT DETERMINE. The path is unreachable through the product.**

**The emitter is present in the artifact under test.** Verified inside the running container, not
just the repo:

```
$ docker exec infra-chat-service-1 sh -c 'grep -n "pass_offered_no_tools" app/services/stream_service.py'
2327:                        "tool": "*", "stage": "pass_offered_no_tools",
```

**Zero instances exist anywhere in the database — not from my runs, and not from any run ever:**

```sql
SELECT count(*) FILTER (WHERE x->>'stage'='pass_offered_no_tools') AS stage_rows
FROM chat_messages, jsonb_array_elements(withheld_tools) x;
--  0

SELECT count(*) AS passes_with_empty_names
FROM chat_messages, jsonb_array_elements(advertised_tools) p WHERE jsonb_array_length(p->'names')=0;
--  0
```

**Seven attempts to reach it, across two surfaces, all failed:**

| # | surface | prompt shape | result |
|---|---|---|---|
| CLAIM2 | universal `/chat` | 20 separate `tool_list` calls | 6 passes, aborted (C-d2) |
| CLAIM2B | universal `/chat` | 25 separate `tool_list` calls | 7 passes, 20 calls, `completed` — model batched |
| CLAIM2C | universal `/chat` | 6 chapter creates, one per turn | 7 passes, `awaiting_input` (confirm gate) |
| CLAIM2D | universal `/chat` | 24 chapter creates, one per turn | 7 passes, `awaiting_input` (confirm gate) |
| CLAIM2E | book studio | 10 chapter reads + revisions, one per turn | **9 passes**, 19 calls, `completed` — one short |
| CLAIM2F | book studio | 16 explicit sequential reads | 7 passes, `completed` |
| CLAIM2G | book studio | 12 chapter creates, one per turn | 6 passes, `awaiting_input` (confirm gate) |

Run A itself reached **19 passes** and did not trigger it. **After** these runs I read
`stream_service.py` to understand why, and the mechanic explains it: the forced-final gate is
`write_passes >= max_iterations - 1` (l.2032) with `MAX_TOOL_ITERATIONS = 5`,
`GLOSSARY_TOOL_ITERATIONS = 10`, `UNIVERSAL_TOOL_ITERATIONS = 20` (ll.437/448/454) — and
`write_passes` only increments on a pass that executed a **Tier-A/W write** (l.4722). So the
universal `/chat` surface needs **19 write passes** and the book-scoped surface **9**, while the
local model reliably terminates or trips a `confirm_action` gate well before either.

**Verdict: CANNOT DETERMINE.** I applied the standard the brief set for claim 3 — *an unreachable
path is a finding about testability, not a pass.* The per-pass array's completeness on tool-free
passes is asserted by code I can see and by no row that exists. If the intent was for this to be
observable in production, note that on the surface real users are on, it takes 19 consecutive
write passes to happen once.

---

### 5-claim-3a · the proactive check-in — **FIXED**

Gate armed **through the real UI** (`/assistant` → `autonomous-toggle-proactive_nudge`, which flipped
`aria-checked` to `true` and wrote `user_chat_ai_prefs.assistant = {"proactive_enabled": true}`).
There is **no on-demand UI trigger** — the toggle arms a cron schedule — so I fired the endpoint the
scheduler fires:

```
POST /internal/chat/assistant/proactive-turn   (X-Internal-Token)
{"user_id": "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", "language": "en"}

HTTP 202
{"proactive":true,"session_id":"019fcad4-0346-7621-ab18-3b8d90b1313a",
 "message_id":"019fcad4-0346-7e80-a61a-1dfaaeb5c6b9",
 "initiated_by":"assistant_proactive","notified":true}
```

The row:

```sql
SELECT message_id, role, initiated_by, outcome, finish_reason, runtime_variant, is_error,
       length(content) chars, advertised_tools IS NULL adv_null, withheld_tools IS NULL wh_null,
       tool_calls IS NULL tc_null, left(content,120) head
FROM chat_messages WHERE message_id='019fcad4-0346-7e80-a61a-1dfaaeb5c6b9';
```
```
message_id      | 019fcad4-0346-7e80-a61a-1dfaaeb5c6b9
session_id      | 019fcad4-0346-7621-ab18-3b8d90b1313a
role            | assistant
initiated_by    | assistant_proactive
outcome         | completed              <-- CLAIM 3: was NULL
finish_reason   | stop
runtime_variant | legacy
is_error        | f
chars           | 93
adv_null        | t
wh_null         | t
tc_null         | t
head            | I noticed you've been working hard on the Q3 billing migration. How's everything progressing?
```

**The proactive assistant row now carries an outcome.** I verified my UI action was load-bearing
rather than incidental: disabling the toggle and re-firing the identical request returns
`{"proactive": false, "reason": "not_enabled"}` — the endpoint is fail-closed on the pref the UI
writes. (Gate restored to `true` afterwards.)

*Caveat, stated plainly:* `initiated_by='assistant_proactive'` had **never** appeared in this
database before this run, so I have no pre-fix proactive row to diff against. What I can assert is
that the row exists and carries `completed`/`stop`.

### 5-claim-3b · the voice pipeline — **UNREACHABLE. A testability finding.**

I drove voice mode through the real UI: `chat-voice-mode-toggle` → the real consent dialog
("Chế độ giọng nói sẽ dùng micro của bạn…") → **Tiếp tục**. The pipeline armed correctly —

```
[Pipeline] idle → activating
VAD | debug > vad is initialized
VAD | debug > started micVAD
[Pipeline] activating → listening
```

— and `getUserMedia({audio:true})` returned **GRANTED**. But the harness's fake capture device emits
silence, so VAD never fires an utterance and no turn is ever produced. **Voice cannot be completed
end-to-end through the UI in this environment.**

I therefore synthesised real speech with the running `local-tts-service` (kokoro, `af_heart`, 24 kHz
mono PCM WAV — *"How many chapters does my throwaway book have right now?"*) and posted it to the
endpoint the UI posts to:

```
POST /v1/chat/sessions/019fcaa6-…/voice-message   (multipart: audio=voice.wav, config={})
HTTP 200
data: {"type": "error", "errorText": "STT model not configured. Check Voice Settings."}
data: [DONE]
```

```sql
SELECT * FROM chat_messages WHERE session_id='019fcaa6-…' AND sequence_num>=27;
--  (0 rows)
```

**The voice pipeline writes no row at all on this deployment** — not a user row, not an assistant
row, not an error row. There is no outcome to check because there is nothing to check it on.

The blocker is configuration, and it is not fixable from the UI: the voice settings panel's
**"Mô hình STT"** picker reads **"Chọn mô hình… / Chưa cấu hình mô hình"** — no STT model is
registered for this account, and the dropdown is empty. (Switching STT source to
*"Trình duyệt (miễn phí)"* would use the browser's Web Speech API and bypass
`voice_stream_service.py` entirely, so it would not test the claim either.)

**Verdict: CANNOT DETERMINE, and I say so as the brief instructs.** Whether the voice assistant row
now carries an outcome is untested on this machine. Separately worth noting for its own sake: a
voice turn that fails at STT is *itself* a turn that ends and records nothing — which is the exact
class of hole CP-0 exists to close.

---

### 5-claim-4 · the surface-assembly / hot-seed narrowing — **FAIL, fourth round**

This is the finding of round 4.

**The catalogue is 307 tools**, read straight out of run A's own `tool_list` result
(`tool_calls->0->'result'->>'count' = 307`) — the record's own number, not one I supplied.

**Run A, accounted end to end:**

```sql
WITH m AS (SELECT advertised_tools a, withheld_tools w, tool_calls tc
           FROM chat_messages WHERE message_id='cda298e8-…'),
catalog AS (SELECT jsonb_array_elements(cat.v)->>'name' name
            FROM m, jsonb_array_elements(m.tc) c, LATERAL jsonb_each(c->'result'->'categories') cat(k,v)
            WHERE c->>'tool'='tool_list'),
adv AS (SELECT DISTINCT jsonb_array_elements_text(p->'names') name FROM m, jsonb_array_elements(m.a) p),
wh  AS (SELECT DISTINCT x->>'tool' name FROM m, jsonb_array_elements(m.w) x)
SELECT (SELECT count(DISTINCT name) FROM catalog) catalog_tools,
       (SELECT count(*) FROM adv) ever_advertised,
       (SELECT count(*) FROM wh)  ever_withheld,
       (SELECT count(DISTINCT name) FROM catalog
        WHERE name NOT IN (SELECT name FROM adv) AND name NOT IN (SELECT name FROM wh)) unaccounted_for;
```
```
 catalog_tools | ever_advertised | ever_withheld | unaccounted_for
---------------+-----------------+---------------+-----------------
           307 |              41 |            33 |             254
```

**254 tools were neither advertised nor withheld at any point in the turn.** They were removed by
surface assembly before the model ever saw a pass, and the record does not mention them.

**And it is every turn, not a special case.** Pass 1 of every assistant row I produced, against the
307-tool catalogue, versus what `withheld_tools` records *at pass 1*:

```
 seq | pass1_offered | withheld_rows | dropped_by_surface_assembly | withheld_stamped_pass1
-----+---------------+---------------+-----------------------------+------------------------
   2 |            29 |            33 |                         278 |                      0
   4 |            33 |           178 |                         274 |                      0
   6 |            29 |             0 |                         278 |                      0
   8 |            29 |             0 |                         278 |                      0
  10 |            33 |             0 |                         274 |                      0
  12 |            33 |            28 |                         274 |                      0
  14 |            32 |             0 |                         275 |                      0
  16 |            32 |             0 |                         275 |                      0
  18 |            32 |             0 |                         275 |                      0
  20 |            31 |             0 |                         276 |                      0
  22 |            21 |             0 |                         286 |                      0
  24 |            32 |             0 |                         275 |                      0
  26 |            32 |            28 |                         275 |                      0
   2 |            51 |             0 |                         256 |                      0   (book-scoped)
   4 |            51 |             1 |                         256 |                      0   (book-scoped)
   6 |            46 |             0 |                         261 |                      0   (book-scoped)
```

**Sixteen turns. Zero pass-1 withheld entries. 256–286 tools dropped on every one of them.**
Nine of the sixteen have no withheld entries at all — for those turns the column says, in effect,
*nothing was withheld*, on a turn where 275 tools were.

**The stage vocabulary confirms it independently.** Only two stages have *ever* been written to the
column, across the entire table's history:

```sql
SELECT x->>'stage' stage, x->>'reason' reason, count(*) n, count(DISTINCT message_id) msgs
FROM chat_messages, jsonb_array_elements(withheld_tools) x GROUP BY 1,2;
```
```
      stage      |                    reason                     |  n  | msgs
-----------------+-----------------------------------------------+-----+------
 failure_breaker | repeated-failure breaker gave up on this tool  |  11 |    3
 token_budget    | did not fit the activation token budget       | 710 |    7
```

Both are *late* narrowings that happen **after** a `tool_load` has already expanded the surface —
`token_budget` is the *activation* budget (its own reason string says so), which is why it only
appears on turns where the model called `tool_load`, and why it is stamped at pass 2 or 3, never
pass 1. There is no stage for the hot-seed / surface-assembly trim, and no entry for it, on any row
that has ever existed.

> **Claim (4) is not fixed.** The ContextVar may well carry registrations that an explicit argument
> previously dropped — but whatever it now carries, the hot-seed narrowing is not among it. The
> observable outcome is identical to rounds 1, 2 and 3: the single largest narrowing the system
> performs, on every turn, is absent from the column built to record narrowings.
>
> The concrete harm is in §0.1: the record answers *"was anything hidden from it?"* with **33** when
> the answer is **311**, and offers no signal that the number is partial.

---

### C · cancelled — **PASS** (new defect C-d2)

Cancelled from the UI with the real stop button (`button.bg-destructive`, the control that replaces
send while `isStreaming`), 4.1 s into a streaming turn, after ~450 characters of visible prose.

```
 seq | role      | outcome           | finish_reason | chars | adv | head
-----+-----------+-------------------+---------------+-------+-----+---------------------------------------
  22 | assistant | abandoned_by_user | interrupted   |   456 |   1 | I cannot fulfill the request to write…
```

`outcome='abandoned_by_user'` — *the user abandoned this*, distinct from *this broke*. Partial text
preserved. The advertised pass preserved. **The brief's bar is met.**

Round 3's change (detached cancel-write) still holds on this build:

```
$ docker logs infra-chat-service-1 | grep -c "interrupt-persist failed"        → 0
$ docker logs infra-chat-service-1 | grep -c "interrupt-persist detached"      → 2
$ docker logs infra-chat-service-1 | grep -c "CancelledError"                  → 0
```

> **C-d2 (NEW) — `abandoned_by_user` is written for turns the user did not abandon.** At seq 6, I
> opened a **second browser tab** while a turn was streaming. I pressed no stop button and made no
> cancel gesture. The connection dropped (plausibly the per-host HTTP/1.1 connection cap, with the
> notifications `EventSource` competing), and the turn was recorded:
> ```
>   6 | assistant | abandoned_by_user | interrupted | 0 chars | 6 passes | 5 calls
> ```
> The instrument's whole point in run C is to distinguish *the user abandoned this* from *this
> broke*. Here a transport failure was recorded, with full confidence, as a deliberate human act.
> The two are indistinguishable in the column, and the wrong one was chosen.
>
> Mitigating: the turn's six advertised passes and five tool calls *were* preserved, which is more
> than a lost turn would have. The defect is the label, not the loss.

---

### D · killed — **PASS**

`docker kill infra-chat-service-1` landed while the row was confirmed non-terminal.

```
PRE-KILL 03:14:58
 seq | message_id                           | outcome | finish_reason | chars | adv | calls
  26 | 4ce53500-cd3c-40fd-8f5c-7136ecf7482a | crashed | streaming     |     0 |   4 |     4   <- in flight
=== KILL 03:14:58 ===
infra-chat-service-1
```

Post-kill, service **exited**:
```
 seq | role      | outcome | finish_reason | chars | adv | wh | calls
  25 | user      |         |               |   313 |     |    |
  26 | assistant | crashed | streaming     |     0 |   4 | 28 |     4
```

Post-restart (healthy 03:15:34), **unchanged and still present**:
```
  26 | assistant | crashed | streaming     |     0 |   4 | 28 |     4
```

The brief's requirement — *"the turn does not sit forever in a non-terminal state with nothing
recorded"* — is met: `crashed` is terminal, and four advertised passes, 28 withheld entries and four
tool calls survive the kill. **D · PASS.**

I also re-verified the image hash after the kill/start cycle (`IMAGE STILL MATCHES REPO`), so no run
above was driven against a different build.

> **D-c1 (caveat, survives from round 3) — `crashed` cannot distinguish "the process died" from
> "this is still running".** It is written optimistically at every checkpoint and superseded on
> completion. I observed this directly again this session: run A read `crashed|streaming` for its
> entire ~7-minute life with the service healthy throughout, then flipped to `completed|stop`.
> Anything counting `outcome='crashed'` counts every in-flight turn as a dead one. Nothing sweeps or
> reconciles `finish_reason='streaming'` on restart, so the row's terminality rests entirely on the
> pessimistic pre-write.

---

## 6. Out of scope — things I saw that CP-0 did not ask about

**O1 — `withheld_tools` is `NULL`, not `[]`, on turns where nothing was withheld.** 11 of the 16
assistant rows I produced; zero empty arrays.
```
 wh_null | wh_empty_array
---------+----------------
      11 |              0
```
Round 2's O4 and round 3's O4 stand unchanged. `NULL` reads identically to *"we did not look"* — and
given §5-claim-4, on those rows it is closer to the truth than `[]` would have been.

**O2 — the `outcome` CHECK constraint still admits `'interrupted'`.**
```
chat_messages_outcome_check | CHECK (outcome IS NULL OR outcome = ANY
  (ARRAY['completed','awaiting_input','abandoned_by_user','failed','crashed','interrupted']))
```
Nothing writes it, and no row in this session carries it. But the deprecated fused value the
instrument exists to retire is still a legal outcome at the schema level, so nothing prevents a
future writer from reintroducing it.

**O3 — `runtime_variant` is `'legacy'` on every row I produced**, as in rounds 2 and 3. The column
admits `'agentruntime'`; nothing reachable through the UI produced it. **Reporting as an ambiguity**,
per the brief's instruction not to resolve one by reading builder notes.

**O4 — the chat session still does not bind to a book from the chat surface.** Round 2's O3 and
round 3's O6 stand. The throwaway-book rule was honoured, but the new-chat dialog offers a model and
a persona, not a book. The book-scoped studio chat *is* book-bound, which is how I reached that
surface for the claim-2 attempts.

**O5 — the model repeatedly emits byte-identical duplicate tool calls, and the service logs it.**
```
D-TOOLCALL-DUP-IDENTICAL: collapsed 4 byte-identical duplicate tool-call(s) in one pass:
  ['book_update_details','book_update_details','book_update_details','book_update_details']
```
Six such lines this session. The collapse works; I note it only because A-d3 shows one duplicate
surviving into `tool_calls` anyway.

**O6 — browser console errors were self-inflicted.** `ERR_INCOMPLETE_CHUNKED_ENCODING` on
`/v1/notifications/stream` coincides with my `docker kill` windows and with the tab-open that caused
C-d2. **Not a product defect** — recorded so a later reader does not mistake it for one.

---

## 7. What could not be performed

| item | why |
|---|---|
| **Claim 2** — a tool-free pass | Seven attempts, two surfaces. The forced-final gate needs 19 consecutive **write** passes on the universal surface (9 book-scoped); the model terminates or hits a confirm gate first. Zero instances DB-wide. |
| **Claim 3b** — the voice pipeline | No STT model is registered, the UI's model picker is empty, and the endpoint fails before persisting anything. Also unreachable through the UI proper: the harness has no speech input. |
| **Claim 3a via the UI** | The proactive toggle arms a cron schedule; there is no on-demand UI trigger. Armed via UI, fired via the scheduler's endpoint. Disclosed. |

Runs A–D were all performed against the correct build, all through the real UI.

---

## 8. Summary of raw artefacts

| item | value |
|---|---|
| commit under test | `8aa01a77a` (container **was stale — 4th consecutive round**; rebuilt, force-recreated, hash-verified before, after, and after the kill cycle) |
| throwaway book | `CP0-VLIVE-R4-THROWAWAY` / `019fcaa4-856f-7206-8bc3-d3a81d71e065` |
| primary session | `019fcaa6-10b2-76e4-84ae-842e4198b250` (universal `/chat`) |
| book-scoped session | `019fcac6-8c70-70f4-9593-2822dba0e97d` (studio) |
| proactive session | `019fcad4-0346-7621-ab18-3b8d90b1313a` |
| run A message | `cda298e8-21f7-4b86-bce7-a1bda17d54e1` — 19 passes, 33 withheld, 18 call entries, `completed`, **5 silent removals recorded, 254 tools unaccounted for** |
| run B message | `8dad348e-5e5b-4d65-8fc1-92963ed42734` — 2 passes, 178 withheld, `completed`, **11 same-pass contradictions (6.2%, unchanged)** |
| run C message | `c22d4d40-d29a-4f0d-87f8-a670c1076057` — `abandoned_by_user`, 456 chars, real UI stop at 4.1 s |
| run C defect row | seq 6, `883f330c-2463-45ac-a69e-4e3a98269458` — `abandoned_by_user` **with no user cancel** |
| run D message | `4ce53500-cd3c-40fd-8f5c-7136ecf7482a` — `crashed`/`streaming`, 4 passes, 28 withheld, 4 calls, survived restart |
| proactive message | `019fcad4-0346-7e80-a61a-1dfaaeb5c6b9` — `initiated_by='assistant_proactive'`, **`outcome='completed'`** |
| `interrupt-persist failed` | **0** across 2 cancels |
| `pass_offered_no_tools` rows, all time | **0** |
| advertised passes with `names=[]`, all time | **0** |
| withheld stages ever written, all time | `token_budget`, `failure_breaker` — **and nothing else** |
| database | `loreweave_chat` in `infra-postgres-1`, user `loreweave` |

No fixes are proposed, per the brief.
