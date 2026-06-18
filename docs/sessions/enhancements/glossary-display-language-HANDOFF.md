# Enhancement Handoff — glossary-display-language · parent: feat/auto-draft-factory-gaps · started 2026-06-12

> **Track:** isolated enhancement — does NOT update `docs/sessions/SESSION_HANDOFF.md`

## ▶ NEXT SESSION

- [x] **GLOSS-DISPLAY-LANG** — per-book display language picker + list/detail resolve
- [x] **GLOSS-DISPLAY-LANG-REVIEW** — P1/P2 fixes (no book lang, pref flash, name sort, view UX, prefMap, translation-languages API)

**Spec:** [`docs/specs/2026-06-12-glossary-display-language.md`](../../specs/2026-06-12-glossary-display-language.md)  
**Plan:** [`docs/plans/2026-06-12-glossary-display-language.md`](../../plans/2026-06-12-glossary-display-language.md)

### Verify evidence (review fixes 2026-06-12)

- `go test ./internal/api -run "DisplayLanguage|TranslationLanguages" -count=1` — pass
- `npm run test -- --run src/features/glossary/lib` — 11 passed
- `tsc --noEmit` — green

## Deferred

(none)
