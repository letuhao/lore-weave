// Spec 29 D9 — translation surfaces must distinguish a *retryable* failure (5xx, network,
// timeout) from a *terminal* one (403 no grant, 404), and must NEVER render the raw
// `(error as Error).message` — that is what leaked the "Error occurred while trying to proxy…"
// string to the user (T4). Callers render a canned, localized message by kind + a Retry only
// when retrying could help.

export type TranslationErrorKind = 'retryable' | 'forbidden' | 'notfound';

/**
 * Classify a thrown API error. `apiJson` attaches `.status` (the HTTP status) to the Error;
 * a network reject / timeout throws before any response, so it has no status → retryable.
 */
export function classifyTranslationError(e: unknown): { kind: TranslationErrorKind; status?: number } {
  const status = (e as { status?: number } | null | undefined)?.status;
  if (status === 403) return { kind: 'forbidden', status };
  if (status === 404) return { kind: 'notfound', status };
  return { kind: 'retryable', status };
}

/** Retryable errors are the only ones for which a Retry button is offered. */
export function isRetryableTranslationError(e: unknown): boolean {
  return classifyTranslationError(e).kind === 'retryable';
}

/** Sentinel thrown when a translation fetch exceeds its client-side deadline (T5 wedge). */
export class TranslationTimeoutError extends Error {
  constructor(message = 'timeout') {
    super(message);
    this.name = 'TranslationTimeoutError';
  }
}

/**
 * Race a promise against a client-side deadline so a *hanging* dependency (not just a
 * rejecting one) can never wedge the UI forever (T5). The underlying request is not aborted
 * — `booksApi.listChapters` takes no signal — but the caller recovers and can offer Retry.
 */
export function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new TranslationTimeoutError()), ms);
    p.then(
      (v) => { clearTimeout(timer); resolve(v); },
      (e) => { clearTimeout(timer); reject(e); },
    );
  });
}
