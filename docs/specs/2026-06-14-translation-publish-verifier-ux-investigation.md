# Investigation — Single-chapter translation: poor quality root cause + publish/verifier UX gaps

- **Date:** 2026-06-14
- **Branch:** feat/auto-draft-factory-gaps
- **Trigger:** User reported Vietnamese chapter translations are very poor ("sót tiếng Trung rất nhiều", names completely wrong) despite using a strong model (Gemma-4 26B). Suspected the glossary was not being applied.
- **Subject book:** `019eb60e-9f37-7198-b512-b526f1969ab9` (zh → vi)
- **Status:** Root cause confirmed with live DB evidence. Feeds the build below.

---

## TL;DR

1. **Glossary IS exploited correctly.** The translation pipeline fetches the scoped glossary (with target-language translations) and injects it into the LLM prompt; it also auto-corrects and (when a verifier is configured) hard-enforces verified names. Not the problem.
2. **The user was reading an OLD low-quality version.** Two translation runs exist on this book: a 06-11 run with `qwen2.5-7b-instruct` (7B, bad — 15–41% leftover Han, wrong names) and a 06-14 run with `google/gemma-4-26b-a4b-qat` (clean — 0% Han, correct names). Gemma translated well.
3. **Chapter 1 is stuck on the old Qwen version** because single-chapter re-translation does **not** auto-promote the new version to "active" (only campaign jobs do). The good Gemma re-translation (v4) was completed but never published.
4. **UX gaps confirmed:**
   - The "set active / publish version" UI exists but is an **orphaned route** — nothing in the workspace navigates to it.
   - The **verifier model selector is absent** from single-chapter translate (backend supports it; campaigns expose it). Every job ran with an empty `verifier_model_ref`, so the verify→correct loop never ran and `unresolved_high_count` is meaningless (a Qwen version full of Han still showed `unresolved_high_count = 0`).

---

## Evidence

### Glossary layer is healthy

- Book has 14 **active** glossary entities (11 character, 2 location, 1 item), 0 draft.
- 147 Vietnamese (`vi`) translations at confidence `machine`.
- The `translation-glossary` endpoint query returns all 14 entries WITH their `vi` translations, e.g. `张若尘→Trương Nhược Trần`, `池瑶→Trì Dao`, `侍女→Thị nữ`, `九天明帝经→Cửu Thiên Minh Đế Kinh`.
- Glossary usage was recorded for the book (63 rows in `chapter_translation_glossary_usage`).
- Pipeline code path confirmed correct:
  - Fetch: `services/translation-service/app/workers/session_translator.py:1064-1068`
  - Inject into prompt + "MUST use EXACT translations": `session_translator.py:1121-1126`
  - Build/score/auto-correct: `services/translation-service/app/workers/glossary_client.py:131-255`, `:431-462`
  - glossary-service query (filters `status='active'`): `services/glossary-service/internal/api/server.go:356-519`

> Note: extracted entities default to `status='draft'` (`services/glossary-service/internal/api/extraction_handler.go:893-894`) and the translation-glossary query only returns `status='active'`. For THIS book the entities were already active, so it wasn't the cause — but it is a latent trap for freshly-extracted books (drafts are invisible to translation until activated).

### Two translation runs, two models

`translation_jobs` for the book (vi):

| Created | Model (`model_ref`) | Pipeline | Verifier | Result |
|---|---|---|---|---|
| 06-11 12:23 | `qwen2.5-7b-instruct` (7B) | v3 | **empty** | bad |
| 06-11 19:05 / 19:20 | `qwen2.5-7b-instruct` | v2 | **empty** | bad |
| 06-14 09:27 | `google/gemma-4-26b-a4b-qat` | v2 | **empty** | clean |

Model refs resolved via `loreweave_provider_registry.user_models`:
- `019eb620-…` = `lm_studio` / `qwen2.5-7b-instruct` ("Qwen2.5 7B Instruct (fast, non-reasoning)")
- `019ebb72-…` = `lm_studio` / `google/gemma-4-26b-a4b-qat` ("Gemma-4 26B-A4B QAT (40K)")

### Quantified leftover Han in the translation output (content.text, not the `_text` source mirror)

| Chapter version | Model | leftover-Han % | tgt chars |
|---|---|---|---|
| 06-11 batch (7 versions) | Qwen 7B | 4.8% – 41.2% | 4.5k – 9.9k (≈ half length → incomplete) |
| 06-14 batch (5 versions) | Gemma 26B | 0.0% | 10.5k – 12.7k (complete) |

### Chapter-1 side-by-side (the chapter the user was reading)

- **ACTIVE (Qwen v2):** leftover Chinese mid-sentence (`…cũng đã tuyệt迹于人间，只留下一段段…`, `"吱呀！"`), wrong names **"Trần Rựu"** (should be Trương Nhược Trần / 张若尘) and **"Chí Yao"** (should be Trì Dao / 池瑶).
- **Gemma v4 (NOT active):** correct names (Trì Dao, Trương Nhược Trần), no leftover Han, fluent.

### Active-version pointer state (`active_chapter_translation_versions`)

5 unique chapters. Per-chapter active version + the gate field `unresolved_high_count`:

| chapter_id | v# (model, unresolved_high) → active |
|---|---|
| `019eb60f-3b81…` (ch 1) | v1 Qwen(62) f · **v2 Qwen(0) ACTIVE** · v3 Qwen(0) f · **v4 Gemma(0) NOT active** |
| `019eb60f-3bca…` | v1 Qwen(56) f · **v2 Gemma(0) ACTIVE** |
| `019eb60f-3bfe…` | v1 Qwen(52) f · **v2 Gemma(0) ACTIVE** |
| `019eb60f-3c30…` | v1 Qwen(55) f · **v2 Gemma(0) ACTIVE** |
| `019eb60f-3c68…` | v1 Qwen(46) f · **v2 Gemma(0) ACTIVE** |

### Why chapter 1 differs (mechanism, exact)

Promotion logic at `services/translation-service/app/workers/chapter_worker.py:360-379`:

```sql
INSERT INTO active_chapter_translation_versions (chapter_id, target_language, chapter_translation_id, set_by_user_id)
SELECT $1, ct.target_language, $2, ct.owner_user_id
FROM chapter_translations ct
WHERE ct.id = $2 AND COALESCE(ct.unresolved_high_count, 0) = 0
{ON CONFLICT (chapter_id, target_language) DO UPDATE ...   -- only when msg.campaign_id is set
 | ON CONFLICT (chapter_id, target_language) DO NOTHING}   -- non-campaign (single translate)
```

- Chapters 2–5: the 06-11 Qwen version had `unresolved_high_count` 52–56 → blocked by the `=0` gate → no active row existed. On 06-14 the clean Gemma version (0) was the first to pass → `INSERT` succeeded → Gemma active. ✓
- Chapter 1: on 06-11 a Qwen attempt (v2) happened to land `unresolved_high_count=0` → it became active. On 06-14 Gemma v4 (0) hit `ON CONFLICT DO NOTHING` → not promoted → chapter 1 stays Qwen. ✗

This matches the known issue class: *manual re-translation (even to a stronger model) does not update the active pointer when one already exists; only campaigns DO UPDATE.*

### Why `unresolved_high_count=0` is not trustworthy here

All jobs ran with `verifier_model_ref` empty → the verify→correct loop and quality scoring never ran (`quality_score=0` on all vi rows). So a Qwen version littered with Han + wrong names still recorded `unresolved_high_count=0`. The gate that guards active-promotion is therefore guarding on a meaningless number.

---

## UX gaps confirmed (frontend)

| Capability | State | Location |
|---|---|---|
| List versions | EXISTS | `frontend/src/features/translation/components/VersionSidebar.tsx`; page `frontend/src/pages/ChapterTranslationsPage.tsx` |
| Set active / publish (+ quality-gate confirm) | EXISTS but **UNREACHABLE** | button `frontend/src/features/translation/components/TranslationViewer.tsx:181-189`; API `frontend/src/features/translation/api.ts:141-149`; route `frontend/src/App.tsx:108` (`/books/:bookId/chapters/:chapterId/translations`) — **grep finds NO navigation to this route from the workspace** |
| Verifier model selector (single translate) | **ABSENT** | `frontend/src/pages/book-tabs/TranslateModal.tsx` sends only `chapter_ids`, `target_language`, `model_source`, `model_ref`. Backend supports `verifier_model_source/ref`, `max_qa_rounds`, `qa_depth` (`services/translation-service/app/models.py:96-169`, `app/routers/jobs.py:82-85,150,166`). Campaigns expose it (`frontend/src/features/campaigns/components/steps/ModelMatrixStep.tsx`). |

---

## Planned work (all approved by user 2026-06-14)

1. **Wire the version/publish route into the workspace.** Add a per-chapter "versions / publish" entry point in `TranslationTab` (and/or post-translate) navigating to `/books/:bookId/chapters/:chapterId/translations`. Closes "no place to publish".
2. **Add an optional verifier-model selector to `TranslateModal`** (reuse the campaign selector); send `verifier_model_source/ref` (+ optionally `max_qa_rounds`, `qa_depth`) in `createJob`.
3. **Auto-promote on a clean single re-translation.** Make the non-campaign path `DO UPDATE` under a safe condition (e.g. new version `unresolved_high_count=0` AND the existing active was not human-edited), so the user isn't forced to publish by hand. Guard against clobbering manually-edited active versions.
4. **Immediate data fix:** promote chapter 1's Gemma v4 to active:
   ```sql
   UPDATE active_chapter_translation_versions
   SET chapter_translation_id='019ec574-e9bc-7d81-8a21-621a038ee41c', set_at=now()
   WHERE chapter_id='019eb60f-3b81-730b-800b-5b52e8003a80' AND target_language='vi';
   ```

### Latent issues to consider during build
- Draft glossary entities are invisible to translation (`status='active'` filter) — freshly-extracted books will translate without glossary until entities are activated. Consider surfacing this (or including draft at low trust).
- The active-promotion gate relies on `unresolved_high_count`, which is 0 by default when no verifier runs. If (2) makes a verifier easy to pick but still optional, the gate remains weak for verifier-less jobs — factor this into (3)'s condition.
