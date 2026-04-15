# Session Handoff — Session 40 END (K11 cluster fully closed — K11.9 ✅)

> **Purpose:** Give the next agent complete context. **K11.1 → K11.9 are all done. Track 2 extraction pipeline (K15 pattern extractor, K17 LLM extractor) is next.**
> **Date:** 2026-04-15 (session 40)
> **Previous handoff:** `SESSION_HANDOFF_V15.md` (K11.1 → K11.8)
> **Source of truth for all state:** `docs/sessions/SESSION_PATCH.md` → "K11.9 Evidence count drift reconciler" entry

---

## 1. TL;DR — K11.9 reconciler shipped, K11 cluster closed

Session 40 shipped K11.9 (offline evidence_count drift reconciler) end-to-end through the 9-phase workflow. Two commits: the feature + the R1 second-pass review-fix. Every R1 round in this sub-project has found at least one real bug — K11.9's was a defensive-paranoia gap around cross-user EVIDENCED_BY edges that would have let the reconciler mask real drift by counting rogue edges.

```
K11.1 Neo4j compose service                        ✅
K11.2 Neo4j async driver wiring                    ✅
K11.3 Cypher schema runner                         ✅
K11.4 Multi-tenant Cypher query helpers            ✅
K11.5 entities repo (K11.5a + K11.5b)              ✅
K11.6 relations repo                               ✅
K11.7 events + facts repos                         ✅
K11.8 provenance repo                              ✅
K11.9 evidence_count drift reconciler              ✅  ← this session
K11.10+                                            ⏸️
```

