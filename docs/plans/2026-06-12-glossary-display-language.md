# Plan — Glossary Display Language

## Files

| Area | File |
|------|------|
| BE | `services/glossary-service/internal/api/entity_handler.go` |
| BE test | `services/glossary-service/internal/api/entity_list_display_language_test.go` |
| FE hook | `frontend/src/features/glossary/hooks/useGlossaryDisplayLanguage.ts` |
| FE helper | `frontend/src/features/glossary/lib/resolveDisplayValue.ts` |
| FE api | `frontend/src/features/glossary/api.ts` |
| FE tab | `frontend/src/pages/book-tabs/GlossaryTab.tsx` |
| FE modal | `frontend/src/components/entity-editor/EntityEditorModal.tsx` |
| i18n | `frontend/src/i18n/locales/*/books.json`, `entityEditor.json` |

## BUILD order

1. BE `display_language` query param + search extension + test
2. FE helper + hook + api
3. GlossaryTab picker + query key
4. EntityEditorModal view layer
5. i18n + vitest

## Verify

- `go test ./internal/api -run DisplayLanguage -count=1`
- `npm run test -- --run src/features/glossary`
- `tsc --noEmit`
