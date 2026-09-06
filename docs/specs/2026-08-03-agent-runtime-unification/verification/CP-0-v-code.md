# CP-0 · V-CODE — verdict

Source-only review. Nothing was run; no service was started; no tracked file was modified.
Commit messages and rationale documents were not read — the artifact was graded, not its defence.

---

## 1. Verdict

**Overall: `FAIL`.**

| item | claim | verdict |
|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | **FAIL** — mechanism correct, coverage is not |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | **FAIL** — the reporting variant has zero production callers |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | **FAIL** — a real dispatch is recorded as `breaker`; `latency_ms` is null on all but one mint site |
| 0.4 | every terminal path writes an outcome | **FAIL** — four paths write none, one writes a stale success |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | **PASS** (two findings) |
| 0.6 | binding-format measurement scripted **and its output committed** | **FAIL** — script yes, output does not exist |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | **PASS** on the literal claim (two vacuity findings) |

The headline claim is *"on **every** path, with **no path that skips them**."* Five distinct skipping
paths are named below with `file:line`. The instrument's **core mechanisms are well-built** — the
per-pass recorder appends rather than overwrites, and `source` does not default to `tool`. Those were
my two sharpest falsifiers and both survived. What fails is reach: the instrument is wired into one
of the service's two turn pipelines, and the single mechanism it was justified by (the token
budgeter) is not wired into it at all.

---

## 2. The falsifier

What I looked for that would have made this FAIL, stated before the findings so the PASSes are
readable:

1. **`advertised_tools` overwritten rather than appended** (brief §5). *Not found.*
   `AdvertisedToolsRecorder.record_pass` appends with `"pass": len(self._passes) + 1`
   (`instrument.py:181-189`), the producer yields one event per iteration of the `while True:` pass
   loop (`stream_service.py:1985` → `2219`/`2249`), and both INSERTs use
   `COALESCE(EXCLUDED.advertised_tools, chat_messages.advertised_tools)`
   (`stream_service.py:6144`, `7112`) so a mid-turn checkpoint cannot erase earlier passes. This is
   correct and it is the hardest part of CP-0.1 to get right.
2. **`source` defaulting to `tool`** (brief §6). *Not found.* `ensure_tool_call_instrumented`
   assigns `meta` (closed name set) or `breaker`, never `tool`, and flags the row
   `source_inferred: true` (`instrument.py:137-140`). `stamp_tool_call` raises on an unknown source
   (`instrument.py:98-99`).
3. **DDL appended to an already-applied ledger step** (brief §2 — the flagged likely failure).
   *Not applicable here, and I checked specifically.* `services/chat-service/app/db/migrate.py` is
   **not** a ledger: it is one `DDL = """…"""` string (lines 3-784) executed in full on every boot by
   `run_migrations` (`migrate.py:787-789`). There is no version table, no step list, no
   applied-marker. The four new statements are `ADD COLUMN IF NOT EXISTS` (`migrate.py:319`, `327`,
   `344`, `359`) and will therefore apply on the next start. *How I searched:* read the file end to
   end for a chain/step/version construct, and read the runner. The repository rule the brief cites
   is real but belongs to the Go services' ledgers, not to this one.
4. **A production call site that still discards the budgeter's drops.** *Found — all of them.* See
   0.2.
5. **A terminal path that writes no outcome, or leaves a stale one.** *Found — see 0.4.*
6. **A real dispatch classified as non-`tool`.** *Found — see 0.3.*
7. **Committed output for the 0.6 measurement.** *Looked for; it does not exist.*

Two things I **could not determine from source** and am not claiming either way:

- Whether the recorded *values* are right. All four columns are **write-only** (finding F-8): no
  query, model field, router, or script in the repository reads `advertised_tools`,
  `withheld_tools`, `outcome`, or `runtime_variant` back. Correctness of content is a V-LIVE /
  V-METRIC question; from source I can only show the writes exist.
- The real-world frequency of the D7 forced-tool-free pass (0.1 bypass B) — it depends on how often
  turns exhaust `max_iterations`, which source cannot tell me.

---

## 3. Findings

### F-1 · `budget_names_by_tokens_ex` has no production caller (kills 0.2)

