# MCP Fan-Out — Detailed Design & Parallel Execution Plan

- **Date:** 2026-06-20
- **Spec:** [`docs/specs/2026-06-20-mcp-fanout-agent-universal-control.md`](../specs/2026-06-20-mcp-fanout-agent-universal-control.md) (Parts I–IV — all OD-* resolved)
- **Purpose:** Turn the resolved spec into (a) **detailed design** at the interface altitude and (b) a **parallel execution plan** — provably-disjoint slices fanned out as worktree sub-agents, reconciled at defined **compose points**, with human junctions.
- **Execution model:** `/warp`-style. Slices below are disjoint by **owned directory**; they meet only at **frozen contracts** (§3) and **compose points** (§6). An agent never edits a directory another slice owns.
- **Review status:** a 3-lens adversarial review (2026-06-20) is **fully applied in-body** below; §10 is the changelog. Result: **10 slices** (S-JOBS added), `frontend_tools.py` sole-owned by S-CONSUMER, all dropped numbers re-pinned, all orphan holes assigned.

---

## 1. Parallelization model at a glance

```
WAVE 1 — FOUNDATION (6 slices, fully parallel; share only §3 contracts)
  S-KIT-GO    sdks/go/loreweave_mcp/        Go MCP kit (identity mw, 3 scope guards, tier+confirm helpers)  ← critical path
  S-KIT-PY    sdks/python/loreweave_mcp/    Python MCP kit (same surface)                                   ← critical path
  S-CONSUMER  services/chat-service/        find_tools + per-iter curation + iteration budget + H7 cap
                                            + generic confirm/propose generalization + ui_* advertising (SOLE owner of frontend_tools.py)
  S-GATEWAY   services/ai-gateway/          env-driven provider registry + prefix enforcement + partial-catalog flag (H10)
  S-FE        frontend/                     ui_* executors + confirm card (incl. N-item batch, H2) + diff card + activity/Undo strip
  S-JOBS      services/jobs-service/        Py MCP server (jobs_list/summary/get reads) via S-KIT-PY
                       │
            ╞════ COMPOSE POINT A ════╡  contracts realized · kits published · consumer↔FE round-trip smoked
                       │                   (HUMAN JUNCTION 1 — review foundation)
                       ▼
WAVE 2 — PROVIDERS (4 slices, fully parallel; each depends on ONE kit)
  S-BOOK      services/book-service/        Go MCP server (R/A/W) via S-KIT-GO + verifyBookOwner
  S-COMPOSE   services/composition-service/ Py MCP server (R/A; publish=W) via S-KIT-PY
  S-TRANSL    services/translation-service/ Py MCP server + NEW cost-estimate (HIGH#1) + job_control (forwards) + re-price (H14)
  S-SETTINGS  services/{auth,provider-registry}/ Go MCP server (user-scoped) via S-KIT-GO + secret redaction
                       │
            ╞════ COMPOSE POINT B ════╡  integrator federates 4 providers (env) · per-provider live-smoke
                       │                   (HUMAN JUNCTION 2 — all providers working)
                       ▼
WAVE 3 — ORCHESTRATION (1 slice, serial)
  S-WORKFLOW  chat-service skill prompt    cross-service ordering ("import→translate→glossary→wiki")
                       │
            ╞════ COMPOSE POINT C ════╡  end-to-end lazy-user scenarios green (HUMAN JUNCTION 3 — ship)
```

**Why this is safe to parallelize:** every slice owns a distinct directory tree (disjoint file sets → no merge conflicts in worktrees). The only cross-slice coupling is the **contracts in §3**, which are frozen *before* Wave 1 starts. Two would-be shared files are explicitly de-conflicted: (1) `ai-gateway/src/config/config.ts` provider array → S-GATEWAY makes it **env-driven** (§3 C-GW) so providers self-register via env at compose points, not code edits; (2) `chat-service/.../frontend_tools.py` (the only file both a consumer and an FE concern want) → **S-CONSUMER is its sole owner** (defines all frontend-tool schemas), and S-FE **only renders** — it never edits chat-service.

---

## 2. Dependency matrix

