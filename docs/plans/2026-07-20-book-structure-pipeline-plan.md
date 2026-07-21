# Plan / RUN-STATE — Book Structure Pipeline (build)

**Spec:** [`docs/specs/2026-07-20-book-structure-pipeline.md`](../specs/2026-07-20-book-structure-pipeline.md) (v2, adversarially reviewed).
**Goal (committed):** plan + build the spec; **QC + `/review-impl` + a live e2e test per slice** to prove each works.
**Branch:** feat/frontend-tools-mcp-migration. **Started:** 2026-07-20.

## ▶ AUDIT-FIX RESUME (paused 2026-07-21 — user said "clear ALL issues, no debts")

A completeness audit (3 cold-start agents over disjoint phase-code + a solo §6/§8 pass) found the P1–P5
"complete" claim was over-stated. Clearing every gap. **DONE + live-proven:**
- **H1 [x] `d77d7e0b1`** — bulk book trash/purge/restore now emits per-chapter chapter.trashed/deleted/
  RESTORED (new, symmetric); statistics(re-read)/glossary(re-ground)/written-verdict(reconcile) handle
  restored. LIVE: trash→2 trashed, restore→2 restored via the API, consumers clean; emit DB test + glossary
  rule test + 11 verdict tests green.
- **H2 [x] `5d2ddcdb7`** — agent write path `book_chapter_set_part` now validates the target via a NEW
  internal composition parts route (`GET /internal/composition/books/{id}/parts?caller_user_id=`,
  X-Internal-Token + grant-check). LIVE: bad part → "not a live part" (isError), good part → success.
- **H3 [x] `d93e739b7`** — corrected the FALSE "Act One stale" doc claim; KEPT the seed (plan-axis arc,
  clean distinct translations; "Arc 1" machine-translates to 第1章/chapter in CJK — reverted that experiment).

**REMAINING (the resume worklist — every one is fix-not-defer):**
- **M1** — Go regression tests: extract `partIsLiveTarget` + test (live/archived/arc/foreign → the matching);
  resolver lifecycle-gate handler test (trashed → empty skeleton); composition read-filter EXCLUSION DB tests
  (`list_tree` + `resolve_by_book` drop a non-active `book_lifecycle`) + a consumer `_apply` DB test. (The
  behaviours are live-proven; these are the missing AUTOMATED regression guards.)
- **M2** — FE `runAct`-on-FAILURE test: a rejected mutator fires `toast.error` (parts.test.tsx currently
  mocks all mutators as resolved → the error path is untested).
- **M3** — emit ATOMICITY test (inject a mid-tx failure → the lifecycle write + the events roll back together)
  + drive the HTTP + MCP entry paths (currently the DB test calls `transitionBookLifecycleTx` directly).
- **ML1** — FE reads the `/structure` `sources` outage signal → surface "parts unavailable" instead of a
  silent flatten (`useManuscriptTree` reads only `kinds_present.parts`; `sources` is returned-but-unread).