`tool_surface.py:125-147` adds a `(kept, dropped)` variant, documented as closing "the founding
defect of the runtime rebuild" — arm E, where the budgeter deleted `book_list` and returned only
survivors. `migrate.py:321-327` cites that same mechanism as the reason `withheld_tools` exists.

Every production call site still calls the **plain** function and throws the drops away:

- `stream_service.py:2900`, `3006`, `3098`, `3267` (four `budget_names_by_tokens(...)` calls in the
  tool-loop auto-load paths)
- `tool_surface.py:336`, `383`, `424`, `553` (hot-seed, plan-hot, extra-hot, and the main surface
  build)

The only callers of `_ex` in the entire repository are `eval/arms/run_arms.py:118` and
`tests/test_cp0_instrument.py:108,120`. Search: `grep -rn "budget_names_by_tokens" --include=*.py .`
over the whole tree — 20 hits, zero production `_ex`.

Its sibling `budget_rail_tools` does return drops, but they go to `logger.warning`
(`tool_surface.py:479-483`), not to `withheld_tools`.

**Consequence:** `withheld_tools` records five stages (`oneshot_*`, `rail_gate`, `failure_breaker`,
`suppress_tool_list`, `permission_mode_*` — `stream_service.py:2163-2207`) and **not** the token
budgeter. The one narrowing CP-0.2 was justified by is the one narrowing it does not capture. The
claim's second clause is satisfied as a function signature and falsified as behaviour.

### F-2 · A real MCP dispatch is recorded as `breaker` (kills 0.3)

`instrument.py:124-131` states: *"`source='tool'` is assigned at exactly one place — the site where a
dispatch actually executes — so having run is a structural fact here, never an inference."*

There are **three** real-dispatch sites. Two stamp:

- `stream_service.py:3415` — subagent run, `source=SOURCE_TOOL` (no latency)
- `stream_service.py:4599-4601` — in-loop dispatch, `source=SOURCE_TOOL, latency_ms=_dispatch_ms`

The third does not:

- `stream_service.py:7645-7684` — the **approved Tier-A resume path**. It calls
  `knowledge_client.mcp_execute_tool(...)` (a real execution against MCP), builds `_chunk` at
  `7660-7665` with no `instrument.stamp_tool_call`, and hands it out as `pre_tool_chunks`
  (`7684`). That list is appended to `tool_calls_history` unmodified at `stream_service.py:6378`.

At persistence, `ensure_tool_call_instrumented` sees no `source`, finds the tool name is not in
`RUNTIME_PRIMITIVES`, and writes `source="breaker"` — *"our code declined, capped, or repaired — no
tool ran"* (`instrument.py:35`, `139`). Every user-approved Tier-A write is therefore filed as our
own prose, which is the exact miscount the field exists to prevent, running in the opposite
direction. To the implementation's credit, `source_inferred: true` makes these rows findable — the
mitigation the docstring promises works; the classification it promises does not.

### F-3 · `latency_ms` is null on all but one mint site (0.3)

`ensure_tool_call_instrumented` does `chunk.setdefault("latency_ms", None)` (`instrument.py:143`).
Of the ~30 `yield {"tool_call": …}` sites in `stream_service.py` (2953, 2974, 3056, 3072, 3131,
3151, 3217, 3295, 3321, 3350, 3416, 3434, 3505, 3524, 3581, 3671, 3747, 3785, 3845, 3878, 3898,
3940, 4010, 4094, 4179, 4203, 4225, 4273, 4345, 4602), exactly **one** supplies a latency (4599).
The claim "carries `latency_ms`" is true only in the sense that the key is present. A row rendering
null is present, and blank.

### F-4 · The empty terminal turn writes nothing, by documented exemption (0.4)

`stream_service.py:6085-6098`. `_persist_terminal_assistant` returns `False` before any write when
`not content and not reasoning and not tool_calls_history`, with a comment naming itself
*"CP-0.4, KNOWN HOLE, DELIBERATELY NOT CLOSED HERE … one of the four silent exits."*

This is precisely the brief's hunting ground #1 — a new gate shipping its own documented exemption.
It is honestly labelled and logged, which is better than silence, but the item claims *every*
terminal path and this one is exempted at the chokepoint that all five terminal callers route
through (`6199`, `6694`, `6841`, `7258`, `7295`).

### F-5 · An abandoned suspend keeps `outcome='awaiting_input'` — a success state (0.4)

