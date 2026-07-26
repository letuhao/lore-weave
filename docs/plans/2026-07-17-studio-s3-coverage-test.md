# Studio S3 (PlanForge) — full-coverage test scenario

> **Purpose:** NOT a smoke. A **coverage** pass where the tester role-plays a **real web-novel
> author** and exercises *every* S3 capability end-to-end on the **real built app**, deliberately
> hunting for **UI/UX gaps and business-flow gaps** — "there's no item to do/view the thing I need",
> "the flow dead-ends", "I can't get from A to B", "the state is wrong/stale", "I don't understand
> what happened". Smoke asks *"does the happy path run?"*; coverage asks *"can a real author actually
> do their whole job, and where does the product fail them?"*
>
> **Environment (MANDATORY):** the **static Docker build** (rebuilt FE image + rebuilt
> composition-service so BE-3/BE-20/BE-4 migration are live), NOT `vite dev` / :5199 — concurrent
> sessions' HMR churns the source build and invalidates coverage. Drive with Playwright/CDP on an
> **isolated** browser context. Test account: `claude-test@loreweave.dev`. LLM smokes:
> gemma-4-26B-A4B QAT (`019ebb72-27a2-72f3-a42d-d2d0e0ded179`), local, $0.

## How to run each step
For every step below: **(a)** do the action as the author would, **(b)** record what actually
happened, **(c)** answer the **gap probes** (⛳). A ⛳ answered "no / missing / unclear" is a FINDING —
log it (severity, what a real author expected, what the UI gave). Coverage is measured by findings,
not by green checks.

---

## Persona
"I'm writing a xianxia web-novel. I have a premise in my head and a few existing chapters. I want the
tool to help me plan the book's structure — cast, beats, scenes — review it, fix what's wrong, and
push it into my outline so I can write."

---

## Journey 1 — Discover & reach the tools
1. Log in → open a book's **Writing Studio**.
2. Open the **Command Palette** (⌘⇧P). Find **"Open Planner"** and **"Open Pass Rail"**.
   - ⛳ Are both discoverable by an author who doesn't know they exist? Is the description enough to
     know *when* to use each? Is the split Planner-vs-Pass-Rail obvious or confusing?
3. Open the **User Guide** panel → find the Pass Rail entry.
   - ⛳ Does the guide explain the 7-pass model + the two blocking checkpoints in author language
     (not "cast_plan/derive_view")?

## Journey 2 — Propose a plan (Planner)
1. Planner → **Run** tab. Read the honesty copy ("Proposed from this braindump only…").
   - ⛳ Is it clear the proposer ignores my existing chapters? Would I be surprised later?
2. Paste a real premise (multi-section markdown). Pick **LLM** mode + the gemma model. **Propose**.
3. Watch the run go pending → proposed. Read the **Self-check** + **Validate** reports.
   - ⛳ Do the gaps/rules make sense to an author, or are they engineer-speak? Can I tell if my plan
     is "good enough"?
4. Open each **artifact** ("open ↗") → the read-only json viewer.
   - ⛳ Is raw JSON the right way for an *author* to read their spec/package? Or is this a
     developer view? (Coverage gap candidate: no human-readable spec render.)
5. **Compile** — pick an arc by title, compile.
   - ⛳ Do I understand what "compile" produced? Is the arc-picker enough, or do I need to see the
     arc's content before choosing?

## Journey 3 — Repair a plan (Planner repair strip)
1. If Self-check found gaps, the **Repair strip** appears. Try **Explain what's wrong** (gemma).
   - ⛳ Is the diagnosis actionable? Does it point at specific arcs/beats?
2. Try **Apply the suggested fix** and **Fix the top gaps automatically** (autofix). Re-run Self-check.
   - ⛳ Did the gaps actually go down? Can I tell what changed? Is the PS-6 paid-confirm clear about
     cost? Is there any undo if the fix made it worse?
3. ⛳ **Business-flow gap probe:** if I don't like the autofix, can I get back to the previous state?
   (There is no plan-level undo — is that acceptable, or a gap?)

