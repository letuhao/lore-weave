# Session Handoff — Session 39 Continuation END (Track 2 K11 cluster ✅ COMPLETE)

> **Purpose:** Give the next agent complete context. **The K11 Neo4j repo cluster is done; Track 2 extraction pipeline (K15+, K17+) is the next big rock.**
> **Date:** 2026-04-15 (session 39 continuation, absolute end)
> **Last code commit:** `220c22c` — K11.8-R1 second-pass review fixes (R1, R2, R3)
> **Continuation commit count:** 15 (8 features + 7 review fixes; see §3 for the full list)
> **Previous handoffs:** V9-V14 cover Track 1 closing; V14 was "Track 1 100% done"
> **Source of truth for all state:** `docs/sessions/SESSION_PATCH.md` → "K11.8 Provenance repository" entry and the K11.x entries above it

---

## 1. TL;DR — every K11.x repo + provenance shipped against live Neo4j

Session 39 continuation took Track 2's K11 cluster from "schema applied, no callers" to "every node + edge + provenance writer green against live Neo4j 2026.03.1". Eight feature commits, each immediately followed by an `*-R1` second-pass review-fix commit. Plan doc K11.1 → K11.8 checkboxes flipped `[ ]` → `[✓]` (K11.4 was already done in session 38).

The pattern this session: **build → test → critical second-pass review → fix → re-test → commit**. Every R1 round found at least one real bug — that's not "review for show", that's the workflow paying off. Examples:

- **K11.5a** — `HONORIFICS` was a `frozenset`, hash-randomized iteration would have made `canonical_id` non-deterministic across worker process restarts. Caught in self-test before commit.
- **K11.5b** — `link_to_glossary` could create two entities with the same `glossary_entity_id` FK; `get_entity_by_glossary_id`'s `result.single()` would crash. Fixed via schema constraint + defensive iterator scan.
- **K11.6** — `find_relations_for_entity` only returned outgoing edges; the L2 RAG loader needs both directions and would have shipped with that bug.
- **K11.7** — `merge_event` ON CREATE stored raw participants list (no dedup), and `merge_event` summary `coalesce` treated empty string as a deliberate clear (would silently wipe existing summaries).
- **K11.8** — `get_extraction_source` natural-key lookup ignored `project_id`, so two projects with the same chapter id would crash via single().

---

## 2. Where We Are — K11 cluster status

```
K11.1 Neo4j compose service                        ✅
K11.2 Neo4j async driver wiring                    ✅
K11.3 Cypher schema runner                         ✅ + R1 review fixes
K11.4 Multi-tenant Cypher query helpers            ✅ (session 38)
K11.5 entities repo                                ✅
  K11.5a (core CRUD)                               ✅ + R1 review fixes
  K11.5b (vector + linking)                        ✅ + R1 review fixes
K11.6 relations repo                               ✅ + R1 review fixes
K11.7 events + facts repos                         ✅ + R1 review fixes
K11.8 provenance repo                              ✅ + R1 review fixes
K11.9 offline reconciler                           ⏸️ next
K11.10+                                            ⏸️
```

Test count: **554 passed, 93 skipped** against live Neo4j 2026.03.1 (was 369 at the start of this continuation; +185 new tests).

---

## 3. Continuation commit log (newest first)

```
220c22c fix(knowledge-service): K11.8-R1 second-pass review fixes (R1, R2, R3)
096db42 feat(knowledge-service): K11.8 provenance repository (ExtractionSource + EVIDENCED_BY)
b1b768c fix(knowledge-service): K11.7-R1 second-pass review fixes (R1..R4)
0bfd6be feat(knowledge-service): K11.7 events + facts repositories
0846c81 fix(knowledge-service): K11.6-R1 second-pass review fixes (R1, R2)
9fa5d16 feat(knowledge-service): K11.6 relations repository (RELATES_TO edges)
d46a502 fix(knowledge-service): K11.5b-R1 second-pass review fixes (R1..R5)
9f8e6a1 feat(knowledge-service): K11.5b entities repository — vector + linking slice
16e845c fix(knowledge-service): K11.5a-R1 second-pass review fixes (R1..R6)
ffe7b8a feat(knowledge-service): K11.5a entities repository (Neo4j) — core CRUD slice
f594aad fix(knowledge-service): K11.3-R1 second-pass review fixes (R1..R5)
401ad0a feat(knowledge-service): K11.3 Neo4j Cypher schema runner + 2026.03 bump
0f70024 feat(knowledge-service): K11.2 Neo4j async driver wiring        [start of cont.]
52d1f5c feat(infra): K11.1 Neo4j compose service for Track 2 extraction graph
```

(K11.1 + K11.2 landed at the very start of the continuation before the R1 review pattern was established; they did not get separate review-fix commits but their issues were folded into K11.3 — notably the Neo4j 2025.10 → 2026.03 image bump that came from user pushback.)

---

## 4. The full K11 Neo4j writeable surface (what's available now)

`app/db/neo4j_repos/`:

