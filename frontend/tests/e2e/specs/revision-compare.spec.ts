import { test, expect } from '@playwright/test';
import { RevisionComparePage } from '../pages/RevisionComparePage';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, seedChapterWithRevisions, trashBook } from '../helpers/api';

// V0 scenario tests U9 + B8 — Chapter Revision Compare. No model needed; data is
// seeded via API, then the compare UI is driven for real.
test.describe('Revision Compare (U9 / B8)', () => {
  test('B8.1 + U9: diffs two revisions, highlights changed words, toggles inline', async ({ page, request }) => {
    const token = await getAccessToken(request);
    // two revisions differing by one word on the first line; "shared middle" and
    // "gamma end" are common.
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, [
      'alpha start\nshared middle\ngamma end',
      'beta start\nshared middle\ngamma end',
    ]);
    try {
      await loginViaUI(page);
      const cmp = new RevisionComparePage(page);
      await cmp.goto(bookId, chapterId);

      // side-by-side renders + only the changed words tint (not "shared"/"gamma")
      await expect(cmp.diffSxs).toBeVisible();
      const changed = await cmp.changedWords();
      expect(changed).toContain('alpha');
      expect(changed).toContain('beta');
      expect(changed).not.toContain('shared');
      expect(changed).not.toContain('gamma');

      // toggle to inline → git-style ops present
      await cmp.modeInline.click();
      await expect(cmp.diffInline).toBeVisible();
      await expect(cmp.diffInline.locator('[data-op="insert"]')).toHaveCount(1);
      await expect(cmp.diffInline.locator('[data-op="delete"]')).toHaveCount(1);
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B8.4: CJK diff highlights only the changed character', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, [
      '封神演義\n共同\n結尾',
      '封神演功\n共同\n結尾',
    ]);
    try {
      await loginViaUI(page);
      const cmp = new RevisionComparePage(page);
      await cmp.goto(bookId, chapterId);
      await expect(cmp.diffSxs).toBeVisible();
      const changed = await cmp.changedWords();
      // only 義/功 differ; 封神演 + the common lines must not be marked changed
      expect(changed).toContain('義');
      expect(changed).toContain('功');
      expect(changed).not.toContain('封');
      expect(changed).not.toContain('共同');
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B8.2: same revision on both sides → no differences', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, [
      'one\ntwo', 'one\nTWO',
    ]);
    try {
      await loginViaUI(page);
      const cmp = new RevisionComparePage(page);
      await cmp.goto(bookId, chapterId);
      await expect(cmp.diffSxs).toBeVisible();
      const opts = await cmp.optionValues();
      // point both sides at the newest revision
      await cmp.leftSelect.selectOption(opts[0]);
      await cmp.rightSelect.selectOption(opts[0]);
      await expect(cmp.same).toBeVisible();
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B8.8: a chapter with <2 revisions shows the need-two message', async ({ page, request }) => {
    const token = await getAccessToken(request);
    // zero extra saves → only the chapter-create seed revision (1 total)
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, []);
    try {
      await loginViaUI(page);
      const cmp = new RevisionComparePage(page);
      await cmp.goto(bookId, chapterId);
      await expect(cmp.needTwo).toBeVisible();
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
