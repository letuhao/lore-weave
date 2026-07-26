# Studio Completeness BUILD — code-level AUDIT RESULT (2026-07-18)

> **Why this doc exists.** The build status (S-01…S-13 SHIPPED) had only ever been asserted by RUN-STATE
> files + git commit messages — i.e. self-report. This audit **verified the claims against actual source and
> by RUNNING the tests** (live Postgres :5555, Neo4j :7688 where safe, Go + pytest + vitest), not by trusting
> docs. Method: 4 cold-start sub-agents, one per disjoint service cluster, each grepping real files + pasting
> real test output. This is the falsifiable record.

## Verdict

**All 13 specs COMPLETE at the code + test level.** No claimed data-layer verb is MISSING; no stub, no
unwired route, no MCP function absent from its registry, no built-but-unreachable panel. Every repo method /
route / MCP tool / FE affordance was found in real code, wired (routers mounted, hooks consumed, catalog +
`panel_id` contract registered on both sides), and exercised by a passing test.

| Spec | Owning service(s) | Verdict | Test evidence |
|---|---|---|---|
| S-01 structure-template authoring | composition (Py) | COMPLETE | 11 DB + 6 unit green (live PG) |
| S-01b structure-templates UX hardening | FE | COMPLETE | 18 + 4 FE unit |
| S-02 manuscript parts | book (Go) | COMPLETE | 19 Go `_DB` tests green (live PG) |
| S-02b/S-02c parts reachability + polish | FE | COMPLETE | FE unit (14 nav) |
| S-03 references edit | composition (Py) | COMPLETE | 17 unit + live-PG integration |
| S-04 derivative delta editing | composition (Py) | COMPLETE | 18 + 7 unit + 4 live-PG |
| S-05 KG fact authoring + triage | knowledge (Py) | COMPLETE *(mechanism deviation — below)* | 17 + 406 unit |
| S-05b triage UX hardening (6 slices) | knowledge + FE | COMPLETE | unit green |
| S-06 glossary attribute-value | glossary (Go) | COMPLETE | 5 live-PG + contract-conformance |
| S-07 world-maps OCC + agent verbs | book (Go) | COMPLETE | 7 tests green (live PG) |
| S-08 soft-archive restore | composition (Py) | COMPLETE | 10 unit + 3 live-PG repo |
| S-09 wire-ups W1–W5 | composition + knowledge + glossary | COMPLETE | green across all three |
| S-10 Tier-C FE orphans (7 O-items) | FE (+ composition O3 route) | COMPLETE *(O4 note — below)* | 54 + 26 FE, 27 BE, tsc 0 |
| S-11 search activity-view | FE | COMPLETE | in the 54 FE set; stub confirmed removed |
| S-12 workflows + proposals GUI | agent-registry (Go) + FE | COMPLETE | 12 BE + 77 FE |
| S-13 studio decompose surface | FE | COMPLETE | 119 FE + 14 contract + 22 BE contract |

## Deviations from the sealed specs (NOT gaps — recorded so they stop re-surfacing)

1. **S-05 fact-author mechanism.** Spec §A.2 designed authoring as `POST /v1/knowledge/pending-facts`
   queueing into the review lane (reuse confirm-promotion). The implementation instead writes **straight to
   the graph** via `POST /entities/{id}/facts` → `merge_fact(pending_validation=False, confidence=1.0)`; the
   spec-named `/pending-facts` create route does **not** exist. The user-facing deliverable ("a human authors
   a fact, visible in the curation list") is met, enum-validation (422) is honored, and immediate-write is
   arguably better UX (no second confirm step) — but it is a genuine design departure from the sealed spec.
   **Status: conscious accept** (gate #5). If the review-lane semantics are later wanted, that is a new slice,
   not a bug fix.

2. **S-10 O4 `bible` rail scope.** O4 prose implied the bible rail should list ~13 storyBible panels; the
   shipped rail (`BIBLE_NAV_PANELS`, filtered on `navGroup:'bible'`) surfaces **2** (`divergence`,
   `reference-shelf`). All 15 storyBible-category panels remain **palette-reachable**, so this is NOT a
   built-but-unreachable defect — it is a curated-rail choice already recorded in RUN-STATE_S10 (H-1b).
   `quality` similarly ships a nav entry + launcher button to `QualityHubPanel` rather than a list-rail.
   **Status: conscious accept.** Reachability met; rail curation is looser than the prose.

3. **Cosmetic spec-path drift** (FE/BE agree, functionally fine, spec text stale): S-01 routes are
   `/v1/composition/templates` (not `…/structure-templates`); S-04 keys on `{project_id}` (spec wrote
   `{work_id}`); S-09 W1 is `/works/{project_id}/jobs/{job_id}/corrections` (spec wrote bare `/jobs/…`).

## Test-execution caveat — the env-gated-skip trap (real, matters for CI)

Several DB suites **silently SKIP** without their env var set, so a bare `go test ./...` / `pytest` returns a
misleading `ok` while the load-bearing tests never run (the repo's known
[`env-gated-integration-tests-skip-and-the-green-suite-lies`] class). The audit closed these by pointing them
at live infra:

- **book-service parts (S-02)** — gated on `BOOK_TEST_DATABASE_URL`; re-run vs `:5555/loreweave_book` → 19/19.
- **glossary S-06/W5** — gated on `GLOSSARY_TEST_DB_URL`; re-run vs `:5555/loreweave_glossary_test` → green.
- **knowledge S-05 repo-layer** (invalidate/revalidate on a committed `:Fact`, triage queue): 28 tests gated
  on `TEST_NEO4J_URI` / `TEST_KNOWLEDGE_DB_URL`. **GAP NOW CLOSED (2026-07-18).** Rather than risk the shared
  dev graph, spun a **throwaway isolated Neo4j** (`neo4j:2026.03-community` + APOC on host :7690) + a throwaway
  PG DB (`lw_audit_knowledge` on :5555), ran the two files against them, and tore both down:
  ```
  $ TEST_NEO4J_URI=bolt://localhost:7690 TEST_KNOWLEDGE_DB_URL=…/lw_audit_knowledge \
      python -m pytest tests/integration/db/test_facts_repo.py tests/integration/db/test_kg_triage.py
    38 passed in 11.83s        # was 10 passed / 28 SKIPPED under bare pytest
  ```
  `test_facts_repo.py` (Neo4j: merge_fact idempotence + pass-2 promotion, invalidate sets valid_until,
  list excludes pending/invalidated, cross-user boundary, WS26 supersession + merge-repoints-facts) and
  `test_kg_triage.py` (PG TriageRepo: park/group-by-signature, resolve-batches-pending, glossary handoff,
  cross-tenant + cross-project isolation) all green on real isolated infra. **No execution gap remains.**

## Bottom line

The studio-completeness build is genuinely complete — not just claimed-complete. The two deviations are
conscious-accepts, not defects. The previously-open execution gap (S-05 Neo4j/PG repo layer) has since been
**closed** by running it against throwaway isolated infra (38 passed) — there is now no unrun code path in
this track.