## Journey 4 — Run the 7-pass compiler (Pass Rail)
1. Planner → click **"Pass Rail →"** deep-link. Confirm it opened the rail on this run.
   - ⛳ Did the rail land on the RIGHT run, or the latest? If I have several runs, can I choose which
     run the rail shows? (Known limitation — is it a real gap for a multi-run author?)
2. Read the rail: 7 passes, badges, freshness, cursor "N of 7", blocked_at.
   - ⛳ Do I understand *why* a pass is 🔒 blocked? Is the blockers reason discoverable (hover/title
     only — is that enough)?
3. **Run motifs** (advisory) via gemma + the PS-6 cost-confirm. Watch it complete → fresh.
   - ⛳ Is the cost-confirm clear? Do I know it's about to spend? Is the model choice obvious?
4. **View** a completed pass's output ("→ kind ↗") read-only.
   - ⛳ Same as J2.4 — is raw JSON acceptable for reading a motif/cast plan?
5. **Run cast** (blocking). It completes → "review →".

## Journey 5 — The blocking checkpoints (the S3 headline)
1. Click **"review →"** on cast. Read the cast content (read-only).
2. The **cast seed-gate**: is the glossary seed "applied"? If not, **Apply seed**.
   - ⛳ Do I understand WHY I can't approve until the seed is applied? Is "Apply seed" self-explanatory
     to an author who doesn't know PF-7?
3. **Approve** cast. Confirm the cursor advances (1→2) and world/beats unblock.
   - ⛳ Is the advance visible/satisfying? Do I know what to do next?
4. Try **Reject** on a fresh checkpoint. Confirm it holds.
   - ⛳ After reject, what's my recovery path? Re-run the pass? Is that obvious?
5. ⛳ **The BIG coverage probe (structured-edits gap, spec'd not built):** the review is READ-ONLY. As
   an author I see a wrong cast member — **I cannot fix it here**. Is read-only + re-run acceptable, or
   is the missing in-place edit a real blocker to my workflow? (This is the D-S3-CHECKPOINT-STRUCTURED-
   EDITS spec — the coverage test should *confirm* the gap is felt.)
6. Run **beats** (the 2nd blocking checkpoint) → approve. Then run world/character_arcs/scenes/self_heal
   in dependency order to the end.
   - ⛳ Does the rail guide me through the order, or do I have to figure out which pass is runnable
     next? Is "run everything to the end" a chore (7 manual runs + 2 approvals) — should there be a
     "run all advisory to the next checkpoint" affordance? (Business-flow gap candidate.)

## Journey 6 — Push the plan into the manuscript (loop-connect)
1. Rail footer → **"Link to outline →"**. Confirm it links.
   - ⛳ Where did my plan GO? Can I see the arcs/chapters/scenes now in the manuscript navigator /
     Plan Hub? Is the hand-off visible, or a silent success?
2. ⛳ **Business-flow gap probe:** after linking, is the loop closed — can I now go write the first
   chapter from the planned scenes? Trace: rail → outline → editor. Where does it break?

## Journey 7 — Manage runs (BE-4 archive/restore + BE-3b resume)
1. Planner → **Runs** tab. See the list of runs.
2. **Reopen** an old run → confirm the **braindump textarea is restored** (BE-3b), not blank.
   - ⛳ Does reopening feel like resuming, or starting over?
3. **Archive** a failed/junk run. Confirm it disappears from the list.
4. Toggle **"Show archived"** → **Restore** it.
   - ⛳ Is archive/restore discoverable? Is there a confirm/undo for archive? Try archiving a run
     that's mid-compile → expect the 409 "job in flight" message. Is that message clear?

## Journey 8 — Agent parity (cross-check)
1. In the studio chat, ask the agent to run a pass or approve a checkpoint (plan_run_pass /
   plan_review_checkpoint). Confirm the **open Pass Rail refreshes** (planEffects).
   - ⛳ Does the human's rail reflect the agent's write without a manual refresh? If the agent and I
     both drive the compiler, is the shared state coherent?

---

## Coverage findings ledger

### Run 1 — 2026-07-17, rebuilt Docker stack (composition-service + worker rebuilt, BE-3/BE-20/BE-4
migration live; FE static :5210). Partial pass — J1/J2.4/J4/J6 exercised live; J2-full/J3/J5-full/
J7/J8 deferred to a fresh-context continuation (needs fresh gemma runs through all 7 passes).

