# POC P1 + P2 — measured on the live stack, 2026-08-03

**Why these exist.** The spec borrows its architecture from Entity Framework, Backstage, Temporal and
the MCP registry ecosystem. **None of those has a client that is an LLM** — a caller that passes
strings and can never fail to compile. The PO's instruction was therefore to *decide the architecture
by POC rather than refactor and discover the assumption was wrong*. Each POC below is designed to
**falsify** a spec requirement, not to confirm it.

Sources: `ai-gateway /mcp tools/list` (live, 315 tools) and `loreweave_chat.chat_messages.tool_calls`
(7,442 calls across 549 sessions). Both reproducible; commands in §4.

---

## P1 — Can a group hierarchy be derived from tool names? **NO.**

R2/R14.2 assume a tool's group (and, at scale, its path) can be organised from the name. Test: does
the second name segment form a taxonomy?

| level-1 prefix | noun-first level-2 | verb-first level-2 | mixed? |
|---|---|---|---|
| `composition` (107) | 89 | 15 | ✅ |
| `glossary` (54) | 26 | 26 | ✅ |
| `kg` (31) | 19 | 11 | ✅ |
| `book` (35) | 24 | 5 | ✅ |
| `plan` (16) | 4 | 9 | ✅ |
| `world` (17) | 11 | 1 | ✅ |
| `settings` (12) | 7 | 5 | ✅ |
| `translation` (12) | 3 | 8 | ✅ |

**8 of 8 mix nouns (`arc`, `motif`, `entity`, `chapter`) with verbs (`get`, `list`, `propose`) at the
same level.** `glossary` is an exact 26/26 split.

**Verdict — the path must be DECLARED, never parsed.** Any scheme deriving structure from the name
inherits this inconsistency, which is also the root reason `_domain_of` was always fragile. Settles
DESIGN Q15's "who decides a tool's path": the author, at registration, gate-checked.

Supporting scale facts, measured (not estimated): **315 tools · ~130k tokens of schema · 413 tokens per
tool** — higher than the 375 the spec first estimated. `composition` alone is 107 tools, a third of the
catalog, so the flat taxonomy fails today rather than at 3,000. And **17 level-1 prefixes exist while
`GROUP_DIRECTORY` declares 14** — three already unaccounted for.

---

## P2 — Is the infinite loop caused by ambiguous tool errors? **PARTLY — and the larger half is us.**

R10 (the error contract) is premised on the loop being driven by errors the model cannot act on. Test:
autopsy every tool call in the real history.

### The shape of the problem

| | |
|---|---|
| tool calls | **7,442** across 549 sessions |
| failed (`ok=false`) | **4,007 — 54% of every call ever made** |
| byte-identical repeats (same session, tool, args) | **5,508 — 74% of all calls** |
| of those repeats | 3,669 error · 1,839 success |

### 🔴 The finding that changes the spec

Of 3,976 errors carrying text, **58% are not tool failures at all — they are our own loop-breakers'
output**:

| count | error text |
|---|---|
| 1,180 | *"You have already called `tool_list` with these exact arguments this turn and it returns the SAME list every time"* |
| 495 | *"You have already called `book_get` … it returned the IDENTICAL …"* |
| 263 | *"`kg_project_create` already ran this turn … reported created=false"* |
| 157 | *"`find_tools` has been called with no `intent` N times this turn — STOP…"* |
| 86 | *"`book_chapter_save_draft` keeps being called with missing/blank required arguments — STOP."* |

**2,318 of 3,976 errors (58%) are breaker feedback — 31% of every tool call in the system.** Each is a
call the model emitted, the tool never ran, and a full tool-loop pass was burned re-sending the entire
context.

**The breakers are participants in the loop, not terminators of it.** The breaker returns prose → the
prose enters context → the model reads "STOP" and calls again → the breaker fires again. This is the
context-contamination mechanism observed in our own production data.

> **A message cannot stop a model. Only an absent affordance can.**

The repo already discovered this empirically and wrote it down at `stream_service.py:1905-1911`:
*"Short-circuiting DISPATCH isn't enough; take the tool OFF THE WIRE so it physically cannot be
re-emitted."* The de-advertise escalation is the mechanism that works. **The messages are the mechanism
that fails, and they outnumber real errors 3:2.**

### R10's taxonomy, tested against real tool errors only

