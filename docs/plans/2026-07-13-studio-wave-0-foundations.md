# Wave 0 — FOUNDATIONS · Implementation Plan

> **Type:** FS · **Size:** **XL** (re-sized 2026-07-13 after folding the adjudication register **and the
> PO's sealed `D-1..D-7`**: logic ~20 · side effects: **2 new REST routes + 1 OpenAPI contract change**,
> 1 additive DDL migration, 2 MCP arg changes, 1 MCP tool retirement + **2** contract regens, 1 packer lens
> on the generation hot path, 1 Go MCP description fix, **1 app-wide FE error default (`MutationCache`)**
> · files ~74 · **21 slices**)
> **Source spec:** [`docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §7 Wave 0 (X-1..X-10)
> **Planned at:** HEAD `9262ed53e`+ (branch `feat/context-budget-law`), 2026-07-13.
> **Revised 2026-07-13** — folded the PO's **sealed `D-1..D-7`** (§0-PO). **Two of them ADD SLICES:**
> `W0-S15` (D-2 · Translate drops the user's ticked chapters) and `W0-S16` (D-3 · the global
> `MutationCache.onError` — *every failed mutation in the FE is silent today*). **19 slices → 21.**
> Also corrected: the motif-mine story is a **500 at CONFIRM, before the enqueue** — **not** a 404 at the
> poll, and **no user was ever charged** (`W0-BE1` was already built for the true mechanism; only the
> narrative prose was stale).
> **Every fact below was verified by opening the file.** Where this plan contradicts plan 30, the
> contradiction is flagged 🔴 **AUDIT CORRECTION** with the code evidence. There are **five**.

---

## 0-PO · 🔒 SEALED DECISIONS — **D-1 … D-7**, sealed 2026-07-13. **Binding. Do not re-litigate.**

> These were sealed by the PO **after** this plan's QC gate, on the adversarial audit of the whole
> 10-wave batch. **Two of them ADD SLICES TO WAVE 0** (`W0-S15` ← D-2, `W0-S16` ← D-3). They are
> reproduced **verbatim** — the paraphrase is the drift.

- **D-1 · REKEY the corrupted language data — but DRY-RUN FIRST.** 5 rows say `Vietnamese` next to 89
  saying `vi`, inside `UNIQUE(chapter_id, target_language, version_num)`. The migration is DESTRUCTIVE
  (a 3-table rekey). The PO's ruling: **write the migration + a rollback path + a before/after row-count
  assertion, run a DRY-RUN, show the output, and only then execute.** The agent may NOT execute it
  unattended. (This is the one CRITICAL-class stop in the whole build.)
- **D-2 · WAVE 0 IS THE HOTFIX BATCH.** It already carries 3 of the 4 HIGH bugs (AddModelCta = X-1/W0-S3,
  motif-Mine 500 = W0-BE1, the conformance 404s = W0-S7). **PULL THE 4th FORWARD INTO WAVE 0**: Translate
  silently discards the user's ticked chapters and substitutes the whole backlog
  (`TranslationTab.tsx:300-305` renders `<TranslateModal>` with **no `preselectedChapterIds`** though the
  prop exists and the sibling `ExtractionWizard` call site passes it).
- **D-3 · ADD THE GLOBAL `MutationCache.onError` TO WAVE 0.** `frontend/src/App.tsx:6` builds
  `new QueryClient({…})` with **no MutationCache** ⇒ **every failed mutation in the entire frontend is
  silent, forever** — the button just re-enables. That is why three live bugs survived to an audit.
- **D-4 · The content-language SSOT is `contracts/languages.contract.json`** (mirroring
  `frontend-tools.contract.json`, the proven cross-language-SSOT shape in this repo). ⚠ It must NOT be
  called `languages.yaml` — `contracts/language-rule.yaml` already exists and means *service →
  programming language*. Different axis; one name for two concepts is the drift this repo legislates
  against.
- **D-5 · Mobile shell — DECIDE AT WAVE 6's CLOSE.** Until then **GG-4 stays SHUT**: Wave 6 ships the
  mechanical parity guard, **not** the deletion of `ChapterEditorPage`.
- **D-6 · `D-COMPOSE-GENERATE-UNGATED` — CARRY IT; raise at Wave 3/3c.** Pre-existing, not a regression
  of this batch, and the user does get what they pay for. ⚠ When fixed, it must be fixed **AT THE ROUTE**,
  never by gating the Regenerate button alone (that would mint a second confirmation convention, and
  **AN-8 seals one-channel-per-object-class**).
- **D-7 · ADD A `place-graph` SLICE TO WAVE 8.** The legacy `WorldMap.tsx` place-graph was a CIRCULAR
  DEFER (spec 38 said "it belongs to Wave 6"; Wave 6 never contained it) ⇒ no wave built it ⇒ it would
  have died at the GG-4 gate. ⚠ It is **NOT** Wave 8's `world-map` panel: that reads book-service's
  `world_maps`/`map_markers`/`map_regions`; the legacy `useWorldMap` reads `work.settings.world_map`.
  Plan 30 §10 explicitly refutes conflating them. Leaf-reuse `WorldMap.tsx`.

### 🔴 D-1 is **THE ONE CRITICAL-CLASS STOP IN THE ENTIRE BUILD** — and it is **NOT Wave 0's**

The language rekey is **DESTRUCTIVE** (a 3-table rekey under a live UNIQUE constraint). Per §0.3 it is the
**stop-and-ask** class, and the PO has already ruled on the shape of the stop:

> **produce a DRY-RUN for PO review — migration + rollback path + before/after row-count assertion —
> and DO NOT EXECUTE IT UNATTENDED.**

**Wave 0 does not run it.** Wave 0's only obligation is to **not pretend it is routine**: when the rekey's
wave arrives, the run **pauses at the dry-run and waits for a human.** Every other blocker in this batch
is still a defer-row-and-keep-going (§0.3) — **this one is not.**

### What D-2 / D-3 do to THIS plan

| Decision | Effect on Wave 0 |
|---|---|
| **D-2** | 🆕 slice **`W0-S15`** — the Translate dropped-selection fix. 🔴 **Wave T's `T-A4` (gap `T8`) is DISCHARGED HERE — its SELECTION half only.** `T-A4`'s `preselectedLang`/**D6** half, the per-cell language hand-off, and the fully-translated-book dead end **stay in Wave T**. It must not be built twice, and it must not be dropped. |
| **D-3** | 🆕 slice **`W0-S16`** — the global `MutationCache.onError`. **The highest leverage-per-line item in the whole build.** |
| **D-4** | No Wave-0 code. Recorded so the name is not invented twice: the content-language SSOT is **`contracts/languages.contract.json`**, *never* `languages.yaml`. |
| **D-5** | **`W0-S12`'s GG-4 gate stays SHUT** — it is a *machine-checked ledger*, not a deletion trigger. This is already how S12 is written; D-5 seals it. |
| **D-6** | `D-COMPOSE-GENERATE-UNGATED` **stays a carried row** (§8). `W0-S7` **must not** gate the Regenerate button on cost (§10 #10 already says this — D-6 seals it, and adds: **fix it AT THE ROUTE**, Wave 3/3c). |
| **D-7** | 🔴 **SEALS the `worldmap` row of `W0-S12`'s LEGACY_SUBTAB_HOME ledger.** That row said *"pick ONE: (i) home it in Wave 8 as `place-graph` … or (ii) get a PO adjudication that book-service's world-map supersedes it."* **The PO picked (i).** So the ledger's `place-graph` → **WAVE 8** row is now **sealed, not proposed**, Wave 8's delta stays **+2 → +6**, and 🔴 **`place-graph` is NOT Wave 8's `world-map` panel** (different service, different data — plan 30 §10). **Leaf-reuse `WorldMap.tsx`.** Wave 0 writes the ledger row; **Wave 8 builds the slice.** |

---

## 0 · The policy this plan is written under (binding — quoted verbatim from the PO)

1. **This plan is written ONCE, in full, at BUILD DETAIL.** After the QC gate, implementation
   proceeds **autonomously with no further design checkpoints.** So anything left vague becomes a
   stall or a guess at 3am. A slice that says "wire the panel" is a FAILURE; a slice says WHICH FILE,
   WHAT CHANGE, WHICH TEST.
2. **`/review-impl` runs at the completion of EVERY wave**, and any bug it finds is fixed before the
   wave closes. It is a literal step in the DoD (§8).
3. **DEFERRAL POLICY — "blocked ≠ stopped".** On a blocker: write a tracked defer row and **KEEP
   GOING**. Do **not** stop, do **not** ask. A blocker is a DEFER by default. **Stop and ask ONLY for
   a CRITICAL blocker**, defined narrowly as exactly one of:
   - a destructive / irreversible action (data loss; a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (§0 PO-1..4 of plan 30),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing.**
   Everything else — a missing route, an awkward refactor, a failing third-party thing, an ugly seam
   — is a **defer row + continue**.
4. Every defer row carries: ID, wave/slice of origin, what, the gate reason (CLAUDE.md's 5 gates),
   target wave/trigger. A defer row is never a silent drop.
5. **CLAUDE.md's anti-laziness rule is in force:** *"missing infrastructure is NOT blocked — it is
   unbuilt work to implement."* A route that does not exist is a route you **WRITE**.

> 🔴🔴 **THE ADJUDICATION REGISTER EXISTS AND IT OUTRANKS THIS PLAN.**
> [`docs/plans/studio-adjudication/wave-0-decisions.md`](studio-adjudication/wave-0-decisions.md) —
> **90 items · 81 DECIDED · 5 not-a-question · 4 deferred.** It was recovered from the journal AFTER
> this plan's first cut was written, so **the first cut was written blind.** Its own header is binding:
> *"These are INSTRUCTIONS, not suggestions. Each was settled by reading source. Do not re-open a
> decided question. **Where this contradicts the wave plan, this file wins.**"*
>
> **This revision folds it in.** Every slice below now carries the decision that governs it, named by its
> `Q-30-*` id. **READ THE DECISION BEFORE YOU BUILD THE SLICE** — the plan text is a summary; the
> decision carries the file:line evidence and the veto-able defaults.
>
> **THE THREE PLACES THE PLAN WON ANYWAY** — each because the *code* refuted the decision, which is the
> decisions file's own standard of proof. They are written up in §10 (AUDIT CORRECTIONS #6-#8) with the
> verifying command. **Do not silently re-flip them; re-run the command.**
>
> Plan 30 §0 (PO-1..PO-4) remains the sealed decision source and is **not** re-litigated.

---

## 1 · Header — what this wave is, and what it gates

**Nothing in this wave is a feature. Every item is a landmine on the critical path of the other 8
waves.** Wave 0 ships **zero new panels** — so the GG-8 per-panel registration checklist (plan 30 §8)
is **N/A for this wave except the guards it STRENGTHENS (X-2, X-3)**, and the panel enum ends the wave
at **`N_before + 0`** (§6). ⚠ **`N_before` is MEASURED at pre-flight, never copied** — no DoD, test, or
spec in this batch may assert a **literal** panel count (decision `Q-30-ENUM-COUNT-BASELINE`; the repo
already deleted a hand-copied enum list once, `test_frontend_tools.py:153-162` is its tombstone).

### Gaps closed

| Item | What | Slice |
|---|---|---|
| **X-1** | `AddModelCta` DOCK-7 — a raw `<Link>` in a shared component tears down the whole dockview | `W0-S3` |
| **X-2** | `CATEGORY_ORDER` missing `'quality'` (`indexOf → -1` ⇒ sorts FIRST) + the **missing group LABEL** + 2 machine guards | `W0-S1` |
| **X-3** | `guideBodyKey` unguarded — and **4 shipped panels already render a BLANK guide body** | `W0-S2` |
| **X-4** | Lane-B effect registry: kill the string branch · the **false comment** · the one stale domain · the coverage ledger | `W0-S4` |
| **X-5** | RETIRE `ui_show_panel` (PO-3); `ui_watch_job` → studio-intercepted `job-detail` | `W0-S5` |
| **X-6** | Write spec 28's **AN-12.1 `resource_ref`** section (contract only; build lands Wave 2) | `W0-S8` |
| **X-7** | `gather_motif` packer lens + a BA12-style **effect** test — 🔴 **the HARD GATE on Wave 3** | `W0-S6` |
| **X-8** | Doc hygiene (14a/14b, 15a/15b, stale headers, the 5th destructive-token drift) | `W0-S10` |
| **X-9** | The 2 MCP sweeps — **CLOSED IN THE DECISION**; Wave 0 *applies* the result + 2 code fixes | `W0-S9` |
| **X-10** | AN-C2 — the discovery scent in `book_context_note` | `W0-S11` |
| **X-11** | The dangling `see X-11` ref (it is **BE-11**) + **BUILD BE-11** (canon-rule restore) | `W0-S10` + `W0-BE2` |
| **X-12** | 🆕 `ui_open_studio_panel` gains an **OPTIONAL `params`** object — sealed PO-3 cannot be implemented without it | `W0-S5b` |
| **X-13** | 🆕 DELETE `consumer_capabilities` + `contributeContext` (both dead) — and **fix the silent-success they were nominally defending against** | `W0-S5c` |
| **X-GG4-GATE** | 🆕 The GG-4 legacy-editor retirement gate, as a **machine-checked test** + the LEGACY_SUBTAB_HOME ledger | `W0-S12` |
| **X-DIRTY-CLOSE** | 🆕 Closing a dirty dock tab **silently discards the edit today**. Guard it before any editing panel lands. | `W0-S13` |
| **X-NEW-CHAPTER** | 🆕 The manuscript `+` button is **DEAD** (`StudioSideBar` has no `onNewChapter` prop at all) | `W0-S14` |
| **X-TRANSLATE-SELECTION** | 🆕 **PO `D-2`** — Translate **silently throws the user's ticked chapters away** and substitutes the whole backlog (`TranslateModal` mounted with **no `preselectedChapterIds`**). **A HIGH bug, damaging data TODAY.** Discharges the **selection half** of Wave T's `T-A4`/`T8` (the D6 language half stays in Wave T). | `W0-S15` |
| **X-SILENT-MUTATION** | 🆕 **PO `D-3`** — `QueryClient` has **no `MutationCache`** ⇒ **every failed mutation in the entire FE is SILENT.** *This is why three live bugs survived to an audit.* | `W0-S16` |
| **The motif-mine 500** | 🔴 `/actions/confirm` **500s BEFORE the enqueue** (the job row is **never written**) + 3 FE-invented conformance/regenerate URLs. ⚠ **NOT a "404 at the poll", and NO USER WAS EVER CHARGED** — see `W0-BE1`. | `W0-BE1` + `W0-S7` |
| **Contract-first** | 🆕 **Both new REST routes go into `contracts/api/composition/v1/openapi.yaml` BEFORE any FE consumes them** | `W0-C1` |

### Hard gates — what must be green BEFORE this wave starts

None. **Wave 0 is the root of the dependency graph.** Its only external constraint was Track C's
mid-edit `stream_service.py` (plan 30 §9) — see the pre-flight, that gate is now **verified clear**.

### What this wave unblocks

```
Wave 0 ──┬─▶ Wave 1 (quality)      X-2 is a HARD GATE (4 quality panels sort wrong without it)
         ├─▶ Wave 2 (arc inspector) consumes X-6 (resource_ref)
         ├─▶ Wave 3 (motif cluster) X-7 is a HARD GATE — without it the wave ships decoration
         ├─▶ Wave 4/5/6/7/8         all consume X-1 (every ModelPicker empty state) + X-4 + X-5
         └─▶ Wave 7                 consumes X-6
```

---

## 2 · Pre-flight — run these EXACTLY. Paste the output. Do not proceed on a claim.

> **STEP 0 — READ `docs/plans/studio-adjudication/wave-0-decisions.md` END TO END.** It is 90 adjudicated
> decisions and **it outranks this plan.** Each slice below names the `Q-30-*` id that governs it; open
> that decision before you touch its files. It carries the file:line evidence, the exact code, and the
> PO-veto-able defaults this summary compresses away.

```bash
cd /d/Works/source/lore-weave-mvp

# 1. The X-7 gate (this MUST be EMPTY now, and NON-empty when W0-S6 lands).
grep -rn "motif" services/composition-service/app/packer/*.py ; echo "exit=$?"   # expect: no output, exit=1

# 1b. 🔴 THE THREE CODE FACTS ON WHICH THIS PLAN OVERRIDES A DECISION (§10 #6/#7/#8).
#     If ANY of these now prints the opposite of the stated expectation, the decision was right after
#     all and the plan is stale — follow the DECISION and note it in the drift register.
grep -n "project_id         UUID NOT NULL\|book_id            UUID NOT NULL" \
     services/composition-service/app/db/migrate.py     # expect: BOTH present ⇒ BE-7c NEEDS the DDL (#6)
grep -n 'scope != "arc"' services/composition-service/app/engine/motif_conformance_run.py
                                                        # expect: 1 hit ⇒ chapter conformance CANNOT be a paid run (#7)
grep -c "structure_repo=" services/composition-service/app/routers/engine.py \
                          services/composition-service/app/routers/grounding.py
                                                        # expect: engine.py 3, grounding.py 1 ⇒ FOUR pack() call sites (#8)

# 2. The X-2 drift (9 listed vs 10 defined).
sed -n '20,22p' frontend/src/features/studio/palette/useStudioCommands.ts

# 3. The enum baseline — RECORD `N_before`. Do NOT assert a literal anywhere (Q-30-ENUM-COUNT-BASELINE).
#    The three numbers MUST be EQUAL to each other. Wave 0 ends at N_before + 0.
python - <<'PY'
import json, re
c = json.load(open('contracts/frontend-tools.contract.json', encoding='utf-8'))
print('contract enum:', len(c['ui_open_studio_panel']['args']['panel_id']['enum']))
s = open('frontend/src/features/studio/panels/catalog.ts', encoding='utf-8').read()
rows = re.findall(r'\{ id: .([a-z0-9-]+).,([^\n]*)\}', s)
openable = [i for i, r in rows if 'hiddenFromPalette: true' not in r]
print('catalog rows:', len(rows), 'openable:', len(openable))
PY

# 4. 🔴 THE TRACK-C GATE for X-10 (plan 30 §9 says stream_service.py is "uncommitted, mid-edit RIGHT NOW").
#    VERIFIED CLEAR at plan time — re-verify at build time. If ANY of these print, X-10 (W0-S11) DEFERS.
git status --short services/chat-service/app/services/stream_service.py \
                   frontend/src/features/chat/components/ToolApprovalCard.tsx \
                   frontend/src/features/chat/hooks/useChatMessages.ts \
                   services/chat-service/app/routers/tool_permissions.py
# expect: NO OUTPUT (clean).  Plan-time result: clean — Track C landed. X-10 is UNBLOCKED.

# 5. Baseline test counts — RECORD THESE. Every DoD below asserts "≥ baseline, 0 failed",
#    never a literal (a hardcoded count rots; see memory `test-budget-constants-drift`).
cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup 2>&1 | tail -3
cd ../chat-service && python -m pytest tests -q -n auto --dist loadgroup 2>&1 | tail -3
cd ../../frontend && npx vitest run 2>&1 | tail -5
```

```bash
# 6. 🆕 THE PO'S TWO HOTFIX FACTS (D-2 / D-3). Both must still be TRUE, or the slice is stale.
#    (Line numbers drift; these greps do not.)

# D-2 (W0-S15): the matrix's TranslateModal mount must have NO preselectedChapterIds.
grep -n -A5 "<TranslateModal" frontend/src/pages/book-tabs/TranslationTab.tsx
# expect: open / onClose / bookId / onJobCreated — and NOTHING else.  If it already passes
# preselectedChapterIds, another track fixed it: mark W0-S15 VERIFY-ONLY and log the drift.

# D-3 (W0-S16): the app QueryClient must have NO MutationCache.
grep -rn "MutationCache" frontend/src --include=*.ts --include=*.tsx
# expect: ONE hit, and it is a COMMENT (useRunBenchmark.ts:41). Zero real handlers.
# RECORD the scale (do NOT copy the plan-time numbers — measure):
grep -rn "useMutation(" frontend/src --include=*.ts --include=*.tsx | wc -l   # plan-time: 142
grep -rn "onError:"     frontend/src --include=*.ts --include=*.tsx | wc -l   # plan-time:  98
#   The two counts are a SIGNAL, not an exact subtraction (some `onError:` sites are on queries,
#   not mutations). The load-bearing fact is binary and needs no arithmetic: THERE IS NO GLOBAL
#   DEFAULT, so EVERY mutation without its own onError fails silently. Do not publish a derived
#   "N silent mutations" number you did not actually enumerate.
```

> ⚠ **`git commit -- <path>` commits the WORKING TREE, not the index** (memory:
> `git-commit-pathspec-reads-working-tree-not-index`), and **the index may already carry another
> session's staged changes** (`git-index-may-carry-prestaged-unrelated-changes`). Three tracks share
> this checkout. **Run `git diff --cached --name-only` before every commit. NEVER `git add -A`.**

---

## 3 · Backend prerequisites — as slices, FIRST

### `W0-BE1` — BE-7c · a Work-LESS job, CREATABLE then READABLE (**kills the paid-action defect**)

> ⚖ **DECISION: `Q-30-404-MOTIF-MINE-POLL`** (read it — it owns the MCP + FE halves of this slice
> verbatim). ⚠ **§10 AUDIT CORRECTION #6 — the plan overrides ONE clause of it.**

> 🔴 **This is the PO's own CRITICAL class: "a paid-action defect."** It fires **today**, on the live
> legacy page: **⛏ Mine is 100% DEAD — `POST /actions/confirm` returns a hard 500 and the confirm token is
> burned (a retry gets 409).** Plan 30 and the decision both scheduled it for Wave 3a. **This plan pulls
> the WHOLE of BE-7c into Wave 0** because (a) it is live and the feature cannot work at all, and (b)
> `W0-S7` cannot fix the FE poll — **or run its live smoke** — without it. Wave 3 / `3a-1` then
> **verifies** it and only builds it if this slice somehow did not land.

> ✅ **CORRECTION — SEALED. NO USER WAS EVER CHARGED, AND THIS IS *NOT* A 404 AT THE POLL.**
> **Three documents get this wrong** (plan 30 §3.3 is the worst: *"the user pays for the LLM run and
> watches a spinner forever"*). **They are wrong in the user's favour, and the story must not be repeated
> anywhere** — a reader who believes it will build the wrong fix. The truth, **live-reproduced inside the
> container**: the 500 happens **at confirm, BEFORE the enqueue**. **No job row. No Redis `XADD`. No
> worker. No LLM call. No spend booked.** The poll is **never reached** — so **an owner-scoped job-read
> route CANNOT FIX THIS**: it would read a row that does not exist, **and it would SHIP GREEN** (its test
> would seed the job row directly). That is this repo's own `fixtures-can-seed-a-field-the-writer-never-sets`
> bug class, about to be committed **on purpose**. 🔴 **THE WRITER IS THE FIX.** *(A billing hold may be
> reserved by `_precheck_or_402` before the raise; that is a **hold**, not a charge — do not upgrade it
> into "the user paid" when you write this up.)*

> 🔴🔴 **AUDIT CORRECTION #0 / #6 — THE READ ROUTE ALONE FIXES NOTHING, AND "ZERO MIGRATION" IS WRONG.**
> `Q-30-404-MOTIF-MINE-POLL` says *"Zero migration needed (`created_by` already exists)"* and specs only
> the read route. **The code refutes that one clause** (re-verify with pre-flight 1b):
> `migrate.py:268-269` — `project_id UUID NOT NULL, book_id UUID NOT NULL` — and
> `generation_jobs.py:159-173` inserts via `INSERT … SELECT $1,$2,w.book_id,… FROM composition_work w
> WHERE w.project_id = $2`. A **synthetic** `project_id` matches **no row** ⇒ zero rows inserted ⇒
> `:198-206` raises **`ReferenceViolationError("project … has no composition_work row")`**.
> **⇒ The job row is NEVER CREATED.** A read route over a row that can never be written 404s forever —
> and its integration test goes green because the fixture raw-`INSERT`s a shape **the producer can never
> produce** (memory: `fixtures-can-seed-a-field-the-writer-never-sets`).
> **BUILD THE WRITER TOO. Everything ELSE in `Q-30-404-MOTIF-MINE-POLL` is adopted verbatim.**

**The bug, traced end to end (every line verified against HEAD `9262ed53e`):**

1. `services/composition-service/app/routers/actions.py:644` `_execute_motif_mine` enqueues with
   `project_id=None` (a book/corpus mine is not Work-bound). Same at `:694` `_execute_arc_import` (拆文).
2. `actions.py:552` `_enqueue_motif_job` → `pid = project_id if project_id is not None else uuid4()`
   — **a synthetic `project_id` with no `composition_work` row.**
3. `GenerationJobsRepo.create()` (`generation_jobs.py:159-173`) inserts via
   `INSERT INTO generation_job … SELECT $1, $2, w.book_id, … FROM composition_work w WHERE w.project_id = $2 …`
   — because `generation_job.book_id` is **`UUID NOT NULL`** (`migrate.py:269`) and is **derived from
   `composition_work` inside the statement**. A synthetic `project_id` matches **no row** ⇒ the INSERT
   inserts **zero rows** ⇒ `row is None` ⇒ `:198-206` raises
   **`ReferenceViolationError("project … has no composition_work row")`**.
4. That is **uncaught** ⇒ **`POST /actions/confirm` 500s** — *after* `_claim_or_replay` **burnt the
   confirm token** and `_precheck_or_402` **reserved the billing hold**.

**⇒ There is no `job_id`, no job row, and nothing to poll — the call dies with a 500 at CONFIRM, before
any work (or any spend) is ever started.**
**Re-pointing the poll (`W0-S7`) fixes NOTHING on its own** — and neither does the read route. The table
must be able to say "this job is owner-scoped, not Work-scoped", **and the WRITER must be able to write
such a row.**

**Why a synthetic `project_id` can never work / why not resolve the book's Work:** a mine is *genuinely*
not Work-bound, and the GUI offers **corpus** scope as a first-class, always-enabled radio
(`MotifMinePanel.tsx:65-71`; `useMotifMine.ts:15` defaults to `'corpus'` when there is no `bookId`), so a
book-only fix leaves the default path broken. **Never back-fill a phantom `composition_work` per mine.**

#### Files

> 📖 **The full build detail for parts (a)–(d) is written ONCE, verbatim, in
> `docs/plans/2026-07-13-studio-wave-3-motif.md` → slice `3a-1` (§ "Files" (a)–(d)) — the DDL text, the
> `create_unbound()` body, the `GenerationJob` model change and the `_enqueue_motif_job` branch.
> **BUILD IT FROM THERE. Do not re-derive it and do not fork a second version.**

| # | File | Change |
|---|---|---|
| **a** | `services/composition-service/app/db/migrate.py` | **DDL (additive)** — `ALTER TABLE generation_job ALTER COLUMN project_id DROP NOT NULL;` + same for `book_id`; the `generation_job_scope_shape` **both-or-neither CHECK**; the partial index `idx_generation_job_owner_unbound`. **Verbatim from `3a-1` (a).** |
| **b** | `services/composition-service/app/db/repositories/generation_jobs.py` | **NEW `create_unbound()`** + `UNBOUND_OPERATIONS = frozenset({"mine_motifs", "analyze_reference"})`. **Do NOT touch `create()`** — it is the hot path for every draft. **Verbatim from `3a-1` (b).** |
| **c** | `services/composition-service/app/db/models.py` | `GenerationJob.project_id` / `.book_id` → `UUID \| None = None`. **From `3a-1` (c).** |
| **d** | `services/composition-service/app/routers/actions.py` | `_enqueue_motif_job` (`:534`) — **delete the `uuid4()` synthetic pid**; branch to `create_unbound()` when `project_id is None`. **From `3a-1` (d).** |
| **e** | `services/composition-service/app/routers/engine.py` | **CREATE** the read route (below). Put it directly beneath `get_job` (`:1415`) so the two gates are read side by side. |
| **f** | `services/composition-service/app/mcp/server.py` | `composition_get_mine_job` — **drop the un-knowable `project_id` arg**; gate on `created_by` instead. |
| **g** | `services/composition-service/tests/integration/db/test_motif_job_read.py` | **CREATE** (real DB). |

> **Migration safety (CLAUDE.md's traps, checked — full review in `3a-1`):** no new column ⇒ *"ADD COLUMN
> never revisits a bad default"* is **N/A**. The CHECK constrains **shape**, not an operation enum ⇒ the
> *"backfill ALL historical CHECK blocks"* trap is **deliberately avoided** (the op allowlist lives in the
> **writer**, where it evolves without DDL). The index is **non-unique** ⇒ no tombstone/`ON CONFLICT`
> hazard. Every existing row has both keys non-null ⇒ the CHECK **validates clean**; `DROP NOT NULL`
> **rewrites nothing**. ✅ **Additive and reversible — NOT the destructive stop-and-ask class.**

#### Route contract

```
GET /v1/composition/motif-jobs/{job_id}
  auth:     the normal user JWT (get_current_user)
  gate:     job.created_by == user_id            ← the OWNER gate. NOT _gate_work.
  200:      the same body as GET /jobs/{job_id}  → job.model_dump(mode="json")
  404:      job is None  OR  job.created_by != user_id
            → the SAME uniform detail string for both ("job not found").
              H13: denial and missing MUST be indistinguishable — no enumeration oracle.
  no other codes.
```

```python
# services/composition-service/app/routers/engine.py — directly below get_job (:1428)

@router.get("/motif-jobs/{job_id}")
async def get_motif_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> dict[str, Any]:
    """BE-7c — the OWNER-scoped job read.

    `GET /jobs/{job_id}` gates on the job's project→book grant (`_gate_work`). That is
    correct for Work-bound jobs and IMPOSSIBLE for the ones that aren't: a book/corpus
    motif-mine and an arc-import are enqueued with `project_id=None`, so the row
    carries NO composition_work and `_gate_work` can never grant on it. This route
    gates on the actor stamp the row DOES carry (`created_by`) instead.

    ⚠ Read this WITH create_unbound(): before that landed, `_enqueue_motif_job`
    stamped a SYNTHETIC uuid4() and create()'s `INSERT … SELECT … FROM composition_work`
    matched zero rows ⇒ ReferenceViolationError ⇒ POST /actions/confirm 500'd at CONFIRM,
    BEFORE the enqueue. So the row was never written and this route would have 404'd
    forever. THE WRITER IS THE FIX; this route is only its read half.

    ⚠ NEVER "fix" this by back-filling a synthetic project_id into a Work — that would
    mint a phantom Work row per mine. The job is genuinely user-scoped, not Work-scoped.
    ⚠ Missing and denied return the SAME 404 (H13 — no enumeration oracle).
    """
    job = await jobs.get(job_id)
    if job is None or job.created_by != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump(mode="json")
```

**MCP half** (`Q-30-404-MOTIF-MINE-POLL` §2 — `services/composition-service/app/mcp/server.py:3205-3221`).
`composition_get_mine_job` today demands a `project_id` the caller can never know (the confirm response
names this tool in its own `poll` field — a tool that **cannot be called**). Exactly:

- **Drop the `project_id` parameter entirely.** Remove `_book_or_deny` and the `job.project_id != pid`
  assertion; replace with `if job is None or job.created_by != tc.user_id: raise uniform_not_accessible()`.
- **`require_meta("R", "book", …)` → `require_meta("R", "user", …)`** — the pattern `composition_motif_search`
  already uses (`server.py:2083`). Keep the name, tier R, and synonyms.
- Update the tool description: *"VIEW on the book required"* → *"Your own job only."*
- Update the composition row in `docs/specs/2026-06-26-public-mcp/05-tool-scope-map.md:35` if it records a scope.
- **This is a 3-schema-source FastMCP change** (memory: `knowledge-mcp-three-schema-sources-fastmcp-strips`)
  — the Pydantic args model, the `@mcp_server.tool` registration, **and** any inline JSON-schema dict.
  `grep -n "get_mine_job" services/composition-service/app/mcp/server.py` and fix **every** hit.
- **MCP test** (`tests/unit/test_motif_mcp.py`): replace `test_get_mine_job_foreign_project_uniform`
  with `test_get_mine_job_foreign_owner_uniform`; add a happy path passing **only** `job_id`.

**FE half** (`Q-30-404-MOTIF-MINE-POLL` §3 — belongs to `W0-S7`, listed here so the route's consumers are
in one place). Add `getMotifJob(jobId, token)` to `frontend/src/features/composition/api.ts` next to
`getJob` (`:420`), then re-point **THREE** Tier-W polls in `frontend/src/features/composition/motif/api.ts`
off `compositionApi.getJob`: **`mineConfirm` (`:172`,`:175`) · `arcConformanceRunConfirm` (`:286`,`:289`) ·
`_resolveActionJob` (`:335`,`:338`)**. All three poll a job **the caller itself just confirmed**, so
`created_by == caller` always holds. **Leave `compositionApi.getJob` in place** for the engine/critic jobs
(`CriticPanel.tsx:35`, `api.ts:59`). ⚠ **On 404 the panel renders an ERROR, never a spinner** (spec 34
AT-11) — a spinner-until-timeout is the papering-over this whole slice exists to kill.

#### Tests — TDD order (failing test FIRST)

`services/composition-service/tests/integration/db/test_motif_job_read.py` (**real DB**):

```python
pytestmark = [
    pytest.mark.skipif(not os.environ.get("TEST_COMPOSITION_DB_URL"),
                       reason="set TEST_COMPOSITION_DB_URL to a throwaway DB"),
    pytest.mark.xdist_group("pg"),   # MANDATORY — a real-DB test on a shared PG.
]
```

> 🔴 **THE FIXTURE MUST GO THROUGH THE PRODUCER.** Do **not** raw-`INSERT` the job row. A raw insert
> seeds a shape the writer can never emit, and the suite then goes green over a live-broken path
> (`fixtures-can-seed-a-field-the-writer-never-sets`). **Every row below is created by
> `create_unbound()`** — the same call `_enqueue_motif_job` makes.

| Test name | Asserts |
|---|---|
| 🔴 `test_an_unbound_job_can_be_CREATED_at_all` | `create_unbound(created_by=U, operation="mine_motifs")` returns a job with `project_id is None` and `book_id is None`. **REDS AT HEAD** — today the only writer is `create()`, which raises `ReferenceViolationError`. **This is the actual paid-action bug.** |
| `test_create_unbound_rejects_a_work_bound_operation` | `create_unbound(operation="draft_scene")` raises `ValueError` — a Work-bound op must never silently lose its tenancy keys. |
| `test_the_scope_shape_check_rejects_a_half_null_row` | A raw `INSERT` with `project_id` set and `book_id` NULL violates `generation_job_scope_shape`. **The tenancy-hole lock.** |
| `test_synthetic_project_job_is_readable_by_its_owner` | The row from `create_unbound()`, `GET /motif-jobs/{id}` as U → **200**, body has `status`. |
| `test_other_user_gets_404_not_403` | Same row, called as V → **404**, `detail == "job not found"` — byte-identical to the missing-row 404. |
| `test_missing_job_is_404` | Random UUID → 404, same detail. |
| `test_the_old_route_still_404s_on_an_unbound_job` | `GET /jobs/{id}` on the same row still 404s. **Proves we did not weaken the Work-scoped gate** — the new route is additive, not a loosening. |
| 🔴 `test_the_confirm_path_no_longer_500s` | Drive `_enqueue_motif_job(project_id=None, operation="mine_motifs")` → it returns a real `job_id` and **does not raise**. **REDS AT HEAD** (`ReferenceViolationError`). **This is the leg `W0-S7`'s live smoke depends on.** |

**DoD evidence:** `"pytest -q tests/integration/db/test_motif_job_read.py -n auto --dist loadgroup → 8 passed"` **+ the pasted output**, with `test_an_unbound_job_can_be_CREATED_at_all` and `test_the_confirm_path_no_longer_500s` **observed RED before the change and GREEN after (both runs pasted)**. Plus the full composition suite green at `<baseline>+8`.
**dependsOn:** —
**⚠ `W0-S7` HARD-DEPENDS ON THIS SLICE.** Until (a)–(d) land, `/actions/confirm` 500s and there is no
job to poll — so `W0-S7`'s live smoke **cannot pass**. Build `W0-BE1` first, in full.

---

### `W0-BE2` — BE-11 · `canon_rule` **restore** (the undo the DELETE already promises)

> ⚖ **DECISION: `Q-30-X11-DANGLING-REF`.** Two halves: the doc fix (`see X-11` → `see BE-11`) rides
> `W0-S10`; **the route is built HERE.** It is `archive()`'s exact inverse, XS, and it is Wave 1's
> declared BE prereq for G-CANON-RULE-CRUD — so it lands in the backend-prereq wave, not in Wave 1's
> feature diff.

#### Files

| File | Change |
|---|---|
| `services/composition-service/app/db/repositories/canon_rules.py` | **NEW `async def restore(self, project_id, rule_id) -> CanonRule \| None`**, immediately after `archive()` (ends `:166`). Body = archive's inverse: `UPDATE canon_rule SET is_archived = false, updated_at = now() WHERE project_id = $1 AND id = $2 AND is_archived RETURNING {_SELECT_COLS}`; `return _row_to_rule(row) if row else None`. 🔴 **It must NOT bump `version` and must NOT touch `active`** — restore un-archives *only*; a rule that was `active=false` when deleted comes back **inactive**. `canon_rule` has no parent/child tree ⇒ **no cascade** (unlike `outline.restore_node`'s two recursive walks). |
| `services/composition-service/app/routers/canon.py` | **NEW `@router.post("/canon-rules/{rule_id}/restore", status_code=200)`**, right after the DELETE handler (`:175`). Copy the DELETE body 1:1: resolve scope **from the ROW** via the existing `_rule_project_id(rule_id)` helper (`:95-105` — the by-id routes carry no project in the path), then `await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)`, then `rule = await canon.restore(project_id, rule_id)`; `if rule is None: raise HTTPException(404, detail="canon rule not found or not archived")`; return `rule.model_dump(mode="json")`. **No If-Match / OCC** — the sibling restores (`outline.py:648`, `arc.py:528`) take none, and an archived row has no concurrent editor to race. |

**Do NOT build:** an `include_archived` list param, an archived-rules browser, or a
`composition_canon_rule_restore` **MCP tool.** Reachability is an **undo TOAST**: `DELETE /canon-rules/{rule_id}`
already returns the archived row (id included), so the FE holds the id and renders *"Rule deleted · Undo"* →
`POST …/restore`. §5.1's tool column for G-CANON-RULE-CRUD lists create/update/delete/list only — **restore is
a human undo affordance, not an agent action.** Adding any of the above pushes BE-11 off XS.

#### Tests

`services/composition-service/tests/unit/test_outline_canon_routers.py` (the existing home for both routers):

| Test | Asserts |
|---|---|
| `test_delete_then_restore_reappears_in_list` | delete → restore → the rule is back in `GET /works/{pid}/canon-rules`. |
| `test_restore_of_a_never_archived_rule_is_404` | 404, detail `"canon rule not found or not archived"`. |
| `test_restore_by_a_view_only_grantee_is_403` | the gate is **EDIT**. |
| `test_restore_does_not_bump_version_and_does_not_flip_active` | 🔴 repo-level. **The two silent-corruption bugs.** |

Plus the repo round-trip in `tests/integration/db/test_repositories.py` beside the existing `restore_node`
coverage (`pytestmark = pytest.mark.xdist_group("pg")` — it is already on that file; **confirm it**).

**DoD evidence:** `"pytest tests/unit/test_outline_canon_routers.py -q → 4 new passed; full composition suite ≥ baseline, 0 failed"` + the pasted output.
**dependsOn:** —

---

## 3.5 · 🔴 `W0-C1` — THE CONTRACT SLICE (**CLAUDE.md: "contract-first — API contract frozen before frontend flow"**)

> 🔴 **This slice was MISSING from the first cut and it is a repo-law violation.** Wave 0 adds **two**
> REST routes and the first cut touched **zero** contract files. **`W0-C1` runs AFTER `W0-BE1`/`W0-BE2`
> land the handlers (so the spec describes what actually exists) and BEFORE `W0-S7` — the FE slice that
> consumes `motif-jobs` — is written.** A contract written after its consumer is not a contract.

**THE FILE — verified, do not guess.** `contracts/api/composition/v1/openapi.yaml`
(**not** `contracts/api/composition-service/plan-forge.v1.yaml`, which is **PlanForge / Wave 5's**;
**not** `contracts/api/book-service/`, which **does not exist** — book-service's spec is
`contracts/api/books/v1/openapi.yaml`). It is live and maintained: `openapi: 3.0.3`,
`servers: [{ url: /v1/composition }]` ⇒ **paths are written RELATIVE to `/v1/composition`**, 17 paths,
and it already carries `/canon-rules/{rule_id}` (`:198`) and `/jobs/{job_id}` (`:273`).

#### Edit 1 — the new engine route (`W0-BE1`). Add **after** `/jobs/{job_id}` (`:279`):

```yaml
  /motif-jobs/{job_id}:
    get:
      tags: [engine]
      summary: OWNER-scoped read of a Work-LESS async job (mine_motifs / analyze_reference)
      description: >
        BE-7c. `GET /jobs/{job_id}` gates on the job's project→book grant, which is correct for
        Work-bound jobs and IMPOSSIBLE for the ones that are not: a book/corpus motif-mine and an
        arc-import are enqueued with project_id=None, so the row carries NO composition_work and the
        Work gate can never grant on it. This route gates on the actor stamp the row DOES carry
        (`created_by`). It is the READ half of BE-7c — the write half (`create_unbound()`) is what
        makes such a row exist at all. Missing and denied return the SAME 404 (H13 — no enumeration
        oracle).
      parameters: [{ name: job_id, in: path, required: true, schema: { type: string, format: uuid } }]
      responses:
        '200': { description: Job, content: { application/json: { schema: { $ref: '#/components/schemas/GenerationJob' } } } }
        '404': { $ref: '#/components/responses/NotFound' }
```

#### Edit 2 — the new canon route (`W0-BE2`). Add **after** `/canon-rules/{rule_id}`'s `delete` (`:217`):

```yaml
  /canon-rules/{rule_id}/restore:
    post:
      tags: [canon]
      summary: Un-archive a soft-deleted canon rule (BE-11 — the undo behind the delete toast)
      description: >
        The exact inverse of DELETE /canon-rules/{rule_id}. Does NOT bump `version` and does NOT
        touch `active` — a rule archived while inactive comes back inactive. EDIT grant, derived
        from the ROW's project (the by-id routes carry no project in the path). No If-Match.
      parameters: [{ name: rule_id, in: path, required: true, schema: { type: string, format: uuid } }]
      responses:
        '200': { description: Restored, content: { application/json: { schema: { $ref: '#/components/schemas/CanonRule' } } } }
        '403': { description: Insufficient grant (EDIT required) }
        '404': { description: Not found, or not archived (uniform — also cross-user) }
```

#### Edit 3 — `GenerationJob` becomes scope-nullable (the DDL in `W0-BE1` makes it so)

`components.schemas.GenerationJob` (`:470`) declares `project_id: { type: string, format: uuid }`.
After `W0-BE1`'s `DROP NOT NULL`, an unbound job returns **`null`**. A contract that says otherwise is a
lie the FE will trust. Change to — and **add the field the schema never had**:

```yaml
        project_id: { type: string, format: uuid, nullable: true }   # null ⇒ an UNBOUND (owner-scoped) job
        book_id:    { type: string, format: uuid, nullable: true }   # null ⇒ ditto; both-or-neither (CHECK generation_job_scope_shape)
```

#### Test — the contract is not a document, it is a gate

**CREATE** `services/composition-service/tests/unit/test_openapi_contract_parity.py`:

| Test | Asserts |
|---|---|
| `test_every_declared_path_exists_on_the_app` | Load `contracts/api/composition/v1/openapi.yaml`; for every `path` + `method`, assert a matching route exists on `app.main:app` (prefix `/v1/composition` + the relative path). **REDS if a contract path is fictional.** |
| 🔴 `test_the_two_wave0_routes_are_in_the_contract` | `/motif-jobs/{job_id}` **GET** and `/canon-rules/{rule_id}/restore` **POST** are both present. **This is the contract-first assertion. It REDS at HEAD.** |
| `test_generation_job_scope_keys_are_nullable` | `GenerationJob.project_id.nullable is True` and `book_id` is declared + nullable. **Catches the DDL⇄contract drift the FE would otherwise eat.** |

> ⚠ **Deliberately NOT the reverse assertion** (*"every app route is in the contract"*). 21 shipped
> composition routes have no contract row today (decision `Q-30-22-NOFE-ROUTES-NOT-ENUMERATED` enumerates
> them); a reverse gate would red on 21 pre-existing rows and this wave would spend itself backfilling
> them. **That backfill is Wave 1's `W1-S0` route-coverage register** — the decision assigns it there.
> Wave 0 asserts the *forward* direction (nothing fictional) + its own two rows.

**DoD evidence:** `"pytest tests/unit/test_openapi_contract_parity.py -q → 3 passed"` **+ the pasted output**, with `test_the_two_wave0_routes_are_in_the_contract` **observed RED before the yaml edit and GREEN after (both runs pasted)**.
**dependsOn:** `W0-BE1`, `W0-BE2`.
**🔴 BLOCKS:** `W0-S7` (the FE consumer of `/motif-jobs/{job_id}`).

---

## 4 · The slices. Each slice = ONE COMMIT.

**Wave 0 = 21 slices**: `W0-BE1` · `W0-BE2` · `W0-C1` (backend + contract, §3/§3.5) **+ 18 `W0-S*`**
(`S1`–`S14`, `S5b`, `S5c`, and 🆕 **`S15`** ← PO `D-2`, 🆕 **`S16`** ← PO `D-3`).
*(Was 19 before the 2026-07-13 PO seal. **Zero new panels** — the enum still ends at `N_before + 0`.)*

---

### `W0-S1` — X-2 · `CATEGORY_ORDER` + the group LABEL + two machine guards

**The bug (verified).** `frontend/src/features/studio/palette/useStudioCommands.ts:20-22` lists **9**
categories. `frontend/src/features/studio/panels/catalog.ts:81-91` defines **10** — `'quality'` is
missing from the order array. `CATEGORY_ORDER.indexOf('quality')` → **`-1`** ⇒ the 5 shipped
`quality-*` panels sort **above `editor`** (index 0) in the Command Palette **today**.

> **The failure modes are INVERTED and that is the whole point:** a category *missing from the
> catalog* sorts LAST (harmless). A category *present in the catalog but unlisted in `CATEGORY_ORDER`*
> sorts **FIRST** (loud, wrong). Spec 18's B6 assertion guards that a panel *has* a category —
> **nothing** guards that the category is a **member of `CATEGORY_ORDER`**. Wave 1 adds 3 more
> `quality` panels; Waves 3+ add more. **This is a hard gate on Wave 1.**

> ⚖ **DECISION: `Q-30-X2-CATEGORY-ORDER`** (+ `Q-30-PANEL-REGISTRATION-9-STEPS`). It **overrides this
> plan's first cut on two points and adds a whole second half the plan missed.** Build the decision.

> 🔴 **CONTRADICTION FOLDED — the POSITION. The first cut said *"after `storyBible`, before `knowledge`
> — decided, do not re-open."* THE DECISION SAYS: `'quality'` goes AFTER `'knowledge'`, BEFORE
> `'translation'`** (*"it reads the manuscript, so it groups with the other analysis surfaces"*), and
> `Q-30-PANEL-REGISTRATION-9-STEPS` says the same, independently. **The decision wins. It is settled:
> `… 'knowledge', 'quality', 'translation', …`. Do not re-litigate it in either direction.**

#### 1a — the order + make the drift **UNBUILDABLE** (not merely tested)

`frontend/src/features/studio/palette/useStudioCommands.ts` — **replace lines 20-22 entirely:**

```ts
export const CATEGORY_ORDER = [
  'editor', 'storyBible', 'knowledge', 'quality', 'translation',
  'enrichment', 'sharing', 'platform', 'discovery', 'jobs',
] as const satisfies readonly StudioPanelCategory[];

// X-2 — compile-time exhaustiveness. A new StudioPanelCategory not listed above is now a TYPE ERROR.
// The failure modes are INVERTED: an un-categorized panel sorts LAST (harmless fallback), but an
// UNLISTED category indexOf()s to -1 and sorts FIRST. "Forgot to add it" must be unbuildable.
type _UnorderedCategory = Exclude<StudioPanelCategory, (typeof CATEGORY_ORDER)[number]>;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _CATEGORY_ORDER_IS_EXHAUSTIVE: [_UnorderedCategory] extends [never] ? true : never = true;
```

> 🔴 **THE `as const satisfies` IS LOAD-BEARING, NOT STYLE.** Keeping the old
> `: StudioPanelCategory[]` annotation makes `(typeof CATEGORY_ORDER)[number]` **widen back to the full
> union**, so `Exclude<>` is always `never` and **the guard PASSES WHILE STILL MISSING `'quality'`.**
> Dropping the annotation is what gives the tuple its literal element type. Consumers keep
> typechecking on a readonly tuple (`useStudioCommands.ts:55-56` `.indexOf`/`.length`;
> `UserGuidePanel.tsx:24-25` `.filter`/`.includes`). **Verify with `npx tsc --noEmit` — tsc is what
> proves this guard, not vitest.**

#### 1b — 🔴 **THE SECOND LIVE HALF THE FIRST CUT MISSED: there is no group LABEL either**

`palette.group.quality` **does not exist in ANY locale.** `en/studio.json`'s `palette.group` has 13 keys
(recent, panels, navigate, layout, editor, storyBible, knowledge, translation, enrichment, sharing,
platform, discovery, jobs, help) and **no `quality`** — and `useStudioCommands.ts:60` calls
`group(p.category, p.category)`, so the palette renders a group header of the **raw lowercase string
`"quality"`** next to *"Editor & Chapters"* and *"Story Bible"* **today**. Sorting it correctly and
leaving it mislabeled is a half-fix.

- Add `"quality": "Quality"` to `palette.group` in `frontend/src/i18n/locales/en/studio.json`
  (beside `"knowledge": "Knowledge Graph"`).
- **Propagate to all 17 other locales** (ar bn de es fr hi id ja ko ms pt-BR ru th tr vi zh-CN zh-TW)
  with `python scripts/i18n_translate.py` — **never hand-write.** There is **no studio-namespace parity
  test**, so an en-only add silently English-fallbacks in 17 locales. **Do all 18.**
  ⚠ Read the script's output: a **SOFT** flag does **not** self-heal (memory:
  `i18n-translate-self-heal-only-fires-on-hard-failures`).

#### 1c — the two guards (`panelCatalogContract.test.ts`, after B6 at `:40-43`)

Add `import { CATEGORY_ORDER } from '../../palette/useStudioCommands';` — **no runtime cycle**:
`useStudioCommands.ts:4` imports only *types* from `catalog`, so the edge is erased.
Also export `const ALL_CATEGORIES: StudioPanelCategory[]` from `catalog.ts` next to the union type.

```ts
// X-2 / B7 — B6 asserts a category is PRESENT; nothing asserted it was a MEMBER of CATEGORY_ORDER.
// That guards the harmless half. A panel with no category sorts LAST; a panel whose category is
// unlisted sorts FIRST — which is how 5 shipped `quality` panels ended up above `editor`.
it('every palette-openable panel category is a MEMBER of CATEGORY_ORDER (X-2)', () => {
  const unordered = OPENABLE_STUDIO_PANELS
    .filter((p) => p.category && !CATEGORY_ORDER.includes(p.category))
    .map((p) => `${p.id}:${p.category}`);
  expect(unordered).toEqual([]);
});

// …and catch the drift AT THE TYPE, which is where it was actually introduced.
it('CATEGORY_ORDER and the StudioPanelCategory union are the same set', () => {
  expect([...ALL_CATEGORIES].sort()).toEqual([...CATEGORY_ORDER].sort());
});

// X-2 / 1b's effect: an ordered category with no `palette.group.<cat>` label renders its raw
// lowercase id as the group header. Guard the LABEL set, not just the order.
it('every CATEGORY_ORDER entry has a palette.group i18n label', () => {
  const groups = (JSON.parse(readFileSync(resolve(process.cwd(),
    'src/i18n/locales/en/studio.json'), 'utf-8')) as any).palette.group;
  expect(CATEGORY_ORDER.filter((c) => !groups[c])).toEqual([]);
});
```

(`readFileSync`/`resolve` are already imported at the top of that file; vitest cwd is `frontend/`.)

#### 1d — assert the **EFFECT** (a green type-guard is not a sorted palette)

`frontend/src/features/studio/palette/__tests__/useStudioCommands.test.ts` — **extend the B4 sort test
(`:74`)**: feed it a `category:'quality'` panel **alongside** an `editor` panel **in that order**, and
assert the emitted `studio.openPanel.*` id list puts **`editor` FIRST**. *That is the exact assertion
that would have red-flagged this bug the day the quality tab shipped.*

> ❌ **REJECTED — do not "improve" the fix into this:** moving `CATEGORY_ORDER` into `catalog.ts` to sit
> beside the union. `catalog.ts` imports `UserGuidePanel.tsx`, which imports `CATEGORY_ORDER` from
> `useStudioCommands` — a **value** import back the other way closes a real **runtime cycle**
> (`UserGuidePanel.tsx:12-14`'s own header comment warns about exactly this for `tours.ts`).

**DoD evidence:** `"cd frontend && npx tsc --noEmit && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts src/features/studio/palette/__tests__/useStudioCommands.test.ts → all passed"` **+ the pasted `tsc` line (it is what proves the compile guard)** + a live-browser/DOM assert that the palette shows a group header **"Quality"** (not `quality`) and that it **no longer sorts above `editor`**.
**dependsOn:** —

---

### `W0-S2` — X-3 · `guideBodyKey`: assert the **EFFECT**, not the declaration

> 🔴 **AUDIT CORRECTION #1 — plan 30's proposed assertion would be GREEN on a live bug.**
> Plan 30 X-3 says: *"Extend `panelCatalogContract.test.ts`: `OPENABLE_STUDIO_PANELS.every(p => !!p.guideBodyKey)`."*
> **That assertion passes while the User Guide renders blank.** Verified:
>
> - `agent-mode` (`catalog.ts:258`) declares **no** `guideBodyKey` — the erosion plan 30 found. ✅ caught by the proposed test.
> - **`quality-promises`, `quality-critic`, `quality-coverage`, `quality-canon` all DECLARE a
>   `guideBodyKey` whose i18n key DOES NOT EXIST in `en/studio.json`.** `UserGuidePanel.tsx:120`
>   does `t(p.guideBodyKey ?? p.descKey, { defaultValue: '' })` → **renders an empty string.**
>   **4 shipped panels have a blank User-Guide body, right now.** ❌ the proposed test is GREEN on all four.
>
> This is the repo's own `checklist-is-self-report-enforce-by-tests` memory: *an item is DONE only
> when a test asserts its EFFECT.* **Assert that the key RESOLVES**, not that a string was typed.

> ⚖ **DECISION: `Q-30-X3-GUIDEBODYKEY-UNGUARDED`** (+ `Q-30-PANEL-REGISTRATION-9-STEPS` §3). It **confirms
> the audit correction** and adds the exact form: **TWO assertions, not one** — and it **overrides the
> plan on the locale scope.**

#### Files

| File | Change |
|---|---|
| `frontend/src/features/studio/panels/catalog.ts` | (a) Add `guideBodyKey: 'panels.agent-mode.guideBody'` to the `agent-mode` row (`:258`) — verified the **only** non-hidden panel missing one. (b) 🔴 **Tighten the type** (`:105`): `guideBodyKey?: string` → **`guideBodyKey: string`**, and delete the *"falls back to descKey when absent"* comment. Every openable row already has one after (a) ⇒ **zero row edits**. Fill the `hiddenFromPalette` rows too rather than forking the type. |
| `frontend/src/i18n/locales/en/studio.json` | Add **5** `panels.<id>.guideBody` bodies: `agent-mode`, `quality-promises`, `quality-critic`, `quality-coverage`, `quality-canon`. |
| `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` | The **two** assertions below. |

> 🔴 **CONTRADICTION FOLDED — THE LOCALE SCOPE. The first cut said "the same 5 keys × 17 locales via
> `i18n_translate.py`". THE DECISION SAYS: `en` ONLY.** *"Do NOT touch the other 17 locales —
> `fallbackLng: 'en'` (`i18n/index.ts:48`) covers them; optionally propagate later."* **The decision
> wins: `en/studio.json` is the SSOT and the only file this slice edits.** (Note the asymmetry with
> `W0-S1`'s `palette.group.quality`, which **does** go to all 18 — because there the *English* key is
> the one that never existed, so every locale renders the raw id. Here `vi`/`ja` already **have** the
> copy and **English is the drifted locale**. Different bug, different fix. Do not "unify" them.)

**Guide-body copy** (1–3 sentences each, in the voice of the shipped `panels.quality.guideBody` — read it
first). Write them from what the panel actually does: `agent-mode` = autonomous multi-chapter authoring
runs (start/pause/resume over an approved plan; review each chapter's diff + critic verdict;
accept/reject/revert). `quality-promises` = the open-promise debt ledger. `quality-critic` = per-chapter
coherence/voice/pacing/canon scores. `quality-coverage` = whole-book audit of which outline promises got
paid off. `quality-canon` = book-wide confirmed canon contradictions.

#### Tests — **TWO**, and the second is the one that catches the live bug

Mirror the shape of the existing B6 test (`:38-42`). `readFileSync`/`resolve` are already imported;
vitest cwd is `frontend/`.

```ts
// X-3 — UserGuidePanel renders t(p.guideBodyKey ?? p.descKey, { defaultValue: '' })
// (UserGuidePanel.tsx:120), so a missing KEY **or** missing COPY renders a SILENTLY EMPTY guide row.
// Both halves must be guarded: the declaration assertion alone is GREEN on the live bug (4 quality
// panels DECLARE a guideBodyKey whose en key does not exist).
const enStudio = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/i18n/locales/en/studio.json'), 'utf-8'),
);
const lookupEn = (key: string): unknown =>
  key.split('.').reduce<any>((o, k) => (o == null ? undefined : o[k]), enStudio);

it('every palette-openable panel declares a guideBodyKey (#19 User Guide)', () => {
  const missing = OPENABLE_STUDIO_PANELS.filter((p) => !p.guideBodyKey).map((p) => p.id);
  expect(missing).toEqual([]);
});

it('every guideBodyKey resolves to non-empty English copy (no blank guide row)', () => {
  const empty = OPENABLE_STUDIO_PANELS.filter((p) => {
    const v = p.guideBodyKey ? lookupEn(p.guideBodyKey) : undefined;
    return typeof v !== 'string' || v.trim() === '';
  }).map((p) => p.id);
  expect(empty).toEqual([]);
});
```

**Do NOT** create a studio.json cross-locale parity test — none exists, and the decision puts it out of scope.

> 📌 **THE LINE EVERY LATER WAVE COPIES (put it in each wave's DoD verbatim):** *a new panel lands its
> `guideBodyKey` in `catalog.ts` **AND** its `panels.<id>.guideBody` string in `en/studio.json` **in the
> same slice** — the two tests above red otherwise.*

**DoD evidence:** `"npx vitest run src/features/studio/panels/__tests__/ → all passed (2 new); 5 en guide bodies backfilled; catalog.ts guideBodyKey is now REQUIRED (tsc green)"` + open `user-guide` **in the live browser** and **see the 4 quality bodies render** (they are blank at HEAD).
**dependsOn:** —

---

### `W0-S3` — X-1 · `AddModelCta` DOCK-7, fixed at the **shared component**

**The bug (verified).** `frontend/src/components/shared/AddModelCta.tsx` renders a bare
`<Link to="/settings/providers?return=…">` with **no** `useOptionalStudioHost()` branch. It is
rendered by every `ModelPicker` empty state. Inside a dock panel that `<Link>` **navigates the SPA
away from the studio and unmounts the entire dockview layout** — the user loses their whole workspace.

**Motif Mine, Conformance Run, Arc Import, and every `plan_*` LLM pass are BYOK `model_ref` flows.
They all render a ModelPicker. Without this fix, every panel Waves 1–8 ship contains a button that
destroys the user's workspace.**

> **Fix it ONCE, at the shared component. NEVER at the ~8 call sites.** A per-call-site fix is the
> `css-var-duplicated-across-two-consumers-drifts` class: the 9th call site will forget.

**The precedent is already in the repo** — copy it exactly:
`frontend/src/features/glossary-translate/StepConfig.tsx:41-44` (+ `followStudioLink` from
`@/features/studio/host/studioLinks`), and `frontend/src/features/wiki/components/CreateArticleDialog.tsx:27`.

#### Files

| File | Change |
|---|---|
| `frontend/src/components/shared/AddModelCta.tsx` | Add the studio branch (below). |
| `frontend/src/components/shared/__tests__/AddModelCta.test.tsx` | 2 new tests. |

> ⚖ **DECISION: `Q-30-X1-ADDMODELCTA-DOCK7`.** It confirms the shared-component fix and the ~8
> untouched call sites — **and it overrides the plan's MECHANISM.**

> 🔴 **CONTRADICTION FOLDED — THE MECHANISM. The first cut said: keep the `<Link>`, add
> `onClick={e => { e.preventDefault(); openPanel('settings', {params:{tab:'providers'}}) }}`.
> THE DECISION SAYS: in the studio branch render a `<button>` and call
> `followStudioLink(REGISTRATION_PATH, studioHost, { bookId: studioHost.bookId })`.
> The decision wins, and its grounds are the shipped precedent it points at.** Reasons the plan's
> hand-rolled `openPanel` call is the worse fix: it **re-derives** a mapping
> (`/settings/providers` → `openPanel('settings', {tab:'providers'})`) that **`studioLinks.ts` already
> owns** (`SETTINGS_RE`, `:110-111`) — a second copy of one rule is the
> `css-var-duplicated-across-two-consumers-drifts` class — and a `preventDefault`-ed `<Link>` still
> renders an `<a href>` that a middle-click / ⌘-click **navigates anyway**, tearing the dock down by the
> exact path the fix exists to close.

**The change** — `frontend/src/components/shared/AddModelCta.tsx`. Public props stay **byte-identical**
(8 call sites depend on them). Two imports:

```tsx
import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';
import { followStudioLink } from '@/features/studio/host/studioLinks';
```

Inside the component (which today, at `:33-37`, computes `to = '/settings/providers?return=' + encodeURIComponent(back)`):
`const studioHost = useOptionalStudioHost();` — then **branch BEFORE the two `<Link>` returns**:

- **STUDIO branch (`studioHost !== null`)** — render a `<button type="button">` carrying the **SAME
  `cn(...)` classes** as the corresponding variant (so `variant: 'button' | 'link'` styling is
  preserved), with
  `onClick={() => followStudioLink(REGISTRATION_PATH, studioHost, { bookId: studioHost.bookId })}`.
  🔴 **Pass the BARE `REGISTRATION_PATH` (`/settings/providers`) — NOT `to`. Do not append `?return=`.**
  `resolveStudioLink` **strips the query before matching** (`studioLinks.ts:76`), and `SETTINGS_RE`
  (`:110-111`) resolves `/settings/providers` → `openPanel('settings', { tab: 'providers' })`;
  `SettingsPanel.tsx:35-38` reads `params.tab` and `'providers'` is a valid `SettingsTabId`
  (`features/settings/tabs.ts:26`). **The return-path round-trip is MEANINGLESS in the studio** — the
  dock never navigates away, so there is nothing to come back from.
- **FALLBACK branch (host is `null`)** — keep the **EXISTING `<Link to={to}>` verbatim** for both
  variants, `useLocation()`-derived `?return=` intact (`ProvidersTab.tsx:46` honors it on the classic
  route). `useLocation()` stays safe in the studio (panels mount under `/books/:id/studio`), so it needs
  no guard.

Mirror the DOCK-7 comment style of `StepConfig.tsx:41-44` — **the shipped precedent. Copy it, don't
reinvent it** (`StepConfig.tsx:44` + `:154-163`; second precedent `CreateArticleDialog.tsx:27`).

**Do NOT touch the ~8 call sites** — `ModelPicker.tsx:388`, `CompositionPanel.tsx:514`,
`BuildGraphDialog.tsx:647`, `EmbeddingModelPicker.tsx:97`, `RerankModelPicker.tsx:58`,
`DefaultModelsCard.tsx:50`, + the two picker re-exports. **They inherit the fix. That is the point.**

#### Tests

`frontend/src/components/shared/__tests__/AddModelCta.test.tsx` (today it asserts only the `<Link>` href,
via `screen.getByRole('link')`):

| Test name | Asserts |
|---|---|
| `renders a plain Link outside the studio (no host)` | No `StudioHostProvider`. `getByRole('link')` exists, href `/settings/providers?return=…`. **Existing behavior preserved.** |
| 🔴 `inside the studio it renders a BUTTON, not a link` | Wrap in `<MemoryRouter><StudioHostProvider bookId="b1">…`. **`queryByRole('link')` is NULL** and `getByRole('button')` exists. *(The anchor is what a ⌘-click would navigate.)* |
| 🔴 `clicking it OPENS the settings panel and does NOT navigate` | Click → the host's `openPanel` was called with `('settings', expect.objectContaining({ params: { tab: 'providers' } }))`, and the router did **NOT** navigate. **Verify by EFFECT — assert the PANEL OPENS, not that a button rendered.** |

**DoD evidence:** `"npx vitest run src/components/shared/__tests__/AddModelCta.test.tsx → 3 passed (2 new)"` **+ a LIVE BROWSER smoke:** open a studio panel whose ModelPicker is empty, click **Add a model**, and assert **the dock is still mounted** (another open panel's `data-testid` still in the DOM) **and** the settings panel opened on **Providers**. *A green unit test does not prove the dock survived.*
**dependsOn:** —
**⚠ ORDERING:** this is a **hard gate** — land it **BEFORE any new panel that renders a ModelPicker empty state**, or every such panel ships a layout-nuking link.

---

### `W0-S4` — X-4 · Lane-B: kill the string branch · the false comment · the ONE stale domain · the COVERAGE LEDGER

> 🔴 **AUDIT CORRECTION #2 — "~15 handlers" is not buildable in Wave 0, and plan 30's own §8.0b says so.**
>
> Plan 30 §7 X-4 asks for *"~15 handlers"* now. Plan 30 §8.0b (the **later**, 2026-07-13 cross-spec
> reconciliation) assigns each domain's handler file to the wave that **builds its panel**:
> `compositionEffects.ts` → **Wave 1 creates**; `arcEffects.ts` → **Wave 2 creates**;
> `motifEffects.ts` → Wave 3; `planEffects.ts` → Wave 5; `diagnosticsEffects.ts` → Wave 7;
> `worldEffects.ts` → Wave 8.
>
> **These cannot both be obeyed, and §8.0b is right on the code:** an effect handler's *only* job is
> to invalidate **the query keys of the panel it refreshes**. Those panels — and their query keys —
> **do not exist yet.** A Wave-0 handler for `composition_canon_rule_*` would invalidate *nothing*,
> and if Wave 1 then created `compositionEffects.ts` as §8.0b instructs, **`matchEffectHandlers`
> returns EVERY match and `runEffectHandlers` awaits ALL of them ⇒ DOUBLE-FIRE.**
>
> ⚖ **DECISIONS: `Q-30-X4-LANE-B-HANDLERS` · `Q-30-REGISTEREFFECT-STRING-BRANCH` ·
> `Q-30-EFFECT-HANDLER-DOUBLE-FIRE`.** All three **confirm the audit correction** (Wave 0 ships 4 things,
> not 15 handlers) and then **override the plan's guards with stronger ones.** Wave 0's X-4 is:
> 1. **`4.0` — DELETE the string branch from `registerEffectHandler`** (make the bug *uncompilable*),
> 2. **`4a`** — delete the false comment (×2 files),
> 3. **`4b`** — build the **one** handler whose consumer panel is already shipped and already stale,
> 4. **`4c`** — ship the **coverage ledger** that turns X-4 from a checklist into a mechanical gate.
>
> Waves 1–8 add their own handler file, per §8.0b. **The Wave-0 gate "X-4 green" means: the registry is
> sound, the ledger exists, and no shipped panel is stale.**

#### 4.0 — 🔴 **DELETE the string branch. Do not "guard" it — make it UNCOMPILABLE.** (`Q-30-REGISTEREFFECT-STRING-BRANCH`)

> 🔴 **CONTRADICTION FOLDED. The first cut shipped "Guard 1 — no registered handler uses a string
> pattern containing regex metacharacters" (a TEST over a legal API). THE DECISION SAYS: the string
> branch has ZERO production callers — DELETE IT.** All 4 live registrations already pass a RegExp; the
> only string callers in the repo are **two lines of `effectRegistry.test.ts`.** A test that polices a
> legal API is self-report; a compile error + a throw is the effect. **The decision wins. Build 4.0 —
> and delete the plan's old "Guard 1", which 4.0 subsumes.** Do this **BEFORE** any of the 6 domain
> handler files are written (i.e. before Wave 1).

`frontend/src/features/studio/agent/effectRegistry.ts`:

- `:28` — `interface Entry { pattern: RegExp; handler: EffectHandler; }` (**drop `string |`**).
- `:32` — narrow to `export function registerEffectHandler(pattern: RegExp, handler: EffectHandler): void`
  and add a **runtime** guard as the first statement (**TS types are erased — an `as any` or a JS caller
  must still fail loudly**):

```ts
if (!(pattern instanceof RegExp)) throw new Error(
  `registerEffectHandler: pattern must be a RegExp, got ${typeof pattern}. A string was exact-or-prefix, ` +
  `NOT a pattern — 'composition_(style|voice)_' would have matched NOTHING and shipped a silent no-op handler.`);
if (pattern.global) throw new Error(
  'registerEffectHandler: pattern must not use the /g flag — RegExp.test() with /g advances lastIndex ' +
  'and alternates true/false across calls.');
```

- `:41-43` — collapse `matches()` to `pattern.test(tool)`; **delete the `typeof pattern === 'string'` ternary.**
- `:31` doc comment → `/** Register a handler for a tool-name RegExp (anchored, e.g. /^composition_arc_/). Strings are REJECTED — see plan 30 §8.0b. */`

`frontend/src/features/studio/agent/__tests__/effectRegistry.test.ts` — the only two string callers:
`:23` `'book_save'` → `/^book_save/`; `:33` `'book_'` → `/^book_/`; rename the `:21` test to
`'RegExp patterns match by test'`. **ADD the three regressions:**

```ts
it('REJECTS a string pattern — an alternation string would silently match nothing (§8.0b)', () => {
  expect(() => registerEffectHandler('composition_(style|voice)_' as unknown as RegExp, vi.fn()))
    .toThrow(/must be a RegExp/);
  expect(matchEffectHandlers('composition_style_set')).toHaveLength(0);
});
it('the RegExp form of the same pattern DOES match', () => {
  const h = vi.fn(); registerEffectHandler(/^composition_(style|voice)_/, h);
  expect(matchEffectHandlers('composition_style_set')).toContain(h);
  expect(matchEffectHandlers('composition_voice_apply')).toContain(h);
});
it('REJECTS the /g flag (test() advances lastIndex and alternates)', () => {
  expect(() => registerEffectHandler(/^book_/g, vi.fn())).toThrow(/\/g flag/);
});
```

**Binding on all 6 future domain handler files:** every `registerEffectHandler` call takes an **ANCHORED
RegExp** (`/^…/`). A string literal now fails `tsc` **and** throws at registration. The class is dead —
not discouraged.

#### 4a — Delete the FALSE comment

`frontend/src/features/studio/agent/useStudioEffectReconciler.ts:10` reads:

```
// authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale).
```

**Both halves are false.** `services/composition-service/app/mcp/server.py` registers **11**
`composition_authoring_run_*` MCP tools (`_list`, `_get`, `_create`, `_gate`, `_start`, `_resume`,
`_pause`, `_close`, `_accept_unit`, `_reject_unit`, `_revert_all` — from `:1616`), and the
**`agent-mode` panel shipped** (`catalog.ts:258`) and **is** the Studio consumer that goes stale
(`panels/agentMode/useNewRunForm.ts:124` invalidates `['authoring-runs', bookId]` by hand today).

**Replace lines 5-10 with:** *"Handlers are registered per-domain in `handlers/*.ts`; §8.0b of spec 30 is
the one-file-per-domain owner map. Coverage is machine-checked by `effectCoverage.contract.test.ts` — do
not add a domain without a row there."*

**AND fix the second stale comment the plan missed:** `effectRegistry.ts:4` still says
*"book/glossary/knowledge/translation as of 2026-07-05"*. Update it.

#### 4b — The one genuinely-stale domain: `composition_authoring_run_*`

🔴 **CREATE `frontend/src/features/studio/agent/handlers/authoringRunEffects.ts`.**
*(Not `agentModeEffects.ts` — `Q-30-X4-LANE-B-HANDLERS` §3 names the file, and the §8.0b row it adds says
`composition_authoring_run_* → authoringRunEffects.ts → owner: Wave 0`. **One name for one concept:** the
domain is the TOOL FAMILY, not the panel that happens to render it.)*

> **Why its own file, not `compositionEffects.ts`:** §8.0b's ONE-FILE-PER-DOMAIN law. Authoring runs is
> its own domain; `compositionEffects.ts` is **owned by spec 31 / Wave 1** (canon, corrections, style,
> voice). Two waves writing one file is the collision §8.0b exists to prevent.

**Mirror `knowledgeEffects.ts` exactly** — module-level `let registered`, a `_reset*` test hook, and a
**RegExp** (never a string; `4.0` now makes that a throw).

🔴 **SEVEN query keys, not three.** The first cut listed 3. `Q-30-X4-LANE-B-HANDLERS` §3 lists **7** —
invalidate all of them: `['authoring-runs']` · `['authoring-run']` · `['authoring-run-report']` ·
`['authoring-unit-diff']` · `['plan-runs-for-authoring']` · `['plan-run-for-authoring-gate']` ·
`['book-toc-for-authoring']`. *(Mission Control reads all seven; a partial invalidation is a partially
stale panel, which is the bug with extra steps.)*

**Double-fire check (done — do not skip it when you add a handler):** the 11 tool names are matched
against every existing registration:

| Existing pattern | File | Matches any `composition_authoring_run_*`? |
|---|---|---|
| `/^book_.*(draft\|chapter)/` | bookEffects | no (`book_` prefix) |
| `/^composition_.*(prose\|draft)/` | bookEffects | **no** — no authoring_run tool name contains `prose` or `draft` (checked all 11) |
| `/^composition_(outline_node\|scene_link)_/` | bookEffects | no |
| `GLOSSARY_WRITE_PATTERN` / `KNOWLEDGE_WRITE_PATTERN` / `/^translation_job_control/` | — | no |

⇒ `/^composition_authoring_run_/` is **disjoint**. Safe.

```ts
// #09 Lane B — authoring runs. The reconciler's header comment used to claim "authoring_run has no
// MCP tools at all, REST-only, no Studio consumer to go stale". BOTH halves were false: server.py
// registers 11 composition_authoring_run_* tools (from :1616), and the `agent-mode` panel
// (catalog.ts:258) is exactly the consumer that goes stale. An agent accept_unit/reject_unit/pause
// left Mission Control showing the PREVIOUS state until the user manually refetched.
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

let registered = false;

/** ⚠ INVALIDATE BY PREFIX — the result does NOT carry the ids.
 *  composition_authoring_run_accept_unit / _reject_unit return `{success, unit_index, status}`
 *  (server.py:1924, :1981) — NO run_id, NO book_id. A handler that tried to read `run_id` from the
 *  result would extract null and silently no-op (the `fe-status-default-fallback` class). Note
 *  ['authoring-run'] does NOT prefix-match ['authoring-runs', …] (different first element), so every
 *  key is listed explicitly. */
const KEYS = [
  ['authoring-runs'], ['authoring-run'], ['authoring-run-report'], ['authoring-unit-diff'],
  ['plan-runs-for-authoring'], ['plan-run-for-authoring-gate'], ['book-toc-for-authoring'],
] as const;

export function authoringRunEffect(ctx: EffectContext): void {
  for (const queryKey of KEYS) ctx.queryClient.invalidateQueries({ queryKey: [...queryKey] });
}

export function registerAuthoringRunEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(/^composition_authoring_run_/, authoringRunEffect);
}
export function _resetAuthoringRunEffectHandlers(): void { registered = false; }  // test hook
```

**Double-fire check (done — reproduce it whenever you add a handler):** the 11 tool names were matched
against every existing registration. `/^book_.*(draft|chapter)/` → no (`book_` prefix).
`/^composition_.*(prose|draft)/` → **no** (no authoring_run name contains `prose` or `draft` — checked all
11). `/^composition_(outline_node|scene_link)_/` → no. `GLOSSARY_WRITE_PATTERN` /
`KNOWLEDGE_WRITE_PATTERN` / `/^translation_job_control/` → no. ⇒ `/^composition_authoring_run_/` is
**disjoint. Safe.**

**EDIT** `useStudioEffectReconciler.ts`: import + call `registerAuthoringRunEffectHandlers()` in the
existing registration `useEffect` (~`:35`).
**Test:** `handlers/__tests__/authoringRunEffects.test.ts` — assert **each of the 11 real tool names**
matches, and **each of the 7 keys** is invalidated.
**ADD the §8.0b row** in plan 30: `composition_authoring_run_* → authoringRunEffects.ts → owner: Wave 0`.

#### 4c — 🔴 **THE ACTUAL WAVE-0 GATE ARTIFACT: the coverage LEDGER** (`Q-30-X4-LANE-B-HANDLERS` §4)

> 🔴 **CONTRADICTION FOLDED. The first cut's "Guard 2" fed a hand-written `TOOL_NAME_CORPUS` to
> `matchEffectHandlers` and asserted *no name matches >1*. THE DECISION SAYS: that is only the
> double-fire half. The gate Wave 0 owes the next 8 waves is a COVERAGE LEDGER — a literal
> tool-name → owning-file map with an explicit `PENDING` allowlist, asserting `>= 1` handler per write
> tool. It catches the X-4 bug class itself (a wave ships a panel and forgets its handler), AND it
> catches the double-fire, AND — because it feeds REAL tool names — it catches the string-vs-RegExp
> silent no-op that no per-handler unit test can see. The decision wins; it strictly subsumes Guard 2.**

**CREATE** `frontend/src/features/studio/agent/__tests__/effectCoverage.contract.test.ts`:

1. A literal **`WRITE_TOOLS: Record<string, string>`** mapping every write-tool **NAME** (not pattern)
   to its owning handler file. Seed it from the live inventory:
   - `composition_canon_rule_{create,update,delete,restore}`, `composition_publish`,
     `composition_conformance_run` → **compositionEffects** (W1)
   - `composition_arc_{create,update,delete,move,restore,apply,assign_chapters,import_analyze,extract_template,suggest}`,
     `composition_arc_template_drift` → **arcEffects** (W2)
   - `composition_motif_{create,patch,archive,adopt,bind,unbind,link_create,link_delete,mine,suggest_for_chapter}` → **motifEffects** (W3)
   - `plan_{compile,run_pass,apply_revision,propose_spec,self_check,validate,link,handoff_autofix,interpret_feedback,review_checkpoint}` → **planEffects** (W5)
   - `world_map_{create,delete,add_marker,remove_marker,add_region,remove_region}` → **worldEffects** (W8)
   - `registry_{propose_skill,propose_workflow,update_skill,update_workflow,set_skill_enabled,ingest}` → **registryEffects**
   - `composition_authoring_run_*` (all 11) → **authoringRunEffects** ✅ *(Wave 0 clears this)*
   - `kg_create_node` → **knowledgeEffects** ✅ *(Wave 0 clears this — see below)*
2. After calling **every** `register*EffectHandlers()`, assert for each name
   `matchEffectHandlers(name).length >= 1` **UNLESS** it is in an explicit
   **`PENDING: Record<string, 'wave-N'>`** allowlist.
3. Also assert `toHaveLength(0)` for representative **READ** tools each domain excludes
   (`glossary_get_*`, `kg_graph_query`, `world_map_get`, `world_map_list`, `translation_job_status`) —
   an over-broad new pattern that starts thrashing the cache also reds.
4. And assert **no name matches MORE than one** handler (the double-fire half — §8.0b).

**Wave 0 leaves `PENDING` holding exactly:** compositionEffects(**wave-1**) · arcEffects(**wave-2**) ·
motifEffects(**wave-3**) · planEffects(**wave-5**) · diagnosticsEffects(**wave-7**) ·
worldEffects(**wave-8**) · registryEffects(**wave-7**, the veto-able default — *"no Studio panel reads
registry workflows today, so a Wave-0 handler there would be the no-op class again"*).

> 🔴 **THE LINE THAT MAKES THIS A GATE — put it in EVERY wave's Definition of Done, verbatim:**
> *"delete this wave's rows from `PENDING` in `effectCoverage.contract.test.ts` by creating/extending its
> §8.0b handler file — **the test reds until you do.**"* That converts X-4 from a checklist item into a
> mechanical ledger. **Waves 4 and 6 add ROWS ONLY** (`composition_arc_apply`,
> `composition_arc_extract_template`, `composition_style_*`, `composition_voice_*`) — if a builder also
> adds a second `registerEffectHandler` call, the `<= 1` half reds and the wave cannot close.

**Supporting edits:** export a test-only `listEffectHandlers()` + `clearEffectHandlers()` from
`effectRegistry.ts`; extract the 4 (now 5) `register*EffectHandlers()` calls out of
`useStudioEffectReconciler`'s `useEffect` into one exported `registerAllStudioEffectHandlers()` barrel in
a new **`handlers/index.ts`**, and have the reconciler call the barrel. 🔴 **The ledger must test what the
APP actually registers** — a test that registers its own list proves nothing (memory:
`test-injecting-a-fake-at-the-chokepoint-cannot-prove-the-chokepoint-is-wired`).

#### 4d — `kg_create_node`: **VERIFY, do not ADD** — and pin it

> 🔴 **AUDIT CORRECTION #3 (confirmed by `Q-30-X4-LANE-B-HANDLERS` §2) — plan 30 X-4 lists
> `kg_create_node` as having "no handler". It already has one.**
> `KNOWLEDGE_WRITE_PATTERN = /^kg_(?!project_list|graph_query|world_query|multi_query|entity_edge_timeline|schema_read|list_templates|sync_available|view_read|triage_list)/`
> (`knowledgeEffects.ts:16`) is **allow-by-default over `kg_*` minus reads** — `kg_create_node` is **not**
> in the lookahead ⇒ **it matches today.** Adding a second handler is a **DOUBLE-FIRE** (4c reds).

**Wave 0's job is to PIN it:** add `kg_create_node` to `handlers/__tests__/knowledgeEffects.test.ts` as an
**explicit positive case**, so the truth stays true and Wave 8a finds a green assertion instead of
re-deriving the lookahead at 3am. *(That is what "Wave 0 clears this row" in 4c means.)*

> 📌 `registry_*workflow*` — **PO-2 DROPPED it to Track C.** Do **not** build a handler for it in Wave 0.
> It stays a `PENDING` row (target wave-7) so it is **tracked, not dropped**.

**DoD evidence:** `"npx vitest run src/features/studio/agent/ → all passed (effectRegistry rejects strings + /g; authoringRunEffects 11 tools × 7 keys; effectCoverage.contract PENDING=6 files documented; kg_create_node pinned); the false comments at useStudioEffectReconciler.ts:5-10 and effectRegistry.ts:4 are deleted"` **+ a LIVE BROWSER smoke:** open `agent-mode`, have the agent call `composition_authoring_run_pause`, and watch Mission Control's status **update without a manual refetch**.
**dependsOn:** —

---

### `W0-S5` — X-5 · RETIRE `ui_show_panel` (PO-3) · fix `ui_watch_job`

> ⚖ **DECISION: `Q-30-PO3-SHOWPANEL-NONSTUDIO-PATH`** — it **RATIFIES AUDIT CORRECTION #4 independently**
> (*"RETIRE `ui_show_panel` OUTRIGHT. Build no non-studio path and no migration shim, because the code
> proves there are ZERO working non-studio call sites to preserve"*) and supplies the exact 9-file edit
> list, which is folded in below. It voids only PO-3's **caveat**, not PO-3.

> 🔴 **AUDIT CORRECTION #4 — the "cross-surface migration" is far smaller than feared, because
> `ui_show_panel` has ZERO working consumers ANYWHERE.**
>
> The brief and plan 30 (PO-3) warn: *"`ui_show_panel` is also used **outside** the studio, so
> retirement must keep the non-studio call sites working."* **Traced. It does not work outside the
> studio either.** `uiNav.ts:115-130` resolves it to `` `${window.location.pathname}?panel=…` `` — a
> query param on the **current** page. **A repo-wide grep for a reader of `?panel=` returns exactly
> ONE file:** `frontend/src/features/composition/components/workspace/PopoutHost.tsx:27` — which is
> mounted at the **dedicated route `/composition/popout`** (`App.tsx:112`), is opened by
> `PopoutBridge` via `window.open` with its own `?book=&chapter=&panel=`, and **is not a page the
> chat is ever mounted on.**
>
> ⇒ **`ui_show_panel` appends a query param that nothing reads, and returns `{shown: true}`.** It is
> the repo's own `silent-success-is-a-bug` class, shipped and global. **Retiring it loses nothing.**
>
> ⚖ **The non-studio migration target already exists and already has an enum:**
> `ui_open_book {book_id, tab}` — `tab` enum `["overview","translation","glossary","enrichment","wiki","settings"]`
> (`frontend_tools.py:298`), already in `CLOSED_SET_ARGS`. That **is** "open a panel on a non-studio
> book page", done correctly. **The model loses no capability.**

#### Files — `ui_show_panel` retirement (delete every trace; a half-retired tool is worse than none)

| File | Change |
|---|---|
| `services/chat-service/app/services/frontend_tools.py` | Delete `UI_SHOW_PANEL_TOOL` (`:336-359`); remove `"ui_show_panel"` from `FRONTEND_TOOL_NAMES` (`:52`) and from the `_GENERIC` dict (`:655`); fix the module docstring (`:36`). |
| `services/chat-service/app/services/tool_discovery.py` | Remove `"ui_show_panel"` from **`ALWAYS_ON_CORE_NAMES`** (`:258`). Core drops **10 → 9**; the **≤10 ceiling still holds**. |
| `frontend/src/features/chat/nav/uiNav.ts` | Remove from `UI_TOOL_NAMES` (`:19`); **delete the `case 'ui_show_panel'`** (`:115-131`). **Leave `ui_navigate`/`ui_open_book`/`ui_open_chapter`/`ui_watch_job` untouched.** |
| `frontend/src/features/chat/utils/serverKey.ts` | Remove from `FRONTEND_TOOL_NAMES` (`:37`). |
| `services/chat-service/app/services/stream_service.py` | `:2362-2371` — **COMMENT ONLY.** The `_unwrap_wrapped_args(..., _fe_def)` logic is **schema-generic**; reword *"Protect ui_show_panel's real `args` param via its schema"* to name a surviving open-bag tool (or state it generically). 🔴 **DO NOT TOUCH THE LOGIC.** |
| `contracts/frontend-tools.contract.json` | **NEVER hand-edit — REGENERATE** (below). 12 tools → **11**. |
| **Do NOT** | add `ui_show_panel` to `STUDIO_UI_TOOLS` or `makeStudioNavInterceptor`, and do NOT alias it inside `resolveStudioUiTool`. *(The `panel`/`page` alias tolerance at `studioUiNav.ts:32` — which exists because a live gemma-26b smoke sent `panel:"editor"` — **stays**, and already catches a model reaching for the old name while calling `ui_open_studio_panel`.)* |
| Tests | `services/chat-service/tests/test_frontend_tools.py`, `test_tool_discovery.py:632`, `test_agent_surface.py:70`, `frontend/src/features/chat/nav/__tests__/uiNav.test.ts:99-110`, **and `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts`** (the one the first cut missed) — remove the `ui_show_panel` expectations. `studioUiNav.test.ts:109` asserts the interceptor *never claims* `ui_show_panel` — **that test is now vacuous; delete that line, keep the `ui_watch_job` half** (its meaning inverts below). |

#### Files — `ui_watch_job` → a studio dock panel (it currently **unmounts the dock**)

**The bug (verified).** `ui_watch_job` is in **neither** `STUDIO_UI_TOOLS` (`studioUiNav.ts:11`) **nor**
`makeStudioNavInterceptor` (`:53`). So inside the studio it falls through to the generic executor →
`uiNav.ts:135` → `path: '/jobs?focus=…'` → **the SPA navigates and the whole dock is torn down** —
even though `jobs-list` **and** `job-detail` panels exist (`catalog.ts:167-168`).

**Fix: intercept it, don't re-home it.** `ui_watch_job` is a **generic** tool (jobs are cross-domain,
and it is advertised on every surface — `jobs_skill.py:77`, `universal_skill.py:66`,
`workflow_skill.py:49`, `workflow_runner.py:202` all instruct the model to call it). Adding it to
`STUDIO_UI_TOOLS` would make it a studio-only tool and break those four skill prompts.

> ⚖ **ADJUDICATED — add it to `makeStudioNavInterceptor`, NOT to `STUDIO_UI_TOOLS`.** The interceptor
> is *exactly* the seam for "a generic nav tool that must become a dock action inside the studio" —
> it is what `ui_open_chapter` / `ui_open_book` / `ui_navigate` already do (`studioUiNav.ts:56-82`).
> The tool keeps ONE name, ONE schema, and ONE meaning on every surface; only its **effect** is
> remapped inside the dock. This *is* PO-3's "one name for one concept", applied consistently.

```ts
// frontend/src/features/studio/agent/studioUiNav.ts — a new case inside makeStudioNavInterceptor
      case 'ui_watch_job': {
        // Un-intercepted, the generic resolver pushes /jobs?focus=… and UNMOUNTS THE WHOLE DOCK
        // (uiNav.ts:135) — orphaning the agent's own resumed run. The `job-detail` panel exists
        // (catalog.ts:168, hiddenFromPalette because it needs params). Open it in place.
        const jobId = typeof args.job_id === 'string' ? args.job_id : '';
        if (!jobId) return null;   // malformed → fall through to the generic reject (no silent no-op)
        return {
          path: null,
          result: { watching: true, note: 'opened in the studio jobs panel' },
          effect: (host) => host.openPanel('job-detail', {
            component: 'job-detail',
            params: { jobId },
            title: `Job ${jobId.slice(0, 8)}…`,
          }),
        };
      }
