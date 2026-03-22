# LoreWeave Module 04 Frontend Detailed Design

## Document Metadata

- Document ID: LW-M04-64
- Version: 0.1.0
- Status: Approved
- Owner: Frontend Lead
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Frontend architecture, component tree, state boundaries, and integration strategy for Module 04 raw translation pipeline.

## Change History

| Version | Date       | Change                              | Author    |
| ------- | ---------- | ----------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 frontend design   | Assistant |

## 1) New Routes

| Route | Page Component | Layout | Guard |
| --- | --- | --- | --- |
| `/translation/settings` | `TranslationSettingsPage` | `AppLayout` | `RequireAuth` |
| `/books/:bookId/translation` | `BookTranslationPage` | `AppLayout` | `RequireAuth` |

## 2) New Feature Module: `frontend/src/features/translation/`

### `api.ts` — Types and API Functions

**Types:**
```typescript
export type ModelSource = 'user_model' | 'platform_model';

export type UserTranslationPreferences = {
  user_id: string;
  target_language: string;
  model_source: ModelSource;
  model_ref: string | null;
  system_prompt: string;
  user_prompt_tpl: string;
  updated_at: string;
};

export type BookTranslationSettings = UserTranslationPreferences & {
  book_id: string;
  owner_user_id: string;
  is_default: boolean;
};

export type TranslationJobStatus =
  | 'pending' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';

export type ChapterTranslationStatus =
  | 'pending' | 'running' | 'completed' | 'failed';

export type ChapterTranslation = {
  id: string;
  job_id: string;
  chapter_id: string;
  status: ChapterTranslationStatus;
  translated_body: string | null;
  source_language: string | null;
  target_language: string;
  input_tokens: number | null;
  output_tokens: number | null;
  usage_log_id: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type TranslationJob = {
  job_id: string;
  book_id: string;
  owner_user_id: string;
  status: TranslationJobStatus;
  target_language: string;
  model_source: ModelSource;
  model_ref: string;
  total_chapters: number;
  completed_chapters: number;
  failed_chapters: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  chapter_translations?: ChapterTranslation[];
};
```

**API functions:**
```typescript
export const translationApi = {
  getPreferences(token: string): Promise<UserTranslationPreferences>,
  putPreferences(token: string, payload: PreferencesPayload): Promise<UserTranslationPreferences>,
  getBookSettings(token: string, bookId: string): Promise<BookTranslationSettings>,
  putBookSettings(token: string, bookId: string, payload: BookSettingsPayload): Promise<BookTranslationSettings>,
  createJob(token: string, bookId: string, payload: { chapter_ids: string[] }): Promise<TranslationJob>,
  cancelJob(token: string, jobId: string): Promise<void>,
  listJobs(token: string, bookId: string, params?: { limit?: number; offset?: number }): Promise<{ items: TranslationJob[]; total: number; limit: number; offset: number }>,
  getJob(token: string, jobId: string): Promise<TranslationJob>,
  getChapterTranslation(token: string, jobId: string, chapterId: string): Promise<ChapterTranslation>,
};
```

All functions use `apiJson<T>()` from `frontend/src/api.ts`.

## 3) New Components: `frontend/src/components/translation/`

### 3.1 `ModelSelector.tsx`

**Purpose:** Reusable dropdown combining user models and platform models.

**Props:**
```typescript
type Props = {
  token: string;
  value: { model_source: ModelSource; model_ref: string | null };
  onChange: (v: { model_source: ModelSource; model_ref: string }) => void;
  label?: string;
  disabled?: boolean;
};
```

**Implementation notes:**
- On mount, fetch `aiModelsApi.listUserModels(token)` and `aiModelsApi.listPlatformModels(token)` in parallel via `Promise.all`.
- Show `<Skeleton className="h-9 w-full" />` while loading.
- Render native `<select>` (no shadcn `Select` to keep simple):
  ```html
  <optgroup label="Your models">
    <option value="user_model:{uuid}">{alias || provider_model_name}</option>
  </optgroup>
  <optgroup label="Platform models">
    <option value="platform_model:{uuid}">{display_name}</option>
  </optgroup>
  ```
