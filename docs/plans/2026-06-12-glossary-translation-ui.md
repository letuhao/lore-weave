# Glossary Batch Translation UI — Plan

> **Epic size:** XL · **Milestones:** GT-0..GT-3 serial `/loom`

## GT-1 — glossary-service (M)

| File | Action |
|------|--------|
| `internal/api/glossary_translate_handler.go` | NEW handlers |
| `internal/api/server.go` | Register routes |
| `internal/api/glossary_translate_handler_test.go` | Integration tests |

**Verify:** `cd services/glossary-service && go test ./internal/api -run GlossaryTranslate -count=1`

## GT-2 — translation-service + gateway (L)

| File | Action |
|------|--------|
| `app/migrate.py` | `glossary_translation_jobs` table |
| `app/routers/glossary_translate.py` | Public API |
| `app/workers/glossary_translate_worker.py` | Worker |
| `app/workers/glossary_translate_prompt.py` | LLM prompt + parse |
| `app/workers/glossary_client.py` | fetch candidates + apply |
| `app/main.py` | Include router |
| `app/broker.py` | `glossary_translate.jobs` queue |
| `worker.py` | Consume queue |
| `api-gateway-bff/src/gateway-setup.ts` | Proxy `/v1/glossary-translate` |

**Verify:** `cd services/translation-service && python -m pytest tests/test_glossary_translate_router.py -q`

## GT-3 — frontend (M)

| File | Action |
|------|--------|
| `frontend/src/features/glossary-translate/*` | Wizard feature |
| `frontend/src/pages/book-tabs/GlossaryTab.tsx` | Button |
| `frontend/src/i18n/locales/*/glossaryTranslate.json` | 4 locales |

**Verify:** `cd frontend && npm run test -- --run src/features/glossary-translate`
