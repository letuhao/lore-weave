# RT7 — The refactor is not needed: four rivals, priced

**Mandate:** argue that the "1+4" re-architecture is unnecessary, or that a far cheaper option
captures most of the value. **Verdict up front:** the proposal's own POC contains the evidence that
kills its cost case. The measured root cause is a **~10-line bug plus an env var**, and the dataset
that motivates the expensive half of the design (coarse text-in capabilities, A2/A3/A4) is
**contaminated by an eval harness driving a model with a documented blank-args defect**.

---

## 0 · The finding that reprices everything: P8's evidence base is partly synthetic

`poc/P1-P2-findings.md:1074-1078` gives the query. It reads **every row** of
`loreweave_chat.chat_messages.tool_calls` with **no filter** — the doc says so plainly: *"P2 reads the
dogfood history of the shared dev database"* (`poc/P1-P2-findings.md:1079`). There is no exclusion of
eval-harness sessions.

`docs/eval/skill-authoring/2026-07-08-gemma-post-allfixes-rerun.md:139-160` reports a **37-session
harness run against the same model the POC used** (`gemma-4-26b-a4b-qat`), whose finding was:

> **"Every tool call across all 37 sessions had blank args."** … *"Every tool requiring so much as one
> argument (`book_id`, `service`, `project_id`, `chapter_id`…) failed validation every single time it
> was called, regardless of how many times the validation error was fed back."* … *"it is a general
> property of this model's tool-calling in this LM Studio setup, not scoped to any one tool or code
> path."* — lines 158-166

Now put its per-tool histogram (lines 144-156) next to P8's "twelve tools ship with a 0% success rate"
table (`poc/P1-P2-findings.md:483-498`):

| tool | 2026-07-08 harness run | P8 "0% success" table |
|---|---|---|
| `translation_coverage` | **22** calls, 0/22 non-blank args | **0 / 22** |
| `settings_provider_inventory` | **22**, 0/22 | **0 / 22** |
| `jobs_get` | **19**, 0/19 | **0 / 19** |
| `translation_job_status` | **13**, 0/13 | **0 / 13** |
| `composition_list_outline` | 19, 0/19 | 0 / 33 |
| `composition_get_work` / `composition_list_canon_rules` | 25 / 15, all blank | (adjacent rows) |

**Four exact count matches.** Four of the twelve "0% success" tools are wholly accounted for by one
2026-07-08 eval run whose stated failure mode was **blank `{}` args**, not *"an identifier the model
could not obtain."* P8 asserts the opposite — *"Every one is an identifier the model could not
obtain"* (`poc/P1-P2-findings.md:517`).

**Why this matters more than any individual rival.** A3 ("text-in capabilities eliminate
id-resolution by construction") is the load-bearing justification for dropping the atomic write tools
— 118 of 198 — and it rests on the 57% figure. If a material share of the 960 id-resolution errors
are a harness × a model that sent `{}` to `find_tools` **117 times out of 117**, then a text-in
capability does not remove the failure: a model that cannot fill `book_id` will equally emit an empty
`instruction` string, and `subagent_runtime.py` will then be given nothing to resolve. **The failure
does not disappear; it becomes unobservable** — which the design hypothesis itself names as A3's
worst case (`DESIGN-HYPOTHESIS.md:70-73`).

**Cheapest observation that settles it:** re-run the P2 query with
`where session_id not in (select session_id from <eval-harness runs>)`, or simply
`where created_at > '2026-07-22'` (after the last harness round). Publish the 54/74/58/57 figures
**for real user sessions only**. This is one SQL statement. Until it is run, no number in §1.0 of the
SPEC is admissible as a reason to rebuild.

---

## 1 · Rival 1 — the minimal fix (a) kill the silent drop, (b) R10, (c) R15

### (a) The silent drop is a bug, and its honest twin is 20 lines below it

`services/chat-service/app/services/tool_surface.py:125-162` — `budget_names_by_tokens` returns
**`kept` only**. It logs nothing, reports nothing, and has no `dropped` return value.

Twenty lines below, `budget_rail_tools` (`tool_surface.py:180-214`) does the identical job and
**returns `(kept, dropped)`**, with a docstring that states the exact rule the other function
violates:

> *"leaving the agent a rail naming tools it cannot see — a silent no-op of the worst kind (it looks
> like it should work). … whatever gets dropped is **REPORTED** so the caller can log it rather than
> pretend."* — `tool_surface.py:194-197`

**The repo already knows the rule and already implemented it once.** This is not an architectural
gap; it is one function that was not brought up to the standard of its neighbour.

