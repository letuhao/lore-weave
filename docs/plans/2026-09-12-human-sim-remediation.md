# Implementation Plan: Writing Studio remediation — the human-sim findings

Branch: `feature/human-sim-remediation` (based on `release/v0.1.0`)
Created: 2026-09-12

## Original Request

ok help me make new plan to improve them

## Settings
- Testing: yes
- Logging: verbose
- Docs: yes  # mandatory documentation checkpoint at completion

## Source

This plan remediates [`2026-09-06-human-sim-van-tuong-quy-nhat-REPORT.md`](2026-09-06-human-sim-van-tuong-quy-nhat-REPORT.md)
(26 findings, go/no-go) and its run log [`2026-09-06-human-sim-van-tuong-quy-nhat.md`](2026-09-06-human-sim-van-tuong-quy-nhat.md).
The report's verdict was: conditional GO for the outline/structure system and the Workflow-style
review pattern; **NO-GO for the in-manuscript AI-authoring pitch as currently wired.**

## The release bar (PO decision, 2026-09-12)

> *"we will release that we commit to use — a version that can really usable like readme marketing"*

So the acceptance bar for this work is **not** "the 21 tasks are ticked." It is: **every claim the
[`README.md`](../../README.md) makes is either true of the shipped build, or removed from the
README.** A feature that exists but cannot be reached does not satisfy a claim — the human-sim run
is the proof, since it failed to find working capability that was present the whole time (see C1).

All six phases run straight through (PO decision), and the run ends with a claims reconciliation
(T22), not with a task count.

### Claims audit — README vs. what the run measured

| README claim | Where | Evidence from the run | Status |
|---|---|---|---|
| *"A co-writer that can't contradict your canon"* · *"Advisory prose critic flags potential canon contradictions before you accept a suggestion"* | §How LoreWeave is different, §AI Co-Writing | Finding #17 — the co-writer re-derived a **diverging** version of already-committed canon *in the same turn it was told that canon*. No critic fired at any point in a 5-arc run. | **FALSIFIED** |
| *"Motif and arc libraries with conformance checking against what you actually wrote"* | §The Writing Studio | C2 — conformance structurally cannot see what you actually wrote; it requires a completed per-scene `generation_job`. | **FALSIFIED** |
| *"Lore-grounded prose suggestions anchored to your published canon"* | §AI Co-Writing | Scene Inspector reported *"Grounding thin / unavailable · 670 tokens"* and *"No knowledge graph yet."* | **NOT DELIVERED by default** |
| *"Automatic entity and relationship extraction from chapters"* | §Worldbuilding & Lore | Required a manual "Build knowledge graph" run; the studio otherwise said *"No knowledge graph yet."* The word doing the overclaiming is **automatic**. | **OVERCLAIMED** |
| *"Rich text editor with AI-assist mode and Classic mode"* | §Writing & Editing | The AI/Classic toggle is cosmetic — `InlineAiLayer.tsx:42-46` writes `localStorage` and fires an event; **nothing in the Continue path reads `mode`**. | **OVERCLAIMED** |
| *"PlanForge — plan a novel's structure from your premise"* | §The Writing Studio | Finding #11 — compile never completed across three attempts and two Tier-A approvals; zero arcs produced. | **NOT DELIVERED** |
| *"Auto-Draft Factory — run a whole drafting campaign across chapters"* | §AI Co-Writing | **The engine is real, production-grade, tested, and has a verified live run** — but it does not draft. Its only stages are `knowledge`, `translation`, `eval` (`campaign-service/app/migrate.py:19`); the driver's entire dispatch surface is `dispatch_extraction` + `dispatch_job` (`app/saga/driver.py:129-216`); campaign-service's book-service client is **GET-only** (`app/clients/book_client.py`). Output lands in `chapter_translations.translated_body` (`translation-service/app/workers/chapter_worker.py:464-477`), and the product's own completion CTA points at `/books/:id/translation`. Its wizard placeholder reads *"e.g. Translate Book 1 → Vietnamese."* | **MISNAMED + OVERCLAIMED** — a translation batch engine wearing a drafting name |
| *"Steering rules … injected into every book-scoped AI turn"* | §The Writing Studio | Finding #10 — silently truncated to ~3 of 8 rules. Fixed this run (#223); still has no UI indicator when it truncates. | **DELIVERED, with a gap** (Task 12) |
| *"A workspace that holds your whole novel at once"* (dockable, pop-out, `⌘P`) | §How LoreWeave is different | Worked throughout the run. The strongest part of the product. | **DELIVERED** |

Two of these are flatly false today and four more are reachable-but-undisclosed or misnamed. That
is the gap between the README and the build, and closing it — in either direction — is what "really
usable like readme marketing" means.

### The README is not uniformly overclaiming — the tension is internal

Worth stating precisely, because it changes the fix. The README's **Roadmap table already marks the
relevant phases honestly**:

| Phase 3 | Intelligence Layer — canon co-writing, lore enrichment, translation quality | 🔄 In Progress |
| Phase 4 | Continuation & Canon Safety — the Writing Studio, PlanForge, canon rules, Auto-Draft Factory | 🔄 In Progress |

But **§Features** and **§How LoreWeave is different** state those same capabilities as unqualified
present-tense fact — *"a co-writer that **can't** contradict your canon"*, *"conformance checking
against what you actually wrote"*, *"advisory prose critic **flags**…"*. A reader who reaches the
roadmap has been told twice already that these ship today.

So the reconciliation is not "rewrite the README to be pessimistic." It is: **make the prose match
the roadmap the same document already publishes**, and make true the handful of claims that are
cheap to make true. That is a far smaller and more honest change than it first appears.

**The Auto-Draft Factory finding stands on its own as two defects, neither of which is "it's
broken":** (a) the name and the README line describe drafting, the engine does extraction +
translation — a naming/claim defect; (b) the single link lives in a Sidebar the Writing Studio does
not render (`App.tsx:124` puts Studio outside `EditorLayout`; a grep for `campaign` across
`features/studio/**` returns zero hits), so a user inside the Studio cannot reach it at all.
Task 23 covers both. **It does NOT refute the NO-GO** — the tester was right that no path writes AI
prose into the manuscript.

## Size

`./scripts/workflow-gate.sh size XL 35 11 4 12` → **XL** (files=35, logic=11, side_effects=4).
No phases may be skipped. The gate's own budget guidance applies: **commit at RISK boundaries
(contract, migration, cross-service seam), not at file-count thresholds** — the Commit Plan below
is structured that way rather than "every 3-5 tasks."

---

## ⚠ Three findings in the delivered report are WRONG — read before planning any task

Codebase reconnaissance contradicted the report on three points. Each correction makes the fix
**cheaper and more specific**, and each one changes what the corresponding task must do. The
report is a delivered artifact that informed a go/no-go, so correcting it is Task 1, not a footnote.

### C1 — "No in-Editor AI-write path exists" is false. Three paths exist; all three are gated, and none of the gates is visible.

The report's F-A claimed the capability was absent. It is present, three times over:

1. **`book_chapter_save_draft`** — a real Tier-A MCP tool that writes prose directly into
   `chapter_drafts.body`, which is *the Manuscript editor's canonical document*
   (`services/book-service/internal/api/mcp_tools_write.go:778-877`; registered at
   `mcp_server.go:342-355`). It is advertised in the co-writer skills
   (`services/chat-service/app/services/book_skill.py:102`,
   `composition_skill.py:57`) and present in `tool_surface.py:103`.
   **But it is deliberately LAZY on the editor/studio surface** — reachable only through a
   `find_tools`/`tool_load` round-trip. The design note states this outright
   (`services/chat-service/app/services/tool_discovery.py:341-347`): *"The editor's extra
   capability (prose write-back) is the `propose_edit` FRONTEND tool … NOT a backend domain — so
   composition / book tools stay lazy there too."*
2. **`propose_edit`** — the frontend tool that IS the intended editor write-back
   (`services/ai-gateway/src/mcp/propose-edit-tool.ts:27`). Tier R, client-applied, and it
   requires the editor open with a live cursor/selection (`insert_at_cursor` / `replace_selection`).
3. **"✦ Continue from cursor"** — a real handler, not a stub
   (`frontend/src/features/composition/components/InlineAiLayer.tsx:79-87`).

So the run's observed *"I have no direct access to the Manuscript editor"* was very likely **true
from the model's own context**: `book_*` was not hot, and `propose_edit` needs a live selection.
Meanwhile Continue was disabled by `canContinue`
(`frontend/src/features/composition/hooks/useInlineGhost.ts:40`):

```ts
const canContinue = !!editor && !!opts.projectId && !!opts.sceneId && !!opts.modelRef;
```

`modelRef` resolves only from a persisted `settings.default_model_ref` on the Work **or** from the
user having *exactly one* active chat model (`EditorPanel.tsx:272-275`). With several models
registered and no persisted default it is null forever. The reason is in a `title` tooltip on a
`disabled` button (`InlineAiLayer.tsx:48-52`) — the one place a user cannot hover-discover it.

**Consequence for the plan:** this is a *reachability and disclosure* defect, not a missing
feature. Phase 1 un-gates and discloses; it does not build a new write path.

### C2 — Conformance's "Realized" never consults `written_*`.

The report's F-B attributed "Realized: Not written yet" to the null `written_scene_id`. It is
actually a **completely separate** signal. `services/composition-service/app/routers/conformance.py:288-291`:

```python
realized: dict[str, Any] = {
    "job_id":    latest["job_id"] if latest else None,
    "has_prose": bool(latest["has_text"]) if latest else False,
}
```

`latest` comes from `latest_completed_by_nodes` (`conformance.py:191-229`), which requires a
**completed `generation_job`** for that scene whose `result.text` is non-empty.