| Slice | Owns (dir) | Hard deps (must exist first) | Contracts it **produces** | Contracts it **consumes** |
|---|---|---|---|---|
| S-CONSUMER | `services/chat-service/` (incl. **sole** owner of `frontend_tools.py`) | — | C-FT, C-NAV, C-CONFIRM, C-PROPOSE (advertiser side: all frontend-tool schemas) | C-ACTIVITY, C-NAV (renderer side from S-FE) |
| S-GATEWAY | `services/ai-gateway/` | — | C-GW (env registry + prefix rule + partial-catalog flag) | C-TOOL (prefix map) |
| S-KIT-GO | `sdks/go/loreweave_mcp/` (new) | — | C-KIT-GO, C-TOOL (Go) | — |
| S-KIT-PY | `sdks/python/loreweave_mcp/` (new) | — | C-KIT-PY, C-TOOL (Py) | — |
| S-FE | `frontend/` (**never** edits chat-service) | — | C-NAV, C-CONFIRM, C-PROPOSE, C-ACTIVITY (renderer side) | C-* schemas from S-CONSUMER (read-only) |
| S-JOBS | `services/jobs-service/` | **S-KIT-PY** | jobs read tools (`jobs_list/summary/get`) | C-KIT-PY, C-TOOL |
| S-BOOK | `services/book-service/` | **S-KIT-GO** | book tool catalog + `/v1/book/actions/*` | C-KIT-GO, C-TOOL, C-CONFIRM/C-PROPOSE descriptors |
| S-COMPOSE | `services/composition-service/` | **S-KIT-PY** | composition tool catalog + `/v1/composition/actions/*` | C-KIT-PY, C-TOOL |
| S-TRANSL | `services/translation-service/` | **S-KIT-PY** | translation catalog + estimate API + `job_control` (forwards to existing control routers) | C-KIT-PY, C-TOOL |
| S-SETTINGS | `services/auth-service/`, `services/provider-registry-service/` | **S-KIT-GO** | settings tool catalog + `/v1/settings/actions/*` | C-KIT-GO (user-scope guard), C-TOOL |
| S-WORKFLOW | `services/chat-service/` (system-prompt fragment only — coordinate with S-CONSUMER; Wave 3 so no overlap) | Wave 2 federated | workflow skill | all catalogs |

**Critical-path note:** S-KIT-GO and S-KIT-PY are on the critical path (block Wave 2 **and** S-JOBS). They are the **smallest** slices — *mostly* extraction of proven glossary/knowledge patterns (identity-mw, BookOwnerGuard, confirm-token), with `UserScopeGuard`/`ProjectGuard` built fresh (no existing instance) — so schedule them to finish first within Wave 1.

---

## 3. FROZEN CONTRACTS (the load-bearing part — pin before Wave 1)

These are the interfaces where disjoint slices meet. **Changing one after Wave 1 starts forces a re-sync** — so they are frozen here. Each is generalized from a proven existing shape (cited).

### C-FT — `find_tools` meta-tool (consumer-local, S-CONSUMER)
Lives **in chat-service**, not federated (operates on the catalog chat already caches via `get_tool_definitions()`; carries no user-data envelope → no ownership guard).

```jsonc
// advertised on the universal /chat surface as part of the always-on core
{ "name": "find_tools",
  "description": "Find tools that can perform an intent. Call this FIRST when the user asks for something you don't already have a tool advertised for. Returns matching tool names + descriptions; the matched tools become callable on your next step.",
  "parameters": { "type":"object",
    "properties": { "intent": {"type":"string"}, "limit": {"type":"integer","default":8} },
    "required": ["intent"], "additionalProperties": false } }
```
- **Return:** `{ "tools": [ {"name": "...", "description": "..."} ] }` — names+descriptions only (not full schemas).
- **Loop semantics (S-CONSUMER):** chat keeps a per-turn `active_tool_names: set`. A `find_tools` result **unions matched names into `active_tool_names`**; the NEXT pass advertises `{always-on core} ∪ {full schemas of active_tool_names}`. Search = in-memory fuzzy over the cached catalog's `name` + `description` **+ `synonyms`** (from C-TOOL metadata; rapidfuzz or token-overlap; no embeddings in v1).
- **Recall + escalation (H6):** on a **low-confidence / empty** result, the agent may **escalate once** to the full curated surface group rather than denying — a false "I can't" on a covered capability is the headline failure (spec QA1).
- **Missing vs. unavailable (H10):** `find_tools` distinguishes "no such tool" from "owning provider is in the **partial catalog** (temporarily unavailable)" using the gateway availability flag (C-GW); for the latter the agent says **"try again,"** never "I can't."
- **Budget (H9):** `find_tools` calls and Tier-R reads do **not** count against the `/chat` iteration cap (=20). Implemented as: only passes that execute a Tier-A/W tool decrement the write-budget.
- **Always-on core** (advertised every `/chat` turn, ≤8): `find_tools`, `ui_navigate`, `ui_open_book`, `ui_show_panel`, `ui_watch_job`, `propose_edit`, `propose_record_edit`, `confirm_action`. (Domain reads/writes are discovered via `find_tools`.)

