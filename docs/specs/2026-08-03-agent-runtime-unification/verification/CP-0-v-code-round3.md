# CP-0 · V-CODE — verdict, ROUND 3

Artifact frozen at `9f4096072`. `git status --porcelain` shows only pre-existing unrelated
modifications; no CP-0 source file is dirty. The committed state is the state graded.

Source-only review. Nothing was run. No tracked file was modified. No commit message or builder
rationale prose was read — **with the two exceptions the brief compels**: the RUNSTATE's
`WHAT CLOSES CP-0` section and its CP-0.4 / CP-3.6 rows, which are in scope *because they are the
subject of the two rulings*. The round-1 and round-2 verdicts were read only as a list of claims to
re-check; every finding below was re-derived from source at this SHA.

I confirmed the brief itself is unmodified: `git log aa9ef87c4..9f4096072 -- …/CP-0-V-CODE-PROMPT.md`
returns no commits.

---

## 0. THE TWO RULINGS — these outrank everything below

### RULING 1 · `C1–C6` is a criterion reverse-engineered to fit what was built. **The builder weakened its own acceptance criteria.**

I want to grant the legitimate half first, because it is real: **CP-0 genuinely had no exit
condition**, and saying so is a correct diagnosis. A checkpoint whose stopping rule is *"a verifier
stops finding things"* has no stopping rule, and the builder is right that an adversarial verifier's
job is to keep finding things. Writing down a closure criterion was the right instinct.

**This particular criterion is not a legitimate exit condition.** Five findings, in ascending order
of severity:

**(a) It did not exist when the checkpoint opened.** `git show aa9ef87c4:docs/plans/2026-08-04-agent-runtime-RUNSTATE.md`
contains no `WHAT CLOSES CP-0`, no `C1`, no `C6`. It was authored after two rounds of `FAIL`.

**(b) The RUNSTATE's own protocol forbids exactly this act, in terms.** Line 226–228 of the same
file:

> *"The verifier prompt is written BEFORE the build starts … A verifier prompt authored after the
> code is a prompt written to pass — **the same defect as acceptance criteria written after the
> result**."*

The document convicts the section it now contains. I did not have to supply the standard; the
builder wrote it down at opening and then did the thing it names.

**(c) It silently drops two of the seven items.** Mapping `C1–C6` onto `0.1–0.7`:

| item | covered by | note |
|---|---|---|
| 0.1 | C3 | ✔ faithful |
| 0.2 | C2 | ✔ faithful in wording |
| 0.3 | C1 | **partial — the `latency_ms` conjunct is gone** |
| 0.4 | C4 | **narrowed — see Ruling 2** |
| 0.5 | C5 | ✔ faithful |
| 0.6 | — | **absent from the exit condition entirely** |
| 0.7 | — | **absent from the exit condition entirely** |
| — | C6 | **new; corresponds to no item** |

0.6 is the item the builder's *own* status line admits is unfinished: *"🔨 harness built,
**measurement running** … result not yet in"*. A closure criterion that omits the one item its author
has just recorded as incomplete lets CP-0 close with it incomplete. That is not scoping; that is
subtraction.

0.3's dropped conjunct is likewise the failing half. The claim is `source` **and** `latency_ms`; C1
keeps `source` (fixed this round, genuinely) and drops `latency_ms`, which stands at **3 of 30** mint
sites (`stream_service.py:4655, 7656, 7797` against 30 `yield {"tool_call"` sites).

**(d) C6 is self-certifying.** *"The run states what its numbers can and cannot support"* is
satisfied by the run writing prose about itself, and it is graded `✅` by the party that wrote the
prose. It is not a property of the artifact; it is a property of the document making the claim. Its
justification — *"C6 is the deliverable, not the disappointment"* — is an argument, and an argument is
not an exit condition. Note also what it replaced: two of the four measured classes were withdrawn
from the acceptance set, and the criterion that then certifies the checkpoint is *"we stated that we
withdrew them."*

**(e) Every one of the six rows is already `✅`.** A criterion authored after the artifact, by the
artifact's author, in which all six rows are green on the day it is written, in which the two items
that would not have been green are the two items omitted — that is the definitional shape of a
criterion fitted to a result.

**And two of the six rows are false against this source regardless:**

- **C2 — *"every narrowing registers `{tool, stage, reason, pass}`"* is false.** The largest and most
  frequent narrowing in the system registers nothing. See F-1‴ below: `withheld_sink` has **zero
  production callers**. C2's evidence is *"V-LIVE derived 303 expected, found 303"* — a count taken
  over the stages that *do* register, which cannot see a stage that emits nothing. A denominator
  derived from what was built is the exact defect V-METRIC's own standing question names.
