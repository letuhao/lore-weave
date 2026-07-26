# MASTER IMPLEMENTATION PLAN — Writing Studio tool↔GUI build

> **Type:** FS · **Umbrella.** This file is **not** a build spec. It is the **contract that sequences the
> ten per-wave BUILD-DETAIL plans** already on disk. Every slice, file, function, test name and DoD
> evidence string lives in the wave plans; this file owns the **order, the gates, the ledger, the defer
> register, the collisions, and the escalations**.
> **Written at:** HEAD `9262ed53e`, branch `feat/context-budget-law`, 2026-07-13.
> **Parent:** [`docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) (audit + PO-sealed decisions).
> **Children (all BUILD DETAIL, all on disk):**
> `docs/plans/2026-07-13-studio-wave-0-foundations.md` ·
> `…-wave-1-quality.md` · `…-wave-2-arc-inspector.md` · `…-wave-3-motif.md` ·
> `…-wave-4-arc-templates.md` · `…-wave-5-planforge.md` · `…-wave-6-editor-craft.md` ·
> `…-wave-7-issues-feed.md` · `…-wave-8-kg-world.md` · `…-wave-T-translation-repair.md`

---

## 1 · THE COMMITMENT

> **DONE means:** every capability enumerated in plan 30's gap register (§5) that a user *owns* is
> reachable from a **Writing-Studio panel or an in-Studio affordance** — proven by a **live browser
> smoke on the rebuilt `:5174` image**, not by a green unit suite — with the two machine drift-locks
> green at **77 openable == 77 py enum == 77 contract enum** *(77, not 76 — PO `D-7` adds `place-graph`; a planning aid — **the DoD asserts the
> DELTA `N_before + k`, never this literal**; §5)*, `/review-impl` run at the close of **every one of the
> ten waves** with **every bug it found fixed before that wave closed**, and **zero** slice marked done
> whose DoD evidence string is absent from the transcript.

**This sentence is falsifiable in four independent ways** — and each falsifier is a real failure mode
this repo has already shipped once:

| Falsifier | The bug class it kills |
|---|---|
| A panel exists in `catalog.ts` and no live browser smoke ever mounted it | `agent-gui-loop-needs-live-browser-smoke-not-raw-stream` — a green unit suite proved the FE *could not execute it* |
| `panelCatalogContract.test.ts` asserts a **literal** count instead of `N_before + k == N_after` | six of the eight batch specs computed from the same 57 baseline; a literal sends the next builder hunting a phantom regression |
| A wave closed without `/review-impl` | it is a **literal DoD step** in all ten plans, per THE POLICY §2 |
| An authored field reaches no consumer (`motif_application` → `pack()`) | `stored-but-unread ⇒ write-only-behavior`. **This is why X-7 hard-gates Wave 3.** |

---

## 2 · THE SEALED DECISIONS (plan 30 §0 — PO-1..4) — RESTATED, NEVER RE-LITIGATED

> **Do not re-litigate these from memory. Re-read this section.** A sealed decision **proven wrong by
> the code** is one of the four CRITICAL stop-and-ask classes (§3.3) — that is the *only* channel by
> which one of these may re-open, and it re-opens with the PO, not with the builder.

| # | Decision | Consequence, as it binds this build |
|---|---|---|
| **PO-1** | **AMEND spec 28's AN-12** — the "No new GUI surface" clause is **lifted** for `composition_diagnostics` / `composition_package_tree` / `composition_find_references`. | **Wave 7 proceeds.** It wires the **existing** `StudioBottomPanel` Issues tab and makes `find_references` a **right-click lens on an entity badge**. **ZERO new dock panels** (the ledger delta for Wave 7 is **+0**). The amendment is written **into** `28_agent_native_studio.md` — never forked. `composition_package_tree` gets **no** human surface (AN-12's premise holds for *that one*: `D-W7-PACKAGE-TREE-NO-GUI`, gate #5). |
| **PO-2** | **G-WORKFLOWS is DROPPED — Track C owns it** (its P-5 claims "workflow rack, binding UI"). | **Wave 8 loses 8c.** Wave 8 = **KG write holes + world maps only**. The gap stays in the register marked **OWNED-BY-TRACK-C**, never re-raised as a hole. ⚠ The defect is real and is **Track C's to close**: `registry_propose_workflow` tells the model the user approves "in the UI" and there is no UI. |
| **PO-3** | **RETIRE `ui_show_panel`** — fold it into `ui_open_studio_panel` (one name for one concept). | **X-5 is a retirement, not an enum-add** (Wave 0, `W0-S5`). Wave 0's plan **verified** the cross-surface fear is unfounded: `ui_show_panel` has **ZERO working consumers anywhere** (it resolves to `${pathname}?panel=…` and the only `?panel=` reader is `PopoutHost.tsx:27` on the `/composition/popout` route, which the chat is never mounted on). `ui_watch_job` is fixed **separately, via the interceptor** — *not* `STUDIO_UI_TOOLS`, because 4 skill prompts advertise it globally. **DoD (the RUNTIME references are gone — scoped to quoted string literals in non-test source; a hygiene grep that also matches PROSE can never go to zero and would send the builder mangling good comments — `hygiene-grep-literal-token-in-comment-false-positive`):** `grep -rnE "['\"]ui_show_panel['\"]" frontend/src services/ --include=*.ts --include=*.tsx --include=*.py \| grep -v __tests__ \| grep -v '/tests/'` returns **ZERO** lines. *(Explanatory comments naming the retired tool, and the rewritten negative tests asserting `isUiTool('ui_show_panel') === false`, are CORRECT and stay.)* |
| **PO-4** | **All detail specs (31–38) + all HTML drafts FIRST. No implementation before them.** | ✅ **SATISFIED.** Specs 31–38 are on disk; the 11 new drafts are drawn and token-normalized (plan 30 §8.3). The ten BUILD-DETAIL plans are on disk. **This master plan is the last artifact before BUILD.** |

### 2.1 · 🔒 THE SECOND SEAL — **D-1 … D-7**, sealed **2026-07-13** on the finished plan set. **Binding.**

> These are PO rulings on the *ten wave plans*, not on plan 30. They **add three slices**, **add the run's
> ONE sanctioned stop**, and **reverse one won't-port**. Re-read them; never re-derive them.

| # | Decision | Consequence, as it binds this build |
|---|---|---|
| 🔴 **D-1** | **REKEY the corrupted content-language data — but DRY-RUN FIRST.** 5 rows say `Vietnamese` beside 89 saying `vi`, inside `UNIQUE(chapter_id, target_language, version_num)`. | 🔴 **THE ONE CRITICAL-CLASS STOP IN THE ENTIRE BUILD.** Wave T's **`T-C10`** *writes* the migration + a rollback path + a before/after row-count assertion, **runs the DRY-RUN, prints the report — AND STOPS.** **The agent may NOT execute it unattended.** Execution is a separate, PO-supervised act (`D-TRANSL-LANG-REKEY-EXECUTE`). ⇒ Wave T is **no longer "zero migrations"**: it *produces* one destructive migration and *runs* only its dry-run. |
| **D-2** | **WAVE 0 IS THE HOTFIX BATCH — pull the 4th HIGH bug forward.** Translate **silently discards the user's ticked chapters** and substitutes the whole backlog. | 🆕 slice **`W0-S15`** — one line at `TranslationTab.tsx`'s `<TranslateModal>` mount (`preselectedChapterIds={[...selectedChapters]}`; the prop exists and every *other* call site passes it). **Discharges the SELECTION half of Wave T's `T-A4`/`T8` — and nothing else** (`preselectedLang`/D6 stays in Wave T). |
| **D-3** | **ADD THE GLOBAL `MutationCache.onError`.** `App.tsx`'s `QueryClient` has **no `MutationCache`** ⇒ **every failed mutation in the entire FE is silent, forever.** | 🆕 slice **`W0-S16`** — the highest leverage-per-line item in the build. Slice-local `onError` still WINS (no double-toast). *This is why three live bugs survived to an audit.* |
| **D-4** | The content-language SSOT is **`contracts/languages.contract.json`** (mirroring `frontend-tools.contract.json`). | ⚠ **It must NOT be named `languages.yaml`** — `contracts/language-rule.yaml` already exists and means *service → programming language*. **Different axis; one name for two concepts is the drift this repo legislates against.** Binds Wave T's `T-C1`. |
| **D-5** | **Mobile shell — DECIDE AT WAVE 6's CLOSE.** | **GG-4 stays SHUT until then.** Wave 6 ships the **mechanical parity guard**, **not** the deletion of `ChapterEditorPage`. A green gate is **not** an authorization to delete. |
| **D-6** | **`D-COMPOSE-GENERATE-UNGATED` — CARRY it; raise at Wave 3/3c.** | Pre-existing, not a regression of this batch (the user *does* get what they pay for). ⚠ When fixed, fix it **AT THE ROUTE** — never by gating the Regenerate button alone (that would mint a second confirmation convention; **AN-8 seals one-channel-per-object-class**). |
| 🔴 **D-7** | **ADD A `place-graph` SLICE TO WAVE 8** — the legacy `WorldMap.tsx` place-graph was a **CIRCULAR DEFER** (spec 38 said *"Wave 6 owns it"*; **Wave 6 never contained it**) ⇒ no wave built it ⇒ it would have died at the GG-4 gate. | 🆕 slice **`W8-20`**, panel id **`place-graph`** (leaf-reuse `WorldMap.tsx`, de-forked onto W8-02/03's writers). ⚠ **`place-graph` is NOT Wave 8's `world-map` panel**: `world-map` reads **book-service's** `world_maps`/`map_markers`/`map_regions`; `place-graph` reads **`composition_work.settings.world_map`**. **Plan 30 §10 explicitly refutes conflating them.** ⇒ **`D-WORLDMAP-PLACE-GRAPH-WONTPORT` is RETIRED**; the `worldmap` parity row becomes a **real home**, never `{retired}`. Wave 8's panel delta: **+2 → +6**. |

---

## 3 · THE RUN POLICY (binding — quoted verbatim in every wave plan)

```
## THE POLICY THE PO SET FOR THIS RUN (binding — quote it in every plan you write)

1. **This plan is written ONCE, in full, at BUILD DETAIL.** After the QC gate, implementation proceeds
   **autonomously with no further design checkpoints.** So anything you leave vague becomes a stall or a
   guess at 3am. A slice that says "wire the panel" is a FAILURE; a slice says WHICH FILE, WHAT CHANGE,
   WHICH TEST.
2. **`/review-impl` runs at the completion of EVERY wave**, and any bug it finds is fixed before the
   wave closes. Bake it into each wave's Definition of Done as a literal step.
3. **DEFERRAL POLICY — "blocked ≠ stopped".** When the build hits a blocker: write a tracked defer row
   and **KEEP GOING**. Do **not** stop, do **not** ask. A blocker is treated as a DEFER by default.
   **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as exactly one of:
   - a destructive / irreversible action (data loss, a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (§0 PO-1..4 of plan 30),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing** (this repo just shipped one — the
     motif-mine / 拆文 `POST /actions/confirm` returns **HTTP 500 BEFORE the enqueue**: the confirm token
     is burnt and a billing **hold** is reserved, and **the `generation_job` row is never created**.
     ⚠ **NOT a "404 at the poll", and NO USER WAS EVER CHARGED** — no XADD, no worker, no LLM call. The
     fix is the **Work-less job lane** (`W0-BE1`), **not** a job-read route; see C-1).
   Everything else — a missing route, an awkward refactor, a failing third-party thing, an ugly seam —
   is a **defer row + continue**.
4. Every defer row carries: ID, wave/slice of origin, what, the gate reason (CLAUDE.md's 5 gates),
   target wave/trigger. A defer row is never a silent drop.
5. **CLAUDE.md's anti-laziness rule is in force:** "missing infrastructure is NOT blocked — it is unbuilt
   work to implement." A route that does not exist is a route you WRITE. Do not defer it as "blocked"
   unless the dependency is genuinely external to this repo.
```

### 3.1 What the policy already bought, before a line was built

Ten planning agents applied §5 (anti-laziness) and §3 (blocked ≠ stopped) against the **code**, not the
docs. It changed the shape of the build in ten load-bearing places. These are **binding over the specs'
prose** and are recorded here so no builder re-derives them:

| # | Wave | The correction (all verified in source) |
|---|---|---|
| **C-1** | **0** / 3 / 4 | 🔴 **The paid-action defect is WORSE than plan 30 §3.3 says.** The motif-MINE / 拆文 poll does **not** "404" — `GenerationJobsRepo.create()` derives `book_id` via `INSERT…SELECT FROM composition_work`, so `_enqueue_motif_job`'s synthetic `uuid4()` project matches **no row** ⇒ `ReferenceViolationError` ⇒ **`/actions/confirm` 500s AFTER the confirm token is burnt and the billing hold reserved.** The job row is **never created**. Re-pointing the poll fixes **nothing**, and **a read route over a row that is never written 404s forever.** ⇒ **BE-7c goes XS → M** (DDL: `DROP NOT NULL` on `project_id`/`book_id` + a both-or-neither shape CHECK + a partial index + a `create_unbound()` writer + the owner-gated read). 🔴 **ALL SIX PARTS ARE BUILT IN WAVE 0 (`W0-BE1`)** — it is a CRITICAL (paid-action) class that fires today, **and `W0-S7`'s live smoke cannot pass without the writer.** The canonical build detail lives in **Wave 3's `3a-1`**; `W0-BE1` builds from it by reference. **Wave 3 / `3a-1` is VERIFY-OR-BUILD** (pre-flight G4: if `create_unbound` exists ⇒ skip). **Wave 4 `W4-BE3` likewise verifies, and builds only if absent.** ⚠ **The migration therefore lands in WAVE 0, not Wave 3** (§9). |
| **C-2** | 0 | **X-4's "~15 handlers in Wave 0" is NOT BUILDABLE** — a handler's only job is invalidating **its panel's** query keys, and those panels don't exist yet. Plan 30 §8.0b already says so. Wave 0 ships the **one genuinely-stale domain** + **2 mechanical guards** (no-metachar-string-pattern; no-double-fire) that make the other 13 safe to add in the wave that builds their panel. |
| **C-3** | 0 | **X-3's proposed assertion (`every(p => !!p.guideBodyKey)`) is GREEN ON A LIVE BUG.** Four shipped `quality-*` panels declare a `guideBodyKey` whose `en` key does not exist ⇒ `UserGuidePanel.tsx:120`'s `t(key,{defaultValue:''})` renders a **blank** body today. **Assert the EFFECT (the key resolves), not the declaration.** 5 bodies × 18 locales backfilled. |
| **C-4** | 2 | 🔴 **`StructureRepo.span()` MUST NOT be "cleaned up".** Its third caller is the **packer** (`lenses.py:322 → _arc_position`), which compares min/max against the scene's **raw strided** `story_order` (stride 1000). Dense-ranking it clamps every prompt to "~100% through arc X" — and `gather_arc`'s degrade-safe `except: return ''` **swallows it**, so the unit suite stays green. **BE-A1 fixes the ROUTES only** (`arc.py:455` + `server.py:4255`), and `W2-S1` pins `span()`'s exact raw keys **and values** against a real DB. |
| **C-5** | 5 | **BE-2's autofix route is NOT a 202 ack.** `handoff_autofix` loops synchronously and always returns `{rounds, run}`. Following spec 35's prose would ship an FE reading a `job_id` that is not there — the user has **already paid** for the LLM rounds. Pinned by `test_autofix_returns_rounds_and_run_not_an_ack`. |
| **C-6** | 5 | **`features/plan-forge` does NOT use react-query.** It is hand-rolled `useState`/`useEffect`. `planEffects.ts` calls `queryClient.invalidateQueries`, which **cannot reach hand-rolled state** — registering it as-specced ships a handler that passes its own unit test and does **nothing live**. `W5-PS-14` migrates the three plan-forge server reads to react-query **first**. |
| **C-7** | 6 | **`confirm_action`'s Work-scoped tail ends in an UNCONDITIONAL `return await _execute_conformance_run(...)`.** Adding `composition.decompose` to `_ALL_DESCRIPTORS` without an explicit dispatch branch **silently runs the CONFORMANCE effect on a PAID action.** The fallthrough becomes explicit + a terminal 400, guarded by `test_an_unknown_work_scoped_descriptor_400s_and_does_NOT_run_conformance`. |
| **C-8** | 6 | **Spec 36's M3 DoD demands a repo-wide `candidates[0]` hygiene test that REDS on day one** against 5 legitimate unrelated sites (prosemirror positions, a glossary display fallback, a model list). The next agent would **delete the guard to get green**. It must be **directory-scoped** to the 4 dirs holding the 11 real work-resolution sites. |
| **C-9** | 8 | **`kg_create_node`'s `kind` has THREE schema sources** (pydantic arg model · the OpenAI JSON schema · the FastMCP function signature — **FastMCP generates from the SIGNATURE and STRIPS the pydantic model**). Spec 38 names one. Editing one third leaves the agent still able to send `kind:"item"`. All three + one 4-assertion drift-lock. |
| **C-10** | T | 🔴 **T9 needs ZERO backend work.** book-service **already** computes and returns the caller's effective grant on every book read (`access_level`, `server.go:956-957`, emitted at `:987`) — and `grep -rn "access_level" frontend/src` returns **ZERO hits**: the field crosses the wire today and the frontend throws it away. book-service **drops out of Wave T entirely**. ⚠ **Do NOT mint the name `my_grant_level`** — that is two names for one concept, the exact defect plan 30 §8.0 killed for `references`/`reference-shelf`. |

---

## 4 · THE SEQUENCE

### 4.1 The wave table

| Wave | Plan file | Size | Slices | **HARD GATE — what must be green first** | What it unblocks | Parallel with? |
|---|---|---|---|---|---|---|
| **0 · Foundations** | `…-wave-0-foundations.md` | **L** | **22** *(20 + `W0-S15`/`W0-S16` — PO `D-2`/`D-3`)* | **None** — it *is* the gate. Pre-flight only: `git status` on Track C's 4 files (§8) must be **clean** for `W0-S11` (X-10); if dirty ⇒ **DEFER `D-X10-ANC2-SCENT` and keep going**. | **Everything.** X-1 · X-2 · X-3 · X-5 · X-7 · **BE-7c IN FULL** (`W0-BE1` — DDL + `create_unbound()` + `_enqueue_motif_job` + the owner-gated read; **the writer is NOT optional — `W0-S7`'s live smoke cannot pass without it**, C-1) | **Wave T** (fully disjoint) |
| **T · Translation repair** | `…-wave-T-translation-repair.md` | **L** | **24** (3 phases; +`T-C10`, PO `D-1`) | **NONE. Fully parallel — schedule it into ANY free lane, at any time.** 00C Q-1: *"disjoint files from the whole 00B cluster."* Pre-flight confirmed no other agent is in translation/book-tabs/languages files. | Nothing (leaf) · **0 panels · 0 routes** ⇒ ledger delta **+0**, `catalog.ts`/`frontend_tools.py`/the contract JSON are **never touched**. 🔴 **NOT "0 migrations" any more — PO `D-1` (§2.1) puts ONE DESTRUCTIVE migration here (`T-C10`): WRITTEN + DRY-RUN ONLY, never executed by the agent. It is the run's ONE sanctioned STOP.** | **Every wave.** This is the filler lane — if any wave stalls, Phases A/B/C slot straight in (T-B4, T-C1, T-C6 have **no dependencies** and exist for exactly this). |
| **1 · Quality completion** | `…-wave-1-quality.md` | **L** | **20** | 🔴 **X-2 HARD-GATES WAVE 1.** `CATEGORY_ORDER` (`useStudioCommands.ts:20-22`) lists **9**; `catalog.ts:81-91` defines **10** — `'quality'` is missing ⇒ `indexOf → -1` ⇒ it sorts **ABOVE `editor`**. Wave 1 lands **four** panels into that category. Also needs **X-3** (guideBodyKey **effect**) and **X-1** (AddModelCta). *If Wave 0 has not landed at pre-flight, Wave 1's `W1-00`/`W1-01` build them — with an explicit "if green, SKIP, do not double-implement".* | **CREATES `compositionEffects.ts`** (Wave 6 extends it) · the spec-16 M1 prerequisites (progress + canon/heal/corrections ports) | **Wave 2** (disjoint: quality panels + `compositionEffects.ts` vs arc + `arcEffects.ts` + book-service) · **Wave T** |
| **2 · Arc inspector** | `…-wave-2-arc-inspector.md` | **L** | **14** | **X-6** (AN-12 `resource_ref`, Wave 0) for the deep-link. `W2-S0` builds `GET /v1/books/{id}/my-access` (Go, ~40 LOC) — the mock's VIEW-only state was **unbuildable** without it. | **24-H3.1** (PlanDrawer's arc variant) · **CREATES `arcEffects.ts` with ONE broad `/^composition_arc_/`** (Wave 4 **extends its handler body**) · hands spec 29-T9 its dependency | **Wave 1** · **Wave T** · 🔴 **NOT Wave 3b** — both edit `PlanDrawer.tsx` (§8) |
| **3 · Motif studio** | `…-wave-3-motif.md` | **XL** | **15** (3 milestones: 3a·3b·3c) | 🔴🔴 **X-7 (`gather_motifs`) HARD-GATES WAVE 3.** Verified at HEAD: `grep -rn "motif" services/composition-service/app/packer/` → **ZERO hits**. Without it the author binds 打脸 to ch.41 and **the drafter is never told** — the wave ships **decoration**, a beautiful editor for a field with no consumer. **The gate is not the lens: it is the 4-call-site EFFECT test** (`engine.py:391/767/973` + `grounding.py:103`), because BA12's wiring bug already shipped once with a green unit suite. | the shared components Wave 4 imports (`MotifStateBoundary`, `CostConfirmCard`, `AdoptTargetModal`, `MatchReasonChip`) · **M-BUG-4** (the `arc_template_id`→`arc_id` drift Wave 4 depends on being fixed). ⚠ **BE-7c is NOT this wave's to build — Wave 0 owns it (C-1); `3a-1` is VERIFY-OR-BUILD.** | 3a/3c ∥ **Wave 1** · **Wave T**. 🔴 **3b must follow Wave 2** (`PlanDrawer.tsx`, `NodeBadges.tsx`). |
| **4 · Arc templates + 拆文** | `…-wave-4-arc-templates.md` | **L** | **17** | **BE-7c present** (built in **Wave 0 / `W0-BE1`**; re-verified at Wave 3 / `3a-1`) — pre-flight cmd 4. **If absent ⇒ `W4-BE3` BUILDS IT** (it is the paid-action class; do not ship the wave without it). **`arcEffects.ts` exists** (Wave 2) — **EXTEND its body, never register a second pattern.** **X-1** for the zero-model state. | — | **Wave 5 BE** · **Wave 8a** · **Wave T** |
| **5 · PlanForge made human** | `…-wave-5-planforge.md` | **L** | **19** | 🔴 **X-1 (AddModelCta DOCK-7) gates every PANEL slice** — every paid action here needs a ModelPicker whose empty state today is a raw `<Link>` that **tears down the whole dockview layout**. **The 6 BE slices (S1–S6) are unaffected and can proceed regardless.** | — | **BE slices: anything.** Panels: after X-1. ∥ **Wave 4** · **Wave 8a** · **Wave T** |
| **6 · Editor-craft ports** | `…-wave-6-editor-craft.md` | **L** | **22** (M0–M7) | **`compositionEffects.ts` exists** (Wave 1 — extend, never fork). **Waves 1–5's panels landed** (the `legacyParityContract` rows are `PENDING Wave N` placeholders — flip each as its wave lands; `D-GG4-PARITY-ROWS-PENDING`). | 🔴 **WAVE 6 GATES THE SPEC-16 RETIREMENT (GG-4).** When Wave 6 closes — **and only then** — `ChapterEditorPage` may be retired. Retiring earlier **DELETES shipped features**. ⚠ M5 ships the **MECHANICAL parity guard**, *not* the deletion: `D-STUDIO-MOBILE-SHELL` is a **hard blocker on deletion** and is a PO decision (§10). | **Wave 7** · **Wave 8** · **Wave T** |
| **7 · Issues feed** | `…-wave-7-issues-feed.md` | **M** | **17** | **PO-1** (sealed — AN-12 amended). **X-1** for the Run-conformance button (`D-W7-RUN-BUTTON-X1`) — without it the row still renders and still states the fact, but the button does not ship. | — | **Wave 6** · **Wave 8** · **Wave T** |
| **8 · KG + world** | `…-wave-8-kg-world.md` | **XL** | **22** (8a = M · 8b = L; +`W8-20` — PO `D-7`) | **8a (KG holes): none** — knowledge-service, disjoint. **8b (world container + maps):** the **Track C P-5 ownership note** (`W8-00`, a ~10-minute write-down — **verified: Track C's P-5 is PARKED with NO design and NO code**; `grep "'world'" catalog.ts` → zero hits; spec 38 HAS the design). **An ownership question is not one of the 4 CRITICAL classes — do not stall on it.** | **Nothing** (it is the last wave) ⇒ 🔴 **there is no next wave to defer a bug into. `/review-impl` findings are FIXED, full stop.** | **8a ∥ any composition wave** (different service) · **Wave T** |

### 4.2 The four call-outs, stated explicitly

- 🔴 **X-7 (`gather_motifs`) hard-gates Wave 3.** Not advisory. Without the lens **and its 4-call-site
  effect test**, the entire motif cluster (library · binding · suggest · conformance) is a GUI for data
  `pack()` never reads.
- 🔴 **X-2 (`CATEGORY_ORDER` ∋ `'quality'`) hard-gates Wave 1.** The failure modes are **inverted** — a
  *missing* category sorts LAST, an *unlisted* one sorts **FIRST**. `panelCatalogContract.test.ts:40`
  asserts a category is **present**, not that it is a **member of `CATEGORY_ORDER`**. Add the membership
  assertion, or the next new category silently jumps to the top of the palette.
- 🔴 **Wave 6 gates the spec-16 retirement (GG-4).** Every LEGACY-ONLY gap lives on `ChapterEditorPage`.
  Retiring it before the ports land deletes style/voice, references, motif library, arc templates,
  divergence, progress, correction capture, and polish/self-heal. **And even after Wave 6, deletion is
  blocked on `D-STUDIO-MOBILE-SHELL`** — the Studio has **no mobile editing surface**.
- 🟢 **Wave T (translation repair) is fully parallel — schedule it into any free lane.** Zero panels,
  zero routes, provably disjoint files. It is also the **stall-filler**: if any wave blocks, its
  dependency-free slices (T-B4, T-C1, T-C6) slot straight in. *"Blocked ≠ stopped"* has a lane to move
  into. 🔴 **But it is NOT "zero migrations" any more** — PO **`D-1`** (§2.1) puts the **destructive
  `Vietnamese` → `vi` rekey** in `T-C10`: **written + dry-run ONLY**, and **`T-C10` STOPS AND ASKS.** It
  is the **only** stop in the whole ten-wave run.

### 4.3 Lane-B effect-handler ownership — ONE FILE PER DOMAIN (plan 30 §8.0b)

`matchEffectHandlers` returns **EVERY** match and `runEffectHandlers` **awaits ALL** of them. Two files
for one domain does **not shadow — it DOUBLE-FIRES.**

| Tool family | File | **CREATES** | **EXTENDS (body only — never a 2nd registration)** |
|---|---|---|---|
| `composition_arc_*` | `arcEffects.ts` | **Wave 2** (one broad `/^composition_arc_/`) | **Wave 4** (adds the `arc-templates` query keys) |
| `composition_*` (canon, corrections, style, voice) | `compositionEffects.ts` | **Wave 1** | **Wave 6** |
| `composition_motif_*` | `motifEffects.ts` | Wave 3 | — |
| `plan_*` | `planEffects.ts` | Wave 5 | — |
| `composition_diagnostics` | `diagnosticsEffects.ts` | Wave 7 | — |
| `world_map_*` / `memory_*` | `worldEffects.ts` | Wave 8 | — |

⚠ **`registerEffectHandler`'s string branch is `tool === p || tool.startsWith(p)` — it is NOT a pattern
match.** A string with alternation matches **NOTHING** and ships a **silent no-op** that no unit test
(which registers and calls its own fake) can catch. **Use a `RegExp`.** Every wave's lock is
`matchEffectHandlers('<a real tool name>').length === 1` — `toHaveLength(1)`, never `toBeTruthy()`.

### 4.4 The dependency graph

```
                    ┌───────────────────────────────────────────────────────┐
   WAVE 0  ─────────┤ X-1 · X-2 · X-3 · X-5 · X-6 · X-7 · BE-7c IN FULL     │
   (22 slices, L)   │  W0-BE1 = DDL + create_unbound() + _enqueue + read     │
   +W0-S15 (D-2)    │  W0-S15 = Translate's dropped selection (1 line)       │
   +W0-S16 (D-3)    │  W0-S16 = the GLOBAL MutationCache.onError             │
                    │  ⚠ W0-S7 (the 404 kill + its LIVE SMOKE) NEEDS W0-BE1  │
                    └──┬──────────┬───────────┬──────────┬───────────┬──────┘
                       │          │           │          │           │
            X-2,X-3,X-1│      X-6 │       X-7 │      X-1 │    BE-7c  │
                       ▼          ▼           ▼          ▼           │
                  WAVE 1     WAVE 2      WAVE 3     WAVE 5(panels)   │
                 (quality)  (arc-insp)  (motif,XL)  (planforge)      │
                creates       creates   3a-1=VERIFY   ▲ BE slices    │
            compositionEffects arcEffects  -OR-BUILD    run anytime  │
                     │          │            │                       │
                     │          └──▶ 3b (PlanDrawer — MUST follow Wave 2)
                     │          │                                    │
                     │          └──────────▶ WAVE 4 (arc-templates + 拆文)
                     │                        extends arcEffects     │
                     │                        W4-BE3 = VERIFY ◀──────┘
                     │                        (BE-7c already built in W0)
                     │
                     └──────────────────────▶ WAVE 6 (editor-craft, 22)
                                              extends compositionEffects
                                              +5 panels (incl. scene-compose,
                                                         chapter-assemble)
                                              W6-M5 = the GG-4 gate, MECHANIZED
                                                      │
                                                      │ 3 rows ship {pending: Wave 8}
                                                      │ (cast · arc · flywheel)
                                                      │ it.fails() is RED — BY DESIGN
                                                      ▼
   WAVE 7 (issues feed, 17) ◀── PO-1 (SEALED) + X-1   │  ── runs after/∥ Wave 6
                                                      │
   WAVE 8 (KG + world, 22) ◀── 8a: free · 8b: W8-00   │  ── 8a ∥ anything
        W8-16/17/18/20 = cast · character-arc · canon-growth · place-graph
                     └──── FLIP the 4 pending rows ───┘   (place-graph = PO D-7)
                           W8-20 (NOT W8-18) converts it.fails → it
                                                      │
                                                      ▼
                                          ═══ GG-4 GATE (mechanically GREEN) ═══
                                     spec-16 ChapterEditorPage RETIREMENT
                                   🔴 STILL BLOCKED on D-STUDIO-MOBILE-SHELL (E-3)
                                      + spec 16's Phase-4b "kept indefinitely"
                                   ⇒ NO WAVE DELETES THE PAGE. Green ≠ authorized.

   ∥∥∥ WAVE T (translation repair, 24) ── FULLY PARALLEL, ANY LANE, ANY TIME ∥∥∥
        └── T-C10 (PO D-1) = the DESTRUCTIVE rekey: WRITE + DRY-RUN + 🔴 STOP.
            The ONE sanctioned stop of the entire run. NEVER executed unattended.
```

**Acyclic — and the board's order (0→1→2→3→4→5→6→7→8, T anywhere) is a valid topological sort of it.**
A builder who simply walks the RUN-STATE slice board top-to-bottom satisfies every edge above:
`BE-7c` before `W0-S7`; X-2/X-3/X-1 before Wave 1; X-6 before Wave 2; X-7 before Wave 3;
Wave 2 before 3b **and** before Wave 4 (`arcEffects.ts`); Wave 1 before Wave 6 (`compositionEffects.ts`).
**And inside every wave: the CONTRACT slice precedes that wave's first FE slice, and every migration
precedes the code that reads its column.**

🔴 **THE ONE EDGE THAT RUNS BACKWARD — and it is handled, not broken.** Wave 6's `W6-M5` mechanizes the
GG-4 gate over an **exhaustive `Record<SubTab, Home>`** (a missing key is a **TS error**). But 🔴 **FOUR** of
its 25 rows (`cast` · `arc` · `flywheel` · **`worldmap`** — the last added by PO **`D-7`**) are homed by
**Wave 8**, which runs **after** Wave 6. Their panels do not exist when the test first runs. **This is NOT a
cycle** — it is a *deferred obligation*, and it is expressed as one: those rows ship as
**`{ pending: 'Wave 8 / W8-1x|W8-20' }`**, and `it.fails('GG-4: zero pending rows')` is **RED at Wave 6's
close, BY DESIGN — that is the gate HOLDING.** `W8-16/17/18/20` flip them; 🔴 **`W8-20` — the LAST flip, not
`W8-18` — converts the `it.fails` to an `it`.**
⚠ **The trap this closes is the one the master's own C-8 names:** *a red exhaustive guard tempts the next
agent to delete it, or to give a row a FALSE home to go green.* **A false home makes the gate go GREEN on a
feature being DELETED.** So: **never re-point a row at a panel that is not the thing** (`flywheel` is **not**
`quality-corrections` — two services, two datasets; `arc` is **not** `arc-templates` — two different arcs),
and **never demote a `{pending}` to a `{retired}`** to silence it.
🔴 **`worldmap` IS NOT `{retired}` — REVERSED BY PO DECISION `D-7` (§2.1), 2026-07-13.** This paragraph used
to read *"`worldmap` is the one genuine `{retired:…}` — a reviewed won't-port; there is NO `place-graph`
panel and NO wave builds one."* **That was a CIRCULAR DEFER** (spec 38 → *"Wave 6 owns it"* → **Wave 6 never
contained it** → **no wave builds it** → **it dies at GG-4**), and the PO reversed it. ⇒ **`worldmap` is a
FOURTH `{pending}` row** (`place-graph`, **`W8-20`**), `D-WORLDMAP-PLACE-GRAPH-WONTPORT` is **RETIRED**, and
**`W8-20` — not `W8-18` — is the slice that flips the LAST row and converts `it.fails` → `it`.**
⚠ **`place-graph` ≠ `world-map`** — two panels, two services, two id spaces (`composition_work.settings.world_map`
vs book-service's `world_maps`; plan 30 §10 refutes conflating them). **Demoting `worldmap` back to
`{retired}` to get a green suite silently re-installs the exact drop the PO reversed.**

---

## 5 · THE CUMULATIVE PANEL-ENUM LEDGER (plan 30 §8.0)

**HEAD `9262ed53e`: 57 openable == 57 py enum == 57 contract enum. Zero drift. Keep it that way.**

| After wave | Panels added | Ids | **OPENABLE == py enum == contract enum** |
|---|---:|---|---:|
| **HEAD `9262ed53e`** | — | — | **57** |
| **0** (foundations) | **0** | *(retires `ui_show_panel`; adds no panel)* | **57** |
| **T** (translation) | **0** | *(never touches `catalog.ts`)* | **±0 — a no-op on the ledger, in any lane** |
| **1** (spec 31) | **+4** | `quality-canon-rules` · `quality-corrections` · `quality-heal` · `progress` | **61** |
| **2** (spec 32) | **+1** | `arc-inspector` | **62** |
| **3** (spec 33) | **+2** | `motif-library` (3a) · `quality-conformance` (3c) | **64** |
| **4** (spec 34) | **+1** | `arc-templates` | **65** |
| **5** (spec 35) | **+1** | `plan-passes` | **66** |
| **6** (spec 36) | 🔴 **+5** | `style-voice` · **`reference-shelf`** *(NOT `references`)* · `divergence` · **`scene-compose`** · **`chapter-assemble`** *(the last two HOME the orphaned `compose`/`assemble` legacy sub-tabs — without them GG-4 **deletes the compose loop**)* | **71** |
| **7** (spec 37) | **0** | *(wires the existing `StudioBottomPanel` + a right-click lens — PO-1/AN-12)* | **71** |
| **8** (spec 38) | 🔴 **+6** | `world` · `world-map` · **`cast`** · **`character-arc`** · **`canon-growth`** · 🔴 **`place-graph`** *(the last FOUR HOME the orphaned sub-tabs **and FLIP Wave 6's four `{pending}` GG-4 rows**; `place-graph` = PO **`D-7`**, `W8-20`)* ⚠ **`place-graph` ≠ `world-map`** — two services, two tables, two id spaces. | **77** |

🔴 **THESE NUMBERS ARE A PLANNING AID, NOT A TEST ASSERTION.**
**Six of the eight batch specs computed their target from the same 57 baseline as if each were the only
wave.** The waves are **sequential** and the counts **cumulative**. A DoD pinned to a literal sends the
next builder hunting a **phantom regression** if a wave is re-ordered or dropped.

⚠ **AND THIS TABLE ITSELF WENT STALE ONCE — read the lesson, not just the number.** It said `6 → +3 → 69`
and `8 → +2 → 71` (**total 71**). Both were written *before* the plans homed the seven orphaned legacy
sub-tabs, which added **2 panels to Wave 6** and **3 to Wave 8** — and then PO **`D-7`** homed a **fourth** in Wave 8 (`place-graph`). **The true total is 77 (+20).** The
cumulative table is exactly the artifact that rots when a wave grows — **which is why NO DoD may cite it.**
🔴 **If a literal and a delta ever disagree again, THE DELTA WINS. Assert `N_before + k`, always.**

> **EVERY wave's DoD asserts `N_before + k == N_after` AND the three-way equality. NEVER a literal.**

### The two machine drift-locks — GREEN AFTER EVERY WAVE, no exceptions

```bash
# lock 1 — enum == openable, sorted equality; + X-2 membership; + X-3 guideBody EFFECT (must RESOLVE)
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts

# lock 2 — CLOSED_SET_ARGS ⇒ must be an enum; the contract JSON is REGENERATED, never hand-edited
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
# regenerate (and commit the JSON in the SAME commit as catalog.ts + frontend_tools.py):
cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py
```

**`contracts/frontend-tools.contract.json` is NEVER hand-edited or hand-merged after a rebase.
REGENERATE. Every wave in this batch touches it.**

---

## 6 · THE CROSS-CUTTING DoD — applied at EVERY wave, in this order

A wave is **not done** until all six are true. Each is a **literal step**, not a disposition.

| # | Step | The evidence string that closes it | Why it exists (the bug it caught) |
|---|---|---|---|
| **1** | **Suites green — as DELTAS, counted, and PASTED** | *"composition 2355 → 2372 passed (17 new); frontend 152 → 178 passed"*. Integration tests must show **`passed`**, not **`skipped`** — an env-gated test that SKIPs is **not** a passing test. | `env-gated-integration-tests-skip-and-the-green-suite-lies` (1740 unit green while 106 real-SQL red). New DB-touching test files **MUST** carry `pytestmark = pytest.mark.xdist_group("pg")` or parallel workers interleave and the counts lie. |
| **2** | **The two machine drift-locks green** (§5) | *"57 + 4 == 61 == 61 == 61 (three-way)"* — **the delta form, never a literal.** | Six of eight specs got the baseline wrong. |
| **3** | 🔴 **LIVE BROWSER SMOKE on a REBUILT image** | A Playwright run driven via `evaluate` + `data-testid` (dockview refs go stale), against the **baked `:5174` nginx build** — **rebuild the image first**, or use `vite dev` on **`:5199`**. A host `vite dev` on `:5174` **SHADOWS** the baked build and the smoke then proves nothing about what ships. | `agent-gui-loop-needs-live-browser-smoke-not-raw-stream` · `live-smoke-rebuild-stale-images-first` · `frontend-5174-is-baked-prod-nginx-not-vite`. **A green unit suite does not prove the loop closed.** Prefer a **local lm_studio** model — $0 spend. |
| **4** | 🔴 **`/review-impl` on the wave's diff — and EVERY bug it finds is FIXED before the wave closes** | *"`/review-impl` run; N findings; all N fixed in `<commits>`"* — **THE POLICY §2, a literal step.** Not "reviewed, findings noted". | Author blindness makes POST-REVIEW self-review a rubber stamp. Wave 8 is last — **there is no next wave to defer into.** |
| **5** | **`docs/sessions/SESSION_HANDOFF.md` updated** — the ▶ NEXT block overwritten; new defer rows added; cleared rows moved to "Recently cleared". Plan 30's wave row updated. | *"handoff ▶ NEXT rewritten; D-XXX added; DBT-06 cleared"* | *"Work not recorded in SESSION_HANDOFF and committed to git does not exist for the next session."* |
| **6** | **COMMIT — enumerated paths only** | `git status` **and** `git diff --cached --name-only` **before every commit**; `git commit -- <explicit paths>`. **NEVER `git add -A`.** | Three tracks share this checkout. `git commit -- <path>` commits the **WORKING TREE, not the index** — and the index may already carry a concurrent session's pre-staged changes. The SESSION update lands **in the same commit** as the code. |

**Plus, per new panel — GG-8's 9-step registration checklist (plan 30 §8):** component (`data-testid="studio-<id>-panel"`) · `catalog.ts` row (`category` **∈ `CATEGORY_ORDER`** + `guideBodyKey`) · `en/studio.json` (3 keys) · **17 locales via `python scripts/i18n_translate.py` — NEVER hand-written** (and **add** keys, never **edit** them: the tool **gap-fills only**, so an edited `en` string leaves 17 stale locales forever, and a SOFT untranslated flag does **not** self-heal) · `frontend_tools.py` (enum **+** the description gloss — the model's only hint) · **regenerate** the contract JSON · `studioLinks.ts` (cond.) · **the Lane-B handler (MANDATORY for this batch)** · tours (cond.).

---

## 7 · THE DEFER REGISTER

### 7.1 THE POLICY, restated where the builder will actually hit it

> **A blocker becomes a defer row and the run CONTINUES. Only a CRITICAL blocker stops it.**
> **STOP AND ASK for exactly these four — nothing else:**
> 1. **A destructive / irreversible action** — data loss; a migration that **drops or rewrites user rows**.
>    🔴 **THE RUN CONTAINS EXACTLY ONE, AND IT IS PRE-KNOWN: PO decision `D-1` (§2.1) — Wave T's `T-C10`,
>    the `Vietnamese` → `vi` content-language REKEY.** `T-C10` **writes** the migration + the rollback +
>    the row-count assertions, **runs the DRY-RUN, prints the report — and STOPS.** 🔴 **The agent may NOT
>    execute it unattended.** *(The PO's advance approval of the **plan** is **not** approval of the
>    **dry-run output** — that is a separate, explicit act: `D-TRANSL-LANG-REKEY-EXECUTE`.)*
> 2. **A sealed decision proven wrong by the code** (§2, PO-1..4).
> 3. **A tenancy / security breach** — cross-user data exposure.
> 4. **A paid-action defect that would charge the user for nothing** — *this repo just shipped one* (the
>    motif-mine / 拆文 confirm **500s BEFORE the enqueue**, after burning the confirm token and reserving
>    a billing hold; **the job row is never created**). ⚠ **NOBODY WAS EVER CHARGED** — no XADD, no worker,
>    no LLM call. A burnt token + a dangling hold is a real defect; *"the user pays and watches a spinner
>    forever"* is **not**, and is retracted. **This is why the Work-less job lane (`W0-BE1`) is IN SCOPE and
>    not deferrable — and why a job-READ route alone does not fix it** (it would read a row that is never
>    inserted, and would **ship green** on a hand-seeded fixture:
>    `fixtures-can-seed-a-field-the-writer-never-sets`).
>
> **Everything else — a missing route, an awkward refactor, a failing third-party thing, an ugly seam —
> is a defer row + continue.** And *"missing infrastructure" is NOT "blocked" — it is unbuilt work you
> WRITE (CLAUDE.md's anti-laziness rule). A route that does not exist is a route you write.*
>
> ⚠ **"Sealed decision" (#2) means EXACTLY plan 30 §0's PO-1..4 — and nothing else.** A *spec's internal
> invariant*, a plan's assumption, or a slice's premise turning out to be false is **not** a sealed
> decision. It is a **wrong plan** ⇒ **DEFER + CONTINUE**. *(QC caught this exact mis-mapping: Wave 3's
> `3a-3` probe was labelled "critical category #2" and would have stalled the unattended run over a
> UNIQUE index that simply cannot build.)*
>
> ⚠ **#4 is about SHIPPING a new paid-action defect — not about ENCOUNTERING the known one.**
> `W0-BE1` **is the fix** for the known one. **Build it. Do not stop and ask about it.**
>
> **Three live examples of the gate working, all already exercised in planning:**
> - Wave 8's `W8-00` (Track C ownership of the `world` container): **an ownership question is not one of
>   the four.** It is a 10-minute write-down, **not a stall**.
> - Wave 0's BE-7c 500 (the paid-action defect): **the PO already knows** — it is *why* BE-7c was pulled
>   into `W0-BE1` — so it is *the same defect*, not a new one. **Build it. Do not stop and ask.**
> - Wave 3's G5 probe returning rows: **park `D-MOTIF-APPLICATION-MULTI-ROW`, skip `3a-3`, keep going.**

### 7.2 The live register — 67 rows opened by the ten wave plans

**Gate reasons** (CLAUDE.md): **1** out-of-scope · **2** large/structural · **3** naturally-next-phase ·
**4** blocked/needs-evidence · **5** conscious won't-fix.

| ID | Origin | What | Gate | Target / trigger |
|---|---|---|---|---|
| `D-X4-WAVE-HANDLERS` | W0-S4 | The 13 remaining Lane-B handlers. **NOT deferrable work — DISTRIBUTED work** (§8.0b assigns each file to the wave that builds its panel). | 3 | Waves 1/2/3/5/7/8 |
| `D-X9-WEBSEARCH-UNPREFIXED` | W0-S9 | `web_search` registered unprefixed while glossary registers `glossary_web_search`. **Deliberate supersession** — renaming breaks it. | 5 | Never. Recorded. |
| `D-X10-ANC2-SCENT` | W0-S11 | **CONDITIONAL** — the AN-C2 discovery scent in `book_context_note`. Only if the build-time re-verify shows Track C's 4 files dirty. *(At plan time they are CLEAN ⇒ this row should never open.)* | 4 | After Track C lands |
| `D-X12-PANEL-PARAMS` | W0-S5 | A `params` arg on `ui_open_studio_panel`. **ADJUDICATED: NO, not needed** — all 14 panels are bare-id openable; param-panels are reached by a param-carrying tool (`ui_watch_job`). | 5 | Only if a wave finds a panel that is neither |
| `D-QUALITY-GUIDEBODY-ROT` | W0-S2 | ✅ **OPENED AND CLOSED in Wave 0.** 4 shipped panels declared a `guideBodyKey` whose i18n key never existed. **The lesson is the guard: assert the EFFECT, not the declaration.** | — | ✅ Cleared |
| `D-31-PROPOSE-EDIT-CORRECTION` | W1 (OQ-1/F-Q4) | Studio-Compose `propose_edit` records no correction — no `job_id`, prose came from a **chat-service** turn. **v1 = accept: the flywheel learns from structured generation only.** | 2 | When Compose's prose path is specced |
| `D-31-HEAL-CORRECTION-KIND` | W1 (OQ-2) | `heal_accept`/`heal_reject` correction kinds. A CHECK migration that trips `migration-check-constraint-must-backfill-all-historical-blocks`. | 5 | Only with a learning-side consumer |
| `D-31-SELFHEAL-COST-GATE` | W1 (OQ-3) | Run Polish / Analyze quality / Coverage are **paid, unestimated**. Fix = descriptors on the **generic** action spine. **Do NOT invent `/self-heal/estimate` — three such routes already 404 in production.** | 2 | A cost-gate pass over the paid quality actions |
| `D-31-DISMISS-MCP` | W1 (OQ-4) | The human can dismiss a false-positive canon violation; the agent cannot. GG-2 inverse. | 1 | Any wave touching the composition MCP surface |
| `D-31-CORRECTION-DRILLDOWN` | W1 (BE-9d) | Per-row corrections drill-down. **Check learning-service's `GET /v1/learning/corrections` first** — two lists over the same rows is one-name-one-concept. | 1 | If asked for |
| `D-31-REVERTALL-CAPTURE` | W1-15 | `revert_all` records no corrections. Semantically right, **and** it dodges an unmeasured burst (dozens of `GENERATION_CORRECTED` events in one txn). learning-service's burst behaviour is **UNREAD**. | 4 | Measure, then decide |
| `D-31-BE-18-SETTINGS-OCC` | W1 (inherited) | `PATCH /works/{pid}` REPLACES the `settings` blob with no If-Match ⇒ a lost-update window. | 1 | plan-30's BE-18 |
| `D-31-LEGACY-POLISH-DIRTY` | W1 (F18) | 🔴 The **legacy** page has the bug the Studio is fixing (`setContent` suppresses `onUpdate` ⇒ Apply may not dirty ⇒ ⌘S saves nothing). | 1 | **Wave 6** (or fix now if the retirement slips) |
| `D-31-CANON-UPDATE-MCP-PARTIAL` | W1 (F3) | `composition_canon_rule_update` takes only `text`+`active`; the human (post-wave) can edit every field. GG-2 inverse **this wave reveals**. | 1 | Next composition-MCP wave. **Cheap — take it opportunistically.** |
| `D-ARC-TRACKS-ROSTER-SCHEMA` | W2-S6 | `tracks`/`roster` are free-form blobs at **both** doors; the server accepts a keyless entry that corrupts the cascade. | 2 | Its own spec |
| `D-ARC-ARCHIVE-CHAPTER-STRANDING` | W2-S6 | Archiving an arc **strands its chapters** (in neither the archived lane nor the unassigned tray). Should `archive()` cascade an unassign? | 2 | Its own spec |
| `D-ARC-DELETE-BLAST-COUNT` | W2-S6 | `DELETE /arcs/{id}` returns no subtree count (OUT-5 silent blast radius). | 5 | On a 2nd consumer |
| `D-ARC-STATUS-DERIVED` | W2-S5 | Should `structure_node.status` be derived? **No engine branches on it.** **Do not derive it on a guess.** | 5 | On a consumer |
| `D-ARC-SUGGEST-BUTTON` | W2-S5 | *Suggest an arc* — **not FE-only**: no REST route ⇒ a 403 from the BFF allowlist. **Lands with its backend.** | 1/3 | **Wave 4** |
| `D-PLANDRAWER-FINDREFS-COPY` | W2-S9 | `PlanDrawer.tsx:287`'s "not built yet" copy is stale (the tool shipped, MCP-only). **Leave the facet; do NOT "fix" the copy from a RUN-STATE alone.** | 1 | **Wave 7** |
| `D-BOOK-MYACCESS-ADOPTION` | W2-S0 | `my-access` now exists and **only `arc-inspector` uses it**; `PlanHubPanel.tsx:289` still renders EDIT controls to a VIEW collaborator. | 1 | A hygiene sweep, or **Wave 6** |
| `D-ARC-I18N-LOCALES` | W2-S4 | 17 locales, only if `i18n_translate.py` can't run (needs LM Studio). **FE falls back to `en` — never block the wave on it.** | 4 | Next i18n run |
| `D-ARC-VIEWONLY-SMOKE` | W2-S10 | The VIEW-only live proof, only if a 2nd granted account is unavailable. **Say so — never claim it passed.** | 4 | When a 2nd account exists |
| `D-COMPOSE-GENERATE-UNGATED` | W3-3c | 🔴 `POST /works/{pid}/generate` spends tokens with **no confirm gate** while its MCP twin **is** Tier-W gated. ComposePanel drives it. **DO NOT close this by gating Regenerate alone — that is the AN-8 defect.** Fix **at the route**, both call sites. | 1 | The compose path |
| 🔴 `D-MOTIF-APPLICATION-MULTI-ROW` | W3-3a3 | **CONDITIONAL — opens ONLY if the §2 G5 back-fill probe returns ROWS.** The one-row-per-node invariant is then FALSE ⇒ the UNIQUE index cannot build ⇒ M-BUG-2/M-BUG-3 are real. **SKIP ALL of `3a-3`** (index **and** the collapse-4-predicates-to-1, which assumes the invariant) and **CONTINUE to `3a-2`.** Needs a de-dup migration + a product rule for which row wins. ⚠ **NOT a stop-and-ask** — a false *spec invariant* is **not** a PO-1..4 *sealed decision*. | 2 | Its own spec |
| `D-MOTIF-GRAPH-CANVAS` | W3-3a | A **visual** motif DAG. This wave ships an honest **LIST**. **Recorded so it is not "fixed" by accident with d3.** | 2 | Wave 4/5 |
| `D-ARC-TEMPLATE-DRIFT-VIEW` | W3-3c | `?scope=arc_template_drift` — a shipped route with zero FE consumers. | 3 | **Wave 4** |
| `D-MOTIF-BOOKSHARED-QUOTA` | W3-3a | Adopt into `book_shared` counts against **whose** quota? Probably right; **NOT verified against the ledger.** | 4 | 🔴 **Needs the usage-billing owner (§10)** |
| `D-MOTIF-DEEPLINK-NO-RESOURCE-REF` | W3-3b | *(Open ONLY if X-6 has not landed.)* The motif-chip deep-link needs AN-12 `resource_ref`. | 4 | When X-6 lands |
| `D-ARC-CONFORMANCE-LEGACY-PAGE` | W3-3c | *(Open ONLY if the legacy view has no `structure_node.id`.)* | 1 | Wave 4 |
| `D-AT6-FE-PROVENANCE-STAMP-DUPLICATE-WRITER` | W4-FE4 | AT-6 stamps `structure_node.arc_template_id` **from the FE**. Once a server-side stamp exists it **must be DELETED**, not left a second writer. **Raise this row the moment W4-FE4 lands.** | 2 | Wave 6 / whenever `materialize` gains a txn stamp |
| `D-IMPORT-SOURCE-20K-CAP` | W4-FE7 | `import_source.content` is capped at 20 000 chars; a novel is 100×–1000× that. | 2/4 | 🔴 **PO decision at Wave 4's POST-REVIEW, with the live smoke's real output in hand (§10)** |
| `D-ARC-TEMPLATE-BOOK-SHARED-TIER` | W4-FE1 | No `book_shared` tier for `arc_template`. Collaborators share by publish + adopt. | 5 | Recorded; documented in the User Guide |
| `D-BE8-APPLY-ARC-TO-SPEC` | W4-BE8b | **ONLY IF the escape hatch fires.** `apply_arc_to_spec` needs a schema change or a `plan.py` refactor. **W4-BE8a (drift) ships regardless. DO NOT STOP. DO NOT ASK.** | 2 | Its own slice |
| `D-PLAN-GET-ARTIFACT-TOOL` | W5-S2 | After BE-3 the human can read a plan artifact and **the agent still cannot**. A real GG-2 inversion. | 1/2 | Next PlanForge touch |
| `D-PLAN-TIERW-DESCRIPTOR` | W5 §8 | PlanForge's paid actions spend with **no pre-run guardrail claim**, unlike their Tier-W siblings. | 4 | 🔴 **PO decision — it changes the AGENT's channel, and AN-8 seals one-channel-per-object-class (§10)** |
| `D-PLAN-ARTIFACT-HISTORY` | W5-S9 | The viewer shows latest-per-kind, not history — though every version is stored. | 1 | v2 |
| `D-PLAN-EDITS-GENERIC-PATCH` | W5 (OQ-2) | Structured edit forms for `cast` + `beats` only; other artifacts are read-only + re-run. | 3 | After W5-S6 |
| `D-PLANFORGE-GUI-AUDIT` | W5 (inherited) | ⚠ **AMEND then CLEAR.** Sub-gap 1 (the `arc_id` text box) is **STALE — fixed by `9c685c28a`.** Sub-gaps 2/3/4 **are** this wave. | — | ✅ **CLEARED by Wave 5** |
| `D-REF-UPDATE-AND-MODEL-SURFACE` | W6-M2 | BE-17. Today, fixing a **typo** in a reference title means delete+re-add, **which RE-EMBEDS — a paid provider call to fix a typo.** | 2 | v2 |
| `D-DIVERGENCE-SPEC-EDIT` | W6-M3 | BE-13. **UNBUILDABLE on today's backend** — spec + overrides are written once inside the derive txn. | 2 | v2 |
| `D-STRUCTURE-TEMPLATE-AUTHORING` | W6-M4a | BE-12. **Tenancy is the whole job** — the 6 built-ins are System-tier; a user **CLONES**, never mutates (the `entity_kinds` bug). **OQ-1 DECIDED: DEFER.** | 5 | When a user asks |
| `D-REFERENCES-MCP-TOOLS` | W6-M2 | The agent can `pack()` with references and cannot curate them. Routes all exist — **cheap.** | 3 | Wave 7+ |
| `D-DIVERGENCE-MCP-TOOLS` | W6-M3 | Deriving **forks a knowledge partition** — needs its own AN-8 confirm design. | 2 | Its own slice |
| `D-STUDIO-MOBILE-SHELL` | W6-M5 | 🔴 **The Studio has NO mobile editing surface.** `MobileEditorShell.tsx` exists **only** on the legacy path. | 4 | 🔴 **HARD BLOCKER on the spec-16 deletion. PO decision (§10).** |
| `D-EDITORBRIDGE-SINGLETON` | W6-M5 | Alive only because the page it was going to die with **was KEPT** — a premise Phase 4b cancelled and nobody revisited. | 3 | With the deletion |
| `D-WORK-MODEL-ROLES-DEFAULT-REF` | W6-BE2 | BE-21 re-points the 7 `critic` sites at `model_roles`; the `default_model_ref` readers (incl. **8 `scripts/eval_*.py`**) still read the legacy scalar. **One home is only HALF-built until they follow.** | 2 | Its own slice |
| `D-WORK-BLIND-PATCH-NO-VERSION-BUMP` | W6-BE1 (C4) | `WorksRepo.update` bumps `version` **only** when `expected_version` is passed ⇒ a blind PATCH is invisible to a later If-Match write. **Do NOT "fix" it inside this wave** — bumping on blind writes would **412 every If-Match caller after a world-map drag.** | 2 | With `D-WORLDMAP-OCC` |
| `D-WAVE6-DISCOVERY-SCENT` | W6 §7 (X-10) | The 7 new MCP tools are **never mentioned to the model**. One clause in `stream_service.py`. **The ONE genuinely-external blocker in the wave.** | 4 | After Track C lands |
| `D-GG4-PARITY-ROWS-PENDING` | W6-M5 | *(File only if Waves 1–5 have not landed.)* The `legacyParityContract` rows for Waves 1–5's panels are `PENDING Wave N`. **Flip each as its wave lands. The rows ARE the gate — do not delete them.** | 3 | As each wave lands |
| `D-W7-RUN-BUTTON-X1` | W7-S7 | The Run-conformance button ships **only if X-1 landed** — without it, it destroys the dock on the empty-model path. The row still renders and states the fact. | 4 | Wave 0's X-1 |
| `D-W7-FE1-BOOKPKG` | W7-S9 | FE-1 needs a Book-Package handoff. Until then **3 routing rows ship INERT — honest, not broken.** | 1 | On handoff |
| `D-W7-M3-JOBS` | W7-S10..12 | Jobs + Generation tabs are independently deferrable. **M1 still ships the honest stub copy** — the lie *"once wired"* is deleted either way. | 3 | A follow-up session |
| `D-W7-PACKAGE-TREE-NO-GUI` | W7 (IF-5) | `composition_package_tree` gets **NO** human surface. **AN-12's premise holds for THIS one.** A "book at a glance" panel would be exactly the DOCK-2 fork AN-12 forbids. | 5 | **Never.** Recorded. |
| `D-W7-UI-TOGGLE-BOTTOM-PANEL` | W7 (OQ-1) | The agent cannot *show* a human the Issues feed. Adding `"issues"` to the panel enum **reds the catalog contract by construction** (it is not a dockview panel). | 1 | **Wave 0's X-5/X-12 decision surface** |
| `D-W7-X13-REHOME` | W7 (OQ-5) | 🔴 Plan 30 §8.2 deadlines **X-13** at *"Wave 7 at the latest"*. **Wave 7 is that wave and does not carry it** (zero frontend tools, zero panel ids; `chat-service` is **Track-C-locked**). | 1/4 | 🔴 **RAISE TO THE PO at Wave 7's close-out. Amend §8.2 explicitly — do not let a "load-bearing" item lapse by omission (§10).** |
| `D-W7-OQ3-CHAPTER-SCOPE` | W7 (OQ-3) | Feed is **BOOK-WIDE in v1** (a "clean chapter" would be read as a clean book). Every row shows its chapter. | 5 | On user feedback |
| `D-KG-FACT-RESTORE` | W8-06 | **No un-forget.** `invalidate_fact` sets `valid_until` and **nothing anywhere clears it** — a mis-clicked Forget is unrecoverable through **any** surface. **v1 mitigation SHIPS: a confirm dialog whose copy says it is one-way.** | 2 | Post-wave-8 |
| `D-KG-MANUAL-NODE-ANCHOR` | W8-02 | A manual KG node has no `glossary_entity_id` and can **shadow** a later projection's anchor. **v1 mitigation SHIPS: the in-form anchor warning.** | 2 | Post-wave-8 |
| `D-KG-RELATION-PREDICATE-UNCONSTRAINED` | W8-03 | `predicate` is a free string at the **BACKEND** (an agent or a curl can mint an off-ontology edge). 🟢 **The FE half is FIXED in W8-03** (create *and* correct both go through `PredicateControl`). BE-only. | 2 | Post-wave-8 |
| `D-WORLD-MARKER-TYPE-VOCAB` | W8-13 | `marker_type` has **no vocabulary anywhere** in the backend. v1 ships a `<select>` + a free-text escape **and says in the UI it is not a closed set.** ⚠ **Do NOT add it to `CLOSED_SET_ARGS`** — declaring it closed on one side only is the drift this repo hunts. | 2 | Post-wave-8 |
| `D-KG-PROJECTION-DEGRADE-OPAQUE` | W8-05 | *"the glossary is empty"* and *"we couldn't read the glossary"* are **indistinguishable** to the route. **The fix is in the ENGINE. Do not guess in the route.** | 2 | Post-wave-8 |
| `D-WORLD-NO-COLLABORATORS` | W8-12 | A book collaborator with EDIT gets a **404 from every world route**. 🔴 **Worlds are owner-only ON PURPOSE — this is NOT a bug to fix by widening the world routes.** | 5 | Recorded, not scheduled |
| `D-WORLD-MAP-LEGACY-PLACEGRAPH` | W8 | The legacy **place-graph** (`composition_work.settings.world_map` — a *different thing*) is not ported. 🟢 After W8-02/03 the KG panels own create ⇒ **GG-4 is unblocked for this component.** | 1 | plan 30's Wave 6 |
| `D-KG-BIO-NO-FACTS` | W8-06 | `kg-bio` has no facts list, so Forget cannot live there. **Recorded so `kg-bio` is not re-proposed as the A4 home.** | 5 | Never |
| `D-TRANSL-LANG-BACKFILL` | WT-C2 | Merge legacy free-text `target_language` (`Vietnamese` → `vi`) across 3 tables. `Dracula` ch.1 has 2 `Vietnamese` + 1 `vi` ⇒ **`version_num` 1 exists twice ⇒ index violation, needs renumbering**, and `active_chapter_translation_versions`'s PK collapses two rows ⇒ **needs a which-version-wins product rule**. | 2 | **After Wave T lands T-C2** (so the bad set stops growing). Its own spec + plan. |
| `D-TRANSL-S11-JOBCONTROL-EFFECTS` | WT §1.5 | `translationEffects.ts`'s pattern doesn't match the agent's `resume`/`retry` (they dispatch via `confirm_action`). | 5 | When `confirm_action`'s effect envelope is next touched |

### 7.3 Rows plan 30 ABSORBS — move to "Recently cleared" as each wave lands

`D-MOTIF-LIBRARY-CRUD-GUI` → W3-3a · `D-QUALITY-MOTIF-ROLLUP` → W3-3c ·
`D-ARC-TEMPLATE-CRUD-GUI` → W4 · `D-ARC-APPLY-MCP-WRAPPER` → W4-BE8 ·
`DBT-06` → W2 · `D-PLANFORGE-GUI-AUDIT` → W5 (**amend: sub-gap 1 is stale**) ·
`D-QUALITY-CRITIC-HEAL-LINK` → W1 · `D-WS3-BINDING-GUI` → **Track C P-5 (PO-2)** ·
00C **Q-1** → Wave T · 00C **Q-2** → ✅ **already stale/cleared** · 00C **Q-3** → W1 ·
00C **Q-4/Q-5/Q-6** → **GATED on Wave 6 (GG-4)** · 00C **Q-7** → W7 ·
`D-ARC-DECOMPILER-STRUCTURE-NODE` → **out of scope, its own spec.**

**Two rows are STRUCK, not deferred** (each wave plan says so, loudly, so nobody re-mints them):
`~~D-ARC-CONFORMANCE-FE-ARGS-DRIFT~~` — spec 33's **M-BUG-4** owns it and closes it in **3c**, before Wave 4.
`~~D-MOTIF-JOB-POLL-404~~` — it **is** BE-7c, built in **Wave 0 / `W0-BE1`** (and its name is a
**misnomer**: the poll never 404s, because the confirm **500s** and the job row is never created — C-1).

---

## 8 · COLLISIONS — a SHARED CHECKOUT, three live tracks, ONE branch

**All three live tracks are on `feat/context-budget-law`, in THIS checkout.**

> **NEVER `git add -A`.** Enumerate files. `git commit -- <path>` commits the **WORKING TREE, not the
> index** — and the index may already carry a concurrent session's pre-staged changes. **`git status` +
> `git diff --cached --name-only` before EVERY commit.**

| Track | State | What it owns / collides on | The rule |
|---|---|---|---|
| 🔴 **Track C** (agent discoverability / workflow rails) — `docs/plans/2026-07-12-track-c-completion-RUN-STATE.md` | Phases 1–3 done · **P-5 PARKED with NO design and NO code** (verified: `grep "'world'" catalog.ts` → zero hits) | **Owns `G-WORKFLOWS` outright (PO-2).** Its P-5 also *claims* "W10 world container" — which is **Wave 8b's host**. **4 files were uncommitted + mid-edit:** `chat-service/app/services/stream_service.py` · `frontend/.../ToolApprovalCard.tsx` · `chat/hooks/useChatMessages.ts` · `chat-service/app/routers/tool_permissions.py` | **DO NOT TOUCH those 4 files.** **X-10 (AN-C2 scent) sequences AFTER Track C** — it is `W0-S11`, deliberately the **last** slice of Wave 0. ⚠ **Plan 30 §9's "mid-edit RIGHT NOW" is STALE — all four are CLEAN at HEAD `9262ed53e`.** The builder **RE-VERIFIES at build time** and, if dirty, **DEFERS `D-X10-ANC2-SCENT` and KEEPS GOING.** Wave 8b's ownership is a **10-minute write-down (`W8-00`), not a stall** — an ownership question is **not** one of the four CRITICAL classes. |
| 🟡 **Book-Package track** (specs 22–28) — `docs/plans/2026-07-12-book-package-RUN-STATE.md` | **DECLARED COMPLETE 2026-07-12** | Owns **`PlanDrawer.tsx`** · `plan-hub` · `scene-browser` · **`scene-inspector`** · `structure_node` · the compiler. **Wave 2 (AI-4), Wave 3b, Wave 6 and Wave 7's FE-1 all touch these.** | **Read the git history before editing.** Wave 2's `PlanDrawer` change is deliberately shaped as **a deletion + a one-line mount** (~55 out, ~6 in, no moved symbols) so it **reverts cleanly**. Wave 7's FE-1 needs a handoff — until then its 3 routing rows ship **INERT** (`D-W7-FE1-BOOKPKG`). **🔴 Wave 2 must precede Wave 3b** — both edit `PlanDrawer.tsx`/`NodeBadges.tsx`. |
| 🟡 **`QualityCanonPanel.tsx`** | Touched **2026-07-12** (`d662bd97d`) | Wave 1 adds siblings under the same hub. | Read its history. **Its `focusRuleId` deep-link seam is ALREADY THERE — use it, don't rebuild it.** |
| 🟡 **Work Assistant track** | Phase 1 ~40% | knowledge-service **diary/fact** pipeline. | **Wave 8a touches entity/graph files, not diary/fact.** Verify before editing. |
| 🟢 **Genuinely un-colliding — the safe lanes** | — | **Wave T** (spec 29 — disjoint from the whole 00B cluster) · **the motif + arc-template ports** (nobody is in `features/composition/motif/**`) · **the Planner panel** (Track C only *reads* PlanForge tool descriptions) · **Wave 8a** (knowledge-service, different service) | **Start here when a lane frees up.** |
| ⚠ **7 stale `lane/*` worktrees** | A finished KG-ontology `/warp` fan-out, still checked out | — | **Do not reuse those branch names.** |

**Files EVERY wave touches — the guaranteed conflict surface:** `frontend/src/features/studio/panels/catalog.ts` ·
`services/chat-service/app/services/frontend_tools.py` · `contracts/frontend-tools.contract.json` ·
`frontend/src/i18n/locales/**/studio.json`. **Regenerate the contract JSON; never hand-merge it after a rebase.**

---

## 9 · TOTALS

| | |
|---|---:|
| **Waves** | **10** (0 · 1 · 2 · 3 · 4 · 5 · 6 · 7 · 8 · T) |
| **Slices (= commits)** | 🔴 **192** — W0 **22** · W1 **20** · W2 **14** · W3 **15** · W4 **17** · W5 **19** · W6 **22** · W7 **17** · W8 **22** · WT **24**. *(Was 188. **+4 from the second seal (§2.1):** `W0-S15` (D-2) · `W0-S16` (D-3) · `W8-20` (D-7) · and `T-C10` (D-1), which existed in the Wave-T plan but was **on no board row** — the exact silent-skip this ledger exists to prevent.)* *(Every wave carries an explicit **close-out slice** whose DoD includes `/review-impl` + fix — the resume protocol walks the **BOARD**, so a wave whose close-out is not a board row is a wave whose `/review-impl` gets skipped after a compaction.)* 🔴 **RECONCILED 2026-07-13: was 143.** 46 slices lived in the wave plans and on **no board row**. The additions: **9 contract-first slices** (one per route-bearing wave — CLAUDE.md's *"API contract frozen before frontend flow"* was being violated by **every** wave), the **5 homeless-legacy-sub-tab panels**, and the **defer rows refuted against code that became slices** (I-14). **One row was DELETED** — the old `W2-S0` (a Go `my-access` route); the plan **refutes it** (`access_level` is already on the wire and the FE drops it). |
| **Shippable milestones (= POST-REVIEWs)** | **≈19** — most waves are one; **W3 = 3** (3a/3b/3c) · **W6 = 5** (M1–M5) · **W8 = 2** (8a/8b) · **WT = 3** (Phases A/B/C) |
| **New REST routes** | **~55** — W0 **2** · W1 6 · W2 **0** *(🔴 **ZERO. No Go. The `my-access` route the first draft invented is DELETED** — `access_level` already ships on `GET /v1/books/{id}` and the FE drops it; the 8 arc routes are **existing** code entering the contract for the first time)* · W3 **6** · W4 2 · W5 5 · W6 7 · W7 2 · **W8 18** · WT **0**. 🔴 **EVERY route-bearing wave now has a CONTRACT-FIRST slice that freezes them BEFORE its first FE consumer** — `W0-C1` · `W1-CONTRACT` · `W2-S0` · `3a-0` · `W4-BE0` · `W5-S6c` · `W6-C0` · `W7-S3b` · `W8-0C`. *(Not one wave plan touched a contract file as originally drafted. That is a repo-law violation, not an oversight to absorb.)* ⚠ **The contract files are NOT interchangeable:** `contracts/api/composition/v1/openapi.yaml` (W0/1/2/3/4/6/7) · **`contracts/api/composition-service/plan-forge.v1.yaml`** (W5 ONLY) · `contracts/api/books/v1/openapi.yaml` (W8 — 🔴 **`contracts/api/book-service/` DOES NOT EXIST; do not create it**). |
| **Migrations** | **7 additive DDL units, ZERO destructive** — **W0 ×1** (`generation_job` scope `DROP NOT NULL` + the **`generation_job_scope_shape`** both-or-neither CHECK + the **`idx_generation_job_owner_unbound`** partial index — **BE-7c, pulled into `W0-BE1` with the rest of the paid-action fix; C-1**) · W1 ×2 (`authoring_run_units.job_id` nullable; `composition_progress_goal`) · W3 ×1 (the `motif_application` partial UNIQUE — **3a-3, and PROBE-GATED: a non-empty probe ⇒ DEFER the slice and CONTINUE, never a stop-and-ask**) · W5 ×1 (`plan_run.is_archived` + its partial index) · W7 ×1 (a `job_projection` expression index) · W8 ×1 (3 ALTERs on `world_maps`/`map_markers`/`map_regions`). **W2 · W6 · WT = ZERO, by design.** ⚠ **W4 = ZERO *in the planned sequence*, but NOT "banned":** `W4-BE3` is **CONDITIONAL** — it re-applies **W0-BE1's** DDL **only if Wave 0 and Wave 3 both somehow did not** (pre-flight cmd 4). 🔴 **If it ever fires, COPY `W0-BE1`'s block VERBATIM — DO NOT FORK IT.** An earlier cut of Wave 4 wrote a **second, different** version of the same migration (`generation_job_project_scope_chk` + `idx_generation_job_owner`); applying both would leave **two constraints and two indexes for one invariant, under two names**. Wave 0's CHECK constrains the **SHAPE** (both scope keys NULL or both set), *not* an operation set — so a third Work-less op needs **zero DDL** and never trips `migration-check-constraint-must-backfill-all-historical-blocks`. The op allowlist lives in the **writer** (`create_unbound()`). |
| **New panel ids** | 🔴 **20** (57 → **77**) — W1 4 · W2 1 · W3 2 · W4 1 · W5 1 · **W6 5** · W7 0 · **W8 6** · W0/WT 0. *(Was 14 → 71 before the plans homed the 7 orphaned legacy sub-tabs; then 19 → 76; then PO **`D-7`** added `place-graph` ⇒ **20 → 77**.)* **Assert the DELTA, never the literal.** |
| **Defer rows opened** | **~60** (+ 14 absorbed from plan 30's Appendix B). 🔴 **SIX rows were REFUTED AGAINST CODE and became SLICES, not rows** (I-14 — *"missing infrastructure is NOT blocked; it is unbuilt work you WRITE"*): `D-DIVERGENCE-SPEC-EDIT` → **W6-BE6** · `D-REFERENCES-MCP-TOOLS` → **W6-BE4b** · `D-DIVERGENCE-MCP-TOOLS` → **W6-BE8** · `D-WAVE6-DISCOVERY-SCENT` → **W6-BE9** · `D-W7-RUN-BUTTON-X1` → **W7-S0** · `D-TRANSL-S11-JOBCONTROL-EFFECTS` → **T-B6**. And `D-W7-X13-REHOME` (E-2) is **DISCHARGED by building X-13 in `W0-S5c`** — Wave 0 is *earlier* than its "Wave 7 at the latest" deadline, so it tightens rather than lapses. `D-AT6-FE-PROVENANCE-STAMP-DUPLICATE-WRITER` **never opens** — `W4-BE4` puts the stamp server-side, so no second writer is ever shipped. |
| **Services touched** | composition · chat · book · knowledge · frontend. **api-gateway-bff: ZERO changes** (both proxies are generic path-preserving). |

**Migration discipline — every one of the 7 is ADDITIVE, and each plan states its traps explicitly:**
`ADD COLUMN IF NOT EXISTS` **never revisits a bad default** on an already-migrated DB (get it right the
first time) · a new enum value must **backfill ALL historical CHECK blocks** (W0's shape CHECK
deliberately constrains **shape, not an operation set**, so a new Work-less op never needs DDL — the
allowlist lives in the **writer**) · a partial UNIQUE index must **exempt soft-delete tombstones** and its
**`ON CONFLICT` must repeat the predicate** · **NEVER backfill a guess** (W1's `job_id` is nullable *by
design* — a wrong guess attributes THIS author's rejection to SOMEONE ELSE'S generation; the synthetic
`project_id` **IS the bug** and must not be back-filled into a phantom Work) ·
🔴 **W3's partial index (3a-3) PROBES FIRST** — if the probe returns rows the index cannot build, the
spec's invariant is **false** and **3a-3** is wrong. **⇒ DEFER 3a-3 (`D-MOTIF-APPLICATION-MULTI-ROW`,
gate #2) and CONTINUE to 3a-2. This is NOT a stop-and-ask** — a false *spec invariant* is none of the four
CRITICAL classes (it is not destructive, not a tenancy breach, not a paid action, and **not** a PO-1..4
*sealed decision*). Nothing else in Wave 3 depends on 3a-3.

---

## 10 · ESCALATIONS STILL OPEN FOR THE PO

> These do **not** stop the run. Waves proceed; each escalation is raised at the **named checkpoint**.
> They are here so none of them **lapses by omission** — which is itself the failure this list exists to
> prevent.

| # | Escalation | Where it surfaces | What the PO must decide |
|---|---|---|---|
| **E-1** | 🔴 **THE ADJUDICATION REGISTER DOES NOT EXIST.** All **ten** planning agents independently searched the scratchpad, the temp tree and the repo and found **no `adjudication-register.md`** (the scratchpad holds only the `inv-*.md` / `spec-audit-*.md` dumps). **Every open question was therefore RE-ADJUDICATED FROM THE CODE**, with file+line evidence, recorded inline in each plan's §0.x. | **Now.** | Either (a) confirm the register was never written and the ten in-plan adjudications **stand**, or (b) produce it. **If it surfaces and contradicts a code-verified adjudication, the CODE wins** — but the rows worth re-checking first are Wave 2's LA-1/LA-2/LA-3 and Wave 7's OQ-1/OQ-3/OQ-4/OQ-5. **PO-1..4 are not re-openable from memory either way.** |
| **E-2** | ✅ **`D-W7-X13-REHOME` — DISCHARGED BY BUILDING IT. No PO decision is owed.** Plan 30 §8.2 deadlines **X-13** (`consumer_capabilities` + `contributeContext()`) at *"Wave 0 stretch, or **Wave 7 at the latest**"*. Wave 7 legitimately cannot carry it (zero frontend tools, zero panel ids). ⇒ **It is re-homed to `W0-S5c`** — which rides `W0-S5`/`W0-S5b`'s contract regen (same file, same regen, same two resolvers). **Wave 0 is EARLIER than Wave 7, so the deadline TIGHTENS; nothing lapses.** ⚠ The premise was *understated*: `ConsumerCapabilities` is not merely unread — it is an **EMPTY model (`pass`, zero fields)** that `messages.py` **never forwards**. **No consumer AND no producer** ⇒ deleting it costs nothing. *(Also dead: `StudioContext.active_panel_ids`.)* | **`W0-S5c` builds it; `W7-S13` amends plan 30 §8.2 + marks spec 37 OQ-5 CLOSED.** | **Nothing — unless the PO vetoes.** If Wave 0 slips X-13 for scope, the **only** acceptable alternative is to **DELETE the four dead symbols** (a declared-and-unread field is the class CLAUDE.md bans). **Do not defer them a third time.** |
| **E-3** | **`D-STUDIO-MOBILE-SHELL`** — the Studio has **NO mobile editing surface**; `MobileEditorShell.tsx`/`MobilePanelSwitcher.tsx` exist **only** on the legacy path. | **Wave 6's close-out (the GG-4 gate).** | 🔴 **This is a HARD BLOCKER on the spec-16 `ChapterEditorPage` deletion.** Wave 6 ships the **mechanical parity guard**, not the deletion. Decide: build a mobile Studio shell, or keep the legacy page for mobile, or accept desktop-only. **Until then, GG-4 stays shut.** |
| **E-4** | **Track C P-5 ownership of the `world` container** (Wave 8b's host). PO-2 already gave Track C `G-WORKFLOWS`; P-5's text *also* claims "W10 world container". **Verified: P-5 is PARKED with NO design and NO code; spec 38 HAS the design.** | **Wave 8's pre-flight (`W8-00`).** | Confirm the **write-down**: this plan takes the `world` container, Track C keeps workflows. It is a 10-minute note, **not a stall** — the builder proceeds either way (an ownership question is **not** one of the four CRITICAL classes). |
| **E-5** | **`D-IMPORT-SOURCE-20K-CAP`** — `import_source.content` is capped at **20 000 chars**; a novel is 100×–1000× that. If a 20k excerpt yields a thin template, the fix is a **chunked multi-part import source** (a schema change). | **Wave 4's POST-REVIEW — with the live smoke's ACTUAL output in hand.** | Is a 20k excerpt good enough for 拆文 v1? **Decide with evidence, not in the abstract.** |
| **E-6** | **`D-PLAN-TIERW-DESCRIPTOR`** — PlanForge's paid actions (`run_pass`, `refine`, `interpret`, `autofix`) spend with **no pre-run usage-billing/guardrail claim**, unlike their Tier-W siblings (`motif_mine`, `conformance_run`). | **Wave 5's POST-REVIEW.** | Adding a `composition.plan_*` descriptor **changes the AGENT's channel**, and **AN-8 seals one-channel-per-object-class** (*"a reviewer finding a new confirmation convention here has found a defect"*). This is a product decision, not a refactor. |
| **E-7** | **`D-MOTIF-BOOKSHARED-QUOTA`** — adopting into `book_shared` counts against **whose** quota, the adopter's or the book owner's? The confirm stamps `owner_user_id` = the adopter; the quota check is on the caller. **Probably right; NOT verified against the ledger.** | **Wave 3 / 3a's close-out.** | Needs the **usage-billing owner**. Gate #4 (genuinely blocked on another owner) — the wave ships regardless. |
| **E-8** | **`D-COMPOSE-GENERATE-UNGATED`** — 🔴 `POST /works/{pid}/generate` **spends LLM tokens with NO confirmation gate** while its own MCP twin **IS** Tier-W confirm-gated. **The shipped `ComposePanel` drives the ungated route today.** | **Raised at Wave 3 / 3c; it is a defect of the COMPOSE path, not the motif cluster.** | It is **adjacent to the paid-action CRITICAL class** but is **pre-existing and not a regression of this batch**, so it defers under gate #1. 🔴 **DO NOT close it by gating Regenerate alone — that would be the AN-8 defect.** Fix **at the route**, which fixes both call sites. **Confirm the PO is content to carry it, or pull it forward.** |

---

## Appendix — the pre-flight EVERY wave runs, before its first commit

```bash
# 1 · The lane is clean (three tracks share this checkout)
git status --short
git diff --cached --name-only          # the index may carry ANOTHER agent's staged work

# 2 · Track C's 4 files are untouched (X-10 / stream_service.py)
git status --short -- services/chat-service/app/services/stream_service.py \
  services/chat-service/app/routers/tool_permissions.py \
  frontend/src/features/chat/components/ToolApprovalCard.tsx \
  frontend/src/features/chat/hooks/useChatMessages.ts

# 3 · The two drift-locks are green BEFORE you start (know your N_before)
cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py -q

# 4 · This wave's hard gate (see §4.1) — e.g. for Wave 3:
grep -rn "motif" services/composition-service/app/packer/    # X-7: must be NON-EMPTY
grep -c 'motif_app_repo=' services/composition-service/app/services/engine.py \
        services/composition-service/app/packer/grounding.py  # must total 4

# 5 · For Wave 1: X-2 is green (quality ∈ CATEGORY_ORDER) — else build W1-00 first
grep -n "CATEGORY_ORDER" -A4 frontend/src/features/studio/palette/useStudioCommands.ts
```

**And at the END of every wave, in this order, no exceptions:**
suites green (deltas, pasted, `passed` not `skipped`) → drift-locks green (delta + three-way) →
**live browser smoke on a REBUILT image** → **`/review-impl`, every bug FIXED** → SESSION_HANDOFF →
commit with **enumerated paths**.
