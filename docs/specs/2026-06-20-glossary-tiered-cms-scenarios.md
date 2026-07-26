# Glossary-Assistant — Tiered + CMS Scenarios (S27–S40)

> **Date:** 2026-06-20. **Status:** CLARIFY / coverage extension. **Companions:** [`2026-06-10-glossary-assistant-scenario-coverage.md`](2026-06-10-glossary-assistant-scenario-coverage.md) (S1–S8 + the 3-layer model + the 2026-06-20 status table) and [`2026-06-10-glossary-assistant-extended-scenarios.md`](2026-06-10-glossary-assistant-extended-scenarios.md) (S9–S26).
> **Why this doc:** the original S1–S26 predate three big extensions — (1) the **System→User→Book tiered ontology** (adopt / sync / clone-down / tier shadowing), (2) the **CMS** (the System-tier admin app), and (3) **genre as a first-class editable entity per tier**. These created new realistic scenarios for **both the human (manual FE) and the AI assistant (MCP tool)** that S1–S26 don't capture. This doc enumerates them and records the current verdict for each path.

## The three surfaces (where each tier is managed)

| Tier | Who writes | Human FE | AI surface |
|---|---|---|---|
| **System** | admin only (RS256) | **cms-frontend** `features/standards-admin` (Genres/Kinds/Attributes panels) + `features/admin-chat` | `/mcp/admin` → `glossary_admin_propose_create/patch/delete` + `glossary_admin_standards_read` (human-confirmed) |
| **User** (per-user, cross-book) | the user | **frontend** `features/standards` (`/standards/:tab` — Genres/Kinds/Attributes + TrashDrawer) | `glossary_user_create/patch/delete/restore` + `glossary_user_standards_read` |
| **Book** (per-book ontology + entities) | owner + grantees | **frontend** `features/glossary` (`OntologyShell` → Manage / Matrix / Sync; entities) | `glossary_book_create/patch/delete`, `adopt_standards`, `book_sync_available/apply`, `set_active_genres`, `set_kind_genres`, `entity_get/set_genres`, `propose_new_entity`, `propose_entity_edit` |

**Legend:** ✅ done · ⚠️ partial · ❌ open. Each scenario lists the **Human** path and the **AI** path independently (a scenario is only "done" when *both* surfaces deliver it the way the user expects).

---

## S27 — Adopt System/User standards into a book (copy-down)
**Intent:** an empty book → pick System/User genres+kinds+attributes → the book gets editable *copies* (Book tier), not references.
- **Human:** ✅ `AdoptPicklistModal` + `useBookOntology.adopt`.
- **AI:** ✅ `glossary_adopt_standards` (C — confirm-gated).

## S28 — Sync a book's adopted standards after upstream changes
**Intent:** a System/User row changed after adoption → the book-owner reviews a diff → applies per-row.
- **Human:** ✅ `SyncScreen` + `SyncDiffTable` (`useSync`).
- **AI:** ✅ `glossary_book_sync_available` (R) + `glossary_book_sync_apply` (C, per-row choices).

## S29 — Manage the per-user Standards Library
**Intent:** a user curates their *own* cross-book genres/kinds/attributes (a custom "Character+" kind reused in every book), with a recycle bin.
- **Human:** ✅ `features/standards` — `StandardsShell`, `GenresPanel`/`KindsPanel`/`AttributesPanel`, `StandardFormModal`, `AttributeFormModal`, `KindGenresModal`, `TrashDrawer` (`useUserStandards`, `useStandardsTrash`).
- **AI:** ✅ `glossary_user_create/patch/delete/restore` + `glossary_user_standards_read`.

## S30 — Manage System defaults via the CMS (admin)
**Intent:** an admin edits the platform-wide System defaults every tenant reads.
- **Human:** ⚠️ cms `standards-admin` panels do full CRUD, but the UX is **thinner** than the user-tier FE (no matrix, no field-type badge, no cell inspector, no search/filter, no recycle bin — see the gap plan).
- **AI:** ✅ cms `admin-chat` → `glossary_admin_propose_*` → `AdminConfirmCard` → `/actions/admin/confirm` (live-proven end-to-end at CP-6).

## S31 — Tier resolution & edit-safety (shadowing)
**Intent:** a Book row shadows a User override which shadows a System default; the user must see *what is a local editable copy vs a read-only shadow*, and be able to **revert** a local override back to its parent.
- **Human:** ⚠️ `TierChip` shows provenance (System/User/Book); **revert-to-parent is ❌** (no button/endpoint).
- **AI:** ⚠️ reads the merged ontology fine; **no revert tool ❌**.

