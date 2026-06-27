# Public MCP Gateway + Security Model — Architecture Design (CLARIFY + DESIGN)

- **Date:** 2026-06-26
- **Status:** Architecture DRAFT (pre-build). Decisions below are **proposed**, marked `OD-*` where open for the PO.
- **Builds on:** [`2026-06-10-glossary-assistant-architecture.md`](../2026-06-10-glossary-assistant-architecture.md) (ai-gateway federation, envelope, tiering, confirm-token), [`2026-06-20-mcp-fanout-agent-universal-control.md`](../2026-06-20-mcp-fanout-agent-universal-control.md) (tier model, frontend-tool handshake H12, async-loop H1), the auth-service identity model, usage-billing spend guardrails.
- **Companion docs:** [01-feature-catalog.md](01-feature-catalog.md), [02-interface-matrix.md](02-interface-matrix.md).
- **Task size:** **XL** — a new public security boundary on the gateway + a new credential subsystem in auth-service + per-key rate/spend/audit + a headless write-gating policy across ~10 MCP providers. New external trust boundary. Recommend `/loom` per phase, **`/amaw` mandatory** for the credential mint/verify path and the write-tier gate.

---

## 1. Problem & goal

> *"I want to make MCP public on the internet, so other agents can use our platform without going through the FE. This needs a new security setting."*

Today the MCP layer is **internal-only**. `ai-gateway` (:8210) federates ~100 domain tools and trusts an `X-Internal-Token` + a forwarded `X-User-Id` that a **trusted internal consumer** (chat-service) derived by verifying the user's JWT. There is **no way for an external, third-party agent** (someone else's Claude/GPT agent, a CLI, a partner integration) to call our tools — and we would never want to hand out `X-Internal-Token` or a user's raw JWT to do it.

**Goal:** a **public MCP endpoint** an external agent can connect to over the internet with its **own credential**, which the edge authenticates, maps to a specific LoreWeave user + a bounded set of scopes, and then turns into the *existing* internal envelope — inheriting all the ownership, tiering, anti-oracle, and spend protections already built, plus **new** edge controls (auth, per-key rate-limit, per-key spend cap, audit) and a **headless write-gating policy** (no browser to render confirm cards).

**Non-goals (v1):** exposing admin/system tools publicly; letting a public key create provider-credential secrets; a public *marketplace* of agents; multi-org/team RBAC beyond per-user keys.

---

## 2. Grounded current state (what we build on / around)

| Fact (verified in deep-dive) | Consequence for this design |
|---|---|
| `api-gateway-bff` is a **pure pass-through proxy** — it does **no JWT validation**, injects no `X-User-Id`. | We **cannot** put public-MCP auth "in the BFF as-is." We need a real auth-enforcing component. Two shapes in §4. |
| `ai-gateway` is **internal-only** (:8210), auth = `X-Internal-Token`, identity = forwarded `X-User-Id`. Stateless per-call transport, per-call envelope (proven, glossary H3). | The federation core is reusable verbatim. The new edge sits *in front of* it and produces the envelope. |
| Identity model: **HS256 JWT** (`{sub,sid,iat,exp}`, shared `JWT_SECRET`), validated **per-service**; refresh = opaque hashed; admin = **RS256/KMS**. | We add a **new credential class** (API key / OAuth token) issued + verified by **auth-service** (it already owns identity, sessions, RS256 minting). |
| **No** API-key / OAuth-for-external infrastructure exists. Rate-limit exists **only** in auth-service (per-route/IP); **none at the gateway**. | Build the credential store, the edge rate-limiter, and audit new. |
| **Spend guardrails** (USD reserve→reconcile→release) + platform free-tier already gate every priced job per user. | Public keys inherit the user wallet; we add a **per-key sub-cap**. No new billing core. |
| Tools are **envelope-only identity**, `extra="forbid"`, anti-oracle, and **tiered R/A/W/S** with **server-minted confirm tokens** re-priced at execute. | Inherited for free. The confirm-token *is* the headless-friendly gate primitive. |
| Write Tier-W/S today relies on a **browser** rendering a confirm card via the `agui` frontend-tool channel; a non-`agui` client gets **inline-only, never suspends** (internal F2/H12). | A headless agent is "non-`agui`": it must get a **non-visual** confirm path or be denied W/S. §6. |

---

## 3. Locked-ish shaping decisions (proposed)

- **D1 — The public entry point is a NEW thin edge service: `mcp-public-gateway`** (TS/NestJS, sibling of `api-gateway-bff`), reachable through `api-gateway-bff` at `/mcp` (honors the Gateway Invariant: one external host). It authenticates the external credential, enforces per-key rate-limit + spend cap + audit, mints the internal envelope, and forwards to `ai-gateway/mcp`. It is **pure edge** — no tool logic, no LLM. *(Alternative considered: bolt auth onto `api-gateway-bff` directly — rejected because the BFF is deliberately auth-free pass-through and SSE/stream-shaped; a focused edge keeps the security boundary auditable. See OD-1.)*
- **D2 — Two credential classes, one identity mapping:** **(a) Personal API keys** (developer pastes a key into their own agent — the 90% case) and **(b) OAuth 2.1 authorization-code + PKCE** (a third-party agent acts *on behalf of* a LoreWeave user, MCP-spec-compliant). Both resolve to **one `user_id` + a scope set + a key policy**. v1 ships (a); (b) is phase P4. See §5.
- **D3 — Public keys are scoped, least-privilege, and default to read+auto-write only.** A key carries **tier scopes** (`read`, `write_auto`, `write_confirm`) and **domain scopes** (`book`,`glossary`,`knowledge`,`translation`,`composition`,`jobs`,`settings:read`,`catalog`). Default new key = `read` + `write_auto` on a user-chosen domain set. **`write_confirm` is opt-in; `schema`/secret/admin are never grantable to a public key.** See §6.
- **D4 — Headless write-gating = programmatic two-call confirm, never a hung suspend.** Tier-W tools already return a `confirm_token` + preview *as data*. A headless agent calls the tool (gets the token + estimate), then calls a generic `confirm_action(confirm_token)` tool to execute — **the agent itself is the second actor**, bounded by spend cap + the key's `write_confirm` scope. No browser needed; nothing hangs. Tier-S/secret stays human-only. See §6.3.
- **D5 — Every public key has its own rate-limit + USD spend sub-cap + full audit.** Independent of, and stricter than, the user's global guardrail. A leaked key cannot drain the wallet or hammer the platform. See §7.
- **D6 — Reuse the internal federation + envelope + tier machinery unchanged.** The new code is the *edge* (auth, limits, audit, envelope-mint) + the credential subsystem. `ai-gateway` and every provider stay as-is. See §4.

