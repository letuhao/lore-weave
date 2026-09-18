// Sign-in backfill (plan 2026-09-18, Q4).
//
// Books created before provisioning moved to creation time get their knowledge project only when
// someone opens them. On every SIGN-IN (a login or a register, never a silent token refresh) this
// asks book-service to provision the caller's own books that still lack one. The server scopes it to
// the caller's own books and forwards only the caller's bearer (OQ-1); this side only fires it.
//
// Fire-and-forget by design: it never blocks navigation or onboarding, never shows an error, and
// is not counted by the global operation tracker. The server sweep can take a while, and a progress
// bar for work the author never asked for would be noise.

const base = () => import.meta.env.VITE_API_BASE || '';

export function provisionOnSignIn(accessToken: string): void {
  try {
    void fetch(`${base()}/v1/books/provision-missing`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        // Opt out of installFetchTracker: background housekeeping, not an author action.
        'X-LW-Operation-Tracked': '1',
      },
      // Let the request outlive a navigation that happens right after sign-in.
      keepalive: true,
    })
      .then((res) => {
        if (import.meta.env.DEV) console.debug('[provisionOnSignIn] status', res.status);
      })
      .catch((err: unknown) => {
        if (import.meta.env.DEV) console.debug('[provisionOnSignIn] failed', err);
      });
  } catch {
    // A missing fetch or a bad URL must never break sign-in.
  }
}
