# SS-3 — Glossary Settings + Auto-suggest Toast: Detailed Design

## Document Metadata

- Document ID: LW-M05-92
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + Tech Lead
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Parent Plan: [doc 89](89_MODULE05_SUPPLEMENT_DETAILED_DESIGN_PLAN.md) — SS-3 row
- Summary: Full spec for the Glossary user preferences endpoint (Feature E) and the auto-suggest chapter-link banner in `AttributeRow` (Feature A). Smallest sub-phase of M05-S1; zero DB migration risk; independent after SS-1.

## Change History

| Version | Date       | Change         | Author    |
| ------- | ---------- | -------------- | --------- |
| 0.1.0   | 2026-03-25 | Initial design | Assistant |

---

## 1) Scope

SS-3 delivers two features that share a single data dependency (user preferences):

| Feature | What it builds |
|---|---|
| **E — Glossary settings** | `glossary_user_preferences` DB table; `GET/PUT /v1/glossary/preferences` endpoint; new "Glossary" tab in user settings page |
| **A — Auto-suggest toast** | Inline chapter-link suggestion banner in `AttributeRow` expanded body; fires when an evidence references a chapter not yet linked to the entity; respects the user's `default_chapter_link_relevance` from Feature E |

**Not in SS-3:** Kind management UI, recycle bin (SS-2), T2/T3 kind tables (SS-4/SS-5).

---

## 2) Dependency on SS-1

SS-3 has **no functional dependency** on SS-1 (entity snapshots). The preferences endpoint and banner work independently of snapshot infrastructure. SS-3 can proceed immediately after SS-2, or in parallel with SS-4, as stated in the dependency graph in doc 89.

---

## 3) Backend — Feature E (Preferences Endpoint)

### 3.1 DB Migration

**File:** `services/glossary-service/internal/migrate/migrate.go`

Add as the last migration step (after existing DDL):

```sql
CREATE TABLE IF NOT EXISTS glossary_user_preferences (
  user_id                        UUID PRIMARY KEY,
  default_chapter_link_relevance TEXT NOT NULL DEFAULT 'mentioned'
    CONSTRAINT ck_gup_relevance
      CHECK (default_chapter_link_relevance IN ('major', 'appears', 'mentioned')),
  updated_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Notes:**
- Relevance values match the existing `chapter_entity_links` check constraint (`'major','appears','mentioned'`), NOT the requirement doc's preliminary list. The requirement doc used a draft set; this design aligns with production schema.
- No index needed — single-row-per-user table; lookup is always by PK.
- `updated_at` is set on upsert, not by trigger. The handler sets it manually.

### 3.2 Response Type (shared by GET and PUT)

```go
// in a new file: services/glossary-service/internal/api/preferences_handler.go

