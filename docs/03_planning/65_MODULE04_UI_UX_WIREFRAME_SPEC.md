# LoreWeave Module 04 UI/UX Wireframe Specification

## Document Metadata

- Document ID: LW-M04-65
- Version: 0.1.0
- Status: Approved
- Owner: Product Manager + Frontend Lead
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Low-fidelity wireframe and UI state behavior specification for Module 04 translation settings and book translation pages.

## Change History

| Version | Date       | Change                             | Author    |
| ------- | ---------- | ---------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 wireframe spec   | Assistant |

## 1) `/translation/settings` — Translation Settings Page

### 1.1 Layout (full page)

```
┌─────────────────────────────────────────────────────┐
│ AppNav  [Books] [AI Models] [Platform models]        │
│         [Usage logs] [Translation]                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Translation Settings                               │
│                                                     │
│  ┌─ Default translation settings ─────────────────┐ │
│  │                                                 │ │
│  │  Default target language                        │ │
│  │  [LanguagePicker ▼]                             │ │
│  │                                                 │ │
│  │  Default model                                  │ │
│  │  [── Your models ──]                            │ │
│  │  [GPT-4o (openai) ▼]                            │ │
│  │                                                 │ │
│  │  System prompt                                  │ │
│  │  ┌────────────────────────────────────────────┐ │ │
│  │  │ You are a professional literary translator. │ │ │
│  │  │ Preserve the style, tone...                 │ │ │
│  │  └────────────────────────────────────────────┘ │ │
│  │                                                 │ │
│  │  User prompt template                           │ │
│  │  ┌────────────────────────────────────────────┐ │ │
│  │  │ Translate the following {source_language}   │ │ │
│  │  │ text into {target_language}...              │ │ │
│  │  │ {chapter_text}                              │ │ │
│  │  └────────────────────────────────────────────┘ │ │
│  │  Variables: {source_language}, {target_language},│ │
│  │  {chapter_text}                                 │ │
│  │                                                 │ │
│  │  [Save defaults]                                │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ Per-book settings ─────────────────────────────┐ │
│  │  Configure translation settings per book from   │ │
│  │  within each book's Translation page.           │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 1.2 States

| State | Visual |
| --- | --- |
| Loading | Skeleton lines in place of form fields |
| Idle | Form populated with saved or default values |
| Saving | "Save defaults" button disabled + spinner |
| Save success | Toast: "Defaults saved" |
| Save error | Inline alert below button: error message |
| No model selected (on save attempt) | Validation error under model selector |
| `{chapter_text}` missing in template | Validation error under user prompt textarea |

## 2) `/books/:bookId/translation` — Book Translation Page

### 2.1 Layout (full page)

```
┌─────────────────────────────────────────────────────┐
│ AppNav                                               │
├─────────────────────────────────────────────────────┤
│                                                     │
│  My Novel Title                                     │
│  [Sharing] [Translation*]                           │
│                                                     │
│  ┌─ Translation settings for this book ───────────┐ │
│  │  ⓘ Using your default settings. Save below to  │ │
│  │    override for this book.          [×]         │ │
│  │  (banner only shown when is_default=true)       │ │
│  │                                                 │ │
│  │  [same 4 form fields as settings page]          │ │
│  │                                                 │ │
│  │  [Save for this book]  [Reset to my defaults]   │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ Translate chapters ────────────────────────────┐ │
│  │                                                 │ │
│  │  [Select all] [Deselect all]                    │ │
│  │                                                 │ │
│  │  ☑ Chapter 1: The Beginning                    │ │
│  │  ☑ Chapter 2: The Journey                      │ │
│  │  ☑ Chapter 3: The End                          │ │
│  │                                                 │ │
│  │  ┌──────────────────────────────────────────┐  │ │
│  │  │                                          │  │ │
│  │  │  [Translate]  ← idle state              │  │ │
│  │  │  [◌ Translating...] ← submitting        │  │ │
│  │  │  Translating… 1/3 chapters [████░░░░]   │  │ │
│  │  │  ← polling state                         │  │ │
│  │  │  ✓ 3 chapters translated  ← done         │  │ │
│  │  │                                          │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─ Recent translation jobs ───────────────────────┐ │
│  │                                                 │ │
│  │  ▶ Mar 22 2026  ✓ completed  3/3 → Vietnamese  │ │
│  │    ▼ (expanded accordion)                       │ │
│  │    ┌─ Chapter 1: The Beginning ──────────────┐  │ │
│  │    │ ✓ completed · 245 → 198 tokens          │  │ │
│  │    │ ┌──────────────────────────────────────┐│  │ │
│  │    │ │ Phần mở đầu...                       ││  │ │
│  │    │ └──────────────────────────────────────┘│  │ │
│  │    └─────────────────────────────────────────┘  │ │
│  │    ┌─ Chapter 2: The Journey ────────────────┐  │ │
│  │    │ ✓ completed · 312 → 267 tokens          │  │ │
│  │    │ [translated text...]                     │  │ │
│  │    └─────────────────────────────────────────┘  │ │
│  │                                                 │ │
│  │  ▶ Mar 21 2026  ⚠ partial   2/3 → Vietnamese  │ │
│  │  ▶ Mar 20 2026  ✗ failed    0/2 → English     │ │
│  │                                                 │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 2.2 States

