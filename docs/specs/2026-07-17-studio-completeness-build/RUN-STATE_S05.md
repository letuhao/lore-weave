# RUN-STATE — S-05 build (KG fact authoring/invalidation + triage queue panel)

> Re-read THIS first after any compaction, then `git log`, then continue.
> Parallel sessions on same checkout: stage ONLY my files, no `git add -A`, no touching shared studio
> registry (catalog.ts / panel_id enum / frontend-tools.contract.json / i18n) — write to a manifest
> section (below) for the convergence node to wire instead.

## THE COMMITMENT
Build S-05 = Part A (human fact AUTHOR + INVALIDATE routes + FE affordance on EntityDetailPanel) +
Part B (kg-triage queue panel, pure FE wire-up over a complete backend).
**DONE = build complete, tests green with pasted output, /review-impl pass.**

## THE USER'S OVERRIDING CONSTRAINT (goal prompt, 2026-07-17)
Plan Hub shipped as a VIEW-ONLY dead-end — everything blocked, user can DO nothing. The user suspects
other features are the same empty shell. **Before building each slice, analyze whether a real user can
actually OPERATE it end-to-end** — not just whether code compiles / tests pass. A slice is NOT done if
its FE affordance lands on an unreachable/inert panel, or if the write it makes vanishes from the UI.

## U0 — USABILITY RECON (verified against code 2026-07-17)
### Part A host panel — REACHABLE + OPERABLE ✅ (not a Plan-Hub dead-end)
studio → `kg-entities` catalog panel (category `knowledge`) → mounts `EntitiesTab` → click entity →
`EntityDetailPanel` slide-over. That panel already has Edit/Merge/Link/Archive/promote/unpin + a
relation "mark wrong" (RelationRow → RelationEditDialog). So the fact affordances land on a live surface.

### Part A — THREE empty-shell TRAPS if we follow the spec literally (author→pending→confirm as-is):
- **T1 confidence floor**: `list_facts_for_entity` defaults `min_confidence=0.8`. The existing confirm
  path writes every pending fact at `_TOOL_FACT_CONFIDENCE = 0.7` + `source_type="llm_tool_call"`
  (pending_facts.py). A human-authored fact confirmed that way = 0.7 < 0.8 → **invisible in the very
  panel that authored it.**
- **T2 no ABOUT edge**: `_promote_pending_fact` only creates `(:Fact)-[:ABOUT]->(:Entity)` when the fact
  has subject+project_id+event_date (the diary/temporal path). A fact authored ABOUT entity X gets no
  ABOUT edge on confirm → `list_facts_for_entity` (MATCH on the ABOUT edge) never returns it, even at
  high confidence.
- **T3 review-lane reachability**: the "pending inbox" is the chat `PendingFactsCard` / diary inbox — a
  different feature, not obviously reachable from the KG entity panel. Author-here-confirm-in-chat is
  disjointed.
- **T4 (label) 6-vs-4**: FE `EntityFactType` = 4 values (decision|preference|milestone|negation);
  BE `FactType` = 6 (adds statement|commitment). `FACT_TYPE_LABEL` has only 4 keys. Author form offering
  6 → a `statement`/`commitment` fact renders a blank/crash label. The projection route docstring also
  says 4. → Author form must offer the SAME set the FE can render (start with the 4), OR extend FE to 6.
- **T5 (section hidden on empty)**: the facts `<section>` renders only `when facts.length > 0`. If
  "+ Add fact" lives inside it, an entity with zero facts (the case that most needs authoring) can never
  add one. → the Add-fact CTA must live OUTSIDE that guard.