type glossaryPrefsResp struct {
    UserID                       string `json:"user_id"`
    DefaultChapterLinkRelevance  string `json:"default_chapter_link_relevance"`
    UpdatedAt                    string `json:"updated_at"`
}
```

### 3.3 GET /v1/glossary/preferences

**Handler:** `getGlossaryPreferences`

Logic:
1. Extract `userID` from JWT — `requireUserID`. Return 401 if missing/invalid.
2. Query `glossary_user_preferences WHERE user_id = $1`.
3. If `pgx.ErrNoRows`: return **defaults** (do NOT create row eagerly):
   ```json
   {
     "user_id": "<user_id>",
     "default_chapter_link_relevance": "mentioned",
     "updated_at": "<zero time or omit>"
   }
   ```
   Use `time.Time{}` for `updated_at` when no row exists, serialized as zero RFC3339.
4. If row found: return the row.

**Response:** 200 `glossaryPrefsResp`

**No-row default design rationale:** Avoids writing a row on every first GET. Row is created only on first PUT. Frontend GET always returns a valid object.

### 3.4 PUT /v1/glossary/preferences

**Handler:** `putGlossaryPreferences`

Logic:
1. Extract `userID` from JWT. Return 401 if absent.
2. Decode body:
   ```go
   var in struct {
       DefaultChapterLinkRelevance string `json:"default_chapter_link_relevance"`
   }
   ```
3. Validate `default_chapter_link_relevance` ∈ `{"major", "appears", "mentioned"}`. Return 422 `GLOSS_INVALID_BODY` if invalid or empty.
4. Upsert:
   ```sql
   INSERT INTO glossary_user_preferences (user_id, default_chapter_link_relevance, updated_at)
   VALUES ($1, $2, now())
   ON CONFLICT (user_id) DO UPDATE
     SET default_chapter_link_relevance = EXCLUDED.default_chapter_link_relevance,
         updated_at = now()
   RETURNING user_id, default_chapter_link_relevance, updated_at
   ```
5. Return 200 with the upserted `glossaryPrefsResp`.

### 3.5 Route Registration

**File:** `services/glossary-service/internal/api/server.go`

Add inside the `r.Route("/v1/glossary", ...)` block, **before** the book routes:

```go
// Preferences (user-scoped, no book path)
r.Get("/preferences", s.getGlossaryPreferences)
r.Put("/preferences", s.putGlossaryPreferences)
```

**Full updated route block:**

```go
r.Route("/v1/glossary", func(r chi.Router) {
    r.Get("/kinds", s.listKinds)

    // ── User-scoped preferences ──────────────────────────────────────────
    r.Get("/preferences", s.getGlossaryPreferences)
    r.Put("/preferences", s.putGlossaryPreferences)

    r.Route("/books/{book_id}", func(r chi.Router) {
        // ... existing routes unchanged ...
    })
})
```

### 3.6 Full Handler File

**New file:** `services/glossary-service/internal/api/preferences_handler.go`

```go
package api

import (
    "encoding/json"
    "net/http"
    "time"

    "github.com/jackc/pgx/v5"
)

var validRelevances = map[string]bool{
    "major":     true,
    "appears":   true,
    "mentioned": true,
}

type glossaryPrefsResp struct {
    UserID                      string `json:"user_id"`
    DefaultChapterLinkRelevance string `json:"default_chapter_link_relevance"`
    UpdatedAt                   string `json:"updated_at"`
}

func (s *Server) getGlossaryPreferences(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }

    var resp glossaryPrefsResp
    err := s.pool.QueryRow(r.Context(),
        `SELECT user_id, default_chapter_link_relevance, updated_at
         FROM glossary_user_preferences
         WHERE user_id = $1`,
        userID,
    ).Scan(&resp.UserID, &resp.DefaultChapterLinkRelevance, &resp.UpdatedAt)

    if err == pgx.ErrNoRows {
        // Return defaults without persisting a row
        writeJSON(w, http.StatusOK, glossaryPrefsResp{
            UserID:                      userID.String(),
            DefaultChapterLinkRelevance: "mentioned",
            UpdatedAt:                   time.Time{}.Format(time.RFC3339),
        })
        return
    }
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
        return
    }
    writeJSON(w, http.StatusOK, resp)
}