- Parse selected string on change: split on `":"` first occurrence.
- If both lists empty after load: show disabled placeholder `"No models — add one in AI Models"`.

### 3.2 `PromptEditor.tsx`

**Purpose:** Two-textarea editor for system prompt and user prompt template.

**Props:**
```typescript
type Props = {
  systemPrompt: string;
  userPromptTpl: string;
  onSystemPromptChange: (v: string) => void;
  onUserPromptTplChange: (v: string) => void;
  disabled?: boolean;
};
```

**Implementation notes:**
- Two labeled `<textarea>` elements, `rows={4}` and `rows={6}` respectively.
- Below user prompt textarea: `<p className="text-xs text-muted-foreground">Variables: {'{source_language}'}, {'{target_language}'}, {'{chapter_text}'}</p>`
- Wrap in parent `<div className="space-y-3">`.

### 3.3 `TranslateButton.tsx`

**Purpose:** Trigger translation job and display inline progress.

**Props:**
```typescript
type Props = {
  token: string;
  bookId: string;
  chapterIds: string[];
  onJobCreated?: (job: TranslationJob) => void;
};
```

**State machine:**
```typescript
type Phase = 'idle' | 'submitting' | 'polling' | 'done' | 'partial' | 'error';
```

**State transitions:**
- `idle` → `submitting` on button click
- `submitting` → `polling` on job creation success (stores `jobId`)
- `submitting` → `error` on API failure
- `polling` → `done` when `job.status === 'completed'`
- `polling` → `partial` when `job.status === 'partial'`
- `polling` → `error` when `job.status === 'failed'`
- `error` → `idle` on "Retry" click

**Polling:**
- `useEffect` sets up `setInterval(5000)` calling `translationApi.getJob(token, jobId)`.
- Returns `() => clearInterval(...)` for cleanup.
- Network error retries up to 3 times before transitioning to `error`.

**UI per state:**
- `idle`: `<Button>Translate</Button>`
- `submitting`: `<Button disabled><Spinner /> Translating…</Button>`
- `polling`: Progress bar + `"Translating… {completed}/{total} chapters"`
- `done`: Green status text `"✓ {completed} chapters translated"`
- `partial`: Amber text `"⚠ {completed}/{total} chapters translated ({failed} failed)"`
- `error`: Red alert + "Retry" button

### 3.4 `ChapterTranslationPanel.tsx`

**Purpose:** Display translated result for one chapter within a job.

**Props:**
```typescript
type Props = {
  token: string;
  jobId: string;
  chapterId: string;
  chapterTitle?: string;
};
```

**Implementation notes:**
- Calls `translationApi.getChapterTranslation(token, jobId, chapterId)` on mount.
- Loading: `<Skeleton className="h-24 w-full" />`
- `status === 'completed'`: display `translated_body` in `<div className="whitespace-pre-wrap text-sm rounded border p-3 bg-muted max-h-96 overflow-y-auto">`; token counts in small text below.
- `status === 'failed'`: `<Alert variant="destructive"><AlertDescription>{error_message}</AlertDescription></Alert>`
- `status === 'pending' | 'running'`: spinner + `"Processing…"`

## 4) New Pages

### 4.1 `TranslationSettingsPage.tsx`

**Route:** `/translation/settings`

**State:** `loading | idle | saving | error`

**On mount:** `GET /v1/translation/preferences` → populate form.

**Form fields** (react-hook-form + zod schema `translationPreferencesSchema`):
- `target_language`: string, required
- `model_source` + `model_ref`: resolved from `ModelSelector`
- `system_prompt`: string, min 1
- `user_prompt_tpl`: string, must include `{chapter_text}`

**Sections:**
1. `<section className="space-y-3 rounded border p-3">` — "Default translation settings" with all form fields + "Save defaults" button
2. `<section className="space-y-3 rounded border p-3">` — info card: "Per-book settings can be configured from within each book's Translation page."