### C-NAV — navigation/render frontend tools (advertiser S-CONSUMER, executor S-FE)
Frontend tools (suspend→browser), but **resolve-immediately** (no Apply needed). Only advertised when `stream_format=="agui"` (F2 capability handshake — `legacy` clients never see them, so no suspend/hang).

| Tool | params | FE effect | resume payload |
|---|---|---|---|
| `ui_navigate` | `{path: string}` | `router.push(path)` (allowlisted route prefixes) | `{navigated: true\|false}` |
| `ui_open_book` | `{book_id, tab?: "overview\|translation\|glossary\|enrichment\|wiki\|settings"}` | open `/books/:id?tab=` | `{opened: bool}` |
| `ui_open_chapter` | `{book_id, chapter_id, mode: "edit\|read"}` | open editor/reader | `{opened: bool}` |
| `ui_show_panel` | `{panel: string, args?: object}` | open a tab/panel on the current view | `{shown: bool}` |
| `ui_watch_job` | `{job_id}` | open `/jobs?focus=job_id` (live SSE) | `{watching: bool}` |

`FRONTEND_TOOL_NAMES` (chat-service) gains these. The resume path reuses the existing suspend/resume; for nav the FE POSTs the resolve immediately (no human gate).

### C-CONFIRM — generic `confirm_action` (generalize `glossary_confirm_action`)
**Today** [`frontend_tools.py:183`] `glossary_confirm_action(confirm_token, descriptor, title)` POSTs to the glossary-only `/v1/glossary/actions/confirm`. **Generalize** so the *descriptor namespace* selects the committing endpoint:

```jsonc
{ "name": "confirm_action",
  "parameters": { "type":"object", "properties": {
     "confirm_token": {"type":"string"},
     "descriptor":    {"type":"string"},   // e.g. "glossary.book_delete", "book.publish_batch", "translation.start_job"
     "title":         {"type":"string"},
     "domain":        {"type":"string"},    // "glossary"|"book"|"translation"|"settings" — selects the confirm endpoint
     "items":         {"type":"array"}      // H2: OPTIONAL — N rows for a BATCH confirm (one card, single Apply), e.g. publish_batch
  }, "required": ["confirm_token","descriptor","title","domain"], "additionalProperties": false } }
```
- **Outcome enum (carry from glossary):** `action_done | token_expired | action_error | cancelled`. Agent claims success ONLY on `action_done`.
- **Batch confirm (H2):** when `items` is present (e.g. descriptor `book.publish_batch`), the FE renders **one** card listing the N rows with a **single Apply** (or per-row checkboxes) — never N separate cards. This is what keeps "publish all my drafts" from defeating the lazy-man goal.
- **Confirm endpoint map (FE, S-FE):** `domain → POST /v1/<domain>/actions/confirm` (token-gated; uniform shape `{confirm_token}` → executes the bound payload). Preview: `GET /v1/<domain>/actions/preview?token=`. **These routes are NET-NEW per provider** — only glossary has them today; each Tier-W/S provider slice wires its own pair using the kit's `MintConfirmToken/VerifyConfirmToken`.
- **Provider obligation (INV-9, every Tier-S/W provider):** the propose tool **mints** a `confirm_token` (bound to user+resource+payload+expiry) and returns `{confirm_token, descriptor, title}`; the confirm route is the **only** write path; it refuses an expired/forged token. This is the glossary class-C spine, applied per service.

