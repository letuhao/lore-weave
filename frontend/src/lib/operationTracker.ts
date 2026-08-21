/**
 * Small, framework-independent tracker for requests that do not go through
 * React Query. The app shell subscribes to it so direct `apiJson` calls and
 * uploads still get the same visible busy state as query/mutation requests.
 */

export type OperationKind = 'read' | 'write';

export interface OperationSnapshot {
  active: number;
  reads: number;
  writes: number;
}

const listeners = new Set<() => void>();
let snapshot: OperationSnapshot = { active: 0, reads: 0, writes: 0 };

function publish(next: OperationSnapshot): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

export function getOperationSnapshot(): OperationSnapshot {
  return snapshot;
}

export function subscribeToOperations(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Mark a request as active and return the idempotent cleanup callback. */
export function beginOperation(kind: OperationKind = 'read'): () => void {
  let ended = false;
  publish({
    active: snapshot.active + 1,
    reads: snapshot.reads + (kind === 'read' ? 1 : 0),
    writes: snapshot.writes + (kind === 'write' ? 1 : 0),
  });

  return () => {
    if (ended) return;
    ended = true;
    publish({
      active: Math.max(0, snapshot.active - 1),
      reads: Math.max(0, snapshot.reads - (kind === 'read' ? 1 : 0)),
      writes: Math.max(0, snapshot.writes - (kind === 'write' ? 1 : 0)),
    });
  };
}


let fetchTrackerInstalled = false;

/** Install once at the browser boundary so direct fetch calls (uploads,
 * language-tool checks, voice requests, and streams) also participate. */
export function installFetchTracker(): void {
  if (fetchTrackerInstalled || typeof window === 'undefined') return;
  fetchTrackerInstalled = true;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const requestHeaders = input instanceof Request ? input.headers : new Headers(init?.headers);
    // apiJson tracks its own bounded operation; do not count its underlying fetch twice.
    if (requestHeaders.get('X-LW-Operation-Tracked') === '1') return nativeFetch(input, init);
    const requestMethod = input instanceof Request ? input.method : init?.method;
    const method = (requestMethod ?? 'GET').toUpperCase();
    const endOperation = beginOperation(method === 'GET' || method === 'HEAD' ? 'read' : 'write');
    return nativeFetch(input, init).finally(endOperation);
  }) as typeof window.fetch;
}