**The lie is 18 lines from the truncation.** `stream_service.py:2819-2822` truncates the F18
auto-load through `budget_names_by_tokens(..., HOT_SEED_TOKEN_BUDGET)`; `stream_service.py:2835-2839`
then emits *"Its tools are now LOADED and callable: {…}. Call one of them now."* And the very next
block — `tool_load` at `stream_service.py:2925-2937` — **does the honest thing**: on truncation it
sets `payload["truncated"] = True` and a note *"Loaded N of M tools (token budget)."*

So the fix for (a) is: **copy the `truncated`/`note` treatment from `tool_load` (2929-2934) into the
F18 branch (2822), and give `budget_names_by_tokens` the `dropped` return `budget_rail_tools` already
has.** Roughly 10-15 lines in one file, one service, one language.

**And there is a zero-line version.** `tool_surface.py:50`:

```python
HOT_SEED_TOKEN_BUDGET = int(os.environ.get("LW_HOT_SEED_TOKEN_BUDGET", "2000"))
```

Arm C — **35 tools, 7,921 tokens — scored 3/3** (`SPEC.md:36-42`). The budget that produced arm E's
0/3 is **2000**, and it is **already an environment variable** whose comment offers 0 and 4000 as
supported settings (`tool_surface.py:41-49`). Setting `LW_HOT_SEED_TOKEN_BUDGET=8000` reproduces
arm C in production with a container restart. The design hypothesis's A1 — *"there is no budget — the
set is small and fixed"* (`DESIGN-HYPOTHESIS.md:29`) — is achievable today by **changing one number**.

**Judgment on how hard (a) is: trivial.** It is the cheapest item in the entire program and it is not
in Phase 0. `SPEC.md:908-916`'s six "lies" do not include it.

### (b) R10 — the spec itself scores it

`SPEC.md:686-690`, written by the spec after the POC:

> *"P2 measured that **58% of 'errors' are our own breaker messages** … so R10's error contract
> addresses **42% of error volume and is not the loop fix**."*

And R10's reach is capped by the model. `2026-07-08-gemma-post-allfixes-rerun.md:161-164`: validation
errors were fed back and the model **kept sending blank args regardless**. A better message cannot
help a caller that is not reading the message.

**Cost is not minimal.** `SPEC.md:948` — *"It touches ten services, so it is the widest phase."* A
genuinely minimal version exists: apply **R10.2a only to the four worst arguments** — `entity_id`
(431), `book_id` (182), `job_id` (32), `provider_credential_id` (22) = **667 of 960 id failures**
(`poc/P1-P2-findings.md:536`) — i.e. edit ~6 validators to name the producer tool. Days, not phases.

### (c) R15 — book_id outside the studio

The plumbing exists. `stream_service.py:5143` already falls back to `session_row["book_id"]`; the gap
is that `/chat` sessions have it NULL, and `tool_discovery.py:413-414` hot-seeds the `book`/`story`
domain **only** `if book_scoped or editor or studio`. So on `/chat` the model must both discover the
book tools and invent an id with zero server assistance (`poc/P1-P2-findings.md:311-318`).

`book_list` **takes no arguments** and was present in the failing capture (`poc/P1-P2-findings.md:267-274`).
Hot-seeding it on every surface is a one-line addition to `ALWAYS_ON_CORE_NAMES`
(`tool_discovery.py:282-318`, currently **four** entries) or to `_ALWAYS_HOT_ON_BOOK_BOUND_SURFACE`
(`tool_discovery.py:359`) with the surface gate relaxed.

### Fraction of measured failure each removes

| fix | effort | share of the 4,007 failures it plausibly removes | basis / honest caveat |
|---|---|---|---|
| **(a) drop + env** | **hours** | **unknown, plausibly 15-35%** | `tool_list` breaker alone is **1,180 of 2,318** breaker messages = **30% of all errors carrying text** (`poc:64`). The re-list loop is the model circling tools it cannot call — exactly what (a) fixes. **Unmeasurable today because the drop has no telemetry** — which is itself the argument for doing (a) first |
| **(b) R10 (full)** | weeks, 10 services | **≤42% of error *volume*, ~0-10% of *failures*** | the spec's own number (`SPEC.md:688`); ceiling set by a model that ignores fed-back validation errors (`gemma-rerun:161-164`) |
| **(b′) R10.2a on 4 args** | days | same reach at ~5% of the cost | 667/960 id failures concentrated in 4 argument names |
| **(c) R15 book_id** | hours | **~11% of real errors** (182/1,688), plus it unblocks the whole P6 capture | does **not** touch `entity_id` — **431 of 960 (45%)**, the dominant id class |
| **(a)+(b′)+(c)** | **~1 sprint, 1 service** | **plausibly 30-50%** | vs. 9 phases / 5 services / 3 languages / 21 requirements |

