# Module 04 UX Wave: Translation & Chapter Viewer Redesign Plan

## Document Metadata
- Document ID: LW-72
- Version: 1.1.0
- Status: Approved
- Owner: Frontend Lead
- Last Updated: 2026-03-23
- Approved By: Decision Authority
- Approved Date: 2026-03-23
- Summary: Redesign the chapter translation viewer and the book translation dashboard to match professional TMS (Translation Management System) UX standards — introduces per-chapter version management, a chapter × language coverage matrix, and language dropdown (replacing tabs).

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.1.0 | 2026-03-23 | Approved; replaced language tabs with dropdown throughout (supports 140+ languages) | Decision Authority |
| 1.0.0 | 2026-03-23 | Initial draft | Assistant |

---

## 1. Problem Statement

The current M04 translation UI has three critical usability failures:

### 1.1 No Multi-Version Chapter Viewer
- A chapter can be translated multiple times (different models, prompts, languages), but there is **no UI to see, compare, or choose between versions**.
- Translation results are buried inside job accordions. To read a translation the user must: go to Translation tab → find the right job → expand it → find the chapter → expand the nested panel. That is 4 clicks into nested collapsibles to read one sentence.
- There is no concept of an "active" or "canonical" translation per language — all versions are equally invisible.

### 1.2 No Language-Aware Chapter Navigation
- In `BookDetailPage`, the chapter list shows only the original language. There is no indication of which languages a chapter has been translated into.
- There is no way to navigate to "read chapter 5 in Vietnamese" without digging through job history.

### 1.3 Translation Dashboard is a Form Dump
- `BookTranslationPage` stacks Settings → Chapter checkboxes → Job history vertically. The user must scroll past settings to reach the chapter list, and scroll further to see recent jobs.
- "Recent jobs" shows up to 5 jobs, but each job is a flat accordion — there is no cross-job view of which chapters are covered in which languages.
- No status matrix: the user cannot tell at a glance that "chapters 1–10 are done in Vietnamese but chapters 11–23 are not started in Japanese."

---

## 2. Design Principles (from TMS Research)

The redesign adopts patterns from Crowdin, Lokalise, and Phrase — the industry-standard tools for managing multi-language content:

1. **Three-level hierarchy**: Book → Chapter → Language×Version. Each level is navigable independently.
2. **Status vocabulary**: untranslated (gray) / in-progress (orange) / translated (blue) / active/confirmed (green) / failed (red). Consistent across all surfaces.
3. **Chapter list as a status map**: Each chapter row shows compact per-language status dots. The list is both navigation and progress overview.
4. **Floating action bar for bulk operations**: Selecting chapters reveals a sticky action bar with labeled buttons. Settings are not pre-requisite to seeing the chapter list.
5. **Version history is on-demand**: A slide-in panel, not always visible. Accessed per chapter per language.
6. **Language dropdown, not tabs**: A labeled `<select>` with search for all language switching. The system supports 140+ languages — tabs are unusable beyond 6. Never use flags; always use text labels (language name + code).

---

## 3. New Architecture Overview

### 3.1 New Page: `ChapterTranslationsPage`

**Route**: `/books/:bookId/chapters/:chapterId/translations`

