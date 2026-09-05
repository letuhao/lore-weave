import { test, expect } from '@playwright/test';
import type { APIRequestContext, Page } from '@playwright/test';
import { createBook } from '../helpers/api';
import { PERSONAS, type Persona } from '../personas/types';
import {
  assertDisposableTarget,
  freshAccount,
  markOnboarded,
  stableAccount,
  type PersonaAccount,
} from '../personas/account';

/**
 * Human-behaviour simulation — the persona journeys.
 *
 * Two personas, because the product must serve both and they fail differently: a NEWCOMER
 * hits empty states and unexplained vocabulary; a FREQUENT user hits SCALE. Almost every
 * defect this repo has recorded in the second class was invisible to a fresh account.
 *
 * WHAT MAKES THIS A TEST AND NOT A DEMO
 * ─────────────────────────────────────
 * Every journey ends in a claim that can be false, written as the user's expectation and
 * carrying its own justification (personas/types.ts). A simulated user that clicks around
 * and reports how it went cannot go red, and a check that cannot fail is not a check.
 *
 * THE SCALE GUARD IS THE LOAD-BEARING PART
 * ────────────────────────────────────────
 * `ensureScale` seeds up to the persona's `minBooks` and FAILS if it cannot. Not defensive
 * habit: the defect that motivated this suite — a library search that read 20 rows while
 * reporting a total of 83 — DOES NOT EXIST below 21 books. Run these journeys on a small
 * account and they pass forever while the bug ships.
 *
 * Each persona owns its ACCOUNT for the same reason. The first version borrowed the shared
 * developer login, and a "newcomer" on an account with 83 books and completed onboarding is
 * not a newcomer — every empty-state claim it made was vacuous.
 */

const SEED_PREFIX = 'persona-sim';

/** Log in through the real form, as the persona would. */
async function loginAs(
  page: Page,
  account: PersonaAccount,
  expectUrl = '**/books',
): Promise<void> {
  await page.goto('/login');
  await page.getByTestId('auth-email-input').fill(account.email);
  await page.getByTestId('auth-password-input').fill(account.password);
  await page.getByTestId('auth-submit-button').click();
  await page.waitForURL(expectUrl, { timeout: 20_000 });
}

/**
 * Bring the account up to `minBooks`, or fail the run.
 *
 * Returns a title that is deliberately NOT among the newest: seeds are created in order, so
 * the first one is oldest. Searching for the most recently created book cannot distinguish a
 * working search from one that only ever reads page one — which is precisely how the
 * original defect survived every test written against it.
 */
async function ensureScale(
  request: APIRequestContext,
  account: PersonaAccount,
  persona: Persona,
): Promise<{ subjectTitle: string; total: number }> {
  const auth = { headers: { Authorization: `Bearer ${account.token}` } };

  const before = await request.get('/v1/books?limit=100', auth);
  expect(before.ok(), `list books: ${before.status()}`).toBeTruthy();
  const beforeBody = (await before.json()) as { items: { title: string }[]; total: number };

  const have = beforeBody.total ?? beforeBody.items.length;
  const marker = Date.now().toString(36);
  for (let i = have; i < persona.state.minBooks; i++) {
    await createBook(
      request,
      account.token,
      `${SEED_PREFIX} ${String(i).padStart(3, '0')} ${marker}`,
    );
  }

  const after = await request.get('/v1/books?limit=100', auth);
  const afterBody = (await after.json()) as { items: { title: string }[]; total: number };
  const total = afterBody.total ?? 0;

  // Fail CLOSED. A journey that quietly ran at 12 books when it asked for 25 reports a pass
  // for a case it never entered — the failure mode this guard exists for.
  expect(
    total,
    `persona "${persona.id}" needs at least ${persona.state.minBooks} books; the account has ` +
      `${total}. Running the journey anyway would test a smaller world than the persona ` +
      `describes, and the defect this suite exists to catch does not appear at that size.`,
  ).toBeGreaterThanOrEqual(persona.state.minBooks);

  // `/v1/books` returns newest first, so the LAST item of a full page is the oldest one we
  // can see — comfortably past the endpoint's default page of 20.
  const items = afterBody.items;
  const subjectTitle = items[items.length - 1]?.title ?? '';
  expect(subjectTitle, 'no subject title could be chosen for the search journey').not.toEqual('');
  return { subjectTitle, total };
}

const frequent = PERSONAS.find((p) => p.id === 'frequent')!;
const newcomer = PERSONAS.find((p) => p.id === 'newcomer')!;

test.describe(`persona: ${frequent.id}`, () => {
  test('open-a-book-by-name: a book they own is findable even when it is not the newest', async ({
    page,
    request,
    baseURL,
  }) => {
    assertDisposableTarget(baseURL);
    const account = await stableAccount(request, frequent.id);
    // A returning author has passed onboarding. Without this the login lands on
    // /onboarding and every assertion below is really about a screen this persona
    // has not seen in months.
    await markOnboarded(request, account.token);
    const { subjectTitle, total } = await ensureScale(request, account, frequent);

    await loginAs(page, account);
    await page.goto('/books');

    const search = page.getByTestId('filter-search-input');
    await expect(search, 'the library must offer a search input').toBeVisible({ timeout: 20_000 });
    await search.fill(subjectTitle);

    await expect(
      page.getByText(subjectTitle, { exact: false }).first(),
      `"${subjectTitle}" is one of this account's ${total} books and was searched by its exact ` +
        `title. Not finding it tells the user the book does not exist. This is the journey ` +
        `that was broken for six days while every fresh-account test passed: the page ` +
        `filtered the first 20 rows in the browser while displaying the true total.`,
    ).toBeVisible({ timeout: 20_000 });
  });
});

test.describe(`persona: ${newcomer.id}`, () => {
  test('find-where-to-start: an empty library still offers the next action', async ({
    page,
    request,
    baseURL,
  }) => {
    assertDisposableTarget(baseURL);
    // A FRESH account, so "empty" is a fact rather than a hope. Asserting an empty state on
    // an account that happens to hold 83 books proves nothing at all.
    const account = await freshAccount(request, newcomer.id);

    const listed = await request.get('/v1/books', {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const body = (await listed.json()) as { total: number };
    expect(body.total ?? 0, 'a newcomer account must genuinely start empty').toBe(0);

    // A registered account with onboarding unseen lands on /onboarding, NOT /books.
    // Running this suite is what established that: the shared loginViaUI helper waits for
    // the books URL, which silently only ever described an already-onboarded account.
    await loginAs(page, account, '**/onboarding');

    await expect(
      page.getByTestId('intent-choices'),
      'A first session ends at the first screen more often than anywhere else. The account ' +
        'is genuinely empty, so nothing on the page can rely on existing content to guide ' +
        'them — the choices themselves have to be the way forward.',
    ).toBeVisible({ timeout: 20_000 });
  });
});