Excluding breaker output, the 1,658 genuine tool errors classify well:

| bucket | count | share |
|---|---|---|
| `retryable_modified` | 962 | 58% |
| `terminal_permanent` | 415 | 25% |
| UNCLASSIFIED | 277 | 17% |
| `retryable_transient` | 4 | 0% |

**83% bucket deterministically.** R10's taxonomy is sound — but it addresses **42% of error volume**,
not the loop's dominant driver. `retryable_transient` being ~0 is itself informative: these are not
flaky-network loops, they are *the model being wrong the same way repeatedly*.

### Concentration

Breaker storms occur in **73 of 549 sessions (13%)**, and the **top 5 sessions produce 66%** of all
breaker output. The median session is healthy; the failure is a tail that consumes the budget.

### Consequences for the spec

1. **R10 stays, re-scoped honestly.** It fixes the 42% and improves error quality. It is **not** the
   loop fix, and its DoD must not claim to be.
2. **The loop fix is R4/R5** — `excluded_by` withholding the affordance — promoted in priority. Add
   the rule this POC produced: **a guard withholds; it does not argue.** Returning a "STOP" string as
   a tool result is itself a defect, because the tool result is exactly the channel the model is free
   to ignore.
3. **R14 is urgent, not speculative.** `tool_list` is the **single largest loop source in the system**
   (1,180 breaker fires). The tool built to fix discovery is the biggest generator of the failure it
   was meant to fix — measured, in production data.
4. **The 54% failure rate is itself the headline.** No amount of prompt or skill work matters while
   more than half of every tool call fails.

---

## ⚠️ RETRACTION AND CORRECTION (2026-08-04)

**P2b as first written is withdrawn.** The PO challenged it on two grounds — that skills and tool
schemas are a *fixed* per-turn cost that does not balloon, and that against a large window they are a
small share — and then said the measurement itself looked wrong. Both objections were correct, and
checking them exposed a sampling bias worse than the framing error.

**What was wrong:**

1. **Sampling bias.** `context_breakdown` exists on only **2,029 of 5,720 messages (35%)**, and the
   coverage is **zero before July 2026** — the instrumentation did not exist. A freshly driven turn
   (session `019fc893-…`, 3 tool calls, 2026-08-04) wrote **no `context_breakdown` and no
   `input_tokens` at all**. The aggregate was therefore a July-only, partially-instrumented sample.
2. **Cumulative spend was reported as context occupancy.** Summing a *fixed* per-turn cost across
   2,029 messages and calling the result "80% of every turn" conflates what we *pay* with what the
   window *holds*. The two diverge exactly when the tool loop re-sends the same prompt.
3. **The tail metric was misread.** `pct` and `raw_tokens` are **cumulative across tool-loop passes**,
   not context size. The worst observed turn showed `pct` 4.69 (469%) against a `context_size` of
   **33,918** — i.e. ~28 passes over the same 34k prompt, **96% of it served from cache**. It was
   never a full window.

**What the PO was right about, confirmed:** tool schemas are fixed per session — in **112 of 119**
sessions with ≥4 messages, `mcp_tool_schemas` varies by under 25% (mean spread 1,165 tokens). They do
not balloon. Median context utilisation is **14.4%** of target. **There is no context-pressure
problem in the median case.**

**Therefore withdrawn:** "80% of every turn is schemas and skills", "≈28% of all context ever was
schemas on zero-tool turns", and "R14 is the budget fix". None survive the sampling check.

**Standing finding, retained:** the loop is a **pass-count, latency and call-count** problem, not a
context-occupancy problem. Bounding passes (R11) matters; R14 remains justified by C1 and by
selection accuracy, **not** by context pressure.

