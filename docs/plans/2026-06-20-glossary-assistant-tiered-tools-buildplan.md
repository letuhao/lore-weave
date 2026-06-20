# Build Plan — Glossary Assistant Tiered MCP Tools (parallel execution)

**Date:** 2026-06-20 · **Spec:** [`…glossary-assistant-tiered-tools.md`](../specs/2026-06-20-glossary-assistant-tiered-tools.md) · **Services:** glossary (Go), chat-service (Py), ai-gateway (TS), frontend (TS), cms-frontend (TS)

This plan turns the 5-phase spec into a **dependency DAG with explicit compose points (CP)** — the sync barriers where parallel streams converge — and **async streams** (independent work between barriers). Goal: maximize parallelism without letting cross-service contracts drift.

---

## 0. Solidity gate (pre-condition)

Spec is build-ready. Remaining phase-level (NOT blockers): T4 cms-frontend chat-panel mini-design (port main-FE SSE infra, §12.1); `admin:read` scope (lean reuse `admin:write`). Both resolved at their phase CLARIFY.

---

## 1. The DAG (compose points = sync barriers)

```
CP-0  confirm contract ──┐
                         ▼
      ┌──────── FOUNDATION (F1∥F2∥F3) ────────┐
      │   F1 glossary confirm   F2 helpers     │
      │   F3 FE/chat card proto                │
      └──────────────┬─────────────────────────┘
                     ▼  CP-1  foundation done
              ┌──── T1 book (full) ────┐
              └──────────┬──────────────┘
                         ▼  CP-2  book pattern established
              ┌─ T2 sync ─┐   ┌─ T3 user ─┐     (ASYNC: parallel)
              └─────┬─────┘   └─────┬──────┘
                    └──────┬────────┘
                           ▼  CP-3  book+user tools live
                  CP-4  admin contract
              ┌─ T4a glossary/admin ─┐ ┌─ T4b gateway/admin ─┐  (ASYNC)
              └──────────┬────────────┘ └─────────┬───────────┘
                         └──────┬─────────────────┘
                                ▼  CP-5  admin backend ready
                         T4c chat AdminContext
                                ▼
                         T4d cms chat panel
                                ▼  CP-6  admin end-to-end live
                         T5 cross-cutting (skill prompts, curation tests, smokes)
                                ▼  CP-7  ship
```

**Sync (blocking barriers):** CP-0, CP-1, CP-3, CP-4, CP-5, CP-6, CP-7.
**Async (parallel streams):** within Foundation (F1∥F2∥F3); T2∥T3 after CP-2; T4a∥T4b after CP-4.

---

## 2. CP-0 — Confirm contract (tiny sync, unblocks Foundation)

