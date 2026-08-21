export type ClientErrorContext = {
  source?: string;
  componentStack?: string;
  route?: string;
  detail?: unknown;
};

const STORAGE_KEY = 'lw_client_errors';
const MAX_ENTRIES = 50;

function serializeDetail(detail: unknown): string | undefined {
  if (detail == null) return undefined;
  try {
    return typeof detail === 'string' ? detail : JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

export function reportClientError(error: unknown, context: ClientErrorContext = {}): void {
  const err = error instanceof Error ? error : new Error(String(error));
  const entry = {
    at: new Date().toISOString(),
    name: err.name,
    message: err.message,
    stack: err.stack,
    source: context.source ?? 'runtime',
    componentStack: context.componentStack,
    route: context.route ?? (typeof window !== 'undefined' ? window.location.href : undefined),
    detail: serializeDetail(context.detail),
  };

  // Keep a bounded local journal for support/debugging even when no telemetry service
  // is configured. Never let diagnostics break the application.
  try {
    const previous = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    const entries = Array.isArray(previous) ? previous : [];
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...entries, entry].slice(-MAX_ENTRIES)));
  } catch {
    // Storage can be unavailable (private mode/quota); console logging still remains.
  }
  // eslint-disable-next-line no-console
  console.error('[LoreWeave client error]', entry);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('lw-client-error', { detail: entry }));
  }
}

let installed = false;

export function installGlobalErrorLogging(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;
  window.addEventListener('error', (event) => {
    reportClientError(event.error ?? event.message, {
      source: 'window.error',
      detail: { filename: event.filename, line: event.lineno, column: event.colno },
    });
  });
  window.addEventListener('unhandledrejection', (event) => {
    reportClientError(event.reason, { source: 'unhandledrejection' });
  });
}
