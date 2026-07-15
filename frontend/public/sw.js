/* LoreWeave service worker (M4). Hand-authored (no build plugin) so the caching policy is
 * explicit and auditable:
 *   - API (/v1/*): NETWORK-ONLY — a stale API response must never be served from cache (MB5).
 *   - Navigations: network-first, falling back to the cached app shell when offline (offline shell,
 *     NOT offline data).
 *   - Static same-origin assets: cache-first — Vite emits content-hashed filenames, so a new build
 *     produces new URLs and cache-first can never serve stale code.
 *   - Update flow (MB5): NO silent skipWaiting. A new SW installs and WAITS; the page shows a
 *     "new version — refresh" prompt and only then posts SKIP_WAITING. So a lagging tab is never
 *     hot-swapped mid-interaction.
 * Bump SHELL_CACHE to invalidate the precache on a shell change.
 */
const SHELL_CACHE = 'loreweave-shell-v1';
const SHELL_ASSETS = ['/', '/manifest.webmanifest', '/icon.svg'];

self.addEventListener('install', (event) => {
  // Precache the shell, but do NOT skipWaiting — wait for the user to accept the update.
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// The page posts this after the user accepts the "new version" prompt.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return; // never touch writes

  const url = new URL(req.url);

  // API: network-only. Let the request hit the network untouched — never cache-first (MB5).
  if (url.pathname.startsWith('/v1/')) return;

  // Navigations: network-first, cached shell as the offline fallback.
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/')));
    return;
  }

  // Static assets only: cache-first (content-hashed → safe). Restrict to asset destinations
  // (script/style/image/font) rather than "any same-origin non-/v1 GET" so the policy can't drift
  // onto a future same-origin data endpoint (cold-review LOW-3).
  const ASSET_DESTINATIONS = ['script', 'style', 'image', 'font'];
  if (url.origin === self.location.origin && ASSET_DESTINATIONS.includes(req.destination)) {
    event.respondWith(
      caches.match(req).then(
        (cached) =>
          cached ||
          fetch(req)
            .then((res) => {
              // Only cache SUCCESS — else a transient 5xx/404 for a hashed asset would be cached
              // permanently and served forever (a self-inflicted white-screen; cold-review MED-2).
              if (res.ok) {
                const copy = res.clone();
                caches.open(SHELL_CACHE).then((cache) => cache.put(req, copy));
              }
              return res;
            })
            .catch(() => cached),
      ),
    );
  }
});