`stream_service.py:6234-6238`:

```
elif row["finish_reason"] == "awaiting_input":
    await pool.execute(
        "UPDATE chat_messages SET finish_reason = 'interrupted' WHERE message_id = $1",
        susp.message_id,
    )
```

`finish_reason` is corrected; `outcome` is not touched. The row was written at suspend time with
`outcome=OUTCOME_AWAITING_INPUT` (`6852`), documented at `6849-6851` as *"a SUCCESS state (§0.5), not
a stall."* After abandonment the row still says so.

This is the branch the function's own docstring calls the **preferred** path (`6221-6224`); the
sibling branch — reached only when no provisional row exists — *does* set `abandoned_by_user`
(`6215`). So the dominant abandonment case is recorded as a success and the rare one is recorded
correctly. Reached from `stream_service.py:7432` (expired/refused resume).

Compounding: `sweep_expired_runs` (`db/suspended_runs.py:187`) has **no caller** anywhere in the
service (`grep -rn "sweep_expired_runs" services/chat-service/` → one hit, the definition). A user
who simply never returns to a confirm card leaves a row at `awaiting_input` permanently.

### F-6 · The voice turn pipeline records none of the four fields (0.1, 0.3, 0.4)

`voice_stream_service.py:578-587` is a second, complete assistant-turn INSERT into `chat_messages`.
Its column list is `(message_id, session_id, owner_user_id, role, content, content_parts,
sequence_num, model_ref, branch_id, local_date)` — no `outcome`, no `advertised_tools`, no
`withheld_tools`, no `tool_calls`.

This is not a tool-free path: `voice_stream_service.py:440-463` calls the shared
`_stream_with_tools` with `permission_mode='ask'`, so it emits `{"advertised": …}` events. Its
consumer loop at `465-492` reads only `content` / `reasoning_content` / `usage` / `suspend` /
`tool_call`; the `advertised` chunk falls through `chunk_data.get("content", "")` and is silently
discarded (no crash — the `.get` at `470` absorbs it). Its `tool_call` chunks are emitted as SSE at
`489-492` and **never persisted at all**.

So: every voice turn has `outcome IS NULL`, and every tool a voice turn calls exists in no
`tool_calls` row. `runtime_variant` survives only because the DDL `DEFAULT 'legacy'`
(`migrate.py:359`) is the fail-safe direction — which is the one place the design's caution pays off
on this path.

A third assistant-row writer, the proactive check-in at `routers/internal.py:926-929`, likewise
writes no `outcome`.

### F-7 · Passes with `offered_tools == False` emit no record, contradicting the comment (0.1)

The entire CP-0.1/0.2 emit block (`stream_service.py:2145-2249`) sits inside `if offered_tools:`
(`2063`), where `offered_tools = tools_supported and not last_iter` (`2062`, `2025`, `1839`).

The comment at `2152-2153` claims: *"Emitted for a tool-FREE pass too (`names: []`). 'The model was
offered nothing' and 'the model was never asked' are different facts."* That is true only for a pass
that reached the filter and came out empty. It is **false** for the two ways a pass is genuinely
tool-free:

- **D7 forced-final pass** (`last_iter`, `2025`) — the pass that produces the user-visible answer
  after a tool loop. Unrecorded.
- **D8 provider tool rejection** (`tools_supported = False`, `2439`) — every pass after it is
  unrecorded, and `advertised_tools` silently keeps only the pre-rejection passes.

Consequence: the `pass` ordinals in the column do not correspond to the turn's model-call count, and
the concluding pass is missing whenever D7 fires. The plain path `_stream_via_gateway`
(`stream_service.py:6654`) also emits nothing — that one is defensible under the documented
`None` ≠ `[]` semantics (`instrument.py:215-223`).

### F-8 · All four columns are write-only

Repository-wide search across `*.py *.ts *.tsx *.go` for `advertised_tools|withheld_tools|
runtime_variant` returns only `migrate.py`, `instrument.py`, `stream_service.py`, and the CP-0 test
— no reader. `outcome` is absent from the message read model: `routers/messages.py:80` and
`models.py:577` expose `finish_reason` and nothing else new.