- **ML2** — toggle persistence: `userLens` is in-memory `useState` (resets on reload) → per-device
  localStorage (the spec's §8 lean).
- **L1** — resolver outline-detail half (`outline.arcs` + §6.4 `chapter_id` reconciliation). NOTE: assess a
  consumer first — if none needs the reconciliation, this is a documented conscious-decision, not a build.
- **L2 [x] §6.1 — CONSCIOUS DECISION (verified), a synthetic migration test is infeasible.** The C2/C4
  parts→structure_node mirror is one-time INLINE DDL (no callable function to unit-test) and the pre-C4
  `parts` table is DROPPED (nothing to compare ids against). The concern is already GUARDED: the resolver's
  LEFT-JOIN-safety (a chapter whose link points at a re-keyed / dead / foreign / archived part → Unassigned,
  never dropped, never mass-orphaned) is tested by `TestBuildBookStructure_DanglingLinkNeverDropsAChapter` +
  the conservation assertion. VERIFIED LIVE against real data: of the book-service chapters with a part link,
  the repro book's resolve to a live part (id-equivalence held); one stale orphan exists and the resolver
  correctly routes it to Unassigned. Not a debt — a decision backed by infeasibility + an existing tested guard
  + live verification.
- **L3 [x] §6.3 — has_work two bits DONE.** `structureWork.HasWork` (json `has_work`) is set true whenever a
  Work ROW exists (`decodeStructureWork`: `out.Work != nil`), even for a pending Work whose `project_id` is
  null — DISTINCT from the project-backed bit (`kinds_present.outline` = project_id!=null). A consumer (door,
  CTAs) can now show "pending" vs "absent" instead of conflating them. Tested (decodeStructureWork: pending→
  has_work=true, absent→false) + exposed in the FE `BookStructure` type (+ the previously-undeclared
  `book_lifecycle`). No consumer wired yet (the bit is AVAILABLE; wiring the door is that feature's job — not
  speculatively built here).
- **L4** — FE lazy-expand the skeleton instead of eager full-load (bounded 6000, functionally fine today).
  **L5** — CJK `lensParts` 章节→部 + the broader CJK "part"→幕/章节 mistranslation (add a domain glossary to
  `i18n_translate`, NOT a blind non-native hand-edit).

## Commitment / invariants (re-read after any compaction)
- Resolver owner = **book-service** (holds chapters + the `structure_node_id` join key + lifecycle; calls
  composition for the *small* parts list + active work, bearer-forwarded — the `parts_import.go` pattern via
  `cfg.CompositionServiceURL`).
- **Parts are always read** (book_id-scoped, Work-independent) → Bug 4 can't recur.
- **LEFT-JOIN-safe:** a chapter whose `structure_node_id` points at an arc / foreign / archived / missing
  node falls to **Unassigned**, never dropped, never filed under an arc.
- **No silent seams:** no silent chapter truncation (book-service owns chapters locally — page fully);
  writes validate targets (P2); FE surfaces mutation errors (P2).
- **Rail = mode-by-content + toggle** (parts-only→parts; outline-only→unchanged; both→toggle; neither→flat).
- Each slice: TDD → VERIFY (paste real output) → `/review-impl` → **live e2e** (real stack) → commit.

## Composition endpoints the resolver uses
- `GET /v1/composition/books/{book_id}/parts` → `{items:[{part_id,title,sort_order,lifecycle_state}]}` (arc.py:574)
- `GET /v1/composition/books/{book_id}/work` → active work (`work_id`, `project_id|null`) (works.py resolve_work)

## Slice board (done ⇒ an EVIDENCE string, not a checkmark)
- **P1.1 [x] book-service `GET /v1/books/{id}/structure` resolver** — `book_structure.go` + `_test.go` + route.
  EVIDENCE: 4/4 unit tests (grouping/sort/counts, LEFT-JOIN-safety, chapter-conservation, sources passthrough)
  + `go vet` clean + full api suite green; e2e-live on repro book 019f8027 → `{parts:[Part 1 count 2],
  unassigned 0, kinds:{parts:true,outline:false}, sources:{parts:ok,work:ok}}`. No book-service
  route-conformance gate exists (glossary-only), so no contract entry needed. NOTE: resolver returns the
  parts skeleton + `active_work.project_id` (kinds.outline = project_id!=null, the P1 outline signal);
  chapters lazy-loaded per group by the FE (P1.2).
- **P1.2 [~] FE `useManuscriptTree` reads `/structure` + mode-by-content + `[Parts|Outline]` toggle.** Files:
  structureApi.ts, manuscriptLens.ts (pure), useBookStructure.ts, useManuscriptTree.ts (source now lens-derived),
  ManuscriptNavigator.tsx (toggle). `source` is content-derived so a Work-book WITH parts → 'chapters' → loads
  parts (Bug 4 gone); outline-only → unchanged; partless → flat. EVIDENCE: 147 manuscript tests green (6 new
  lens + refactored hook + navigator + a HIGH regression test) + `tsc --noEmit` clean. `/review-impl` caught +
  FIXED: (HIGH) a /structure ERROR left the rail permanently 'pending' → now degrades to flat; (MED) creating
  the FIRST part didn't flip the lens until the 5s cache expired → invalidate /structure on create/trash/restore.
  e2e-LIVE (browser, vite :5199 → gateway, repro book 019f8027 = Part 1 + a REAL Work = outline mode): the
  Manuscript navigator renders "PART · Part 1 · 2" with Chapter 1 + Chapter 2 nested, the [Parts|Outline]
  toggle present, footer "1 part · 2 ch". Before P1.2 this book was outline-mode → Part 1 HIDDEN (Bug 4);
  now it shows. **P1 COMPLETE — Bug 4 fixed end-to-end (resolver → FE → live browser).**
- **P2.1a [x] Backend write silent-seam:** `setChapterPart` (HTTP, the FE drag path) validates the target is a
  LIVE part of this book via `validatePartTarget` (reuses P1.1's composition fetch) → typed error instead of
  silently accepting any UUID. EVIDENCE: go vet + e2e-live (bad UUID→422 BOOK_PART_NOT_FOUND, good→200,
  null-unhome→200, archived-part→422). review-impl: no HIGH (VIEW/EDIT-gated, 502 on composition outage).
- **P2.1b [x] FE surfaces part-mutation errors** — a `runAct(promise, msg)` wrapper toasts on failure; applied
  to ALL 8 mutation sites (create/rename/trash/restore/drag-move/reorder-up/down). A failed mutation now shows
  a toast instead of silently reverting on reload. EVIDENCE: 34 navigator vitest + tsc clean + browser
  regression (navigator still renders Part 1 + toggle, 0 console errors; the P2.1a 422 is what runAct now
  surfaces). The failed-drag case is the highest-value (a stale/bad part target → 422 → toast, no silent revert).
- **P2.1c [ ] mobile "Move to part…" affordance** (chapter→part is native-drag only — no touch path). DEFERRED.
- **P3 DECISION (user, 2026-07-20): Option C — soft-cascade via a dedicated `book_lifecycle` column.**
  Bounded realization (composition has ~20 book_id-scoped tables; a column on all is XL + leak-prone): put
  `book_lifecycle TEXT DEFAULT 'active'` on the TWO manuscript-structure ANCHOR tables — `structure_node`
  (parts/arcs) + `composition_work` (the Work) — which the spec's own model defines as "the book's manuscript
  structure". The 18 deep planning/generation tables are reached THROUGH a Work → gating the Work covers
  user-facing reads (extending the column to them = tracked follow-up). Order-safe RE-READ (not payload-trust,
  the codebase pattern): the consumer reads `GET /internal/books/{id}/projection` (returns lifecycle_state +
  kind for ANY state) and sets the column. NO kind-gate needed (a diary has no structure_node/composition_work
  rows → the cascade UPDATE is a 0-row no-op). Sub-slices:
  - **P3.1 [x] book-service:** `emitBookLifecycleChanged` (aggregate_type='book', payload {book_id}) via new
    `insertOutboxEventTyped`; a shared `transitionBookLifecycleTx` makes BOTH transition sites (HTTP
    `transitionBookLifecycle` + MCP `mcpTransitionBook`, previously bare-Exec + emit-nothing) transactional +
    atomic-emit. Resolver `getBookStructure` gates on the book's own lifecycle (non-active → empty skeleton +
    `book_lifecycle` marker, no composition fetch). EVIDENCE: new emit DB test green (trash/restore/re-trash/
    purge → 1/2/4 book.lifecycle_changed rows, book_id in payload, lifecycle correct) + **full api suite green
    27.5s (no regression from the tx refactor of the working lifecycle path)** + go vet + db-safety-gate=0.
    Relay auto-routes aggregate_type='book' → `loreweave:events:book` (zero worker-infra change). Inert until
    P3.2's consumer (events pile harmlessly, MAXLEN-trimmed).
  - **P3.2 [x] composition:** migration adds `book_lifecycle TEXT DEFAULT 'active'` to structure_node +
    composition_work; `BookLifecycleConsumer` (own stream `loreweave:events:book` + group, re-reads
    `get_book_lifecycle` → projection → UPDATEs both anchors idempotently, RAISES on 5xx so it never mislabels
    live) wired into worker `__main__`; `list_tree` (structure.py, covers parts+arcs) and `resolve_by_book`
    (works.py, the plan-hub chokepoint) exclude non-active. EVIDENCE: 8 consumer unit tests (wiring/silent-
    success guard, re-read contract, raise-on-outage) + migration applied clean (77+230 rows default 'active').
    No central events SoT (consumer-local REQUIRED_EVENTS is the precedent); book DB already an OUTBOX_SOURCE.
  - **P3.3 [x] live e2e (the real cross-service proof):** login → DELETE /v1/books/{repro} (204) → composition
    mirror flipped `trashed` in 8s (BOTH anchors UPDATE 1) → GET /structure returned **parts=0, kinds all-false**
    (resolver gate + list_tree filter both hiding) → POST /restore (200) → mirror flipped `active` in 25s → GET
    /structure returned **parts=1, kinds restored** (full soft-restore, nothing lost). Baseline (active→parts=1)
    proves the filters DON'T regress active reads. Consumer logs clean, no errors. **P3 COMPLETE — Option C
    soft-cascade proven end-to-end (emit → relay → mirror → gated reads → restore).**
- **P3.1-OLD [scoped] Lifecycle cascade — sealed spec design is WRONG; needs a human call.** Scoping
  against real code found: (1) composition has **no dedicated book-lifecycle column** — `structure_node`
  has only `is_archived`, `composition_work` only `status active|archived`, BOTH *user-archive* flags. The
  spec §4.6 "soft-trash cascade" would overload them → the **un-archive-orphan bug** ([[feedback_symmetric_unarchive_orphans_node]]):
  restore would un-archive acts the user manually archived. (2) **No book-row purge sweeper exists** —
  `purge_pending` is terminal-but-retained (row lingers), so the "orphan" is LOGICAL (dead book, live
  structure) not a physical FK orphan. (3) TWO emit sites: HTTP `transitionBookLifecycle` (server.go:1188,
  non-tx) + MCP `mcpTransitionBook` (mcp_actions.go:880, already in a tx). GOOD NEWS: worker-infra
  auto-relays any `aggregate_type` to `loreweave:events:<type>` (outbox_relay.go:220, default MAXLEN) → the
  emit needs ZERO worker-infra change; composition's `CompositionEventConsumer` (events/consumer.py) is the
  exact consumer pattern to mirror (REQUIRED_EVENTS guard against silent-ack-into-void). **The real value
  (reclaim orphaned composition structure on purge) is a DESTRUCTIVE cross-service hard-delete that
  CONTRADICTS the user's "important data is soft-delete" principle** → surfaced for a design decision
  (options A: hard-delete-on-purge scoped by book_id; B: add a dedicated `book_trashed` column + soft-cascade
  — bigger blast radius; C: read-side resolver lifecycle-join only, non-destructive; D: defer). Kind-gate to
  novel (diary has no composition structure).
- **P4.1 [x] Agent guidance — metadata-vs-structure disambiguation (Bug 2).** Scoping found `book_get`
  ALREADY returns the description (so a NEW read tool would be redundant — Bug 2 is a tool-SELECTION problem,
  not a missing-read one). Fix = sharpen the two write tools so the boundary is unmistakable:
  `book_update_meta` now claims the metadata-field territory ("the ONLY home for a book's description/summary
  … NEVER create a chapter for it") + gains write-imperative synonyms (set/update description|summary|blurb|
  synonym, write the book description); `book_chapter_create` disclaims metadata ("a unit of manuscript PROSE
  … for the book's own description use book_update_meta, do NOT create a chapter"). EVIDENCE: $0 real-model
  selection proxy (Gemma-4 26B via provider-registry, `scripts/eval/tool_liveness/selection.py`, full 274-tool
  catalog as distractors): book tools 90% discoverable (27/30); **book_update_meta correctly picked for "write
  the book description" and NEVER confused with book_chapter_create for a metadata request — the Bug-2 failure
  mode is gone.** A first run mis-picked `book_get` for the ambiguous read-phrase "what the book is about" →
  replaced it with a clear write imperative → HIT. (The description IS deployed: verified book-service /mcp
  tools/list directly; the re-federation needed an ai-gateway restart to bust its tool-list cache.)
- **P5.1 — USER CHOSE TO COMPLETE P5, not defer (2026-07-20). Building all three.**
  - **(a) ensure_work consolidation [x] DONE + verified.** Extracted the canonical-first, F5-fork-safe
    `ensure_work(works, book_id, created_by)` into `app/work_resolution.py` (the ONE primitive); the three
    divergent copies now delegate to it — `plan_forge_service._ensure_work`, `routers/works._ensure_pending_work`
    (keeps its 409 wrapper), `mcp/server._ensure_pending_work` (keeps its ValueError wrapper). SAFETY (the F5
    concern): both pending-only callers are reached ONLY after resolve_work returned `unavailable`/`None` ⇒ 0
    marked Works, so canonical-first is a race-safety net there, not a behaviour change; verified every caller
    just returns the Work (no pending-specific backfill). EVIDENCE: 6 ensure_work unit tests (canonical-first
    returns canonical + NEVER forks a 2nd pending — the F5 regression; derivative≠canonical; existing-pending;
    create-when-none stamping created_by; race re-get; truly-stuck re-raise) + composition service+worker
    rebuilt HEALTHY (all 3 delegation sites import clean) + live `/structure` smoke (work resolution intact).
  - **(b) i18n "part" [x] DONE + verified.** Re-checked vs code (anti-laziness): the act→part TERMINOLOGY was
    ALREADY correct in `en/studio.json` (`actShort='Part'`, `trashAct='Trash part'`, …) — the "Act" I first saw
    was only the DEAD code `defaultValue` fallback (studio.json wins). The real gap: 9 of my P1.2/P2.1b keys
    (`lensParts/lensOutline/lensToggle` + the 6 error toasts `createFailed/renameFailed/trashFailed/
    restoreFailed/moveFailed/reorderFailed`) were `defaultValue`-only (absent from `studio.json` → English in
    every locale). Added them to `en/studio.json` + ran `i18n_translate.py --ns studio` (LM Studio gemma-4-26b,
    gap-fill: +9 new keys × 17 locales, 0 failed, 28s). EVIDENCE: completeness gate GREEN (17 locales × 33 ns at
    full en parity) + spot-check (vi `lensParts='Các phần'`, ja `'パート'`, de `'Abschnitte'` — real per-locale
    translations, not English). **"Act One arc seed" — CORRECTED (I first wrongly called it stale; the audit
    caught that).** It EXISTS: `en/studio.json` `setup.firstStructureTitle="Act One"` → `useBookSetup.ts` →
    `usePlanOrigin.createArc(kind='arc')`, localized in all 18 locales. CONSIDERED DECISION to KEEP it (a
    decision with evidence, NOT a debt): it seeds a PLAN-axis ARC, and Decision 4's "part" rule governs the
    MANUSCRIPT axis, not the plan; "Act One" is dramaturgically standard AND translates DISTINCTLY everywhere
    (第1幕 / Erster Akt / Acte I), whereas retitling to "Arc 1" machine-translates to 第1章 (Chapter 1) in
    Japanese — reintroducing a WORSE arc/chapter conflation (verified live via i18n_translate, then reverted).
  - **(c) route parts_import + arc-grouped Chapter Browser through the pipeline [x] VERIFIED — no real gap
    (targets already-centralized or design-incompatible; not a defer, a code-checked finding).**
    (i) `parts_import.go::groupImportedChaptersIntoParts` is a correct best-effort WRITE (creates composition
    parts + stamps `chapters.structure_node_id`) — NOT a divergent read; there is no read-pipeline to route a
    write through. (ii) `books/hooks/useChapterBrowserGroups.ts` (the arc-grouped browser) ALREADY reuses the
    shared composition primitives (`useWorkResolution` + `compositionApi.listOutlineChildren`, per its DOCK-2
    docstring) — it is not a fork/divergent read; it builds a flat `chapter_id→arc_id` map. Routing it through
    `/structure` is INCOMPATIBLE with the resolver's skeleton design (§4.2 "headers + counts, NOT inline
    chapters"): the browser needs the full arc→chapter MEMBERSHIP the skeleton omits by design, and even the
    spec's `outline.arcs` counts wouldn't supply it — so there is no benefit + a design conflict. (iii) The
    ONE genuine divergent read (the manuscript rail, Bug 4) was centralized onto `/structure` in P1.2.

## Correctness must-fixes (fold into the touching slice)
- Verify C4 migration UUID-equivalence (test) · `has_work` = two bits (row-exists vs project-backed) · outline/part identity reconciliation.

## Registers
- **Decisions:** owner=book-service; rail=mode-by-content+toggle; drop eager-provision; P4=metadata-vs-structure; kinds_present.outline = the resolved active Work's `work.project_id`!=null (mirrors the FE's resolveActiveWork; a lazy/null-project Work ⇒ outline=false = 'chapters' mode).
- **Parked:** —
- **Debt:** (1) MED — no unit/contract test pins composition's `/parts` response shape the resolver parses (a
  field rename silently degrades parts to empty). `/work` shape now has `decodeStructureWork` regression tests;
  `/parts` still relies on the e2e. (2) LOW — the MCP tool `book_chapter_set_part` (agent path) is NOT yet
  target-validated like the HTTP path: the MCP ctx has `user_id` but no user bearer, and composition's `/parts`
  is bearer/VIEW-gated, so validation needs a new composition internal parts route (X-Internal-Token + X-User-Id).
  Mitigated: the resolver's LEFT-JOIN-safety makes a bad agent target read as Unassigned (visible, not lost).
  (3) LOW — the P4 selection proxy surfaced 3 PRE-EXISTING synonym overlaps (unrelated to Bug 2, out of P4
  scope): `book_chapter_update_meta` ships "reorder chapter" (that's `book_chapter_reorder`'s job);
  `book_index_chapter` "extract knowledge" collides with `kg_build_graph`; `book_search` "where in the book"
  collides with `story_search`. A synonym-hygiene sweep, not a P4 fix. (4) LOW — bounded-Option-C put
  `book_lifecycle` on 2 anchor tables; the 18 deep book-scoped tables rely on the Work chokepoint gate — a
  belt-only column on them is a follow-up if a direct-by-book_id read of one is ever added.
- **Drift:** (P3) The sealed spec (§4.6/§7) prescribed a "soft-trash / restore / hard-delete cascade" of
  composition structure. Scoping against real code proved that design partially WRONG: composition has no
  dedicated book-lifecycle column, so a soft-trash cascade would ride `is_archived`/`status` and reintroduce
  the un-archive-orphan bug on restore. A sealed decision that turns out wrong + a destructive cross-service
  op = a mandatory human checkpoint (WORKFLOW.md), so P3 was STOPPED at design and surfaced rather than
  autonomously built. This is why "scope the slice against real code before building" is in the goal.
- **Drift:** P1.1 `/review-impl` + the Work-book e2e caught a REAL parse bug — `fetchStructureWork` read the top-level `book_project_id` (null for a resolved work) instead of the nested `work.project_id`, so kinds.outline was ALWAYS false → the FE toggle would never appear for a planned book. FIXED + regression-tested (`decodeStructureWork`) + re-e2e'd (repro book with a real Work → outline:true, parts still present). This is why e2e-per-slice is in the goal.