Dedicated page for viewing, comparing, and managing all translation versions of a single chapter.

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back to Book    Chapter 05: The Iron Gate                    │
│                                                                  │
│  Language: [Vietnamese (vi) — 2 versions  ▾]  [+ Translate…]   │
├──────────────────┬──────────────────────────────────────────────┤
│  Versions        │  Version Content                             │
│  ──────────────  │  ─────────────────────────────────────────   │
│  v2  ● Active    │  [Compare with Original]  [Set Active] ▼    │
│  2026-03-23      │                                              │
│  gpt-4o          │  Cánh cửa sắt đứng sừng sững trước mặt     │
│                  │  hắn, không khác gì bức tường ngăn cách     │
│  v1              │  hai thế giới. Thứ ánh sáng lạnh lẽo từ     │
│  2026-03-15      │  ngọn đèn đường xuyên qua lớp rỉ sét,      │
│  claude-3-sonnet │  chiếu lên khuôn mặt tái nhợt của hắn.     │
│                  │                                              │
│  [Re-translate]  │  …                                           │
└──────────────────┴──────────────────────────────────────────────┘
```

**Language selector** — a labeled dropdown in the page header, not tabs:
- First option is always `Original (Japanese)` — shows the source body (from draft)
- Then one option per translated language, ordered by version count descending: `Vietnamese (vi) — 2 versions`, `Chinese Simplified (zh-Hans) — 1 version`
- Selected language is persisted in URL query param (`?lang=vi`) so the user can share or bookmark a specific language view
- `[+ Translate…]` button next to the dropdown opens the quick-translate drawer to add a new language or create a new version

**Why dropdown, not tabs**: The system supports 140+ languages. Tabs break at 4+ items and are completely unusable beyond 6. A labeled dropdown with search/filter scales to any number of languages, keeps the header compact, and is the standard pattern used by Lokalise, Crowdin, and Google Translate for large language inventories.

**Version list (left pane)**:
- Sorted newest → oldest
- Shows: version number (v1, v2…), "● Active" badge if canonical, creation date, model used
- Active version auto-selected on load; user can click any version to preview it

**Content pane (right pane)**:
- Read-only display of `translated_body` with `whitespace-pre-wrap`
- Token info: `in: 1,243 → out: 987 tokens` shown subtly above text
- Error state: if version has `status=failed`, shows red alert with `error_message`
- Loading state: skeleton while fetching

**Action bar (above content pane)**:
- **Set as Active**: designates this version as the canonical translation for this language (writes to `active_chapter_translation_versions` table)
- **Compare with Original**: toggles split-pane view — original text on left, translation on right, side by side
- **Re-translate**: opens mini drawer → choose model/language → triggers a new translation job for this single chapter (adds v3, v4, etc.)
- **Copy text**: copies `translated_body` to clipboard

**Compare mode**:
```
┌──────────────────────────┬──────────────────────────────────────┐
│  Original (Japanese)     │  Vietnamese v2  ● Active             │
│  ──────────────────────  │  ────────────────────────────────    │
│  鉄の扉は彼の前に…       │  Cánh cửa sắt đứng sừng sững…      │
└──────────────────────────┴──────────────────────────────────────┘
```

---

### 3.2 Redesigned Page: `BookTranslationPage`

**Route**: `/books/:bookId/translation` (existing, redesigned)

Split into two primary sections: **Translation Matrix** (always visible) and **Settings Drawer** (on demand).

```
┌─────────────────────────────────────────────────────────────────┐
│  Translation Dashboard — My Novel                               │
│  [⚙ Settings]  [📋 Jobs (3 active)]  [Filter language: All ▾]  │
├─────────────────────────────────────────────────────────────────┤
│  □  #  Title              vi        zh        ja       Actions  │
│  ──────────────────────────────────────────────────────────── │
│  ☑  1  Chapter 01         ●v2 ✓     ●v1 ✓     —        [⋯]    │
│  ☑  2  Chapter 02         ●v1 ✓     —         —        [⋯]    │
│  □  3  Chapter 03         ◌ running —         —        [⋯]    │
│  □  4  Chapter 04         —         —         —        [⋯]    │
│  □  5  Chapter 05         ✗ failed  —         —        [⋯]    │
│  …                                                              │
│  [Select all]  [Deselect all]  [Filter: All ▼]                 │
├─────────────────────────────────────────────────────────────────┤
│  FLOATING ACTION BAR (appears when chapters selected):          │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │
│  ▓  2 chapters selected   [Translate ▾]  [Clear selection]  ▓  │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │
└─────────────────────────────────────────────────────────────────┘
```

**Column headers** (language columns shown for each configured/available target language):
- `#` — sort_order
- `Title` — chapter title
- One column per target language used in any existing job for this book
- `Actions` — per-row kebab menu

**Status cell per (chapter, language)**:
| State | Display | Color |
|---|---|---|
| No translation | `—` | gray |
| In progress | `◌ running` | orange |
| Has translations, none active | `v1` | blue |
| Has active version | `●v1 ✓` | green |
| All failed | `✗` | red |
| Mixed (some versions failed, some ok) | `●v1 ⚠` | amber |

Clicking a status cell → navigates to `ChapterTranslationsPage` for that chapter filtered to that language.