This is the brief's hunting ground #3, and it applies to the whole checkpoint rather than to one
field. The `finish_reason='streaming'` precedent named in the brief is exactly reproduced: rows are
written that no consumer receives. That does not by itself falsify "the database records X" — but it
means **no source-level evidence can show the recorded values are right**, and I record it as the
reason several of my sub-verdicts are bounded.

### F-9 · `run_arms.py` claims an assertion it does not make (0.5)

`eval/arms/run_arms.py:112-114`: *"That the answer tool is absent is asserted below, never assumed."*
There is no such assertion. `main` computes `has_answer` (`193`), prints it, and stores it in the
results JSON (`198`) — nothing exits or fails if arm E were to contain `book_list`. If a future
budgeter change kept the answer tool, arm E would silently stop being an arm and would score like
arm D.

I checked the current state by evaluating the committed budgeter against the committed snapshot:
arm E resolves to 6 tools and `book_list` is absent, so the variable holds **today**. Two drifts
worth recording: the module docstring describes arm C as "35 book_* tools, 19 retired" and arm E as
"exactly the 7"; the committed detector over the committed snapshot yields 35 tools, **17** retired,
and **6** in arm E. The replay is an approximation of the recorded run, not a reproduction of it.

### F-10 · No committed output for the binding-format measurement (kills 0.6)

`eval/arms/binding_format.py` writes to `OUT_DIR = eval/arms/results` (`:42`, `:204-217`). That
directory does not exist. `git ls-files eval/` lists exactly two files under `eval/arms/`
(`binding_format.py`, `run_arms.py`) and no results. Nothing is git-ignored there — the output was
simply never produced or never committed.

Additionally the script has **uncommitted working-tree changes** (`git diff` shows `max_tokens: 600`
and `CALL_TIMEOUT_S` added at `:47`, `:139`, `:145`), so even the script half is not fully committed
in the form that would run.

The script itself is the best-designed artifact in this checkpoint: a decoy control whose wrong id is
the *more recently mentioned* (`:107-119`), grading in code on the argument actually sent
(`:149-178`), and an explicit `_bound` refusing to let the result admit a format (`:211-215`). None
of that is a substitute for a number.

### F-11 · `runtime_variant` and `declaration` are constants (0.7, vacuity)

`RUNTIME_AGENTRUNTIME` has no producer: `grep` finds it only in `instrument.py:66` and the test.
Every write site passes `RUNTIME_LEGACY` (`stream_service.py:6069`, `7124`) or relies on the column
default. Likewise `declaration` is `chunk.get("tool")` at both assignment points
(`instrument.py:103`, `141`) — no site passes a `declaration` differing from `tool`.

Both fields are therefore constant across 100% of rows. This is expected at CP-0 (no second runtime
exists yet) and the mechanism is correct, but it means the matched-pair join CP-0.7 exists to serve
cannot be exercised, and nothing in the repository would go red if the `declaration` parameter of
`stamp_tool_call` were deleted. I record it as an NV-class finding rather than as the item verdict,
because a label is not a gate.

---

## 4. Vacuity (NV) — can each new check fire?

| check | realistic firing input? |
|---|---|
| `stamp_tool_call` raises on unknown source (`instrument.py:98`) | **Yes** — a future mint site passing a typo'd constant. Covered by `test_an_unknown_source_is_refused_at_the_stamp`. |
| `ensure_tool_call_instrumented` inference | **Yes, constantly** — ~28 of ~30 mint sites are unstamped. It fires on nearly every tool-bearing turn. |
| `outcome` CHECK constraint (`migrate.py:344-346`) | **Yes** — a write site inventing a value would fail the INSERT. Guarded against drift by `test_the_vocabulary_matches_the_database_constraint`, which parses the real DDL. |
| `runtime_variant` CHECK (`migrate.py:360`) | **No** — only `'legacy'` is ever written. NV finding F-11. |
| `run_arms.py` hash-mismatch refusal (`:65-68`) | **Yes** — any edit to the snapshot's `tools` array. I verified the hash currently matches. |
| `run_arms.py` "answer tool absent in arm E" | **Never** — the assertion does not exist. F-9. |
| The five `withheld_tools` stages (`stream_service.py:2163-2207`) | **Yes** for the four discovery-gated stages, which are live suppressions today. `permission_mode_*` is gated on `not discovery` (`2194`) and so fires only on the non-discovery surface. |
| The token-budget stage of `withheld_tools` | **Never** — no such stage exists. F-1. |

