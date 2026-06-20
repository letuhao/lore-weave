# Spec — Glossary Assistant: Tiered MCP Tool Expansion

**Date:** 2026-06-20 · **Status:** DESIGN (spec only, no code) · **Branch (build later):** TBD
**Owning service:** `glossary-service` (tools live here per the MCP-first invariant; `ai-gateway` only federates)
**Supersedes nothing; extends** [`2026-06-10-glossary-assistant-architecture.md`](2026-06-10-glossary-assistant-architecture.md) (P0–P5 shipped) onto the tiered model from [`2026-06-19-genre-kind-attribute-tiering.md`](2026-06-19-genre-kind-attribute-tiering.md).

---

## 1. Why

The glossary was re-architected into a **tiered ontology** (System / User / Book × genre·kind·attribute) with **adopt** (copy-down), **sync** (diff/apply), per-entity genre override, a **User-tier standards library**, and an **admin System-tier** write surface driven by a separate thin **cms-frontend**. All of that is reachable over HTTP today — but the **agentic (MCP) surface still only knows the pre-tiering world**: it can read entities, propose new entities, and propose flat kinds/attributes. It cannot scaffold a book from standards, shape a book's ontology, run a sync, build a user's standards library, or touch the System tier.

**Goal:** give the AI agent *complete, tenancy-safe, human-gated control of glossary across all three tiers, including the admin System tier* — every new capability exposed as an MCP tool on `glossary-service`, federated through `ai-gateway` (MCP-first invariant), never a bespoke prompt-driven endpoint.

**Product decisions locked (2026-06-20):**
- **Spec the whole epic first** (this doc), then build phase-by-phase.
- **Admin/System control:** CMS-surface-only + admin RS256 identity + human-confirm on every System write.

---

## 2. Current agentic surface (baseline — all shipped, P0–P5)

| Tool | Tier | Gate | Surface |
|---|---|---|---|
| `glossary_search`, `glossary_get_entity`, `glossary_list_kinds` | read (entities + merged schema) | service-token + per-call `X-User-Id` + book `GrantView` | book surfaces (reader/editor/glossary page) |
| `glossary_propose_new_entity` | entity draft → inbox | `GrantEdit` | book surfaces |
| `glossary_propose_new_kind`, `glossary_propose_new_attribute` | schema propose (mint `confirm_token`, no write) | `GrantEdit` | book surfaces |
| `glossary_confirm_schema`, `glossary_propose_entity_edit` | frontend tools (suspend/resume; confirm-token / version-checked Apply) | human in browser | book surfaces |

