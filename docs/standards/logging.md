# Logging Standard

**Status:** ACTIVE (rules) · enforcement to build — see §Enforcement · **Date:** 2026-07-04
**Governs:** how every service (Go/Python/TS) and the frontend emit operational logs — structure, correlation, redaction, levels — and the operational-vs-audit split. (LLM-call payload logging is the separate [LLM Call Logging Standard](./llm-call-logging.md).) Indexed in [`README.md`](./README.md); current-state in [audit](../plans/2026-07-04-enterprise-hardening-audit.md#area-2--general-logging).

> **Why.** The fragmentation is not "no standard" — it's **three competing Go idioms** (`contracts/logging` with 0 adopters, fleet `slog`, raw `log.Printf`), a **3-tier Python spectrum** (structured / partial / `basicConfig` plain), and TS/frontend `console.*`. Plus two unreconciled correlation-id namespaces so Go logs don't join their traces. This picks ONE idiom per language and makes trace-correlation + redaction non-optional.

## Rules

- **LG-1 · Structured JSON everywhere, one envelope.** Every service log line is JSON `{ts, level, msg, service, trace_id, span_id, correlation_id, fields{}}` (the envelope already defined in `contracts/logging/doc.go`). **Banned in service code:** `print` / `console.*` / `fmt.Println` / bare `log.Print` / plain-text `basicConfig`.
- **LG-2 · One correlation model — OTel is SSOT, auto-injected.** The OTel trace/span id is the single correlation source and is **auto-injected into every log line** (a Go `slog` handler reading span context; a Python filter reading the current OTel trace id). The bespoke `X-Trace-Id` scheme is retired or aliased to W3C `traceparent` so Loki logs ↔ Tempo traces join.
- **LG-3 · Trace-id propagated across every hop.** Inbound HTTP middleware + outbound transport + AMQP carrier inject/extract, wired in **every** service (the seams exist: `observability.ChiMiddleware`, `AMQPCarrier`, `TraceIdMiddleware`) — not the current subset.
- **LG-4 · Source-side secret/PII redaction is non-optional.** Use a **typed tagged-field** API (the `contracts/logging` `FieldKindPII`/`Redactor` model), not ad-hoc regexes. The Vector ingest scrubber (`infra/vector/scrubber_patterns.yaml`) is kept only as defense-in-depth (it is strictly weaker than typed-source redaction).
- **LG-5 · Level discipline.** Env-driven `LOG_LEVEL`; DEBUG off in prod (config/build guard); ERROR always carries a stack trace (`logger.exception`/`exc_info` in Python, error attr in Go).
- **LG-6 · One shared logger per language, not copy-paste.** A shared SDK, not per-service re-declared config: Go → a `sdks/go/observability` helper returning a pre-wired `slog` handler (service name + span-context trace_id + Redactor); Python → promote `logging_config.py` into `sdks/python/loreweave_obs.setup_logging()`; TS → a `nestjs-pino` module with trace-id from OTel.
- **LG-7 · Audit ≠ operational.** Operational logs → stdout→Vector→Loki. **Audit events** (admin actions, security events, **tenant-boundary crossings**) → the append-only scrubbed `*_audit` meta tables via the `contracts/meta` scrubber contract (raw text never stored — only `*_raw_hash` + `*_scrubbed`). Extend audit coverage to domain tenant boundaries (book/glossary/sharing currently emit none).

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| LG-1 no `print`/`console.*`/`basicConfig`-plain | **revive+build (P1)** | `scripts/logging-discipline-lint.sh` exists but is **warn-mode, unwired, premise contradicts the fleet** — fix its premise (slog, not `contracts/logging`), add `console.*`(TS) + `basicConfig`-plain(Py) + "service main sets JSON slog default" checks, **flip to error-mode + wire into pre-commit + CI** |
| LG-2/3 trace-id present in log lines | **to build (P1)** | extend the `observability-inventory-lint` model to logs (every service declares structured setup + trace-id middleware wired) |
| LG-4 redaction | **to build (P1)** | a source-side redaction test (mirror `contracts/logging/prod_test.go` — PII never reaches sink in prod build) run against each service's actual logger init |
| LG-7 audit tables | **ENFORCED** | `pii-classify-lint` + role-REVOKE on `*_audit` + `contracts/meta/scrubber.go` (no raw accessor) |

## Checklist — a service's logging setup
- [ ] Calls the shared logger SDK (LG-6); JSON envelope (LG-1)
- [ ] Trace-id middleware wired on HTTP + AMQP; auto-injected into log lines (LG-2/3)
- [ ] Typed PII/secret redaction at source (LG-4)
- [ ] `LOG_LEVEL` env-driven; errors carry stack traces (LG-5)
- [ ] Audit events go to the `*_audit` tables via the scrubber, not stdout (LG-7)
- [ ] No `print`/`console.*`/`basicConfig`-plain (LG-1)