func (s *Server) putGlossaryPreferences(w http.ResponseWriter, r *http.Request) {
    userID, ok := s.requireUserID(r)
    if !ok {
        writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
        return
    }

    var in struct {
        DefaultChapterLinkRelevance string `json:"default_chapter_link_relevance"`
    }
    if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
        writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
        return
    }
    if !validRelevances[in.DefaultChapterLinkRelevance] {
        writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
            "default_chapter_link_relevance must be major, appears, or mentioned")
        return
    }

    var resp glossaryPrefsResp
    err := s.pool.QueryRow(r.Context(), `
        INSERT INTO glossary_user_preferences (user_id, default_chapter_link_relevance, updated_at)
        VALUES ($1, $2, now())
        ON CONFLICT (user_id) DO UPDATE
          SET default_chapter_link_relevance = EXCLUDED.default_chapter_link_relevance,
              updated_at = now()
        RETURNING user_id, default_chapter_link_relevance, updated_at`,
        userID, in.DefaultChapterLinkRelevance,
    ).Scan(&resp.UserID, &resp.DefaultChapterLinkRelevance, &resp.UpdatedAt)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "upsert failed")
        return
    }
    writeJSON(w, http.StatusOK, resp)
}
```

### 3.7 Backend Tests

**File:** `services/glossary-service/internal/api/server_test.go` (append to existing test file)

Test cases:

| # | Scenario | Expected |
|---|---|---|
| T1 | `GET /v1/glossary/preferences` — new user (no row) | 200 with `default_chapter_link_relevance: "mentioned"` |
| T2 | `PUT /v1/glossary/preferences` `{default_chapter_link_relevance: "major"}` | 200 with `default_chapter_link_relevance: "major"` |
| T3 | `GET /v1/glossary/preferences` after T2 | 200 with `default_chapter_link_relevance: "major"` |
| T4 | `PUT` with `default_chapter_link_relevance: "pivotal"` (invalid) | 422 `GLOSS_INVALID_BODY` |
| T5 | `PUT` with `default_chapter_link_relevance: ""` | 422 `GLOSS_INVALID_BODY` |
| T6 | `GET /v1/glossary/preferences` without Bearer token | 401 `GLOSS_UNAUTHORIZED` |
| T7 | `PUT /v1/glossary/preferences` without Bearer token | 401 `GLOSS_UNAUTHORIZED` |
| T8 | Upsert idempotency: `PUT major` then `PUT appears` then `GET` | 200 `appears` |

---

## 4) Frontend — Feature E (Settings UI)

### 4.1 API Client Addition

**File:** `frontend/src/features/glossary/api.ts`

Add to the `glossaryApi` object:

```typescript
// ── Preferences (SS-3) ──────────────────────────────────────────────────────

/** GET /v1/glossary/preferences */
getPreferences(token: string): Promise<GlossaryUserPreferences> {
  return apiJson<GlossaryUserPreferences>(`${BASE}/preferences`, { token });
},

/** PUT /v1/glossary/preferences */
putPreferences(
  token: string,
  body: { default_chapter_link_relevance: Relevance },
): Promise<GlossaryUserPreferences> {
  return apiJson<GlossaryUserPreferences>(`${BASE}/preferences`, {
    method: 'PUT',
    body: JSON.stringify(body),
    token,
  });
},
```

Add the `GlossaryUserPreferences` type to `frontend/src/features/glossary/types.ts`:

```typescript
export type GlossaryUserPreferences = {
  user_id: string;
  default_chapter_link_relevance: Relevance;
  updated_at: string;
};
```

### 4.2 GlossarySection Settings Component

**New file:** `frontend/src/components/settings/GlossarySection.tsx`

This component follows the exact same pattern as `TranslationSection.tsx`:
- Loads preferences on mount
- Shows a loading skeleton while fetching
- Has a single controlled `<select>` field
- Save button with inline success/error feedback

```tsx
import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { glossaryApi } from '@/features/glossary/api';
import type { Relevance } from '@/features/glossary/types';

const RELEVANCE_OPTIONS: { value: Relevance; label: string }[] = [
  { value: 'major',     label: 'Major — key plot role' },
  { value: 'appears',   label: 'Appears — present in chapter' },
  { value: 'mentioned', label: 'Mentioned — referenced but not present' },
];