**What Rival 1 does NOT fix:** the `entity_id` class (45% of id failures); the C1 scale projection
(3,000 tools); the 13 uncomposed mechanisms; prompt-cache instability (A6); the fact that the
architecture has 16 producers and 18 filters. It buys **symptom relief with no structural payment**.

**Observation that would show Rival 1 is sufficient:** ship (a) + (c) behind a flag, re-run the P6
live capture and arms C/D/E, and measure the real-user (post-2026-07-22) failure rate. **If it drops
below ~25%, the architecture is not the problem and the rebuild is not justified.**

---

## 2 · Rival 2 — user curation only (shape 3). **It is already built. All of it.**

The SPEC calls shape 3 an option that *"needs a UI"* (`SPEC.md:145`). That is **false**, and the code
says so:

| piece | evidence |
|---|---|
| pin/unpin UI with a picker modal | `frontend/src/features/chat/components/AgentContextRack.tsx:170-179` (`+ add`), `:211-221` (`ToolSkillAddModal`) |
| per-tool removal chips, grouped by server | `AgentContextRack.tsx:129-135` (`RackServerGroups`), `:150-169` (legacy pins) |
| request wiring | `frontend/src/features/chat/hooks/runChatStream.ts:144` — `body.enabled_tools = args.enabledTools` |
| session persistence + resume | `useChatMessages.ts:135-142`, `:275`, `:525` |
| server-side curated mode | `tool_surface.py:466-489` (`is_curated`), `:217-239` (`resolve_session_tool_pins`) |
| escape hatch for retired tools | `SessionToolPins.pinned_legacy` (`tool_surface.py:173-177`), unioned unconditionally at `tool_surface.py:463` |
| curated-mode surface assembly | `tool_surface.py:300-388` |
| a live measurement surface for the user | `AgentContextRack.tsx:108-110` — tools / skills / **token count** |

**What is actually missing is three things, none of them a UI:**

1. **Curation is not the default.** An empty pin list means auto mode (`tool_surface.py:489`), i.e.
   shape 2. Nothing ships a *preset* the user can adopt in one click.
2. **Curated mode does not escape the silent drop.** The F18 auto-load truncates in curated sessions
   too (`stream_service.py:2819-2827` — the `if curated` branch runs *after* the budget), and the
   glossary auto-union is budgeted at `tool_surface.py:513-516`. Explicit pins do pass through
   unbudgeted (`tool_surface.py:509-510` returns them verbatim), so **Rival 2 partially fixes arm E
   for pinned names only** — but a session that pins a *skill* rather than tools rides the budget.
3. **It cannot fix ids.** `entity_id` (431) and `book_id` (182) failures are unaffected by which tools
   are on the wire.

**Cost:** near-zero code. Make a per-surface preset and one "use recommended set" button; delete or
raise the budget inside curated mode.
**Value:** high for a power user, **zero for the newcomer flows the dogfood evals target**
(`docs/eval/e2e-newcomer/`), because the SPEC's own objection stands — *"the user must know what they
will need"* (`SPEC.md:145`).
**Observation that would show it is sufficient:** a curated preset session completes the S01-S06
scenarios at a materially better rate than auto mode. That A/B is runnable **today, with no code
change at all** — it is the cheapest experiment in this document and it has never been run.

---

## 3 · Rival 3 — fixed per-surface sets, keeping the atomic tools

Today `surface_hot_domains` (`tool_discovery.py:362-415`) derives *domains* from whichever skills
would auto-inject, then `budget_names_by_tokens` cuts the union down to 2,000 tokens. The domains for
a book-scoped surface come from `skill_registry.py`'s `hot_domains` declarations — `glossary`,
`knowledge`, `plan`, `composition`+`book`, `translation` (lines 111, 177, 196, 237, 251, 266) — plus
`story` (`tool_discovery.py:359`). Against the measured catalog (`SPEC.md:120-127`: composition 107,
glossary 54, book 35, kg 31) that candidate pool is **200+ tools**, which is exactly why a budget was
introduced and exactly why it silently deletes things.

**Rival 3 replaces the derivation + budget with a literal, hand-authored per-surface tool list.**