---

## 4. Target architecture

```
   External agent (Claude/GPT/CLI/partner)
        │  MCP streamable-HTTP, JSON-RPC
        │  Authorization: Bearer <lw_pk_…  | OAuth access token>
        ▼
   api-gateway-bff  :3000   (one public host — Gateway Invariant)
        │  proxy  /mcp  →  mcp-public-gateway
        ▼
   ┌──────────────────────────────────────────────────────────┐
   │  mcp-public-gateway (NEW, TS/NestJS)   — the security edge │
   │  1. AUTHN: verify credential → resolve {user_id, key_id,  │
   │       scopes, policy}  (calls auth-service /internal)      │
   │  2. RATE-LIMIT: per-key token bucket (Redis)              │
   │  3. SCOPE GATE: drop tools outside key's tier∩domain set  │
   │  4. SPEND PRE-CHECK: per-key USD sub-cap (usage-billing)  │
   │  5. AUDIT: append every call (key_id,tool,verdict,cost)   │
   │  6. ENVELOPE MINT: set X-Internal-Token + X-User-Id +     │
   │       X-Trace-Id + X-Mcp-Key-Id; forward                  │
   └───────────────────────────┬──────────────────────────────┘
        │  X-Internal-Token + X-User-Id  (the EXISTING envelope)
        ▼
   ai-gateway :8210  /mcp   (UNCHANGED federation)
        ▼  per-call stateless transport, per-call envelope
   knowledge · glossary · book · composition · translation · jobs · settings · enrichment  (UNCHANGED providers)
        ▼
   each provider: require_book_owner / user-scope guard · tier gate · confirm-token · anti-oracle  (UNCHANGED)
```

**Two new components only:**
1. **`mcp-public-gateway`** — the edge above. Stateless; Redis for rate-limit + token-cache; calls auth-service to resolve keys, usage-billing for spend pre-check, and writes an audit row.
2. **API-key / OAuth subsystem in `auth-service`** — the credential store + mint/verify + management API + (P4) OAuth endpoints. auth-service already owns identity, sessions, and RS256 minting, so the credential lifecycle belongs there (DDD: identity owns credentials).

**Why a separate edge service (D1):** the public security boundary wants its own deploy/scale/audit/WAF surface, must NOT inherit the BFF's auth-free pass-through behavior, and is shaped differently (auth-enforcing, MCP-aware) from the BFF's stream proxy. It also keeps the blast radius small — a bug here can't touch the FE's `/v1/*` traffic.

---

## 5. The credential subsystem (the "new security setting")

### 5.1 Data model (auth-service DB)
```sql
CREATE TABLE mcp_api_keys (
  key_id          UUID PRIMARY KEY,
  owner_user_id   UUID NOT NULL REFERENCES users(id),
  name            TEXT NOT NULL,              -- "my-research-agent"
  key_prefix      TEXT NOT NULL,             -- "lw_pk_AbC1" (shown in UI; for lookup)
  key_hash        TEXT NOT NULL,             -- Argon2id/bcrypt of the full secret (never store raw)
  scopes          TEXT[] NOT NULL,           -- ['read','write_auto','domain:book','domain:knowledge', …]
  spend_cap_usd   NUMERIC,                   -- per-key monthly USD sub-cap (NULL = inherit user guardrail only)
  rate_limit_rpm  INT NOT NULL DEFAULT 60,   -- requests/min
  status          TEXT NOT NULL DEFAULT 'active',  -- active | revoked
  last_used_at    TIMESTAMPTZ,
  expires_at      TIMESTAMPTZ,               -- optional rotation/expiry
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON mcp_api_keys (key_prefix);   -- O(1) lookup, then verify hash
```
- **Key format:** `lw_pk_<22+ url-safe random>`. Shown **once** at creation. Stored as **Argon2id hash** (mirrors how refresh tokens are hashed today, but slow-hash since these are long-lived). Lookup by `key_prefix`, then constant-time verify the hash.
- **OAuth (P4):** add `mcp_oauth_clients` (dynamic client registration, RFC 7591) + `mcp_oauth_grants` (per user×client, scopes, refresh). Access tokens are short-lived JWTs (RS256, reuse the admin signer infra) with `{sub, key_id|client_id, scopes, exp}`; the edge verifies signature locally (no auth-service round-trip on the hot path).

### 5.2 Management surface (FE settings + REST)
New `/v1/account/mcp-keys` on auth-service (JWT-gated, owner-only) — the "new security setting" the user asked for, surfaced under **Settings → Developer / MCP access**:
| Method | Path | Description |
|---|---|---|
| GET | `/v1/account/mcp-keys` | List my keys (prefix, name, scopes, caps, last_used — never the secret) |
| POST | `/v1/account/mcp-keys` | Create key → returns the **full secret once** + the connection URL |
| PATCH | `/v1/account/mcp-keys/{id}` | Edit name/scopes/caps/rate-limit/expiry |
| DELETE | `/v1/account/mcp-keys/{id}` | Revoke immediately |
| GET | `/v1/account/mcp-keys/{id}/audit` | Recent calls (tool, verdict, cost, ts) for this key |

