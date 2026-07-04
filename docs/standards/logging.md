# Logging Standard

**Status:** ACTIVE (rules) · enforcement to build — see §Enforcement · **Date:** 2026-07-04
**Governs:** how every service (Go/Python/TS) and the frontend emit operational logs — structure, correlation, redaction, levels — and the operational-vs-audit split. (LLM-call payload logging is the separate [LLM Call Logging Standard](./llm-call-logging.md).) Indexed in [`README.md`](./README.md); current-state in [audit](../plans/2026-07-04-enterprise-hardening-audit.md#area-2--general-logging).

> **Why.** The fragmentation was not "no standard" — it was **three competing Go idioms** (`contracts/logging` with 0 adopters, fleet `slog`, raw `log.Printf`), a **3-tier Python spectrum** (structured / partial / `basicConfig` plain), and TS/frontend `console.*`. Plus two unreconciled correlation-id namespaces so Go logs don't join their traces. This picks ONE idiom per language and makes trace-correlation + redaction non-optional.
>
> **P2·A2b resolution (2026-07-05):** the Go fork is settled — `contracts/logging` (the typed Field/Emit module, 0 adopters) was **RETIRED**; the fleet standardized on **`log/slog` wired via `sdks/go/observability`** (`observability.SetupLogging` — the A1 span-reading handler that injects `otel_trace_id`). Python settled on `loreweave_obs.setup_logging` (A2a). References below that named `contracts/logging` files now point at `sdks/go/observability`; its retired Redactor (git history, cycle-32) is the design template for the still-to-build LG-4 Go source-side redaction.

## Rules

- **LG-1 · Structured JSON everywhere, one envelope.** Every service log line is JSON `{ts, level, msg, service, otel_trace_id, …fields}` (Go: slog's `JSONHandler` + the `observability` trace handler; Python: `loreweave_obs.setup_logging`). **Banned in service code:** `print` / `console.*` / `fmt.Println` / bare `log.Print` / plain-text `basicConfig`.
- **LG-2 · One correlation model — OTel is SSOT, auto-injected.** The OTel trace/span id is the single correlation source and is **auto-injected into every log line** (a Go `slog` handler reading span context; a Python filter reading the current OTel trace id). The bespoke `X-Trace-Id` scheme is retired or aliased to W3C `traceparent` so Loki logs ↔ Tempo traces join.
- **LG-3 · Trace-id propagated across every hop.** Inbound HTTP middleware + outbound transport + AMQP carrier inject/extract, wired in **every** service (the seams exist: `observability.ChiMiddleware`, `AMQPCarrier`, `TraceIdMiddleware`) — not the current subset.
- **LG-4 · Source-side secret/PII redaction is non-optional.** Use a **typed tagged-field** API (design template: the retired `contracts/logging` `FieldKindPII`/`Redactor` model, in git history — to be rebuilt on `sdks/go/observability`), not ad-hoc regexes. The Vector ingest scrubber (`infra/vector/scrubber_patterns.yaml`) is kept only as defense-in-depth (it is strictly weaker than typed-source redaction). **Status: still to-build for Go** (the fleet has trace-correlated slog via A1, but source-side typed redaction is not yet wired).
- **LG-5 · Level discipline.** Env-driven `LOG_LEVEL`; DEBUG off in prod (config/build guard); ERROR always carries a stack trace (`logger.exception`/`exc_info` in Python, error attr in Go).
- **LG-6 · One shared logger per language, not copy-paste.** A shared SDK, not per-service re-declared config: Go → a `sdks/go/observability` helper returning a pre-wired `slog` handler (service name + span-context trace_id + Redactor); Python → promote `logging_config.py` into `sdks/python/loreweave_obs.setup_logging()`; TS → a `nestjs-pino` module with trace-id from OTel.
- **LG-7 · Audit ≠ operational.** Operational logs → stdout→Vector→Loki. **Audit events** (admin actions, security events, **tenant-boundary crossings**) → the append-only scrubbed `*_audit` meta tables via the `contracts/meta` scrubber contract (raw text never stored — only `*_raw_hash` + `*_scrubbed`). Extend audit coverage to domain tenant boundaries (book/glossary/sharing currently emit none).

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| LG-1 no `print`/`console.*`/`basicConfig`-plain | **partial (P2·A2a/A2b)** | `scripts/logging-discipline-lint.sh` — **premise fixed (slog+`observability`, not `contracts/logging`; A2b)**, `basicConfig`-plain(Py) is HARD-blocking + CI-wired (A2a). REMAINING: `console.*`(TS) check + "service main sets JSON slog default" check + flip the SOFT bare-print class to error-mode after a sweep |
| LG-2/3 trace-id present in log lines | **to build (P1)** | extend the `observability-inventory-lint` model to logs (every service declares structured setup + trace-id middleware wired) |
| LG-4 redaction | **to build (P1)** | a source-side redaction test (the retired `contracts/logging/prod_test.go` in git history is the template — PII never reaches sink in prod build) run against each service's actual logger init on `sdks/go/observability` |
| LG-7 audit tables | **ENFORCED** | `pii-classify-lint` + role-REVOKE on `*_audit` + `contracts/meta/scrubber.go` (no raw accessor) |

## Checklist — a service's logging setup
- [ ] Calls the shared logger SDK (LG-6); JSON envelope (LG-1)
- [ ] Trace-id middleware wired on HTTP + AMQP; auto-injected into log lines (LG-2/3)
- [ ] Typed PII/secret redaction at source (LG-4)
- [ ] `LOG_LEVEL` env-driven; errors carry stack traces (LG-5)
- [ ] Audit events go to the `*_audit` tables via the scrubber, not stdout (LG-7)
- [ ] No `print`/`console.*`/`basicConfig`-plain (LG-1)