So there are **two** dead signals, not one, and the human path produces neither:

| Signal | Only populated by | Read by |
|---|---|---|
| `written_scene_id` / `written_at` (`app/db/models.py:266-268`) | book-service parse/import writes `scenes.source_scene_id` → `chapter.scenes_linked` event → `written_verdict.py:56-73` reconcile | Plan Hub "written" badge (`routers/outline.py:335`) |
| `realized.has_prose` | a completed per-scene `generation_job` with non-empty `result.text` | Conformance panel |

Neither is reachable from "chat draft → human pastes → save draft."

**Consequence for the plan:** a fix needs a **third, manuscript-derived** signal. The ingredients
already exist — `BookClient.get_draft` (used at `routers/plan.py:391`), `tiptap_doc_to_text`
(`app/engine/prose_doc.py:125+`), and server-side heading→scene matching `_attach_scene_ids`
(`app/engine/prose_doc.py:58-78`). Only the per-scene segmentation helper is missing.

### C3 — `no_tracked_promises` is conflated with LLM failure, so it is a correctness bug, not a copy problem.

The report filed this as a LOW-MEDIUM "unhelpful error message." In fact
`extract_tracked_promises` returns `[]` on **any** extract failure, including the truncated /
unusable-content path (`app/engine/promise_audit.py:290-310`, `:276-287`). Downstream that becomes
`error="no_tracked_promises"` (`app/engine/quality_report.py:255-262`). So one code means either
*"the spec genuinely declares no promises"* or *"the extraction call failed"* — indistinguishable
to every caller.

That is the same silent-failure-reported-as-a-clean-empty-result shape as the Phase-3 audit bundle,
and it belongs with them in severity.

**Also corrected:** the error string already reaches the browser. The UI throws it away —
`frontend/src/features/composition/components/BookPromiseCoverageSection.tsx:50-54` branches on
`c.error` and renders a fixed string. The UI half is a few lines.

### One more thing recon found that the run never saw

**The scene decompiler computes the back-link mappings and NO caller ever writes them back.**

Both `materialize-scenes` routes — the Hub CTA (`app/routers/outline.py:1004-1025`) and the
internal import tail (`:975-1001`) — are behaviourally identical: each calls `materialize_scenes(...)`
and returns `result.to_dict()`, which includes `mappings[]`. The write-back was designed to be the
**caller's** job, and `app/engine/scene_decompile.py:284` says so in as many words:

> `# so a retry after a failed write-back returns the SAME mappings.`

But grep finds **no consumer of `mappings` anywhere** outside the engine and its tests. The frontend
caller (`frontend/src/features/plan-hub/hooks/useExtractPlan.ts`) reads only `work_resolved` and
discards `res.mappings` entirely. So the idempotent-retry design exists for a write-back that was
never built on either path.

Since `scenes.source_scene_id` is the sole trigger for the whole `written_*` chain, adding that
write-back is the missing human-driven path — small change, disproportionate payoff (Task 7).
**Note this is a caller-side gap, not a route-side one** — do not "fix" the routes.

---

## Standards that govern this work

Cite these at the enforcement site and in the proving test — do not restate them in new prose.

| Area | Standard |
|---|---|
| The new/changed MCP surface | [MCP Tool I/O](../standards/mcp-tool-io.md) — **IN-4** bounds-in-schema, **IN-6** self-correcting errors, **IN-8** 4-source drift, **OUT-4** success/error discrimination, **OUT-5** never silently truncate |
| Agent → GUI writes | [09 Agent GUI Reconciliation](../specs/2026-07-01-writing-studio/09_agent_gui_reconciliation.md) — locked G1-G6, the **G7 DIRTY-HOIST GUARD** (open design hole), Lane B/C |
| Studio panels | [Dockable Panel Standard](../standards/dockable-gui.md) — DOCK-1..11 |
| Every test in this plan | [Non-Vacuity](../standards/non-vacuity.md) — **NV-6**: break the guarded thing, watch it go red, restore it, paste the output. *"I added a test" is not evidence.* |
| Any language-dependent path | [Multilingual](../standards/multilingual.md) — relevant to Task 6's hardcoded `language: 'en'` |
| Any new toggle/threshold | [Settings & Configuration Boundary](../standards/settings-and-config.md) — SET-1..8 |

**Logging (applies to EVERY task below).** Verbose was selected. At each changed decision point log
inputs, the branch taken, and the reason — `[Service.method] message {data}`, DEBUG for flow, INFO
for a state change a user could observe, WARN/ERROR for a degraded or failed path. The recurring
defect class in this whole plan is *a path that fails or no-ops without saying so*, so **every
`return` that silently does nothing gets a log line naming which precondition was unmet.**

---

## Commit Plan — checkpoints at RISK boundaries

- **C1** (T1) — `docs: correct three factual errors in the human-sim report`. Docs only, no risk.
- **C2** (T4) — `fix(studio): close the G7 dirty-hoist guard`. **Data-loss boundary.** Must land BEFORE the agent write path is made prominent by C3.
- **C3** (T2, T3, T5, T6) — `feat(studio): make the existing AI-write paths reachable and their gates visible`. Cross-service seam (chat-service tool surface + frontend).
- **C4** (T7, T8) — `feat(composition): recognise human-authored prose as realized`. Contract change (conformance response) + a new write-back.
- **C5** (T9, T10) — `fix(composition): un-conflate no_tracked_promises from extraction failure`. Contract + UI.
- **C6** (T11, T12, T13) — `fix: close the silent-write/exploding-read class`. Schema/contract boundary across services.
- **C7** (T14, T15) — `fix(planforge): bounded compile recovery and an honest turn end`.
- **C8** (T16, T17) — `feat(composition): prose length floor and a critic pass`.
- **C9** (T18-T21) — `fix(studio): title precedence, cache invalidation, and discoverability`.
- **C10** (T23) — `fix(campaigns): name the factory for what it does, reach it from the Studio`.
- **C11** (T22) — `docs(readme): reconcile the claims with the build`. **The release gate.** Runs last because it grades everything before it.

---

## Tasks

### Phase 0 — Correct the delivered report

- [x] **T1** — Correct C1/C2/C3 in the report and the FEEDBACK LOG.
  The report informed a go/no-go; leaving three wrong mechanisms in it means the next reader plans
  against fiction. Rewrite report §2 F-A (the write path exists but is lazy/gated — cite
  `tool_discovery.py:341-347` and `useInlineGhost.ts:40`), F-B (two separate dead signals, neither
  is the `written_*` mechanism claimed — cite `conformance.py:288-291`), and F-L (promise coverage
  is a conflated silent failure, not a copy problem — cite `promise_audit.py:290-310`).
  Add the "Extract the plan discards its mappings" discovery. Update FEEDBACK LOG #19, #24, #26 in
  the run log to match, and add a short "corrected 2026-09-12 by codebase recon" note under each
  rather than silently editing — the correction trail is the point.
  **Do NOT restate the verdict as unchanged:** re-derive it. The NO-GO rested on F-A/F-B; with the
  corrected mechanism the verdict likely becomes *"the capability ships but is unreachable and
  undisclosed,"* which is a different and far more fixable claim.
  Files: `docs/plans/2026-09-06-human-sim-van-tuong-quy-nhat-REPORT.md`,
  `docs/plans/2026-09-06-human-sim-van-tuong-quy-nhat.md`.
  Logging: n/a (docs only).

  **EVIDENCE (T1).** Report §2 rewritten: **F-A** now states the three gated paths with citations
  (the original "the app's own AI cannot write directly into the manuscript" is preserved in a
  CORRECTED block, not silently deleted); **F-B** now carries the two-dead-signals table and the
  decompiler write-back discovery; **F-L** split — the chapter-picker half kept, the promise-coverage
  half promoted to a new **F-M** as a correctness bug. New **§5 re-derives the verdict**: NO-GO
  stands, but as reachability-and-disclosure, and §4's "the controls do not work at all" is called
  out as wrong. Run-log FEEDBACK LOG #19/#24/#26 each carry a dated CORRECTED note.

  BITE — a citation checker over all 10 code references the corrected text makes. It **caught two
  of my own citations being wrong on its first run** (`promise_audit.py:310` and
  `quality_report.py:258` held different code; the real lines are 308 and 262, both inside the
  ranges the prose cites, so no prose change was needed). Then deliberately broken and restored:

  ```
  # RED (conformance citation moved 290 -> 291)
    X  services/composition-service/app/routers/conformance.py:291: expected '"has_prose"'
          got: '}'
  exit=1
  # RESTORED byte-exact (diff clean)
  T1: all 10 code citations verified against the working tree.
  exit=0
  ```

### Phase 1 — Make the existing write paths reachable (the release-gate work)