```

⚠ **Verify `JobDetailPanel` reads `params.jobId`** — open the file and match the key name **exactly**
(`jobId` vs `job_id` is the `cross-service-normalization-bug-class`). If it reads a different key,
use **its** key. Do not guess.

⚠ `job-detail` is `hiddenFromPalette: true` ⇒ it is **outside** the `ui_open_studio_panel` enum
(X-12 / DOCK-6). That is correct and unchanged: the agent reaches it through `ui_watch_job`, which
carries the `job_id` param the bare-id enum cannot. **Do not add `job-detail` to the enum.**

#### Contract regeneration — the ONE way

```bash
cd services/chat-service
WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py
# then COMMIT the regenerated contracts/frontend-tools.contract.json IN THIS SAME COMMIT.
```

The `panel_id` enum **must still be `N_before`** after this slice — we removed a **tool**, not a **panel**.
🔴 **Assert the DELTA (`N_after === N_before`), never the literal** (`Q-30-ENUM-COUNT-BASELINE`). The
contract's **tool** count goes **12 → 11**; `test_every_advertised_name_has_exactly_one_schema`
(`test_frontend_tools_contract.py:103`) is the machine check that both sides agree.

⚠ **SEQUENCING — `Q-30-X6-RESOURCE-REF` §4 + `00B_EXECUTION_ROADMAP.md:203`: NEVER TWO CONCURRENT CONTRACT
REGENS.** `W0-S5` (retire) → `W0-S5b` (add `params`) → `W0-S5c` (X-13) each regenerate
`contracts/frontend-tools.contract.json`. **Land them SERIALLY, in that order, each regen committed with
its own code change.** Do not batch them and do not interleave them with Wave 2's `ui_focus_resource`.

#### Tests

| File | Test | Asserts |
|---|---|---|
| `services/chat-service/tests/test_frontend_tools.py` | `test_ui_show_panel_is_retired` | `"ui_show_panel" not in FRONTEND_TOOL_NAMES`; `generic_frontend_tool_def("ui_show_panel") is None`; it appears in **no** `frontend_tool_defs(...)` combination (editor/book_scoped/studio/none). |
| `services/chat-service/tests/test_frontend_tools_contract.py` | (existing) | The regenerated contract has no `ui_show_panel` key and the FE guard agrees. |
| `frontend/src/features/chat/nav/__tests__/uiNav.test.ts` | `isUiTool('ui_show_panel') === false`; `resolveUiTool('ui_show_panel', …)` → `{path: null, result: {}}` (the default branch — **never** a `shown:true`). |
| `frontend/src/features/studio/agent/__tests__/studioUiNav.test.ts` | `ui_watch_job opens job-detail in the dock and does NOT navigate` | `makeStudioNavInterceptor(host)('ui_watch_job', {job_id:'j9'})` → `path === null`, `result.watching === true`; running `effect(host)` calls `host.openPanel('job-detail', {…params:{jobId:'j9'}})`. |
| ″ | `ui_watch_job with no job_id falls through (never a silent success)` | returns `null` ⇒ the generic resolver's `{watching:false, error:'missing job_id'}` is what the agent gets. |

**DoD evidence:** `"chat-service: pytest tests/test_frontend_tools*.py tests/test_tool_discovery.py tests/test_agent_surface.py -q → all passed; contract regenerated (ui_show_panel gone: 12 tools → 11; panel_id enum N_after === N_before). frontend: npx vitest run src/features/chat/nav src/features/studio/agent → all passed."` **+ the hygiene grep returning ZERO lines** (§9 risk 3) **+ TWO LIVE BROWSER smokes:** (1) ask the agent *"open the glossary"* → **a dock tab actually appears** (verify by EFFECT, not raw stream); (2) ask it to start a translation job → it calls `ui_watch_job` → **the dock is still mounted** and a `job-detail` tab appeared. *(Exactly `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`: a raw-stream check would show `watching:true` while the dock was destroyed.)*
**dependsOn:** —

---

### `W0-S5b` — 🆕 **X-12 · `ui_open_studio_panel` gains an OPTIONAL `params` object**

> ⚖ **DECISION: `Q-30-X12-PARAMS-ARG`. 🔴 THIS SLICE DID NOT EXIST IN THE FIRST CUT — THE PLAN SAID
> "NO".** Its defer row `D-X12-PANEL-PARAMS` read *"⚖ ADJUDICATED: NO, and it is not needed."*
> **THE DECISION SAYS: BUILD IT, in Wave 0, paired with X-5 exactly as §8.2 asked. The decision wins,
> and the defer row is DELETED (§8).**
>
> **The decisive fact, which the plan's "no" never confronted: SEALED PO-3 ALREADY REQUIRES IT.** PO-3
> mandates `ui_watch_job` → open `job-detail`, and `JobDetailPanel.tsx:1` says verbatim *"singleton,
> **retargets via params**"*. **Without a `params` arg a sealed decision cannot be implemented
> faithfully** — `W0-S5` has to smuggle the `jobId` through a bespoke interceptor `effect` precisely
> because the tool itself cannot carry it. On top of that, **three specs in this very batch design a
> params deep-link the agent structurally cannot use** (`32:142` `props.params.arcId`; `38:203`
> `params.mapId`; `31:136` `props.params.focusRuleId`).
>
> **It does NOT contradict §8.0 check 5.** That check answers only the `hiddenFromPalette` half of X-12
> (no panel is forced *out* of the enum); **it is silent on the deep-link half.** Because `params` is
> **OPTIONAL**, all 14 future panels stay bare-id openable, stay in the enum/palette/User Guide, and the
> `N_before + k` ledger is **untouched**.

**The whole params pipe ALREADY EXISTS below the agent** (`StudioHostProvider.tsx:52` accepts
`opts.params`; `:83` calls `updateParameters()` on an already-open panel ⇒ **retargeting an open
`arc-inspector` works for free**; `:92` passes them to `addPanel`). **The agent is the only caller in the
repo that cannot pass them.** The work is ~1 schema field + ~4 lines of resolver.

#### Files

| # | File | Change |
|---|---|---|
| 1 | `services/chat-service/app/services/frontend_tools.py` | In `UI_OPEN_STUDIO_PANEL_TOOL["function"]["parameters"]["properties"]`, **after `panel_id` (~`:402`)**, add the `params` property (below). 🔴 **LEAVE `required` as `["panel_id"]` — `params` must NOT be required.** |
| 2 | `services/chat-service/tests/test_frontend_tools_contract.py` | 🔴 **Do NOT add `params` to `CLOSED_SET_ARGS` (`:57`).** Its values are dynamic UUIDs; that dict's own comment (`:54-56`) reserves it for *"a FINITE, code-known set"* and explicitly excludes free-form/UUID args. **`panel_id` remains the tool's only closed-set entry.** *(This is the explicit answer to the "+ CLOSED_SET_ARGS?" half of X-12: **NO ENTRY**.)* |
| 3 | `contracts/frontend-tools.contract.json` | **REGENERATE** (`WRITE_FRONTEND_CONTRACT=1 pytest tests/test_frontend_tools_contract.py`); commit in the **SAME** commit as (1). ⚠ **After `W0-S5`, never concurrently.** |
| 4 | `frontend/src/features/studio/agent/studioUiNav.ts:35` | Replace the one line that drops params (below). |
| 5 | — | 🔴 **There is only ONE executor** (`useStudioUiToolExecutor` → `resolveStudioUiTool`). The chat-side mirror `frontend/src/features/chat/utils/serverKey.ts:41` is a **NAME list only** (no arg shape) and needs **NO change**. **Do not go hunting for a second resolver.** |

```python
# frontend_tools.py — the new property (the description gloss is the model's ONLY hint at the key names)
"params": {
    "type": "object",
    "additionalProperties": True,
    "description": (
        "OPTIONAL deep-link target — the ID of the row you want the panel focused on. IDs only, never prose. "
        "Recognized keys: arc-inspector {arcId}; world-map {mapId}; quality-canon-rules {focusRuleId}; "
        "job-detail {jobId}; chapter-revision-compare {chapterId, fromRevisionId, toRevisionId}; "
        "book-reader {bookId, chapterId}; settings {tab}. Omit it and the panel self-resolves a sane default."
    ),
},
```

```ts
// studioUiNav.ts:35 — was: return { result: { opened: true }, effect: (host) => host.openPanel(panelId) };
const p = args.params;
const params = p && typeof p === 'object' && !Array.isArray(p) ? (p as Record<string, unknown>) : undefined;
return {
  result: { opened: true, ...(params ? { params } : {}) },
  effect: (host) => host.openPanel(panelId, params ? { params } : undefined),
};
// A NON-OBJECT params (the weak-model drift, e.g. the string "arcId=A") is DROPPED, not crashed on —
// the panel still opens bare-id. NO host change is needed.
```

#### Tests (all must be **written**, not just run)

| File | Asserts |
|---|---|
| `frontend/src/features/studio/agent/__tests__/studioUiNav.test.ts` | (a) `{panel_id:'arc-inspector', params:{arcId:'A'}}` → spy `host.openPanel` called with `('arc-inspector', {params:{arcId:'A'}})`; (b) **no params → `openPanel('arc-inspector', undefined)`** — the bare-id open is unbroken; (c) `params:'arcId=A'` (a **string**) → `opened:true`, params **dropped**, **no throw**. |
| `services/chat-service/tests/test_frontend_tools.py` | `'params' in properties`; `type == 'object'`; **`'params' NOT in required`**. |
| both drift-locks | `test_frontend_tools_contract.py` + `panelCatalogContract.test.ts` stay green (py enum == contract enum == openable; **`N_after === N_before`** at Wave 0 close). |

**AMEND §8 step 5 of the per-panel checklist:** *a new panel that accepts a params deep-link must ALSO
append its key to the `params` description gloss — that prose is the model's only hint about the key's name.*

> **PO-veto-able default (recorded):** `params` is **free-form (no enum)**, so a weak model could invent a
> key. **Accepted** — the resolver ignores unknown keys, every panel reads dockview params defensively
> (`ChapterRevisionComparePanel.tsx:34`'s `str()` guard), the panel self-resolves a default, and the
> bare-id path is unchanged. A closed enum of key names would have to be re-opened on every new panel and
> buys nothing the panel-side guard doesn't already give.

**DoD evidence:** `"chat-service: pytest tests/test_frontend_tools.py tests/test_frontend_tools_contract.py -q → passed; contract regenerated (ui_open_studio_panel.params present, NOT in required, NOT in CLOSED_SET_ARGS). frontend: npx vitest run src/features/studio/agent → 3 new passed."` **+ a LIVE BROWSER smoke (VERIFY BY EFFECT — GG-8: a green unit suite does not prove the loop closed):** drive `ui_open_studio_panel {panel_id:"job-detail", params:{jobId:"<a real id>"}}` and assert **the dock tab mounts ON THAT JOB**. *(Precedent: `studio-palette.spec.ts`.)*
**dependsOn:** `W0-S5` (contract-regen serialization).

---

### `W0-S5c` — 🆕 **X-13 · DELETE the two dead fields — and fix the SILENT SUCCESS they pretended to guard**

> ⚖ **DECISION: `Q-30-X13-CONSUMER-CAPABILITIES-DEAD`. 🔴 A SLICE THE FIRST CUT DID NOT HAVE AT ALL.**
> *"WAVE 0 — but NOT as 'implement the two fields'. **DELETE both dead fields and fix the REAL bug they
> were nominally defending against.**"* It rides X-5/X-12 (same files, same contract regen).
> **All three premises of X-13-as-filed are false:** `consumer_capabilities` is not "stored-but-unread",
> it is an **EMPTY model** (`class ConsumerCapabilities(BaseModel): pass`, `models.py:474-476`) with
> **zero producers**; the G6 advertise-filter **already exists and is CI-enforced statically**
> (`frontend_tool_defs(editor=|book_scoped=|studio=)`, `frontend_tools.py:670-691`, + the
> `panelCatalogContract.test.ts` triple lock); and `contributeContext()` is **dead by construction**
> (`useStudioPanel.ts:14` forwards only `mcpToolPrefixes|mcpTools|frontendTools|skills`, so no panel
> using the shared helper can even supply it).

#### X-13a — BE: delete `consumer_capabilities` (chat-service)

Delete `class ConsumerCapabilities` (`app/models.py:474-476`) **and** the field
`consumer_capabilities: ConsumerCapabilities | None = None` (`:502`). **Safe:** zero senders repo-wide
(grep: only `models.py` + docs), and Pydantic's default `extra='ignore'` means a hypothetical caller
sending the key still **200s**.

Then **AMEND — do not fork —** the specs that promised it, stating the filter is **STATIC + CI-enforced,
not a runtime handshake**: `09_agent_gui_reconciliation.md` (G6 `:42`, the JSON `:269`, the prose `:283`),
`07_studio_agent_chat.md:85`, `00_OVERVIEW.md:93`/`:99`, and the **`docs/standards/README.md:76`
enforcement cell** (replace *"`consumer_capabilities.frontend_tools` advertise filter"* with
*"`frontend_tool_defs()` surface gating + `panelCatalogContract.test.ts` enum⇄catalog lock"*).

**Test:** none new. `pytest tests -q -n auto --dist loadgroup` in chat-service **must stay green** — *that
is the proof nothing read it.*

#### X-13b — 🔴 FE: **THE REAL BUG, and it is LIVE TODAY**

`studioUiNav.ts:32-38` returns `{ result: { opened: true }, effect: host.openPanel(panelId) }` for **ANY
non-empty string**, and `StudioHostProvider.tsx:92` **swallows the unknown-component throw**
(`catch { /* panel not in the catalog */ }`). **Net: the agent is told `opened: true` while nothing
opened** — the repo's own `silent-success-is-a-bug` class, **shipped**. Every panel Waves 1–8 add
multiplies it.

**FIX** — in `studioUiNav.ts`, import `STUDIO_PANEL_COMPONENTS` from `../panels/catalog` and **validate
BEFORE returning success**:

```ts
if (!(panelId in STUDIO_PANEL_COMPONENTS)) {
  return { result: { opened: false,
    error: `unknown panel_id "${panelId}" — valid ids: ${Object.keys(STUDIO_PANEL_COMPONENTS).join(', ')}` } };
  // no `effect` — nothing to run.
}
```

🔴 **Validate against `STUDIO_PANEL_COMPONENTS` (the *buildable* set), NOT `OPENABLE_STUDIO_PANELS`** — so
X-12's params-carrying `hiddenFromPalette` ids (`job-detail`, `arc-inspector`, `motif-editor`) do **not**
false-reject. **KEEP** the existing `panel`/`page` alias tolerance (`:32`) — it exists because a live
gemma-26b smoke sent `panel:"editor"`.

**Also make `StudioHostProvider.openPanel` return `boolean`** (`false` on `!api` or on the caught
`addPanel` throw), so no future caller can re-introduce a silent swallow.

**Tests** (`frontend/src/features/studio/agent/__tests__/studioUiNav.test.ts`):
- `unknown panel_id ⇒ opened:false + result.error, and NO effect returned`;
- a regression that **every id in the contract's `ui_open_studio_panel.panel_id.enum` resolves with
  `opened:true`** — guarding the **enum⇄resolver** seam the same way `panelCatalogContract.test.ts` guards
  the **enum⇄catalog** seam.

#### X-13c — FE: delete `contributeContext`

Delete `contributeContext?: () => StudioContextSlice | null;` (`host/types.ts:31`) and
`interface StudioContextSlice` (`types.ts:34-39` — unreferenced; grep confirms `types.ts` is the only
file). Replace the line in the three specs that promise it (`07c_studio_tool_registry.md:54`,
`08_studio_state_architecture.md:300` item 4, `04b_raw_editor.md:152`) with **the law every new panel in
Waves 1–8 follows**:

> **"A panel feeds the agent by PUBLISHING a bus event (`host.publish({type: …})`), never by implementing
> a second context mechanism. If a panel's slice key has no `StudioBusEvent` variant, ADD one — the union
> is additive (`types.ts:41-66`)."**

**DoD evidence:** `"chat-service: pytest tests -q -n auto --dist loadgroup → ≥ baseline, 0 failed (proves nothing read consumer_capabilities). frontend: npx vitest run src/features/studio/agent → 2 new passed (unknown panel_id ⇒ opened:false + error; every contract enum id ⇒ opened:true)."` **+ a LIVE BROWSER smoke: the agent calls `ui_open_studio_panel` with a BOGUS id and gets a VISIBLE `error` back — not a hallucinated "Opened!".**
**dependsOn:** `W0-S5b` (contract-regen serialization; X-13b's enum⇄resolver test reads the regenerated contract).

---

### `W0-S6` — X-7 · the `gather_motif` packer lens 🔴 **THE HARD GATE ON WAVE 3**

**The bug (verified — `grep -rn "motif" services/composition-service/app/packer/*.py` → ZERO hits).**
The author binds 打脸 to chapter 41. The Hub renders the chip. The binder writes `motif_application`.
The conformance engine **grades the prose against it**. And `pack()` **never tells the drafter.**

**This is the *stored-but-unread ⇒ write-only-behavior* class CLAUDE.md bans by name.** Wave 3 ships
a motif library, a binding lens, and suggest buttons — **all authoring data with no consumer** until
this lands. **Without X-7, Wave 3 is decoration.**

> ⚖ **DECISIONS: `Q-30-X7-GATHER-MOTIFS-LENS` · `Q-30-BE-M2-MISSING`.** Both CONFIRM: build it in Wave 0;
> it IS the hard gate on Wave 3; deferral is **not available** (the read path already exists ⇒ this is
> **unbuilt wiring**, not missing infrastructure). `Q-30-BE-M2-MISSING` settles the ID confusion:
> 🔴 **`X-7` == spec 30's `BE-19` == spec 33's `BE-M2` — ONE item, THREE ids. Build it ONCE, in Wave 0.**
> **Canonical id = `X-7`.** Wave 3 only **verifies** it.

**Contract owner:** 🔴 **`33_motif_studio.md` §5 `BE-M2` (`:441`) — the ONLY row carrying the full contract**
(the signature, the scene→chapter resolution chain, `sanitize_lore`/SEC3, the best-effort-`""` rule, the
≤3-binding cap). **READ THAT ROW, not X-7's one-line summary.** This plan implements it.

#### Naming — 🔴 **the decision's names win. Use these EXACTLY.**

> The first cut used `gather_motifs` / `<motifs>` / `motif_app_repo=`. **`Q-30-X7-GATHER-MOTIFS-LENS`
> specifies `gather_motif` / `<motif>` / `motif_application_repo=`.** Cosmetic — **and therefore exactly
> the kind of drift that costs an hour at 3am when the grep does not match.** The decision wins.
> The **lens** is `gather_motif`; the **block** is `<motif>`; the **kwargs** are
> `motif_application_repo=` and `motif_repo=`.

#### Files

| File | Change |
|---|---|
| `services/composition-service/app/packer/lenses.py` | **CREATE `async def gather_motif(...)`** immediately **after `gather_arc`** (which ends `:363`) — mirror its shape exactly: same repo-injection signature, same best-effort posture, same `sanitize_lore` discipline. |
| `services/composition-service/app/packer/pack.py` | `:194` — add `motif_application_repo=None, motif_repo=None` beside `structure_repo=None`. `:332-337` — add `motif_gated` beside `arc_gated`, gated on `(motif_application_repo is not None and motif_repo is not None and node_id is not None)`, else `_empty_str()`. `:338` — add it to the existing `asyncio.gather(...)` tuple. `:522` — emit `<motif>` **immediately after** the `<arc>` frame. |
| `services/composition-service/app/routers/engine.py` | 🔴 **Wire the repos at ALL THREE `pack()` call sites: `:391`, `:767`, `:973`.** |
| `services/composition-service/app/routers/grounding.py` | 🔴 **And the fourth: `:103`.** |
| `services/composition-service/tests/unit/test_pack_motif.py` | **CREATE** — the unit **effect** test (mirror `test_pack_arc.py`). |
| `services/composition-service/tests/integration/db/test_pack_motif_wired.py` | **CREATE** — the real-DB **wired** proof (mirror `test_pack_arc_wired.py`). |

> 🔴 **AUDIT CORRECTION #8 — THE DECISION UNDERCOUNTS THE CALL SITES, AND THIS IS THE ONE PLACE THAT
> MATTERS.** `Q-30-X7-GATHER-MOTIFS-LENS` §2 says *"`routers/engine.py:391` — **the** real `pack(...)` call
> site."* **There are FOUR** (re-verify with pre-flight 1b):
> `engine.py:391` · `engine.py:767` · `engine.py:973` · `grounding.py:103` — **all four already pass
> `structure_repo=`** (`grep -c "structure_repo=" …` → engine 3, grounding 1). **Wire ALL FOUR.**
> This is not a disagreement with the decision — it is the decision's **own** stated principle
> (*"A lens not passed here is a lens that does not exist in production — that is verbatim the arc bug"*)
> applied to the complete set. `grounding.py` is the **context-inspector preview**: miss it and the
> preview and the real prompt **disagree**, which is worse than both being wrong.

> 🔴 **THE WIRING TRAP — this is the bug BA12 already shipped once, and `/review-impl` caught it.**
> From `test_pack_arc_wired.py`'s own docstring: *"no production caller did either: the pack() call
> sites omitted `structure_repo=` … so in production `arc_gated` always took the dormant branch and
> the arc never reached the prompt. The write-only-arc bug the whole spec exists to kill was alive in
> prod, and D2 could not see it because it bypassed the real chokepoint."*
> **There are exactly 4 `pack()` call sites** (verified: `engine.py:391`, `engine.py:767`,
> `engine.py:973`, `grounding.py:103` — all four already pass `structure_repo=`). **Miss one and you
> have re-shipped the identical bug.** `grounding.py` is the context-inspector preview: if it is
> missed, the preview and the real prompt **disagree**, which is worse than both being wrong.

#### The lens — `Q-30-X7-GATHER-MOTIFS-LENS` §1 is the build spec. Follow it literally.

```python
# services/composition-service/app/packer/lenses.py — immediately AFTER gather_arc (ends :363).

async def gather_motif(
    applications_repo, motif_repo, project_id: UUID, node_id: UUID, *, user_id: UUID,
) -> str:
    """X-7 == 30 BE-19 == 33 BE-M2 — the MOTIF lens: the narrative-craft layer (套路/爽点/打脸)
    reaching the prompt. The anti-write-only proof for the whole motif cluster — a motif bound
    to a scene must STEER generation, and the effect test asserts this frame CHANGES when the
    binding changes.

    a. apps = await applications_repo.by_nodes(project_id, [node_id])   # already filters project_id
       → take the LAST row. by_nodes is ORDER BY created_at ASC ⇒ last-wins on a re-bind — the
         same rule plan.py:1196 already applies. Empty → return "".
    b. m = await motif_repo.get_visible(user_id, app.motif_id)
       → None (archived / foreign motif; motif_id is SET NULL per models.py:545) → return "".
         No oracle — exactly as plan.py:1188 degrades.
    c. Render:
         · Motif: "<name>" (<kind>)   +  Motif intent: <summary>
         · the BOUND BEAT — resolve app.annotations["beat_key"] against m.beats[] (MotifBeat,
           models.py:476) → `Beat: <label> — <intent>` + `Tension target: <n>/5` when set.
           Absent beat_key → list the motif's beats in `order` as the scene's shape.
         · `Reversal:` / `Alliance shift:` from app.annotations (or the beat's), when present.
         · `Motif roles:` — role_bindings (role_key → entity_id), rendered EXACTLY like
           gather_arc's "Cast bindings" (lenses.py:337-343). A null entity_id (set_role_binding
           writes JSON null for an unresolved role) renders `role_key → (unresolved)` —
           NEVER dropped silently.
    d. sanitize_lore() EVERY author-authored string (name, summary, beat label/intent, role keys).
       STRICTER than gather_arc's need, not looser: motifs can be MINED from imported third-party
       text (source/imported_derived, models.py:519-521), so the SEC3 delimiter-forging surface
       is LARGER here.
    e. Best-effort: wrap in try/except Exception → logger.warning(...); return "".
       The motif frame THINS, never fails a pack.

    🔴 CAPPED (≤3 bindings — 33 BE-M2). The <motif> block rides OUTSIDE enforce_budget (like
    <arc>), so an UNCAPPED block is a Context-Budget-Law hole.
    """
```

Repos to use (both already built + tenant-gated): `MotifApplicationRepo.by_nodes`
(`motif_application.py:94` — **it already filters `project_id`**, the tenancy rule) and
`MotifRepo.get_visible` (used at `plan.py:1211`).

#### The pack() gate + emit — copy `gather_arc`'s exact posture

```python
# pack.py — beside arc_gated (:332-337)
    motif_gated = (
        gather_motif(motif_application_repo, motif_repo, req.project_id,
                     _as_uuid(node.get("id")), user_id=req.user_id)
        if (motif_application_repo is not None and motif_repo is not None and node_id is not None)
        else _empty_str()
    )
# …add motif_text to the asyncio.gather(...) tuple at :338…

# pack.py — beside the <arc> emit (:522)
    if motif_text:
        blocks["motif"] = motif_text
        prompt = f"<motif>\n{motif_text}\n</motif>" + (f"\n{prompt}" if prompt else "")
```

**Order:** the arc frame is composed **HERE, prepended manually — NOT via `assemble.py`'s `_BLOCK_ORDER`**
(note `"arc"` is deliberately **absent** from `assemble.py:25`). **Follow that same pattern.** Inject
`<motif>` **immediately after** the `<arc>` frame, so the prompt reads `<arc>` → `<motif>` → the rest.
**The arc = the durable chapter-level spec frame; the motif = the scene-level beat structure inside it.**

#### The tests — 🔴 **BOTH are required.** (`Q-30-X7-GATHER-MOTIFS-LENS` §3)

> **The decision is explicit that the plan's first cut was one test short:** *"The spec asked for 'a
> BA12-style EFFECT test'; **a unit effect test is precisely what FAILED to catch this bug for the arc
> lens**, so it is necessary but NOT sufficient."* Write **both.**

**1 · `tests/unit/test_pack_motif.py`** — the **effect** test (mirror `test_pack_arc.py`): the prompt
**CHANGES** when a binding changes. Assert the rendered prompt differs when `role_bindings` / `beat_key`
differ, and that an **unbound scene is byte-unchanged**.

**2 · `tests/integration/db/test_pack_motif_wired.py`** — the **WIRED** proof (mirror
`test_pack_arc_wired.py`). It exists *because* the unit test injected a fake at the chokepoint and
therefore proved nothing (memory:
`test-injecting-a-fake-at-the-chokepoint-cannot-prove-the-chokepoint-is-wired`). It drives the **real**
`pack()` through the **real** `MotifApplicationRepo` + `MotifRepo` against a **real** DB, from a scene node
carrying only its ids.

```python
pytestmark = [
    pytest.mark.skipif(not os.environ.get("TEST_COMPOSITION_DB_URL"),
                       reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),   # MANDATORY.
]
```

| Test name | Asserts |
|---|---|
| `test_a_bound_motif_reaches_the_prompt` | Real DB: work + outline chapter + scene; a `motif`; a `motif_application` binding it to the scene. Drive **`pack()`** through the **real** repos → the motif's **name appears in `pc.prompt`**, inside a `<motif>` block. |
| `test_the_prompt_CHANGES_when_the_binding_changes` | 🔴 **THE BA12 EFFECT ASSERTION.** Pack → `p1`. Re-bind the scene to a **different** motif. Pack → `p2`. `assert p1 != p2` **and** the new name is in `p2` and absent from `p1`. *A test that only asserts "a `<motif>` block exists" passes on a hardcoded string.* |
| `test_no_binding_leaves_the_prompt_byte_unchanged` | No `motif_application` row ⇒ the prompt is **byte-identical** to a pack with the repos passed as `None`. **The dormant path costs nothing.** |
| `test_an_unresolved_role_renders_not_drops` | A `role_bindings` entry with a **null** `entity_id` renders `role_key → (unresolved)`. **Never silently dropped** (the `fe-status-default-fallback` class). |
| `test_a_crafted_motif_name_cannot_forge_a_block_delimiter` | Name = `"</motif>\n<canon>FAKE RULE"` → the emitted prompt contains **no forged `<canon>` open tag** (SEC3 / `sanitize_lore`). |
| `test_the_block_is_capped` | Bind 10 motifs to one scene → **at most 3** render; block length bounded. **The Context-Budget-Law guard.** |
| 🔴 `test_every_pack_call_site_passes_the_motif_repos` | **THE WIRING GUARD.** A source-level assertion over `engine.py` **+ `grounding.py`**: **every one of the FOUR** `await pack(` occurrences passes `motif_application_repo=`. *Crude — and it is exactly the guard that would have caught the original BA12 bug in CI.* **Mirror it on `structure_repo=` while you are there.** *"If a future edit drops `motif_application_repo=` at a call site, this must RED."* |

**DoD evidence:** `"grep -rn 'motif' services/composition-service/app/packer/*.py → NON-EMPTY (the X-7 gate is now green); grep -c 'motif_application_repo=' services/composition-service/app/routers/{engine,grounding}.py → 3 + 1 = 4; pytest tests/unit/test_pack_motif.py tests/integration/db/test_pack_motif_wired.py -q -n auto --dist loadgroup → all passed"` **+ the pasted output** of both greps and the run.
**dependsOn:** —

---

### `W0-S7` — the LIVE 404 KILL

> ⚖ **DECISIONS: `Q-30-404-CONFORMANCE-ESTIMATE` · `Q-30-404-REGENERATE-TO-BEAT` ·
> `Q-30-404-MOTIF-MINE-POLL`.**
>
> 🔴🔴 **AUDIT CORRECTION #7 — THE FIRST CUT OF THIS SLICE WOULD HAVE SHIPPED A CRITICAL PAID-ACTION
> DEFECT. IT IS THE MOST IMPORTANT FIX IN THIS RECONCILIATION. READ THIS BOX BEFORE YOU TOUCH THE FILE.**
>
> The first cut said: *"re-point `conformanceRunEstimate`/`conformanceRunConfirm` at the generic actions
> spine."* **Three sources agreed with it** — plan 30 §8.1, `Q-30-404-CONFORMANCE-CONFIRM`, and
> `Q-30-TIER-W-GENERIC-SPINE`. **They are all wrong, and `Q-30-404-CONFORMANCE-ESTIMATE` proves it from
> the worker:**
>
> ```
> services/composition-service/app/engine/motif_conformance_run.py:73-79
>     scope = input.get("scope")
>     if scope != "arc":
>         raise ValueError(f"conformance_run worker supports scope='arc' only (got {scope!r}); "
>                          "chapter conformance is the synchronous GET trace ...")
> ```
> **The worker TERMINALLY REJECTS `scope='chapter'`.** Meanwhile `composition_conformance_run`
> (`server.py:3141`) happily **MINTS** a confirm token for `scope='chapter'`, and `/actions/confirm` →
> `_execute_conformance_run` (`actions.py:714`) **ledger-claims → `_precheck_or_402` billing-prechecks →
> enqueues** — **all BEFORE the worker's `ValueError`.**
>
> ⇒ **Wiring the chapter FE to the "real" spine converts a harmless 404 into a PAID JOB GUARANTEED TO
> FAIL.** That is the motif-mine twin the PO named **CRITICAL**. **The fix is DELETE, not re-point.**
>
> **And chapter conformance is ALREADY FREE + SYNCHRONOUS:**
> `GET /works/{project_id}/conformance?scope=chapter&chapter_id=…` (`conformance.py:334`) reads stored
> per-scene verdicts — **no LLM** — and the hook **already calls it** (`motifApi.conformance`).
> **"Re-run" for a chapter == REFETCH.** *(Re-verify with pre-flight 1b.)*

**The gateway is a pure path-preserving proxy** (`gateway-setup.ts:354`,
`pathFilter: (p) => p.startsWith('/v1/composition')`, **no rewrite**) — an FE path with no BE route 404s
and nothing saves it.

| # | The bad call | Live caller | 🔴 The fix (**REVISED**) |
|---|---|---|---|
| 1 | `POST /actions/conformance_run/estimate` | `motif/api.ts:223` ← `useConformanceTrace.ts:32` | **DELETE. Do NOT re-point.** |
| 2 | `POST /actions/conformance_run/confirm` | `motif/api.ts:229` ← `useConformanceTrace.ts:36` | **DELETE. Do NOT re-point.** |
| 2b | *(source hardening)* | `mcp/server.py:3141` | 🔴 **The MCP tool must REFUSE to mint what the worker cannot run.** |
| 3 | `POST /works/{pid}/scenes/{nid}/regenerate-to-beat` | `motif/api.ts:301` ← `ConformanceTraceView.tsx:69` | **DELETE the method. Re-point the button at the EXISTING scene-generate — NOT at the actions spine.** |
| 4 | `GET /jobs/{synthetic}` (the MINE / 拆文 poll) | `motifApi.mineConfirm` + 2 more | → `GET /motif-jobs/{id}` (**`W0-BE1`**). |

#### 1 + 2 — DELETE the invented chapter Tier-W flow (`Q-30-404-CONFORMANCE-ESTIMATE`)

- `frontend/src/features/composition/motif/api.ts` — **DELETE `conformanceRunEstimate` (`:223`) and
  `conformanceRunConfirm` (`:228`) outright.** 🔴 **Do NOT re-point them.**
  **KEEP `arcConformanceRunPropose`/`arcConformanceRunConfirm` (`~:249`/`~:277`)** — those are **correct**
  (arc scope is what the worker runs) and remain the model for any future paid flow.
- `frontend/src/features/composition/motif/hooks/useConformanceTrace.ts` — delete the `estimate`
  `useState`, `mintRun`, `confirmRun`, `cancelRun`, and the now-unused `CostEstimate` import. Keep
  `query` / `refetch`. **Export `rerun: () => query.refetch()` and `isFetching: query.isFetching`.**
- `frontend/src/features/composition/motif/components/ConformanceTraceView.tsx` — the
  `[data-testid=conformance-rerun]` button (`:41-46`) calls `trace.rerun()`,
  `disabled={!projectId || !chapterId || trace.isFetching}`. 🔴 **DELETE the `CostConfirmCard` block
  (`:50-58`) and its import (`:7`). No cost card, no confirm — the read is FREE.**

#### 2b — 🔴 HARDEN AT SOURCE, same slice (~4 lines). **The FE fix alone does NOT close this.**

An LLM can still call the tool directly. In `services/composition-service/app/mcp/server.py:3141`, make
`composition_conformance_run` **refuse to mint what the worker cannot run** — for `scope == 'chapter'`
return

```python
{"success": False,
 "error": "chapter conformance is a free synchronous read (GET …/conformance?scope=chapter) — no run needed"}
```

**instead of minting a confirm token.** **No live caller can regress:** the worker rejects chapter today,
so **no chapter mint has ever succeeded.** Unit test: `scope='chapter'` → `success:False` and **NO
`confirm_token` is minted.**

**DEFER ROW (the genuine gap — file it, do not silently drop it):** **`D-MOTIF-CONFORMANCE-ENGINE-WIRING`**
(the worker already names it) — the **PAID** per-scene extract-diff chapter re-run **does not exist** (the
worker is arc-only). **Gate #3 — naturally-next-phase** (the chapter extract-diff engine is unbuilt; this
is a real unbuilt slice, not "blocked", but it is out of this slice's scope, which is GUI wiring).
Target: whenever that engine is scoped. **Until then chapter conformance is a read-only refresh and the
button MUST NOT pretend to spend.**

#### 3 — `regenerate-to-beat`: DELETE the route idea; re-point at the EXISTING scene-generate

> 🔴 **SECOND CONTRADICTION IN THIS SLICE.** The first cut said re-point it *"through the generic actions
> spine with descriptor `composition.generate` + reuse `CostConfirmCard`"* (as does
> `Q-30-TIER-W-GENERIC-SPINE`). **`Q-30-404-REGENERATE-TO-BEAT` — the dedicated decision — says use
> `compositionApi.generateAuto` directly and GATE ON MODEL, NOT ON COST.** It wins, and its grounds are
> concrete: **`POST /generate` is UNGATED today for ComposePanel too** — spec 28 **AN-8** says *a new
> confirmation convention here is a defect*, and the ungated spend is **already tracked as
> `D-COMPOSE-GENERATE-UNGATED`** and gets fixed **once, on the compose path, for both.** Bolting a
> bespoke estimate/confirm onto this one button would fork the convention.

- **DELETE** `motifApi.regenerateToBeat` (`motif/api.ts:299-304`) — the whole method + its doc comment.
- **DELETE** `useMotifBinding.regenerateScene` (`hooks/useMotifBinding.ts:64-68`) and remove it from the
  returned object (`:75`). **KEEP `commitAndGenerate` (`:70`)** — a different, working seam.
- **REWRITE** the mutation in `hooks/useConformanceTrace.ts:25-28`. Rename `regenerateToBeat` →
  **`regenerateScene`**. Widen the hook signature to
  `useConformanceTrace(projectId, chapterId, token, model: { modelRef?; modelKind?; modelName? })`.
  It calls the **EXISTING client**
  `compositionApi.generateAuto(projectId, { outlineNodeId: nodeId, modelSource: 'user_model', modelRef, operation: 'draft_scene', modelKind, modelName }, token)`
  (`frontend/src/features/composition/api.ts:398`), which POSTs `/v1/composition/works/{pid}/generate` —
  byte-matching `GenerateBody` (`engine.py:89-112`). 🔴 **Do NOT hand-roll an `apiJson` call** — reuse
  `generateAuto` (it already handles the worker-flag 202 submit+poll via `_resolveJob`).
- 🔴 **SHOW THE RESULT — do not `mutate()` + `invalidate()`.** `POST /generate` **returns the winner text;
  it does NOT write the chapter draft** (the only per-scene write is `persist_scene_prose`,
  `engine.py:1521`, and it is **derivative-promote-only**). So: hold the returned `AutoGeneration` in hook
  state keyed by `outline_node_id`; have `ConformanceSceneRow.tsx` render the winner inline as a **review
  ghost** with an **Accept** button calling a new `onAccept(nodeId, text)` prop; the panel wires `onAccept`
  to the **same editor write-back target `EditorPanel` already registers** (`registerEditorTarget` /
  the propose-edit ghost) — mirroring `ComposeView.accept` (`ComposeView.tsx:77`, buttons `:223-240`).
  **Invalidate the conformance query ONLY after the accept lands.** *(A `mutate()`+`invalidate()` with
  nothing rendered is an invisible button — `silent-success-is-a-bug`.)*
- 🔴 **GATE ON MODEL, NOT ON COST.** Disable Regenerate when `!modelRef`; show the "Pick a model"
  affordance + the X-1 **`AddModelCta`** — mirroring `ComposeView.tsx:63`
  (`canGenerate = !!sceneId && !!modelRef && !busy`) and `:204` (`data-testid="compose-need-model"`).

> **Why no route:** *"to-beat" is the PACKER LENS, not a route.* Once `W0-S6` (`gather_motif`) injects the
> scene's bound motif + target beat into `pack()`, **the existing scene-generate IS "regenerate to
> beat"** — and `engine.py:326` is already the production caller that will ride it. `regenerate-to-beat`
> appears **nowhere** in `services/**/*.py`; the route it was told to "mirror" (`persist_scene_prose`) is a
> divergence-promote **PERSIST** that **generates nothing.**

#### 4 — the poll (`Q-30-404-MOTIF-MINE-POLL` §3)

Add `getMotifJob(jobId, token)` to `frontend/src/features/composition/api.ts` beside `getJob` (`:420`),
then re-point **THREE** polls in `motif/api.ts` off `compositionApi.getJob`:
**`mineConfirm` (`:172`,`:175`) · `arcConformanceRunConfirm` (`:286`,`:289`) · `_resolveActionJob`
(`:335`,`:338`)**. All three poll a job **the caller itself just confirmed** ⇒ `created_by == caller`
always holds — *including* conformance, which is safe under the owner gate even though it has a real
`project_id`. **ONE path.** **Leave `compositionApi.getJob` in place** for the engine/critic jobs
(`CriticPanel.tsx:35`, `api.ts:59`). 🔴 **On 404 the panel renders an ERROR, never spins** (spec 34 AT-11).

#### Tests

| File | Test | Asserts |
|---|---|---|
| `motif/__tests__/api.test.ts` | 🔴 `the chapter conformance re-run spends NOTHING` | Clicking `[data-testid=conformance-rerun]` fires **exactly ONE** request — a **GET** to `/v1/composition/works/:pid/conformance?scope=chapter&chapter_id=…` — and **NO request to ANY `/actions/*` path.** |
| ″ | `conformanceRunEstimate / conformanceRunConfirm are GONE` | `expect((motifApi as any).conformanceRunEstimate).toBeUndefined()` (same for `Confirm`, and for `regenerateToBeat`). |
| ″ | 🔴 **the BUG-CLASS guard** | **No string literal in `motif/api.ts` matches `/actions\/[a-z_]+\/(estimate\|confirm)/`.** *Kills the whole per-action-route class §8.1 forbids — not just these two instances.* |
| ″ | `the mine poll targets /motif-jobs/{id}` | The mock records `GET /v1/composition/motif-jobs/…` and **never** `/v1/composition/jobs/…`. |
| `useConformanceTrace.test.ts` | `regenerateScene hits the scene-generate` | Request URL `/v1/composition/works/{pid}/generate`, body `{mode:'auto', outline_node_id, operation:'draft_scene'}`; **ZERO** requests to `regenerate-to-beat`. |
| `MotifMine.test.tsx:56` | 🔴 **the ANTI-MOCK guard** | **DELETE the `vi.spyOn(motifApi, 'mineConfirm')` mock for at least one case** and stub the **HTTP layer** instead. *§10 of plan 30: "the propose→confirm half ships **with a passing test** — **the test mocks the poll**." A mock encodes YOUR assumption (memory: `mocked-client-hides-server-side-default-filters`). Assert on the **URL the client actually built**.* |
| `tests/unit/test_motif_mcp.py` | `chapter scope mints NOTHING` | `composition_conformance_run(scope='chapter')` → `success:False`, **no `confirm_token`**. |

**DoD evidence:** `"npx vitest run src/features/composition/motif → all passed; pytest tests/unit/test_motif_mcp.py -q → passed; grep -rnE 'actions/[a-z_]+/(estimate|confirm)' frontend/src → 0 hits"` **+ a LIVE cross-service smoke (composition + gateway + FE): click ⛏ Mine in the browser, confirm the cost, and watch `/actions/confirm` return a real `job_id` (at HEAD it is a hard 500), then the poll return 200 and the panel reach a TERMINAL state.** *That is the whole point of the slice: **the unit suite was green while ⛏ Mine 500'd on every click in production.** ⚠ Assert the **CONFIRM**, not just the poll — a green poll over a row the writer can never produce is the `fixtures-can-seed-a-field-the-writer-never-sets` trap.*
**dependsOn:** `W0-BE1`, `W0-C1`, `W0-S6`

---

### `W0-S8` — X-6 · write spec 28's **AN-12.1 `resource_ref`** section (spec only — zero code)

**Status (verified).** `28_agent_native_studio.md` **already has** the PO-1 `## AN-12 AMENDED` section
(`:217-283`). What it does **not** have is the `resource_ref` contract — that is still only **OQ-8**
(`:615`), *"HOMED HERE. Deferred, tracked, gated… **A Phase-4 build without AN-12 is a spec
violation, not a shortcut.**"*

**Wave 2 (`arc-inspector` deep-link), Wave 3 (motif chips → editor) and Wave 7 (diagnostics rows →
the panel that owns the fix) all consume it. It is a hard prerequisite by spec 28's own words.**

> ⚖ **DECISION: `Q-30-X6-RESOURCE-REF`. 🔴 IT OVERRIDES THE FIRST CUT'S CONTRACT SKETCH ON TWO POINTS,
> AND THE SKETCH WAS *WRONG* — a builder following it literally would DROP kinds the code already
> produces.** It is a **RATIFICATION + DISAMBIGUATION of a shape that ALREADY SHIPS**, not a greenfield
> design. **Read the decision; write what it says.**

#### File

**EDIT** `docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md` — **do NOT fork it.** Add
**`## AN-12.1 — the `resource_ref` convention`**, placed **directly after the existing
`## AN-12 AMENDED (PO-1)` section (`:217`)**, and **update OQ-8's row (`:615`) to CLOSED → §AN-12.1.**

#### The five normative parts (write ALL five)

**(1) NAME — one name for one concept (DA-10). The concept is `resource_ref`. The shipped key is
`node_ref`. RENAME IT.** Zero FE consumers exist (`grep node_ref frontend/` → 0), and **`node_ref` is
ALREADY a third, unrelated thing in the same service** — `plan_overlay.py:110` aliases it to a **bare uuid
STRING** and `routers/plan_overlay.py:195` returns it as one. **Leaving it named `node_ref` ships one name
over three meanings.** ~11 non-test sites: `entity_references.py` (`:138 :161 :186 :212 :222`),
`agent_native.py` (`Diagnostic.node_ref` `:113` + serializer `:143`), `mcp/server.py`
(`:3998 :4025 :4047 :4099 :4125`).

**(2) 🔴 KIND = ONE TABLE = ONE ID-SPACE. This is the bug the section exists to kill, and it is LIVE.**
`{kind:'arc'}` is emitted **both** for a `structure_node.id` (`server.py:3998`) **and** for an
`outline_node` row (whose CHECK allows `'arc'` — `migrate.py:196`); `{kind:'chapter'}` **both** for a
**book-service** chapter id (`:4125`) **and** an `outline_node` id (`:4099`). **A resolver receiving
`{kind:'arc'|'chapter', id}` cannot tell WHICH TABLE the uuid lives in** ⇒ it deep-links to the wrong
object, or 404s. **So the closed set is keyed to the TABLE, never to the row's `kind` column:**

```
composition:   structure_node | outline_node | motif_application | canon_rule | narrative_thread
book-service:  chapter | scene
glossary:      glossary_entity

resource_ref := { kind: <the enum above>, id: uuid-string,
                  subkind?: string, title?: string|null, version?: number|null }
```

- **`subkind`** carries the row's **own** kind column (`'saga'|'arc'` for `structure_node`;
  `'arc'|'chapter'|'scene'|'beat'` for `outline_node`) so emitters keep semantics they'd otherwise lose.
- **`version`** is an optimistic-concurrency **HINT only**. **Absent means UNKNOWN, never 0**
  (the `fe-status-default-fallback` lesson).

**Emitter fixes (exact):** `server.py:3998` → `structure_node` + subkind `'arc'`; `:4025`/`:4047` →
`scene`; `:4099` → `outline_node` + subkind `n['kind']`; `:4125` → `chapter`.
`entity_references.py:138` → `structure_node` + subkind `r['kind']`; `:222` `_ref()` → `outline_node` +
subkind; `:161` → `motif_application`; `:186` → `canon_rule`; `:212` → `narrative_thread`.

> 🔴 **RECORD THE OVERRIDE OF OQ-8's SKETCH IN THE SPEC** (and of this plan's first cut, which copied it):
> `'structure'`→**`structure_node`**, `'outline'`→**`outline_node`**, `'thread'`→**`narrative_thread`**
> (the table **and** the shipped emitter both say `narrative_thread`) — **and the sketch's 5 kinds are
> INCOMPLETE: it omits `chapter` / `scene` / `glossary_entity`, which the shipped diagnostics ALREADY
> EMITS** and which G-MOTIF-BINDING (chips→editor) and the shipped PH18 canon deep-link both require.
> **A builder following the sketch literally would drop kinds the code already produces.**

**(3) THE FE RESOLVER — the genuinely missing half** (no such function exists). Spec **NEW FILE**
`frontend/src/features/studio/host/resourceRef.ts`, mirroring `studioLinks.ts:69` exactly (pure, host
injected, no React, unit-testable):
`resolveResourceRef(ref, ctx:{bookId}) → {kind:'studio'; effect:(host:StudioHost)=>void} | {kind:'unresolved'; reason:string}`.
🔴 **It NEVER silently no-ops** (Frontend-Tool Contract: **return the error**). Each arm reuses a **SHIPPED**
seam:

| kind | resolves to |
|---|---|
| `canon_rule` | `host.openPanel('quality-canon', {params:{bookId, focusRuleId:id}})` — the exact contract `PlanHubPanel.tsx:74` already **emits** and `useQualityCanon.ts:74` already **consumes** |
| `chapter` | `host.focusManuscriptUnit(id)` (`StudioHostProvider.tsx:53`) |
| `outline_node` / `structure_node` | `host.publish({type:'planFocusNode', nodeId:id})` + `openPanel('plan-hub')` (`types.ts:66/109` → `PlanHubPanel.tsx:121-127`) |
| `scene` | `openPanel('scene-inspector', {params:{sceneId:id}})` |
| `narrative_thread` | `openPanel('quality-promises', {params:{bookId, focusPromiseId:id}})` |
| `glossary_entity` | `openPanel('glossary', {params:{focusEntityId:id}})` |
| `motif_application` | `{kind:'unresolved', reason:'motif studio not built yet (spec 33 / Wave 3)'}` — **Wave 3's DoD flips this arm and its test** |

**Test:** `host/__tests__/resourceRef.test.ts` — one case **per kind** asserting the exact host call, plus
`'unresolved'` for `motif_application` **AND** for an **unknown kind** (never throws, never no-ops).

**(4) THE AGENT'S POINTING VERB.** Today the agent literally **cannot point at a rule or a plan node**.
Spec **ONE** new frontend tool **`ui_focus_resource(kind, id)`**: `kind` is a **closed set** ⇒ `enum` in
the schema **+ registered in `CLOSED_SET_ARGS`** + `WRITE_FRONTEND_CONTRACT=1 pytest` regen; the FE
resolver is `resolveResourceRef`. **NO new dock panel, NO catalog row, NO `ui_open_studio_panel` enum
change** — AN-12's architecture (the DOCK-2/DOCK-8 anti-fork clause, which PO-1 left standing) is honoured
**verbatim**.
🔴 **SEQUENCING:** its contract regen **must not run concurrently with `W0-S5`/`W0-S5b`/`W0-S5c`'s regens**
(`00B_EXECUTION_ROADMAP.md:203` — *never two concurrent regens*). It lands in **Wave 2**, after Wave 0's
three regens are committed.
*(PO-veto-able default, recorded: a **typed 2-arg verb**, not a free-form `resource_ref` bag bolted onto
`ui_open_studio_panel`. `{kind enum, id}` stays machine-checked on both sides. Note this is **orthogonal**
to X-12's `params` — `params` is a panel DEEP-LINK hint; `ui_focus_resource` is a typed OBJECT pointer.
Both ship. They are not the same concept.)*

**(5) SCOPE FENCE.** `resource_ref` is an **ADDRESS**, not a lock and not a mutation contract. Writes keep
going through the owning tool's own OCC / `base_version`. **State this explicitly** so a later agent does
not grow it into a write channel.

#### 🔴 BUILD PLACEMENT — read this, it is the whole point of the slice

**Wave 0 writes the SPEC SECTION ONLY. It changes ZERO code.**
Parts **(1)+(2)** — the BE rename + kind disambiguation + emitter fixes + updated MCP output-schema tests —
**build in WAVE 2**, alongside G-ARC-SPEC-CRUD. Parts **(3)+(4)** also **build in WAVE 2**, and are
**CONSUMED** by Wave 3 (G-MOTIF-BINDING) and Wave 7. *(Rationale: a schema with no consumer is the
stored-but-unread class. Write the contract; wire it when there is something to point at.)*

**DoD evidence:** `"28_agent_native_studio.md gains §AN-12.1 (8 table-keyed kinds + subkind + version-is-a-hint + the resolver map + ui_focus_resource + the scope fence); OQ-8 marked CLOSED → §AN-12.1; the OQ-8 sketch's 5-kind list is recorded as OVERRIDDEN with the reason; no code changed"` + the section explicitly names `chapter`, `scene` and `glossary_entity` (the three the sketch dropped).
**dependsOn:** —

---

### `W0-S9` — X-9 · **APPLY** the closed MCP sweep (2 doc edits + **2 code fixes**)

> ⚖ **DECISION: `Q-30-X9-UNAUDITED-MCP-SWEEPS`** (+ `Q-30-X9-WEBSEARCH-NAMESPACE`, filed under
> *"not a question"*). 🔴 **THE SWEEPS ARE ALREADY DONE — the decision ran them from the code.**
> **Wave 0 does NOT "run a sweep". It APPLIES the result.** And the result contains **two real code
> bugs the first cut of this plan never knew about.**

#### The closed result — write these numbers, do not re-derive them

| Claim | First cut / plan 30 | 🔴 **The truth** |
|---|---|---|
| provider-registry tool count | 14 | **13** (12 `settings_*` + 1 `web_search`). *(The file's own header comment at `:22` says "10 of the 12" — it is stale too.)* |
| catalog-service | "verify" | **2/2 GUI-covered, zero gaps.** `catalog_list_public_books` → `pages/BrowsePage.tsx:53`; `catalog_get_book` → `features/books/api.ts:535`. **Record as verified-covered; add nothing.** |
| §3.1 "MCP tools, other services" | `173 / 150 / 23` | **`188 total / 164 covered / 24 no-GUI`.** *(The "real total ≥ 189" hedge is itself wrong — it is 188.)* |
| the 24th no-GUI tool | — | **`web_search` — agent-native BY DESIGN, NOT a gap.** A human already has a browser. Classify it with the audit's existing "3 agent-native reads". |

#### 🔴 The `web_search` namespacing "violation" is **REFUTED — no action, and NOT a "won't-fix"**

> 🔴 **CONTRADICTION FOLDED. The first cut recorded it as a *conscious won't-fix* (defer gate #5) with a
> defer row `D-X9-WEBSEARCH-UNPREFIXED`. THE DECISION SAYS: it is not a violation at all — the premise is
> factually wrong, so there is nothing to "won't-fix".** `ai-gateway/src/config/config.ts:110-128`
> declares **`settings: ['web_']` in `EXTRA_PREFIX_MAP`**, and `test/catalog.spec.ts:161` **pins that
> against the REAL config** (not a fixture) ⇒ **the C-GW prefix gate does not drop it.** It **shadows
> nothing**: glossary's tool is separately named `glossary_web_search`
> (`glossary-service/internal/api/web_search_tool.go:40`). The `external-system-mcp-must-be-namespaced`
> law governs **EXTERNALLY FEDERATED** servers, where an unprefixed tool shadows a first-party one;
> `web_search` is **first-party, registered by exactly ONE provider**, resolved through a single
> `toolToProvider` map. **The law is precisely what guarantees no external tool can collide with it.**
> ⇒ **DELETE the defer row (§8). STRIKE the bullet from the spec.** Record the exception where an auditor
> will look, so it is not re-opened a **third** time: **one row in `docs/standards/README.md`'s index** —
> *"Exception: first-party universal `web_search` is intentionally unprefixed; allowed via
> `EXTRA_PREFIX_MAP.settings=['web_']`; pinned by `ai-gateway/test/catalog.spec.ts`. See
> `provider-registry-service/internal/api/mcp_web_search_tool.go:3-18`."*

#### Doc edits

**EDIT** `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`:
- **§3.1** — `173/150/23` → **`188/164/24`**.
- **§3.4** — **DELETE the section entirely**, replacing it with a one-line *"closed by X-9"* note pointing
  at this slice. *(It is the "⚠ Known holes / UNVERIFIED" block; its whole content is now decided.)*
- **The X-9 row (`:342`)** — strike *"Also decide the unprefixed `web_search` namespacing violation."*
  X-9 reduces to the two sweeps, **and both are now closed.**

#### 🔴 CODE FIX 1 — **`G-PROFILE-FIELDS`**: an agent-only write surface (*"the spot-check was luck"* — it was)

`settings_update_profile` accepts **`locale` / `avatar_url` / `bio` / `languages`**
(`provider-registry-service/internal/api/mcp_server.go:441-445`) and **auth-service validates + persists
all of them** (`auth-service/internal/api/handlers.go:366-384`) — but the FE payload type is literally
**`{ display_name?: string }`** (`frontend/src/features/settings/api.ts:24`) and `AccountTab.tsx:65` only
ever sends `display_name` — **while `frontend/src/features/profile/ProfileHeader.tsx:32-62` RENDERS
avatar/bio/languages that no human can set.** *(That is a GG-1 breach inside the very plan that enforces
GG-1: the agent can write four fields the user cannot.)*

**FIX IN WAVE 0 — it is ~40 lines and it clears no defer gate:**
- `settings/api.ts:24` — widen `accountApi.patchProfile`'s payload type to
  `{ display_name?: string; locale?: string; avatar_url?: string; bio?: string; languages?: string[] }`.
- `AccountTab.tsx` — under the existing display_name field (~`:141`) add: an **avatar_url** text input, a
  **bio** `<textarea maxLength={1000}>`, a **languages** editor **reusing
  `frontend/src/features/settings/TagEditor.tsx`** (do not build a second one), and a **locale** `<select>`.
  Send **all five** in the `patchProfile` call at `:65`, and keep the dirty-check at `:216` covering
  **every** field.
- **TEST** — new `frontend/src/features/settings/__tests__/AccountTab.profile.test.tsx`: edit **bio** + add
  a **language** + set **avatar_url**, click Save, **assert the fetch body contains all four keys.**
  *(Guards the exact bug: a save that silently drops the fields.)*

#### 🔴 CODE FIX 2 — `settings_model_set_default` **under-advertises itself to the LLM**

Its Description **and** jsonschema say **"(rerank or embedding)"** (`mcp_server.go:82`, `:135`, `:650`)
while the runtime whitelist `defaultModelCapabilities` accepts **rerank | embedding | chat | planner**
(`default_models_handler.go:20-30`) **and the GUI already exposes all four** (`settings/api.ts:91-96`).
**The agent only ever sees the description — so it will NEVER set a chat or planner default.**

- Change **all three** strings to **"rerank, embedding, chat, or planner"**, and mirror the wording in
  **`settings_get_defaults`'s Description (`:82`)**.
- **TEST** in `mcp_server_test.go`: `settings_model_set_default` with `capability:"planner"` **succeeds**,
  **AND** the registered tool's schema/description **mentions all four** capabilities.
  *(A string-drift guard — the whitelist and the description live in different files.)*

**DoD evidence:** `"plan 30 §3.1 → 188/164/24; §3.4 DELETED (closed by X-9); the web_search bullet STRUCK and the exception recorded in docs/standards/README.md. go test ./internal/api/... (provider-registry) → passed incl. the 4-capability drift guard. npx vitest run src/features/settings → AccountTab.profile.test.tsx passed (bio + languages + avatar_url + locale all in the PATCH body)."`
**dependsOn:** —

---

### `W0-S10` — X-8 · doc hygiene (every one of these is actively misleading the next agent RIGHT NOW)

> ⚖ **DECISIONS: `Q-30-X8-DOC-HYGIENE` · `Q-30-X11-DANGLING-REF` · `Q-30-DRAFT-DESTRUCTIVE-TOKEN` ·
> `Q-30-SEC11-VS-SEC0-CONTRADICTION`.** Pure-docs (+ **one** new lint script). **No product code changes.**

> 🔴 **CONTRADICTION FOLDED — TWO of the first cut's five items were ALREADY FIXED on 2026-07-12, and
> re-doing them would CHURN CORRECT DOCS. And its RENUMBER MAPPING FOR 15 WAS INVERTED.**

#### ⛔ SKIP — verify, do **not** redo (`Q-30-X8-DOC-HYGIENE`)

- ~~*"`00_OVERVIEW.md`'s component index + Debt stack are stale"*~~ — **ALREADY REFRESHED.**
  `00_OVERVIEW.md:74-79` carries the *"STATUS SOURCE OF TRUTH (2026-07-12) … When these disagree, §4 wins"*
  banner; rows 02/03/04/07/08/09 now read 🟡/✅ with code citations; the Debt stack (`:149-158`) was rebuilt
  to 3 live rows with a *"5 of the original 6 were stale"* note. **Confirm and move on.**
- ~~*"00C Q-2 (Agent Mode 0% frontend) is FALSE — move it to cleared"*~~ — **ALREADY CLEARED.**
  `00C_POST_ARCHITECTURE_QUEUE.md:34` = *"~~Agent Mode / Mission Control build~~ — CLEARED 2026-07-12 (this
  row was FALSE)"*, write-up at `:54-59`. **Confirm and move on.**

#### ✅ DO — 6 open items

**1 · RENUMBER.** 🔴 **The mapping is NOT arbitrary and the first cut had 15 BACKWARDS.**
Rule: **`a` = the spec that already owns that number in the `00_OVERVIEW` row; `b` = the later add-on that
collided.** Every bare-number prose ref **on disk already means it** (`#14` = KG at `00_OVERVIEW.md:104`,
`21_plan_hub.md:36/196/218`, `20_agent_mode.md:43`; **`#15` = WIKI** at `00_OVERVIEW.md:105` and
`20_agent_mode.md:65` — *"same params-retargeting pattern as **wiki-editor, #15**"*). **This mapping means
ZERO prose rewrites; the inverse mapping would SILENTLY INVERT 6 EXISTING REFERENCES.**

```
git mv  docs/specs/2026-07-01-writing-studio/14_kg_panels.md        14a_kg_panels.md
git mv  docs/specs/2026-07-01-writing-studio/14_utility_panels.md   14b_utility_panels.md
git mv  docs/specs/2026-07-01-writing-studio/15_wiki_panels.md      15a_wiki_panels.md     # ← WIKI is 15a
git mv  docs/specs/2026-07-01-writing-studio/15_chapter_browser.md  15b_chapter_browser.md # ← BROWSER is 15b
```

Then update **all 21 link occurrences** (every cross-ref is a markdown link **by filename**, so a mechanical
path rewrite is complete and safe): `docs/plans/2026-07-04-chapter-browser-plan.md:3,57` ·
`docs/plans/2026-07-04-utility-panels-fanout.md:3,9,45,70` ·
`docs/sessions/SESSION_HANDOFF.md:1971,2215,2218,2246` · `00_OVERVIEW.md:104,105` ·
`12_json_document_standard.md:117` · `15b_chapter_browser.md:4` *(its own "same shape as
14_utility_panels.md" prose workaround — the very one X-8 calls out)* · `15a_wiki_panels.md:11` ·
`16_chapter_editor_parity_and_retirement.md:143` · `22_scene_model_and_crud.md:238,272` ·
`23_book_architecture.md:302,493` · `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:219` *(rewrite the X-8 bullet to
record the mapping **as DONE + the a/b rationale**, so no later agent re-litigates it)*.
**Also bump each file's H1:** `# 14 · Knowledge/KG…` → `# 14a · …`; `# 14 · Utility Panels…` → `# 14b · …`;
`# 15 — Wiki dockable migration` → `# 15a — …`; `# 15 · Chapter Browser…` → `# 15b · …`.

**2 · FIX 29's H1.** `29_translation_repair.md:1` — `# 24 — Translation surfaces: defect audit + repair spec`
→ **`# 29 — …`**. (29 is the file's real number; **24 is now Plan Hub v2**, so the current H1 actively collides.)

**3 · UN-STALE spec 20's header.** `20_agent_mode.md:3` — replace
*"📐 CLARIFY complete, ready for DESIGN/PLAN · not yet built"* with the verified truth: **"✅ SHIPPED — the
`agent-mode` panel is in `catalog.ts` AND in the `ui_open_studio_panel` enum (verified by 30 §4,
2026-07-12). Unshipped tail: no Lane-B effect handler for `composition_authoring_run_*` (→ **fixed by
`W0-S4`**), a now-false comment at `useStudioEffectReconciler.ts:10` (→ **`W0-S4`**), a missing
`guideBodyKey` (→ **`W0-S2`**), and NO `compaction_failed` breaker for its L3/L4 autonomous runs (07S §3/§10
makes it MANDATORY — P1 Deferred row)."** *(This matches what `00_OVERVIEW.md:109` and `00C:34` already say,
so the three files stop contradicting each other.)*

**4 · 🆕 FOUND GAP — close it in the same slice.** **14b (utility panels) and 15b (chapter browser) have NO
ROW AT ALL in the `00_OVERVIEW` component index** (it goes 13 → 14 KG → 15 Wiki → 16). **Two shipped specs
are invisible to the index plan 30 just declared the status SSOT.** Add a row for each after its `a` sibling
— and **re-check the status against `catalog.ts` before writing it. Do NOT copy a status from memory** (the
exact rule `00_OVERVIEW.md:79` lays down).

**5 · 🆕 X-11 — the dangling ref** (`Q-30-X11-DANGLING-REF` half 1). `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:237`
— the G-CANON-RULE-CRUD row's **"(+ one SMALL: no `restore` — see X-11)"** → **"see BE-11"**. **No X-11
exists** (§8 runs X-1..X-10, X-12, X-13) and `:305` already names the real item. *(The route itself is
**`W0-BE2`**.)*

**6 · 🆕 `30_…PLAN.md` §11 is STALE PROSE and all three of its "blocking" decisions are made**
(`Q-30-SEC11-VS-SEC0-CONTRADICTION`). **§0 SEALED wins.** Delete §11 item 1 (`:772-782`) and replace with a
block that records: **(a) X-5 → PO-3** (RETIRE — and note the caveat is void, `W0-S5`);
**(a′) X-12 → ANSWERED: `ui_open_studio_panel` GAINS an OPTIONAL `params` (`W0-S5b`)** — ⚠ **note carefully:
`Q-30-SEC11-VS-SEC0-CONTRADICTION`'s own (a′) says "do NOT add a `params` arg". THE DEDICATED DECISION
`Q-30-X12-PARAMS-ARG` OVERRULES IT** (§10 #9 — the two decisions contradict each other, and the dedicated
one has the code + the sealed-PO-3-needs-it argument). **Write X-12's answer, not §11's.**
**(b) AN-12 → PO-1** (amended; already landed at `28:217-283`). **(c) Track C P-5 → PO-2**
(workflows/8c = Track C's; **8b stays in this plan**). Also update the §11 preamble ordering.

**7 · 🆕 THE 5th DESTRUCTIVE-TOKEN DRIFT** (`Q-30-DRAFT-DESTRUCTIVE-TOKEN` — **FIX-NOW: 2 files, root cause
clear; a defer row would cost more than the fix**). Plan 30 §8.3 claims the red *"drifted FOUR ways"* and
*"all 24 files are now normalized"* — **both wrong. The audit grepped token NAMES, so it missed a fifth
drift wearing a THIRD name.**
- **TEMPLATE:** `design-drafts/screens/studio/screen-issues-feed.html:148` (`--destructive: #d9584f;
  --destructive-muted: #3a1f1c;`). 🔴 **Do NOT copy `screen-studio-raw-editor.html` or
  `screen-studio-agent-gui-bridge.html` — both carry the surviving drift.**
- **FIX `screen-studio-raw-editor.html`:** `:28` — `--error: #e85a5a; --error-muted: #3d1a1a;` →
  `--destructive: #d9584f; --destructive-muted: #3a1f1c;`. Rewrite the **7** usages at `:65,97,98,108,109,120,128`.
  At `:120` also replace the raw `rgba(232,90,90,.18)` with `rgba(217,88,79,.18)`.
- **FIX `screen-studio-agent-gui-bridge.html`:** add the two tokens to `:root`; `:74`
  `.forbidden strong { color: #e85a5a; }` → `color: var(--destructive);`.
- **SECONDARY (same file family):** `screen-studio-agent-hooks.html:23` defines `--warn: #e8b87e` where canon
  is `--warning: #e8a832`. Normalize.
- **AMEND plan 30 §8.3 (`:673-689`):** add the **fifth** row; restate as *"18 of 24 define the canon
  destructive token; the other 6 have no destructive affordance and need none. There is no `--danger` and no
  `--error` alias."*
- 🔴 **GUARD** (a prose checklist did **not** stop this drift — `checklist-is-self-report-enforce-by-tests`):
  **NEW `scripts/design-draft-token-lint.py`** — fail if any `design-drafts/screens/studio/*.html` contains
  (a) a destructive-alias custom property other than `--destructive`/`--destructive-muted` (i.e. `--danger*`,
  `--error*`, `--warn` ≠ `--warning`), or (b) any red hex/rgba outside `{#d9584f, #3a1f1c}` in a color-ish
  position. **Wire it into the same pre-commit path as `scripts/ai-provider-gate.py`.**
  🔴 **Grep by CONCEPT (the hex), not by the token NAME — that is the miss this bug is made of.**

**DoD evidence:** `"git mv ×4 (15a=WIKI, 15b=BROWSER); grep -rn '14_kg_panels|14_utility_panels|15_chapter_browser|15_wiki_panels' --include=*.md docs/ → 0 hits; grep -rn 'not yet built' 20_agent_mode.md → 0; 29's H1 says 29; 00_OVERVIEW gains 14b + 15b rows; the 'see X-11' ref now says BE-11; plan 30 §11 item 1 replaced; python scripts/design-draft-token-lint.py → 0 violations (it REDS at HEAD on 2 files — paste both runs)"` + the pasted greps.
**dependsOn:** —

---

### `W0-S11` — X-10 · AN-C2, the discovery scent (**sequence LAST**)

**The bug (verified).** Spec 28's 3 agent-native tools shipped, and **the model was never told they
exist.** `grep "package_tree\|composition_diagnostics"` against `stream_service.py`'s
`book_context_note` (`:3751-3765`) → **0 hits**. AN-11's own risk row calls "shipped but never called"
a **FAIL**.

> ⚖ **DECISIONS: `Q-30-X10-DISCOVERY-SCENT` · `Q-30-TRACKC-UNCOMMITTED-FILES`.** Both **DISCHARGE the
> Track-C hold** (`git status` is clean for all four files; **HEAD `9262ed53e` IS Track C's D8**; Track C's
> next run — `docs/specs/2026-07-13-track-c-clear.md` — **does not touch `stream_service.py`**: grep = 0
> hits). **Plan 30 §9's "DO NOT TOUCH" row is STALE. X-10 runs in Wave 0's ordinary XS batch — do NOT
> hold it.** *(Still: **RE-VERIFY at build time** — pre-flight step 4. Three tracks share this checkout.
> If it has re-dirtied: **DEFER `D-X10-ANC2-SCENT`, do not stop.**)*

> 🔴 **CONTRADICTION FOLDED — the first cut appended a string INLINE inside a ~500-line assembly function.
> `Q-30-X10-DISCOVERY-SCENT` says EXTRACT A TESTABLE HELPER first** — *"the enclosing assembly fn is ~500
> lines and **cannot be called from a unit test**"*. **A test that cannot reach the code is not a test.**

#### The change — 2 steps, one file

**Step 1 — hoist the tools-live predicate.** It is computed inline at `:3723` for `group_directory_block`.
Give it a name so the scent can reuse it **verbatim**:

```python
_tools_live = stream_format == "agui" and not disable_tools and kctx.tool_calling_enabled
if _tools_live:
    group_directory_block = group_directory_text()
```

**Step 2 — extract the note into a module-level PURE helper**, next to the other prompt-text helpers:

```python
def build_book_context_note(book_id, chapter_id, project_id, tools_live: bool) -> str | None:
    """AN-C2 (28 §AN-11) — the DISCOVERY SCENT. The three agent-native reads SHIPPED and the model was
    never told they exist; AN-11's own risk row calls "shipped but never called" a FAIL. AN-9's
    pull-not-push law: do NOT hot-seed the schemas — NAME the tools so the model can pull them from the
    registry when the question calls for them.

    Body = the EXISTING lines 3750-3765 verbatim ("You are working inside book_id=…", the chapter
    clause, the CTX-1 project_id clause, "Use these exact ids… never pass a placeholder."), PLUS —
    appended ONLY when tools_live — the scent sentence below.
    """
    ...
    if tools_live:
        note += (
            " To orient yourself in this book, call composition_package_tree (the book at a glance)"
            " or composition_diagnostics (what is currently wrong with it) instead of stitching"
            " several reads together; composition_find_references answers where one entity is used."
        )
```

Call site becomes:
`book_context_note = build_book_context_note(_ctx_book_id, _ctx_chapter_id, _ctx_project_id, _tools_live)`.

All three names are **verified registered MCP tools**: `composition_package_tree` (`server.py:3712`),
`composition_find_references` (`:3867`), `composition_diagnostics` (`:3935`).

#### The three decisions inside this slice (veto-able defaults — **recorded, not re-derived**)

1. 🔴 **Gated on `_tools_live`, NOT on `_studio`.** Spec 28 AN-9/C2 says *"the **studio**
   `book_context_note`"* — but the three tools are **book-scoped** and are reached through
   `find_tools(group=…)` discovery, which is live on **any** agui tool-calling turn: a book-scoped
   non-studio turn has exactly the same access. Cost is **~25 tokens, and only when tools are on.**
   **Naming tools on a tools-OFF turn is the real hazard** — and a `_studio`-only gate would still allow
   it. `_tools_live` closes it.
2. **All THREE tools named, not two.** X-10 names only package_tree/diagnostics. `find_references` is
   **+8 tokens** and is the third of the same shipped trio (AN-2/3/4) with the identical "shipped but
   never called" risk.
3. **No per-turn fetch. Static text only.** AN-9's measured-budget rule and OQ-2 (ratified **NO** on an
   auto `package_tree` call) both hold.

⚠ **`composition_package_tree` gets NO human surface — and that is CORRECT** (PO-1 / spec 28's amended
AN-12 point 5: a **conscious won't-fix**). Naming it in the scent is **not** a promise of a GUI.
**Do not open a gap row for it.**

#### BUDGET — 🔴 **verified: NOTHING breaks. Do not "fix" a budget test.**

`book_note` is **already a first-class `BREAKDOWN_CATEGORIES` key** (`token_budget.py:100`) and is counted
at `stream_service.py:4091`. **No test asserts a ceiling on it** — `test_token_budget.py:165`'s
`"book_note": 20` is a **synthetic fixture**, not an assertion about the real string. The ~25 added tokens
are automatically measured and surfaced in the Inspector ⇒ **an always-on block that is COUNTED ⇒ no
Context-Budget-Law violation.** *(If a budget test does red, that is new information — update the constant,
**never trim the sentence**: memory `test-budget-constants-drift-as-baseline-overhead-grows`.)*

#### Test — **NEW FILE** `services/chat-service/tests/test_book_context_note.py` (4 asserts)

| Test | Asserts |
|---|---|
| `test_tools_live_names_all_three_agent_native_reads` | `tools_live=True` + `book_id` ⇒ the note contains **all** of `composition_package_tree`, `composition_diagnostics`, `composition_find_references`. |
| 🔴 `test_tools_off_names_NONE_of_them` | `tools_live=False` ⇒ the note contains **none** of the three — **but still contains `book_id=`.** *(We do not name tools the model cannot call.)* |
| `test_no_book_no_note` | `book_id=None` ⇒ returns **`None`**. **We do not pay the tokens on a bookless turn.** |
| `test_the_ctx1_clause_survives_the_extraction` | `project_id` present ⇒ the CTX-1 *"a book_id is NOT a project_id"* clause **still lands**. **The regression guard on the extraction itself.** |

Also extend the existing `test_stream_service_story04.py::TestStudioSurface` assertions (`:175`, `:263`).

**DoD evidence:** `"pytest services/chat-service/tests -q -n auto --dist loadgroup → ≥ baseline, 0 failed (4 new in test_book_context_note.py); grep -c 'composition_diagnostics' stream_service.py → 1"` **+ a LIVE LLM smoke:** ask the studio agent *"what's wrong with my book?"* and assert it calls **`composition_diagnostics`** instead of foraging through per-domain list tools. *(Use a local lm_studio model — $0. Test account: `claude-test@loreweave.dev`.)*
**dependsOn:** — *(sequence last; gated on the Track-C re-verify)*

---

### `W0-S12` — 🆕 **X-GG4-GATE · the legacy-editor retirement gate, as a MACHINE CHECK** 🔴 **+ the LEGACY_SUBTAB_HOME ledger**

> ⚖ **DECISION: `Q-30-GG4-RETIREMENT-GATE`** — *"CONFIRM the constraint **AND make it mechanical NOW** —
> it is a buildable Wave-0 slice, **not a note**."* XS, FE-only, no backend.
>
> 🔴 **WHY THIS IS WAVE 0's AND NOT SOMEONE ELSE'S.** GG-4 says the legacy `ChapterEditorPage` stays
> mounted until every feature that lives **only** there has a Studio home. Today that constraint is
> **prose in a spec** — *nothing reds.* Meanwhile **seven legacy sub-tabs have no home in ANY wave plan**,
> and two of them are **FALSE-HOMED in Wave 6's map**, which means **the gate would go GREEN on a feature
> being deleted.** **Wave 0 owns the gate test ⇒ Wave 0 owns the ledger that gate reads.** The ledger is
> the artifact that makes the homes real; the waves that *build* the panels are named in it.

#### 12a — the gate test

**CREATE** `frontend/src/features/studio/panels/__tests__/legacyEditorRetirementGate.test.ts`, cloning the
`readFileSync`-over-source pattern of its sibling **`dockablePanelHygiene.test.ts:1-31`** (proof this is a
~40-line file, not new infrastructure).

```ts
const APP     = readFileSync(resolve(__dirname, '../../../../App.tsx'), 'utf-8');
const CATALOG = readFileSync(resolve(__dirname, '../catalog.ts'), 'utf-8');
const LEGACY_ROUTE = '/books/:bookId/chapters/:chapterId/edit';

// GG-4 — every panel that PORTS a feature living ONLY on ChapterEditorPage / CompositionPanel.
// 🔴 THIS LIST IS THE LEDGER (12b). Adding an id here KEEPS THE GATE CLOSED until that id exists
//    in catalog.ts. Removing an id is the retirement act for that feature and requires a
//    DELETE_ON_PURPOSE row in plan 30 §7's "Consciously OUT OF SCOPE" table.
const PORTED_PANELS = [
  // ── Wave 1 ──
  'quality-canon-rules', 'quality-corrections', 'quality-heal', 'progress',
  // ── Wave 3 ──
  'motif-library',
  // ── Wave 4 ──
  'arc-templates',
  // ── Wave 6 ──
  'style-voice', 'reference-shelf', 'divergence',
  'scene-compose',      // 🆕 ComposeView            — see 12b
  'chapter-assemble',   // 🆕 ChapterAssembleView    — see 12b
  // ── Wave 8 ──
  'cast',               // 🆕 CastCodexPanel         — see 12b
  'character-arc',      // 🆕 CharacterArcView       — see 12b
  'place-graph',        // 🆕 WorldMap               — see 12b
  'canon-growth',       // 🆕 FlywheelPanel          — see 12b
];

it('GG-4: the legacy chapter editor stays mounted until every port lands', () => {
  const missing = PORTED_PANELS.filter((id) => !CATALOG.includes(`id: '${id}'`));
  if (missing.length === 0) return;              // gate OPEN — retirement is now *permitted*
  expect(APP, `GG-4 VIOLATION: you removed the legacy route while these ports are still missing from ` +
    `catalog.ts: ${missing.join(', ')}. Deleting ChapterEditorPage/CompositionPanel now DELETES SHIPPED ` +
    `FEATURES. See spec 30 §GG-4 + the LEGACY_SUBTAB_HOME ledger in plan wave-0 §W0-S12.`)
    .toContain(LEGACY_ROUTE);
  expect(existsSync(resolve(__dirname, '../../../../pages/ChapterEditorPage.tsx'))).toBe(true);
});

// Guards a silent list-trim — the way a lazy agent would "pass" this gate.
it('the ledger has not been trimmed', () => { expect(PORTED_PANELS.length).toBe(15); });
```

**File header (write it):** *deleting THIS TEST is itself the retirement act and requires the spec-16 M1
close-out row.*
🔴 **Verify by EFFECT:** `npx vitest run legacyEditorRetirementGate` must go **RED** when you locally comment
out `App.tsx:134`, and **green** when restored. **Paste both outputs.**

**The gate is SELF-EXPIRING and PERMISSIVE, not forcing.** When every id is in `catalog.ts` the test
early-returns and retirement is **unlocked** — it does **not** then demand the deletion. *(Default, PO may
veto: retirement stays a deliberately-scoped slice. `ChapterEditorPage.tsx:9-10` already records "spec 16
Phase 4b, 2026-07-05: **kept indefinitely, not deleted**", and spec 16's M6 — the mobile shell, which the
page owns and dockview has no narrow-viewport pattern for — is an unresolved product call.)*

#### 12b — 🔴 **THE `LEGACY_SUBTAB_HOME` LEDGER — the 7 homeless sub-tabs, each given a wave IN WRITING**

> **The retirement gate can only protect what it can name.** These seven live **only** on the legacy
> surface. **Wave 0 names their homes; the named wave BUILDS them.** Two rows exist because **Wave 6's
> current map FALSE-HOMES them — the single most dangerous thing in the whole gate, because a wrong map
> row makes the machine check GO GREEN ON A DELETED FEATURE.**

| Legacy sub-tab | What it actually is | 🏠 **HOME (binding)** | Panel id |
|---|---|---|---|
| **compose** | `ComposeView` — the scene-scoped draft loop: guide box → Generate → FE-local ghost stream (**never autosaved**) → `CandidatesView` (diverge→converge rerank) → Accept (`onAccept` → editor + provenance mark) → inline critic → `useCorrection` human-gate capture. 🔴 **It also carries the ONLY adapt-from-source affordance for derivative Works** (`useAdaptFromSource`, `canAdapt`/`adaptSourceEmpty`) — **that exists on NO other surface.** | **WAVE 6** — a 4th panel beside style-voice / reference-shelf / divergence. **Mount `ComposeView` as a LEAF** (Wave 6's own **EC-6**: NEVER `<CompositionPanel soloPanel=…>` — ~20 hooks fire and `WorkspaceLayoutContext` is missing). Inputs: `projectId` ← `useQualityWork`/`useWork`; `sceneId` ← the studio bus (`host/types.ts:36-37` **already carries `activeSceneId`**); `modelRef` ← the shared ModelPicker; `onAccept` → `ManuscriptUnitProvider.applyProposedEdit(text, ProvenanceAttrs)`. **Wave 6's §6 registration delta moves +3 → +4** (assert `N_before+4` three-way, **never a literal**). 🔴 **The Chat-based `compose` panel is NOT a substitute.** If PO rules ComposeView superseded by the chat, **that ruling MUST also name a home for `useAdaptFromSource`** — retirement deletes it outright. | `scene-compose` |
| **assemble** | `ChapterAssembleView` — chapter-granularity generation: single-pass (B2) **or** stitch (B3), gated on `scenesAllDone`; the `assembly_mode` setter; `CanonGatePanel` result; an editable preview generated with **`persist=false`** (never clobbers the editor draft); Accept → `onAccept`; **`useCorrection` human-gate capture** → `composition.generation_corrected` → learning-service. | **WAVE 6** — leaf-reuse of `ChapterAssembleView` (**EC-6 applies**). Inputs: `projectId` + `bookId` + `chapterId` from the manuscript hoist's active chapter using **the ONE convention spec 31 QC-10 locks** (`QualityCriticPanel.tsx:33-59`'s picker, **incl. the `chaptersTruncated` no-silent-cap notice**); `work.settings` for `assembly_mode`; `scenesAllDone` ← `useChapterScenes`; `onAccept` → `applyProposedEdit`. **Registration +1.** 🔴 **This is ALSO the SECOND producer spec 30's `G-CORRECTION-FLYWHEEL` row names** — that row says corrections are *"written only from the legacy ComposeView"*, which **understates it: `ChapterAssembleView` calls `useCorrection` too. Wave 1's capture seam is INCOMPLETE while this is homeless.** *(Agent Mode / `authoringRuns` is **not** a substitute — it is an autonomous multi-chapter runner, not the interactive stitch-with-human-gate surface.)* | `chapter-assemble` |
| **cast** | `CastCodexPanel` — the book's cast (characters / locations / factions / concepts) as a docked codex, **GROUPED BY KIND**, searchable, each row showing its **SPOILER-SAFE current story-state** (joins knowledge entities ↔ `EntityStatusEntry`). It is the **deep-link TARGET** of FlywheelPanel's entity chips, WorldMap's *"open this place in the codex"*, and the Cast→Arc launcher. | **WAVE 8** — 🔴 **the closest existing panel, `kg-entities`, is NOT this**: it is a thin wrapper over knowledge's `EntitiesTab` — a **flat, cross-project entity LIST** with no kind-grouping and **no spoiler-safe story-state join.** Leaf-reuse `CastCodexPanel` (props: `bookId`, `chapterId` from the hoist, `token`; **lift `search` into `params`** so the flywheel/worldmap deep-links still land; `onViewArc` → `host.openPanel('character-arc', {entityId})`). Wave 8 already owns the KG panels and is already editing `EntitiesTab`/`EntityDetailPanel`/`ProjectGraphView` ⇒ **the files are in its blast radius.** `category: 'storyBible'` (Wave 8's G3 confirms `storyBible` is already in `CATEGORY_ORDER` — **no X-2 dependency**). *(If PO prefers Wave 2 because of the arc deep-link, that is defensible — **but it must be written into SOME wave; today it is in none.**)* | `cast` |
| **arc** | `CharacterArcView` — **ONE character's** events in `event_order` on a compact arc, **spoiler-cut at the current chapter**, with an active→gone state band and the current 1-hop relations strip (`ArcRelationsStrip`). Launched with a character preselected from the Cast codex (`arcEntityId` is lifted into `CompositionPanel` for exactly that hand-off). | 🔴 **WAVE 6's MAP FALSE-HOMES THIS: `arc: 'arc-templates'` (wave-6 `:1457`). WRONG.** `arc-templates` (Wave 4) is the structure-**TEMPLATE** library + 拆文 deconstruct; `arc-inspector` (Wave 2) is G-ARC-SPEC-CRUD — the narrative arc **SPEC tree** over book/composition arc rows. **Neither is a character's event arc over the knowledge graph.** **ACTION: (a) FIX the row in wave-6's `LEGACY_SUBTAB_HOME`** — as written **the machine gate goes GREEN on a deleted feature**; **(b) HOME IT IN WAVE 8**, next to `cast` (same knowledge-service data, same deep-link pair). Leaf-reuse `CharacterArcView`; **`entityId` arrives via `params`** (⇒ **W0-S5b's X-12 `params` arg is what makes this reachable by the agent at all**) so `cast` can `host.openPanel('character-arc', {entityId})` — today that hand-off is `onViewArc`/`setArcEntityId` **inside `CompositionPanel`** and **dies with it.** Registration +1. | `character-arc` |
| **worldmap** | `WorldMap` — the book's **PLACES** (location entities) and their location↔location connections as a graph; **drag to arrange (persisted server-side in `work.settings.world_map`, per-Work, cross-device)**; an optional **backdrop image**; *"+ add place"* / *"link places"* **AUTHOR the knowledge graph** (`PLACE_LINK_PREDICATES`); clicking a place opens it in the Cast codex. | 🔴 **THE MOST DANGEROUS ROW — a CIRCULAR DEFER masquerading as a home.** Spec 38 OQ-9 says *"This wave does NOT port `WorldMap.tsx`… it belongs to plan 30's **Wave 6** editor-craft ports"* — **AND WAVE 6 DOES NOT CONTAIN IT.** Wave 8 ports only the **CAPABILITY** (`useWorldMap.ts:129,134` is the frontend's **only** human caller of `knowledgeApi.createEntity`/`createRelation` → W8-02/03 give the kg panels entity-create + relation-create), which is why Wave 8 §1.3 claims it *"unblocks GG-4"* — **TRUE FOR THE WRITE LEG ONLY.** The place-graph **VIEW** (backdrop image, persisted spatial arrangement, place↔place link predicates) **has no home.** And **spec 30 §10 REFUTES conflating it with Wave 8's `world-map` panel**: that one is **book-service's** `world_maps`/`map_markers`/`map_regions`; `useWorldMap` reads **`work.settings.world_map`** — *"entirely unrelated"*. 🔒 **ADJUDICATED — PO decision `D-7` (§0-PO), sealed 2026-07-13: option (i). HOME IT IN WAVE 8** as `place-graph`, **leaf-reusing `WorldMap.tsx`** (Wave 8 is already in these files). **This row is now BINDING, not a proposal** — Wave 8's slice board must carry a `place-graph` slice, and Wave 8's registration delta stays **+2 → +6**. ⚠ **D-7 restates the trap: `place-graph` is NOT Wave 8's `world-map` panel** — that one reads **book-service's** `world_maps`/`map_markers`/`map_regions`; this one reads **`work.settings.world_map`**. *(Option (ii) — "book-service's world-map supersedes it" — was CONSIDERED AND REJECTED. Do not revive it: it would orphan every existing `work.settings.world_map` blob.)* 🔴 **This was a CIRCULAR DEFER — spec 38 said "Wave 6", Wave 6 never contained it — so silence here meant the feature died at GG-4. The silence is now broken; do not re-open it.** | `place-graph` |
| **canonview** | `CanonAtChapterPanel` — the *"what does canon KNOW as of chapter N"* inspector: glossary **PRESENCE** and knowledge **CANON-STATE** for that chapter window, **labelled by source distinctly** (two stores, may disagree), graded major/appears/mentioned. **Mounted TWO ways today:** as a per-scene studio panel, **and at a what-if BRANCH POINT** (canon right before the divergence). | 🔴 **Do not confuse it with the two canon panels that DO have homes:** `quality-canon` (shipped) = canon **ISSUES**/violations; `quality-canon-rules` (Wave 1) = canon **RULE authoring**. **This is neither** — it is a read-only canon **SNAPSHOT at a chapter boundary**, and its second mount point is **load-bearing for the divergence flow.** **TWO homes, near-zero cost: (a) FOLD INTO WAVE 6 M3** — a file row on `DivergencePanel`'s table (`:1133-1192`, which already ports `DivergenceWizard` + `DivergenceWizardSteps` + `useDivergenceWizard` **VERBATIM**) **plus a test that the branch-point step renders the canon-at-branch view.** 🔴 **If M3's wizard port silently drops it, the writer branches BLIND.** **(b)** for the standalone per-scene use, add it as a **SECTION inside the existing `scene-inspector` panel** (which already hosts `GroundingPanel` — same shape) ⇒ **no new panel id, no registration-count change.** | *(no new id)* |
| **flywheel** | `FlywheelPanel` — the **CANON-GROWTH** flywheel: after a publish→extraction run completes, shows *"+N entities / +N relations / +N events"* the run **ADDED to canon**, with named highlights; each stat deep-links to its view (Cast / Timeline / Relations) and each entity chip focuses that entity in Cast. Reads `knowledgeApi.getFlywheel` (**knowledge-service**). | 🔴 **WAVE 6's MAP FALSE-HOMES THIS: `flywheel: 'quality-corrections'` (wave-6 `:1454`). WAVE 1'S OWN PLAN CONTRADICTS IT IN WRITING (`:2445`):** *"No FlywheelPanel port. It is **knowledge-graph growth** (`knowledgeApi.getFlywheel`), **NOT the correction flywheel.** The name collides; the thing does not."* Spec 31 `:64` repeats it. `quality-corrections` = `CorrectionStatsTable` (**composition** correction RATES). **Two services, two datasets.** **ACTION: (a) FIX the row in wave-6's `LEGACY_SUBTAB_HOME` — this is currently the single most dangerous line in the whole gate, because it makes the machine-checked test GO GREEN on a feature being deleted; (b) HOME IT IN WAVE 8** — `getFlywheel` is a knowledge-service read and Wave 8 is already in those files. Leaf-reuse `FlywheelPanel`; its three deep-links become `host.openPanel('cast')` / `('kg-timeline')` / `('kg-graph')` — **a further reason to home `cast` in the same wave.** `category: 'knowledge'`. *(If PO instead rules won't-fix, that MUST be an explicit **DELETE_ON_PURPOSE** row in plan 30 §7's "Consciously OUT OF SCOPE" table — **NOT a mislabelled map row.**)* | `canon-growth` |

