# RUN-STATE — S-09 build (small wire-ups over existing repo methods)

> Five narrow route/FE wire-ups the completeness audit named — each exposes a repo/reader that already
> existed but had no reachable caller. Spec: S-09_small-wireups.md. Roadmap: Tier-B, XS–S.
> Cross-service: NONE — every item is a single-service change (no cross-service live-smoke required).

## THE COMMITMENT
Build all five W1–W5. DONE = built + tests (DB-proven where a real DB exists; unit where pure) + committed
per-service, no `git add -A`, atomic pathspec commits (shared checkout).

## INVESTIGATE (verified vs code 2026-07-18 — spec line-refs held)
- W1: `corrections.list_for_job` existed on the repo; only `correction_stats` had a route. Added the GET.
- W2: `project_glossary_entities_to_nodes` (anchor_loader) existed; no public route seeded the graph from
      glossary without prose. Added POST `.../entities/from-glossary` (EDIT-gated, book-less → 400).
- W3 (F-12): the view-aware reader `GET /v1/kg/projects/{id}/graph?view=&as_of_chapter=` (graph_views.py)
      + the FE `ontologyApi.readGraph` client + GraphSlice/GraphReadParams types ALL already existed with
      ZERO callers. Pure FE wire-up — no BE change.
- W4: `resolve_by_book` existed; MCP `list_derivatives` existed; no REST list of a book's derivatives.
      Added GET `/v1/composition/books/{book_id}/derivatives`.
- W5: `submitWikiSuggestion` was INSERT-only; only owner-facing `listWikiSuggestions` (GrantView). Added the
      submitter's DELETE (withdraw own pending) + GET `.../suggestions/mine` (own, WITH status).

## SLICE BOARD (done = evidence)
- [x] W1 — composition `GET /works/{project_id}/jobs/{job_id}/corrections` (VIEW-gated). EVID:
      `test_list_job_corrections` (StubCorrections) PASS. Commit 86148f535.
- [x] W2 — knowledge `POST /projects/{id}/entities/from-glossary` (EDIT-gated, threads owner+book+subset,
      best-effort stats reconcile, book-less → 400). EVID: 3 route tests (whole-glossary / subset / bookless-400)
      PASS. Commit 86148f535.
- [x] W4 — composition `GET /books/{book_id}/derivatives` (VIEW-gated, canonical flag + derivative_name).
      EVID: `test_list_book_derivatives` PASS. Commit 86148f535.
- [x] W5 — glossary DELETE withdraw (submitter, pending-only, anti-oracle 404, 409 reviewed, status='pending'
      predicate on the mutation to close a TOCTOU with a concurrent owner-accept) + GET suggestions/mine
      (no grant — ws.user_id=caller IS the scope). EVID: 4 DB-integration tests green vs live glossary_test
      (withdraw pending 204 / non-submitter 404 / reviewed 409 / mine returns own with status). Commit 515eaab0c.
- [x] W3 (F-12) — ProjectGraphView lens toolbar: saved-view dropdown (useGraphViews) + as-of-chapter input;
      switches to useProjectGraphSlice (readGraph) when a lens is active, else keeps /subgraph + expand.
      Warnings surfaced; empty lens = escapable hint; expand hidden in lens mode. EVID: 13 component
      (subgraph preserved + 7 lens cases) + 4 normalizeSlice units PASS; tsc --noEmit clean. Commit b3e1a050f.

## VERIFY (evidence)
- glossary-service (Go): `go build ./...` clean, `go vet ./internal/api/` exit 0. W5 four tests + the existing
  Suggestion/Review suite green vs live PG (`GLOSSARY_TEST_DB_URL=…/loreweave_glossary_test`).
- composition + knowledge (Py): W1/W2/W4 route tests green (committed 86148f535, prior slice).
- Frontend: `tsc --noEmit` whole-project = 0 errors. W3 vitest 17/17; existing useProjectSubgraph 6/6 (the new
  `enabled` param is backward-compatible, default true). i18n-completeness-gate OK (17 locales × parity;
  +8 knowledge keys gap-filled via scripts/i18n_translate.py, 1 ja key hand-corrected).

