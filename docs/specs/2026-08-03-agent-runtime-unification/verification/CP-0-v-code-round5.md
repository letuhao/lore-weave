# CP-0 · V-CODE — verdict, ROUND 5

Artifact frozen at `711f94c61656fb997da6de45e509a6605b8bc00b`. **`git status --porcelain` is empty** —
the working tree is clean, so the committed state and the graded state are the same state.

I confirmed the brief is unmodified: `git log aa9ef87c4..711f94c61 -- …/CP-0-V-CODE-PROMPT.md`
returns no commits.

Source-only review. Nothing in the product was run. No tracked file was modified. No commit message
or builder rationale prose was read. The round-4 verdict was read as a list of claims to re-check;
every finding below was re-derived from source at this SHA.

**Method note.** For each gate I replicated its logic verbatim over **in-memory** copies of the real
sources, applied the specific mutation, and recorded the result — with an assertion that each
mutation actually changed the string, because round 4's harness silently no-op'd on two probes and I
reproduced that failure on my own first pass. For the two rulings I imported the real
`app.services.instrument` and called the real functions. Where I say "green over the mutation", that
is a mechanical result, not an inference.

---

## 1. Verdict

**Overall: `FAIL`.**

| item | claim | R1 | R2 | R3 | R4 | **R5** |
|---|---|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | FAIL | FAIL | FAIL | **FAIL** — voice now writes a **hardcoded literal** claiming a tool-free pass, on a path that fetches the full catalog and offers it |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | FAIL | FAIL | **FAIL** — the four-round arming defect is **genuinely closed**; the same property now fails at the *output* boundary instead |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | FAIL | FAIL | **FAIL** — `latency_ms` still 3 of 30; and `dedupe_recorded_calls` now **deletes genuinely distinct calls** |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | FAIL | FAIL | **FAIL** — no change since R4; five paths still fail |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | PASS | PASS | **PASS** |
| 0.6 | binding-format measurement scripted **and its output committed** | FAIL | FAIL | FAIL | FAIL | **PASS** — all five arms ran, control included, output committed |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | PASS | PASS | **PASS** on the literal claim; same vacuity bounds, plus a new one |

**Three things are genuinely fixed this round and belong on the record before the findings.**

1. **0.2's arming is, for the first time in five attempts, correct.** `instrument.surface_withheld`
   is armed at `stream_service.py:5991` (one line before the fresh-turn narrowing at `:5992`) and at
   `:7913` (one line before the resume narrowing at `:7914`), and `_emit_chat_turn` **adopts** rather
   than replaces it (`:6429-6432`). I verified the reachability closure: `surface_withheld.set(` has
   exactly three sites repo-wide (`:5991`, `:6432`, `:7913`), the middle one guarded by
   `if _surface_sink is None`, so nothing overwrites the armed sink; the sink is drained into the
   recorder at `:6826-6830` and persisted at `:6812` / `:7231`. The four `hot_seed*` stages can now
   reach the column. That defect is closed.
2. **Gate F is fixed.** All four CP-0 columns now have an existence assertion against the real DDL,
   and I confirmed each one goes red when its `ADD COLUMN` line is deleted. This was round 4's
   largest structural gap and it is gone.
3. **0.6 completed.** All five arms, including `decoy_control`, `n=3`, output committed as both raw
   JSON and a finding that states its own bound and refuses to rank the formats.

**The pattern is now five for five on the item that decides the checkpoint, and it moved one layer
outward rather than inward.** 0.2's defect has been: no caller → wrong file → unpassed argument →
unarmed context → **and now an output filter that can delete the record after it is correctly
made.** The input side is right; `withheld_json()` can return `None` for a turn in which a tool was
genuinely invisible to the model (§6, Ruling 1).

---

## 2. The falsifier

Stated before the findings, so the three PASSes are readable. What I looked for that would have made
this FAIL, and what each search returned.

1. **A production narrowing whose drops still register nowhere.** *Not found, for the first time in
   five rounds.* *How I searched:* `grep -rn` repo-wide for every `surface_withheld` reference, every
   `_budget_and_register` / `discovery_seed_for_surface` / `effective_enabled_tools` call site; then
   read both enclosing functions for straight-line order; then confirmed no `set()` after the arming
   can replace the sink. `_budget_and_register` is reachable only via `discovery_seed_for_surface`
   (`tool_surface.py:375, 423, 465`) and `effective_enabled_tools` (`:596`, whose sole caller is
   `discovery_seed_for_surface:388`), and both entry points are armed one line earlier.
2. **A record that is correctly made and then deleted before it reaches the column.** *Found — twice,
   both new this round.* `withheld_json()` (Ruling 1) and `dedupe_recorded_calls` (Ruling 2). §6.
3. **A column written with a value the code contradicts.** *Found.* `voice_stream_service.py:604-607`
   writes a hardcoded `{"names": [], "count": 0, "note": "voice pipeline — tool-free by design"}`
   while `:449-465` fetches the full tool catalog and hands it to `_stream_with_tools`. F-12.
4. **A terminal path writing no outcome, a stale one, or a wrong one.** *Found — five remain,
   unchanged from R4.* §5.
5. **A gate that is green over the defect it names.** *Found — two of six (A, D), with two more
   carrying named blind spots (B, E).* §4, with mutations.
