// Phase 6c-γ — OpenTelemetry for api-gateway-bff.
//
// This module MUST be imported FIRST in main.ts (before @nestjs/core, http,
// express, http-proxy-middleware) — Node auto-instrumentation patches those
// modules via require-hooks, and a module already required before sdk.start()
// is not retroactively patched. `import './tracing'` evaluated first satisfies
// that. It is a side-effect-only import; safe under `nest build` (= tsc, no
// tree-shaking).
//
// No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset — dev without the
// observability stack still runs. (Mirrors the Go observability.InitTracer
// and the Python loreweave_obs.setup_tracing no-op contract.)
import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';

if (process.env.OTEL_EXPORTER_OTLP_ENDPOINT) {
  // The NodeSDK env-resource detector reads OTEL_SERVICE_NAME; default it here
  // so the service name has a code-level source.
  process.env.OTEL_SERVICE_NAME ||= 'api-gateway-bff';

  // No explicit SIGTERM shutdown hook here — NestJS owns process lifecycle
  // via app.enableShutdownHooks(); a process.exit() here would race it. The
  // BatchSpanProcessor flushes on its own interval; a few trailing spans may
  // be lost at shutdown (best-effort, same as the Go services).
  new NodeSDK({
    traceExporter: new OTLPTraceExporter(), // reads OTEL_EXPORTER_OTLP_ENDPOINT
    instrumentations: [getNodeAutoInstrumentations()],
  }).start();
}
