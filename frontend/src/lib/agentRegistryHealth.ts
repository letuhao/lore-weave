// F12 (dogfood round-4) — a tiny shared availability breaker for agent-registry reads.
//
// When a read fails (the registry is down — e.g. the service crashed and, before the
// F12 compose restart policy, stayed down for hours), remember it BRIEFLY so a component
// remount does not re-hit the slow 504 path, and the UI can show an explicit
// "unavailable" instead of a silently-empty panel.
//
// It caches only AVAILABILITY (a down service is down for every user) — never any
// per-user payload — so it is tenancy-safe (no cross-user data leak). This is a
// FE-side courtesy only; the real fix for "the service stayed down" is the compose
// `restart: unless-stopped` policy (F12a), not this.
const BACKOFF_MS = 30_000;
let downUntil = 0;

export const agentRegistryHealth = {
  /** True if a recent read failed and we are still inside the back-off window. */
  likelyDown(now: number = Date.now()): boolean {
    return now < downUntil;
  },
  /** Record a failed read — suppress re-hits for BACKOFF_MS. */
  noteDown(now: number = Date.now()): void {
    downUntil = now + BACKOFF_MS;
  },
  /** Record a successful read — clear the back-off immediately. */
  noteUp(): void {
    downUntil = 0;
  },
  /** Test-only: reset the module-level back-off between cases. */
  _reset(): void {
    downUntil = 0;
  },
};
