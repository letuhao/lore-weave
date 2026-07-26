# Plan: D-KG-EXTRACTION-CANON-WIRE + D-CANON-CHECK-SDK-UNIFY

Size: L (touches DB read query + orchestrator wiring + a new shared SDK package + migrating
2 services + cross-service regression). Both items were tracked follow-ups from the
2026-07-05 POC (`kg-extraction-canon-gate-poc`) and the 2026-07-06 judge-accuracy eval
(`docs/eval/canon-check-judge-2026-07-06.md`), which recommended wiring as a
**quarantine+promote** gate (not hard-block) using Gemma-4 26B QAT.

## Part A — D-KG-EXTRACTION-CANON-WIRE

**Wiring point confirmed:** `services/knowledge-service/app/extraction/pass2_orchestrator.py`
`_run_pipeline`, between the R/E/F gather's `_emit_log` (line ~1111) and "Step 5 — write
everything to Neo4j" (`write_pass2_extraction` call, line ~1115). Everything needed is
already in scope at that point: `session`, `text`, `user_id`, `project_id`, `model_source`,
`model_ref`, `llm_client`, `job_logs_repo`, `job_id`.

**Rejected mechanism: `kg_triage_items`.** Structurally similar (park-for-human-review) but
semantically wrong fit — its own docstring: "extraction elements that don't match the
resolved schema are parked here (**NOT written to Neo4j**)". Its lifecycle is
withhold-until-resolved for schema-conformance failures (`unknown_edge_type`,
`edge_kind_mismatch`, etc.) — a genuinely different failure class from a narrative-continuity
flag on data that DID extract successfully. Reusing it would mean withholding graph writes on
a judge whose own eval showed 85.7% precision — 1-in-7 legitimate revivals/dialogue turns
would be silently dropped pending a review nobody may ever perform. Also its `TriageItemType`
is a closed spec'd enum (5 schema-mismatch types + `proposed_edge`) mirrored on the FE
(`frontend/src/features/knowledge/types/ontology.ts`) — adding a 7th, semantically unrelated
type would misuse a taxonomy that's documented as being specifically about schema mismatches.

**Chosen mechanism: `job_logs` via the existing `_emit_log` helper.** Already wired
end-to-end to the Studio's JobLogsPanel (confirmed: "Writes to `job_logs` so the FE's
JobLogsPanel can render extraction-pipeline progress"). Zero schema change, zero new FE
surface, immediately visible wherever a user already watches extraction jobs. The write
proceeds UNCHANGED regardless of the check's outcome — this IS the quarantine tier
(flagged for attention, not withheld).

**Steps:**
1. `services/knowledge-service/app/db/neo4j_repos/entity_status.py` — new
   `list_gone_entities(session, *, user_id, project_id, min_evidence=1) -> list[dict]`.
   Single Cypher query: latest EVIDENCED `:EntityStatus` per `entity_id` (no `at_order`
   window — "gone as of now", mirrors `statuses_detail_at_order`'s windowed shape but without
   a caller-supplied id list), filtered to `status='gone'`, left-joined to `:Entity` for
   `name`/`canonical_name`. Returns `{entity_id, name, canonical_name, from_order}` — the
   exact shape `check_extraction_canon`'s snapshot expects.
2. `pass2_orchestrator.py::_run_pipeline` — before the write call: fetch gone entities for
   the project; if any exist, build the snapshot and call `check_extraction_canon(text,
   snapshot, llm=llm_client, user_id=user_id, model_source=model_source, model_ref=model_ref)`
   — **reusing the SAME model already resolved for this extraction job**, no new setting (per
   `docs/standards/settings-and-config.md`: don't add a knob when the existing per-job choice
   already answers "which model"). Wrapped in `try/except Exception` (this repo's fail-soft
   convention for non-critical instrumentation — a canon-check bug must never break real
   extraction, CC4).
3. For each candidate with `confirmed=True`, one `_emit_log` call per candidate:
   `event="pass2_canon_flag"`, message names the entity + why. The write proceeds
   unconditionally right after.