- [x] **T4** — Close the G7 DIRTY-HOIST GUARD. (Own commit; data-loss boundary.)
  Spec 09 flags this as an open design hole to close *before* Lane B build: an agent MCP-save that
  triggers `manuscript.reload(chapterId)` while the user is typing in that chapter **clobbers their
  unsaved keystrokes**. S7 covers only tab-close dirty; the 409 FSM covers only the user's own save.
  This must land before Task 3 makes agent writes more likely, or the plan ships a data-loss bug in
  the course of fixing a usability one.
  Rule from the spec: a reconciler handler that reloads a hoist MUST check `hoist.dirty` first; if
  dirty, surface a conflict (reload-or-keep, same family as the save-conflict FSM) or no-op with a
  toast — never a blind reload. The reconciler owns the *signal*; the hoist owns the *dirty decision*.
  Files: `frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx` (415-418 and the
  reload path), plus the effect-reconciler seam — confirm at BUILD whether
  `StudioEffectReconciler`/`effectRegistry` exists yet or whether this guard lands in the reload
  entry point itself.
  Logging: WARN whenever a reload is refused because the hoist was dirty, with chapter id and the
  dirty-since timestamp. This is the line that proves the guard fired in the wild.
  Tests: dirty hoist + incoming reload ⇒ no content loss. NV-6: remove the dirty check, watch the
  test go red with an actual lost keystroke, restore, paste output.

  **EVIDENCE (T4) — the plan's premise was half wrong; rule 6 caught it.** The guard is **already
  built**: `ManuscriptUnitApi.isChapterDirty` exists (`ManuscriptUnitProvider.tsx:85`), `reload`
  documents the caller's obligation (`:407-410`), and `bookEffects.ts:49` honoured it with
  `if (ctx.isChapterDirty?.(chapterId)) return;`, covered by tests. So no keystroke was ever at
  risk, and the spec's "design hole" had been closed.

  **What was actually missing is G7's second half.** Spec 09 allows the dirty branch to be
  *"no-op **+ toast** 'agent changed this chapter — reload?'"* — the no-op shipped, the toast did
  not. So an agent write onto the chapter the user was editing vanished **silently**: the agent
  believed it wrote, the editor kept showing older content, and nothing said the two had diverged.
  That is this plan's own recurring defect class, and T3 is about to make agent writes far more
  frequent. Implemented a debounced `toast.warning` naming what happened, with a
  "Discard mine & reload" action wired to `reloadChapter` — the keystrokes still win, but the user
  is told and given the choice.

  BITE — reverted the branch to the bare `return` it shipped as:

  ```
  # RED (guard reverted to the silent no-op)
    × G7: TELLS the user when a dirty hoist blocked the reload, and offers the reload as their choice
      → expected "spy" to be called once, but got 0 times
    × G7 notice is debounced — one agent turn firing the handler repeatedly is one warning, not three
      → expected "spy" to be called once, but got 0 times
   Tests  2 failed | 16 passed (18)
  # RESTORED byte-exact (diff clean)
   Tests  18 passed (18)
  ```

  The other 16 stayed green under the bite, so the new tests are pinning the new behaviour and not
  duplicating existing coverage. A third test asserts the notice does **not** fire on the clean path
  (NV-7 — a warning that always fires means nothing). Regression: `tsc --noEmit` clean, eslint clean
  on both files, and the whole studio suite **163 files / 1515 tests passed**.

  Note for T3: `Date.now()` drives the debounce, so the test pins the clock — left real, the first
  test's toast would have suppressed the second's, and the suite would have gone green for the wrong
  reason.
- [ ] **T2** — Make "Continue from cursor" state its own reason, and give `modelRef` a resolution path.
  Today a user with 0 or ≥2 chat models and no persisted `settings.default_model_ref` sees a
  permanently disabled button whose explanation lives only in a `title` tooltip on a disabled
  element. Render the `disabledHint` as visible text (or an inline affordance that opens the
  co-writer model setting), and make the unmet precondition specific — "no default model" and "no
  scene selected" are different problems with different fixes.
  Per SET-1..8 a default-model choice is a **user setting**, not a silent fallback: do not invent an
  implicit "just pick the first model" behavior; make choosing it one click from here.
  Files: `frontend/src/features/composition/components/InlineAiLayer.tsx` (48-52, 79-87),
  `frontend/src/features/composition/hooks/useInlineGhost.ts:40`,
  `frontend/src/features/studio/panels/EditorPanel.tsx` (267-280, 562-574).
  Logging: DEBUG each precondition of `canContinue` with its resolved value, so a support question
  is answerable from one log line instead of four.
  Tests: a render test per unmet precondition asserting the specific reason is *visible* (not in
  `title`). NV-6: delete the reason text, watch each go red, restore, paste output.

