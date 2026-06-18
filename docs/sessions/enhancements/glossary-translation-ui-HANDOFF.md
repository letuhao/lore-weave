# Enhancement Handoff — glossary-translation-ui · parent: origin/main · started 2026-06-12

> **Track:** isolated enhancement — does NOT update `docs/sessions/SESSION_HANDOFF.md`

## ▶ NEXT SESSION

- [x] **GT-0..GT-3** — initial implementation
- [x] **GT-REVIEW** — code review + bugfix (pagination, SQL $2, infinite loop, FE hardening)
- [ ] Optional: browser smoke Glossary tab → Translate wizard (manual)
- [ ] **D-GT-FILTERS** — wire `kind_codes` / `entity_status` in worker when needed

**Spec:** [`docs/specs/2026-06-12-glossary-translation-ui.md`](../../specs/2026-06-12-glossary-translation-ui.md)  
**Plan:** [`docs/plans/2026-06-12-glossary-translation-ui.md`](../../plans/2026-06-12-glossary-translation-ui.md)

### Verify evidence (GT-REVIEW 2026-06-12)

- `go test ./internal/api -run GlossaryTranslate -count=1` — pass (incl. candidates missing_only + refresh_machine)
- `pytest tests/test_glossary_translate_*.py` — 10 passed (router, worker, prompt)
- `npm run test -- --run src/features/glossary-translate` — 6 passed; `tsc --noEmit` green
- `python scripts/ai-provider-gate.py` — OK
- **live smoke:** gateway `/v1/glossary-translate/jobs/*` → **401** (not 404); `GT_SAME_LANGUAGE` **422**; candidates `total=11`; job `019ebb5e…` translated **138 attrs** machine `vi` on book `019eb60e…` (11 entities) — worker infinite-loop on partial entities **fixed** (`processed_entity_ids` dedupe)

## Deferred

| ID | Description |
|----|-------------|
| D-GT-FILTERS | Wire `kind_codes` / `entity_status` metadata filters in worker |
| D-GT-MCP-S4 | MCP assistant `glossary_propose_translation` |
| D-GT-ALIASES-S6 | Per-language alias model |
| D-GT-TRANS-TAB | Translation tab entry point |
| D-GT-DECOUPLE | Event-resume decouple for glossary translate jobs |

## Recently cleared

- **D-GT-LIVE-SMOKE** — cleared GT-REVIEW (stack rebuild + curl/job evidence)
- GT-0..GT-3 implementation (2026-06-12)
