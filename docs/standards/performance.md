# Performance Standard (main platform)

**Status:** ACTIVE (rules) · enforcement to extend — see §Enforcement · **Date:** 2026-07-04
**Governs:** the performance controls every main-platform service upholds — timeouts, resilience, bounded results, async hygiene, caching, latency budgets. Indexed in [`README.md`](./README.md); current-state in [audit](../plans/2026-07-04-enterprise-hardening-audit.md#area-4--performance).

> **Why.** A strong perf apparatus exists but is **MMO/foundation-scoped + Go/Rust-only + mostly advisory** for the product. The one enforced runtime rule (timeout-discipline) doesn't cover Python — yet the latency-heavy services (chat, knowledge, translation, composition) are Python and the highest-risk calls (LLM/embed/rerank) are unlinted. Most machinery exists; it just needs pointing at the product + extending to Python.

## Rules

- **PERF-1 · Timeouts everywhere, all languages.** Every outbound call (HTTP, DB, Redis, LLM, S3) declares an explicit timeout. The un-inspectable `httpx.AsyncClient(**kwargs)` / bare `db.Query("...")` without a timeout is banned.
- **PERF-2 · Resilience contract covers product deps.** Every real main-platform dependency (book↔translation, →glossary, →knowledge-gateway, →provider-registry, →Neo4j, →Redis, →MinIO) is registered in `contracts/dependencies/matrix.yaml` with timeout/breaker/retry/bulkhead, and consumers route through the client factory.
- **PERF-3 · Bounded results by construction.** Every list/search endpoint paginates with an **enforced max cap**; an unbounded `SELECT` without `LIMIT` on a user-facing path is a defect. Large sets use cursor/keyset pagination. (This is what the reactive `parseLimitOffset` clamp + `limit le=100` fixes were patching one-by-one.)
- **PERF-4 · No blocking in async.** No blocking call (sync DB driver, `requests`, `time.sleep`, CPU loop) inside an `async def` handler; CPU-bound work goes to `asyncio.to_thread`/executor (the kg_unify fix is the reference).
- **PERF-5 · Latency SLOs per route class.** Each HTTP route declares a tier (interactive / standard / batch) with a p95/p99 budget in a SoT, checked against real metrics (adopt the DP-T tier idea for the platform).
- **PERF-6 · Caching on hot paths.** Read hot-paths (entity/glossary/catalog reads) register a key in `contracts/cache/keys.yaml` with TTL + invalidation trigger; any new cache needs a registered key.
- **PERF-7 · Payload caps.** A standard request-body limit (413) at the gateway + per-route overrides; response/MCP-return size caps per the [Context Budget Law](../specs/2026-07-03-context-budget-law.md) / [MCP Tool I/O OUT-1/2](./mcp-tool-io.md).
- **PERF-8 · Capacity budgets are real + SLO-linked.** `contracts/capacity/budgets.yaml` values are meaningful (not V1 stubs) and tied to a measured SLO; pool sizes tied to the budget.

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| PERF-1 timeouts (Go/Rust) | **ENFORCED** | `scripts/timeout-discipline-lint.sh` (CI-blocking) |
| PERF-1 timeouts (Python) | **to build (P1)** | **extend** the lint to `httpx`/`aiohttp`/`asyncpg` without `timeout=` — the single highest-leverage change (closes the Go/Rust-vs-Python gap; LLM calls are Python) |
| PERF-3 pagination cap | **to build (P1)** | `pagination-cap-lint` — FastAPI list routes whose `limit` lacks an `le=` bound; Go list SQL without a clamped limit |
| PERF-4 blocking-in-async | **to build (P1)** | `blocking-in-async-lint` — known-blocking calls inside `async def` (mirrors the existing logging/tracing lint shape) |
| PERF-2 resilience | **contract exists, WARN-only, MMO-scoped** | register platform deps in `matrix.yaml` + flip `dependency-registry-lint` → error |
| PERF-5 latency SLO | **to build (P2)** | `contracts/slo/latency.yaml` SoT + presence/shape check + p95 assertion in perf-nightly; k6 smoke on real platform HTTP endpoints (advisory→blocking on the top-level latency check) |
| PERF-8 capacity | **presence-only** | `capacity-budget-lint.sh` checks a row exists; extend to validate numbers vs SLO |

## Checklist — a new endpoint / outbound call
- [ ] Every outbound call has an explicit timeout (PERF-1)
- [ ] New dependency registered in the resilience matrix (PERF-2)
- [ ] List/search paginates with an enforced max cap (PERF-3)
- [ ] No blocking call in an async handler (PERF-4)
- [ ] Route declares a latency tier + p95 budget (PERF-5)
- [ ] Hot-path cache has a registered key + TTL (PERF-6)
- [ ] Body-size cap applies; return size bounded (PERF-7)