- [ ] **T3** — Hot-seed the `book` domain on the studio surface. (PO decision, 2026-09-12.)
  **Decided: option (a), hot-seed.** The alternative — keep it lazy and signpost the `find_tools`
  hop in the skill — was rejected because the measured failure was the model *asserting it had no
  access to the manuscript editor* rather than searching for a tool. Instructing a model to search
  does not fix a model that has concluded it cannot. Hot-seeding puts `book_chapter_save_draft` in
  context every turn, so the claim "I have no access" becomes impossible rather than merely
  discouraged.
  **The cost is real and must be paid deliberately:** a hot-seeded domain is ~24K tokens against
  ~300-500 for the group-directory pointer (see `docs/eval/context-budget/`). Measure what the
  studio surface's seeded set costs before and after, and confirm what `budget_names_by_tokens`
  truncates to make room — if it silently evicts something the studio skill depends on, that is a
  new instance of this plan's own recurring defect class and must be surfaced, not absorbed.
  Honor `HOT_SEED_TOKEN_BUDGET`. `surface_hot_domains`
  (`tool_discovery.py:369+`) derives hot domains from injected skills' `SkillDef.hot_domains`, so
  the change belongs in the skill declaration, not a hand-authored constant — that hand-authored
  shape already caused one miss ("plan_forge shipped, 'plan' wasn't added to any of them").
  Files: `services/chat-service/app/services/tool_discovery.py` (328-400),
  `services/chat-service/app/services/composition_skill.py:57`,
  `services/chat-service/app/services/book_skill.py` (65, 102-118).
  Logging: INFO the resolved hot-domain set + total seeded token cost per surface at turn start —
  the context-explosion investigation had to be reconstructed for want of exactly this line.
  Tests: extend `tests/test_tool_surface.py`; assert the budget ceiling still holds. NV-6 applies —
  a budget assertion that cannot exceed its ceiling is the NV-2 "subject cannot vary" shape, so
  prove it by feeding an oversized candidate set.

  **🛑 BLOCKED — D3's premise is FALSE. Row stays OPEN, not ticked. PO decision needed.**

  `book` is **already hot on the studio surface**, and `book_chapter_save_draft` is **additionally
  allowlisted so the token budget cannot starve it**. There is no work in this row as written.
  Executed, not read (the comment this plan cited turned out to be stale):

  ```
  $ python -c "from app.services.tool_discovery import surface_hot_domains; ..."
  studio       -> ['book', 'composition', 'glossary', 'knowledge', 'story']
  editor       -> ['book', 'glossary', 'knowledge', 'story']
  book-scoped  -> ['book', 'glossary', 'knowledge', 'story']
  universal    -> ['knowledge']
  ```

  Why: `resolve_skills_to_inject` appends `"book"` on the studio branch and the `book` SkillDef
  declares `hot_domains={"book"}` — both added by **F14 (round-4 dogfood, 2026-07-20)** for exactly
  this reason (*"A book workbench must offer its own book tools by default"*). Separately,
  `tool_surface.py:78` puts `book_chapter_save_draft` in `ALWAYS_HOT_WRITES`, and `:546` adds that
  set to `kept` **outside** the budget loop, so it cannot be truncated out.

  **The comment this plan quoted (`tool_discovery.py:341-347`, *"composition / book tools stay lazy
  there too"*) describes the pre-F14 world and was never updated.** It is now the third stale or
  wrong premise this run has caught, and the second one I propagated into the corrected report —
  F-A's point 1 needs amending again.

  **What this does to the finding.** The tool was on the wire, unconditionally, and the model still
  said it had no access to the manuscript editor. So for this path the defect is **not** discovery.
  The codebase already documents the real failure mode in measured live runs:
  `stream_service.py:1274` (*"`book_chapter_save_draft` WITHOUT its `body`, and the turn ended —
  chapter created, 0 words"*), `:7745` (*"`book_chapter_save_draft` with `book_id == chapter_id`
  (38 / 6). Zero successes"*), `:4542`. That is a **model-capability / prompting** problem on an
  advertised tool, not a gating one — materially harder than un-gating, and it puts D1's
  "recoverable in about a day" reading of F-A in doubt for this path specifically.

  Note T2 still stands on its own merits and is done: "Continue from cursor" really was gated by an
  unresolvable `modelRef` with the reason hidden in a `title`.


- [x] **T5** — Make the "✦ Suggest scenes" toolbar button reach the affordance it advertises.
  It is a signpost that only fires a toast — by design (`EditorPanel.tsx:356-368`, 452-462). The
  real generator lives in the selection bubble menu (`SelectionToolbar.tsx:273-281`), which appears
  only on a non-empty selection under `SCENE_PLAN_MAX_CHARS`. A button that looks like the feature
  and is actually a pointer to it is a discoverability defect regardless of intent.
  Either act on the current selection directly, or make the toast an actionable affordance rather
  than prose instructions. Do not leave a third state where it looks enabled and does nothing.
  Files: `frontend/src/features/studio/panels/EditorPanel.tsx` (356-368, 452-462),
  `frontend/src/features/composition/components/SelectionToolbar.tsx` (175-180, 273-281).
  Logging: DEBUG which branch was taken and why (no selection / too long / dispatched).
  Tests: assert the no-selection branch produces a reachable path, not a dead toast.

  **EVIDENCE (T5).** The no-selection branch was already fair guidance and is kept. The defect was
  the other one: a user who HAD selected a passage was toasted *"Use Suggest scenes in the AI
  toolbar above the selected passage"* — sent to a second button for the thing they had just asked
  for. It now dispatches on the **existing** `lw-editor-context-ai` bridge the right-click menu
  already uses (`TiptapEditor.tsx:419`), so the generator, its stream and its proposal state stay
  owned by `SelectionToolbar` — no duplicated pipeline. `scene_plan` was added to that bridge's
  allowlist, which had deliberately carried only rewrite/expand/describe.

  BITE — reverted `BRIDGED_OPS` to exclude `scene_plan`:

  ```
  # RED
    × T5: the lw-editor-context-ai bridge runs scene_plan (the toolbar button path)
   Tests  1 failed | 8 passed (9)
  # RESTORED byte-exact (diff clean)
   Tests  9 passed (9)
  ```

  The companion test (*"the bridge still ignores an operation outside the allowlist"*) stayed green
  through the bite — NV-7: a bridge that forwarded anything would forward junk too.

- [x] **T6** — Replace the ✨ narration-attach silent no-ops, raw `alert()`, and hardcoded language.
  Three separate silent `return`s and one raw `alert()`
  (`frontend/src/components/editor/AudioAttachActionsExtension.ts`): `:215-217` returns when
  `currentPos < 0` or the upload context is unset; `:219-234` fires
  `alert('Select a TTS model in Reader > TTS Settings first.')`; `:239` returns on empty text. There
  is no pending/spinner/result UI at all, and errors reach only `console.error` (`:263`, `:266`).
  Give each branch a visible, localized reason (a toast, consistent with the rest of the app — a raw
  `alert()` is the same family as deferred item 161's `window.prompt` finding). **Also fix
  `language: 'en'` hardcoded at `:248`** — the run's book is Vietnamese; per the multilingual
  standard this must come from the content/display language, not a literal.
  Files: `frontend/src/components/editor/AudioAttachActionsExtension.ts` (214-292),
  `frontend/src/features/studio/panels/EditorPanel.tsx` (183-196).
  Logging: WARN on each unmet precondition, naming the specific missing value.
  Tests: one per branch asserting a visible reason; one asserting the language is not literal `'en'`.

  **EVIDENCE (T6).** Six defects, all fixed: five bare `return`s and a raw `alert()` left the ✨
  button looking active while doing nothing, and `language: 'en'` was hardcoded — which for the
  run's Vietnamese manuscript would have generated **English audio**, not merely a silent failure.

  Rather than bolt six toasts onto six branches, the precondition logic is extracted into a pure,
  exported `resolveTtsBlocker()` returning a named blocker, plus a `TTS_BLOCKER_MESSAGES` table.
  Five `return`s buried in a ProseMirror plugin view cannot be tested; a resolver can — and the
  table makes "a blocker with no message" a structural impossibility rather than a review item.

  The language now comes from the book's own `original_language`, threaded through a new optional
  `ImageUploadContext.language` and read from the **same cached `['book', bookId]` query**
  `useChapterDoor` already uses — whose own comment reads *"never hardcode 'en' — multilingual
  platform."* Left `undefined` while loading so the resolver can **refuse and say so**, rather than
  silently asserting English.

  BITE — removed the language guard, restoring the pre-T6 "assume English" behaviour:

  ```
  # RED
    × resolveTtsBlocker (T6) > refuses rather than defaulting the language to English
      → expected null to be 'no-language'
   Tests  1 failed | 7 passed (8)
  # RESTORED byte-exact (diff clean)
   Tests  8 passed (8)
  ```

  Regression for C3 as a whole: `tsc --noEmit` clean, eslint clean on all four changed files, and
  **328 test files / 2648 tests green** across `features/studio`, `features/composition` and
  `components/editor`.

### Phase 2 — Make the quality signals see human-authored prose

- [x] **T7** — Consume the decompiler's `mappings[]` and write `source_scene_id` back.
  **This is a caller-side gap — do not change the routes.** Both `materialize-scenes` routes already
  return `mappings[]` identically; no caller anywhere consumes them, even though
  `scene_decompile.py:284` documents an intended, idempotent-on-retry write-back. The frontend
  caller reads only `work_resolved` and drops `res.mappings`.
  Since `scenes.source_scene_id` is the **sole** trigger for `chapter.scenes_linked` →
  `written_verdict.py:56-73` reconcile, adding that write-back is the missing human-driven path into
  the entire `written_*` chain.
  **Decided (PO, 2026-09-12): a new internal book-service endpoint that accepts the mapping batch.**
  Composition POSTs the mappings; **book-service performs the write to its own table.** This keeps
  the scope-separation standard intact (one owner per concept — `scenes.source_scene_id` belongs to
  book-service), makes the batch atomic, and gives the retry-idempotency documented at
  `scene_decompile.py:284` something real to be idempotent against.
  Rejected alternatives, recorded so they are not relitigated: composition writing book-service's
  column directly (crosses the ownership boundary that standard exists to protect), and a
  browser-side per-scene loop (N round-trips, partial-failure states, and it puts a data-integrity
  step in the least reliable place).
  The new endpoint is internal-token authenticated but must **still grant-check** the asserted
  owner's EDIT grant on the book before writing — follow the pattern already used at
  `outline.py:975-1001` (`internal-route-driven-by-a-session-must-grant-check`), which exists
  because the internal token authenticates the caller but does not authorize the action.
  Respect `scene_decompile.py:263-290` — human-authored nodes are deliberately excluded
  (`skipped_authored`); this task must not quietly overwrite an author's own structure. Surface a
  count of what was linked vs skipped.
  Files: `services/composition-service/app/engine/scene_decompile.py` (85-89, 246, 263-326),
  `services/composition-service/app/routers/outline.py` (975-1001, 1004-1025 — read for context),
  `frontend/src/features/plan-hub/hooks/useExtractPlan.ts` (the `res.mappings` drop),
  plus the book-service scene-write path that owns `source_scene_id`.
  Logging: INFO linked/skipped counts with reasons; WARN when a mapping is ambiguous and dropped.
  Tests: extract → mappings persisted → `chapter.scenes_linked` emitted → `written_*` populated.
  NV-6: assert against a chapter whose heading genuinely does not match a scene and confirm it is
  NOT linked — a test that only proves the happy path is the NV-3 "scope never reaches it" shape.

  **EVIDENCE (T7).** Built per D4. New `POST /internal/books/{book_id}/scene-mappings`
  (`book-service/internal/api/scene_mappings.go`, routed at `server.go`) — the book-scoped sibling
  of the existing EPUB-import endpoint, which could not be reused because it keys on an import job
  and joins `chapter_import_provenance`; a Hub extraction has neither. Book-service owns the write
  because `scenes` is its table, and it re-checks the asserted owner and constrains the UPDATE to
  chapters of THIS book, so a caller cannot reach another book's scenes. `source_scene_id IS NULL`
  keeps it idempotent and non-destructive — a re-run relinks nothing and never overwrites an
  author's existing link. `emitScenesLinked` fires per touched chapter **inside the same
  transaction**, because the event is the entire point: without it the columns change and nothing
  downstream notices.

  Composition calls it via a new `BookClient.apply_scene_mappings`, consumed by a shared
  `_write_back_scene_mappings` helper wired into **both** materialize routes. A failure is degraded,
  never fatal and never silent: the extraction has already committed, so raising would fail a user
  action that genuinely succeeded — instead the result carries `scene_link_writeback`, and
  `useExtractPlan` surfaces it, telling the author a re-run is safe.

  BITE — reverted the Hub CTA route to `return result.to_dict()`, i.e. the original defect:

  ```
  # RED
  E  AssertionError: 2 materialize_scenes call(s) but only 1 write-back(s): a route computes
     the back-link mappings and drops them, which is the exact defect T7 fixed
  1 failed, 4 passed
  # RESTORED byte-exact (diff clean)
  5 passed
  ```

  The drift-lock is deliberately DB-free (the shape `scenes_linked_parity_test.go` uses, and for
  its stated reason — "no DB, so it can never be skipped into a false green"), because the original
  defect was never a broken write-back: it was two routes that each computed the mappings and
  returned them unused, with every other test green. Four behavioural tests cover the happy path,
  the reported failure, the empty extraction, and a partial relink.

  Regression: `go build ./...` + `go vet` clean; composition-service **4154 tests passed**;
  frontend `tsc --noEmit` clean.

- [x] **T8** — Add a manuscript-derived "realized" signal to conformance.
  Per C2 both existing signals are structurally unreachable from human authoring. Add a third:
  fetch the chapter draft (`BookClient.get_draft`, already used at `routers/plan.py:391`), segment
  the Tiptap body by `attrs.sceneId` (written by `_attach_scene_ids`,
  `app/engine/prose_doc.py:58-78`) falling back to normalized heading-title match, and report
  per-scene prose presence and word count.
  **Keep the three signals distinguishable in the response** — do not collapse them into one
  boolean. "A generation job wrote this" and "a human typed this" are different facts, and a
  conformance panel that cannot tell them apart loses exactly the information the flywheel needs.
  Files: `services/composition-service/app/routers/conformance.py` (191-229, 288-291, 334-421),
  `services/composition-service/app/engine/prose_doc.py` (40-45, 58-78, 125+),
  `frontend/src/features/composition/motif/components/ConformanceSceneRow.tsx` (66-68),
  `frontend/src/i18n/locales/en/composition.json:854`.
  Logging: DEBUG per scene — which signal matched, segment length, and why a scene was unmatched.
  Tests: a chapter authored purely by the paste path reports realized. NV-6: empty the body, watch
  it go red, restore, paste output. Per IN-8's 4-source discipline a response-shape change touches
  the API model, the FE type, and a drift test — all three, or none.

  **EVIDENCE (T8).** New `scene_prose_presence()` in `app/engine/prose_doc.py` segments the SAVED
  manuscript by scene and returns `{scene_id: word_count}` for scenes that actually have prose.
  `realized` now carries **three distinguishable signals**, not one collapsed boolean:
  `has_prose` (either source), `source` (`generation_job` | `manuscript` | null), and
  `manuscript_words`. "A generator wrote this" and "a human typed this" are different facts and the
  flywheel needs both.

  Anchoring deliberately reuses `_attach_scene_ids`' own rules — exactly one free heading per
  title, each heading anchoring at most once — rather than re-deriving them, because the editor
  draws its Scene Rail the same way; a looser rule here would report a scene as written that the
  author's own rail shows as unanchored.

  **The design caught a flaw in itself.** The first implementation counted a sub-heading's TITLE
  toward the word total, so a scene containing nothing but a sub-heading would have read as
  written — the same false positive the bare-heading case exists to prevent, one level down. The
  failing test found it before commit; sub-heading titles are now excluded.

  BITE — restored the bare-heading false positive:

  ```
  # RED
  E  AssertionError: an empty section was reported as written
  E  assert 's1' not in {'s1': 0, 's2': 6}
  1 failed, 7 passed
  # RESTORED byte-exact (diff clean)
  8 passed
  ```

  Eight tests cover: hand-pasted prose counts (the case the task exists for), a bare heading does
  NOT, an explicit `attrs.sceneId` beats title matching, an ambiguous title anchors nothing, a
  deeper heading belongs to its scene, junk input degrades to `{}` rather than raising, and the
  read does not mutate the caller's document.

  **Two self-inflicted regressions, both caught by the suite and fixed:** a `.replace()` whose
  anchor didn't exist silently did nothing (no assert — my error, now a habit to assert every
  patch), and adding `bearer` as a REQUIRED dependency would have changed this route's auth
  contract for every scope to buy one best-effort read in one branch. It is now optional via
  `bearer_scheme`, and the manuscript signal degrades with a logged reason when absent.

  Regression: composition-service **4162 tests passed**.

- [x] **T9** — Un-conflate `no_tracked_promises` from extraction failure.
  `extract_tracked_promises` returns `[]` on genuine emptiness AND on any LLM failure, including the
  truncated/unusable path (`promise_audit.py:276-287`, `:290-310`). Return a discriminated result so
  `quality_report.py:255-262` can emit a distinct code (e.g. `promise_extraction_failed` vs
  `no_tracked_promises`), and leave the sibling `coverage_unavailable` (`promise_audit.py:334`,
  `quality_report.py:233`) meaning what it means today.
  This is the same class as Phase 3's audit — a failure reported as a clean empty result — so treat
  it with that severity, not as copy.
  Files: `services/composition-service/app/engine/promise_audit.py` (276-287, 290-310, 321-322, 334),
  `services/composition-service/app/engine/quality_report.py` (233, 255-262, 274-276).
  Logging: ERROR on extraction failure with the provider-side reason; INFO on genuine emptiness.
  These must be different levels — that is the entire point of the task.
  Tests: a forced extract failure produces the failure code, not the empty code. NV-6: collapse the
  two codes, watch it go red, restore, paste output.

  **EVIDENCE (T9).** Added `extract_tracked_promises_ex()` returning `(promises, extraction_ok)`;
  the old list-only `extract_tracked_promises` is kept as a wrapper for callers that genuinely
  cannot act on the difference (the eval harness skips the book either way), so no contract broke.
  Three previously-collapsed paths now report failure distinctly: LLM error, truncated/unusable
  response, and unparseable content. `quality_report` emits `promise_extraction_failed` instead of
  `no_tracked_promises` for all three.

  **A pre-existing test was pinning the defect in place.**
  `test_coverage_extract_degrade_yields_no_tracked_promises` asserted that a FAILED extraction
  reports `no_tracked_promises` — the conflation itself, ratified by the suite. Rewritten to assert
  the corrected contract while keeping the no-phantom guarantee it was really protecting. This is
  the shape E2E CONVENTIONS warns about: *"an assertion nobody can justify is how a suite ends up
  pinning a bug in place."*

  BITE:

  ```
  # RED
  E  AssertionError: assert 'no_tracked_promises' == 'promise_extraction_failed'
  # RESTORED byte-exact (diff clean)
  6 passed
  ```

  Regression: composition-service **4168 tests passed**.

- [x] **T10** — Render the coverage reason instead of discarding it.
  `BookPromiseCoverageSection.tsx:50-54` branches on `c.error` and renders a fixed string, dropping
  the machine-readable code that is already on the wire (`api.ts:893-905` types it;
  `useBookPromiseCoverage.ts:28` preserves it). Map the code through an i18n reason table with
  `coverageNa` as fallback, and for `no_tracked_promises` link straight to the Promises panel — the
  user's actual next step. Depends on Task 9 for the new codes.
  Files: `frontend/src/features/composition/components/BookPromiseCoverageSection.tsx` (48-56),
  `frontend/src/i18n/locales/en/composition.json:1648`,
  `frontend/src/features/studio/panels/QualityCoveragePanel.tsx:40`.
  Logging: DEBUG the raw code received whenever the fallback is used — an unmapped code should be
  traceable, not invisible.
  Tests: each known code renders its own reason; an unknown code renders the fallback AND logs.

  **EVIDENCE (T10).** The panel branched on `c.error` and then discarded it, rendering one fixed
  string for every cause — so "you have not declared any promises yet" (one click to fix) and "the
  extraction call failed" (not the user's to fix) read identically. Now mapped through a reason
  table, with `data-reason` on the element, an amber treatment for a genuine failure rather than
  neutral "nothing here yet" grey, and a direct pointer to the Promises panel for the unconfigured
  case. An unmapped code falls back to the original string **and** logs, so a future code is
  traceable rather than invisible.

  BITE — restored the single fixed string:

  ```
  # RED
  E  AssertionError: expected 'coverageNa' not to be 'coverageNa'
   Tests  2 failed | 6 passed (8)
  # RESTORED byte-exact (diff clean)
   Tests  8 passed (8)
  ```

  The test asserts the two causes render **differently from each other** rather than asserting
  specific copy: the i18n harness renders keys, not `defaultValue`, so a copy assertion would have
  been testing the harness. A fourth test asserts no reason renders at all on success (NV-7).

  Regression: `tsc` + eslint clean; **1081 composition tests green**.

### Phase 3 — Close the silent-write / exploding-read class

- [x] **T11** — Cap-parity sweep: every response-model bound needs a matching write-side bound (IN-4).
  Finding #12's root cause was `goal` capped at 2000 on the *response* model while every write path
  declared unbounded `str` — so an over-long write always succeeded and then 500'd every later read
  of the whole book's arc list. That was point-fixed; the *shape* was not. Issue #224's own
  follow-up names `title`/`summary` on the same Create/Patch schemas as carrying the identical
  unguarded shape.
  Enumerate every field where a response model declares a length bound and the corresponding write
  schema (REST **and** the MCP tool-arg schemas) does not, then close each. Prefer a mechanical
  check over a one-time sweep — a sweep is `default-uncovered` for any field added tomorrow, which
  is precisely NV-3.
  Files: `services/composition-service/app/db/models.py`, `app/routers/arc.py`,
  `app/routers/outline.py`, `app/mcp/server.py`, plus the equivalent book-service schemas.
  Logging: the new rejection must be a self-correcting one-liner per IN-6 — name the field, the
  limit, and the actual length.
  Tests: a write exceeding each bound gets 422, not a later 500. NV-6 per field family.

  **EVIDENCE (T11).** Built as a mechanical parity check rather than a sweep, per the row's own
  NV-3 reasoning. It derives BOTH sides from source — response-model caps from `db/models.py`,
  write-side bounds from the Create/Patch schemas — so a field added tomorrow is covered without
  anyone remembering to add it.

  **It found five real gaps on its first run**, exactly the shape #224's follow-up predicted:

  ```
  outline.py::NodeCreate.title     is `str`         but the response model caps `title` at 500
  outline.py::NodeCreate.synopsis  is `str`         but the response model caps `synopsis` at 20000
  outline.py::NodePatch.title      is `str | None`  ...
  outline.py::NodePatch.synopsis   is `str | None`  ...
  arc.py::PartCreate.title         (false positive — see below)
  ```

  **`title` is the sharper edge and nobody had noticed it: 500 characters.** #224 was hit at 2800
  characters in a `goal`; a 501-character chapter title would have 500'd the same reads, and is far
  easier to reach by accident. Fixed with `_NodeTitle`/`_NodeSynopsis` mirroring the response caps.

  **Two corrections the work forced on the check itself** — both worth more than the fix:
  1. `PartCreate.title` was a **false positive**: it was already bounded via
     `Field(default="", max_length=500)`, and the check read only the annotation. A parity check
     that cries wolf is one people learn to ignore. It now reads the whole declaration.
  2. **The check passed on a file that did not parse.** While adding the caps I wrote literal
     backslash-escapes into `outline.py` via a bad raw-string replacement; every parity assertion
     stayed green because they only ever read TEXT. Added `test_the_files_this_check_reads_are_valid_python`
     — a source-text check that cannot notice its subject is unparseable is reporting coverage it
     does not have.

  BITE — removed the write-side cap from `synopsis` again:

  ```
  # RED
  E  outline.py::NodeCreate.synopsis is `str = ""` (unbounded) but the response model caps
     `synopsis` at 20000 — an over-long write will succeed and then 500 every later read
  1 failed, 6 passed
  # RESTORED byte-exact (diff clean)
  7 passed
  ```

  A companion test feeds `_is_bounded` known-good and known-bad declarations (NV-2), and another
  asserts the models scan actually discovers `goal`/`synopsis`/`summary` — without it, a silently
  non-matching regex would make every parity assertion pass vacuously (NV-3).

  Regression: composition-service **4175 tests passed**.

- [ ] **T12** — Make truncation visible where it happens (OUT-5).
  Finding #10's fix raised `STEERING_TOKEN_CAP` 2000→8000 but explicitly deferred the real problem:
  **truncation still has no UI-visible indicator**, so an author with a genuinely oversized bible
  silently loses rules, discoverable only in server logs. OUT-5 already says never silently
  truncate — report the cap. Surface the drop in the Steering panel (how many entries, how many
  tokens, which ones) and in the chat turn that suffered it.
  Files: `services/chat-service/app/services/steering.py`, the Steering panel under
  `frontend/src/features/steering/`, and the turn-metadata path to the chat UI.
  Logging: the drop is already logged; add the count to the turn's user-visible metadata, not just
  stderr.
  Tests: an oversized bible produces a visible indicator. NV-6: this run had to read server logs to
  find it, so the test must fail if the indicator is removed while the log line stays.

  **⚠ PARTIAL — row stays OPEN. The reporting primitive is built and tested; nothing user-visible
  changed, which is the whole point of the row.**

  Done: `select_steering_ex()` returns `(selected, SteeringTruncation | None)` carrying the dropped
  count, **the dropped rules' names**, the cap and the kept-token total. The list-only
  `select_steering` is kept as a wrapper, so no existing caller or test changed. `stream_service`
  computes it per turn into `steering_truncation`. 6 tests, BITE verified:

  ```
  # RED (report the count but not WHICH rules)
  E  assert 0 == 5   [test_a_dropped_rule_is_reported_with_its_NAME]
  # RESTORED byte-exact (diff clean)
  21 passed  (6 new + the 15 pre-existing steering tests, unchanged)
  ```

  **Not done, and why.** Surfacing it needs one of two routes, both larger than they look:
  - **Per-turn notice.** `stream_response` feeds `StreamingResponse` directly, so it must yield
    str/bytes; the dict events (`{"compaction": …}`) are serialised in an intermediate layer inside
    a 14,705-line generator. Threading a new event through it without the ability to run the live
    stack here risks breaking the product's core stream to add a toast. Not a trade worth making
    blind.
  - **Steering panel indicator** (the row's primary ask, and the better UX — an author sees it
    while editing rules, not mid-generation). The panel reads book-service `/v1/books/{id}/steering`,
    but the cap and the token estimator live in **chat-service**, which has no book-scoped routes at
    all. So this needs a new router + gateway wiring + frontend work across three layers.
    Re-implementing the estimate client-side was rejected outright: a second source of truth that
    disagrees with the server is worse than no indicator.

  **Recommendation for whoever takes this:** build the panel endpoint, not the turn notice. A
  budget preview *while editing rules* prevents the problem; a mid-turn toast only reports it after
  the generation it spoiled. Note two pre-existing failures in
  `test_a_turn_that_called_nothing_may_not_claim_an_effect.py` — confirmed pre-existing by stashing
  these changes and re-running; unrelated to this work.

- [x] **T13** — Stop save-on-blur from discarding a sibling field's unsaved text.
  Finding #13 is a data-loss shape, not friction: typing a 1686-char chapter Goal, then saving a
  *different* field, reset the Goal textarea to its last-saved value (empty) — confirmed via API,
  not just visually. It recurs for every node until fixed. Related to Task 4's dirty-state
  reasoning; solve them consistently rather than inventing two mechanisms.
  Files: the Chapter/Arc Inspector field components under `frontend/src/features/composition/` and
  `frontend/src/features/plan-hub/` (confirm exact files at BUILD — the run observed this on the
  Chapter Inspector Goal and the Arc Summary field).
  Logging: WARN when a re-render would replace a dirty field's value with a server value.
  Tests: edit A, save B, assert A survives. NV-6: revert the guard, watch it go red, restore.

  **EVIDENCE (T13).** Found in `plan-hub/components/PlanDrawerEdit.tsx`: `CommitField` held
  `useEffect(() => setDraft(value), [value])`, which re-syncs from the server unconditionally —
  including over text the user has typed and not saved. Both halves of the reported harm follow
  from it: the draft is replaced, **and** `commit` then sees `draft === value` and writes nothing,
  so the text is unrecoverable with no error anywhere.

  Fixed with a `dirty` ref — set on keystroke, cleared on commit — gating the re-sync. Same policy
  as T4's G7 on the manuscript hoist, deliberately: two mechanisms for one rule ("unsaved
  keystrokes are the user's") is how they drift apart.

  **The first bite did NOT go red, and that was the most useful result of this row.** My initial
  test re-rendered with a changed *sibling* field, leaving `goal` as `''` in both renders — so the
  `[value]` effect never fired and the test passed with or without the guard. Textbook NV-2, "the
  subject cannot vary". Rewritten so the re-render actually changes `goal` (a concurrent edit, a
  412 recovery reload, or a stale snapshot echoing back — the real conflict shapes). Then:

  ```
  # RED (guard removed)
    × keeps a dirty field when the parent re-renders with the server value
      → expected 'a stale server value' to be 'An Nhien refuses the sect elder, and …'
    × still commits that text afterwards — surviving on screen is not enough
      → expected "spy" to be called with arguments: [ { goal: 'the long goal' } ]
   2 failed | 17 passed (19)
  # RESTORED byte-exact (diff clean)
   19 passed (19)
  ```

  Two companion tests keep the guard from over-reaching (NV-7): a CLEAN field still re-syncs (so
  selecting a different node updates the drawer), and a field re-syncs again once committed (so it
  is not permanently pinned to whatever was typed first).

  **Honest scope note.** This fixes the *mechanism* by which unsaved text is destroyed, and the
  bite proves it. I could not reproduce finding #13's exact reported sequence — typing Goal then
  saving Synopsis — because that path leaves `goal` unchanged between renders and so never trips
  this effect at all. Either the run's sequence involved a genuine value change (a 412 reload is
  the most likely candidate, and this now covers it), or there is a second, server-side
  last-write-wins path that this does not touch. Worth a live reproduction before finding #13 is
  called closed.

  Regression: plan-hub **24 files / 257 tests green**; `tsc` clean.