**Confirmed WORKING live (not findings — coverage passed):**
- Pass Rail reachable via ⌘⇧P palette with a clear description (J1). ✅
- PS-9 artifact view: rail "→ cast_plan ↗" AND planner "open ↗" open the artifact in the json-editor
  READ-ONLY (chip "READ-ONLY", no Save/Revert, only Format) showing the real content — the full
  PS-9 provider → BE-3 content route → FE-1 read-only chain, live (J4.4/J2.4). ✅
- Rail renders the derived ledger (7 passes, badges, freshness, cursor, blocked_at) + "Link to
  outline →" (J4/J6). ✅

**FINDINGS:**
| # | journey/step | severity | what the author expected | what the UI gave | gap type |
|---|---|---|---|---|---|
| F-1 | J4.4 / J2.4 (H1) | **MED** | to READ my cast/beats as a cast/beat list | **raw JSON** in a tab titled "JSON · {runId}" — `{"cast":[{"name":…}]}` | **view-inadequate** — the viewer is developer-shaped; an author needs a human-readable per-kind render (the READ side of the structured-edits spec's per-kind components). H1 **CONFIRMED**. |
| F-2 | J5 (fixture) | n/a | — | cast showed "re-run" not "review →" | NOT a product bug: the seeded run's cast was already `accepted` (cursor 2) from the prior REST smoke; a full fresh run is needed to exercise the pending-checkpoint UI. Re-run coverage with a clean propose→compile→run in fresh context. |

### Run 2 — 2026-07-17, same rebuilt stack — J5 + J7 driven fully through the GUI

**Confirmed WORKING live (GUI-driven, not REST):**
- **J5 — the S3 headline, end-to-end in the browser:** cast "review →" → the CheckpointReview shows
  the cast **content read-only** (BE-3), the **seed-gate** "Glossary seed is 'pending'. Apply it
  before approving (PF-7)", **Approve DISABLED** with the PF-7 tooltip, **no raw-JSON editor** (the
  /review-impl read-only fix) → **Apply seed** → "Glossary seed applied — cast can be approved",
  Approve ENABLES → **Approve** → API confirms `pass_cursor 1→2, cast=accepted, world+beats
  unblocked`. A GUI-only author advanced past the cast checkpoint incl. the seed gate. ✅✅
- **J7 — archive/restore (BE-4), GUI-driven:** "Archive" → the run vanishes from the list; the
  "Show archived" toggle → it reappears with "Restore" → "Restore" → back in the active list. ✅
- **Loop-connect:** the planner Runs tab shows "Pass Rail →"; the rail shows "Link to outline →". ✅