Test count: **547 passed, 93 skipped** against live Neo4j 2026.03.1 (the 3 failures + 14 errors elsewhere are the pre-existing `personal_kas.cer` SSL truststore environment issue — unrelated to K11, documented in SESSION_PATCH Won't-fix).

---

## 2. What K11.9 actually is

A pure async function — `reconcile_evidence_count(session, *, user_id, project_id=None)` — that scans `:Entity|:Event|:Fact` nodes for a given user and corrects any drift between the cached `evidence_count` property and the actual count of outgoing `EVIDENCED_BY` edges. Returns per-label fix counts; emits a `knowledge_evidence_count_drift_fixed_total{node_label}` Prometheus Counter.

**Run cadence:** daily at low traffic per KSA §3.6. A normal run should fix ZERO nodes.

**What the reconciler does NOT fix (deferred):**
- Orphan `:ExtractionSource` nodes left behind by `delete_source_cascade` partial failures (K11.8-R1/R2 documented gap — needs explicit transaction wrapping, separate task)
- `mention_count` drift (it's a monotonic "times observed" counter, not a live edge count per K11.8 docstring)
- Relation confidence promotion state (K11.6 handles that at write time)

**Scheduler wiring is NOT in this task.** The function is shipped; calling it on a cron / APScheduler / Temporal timer is K19/K20 cleanup-scheduler work.

---

## 3. Session 40 commit log

```
<pending> fix(knowledge-service): K11.9-R1 second-pass review fixes (R1, R2, R3)
<pending> feat(knowledge-service): K11.9 evidence_count drift reconciler
```

(Commits pending in Phase 9 at the time this handoff was drafted.)

---

## 4. Files added / modified

| File | Change |
|---|---|
| `services/knowledge-service/app/jobs/__init__.py` | NEW package for offline maintenance jobs |
| `services/knowledge-service/app/jobs/reconcile_evidence_count.py` | NEW — reconciler function, result model, label dispatch |
| `services/knowledge-service/app/metrics.py` | Added `knowledge_evidence_count_drift_fixed_total{node_label}` Counter (pre-init via `.inc(0)`) |
| `services/knowledge-service/tests/integration/db/test_reconcile_evidence_count.py` | NEW — 11 integration tests |
| `docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md` | K11.9 checkbox `[ ]` → `[✓]` |
| `docs/sessions/SESSION_PATCH.md` | K11.9 entry + header metadata |

---

## 5. Patterns reinforced this session

- **Per-label Cypher dispatch via closed-enum f-string at module load** (same pattern as K11.8 `add_evidence`). Cypher labels can't be parameterised in a way that uses the label-scoped index, so the dispatch lives in Python. `_build_reconcile_cypher` is called exactly 3 times at import; `reconcile_evidence_count` validates against `RECONCILE_LABELS` before picking a prebuilt template. Reviewers: if you add a fourth label, extend `RECONCILE_LABELS` — do NOT pass user input through.
- **`project_id` optional from day one** (V15 §9 lesson). Every K11.x R1 round found a project_id gap; K11.9 ships with the filter from commit 1.
- **`OPTIONAL MATCH + count(r)` is correct for edge-count aggregation** — count skips nulls so a node with zero edges returns 0, not 1. Standard Cypher but worth stating since it was a V15 gotcha area.
- **Metric is a Counter, not a Gauge.** Dashboards compute "drift fixed in last N hours" via `rate()` on a monotonic counter. A Gauge would only show the last run's value.
- **Paranoid-by-default on cross-user endpoints.** The R1 fix filtered not only `n.user_id = $user_id` but also `src.user_id = $user_id` on the EVIDENCED_BY target. A reconciler is the safety net for write-path bugs, so it should tolerate shouldn'ts.

---

## 6. Next session — recommended starting points

### Option A: K15 pattern extractor (RECOMMENDED)
First real consumer of the K11 writeable surface. Reads chapters/messages, runs regex patterns, writes entities + relations + facts + events with `pending_validation=true`. Uses K11.5a `merge_entity`, K11.6 `create_relation`, K11.7 `merge_event` / `merge_fact`, and K11.8 `add_evidence` in anger. This is where you'll find out whether the K11 surface is missing anything.

Plan reference: `docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md` — search for `K15`.

### Option B: K17 LLM extractor (Pass 2)
Reads chapters with an LLM, writes the same node/edge types with `pending_validation=false` and high confidence, **promotes existing K15 quarantined writes via the merge max-confidence semantics** established in K11.6 / K11.7. Both repos already implement the Pass 1 → Pass 2 promotion path on `merge_*`, so the LLM extractor mostly composes existing helpers plus an LLM client.

Recommendation: **K15 first** to validate the K11 surface against real-world extraction shapes, then K17 to benefit from K15's surface-validation feedback. K11.9 is deliberately in place first so any K15/K17 counter drift is caught immediately.

### Option C: K11.10 Glossary service client (HTTP + event subscriber)
Per KSA §6.0, knowledge-service talks to glossary-service across HTTP (outbound proposals) and Redis Streams (inbound authoritative updates). This unblocks the two-layer entity pattern validation in production. Smaller scope than K15 but cross-service — requires glossary-service to be up.

---

## 7. Known follow-ups carried forward

These are all in `SESSION_PATCH.md → Deferred Items`. None are K11.9 blockers:

| ID | Origin | What | Target |
|---|---|---|---|
| D-K11.3-01 | K11.3-R1 | Lifespan startup leaks resources on partial failure | Gate 4 hardening |
| (K11.8 delete_source_cascade non-atomicity) | K11.8-R1/R2 | Three round-trips are non-atomic; partial failure leaves orphan source | Separate K11.9.x task — explicit transaction wrapping |
| (K11.9 orphan ExtractionSource cleanup) | K11.9 PLAN | Reconciler fixes counters only; orphan source nodes need a separate sweep | Same K11.9.x or K19/K20 |

---

## 8. Live infrastructure state

```
infra/docker-compose.yml:
  neo4j:2026.03-community on host ports 7475 (HTTP) / 7688 (bolt)
  → Internal compose name `neo4j` on port 7687
  → Container name infra-neo4j-1
  → APOC plugin loaded
```

To run the integration suite locally:
```
cd services/knowledge-service
TEST_NEO4J_URI="bolt://localhost:7688" python -m pytest tests -q
```

The 93 skipped tests are Postgres integration tests that need `TEST_KNOWLEDGE_DB_URL` set.

---

## 9. Don'ts (new gotchas from this session)

- **Don't let a reconciler trust that write-path invariants hold.** The R1 bug in K11.9 was exactly this: the first draft assumed `add_evidence` is the only path to EVIDENCED_BY, so it didn't filter the edge target's `user_id`. The reconciler's whole job is to tolerate the case where that assumption breaks. Filter both endpoints.
- **Don't log INFO per user in an offline job.** A daily job over a growing user base at INFO floods logs. Log DEBUG on the clean path and WARNING on the drift-fixed path; aggregate INFO lives at the orchestrator layer.
- **Don't couple pure-guard tests to live-infra fixtures.** A `ValueError` raised before any driver call should be testable without the driver. Use a throwaway stub object.
- **Don't run K11.9 concurrently with extraction.** Same rule as K11.8 `cleanup_zero_evidence_nodes`: there's a transaction-local window where `add_evidence` has merged the edge but not yet committed the counter increment. The reconciler would "fix" upward, then the commit would increment again, producing +1 drift in the opposite direction. Call only from a paused / completed extraction-job state.

---

## 10. What's NOT in this handoff (look elsewhere)

- **Track 1 status** → `SESSION_HANDOFF_V14.md` (100% closed)
- **K11.1 → K11.8 details** → `SESSION_HANDOFF_V15.md`
- **K10.x extraction infra** → SESSION_PATCH "K10.4" / "K10.5" entries
- **K17.9 benchmark harness** → SESSION_PATCH "K17.9" entry (session 38)

---

End of handoff. Next agent: read this file, then `SESSION_PATCH.md` (sections "Current Active Work" and "Deferred Items"), then pick K15 unless the user directs otherwise.
