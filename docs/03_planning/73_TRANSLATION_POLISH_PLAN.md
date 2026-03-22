# LW-73 Translation Polish — Compact Prompts, Timestamps & Full Language List

## Document Metadata
- Document ID: LW-73
- Version: 1.0.0
- Status: Approved
- Owner: Full-Stack Lead
- Last Updated: 2026-03-23
- Approved By: Decision Authority
- Approved Date: 2026-03-23
- Summary: Three focused polish improvements — expose compact model prompts in the settings UI, add time (HH:MM) to all translation timestamps, and replace the 6-preset language picker with a full 580-entry BCP-47 searchable datalist.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.0.0 | 2026-03-23 | Initial draft; approved | Assistant |

---

## 1. Problem Statement

### 1.1 Compact Model Prompts Are Not User-Configurable

`session_translator.py` hardcodes `_DEFAULT_COMPACT_SYSTEM`. Users can already choose *which* model compacts the translation history (via `AdvancedTranslationSettings`), but they cannot control *what instructions the compact model receives*. Power users who want a domain-specific or language-specific compaction memo have no way to customise it.

### 1.2 Translation Timestamps Show Only Date

All timestamp displays in the translation UI use `toLocaleDateString()`, which hides the hour and minute. Jobs and versions created on the same date are indistinguishable by time. The underlying DB fields (`created_at`, `started_at`, `finished_at`) are `TIMESTAMPTZ` and include full precision — it just isn't displayed.

Affected:
- `JobsDrawer.tsx` line 56 — job `created_at`
- `VersionSidebar.tsx` line 18 — version `created_at` via `formatDate()`

### 1.3 Language Picker Has Only 6 Presets

`LanguagePicker.tsx` hardcodes 6 languages (`en`, `vi`, `ja`, `zh-Hans`, `zh-Hant`, `ko`). The system supports any BCP-47 code. `data/language_codes.txt` contains 580 entries. Users who want to translate to/from Arabic, Hindi, Thai, Ukrainian, etc. must type the code from memory with no autocomplete guidance. Similarly, `_LANG_NAMES` in `session_translator.py` covers only 45 codes.

---

## 2. Design Decisions

### 2.1 Compact Prompt Storage
- Store `compact_system_prompt TEXT NOT NULL DEFAULT ''` and `compact_user_prompt_tpl TEXT NOT NULL DEFAULT ''` in the three settings tables (`user_translation_preferences`, `book_translation_settings`, `translation_jobs`).
- Empty string = use built-in default. No NULL needed.
- The compact user prompt supports one variable: `{history_text}` — the serialised session transcript.
- Default compact user prompt is literally `{history_text}` — the full transcript is passed as-is when the user has not customised it.

### 2.2 Timestamp Format
- Use `toLocaleString(undefined, { year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })` for all translation date displays.
- No new utility file — update the two existing formatter calls in-place.

### 2.3 Language Picker Redesign
- Replace the `<select>` + `<input>` dual-control with a single `<input list="...">` + `<datalist>` containing all 580 BCP-47 entries.
- Import from a generated `frontend/src/data/languageCodes.ts` — not inlined in the component.
- Value stored is always the raw BCP-47 code typed by the user. Autocomplete options display `Name (code)`.
- Backend `_LANG_NAMES` dict expanded to cover all ~480 deduplicated codes (lowercase keys).

---

## 3. Backend Changes

### 3.1 `app/migrate.py` — V3 migration block

Append after the existing V2 block:

```sql
-- V3: compact model prompts
ALTER TABLE user_translation_preferences
  ADD COLUMN IF NOT EXISTS compact_system_prompt   TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS compact_user_prompt_tpl TEXT NOT NULL DEFAULT '';

ALTER TABLE book_translation_settings
  ADD COLUMN IF NOT EXISTS compact_system_prompt   TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS compact_user_prompt_tpl TEXT NOT NULL DEFAULT '';

ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS compact_system_prompt   TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS compact_user_prompt_tpl TEXT NOT NULL DEFAULT '';
```

### 3.2 `app/config.py` — move compact defaults here

```python
DEFAULT_COMPACT_SYSTEM_PROMPT = (
    "You are a translation assistant. Summarise the following translation session history "
    "into a concise Translation Memo (200 words max). Include: key character names and "
    "their translations, recurring terminology, tone/style notes. "
    "Output ONLY the memo, no other text."
)
DEFAULT_COMPACT_USER_PROMPT_TPL = "{history_text}"
```