| Module | Functions |
|---|---|
| `canonical.py` | `canonicalize_entity_name`, `canonicalize_text`, `entity_canonical_id`, `HONORIFICS` |
| `entities.py` (K11.5a + K11.5b) | `merge_entity`, `upsert_glossary_anchor`, `get_entity`, `find_entities_by_name`, `find_entities_by_vector`, `link_to_glossary`, `get_entity_by_glossary_id`, `unlink_from_glossary`, `recompute_anchor_score`, `find_gap_candidates`, `archive_entity`, `restore_entity`, `delete_entities_with_zero_evidence` + `Entity`, `VectorSearchHit`, `SUPPORTED_VECTOR_DIMS` |
| `relations.py` (K11.6) | `relation_id`, `create_relation`, `get_relation`, `find_relations_for_entity` (1-hop, both directions, optional project_id), `find_relations_2hop` (with required hop1_types), `invalidate_relation` + `Relation`, `RelationHop`, `RelationDirection` |
| `events.py` (K11.7) | `event_id`, `merge_event`, `get_event`, `list_events_for_chapter`, `list_events_in_order`, `delete_events_with_zero_evidence` + `Event` |
| `facts.py` (K11.7) | `fact_id`, `merge_fact`, `get_fact`, `list_facts_by_type`, `invalidate_fact`, `delete_facts_with_zero_evidence` + `Fact`, `FactType`, `FACT_TYPES` |
| `provenance.py` (K11.8) | `extraction_source_id`, `upsert_extraction_source`, `get_extraction_source`, `add_evidence` (atomic counter increment), `remove_evidence_for_source`, `delete_source_cascade`, `cleanup_zero_evidence_nodes` + `ExtractionSource`, `EvidenceWriteResult`, `CleanupResult`, `SOURCE_TYPES`, `TARGET_LABELS` |

**Every Cypher in this layer routes through K11.4's `run_read` / `run_write`.** The `assert_user_id_param` runtime check is the multi-tenant safety net. The two documented exceptions are `app/db/neo4j_schema.py` (global schema apply) and `_build_add_evidence_cypher` (label dispatch via closed-enum f-string interpolation).

---

## 5. Cross-cutting patterns established this session

These are now load-bearing for K11.9 / K15 / K17:

1. **Deterministic id hashes for idempotency.** Every node and edge type has an `<x>_id(...)` helper that derives a 32-char SHA-256 from `(user_id, project_id, …natural key bits)`. Re-extraction is a no-op against the repo because the merge key collides on the deterministic id.

2. **Three-way temporal field handling on ON MATCH.** First-non-null write wins for descriptive fields (`summary`, `event_order`, `chronological_order`); `coalesce(...)` would have wiped existing values when a caller passed `""`, so empty strings are normalized to `None` at the Python boundary.

3. **`_just_created` marker pattern for atomic upsert + "was this a no-op?" signaling.** `add_evidence` uses this to surface idempotency to the caller without a separate pre-read query. ON CREATE sets `e._just_created = true`, ON MATCH sets `false`, then `WITH ... coalesce(.., false) AS created REMOVE e._just_created` cleans up.

4. **Per-label dispatch for label-using queries.** Cypher labels can't be parameterized in a way that uses an index, so functions that need to query a specific node label (`add_evidence` for `Entity`/`Event`/`Fact`, `find_entities_by_vector` for the dim-routed index name) build N templates at module-load time with f-string interpolation, gated by closed-enum validation in the public function. **Reviewers: if you add a new label, extend the closed enum — do NOT pass user input to the builder.**

5. **`UNION` over disjunction-with-mixed-indexability.** When a query combines two predicates where one is indexed and the other is a list scan (e.g., `canonical_name = $x OR $name IN aliases`, or 1-hop both-directions traversal), Neo4j's planner falls back to a label scan that defeats the index. The fix is to split into a `CALL { … UNION … }` subquery so each arm uses its own optimal plan.

6. **`coalesce(x, false) = false` instead of `IS NOT TRUE`.** KSA L2 loader Cypher used `IS NOT TRUE` which is invalid in Neo4j 5+ syntax. Use the coalesce form everywhere — it's the documented replacement.

7. **`cross-project isolation` parameter.** Every find/list helper that initially shipped without a `project_id` parameter got one in its R1 round. The L2 RAG loader needs to scope to the chapter's project; without the filter, edges from unrelated works pollute the context. **K11.9 helpers should ship with `project_id` from day one.**

---

## 6. Next session — recommended starting points

### Option A: K11.9 offline reconciler
The offline drift detector that compares `evidence_count` to the actual EVIDENCED_BY edge count and corrects mismatches. K11.8 is the runtime primitive that should make K11.9 a no-op in steady state, but the reconciler is the safety net for the documented gaps:
- `delete_source_cascade` is NOT atomic across its three round-trips (K11.8-R1/R2 deferred this to K11.9)
- The `delete_*_with_zero_evidence` functions all have a documented race window with concurrent extraction
- Any caller that bypasses K11.8 helpers (tests doing direct `session.run(...)` for fixtures, glossary sync, manual data fixes) creates drift