**A real defect surfaced by the correction:** the context telemetry is partial and undated —
35% coverage, nothing before July, and nothing on a turn driven today. Any future budget decision
(R13.6.1's per-artifact ceilings, DESIGN Q18) rests on instrumentation that currently cannot support
it. Fixing the telemetry is a prerequisite for those, not a nicety.

---

## P2 — re-checked against the sampling bias, and it **strengthens**

The same bias check was applied to P2, which reads `tool_calls` rather than `context_breakdown`. The
concern was that sessions named `G-off`, `G-step_lock-*`, `M-per_turn`, `ds-M0-outage-*` are
**deliberate experiments that exist to trigger the breakers**, so P2 might have measured its own test
harness. Segmented:

| session kind | calls | errors | error rate | of which breaker output |
|---|---|---|---|---|
| **organic** | 3,813 | 2,749 | **72.1%** | **1,928** |
| experiment | 3,632 | 1,259 | 34.7% | 415 |

**Organic sessions fail at twice the rate of the experiments**, and **70% of organic errors are our
own breaker messages** — so **more than half of every tool call in real use is the model arguing with
a breaker.** P2's conclusion is not an artifact of the harness; the harness was the healthier half.

---

## P2b (ORIGINAL, SUPERSEDED BY THE RETRACTION ABOVE) — kept for the audit trail

The PO asked whether the budget is consumed by stuffing tool input/output into the session and keeping
it there as conversation. Measured over 2,029 messages carrying `context_breakdown`:

| category | avg tokens / message | share | lifetime total |
|---|---|---|---|
| **`mcp_tool_schemas`** | **11,725** | **41%** | 23.8M |
| **`skills`** | **9,162** | **32%** | 18.6M |
| `history` (the actual conversation) | 4,424 | 15% | 9.0M |
| `frontend_tool_schemas` | 2,137 | 7% | 4.3M |
| **`tool_results`** | **1,146** | **4%** | 2.3M |

**Answer: no.** Tool output is 4% and conversation history is 15%. `tool_result_token_cap` and
compaction are working — that part of the system was fixed and stayed fixed.

**80% of every turn is tool schemas plus skill bodies** — the static surface, re-sent in full on every
pass, before the conversation contributes a word.

### Why this compounds with P2

P2 measured that **74% of tool calls are byte-identical repeats**, and each repeat is another
tool-loop pass. Each pass re-sends the static surface.

> The loop does not merely waste calls — **it re-pays the 80% on every iteration.**
> Loop × static surface. Two problems we had been treating separately **multiply**.

This is the complete explanation of *"local patching cannot save the repo"*: cutting the loop without
cutting the surface still pays 23k per pass; cutting the surface without cutting the loop still pays
it N times.

### Two surprises in the same data

**1 · Schema cost does not rise with tool-call count — it falls.**

| tool calls in the turn | messages | avg `mcp_tool_schemas` |
|---|---|---|
| 0 | 1,359 | **13,033** |
| 1–2 | 304 | 9,573 |
| 3–5 | 171 | 11,259 |
| 6+ | 195 | 6,377 |

Turns that call *nothing* carry the **largest** tool surface (rail and curated modes narrow it for the
turns that do work). **We pay ~13k tokens of tool schema on conversational turns that never call a
tool.** No requirement currently covers this; it is the cheapest large saving on the board.

**2 · `skills` is 32% of all context while `lazy_skill_bodies` defaults to True.**

That flag exists precisely to *not* inject skill bodies. 9,162 tokens per message says it is not
achieving its purpose — consistent with `AUDIT.md` §2.3, where the hot-seed and the prompt are
computed under opposite `lazy_bodies` assumptions. The audit found the *mechanism*; this is its
*price*.

### Consequences for the spec

1. **R14 is the budget fix, not only the scale fix** — it attacks 41% directly.
2. **A 32% slice has no requirement covering it.** Skill-body injection needs the same
   budgeted, explained treatment R4 gives tools.
3. **New rule: a turn that offers no tools must not pay for tool schemas.** Currently the reverse is
   true.

---

## P6 — A live capture: every finding in this spec, in one three-call trace

Driven through the real frontend, 2026-08-04, session `019fc893-096d-7193-abd8-7a0b23e81702`, plain
`/chat` (no book binding), Gemma-4 26B-A4B. One Vietnamese request: *"list my books, tell me which has
the most chapters, and summarise its first chapter."*

```
1. tool_list(category="book")   ok   -> 35 bare names, alphabetical, no descriptions
2. tool_list(category="book")   ok   -> (repeat; empty)
3. book_list_chapters           FAIL -> "book_id must be a UUID"
   … ends `interrupted` after 5 calls
```

### ⚠️ CORRECTION (2026-08-04) — "no descriptions" was my measurement error

The claim below that `tool_list` returned **bare names** is **wrong**. It was an artifact of the SQL
used to inspect the payload, which `string_agg`'d only the `name` field. The real payload per entry is:

```json
{"name": "book_audio_generate", "tier": "W", "deprecated": true,
 "description": "Propose generating chapter audio narration (priced) … DEPRECATED: spending money on
                 narration is a MANUAL UI action — the agent does not bill."}
```

**Measured properly: 3,393 tokens · 35 tools · 19 flagged `deprecated: true` (54%).**

And it is worse for the theory, not better. `book_list_chapters` — the tool the model chose — arrived
carrying `deprecated: true` **and** the sentence *"DEPRECATED: use `book_list` with kind=chapters — the
one 'ls' tool, paged + self-terminating."* Meanwhile `book_list` was present, unflagged, its
description opening *"List REFERENCES only (the 'ls') … `kind` selects what: books (default; the
caller's library)"* — the exact answer, requiring no arguments at all.

**The model was told the tool was retired, told what to use instead, and used the retired one anyway.**

So the corrected diagnosis of this capture is **not** "guidance was missing" but:

1. **`include_deprecated` defaults to `true`, and the cost is now measured.** ~1,840 of the 3,393
   tokens (54%) describe tools the model must not use. The payload is **46% signal**. This is
   `audits-01` §5.1's defect with a price tag.
2. **Labeling is not filtering — and OQ5's premise is falsified on this evidence.** The 2026-07-09
   decision was that a deprecated tool should be *labeled, not hidden* (reversing CAT-4). Here the
   label was present, correct, actionable, and **ignored**. A `deprecated: true` field and a
   "use X instead" sentence did not prevent selection.
3. **This capture is a SELECTION failure, not an id-provenance failure.** `book_list` needs no
   identifier. The earlier attribution of this trace to R17/G3 was over-reach on my part; G3 stands on
   P8's evidence (a different dataset, different tools), not on this one.

**What this trace actually argues for:** R14.1 (a hard result bound — 35 entries in one 3.4k-token
dump is not a listing), fixing the `include_deprecated` default, and reconsidering OQ5 — because the
first live test of "label, don't hide" failed.

### What `tool_list` handed the model (original text, superseded on the "no descriptions" point)

35 entries, alphabetically ordered. Checked against the live catalog:

- **19 of the 35 are `visibility:"legacy"` — 54% of the payload is retired tools.**
- **Not one of the 19 declares `superseded_by`.** Even a model that recognised them as retired could
  not find the replacement.
- The correct tool, `book_list`, sits at **position 18**. The tool the model chose,
  `book_list_chapters`, sits at **position 19 — adjacent** — and is itself one of the retired 19.

The model was asked to *list books*, was handed an alphabetical wall in which *list books* and *list
chapters* are neighbours, and took the wrong neighbour.

### The causal link the PO supplied: the chat surface cannot resolve a book id at all

Verified in code:

- `_ALWAYS_HOT_ON_BOOK_BOUND_SURFACE` is applied only `if book_scoped or editor or studio`
  (`tool_discovery.py:413-414`), so a plain `/chat` turn hot-seeds **no `book` domain whatsoever**.
- `context_ids["book_id"]` is read from `session_row["book_id"]` (`stream_service.py:5143`), which is
  **NULL** off the studio. So `_inject_context_ids` — the deterministic repair built precisely for
  "the model cannot transcribe a UUID" — **has nothing to inject on this surface.**

**This is a surface-capability gap, not a tool bug.** On `/chat` the model must both *discover* the
book tools and *resolve* an id with no server assistance, and discovery answers with 54% retired names
and no descriptions.

### Every requirement, visible at once

| observed | finding it confirms |
|---|---|
| 35 names, no descriptions, alphabetical | R14.1 bounded results · R14.2 hierarchy — the flat dump is unusable at 35, let alone at scale |
| 19/35 retired, 0 with `superseded_by` | R9 — `legacy` is a runtime filter with no policy and no clock. And `include_deprecated` defaulted **true**, the live confirmation of `AUDIT.md`/audits-01 §5.1 |
| picked the retired neighbour of the right tool | P1 — naming carries no semantics, so adjacency decides |
| `tool_list` called twice, second empty | P2 — the discovery tool is the top loop source |
| *"book_id must be a UUID"* with no path to one | R10.2 — an error that names the constraint but not the remedy |
| `/chat` has no book binding and no book hot-seed | **new: a surface may advertise an intent it cannot fulfil** |
| ends `interrupted` after 5 calls | R11 — the turn never terminates on its own |

### The requirement this adds

**R15 — a surface must be able to complete what it advertises.** If a surface exposes a domain's
tools (or the prompt invites requests about that domain), it must also expose the path to the
identifiers those tools require — either a hot-seeded resolver tool or a server-side binding. Today
`/chat` has neither for `book`, and the failure is silent: nothing reports that the surface cannot
satisfy the request it accepted.

This is the same shape as R4's `excluded_by`, one level up: **not "why can't I see this tool" but "why
can't this surface do this at all"** — and it should be answerable by the same mechanism.

### The model was not being stupid — it reasoned correctly and we refused to answer

The PO asked why the model does not stop and reason about the missing parameter: is it a weak model, or
does the response never tell it why the call failed? The raw payload settles it:

```json
{"tool": "book_list_chapters", "args": {"book_id": "all"},
 "error": "book_id must be a UUID", "result": null, "iteration": 2}
```

It passed **`book_id: "all"`** — not a hallucinated UUID, but an attempt to express *"all my books"*
from a surface that offered no way to enumerate them.

**And it learned `"all"` from us.** `tool_list`'s own closed set is
`CATEGORY_ENUM = sorted(GROUP_DIRECTORY) + ["all"]`, so call #1 taught the model that `"all"` is this
platform's sentinel for *everything*. It then generalised that convention to a domain tool. **The
model correctly applied a convention we taught it one call earlier** — inconsistent conventions across
meta-tools and domain tools are a defect that produces confident wrong calls.

The reply it received states the type constraint and nothing else: not what a valid `book_id` looks
like, not where to obtain one, not that `book_list` exists, not that there is no `"all"` mode.
`result: null`.

> **There is no "stop and reason" because the response contains nothing to reason from.** The model is
> not stuck for want of capability; it is stuck because every iteration returns the same zero bits.

One sentence would have ended the turn: *"book_id must be a UUID. There is no 'all' mode — call
`book_list` to get your books and their ids, then call this per book."* That is R10.2 stated as a
concrete, measured requirement rather than a style preference, and it is why R10 — while **not** the
loop fix (P2) — still matters: an unactionable error guarantees the next iteration is uninformed.

**Requirement refinement — R10.2a:** a `retryable_modified` error must name the **remedy**, not only
the violated constraint, and where the remedy is another tool it must name that tool. An error that
cannot change the model's next action is indistinguishable from silence.

### R16 — one deterministic loop detector, in the stream, that TERMINATES

The PO's reading of the same trace, and the evidence supports it exactly: **the anti-loop machinery
died here.** The turn ended `finish_reason: interrupted` after 5 calls — **not `stop`**. Nothing
concluded the turn; it was cut off. The breakers fired (`tool_list` repeat), emitted prose, were
ignored, and the run was killed from outside rather than terminated from inside.

That is rot, and it has a precise shape:

1. **Not centralised.** There are **14 function-local counters** inside a 7,818-line function
   (`stream_service.py:1863-1957`) — `blank_tool_args_streak`, `read_call_results`,
   `noop_write_counts`, `fail_by_tool_error`, `failure_suppress`, `listed_categories`,
   `rail_nudge_counts`, `reasoning_loop_interventions`, and more. Each was added for one incident.
   None can see the others. All reset on a confirm suspend/resume (audits-03).
2. **No deterministic duplicate detection over the stream.** Detection is per-mechanism and
   *ad hoc*: identical-args hashing here, error-signature keying there, a category counter elsewhere.
   Nothing computes *"this turn is repeating itself"* as one fact over the whole assembled context.
3. **It argues instead of withholding** (P2), so its output re-enters the context it is trying to
   break out of — the contamination mechanism, self-inflicted.
4. **It does not terminate.** A loop detector whose success condition is *"someone kills the run"*
   has no success condition. `interrupted` is the tell.

**The requirement:** exactly one loop detector, deterministic, computed over the streaming turn state,
with a defined terminal outcome:

- **one owner** — the detector is a single component, not a counter in a closure; every existing
  breaker either becomes an input to it or is deleted (P2's Q10);
- **deterministic** — a content-addressed signature over emitted calls *and* assembled context, so
  "we have been here before" is a computed fact, not a heuristic per subsystem;
- **survives suspend/resume** — it is turn state, not stack state, so a confirm gate does not reset it
  (today all 14 counters do);
- **withholds, not argues** — its action is `excluded_by` (R4/R5), never a tool result;
- **terminates** — on detection the turn ends with an honest `finish_reason` and a user-visible
  reason, never `interrupted`. *A loop breaker that cannot end the turn is not a breaker.*

This is the deterministic core the 14 heuristics were each approximating, and it is what R11's retry
budget attaches to.

---

## P7 — R17: guidance becomes a GATE, and 60% of the catalog fails it today

The PO's conclusion from the live capture, and it is the right one: *guidance must be forced into a
gate rather than left to authorship — after the refactor, an MCP tool without effective guidance must
be blocked.*

The **mechanism already exists**: `MustValidateToolMeta` panics at registration on a missing `tier`,
Python's `require_meta` raises, and `tier-tag-gate.py` runs in CI. What is missing is the **predicate**.

### The predicate, and it must be mechanical

| id | rule | rationale |
|---|---|---|
| **G1** | a description of substance | trivially checkable |
| **G2** | `visibility: legacy` ⇒ `superseded_by` is **mandatory** | a retired tool that cannot name its replacement is a trap, and `tool_list` shows it |
| **G3** | **every REQUIRED id-shaped argument must name the tool that produces it** — unless it is `ambient_*` (server-resolved) | this single rule would have prevented today's loop |
| G4 | closed-set arg ⇒ `enum` | existing `CLOSED_SET_ARGS` discipline |
| G5 | belongs to exactly one group **and** is named by a skill | R3's coverage gates — someone must teach it |

### Measured against the live catalog (315 tools)

| rule | failures | share |
|---|---|---|
| **G3 — required id arg names no producer** | **189** | **60%** |
| G2 — legacy without `superseded_by` | 63 | 20% |
| G1 — description missing/too short | 1 | 0% |

**Descriptions are not the problem. Argument provenance is.** Only one tool in the whole catalog has a
thin description, while **60% demand an identifier and never say where to obtain one**. That is
precisely the gap the live capture walked into: `book_list_chapters.book_id` says the value must be a
UUID and nothing about `book_list`, so the model invented `"all"`.

Sample failures: `book_audio_generate.book_id`, `book_chapter_bulk_create.book_id`,
`book_chapter_create.book_id`.

### How it ships without dying on day one

The lesson from R6 applies exactly: a gate that reds on 60% of the catalog gets switched off. So:

- **New or modified tools: HARD FAIL at registration.** No new violation can enter — the pattern
  `context-budget-defaults-lint.py` already uses with its FLIP-PENDING allow-list.
- **Existing 189: a ratchet** with a recorded baseline that may only shrink, each waiver carrying a
  reason.
- **G3 is the priority**, because it is the measured cause of the observed failure and because the
  remedy is one sentence per argument.

### Why this is the right level to intervene

Everything else in this document treats a symptom: the loop detector ends a bad turn (R16), the error
contract makes a failure informative (R10), the surface gate stops advertising the unachievable (R15).
**R17 stops the unusable tool from existing.** It is the only requirement here that operates *before*
the model is ever involved — which is also why it is the cheapest.

And it reframes the PO's original complaint precisely. *"Adding an MCP tool is a nightmare"* has a
converse that the data now supports: **adding one is currently too easy.** A tool can ship with no
group, no skill, no producer for its own required arguments, and no replacement when retired — and
nothing stops it. R13 makes changing a tool safe; **R17 makes creating one honest.**

---

## P8 — 🔴 THE ROOT CAUSE: 57% of real tool failures are the model unable to name a thing

Continuing the dig, two questions: which tools never succeed, and why.

### Twelve tools ship with a 0% success rate

Across all real usage, excluding breaker noise, counting only tools with ≥8 genuine attempts:

| tool | successes / real attempts |
|---|---|
| **`glossary_propose_entity_edit`** | **0 / 101** |
| `composition_list_outline` | 0 / 33 |
| `composition_conformance_run` | 0 / 28 |
| `translation_coverage` | 0 / 22 |
| `settings_provider_inventory` | 0 / 22 |
| `composition_get_mine_job` | 0 / 21 |
| `jobs_get` | 0 / 19 |
| `book_chapter_delete` | 0 / 19 |
| `kg_propose_edge` | 0 / 17 |
| `translation_job_status` | 0 / 13 |
| `kg_build_graph` | 0 / 13 |
| `composition_authoring_run_start` | 0 / 10 |

Near-zero alongside them: `glossary_list_chapter_links` **1/264**, `composition_arc_suggest` 2/46,
`glossary_get_entity` **14/197 (7%)**.

**The liveness matrix reports 211/224 passing and the ship gate reports "0 tools blocked."** It
measures whether a tool *can* execute under a synthetic probe, never whether it *ever* succeeds in
real use. Twelve tools at 0% is the falsification.

### They all fail the same way

| tool | dominant failure |
|---|---|
| `glossary_propose_entity_edit` | 66× `entity_id must be a real UUID, got 'place…'` · 24× `book_id … got 'current…'` |
| `translation_coverage` | 22× `book_id: Field required (you sent a dict)` |
| `jobs_get` | 19× `service` + `job_id` Field required |
| `settings_provider_inventory` | 22× missing `provider_credential_id` |
| `glossary_list_chapter_links` | 201× `entity_id must be a UUID` |

**Every one is an identifier the model could not obtain.** Measured over all 1,688 real tool errors:

> **960 of 1,688 — 57% — are identifier-resolution failures.**

### The vocabulary the model invents for "the thing we are discussing"

| count | value it sent |
|---|---|
| 60 | `placeholder_id_1` |
| 18 | `current_book_id_placeholder` |
| 6 | `current_book_id` |
| 5 | `placeholder_id` |
| 2 | `0` |
| 1 | `placeholder` |

Plus `"all"` from the live capture. **The model is writing, into a UUID field, that it knows it needs
the current book id and does not have it.** That is not a hallucination; it is a request for a
capability the surface does not offer, expressed in the only channel available to it.

Worst-affected arguments: `entity_id` (431), `book_id` (182), `job_id` (32),
`provider_credential_id` (22).

### The whole loop, end to end, with a number at every step

| # | step | measure |
|---|---|---|
| 1 | tools require an id and never say where to get it | **60%** of the catalog (G3) |
| 2 | → identifier-resolution failures | **57%** of all real tool errors |
| 3 | → the model invents a placeholder | `placeholder_id_1`, `current_book_id_placeholder`, `"all"` |
| 4 | → which fails deterministically, every time | **12 tools at 0%**, one at 0/101 |
| 5 | → so it retries | **74%** of all calls are byte-identical repeats |
| 6 | → breakers fire and *argue* instead of withholding | **58%** of "errors" are our own messages |
| 7 | → the turn never terminates | `finish_reason: interrupted` |

**This is one defect with six symptoms, and R17/G3 sits at the head of it.** Every other requirement
in this document treats a step further down the chain.

It also settles the PO's question about model strength definitively: a model that writes
`current_book_id_placeholder` has understood the task, identified exactly what it lacks, and named it.
**No increase in model capability fixes a missing capability in the surface.**

---

## 3 · What P1 and P2 settle, and what they do not

| DESIGN question | settled by | answer |
|---|---|---|
| Q15 who decides a tool's path | P1 | declared at registration; parsing is impossible |
| Q3 group granularity | P1 (partly) | `composition` at 107 must split; the *shape* still needs Q14 |
| Q10 which breakers R10 deletes | P2 | the ones that argue: `tool_list` cap, `book_get` repeat, blank-args, `find_tools` no-intent |
| R10 scope | P2 | valid for 42% of errors; not the loop fix |

**Still open and still needing evidence:** Q14 (tool identity — P3, retrospective over git history),
Q16/Q18 (retrieval backend and budget numbers — need measurement), and R14's flat-cost claim (P4, the
synthetic 3,000-tool catalog).

---

## 4 · Reproduce

```bash
# P1 — live catalog
curl -s -X POST http://localhost:8218/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "X-Internal-Token: $INTERNAL_SERVICE_TOKEN" -H 'X-User-Id: <uid>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# P2 — tool-call history
docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -tAc "
  select json_agg(row_to_json(x)) from (
    select session_id::text sid, created_at, tc->>'tool' tool, (tc->>'ok')::boolean ok,
           left(coalesce(tc->>'error',''),200) err, md5(coalesce(tc->>'args','')) argsig
    from chat_messages, jsonb_array_elements(tool_calls) tc
    where tool_calls is not null and jsonb_array_length(tool_calls) > 0) x;"
```

Both are read-only. P2 reads the dogfood history of the shared dev database; no cleanup is performed
and none is needed.