### 3.3 `app/models.py` — new fields on preferences/settings/job models

Add to `UserTranslationPreferences`, `BookTranslationSettings`, and the job request/response model:

```python
compact_system_prompt:   str = ''
compact_user_prompt_tpl: str = ''
```

### 3.4 `app/routers/settings.py`

- `GET /v1/translation/preferences` — SELECT includes `compact_system_prompt`, `compact_user_prompt_tpl`; populate in response.
- `PUT /v1/translation/preferences` — UPSERT includes both new fields.
- `GET /v1/translation/books/{book_id}/settings` — same.
- `PUT /v1/translation/books/{book_id}/settings` — same.

### 3.5 `app/routers/jobs.py`

In the settings snapshot INSERT into `translation_jobs`, include:
```sql
compact_system_prompt   = $N,
compact_user_prompt_tpl = $N
```

### 3.6 `app/workers/session_translator.py` — use job prompts + expand `_LANG_NAMES`

**`_compact_history()`**: replace hardcoded `_DEFAULT_COMPACT_SYSTEM` with:

```python
from ..config import DEFAULT_COMPACT_SYSTEM_PROMPT, DEFAULT_COMPACT_USER_PROMPT_TPL

compact_system   = msg.get("compact_system_prompt")   or DEFAULT_COMPACT_SYSTEM_PROMPT
compact_user_tpl = msg.get("compact_user_prompt_tpl") or DEFAULT_COMPACT_USER_PROMPT_TPL
compact_user_msg = compact_user_tpl.format_map(_SafeFormatMap({"history_text": history_text}))

compact_payload = {
    ...,
    "input": {
        "messages": [
            {"role": "system", "content": compact_system},
            {"role": "user",   "content": compact_user_msg},
        ]
    },
}
```

Remove the module-level `_DEFAULT_COMPACT_SYSTEM` constant.

**`_LANG_NAMES`**: replace with the full ~480-entry dict generated from `data/language_codes.txt` (lowercase keys, deduplicated — first occurrence wins for duplicate codes).

---

## 4. Frontend Changes

### 4.1 `features/translation/api.ts`

Add to `UserTranslationPreferences`, `BookTranslationSettings`, `TranslationJob` types:

```typescript
compact_system_prompt:   string;
compact_user_prompt_tpl: string;
```

### 4.2 `components/translation/PromptEditor.tsx`

Add optional `hintOverride` prop so callers can substitute their own variable hint:

```typescript
type Props = {
  systemPrompt: string;
  userPromptTpl: string;
  onSystemPromptChange: (v: string) => void;
  onUserPromptTplChange: (v: string) => void;
  disabled?: boolean;
  hintOverride?: React.ReactNode;
};
```

When `hintOverride` is provided, render it instead of the default variables hint paragraph.

### 4.3 `components/translation/AdvancedTranslationSettings.tsx`

Add two fields to `AdvancedSettings`:

```typescript
export type AdvancedSettings = {
  compact_model_source:    ModelSource | null;
  compact_model_ref:       string | null;
  compact_system_prompt:   string;
  compact_user_prompt_tpl: string;
  chunk_size_tokens:       number;
  invoke_timeout_secs:     number;
};
```

Inside the "Context compaction model" `<fieldset>`, after the model selector, add a collapsible compact prompts section:

```tsx
<details className="rounded border mt-2">
  <summary className="cursor-pointer px-2 py-1 text-xs text-muted-foreground select-none">
    Compact model prompts (optional)
  </summary>
  <div className="pt-2">
    <PromptEditor
      systemPrompt={value.compact_system_prompt}
      userPromptTpl={value.compact_user_prompt_tpl}
      onSystemPromptChange={(v) => onChange({ ...value, compact_system_prompt: v })}
      onUserPromptTplChange={(v) => onChange({ ...value, compact_user_prompt_tpl: v })}
      disabled={disabled}
      hintOverride={
        <p className="text-xs text-muted-foreground">
          Variable: {'{history_text}'} (required in user prompt — the session transcript).
          Leave both blank to use built-in defaults.
        </p>
      }
    />
  </div>
</details>
```

### 4.4 Page components (SettingsDrawer, TranslationSettingsPage, BookTranslationPage)