---

## 5. Terminal-path enumeration (0.4), as requested — full, not summarised

| # | terminal path | `file:line` | outcome written |
|---|---|---|---|
| 1 | clean finish | `stream_service.py:7085-7125` | `completed` ✅ |
| 2 | frontend-tool suspend | `stream_service.py:6841-6855` | `awaiting_input` ✅ |
| 3 | cancellation / client disconnect | `stream_service.py:7246-7282` | `abandoned_by_user` ✅ (`asyncio.shield`ed) |
| 4 | mid-stream exception | `stream_service.py:7284-7306` | `failed` ✅ |
| 5 | abandoned suspend, **no** provisional row | `stream_service.py:6199-6216` | `abandoned_by_user` ✅ |
| 6 | abandoned suspend, provisional row exists (**preferred branch**) | `stream_service.py:6234-6238` | ❌ leaves `awaiting_input` — F-5 |
| 7 | empty terminal turn | `stream_service.py:6085-6098` | ❌ no row at all — F-4 |
| 8 | mid-turn checkpoint (crash surrogate) | `stream_service.py:6694-6712` | `crashed` ✅ pessimistic — good design |
| 9 | process death **before** the first checkpoint | throttle `_CHECKPOINT_MIN_INTERVAL_S = 1.5` at `:443`, checkpoint only inside the `tool_call` branch at `6682-6693` | ❌ no row. A prose-only turn killed mid-stream records nothing; a tool turn killed inside the first 1.5 s likewise |
| 10 | tool-loop write-budget exhaustion | break at `stream_service.py:1987`, defensive yield at `4668-4674` (`finish_reason: "stop"`) | ⚠️ falls into path 1 → `completed`. A breaker exit is recorded as a clean success |
| 11 | expired/mismatched resume | `stream_service.py:7420-7441` | delegates to path 6 → ❌ |
| 12 | voice turn (any ending) | `voice_stream_service.py:578-587` | ❌ column not in the INSERT — F-6 |
| 13 | voice suspend refusal | `voice_stream_service.py:481-488` | ❌ breaks to the same INSERT as 12 |
| 14 | proactive check-in | `routers/internal.py:926-929` | ❌ |
| 15 | spend-gate refusal | searched — **no such gate exists in this service**. `grep` for `quota|insufficient|spend_gate|402` over `stream_service.py` and `routers/messages.py` returns no gate. Not a hole; the subject does not exist |
| 16 | timeout | searched — no turn-level timeout wrapper. Consistent with the repository's standing "no timeout on LLM pipelines" position. Not a hole |

Six paths reach the end of a turn without a correct outcome; two of them (6, 12) are common.

---

## 6. Judging the tests

`services/chat-service/tests/test_cp0_instrument.py` (245 lines) is the **only** test added. It is
honest work and mostly red-able, but it is not evidence for the checkpoint's claims.

**Red-able, and I can say how.** Each assertion targets a pure function whose behaviour it
constrains, so removing the behaviour breaks it deterministically:

- `test_a_mid_turn_deletion_is_visible_in_the_record` (`:25`) computes
  `set(pass1.names) - set(pass2.names)` and asserts the exact vanished set. Change `record_pass` from
  `append` to assignment and this fails on `len(recorded) == 2`. **This is a real test of the item's
  hardest property.**
- `test_an_unstamped_record_is_never_silently_called_a_tool` (`:128`) asserts both
  `!= SOURCE_TOOL` **and** `== SOURCE_BREAKER` **and** `source_inferred is True`. Flipping the
  default to `tool` fails it. Not an `is not None` stand-in.
- `test_the_vocabulary_matches_the_database_constraint` (`:228`) reads `app/db/migrate.py` and regex-
  extracts the real CHECK list, comparing it set-wise to `instrument.OUTCOMES`. **This is the one test
  that asserts over an artifact outside the module under test**, and it is the right one to have
  written — it is what would catch a Python/DB vocabulary drift that could only otherwise fail in
  production, on a terminal path, losing a turn.
- `test_the_reporting_variant_does_not_change_what_is_kept` (`:113`) sweeps five budgets and asserts
  `kept == plain`. Genuinely guards the "instrument must not move the thing it measures" property.
