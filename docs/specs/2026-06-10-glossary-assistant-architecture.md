# Glossary Assistant — Architecture Design

- **Date:** 2026-06-10
- **Status:** Architecture DRAFT (pre-CLARIFY). Decision **C + dedicated mcp-gateway** locked by PO.
- **Builds on:** `GLOSSARY_AI_PIPELINE_V2_ARCHITECTURE.md` (AI-suggestions inbox, human-gate), chat-service K21 tool-loop, knowledge-service ARCH-1/2 MCP server.
- **Task size:** **XL** (new `mcp-gateway` service + glossary tools + chat rewire + FE; new service boundary; security boundary). `/loom` per phase; **`/amaw` for the write path + ownership boundary**. Build P0 (gateway) as its own task before glossary tools.

---

## 1. Problem & goal

Today the glossary AI pipeline runs **fully in background**; human curation is **manual CRUD** in the FE. The user wants a **conversational assistant**: open chat, ask it to *show* a book's glossary, then *fix a name / edit an attribute / draft a new kind or attribute* — full human-CRUD, but driven by the LLM and **always human-gated** (INV-1).

This is the **domain-copilot pattern** (Cursor/NovelCrafter): LLM + tool-calling + RAG grounding + propose→review. We already own every primitive — this design **wires glossary into the existing tool-loop**, it does not invent a new mechanism.

## 2. Decision: C (domain owns tools) + dedicated MCP-gateway

Rejected A (knowledge hosts glossary tools — leaks book-ownership into knowledge) and B (chat defines glossary tools — chat reaches into glossary internals). **C keeps DDD clean: glossary-service is the only place that knows glossary schema + book ownership, so it owns and serves its own tools.**

**Refinement (PO, 2026-06-10):** roadmap confirms a **2nd tool consumer** (composition co-writer agent) *and* **3rd+ tool providers** (book/translation/composition). With N consumers × M providers, federation cannot live inside chat-service — it would be duplicated in every consumer. So we add a dedicated **`mcp-gateway`** service: the single internal MCP face that federates all providers and routes execution. This is the **D-thin** variant — domain services still *own* their tool catalogs (C); the gateway is pure plumbing (federation + routing + auth-envelope + audit), **not** a place domain schema leaks into. Consistent with the codebase's gateway invariant (this is the *internal* sibling of `api-gateway-bff`).

## 3. Target architecture — mcp-gateway federates domain-owned tools

Two tool kinds, routed differently:
- **Backend tools** (server-executed: reads, draft-writes) → consumer → **mcp-gateway** → owning provider.
- **Frontend tools** (browser-executed, suspend→Apply/Dismiss: edits of existing canon) → advertised by the **consumer directly**, executed by the FE. These never touch the gateway (there is no server to route to — the "executor" is the human clicking Apply).

```
   consumers (single MCP client each)          frontend tools (suspend→browser)
   ┌────────────────┐  ┌──────────────────┐         ▲ propose_edit / glossary-diff
   │ chat-service   │  │ composition (soon)│         │ (advertised consumer-side,
   └───────┬────────┘  └─────────┬─────────┘         │  rendered + applied in FE)
           │  one MCP endpoint    │
           └──────────┬───────────┘
                      ▼
            ┌───────────────────────────┐   federation: merge all providers'
            │      mcp-gateway (NEW)     │   tool defs → one catalog
            │  registry: name→provider   │   routing: dispatch execute to owner
            │  auth-envelope · audit     │   scope/injection defense (one place)
            └───┬───────────────┬────────┘
                │ tools-HTTP     │ tools-HTTP (C2: definitions + execute)
                ▼                ▼
        knowledge-service   glossary-service        book / translation / … (future)
         (memory tools)      (NEW: read + draft      each: owns its tool catalog
                              + schema tools)          + its own auth/ownership
                                  │ owns schema + book ownership
                                  ▼ calls its own /v1 + /internal handlers
                              Postgres (glossary SSOT) + AI-suggestions inbox
```

**Why this shape:** every provider speaks the **same C2 tools-HTTP contract** (`GET /internal/tools/definitions` + `POST /internal/tools/execute`), so adding the gateway is mechanical and adding the 4th/5th provider is config, not code. Each provider enforces its **own** ownership (the gateway forwards identity, never decides it). A provider down → contributes 0 tools, turn proceeds (degradation contract preserved end-to-end).

**Migration note:** knowledge-service already self-hosts `/mcp` + bespoke `/internal/tools/*`. The gateway federates knowledge via its existing **bespoke tools-HTTP** (no change to knowledge needed); knowledge's direct `/mcp` can stay as a dual-run path and be retired later.