### Phase 4 — PlanForge compile self-recovery

- [x] **T14** — Bounded compile retry that looks up the real `arc_id`.
  Finding #11: two Tier-A approvals and ~10 minutes produced zero arcs. The backend's rejections are
  *good* — placeholder-id rejection, and an `arc_id != run_id` loop-guard that names the confusion
  explicitly — but the model never adapts across three clearly-worded refusals, and on the third
  attempt announced it would send the same bad placeholder again.
  Add bounded recovery: on either named rejection shape, call `composition_arc_list` /
  `composition_package_tree` for a real id before retrying, capped at 2 attempts. Note the existing
  precedent and its hazard — `FindToolsAttemptTracker` exists precisely because an unbounded retry
  invitation once produced 40 `find_tools` iterations and a 0-length final answer. Cap it from the
  start.
  Files: `services/chat-service/app/services/stream_service.py` (the tool-loop retry seam),
  `services/chat-service/app/services/tool_discovery.py` (`FindToolsAttemptTracker` as the pattern),
  and the `plan` group description in `GROUP_DIRECTORY` (`tool_discovery.py:100-113`).
  Logging: INFO each recovery attempt with the rejection reason that triggered it and the id looked
  up; WARN at the cap.
  Tests: the two rejection shapes each drive exactly one lookup-then-retry, and stop at the cap.

  **EVIDENCE (T14 + T15 — delivered together; they are one mechanism).**

  **Re-scoped after reading the code, per rule 6.** The row proposed a lookup-then-retry in the
  tool loop. The codebase shows why that is the wrong lever: the refusal ALREADY names the fix
  ("look the missing one up… and call again"), and models ignore it — the audited corpus has one
  session repeating a refused call **14 times** and another **71**. Adding a retry to a model that
  will not stop retrying is the wrong direction. What was missing is the opposite: a way to STOP.

  So the refusal now counts and escalates. `RepeatedRefusalTracker` (per-session, TTL'd, keyed on
  the normalised refusal) feeds `duplicate_identifier_message(..., attempt=N)`; the second identical
  refusal drops the retry advice and says *"You have now sent this same call N times… STOP retrying
  this call… tell the user plainly that you could not complete this step… do not report the task as
  done."* That is T15 in the same string — the run's real harm was not the failed call but the turn
  closing on partial success, so the author believed a plan existed.

  Deliberately the same shape as `FindToolsAttemptTracker`, which exists because an unbounded retry
  invitation once produced 40 `find_tools` iterations and a 0-length answer. It remains a REFUSAL,
  never a repair — the runtime still cannot know which argument is wrong.

  BITE:

  ```
  # RED (escalation disabled — every refusal says the same thing)
    × test_the_second_refusal_tells_it_to_STOP
    × test_the_repeat_refusal_forbids_claiming_success
    × test_the_repeat_refusal_says_how_many_times
   3 failed, 10 passed
  # RESTORED byte-exact (diff clean)
   19 passed  (13 new + the 6 pre-existing refusal tests, unchanged)
  ```

  **A gate caught a real architectural violation in my code, and was right to.** The tracker first
  did `import time` inside `agentruntime`, and `test_cp1_membrane` failed:
  `FAIL …/toolcontract.py:641: import time - ambient`. That package refuses ambient APIs (the same
  rule that refuses `uuid`). Fixed at the cause per rule 4: the clock is now an injected, REQUIRED
  argument, which also makes the tracker fully deterministic under test and lets the caller — which
  lives outside the membrane — decide what "now" means. Better design than the one the gate rejected.

  Counter-tests keep the escalation from over-firing (NV-7): a different tool, a different param
  pair, a different value, and a different session each start at 1, and an expired entry starts over
  so a session that erred an hour ago is not met with an escalated refusal today.

  Regression: chat-service **3954 passed** (2 pre-existing failures in
  `test_a_turn_that_called_nothing_may_not_claim_an_effect.py`, confirmed pre-existing earlier by
  stashing); membrane + contract suites **179 passed, 3 skipped**.

