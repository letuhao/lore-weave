---
name: KNOWLEDGE_SERVICE_4BALPHA_PLAN
description: Phase 4b-α plan — extract loreweave_extraction shared library; knowledge-service refactored to delegate; worker-ai untouched
type: plan
---

# Phase 4b-α — Extract `loreweave_extraction` shared library

> **Status:** PLAN (2026-04-27, session 53 cycle 7)
> **Authorized by:** User chose Option C3 (shared library) over C1/C2; sliced into 3 sub-cycles 4b-α/β/γ
> **Closes-on-BUILD:** Phase 4b-α slice of [`LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md`](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md#phase-4--service-migrations-to-job-pattern) Phase 4b row
> **Sub-cycle scope:** 4b-α only — pure library extraction with NO behavioral change. Worker-ai migration deferred to 4b-γ.
> **Size:** XL (28 prod files modify/move/delete + tests + plan doc).

---

## 1. Why a shared library now

After Phase 4a-δ, every LLM-calling service that wants Pass 2 extraction has to:
1. Talk to the LLM gateway through `loreweave_llm` SDK ✅ (already done)
2. Load extraction prompts (knowledge-service-private)
3. Call 4 SDK operations + tolerant-parse results (knowledge-service-private)
4. Aggregate candidates + dedup (knowledge-service-private)
5. POST to knowledge-service `/internal/extraction/extract-item` for Neo4j persist (cross-service HTTP)

Steps 2-4 are pure logic — no service state — but live inside knowledge-service's `app/extraction/`. Phase 4b-γ wants worker-ai to do steps 1-4 itself and then call a thin "persist these candidates" endpoint, eliminating the 120s `extract_item_timeout_s` HTTP block. That requires steps 2-4 to be importable from any service. Hence the library.

---

## 2. What moves to the library, what stays in knowledge-service

### Moves (pure logic — no Neo4j IO, no service state):

| From | To | Rationale |
|------|-----|-----------|
| [`app/extraction/errors.py`](../../services/knowledge-service/app/extraction/errors.py) | `loreweave_extraction/errors.py` | ExtractionError + ExtractionStage are extraction-domain types |
| [`app/extraction/llm_prompts/__init__.py`](../../services/knowledge-service/app/extraction/llm_prompts/__init__.py) + 8 .md files | `loreweave_extraction/prompts/` | Prompt loader + 8 .md templates (4 combined + 4 system-only) |
| [`app/extraction/llm_entity_extractor.py`](../../services/knowledge-service/app/extraction/llm_entity_extractor.py) | `loreweave_extraction/extractors/entity.py` | Pure SDK call + tolerant parse |
| [`app/extraction/llm_relation_extractor.py`](../../services/knowledge-service/app/extraction/llm_relation_extractor.py) | `loreweave_extraction/extractors/relation.py` | Pure |
| [`app/extraction/llm_event_extractor.py`](../../services/knowledge-service/app/extraction/llm_event_extractor.py) | `loreweave_extraction/extractors/event.py` | Pure |
| [`app/extraction/llm_fact_extractor.py`](../../services/knowledge-service/app/extraction/llm_fact_extractor.py) | `loreweave_extraction/extractors/fact.py` | Pure |
| [`app/db/neo4j_repos/canonical.py`](../../services/knowledge-service/app/db/neo4j_repos/canonical.py) `canonicalize_entity_name` + `canonicalize_text` + `entity_canonical_id` + `HONORIFICS` | `loreweave_extraction/canonical.py` | Misclassified — these are pure ID-derivation utilities, not Neo4j IO. The Neo4j `merge_entity` etc. functions stay in the repo file. |
| [`app/db/neo4j_repos/relations.py`](../../services/knowledge-service/app/db/neo4j_repos/relations.py) `relation_id` | `loreweave_extraction/canonical.py` | Same — pure deterministic hash |
| Pass 2 high-level orchestration (the `_run_pipeline` flow inside [`pass2_orchestrator.py`](../../services/knowledge-service/app/extraction/pass2_orchestrator.py)) | `loreweave_extraction/pass2.py` `extract_pass2(...)` | Pure — calls extractors + aggregates candidates |
| Test files for the 4 extractors + pass2_orchestrator (5 files) | `sdks/python/tests/test_extraction/` | Tests follow the code |

### Stays in knowledge-service (Neo4j IO + service-specific):

| Module | Why it stays |
|--------|--------------|
| [`app/extraction/pass2_writer.py`](../../services/knowledge-service/app/extraction/pass2_writer.py) (300 LOC) | Cypher writes (merge_entity / merge_event / merge_fact / create_relation / add_evidence) |
| [`app/extraction/anchor_loader.py`](../../services/knowledge-service/app/extraction/anchor_loader.py) (131 LOC) | Glossary→Neo4j anchor MERGE; uses GlossaryClient + Cypher |
| [`app/extraction/entity_resolver.py`](../../services/knowledge-service/app/extraction/entity_resolver.py) | Anchor matching; Neo4j-coupled |
| [`app/extraction/injection_defense.py`](../../services/knowledge-service/app/extraction/injection_defense.py) | Generic but used at write time, kept service-side |
| `app/extraction/pass2_orchestrator.py` | Becomes a thin wrapper: `_run_pipeline` calls `loreweave_extraction.extract_pass2(...)` then `pass2_writer.write_pass2_extraction(...)`. Anchor loading + telemetry hooks stay here. |
| `app/db/neo4j_repos/canonical.py` | Re-exports the 3 moved helpers from library (back-compat for non-extraction call sites) + keeps Neo4j-specific MERGE functions |
| `app/db/neo4j_repos/relations.py` | Same — re-export `relation_id` from library |

---

## 3. Decisions baked in

### D1 — Library lives in same `sdks/python/` directory as `loreweave_llm`

**Decision:** Add `loreweave_extraction` as a sibling package under `sdks/python/`. Extend the existing `pyproject.toml` to discover both packages.

- **Why same directory:** Dockerfile pattern unchanged (`COPY sdks/python /sdk + pip install /sdk`). One install brings both packages. Inter-package dep `loreweave_extraction` → `loreweave_llm` resolves locally.
- **Why not separate `sdks/python-extraction/`:** Adds Dockerfile complexity for zero gain. The 2 packages are tightly coupled by design (extraction ALWAYS uses LLM SDK).

### D2 — `canonical.py` helpers are PURE — moved verbatim

**Decision:** `canonicalize_entity_name`, `canonicalize_text`, `entity_canonical_id`, `relation_id`, `HONORIFICS` move to `loreweave_extraction/canonical.py` byte-identically.

- **Why pure-move:** They have no Neo4j IO despite living in `neo4j_repos/`. Misclassification — fix it.
- **Back-compat shim:** `app/db/neo4j_repos/canonical.py` and `relations.py` re-export the moved names for non-extraction call sites (e.g., entity_alias_map repo, anchor_loader). This keeps cycle 4b-α's blast radius bounded.

### D3 — `pass2_orchestrator.py` stays in knowledge-service but delegates

**Decision:** Keep `pass2_orchestrator.py` as a thin wrapper. The `_run_pipeline` body becomes:
```python
candidates = await extract_pass2(  # NEW — from loreweave_extraction
    llm_client=llm_client,
    text=text,
    known_entities=known_entities,
    user_id=user_id,
    project_id=project_id,
    model_source=model_source,
    model_ref=model_ref,
)
# anchor loading + Neo4j write stay service-side
return await write_pass2_extraction(
    session, ...,
    entities=candidates.entities,
    relations=candidates.relations,
    events=candidates.events,
    facts=candidates.facts,
    anchors=anchors,
)
```

- **Why orchestrator stays:** It owns service-specific concerns: `JobLogsRepo` telemetry hooks, anchor loading via Neo4j session, write_pass2_extraction call. Moving these to the library would require Neo4j + repo abstractions in the library — wrong layer.

### D4 — Test files move to `sdks/python/tests/test_extraction/`

**Decision:** Move `test_llm_{entity,relation,event,fact}_extractor.py` + `test_pass2_orchestrator.py` (5 files) to the library's test suite. Tests are tightly coupled to the moved code; co-location keeps the library self-testable.

- **Knowledge-service keeps:** `test_internal_extraction.py` (router-level), `test_passages_selector.py` (uses extractors but tests passage selection), tests for `pass2_writer` / `anchor_loader` / `entity_resolver` (Neo4j-coupled).
- **Pass2 orchestrator test:** moves to library, but knowledge-service may add a thin wrapper-integration test if needed (deferred — 4b-α should not add new tests).

### D5 — No re-export shims in `app/extraction/`

**Decision:** `app/extraction/llm_*_extractor.py` + `errors.py` + `llm_prompts/__init__.py` are DELETED, not shimmed. Importers update directly.

- **Why hard-delete:** Re-export shims hide the migration. Importers explicitly switching to `from loreweave_extraction.extractors.entity import extract_entities` makes the dependency direction clear.
- **`app/extraction/llm_prompts/*.md`:** DELETED (moved to library).
- **Exception — `app/db/neo4j_repos/canonical.py` + `relations.py`:** DO get re-export shims because they have non-extraction callers (~6 sites).

### D6 — Order of operations: build library → switch importers → delete

1. Create `loreweave_extraction/` with all 12-15 new files (library is self-complete + self-tested before knowledge-service touches it)
2. Add re-export shims in `canonical.py` + `relations.py`
3. Update knowledge-service importers (~10 sites) to import from library
4. Refactor `pass2_orchestrator.py` to delegate
5. Delete old extractor files + prompt .md files + errors.py + llm_prompts package
6. Move 5 test files to library test suite
7. Verify both pytest suites green

---

## 4. Step-by-step file map

| Step | Files | Action |
|------|-------|--------|
| 1 | `sdks/python/pyproject.toml` | Extend `[tool.setuptools.packages.find]` to include `loreweave_extraction*` |
| 2 | `sdks/python/loreweave_extraction/__init__.py` | NEW — package init + top-level exports |
| 2 | `sdks/python/loreweave_extraction/errors.py` | NEW — moved from `app/extraction/errors.py` |
| 2 | `sdks/python/loreweave_extraction/canonical.py` | NEW — moved canonicalize_* + entity_canonical_id + relation_id + HONORIFICS |
| 2 | `sdks/python/loreweave_extraction/prompts/__init__.py` | NEW — load_prompt + PromptName Literal (moved from llm_prompts/__init__.py) |
| 2 | `sdks/python/loreweave_extraction/prompts/*.md` (8 files) | MOVED from app/extraction/llm_prompts/ |
| 3 | `sdks/python/loreweave_extraction/extractors/__init__.py` | NEW |
| 3 | `sdks/python/loreweave_extraction/extractors/entity.py` | MOVED from llm_entity_extractor.py |
| 3 | `sdks/python/loreweave_extraction/extractors/relation.py` | MOVED from llm_relation_extractor.py |
| 3 | `sdks/python/loreweave_extraction/extractors/event.py` | MOVED from llm_event_extractor.py |
| 3 | `sdks/python/loreweave_extraction/extractors/fact.py` | MOVED from llm_fact_extractor.py |
| 4 | `sdks/python/loreweave_extraction/pass2.py` | NEW — `extract_pass2()` orchestrator (extracted from `pass2_orchestrator._run_pipeline` LLM-call portion) + Pass2Candidates dataclass |
| 5 | `services/knowledge-service/app/extraction/llm_entity_extractor.py` | DELETE |
| 5 | `services/knowledge-service/app/extraction/llm_relation_extractor.py` | DELETE |
| 5 | `services/knowledge-service/app/extraction/llm_event_extractor.py` | DELETE |
| 5 | `services/knowledge-service/app/extraction/llm_fact_extractor.py` | DELETE |
| 5 | `services/knowledge-service/app/extraction/errors.py` | DELETE |
| 5 | `services/knowledge-service/app/extraction/llm_prompts/` (entire package) | DELETE |
| 6 | `services/knowledge-service/app/extraction/pass2_orchestrator.py` | REFACTOR — delegate to `loreweave_extraction.extract_pass2` |
| 7 | `services/knowledge-service/app/db/neo4j_repos/canonical.py` | SHIM — re-export `canonicalize_entity_name`, `canonicalize_text`, `entity_canonical_id`, `HONORIFICS` from library; keep Neo4j-specific functions |
| 7 | `services/knowledge-service/app/db/neo4j_repos/relations.py` | SHIM — re-export `relation_id` from library; keep Neo4j-specific functions |
| 8 | `services/knowledge-service/app/extraction/pass2_writer.py` | UPDATE imports — `LLMEntityCandidate` etc. from library |
| 8 | `services/knowledge-service/app/extraction/entity_resolver.py` | UPDATE imports |
| 8 | `services/knowledge-service/app/extraction/anchor_loader.py` | UPDATE imports if any |
| 8 | `services/knowledge-service/app/routers/internal_extraction.py` | UPDATE — `from loreweave_extraction.errors import ExtractionError` |
| 8 | `services/knowledge-service/Dockerfile` | UPDATE comment if needed (sdks/python COPY already covers both packages) |
| 9 | `sdks/python/tests/test_extraction/test_entity_extractor.py` | MOVE from `services/knowledge-service/tests/unit/test_llm_entity_extractor.py` |
| 9 | (same for relation/event/fact/pass2_orchestrator) | MOVE 4 more test files |

---

## 5. Verification gates (Phase 6 evidence)

| Gate | Command | Pass criterion |
|------|---------|----------------|
| Library unit suite | `cd sdks/python && pytest tests/ -q` | All green; 4 extractor + 1 pass2 test files now under SDK pass |
| Knowledge-service unit suite | `cd services/knowledge-service && pytest tests/unit -q` | All remaining green; baseline minus the 5 moved test files |
| Knowledge-service integration | `pytest tests/integration/db -q` | Green |
| Stale-import grep | `grep -rn "from app.extraction.llm_.*_extractor\|from app.extraction.errors\|from app.extraction.llm_prompts" services/knowledge-service` | Empty |
| Library importable from knowledge-service | `python -c "from loreweave_extraction.extractors.entity import extract_entities"` | No ImportError |

---

## 6. Risks + mitigations

| Risk | Mitigation |
|------|-----------|
| Tests fail because moved test files reference `app.*` paths | Subagent rewrite for ~5 test files (similar to 4a-δ subagent pattern) |
| Library can't import `loreweave_llm` due to package discovery | Verify with explicit `pip install -e ../../sdks/python && python -c "import loreweave_extraction"` early |
| Re-export shims confuse readers | Add explicit `# Phase 4b-α — re-exports from loreweave_extraction; primary site is the library` comments |
| Knowledge-service Pass 2 telemetry breaks (job_logs hooks) | Pass2 orchestrator stays service-side and calls library's `extract_pass2` between log-emit calls — no telemetry move |

---

## 7. What 4b-β + 4b-γ do (forward reference)

- **4b-β (M):** knowledge-service adds `POST /internal/extraction/persist-pass2` accepting `Pass2Candidates` payload (entities/relations/events/facts dicts). Reuses `pass2_writer.write_pass2_extraction`. extract-item endpoint kept for back-compat.
- **4b-γ (L):** worker-ai migration: drops `KnowledgeClient.extract_item`; uses `loreweave_extraction.extract_pass2(llm_client, ...)` then POSTs to `/persist-pass2`. extract-item endpoint deleted. **The 120s HTTP timeout finally goes away.**

After 4b-γ: every Pass 2 caller (knowledge-service internal, worker-ai, future translation-service) uses the same `loreweave_extraction.extract_pass2` flow with a thin persist-pass2 HTTP boundary.
