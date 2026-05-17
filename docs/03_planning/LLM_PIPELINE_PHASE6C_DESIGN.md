# LLM Pipeline — Phase 6c: OpenTelemetry tracing (foundation + 6c-α)

> Status: DESIGN (session 57 cycle 8). Parent: `LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §6 row 6c.
> This doc covers the **6c foundation** and the **6c-α** sub-cycle in detail; 6c-β/γ are outlined in §8.

---

## 1. Why

The monorepo has **zero** distributed tracing today (grep-confirmed: no `opentelemetry`
import in any of the 16 services or 2 SDKs). When an LLM job misbehaves — a slow
upstream, a guardrail 402, a stuck `running` row — there is no way to follow one
request across `api-gateway-bff → provider-registry → worker → usage-billing →
RabbitMQ → notification-service`. Logs are per-service and uncorrelated.

Phase 6c builds a **whole-monorepo** OpenTelemetry tracing foundation: every service
emits spans into a shared `trace_id`, exported to Grafana Tempo, viewed in Grafana.

## 2. Scope decision (CLARIFY)

| Question | Decision |
|---|---|
| Breadth | **Whole monorepo** — all 16 services + both SDKs eventually. |
| Backend | **Grafana Tempo + Grafana**, fronted by an **OTel Collector** (services stay backend-agnostic). |
| Structure | **Foundation-first, 3 sub-cycles.** This pass = **6c-α**. |

### Sub-cycle slicing

| Sub-cycle | Deliverable | Effort |
|---|---|---|
| **6c-α** *(this cycle)* | Collector + Tempo + Grafana in docker-compose; the shared Go module `sdks/go/observability`; instrument **provider-registry-service** + **usage-billing-service** end-to-end. | XL |
| **6c-β** | Roll the shared Go module to the ~8 remaining Go services + the Go SDK (`llmgw`); RabbitMQ **consumer** extraction in notification-service. | L |
| **6c-γ** | Python services (chat, knowledge, video-gen, worker-ai) + Python SDK; TypeScript api-gateway-bff. | L |

provider-registry + usage-billing are chosen for 6c-α because between them they
exercise **every** propagation boundary (§5): inbound HTTP, outbound HTTP, a
detached worker goroutine, and a RabbitMQ producer. If the pattern holds here it
holds for the wide-but-shallow rollout in 6c-β/γ.

## 3. Architecture

```
                         ┌───────── docker-compose (dev) ─────────┐
 provider-registry ──OTLP─┤                                       │
 usage-billing  ─────OTLP─┤  otel-collector ──► tempo ◄── grafana  │
 (6c-β/γ: all others)─────┤   :4317/:4318                  :3000   │
                         └────────────────────────────────────────┘
```

- Services export OTLP/HTTP to the **Collector** (`otel-collector:4318`).
- The Collector batches and forwards to **Tempo**.
- **Grafana** reads Tempo via a provisioned datasource; trace search UI at `:3000`.
- A service with **no** `OTEL_EXPORTER_OTLP_ENDPOINT` set uses a **no-op tracer
  provider** — dev without the observability stack still boots (mirrors the
  existing optional-`RabbitMQURL` / optional-`audioCache` pattern in `main.go`).

### 3.1 docker-compose additions (`infra/`)

| Service | Image | Config file (NEW) |
|---|---|---|
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.123.0` | `infra/otel/collector-config.yaml` |
| `tempo` | `grafana/tempo:2.6.1` | `infra/otel/tempo.yaml` |
| `grafana` | `grafana/grafana:11.4.0` | `infra/otel/grafana-datasources.yaml` (provisioning) |

- Pin image tags (no `:latest` — reproducible dev).
- `grafana` port `3000` collides with **ContextHub MCP** (`mcp_url: http://localhost:3000`).
  → expose Grafana on host **`3200`** (`3200:3000`); internal port unchanged.
