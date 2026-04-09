# Session Handoff — Session 29

> **Purpose:** Give the next agent complete context to continue.
> **Date:** 2026-04-10 (session 29 end)
> **Last commit:** `6db8553` — fix: forward usage tokens in provider-registry, parse JSONB string
> **Uncommitted work:** None
> **Previous focus:** Phase 9 COMPLETE (session 28), V2 pipeline design
> **Current focus:** Translation Pipeline V2 — IMPLEMENTED AND TESTED

---

## 1. What Happened This Session (3 commits)

| Commit | What |
|--------|------|
| `662cbf7` | Translation Pipeline V2 full implementation (P1-P8): CJK token fix, expansion-ratio budget, 40-block cap, output validation + retry, multi-provider token extraction, glossary injection, rolling context, auto-correct, chapter memo, quality metrics. 17 files, 2305 lines. |
| `1aa25b3` | Glossary endpoint Tier 2 fallback — when no chapter_entity_links exist, return all active entities |
| `6db8553` | Provider-registry forward usage tokens + translation-service JSONB string parse fix |

**Services touched:** translation-service, glossary-service, provider-registry-service

**Integration tested:** Docker Compose with real Ollama gemma3:12b
- Chapter 1 (132 blocks): 4 batches, all valid first attempt, ~68s
- Chapter 2 (113 blocks): 3 batches, all valid, ~51s, in=5223 out=3670
- Glossary: 12 entries (characters, locations, orgs, species), ~179 tokens overhead

---

## 2. Translation Pipeline V2 — What Was Built

| Priority | Feature | Status |
|----------|---------|--------|
| P1 | CJK-aware token estimation (fixes 2.3x undercount) | **Done** |
| P2 | Output validation + retry (2 retries with correction prompt) | **Done** |
| P3 | Multi-provider token extraction (OpenAI/Anthropic/Ollama/LM Studio) | **Done** |
| P4 | Glossary context injection (tiered, scored, JSONL from glossary-service) | **Done** |
| P5 | Rolling summary context between batches | **Done** |
| P6 | Auto-correct post-processing (source term replacement) | **Done** |
| P7 | Cross-chapter memo table + load/save | **Done** |
| P8 | Quality metrics columns on chunk rows | **Done** |

**Key files:**
- `translation-service/app/workers/chunk_splitter.py` — CJK-aware `estimate_tokens()`
- `translation-service/app/workers/block_batcher.py` — expansion ratio budget, 40-block cap
- `translation-service/app/workers/session_translator.py` — V2 block pipeline with validation, retry, glossary
- `translation-service/app/workers/glossary_client.py` — **NEW** glossary fetch + context builder + auto-correct
- `translation-service/app/workers/chapter_worker.py` — chapter memo load/save
- `translation-service/app/migrate.py` — V6: memo table + metrics columns
- `glossary-service/internal/api/server.go` — `GET /internal/books/{book_id}/translation-glossary`
- `provider-registry-service/internal/api/server.go` — usage tokens in invoke response

**Tests:** 280 pass (31 new V2 tests), 5 pre-existing chapter_worker mock failures

---

## 3. What's Next

### Immediate candidates

| Priority | Item | Notes |
|----------|------|-------|
| **P0** | **Translation quality review** | Read actual translated chapters in browser, check glossary name accuracy |
| **P1** | **Chapter entity linking** | Currently no chapter_entity_links → Tier 2 fallback returns all entities. Entity linking would enable Tier 0+1 precision |
| **P2** | **Glossary extraction pipeline** | Auto-discover entities from chapter text (separate from translation) |
| **P2** | **Provider-registry token passthrough for text pipeline** | Text pipeline also uses `extract_token_counts()` — now works |
| **P3** | **Frontend: translation progress with token counts** | Token data now available, can show in UI |
| **P3** | **Quality dashboard** | validation_errors, retry_count, glossary_corrections now in DB |

### Known issues

1. **Length warnings (too_long 4-5x):** CJK→Vietnamese expansion can be 4-5x for short blocks. Current threshold is 4.0x which triggers many false warnings. Consider raising to 6.0x for CJK→Latin pairs.
2. **Pre-existing test failures:** 5 `test_chapter_worker.py` tests fail due to `db.transaction()` async mock issue — not V2-related.
3. **Glossary entry status:** New entities default to `draft` status. Must be set to `active` to appear in translation glossary.

---

## 4. Architecture Context

### Translation Pipeline V2 Data Flow

```
chapter_worker.py
  → load previous chapter memo (from translation_chapter_memos)
  → fetch chapter body from book-service
  → detect JSON body → BLOCK pipeline (session_translator.py)
    → build_batch_plan() — CJK-aware tokens, expansion ratio, 40-block cap
    → fetch_translation_glossary() — GET glossary-service internal endpoint
    → build_glossary_context() — score by occurrence, JSONL, token budget
    → for each batch:
        → build system prompt + glossary block
        → invoke LLM (via provider-registry)
        → extract_token_counts() — multi-provider
        → parse [BLOCK N] markers
        → validate_translation_output() — count, indices, length
        → if invalid: retry with correction prompt (max 2)
        → auto_correct_glossary() — replace untranslated source terms
        → update rolling summary
    → reassemble blocks
  → persist to DB (chapter_translations)
  → save chapter memo (for next chapter)
  → emit events + notification
```

### Glossary Internal Endpoint

```
GET /internal/books/{book_id}/translation-glossary
  ?target_language=vi
  &chapter_id=... (optional)
  &max_entries=50

Auth: X-Internal-Token header

Response: [{"zh":["伊斯坦莎"],"vi":["Isutansha"],"kind":"character"}, ...]

Tiered query:
  Tier 1: chapter_entity_links (if chapter_id given)
  Tier 0: most-linked entities across book
  Tier 2: all active entities (fallback when no links exist)
```

---

## 5. Project Constants (unchanged)

```
frontend_port:   5173
gateway_port:    3123 (mapped from 3000)
glossary_port:   8211 (mapped from 8088)
translation_port: 8210 (mapped from 8087)
```

## 6. Test Glossary Data

12 glossary entries created for book `019d5e35-d5df-7e89-964d-8d6d838ce302`:

| ZH | VI | Kind |
|----|-----|------|
| 伊斯坦莎 | Isutansha | character |
| 提拉米 | Tirami | character |
| 索菲亞 | Sophia | character |
| 卡洛 | Carlo | character |
| 卡維佳 | Kavica | character |
| 庫蘭尼斯 | Kuranis | character |
| 西蒙 | Simon | character |
| 希娜 | Hina | character |
| 暗黑魔域 | Hắc Ám Ma Vực | location |
| 白銀騎士團 | Bạch Ngân Kỵ Sĩ Đoàn | organization |
| 光明聖教 | Giáo Hội Quang Minh | organization |
| 魔族 | Ma tộc | species |
