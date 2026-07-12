# /review-impl — WS-3 mode→capability binding (`142fbcbb9`)

**Date:** 2026-07-11 · **Method:** 33-agent adversarial Workflow — 6 reviewers (one per dimension:
tenancy/security · resolution correctness · chat consumption · context budget + seed · degrade/no-silent-no-op ·
migration + seeds), each finding then handed to an independent agent prompted to **refute** it.
**27 raised → 17 confirmed, 10 refuted.** No HIGH survived except one; no security escalation.

## Outcome: 17 findings, all fixed + verified. Two of them were the S06 rail-stall root cause I was about to go hunt by hand.

The review paid for itself twice over: it found **why the pinned rail starts but never finishes**, which I had
been about to investigate with more eval runs.

| # | Sev | Area | Finding | Fix |
|---|---|---|---|---|
| 1 | **HIGH** | chat | **A confirm-gate resume keeps the rail's TEXT but drops its TOOLS.** The rail lives in the system message (persisted in `working`), so it survives the suspend for free — but the resume re-derives the tool surface from scratch and has no `book_id` to re-fetch the binding with. The resumed turn therefore read an ordered recipe naming tools it could not call. **the flagship rail's first confirm gate is step 3 of 12**, so the flagship rail broke at its very first gate. | Carry `pinned_step_tools` on the `SuspendedRun` (new `chat_suspended_runs.pinned_step_tools` column, NULL = pre-WS-3) and re-advertise them on resume |
| 2 | MED | seeds | **the flagship rail's `capture-cast` step was mislabelled ASYNC.** `glossary_extract_entities_from_doc` matches the name heuristic (`extract_entities`), so the rail told the agent *"background job — do NOT begin a dependent step until it finishes"* about a **synchronous** tool. It stalls waiting for a job that never exists — **the cast is never saved.** | Author `async_job: false` on the step (the authored flag beats the heuristic) |
| 3 | MED | chat | The pin rendered **before** the tool catalog was fetched, so it lost the catalog's `_meta.async` signal — a pinned rail and a `workflow_load`ed rail could disagree about which steps start a job. The exact pin/load drift that reusing `workflow_load_result` was supposed to make impossible. | Hoist the catalog fetch above the pin, pass the async set in (also removes a duplicate HTTP call) |
| 4 | MED | tenancy | **`/internal/workflows` never grant-checked its `book_id`** — which is client-supplied (the FE's `book_context`). Any user could read any book's book-tier workflows (full steps + notes) and its book-tier binding by knowing the UUID, and steer their own tool surface with it. | `bookGrantOK(GrantView)` before either query; fail **soft** (drop to the user's own scope) so a grant-authority blip cannot brick every chat turn |
| 5 | MED | tenancy | **The book-tier pin was validated against the WRITER's private visibility.** Both directions were wrong: A could pin their own *private* user-tier workflow into a **shared** book (invisible to every other grantee, whose turns silently ran unpinned while `GET` still reported the pin as effective) — and the legitimate case, pinning the book's *own* workflow, was **rejected**, making that tier unpinnable. | Validate against whoever will **consume** the binding: book tier ⇒ System ∪ *that book's* rows (mirrors what `internalWorkflows` serves a grantee) |
| 6 | MED | seeds | The **System `mode_bindings` seed still used `DO NOTHING`** — I had fixed the workflow seeds and missed the binding right beside them. A shipped System binding could never be corrected. | `DO UPDATE` |
| 7 | MED | settings | `inject_skills` / `seed_tool_categories` were **stored unvalidated and silently no-op'd** — only `inject_workflows` was closed-set checked. A setting `GET` reports as effective that does nothing, ever (the write-only-behavior bug the Settings standard names outright). | Enum-validate both at the PUT (C1 category set + a visible-skill check); **log** at consumption if one still arrives (⇒ the two sides have drifted) |
| 8 | MED | budget | The pinned block had **no aggregate ceiling** — `notes_char_cap` bounds one rail's prose, but a binding may pin 32 workflows with unbounded titles/descriptions/steps. An always-on block with no ceiling. | `TOTAL_CHAR_CAP`, with the overflow logged |
| 9 | MED | tests | **The migration lint was tautologically green — it could not fail on its own bug class.** The scanner stops *at* the first bare quote (that is what "terminator" means), so the body it checks can never contain one. | Detect **mis-termination** (what follows the closing quote is prose, not SQL) + ship a **negative control** that fails on the exact bug that shipped |

## Two more bugs found by running the fixed code

- **A cap silently ate the rail's most important rules.** the flagship rail's `notes_md` was 3218 chars against my own
  3000-char `notes_char_cap`, so the tail was dropped — and the tail was the **SPEAK-PLAINLY block** ("never
  say workflow/glossary/spec…"), i.e. exactly the rules written to stop the jargon leak. **The leak survived
  its own fix, and the truncation said nothing.** A cap that silently eats the end of a prompt is worse than
  no cap: the block still *looks* complete. Fixed: cap raised, truncation now **warns**, and the registry
  lints that a seeded rail fits the consumer's ceiling (an author cannot see the consumer's cap).

- **A mid-tier model cannot transcribe a UUID.** gemma called `glossary_propose_entities` with the turn's
  real `book_id` **plus one extra character** (`…056e6`) → `400 book_id must be a UUID`, then repeated the
  identical corruption on a later turn. (Same failure mode as its mangling of a 519-char `confirm_token`.)
  Arg-injection only filled a *missing* id, deliberately — to respect a cross-book call. But a **malformed**
  value cannot be a deliberate cross-book call: a real id is a UUID. Now the server's known id wins when the
  supplied one is malformed; a **valid-but-different** UUID is still honored (negative control).
  General fix — it helps every weak model, not just this scenario.

## Live re-run (fresh empty book, all fixes in)

The fixes work, and one of them visibly drives self-correction: the agent proposed entities before any
category existed, got the **silent-success fix's** honest error — *"no entities were created — 4 of 4 failed.
Reasons: unknown kind: character… create the categories first"* — and **immediately called
`glossary_adopt_standards`**. That is a tool error message doing its whole job.

**But S06 still does not ship, and the run-to-run variance is now the story.** Across four runs of the
identical stack + model + scenario, ground truth was: **kinds 5 / 12 / 0 / 5 · entities 0 / 0 / 0 / 0 ·
plan 0 / 1 / 0 / 0**. The rail reliably gets *started* (the assent gap stays closed) and the world gets built
more often than not — but the cast **never** lands in any run, and which artifacts appear is close to a coin
flip.

## What this says about the next build

The remaining failure is no longer a *missing mechanism* — discovery is dead (0 `find_tools` calls), the
assent lands on the rail, the tools are advertised, the errors are honest and actionable. It is that **nothing
drives the rail forward**: the model is asked to hold a 12-step recipe across a 17-turn conversation while
also doing the emotional work of the scene, and it drops it. Each user turn is answered on its own terms.

That points at a **step-runner that advances the rail** (server-side: "you are at step N; step N-1 succeeded;
the next call is X") rather than a rail the model must *remember* to follow — plus book-state grounding so
"what is already done" is answerable from the SSOT instead of from memory. That is a real design, not a
prompt tweak, and it is the honest next milestone.

## Verification

- **chat-service:** full suite **1418** green (+31 over the WS-3 commit), incl. the resume-pin seam, the
  async-mislabel + its negative control, the total ceiling, loud truncation, and the UUID-correction pair
  (typo corrected / deliberate cross-book still honored).
- **agent-registry:** api + migrate green, incl. the rewritten lint's **negative control**.
- **live:** both migrations applied on a real stack (`chat_suspended_runs.pinned_step_tools`,
  vision-to-book `async_job:false`); S06 re-run end-to-end on a fresh, provably-empty book.