## CONVERGENCE NOTES (for sibling sessions)
- **i18n**: added `graph.emptyLens/truncatedLens/hintLens` + `graph.lens.{view,noView,asOf,latest,clear}` to
  `knowledge.json` across all 18 locales. (knowledge namespace — NOT the contested studio.json.)
- **useProjectSubgraph signature**: gained an optional 2nd arg `enabled: boolean = true`. Backward-compatible;
  its only caller is ProjectGraphView.
- **FE ontology types**: `GraphNode`/`GraphEdge` gained optional `kind_label`/`name_label`/`edge_type_label`
  (mirrors the BE reader; additive).
- No shared registry touched (no catalog.ts / panel_id enum / frontend-tools.contract.json).

## REVIEW-IMPL (adversarial pass, 2026-07-18) — 0 HIGH / 0 MED
Verified every new route's tenancy seam against code (not just the gate name):
- **W1** `list_for_job` query is `WHERE project_id=$1 AND job_id=$2` — a job from another project
  returns empty; the VIEW gate is on the SAME project_id's book. No cross-project leak.
- **W2** subset path calls `fetch_entities_by_ids(book_id=…, entity_ids=…)` — the server-resolved
  book_id scopes the fetch, so a caller-supplied cross-book entity_id is simply not returned. Write runs
  as the project OWNER. Engine counting/idempotency/subset/truncation covered by test_anchor_loader +
  the upsert_glossary_anchor idempotency test.
- **W4** is a byte-for-byte field parity twin of the MCP `composition_list_derivatives` (same 6 fields,
  same `resolve_by_book` which filters `status='active' AND NOT pending_project_backfill`). Anti-oracle
  404 via `_gate_book` (OwnershipError→404, tested at the gate level + test_get_work_revoked_collaborator_404).
- **W5** withdraw gates on submitter identity (user_id match), non-submitter→404 (anti-oracle), reviewed→409,
  DELETE predicate repeats `status='pending'` (TOCTOU). `mine` scopes `wa.book_id=$1 AND ws.user_id=$2`.
- **W3** no double-fetch (each hook `enabled` only for its mode — asserted), no silent no-op, escapable empty lens.

**FIXED this pass (fix-now):** W2 now normalizes `entity_ids` exactly like the MCP handler (strip / drop-empty /
empty-list→None) instead of passing the raw body — parity + robustness against a sloppy payload. +2 tests
(`test_from_glossary_normalizes_entity_ids_like_the_mcp_tool`, `…_empty_id_list_becomes_whole_glossary`).

## CONVERGENCE HAND-OFF (contract owner — the glossary contract-first track)
`contracts/api/glossary-service/wiki.yaml` DELETE `.../suggestions/{sug_id}` documents responses `204/403/404`,
but the `withdrawWikiSuggestion` handler NEVER emits 403 (it is submitter-identity-gated, not grant-gated) — it
emits **404** (not found / non-submitter anti-oracle) + **409** (already reviewed). Correct set = **204 / 404 /
409**. Left to the file's owner (their hot file; the method/path conformance gate is green either way — purely a
response-code doc-accuracy nit). Not a defer — a one-line correction for whoever next touches wiki.yaml.

## DECISIONS (S-09-local)
- W5 anti-oracle: a non-submitter gets 404 (not 403) on withdraw so a suggestion_id can't be probed.
- W5 status read needs NO grant — a grant-less community contributor must still read their own outcome
  (`listMyWikiSuggestions` proven correct by the mine-test passing while grantclient failed closed).
- W3 renders BOTH data hooks unconditionally (hooks can't be conditional); each `enabled` only for its mode,
  so no double-fetch. The lens IS the scope → no expand-hop in lens mode.