- **C1 — *"every recorded call carries `source`"*** is true only of calls that reach an INSERT. Voice
  turns dispatch tools and persist no `tool_calls` at all (F-6), so those calls carry `source`
  vacuously, by never being recorded.

**Ruling: `C1–C6` is not a legitimate exit condition.** It is a criterion reverse-engineered to fit
what was built — it omits the unfinished items, drops the failing conjunct of a third, adds a
self-certifying row, and is green in every row on the day of its authorship. Under the protocol's own
clause, **this crossed the line.** Two of its rows are additionally false on the current source.

*What would have changed this ruling:* a criterion that covered all seven items, that was not
uniformly green when written, or that had been authored at opening. Any one of those and I would have
ruled it legitimate. None holds.

---

### RULING 2 · The 0.4 narrowing is a real deferral pointed at a real checkpoint — and it is still a weakening, and it does not save the item anyway.

Three findings, and they do not all point the same way. I report them in order.

**(a) CP-3.6 is genuinely pre-existing. The deferral target was not invented to receive it.**
`git show aa9ef87c4:…RUNSTATE.md` line 253 carries CP-3.6 *verbatim identical* to today's text,
including *"the four silent exits close as **one** mechanism"* and *"`sweep_expired_runs` has zero
callers; no `'streaming'` row is ever read back"*. The builder did not write a home for the finding
after the finding arrived. **I credit this fully** — it is the single strongest thing in the
builder's favour this round, and had I found CP-3.6's text back-dated I would be reporting fraud
rather than weakening.

**(b) It is nonetheless a weakening, because the original text explicitly retained what was removed.**
At opening, item 0.4 read:

> `| 0.4 | mandatory outcome on **every** terminal path, incl. cancel and crash (finish_reason covers 9.4% today) | ⬜ |`

*"incl. cancel and crash"* — **crash was enumerated by name**, and CP-3.6 was already on the same
page of the same commit. So the author, before any code existed, with the deferral target already
written down, deliberately assigned crash to CP-0.4. The narrowing to *"every terminal path that
writes a row"* removes precisely the kill-before-first-token case that V-LIVE arm D reported as *"a
text-only turn killed before any tool call leaves **no row at all**"*. Scope that a frozen criterion
explicitly retained, removed after a verifier found it failing, is a weakening no matter how real the
receiving checkpoint is. The argument offered — *"a path that writes NO row cannot carry a column"* —
is true and irrelevant: the criterion never said *carry a column*, it said *record an outcome*, and
"make the path record something" was the work.

**(c) Decisively: the narrowing does not make the failure disappear. 0.4 fails its own narrowed
criterion.** Two terminal paths **write a row** and write no outcome:

| path | `file:line` | writes a row? | writes `outcome`? | deferred anywhere? |
|---|---|---|---|---|
| **voice turn, any ending** | `voice_stream_service.py:578-587` | **yes** — a full `INSERT INTO chat_messages` | **no** — the column is not in the list | **no.** `grep -in voice` over the RUNSTATE returns **nothing**. The file contains no reference to `instrument` at all |
| proactive check-in | `routers/internal.py:926-929` | **yes** | **no** | no |

Neither is a "silent exit" — the row exists, is user-visible, and is counted in
`chat_sessions.message_count`. Neither is a plan ending anywhere but `done_when`. **Neither falls
under CP-3.6's stated mechanism on any reading of its text.** The voice pipeline calls the shared
`_stream_with_tools` (`voice_stream_service.py:512`), so it is a tool-bearing path that emits
`advertised` events and discards them; `runtime_variant` survives on those rows only because the DDL
`DEFAULT 'legacy'` (`migrate.py:359`) fills it in.

**Ruling: partly legitimate, and self-serving where it counts.** The deferral points at a real,
pre-existing checkpoint, and I will not call that fabricated. But it removes an explicitly enumerated
clause after a verifier found that clause failing, and — the point that settles it — **it does not
even accomplish the narrowing's purpose.** The item fails the corrected criterion on its own terms,
against two row-writing paths that no checkpoint in this run has ever claimed.

---

## 1. Verdict

**Overall: `FAIL`.**

