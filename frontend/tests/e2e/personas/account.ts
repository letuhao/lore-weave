import { expect } from '@playwright/test';
import type { APIRequestContext } from '@playwright/test';

/**
 * Per-persona accounts.
 *
 * WHY NOT THE SHARED TEST ACCOUNT
 * ───────────────────────────────
 * The first version of this suite logged in as the developer's `claude-test` account, and
 * running it made the mistake obvious: a NEWCOMER persona on an account with 83 books and a
 * completed onboarding is not a newcomer, and every empty-state claim it makes is vacuous.
 * The account IS the persona's starting state, so borrowing one makes both personas lie —
 * and a persona suite whose state is whatever the shared account happens to hold today is
 * the same defect as the bug that motivated it: testing a world you did not choose.
 *
 * So each persona provisions its own:
 *
 *   newcomer  a FRESH account per run (unique email). Genuinely empty, genuinely first
 *             session — which is the only way an empty-state assertion means anything.
 *   frequent  a STABLE account (same email every run), seeded once to scale and reused.
 *             Re-seeding 25 books on every run would make the suite slow for no gain.
 *
 * Passwords are a fixed local constant: these accounts exist only on a disposable stack, are
 * created by this file, and hold nothing. Never point this at an environment where that is
 * not true — see `assertDisposableTarget`.
 */

export const PERSONA_PASSWORD = 'Persona@Sim2026';

export interface PersonaAccount {
  email: string;
  password: string;
  token: string;
}

/**
 * Refuse to provision accounts against anything but a local, disposable stack.
 *
 * This helper REGISTERS USERS and SEEDS DATA. Pointed at a shared or real deployment it
 * would create junk accounts under someone else's domain, and the failure would be silent —
 * the suite would go green. The guard is a allowlist of loopback hosts rather than a
 * denylist of known-real ones, because a denylist is wrong the first time a new environment
 * appears.
 */
export function assertDisposableTarget(baseURL: string | undefined): void {
  const url = baseURL ?? '';
  const ok = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(\/|$)/.test(url);
  expect(
    ok,
    `persona simulation writes: it registers accounts and seeds books. The target ` +
      `"${url || '(unset)'}" is not a loopback address, so it may be a shared or real ` +
      `deployment. Point PLAYWRIGHT_BASE_URL at a local disposable stack (the lw-iso ` +
      `frontend, e.g. http://localhost:25174) before running these journeys.`,
  ).toBeTruthy();
}

async function register(
  request: APIRequestContext,
  email: string,
  name: string,
): Promise<void> {
  const res = await request.post('/v1/auth/register', {
    data: { email, password: PERSONA_PASSWORD, name },
  });
  // 201 created, or already exists — both are fine; anything else is not.
  expect(
    [200, 201, 409, 400].includes(res.status()),
    `register ${email}: unexpected ${res.status()}`,
  ).toBeTruthy();
}

async function login(request: APIRequestContext, email: string): Promise<string> {
  const res = await request.post('/v1/auth/login', {
    data: { email, password: PERSONA_PASSWORD },
  });
  expect(res.ok(), `login ${email}: ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as { access_token?: string; accessToken?: string };
  const token = body.access_token ?? body.accessToken ?? '';
  expect(token, `login ${email} returned no access token`).not.toEqual('');
  return token;
}

/** A brand-new account, unique to this run. */
export async function freshAccount(
  request: APIRequestContext,
  personaId: string,
): Promise<PersonaAccount> {
  const email = `persona-${personaId}-${Date.now().toString(36)}@loreweave.test`;
  await register(request, email, `${personaId} (simulated)`);
  return { email, password: PERSONA_PASSWORD, token: await login(request, email) };
}

/** A reused account, stable across runs so seeded scale survives. */
export async function stableAccount(
  request: APIRequestContext,
  personaId: string,
): Promise<PersonaAccount> {
  const email = `persona-${personaId}@loreweave.test`;
  await register(request, email, `${personaId} (simulated)`);
  return { email, password: PERSONA_PASSWORD, token: await login(request, email) };
}

/**
 * Mark the account as having completed onboarding.
 *
 * A newly registered user is redirected to `/onboarding`, not `/books` — which is correct
 * product behaviour and was NOT obvious until this suite ran: the shared `loginViaUI` helper
 * hard-codes the books URL as its glob, an assumption that only holds for an account someone already
 * onboarded by hand. A returning author has passed that screen, so the persona has to as
 * well, or every journey after login is really a journey about onboarding.
 */
export async function markOnboarded(
  request: APIRequestContext,
  token: string,
): Promise<void> {
  const res = await request.patch('/v1/me/preferences', {
    headers: { Authorization: `Bearer ${token}` },
    data: { prefs: { hasSeenOnboarding: true } },
  });
  expect(res.ok(), `mark onboarded: ${res.status()}`).toBeTruthy();
}