### Part A — T2b: THE DEEPEST TRAP — the fact list is ALREADY a silent empty shell (pre-existing bug)
`useEntityFacts` calls `getEntityFacts(entityId, {})` with NO `before_chapter_id`, ALWAYS.
`resolve_before_order(None)` → `(FAIL_CLOSED_BEFORE_ORDER = -1, False)` (spoiler_window.py:40). Projection
cypher: `($before_order IS NULL OR f.from_order <= $before_order)` → with before_order=-1 → `f.from_order
<= -1` → **no fact passes** (orders ≥ 0; a NULL from_order human fact fails too). ⇒ **the EntityDetailPanel
"known facts" list renders EMPTY in the studio, always.** The C9 test (`EntityDetailPanelC9`) MOCKS the API
response (`setFacts`), so it's green while the real route returns [] — the exact "mock-hides-server-filters"
lesson. This is the user's thesis proven: a shipped-and-green feature that's a silent empty shell.
**REQUIRED FIX for operability**: the author-facing curation view must NOT spoiler-fail-closed. Add a
`curation: bool = False` query param to `GET /entities/{id}/facts`; when true, skip `resolve_before_order`
and pass `before_order=None` (whole-book, no window — the hook's own stated intent). FE `useEntityFacts`
passes `curation=true`. Reader surfaces keep passing `before_chapter_id` → unchanged. Without this, "+ Add
fact" writes a fact that never shows (from_order NULL) = empty shell squared.

### Part A invalidate — OPERABLE ✅
"mark wrong" per committed fact → POST /facts/{id}/invalidate → fact drops from the list (mirrors the
existing relation mark-wrong). `get_fact` (facts.py:415) exists for the before-snapshot.
Note: learning-service mining consumes `target_type IN ('entity','relation','event')` — NOT 'fact'
(mining.py:214). So a `fact_corrected` event is audit/symmetry only; it does NOT yet feed learning. → DEBT.

### Part B triage panel — buildable + operable IF reachable + has data
Backend COMPLETE (triage.py: list/resolve/dismiss, grant-scoped). FE api `ontologyApi.listTriage/
resolveTriage/dismissTriageItem` exist with ZERO callers. Building the panel is real IF: (a) it's added
to the catalog + nav (convergence node), (b) suggested_actions→buttons drives the real routes, (c) there
is triage data (extraction that missed schema) — empty state is legit but live-smoke must seed one item
to prove the resolve loop. Spec says category `storyBible`; all sibling kg-* panels are `knowledge` →
lean `knowledge` for discoverability (flag; 01_DECISIONS did not seal it).

## SLICE BOARD (done = evidence string) — RESTRUCTURED after PO chose direct-write
Design = user-authored EVENT/ENTITY pattern: `merge_fact(subject_id=entity_id, source_type='manual',
confidence=1.0, provenance='human_authored', pending_validation=False)`. No pending queue.
- [x] U0  Usability recon — EVIDENCE: this file §U0 (traps T1–T5 + T2b pre-existing empty shell found)
- [x] S5-BE1 read-fix: `GET /entities/{id}/facts?curation=true` → before_order=None (whole-book) + test — EVIDENCE: test_fact_authoring.py test_curation_read_skips_spoiler_window + test_reader_read_still_fail_closed; 8 passed
- [x] S5-BE2 author route `POST /entities/{id}/facts` (merge_fact manual/1.0, owner-check entity, FactType→422) + test — EVIDENCE: test_author_fact_happy/_bad_type_422/_cross_user_404/_all_six_types; asserts conf=1.0+manual+human_authored+subject_id
- [x] S5-BE3 invalidate route `POST /facts/{id}/invalidate` + FACT_CORRECTED/fact_snapshot in outbox_emit + test — EVIDENCE: test_invalidate_fact_happy/_404; `8 passed in 3.15s`; +17 passed w/ relation_correction (no regression)
- [x] S5-FE1 EntityDetailPanel: useEntityFacts curation=true, Add-fact form (6 types), mark-wrong; api+hooks; label fix — EVIDENCE: 20 FE tests pass (EntityDetailPanel + C9); tsc exit 0; i18n gate 17 locales PASS; commit 0a5c930e5
- [x] S5-FE2 kg-triage panel (GG-8) + triageEffects Lane-B + deep-links + convergence manifest — EVIDENCE: TriageQueue+hook+panel built; 6 TriageQueue tests + 33 (w/ effects handlers) pass; tsc 0; i18n 17 locales; effects folded into ONE /^kg_/ handler; CONVERGENCE_MANIFEST_S05.md written (catalog/panel_id/studio.json for convergence)

## COMMITS (mine)
- b27e2ec80 BE: author + invalidate + curation read-fix (8 tests)
- 0a5c930e5 FE: EntityDetailPanel affordance (20 tests)
## SHARED CHECKOUT NOTE: sibling sessions committing to same branch (S-01 7712c8bb1, S-02 b56725e05). git pull --rebase before push.
## VERIFY CONSTRAINT (user, 2026-07-17): multi-session ⇒ live-smoke on an ISOLATED STATIC FE build on
##   its OWN free port. Do NOT use the shared vite dev / :5174 (N sessions share one HMR → remounts fake
##   bugs; a host vite dev SHADOWs the baked :5174). Build the image / `vite build` + preview on a free port.
- [ ] VERIFY pasted output + 2-stage review + /review-impl + live-smoke ≥2 svc — EVIDENCE:

## SEALED DECISIONS (do NOT re-litigate — 01_DECISIONS.md)
- CV-2: NO new `memory_invalidate` MCP tool — `_handle_memory_forget` (executor.py:726) already calls
  invalidate_fact; agent parity on both verbs exists. Human routes ONLY.
- Tenancy: fact/pending-fact authorable/invalidatable only by its owner within an accessible project.
- Part A adds HUMAN routes only. Triage backend is complete — CONSUME it, do NOT touch it.
- By-design: in-place fact UPDATE does not exist (bitemporal = invalidate + re-assert). Do not build.

## DECISIONS (mine, this run)
- **PO D-S05-authorflow (2026-07-17, AskUserQuestion): DIRECT-WRITE, show immediately.** Human authors a
  fact about their own entity → write STRAIGHT to `:Fact` ABOUT the entity at HIGH confidence
  (provenance=`human_authored`), appears in the list at once. NO pending queue for human authoring (the
  pending lane gates AGENT proposals; self-review is pointless friction). Invalidate stays for fixing
  mistakes. This deviates from spec Part A ("author queues to pending") — sealed by PO, records the T1/T2
  empty-shell traps as the reason. **Route shape**: entity-scoped `POST /v1/knowledge/entities/{id}/facts`
  (NOT `POST /pending-facts`) — the fact is ABOUT an entity, so scope it to the entity; owner-checked.
- FactType label 6-vs-4 (T4): extend FE `EntityFactType` to all 6 + add statement/commitment labels so
  the author form can offer + render all 6 (no blank labels). knowledge-namespace i18n = my feature's
  strings (not the shared studio.json convergence node) → add en keys, i18n tool gap-fills locales.

## PARKED / BLOCKED
- (none yet)

## DEBT
- learning-service mining does not consume `target_type='fact'` (mining.py:214) → `fact_corrected`
  events are audit-only until a mining IN-list extension. Separate service; tracked, not fixed here.

## DRIFT LOG (near-misses — an empty log at end is dishonest)
- Spec Part A "reuse confirm-promotion as-is" would ship an empty shell (T1+T2). Deviating to make the
  confirmed human fact actually appear on the entity — recorded, not silently done.
