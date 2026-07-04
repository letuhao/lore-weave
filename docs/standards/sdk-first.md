# SDK-First Standard (reusable logic lives in an SDK)

**Status:** ACTIVE · **Date:** 2026-07-04
**Governs:** where reusable logic lives — any capability used by ≥2 services goes into a shared SDK (`sdks/<lang>/`) or a shared `contracts/*` module, never copy-pasted per service. Indexed in [`README.md`](./README.md). Composes with [Scope Separation SCOPE-4](./scope-separation.md) (one logic owner per capability).

> **Why.** Copy-paste across services is the top driver of cross-service drift: `logging_config.py` is byte-identical in 3 services; the platform JWT verifier is re-implemented **8× in Go + 6× in Python**; the notification `TerminalEvent` wire struct is duplicated (its own comment admits "mirrors provider-registry's"). Each copy diverges silently. The repo already proves the fix works: `loreweave_grants` was "extracted from 3 byte-identical service copies" and each service now imports a ~45-line thin shim. This standard makes that the rule, and adds the mirror-image rule (an SDK nobody adopts is also a defect).

## Rules

- **SDK-1 · ≥2 users ⇒ SDK.** Any logic used by two or more services (or plausibly will be) MUST live in `sdks/<lang>/` or a shared `contracts/*` Go module. A new cross-service utility is a **PR into the SDK**, not a new per-service file. Per-service code is only wiring + service-specific behavior.
- **SDK-2 · Always-SDK-tier categories.** These are SDK-tier by default, never per-service: **security-critical verifiers** (platform + admin JWT, redaction, injection-sanitize), **wire types crossing a service boundary** (`TerminalEvent`, event envelopes), and **cross-service client contracts** (grant, embed, book, glossary clients — a shared base async client carrying the timeout/retry/graceful-degradation/error-wrap contract).
- **SDK-3 · Anti-orphan: if a shared module exists, ADOPT it — OR retire it.** Hand-rolling a capability that already has a shared module is a violation from the other side. Today `contracts/errors` and `contracts/dependencies/client_factory.go` exist with **zero importers** while services hand-roll the same thing — an orphan SDK is a defect: adopt it, or consciously retire it (no half-alive orphan). *(P2·A2b retired the former orphan `contracts/logging` this way — the fleet standardized on `log/slog` + `sdks/go/observability` rather than adopt its unused Field/Emit API; see [Logging](./logging.md).)*
- **SDK-4 · Polyglot mirrors move together.** This repo is Go+Python+Rust+TS. A capability with cross-language mirrors (`loreweave_grants`↔`grantclient`, `loreweave_obs`↔Go `observability`, `loreweave_llm` ×3, `loreweave_extraction` ×2, `namenorm`↔`name_normalize`) MUST **update ALL mirrors in the same change** (memory `blocked-on-sdk-field-often-self-owned`). Name the mirror pair in the PR.
- **SDK-5 · Additive + atomic bump.** SDKs are in-repo path/workspace deps (each Go SDK has its own `go.mod`; Python via `PYTHONPATH=sdks/python`). Prefer additive changes; a breaking SDK change updates every importer in the **same PR** (monorepo atomic bump); keep re-export shims to migrate call sites without churn (the `grant_client.py` thin-shim is the model).
- **SDK-6 · Target shape.** Converge duplicated logic to the `loreweave_grants` / `loreweave_obs` shape: one implementation in the SDK, a thin per-service shim that wires the singleton + settings, one identity across services (a single `GrantLevel`/tracer, not N copies).

## Known reuse-violations (the execution backlog)

Recorded in the [enterprise-hardening audit](../plans/2026-07-04-enterprise-hardening-audit.md); the SDKs to create/adopt when this standard is executed:
- **`loreweave_obs.setup_logging`** (Python, ✅ done P2·A2a) + **`sdks/go/observability`** (Go slog handler, ✅ A1) — the shared logging/trace idiom that folded the 3× copy-pasted `logging_config.py` + the `trace_id` middleware ([Logging LG-6](./logging.md)). *(The former Go orphan `contracts/logging` was retired P2·A2b, not adopted — 0 importers, superseded by slog+observability.)*
- **`loreweave_authn`** (Python) + **`contracts/platformjwt`** (Go) — one shared user-JWT verifier, replacing 6 Python + 8 Go re-implementations ([Security SEC-2](./security.md)).
- **Shared `TerminalEvent`** in `contracts/events` — imported by provider-registry + notification-service ([Notification NOTIF-1](./notification.md)).
- **Base async HTTP client** (`BaseInternalClient`) — the shared timeout/retry/graceful-degradation/error-wrap contract the per-service `*_client.py` all re-declare.
- **Adopt-or-retire the orphans:** `contracts/errors`, `contracts/dependencies/client_factory.go` (currently 0 importers). *(`contracts/logging` — retired P2·A2b.)*

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| SDK-1 no cross-service copy-paste | **to build** | near-duplicate detector in CI (jscpd/token-similarity) over `services/**`, fails when a block recurs across ≥2 `services/<name>/` prefixes — baseline seeded from the known-good SDK files |
| SDK-2 always-SDK categories | **to build** | symbol-level grep-gate (extend `ai-provider-gate.py` shape): fail on `jwt.ParseWithClaims`+`SigningMethodHS256`, `class RedactFilter`, `type TerminalEvent`, `_SECRET_PATTERNS` outside `sdks/`/`contracts/` |
| SDK-3 anti-orphan | **to build** | adoption check: assert each Python service `main.py` imports the shared logging/trace/authn SDK; assert `contracts/errors` has >0 importers OR is retired (orphan → red). *(`contracts/logging` retired P2·A2b — removed from this check; a deleted module can never satisfy >0 importers.)* |
| SDK-4 mirrors | **process** | PLAN/REVIEW checklist: a mirrored-capability change names + updates all mirrors |

## Checklist — adding/changing reusable logic
- [ ] Used by ≥2 services (or will be)? → it goes in `sdks/`/`contracts/`, not a per-service file (SDK-1)
- [ ] JWT/redaction/sanitize/wire-type/cross-service-client? → SDK-tier, no exception (SDK-2)
- [ ] A shared module already exists? → adopt it, don't hand-roll (SDK-3)
- [ ] Mirrored across languages? → update every mirror in this change (SDK-4)
- [ ] Breaking change? → bump every importer in the same PR; keep a shim (SDK-5)
- [ ] Per-service code reduced to a thin wiring shim (SDK-6)
