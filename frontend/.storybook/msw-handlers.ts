// C13 — MSW v2 handler factories for Storybook knowledge-dialog stories.
//
// Each factory returns a `http.METHOD(path, resolver)` handler. Pass
// these into `parameters.msw.handlers` at the story level. The preview
// bootstraps MSW once via `initialize()` + `mswLoader` in preview.tsx.
//
// URL paths use `*` prefix so the handler matches both relative fetches
// (the app hits `/v1/knowledge/...`) and any absolute-origin variants
// dev servers may produce.
//
// Three shapes we support per handler:
//   (1) happy: `handler(fixtureJson)` — 200 with JSON body
//   (2) delayed: `handler(fixtureJson, {delayMs})` — happy after N ms,
//       or `delayMs: 'infinite'` for permanent loading state
//   (3) error: `handler(null, {status, body})` — BE error shape
//
// MSW v2 `HttpResponse.json(...)` handles both happy and error cases;
// the wrapper below lets stories declare shape without reading docs.

import { http, HttpResponse, delay, type JsonBodyType } from 'msw';
import type {
  BenchmarkStatus,
  BenchmarkRunResponse,
} from '../src/features/knowledge/types';
import type { CostEstimate } from '../src/features/knowledge/types/projectState';
import type {
  ExtractionJobWire,
  ChangeEmbeddingModelResponse,
  UserCostSummary,
} from '../src/features/knowledge/api';
import type { UserModel } from '../src/features/ai-models/api';

/**
 * Options for any handler that might need to delay or surface an error.
 * `delayMs: 'infinite'` keeps the request unresolved for the story's
 * lifetime — useful for "loading" stories.
 * `status` + `body` produce a non-2xx response the dialog's error path
 * can render.
 */
export interface HandlerOptions {
  delayMs?: number | 'infinite';
  status?: number;
  body?: unknown;
}

async function maybeDelay(opts: HandlerOptions | undefined) {
  if (!opts?.delayMs) return;
  if (opts.delayMs === 'infinite') {
    // `delay('infinite')` never resolves — story sits in loading.
    await delay('infinite');
    return;
  }
  await delay(opts.delayMs);
}

/**
 * /review-impl COSMETIC #7 — defensively narrow to a plain JSON object
 * before casting. Catches the footgun of a caller passing a Date,
 * Promise, Map, or undefined as the error body (tsc allows it via
 * `body: unknown` but `HttpResponse.json` would serialize it
 * incorrectly or throw). Non-POJO bodies fall back to a generic
 * envelope with `__unserializable: typeof value` so the story still
 * surfaces _something_ rather than silently failing.
 */
function isJsonSafe(v: unknown): v is JsonBodyType {
  if (v === null) return true;
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
    return true;
  }
  if (Array.isArray(v)) return v.every(isJsonSafe);
  if (typeof v === 'object') {
    const proto = Object.getPrototypeOf(v);
    if (proto !== null && proto !== Object.prototype) return false;
    return Object.values(v as Record<string, unknown>).every(isJsonSafe);
  }
  return false;
}

function errorOr<T>(fixture: T, opts: HandlerOptions | undefined): JsonBodyType {
  if (opts?.status !== undefined && opts.status >= 400) {
    const body = opts.body ?? { detail: 'error' };
    if (isJsonSafe(body)) return body;
    return { __unserializable: typeof body } as JsonBodyType;
  }
  return fixture as JsonBodyType;
}

function statusFrom(opts: HandlerOptions | undefined): number {
  return opts?.status ?? 200;
}

// ── Handlers ───────────────────────────────────────────────────────────

// GET /v1/knowledge/projects/:id/benchmark-status?embedding_model=...
export function benchmarkStatusHandler(
  fixture: BenchmarkStatus,
  opts?: HandlerOptions,
) {
  return http.get('*/v1/knowledge/projects/:id/benchmark-status', async () => {
    await maybeDelay(opts);
    return HttpResponse.json(errorOr(fixture, opts), { status: statusFrom(opts) });
  });
}

// POST /v1/knowledge/projects/:id/benchmark-run
export function benchmarkRunHandler(
  fixture: BenchmarkRunResponse,
  opts?: HandlerOptions,
) {
  return http.post('*/v1/knowledge/projects/:id/benchmark-run', async () => {
    await maybeDelay(opts);
    return HttpResponse.json(errorOr(fixture, opts), { status: statusFrom(opts) });
  });
}

// POST /v1/knowledge/projects/:id/extraction/estimate
export function estimateHandler(
  fixture: CostEstimate,
  opts?: HandlerOptions,
) {
  return http.post('*/v1/knowledge/projects/:id/extraction/estimate', async () => {
    await maybeDelay(opts);
    return HttpResponse.json(errorOr(fixture, opts), { status: statusFrom(opts) });
  });
}

// POST /v1/knowledge/projects/:id/extraction/start
export function startExtractionHandler(
  fixture: ExtractionJobWire,
  opts?: HandlerOptions,
) {
  return http.post('*/v1/knowledge/projects/:id/extraction/start', async () => {
    await maybeDelay(opts);
    return HttpResponse.json(errorOr(fixture, opts), { status: statusFrom(opts) });
  });
}

// PUT /v1/knowledge/projects/:id/embedding-model(?confirm=true)
export function updateEmbeddingModelHandler(
  fixture: ChangeEmbeddingModelResponse,
  opts?: HandlerOptions,
) {
  return http.put('*/v1/knowledge/projects/:id/embedding-model', async () => {
    await maybeDelay(opts);
    return HttpResponse.json(errorOr(fixture, opts), { status: statusFrom(opts) });
  });
}

// GET /v1/knowledge/costs
export function userCostsHandler(
  fixture: UserCostSummary,
  opts?: HandlerOptions,
) {
  return http.get('*/v1/knowledge/costs', async () => {
    await maybeDelay(opts);
    return HttpResponse.json(errorOr(fixture, opts), { status: statusFrom(opts) });
  });
}

// GET /v1/model-registry/user-models — inspects `?capability=` query
// so the same handler can serve both the BuildGraph LLM dropdown
// (capability=chat) and EmbeddingModelPicker (capability=embedding)
// without returning an unrealistic merged list. Pass either:
//   - a single fixture → applied to every capability (back-compat)
//   - `{chat, embedding}` — selects per query param
// Requests without a capability query get `fallback` (or `chat` if no
// fallback). Requests with an unknown capability also get `fallback`.
export function userModelsHandler(
  fixture:
    | { items: UserModel[] }
    | { chat?: { items: UserModel[] }; embedding?: { items: UserModel[] }; fallback?: { items: UserModel[] } },
  opts?: HandlerOptions,
) {
  return http.get('*/v1/model-registry/user-models', async ({ request }) => {
    await maybeDelay(opts);
    let resolved: { items: UserModel[] };
    if ('items' in fixture) {
      resolved = fixture;
    } else {
      const cap = new URL(request.url).searchParams.get('capability');
      const byCap =
        cap === 'embedding' ? fixture.embedding
        : cap === 'chat' ? fixture.chat
        : undefined;
      resolved = byCap ?? fixture.fallback ?? fixture.chat ?? { items: [] };
    }
    return HttpResponse.json(errorOr(resolved, opts), { status: statusFrom(opts) });
  });
}
