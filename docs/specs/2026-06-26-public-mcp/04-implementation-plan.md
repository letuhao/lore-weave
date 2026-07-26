# Public MCP Gateway — Implementation Plan & Fanout

- **Date:** 2026-06-26
- **Status:** PLAN (post-spike, build-ready pending OD-3/5/6/7 tunables).
- **Inputs:** [03-public-mcp-security-design.md](03-public-mcp-security-design.md) (DESIGN + Part II holes + Part III spike results), [02-interface-matrix.md](02-interface-matrix.md).
- **Locked:** dedicated `mcp-public-gateway` service · v1 = **full incl. priced jobs** · API keys (OAuth = later) · owned-books-only default (OD-8) · **key-creation behind a feature flag, any user (Q-GATE)** · **BYOK-only spend, no free-tier draw (Q-MONEY / PUB-12)** · **headless Tier-W = human-approve by default, self-confirm opt-in (OD-2)**.
- **Task size:** **XL** — new external trust boundary + new edge service + credential subsystem + cross-service spend plumbing. `/loom` per phase; **`/amaw` mandatory on P1 (credential mint/verify) and P3/P4 (spend + write-tier gate)**.

---

## 1. Verified foundation (from spikes — what we're NOT redesigning)

- Envelope hop works: edge mints `X-Internal-Token` + `X-User-Id` → `ai-gateway/mcp` → providers (Spike 1).
- BFF proxy is a known pattern; streaming already supported (Spike 2).
- Confirm-token is headless-safe and identity-locked (Spike 3).
- Spend attribution has a proven template (`campaign_id`) (Spike 4).
- Ownership guards are grant-aware and arg-based for book-scoped tools (Spike 5).

**The new work is the edge, the credential store, and 5 cross-service hardening items** (H-A admin/header isolation, H-B paid-reads, H-C per-key spend via `X-Mcp-Key-Id`, H-U project-owner guard, OD-8 owner-only resolver).

## 2. Parallelization model (what's serial vs fanout)

```
   ┌─────────────────────── SERIAL KEYSTONE (no fanout) ───────────────────────┐
   │ P0  edge skeleton + envelope hop + MCP handshake + PUB-9 strip/admin-isolate │
   │ P1  credential subsystem (auth-service) + Settings UI                        │
   └──────────────────────────────────┬─────────────────────────────────────────┘
                                       │ keystone done → providers can be worked in parallel
        ┌──────────────────────────────┼───────────────────────────────────────┐
        ▼ (FANOUT: 1 agent / provider)  ▼ (FANOUT: cross-cutting, 1 agent each)  ▼
   per-provider scope+hardening      edge controls            FE + OAuth
   book · glossary · knowledge*      rate-limit/spend/audit    Settings polish
   translation · composition         catalog default-deny      OAuth (P5)
   jobs · settings · lore-enrich     X-Mcp-Key-Id plumbing
   (*knowledge also needs H-U)        confirm_action server tool
```

- **P0 + P1 are a single serial track** — everything depends on the edge existing and a key resolving. **Do not fanout before P1 lands.**
- **After P1**, the per-provider classification+hardening is the natural fanout unit (§5), one worktree-isolated agent per MCP provider, because each touches a *different* service. They reconcile at the edge's scope map.
- **Cross-cutting items** (spend plumbing, catalog filter, confirm_action) each need ≥1 provider present, so they run **after** the first 1-2 providers, also parallelizable among themselves.

## 3. Phase plan with DoD (the gates)

### P0 — Edge keystone (SERIAL, /loom; security-review at end)
**Build:** `services/mcp-public-gateway` (TS/NestJS). It (a) terminates MCP streamable-HTTP from external clients (spec-compliant `initialize`/`tools/list`/`tools/call`, stateless — H-M), (b) **strips the entire inbound `X-*` namespace** and mints a fresh envelope (`X-Internal-Token` from config + a **static test `X-User-Id`** for now), (c) forwards to `ai-gateway/mcp` **only** (no route to `/mcp/admin`, holds no admin token — H-A/PUB-9), (d) requires the credential in the `Authorization` header, rejects query-string keys (H-R). BFF proxies `/mcp` → edge. `language-rule.yaml` + docker-compose + env entries.
**DoD:** external MCP client → BFF → edge → ai-gateway → a **read tool** round-trips on a live stack-up (not mock). Inbound `X-Admin-Token`/`X-Internal-Token`/`X-User-Id` are provably discarded (test). ai-gateway `X-Internal-Token` compare made constant-time. **live smoke:** real round-trip token present.