**Floating action bar** (sticky, appears on chapter selection):
- Shows count: "2 chapters selected"
- Primary button: **[Translate ▾]** — opens translate modal
- Secondary: **[Clear selection]**
- On mobile: bar anchors to screen bottom

**Translate modal** (multi-step):
```
Step 1 of 3 — Target Languages
  ☑ Vietnamese (vi)
  ☑ Chinese Simplified (zh-Hans)
  □ Japanese (ja)
  □ Korean (ko)
  [Next →]

Step 2 of 3 — Model & Settings
  [Use book settings]  or  [Customize for this batch]
  Model: [platform_model: gpt-4o ▾]
  → [Advanced settings ▾]
  [← Back]  [Next →]

Step 3 of 3 — Review
  Translating 2 chapters × 2 languages = 4 translation tasks
  Model: gpt-4o (platform)
  Estimated cost: ~0.02 credits
  [← Back]  [Start Translation]
```

**Settings Drawer** (slides in from right on clicking ⚙ Settings):
- Contains the existing form: LanguagePicker, ModelSelector, PromptEditor, AdvancedTranslationSettings
- "Save as book defaults" button
- "Reset to my global defaults" button
- Closes when clicking outside or pressing Escape

**Jobs Panel** (slides in from right on clicking 📋 Jobs):
- Lists recent 10 jobs with status badges
- Each job row: date, language, N/M chapters, status badge
- Clicking a job → jumps to the relevant rows in the matrix and highlights them
- Cancel button for running jobs

---

### 3.3 Enhancement: `BookDetailPage` Chapter List

Add per-language status indicators to each chapter row.

**Before** (current):
```
Chapter 01  [ja]  · edit · download · trash
Chapter 02  [ja]  · edit · download · trash
```

**After**:
```
Chapter 01  [ja]  vi●  zh●  · edit · translations · download · trash
Chapter 02  [ja]  vi●  ──  · edit · translations · download · trash
Chapter 03  [ja]  ──   ──  · edit · translations · download · trash
```

- Language dots: `●` green (active translation exists), `○` blue (translated, no active set), `──` gray (no translation)
- Tooltip on hover: "Vietnamese: v2 active (2026-03-23)"
- "translations" action link → navigates to `ChapterTranslationsPage`

---

## 4. Backend API Changes Required

The redesign requires 4 new API endpoints and 2 DB schema additions.

### 4.1 DB Schema Additions

**Add `version_num` to `chapter_translations`**:
```sql
-- Computed on INSERT: COALESCE(MAX(version_num), 0) + 1 WHERE chapter_id=? AND target_language=?
ALTER TABLE chapter_translations
  ADD COLUMN version_num INT NOT NULL DEFAULT 1;

-- Unique constraint: one version number per (chapter, language) sequence
CREATE UNIQUE INDEX IF NOT EXISTS idx_ct_version
  ON chapter_translations(chapter_id, target_language, version_num);
```

**New table: `active_chapter_translation_versions`**:
```sql
CREATE TABLE IF NOT EXISTS active_chapter_translation_versions (
  chapter_id              UUID NOT NULL,
  target_language         TEXT NOT NULL,
  chapter_translation_id  UUID NOT NULL REFERENCES chapter_translations(id) ON DELETE CASCADE,
  set_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  set_by_user_id          UUID NOT NULL,
  PRIMARY KEY (chapter_id, target_language)
);
```

Auto-set active on first successful translation for a (chapter, language) pair (i.e., when `version_num = 1` completes).

### 4.2 New API Endpoints

**`GET /v1/translation/chapters/{chapter_id}/versions`**

Returns all translations grouped by language.

```json
{
  "chapter_id": "uuid",
  "languages": [
    {
      "target_language": "vi",
      "active_id": "uuid-of-v2",
      "versions": [
        {
          "id": "uuid",
          "version_num": 2,
          "job_id": "uuid",
          "status": "completed",
          "is_active": true,
          "model_source": "platform_model",
          "model_ref": "uuid",
          "input_tokens": 1243,
          "output_tokens": 987,
          "created_at": "2026-03-23T10:00:00Z"
        },
        {
          "id": "uuid",
          "version_num": 1,
          ...
          "is_active": false
        }
      ]
    }
  ]
}
```

Auth: user must own the book (validated via book-service internal endpoint).

**`GET /v1/translation/chapters/{chapter_id}/versions/{version_id}`**

