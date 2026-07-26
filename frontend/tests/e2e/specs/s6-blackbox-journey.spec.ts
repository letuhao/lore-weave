// S6 — BLACKBOX USER JOURNEY. Not a per-panel check: this is a real author's end-to-end path through
// the quality tools on a BRAND-NEW book, asserting the thing S6 exists to fix — that a GUI-only user
// can DO the job entirely in the Studio, never dropping to the legacy /edit page or the agent.
//
// The evaluation question (the PO's "is it genuinely usable?"): starting from a fresh book with NO
// co-writer session, can the author — with only clicks — set up the co-writer, author a canon rule,
// review corrections, track progress with a personal goal, and reach the flywheel? Each step is a
// human action against the real login/gateway/composition/knowledge stack.
//
// Run against the S6 build: PLAYWRIGHT_BASE_URL=http://localhost:5199 npm run e2e -- s6-blackbox
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

test.describe('S6 · blackbox author journey (fresh book → operable, Studio-only)', () => {
  let bookId = '';
  let token = '';

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    // A BRAND-NEW book with a chapter but NO composition Work — the fresh-book state that used to
    // dead-end a GUI user (no way to set up the co-writer in the Studio; only the agent or /edit).
    bookId = await createBook(request, token, 'S6 E2E — blackbox journey');
    await createChapter(request, token, bookId, 'Opening');
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test('a GUI-only author goes fresh-book → set up co-writer → author a rule → track progress, all in the Studio', async ({ page }) => {
    await loginViaUI(page);
    const studio = new StudioPage(page);
    await studio.goto(bookId);

    // 1 · The author opens Canon rules to declare an invariant — but there is no co-writer session yet.
    //     The panel does NOT dead-end: it offers "Set up co-writer" (D0), the self-service exit.
    await studio.openPanel('quality-canon-rules', 'Canon rules');
    const cta = page.getByTestId('work-setup-cta');
    await expect(cta).toBeVisible();

    // 2 · One click sets up the co-writer (no agent, no leaving the Studio) → the CRUD panel appears.
    await cta.click();
    await expect(page.getByTestId('studio-quality-canon-rules-panel')).toBeVisible({ timeout: 20_000 });

    // 3 · The author writes a canon rule and SEES it land — the read↔write closure a GUI user needs.
    const rule = `Lâm Phong has one arm after ch. 41. ${Date.now()}`;
    await page.getByTestId('composition-canon-input').fill(rule);
    await page.getByTestId('composition-canon-submit').click();
    await expect(page.getByTestId('composition-canon-rule').filter({ hasText: rule })).toBeVisible();

    // 4 · They open the Quality hub — the whole family is reachable from one launcher.
    await studio.openPanel('quality', 'Quality');
    await expect(page.getByTestId('quality-hub-card-quality-canon-rules')).toBeVisible();
    await expect(page.getByTestId('quality-hub-card-quality-heal')).toBeVisible();

    // 5 · They track progress and set a personal daily goal (BE-P2 — their own, not the book's shared one).
    await studio.openPanel('progress', 'Progress');
    await expect(page.getByTestId('progress-panel')).toBeVisible();
    await page.getByTestId('progress-goal-input').fill('2000');
    await page.getByTestId('progress-goal-save').click();
    // Goal persisted → the goal block + readout show it (fill bar is 0% on a fresh book, zero-width).
    await expect(page.getByTestId('progress-goal')).toBeVisible();
    await expect(page.getByTestId('progress-goal-readout')).toContainText('2,000');

    // 6 · They reach the flywheel — the publish reward. Empty on a fresh book ("publish to grow"),
    //     which is the correct, non-error empty state (not a broken panel).
    await studio.openPanel('flywheel', 'Flywheel');
    await expect(page.getByTestId('studio-flywheel-panel')).toBeVisible();

    // Verdict: from a fresh book, a GUI-only author set up the co-writer, authored canon, and tracked
    // progress — entirely in the Studio, never the legacy page, never the agent. S6's reason to exist.
  });
});