Internal resolver for the edge: `GET /internal/mcp-keys/resolve` (prefix+hash → `{user_id, key_id, scopes, caps}`), `X-Internal-Token`-gated, short-TTL cached in the edge (Redis, ~30–60s) so the hot path is one Redis hit, not a DB round-trip per call.

### 5.3 Connection
The external agent points its MCP client at `https://app.loreweave.dev/mcp` with `Authorization: Bearer lw_pk_…`. The edge advertises **only the tools the key's scopes allow** (federated catalog ∩ scope filter), so an under-scoped key literally cannot see tools it may not call (defense + clean discovery). MCP-spec clients that do OAuth discovery get a **Protected Resource Metadata** doc (RFC 9728) pointing at auth-service's `/oauth/*` (P4).

---

## 6. Authorization & write-gating (the load-bearing part)

### 6.1 Invariants (extend the proven internal set)
- **PUB-1 — Identity is derived at the edge, never trusted from the agent.** The edge resolves `user_id` from the credential and sets `X-User-Id`; the agent **cannot** supply or override it (envelope, not arg — inherits SEC-1). A public request that reaches `ai-gateway` always carries an edge-minted envelope.
- **PUB-2 — `X-Internal-Token` never leaves the private network.** The agent presents only its own credential; the edge holds the internal token. The BFF→edge→ai-gateway hops are private.
- **PUB-3 — A public key may only call tools within its `tier ∩ domain` scopes.** Enforced **twice**: at the edge (catalog filter + pre-dispatch check) and inherited at the provider (ownership + tier). Default scopes: `read` + `write_auto`. `write_confirm` opt-in. **`schema`, secret, and admin tools are never grantable** to a public key (hard allowlist, not a scope toggle).
- **PUB-4 — Ownership is still enforced per-tool by the provider.** The edge sets identity; each provider still runs `require_book_owner` / user-scope guard + anti-oracle. The edge does **not** decide ownership (it can't be the only gate — fail-closed defense in depth).
- **PUB-5 — Headless writes propose without a hung suspend, but execute behind a HUMAN gate by default (OD-2).** See §6.3. A public (non-`agui`) caller is never offered a frontend/suspend tool; a Tier-W call **proposes** and the resulting `confirm_token` routes to a **human approval queue** (FE + notification) by default. Agent-self-confirm is an **opt-in per-key flag** (`allow_self_confirm`).
- **PUB-6 — Every priced call is spend-gated twice:** the key's USD sub-cap (edge pre-check) **and** the user's global guardrail (existing reserve→reconcile→release). A leaked key cannot exceed either.
- **PUB-7 — Every call is audited** with `{key_id, user_id, tool, args_hash, verdict, cost, trace_id, ts}`. Audit is append-only and surfaced to the key owner.
- **PUB-8 — Rate-limit per key, fail-closed on limiter outage for writes, fail-open for reads** (availability vs safety trade chosen per tier).
- **PUB-12 — BYOK-only spend (Q-MONEY LOCKED).** A public key may incur cost **only** via the owner's own BYOK credentials. The edge spend pre-check **rejects** (402) any call whose model resolves to a **platform model** or would draw the **free-tier / platform balance**. A public agent cannot consume the human's free credits; a leaked key's blast radius is the user's own BYOK provider bill (further bounded by the per-key sub-cap, PUB-6).

### 6.2 Scope → tier mapping
| Key scope | Grants | Example tools |
|---|---|---|
| `read` | all Tier-R in granted domains | `*_search`, `*_get_*`, `*_list_*`, `memory_*`, `jobs_*`, `catalog_*` |
| `write_auto` | Tier-A in granted domains | `book_chapter_save_draft`, `glossary_create_evidence`, `kg_propose_fact`, `composition_write_prose` |
| `write_confirm` | Tier-W via programmatic confirm (incl. priced, subject to spend cap) | `book_chapter_publish`, `translation_start_job`*, `kg_build_graph`*, `composition_generate`* |
| *(ungrantable)* | Tier-S, provider-secret, admin | `glossary_*` schema kinds, `settings` secret create, all `*_admin_*` |

### 6.3 Headless Tier-W: propose → human approval (default), self-confirm (opt-in) — OD-2 LOCKED
The internal `confirm_token` flow separates *propose* from *execute*; the confirm step is **pure request/response** (Spike 3 — no browser needed mechanically). **Policy default is human-in-the-loop:**

**Default path (`allow_self_confirm = false`):**
1. Agent calls a Tier-W tool (e.g. `translation_start_job`) → provider returns `{preview, cost_estimate, _meta:{confirm_token}}` **without spending**.
2. The edge **routes the `confirm_token` to a human approval queue** — a row in a new `mcp_pending_approvals` surface + a **notification** to the owner. The agent gets `status: pending_human_approval` (+ the approval id) and **must not** self-confirm.
3. The human reviews in the FE (preview + estimate + which key requested it) and **Approves/Denies**. Approve executes the action (the existing confirm endpoint); deny drops the token.
4. The agent polls (e.g. `jobs_get` / an approval-status read) or is told "started" only after approval.

**Opt-in path (`allow_self_confirm = true`, power users):** the agent calls a generic server-side **`confirm_action(confirm_token)`** directly (the FE `glossary_confirm_action` generalized + exposed through the edge), bounded by `write_confirm` scope + spend sub-cap + audit. Same token, different second actor.

**Why this is safe:** human-approve default means a Tier-W public-key action **cannot reach canon/money without a human Approve** — the strongest INV-1 posture. Even the opt-in self-confirm is bounded by: explicit `write_confirm` + `allow_self_confirm` grants, the spend sub-cap (PUB-6) + BYOK-only (PUB-12), the server-minted token (user+payload+expiry, Spike 3), Tier-A volume caps + audit, and Tier-S/secret/admin being unreachable. **New work:** the `mcp_pending_approvals` surface + the FE approval card (reuse the existing confirm-card renderer) + the notification leg (notification-service exists). The agent-facing async contract is the same poll model as a long job (§8).

### 6.4 What a public key can never do
Account/auth mutations, password/email, account delete, provider-credential **secret** create/update, system/admin glossary+KG, billing admin, another user's data (anti-oracle + ownership), raising its own caps, or seeing `X-Internal-Token`.

---

## 7. Abuse, cost & availability controls (the new edge)

| Control | Mechanism | Where |
|---|---|---|
| **Per-key rate limit** | Redis token bucket keyed `key_id`, `rate_limit_rpm` from the key row; 429 + `Retry-After`. | edge |
| **Per-key spend sub-cap** | Pre-dispatch USD check against a per-key monthly counter; priced tools blocked when exceeded (402). Reconciled from the same usage-billing record stream (tag the record with `key_id`). | edge + usage-billing |
| **Global user guardrail** | Existing reserve→reconcile→release on every priced job. | usage-billing (unchanged) |
| **Audit** | Append-only `mcp_call_audit` (key_id, user_id, tool, args_hash, verdict, cost, trace). Owner-visible; SRE-queryable. | edge |
| **Revocation** | `DELETE /v1/account/mcp-keys/{id}` → status=revoked → edge cache TTL ≤60s → key dead within a minute. | auth + edge |
| **Key expiry / rotation** | optional `expires_at`; UI nudges rotation. | auth |
| **WAF / DDoS** | edge is its own host → platform firewall rules, IP throttling, attack-mode independent of FE. | infra |
| **Anti-oracle preserved** | provider returns uniform not-accessible; edge never adds an existence signal. | provider (unchanged) |
| **Input caps** | inherit read-tool clamps (default 20 / max 50) + `extra="forbid"`. | provider (unchanged) |

---

## 8. Async completion for headless agents (gap from interface matrix §3)

A public agent that starts a priced job (`translation_start_job`, `kg_build_graph`) gets a `job_id` — the turn ends; the job runs minutes. The FE uses SSE + notifications; a headless agent has neither. v1 solution:
- **Poll:** `jobs_get` / `translation_job_status` are Tier-R — the agent polls. Simple, no new infra. **(v1 default.)**
- **Webhook (OD-3, P3+):** a per-key optional `callback_url` the edge POSTs (signed) on job terminal, fed by the existing job terminal stream. Defer unless demand. This is the public sibling of internal `D-MCP-ASYNC-INCHAT-MSG`.

The agent contract: **"started, here is the job_id"** — never "done" — exactly the internal INV-8 rule.

---

## 9. Build phases

```
P0  mcp-public-gateway skeleton: BFF proxies /mcp → edge; edge mints the internal
      envelope from a STATIC test key; forwards to ai-gateway; round-trip proven
      end-to-end (read tool only). No credential store yet.        ← keystone
P1  Credential subsystem in auth-service: mcp_api_keys table + create/list/revoke
      REST + /internal resolve; edge resolves real keys (Redis cache); FE Settings →
      MCP access page (create/copy-once/revoke).                    ← the "new security setting"
P2  Scope gate + catalog filter: edge advertises only tier∩domain-allowed tools;
      pre-dispatch scope check; default read+write_auto; hard allowlist excludes S/secret/admin.
P3  Edge rate-limit (Redis bucket) + per-key spend sub-cap (tag billing records with
      key_id; 402 on exceed) + append-only audit + owner audit view. Read-tier public.
P4  write_confirm scope + programmatic confirm_action exposure for headless;
      OD-2 require_human_confirm option. /amaw this phase.
P5  OAuth 2.1 (auth-code + PKCE, RFC 9728 PRM, dynamic client reg) for on-behalf-of
      third-party agents. catalog_* read provider (discovery).
────────────────────────────────────────────────────────────────────────────
P6+ (defer) webhook completion (OD-3); import/upload MCP path; partner org/team RBAC.
```
**Every phase:** real cross-service **live-smoke** (external client → BFF → edge → ai-gateway → a provider → book-service ownership) on a stack-up, not mock-only (repo VERIFY gate). P0 proves the envelope hop; P1 proves a real key; P3 proves a leaked-key can't drain; P4 proves headless write + spend cap.

---

## 10. Open decisions for CLARIFY (PO)

> **LOCKED (PO, 2026-06-26):**
> - **OD-1 → dedicated `mcp-public-gateway` service.**
> - **v1 ambition → FULL, including priced jobs.** ⇒ **H-C (per-key spend attribution) is a HARD pre-launch blocker** for priced tools (estimate-only is unsafe for money; Spike 4 de-risks via `X-Mcp-Key-Id`).
> - **OD-4 → API keys first, OAuth P5.** **OD-8 → owned-books-only default + opt-in `include_shared`.** **OD-3 → poll-only async** (webhook = P6; MCP-native long-job pattern, §8a).
> - **Q-GATE → any user, behind a feature flag.** Key creation is gated by a platform feature flag (fast kill-switch); when on, any user may mint keys.
> - **Q-MONEY → BYOK passthrough, NO free-tier draw.** ⇒ new invariant **PUB-12**: a public key may spend **only** through the owner's own BYOK credentials; the edge **rejects any call that would resolve to a platform model or draw the free-tier / platform balance**. A leaked key cannot burn platform free credit.
> - **OD-2 → human-approve by DEFAULT for headless Tier-W.** ⇒ §6.3 inverts: a public key's Tier-W (write/priced) action **proposes headless but routes to an approval queue + notification; the human approves in the FE before execution.** Agent-self-confirm becomes an **opt-in per-key flag** (`allow_self_confirm`), not the default.
>
> The remaining ODs (5/6/7) keep their recommended defaults unless overridden.

- **OD-1 — Edge placement:** dedicated `mcp-public-gateway` service (recommended) vs an auth-enforcing module inside `api-gateway-bff` vs adding a public auth mode to `ai-gateway` itself. Recommend the **dedicated edge** (clean security boundary, independent scale/WAF, BFF stays pass-through).
- **OD-2 — Headless Tier-W:** allow agent self-confirm (spend-capped) by default vs require a per-key `require_human_confirm` (human approves in FE) vs deny Tier-W to public keys in v1 entirely. Recommend **self-confirm with spend cap, `require_human_confirm` as an opt-in flag**; deny only if the PO wants v1 read-mostly.
- **OD-3 — Async completion:** poll-only (v1) vs add signed webhooks (P6). Recommend **poll-only v1**.
- **OD-4 — Credential class for v1:** personal API keys only vs API keys + OAuth from the start. Recommend **API keys v1, OAuth P5** (most agent frameworks accept a bearer key; OAuth is the standards-compliant on-behalf-of path for partners).
- **OD-5 — Default domain scope on a new key:** all read-able domains vs a user-picked subset. Recommend **user-picks at creation**, default to `book + glossary + knowledge` read+write_auto.
- **OD-6 — Spend cap default:** inherit user guardrail only vs a conservative per-key default (e.g. $5/mo). Recommend **a conservative default sub-cap**, user-raisable up to their guardrail.
- **OD-7 — Catalog/discovery tool:** add `catalog_*` MCP read provider in v1 (lets external agents find public books) vs defer. Recommend **add in P5** with OAuth (public-content discovery is a natural public-agent use case).

---

## 11. Adversarial scenarios (stress the design)

- **S1 — Leaked API key.** Attacker has `lw_pk_…`. → bounded by: key scopes (no S/secret/admin), per-key rate-limit, per-key spend sub-cap, audit (owner sees anomalous calls), one-click revoke (≤60s). Cannot touch other users (ownership + anti-oracle). **Contained;** add anomaly alerting (P3+).
- **S2 — Agent supplies `X-User-Id`/`X-Internal-Token` headers itself.** → the edge **strips and overwrites** all envelope headers from inbound requests before minting its own (PUB-1/PUB-2). Inbound `X-*` are never trusted. **Must be an explicit edge rule + test.**
- **S3 — Prompt-injected external agent calls a destructive tool.** A poisoned document tells the agent `book_purge`. → `book_purge` is Tier-W (not `write_auto`); needs `write_confirm` + a confirm token; even then, audit + (optional) human-confirm. Most public keys won't hold `write_confirm`. Tier-A injection is volume-capped + undo-able. **Contained by tier policy; document that `write_confirm` keys carry real risk.**
- **S4 — Spend bomb.** Agent loops `translation_start_job`. → per-key spend sub-cap (402) + global guardrail reserve + rate-limit. **Contained, double-gated.**
- **S5 — Key with `write_confirm` self-confirms everything.** → that's the point of the scope; bounded by spend cap + audit + `require_human_confirm` opt-in (OD-2). The grant is the user's informed choice. **Acceptable; make the scope's risk explicit in the UI.**
- **S6 — Edge is down / limiter (Redis) down.** → edge down = public MCP unavailable, FE unaffected (separate service). Limiter down = fail-closed for writes, fail-open for reads (PUB-8). **Graceful.**
- **S7 — Enumeration via tool errors.** → anti-oracle preserved at providers; edge adds no existence signal; under-scoped tools aren't even advertised. **Inherited.**
- **S8 — Token replay of a confirm_token across keys/users.** → token bound to user+payload+expiry, single-use, re-priced; a different key resolves a different user → mismatch → reject. **Contained.**
- **S9 — OAuth (P5) confused-deputy / token audience.** → access tokens carry an audience bound to our MCP resource (RFC 8707 resource indicators); the edge verifies audience. **Designed in at P5.**

---

## 12. Verdict

The public-MCP feature is **mostly an edge + credential problem, not a tools problem** — the ~100-tool federation, envelope-only identity, tiering, confirm-token, anti-oracle, and spend guardrails already exist and are reused unchanged. The genuinely new, load-bearing work is concentrated in four places, each de-risked:
1. **A real auth boundary** where there is none today (BFF is pass-through) → a dedicated edge service that authenticates a new credential class and mints the existing internal envelope (PUB-1/2).
2. **A credential subsystem** in the service that already owns identity (auth-service) → hashed keys, scopes, caps, management UI, the "new security setting" (§5).
3. **Headless write-gating** → reuse the confirm-token spine programmatically; never hang on a browser gate (PUB-5, §6.3).
4. **Per-key abuse/cost controls** → rate-limit + spend sub-cap + audit + revoke at the edge (§7).

**Recommendation:** build P0 (envelope hop) and P1 (credential store + Settings page) first to ship a **read-only public MCP** safely, then layer scopes (P2), abuse controls (P3), headless writes (P4), and OAuth (P5). Resolve OD-1..OD-7 at CLARIFY before P0.

---

# PART II — Adversarial edge-case review (2026-06-26)

**Method:** walk the design against the grounded codebase to find edge cases §11 does **not** cover. Each hole = symptom → why the current design misses it → concrete patch → severity → phase. Two were verified against code and reshape the design; they are listed first. **Holes H-A and H-B are blockers** — the design as written in Parts I is unsafe without them.

## 13. Code-verified findings that change the design

### H-A 🔴 BLOCKER — the edge must hard-isolate the admin surface and strip ALL inbound `X-*`
**Symptom.** `ai-gateway` exposes **`/mcp/admin`** (RS256 `X-Admin-Token`) alongside `/mcp`. Part I says "admin not grantable" but never states the edge must (a) route public traffic **only** to `/mcp`, never `/mcp/admin`, and (b) **strip every inbound `X-*` header** — `X-Admin-Token`, `X-Internal-Token`, `X-User-Id`, `X-Project-Id`, `X-Mcp-Key-Id` — before minting its own. S2 only mentioned `X-User-Id`/`X-Internal-Token`. An external agent that sets `X-Admin-Token: …` or `X-Internal-Token: …` must have it **discarded**, not forwarded.
**Patch.** Edge invariant **PUB-9: the edge constructs the outbound envelope from scratch and deletes the entire inbound `X-*` namespace first (allowlist, not denylist).** The edge has **no** route to `/mcp/admin` and holds no admin token. Add an explicit test: inbound `X-Admin-Token`/`X-Internal-Token` → 401/ignored, never reaches `ai-gateway`.
**Severity: BLOCKER (privilege escalation).** **Phase P0.**

### H-B 🔴 BLOCKER — "read" tools can spend money; spend-gating keyed on Tier-W is wrong
**Symptom.** `glossary_web_search` is **Tier-R** but its own header says *"a PAID outward call … it is NOT confirm-gated"* (`web_search_tool.go:13-16`). Hybrid `memory_search`/drawer search with `rerank=true`, and any embedding-backed read, also call provider-registry (`/internal/rerank`, `/internal/embed`) → **real BYOK spend**. PUB-6 assumes only priced Tier-W tools spend, so a `read`-only public key can still **burn the user's wallet** through "free" reads, and the per-key cap (which the design only checks before Tier-W) never fires.
**Patch.** Spend-gate on a **per-tool `incurs_cost` flag, not the tier.** Every cost-incurring tool (regardless of R/A/W) goes through the edge spend pre-check + audit. Add a `cost` scope dimension: a `read`-only key gets **`incurs_cost=false` reads only** unless it also holds `paid_read`. Mark `glossary_web_search`, `glossary_deep_research`, rerank-enabled search as `incurs_cost`. **Re-tier `glossary_web_search` consideration:** a paid, un-gated tool reachable by a bare `read` key is the exact abuse vector — at minimum require `paid_read` + spend cap.
**Severity: BLOCKER (cost-drain via read scope).** **Phase P2/P3.**

### H-C 🟠 HIGH — per-key spend attribution requires threading `key_id` to the billing record
**Symptom.** `usage_logs` is written by `usage_consumer` from the `loreweave:events:usage` stream and is keyed by **`owner_user_id`, `request_id`, `model_ref`, `operation` — there is no key/api-key dimension** (`usage_consumer.go:182-214`). The actual cost is recorded *deep* in provider-registry after the LLM call, far from the edge. So the edge can enforce a per-key cap only on its own *pre-estimates*, never on **actuals** — and a month's true per-key spend is unknowable.
**Patch.** Thread `key_id` from the edge through the whole call chain into the usage event — the **same `campaign_id` contextvar pattern already used** (set at the submit chokepoint, emitted into `job_meta`/usage fields, cleared on non-public paths). Add `mcp_key_id` to the usage event + a `usage_logs.mcp_key_id` column; the edge reconciles the per-key counter from the same stream it already drains. Until then, the per-key cap is **estimate-only** (document the gap).
**Severity: HIGH (the cap is the headline safety claim).** **Phase P3.** *(Cross-ref memory: `contextvar-attribution-merge-pattern`.)*

### H-D 🟠 HIGH — a public key inherits the owner's E0 grants → reaches *other people's* shared books
**Symptom.** Ownership guards resolve via E0 grants, so a key acting as user U can act on **any book U was granted access to**, including books **owned by someone else** who shared with U. That third party never consented to a *third-party agent* (U's API key) touching their book. Part I's tenancy story stops at "U's own data."
**Patch.** Decide the grant-inheritance policy (**OD-8**): (a) public keys are **owned-books-only** by default (drop grant-derived access unless the key has an explicit `include_shared` scope) — recommended; or (b) inherit grants but **notify the grantor** that an external agent touched their shared book; or (c) the book owner can opt out of "third-party-agent access" on shared books. Recommend **(a) owned-books-only default** + opt-in `include_shared`.
**Severity: HIGH (cross-tenant consent).** **Phase P2.**

## 14. Design holes (patch in design)

### H-E 🟠 Scope/catalog filter must **default-deny unknown tools** (fail-closed)
A provider that ships a **new** tool the edge's tier/domain map doesn't recognize would, under a denylist, leak as callable. The edge must treat any tool with no explicit tier+domain classification as **deny for public** until classified. Pairs with the gateway's prefix enforcement. **P2.**

### H-F 🟡 Domain scope is leaky across cross-domain side effects
`translation_start_extraction` **writes glossary entities**; `jobs_*` and `settings_*` are user-global (a `knowledge`-scoped key still sees translation jobs via `jobs_list`). Domain scoping at the tool boundary doesn't capture a tool's downstream writes or cross-cutting reads. **Patch:** classify each tool by the domains it *touches* (read + write), not just its prefix; `jobs_*`/`settings_*` require their own explicit scope, never implied by another domain. **P2.**

### H-G 🟡 Idempotency for Tier-A writes (headless retries duplicate)
Headless agents retry on timeout. Version-checked drafts are safe, but `book_create`, `book_chapter_create`, `composition_create_work`, `kg_propose_fact` are **not idempotent** → a retry creates duplicates. **Patch:** accept an optional `idempotency_key` (client-supplied) on Tier-A create tools; the edge can also dedup on `(key_id, tool, args_hash)` within a short window. **P2/P4.**

### H-H 🟡 Argon2id verification is a CPU-DoS vector on known-prefix wrong-secret
Slow-hash on every auth attempt means an attacker who learns a valid `key_prefix` (it's shown in the UI/logs) can force expensive Argon2id verifications. **Patch:** per-`(key_prefix, IP)` auth-failure rate-limit + a cheap pre-check (HMAC of the secret with a server pepper) before the slow verify; cache negative results briefly. **P1.**

### H-I 🟡 Project-scoped tools need `project_id` as an **arg** on the public path
The edge strips `X-Project-Id` (H-A), and the known bug `D-GW-XPROJECT-NOT-FORWARDED` means some `kg_*` tools read project from the header. A public agent has no way to set it. **Patch:** project-scoped tools must accept `project_id` as an explicit, ownership-checked **arg** for the public path (consistent with memory `gateway-drops-xprojectid-envelope`). Verify each `kg_*` tool before exposing it publicly. **P2.**

### H-J 🟡 Headless confirm re-price overshoot
A Tier-W confirm token re-prices at execute. The FE re-confirms a changed price via a new card (internal H14); a headless agent has no card. If actual > estimate×1.25, silently spending breaks the spend contract; an opaque error strands the agent. **Patch:** on re-price breach, `confirm_action` returns a **structured `price_changed` result with the new estimate + a fresh token** (re-propose), never auto-spends over the breach. The agent re-confirms explicitly. **P4.**

> **H-J contract — uniform `reprice_required` shape (P4 slice C, SHIPPED for translation).** Every **priced** confirm handler (translation `actions/confirm` is done; glossary/composition/kg priced confirm routes MUST follow) re-prices at execute and, on a breach of `actual > estimate×1.25 OR actual > estimate + $0.50` (the threshold is **BE-owned** — `transl_reprice_mult` / `transl_reprice_abs_usd`; the edge/FE never recompute it), MUST refuse-and-re-confirm with **HTTP 409 `TRANSL_REPRICE_REQUIRED`**-style body rather than spend:
> ```json
> { "code": "<DOMAIN>_REPRICE_REQUIRED", "message": "...", "status": "reprice_required",
>   "confirmed_cost_usd": 0.40, "actual_cost_usd": 0.95, "estimate": { "cost_usd": 0.95, ... } }
> ```
> (FastAPI nests this under `{ "detail": {...} }`.) This single shape lets every consumer handle reprice **uniformly**: the **edge** maps the domain 409 → `{status:'reprice_required', detail}` MCP `isError` result (auth-service `confirmReplayLabel`/`writeConfirmReplayResult` + `confirm-action.ts`); the **first-party FE** `ConfirmActionCard` detects the 409 (`status==='reprice_required'` or the `*_REPRICE_REQUIRED` code, at `body.detail` or `body` root), surfaces old→new cost, and resumes the agent with a `reprice_required` outcome so it re-proposes at the real price. The single-use token is spent on the breach, so re-confirming is always a **fresh proposal**, never a silent retry.

### H-K 🟡 Per-key spend-cap race under concurrency
Two priced calls from one key can both pass the pre-check before either records → overshoot. **Patch:** atomic edge-side reserve (Redis `INCRBY` with a check, or reuse the usage-billing reserve primitive keyed by `key_id`); accept a bounded overshoot ≤ in-flight concurrency. **P3.**

### H-L 🟡 Owner account lifecycle vs a live key
A key can outlive a **deleted/suspended** owner, or belong to an **email-unverified** user. **Patch:** the `/internal/mcp-keys/resolve` check must require `account_status='active'` (and a policy decision on `email_verified`); a deleted/suspended account invalidates all its keys immediately (bypass the 60s cache for this case). **P1.**

### H-M 🟡 MCP protocol semantics for arbitrary external clients
External MCP clients run the full handshake — `initialize`, capability/version negotiation, `tools/list`, possibly SSE notifications. Part I describes the envelope hop but not that the **edge must be a spec-compliant MCP server** to the outside (the internal `ai-gateway` already is, but the edge sits in front). Decide **stateless per-call vs session** for external clients, and pin a supported MCP protocol-version range. **Patch:** edge implements the MCP server handshake; default **stateless** (matches the internal transport); reject unsupported protocol versions cleanly. **P0.**

### H-N 🟡 Job control + cancel is unreachable for a headless agent
A public agent can **start** a priced job but `jobs_*` is read-only over MCP and `job_control` (cancel/pause) is REST/FE-only → it cannot stop a runaway job it launched. **Patch:** expose `jobs_cancel`/`jobs_pause` as Tier-A (free, reversible) MCP tools behind the `jobs` scope, so an agent can abort its own spend. **P3/P4.**

## 15. Track (lower severity / document)

- **H-O — Audit content vs privacy.** `args_hash` protects content but kills debuggability; raw args may contain book text. Store hash + a redacted shape; raw only behind an SRE break-glass. **P3.**
- **H-P — Scope-downgrade cache lag.** The 60s resolve cache means a *downgraded* (not just revoked) key keeps old scopes for ≤60s. Acceptable; document. Revocation already bypasses for the deleted-account case (H-L). **P1.**
- **H-Q — Secret-shown-once recovery.** If the create response is lost, the secret is unrecoverable → delete+recreate. Document in the UI. **P1.**
- **H-R — Header-only credential.** Reject the key in a query string (it lands in access logs); require the `Authorization` header. **P0.**
- **H-S — Catalog read leaks via a `read` key.** `jobs_list`/`settings_list_*` let a read key enumerate the user's entire job/model history across domains — it *is* the owner's data, but a narrowly-scoped key (e.g. "knowledge read") shouldn't see translation jobs. Folds into H-F (explicit `jobs`/`settings` scope). **P2.**
- **H-T — Free-tier interaction → RESOLVED by PUB-12 (Q-MONEY LOCKED).** Public keys are **BYOK-only**: the edge rejects any call resolving to a platform model / free-tier / platform-balance draw (402). A runaway/leaked key therefore cannot touch the human's free credits at all — it can only spend the user's own BYOK provider budget, further bounded by the per-key sub-cap (PUB-6). **P3 enforces the BYOK-only pre-check.**

## 16. New invariants / open decisions from this review

- **PUB-9 (new, P0):** the edge builds the outbound envelope from scratch and strips the entire inbound `X-*` namespace; it has no route to `/mcp/admin` and holds no admin token. *(H-A)*
- **PUB-10 (new, P2/P3):** spend-gating + audit key on a per-tool `incurs_cost` flag, not on the write tier; cost-incurring reads require a `paid_read` scope. *(H-B)*
- **PUB-11 (new, P3):** per-key spend is attributed by threading `mcp_key_id` into the usage event (contextvar pattern); until shipped, the per-key cap is estimate-only and labelled as such. *(H-C)*
- **OD-8 (new):** grant inheritance for public keys — owned-books-only default vs inherit-with-notify vs owner opt-out. Recommend **owned-books-only + opt-in `include_shared`.** *(H-D)*

## 17. Revised verdict

Parts I's core stands — edge + credential, reusing the internal machinery. But the review surfaces **two blockers the original design would have shipped unsafely**: **H-A** (admin-surface / inbound-header isolation — a privilege-escalation hole) and **H-B** (paid "read" tools defeat the spend cap — verified against `web_search_tool.go`). Both must land in P0–P3 DoD. **H-C** (per-key attribution needs cross-hop plumbing) and **H-D** (grant inheritance reaches third parties' shared books) are HIGH and reshape P2/P3. The remaining holes are design-level patches folded into the existing phases. Net: **8 new holes + 2 blockers + 3 new invariants + 1 new OD** — fold H-A/H-R/H-M into P0, H-D/H-E/H-F/H-G/H-I into P2, H-B/H-C/H-K/H-N/H-T into P3, H-J into P4. With these, the design is build-ready; without H-A and H-B it is not.

---

# PART III — Spike verification results (2026-06-26)

Five read-only spikes ran against the code to de-risk the load-bearing assumptions before the detailed plan. **Verdict: the architecture is sound and build-ready; spikes confirmed 4 assumptions, corrected 2, and found 1 new hole (H-U).** The detailed build plan is [04-implementation-plan.md](04-implementation-plan.md).

| Spike | Assumption | Result |
|---|---|---|
| 1 — ai-gateway contract | edge can mint envelope + forward to `/mcp` | ✅ **Confirmed.** ai-gateway reads `X-User-Id/Project/Session/Trace` from inbound headers and forwards them, synthesizing its **own** `X-Internal-Token` downstream. Token compare is **non-constant-time** (low-risk note). **Reinforces H-A:** ai-gateway trusts whatever identity the caller sends → the edge is the only control point; it must strip all inbound `X-*` and route **only** to `/mcp`, never `/mcp/admin`. |
| 2 — BFF integration | add `/mcp` → edge proxy | ✅ **Confirmed.** Mirror the chat-SSE proxy (`bodyParser:false` + `selfHandleResponse:false` already support streamable-HTTP; CORS allows `Authorization`). Concrete file:line checklist in §04. |
| 3 — confirm-token | headless self-confirm is safe | ✅ **Confirmed + 1 correction.** Token binds `UserID`+resource+payload+expiry(10m), HMAC constant-time, single-use `jti` ledger, redeemer==proposer checked *before* consume (S8 safe), pure request/response. **Correction (H-J real):** confirm **does NOT re-price** and has **no overdraft guard** → the priced-job ceiling must come from the edge per-key pre-check + the usage-billing guardrail reserve, not from confirm. **Also:** the confirm step is a REST endpoint / partly a *frontend* tool today → the edge must expose a server-side `confirm_action` path for headless agents. |
| 4 — spend attribution (H-C) | thread `mcp_key_id` like `campaign_id` | ✅ **Confirmed + 1 correction.** The `campaign_id` contextvar→`job_meta`→`usage_outbox`→`loreweave:events:usage`→`usage_logs` pipeline is the template (~7 additive chokepoints). **Correction:** `mcp_key_id` **cannot be an edge contextvar** (edge ≠ provider process); it must be an **envelope header `X-Mcp-Key-Id`** that **ai-gateway forwards** (new additive forward) → shared kits lift to ctx → provider-registry submit merges into `job_meta`. Guardrail is **owner-keyed only** today → per-key cap = edge pre-check + new `usage_logs.mcp_key_id` rollup. |
| 5 — ownership/project_id | tools enforce ownership; project_id reachable | ⚠️ **Mostly confirmed, 1 NEW hole.** `book_*`/`glossary_*`/`composition_*`/`translation_*` are **grant-aware** (E0 resolves) and take `book_id`/`project_id` as **args** ✓. **H-U (NEW, HIGH):** the knowledge **project-scoped** tools (`kg_graph_query`, `kg_schema_read`, `kg_propose_fact`, `kg_propose_edge`, `memory_*`, …) trust `ctx.project_id` as authoritative with **no user-owns-project check** + rely on the `X-Project-Id` **header** (H-I) — safe internally, **cross-tenant unsafe publicly**. **OD-8 has no in-kit toggle** — owned-books-only needs an owner-only resolver variant or a context flag. |

## 18. New findings folded into the plan

- **H-U 🟠 HIGH (NEW) — add `require_project_owner` to knowledge project-scoped tools before public exposure.** They currently trust the envelope `project_id`. For the public path, verify `X-User-Id` owns `X-Project-Id` (and promote `project_id` to an explicit ownership-checked arg per H-I, since the edge controls the header). **Phase P2; gates knowledge-tool public exposure.**
- **H-C carrier correction → `X-Mcp-Key-Id` envelope header**, forwarded by ai-gateway (small additive change), lifted by both shared MCP kits, merged into `job_meta` at the provider-registry submit chokepoint. **Phase P3; gates priced-tool public exposure.**
- **H-J → no confirm re-price exists** → the per-key spend pre-check + guardrail reserve are the *only* money ceiling; document that confirm does not re-price, and add an edge re-price-on-execute check for priced tools. **Phase P3/P4.**
- **Confirm reachability** → expose a **server-side `confirm_action`** through the edge (today it's partly a frontend tool). **Phase P4.**
- **OD-8 mechanism** → add an `owner_only` resolver variant / context flag in the shared kits (no per-call toggle exists). **Phase P2.**
- **Low-risk note:** make ai-gateway's `X-Internal-Token` compare constant-time while touching it. **P0, cheap.**