## S32 — Genre lifecycle per tier
**Intent:** create/edit a genre (name, code, **icon, color**, sort) at System (CMS) / User (standards) / Book; activate/deactivate per book.
- **Human:** User ✅ (`GenresPanel`), Book active-genres ✅ (`ActiveGenrePills`/`GenrePillSelector`), System ⚠️ (cms create/edit works but **icon/color are plain text inputs**, no picker).
- **AI:** ✅ user/admin/book genre tools + `set_active_genres`.

## S33 — Adopt-then-customize per book (divergence)
**Intent:** two books adopt the same System genre, then diverge — different attributes per book — without affecting each other or the System default.
- **Human:** ✅ `ManageWorkspace` per book (book-scoped writes).
- **AI:** ✅ book tools (book-scoped).

## S34 — Attribute matrix (kind × genre grid)
**Intent:** see one kind's attributes across all active genres at a glance, with conflict highlighting (a code in 2+ genres).
- **Human:** user FE ✅ (`MatrixScreen` + `AttributeMatrix` + `MatrixCellInspector`); **CMS ❌** (sequential kind+genre dropdowns only).
- **AI:** n/a (the agent reads the resolved ontology).

## S35 — Field-type-aware attribute authoring
**Intent:** author an attribute as text/textarea/select(+options)/number/date/tags/boolean/url; options only when `select`; validation per type.
- **Human:** user/standards ✅ (`AttributeEditorPanel` / `AttributeFormModal`); **CMS ⚠️** (options textarea always shown; no field-type badge).
- **AI:** ✅ propose tools validate `field_type` (admin/book/user create cores).

## S36 — Revert / restore across tiers
**Intent:** restore a soft-deleted standard from trash; revert a Book override back to its User/System parent.
- **Human:** user-tier trash restore ✅ (`TrashDrawer`); **book→parent revert ❌**; **System restore ❌** (hard-delete).
- **AI:** `glossary_user_restore` ✅ (user-tier); **no book-revert / system-restore tool ❌**.

## S37 — CMS recycle bin + audit for System changes
**Intent:** System deletes are reversible (soft-delete + restore) and auditable (who changed which System default, when).
- **Human:** ❌ — System deletes are **hard** (`admin_core.go`); no audit/history view.
- **AI:** ❌ — no system-restore / no audit tool.

## S38 — Per-attribute AI-assistance authoring
**Intent:** author per-attribute `auto_fill_prompt` + `translation_hint` (the `screen-attr-editor-modal` draft shows this) so the future extract/translate tools can auto-fill / hint.
- **Human:** ❌ — not built (the draft shows it; **needs BE schema** on `*_attributes`).
- **AI:** ❌ — no tool; and the consuming extract/translate tools don't exist yet (S4/S7).

## S39 — Admin assistant grounded in current System state
**Intent:** the admin chat shows / can query the live System standards so the agent proposes against what exists (no blind proposals).
- **Human:** ⚠️ — no on-screen "System standards reference" sidebar in `AdminChatPanel`.
- **AI:** ⚠️ — `glossary_admin_standards_read` exists, but it isn't surfaced as standing context; the agent must call it each turn.

## S40 — Admin token lifecycle in long chats
**Intent:** the RS256 admin token (short TTL) expires mid-conversation; the chat re-exchanges via `/v1/admin/session` transparently and retries.
- **Human/AI:** ❌ — deferred (`D-T4D-ADMIN-TOKEN-REFRESH`); today a mid-session expiry surfaces an error and needs a re-login.

---

## Tally (S27–S40)

| Both surfaces ✅ | Partial ⚠️ | Open ❌ |
|---|---|---|
| S27, S28, S29, S33 | S30, S31, S32, S34, S35, S39 | S36*, S37, S38, S40 |

\* S36 is ✅ for user-tier restore, ❌ for book-revert + system-restore.

**Headline:** the **tier mechanics** (adopt/sync/clone-down/user-library) are done on both surfaces. The remaining work clusters in three buckets — all captured in the gap plan [`docs/plans/2026-06-20-glossary-tiered-cms-gap-plan.md`](../plans/2026-06-20-glossary-tiered-cms-gap-plan.md):
1. **CMS UX parity** with the user-tier FE (matrix, field-type badge, cell inspector, search, icon/color picker, standards-reference sidebar) — S30/S34/S35/S39, mostly FE-only.
2. **Reversibility across tiers** — book→parent revert + System soft-delete/restore + audit — S31/S36/S37, needs BE.
3. **Authoring depth + token lifecycle** — attribute AI-assistance fields (S38, needs BE schema) + admin-token refresh (S40, chat-service).
