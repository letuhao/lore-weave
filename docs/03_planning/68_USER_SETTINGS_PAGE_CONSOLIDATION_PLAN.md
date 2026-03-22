# User Settings Page Consolidation Plan

## Document Metadata
- Document ID: LW-68
- Version: 1.1.0
- Status: Approved
- Owner: Frontend Lead
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Plan to consolidate Profile, Security, Verify Email, AI Models, and Translation Settings into a unified `/settings` page with tab-based sections.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.1.0 | 2026-03-22 | Approved by Decision Authority; added `POST /v1/auth/change-password` backend + real change-password form in AccountSection | Assistant |
| 1.0.0 | 2026-03-22 | Initial draft | Assistant |

---

## 1. Motivation

Currently, user-facing settings are scattered across 5 separate nav links:

| Current route | Current nav label | Content |
|---|---|---|
| `/profile` | Profile | Display name, raw profile JSON |
| `/security` | Security | Password reset method preference |
| `/verify` | Verify email | Request verification email + confirm token |
| `/m03/models` | AI Models | Provider credentials + user models |
| `/translation/settings` | Translation | Default target language, model, prompt templates |

Problems:
- Nav bar is cluttered — 5 user-account links plus workspace links
- "No model configured" warning on BookTranslationPage because model is saved in Translation Settings but users may not realize they need to go there first
- Each page is isolated; users cannot discover related settings without navigating separately

---

## 2. Goal

Replace all 5 pages with a single **User Settings** page at `/settings` with tab/section navigation:

```
/settings                → redirect to /settings/account
/settings/account        → Account section (profile + email verify + change password)
/settings/providers      → Model Providers section (provider credentials + user models)
/settings/translation    → Translation section (default translation preferences)
```

Nav bar collapses to one link: **Settings**

---

## 3. Section Specifications

### 3.1 Account section (`/settings/account`)

Consolidates: `ProfilePage`, `SecurityPage`, `VerifyPage`

Sub-sections (displayed sequentially on same page, no additional tabs):

#### 3.1.1 Profile
- Display name input + Save (existing `ProfilePage` form)
- Show email (read-only from profile API response)
- Show `email_verified` status badge (green "Verified" / amber "Not verified")

#### 3.1.2 Email Verification
- Shown only when `email_verified === false`
- "Send verification email" button → `POST /v1/auth/verify-email/request`
- Token input + Confirm button → `POST /v1/auth/verify-email/confirm`
- On success: re-fetch profile, hide this sub-section

#### 3.1.3 Change Password
- New subsection (currently no dedicated change-password UI)
- Fields: `current_password`, `new_password`, `confirm_new_password`
- Calls: `POST /v1/auth/change-password` (endpoint exists in auth-service)
- Client-side validation: new ≠ current, confirm matches new, min 8 chars

#### 3.1.4 Security Preferences
- Password reset method selector (existing `SecurityPage` form)

### 3.2 Model Providers section (`/settings/providers`)

Mirrors: existing `UserModelsPage` content verbatim (no feature changes)

- Provider credentials (add / delete)
- Model inventory fetch per provider
- User models (add / delete / favorite)
- **Note:** `PlatformModelsPage` stays at `/m03/platform-models` for now (admin/read-only page, not user settings)

### 3.3 Translation section (`/settings/translation`)

Mirrors: existing `TranslationSettingsPage` content verbatim (no feature changes)

- Default target language
- Default model (ModelSelector)
- Default system prompt + user prompt template

---

## 4. Navigation Changes

### 4.1 AppNav — before

```
Workspace | Recycle bin | AI Models | Platform models | Usage logs | Translation  [Browse]
                                             Profile | Security | Verify email | [Log out]
```

### 4.2 AppNav — after

```
Workspace | Recycle bin | Usage logs  [Browse]
                               Settings | [Log out]
```

- **Removed links:** AI Models, Translation, Profile, Security, Verify email
- **Added link:** `Settings` → `/settings`
- **Kept:** Platform models link removed from primary nav too (accessible via Settings or direct URL); Usage logs stays (it is a log viewer, not a settings page)

### 4.3 Platform Models

`PlatformModelsPage` at `/m03/platform-models` is a read-only catalog, not a personal settings page. Keep it accessible but remove from primary nav — add a link inside the Model Providers section: "Browse platform models →"

