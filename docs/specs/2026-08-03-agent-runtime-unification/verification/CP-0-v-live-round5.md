# CP-0 · V-LIVE — round 5 verdict

**Artifact under test:** `711f94c61` (frozen)
**Driven:** real UI (Playwright-driven Chrome against `http://localhost:5174`), not the API
**Throwaway book:** `VLIVE-R5 Throwaway (CP-0 verification)` — `019fcaf0-59fe-7047-9ce1-482bd6885487`
**Sessions used:** `019fcaf2-7716-7cf7-8a6a-424d2edf99d2`, `019fcafc-bef1-7594-abe4-1d994c160de7`
**Account:** `claude-test@loreweave.dev` (`019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)

## Overall verdict: **FAIL**

| | verdict |
|---|---|
| **Run A · clean** | **PASS** |
| **Run B · withheld** | **PASS** |
| **Run C · cancelled** | **FAIL** |
| **Run D · killed** | **FAIL** |
| Claim 1 · surface-assembly narrowing | **PASS** — 0 unaccounted (was 254) |
| Claim 2 · advertised/withheld overlap | **PASS on observed evidence**, with a stated blind spot |
| Claim 3 · `tool_calls` double-counting | **PASS** — and round 4's finding was a misread |
| Claim 4 · `abandoned_by_user` | **CONFIRMED STILL BROKEN** |

---

## 0. PRECONDITION — the container was stale for the FIFTH round running

I hashed the repo tree against the container **before driving anything**. It did not match.

```
$ cd services/chat-service && find app -name '*.py' -type f | sort | xargs sha256sum | sha256sum
87fa564e4ec12f4d4746dd92be083ac77751855121eb0ca7d8298ba9cd847517   (107 files)

$ docker exec infra-chat-service-1 sh -c "cd /app && find app -name '*.py' -type f | sort | xargs sha256sum | sha256sum"
f52db91ae75d683970abb309f50aed1b3e39e9df4f3c20400ea774ac6f9c5b65   (107 files)
```

Per-file diff — exactly the three CP-0 files, and nothing else:

```
71c71 < instrument.py            6e0c53eb…  |  > 7a282c4e…
89c89 < stream_service.py        2d8077f3…  |  > f4922bcd…
102c102 < voice_stream_service.py 7aed2753… |  > b2e62fbf…
```

Normalising line endings (the Windows worktree is CRLF, git blobs are LF) identifies the running
commit exactly:

| file | container (normalised) | = git blob at |
|---|---|---|
| `instrument.py` | `876f8377e07f381e…` | **`8aa01a77a`** |

The container was running **`8aa01a77a`** — *four* commits of CP-0 changes behind the frozen artifact,
and missing **both** round-5 decisive fixes:

- `88ac07fca` — "the sink was armed 435 lines too late" (the claim-1 fix)
- `4559488eb` — "a tool the model could see is no longer reported as withheld" (the claim-2 fix)

The container reported `Up 41 minutes` — it had been **restarted but not rebuilt**. Uptime is not
evidence; only a hash is.

**Remediation, then re-verification:**

```
$ docker compose -f infra/docker-compose.yml build chat-service
$ docker compose -f infra/docker-compose.yml up -d --force-recreate --no-deps chat-service
$ diff <repo per-file hashes> <container per-file hashes>
IDENTICAL — 107/107 files match
$ docker exec infra-chat-service-1 sh -c "tr -d '\r' < /app/app/services/instrument.py | sha256sum"
fc74d8bc240df111b8dd83428eec45293e412c6a092b7a8a0d0f72224a580344
```

I re-checked at the **end** of the run (the container was killed and restarted for run D), against the
frozen blob rather than the worktree:

```
instrument.py           MATCH frozen (fc74d8bc…)
stream_service.py       MATCH frozen (470575d0…)
voice_stream_service.py MATCH frozen (4c3f42a9…)
POST-RUN: container still IDENTICAL to frozen artifact (107/107)
```

Every result below was produced against the frozen artifact. This is the first round where that is
true, and it is why several round-4 findings do not reproduce.

> **The artifact was retracted while I was running.** `HEAD` moved from `711f94c61` to `8539b9a1d`
> ("*I shipped a fabricated record and two data-deleting fixes — all three retracted*") mid-verification.
> I did not read the commit body. My verdict is about `711f94c61` as frozen, which is what I was asked
> to verify and what the container ran throughout. The retraction post-dates and partially contradicts
> my claim-2 finding; see §3.

---

## 1. Claim 1 — the surface-assembly narrowing: **0 unaccounted (PASS)**

I repeated the round-4 accounting exactly: derive the catalogue from **the turn's own `tool_list`
result**, then set-difference it against every name ever advertised or withheld in that turn.

Run A turn: session `019fcaf2…`, `sequence_num=2`. The turn's own output declares its size:

```
$ SELECT e->>'result' FROM chat_messages m, jsonb_array_elements(m.tool_calls) t(e)
  WHERE m.session_id='019fcaf2-7716-7cf7-8a6a-424d2edf99d2' AND e->>'tool'='tool_list' …
{"count": 307, "categories": {"book": [{"name": "book_audio_generate", …
```

```
catalogue declared count : 307
catalogue distinct names : 307
advertised entries       : 13   passes 1..13
withheld entries (total) : 294   distinct tools: 286
ADV union : 32   WH union : 286   ADV|WH : 317
>>> UNACCOUNTED FOR (catalogue − (adv ∪ wh)) : 0
in adv/wh but NOT in catalogue : 10  ['chat_search_sessions','confirm_action','conversation_search',
   'load_skill','run_subagent','tool_list','tool_load','web_search','workflow_list','workflow_load']
```

**Round 4: 254 unaccounted. Round 5: 0.** The stated falsifier ("a number greater than zero is a
FAIL") is not met.

The partition at the pass where the full catalogue is the candidate pool is **exact**:

```
pass 3: adv=32  wh=285  →  32 + 285 = 317 = 307 catalogue + 10 kit/meta tools
        same-pass overlap = 0,  unaccounted = 0
```

Every name lands in exactly one bucket, once. That is a complete, disjoint, exhaustive partition of
the whole universe — the strongest form this accounting can take.

Pass-1 withheld entries now **exist** (round 4 found zero across all 16 rows):

```
 pass |      stage      |                     reason                       | count
------+-----------------+--------------------------------------------------+-------
 1    | hot_seed        | did not fit the hot_seed token budget (2000 tok) |     8
 3    | token_budget    | did not fit the activation token budget          |   285
 6    | failure_breaker | repeated-failure breaker gave up on this tool    |     1
```

### The defect CP-0 was built for — caught

The advertised count moves **32 → 31 at pass 6**, and pass 6 carries exactly one withheld entry:

```json
{ "pass": 6, "tool": "book_update_details",
  "stage": "failure_breaker", "reason": "repeated-failure breaker gave up on this tool" }
```

A tool the model was holding was silently deleted from the offered set mid-turn — and the record
shows **both states**, names the tool, the stage, and the reason. This is the recorded historical
defect, reproduced in production and caught.

### Residual (reported, not scored against the stated falsifier)

At passes that never reach the `token_budget` stage, only the hot-seed candidate pool is accounted
for — run A pass 1 covers 37 of 307; run B pass 1 covers 59 of 307. The remaining ~270 are the lazy
tail, reachable via `tool_list`/`tool_load` (the model demonstrably retrieved all 307 that way), so
they were never offered-then-removed and calling them "withheld" would be wrong. But **the record
does not say that.** An outsider reading pass 1 alone sees 29 advertised + 8 withheld and cannot tell
whether 270 more existed and were dropped or were never in scope. The `stage` field is the only
discriminator and it is implicit. I am flagging this as an inference I had to make.

---

## 2. Claim 2 — the 11/178 overlap: **zero now, and evidence was not deleted (PASS, with a blind spot)**

**Same-pass overlap is genuinely zero**, across all 13 passes of run A:

```
pass 1: adv=29 wh=8   SAME-PASS OVERLAP=0
pass 3: adv=32 wh=285 SAME-PASS OVERLAP=0
pass 6: adv=31 wh=1   SAME-PASS OVERLAP=0
… all 13 passes: 0
```

The one union-level overlap (`book_update_details`, advertised passes 3–5, withheld pass 6) is the
legitimate mid-turn removal above — a state change, not a contradiction.

**Did the reconciliation delete evidence?** Measured against prior rounds, using the rows still in
`loreweave_chat`:

```
ts                    outcome      advE   whE   same-pass-overlap
2026-08-04 01:37:45   completed       3   178     11     ← round-4 era
2026-08-04 02:50:41   completed       2   178     11     ← round-4 era
2026-08-04 03:04:57   awaiting_input  7    28      1
2026-08-04 03:14:38   crashed         4    28      5
2026-08-04 04:06:34   completed      13   294      0     ← round 5, frozen artifact
```

Withheld entries went **up** — 178 → 294 in a single row, a 65% increase — while overlap went to
zero. Deleting evidence would have moved that number down. Corroborated structurally by the exact
pass-3 partition (32 + 285 = 317, nothing missing).

**What the reconciliation actually resolved.** All 11 pre-fix overlapping entries were at the *same
pass* **and the same stage**:

```
 pass |          tool           |    stage     |                 reason
------+-------------------------+--------------+-----------------------------------------
    2 | glossary_deep_research  | token_budget | did not fit the activation token budget
    2 | kg_entity_edge_timeline | token_budget | did not fit the activation token budget
    2 | kg_graph_query          | token_budget | did not fit the activation token budget
    … 11 rows, all pass 2, all stage token_budget
```

All 178 entries in that row are `pass 2 / token_budget`. A tool cannot both fit and not fit the same
budget at the same stage — that is a real contradiction, and since there is only one stage in play,
dropping the withheld side loses **no distinct information**. Post-fix, `hot_seed` withholdings live
at pass 1 and `token_budget` withholdings at pass 3, so the two stages never collide.

### Blind spot — stated plainly

My set-difference **cannot detect** a withheld entry dropped when the tool is withheld at stage X but
advertised at stage Y *within the same pass*: the name still appears in `advertised_tools`, so it
stays "accounted for" and the lost stage/reason is invisible to this method. I did not observe such a
case in the frozen artifact, so I cannot rule it out. This is exactly the shape of "deleted evidence
rather than resolved contradiction," and my PASS is conditional on it not occurring.

The builder's own `8539b9a1d` retracts two fixes as "data-deleting." I did not read the reasoning. A
verifier and a builder disagreeing on this point should be resolved by someone who can see both — my
evidence is turn-shape-specific and my method has the blind spot above.

---

## 3. Claim 3 — `tool_calls` double-counting: **PASS**, and round 4's finding was a misread

**Distinct calls are not collapsed.** Post-fix, session `019fcafc…` `sequence_num=31`:

```
 ord | iter |        tool         | src  |                args                  |          id
-----+------+---------------------+------+--------------------------------------+-----------------------
   1 | 0    | tool_list           | meta | {"category": "all"}                  | call_4274648666862588
   2 | 0    | kg_project_create   | tool | {"name": "temp_project_for_listing"} | call_4274648666862589
   3 | 0    | workflow_list       | meta | {}                                   | call_4274648666862590
   4 | 0    | memory_search       | tool | {"query": "compass"}                 | call_4274648666862591
   5 | 0    | tool_load           | meta | {"category": "composition"}          | call_4274648666862592
   6 | 0    | kg_schema_read      | tool | {}                                   | call_4274648666862594
   7 | 0    | book_update_details | tool | {"book_id": "book_list", …}          | call_4274648666862595
```

**Seven distinct calls at iteration 0, all preserved, all with distinct call ids.** The dedupe is not
keyed on iteration.

Run A additionally preserves **identical tool + identical args across iterations** — seven
`book_chapter_save_draft` entries with byte-identical `{"body":"","book_id":"book_list"}` at
iterations 5–11, and two identical `book_update_details` at iterations 2 and 3. The dedupe is not
keyed on `(tool, args)` either.

**Round 4's "18 entries for 17 iterations" was not a double-count.** Measuring the actual
double-count signature — entries vs *distinct call ids* — across every instrumented row today:

```
         ts          | entries | distinct_ids | excess
 2026-08-04 02:42:38 |      18 |           18 |      0     ← the row round 4 flagged
 2026-08-04 02:59:53 |      20 |           20 |      0
 2026-08-04 03:18:02 |      19 |           19 |      0
 2026-08-04 04:06:34 |      12 |           12 |      0
 2026-08-04 04:58:10 |       7 |            7 |      0
 … 37 rows, excess = 0 everywhere
```

That row has 18 entries and **18 distinct call ids** over 17 iterations — one iteration legitimately
carried two calls. Iterations are not 1:1 with calls; treating them as such produced round 4's
finding. There was no double-count to fix, and the dedupe added has not introduced a collapse.

Only untested case: same tool + same args + same iteration, which would be an indistinguishable
duplicate. Five attempts across two models failed to elicit it from the local model.

---

## 4. Claim 4 — `abandoned_by_user`: **CONFIRMED STILL BROKEN**

Reproduced. A closed browser tab — a pure connection drop, the user never pressed stop — is recorded
identically to a deliberate cancel.

```
$ SELECT sequence_num, outcome, finish_reason, is_error, error_detail, initiated_by, …
  FROM chat_messages WHERE session_id='019fcafc-…' AND sequence_num IN (16,27);

-[ RECORD 1 ]---+------------------      -[ RECORD 2 ]---+------------------
sequence_num    | 16  (STOP BUTTON)      sequence_num    | 27  (TAB CLOSED)
outcome         | abandoned_by_user      outcome         | abandoned_by_user
finish_reason   | interrupted            finish_reason   | interrupted
is_error        | f                      is_error        | f
error_detail    |                        error_detail    |
initiated_by    | user                   initiated_by    | user
runtime_variant | legacy                 runtime_variant | legacy
response_id     |                        response_id     |
input_tokens    |                        input_tokens    |
output_tokens   |                        output_tokens   |
has_ctx         | f                      has_ctx         | f
content_len     | 244                    content_len     | 0
tc              | 0                      tc              | 1
```

**Is there any signal that distinguishes the two? No.** Every semantic field is identical. The three
that differ — `content_len`, `tc`, `adv` — record *how far the turn got*, not *why it ended*: a user
who cancels instantly also yields `content_len=0`, and a connection dropped late also yields
`content_len>0`. Neither direction is a discriminator. The service logs are identical too; both emit
`interrupt-persist detached … (write continues after cancel)`.

Nothing in the recorded data distinguishes them. Confirmed unresolved, as documented.

**Not reproduced:** the *second-tab* variant specifically. Three attempts (external tab, and
`window.open` from the streaming page at a controlled 6s into the stream) all completed normally
(`completed`/`stop`). Round 4's second-tab case did not recur against the frozen artifact; the
defect surfaces on tab **close**, not tab **open**.

---

## 5. Run A · clean — **PASS**

`advertised_tools` present per pass (13 passes), an outcome, and every `tool_calls` entry carrying
`source` and `latency_ms`. The brief's four questions, answered **from the record alone**:

1. **What was the model holding on its second pass?** `advertised_tools` → `pass 2`, 29 named tools,
   `tool_choice: auto`. Directly readable.
2. **Was anything hidden from it?** Yes — 294 withheld entries with `pass`, `tool`, `stage`, `reason`.
3. **Did the third result come from a tool or from our own breaker?** From a tool. Entry 3 is
   `source: "tool"`, `latency_ms: 20`. Entries 5–12 are `source: "breaker"`, each with
   `source_inferred: true` and `latency_unmeasured: "breaker"`. The instrument is explicit about
   which fields are inferred rather than measured — I did not have to guess.
4. **How did the turn end?** `outcome=completed`, `finish_reason=stop`.

All four answered without reading code. Two small shape notes: the field is `tool`, not `name`; and
the pending-approval entry (run B) uses `toolCallId`/`runId` where every other entry uses
`id`/`iteration`.

## 6. Run B · withheld — **PASS**

`withheld_tools` is not an empty array and names tool, stage and reason:

```json
{"pass":1,"tool":"kg_add_nodes","stage":"hot_seed","reason":"did not fit the hot_seed token budget (2000 tok)"}
```

Run B itself (session `019fcaf2…` seq 4): `pass 1`, 23 advertised, 36 withheld at `hot_seed`,
outcome `awaiting_input`.

**Out-of-scope defect found here.** The pending tool-approval entry is stamped `source: "breaker"`:

```json
{"ok": false, "tool": "kg_propose_fact", "pending": true, "source": "breaker",
 "source_inferred": true, "latency_unmeasured": "breaker", "kind": "tool_approval"}
```

The call was not refused by the breaker — it is awaiting user confirmation. An outsider reading this
record concludes the breaker gave up. `source_inferred: true` honestly flags it as a guess, but the
guess is wrong, and `source` is precisely the field CP-0 exists to make trustworthy.

## 7. Run C · cancelled — **FAIL**

**Cancel *with* content works.** Stop clicked 17.2s in, after 475 chars had streamed:

```
 16 | assistant | abandoned_by_user | interrupted | len=244
```

**Cancel *before* content records nothing at all.** Two cancels at ~1.3s and ~1.6s into the stream
(the model finishes in ~2.5s, so these are genuinely mid-stream) left **orphaned user messages with
no assistant row whatsoever**, after 80s+ of polling:

```
 seq | role      | outcome           | len
  11 | user      |                   | 240      ← RUN-C3, cancelled: NO REPLY ROW, EVER
  14 | user      |                   | 226      ← RUN-C5, cancelled: NO REPLY ROW, EVER
```

The service names the defect itself:

```
INFO: CP-0.4 silent-exit: empty terminal turn recorded nowhere
      (session 019fcafc-…, msg ddb54102-…, reason=interrupted).
      Closes at CP-3.6 with the other three silent exits.
INFO: interrupt-persist detached for session 019fcafc-… (write continues after cancel)
```

The write is detached, logged, and then never lands — no completion log, no error, no row. From the
database an outsider cannot tell the turn ever happened, let alone that a user abandoned it. The
brief's bar is "a terminal outcome that distinguishes *the user abandoned this* from *this broke*";
this is below even "`interrupted` alone". Self-identified and deferred to CP-3.6, but it is a run-C
failure today.

## 8. Run D · killed — **FAIL**

`docker kill` landed at `04:39:11`, two seconds into a streaming turn started at `04:39:09`.

```
 seq | role | outcome | finish_reason | len
  19 | user |         |               | 372     ← killed mid-turn
```

Container restarted and `healthy` at `04:40:11`. Then, polled for **160 seconds**:

```
t+20s: 0    t+60s: 0    t+100s: 0   t+140s: 0
t+40s: 0    t+80s: 0    t+120s: 0   t+160s: 0     (rows with sequence_num >= 20)
```

No reconciliation, no `crashed` outcome, no recovery log (`grep -iE 'recover|reconcil|orphan|stale|
crash|resume|suspend'` → nothing). The turn sits permanently in a non-terminal state with nothing
recorded — the exact condition run D exists to detect.

The UI agrees, and offers the user nothing:

```
tail_after_RUND2: "…Do not stop until every step is done.\n\n11:39:08 AM\n\nNGỮ CẢNH\n10 công cụ…"
has_spinner: false,  stop_button_present: false,  send_disabled: true
```

The question is rendered with no answer, no error and no spinner. Note `crashed` **is** reachable for
in-process failures (rows at 00:21, 02:05, 03:14) — it is the container-death path that reconciles
nothing.

---

## 9. The falsifier

What I looked for that would have made this FAIL — and in two places, did:

1. **Claim 1:** any tool in the turn's own `tool_list` output absent from both `advertised_tools` and
   `withheld_tools`. **A single unaccounted name is a FAIL.** Result: 0 of 307. Passed.
2. **Claim 2:** withheld volume *falling* relative to round 4, or the pass-3 partition summing to less
   than the full universe — either would show the overlap fix deleted records instead of resolving a
   contradiction. Result: 178 → 294 (up), and 32 + 285 = 317 exactly. Passed, with the stated blind
   spot.
3. **Claim 3:** any row where entries exceed distinct call ids (collapse or duplication), or a turn
   with two genuine calls in one iteration showing one entry. Result: excess = 0 across 37 rows; 7
   calls at iteration 0 all preserved. Passed.
4. **Runs C and D:** a cancelled or killed turn leaving no terminal record. **Both failed this.** A
   cancel before first token writes nothing; a container kill reconciles nothing.
5. **Claim 4:** any recorded field separating a dropped connection from a deliberate cancel. Result:
   none exists. Confirmed broken.

A note on my own method: I derived the catalogue size from the turn's own output rather than from any
source I control, and I set-differenced rather than spot-checked, precisely so that a PASS could not
come from a denominator I chose. The blind spot in §3 is where that discipline runs out, and I have
named it rather than let the zero speak for itself.

## 10. Out of scope

- **Pending approvals mislabelled `source: "breaker"`** (§6). Wrong attribution in CP-0's own field.
- **`crashed` appears as a transient pre-stamp.** Polling caught `outcome=crashed, finish_reason=streaming`
  on in-flight turns that then settled to `completed` (04:06, 04:19, 04:50, 04:58). Fail-safe and
  sensible, but any consumer reading mid-flight will see a turn that "crashed" and then did not.
- **Withheld entries with no `pass` key** in rows before ~00:55 (332 of them) — an older on-disk
  format sharing a column with the new one. Anything aggregating `withheld_tools` across history must
  tolerate both.
- **Two orphaned user messages** (seq 11, 14) left in session `019fcafc…` by the run-C cancels, and
  one (seq 19) by the run-D kill. All in the throwaway session; no dogfood data touched.
- **Frontend console errors** accumulated during streaming/cancel cycles (1→4 over the session). Not
  investigated.

## 11. Queries used

```sql
-- instrumented columns for a turn
SELECT sequence_num, role, outcome, finish_reason, runtime_variant, is_error, content
FROM chat_messages WHERE session_id='019fcaf2-7716-7cf7-8a6a-424d2edf99d2' ORDER BY sequence_num;

-- the turn's own catalogue, for the set-difference
SELECT e->>'result' FROM chat_messages m, jsonb_array_elements(m.tool_calls) t(e)
WHERE m.session_id='019fcaf2-…' AND m.role='assistant'
  AND e->>'tool'='tool_list' AND length(e->>'result')>1000 LIMIT 1;

-- withheld, by pass/stage/reason
SELECT w->>'pass', w->>'stage', w->>'reason', count(*)
FROM chat_messages m, jsonb_array_elements(m.withheld_tools) t(w)
WHERE m.session_id='019fcaf2-…' AND m.role='assistant' GROUP BY 1,2,3 ORDER BY 1::int;

-- tool_calls with provenance
SELECT ord, e->>'iteration', e->>'tool', e->>'source', e->>'latency_ms', e->>'ok',
       e->>'source_inferred', e->>'latency_unmeasured', e->>'id'
FROM chat_messages m, jsonb_array_elements(m.tool_calls) WITH ORDINALITY t(e,ord)
WHERE m.session_id='019fcaf2-…' AND m.role='assistant';

-- double-count signature: entries vs distinct call ids
SELECT m.created_at::timestamp(0), jsonb_array_length(m.tool_calls) AS entries,
       count(DISTINCT coalesce(e->>'id', e->>'toolCallId')) AS distinct_ids,
       jsonb_array_length(m.tool_calls) - count(DISTINCT coalesce(e->>'id', e->>'toolCallId')) AS excess
FROM chat_messages m, jsonb_array_elements(m.tool_calls) t(e)
WHERE m.role='assistant' AND m.tool_calls IS NOT NULL AND m.created_at > '2026-08-04 00:00:00'
GROUP BY 1,2 ORDER BY 1;

-- pre-fix overlap: tools both advertised and withheld in the same pass
WITH r AS (SELECT withheld_tools, advertised_tools FROM chat_messages
           WHERE created_at::timestamp(0)='2026-08-04 02:50:41'),
adv AS (SELECT (p->>'pass')::int AS pass, jsonb_array_elements_text(p->'names') AS nm
        FROM r, jsonb_array_elements(r.advertised_tools) p),
wh  AS (SELECT (w->>'pass')::int AS pass, w->>'tool' AS tool, w->>'stage' AS stage, w->>'reason' AS reason
        FROM r, jsonb_array_elements(r.withheld_tools) w)
SELECT wh.pass, wh.tool, wh.stage, wh.reason FROM wh JOIN adv ON adv.pass=wh.pass AND adv.nm=wh.tool;

-- cancel vs dropped-connection comparison
SELECT sequence_num, outcome, finish_reason, is_error, error_detail, initiated_by, runtime_variant,
       length(content), response_id, input_tokens, output_tokens,
       jsonb_array_length(coalesce(tool_calls,'[]'::jsonb)),
       context_breakdown IS NOT NULL
FROM chat_messages WHERE session_id='019fcafc-…' AND sequence_num IN (16,27);
```

## 12. What would close this

Not proposing fixes, per the brief — stating what a future round must *observe*:

- A cancel landing before the first token that leaves a terminal row (run C).
- A container kill mid-turn that reconciles to a terminal outcome after restart (run D).
- Any recorded field that separates a dropped connection from a deliberate cancel (claim 4).
- A turn where a tool is withheld at one stage and advertised at another **within the same pass**,
  to close the blind spot in §3 that my method cannot see.
- And, before any of it: a hash check of the container against the artifact. Five rounds, five stale
  containers. Nothing above would have been true of the running system had I not rebuilt first.