6. **`advertised_tools` overwritten rather than appended.** *Not found, a fifth time.* `record_pass`
   appends (`instrument.py:277-285`); both upserts `COALESCE` (`:6229-6230`, `:7221-7222`).
7. **`source` defaulting to `tool`.** *Not found.* `ensure_tool_call_instrumented` assigns `meta`
   (closed name set) or `breaker` with `source_inferred` (`instrument.py:196-199`); `stamp_tool_call`
   raises on an unknown source (`:130-131`).
8. **DDL appended to an already-applied ledger step** (the brief's flagged likely failure).
   *Not applicable, re-checked independently.* `migrate.py` is one DDL string executed in full on
   every boot; no version table, step list or applied-marker. All four CP-0 statements are
   `ADD COLUMN IF NOT EXISTS` (`:319, :327, :344, :359`) and all four are now gated by Gate F.
9. **Committed output for the 0.6 measurement.** *Found, and it is a real measurement.*
   `git ls-files eval/arms/` returns `binding_format.py`, `run_arms.py`,
   `results/binding-format-20260804T035320Z.json`, `results/binding-format-FINDING.md`. The
   `-INCOMPLETE.md` is gone.

Two things I **cannot determine from source**, unchanged across five rounds and worth restating
because they bound the PASSes:

- **Whether the recorded values are right.** `advertised_tools|withheld_tools|runtime_variant`
  appears repository-wide in exactly seven files: `migrate.py`, `instrument.py`, `stream_service.py`,
  `voice_stream_service.py`, `routers/internal.py`, and two tests. No query, model field, router or
  SQL reads any of them back. `chat_messages.outcome` has no reader; `latency_unmeasured` has no
  reader. This is the brief's hunting ground #3 and the `finish_reason='streaming'` precedent. It is
  a V-LIVE/V-METRIC question, but it is why no source-level evidence can show the values are right —
  and it is what let F-12 (a fabricated value) ship without anything noticing.
- **The real-world frequency** of a same-stage re-drop across passes, which sets how often Ruling 1's
  deletion actually fires.

---

## 3. THE GATE AUDIT — six gates, two green over the defect they name

`tests/test_cp0_instrument.py` (553 lines). For each gate: the boundary it draws, the mutation that
should make it red, and whether it does. Every row below is a mechanical result from the harness
described in the method note; every mutation was asserted to have actually changed the source string.

### Gate A · `test_the_token_budgeter_reports_its_drops_in_production` (`:42-85`) — **WIDENED, AND STILL GREEN OVER ITS OWN DEFECT (ROUND 4 RUNNING)**

**Boundary drawn:** *text*. A regex forbidding any call to `budget_names_by_tokens(` in two files
(excluding the `def`), plus four substring presence checks and a `>= 4` call count.

| mutation | should be | **is** |
|---|---|---|
| revert a site to `x = budget_names_by_tokens(` | red | red ✔ |
| **`return budget_names_by_tokens(...)`** — round 4's escape | red | **red ✔ — genuinely fixed** |
| `_mod.budget_names_by_tokens(...)` (attribute call) | red | red ✔ |
| **delete the ContextVar fallback in `_budget_and_register` (`tool_surface.py:246-253`)** — restoring exactly the R3 state where the narrowing registers nowhere | red | **GREEN** |
| **a NEW narrowing that calls `budget_names_by_tokens_ex(...)` and discards `dropped`** | red | **GREEN** |

The widening is real: the round-4 finding (the boundary was drawn around one assignment syntax) is
closed, and I could not find a call form that escapes the regex.

**But the boundary is still "the plain function is not called", not "the drops reach a sink."** Row 4
is the same finding for the fourth consecutive round: the gate is green over the state in which
`_budget_and_register` registers nothing. Row 5 is new and is the more useful one — the `_ex` variant
*returns* its drops, so a caller that ignores the second tuple element discards them just as
completely as the plain variant did, and the gate has no opinion about it. That is the exact shape of
the founding defect, expressed through the function the gate was written to promote.

Also: the docstring at `tool_surface.py:237-239` still ships the exemption round 3 flagged
(*"``sink`` is optional … That is a real hole and it is the honest one"*), now contradicted by the
ContextVar fallback five lines beneath it.

### Gate B · `test_every_real_dispatch_is_stamped_as_a_real_dispatch` (`:186-226`) — **SOUND for its three named sites; two blind spots, one of which contradicts its own docstring**

**Boundary drawn:** *positional syntax*. Each occurrence of `await knowledge_client.mcp_execute_tool(`
owns the region from itself to the next occurrence, which must contain `source=instrument.SOURCE_TOOL`.

| mutation | should be | **is** |
|---|---|---|
| unstamp the in-loop dispatch (`:4453`/stamp `:4672`) | red | red ✔ names 4453 |
| a 4th unstamped `knowledge_client` dispatch appended after the last | red | red ✔ names it |
| **a dispatch via a differently-named receiver (`await _kc.mcp_execute_tool(`)** | red | **GREEN** — round 4 recorded this as "caught by luck via the `>= 3` floor"; it is **not**. The needle does not match, `len(starts)` stays 3, the floor is satisfied, and the region logic never sees it |
| **a 4th `knowledge_client` dispatch inserted BEFORE line 4453** | red | **GREEN** — its region `[new, 4453)` contains the stamp at `:3487`, which is the **subagent** stamp, not a dispatch stamp |

The last row falsifies the gate's own docstring, which says *"a surplus stamp somewhere else in the
file can no longer pay for a deficit here."* It can, for any dispatch added before `:4453`: the
non-dispatch stamp at `:3487` sits in the region that precedes the first real dispatch and is
available to pay for it. Region-ownership bounds the *forward* direction only.

Also unchanged from round 4: the gate reads `stream_service.py` only, in a run whose purpose is to
add a new runtime module that will dispatch tools.

### Gate C · `test_outcome_never_moves_without_finish_reason_moving_with_it` (`:501-525`) — **SOUND, scope unchanged**

**Boundary drawn:** *syntax*. Each `UPDATE chat_messages SET` in `stream_service.py`; the clause
before `WHERE`; if it mentions `finish_reason` it must mention `outcome`. Plus an explicit
anti-vacuity assertion (`:525`).

| mutation | should be | **is** |
|---|---|---|
| drop `outcome = $2` from the abandoned-suspend UPDATE (`:6327`) | red | red ✔ |
| the same defect in `voice_stream_service.py:882` or `routers/messages.py:449` | red | **invisible** — gate reads `stream_service.py` only |

Both other files do contain `UPDATE chat_messages`; neither touches `finish_reason` today, so nothing
is missed *now*. Unchanged, and still one of the better-built gates.

### Gate D · `test_a_surface_narrowing_registers_without_anyone_wiring_it` (`:87-148`) — **RED-ABLE FOR EXACTLY THE ROUND-4 DEFECT AND FOR ALMOST NOTHING ELSE**

**Boundary drawn:** *text, positional* (a source assertion) **+ isolated behaviour** (the mechanism,
with the test still arming the sink itself at `:130-131`).

Round 4's complaint — the behavioural half supplies the precondition production was failing to
supply — is **not** fixed. What was added is a *source* assertion in front of it: the literal string
`surface_withheld.set(` must appear within the 1200 characters preceding each of two specific,
named assignment expressions.

| mutation | should be | **is** |
|---|---|---|
| **delete the arming line at `:5991`** (the exact R4 defect) | red | **red ✔** |
| `instrument.surface_withheld.set(None)` instead of `set([])` — present as text, useless at runtime | red | **GREEN** |
| the arming line demoted to a **comment** (`# instrument.surface_withheld.set([])`) | red | **GREEN** |
| **adopt then immediately replace: `_surface_sink = …get()` followed by `_surface_sink = []; …set(_surface_sink)`** — discards every assembly-time narrowing | red | **GREEN** |
| a **third** `discovery_seed_for_surface(` call site, unarmed | red | **GREEN** |
| **delete the drain** at `:6826-6830`, so the sink never reaches the recorder | red | **GREEN** |
| rename `discovery_seed_names` → `discovery_seed_names_v2`, changing nothing | green | **RED** (false positive) |

**Row 4 is the finding.** The gate's own third assertion (`:125-128`) states the property *"the turn
must ADOPT that sink rather than replace it, or the records are discarded"* — and a mutation that
adopts and then immediately replaces it is green, because the assertion tests only that the string
`_surface_sink = instrument.surface_withheld.get()` is *present*, never that nothing after it
replaces the sink. **A gate green over a defect in its own stated subject, for the second gate in a
row on this item.**

Row 3 is the failure mode the builder documented fixing in Gate E — *"a gate of mine matched prose
instead of code"* — reproduced here, in the gate written one round later. Row 6 is the one that
decides whether any of this reaches the database, and it is invisible. Row 7 shows the boundary is
drawn around two edited *identifiers*, not around a property: a rename that changes no behaviour
turns it red.

The honest summary: this gate rejects the literal edit of round 4 and one adjacent state. It is a
regression pin for a specific line, not a check that narrowings register.

### Gate E · `test_every_assistant_row_insert_anywhere_writes_an_outcome` (`:150-184`) — **RED-ABLE for a missing column, anywhere; still blind to a missing value**

**Boundary drawn:** *syntax, whole-`app`-package scope.*

| mutation | should be | **is** |
|---|---|---|
| voice drops the `outcome` column | red | red ✔ names `voice_stream_service.py:581` |
| proactive drops the `outcome` column | red | red ✔ names `internal.py:932` |
| the clean-finish INSERT drops it | red | red ✔ names `stream_service.py:7195` |
| a brand-new assistant INSERT in another file | red | red ✔ |
| **an assistant `INSERT … SELECT` (no `VALUES`) with a nearby Python comment containing "outcome"** | red | **red ✔** — round 4 found this passed only *by accident*; I re-probed it deliberately and it fails closed |
| **voice binds `None` instead of `instrument.OUTCOME_COMPLETED`** — column named, value NULL | red | **GREEN** |
| a new assistant INSERT with the role bound as a parameter (`VALUES ($1,…,$20,…)`) | red | **GREEN** |

Rows 1–5 are a real, verified improvement and the whole-package scope is the right population for
"wherever it lives". Rows 6–7 are unchanged from round 4: the gate verifies the column is **named**.
`outcome` present in the column list with `NULL` bound to it satisfies it completely and produces a
row indistinguishable from the pre-CP-0 state.

It also remains structurally unable to see four of the five remaining 0.4 failures (§5): a path that
writes **no row** is not an INSERT; a **wrong** value (`completed` on a breaker exit) is a value; a
**stale** value is written by nobody.

### Gate F · `test_the_vocabulary_matches_the_database_constraint` (`:527-552`) — **FIXED THIS ROUND**

**Boundary drawn:** *syntax* — a regex over the real DDL for the `outcome` CHECK, plus an existence
assertion for each of the four CP-0 columns.

| mutation | should be | **is** |
|---|---|---|
| drop a value from either side of the vocabulary | red | red ✔ both directions |
| delete the `advertised_tools` `ADD COLUMN` line | red | **red ✔** |
| delete the `withheld_tools` `ADD COLUMN` line | red | **red ✔** |
| delete the `runtime_variant` `ADD COLUMN` line | red | **red ✔** |

Round 4's largest structural gap — *"no test asserts that three of the four CP-0 columns exist in the
schema at all"* — is closed, and it is closed at the property (existence in the real DDL) rather than
at the string the verdict quoted. **This is the round's cleanly-built fix.**

### Scorecard

| gate | boundary | red-able for its own defect? |
|---|---|---|
| A · budgeter wiring | text | **NO** — green over the R3 defect state (4th round) and over a discarding `_ex` caller; call-form widening is real |
| B · dispatch stamping | positional syntax | **yes** for its three named sites; green over a renamed receiver and over any dispatch inserted before `:4453` |
| C · outcome/finish_reason lockstep | syntax | **yes**, within one file |
| D · surface narrowing arrives | text + isolated behaviour | **NO** — green over adopt-then-replace, over `set(None)`, over a commented-out arming, over a deleted drain, over a third call site |
| E · assistant-INSERT outcome | syntax, whole package | **partly** — catches a missing column anywhere (improved); blind to a NULL value and a parameterised role |
| F · outcome vocabulary + column existence | syntax over real DDL | **yes**, all four columns — **fixed** |

Two of six are green over a defect in their own stated subject (A, D); two more have named blind
spots (B, E); one is fixed (F); one is unchanged and sound within its file (C).

---

## 4. Terminal-path enumeration (0.4) — full, not summarised

Graded against the frozen criterion (*"every terminal path, incl. cancel and crash"*).

| # | terminal path | `file:line` | writes a row? | outcome | R5 |
|---|---|---|---|---|---|
| 1 | clean finish | `stream_service.py:7195` | yes | `completed` (`:7229`) | pass |
| 2 | frontend-tool suspend | `:6960` | yes | `awaiting_input` | pass |
| 3 | cancellation / client disconnect | `:7392` | yes | `abandoned_by_user` | pass |
| 4 | mid-stream exception | `:7433` | yes | `failed` | pass |
| 5 | abandoned suspend, no provisional row | `:6300` | yes | `abandoned_by_user` | pass |
| 6 | abandoned suspend, provisional row | `:6327` | yes | `abandoned_by_user` | pass |
| 7 | **empty terminal turn** | `:6170-6183` | **no** | ❌ none | **FAIL** — returns `False` before any write; labelled *"CP-0.4, KNOWN HOLE, DELIBERATELY NOT CLOSED HERE"* and logged at INFO, so it is countable |
| 8 | mid-turn checkpoint (crash surrogate) | `:6810` | yes | `crashed`, pessimistic | pass — good design |
| 9 | **process death before the first checkpoint** | checkpoint is inside the tool-boundary branch | **no** | ❌ none | **FAIL** — *crash* is named in the frozen criterion |
| 10 | **tool-loop pass exhaustion** | `break` at `:1994`, `:4738` → defensive `finish_reason: "stop"` at `:4743` → `OUTCOME_COMPLETED` at `:7229` | yes | ⚠️ `completed` | **FAIL, and the worst kind** — a breaker exit recorded as a clean success |
| 11 | expired / mismatched resume | delegates to #6 | yes | ✅ | pass |
| 12 | voice turn, clean finish | `voice_stream_service.py:581-594` | yes | ✅ `completed` | pass (fixed R4) |
| 13 | **voice turn, exception** | INSERT at `:581` sits inside `try:` at `:440`; `except Exception` at `:754` logs, emits an SSE error, returns | **no** | ❌ none | **FAIL** |
| 14 | proactive check-in | `routers/internal.py:932-937` | yes | ✅ `completed` | pass (fixed R4) |
| 15 | **suspend never resumed, never expired** | `db/suspended_runs.py:187` — `sweep_expired_runs` still has **zero callers** (re-verified: `grep -rn` over `app/` returns the definition only) | yes | ❌ stays `awaiting_input` forever | **FAIL** — a success state on a dead turn |
| 16 | spend-gate refusal | searched — no such gate in this service | n/a | n/a | — |
| 17 | turn-level timeout | searched — no wrapper; consistent with the repo's standing "no timeout on LLM pipelines" | n/a | n/a | — |

**Five paths fail (#7, #9, #10, #13, #15), unchanged from round 4.** The brief's summary of this
round's 0.4 change ("voice + proactive write outcomes") describes the round-4 fix; I found no 0.4
change at this SHA. Gate E can see **none** of the five: #7, #9 and #13 write no row; #10 and #15
write a value the gate does not inspect.

---

## 5. The two rulings

### RULING 1 · `withheld_json()`'s reconciliation — **a defensible rule, implemented so that it can delete a true withholding, and shipped with a false mitigation claim**

`instrument.py:342-374`. Verdict in three parts.

**(a) The rule itself is correct, and better than what its own docstring says.** The docstring claims
*"the final advertised set wins"*. The code does not do that — it compares each withheld entry
against **the advertised set of the pass it was stamped against** (`by_pass.get(w.get("pass"))`,
`:372`). I confirmed the difference by running it: a tool absent on pass 1, withheld and stamped
pass 1, then present on the final pass 2, is **kept**. Per-pass reconciliation is the defensible
rule; "final set wins" would erase a genuine early withholding. So the prose overstates the deletion
and the code is the more careful of the two. On the narrow question asked — *is dropping an entry
whose tool the model could actually see on that pass a correct reconciliation?* — **yes.** A column
whose claim is *"the model could not see this"* must not contain rows where it could, and the
per-eleven-tool contradiction three live rounds measured is a real defect in the claim, not merely in
the timestamp.

**(b) But it can delete a withholding that is true.** The deletion interacts with
`record_withheld`'s dedupe on `(tool, stage)` (`:300-303`), which is first-wins and stamps the pass
at *first* occurrence. Run against the real code:

```
pass 1: advertised {book_list, glossary_search}   # a later stage put glossary_search back
        record_withheld(glossary_search, stage=rail_gate)   -> stamped pass 1
pass 2: advertised {book_list}                    # glossary_search now genuinely GONE
        record_withheld(glossary_search, stage=rail_gate)   -> DEDUPED, no entry
withheld_json() -> None
```

The model could not see `glossary_search` on pass 2, one stage decided that, and the column reports
**nothing**. This is the run's own invariant 3 (*"an exclusion with no `{tool, stage, reason}` row is
a defect"*) failing through a new mechanism — and it is the same property that has failed for five
rounds, now failing after the record was correctly made rather than before. I also confirmed
`withheld_json()` returns `None` when every entry reconciles away, so the column is `NULL` — the
value that is indistinguishable from a turn that narrowed nothing at all.

**(c) The mitigation claim in the docstring is false, and it is the sentence that makes the deletion
look safe.** `:358-360` states: *"The dropped decisions are not lost: they remain visible in the
per-stage counters a caller can compute from `passes`."* A `passes` entry is
`{pass, tool_choice, names, count}` — I printed it. It contains **no stage and no reason**. There is
no per-stage counter anywhere in the codebase, and the raw `_withheld` list reaches no INSERT: both
persist sites bind `withheld_json()`. The dropped decision is not recoverable from anything that is
written down.

**Ruling: not a deliberate erasure of evidence — the rule is one a careful person would choose, and
it is applied more conservatively than its own prose admits. But it is *implemented* as a deletion
with no surviving record, it can delete a genuine withholding, and it is defended by a claim of
recoverability that is not true.** The practical consequence is that a live measurement of
"withheld-yet-advertised" — which read 6.3% / 6.2% / 6.2% across three rounds — will now read 0% with
no production narrowing having changed. That is a metric closed by making it unable to fire, and
under NV-1..6 that is a `FAIL` finding on its own terms.

### RULING 2 · `dedupe_recorded_calls` — **it can and will delete genuinely distinct calls; the codebase already contains the correct key**

`instrument.py:152-176`. Key: `(iteration, tool, ok, source, str(error))`. It omits **`args` and
`result`** — the only two fields that distinguish two different calls to the same tool.

Two real calls to the same tool in the same iteration with the same outcome collide. I ran the real
function:

| input | out |
|---|---|
| `book_read(chapter=1)` ok + `book_read(chapter=2)` ok, iteration 3 | **1** — the `chapter=2` call is deleted |
| two `glossary_propose_entity_edit` failures with the same error string, different args, iteration 5 | **1** |
| the resume pre-dispatch (`iteration: 0` hardcoded at `:7813`/`:7849`) + the first in-loop pass of the same tool (`iteration = -1` then `+= 1` → **0**, `:1991-1993`) | **1** |

The third row is not hypothetical: the pre-executed and in-loop calls carry a hardcoded and a
computed `0` respectively, so they share an iteration by construction.

**Multiple calls to one tool in one iteration are a documented, measured property of this
codebase.** `_collapse_identical_tool_calls` (`stream_service.py:1168-1219`) exists precisely because
the model emits 2–4 calls to the same tool in one `tool_calls` array, and its docstring records that
every affected session had `count(DISTINCT args) = 1` — i.e. it identified the *byte-identical* case
specifically, and it keys on `(name, canonical args)` so that a batch of *different* requests is
preserved. That helper runs **before** execution, so the byte-identical duplicates it targets never
reach the recorder at all. What survives to `dedupe_recorded_calls` is therefore, by construction,
disproportionately the calls that differ in args — exactly the population its key cannot see.

**Ruling: yes, it can delete a genuinely distinct call, and the case is easy to construct and
plausible in production.** The direction of the bias is the concerning part: the docstring justifies
the function by noting that a duplicate *inflates* a denominator and so *understates* a failure rate.
Deleting a distinct successful call moves the rate the other way; deleting a distinct failure moves
it back. Either way the call count — the denominator of the headline 57.7% and of every CP-4
comparison — is now adjusted by an unaudited rule at the persistence chokepoint. **It has zero
tests** (`grep -rn dedupe_recorded_calls tests/` returns nothing), and the correct key already exists
25 lines of source away in the same repository. I am not ruling it self-serving in intent; I am
ruling that a function which silently removes rows from the run's primary denominator, keyed on
strictly less than the identity of a call, is a correctness defect that lands on 0.3.

---

## 6. Findings

### F-12 · The voice pipeline now records a FABRICATED `advertised_tools` (0.1) — **the finding that decides 0.1**

`voice_stream_service.py:596-607` binds a hardcoded literal:

```python
json.dumps([{
    "pass": 1, "tool_choice": None, "names": [], "count": 0,
    "note": "voice pipeline — tool-free by design",
}]),
```

The justifying comment two lines above reads: *"the voice pipeline runs ONE tool-free pass by design
(it routes through `_stream_via_gateway`, which offers no tools at all)."*

**That is false against the same file.** `voice_stream_service.py:447` imports `_stream_with_tools`;
`:449-452` calls `knowledge_client.get_tool_definitions(user_id=...)` for the **full** tool catalog;
`:453-465` passes it as `tools=_voice_tools` with `permission_mode="ask"`. The only tool-free case is
the `except` fallback at `:450-452`, which the comment does not describe. `_stream_via_gateway` is
imported at `:40` but is not the function this path calls.

Three consequences, in increasing severity:

1. **`names: []` is wrong on every voice turn where the catalog fetch succeeds** — which is the
   normal case. The model was offered the catalog and the column says it was offered nothing.
2. **`pass: 1` is wrong whenever the voice turn takes more than one pass.** `_stream_with_tools` is
   a multi-pass loop; the record asserts exactly one.
3. **This is strictly worse than round 4's NULL.** A NULL is a hole a verifier counts. This is a
   confident, well-formed, plausible-looking answer, and per the repository's own standing rule
   *nobody re-checks a column that has an answer*. It is the `toBeVisible()`-asserts-presence shape
   inverted: the row is present, populated, well-shaped, and false.

Note also that no gate can see it: Gate E asks only that the `outcome` column be **named**, and the
voice INSERT names it. Nothing anywhere asserts that a persisted `advertised_tools` value was
produced by a recorder rather than typed by hand.

Unchanged from round 4 on the same statement: the voice INSERT still writes **no `withheld_tools`
and no `tool_calls`** (`:583-584`), and its `tool_call` chunks are emitted as SSE at `:491-493` and
never accumulated — so voice-dispatched tools carry `source`, `latency_ms`, `declaration` and
`runtime_variant` only vacuously, by never being recorded.

### RESOLVED · The 0.2 arming is correct (five rounds)

Detailed in §1. `stream_service.py:5991` and `:7913` precede `:5992` and `:7914` by one line each;
`:6429-6432` adopts under an `is None` guard; the drain at `:6826-6830` runs immediately after
`record_pass` so the surface narrowings are stamped to pass 1, which is the pass they shaped. I
searched for a third arming site, an overwrite, a third narrowing entry point and a task boundary
that could split the context, and found none. This is the fix the previous four rounds were asking
for and it should be credited as such.

### RESOLVED · Gate F now asserts all four columns exist

`tests/test_cp0_instrument.py:544-548`. Verified red for each of the three previously-unasserted
columns.

### RESOLVED · 0.6 completed, with a control, and its output committed

`eval/arms/results/binding-format-20260804T035320Z.json` and `binding-format-FINDING.md` are both in
`git ls-files`. All five arms ran at `n=3` on the local target model, graded **in code** on the
`chapter_id` actually sent (`binding_format.py:149-178`), never by asking a model. Every arm scored
3/3, including `decoy_control`, which sends a second UUID and was never once copied. The finding
states the correct bound (*"3/3 bounds a failure rate only at ≤63.2%"*), states that the arms
therefore **fail to rank** the formats rather than ranking them, and instructs CP-3 not to choose a
format on this evidence. That is the honest reading of a null result and the item's second conjunct
is now satisfied.

*One bound on the control, recorded because the finding leans on it.* The decoy is a
**differently-named** binding (`cover_asset_id`), so 3/3 rules out *"copy the nearest UUID"* but not
*"match the key name without resolving the binding"* — a same-named decoy under a superseded step
would be the stronger control. This does not change the verdict (the claim is *scripted and its
output committed*), but the FINDING's sentence *"it is genuinely resolving the binding"* is stronger
than the arm supports.

### F-13 · `dedupe_recorded_calls` and `withheld_json()` are two new deletion points with one test between them

Ruling 1 and Ruling 2 above. `withheld_json`'s reconciliation is covered by one test
(`:323-349`), which asserts the drop and asserts that a genuinely-absent tool survives — a
well-constructed pair, red-able, and it does not cover the dedupe interaction in Ruling 1(b).
`dedupe_recorded_calls` has **no test at all**. Both run at the persistence chokepoint, on the
columns the whole checkpoint exists to fill.

### F-1⁵ · 0.2's residuals, unchanged

- `budget_rail_tools` returns `(kept, dropped)` and the caller sends the drops to `logger.warning`
  (`tool_surface.py:257-291`, caller at `:516-519`), not to `withheld_tools`. The literal 0.2 wording
  ("returns what it dropped") is satisfied; the property is not.
- `_budget_withheld` is drained only inside `if offered_tools:` (`stream_service.py:2206-2208`), and
  the new tool-free block at `:2316-2331` does not drain it — so activation drops accumulated before
  a D7 forced-final pass are discarded when that pass is the last.
- The tool-free record's withheld entry is `{"tool": "*", "stage": "pass_offered_no_tools", …}`
  (`:2325-2331`). `"*"` is not a tool name, the column is typed `[{tool, stage, reason}]`, and
  `record_withheld` dedupes on `(tool, stage)` so three tool-free passes register one entry.

### F-9 · `run_arms.py` still claims an assertion it does not make (0.5)

`eval/arms/run_arms.py:114`: *"That the answer tool is absent is asserted below, never assumed."*
There is no such assertion. `has_answer` is computed at `:190`, printed at `:193`, stored at `:196`;
nothing exits or fails. Unchanged from rounds 3 and 4. A docstring overstatement, not a bypass of the
0.5 claim.

### F-11‴ · `runtime_variant`, `declaration` and `unclassified` remain constants or dead (0.7, vacuity)

- `RUNTIME_AGENTRUNTIME` (`instrument.py:98`) has no producer; every write site passes
  `RUNTIME_LEGACY` or relies on `DEFAULT 'legacy'` (`migrate.py:359`).
- `declaration` is `chunk.get("tool")` at both assignment points (`:135`, `:209`); no site passes a
  differing `declaration`.
- `tool_call_source()` (`:101-111`), the only function that can return `unclassified`, still has
  **zero callers**. The persistence chokepoint assigns `meta` or `breaker` and never `unclassified`.
- New this round: *"every recorded call"* is now true of a set from which `dedupe_recorded_calls` has
  removed members.

### F-8″ · Six of seven recordings remain write-only

`advertised_tools|withheld_tools|runtime_variant` appears repository-wide in exactly seven files:
`migrate.py`, `instrument.py`, `stream_service.py`, `voice_stream_service.py`, `routers/internal.py`,
`tests/test_cp0_instrument.py`, `tests/test_tool_discovery.py`. `chat_messages.outcome` has no
reader. `latency_unmeasured` has no reader. `tc->>'source'` is read only at
`contracts/agent-runtime-baseline/baseline-metrics.sql`, the pre-CP-0 baseline. This is the brief's
hunting ground #3, and F-12 is what it costs: a hand-typed value sat in a column that nothing reads,
and only a path enumeration found it.

---

## 7. Vacuity (NV) — can each check fire?

| check | realistic firing input? |
|---|---|
| `stamp_tool_call` raises on unknown source (`instrument.py:130`) | **Yes** — a future mint site with a typo'd constant. |
| `ensure_tool_call_instrumented` inference (`:196`) | **Yes, constantly** — 27 of 30 mint sites are unstamped. |
| `tool_call_source` → `unclassified` (`:111`) | **No** — zero callers. F-11‴. |
| `_budget_and_register`'s ContextVar fallback (`tool_surface.py:246-253`) | **Yes — for the first time.** The sink is armed before both entry points. |
| `withheld_json` reconciliation (`instrument.py:366-373`) | **Yes**, and it fires on the eleven tools three live rounds measured — **removing the only signal that measured them.** Ruling 1. |
| `dedupe_recorded_calls` (`:152-176`) | **Yes**, on any two same-tool calls in one iteration with the same outcome. Ruling 2. |
| `pass_offered_no_tools` withheld record (`stream_service.py:2325`) | **Yes** — D7/D8/ask-mode. Capped at one entry per turn; names no real tool. |
| `outcome` CHECK constraint (`migrate.py:344-346`) | **Yes** — drift-guarded by Gate F. |
| `runtime_variant` CHECK (`migrate.py:359`) | **No** — only `'legacy'` is ever written. |
| voice `advertised_tools` literal (`voice_stream_service.py:604`) | **Fires on every voice turn, and is wrong on every one where the catalog fetch succeeds.** F-12. |
| `run_arms.py` hash-mismatch refusal (`:65-68`) | **Yes** — any edit to the snapshot's `tools` array. |
| `run_arms.py` "answer tool absent in arm E" | **Never** — the assertion does not exist. F-9. |
| `binding_format.py` `decoy_control` (`:107-119`) | **Yes** — it ran, and it discriminated (0/3 decoy). Bounded: the decoy carries a different key name. |
| Gate A | **Yes**, and green over a live-shaped instance of its own defect for the 4th round. §3 |
| Gate B | **Yes** for its three named sites; blind to a renamed receiver and to a pre-`:4453` insertion. |
| Gate C | **Yes**, with an explicit anti-vacuity assertion. |
| Gate D | **Yes** for the deleted arming line only; green over five adjacent defects incl. one its own docstring names. §3 |
| Gate E | **Yes** for a missing column anywhere; cannot fire on a NULL value or a parameterised role. |
| Gate F | **Yes**, all four columns and both vocabulary directions. |

---

## 8. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:596-607` — writes a hardcoded `{"names": [], "count": 0}` while `:449-465` fetches the full catalog and offers it via `_stream_with_tools`. Not bypassed by overwrite: `record_pass` appends (`instrument.py:277-285`) and both upserts COALESCE (`:6229`, `:7221`). Search: `grep -rn "INSERT INTO chat_messages"` over `app/` → 6 sites, column list and bound value read on each; then `grep -n "_stream_with_tools\|_stream_via_gateway\|tool_defs"` in the voice module. |
| **0.2** | **The arming bypass is closed** (five sites read, straight-line order confirmed in both enclosing functions, no third narrowing entry point, no overwriting `set()`). The remaining bypass is at the output: `instrument.py:366-373` deletes a withheld entry whose tool was advertised on the *stamped* pass, and `record_withheld`'s `(tool, stage)` dedupe (`:300-303`) means a later, genuine drop by the same stage registers nowhere — demonstrated by running the real recorder. Plus `budget_rail_tools`' drops → `logger.warning`, `_budget_withheld` drained only under `if offered_tools:`, and a `"*"` pseudo-tool. |
| **0.3** | `source`: **no bypass found** — all three `await knowledge_client.mcp_execute_tool(` sites stamped and recorded; the chokepoint classifies the rest by a closed name set; no `tool` default. `latency_ms`: measured at 3 of 30 mint sites (`:4672`, `:7696`, `:7837`); the other 27 carry an explicit null plus `latency_unmeasured`. **New bypass:** `instrument.dedupe_recorded_calls` (called at `:6192` and `:7038`) deletes entries keyed without `args` or `result`, so two distinct same-tool calls in one iteration persist as one. Voice tool calls reach no INSERT at all. |
| **0.4** | Five paths, unchanged from R4. Write **no row**: `stream_service.py:6170` (empty turn), pre-checkpoint process death, `voice_stream_service.py:754` (voice exception). Write a **wrong** value: `:1994`/`:4738` → `finish_reason: "stop"` at `:4743` → `completed` at `:7229`. Write a **stale** value: `db/suspended_runs.py:187` — `sweep_expired_runs` has zero callers repo-wide (re-verified). Full enumeration of 17 paths in §4. |
| **0.5** | No bypass. `contracts/agent-runtime-baseline/` holds `tools-list.snapshot.json`, `baseline-metrics.sql`, `baseline-metrics.frozen.txt` (`git ls-files`). `run_arms.py` builds all five arms from the snapshot and refuses on hash mismatch (`:65-68`). F-9 is a docstring overstatement, not a bypass. |
| **0.6** | No bypass. `git ls-files eval/arms/` returns both scripts plus `results/binding-format-20260804T035320Z.json` and `results/binding-format-FINDING.md`; the JSON carries all five arms with per-trial records and a `_bound` field, and grading is in code on the argument sent. |
| **0.7** | No bypass of the literal claim: both `stream_service` INSERT chokepoints route every entry through `ensure_tool_call_instrumented`, which sets `declaration` and `runtime_variant` unconditionally (`instrument.py:209-210`); `voice_stream_service.py:594` and `routers/internal.py:937` pass `RUNTIME_LEGACY` explicitly; `DEFAULT 'legacy'` (`migrate.py:359`) is the fail-safe direction. Bounded by F-11‴ (both values constant, `unclassified` dead), by voice tool calls reaching no INSERT, and now by `dedupe_recorded_calls` shrinking the set of "recorded calls". |

---

## 9. What is genuinely better this round, and the one thing I would want recorded

**Three fixes are real and correctly diagnosed at the property, not at the string.** The 0.2 arming
is right after four failed attempts, and I could not construct a route around it. Gate F now asserts
column existence against the real DDL for all four columns — the round-4 finding was *"no test
asserts that three of the four columns exist"* and the fix asserts exactly that, generically. And the
0.6 measurement ran with the control that makes it readable and reported a null result honestly,
including the sentence that forbids ranking the formats — that is the harder thing to write than a
winner.

**The thing I would want recorded is where the failure moved.** For four rounds 0.2 failed because a
narrowing's record was never *made*. This round it is made correctly, and the item still fails
because the record can be *deleted on the way out* — by a reconciliation that is individually
defensible, defended by a recoverability claim that is false, and whose net effect is that a metric
which read 6.2% for three consecutive live rounds will now read 0% with no narrowing behaviour
changed. The same shape appears twice more: `dedupe_recorded_calls` removes rows from the run's
primary denominator on a key weaker than the identity of a call, untested, with the correct key
already present in the repository; and the voice pipeline's response to *"this column is NULL here"*
was to write a constant that the file's own code contradicts.

**A NULL that a verifier counts has become a value that no verifier will re-check.** That is the one
transformation this checkpoint cannot afford, because the entire premise of CP-0 is that a later
question about a turn has an answer which is not a reconstruction. Round 4's note was that each fix
closes the exact `file:line` the previous verdict cited. Round 5's is narrower and worse: on 0.1 and
0.2 the fix closed the *finding* by removing the thing that produced it.

**For the next round, the gate that would settle 0.2** is one that drives a real turn's advertise
event through the recorder and asserts a `hot_seed` entry survives `withheld_json()` — the output
the consumer receives — rather than one that asserts a string appears 1200 characters before a named
variable.