**Is it enough? Yes, on the measured evidence.** Arm D — **16 tools** — was 3/3; arm C — **35** — was
3/3 (`SPEC.md:36-42`). The size that works is **15-35**, i.e. squarely reachable **without** coarse
capabilities. That is the proposal's own data undercutting its stated reason for dropping the atomic
tools: `SPEC.md:161` says shape 1 *"was assumed impractical because the fixed set would have to be
large"* — arms C and D say a 16-35 tool set is fine.

**The mechanism already exists twice**, hand-authored: `ALWAYS_HOT_WRITES` (`tool_surface.py:79-106`,
6 entries with per-entry rationale) and `DISCOVER_ONLY_HIGH_IMPACT` (`tool_discovery.py:426-428`).
Rival 3 is those two lists, generalised per surface, replacing `surface_hot_domains`.

**Cost:** ~50 lines + real curation work (choose 20 tools × 5 surfaces). One service.
**Fixes:** arm E by construction (no budget ⇒ no silent drop); A6 cache stability (a literal list is
cache-stable, which A6 says is worth **+65% uncached tokens**, `DESIGN-HYPOTHESIS.md:96`).
**Does NOT fix:** the id class — the atomic tools still demand `entity_id`/`book_id`; the long tail
becomes unreachable, which the SPEC correctly flags (`SPEC.md:143`) and which shape 4 exists to
answer; C1 at 3,000 tools.
**Observation that would show it is sufficient:** hand-pick 20 tools for the book surface, ship it as
the default, and re-run S01-S06 + the P6 capture. If the failure rate drops to arm-C/D levels, the
coarse-capability half of the proposal (A2/A3/A4 — the expensive, unmeasured half) is **unnecessary**.

---

## 4 · Rival 4 — do nothing structural; the model is the variable

**The POC dismisses this in one sentence** (`poc:555-557`): *"a model that writes
`current_book_id_placeholder` has understood the task … No increase in model capability fixes a
missing capability in the surface."* Three pieces of the repo's own evidence say that dismissal is
premature:

1. **The blank-args defect (§0).** `2026-07-08-gemma-post-allfixes-rerun.md:158-166` — every call in
   37 sessions had `{}` args, *"a general property of this model's tool-calling in this LM Studio
   setup."* That is not a surface gap under any reading. It is the model.
2. **The P6 live capture is a pure model failure, and the POC admits it.** Correction at
   `poc:262-288`: `book_list` was present, unflagged, described as the exact answer and needing **no
   arguments**; `book_list_chapters` arrived carrying `deprecated: true` **and** the sentence *"use
   `book_list` instead."* The model chose the retired neighbour anyway. The POC's own conclusion:
   *"The model was told the tool was retired, told what to use instead, and used the retired one
   anyway"* (`poc:277`), and *"This capture is a SELECTION failure"* (`poc:285`).
   **This is precisely the falsifier A1 asks for** — *"a task where the correct tool is present … and
   the model still picks wrong at a material rate"* (`DESIGN-HYPOTHESIS.md:50`). It is in the repo,
   in production data, and **A1 is not marked falsified**. A1's blast radius is stated as **total**.
3. **The one non-model A/B that exists points the same way.** `docs/eval/tool-catalog-comprehension-2026-07-06.md`
   — same weak model, **12/12 PASS** on argument construction (including a mixed create/update batch
   and correct scope selection) *when the tool set was small and correct*. The model can do this.

**Against Rival 4, honestly:** the repo's stance is local-LLM-first with cloud as fallback (recorded
constraint), so "buy a better model" is a **product** change, not just an engineering one. And a
frontier model does not remove the C1 scale problem, the 13 uncomposed mechanisms, or the 130k-token
catalog.

**The damning part is that Rival 4 has never been tested.** There is **no same-surface cross-model
A/B in this repo.** Rounds 3/4 used Qwen2.5 **7B** — *weaker*, and the report says outright *"not
directly comparable"* (`gemma-rerun:116-117`). `gpt-4o-mini` appears only in a **cost** measurement
(`docs/eval/co-writer-onboarding-dogfood-2026-07-21.md:18,34`), never in a tool-selection comparison.
The methodology doc concedes the gap: *"Single weak model (gemma-4-26b). Local-only per the $0 rule
(no paid gpt-4o) … revisit if a stronger model becomes the default"*
(`docs/eval/context-budget/OPTIMIZATION-EVAL-METHODOLOGY.md:202-206`).

