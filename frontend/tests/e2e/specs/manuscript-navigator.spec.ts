import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// #02 Manuscript Navigator — live E2E through the gateway for the NO-WORK (flat chapters)
// path, the 10k-scale case. A fresh book + chapters is seeded via API and trashed after; the
// keyset cursor endpoint (/chapters/page) + the virtualized navigator are exercised end-to-end.
//
// The has-Work outline path (arc→chapter→scene via /outline/children) is unit-covered
// (useManuscriptTree + the Python endpoint tests); its live E2E is deferred until an
// outline-tree seed helper exists (needs parent-linked arc/chapter/scene nodes) — Debt.
test.describe('Manuscript Navigator — chapters path (no Work)', () => {
  let token: string;
  let bookId: string;
  const chapterIds: string[] = [];
  const titles = ['Alpha chapter', 'Beta chapter', 'Gamma chapter'];

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E nav ${Date.now()}`);
    for (const t of titles) chapterIds.push(await createChapter(request, token, bookId, t));
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('renders the book chapters in the manuscript navigator', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId); // manuscript is the default view, sidebar open
    await expect(page.getByTestId('manuscript-nav')).toBeVisible();
    for (const cid of chapterIds) {
      await expect(page.getByTestId(`manuscript-row-${cid}`)).toBeVisible();
    }
  });

  // The keyset boundary invariant: paging with a small limit (forcing multiple pages) must
  // return every chapter exactly once, no gap, no duplicate across the page boundary.
  test('keyset paging crosses page boundaries with no gap or duplicate', async ({ request }) => {
    const auth = { headers: { Authorization: `Bearer ${token}` } };
    const seen: string[] = [];
    let cursor: string | null = null;
    for (let i = 0; i < 10; i++) { // safety bound (3 chapters @ limit 2 → 2 pages)
      const url = `/v1/books/${bookId}/chapters/page?limit=2${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`;
      const res = await request.get(url, auth);
      expect(res.ok()).toBeTruthy();
      const body = await res.json();
      for (const c of body.items as Array<{ chapter_id: string }>) seen.push(c.chapter_id);
      cursor = body.next_cursor;
      if (!cursor) break;
    }
    expect(new Set(seen).size).toBe(seen.length);        // no duplicate across the boundary
    expect(new Set(seen)).toEqual(new Set(chapterIds));  // every seeded chapter, no gap
    expect(seen.length).toBe(chapterIds.length);
  });

  test('filter narrows to matching loaded chapters', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await expect(page.getByTestId(`manuscript-row-${chapterIds[0]}`)).toBeVisible();
    await page.getByTestId('manuscript-filter').fill('Beta');
    await expect(page.getByTestId(`manuscript-row-${chapterIds[1]}`)).toBeVisible(); // Beta
    await expect(page.getByTestId(`manuscript-row-${chapterIds[0]}`)).toHaveCount(0); // Alpha hidden
    await expect(page.getByTestId(`manuscript-row-${chapterIds[2]}`)).toHaveCount(0); // Gamma hidden
  });
});
