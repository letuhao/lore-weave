import { expect, test } from '@playwright/test';

// `G5` — kernel state, in a browser, asserted.
//
// # What this covers that nothing else does
//
// Every other test of this path stops at a boundary. `channel-client.test.ts`
// drives the client with a fake socket; `turnOutcome`'s units fold fixture
// events; `world-actor-subject` proves the subject route against two real
// databases. None of them can say that an event the KERNEL produced reaches a
// screen — and `F4` could not either, because the reality it used had zero
// committed events, so it rendered `turn 0` and an empty roster honestly.
//
// The chain this asserts, end to end:
//
//   actor-hub -> commit-service (spine) -> events row
//     -> publisher -> lw.events.<reality>
//     -> ChannelRoom.foldEvent -> w1.frame -> channel-store -> the DOM
//
// # Why the roster entry is the assertion and not the turn number
//
// `turn 1` proves an event arrived. The ROSTER ENTRY proves the event's PAYLOAD
// was folded: `foldEvent` mutates the view for `struck`, `downed`, `fled` and
// `moved`, and everything else — including `defended` — falls through to
// `default: break`. The demo script's first version proposed `defend`, which
// committed a real event, advanced the turn, and rendered an empty roster. That
// is the partial success this assertion exists to refuse.
//
// # Running it
//
//   bash scripts/smoke/kernel-state-demo.sh          # stand the stack up
//   cd frontend-game && VITE_GAME_SERVER_URL=ws://localhost:2577 \
//     VITE_INTERNAL_TOKEN=kernel_demo_token npx vite --port 5199 --strictPort
//   LOREWEAVE_E2E_FULL=1 KERNEL_STATE_BASE=http://localhost:5199 npx playwright test kernel-state
//
// It SKIPS without `LOREWEAVE_E2E_FULL=1`, loudly, naming the script — a live
// assertion that passes quietly with no stack is worse than one nobody wrote.
// That flag has been documented in `playwright.config.ts` since the config was
// written and read by NOTHING; this is its first consumer.

const FULL = process.env.LOREWEAVE_E2E_FULL === '1';
const BASE = process.env.KERNEL_STATE_BASE ?? 'http://localhost:5199';

// The ids the demo script seeds. Fixed there on purpose so this file can name
// them; a demo whose ids move on every run cannot be asserted against.
const SELF_ENTITY = '1';
const STRUCK_TARGET = 'entity-2';

/**
 * A REAL access token, or the suite skips.
 *
 * `/play` is behind `<RequireAuth>` and the app does not merely read the token
 * — it CLEARS a token it cannot use. Seeding `lw_auth` with a placeholder was
 * the obvious move and it does not work: measured, `localStorage.getItem`
 * returns `null` after the redirect, so the app wiped it. Which is correct
 * behaviour and is why this needs a token auth-service actually issued.
 *
 * That service is not part of the kernel-state stack, so rather than pretend,
 * this skips and names what it wants — the same contract every live suite in
 * this repo honours. See `GO-2` for what it would take to make it unconditional.
 */
const SESSION = process.env.KERNEL_STATE_ACCESS_TOKEN ?? '';

/**
 * Seed a session, then open `/play`.
 *
 * `/play` sits behind `<RequireAuth>`, so a fresh context lands on `/login` and
 * every locator below times out against a page carrying only a heading. This
 * bit me in a way worth recording: **the same steps driven by hand SUCCEEDED**,
 * because that browser still carried a session from an earlier navigation. A
 * manual run is authenticated by accident; a test never is — one more reason
 * the hand-driven proof was not enough on its own.
 *
 * # Why the session is SEEDED rather than logged in
 *
 * Stated plainly because it is a real limit: this bypasses the login flow by
 * writing the two keys `@loreweave/auth-client` owns. The alternative is
 * standing auth-service up, and this stack does not run it — the demo is about
 * whether an event the kernel produced reaches a screen, and the auth path has
 * its own suites. What this test must NOT do is silently look like it logged
 * in, so: it does not log in, and nothing here asserts anything about auth.
 *
 * (The obvious third option — the guest button `smoke.spec.ts` clicks — is
 * gone. There is no "Continue as guest" control in `frontend-game/src` any
 * more, which means that older test is stale; recorded as `GO-1`, not fixed
 * here.)
 */
async function openPlay(page: import('@playwright/test').Page): Promise<void> {
  await page.addInitScript((token: string) => {
    localStorage.setItem(
      'lw_auth',
      JSON.stringify({ accessToken: token, refreshToken: token }),
    );
    localStorage.setItem(
      'lw_user',
      JSON.stringify({ user_id: '33333333-2222-4333-8444-000000000003', email: 'e2e@local' }),
    );
  }, SESSION);
  await page.goto(`${BASE}/play`);
}

test.describe('kernel state reaches the browser', () => {
  test.skip(
    !FULL,
    'set LOREWEAVE_E2E_FULL=1 and run scripts/smoke/kernel-state-demo.sh first',
  );
  test.skip(
    !SESSION,
    'set KERNEL_STATE_ACCESS_TOKEN to a token auth-service issued — /play is behind ' +
      'RequireAuth and the app CLEARS a token it cannot use, so a placeholder does not ' +
      'work (measured). See GO-2.',
  );

  test('a committed strike renders as a roster entry', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));

    await openPlay(page);
    await page.getByRole('button', { name: 'Join channel' }).click();

    // The SUBJECT hop (F4): resolved from actor_control_binding through
    // world-service, not from anything the client sent.
    await expect(
      page.getByText(`you are entity ${SELF_ENTITY}`),
      'the subject did not resolve — is world-service up, and does the driver hold the binding?',
    ).toBeVisible({ timeout: 15_000 });

    // The STATE hop: this entry exists ONLY because `struck` set hp on target 2.
    // With the event stream empty the same join renders an empty roster —
    // measured, by deleting the stream and re-joining.
    await expect(
      page.getByText(STRUCK_TARGET, { exact: true }),
      'no roster entry — the committed event did not reach the fold. Check ' +
        'XLEN lw.events.<reality> and the publisher log.',
    ).toBeVisible({ timeout: 15_000 });

    // The turn advanced too. Asserted AFTER the roster because it is the weaker
    // claim: a turn number moves for any committed event, including one whose
    // payload folds to nothing.
    await expect(page.getByText(/turn [1-9]/)).toBeVisible();

    expect(pageErrors, 'no uncaught page errors').toEqual([]);
  });

  // Non-vacuity. Every assertion above is `toBeVisible`, and all of them would
  // also pass on a page that happened to contain those strings for some other
  // reason. This one fixes the panel as their source: the roster entry must sit
  // inside the channel panel, beside the action its own event enables.
  test('the roster entry is in the channel panel, not somewhere else on the page', async ({
    page,
  }) => {
    await openPlay(page);
    await page.getByRole('button', { name: 'Join channel' }).click();

    const panel = page.locator('li', { hasText: STRUCK_TARGET });
    await expect(panel).toBeVisible({ timeout: 15_000 });
    await expect(
      panel.getByRole('button', { name: 'Strike' }),
      'a hostile roster entry offers Strike — THR-A4, the engine offers the targets',
    ).toBeVisible();
  });
});