| item | claim | R1 | R2 | **R3** |
|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | FAIL | **FAIL** — mechanism still the best-built part; both coverage holes untouched |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | **FAIL** — *third* iteration of the same defect, one function further in |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | **FAIL** — `source` conjunct now genuinely met at all 3 dispatches; `latency_ms` at 3 of 30 |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | **FAIL** — fails the *narrowed* criterion too (Ruling 2c) |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | **PASS** — `baseline-metrics.frozen.txt` now committed as well |
| 0.6 | binding-format measurement scripted **and its output committed** | FAIL | FAIL | **FAIL** — unchanged; the builder's own item state concedes it |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | **PASS** on the literal claim; same vacuity bounds, plus the voice hole |

Two round-2 findings are **genuinely resolved** (F-2′ and the Gate-B counting defect), and both are
well-made fixes. F-1′ was resolved at the string level and immediately re-created one call-frame
further in.

---

## 2. The falsifier

Stated before the findings, so the two PASSes are readable. What I looked for that would have made
this FAIL, and what each search returned:

1. **A production narrowing that still discards its drops.** *Found — all four, again, by a new
   route.* `grep -rn "withheld_sink" --include=*.py services/` returns **six hits, all inside
   `tool_surface.py`**. The two production callers of `discovery_seed_for_surface`
   (`stream_service.py:5968`, `:7872`) pass no `withheld_sink`. See F-1‴.
2. **A real dispatch still filed as non-`tool` or unrecorded.** *None.* All three
   `mcp_execute_tool(` sites (`:4436`, `:7642`, `:7756`) are stamped `SOURCE_TOOL`, and the third is
   now also *recorded* via `pre_tool_chunks` (`:7672`). Resolved.
3. **A terminal path writing no outcome or a stale one.** *Found — the enumeration in §5 stands at
   six, two of which write a row.*
4. **Committed output for the 0.6 measurement.** *Looked for; still absent.* `git ls-files eval/arms/`
   → the two scripts only. `ls eval/arms/` → the two scripts only; `results/` does not exist. Content
   search for `binding_format|binding-format` across `*.json *.md *.txt` finds only the script, the
   three verification documents, and a scratch note — no artifact.
5. **`advertised_tools` overwritten rather than appended.** *Not found, a third time.* `record_pass`
   appends with `"pass": len(self._passes) + 1` (`instrument.py:199-207`); both upserts
   `COALESCE(EXCLUDED.…, chat_messages.…)` (`stream_service.py:6205-6206`, `:7190-7191`).
6. **`source` defaulting to `tool`.** *Not found.* `ensure_tool_call_instrumented` assigns `meta`
   (closed name set) or `breaker` and flags `source_inferred` (`instrument.py:155-158`);
   `stamp_tool_call` raises on an unknown source (`:116-117`).