export function GlossarySection() {
  const { accessToken } = useAuth();
  const token = accessToken!;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [relevance, setRelevance] = useState<Relevance>('mentioned');
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    glossaryApi.getPreferences(token)
      .then((p) => setRelevance(p.default_chapter_link_relevance))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSave() {
    setSaving(true);
    setErrorMsg('');
    setSuccessMsg('');
    try {
      await glossaryApi.putPreferences(token, {
        default_chapter_link_relevance: relevance,
      });
      setSuccessMsg('Preferences saved');
    } catch (e: unknown) {
      setErrorMsg((e as { message?: string })?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Glossary</h2>
        <p className="text-sm text-muted-foreground">
          Preferences for the glossary and lore management features.
        </p>
      </div>

      <section className="space-y-4 rounded border p-4">
        <h3 className="font-medium">Chapter link defaults</h3>

        {loading && <Skeleton className="h-9 w-full" />}

        {!loading && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">
                Default chapter-link relevance
              </label>
              <p className="mb-2 text-xs text-muted-foreground">
                Used when the auto-suggest banner links a chapter to an entity.
              </p>
              <select
                value={relevance}
                onChange={(e) => setRelevance(e.target.value as Relevance)}
                disabled={saving}
                className="rounded border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
              >
                {RELEVANCE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {errorMsg && (
              <Alert variant="destructive">
                <AlertDescription>{errorMsg}</AlertDescription>
              </Alert>
            )}
            {successMsg && (
              <p className="text-sm text-green-600">{successMsg}</p>
            )}

            <Button onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save preferences'}
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
```

### 4.3 UserSettingsPage Changes

**File:** `frontend/src/pages/UserSettingsPage.tsx`

Two changes:

1. Add `'glossary'` tab:

```typescript
// Change type and tabs array:
type Tab = 'account' | 'providers' | 'translation' | 'glossary';

const tabs: { id: Tab; label: string }[] = [
  { id: 'account',     label: 'Account' },
  { id: 'providers',   label: 'Model providers' },
  { id: 'translation', label: 'Translation' },
  { id: 'glossary',    label: 'Glossary' },        // ← NEW
];
```

2. Import and render `GlossarySection`:

```typescript
import { GlossarySection } from '@/components/settings/GlossarySection';

// In JSX:
{activeTab === 'glossary' && <GlossarySection />}
```

**Full updated file:**

```tsx
import { Navigate, useParams, Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { AccountSection } from '@/components/settings/AccountSection';
import { ProvidersSection } from '@/components/settings/ProvidersSection';
import { TranslationSection } from '@/components/settings/TranslationSection';
import { GlossarySection } from '@/components/settings/GlossarySection';

type Tab = 'account' | 'providers' | 'translation' | 'glossary';

const tabs: { id: Tab; label: string }[] = [
  { id: 'account',     label: 'Account' },
  { id: 'providers',   label: 'Model providers' },
  { id: 'translation', label: 'Translation' },
  { id: 'glossary',    label: 'Glossary' },
];

export function UserSettingsPage() {
  const { tab } = useParams<{ tab: string }>();

  if (!tab || !tabs.some((t) => t.id === tab)) {
    return <Navigate to="/settings/account" replace />;
  }

  const activeTab = tab as Tab;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <nav className="flex gap-1 border-b">
        {tabs.map((t) => (
          <Link
            key={t.id}
            to={`/settings/${t.id}`}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === t.id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </Link>
        ))}
      </nav>

      <div>
        {activeTab === 'account'     && <AccountSection />}
        {activeTab === 'providers'   && <ProvidersSection />}
        {activeTab === 'translation' && <TranslationSection />}
        {activeTab === 'glossary'    && <GlossarySection />}
      </div>
    </div>
  );
}
```

---

## 5) Backend — Feature A (No Backend Changes)

The auto-suggest banner is **purely frontend**. It uses the existing `POST /v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links` endpoint (SP-3, already implemented). No new backend endpoint is needed for Feature A.

---

## 6) Frontend — Feature A (Auto-suggest Banner)

### 6.1 Design Decisions

**Where the banner lives:** Inside `AttributeRow` expanded body, after the evidences section. This is the closest proximity to the evidence that triggered the suggestion, matching the UX intent from doc 88.

**Detection logic:** For each `AttributeRow`, scan `av.evidences` to find any evidence where:
1. `evidence.chapter_id !== null`
2. That `chapter_id` is **not** in the entity's existing chapter links

When multiple such evidences exist, suggest only the most recent one (last in the array — the API returns evidences in `created_at` ascending order, so the last element is newest).

**Dismiss persistence:** Session-only. Local state `Set<string>` keyed by `chapter_id`. If the user navigates away and comes back, the banner reappears (acceptable for MVP). Persisted dismiss is deferred to future polish.

**Data flow:**
```
GlossaryPage
  └── EntityDetailPanel  [loads entity.chapter_links, fetches preferences once]
        ├── defaultChapterLinkRelevance: Relevance  (from useGlossaryPreferences)
        └── entityChapterIds: string[]              (from entity.chapter_links)
              └── AttributeRow  [per attribute]
                    ├── existingChapterIds: string[]
                    ├── defaultRelevance: Relevance
                    └── ChapterSuggestBanner  [if applicable]
```

**Why preferences are fetched at `EntityDetailPanel` level (not in `AttributeRow`):**
- Avoids N concurrent preference fetches (one per expanded attribute row).
- `EntityDetailPanel` mounts once per entity selection; the single fetch is cached in component state.
- Preferences are user-level, not per-attribute — no reason to re-fetch per row.

### 6.2 useGlossaryPreferences Hook

**New file:** `frontend/src/features/glossary/hooks/useGlossaryPreferences.ts`

```typescript
import { useEffect, useState } from 'react';
import { glossaryApi } from '../api';
import type { GlossaryUserPreferences, Relevance } from '../types';

const DEFAULT_RELEVANCE: Relevance = 'mentioned';

export function useGlossaryPreferences(token: string): Relevance {
  const [relevance, setRelevance] = useState<Relevance>(DEFAULT_RELEVANCE);

  useEffect(() => {
    glossaryApi
      .getPreferences(token)
      .then((p) => setRelevance(p.default_chapter_link_relevance))
      .catch(() => {
        // Silently fall back to default on error — preferences are non-critical
      });
  }, [token]);

  return relevance;
}
```

**Notes:**
- Returns `Relevance` directly (not `{ relevance, loading }`) because the banner uses a default while loading, and preference loading failure is non-fatal.
- The hook uses the **default** value immediately so the banner is functional even before the preference fetch resolves.

### 6.3 EntityDetailPanel Changes

**File:** `frontend/src/features/glossary/components/EntityDetailPanel.tsx`

Two additions:

1. Import and call the hook:
```typescript
import { useGlossaryPreferences } from '../hooks/useGlossaryPreferences';

// Inside the component:
const defaultChapterLinkRelevance = useGlossaryPreferences(token);
```

2. Derive `entityChapterIds` from the entity and pass both to `AttributeRow`:
```typescript
const entityChapterIds = entity?.chapter_links.map((cl) => cl.chapter_id) ?? [];

// In JSX, update each AttributeRow:
<AttributeRow
  key={av.attr_value_id}
  av={av}
  bookId={bookId}
  entityId={entity.entity_id}
  token={token}
  onRefresh={onRefresh}
  existingChapterIds={entityChapterIds}          // ← NEW
  defaultRelevance={defaultChapterLinkRelevance}  // ← NEW
/>
```

**Change is additive** — no other part of `EntityDetailPanel` needs modification.

### 6.4 AttributeRow Changes

**File:** `frontend/src/features/glossary/components/AttributeRow.tsx`

#### 6.4.1 Updated Props Type

```typescript
type Props = {
  av: AttributeValue;
  bookId: string;
  entityId: string;
  token: string;
  onRefresh: () => void;
  existingChapterIds: string[];  // ← NEW: chapter IDs already linked to entity
  defaultRelevance: Relevance;   // ← NEW: from user preferences
};
```

#### 6.4.2 Dismiss State

Add to component body (after existing useState declarations):

```typescript
const [dismissedChapterIds, setDismissedChapterIds] = useState<Set<string>>(
  () => new Set(),
);
```

#### 6.4.3 Derived suggestedChapter

Add derived computation (pure, no state needed):

```typescript
// Find the most-recent evidence that references a chapter not yet linked to entity.
// av.evidences is ordered created_at ASC; iterate reversed to get newest first.
const suggestedChapter = (() => {
  if (!isExpanded) return null;
  for (let i = av.evidences.length - 1; i >= 0; i--) {
    const ev = av.evidences[i];
    if (
      ev.chapter_id &&
      !existingChapterIds.includes(ev.chapter_id) &&
      !dismissedChapterIds.has(ev.chapter_id)
    ) {
      return { chapterId: ev.chapter_id, chapterTitle: ev.chapter_title };
    }
  }
  return null;
})();
```

**Notes:**
- Only computed when `isExpanded` to avoid unnecessary work.
- `existingChapterIds` is derived from the live entity state — so after a successful Link action triggers `onRefresh()`, the entity reloads with the new chapter link, `existingChapterIds` updates, and `suggestedChapter` naturally becomes `null` (no banner).

#### 6.4.4 Link Action Handler

```typescript
const [isBannerLinking, setIsBannerLinking] = useState(false);
const [bannerError, setBannerError] = useState('');

async function handleSuggestLink(chapterId: string, chapterTitle: string | null) {
  setIsBannerLinking(true);
  setBannerError('');
  try {
    await glossaryApi.createChapterLink(bookId, entityId, {
      chapter_id: chapterId,
      relevance: defaultRelevance,
      // chapter_title is stored on creation if the API accepts it;
      // the existing createChapterLink API does not take chapter_title in body —
      // the backend resolves it from book-service. No change needed.
    }, token);
    onRefresh(); // triggers entity reload → existingChapterIds updates → banner hides
  } catch (e: unknown) {
    setBannerError((e as Error).message || 'Failed to link chapter');
  } finally {
    setIsBannerLinking(false);
  }
}
```

**Alignment note:** `glossaryApi.createChapterLink` already accepts `{ chapter_id, relevance, note? }` — no API change needed.

#### 6.4.5 Banner JSX

Add after the `{/* Evidences */}` block, still inside `{isExpanded && ...}`:

```tsx
{/* Chapter-link suggestion banner */}
{suggestedChapter && (
  <div className="flex items-start gap-2 rounded border border-blue-200 bg-blue-50 px-3 py-2 text-xs dark:border-blue-800 dark:bg-blue-950">
    <span className="mt-0.5 shrink-0 text-blue-500">💡</span>
    <div className="min-w-0 flex-1">
      <p className="font-medium text-blue-800 dark:text-blue-200">
        Link chapter to entity?
      </p>
      <p className="text-blue-700 dark:text-blue-300">
        Evidence references{' '}
        <span className="font-semibold">
          {suggestedChapter.chapterTitle ?? suggestedChapter.chapterId}
        </span>
        {' '}but this chapter is not linked yet.
      </p>
      {bannerError && (
        <p className="mt-1 text-destructive">{bannerError}</p>
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={isBannerLinking}
          onClick={() =>
            handleSuggestLink(suggestedChapter.chapterId, suggestedChapter.chapterTitle)
          }
          className="rounded bg-blue-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {isBannerLinking ? 'Linking…' : 'Link chapter'}
        </button>
        <button
          type="button"
          onClick={() =>
            setDismissedChapterIds((prev) =>
              new Set([...prev, suggestedChapter.chapterId]),
            )
          }
          className="rounded px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground"
        >
          Dismiss
        </button>
      </div>
    </div>
  </div>
)}
```

#### 6.4.6 Reset Banner State on Entity Reload

When `onRefresh()` causes the entity to update (changing `av.evidences` via new prop), and if a link was just created, the banner hides automatically because `existingChapterIds` is updated by the parent re-render. No extra cleanup needed.

However, `isBannerLinking` and `bannerError` should reset when the `av` prop changes identity (entity reload). Add to existing `useEffect` that syncs local state:

```typescript
// Existing useEffect — extend to also clear banner error:
useEffect(() => {
  if (!isEditingRef.current) {
    setLocalValue(av.original_value);
    setLocalLang(av.original_language);
    setBannerError('');  // ← ADD: clear stale error on entity reload
  }
}, [av.original_value, av.original_language]);
```

**Note:** `isBannerLinking` is naturally reset by the `finally` block in `handleSuggestLink`. No additional cleanup needed.

### 6.5 Complete Updated AttributeRow.tsx

For implementer reference, the full diff summary:

```
Props type:     +existingChapterIds: string[], +defaultRelevance: Relevance
New state:      dismissedChapterIds: Set<string>
                isBannerLinking: boolean
                bannerError: string
New derived:    suggestedChapter (computed inline, not state)
New handler:    handleSuggestLink(chapterId, chapterTitle)
useEffect:      +setBannerError('') on entity reload
JSX addition:   ChapterSuggestBanner block after {/* Evidences */}
```

The existing logic (save, translations, evidences) is **unchanged**.

---

## 7) Files to Create/Modify

### New Files

| File | Purpose |
|---|---|
| `services/glossary-service/internal/api/preferences_handler.go` | `getGlossaryPreferences` + `putGlossaryPreferences` handlers |
| `frontend/src/features/glossary/hooks/useGlossaryPreferences.ts` | Fetch preferences once; return `defaultRelevance` |
| `frontend/src/components/settings/GlossarySection.tsx` | "Glossary" tab content in user settings |

### Modified Files

| File | Change |
|---|---|
| `services/glossary-service/internal/migrate/migrate.go` | Add `glossary_user_preferences` table DDL |
| `services/glossary-service/internal/api/server.go` | Register `GET/PUT /v1/glossary/preferences` routes |
| `frontend/src/features/glossary/types.ts` | Add `GlossaryUserPreferences` type |
| `frontend/src/features/glossary/api.ts` | Add `getPreferences`, `putPreferences` to `glossaryApi` |
| `frontend/src/features/glossary/components/EntityDetailPanel.tsx` | Call `useGlossaryPreferences`; pass `existingChapterIds` + `defaultRelevance` to `AttributeRow` |
| `frontend/src/features/glossary/components/AttributeRow.tsx` | Add `existingChapterIds` + `defaultRelevance` props; add banner state/logic/JSX |
| `frontend/src/pages/UserSettingsPage.tsx` | Add `'glossary'` tab; render `GlossarySection` |

---

## 8) Test Coverage

### Backend Tests (append to `server_test.go`)

| # | Scenario | Expected |
|---|---|---|
| T1 | GET preferences — new user | 200, `default_chapter_link_relevance: "mentioned"` |
| T2 | PUT preferences `major` | 200, `default_chapter_link_relevance: "major"` |
| T3 | GET preferences after PUT | 200, persisted value |
| T4 | PUT invalid value `"pivotal"` | 422, `GLOSS_INVALID_BODY` |
| T5 | PUT empty string | 422, `GLOSS_INVALID_BODY` |
| T6 | GET without auth | 401 |
| T7 | PUT without auth | 401 |
| T8 | PUT upsert idempotency (two writes) | 200, second value returned |

### Frontend Tests

**File:** `frontend/src/features/glossary/components/AttributeRow.test.tsx` (new)

| # | Scenario | Expected |
|---|---|---|
| F1 | Evidence with `chapter_id` not in `existingChapterIds` → expanded | Banner renders with chapter title |
| F2 | Evidence with `chapter_id` already in `existingChapterIds` | No banner |
| F3 | Evidence with `chapter_id = null` | No banner |
| F4 | Click "Dismiss" | Banner disappears; `createChapterLink` not called |
| F5 | Click "Link chapter" → success | `createChapterLink` called with correct `chapter_id` + `defaultRelevance`; `onRefresh` called |
| F6 | Click "Link chapter" → API error | Error message shown inline; `onRefresh` not called |
| F7 | Multiple evidences with unlinked chapters | Suggests only the most recent one |

**File:** `frontend/src/components/settings/GlossarySection.test.tsx` (new)

| # | Scenario | Expected |
|---|---|---|
| G1 | Mount → `getPreferences` called → select shows returned value | Correct option selected |
| G2 | Change select → click Save | `putPreferences` called with new value |
| G3 | Save success | Success message shown |
| G4 | Save failure (network error) | Error alert shown |

---

## 9) Edge Cases and Notes

### 9.1 Stale `suggestedChapter` After Dismiss + Entity Refresh

If the user dismisses a chapter suggestion, then navigates away and back (remounting `EntityDetailPanel`), the `dismissedChapterIds` Set is recreated empty. The banner will reappear. This is **acceptable for MVP** — the banner is informational and the user can dismiss again. Persistent dismiss storage is deferred.

### 9.2 Multiple Attributes Referencing the Same Chapter

If two `AttributeRow`s both have evidences referencing the same unlinked chapter, both will show the banner. The second click would fail with a duplicate chapter link error (backend enforces uniqueness on `(entity_id, chapter_id)`).

**Mitigation in handler:** On API error with a conflict-style error code, show specific message: "Chapter is already linked." The `createChapterLink` endpoint currently returns whatever error the backend sends; if it returns 409 or a descriptive error, the banner displays it. After `onRefresh()`, the now-linked chapter disappears from both banners.

This is considered acceptable behavior for MVP — after the first link is created and `onRefresh` fires, the second banner auto-dismisses.

### 9.3 createChapterLink API — chapter_title Parameter

The existing `createChapterLink` in `api.ts` does NOT send `chapter_title` in the body:
```typescript
body: { chapter_id: string; relevance: Relevance; note?: string }
```

The backend `createChapterLink` handler retrieves `chapter_title` from the book-service via `book_client.go` when the chapter_id is provided. **No change needed** to the API contract — the banner does not need to pass `chapter_title`.

### 9.4 Relevance Mismatch Between Requirement Doc and Existing Schema

Doc 88 (requirements) listed `'mentioned','minor','major','pivotal'` as the relevance enum. The existing production schema (`chapter_entity_links`) and TypeScript type use `'major' | 'appears' | 'mentioned'`. This design **uses the existing production values** to maintain consistency. The requirements doc was written before final schema alignment. `'minor'` and `'pivotal'` do not exist in the current system and cannot be introduced by SS-3 alone (requires a migration on `chapter_entity_links` CHECK constraint, out of SS-3 scope).

### 9.5 Dark Mode Styling

The banner uses Tailwind dark-mode classes (`dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200`). The existing app has dark mode support via the Tailwind `dark` variant. The banner is tested visually against both themes.

---

## 10) Exit Criteria

- [ ] `glossary_user_preferences` table created in migration; `go test ./...` passes.
- [ ] `GET /v1/glossary/preferences` returns defaults for new user; returns persisted value after PUT.
- [ ] `PUT /v1/glossary/preferences` with invalid value returns 422.
- [ ] Settings page `/settings/glossary` renders "Glossary" tab with relevance select.
- [ ] Saving changes preference; page shows success message.
- [ ] `AttributeRow`: expanding with an evidence that references an unlinked chapter shows banner.
- [ ] Banner "Link chapter" creates a chapter link with user's configured relevance.
- [ ] Banner "Dismiss" hides banner without creating a link.
- [ ] No banner when evidence has no `chapter_id` or chapter is already linked.
- [ ] `npx tsc --noEmit` passes — no TypeScript errors.
- [ ] `go test ./...` passes — all backend tests green.