A 1-sitting design lock (no code) so F1/F3 can proceed in parallel. Pin:
- **Action descriptor** enum: `adopt | sync_apply | book_delete | book_set_genres | system_create | system_patch | system_delete`.
- **Confirm-token claims** (extend `mintSchemaToken`): `{ minter_identity (user_id OR admin_sub), authority_kind (grant|admin), descriptor, params_json, exp, jti }`. Single-use via a `consumed_tokens(jti)` table (the one gap vs today's rely-on-DB-unique).
- **Confirm-card payload** (what the FE frontend-tool receives): `{ confirm_token, descriptor, title, preview_rows[], destructive: bool }`. Preview is re-rendered from CURRENT state at confirm-render (§5.1 #5).
- **Confirm endpoint(s):** one `POST /v1/glossary/actions/confirm` that branches authority by `authority_kind` (grant-Manage re-check vs RS256 admin re-check).

Output: a short contract appendix appended to the spec. **Owner: human + 1 design pass.**

---

## 3. FOUNDATION (after CP-0; F1∥F2∥F3 parallel) → CP-1

Shared infra every class-C tool + surface depends on. **Build before any tier stream.** This is load-bearing/security-sensitive → human-in-loop `/loom`, `/review-impl` on F1.

| Task | Service | Files (NEW to avoid contention) | Async? |
|---|---|---|---|
| **F1 — generalized confirm** | glossary Go | `action_confirm.go` (mint/verify/consume + `confirmAction` branching authority), `consumed_tokens` migration **chain entry** (ledger!) | ∥ |
| **F2 — shared helpers** | glossary Go | `tool_helpers.go`: code→id resolvers (book/user/system scoped), base-version 409 (`content_hash`/`updated_at`), read-tool rename (`list_kinds`→`list_system_standards`, add `book_ontology_read`) | ∥ |
| **F3 — reusable confirm card** | chat-service Py + frontend TS | generalize `glossary_confirm_schema` → a generic `confirm_card` frontend tool family; FE renderer keyed on `descriptor` | ∥ (needs CP-0 payload) |

**CP-1 barrier:** confirm machinery round-trips (mint→card→confirm→effect) for ONE descriptor end-to-end (use `book_delete` as the canary), single-use enforced, base-version 409 proven, read-rename live. *Migration note:* the `consumed_tokens` table is a NEW ledger chain entry (`0030_consumed_tokens`) — do not bypass the ledger.

---

## 4. T1 BOOK (after CP-1, full) → CP-2

Built **fully and first** because it establishes the per-stream patterns (tool-file layout, confirm card, curation) that T2/T3 then copy cheaply. Human-in-loop `/loom`.

| Task | Service | Files | Notes |
|---|---|---|---|
| Book read tool | glossary | `book_tools.go` → `RegisterBookTools(srv)` | `book_ontology_read` (R) |
| Book CRUD (3 verbs × `level`) | glossary | `book_tools.go` | create/patch (W, base-version) / delete (C→`book_delete`) |
| Active-genres / kind-genres | glossary | `book_tools.go` | **delta add/remove (W)** or C-with-diff (§11 #2) |
| Entity-genres | glossary | `book_tools.go` | get (R) / set (W) |
| adopt | glossary | `book_tools.go` | **C** (`adopt`) |
| Book confirm cards | chat + FE | extend `confirm_card` family | adopt / book_delete previews (cascade enumerated, §11 #10) |
| Book-surface curation | chat-service | `frontend_tools.py` + `stream_service.py` | advertise book tools on BookContext |

**Key parallelism-enabler:** each tier registers tools in its OWN Go file via `RegisterXTools(srv)` called from `mcpHandler()` — so T1/T2/T3 don't fight over `mcp_server.go`. Same for FE cards (separate components) and curation (separate `frontend_tool_defs` branches).

**CP-2 barrier:** T1 live-smoked on a book surface (chat → adopt → confirm → ontology read → create kind → entity uses it). Pattern documented for T2/T3.

---

## 5. T2 SYNC ∥ T3 USER (after CP-2, parallel) → CP-3

Now independent — they follow the T1 pattern, separate files, no shared mutable surface beyond append-only registration. **Can run as 2 parallel background agents** (or 2 quick `/loom`s).

| Stream | Service | Files | Tools |
|---|---|---|---|
| **T2 sync** | glossary + chat + FE | `sync_tools.go`, sync confirm card | `book_sync_available` (R); `book_sync_apply` (C, §12.4 — LLM proposes per-row `Items[]`, human confirms set) |
| **T3 user** | glossary + chat | `user_tools.go`, user-surface curation | user-tier read + 3-verb×`level` (W, trash-reversible) + `user_restore` (§11 #12); identity = caller's `X-User-Id`, "your personal standards" (§11 #11) |

**CP-3 barrier:** all book+user+sync tools on `/mcp`, each live-smoked, catalog size sane (verbs collapsed). No admin work has touched the system yet — `/mcp` is feature-complete for non-admin tiers.

---

## 6. CP-4 — Admin contract (sync) → T4a ∥ T4b

Pin the admin transport before parallel backend work:
- glossary **`/mcp/admin`** endpoint + transport middleware (RS256 verify before `tools/list`).
- envelope header **`X-Admin-Token`**; gateway **downstream `/mcp/admin`** (separate catalog).
- admin confirm descriptors (`system_*`) use `authority_kind=admin` in F1's `confirmAction`.

## 7. T4 ADMIN (the high-risk phase) → CP-5 → CP-6

| Task | Service | Depends | Async |
|---|---|---|---|
| **T4a** `/mcp/admin` server + admin tools (read R, propose C) + admin confirm branch | glossary Go | F1, CP-4 | ∥ T4b |
| **T4b** gateway `/mcp/admin` downstream + `X-Admin-Token` envelope (never logged) | ai-gateway TS | CP-4 (contract only) | ∥ T4a |
| **T4c** `AdminContext` surface: list from gateway `/mcp/admin`, attach admin token, advertise admin tools+cards | chat-service Py | **CP-5** (T4a+T4b) | seq |
| **T4d** cms-frontend admin chat panel (port main-FE SSE/suspend-resume) + admin confirm cards | cms-frontend TS | T4c, F3 | seq (own mini-design) |

**CP-5 barrier:** admin backend ready — a raw MCP client with a valid admin token can list+call `/mcp/admin` via the gateway; a non-admin token gets 401 before `tools/list` (the INV-T6 leak test). **CP-6 barrier:** end-to-end admin live-smoke (cms chat → "add steampunk system genre" → confirm card → System write; non-admin chat can neither see nor reach admin tools). **`/review-impl` mandatory on T4** (auth boundary).

---

## 8. T5 CROSS-CUTTING (final compose) → CP-7

| Task | Service |
|---|---|
| Per-surface glossary skill prompts (book / user / admin variants) | chat-service |
| **Security curation tests** (INV-T4/T6): book surface ⇏ admin tools; admin surface ⇏ book tools; gateway `/mcp` catalog has zero admin tool names | chat-service + ai-gateway |
| Per-surface live-smokes (book, user, admin) + catalog-size check | all |

**CP-7:** ship — all surfaces smoked, security tests green, skill prompts teach the tiered workflow.

---

## 9. Sync vs Async summary (the user's framing)

- **SYNC tasks (sequential / barrier):** CP-0 contract · Foundation completion (CP-1) · T1 pattern (CP-2) · admin contract (CP-4) · admin backend (CP-5) · admin end-to-end (CP-6) · final integration (CP-7). These are *compose points* — cross-service contracts or integration smokes that MUST converge before downstream work is correct.
- **ASYNC tasks (parallel streams):** F1∥F2∥F3 (Foundation internals) · T2∥T3 (after CP-2) · T4a∥T4b (after CP-4). Within any glossary stream, handler+test pairs parallelize.
- **The enabler for safe async:** append-only tool registration (`RegisterXTools(srv)` per tier in its own file), separate FE card components, and separate `frontend_tool_defs` branches — so parallel streams never edit the same lines. Worktree isolation only needed if two streams must touch a shared file simultaneously (avoid by the file-split design).

---

## 10. Recommended execution

1. **CP-0 + Foundation** → one human-in-loop `/loom` (security-sensitive; `/review-impl` on F1). *Do not parallelize across agents — this is the shared spine.*
2. **T1 book** → one `/loom` (establishes the pattern). 
3. **T2 ∥ T3** → two background agents (or two short `/loom`s) once CP-2 is in; integrate + live-smoke together at CP-3.
4. **CP-4 + T4** → sequential, human-in-loop. T4a∥T4b as two tasks against the pinned contract; then T4c; then T4d (its own CLARIFY for the CMS panel). `/review-impl` at CP-6.
5. **T5** → one integration `/loom`.

Each numbered run is its own size-L `/loom`; commit at each CP. The CPs are the natural checkpoint/commit boundaries (risk seams), per the continuous-flow guidance.

## 11. Risks / ordering notes
- **Migration discipline:** F1's `consumed_tokens` is a ledger chain entry — new seed/DDL goes through `RunChain`, not a bare exec (see the migration-ledger work).
- **Catalog bloat:** keep verbs collapsed (3×level) + curation tight, or LLM tool-selection degrades (§11 #13).
- **T4d is the long pole** (greenfield CMS streaming). If schedule-bound, an interim: admin tools usable via a raw MCP client / the existing chat UI pointed at the admin token, deferring the polished CMS panel — but that's a UX deferral, not a security one (the boundary holds regardless).
- **Don't start T4 before CP-3** — the confirm machinery + patterns must be battle-tested on the low-risk tiers first.