**Cost of settling it: under $1 and one afternoon.** Re-run arms C/D/E and the P6 capture on
`gpt-4o-mini` — the dogfood run cost **$0.0008** for a full session (`co-writer-onboarding:18`).
**Observation that would show it is sufficient:** if a mid-tier cloud model scores 3/3 on **arm E** —
the 7-tool starved set — then the silent drop is survivable, A1 is false, and **the entire shape
argument collapses to a model-tier problem**, exactly as `DESIGN-HYPOTHESIS.md:51-52` concedes.
If it scores 0/3 on arm E too, A1 survives its hardest test and the proposal is meaningfully stronger.

**Either result is decisive. Neither has been purchased. It is the highest-information-per-dollar
experiment available and it is not in the plan.**

---

## 5 · Ranking — value / (risk × effort)

| rank | option | value | risk | effort | score | one-line case |
|---|---|---|---|---|---|---|
| **1** | **Rival 1(a) — un-silence the drop + raise `LW_HOT_SEED_TOKEN_BUDGET`** | high | ~0 | **hours** | **highest** | the honest twin already exists at `tool_surface.py:180-214`; arm C proves 7,921 tokens works |
| **2** | **Rival 4 — the cross-model A/B** (as an *experiment*, not a purchase) | decisive | ~0 | **<$1** | **highest** | settles A1, whose blast radius is *total*, before anything is built |
| **3** | **Rival 1(c) — R15 book_id** | moderate (11% of real errors) | low | hours | high | `stream_service.py:5143` already has the fallback; `/chat` just isn't bound |
| **4** | **Rival 3 — fixed per-surface sets** | high | low-med | ~1 sprint | high | arms C/D say 16-35 tools is enough; `ALWAYS_HOT_WRITES` is the pattern already |
| **5** | **Rival 2 — curation as default + preset** | moderate | low | days | med-high | shipped end-to-end; only the default and the budget-inside-curated need changing |
| **6** | **Rival 1(b′) — R10.2a on 4 argument names** | moderate | low | days | med | 667/960 id failures in 4 args |
| **7** | **SPEC Phases 0-1 only** | real (deletes the six lies, adds the eval net) | med | weeks | med | the spec's own fallback: *"if the effort stops after Phase 1 the repo is still measurably better off"* (`SPEC.md:998`) |
| **8** | **The full proposal (1+4, 21 reqs, 9 phases)** | potentially highest | **very high** | **months** | **lowest** | 5 services · 3 languages · 198 tools re-homed; A2/A3/A4 all 🔴 unmeasured; its own risk table admits *"the refactor is too large to land"* |

### Why the proposal ranks last on this metric

- **Its expensive half is unmeasured.** A2 (~20 fits) is 🔴, A4 (sub-agent correctness under free
  text) is 🔴, A3 (id failure eliminated) is 🔴 on the part that matters
  (`DESIGN-HYPOTHESIS.md:58, 70, 78`). Only the *cheap* half — A1, small sets work — is 🟢, and that
  half is delivered by **Rival 3 or by one env var**.
- **A10 is 🔴 and self-admittedly fatal.** *"all thirteen previous mechanisms were also 'verified'"*;
  telemetry covers **35%** of messages and a freshly driven turn wrote **none**
  (`DESIGN-HYPOTHESIS.md:134-139`). You cannot land a 9-phase rebuild on instrumentation that cannot
  tell a fallen tower from a standing one.
- **The A3 relocation risk is worse than the status quo.** The hypothesis says so:
  *"the failure becomes unobservable"* (`DESIGN-HYPOTHESIS.md:73`). Trading a 57% *visible* failure
  for an unknown *invisible* one is a downgrade, and §0 above shows the 57% may not survive
  de-contamination.
- **A9 (deprecate-all) has zero evidence and live counter-evidence** — the product has a dogfood book
  and the frontend-tools MCP migration is mid-flight on this very branch
  (`DESIGN-HYPOTHESIS.md:124-126`).

---

## 6 · The bet

**I would bet on: Rival 1(a) + Rival 4's experiment this week; Rival 3 next; and hold Phases 2-8.**

Not because the architecture is fine — it is not; 16 producers, 18 filters, 13 silent, is real debt.
But because **every measurement that currently justifies the rebuild is either a bug with a 10-line
fix, or a number computed over a dataset containing an eval harness driving a model that sent `{}` to
117 of 117 calls.** Fix the bug, clean the dataset, run the $1 model A/B — then decide. Three days of
work can retire or confirm assumptions whose blast radius the proposal itself labels *total*.

**The falsifier for this red-team finding:** re-run the P2 query filtered to real user sessions after
2026-07-22 and find the failure rate still above ~45% with the id class still near 57%. Then §0 is
wrong, the evidence base holds, and rivals 1-4 are genuinely insufficient. **That query has not been
run.**