**Section 1 — Settings:**

| State | Visual |
| --- | --- |
| Loading | Skeleton in place of form |
| `is_default: true` | Blue info banner shown above form |
| `is_default: false` | No banner; form shows book-specific values |
| Saving | "Save for this book" disabled + spinner |
| Save success | Toast: "Book translation settings saved" |
| "Reset to my defaults" | Form fields repopulate from user preferences; banner not shown until save |

**Section 2 — Translate:**

| State | Visual |
| --- | --- |
| No chapters loaded | Skeleton list |
| Chapters loaded, none selected | "Translate" button disabled with tooltip "Select at least one chapter" |
| No model configured | "Translate" button disabled; inline warning "No model configured — go to Translation Settings" |
| Translating (polling) | Progress bar + "Translating… N/M chapters"; chapter list and settings form are not blocked |
| Job done | Success state in TranslateButton; new job appears in Section 3 automatically |

**Section 3 — Jobs:**

| State | Visual |
| --- | --- |
| Loading | Skeleton rows |
| No jobs | "No translation jobs yet. Click Translate above to get started." |
| Job `completed` | Green ✓ badge |
| Job `partial` | Amber ⚠ badge |
| Job `failed` | Red ✗ badge |
| Job `running` | Blue spinner badge |
| Accordion collapsed | Shows summary row only |
| Accordion expanded | Shows `ChapterTranslationPanel` for each chapter in the job |

## 3) `ModelSelector` Component States

| State | Visual |
| --- | --- |
| Loading | `<Skeleton className="h-9 w-full" />` |
| Loaded with models | `<select>` with `<optgroup>` sections |
| No models available | Disabled `<select>` with placeholder text |
| Selected | Shows model alias/name + provider |

## 4) `ChapterTranslationPanel` States

| State | Visual |
| --- | --- |
| Loading | `<Skeleton className="h-24 w-full" />` |
| `pending` | Spinner + "Waiting…" |
| `running` | Spinner + "Translating…" |
| `completed` | Scrollable text block with translation + token count footer |
| `failed` | Red alert with `error_message` |

## 5) Responsive Behavior

- Pages follow existing `AppLayout` constraints (`max-w-screen-2xl`, `px-4 py-6`, `sm:px-6 lg:px-8 xl:px-10`).
- Section cards stack vertically on all viewports (no side-by-side layout for M04).
- Chapter list in Section 2 uses vertical stack; no horizontal grid.
- Translated text panel in accordion uses `max-h-96 overflow-y-auto` to prevent excessive vertical height.

## 6) Accessibility Notes

- All form fields have `<label>` elements.
- Error messages are associated with their fields via `aria-describedby` (through `FormMessage` in RHF).
- `TranslateButton` polling state uses `aria-live="polite"` region for screen reader announcements.
- Accordion uses `<details>/<summary>` (native accessible disclosure).
