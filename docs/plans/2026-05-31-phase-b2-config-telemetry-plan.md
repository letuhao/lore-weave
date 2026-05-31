# PLAN — Phase B2: config telemetry + per-novel tuning

**Date:** 2026-05-31 · **Size:** XL+ · **Workflow:** human-in-loop v2.2 (AMAW off)
**DESIGN:** [`2026-05-31-phase-b2-config-telemetry-design.md`](../specs/2026-05-31-phase-b2-config-telemetry-design.md) · **CLARIFY:** [`…-clarify.md`](../specs/2026-05-31-phase-b2-config-telemetry-clarify.md) · **Deferred:** D#055

This plan locks interfaces so each BUILD sub-session inherits them and doesn't re-litigate. Build order: **B2-A → B2-B (b1 then b2) → B2-C**. Each sub-cycle is independently VERIFY-able + live-smokeable.

---

## 0 · Locked interfaces (do not change in BUILD without a design note)

### 0.1 SDK — `loreweave_extraction`
```python
# resolve_config.py (NEW)
@dataclass(frozen=True)
class ResolvedConfig:
    model_ref: str
    model_source: Literal["user_model", "platform_model"]
    precision_filter: PrecisionFilterConfig | None
    entity_recovery: EntityRecoveryConfig | None
    writer_autocreate: bool
    prompts: dict[str, dict[str, str]]      # {op: {"system": ..., "user": ...}}; empty = all defaults; ≤16kB/field
    # prompt_pack_id dropped from B2 (superseded by raw-prompt editing; custom-vs-default via prompt_versions)
    prompt_versions: dict[str, str]         # {op: "v1-op-8hex" | "custom-<sha256-8>"}
    # embedding_model is NOT here — excluded from config_hash (retrieval concern)

def resolve_effective_config(*, global_defaults: dict, project_overrides: dict) -> ResolvedConfig: ...
def config_hash(rc: ResolvedConfig) -> str:    # sha256 of canonical JSON (sorted keys); NOT hash()
def base_default_version(global_defaults: dict) -> str:   # sha256-8 of canonical global defaults

# pass2.py — extract_pass2 gains ONE kw-only param (back-compat: None = today's behaviour)
async def extract_pass2(*, ..., prompt_overrides: dict[str, dict[str, str]] | None = None) -> Pass2Candidates

# _version.py — get_extractor_version gains optional override text
def get_extractor_version(op: str | None = None, *, override_text: str | None = None) -> str
#   override present → "custom-<sha256(override_text)[:8]>"; else file-hash (unchanged)
```
Prompt assembly order (fixed, §2.5): `[override.system or default] + [override.user or default + chapter] + [SDK output-contract block, ALWAYS LAST]`.

### 0.2 Event payloads (outbox `event_type`)
- `knowledge.extraction_run_completed` (worker-ai, **transactional**):
  `{run_id, user_id, project_id, book_id, job_id, scope, chapter_ref, config_hash, resolved_config (prompts hashed), prompt_versions, base_default_version, model_ref, metrics:{entities_merged, relations_created, events_merged, facts_merged, cost_usd}, outcome:'succeeded'|'skipped'|'failed', outcome_source:'pipeline', emitted_at}`
- `knowledge.config_adjusted` (knowledge-service, best-effort):
  `{user_id, project_id, actor_type:'user', actor_id, base_default_version, target, op:'set', before_structural?, after_structural?, before_content_hash?, after_content_hash?, reason?, emitted_at}`

### 0.3 Schema — 3 tables, learning-service `migrate.py` (DDL in DESIGN §3, final).

### 0.4 KS endpoint
`PUT /v1/knowledge/projects/{id}/extraction-config` — If-Match required (428), body `ProjectExtractionConfigUpdate`, 422 on out-of-subset keys / prompt length cap, returns updated `Project` + ETag. Dedicated sub-resource (mirrors `PUT /embedding-model`), NOT generic PATCH.

---

## 1 · B2-A — run plumbing (no UI)

