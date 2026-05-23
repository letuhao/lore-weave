# Plan — P1 Structural Decomposer (hierarchical extraction T1)

> **Spec:** [`docs/specs/2026-05-23-p1-structural-decomposer.md`](../specs/2026-05-23-p1-structural-decomposer.md).
> **Parent ADR:** [`docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md).
> **Size:** XL · **Cycle:** session 62 (started 2026-05-23, continuing).
> **Workflow:** default v2.2 (no `/amaw`).

---

## 1. File-by-file breakdown

### NEW files (10)

| # | File | Purpose | Lines (est) |
|---|---|---|---|
| 1 | `sdks/python/loreweave_parse/__init__.py` | Public re-exports + version `__version__ = "0.1.0"` | ~25 |
| 2 | `sdks/python/loreweave_parse/_types.py` | Pydantic `Scene` / `Chapter` / `Part` / `StructuralTree` + `ParseOptions` + `ParseRequest` + `ParseResponse` envelopes; D8 + D6 schemas | ~110 |
| 3 | `sdks/python/loreweave_parse/html_walker.py` | `parse_html(content, options, filename) -> StructuralTree`; implements D4 (BS4 `html.parser`, `<body>`-only walk, `<h1>/<h2>/<h3>` mapping, `<hr/>` scene break, `html_to_leaf_text`) | ~220 |
| 4 | `sdks/python/loreweave_parse/plaintext_parser.py` | `parse_plain(content, language, filename) -> StructuralTree`; implements D5 (multi-language regex sets + auto-detect) | ~180 |
| 5 | `sdks/python/loreweave_parse/dispatcher.py` | `parse(source_format, content, language, filename, options) -> StructuralTree`; 2-branch switch (D3) | ~50 |
| 6 | `sdks/python/loreweave_parse/_text_strip.py` | `html_to_leaf_text(html) -> str` (D4 H2 fix — the locked algorithm); imported by `html_walker.py`. Separate module so P2/P3 tiptap-to-text helper can re-use the same collapsing pass | ~40 |
| 7 | `sdks/python/loreweave_parse/pyproject.toml` | NEW Python package; depends on `pydantic>=2.0`, `beautifulsoup4>=4.12`. **No HTTP / no LLM deps.** | ~30 |
| 8 | `services/knowledge-service/app/routers/internal/parse.py` | `POST /internal/parse`; reads body via `Request.body()` with 200MiB cap (H3); dispatches to SDK; OTel span | ~85 |
| 9 | `services/knowledge-service/tests/unit/test_internal_parse.py` | Per spec §4.2 — 8 test cases | ~180 |
| 10 | `services/worker-infra/internal/tasks/parse_client.go` | `callParse(ctx, html, format, language) (*StructuralTree, error)` HTTP client; OTel propagation; 5min timeout; no body cap on Go side (streaming) | ~110 |

### MODIFY files (8)

| # | File | Change |
|---|---|---|
| M1 | `sdks/python/pyproject.toml` (workspace root) | Add `loreweave_parse` to workspace packages list |
| M2 | `services/knowledge-service/app/main.py` (or wherever routers are wired) | Register `parse.router` under `/internal` prefix; add `MAX_PARSE_BODY_BYTES` env-read |
| M3 | `services/knowledge-service/requirements.txt` | Add `beautifulsoup4>=4.12,<5` |
| M4 | `services/knowledge-service/Dockerfile` | COPY the new SDK into the image (`COPY sdks/python/loreweave_parse /app/loreweave_parse` + `pip install -e /app/loreweave_parse`) |
| M5 | `services/book-service/internal/migrate/migrate.go` | Append D2 schema: `CREATE TABLE parts`, `CREATE TABLE scenes`, `ALTER TABLE chapters ADD COLUMN part_id`, `ALTER TABLE chapters ADD COLUMN structural_path`, indexes. No DO blocks, no backfill (R-SELF-1) |
| M6 | `services/book-service/internal/api/import.go` | (a) Add `".md": "markdown"` to `allowedImportFormats`. (b) `.txt` branch (lines 80-89): call new helper `s.processTxtImport(ctx, ownerID, bookID, lang, data, fh.Filename, jobID)` — implements H1 sync `/internal/parse` call + inline parts/scenes writes |
| M7 | `services/book-service/internal/api/server.go` | New helper methods: `callKnowledgeParse(ctx, content, language) (*StructuralTree, error)` + `insertPartInTx` + `insertSceneInTx` + `processTxtImport` (the `.txt` orchestrator from M6) |
| M8 | `services/worker-infra/internal/tasks/import_processor.go` | Replace `splitChapters(html, format)` call with `t.parseClient.Call(...)` + per-part Tx prelude + per-chapter Tx (D7 3-level scoping); chapterGlobalSort counter; multi-part filename pattern (L3) |

### DELETE (3 functions in 1 file)

| # | File | Deleted symbols |
|---|---|---|
| D1 | `services/worker-infra/internal/tasks/html_to_tiptap.go` | `splitChapters` (lines 17-61), `splitOnH1` (71-73), `splitOnTag` (75-end-of-fn), `h1Re` + `h2Re` regex globals (lines 68-69), `section` struct (63-66), `extractFirstHeading` (only callsite was `splitChapters` for DOCX) |

`htmlToTiptapJSON` stays — different concern, retained.

### NEW test files (4)

| # | File | Purpose |
|---|---|---|
| T1 | `sdks/python/tests/test_loreweave_parse_html_walker.py` | Per spec §4.1 HTML rows (6 tests) |
| T2 | `sdks/python/tests/test_loreweave_parse_plaintext.py` | Per spec §4.1 plaintext rows (6 tests) + auto-detect |
| T3 | `sdks/python/tests/test_loreweave_parse_roundtrip.py` | §4.1 lossless round-trip × 2 + deterministic-paths + no-outbound-HTTP (4 tests) |
| T4 | `services/worker-infra/internal/tasks/import_processor_test.go` | Per spec §4.3 (3 tests; .txt-test row removed per spec §4.3 update — handled by §4.3a in book-service) |
| T5 | `services/book-service/internal/api/import_test.go` | Per spec §4.3a — 3 tests for `.txt` sync `/internal/parse` path. **NEW file** if not present; check existing first. |
| T6 | `services/book-service/internal/migrate/migrate_test.go` | Per spec §4.4 — 3 idempotency tests for parts/scenes/chapters schema additions. **NEW file** if not present. |

**Total file count:** 10 NEW + 8 MODIFY + 1 DELETE-symbols + 6 NEW-test = 25 file touches. Reconciles with XL classification (12 logic files declared; the rest are tests + config).

---

## 2. Fixture corpora (L2 fix — enumeration)

10 fixtures under `sdks/python/tests/fixtures/loreweave_parse/`:

| # | Filename | Format | Language | Coverage purpose |
|---|---|---|---|---|
| 1 | `alice_en.html` | post-pandoc HTML | EN | EPUB-shaped HTML; 12 chapters with `<h2>` headings; round-trip lossless |
| 2 | `journey_west_zh.html` | post-pandoc HTML | ZH (trad.) | EPUB-shaped HTML; multi-part book (`第一部`/`第二部` via `<h1>`); chapters via `<h2>` (`第一回`) |
| 3 | `kim_van_kieu_vi.html` | post-pandoc HTML | VI | EPUB-shaped HTML; single-part; chapters `Chương 1`-`Chương 20` via `<h2>` |
| 4 | `genji_ja.html` | post-pandoc HTML | JA | EPUB-shaped HTML; chapters `第一帖` etc. via `<h2>` |
| 5 | `docx_sample.html` | post-pandoc HTML (DOCX origin) | EN | Single-`<h1>`-book (DOCX heading-1 = title); multiple `<h2>` chapters; `<hr/>` scene breaks via `***` dinkus |
| 6 | `markdown_sample.html` | post-pandoc HTML (MD origin) | EN | Setext + ATX header mix; pandoc normalised → `<h1>/<h2>/<h3>` ATX; tests R6 |
| 7 | `alice_plain_en.txt` | plain | EN | Roman numeral chapters (`I.`, `II.`); dinkus scene breaks; M3 regression (contains "I. understand" mid-paragraph + real `I.` heading on its own line) |
| 8 | `xianxia_plain_zh.txt` | plain | ZH (simp.) | `第一卷`/`第一章` part+chapter; `※ ※ ※` scene breaks |
| 9 | `truyen_plain_vi.txt` | plain | VI | `Phần I`/`Chương 1`/`Hồi 1` mixed (chapter detection wins); `– – –` em-dash scene breaks |
| 10 | `monogatari_plain_ja.txt` | plain | JA | `第一巻`/`第一章`/`その一` triple-marker; `◇◇◇` scene breaks |

**Auto-detect fixture** (covered by `xianxia_plain_zh.txt` + `truyen_plain_vi.txt` + `monogatari_plain_ja.txt` re-tested with `language=None` instead of explicit lang).

**Source ethics:** all 10 fixtures are public-domain (Alice, Journey to the West, Kim Vân Kiều, Genji Monogatari) or synthetic-by-author (DOCX/MD samples, plain-text xianxia synthetic short to avoid copyright). Document provenance in `tests/fixtures/loreweave_parse/README.md`.

---

## 3. Implementation order (DAG)

```
[1] SDK loreweave_parse (no external deps) ────────────────┐
       _text_strip.py                                       │
       _types.py                                            │
       html_walker.py  ←─ uses _text_strip + _types        │
       plaintext_parser.py ←─ uses _types                  │
       dispatcher.py ←─ uses html_walker + plaintext       │
       pyproject.toml                                      │
       SDK tests (T1+T2+T3)                                │
                                                            │
[2] knowledge-service /internal/parse router ←─────────────┤
       parse.py + main.py wire-up                          │
       requirements.txt + Dockerfile                        │
       Router unit tests (T file from spec §4.2)            │
                                                            │
[3] book-service Postgres schema ←─ migrate.go             │
       migrate_test.go (T6)                                 │
                                                            │
[4] worker-infra integration ←─ steps 2 + 3                 │
       parse_client.go                                     │
       import_processor.go (replace splitChapters)         │
       DELETE html_to_tiptap.go:splitChapters et al.       │
       Tests T4                                            │
                                                            │
[5] book-service .txt sync path ←─ steps 2 + 3              │
       import.go .txt branch + server.go helpers           │
       Tests T5                                            │
                                                            │
[6] Live smoke (cross-service) ←─ steps 4 + 5              │
       per spec §4.5
```

**Dependency rules:**
- Step 1 has NO external dependency — pure Python SDK, can be built + tested in isolation.
- Step 2 depends on step 1 (imports the SDK).
- Step 3 is independent of 1/2 — pure schema; can be done in parallel.
- Steps 4 + 5 depend on 2 + 3 (need both router + schema before integration).
- Step 6 (live smoke) depends on all prior + a running compose stack.

**Suggested commit grain:** one commit per step. 6 commits total. Step 1 alone is ~700 LoC + tests so warrants its own commit. Each subsequent step is smaller delta.

---

## 4. Migration sequence (book-service `migrate.go`)

The migration runs every service start via `migrate.Run(pool)` (existing pattern). It must be:
- **Idempotent** — second run is no-op (use `CREATE TABLE IF NOT EXISTS` + `ALTER ... ADD COLUMN IF NOT EXISTS`).
- **Forward-only** — no DOWN migrations. Schema added to `schemaSQL` after the existing chapter blocks.
- **Concurrent-safe** — `IF NOT EXISTS` clauses are PG-native concurrency-safe.

Order within `schemaSQL` (appended at end):

```sql
-- ═══════════════════════════════════════════════════════════════
-- P1 (hierarchical extraction T1) - 2026-05-23
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS parts (...);                  -- per spec D2
CREATE TABLE IF NOT EXISTS scenes (...);                 -- per spec D2

ALTER TABLE chapters ADD COLUMN IF NOT EXISTS part_id UUID
  REFERENCES parts(id) ON DELETE SET NULL;
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS structural_path TEXT;

CREATE INDEX IF NOT EXISTS idx_scenes_chapter_sort_active
  ON scenes(chapter_id, sort_order) WHERE lifecycle_state = 'active';
CREATE INDEX IF NOT EXISTS idx_scenes_content_hash ON scenes(content_hash);
CREATE INDEX IF NOT EXISTS idx_chapters_part ON chapters(part_id)
  WHERE part_id IS NOT NULL;
```

**Test (`migrate_test.go`):**
- Fresh DB run → all tables + columns + indexes exist; idempotent re-run is no-op.
- Pre-existing DB (chapters present, no parts) → migration adds parts table empty; `chapters.part_id` column NULL for all existing rows; `chapters.structural_path` NULL.

**Rollback plan (operational, NOT in schemaSQL):** if a build fails mid-cycle and we need to roll back, manual SQL:
```sql
DROP INDEX IF EXISTS idx_scenes_chapter_sort_active;
DROP INDEX IF EXISTS idx_scenes_content_hash;
DROP INDEX IF EXISTS idx_chapters_part;
ALTER TABLE chapters DROP COLUMN IF EXISTS structural_path;
ALTER TABLE chapters DROP COLUMN IF EXISTS part_id;
DROP TABLE IF EXISTS scenes;
DROP TABLE IF EXISTS parts;
```

Document this rollback in SESSION_PATCH under "Cycle deferrals" only if BUILD actually requires it (memory `feedback_no_timeout_on_llm_pipeline` corollary — don't pre-emptively script rollback into the migrator).

---

## 5. Test sequencing

Run in order; each gate must pass before the next stage starts:

| Stage | Command | Expected |
|---|---|---|
| 5a | `pytest sdks/python/tests/test_loreweave_parse_*.py -v` | All 18 SDK tests green; <3s wall-clock (no I/O) |
| 5b | `pytest services/knowledge-service/tests/unit/test_internal_parse.py -v` | 8 router tests green |
| 5c | `pytest services/knowledge-service/tests/unit/ -v` | Full knowledge-service unit baseline preserved (currently 1620/1620 per session 59) → 1620 + 8 = 1628 |
| 5d | `cd services/book-service && go test ./internal/migrate/... ./internal/api/...` | Migrate tests pass; existing import_test.go regressions caught |
| 5e | `cd services/worker-infra && go test ./internal/tasks/...` | parse_client + import_processor_test pass |
| 5f | Live smoke (compose up + EPUB upload + DB assertions) | Per spec §4.5 |

**Cross-service evidence (CLAUDE.md soft-WARN):** stages 5d + 5e + 5f all touch ≥2 services (worker-infra + book-service + knowledge-service); VERIFY evidence string MUST include `live smoke: Alice EPUB → 1 part / N chapters / N+ scenes in book DB, leaf_text round-trips`. No deferral acceptable for P1 (live infra IS available).

---

## 6. Risk-driven sequencing notes

- **Step 1 (SDK) first** because: pure Python, no infra, all bugs visible from unit tests. Catching schema/contract bugs here saves later rework.
- **Step 3 (schema) before steps 4/5** because: integration tests in 4/5 need the tables. Schema change is forward-only + idempotent → can run before code uses it.
- **Step 5 (.txt sync) after step 4 (worker-infra async)** because: .txt path replicates the same `/internal/parse` call + tree-write code from worker-infra. Building worker-infra integration first means step 5 can copy-paste the orchestration pattern; reduces double-rework.
- **Live smoke (step 6) last** because: requires all prior pieces. Memory `feedback_mock_only_coverage_hides_crossservice_bugs` — live smoke is the actual cross-service truth.

---

## 7. Open implementation questions (resolve at BUILD)

- **IQ1 — SDK auto-detect tie-break implementation:** spec D5 says "prefer the language with the FIRST chapter match by file position". Concrete impl: run each language's chapter regex with `re.search` (first match only), record `(language, match.start())` for any match, pick min-start. Document the tie-break in `plaintext_parser.py:detect_language()` docstring.
- **IQ2 — book-service `processTxtImport` failure status code:** spec D6 says 502 on `/internal/parse` 500. Confirm via the existing `writeError` helper pattern. Use `BOOK_PARSE_UPSTREAM_FAILURE` error code (NEW).
- **IQ3 — `scenes.content_hash` collision detection across books:** UNIQUE constraint? **NO** — same scene text in different books is legitimate (e.g. two translations of the same novel) AND P2 task-ID caching relies on cross-book hash hits. Plain index only.
- **IQ4 — `parse_client.go` retry policy:** none in P1. `/internal/parse` is deterministic; if it 5xx's once it'll 5xx again. Fail the import job; user can retry via UI. Document in `parse_client.go` package doc.

---

## 8. Pre-flight checks (before BUILD starts)

- [ ] Confirm `loreweave_parse` package name not used: `grep -r "loreweave_parse" sdks/`.
- [ ] Confirm knowledge-service has `requirements.txt` (not Poetry/uv lockfile drift): `ls services/knowledge-service/requirements.txt`.
- [ ] Confirm book-service `import.go` line 80-89 `.txt` branch matches spec assumption.
- [ ] Confirm pandoc version in compose stack supports `--standalone` for our format mix: `docker compose run --rm pandoc-server pandoc --version`.
- [ ] Confirm `internal_token` env is wired into knowledge-service for `/internal/*` middleware (existing — used by chat-service `BillingClient` already).

All 5 pre-flight items will be confirmed at BUILD entry.

---

## 9. Estimated effort

- Step 1 (SDK + tests): ~4 h (most expensive — new abstraction, careful regex)
- Step 2 (router + tests): ~1 h
- Step 3 (schema + tests): ~0.5 h
- Step 4 (worker-infra + tests): ~2 h
- Step 5 (book-service `.txt` + tests): ~1.5 h
- Step 6 (live smoke): ~1 h

**Total: ~10 h working time.** Single session feasible if focused; otherwise split at the step-1/step-2 boundary (clean cut: SDK is self-contained).
