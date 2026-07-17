# RUN-STATE — S-03 + S-04 build (session: feat/context-budget-law)

> Re-read THIS first after any compaction, then `git log`, then continue.
> Parallel sessions on same checkout: stage only MY files, no `git add -A`, no touching shared
> studio registry (catalog.ts / panel_id enum / frontend-tools.contract.json / i18n) — write to a
> manifest for convergence instead.

## THE COMMITMENT
Build S-03 (references edit) + S-04 (derivative delta editing). Each: DATA-layer verb + REST + MCP
+ FE affordance. **DONE = build complete, tests green with pasted output, /review-impl pass.**

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
- [ ] S3a ReferencesRepo.update_metadata + update_content (repo + unit tests) — EVIDENCE:
- [ ] S3b PATCH metadata + PUT content routes (embed via provider-registry) — EVIDENCE:
- [ ] S3c composition_reference_update MCP tool (metadata-only) — EVIDENCE:
- [ ] S3d FE edit affordance on reference row (+ reachability resolved) — EVIDENCE:
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

## DEBT
- S-04 pov_anchor RE-PICK deferred (gate #2 large/structural): editing shows current + Clear (both usable
  now); re-picking a NEW pov entity needs the glossary entity-search picker wired into the editor. Clear +
  taxonomy + canon + override-CRUD all fully usable. Target: fold into an entity-picker reuse pass.
- S-04 override edit surface = the `description` field (matches wizard Step3 + packer present-lens). Editing
  ARBITRARY overridden_fields JSON is a power-user affordance, intentionally not built (would be a raw-JSON
  shell; the description field is the proven-usable path).

## DRIFT LOG (near-misses — an empty log at end is dishonest)
- (none yet)
