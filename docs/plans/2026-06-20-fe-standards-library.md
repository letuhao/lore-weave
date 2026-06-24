# Plan — FE Standards Library (`D-GKA-FE-STANDARDS-LIBRARY`)

**Date:** 2026-06-20 · **Branch:** `feat/glossary-assistant-coverage` · **Size:** L (FE-only, backend shipped in G2)
**Spec:** [`2026-06-19-genre-kind-attribute-tiering.md`](../specs/2026-06-19-genre-kind-attribute-tiering.md)
**PO decision (CLARIFY):** standalone **`/standards`** route + top-level sidebar entry (tier-correct: User-tier standards are per-user, not per-book).

## Goal & acceptance criteria

A per-user UI to manage the **User tier** of glossary standards. A user can:
- **View** merged System + User genres / kinds / attributes (tier-tagged via `TierChip`).
- **Clone** a System standard into their User tier (same `code`) and then edit it — never edits the shared System row (CLAUDE.md › User Boundaries).
- **CRUD** their own user-tier genres / kinds / attributes + kind↔genre links.
- **Restore** soft-deleted user standards from a recycle bin.

These already flow into the adopt pick-list (`useStandards` merges System+User) and, per spec D7, into book resolution as the book owner's User tier. **No backend work** — every route exists (G2).

## Backend surface (exists; FE consumes)
- `GET /v1/glossary/genres` merged · `/user-genres` POST/PATCH/DELETE (+`clone_from_genre_id`) · `/user-genres-trash` GET / `{id}/restore` / DELETE-purge
- `GET /v1/glossary/user-kinds` · POST (+`clone_from_kind_id`) · `{id}` PATCH/DELETE · `{id}/genres` GET/PUT (links) · `/user-kinds-trash` GET / restore / purge
- `GET /system-attributes?kind_id=&genre_id=` (read-only) · `/user-attributes` GET/POST/PATCH/DELETE (attach-by-code: kind_id+genre_id must be the caller's live user rows → 422)

## Tenancy (already enforced server-side; FE must not assume otherwise)
- Every user-* route is **owner-scoped** by the JWT `user_id` (G2 `TenantIsolation`/`AttachByCodeAndTenancy` tests). The FE only ever reads/writes the caller's own tier; System rows render **read-only** (clone, never edit).

## File layout (new `features/standards/`, reuses glossary `tieringApi`/`tieringTypes`/`TierChip`/`FieldTypeBadge`)
```
features/standards/
  pages/StandardsPage.tsx        route entry; redirect /standards → /standards/genres; mounts StandardsShell
  components/
    StandardsShell.tsx           tab bar Genres|Kinds|Attributes + Trash button (≤100 ln)
    GenresPanel.tsx              list system+user genres; clone/edit/delete
    KindsPanel.tsx               list system+user kinds; clone/edit/delete; kind↔genre links
    AttributesPanel.tsx          pick user kind×genre → user attrs (CRUD) + system attrs (read-only)
    StandardRow.tsx              shared row: icon, name, code, TierChip, actions
    StandardFormModal.tsx        create/edit a user genre|kind (name/icon/color/code)
    AttributeFormModal.tsx       create/edit a user attribute (name/code/field_type/required/options)
    TrashDrawer.tsx              recycle bin: list trashed genres+kinds, restore/purge
  hooks/
    useUserStandards.ts          controller: merged reads + clone/create/patch/delete + trash (≤200 ln; split if over)
```
Wiring: `App.tsx` add `/standards` + `/standards/:tab` under the authed `DashboardLayout`; `Sidebar.tsx` add `{ to:'/standards', icon: Library, labelKey:'nav.standards', auth:true }` to `mainNav`.
API: extend `tieringApi` with `createUserKind`/`patchUserKind`/`deleteUserKind` + 6 trash methods; add `UserKindCreate` type. (No new contract — routes exist; `POST /entities`-style additive client only.)

## Sub-milestones (POST-REVIEW at each shippable boundary)
- **M1 — read + clone + route/nav.** StandardsPage route, sidebar entry, StandardsShell, GenresPanel + KindsPanel read views (merged, tier-tagged), clone-from-System (genre `clone_from_genre_id`, kind `clone_from_kind_id`). `useUserStandards` reads + clone mutations. i18n `en`. Tests: hook (merged read + clone), shell tabs, one panel.
- **M2 — attributes + kind↔genre links.** AttributesPanel (kind×genre picker → user attrs list + system attrs read-only + create user attr via attach-by-code) + link editing on KindsPanel (`setUserKindGenres`). Tests: attr create attach-by-code, link set.
- **M3 — edit/delete + recycle bin.** StandardFormModal + AttributeFormModal (create/edit), delete (soft) for all 3 levels, TrashDrawer (restore/purge). Busy-guards on modals (mirror CreateEntityModal). Tests: form submit, delete→trash→restore.
- **M4 — i18n ×4 + a11y + parity.** vi/ja/zh-TW `standards` namespace; `npm run i18n:check` clean; a11y (roles/labels/focus); fill test gaps.

## VERIFY (per milestone)
`tsc` clean (ignore pre-existing @dnd-kit) + `vitest` green for new specs + `npm run i18n:check` clean (M4). FE-only, single surface → **no cross-service live-smoke token** needed (stack already up — optional Playwright click-through at M4).

## Risks / deferrals
- `genre_tags` is a vestigial field on `createUserKind` — FE omits it (defaults `[]`).
- System attributes are read per (kind×genre); the AttributesPanel only fetches them for a selected user kind that has a `cloned_from_kind_id` system parent — otherwise there is no system (kind×genre) to show (a pure user kind has no system attrs). Acceptable; documented in M2.
- No new System-tier writes (that's `D-GKA-SYSTEM-TIER-ADMIN`, blocked on admin-identity).
