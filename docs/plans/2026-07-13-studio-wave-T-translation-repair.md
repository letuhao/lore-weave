# Wave T — Translation repair (the parallel lane) · IMPLEMENTATION PLAN

> **Type:** FS (Phase A/B = FE-only · Phase C = translation-service + frontend + contracts)
> **Size:** **L** (**24 slices** · 4 phases · 🔴 **1 migration — WRITTEN + DRY-RUN ONLY, NEVER EXECUTED
> (PO-gated: T-C10)** · 0 new panels · 1 contract slice)
> **Spec:** [`docs/specs/2026-07-01-writing-studio/29_translation_repair.md`](../specs/2026-07-01-writing-studio/29_translation_repair.md) — PO-decided 2026-07-10
> **🔴 ADJUDICATED DECISIONS (BINDING — READ BEFORE ANY SLICE):**
> [`docs/plans/studio-adjudication/wave-T-decisions.md`](studio-adjudication/wave-T-decisions.md) — 34 items settled
> **against source code**. **Where this plan and that file disagree, THAT FILE WINS** — it was adjudicated
> against the tree; this plan's first draft was written blind to it. §3.6 below lists every place the plan
> was already corrected, so a builder never has to diff the two.
> **Master plan:** [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §4 (row 29), §7 ("The parallel lane"), §9 (collisions)
> **Planned at:** HEAD `9262ed53e`, branch `feat/context-budget-law`, 2026-07-13. Reconciled 2026-07-13.
>
> ## 🔴 PO DECISIONS — SEALED 2026-07-13. BINDING. DO NOT RE-LITIGATE.
>
> Three of the PO's sealed decisions land on **this** plan. They **outrank both this plan and the
> adjudication file.** Each is applied in full below; this box exists so nobody "restores" the old text.
>
> | PO | Ruling | Effect on Wave T |
> |---|---|---|
> | 🔴 **D-1** | The `Vietnamese` → `vi` **rekey is DESTRUCTIVE and PO-GATED.** Write the migration + a rollback path + a before/after row-count assertion, **run a DRY-RUN, show the output, and STOP.** The agent may **NOT** execute it unattended. | **§5 is REWRITTEN.** The old *"NONE. Wave T ships zero DDL"* is **superseded**: the wave now **produces the migration and its dry-run** in slice **T-C10** — and **T-C10 STOPS AND ASKS.** It is **the ONE place in the entire build where the agent stops.** `D-TRANSL-LANG-BACKFILL` is **replaced** by T-C10 (write + dry-run) + `D-TRANSL-LANG-REKEY-EXECUTE` (the PO-supervised execution). |
> | 🔴 **D-2** | **T8 (the dropped selection) is PULLED FORWARD into WAVE 0** as **`W0-S15`** — it damages data today. | **T8 is DISCHARGED ELSEWHERE. Wave T must not build it twice.** The T8 half of slice **T-A4 is DROPPED**; T-A4 survives **only** as the **D6** language hand-off, and it carries a **hard pre-flight assert that W0-S15 has landed.** ⚠ **This gives Wave T its FIRST upstream dependency — see §1.2.** |
> | 🔴 **D-4** | The content-language SSOT file is **`contracts/languages.contract.json`**. | ⚠ **It must NEVER be called `languages.yaml`.** `contracts/language-rule.yaml` **already exists** and means *service → **programming** language* — **a different axis.** One name for two concepts is the drift this repo legislates against. The plan already uses the sealed name throughout (§3.2a, T-C1); **that name is now LOCKED — do not "tidy" it to `.yaml` or to `languages.json`.** |
>
> **Gaps closed:** T1 · T2 · T3 · T4 · T5 · T6 · T7 · T9 · T10 · S1–S9 · S11 · S12 · D11
> **DISCHARGED ELSEWHERE (PO D-2):** ~~**T8**~~ → **Wave 0 / `W0-S15`.** Wave T **consumes** that fix; it does
> not re-build it.
> **Also closed (found by the adjudication, NOT in the original spec):** the Translate-workmode **editor
> unmount ⇒ silent data loss** · the modal's cross-user **book-settings clobber** · the editor's
> **100-chapter blindness** · the **third** re-translate dead-end (`retranslate-dirty`)
> **Deferred out:** 🔴 **`D-TRANSL-LANG-BACKFILL` is REPLACED** (PO **D-1**): the migration is **WRITTEN and
> DRY-RUN in-wave** (slice **T-C10**), and only its **EXECUTION** is deferred, to a PO-supervised step
> (`D-TRANSL-LANG-REKEY-EXECUTE`, §10). **`D-TRANSL-S11-JOBCONTROL-EFFECTS` is DELETED — S11 is a one-line
> fix-now (slice T-B6).**

---

## 0 · READ THIS FIRST — the PO policy binding this run

Quoted verbatim from the run brief. It is binding on every slice below.

1. **This plan is written ONCE, in full, at BUILD DETAIL. After the QC gate, implementation proceeds
   autonomously with no further design checkpoints.** So anything left vague becomes a stall or a guess
   at 3am. A slice that says "wire the panel" is a FAILURE; a slice says WHICH FILE, WHAT CHANGE, WHICH
   TEST.
2. **`/review-impl` runs at the completion of EVERY wave**, and any bug it finds is fixed before the wave
   closes. It is step 6 of §8's DoD checklist, literally.
3. **DEFERRAL POLICY — "blocked ≠ stopped".** When the build hits a blocker: write a tracked defer row
   and **KEEP GOING**. Do **not** stop, do **not** ask. A blocker is treated as a DEFER by default.
   **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as exactly one of:
   - a destructive / irreversible action (data loss, a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (§0 PO-1..4 of plan 30),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing.**
   Everything else — a missing route, an awkward refactor, a failing third-party thing, an ugly seam —
   is a **defer row + continue**.
4. Every defer row carries: ID, wave/slice of origin, what, the gate reason (CLAUDE.md's 5 gates),
   target wave/trigger. A defer row is never a silent drop.
5. **CLAUDE.md's anti-laziness rule is in force:** "missing infrastructure is NOT blocked — it is unbuilt
   work to implement." A route that does not exist is a route you WRITE.

⚠ **Note on rule 3's 4th bullet:** slice **T-B4** (S1) fixes a *live instance of that exact class* —
the glossary-translate poll can spin forever after a paid LLM job. It is in scope and gets fixed here;
it is not a reason to stop.

> 🔴 **THE ONE SANCTIONED STOP — slice `T-C10` (PO decision D-1).** Rule 3's **first** bullet ("*a destructive
> / irreversible action … a migration that rewrites user rows*") has **exactly one live instance in this
> wave**, and the PO has ruled on it in advance: the `Vietnamese` → `vi` **rekey**. **T-C10 writes the
> migration, its rollback, and its assertions, runs the DRY-RUN, prints the report — AND STOPS.**
> **The agent may NOT execute it, not even if every count looks right, not even if the PO approved "the
> migration" in the abstract.** Approval of the *dry-run output* is a separate, explicit act.
> **Everywhere else in Wave T: blocked ≠ stopped. Here, and only here: STOP.**

---

## 1 · Header — what this wave is, and what it is not

### 1.1 What it closes

| ID | Sev | Surface | Symptom | Slice |
|---|---|---|---|---|
| **T1** | HIGH | `translation` matrix | No Translate CTA at all once the book has ≥1 translated language | **T-A2** |
| **T2** | HIGH | `translation` matrix | Untranslated chapters are invisible — the matrix renders coverage rows, not chapters | **T-A3** |
| **T4** | HIGH | `translation` matrix | Coverage failure ⇒ raw proxy-error string, no retry, no CTA; textless skeleton while loading | **T-A1** |
| **T5** | HIGH | `TranslateModal` | Wedges on "Loading chapters…" — no language picker, no model picker, no error, no timeout | **T-A5** |
| ~~**T8**~~ | HIGH | matrix → modal | "Translate Selected (N)" **discards the selection**; a fully-translated book opens every action disabled | 🔴 **DISCHARGED IN WAVE 0 — `W0-S15`** (PO **D-2**: pulled forward, it damages data today). **NOT BUILT IN WAVE T.** Wave T's **T-A4** now builds **only D6** (the language hand-off) **on top of** W0-S15's prop. |
| **T10** | MED | `translation` matrix | Chapter-fetch failure renders "No chapters to translate" — an error shown as an empty book | **T-A1** |
| **T6** | MED | `ChapterTranslationsPanel` | Degrades silently: blank title, `??` language, zero targets, no error banner | **T-B1** |
| **T7** | MED | `VersionSidebar` | No discoverable way to add a *new* target language | **T-B3** |
| **T3/D13** | MED | matrix + BE | Free-text `target_language` ⇒ duplicate columns (`Vietnamese` **and** `vi`) | **T-C1/2/3/4** |
| **T9/D10** | MED | matrix + BE | `VIEW`-grant collaborators are shown translate actions; job creation needs `EDIT` ⇒ late 403 | **T-A6** (toast) + **T-C5** (gate) |
| **S1–S9, S12** | — | every translate surface | Errors swallowed into states that look like "nothing happened" | **T-B4/B5**, **T-C6** |
| **S11** | LOW | studio matrix | An agent-confirmed `resume`/`retry` does not refresh the **segment** grids | **T-B6** (one line — NOT deferred) |
| **D11 / S10** | LOW | studio dock | Two dock ids for one `translation-versions` panel | **T-B3** |

**🔴 Found by the adjudication, absent from the spec — all in scope, all fix-now:**

| ID | Sev | Surface | Symptom | Slice |
|---|---|---|---|---|
| **X1** | 🔴 **HIGH — data loss** | `ChapterEditorPage` | Switching to **Translate** workmode **UNMOUNTS** the Tiptap editor (`:1221`). It remounts from `savedBody`, so **unsaved edits are destroyed**, `isDirty` still says "dirty" (the header lies), and the next keystroke persists the regressed body. | **T-A7** |
| **X2** | 🔴 **HIGH — tenancy** | `TranslateModal` | Every language/model pick **auto-`PUT`s book settings**. `settings.py:160` upserts `ON CONFLICT (book_id)` (**one row per book**) while `effective_settings.py:76` reads **per-user** ⇒ an EDIT collaborator writes **their private BYOK `user_models` UUID** into the row the **owner** reads. | **T-A5** |
| **X3** | MED | `ChapterEditorPage:433` | `listChapters({limit: 200})` with **no paging loop**; the server clamps to 100 ⇒ on a >100-chapter book the editor's prev/next nav and Chapters sidebar **silently see only the first 100**. Chapter 101's "next" is dead. | **T-A7** |
| **X4** | 🔴 MED — **paid action** | segment drill-down | The **third** re-translate path (`useSegmentDrilldown` → `POST /retranslate-dirty`) posts the matrix column's language **verbatim, with no picker** ⇒ after D13 it is a **guaranteed 400** on a legacy column. The spec listed only two paths. | **T-C8** |
| **X5** | MED | books shelf | `useBooksList.ts:63-78` pulls the **full chapter×language matrix for EVERY book** just to read `known_languages`. Megabytes discarded on arrival. | **T-C7** |

### 1.2 Hard gates — what must be true before this wave starts

### 🔴 1.2.0 — WAVE T NOW HAS **ONE** UPSTREAM DEPENDENCY: **Wave 0 / `W0-S15`** (PO decision D-2)

**This is new, and it is the single most likely way this plan gets built wrong.** Wave T was written as a
**free lane** — *"schedule it into any idle slot"* — and that is **still true of 23 of its 24 slices**. But
**D-2 moved T8's fix into Wave 0 (`W0-S15`)**, and **T-A4 (D6) now builds ON TOP of the prop that slice
adds.** So:

- **`W0-S15` adds `preselectedChapterIds={[...selectedChapters]}`** to the `<TranslateModal>` call site at
  `TranslationTab.tsx:300-305` (+ the header-CTA `clearSelection()` rule — see T-A4).
- **T-A4 adds `preselectedLang`** to the **same** call site and the **same** component.
- ⇒ **They edit the SAME LINES of the SAME TWO FILES.** If Wave T runs first, it will re-implement T8 (a
  double-build the PO explicitly forbade). If it runs second and does not *check*, it will silently **revert**
  W0-S15 by pasting an older version of the JSX block.

> 🔴 **T-A4's FIRST ACTION IS THIS ASSERT — it is a HARD GATE, not a courtesy:**
> ```bash
> # W0-S15 MUST have landed. Expect the prop ON THE TranslateModal call (~:300-305), not only on the
> # ExtractionWizard call (~:544).
> grep -n "preselectedChapterIds" frontend/src/pages/book-tabs/TranslationTab.tsx
> ```
> - **If it is present on the TranslateModal call ⇒ proceed.** T-A4 **ADDS `preselectedLang` beside it** and
>   **touches nothing else about the selection.**
> - **If it is ABSENT ⇒ Wave 0 has not run.** **Do NOT build T8 here** — that is the double-build D-2
>   forbids. **Park T-A4** (and its dependents **T-A5 → T-A6**, and **T-C5**'s A4 leg), **build the rest of
>   the wave** (blocked ≠ stopped — §0 rule 3), and file a **defer row** naming `W0-S15` as the trigger.
>   Come back when Wave 0 lands.
>
> ⚠ **And NEVER `git add -A`.** Three tracks share this checkout (§9 R8); a stale `TranslationTab.tsx` in your
> editor buffer will silently un-ship `W0-S15`.

### 1.2.1 Everything else is still un-colliding

Wave T is **otherwise independent of Waves 0–8**. 00C **Q-1**: *"None — unblocked now. Disjoint files from the
whole 00B cluster."* Plan 30 §9 lists it under **🟢 Genuinely un-colliding**. Concretely:

- ✅ **No X-1/X-2/X-3/X-4 dependency.** Wave T adds **ZERO new panels** ⇒ it does not touch `catalog.ts`,
  `CATEGORY_ORDER`, `guideBodyKey`, `frontend_tools.py`, or `contracts/frontend-tools.contract.json`.
- ✅ **No `stream_service.py`** (Track C is mid-edit there — §9 of plan 30 says DO NOT TOUCH).
- ✅ **No `PlanDrawer.tsx` / `plan-hub` / composition-service** (Book-Package track).
- ✅ **No `knowledge-service`** (Work Assistant track).

### 1.3 What it unblocks downstream

**Nothing.** No other wave depends on Wave T. That is the point: it is a free lane.

🔴 **But it is no longer a *completely* free lane (PO decision D-2).** *(The old text said "nothing blocks it —
schedule it into any idle slot." **That is now false for exactly one slice.**)*

- **23 of 24 slices** are still schedulable in **any** idle slot, against **any** wave order.
- **`T-A4` (and, through it, `T-A5`, `T-A6`, and `T-C5`'s A4 leg) requires `W0-S15` (Wave 0) to have landed.**
  If it has not: **park those four legs, file the defer row, and build the other 20 slices** — do **not** build
  T8 here. **§1.2.0 is the gate; read it before scheduling this wave.**

### 1.4 🔴 THE PANEL-ID LEDGER — Wave T ADDS ZERO ROWS

Plan 30 §8.0 item 6 records a **batch-wide bug**: six of eight specs each computed their enum count from
the same `57` baseline, as if each were the only wave. **Wave T is not in that table at all, because it
introduces no panel.**

> **INSTRUCTION:** Wave T's contribution to the running baseline is **+0**. It must **not** edit
> `frontend/src/features/studio/panels/catalog.ts`, `services/chat-service/app/services/frontend_tools.py`,
> or `contracts/frontend-tools.contract.json`. `translation-versions` (`catalog.ts:230`) already exists and
> is `hiddenFromPalette: true` — a DOCK-6 sanctioned exception, **out of the enum by design**. D11 (slice
> T-B3) makes the *editor* stop minting a second dock id for it; it does **not** add an id.
>
> **The DoD asserts a DELTA OF ZERO + the three-way equality** (`OPENABLE == py enum == contract enum`),
> **never a literal** — a literal "sends a builder hunting a phantom regression" (plan 30 §8.0).

### 1.5 🔴 Lane-B effect handlers — Wave T CREATES NO NEW HANDLER FILE

Plan 30 §8.0b: **ONE FILE PER DOMAIN.** `frontend/src/features/studio/agent/handlers/translationEffects.ts`
**already exists** and already owns the `translation_*` family (its test is
`src/features/studio/agent/__tests__/translationEffects.test.ts`).

> **INSTRUCTION:** Do **not** create a second translation handler file. `matchEffectHandlers`
> (`effectRegistry.ts:45`) returns **EVERY** match and `runEffectHandlers` **awaits ALL** of them — two files
> for one domain **double-fire**. If a slice needs a new invalidation, **extend the existing handler body**.
>
> ⚠ Also from §8.0b: `registerEffectHandler`'s string branch is `tool === p || tool.startsWith(p)` — it is
> **NOT a pattern match**. Anything with alternation MUST be a `RegExp`, or you ship a silent no-op handler
> that no unit test can catch.

**🔴 S11 is FIXED HERE, not scoped out — and it is NOT in `translationEffects.ts` at all.**
*(Reversal. The earlier draft of this plan carried a defer row for S11. The adjudication
`DEF-29-S11-AGENT-REFRESH` proved the premise wrong by reading the code. The decision wins; the defer row is
deleted.)*

Agent-initiated `resume`/`retry` **already** live-refresh the coverage matrix: they dispatch via
`confirm_action`, whose `domain` enum already includes `"translation"`
(`chat-service/app/services/frontend_tools.py:553-556`), and `ConfirmActionCard.tsx:175` calls
`invalidateAfterConfirm(queryClient, 'translation')`, whose prefix `['translation']`
(`invalidateAfterConfirm.ts:24`) already matches `['translation-coverage', bookId]` and
`['translation','refresh',…]`.

**The ONLY real gap** is that the **segment** keys — `['segment-coverage', …]` (`TranslationTab.tsx:184`)
and `['segment-status', …]` (`useSegmentDrilldown.ts:21`) — have heads that are **not** under `'translation'`,
so the confirm path misses them **while the cancel/pause effect handler hits them**
(`translationEffects.ts:17`). That asymmetry is the entire defect. **Fix = one line, slice T-B6.**

> 🔴 **EXPLICITLY REJECTED:** do **not** widen `/^translation_job_control/` to also match `confirm_action`.
> `confirm_action` is **domain-generic** — a regex match there fires translation invalidation on every
> glossary/book/settings/kg confirm, and the effect handler cannot see the confirm's domain. The
> domain-routed `invalidateAfterConfirm` map is the correct, already-built seam.

---

## 2 · Pre-flight — the exact commands, before slice 1

Run all five. Every one must produce the stated result.

```bash
# 1 · The lane is clean (shared checkout, 3 live tracks — plan 30 §9). MUST be EMPTY.
git status --short | grep -iE "transl|book-tabs|lib/languages|features/glossary-translate"

# 2 · 🔴 CHANGED BY PO D-2 — the T8 GATE. W0-S15 (Wave 0) now owns this fix. This check is no longer
#     "prove the bug is real"; it is "prove WHOSE tree I am standing in". Read §1.2.0 before acting.
sed -n '300,306p' frontend/src/pages/book-tabs/TranslationTab.tsx

# 3 · Where is `preselectedChapterIds`?
grep -n "preselectedChapterIds" frontend/src/pages/book-tabs/TranslationTab.tsx \
  frontend/src/features/studio/panels/ChapterBrowserTitleView.tsx \
  frontend/src/features/translation/components/ChapterTranslationsPanel.tsx
#   ALWAYS expected (they shipped long ago):
#     TranslationTab.tsx:~544 (ExtractionWizard) · ChapterBrowserTitleView.tsx:~509 ·
#     ChapterTranslationsPanel.tsx:~207
#   🔴 AND THE ONE THAT DECIDES YOUR PLAN — the <TranslateModal> call at ~:300:
#     • PRESENT  ⇒ W0-S15 has LANDED. ✅ Proceed. T-A4 builds D6 ONLY (add `preselectedLang` BESIDE it).
#                  DO NOT re-implement T8. DO NOT paste an older JSX block over it.
#     • ABSENT   ⇒ Wave 0 has NOT run. 🔴 DO NOT BUILD T8 HERE (PO D-2 forbids the double-build).
#                  PARK T-A4 (+ its dependents T-A5, T-A6, and T-C5's A4 leg), file the defer row naming
#                  W0-S15 as the trigger, and BUILD THE REST OF THE WAVE. Blocked ≠ stopped.

# 4 · Baseline test counts — RECORD THESE NUMBERS, the DoD asserts deltas against them, never literals.
cd frontend && npx vitest run 2>&1 | tail -5          # → record N_fe_before
cd ../services/translation-service && python -m pytest tests -q -n auto --dist loadgroup 2>&1 | tail -3
                                                       # → record N_be_before

# 5 · The enum three-way equality is green BEFORE we start (so a red later is OURS).
cd ../chat-service && python -m pytest tests/test_frontend_tools_contract.py -q
cd ../../frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts
```

**If check 1 is non-empty, another agent is in these files. STOP and reconcile — do not `git add -A`, ever
(`shared-file-collision-safe-staging-multi-agent-checkout`).** Verified empty at plan time.

---

## 3 · 🔴 CORRECTIONS TO THE SPEC + AUDIT — read before touching code

The wave brief warned: *"The audit was adversarially verified and STILL had 3 wrong backend rows. Assume the
same rate remains."* It does. **These were found by opening the files. They change the shape of the
build. Do not plan against the doc's claim — these ARE the corrected claims.**

### 3.1 🔴 T9 NEEDS **ZERO** BACKEND WORK. `access_level` ALREADY SHIPS.

Spec 29's **D10** says Phase C *"adds the caller's effective grant to the book read (`my_grant_level`)"*, and
plan 30 §4 row 29 says **"T9: no `my_grant_level` anywhere."**

**Both are WRONG.** `book-service` **already computes and returns the caller's effective grant** on the book
read, and has done for a long time:

```go
// services/book-service/internal/api/server.go:956-957  (getBookByID)
  CASE WHEN b.owner_user_id=$2 THEN 'owner'
       ELSE COALESCE((SELECT role FROM book_collaborators bc
                      WHERE bc.book_id=b.id AND bc.user_id=$2),'none') END AS access_level
// …and it is in the JSON body:
// services/book-service/internal/api/server.go:987   "access_level": accessLevel,
```

It ships on **four** surfaces: `GET /v1/books/{book_id}` (`server.go:987`), `GET /v1/books` LIST
(`server.go:885`), favorites (`favorites.go:148`), and the book MCP read tools
(`mcp_tools_read.go:44,124`). Values: **`owner` | `manage` | `edit` | `view` | `none`**
(`roleToLevel`, `collaborators.go:51`).

`grep -rn "access_level" frontend/src` → **ZERO hits.** The field crosses the wire on every book read today
and the frontend throws it away — it is not even declared on the `Book` type (`features/books/api.ts:6-24`).

> **INSTRUCTIONS (binding):**
> 1. **T9 is a PURE FRONTEND slice** (T-C5). **Write no Go.** Do not add a `my_grant_level` column, field,
>    or route.
> 2. 🔴 **DO NOT introduce the name `my_grant_level`.** The concept already has a name — **`access_level`**.
>    Plan 30's own registration discipline is *"one name for one concept"* (§8.0 item 3 killed the
>    `references`/`reference-shelf` near-miss for exactly this). Minting a second name for a shipped field is
>    the identical defect. **Everywhere spec 29 says `my_grant_level`, read `access_level`.**
> 3. Consume it from the **SINGLE-book read** (`booksApi.getBook`, `features/books/api.ts:156`), which is
>    **proven** to carry it. The LIST also carries it, but memory
>    `fe-status-default-fallback-signals-backend-field-omission` says: never assume a LIST carries a field the
>    detail read has — and `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent` says a
>    fallback default across a list is exactly how "everything shows the same wrong status" ships.
> 4. **Consequence:** Phase C is **translation-service + frontend**. book-service is **out of the wave**.
>    It is still ≥2 services ⇒ **the live-smoke gate still holds.**

### 3.2 🔴 The `target_language` MCP enum has a working precedent IN THE SAME FILE.

Spec 29 says the MCP arg *"becomes a real enum"* and stops there. The mechanism is already proven **12 lines
of the same file away**:

```python
# services/translation-service/app/mcp/server.py:939  (translation_job_control)
    action: Annotated[Literal["cancel", "pause", "resume", "retry"], "…"],
```

FastMCP derives the JSON-Schema `enum` from a Python `Literal`. Use that. **See §3.2a for the drift guard —
a hand-copied 18-item Literal that silently diverges from the registry is the whole bug we are fixing,
one layer up.**

⚠ **And the load-bearing half** (memory `knowledge-mcp-three-schema-sources-fastmcp-strips`): **the FastMCP
tool-function SIGNATURE is the schema that is advertised AND the one FastMCP validates against — it STRIPS
any arg not in the signature before the handler runs.** So the enum MUST live on the signature. A pydantic
model or a hand-written schema elsewhere would be advertised and then bypassed. That memory records a bug
that **3143 unit tests missed and a live-smoke caught.** Slice **T-C3** therefore asserts on the *live
advertised `inputSchema`*, not on the Python annotation.

### 3.2a The registry is the SSOT — the enum is a MIRROR, and it needs a mechanical guard.

D13: *"`LANGUAGE_REGISTRY` is the single source of truth for `target_language`."* There will now be **three**
materializations (TS registry, `contracts/languages.contract.json`, Python registry) plus the MCP `Literal`. Memory
`css-var-duplicated-across-two-consumers-drifts` is the exact failure mode. **Every one of the three gets a
parity test in T-C1, and the `Literal` gets a `get_args` drift assertion in T-C3.** No exceptions.

> ## 🔴 THE FILE'S NAME IS SEALED — PO DECISION D-4 (2026-07-13)
>
> The contract file is **`contracts/languages.contract.json`**. **This is not a stylistic choice and it is not
> negotiable.**
>
> | ✅ **`contracts/languages.contract.json`** | the **CONTENT** language axis — *what a book can be translated INTO* (`en`, `vi`, `zh-CN`, …). Mirrors the proven cross-language-SSOT shape of **`contracts/frontend-tools.contract.json`** — the same generate-and-machine-check pattern, deliberately. |
> |---|---|
> | 🔴 **`contracts/language-rule.yaml`** — **ALREADY EXISTS. DIFFERENT THING.** | the **PROGRAMMING** language axis — *service → Go / Python / TypeScript / Rust* (CLAUDE.md's language rule, linted by `scripts/language-rule-lint.sh`). |
>
> **⇒ NEVER name it `languages.yaml`.** Two files one letter apart, both under `contracts/`, both about
> "language", meaning **completely different axes** — that is the *one-name-for-one-concept* drift this repo
> legislates against, and it would be a **permanent** trap for every future agent.
> **Also not `languages.json`** (the first draft's name — §3.6 row 9 already corrected it; it loses the
> `.contract.` marker that says *"machine-checked, generated, do not hand-edit"*).
>
> **If you find any reference in this plan, spec 29, or the code to `languages.yaml`, it is WRONG — fix it to
> `languages.contract.json`.** *(Verified at reconcile time: zero such references exist. Keep it that way.)*

### 3.3 D9 is implementable — the API layer already carries the HTTP status.

Spec 29's D9 (*"errors are typed, not stringified"*) needs the FE to distinguish 403 from 5xx. It can:

```ts
// frontend/src/api.ts:159-161
throw Object.assign(new Error(err?.message || detailMessage || res.statusText), {
  status: res.status,
  code: err?.code,
```

The thrown `Error` carries **`.status`** (HTTP) and **`.code`** (the backend's error code).
`TranslateModal.tsx:250-251` already reads `.code`. **No API-layer change is needed for D9.**

### 3.4 There are **FIVE** target-language input surfaces, not three.

Spec 29 (§"`TRANSLATION_TARGETS` and the three language inputs") names three. A `grep` finds **five**:

| # | Surface | Fed from | Slice |
|---|---|---|---|
| 1 | `components/shared/LanguagePicker.tsx:45` | `LANGUAGE_NAMES` | T-C4 |
| 2 | `pages/book-tabs/TranslateModal.tsx:320-329` (hand-rolled `<select>`) | `LANGUAGE_NAMES` | T-C4 |
| 3 | `features/glossary/components/BatchTranslateDialog.tsx:26-29` (free-text + regex — **S7**) | free text | T-C4 |
| 4 | **`features/studio/panels/ChapterBrowserTitleView.tsx:327`** (its own `<select>`) — **MISSED BY THE SPEC** | `LANGUAGE_NAMES` | T-C4 |
| 5 | **`features/glossary-translate/StepConfig.tsx:61`** (`Object.keys(LANGUAGE_NAMES)`) — **MISSED BY THE SPEC** | `LANGUAGE_NAMES` | T-C4 |

**T-C4 consolidates all five.** Today `TRANSLATION_TARGETS === LANGUAGE_REGISTRY` (all 18 entries carry
`translationTarget: true`), so this removes **zero** options from **any** picker — exactly as D13 promises.
It makes the flag load-bearing.

### 3.5 ⚠ There is **NO HTML DRAFT** for spec 29 — recorded, not skipped.

`design-drafts/screens/studio/` has 24 files; **none is a translation draft** (plan 30 §8.3's "Not yet
drafted" list includes 25–29). The run brief says *"the mock IS the acceptance criterion for the UI."*

**There is no mock.** This is not a blocker and does **not** need one: plan 30 §8.3's rule is *"Every **panel
proposed in this plan** needs one"* — and **Wave T proposes no panel.** It repairs shipped surfaces whose
layout is unchanged.

> **INSTRUCTION:** The acceptance criterion for Wave T is **spec 29's D1–D13 + its "Verify gate" section**,
> which are unusually precise (they name the exact assertions). Use them. **Do not stall waiting for a draft,
> and do not invent a new layout** — every slice below is a behavior fix inside an existing layout. This
> decision is recorded in §9 (Risks, R5).

### 3.6 🔴 THE RECONCILIATION LEDGER — where the ADJUDICATION overruled this plan

The adjudication (`docs/plans/studio-adjudication/wave-T-decisions.md`) was settled against source **after**
this plan's first draft. **Every row below is a place the plan was WRONG and has been rewritten.** They are
listed here so a builder who has already read the old plan is not confused, and so nobody "restores" the old
behavior thinking it was intentional. **Do not re-litigate any of these.**

| # | The plan said (WRONG) | The decision says (BINDING) | Where |
|---|---|---|---|
| 1 | Header CTA `disabled={chapters.length === 0}` | **Gate on the chapters query's TRI-STATE.** `chapters.length === 0` collapses *loading* / *fetch-failed* / *genuinely-empty* into one — the exact "error rendered as a benign fact" class as T10 itself. **A retryable error leaves the CTA ENABLED** (the modal fetches its own chapters). | `Q-29-D1-CTA-DURING-LOAD` → **T-A2** |
| 2 | Header checkbox = **select ALL chapters** book-wide | **PAGE-SCOPED header checkbox + a separate, counted "Select all N chapters" link** (the repo's existing Gmail pattern, shipped twice). A header checkbox that silently swallows 1,900 off-screen chapters can **launch a huge paid LLM job the user never saw** — the run's CRITICAL paid-action class. | `Q-29-D4-SELECT-ALL-LABEL` → **T-A3** |
| 3 | `CHAPTER_LOAD_TIMEOUT_MS = 15_000` + `AbortSignal.any` | **`12_000`**, per HTTP request, via a **hand-rolled `timeoutSignal`**. 8–10 s would RACE the measured 5-10 s proxy connect-timeout and turn a classifiable 502 into a generic client timeout. `AbortSignal.any/timeout` is **unusable under jsdom + vitest fake timers**. | `Q-29-D8-TIMEOUT-DURATION` → **T-A5** |
| 4 | Error helper = `features/translation/lib/apiError.ts`, 3 kinds | **`frontend/src/lib/classifyApiError.ts`**, 9 kinds, `retryable: boolean`, `messageKey`, and 🔴 **the T4 guard: `detail` is `undefined` when `code === 'PARSE_ERROR'`** — that is the exact carrier of the raw proxy string (`api.ts:102`). A 3-kind helper without that guard **does not fix T4.** | `Q-29-D9-ERROR-TAXONOMY` → **T-A1** |
| 5 | D7: "queue the settings `PUT` until the GET settles (`pendingSave` ref)" | 🔴 **DELETE the auto-`PUT` entirely.** It is not "surprising" — it is **cross-user corrupting** (X2 above). Queueing it *preserves the clobber.* Replace with an explicit, **unchecked-by-default** `Remember as this book's default` checkbox that PUTs only on submit. | `Q-29-D7-BOOK-SETTINGS-WRITE-SIDEEFFECT` → **T-A5** |
| 6 | T-C2 validates **7** Pydantic models, incl. `SaveEditedTranslationRequest` + `PatchTranslationBlockRequest` | 🔴 **Those two are ROW-ANCHORED and MUST NOT be validated.** They already 422 (`TRANSL_LANG_MISMATCH`) unless the body's value **equals the stored row's**, so they cannot introduce a novel language. Enum-ing them **locks a user out of editing their own legacy `Vietnamese` versions.** The real set is **6 NOVEL-VALUE writers** — and it includes two the plan missed (`glossary_translate.py`, `internal_dispatch.py`). | `BE-29-LANG-WRITE-VALIDATION` → **T-C2** |
| 7 | T-C3 enums **4** MCP args, including `translation_segment_status` (`:220`) | **`:220` is a READ arg — leave it a free string.** Enum-ing a read arg makes the legacy `Vietnamese` rows **unreadable by the agent** before the backfill lands — a direct breach of D13's read-side tolerance. **Enum the 3 WRITE args only.** | `BE-29-LANG-WRITE-VALIDATION` §4 → **T-C3** |
| 8 | Python mirror = a **code list** (`TRANSLATION_TARGET_CODES: tuple[str, ...]`) | 🔴 **Mirror ROWS + BOTH FLAGS.** `uiLocale` and `translationTarget` are **independent axes**; today all 18 rows set both, which is *a coincidence of the seed data, not an invariant*. **"A parity test that compares only code lists is REJECTED at review."** | `Q-29-REGISTRY-AXIS-CONFLATION` → **T-C1** |
| 9 | Contract file = `contracts/languages.json` | **`contracts/languages.contract.json`** — matches the `frontend-tools.contract.json` precedent it is copying. | `BE-29-LANG-REGISTRY-PY` · `UC-29-NO-PY-REGISTRY-EXISTS` → **T-C1** |
| 10 | D11: `openPanel('translation-versions', { params: { chapterId } })` | 🔴 **`{ params: { chapterId, lang: undefined } }`.** dockview's `updateParameters` **MERGES** (`dockviewPanel.js:179-191`); a key is removed **only** if its value is literally `undefined`. Without it, the matrix's `lang:'en'` **leaks into a chapter that has no `en` version.** The plan's own test (`toHaveBeenCalledWith({params:{chapterId}})`) **would pass while the bug ships.** | `Q-29-D11-DOCK-ID-MIGRATION` → **T-B3** |
| 11 | S12: wire "View glossary" → `host.openPanel('glossary')` / `navigate()` | **NEITHER. Navigate NOWHERE.** The glossary is *already mounted behind the modal* — `GlossaryTranslateWizard` renders **only** from `GlossaryEntityList`, which **IS** the glossary body in both the studio panel and the legacy tab (DOCK-2, un-forked). `openPanel('glossary')` is a **no-op**; `navigate()` **tears down the whole dock**. Two buttons perform one action under two labels: **delete one, relabel the other.** | `Q-29-S12-VIEW-GLOSSARY-TARGET` → **T-C6** |
| 12 | S11 gets a **defer row** | **S11 is a ONE-LINE fix-now** (`invalidateAfterConfirm.ts:24`). A defer row for a one-line change is the exact anti-pattern CLAUDE.md's FIX-NOW rule kills, and it clears **none** of the 5 gates. **Row deleted.** | `DEF-29-S11-AGENT-REFRESH` → **T-B6** |
| 13 | T-A5: a legacy stored language "seeds the picker to `''`" | **Seed it as a visible ORPHAN OPTION + a notice + a HARD SUBMIT GATE.** Blanking it is a silent retarget of a **paid** job. And the guard must sit on **the SEED, not the prop** — `bkSettings.target_language` **can itself be legacy** (the unvalidated `PUT` at `settings.py:161` is how it got there). The spec missed that second source. | `Q-29-D6-PRESELECTED-LANG-UNKNOWN-CODE` · `Q-29-D13-LEGACY-RETRANSLATE-DEAD-END` → **T-A5** |
| 14 | i18n regen runs **per slice** (18 locales each) | **English key only during build; ONE batch `scripts/i18n_translate.py` run at wave close.** `fallbackLng: 'en'` makes the other 17 render English immediately. A missing translation is a cosmetic English string; a hardcoded literal is an unfixable one. **+ a parity test, which is the thing that actually stops the rot.** | `Q-29-D9-LOCALIZED-MESSAGES` → **T-C9** |
| 15 | §4: *"No new route is created in this entire wave"* | **False after the adjudication.** T-C7 adds an **additive query param** (`?languages_only=true`) to the coverage route. It is additive ⇒ no break — but it **is** a contract change and gets a contract row. | `UC-29-COVERAGE-IS-UNPAGED` → **T-X0** + **T-C7** |
| 16 | §5: **3** colliding tables in the backfill | **FOUR.** `segment_translations` (`UNIQUE (chapter_id, target_language, segment_index)`, `migrate.py:550-563`) collides identically — **spec 29's D12 missed it, and the migration will hard-fail on that index** without it. | `PO-29-BACKFILL-MERGE-RULES` → **§5** |

### 3.6b 🔴 WHERE THE **PO** OVERRULED BOTH THIS PLAN **AND** THE ADJUDICATION (sealed 2026-07-13)

The adjudication outranks this plan (§3.6). **The PO outranks the adjudication.** Three rows — and each one
**inverts** an instruction that appears elsewhere in this document, so if you find the old text, **this table
wins.**

| # | This plan / the adjudication SAID | The **PO** RULES (**binding**) | Where it lands |
|---|---|---|---|
| 🔴 **P-1** | §5: *"**NONE. Wave T ships zero DDL.** … If you find yourself writing a migration in this wave, you have gone off-plan."* + defer row `D-TRANSL-LANG-BACKFILL` (gate #2). | **D-1: WRITE THE MIGRATION. Then DRY-RUN it and STOP.** Rollback path + before/after row-count assertion + a dry-run report the PO reads. **The agent may NOT execute it unattended.** *(The rules were **already sealed** in §5.1 — so it was always writable; the PO simply refuses to leave a known-corrupt identity key sitting in a defer row indefinitely.)* | **§5 (rewritten)** · **slice T-C10** · `D-TRANSL-LANG-REKEY-EXECUTE` (§10) |
| 🔴 **P-2** | §1.1 + T-A4: **T8** is Wave T's to fix. §1.2: *"Wave T is independent of Waves 0–8."* | **D-2: T8 SHIPS IN WAVE 0 (`W0-S15`)** — it discards a paid job's chapter selection **today**. **Wave T must not build it twice.** ⇒ **T-A4 is re-scoped to D6 only**, and **Wave T gains one upstream dependency.** | **§1.2.0** · **§2 check 2/3** · **slice T-A4** · **§9 R2/R9** |
| 🔴 **P-3** | *(no conflict — a LOCK)* | **D-4: the content-language SSOT is `contracts/languages.contract.json`.** ⚠ **NEVER `languages.yaml`** — `contracts/language-rule.yaml` already means *service → **programming** language*. **Different axis; one name for two concepts is the drift this repo legislates against.** | **§3.2a (the name lock)** · **T-C1** |

> ⚠ **P-1 and P-2 pull in OPPOSITE directions and that is the point.** The PO **moved work OUT** of Wave T
> (T8 → Wave 0, because it damages data now) and **moved work IN** (the rekey, because leaving corrupt
> identity keys parked is worse than facing them). **Neither is a licence to re-scope anything else.**

### 3.7 🔴 THE THREE INTERNAL CONFLICTS IN THE ADJUDICATION — settled here, do not re-open

The decisions file contains **34 independently-adjudicated items**, and three pairs of them disagree. A
builder MUST NOT stall on this. **Each is settled below, with the reason.** If the PO disagrees, they veto —
but the builder builds what is written here.

**① T7's design — `Q-29-T7-NO-DESIGN` **WINS** over `D14`.**
`D14` (a bundled sub-answer inside `UC-29-NO-OPEN-QUESTIONS-REMAIN`) proposes a ghost `+ Add language` button
that just **opens `TranslateModal` preselected to this chapter**. `Q-29-T7-NO-DESIGN` — the **dedicated**
adjudication of that exact question — **refutes it by name and by code**: that is *"byte-for-byte what the
Re-translate button already does"* (`ChapterTranslationsPanel.tsx:196` + `:203-209` **already** render
`<TranslateModal preselectedChapterIds={[chapterId]}/>` from `onRetranslate`). It would add *"a duplicate
surface, zero capability, and leave the dead CTA dead."* **T7's real defect is that `VersionSidebar.tsx:86-106`
maps only languages that ALREADY have versions.** → **Build the `pendingLangs` design (T-B3).**

**② The FE normalizer — `Q-29-NORMALIZER-PARITY` **WINS**, but `isTranslationTarget` still ships.**
`Q-29-D6-PRESELECTED` and `Q-29-D13-LEGACY` both ask for `normalizeLanguageCode()` **and**
`isTranslationTarget()` on the frontend. `Q-29-NORMALIZER-PARITY` forbids a FE **normalizer** — a second
normalizer is the repo's `cross-service-normalization-bug-class`, and the one FE site that normalizes today
(`BatchTranslateDialog.tsx:27`) is **both the site S7 deletes AND already wrong** (`.toLowerCase()` yields
`zh-cn`; D13 yields `zh-CN`). Mirroring it would be **re-shipping a bug on purpose.**

> **SETTLED:** ship **`isTranslationTarget(code)` — a pure exact-match membership check over
> `TRANSLATION_TARGETS`, with NO case-folding — and ship NO `normalizeLanguageCode` on the frontend.**
> This satisfies *both*: the two decisions that "need a normalizer" actually only need the **validity check**
> (to decide *legacy vs not* over `known_languages` and over a seeded `preselectedLang`). Normalization is a
> **lenient-write-path** concern, and after T-C4 **every FE language value is a literal lifted straight out of
> `TRANSLATION_TARGETS` by a picker — a picker cannot emit a non-canonical code.** The server normalizes;
> the client validates. `Q-29-NORMALIZER-PARITY`'s **hygiene test** (T-C1) is what keeps the twin from
> coming back.
>
> ⚠ **Verified safe against live data:** the only non-canonical stored values on the dev DB are `Vietnamese`
> (89 `vi` / 5 `Vietnamese` / 5 `ja` / 3 `en` / 1 `ko`) — no `VI`, no `zh_CN`. An exact-match check
> mislabels nothing that exists.

**③ The MCP enum's blast radius — `BE-29-LANG-WRITE-VALIDATION` **WINS** over `BE-29-MCP-TARGET-LANG-ENUM`.**
`BE-29-MCP-TARGET-LANG-ENUM` enums **six** args (including the read arg `:220` and the two row-anchored
writers `:473`/`:545`) — and **flags its own choice as a PO-vetoable default whose stated cost is that "the
agent can no longer address that row."** `BE-29-LANG-WRITE-VALIDATION` refuses exactly that cost, because it
**breaks D13's read-side tolerance**, which is this wave's central invariant.

> **SETTLED: enum the THREE novel-value WRITE args only** — `translation_start_job` (`:728`),
> `translation_retranslate_dirty` (`:775`), `translation_update_settings` (`:656`).
> **Leave free-string:** `translation_segment_status` (`:220` — a **READ**), `translation_save_edited_version`
> (`:473`) and `translation_patch_block` (`:545`) — **row-anchored**, already equality-gated by
> `TRANSL_LANG_MISMATCH`, so they **cannot** introduce a novel language; they can only propagate an existing
> one. **Add a one-line comment at each of the three citing this decision, so a later agent does not "fix"
> it.** T-C3 ships a test that **fails if someone enums them.**

---

## 4 · Backend prerequisites

**There are none for Phase A or Phase B.** Both are frontend-only, against routes that already ship.

Phase C's backend work is **not a prerequisite of anything in A or B** — it is the last phase.

> 🔴 **CORRECTION (§3.6 row 15).** The first draft of this plan said *"No new route is created in this entire
> wave."* **That is now false.** `UC-29-COVERAGE-IS-UNPAGED` adds an **additive query parameter** —
> `GET /v1/translation/books/{book_id}/coverage?languages_only=true` (slice **T-C7**) — and
> `BE-29-MY-GRANT-LEVEL` requires documenting a **shipped-but-undocumented** response field
> (`Book.access_level`). **Both are contract changes ⇒ slice T-X0 (contract-first) comes BEFORE the FE
> slices that consume them.** No *new path* is created; the coverage route is not rebuilt server-side (spec
> 29 §"Out of scope" still holds — see §3.6/T-C7 for why the *reason* the spec gave was wrong).

**Routes consumed (all exist today — verified at plan time):**

| METHOD path | Grant | File | Used by |
|---|---|---|---|
| `GET /v1/translation/books/{book_id}/coverage` | VIEW | `routers/coverage.py:54` | matrix, modal |
| `GET /v1/translation/books/{book_id}/segment-coverage?target_language=` | VIEW | `routers/coverage.py:147` | matrix badges |
| `GET /v1/translation/books/{book_id}/settings` | VIEW | `routers/settings.py:94` | modal seed |
| `PUT /v1/translation/books/{book_id}/settings` | **EDIT** | `routers/settings.py:117` | modal lang/model persist |
| `POST /v1/translation/books/{book_id}/jobs` | **EDIT** | `routers/jobs.py:42` | translate submit |
| `POST /v1/translation/chapters/{chapter_id}/retranslate-dirty` | **EDIT** | `routers/jobs.py:78` | drill-down |
| `GET /v1/translation/chapters/{chapter_id}/versions` | VIEW | `routers/versions.py:62` | versions panel |
| `GET /v1/books/{book_id}` → **carries `access_level`** | VIEW | `book-service server.go:926` | **T-C5** |
| `GET /v1/books/{book_id}/chapters` | VIEW | book-service | matrix, modal |

**The EDIT/VIEW split is the whole of T9:** coverage is VIEW (`coverage.py:59`), job-create is EDIT
(`jobs.py:55`). A `view`-grant collaborator loads the matrix and is refused at submit.

---

## 5 · Migrations — 🔴 **REWRITTEN BY PO DECISION D-1 (sealed 2026-07-13)**

> ### 🔴 THE OLD TEXT SAID: *"NONE. Wave T ships zero DDL."* **THAT IS SUPERSEDED.**
>
> **The PO has ruled: REKEY the corrupted language data — but DRY-RUN FIRST.**
>
> | | |
> |---|---|
> | **What the wave BUILDS** | the migration · a **rollback path** · a **before/after row-count assertion** · a **dry-run harness** — slice **T-C10** |
> | **What the wave RUNS** | 🔴 **THE DRY-RUN ONLY.** It prints the report **and STOPS.** |
> | **What the wave MUST NOT DO** | 🔴 **EXECUTE THE MIGRATION.** *"The agent may NOT execute it unattended."* This is a **3-table** (in fact **four**-table) rekey inside `UNIQUE(chapter_id, target_language, version_num)`. **It rewrites user rows.** |
> | **Who executes it** | the **PO**, after reading the dry-run output, as an **explicit separate act** (`D-TRANSL-LANG-REKEY-EXECUTE`, §10). |
>
> **This is THE ONE CRITICAL-CLASS STOP in the whole build** (§0 rule 3, bullet 1: *"a destructive /
> irreversible action … a migration that rewrites user rows"*). Everywhere else: **blocked ≠ stopped.**
> **Here: STOP AND ASK.** ⚠ **PO approval of *the plan* is NOT approval of *the execution*.** Approval of
> the **dry-run output** is a separate act, and it has not happened when you read this.
>
> **Scale (measured live 2026-07-12):** **5 rows** say `Vietnamese` next to **89** saying `vi` (plus 5 `ja`,
> 3 `en`, 1 `ko`). **Small — and that is exactly why it is dangerous:** a 5-row rekey looks trivial, and the
> collision it hits is a **PRIMARY KEY**.

### 5.0 Why it cannot be a naive `UPDATE … SET target_language='vi'`

`target_language` is an **identity key in FOUR tables** — *not three; spec 29's D12 missed one* — and merging
`Vietnamese` → `vi` **collides in all four**:

| Object | Key | Collision |
|---|---|---|
| `chapter_translations` | `UNIQUE (chapter_id, target_language, version_num)` (`migrate.py:170-172`) | `Dracula` ch.1 has 2 `Vietnamese` + 1 `vi` version — `version_num` 1 exists twice ⇒ index violation. Needs renumbering. |
| `active_chapter_translation_versions` | `PRIMARY KEY (chapter_id, target_language)` (`migrate.py:174-181`) | ⚠ **Verified live, not hypothetical:** one chapter has **both** a `Vietnamese` **and** a `vi` active version ⇒ two rows collapse to one PK. Needs a which-version-wins rule. |
| `translation_chapter_memos` | `PRIMARY KEY (book_id, chapter_index, target_language)` (`migrate.py:219-228`) | Same shape. 1 legacy row live. |
| 🔴 **`segment_translations`** | `UNIQUE (chapter_id, target_language, segment_index)` (`migrate.py:550-563`) | **THE ONE THE SPEC MISSED.** It collides identically. **Without it in the list, the migration hard-fails on that unique index.** |

⇒ 🔴 **This is what T-C10 must get right, and what the DRY-RUN exists to prove BEFORE anything is written.**
Phase C's **T-C2** independently **stops the bleed** (write-side validation), so the bad set **stops growing**
while the rekey waits for the PO. **T-C10 dependsOn T-C2** for exactly that reason: *rekeying a set that is
still growing is a race.*

### 5.1 🔴 The rekey's rules are SEALED — they are now **T-C10's SPEC**, not a note for later

`PO-29-BACKFILL-MERGE-RULES` settled both open product questions **from existing code**, so the migration is
writable **now**, without another design round. **⚠ The old text here said "DO NOT BUILD ANY OF IT IN THIS
WAVE." PO decision D-1 REVERSES that: BUILD IT — and then STOP AT THE DRY-RUN.**

- **WHICH VERSION WINS (the active pointer) — reuse `_PROMOTE_ACTIVE_SQL`'s precedence, verbatim.** The repo
  already has exactly one conflict rule for "two candidates want to be the active version of (chapter, lang)"
  (`workers/chapter_worker.py:36-58`): ***never clobber a HUMAN-authored active version;*** otherwise the
  newer promotion wins. → winner = (a) the `authored_by='human'` candidate if exactly one is human; else
  (b) greater `set_at`; else (c) greater `created_at`; else (d) greater `id` (uuidv7 = monotonic). Delete the
  loser's **active** row only — **the losing translation row itself survives** under the canonical code and is
  one click from restoration (`versions.py:246-256`), so the merge is **non-destructive and reversible**.
- **RENUMBERING — interleave by `created_at`. The code FORBIDS the alternative.** `migrate.py:156-172` runs
  `ROW_NUMBER() OVER (PARTITION BY chapter_id, target_language ORDER BY created_at)` **on every service boot**
  (it is inside the always-executed `DDL`). So an "append legacy after canonical" numbering would be
  **silently re-interleaved at the very next restart.** Append is not a stable state in this schema;
  interleave already **is** the invariant.
- **Memos:** derived cache, non-fatal on miss (`chapter_worker.py:1074-1094`) ⇒ keep greater `created_at`,
  delete the loser. No product call needed.
- **Segments:** keep greater `translated_at`, delete the loser — safe because a missing row **already reads as
  DIRTY by design** (the `source_content_hash` staleness contract), so the deletion just re-marks a segment
  for re-translate.
- **Plain rewrites (no unique constraint, but REQUIRED):** `translation_jobs.target_language`,
  `glossary_translation_jobs.target_language`, and **especially** `book_translation_settings.target_language`
  + `user_translation_preferences.target_language` — **after T-C2 lands, a book whose stored default is
  `Vietnamese` 400s on every translate.** Normalizing these is part of the backfill, not optional.
- **The 3-pass renumber that needs no index drop:** (a) `SET version_num = 1000000 + rn` for the whole merged
  group (old langs still in place ⇒ both old partitions stay unique, and `1000000+` cannot hit `1..N`);
  (b) `SET target_language = canonical`; (c) `SET version_num = version_num - 1000000` (uniform ⇒ injective).

> 🔴 **INSTRUCTION — the knowingly-accepted consequence (D13, verbatim), which now holds only UNTIL THE PO
> EXECUTES T-C10's MIGRATION:** *"until the rekey runs, `Dracula`'s legacy `Vietnamese` column keeps rendering
> (coverage still returns it) and cannot be re-translated, because the picker no longer offers that value.
> That is the correct behaviour — the column is a record of data that exists."*
> **⇒ Wave T ships with that column still on screen. That is EXPECTED, not a bug, and T-C8 makes its dead
> ends honest rather than hiding them.**
>
> **D13 constrains what can be WRITTEN, never what can be READ.** The frontend MUST keep tolerating unknown
> codes in `known_languages`. `getLanguageName()` (`lib/languages.ts:86`) already echoes an unknown code
> rather than crashing — **keep it that way.** T-C4 ships a **read-side regression test** that proves a
> legacy `Vietnamese` column still renders.

🔴 **The old closing line here read: *"If you find yourself writing a migration in this wave, you have gone
off-plan."* IT IS REVERSED BY PO DECISION D-1.** Writing it is **on-plan** — **slice T-C10.**
**RUNNING it is off-plan.** *If you find yourself about to `python migrate.py` / `psql -f` this migration
against a real database, you have gone off-plan. STOP and hand the dry-run to the PO.*

---

## 6 · THE SLICES

Each slice = **one commit**. TDD: the failing test first, then the change.
Test parallelization (CLAUDE.md): Python runs `-n auto --dist loadgroup`; **any new test touching a real
DB/port carries `pytestmark = pytest.mark.xdist_group("pg")`.** (None of Wave T's new Python tests hit a DB
— they are all pure-function/validator/in-process-FastMCP tests — so **none needs the mark**. If you add one
that does, mark it.)

---

### ── PHASE X — CONTRACT-FIRST (must land BEFORE any FE slice that consumes these) ──

---

#### **T-X0 — Freeze the API contract + fix the spec's stale tokens** (CLAUDE.md: *"Contract-first: API contract frozen before frontend flow"*)

**dependsOn:** — **(FIRST SLICE OF THE WAVE. Nothing else starts until this commits.)**

🔴 **Why this slice exists.** CLAUDE.md's rule is *"Contract-first: API contract frozen before frontend flow."*
Wave T changes the wire in **three** ways and the first draft of this plan touched **zero** contract files:

1. **`Book.access_level`** — shipped by `book-service` on **four** surfaces since E0-2, **undocumented**, and
   **T-C5 is about to consume it**. An undocumented shipped field is a contract defect *today*.
2. **`?languages_only=true`** on the coverage route — an **additive** query param added by **T-C7**.
3. **Two new error codes** on the translation write edges (**T-C2**): `TRANSL_INVALID_TARGET_LANGUAGE` (the
   request carried a bad language) and `TRANSL_INVALID_STORED_LANGUAGE` (the request omitted it and the
   *stored* row is legacy).

**🔴 VERIFY THE PATHS BEFORE YOU WRITE — the run brief warns that other waves guessed and were wrong.**
Verified at reconcile time, `2026-07-13`:

```bash
ls contracts/api/                          # → books/ catalog/ chat-service/ composition/ composition-service/
                                           #   glossary-service/ identity/ knowledge-gateway/ knowledge-service/
                                           #   llm-gateway/ lore-enrichment/ model-billing/ model-registry/
                                           #   roleplay-service/ sharing/ travel/ world/  (+ agent-registry.yaml)
ls contracts/api/books/v1/openapi.yaml     # ✅ EXISTS — this is the books spec.
                                           #    ⚠ `contracts/api/book-service/` DOES NOT EXIST. Do not create it.
grep -n "access_level" contracts/api/books/v1/openapi.yaml   # → 0 hits. The gap is real.
ls contracts/api/translation*              # ❌ NOTHING. translation-service has NO OpenAPI spec at all.
```

**Files**

1. **EDIT** `contracts/api/books/v1/openapi.yaml` — the `Book` schema (**`:1153`**, `required:` at `:1155`,
   `properties:` at `:1156`). Add **one property**, **NOT** to `required`:
   ```yaml
        access_level:
          type: string
          enum: [owner, manage, edit, view, none]
          description: >
            The CALLER's effective grant on this book — computed per-request, NOT a property of the book.
            'owner' is synthesized from books.owner_user_id; the rest come from book_collaborators.role
            (server.go:856-857 LIST, :956-957 DETAIL; roleToLevel at collaborators.go:51-62 default-denies).
            Ships on GET /v1/books/{book_id}, GET /v1/books, favorites, and the book MCP read tools.
            Consumers MUST compare by RANK (none<view<edit<manage<owner), never by equality:
            a `=== 'edit'` check locks out `manage` and `owner`.
   ```
   🔴 **It is `access_level`. There is NO field called `my_grant_level`** — spec 29 invented that name for a
   field that already exists under another. *"One name for one concept."* (See §3.1.)

2. **CREATE** `contracts/api/translation/v1/openapi.yaml` — translation-service has **no spec**, and this wave
   both **changes** its wire (the new query param + the new error codes) and **hardens** its write edges. Per
   CLAUDE.md's anti-laziness rule, *"missing infrastructure is NOT blocked — it is unbuilt work to
   implement."* **Scope it to exactly the 9 routes this wave touches or consumes** (§4's table) — this is a
   contract for Wave T's surface, **not** a from-scratch audit of all of translation-service. Copy the header
   shape of `contracts/api/composition/v1/openapi.yaml:1-19` (`openapi: 3.0.3`, `servers: [- url: /v1/translation]`,
   `security: [- bearerAuth: []]`).

   | METHOD path | Grant | Must document |
   |---|---|---|
   | `GET /books/{book_id}/coverage` | VIEW | 🔴 **the NEW `languages_only: boolean` query param** (default `false`; when `true`, `coverage: []` + `known_languages` only — T-C7). Response `BookCoverage { book_id, coverage: CoverageRow[], known_languages: string[] }`; `CoverageRow { chapter_id, languages: map<string, CoverageCell> }`; `CoverageCell { status, version, has_active, is_glossary_stale }`. 🔴 **`known_languages` is `type: string` — NOT an enum.** It may legitimately carry a **legacy free-text value** (`Vietnamese`). **D13 constrains WRITES, never READS.** Say so in the description or a future agent will "fix" it into an enum and break the read path. |
   | `GET /books/{book_id}/segment-coverage` | VIEW | `target_language` query param — also **`type: string`, not an enum**, same reason. |
   | `GET /books/{book_id}/settings` · `PUT …/settings` | VIEW / **EDIT** | `BookSettingsPayload.target_language` → **`$ref: TargetLanguage`** (the enum). |
   | `PUT /preferences` | — | `PreferencesPayload.target_language` → **`$ref: TargetLanguage`**. |
   | `POST /books/{book_id}/jobs` | **EDIT** | `CreateJobPayload { chapter_ids, target_language?: TargetLanguage, model_source, model_ref, … }` → `201 { job_id }`. **Errors: `400 TRANSL_INVALID_STORED_LANGUAGE` · `422 TRANSL_INVALID_TARGET_LANGUAGE` · `403` (EDIT grant) · `422 TRANSL_NO_MODEL_CONFIGURED`.** |
   | `POST /chapters/{chapter_id}/retranslate-dirty` | **EDIT** | `RetranslateDirtyPayload.target_language` → **`$ref: TargetLanguage`**. Same error set. |
   | `GET /chapters/{chapter_id}/versions` | VIEW | the version-group list. **`target_language` in the RESPONSE is a free `string`** (legacy rows exist). |
   | `POST /chapters/{chapter_id}/versions/edited` · `PATCH …/blocks` | **EDIT** | 🔴 **`target_language` here is a FREE `string`, NOT the enum** — it is **row-anchored** (must EQUAL the stored version's value, `422 TRANSL_LANG_MISMATCH`). **Enum-ing it would make a legacy version un-editable.** Document *why*, inline, or someone will "tidy" it. (§3.7 ③.) |

   Plus `components/schemas`:
   ```yaml
        TargetLanguage:
          type: string
          enum: [en, vi, ja, ko, zh-CN, zh-TW, es, pt-BR, fr, de, ru, id, ms, tr, ar, hi, bn, th]
          description: >
            The closed set of translation targets. GENERATED from contracts/languages.contract.json
            (which is itself generated from frontend/src/lib/languages.ts — the SSOT, D13).
            WRITE paths only. READ paths (coverage.known_languages, versions.target_language)
            deliberately stay `type: string` so legacy free-text rows keep rendering.
        Error:
          type: object
          required: [code, message]
          properties:
            code:
              type: string
              enum: [TRANSL_INVALID_TARGET_LANGUAGE, TRANSL_INVALID_STORED_LANGUAGE,
                     TRANSL_LANG_MISMATCH, TRANSL_NO_MODEL_CONFIGURED, TRANSL_NOT_FOUND]
            message: { type: string }
            allowed:
              type: array
              items: { type: string }
              description: On TRANSL_INVALID_TARGET_LANGUAGE — the supported codes.
   ```

3. **CREATE** `contracts/api/translation/v1/README.md` — one paragraph: what the spec covers (Wave T's
   surface), what it does **not** (the rest of translation-service is undocumented — a tracked gap), and the
   🔴 **the-enum-is-write-only** rule, so the next agent does not "complete" it by enum-ing the read paths.

4. **EDIT** the spec's stale tokens — three one-line doc fixes the adjudication ordered, done here so no later
   slice carries a docs commit:
   - `docs/specs/2026-07-01-writing-studio/29_translation_repair.md:1` — `# 24 —` → **`# 29 —`**. The
     filename is authoritative; the H1 is *the only stale token in the whole repo* (a missed heading in the
     24→29 renumber; `24_plan_hub_v2.md` legitimately owns 24). ⚠ **Do NOT rewrite plan 30 line 762's
     `spec 24-H5` — that is a CORRECT reference to `24_plan_hub_v2`.** Then mark
     `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:220` resolved. *(`Q-29-SPEC-NUMBER-MISMATCH`)*
   - `29_translation_repair.md:202, 294-295, 442` — **`my_grant_level` → `access_level`** everywhere.
     *(`BE-29-MY-GRANT-LEVEL`)*
   - `29_translation_repair.md:490-492` — replace *"changing the BE contract would ripple into the MCP tools"*
     with the **true** reason: **"translation-service owns no `chapters` table (`app/migrate.py`); a
     server-side left-join would be a cross-service HTTP call to book-service + a grant relay + a new
     availability coupling. The MCP tool duplicates the SQL rather than calling the route
     (`mcp/server.py:1025`), so there is no MCP ripple."** The conclusion (keep the FE-side join) is
     **unchanged and correct** — only its reason was false, and a false reason gets re-litigated at 3am.
     *(`Q-29-OUT-OF-SCOPE-BE-JOIN`)*
   - `29_translation_repair.md:445-446` — the "Phases A and B do not carry the live-smoke gate" sentence is
     about **`workflow-gate.py`'s BE↔BE autodetect** (`scripts/workflow-gate.py:232` matches only
     `services/<name>/`), **not** an exemption from the spec's own live-browser-smoke bar.
     🔴 **Phase A carries a LIVE BROWSER SMOKE. T4/T5/T6 were found ONLY by stopping a real service.**
     Rewrite the sentence to say that, and delete D10's trailing *"and off the cross-service live-smoke
     gate"* (`:297`). *(`Q-29-PHASE-A-LIVE-SMOKE-CONTRADICTION`)*
   - `29_translation_repair.md:486` — delete *"No open questions remain. The spec is PLAN-ready."* It was
     false; the five gaps are now closed in the decisions file. Replace with a pointer to
     `docs/plans/studio-adjudication/wave-T-decisions.md`.
   - `29_translation_repair.md:327` — *"Adding a language is one registry row"* → **"Adding a translation
     target is one registry row with `translationTarget: true, uiLocale: false`. Flip `uiLocale: true` ONLY
     once `frontend/src/i18n/locales/<code>/common.json` exists. The two flags are independent axes; today
     all 18 rows set both, which is a coincidence of the seed data, not an invariant."**
     *(`Q-29-REGISTRY-AXIS-CONFLATION`)*
   - `29_translation_repair.md` §D12 — add **`segment_translations`** to the colliding-table list (§5).
     *(`PO-29-BACKFILL-MERGE-RULES`)*

**Tests**

- `contracts/api/translation/v1/openapi.yaml` and `contracts/api/books/v1/openapi.yaml` both **parse**:
  ```bash
  npx @redocly/cli lint contracts/api/translation/v1/openapi.yaml contracts/api/books/v1/openapi.yaml
  ```
  *(If `@redocly/cli` is not available, any YAML/OpenAPI parser is acceptable —
  `python -c "import yaml,sys; [yaml.safe_load(open(p)) for p in sys.argv[1:]]" <paths>` is the zero-install
  floor. **Do not skip the parse check** — a contract that does not parse is not a contract.)*
- 🔴 `services/translation-service/tests/test_openapi_target_language_enum.py` (NEW — no DB, no mark) — **the
  anti-drift lock, and the reason this slice is not just documentation.** Load
  `contracts/api/translation/v1/openapi.yaml`, read `components.schemas.TargetLanguage.enum`, and assert it
  **equals `app.languages.TRANSLATION_TARGET_CODES`** (order included). **⚠ ORDERING:** this test is written
  in T-X0 but **cannot pass until T-C1 creates `app/languages.py`.** → **In T-X0, write it `@pytest.mark.xfail(strict=True, reason="app/languages.py lands in T-C1")`; T-C1's DoD is to REMOVE the xfail and see it pass.** *(A test that
  cannot fail is not a test — `checklist-is-self-report-enforce-by-tests`. `strict=True` means it also reds
  if it starts passing early, so the xfail cannot silently rot.)*

**DoD evidence:** `"contracts: books/v1/openapi.yaml Book.access_level added (enum 5, not required); contracts/api/translation/v1/openapi.yaml CREATED (9 paths, TargetLanguage enum 18, read paths deliberately free-string); both parse clean; spec 29 H1 24→29, my_grant_level→access_level ×3, out-of-scope reason corrected, live-smoke sentence corrected, D12 gains segment_translations; test_openapi_target_language_enum.py xfail(strict) pending T-C1"`

---

### ── PHASE A — the reported bugs (frontend-only, no contract change) ──

> Phase A is **independently shippable** and is exactly what the user asked for. `TranslationTab.tsx` +
> `TranslateModal.tsx`. **No cross-service live-smoke gate** (single surface, no BE change) — but the
> **browser** smoke in §8 still applies.

---

#### **T-A1 — Typed errors + the always-rendered shell** (closes **T4**, **T10**; lands **D9**; sets up **D1**)

**dependsOn:** T-X0

**Why first (of Phase A):** D1 says *"T1's button is useless if it lives below `if (loading) return …` /
`if (error) return …`. Restructure so the header always renders."* Every later Phase-A slice renders into that
shell.

> 🔴 **REWRITTEN per `Q-29-D9-ERROR-TAXONOMY` (§3.6 row 4).** The first draft built a 3-kind helper at
> `features/translation/lib/apiError.ts`. **That helper does not fix T4.** T4's raw proxy string arrives as
> `{status: 500, code: 'PARSE_ERROR', message: 'Error occurred while trying to proxy: …'}` — a **500 is
> `retryable`**, so a 3-kind classifier happily hands the caller an error whose only message **IS the leak.**
> The guard has to be on **`code === 'PARSE_ERROR'`**, and it has to live in the classifier, not in each view.

**Files**

1. **CREATE** `frontend/src/lib/classifyApiError.ts` — **beside** the existing shared `readBackendError.ts`,
   **not** under `features/translation/` (the studio views need it too).

   ```ts
   export type ApiErrorKind =
     | 'network' | 'server' | 'rate_limit' | 'auth' | 'forbidden'
     | 'not_found' | 'conflict' | 'invalid' | 'timeout' | 'unknown';
   export type ClassifiedApiError = {
     kind: ApiErrorKind;
     retryable: boolean;
     status?: number;
     messageKey: string;      // → t(messageKey)
     detail?: string;         // OPTIONAL extra line — see THE T4 GUARD
   };
   export function classifyApiError(err: unknown): ClassifiedApiError
   ```

   **RULES — all derivable from `api.ts`'s throw contract (`api.ts:159-163`), no API-layer change needed:**
   - `status = (err as {status?: number}).status` · `code = (err as {code?: string}).code`.
   - **`retryable = (status === undefined) || status >= 500 || status === 429`** — plus `AbortError`/
     `TimeoutError` (T-A5's timeout) → `kind: 'timeout'`, `retryable: true`.
   - **kind:** `status === undefined` → `network` · `429` → `rate_limit` · `>= 500` → `server` ·
     `401` → `auth` · `403` → `forbidden` · `404` → `not_found` · `409`/`412` → `conflict` ·
     `400`/`422` → `invalid` · else `unknown`.
   - 🔴 **`detail` — THE T4 GUARD. Return `undefined` when `code === 'PARSE_ERROR'` OR `status === undefined`.**
     Otherwise `readBackendError(err)`.
     **Grounded in code, not taste:** a non-JSON body means the response **never came from a backend
     handler** — it is a dev-proxy / nginx / gateway transport failure, and `api.ts:102` stuffs the raw text
     into `{code: 'PARSE_ERROR', message: text}`. **That is exactly how the proxy string reached the user in
     T4.** Gate on `code` **BEFORE** calling `readBackendError`, because `readBackendError` falls back to
     `err.message`.
   - **`messageKey` → `errors.<kind>`** in `frontend/src/i18n/locales/en/common.json` (shared by studio +
     translation): `errors.network` *"Can't reach the server."* · `errors.server` *"The translation service is
     unavailable."* · `errors.rate_limit` *"Too many requests — retrying shortly."* · `errors.forbidden`
     *"You don't have access to this book's translations."* · `errors.timeout` · `errors.not_found` ·
     `errors.conflict` · `errors.invalid` · `errors.unknown`.

   > ⚠ **CORRECTION TO SPEC 29's D9 (write it into the spec):** its claim *"the proxy string may have no
   > status at all"* is **FALSE**. `frontend/vite.config.ts:33-36` registers the `/v1` proxy with **no error
   > handler**, so a dead target returns a **real HTTP 500 with a text body**. The proxy failure is
   > **5xx + PARSE_ERROR** and needs no statusless special case. (The genuinely statusless case is a `fetch`
   > rejection — DNS/offline — which is *also* retryable.)

   > **DEFAULT (PO may veto):** `classifySteeringError` (`useSteering.ts:18`) is **NOT** migrated onto this
   > helper. Its `409 → 'duplicate'` / `422 → 'cap'` mapping is domain-specific; rewriting it is scope creep
   > outside D9's blast radius. **It stays as-is.**

2. **CREATE** `frontend/src/features/translation/components/TranslationErrorState.tsx` (view-only, ~40 lines)
   - Props: `{ error: ClassifiedApiError; onRetry?: () => void }`.
   - Renders `data-testid="translation-error-state"` + `data-error-kind={error.kind}`, **`t(error.messageKey)`**,
     and `error.detail` **only when it is defined**.
   - 🔴 **Retry button IFF `error.retryable`** *(and `onRetry` given)*. **A 403 gets the grant message and NO
     Retry** (D9, verbatim) — retrying a 403 forever is pointless.

3. **THE CONSUMER LAW (D9 — enforce it in T-A1/A5/A6/B1/B4/B5/C8, and it is a `/review-impl` finding if
   broken):**
   - A view renders `t(c.messageKey)` and MAY append `c.detail` **only when defined**.
   - 🔴 **`(e as Error).message` is BANNED in every translation/studio view.** It appears today at
     `TranslationTab.tsx:165`, `TranslationViewer.tsx:48`/`:82`, `ChapterTranslationsPanel.tsx:91`,
     `useSegmentDrilldown.ts:40`/`:43`. **Replace every one.**
   - **401: do NOT add a re-auth branch.** `api.ts:109-126` already handles it (silent refresh + one retry +
     `forceLogout`) — it never reaches a studio caller as a throw. The `auth` kind exists **only** defensively
     and is terminal.
   - 🔴 **429 / terminal backoff:** in every translation/studio `useQuery`/`useMutation`, set
     `retry: (n, e) => classifyApiError(e).retryable && n < 3` — **today a terminal 403/404 is retried 3×.**

4. **EDIT** `frontend/src/pages/book-tabs/TranslationTab.tsx`
   - Surface the **chapters** query's error (**T10**): change `const { data: chaptersData } = useQuery({...})`
     (`:145`) to also destructure **`isPending: chaptersPending`** and **`error: chaptersError`** (react-query
     v5 — `isPending`, not `isLoading`). 🔴 **The query currently destructures only `data`. That is the root
     cause of T10 and of T-A2's CTA bug — one symptom, one fix.**
   - **DELETE the two early returns** at `:251-260`:
     ```tsx
     if (loading) return (<div className="space-y-3 p-6"><Skeleton …/><Skeleton …/></div>);
     if (error)   return <div className="p-6 text-sm text-destructive">{error}</div>;
     ```
     …and the `if (!coverage || chapters.length === 0)` early return at `:262-266`.
   - **Restructure** the returned JSX to: `<header/>` → `<TranslateModal/>` → `<filter/>` → **`<body/>`**,
     where `<body/>` is the ONLY thing that branches:
     - `chaptersError || coverageError` → `<TranslationErrorState error={classifyApiError(err)} onRetry={…}/>`
       — `onRetry` calls `queryClient.invalidateQueries` for **both** query keys. **Chapters error wins**
       (without chapters there is nothing to render at all).
     - `loading` → the skeleton — **now with a visible caption** (`t('matrix.loading')`). The current skeleton
       renders `innerText.length === 0`, which is literally how the bug was first reported. **A skeleton with
       no text is a bug in this codebase.**
     - `chapters.length === 0` (and NO error) → the existing `EmptyState`.
     - else → the table.
   - `const error = coverageError ? (coverageError as Error).message : ''` (`:165`) — 🔴 **DELETE.** Nothing may
     stringify a thrown error onto the screen again.
   - Set `retry: (n, e) => classifyApiError(e).retryable && n < 3` on **both** queries (the consumer law).
   - Header/filter/modal now render in **all** of these states.

5. **EDIT** `frontend/src/i18n/locales/en/common.json` — add the **`errors.*`** block (9 keys, above).
   **EDIT** `frontend/src/i18n/locales/en/translation.json` — add `matrix.loading`, `matrix.retry`.
   🔴 **`en` ONLY. Touch no other locale in this slice** — see T-C9. `fallbackLng: 'en'`
   (`i18n/index.ts:48`) makes the other 17 render the English string **immediately**, and the file's own
   docstring (`:13-14`) sanctions it: *"Partial locales are fine … a half-generated language degrades
   gracefully to English."* **A missing translation is a cosmetic English string; a hardcoded literal is an
   unfixable one.** *(Reversal of the first draft, which regenerated 18 locales per slice —
   `Q-29-D9-LOCALIZED-MESSAGES`, §3.6 row 14.)*

**Tests** — `frontend/src/lib/__tests__/classifyApiError.test.ts` (NEW)
- 🔴 **`T4: the literal payload that shipped`** — this is the test, and it must use the real string:
  ```ts
  const t4 = Object.assign(
    new Error('Error occurred while trying to proxy: localhost:3123/v1/translation/books/019eeb09-…/coverage'),
    { status: 500, code: 'PARSE_ERROR' },
  );
  const c = classifyApiError(t4);
  expect(c).toMatchObject({ kind: 'server', retryable: true, detail: undefined });
  // the anti-leak assertion — no field of the RESULT may carry the string:
  expect(JSON.stringify(c)).not.toContain('proxy');
  ```
- `403 → kind 'forbidden', retryable FALSE` · `429 → retryable true` · `409 → 'conflict'` ·
  `new TypeError('Failed to fetch')` → `kind 'network'`, `retryable true`, `detail undefined` ·
  a real backend `{status: 422, code: 'TRANSL_NO_MODEL_CONFIGURED', body:{message:'…'}}` → `detail` **IS**
  defined (proving the PARSE_ERROR gate does not swallow *genuine* backend detail).

**Tests** — `frontend/src/pages/book-tabs/__tests__/TranslationTab.errors.test.tsx` (NEW)
- `T4: a coverage 500 renders a localized message + a Retry, never the raw proxy string` — mock
  `translationApi.getBookCoverage` to reject with the **T4 payload above**;
  assert `getByTestId('translation-error-state')`, assert **`queryByText(/trying to proxy/)` is `null`**,
  assert a Retry button exists.
- `T4: a 403 renders NO Retry` — assert `data-error-kind="forbidden"` and `queryByRole('button',{name:/retry/i})`
  is null.
- `T10: a chapters 500 renders the error state, NOT "No chapters to translate"` — mock `booksApi.listChapters`
  to reject; assert `queryByText(/No chapters to translate/)` is **null**.
- `D1: the header survives the loading and error branches` — assert the header `<h3>` is in the document while
  the coverage query is pending **and** after it rejects.
- `the loading skeleton is not textless` — assert `container.textContent.trim().length > 0` while loading.
  *(This is the literal measured symptom: `innerText.length === 0` on a 1103×491 panel.)*
- `a terminal 403 is NOT retried 3×` — assert the query fn was called exactly once.

**DoD evidence:** `"vitest: classifyApiError.test.ts 7 passed (incl. the literal T4 PARSE_ERROR payload → detail undefined, no 'proxy' substring in the result), TranslationTab.errors.test.tsx 6 passed; grep '(e as Error).message' in features/translation + pages/book-tabs → 0 hits"`

---

#### **T-A2 — The header `Translate…` CTA** (closes **T1**; lands **D1**, **D2**)

**dependsOn:** T-A1

**Files** — `frontend/src/pages/book-tabs/TranslationTab.tsx`

> 🔴 **REWRITTEN per `Q-29-D1-CTA-DURING-LOAD` (§3.6 row 1).** The first draft gated the CTA on
> **`disabled={chapters.length === 0}`**. **That is the bug, not the rule.** `chapters.length === 0` collapses
> **three distinct states** — *still loading* / *fetch failed* / *genuinely empty* — into one, which is the
> **same "an error rendered as a benign fact" class as T10 itself.** And it disables the button in **exactly
> the state the user most needs it**: `TranslateModal` **fetches its OWN chapter list**
> (`fetchAllChapters`, `TranslateModal.tsx:38-54`, called at `:118`) — it **never** consumes the tab's
> `chapters` prop — so an enabled CTA is **fully functional** even when the *tab's* chapter query is in-flight
> or has failed.

- In the header's right-hand `<div className="flex items-center gap-2">` (`:284-297`), **before** the existing
  Filter button, add a `data-testid="translation-header-translate"` button (`Languages` icon,
  `t('matrix.translate_cta')`, `btn-glow … bg-primary … disabled:opacity-50 disabled:cursor-not-allowed`),
  `onClick={() => openTranslate(undefined)}`.

- 🔴 **ENABLEMENT — gate on the chapters query's TRI-STATE, never on `chapters.length` alone.**
  *(Uses `chaptersPending` / `chaptersError` — T-A1 already destructured them.)*

  | chapters-query state | CTA | Why |
  |---|---|---|
  | **`chaptersPending`** | **rendered · disabled · inline `Loader2` spinner · `aria-busy="true"` · tooltip `matrix.cta_loading_chapters`** | A spinner is **unambiguously not** the T1 missing-button bug. |
  | **`chaptersError` — retryable (5xx / network)** | 🔴 **ENABLED.** | **The modal re-fetches independently and owns its own error + Retry (D8).** Disabling here re-creates the **T4/T10 dead-end** in the state the user most needs the button. The *table region* separately renders the typed error banner + Retry (T-A1). |
  | **`chaptersError` — terminal (403 / 404)** | disabled + reason `matrix.cta_no_access` | The **only** true disable-with-reason case: the modal's own fetch cannot succeed either. Derive from `classifyApiError(chaptersError).retryable === false`. |
  | **success && `chapters.length === 0`** | disabled + reason `matrix.cta_no_chapters` | A **true fact**. D2's empty-state CTA still owns the fresh-book case. |
  | **success && `chapters.length > 0`** | **enabled** | The original T1 assertion. |

- **D1 — the CTA is UNSCOPED.** It opens the modal with **no preselection and no language**. The modal's own
  summary block (`Translate what needs it (N)`) owns scope, *because it only knows what "needs work" after the
  user has chosen a language*. A pre-scoped header button would have to commit to the book-default language
  before the user picked one — **the same mistake T8 makes.** Do not "improve" this by pre-scoping it.
- It does **NOT** depend on coverage (the modal already tolerates `coverage === null` —
  `TranslateModal.tsx:119` `.catch(() => null)`).
- **D2 — the empty-state `Start Translation` CTA STAYS** (`:346-352`). Header + empty-state coexist; different
  regions; the empty state is the discoverable primary for a fresh book. **It is not a duplicate to remove.**
- **Dead imports:** `Plus` and `AlertCircle` (`:6`) are vestigial imports of a header CTA that never existed.
  Use `Languages` (already imported); **delete `Plus` and `AlertCircle` from the import** — `npm run lint` will
  otherwise flag them.
- i18n (**`en` only** — T-C9 batches the rest): `matrix.translate_cta` ("Translate…"),
  `matrix.cta_loading_chapters`, `matrix.cta_no_access`, `matrix.cta_no_chapters`.

**Tests** — `frontend/src/pages/book-tabs/__tests__/TranslationTab.cta.test.tsx` (NEW)
- `T1: a book with ≥1 translated language renders a header Translate CTA` — the spec's own verify gate:
  render with `visibleLangs.length > 0`; assert `getByTestId('translation-header-translate')` is in the
  document. **This is the test that would have caught T1.**
- `D1: while the chapters query is PENDING the CTA is present, disabled, and aria-busy` — assert all three.
- 🔴 `D1: a chapters 500 leaves the CTA ENABLED, and clicking it OPENS the modal` — **the load-bearing one.**
  This is the assertion the first draft's `chapters.length === 0` gate would have failed.
- `D1: a chapters 403 disables it WITH an accessible reason` (and it is **still in the document** — not hidden).
- `D1: success + 0 chapters disables it with the no-chapters reason`.
- `D2: the empty-state CTA still renders on a book with zero translations` — assert **both** exist in their
  respective states.

**DoD evidence:** `"vitest: TranslationTab.cta.test.tsx 6 passed — CTA present+disabled+aria-busy while pending; ENABLED and opens the modal on a chapters 500; disabled-with-reason only on 403/404 and on a truly empty book; lint clean (Plus/AlertCircle removed)"`

---

#### **T-A3 — One row per CHAPTER, left-joined onto coverage** (closes **T2**; lands **D3**, **D4**, **D5**)

**dependsOn:** T-A1

**The bug:** `TranslationTab.tsx:383` maps **`coverage.coverage`** — coverage rows, not chapters. Backend
`coverage.py` derives rows from `chapter_translations` only (`SELECT … FROM chapter_translations ct … WHERE
ct.book_id = $1`), so **a chapter with no translation yields no row**. Live on `Dracula`: legend reads
*"Showing 4 of 8 chapters"*; the 4 untranslated chapters have no checkbox and cannot be selected.

**D3 — the matrix renders one row per *chapter*, left-joined onto coverage.** The component **already fetches
the full chapter list** (`:143-160` — *"loop-fetch ALL active chapters"*). A missing coverage row is a
legitimate all-`—` row — `cellContent` (`:18-19`) **already handles `undefined`**. **This is a pure FE fix; do
not touch the coverage SQL.**

> 🔴 **The spec's REASON for that is FALSE — and a false reason gets re-litigated at 3am, so know the real
> one** (`Q-29-OUT-OF-SCOPE-BE-JOIN`). Spec 29 says *"changing the BE contract would ripple into the MCP
> tools."* **There is no MCP ripple:** `translation_coverage` (`mcp/server.py:184-198`) **does not call the
> REST route** — it runs its **own duplicated `_COVERAGE_SQL`** (`:1025`). *Proof they are independent: they
> have already drifted* — REST's `CoverageCell` carries `is_glossary_stale` (`coverage.py:96-111`); the MCP
> SQL never selects it. **MCP consumers of the REST coverage route: ZERO.**
> **The REAL reason a server-side left-join is rejected:** **translation-service owns no `chapters` table**
> (`app/migrate.py` creates `chapter_translations` / `chapter_segments` / `segment_translations` / … —
> **no `chapters`**). Chapters live in **book-service**. So "left-join chapters server-side" is not a SQL join
> — it is a **per-request cross-service HTTP call + a grant relay + a new availability coupling** (coverage
> 500s whenever book-service is down). *That* earns the rejection.
> ⇒ **T-X0 wrote this correction into the spec. Do not re-open it.**

**Files** — `frontend/src/pages/book-tabs/TranslationTab.tsx` + a new shared helper

0. 🔴 **DEDUPE THE PAGING LOOP FIRST — `frontend/src/features/books/fetchAllChapters.ts` (NEW).**
   The identical loop exists **twice**: `TranslationTab.tsx:143-159` and `TranslateModal.tsx:38-54`
   (`fetchAllChapters`). **Extract ONE implementation** and import it in both. **Keep `TranslateModal`'s
   version's `?? Infinity` guard verbatim — it is the correct one** (a missing `total` must not collapse the
   loop to a single page).
   ```ts
   export async function fetchAllChapters(
     token: string, bookId: string, signal?: AbortSignal,
   ): Promise<Chapter[]>
   ```
   > **Home:** `features/books/`, **not** `features/translation/`, because it has a **third** consumer that is
   > neither — `ChapterEditorPage` (T-A7/X3). It wraps `booksApi.listChapters`; it belongs with `booksApi`.
   > *(The decisions file names `features/translation/fetchAllChapters.ts` in one item and "suggest
   > `features/books/fetchAllChapters.ts`" in another. Same function, and the third consumer settles it.)*

   **① PARALLELIZE THE TAIL** (`Q-29-CHAPTERS-FULL-FETCH-PERF`). `book-service` **already returns `total` in
   the FIRST page** (`server.go:1381-1382`). So: `await` page 0 (`offset=0, limit=100`) → read `total` →
   compute the remaining offsets `[100, 200, … < total]` → fetch them **with bounded concurrency (chunks of
   6 via `Promise.all`)** → **concat in offset order** so `sort_order` stays stable. **2000 chapters:
   20 serial RTTs → ~4.** 🔴 **Do NOT fan out unbounded** — a 10k-chapter book would open 99 sockets. Keep
   the existing short-page / `total ?? Infinity` terminator for the defensive case where `total` is absent.
   **② `signal` is threaded into EVERY page fetch**, and `if (signal?.aborted) throw new DOMException('aborted','AbortError')`
   at the top of each iteration/chunk — **T-A5's timeout must be able to kill the loop mid-page**, not after
   page 20 of a 2000-chapter book.

   **③ STOP RE-RUNNING IT ON EVERY TAB OPEN.** The global default is `staleTime: 30 * 1000`
   (`App.tsx:9`) — which is **why re-opening the dock tab refires all 20 requests.** Add
   **`staleTime: 5 * 60 * 1000`** to the `['chapters', bookId, 'all']` `useQuery` (`TranslationTab.tsx:145`).
   *(In-tree precedent: `GlossaryTab.tsx:30` uses `10 * 60 * 1000`.)* 🔴 **The existing `invalidate()`
   (`:166-171`) does NOT invalidate the chapter key — and MUST NOT.** Chapters change on **chapter CRUD**, not
   on a translation job; `ChaptersTab`'s own mutations already invalidate `['chapters', bookId, …]`.

   **④ ACCEPTED, DO NOT BUILD** (state in the wave close-out): *no chapter-count guard, no cap, no
   degrade-above-N.* A cap **reintroduces T2** on exactly the 2000+ chapter books the spec cites. The payload
   is **metadata-only** — `server.go:1341` selects 18 scalar columns, **no body text** (~2000 chapters ≈ a few
   hundred KB, once, cached 5 min), and **D4 already bounds the rendered DOM to one page.** If a real
   2000-chapter book later measures badly, the fix is a `chapters/index` lightweight route — **buildable, but
   not justified without profiling evidence** (CLAUDE.md defer-gate #4).

1. Build the join **once**, above the render:
   ```ts
   // D3: rows are CHAPTERS (sorted by sort_order), coverage LEFT-JOINed on.
   const coverageByChapter = useMemo(() => {
     const m = new Map<string, Record<string, CoverageCell>>();
     for (const row of coverage?.coverage ?? []) m.set(row.chapter_id, row.languages);
     return m;
   }, [coverage]);
   // D3 — mirrors the backend's default ORDER BY sort_order, created_at (server.go:1391).
   const rows = useMemo(
     () => [...chapters].sort(
       (a, b) => a.sort_order - b.sort_order || (a.created_at ?? '').localeCompare(b.created_at ?? ''),
     ),
     [chapters],
   );
   ```
2. **Move EVERY derivation off `coverage.coverage` onto `rows`** (D3 names them all — miss one and the
   selection silently diverges from what is on screen):

   | Line | Today | Becomes |
   |---|---|---|
   | `:216-220` `toggleAllChapters` | `coverage.coverage.map(r => r.chapter_id)` | **DELETED — replaced by the two-step in ③.** |
   | `:271` `allSelected` | `=== coverage.coverage.length` | **DELETED — replaced by `pageAllSelected` in ③.** |
   | `:224-237` `summaryCounts` | iterates `coverage.coverage` | iterates `rows` → `coverageByChapter.get(id)?.[lang]` |
   | `:97-112` `staleChapterIds` (**exported**) | takes `BookCoverageResponse` | **new signature** `staleChapterIds(coverageByChapter, chapterIds, visibleLangs)`. ⚠ It is exported and unit-tested — **update `coverageClassify`-adjacent tests too.** |
   | `:472` `showing_chapters` | `shown: coverage.coverage.length` | `shown: pageRows.length, total: rows.length` |
   | `:383` `tbody` map | `coverage.coverage.map((row, idx) …)` | `pageRows.map((ch) …)`, cells from `coverageByChapter.get(ch.chapter_id)?.[lang]` |
   | `:402` the `#` column | `idx + 1` (a coverage-row index!) | **`ch.sort_order`, VERBATIM** — see ②. |

3. **② The `#` column is `sort_order`, verbatim** (`Q-29-D3-SORT-ORDER-SOURCE`).
   - 🔴 **NEVER an index.** Not `idx + 1`, not `(page-1)*100 + i + 1`. Row key is **`ch.chapter_id`**.
   - `sort_order` is **dense after a reorder** (`chapter_reorder.go:134-147` rewrites the whole track) but
     **NOT dense after a trash** (`server.go:1165` flips `lifecycle_state` with no renumber). **That gap is
     TRUTH, not a bug:** the `#` must match the chapter number the user sees in the **editor**. A positional
     index would silently renumber `1, 2, 4` → `1, 2, 3` and the matrix's "chapter 7" would be a *different
     chapter* from the editor's "chapter 7" on any book that has ever trashed a chapter.
   - 🔴 **Duplicate-`#` guard** (the only real duplicate risk): the partial UNIQUE is
     `(book_id, sort_order, original_language) WHERE active` — so **two active chapters in different
     original-language tracks legitimately share slot 1** (`chapter_reorder.go:20-22`). Compute
     `const multiTrack = new Set(chapters.map(c => c.original_language)).size > 1;` and when true render a
     small **source-language chip** beside the number (`4 · en`). Rows stay distinct (keyed by `chapter_id`);
     the chip **explains the repeat instead of it reading as a render bug.**

4. **③ D4 — pagination + 🔴 the PAGE-SCOPED select-all** (`Q-29-D4-SELECT-ALL-LABEL`).
   ```ts
   import { usePagedList } from '@/components/pagination/usePagedList';
   import { Pager } from '@/components/pagination/Pager';
   const { page, setPage, pageCount, pageItems: pageRows } = usePagedList(rows, 100);
   ```
   Render `<Pager …/>` under the table. `usePagedList` slices **client-side** — `rows` is **already the
   complete list**, so paging needs **no fetch and no cap**.

   > 🔴 **REVERSAL — the first draft said *"`toggleAllChapters` selects ALL chapters, not just the visible
   > page."* THAT IS NOW WRONG.** `Translate Selected` is a **PAID action**. A header checkbox that silently
   > swallows **1,900 off-screen chapters** can launch a huge LLM job the user never saw — the run's
   > **CRITICAL paid-action class**. Adopt the repo's existing **two-step ("Gmail") pattern**, which is
   > **already implemented twice** (`ChapterListBrowser.tsx:119-171`, `GlossaryEntityList.tsx:253-296`), so
   > this is a **port, not a design**.

   ```ts
   const pageIds = pageRows.map(c => c.chapter_id);
   const pageAllSelected  = pageIds.length > 0 && pageIds.every(id => selectedChapters.has(id));
   const pageSomeSelected = !pageAllSelected && pageIds.some(id => selectedChapters.has(id));
   const togglePageChapters = () => setSelectedChapters(prev => {
     const next = new Set(prev);
     if (pageAllSelected) pageIds.forEach(id => next.delete(id));   // NEVER touches off-page ids
     else                 pageIds.forEach(id => next.add(id));
     return next;
   });
   ```
   - **Header checkbox** (`:363-368`): `checked={pageAllSelected}`, `onChange={togglePageChapters}`,
     `ref={(el) => { if (el) el.indeterminate = pageSomeSelected; }}`,
     `aria-label={t('matrix.select_page')}`, `data-testid="matrix-select-page"`.
     ⇒ *checked = every chapter **on this page**; indeterminate = some-but-not-all on this page; unchecked =
     none on this page* — **independent of off-page selection.**
   - **BOOK-WIDE select-all = a second, explicit, COUNTED step**, in the toolbar/legend row beside
     `matrix.showing_chapters`:
     - if `pageAllSelected && rows.length > pageIds.length && selectedChapters.size < rows.length` → a
       `text-primary hover:underline` button reading
       **`t('matrix.select_all_chapters', { count: rows.length })`** = *"Select all {{count}} chapters"*,
       `onClick={() => setSelectedChapters(new Set(rows.map(c => c.chapter_id)))}` (synchronous, **no fetch**).
     - else if `selectedChapters.size === rows.length && rows.length > pageIds.length` → plain text
       **`t('matrix.all_chapters_selected', { count })`** + the existing `clearSelection` link.
   - 🔴 **Selection is a `Set<chapter_id>` and MUST survive paging.** It already is one (`:133`) — do **not**
     reset it in a `useEffect` on page change (that is "useEffect for event handling", a CLAUDE.md violation
     *and* a data-loss bug). The `FloatingActionBar`'s `matrix.chapters_selected` (`:518`) already reports the
     true cross-page total — **leave it.**
   - **Page reset on data swap is the CALLER's job** (`usePagedList.ts:16-21` holds no opinion): call
     `setPage(0)` **inside the explicit `bookId` / language-filter change handler** — 🔴 **NOT in a
     `useEffect`.**

5. **④ D5 — orphan coverage rows are surfaced, never silently dropped — AND THE JOIN IS GATED.**
   A left-join by chapter hides coverage rows whose `chapter_id` is not in the active list (a **trashed**
   chapter that still has translations).
   ```ts
   const orphanCount = useMemo(() => {
     // 🔴 GATED: only meaningful once the COMPLETE chapter set has actually arrived.
     if (chaptersPending || chaptersError) return null;
     const active = new Set(rows.map(c => c.chapter_id));      // the COMPLETE array, never pageRows
     return (coverage?.coverage ?? []).filter(r => !active.has(r.chapter_id)).length;
   }, [coverage, rows, chaptersPending, chaptersError]);
   ```
   Render the footnote **only when `orphanCount !== null && orphanCount > 0`**:
   `t('matrix.orphan_note', { count: orphanCount })` → *"N translations belong to trashed chapters"*,
   `data-testid="translation-orphan-note"`.

   > 🔴 **TWO WAYS TO GET THIS WRONG, and the repo has shipped both:**
   > 1. **Joining against `pageRows`** would report ~1,900 off-page chapters as *"translations belonging to
   >    trashed chapters."* → **join against `rows` (the COMPLETE array).**
   > 2. **Not gating on the chapter query** would report **every** coverage row as an orphan while the
   >    chapters are still loading, or when their fetch **failed**. → memory
   >    `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent`. **A not-yet-loaded chapter must
   >    NEVER be reported as "trashed."** While loading or on error, render the T-A1 loading/error state and
   >    **NO footnote.**
   >
   > **Silent truncation is the anti-pattern this repo keeps shipping. Do not drop them without a word — and
   > do not invent them either.**

6. i18n (**`en` only**): `matrix.select_page`, `matrix.select_all_chapters`, `matrix.all_chapters_selected`,
   `matrix.orphan_note`, `matrix.page`, `matrix.prev_page`, `matrix.next_page`. Reuse the existing
   `matrix.clear`.

**Tests** — `frontend/src/pages/book-tabs/__tests__/TranslationTab.matrix.test.tsx` (NEW)
- `T2/D3: a coverage fixture with FEWER rows than chapters renders one row per CHAPTER` — 8 chapters, coverage
  for 4. Assert `getAllByRole('row')` in the tbody === **8**, and that the 4 uncovered rows render `—` cells
  and **have an enabled checkbox** (the T2 symptom was "no checkbox, cannot be selected").
- `D3: the # column is sort_order, with GAPS preserved` — fixture `sort_order` `[1, 2, 4]` (ch.3 trashed) ⇒
  the column renders **`1, 2, 4`**, *not* `1, 2, 3`.
- `D3: two active chapters sharing sort_order 1 in different original_language tracks BOTH render, each with a
  language chip`.
- `D3: on page 2 of a 150-chapter book the first row's # is 101` — proves the number is **not page-relative**.
- 🔴 `D4: 250 chapters — the fetch is COMPLETE, PARALLEL and BOUNDED` — mock `booksApi.listChapters`
  **offset-aware** (it MUST slice by `offset`: pages of 100/100/50, `total: 250`) with a counter recording the
  **in-flight high-water mark**. Assert: (a) all 250 reach the matrix data (**no silent truncation**),
  (b) exactly 3 calls, (c) high-water mark **> 1** (proves the tail is parallel) **and ≤ 6** (proves the
  concurrency is bounded), (d) re-mounting within `staleTime` issues **0** additional calls.
  ⚠ **A mock that ignores `offset` would false-green this whole test.**
- `D4: the selection survives a page change` — tick a chapter on page 1, go to page 2, come back, assert still
  checked; and assert `selectedChapters.size` is still 1 **while on page 2** (the set is book-wide).
- 🔴 `D4: the header checkbox is PAGE-SCOPED` — 250 chapters; click it ⇒ the FAB reads **"100 chapters
  selected"** (**not** 250) **and** the *"Select all 250 chapters"* link appears. Click that link ⇒ FAB reads
  **"250 chapters selected"**.
- `D4: unticking the header checkbox on page 2 leaves page-1's selection intact` — 150 remain selected
  (off-page ids untouched).
- `D4: selecting one row sets the header checkbox to .indeterminate === true`.
- `D5: an orphan coverage row produces the footnote` — assert `getByTestId('translation-orphan-note')` reads
  **"1 translation belongs to a trashed chapter"** (**not** 151), and the orphan row is **not** in the tbody.
- 🔴 `D5 NEGATIVE: the chapters query rejects ⇒ the error state renders and the orphan footnote is ABSENT` —
  **this is the test that proves the gate.** Without it, a failed chapter fetch reports every translation in
  the book as trashed.
- Update the existing `TranslationTab.badge.test.tsx` (it keys off coverage rows and **will** break).

**DoD evidence:** `"vitest: TranslationTab.matrix.test.tsx 11 passed — 8 rows from 4 coverage rows; # = sort_order with gaps (1,2,4); 250-ch fetch = 3 offset-aware calls, in-flight high-water 2..6, 0 refetch within staleTime; header checkbox page-scoped (100) + 'Select all 250' link; orphan footnote reads 1 and is ABSENT when the chapters query fails. grep 'coverage.coverage' TranslationTab.tsx → hits ONLY inside coverageByChapter + orphanCount"`

---

#### **T-A4 — The modal receives the LANGUAGE** (lands **D6**) · 🔴 **T8 IS NOT BUILT HERE — IT SHIPPED IN WAVE 0 (`W0-S15`)**

**dependsOn:** T-A2, T-A3, **🔴 `W0-S15` (Wave 0 — a CROSS-WAVE dependency; see §1.2.0)**

> ## 🔴 READ THIS BEFORE YOU TOUCH EITHER FILE — PO DECISION D-2 (sealed 2026-07-13)
>
> **This slice used to close T8** *("Translate Selected discards the selection")*. **It no longer does.**
> **The PO pulled T8 forward into Wave 0 as `W0-S15`**, because it *"damages data today"*: it silently
> substitutes **the whole backlog** for the chapters the user ticked, and that is a **paid LLM job the user
> did not ask for**.
>
> **⇒ T8's fix is DISCHARGED ELSEWHERE. DO NOT BUILD IT TWICE.** What is left of this slice is **D6, and only
> D6**: the *language* hand-off (`preselectedLang`) — a **separate gap** that Wave 0 does **not** close.
>
> **THE FIRST THING YOU DO IN THIS SLICE:**
> ```bash
> grep -n "preselectedChapterIds" frontend/src/pages/book-tabs/TranslationTab.tsx
> ```
> | Result | What you do |
> |---|---|
> | **present on the `<TranslateModal>` call (~:300-305)** | ✅ **W0-S15 landed.** Proceed. **ADD `preselectedLang` BESIDE IT.** Change nothing else about the selection. |
> | **absent there** (only on `ExtractionWizard` ~:544) | 🔴 **Wave 0 has not run. STOP THIS SLICE — do NOT implement T8.** Park T-A4 + its dependents (**T-A5, T-A6**, and **T-C5**'s A4 leg), **file the defer row naming `W0-S15` as the trigger**, and **build the rest of the wave.** *Blocked ≠ stopped (§0 rule 3).* |
>
> ⚠ 🔴 **THE SILENT-REVERT HAZARD.** T-A4 and W0-S15 edit **the same JSX block in the same file**. If you
> write the call site out from this plan wholesale, you will **overwrite W0-S15 with a stale version and
> un-ship it — and every test will still pass**, because you will have re-added the prop yourself. **EDIT the
> existing block. Never retype it. And NEVER `git add -A`** (three tracks share this checkout).

**What W0-S15 already did (verify, do not repeat):** added `preselectedChapterIds={[...selectedChapters]}` to
the `<TranslateModal>` call at `TranslationTab.tsx:300-305`; made the **header CTA unscoped** (it calls
`clearSelection()` before opening, per **D1** — an empty preset means "no preset", `TranslateModal.tsx:132`);
and kept the **`handleLangChange` guard** at `TranslateModal.tsx:205`.

> 🔴 **THAT GUARD IS THE TRIPWIRE, AND IT IS NOW *YOUR* PROBLEM.**
> `handleLangChange` (`:201-211`) must **NOT** re-derive the default selection when a preselection was given —
> the guard is `if (!(preselectedChapterIds && preselectedChapterIds.length > 0))`. **T-A4 is the slice that
> changes the language**, so **T-A4 is the slice most likely to "simplify" that guard away** — and doing so
> **re-introduces T8 through the back door, in a wave that is no longer even testing for T8.**
> **KEEP IT. A test below is its canary.**

**The gap that IS still open (D6):** a matrix cell carries a **language** as well as a chapter. Clicking the
`vi` column's *"not translated"* cell should open the modal **targeting `vi`** — today that cell
(`TranslationTab.tsx:458`) is `cursor-default` **dead text**, and the modal falls back to the book's default
language. **The user's click on a specific column is thrown away.**

**Files**

1. **EDIT** `frontend/src/pages/book-tabs/TranslateModal.tsx`
   - Add the prop (**D6**):
     ```ts
     /** D6: seed the target language (e.g. the matrix column the user clicked). */
     preselectedLang?: string;
     ```
   - In the load effect (`:113-155`), seed the language as
     `const lang = preselectedLang || bkSettings?.target_language || '';`
     — **but see T-A5's `seeded` ref (D7) and §3.6 row 13: the seed can itself be a LEGACY value, from EITHER
     source. T-A5 hardens it (orphan option + notice + hard submit gate). Land T-A4 first, then T-A5.**
   - 🔴 **Do NOT touch `preselectedChapterIds` or the `:205` guard.** (See the box above.)

2. **EDIT** `frontend/src/pages/book-tabs/TranslationTab.tsx` — **an ADDITIVE edit to what W0-S15 shipped.**
   - Track the language a cell click carried, and thread it through the **existing** open handler:
     ```ts
     const [translateLang, setTranslateLang] = useState<string | undefined>();
     const openTranslate = (lang?: string) => { setTranslateLang(lang); setTranslateOpen(true); };
     ```
     ⚠ **If W0-S15 already introduced an `openTranslate`/`setTranslateOpen` helper, EXTEND IT — do not add a
     second one.** *(One name for one concept.)*
   - **Add ONE prop** to the existing `<TranslateModal …>` block: **`preselectedLang={translateLang}`**.
     🔴 **Everything else in that block is W0-S15's. Leave it exactly as it is.**
   - The **header CTA** (T-A2) and the `FloatingActionBar`'s **Translate Selected** (`:521`) call
     `openTranslate(undefined)` — neither carries a single language. *(The header CTA's `clearSelection()` is
     W0-S15's, per D1 — **keep it**.)*
   - **Wire D6's hand-off — THE ONE NEW BEHAVIOR IN THIS SLICE:** make the per-cell **"not translated"** span
     (`:458`) a **button** → `openTranslate(lang)`, **with that chapter ticked**. This is the natural home for
     *"translate THIS chapter into THIS language"*, and it is what makes the language hand-off real rather
     than a prop nobody passes.

**Tests** — `frontend/src/pages/book-tabs/__tests__/TranslationTab.preselect.test.tsx`

⚠ **This file may ALREADY EXIST — `W0-S15` is expected to have created it for T8.** **EXTEND it; do not
overwrite it.** *(Overwriting it deletes T8's regression guards, and nothing would red.)*

**New (D6 — this slice):**
- `D6: clicking an untranslated cell opens the modal with THAT COLUMN's language selected` — assert the
  `<select>`'s value is the clicked lang. Render the **real** `TranslateModal` (not a spy), so the prop is
  proven to **arrive and be used**, not merely passed. *(`test-injecting-a-fake-at-the-chokepoint-cannot-prove-the-chokepoint-is-wired`.)*
- `D6: the cell is a BUTTON, not dead text` — it is reachable by keyboard and has an accessible name.
- `D6: the header CTA passes NO language` — the modal falls back to the book default.

**🔴 REGRESSION GUARDS FOR W0-S15 — RE-RUN THEM, and if they are missing, WRITE THEM. They are this slice's
canary, because this slice edits their exact lines:**
- `T8 (W0-S15): tick two chapters → open the modal → the footer reads "Translate 2 selected" and is ENABLED`.
- `T8 (W0-S15): a FULLY-TRANSLATED book still yields an ENABLED force-retranslate for the selection` — this is
  **the guard's canary**: it **fails the moment someone "cleans up" `TranslateModal.tsx:205`.**
- `D1 (W0-S15): the header CTA opens the modal UNSCOPED even when chapters are ticked`.

**DoD evidence:** `"vitest: TranslationTab.preselect.test.tsx <N> passed. 🔴 T8 was NOT re-implemented — W0-S15's preselectedChapterIds prop was VERIFIED PRESENT at TranslationTab.tsx:~300 before this slice began (grep output pasted), and this slice ADDED ONE PROP (preselectedLang) beside it. D6: clicking a 'not translated' cell (now a button, not dead text) opens the modal with THAT column's language selected — asserted on the real TranslateModal's <select> value, not a spy. W0-S15's three regression guards re-run GREEN, incl. the fully-translated-book case that canaries the handleLangChange guard at TranslateModal.tsx:205."`

---

#### **T-A5 — The modal stops wedging** (closes **T5**; lands **D7**, **D8**)

**dependsOn:** T-A4

**The bug:** `TranslateModal.tsx:113-155` awaits a `Promise.all` whose two `.catch(() => null)` guards protect
against **rejection, not latency**. There is no timeout and no error branch, and while `loading` is true the
body renders **only** `Loading chapters…` (`:308-312`) — so the target-language `<select>`, the `ModelPicker`
**and** the chapter checklist are all absent, and the footer shows a disabled `Translate 0 selected`.

Measured: with the service stopped, ~5-10 s frozen. In one run against a just-restarted service it stayed
stuck past **9 s** while the same endpoints answered a direct `fetch` in **36 ms**. **If the dependency hangs
rather than refuses, the state is permanent.**

> This is both *"press it and nothing happens"* **and** *"there is no modal to pick language"* — the modal did
> open, it just never rendered its own controls.

**Files** — `frontend/src/pages/book-tabs/TranslateModal.tsx`

1. **D8 — the spinner is scoped to the chapter checklist.** Only the checklist depends on the network.
   - **Delete the whole-body `loading ? … : …` ternary** at `:308-313`. The language `<select>`, the
     `ModelPicker`, the config warning, the summary block and Advanced **render immediately** — they need no
     network.
   - Replace `const [loading, setLoading]` with **`chaptersState: 'loading' | 'ready' | 'error'`** + a
     `chaptersError: ClassifiedApiError | null`. **Only the chapter-checklist region** branches on it.
   - On error, the checklist region renders an inline message + a **`Retry`** button
     (`data-testid="translate-chapters-retry"`) that re-runs the load. **Not** a replaced dialog body.
   - 🔴 **When `preselectedChapterIds` is present, SUBMIT STAYS ENABLED even if the chapter list fails** —
     the ids are already known (D8, verbatim). So `canSubmitSelected` must **not** depend on
     `chaptersState === 'ready'`.

2. **D8 — AbortController + timeout. 🔴 `12_000` ms, PER HTTP REQUEST.** *(`Q-29-D8-TIMEOUT-DURATION`,
   §3.6 row 3 — the first draft said 15 s / whole-loop / `AbortSignal.any`. All three are wrong.)*
   ```ts
   // TranslateModal.tsx, beside `const PAGE_SIZE = 100` (:36):
   export const CHAPTER_LOAD_TIMEOUT_MS = 12_000;
   // > the measured 5-10s proxy connect-timeout, so a REAL typed 5xx wins the race and D9 can classify it;
   // the abort then only fires on a genuine hang. Below ~11s we start eating the backend's own error.
   // ONE home for the value — no env var, no user setting (SET-1: two users would not want different values).
   ```
   - 🔴 **Per REQUEST, not per loop.** Each of `fetchAllChapters`' ~20 pages gets its **own fresh 12 s timer**,
     so a healthy 2000-chapter book (measured **36 ms**/request) never trips it, while a hung request dies in
     12 s.
   - 🔴 **Hand-roll the signal. Do NOT use `AbortSignal.timeout` / `AbortSignal.any`** — **jsdom + vitest fake
     timers must be able to drive it** (`vite.config.ts:66` `environment: 'jsdom'`):
     ```ts
     function timeoutSignal(outer: AbortSignal, ms: number): { signal: AbortSignal; done: () => void } {
       const ac = new AbortController();
       const timer = setTimeout(() => ac.abort(new DOMException('Timed out', 'TimeoutError')), ms);
       const relay = () => ac.abort(outer.reason);
       if (outer.aborted) relay();
       else outer.addEventListener('abort', relay, { once: true });
       return { signal: ac.signal, done: () => { clearTimeout(timer); outer.removeEventListener('abort', relay); } };
     }
     ```
     Every network call in the modal wraps itself in `timeoutSignal(outerSignal, CHAPTER_LOAD_TIMEOUT_MS)` and
     calls `done()` in a `finally`.
   - **Plumb `signal?: AbortSignal` through three APIs** — each is a one-line signature + one-line
     pass-through (**`apiJson` already spreads `init` into `fetch`**, `api.ts:92`, so no new infra):
     `booksApi.listChapters` (`features/books/api.ts:176`) · `translationApi.getBookCoverage`
     (`features/translation/api.ts:235`) · `translationApi.getBookSettings` (`:327`).
     *(CLAUDE.md's anti-laziness rule: a missing param is a param you write, not a blocker.)*
   - The load effect owns **ONE outer `AbortController` per open/retry**: `abort()` it in the effect cleanup
     (close / unmount / `bookId` change); **Retry creates a fresh one.**
   - **The abort must propagate INTO the shared `fetchAllChapters`' paging loop** (T-A3 §0②) — it is bounded
     `Promise.all` chunks and will keep fetching a 2000-chapter book otherwise.
   - On abort-by-timeout set a **typed** checklist error `{ kind: 'timeout', retryable: true }` (D9 —
     **do NOT stringify**). On abort/unmount, **do not setState**.

3. 🔴 **D16 — THE CONTRADICTION THE SPEC DID NOT SEE.** `TranslateModal.tsx:131` filters the preselection
   against the loaded chapter list: `preselectedChapterIds?.filter((id) => chs.some(…))`. **If the chapter
   fetch fails or times out, `chs` is `[]` and the filter ERASES the preselection** — directly contradicting
   D8's *"submit stays enabled when `preselectedChapterIds` is present even if the chapter list fails."*
   > **RULE:** apply the `chs.some(…)` filter **ONLY when the chapter load SUCCEEDED.** On failure/timeout,
   > seed `selectedChapters` from the **raw, unfiltered** `preselectedChapterIds` and **keep submit enabled.**
   > *(Without this, T-A5's own "submit stays enabled" requirement is unreachable and its test would be
   > testing a lie.)*

4. 🔴 **D7 — DELETE THE AUTO-`PUT`. It is not "surprising"; it is CROSS-USER CORRUPTING.**
   *(`Q-29-D7-BOOK-SETTINGS-WRITE-SIDEEFFECT`, §3.6 row 5 + X2. **The first draft said "queue the write until
   the GET settles." That PRESERVES the clobber.** Reversed.)*

   **The mechanism, from code — this is a tenancy defect, not a UX nit:** `settings.py:160` upserts
   **`ON CONFLICT (book_id)`** — **ONE row per book** — while `effective_settings.py:76` reads
   **`WHERE book_id=$1 AND owner_user_id=$2`** — **per-user**. And `model_ref` holds a **BYOK `user_models`
   UUID**. So an **EDIT collaborator** changing the model in the modal writes **their private model id into
   the row the OWNER reads**, and the owner's next modal seeds a `model_ref` that **cannot resolve under the
   owner's provider-registry scope.** D1 makes the modal the *primary* translate door ⇒ **this fires on
   essentially every translate.**
   **And the write is NOT load-bearing:** `submitJob` already passes `target_language` + `model_ref`
   **explicitly** (`:227-235`, whose own comment reads *"Fix-C: pass the selection directly so the job
   succeeds even if the best-effort settings save above failed"*). **Nothing breaks by not PUTting.**

   - `TranslateModal.tsx:210` — **DELETE** `void handleSaveSettings(lang, selectedModelRef);` from
     `handleLangChange`. **Keep** the rest of the handler (the selection re-derivation at `:205-209` stays —
     that is T8's guard, see R2).
   - `TranslateModal.tsx:215` — **DELETE** the `void handleSaveSettings(…)` line from `handleModelChange`; it
     becomes a one-line `setSelectedModelRef(modelRef)`.
   - 🔴 **Do NOT delete `handleSaveSettings` (`:183-199`).** `TranslateModal.tsx:192` is **the ONLY
     `putBookSettings` call site in the entire frontend** (`BookSettingsPanel` is metadata — tags/world link).
     Removing it leaves the book default **writable by no human**, violating plan 30's **GG-1**. Keep it
     unchanged, including its best-effort try/catch + `translate.settings_save_failed` toast.
   - **ADD an explicit opt-in:** `const [rememberDefault, setRememberDefault] = useState(false);` beside
     `thinkingEnabled` (`:102`); reset it to `false` in the open-effect's reset block (~`:146`). Render a
     Checkbox in the footer (`:276`), styled like the `thinking_enabled` checkbox at `:515`, label
     `translate.remember_default` ("Remember as this book's default"),
     `data-testid="translate-remember-default"`.
   - In `submitJob`, **AFTER `createJob` resolves and BEFORE `onJobCreated()`**:
     `if (rememberDefault) await handleSaveSettings(selectedLang, selectedModelRef);` — inside the existing
     try. A save failure must **not** fail the translate (satisfied by construction — `handleSaveSettings`
     already swallows into a toast).
   - 🔴 **DEFAULT IS UNCHECKED, ALWAYS.** *Considered and REJECTED:* pre-checking when `is_default === true`
     (`settings.py:112`) — **`is_default` is PER-USER, so it is ALWAYS true for a collaborator** (no row of
     theirs exists), which **re-arms the exact clobber.** The FE cannot distinguish owner from collaborator
     until `access_level` lands in T-C5. Unchecked is the **fails-closed** choice.
   - **D7's "must not PUT before the initial GET resolves" is now satisfied BY CONSTRUCTION** — **no PUT
     exists during the seeding window at all.**
   - 🔴 **KEEP the `seeded` ref.** It guards the **OTHER** race, which is still real: an in-flight
     `getBookSettings` overwriting a language the user already picked (`:126-128`). Add
     `const seeded = useRef(false)` (reset when `open` flips false→true) + `touchedLang` / `touchedModel` refs
     set in the handlers; **skip seeding any field the user has already touched.**

5. 🔴 **THE LEGACY SEED — orphan option + notice + HARD SUBMIT GATE** (`Q-29-D6-PRESELECTED-LANG-UNKNOWN-CODE`,
   §3.6 row 13. **The first draft said "seeds to `''`". That is a silent retarget of a PAID job.**)
   - Seed order: `preselectedLang` (T-A4, the raw `known_languages` string) **>** stored
     `bkSettings.target_language` **>** `''`.
   - 🔴 **THE GUARD SITS ON THE SEED, NOT ON THE PROP — the spec missed the second source.**
     `bkSettings.target_language` **can itself be legacy** (that is exactly how it got there: the unvalidated
     `PUT` at `settings.py:161`). A guard on `preselectedLang` alone leaves the book-settings door wide open.
   - If the seeded value is **not** `isTranslationTarget(...)` (§3.7 ②):
     a. **still SELECT it**, rendering it as a transient **orphan `<option value={lang}>{lang}</option>`** —
        **this is already the repo's shipped pattern** (`LanguagePicker.tsx:45-64`, `valueInOptions` /
        `showOrphanValue`, whose doc comment reads *"…it is still rendered as a selectable option so editing an
        existing resource never silently blanks an unrecognised language"*). React sees `value ∈ options` ⇒
        **no value-not-in-options warning.**
     b. render an inline notice under the picker — `translate.legacy_lang_notice` = *"'{{code}}' is a legacy
        language code from older data. It can't be used as a translation target — pick a supported language
        below."*
     c. 🔴 **GATE SUBMIT:** extend `configReady` (`:264`) to
        **`const configReady = !!selectedLang && isTranslationTarget(selectedLang) && !!selectedModelRef;`**
        so **BOTH** CTAs (`Translate N selected` **and** the force-retranslate branch) are disabled.
        **This is the fail-closed choice that prevents the user PAYING for a job the T-C2 backend will 400.**
     d. The moment the user picks any real language, the orphan option disappears and the notice clears —
        **derive both from `selectedLang`, no extra state.**
   - 🔴 **NEVER silently fall back to the book default, and NEVER auto-map an English name to a code.**
     Auto-mapping `Vietnamese` → `vi` would write into a **DIFFERENT column** (Dracula has **both**),
     contradicting D13's sealed consequence that the legacy column *"cannot be re-translated."*

**Tests** — `frontend/src/pages/book-tabs/__tests__/TranslateModal.degraded.test.tsx` (NEW)
- `T5: the language picker and the ModelPicker render IMMEDIATELY, while the chapter list is still loading`
  — a `listChapters` promise that never resolves; assert the picker is in the document **and its option list
  is populated**. **This is the "there is no modal to pick language" bug.**
- 🔴 `T5/D8: a HANGING chapter fetch times out at 12 s → inline error + Retry in the CHECKLIST REGION ONLY` —
  fake timers; `vi.advanceTimersByTime(12_000)`; assert `getByTestId('translate-chapters-retry')` **and** that
  the language picker is **still** rendered (the dialog body was NOT replaced).
- 🔴 `D8: advancing only 11_999 ms shows the SPINNER, not the error` — **pins the constant.** Without this the
  timeout value is untested and drifts.
- `D8: a rejecting chapter fetch keeps SUBMIT ENABLED when preselectedChapterIds is present` (**D16**).
- 🔴 `D16: a FAILING chapter fetch does not ERASE the preselection` — mock `listChapters` to reject; assert the
  footer still reads "Translate 2 selected". *(Without D16's fix, `chs` is `[]`, the `:131` filter empties the
  set, and the previous test passes for the wrong reason.)*
- `D8: the abort propagates — listChapters is not called again after the timeout` (call count stops growing).
- `D7: a language picked BEFORE getBookSettings resolves survives the seed` — resolve `getBookSettings` late
  with a *different* `target_language`; assert the picker still holds the user's choice. **The spec's verify
  gate names this test.**
- 🔴 `D7 ANTI-REGRESSION: changing the language AND the model issues NO putBookSettings` —
  `expect(putBookSettings).not.toHaveBeenCalled()`. **This is the test for the tenancy fix (X2).**
  ⚠ **REWRITE the existing test at `TranslateModal.test.tsx:121-133`** ("a settings-save failure surfaces a
  toast") — **it currently asserts that a language change CALLS `putBookSettings`. That assertion inverts.**
- `D7: ticking translate-remember-default → submit → putBookSettings called EXACTLY ONCE` with
  `{ model_source:'user_model', target_language:'vi', model_ref:'m1' }`, and `createJob` still called.
- `D7 (preserves Fix-B's intent): box ticked + putBookSettings rejects → toastError fires AND createJob still
  SUCCEEDED` (a failed default-save never fails the translate).
- 🔴 `D6/D13: preselectedLang="Vietnamese" ⇒ the option EXISTS and is selected, the legacy notice renders, and
  BOTH submit CTAs are DISABLED` — and assert **`translationApi.createJob` is NEVER called**. Fail the test on
  `console.error` (catches a React value-not-in-options warning).
- `D6: a legacy value arriving via BOOK SETTINGS (not the prop) is guarded identically` — **the source the spec
  missed.**
- `D6: preselectedLang absent ⇒ the book-settings language still seeds` (D7 unchanged).

**DoD evidence:** `"vitest: TranslateModal.degraded.test.tsx 12 passed — pickers render during load; 12s timeout → inline Retry (11_999ms still spinner); preselection SURVIVES a failed chapter fetch; putBookSettings NOT called on a picker change (tenancy fix) and called exactly once when 'remember' is ticked; a legacy 'Vietnamese' seed renders as an orphan option + notice with BOTH CTAs disabled and createJob never called"`

---

#### **T-A6 — The `EDIT`-grant 403 becomes readable** (lands **D10**, first half)

**dependsOn:** T-A5

**D10 (PO, 2026-07-10):** *"Phase A keeps translate actions ungated (status quo) but **must** surface the
`EDIT`-grant 403 as a readable toast — a silent 403 is the exact bug class this spec exists to kill, and
leaving it silent while fixing T5 would be incoherent."*

**Files** — `frontend/src/pages/book-tabs/TranslateModal.tsx`, `submitJob` (`:249-256`)

Today:
```ts
} catch (e) {
  const err = e as Error & { code?: string };
  if (err.code === 'TRANSL_NO_MODEL_CONFIGURED') { toast.error(t('translate.no_model_configured')); }
  else { toast.error(err.message || t('translate.failed')); }   // ← a 403 lands HERE, as a raw message
}
```
Add, **before** the generic branch:
```ts
const cls = classifyApiError(e);
if (cls.kind === 'forbidden') { toast.error(t('translate.forbidden_edit')); return; }
```
`translate.forbidden_edit` → *"You have view-only access to this book — you can't start a translation."*
**Never `err.message`** for a 403.

Do the same in `handleSaveSettings` (`:194-198`) — `PUT /settings` is **also** EDIT-gated
(`settings.py:126`), so a `view` collaborator who ticks **"Remember as this book's default"** (T-A5) gets a
silent settings-save failure today. **Same toast, same key.**

Also apply to the drill-down's re-translate (`features/translation/hooks/useSegmentDrilldown.ts` —
`retranslate-dirty` is EDIT-gated, `jobs.py:98`); its `onError` is added in **T-B5** (S2) — **use the same
`classifyApiError` + key there.**

i18n (**`en` only**): `translate.forbidden_edit`.

**Tests** — extend `TranslateModal.degraded.test.tsx`
- `D10: a 403 from createJob renders the view-only toast, never the raw message` — mock `createJob` to reject
  `{status:403}`; assert `toast.error` called with the localized string and **not** with the raw message.
- `D10: a 403 from PUT /settings renders the same toast`.

**DoD evidence:** `"vitest: 2 new assertions green — a 403 renders 'view-only access', never the raw message"`

---

#### **T-A7 — 🔴 The editor STOPS BEING UNMOUNTED by Translate workmode** (closes **X1** — *silent data loss* — and **X3**)

**dependsOn:** T-A3 *(reuses the shared `fetchAllChapters`)*

> 🔴 **NOT IN THE SPEC. Found by the adjudication (`DEF-29-EDITOR-UNMOUNT-UNTRACKED`), and it ordered:
> "FIX IT NOW — fold into spec 29's build as a slice. Do NOT write a defer row; do NOT wait for 'a separate
> spec'. It is a real data-loss bug, not a style violation."** Plan 30's **GG-4 keeps `ChapterEditorPage` live
> for the whole build**, so the bug stays user-reachable the entire time.

**X1 — the data-loss chain, grounded, not inferred:**
`TiptapEditor` takes its doc from `content` **ONCE at mount** (`TiptapEditor.tsx:122`
`const initialContent = useRef(content)` → `:169` `content: initialContent.current`; the external-sync effect
at `:188` is a **no-op after a remount** because `prevContent` is a fresh ref). `ChapterEditorPage.tsx:719`
passes `content={savedBody}` — **the LAST SAVED body**. Unsaved edits live **only** in page state `tiptapJson`
(`:177`, written by `onUpdate` `:720`). And `:1221` reads:

```tsx
{workmode !== 'translate' && editorMain}     // ← THE UNMOUNT
```

So **Write → Translate → Write**: the editor remounts showing `savedBody` ⇒ **the user's unsaved edits vanish
from the doc**, undo history is gone, **`isDirty` still reads true (the header LIES)**, and the **first
keystroke** fires `onUpdate` with `savedBody + keystroke`, **overwriting the good `tiptapJson`** — after which
`save()` (`:522`, `bodyToSave = tiptapJson ?? savedBody`) **persists the regressed body.** Silent data loss.

**Files** — `frontend/src/pages/ChapterEditorPage.tsx`

1. **`:1221`** — replace `{workmode !== 'translate' && editorMain}` with an **always-mounted, CSS-hidden**
   wrapper (the repo's own prescribed pattern — CLAUDE.md: *"Never conditionally unmount stateful components —
   use CSS `hidden` or internal branching"*):
   ```tsx
   <div className={cn('flex min-w-0 flex-1 overflow-hidden', workmode === 'translate' && 'hidden')}>
     {editorMain}
   </div>
   ```
   (`cn` is already imported and used at `:1236`.)
2. **Leave `:1222`'s `{workmode === 'translate' && <ChapterTranslationsPanel …/>}` conditional AS-IS.** The
   LOCKED rule protects the **stateful manuscript editor**, not the translations panel (which already re-keys
   on `chapterId`). **Only the editor must stay mounted.**
3. **`:1216-1220`** — the comment block currently **documents the bug** (*"Translate swaps the centre"*).
   Rewrite it: Translate **HIDES** the centre, **and why** (a remount reinitializes from `savedBody`, dropping
   unsaved `tiptapJson`).
4. ⚠ **Check the mobile shell** (`:843-850`) — it passes `editorMain` into `EditorMobileShell` as the `editor`
   group. **If that shell conditionally renders the group (`{group === 'editor' && editor}`), it unmounts the
   same editor on a mobile group switch and needs the same `hidden` treatment.** Fix it if it is a one-liner;
   otherwise raise it in the wave's `/review-impl`.

**X3 — the editor's 100-chapter blindness** *(`UC-29-CHAPTER-LIMIT-CLAMPS-100`, same file, same root cause)*
- **`ChapterEditorPage.tsx:433`** calls `listChapters(…, { limit: 200, offset: 0 })` **with no paging loop**.
  `parseLimitOffset` (`server.go:474-494`) **clamps `limit` to 100**. ⇒ on a >100-chapter book the editor's
  **prev/next nav and Chapters sidebar silently see only the first 100 chapters — chapter 101's "next" is
  dead.**
- **Fix:** call the shared **`fetchAllChapters(accessToken, bookId)`** (T-A3 §0) instead of the raw
  `limit: 200` call. *(This was masked before the clamp fix — it used to silently get 20 — so it is **not a
  regression from this run**, but it is now trivially fixable with the function T-A3 is already lifting.)*

**Tests** — `frontend/src/pages/__tests__/ChapterEditorPage.test.tsx` (extend — **the file already has the
sibling test**, `it('keeps the manuscript editor mounted in Compose mode')` at `:153`; mirror it)
- 🔴 `X1: keeps the manuscript editor mounted (hidden) in Translate mode` — drive via `workmode-switcher` →
  `workmode-item-translate` (the exact drive used at `:146-147`); assert the translations panel is visible
  **AND** `chapter-title-input` (testid at `:668`) is **still in the DOM** —
  **`toBeInTheDocument()`, NOT `toBeVisible()`.**
- 🔴 `X1 (the strong one): type into the editor → switch to translate → switch back → THE TYPED TEXT SURVIVES.`
  **This is the data-loss regression lock.** A mount-check alone can pass while the content is still reset.
- `X3: a 250-chapter book loads ALL chapters into the editor's nav` — offset-aware `listChapters` mock; assert
  chapter 101 has a working "next", and that `listChapters` was called with offsets `0/100/200`.

**DoD evidence:** `"vitest: ChapterEditorPage 3 passed — the editor stays MOUNTED (hidden) in Translate mode and typed-but-unsaved text survives a Write→Translate→Write round-trip (X1, silent data loss); a 250-chapter book paginates fully into the editor nav (X3)"`

---

### ── PHASE B — degraded mode + panel parity (frontend-only) ──

> The shared theme: **every translate surface gets a typed error state with a retry (D9), and no
> `.catch(() => null)` survives without a rendered consequence.**

---

#### **T-B1 — `ChapterTranslationsPanel` stops degrading silently** (closes **T6**)

**dependsOn:** T-A1 *(reuses `classifyApiError` + `TranslationErrorState`)*

**The bug:** `loadAll` (`ChapterTranslationsPanel.tsx:66-96`) runs a `Promise.all` in which
`versionsApi.listChapterVersions` has **no** `.catch`, so any `translation-service` failure rejects the whole
batch → one `toast.error` → `finally` clears `loading`. The panel then renders a **structurally fine,
factually empty** UI.

Live with the service down: chapter title **blank** (breadcrumb reads `— Translations`), original language
**`??`**, `LANGUAGES` containing only `Original`, **zero** versions, **no error banner anywhere**. The toast is
long gone by the time the user looks.

**Files** — `frontend/src/features/translation/components/ChapterTranslationsPanel.tsx`

- Add `const [loadError, setLoadError] = useState<ClassifiedApiError | null>(null)`.
- In `loadAll`: `setLoadError(null)` on entry; in `catch`, `setLoadError(classifyApiError(e))` **in addition
  to** the toast (keep the toast — it is the *immediate* signal; the banner is the *persistent* one).
  🔴 **`ChapterTranslationsPanel.tsx:91` currently surfaces `(e as Error).message` — DELETE it** (the D9
  consumer law, T-A1).
- **Render the banner.** After `if (loading) return …` (`:163`), add:
  ```tsx
  if (loadError) return (
    <div className={className ?? 'flex h-full items-center justify-center p-6'}>
      <TranslationErrorState error={loadError} onRetry={loadError.retryable ? () => void loadAll() : undefined} />
    </div>
  );
  ```
- **Do NOT** add a `.catch(() => null)` to `listChapterVersions` to "make it degrade gracefully". That is the
  bug. The batch **should** fail loudly.

**Tests** — `frontend/src/features/translation/components/__tests__/ChapterTranslationsPanel.error.test.tsx` (NEW)
- `T6: a listChapterVersions failure renders an error banner with a Retry, not an empty panel` — assert
  `getByTestId('translation-error-state')` and that the panel does **not** render `??` / a blank title.
- `T6: Retry re-runs loadAll` — assert the API is called a second time.
- `T6: a 403 renders no Retry`.

**DoD evidence:** `"vitest: ChapterTranslationsPanel.error.test.tsx 3 passed — service-down renders a banner, not a blank panel"`

---

#### **T-B2 — the version list refreshes after a human edit** (closes **S4**)

**dependsOn:** T-B1

**The bug:** `TranslationViewer` declares `onSaved?: (saved: ChapterTranslation) => void`
(`TranslationViewer.tsx:20`) and calls it at `:39` — but its **sole production caller**
(`ChapterTranslationsPanel.tsx:251-258`) **never passes it**. So after a human edit creates a new version, the
sidebar's version list does not refresh. *(Memory `invalidatequeries-cannot-reach-hand-rolled-state`: this
panel's state is a hand-rolled `useState`+`loadAll`, so nothing else can refresh it.)*

**Files** — `frontend/src/features/translation/components/ChapterTranslationsPanel.tsx`

```tsx
<TranslationViewer
  bookId={bookId} chapterId={chapterId} versionId={currentVersion.id}
  isActive={isActive} onSetActive={handleSetActive} onReview={onReview}
  onSaved={() => void loadAll()}          {/* S4 */}
/>
```

**Tests** — extend `ChapterTranslationsPanel.error.test.tsx` (or a new `…save.test.tsx`)
- `S4: saving a human edit re-runs loadAll so the new version appears in the sidebar` — fire the viewer's
  save; assert `versionsApi.listChapterVersions` is called again **and** the new version renders in the
  sidebar. *(Assert the EFFECT — the rendered list — not that a callback fired. `checklist-is-self-report-enforce-by-tests`.)*

**DoD evidence:** `"vitest: S4 — a saved human edit renders in the sidebar without a manual reload"`

---

#### **T-B3 — Add-a-language + ONE `translation-versions` id** (closes **T7**; lands **D11**/**S10**)

**dependsOn:** T-B1

**T7** — `VersionSidebar` offers no way to add a *new* target language: the only path is the Re-translate
modal, which is not what a user looks for when the language does not exist yet.

**D11** — `EditorPanel.tsx:351` opens **`translation-versions:${chapterId}`** with a `component` override,
while `TranslationPanel.tsx:26` opens the **bare** `translation-versions` id ⇒ **two dock tabs for one panel**,
contradicting `TranslationVersionsPanel`'s own *"params-retargeting singleton"* doc comment
(`TranslationVersionsPanel.tsx:1-10`). **The editor adopts the bare id.**

> 🔴 **T7 REWRITTEN per `Q-29-T7-NO-DESIGN` (§3.7 ①).** The first draft (and `D14`) proposed a ghost button
> that just **opens `TranslateModal` preselected to this chapter**. **That adds nothing:**
> `ChapterTranslationsPanel.tsx:196` + `:203-209` **already** render
> `<TranslateModal preselectedChapterIds={[chapterId]} …/>` from `onRetranslate` — so the "new" button would
> be **byte-for-byte the Re-translate button**, a duplicate surface with **zero capability**, and it would
> **leave the dead CTA dead.**
>
> 🔴 **T7's REAL defect: `VersionSidebar.tsx:86-106` maps ONLY languages that ALREADY have versions.** The
> fix is a **client-side PENDING language** — which also makes the near-dead
> *"no translations yet → **Translate now**"* CTA (`ChapterTranslationsPanel.tsx:226-239`) **reachable**,
> which is precisely the second requirement the spec left vague. **Zero backend work.**

**Files**

1. **EDIT** `frontend/src/features/translation/components/VersionSidebar.tsx`
   - Add props: **`pendingLangs: string[]`**, **`onAddLang: (code: string) => void`** (plus the existing
     `languages` / `originalLanguage`, used for exclusion).
   - Render each `pendingLangs` entry as an **extra row** in the language list (after the `languages.map` at
     `:86-106`), **same button shape**, but with the right-hand badge reading **`t('sidebar.no_versions')`**
     ("not translated") instead of `sidebar.ver_count`. Clicking it calls the existing `onLangChange(code)`.
   - Under the list (still inside the `px-3 py-2.5` block, before the closing `</div>` at `:108`) add a
     **`+ Add language`** text button (`data-testid="sidebar-add-language"`, i18n `sidebar.add_language`).
     It flips a local `const [adding, setAdding] = useState(false)` and renders:
     ```tsx
     <LanguagePicker
       value=""
       onChange={(code) => { if (code) { onAddLang(code); setAdding(false); } }}
       placeholder={t('sidebar.select_language')}
       exclude={[
         ...languages.map(g => g.target_language),
         ...pendingLangs,
         ...(originalLanguage ? [originalLanguage] : []),
       ]}
       data-testid="sidebar-language-picker"
     />
     ```
     *(`exclude?: string[]` is **already shipped** and documented for exactly this —
     `LanguagePicker.tsx:12-13`: *"Codes to omit from the list (e.g. languages already added elsewhere)"*.)*
     🔴 **It submits NOTHING.**
   - **Default (PO may veto):** the picker is **revealed by the link** rather than always-visible, so the
     240 px sidebar's resting state is unchanged.

2. **EDIT** `frontend/src/features/translation/components/ChapterTranslationsPanel.tsx`
   - `const [pendingLangs, setPendingLangs] = useState<string[]>([])`.
   - `handleAddLang(code)`: `setPendingLangs(p => p.includes(code) ? p : [...p, code]); handleLangChange(code);`
     — 🔴 **NO API CALL.** `handleLangChange` (`:130-142`) **already tolerates a code with no group** (`group`
     is `undefined` ⇒ `setSelectedLang(code); setSelectedVersionId(null)`), and the auto-select effect
     (`:120-128`) **already early-returns** on the missing group ⇒ nothing clobbers it. `currentVersion`
     (`:159`) is then `null` ⇒ **the EXISTING `!currentVersion` branch (`:226-239`) renders "no translations
     yet → Translate now"** — the dead CTA is now reachable.
   - In `loadAll`, after `setLanguages(versionsRes.languages)` (`:80`), **prune resolved pendings**:
     `setPendingLangs(p => p.filter(c => !versionsRes.languages.some(g => g.target_language === c)))` — once a
     job produces a real group the pending row disappears.
   - Pass `pendingLangs` + `onAddLang` to `<VersionSidebar>` (`:187-199`).
   - 🔴 **Pass the language to the modal:** `<TranslateModal …>` (`:203-209`) gains
     **`preselectedLang={selectedLang ?? undefined}`** alongside the existing `preselectedChapterIds={[chapterId]}`.
     **This is load-bearing, not cosmetic:** `TranslateModal.tsx:126-127` seeds `selectedLang` from
     `getBookSettings`, so **without it the CTA submits the BOOK-DEFAULT language, not the one the user just
     added — a silent wrong-language PAID job.**

   > **BEHAVIOUR CONTRACT (required, not merely preferred):** *"Add language" = **client-side selection
   > only**. It neither creates a group nor submits a job. Nothing is written to the DB until the user clicks
   > a submit button.* **Why it MUST be client-side:** `listChapterVersions` **derives** language groups from
   > version rows (`versions.py:97-124`) ⇒ **an "empty group" has no representation to persist.** Creating one
   > would need a new table **and** a new route. Phase B is frontend-only.

   - **KEEP the CTA at `:226-239`** (do **not** delete it) — it is now the **primary submit** for a newly
     added language.

3. **EDIT** `frontend/src/features/studio/panels/EditorPanel.tsx:351-353` — **D11**:
   ```tsx
   // was: host.openPanel(`translation-versions:${chapterId}`, { component: 'translation-versions', title: … })
   host.openPanel('translation-versions', { params: { chapterId, lang: undefined } })
   //                                                          ^^^^^^^^^^^^^^^^^ LOAD-BEARING. NOT NOISE.
   ```
   > 🔴 **`lang: undefined` IS THE BUG FIX — the first draft omitted it and the spec never saw it**
   > (`Q-29-D11-DOCK-ID-MIGRATION`, §3.6 row 10). **dockview's `updateParameters` MERGES, it does not
   > replace** (`dockview-core/…/dockviewPanel.js:179-183`: *"merge the new parameters with the existing
   > parameters"*); **a key is removed ONLY if its value is literally `undefined`** (`:189-191`).
   > The matrix passes `{chapterId, lang}`; the editor passes only `{chapterId}`. On ONE shared singleton:
   > **open chapter A from the matrix with `lang:'en'`, then hit Translate in the editor on chapter B ⇒
   > merged params `{chapterId: B, lang: 'en'}` ⇒ `initialLang='en'` LEAKS into a chapter that may have no
   > `en` version.** The per-chapter id hides this **today** — collapsing to the singleton **exposes** it.
   > **Add a code comment citing `dockviewPanel.js:183` so nobody "cleans it up."**
   - Delete the now-unused `component` / `title` overrides (the panel **self-titles** —
     `TranslationVersionsPanel.tsx:44-48`).
   - 🔴 **NO layout migration, NO id-alias.** The "orphaned tab that no longer resolves" **cannot happen**:
     dockview persists **`contentComponent`, not the id** (`toJSON`, `dockviewPanel.js:141-145`), so a saved
     legacy entry still resolves and renders the correct chapter. The layout is **per-device localStorage**
     (`lw_studio_layout_<bookId>`), not server state. **Do NOT add prune/alias code** — pruning would silently
     close a tab the user left open, to fix a purely cosmetic duplicate.
   - **Do NOT touch `translation-review:<chapterId>`** (`TranslationVersionsPanel.tsx:68`). It stays
     per-chapter **by design**; D11 is scoped to `translation-versions` only.

**Tests**
- `frontend/src/features/translation/components/__tests__/VersionSidebar.test.tsx` (NEW or extend):
  - `T7: clicking "+ Add language" reveals the picker` — and its options **EXCLUDE** every
    `languages[].target_language`, every `pendingLangs` entry, **and** `originalLanguage`.
  - `T7: selecting 'fr' fires onAddLang('fr') exactly once`.
- `frontend/src/features/translation/components/__tests__/ChapterTranslationsPanel.test.tsx` (**the T7
  regression test**): mount with `languages=[{target_language:'vi', …1 version}]`; add `fr` via the sidebar
  picker; assert (i) a **pending `fr` row** renders, (ii) the pane now shows `page.no_translations_yet` +
  `page.translate_now` (**the ex-dead branch, now on the common path**), (iii) clicking **Translate now** opens
  `TranslateModal` which **received `preselectedChapterIds=[chapterId]` AND `preselectedLang='fr'`**, and
  🔴 (iv) **NO network call fired on add** — spy `translationApi.createJob` / `versionsApi` ⇒ **0 calls.**
- `frontend/src/features/studio/panels/__tests__/EditorPanel.test.tsx` (extend):
  🔴 `D11/S10: the editor opens the BARE id with lang EXPLICITLY CLEARED` — assert `openPanel` was called with
  exactly `('translation-versions', { params: { chapterId, lang: undefined } })`; assert **`component` is
  absent**; assert the first arg **does not contain `:`**; and assert **`'lang' in call.params` is `true`**.
  ⚠ **A plain `toHaveBeenCalledWith({ params: { chapterId } })` PASSES WHILE THE BUG SHIPS** — it cannot tell
  "key absent" from "key present and undefined."
- `frontend/src/features/studio/panels/__tests__/TranslationVersionsPanel.test.tsx` (**the merge-semantics
  regression test**): mount with `params={{chapterId:'A', lang:'en'}}`; fire `onDidParametersChange` with
  `{chapterId:'B', lang: undefined}`; assert `ChapterTranslationsPanel` receives `chapterId='B'` **and
  `initialLang={null}` (NOT `'en'`)**, and that `api.setTitle` was called with the 'B' suffix.
- `frontend/src/features/studio/hooks/__tests__/useStudioLayout.test.ts`: seed localStorage
  `lw_studio_layout_<bookId>` with a **legacy** entry `{id:'translation-versions:<chapterId>',
  contentComponent:'translation-versions', params:{chapterId}}`; assert `fromJSON` is called and **does not
  throw**. **This is the evidence that no migration is owed.**
- ✅ **`panelCatalogContract.test.ts` must stay green** — this slice changes **no** catalog row.

**DoD evidence:** `"vitest: VersionSidebar 2 passed (picker excludes existing+pending+original), ChapterTranslationsPanel T7 1 passed (pending row + the ex-dead 'Translate now' CTA + preselectedLang='fr' + ZERO network calls on add), EditorPanel D11 1 passed ('lang' IS present-and-undefined), TranslationVersionsPanel retarget 1 passed (stale lang:'en' does NOT leak into chapter B), useStudioLayout legacy-restore 1 passed; panelCatalogContract green (delta 0)"`

---

#### **T-B4 — the paid-job poll can no longer spin forever** (closes **S1**)

**dependsOn:** — (independent of A/B; can be built any time in Phase B)

🔴 **This is the highest-severity item in Phase B**, and it is a live instance of the class the PO named as a
CRITICAL blocker category: *"a paid-action defect that would charge the user for nothing."*

**The bug:** `useGlossaryTranslatePolling.ts` returns `{ status, error, isTerminal, stopPolling }` (`:46`).
`StepProgress.tsx:18` destructures only **`{ status, isTerminal }`** — the hook's **`error`** and
**`stopPolling`** are consumed by **nothing**. On a failing first poll: the `catch` sets `error` (invisible),
`status` **stays `null`**, `isTerminal` stays `false`, the interval **is never cleared** ⇒ **an infinite
spinner over a job the user already paid for.**

**Files**

1. **EDIT** `frontend/src/features/glossary-translate/useGlossaryTranslatePolling.ts`
   - Add a **consecutive-failure counter**. After `MAX_CONSECUTIVE_FAILURES = 3`, call `stopPolling()` and
     leave `error` set. (Reset the counter on any successful poll — a transient blip must not kill a long job.)
   - **Terminal HTTP statuses stop immediately:** a `403` or `404` (`classifyApiError(e).retryable === false`)
     ⇒ `stopPolling()` at once. Retrying a 403 forever is pointless.
   - Return an extra `retry: () => void` that clears `error`, resets the counter, and restarts the interval.
2. **EDIT** `frontend/src/features/glossary-translate/StepProgress.tsx`
   - Destructure `{ status, error, isTerminal, retry }`.
   - When `error` is set: **render it** (localized, via `classifyApiError`) with a **Retry** button
     (`data-testid="glossary-translate-poll-retry"`) and a **Close** — never a bare spinner.
   - 🔴 **Do NOT** call `onComplete` on an error — the job's real status is unknown; a fabricated completion is
     `silent-success-is-a-bug` in its purest form.

**Tests** — `frontend/src/features/glossary-translate/__tests__/useGlossaryTranslatePolling.test.ts` (NEW)
- `S1: a persistently failing poll stops after 3 consecutive failures` — assert the interval is cleared
  (advance fake timers well past 3×3 s and assert the fetch count stops at 3).
- `S1: a 403 stops polling immediately`.
- `S1: a transient failure followed by a success keeps polling` (the counter resets).

**Tests** — `frontend/src/features/glossary-translate/__tests__/StepProgress.test.tsx` (NEW)
- `S1: a failing poll renders an error + Retry, NOT an infinite spinner` — assert the spinner is gone and
  `getByTestId('glossary-translate-poll-retry')` is present. **This is the test that would have caught S1.**
- `S1: onComplete is NOT called on a poll error`.

**DoD evidence:** `"vitest: useGlossaryTranslatePolling 3 passed, StepProgress 2 passed — the paid-job spinner now terminates and shows Retry"`

---

#### **T-B5 — the remaining swallowed errors** (closes **S2**, **S3**, **S5**, **S6**, **S8**)

**dependsOn:** T-A1, T-A6

One commit — they are one bug class (an error swallowed into a state that looks like "nothing happened") and
each fix is 1–6 lines.

| ID | File | Fix |
|---|---|---|
| **S2** | `features/translation/hooks/useSegmentDrilldown.ts:26-33` | `useMutation` has `onSuccess` but **no `onError`**; `retranslateError` is *exposed and never rendered* (the modal renders only `drill.error` — `SegmentDrilldownModal.tsx:63-64`). Add `onError: (e) => toast.error(…classifyApiError(e)…)` — and use **T-A6's `translate.forbidden_edit`** key for a 403 (`retranslate-dirty` is EDIT-gated). **AND render `retranslateError`** in `SegmentDrilldownModal` — an exposed-but-unrendered field is the same bug twice. 🔴 **`:40`/`:43` surface `(e as Error).message` — DELETE both** (D9 consumer law). ⚠ **This hook is also the THIRD re-translate dead-end (X4) — that half is T-C8.** |
| **S3** | `features/settings/TranslationTab.tsx:70` | `.catch(() => {})` on the providers+models load ⇒ a fetch error renders as the benign **"you have no models"** empty state. Set an error state and render `TranslationErrorState` instead of the empty state. *(An error rendered as a benign fact — same class as T10.)* |
| **S5** | `features/translation/components/TranslationReviewView.tsx:69-75,118` | All four initial fetches `.catch(() => null)` with **no toast** ⇒ it silently falls back to `SplitCompareView`, dropping the language pair, stats and the Confirm-name button. Add a toast + an error banner; **do not** silently downgrade the view. |
| **S6** | `features/translation/components/SplitCompareView.tsx:32,76` | A failed `getDraft` ⇒ a **blank** original pane, no fallback copy (the translation pane has one). Add the same fallback copy. |
| **S8** | `features/translation/hooks/useConfirmName.ts:59` | `catch { return 'error' }` discards the exception ⇒ a generic message, no `console.error`. Keep the `'error'` return (callers depend on it) but `console.error(e)` and surface `classifyApiError(e)`'s `messageKey` in the toast. |

Also in this slice: 🔴 **`TranslationViewer.tsx:48` and `:82` surface `(e as Error).message` — replace both**
(D9 consumer law; these are the last two of the six sites T-A1 enumerates).

**Tests** — one new file per fix, or extend the nearest existing:
- `useSegmentDrilldown.error.test.tsx`: `S2: a failing retranslate renders an error, not silence` +
  `S2: a 403 renders the view-only toast`.
- `settings/__tests__/TranslationTab.error.test.tsx`: `S3: a providers fetch failure renders an error, NOT "no models"`.
- `TranslationReviewView.error.test.tsx`: `S5: a failed initial fetch surfaces an error and does not silently fall back`.
- `SplitCompareView.test.tsx` (extend): `S6: a failed getDraft renders fallback copy, not a blank pane`.
- `useConfirmName.test.ts` (extend): `S8: the underlying error is logged and surfaced`.

**DoD evidence:** `"vitest: 5 findings (S2/S3/S5/S6/S8) — 7 new tests passed; grep '(e as Error).message' across features/translation + pages/book-tabs → 0 hits; no .catch(()=>null) without a rendered consequence remains in features/translation/**"`

---

#### **T-B6 — 🔴 The agent's confirmed `resume`/`retry` refreshes the SEGMENT grids too** (closes **S11** — *one line, NOT a defer row*)

**dependsOn:** —

> 🔴 **REVERSAL (§1.5, §3.6 row 12).** The first draft of this plan **deferred** S11
> (`D-TRANSL-S11-JOBCONTROL-EFFECTS`). The adjudication (`DEF-29-S11-AGENT-REFRESH`) read the code and found
> **the premise was wrong**: agent `resume`/`retry` **already** refresh the coverage matrix. **The residual
> gap is ONE LINE.** *"A defer row for a one-line change is the exact anti-pattern CLAUDE.md's FIX-NOW rule
> kills, and this finding clears NONE of the 5 defer gates."* **The row is deleted; the fix lands here.**

**The real (and only) gap:** `invalidateAfterConfirm`'s `translation` prefix list is `['translation']`
(`invalidateAfterConfirm.ts:24`), which **prefix-matches the query-key HEAD**. That already covers
`['translation-coverage', bookId]` (`TranslationTab.tsx:138`) and `['translation','refresh',…]`
(`ChapterTranslationsPanel.tsx:106`). But the **segment** keys — `['segment-coverage', bookId, langs]`
(`TranslationTab.tsx:184`) and `['segment-status', chapterId, lang]` (`useSegmentDrilldown.ts:21`) — have
heads that are **not** under `'translation'`, **so the confirm path misses them — while the cancel/pause
effect handler HITS them** (`translationEffects.ts:17`). **That asymmetry is the entire defect.**

**Files**

1. **EDIT** `frontend/src/features/chat/utils/invalidateAfterConfirm.ts:24`
   ```ts
   translation: ['translation', 'segment-'],
   // 'segment-' covers the matrix's segment-coverage grid + the drilldown's segment-status, whose key HEADS
   // are NOT under 'translation'. An agent-confirmed translation.job_resume / job_retry / start_job must
   // refresh them exactly like the cancel/pause effect handler already does (translationEffects.ts:17).
   ```
2. **EDIT** `frontend/src/features/studio/agent/handlers/translationEffects.ts:1-8` — **replace the
   "out of scope" comment with the TRUE statement:** *resume/retry reach the GUI through the **domain-routed
   confirm path** (`ConfirmActionCard` → `invalidateAfterConfirm('translation')`), **NOT** through this
   registry.* **A comment that documents a false premise is how S11 survived three reviews.**

**Tests** — `frontend/src/features/chat/utils/__tests__/invalidateAfterConfirm.test.ts` (extend)
- `S11: invalidateAfterConfirm(qc, 'translation') invalidates ALL FOUR keys` —
  `['translation-coverage', b]`, `['translation','refresh',b,c]`, **`['segment-coverage', b, 'vi']`**, and
  **`['segment-status', c, 'vi']`**.
- 🔴 `S11: and does NOT over-invalidate` — assert `['glossary-entities', b]` and `['kg-schema']` are **NOT**
  invalidated. **A prefix list is a blunt instrument; prove it did not get blunter.**

**DoD evidence:** `"vitest: invalidateAfterConfirm 2 passed — an agent-confirmed translation resume/retry now refreshes segment-coverage + segment-status, with zero cross-domain over-invalidation; defer row D-TRANSL-S11-JOBCONTROL-EFFECTS DELETED (fixed, not deferred)"`

---

### ── PHASE C — contract + hygiene (translation-service + frontend) ──

> 🔴 **Phase C is the first CROSS-SERVICE phase ⇒ it carries the LIVE-SMOKE gate** (§8).
> Per §3.1, **book-service is NOT in this wave** — `access_level` already ships.

---

#### **T-C1 — The language registry becomes a real, machine-checked contract** (lands **D13**, part 1)

**dependsOn:** —

**The fact that constrains this slice** (D13, verified at plan time): `lib/languages.ts:9-10` claims *"Backend
mirrors this in Python; keep the two in parity (see loreweave language registry + its parity test)."*
**No Python registry and no parity test exist** (`find -name languages.py` → nothing). **The comment asserts a
contract that was never built.** Per CLAUDE.md's anti-laziness rule, we build exactly what the comment already
promises.

**Files**

1. **CREATE** `contracts/languages.contract.json` — the cross-language machine contract, **GENERATED from the
   TS registry (which is the SSOT — D13), never hand-edited.**
   🔴 **The filename is `languages.contract.json`** (the first draft said `contracts/languages.json`) — it
   mirrors the `contracts/frontend-tools.contract.json` precedent it is copying, read by
   `services/chat-service/tests/test_frontend_tools_contract.py:68` from the repo root.
   🔴 **It carries ALL SEVEN FIELDS PER ROW, in registry order — NOT a code list:**
   ```json
   {
     "$comment": "GENERATED from frontend/src/lib/languages.ts. Regenerate: WRITE_LANGUAGES_CONTRACT=1 npx vitest run languagesContract. DO NOT HAND-EDIT.",
     "version": 1,
     "languages": [
       { "code": "en", "englishName": "English", "endonym": "English", "script": "Latn",
         "dir": "ltr", "uiLocale": true, "translationTarget": true },
       "…all 18, in LANGUAGE_REGISTRY order…"
     ]
   }
   ```
2. **CREATE** `frontend/src/lib/__tests__/languagesContract.test.ts` — 🔴 **the FE test IS the generator**
   (`languages.ts` is the SSOT). Mirrors `frontend/src/features/chat/nav/__tests__/frontendToolContract.test.ts:24`:
   read `resolve(process.cwd(), '../contracts/languages.contract.json')` and **deep-equal against
   `LANGUAGE_REGISTRY` INCLUDING ORDER AND EVERY FLAG.** Under **`WRITE_LANGUAGES_CONTRACT=1`** it **rewrites**
   the JSON and skips (copy `test_frontend_tools_contract.py:135-146`'s pattern). **No new toolchain, no
   codegen step, no `.mjs` script.**
3. **CREATE** `services/translation-service/app/languages.py` — the Python mirror.
   🔴 **MIRROR ROWS + BOTH FLAGS. A code list is REJECTED at review** (`Q-29-REGISTRY-AXIS-CONFLATION`,
   §3.6 row 8) — `uiLocale` and `translationTarget` are **independent axes**; that all 18 rows currently set
   both is *"a coincidence of the seed data, not an invariant."*
   ```python
   """Python mirror of frontend/src/lib/languages.ts (D13).
   SSOT = the TS registry. Parity is machine-checked against contracts/languages.contract.json by
   tests/test_languages_parity.py — edit one side and not the other and it REDS."""

   @dataclass(frozen=True)
   class LanguageEntry:
       code: str; english_name: str; endonym: str; script: str
       dir: str; ui_locale: bool; translation_target: bool

   LANGUAGE_REGISTRY: tuple[LanguageEntry, ...] = (...)          # the 18 rows, in TS order
   TRANSLATION_TARGET_CODES: tuple[str, ...] = tuple(e.code for e in LANGUAGE_REGISTRY if e.translation_target)
   UI_LOCALES:              tuple[str, ...] = tuple(e.code for e in LANGUAGE_REGISTRY if e.ui_locale)
   _TARGETS: frozenset[str] = frozenset(TRANSLATION_TARGET_CODES)

   def normalize_language(raw: str) -> str:
       """strip → '_'→'-' → base subtag lower-cased → region subtag UPPER-cased.
       Runs BEFORE the registry check so a lenient client is CORRECTED rather than rejected (D13):
           'VI' → 'vi'  ·  'zh_cn' → 'zh-CN'  ·  ' pt_br ' → 'pt-BR'  ·  'Vietnamese' → 'vietnamese' (→rejected)
       """
   def is_valid_target(raw: str) -> bool: ...
   def validate_target_language(raw: str) -> str:
       """normalize → membership-check. Returns the canonical code, or raises HTTPException(400, {
           "code": "TRANSL_INVALID_TARGET_LANGUAGE",   # ← the TRANSL_ prefix: every other error in this
           "message": ..., "value": raw,               #    service uses it and the FE toast mapper keys on it
           "allowed": list(TRANSLATION_TARGET_CODES),
       })."""
   ```
   🔴 **The write-path validator and the MCP enum read `TRANSLATION_TARGET_CODES` — NEVER the whole registry,
   NEVER `UI_LOCALES`.**
   ⚠ `normalize_language` must get the region case right: `zh-cn` → `zh-**CN**`, `pt_br` → `pt-**BR**`.
   *(The one FE site that normalizes today, `BatchTranslateDialog.tsx:27`, lower-cases the WHOLE string and
   yields `zh-cn` — **it is already wrong, and T-C4 deletes it.** Do not mirror it.)*
4. 🔴 **REMOVE the `xfail` from `services/translation-service/tests/test_openapi_target_language_enum.py`**
   (written in T-X0). It must now **pass** — the OpenAPI `TargetLanguage` enum == `TRANSLATION_TARGET_CODES`.
5. **EDIT** `frontend/src/lib/languages.ts` — replace the stale `:9-10` comment (*"Backend mirrors this in
   Python; keep the two in parity (see … its parity test)"* — **a contract that was never built**) with the
   truth:
   > *"Normalization is **SERVER-SIDE ONLY** (`translation-service/app/languages.py`). The FE emits canonical
   > codes from this registry and **MUST NOT normalize** — a second normalizer is the
   > cross-service-normalization bug class. The FE exports only `isTranslationTarget()` (an exact-match
   > membership check). Parity of the ROWS is machine-checked via `contracts/languages.contract.json`."*
   Add **`export function isTranslationTarget(code: string | null | undefined): boolean`** —
   `!!code && TRANSLATION_TARGETS.some(l => l.code === code)`. **Exact match, NO case-folding.** (§3.7 ②.)

**Tests** — `services/translation-service/tests/test_languages_parity.py` (NEW — **pure functions, no DB, so
NO `xdist_group` mark needed**)
- 🔴 `test_python_registry_matches_the_contract_FIELD_BY_FIELD` — read `contracts/languages.contract.json` via
  `Path(__file__).resolve().parents[3] / "contracts" / "languages.contract.json"` (identical to
  `chat-service/tests/test_frontend_tools_contract.py:68`); assert it **deep-equals `LANGUAGE_REGISTRY` —
  same order, same 7 fields, BOTH FLAGS.** **It NEVER writes** (a mismatch means *"edit `languages.py`"*, and
  the message must say so). ⚠ **A parity test that compares only code lists is REJECTED at review** — it is
  the exact conflation this guards.
- `test_normalize` — `VI→vi`, `zh_CN→zh-CN`, `ZH-cn→zh-CN`, `pt_br→pt-BR`, `" vi "→vi`, `en→en`,
  `Vietnamese→vietnamese`.
- `test_validate_accepts_the_registry` — all 18 round-trip.
- 🔴 `test_validate_rejects_Vietnamese` — raises `TRANSL_INVALID_TARGET_LANGUAGE`. **The exact bad value that
  shipped.**
- `test_validate_rejects_pl` — `pl` is not a registry row ⇒ rejected (D13: *"add a registry row to enable"*).
- 🔴 **The test must FAIL, not SKIP, if the contract file is absent** (memory
  `env-gated-integration-tests-skip-and-the-green-suite-lies`).

**Tests** — `frontend/src/lib/__tests__/languages.test.ts` (extend)
- `the TS registry deep-equals contracts/languages.contract.json` (order + all 7 fields).
- 🔴 `translationTarget and uiLocale are INDEPENDENT AXES` — for every row with `uiLocale: true`, assert
  `frontend/src/i18n/locales/<code>/` **exists** (via `import.meta.glob('../../i18n/locales/*/*.json')`), and
  no orphan bundle exists. **`uiLocale: true` is a PROMISE that a locale bundle exists** — this makes the
  copy-paste bug (a new `pl` row with `uiLocale: true` and no bundle) **red at the moment the row is added.**
- `TRANSLATION_TARGETS.map(l => l.code)` **equals** `Object.keys(LANGUAGE_NAMES)` — the machine-checked guard
  that T-C4's picker-source swap is **option-preserving at this commit**, and it **reds the day someone flips
  a `translationTarget` flag** — which is exactly when a picker option-set change should become a **conscious
  decision** rather than a silent regression.
- `isTranslationTarget`: `'vi'`→true · `'Vietnamese'`→false · `'VI'`→**false** (exact match — no case-folding
  by design; nothing on the FE produces `VI` after T-C4) · `null`/`undefined`→false.
- 🔴 **Do NOT narrow the registry.** All 18 rows keep `translationTarget: true` (`languages.ts:42-61`), so the
  existing assertion `TRANSLATION_TARGETS.length >= 15` (`languages.test.ts:87`) **stays green with no edit.**
  A builder tempted to set any row `false` is **out of scope and breaks this test.**

**Tests** — 🔴 `frontend/src/lib/__tests__/noFrontendLanguageNormalizer.test.ts` (NEW — **the mechanical guard
that makes "no FE normalizer" enforceable rather than aspirational**; modelled on
`features/studio/panels/__tests__/dockablePanelHygiene.test.ts`)
- Scan `frontend/src/**/*.{ts,tsx}` (skip `__tests__`, skip `i18n/`); **FAIL** on any `.toLowerCase()` /
  `.toUpperCase()` / `replace(/_/g` applied to an identifier matching `/lang|locale|target_language/i`.
- ⚠ **Strip `//` and `/* */` comments BEFORE matching** — memory
  `hygiene-grep-literal-token-in-comment-false-positive`: hygiene greps match literal tokens in prose.
- *(It should pass the moment T-C4 deletes `BatchTranslateDialog`'s `LANG_RE` + `.toLowerCase()` — the ONLY
  hit in the tree today. **Land the test in T-C1 as `xfail(strict=True)`-equivalent (`it.fails`) and flip it
  in T-C4**, or simply land the whole test in T-C4. Either is fine; do not land a test that cannot fail.)*

**ESCAPE HATCH (so a builder is never stuck):** if Phase C uncovers a **genuine** FE need to normalize a
user-typed code (it should not — every remaining input is a picker), **do NOT hand-write a second function.**
Extend `contracts/languages.contract.json` with a `normalization_fixtures: [[input, output], …]` table,
implement the TS twin against it, and have **BOTH** sides' tests iterate **that same table**. Note it as a
deviation in the wave's `/review-impl`.

**DoD evidence:** `"pytest: test_languages_parity.py 7 passed (field-by-field, both flags, order); test_openapi_target_language_enum.py xfail REMOVED and PASSING; vitest: languages.test.ts +5 passed (uiLocale⇄bundle axis test, isTranslationTarget), noFrontendLanguageNormalizer hygiene test in place; contracts/languages.contract.json committed (18 rows × 7 fields, registry order); regen path proven: WRITE_LANGUAGES_CONTRACT=1 npx vitest run languagesContract rewrites it"`

---

#### **T-C2 — Normalize → validate on EVERY REST write edge** (lands **D13**, part 2)

**dependsOn:** T-C1

**D13's write path, verbatim:** *"normalize, then validate against the registry."*
```
"VI"          -> normalize -> "vi"          -> in registry -> accept
"zh_CN"       -> normalize -> "zh-CN"       -> in registry -> accept
"Vietnamese"  -> normalize -> "vietnamese"  -> not in registry -> 400 invalid_target_language
"pl"          -> normalize -> "pl"          -> not in registry -> 400 (add a registry row to enable)
```

🔴 **THE RULE THAT DECIDES WHICH EDGES** (`BE-29-LANG-WRITE-VALIDATION`, §3.6 row 6 — **the first draft's
7-model table was wrong in BOTH directions**):

> **Validate wherever `target_language` can be NOVEL (caller-chosen).
> Normalize-only where it is COPIED from an existing row.
> NEVER validate a read/filter path.**

**And a single chokepoint at job creation is NOT enough — the spec's own premise is wrong.** `jobs.py:246`
reads `eff["target_language"]` from `resolve_effective_settings` — i.e. **from the SETTINGS TABLES**, whose
writers (`settings.py:77`, `settings.py:177`, MCP `server.py:656`) accept **unvalidated free strings**. A job
that *omits* `target_language` reads that row and writes it straight into `chapter_translations`. Since
`TranslateModal`'s picker only ever emits codes, **the settings writer is the most likely door `Vietnamese`
came through.** Validating only `jobs.py` leaves it wide open.

**① THE SIX NOVEL-VALUE INGRESS POINTS** (Pydantic ⇒ 422 before any SQL):

| # | Pydantic model / arg | Route | File |
|---|---|---|---|
| 1 | `CreateJobPayload.target_language` | `POST /books/{id}/jobs` — *also covers `actions.py:332` (confirm replay) and `internal_dispatch.py:125`, which both CONSTRUCT this model* | `models.py:101` |
| 2 | `RetranslateDirtyPayload.target_language` | `POST /chapters/{id}/retranslate-dirty` | `jobs.py:75` |
| 3 | `PreferencesPayload.target_language` ← **the missed bleed vector** | `PUT /preferences` | `models.py:12` |
| 4 | `BookSettingsPayload.target_language` ← **the missed bleed vector** | `PUT /books/{id}/settings` | `models.py:48+` |
| 5 | **`InternalDispatchPayload.target_language`** — 🔴 **MISSED BY THE FIRST DRAFT** | internal dispatch | `internal_dispatch.py:66` |
| 6 | **`glossary_translate.py`'s `target_language`** — 🔴 **MISSED BY THE FIRST DRAFT** (same bug class, one line, same validator) | glossary batch translate | `glossary_translate.py:38` |

**② 🔴 DO NOT TOUCH — validating these is an ACTIVE REGRESSION** *(the first draft listed both as #4/#5 to
validate. **Remove them.**)*

| Model / route | Why it is already closed |
|---|---|
| `SaveEditedTranslationRequest` (`models.py:227`, `versions.py:445`) | **ROW-ANCHORED.** Already 422s (`TRANSL_LANG_MISMATCH`) unless the body's value **EQUALS the stored row's**. It **cannot** introduce a novel language — it can only propagate an existing one. |
| `PatchTranslationBlockRequest` (`models.py:242`, `versions.py:336`) | Same. |

> 🔴 **Enum-validating either would LOCK A USER OUT OF EDITING THEIR OWN LEGACY `Vietnamese` VERSIONS** until
> the deferred backfill lands — a direct breach of D13's read-side tolerance, which is this wave's central
> invariant. **Add a one-line comment at `versions.py:336` and `versions.py:445` citing this decision, so a
> later agent does not "fix" it.** *(Likewise leave `coverage.py:150` and segment-status **permissive** —
> normalize, never reject; the legacy column must still render.)*
> `TranslateTextRequest` (`models.py:286`): validate **only if** it is a free/novel value on a write path —
> **grep it first.** If it is copied from an existing row, it goes in the DO-NOT-TOUCH column. **Verify, do
> not assume.**

**Files** — `services/translation-service/app/models.py`, `app/routers/jobs.py`, `app/routers/internal_dispatch.py`,
`app/routers/glossary_translate.py`

Add **one** reusable validator and attach it to **all six**:
```python
from .languages import normalize_language, is_valid_target

def _validate_target_language(v: str | None) -> str | None:
    if v is None or v == "":
        return v
    norm = normalize_language(v)
    if not is_valid_target(norm):
        raise ValueError(f"invalid_target_language: {v!r} is not a supported target language")
    return norm            # ← RETURNS THE NORMALIZED VALUE. This is the whole fix.
```
…as a `@field_validator("target_language")` on each model — or, equivalently, swap the field's **type** to a
shared `TargetLanguage = Annotated[str, AfterValidator(validate_target_language)]` /
`OptTargetLanguage = Optional[…]` (None passes through) exported from `app/languages.py`. **One definition,
six edges.**
**A pydantic `ValueError` in a request body → FastAPI 422.** Spec 29 asks for a **400
`invalid_target_language`**; a **422 carrying `TRANSL_INVALID_TARGET_LANGUAGE`** is acceptable and is the
framework default. **Decision: keep the pydantic validator (one place, six models) and let it 422.** T-C4's
picker makes an invalid value unreachable from the GUI anyway — **this is the *defense*, not the UX path.**

🔴 **The resolved-from-settings fallback.** `_resolve_and_create_job` (`jobs.py:195-197`) does:
```python
eff, _, _ = await resolve_effective_settings(uid, book_id, db)
if payload.target_language:
    eff["target_language"] = payload.target_language
```
When the payload omits it, `eff["target_language"]` comes from a **stored settings row** — which on a legacy
book may be `"Vietnamese"`. **Do NOT auto-coerce it** (that is a silent data decision) and **do NOT
hard-reject every legacy book** (that would break translation entirely for them).

> **INSTRUCTION — the resolved value:** in `_resolve_and_create_job`, after the overlay, run:
> ```python
> lang = normalize_language(eff["target_language"] or "")
> if not is_valid_target(lang):
>     raise HTTPException(status_code=400, detail={
>         "code": "TRANSL_INVALID_STORED_LANGUAGE",
>         "message": f"This book's stored target language ({eff['target_language']!r}) is not a supported "
>                    f"language code. Pick a language in the translate dialog to fix it.",
>     })
> eff["target_language"] = lang
> ```
> This is **honest and actionable** (D9: typed, never silent), and it is the **correct FAIL-CLOSED behavior**
> (repo precedent: `spend-causing-setting-fails-closed-not-open`) — a user whose stored setting holds
> `Vietnamese` gets a readable 400 telling them to pick a language, **instead of silently minting another
> duplicate column.** The GUI never hits it — `TranslateModal` **always** submits an **explicit**
> `target_language` from the picker (`TranslateModal.tsx:226`). Only an MCP caller that *omits* the arg on a
> legacy book can reach it.
>
> 🔴 **Do NOT add an englishName→code alias (`Vietnamese`→`vi`) to the normalizer to "avoid" this.** Aliasing
> at the *write* edge would quietly **merge two live columns in the user's face**, with no which-version-wins
> rule and no backup. That merge is **slice T-C10's** job — and **T-C10 stops for the PO before executing it**
> (PO decision **D-1**; the rules are in §5.1).
>
> ⚠ **Do NOT put this check inside `resolve_effective_settings`** — it is also read by the **estimate** path
> and the **worker**; a 400 there would break a *read*. **The chokepoint is `_resolve_and_create_job`, and it
> is the single funnel for BOTH the REST route and the MCP confirm replay** (`actions.py:306` `DESC_START_JOB`
> → `_resolve_and_create_job`; `_retranslate_dirty_core` (`jobs.py:123`) → same; `actions.py:482`
> `lang = target_language or eff.get(…) or "en"` → same call). **One guard, all doors.**
> Place it **BEFORE the idempotency gate and BEFORE the `_job_params` dict (`jobs.py:232`)** so the emitted
> event carries the **canonical** value.

**Tests** — `services/translation-service/tests/test_language_validation.py` (NEW — **no DB, no mark**)
- `test_create_job_payload_rejects_Vietnamese` — `CreateJobPayload(chapter_ids=[…], target_language="Vietnamese")`
  raises `ValidationError`. **The spec's verify gate names this.**
- `test_create_job_payload_normalizes_VI_to_vi` — `target_language="VI"` → `.target_language == "vi"`.
  **Also named by the verify gate.**
- `test_settings_payload_normalizes_zh_underscore_CN` — `"zh_CN"` → `"zh-CN"`.
- 🔴 `test_all_SIX_novel_writers_carry_the_validator` — **the drift guard.** Iterate the 6 models/args and
  assert each rejects `"Vietnamese"`. **A new write edge added later without the guard REDS this test.**
  *(Memory `rest-write-mirror-drops-fields-the-mcp-tool-accepts`: a write edge added without its guard is
  exactly how these ship.)*
- 🔴 `test_the_two_row_anchored_models_are_NOT_validated` — `SaveEditedTranslationRequest` and
  `PatchTranslationBlockRequest` **still accept `"Vietnamese"`** (they are equality-gated downstream).
  **This test protects D13's read-side tolerance from a well-meaning future "fix".**
- 🔴 `test_a_job_with_NO_target_language_on_a_LEGACY_STORED_setting_400s` — **the test that proves the
  backfill's input set stopped growing, and the one a job-route-only fix would FAIL.** Monkeypatch
  `resolve_effective_settings` to return `{"target_language": "Vietnamese", …}`; POST a job with **no**
  `target_language`; assert `HTTPException(400, code="TRANSL_INVALID_STORED_LANGUAGE")`.
- `test_read_paths_stay_permissive` — coverage / segment-status still return a legacy `Vietnamese` column
  **without raising.** *(D13 constrains WRITES, never READS.)*

**DoD evidence:** `"pytest: test_language_validation.py 7 passed — 'Vietnamese' → 422 TRANSL_INVALID_TARGET_LANGUAGE, 'VI' → 'vi', 'zh_CN' → 'zh-CN'; all SIX novel-value writers guarded (incl. internal_dispatch + glossary_translate); the TWO row-anchored models deliberately UNguarded (legacy versions stay editable); a no-language job on a legacy stored setting 400s TRANSL_INVALID_STORED_LANGUAGE; read paths still render 'Vietnamese'"`

---

#### **T-C3 — The MCP `target_language` arg becomes a real enum** (lands **D13**, part 3; closes the **closed-set⇒enum** breach)

**dependsOn:** T-C1

**The violation:** `services/translation-service/app/mcp/server.py:220`:
```python
target_language: Annotated[str, "The target language code (e.g. 'en')."],
```
An unconstrained string — a **`closed-set arg ⇒ enum`** violation of
[`docs/standards/mcp-tool-io.md`](../standards/mcp-tool-io.md). **This is the writer that admitted
`Vietnamese` in the first place** (`TranslateModal`'s `<select>` only ever emits codes, so the bad value
entered through another writer).

**The precedent is in the same file** (§3.2): `translation_job_control` (`server.py:939`) already uses
`Literal["cancel","pause","resume","retry"]`, and FastMCP derives the JSON-Schema `enum` from it.

**Files** — `services/translation-service/app/mcp/server.py`

1. Near the imports:
   ```python
   from typing import Literal, get_args
   from ..languages import TRANSLATION_TARGET_CODES

   # D13 — the closed set, GENERATED from the registry so it cannot drift.
   # (Literal[<tuple>] is valid at runtime; typing normalizes it to Literal['en','vi',…].)
   TargetLanguage = Literal[TRANSLATION_TARGET_CODES]  # type: ignore[valid-type]
   ```
   > **FALLBACK, if pydantic/FastMCP rejects the dynamic form:** spell the 18 codes out explicitly in the
   > `Literal[...]` — **and keep the `get_args` drift assertion below regardless.** Do not stall on this; both
   > paths end at the same required test.
   ✅ **One schema source here.** translation-service's MCP tools are advertised **and** validated **solely by
   the FastMCP function signature** — the knowledge-service "three sources" hazard does **not** apply (no
   bespoke `TOOL_DEFINITIONS`, no pydantic arg-model layer: `ForbidExtra` is imported at `:45` and **never
   subclassed**). So changing the `Annotated` type **is** sufficient, and `Literal` **provably** survives into
   the advertised `inputSchema`.

2. 🔴 **Enum the THREE NOVEL-VALUE WRITE args — and ONLY those** (§3.7 ③; the first draft enum'd four,
   including a **read** arg):
   - `translation_start_job` (`:728`) → `target_language: Annotated[TargetLanguage | None, "…"] = None`
   - `translation_retranslate_dirty` (`:775`) → `target_language: Annotated[TargetLanguage, "…"]`
   - `translation_update_settings` (`:656`) → `target_language: Annotated[TargetLanguage | None, "…"] = None`

3. 🔴 **LEAVE FREE-STRING — enum-ing any of these is an ACTIVE REGRESSION.** Add a one-line comment at each
   citing this decision:
   - **`translation_segment_status` (`:220`) — it is a READ arg.** *(The first draft enum'd it.)* Enum-ing a
     read arg makes the legacy `Vietnamese` rows **unreadable by the agent** before the backfill lands.
     **Normalize before the query; never reject.**
   - **`translation_save_edited_version` (`:473`)** and **`translation_patch_block` (`:545`)** — **row-anchored
     writes.** Their `target_language` is already validated by **equality with the existing row's value**
     (`:485`, `:559` — *"must match the source version"*, `TRANSL_LANG_MISMATCH`), so they **cannot introduce a
     novel language.** Enum-constraining them makes a **legacy `Vietnamese` version un-editable.**

4. **Update each enum'd tool's `description`** (the description is the model's only hint): append
   *"Must be one of the supported target language codes (e.g. 'en', 'vi', 'zh-CN')."*

5. **Do NOT touch:** `contracts/tool-liveness.json` (liveness only: `{status, executes, proven}` — no schema),
   `contracts/mcp-response-shapes/translation.json` (output-side), or chat-service's `CLOSED_SET_ARGS` (that
   registry governs **FRONTEND** tools, not MCP tools).

**Tests** — `services/translation-service/tests/test_mcp_language_enum.py` (NEW — **no DB, no mark**; reuse the
existing in-process FastMCP fixture at `tests/test_mcp_server.py:147-153` — `mcp_base_url` +
`session.list_tools()` + `tool.inputSchema`)
- 🔴 `test_advertised_inputSchema_carries_the_enum` — **the load-bearing one.** Stand up the FastMCP server
  in-process, call `tools/list`, and assert `translation_start_job`'s `inputSchema.properties.target_language`
  carries an **`enum` with exactly the 18 registry codes**.
  **Assert on the ADVERTISED schema, not the Python annotation** — memory
  `knowledge-mcp-three-schema-sources-fastmcp-strips`: *"the FastMCP signature is what is advertised AND what
  FastMCP validates + STRIPS against"*, and that bug **passed 3143 unit tests**.
  > 🔴 **THE TRAP THAT MAKES THIS TEST SILENTLY VACUOUS.** A **required** arg renders as
  > `{"type":"string","enum":[…]}`, but an **OPTIONAL** one renders as
  > `{"anyOf":[{"type":"string","enum":[…]},{"type":"null"}],"default":null}`. **Two of the three tools are
  > optional.** The test MUST unwrap `anyOf`:
  > ```python
  > enum = prop.get("enum") or next(s["enum"] for s in prop["anyOf"] if "enum" in s)
  > ```
  > …**or it passes without ever seeing an enum.** And assert the **tool count found is exactly 3**, so the
  > loop cannot pass vacuously.
- `test_literal_does_not_drift_from_the_registry` — `set(get_args(TargetLanguage)) == set(TRANSLATION_TARGET_CODES)`.
- `test_the_three_write_tools_are_enum_constrained` — iterate the 3 tool names; assert each advertises the enum.
- 🔴 `test_the_READ_and_ROW_ANCHORED_tools_are_NOT_constrained` — `translation_segment_status`,
  `translation_save_edited_version`, `translation_patch_block` **still accept a free string** (a legacy
  `Vietnamese` row stays **readable** and its versions stay **editable**).
  **This test protects D13's read-side tolerance from a well-meaning future "fix".**

**VERIFY (do NOT settle for the unit test — the enum must reach the schema the LLM actually sees):** after the
change, hit `tools/list` **through ai-gateway** (the federation path chat-service compiles `mcp_tool_schemas`
from) and **PASTE the `translation_start_job.inputSchema.target_language` block showing the 18-value enum**
into the VERIFY evidence.

**DoD evidence:** `"pytest: test_mcp_language_enum.py 4 passed — the LIVE advertised inputSchema for translation_start_job carries an 18-value enum (anyOf-unwrapped; 3 tools found, not 0); segment_status (READ) + save_edited_version + patch_block stay free-string so legacy 'Vietnamese' rows remain readable AND editable. ai-gateway tools/list target_language block pasted."`

---

#### **T-C4 — All FIVE language inputs consolidate onto `LanguagePicker` + `TRANSLATION_TARGETS`** (lands **D13**, frontend half; closes **S7**)

**dependsOn:** T-C1

Per **§3.4**, there are **five** surfaces, not the three the spec names. `TRANSLATION_TARGETS`
(`lib/languages.ts:73`) is exported and imported by **nobody** — the `translationTarget` flag governs nothing
today. **D13 makes it load-bearing.**

**Files**

1. **EDIT** `frontend/src/components/shared/LanguagePicker.tsx:45` — feed from `TRANSLATION_TARGETS`, not
   `LANGUAGE_NAMES`:
   ```ts
   const options = TRANSLATION_TARGETS
     .filter((l) => !excludeSet.has(l.code))
     .map((l) => [l.code, l.endonym] as const);
   ```
   🔴 **Keep `:62`'s read-side echo intact:** `{LANGUAGE_NAMES[value] ? … : value}` — a picker rendering a
   **legacy** value must still display it. **D13 constrains writes, never reads.**
2. **EDIT** `frontend/src/pages/book-tabs/TranslateModal.tsx:320-329` — replace the hand-rolled `<select>` with
   `<LanguagePicker …/>`. **Keep `data-testid` / `aria-label` stable** so T-A5's tests don't churn.
   `const availableLangs = Object.entries(LANGUAGE_NAMES)` (`:262`) — **delete**.
3. **EDIT** `frontend/src/features/glossary/components/BatchTranslateDialog.tsx:20-29` — **S7**: replace the
   free-text `<input>` + `LANG_RE` (whose `if (LANG_RE.test(v)) …` has **no `else`** ⇒ an invalid code makes
   Load **silently no-op**) with `<LanguagePicker/>`. **A picker cannot emit an invalid code — S7 is fixed for
   free.** Delete `LANG_RE`.
4. **EDIT** `frontend/src/features/studio/panels/ChapterBrowserTitleView.tsx:327` (**spec missed this**) —
   replace its `<select>` over `LANGUAGE_NAMES` with `<LanguagePicker/>`.
5. **EDIT** `frontend/src/features/glossary-translate/StepConfig.tsx:61` (**spec missed this**) —
   `Object.keys(LANGUAGE_NAMES)` → `TRANSLATION_TARGETS.map(l => l.code)`.

🔴 **KEEP `LanguagePicker`'s ORPHAN-VALUE GUARD (`:46-64`) VERBATIM IN BEHAVIOR.** `valueInOptions` /
`showOrphanValue` + the orphan `<option value={value}>` is the **shipped** mechanism whose doc comment reads
*"if value is a code that is not in the list … it is still rendered as a selectable option so editing an
existing resource never silently blanks an unrecognised language."* **T-A5's legacy seed DEPENDS on it.**
Update the JSDoc at `:24-27` to name `TRANSLATION_TARGETS` instead of `LANGUAGE_NAMES`.
🔴 **Leave `LANGUAGE_NAMES` EXPORTED** — it is still the right lookup for *displaying* an already-stored code.
**Only the OPTION LISTS move to `TRANSLATION_TARGETS`.**

**Tests**
- `frontend/src/components/shared/__tests__/LanguagePicker.test.tsx` (extend):
  - `D13: the rendered <option> count (excluding the placeholder) === TRANSLATION_TARGETS.length` (18).
  - `D13: no option has translationTarget === false` — assert
    `options.every(o => LANGUAGE_BY_CODE[o.value]?.translationTarget !== false)`. **This is the assertion that
    makes the flag LOAD-BEARING** — flip a flag and the picker's option set changes, provably.
  - 🔴 `D13 read-side: a value NOT in the registry still DISPLAYS as a selectable option (it is not blanked)` —
    pass `value="Vietnamese"`; assert the string renders **and** that no React `value-not-in-options` warning
    fires (**fail the test on `console.error`**).
- `frontend/src/features/glossary/components/__tests__/BatchTranslateDialog.test.tsx` (**must be UPDATED — it
  currently TYPES INTO the removed input**):
  - `S7: an invalid code can no longer be entered (the free-text input is gone)` — select an option instead.
- `TranslateModal` / `BatchTranslateDialog`: one test each asserting a **`<select>` (not an `<input>`)** drives
  the target language.
- ✅ **`noFrontendLanguageNormalizer.test.ts` (T-C1) FLIPS GREEN HERE** — deleting `LANG_RE` +
  `.toLowerCase()` removes the only hit in the tree.
- 🔴 `frontend/src/pages/book-tabs/__tests__/TranslationTab.legacy.test.tsx` (NEW) — **the read-side regression
  test the verify gate names by name:**
  - `D13: coverage returning a legacy unknown code ("Vietnamese") still renders its column without crashing` —
    fixture `known_languages: ["vi", "Vietnamese"]`; assert **both** column headers render and `getLanguageName`
    echoes `Vietnamese`. **This proves D13 constrains writes, never reads.**

**DoD evidence:** `"vitest: 5 language inputs consolidated; LanguagePicker 2 passed; TranslationTab.legacy.test.tsx 1 passed (a legacy 'Vietnamese' column still renders); grep LANGUAGE_NAMES in a picker → 0 hits"`

---

#### **T-C5 — `access_level` gates the translate affordance, WITH A REASON** (closes **T9**; lands **D10**, second half)

**dependsOn:** T-X0 *(the contract row)*, T-A2, T-A4 *(the CTAs must exist before they can be gated)*

🔴 **Re-read §3.1 before writing a line of this slice. `access_level` ALREADY SHIPS. This is a PURE FRONTEND
slice. Write no Go. Do not create `my_grant_level`.** *(T-X0 already documented the field in
`contracts/api/books/v1/openapi.yaml` and fixed spec 29's three `my_grant_level` mentions.)*

🔴 **THE VALUE SET IS 5, NOT 3 — THIS IS THE BUG TRAP.** The wire emits
**`'owner' | 'manage' | 'edit' | 'view' | 'none'`** (`collaborators.go:34-47`). **Spec 29's 3-value
`'view'|'edit'|'owner'` is WRONG.** A builder who follows the spec literally and gates on
`lvl === 'edit' || lvl === 'owner'` **WRONGLY BLOCKS a `manage` collaborator from translating — shipping the
exact grant/403 mismatch T9 exists to kill.**

**D10, second half:** *"Phase C then adds the caller's effective grant to the book read … and **disables the
affordance with a reason** rather than hiding it (**a hidden button is indistinguishable from the T1 bug**)."*

**Files**

1. **EDIT** `frontend/src/features/books/api.ts` — the `Book` type (`:6-24`) gains the field that has been on
   the wire all along:
   ```ts
   /** The CALLER's effective grant on this book, computed per-request by book-service
    *  (server.go:956 — `CASE WHEN owner THEN 'owner' ELSE book_collaborators.role END`).
    *  Ships on GET /v1/books/{id}, GET /v1/books, and favorites. NOT a new field —
    *  the FE simply never declared it. Comparing owner_user_id to the current user is
    *  NOT sufficient: that would also hide the button from legitimate EDIT collaborators. */
   access_level?: 'owner' | 'manage' | 'edit' | 'view' | 'none';
   ```
2. **CREATE** `frontend/src/features/books/lib/grants.ts`
   ```ts
   const ORDER = { none: 0, view: 1, edit: 2, manage: 3, owner: 4 } as const;
   export function canEditBook(b?: { access_level?: string } | null): boolean {
     return (ORDER[(b?.access_level ?? 'none') as keyof typeof ORDER] ?? 0) >= ORDER.edit;
   }
   ```
   *(Mirrors `book-service`'s `GrantLevel.AtLeast` — `collaborators.go:32`. **`manage` and `owner` both
   out-rank `edit`** — a naive `=== 'edit'` check would lock out the owner. That is the exact bug this
   ordering exists to prevent.)*
3. **EDIT** `frontend/src/pages/book-tabs/TranslationTab.tsx`
   - Add `const { data: book } = useQuery({ queryKey: ['book', bookId], queryFn: () => booksApi.getBook(accessToken!, bookId), enabled: !!accessToken });`
   - `const canEdit = canEditBook(book);`
   - The header CTA (T-A2), the FloatingActionBar's **Translate Selected**, and the per-cell translate button
     (T-A4) get `disabled={!canEdit || …}` **and a `title={!canEdit ? t('matrix.view_only_reason') : …}`**
     → *"You have view-only access to this book."*
   - 🔴 **DISABLE, never hide.** A hidden button is indistinguishable from T1 — the bug we just fixed.
   - ⚠ **`book` may still be loading.** Default to **enabled** while `book === undefined` (a spurious disable is
     worse than a late 403, and T-A6's toast already catches the 403 honestly). **Do not** default to disabled
     — that would re-create T1 for one render.
4. **EDIT** `frontend/src/features/translation/components/VersionSidebar.tsx` — same gate on `onRetranslate`
   and `onAddLanguage` (T-B3). Pass `canEdit` down from `ChapterTranslationsPanel` (which must fetch the book
   the same way).

i18n: `matrix.view_only_reason` → 18 locales.

**Tests** — `frontend/src/pages/book-tabs/__tests__/TranslationTab.grants.test.tsx` (NEW)
- `T9: access_level 'view' disables the translate CTA with a reason` — assert the button is `disabled` **and**
  `title` carries the reason **and** the button **is still in the document** (not hidden).
- `T9: access_level 'edit' ENABLES it` · `'manage' enables it` · `'owner' enables it` — 🔴 **all four.** A
  naive `=== 'edit'` passes the first three tests and locks out the owner.
- `T9: the CTA is enabled while the book query is still loading` (no spurious disable).
- `frontend/src/features/books/lib/__tests__/grants.test.ts` (NEW): the ordering table, all 5 levels + `undefined`.

**DoD evidence:** `"vitest: TranslationTab.grants.test.tsx 6 passed, grants.test.ts 6 passed — view disables-with-reason; edit/manage/owner all enable; ZERO Go changed (git diff --stat services/book-service = empty)"`

---

#### **T-C6 — The last DOCK-9 leftover + the dead button** (closes **S9**, **S12**)

**dependsOn:** —

| ID | File | Fix |
|---|---|---|
| **S9** | `features/translation/components/ConfirmNameDialog.tsx:43-44` | Still a hand-rolled `fixed inset-0` Radix overlay — **the one DOCK-9 leftover in this feature** (`TranslateModal` and `SegmentDrilldownModal` were correctly migrated per spec 17). Migrate to `FormDialog` (`components/shared/FormDialog.tsx`), exactly as `TranslateModal.tsx:300-307` does. **Chrome-only: preserve every existing prop and behavior.** ⚠ Memory `dockview-panel-fixed-positioning-window-scoped-bug`: a `fixed`/`100vw` overlay pins to the **WINDOW**, not the dock panel — which is why this rule exists. |

🔴 **S12 — REWRITTEN. NAVIGATE NOWHERE.** *(`Q-29-S12-VIEW-GLOSSARY-TARGET`, §3.6 row 11. The first draft said
"wire `onViewGlossary` → `host.openPanel('glossary')` / `navigate()`". **Both candidates are wrong, and the
code settles it.**)*

**The glossary is ALREADY MOUNTED BEHIND THE MODAL.** `GlossaryTranslateWizard` is rendered from **exactly
one** place — `GlossaryEntityList.tsx:787` — and **`GlossaryEntityList` IS the glossary list body**, shared
**un-forked** (DOCK-2) by **both** the studio `glossary` dock panel (`GlossaryPanel.tsx:42`) **and** the legacy
`GlossaryTab` page (`GlossaryTab.tsx:47`). Therefore:
- **`host.openPanel('glossary')` is a NO-OP** — you are *already in that panel*, and on the legacy page there
  is no studio host at all.
- **`navigate('/books/:id/glossary')` is ACTIVELY HARMFUL** — a bare `navigate()` from inside a studio panel
  **tears down the whole dock** (the anti-pattern `ExtractionWizard.tsx:45-48` documents and guards against).
- **`handleClose` was the right target all along.** `onComplete → invalidate()` (`GlossaryEntityList.tsx:791`)
  **already refetches**, so the dismissed user sees fresh translations.

**THE REAL DEFECT is that two buttons perform ONE action under TWO labels** (the repo's "one name for one
concept" / silent-no-op-honesty class), plus genuinely dead state. **Four edits, NO navigation added:**

1. **`features/glossary-translate/StepResults.tsx`** — **delete the `onViewGlossary` prop** (decl. `:10`,
   destructure `:31`) and **DELETE the second button** (the `onClick={onViewGlossary}` block, ~`:152-159`).
   Keep **ONE** dismiss button: take the remaining `onClick={onClose}` button, **relabel it from
   `t('results.close')` to `t('results.viewGlossary')`**, add the existing `<BookOpen className="h-3.5 w-3.5"/>`
   icon, and promote it to primary styling. **Dismissing the modal IS "view glossary" — the label becomes TRUE
   instead of a lie.** Then grep `results.close`; if now unused, remove the key from every locale file.
2. **`GlossaryTranslateWizard.tsx:124`** — delete the `onViewGlossary={handleClose}` line.
3. **Kill the dead state** (`state.totalEntities` — *stored and never read*): in `useGlossaryTranslateState.ts`
   remove the `totalEntities` field (init `:25`, type `:41`) and drop the param from `setJobCreated`
   (`:95-99`) ⇒ `(jobId, costEstimate)`. Update the two callers (`StepConfirm.tsx:20` + its invocation;
   `GlossaryTranslateWizard.tsx:100-101`). **Deleting is correct rather than "rendering it": `StepResults`
   already reads the AUTHORITATIVE count off the job status (`s.total_entities`, `StepResults.tsx:41`) — the
   wizard-state copy is a redundant SECOND SOURCE OF TRUTH.**

**Tests**
- `frontend/src/features/translation/components/__tests__/ConfirmNameDialog.test.tsx` (NEW or extend):
  `S9: renders through FormDialog (no hand-rolled fixed inset-0)`.
- ✅ **`frontend/src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts` must stay green** — the
  spec's verify gate says *"S9 removes the last `fixed inset-0` here"*. **Run it and paste the result.**
- `GlossaryTranslateWizard.test.tsx` (extend) — drive to the results step and assert:
  - (a) **exactly ONE dismiss affordance** renders (query by `results.viewGlossary`; assert `results.close` is
    **absent**),
  - (b) clicking it calls `onOpenChange(false)`,
  - 🔴 (c) **NEITHER `navigate` NOR `studioHost.openPanel` is called** — spy on **both**, assert **not-called**.
    **Leg (c) is the regression guard that stops a future agent from "fixing" this back into a dock-tearing
    `navigate()`.**

**DoD evidence:** `"vitest: ConfirmNameDialog 1 passed, GlossaryTranslateWizard S12 3 passed (ONE dismiss button; navigate AND openPanel both NOT called), dockablePanelHygiene.test.ts GREEN; totalEntities dead state deleted"`

---

#### **T-C7 — The unbounded coverage payload gets an opt-in projection** (closes **X5**; the Phase-C half of `UC-29-COVERAGE-IS-UNPAGED`)

**dependsOn:** T-X0 *(the contract row)*

**The bug (X5):** the worst offender is **not** `TranslationTab` (one book, one fetch) — it is
**`frontend/src/features/books/hooks/useBooksList.ts:63-78`**, which pulls the **FULL chapter×language matrix
for EVERY book in the list** (batched 10 at a time) **purely to read `cov.known_languages` (`:69`)**.
`BooksBrowserPanel` does the same. **On a shelf of 2000-chapter books that is megabytes of JSON discarded on
arrival.**

**Files**

1. **EDIT** `services/translation-service/app/routers/coverage.py` — an **ADDITIVE** query param on the
   **existing** route:
   `GET /v1/translation/books/{book_id}/coverage?languages_only=true`
   → when set, run `SELECT DISTINCT target_language FROM chapter_translations WHERE book_id=$1` and return
   `{book_id, coverage: [], known_languages: [...]}`. **Same VIEW grant gate** (`coverage.py:59`).
   ✅ **Additive ⇒ zero break for existing callers.**
   ✅ **VERIFIED no MCP ripple:** `translation_coverage` (`mcp/server.py:184-198`) carries its **OWN**
   `_COVERAGE_SQL` and **never calls this route.**
   *(Already documented in `contracts/api/translation/v1/openapi.yaml` by T-X0.)*
2. **EDIT** `frontend/src/features/books/hooks/useBooksList.ts:69` **and** `BooksBrowserPanel` — switch both to
   `?languages_only=true`.
3. **BONUS FIX-NOW** (cheap, adjacent, root cause identical — `Q-29-OUT-OF-SCOPE-BE-JOIN`): the **duplicated**
   MCP SQL means **an agent asking "how much of my book is translated" cannot see the glossary-staleness the
   GUI shows.** Add `is_glossary_stale` to `mcp/server.py`'s `_COVERAGE_SQL` SELECT (`:1025` — mirror
   `coverage.py:96-111`'s COALESCE-active-then-latest expression) and to `_coverage_payload` (`:1054-1061`).
   ⚠ **Not required for anything else in this wave — if it fights you, give it a defer row and MOVE ON.**
4. **RECOMMENDED DEFAULT (PO may veto):** `translation_coverage` returns that same unbounded matrix **straight
   into the model's context** and is explicitly exempted from projection via `@small_return`
   (`mcp/server.py:188-192`). **That exemption is defensible at 100 chapters and VIOLATES THE CONTEXT BUDGET
   LAW at 2000.** Add an optional `chapter_ids: list[str] | None` filter, and when the unfiltered matrix
   exceeds **200 chapters** return **per-language ROLLUP totals** plus `truncated: true` + a *"pass chapter_ids
   to drill in"* hint, instead of every cell.

**Tests** — `services/translation-service/tests/test_coverage_languages_only.py` (NEW — **hits a DB ⇒ 🔴 it
carries `pytestmark = pytest.mark.xdist_group("pg")`**)
- `a book with 2 langs × N chapters returns coverage == [] and BOTH langs` under `?languages_only=true`.
- `the default (no param) response is BYTE-IDENTICAL to today's` — **the additive-ness proof.**
- `languages_only still enforces the VIEW grant` (a non-grantee gets 403 — **not** an empty list).
- `known_languages still includes a legacy 'Vietnamese'` (D13 read-side).
- If step 4 ships: `a 250-chapter matrix returns rollups + truncated: true`; `passing chapter_ids returns the
  cells`.

**Tests** — `frontend/src/features/books/hooks/__tests__/useBooksList.test.ts` (extend)
- `X5: the shelf requests languages_only=true and does NOT download the full matrix` — assert the request URL
  carries the param **and** that a 2000-row coverage fixture is never fetched.

**DoD evidence:** `"pytest: test_coverage_languages_only.py 4 passed (xdist_group pg) — languages_only returns [] + both langs, the default response is byte-identical, the VIEW grant still 403s, a legacy 'Vietnamese' still appears; vitest: useBooksList 1 passed — the shelf no longer downloads the full matrix per book"`

---

#### **T-C8 — 🔴 The legacy language's THREE dead ends become LEGIBLE** (closes **X4** — *a paid-action defect*; lands `Q-29-D13-LEGACY-RETRANSLATE-DEAD-END`)

**dependsOn:** T-C1 *(`isTranslationTarget`)*, T-C2 *(the backend now 400s)*, T-C4 *(the pickers)*

> 🔴 **NOT IN THE FIRST DRAFT AT ALL, and it is the slice that keeps T-C2 from creating a NEW bug.**
> The moment T-C2 lands, **every path that re-translates a legacy column becomes a guaranteed 400.** D13
> already records *"the legacy column keeps rendering and cannot be re-translated"* as **CORRECT** — so the
> job is to make that dead-ness **LEGIBLE**, never to silently retarget the write to another column.
> **The spec listed TWO such paths. There are THREE.**

**The three re-translate paths into a legacy column:**

| # | Path | State after T-C2 |
|---|---|---|
| 1 | `VersionSidebar` → Re-translate → `TranslateModal` | Guarded by T-A5's seed gate (notice + disabled CTA). ✅ |
| 2 | The matrix cell / column → `TranslateModal` | Guarded by T-A5's seed gate. ✅ |
| 3 | 🔴 **`TranslationTab.tsx:447` "N changed" badge → `useSegmentDrilldown.ts:27` → `POST /retranslate-dirty` (`jobs.py:75`)** | **NO PICKER. It posts the column's language VERBATIM ⇒ a GUARANTEED 400 — on a button the user pays for.** **The spec never saw this path.** |

**Files**

1. **EDIT** `frontend/src/pages/book-tabs/TranslationTab.tsx` — **the legacy marker (D13 (b))**
   - `const isLegacy = (l: string) => !isTranslationTarget(l);` over `allLanguages` (`:173`).
   - **Column header (`:374-379`):** when `isLegacy(lang)`, append a muted, `border-dashed` **"Legacy" pill**
     with `title={t('matrix.legacy_lang_tooltip')}` = *"Legacy language value. Read-only: translations here
     still display, but new jobs can't target it. A one-time cleanup will merge it into the standard code."*
     🔴 **Do NOT name a defer-row id in user-facing copy.** *(The cleanup is T-C10's migration, PO-gated —
     `D-TRANSL-LANG-REKEY-EXECUTE`. The user does not care what we call our tickets.)*
   - **Cell (`:406-460`):** for a legacy column, render the status chip as a **NON-button `<span>`** (the
     `:412` `inner`, **no `onClick`**) and 🔴 **DROP the "N changed" badge button (`:447`) — that badge IS the
     entry to the third dead path (X4).** Give the cell the same `title`.
   - Pass `preselectedLang` to `TranslateModal` (`:544`) from the column the user acted on. The matrix can
     **never** pass a legacy code (those cells are now inert) — **T-A5's seed guard is the belt-and-braces.**
2. **EDIT** `frontend/src/features/translation/components/VersionSidebar.tsx`
   - **Disable the Re-translate button** (`:33` `onRetranslate`, button ~`:157`) when
     `selectedLang !== null && !isTranslationTarget(selectedLang)`, with the same tooltip.
   - Add a **"Legacy" pill** to that language tab (`:88-101`).
3. 🔴 **The read side stays TOLERANT — this is the whole point.** The matrix **still renders** the legacy
   column, its cells **still show their status text**, and `getLanguageName` **still echoes** the unknown code.
   **D13 constrains WRITES, never READS. Do not "fix" the legacy column by hiding it — it is a record of data
   that exists.**

i18n (**`en` only**): `matrix.legacy_lang_tooltip`, `matrix.legacy_pill`.

**Tests** — `frontend/src/pages/book-tabs/__tests__/TranslationTab.legacy.test.tsx` (the file T-C4 creates —
extend it)
- 🔴 `X4: a legacy column's cells expose NO clickable button and NO segment-drilldown badge` — fixture
  `known_languages: ['vi','Vietnamese']`; assert the `Vietnamese` cells render **text** (T3's read-tolerance
  holds) and `queryAllByRole('button')` **within them is empty**. **This is the test that closes the paid-action
  defect: with the badge live, one click = a 400 on a job the user thinks they bought.**
- `D13: the Vietnamese header carries the Legacy pill; the vi header does not`.
- `D13: the vi column's cells are STILL clickable` (the guard did not over-fire).
- `VersionSidebar.test.tsx` (extend): `D13: a legacy lang selected ⇒ Re-translate is DISABLED with a reason`.

**DoD evidence:** `"vitest: TranslationTab.legacy 4 passed, VersionSidebar legacy 1 passed — the legacy 'Vietnamese' column still RENDERS (read-tolerance) but exposes zero write affordances: no cell button, no 'N changed' drilldown badge (X4 — the third dead end, a paid 400), and Re-translate is disabled with a reason"`

---

#### **T-C9 — The i18n backfill + the parity test that keeps it from rotting** (lands `Q-29-D9-LOCALIZED-MESSAGES`)

**dependsOn:** every slice that added an `en` key (**this is the LAST slice before the live smoke**)

> 🔴 **REVERSAL (§3.6 row 14).** The first draft regenerated 18 locales **per slice**. **The decision: English
> key during the build; ONE batch generation at wave close.** `fallbackLng: 'en'` (`i18n/index.ts:48`) makes
> the other 17 locales render the English string **immediately**, and `i18n/index.ts:16` globs
> `./locales/*/*.json` so **no loader edit is ever needed.** *"A missing translation is a cosmetic English
> string; a hardcoded literal is an unfixable one."*

**Steps**

1. **Run the generator** (it is **incremental** — `scripts/i18n_translate.py:341-342`: *"(re)translate ONLY
   the keys that are missing, broken, or listed in `_FAILED.json` … safe to run anytime"*):
   ```bash
   python scripts/i18n_translate.py --ns translation,studio,editor,common
   ```
   *(Needs LM Studio on `:1234` with `google/gemma-4-26b-a4b-qat`.)* **Including `editor,common` is free and
   clears pre-existing drift — 19 + 1 keys are missing in all 17 locales today.**
2. ⚠ **Spot-check `vi` and `zh-CN` ACTUALLY CHANGED** before committing — memory
   `i18n-translate-self-heal-only-fires-on-hard-failures`: **the self-heal SKIPS soft untranslated flags**, so
   a silent no-op is the expected failure mode. **Diff the two files. Do not trust the exit code.**
3. **Commit the generated JSON in this slice's commit.**
4. 🔴 **THE MECHANISM THAT ACTUALLY MATTERS — the parity test.** Create
   `frontend/src/i18n/__tests__/translationRepairParity.test.ts` by copying
   `frontend/src/i18n/__tests__/campaignsParity.test.ts` **verbatim** and swapping the namespace to
   `translation` (guard `vi` / `ja` / `zh-TW`, exactly as the four existing parity tests do — locales move as a
   block under the generator, so 3 is a sufficient proxy).
   **Measured, and this is the entire argument:** the **4 namespaces WITH a parity test are at 100% parity**
   (`studio` 722/722, `translation` 148/148); **`editor` and `common` — the only two with NO parity test — are
   the only two that drifted.**

**🔴 IF LM STUDIO IS NOT UP:** write defer row **`D-29-I18N-BACKFILL`** (gate **#4** — blocked on an external
dev-time backend) and **KEEP GOING.** English fallback is already correct and **shipping**; the backfill is a
cosmetic catch-up, **never a blocker.** **Do not stop. Do not ask.** *(Per §0 rule 3 — this is a textbook
defer-and-continue, not one of the four CRITICAL stop classes.)*

**Tests**
- `translationRepairParity.test.ts` green.
- **Do NOT write a test that requires 18 translated files to exist.** The Verify gate for T4/T5/T6/D9 is
  satisfied by **the KEY**: assert the rendered text **resolves from an i18n key** (render under the test i18n
  instance; assert the `en` value appears; assert **no error/retry string is a bare literal in the
  component**). *That* is what the gate is testing.

**DoD evidence:** `"i18n: scripts/i18n_translate.py --ns translation,studio,editor,common run; vi + zh-CN diffs INSPECTED and non-empty (N new keys each); _FAILED.json empty; vitest: translationRepairParity.test.ts passed — translation ns at 100% parity for vi/ja/zh-TW"` *(or the defer row `D-29-I18N-BACKFILL` + "English fallback verified rendering")*

---

#### **T-C10 — 🔴 THE `Vietnamese` → `vi` REKEY: WRITE IT, DRY-RUN IT, AND **STOP**** (PO decision **D-1**)

**dependsOn:** **T-C2** *(the write-side validation MUST already be live — you cannot rekey a set that is
still growing)*, T-C1

> # 🛑 THIS IS THE ONE SLICE WHERE THE AGENT STOPS AND ASKS.
>
> Everywhere else in this run: **blocked ≠ stopped** — file a defer row and keep going. **Not here.**
> §0 rule 3's **first** CRITICAL bullet is *"a destructive / irreversible action (data loss, **a migration
> that drops or rewrites user rows**)"*. **This is that.** It is a **four-table rekey** whose target column
> is inside a **`UNIQUE`** and a **`PRIMARY KEY`**.
>
> ## THE DELIVERABLE OF THIS SLICE IS A DRY-RUN REPORT, NOT A CHANGED DATABASE.
>
> **You will:** write the migration · write the rollback · write the assertions · **run it in DRY-RUN mode
> against the real dev DB inside a transaction that is ROLLED BACK** · **print the report** · **commit the
> code** · **STOP and hand the report to the PO.**
>
> **You will NOT:** execute it. Not against dev. Not "just to see". Not because the counts look right. Not
> because the PO approved *this plan* — **approving the plan is not approving the execution; the PO's
> decision D-1 says so in terms.** The execution is a **separate, human-run, backed-up step**
> (`D-TRANSL-LANG-REKEY-EXECUTE`, §10).
>
> ⚠ **THE SNEAKY WAY TO VIOLATE THIS: `services/translation-service/app/migrate.py` RUNS ITS DDL ON EVERY
> SERVICE BOOT** (§5.1 — that is *why* the renumber must interleave). 🔴 **SO THE REKEY MUST NOT GO INTO
> `migrate.py`.** Putting it there = **it executes the next time anyone starts the service.** It goes in a
> **standalone, explicitly-invoked script** (below). **Adding it to `migrate.py` is the failure mode this
> whole slice exists to prevent.**

**What is broken (measured live 2026-07-12 — re-measure at build time; the numbers go in the report):**
`chapter_translations.target_language` holds **5 `Vietnamese`** rows beside **89 `vi`** (+ 5 `ja`, 3 `en`,
1 `ko`). **One chapter has BOTH a `Vietnamese` and a `vi` ACTIVE version** ⇒ two rows would collapse onto one
**primary key**. **1 legacy memo.** Segment rows: **count them — spec 29's D12 missed this table entirely.**

**Files**

1. **CREATE** `services/translation-service/scripts/rekey_legacy_target_language.py` — **standalone.**
   🔴 **NOT in `app/migrate.py`** (see the box). **NOT imported by anything.** It is run by a human:
   ```bash
   # DRY-RUN (the default — and it must be the default; an accidental bare invocation must be SAFE):
   python scripts/rekey_legacy_target_language.py                     # → prints the report, ROLLS BACK
   # EXECUTE (PO only, after reading the report, with a backup taken):
   python scripts/rekey_legacy_target_language.py --execute --i-have-a-backup
   ```
   - 🔴 **`--execute` is NOT enough on its own.** Require **BOTH** flags. A single flag is one typo away from
     a rewrite. *(And print a 5-second `Ctrl-C` window before committing, naming the DB and the row counts.)*
   - **DEFAULT = DRY-RUN.** The whole body runs inside `BEGIN … ROLLBACK` unless both flags are present.
     **The dry-run must exercise the REAL statements against the REAL data** — a dry-run that only *simulates*
     proves nothing (`test-injecting-a-fake-at-the-chokepoint-cannot-prove-the-chokepoint-is-wired`). **Run
     the actual `UPDATE`s, take the actual counts, then `ROLLBACK`.** That is what makes the report evidence.
   - **The mapping is derived, never hardcoded:** legacy value → canonical code via **`app/languages.py`**
     (T-C1's Python registry — the SSOT mirror). A legacy value with **no** canonical mapping is **REPORTED
     AND LEFT ALONE**, never guessed. *(`Vietnamese` → `vi` is a name→code match. **`VI`, `zh_CN` etc. do not
     exist in the live data** — §3.7 ② verified that — but the script must still **refuse to guess**.)*

2. **THE MIGRATION BODY — the rules are already SEALED in §5.1. Implement them exactly; do not re-derive:**

   | # | Table | Rule (from §5.1 — settled from existing code) |
   |---|---|---|
   | 1 | `chapter_translations` | **3-pass renumber, no index drop:** (a) `SET version_num = 1000000 + rn` over the merged group *(old langs still in place ⇒ both old partitions stay unique, and `1000000+` cannot hit `1..N`)*; (b) `SET target_language = canonical`; (c) `SET version_num = version_num - 1000000`. 🔴 **`rn` is `ROW_NUMBER() OVER (PARTITION BY chapter_id, <canonical> ORDER BY created_at)` — INTERLEAVED BY `created_at`, not appended.** *(`migrate.py:156-172` re-runs exactly that `ROW_NUMBER()` **on every service boot** ⇒ an "append legacy after canonical" numbering is **silently re-interleaved at the next restart**. Append is not a stable state in this schema.)* |
   | 2 | `active_chapter_translation_versions` (**PK `(chapter_id, target_language)`**) | **Reuse `_PROMOTE_ACTIVE_SQL`'s precedence VERBATIM** (`workers/chapter_worker.py:36-58`) — ***never clobber a HUMAN-authored active version***: winner = (a) the `authored_by='human'` candidate if exactly one is human; else (b) greater `set_at`; else (c) greater `created_at`; else (d) greater `id` (uuidv7 = monotonic). 🔴 **Delete the LOSER'S ACTIVE ROW ONLY — the losing translation row itself SURVIVES** under the canonical code and is **one click from restoration** (`versions.py:246-256`). **That is what makes this merge non-destructive and reversible.** |
   | 3 | `translation_chapter_memos` (**PK `(book_id, chapter_index, target_language)`**) | derived cache, non-fatal on miss (`chapter_worker.py:1074-1094`) ⇒ **keep greater `created_at`, delete the loser.** |
   | 4 | 🔴 `segment_translations` (**`UNIQUE (chapter_id, target_language, segment_index)`** — `migrate.py:550-563`) | **THE TABLE SPEC 29's D12 MISSED. Without it the migration HARD-FAILS on that index.** Keep greater `translated_at`, delete the loser — safe because **a missing segment row already reads as DIRTY by design** (the `source_content_hash` staleness contract), so the delete just re-marks it for re-translate. |
   | 5 | **Plain rewrites — REQUIRED, not optional** | `translation_jobs` · `glossary_translation_jobs` · 🔴 **`book_translation_settings`** · 🔴 **`user_translation_preferences`**. **After T-C2 lands, a book whose stored default is `Vietnamese` 400s on EVERY translate** — normalizing these is what un-bricks it. |

3. **THE ROLLBACK PATH — 🔴 and be honest about what it can and cannot do.**
   - **BEFORE any write, the script DUMPS the exact pre-image** of every row it will touch, from all 7 tables,
     to **`services/translation-service/scripts/rekey_backup_<UTC-timestamp>.sql`** — a file of literal
     `INSERT`s (and the `DELETE`s needed to clear the post-state). **Print its path in the report.**
     **If the dump cannot be written, ABORT before touching anything.**
   - **`--rollback <file>`** replays it.
   - 🔴 **State the limit plainly in the report, do not bury it:** the rollback restores **these tables' rows**.
     It does **not** un-ring downstream bells (a worker that read a memo mid-run, a cache). **⇒ the real
     safety net is `pg_dump` before `--execute`, which is why `--i-have-a-backup` is a required flag and not
     a nag.** *(Do not let the existence of a rollback script talk anyone out of the backup.)*

4. **THE ASSERTIONS — before/after row counts, and they are the point of the exercise.**
   ```
   For EACH of the 7 tables, in ONE transaction, print:
     BEFORE:  total | legacy(non-canonical) | canonical | COLLIDING(would violate the key)
     AFTER :  total | legacy               | canonical | conflicts_remaining
   ```
   **The invariants the script ASSERTS (and ABORTS on, in dry-run AND execute):**
   - 🔴 **`AFTER.legacy == 0`** for every table. *(If not: an unmapped value exists — report it, change nothing.)*
   - 🔴 **`AFTER.total == BEFORE.total − BEFORE.expected_deletions`, and `expected_deletions` is computed
     BEFOREHAND from the collision query.** **A row count that drops by even one more than predicted is a
     BUG — ABORT.** *(This is the assertion the PO asked for by name. It is the difference between "the
     migration ran" and "the migration did what we said".)*
   - 🔴 **`AFTER.conflicts_remaining == 0`** — re-run the collision query post-merge; it must return zero.
   - 🔴 **NO `chapter_translations` ROW IS DELETED. EVER.** Only *active-pointer*, *memo* and *segment* rows are
     deleted. **Assert `chapter_translations.AFTER.total == BEFORE.total`.** *(The version rows are the user's
     actual translated prose. Losing one is the unrecoverable case.)*
   - 🔴 **`version_num` is `1..N` with no gap and no duplicate** per `(chapter_id, target_language)` after the
     3-pass renumber — because **`migrate.py` will re-derive it on the next boot**, and a mismatch there means
     the numbering **silently changes under the user's feet.**

5. **THE DRY-RUN REPORT — this exact shape. It IS the deliverable.** Print it to stdout **and** write it to
   `docs/analysis/2026-07-13-translation-lang-rekey-dryrun.md` *(memory `store-reports-in-files` — a report
   that lives only in a terminal is lost by the time the PO reads it)*:
   ```
   ══ TRANSLATION LANGUAGE REKEY — DRY RUN (NOTHING WAS WRITTEN; TRANSACTION ROLLED BACK) ══
   db: <host/db>   at: <UTC>   registry: app/languages.py (<N> canonical codes)

   MAPPING (derived from the registry — no hardcoded pairs):
     "Vietnamese" → "vi"        (5 rows across 4 tables)
     <unmapped>   → ✋ LEFT ALONE, listed below

   ┌ chapter_translations ─────────────────────────────────────────────────────┐
   │ BEFORE  total 103 | legacy 5 | canonical 98 | COLLIDING 1                  │
   │ AFTER   total 103 | legacy 0 | canonical 103 | conflicts 0                 │
   │ renumbered: ch <uuid> vi → version_num 1,2,3 (was 1,1,2 — INTERLEAVED by   │
   │             created_at, because migrate.py re-derives it on every boot)    │
   │ 🔴 DELETIONS: 0  (INVARIANT: a translation row is NEVER deleted)           │
   └───────────────────────────────────────────────────────────────────────────┘
   ┌ active_chapter_translation_versions ──────────────────────────────────────┐
   │ BEFORE  total 47 | legacy 1 | COLLIDING 1                                  │
   │ AFTER   total 46 | legacy 0 | conflicts 0                                  │
   │ 🔴 DELETIONS: 1 active POINTER (the losing row's translation SURVIVES and  │
   │    is 1 click from restore — versions.py:246-256)                          │
   │    ch <uuid>: kept version <id> (authored_by=human)  ← _PROMOTE_ACTIVE_SQL │
   │               dropped pointer to <id> (authored_by=machine, set_at older)  │
   └───────────────────────────────────────────────────────────────────────────┘
   … (translation_chapter_memos · segment_translations · translation_jobs ·
      glossary_translation_jobs · book_translation_settings ·
      user_translation_preferences)

   ── ASSERTIONS ──────────────────────────────────────────────────────────────
   ✅ legacy_after == 0 on all 7 tables
   ✅ total_after == total_before − expected_deletions   (predicted 2, observed 2)
   ✅ conflicts_remaining == 0
   ✅ chapter_translations deletions == 0
   ✅ version_num is 1..N, contiguous, unique, per (chapter_id, target_language)

   ── ROLLBACK ────────────────────────────────────────────────────────────────
   pre-image dump would be written to: scripts/rekey_backup_<ts>.sql (7 tables, N rows)
   replay with: --rollback scripts/rekey_backup_<ts>.sql
   ⚠ it restores THESE ROWS only. TAKE A pg_dump ANYWAY.

   ══ 🛑 STOPPED. NOTHING WAS WRITTEN. ═════════════════════════════════════════
   To execute (PO only, after reading the above, with a backup taken):
     python scripts/rekey_legacy_target_language.py --execute --i-have-a-backup
   ```

**Tests** — `services/translation-service/tests/test_rekey_legacy_target_language.py` (**NEW**).
🔴 **It hits a real DB ⇒ `pytestmark = pytest.mark.xdist_group("pg")`** (CLAUDE.md test-parallelization rule —
without it, parallel workers interleave and the counts lie). ⚠ **It must SEED ITS OWN legacy fixture rows and
clean up** — the shared dev DB carries pre-existing rows (`shared-dev-db-not-clean-fixture-e2e`), and it must
**never** assert against the live corruption.
- 🔴 `dry-run is the DEFAULT and WRITES NOTHING` — seed a legacy row, run with no flags, assert the row is
  **still legacy** afterwards. **This is the test that keeps the whole slice safe.**
- 🔴 `--execute WITHOUT --i-have-a-backup refuses` (and vice versa).
- `the collision case merges by the SEALED rule` — seed a chapter with a `Vietnamese` **human** active version
  and a `vi` **machine** active version with a newer `set_at`; assert **the HUMAN one wins** *(the naive
  "newest wins" is the bug this rule exists to prevent)*.
- 🔴 `no chapter_translations row is ever deleted` — assert `total` is unchanged; only pointers/memos/segments
  shrink.
- `version_num is contiguous 1..N and INTERLEAVED by created_at` — and 🔴 **a second assertion that re-running
  `migrate.py`'s own `ROW_NUMBER()` derivation over the post-state yields THE SAME numbers** (that is the
  every-boot re-derivation; if they differ, the numbering silently changes at the next restart).
- `an UNMAPPABLE legacy value is REPORTED and LEFT ALONE` — it must never be guessed.
- `the rollback file replays to the exact pre-image` — round-trip it.
- `segment_translations is in the table list` — a **literal guard** against re-dropping the table spec 29
  missed. *(A `set(TABLES) == {…7…}` assertion. It is dumb and it is the one that catches the regression.)*

**DoD evidence:** `"T-C10: pytest tests/test_rekey_legacy_target_language.py <N> passed (xdist_group=pg) — dry-run is the DEFAULT and provably writes nothing; --execute requires BOTH flags; the human-authored active version WINS over a newer machine one (_PROMOTE_ACTIVE_SQL precedence); ZERO chapter_translations rows are ever deleted; version_num is 1..N interleaved by created_at AND matches migrate.py's own every-boot ROW_NUMBER() re-derivation; all 7 tables incl. segment_translations (the one spec 29's D12 missed). 🔴 DRY-RUN EXECUTED against the dev DB inside a ROLLED-BACK transaction — the full report is PASTED BELOW and written to docs/analysis/2026-07-13-translation-lang-rekey-dryrun.md. 🛑 THE MIGRATION WAS NOT EXECUTED. STOPPING FOR PO REVIEW per decision D-1. <paste the report>"`

> 🔴 **AND THEN STOP.** Do not proceed to the wave close-out with T-C10's execution pending as though it were
> done. **The wave CLOSES with the rekey un-executed** — that is the expected, correct end state. The PO
> executes it separately (`D-TRANSL-LANG-REKEY-EXECUTE`, §10).

---

## 7 · Registration checklist (GG-8)

> **NOT APPLICABLE — Wave T registers ZERO new panels.** See §1.4.

The GG-8 checklist (plan 30 §8) governs **new panels**. Wave T adds none. It therefore touches **none** of:
`catalog.ts` · `studio.json` (panel keys) · `frontend_tools.py` · `contracts/frontend-tools.contract.json` ·
`studioLinks.ts` · `tours.ts`.

**What Wave T DOES owe the drift-locks — run them anyway, and assert a DELTA OF ZERO:**

```bash
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd ../../frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

All must be **green and UNCHANGED**. If `panelCatalogContract.test.ts` moves by even one, **you have added a
panel and gone off-plan.** The running baseline (plan 30 §8.0) is **unaffected by Wave T**.

**🔴 Wave T DOES owe the CONTRACT locks (new — T-X0):**

```bash
# the contracts parse
python -c "import yaml,sys; [yaml.safe_load(open(p)) for p in sys.argv[1:]]" \
  contracts/api/translation/v1/openapi.yaml contracts/api/books/v1/openapi.yaml
# the language registry is a three-way lock: TS ⇄ contracts/languages.contract.json ⇄ Python ⇄ OpenAPI enum
cd frontend && npx vitest run src/lib/__tests__/languagesContract.test.ts src/lib/__tests__/languages.test.ts \
                             src/lib/__tests__/noFrontendLanguageNormalizer.test.ts
cd ../services/translation-service && python -m pytest \
  tests/test_languages_parity.py tests/test_openapi_target_language_enum.py tests/test_mcp_language_enum.py -q
```

**i18n keys ARE added** (~25 new `translation.*` / `common.errors.*` keys across the slices).
🔴 **`en` ONLY during the build; the 17-locale batch runs ONCE, in T-C9.** *(Reversal — see §3.6 row 14.)*
**Generate, never hand-write** (memory `i18n-locale-generation-tool`), and **spot-check that `vi` and `zh-CN`
actually changed** (memory `i18n-translate-self-heal-only-fires-on-hard-failures` — the self-heal skips SOFT
untranslated flags).

---

## 8 · WAVE DEFINITION OF DONE

A literal checklist. **Every box must be tickable with pasted evidence, not a claim.**

- [ ] **1 · All 24 slices committed**, each as its own commit, each with its tests green at commit time.
      *(24, not 23: **+ T-C10** (the PO-gated rekey, D-1). **T-A4 survives but re-scoped to D6 only** — T8 is
      **`W0-S15`'s**, D-2. 🔴 **If `W0-S15` had not landed, T-A4/T-A5/T-A6 + T-C5's A4 leg are PARKED with a
      defer row — say so here explicitly rather than quietly shipping 20.**)*
- [ ] **2 · The full frontend suite is green.**
      `cd frontend && npx vitest run` → **`N_fe_before + ~80` passed, 0 failed.**
      *(Assert the DELTA against the §2 baseline, never a literal — plan 30 §8.0: a literal "sends a builder
      hunting a phantom regression".)*
- [ ] **3 · The full translation-service suite is green.**
      `cd services/translation-service && python -m pytest tests -q -n auto --dist loadgroup`
      → **`N_be_before + ~26` passed.**
      🔴 **`test_coverage_languages_only.py` (T-C7) HITS A REAL DB ⇒ it MUST carry
      `pytestmark = pytest.mark.xdist_group("pg")`.** Every other new Python test is a pure
      function/validator/in-process-FastMCP test and needs no mark. **Without the mark the parallel workers
      interleave on the shared dev Postgres and the counts lie.**
- [ ] **4 · The drift-locks are green AND UNCHANGED** (§7 — delta 0 on the panel enum, three-way equality holds).
- [ ] **4b · 🔴 THE CONTRACT LOCKS are green** (§7, new): both OpenAPI files parse; the language registry's
      **four-way** lock holds (TS ⇄ `contracts/languages.contract.json` ⇄ `app/languages.py` ⇄ the OpenAPI
      `TargetLanguage` enum); `noFrontendLanguageNormalizer` green.
- [ ] **5 · 🔴 LIVE BROWSER SMOKE — in BOTH states.** The spec's verify gate is explicit and non-negotiable:
      *"Live browser smoke, both states — healthy backend **and** `docker stop infra-translation-service-1`.
      **A mock-only pass cannot see T4/T5/T6; they were found only by stopping a real service.**"*

      🔴 **PHASE A CARRIES THIS TOO — it is NOT exempt.** Spec 29's *"Phases A and B do not [carry the gate]"*
      is a statement about **`workflow-gate.py`'s BE↔BE autodetect** (`scripts/workflow-gate.py:232` matches
      only `services/<name>/`, so a FE-only diff cannot trip it, and the warning is soft anyway). **It is NOT
      an exemption from the spec's own bar.** T4/T5/T6 are **Phase A** defects and **were found ONLY by
      stopping a real service.** **Phase A's VERIFY evidence string MUST carry the `live smoke:` token by
      fiat of this plan, even though the script will not demand it.**
      🔴 **Do NOT accept `live infra unavailable` for Phase A.** The stack is bootable in this repo. If it
      genuinely will not come up, **that is a STOP-and-fix-the-stack, not a skip** — Phase A's two headline
      defects cannot otherwise be verified at all.

      **Rig:** `vite dev` on **:5199** → gateway **:3123** → docker compose.
      ⚠ **`:5174` is the BAKED nginx prod build and a host `vite dev` SHADOWs it** (memory
      `frontend-5174-is-baked-prod-nginx-not-vite`). Use **:5199**.
      ⚠ **Rebuild before smoking** — stale images = false-green (memory `live-smoke-rebuild-stale-images-first`).
      Account: `claude-test@loreweave.dev` / `Claude@Test2026`. Books: **`Dracula`** (`019eeb09-…`, 8 chapters,
      2 languages **incl. the legacy `Vietnamese`**) and **`Ma Nữ Nghịch Thiên (POC)`** (`019f1783-…`, 14
      chapters, 0 translations — *exercises the plain non-force path and clobbers no existing data*).
      ⚠ Playwright: **refs go stale — drive via `evaluate` + `data-testid`** (memory
      `playwright-live-dockview-automation-recipe`).

      **🔴 PREREQS — three myths killed by `Q-29-LIVE-SMOKE-PREREQS`. Do not "prepare" for any of them:**
      1. **The empty `user_default_models` worry is VOID — do NOTHING about it.** Nothing in the translate
         submit path resolves *"the default model for capability X"*. `TranslateModal.tsx:86` calls
         `useUserModels({capability:'chat'})`, which **LISTS** the account's chat-capable models; **the user
         PICKS one**, and `:227-228` submits it explicitly as `model_source:'user_model'` + `model_ref:<uuid>`.
         The 422 `TRANSL_NO_MODEL_CONFIGURED` fires **only when no ref is present at all.** The test account's
         ~15 BYOK models are exactly what the picker needs. **Do not seed `user_default_models`; do not add a
         default-resolution fallback.**
      2. **lm_studio is NOT a prerequisite.** T8's claim is *"the enabled CTA CREATES a job"* — evidence is
         **201 + a `job_id` + the matrix showing it pending/running**, which is reached **before any model is
         called.** If lm_studio is down the job simply transitions to **failed AFTER creation** — **the
         creation evidence still stands.** Say so in the evidence string. **Do not block, defer, or weaken the
         smoke because lm_studio is not running.**
      3. **The REAL stack dependency is `provider-registry`** (`jobs.py:228` `resolve_model_name` calls it) —
         **not** lm_studio. `docker compose ps` in `infra/`; if `translation-service` or `provider-registry` is
         not Up, `docker compose up -d`.
      **🔴 $0 SPEND RULE (binding):** in the ModelPicker select a **local lm_studio** chat model (Qwen2.5 7B /
      Gemma-4 26B). **NEVER select `gpt-4o`** — that is real money for a CTA-wiring proof.

      **HEALTHY-backend script (paste the output of each):**
      1. Open `Dracula` → Translation tab. **A `Translate…` button is visible in the header.** *(T1 — today
         there is none.)*
      2. The table shows **8 rows, one per chapter** — including the **4 untranslated** ones, each with a
         checkbox. *(T2 — today it shows 4.)*
      3. The **legacy `Vietnamese` column still renders.** *(D13 read-side.)*
      4. Tick **2** chapters → **Translate Selected** → the modal footer reads **"Translate 2 selected"** and
         is **ENABLED**. *(🔴 **A REGRESSION CHECK on Wave 0's `W0-S15`, not a Wave-T fix** — PO D-2 moved T8
         there. **Smoke it anyway:** T-A4 edits the same lines, and this is the cheapest possible proof that it
         did not silently revert them — see R9.)*
      5. Click an **untranslated cell** → the modal opens with **that column's language** selected. *(D6 —
         **this one IS Wave T's**, slice T-A4.)*
      6. Submit a real job on **`Ma Nữ Nghịch Thiên`** with a **local lm_studio** chat model (**$0**) →
         **201 + a `job_id` + the matrix shows it pending/running.** *(The loop closes. **A post-creation
         failure because lm_studio is down is ACCEPTABLE evidence — this is about CTA wiring, not the
         worker.**)*
      7. `Ma Nữ Nghịch Thiên` → the empty-state **Start Translation** CTA still works. *(D2.)*
      8. 🔴 **`Dracula`: the `Vietnamese` column shows a "Legacy" pill; its cells have NO button and NO
         "N changed" badge.** *(T-C8 / X4 — the paid-action dead end.)* Click a **`vi`** cell → still works.
      9. 🔴 **`Dracula`: change the language AND the model in the modal, then CLOSE it without submitting.
         Re-open it. The book's stored default is UNCHANGED.** *(T-A5 / X2 — the cross-user settings clobber.
         Confirm in the DB: `SELECT target_language, model_ref FROM book_translation_settings WHERE book_id=…`
         is the same before and after.)* Then tick **"Remember as this book's default"**, submit, and confirm it
         **did** change. **Both halves, or the fix is unproven.**
      10. 🔴 **Open a chapter in the editor. Type. WITHOUT saving, switch to Translate workmode, then back to
          Write. THE TYPED TEXT IS STILL THERE.** *(T-A7 / X1 — silent data loss. **This is the highest-severity
          item in the whole wave and it is invisible to every unit test that does not remount.**)*

      **SERVICE-DOWN script** — `docker stop infra-translation-service-1`
      *(compose service `translation-service` in dir `infra` ⇒ that exact container name — `docker-compose.yml:558`)*, then:
      11. Reload the Translation tab → **a readable, localized error + a Retry button.** **`grep` the rendered
          text for `"trying to proxy"` → ZERO hits.** *(T4 — today it leaks the raw proxy string.)*
      12. The **header `Translate…` CTA is still visible AND ENABLED** in the error state, and **clicking it
          OPENS the modal.** *(D1 — the modal fetches its own chapters, so a disabled button here would be the
          T4/T10 dead-end all over again.)*
      13. Open the modal → **the language picker and the ModelPicker render IMMEDIATELY**; the chapter
          checklist shows an inline error + Retry within **12 s** — **and the dialog body is NOT replaced.**
          *(T5/D8 — today it wedges on "Loading chapters…" forever.)*
      14. 🔴 **With 2 chapters ticked, stop the service, then open the modal: the footer STILL reads "Translate
          2 selected" and Submit is ENABLED.** *(D16 — the preselection must not be erased by the failed
          chapter fetch.)*
      15. Open the editor's Translate workmode → **an error banner**, not a blank title + `??` language.
          *(T6.)*
      16. `docker start infra-translation-service-1` → press **Retry** → everything recovers **without a page
          reload.**

      **Evidence string must name what was OBSERVED, not what was run.**
- [ ] **6 · 🔴 `/review-impl` RUN ON THE WAVE'S DIFF, AND EVERY BUG IT FINDS FIXED BEFORE THE WAVE CLOSES.**
      `/review-impl wave-T-translation-repair`. **This is a literal step, not a formality** (PO policy, §0
      rule 2). Fold its findings into the POST-REVIEW evidence. **A finding that is not fixed needs a defer row
      that clears one of CLAUDE.md's 5 gates — "we ran out of time" is not one of them (there is no deadline).**
- [ ] 🛑 **6b · THE REKEY DRY-RUN IS DONE AND THE MIGRATION IS *NOT* EXECUTED** (**T-C10**, PO decision D-1).
      The **dry-run report is pasted into the evidence AND written to
      `docs/analysis/2026-07-13-translation-lang-rekey-dryrun.md`**; the script is committed;
      `python scripts/rekey_legacy_target_language.py` (no flags) **provably writes nothing**; and the wave
      **closes with `Vietnamese` still in the database.** 🔴 **That is the CORRECT end state — the PO executes
      it separately.** *(If the DB is clean when you finish, someone ran it. That is a decision-violation, not
      a success.)*
- [ ] **7 · `docs/sessions/SESSION_HANDOFF.md` updated** — the ▶ NEXT SESSION block, and the Deferred list
      carries 🔴 **`D-TRANSL-LANG-REKEY-EXECUTE`** (§10) **with a pointer to the dry-run report**, plus a
      **Decisions** row recording that **T8 was discharged in Wave 0 / `W0-S15`** (PO D-2), so the next agent
      does not "notice T8 is missing from Wave T" and re-open it.
- [ ] **8 · The wave is committed.** Stage **enumerated files only** — 🔴 **never `git add -A`** (3 live tracks
      share this checkout; memory `shared-file-collision-safe-staging-multi-agent-checkout`). And remember
      `git commit -- <path>` commits the **WORKING TREE, not the index** (memory
      `git-commit-pathspec-reads-working-tree-not-index`), and the index may already carry another agent's
      pre-staged changes (`git-index-may-carry-prestaged-unrelated-changes`) — **check `git diff --cached`
      before every commit.**

---

## 9 · Risks — and the tell that each has fired

| # | Risk | The tell | Mitigation |
|---|---|---|---|
| **R1** | **T-A3's row-shape change silently breaks a derivation.** D3 lists 7 call sites keyed off `coverage.coverage`. Miss one and the *selection* diverges from what is *on screen* — the user translates chapters they did not pick. | `TranslationTab.badge.test.tsx` reds, **or worse: it stays green** and only the live smoke shows a wrong count in the legend. | The slice enumerates **all 7** with line numbers. **Grep `coverage.coverage` in `TranslationTab.tsx` after the slice → must be ZERO hits outside `coverageByChapter` and `orphanCount`.** Make that grep a literal DoD line. |
| **R2** | **T-A4 re-introduces T8 through the back door** by "simplifying" `handleLangChange`'s guard at `TranslateModal.tsx:205`. 🔴 **Sharper after PO D-2:** T8's fix now lives in **Wave 0 (`W0-S15`)**, so **Wave T is no longer even *looking* for T8** — and T-A4 edits the exact lines that carry it. | The guard is "cleaned up" and no test in *this* wave's mental model covers it. **The fully-translated book silently opens with every action disabled again — the original bug, un-shipped by the wave that was supposed to be safe.** | The guard is called out **in bold** in the slice. **T-A4's DoD REQUIRES re-running W0-S15's three guards** (they live in the same test file) — and `TranslationTab.preselect.test.tsx`'s *fully-translated book* case is the canary: **it fails the moment the guard goes.** If that file does not exist when you arrive, **W0-S15 has not landed — see R9.** |
| 🔴 **R9** | **T-A4 SILENTLY REVERTS `W0-S15`.** They edit the **same JSX block** in `TranslationTab.tsx` (~:300-305) and the **same component**. A builder who writes the call site out **wholesale from this plan** overwrites Wave 0's prop with a stale block — **and then re-adds it themselves**, so **every test still passes.** *(Memory: `green-suite-proves-the-working-tree-not-the-commit`.)* | **Nothing. That is the danger.** The diff looks additive; the suite is green; the data-loss fix Wave 0 shipped is quietly gone from `main` — or double-implemented in two waves' diffs and conflicting at merge. | **§1.2.0 + the slice's opening box: `grep` FIRST, then EDIT the existing block — never retype it.** T-A4's DoD **requires pasting the pre-slice `grep` output** proving the prop was already there. **And never `git add -A`** (three tracks, one checkout). |
| 🔴 **R10** | **T-C10's migration ends up in `app/migrate.py`** — the "obvious" home for a migration in this service. | 🔴 **IT EXECUTES ON THE NEXT SERVICE BOOT.** `migrate.py`'s DDL block runs **every time the service starts** (§5.1 — that is *why* the renumber must interleave). A PO-gated destructive rekey would fire **unattended, on a container restart, with no backup** — the exact outcome D-1 exists to prevent, reached by the most natural-looking wrong turn in the wave. | **T-C10 says it in a red box: the script is STANDALONE (`scripts/rekey_legacy_target_language.py`), NOT imported by anything, DRY-RUN by default, and needs TWO flags to write.** Its first test asserts **a bare invocation writes nothing.** |
| **R3** | **The MCP `Literal` drifts from the registry** — a 19th language is added to `languages.ts` and the enum still advertises 18. **This is the bug we are fixing, one layer up.** | An agent cannot translate into a language the GUI offers. Silent. | `test_literal_does_not_drift_from_the_registry` (`get_args`) **+** the live-`inputSchema` assertion **+** the `contracts/languages.contract.json` parity test on both sides **+** T-X0's OpenAPI-enum lock. **FOUR** guards, because `css-var-duplicated-across-two-consumers-drifts` says two consumers of one truth *will* diverge. |
| **R4** | **T-C2's chokepoint guard breaks a legacy book's translation entirely** — a `Vietnamese` settings row 400s every job, even into a valid language. | A user on `Dracula` cannot translate **at all**. | The guard is on the **resolved effective value only when the payload omits the language**. The GUI **always** sends an explicit language (`TranslateModal.tsx:226`) ⇒ unreachable from the browser. **The live smoke on `Dracula` (step 6) is the proof.** If it 400s, the guard is in the wrong place — move it out of `resolve_effective_settings`. |
| **R5** | **No HTML draft exists** (§3.5), so "the mock is the acceptance criterion" has no mock. A builder invents a layout. | Scope creep; a redesigned matrix nobody asked for. | **Every slice is a behavior fix inside the EXISTING layout.** Acceptance = spec 29's D1–D13 + its verify gate. **Do not restyle anything.** If a slice tempts you to redesign, you have misread it. |
| **R6** | **`access_level` is stale in the react-query cache** — a grant revoked mid-session leaves the CTA enabled. | A late 403 on submit. | **Acceptable, and already handled:** T-A6's toast renders the 403 readably. **The gate is a UX affordance, not a security boundary — the backend gate (`jobs.py:55` `GrantLevel.EDIT`) is the boundary and it is untouched.** Do not "fix" this by weakening the backend. |
| **R7** | **The 17-locale i18n regen silently no-ops** (the self-heal skips SOFT untranslated flags — memory `i18n-translate-self-heal-only-fires-on-hard-failures`). | The new keys render as raw key strings in `vi`/`zh-CN`. | **Spot-check `vi` and `zh-CN` diffs before each commit that adds a key.** Make it a per-slice habit, not an end-of-wave audit. |
| **R8** | **A concurrent agent enters these files** (shared checkout, 3 live tracks). | `git status` shows a translation file you did not touch. | **Re-run pre-flight check 1 before EVERY commit.** Never `git add -A`. Enumerate paths. |

---

## 10 · Defer register — the starting rows

| ID | Origin | What | Gate (CLAUDE.md 1–5) | Target / trigger |
|---|---|---|---|---|
| 🔴 **`D-TRANSL-LANG-REKEY-EXECUTE`** *(replaces `D-TRANSL-LANG-BACKFILL` — **PO decision D-1**)* | Wave T · **T-C10** | **EXECUTE** the `Vietnamese` → `vi` rekey. 🔴 **THE MIGRATION ITSELF IS NOT DEFERRED — IT IS BUILT AND DRY-RUN IN-WAVE** (slice **T-C10**: `services/translation-service/scripts/rekey_legacy_target_language.py` + rollback + before/after assertions + the dry-run report at `docs/analysis/2026-07-13-translation-lang-rekey-dryrun.md`). **What is deferred is ONE thing: pressing the button.** | 🔴 **NOT a normal defer row — it is the run's ONE SANCTIONED STOP.** §0 rule 3 bullet 1: *"a destructive/irreversible action … a migration that rewrites user rows."* The PO ruled: *"the agent may NOT execute it unattended."* | **The PO**, after reading T-C10's dry-run report, **with a `pg_dump` taken**, running `python scripts/rekey_legacy_target_language.py --execute --i-have-a-backup`. ⚠ **Approving the PLAN ≠ approving the EXECUTION.** ✅ Prerequisite already met by **T-C2** (write-side validation) ⇒ the bad set is **closed** and cannot grow while this waits — verify with `SELECT DISTINCT target_language FROM chapter_translations WHERE target_language !~ '^[a-z]{2}(-[A-Z]{2})?$'` returning a set that **has not grown** since 2026-07-12. |
| **`D-29-I18N-BACKFILL`** *(conditional — write it ONLY if it fires)* | Wave T · T-C9 | The 17-locale generation could not run because **LM Studio was not up** on `:1234`. | **#4 — blocked on a genuinely external dev-time backend.** | Next time LM Studio is up. 🔴 **NOT a blocker: `fallbackLng: 'en'` means the English strings are already SHIPPING and correct.** Per §0 rule 3: **write the row and KEEP GOING. Do not stop, do not ask.** |

🔴 **DELETED: `D-TRANSL-S11-JOBCONTROL-EFFECTS`.** The first draft deferred S11. `DEF-29-S11-AGENT-REFRESH`
read the code and **proved the premise wrong** — the fix is **one line** (`invalidateAfterConfirm.ts:24`) and
it **clears none of the 5 gates** (in scope · tiny · root cause known · nothing external). **It is FIXED in
slice T-B6.** *"A defer row for a one-line change is the exact anti-pattern CLAUDE.md's FIX-NOW rule kills."*

**🔴 DELIBERATELY NOT DEFERRED (all were candidates; all fail the gate ⇒ all are fixed in-wave):** the editor
unmount / data loss (**X1** — *"FIX IT NOW; do NOT write a defer row; do NOT wait for 'a separate spec'"*) ·
the settings clobber (**X2** — a **tenancy** defect) · the editor's 100-chapter blindness (**X3** — one call
site, the helper is already being lifted) · the third re-translate dead-end (**X4** — a **paid-action**
defect) · **S11**.

**No other row is expected.** Per §0 rule 3, a blocker found during the build gets a row **and the build keeps
going**. Per CLAUDE.md's defer gate: **if fixing the bug is cheaper than writing and carrying its defer row,
just fix it.** Every one of S1–S12 is in this wave precisely because it fails the defer gate.

**KNOWN, ACCEPTED RESIDUALS — state them in the wave close-out, do NOT build them:**
- `getSegmentCoverage` (`TranslationTab.tsx:182-195`) fires one request **per visible language**. Pre-existing;
  same order of magnitude as coverage. **Accepted.**
- After T-C7, the *matrix's own* coverage payload is still unbounded in `translated-chapters × languages`. It
  is **ONE request** and it exists today. **Accepted.** If a real 2000-chapter book later measures badly, the
  fix is a `chapters/index` lightweight route in book-service — **buildable in this repo, but not justified
  without profiling evidence** (CLAUDE.md defer-gate #4: perf items fix when profiling shows pain).
- **`D-E0-4A-SETTINGS-PERUSER`** (`docs/analysis/2026-06-20-tenant-isolation-idor-sweep/FINDINGS.md:54`) — the
  composite-PK migration `(book_id, owner_user_id)` that makes book settings **genuinely** per-user — **stays
  deferred** (gate #2). 🔴 **T-A5 does NOT fix it; it SHRINKS ITS BLAST RADIUS** from *"every language/model
  pick by any collaborator, on every translate"* to *"a collaborator deliberately ticked 'remember as book
  default'"* — which under **User Boundaries** is a **legal, intentional per-book write by an EDIT grantee**.
  **Add a cross-ref note to that row pointing at T-A5.**

---

## 11 · Commit order (the literal sequence)

```
T-X0  🔴 CONTRACT-FIRST + spec token fixes      (access_level · languages_only · error codes)   ← FIRST
      ── nothing else starts until T-X0 commits (CLAUDE.md: contract frozen before FE flow) ──
T-A1  typed errors (classifyApiError) + shell   (T4, T10, D9)          ← X0
T-A2  header Translate… CTA (TRI-STATE gate)    (T1, D1, D2)           ← A1
T-A3  one row per CHAPTER + shared fetch + D4/D5(T2, D3, D4, D5)       ← A1
      ── 🔴 T8 IS **NOT** BUILT HERE. Wave 0 / W0-S15 owns it (PO D-2). ──
T-A4  preselectedLang ONLY — D6                 (D6; T8 = W0-S15)      ← A2, A3, 🔴 W0-S15
T-A5  modal stops wedging + DELETE the auto-PUT (T5, D7, D8, D16, X2)  ← A4
T-A6  the EDIT-grant 403 becomes readable       (D10 ½)                ← A5
T-A7  🔴 editor STAYS MOUNTED in Translate      (X1 data loss, X3)     ← A3
      ── PHASE A SHIPPABLE HERE (this is what the user asked for) ──
T-B1  ChapterTranslationsPanel error state      (T6)                   ← A1
T-B2  onSaved wired → version list refreshes    (S4)                   ← B1
T-B3  pendingLangs add-a-language + lang:undef  (T7, D11, S10)         ← B1
T-B4  the paid-job poll terminates              (S1)                   ← A1
T-B5  the remaining swallowed errors            (S2,S3,S5,S6,S8)       ← A1, A6
T-B6  invalidateAfterConfirm gains 'segment-'   (S11 — NOT deferred)   ← no deps
      ── PHASE B SHIPPABLE HERE ──
T-C1  the language registry becomes a contract  (D13 ①)                ← X0
T-C2  normalize→validate on 6 NOVEL write edges (D13 ②)                ← C1
T-C3  the MCP enum — 3 WRITE args only          (D13 ③)                ← C1
T-C4  5 language inputs → LanguagePicker        (D13 ④, S7)            ← C1
T-C5  access_level gates WITH A REASON          (T9, D10 ½)            ← X0, A2, A4
T-C6  ConfirmNameDialog → FormDialog + S12      (S9, S12)              ← no deps
T-C7  coverage ?languages_only + MCP staleness  (X5)                   ← X0
T-C8  🔴 the legacy column's 3 dead ends        (X4 — a PAID 400)      ← C1, C2, C4
T-C9  the i18n batch + the parity test          (D9 localization)      ← every en-key slice
T-C10 🛑 the Vietnamese→vi REKEY: WRITE + DRY-RUN + **STOP**  (PO D-1) ← C2, C1
      ── LIVE-SMOKE GATE (both states) + /review-impl + WAVE CLOSE ──
      ── 🛑 THE WAVE CLOSES WITH THE REKEY **UN-EXECUTED**. THAT IS CORRECT. ──
```

**T-B4, T-B6, T-C6 have no dependencies** — use them to fill any stall. **Blocked ≠ stopped.**

> 🔴 **TWO CROSS-WAVE FACTS THAT CHANGE THIS ORDER (PO decisions, sealed 2026-07-13):**
> 1. **`T-A4` now dependsOn `W0-S15` (Wave 0).** If Wave 0 has not landed, **park T-A4 → T-A5 → T-A6 and
>    T-C5's A4 leg**, and build everything else. **Do NOT build T8 here** (§1.2.0).
> 2. **`T-C10` is the LAST slice and it ENDS IN A STOP.** It is placed after the i18n batch on purpose: it is
>    the only slice whose output is a *question for a human*, and the wave must be otherwise **finished and
>    green** before that question is asked. **Do not fold it into an earlier commit, and do not "finish the
>    job" by running it.**

> 🔴 **T-C8 MUST NOT BE DROPPED IF THE WAVE GETS TIGHT.** T-C2 makes every legacy-column re-translate a
> **guaranteed 400**. Shipping T-C2 **without** T-C8 leaves a **live "N changed" badge the user pays to
> click and which cannot ever succeed** — i.e. **T-C2 alone CREATES a paid-action defect**, the run's own
> CRITICAL class. **They ship together or neither ships.**

---

## 12 · 🔴 CROSS-WAVE ESCALATION — the 7 homeless legacy sub-tabs are NOT Wave T's

The reconcile brief routed the **homeless legacy sub-tab** block (the GG-4 retirement gate would DELETE these
unless some wave homes them) into **every** wave's prompt, unfiltered. **Wave T is not their home, and this
section exists so the information is not silently dropped on the floor.**

**Why not Wave T:** every one of the seven **names another wave in its own body**; **none is a translation
surface**; and Wave T's §1.4 ledger is **+0 panels** (it touches neither `catalog.ts` nor
`frontend_tools.py` nor `contracts/frontend-tools.contract.json`). Homing a KG or editor panel here would
**break that invariant** and **collide with the wave-6 / wave-8 reconcile agents editing those same files
right now** (3 live tracks share this checkout — memory
`shared-file-collision-safe-staging-multi-agent-checkout`). **So Wave T records and escalates; it does not
edit another wave's plan.**

| Sub-tab | Its real home (per its own body) | Verified? |
|---|---|---|
| `compose` (ComposeView — **the ONLY `useAdaptFromSource` surface**) | **Wave 6** — a 4th panel `scene-compose`, leaf-mounted (EC-6: never `<CompositionPanel soloPanel=…>`) | — |
| `assemble` (ChapterAssembleView — **the 2nd `useCorrection` producer**; Wave 1's capture seam is incomplete while it is homeless) | **Wave 6** — `chapter-assemble` | — |
| `cast` (CastCodexPanel — kind-grouped, **spoiler-safe story-state join**; `kg-entities` is a flat cross-project LIST and is **not** this) | **Wave 8** — `cast`, category `storyBible` | — |
| `arc` (CharacterArcView — a character's events over the KG) | **Wave 8** — `character-arc` | — |
| `worldmap` (WorldMap — the place-graph: backdrop, persisted spatial arrangement, place↔place predicates) | **Wave 8** — `place-graph` **OR** an explicit PO won't-fix. 🔴 **A CIRCULAR DEFER: spec 38 says "it belongs to plan 30's Wave 6" — WAVE 6 DOES NOT CONTAIN IT.** Wave 8 ports only the **write leg**. **Silence here = the feature dies at GG-4.** | — |
| `canonview` (CanonAtChapterPanel — read-only canon SNAPSHOT; **its 2nd mount is the divergence BRANCH POINT**) | **Wave 6** M3 (a file row on DivergencePanel's table) **+** a section in the existing `scene-inspector` | — |
| `flywheel` (FlywheelPanel — **knowledge-graph** growth via `knowledgeApi.getFlywheel`) | **Wave 8** — `canon-growth` | — |

🔴 **TWO FALSE MAP ROWS — VERIFIED IN THE TREE, and they are the dangerous part.**
`docs/plans/2026-07-13-studio-wave-6-editor-craft.md:2631-2659` defines `LEGACY_SUBTAB_HOME`, and **two rows
point at panels that are not the thing**:

```
:2641   flywheel:    'quality-corrections',   // ← WRONG. quality-corrections = CorrectionStatsTable
                                              //    (composition correction RATES). FlywheelPanel = KG growth
                                              //    (knowledgeApi.getFlywheel). TWO SERVICES, TWO DATASETS.
                                              //    Wave 1's OWN plan (:2445) says so IN WRITING.
:2644   arc:         'arc-templates',         // ← WRONG. arc-templates (Wave 4) = the structure-TEMPLATE
                                              //    library + 拆文. arc-inspector (Wave 2) = the arc SPEC tree.
                                              //    NEITHER is a character's event arc over the KG.
```

**Because the gate is `expect(Object.keys(LEGACY_SUBTAB_HOME).sort()).toEqual([...ALL_TABS].sort())`
(`:2659`), a mislabelled row makes the machine-checked test GO GREEN ON A FEATURE BEING DELETED.** That is
strictly worse than a missing row, which would at least red.

> **ACTION (owner: the wave-6 and wave-8 reconcile agents / the PO — NOT Wave T):**
> 1. **FIX the two rows** in wave-6's `LEGACY_SUBTAB_HOME`.
> 2. **Home the seven** per the table above.
> 3. If the PO instead rules any of them superseded, that MUST become an explicit **`DELETE_ON_PURPOSE`** row
>    in plan 30 §7's *"Consciously OUT OF SCOPE"* table — **never a mislabelled map row.** And a ruling that
>    `compose` is superseded by the chat **must still name a home for `useAdaptFromSource`** — it exists on no
>    other surface and retirement deletes it outright.