- `test_dropped_names_are_returned_not_discarded` (`:106`) opens with
  `assert dropped, "a budget this small MUST drop something, or the test proves nothing"` — an
  explicit anti-vacuity guard on its own fixture. Good practice.

**What the suite does not do, and it is the whole gap.** Not one test touches
`stream_service.py`. Specifically there is no test that:

- any INSERT actually carries `advertised_tools` / `withheld_tools` / `runtime_variant` (only
  `outcome`'s CHECK is asserted, and only as DDL text, not as a write);
- the DDL contains the other three columns at all;
- a terminal path passes an `outcome` — all six 0.4 defects above are outside the suite's reach;
- the `advertised` chunk producer and consumer agree (F-7 lives in exactly that seam);
- `budget_names_by_tokens_ex` is *called* by anything that persists (F-1 is the whole checkpoint's
  central defect and no test can see it, because the test calls `_ex` directly).

So: the suite tests `instrument.py`, and `instrument.py` is correct. It is silent on whether the
service uses it. Per the repository's standing rule, it rejects the reintroduction of six named
defects in the helper and admits nothing about the product. That is the correct posture; it is just
much narrower than the checkpoint it is attached to.

---

## 7. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:578-587` — the voice pipeline persists no `advertised_tools`, though it runs `_stream_with_tools` and its `advertised` events are dropped at `voice_stream_service.py:470`. Also `stream_service.py:2063` — every pass with `offered_tools == False` (D7 final pass `:2025`, D8 rejection `:2439`) emits no entry, contradicting the comment at `:2152`. *Not* bypassed by overwrite: the recorder appends (`instrument.py:181-189`) and the upserts COALESCE (`:6144`, `:7112`). |
| **0.2** | `stream_service.py:2900,3006,3098,3267` and `tool_surface.py:336,383,424,553` — eight production sites call `budget_names_by_tokens` and discard the drops. `budget_names_by_tokens_ex` (`tool_surface.py:125`) is reached only from `eval/arms/run_arms.py:118` and the test. `budget_rail_tools`' drops go to `logger.warning` at `tool_surface.py:479-483`. Search: `grep -rn "budget_names_by_tokens" --include=*.py .`, 20 hits, all classified. |
| **0.3** | `stream_service.py:7660-7684` — the approved-Tier-A resume dispatch mints its chunk unstamped after a real `mcp_execute_tool` call (`:7645`); it is filed `breaker` by `instrument.py:139`. `latency_ms` is supplied at one of ~30 mint sites. Search: enumerated every `yield {"tool_call"` / `tool_chunk =` in the file (30 sites, listed in F-3) and cross-checked against the two `stamp_tool_call` call sites. |
| **0.4** | Six: `stream_service.py:6234-6238` (stale `awaiting_input` on the preferred abandonment branch), `:6085-6098` (empty turn, self-documented exemption), `voice_stream_service.py:578`, `routers/internal.py:926`, process death before the `:6682` checkpoint, and `:1987`→`:4668` (breaker exit filed `completed`). Full enumeration of 16 paths in §5. |
| **0.5** | No bypass. `contracts/agent-runtime-baseline/tools-list.snapshot.json` present (315 tools); I recomputed `sha256` over `json.dumps(tools, sort_keys=True, ensure_ascii=False, separators=(',',':'))` and it matches `catalog_sha256`. `eval/arms/run_arms.py` builds all five arms from that file and refuses on mismatch (`:65-68`). Two findings (F-9), neither fatal to the claim as written. |
| **0.6** | `eval/arms/results/` does not exist; `git ls-files eval/` lists only the two scripts; nothing under `eval/` is git-ignored (`git check-ignore` returns nothing). The script is also uncommitted-dirty. |
| **0.7** | No bypass of the literal claim: both INSERT chokepoints route every entry through `ensure_tool_call_instrumented` (`stream_service.py:6108`, `6931`), which sets `declaration` and `runtime_variant` unconditionally (`instrument.py:141-142`), and the column's `DEFAULT 'legacy'` (`migrate.py:359`) is the fail-safe direction for a writer that omits it — as `voice_stream_service.py:580` does. Bounded by F-11 (both values constant) and by the fact that voice-turn tool calls reach no INSERT at all, so "every recorded call" holds partly because those calls are never recorded. |
