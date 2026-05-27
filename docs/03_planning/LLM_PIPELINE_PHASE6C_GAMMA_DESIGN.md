# LLM Pipeline — Phase 6c-γ: OpenTelemetry — Python services + TS gateway

> Status: DESIGN (session 57 cycle 10). Parent: `LLM_PIPELINE_PHASE6C_DESIGN.md` §8.
> 6c-α built the foundation; 6c-β covered every Go service. 6c-γ closes the
> last hops — the Python services, the Python SDK, and the TypeScript gateway.
> **After 6c-γ, whole-monorepo distributed tracing is complete.**

---

## 1. Why / scope

The Go side is fully traced (6c-α/β). The remaining uninstrumented hops:

| Component | Lang | Inbound | Outbound |
|---|---|---|---|
| api-gateway-bff | TS / NestJS | HTTP (every external request) | HTTP to all 13 backends |
| chat-service | Python / FastAPI | HTTP | httpx (billing, knowledge, provider clients) |
| knowledge-service | Python / FastAPI | HTTP | httpx (book, embedding, glossary clients) |
| video-gen-service | Python / FastAPI | HTTP | httpx |
| worker-ai | Python (poll-loop, no FastAPI) | — (polls) | httpx (the `loreweave_llm` SDK) |

api-gateway-bff is the **keystone** — it's the entry point for every external
request, so once it starts a SERVER span and propagates `traceparent`, every
user-facing request becomes one connected trace across all 16 services.

Decisions (CLARIFY): the 6c-γ scope was fixed by the earlier whole-monorepo
decision — this is simply "the rest." The one implementation fork — Python
instrumentation **mechanism** — is settled by precedent: a **programmatic
shared helper** (`loreweave_obs.setup_tracing`), mirroring the Go
`observability.InitTracer`, NOT the zero-code `opentelemetry-instrument`
wrapper (which would change every Docker `CMD` and need an env var for its
no-op path — both inconsistent with 6c-α/β).

## 2. Python — the shared `loreweave_obs` helper

NEW package `sdks/python/loreweave_obs/` — a third package under the existing
`sdks/python` distribution (alongside `loreweave_llm` + `loreweave_extraction`;
the `pyproject.toml` `packages.find` glob is extended to include it). One
function:

```python
def setup_tracing(service_name: str, app=None) -> None:
    """Configure OpenTelemetry tracing for a LoreWeave service.

    No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset — dev without the
    observability stack still runs. When configured: installs a TracerProvider
    (Resource service.name=service_name) + an OTLP/HTTP span exporter +
    BatchSpanProcessor; instruments httpx GLOBALLY; and, if `app` is a FastAPI
    instance, instruments it for inbound SERVER spans."""
```

Behaviour:
- **No-op gate** — `if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"): return`.
  Same contract as Go's `InitTracer`. (OTel Python's *default* propagator is
  already W3C `tracecontext,baggage`, so — unlike Go — no explicit propagator
  install is needed; propagation is the library default.)
- **Exporter** — `OTLPSpanExporter` (proto-http), reads
  `OTEL_EXPORTER_OTLP_ENDPOINT` itself; `BatchSpanProcessor`.
- **httpx** — `HTTPXClientInstrumentor().instrument()`. This monkey-patches
  the httpx **transport class process-wide**, so it covers every service HTTP
  client **and the `loreweave_llm` SDK's httpx client** (see §5) — regardless
  of when the client was constructed (the patch is on the transport class, not
  per-instance). **Caveat:** a client built with a *custom* httpx transport
  (`httpx.AsyncClient(transport=…)`) escapes the patch — BUILD must confirm no
  inter-service client uses one (none expected; custom transports are
  test-only).
- **FastAPI** — `FastAPIInstrumentor.instrument_app(app)` when `app` is given.
- DB (asyncpg/psycopg) is **not** instrumented — 6c is HTTP/messaging tracing,
  consistent with the Go side leaving pgx untraced.

The OTel Python dependencies (`opentelemetry-sdk`,
`opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi`,
`opentelemetry-instrumentation-httpx`) are declared in the **`sdks/python`
`pyproject.toml` `dependencies`** — so every service that already does
`pip install /sdk` gets them transitively. **No service `requirements.txt`
change, and no service Dockerfile change** — chat/knowledge/video-gen/worker-ai
Dockerfiles already use a repo-root context + `COPY sdks/python` +
`pip install /sdk` (from Phase 4a-α/4b); `loreweave_obs` rides along.

## 3. The 3 FastAPI services

chat-service, knowledge-service, video-gen-service — each `app/main.py` has
`app = FastAPI(title="…", lifespan=…)`. Add a `setup_tracing` call:

```python
from loreweave_obs import setup_tracing
setup_tracing("chat-service", app=app)
```

Place the call AFTER the `app.add_middleware(...)` calls — `FastAPIInstrumentor`
adds an ASGI middleware and Starlette *prepends* middleware, so calling
`setup_tracing` last lands the OTel SERVER-span middleware outermost; the span
then covers the full request (CORS + any `TraceIdMiddleware` included).
/review-impl(6c-γ) LOW#4.

