import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { StudioPage } from '../pages/StudioPage';

// S-11 — the search activity-view live smoke (D-S11-BROWSER-SMOKE). Proves in a real browser
// that the view is REACHABLE (activity icon → rail, not the "Coming soon" stub), that the rail
// OPENS the search dock panel, and that BOTH modes MOUNT (Text = the reused RawSearchPanel;
// Semantic = the SemanticSearchList). Needs a seeded book for the test account — pass its id via
// S11_BOOK_ID (defaults to the smoke fixture seeded during the S-11 review).
const BOOK_ID = process.env.S11_BOOK_ID ?? '019f73ee-e02f-7560-9d44-ed8305564c3c';

test('S-11 search view: reachable rail → panel, Text + Semantic mount (not a stub)', async ({ page }) => {
  await loginViaUI(page);
  const studio = new StudioPage(page);
  await studio.goto(BOOK_ID);

  // 1. the search activity icon exists + selecting it renders the REAL rail (not the stub).
  await studio.activity('search').click();
  await expect(page.getByTestId('studio-search-rail')).toBeVisible();
  await expect(page.getByTestId('studio-search-rail-input')).toBeVisible();
  await expect(page.getByText('Coming soon')).toHaveCount(0);

  // 2. typing a query + Search opens the search dock panel (seeded via openPanel params).
  await page.getByTestId('studio-search-rail-input').fill('the');
  await page.getByTestId('studio-search-rail-go').click();
  await expect(page.getByTestId('search-panel')).toBeVisible();

  // 3. Text mode = the reused RawSearchPanel (its own query box + toggles render).
  await expect(page.getByTestId('raw-search-panel')).toBeVisible();
  await expect(page.getByTestId('raw-search-input')).toBeVisible();

  // 4. the in-panel toggle switches to Semantic = the SemanticSearchList (mounts without a crash).
  await page.getByTestId('search-mode-semantic').click();
  await expect(page.getByTestId('studio-semantic-search')).toBeVisible();

  await page.screenshot({ path: 'test-results/s11-search-smoke.png', fullPage: true });
});