Plan reference: `docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md` lines 685+ (search for `K11.9`).

### Option B: K15 pattern extractor
First consumer of the K11 surface. Reads chapters/messages, runs regex patterns, writes entities + relations + facts + events with `pending_validation=true`. Uses the K11.5a/K11.6/K11.7/K11.8 surface in anger. This is where you'll find out whether the surface is missing anything.

### Option C: K17 LLM extractor (Pass 2)
Reads chapters with an LLM, writes the same node/edge types with `pending_validation=false` and high confidence, **promotes existing K15 quarantined writes via the merge max-confidence semantics established in K11.6 / K11.7**. Both repos already implement the Pass 1 → Pass 2 promotion path on `merge_*`, so the LLM extractor mostly composes existing helpers.

Recommendation: **K11.9 first** because it closes the K11 cluster cleanly and gives K15/K17 a known-good baseline. Then K15 to validate the surface. K17 last because it's the largest and benefits from K15's surface-validation feedback.

---

## 7. Known follow-ups carried forward (deferred items)

These were deferred during K11.x review rounds and live in `SESSION_PATCH.md → Deferred Items`:

| ID | Origin | What | Target |
|---|---|---|---|
| D-K11.3-01 | K11.3-R1 | Lifespan startup leaks resources on partial failure | Gate 4 hardening |
| (K11.5a/b/6/7/8 R-fix deferrals: cosmetic helper extraction, edge property index, perf items) | various | See per-task entries in SESSION_PATCH | Various |

None of these are blockers for K11.9 / K15 / K17.

---

## 8. Live infrastructure state (when you start the next session)

```
infra/docker-compose.yml:
  neo4j:2026.03-community on host ports 7475 (HTTP) / 7688 (bolt)
  → Internal compose name `neo4j` on port 7687
  → Container name infra-neo4j-1
  → APOC plugin loaded (used by vector indexes)

knowledge-service env:
  NEO4J_URI=bolt://neo4j:7687     (set in compose; empty in unit-test env)
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=loreweave_dev_neo4j
```

To run the integration suite locally:
```
cd services/knowledge-service
TEST_NEO4J_URI="bolt://localhost:7688" python -m pytest tests -q
# Expected: 554 passed, 93 skipped
```

The 93 skipped tests are Postgres integration tests that need `TEST_KNOWLEDGE_DB_URL` set. To run those too:
```
TEST_KNOWLEDGE_DB_URL="postgres://..." TEST_NEO4J_URI="bolt://localhost:7688" python -m pytest tests -q
```

---

## 9. Don'ts (gotchas accumulated this session)

- **Don't use `IS NOT TRUE` or `IS NOT FALSE` in Cypher.** Neo4j 5+ rejects these as syntax errors. Use `coalesce(x, false) = false` instead.
- **Don't use `frozenset` for anything that ends up in a deterministic id hash.** Hash randomization makes the iteration order non-deterministic across process restarts; the resulting hash will differ between worker processes. Use a `tuple` sorted explicitly.
- **Don't trust `coalesce($text_field, e.text_field)` to mean "no new value".** Cypher's `coalesce` only short-circuits on NULL, and `""` is non-NULL. Normalize empty strings to `None` at the Python boundary before passing to the driver.
- **Don't query labels with disjunctions when one branch is indexed.** Use `CALL { … UNION … }` so each arm gets its own optimal plan.
- **Don't create EVIDENCED_BY edges directly.** Always go through `add_evidence` so the counter stays in sync. K11.9 reconciler is the safety net; the cheap path is to never produce drift in the first place.
- **Don't run `cleanup_*_with_zero_evidence` concurrently with extraction.** A freshly-merged node has `evidence_count = 0` until the first `add_evidence` call; concurrent cleanup would mistake it for an orphan.
- **Don't add new text fields without considering empty-string vs NULL.** First-write-wins semantics need empty→None normalization or `coalesce(nullif($x, ''), e.x)` in Cypher.
- **Don't omit `project_id` from new find/list helpers.** Every K11.x R1 round found a project_id gap. Default to optional + filter when set.

---

## 10. What's NOT in this handoff (look elsewhere)

- **Track 1 status** → `docs/sessions/SESSION_HANDOFF_V14.md` (Track 1 100% closed)
- **K10.x extraction infra** → done in session 38 + start of 39, see SESSION_PATCH "K10.4" and "K10.5" entries
- **K11.4 details** → done in session 38, see SESSION_PATCH "K11.4 — Multi-tenant Cypher query helpers"
- **K11.Z provenance validator** → pure-function slice from session 38, will get wrapped into `add_evidence` (or a writer-wrap) when K11.9 lands
- **Glossary-service standalone pass** → done in session 38/39, all D-K2a items cleared

---

End of handoff. Next agent: read this file, then `SESSION_PATCH.md` (sections "Current Active Work" and "Deferred Items"), then pick from §6 above.
