# Enhancement Handoff — glossary-display-language · parent: feat/auto-draft-factory-gaps · started 2026-06-12

> **Track:** isolated enhancement — does NOT update `docs/sessions/SESSION_HANDOFF.md`

## ▶ NEXT SESSION

- [x] **GLOSS-DISPLAY-LANG** — per-book display language picker + list/detail resolve

**Spec:** [`docs/specs/2026-06-12-glossary-display-language.md`](../../specs/2026-06-12-glossary-display-language.md)  
**Plan:** [`docs/plans/2026-06-12-glossary-display-language.md`](../../plans/2026-06-12-glossary-display-language.md)

### Verify evidence (2026-06-12)

- `go test ./internal/api -run DisplayLanguage -count=1` — pass
- `npm run test -- --run src/features/glossary/lib` — 6 passed
- `tsc --noEmit` — green

## Deferred

(none)