### P1 — Credential subsystem + Settings UI (SERIAL, /loom + **/amaw**)
**Build:** `mcp_api_keys` table in auth-service (Argon2id hash, prefix lookup, scopes, caps, `allow_self_confirm` flag, expiry, status) + `/v1/account/mcp-keys` CRUD (JWT, owner-only) + `/internal/mcp-keys/resolve` (X-Internal-Token; checks `account_status='active'` — H-L) + edge resolves real keys (Redis ~30-60s cache) and derives `X-User-Id` from the key. **Feature-flag gate (Q-GATE):** key creation is enabled by a platform flag (`PUBLIC_MCP_ENABLED`) — any user when on, fast kill-switch when off. Per-`(prefix,IP)` auth-failure limit + cheap HMAC pre-check before Argon2id (H-H). FE **Settings → MCP access** tab (create/copy-once/revoke/audit-view) — H-Q copy-once warning; tab hidden when the flag is off.
**DoD:** a real key created in the UI authenticates an external read call end-to-end; revoke kills it ≤60s; deleted account invalidates keys immediately; wrong-secret on a known prefix is rate-limited; flag off → no key creation + existing keys rejected. **/amaw cold-start review** of the mint/verify path.

### P2 — Scope gate + ownership hardening (FANOUT per provider, /loom)
**Build (edge):** catalog filter advertises only `tier ∩ domain`-allowed tools; pre-dispatch scope check; **default-deny unknown tools** (H-E); domain classification by *tools-touched* not prefix (H-F); `jobs`/`settings` require explicit scope. Default new key = `read + write_auto` on user-picked domains (OD-5); **owned-books-only** via an owner-only resolver/flag in the shared kits (OD-8).
**Build (per provider — the fanout):** confirm `book_id`/`project_id` are ownership-checked args; **knowledge: add `require_project_owner` (H-U) + promote `project_id` to an explicit arg (H-I)**; idempotency keys on Tier-A creates (H-G).
**DoD:** a `read`-only key sees only read tools; a `knowledge`-scoped key cannot touch books; H-U proven (key A cannot read user B's project even supplying its id); owned-books-only proven (key cannot reach a book merely shared to the owner unless `include_shared`).

### P3 — Abuse + cost controls + per-key spend (FANOUT cross-cutting, /loom + **/amaw**)
**Build:** edge per-key Redis rate-limit (429) with fail-closed-writes/fail-open-reads (PUB-8); **per-tool `incurs_cost` flag → spend pre-check on cost-incurring READS too** (H-B/PUB-10) + a `paid_read` scope; **BYOK-only enforcement (PUB-12)** — the edge pre-check resolves the would-be model and **rejects (402) any call that maps to a platform model or a free-tier / platform-balance draw**; **`X-Mcp-Key-Id` plumbing** — ai-gateway forwards it (additive) → shared kits lift to ctx → provider-registry submit merges into `job_meta` → `usage_outbox`/stream/`usage_logs` add `mcp_key_id` column → edge reconciles per-key monthly rollup (H-C/PUB-11); per-key spend sub-cap (402) with atomic reserve (H-K); append-only `mcp_call_audit` + owner audit view (H-O).
**DoD:** a leaked key cannot exceed its rate-limit or USD sub-cap; **a priced tool call is attributed to the key in `usage_logs`** (live smoke: run `translation_start_job` via a key, see the cost land tagged); a paid `glossary_web_search` is spend-gated; **a call resolving to a platform model is rejected 402 (BYOK-only)**. **/amaw** the spend path.

### P4 — Headless writes + priced jobs open (FANOUT per priced provider, /loom + **/amaw**)
**Build:** `write_confirm` scope; **human-approval queue (OD-2 default)** — a Tier-W propose routes its `confirm_token` to a new `mcp_pending_approvals` surface + a notification (notification-service exists); the FE approval card (reuse the confirm-card renderer) lets the owner Approve/Deny; the agent gets `pending_human_approval` and polls. **Opt-in `allow_self_confirm`** path: server-side **`confirm_action(confirm_token)`** reachable via the edge (generalize the frontend tool) for keys that hold the flag. **Edge re-price-on-execute** for priced tools (re-estimate; if actual > estimate×1.25 → structured `price_changed` + fresh token, never silent overspend — H-J); `jobs_cancel`/`jobs_pause` as Tier-A so an agent can abort its own spend (H-N); multi-step partial-failure honesty (agent reports what landed — H17).
**DoD:** a default key's priced action waits for a human Approve before any spend; an `allow_self_confirm` key runs propose→confirm→execute headless bounded by spend cap; a re-price breach is surfaced, not silently spent; an agent can cancel its own job. **/amaw** the write-tier gate.

### P5 — OAuth 2.1 + discovery (/loom)
**Build:** auth-code + PKCE, RFC 9728 Protected Resource Metadata, dynamic client registration (RFC 7591), audience-bound tokens (RFC 8707) verified at the edge (S9); `catalog_*` read provider for public-content discovery (OD-7).
**DoD:** a standards-compliant third-party MCP client completes the OAuth flow and calls a read tool on-behalf-of a user; audience confusion rejected.

### P6+ (deferred)
Signed webhook completion (OD-3); import/upload MCP path; anomaly alerting on key audit; partner org/team RBAC.

## 4. Hole → phase map (DoD checklist)

| Phase | Must satisfy |
|---|---|
| **P0** | H-A/PUB-9 (strip `X-*` + admin isolation) · H-M (MCP handshake/stateless) · H-R (header-only) · constant-time internal token |
| **P1** | H-L (account lifecycle) · H-H (Argon2id DoS guard) · H-Q (copy-once) · H-P (cache lag doc) · **/amaw** |
| **P2** | H-E (default-deny unknown) · H-F (domain-by-touch) · H-D/OD-8 (owned-books-only) · **H-U (project-owner guard)** · H-I (project_id arg) · H-G (idempotency) |
| **P3** | **H-B/PUB-10 (paid reads)** · **H-C/PUB-11 (`X-Mcp-Key-Id` spend attribution)** · **PUB-12 (BYOK-only, reject platform/free-tier)** · H-K (cap race) · H-O (audit) · **/amaw** |
| **P4** | **OD-2 human-approval queue (`mcp_pending_approvals` + notification + FE card)** · `allow_self_confirm` opt-in + confirm_action server tool · H-J (re-price on execute) · H-N (agent self-cancel) · H17 (partial-failure honesty) · **/amaw** |
| **P5** | S9 (OAuth audience) · OD-7 (`catalog_*`) |

**Blocking order:** H-A + H-B + H-C + H-U gate *opening to the public*. Priced tools (the v1 ambition) **must not** be exposed until **P3 (H-C) ships** — until then, the edge advertises non-cost tools only.

## 5. Fanout spec (after P1) — one agent per provider

Each provider agent runs the **same checklist** on its service, in its own worktree (no cross-file conflict — distinct services):

> For `<provider>` (book / glossary / knowledge / translation / composition / jobs / settings / lore-enrichment):
> 1. Classify every tool: tier (R/A/W/S), `incurs_cost` (true if it calls provider-registry embed/rerank/web-search/LLM), domains-touched (read + write side effects), required scope.
> 2. Confirm `book_id`/`project_id` are ownership-checked **args** (not header-only). **knowledge: add `require_project_owner` + project_id arg (H-U/H-I).**
> 3. Add `idempotency_key` to Tier-A create tools (H-G).
> 4. Ensure the shared MCP kit lifts `X-Mcp-Key-Id` → ctx and the submit path merges it into `job_meta` (H-C) — for providers that spend.
> 5. Emit the per-tool scope/cost classification as structured output → feeds the edge's central scope map.

**Cross-cutting agents (parallel, after ≥1 provider):**
- **Spend-plumbing agent** — ai-gateway `X-Mcp-Key-Id` forward + both shared kits + provider-registry `job_meta` merge + the 3 SQL columns + usage-consumer parse (H-C). *(touches ai-gateway + sdks + provider-registry + usage-billing — coordinate, not fully disjoint.)*
- **Edge-controls agent** — rate-limit, spend pre-check, catalog default-deny, audit (edge only).
- **Confirm/write agent** — server-side `confirm_action` + re-price-on-execute + jobs cancel (P4).

**Coordination note:** the spend-plumbing agent and the per-provider agents both touch the shared kits / provider-registry — sequence the kit changes first (one agent), then providers consume. Don't fan these out fully concurrently against the same kit files.

## 6. Live-smoke gates (repo VERIFY rule — ≥2 services)

Every phase ends with a real stack-up smoke (external MCP client → BFF → edge → ai-gateway → provider → book-service ownership), not mock-only:
- **P0:** read tool round-trip + inbound-header-strip proof.
- **P1:** real key auth + revoke.
- **P2:** scope filter + H-U cross-tenant denial.
- **P3:** priced call attributed to key in `usage_logs` + cap enforcement.
- **P4:** headless propose→confirm priced job under cap + re-price breach surfaced.

## 7. Remaining tunables (don't block P0–P1; decide by P2/P3 — defaults applied)

All apply their recommended default unless overridden:
- **OD-5** default domain scope on a new key → user-picks; default `book+glossary+knowledge` (read+write_auto). **P2.**
- **OD-6** default per-key spend sub-cap → conservative ~$5/mo, user-raisable to guardrail. **P3.**
- **OD-7** `catalog_*` discovery provider → P5 with OAuth.
- **N-1** rate-limit default → 60 rpm, editable. **P3.**
- **N-2** key expiry → optional, default none, UI nudge. **P1.**
- **N-3** audit retention → `args_hash`+redacted shape, ~90 days. **P3.**
- **H-L policy** → require `account_status=active`; email-verified optional. **P1.**

*Resolved (no longer open):* OD-1, OD-2, OD-3, OD-4, OD-8, Q-GATE, Q-MONEY, v1-ambition — see header + §3.

## 8. Recommended first move

Build **P0 + P1 serially now** (the keystone — read-only public MCP behind a real key, fully safe because no priced/write tools are advertised yet). That ships a usable, secure milestone and unblocks the per-provider fanout. Then fan out P2 (scope + H-U) and the P3 spend-plumbing in parallel. Priced tools flip on only after P3's per-key attribution live-smoke passes.