**Envelope today** ([mcp_server.go:88-99](../../services/glossary-service/internal/api/mcp_server.go#L88)): `ai-gateway` connects as an MCP client and forwards `X-Internal-Token` (SO-1 service trust anchor) + `X-User-Id` (per-call identity — never derived from the LLM, SEC-1). Handlers read the user id from ctx and `checkGrant(book, user, View|Edit|Manage)`.

---

## 3. Target tool inventory (the gap → ~16 new tools)

Grouped by tier. **Gate column** uses three execution classes (see §5):
**R** = read (direct) · **W** = write direct (low-impact, grant-gated, reversible) · **C** = confirm-token (LLM proposes → human confirms; high-impact / destructive / shared-scope).

### 3a. Book-tier ontology (the agent helps an author set up & shape a book)

| New tool | Wraps (HTTP handler) | Identity / gate | Class |
|---|---|---|---|
| `glossary_book_ontology_read` | `getBookOntology` | `GrantView` | R |
| `glossary_adopt_standards` | `adoptBookOntology` | `GrantManage` | **C** (scaffolds a book — large, copy-down) |
| `glossary_book_create_genre` / `_kind` / `_attribute` | `createBookGenre`/`Kind`/`Attribute` | `GrantManage` | W |
| `glossary_book_patch_genre` / `_kind` / `_attribute` | `patchBook*` | `GrantManage` | W |
| `glossary_book_delete_genre` / `_kind` / `_attribute` | `deleteBook*` (soft `deprecated_at` cascade) | `GrantManage` | **C** (cascade delete) |
| `glossary_book_set_active_genres` | `setBookActiveGenres` | `GrantManage` | W (replace-set — show diff in result) |
| `glossary_book_set_kind_genres` | `setBookKindGenres` | `GrantManage` | W |
| `glossary_entity_get_genres` / `glossary_entity_set_genres` | entity_genres GET/PUT | `GrantView` / `GrantEdit` | R / W |

> Note: the create/patch/delete trio can ship as **one tool per verb with a `level: genre|kind|attribute` arg** (3 tools) rather than 9, to keep the catalog small for the LLM (H7). Spec leaves the split to PLAN; favor the 3-verb form.

### 3b. Book sync (the agent reconciles a book against its standards)

| New tool | Wraps | Gate | Class |
|---|---|---|---|
| `glossary_book_sync_available` | `getBookSyncAvailable` | `GrantView` | R |
| `glossary_book_sync_apply` | `applyBookSync` | `GrantManage` | **C** (overwrites adopted rows; per-row keep_mine/take_theirs surfaced in the confirm card) |

### 3c. User-tier standards (the agent helps a user build a reusable library)

| New tool | Wraps | Gate | Class |
|---|---|---|---|
| `glossary_user_standards_read` | `listUserKinds`/`listUserGenres`/`listUserAttributes` | per-call user id (owner-scoped; no book) | R |
| `glossary_user_create_genre` / `_kind` / `_attribute` (or 1 tool × `level`) | `createUser*` (incl. clone-from-system) | owner == caller | W |
| `glossary_user_patch_*` | `patchUser*` | owner == caller | W |
| `glossary_user_delete_*` | `deleteUser*` (soft-delete → trash) | owner == caller | W (reversible via trash; not C) |

> User-tier is **owner-scoped, not book-scoped** — the gate is "the `X-User-Id` IS the owner," no grant lookup. Trash/restore makes deletes reversible, so user-tier deletes are W not C.

### 3d. System-tier admin (CMS-surface only — the crux, §4)

| New tool | Wraps (admin HTTP handler) | Identity / gate | Class |
|---|---|---|---|
| `glossary_admin_standards_read` | `listSystemAttributes` + system genres/kinds reads | admin RS256 (`admin:write`*) | R |
| `glossary_admin_propose_genre` / `_kind` / `_attribute` (create) | `createSystemGenre`/`Kind`/`Attribute` | admin RS256 | **C** |
| `glossary_admin_propose_patch_*` | `patchSystem*` | admin RS256 | **C** |
| `glossary_admin_propose_delete_*` | `deleteSystem*` (universal/unknown un-deletable) | admin RS256 | **C** |

\* a read could use a narrower `admin:read` scope if we add one; v1 reuses `admin:write` presence as the admin signal.

**Total: ~16 logical tools** (fewer wire-tools if verbs collapse `level` args).

---

## 4. Authority & identity model (the load-bearing design)

Two distinct authority paths, by tier:

### 4a. Book + User tiers — extend the existing envelope (no new trust)
The agent acts **on behalf of the signed-in user**. Reuse today's envelope verbatim: `X-Internal-Token` (service trust) + `X-User-Id` (per-call identity). Book tools `checkGrant(book, user, View|Edit|Manage)`; user-tier tools enforce `owner == X-User-Id`. **No change to the trust model** — only new handlers. This is why phases T1–T3 are low-risk.

### 4b. System/admin tier — carry the existing RS256 admin authority through the envelope
**Do NOT invent a new admin trust path and do NOT trust `X-User-Id` alone for admin.** The HTTP admin routes already prove authority with an **RS256 admin JWT** (`contracts/adminjwt`: `Verify` + `admin:write` scope + kid/iss/aud/exp, fail-closed) — see `requireAdminScope`. The MCP admin tools reuse **exactly that**:

- The **cms-frontend** already mints an RS256 admin token via `POST /v1/admin/session` (admin-session exchange). The CMS agent surface (§6) forwards that token to `ai-gateway`, which forwards it to glossary's **admin** MCP endpoint in a new envelope header **`X-Admin-Token`**.
- glossary's admin MCP middleware calls the **same `adminjwt.Verify` + scope check** `requireAdminScope` uses. Authority = the verified RS256 token, identical to the HTTP admin surface.
- **Every System write is class C (confirm-token):** the admin tool *proposes* (mints a confirm token + preview, no write); a human admin *confirms* in the CMS (frontend tool → the token-gated write). The LLM never directly mutates the shared System tier. This keeps the LOCKED tenancy rule intact: the **human admin is the authority; the agent is their instrument**.

### 4c. PHYSICAL endpoint separation — admin MCP ≠ user MCP (INV-T6, security-critical)
Surface curation alone (the gateway/chat "just doesn't advertise" admin tools) is **not a sufficient boundary** — it relies on the federation layer never mis-curating, and even a correctly-curated user session could still leak admin internals via `tools/list`, error text, or schema introspection if the admin tools live in the same MCP server. **Admin tools therefore live on a separate MCP server mounted at a distinct endpoint, gated at the transport layer:**

- **`/mcp`** — the existing user/book MCP server. Gate: `X-Internal-Token` + `X-User-Id`. Contains **only** book + user-tier tools. An admin tool name, description, JSON-schema, or system-tier code **never appears** in this server's catalog.
- **`/mcp/admin`** — a NEW, separate MCP server. Gate (transport middleware, before any tool is listed or called): a valid RS256 `admin:write` token in `X-Admin-Token`, verified via `adminjwt.Verify`. **No valid admin token → 401 at the transport, before `tools/list`** — so a non-admin caller cannot even enumerate the admin tools, read their descriptions, or learn system-tier internals. Contains **only** admin System-tier tools.
- `ai-gateway` federates these as **two distinct upstream MCP servers**; it connects to `/mcp/admin` **only** for the CMS agent surface (and only when it holds an admin token to present). A book/reader chat's federation never dials `/mcp/admin`.

> This is the "leak internal info" defense the user flagged: separation is at the **endpoint + transport-auth** layer, not just at advertising. Three independent barriers for any System mutation: (1) you can't reach `/mcp/admin` without a verified admin token, (2) admin tools are absent from `/mcp` entirely, (3) every System write is still human-confirm-gated.

> **Tenancy check:** a regular user mutating System tier is blocked at the endpoint (no admin token → can't even list the tools), at the catalog (admin tools not on `/mcp`), and at the write (human-confirm). Defense in depth, not a single check.

---

## 5. Gating policy (when does a write need a human?)

| Class | Rule | Pattern |
|---|---|---|
| **R** read | direct; bounded output (SO-3 caps carry over); **inherits the caller-scoped visibility of the wrapped HTTP handler** (never raw queries — see §11 #3) | return data |
| **W** write-direct | low-impact, **reversible** (trash / soft-delete), grant- or owner-gated; **additive only** | execute + report real outcome (H6) |
| **C** confirm-token | high-impact (adopt/scaffold), destructive (cascade delete, sync overwrite), **set-replace** (active-genres / kind-genres — see §11 #2), or **any** System-tier write | mint `confirm_token` + preview (no write) → human confirms via a frontend tool → token-gated HTTP write (the generalized confirm machinery, §6.5 + the contract below) |

Rationale: mirror the shipped P4 schema pattern. The agent gets *broad reach* (it can do everything) but *high-impact, destructive, set-replacing, and shared-scope writes always pause for a human* — which is also what keeps "agent controls admin" safe. Note **set-replace operations are class C, not W**: an LLM emitting a bare replace-set silently drops omitted members (§11 #2), so either expose them as delta `add`/`remove` (W) or require a human-confirmed before/after diff (C).

### 5.1 Confirm-token contract (binding for every class-C action)
A `confirm_token` is an opaque, server-minted capability — NOT a snapshot the human rubber-stamps. It MUST:
1. **Be single-use** — consumed atomically at confirm; a replay is rejected (C2).
2. **Expire** — short TTL (carry P4's value); an expired token fails closed.
3. **Bind to the minting identity AND scope** — a user token can only be confirmed by that user; an admin (`/mcp/admin`) action can only be confirmed by a caller holding the same `admin:write` authority (C3). The confirm endpoint re-checks authority, never trusts the token alone.
4. **Re-validate the action at confirm time, not mint time** (C1) — the world may have changed between propose and confirm (the System genre was deleted, the book already adopted it, the target row was edited). Confirm MUST re-run the same validation the direct write would (existence, FK, un-deletable guards, and — for edits — an optimistic-concurrency check, §11 #6). On drift it fails with a clear, re-proposable error rather than applying stale intent.
5. **Carry an action descriptor** (`adopt` | `sync_apply` | `book_delete` | `system_create|patch|delete` | …) so one mint/confirm path serves all class-C tools, and the preview the human sees is generated from the *current* state at confirm render (not mint).

---

## 6. Architecture changes (beyond new handlers)

1. **Glossary: two MCP servers, two endpoints (INV-T6, §4c)** — keep `/mcp` (user/book; gate `X-Internal-Token` + `X-User-Id`) and add a **separate** `/mcp/admin` server (gate: RS256 `X-Admin-Token` verified at the transport middleware *before* `tools/list`). Admin tools registered ONLY on the admin server; book/user tools ONLY on `/mcp`. No shared catalog. Refactor `requireAdminScope`'s verify into a ctx-based helper reused by the HTTP admin routes and the `/mcp/admin` middleware (mirrors the `mcpIdentityMiddleware` pattern at [mcp_server.go:88](../../services/glossary-service/internal/api/mcp_server.go#L88)).
2. **`ai-gateway`: separation must be END-TO-END, not just two upstreams (corrected after the deep-dive).** The gateway federates by *tool name into one unified catalog* ([catalog.ts](../../services/ai-gateway/src/federation/catalog.ts), routing at [federation.service.ts:111](../../services/ai-gateway/src/federation/federation.service.ts#L111)) and does **no** per-surface/per-caller gating. So merely adding `/mcp/admin` as a 2nd upstream would put admin tool **names** into the single catalog every surface lists — an INV-T6 leak. Instead the gateway exposes **two downstream MCP endpoints**: its existing `/mcp` (federates glossary `/mcp` + knowledge) and a **new gateway `/mcp/admin`** (federates glossary `/mcp/admin` only, forwards `X-Admin-Token`). Two catalogs, never blended. Add `X-Admin-Token` to the envelope: `Envelope` iface + `extractEnvelope` ([handlers.ts:14](../../services/ai-gateway/src/mcp/handlers.ts#L14)) + forward in [federation.service.ts:115-118](../../services/ai-gateway/src/federation/federation.service.ts#L115). Stateless per-call; token never cached, never logged ([handlers.ts:44](../../services/ai-gateway/src/mcp/handlers.ts#L44) only logs *absence* of userId — keep that).
3. **`chat-service`: the surface→endpoint map is the enforcement point.** Surfaces are implicit context objects, not an enum ([models.py:127-150](../../services/chat-service/app/models.py#L127)); tool curation is `frontend_tool_defs(editor, book_scoped)` ([frontend_tools.py:222](../../services/chat-service/app/services/frontend_tools.py#L222)); the MCP tool-def fetch + envelope is in the gateway client ([knowledge_client.py:349,408](../../services/chat-service/app/client/knowledge_client.py#L349)). Add an **`AdminContext`** surface that (a) lists tools from gateway **`/mcp/admin`** (not `/mcp`), (b) attaches `X-Admin-Token`, (c) advertises only admin tools + the admin confirm cards. A book/reader surface lists from `/mcp` only and never holds an admin token — so it can neither see nor reach admin tools. This per-surface base-URL+token choice is where INV-T4/T6 are actually enforced; **it is covered by a test** (§11 #4).
4. **CMS agent surface (new sub-scope)** — the thin cms-frontend currently has no chat/assistant panel. A minimal admin-assistant surface (chat panel → chat-service/ai-gateway with the admin identity) is a **dependency for phase T4**. Could be a thin reuse of the existing chat UI scoped to admin tools. Flag for its own design at T4 PLAN.
5. **Generalized confirm-token machinery** — today `schema/confirm` is schema-specific. Generalize it to carry an opaque action descriptor (`adopt`, `sync_apply`, `book_delete`, `system_create|patch|delete`) so all class-C tools share one mint/confirm path, honouring the §5.1 contract. (Or per-action endpoints — PLAN decides.)
6. **Contracts** — the MCP tools are not OpenAPI (MCP catalog), but the new confirm endpoints + any new HTTP are contract-first.
7. **Credential hygiene** — `X-Admin-Token` is a bearer credential. It MUST NOT be logged in the gateway, chat-service, glossary middleware, or any envelope dump (redact like other secrets). The federation path that forwards it is the only place it travels (§11 #7).
8. **Code-based addressing** — new tools take human-stable **codes** (`kind_code`, `genre_code`) and resolve to IDs server-side wherever the wrapped handler allows, mirroring `propose_new_entity`. UUID-only args invite LLM transposition errors (§11 #9). IDs are accepted only where no stable code exists.

---

## 7. Invariants (carried + new)

Carried from the P0–P5 spec: SEC-1 (identity never from LLM), INV-7 (per-call identity), H4 (ownership fail-closed), H13 (uniform not-found/not-owner — no existence oracle), H6 (truthful resume outcome), H7 (per-surface tool curation), SO-3 (read-output caps).

New for this epic:
- **INV-T1 — MCP-first:** every capability here is an MCP tool on glossary-service; no bespoke prompt endpoint. Federated via ai-gateway.
- **INV-T2 — admin authority = RS256, never `X-User-Id`:** an admin tool MUST verify an RS256 `admin:write` token (same as the HTTP admin routes). `X-User-Id` alone is never sufficient for a System write.
- **INV-T3 — System writes are always human-confirmed:** no MCP tool directly mutates System tier; it proposes a confirm-token only.
- **INV-T4 — surface curation is a security boundary, not a UX nicety:** admin tools are advertised on the CMS surface only; a book/reader chat must never receive them. (Second layer behind INV-T6.)
- **INV-T5 — tenancy preserved:** book tools grant-gated; user tools owner-scoped; system tools admin-gated. No tool lets tier A's caller affect tier B's data without the proper authority.
- **INV-T6 — admin MCP is a physically separate endpoint (`/mcp/admin`), transport-gated by the RS256 admin token (§4c):** admin tool names/descriptions/schemas + system-tier internals are NEVER present in the user/book `/mcp` catalog, and a caller without a verified admin token cannot even `tools/list` them. Prevents internal-info leakage to non-admin sessions. This is the primary admin boundary; INV-T4 (curation) + INV-T3 (human-confirm) are defense-in-depth behind it.

---

## 8. Phasing (each ≈ L, its own `/loom`)

| Phase | Scope | Risk | Authority |
|---|---|---|---|
| **T1 — Book ontology tools** | read + create/patch (W) + delete/adopt (C) + active-genres/kind-genres + entity-genres | low (existing envelope) | user id + grant |
| **T2 — Book sync tools** | sync_available (R) + sync_apply (C) | low–med | user id + grant |
| **T3 — User-tier standards tools** | read + CRUD (W, trash-reversible) | low | owner == caller |
| **T4 — Admin/System tools + CMS agent surface** | NEW `/mcp/admin` server (transport-gated by RS256, §4c/INV-T6); admin read (R) + propose create/patch/delete (C); envelope `X-Admin-Token`; gateway federates it as a 2nd upstream for the CMS surface only; CMS chat panel | **high** | RS256 admin + separate endpoint + human-confirm |
| **T5 — Cross-cutting** | generalize confirm-token machinery; glossary skill prompt updates (teach the tiered workflow); per-surface curation; live-smoke each surface | med | — |

Build order T1→T2→T3 first (compounding value, no authority risk), then the envelope/confirm generalization (parts of T5), then T4 last. Each phase: VERIFY with unit tests + a live cross-service smoke (gateway → glossary MCP), 2-stage REVIEW, `/review-impl` on T4 (auth boundary).

---

## 9. Open decisions

Most were **resolved in the 2026-06-20 deep-dive (§12)**. Remaining truly-open items are deferred to the owning phase's CLARIFY:

1. **Verb-collapsing:** one tool per (verb × level) = 9 book tools, vs 3 tools with a `level` arg. *Resolved (§12.8): 3-verb form.* — confirm at PLAN.
2. **Generalized vs per-action confirm endpoints** (§6.5). *Resolved (§12.5): one generalized mint/confirm path that branches on the action descriptor's authority.* — shape at T1 PLAN.
3. **CMS agent surface shape** (§6.4). *Resolved (§12.1): a chat panel in cms-frontend reusing the main FE's streaming infra.* — detail at T4.
4. **`admin:read` scope:** narrower read scope vs reuse `admin:write` presence. *Lean: reuse for v1.* — still open, T4.
5. **User-tier agent surface** placement. *Resolved (§12.3): book surfaces expose the caller's user-tier tools; a dedicated "my standards" surface is optional later.* — T3.
6. **Adopt as C vs W.** *Resolved (§12.7): **C** (confirm-token).*

## 10. Out of scope
- P6 grounding consolidation (already deferred, separate).
- Knowledge-service / wiki agent tools (separate domains).
- Any change to the tiered HTTP/DB model itself — it is complete; this epic only adds the agent layer over it.

---

## 11. Edge cases & hardening (from the 2026-06-20 spec stress-test)

Adversarial walkthrough of every tier (happy + edge). Severity: 🔴 must-fix-in-design · ⚠️ resolve-at-phase · ▫ ergonomic. Each maps to a scenario id from the review.

**🔴 Must specify before building:**
1. **Confirm-token is a capability, not a snapshot** (C1/C2/C3) → §5.1 contract: single-use, expiring, identity+scope-bound, **re-validated at confirm time**. Without this, a token minted against stale state applies wrong/vanished intent, or a non-admin confirms an admin action. *The keystone edge case.*
2. **Set-replace is class C, never a bare W PUT** (B4) → an LLM emitting `set_active_genres:[romance]` silently drops `fantasy`. Expose set-replace ops (`active-genres`, `kind-genres`, book/user kind↔genre) as **delta `add`/`remove`** (W) OR as a human-confirmed before/after diff (C). Reflected in §3a/§5.
3. **Read tools inherit the wrapped handler's caller-scoped visibility** (C5) → must call the same scoped query path the HTTP handler uses (e.g. the `D-GKA-SYNC-USER-SOURCE-VISIBILITY` caller-scoping of user-tier `source_ref`), never raw SQL — else a grantee's read leaks the owner's `user:<uuid>` provenance. A per-tool test asserts the scoping.
4. **CMS surface federates `/mcp/admin` ONLY, never `/mcp`** (E17) → enforced in chat-service config **and covered by a test** (a CMS session must not receive book/user tools; a book session must not receive admin tools). Curation drift is a security regression, so it is tested, not trusted.

**⚠️ Resolve at the owning phase:**
5. **Admin-token lifecycle in long conversations** (A5/T4) → an admin token expires (15m TTL) mid-session; the `/mcp/admin` transport 401s. Define the refresh: chat-service re-exchanges via `/v1/admin/session` on 401 (same pattern the CMS HTTP client uses), transparent to the turn.
6. **Optimistic concurrency on ontology/system edits** (B6/A-concurrent/T1/T4) → patch tools (book + system) take a base-version/`content_hash` and 409 on drift (the H5 lesson), or we consciously accept last-write-wins and document it per-tool. System-tier especially (concurrent admins; `content_hash` feeds Sync).
7. **Never log `X-Admin-Token`** (C4) → §6.7; redact in every hop (gateway, chat-service, glossary middleware, envelope dumps).
8. **Mint-time validation for doomed proposals** (A3) → propose tools reject clearly-invalid actions up front (un-deletable `universal`/`unknown`, already-exists) so the agent never presents a confirm card destined to 4xx. (Confirm-time re-validation per #1 still runs — this is just earlier, friendlier failure.)

**▫ Ergonomic / clarity:**
9. **Code-based addressing over UUIDs** (B3) → §6.8.
10. **Cascade-delete previews enumerate the blast radius** (B5) → the `book_delete_*` confirm card lists the attrs / active-genre / kind-genre / entity_genres rows the soft-delete cascade will deprecate.
11. **User-tier identity in a shared book is the caller's** (U3) → a grantee's user-tier tools act on the **grantee's own** library (their `X-User-Id`), not the book owner's; tool descriptions say "your personal standards" to avoid the "whose standards?" confusion. (Adopt/book context still uses the owner's tier — that's the book layer, not the user layer.)
12. **User-tier restore/trash tools** (U2) → either add `glossary_user_restore_*` (so the agent can undo its own soft-delete) or state in the delete tool's description that restore is human-only via the standards UI. Lean: add restore (cheap, symmetric).
13. **Catalog-size discipline** (E26) → reinforces collapsing create/patch/delete to `(verb × level-arg)` (3 tools, not 9) and tight per-surface curation (H7); keep each surface's advertised catalog small so tool-selection stays accurate.

**Validated as already-sound by the stress-test:** the two-endpoint admin separation (A2 — 401 before `tools/list`, no leak), human-confirm as the prompt-injection backstop (A4), and the three-class gating model all held under adversarial scenarios. The gaps above are detail-level, not architectural.

---

## 12. Resolved design questions (deep-dive 2026-06-20)

Each was an *unflagged* ambiguity a builder would trip on. Resolved against the actual code, with anchors.

### 12.1 / 12.2 / 12.5 — The admin/CMS delivery path (the riskiest cluster), now concrete
The investigation found the gateway has **no per-surface gating** and federates by tool-name into **one unified catalog**. So the admin boundary cannot live at the gateway's routing — it must be **endpoint separation end-to-end** + **chat-service surface routing** + **glossary transport gate**. The full path:

```
cms-frontend (admin RS256 in `cms_auth` localStorage)
  → chat-service  [NEW AdminContext surface]
        · lists tool-defs from gateway **/mcp/admin** (not /mcp)
        · attaches X-Admin-Token (from the request's admin bearer)
        · advertises only admin tools + admin confirm cards
  → ai-gateway  [NEW downstream **/mcp/admin** endpoint]
        · federates glossary **/mcp/admin** ONLY (separate catalog; admin tool
          names never appear in the /mcp catalog the book surfaces list)
        · forwards X-Admin-Token; never logs it
  → glossary-service **/mcp/admin** MCP server
        · transport middleware verifies RS256 admin token + admin:write BEFORE tools/list
        · admin tools mint confirm-tokens only (no direct System write)
```

- **CMS surface shape (12.1):** a chat panel **in cms-frontend**. cms-frontend today is pure CRUD with **no streaming** ([cms-frontend/src/api.ts](../../cms-frontend/src/api.ts)); the main FE has reusable SSE infra (`frontend/src/features/chat/useChatMessages.ts`, the `x-loreweave-stream-format: agui` + suspend/resume protocol). T4 ports a minimal version of that, keyed to the `cms_auth` admin token. **Greenfield-but-reuse**, scoped at T4.
- **Surface→endpoint map (12.2):** the *enforcement point*. chat-service picks the gateway base (`/mcp` vs `/mcp/admin`) and whether to attach `X-Admin-Token` **by surface**. Add `AdminContext` to [models.py:143](../../services/chat-service/app/models.py#L143); branch the tool-def fetch + envelope build in [knowledge_client.py:349,408](../../services/chat-service/app/client/knowledge_client.py#L349).
- **Confirm endpoints (12.5):** generalize the existing `mintSchemaToken`/`confirmSchema` ([schema_confirm_handler.go:125,149](../../services/glossary-service/internal/api/schema_confirm_handler.go#L125)) into one mint + one confirm path carrying an **action descriptor**. The confirm endpoint **branches authority by descriptor**: user-grant actions (adopt/sync/book-delete) re-check `GrantManage` like `confirmSchema` does today; System actions re-check the **RS256 admin token + admin:write** (a *distinct* admin-gated confirm, since System writes have no book/grant). The admin confirm card is a new frontend tool in the admin surface's `FRONTEND_TOOL_NAMES`.

### 12.3 — Old vs new read tools (no overlap; complementary)
Keep both, with clear, distinct roles (and rename for the LLM):
- **`glossary_list_system_standards`** (retarget of today's `glossary_list_kinds`) → "what CAN I adopt": the System (+ caller's User) standards catalogue. Used **before** adopt.
- **`glossary_book_ontology_read`** (new) → "what does THIS book have": the book-local genres/kinds/attributes. The canonical schema read for in-book work; what `propose_new_entity` already resolves against via `loadKindMap(bookID)`.
Today's `glossary_list_kinds` takes no `book_id` and returns a global/merged view — *misleading* for a book assistant post-tiering. Retarget it to the standards-browse role; `book_ontology_read` owns the in-book read.

### 12.4 — Sync: the LLM proposes per-row choices, the human confirms the set
`applyBookSync` already takes `Items[]{entity, id, choice: keep_mine|take_theirs}` ([book_sync_handler.go:251](../../services/glossary-service/internal/api/book_sync_handler.go#L251)). So: `glossary_book_sync_apply` reads the diff (`sync_available`), the **LLM proposes** a per-row choice set (it has the context to recommend), mints a confirm-token carrying the proposed `Items[]`; the **human reviews the full diff + the proposed choices in the confirm card and may flip any row before confirming**. Input shape = the proposed `Items[]`; authority = `GrantManage`, re-checked at confirm.

### 12.6 — Optimistic concurrency: yes, carry a base version (decided, not deferred)
Patch tools **take a base version and 409 on drift** (the H5 lesson) — this is decided now because it fixes the tool *signature*. Reuse what exists: genres/attributes already carry **`content_hash`** → the tool passes `base_content_hash`, handler 409s if the live row's hash differs. Kinds have no hash → use **`updated_at`** as the concurrency token. Same for System-tier admin patches (concurrent admins; the `content_hash` also feeds Sync, so a blind overwrite would corrupt drift detection).

### 12.7 — `adopt` is class **C** (confirm-token)
Non-destructive but high-impact and visible (scaffolds the book by copy-down). The confirm card previews what will be adopted (which genres/kinds/attributes, and — re-rendered at confirm time — how many are *new* vs already present, since adopt is idempotent). Resolves the §3a↔§9 contradiction in favour of C.

### 12.8 — Tool shape: 3 verbs × `level` arg (not 9), code-addressed
Create/patch/delete collapse to `glossary_book_create|patch|delete` with a `level: genre|kind|attribute` arg (and the same for user-tier), keeping the catalogue small (H7, §11 #13). Args are **codes** (`kind_code`, `genre_code`) resolved server-side, not UUIDs (§6.8, §11 #9) — except where no stable code exists (entity ids).

### 12.9 — Services touched per phase (scope is NOT glossary-only)
| Phase | glossary (Go) | chat-service (Py) | ai-gateway (TS) | frontend (TS) | cms-frontend (TS) |
|---|---|---|---|---|---|
| **T1 book** | MCP tools on `/mcp` + generalized confirm mint/confirm | book-surface curation + adopt/book-delete confirm cards | — (same `/mcp`) | confirm-card renderers | — |
| **T2 sync** | sync tools + confirm | sync-apply confirm card | — | confirm-card renderer | — |
| **T3 user** | user-tier tools (+ restore) | user-tier tools on book surface | — | (minor) | — |
| **T4 admin** | **NEW `/mcp/admin` server** + admin tools + admin confirm + admin-gated confirm endpoint | **NEW AdminContext surface** + admin token wiring + admin confirm cards | **NEW `/mcp/admin` downstream** + `X-Admin-Token` envelope | — | **NEW admin chat panel** (port main-FE SSE infra) + admin confirm cards |
| **T5 cross-cutting** | — | glossary skill prompt per-surface + curation tests | — | — | — |

Auth-service: **no change** — admin tools reuse the shipped `/v1/admin/session` RS256 exchange. The "single-service" framing in earlier phase tables applies only to T1–T3's *backend*; the FE/chat surfaces are always part of the phase.