**Gateway language (OD-6):** it does no LLM inference — pure federation/routing/auth. By the language rule that's **gateway/BFF → TypeScript/NestJS** (sibling of `api-gateway-bff`, reuse its auth/observability middleware). Alternative: **Python/FastMCP**, reusing knowledge's proven MCP-server code verbatim. Lean **TS/NestJS** for rule-consistency; revisit if FastMCP reuse proves decisive.

## 4. Transport sub-decision (glossary is Go, not Python/FastMCP)

knowledge's `/mcp` is Python **FastMCP** (streamable-HTTP, JSON-RPC). Go has no FastMCP. Two ways to honour "C":

| Option | What | Cost | Verdict |
|---|---|---|---|
| **C1 — true MCP server in Go** | Use a Go MCP SDK (`modelcontextprotocol/go-sdk` or `mark3labs/mcp-go`) to expose streamable-HTTP `/mcp` | New dependency + streamable-HTTP/SSE plumbing in Go; chat reuses `mcp_execute_tool` | Purest "MCP", but heaviest |
| **C2 — bespoke tools-HTTP (MCP-shaped)** | glossary exposes `GET /internal/tools/definitions` + `POST /internal/tools/execute` (plain JSON), **identical contract to knowledge's bespoke path** | Trivial in Go (normal Chi handlers); chat reuses `execute_tool()` (non-MCP path already exists) | **RECOMMENDED** for v1 |

**Decision (OD-1): C1 — true MCP on every hop.** Every link is MCP streamable-HTTP: providers host MCP servers (knowledge Python/FastMCP exists; **glossary adds a Go MCP server** via a Go MCP SDK), and the gateway is an MCP **client** downstream + MCP **server** upstream — a clean MCP→MCP router. Cost: glossary takes on a Go MCP SDK dependency (OD-1a) rather than two plain Chi handlers; benefit: one uniform protocol end-to-end, native tool discovery, and any third-party MCP server can be federated by the gateway with zero bespoke glue. chat-service keeps using `mcp_execute_tool`, just pointed at the gateway instead of knowledge.

## 5. Tool catalog (tiered by blast radius)

Tiering follows INV-1 (no AI write reaches canon without a human action). Three tiers:

### Tier R — Read (execute server-side, no gate)
| Tool | Wraps | Notes |
|---|---|---|
| `glossary_search` | `select-for-context` (FTS + vector, mui #4) | The domain "raw search" the user asked to wire — sharper than `memory_search` for glossary |
| `glossary_get_entity` | `getEntityDetail` | entity + attributes + aliases + kind |
| `glossary_list_kinds` | `listKinds` (+ attr defs) | so the LLM knows the book's schema before proposing |

### Tier W — Write one record (propose → user Apply)
| Tool | Wraps | Gate |
|---|---|---|
| `glossary_propose_entity_edit` | `patchEntity` / `patchAttributeValue` | **frontend propose** — suspend, render diff, user Apply/Dismiss |
| `glossary_propose_new_entity` | `createEntity` (status `draft`+`ai-suggested`) | lands in **existing AI-suggestions inbox** |
| `glossary_propose_rename` | alias add + name patch | name changes ripple → review-gated |

### Tier S — Write schema (propose → **2-step confirm**)
| Tool | Wraps | Gate |
|---|---|---|
| `glossary_propose_new_kind` | `createKind` | schema-level (whole book) → stronger confirm |
| `glossary_propose_new_attribute` | `createAttrDef` | same |

**Why tiering matters:** editing one entity is low-blast; creating a *kind* changes the schema every entity is measured against. Tier S must not be a one-click Apply.

> **Open decision OD-2:** Tier-W execution = **frontend-propose** (reuse `propose_edit` suspend/resume, render a glossary diff card) vs **backend draft-write** (write `draft` immediately, user promotes in inbox). Recommend **frontend-propose for edits of existing canon**, **draft-write for new entities** (the inbox already handles new-entity review). Confirm.

## 6. Scope & security model (the load-bearing part)

glossary is keyed by **`book_id`**; knowledge tools are scoped by `project_id`. The user wants "show glossary of book X (owned by me)" — so `book_id` is **named by the user/LLM**, which means the LLM can *supply* a `book_id` argument. That is safe **only** if ownership is enforced server-side on every call.

**Invariants:**
- **SEC-1 — identity from envelope, never from LLM.** `user_id` arrives in the `/internal/tools/execute` envelope (knowledge pattern, design D3). `book_id` MAY be an LLM-supplied semantic arg, but…
- **SEC-2 — ownership enforced on every tool, every tier (incl. reads).** Each handler does `assert user owns book_id` (reuse the `/v1` ownership check) before any read or write. A non-owned `book_id` returns a tool error the LLM sees — never data, never a write.
- **SEC-3 — internal-token boundary.** chat→glossary tools authed by `X-Internal-Token` (service-to-service), `user_id` via `X-User-Id` header — exactly knowledge's MCP boundary. No user JWT crosses into the tool path.
- **SEC-4 — Tier-S/W never auto-commit.** Human action is the only path to canon (INV-1).

> **Open decision OD-3:** is `book_id` an LLM arg (flexible: "show glossary of my other book") or pinned by chat context (safest: only the book the chat is open on)? Recommend **LLM arg + hard ownership filter** — it enables the cross-book asks the user described, and SEC-2 makes it safe.

## 7. Human-in-loop flow (reuse, don't reinvent)

- **Reads** stream results inline (like memory tools today).
- **Tier-W edits** reuse the **`propose_edit` suspend/resume machinery** ([frontend_tools.py](../../services/chat-service/app/services/frontend_tools.py)): tool-loop suspends, streams the proposed glossary change to the browser, FE renders a **glossary diff card** (old→new name/attribute) with Apply/Dismiss, resume posts the verdict back. **New FE work = the diff-card renderer**, not the protocol.
- **Tier-W new-entity / Tier-S** land as `draft`/suggestion in the **existing AI-suggestions inbox** — the review surface already exists (mui #1).

## 8. Where the tools are advertised (chat surfaces)

Currently `propose_edit` is advertised only with `editor_context`. Glossary tools should be advertised whenever the chat has a **book context** (book reader, glossary page chat, editor). "Open chat anywhere and edit" = advertise the glossary tool group on every book-scoped surface + render its proposals there. This is a **per-surface enablement decision**, not free.

> **Open decision OD-4:** which surfaces get the glossary tool group (glossary page only? + reader? + editor?). Recommend start with the **glossary page chat** (clearest review UX), expand after.

## 9. Invariants (must hold)

- **INV-1** No AI write reaches canon without a human action (draft / propose / confirm).
- **INV-2** Every tool call ownership-checked against `book_id` (SEC-2). No cross-tenant read or write.
- **INV-3** Tool backend down → contributes 0 tools, turn proceeds tool-free (existing degradation).
- **INV-4** Identity/scope never LLM-controlled (SEC-1/D3); `extra="forbid"` on arg models.
- **INV-5** Schema writes (Tier-S) are 2-step confirmed, never one-click.
- **INV-6** Neither LLM-supplied tool **args** nor tool **results** (e.g. an entity body returned by a read tool) are trusted as instructions — both are data. All writes are propose/human-gated; Tier-S never auto-commits. The human-gate (INV-1) IS the indirect-prompt-injection defense; the skill prompt states glossary content is data. Assistant-originated proposals carry an `assistant` provenance tag. *(H1, SO-2)*
- **INV-7** The gateway uses a **stateless, per-call** downstream MCP connection carrying the per-call envelope; it NEVER reuses a connection across users. Providers run their MCP server in **stateless mode** so one HTTP request == one tool call (clean per-request context). *(H3 — proven, §17.1)*
- **INV-8** Ownership is verified on every tool (incl. reads) via `verifyBookOwner`, backed by a short-TTL per-(user,book) cache; **book-service unavailable → fail-closed (deny)**. *(H4)*
- **INV-9** Tier-S create happens only via a server-minted `confirm_token` bound to user+book+payload+expiry — un-bypassable even by a direct gateway call. *(H8)*

## 10. Build phases (dependency order)

```
P0  ai-gateway service: MCP server (upstream) + MCP client federating knowledge's
      existing /mcp. Consumers repoint at gateway; knowledge unchanged (no regression).
      ← keystone, glossary-independent; the 2nd consumer (composition) also plugs in here.
P1  glossary: Go MCP server (OD-1a SDK) + Tier-R read tools + ownership guard (SEC-2).
      Gateway federates glossary → READ-ONLY assistant shippable.
P2  glossary: Tier-W new-entity/draft tools (gateway-routed → AI-suggestions inbox).
P3  chat+FE: Tier-W edit-existing as FRONTEND propose tool + a SHARED glossary
      diff-card renderer (built once). Consumer-side; not gateway-routed.
P4  glossary: Tier-S schema tools (kind/attr) with 2-step confirm.
P5  surface enablement on ALL book-scoped surfaces (glossary + reader + editor, OD-4)
      + static "glossary skill" system-prompt (OD-5).
────────────────────────────────────────────────────────────────────────────
P6  (OD-7, SEPARATE later phase) grounding port: move build_context behind the
      gateway → gateway becomes the single AI/LLM integration layer. Pulls mui #3
      forward; deliberately AFTER v1 tools so it never blocks the assistant.
```
**P0 is the keystone and glossary-independent** — gateway up with knowledge as first provider, federation proven at zero new-tool risk. P1 ships the **read-only assistant**. Write tiers layer on. **P6 (grounding) is fenced off below the line** so the OD-7 scope expansion does not gate v1: the assistant ships at P5; grounding consolidation follows as its own `/loom` task.

## 11. Resolved decisions (PO, 2026-06-10)

- **OD-1 → C1 (true MCP, every hop).** Providers host real MCP servers: knowledge (Python/FastMCP, exists), glossary (Go — **needs a Go MCP SDK**, see OD-1a). Gateway is an MCP **client** to providers + MCP **server** to consumers — a pure MCP→MCP router. *Implication:* glossary's P1 grows by one Go MCP server; knowledge needs no change (already MCP).
  - **OD-1a → official `modelcontextprotocol/go-sdk`** (v1 stable, compatibility guarantee, spec-complete MCP 2025-11-25, Google-maintained). Rationale: glossary needs only the **server** half (gateway client is TS), so the SDK's known *client*-side streamable bug doesn't apply; knowledge already runs the official `mcp`/FastMCP (Python), so staying official keeps Go↔Python on the same spec + behavior; glossary is Go 1.25.0 (ample). `mark3labs/mcp-go` is the fallback.
- **OD-2 → Split.** Edit-existing-canon = **frontend propose** (suspend→Apply, consumer-side, not gateway-routed). New entity = **backend draft-write** → AI-suggestions inbox (gateway-routed).
- **OD-3 → LLM arg + hard ownership filter.** `book_id` is an LLM-supplied semantic arg; **every tool (incl. reads) enforces user-owns-book server-side** (SEC-2). Enables cross-book asks.
- **OD-4 → Every book-scoped surface** (glossary page + reader + editor) from the start. *Implication:* the glossary-proposal diff-card renderer must work on all three surfaces — front-load FE. Mitigate by building the renderer once as a shared component, mounting it per surface (no logic duplication).
- **OD-5 → Static skill + on-demand kinds.** One fixed "glossary skill" system-prompt; the book's kind/attr list is fetched via `glossary_list_kinds` when needed, never baked per-turn.
- **OD-6 → TS/NestJS** gateway (sibling of `api-gateway-bff`, reuse its middleware).
- **OD-7 → Tools + grounding port** *(H2 resolved: gateway owns grounding, but `[]`-on-failure + a retained direct chat→knowledge fallback are mandatory P6 DoD — see Part II H2).* The gateway also consolidates `build_context` (mui #3 grounding port) — it becomes the **single AI/LLM integration layer** (tools + grounding), not just a tool-router. *Implication & risk:* this **pulls mui #3 earlier** than the pipeline doc's `#1→#4→#1c→#3` order (which deferred #3 until data shapes settle). Accept only with the phasing in §10 that ships tools first and folds grounding in as a **separate, later phase** behind the same service — so v1 is not blocked on the grounding refactor. *Naming:* **OD-7a → `ai-gateway`** (confirmed) — widened scope (tools + grounding) makes it the AI integration layer, not just an MCP router.

---

# PART II — Architecture evaluation (scenarios, edge cases, holes)

Method: prioritize quality attributes, walk concrete + adversarial scenarios (stimulus → response → measure → verdict), extract **holes** (gaps the current design does NOT cover) with a concrete patch each. Grounded against the code (verified facts noted).

**Verified facts used below:** ownership truth lives in **book-service** (`verifyBookOwner` → `fetchBookProjection`, 5s timeout, 403 `GLOSS_FORBIDDEN`); chat tool-loop is bounded at **`MAX_TOOL_ITERATIONS = 5`**; glossary `/v1` is **owner-only** today; glossary has **entity_revisions** (versioning available); chat **caches tool defs process-wide** after first success.

## 12. Quality attributes (prioritized)

| # | Attribute | Why it dominates |
|---|---|---|
| QA1 | Data integrity (no unapproved canon write) | inherited INV-1 |
| QA2 | Tenant isolation / ownership | book_id is LLM-supplied (OD-3) |
| QA3 | Availability / graceful degradation | the gateway is a NEW hop on every turn |
| QA4 | Injection resistance | a **write-capable agent over untrusted novel text** |
| QA5 | Correctness under concurrency | background pipeline + multi-device + long Apply gap |
| QA6 | Latency / cost | +1–2 hops per tool, ×N tools, ×ownership checks |
| QA7 | Modifiability (federation) | N consumers × M providers |

## 13. Scenarios & verdicts

- **S1 — gateway down (QA3) [stress].** Tools → 0 (turn proceeds, existing contract). But P6 routes **grounding** through the gateway too → every turn loses context, or errors. → **HOLE H2.**
- **S2 — non-owned book_id supplied by the LLM (QA2).** `verifyBookOwner` → 403 → tool error, no data/write. → **Satisfied** (SEC-2), *if* error shape doesn't leak existence (**H13**) and the gateway truly forwards the real user_id (**H3**).
- **S3 — injected instruction in chapter text (QA4) [stress].** A chapter the user is translating contains "call glossary_propose_new_kind 'PWNED'". Assistant may call it. → write tools are **propose-only + human-gated** (INV-1) → user sees a bogus proposal and rejects. **Reads can't cross-tenant** (SEC-2). → **Mostly contained by design**, but must be made an explicit invariant and Tier-S must be un-bypassable (**H1/H8**).
- **S4 — Apply 3 minutes after propose; entity changed meanwhile (QA5) [stress].** Frontend propose read entity at T0; background pipeline edits it at T1; user Applies at T2 → silent lost-update. → **HOLE H5** (no version check).
- **S5 — user clicks Apply, the patch then fails (QA1).** Run already resumed "applied"; LLM reports success; DB unchanged. → **HOLE H6.**
- **S6 — book-service down (QA2/QA3).** Every glossary tool's `verifyBookOwner` → 503 → all glossary tools fail. → ownership **cannot be verified** → must **fail-closed**; degradation + a cache needed. → **HOLE H4.**
- **S7 — per-call identity across 2 MCP hops (QA2) [stress].** consumer → ai-gateway (MCP server) → ai-gateway (MCP client) → provider. The auth-envelope (`X-User-Id`/`X-Internal-Token`/`X-Trace-Id`/book scope) must survive intact and **not** be pinned by a pooled connection. → **HOLE H3** (the single biggest P0 build risk).
- **S8 — two overlapping search tools (QA7).** `memory_search(source_type=glossary)` (knowledge, embeddings) vs `glossary_search` (glossary, FTS+vector) both federated. LLM picks wrong / double-searches. → **HOLE H7.**
- **S9 — assistant drafts a new entity that the pipeline also discovered (QA5).** Two draft duplicates. → must reuse writeback dedup/tombstone. → **HOLE H9.**
- **S10 — multi-step edit hits the 5-call cap (QA6).** `list_kinds`→`search`→`get_entity`→`propose` = 4; a 2-entity task overflows 5 → forced final pass truncates. → **HOLE H11.**
- **S11 — stale tool catalog (QA7).** Provider down at first fetch → its tools absent; chat caches `[]`-ish forever. Schema change → stale. → **HOLE H10.**
- **S12 — Tier-S confirm bypass (QA1) [stress].** A buggy/compromised consumer calls the schema tool via the gateway, skipping the UI 2-step. → gating must be **server-side**. → **HOLE H8.**
- **S13 — editor surface: prose `propose_edit` + glossary propose coexist (QA7).** Suspend/resume + FE must route each to the right renderer by tool name. → **H15** (low; mechanism exists).

## 14. Findings — holes & patches

**Must-patch before build (fold into CLARIFY/PLAN):**

- **H1 — Injection invariant (QA4).** State **INV-6: no tool arg from the LLM is trusted; all writes are propose/human-gated; Tier-S is never auto-committed.** The human-gate + ownership scoping are the primary defense — make them explicit, don't assume.
- **H2 — Gateway SPOF on grounding (QA3). → RESOLVED (PO): keep OD-7 + mandatory fallback.** Gateway owns grounding, but it is a **hard requirement** that (a) any gateway-grounding failure returns `[]` (never errors a chat turn) and (b) a **direct chat→knowledge grounding fallback is retained** so a gateway outage degrades context, never breaks the turn. This is a P6 definition-of-done gate, not optional hardening.
- **H3 — Per-call envelope across 2 MCP hops (QA2). → RESOLVED by spike (§17.1).** Proven that a per-call TS transport carries per-call headers and a stateless Go server + own http-middleware delivers them to the tool handler ctx. No longer a risk; OD-1 stands.
- **H4 — Ownership amplification + fail-closed (QA2/QA3/QA6).** Add a short-TTL (e.g. 30–60s) per-(user,book) ownership cache in glossary; on book-service down, **fail-closed** (deny, don't fall through). Bounds the per-tool book-service hop.
- **H5 — Optimistic concurrency on Apply (QA5).** Propose carries the entity **revision id**; Apply is a version-checked patch → **409 on mismatch**, surfaced to the user ("changed since proposed, re-open"). Reuse `entity_revisions`.
- **H6 — Apply reports the real write result (QA1).** Resume the run with the **actual** outcome (saved / failed-conflict / failed-error), not merely "user clicked Apply". The LLM must not claim success on a failed write.

**Important (patch in design):**
- **H7 — Federation namespacing + search coherence (QA7).** Gateway namespaces tools by provider; pick **one canonical glossary search** and delineate (or retire) `memory_search`'s glossary path so the LLM isn't offered two overlapping tools.
- **H8 — Server-side tier gate (QA1).** Tier-S schema writes require a **two-call confirm protocol enforced by glossary** (a confirm token), not UI-only. Gateway routes blindly — the provider is the gate.
- **H9 — Assistant/pipeline draft dedup (QA5).** Assistant proposes go through the **same** `findEntityByNameOrAlias` + tombstone + inbox path as pipeline writeback.
- **H10 — Catalog freshness (QA7).** Gateway exposes a catalog **version/etag**; consumers TTL-cache (not cache-forever) and refetch on change or provider up/down.
- **H11 — Tool-iteration budget (QA6).** Re-evaluate `MAX_TOOL_ITERATIONS=5` for the glossary edit workflow; make it surface-configurable or raise for tool-rich chats so a legitimate multi-step task isn't truncated.

**Track (lower / CLARIFY notes):**
- **H12** owner-only today vs shared-book editors (sharing-service); schema writes have multi-user blast radius — confirm assistant stays owner-only for writes in v1.
- **H13** uniform "not found / not yours" error (no enumeration oracle).
- **H14** MCP protocol-version skew across providers (knowledge `mcp<2` vs glossary official go-sdk) — gateway client negotiates per provider.
- **H15** editor prose-propose + glossary-propose coexistence — FE routes by tool name (mechanism exists).

## 15. Non-risks (design already covers)

- Human-gate (INV-1) is architecturally native — it doubles as the injection + tool-error defense.
- Ownership is **not reinvented**: `verifyBookOwner` already centralizes it in book-service.
- Tool-loop is already bounded (`MAX_TOOL_ITERATIONS`), so runaway loops are capped.
- Provider-down → 0 tools degradation is the established house pattern.
- Suspend/resume for propose is battle-tested (`propose_edit`).

## 16. Verdict

The core (domain-owned tools + gateway federation + human-gated writes) is **sound and additive**. Risk concentrates in **three places the current design under-specifies**: (1) **the new gateway hop** — SPOF for grounding (H2; resolved by mandatory fallback) and per-call identity across two MCP hops (H3; **now resolved by a runnable spike, §17.1**); (2) **the write/Apply path** — concurrency + real-result reporting (H5/H6); (3) **ownership mechanics** — amplification, caching, fail-closed (H4). H1/H8 make the injection posture explicit. **Recommendation:** treat H3 as a P0 spike (prove header propagation before committing to C1-over-gateway), fold H1/H2/H4/H5/H6/H8 into the P1–P3 definitions of done, and keep H2 as a re-confirm on OD-7.

---

# PART III — Hole resolutions (folded into the design)

Each Part-II hole now has a concrete design, an owning invariant where applicable, and a phase DoD. Holes are no longer "to patch later" — they are specified here.

## 17.1 Gateway envelope contract — resolves H3, H14

The cross-hop envelope is **identity-only** (note: `book_id` is a tool **arg** per OD-3, NOT a header — this shrinks the envelope and removes a class of scope-confusion bugs):

| Header (gateway → provider, per call) | Source | Purpose |
|---|---|---|
| `X-Internal-Token` | gateway config | service-to-service auth (constant-time compare, as today) |
| `X-User-Id` | **consumer-verified from the user JWT**, forwarded | ownership identity (SEC-1: never from the LLM) |
| `X-Session-Id` | consumer | per-session scoping / audit |
| `X-Trace-Id` | consumer | trace stitching chat→gateway→provider→book-service |

- **INV-7 mechanics:** the gateway opens a **per-call (or strictly per-user-session) downstream MCP connection** with these headers bound to that connection; no connection is shared across users. Mirrors knowledge's `stateless_http=True`. 
- **H3 — RESOLVED by runnable spike (2026-06-10, go-sdk v1.6.1 + TS SDK v1.29.0).** A TS MCP client → Go MCP server roundtrip proved per-call identity reaches the Go **tool handler** through both channels, varying correctly per call:
  - **Chosen mechanism — HTTP header → context:** the Go provider runs `StreamableHTTPHandler` in **`Stateless: true`** mode behind *our own* `net/http` middleware that lifts `X-User-Id` (after `X-Internal-Token` check) into `context.WithValue`; the tool handler reads it from `ctx`. **Verified working** — keeps the envelope in HTTP headers as tabled above. The go-sdk #373 limitation only bites if you rely on the SDK to expose headers; owning the http wrapper + stateless mode sidesteps it.
  - **`Stateless: true` is REQUIRED:** it makes one HTTP request == one tool call, so the per-request context maps cleanly to the handler (a stateful SSE session would span requests and blur which request's context the handler sees).
  - **`_meta` proven as a working fallback** (TS `callTool({_meta})` → Go `req.Params.Meta`) if any field is ever better kept out of headers; not needed for v1.
  - **Consequence:** **OD-1 (true MCP every hop) stands — no bespoke HTTP relay needed.** Spike code: `.h3-spike/` (throwaway).
- **H14:** the gateway keeps a **separate MCP client/session per provider** and relies on MCP `initialize` version negotiation — knowledge (`mcp` 1.9–2.x) and glossary (official go-sdk) negotiate independently.

## 17.2 Ownership — resolves H4, H13

- **INV-8 mechanics:** `verifyBookOwner` is fronted by a per-(user_id, book_id) cache, **TTL ~60s** (ownership changes rarely). One book-service hop per book per minute regardless of how many tool calls a turn makes.
- **Fail-closed:** book-service `503` → deny (tool error), never fall through to allow.
- **H13 uniform error:** both "book not found" and "book not yours" return a single `GLOSS_NOT_ACCESSIBLE` — no existence oracle for the LLM to probe.

## 17.3 Write / Apply path — resolves H5, H6, H9

- **H5 optimistic concurrency:** `glossary_get_entity` returns `base_revision_id`; the propose payload carries it; **Apply is a version-checked patch** (`If-Match: base_revision_id`) → **409** if the entity changed since propose. Reuses existing `entity_revisions`.
- **H6 truthful resume:** the suspend/resume envelope gains an outcome enum — `applied_saved | applied_conflict | applied_error | dismissed` — and the tool result fed back to the LLM reflects it. The LLM may claim success only on `applied_saved`.
- **H9 dedup:** `glossary_propose_new_entity` routes through the **same writeback path** as the background pipeline (`findEntityByNameOrAlias` + tombstone check), lands `draft` + `ai-suggested` + `assistant`. A name that already exists / was tombstoned returns "already exists / previously rejected" instead of a duplicate.

## 17.4 Tier-S server-side gate — resolves H8

Two-call protocol, enforced by glossary (INV-9):
1. `glossary_propose_new_kind` / `_new_attribute` → returns a **`confirm_token`** (bound to user+book+payload+expiry) + a preview. **No write.**
2. After the human confirms in the UI, `glossary_confirm_schema(confirm_token)` performs the create. glossary refuses any schema create without a valid, unexpired token.

A buggy/compromised consumer routing through the gateway still cannot create a kind without the human-confirm step that mints the token.

## 17.5 Federation hygiene — resolves H7, H10

- **Naming:** every provider MUST prefix its tools (`memory_*`, `glossary_*`); the gateway rejects/aliases any collision at federation time.
- **Search coherence (H7):** `glossary_search` is the **canonical** glossary lookup (FTS+vector). On glossary-assistant surfaces, advertise the `glossary_*` group and **do NOT also advertise `memory_search`'s glossary overlap** — per-surface tool curation, not one global list.
- **Catalog freshness (H10):** the gateway exposes a **catalog version/etag**; consumers **TTL-cache (~5 min)** instead of cache-forever, and refetch on version change. When a provider is down at federation, the gateway returns a **partial** catalog flagged so consumers refetch sooner (don't cache the gap as permanent).

## 17.6 Budget & scope — resolves H11, H12, H15

- **H11:** `MAX_TOOL_ITERATIONS` becomes **per-surface config**; glossary surfaces default **10** (a real edit is `list_kinds → search → get_entity → propose` ≈ 4, and multi-entity tasks need headroom). Per-turn token budget still bounds cost.
- **H12:** v1 assistant is **owner-only for both read and write** (matches `/v1`). Shared-book editor support is **deferred** (Deferred row) — schema-write blast radius on shared readers is revisited when sharing-write lands.
- **H15:** the FE routes a suspended tool call to its renderer **by tool name** (`propose_edit` → prose card; `glossary_propose_*` → glossary diff card) — the `pending_tool_call` already carries the name.

## 18. Resolution → phase DoD map

| Phase | Must satisfy |
|---|---|
| **P0** ai-gateway | implement the **proven H3 pattern** (stateless provider + own http-middleware → ctx; per-call TS transport) · H10 versioned/partial catalog · H14 per-provider session |
| **P1** glossary read tools | INV-8 ownership cache + fail-closed (H4) · H13 uniform error · H7 canonical `glossary_search` · read-tool caps default 20/max 50 (SO-3) |
| **P2** new-entity draft | H9 writeback dedup + `assistant` provenance (H1) |
| **P3** edit-existing propose + FE | H5 version-checked Apply · H6 truthful resume · H15 renderer routing |
| **P4** Tier-S schema | INV-9 confirm-token two-call (H8) |
| **P5** surfaces + prompt | H11 per-surface iteration cap · per-surface tool curation (H7) · INV-6 injection invariant stated in skill prompt |
| **P6** grounding | H2 `[]`-on-failure + retained direct fallback · billing metering unchanged (SO-6) |

**Every phase (P0–P3):** a real cross-service **live-smoke** on a stack-up (chat + ai-gateway + glossary + book-service), not mock-only — repo VERIFY gate (SO-5).

## 19. Residual open items (CLARIFY)

- **H3 — RESOLVED by spike (§17.1); OD-1 confirmed.** No longer open.
- **H12** shared-book editors → tracked Deferred, not v1.
- Everything above is **resolved and specified**; no open architecture decisions remain.

## 20. Appendix — proven H3 pattern (from the 2026-06-10 spike)

Provider (Go, official go-sdk v1.6.1) — stateless server behind our own middleware that lifts the identity header into the tool ctx:

```go
mcpHandler := mcp.NewStreamableHTTPHandler(
    func(r *http.Request) *mcp.Server { return server },
    &mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true}, // Stateless REQUIRED
)
identity := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
    // validate X-Internal-Token (service auth) here, then:
    ctx := context.WithValue(r.Context(), userKey, r.Header.Get("X-User-Id"))
    mcpHandler.ServeHTTP(w, r.WithContext(ctx))
})
// tool handler: ctxUser, _ := ctx.Value(userKey).(string)   // ← header reached the handler
```

Gateway (TS, official sdk v1.29.0) — per-call transport carries that call's identity; no cross-user connection reuse:

```ts
const transport = new StreamableHTTPClientTransport(new URL(providerUrl), {
  requestInit: { headers: { "X-User-Id": userId, "X-Internal-Token": tok } },
});
const client = new Client({ name: "ai-gateway", version: "…" });
await client.connect(transport);
const res = await client.callTool({ name, arguments, /* _meta also works */ });
await client.close();
```

Verified output: header `hdr-A`/`hdr-B` and `_meta` `meta-A`/`meta-B` both reached the Go handler, varying per call.

## 21. Second-order items — RESOLVED (grounded in code, 2026-06-10)

All closed against the codebase. None reopens an architecture decision.

- **SO-1 — Trust boundary → RESOLVED.** Verified: chat-service `get_current_user` decodes the user JWT (HS256) → `sub`, then forwards `X-User-Id` to internal services under the internal token. The ai-gateway **inherits this exact chain**: consumers verify the JWT and forward identity; the gateway is **internal-only** (not behind `api-gateway-bff`), trusts the forwarded `X-User-Id` under the internal-token boundary, and **never re-derives identity from the LLM**. No new trust model — same as today's chat→knowledge.
- **SO-2 — Tool-result injection → RESOLVED** by extending **INV-6** (results are data, not instructions) + a skill-prompt statement. Writes stay human-gated, so a poisoned result can at worst produce a proposal the human rejects.
- **SO-3 — Read-tool caps → RESOLVED.** Verified: glossary list already paginates (`limit` default 50, **max 200**, offset + total). The read **tools** clamp tighter for the LLM path — default 20, hard max 50 (mirrors knowledge `SEARCH_LIMIT_MAX=20`) — reusing the existing `limit` param. P1 DoD.
- **SO-4 — Composition consumer → CONFIRMED REAL, scoped out of v1.** `composition-service` **exists** (Python, with clients). It is a concrete near-term 2nd consumer — which validates the gateway now. Its **tool set + review surface are its own CLARIFY** when it integrates; the gateway is already consumer-agnostic, so v1 changes nothing for it beyond providing the seam. *If composition is higher-priority than glossary-assistant, revisit phase ordering (PO call).*
- **SO-5 — Cross-service live-smoke → RESOLVED as DoD.** Spans chat + ai-gateway + glossary + book-service; the repo VERIFY gate requires a real stack-up smoke (not mock-only) at P0–P3. Folded into the §18 DoD as an explicit per-phase requirement.
- **SO-6 — Billing → RESOLVED.** The gateway does **no LLM inference** → adds **zero token cost**; LLM-token metering stays on the consumer (chat, via its `billing_client`) exactly as today. Gateway/provider calls are infra cost, not user-metered. P6 grounding is retrieval (no generation) → no double-billing. Confirm metering unchanged in P6 DoD.

### 21.1 Perf deferral (Track-2, not a blocker)

- **PERF-1 — per-call downstream connection cost.** INV-7's stateless per-call transport means each tool call does connect+`initialize`+call to the provider (proven to work in the spike). For a tool-heavy turn this stacks round-trips. v1 ships per-call (simplest, correct); if profiling shows pain, optimize to a **strictly per-user-session pooled** connection (still INV-7-compliant: never shared across users). Deferred to a perf pass.

**Status: no open architecture decisions, no unresolved holes. Ready to build.**