- Collector OTLP receivers: gRPC `4317` + HTTP `4318`. Services use HTTP `4318`.
- Tempo single-binary mode, local filesystem block storage (dev only — not durable).
- One new env var consumed by the instrumented services:
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`
  It is a **standard OTel SDK env var** — read by the SDK directly, NOT threaded
  through each service's `config.go` struct. The **service name** is NOT taken
  from env: it is the explicit `InitTracer(ctx, serviceName)` argument (§3.2) —
  one source of truth, set in each service's `main.go`. (`OTEL_SERVICE_NAME` is
  deliberately not set, to avoid a second, divergeable source.)

### 3.2 Shared Go module — `sdks/go/observability`

New Go module `github.com/loreweave/observability`, package `observability`,
sibling of the existing `sdks/go/llmgw`. Each consuming service adds it via a
`replace` directive (mirror the `llmgw` wiring already used by book-service).

Public API (small, deliberately):

```go
// InitTracer configures the global OTel TracerProvider + W3C propagator from
// standard OTEL_* env vars and returns a shutdown func. With no
// OTEL_EXPORTER_OTLP_ENDPOINT set it installs a no-op provider and returns a
// no-op shutdown — the caller never branches on "is tracing on".
func InitTracer(ctx context.Context, serviceName string) (shutdown func(context.Context) error, err error)

// HTTPTransport wraps base (nil → http.DefaultTransport) so outbound requests
// carry traceparent and emit a client span. Used for the billing HTTP client.
func HTTPTransport(base http.RoundTripper) http.RoundTripper

// ChiMiddleware is the inbound-HTTP server middleware: extracts traceparent,
// starts a server span, and (after routing) names it by the chi route
// pattern. Added in Router(). Takes no service name — that lives on the
// resource set by InitTracer.
func ChiMiddleware() func(http.Handler) http.Handler

// Tracer returns the named tracer for hand-rolled spans (e.g. the job span).
func Tracer(name string) trace.Tracer

// Inject writes the current span context of ctx into any TextMapCarrier —
// the amqp-free seam used by the RabbitMQ producer (§5d). Extract is its dual.
func Inject(ctx context.Context, carrier propagation.TextMapCarrier)
func Extract(ctx context.Context, carrier propagation.TextMapCarrier) context.Context
```

Design notes:
- `InitTracer` uses `otlptracehttp` (no gRPC dependency weight) + a batching
  span processor + a `resource` carrying `service.name` (from the `serviceName`
  arg — the single source of truth).
- `InitTracer` **always** installs the global W3C TraceContext propagator —
  including in no-op mode. No-op mode degrades the *exporter* only; context
  propagation (incoming `traceparent` extraction, outgoing injection) must
  never depend on whether an OTLP endpoint is set, or a partially-rolled-out
  monorepo would drop trace continuity at every uninstrumented hop. The no-op
  *TracerProvider* still produces non-recording spans with an invalid
  SpanContext — so in pure no-op mode there is simply no trace to propagate,
  which is correct; the unconditional propagator matters the moment any one
  service in a chain has the exporter on.
- `ChiMiddleware` starts the server span via `otelhttp`, then sets the span
  name from `chi.RouteContext(r.Context()).RoutePattern()` **after**
  `next.ServeHTTP` returns. The route pattern is not known at span-start
  (chi has not matched the route yet), so a start-time `otelhttp`
  `WithSpanNameFormatter` *cannot* see it — the name must be set post-routing
  (this is what `otelchi`-style middleware does). Raw-path span names explode
  cardinality; the route template (`POST /v1/llm/jobs`) is the right grain.
- `sdks/go/observability/go.mod` **pins** the `go.opentelemetry.io/otel*`
  versions (core SDK, `otlptracehttp`, `otelhttp`). Consuming services inherit
  those exact versions through the `replace`d module; see §10 for the
  version-skew risk.
- The module imports **no** `amqp091-go` — RabbitMQ stays an application concern.
  `Inject`/`Extract` operate on the generic `propagation.TextMapCarrier`; the
  provider-registry notifier supplies a 6-line `amqp.Table` carrier adapter locally.

## 4. The trace, end to end (target shape after 6c-α)

```
trace 〈one trace_id〉
└─ SERVER  POST /v1/llm/jobs            (provider-registry, chi middleware)
   ├─ CLIENT POST /internal/billing/guardrail/reserve   (provider-registry → usage-billing)
   │  └─ SERVER POST /internal/billing/guardrail/reserve (usage-billing, chi middleware)
   └─ INTERNAL llm.job.process          (worker goroutine — re-rooted, §5c)
      ├─ CLIENT POST /internal/billing/guardrail/reconcile
      │  └─ SERVER … (usage-billing)
      └─ PRODUCER llm.job.terminal-event  (RabbitMQ publish, traceparent injected)
