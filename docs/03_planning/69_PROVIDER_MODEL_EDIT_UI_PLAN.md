# Provider & Model Edit UI Plan

## Document Metadata
- Document ID: LW-69
- Version: 1.4.0
- Status: Approved
- Owner: Frontend Lead
- Last Updated: 2026-03-22
- Summary: Plan to add edit/delete UI for provider credentials and user models, plus a reusable TagEditor component to replace the raw text tag input.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.4.0 | 2026-03-22 | Add `context_length` as editable for ollama/lm_studio; replace drag-and-drop with auto-sort alphabetically in TagEditor | Assistant |
| 1.3.0 | 2026-03-22 | Replaced "Out of Scope" with proper §10 Backend Changes; itemized which endpoints already exist, what needs adding | Assistant |
| 1.2.0 | 2026-03-22 | Added `has_secret` field to ProviderCredential; refined secret field placeholder UX in edit form | Assistant |
| 1.1.0 | 2026-03-22 | Added TagEditor component spec; expanded tag UX to cover both add-model form and edit-model form | Assistant |
| 1.0.0 | 2026-03-22 | Initial draft | Assistant |

---

## 1. Current State

### Backend (already exists)
| Endpoint | Purpose |
|---|---|
| `PATCH /v1/model-registry/providers/{id}` | Edit provider: `display_name`, `secret`, `endpoint_base_url`, `active` |
| `DELETE /v1/model-registry/providers/{id}` | Delete provider credential |
| `PATCH /v1/model-registry/user-models/{id}` | Edit model: `alias`, `capability_flags` |
| `DELETE /v1/model-registry/user-models/{id}` | Delete user model |
| `PUT /v1/model-registry/user-models/{id}/tags` | Replace full tag list |

### Frontend gaps
- `aiModelsApi` has no `patchProvider`, `deleteProvider`, `patchUserModel`, or `deleteUserModel` functions
- `ProvidersSection` provider rows: only "Use this provider" button — **no Edit, no Delete**
- `ProvidersSection` model rows: Set active / Set inactive / Favorite / Verify — **no Edit, no Delete**
- Tags (add-model form): **raw text input** `"tag:note, tag2:note2"` — poor UX, error-prone
- Tags (model row display): comma-joined plain text — no way to edit individual tags

---

## 2. Goal

1. Add inline **Edit** + **Delete** for both provider credentials and user models
2. Replace the raw tag text input with a proper **`TagEditor`** component used in both the add-model form and the model edit form

---

## 3. Edit Scope per Entity

### 3.1 Provider credential edit
| Field | Input type | Notes |
|---|---|---|
| `display_name` | text input | required |
| `endpoint_base_url` | text input | optional; shown for all providers |
| `secret` | password input | optional; placeholder depends on `has_secret` (see §3.3) |
| `active` | checkbox | maps to status `active` ↔ `disabled` |

Not editable: `provider_kind` (immutable — delete + re-add).

### 3.3 Secret field placeholder logic

The backend must expose whether a secret is already stored — it must **never** send the actual secret value to the frontend.

**Backend change**: add `has_secret: bool` to `ProviderCredential` response.
- `has_secret = true` when `secret IS NOT NULL AND secret != ''` in DB
- `has_secret = false` otherwise

**Frontend edit form**:
| `has_secret` | Secret input initial value | Placeholder text |
|---|---|---|
| `true` | empty | `·········` (looks filled, signals "a secret is stored") |
| `false` | empty | `Enter API key / secret` |

In both cases the field is empty — the `·········` placeholder is just a visual cue rendered via `placeholder="·········"`, not actual value.

**Save logic**: if the user leaves the field empty → omit `secret` from PATCH body → backend keeps existing value. If the user types anything → send new value.

### 3.2 User model edit
| Field | Input type | Notes |
|---|---|---|
| `alias` | text input | optional |
| `context_length` | number input | editable for `ollama` / `lm_studio` only; hidden for `openai` / `anthropic` (managed by provider) |
| `capability_flags` | checkboxes | known flags: `chat`, `tool_calling`, `vision`, `thinking` |
| `tags` | `TagEditor` component | free-form `tag_name` + `note` pairs |

Not editable: `provider_model_name`, `provider_credential_id` (identity fields — delete + re-add).

---

## 4. TagEditor Component

### 4.1 Purpose

A reusable component that manages a `ModelTag[]` list with full add / edit / remove UX.
Replaces the current raw text input `"tag:note, tag2:note2"` in two places:
- **Add model form** (currently in `ProvidersSection`)
- **Model edit form** (new, in this plan)

### 4.2 Interface

```ts
// src/components/settings/TagEditor.tsx

type Props = {
  tags: ModelTag[];           // controlled value
  onChange: (tags: ModelTag[]) => void;
  disabled?: boolean;
};
```

### 4.3 Wireframe