---

## 5. Routing Changes

### 5.1 New routes

| Route | Component |
|---|---|
| `/settings` | redirect → `/settings/account` |
| `/settings/account` | `UserSettingsPage` (tab: account) |
| `/settings/providers` | `UserSettingsPage` (tab: providers) |
| `/settings/translation` | `UserSettingsPage` (tab: translation) |

### 5.2 Redirect / compat routes (keep old routes working)

| Old route | Redirect to |
|---|---|
| `/profile` | `/settings/account` |
| `/security` | `/settings/account` |
| `/verify` | `/settings/account` |
| `/m03/models` | `/settings/providers` |
| `/translation/settings` | `/settings/translation` |

### 5.3 BookTranslationPage link fix

`BookTranslationPage.tsx` line 235 currently links to `/translation/settings`. Update to `/settings/translation`.

---

## 6. Component Architecture

```
src/pages/UserSettingsPage.tsx          ← new shell (tab router)
src/components/settings/
  AccountSection.tsx                    ← merged Profile + VerifyEmail + ChangePassword + SecurityPrefs
  ProvidersSection.tsx                  ← moved from UserModelsPage (rename/refactor)
  TranslationSection.tsx                ← moved from TranslationSettingsPage (rename/refactor)
```

`UserSettingsPage` reads the active tab from the URL path segment and renders the matching section component. Uses `<Link>` for tab navigation (no JS tab state — URL is the source of truth).

Old page files become thin wrappers or are deleted:
- `ProfilePage.tsx` → delete (content moved to `AccountSection`)
- `SecurityPage.tsx` → delete (content moved to `AccountSection`)
- `VerifyPage.tsx` → delete (content moved to `AccountSection`)
- `UserModelsPage.tsx` → delete (content moved to `ProvidersSection`)
- `TranslationSettingsPage.tsx` → delete (content moved to `TranslationSection`)

---

## 7. Change Password — Backend Check

The `AccountSection` change-password form calls `POST /v1/auth/change-password`. Before implementing the frontend, confirm this endpoint exists in `auth-service`.

**Action item:** Read `services/auth-service/app/routers/` to verify endpoint availability. If missing, backend work is required before frontend can be completed for this sub-section (treat as deferred — render form as "coming soon" if endpoint absent).

---

## 8. Implementation Steps

1. **Verify** `POST /v1/auth/change-password` endpoint in auth-service
2. **Create** `src/pages/UserSettingsPage.tsx` — shell with tab layout, reads tab from URL
3. **Create** `src/components/settings/AccountSection.tsx` — consolidate Profile + Verify + ChangePassword + SecurityPrefs
4. **Create** `src/components/settings/ProvidersSection.tsx` — move content from `UserModelsPage`
5. **Create** `src/components/settings/TranslationSection.tsx` — move content from `TranslationSettingsPage`
6. **Update** `src/App.tsx` — add `/settings/*` routes + redirect compat routes for old URLs
7. **Update** `src/components/layout/AppNav.tsx` — replace 5 links with single "Settings" link
8. **Update** `src/pages/BookTranslationPage.tsx` — fix `/translation/settings` link → `/settings/translation`
9. **Delete** old page files: `ProfilePage.tsx`, `SecurityPage.tsx`, `VerifyPage.tsx`, `TranslationSettingsPage.tsx`; keep `UserModelsPage.tsx` until `ProvidersSection` is stable then delete

---

## 9. Out of Scope

- No backend API changes (all existing endpoints remain unchanged)
- `PlatformModelsPage` is not merged into settings (read-only, admin-oriented)
- `UsageLogsPage` / `UsageDetailPage` are not merged (operational logs, not settings)
- No design system changes

---

## 10. Open Questions

| ID | Question | Default if not answered |
|---|---|---|
| OQ-1 | Does `POST /v1/auth/change-password` exist in auth-service? | Defer change-password sub-section, show placeholder |
| OQ-2 | Should Platform Models link move inside Settings/Providers or stay in nav? | Move to Settings/Providers as a "Browse platform models" link, remove from top nav |
| OQ-3 | Keep Usage Logs in top nav or move to Settings? | Keep in top nav (it is usage monitoring, not configuration) |
