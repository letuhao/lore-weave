# LLM Pipeline — Phase 6c-β: OpenTelemetry rollout to the remaining Go services

> Status: DESIGN (session 57 cycle 9). Parent: `LLM_PIPELINE_PHASE6C_DESIGN.md` §8.
> 6c-α built the foundation + instrumented provider-registry + usage-billing.
> 6c-β applies the proven pattern to **every remaining Go service** + the Go SDK.

---

## 1. Why / scope

6c-α proved the foundation (the `observability` module, the collector/Tempo/
Grafana stack, the four propagation boundaries) on two services. 6c-β is the
**wide rollout** — the 8 remaining Go services, both directions, so a trace no
longer dead-ends the moment it leaves an instrumented service.

**The 8 services** (audited from `go.mod` + `chi.NewRouter` greps):

| Service | HTTP server | RabbitMQ | Outbound HTTP |
|---|---|---|---|
| auth-service | chi | — | 1 client |
| book-service | chi | — | 3 clients (+ `llmgw` SDK) |
| catalog-service | chi | — | 1 client |
| glossary-service | chi | — | 1 client |
| notification-service | chi | **consumer** (`loreweave.events`) | — |
| sharing-service | chi | — | 1 client |
| statistics-service | chi | — | 1 client |
| worker-infra | **none** (pure worker) | **producer only** (WS-push to `loreweave.events`) | 1 client |