Default `AdvancedSettings` value everywhere must include the two new fields initialised to `''`.
Load from API response, save on PUT — no structural changes otherwise.

### 4.5 Timestamp fix

**`components/translation/JobsDrawer.tsx`** line 56:
```tsx
// before
{new Date(job.created_at).toLocaleDateString()}
// after
{new Date(job.created_at).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
```

**`components/translation/VersionSidebar.tsx`** line 18 `formatDate()`:
```typescript
// before
return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
// after
return new Date(iso).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
```

### 4.6 `data/languageCodes.ts` (new generated file)

Full 580-entry BCP-47 list imported from `data/language_codes.txt`. Format:

```typescript
// Auto-generated from data/language_codes.txt — do not edit by hand.
export type LangEntry = { code: string; name: string };
export const LANGUAGE_CODES: LangEntry[] = [
  { code: 'aa', name: 'Afar' },
  ...
];
```

### 4.7 `components/books/LanguagePicker.tsx` (redesign)

Replace `<select>` + free-text `<input>` with a single `<input list>` + `<datalist>`:

```tsx
import { LANGUAGE_CODES } from '@/data/languageCodes';

export function LanguagePicker({ value, onChange, label = 'Language', required, placeholder = 'e.g. en, vi, zh-Hans' }: Props) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}{required ? ' *' : ''}</label>
      <input
        className="w-full rounded border px-2 py-2 text-sm"
        list="language-picker-list"
        placeholder={placeholder}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
      />
      <datalist id="language-picker-list">
        {LANGUAGE_CODES.map((entry) => (
          <option key={entry.code} value={entry.code}>{entry.name} ({entry.code})</option>
        ))}
      </datalist>
    </div>
  );
}
```

---

## 5. Implementation Sequence

1. `migrate.py` — V3 ALTER TABLE block (6 new columns)
2. `config.py` — add compact prompt defaults
3. `models.py` — add 2 fields
4. `routers/settings.py` — read/write new columns
5. `routers/jobs.py` — snapshot new columns
6. `session_translator.py` — use job's compact prompts + expand `_LANG_NAMES`
7. `frontend/src/data/languageCodes.ts` — generate from `language_codes.txt`
8. `LanguagePicker.tsx` — datalist redesign
9. `PromptEditor.tsx` — add `hintOverride` prop
10. `AdvancedTranslationSettings.tsx` — new fields + compact prompt section
11. `api.ts` — new TS fields
12. `SettingsDrawer.tsx`, `TranslationSettingsPage.tsx`, `BookTranslationPage.tsx` — init/load/save new fields
13. `JobsDrawer.tsx` + `VersionSidebar.tsx` — timestamp fix

---

## 6. Files to Modify

| File | Change |
|---|---|
| `services/translation-service/app/migrate.py` | Add V3 block — 6 new columns |
| `services/translation-service/app/config.py` | Add `DEFAULT_COMPACT_SYSTEM_PROMPT`, `DEFAULT_COMPACT_USER_PROMPT_TPL` |
| `services/translation-service/app/models.py` | Add 2 fields to preference/settings/job models |
| `services/translation-service/app/routers/settings.py` | Read/write 2 new columns |
| `services/translation-service/app/routers/jobs.py` | Snapshot 2 new columns into job row |
| `services/translation-service/app/workers/session_translator.py` | Use job's compact prompts; expand `_LANG_NAMES` |
| `frontend/src/features/translation/api.ts` | Add 2 new TS fields |
| `frontend/src/components/translation/PromptEditor.tsx` | Add `hintOverride` prop |
| `frontend/src/components/translation/AdvancedTranslationSettings.tsx` | New fields + compact prompt section |
| `frontend/src/components/books/LanguagePicker.tsx` | Datalist redesign |
| `frontend/src/components/translation/JobsDrawer.tsx` | Timestamp: add hour:minute |
| `frontend/src/components/translation/VersionSidebar.tsx` | `formatDate`: add hour:minute |
| `frontend/src/pages/TranslationSettingsPage.tsx` | Init/load/save new fields |
| `frontend/src/pages/BookTranslationPage.tsx` | Init/load/save new fields |

## 7. Files to Create

| File | Purpose |
|---|---|
| `frontend/src/data/languageCodes.ts` | Generated BCP-47 list (580 entries) |
| `scripts/gen_language_codes.py` | One-time generation script |