```
Tags
┌──────────────────────────────────────────────┐
│  [thinking] [chain-of-thought] [×]           │  ← existing tag chip (tag_name + note)
│  [tts] [text to speech] [×]                  │
│  [chat] [×]                                  │
│                                              │
│  [+ Add tag]                                 │
└──────────────────────────────────────────────┘

  ↓ clicking a tag chip enters edit mode inline:
┌──────────────────────────────────────────────┐
│  Tag name: [thinking_______]                 │
│  Note:     [chain-of-thought__________]      │
│  [Save]  [Cancel]                            │
└──────────────────────────────────────────────┘

  ↓ clicking [+ Add tag]:
┌──────────────────────────────────────────────┐
│  Tag name: [_______________]  (required)     │
│  Note:     [_______________]  (optional)     │
│  [Add]  [Cancel]                             │
└──────────────────────────────────────────────┘
```

### 4.4 Behaviour rules

| Action | Result |
|---|---|
| Click **[+ Add tag]** | Show add mini-form below chips; hide if already open |
| Fill tag name + click **Add** | Append to list; **sort list alphabetically by `tag_name`**; call `onChange`; clear mini-form |
| Click a **chip** | Enter inline edit mode for that chip |
| Click **Save** (edit mode) | Update tag in list; **re-sort alphabetically by `tag_name`**; call `onChange`; exit edit mode |
| Click **[×]** on a chip | Remove tag from list; call `onChange` immediately (no re-sort needed) |
| Click **Cancel** | Dismiss add/edit form without change |
| Duplicate `tag_name` | Show inline validation error "Tag name already exists" |
| Empty `tag_name` | Add/Save button disabled |

### 4.5 Chip display

Each chip shows:
```
[tag_name]  [note — italic, muted]  [×]
```
If note is empty, only `[tag_name]` and `[×]` are shown.

### 4.6 Auto-sort

Tags are always kept sorted **alphabetically by `tag_name`** (case-insensitive). Sorting is applied after every Add or Save operation inside the component before calling `onChange`. This replaces drag-and-drop — the order is deterministic and consistent across load/save cycles.

---

## 5. UI Pattern — Inline Edit + Delete for Rows

### Provider row (before / after)

**Before (current):**
```
OpenAI Main (openai) | Status: active  [Use this provider]
```

**After:**
```
OpenAI Main (openai) | Status: active  [Use this provider]  [Edit]  [Delete]
  ↓ when Edit clicked
  ┌─────────────────────────────────┐
  │ Display name: [OpenAI Main___] │
  │ Endpoint URL: [______________] │
  │ Secret:       [··············] │  ← placeholder "·········" if has_secret=true, "Enter API key" if false; leave blank to keep current
  │ Active:       [✓]              │
  │        [Save]  [Cancel]        │
  └─────────────────────────────────┘
```

### Model row (before / after)

**Before (current):**
```
Fast - openai | Active: true | Favorite: false | Tags: thinking(chain-of-thought), tts(text to speech)
[Set inactive]  [Favorite]  [Verify]
```

**After:**
```
Fast - openai | Active: true | Favorite: false
[Set inactive]  [Favorite]  [Verify]  [Edit]  [Delete]
  ↓ when Edit clicked
  ┌──────────────────────────────────────────────────┐
  │ Alias:          [Fast__________]                │
  │ Context length: [4096__] (ollama/lm_studio only)│
  │ Flags:  [✓] chat  [✓] tool_calling  [ ] vision  │
  │         [ ] thinking                            │
  │ Tags:   <TagEditor — pre-filled with model tags>│
  │                    [Save]  [Cancel]             │
  └──────────────────────────────────────────────────┘
```

### Rules
- Only one row (provider OR model) in edit mode at a time — opening a new edit collapses any other
- Cancel restores original values without API call
- Save calls PATCH (+ PUT tags if changed) → refresh list → collapse
- Delete shows inline confirm `"Delete X? [Confirm] [Cancel]"` before calling DELETE
- Validation: provider `display_name` must not be empty; tag `tag_name` must not be empty or duplicate

---

## 6. API Client Changes (`frontend/src/features/ai-models/api.ts`)

Add four new functions:

```ts
patchProvider(token, providerId, payload: {
  display_name?: string;
  secret?: string;
  endpoint_base_url?: string;
  active?: boolean;
}) → Promise<ProviderCredential>

deleteProvider(token, providerId: string) → Promise<void>

patchUserModel(token, userModelId, payload: {
  alias?: string;
  context_length?: number | null;
  capability_flags?: Record<string, boolean>;
}) → Promise<UserModel>

deleteUserModel(token, userModelId: string) → Promise<void>
```

`putUserModelTags` already exists — no change needed.

---

## 7. Component Changes

### 7.1 New file: `src/components/settings/TagEditor.tsx`
Reusable controlled component per spec in §4.

### 7.2 `ProvidersSection.tsx` — state additions
```ts
// Provider edit/delete
editingProviderId: string | null
editProviderForm: { display_name: string; endpoint_base_url: string; secret: string; active: boolean }
providerEditError: string
deletingProviderId: string | null

// Model edit/delete
editingModelId: string | null
editModelForm: { alias: string; capability_flags: Record<string, boolean>; tags: ModelTag[] }
modelEditError: string
deletingModelId: string | null
```