`FastAPIInstrumentor` extracts an inbound `traceparent` → a SERVER span per
request; the global httpx instrumentation makes every outbound client call a
CLIENT span carrying the trace onward. Both directions, no per-client edits.

(chat-service has a pre-existing `TraceIdMiddleware` — a header-level request
id, not OTel — left in place, same call as glossary-service in 6c-β.)

## 4. worker-ai (poll-loop, no FastAPI)

worker-ai's `app/main.py` has `async def main()`. Add at the top of `main()`:

```python
from loreweave_obs import setup_tracing
setup_tracing("worker-ai")   # no app — worker-ai has no HTTP server
```

This instruments httpx → worker-ai's `loreweave_llm` SDK calls
(`submit_and_wait`) become CLIENT spans that propagate into provider-registry.
Each poll-loop iteration's SDK call is its own root trace; a manual per-job
parent span grouping a job's calls is a possible enrichment — **out of 6c-γ
scope** (noted, `D-PHASE6C-WORKERAI-JOB-SPAN`).

## 5. The Python SDK — no change

`loreweave_llm` (`sdks/python/loreweave_llm/client.py`) uses `httpx`. Because
`setup_tracing` calls `HTTPXClientInstrumentor().instrument()` — which patches
httpx **process-wide** — the SDK's httpx client is auto-traced in any service
that ran `setup_tracing`. **The Python SDK needs no code change** (unlike the
Go SDK, which needed an explicit `otelhttp` transport — Go has no global
monkey-patch). State this so a reader doesn't go looking for an SDK edit.

## 6. api-gateway-bff (NestJS / TypeScript)

NEW `services/api-gateway-bff/src/tracing.ts`:

```ts
import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';

if (process.env.OTEL_EXPORTER_OTLP_ENDPOINT) {
  // Service name via OTEL_SERVICE_NAME — the NodeSDK env-resource detector
  // reads it. Simpler than an explicit Resource and drops the
  // @opentelemetry/resources dep. /review-impl(6c-γ) LOW#5.
  process.env.OTEL_SERVICE_NAME ||= 'api-gateway-bff';
  new NodeSDK({
    traceExporter: new OTLPTraceExporter(),
    instrumentations: [getNodeAutoInstrumentations()],
  }).start();
}
```

`main.ts` gets `import './tracing';` as its **very first line** — Node
auto-instrumentation must patch `http`/`express`/`@nestjs/core` before those
modules are imported, and an import evaluated first satisfies that. No-op when
`OTEL_EXPORTER_OTLP_ENDPOINT` is unset (the `if` guard). `import './tracing'`
is a **side-effect-only import** (no bindings used): safe under `nest build`
(= `tsc`, no tree-shaking — confirmed `nest-cli.json` is not webpack mode); a
future switch to a tree-shaking bundler would need `sideEffects` care.

**The keystone — how the gateway propagates.** The gateway proxies to all 13
backends via `createProxyMiddleware` (`http-proxy-middleware` → `http-proxy` →
Node `http.request`). `instrumentation-http` (within
`getNodeAutoInstrumentations()`) patches `http.request` → the inbound request
gets a SERVER span and each proxied outbound request gets a CLIENT span **with
`traceparent` injected** → the gateway becomes the **root** of every
user-facing trace, and every backend (Go + Python, all instrumented) continues
it. This holds **only because the proxy routes through Node's `http` module** —
a future swap to a `fetch`/`undici`-based proxy would silently break
propagation and must re-check tracing. WebSocket-proxy hops (the gateway's
`WsAdapter` notification stream) are NOT HTTP-span-traced — out of 6c scope.

npm deps added to `package.json`: `@opentelemetry/sdk-node`,
`@opentelemetry/auto-instrumentations-node`,
`@opentelemetry/exporter-trace-otlp-http`. (No `@opentelemetry/resources` —
the `OTEL_SERVICE_NAME` env-detector path above needs no explicit `Resource`.)

## 7. docker-compose

5 services — chat-service, knowledge-service, video-gen-service, worker-ai,
api-gateway-bff — get `OTEL_EXPORTER_OTLP_ENDPOINT: ${OTEL_EXPORTER_OTLP_ENDPOINT:-}`
added to `environment:`. No build-context changes (Python services already
repo-root for the SDK; the gateway builds from its own context — `tracing.ts`
+ `package.json` deps need no context change).

## 8. Files (6c-γ)

**NEW:** `sdks/python/loreweave_obs/__init__.py` (the `setup_tracing` helper);
`sdks/python/tests/test_loreweave_obs.py`; `services/api-gateway-bff/src/tracing.ts`.

**MOD:** `sdks/python/pyproject.toml` (`packages.find` glob + OTel
`dependencies`); `chat-service`/`knowledge-service`/`video-gen-service`
`app/main.py` (one `setup_tracing(…, app=app)` call each); `worker-ai`
`app/main.py` (`setup_tracing("worker-ai")`); `api-gateway-bff` `src/main.ts`
(first-line import) + `package.json` (+`package-lock.json`);
`infra/docker-compose.yml` (5 env vars).

