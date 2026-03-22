# LoreWeave Module 04 Frontend Flow Specification

## Document Metadata

- Document ID: LW-M04-58
- Version: 0.1.0
- Status: Approved
- Owner: Product Manager + Frontend Lead
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Frontend user journeys, state model, page structure, and API mapping for Module 04 raw translation pipeline.

## Change History

| Version | Date       | Change                              | Author    |
| ------- | ---------- | ----------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 frontend flow spec | Assistant |

## 1) New Routes

| Route | Component | Access | Purpose |
| --- | --- | --- | --- |
| `/translation/settings` | `TranslationSettingsPage` | Protected (RequireAuth) | User-level default translation preferences |
| `/books/:bookId/translation` | `BookTranslationPage` | Protected (RequireAuth) | Per-book settings, chapter selection, translate trigger, results |

## 2) New Navigation

`AppNav.tsx` — add link after "Usage logs":
```
Translation  →  /translation/settings
```

`BookDetailPage.tsx` — add link alongside "Sharing":
```
Translation  →  /books/:bookId/translation
```

## 3) User Journey: Per-User Translation Settings (`/translation/settings`)

### Entry state
- User navigates to `/translation/settings`.
- Page calls `GET /v1/translation/preferences`.
- If no saved preferences: form shows platform defaults (default target language `vi`, no model selected, default prompts).
- If saved: form pre-fills with saved values.

### Form fields

| Field | Component | Validation |
| --- | --- | --- |
| Target language | `LanguagePicker` (reuse existing) | Required, BCP-47 |
| Model | `ModelSelector` (new, see §6) | Required to save |
| System prompt | `<textarea>` via `PromptEditor` | Required, non-empty |
| User prompt template | `<textarea>` via `PromptEditor` | Required, must contain `{chapter_text}` |

### Actions

- **Save defaults**: PUT `/v1/translation/preferences` → success toast → reload form.
- On save error: inline error message below form.

### State transitions

```
loading → idle (form ready)
idle → saving (submit)
saving → idle (success or error)
```

## 4) User Journey: Per-Book Translation (`/books/:bookId/translation`)

### 4.1 Entry state
- Page loads: calls in parallel:
  - `GET /v1/translation/books/:bookId/settings`
  - `GET /v1/books/:bookId/chapters?lifecycle_state=active&limit=100`
  - `GET /v1/translation/books/:bookId/jobs?limit=5`
- If `settings.is_default === true`: display banner "Using your default settings. Save to override for this book."

### 4.2 Section 1 — Translation settings for this book

Same form fields as user preferences page plus:
- **"Save for this book"** → PUT `/v1/translation/books/:bookId/settings` → success toast.
- **"Reset to my defaults"** → GET `/v1/translation/preferences` → populate form fields → user can then save.

### 4.3 Section 2 — Translate chapters

- **Chapter list**: checkboxes for each active chapter (title + sort_order).
  - "Select all" / "Deselect all" toggle.
  - Default: all chapters selected.
- **Translate button** → `TranslateButton` component.
  - Disabled if no model configured in effective settings.
  - On click: POST `/v1/translation/books/:bookId/jobs` with selected `chapter_ids`.
  - Transitions to polling state (see §6.3).

### 4.4 Section 3 — Recent translation jobs

- Shows last 5 jobs from `GET /v1/translation/books/:bookId/jobs?limit=5`.
- Each job row: status badge, created_at, `completed_chapters/total_chapters`, target language.
- Expandable accordion per job → shows `ChapterTranslationPanel` for each chapter in the job.
- Accordion collapsed by default; expands to show per-chapter results.

### State transitions (full page)

```
loading → ready (all three data sources loaded)
ready → ready (settings saved, no page reload needed)
ready → translating (job triggered, TranslateButton enters polling mode)
translating → ready (job terminal state reached)
```

## 5) Component: `ModelSelector`

**Location:** `frontend/src/components/translation/ModelSelector.tsx`

**Props:**
```typescript
{
  token: string
  value: { model_source: 'user_model' | 'platform_model'; model_ref: string | null }
  onChange: (v: { model_source: string; model_ref: string }) => void
  label?: string
  disabled?: boolean
}
```

**Behavior:**
- On mount: calls `aiModelsApi.listUserModels(token)` and `aiModelsApi.listPlatformModels(token)` in parallel.
- Renders `<select>` with two `<optgroup>`: "Your models" (active user models) and "Platform models" (active platform models).
- Option value format: `"user_model:uuid"` or `"platform_model:uuid"`.
- Parses selection to `{ model_source, model_ref }` on change.
- Shows `<Skeleton>` while loading.
- If both lists empty: shows disabled placeholder "No models available — configure in AI Models settings".

