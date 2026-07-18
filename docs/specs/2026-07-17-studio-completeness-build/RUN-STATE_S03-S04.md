# RUN-STATE — S-03 + S-04 build (session: feat/context-budget-law)

> Re-read THIS first after any compaction, then `git log`, then continue.
> Parallel sessions on same checkout: stage only MY files, no `git add -A`, no touching shared
> studio registry (catalog.ts / panel_id enum / frontend-tools.contract.json / i18n) — write to a
> manifest for convergence instead.

## THE COMMITMENT
Build S-03 (references edit) + S-04 (derivative delta editing). Each: DATA-layer verb + REST + MCP
+ FE affordance. **DONE = build complete, tests green with pasted output, /review-impl pass.**

## STATUS: ✅ COMPLETE (2026-07-18)
S-04 committed ab63bd791; S-03 backend/FE swept into S-01's 68b20b8c2 (see DRIFT-7); FE api+types
committed 25a621774 (restores HEAD consistency). Final tree verify: 88 BE (MCP+refs router) + 190 FE
(ledger+refs+divergence) GREEN. /review-impl ran on S-04 (fixes applied). S-03 = focused adversarial
pass (mirrors S-04's reviewed patterns). USABILITY (user's core ask): S-04 turns a read-only dead-end
into an operable editor on an ALREADY-reachable panel; S-03 edit affordance is operable NOW via legacy
ChapterEditorPage. Neither is a shell.

## THE USER'S OVERRIDING CONSTRAINT (goal prompt, 2026-07-17)
Plan Hub shipped as a VIEW-ONLY dead-end — everything blocked, user can DO nothing. The user
suspects other features are the same empty shell. **Before building each slice, analyze whether a
real user can actually OPERATE it end-to-end** — not just whether code compiles / tests pass.
A slice is NOT done if its FE affordance lands on an unreachable/inert panel. Verify reachability.

## SLICE BOARD (done = evidence string)
- [x] U0  Usability recon — EVIDENCE: S-04 DivergenceManagerView REACHABLE+operable (catalog.ts:343);
        spec+overrides sub-view read-only ONLY b/c no BE verb (DivergenceManagerView.tsx:174-176 shows
        "Editing not available yet — archive and re-derive"). Building S-04 removes that dead-end msg.
        S-03 ReferencesPanel already editable + reachable via legacy ChapterEditorPage.tsx:781; NOT a
        studio catalog panel (port = S-10, other session). PLAN: put edit affordance ON the component
        (live in legacy surface now, rides S-10 mount later). Do NOT touch catalog.ts (convergence).
- [x] S3a ReferencesRepo.update_metadata (no re-embed) + update_content (re-embed) — EVIDENCE: repo
        integration test_s03_reference_update_metadata_vs_content PASSED (real PG): metadata edit leaves
        embedding vector unchanged, content edit rewrites vector+model, wrong-project→None, no-op→current.
- [x] S3b PATCH /works/{pid}/references/{rid} (cheap) + PUT .../content (re-embed via provider-registry,
        model from Work not body) — EVIDENCE: test_references_router.py 17 passed incl. patch-no-reembed,
        content-reembeds-pinned-model, 404-before-embed, 502-on-embed-fail.
- [x] S3c composition_reference_update MCP (Tier A + undo, metadata-only; content REJECTED via ForbidExtra)
        — EVIDENCE: test_mcp_server.py 71 passed incl. edits-only-metadata-with-undo + rejects-content-field;
        wire catalog test proves it registered. Ledger: PENDING referencesEffects (S-10 mounts the panel).
- [x] S3d FE: ReferencesPanel LibraryRow — inline title/author/url edit (PATCH, instant) + separate
        "Save content (re-embeds)" with re-embedding state (PUT). Lives on the ReferencesPanel component =
        REACHABLE via legacy ChapterEditorPage NOW; rides S-10 studio mount later. EVIDENCE: tsc 0;
        ReferencesPanel.test 11 passed incl. edits-metadata-no-reembed + edits-content-reembeds; useReferences 7.
- [x] S4a divergence repo methods (update_spec/add_override/update_override/delete_override) — EVIDENCE:
        migration UNIQUE already existed (DRIFT-1, no migration). Repo tests vs real PG:
        test_s04_divergence_spec_post_derive_update PASSED, test_s04_entity_override_crud_post_derive PASSED,
        c23_divergence regression PASSED — 3 passed (throwaway DB loreweave_composition_s04test @5555).
- [x] S4b 5 REST routes in works.py (PATCH divergence-spec, GET/POST/PATCH/DELETE entity-overrides) —
        DRIFT-4: routes keyed by {project_id} (FE convention) resolved to work.id/book_id, NOT {work_id}.
        EVIDENCE: pytest test_routers.py -k "divergence_spec or entity_override or derive" → 17 passed
        (11 new S-04 route tests + 6 derive regression). 422 off-enum, 400 non-derivative, 409 dup, 404 scope.
