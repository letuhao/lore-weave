# WS-3 — mode → capability binding (C6) + the pinned rail · gemma-4-26b-a4b-qat

**Date:** 2026-07-11 · **Plan:** [`docs/plans/2026-07-11-ws3-mode-capability-binding.md`](../../plans/2026-07-11-ws3-mode-capability-binding.md)
**Drives:** the S06 **assent gap** ([S06 re-test](2026-07-11-S06-flagship-retest.md)).
**Runs:** [`runs/2026-07-11-S06-ws3-pin3/`](runs/2026-07-11-S06-ws3-pin3/) (final) · `…-ws3-pin2/` (pre-fix) · `…-ws3-pinned/` (void — stale image, see below).

## Headline: the assent gap is CLOSED. S06 goes 1/5 → 2/5 and stops leaking. It still does not ship.

The mechanism WS-3 was built for **works, and the effect is directly observable in the transcript**:

| turn 7 — the user says only *"yeah do it"* | |
|---|---|
| **baseline** (advertised workflow + steering directive) | `find_tools(intent="plan_propose_spec")` → improvised the planner. Never touched the rail. |
| **WS-3 pinned** | `glossary_adopt_standards(...)` — **runs the rail**, no discovery call at all. |

That was the whole thesis: a mid-tier model will not *recognise* that a workflow applies when the user
merely assents to the agent's own offer. **Pinning removes the recognition step** — the rail is in context
from turn 1, so there is nothing to recognise.

## Ground truth (the flagship's own test: open the book and look)

Fresh, provably-empty book each run (0 kinds / 0 entities / 0 chapters), same model, same 17 turns.

| The flagship promises | baseline | **WS-3 pinned** |
|---|---|---|
| world structure (categories) | **0** ❌ | **12 kinds** ✅ |
| the cast + key terms | 0 ❌ | 0 ❌ |
| how everyone connects | 0 ❌ | 0 ❌ |
| a readable arc plan | 1 plan_run ✅ | 1 plan_run ✅ |
| a drafted opening | 0 ❌ | 0 ❌ |
| **jargon said to the user** | PlanForge ×27, Spec ×24, glossary ×16 | **PlanForge ×4**, slug ×1 |
| discovery (`find_tools`) calls | 1 | **0** |

**1/5 → 2/5.** The world now actually gets built, the plan is retained, and the machinery mostly stops
leaking. Context cost of the pin is bounded and measured: **+3.0K tokens per pass** (rail 1246 + the 11
pre-activated step schemas 1740) — the 64K totals in the raw budget events are the tool-loop re-sending
context across `llm_call_count` passes, not the pin.

## What shipped

- **`mode_bindings`** (agent-registry) — the C6 record, 3-tier (System/user/book), scope-key CHECK +
  per-tier partial UNIQUEs. Effective = **union** of the tiers **minus `disable_workflows`**.
  - *Why the subtractive field* (a C6 extension): a pure union leaves a user unable to turn OFF a System
    pin — that would make it a global flag wearing a setting's clothes. A translator must be able to drop
    the co-writer rail. Per-tier `sources` are returned so the effective value **and its source tier** are
    both visible (Settings & Config: no silent hidden default).
- **Read** folded into the existing per-turn `/internal/workflows` call (`&mode=`) — one hop, one degrade
  path. Registry down ⇒ no workflows *and* no binding ⇒ exactly the pre-WS-3 behavior. The hardcoded
  `plan→plan_forge` **stays** as the degrade-safe fallback (the System `plan` binding now expresses the
  same rule as data; the union is idempotent).
- **Write** `GET/PUT /v1/agent-registry/mode-bindings/{mode}[?book_id=]` — user-authorable (book tier needs
  EDIT). System tier is never writable here. A pin naming a workflow the caller cannot see is **rejected at
  the write**, not silently no-op'd at turn time.