**Wave 0's deliverable for 12b is the LEDGER + the two FIXES, not the panels:**
1. The `PORTED_PANELS` list above **is** the ledger — it keeps the gate CLOSED until each home lands.
2. 🔴 **FIX the two false rows in `docs/plans/2026-07-13-studio-wave-6-editor-craft.md`'s
   `LEGACY_SUBTAB_HOME`** — `flywheel: 'quality-corrections'` (`:1454`) and `arc: 'arc-templates'`
   (`:1457`) — to point at **Wave 8's `canon-growth` / `character-arc`**. *(Two lines. They are the
   difference between a gate and a lie.)*
3. **Write the panel-delta consequences into the two owning plans** so their DoD counts are right:
   **Wave 6: +3 → +5** (`scene-compose`, `chapter-assemble`; canonview folds into existing panels ⇒ +0).
   **Wave 8: +2 → +6** (`cast`, `character-arc`, `place-graph`, `canon-growth`).
   🔴 **Both assert `N_before + k` three-way — NEVER a literal** (`Q-30-ENUM-COUNT-BASELINE`).

> **⚠ These are cross-wave edits.** Three tracks share this checkout and other agents own those plan files.
> **Enumerate paths, never `git add -A`.** If a wave-6/wave-8 plan file is dirty in `git status` when you
> reach this step: **park it in the drift register, land Wave 0's own ledger + gate test, and KEEP GOING**
> (run policy: blocked ≠ stopped). The **gate test is the load-bearing half** — it holds the line even if
> the other plans are edited later, because a missing id keeps the legacy route pinned.