- [x] **T15** — End a failed compile honestly.
  The run's turn reported partial success ("Did plan_propose_spec") rather than "compile failed, and
  here is why" — so the author believed a plan existed when nothing durable had been created. Once
  Task 14's cap is hit, the turn must state the failure and the last rejection reason.
  This is the same honesty guard the codebase already gets right elsewhere (*"I did not make any
  changes to your story or the plan. I only started an asynchronous job…"*) — extend that behavior,
  do not invent a new mechanism.
  Files: `services/chat-service/app/services/stream_service.py` (turn-end summary path).
  Logging: ERROR with the full rejection chain.
  Tests: a capped-out compile produces a failure-shaped turn end, never a success-shaped one.

  **EVIDENCE (T15).** Delivered inside T14's escalated refusal — see that row. The repeat message
  explicitly forbids reporting the task as done and requires telling the user what was missing,
  which is the honesty guard this row asks for, applied at the point the model is actually reading.

### Phase 5 — Prose quality

- [ ] **T16** — Close the reproducible prose-length under-delivery.
  Finding #20, three independent measurements, all short: an initial ask landed at ~25-40% of the
  requested length; an explicit expand-and-enrich follow-up still landed short; a batched
  multi-scene ask landed ~15% under a modest 400-600-word target. It only partially self-corrects
  when told explicitly.
  Implement a measured floor rather than a prompt plea: request proportionally more than the target,
  measure the returned length, and re-ask once when under. Per SET-1..8, if a target length becomes
  user-visible it is a **setting** with a declared default — not a magic constant and not a silent
  fallback.
  Files: the scene/chapter generation prompt assembly in `services/composition-service/app/engine/`
  and/or the co-writer skill prose in `services/chat-service/app/services/`.
  Logging: INFO requested vs delivered word count for every generation — this finding took three
  hand-measurements to establish and should have been one query.
  Tests: a short return triggers exactly one re-ask, and the ratio is asserted, not eyeballed.

  **⚠ PARTIAL — row stays OPEN. The core is a PO decision the repo has ALREADY reserved, and I am
  not taking it.**

  **What the code already knows** (found by reading it, per rule 6 — the row's premise that this
  is unimplemented is wrong):
  - `MEASURED_SINGLE_CALL_CEILING_WORDS = 1500` — the measured point past which a single call
    stops complying.
  - The failure mode is characterised: the model **negotiates** rather than compresses
    (*"I cannot produce a 4000-word text in a single response…"*), so the shortfall is worse than
    the word counts suggest because the refusal text is itself counted.
  - `draft_beats` already solves it, measured same book/model/day: 2500 in one call → ratio
    **0.61**; in two beats → **0.95 / 1.23**. 4000 in one call → **0.24**; in three → **1.21 / 1.04**.
  - `book_skill.py:81` already tells the model the 1,200-1,500 ceiling, to state it up front, to
    offer the composition path, and **never** to promise a Part Two (measured: Part Two arrived
    **0 times out of 4**).

  So the run's ~25-40% delivery happened *with* that guidance present. This is a model-compliance
  limit, not missing machinery — the same shape as T3.

  **Why the row's proposed fix is not mine to make.** `SESSION_HANDOFF.md`'s
  `D-DRAFT-OUTPUT-NO-POST-CONDITION` records the decision explicitly:

  > *"Not fixed yet: detect-and-surface vs detect-and-reject vs strip is a product decision (it
  > affects spend and UX on a paid generation), so it needs the author's call, not mine."*

  A "re-ask once when under" is a second paid generation on the user's key. All three options in
  that reserved decision are exactly what this row would pick between.

  **Done, because it costs nothing and the row asks for it:** one INFO line per generation with
  asked / delivered / ratio / beats / counting-method. The target and the delivered length were
  both already computed here and never reached a log together, which is why establishing this
  defect took a human three hand-measurements. `realised_words`' method is included because a
  `split()` ratio against a spaceless-script target would read as a permanent ~85% shortfall.

  **PO decision needed** to close this row: on a short generation, (a) surface it to the author,
  (b) reject and re-ask automatically — spending again, or (c) accept silently as today. Composition
  suite **4175 passed**.