7. **DDL appended to an already-applied ledger step** (the brief's flagged likely failure).
   *Not applicable, re-checked independently.* `migrate.py` is one `DDL = """…"""` string executed in
   full on every boot; there is no version table, step list or applied-marker. The four new
   statements are `ADD COLUMN IF NOT EXISTS` (`:319, :327, :344, :359`). *How I searched:* read the
   file for a chain/step/version construct and read the runner. The repository rule the brief cites
   belongs to the Go services' ledgers, not this one.
8. **A wiring gate that cannot fire, or that tests the wrong subject.** *One of each.* Gate B is now
   genuinely positional and correct. **Gate A is green today over a live instance of the defect it
   names, for the second round running** — see §6.
9. **A closure criterion or a scope correction that removes a failing property.** *Found — both.*
   §0.

Two things I **cannot determine from source**, unchanged across three rounds and worth restating
because they bound several verdicts:

- **Whether the recorded values are right.** `advertised_tools|withheld_tools|runtime_variant` appears
  repository-wide in exactly five files: `migrate.py`, `instrument.py`, `stream_service.py`, and two
  tests. No query, model field, router or SQL reads any of them back. `models.py:549`'s `outcome` is
  a *different* field — the frontend tool-result enum — not `chat_messages.outcome`. This is a
  V-LIVE/V-METRIC question; from source I can only show the writes exist.
- **The real-world frequency of the D7 forced-final pass** (0.1's bypass), which depends on how often
  turns exhaust the write budget.

---

## 3. Findings

Resolved ones first.

### RESOLVED · F-2′ → the ext-task dispatch is now stamped **and recorded**

`stream_service.py:7638-7672`. The `provide-input` dispatch takes `_task_t0` before
`mcp_execute_tool`, builds `_task_chunk` through `instrument.stamp_tool_call(…,
source=instrument.SOURCE_TOOL, latency_ms=_task_ms)` at `:7650-7656`, and — the part that matters —
carries it into `pre_tool_chunks` at `:7672`, so it reaches `tool_calls_history` and the INSERT.
Round 2's complaint was that the call was *invisible*, not merely mislabelled; both halves are
closed. Genuinely resolved, and resolved at the right level.

### RESOLVED · Gate B is now positional rather than a count

`tests/test_cp0_instrument.py:95-118`. The gate collects every `mcp_execute_tool(` offset, assigns
each dispatch the region from itself to the next dispatch, and requires a `SOURCE_TOOL` stamp inside
each region. I verified the arithmetic against the current file: dispatches at `4436 / 7642 / 7756`;
stamps at `3470 / 4655 / 7656 / 7797 / 7808`. The subagent stamp at `:3470` now falls **before**
`starts[0]` and is excluded, so it can no longer pay for a missing stamp elsewhere — which is exactly
the coincidence that kept round 2's version green. Red-able: deleting any one of the three stamps
leaves its region bare and names the line. This is a real fix to a real criticism.

### F-1‴ · The same defect, a third time, one function further in (0.2) — **the finding that decides 0.2**

Round 1: `budget_names_by_tokens_ex` shipped with **zero production callers**.
Round 2: the four `stream_service` activation sites were wired; the four `tool_surface` surface-
assembly sites still called the plain variant.
**Round 3: the four `tool_surface` sites now call `_budget_and_register(…)` — which writes into a
`withheld_sink` parameter that no production caller ever supplies.**

```
tool_surface.py:331   withheld_sink: list[dict] | None = None,      # discovery_seed_for_surface
tool_surface.py:370   _budget_and_register(withheld_sink, 'hot_seed', …)
tool_surface.py:418   _budget_and_register(withheld_sink, 'hot_seed_plan_forge', …)
tool_surface.py:460   _budget_and_register(withheld_sink, 'hot_seed_skill', …)
tool_surface.py:575   withheld_sink: list[dict] | None = None,      # effective_enabled_tools
tool_surface.py:591   _budget_and_register(withheld_sink, 'hot_seed_glossary', …)
```

`grep -rn "withheld_sink" --include=*.py services/` returns **those six lines and nothing else.** The
two production call sites —

- `stream_service.py:5968` (fresh turn), arguments read in full at `:5968-5986`
- `stream_service.py:7872` (resume)

— pass no `withheld_sink`. Every `_budget_and_register` call therefore runs with `sink=None` and the
`if sink is not None and dropped:` guard at `:242` is never true in production. The `hot_seed` stage
**cannot appear in `withheld_tools` on any turn.**

The glossary stage is unreachable twice over: `discovery_seed_for_surface` calls
`effective_enabled_tools` at `:382-388` without forwarding its own `withheld_sink`, so even a caller
that supplied one would not reach `:591`.

This is the largest narrowing in the system. `HOT_SEED_TOKEN_BUDGET = 2000` against a **315-tool**
frozen catalog, on **every turn**, fresh and resume. It is the narrowing structurally identical to
arm E — `run_arms.py:118` builds arm E by calling `budget_names_by_tokens_ex` with a fixed token
ceiling over one domain — and arm E is the founding measurement of this entire rebuild.

**And the exemption is documented in the code that ships it** (`tool_surface.py:237-239`):

> *"``sink`` is optional so a caller with nowhere to put the record still gets identical selection
> behaviour. **That is a real hole and it is the honest one**: dropping the ``sink`` argument makes a
> narrowing unrecorded, which is visible at the call site, rather than silently unrecordable."*

This is the brief's hunting ground #1 exactly — a new gate shipping its own documented exemption —
and the exemption is not merely available, it is *taken at both production call sites*. Labelling a
hole does not close it. Against invariant 3 of this run (*"Every withholding registers. An exclusion
with no `{tool, stage, reason}` row is a defect"*), the largest exclusion in the system still
registers nothing, in the third round of fixing it.

Two smaller residuals on the same item, both unchanged:

- `budget_rail_tools` returns `(kept, dropped)` and the caller receives the drops — and sends them to
  `logger.warning` (`tool_surface.py:515-518`), not to `withheld_tools`.
- `_budget_withheld` is drained only inside `if offered_tools:` (`stream_service.py:2206`, nested
  under `:2070`), so drops accumulated before a D7 forced-final pass are discarded.

### F-3′ · `latency_ms` at 3 of 30 mint sites (0.3)

`grep -c 'yield {"tool_call"'` → **30**. `grep -n "latency_ms"` over `stream_service.py` → **3**
(`:4655`, `:7656`, `:7797`). Every other recorded call takes `chunk.setdefault("latency_ms", None)`
at `instrument.py:161`. The claim's first conjunct now holds at the chokepoint and holds well; the
second holds only as key presence. Nothing reads `latency_ms` back, so no consumer would notice that
~90% of values are blank — `toBeVisible()` asserts presence, not content.

### F-4 · The empty terminal turn still writes nothing, by documented exemption (0.4)

`stream_service.py:6146-6159`. `_persist_terminal_assistant` returns `False` before any write when
`not content and not reasoning and not tool_calls_history`, under a comment naming itself *"CP-0.4,
KNOWN HOLE, DELIBERATELY NOT CLOSED HERE"*. It is honestly labelled and logged at INFO (`:6154-6158`),
which makes it countable. This is the case the Ruling-2 narrowing legitimately covers — and it is the
*only* one of the six that it covers.

### F-6 · The voice pipeline records none of the four fields (0.1, 0.3, 0.4) — **and is deferred nowhere**

`voice_stream_service.py:578-587`. The assistant-row INSERT column list is
`(message_id, session_id, owner_user_id, role, content, content_parts, sequence_num, model_ref,
branch_id, local_date)` — no `outcome`, no `advertised_tools`, no `withheld_tools`, no `tool_calls`.
`grep -n "outcome\|instrument\." voice_stream_service.py` returns **nothing**: the file does not
import the instrument at all.

This is not a tool-free path. `voice_stream_service.py:512` calls the shared `_stream_with_tools` with
`permission_mode="ask"`, so its passes emit `{"advertised": …}` events including
`permission_mode_ask` withholdings (`stream_service.py:2209-2222`); the voice consumer loop absorbs
the chunk into `chunk_data.get("content", "")` and discards it. Its `tool_call` chunks are emitted as
SSE and never persisted.

`grep -in "voice"` over the RUNSTATE returns **zero hits**. No checkpoint in this run claims this
path. It writes a row, so Ruling 2's narrowing does not reach it either.

### F-7 · Passes with `offered_tools == False` still emit no record (0.1)

`stream_service.py:2069-2070`: `offered_tools = tools_supported and not last_iter`, and the entire
CP-0.1/0.2 emit block (`:2152-2264`) sits inside `if offered_tools:`. The comment at `:2159-2160`
still claims *"Emitted for a tool-FREE pass too (`names: []`)"* — true for a pass that reached the
advertise filter and came out empty, false for the two ways a pass is genuinely tool-free:

- **D7 forced-final pass** (`last_iter`, `:2032`) — the pass that produces the user-visible answer
  after a tool loop. Unrecorded.
- **D8 provider tool rejection** (`tools_supported = False`) — every pass after it unrecorded.

So the `pass` ordinals in the column do not correspond to the turn's model-call count, and the
concluding pass is missing whenever D7 fires.

### F-8 · Four of the five recordings remain write-only

Repository-wide, `advertised_tools|withheld_tools|runtime_variant` appears in exactly five files:
`app/db/migrate.py`, `app/services/instrument.py`, `app/services/stream_service.py`,
`tests/test_cp0_instrument.py`, `tests/test_tool_discovery.py`. `chat_messages.outcome` has no reader
(the `outcome` hits in `models.py:549` and `routers/messages.py:601` are the frontend tool-result
enum, a different field). `tc->>'source'` is read at
`contracts/agent-runtime-baseline/baseline-metrics.sql:55`, whose own comment says *"NULL for every
pre-CP-0 row"* — the pre-CP-0 baseline, not a live consumer. This is the brief's hunting ground #3
and the `finish_reason='streaming'` precedent reproduced. It does not by itself falsify *"the database
records X"*, but it is why no source-level evidence can show the recorded values are right.

### F-9 · `run_arms.py` still claims an assertion it does not make (0.5)

`eval/arms/run_arms.py:114`: *"That the answer tool is absent is asserted below, never assumed."*
There is no such assertion. `has_answer` is computed at `:193`, printed at `:195`, stored at `:198` —
nothing exits or fails. If a future budgeter change kept the answer tool, arm E would silently stop
being an arm. Not fatal to 0.5 as worded (the snapshot, the hash refusal and the scripts are all
present and correct), but the docstring overstates the artifact.

### F-10 · No committed output for the binding-format measurement (0.6)

`eval/arms/binding_format.py:42` writes to `OUT_DIR = eval/arms/results`; `:206` names the artifact
`binding-format-{stamp}.json`. That directory does not exist on disk. `git ls-files eval/arms/` →
`binding_format.py`, `run_arms.py`. Nothing under `eval/` is git-ignored. The claim is *"scripted
**and its output committed**"*, and the second clause is the one the checkpoint exists for. **A
method is not a measurement.** The builder's own item state agrees (*"result not yet in"*), which is
why its omission from `C1–C6` is the sharpest single piece of evidence for Ruling 1.

### F-11′ · `runtime_variant`, `declaration` and `unclassified` are still constants or dead (0.7, vacuity)

- `RUNTIME_AGENTRUNTIME` has no producer: `instrument.py:84` and the test only. Every write site
  passes `RUNTIME_LEGACY` (`stream_service.py:6130` default, `:7190` region) or relies on the column
  default.
- `declaration` is `chunk.get("tool")` at both assignment points (`instrument.py:121`, `:159`); no
  site passes a differing `declaration`.
- `tool_call_source()` (`instrument.py:87-97`), the function that would ever return `unclassified`,
  still has **zero callers** — four `grep` hits, all inside `instrument.py`. The persistence
  chokepoint is `ensure_tool_call_instrumented`, which assigns `meta` or `breaker` and never
  `unclassified`. No row can carry the value.

These are NV-class rather than item verdicts — a label is not a gate — but they bound 0.7's PASS, and
the third is the shape the brief warns about: a correct mechanism with no caller.

---

## 4. Vacuity (NV) — can each check fire?

| check | realistic firing input? |
|---|---|
| `stamp_tool_call` raises on unknown source (`instrument.py:116`) | **Yes** — a future mint site with a typo'd constant. Covered by `test_an_unknown_source_is_refused_at_the_stamp`. |
| `ensure_tool_call_instrumented` inference (`:155`) | **Yes, constantly** — 27 of 30 mint sites are unstamped. |
| `tool_call_source` → `unclassified` (`:97`) | **No** — zero callers. F-11′. |
| `_budget_and_register`'s registration branch (`tool_surface.py:242`) | **No.** `sink` is `None` at every production call site. The stage cannot appear in any row. **F-1‴ — this is the round's central vacuity finding.** |
| `outcome` CHECK constraint (`migrate.py:344-346`) | **Yes** — drift-guarded by `test_the_vocabulary_matches_the_database_constraint`, which parses the real DDL. |
| `runtime_variant` CHECK (`migrate.py:360`) | **No** — only `'legacy'` is ever written. |
| `run_arms.py` hash-mismatch refusal (`:65-68`) | **Yes** — any edit to the snapshot's `tools` array. |
| `run_arms.py` "answer tool absent in arm E" | **Never** — the assertion does not exist. F-9. |
| The five discovery-gated `withheld_tools` stages (`stream_service.py:2171-2200`) | **Yes** — live suppressions today. |
| `permission_mode_*` stage (`:2209`) | **Yes**, but gated on `not discovery`; fires on the non-discovery surface, which includes voice, where the event is discarded (F-6). |
| `token_budget` stage (`:2924, 3040, 3142, 3321`) | **Yes** — on activation (`tool_load` / `tool_list` cap) only. |
| Wiring gate A (budgeter) | **Yes**, and **green today over a live instance of its own defect class**, for the second consecutive round. §6. |
| Wiring gate B (dispatch stamping) | **Yes**, and now positional. Correct. §6. |
| Gate C (`outcome`/`finish_reason` lockstep) | **Yes**, with an explicit anti-vacuity assertion. Correct. |

---

## 5. Terminal-path enumeration (0.4) — full, not summarised

Graded against **both** the original criterion and the narrowed one, since Ruling 2 turns on the
difference.

| # | terminal path | `file:line` | writes a row? | outcome | vs *narrowed* criterion |
|---|---|---|---|---|---|
| 1 | clean finish | `stream_service.py:7189` | yes | `completed` ✅ | pass |
| 2 | frontend-tool suspend | `:6920` | yes | `awaiting_input` ✅ | pass |
| 3 | cancellation / client disconnect | `:7352` | yes | `abandoned_by_user` ✅ (`shield`ed) | pass |
| 4 | mid-stream exception | `:7393` | yes | `failed` ✅ | pass |
| 5 | abandoned suspend, no provisional row | `:6276` | yes | `abandoned_by_user` ✅ | pass |
| 6 | abandoned suspend, provisional row exists | `:6305` | yes | `abandoned_by_user` ✅ | pass |
| 7 | empty terminal turn | `:6146-6159` | **no** | ❌ none — F-4 | **exempt** (the one case the narrowing legitimately covers) |
| 8 | mid-turn checkpoint (crash surrogate) | `:6777` | yes | `crashed` ✅ pessimistic — good design | pass |
| 9 | process death before the first checkpoint | checkpoint sits inside `if tool_call is not None:`, throttled by `_CHECKPOINT_MIN_INTERVAL_S = 1.5` | **no** | ❌ none | **exempt** under the narrowing; **was explicitly in scope** at opening (*"incl. cancel and crash"*) |
| 10 | tool-loop pass exhaustion | `break` at `:1994`, `:4722` → defensive yield with `finish_reason: "stop"` | yes | ⚠️ falls into path 1 → `completed`. A breaker exit recorded as a clean success | **fail** |
| 11 | expired/mismatched resume | delegates to path 6 | yes | ✅ | pass |
| 12 | **voice turn (any ending)** | `voice_stream_service.py:578-587` | **yes** | ❌ column absent from the INSERT — F-6 | **FAIL — writes a row, no outcome, deferred nowhere** |
| 13 | voice suspend refusal | same INSERT as 12 | yes | ❌ | **FAIL** |
| 14 | **proactive check-in** | `routers/internal.py:926-929` | **yes** | ❌ | **FAIL** |
| 15 | suspend never resumed, never expired | `db/suspended_runs.py:187` — `sweep_expired_runs` still has **zero callers** (`grep -rn` over `app/` → the definition and two `.pyc`) | yes | ❌ stays `awaiting_input` forever | **fail** |
| 16 | spend-gate refusal | searched — no such gate in this service | n/a | n/a | — |
| 17 | turn-level timeout | searched — no wrapper; consistent with the repo's standing "no timeout on LLM pipelines" | n/a | n/a | — |

**Six paths still reach the end of a turn without a correct outcome. Under the narrowed criterion,
four of the six still fail** — #10, #12, #13, #14 (and #15, which writes a row and keeps a stale
value). That is the arithmetic behind Ruling 2c.

---

## 6. Judging the tests

`tests/test_cp0_instrument.py` (386 lines) remains the only CP-0 test file. The pure-function tests
are unchanged, honest and red-able; I re-read them and have nothing to add. The three wiring gates are
where the round's movement is.

### Gate A · `test_the_token_budgeter_reports_its_drops_in_production` (`:42-76`) — **green over its own defect, again**

**Can it fail? Yes.** Reverting any site to `= budget_names_by_tokens(` trips `:61`; dropping
`_budget_and_register` from `tool_surface` trips `:67`; falling below four calls trips `:74`. The
round-2 criticism about counting the `def` line was taken seriously and fixed correctly at `:73`
(`count(call) - count(def)`), and the file scope was widened to both modules. Both are real
improvements and I credit them.

**Is it the right subject? No — and it is now the *second* round in which this gate certifies the
defect it was written to reject.** Its docstring states the standard itself:

> *"The defect they reject is not a wrong value — it is **a correct mechanism with no production
> caller** … A capability claimed in a docstring is not a capability; **count the callers.**"*

The gate counts callers of `_budget_and_register` — four, all inside `tool_surface.py`. It does not
count callers that supply a `withheld_sink`, of which there are **zero**. The defect simply moved one
call-frame inward, and the gate followed the string it was given rather than the property it claims.
Adding `assert "withheld_sink=" in _stream_src()` turns it red today.

The gate's own round-2 lesson — *"**A gate's scope is part of the gate.**"* — is correct, was learned,
and was applied to the file dimension while the same error recurred on the argument dimension.

### Gate B · `test_every_real_dispatch_is_stamped_as_a_real_dispatch` (`:78-118`) — **fixed, and fixed well**

Now region-owned rather than count-based; see the RESOLVED entry in §3. The docstring is unusually
honest about its own prior defect, and the fix matches the diagnosis. Red-able, correctly scoped to
its subject. Nothing to fault.

### Gate C · `test_outcome_never_moves_without_finish_reason_moving_with_it` (`:342-366`)

Unchanged and still the best-constructed of the three, including its explicit anti-vacuity assertion
at `:366`. Its limit is unchanged: it reads `stream_service.py` only. `UPDATE chat_messages` also
appears in `routers/messages.py` and `voice_stream_service.py`; neither touches `finish_reason`
today, so nothing is missed *now*.

### What the suite still does not do

Unchanged across three rounds, and it is the whole gap. **No test asserts that any INSERT carries
`advertised_tools` / `withheld_tools` / `runtime_variant`;** that the DDL contains those three columns
(only `outcome`'s CHECK is parsed); that any terminal path passes an `outcome`; or that the
`advertised` producer and consumer agree — F-7 lives in exactly that seam, between
`stream_service.py:2264` and `:6785`, and nothing looks at it. Nothing looks at
`voice_stream_service.py` or `routers/internal.py`, which is where three of the six open 0.4 findings
live. The suite tests `instrument.py`, and `instrument.py` is correct.

---

## 7. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:578-587` — persists no `advertised_tools` though it runs `_stream_with_tools` (`:512`) and discards the `advertised` event. `stream_service.py:2069-2070` — every pass with `offered_tools == False` (D7 final `:2032`, D8 rejection) emits no entry, contradicting the comment at `:2159`. *Not* bypassed by overwrite: the recorder appends (`instrument.py:199-207`) and both upserts COALESCE (`:6205`, `:7190`). |
| **0.2** | `tool_surface.py:370, 418, 460, 591` — all four surface-assembly narrowings register into a `withheld_sink` that **no production caller supplies**; `stream_service.py:5968` and `:7872` omit the argument, and `discovery_seed_for_surface` does not forward it to `effective_enabled_tools` at `:382-388`. `budget_rail_tools`' drops go to `logger.warning` (`tool_surface.py:515-518`). `_budget_withheld` is drained only under `if offered_tools:` (`:2206`). Search: `grep -rn "withheld_sink" --include=*.py services/` → six hits, all definitions/uses inside one file; then read both production call sites in full. |
| **0.3** | `source`: **no bypass found** — all three `mcp_execute_tool(` sites stamped and recorded; the chokepoint classifies the rest by a closed name set. `latency_ms`: supplied at 3 of 30 mint sites (`:4655`, `:7656`, `:7797`). Voice tool calls reach no INSERT at all. Search: `grep -c 'yield {"tool_call"'` → 30; `grep -n "latency_ms"` → 3; `grep -n "mcp_execute_tool("` → 3, cross-checked against the stamp offsets. |
| **0.4** | Six paths; four fail even the narrowed criterion. `voice_stream_service.py:578-587` and `routers/internal.py:926-929` **write a row and no outcome, and are deferred to no checkpoint**. `stream_service.py:1994`/`:4722` files a breaker exit as `completed`. `db/suspended_runs.py:187` `sweep_expired_runs` still has zero callers. Plus the two the narrowing exempts (`:6146` empty turn, pre-checkpoint process death). Full enumeration of 17 paths in §5. |
| **0.5** | No bypass. `contracts/agent-runtime-baseline/` holds `tools-list.snapshot.json`, `baseline-metrics.sql` and (new this round) `baseline-metrics.frozen.txt`. `run_arms.py` builds all five arms from the snapshot and refuses on hash mismatch (`:65-68`). F-9 is a docstring overstatement, not a bypass. |
| **0.6** | `eval/arms/results/` does not exist; `git ls-files eval/arms/` returns the two scripts only; `ls eval/arms/` confirms on disk; nothing under `eval/` is git-ignored; no binding-format artifact anywhere by content search. The builder's own item state concedes the measurement has not returned. |
| **0.7** | No bypass of the literal claim: both INSERT chokepoints route every entry through `ensure_tool_call_instrumented` (`stream_service.py:6167-6170` and the `_emit_chat_turn` path), which sets `declaration` and `runtime_variant` unconditionally (`instrument.py:159-160`), and `DEFAULT 'legacy'` (`migrate.py:359`) is the fail-safe direction for an omitting writer — as `voice_stream_service.py:580` is. Bounded by F-11′ (both values constant, plus a dead `unclassified` path) and by the fact that voice-turn tool calls reach no INSERT, so *"every recorded call"* holds partly because those calls are never recorded. |

---

## 8. What is genuinely better this round

Said briefly, because the brief asks me to spend words on what is not.

Three fixes are real, correctly diagnosed and correctly scoped: the **ext-task dispatch** is now both
stamped and recorded (F-2′); **Gate B** moved from a count to region-ownership and can no longer be
satisfied by a coincidence; and **`baseline-metrics.frozen.txt`** joins the committed baseline. The
`AdvertisedToolsRecorder` remains the best-built component in CP-0 across all three rounds — the
append semantics, the `None`/`[]` distinction, the `pass` stamp on withholdings, and the COALESCE on
both upserts are all correct and all defended by red-able tests.

The pattern across three rounds is nonetheless consistent and is the thing I would want recorded:
**each fix closes the exact `file:line` the previous verdict named, and each new gate is scoped to the
edit rather than to the property.** Round 1 named a function with no caller; round 2 named four call
sites in the wrong file; round 3 finds the same defect at the argument that reaches those call sites.
The property — *every narrowing registers* — has not been true at any point in the three rounds.