**DoD evidence:** `"npx vitest run legacyEditorRetirementGate → 2 passed (gate CLOSED: 15 ids, N missing); RED-on-purpose run pasted (App.tsx:134 commented out ⇒ GG-4 VIOLATION message); wave-6 LEGACY_SUBTAB_HOME's flywheel + arc rows re-pointed at Wave 8; wave-6 delta +3→+5 and wave-8 delta +2→+6 recorded in their plans"`
**dependsOn:** —

---

### `W0-S13` — 🆕 **X-DIRTY-CLOSE · closing a dirty dock tab SILENTLY DISCARDS the edit (live today)**

> ⚖ **DECISION: `Q-30-SPEC08-SESSION-ORCHESTRATOR`** — *"SPLIT the item. (a) the dirty-close guard (S7) is a
> **Wave-0 cross-cutting fix — build it, ID `X-DIRTY-CLOSE`**. (b) `StudioSessionOrchestrator` (the Tier-3
> FSM) is **conscious won't-fix** — it has no consumer; the Tier-3 host primitives S7 actually needs
> (registry + bus + `_dockApiRef`) **already shipped**. **Do NOT build an FSM to get a close guard.**"*
>
> 🔴 **BUILD IT BEFORE ANY NEW EDITING PANEL LANDS.** Waves 1–8 add canon-rules, arc-inspector,
> style-voice, divergence — **every one of them an editing panel.** The bug multiplies with each.