**Goal:** every chapter processed emits a transactional `extraction_run` + a content-addressed `config_registry` row. Pipeline behaviour UNCHANGED (resolve with empty overrides → identical to today's globals).

| # | File | Change | Test |
|---|------|--------|------|
| A1 | `sdks/.../resolve_config.py` (NEW) | `ResolvedConfig`, `resolve_effective_config`, `config_hash`, `base_default_version` | unit: stable hash across restart; canonical sort; embedding-exclusion; precedence; base-version changes on default change |
| A2 | `sdks/.../__init__.py` | export A1 symbols | import smoke |
| A3 | `services/learning-service/app/db/migrate.py` | append 3 tables (DESIGN §3) | boot migration idempotent (run twice) |
| A4 | `services/learning-service/app/events/handlers.py` | `handle_run_completed(event, pool)` → UPSERT config_registry `ON CONFLICT (config_hash) DO NOTHING` + INSERT extraction_runs `ON CONFLICT (origin_service, origin_event_id) DO NOTHING` | unit: 1 registry row for N runs; origin-uniq dedup; DLQ on raise |
| A5 | `services/learning-service/app/main.py` | register `knowledge.extraction_run_completed` | dispatcher registered_types includes it |
| A6 | `services/worker-ai/app/events/outbox_emit.py` (NEW, or extend) | `emit_extraction_run(conn, payload)` — runs `INSERT INTO outbox_events` on the **caller's connection** (not its own pool) | unit: inserts on passed conn |
| A7 | `services/worker-ai/app/runner.py` | job-start: build snapshot `ResolvedConfig` + `config_hash` (pinned); chapter-success path → acquire conn, `BEGIN`, `_advance_cursor`-equiv UPDATE + `emit_extraction_run`, `COMMIT`; skip path (`:1083`) emits `outcome='skipped'` in its cursor txn; **failure path (`:1057`) emits `outcome='failed'` best-effort** (no cursor advance); add `extraction_config` to JobRow SELECT + dataclass | unit: txn rollback on emit failure re-processes chapter; snapshot pinned vs mid-job reload; metrics match `result`; failed-path emits a run row |

**Txn refactor note (A7):** `_advance_cursor` is today a standalone `pool.execute` (`runner.py:442`). Replace the chapter-success cursor-advance with an `async with pool.acquire() as conn, conn.transaction():` block that does the cursor UPDATE + the outbox INSERT. `_record_spending` (`runner.py:493`) stays outside the txn (accounting, not the join target).

**Live-smoke A:** stack up worker-ai + knowledge-service + learning-service + redis + relay; run a chapter extraction job → assert `config_registry` has 1 row, `extraction_runs` has 1 row/chapter with correct metrics + `outcome='succeeded'`; re-run same config → registry still 1 row (dedup), runs accrue. Token: `live smoke: …`.

---

## 2 · B2-B — per-novel tuning BE

### b1 (non-security): structural overrides drive pipeline + edit endpoint
| # | File | Change | Test |
|---|------|--------|------|
| B1 | `services/worker-ai/app/runner.py` | pass `snapshot.precision_filter / entity_recovery / model_ref / writer_autocreate` into `extract_pass2` (was module globals) — resolved from `job.extraction_config` | unit: non-default override → DIFFERENT config_hash AND different extract_pass2 args (guard default-equals-expected) |
| B2 | `services/knowledge-service/app/models/*` | `ProjectExtractionConfigUpdate` Pydantic (structural subset) | schema: rejects out-of-subset keys |
| B3 | `services/knowledge-service/app/routers/public/projects.py` | `PUT /{id}/extraction-config` (If-Match, diff, UPDATE extraction_config version-bumped, emit per changed target) | endpoint: 428 no If-Match; 422 bad key; emit-on-change-only |
| B4 | `services/knowledge-service/app/events/outbox_emit.py` | `emit_config_adjustment(...)` + `config_adjusted_payload(...)` (best-effort) | unit: structural before/after |
| B5 | `services/learning-service/app/events/handlers.py` + `main.py` | `handle_config_adjusted` + register `knowledge.config_adjusted` | unit insert; registered |

### b2 (**security-sensitive** — raw-prompt editing; `/review-impl` before ship)
| # | File | Change | Test |
|---|------|--------|------|
| B6 | `sdks/.../_version.py` | `get_extractor_version(op, override_text=...)` → `custom-<hash>` | unit: custom vs file-hash |
| B7 | `sdks/.../extractors/*.py` + `pass2.py` | each `extract_*` accepts optional `system/user` override; output-contract block stays LAST + SDK-controlled; thread `prompt_overrides` through `extract_pass2` | unit: override changes output; output-contract present even when override tries to suppress it; JSON still validated under hostile prompt |
| B8 | `services/knowledge-service/.../projects.py` + model | extend update to accept `prompts.*` with length caps (422); diff → `before/after_content_hash` (sha256), raw text NOT in event | endpoint: length-cap 422; content-hash-not-text in emitted payload |
| B9 | `services/learning-service/.../handlers.py` | `handle_config_adjusted` stores `*_content_hash` for prompt targets; `*_content` reserved NULL | unit: privacy regression-lock (no raw text persisted) |

**Live-smoke B:** edit filter categories via PUT → `config_adjustment_events` row in learning + next job's runs carry the new `config_hash`; set a custom entity prompt → extraction uses it, `config_registry.prompt_versions.entity = custom-<hash>`, learning event carries hash-not-text. Token: `live smoke: …`.

---

## 3 · B2-C — FE tuning panel

| # | File | Change | Test |
|---|------|--------|------|
| C1 | `frontend/.../knowledge/api.ts` + `types.ts` | `updateExtractionConfig(projectId, body, token)` + types | — |
| C2 | `frontend/.../knowledge/hooks/useExtractionConfig.ts` (NEW) | controller hook: GET current (ETag) → mutate → invalidate | hook test |
| C3 | `frontend/.../knowledge/components/ExtractionTuningPanel.tsx` (NEW) | structural controls (model picker, filter category toggles, recovery/autocreate switches, pack select) | render + toggle→PUT; visibility/open-close |
| C4 | `frontend/.../knowledge/components/RawPromptEditor.tsx` (NEW) | per-op textarea, "advanced / affects quality" warning, length counter | render; warning visible; length guard |
| C5 | mount in project settings (existing settings surface) | wire panel | — |

**Browser-smoke C:** Playwright — open project settings → toggle a filter category + set a custom prompt → save → re-extraction uses both. Token: browser smoke.

---

## 4 · Sequencing / checkpoints
- **This session ends after PLAN** with a **design-checkpoint commit** (DESIGN + CLARIFY + PLAN docs, **no code**) per memory `design-checkpoint-commit…`. Future BUILD sessions inherit §0 locked interfaces.
- BUILD sessions: A → B(b1) → B(b2, with `/review-impl`) → C. Each gets its own 12-phase pass (memory `follow-task-workflow` — never batch BUILD across sub-cycles).
- D#055 row in SESSION_PATCH tracks the multi-session arc.

## 5 · PLAN sign-off — RESOLVED (PO-approved 2026-05-31)
- ✅ prompt length caps = **16 kB/field**.
- ✅ `outcome` adds **`'failed'`** (best-effort on the failure path) so crash-inducing configs are visible-as-bad.
- ✅ `prompt_pack_id` **dropped** from B2 (superseded by raw-prompt editing).
