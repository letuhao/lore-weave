# Plan — Glossary Tiered MCP Tools · T2 SYNC ∥ T3 USER (CP-3 milestone)

**Date:** 2026-06-20 · **Spec:** [tiered-tools](../specs/2026-06-20-glossary-assistant-tiered-tools.md) §3b/§3c/§12.4 · **Buildplan:** [§5](2026-06-20-glossary-assistant-tiered-tools-buildplan.md) · **Predecessors:** Foundation (CP-1), T1 BOOK (CP-2, `99db6907`)

Both streams were unblocked at CP-2. Built as **one continuous milestone** (not two background agents) because T2 edits the shared confirm-spine (not append-only) and both suites share `loreweave_glossary_test` (concurrent runs cross-contaminate). Serial build → single live-smoke + `/review-impl` on the T2 confirm path at CP-3.

---

## T2 — SYNC (glossary Go + chat curation)

New file `sync_tools.go` → `RegisterSyncTools(srv)` (append-only registration in `mcp_server.go`).

| Tool | Class | Wraps | Gate | Notes |
|---|---|---|---|---|
| `glossary_book_sync_available` | R | `syncGenres/Kinds/AttributesAvailable` | GrantView | returns the `syncUpdateItem[]` diff (mine vs theirs, retired) |
| `glossary_book_sync_apply` | C | `applyBookSyncCore` (NEW, extracted) | GrantManage | LLM proposes `Items[]{entity,id,choice}`; mints `descSyncApply` token; human confirms set |

**Confirm-spine edits (shared files):**
- `action_confirm_token.go`: add `descSyncApply = "sync_apply"` to the const block + `liveDescriptor` switch.
- `action_confirm.go`: add `syncApplyParams{Items []syncApplyItemReq}`; dispatch `descSyncApply → effectSyncApply`; preview `descSyncApply → previewSyncApply`.
- `book_sync_handler.go`: **extract `applyBookSyncCore(ctx, bookID, userID, items) (syncApplyResp, error)`** from `applyBookSync` HTTP handler (the advisory-lock + per-row apply tx). HTTP handler + `effectSyncApply` both call it → no divergence (the T1 core pattern).
- `effectSyncApply`: re-decode params → `applyBookSyncCore` (re-validates each row against current source state; retired rows return `source_retired`, never error the batch).
- `previewSyncApply`: re-render from CURRENT state — count rows still updatable vs retired (re-run the diff, intersect with proposed ids); rows = `{take_theirs: n, keep_mine: n, no longer available: n}`.

**Mint-time validation (§11 #8):** `toolBookSyncApply` validates `Items` shape (entity ∈ genre|kind|attribute, choice ∈ keep_mine|take_theirs, id is UUID) + non-empty BEFORE minting, so the agent never shows a doomed card.

**chat-service:** advertise sync tools on the book surface (`frontend_tools.py`/`stream_service.py` book branch); confirm card is the generic descriptor-keyed `glossary_confirm_action` (no FE change). Skill-prompt: one line on "reconcile the book against its standards".

---

## T3 — USER (glossary Go + chat curation)

New file `user_tools.go` → `RegisterUserTools(srv)`. **Owner-scoped:** gate = `X-User-Id == owner`, NO grant/book lookup (§4a). Descriptions say "your personal standards" (§11 #11). Deletes are **W** (reversible via existing trash), not C (§3c).

| Tool | Class | Wraps | Notes |
|---|---|---|---|
| `glossary_user_standards_read` | R | `listUserGenres/Kinds/Attributes` | owner-scoped; optional `level` filter; caller-scoped visibility (C5) |
| `glossary_user_create` | W | `createUser{Genre,Kind,Attribute}` cores | level-collapsed; clone-from-system supported where the handler does |
| `glossary_user_patch` | W | `patchUser*` cores | `base_version` (content_hash / updated_at) → 409 on drift (§12.6) |
| `glossary_user_delete` | W | `deleteUser*` (soft → trash) | level-collapsed; reversible |
| `glossary_user_restore` | W | `restoreUser{Genre,Kind}` (+ attr if it exists) | undo own soft-delete (§11 #12) |

**Core extraction:** user handlers are monolithic HTTP today. Extract `createUser*Core`/`patchUser*Core`/`deleteUser*Core`/`restoreUser*Core` (caller-scoped) mirroring T1's `book_ontology_core.go`, called by BOTH the HTTP handler and the MCP tool. If a verb has no clean core seam, replicate the owner-scoped query in `user_tools.go` with a test asserting parity.

**chat-service:** advertise user-tier tools on the book surface (the caller's own library, §12.3); skill-prompt line on "your reusable standards library".

---

## Tests (VERIFY gate)
- `sync_tools_test.go`: available round-trips a real diff; apply C-path (propose→token→confirm→applied); retired-source row → `source_retired` not error; non-Manage grantee denied; replay→422 (single-use via consumed_tokens).
- `user_tools_test.go`: create/patch/delete/restore round-trip owner-scoped; **non-owner denied** (tenancy); patch `base_version` 409; restore brings a trashed row back; caller-scoped read doesn't leak another owner's rows.
- Full glossary suite green (api + migrate). Live-smoke: chat→sync_available→sync_apply→confirm→ontology reflects; chat→user_create→user_standards_read.

## CP-3 exit
All book + user + sync tools on `/mcp`, each live-smoked; catalog still verb-collapsed; no admin tool on `/mcp`. `/review-impl` on the T2 confirm path (new descriptor = new write authority surface).