### 4.2 `BookTranslationPage.tsx`

**Route:** `/books/:bookId/translation`

**State:** `loading | ready | saving | translating`

**On mount (parallel):**
1. `GET /v1/translation/books/:bookId/settings`
2. `GET /v1/books/:bookId/chapters?lifecycle_state=active&limit=100`
3. `GET /v1/translation/books/:bookId/jobs?limit=5`

**Section 1 — Settings:**
- Banner if `settings.is_default === true`: `<Alert>Using your default settings. Save below to override for this book.</Alert>`
- Same form fields as TranslationSettingsPage
- "Save for this book" → PUT book settings
- "Reset to my defaults" → GET preferences → populate form (does not auto-save)

**Section 2 — Translate:**
- Chapter list with checkboxes (`chapter.id`, `chapter.title || 'Chapter ' + chapter.sort_order`)
- "Select all" / "Deselect all" toggle buttons
- `<TranslateButton token={...} bookId={...} chapterIds={selectedIds} onJobCreated={handleJobCreated} />`
- Button disabled if no chapter selected or `effective settings.model_ref === null`

**Section 3 — Recent jobs:**
- Last 5 jobs from `listJobs(token, bookId, { limit: 5 })`
- Each job row: date, status badge, `completed/total chapters`, target language
- Expandable accordion (using HTML `<details>/<summary>`) → shows `<ChapterTranslationPanel>` for each chapter in `job.chapter_ids`
- On job created by TranslateButton (`onJobCreated`): prepend to jobs list and open its accordion

## 5) AppNav Change

File: `frontend/src/components/layout/AppNav.tsx`

Add after "Usage logs" link (inside authenticated block):
```tsx
<Link to="/translation/settings" className={linkClass}>
  Translation
</Link>
```

## 6) BookDetailPage Change

File: `frontend/src/pages/BookDetailPage.tsx` (around line 127)

Add after the "Sharing" link:
```tsx
<Link to={`/books/${bookId}/translation`} className="underline">
  Translation
</Link>
```

## 7) App.tsx Change

Add two routes inside the `<Route element={<AppLayout />}>` block:
```tsx
<Route
  path="/translation/settings"
  element={<RequireAuth><TranslationSettingsPage /></RequireAuth>}
/>
<Route
  path="/books/:bookId/translation"
  element={<RequireAuth><BookTranslationPage /></RequireAuth>}
/>
```

## 8) Reused Existing Code

| Existing asset | Used by |
| --- | --- |
| `LanguagePicker` (`components/books/LanguagePicker.tsx`) | `TranslationSettingsPage`, `BookTranslationPage` — target language field |
| `aiModelsApi.listUserModels()` + `listPlatformModels()` (`features/ai-models/api.ts`) | `ModelSelector` — populating model options |
| `apiJson<T>()` (`api.ts`) | `features/translation/api.ts` |
| `Skeleton` (`components/ui/skeleton.tsx`) | `ModelSelector`, `ChapterTranslationPanel` |
| `Alert` + `AlertDescription` (`components/ui/alert.tsx`) | `TranslateButton` (error state), `ChapterTranslationPanel` (failure) |
| `Button` (`components/ui/button.tsx`) | `TranslateButton`, form submit buttons |
| `useAuth` (`auth.tsx`) | All pages (get `accessToken`) |

## 9) Form Validation Schemas

New file: `frontend/src/features/translation/validation.ts`

```typescript
import * as z from 'zod';

export const translationSettingsSchema = z.object({
  target_language: z.string().min(1, 'Required'),
  model_source: z.enum(['user_model', 'platform_model']),
  model_ref: z.string().min(1, 'Select a model'),
  system_prompt: z.string().min(1, 'Required'),
  user_prompt_tpl: z
    .string()
    .min(1, 'Required')
    .refine(
      (v) => v.includes('{chapter_text}'),
      'Template must contain {chapter_text}'
    ),
});

export type TranslationSettingsFormValues = z.infer<typeof translationSettingsSchema>;
```
