# Plan — Glossary Tiered + CMS implementation gaps (FE/BE)

> **Date:** 2026-06-20. **Status:** PLAN (CLARIFY done; no code yet). **Inputs:** a 2-agent draft-vs-impl gap review + the tiered/CMS scenarios [`docs/specs/2026-06-20-glossary-tiered-cms-scenarios.md`](../specs/2026-06-20-glossary-tiered-cms-scenarios.md) (S27–S40). **Goal:** the concrete FE/BE backlog to close the tiered + CMS gaps before the next build run.

## Corrections applied (false gaps the raw review flagged — verified DONE, do NOT build)

The design drafts (`design-drafts/screens/glossary/*.html`) are the **old tag-based** model and predate the tiered re-arch; an automated scan of only `features/glossary/` also missed sibling features. Verified actually-built:

- **Per-user Standards Library** — `frontend/src/features/standards/` (`/standards/:tab`): Genres/Kinds/Attributes panels, `StandardFormModal`, `AttributeFormModal`, `KindGenresModal`, **TrashDrawer** (recycle bin), `useUserStandards`/`useStandardsTrash`. ✅
- **Genre CRUD** — user-tier `standards/GenresPanel` + system-tier `cms standards-admin/GenresAdminPanel`. ✅
- **Universal recycle bin / entity trash** — `frontend/src/features/trash/` + `standards/TrashDrawer`. ✅
- **`/mcp/admin` server + chat-service AdminContext + gateway `/mcp/admin` downstream** — shipped T4/T4c/T4d, **live-proven at CP-6** (the raw review assumed T4 unbuilt). ✅
- **Attribute "genre scoping" UI** (old attr-editor draft) — **OBSOLETE**: superseded by the tiered `kind × genre` cell model. Do not build.

## Real gaps — backlog

Tags: **[FE]** cms-frontend or frontend only · **[BE]** glossary-service / chat-service · **[BE+FE]** both. Priority: **P0** safety/reversibility · **P1** CMS parity · **P2** authoring/grounding · **P3** polish · **T2** Track-2/deferred.

### A. Reversibility & safety (P0 — do first; these prevent irreversible loss on shared/System rows)

| ID | Gap | Tag | Scenario | Notes |
|---|---|---|---|---|
| **G-C8** | System genre/kind/attribute **DELETE is hard** — no soft-delete, no restore | **[BE+FE]** | S37 | BE: add `deprecated_at` nullable to `system_genres/kinds/attributes`; `admin_core` delete cores set it + cascade; new restore core + `glossary_admin_propose_restore` tool + `/system-*/{id}/restore`. FE: a "Recycle Bin" view in cms standards-admin. (Spec §3d says `system_delete` is class-C — soft-delete is the safe pattern.) |
| **G-U1** | No **revert a Book override back to its parent tier** (User/System) | **[BE+FE]** | S31, S36 | BE: `DELETE /v1/glossary/book-{genres,kinds,attributes}/{id}` becomes "drop the local copy, fall back to parent" OR a `/revert` endpoint; an MCP `glossary_book_revert` (C). FE: a "Revert to default" action on a Book-tier row in `ManageWorkspace`/`AttributeEditorPanel`. |

### B. CMS UX parity with the user-tier FE (P1 — mostly FE-only; the System admin surface is functional but thin)

| ID | Gap | Tag | Scenario | Notes |
|---|---|---|---|---|
| **G-C1** | No **attribute matrix** (kind × genre grid, conflict highlight) | **[FE]** | S34 | Port the pattern from `frontend tiering/AttributeMatrix` + `MatrixCellInspector` into cms `AttributesAdminPanel` (replace the dual-dropdown-only view). |
| **G-C2** | No **field-type badge** + no **cell inspector** pane | **[FE]** | S35 | Styled `field_type` badge on attribute rows; a read-only side inspector (code/name/type/options/required/sort) without opening a modal. |
| **G-C3** | Options textarea always shown; **no field-type-conditional** rendering/validation | **[FE]** | S35 | Show options only when `field_type === 'select'`; validate per type (mirror the user-FE `AttributeFormModal`). |
| **G-C4** | No **search / filter** on genres/kinds/attributes lists | **[FE]** | S30 | Add name/code search; scales as System grows past a handful of kinds. |
| **G-C6** | Genre/kind **icon + color are plain text inputs** (no picker) | **[FE]** | S32 | `<input type="color">` + an emoji/icon picker; mirror what the user-tier modals should also gain. |
| **G-C7** | Admin chat has **no live System-standards reference** sidebar | **[FE]** | S39 | A read-only pane in `AdminChatPanel` listing current System genres/kinds/attributes so the agent (and human) propose against real state. (`glossary_admin_standards_read` already supplies the data.) |
| **G-C5** | `sort_order` is a number input — no **reorder** affordance | **[FE]** | S30 | ↑↓ buttons per row (simplest) or drag-handle. |

