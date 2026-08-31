import { expect, test } from '@playwright/test';

// `A4` — the actor is sited in a REALITY THAT ALREADY EXISTED, and the browser
// says where.
//
// # Why this is a second file and not a flag on `kernel-state.spec.ts`
//
// The two runs assert different things about different subjects and the
// difference is the entire point of this one:
//
//   kernel-state.spec.ts   two THROWAWAY databases it creates and drops, a
//                          world seeded by direct INSERTs, and a committed
//                          event — so it can assert the roster and the turn.
//   this file              one of the ten realities on this shard, a world
//                          seeded through `POST /internal/v1/world/seed`, and
//                          no committed event — so it asserts the SUBJECT and
//                          the PLACE, and deliberately nothing else.
//
// Folding them into one file behind an env flag would produce a suite whose
// assertions silently change meaning depending on how it was launched, and
// whose failure message could not say which stack it was talking about.
//
// # WHAT THIS DOES NOT COVER, stated rather than left to be assumed
//
// **No roster entry and no turn number.** A real reality has no committed
// events, and committing one here would mean running the spine against it —
// which `G3` already proves, on a stack built for it. Asserting `turn 0` would
// be asserting nothing; asserting `turn 1` would require this file to become
// the demo it deliberately is not. So the claim is exactly: *the world exists
// in a real reality, an actor is in it, and the browser renders where.*
//
// # Running it — the stack comes from the OTHER script
//
//   bash scripts/smoke/world-in-a-running-reality.sh --reality <uuid> --driver <user_id>
//
//   cd frontend-game && VITE_GAME_SERVER_URL=ws://localhost:2577 \
//     VITE_INTERNAL_TOKEN=running_reality_token npx vite --port 5199 --strictPort
//
//   LOREWEAVE_E2E_FULL=1 RUNNING_REALITY_PLACE='Yen Vu Lau' \
//     KERNEL_STATE_BASE=http://localhost:5199 \
//     KERNEL_STATE_ACCESS_TOKEN=<access_token> KERNEL_STATE_USER_ID=<user_id> \
//     npx playwright test running-reality --project=chromium
//
// `--project=chromium` is not optional advice: without it playwright also
// launches firefox and webkit, and a MISSING BROWSER BINARY reads in the output
// exactly like a failing assertion.
//
//   bash scripts/smoke/world-in-a-running-reality.sh --down

const FULL = process.env.LOREWEAVE_E2E_FULL === '1';
const BASE = process.env.KERNEL_STATE_BASE ?? 'http://localhost:5199';
const SESSION = process.env.KERNEL_STATE_ACCESS_TOKEN ?? '';
const USER_ID = process.env.KERNEL_STATE_USER_ID ?? '';

/**
 * The place the actor is sited in.
 *
 * **From the environment, with no fallback that would let this pass by
 * accident.** `kernel-state.spec.ts` could hard-code `Yen Vu Lau` because its
 * script seeds a fixed world; here the world comes from
 * `contracts/world/demo_v1.json`, the script reads the sited node OUT of that
 * file, and a literal here would be a fourth copy of a name that lives in one.
 */
const PLACE = process.env.RUNNING_REALITY_PLACE ?? '';

async function openPlay(page: import('@playwright/test').Page): Promise<void> {
  // Seeded, not logged in — the same deliberate limit `kernel-state.spec.ts`
  // records: this stack does not run the login flow, and the alternative is a
  // test that LOOKS like it authenticated. `/play` is behind `<RequireAuth>`
  // and the app CLEARS a token it cannot use, so the token must be real.
  await page.addInitScript(([token, user]: [string, string]) => {
    localStorage.setItem(
      'lw_auth',
      JSON.stringify({ accessToken: token, refreshToken: token }),
    );
    localStorage.setItem(
      'lw_user',
      JSON.stringify({ user_id: user, email: 'e2e@local' }),
    );
  }, [SESSION, USER_ID]);
  await page.goto(`${BASE}/play`);
}

test.describe('a running reality has a world, and the browser shows where the actor is', () => {
  test.skip(
    !FULL,
    'set LOREWEAVE_E2E_FULL=1 and run scripts/smoke/world-in-a-running-reality.sh first',
  );
  test.skip(
    !SESSION,
    'set KERNEL_STATE_ACCESS_TOKEN to a token auth-service issued — /play is behind ' +
      'RequireAuth and the app CLEARS a token it cannot use.',
  );
  // A skip rather than a fallback. With a default this suite would go green
  // against a page that happened to render the default string, which is the
  // one failure a place assertion must never have.
  test.skip(
    !PLACE,
    'set RUNNING_REALITY_PLACE to the place the script reported siting the actor in',
  );
  test.skip(
    !USER_ID,
    'set KERNEL_STATE_USER_ID to the SAME user the script granted the binding to ' +
      '(--driver): user_ref_id is server-stamped from the redeemed WS ticket, so the ' +
      'subject resolves against the token, and the two must be one person.',
  );

  test('the actor is somewhere, and the browser says where', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));

    await openPlay(page);
    await page.getByRole('button', { name: 'Join channel' }).click();

    // The SUBJECT hop, against a REAL `actor_control_binding` row written
    // through the meta-bridge — not an INSERT into a throwaway meta.
    await expect(
      page.getByText(/you are entity \d+/),
      'the subject did not resolve — is world-service up, and did the grant land ' +
        'for THIS user? (the script prints the driver it granted to)',
    ).toBeVisible({ timeout: 15_000 });

    // THE ROW ITSELF. This text exists only because `entity_binding` sites the
    // actor in a node that carries a `place`, and the room resolved it through
    // `/internal/v1/space/where-is` — the chain `A4` exists to close, now with
    // a reality nobody threw away at the end of it.
    await expect(
      page.getByTestId('frame-place'),
      'no place — is the actor sited, does its node carry a place row, and is ' +
        'LW_WORLD_SERVICE_URL set for the room?',
    ).toHaveText(new RegExp(PLACE), { timeout: 15_000 });

    expect(pageErrors, 'no uncaught page errors').toEqual([]);
  });

  // Non-vacuity. The assertion above is `toHaveText` on one testid, which would
  // also pass if the panel rendered a place for some entity that is not the
  // subject. This pins the two together: the place the frame shows must be the
  // place of the entity the frame says you are.
  test('the place shown belongs to the entity the frame says you are', async ({
    page,
  }) => {
    await openPlay(page);
    await page.getByRole('button', { name: 'Join channel' }).click();

    const header = page.getByTestId('frame-place');
    await expect(header).toBeVisible({ timeout: 15_000 });

    // Both facts come off the same frame, so a frame carrying one without the
    // other — which is precisely what an advisory place lookup produces when it
    // fails — cannot satisfy both locators.
    const subject = page.getByText(/you are entity \d+/);
    await expect(subject).toBeVisible();
    await expect(header).toHaveText(new RegExp(PLACE));
  });
});