Returns the full `ChapterTranslation` including `translated_body`.

**`PUT /v1/translation/chapters/{chapter_id}/versions/{version_id}/active`**

Sets this version as the active translation for its language. Upserts into `active_chapter_translation_versions`.

Body: `{}` (no body needed — version_id implies chapter_id + target_language)

Response: `{ "chapter_id": "...", "target_language": "vi", "active_id": "..." }`

**`GET /v1/translation/books/{book_id}/coverage`**

Returns a matrix of chapter × language coverage. Used by the translation dashboard to populate the status table.

Query params: `chapter_ids[]` (optional, for pagination)

```json
{
  "book_id": "uuid",
  "coverage": [
    {
      "chapter_id": "uuid",
      "languages": {
        "vi": {
          "has_active": true,
          "active_version_num": 2,
          "latest_status": "completed",
          "version_count": 2
        },
        "zh": {
          "has_active": true,
          "active_version_num": 1,
          "latest_status": "completed",
          "version_count": 1
        },
        "ja": null
      }
    }
  ],
  "known_languages": ["vi", "zh"]
}
```

`known_languages` is the set of all languages that appear in any completed/partial/running job for this book — used to generate table columns.

---

## 5. Frontend Component Map

### 5.1 New Components

| Component | Location | Purpose |
|---|---|---|
| `ChapterVersionsPage` | `pages/ChapterTranslationsPage.tsx` | Full page for managing chapter versions |
| `VersionSidebar` | `components/translation/VersionSidebar.tsx` | Left pane: version list per language |
| `TranslationViewer` | `components/translation/TranslationViewer.tsx` | Right pane: rendered translated_body + actions |
| `SplitCompareView` | `components/translation/SplitCompareView.tsx` | Side-by-side original vs. translation |
| `TranslationMatrix` | `components/translation/TranslationMatrix.tsx` | Chapter × language status table |
| `TranslationStatusCell` | `components/translation/TranslationStatusCell.tsx` | Single status cell with color/icon |
| `TranslateModal` | `components/translation/TranslateModal.tsx` | 3-step wizard for bulk translate |
| `SettingsDrawer` | `components/translation/SettingsDrawer.tsx` | Slide-in settings panel |
| `JobsDrawer` | `components/translation/JobsDrawer.tsx` | Slide-in job history panel |
| `LanguageStatusDots` | `components/translation/LanguageStatusDots.tsx` | Compact dots for chapter list rows |
| `FloatingActionBar` | `components/translation/FloatingActionBar.tsx` | Sticky bar on chapter selection |

### 5.2 Modified Components

| Component | Change |
|---|---|
| `BookTranslationPage.tsx` | Full redesign: matrix layout + drawers |
| `BookDetailPage.tsx` | Add `LanguageStatusDots` + "translations" link per chapter |
| `ChapterTranslationPanel.tsx` | Repurpose or deprecate (logic moves to `TranslationViewer`) |
| `TranslateButton.tsx` | Repurpose as the "Start Translation" button inside `TranslateModal` |
| `App.tsx` | Add route `/books/:bookId/chapters/:chapterId/translations` |

### 5.3 New Feature API File

**`frontend/src/features/translation/versionsApi.ts`**:

```typescript
// New functions:
listChapterVersions(token: string, chapterId: string): Promise<ChapterVersionsResponse>
getChapterVersion(token: string, chapterId: string, versionId: string): Promise<ChapterTranslation>
setActiveVersion(token: string, chapterId: string, versionId: string): Promise<ActiveVersionResponse>
getBookCoverage(token: string, bookId: string): Promise<BookCoverageResponse>
```

Types to add:
```typescript
type VersionSummary = {
  id: string;
  version_num: number;
  job_id: string;
  status: ChapterTranslationStatus;
  is_active: boolean;
  model_source: ModelSource;
  model_ref: string;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
};

type LanguageVersionGroup = {
  target_language: string;
  active_id: string | null;
  versions: VersionSummary[];
};

type ChapterVersionsResponse = {
  chapter_id: string;
  languages: LanguageVersionGroup[];
};

type CoverageCell = {
  has_active: boolean;
  active_version_num: number | null;
  latest_status: ChapterTranslationStatus | 'running' | null;
  version_count: number;
} | null;

type ChapterCoverage = {
  chapter_id: string;
  languages: Record<string, CoverageCell>;
};

type BookCoverageResponse = {
  book_id: string;
  coverage: ChapterCoverage[];
  known_languages: string[];
};
```