## 6) Component: `PromptEditor`

**Location:** `frontend/src/components/translation/PromptEditor.tsx`

**Props:**
```typescript
{
  systemPrompt: string
  userPromptTpl: string
  onSystemPromptChange: (v: string) => void
  onUserPromptTplChange: (v: string) => void
  disabled?: boolean
}
```

**Renders:**
- Labeled `<textarea>` for system prompt.
- Labeled `<textarea>` for user prompt template.
- Below user prompt textarea: hint text — `Variables: {source_language}, {target_language}, {chapter_text}`.
- `{chapter_text}` is required; if absent, parent form validation should reject.

## 7) Component: `TranslateButton`

**Location:** `frontend/src/components/translation/TranslateButton.tsx`

**Props:**
```typescript
{
  token: string
  bookId: string
  chapterIds: string[]        // non-empty
  onJobCreated?: (job: TranslationJob) => void
}
```

**State machine:**

| State | UI | Actions |
| --- | --- | --- |
| `idle` | "Translate" button (primary) | Click → `submitting` |
| `submitting` | Disabled button, spinner | POST job |
| `polling` | "Translating… N/M chapters" + progress bar | Poll GET job every 3 s |
| `done` | "Done — N chapters translated" (green) | — |
| `partial` | "Partial — N/M chapters translated" (amber) | — |
| `error` | Error message + "Retry" button | Click retry → `idle` |

**Polling behavior:**
- Poll `GET /v1/translation/jobs/:jobId` every 3 seconds.
- Stop polling when `status` is `completed`, `partial`, or `failed`.
- On network error: retry up to 3 times, then transition to `error` with message "Lost connection".
- Cleanup interval on component unmount.

## 8) Component: `ChapterTranslationPanel`

**Location:** `frontend/src/components/translation/ChapterTranslationPanel.tsx`

**Props:**
```typescript
{
  token: string
  jobId: string
  chapterId: string
  chapterTitle?: string
}
```

**Behavior:**
- Calls `GET /v1/translation/jobs/:jobId/chapters/:chapterId` on mount.
- Shows: status badge, `source_language → target_language`, token count (input + output).
- If `status === 'completed'`: scrollable `<pre>` or `<div>` with `translated_body`.
- If `status === 'failed'`: amber alert with `error_message`.
- If `status === 'pending' | 'running'`: skeleton / spinner.

## 9) Validation Rules

| Field | Rule |
| --- | --- |
| `target_language` | Required, non-empty string |
| `model_ref` | Required (non-null) to save preferences or book settings |
| `system_prompt` | Required, non-empty |
| `user_prompt_tpl` | Required, must contain substring `{chapter_text}` |
| `chapter_ids` (translate action) | At least 1 chapter selected |

## 10) Error State UX

| Scenario | UI response |
| --- | --- |
| GET preferences fails | Inline alert — "Failed to load settings. Retry." |
| PUT preferences fails | Inline error below form |
| `TRANSL_NO_MODEL_CONFIGURED` on job creation | Inline error — "No model configured. Go to Translation Settings to set a default model." with link |
| `TRANSL_BILLING_REJECTED` on job (chapter level) | Chapter shown as failed with message "Billing quota exhausted" |
| Provider invoke failure | Chapter shown as failed with message from `error_message` |

## 11) API Mapping Summary

| UI action | API call |
| --- | --- |
| Page load (`/translation/settings`) | `GET /v1/translation/preferences` |
| Save user preferences | `PUT /v1/translation/preferences` |
| Page load (`/books/:id/translation`) | `GET /v1/translation/books/:id/settings` + `GET /v1/books/:id/chapters` + `GET /v1/translation/books/:id/jobs?limit=5` |
| Save book settings | `PUT /v1/translation/books/:id/settings` |
| Reset to user defaults | `GET /v1/translation/preferences` → populate form |
| Load model selector options | `GET /v1/model-registry/user-models` + `GET /v1/model-registry/platform-models` |
| Trigger translation | `POST /v1/translation/books/:id/jobs` |
| Poll job status | `GET /v1/translation/jobs/:jobId` (every 3 s) |
| View chapter result | `GET /v1/translation/jobs/:jobId/chapters/:chapterId` |