### 7.3 `ProvidersSection.tsx` — add-model form
- Replace raw `tagsInput` string state + `parseTags()` with `<TagEditor>` component
- Remove `tagsInput` state; replace with `modelTags: ModelTag[]` state

### 7.4 Provider row actions
| Button | Action |
|---|---|
| **Edit** | Expand inline form pre-filled with current values; `secret` blank |
| **Delete** | Show inline confirm |
| Save | `patchProvider(...)` → refresh providers → collapse |
| Confirm delete | `deleteProvider(...)` → refresh; if deleted = selected → clear selection |
| Cancel | Collapse without change |

### 7.5 Model row actions
| Button | Action |
|---|---|
| **Edit** | Expand inline form; pre-fill alias, capability_flags, tags |
| **Delete** | Show inline confirm |
| Save | `patchUserModel(...)` then `putUserModelTags(...)` if tags changed → refresh → collapse |
| Confirm delete | `deleteUserModel(...)` → refresh |
| Cancel | Collapse without change |

---

## 8. Implementation Steps

**Backend first:**
1. Add `has_secret` to `listProviderCredentials`, `getProviderCredentialByID` in `server.go` (§10.1)

**Frontend:**
2. Add `has_secret?: boolean` to `ProviderCredential` type in `api.ts`
3. Add `patchProvider`, `deleteProvider`, `patchUserModel`, `deleteUserModel` to `aiModelsApi`
4. Create `src/components/settings/TagEditor.tsx`
5. Replace raw tag input in add-model form with `<TagEditor>`
6. Add edit/delete state to `ProvidersSection`
7. Add **Edit** + **Delete** + inline form to provider rows (use `has_secret` for secret placeholder)
8. Add **Edit** + **Delete** + inline form to model rows (using `<TagEditor>`)
9. Handle edge case: deleting selected provider → clear `selectedProviderCredentialId`

---

## 9. Backend Change: `has_secret` on ProviderCredential

The `GET /v1/model-registry/providers` response must include `has_secret: bool` per item.

**Go change** (`provider_credentials` query in `server.go`):
- Add computed field: `(secret IS NOT NULL AND secret <> '') AS has_secret` to the SELECT
- Add `HasSecret bool \`json:"has_secret"\`` to the Go response struct

This is a **non-breaking additive change** — existing clients that ignore the field are unaffected.

---

## 10. Backend Changes Required

All 4 CRUD endpoints already exist in `provider-registry-service`. The following backend changes are needed to support the new UI:

### 10.1 Add `has_secret` to ProviderCredential responses

Three query locations in `server.go` need updating:

| Function | Current SELECT | Change |
|---|---|---|
| `listProviderCredentials` | `provider_credential_id, provider_kind, display_name, endpoint_base_url, status, created_at, updated_at` | Add `(secret_ciphertext IS NOT NULL AND secret_ciphertext <> '') AS has_secret` |
| `getProviderCredentialByID` | same columns | same addition |
| PATCH response (same `getProviderCredentialByID`) | same | same |

For each location:
- Add `(secret_ciphertext IS NOT NULL AND secret_ciphertext <> '') AS has_secret` to SELECT
- Add `HasSecret bool \`json:"has_secret"\`` to the Go response struct
- Add `&item.HasSecret` (or `&out.HasSecret`) to the corresponding `.Scan(...)` call

**Frontend**: add `has_secret?: boolean` to `ProviderCredential` type in `api.ts`.

### 10.2 Add `context_length` to `patchUserModel`

`PATCH /v1/model-registry/user-models/{id}` currently accepts only `alias` and `capability_flags`. Need to add `context_length`.

**Go change** (`patchUserModel` in `server.go`):
- Add `ContextLength *int \`json:"context_length"\`` to the input struct
- Add `context_length = COALESCE($N, context_length)` to the UPDATE SET clause
- Pass `in.ContextLength` as the new parameter

**Frontend**: add `context_length?: number | null` to the `patchUserModel` payload type. The field is only shown in the edit form when `provider_kind` is `ollama` or `lm_studio`.

### 10.3 `capability_flags` type alignment

`patchUserModel` in Go accepts `map[string]any` for `capability_flags` — compatible with the frontend sending `Record<string, boolean>`. No backend change needed.

### 10.4 Summary — endpoint status

| Endpoint | Status | Change needed |
|---|---|---|
| `PATCH /v1/model-registry/providers/{id}` | exists | none |
| `DELETE /v1/model-registry/providers/{id}` | exists (soft-delete → `archived`) | none |
| `PATCH /v1/model-registry/user-models/{id}` | exists | add `context_length` field (§10.2) |
| `DELETE /v1/model-registry/user-models/{id}` | exists (hard delete) | none |
| `PUT /v1/model-registry/user-models/{id}/tags` | exists | none |
| `GET /v1/model-registry/providers` + responses | exists | add `has_secret` (§10.1) |

---

## 11. Not Editable / Out of Scope

- `provider_kind` is not editable (immutable — delete + re-add)
- `provider_model_name` is not editable (identity field — delete + re-add)
- Bulk edit / bulk delete not in scope
- Tag drag-and-drop reordering not in scope (replaced by auto-sort alphabetically, see §4.6)