4. Tests: unit test in `pass2_orchestrator`'s existing test file mocking
   `check_extraction_canon`/`list_gone_entities` to assert (a) zero gone entities → no LLM
   call, no log; (b) a confirmed candidate → exactly one `_emit_log` call with the expected
   context, write still proceeds; (c) a judge exception → write still proceeds (degrade-safe).
   New unit tests for `list_gone_entities` in `tests/integration/db/test_entity_status_repo.py`
   (real Neo4j, matching that file's existing pattern).
5. Live-smoke: re-run the same seeded-contradiction scenario from the original POC through
   the REAL `_run_pipeline` (not calling `check_extraction_canon` directly) to prove the wiring
   fires end-to-end, and confirm a `job_logs` row lands.

**Explicitly NOT built (tracked as a new follow-up, not this task's scope):**
`D-KG-CANON-FLAG-REVIEW-UI` — a dedicated filtered view/panel for canon-flag job_log entries
(today they're visible but interleaved with all other pass2 log lines). Gate: naturally-next-
phase (this task's own output — real flagged log entries — doesn't exist yet to design a
panel against) and out of proportion for "wire the gate," which is what was asked.

## Part B — D-CANON-CHECK-SDK-UNIFY

**Confirmed call sites (from research):** composition's `canon_check.py` is used ONLY through
`canon_reflect.py::run_canon_reflect`, itself called from 3 `worker/operations.py` sites +
4 `routers/engine.py` sites (all `try/except`, advisory, never blocking generation — but its
persisted `resolved` flag DOES hard-block chapter publish downstream via
`outline.py::chapter_scene_gate`). Knowledge's `canon_check.py` has NO production caller yet
(only the eval harness + its own tests) until Part A above lands.

**Identical-logic hoist targets** (confirmed byte-for-byte or near-identical via diff):
`_find_span`/`_SPAN_PAD`, the symbolic-prefilter body shape, `_parse_verdicts`, the judge
request shape (`response_format`/`temperature`/`max_tokens`/`reasoning_effort`/
`chat_template_kwargs`), the verdict-application loop, the compose-function control flow,
`source_language` message-suffix handling. **A real gap found in the diff, fixed by
unification:** knowledge's judge catches bare `Exception` and manually indexes
`job.result["messages"][0]["content"]`; composition's uses a typed `LLMError` +
`extract_judge_content`. The unified helper adopts composition's more precise handling for
both.

**New package:** `sdks/python/loreweave_canon_check/` (flat submodule layout, matching
`loreweave_llm`'s convention — no nested sub-packages for ~150 lines of shared logic).
Added to the root `sdks/python/pyproject.toml`'s `[tool.setuptools.packages.find].include`
list (the established shared-distribution pattern; do NOT create a standalone
per-package `pyproject.toml` — that path is documented as transitional/legacy for the 2
packages using it, not the target state).

- `loreweave_canon_check/__init__.py` — public exports.
- `loreweave_canon_check/base.py`:
  - `SPAN_PAD = 40`, `find_span(text, name, pad=SPAN_PAD) -> str`
  - `parse_judge_verdicts(content: str) -> dict[str, dict]`
  - `extract_judge_text(job) -> str` — the fixed, shared, robust job-result parser
  - `build_judge_request(messages, *, usage_purpose, extractor, max_tokens=1024) -> dict` —
    the shared request-shape builder (returns `{"input": {...}, "job_meta": {...}}`)
  - `apply_verdicts(candidates, verdicts, id_attr="entity_id") -> None` — generic
    verdict-application over any candidate sequence with `.confirmed`/`.source`/`.why`
  - `CanonCandidateBase(BaseModel)` — the 8 shared fields (`kind, source, entity_id, name,
    status, span, matched, confirmed, why`); each service subclasses adding its own field
    (`glossary_entity_id` for composition, `gone_from_order` for knowledge)
  - `gone_entities_referenced(text, snapshot, *, extra_field=None) -> list[dict]` — the
    unified symbolic-prefilter (structurally identical in both today per the diff),
    parameterized by an optional extra field name to copy from each snapshot entity dict

**Stays per-service (domain-specific, confirmed genuinely divergent):** prompt wording
(`_build_judge_messages`'s system/user text differs in framing — composition's has no
"explicit revival is not a contradiction" exception, knowledge's does), the top-level
`judge_canon`/`judge_extraction_contradiction` + `check_canon`/`check_extraction_canon`
orchestration functions (thin, call into the shared `base` helpers — kept separate rather
than forced into one higher-order function, since composition's carries extra
`trace_id`/`cancel_check` params knowledge's doesn't need), and composition's entire
`reflect_revise`/`ReflectResult`/`scene_at_order`/`EVENT_ORDER_CHAPTER_STRIDE` orchestration
layer (no knowledge-side equivalent — not "divergent", simply absent, stays composition-only).

**Steps:**
1. Create `sdks/python/loreweave_canon_check/{__init__.py,base.py}` + move the identical
   logic there with unit tests (`sdks/python/tests/test_canon_check_base.py`, following the
   root-level cross-package test convention).
2. Add `"loreweave_canon_check*"` to the shared `pyproject.toml` include list.
3. Refactor `services/composition-service/app/engine/canon_check.py` to import from
   `loreweave_canon_check` for the hoisted pieces; re-run composition's full test suite
   (byte-identical behavior expected — this is a pure refactor for this file, the
   `reflect_revise` layer is untouched).
4. Refactor `services/knowledge-service/app/extraction/canon_check.py` the same way — this
   ALSO fixes the error-handling gap (adopts `extract_judge_text`'s precise parsing instead
   of the manual bare-except indexing). Re-run the 16 existing unit tests + the eval harness
   once more to confirm the refactor didn't change judge behavior (same fixture scores
   expected: Gemma-4 26B QAT 93.75%).
5. Update both services' `requirements.txt` comment blocks to note the new SDK package
   (matching the existing per-package comment convention), confirm both Dockerfiles' existing
   `COPY sdks/python /sdk` + `pip install /sdk` already pick it up (no Dockerfile change
   needed — the shared-distribution pattern means a new package under the same root
   `pyproject.toml` is automatically included).

## Verification plan (both parts)

- knowledge-service full suite (`pytest tests/unit -q -n auto --dist loadgroup` +
  targeted integration DB tests for `list_gone_entities`)
- composition-service full suite (byte-identical-behavior regression check)
- sdks/python new unit tests for the hoisted helpers
- Live-smoke: the wiring's end-to-end log-emission proof (Part A step 5)
- Re-run `eval/run_canon_check_eval.py` once post-unification to confirm scores unchanged
  (regression guard on the refactor, not a new accuracy question)

## Order of work

Part A (wire) before Part B (unify) — matches the POC's own stated precondition
("unifying is appropriate once wiring + judge-accuracy are both validated"). Judge-accuracy
is now validated (2026-07-06 eval); wiring is what makes the design real enough to unify
around, so it goes first.