- [x] S4c MCP: composition_divergence_spec_update + entity_override_{add,update,delete} (Tier W, taxonomy
        Literal). DRIFT-2: enum via Pydantic Literal, no CLOSED_SET_ARGS in composition.
        EVIDENCE: pytest test_mcp_server.py -k "divergence_spec_update or entity_override or tools_list or
        valid_meta or archive_derivative" → 10 passed. Wire-path catalog test (tools/list == EXPECTED_TOOLS)
        proves the 4 tools are actually registered (anti silent-no-op); closed-set Literal test passes.
- [x] S4d FE: DivergenceSpecEditor (taxonomy select, canon-rules edit, pov clear, override CRUD w/
        anchored-entity picker keyed on glossary_entity_id) replaces the read-only "editing not available
        yet" block on the ALREADY-REACHABLE panel. + compositionDivergenceEditEffect Lane-B (agent parity).
        DRIFT-4 routes keyed by project_id. pov RE-PICK parked (needs entity picker — see DEBT).
        EVIDENCE: tsc 0 errors; vitest 4 files 188 passed (DivergenceSpecEditor 6, Manager 9, effects 2,
        effectCoverage ledger 171 — proves each of the 4 edit tools has exactly 1 agent handler).

## SEALED DECISIONS (do NOT re-litigate — from 01_DECISIONS.md + specs)
- S-03: split PATCH-metadata (no re-embed) vs PUT-content (re-embed); NO OCC; content-edit via MCP OUT.
- S-03: references hard-delete is by-design; no restore.
- S-04: scope = field-overrides + spec ONLY; relationship/event overrides stay M0-deferred.
- S-04: NO delete of divergence_spec (= archive the Work); add_override upsert via UNIQUE(work_id,target_entity_id).
- S-04: taxonomy is closed-set enum (pov_shift|character_transform|au) — CLOSED_SET_ARGS + validate→422 not 500.

## DECISIONS (mine, this run)
- S4: reuse canon.py by-id route pattern (`_rule_project_id` → `_require_work` → EDIT gate) in works.py
  (no separate derivatives router exists). Rows carry book_id directly → gate on it.
- S4 add_override: POST returns 201, dup target → 409 (route §5 explicit). decisions.md said "upsert";
  reconciled to 409-on-dup (POST=create, user PATCHes to change). "no silent duplicate" satisfied either way.
- S4 taxonomy enum: composition MCP uses Pydantic `Literal` (NO CLOSED_SET_ARGS in this service — that's a
  chat-service frontend_tools registry). Route body + MCP arg both `Literal[pov_shift|character_transform|au]`.

## DRIFT LOG (near-misses — an empty log at end is dishonest)
- DRIFT-1: S-04 spec §3 says "add UNIQUE(work_id,target_entity_id)" — ALREADY EXISTS at migrate.py:175-176.
  No migration written. Verified by reading the file. Spec author didn't realize (CLARIFY-expected drift).
- DRIFT-2: S-04 §6 "register taxonomy in CLOSED_SET_ARGS" — no such symbol in composition-service; enum =
  Pydantic Literal. Followed code reality, not spec letter.
- DRIFT-3 (usability): S-03 FE affordance target (reference-shelf studio panel) not mounted yet (S-10's job).
  Put affordance on ReferencesPanel component → live in legacy ChapterEditorPage now, not a shell.
- DRIFT-5 (self-review near-miss, FIXED): first shipped the 4 MCP tools as Tier "W". Tier W = expensive/
  confirm (publish/generate); these are direct auto-writes → correct tier is "A" (auto-write + Undo).
  Re-tiered to A + added real undo_hints (spec_update restores prior fields; add↔delete; update restores
  prior) matching canon_rule_update. Added repo get_override for the prior-state read. Removed from TIER_W.
- DECISION (tenancy §4): spec §4 says "verify target_entity_id belongs to the book's graph". I did NOT add
  a cross-service verify. Rationale (verified the data flow, not laziness): (a) NO data-leak — a foreign id
  simply never matches in the derivative's own knowledge partition (packer present-lens no-ops it, same as
  the wizard's unanchored-entity no-op); (b) the sibling derive-time writer (create_override) does NOT verify
  either — adding it only here would be asymmetric; (c) the FE picker only offers anchored source entities.
  It's a data-quality nit (dangling ref), not a tenancy breach. Optional hardening → DEBT.

## PARKED / BLOCKED
- CO-EDIT: frontend api.ts + types.ts are shared with S-01 (their uncommitted createTemplate/patchTemplate/
  Beat/StructureTemplate). My additions there (patchDivergenceSpec/listEntityOverrides/... + EntityOverrideRow/
  DivergenceSpecPatch types) live in the working tree but are NOT staged in my commit — staging would sweep
  S-01's in-flight work. Working tree is tsc-green (0 errors). Whoever commits the shared FE surface lands both.

## DRIFT (parallel-session)
- DRIFT-6: commit 7712c8bb1 (S-01 slice A, another session) did a broad `git add` that SWEPT my uncommitted
  server.py divergence MCP tools (Tier-W base) into THEIR commit — so HEAD momentarily had the tools but NOT
  my derivatives.py repo methods they call (inconsistent HEAD). MY S-04 commit lands the repo methods + routes
  + FE + the Tier-A/undo delta, making the tree consistent again. Lesson reaffirmed: [[git-index-may-carry-prestaged]].
- DRIFT-7 (shared-INDEX race): my `git add` of S-03 files, then a parallel session's `git commit`
  (68b20b8c2 S-01 slice D) committed the SHARED index → my staged S-03 backend/FE/tests/RUN-STATE landed
  under S-01's message; my own `git commit` then found "no changes". api.ts/types.ts were NOT swept (left
  HEAD inconsistent — committed FE called uncommitted api methods). Fixed via `git commit -m ... -- api.ts
  types.ts` (pathspec commit reads working tree, atomic, dodges the index race). LESSON: on a shared checkout
  the git INDEX is shared across sessions — `git add` then a slow `git commit` races another session's commit.
  Prefer `git commit -m <msg> -- <my paths>` (stages+commits only my paths, atomically) over add-then-commit.