~15 files — auto-instrumentation keeps it light. XL by side-effects (a new
package + npm deps + 5 services), not by line count.

## 9. Test plan

1. `loreweave_obs.setup_tracing` — with no `OTEL_EXPORTER_OTLP_ENDPOINT`: a
   no-op (the global tracer provider stays the default; no exporter); no raise.
2. `setup_tracing` with the endpoint set: a real `TracerProvider` is installed
   (`trace.get_tracer_provider()` is an SDK provider, not the proxy).
3. `setup_tracing(app=<FastAPI>)` instruments the app — a request through a
   `TestClient` produces a SERVER span (assert via an in-memory span exporter).
4. httpx instrumentation — after `setup_tracing`, an httpx request emits a
   CLIENT span carrying the active trace.
5. Per Python service — a **source-grep regression-lock** that each
   `app/main.py` (chat/knowledge/video-gen + worker-ai) contains a
   `setup_tracing(` call. A behavioral/attribute check is unreliable here: in
   the test env `OTEL_EXPORTER_OTLP_ENDPOINT` is unset → `setup_tracing`
   no-ops → the app is never instrumented, so neither
   `app._is_instrumented_by_opentelemetry` nor a TestClient span would appear
   even when the code is correct. A source-grep (one test looping the 4
   `main.py` files, like the Go-side 5-place-invariant locks) is
   env-independent and bulletproof; instrumentation *behaviour* is proven once
   by #3 against `loreweave_obs` directly.
6. api-gateway-bff — `tracing.ts` compiles + `tsc` clean; the `import './tracing'`
   is line 1 of `main.ts`. (A NestJS runtime span assertion is heavy — the
   end-to-end check is the manual smoke, §10.)

Verify: `sdks/python` pytest GREEN; each Python service's pytest GREEN;
`api-gateway-bff` `npm run build` (tsc) GREEN; `docker compose config` OK.

## 10. Deferred items proposed

| ID | What | Target |
|---|---|---|
| `D-PHASE6C-GAMMA-SMOKE` | Manual: a real external request through api-gateway-bff produces ONE trace spanning the gateway → a Go backend → a Python backend in Grafana. The capstone whole-monorepo check. | 6c-γ follow-up OR first integration-env run |
| `D-PHASE6C-WORKERAI-JOB-SPAN` | worker-ai's poll loop emits no per-job parent span — each SDK call is its own root trace. A manual span grouping a job's calls is an enrichment. | A 6c follow-up |
| `D-PHASE6C-DB-SPANS` | DB calls (asyncpg/pgx/Neo4j) are untraced monorepo-wide — 6c is HTTP/messaging only. | Post-6c observability follow-up |

## 11. Risks

- **OTel Python ↔ instrumentation version skew.** The `opentelemetry-sdk` and
  the `opentelemetry-instrumentation-*` packages version in lockstep (the
  instrumentation packages use `0.Nb0` versions tracking the `1.N` SDK). The
  `pyproject.toml` must pin a mutually compatible set; `pip` resolves, but a
  bad pin fails the install. Verify in BUILD.
- **TS auto-instrumentation load order.** `import './tracing'` MUST be the
  first import in `main.ts`, before `@nestjs/core`/`http`. If a linter or a
  later edit reorders imports, instrumentation silently goes partial. A
  build-time check (the test §9 #6) guards it.
- **npm `@opentelemetry/*` version skew.** `sdk-node`,
  `auto-instrumentations-node`, and `exporter-trace-otlp-http` must be a
  mutually compatible release set (the OTel JS packages version in lockstep).
  Pin a coherent set in `package.json`; `npm install` resolves, but a bad
  combo fails the build. Symmetric with the Python skew risk above.
- **`getNodeAutoInstrumentations()` breadth.** It enables ~40 instrumentations
  (fs, dns, …) — noisy. Acceptable for dev; a follow-up can prune to
  http/express/nestjs if span volume is a problem.

## 12. Build plan — 6c-γ task decomposition

| # | Task | Scope |
|---|---|---|
| **T1** | `loreweave_obs` package | NEW `loreweave_obs/__init__.py` (`setup_tracing`); `pyproject.toml` glob + OTel deps; `tests/test_loreweave_obs.py`. |
| **T2** | 3 FastAPI services | chat/knowledge/video-gen `app/main.py` — one `setup_tracing(…, app=app)` each + the per-service regression-lock test. |
| **T3** | worker-ai | `app/main.py` — `setup_tracing("worker-ai")`. |
| **T4** | api-gateway-bff | NEW `src/tracing.ts`; `main.ts` first-line import; `package.json` deps + `npm install`. |
| **T5** | docker-compose | 5 services' `OTEL_EXPORTER_OTLP_ENDPOINT` env. |
| **T6** | VERIFY | `sdks/python` + 4 Python services pytest; gateway `npm run build`; `docker compose config`. |
