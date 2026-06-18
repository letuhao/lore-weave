# SESSION_PATCH — glossary-translation-ui enhancement track



> Append-only cycle log. Main track: `docs/sessions/SESSION_PATCH.md` (untouched).



- Last Updated: 2026-06-12 **(GT-0 /loom docs+spec+plan, XS)** [enhancement track]

  CLARIFY: spec + plan written; enhancement HANDOFF/PATCH bootstrapped.

  NEXT: GT-1 glossary internal API.



- Last Updated: 2026-06-12 **(GT-1 /loom glossary internal API, BE M)** [enhancement track]

  BUILD: `glossary_translate_handler.go` — GET translation-candidates, POST apply-translations; verified-guard upsert; M6b events.

  VERIFY: `go test ./internal/api -run GlossaryTranslate -count=1` green.

  NEXT: GT-2 translation-service job.



- Last Updated: 2026-06-12 **(GT-2 /loom translation job+gateway, BE L)** [enhancement track]

  BUILD: `glossary_translation_jobs` migration; `glossary_translate.py` router; `glossary_translate_worker.py`; gateway `glossaryTranslateProxy`; RabbitMQ `glossary_translate.jobs`.

  VERIFY: `pytest tests/test_glossary_translate_router.py tests/test_glossary_translate_prompt.py` — 5 passed.

  NEXT: GT-3 frontend wizard.



- Last Updated: 2026-06-12 **(GT-3 /loom FE wizard, FE M)** [enhancement track]

  BUILD: `frontend/src/features/glossary-translate/*`; `GlossaryTab` `glossary-translate-trigger`; i18n `glossaryTranslate` en/vi/ja/zh-TW + `books.glossary.translate`.

  VERIFY: vitest 3 passed; `tsc --noEmit` green.

  LIVE-SMOKE: deferred D-GT-LIVE-SMOKE (stack containers pre-date proxy/router — gateway 404).

  NEXT: rebuild stack + D-GT-LIVE-SMOKE when ready.



- Last Updated: 2026-06-12 **(GT-REVIEW /loom bugfix, M)** [enhancement track]

  REVIEW: Stage-1/2 — verified guard OK; P0 worker offset skip; glossary SQL unused $2 (500 live); missing_only infinite re-LLM loop.

  BUILD: worker offset=0 + processed_entity_ids; entity_ids metadata wire; glossary attr query fix; FE reset/onComplete guard; GT_SAME_LANGUAGE; zero-entity UX.

  VERIFY: go 5 GlossaryTranslate; pytest 10; vitest 6; ai-provider-gate OK.

  live smoke: gateway 401; same_lang 422; candidates total=11; job 138 attrs vi machine on 11 entities.

  NEXT: D-GT-FILTERS; optional browser smoke.