- [ ] **T17** — A critic pass for the one defect prompting could not fix.
  Report §3: three of four recurring prose defects closed reliably via the review-and-revise loop.
  <!-- doc-language-gate: ok -- the Vietnamese construction IS the subject matter: it is the literal
       pattern this task's detector must match, so paraphrasing it into English would destroy the
       specification. Scoped to the two quoted fragments below. -->
  The fourth — the `"không phải X, mà là Y"` antithesis plus `"sự X"` abstract-noun stacking — did
  **not**, across two independent, increasingly specific attempts; the second reproduced the exact
  flagged construction *inside brand-new content written to remove it*. That is strong evidence it
  is not addressable by instructing the writer model.
  <!-- doc-language-gate: end -->
  Route it instead through a **post-generation** critic (a Critic panel already exists in the
  quality group), with a detector for the construction and a targeted rewrite. Follow the
  [AI-Task Standard](../specs/2026-07-03-ai-task-standard.md) for a single-shot generate feature and
  the provider-gateway invariant — no direct provider SDK, no hardcoded model name.
  **Scope honestly:** the detector is language-specific. Per the multilingual standard do not
  hardcode a Vietnamese pattern into a language-agnostic path; make the rule set language-scoped and
  declare which languages are covered.
  Files: the Critic path under `services/composition-service/app/engine/`, its panel under
  `frontend/src/features/studio/panels/`.
  Logging: INFO detections with position and the rewrite applied; before/after must be
  reconstructable from logs.
  Tests: fixture prose with the construction is detected; prose without it is not. NV-7 applies —
  a detector that fires on everything tells you nothing, so assert the negative case explicitly.

### Phase 6 — Remaining UX

- [ ] **T18** — One chapter-title precedence, used by all three quality panels.
  The Conformance picker renders `c.title || c.original_filename || #sort_order`
  (`QualityConformancePanel.tsx:52-56`) instead of the sidebar's `chapterDisplayTitle()`
  (`frontend/src/features/studio/manuscript/partsTree.ts:26-30`), which deliberately never falls
  back to a storage filename. The observed "Untitled chapter" is a server-side placeholder arriving
  via `original_filename`. **The same defect is copy-pasted in two sibling panels** —
  `QualityCriticPanel.tsx:54-58` and `QualityHealPanel.tsx:110-114`. Route all three through the one
  helper; per SDK-First, two users of a rule means shared, not copied.
  Files: the three panels above + `partsTree.ts`.
  Logging: DEBUG when a fallback tier is used, and which field won.
  Tests: a chapter with a placeholder `original_filename` and empty `title` renders the localized
  "Chapter N", not the filename — in all three panels.

- [ ] **T19** — Fix the two stale-widget cache invalidations.
  Both have exact causes:
  (a) `frontend/src/features/studio/manuscript/useChapterDoor.ts:33-35` invalidates only
  `['plan-hub','simple-chapters',bookId]`, missing the advanced canvas keys (`arcs`, `overlay`,
  `scene-links`, the node windows) and `['plan-hub','book-chapters',bookId]` — so a new chapter is
  invisible until reload. Fix: broaden to the `['plan-hub']` prefix, which four sibling hooks
  (`usePlanChildCreate.ts:61`, `usePlanMoves.ts:171`, `usePlanNodeWrites.ts:51`,
  `useExtractPlan.ts:51`) already do.
  (b) `SceneRail.tsx` never invalidates `['composition','publish-gate',projectId,chapterId]`, so the
  "N of N scenes not yet done" counter (`usePublishGate.ts:96-98`) is stale after a status write —
  as are `canonBlocked` and `uncheckedWarning` from the same query.
  Files: `frontend/src/features/studio/manuscript/useChapterDoor.ts` (33-35),
  `frontend/src/features/studio/manuscript/SceneRail.tsx` (55-66, 131-136, 204),
  `frontend/src/features/composition/hooks/usePublishGate.ts` (18-22).
  Logging: DEBUG the invalidated key set after each mutation.
  Tests: mutate through the widget's own adjacent control, assert the widget reflects it with no
  reload. NV-6: remove each invalidation, watch its test go red, restore.

- [ ] **T20** — Cascade the book rename to its Knowledge Project, and stop the silent create no-op.
  Findings #6 and #7 compound into a ~20-minute dead end: the auto-created Knowledge Project keeps
  the book's title *as of creation*, Projects search is by-name only, so searching the book's
  current title finds nothing and reads exactly like "no project exists" — and the natural recovery
  (`POST /v1/knowledge/projects` for a book that already has one) returns `200 OK` and silently
  no-ops, discarding everything typed with no error toast. AGENTS.md's own Agent Extensibility
  Standard names that anti-pattern explicitly.
  Two fixes: cascade the rename, and make create return a real conflict (or update) rather than a
  lying success.
  Files: `services/knowledge-service/` project routes + the book-rename path in `services/book-service/`.
  Logging: INFO the cascade; WARN the conflict branch with the existing project id.
  Tests: rename cascades; create-when-exists no longer returns bare success. NV-6 on both.

