# Glossary Batch Translation UI — Spec

> **Status:** Approved (enhancement track GT-0)  
> **Gap:** S4 in `glossary-assistant-scenario-coverage.md` — CRUD exists, batch flow missing  
> **Scope:** All translatable attributes (`original_value` non-empty, `is_active` attr defs)

## Problem

Glossary extraction writes source-language entities. Users need a **batch translate** flow (mirror ExtractionWizard) to populate `attribute_translations` at `confidence=machine` without hand-editing each entity.

## Non-goals

- MCP assistant tools (deferred D-GT-MCP-S4)
- Per-language aliases (S6)
- Changing extraction or chapter translation pipelines

## Entry point (v1)

**Glossary tab** toolbar — button `glossary-translate-trigger` beside Extract.

## Data flow

```
User → GlossaryTranslateWizard → POST /v1/glossary-translate/books/{id}/translate
  → translation-service job (RabbitMQ glossary_translate.job)
  → worker: GET glossary /internal/.../translation-candidates (paginated)
  → LLM per entity (all attrs in one JSON object)
  → POST glossary /internal/.../apply-translations
  → poll GET /v1/glossary-translate/jobs/{id}
```

## Upsert rules (glossary-service)

- Insert when no `(attr_value_id, language_code)` row
- Update when existing `confidence IN ('draft','machine')`
- **Never** overwrite `verified`
- `confidence='machine'`, `translator='glossary-translate'`
- Emit `emitTranslationChanged` per affected entity (M6b)

## API surface

### glossary-service (internal)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/internal/books/{book_id}/translation-candidates` | Paginated attrs needing translation |
| POST | `/internal/books/{book_id}/apply-translations` | Bulk upsert |

Query `translation-candidates`: `target_language` (required), `overwrite_mode=missing_only|refresh_machine`, `limit`, `offset`, optional `entity_ids`.

### translation-service (public via gateway)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/glossary-translate/books/{book_id}/translate` | 202 create job |
| GET | `/v1/glossary-translate/jobs/{job_id}` | Status |
| POST | `/v1/glossary-translate/jobs/{job_id}/cancel` | Cancel |

Grant: `edit` to create/cancel; `view` to poll.

## Acceptance

1. Wizard completes job; name + description attrs get `vi` machine translations
2. Verified translations unchanged on re-run with `refresh_machine`
3. Partial failures reported in job status + StepResults
4. Enhancement HANDOFF/PATCH updated per milestone; main SESSION files untouched
