# Session Handoff — Session 45 (K17.9 injection defense regression coverage)

> **Purpose:** orient the next agent in one read. **Source of truth for detailed state remains [SESSION_PATCH.md](SESSION_PATCH.md).** This file is the single, unversioned handoff — updated in place at the end of each session. Do NOT create `_V*.md` variants.
> **Date:** 2026-04-17 (session 45)
> **HEAD:** K17.9 regression coverage
> **Branch:** `main` (ahead of origin by sessions 38–45 commits — user pushes manually)

---

## 1. TL;DR — what shipped this session

Session 45 shipped **K17.9** (injection defense regression coverage). Scope collapsed from "apply defense" → "verify + regressions" once inspection confirmed K17.8 writer already sanitizes every persisted text field.

```
K17.9  Injection defense regression coverage  ✅  6 real-fixture tests + docstring pointer
```

**Test execution:**
- **test_pass2_writer.py**: 7 → **14 tests** (+6 K17.9 regressions; replaced 1 weak mock test)
- 184/184 extraction-scoped unit tests green
- 1 commit this session (K17.9 end-to-end)

---

## 2. Where to pick up

The K17 LLM extraction pipeline + injection defense are complete:

```
K17.1  LLM prompts + loader               ✅
K17.2  BYOK LLM client                    ✅
K17.3  JSON parse + retry wrapper          ✅
K17.4  Entity LLM extractor               ✅
K17.5  Relation LLM extractor             ✅
K17.6  Event LLM extractor                ✅
K17.7  Fact LLM extractor                 ✅
K17.8  Orchestrator + writer               ✅
K17.9  Injection defense regressions       ✅ (this session)
K17.10 Golden-set quality eval             ← NEXT (M-sized)
```

**Natural next tasks:**
- **K17.10** — Golden-set benchmark. 10 chapters with hand-labeled expected entities/relations/events, precision/recall metrics against the full Pass 2 pipeline.
- **K16.2–K16.15** — Extraction job lifecycle (cost estimation, start/pause/cancel endpoints, worker-ai integration). These wire K17.8 into the production job runner.

---

## 3. Deferred items — no new items this session

No new deferrals opened in session 45. All existing deferrals unchanged. See [SESSION_PATCH.md §Deferred Items](SESSION_PATCH.md).

---

## 4. Important context the next agent must know

### K17.9 outcome

- **No production behavior change.** K17.8 writer already sanitizes every user-derived text field via `_sanitize`: entity name, relation predicate, event name/summary, every participant, fact content. K17.9 verified this and added regression tests.
- **Orchestrator-level sanitize was NOT added.** The `:ExtractionSource` provenance node in Neo4j stores only source_type/source_id/user_id/project_id/timestamps — no raw text. Sanitization at the writer boundary is sufficient.
- **Metric isolation strategy for Prometheus counter tests:** each test uses a unique `project_id` literal (e.g. `k17-9-entity-name`) so the process-global `injection_pattern_matched_total.labels(project_id=X, pattern=Y)` counter child is isolated across tests. Pattern: `before = .labels(...)._value.get()` → run → `after = .labels(...)._value.get()` → assert `after - before >= 1`.
- **Clean-content negative test sums over all `INJECTION_PATTERNS`** to catch any accidental bump on benign input. Importing `INJECTION_PATTERNS` from `app.extraction.injection_defense` keeps it future-proof as new patterns are added.

### K17.9 gotcha (if revisiting)

- The LLM relation extractor runs `_normalize_predicate` which replaces `[^\w]+` with `_`, so space-dependent injection phrases cannot survive normalization in a relation's `predicate` field. A predicate-level injection test would either never match or be misleading — correctly omitted from K17.9 coverage.
- `LLMRelationCandidate.predicate` field is normalized before reaching the writer, so even though the writer calls `_sanitize(rel.predicate)`, the underscore-normalized value won't match `en_ignore_prior` etc. This is coverage-by-upstream-pipeline rather than by the sanitizer.

### Workflow v2.1 (12-phase) — unchanged

```
CLARIFY → DESIGN → REVIEW-DESIGN → PLAN → BUILD → VERIFY → REVIEW-CODE → QC → POST-REVIEW → SESSION → COMMIT → RETRO
```

- **POST-REVIEW is NEVER skippable** — forces human interaction to break author blindness.
- State machine: `.workflow-state.json` + `scripts/workflow-gate.sh` (run from repo root; running from a subdirectory creates a stray state file)
- Pre-commit hook blocks commits without VERIFY + POST-REVIEW + SESSION completed.

### Infra & test invocation (unchanged)

- Compose: `cd infra && docker compose up -d`, Neo4j: `docker compose --profile neo4j up -d neo4j`
- Neo4j port: **7688**, Postgres port: **5555**
- pytest from `services/knowledge-service/` (env vars set in `pytest.ini`)

### Multi-tenant safety rail (unchanged)

- `entity_canonical_id` scopes by `user_id` + `project_id`. `project_id=None` → `"global"` in the hash key.

---

## 5. Session 45 stats

| Metric | Before session 45 | After session 45 | Delta |
|---|---|---|---|
| `test_pass2_writer.py` tests | 7 | **14** | **+7 (6 new + 1 full pipeline kept)** |
| K17.4–K17.9 unit tests total | 70 | **77** | **+7** |
| Session commits | 0 | **1** | — |
| New deferred items | — | 0 | — |
| Production behavior changes | — | 0 | — |

---

## 6. Housekeeping note

This file is the single, unversioned handoff. **Future sessions MUST update this file in place — do NOT create a `_V19.md`.**