- [ ] **T21** — Signpost the real AI-planning path, and settle the Motif Library naming.
  (a) Finding #9: three plausible entry points are dead ends for "AI, plan my first arc" on a blank
  book — "Create a plan with AI" (decomposes *existing* prose), "Organise into storylines" (a manual
  textbox), "Suggest arcs" (matches a template *library*). The real capability sits behind attaching
  the PlanForge skill to Co-writer Chat, referenced from none of them. Add a pointer from each.
  (b) Finding #23: "Motif Library" is a plot-shape template picker for the planner, not a tracker of
  a story's own recurring imagery. Rename it (e.g. "Plot Shapes") **or** state in the empty state
  what it is not. Do not build a thematic-motif tracker here — that is a feature and it is out of
  scope. Note the binding data is genuinely load-bearing (conformance and the prompt packer both
  read `motif_application`), so this is naming only, never removal.
  Files: the three plan entry points under `frontend/src/features/plan-hub/` and
  `frontend/src/features/composition/`, the motif panel under
  `frontend/src/features/composition/motif/`, and the relevant i18n locale files.
  Logging: n/a (copy/navigation only) — except DEBUG when a new pointer is shown.
  Tests: each dead end exposes a reachable pointer to the working path.

### Phase 7 — Reconcile the build with the README (the release gate)

- [ ] **T22** — Re-run the claims audit against the built code and reconcile the README.
  This is the release gate per D1, and it runs LAST because it grades everything before it. For each
  row of the claims audit above, decide and execute one of: **(i)** the claim is now true — record
  the evidence that proves it (a test, a live-smoke, a screenshot), **(ii)** the claim is true but
  conditional — keep it and state the condition inline, or **(iii)** the claim is not true and will
  not be in this cycle — move it behind the same 🔄 In Progress marking the roadmap table already
  uses, or delete it.
  **Prefer (i) where it is cheap.** After Phases 1-6 the critic claim and the conformance claim both
  become defensible, which is most of the falsified set.
  **Do not quietly soften a claim without saying so** in the commit — a README edit that removes a
  promise is a product decision and should read like one.
  Files: `README.md` (§How LoreWeave is different, §Features, §Screenshots "AI Assistant Mode",
  the Roadmap table), plus this plan's audit table updated with the final disposition.
  Logging: n/a (docs).
  Evidence: per NV-6 the proof for any claim moved to "true" must be a check that can fail — a
  screenshot of a green panel is not evidence that the panel can go red.

- [ ] **T23** — Fix the Auto-Draft Factory's name and its unreachability from the Studio.
  Two separable defects found by recon, neither of which is a bug in the engine — which is
  production-grade, has 9 unit + 5 DB-integration suites, a Playwright spec
  (`frontend/tests/e2e/specs/campaign-factory.spec.ts`), and a verified live run
  (`docs/plans/2026-09-06-v0.1.0-go-live.md:320-333`).
  **(a) Naming.** "Auto-Draft Factory" and the README's *"run a whole drafting campaign across
  chapters"* describe prose drafting. The engine extracts knowledge and translates existing
  chapters; its own wizard placeholder says *"e.g. Translate Book 1 → Vietnamese"* and its
  completion CTA routes to the translation tab. Rename to what it does (the UI already calls it
  "Campaigns" in the sidebar — `common.json:11`), and fix the README line. **Do not rename the
  service or its tables** — that is churn with no user benefit; this is user-facing naming only.
  **(b) Reachability.** `App.tsx:202-205` routes `/campaigns`, and
  `components/layout/Sidebar.tsx:66` holds the only link — but the Studio sits outside
  `EditorLayout` (`App.tsx:124`) and never renders that Sidebar, so a user working in the Studio
  cannot see or reach it. Add a Studio-side entry point for a book already in context.
  **Also surface its hard preconditions** rather than letting them 400: a campaign requires a
  knowledge project (`campaigns.py:143-146`), KG-indexed published chapters in range
  (`campaigns.py:110-113`), `MANAGE` grant (`:154`), and both translator+extractor model roles
  (`useCampaignWizard.ts:92-94`). A user missing any of these currently meets an error, not an
  explanation — the same disclosure defect as Task 2.
  Files: `frontend/src/components/layout/Sidebar.tsx:66`,
  `frontend/src/i18n/locales/en/common.json:11`,
  `frontend/src/i18n/locales/en/campaigns.json`, the Studio entry point under
  `frontend/src/features/studio/`, `README.md`.
  Logging: DEBUG which precondition blocked wizard advancement, per Task 2's pattern.
  Tests: each precondition renders a specific, actionable reason; the Studio exposes a reachable
  entry point. NV-6 on the precondition messages.

---

## Explicitly out of scope

- **Building a thematic-motif tracker.** Finding #23 establishes the gap; filling it is a feature,
  not remediation. Task 21 settles naming only.
- **Rebuilding the Lane B `StudioEffectReconciler`** beyond what Task 4's guard requires. Spec 09's
  full build is "Debt #5 — deferred until #03 Compose shell" and is its own effort.
- **The antithesis detector for languages beyond the one Task 17 declares.** Scoped, not silently
  universal.
- **Re-running the full 5-arc human-sim.** A re-run is the natural VERIFY for this plan, but it is
  an hours-long exercise and belongs in its own session once Phases 1-2 land.
- **Renaming campaign-service, its tables, or its routes.** Task 23 fixes user-facing naming only.
  The engine is production-grade and verified; renaming its internals is churn with no user benefit.
- **Building prose drafting into the campaign engine.** That would be a genuine new feature (a
  third stage beside `knowledge` and `translation`). It may well be the right long-term answer to
  "the AI co-author," but it is not remediation and it is not in this plan.

## PO decisions taken at CLARIFY (2026-09-12) — settled, do not relitigate

| # | Question | Decision |
|---|---|---|
| D1 | Release posture | **The bar is the README, not the task count.** Ship when every README claim is true of the build or removed from it. See "The release bar" above. |
| D2 | Execution scope | **All six phases straight through**, per the size gate's "prefer ONE continuous run." |
| D3 | Task 3 approach | **Hot-seed the `book` domain** on the studio surface; pay and measure the token cost. Signposting rejected — see Task 3. |
| D4 | Task 7 ownership | **New internal book-service endpoint** taking the mapping batch; book-service owns the write. See Task 7. |

**Superseded:** this plan originally asked whether the corrected C1 flips the go/no-go and whether
to ship in v0.1.0. D1 answers both — the verdict is re-derived against the README claims audit at
Task 22, and the release waits for that, not for a date.

---

RESUME: **T1, T4, T2 done. T3 is BLOCKED on a PO decision — see its row.** D3's premise is false:
`book` is already hot on studio and `book_chapter_save_draft` is allowlisted against budget
truncation, so T3 as written has no work. The real finding is that the model had the tool on the
wire and still claimed it could not write — a prompting/model-capability problem the codebase
already documents in measured runs. Do NOT tick T3 without a new PO decision. T5 and T6 are DONE and committed
(C3 landed without T3). T7 is DONE and committed (C4 opened). T8 is DONE (C4 complete). T9 and T10 are DONE (C5 complete). T11 is DONE. T12 is PARTIAL and stays OPEN (primitive built + tested; no UI surfacing — see its row). T13 is DONE (C6 complete). T14 and T15 are DONE (C7 complete). T16 is PARTIAL and stays OPEN (observability added; the re-ask is a reserved PO/spend decision). Next is T17, then T18-T23. Three rows open: T3, T12, T16. Two rows now open: T3 (blocked on PO) and T12 (partial). Phases 2-7 are unaffected by the T3 block. Two rows in, the
pattern is clear and worth carrying forward: **the plan's premises keep being half wrong in the
product's favour** — T4's guard was already built (only its user-facing half was missing), and T1's
own citation checker caught two bad line numbers. Re-verify before building, every time. Frontend
`node_modules` was absent and is now installed (`npm install`, no lockfile in repo); vitest runs
from `frontend/`. The four PO decisions D1-D4 are
sealed (see "PO decisions taken at CLARIFY"): the release bar is the README claims audit, all phases
run through, T3 hot-seeds the `book` domain, T7 adds an internal book-service endpoint. Recon has
already corrected the report three times (C1/C2/C3) — trust the plan's cited line numbers over the
report's prose, and re-verify a line number before building on it.

```goal-prompt
goal: every task on the board is done with pasted evidence, and every README claim in the plan's claims audit is either true of the build with a check that can fail, or reconciled with the roadmap's own In-Progress marking
rules: |
  1 NON-VACUITY (NV-6) is the bar for every test: break the guarded thing, watch it go red, restore it, and PASTE the output. "I added a test" is not evidence and does not satisfy this goal.
  2 MCP-first for agentic logic; every provider call goes through provider-registry-service; no hardcoded model names or pricing.
  3 Written artifacts are ENGLISH - run scripts/doc-language-gate.py --staged before every commit and paste its line.
  4 Commit at the Commit Plan's RISK boundaries, never at file-count thresholds. Never --no-verify; if a gate blocks, fix the cause.
  5 The queue already puts T4 (G7 dirty-hoist guard) before T2/T3 on purpose - the guard must exist before agent writes get easier to trigger. Do not reorder it.
  6 Re-verify a cited line number before building on it. Recon corrected the delivered report three times already.
discipline: |
  Per task: READ the cited files -> BUILD -> run the real check -> PASTE its output -> tick the row -> commit at the next risk boundary -> take the next row.
  No bite output or no pasted evidence => the row is NOT done, regardless of how finished it looks.
  Update the RESUME line after every commit so a fresh session can resume from the file, not from memory.
stop: |
  a sealed decision D1-D4 turns out to be wrong
  a README claim must be REMOVED or softened rather than made true - that is a product promise and the PO decides, not the agent
  a destructive or irreversible action would be needed (force-push, branch delete, dropping data)
  the write target would be main, a shared deployment, or a non-throwaway database
  a security or data-loss-shaped bug is found
note: |
  NOT reasons to stop: a row finishing, a green suite, a commit landing, finding a pre-existing bug, context filling, or wanting to check in.
```