> 🔴 **FIRST, CORRECT THE SPEC'S PREMISE: dockview 7.0.2 has NO cancelable panel-close event.**
> `onWillClose` exists **ONLY** on `DockviewPopoutGroupOptions` (popout-window lifecycle —
> `dockview-core/…/dockviewComponent.d.ts:48`). **The real seam is `defaultTabComponent`**
> (`dockview-react/…/dockview.d.ts:12`), which `StudioDock.tsx` **does not pass today.**
> **Build it as a GUARDED TAB, not an "onWillClose handler."** *(A slice written against a
> non-existent API is a stall.)*

**THE LIVE BUG:** `documents/types.ts:23` puts `dirty` on the shared `DocumentHandle`, and
`registry.ts`'s `wrapRelease()` **disposes the handle at refcount 0** — so `useJsonDocument`'s unmount
`release()` **silently discards unsaved JSON** when you close the tab. **Today.**

| # | File | Change |
|---|---|---|
| 1 | **NEW** `frontend/src/features/studio/host/dirtyRegistry.ts` | Module-level `Map<panelId, () => boolean>`; export `registerDirtyGuard` / `unregisterDirtyGuard` / `isPanelDirty` / `anyPanelDirty` / `_clearDirtyGuards`. **Mirror the existing module-registry pattern** (`documents/registry.ts`, `agent/effectRegistry.ts`): register at mount, test hook to clear. |
| 2 | **NEW** `frontend/src/features/studio/hooks/useDirtyGuard.ts` | `useDirtyGuard(panelId, dirty, onSave?)`. 🔴 **Store `dirty`/`onSave` in a REF so a keystroke does NOT re-register.** Register on mount, unregister on unmount. |
| 3 | **NEW** `frontend/src/features/studio/components/StudioTab.tsx` | A `FunctionComponent<IDockviewPanelHeaderProps>`: title + a dirty dot (`isPanelDirty(props.api.id)`), and a close button **+ middle-click (`auxclick`, button 1)** handler that, **when dirty**, opens `ConfirmDialog` instead of closing. **Reuse its 3-way shape for free** (`components/shared/ConfirmDialog.tsx:6-33`): `extraAction={{label:'Save & close', onClick: save→api.close()}}` · `confirmLabel='Discard changes'` → `api.close()` · cancel → no-op. **Not dirty ⇒ close immediately (identical to today).** |
| 4 | `frontend/src/features/studio/components/StudioDock.tsx:31-37` | Pass **`defaultTabComponent={StudioTab}`**. ⚠ **Also check whether the dock chrome exposes a group-level close-all control that BYPASSES the tab** — if it does, route it through the same guard via `rightHeaderActionsComponent`; **if it does not, assert that in the test.** |
| 5 | `frontend/src/features/studio/panels/JsonEditorPanel.tsx:41` | `useDirtyGuard(props.api.id, !!snapshot?.dirty, () => handle.save())`. **This is the live bug.** Do the same for `WikiEditorPanel` (keep its localStorage draft cache as the safety net for bypass paths). |
| 6 | `frontend/src/features/studio/components/StudioFrame.tsx` | ONE `beforeunload` listener gated on `anyPanelDirty()` — same shape as `WikiEditorWorkspace.tsx:326-333`. Covers browser refresh/close. |
| 7 | i18n | `studio` ns keys `dirtyClose.{title,body,save,discard,cancel}`. **No literals.** (`scripts/i18n_translate.py` for the 17.) |

