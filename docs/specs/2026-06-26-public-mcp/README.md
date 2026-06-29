# Public MCP Gateway — document set

- **Date:** 2026-06-26
- **Branch:** `feat/public-mcp-gateway` (from `origin/main` @ `7bb2143c`)
- **Goal (from the user):** *"Make MCP public on the internet so other agents can use our platform without going through the FE. This feature needs a new security setting."*

This folder holds the deep-dive deliverables that scope and design that goal. Read in order:

| # | Document | What it is |
|---|---|---|
| 01 | [Platform feature catalog](01-feature-catalog.md) | Per-endpoint / per-MCP-tool enumeration of the whole platform BE + FE (excluding the game/world FE). The "what exists" inventory. |
| 02 | [Interface matrix](02-interface-matrix.md) | Every capability classified as **FE-support**, **BE-only**, and/or **MCP-support** — the decision table for what a public agent can/should reach. |
| 03 | [Public-MCP + security design](03-public-mcp-security-design.md) | CLARIFY + DESIGN for the public MCP entry point and its new auth/security model. Part II = adversarial edge-case review (2 blockers + 8 holes). Part III = 5 spike verification results + H-U. |
| 04 | [Implementation plan & fanout](04-implementation-plan.md) | Post-spike build plan: 6 phases with DoD, serial keystone vs per-provider fanout, hole→phase map, live-smoke gates. |
| 05 | [Tool scope-map](05-tool-scope-map.md) | Authoritative per-tool classification (~133 tools) from the 8-provider audit: tier · cost · scope · `public_scope_rec` · hardening worklist. The edge's scope-filter source of truth + the P2 fanout task list. |

**Decisions locked (PO, 2026-06-26):** dedicated `mcp-public-gateway` edge service · v1 = full incl. priced jobs · API keys first (OAuth P5) · owned-books-only default. Consequence: per-key spend attribution (H-C) is a hard pre-launch blocker for priced tools.

## One-paragraph orientation

Today the platform already has a **fully-built internal MCP layer**: `ai-gateway` (:8210, NestJS, internal-only) federates ~100 domain-owned MCP tools across 10 services using a stateless streamable-HTTP transport, an **envelope-only identity** model (`X-Internal-Token` for service auth + `X-User-Id` for the acting user, never from the LLM), and a **tiered write-gating** model (R = read, A = auto-write+undo, W = confirm-token-gated, S = schema/secret). The *only* consumers today are trusted internal services (chat-service, composition-service) that verify the user's JWT and forward `X-User-Id`. **The public-MCP feature is the problem of giving an *untrusted external agent* a credential that the edge can turn into that same trusted envelope — safely, with a rate/spend/scope boundary, and a write-gating story that works without a browser to render confirm cards.** Doc 03 designs exactly that.