**worker-infra correction (review-impl MED#1).** worker-infra's import loop consumes
from a **Redis Stream** (`XReadGroup` on `importStream`), NOT RabbitMQ — its amqp
channel is **publish-only** (`publishWSEvent`). There is no RabbitMQ consumer in
worker-infra. Its only RabbitMQ consumer in the monorepo is notification-service.

Decisions (CLARIFY): **both directions** (server + the ~9 outbound `http.Client`
transports) — a SERVER span without outbound injection still breaks the trace at
the next hop. **One XL cycle** — the chi rollout is uniform/mechanical.

## 2. The uniform chi-service rollout (7 services)

auth, book, catalog, glossary, notification, sharing, statistics — each gets the
**identical** 6c-α treatment:

1. `go.mod` — `require github.com/loreweave/observability v0.1.0` +
   `replace … => ../../sdks/go/observability`; bump the `go` directive to
   `1.25` (the observability module is `go 1.25.0`; a consumer must be ≥ its
   deps); `go mod tidy`. **Audited (review-impl LOW#4):** auth, catalog,
   sharing, statistics are `go 1.22`; glossary is `go 1.23.0`; book +
   notification are already `1.25` — so **5 of 7 need the bump**.
2. `cmd/<svc>/main.go` — `observability.InitTracer(ctx, "<svc>")` right after
   `config.Load()`, `defer shutdown` with a 5 s timeout ctx.
3. `internal/api/server.go` — `r.Use(observability.ChiMiddleware())` between
   `middleware.RealIP` and `middleware.Recoverer`.
4. `Dockerfile` — repo-root build context (`COPY sdks/go/observability …`).
5. `infra/docker-compose.yml` — `OTEL_EXPORTER_OTLP_ENDPOINT` env + the
   `context: ..` / `dockerfile: services/<svc>/Dockerfile` bump.
6. `internal/api/tracing_test.go` — the `TestRouter_EmitsServerSpan`
   regression-lock (ChiMiddleware is mounted).

**Middleware-stack audit (review-impl LOW#4):** 6 of 7 use the exact
`RequestID → RealIP → Recoverer` stack — `ChiMiddleware` slots in after
`RealIP`, before `Recoverer`, unchanged from 6c-α. **glossary-service is the
exception:** its stack is `RequestID → RealIP → traceIDMiddleware →
jsonRecovererMiddleware → requireInternalToken` — a custom recoverer and a
**pre-existing `traceIDMiddleware`**. For glossary, `ChiMiddleware` goes after
`RealIP` (before `traceIDMiddleware`); BUILD also decides whether glossary's
legacy `traceIDMiddleware` (a header-level request-id, not OTel spans) stays
alongside or is retired — flag it in the glossary BUILD step, do not silently
drop it.

## 3. Outbound HTTP (~9 sites)

Each service's inter-service `*http.Client` gets its transport wrapped:
`Transport: observability.HTTPTransport(nil)` (or `HTTPTransport(existing)`).
Same edit 6c-α made to `billing.NewGuardrailClient`. Audited count: auth 1,
book 3, catalog 1, glossary 1, sharing 1, statistics 1, worker-infra 1
(notification makes no outbound HTTP calls). BUILD wraps each at its constructor; the transport itself is unit-tested in
the `observability` module (6c-α §7 #7).

**Regression lock (review-impl MED#2 — the lock must be well-defined).** A bare
`grep "http.Client{"` is useless — it matches the *wrapped* form, the `llmgw`
SDK, and test files alike. The actual lock: a source-grep test that, **per
service**, asserts — if any non-`_test.go` file under `services/<svc>/internal`
contains the substring `http.Client{`, that **same file** also contains
`observability.HTTPTransport`. Coarse but well-defined and drift-catching: a new
inter-service client added without the wrap fails the lock. (The `llmgw` SDK is
under `sdks/`, not `services/` — excluded; it has its own transport test, §9 #6.)

## 4. NEW — the RabbitMQ consumer span

6c-α instrumented the **producer** (`provider-registry` `notifier`). 6c-β adds
the **consumer** side so the trace continues across the broker hop.

### 4.1 Shared carrier — `observability.AMQPCarrier`

6c-α put a local `amqpHeaderCarrier` in `provider-registry/internal/jobs/
notifier.go`. notification-service + worker-infra need the same adapter →
3 copies. Instead, promote it to the `observability` module **without** an
amqp091 dependency — `amqp091.Table` is defined as `map[string]interface{}`,
so a carrier over `map[string]any` fits by a plain conversion:

```go
// AMQPCarrier adapts a map[string]any (an amqp091 Table IS one) to a
// TextMapCarrier. The observability module stays amqp-free; callers convert
// their amqp.Table at the call site: observability.AMQPCarrier(table).
type AMQPCarrier map[string]any
func (c AMQPCarrier) Get(key string) string { /* string-typed value or "" */ }
func (c AMQPCarrier) Set(key, value string) { c[key] = value }
func (c AMQPCarrier) Keys() []string        { /* map keys */ }
```

**Nil-map caveat (review-impl LOW#3).** `Set` writes into the map, so the
producer MUST pass a non-nil `amqp.Table` — `observability.Inject(ctx,
observability.AMQPCarrier(amqp.Table{}))`, never a nil. (6c-α's notifier
already constructs `rabbitmq.Table{}`; §5's worker-infra publish must do the
same — `Inject` on a nil map panics.) `Extract` only reads (`Get`/`Keys`), so
extracting from a delivery with nil `Headers` is safe.

`provider-registry`'s `notifier.go` is refactored to drop its local carrier and
use `observability.AMQPCarrier` — a small, safe change to 6c-α code that
removes the duplication the consumers would otherwise triplicate. (Its 6c-α
`TestAMQPHeaderCarrier_*` tests in `internal/jobs/tracing_test.go` move to
`observability_test.go` along with the type.)

### 4.2 Consumer span pattern — notification-service only

The only RabbitMQ consumer in the monorepo is `notification-service`
`consumer.go` `handle(ctx, d)` (review-impl MED#1 — worker-infra is NOT a
RabbitMQ consumer; see §5). Per delivery:

```go
msgCtx := observability.Extract(ctx, observability.AMQPCarrier(d.Headers))
msgCtx, span := observability.Tracer("consumer").Start(msgCtx, "llm-event.consume",
    trace.WithSpanKind(trace.SpanKindConsumer),
    trace.WithAttributes(attribute.String("messaging.system", "rabbitmq")))
defer span.End()
// … process with msgCtx (the DB INSERT joins the trace) …
// On a failure path (malformed body, missing fields, Nack):
//   span.RecordError(err); span.SetStatus(codes.Error, "…")
```

`Extract` reads the `traceparent` the producer injected → the CONSUMER span is
a child of the producer's PRODUCER span → the broker hop is one continuous
trace. A delivery with no `traceparent` (un-instrumented producer) just starts
a fresh root — no failure.

**Error/nack outcomes (review-impl LOW#5).** `handle` `Nack`s malformed or
incomplete messages. The span MUST record those — `span.RecordError(err)` +
`span.SetStatus(codes.Error, …)` on the unmarshal-fail / missing-field / nack
paths — or a failing consume is invisible in the trace.

## 5. worker-infra (no chi, no RabbitMQ consumer)

worker-infra is a pure worker — no HTTP server, so **no `ChiMiddleware`**. The
review-impl MED#1 re-audit corrected its shape: its import loop consumes from a
**Redis Stream** (`XReadGroup` on `importStream`/`importGroup`), and its amqp
channel is **publish-only** — `publishWSEvent` POSTs WS-push events to
`loreweave.events`. There is **no RabbitMQ consumer** here; §4.2 does NOT apply.

worker-infra's 6c-β scope:
- `InitTracer` in `main.go`; `go.mod`/`Dockerfile`/compose per §2 steps 1, 4, 5.
- **RabbitMQ producer injection** on `publishWSEvent`'s `amqpCh.Publish` — a
  PRODUCER span + `observability.Inject(... AMQPCarrier(amqp.Table{}) ...)`,
  mirroring 6c-α's notifier. (Run it under the active import-processing ctx so
  the WS-push event links to the import work.)
- `HTTPTransport` on its outbound `http.Client`.

**Deferred — the Redis-Stream consume.** worker-infra's real inbound is a Redis
Stream, a transport the 6c plan (§6c — "HTTP/RabbitMQ propagation") never
scoped. Tracing it needs traceparent carried in the XADD message fields + the
producer (a book-service import-submit `XADD`) injecting there — a distinct
mechanism. → `D-PHASE6C-REDIS-STREAM` (§10). Until then worker-infra's import
work starts a fresh root trace; the WS-push it publishes still carries that
root onward.

## 6. The `llmgw` Go SDK

`sdks/go/llmgw` `client.go` builds its internal client as
`&http.Client{Transport: transport}` where `transport` defaults to
`http.DefaultTransport`. 6c-β changes that default to
`otelhttp.NewTransport(http.DefaultTransport)` — the SDK imports
`go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` **directly**
(NOT the loreweave `observability` module — the SDK stays a standalone module;
`HTTPTransport` is a one-liner over `otelhttp`). A caller-supplied
`Transport` is honored as-is (the caller opted out). SDK calls then carry
`traceparent` + emit a CLIENT span, provided the consuming service ran
`InitTracer` (the SDK is a library — it never inits tracing itself).

## 7. Shared test helper — `observability/obstest`

9+ services will each need the recording-`TracerProvider` test setup 6c-α
inlined per file. Promote it to a small package:

```go
// sdks/go/observability/obstest/obstest.go
func RecordingProvider(t *testing.T) *tracetest.SpanRecorder
```

Installs a recording provider + W3C propagator as the globals, restores them on
`t.Cleanup`. Every service `tracing_test.go` shrinks to ~12 lines. 6c-α's four
test files (provider-registry api/billing/jobs, usage-billing api) are
refactored onto it too.

## 8. Files (6c-β)

**NEW:** `sdks/go/observability/obstest/obstest.go`; one
`internal/api/tracing_test.go` per chi service (7); consumer-span tests for
notification-service + worker-infra; an `llmgw` transport test.

**MOD:**
- `sdks/go/observability/observability.go` (+`AMQPCarrier`) +
  `observability_test.go` (+carrier test) — and the obstest refactor of the
  6c-α test files.
- `sdks/go/llmgw/{go.mod,go.sum,client.go}` — otelhttp transport.
- Per the 8 services — `go.mod`/`go.sum`, `cmd/<svc>/main.go`, `Dockerfile`,
  and either `internal/api/server.go` (chi) or the consumer/worker files;
  plus each outbound-HTTP client constructor.
- `provider-registry` `internal/jobs/notifier.go` — use
  `observability.AMQPCarrier` (drop the local copy).
- `infra/docker-compose.yml` — 8 services' `OTEL_EXPORTER_OTLP_ENDPOINT` env +
  repo-root build contexts.

~70 files — XL, one cycle (the chi rollout is uniform).

## 9. Test plan

1. `observability.AMQPCarrier` — Inject→Extract round-trips a `traceparent`
   through a `map[string]any` (moved/kept in `observability_test.go`).
2. `obstest.RecordingProvider` — returns a recorder; globals restored after.
3. Per chi service — `TestRouter_EmitsServerSpan` (ChiMiddleware mounted,
   route-pattern span name). 7 copies, each ~12 lines via `obstest`.
4. notification-service — a consumer-span test: a delivery whose `Headers`
   carry a `traceparent` produces a CONSUMER span on that trace_id; and a
   malformed delivery's span is `codes.Error` (LOW#5).
5. worker-infra — a PRODUCER test: its WS-push publish path injects a
   `traceparent` into the `amqp.Table` (mirrors 6c-α's notifier test). No
   consumer-span test — worker-infra has no RabbitMQ consumer (§5).
6. `llmgw` — the SDK's default transport injects a `traceparent` (mirrors
   6c-α's `TestGuardrailClient_DefaultTransportInjectsTraceparent`).
7. Outbound-HTTP same-file grep-lock (§3) — per service, any non-`_test.go`
   file under `internal/` that contains `http.Client{` must also contain
   `observability.HTTPTransport` in that same file. **Scope:** the 8 6c-β
   services. `http.Client{` cannot be distinguished from third-party egress
   by grep — provider-registry's `server.go` `invokeClient`/`verifyClient`
   are upstream-LLM-provider clients (egress to OpenAI/etc., not
   inter-service); they are intentionally NOT wrapped (their span is
   `D-PHASE6C-ADAPTER-SPANS`), so the lock runs on the 6c-β services only.

Verify: `go build/vet/test` GREEN for the `observability` + `llmgw` modules and
all 10 Go services; `docker compose config` OK.

## 10. Deferred items proposed

| ID | What | Target |
|---|---|---|
| `D-PHASE6C-BETA-SMOKE` | Manual: bring the stack up with ≥2 instrumented services on a real request path + confirm a multi-service trace incl. a CONSUMER span (the broker hop). | 6c-β follow-up OR integration-env run |
| `D-PHASE6C-REDIS-STREAM` | worker-infra's import loop consumes a **Redis Stream** (`XReadGroup`) — a transport the 6c plan never scoped (it says "HTTP/RabbitMQ"). Tracing it needs `traceparent` carried in the XADD message fields + the producer (book-service import-submit `XADD`) injecting there. | A 6c follow-up OR when Redis-stream traces are needed |
| `D-PHASE6C-PYTHON-TS` | 6c-γ — Python services + Python SDK + the TS gateway are the last uninstrumented hops. | 6c-γ |

## 11. Risks

- **`go` directive bumps.** A service still on `go 1.22` (usage-billing was)
  must bump to `1.25` — otel needs it. Cheap, but touches every such `go.mod`.
- **chi version bump.** Pulling `observability` drags `chi v5.2.5`; services
  pinned to `v5.1.0` get bumped via MVS. 6c-α confirmed v5.1→v5.2.5 is
  regression-free (full suites green); re-verify per service.
- **Known non-uniformity (audited, review-impl LOW#4).** glossary-service has a
  custom recoverer + a pre-existing `traceIDMiddleware` (§2) — BUILD handles
  glossary specially and decides the legacy middleware's fate. 5 of 7 services
  need a `go`-directive bump (§2 step 1). All other chi services share the
  `cmd/<svc>/main.go` + `internal/api/server.go` layout; if a further
  difference surfaces, BUILD adapts that service — no design change.

## 12. Build plan — 6c-β task decomposition

Dependency order. T1 is the shared foundation (every later test imports
`obstest`); T4 is the bulk (uniform).

| # | Task | Scope |
|---|---|---|
| **T1** | `observability` module | NEW `AMQPCarrier` (+ test in `observability_test.go`); NEW `obstest` package (`RecordingProvider`); refactor 6c-α's 4 test files onto `obstest`. |
| **T2** | `provider-registry` notifier | Drop local `amqpHeaderCarrier` → `observability.AMQPCarrier`; move its carrier tests to `observability_test.go`. |
| **T3** | `llmgw` Go SDK | `client.go` default transport → `otelhttp.NewTransport`; `go.mod`/`go.sum`; transport test. |
| **T4** | chi-service rollout ×7 | auth, book, catalog, glossary, notification, sharing, statistics — per service: `go.mod` (+replace, +`go 1.25` for the 5), `Dockerfile` (repo-root context), `infra/docker-compose.yml` block, `main.go` `InitTracer`, `server.go` `ChiMiddleware`, outbound `http.Client` → `HTTPTransport`, `tracing_test.go`. **glossary** handled specially (§2). |
| **T5** | notification-service consumer span | `consumer.go` `handle` — `Extract` + CONSUMER span + `RecordError`/`SetStatus` on nack paths; consumer-span test. |
| **T6** | worker-infra | `go.mod`/`Dockerfile`/compose; `main.go` `InitTracer`; PRODUCER injection on `publishWSEvent`; outbound `HTTPTransport`; producer test. No chi, no consumer span. |
| **T7** | VERIFY | `go build/vet/test` for `observability` + `llmgw` + all 10 Go services; `docker compose config`; the §9 #7 same-file outbound grep-lock. |