#### Tests — the DoD ("checklist ⇒ test the effect")

- `components/__tests__/StudioTab.test.tsx` — **dirty tab:** close click ⇒ `api.close()` **NOT** called +
  dialog shown; **Discard** ⇒ `api.close()` called; **Save & close** ⇒ save **awaited THEN** `api.close()`;
  **clean tab** ⇒ closes with **no** dialog.
- `panels/__tests__/JsonEditorPanel.dirtyGuard.test.tsx` — an edited buffer registers a guard whose getter
  returns `true`.
- 🔴 **A guard-COVERAGE test over an `EDITING_PANEL_IDS` constant:** every id in it must have called
  `useDirtyGuard` — **reds when a new editing panel forgets.** *This is what makes the fix cross-cutting for
  canon-rules / arc-inspector / style-voice / divergence.*

**CATALOG/CHECKLIST:** add *"editing panel ⇒ `useDirtyGuard(props.api.id, dirty, save)`"* as a mandatory line
in spec 08's **D22 panel-author checklist**, and mark **S7 ✅** in `08_studio_state_architecture.md:48/64` —
**replacing the "no `onWillClose` guard" wording, because the API it names does not exist.**

**DEFER ROW (part b — filed, not dropped):** **`D-STUDIO-ORCHESTRATOR-FSM`** — the `StudioSessionOrchestrator`
FSM (spec 08 `:228`). **Gate 5 (conscious won't-fix)** + gate 2 (large/structural if revived). Trigger: only
if a concrete orchestration domain produces a bug panel-local state + the bus cannot express. **Note in the
row that S7 — the ONLY consequence of its absence anyone could name — is CLOSED by X-DIRTY-CLOSE without it.**

**DoD evidence:** `"npx vitest run src/features/studio/components/__tests__/StudioTab.test.tsx src/features/studio/panels/__tests__/JsonEditorPanel.dirtyGuard.test.tsx → all passed"` **+ a LIVE BROWSER smoke:** open `json-editor`, type, **close the tab → the confirm dialog appears**; choose **Save & close** → reopen → **the edit is there.** *(At HEAD it is silently gone.)*
**dependsOn:** —

---

### `W0-S14` — 🆕 **X-NEW-CHAPTER · the manuscript `+` button is DEAD**

> ⚖ **DECISION: `Q-30-SPEC02-NEW-CHAPTER-DEAD`** — *"FIX NOW — Wave 0 (size S). **It is NOT a one-line prop
> pass:** the break is at `StudioSideBar` (which has **no `onNewChapter` prop at all**), and **a naive
> book-service-only create is INVISIBLE in a Work-backed book.**"*
>
> 🔴 **The shipped bug is the reason all three tests below are mandatory:** `ManuscriptNavigator.tsx:115-116`
> is `onClick={onNewChapter} disabled={!onNewChapter}` and `ManuscriptNavigator.test.tsx:168` **asserts
> disabled-when-absent.** ⇒ **a GREEN component test over a DEAD app button.**

| # | File | Change |
|---|---|---|
| 1 | **NEW** `frontend/src/features/studio/manuscript/useNewChapter.ts` | *(Logic lives in a hook, not the view — CLAUDE.md React-MVC.)* `useNewChapter(bookId, token, bookLanguage?) → { createChapter, creating }`. Internally call **`useWorkResolution(bookId, token)`** — **the SAME hook `useManuscriptTree.ts:51` uses ⇒ shared react-query cache, no extra fetch** — and derive `projectId` with the **identical** shape as `useManuscriptTree.ts:52-57`. |
| 2 | ″ | `createChapter()`: (a) `title = t('manuscript.untitledChapter', { defaultValue: 'Untitled chapter' })`; (b) `booksApi.createChapterEditor(token, bookId, { original_language: bookLanguage ?? 'auto', title })` — **OMIT `sort_order`** (`server.go:1699-1701` auto-appends `MAX+1`) and **OMIT `body`** (an empty draft is valid); (c) 🔴 **if `projectId` is non-null** (Work-backed book): `compositionApi.createNode(projectId, { kind:'chapter', title, chapter_id: ch.chapter_id, status:'empty' }, token)` — parent_id/rank omitted (root-level, server-assigned rank). **WITHOUT THIS THE ROW NEVER SHOWS:** `useManuscriptTree.ts:85-90` renders **ONLY outline nodes** for a Work ⇒ the create would **201 and vanish** (`silent-success-is-a-bug`); (d) on any throw: `toast.error(...)` (mirror `ChaptersTab.tsx:71`), return `null`; **guard re-entry with `creating`**; (e) return `ch.chapter_id`. |
| 3 | `StudioFrame.tsx` | It already holds `bookLanguage` (`:46`), `accessToken`, `host`, `setSelectedNodeId`. Add `const { createChapter } = useNewChapter(bookId, accessToken, bookLanguage);` and `const onNewChapter = useCallback(async () => { const id = await createChapter(); if (!id) return; setSelectedNodeId(id); host.focusManuscriptUnit(id); }, [createChapter, host]);` — then **pass `onNewChapter={onNewChapter}` into `<StudioSideBar>`** (`:146-153`). |
| 4 | `StudioSideBar.tsx` | 🔴 **ADD `onNewChapter?: () => void \| Promise<void>` to `Props` (`:11-20`) and forward it to `<ManuscriptNavigator>` (`:34-40`). THIS IS THE ACTUAL MISSING LINK.** |
| 5 | `ManuscriptNavigator.tsx:112-121` | Keep the prop optional / `disabled={!onNewChapter}` (other hosts + tests rely on it), **but the click must refresh the tree it owns**: `const handleNew = useCallback(async () => { if (!onNewChapter) return; await onNewChapter(); reload(); }, [onNewChapter, reload]);` → `onClick={handleNew}`. (`reload` already comes from `useManuscriptTree`, `:55`.) |
| 6 | i18n | `manuscript.untitledChapter` + `manuscript.newChapterFailed` in `en/studio.json` (next to `manuscript.newChapter`), then `python scripts/i18n_translate.py` for the 17. |

#### Tests — **all three. The shipped bug proves the component test alone is worthless.**

- 🔴 `StudioFrame*.test.tsx` — render the frame and assert **`getByTestId('manuscript-new')` is NOT
  disabled.** **This is the exact regression that shipped** (green component test + dead app).
- `useNewChapter.test.tsx` — (a) **NO Work** ⇒ only `booksApi.createChapterEditor` is called, with
  `original_language` = the book's language (falls back to `'auto'`); (b) 🔴 **WITH Work** ⇒
  `compositionApi.createNode` **IS** called with `{ kind:'chapter', chapter_id: <the id returned by
  createChapterEditor> }` — **the anti-invisible-create assertion**; (c) failure ⇒ toast, **no**
  `focusManuscriptUnit`.
- `ManuscriptNavigator.test.tsx` — extend `:168-172`: after clicking `manuscript-new`, **the tree fetch is
  re-issued** (`reload` ran).

*(Default, PO may veto: the `+` creates an **Untitled chapter immediately** — VS Code "new file" semantics —
rather than opening a title/language dialog like `ChaptersTab`. The user renames in the editor.)*

**DoD evidence:** `"npx vitest run src/features/studio → all passed (3 new); getByTestId('manuscript-new') is NOT disabled"` **+ a LIVE BROWSER smoke on `:5199`:** click **`+`** → a new chapter **opens in the editor AND appears in the tree.** *(A raw unit-green does not prove this affordance — that is exactly how it shipped dead.)*
**dependsOn:** —

---

### `W0-S15` — 🆕 **PO `D-2` · Translate SILENTLY DISCARDS the user's ticked chapters** 🔴 **a HIGH bug, damaging data TODAY**

> ⚖ **SEALED DECISION `D-2` (§0-PO):** *"WAVE 0 IS THE HOTFIX BATCH. It already carries 3 of the 4 HIGH
> bugs (AddModelCta = X-1/`W0-S3`, motif-Mine 500 = `W0-BE1`, the conformance 404s = `W0-S7`). **PULL THE
> 4th FORWARD INTO WAVE 0.**"*
>
> 🔴 **This slice does NOT belong to Wave 0 by topic — it belongs to spec 29 / Wave T (gap `T8`, slice
> `T-A4` in `docs/plans/2026-07-13-studio-wave-T-translation-repair.md:1084`). The PO pulled it forward
> because it is ACTIVELY DAMAGING DATA TODAY.**
>
> ⚖ **THE DISCHARGE, EXACTLY — read this before you edit, or you will fork Wave T's line:**
> **`W0-S15` discharges the SELECTION half of `T8`/`T-A4` — and NOTHING ELSE.** `T-A4` is bigger than the
> dropped prop: it also lands **D6** (`preselectedLang` — the matrix *column* the user clicked), the
> per-cell *"not translated"* → **`openTranslate(lang)`** hand-off, the header CTA's unscoped open, and the
> *"a fully-translated book opens every action disabled"* dead end. **Those stay in Wave T.**
> ⇒ **In `T-A4`, mark the `preselectedChapterIds` line DISCHARGED-IN-`W0-S15`** (verify, don't re-apply) and
> **keep the rest of the slice.** 🔴 **Write the exact line `T-A4` already specifies** (below) so that when
> Wave T lands `preselectedLang` beside it, it is a **one-line extension, not a conflict.**

**The bug.** The user opens the Translation matrix, **ticks 3 chapters**, and clicks **Translate** in the
`FloatingActionBar`. `TranslateModal` **never receives the ticks** — so its own default kicks in
(`TranslateModal.tsx:134-138`: *"everything that needs translation for the default language"*) and the
modal comes up with **the WHOLE BACKLOG selected**. The user, having already made their selection, hits
Start. ⇒ **the wrong chapters are translated, LLM spend is burned on them, and existing translations can
be overwritten.** Nothing warns; the modal looks like it is doing what was asked.

🔴 **The prop ALREADY EXISTS and every OTHER call site passes it.** This is a **one-line omission at ONE
call site**, not a missing feature:

| Call site | Passes `preselectedChapterIds`? |
|---|---|
| `TranslationTab.tsx:300-305` — **the matrix's bulk Translate** | 🔴 **NO — the bug.** |
| `TranslationTab.tsx:539-544` — the **sibling** `<ExtractionWizard>`, in the SAME component, off the SAME `selectedChapters` state | ✅ `preselectedChapterIds={[...selectedChapters]}` |
| `ChapterTranslationsPanel.tsx:203-207` | ✅ `preselectedChapterIds={[chapterId]}` |
| `ChapterBrowserTitleView.tsx:509-514` | ✅ `preselectedChapterIds={[...selected]}` |

> ⚠ **The line numbers above are from HEAD `9262ed53e` and may have drifted — READ THE ACTUAL CODE FIRST.**
> The anchor that will not drift: **`TranslateModal` is mounted in `TranslationTab.tsx` with `open` /
> `onClose` / `bookId` / `onJobCreated` and NOTHING ELSE.**

#### Files

| # | File | Change |
|---|---|---|
| 1 | `frontend/src/pages/book-tabs/TranslationTab.tsx` | At the `<TranslateModal>` mount, add **exactly the line `T-A4` specifies: `preselectedChapterIds={[...selectedChapters]}`**. (`selectedChapters: Set<string>` is already in scope — `:133` — and the sibling `<ExtractionWizard>` spreads the same set at `:544`.) **ONE LINE. Nothing else in this file, and NOTHING in `TranslateModal.tsx`.** |

🔴 **Pass `[...selectedChapters]` — an EMPTY ARRAY when nothing is ticked — NOT `undefined`.** This is
`T-A4`'s own choice and it is correct: the modal **already treats an empty preset as "no preset"**
(`TranslateModal.tsx:132`: `if (preset && preset.length > 0) … else <needs-translation default>`), and
`handleLangChange` (`:205`) guards on `length > 0` too. ⇒ **the unscoped header/toolbar CTA still gets the
needs-translation default**, and Wave T's line and Wave 0's line are **byte-identical** (no conflict, no
second convention). ⚠ **Verify that branch, don't assume it** — it is test #2 below.

**Why no `key=` remount is needed** (unlike `ChaptersTab.tsx:353-363`'s `ExtractionWizard`): `TranslateModal`
**re-seeds its own selection** on `[open, accessToken, bookId, presetKey]` (`:104`, `:113-155`), where
`presetKey = preselectedChapterIds.join(',')`. It filters the preset against the fetched chapter list
(`:131`) and **only** falls back to the needs-set when the preset is empty (`:132-138`). And `handleLangChange`
(`:205`) **already** guards the pinned-selection case. ⇒ **The modal was BUILT for this. The caller simply
never fed it.** *(This is the whole reason the fix is one line — do not "improve" the modal. Every
improvement anyone can think of is already scoped in `T-A4`/`T-A5`, and doing it here forks that plan.)*

#### Tests — 🔴 **the existing test file is WHY this survived**

`frontend/src/pages/book-tabs/__tests__/TranslationTab.badge.test.tsx:25` mocks it away:
`vi.mock('../TranslateModal', () => ({ TranslateModal: () => null }))` — **a mock that renders `null`
cannot see a dropped prop.** Mock it the way `ChapterBrowserTitleView.test.tsx:31-34` does — **capture the
props and render them**:

| Test (new file `TranslationTab.selection.test.tsx`, or extend the badge file) | Asserts |
|---|---|
| 🔴 `test_ticked_chapters_reach_the_modal` | Tick 2 chapter rows → click **Translate** in the FAB → the `TranslateModal` mock received **`preselectedChapterIds` = exactly those 2 ids**. **MUST RED ON THE OLD CODE** (today it receives `undefined`). **Paste the red run.** |
| `test_no_selection_still_gets_the_needs_default` | Open Translate with **nothing ticked** ⇒ the modal receives an **empty array**, and the **real** `TranslateModal`'s seeding still lands on the needs-translation set (`:132-138`). 🔴 **Assert the EFFECT on the unmocked modal for this one** — an empty-array prop that accidentally *pinned* an empty selection would leave the bulk-backlog CTA disabled, which is `T8`'s OTHER symptom (`T-A4` consequence #3). Do not regress it while fixing #1. |

> 📌 **The rule this slice mints (copy it into every wave's review):** *when a component takes an optional
> selection prop, **every** call site that has a selection must pass it — and a `() => null` mock at a call
> site is a **blind spot**, not coverage.* A prop that exists, is honoured by the child, and is **dropped by
> one parent** is invisible to both sides' unit tests.

**DoD evidence:** `"npx vitest run src/pages/book-tabs → all passed (2 new); test_ticked_chapters_reach_the_modal observed RED before the one-line fix and GREEN after (both runs pasted); wave-T plan T-A4 annotated: the preselectedChapterIds line is DISCHARGED-IN-W0-S15, the D6/preselectedLang half REMAINS"` **+ the LIVE BROWSER smoke row 11 (§7):** tick 2 chapters → Translate → **the modal shows exactly those 2 selected**, not the whole backlog.
**dependsOn:** — *(fully independent; one line in one file. ⚠ The **cross-plan annotation** into `2026-07-13-studio-wave-T-translation-repair.md` is a **different agent's file** — if it is dirty in `git status`, **park it in the drift register and keep going**; Wave 0's code fix is the load-bearing half, and `T-A4`'s own pre-flight grep at `:159-163` will show the line already fixed.)*

---

### `W0-S16` — 🆕 **PO `D-3` · the GLOBAL `MutationCache.onError`** 🔴 **the highest leverage-per-line item in the entire build**

> ⚖ **SEALED DECISION `D-3` (§0-PO):** *"`frontend/src/App.tsx:6` builds `new QueryClient({…})` with **no
> MutationCache** ⇒ **every failed mutation in the entire frontend is silent, forever** — the button just
> re-enables. **That is why three live bugs survived to an audit.**"*

**The bug is an ABSENCE, and it is the meta-bug of this whole batch.** `App.tsx` constructs the app's one
`QueryClient` with `defaultOptions.queries` only. There is **no `mutationCache`** — verify it yourself, it
is a one-command fact:

```bash
# EXPECT: ZERO hits. (At HEAD the only match in the whole FE is a COMMENT in useRunBenchmark.ts:41.)
grep -rn "MutationCache" frontend/src --include=*.ts --include=*.tsx
# The scale of the hole — RECORD BOTH NUMBERS at pre-flight, do not copy these:
grep -rn "useMutation(" frontend/src --include=*.ts --include=*.tsx | wc -l   # plan-time: 142 call sites
grep -rn "onError:"     frontend/src --include=*.ts --include=*.tsx | wc -l   # plan-time:  98 handlers
```

⇒ **React Query's default `onError` is a NO-OP.** A mutation that 500s, 403s, or 409s **and has no local
`onError`** produces: no toast, no console error, no state change — **the button simply re-enables.** The
user clicks again. And again.

> 🔴 **BE PRECISE ABOUT THE GAP — do not "fix" what is not broken.** Individual hooks **do** handle their
> own errors: `useAdoptFlow.ts:59,69` (`onError: (err) => setQuota(readQuota(err))`), `useMotifEditor.ts:126`,
> and ~98 other `onError:` sites. **The hole is the GLOBAL DEFAULT** — which is what makes a *missing*
> handler **safe by construction** instead of silent by construction. ⚠ And the gap is real, not theoretical:
> **`useMotifBinding.ts` has NO `onError` at all** — its comment at `:29` even claims *"the caller keeps the
> prior binding **+ toasts**"*, and **nothing toasts.** A prose promise with no handler and no global default
> is exactly the class of hole this slice closes. *(Memory: `hygiene-grep-literal-token-in-comment-false-positive`
> — a grep for `onError` **matches that comment**. Count `onError:` with the colon.)*

**This is the repo's OWN LAW, applied to the surface it forgot.** The Frontend-Tool Contract (CLAUDE.md)
seals *"a resolver never silently no-ops — return `result.error`"* — and the repo wrote it for
**agent→GUI tools** only. **A user-initiated GUI action that fails silently is the SAME BUG CLASS on a
different surface** (memory: `silent-success-is-a-bug-not-environment`). `W0-S5c` closes it for the agent
door. **This slice closes it for the human door.**

#### Files

| # | File | Change |
|---|---|---|
| 1 | **NEW** `frontend/src/lib/queryClient.ts` | 🔴 **Move the `QueryClient` construction OUT of `App.tsx`** (it is currently an inline `const` at module scope, **untestable**). Export the factory **and** the singleton: `export function createAppQueryClient(): QueryClient` + `export const queryClient = createAppQueryClient();`. Keep `defaultOptions.queries` **byte-identical** (`staleTime: 30_000`, `gcTime: 5*60_000`, `refetchOnWindowFocus: true`, `retry: 1`) — **this slice changes ONE behavior, not four.** Add: `mutationCache: new MutationCache({ onError: (err, _vars, _ctx, mutation) => { if (mutation.options.onError) return; /* slice-local handler WINS — do not double-toast */ toast.error(readBackendError(err)); } })`. |
| 2 | ″ | 🔴 **Use the EXISTING toast mechanism — FIND IT, DO NOT INVENT A SECOND ONE.** It is **`sonner`**: `<Toaster position="bottom-right" richColors closeButton />` is mounted in `App.tsx` (**one** `<Toaster/>`, already there — **do not add another**), and ~every hook already calls `toast.error(...)` from `'sonner'`. The message comes from the **existing** `readBackendError()` (`frontend/src/lib/readBackendError.ts`) — the repo's single reader for FastAPI's `{detail}` / `{message}` shapes. **A new toast lib, a new error-formatting helper, or a second `<Toaster/>` is a REVIEW REJECT.** |
| 3 | `frontend/src/App.tsx` | Delete the inline `new QueryClient({…})` (`:6-15`) → `import { queryClient } from '@/lib/queryClient';`. **No other change.** |

**The `mutation.options.onError` check is the load-bearing line.** Without it, the ~98 hooks that already
handle their own errors (quota banners, inline field errors, optimistic rollbacks) would **each get a
duplicate global toast** — and a wave of double-toasts is how a global handler gets reverted. **Slice-local
`onError` MUST still win.**

> ⚠ **Scope discipline:** this slice adds a `MutationCache` **only**. It does **NOT** add a `QueryCache`
> `onError` (failed *reads* mostly already render an error state, and a global read-toast would fire on
> every backgrounded refetch — a different decision, not this one). It does **NOT** touch `retry`. It does
> **NOT** "fix" any individual hook. **One behavior.**

#### Tests — **the effect, not the declaration** (`checklist ⇒ test the effect`)

`frontend/src/lib/__tests__/queryClient.test.tsx` — render a throwaway component **through
`createAppQueryClient()`** (not a hand-rolled client — a test that builds its own `QueryClient` proves
nothing about the app's):

| Test | Asserts |
|---|---|
| 🔴 `a failing mutation with NO local onError surfaces a toast` | `useMutation({ mutationFn: () => Promise.reject(new Error('boom')) })` → fire it → **`toast.error` was called with `'boom'`** (spy on `sonner`). **MUST RED against the HEAD client** (which has no `MutationCache`). **Paste the red run.** |
| `a slice-local onError still WINS — and the global does NOT double-toast` | Same, but the mutation declares its own `onError` → the local handler ran **and `toast.error` was NOT called by the global**. |
| `the backend detail is what the user sees` | Reject with an `Error` carrying `body: { detail: 'chapter is locked' }` → the toast text is **`'chapter is locked'`**, not `'Bad Gateway'` — i.e. it goes through **`readBackendError`**, not `err.message`. |
| `the query defaults are unchanged` | `createAppQueryClient().getDefaultOptions().queries` still has `staleTime: 30000`, `retry: 1`, `refetchOnWindowFocus: true`. **The anti-scope-creep lock** — a global-error slice must not silently re-tune caching. |

⚠ **`vitest beforeEach` returning a mock is treated as teardown** (memory) — if you seed the `sonner` spy in
`beforeEach`, **do not return it** (`beforeEach(() => { vi.mock… })`, not `beforeEach(() => vi.fn())`); a
rejecting mock returned from `beforeEach` gets CALLED after the test and fails it.

**DoD evidence:** `"npx vitest run src/lib → all passed (4 new); 'a failing mutation with NO local onError surfaces a toast' observed RED against HEAD's client and GREEN after (both runs pasted); grep -rn 'MutationCache' frontend/src → the new file only"` **+ the LIVE BROWSER smoke row 12 (§7)** — a real failing mutation **visibly toasts**.
**dependsOn:** — *(independent; but land it EARLY in the batch — every later slice's live smoke inherits the safety net, and a silent failure during a Wave-0 smoke is exactly what it is there to reveal)*

---

## 5 · Migrations

🔴 **ONE — and the first cut said "NONE", which was wrong** (§10 #6). `W0-BE1` **must** ship DDL, because
the paid-action bug is that the job row **can never be written**, not that it cannot be read.

**`services/composition-service/app/db/migrate.py` — additive, reversible, and NOT the destructive
stop-and-ask class:**

```sql
ALTER TABLE generation_job ALTER COLUMN project_id DROP NOT NULL;
ALTER TABLE generation_job ALTER COLUMN book_id    DROP NOT NULL;
-- both-or-neither: an unbound job has NEITHER key; a bound job has BOTH. A half-null row is a tenancy hole.
ALTER TABLE generation_job ADD CONSTRAINT generation_job_scope_shape CHECK (
  (project_id IS NULL AND book_id IS NULL) OR (project_id IS NOT NULL AND book_id IS NOT NULL));
CREATE INDEX IF NOT EXISTS idx_generation_job_owner_unbound
  ON generation_job (created_by, created_at DESC) WHERE project_id IS NULL;
```

**Migration safety — CLAUDE.md's four traps, each checked:**
- **No new column** ⇒ *"ADD COLUMN never revisits a bad default"* is **N/A**.
- The CHECK constrains **shape**, not an operation enum ⇒ the *"backfill ALL historical CHECK blocks"*
  trap is **deliberately avoided** — **the op allowlist lives in the WRITER**
  (`UNBOUND_OPERATIONS = frozenset({"mine_motifs", "analyze_reference"})`), where it evolves **without DDL**.
- The index is **non-unique** ⇒ no tombstone / `ON CONFLICT` predicate hazard.
- **Every existing row has both keys non-null** ⇒ the CHECK **validates clean** and `DROP NOT NULL`
  **rewrites nothing**.
- 🔴 **Do NOT touch `create()`** — it is the hot path for every draft. Add **`create_unbound()`** beside it.

> ⚠ **The next wave is NOT migration-free either** and the traps are recorded:
> Wave 1's **BE-9** needs `ALTER TABLE authoring_run_units ADD COLUMN job_id UUID` (**nullable — never
> backfill a guess**), and Wave 3's **BE-M1** needs a partial UNIQUE index on `motif_application`.
> When you get there: `ADD COLUMN IF NOT EXISTS` **never revisits a bad default** on an
> already-migrated DB; a new enum value must backfill **every** historical CHECK block; and a partial
> UNIQUE index **must exempt soft-delete tombstones** and its `ON CONFLICT` **must repeat the partial
> index's predicate**. **None of those traps is Wave 0's problem** — Wave 0's one migration is the
> additive, non-rewriting `DROP NOT NULL` + CHECK above. *(An earlier cut of this line said "Wave 0 has no
> migration". That was the §10 #6 error — it is corrected here so nobody re-derives it.)*

> 🔴🔴 **AND THE ONE THAT IS NOT LIKE THE OTHERS — SEALED PO DECISION `D-1` (§0-PO).** The **content-language
> rekey** (5 rows say `Vietnamese` next to 89 saying `vi`, inside `UNIQUE(chapter_id, target_language,
> version_num)`) is a **DESTRUCTIVE 3-table rekey**. **It is NOT Wave 0's** — but every builder reading this
> section must know the rule before they meet it: **write the migration + a rollback path + a before/after
> row-count assertion, run a DRY-RUN, SHOW THE OUTPUT — and STOP for the PO. It may NOT be executed
> unattended.** It is **the one CRITICAL-class stop in the entire 10-wave build** (§0.3's *"destructive /
> irreversible"* class — the ONE thing that is **not** a defer-row-and-keep-going). ⚠ Its SSOT is
> `contracts/languages.contract.json` (**`D-4`** — **never** `languages.yaml`; `contracts/language-rule.yaml`
> already means *service → programming language*).

---

## 6 · The per-panel registration checklist (GG-8)

**N/A — Wave 0 ships ZERO new panels.**

The enum baseline is **UNCHANGED** by this wave: **`N_after === N_before + 0`.**

> 🔴 **NEVER ASSERT A LITERAL PANEL COUNT — anywhere, in any wave** (`Q-30-ENUM-COUNT-BASELINE`).
> The three-way guard is **already count-free and self-updating**: `panelCatalogContract.test.ts:32-35`
> asserts **SORTED SET EQUALITY** (+ every advertised id is buildable in `STUDIO_PANEL_COMPONENTS`), and
> `test_frontend_tools.py:168-171` asserts only non-empty + no-duplicates. **Nothing anywhere hardcodes a
> count.** A builder who "fixes" a wave by writing `expect(enum).toHaveLength(61)` is **re-introducing the
> exact anti-pattern the repo deliberately deleted** — read the tombstone at `test_frontend_tools.py:153-162`.
>
> **The DoD form, for every wave:** MEASURE `N_before` (do not copy it from a spec) → add the wave's **k**
> panels to **all three** places → **regenerate** the contract → assert **`N_after == N_before + k`** AND
> the three-way set-equality suite green. **`k` is the only number a spec may state.** The §8 ladder
> (57→61→…→71) is a **planning aid ONLY** — the waves are sequential and the counts are **cumulative**;
> six of the eight specs computed their target from the same 57 baseline *as if each were the only wave*.
> **If a wave is re-ordered, dropped or split, every literal below it becomes a false red.**

**Wave 0's only obligations against GG-8 are the guards it *strengthens*:** **X-2** (category ∈
`CATEGORY_ORDER`, **now a compile error**, + a group **label**), **X-3** (`guideBodyKey` **RESOLVES**, and
the field is now **required in the type**), and **X-13b** (a bogus `panel_id` gets `opened:false` + an
`error`, not a hallucinated success). All become permanent machine guards every later wave inherits —
which is the whole reason Wave 0 exists.

**Three slices touch `frontend_tools.py` + `contracts/frontend-tools.contract.json` WITHOUT adding a panel:**
`W0-S5` **removes a tool** (12 → 11), `W0-S5b` **adds an arg**, `W0-S5c` **removes a model**. The `panel_id`
enum **must still be `N_before`** after each regeneration. If it isn't, **you edited the wrong thing.**
🔴 **Land the three regens SERIALLY** — *never two concurrent regens* (`00B_EXECUTION_ROADMAP.md:203`).

> 📌 **Two lines every later wave copies into its own DoD** (Wave 0 is where they are minted):
> 1. *"delete this wave's rows from `PENDING` in `effectCoverage.contract.test.ts`" (`W0-S4`).*
> 2. *"a new panel lands its `guideBodyKey` in `catalog.ts` AND its `panels.<id>.guideBody` in
>    `en/studio.json` in the SAME slice" (`W0-S2`).*
> 3. *"an editing panel calls `useDirtyGuard(props.api.id, dirty, save)`" (`W0-S13`).*

---

## 7 · Wave Definition of Done

Tick every box. **No box is ticked by a claim — each is ticked by pasted output.**

- [ ] **`W0-BE1`** — the **WRITER** (`DDL` + `create_unbound()` + the `_enqueue_motif_job` branch) **AND** the read route `GET /v1/composition/motif-jobs/{job_id}`; 8 real-DB tests green; the MCP tool drops `project_id` and gates on `created_by`. **The paid-action defect is dead.**
- [ ] **`W0-BE2`** — BE-11 `POST /canon-rules/{rule_id}/restore`; restore does **NOT** bump `version` and does **NOT** flip `active`.
- [ ] 🔴 **`W0-C1`** — **BOTH new routes are in `contracts/api/composition/v1/openapi.yaml`**; `GenerationJob.project_id`/`book_id` are **nullable**; the parity test is green **and was RED before the yaml edit**. **CONTRACT-FIRST, before `W0-S7`.**
- [ ] **`W0-S1`** — `'quality'` is in `CATEGORY_ORDER` **after `knowledge`, before `translation`**; the `as const satisfies` **compile guard** is green under `tsc --noEmit`; **`palette.group.quality` exists in all 18 locales**; the membership + label + sort-**effect** assertions are green.
- [ ] **`W0-S2`** — **both** guideBody assertions green; **5 `en` bodies** backfilled (**en only** — `fallbackLng` covers the rest); `guideBodyKey` is **required in the type**.
- [ ] **`W0-S3`** — `AddModelCta` renders a **`<button>` + `followStudioLink`** in the studio (**no `<a href>` to ⌘-click**); **the dock survives the click.**
- [ ] **`W0-S4`** — the string branch is **DELETED** (a string now **throws**); **both** false comments deleted; **`authoringRunEffects.ts`** ships (11 tools × **7** keys); **`effectCoverage.contract.test.ts`** is green with a **documented non-empty `PENDING`**; `kg_create_node` is **pinned, not re-added.**
- [ ] **`W0-S5`** — `ui_show_panel` is **gone from every one of the 9 files** (incl. the e2e spec); `ui_watch_job` opens `job-detail` **in the dock**; contract regenerated **in the same commit** (12 tools → **11**); `panel_id` enum **`N_after === N_before`**.
- [ ] 🆕 **`W0-S5b`** — `ui_open_studio_panel` has an **OPTIONAL `params`** (**NOT in `required`, NOT in `CLOSED_SET_ARGS`**); a **string** `params` is dropped, not thrown on; **live browser: the dock tab mounts ON THAT JOB.**
- [ ] 🆕 **`W0-S5c`** — `consumer_capabilities` + `contributeContext` **deleted** (suite still green ⇒ nothing read them); 🔴 **a bogus `panel_id` returns `opened:false` + `result.error`** — **not a hallucinated "Opened!"**.
- [ ] **`W0-S6`** — 🔴 `grep -rn "motif" …/packer/*.py` is **NON-EMPTY**; **BOTH** tests (unit effect + real-DB **wired**) prove the prompt **CHANGES** when a binding changes; **all FOUR** `pack()` call sites pass `motif_application_repo=`. **The Wave-3 gate is green.**
- [ ] **`W0-S7`** — 🔴 the chapter conformance estimate/confirm are **DELETED, not re-pointed** (re-pointing = **a paid job guaranteed to fail**); the MCP tool **refuses to mint `scope='chapter'`**; `regenerateToBeat` is **deleted** and the button drives the **existing scene-generate**, **gated on MODEL not COST**; the mine poll hits `/motif-jobs/{id}`; **`D-MOTIF-CONFORMANCE-ENGINE-WIRING` is filed.**
- [ ] **`W0-S8`** — spec 28 has **§AN-12.1** with the **8 TABLE-keyed kinds** (incl. `chapter`/`scene`/`glossary_entity`, which OQ-8's sketch **dropped**); OQ-8 is CLOSED; **no code changed.**
- [ ] **`W0-S9`** — §3.1 → **188/164/24**; §3.4 **deleted (closed)**; the `web_search` "violation" is **REFUTED and struck** (not a won't-fix); 🔴 **`G-PROFILE-FIELDS` shipped** (bio/languages/avatar/locale are settable by a human); `settings_model_set_default` advertises **all four** capabilities.
- [ ] **`W0-S10`** — renumbered **15a = WIKI, 15b = BROWSER** (the first cut had it backwards) with **zero** dead links; 29's H1; spec 20 un-staled; **14b + 15b added to the index**; the `X-11` ref → `BE-11`; plan 30 §11 item 1 replaced; 🔴 **the 5th destructive-token drift fixed + `design-draft-token-lint.py` wired into pre-commit.**
- [ ] **`W0-S11`** — `build_book_context_note()` is **extracted and unit-testable**; the scent names **all three** reads and is gated on **`_tools_live`** (**absent on a tools-OFF turn**) — **or** deferred as `D-X10-ANC2-SCENT` if the Track-C re-verify shows those files dirty.
- [ ] 🆕 **`W0-S12`** — `legacyEditorRetirementGate.test.ts` is green **and RED-on-purpose was pasted**; 🔴 **the LEGACY_SUBTAB_HOME ledger names a wave for all 7 homeless sub-tabs**; **wave-6's two FALSE map rows (`flywheel`, `arc`) are FIXED** — *as written, the machine gate goes GREEN on a deleted feature.*
- [ ] 🆕 **`W0-S13`** — closing a **dirty** dock tab prompts (Save & close / Discard / Cancel) instead of **silently discarding**; the `EDITING_PANEL_IDS` coverage test reds when a new editing panel forgets.
- [ ] 🆕 **`W0-S14`** — the manuscript **`+`** creates a chapter **AND** (in a Work-backed book) its outline node, **so the row actually appears**; `manuscript-new` is **NOT disabled** in the live frame.
- [ ] 🆕 **`W0-S15`** (PO `D-2`) — the matrix's `<TranslateModal>` receives **`preselectedChapterIds={[...selectedChapters]}`** (`T-A4`'s verbatim line); the ticked chapters are the ones translated (**not the whole backlog**); **nothing ticked still gets the needs-translation default**; the test **REDS on the old code** (paste it); the `() => null` mock is replaced by a **prop-capturing** mock; **`TranslateModal.tsx` is UNTOUCHED**; 🔴 **Wave T's `T-A4` is annotated: the selection half is DISCHARGED here, the `preselectedLang`/D6 half REMAINS.**
- [ ] 🆕 **`W0-S16`** (PO `D-3`) — the app's `QueryClient` has a **`MutationCache.onError`**; a failing mutation **with no local handler TOASTS** (test reds against HEAD's client); a **slice-local `onError` still WINS** (no double-toast); the message goes through the **existing** `readBackendError` + **`sonner`** (**no second toast mechanism, no second `<Toaster/>`**); the **query defaults are unchanged**.

### The suites — name them, run them, paste the counts

```bash
cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup   # ≥ pre-flight baseline, 0 failed
cd services/chat-service        && python -m pytest tests -q -n auto --dist loadgroup   # ≥ pre-flight baseline, 0 failed
cd services/provider-registry-service && go test ./internal/api/...                     # W0-S9's 4-capability drift guard
cd frontend && npx tsc --noEmit && npx vitest run                                       # tsc PROVES X-2's compile guard

# The drift-locks (GG-8's verify block) — ALL must be green:
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/panels/__tests__/legacyEditorRetirementGate.test.ts \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/studio/agent/__tests__/effectCoverage.contract.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts

# The contract-first gate (W0-C1) + the per-action-route bug-class guard (W0-S7):
cd services/composition-service && python -m pytest tests/unit/test_openapi_contract_parity.py -q
grep -rnE "actions/[a-z_]+/(estimate|confirm)" frontend/src   # MUST be empty
python scripts/design-draft-token-lint.py                      # W0-S10 — MUST be 0 violations
```

> ⚠ **A green unit suite has repeatedly hidden "the FE could not actually execute it."** Wave 0 touches
> **4 services** (composition, chat, **provider-registry**, + the FE through the gateway) ⇒ **live-smoke is
> MANDATORY**, and for agent↔GUI work it must be a **LIVE BROWSER** smoke, not a raw-stream check.
> **Rebuild first** — `:5174` is the **BAKED nginx prod build**; a stale image is a false green.

### The LIVE BROWSER smoke (Playwright) — one session, five assertions

**Recipe** (memory: `playwright-live-dockview-automation-recipe`): **refs go stale** — drive via
`evaluate` + `data-testid`; use `page.mouse` for any drag (synthetic events don't drive d3/dockview).
**Rebuild first** — `:5174` is the **BAKED nginx prod build**; a stale image is a false green (memory:
`live-smoke-rebuild-stale-images-first`, `frontend-5174-is-baked-prod-nginx-not-vite`). Log in as
`claude-test@loreweave.dev` / `Claude@Test2026`.

| # | Drive | Assert |
|---|---|---|
| 1 | Open a studio panel with an empty ModelPicker → click **Add a model** | **The dock is still mounted** (another panel's `data-testid` still in the DOM) **and** the settings panel opened on **Providers**. *(X-1)* |
| 2 | Open the Command Palette | `quality` panels **no longer sort above `editor`** **and** the group header reads **"Quality"**, not the raw `quality`. *(X-2 — both halves)* |
| 3 | Open `user-guide` | The **4 quality panels render a non-empty body**. *(X-3)* |
| 4 | Ask the agent to *"open the glossary"*, then to start a long job (→ `ui_watch_job`) | A dock tab **actually appears**; **the dock is still mounted** and a `job-detail` tab appeared. *(X-5 — a raw-stream check would show `watching:true` while the dock was destroyed.)* |
| 5 | Agent calls `ui_open_studio_panel {panel_id:"job-detail", params:{jobId:"<real>"}}` | The tab mounts **ON THAT JOB**. *(X-12)* |
| 6 | Agent calls `ui_open_studio_panel` with a **BOGUS** id | The agent gets a **visible `error`** back — **not a hallucinated "Opened!"**. *(X-13b — the shipped silent-success)* |
| 7 | Click **⛏ Mine** → confirm the cost | 🔴 **`/actions/confirm` returns 2xx with a real `job_id`** *(at HEAD it is a hard **500 at confirm** — the job row is never written)*, **then** the poll returns **200** and the panel reaches a **terminal** state. *(The paid-action defect. Assert the CONFIRM, not just the poll — a green poll over a hand-seeded row proves nothing.)* |
| 8 | Click the chapter conformance **Re-run** | **Exactly ONE** request: a **GET** to `…/conformance?scope=chapter…`. **ZERO** requests to any `/actions/*` path, **no cost card.** *(§10 #7 — the paid job that would always fail.)* |
| 9 | Open `json-editor`, type, **close the tab** | The **confirm dialog** appears; **Save & close** → reopen → **the edit is there.** *(X-DIRTY-CLOSE — at HEAD it is silently gone.)* |
| 10 | Click the manuscript **`+`** | A new chapter **opens in the editor AND appears in the tree.** *(X-NEW-CHAPTER — the button is dead at HEAD.)* |
| 11 | On the Translation matrix, **tick exactly 2 chapters** → **Translate** | 🔴 The modal opens with **exactly those 2 selected** — **not the whole backlog.** *(X-TRANSLATE-SELECTION / PO `D-2` — at HEAD the ticks are thrown away and the user translates the wrong chapters.)* |
| 12 | Force a mutation to fail (e.g. offline the gateway, or hit a route that 403s) from a surface with **no local `onError`** | 🔴 **A toast appears with the backend's reason.** *(X-SILENT-MUTATION / PO `D-3` — at HEAD the button silently re-enables and the user learns nothing. **This one assertion is the reason three live bugs reached an audit.**)* |

### `/review-impl` — **MANDATORY, and its findings are FIXED BEFORE THE WAVE CLOSES**

```
/review-impl studio-wave-0
```

Run it on the **wave's full diff**. **Every bug it finds is fixed in this wave** (per the PO policy,
§0.2). Point it explicitly at:
- 🔴 **the 4 `pack()` call sites** (X-7's wiring — *this exact bug shipped once already in BA12 and
  `/review-impl` is what caught it*),
- 🔴 **`W0-BE1`'s DDL + owner gate** — the `generation_job_scope_shape` CHECK (a **half-null row is a
  tenancy hole**) and `created_by` (a tenancy boundary; H13 uniform-404, **byte-identical** to the
  missing-row 404),
- 🔴 **the `ui_show_panel` retirement's 9 files** (a half-retired tool is worse than none) **and the three
  serial contract regens** (a regen that silently drops a tool is invisible in a green suite),
- 🔴 **the `<motif>` block's cap** (it rides **outside** `enforce_budget` — an uncapped block is a
  Context-Budget-Law hole),
- 🔴 **`W0-S7`'s deletions** — confirm **nothing** still mints a `scope='chapter'` conformance run, from
  **either** door (FE **or** MCP),
- 🔴 **`W0-S9`'s `G-PROFILE-FIELDS`** — it widens a **profile write** payload; check the dirty-check covers
  every field and that no field is silently dropped.

### Close-out

- [ ] `/review-impl` run on the wave diff; **every finding fixed** (or a defer row that clears the gate).
- [ ] `docs/sessions/SESSION_HANDOFF.md` — **▶ NEXT SESSION** block overwritten; the Deferred list updated (rows below); cleared rows moved to "Recently cleared".
- [ ] Committed. **Enumerate files (`git commit -- <paths>`) — NEVER `git add -A`** (three tracks share this checkout). Check `git diff --cached --name-only` first (the index may carry another session's staged work).

---

## 8 · Defer register — the starting rows

| ID | Origin | What | Gate reason (CLAUDE.md 1–5) | Target |
|---|---|---|---|---|
| `D-X4-WAVE-HANDLERS` | `W0-S4` | The ~13 remaining Lane-B handlers (`compositionEffects`, `arcEffects`, `motifEffects`, `planEffects`, `diagnosticsEffects`, `worldEffects`, `registryEffects`). **NOT deferrable work — DISTRIBUTED work.** They invalidate query keys of panels that do not exist yet; §8.0b assigns each file to the wave that builds its panel. | **3 — naturally-next-phase** (the prerequisite — the panel — does not exist) | Waves 1/2/3/5/7/8, per §8.0b. 🔴 **It is no longer a prose row: it is the `PENDING` allowlist in `effectCoverage.contract.test.ts`, and each wave's DoD says "delete YOUR rows or the test reds."** |
| 🆕 `D-MOTIF-CONFORMANCE-ENGINE-WIRING` | `W0-S7` | The **PAID** per-scene extract-diff **chapter** conformance re-run **does not exist** (the worker is arc-only — `motif_conformance_run.py:74-78` names this row itself). Until it does, chapter conformance is a **free synchronous refresh** and the button **must not pretend to spend**. | **3 — naturally-next-phase** (the chapter extract-diff engine is unbuilt. **NOT "blocked"** — it is a real unbuilt slice; it is simply out of a GUI-wiring slice's scope.) | Whenever the chapter extract-diff engine is scoped. |
| 🆕 `D-STUDIO-ORCHESTRATOR-FSM` | `W0-S13` | The `StudioSessionOrchestrator` Tier-3 FSM (spec 08 `:228`). **It has NO consumer**, and the Tier-3 host primitives S7 actually needed (registry + bus + `_dockApiRef`) already shipped. | **5 — conscious won't-fix** (+ gate 2 if ever revived). | Only if a concrete orchestration domain produces a bug that panel-local state + the bus cannot express. 🔴 **S7 — the ONLY consequence of its absence anyone could name — is CLOSED by `W0-S13` WITHOUT it.** |
| `D-X10-ANC2-SCENT` | `W0-S11` | **CONDITIONAL — only if the build-time re-verify shows Track C's 4 files dirty.** The AN-C2 discovery scent. | **4 — blocked (external owner: Track C)** | The next session after Track C's files are clean. *(Verified clean at plan time **and** by `Q-30-TRACKC-UNCOMMITTED-FILES` ⇒ **this row should never be opened.**)* |
| ~~`D-X9-WEBSEARCH-UNPREFIXED`~~ | ~~`W0-S9`~~ | 🔴 **DELETED — the premise was FALSE, so there is nothing to "won't-fix".** `EXTRA_PREFIX_MAP.settings = ['web_']` (`ai-gateway/src/config/config.ts:110-128`) **explicitly allows it**, pinned against the REAL config by `test/catalog.spec.ts:161`. It shadows nothing (glossary's tool is separately named). The namespacing law governs **externally federated** servers. | — **REFUTED, not deferred** (`Q-30-X9-UNAUDITED-MCP-SWEEPS` §2) | ✅ **Struck.** The exception is recorded in `docs/standards/README.md` so it is not re-opened a **third** time. |
| ~~`D-X12-PANEL-PARAMS`~~ | ~~`W0-S5`~~ | 🔴 **DELETED — the plan said "NO"; the adjudication says BUILD IT (`W0-S5b`).** The decisive fact the "no" never confronted: **sealed PO-3 already REQUIRES it** (`ui_watch_job` → `job-detail`, which `JobDetailPanel.tsx:1` says *"retargets via params"*), and **3 specs in this batch design a params deep-link the agent structurally cannot use.** | — **BUILT IN `W0-S5b`** (`Q-30-X12-PARAMS-ARG`) | ✅ **Cleared.** |
| `D-QUALITY-GUIDEBODY-ROT` | `W0-S2` | *(Opened AND CLOSED in this wave — recorded because the class will recur.)* 4 shipped panels declared a `guideBodyKey` whose i18n key never existed ⇒ **a blank User-Guide body, silently.** The **declaration** assertion plan 30 proposed would have been **GREEN** on it. | — **FIXED IN `W0-S2`** | ✅ Cleared. **The lesson is the guard: assert the EFFECT, not the declaration.** |

**Carried from the decisions file (Wave 0 files the row; another track owns the work):**
`D-STUDIO-10-AGENT-HOOKS` (spec 10, 0% built — its own spec+plan track, after Wave 8) ·
`D-ARC-DECOMPILER-STRUCTURE-NODE` (spec 26-D3, after Wave 2) ·
`D-WIKI-MCP-TOOLS` (new spec 39, after Wave 8) ·
`D-PLANFORGE-BLIND-PROPOSE` (its own spec, after Wave 8).
**Write all four into `docs/sessions/SESSION_HANDOFF.md` Deferred Items + `docs/deferred/DEFERRED.md` in the
SESSION phase.** They are pre-scoped **verbatim** in `wave-0-decisions.md` §"Deferred" — **copy the rows,
do not re-derive them.**

---

## 9 · Risks — and the TELL that each has fired

| # | Risk | The tell | The kill |
|---|---|---|---|
| 1 | 🔴 **X-7's wiring bug, re-shipped.** The lens is written, the unit test is green, and a `pack()` call site was missed ⇒ **the motif never reaches the prompt in production.** *This exact bug already shipped once (BA12/arc) and its unit test could not see it.* | The unit test is green and **the real-DB WIRED test is missing or was "simplified"**. Or: `grep -c "motif_application_repo=" services/composition-service/app/routers/{engine,grounding}.py` ≠ **3 + 1**. | `W0-S6`'s `test_every_pack_call_site_passes_the_motif_repos` + **BOTH** tests (unit effect **and** real-DB wired — the decision is explicit that the unit one alone is *"precisely what FAILED to catch this bug for the arc lens"*). **Do not let either be dropped for speed.** |
| 2 | 🔴 **The `<motif>` block blows the context budget.** It rides **outside** `enforce_budget` (like `<arc>`). An author binds 10 motifs to a scene → the prompt bloats → the Context Budget Law is breached, **silently**, on every generation. | Prompt token counts jump after `W0-S6`. `pc.over_budget` starts firing. | The **≤3-binding cap** (spec 33 BE-M2) + `test_the_block_is_capped`. **Point `/review-impl` at it explicitly.** |
| 2b | 🔴 **A decision gets silently re-flipped.** A later agent reads `Q-30-404-MOTIF-MINE-POLL`'s *"zero migration"* (or `Q-30-TIER-W-GENERIC-SPINE`'s *"re-point conformance"*) and "corrects" the plan back — **re-opening the paid-action defect.** | A diff that deletes `create_unbound()`, or re-adds `conformanceRunConfirm`. | **§10.2 names all three overrides with the verifying command (pre-flight 1b). RE-RUN THE COMMAND — do not re-flip from memory.** If it prints the opposite, the decision was right and the plan is stale: follow the decision and log the drift. |
| 3 | **The `ui_show_panel` retirement is half-done.** The tool is removed from the Python schema but a stale name lingers in `tool_discovery.py` / `serverKey.ts` / a test ⇒ the model is offered a tool that no longer resolves, or a test asserts a ghost. | `grep -rn "ui_show_panel" frontend/src services/ --include=*.ts --include=*.tsx --include=*.py \| grep -v __pycache__` returns **anything** after `W0-S5`. | Make that grep a **literal DoD command**. It must return **zero** lines (comments included — memory: `hygiene-grep-literal-token-in-comment-false-positive` cuts the other way here: **delete the comments too**). |
| 4 | **`W0-BE1`'s owner gate leaks.** `created_by != user_id` returns a **403** or a *different* 404 detail than the missing-row case ⇒ an **enumeration oracle** (an attacker learns which job ids exist). | The two 404s have different `detail` strings, or one is a 403. | `test_other_user_gets_404_not_403` asserts the details are **byte-identical**. |
| 5 | **The i18n locale generation silently drops keys.** `scripts/i18n_translate.py` drives a local LLM; a chunk can come back with a merged or missing key. | A locale's `studio.json` is missing `panels.<id>.guideBody` — and **nothing reds**, because `W0-S2`'s assertion only reads **`en`**. | The script has a verify + self-heal loop (key-set identity) — **read its output, don't just run it.** ⚠ Memory: `i18n-translate-self-heal-only-fires-on-hard-failures` — a SOFT flag does **not** self-heal. **Check the soft flags.** |
| 6 | **Another track lands in a Wave-0 file mid-flight.** Three tracks share this checkout; `QualityCanonPanel.tsx` was touched *the day before* this plan. | A merge conflict, or a `git status` that shows files you didn't touch. | `git status` + `git diff --cached --name-only` **before every commit**; `git commit -- <explicit paths>`. **Never `git add -A`.** |
| 7 | **The Track-C gate re-opens.** Track C's `stream_service.py` was clean at plan time. If it re-dirties, `W0-S11` edits a file another agent is mid-edit in. | Pre-flight step 4 prints anything. | **DEFER `W0-S11` (`D-X10-ANC2-SCENT`) and keep going.** It is the only slice with an external owner, and it is last for exactly this reason. |
| 8 | **X-2's chosen position for `'quality'` gets re-litigated at 3am.** | A builder pauses to ask where `quality` should sort. | **It is decided: after `storyBible`, before `knowledge`.** Any position is correct; this one is chosen. **Do not re-open it.** |
| 9 | 🆕 **`W0-S16`'s global handler DOUBLE-TOASTS and gets reverted.** ~98 hooks already toast their own errors; a global handler that fires unconditionally stacks a second toast on every one of them ⇒ the reviewer reverts the whole slice ⇒ **the silence comes back.** | Two toasts for one failed save, anywhere in the app. | **`if (mutation.options.onError) return;`** — the one load-bearing line. Its test (`a slice-local onError still WINS`) is **not optional**; it is what makes the slice survivable. |
| 10 | 🆕 **`W0-S15` regresses the bulk-backlog flow, or FORKS Wave T's line.** Either the empty-array preset accidentally *pins* an empty selection (⇒ the unscoped CTA opens **disabled** — `T8`'s other symptom), or a builder "improves" `TranslateModal.tsx` / writes a different call-site line than `T-A4`'s ⇒ **a merge conflict with the plan that owns the file.** | Opening Translate with nothing ticked selects **nothing** instead of the needs set; or the diff touches `TranslateModal.tsx`. | `test_no_selection_still_gets_the_needs_default` (asserted on the **unmocked** modal). 🔴 **The modal already handles both cases (`:131-138`, `:205`) — the ONLY change is the CALL-SITE line, and it is `T-A4`'s VERBATIM line: `preselectedChapterIds={[...selectedChapters]}`. Touching `TranslateModal.tsx` at all is a scope-creep smell.** |

---

## 10 · The AUDIT CORRECTIONS, in one place

*(Plan 30 was adversarially verified and **still** had 3 wrong backend rows that the spec authors
caught. The brief said to assume the same rate remains. It does. **#1–#5 are the plan vs plan 30. #6–#9
are the plan vs the ADJUDICATION REGISTER — the three places the plan won anyway, plus one place two
decisions contradict EACH OTHER.**)*

### 10.1 — Plan 30 vs the code (found by opening the file)

| # | Plan 30 says | The code says | Consequence |
|---|---|---|---|
| **1** | X-3: assert `OPENABLE.every(p => !!p.guideBodyKey)` | **4 shipped panels DECLARE a `guideBodyKey` whose en i18n key does not exist** ⇒ `UserGuidePanel.tsx:120`'s `t(key, {defaultValue:''})` renders **blank**. The proposed assertion is **GREEN on the live bug.** | `W0-S2` asserts the **EFFECT** (the key resolves) + backfills **5** bodies. |
| **2** | X-4: build "~15 handlers" in Wave 0 | A handler's only job is to invalidate **its panel's query keys** — and those panels **don't exist yet**. Plan 30's own **§8.0b** assigns each handler file to the wave that builds its panel, and warns that two files for one domain **DOUBLE-FIRE**. | `W0-S4` = the **false comment** + the **one** stale domain (`authoring_run`) + **2 mechanical guards**. The other 13 are **distributed**, not deferred. |
| **3** | X-4: "**No handler** for … `kg_create_node`" | `KNOWLEDGE_WRITE_PATTERN` (`knowledgeEffects.ts:16`) is `/^kg_(?!project_list\|graph_query\|…)/` — `create_node` is **not** in the lookahead ⇒ **it already matches.** | Wave 8a must **VERIFY, not ADD**. A second handler is a double-fire (Guard 2 reds). |
| **4** | X-5/PO-3: `ui_show_panel` is "used **outside** the studio, so retirement must keep the non-studio call sites working" | It **doesn't work outside the studio either.** It resolves to `` `${pathname}?panel=…` `` and **the only reader of `?panel=` in the entire frontend** is `PopoutHost.tsx:27`, on the **dedicated `/composition/popout` route**, opened by `window.open` with its own params — **a page the chat is never mounted on.** | **`ui_show_panel` has ZERO working consumers anywhere.** Retirement loses **nothing**. The non-studio migration target (`ui_open_book {book_id, tab}`) **already exists with an enum**. |
| **5** | §9: `stream_service.py` is "**uncommitted, mid-edit RIGHT NOW** … DO NOT TOUCH" | `git status --short` on all four Track-C files → **clean**. Track C landed. | **X-10 is UNBLOCKED** — but the plan makes the builder **re-verify** at build time and **defer, not stop**, if it re-dirties. |

### 10.2 — 🔴 The plan vs the ADJUDICATION REGISTER

> **The rule is "the decision wins."** It won everywhere except these three, and in each the *decisions
> file's own standard of proof* — **the code** — is what overrules it. **Each carries the exact command
> that re-verifies it (pre-flight 1b). If a command now prints the opposite, FOLLOW THE DECISION and log
> the drift.** Do not re-flip these from memory.

| # | The decision says | The code says | Consequence |
|---|---|---|---|
| **6** | `Q-30-404-MOTIF-MINE-POLL`: *"BE-7c … **Zero migration needed** (`created_by` already exists on `generation_job`)"* — and specs **only** the read route. | 🔴 **`migrate.py:268-269`: `project_id UUID NOT NULL, book_id UUID NOT NULL`**, and `generation_jobs.py:159-173` inserts via `INSERT … SELECT $1,$2,**w.book_id**,… FROM composition_work w WHERE w.project_id = $2`. A **synthetic** pid matches no row ⇒ **0 rows inserted** ⇒ `ReferenceViolationError`. **THE JOB ROW IS NEVER CREATED.** | **The read route alone 404s FOREVER** — and its integration test goes **green** on a raw-`INSERT` fixture the producer can never emit (`fixtures-can-seed-a-field-the-writer-never-sets`). **`W0-BE1` ships the WRITER + the DDL.** Everything else in that decision is adopted verbatim. |
| **7** | `Q-30-404-CONFORMANCE-CONFIRM` **and** `Q-30-TIER-W-GENERIC-SPINE` (**and plan 30 §8.1**): *"re-point the chapter conformance estimate/confirm at the generic actions spine."* | 🔴 **`motif_conformance_run.py:74-78`: `if scope != "arc": raise ValueError(…)`.** The worker **terminally rejects `scope='chapter'`** — while the MCP tool happily **mints** for it and `/actions/confirm` **ledger-claims + billing-prechecks + enqueues BEFORE the worker throws.** | **Re-pointing converts a harmless 404 into a PAID JOB GUARANTEED TO FAIL** — the PO's own **CRITICAL** class. 🔴 **`Q-30-404-CONFORMANCE-ESTIMATE` — the DEDICATED decision, and the only one that read the worker — says DELETE. It wins over the other two.** `W0-S7` **deletes** the flow, **hardens the MCP tool to refuse to mint**, and files `D-MOTIF-CONFORMANCE-ENGINE-WIRING`. **This is the single most important fix in this reconciliation.** |
| **8** | `Q-30-X7-GATHER-MOTIFS-LENS` §2: *"`routers/engine.py:391` — **the** real `pack(...)` call site."* | 🔴 **There are FOUR:** `engine.py:391`, `:767`, `:973`, **`grounding.py:103`** — **all four already pass `structure_repo=`** (`grep -c` → 3 + 1). | Wiring only one **re-ships the BA12 bug the decision itself cites**. Its own principle (*"a lens not passed here is a lens that does not exist in production"*) demands **all four**. `grounding.py` is the **context-inspector preview** — miss it and the preview and the real prompt **disagree**. |

### 10.3 — 🔴 Where two DECISIONS contradict EACH OTHER (adjudicate once, here)

| # | The conflict | Resolution |
|---|---|---|
| **9** | **X-12.** `Q-30-SEC11-VS-SEC0-CONTRADICTION` (a′) says *"**do NOT** add a `params` arg to `ui_open_studio_panel`; it keeps `panel_id` (bare id) only"* — grounding it in §8.0 check 5. **`Q-30-X12-PARAMS-ARG` (the DEDICATED decision) says EXTEND IT.** | 🔴 **`Q-30-X12-PARAMS-ARG` WINS** — it is the dedicated adjudication, it confronts the other's argument head-on (*"§8.0 check 5 answers only the `hiddenFromPalette` half; **it is silent on the deep-link half**"*), and it carries the decisive fact the other never addresses: **sealed PO-3 CANNOT BE IMPLEMENTED FAITHFULLY WITHOUT IT** (`ui_watch_job` → `job-detail`, and `JobDetailPanel.tsx:1` says *"singleton, **retargets via params**"*). Because `params` is **OPTIONAL**, both are satisfied: every panel **stays** bare-id openable and **stays** in the enum. **Build `W0-S5b`.** When `W0-S10` rewrites plan 30 §11, **write X-12's answer, not §11's.** |
| **10** | **`regenerate-to-beat`.** `Q-30-TIER-W-GENERIC-SPINE` says drive it **propose→confirm through the `composition.generate` descriptor**. **`Q-30-404-REGENERATE-TO-BEAT` says call `compositionApi.generateAuto` directly and gate on MODEL, not COST.** | 🔴 **The dedicated decision wins.** Its grounds: `POST /generate` **is ungated today for ComposePanel too**; spec 28 **AN-8** says *a new confirmation convention here is a defect*; and the ungated spend is **already tracked once, centrally**, as `D-COMPOSE-GENERATE-UNGATED` — fixed **on the compose path, for both.** Bolting a bespoke estimate/confirm onto this one button **forks the convention.** |

---

## 11 · Slice order (the literal build sequence)

```
── BACKEND FIRST ───────────────────────────────────────────────────────────────
W0-BE1  (BE-7c IN FULL: DDL + create_unbound() + _enqueue branch + read route + MCP)  ─┐
        ▲ the WRITER is the fix. A read route alone 404s FOREVER. (§10 #6)            │
W0-BE2  (BE-11 canon-rule restore)                                                    │
                                                                                      │
── 🔴 CONTRACT-FIRST (CLAUDE.md law) ──────────────────────────────────────────       │
W0-C1   (both new routes → contracts/api/composition/v1/openapi.yaml + parity test) ──┤
        ▲ AFTER the handlers exist, BEFORE the FE consumes them.                      │
                                                                                      │
── 🔴 THE PO'S HOTFIX PAIR (D-2/D-3) — TAKE THESE FIRST IN THE FE BATCH ───────       │
W0-S16  (D-3  the GLOBAL MutationCache.onError — nothing else is silent after this)   │
        ▲ land it EARLY: every later slice's live smoke inherits the safety net.      │
W0-S15  (D-2  Translate stops throwing the user's ticked chapters away)               │
        ▲ discharges T-A4's SELECTION half (D6 stays in Wave T). ONE line, and it is  │
          T-A4's verbatim line. + a test that REDS on the old code.                   │
                                                                                      │
── THE INDEPENDENT BATCH (any order; a stall in one NEVER blocks the wave) ────       │
W0-S1   (X-2  CATEGORY_ORDER + the group LABEL + the compile guard)                   │
W0-S2   (X-3  guideBody × 2 assertions, en-only)                                      │
W0-S3   (X-1  AddModelCta DOCK-7 — followStudioLink + <button>)                       │
W0-S4   (X-4  4.0 kill the string branch → comment → authoringRunEffects → LEDGER)    │
W0-S6   (X-7  gather_motif — 🔴 THE WAVE-3 GATE — all FOUR pack() call sites) ─┐       │
W0-S8   (X-6  AN-12.1 resource_ref — SPEC ONLY, zero code)                     │       │
W0-S9   (X-9  the closed sweep + G-PROFILE-FIELDS + the set_default drift)     │       │
W0-S10  (X-8  doc hygiene + X-11 ref + the 5th token drift + the lint)         │       │
W0-S12  (X-GG4-GATE + 🔴 THE LEGACY_SUBTAB_HOME LEDGER — 7 homeless tabs)      │       │
W0-S13  (X-DIRTY-CLOSE — before ANY new editing panel lands)                   │       │
W0-S14  (X-NEW-CHAPTER — the dead + button)                                    │       │
                                                                              │       │
── THE CONTRACT-REGEN CHAIN — 🔴 STRICTLY SERIAL, NEVER CONCURRENT ────────    │       │
W0-S5   (X-5  retire ui_show_panel; intercept ui_watch_job)   ─┐               │       │
W0-S5b  (X-12 ui_open_studio_panel gains OPTIONAL params)      │ one regen     │       │
W0-S5c  (X-13 delete the 2 dead fields; KILL the silent success)┘ each, in     │       │
        ▲ 00B:203 — "never two concurrent regens".              this order.    │       │
                                                                              │       │
W0-S7   (the live 404 KILL + THE PAID LIVE SMOKE)  ◀── dependsOn BE1 + C1 + S6 ┴───────┘
        🔴 DELETE the chapter conformance flow. Do NOT re-point it. (§10 #7)
W0-S11  (X-10 AN-C2 scent)  ◀── LAST. Re-verify the Track-C gate first.

W0-CLOSE ── the wave close (§7):
             /review-impl studio-wave-0  → EVERY finding FIXED
             LIVE BROWSER smoke on a REBUILT image
             SESSION_HANDOFF (+ the 4 carried defer rows) + COMMIT
             (enumerated paths; panel enum N_after === N_before — NEVER a literal)
```

**The dependency edges are few and each is real:**
`W0-C1` ← `W0-BE1` + `W0-BE2` (a contract describes what exists) ·
`W0-S7` ← `W0-BE1` + `W0-C1` + `W0-S6` ·
`W0-S5b` ← `W0-S5` and `W0-S5c` ← `W0-S5b` (**regen serialization only**).
**Everything else is independent**, so a stall in any one slice **never blocks the wave** — **park it in
the defer register, take the next one, keep going.**

🔴 **The one edge you cannot fudge: `W0-S7` ← `W0-BE1`, and it needs BE1's WRITER, not just its read
route.** At HEAD, `POST /actions/confirm` raises `ReferenceViolationError` and **no `generation_job` row is
ever written** (C-1) — the 500 lands **at confirm, BEFORE the enqueue**, so there is **no job, no worker,
no LLM call.** Until `create_unbound()` + the DDL land, `W0-S7`'s live smoke **has nothing to poll and
cannot pass.** If you see the confirm 500 during the smoke, **`W0-BE1` is incomplete — go finish it.** Do
**not** "fix" it by minting a phantom `composition_work` row (the docstring forbids it), and do **not**
mark `W0-S7` done on a green unit suite: **the unit suite was ALREADY GREEN while ⛏ Mine 500'd on every
single click, in production. That is the whole point of this wave** — and it is also why a read-route-only
"fix" would have shipped green over a still-dead feature
(`fixtures-can-seed-a-field-the-writer-never-sets`).