- **Consumption** — `inject_skills` (additive, surface-filtered) · `seed_tool_categories` (unioned into the
  hot domains under the *same* single budget ceiling) · **`inject_workflows` = PIN**: the rail is rendered
  by **`workflow_load_result()` itself** (one rail format — a pinned rail and a loaded rail cannot drift)
  and its step tools are pre-activated.
- **`budget_rail_tools()`** — a rail is budgeted in **declared step order**. The existing
  `budget_names_by_tokens` is read-first, which under pressure drops exactly the *write* steps that persist
  anything, leaving the agent a recipe naming tools it cannot see. Drops are logged, never silent.
- **the flagship `vision-to-book` rail** — the flagship spine (12 steps: categories → cast → connections → plan → draft),
  surfaces `{book, editor}`. Its `notes_md` owns the vocabulary.

## Three real bugs this run caught (all fixed)

1. **A stale image made the first run a lie.** `docker compose build` had failed on a transient PyPI SSL
   error; `up -d` then saw no new image and left the old container running. The "WS-3" run measured
   pre-WS-3 code. Caught by `plan_nudge` moving only +51 tok and `mcp_tool_schemas` being byte-identical —
   then confirmed by grepping the running container. **Always verify the code is IN the container.**
2. **The rail leaked its own name.** First real run: *"we can use the **vision-to-book** workflow"* — said
   to a novelist, ×6. The rail is the agent's **private** recipe; putting it in context put it in the
   user's face. Fixed in the rail header + the flagship rail's notes; locked by a test.
3. **A bare apostrophe broke the whole migration.** `Saying 'first I'll look…'` inside a Postgres `E'…'`
   literal terminated the string — the entire `schemaSQL` died at boot with a syntax error, while **every
   Go unit test stayed green** (nothing there touches a DB). This bug class has now bitten twice (a
   backtick killed the Go raw string in WS-5). Fixed, and **statically linted**
   (`migrate_lint_test.go`) so it cannot recur.
   - Same file: System workflow seeds now **`DO UPDATE`**, not `DO NOTHING` — a code-owned System row that
     can never be corrected by a deploy is the "migration never revisits its default" trap (which already
     bit this effort once, when a stale July-9 `glossary-bootstrap` row shadowed its rewrite).

## The NEW bottleneck (what stops S06 shipping)

**The agent starts the rail but does not continue it.** It adopts the categories at turn 7 and then, across
movements D and E (*"the people"*, *"how they connect"*), calls **nothing** — it converses. The cast
(`glossary_extract_entities_from_doc` → `propose_entities`), the connections, and the draft never run,
even though their tools are advertised and their steps are in context.

Two candidate causes, not yet separated:
- **No progress state.** The rail says "continue from the first step still outstanding", but the agent has
  no way to know what is done. (Observed directly in the pre-fix run: it re-read step 1 three times.)
  Telling it the *book's actual state* ("12 categories exist; cast: 0") would make that answerable from the
  SSOT rather than from memory.
- **One-tool-per-turn habit.** It treats each user message as a conversational turn and calls at most one
  tool, despite an explicit "chain the steps" instruction. This may need the rail to be **driven**
  (a step-runner that advances it) rather than *described*.

Residual: `PlanForge` ×4 / `NovelSystemSpec` ×3 still reach the user — those come from the **plan_forge
skill prose / tool descriptions**, not from the rail; a separate vocabulary owner needs the same treatment.

## Verification

- **agent-registry:** api + migrate suites green, incl. 6 new binding tests (tier union, **user vetoes a
  System pin**, book veto, dedup, empty-lists-never-null) + the migration lint.
- **chat-service:** full suite **1406** green (+19), covering: the rail renders steps in order with gates
  and async flags · the assent language is present · **the pinned tools are actually advertised** (in both
  curated and auto mode) · rail budgeting keeps step order · binding skills are additive + surface-filtered
  · no binding is byte-identical to before · **registry down ⇒ no binding, no crash**.
- **live:** S06 on a fresh empty book — the assent runs the rail; 12 kinds + 1 plan land; binding crosses
  the wire (`/internal/workflows?mode=write` → `inject_workflows:[vision-to-book]`).