---

## 6. Status Vocabulary (Color System)

Consistent across all new components:

```typescript
// Reusable in TranslationStatusCell, LanguageStatusDots, VersionSidebar
const STATUS_COLORS = {
  none:       'text-muted-foreground',   // gray  — no translation
  running:    'text-amber-600',          // orange — in progress
  translated: 'text-blue-600',           // blue  — done, no active set
  active:     'text-green-600',          // green — done + active designated
  failed:     'text-red-600',            // red   — all versions failed
  partial:    'text-amber-600',          // amber — mixed ok/failed
};

const STATUS_ICONS = {
  none:       '—',
  running:    '◌',
  translated: '○',
  active:     '●',
  failed:     '✗',
  partial:    '⚠',
};
```

---

## 7. UX Flow Walkthroughs

### Flow A: "I want to read chapter 5 in Vietnamese"

**New flow** (4 steps → 2 steps):
1. Go to Book Detail → click "translations" link on Chapter 05 row
2. `ChapterTranslationsPage` loads → Vietnamese tab auto-selected → active version displayed

### Flow B: "Translate all untranslated chapters to Japanese"

**New flow**:
1. Go to Book Translation Dashboard
2. Click column header `ja` → "Filter: untranslated in Japanese" (or use filter dropdown)
3. Click checkbox in header → "Select all 15 untranslated"
4. Floating action bar appears: "15 chapters selected | [Translate ▾]"
5. Click Translate → Modal Step 1: Japanese pre-selected → Next
6. Step 2: model settings (or use defaults) → Next
7. Step 3: "15 chapters × 1 language = 15 tasks" → Start
8. Matrix updates live as chapters finish (via WebSocket)

### Flow C: "v1 was bad, re-translate chapter 12 with a better prompt"

**New flow**:
1. Chapter 12 row in matrix → Japanese cell shows `●v1 ✓` → click it
2. `ChapterTranslationsPage` opens on Japanese tab, v1 shown
3. Click "Re-translate" → mini drawer opens → adjust prompt → Translate
4. New `ja v2` appears in version list, marked "In progress"
5. WebSocket event fires → v2 updates to "completed"
6. Click v2 in sidebar → review text
7. Click "Set as Active" → v2 becomes `●v2 ✓`

---

## 8. Responsive Behavior

| Screen Width | Layout |
|---|---|
| ≥ 1280px (desktop) | Translation matrix full width + drawers overlay |
| 768–1279px (tablet) | Matrix horizontal scroll + drawers overlay |
| < 768px (mobile) | Matrix condensed (chapter title + 2 language cols) → tap cell for details page; drawers become bottom sheets |

For `ChapterTranslationsPage` on mobile:
- VersionSidebar and TranslationViewer become tabs (not side-by-side)
- Compare mode disabled on mobile (too narrow); replaced with toggle switch: "Show original / Show translation"

---

## 9. Implementation Sequence

### Phase 1 — Backend (1 session)

1. Add `version_num` column to `chapter_translations` via migration
2. Create `active_chapter_translation_versions` table
3. Update `translation_runner.py`: compute `version_num` on insert; auto-set active on first successful completion
4. Implement `GET /v1/translation/chapters/{chapter_id}/versions`
5. Implement `GET /v1/translation/chapters/{chapter_id}/versions/{version_id}`
6. Implement `PUT /v1/translation/chapters/{chapter_id}/versions/{version_id}/active`
7. Implement `GET /v1/translation/books/{book_id}/coverage`

### Phase 2 — Frontend: ChapterTranslationsPage (1 session)

8. Add types + API calls to `versionsApi.ts`
9. Build `VersionSidebar` component (language dropdown + version list)
10. Build `TranslationViewer` component (content + action buttons)
11. Build `SplitCompareView` (side-by-side, original from `booksApi.getDraft`)
12. Assemble `ChapterTranslationsPage` page
13. Add route in `App.tsx`
14. Add "translations" link + `LanguageStatusDots` to `BookDetailPage`

### Phase 3 — Frontend: Translation Dashboard Redesign (1 session)