### C-PROPOSE — generic propose/diff frontend tools (generalize `propose_edit` + `glossary_propose_entity_edit`)
Two reusable shapes; the FE renders by tool name (H15):
- **`propose_edit`** — prose insert/replace (UNCHANGED; editor surface). [`frontend_tools.py:39`]
- **`propose_record_edit`** — *generalized diff card* for "edit fields of an existing record," generalizing `glossary_propose_entity_edit`:
```jsonc
{ "name":"propose_record_edit",
  "parameters": { "type":"object", "properties": {
     "domain":      {"type":"string"},   // "glossary"|"book"|...
     "resource_ref":{"type":"object"},    // domain-specific ids, e.g. {book_id, entity_id} or {book_id, chapter_id}
     "base_version":{"type":"string"},    // optimistic concurrency token (H8)
     "changes":     {"type":"array","items": {"type":"object","properties": {
         "field_label":{"type":"string"}, "old_value":{"type":"string"}, "new_value":{"type":"string"},
         "target":{"type":"string"}, "target_ref":{"type":"string"} }, /* required: field_label,old_value,new_value,target */ }},
     "rationale":   {"type":"string"}
  }, "required": ["domain","resource_ref","base_version","changes"] } }
```
- **Outcome enum:** `applied_saved | applied_conflict | applied_error | dismissed` (carry from glossary). On Apply the FE issues the domain's version-checked PATCH (`If-Match: base_version` → 409/412 on drift).
- **v1 note:** glossary keeps its existing `glossary_propose_entity_edit` (other branch owns it); `propose_record_edit` is for **book/composition** record edits. They can coexist or glossary migrates later (not a v1 dependency).

### C-ACTIVITY — Tier-A visibility + Undo (H16, renderer S-FE; emitter S-CONSUMER)
Every **auto-applied (Tier-A)** tool result streams an activity event the FE renders as a strip in chat:
```jsonc
{ "activity": { "op": "chapter.create", "summary": "Created draft chapter 'Chapter 5'",
                "undo": { "available": true, "tool": "chapter_delete", "args": {"book_id":"…","chapter_id":"…"} } } }
```
- `undo.available=false` when the op has no reverse. Clicking Undo issues the named reverse tool (trash/restore, `restoreRevision`, set-back).
- Emitted by S-CONSUMER when a tool's definition is tagged `tier:"A"` (C-TOOL) and returns an `undo_hint`. **The `undo_hint` in a Tier-A tool result is NET-NEW per provider** (glossary has no Tier-A): each Tier-A handler in S-BOOK/S-COMPOSE/S-TRANSL emits `_meta.undo_hint = {tool, args}` (reverse ops verified to exist — book: trash/restore, `restoreRevision`).

### C-TOOL — per-tool definition convention (kits enforce; S-KIT-*)
Every tool's MCP definition carries machine-readable metadata so consumer + gateway + FE behave correctly without hardcoding tool names:
- **Name** MUST be `<provider_prefix>_<verb>` (prefix map in C-GW).
- **`_meta.tier`** ∈ `R|A|W|S` (drives auto-apply vs confirm; consumer reads it).
- **`_meta.scope`** ∈ `book|project|user|none` (drives which kit guard runs).
- **`_meta.undo_hint`** (optional) — `{tool, args_template}` for C-ACTIVITY.
- **`_meta.synonyms`** (optional) — alias terms feeding `find_tools` recall (H6).
- Arg models: `extra="forbid"` (Py) / strict struct decode (Go); **identity/scope ids (user_id/session) are NEVER tool args** — they come from the envelope.
- **Enforcement is NET-NEW in the kits:** S-KIT-GO/PY **reject** a tool registered without `tier`+`scope`. (Legacy glossary/knowledge tools predate `_meta` and are exempt; only kit-registered providers must carry it.)

### C-GW — gateway provider registry + prefix enforcement (S-GATEWAY)
- **Env-driven registry (Wave-1 deliverable, gates COMPOSE B):** replace the hardcoded `providers[]` with parsing of `AI_GATEWAY_PROVIDERS` (e.g. `knowledge=http://…/mcp,glossary=http://…/mcp,book=http://…/mcp`), falling back to the current two for back-compat. **Adding a provider = an env entry**, not a code edit → **no provider slice ever edits `config.ts`**; the integrator adds env entries at COMPOSE B. This must land in Wave 1 or the "env, not code" no-conflict guarantee doesn't hold.
- **Prefix map + enforcement:** `{knowledge:"memory_", glossary:"glossary_", book:"book_", composition:"composition_", translation:"translation_", settings:"settings_", jobs:"jobs_"}`. At `computeCatalog`, **drop + warn** any tool whose name doesn't match its provider's prefix (kills silent first-provider-wins collisions). Optional `/internal/tools/search` index is **out of v1** (find_tools searches consumer-side).
- **Partial-catalog flag (H10):** the catalog already degrades to PARTIAL when a provider is unreachable; expose **per-provider availability** so a consumer's `find_tools` can tell "no such tool" from "provider temporarily down" (→ the agent says "try again," not "I can't").

