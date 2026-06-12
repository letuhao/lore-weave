# De-bias C3 — Profile authoring (slices 0d + 0e) · PLAN · 2026-06-03

> Design (locked + benchmarked): [docs/specs/2026-06-03-enrichment-debias-book-profile.md](../specs/2026-06-03-enrichment-debias-book-profile.md) §2.7 + §4 slices 0d/0e + §6.
> Cycle decomposition: [docs/plans/2026-06-03-debias-cycle-decomposition.md](2026-06-03-debias-cycle-decomposition.md) (C3 row).
> Branch `lore-enrichment/foundation`. **XL** — full 12-phase v2.2 with human-in-loop (PO at CLARIFY-end [inherited from spec] + POST-REVIEW per slice). C1+C2 are COMPLETE + live-proven; C3 is the authoring UX on top of C1's profile model.

## Size classification
**XL** — BE ~7 files + FE ~10 files; side effects = new API surface (3 routes) + 1 LLM call + cross-service reads (book + knowledge). Spec already written (this cycle's CLARIFY/DESIGN inherited). Two independently-shippable slices, each its own VERIFY + POST-REVIEW + COMMIT.

---

## Focused DESIGN-review (resolving spec §6 "confirm in PLAN")

All open items from the spec resolved against live code this session:

1. **book-service metadata endpoint — NO new Go endpoint (confirmed richer than spec assumed).** `GET /internal/books/{book_id}/projection` (`server.go:1717`) already returns `title`, `description`, `original_language`, `summary_excerpt` (180-char), `genre_tags`, `chapter_count`, `lifecycle_state`. The spec feared "no synopsis field" → in fact `description` + `summary_excerpt` + `genre_tags` give AI-suggest a real synopsis seed; sample-chapter text is supplementary, not the only signal. `GET /internal/books/{book_id}/chapters` (`server.go:1778`) returns `{items:[{chapter_id,title,sort_order,original_language,word_count_estimate}], total, limit, offset}` — exactly the chapter-selection picker + sampling source. `clients/book.py` already has `get_chapter_text` (C2). **→ add `get_projection` + `list_chapters` only.**
2. **`kind_label_for(kind, language)` + `freeform` kind — already shipped in C1** (`gaps/model.py` `_KIND_LABELS`; `freeform`→GENERIC). C3 reuses; the dimension-override editor keys on the same built-in kinds + GENERIC.
3. **Profile read consistency (detect-vs-run drift window) — documented, accepted.** Profile is read fresh at run; an author editing between detect and enrich has a small drift window (spec §6 finding F). C3 adds an authoring path → makes edits more frequent, but the drift is benign (worst case: a freshly-added dimension is missed for one in-flight job; re-detect picks it up). No locking; document in the FE ("changes apply to new jobs").
4. **AI-suggest LLM seam — reuse `generation/complete.py` `make_complete_fn`** (provider-registry `/internal/llm/stream`, model resolved by `model_ref` off context — NO hardcoded model name; consistent with every other LLM call). Author supplies `model_ref` (BYOK) in the suggest request, same convention as embed/generate.
5. **KG summary for suggest — reuse `KnowledgeClient.build_context`** (`message = title + genre hint`, project-scoped, best-effort). Empty/down graph → degrade to book-only (never blocks suggest). No new knowledge endpoint.
6. **Override JSON server-validation — reuse C1's `_apply_overrides` contract shape** (`{kind: {add:[...], remove:[...], relabel:{...}, reweight:{...}}}`). The PUT/suggest handler validates structurally (dict-of-dict, known op keys, add-specs have id+label, weights numeric) BEFORE persist; malformed → 400/dropped. C1's `resolve_dimensions` is already defensively guarded against malformed overrides (review #1), so validation is defense-in-depth, not the only guard.

**No new schema** — `enrichment_book_profile` table + columns landed in C1 (migrate.py). C3 only adds the **write** path (`upsert_book_profile`) over the existing reader.

---

## Slice 0d — Profile API + AI-suggest (BE)

**Acceptance (spec §4):** suggest returns a sane draft incl. genre dimensions for a non-Fengshen book (book-only when KG empty); PUT round-trips + rejects malformed overrides; GET returns neutral default when unset; H0/scope guards (auth + book ownership via the row's project).

### TDD task order

| # | Task | Test-first |
|---|---|---|
| **T1** | `clients/book.py`: `get_projection(book_id) -> BookProjection` (frozen dc: title/original_language/description/summary_excerpt/genre_tags/chapter_count) + `list_chapters(book_id, limit, offset) -> (list[ChapterMeta], total)`. Injection-neutralize title/description/summary (author-supplied source, M4). 404→typed `BookServiceError`. | `test_book_client.py`: respx mock projection + chapters; assert shapes, neutralize, 404. |
| **T2** | `db/book_profile.py`: `upsert_book_profile(pool, book_id, *, worldview, language, era_policy, voice, anachronism_markers, dimension_overrides, profile_source) -> BookProfile`. `$N::jsonb` write (json.dumps) for markers+overrides; `ON CONFLICT (book_id) DO UPDATE` + `updated_at=now()`. Round-trips through the existing reader. | `test_book_profile.py` (+): upsert→get round-trip (incl. markers tuple + overrides dict); update path; jsonb serialization. |
| **T3** | `db/book_profile.py`: `validate_dimension_overrides(raw) -> dict` — structural validation (dict; per-kind dict; op keys ⊆ {add,remove,relabel,reweight}; add=list-of-{id,label,(weight,required,payload_shape)}; remove=list[str]; relabel/reweight=dict; weights numeric). Returns the cleaned dict or raises `ValueError`. | `test_book_profile.py` (+): valid passes; non-dict, bad op key, add-without-id, non-numeric weight each rejected. |
| **T4** | `api/book_profile.py` (NEW): `GET /v1/lore-enrichment/books/{book_id}/profile` → `get_book_profile` (neutral default if unset; 200). Auth-required; view shaping (markers→[{term,reason}], overrides passthrough, anachronism_enabled). | `test_book_profile_api.py`: 401 no-auth; 200 unset→neutral; 200 set→values. |
| **T5** | `api/book_profile.py`: `PUT …/profile` → `validate_dimension_overrides` then `upsert_book_profile(profile_source='manual')`; 400 on malformed overrides; 200 with the persisted profile. | API test: round-trip PUT→GET; 400 malformed overrides; auth guard. |
| **T6** | `services/profile_suggest.py` (NEW): `suggest_profile(book, kg_summary, complete_fn, language_hint) -> SuggestedProfile` — build the one-LLM-call prompt (book metadata + sample-chapter excerpts + KG summary), parse JSON → worldview/language/era_policy/voice + per-kind dimension_overrides; validate overrides (drop malformed, never raise); degrade-safe (LLM error → `CompletionSeamError` mapped to 502). Pure-ish (complete_fn injected). | `test_profile_suggest.py`: fake complete_fn returns JSON → parsed draft; malformed-override JSON → dropped not raised; empty KG → book-only prompt. |
| **T7** | `api/book_profile.py`: `POST …/profile/suggest {project_id, suggest_model_ref, sample_chapter_ids?}` → projection + sample chapters (book-client) + build_context KG summary (best-effort) + `make_complete_fn(model_ref)` → `suggest_profile`; returns the DRAFT (does NOT persist; `profile_source='ai_suggested'`). 502 on LLM failure; degrade-safe KG. | API test (respx book + knowledge + provider-registry stream): suggest→draft; KG-down→book-only draft; LLM-error→502. |
| **T8** | Wire `app.include_router(book_profile.router)` in `main.py`; add the 3 paths to `contracts/api/lore-enrichment/v1/openapi.yaml`; update contract tests (`test_api_contract.py` no-orphan-route; exclude /profile/suggest from the 501-stub family). | `test_api_contract.py` green (routes declared). |

**Live smoke (≥2 services → cross-service token):** on the demo Fengshen book — `POST …/profile/suggest` with the test user's qwen model_ref → a draft profile (worldview/language/era + character/location dimension_overrides) grounded in real book metadata + KG; `PUT` it; `GET` round-trips. Token: `live smoke: suggest+put+get profile on demo book via real book/knowledge/provider-registry`.

---

## Slice 0e — FE Settings panel (frontend/src/features/enrichment/)

**Acceptance (spec §4):** author can suggest + edit a profile (incl. dimensions) and it round-trips; FE vitest green; "extract first" empty-state messaged (KB2).

### TDD task order

| # | Task | Test-first (vitest) |
|---|---|---|
| **F1** | `api.ts` + `types.ts`: `BookProfile`, `SuggestedProfile`, `DimensionOverride` types; `getBookProfile/putBookProfile/suggestBookProfile` calls (relative `/v1`). | n/a (typed; covered via hook tests) |
| **F2** | `hooks/useBookProfile.ts` ("controller"): own load/save/suggest state + error; no JSX. Self-contained (own state+effects+cleanup). | `useBookProfile.test.tsx`: load→data; save→optimistic+persist; suggest→draft into form; error surfaces. |
| **F3** | `components/SettingsPanel.tsx` (view): worldview/language/era/voice fields + "Suggest from book" button + save; ≤100 lines (split sub-views). Renders only, data from hook/props. | `SettingsPanel.test.tsx`: renders fields from profile; suggest fills form; save calls hook; disabled while loading. |
| **F4** | `components/DimensionOverrideEditor.tsx`: per-kind add/remove/relabel/reweight editor over the override shape; emits the validated override dict. | `DimensionOverrideEditor.test.tsx`: add a dim; remove; relabel; reweight; emits correct shape. |
| **F5** | `components/ChapterSelectionPicker.tsx` (optional grounding + suggest sampling): lists chapters (book-client via a small `/v1` proxy or reuse), checkbox selection → chapter_ids. Reuses the C2 `…/ground` ingest + feeds suggest sampling. | `ChapterSelectionPicker.test.tsx`: lists chapters; multi-select; emits ids. |
| **F6** | `EnrichmentView.tsx` + `context/EnrichmentContext.tsx`: add a **Settings** tab/sub-view (CSS-hidden switch, NEVER conditional-unmount — stateful hook); "extract first" empty-state when the book has no extracted entities (KB2 messaging). | `EnrichmentView.test.tsx` (+): Settings tab renders; tab switch preserves state; empty-state shows. |
| **F7** | i18n: `enrichment` namespace keys for the panel + dimension editor + extract-first message in **en / vi / ja / zh-TW**. | covered by component tests asserting `t()` keys exist (or a key-parity check). |

**FE verify:** `docker compose build frontend` (= `tsc --noEmit && vite build`) + `vitest run` on the enrichment feature (this worktree's FE deps; the suite was 821 green after C-closure). No browser e2e required (shared-Chrome locked; unit + the BE live smoke cover it).

---

## Cross-cycle invariants (must hold)
- **No-regression:** the Fengshen profile (seeded in C1) is unchanged by C3; GET returns its seeded values; a PUT that re-sends them is a no-op-equivalent.
- **H0 untouched:** C3 is authoring only — it writes the *profile*, never canon. No promote/write-back change.
- **No hardcoded model name:** suggest's LLM call resolves by `model_ref` (BYOK), same as generate/embed.
- **No new Go endpoint** (book projection/chapters/draft-text + knowledge build_context all exist).
- **Scope (Q3):** GET/PUT/suggest auth-required; the profile is book-scoped; suggest's KG read is (user,project)-scoped via the JWT/internal-token convention already in the clients.

## Sequencing
0d (BE) → 0e (FE). 0d is shippable + live-provable alone; 0e consumes its API. Each slice: BUILD → VERIFY (evidence) → REVIEW (2-stage) → QC → **POST-REVIEW (human gate)** → SESSION → COMMIT.

## Deferred / residual (carry forward)
- `LE-debias-eval-suite` (eval-gate de-bias) — unchanged, still deferred (P1 any-book correct; P2/P3 Fengshen-gated).
- Detect-vs-run profile drift window — documented, accepted (no locking).
- A full shared-library curation UI — deferrable (C2 shipped the read-path; admin-curated writes).
- Per-job profile override (`/compose` patch) — Compose owns it, not C3.