```

The `SERVER POST /v1/llm/jobs` span ends when the 202 response returns; the
`llm.job.process` span lives on independently in the **same trace** (sibling under
the submit span's context). 6c-β's notification-service consumer will later attach
a `CONSUMER` span under the injected `traceparent`, closing the loop.

## 5. The four propagation boundaries

This is the heart of 6c — each is a place a `trace_id` can be silently dropped.

### 5a. Inbound HTTP (server)
`server.go Router()` adds `observability.ChiMiddleware(serviceName)` immediately
after `middleware.RealIP` and before `middleware.Recoverer` (so a panic span is
still recorded). The middleware extracts `traceparent` from request headers; an
un-traced caller (any not-yet-instrumented service in 6c-α) just starts a fresh
root span — no failure.

### 5b. Outbound HTTP (client)
`billing.NewGuardrailClient` builds its `*http.Client` with
`Transport: observability.HTTPTransport(nil)`. Every reserve/reconcile/release/record
call then carries `traceparent` and emits a `CLIENT` span. The existing 5s
`Timeout` is preserved. **Audit note:** `client.go:198` already uses
`http.NewRequestWithContext(ctx, …)` — the ctx is threaded, so the transport sees
the active span with no handler changes.

### 5c. Goroutine bridge — the load-bearing fix
`jobs_handler.go:226` spawns `s.jobsWorker.Process(bgCtx, …)` where `bgCtx` is a
**fresh `context.Background()`** (the request ctx would be cancelled when the 202
returns — the worker must outlive it). That fresh context carries **no span** →
the job trace would break into two disconnected traces.

Fix: at submit, capture the span context and re-root the worker context:
```go
// in the submit handler, before the goroutine:
spanCtx := trace.SpanContextFromContext(r.Context())
bgCtx := trace.ContextWithSpanContext(context.Background(), spanCtx)
```
Then `Worker.Process` opens its own span as the first statement:
```go
ctx, span := observability.Tracer("jobs").Start(ctx, "llm.job.process",
    trace.WithAttributes(attribute.String("llm.operation", operation),
        attribute.String("job.id", jobID.String())))