15. Build `TranslationMatrix` (table with chapter × language coverage cells)
16. Build `TranslationStatusCell` (color + icon per cell state)
17. Build `FloatingActionBar` (sticky selection bar)
18. Build `TranslateModal` (3-step wizard — reuses ModelSelector, LanguagePicker, PromptEditor)
19. Build `SettingsDrawer` (slide-in, reuses existing settings form components)
20. Build `JobsDrawer` (slide-in, reuses job list rendering)
21. Rewrite `BookTranslationPage` using the new components
22. Wire WebSocket events → matrix live-update via coverage re-fetch or targeted cell update

---

## 10. Files to Create

| File | Purpose |
|---|---|
| `services/translation-service/app/routers/versions.py` | New endpoints: chapter versions + active setter |
| `services/translation-service/app/routers/coverage.py` | Book coverage matrix endpoint |
| `frontend/src/features/translation/versionsApi.ts` | API client for new endpoints |
| `frontend/src/components/translation/VersionSidebar.tsx` | Version list left pane |
| `frontend/src/components/translation/TranslationViewer.tsx` | Translation content right pane |
| `frontend/src/components/translation/SplitCompareView.tsx` | Side-by-side compare |
| `frontend/src/components/translation/TranslationMatrix.tsx` | Chapter × language table |
| `frontend/src/components/translation/TranslationStatusCell.tsx` | Status cell |
| `frontend/src/components/translation/FloatingActionBar.tsx` | Bulk action bar |
| `frontend/src/components/translation/TranslateModal.tsx` | 3-step translate wizard |
| `frontend/src/components/translation/SettingsDrawer.tsx` | Settings slide-in panel |
| `frontend/src/components/translation/JobsDrawer.tsx` | Job history slide-in panel |
| `frontend/src/components/translation/LanguageStatusDots.tsx` | Compact dots for chapter rows |
| `frontend/src/pages/ChapterTranslationsPage.tsx` | New chapter version viewer page |

## 11. Files to Modify

| File | Change |
|---|---|
| `services/translation-service/app/migrate.py` | Add version_num column + active_chapter_translation_versions table |
| `services/translation-service/app/workers/chapter_worker.py` | Compute version_num on insert; auto-set active for v1 |
| `services/translation-service/app/routers/jobs.py` | Include version info in existing endpoints |
| `services/translation-service/app/main.py` | Register new routers |
| `frontend/src/App.tsx` | Add ChapterTranslationsPage route |
| `frontend/src/pages/BookTranslationPage.tsx` | Full redesign using new components |
| `frontend/src/pages/BookDetailPage.tsx` | Add LanguageStatusDots + translations link per chapter |

---

## 12. Out of Scope (Future Modules)

The following are intentionally excluded from this redesign to keep scope manageable:

- **Write-back to book-service**: Making the "active" translation visible via the public reading API is a future module.
- **Segment-level translation**: Translating and managing individual paragraphs/sentences (CAT editor style). This plan works at chapter granularity.
- **Translation Memory (TM)**: Reusing previously translated segments. Out of scope for M04.
- **Collaborative review/approval workflow**: Multi-user review of translations.
- **Machine translation quality scoring (BLEU/METEOR)**: Automated quality metrics.

---

## 13. Acceptance Criteria

1. **ChapterTranslationsPage**: User can navigate to it from BookDetailPage, switch languages via the dropdown, switch between versions, read `translated_body`, set a version as active, and trigger a re-translate. All without touching job history.
2. **TranslationMatrix**: Shows all chapters × all known languages in a grid. Status cells use consistent color vocabulary. Clicking a cell navigates to ChapterTranslationsPage filtered to that language.
3. **Bulk translate flow**: User can select multiple chapters from the matrix, click Translate, complete the 3-step modal, and see live status updates in the matrix without page reload.
4. **Settings and Jobs are drawers**: Not inline sections. The chapter matrix is always visible without scrolling.
5. **BookDetailPage**: Chapter rows show compact language status dots. "translations" link visible per chapter.
6. **Version numbering**: Each (chapter, language) pair has sequential version numbers (v1, v2, v3). First successful translation is auto-set as active.
7. **No regression**: Existing translation job creation, WebSocket live-update, and settings save functionality continue to work.