### C-KIT-GO — `sdks/go/loreweave_mcp` (S-KIT-GO)
*Extraction honesty:* `IdentityMiddleware`, `BookOwnerGuard`, and the confirm-token spine are **extracted** from glossary (`mcp_server.go` + `action_confirm_token.go`); `UserScopeGuard`/`ProjectGuard` + the `_meta` validator are **built fresh** (no existing instance — low effort, not a copy).
```go
func IdentityMiddleware(internalToken string, next http.Handler) http.Handler // validates X-Internal-Token; lifts X-User-Id/Session/Trace → ctx
func UserIDFromCtx(ctx context.Context) (uuid.UUID, bool)
func NewStatelessHandler(srv *mcp.Server, internalToken string) http.Handler  // StreamableHTTP{Stateless:true,JSONResponse:true} + IdentityMiddleware
// scope guards — the THREE shapes (H15):
type Guard interface { Check(ctx context.Context, userID, resourceID uuid.UUID) error }
func BookOwnerGuard(grants grantclient.Client, level GrantLevel) Guard // verifyBookOwner; fail-closed; 60s cache
func UserScopeGuard(ownerOf func(ctx, resID) (uuid.UUID, error)) Guard  // resource.user_id == caller (settings/models)
func ProjectGuard(...) Guard
func UniformNotAccessible(err error) error // H13: collapse 403/404 → one error (no enumeration oracle)
// confirm-token spine (Tier-S/W):
func MintConfirmToken(userID, resourceID uuid.UUID, payload any, ttl time.Duration) (string, error)
func VerifyConfirmToken(tok string) (ConfirmClaims, error)
```

### C-KIT-PY — `sdks/python/loreweave_mcp` (S-KIT-PY)
*Extraction honesty:* `make_stateless_fastmcp` + `build_tool_context` (+ `ForbidExtra`) are **extracted** from knowledge `app/mcp/server.py`; `require_user_scope`/`require_project`, the confirm-token helpers (ported from the Go/glossary scheme), and the `_meta` validator are **built fresh**.
```python
def make_stateless_fastmcp(name: str) -> FastMCP                      # stateless_http=True, streamable_http_path="/"
def build_tool_context(ctx: MCPContext) -> ToolContext               # validate internal token; extract user/project/session/trace
class ForbidExtra(BaseModel): model_config = ConfigDict(extra="forbid")
def require_book_owner(grants, level)   -> Callable  # decorator/guard, fail-closed + 60s cache
def require_user_scope(owner_of)        -> Callable  # resource.user_id == caller
def require_project()                   -> Callable
def uniform_not_accessible(exc) -> ToolError         # H13
def mint_confirm_token(user_id, resource_id, payload, ttl) -> str
def verify_confirm_token(tok) -> ConfirmClaims
```

---

## 4. Finalized per-service tool catalogs (tiers + scope + confirm descriptor)

Tier per C-TOOL; **A**=auto-commit+activity/Undo; **W**=`confirm_action`; **S**=`confirm_action` (schema/secret). Money tools are ≥W with estimate.

### S-BOOK (`book_*`, scope=book, guard=BookOwnerGuard)
| Tool | Tier | Notes |
|---|---|---|
| `book_list`, `book_get`, `book_list_chapters`, `book_get_chapter`, `book_list_revisions` | R | |
| `book_create`, `book_update_meta`, `chapter_create`, `chapter_bulk_create`, `chapter_update_meta`, `chapter_restore_revision` | A | undo_hint set (trash/restore) |
| `chapter_save_draft` | A | **tool REQUIRES base_version** (H8: server-optional → tool-mandatory); 409 stops; undo=restoreRevision |
| `chapter_publish`, `chapter_unpublish` | W | descriptor `book.publish` |
| `book_delete`, `chapter_delete`, `*_purge` | W | descriptor `book.delete` |
| `book_set_cover`, `media_generate`, `audio_generate` | W | priced → estimate + confirm |

