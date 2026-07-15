// M4 — service-worker registration + the update lifecycle (MB5). Registered ONLY in a production
// build: dev uses MSW (mockServiceWorker.js) + Vite HMR, which the real SW would fight. The update
// flow is explicit and NON-silent: when a new SW finishes installing while an old one still
// controls the page, we surface an "update ready" signal (the UpdatePrompt renders a refresh
// affordance) rather than hot-swapping mid-interaction. Only when the user accepts do we post
// SKIP_WAITING; controllerchange then reloads once, into the new version.

let waitingReg: ServiceWorkerRegistration | null = null;
const listeners = new Set<() => void>();

export function onUpdateReady(cb: () => void): () => void {
  listeners.add(cb);
  // If an update is already waiting when a listener subscribes, tell it immediately.
  if (waitingReg) cb();
  return () => listeners.delete(cb);
}

function notify(): void {
  listeners.forEach((l) => l());
}

export function applyUpdate(): void {
  waitingReg?.waiting?.postMessage({ type: 'SKIP_WAITING' });
}

export function registerServiceWorker(): void {
  if (!import.meta.env.PROD) return;
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;

  // In-tab deep-link (cold-review LOW-2): when a push is tapped and a tab is already open, the SW
  // posts {type:'NAVIGATE', route}. Route to it (same-origin relative only — the SW already validated,
  // we re-check). Without this listener the in-tab case would focus the tab but not navigate.
  navigator.serviceWorker.addEventListener('message', (e: MessageEvent) => {
    const d = e.data as { type?: string; route?: string } | undefined;
    if (d?.type === 'NAVIGATE' && typeof d.route === 'string' && /^\/[^/]/.test(d.route)) {
      window.location.assign(d.route);
    }
  });

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((reg) => {
        if (reg.waiting && navigator.serviceWorker.controller) {
          waitingReg = reg;
          notify();
        }
        reg.addEventListener('updatefound', () => {
          const installing = reg.installing;
          if (!installing) return;
          installing.addEventListener('statechange', () => {
            // installed + an existing controller ⇒ this is an UPDATE (not the first install).
            if (installing.state === 'installed' && navigator.serviceWorker.controller) {
              waitingReg = reg;
              notify();
            }
          });
        });
      })
      .catch(() => {
        /* SW registration is best-effort; the app works without it */
      });

    // Reload exactly once when the new SW takes control (after the user accepts + SKIP_WAITING).
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
  });
}