### C. Authoring depth, grounding & token lifecycle (P2/P3)

| ID | Gap | Tag | Scenario | Notes |
|---|---|---|---|---|
| **G-U2** | No per-attribute **`auto_fill_prompt` / `translation_hint`** authoring | **[BE+FE]** P2 | S38 | BE: add the two columns to `system/user/book_attributes` (+ create/patch cores + tool params). FE: an "AI assistance" section in the attribute editors. **Also unblocks the pipeline campaign** (the future extract/translate tools consume these). |
| **G-C9** | No **audit/revision ledger** for System changes (who/what/when) | **[BE+FE]** P2 | S37 | BE: a `system_change_log` (actor admin sub, action, before/after, confirmed_at) written by `admin_core`. FE: a "History" tab. |
| **G-U3** | **Relationships** field-type is stubbed in the entity form | **[FE]** P3 | — | `RelationshipField` component + wire into `TieredEntityForm` (entity-editor draft shows it). |
| **G-U4** | Entity **edit** modal w/ meta-bar + required/description hints | **[FE]** P3 | — | `EditEntityModal` (vs create-only) showing chapters/translations/evidence counts + per-field `*required` / description help text. (Trash already exists via `features/trash`.) |
| **G-C10** | **Admin token refresh on 401** mid-chat | **[BE]** P3 | S40 | chat-service re-exchanges via `/v1/admin/session` on a `/mcp/admin` 401 and retries (clears `D-T4D-ADMIN-TOKEN-REFRESH`). |
| **G-C11** | No **bulk admin propose** ("create 10 genres") | **[BE]** T2 | — | `glossary_admin_propose_bulk` taking an array of ops under one confirm-token. Deferred. |

## Build order

1. **P0 reversibility (one BE+FE run):** G-C8 (System soft-delete + restore + recycle bin) → G-U1 (book→parent revert). Schema + cores + tools + the two FE surfaces. Highest value: deletes on shared/System rows are currently irreversible.
2. **P1 CMS parity (one FE run):** G-C1 → G-C2 → G-C3 → G-C4 (+ G-C5/G-C6 if cheap). Brings the System admin surface to user-FE quality; pure cms-frontend.
3. **P2 authoring + grounding:** G-U2 (AI-assistance fields — schema + editors; **also the bridge to the pipeline campaign**), G-C7 (standards sidebar), G-C9 (audit ledger).
4. **P3 polish:** G-U3, G-U4, G-C10.
5. **T2:** G-C11.

## Relationship to the other campaign

The scenario coverage doc's next campaign is **making the pipeline + read ops agent-reachable** (S4 translate, S5 deep-research, S7/S8 extract, S9 merge, S12 triage, S16 evidence, S17 chapter-link, S20 async). That is a **parallel track** to this one (this is FE/UX + reversibility; that is new MCP tools). **G-U2 (attribute AI-assistance fields) is the shared dependency** — the extract/translate tools consume `auto_fill_prompt`/`translation_hint`, so doing G-U2 in P2 unblocks part of that campaign.

## Verification notes (carried from the review, to confirm at BUILD)

- Confirm whether cms-frontend should **share** components with `frontend/features/standards` (separate apps today → likely selective port, not a shared package).
- Confirm the entity **edit** path (vs create) — `CreateEntityModal` exists; an `EditEntityModal` with delete→trash may already be partially covered by `features/trash`; verify before building G-U4.