### S-COMPOSE (`composition_*`, scope=book via book ownership/grant)
| Tool | Tier | Notes |
|---|---|---|
| `composition_get_work`, `composition_list_outline`, `composition_get_prose`, `composition_list_canon_rules` | R | |
| `composition_create_work`, `composition_outline_node_*`, `composition_scene_link_*`, `composition_canon_rule_*` | A | |
| `composition_write_prose` | A | DRAFT; server already **mandates** `expected_draft_version` ([prose.py:47]) → reversible |
| `composition_publish` | W | canonization (CM1) |

### S-JOBS (`jobs_*`, scope=user/project — owns `services/jobs-service/`)
| Tool | Tier | Notes |
|---|---|---|
| `jobs_list`, `jobs_summary`, `jobs_get` | R | the read-SSOT for all job state; via S-KIT-PY (jobs-service is Python). Moved here from S-TRANSL (SF-1: jobs-service was unowned). |

### S-TRANSL (`translation_*`, scope=book)
| Tool | Tier | Notes |
|---|---|---|
| `translation_coverage`, `translation_segment_status`, `translation_list_versions`, `translation_job_status` | R | |
| `translation_set_active_version`, `translation_save_edited_version`, `translation_patch_block`, `translation_update_settings` | A | |
| `translation_start_job`, `translation_retranslate_dirty` | W | **priced → needs NEW estimate (HIGH#1)** + **re-price at execution (H14: re-confirm if actual > est×1.25 OR +$0.50)**; descriptor `translation.start_job` |
| `job_control(action)` | A/W | **cancel/pause → A**; **resume/retry → W** (re-spend). Forwards to the per-service control routers S-TRANSL/others already own (job *reads* live in S-JOBS). |

### S-SETTINGS (`settings_*`, scope=user, guard=UserScopeGuard)
| Tool | Tier | Notes |
|---|---|---|
| `settings_get_profile`, `settings_list_providers`, `settings_list_models`, `settings_get_defaults`, `settings_provider_inventory` | R | **H13: redact secrets server-side** |
| `settings_update_profile`, `model_register`(no secret), `model_update`, `model_set_favorite`, `model_set_active`, `model_set_default` | A | `model_set_default` = A+Undo (free, reversible, #8) |
| `model_delete` | W | |
| `provider_create`/`provider_update_secret` | — | **NOT a tool (OD-S1)** — `ui_navigate('/settings')` only |

---

## 5. Per-slice detailed design (what each agent builds)

- **S-KIT-GO / S-KIT-PY (do first — critical path).** Build the shared packages per C-KIT-* (extract identity-mw/BookOwnerGuard/confirm-token; build UserScope/Project guards + `_meta` validator fresh). DoD **(before Wave 2)**: unit tests for **all three** guards (book/user/project), identity-middleware header→ctx, confirm mint/verify round-trip, uniform-error, **and the `_meta` validator rejecting a tool missing `tier`/`scope`**. No service depends on them until published, so they land independently.
- **S-CONSUMER (sole owner of `frontend_tools.py`).** Implement `find_tools` (C-FT) incl. **synonym recall + low-confidence escalation (H6)** and **missing-vs-unavailable (H10)**; per-iteration `active_tool_names` curation + `/chat` cap=20 with find_tools/reads uncounted; **enforce the H7 cap = ≤5 same-op Tier-A writes/turn → escalate to batch confirm**; answer "what can you do" **by category (H5)**; define & advertise `ui_*` (C-NAV) + `confirm_action`/`propose_record_edit` (C-CONFIRM/C-PROPOSE) by reading C-TOOL `_meta.tier`; emit C-ACTIVITY on Tier-A results; **on a multi-step Tier-A failure report what succeeded/failed (H17)** — no false whole-goal success. DoD: tool-loop tests (discovery→call across passes; cap=20 honored; **≤5 Tier-A cap → batch escalation**; Tier-A activity emitted; legacy surface never suspends; unavailable-provider phrasing).
- **S-GATEWAY.** Env-driven provider registry + prefix enforcement + **per-provider partial-catalog/availability flag (H10)** (C-GW). DoD: catalog drops a mis-prefixed tool (test); env list parsed; back-compat default preserved; availability flag surfaced.
- **S-FE (never edits chat-service).** `ui_*` executors (router-driven, allowlisted routes); generic confirm card incl. **N-item batch render (H2 — one card, single Apply over `items[]`)**; generic diff card (`propose_record_edit`); activity/Undo strip (C-ACTIVITY). DoD: each renderer round-trips suspend→resume against a mocked chat stream; **batch card renders N rows with one Apply**; Undo issues the reverse tool.
- **S-JOBS.** `/mcp` server via S-KIT-PY exposing `jobs_list/jobs_summary/jobs_get` (reads) over jobs-service's existing store. DoD: kit identity+scope tests; tier metadata present.
- **S-BOOK / S-COMPOSE / S-TRANSL / S-SETTINGS.** Add an `/mcp` server using the kit; register the §4 catalog with C-TOOL metadata (incl. `synonyms`); **wire the NET-NEW per-domain `/v1/<domain>/actions/{preview,confirm}` token routes** for Tier-W/S (using the kit mint/verify); **emit `undo_hint` on every Tier-A tool result**. S-TRANSL additionally builds the **cost-estimate** endpoint (HIGH#1) + **re-price-at-execution (H14)**. DoD per service: kit-based identity+scope tests; tier metadata present; Tier-W confirm-token round-trip; Tier-A undo_hint present; **cross-service live-smoke** (chat→gateway→provider→ownership) at COMPOSE B.
- **S-WORKFLOW (Wave 3, system-prompt fragment only).** A static "workflow skill" encoding cross-service ordering (chapters→publish→extract→glossary→wiki) + async-job etiquette ("say started, never done; offer ui_watch_job") + **partial-failure honesty (H17)** + **scope honesty (H4 — bulk prose mutation is excluded; say so, don't half-do)**. DoD: scenario eval over the spec's C1–C9.

---

## 6. Compose points (where parallel agents STOP and reconcile)

- **COMPOSE A (after Wave 1) — Foundation integration. Owner: integrator (you or a reconcile agent).**
  - Merge the **6** foundation worktrees (S-KIT-GO, S-KIT-PY, S-CONSUMER, S-GATEWAY, S-FE, **S-JOBS** — disjoint → mechanical).
  - Verify the contracts realized: build a **stub MCP provider** (echo tool tagged `tier:A`) and prove: `find_tools` discovers it (and hides an "unavailable" provider gracefully) → consumer advertises it → call → Tier-A activity strip renders → `ui_navigate` round-trips → `confirm_action` (incl. a 2-item **batch** card) against a stub token route renders+commits. Smoke S-JOBS reads.
  - **Human Junction 1:** review foundation; approve before fanning out providers.
- **COMPOSE B (after Wave 2) — Provider federation. Owner: integrator.**
  - Add the 4 providers to `AI_GATEWAY_PROVIDERS` env (the ONLY shared change — env, not code).
  - Per-provider **cross-service live-smoke** on a stack-up: chat→gateway→provider→book-service ownership; a Tier-A auto-write + Undo; a Tier-W confirm; the translation estimate→start→`ui_watch_job`.
  - Reconcile namespacing (prefix enforcement passes for all) and curation vs the in-flight knowledge/glossary tools (OD-4).
  - **Human Junction 2:** all providers working.
- **COMPOSE C (after Wave 3) — End-to-end.** Run the §13 lazy-user scenarios (C1–C9 from spec Part II); confirm coverage-honesty (no false "I can't") + auto-apply safety (caps/Undo) + async etiquette. **Human Junction 3:** ship.

---

## 7. Risks to the parallel plan + mitigations

| Risk | Mitigation |
|---|---|
| A contract changes mid-wave → re-sync churn | Contracts §3 are frozen now; a change requires a mini-junction (notify affected slices). Keep §3 small. |
| Two provider slices need a kit change | Kit changes are **Wave-1-only**; if a Wave-2 slice finds a kit gap, it stops at a micro-compose with S-KIT owner rather than forking the kit. |
| `config.ts` provider array conflict | Eliminated by C-GW env-driven registry (no code edit per provider). |
| chat-service touched by S-CONSUMER **and** S-WORKFLOW | Sequenced across waves (S-WORKFLOW is Wave 3, prompt-only) → no overlap with S-CONSUMER's Wave-1 code. |
| `frontend_tools.py` wanted by S-CONSUMER **and** S-FE | **S-CONSUMER sole-owns** it (defines all frontend-tool schemas); S-FE renders only, never edits chat-service (SF-2). |
| S-TRANSL job tools touch unowned jobs-service | **S-JOBS owns `services/jobs-service/`** (job *reads*); S-TRANSL keeps only `job_control` forwarding (SF-1). |
| knowledge/glossary branches merge mid-flight | They're additive (own `memory_*`/`glossary_*`, already federated); reconcile only curation at COMPOSE B (OD-4). No code overlap with v1 slices. |
| Worktree cost (10 slices) | Wave 1 = **6** concurrent, Wave 2 = 4 concurrent; never all 10 at once. Kits finish first to unblock Wave 2 + S-JOBS. |

---

## 8. Deferred (tracked, not in this plan)
- **D-MCP-ASYNC-INCHAT-MSG** (P3+) — server-initiated "job finished" chat message (needs a live-push story; notification-service + `ui_watch_job` cover v1).
- **Gateway `/internal/tools/search` index** — only if consumer-side `find_tools` fuzzy search proves insufficient at scale.
- **Voice write tools** — voice stays read/answer-only in v1 (F3).
- **glossary migration to `propose_record_edit`** — glossary keeps its own diff tool; converge later.

---

## 9. Build order (concrete)
1. **Now:** freeze §3 contracts (this doc). 
2. **Wave 1 fan-out (6):** S-KIT-GO + S-KIT-PY first (smallest, critical path) ‖ S-CONSUMER ‖ S-GATEWAY ‖ S-FE ‖ S-JOBS (starts once S-KIT-PY publishes).
3. **COMPOSE A** + Human Junction 1.
4. **Wave 2 fan-out:** S-BOOK ‖ S-COMPOSE ‖ S-TRANSL ‖ S-SETTINGS (each on its kit).
5. **COMPOSE B** (env-federate + live-smoke) + Human Junction 2.
6. **Wave 3:** S-WORKFLOW.
7. **COMPOSE C** + Human Junction 3 → ship.

---

## 10. Review changelog (2026-06-20) — applied in-body

A 3-lens adversarial review (disjointness · contract-realizability · spec↔plan coverage), each grounded against code, **confirmed the architecture is sound** (all Part-IV tier resolutions + the 8 known-tricky items correctly owned, no tier contradictions). The gaps it found are now **fully applied in §1–§9 above**; this is the audit trail.

- **SF-1 — added `S-JOBS`** (owns `services/jobs-service/`, the job-read SSOT that was an unowned dependency). Job *reads* → S-JOBS; S-TRANSL keeps `job_control` forwarding. Now **10 slices**, Wave 1 = 6. *(§1, §2, §4, §5, §9)*
- **SF-2 — `frontend_tools.py` sole-owned by S-CONSUMER**; S-FE renders only, never edits chat-service (removed the only consumer↔FE file collision). *(§1, §2, §5, §7)*
- **Re-pinned two dropped numbers:** H7 Tier-A cap **= ≤5 same-op/turn** (S-CONSUMER §5); H14 re-price **= actual > est×1.25 OR +$0.50** (S-TRANSL §4/§5).
- **Assigned 6 orphan holes:** H2 batch confirm → S-FE (C-CONFIRM `items[]`); H5 capability-by-category, H6 synonym recall + escalation, H17 partial-failure → S-CONSUMER (+H17/H4 also S-WORKFLOW); H10 missing-vs-unavailable → S-GATEWAY flag + C-FT.
- **Contract realizability made honest:** `/v1/<domain>/actions/*` routes + Tier-A `undo_hint` are NET-NEW per provider; `_meta` enforcement is NET-NEW in the kits; `UserScopeGuard`/`ProjectGuard` are built fresh (not extracted); `AI_GATEWAY_PROVIDERS` env parser is a Wave-1 deliverable gating COMPOSE B; `base_version` label fixed H5→H8.

**Net:** no architecture reopened — DoD-completeness + contract-precision only, now woven into the body. Plan is build-ready.
