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

// M5 (D-MOB-4) — Web Push. The payload the server sends is ALREADY content-free (built from the
// push_topic only, never the notification's title/body — §8-B1), so the SW just displays it. It
// carries a route key + opaque id for deep-linking; neither is content.
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  const title = data.title || 'LoreWeave';
  const options = {
    body: data.body || 'You have a new notification.',
    icon: '/icon.svg',
    badge: '/icon.svg',
    // route + opaque id only — NO content in data (§8-S5).
    data: { route: data.route || '/activity', notification_id: data.notification_id || '' },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// Tapping a push opens the app at the (auth-gated) route it carries; the target screen re-fetches
// owner-scoped with the JWT — the id navigates, it does not authorize (§8-S5). Focus an existing tab
// if one is open rather than spawning a duplicate.
// Only a same-origin RELATIVE path is ever opened (defense-in-depth, cold-review MED-2): a single
// leading slash, not `//evil.com`, an absolute URL, or `javascript:`. The server only ever sends
// `/activity`, but the SW is the trust boundary and validates regardless.
function safeRoute(r) {
  return typeof r === 'string' && /^\/[^/]/.test(r) ? r : '/activity';
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const route = safeRoute(event.notification.data && event.notification.data.route);
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) {
          client.postMessage({ type: 'NAVIGATE', route });
          return client.focus();
        }
      }
      return self.clients.openWindow(route);
    }),
  );
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