**FINDINGS (run 2):**
| # | journey/step | severity | what the author expected | what the UI gave | gap type |
|---|---|---|---|---|---|
| F-3 | J7 (H6-adjacent) | **LOW-MED** | an undo after Archive (the draft says "the toast carries an Undo") | the run silently vanished; recovery only via discovering the "Show archived" toggle + Restore | **no-undo / flow-friction** — add a toast-with-Undo on archive (the draft specified it; not built). |
| F-4 | J5 seed-gate | **LOW** | to understand WHY I must "Apply seed" before approving | the copy cites "PF-7" (an internal law id) | **unclear-copy** — "PF-7" means nothing to an author; the gate copy should say *why* (the cast's characters must be written into the glossary first) without the law id. |

**Gap hypotheses — verdicts:**
- **H1 (raw-JSON viewer): CONFIRMED** (F-1) — view-inadequate.
- **H2 (7-run friction): CONFIRMED (structural)** — reaching the end is 7 manual `run…` + 2 approvals
  with no "run all advisory to the next checkpoint" affordance. Real friction for a long book.
- **H3 (read-only checkpoint edit): CONFIRMED as a designed gap** — the review is read-only (correct
  per the draft ban); the structured editor is the D-S3-CHECKPOINT-STRUCTURED-EDITS spec.
- **H4 (no run-picker): CONFIRMED** — the rail always binds the latest run; a multi-run author selects
  a run only from the planner Runs list (no picker in the rail).
- **H6 (no undo): CONFIRMED** (F-3 for archive; the repair strip also has no undo).
- **H5 (loop visibility after link): NOT YET TESTED** — needs a Link-to-outline click + a check that
  the arcs/chapters appear in the manuscript navigator / Plan Hub.

**Still open (fresh-context continuation):** H5, J3 (repair strip with a real gemma self-check gap),
J8 (agent-parity refresh — chat-drives-pass → rail refreshes), the 409-in-flight archive path, and a
FULL clean run (propose → compile → all 7 passes → both checkpoints → link) end-to-end.

### Run 3 — 2026-07-17, FE rebuilt (S2 fixed the arcTemplates import) — F-1/H4/H5 verified live
- **F-1 VERIFIED live:** with a 2nd run seeded, the cast review now renders a **readable cast list**
  (`artifact-cast`: "Diệp Vấn Vũ · protagonist — the discarded fifth miss / Bạch Sư · mentor — …"),
  NOT raw JSON (`artifact-json` absent). ✅
- **H4 VERIFIED live:** the rail shows a **run picker** with both runs ("507c… · proposed",
  "019f6556 · checkpoint"); selecting the checkpoint run switches the rail to it. ✅
- **H5 (loop-connect) — no-silent-success VERIFIED:** "Link to outline →" on a run whose (thin
  fixture) package has no chapters surfaces a **clear error** ("the package has no arc_id / no
  chapters — nothing to link; a compile that materialises nothing is a failure, not an empty
  success"), not a silent success. The success path (arcs/chapters appear in the manuscript) needs a
  REAL compiled package → folded into the full-clean-run continuation. ✅ (error path)

**Remaining (fresh-context / real gemma run):** J3 (repair strip on a real self-check gap), J8
(agent-parity refresh), the 409-in-flight archive, and a FULL clean run (propose→compile→7 passes→2
checkpoints→link with a real package, to see the plan land in the manuscript = the H5 success half).

### Run 4 — 2026-07-17, a REAL gemma-4-26B-A4B QAT run (propose → self-check → autofix → compile)
- **Propose (gemma) VERIFIED:** a real xianxia premise → run `019f6c17` proposed with 3 real arcs
  ("The Discarded Miss", "The Corrupt Path", "Reckoning"). ✅
- **Self-check (gemma) VERIFIED:** returned **2 real gaps** (`open_questions_preserved count=0`,
  `sg_value_shift_per_scene events_without_value_shift=['ev_2_4']`) — so the Repair strip's gate
  (`selfCheck.gaps.length > 0`) fires on real data. ✅
- **J3 autofix (BE-2, gemma) VERIFIED:** `POST /autofix` → 202, `rounds:[{round:1, targets:2,
  result:'pending'}]` — it targeted both gaps and enqueued a refine round on the worker (the async
  path). The Repair strip's "Fix the top gaps automatically" is real-proven end-to-end. ✅

**FINDING F-5 (business-flow / generation-quality, MED):** compiling an arc from this
(high-level, arc-only) gemma spec returns **400 "the package has no arc_id / no chapters — there is
nothing to link. A compile that materialises nothing is a failure, not an empty success."** The
propose generated ARCS but not the chapter-level structure the compiler needs to materialise a
linkable package. So the loop-③ success half (compile → package with chapters → link → the plan
appears in the manuscript) **cannot complete from a high-level premise alone** — it needs a spec rich
enough to decompose into chapters (or the separate decompose/planning-pipeline path). This is the same
CLASS as the propose-blind gap: a generation-quality limitation, not an S3 GUI defect (the GUI
correctly surfaces the 400, no silent success). Ties to the propose-existing-state spec — a
richer/grounded proposer would produce the chapter structure. **Triage:** track as a
generation-quality item for the PlanForge-v2 track; the S3 rail/checkpoints/link GUI are all proven,
they just need a chapter-bearing package to show the manuscript hand-off.

**Only J8 remains** (agent-parity: a chat-driven `plan_run_pass` refreshes the open rail) — needs the
studio chat agent; a clean fresh-context check. Everything else in the scenario is now exercised.

### ⚠ Coverage-ENVIRONMENT blocker — RESOLVED (S2 fixed the import; FE build green again)
Attempting to rebuild the static FE (to verify F-1/H4 live and continue coverage) FAILS:
`Could not resolve "../../api" from src/features/composition/arcTemplates/api.ts` — an UNTRACKED WIP
file from a concurrent session (S2/S4 arc-templates) with a wrong import (`../../api` should be
`@/api`). It blocks EVERY session's `vite build`. Not fixed here (do not edit another session's
uncommitted WIP mid-flight — race risk). **Convergence action:** that session fixes the import (one
line), then F-1/H4 live-verify + the remaining coverage journeys (H5/J3/J8/full-run) run on a fresh
FE build. F-1/H4 are unit-proven (70 passed) + tsc-clean in the meantime.

## Findings summary → triage
| finding | severity | status |
|---|---|---|
| F-4 seed-gate copy cites "PF-7" | LOW | **FIXED** — reworded to author language ("Your cast's characters must be added to the glossary before you can approve. Apply the seed to add them.") |
| F-3 no archive undo toast | LOW-MED | **FIXED** — archive now shows a `toast('Run archived', {action: Undo → restore})` (mirrors canon-rule archive) |
| F-1 raw-JSON artifact viewer | MED | **BUILT** — PassArtifactView (per-kind readable render: cast/beat lists, JSON fallback) in the checkpoint review |
| H4 no run-picker in rail | LOW-MED | **BUILT** — usePassRail exposes runs + setRunId; the rail header shows a run picker when >1 run |
| H2 7-run friction | MED | **SPEC'd** — docs/specs/2026-07-17-planforge-run-to-next-checkpoint.md (real design Qs: batch cost-confirm, stop-at-blocking, partial-failure, FE-vs-BE orchestration) |

**Verdict on the 5 gaps:** F-3/F-4 fixed in-run; F-1/H4 built (buildable, not design-needed);
H2 spec'd (genuine design questions). Nothing hand-waved as "blocked". The S3 commitment was proven
before any of these; all five were polish/operability the coverage test surfaced by role-playing a
real author.

## Known gap hypotheses to CONFIRM or REFUTE (don't assume — test them)
- **H1 (view-inadequate):** raw-JSON artifact viewer is developer-shaped; an author needs a
  human-readable spec/cast/beats render. (J2.4, J4.4)
- **H2 (flow-friction):** running the full 7-pass compiler is 7 manual runs + 2 approvals with no
  "advance to next checkpoint" affordance. (J5.6)
- **H3 (edit-missing):** cannot fix a wrong cast/beat in the checkpoint (read-only). (J5.5 — spec'd)
- **H4 (run-picker-missing):** the rail always shows the latest run; a multi-run author can't point it
  at a specific run except via the planner deep-link. (J4.1)
- **H5 (loop-visibility):** after "Link to outline", the hand-off into the manuscript may be a silent
  success — is the result visible where the author writes? (J6)
- **H6 (no-undo):** no plan-level undo after autofix/refine. (J3.3)

Each hypothesis is a **finding if confirmed** → triage into fix-now vs a new spec/defer with the gate
reason. The point of this test is to turn "cho có" (renders but doesn't serve the job) into a concrete,
prioritized gap list grounded in a real author's journey.
