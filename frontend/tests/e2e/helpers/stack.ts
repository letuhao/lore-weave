// Which STACK is this run pointed at?
//
// 🔴 The default used to be the developer's long-running `infra` stack, for BOTH the gateway
// and the Postgres container, no matter where the browser was pointed. A run against the
// isolated stack's frontend (25174) therefore drove the UI on `lw-iso` while its DB-assert
// helpers read AND WROTE `infra-postgres-1` — `seedPriorExtractionJob()` INSERTs — and
// `frontend-tools-liveness` created chat sessions on `localhost:3123`, the base gateway.
//
// That is a cross-stack write into a database nobody treats as disposable, and it is silent:
// the specs pass or fail for reasons belonging to the OTHER stack. Deriving both from the
// browser target removes the footgun instead of documenting it, and an explicit env still wins
// for anyone who genuinely wants to cross the streams.

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5174';

/** The isolated stack publishes every port shifted by +20000 (infra/docker-compose.isolated.yml). */
function isIsolated(): boolean {
  try {
    return new URL(BASE_URL).port === '25174';
  } catch {
    return false;
  }
}

/** The Compose project prefix for the stack the browser is pointed at. */
export function stackProject(): 'lw-iso' | 'infra' {
  return isIsolated() ? 'lw-iso' : 'infra';
}

/** Postgres container for THIS stack. `PLAYWRIGHT_PG_CONTAINER` overrides. */
export function pgContainer(): string {
  return process.env.PLAYWRIGHT_PG_CONTAINER ?? `${stackProject()}-postgres-1`;
}

/** api-gateway-bff base URL for THIS stack. `PLAYWRIGHT_API_BASE` overrides. */
export function apiBase(): string {
  return process.env.PLAYWRIGHT_API_BASE ?? (isIsolated()
    ? 'http://localhost:23123'
    : 'http://localhost:3123');
}
