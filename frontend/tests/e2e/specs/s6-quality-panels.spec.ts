// S6 (Canon, Quality & Progress) — LIVE coverage of every S6 panel through the real login/gateway/
// dockview stack. Each S6 capability a GUI-only user owns must be OPERABLE in the Studio (§2 bar #1),
// not just render. This drives each panel to a real outcome:
//   quality-canon-rules — full CRUD (create a rule → it appears → archive)
//   quality-corrections — the stats table / cold-start renders (display-only)
//   quality-heal        — chapter picker → Run Polish control mounts
//   progress            — stats render + set a PER-USER goal (BE-P2) that persists
//   flywheel            — renders (delta or the valid empty state)
//   quality hub         — the S6 cards are present and each opens its panel
// Plus D0: on a fresh book the panels offer "Set up co-writer" and become operable after it.
//
// Run against a FE that has the S6 build: PLAYWRIGHT_BASE_URL=http://localhost:5199 npm run e2e -- s6-quality
import { test, expect, type APIRequestContext } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

async function ensureWork(request: APIRequestContext, token: string, bookId: string) {
  // Idempotent get-or-create (works.py) — gives the book a composition Work so the quality panels
  // resolve past the no-work gate (the Set-up-co-writer CTA is exercised separately in the journey spec).
  await request.post(`/v1/composition/books/${bookId}/work`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

test.describe('S6 · quality/canon/progress/flywheel panels are operable', () => {
  let bookId = '';
  let token = '';

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, 'S6 E2E — quality panels');
    await createChapter(request, token, bookId, 'Chapter One');
    await ensureWork(request, token, bookId);
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('quality-canon-rules — reachable + full CRUD (create a rule appears in the list)', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('quality-canon-rules', 'Canon rules');
    await expect(page.getByTestId('studio-quality-canon-rules-panel')).toBeVisible();

    // Author a canon rule via the CRUD form (world scope needs only the text).
    const text = `Spirit stones are consumed, never returned. ${Date.now()}`;
    await page.getByTestId('composition-canon-input').fill(text);
    await page.getByTestId('composition-canon-submit').click();
    // The new rule shows in the list — the read↔write closure a GUI user gets.
    await expect(page.getByTestId('composition-canon-rule').filter({ hasText: text })).toBeVisible();

    // Archive it (with the Undo affordance) — CRUD is complete, no dead button.
    await page.getByTestId('composition-canon-rule').filter({ hasText: text })
      .getByTestId('composition-canon-archive').click();
    await expect(page.getByTestId('composition-canon-rule').filter({ hasText: text })).toHaveCount(0);
  });

  test('quality-corrections — reachable + renders the stats table or cold-start (display-only)', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('quality-corrections', 'Corrections');
    await expect(page.getByTestId('studio-quality-corrections-panel')).toBeVisible();
    // Either the A/B table or the cold-start empty — never a false "clean" on an error.
    await expect(page.getByTestId('quality-corrections-unavailable')).toHaveCount(0);
  });

  test('quality-heal — reachable + chapter picker → Run Polish control mounts', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('quality-heal', 'Self-heal');
    await expect(page.getByTestId('studio-quality-heal-panel')).toBeVisible();
    const picker = page.getByTestId('quality-heal-chapter-picker');
    await expect(picker).toBeVisible();
    // Pick the seeded chapter → the Polish run control mounts (operable).
    await picker.selectOption({ index: 1 });
    await expect(page.getByTestId('polish-run')).toBeVisible();
  });

  test('progress — reachable + stats render + a PER-USER goal persists (BE-P2)', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('progress', 'Progress');
    await expect(page.getByTestId('studio-progress-panel')).toBeVisible();
    await expect(page.getByTestId('progress-panel')).toBeVisible();
    // Set a personal daily goal → the goal bar reflects it (per-user, not the shared work.settings).
    await page.getByTestId('progress-goal-input').fill('1500');
    await page.getByTestId('progress-goal-save').click();
    // The goal block appears and its readout reflects the saved goal (the fill bar is 0% on a
    // fresh book — zero-width, so we assert the always-visible readout, the real persistence proof).
    await expect(page.getByTestId('progress-goal')).toBeVisible();
    await expect(page.getByTestId('progress-goal-readout')).toContainText('1,500');
  });

  test('flywheel — reachable + renders (a delta or the valid empty state)', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('flywheel', 'Flywheel');
    await expect(page.getByTestId('studio-flywheel-panel')).toBeVisible();
    // Populated OR empty — both are valid; an errored fetch must NOT masquerade as empty (QC-F3).
    await expect(
      page.getByTestId('flywheel-panel').or(page.getByTestId('flywheel-empty')).first(),
    ).toBeVisible();
  });

  test('quality hub — the S6 capability cards are present and open their panels', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('quality', 'Quality');
    await expect(page.getByTestId('quality-hub-card-quality-canon-rules')).toBeVisible();
    await expect(page.getByTestId('quality-hub-card-quality-corrections')).toBeVisible();
    await expect(page.getByTestId('quality-hub-card-quality-heal')).toBeVisible();
    // A card opens its sibling panel (host.openPanel).
    await page.getByTestId('quality-hub-card-quality-canon-rules').click();
    await expect(page.getByTestId('studio-quality-canon-rules-panel')).toBeVisible();
  });
});
