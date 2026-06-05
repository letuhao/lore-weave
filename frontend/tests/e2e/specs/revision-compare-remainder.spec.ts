import { test, expect } from '@playwright/test';
import { RevisionComparePage } from '../pages/RevisionComparePage';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, seedChapterWithRevisions, trashBook } from '../helpers/api';

// V0 scenario tests B8.5 / B8.7 / B8.9 — the revision-compare edge cases the first
// compare spec didn't cover. B8.3 (word-level) is covered by B8.1's changedWords
// assertion; B8.6 (huge fully-distinct → truncated) needs ~2000-line revisions to
// trip the 4M-cell perf guard and is Go-unit-covered, so it stays unit-only.
test.describe('Revision Compare remainder (B8.5/B8.7/B8.9)', () => {
  test('B8.5: a large chapter with a one-line edit diffs as one line, not a full replace', async ({ page, request }) => {
    const token = await getAccessToken(request);
    // 12 identical lines except line 6 — the prefix/suffix trim must keep the
    // unchanged lines EQUAL (a full-replace would mark every line changed).
    const lines = Array.from({ length: 12 }, (_, i) => `line ${i + 1}`);
    const before = lines.join('\n');
    const after = lines.map((l, i) => (i === 5 ? 'line SIX edited' : l)).join('\n');
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, [before, after]);
    try {
      await loginViaUI(page);
      const cmp = new RevisionComparePage(page);
      await cmp.goto(bookId, chapterId);
      await expect(cmp.diffSxs).toBeVisible();
      await cmp.modeInline.click();
      await expect(cmp.diffInline).toBeVisible();

      // most rows stay equal (trim worked); only the one line is replaced
      const equal = await cmp.diffInline.locator('[data-op="equal"]').count();
      const ins = await cmp.diffInline.locator('[data-op="insert"]').count();
      const del = await cmp.diffInline.locator('[data-op="delete"]').count();
      expect(equal).toBeGreaterThanOrEqual(10);
      expect(ins).toBeLessThanOrEqual(2);
      expect(del).toBeLessThanOrEqual(2);
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B8.7: a chapter with >100 revisions paginates the picker (newest 100 + load more)', async ({ page, request }) => {
    test.setTimeout(120_000);
    const token = await getAccessToken(request);
    // 100 saves + the chapter-create revision = 101 total → one page over the limit
    const texts = Array.from({ length: 100 }, (_, i) => `revision body ${i + 1}`);
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, texts);
    try {
      await loginViaUI(page);
      const cmp = new RevisionComparePage(page);
      await cmp.goto(bookId, chapterId);
      await expect(cmp.diffSxs).toBeVisible();

      // first page caps at 100
      expect((await cmp.optionValues()).length).toBe(100);
      // load more → the 101st becomes selectable
      await expect(cmp.loadMore).toBeVisible();
      await cmp.loadMore.click();
      await expect.poll(async () => (await cmp.optionValues()).length, { timeout: 15_000 })
        .toBeGreaterThan(100);
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B8.9: a bogus or cross-book revision id errors cleanly (no leak)', async ({ request }) => {
    const token = await getAccessToken(request);
    const a = await seedChapterWithRevisions(request, token, ['a one', 'a two']);
    const b = await seedChapterWithRevisions(request, token, ['b one', 'b two']);
    const auth = { headers: { Authorization: `Bearer ${token}` } };
    try {
      // a non-existent revision id → 4xx, never a 200 with another chapter's text
      const bogus = '00000000-0000-7000-8000-000000000000';
      const r1 = await request.get(
        `/v1/books/${a.bookId}/chapters/${a.chapterId}/revisions/compare?left=${bogus}&right=${bogus}`, auth,
      );
      expect([400, 404]).toContain(r1.status());

      // a real revision id from book B used against book A's chapter → 404 (the
      // ownership/chapter join rejects it; no cross-chapter content leak)
      const bRevs = await request.get(`/v1/books/${b.bookId}/chapters/${b.chapterId}/revisions`, auth);
      const bRevId = ((await bRevs.json()) as { items: Array<{ revision_id: string }> }).items[0].revision_id;
      const r2 = await request.get(
        `/v1/books/${a.bookId}/chapters/${a.chapterId}/revisions/compare?left=${bRevId}&right=${bRevId}`, auth,
      );
      expect([400, 404]).toContain(r2.status());
    } finally {
      await trashBook(request, token, a.bookId);
      await trashBook(request, token, b.bookId);
    }
  });
});