defer span.End()
```
`bgCtx` carries only the **SpanContext** (trace_id + parent span_id + flags), not
the request's cancellation/deadline — exactly what a detached worker wants. The
`ProcessAudioInline` path (`worker_audio.go`) gets the identical bridge.

**Streaming path.** `POST /v1/llm/stream` is the *other* LLM entry point and it
detaches work too: `stream_billing.go`/`stream_handler.go` run `settle` on a
background context (so a client disconnect cannot cancel the spend reconcile).
That is the same goroutine-detach as above — without the bridge, `settle` emits
an orphan trace disconnected from the stream's SERVER span. 6c-α applies the
identical SpanContext bridge to the streaming `settle` and wraps it in an
`llm.stream.settle` span. (`ChiMiddleware` is global, so the streaming
endpoint's inbound SERVER span needs no extra work.)

### 5d. RabbitMQ producer
`rabbitMQNotifier.PublishTerminal` injects `traceparent` into the AMQP message
`Headers` (`amqp.Table`) via a local carrier adapter over `observability.Inject`.
The header rides along harmlessly until 6c-β's consumer reads it. A `PRODUCER`
span (`llm.job.terminal-event`) wraps the publish.

## 6. Files (6c-α)

**NEW (8):**
- `sdks/go/observability/go.mod`, `observability.go` (the module + API §3.2),
  `observability_test.go`.
- `infra/otel/collector-config.yaml`, `infra/otel/tempo.yaml`,
  `infra/otel/grafana-datasources.yaml`.
- `docs/03_planning/LLM_PIPELINE_PHASE6C_DESIGN.md` (this doc).

**MOD (≈12):**
- `infra/docker-compose.yml` — 3 new services + 1 env var on provider-registry
  + usage-billing; Grafana host port `3200`.
- provider-registry: `go.mod`/`go.sum` (+`observability` replace + otel deps),
  `cmd/.../main.go` (`InitTracer` + deferred shutdown), `internal/api/server.go`
  (`ChiMiddleware`), `internal/api/jobs_handler.go` (goroutine bridge §5c),
  `internal/api/stream_handler.go` + `internal/api/stream_billing.go`
  (streaming `settle` goroutine bridge + `llm.stream.settle` span, §5c),
  `internal/jobs/worker.go` (`llm.job.process` span; `ProcessAudioInline` span),
  `internal/jobs/notifier.go` (AMQP `traceparent` inject + producer span),
  `internal/billing/client.go` (`HTTPTransport`).
- usage-billing: `go.mod`/`go.sum`, `cmd/.../main.go`, `internal/api/server.go`.

usage-billing is server-only for 6c-α (its sweeper goroutine is internal — no
cross-service edge — and stays untraced until a need surfaces).

## 7. Test plan (6c-α)

Go unit tests (`sdks/go/observability/observability_test.go` + per-service).

> **Test-harness rule.** Every span-producing test (#3, #5, #6, #7) installs an
> explicit in-memory `tracetest` `TracerProvider` + the W3C propagator — it must
> NOT rely on `InitTracer`. In the test environment no `OTEL_EXPORTER_OTLP_ENDPOINT`
> is set, so `InitTracer` yields a **non-recording no-op provider** whose spans
> have an invalid (zero) SpanContext — under which trace_id / parent-child
> assertions pass *vacuously* (empty == empty). A real recording provider is
> mandatory for these tests to prove anything.

1. `InitTracer` with no `OTEL_EXPORTER_OTLP_ENDPOINT` → no-op provider, shutdown
   returns nil, no panic — **and** the global W3C propagator is still installed
   (`otel.GetTextMapPropagator()` is non-noop).
2. `InitTracer` with an endpoint set → real provider; shutdown is idempotent
   (second call returns nil, no panic).
3. `Inject`→`Extract` round-trip: under a recording tracetest provider, start a
   span, `Inject` its context into a `MapCarrier`, `Extract` into a fresh
   context; assert the extracted `SpanContext.IsValid()` **and** its `TraceID`
   equals the original. (The `IsValid()` assertion is what makes a vacuous
   empty==empty pass impossible.)
4. The AMQP carrier adapter (provider-registry-local) round-trips a `traceparent`
   through an `amqp.Table` (write keys, read them back).
5. Goroutine bridge: start a recording span inside a **cancellable** source
   context; build `bgCtx` per §5c; then **cancel the source context** and assert
   (a) `bgCtx.Err() == nil` — the worker context survives the request ending —
   and (b) a child span started under `bgCtx` shares the parent span's trace_id.
   **(a) is the real regression-lock**: it fails the moment someone re-passes
   `r.Context()` instead of `context.Background()`.
6. `ChiMiddleware` over a tracetest exporter: a request produces exactly one
   `SERVER` span named by the chi route pattern (not the raw path); an inbound
   `traceparent` becomes the span's parent (continuation, not a new root).
7. `HTTPTransport`: under a recording tracetest provider, an outbound request
   through an `httptest` server carries a `traceparent` header whose trace_id
   matches the caller's active span, and records a `CLIENT` span.

Verification: `go build/vet/test` green for `sdks/go/observability` + both
services. The docker-compose additions get a `docker compose config` lint **and**
a one-shot `docker compose up otel-collector tempo grafana` boot check at VERIFY
(the stack must at least start cleanly); the full submit-a-job-see-the-connected-
trace run stays a manual smoke (`D-PHASE6C-ALPHA-SMOKE`, §9).

## 8. 6c-β / 6c-γ outline (not built this cycle)

- **6c-β** — add the `observability` `replace` + `InitTracer` + `ChiMiddleware` to
  the remaining Go services; instrument the `llmgw` Go SDK's HTTP client; add the
  RabbitMQ **consumer** span in notification-service (`Extract` from headers).
- **6c-γ** — Python: `opentelemetry-distro` + `opentelemetry-instrumentation-fastapi`
  + `-httpx`/`-requests`, a shared `loreweave_obs` helper in the Python SDK area;
  TypeScript: `@opentelemetry/sdk-node` auto-instrumentation for the NestJS gateway.
  The W3C `traceparent` contract from 6c-α means no cross-language glue is needed.

## 9. Deferred items proposed

| ID | What | Target |
|---|---|---|
| `D-PHASE6C-ALPHA-SMOKE` | Manual smoke. **Enable (two steps):** (1) `--profile observability`, (2) set `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` — both, or Grafana is empty. Then submit a job + confirm one connected trace (submit → reserve → `llm.job.process` → reconcile → `llm.job.terminal-event`) in Grafana, and that the worker span is a child of the inbound SERVER span (closes the `D-PHASE6C-JOB-SPAN-PARENTAGE` gap too). | 6c-α follow-up OR first integration-env run |
| `D-PHASE6C-JOB-SPAN-PARENTAGE` | No automated test proves the full chain `jobs_handler bridges → worker opens llm.job.process as a child of the SERVER span`. The pieces are unit-tested (`DetachedContext`, `ChiMiddleware`, `Tracer.Start`); the wiring is not — a `Worker`-harness test is heavy. Verified by `D-PHASE6C-ALPHA-SMOKE` until then. | 6c-β (when a Worker test harness exists) OR accept |
| `D-PHASE6C-ADAPTER-SPANS` | No span around the upstream provider call (`adapter.Stream`/`GenerateImage`/…) — the most interesting LLM latency lives there. Adding it touches the `provider` package. | 6c-β enrichment |
| `D-PHASE6C-TEMPO-DURABILITY` | Tempo runs single-binary on local-filesystem storage (dev only). A real deployment needs object-storage block config + retention. | Whenever 6c reaches an integration/prod env |
| `D-PHASE6C-METRICS-LOGS` | 6c is traces-only. OTel metrics + log correlation (same `trace_id` in slog output) are a natural follow-on but out of scope. | Post-6c observability follow-up |

## 10. Open risks

- **Docker build context.** Adding the `observability` module means each service's
  Docker build must see `sdks/go/observability/`. The `llmgw` SDK already faced
  this (book-service Dockerfile context bumped to repo root, per 5e-β.1) — 6c-α
  mirrors that wiring for provider-registry + usage-billing. Verify in BUILD.
- **Go-module / otel version skew.** A consuming service that `require`s a
  `go.opentelemetry.io/otel*` package directly must match the versions pinned in
  `sdks/go/observability/go.mod` (§3.2) — a mismatch is a hard build failure.
  Keep otel packages out of the service `go.mod`s' direct `require`s where
  possible; let them resolve transitively through the `replace`d module.
- **Port 3000 collision** with ContextHub MCP — resolved by mapping Grafana to host
  `3200` (§3.1).
- **otel-collector-contrib image size** (~400 MB). Acceptable for dev; noted.

## 11. Build plan — 6c-α task decomposition

Bite-sized tasks in dependency order. T1 is the foundation everything imports;
T2 is independent (config only); T3→T7 each instrument one boundary, smallest
service first.

| # | Task | Files | Tests |
|---|---|---|---|
| **T1** | Shared `observability` module — `InitTracer`, `HTTPTransport`, `ChiMiddleware`, `Tracer`, `Inject`/`Extract` | `sdks/go/observability/{go.mod,observability.go,observability_test.go}` | §7 #1,#2,#3 |
| **T2** | Observability stack — collector + Tempo + Grafana | `infra/otel/{collector-config,tempo,grafana-datasources}.yaml`, `infra/docker-compose.yml` | `docker compose config` lint |
| **T3** | Instrument **usage-billing** (server-only — proves `InitTracer` + `ChiMiddleware`) | usage-billing `go.mod`/`go.sum`, `cmd/.../main.go`, `internal/api/server.go` | §7 #6 (usage-billing) |
| **T4** | provider-registry HTTP boundaries — server middleware + instrumented billing client | provider-registry `go.mod`/`go.sum`, `cmd/.../main.go`, `internal/api/server.go`, `internal/billing/client.go` | §7 #6,#7 |
| **T5** | provider-registry goroutine bridge (job path) — `llm.job.process` span | `internal/api/jobs_handler.go`, `internal/jobs/worker.go` | §7 #5 |
| **T6** | provider-registry streaming `settle` bridge — `llm.stream.settle` span | `internal/api/stream_handler.go`, `internal/api/stream_billing.go` | streaming-settle bridge test |
| **T7** | provider-registry RabbitMQ producer — AMQP `traceparent` inject + producer span | `internal/jobs/notifier.go` | §7 #4 (AMQP carrier) |
| **T8** | VERIFY — `go build/vet/test` ×3 modules; `docker compose config` + one-shot stack boot | — | full suite |

Docker build-context wiring (the `observability` `replace`, mirroring `llmgw`)
is handled within T3/T4 where each service's `go.mod` + `Dockerfile` are touched.