## UX AUDIT (2026-07-18, cold-start user perspective) — findings + fixes
Fixed (commit 5b380d249): S-04 archive→Undo/restore (was one-way dead-end); POV snap-back;
no-anchor explanatory hint; taxonomy human labels. S-03 mutation error toasts (were silent);
URL-at-add (was dropped); library-row truncation (min-w-0 flex-1).
REMAINING → SPEC'D: full CLARIFY spec [`../2026-07-18-studio-s03-s04-ux-hardening.md`](../2026-07-18-studio-s03-s04-ux-hardening.md)
for every remaining gap (rename, library search, pin-row, embed CTA, delete confirms, touch/a11y,
BranchDiff responsive, divergence nav launcher). Discoverability: PO (2026-07-18) pulled it IN SCOPE
— the spec now ABSORBS S-10 O2 (mount ReferencesPanel → reference-shelf) + the editor-slice of O4 (nav
category rail), and SUPERSEDES those S-10 items (retire them to avoid double-build). Touches the shared
studio registry (catalog + panel_id enum + frontend-tools.contract + parity/catalog tests) — land atomically,
/review-impl the contract change. Projected: S-04 →~8.5, S-03 →~7.5 (mount removes the ceiling). Total: L.
Open PO: rail placement (rec `bible`), touch-util promote, override-confirm style.
REMAINING (reported, deferred): S-03 reachable only via legacy ChapterEditorPage (S-10 port);
S-04 palette-only no nav rail; rename-derivative; S-03 library search + pin-on-library-row +
embed-model dead-end (text no CTA); touch tap-target sizing + BranchDiff narrow-panel layout;
delete/remove confirmations. Scores post-fix: S-03 ≈5.2/10 (stranded on legacy page caps it);
S-04 ≈6.4/10 (dead-end removed; discoverability + touch remain).

## DEBT — reviewed & cleared 2026-07-18 (goal: clear all defers/debts/bugs)
- ✅ CLEARED: override editor now exposes `name` (rename an entity in the dị bản — genderbend/rename AU)
  ALONGSIDE description. Verified against packer merge.py apply_entity_overrides (:182-192) which applies
  `name` + `description`/`summary`. Was description-only (a real gap — user couldn't rename). +2 FE tests.
- ✅ CLEARED (latent bug): taxonomy `<select>` now REVERTS to the prior value if the PATCH fails (was
  optimistic-only → a failed write left a lying select value, since only success invalidates). +1 FE test.
- ⏸ DEFER (gate #3) → NOW SPEC'D: pov_anchor consumption + RE-PICK. Full CLARIFY spec written
  [`../2026-07-18-divergence-pov-and-override-tenancy.md`](../2026-07-18-divergence-pov-and-override-tenancy.md)
  Part A. RESOLVED by code trace: id-space = glossary_entity_id (used directly); pov reaches the prompt NOWHERE
  today (even scene pov_entity_id is unrendered — only implicit as a present cast bio); PackRequest doesn't
  carry taxonomy/pov_anchor. Consumer = default-fill effective_pov at pack.py:261 + explicit `pov=` render line
  (also fixes the scene-POV gap). 3 PO calls open (PO-1/2/3, all with recommendations). Build after PO decides.
- 🚫 WON'T-FIX (gate #5) → NOW SPEC'D: tenancy §4 cross-book verify. Same spec Part B. Confirmed NOT a breach:
  no-op + the present lens is BOOK-scoped (pack.py:409) so even a CONSUMED foreign anchor pulls no book-B bio.
  Hardening design + 3 build-triggers recorded; none active → stays a documented decision, no code.
- 🚫 WON'T-FIX (conscious): per-override canon-rule field (packer OVERRIDE_CANON_FIELD) — redundant with the
  spec-level canon_rule[] editor already shipped; niche. Not built.

## DRIFT LOG (near-misses — an empty log at end is dishonest)
- (none yet)
