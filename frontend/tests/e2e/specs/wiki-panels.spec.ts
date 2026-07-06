import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, trashBook } from '../helpers/api';
import { adoptCharacterKind, seedWikiArticle } from '../helpers/wiki';
import { StudioPage } from '../pages/StudioPage';

// 15_wiki_panels.md — the `wiki` + `wiki-editor` dock panels, opened live through the real
// Command Palette / Edit button against the real backend (this codebase's "LIVE gate" — see
// kg-panels.spec.ts for the precedent this mirrors). Two articles are seeded in ONE fresh book
// (Wiki articles are strictly book-scoped, unlike KG entities, which can be searched globally
// across the shared dev DB — a fresh book always starts with zero wiki articles, so real seed
// data is required here, not just search-narrowing).
//
// Beyond the standard "does it mount" sweep, this spec proves the TWO invariants this migration's
// design review actually found gaps in, which no unit test (even one that calls unmount()) can
// fully prove because unit tests mock TiptapEditor and dockview's params plumbing entirely:
//   - DOCK-10: an unsaved edit survives CLOSING (not just backgrounding) the wiki-editor dock
//     tab and reopening the same article — the module-level draft cache
//     (features/wiki/lib/wikiEditorDraftCache.ts) fix from the second /review-impl pass.
//   - G7: retargeting wiki-editor to a DIFFERENT article while dirty is gated behind a real
//     confirm dialog, not a silent overwrite.
test.describe('Wiki dock panels', () => {
  let token: string;
  let bookId: string;
  let displayName: string;
  let otherDisplayName: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E Wiki ${Date.now()}`);
    const kindId = await adoptCharacterKind(request, token, bookId);
    displayName = `Seraphine Vale ${Date.now()}`;
    otherDisplayName = `Lucian Thorne ${Date.now()}`;
    await seedWikiArticle(request, token, bookId, kindId, displayName);
    await seedWikiArticle(request, token, bookId, kindId, otherDisplayName);
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('wiki opens via the Command Palette and shows the seeded articles', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('wiki', 'Wiki');
    await expect(page.getByTestId('studio-wiki-panel')).toBeVisible();
    await expect(page.getByTestId('wiki-article-row').filter({ hasText: displayName })).toBeVisible();
    await expect(page.getByTestId('wiki-article-row').filter({ hasText: otherDisplayName })).toBeVisible();
  });

  test("Edit opens wiki-editor in-tab (DOCK-7 — the studio never navigates away)", async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('wiki', 'Wiki');
    await page.getByTestId('wiki-article-row').filter({ hasText: displayName }).click();
    await page.getByTestId('wiki-edit').click();
    await expect(page.getByTestId('studio-wiki-editor-panel')).toBeVisible();
    await expect(page.locator('.tiptap-content[contenteditable="true"]')).toBeVisible();
    // The studio's own URL never changed — no route hop, no page reload.
    await expect(page).toHaveURL(new RegExp(`/books/${bookId}/studio$`));
  });

  test('DOCK-10: an unsaved edit survives closing and reopening the wiki-editor dock tab', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('wiki', 'Wiki');
    await page.getByTestId('wiki-article-row').filter({ hasText: displayName }).click();
    await page.getByTestId('wiki-edit').click();
    await expect(page.getByTestId('studio-wiki-editor-panel')).toBeVisible();

    const editable = page.locator('.tiptap-content[contenteditable="true"]');
    const sentinel = 'This unsaved sentence must survive a tab close.';
    await editable.click();
    await editable.pressSequentially(sentinel);
    await expect(editable).toContainText(sentinel);

    // Close the dock tab OUTRIGHT (not just switch away from it) — the exact vector the G7
    // params-retargeting guard never covered, and the one this /review-impl pass found.
    await studio.closePanel(displayName);
    await expect(page.getByTestId('studio-wiki-editor-panel')).toHaveCount(0);

    // Reopen the SAME article from scratch.
    await page.getByTestId('wiki-article-row').filter({ hasText: displayName }).click();
    await page.getByTestId('wiki-edit').click();
    await expect(page.getByTestId('studio-wiki-editor-panel')).toBeVisible();
    await expect(page.locator('.tiptap-content[contenteditable="true"]')).toContainText(sentinel);
  });

  test('G7: retargeting wiki-editor to a different article while dirty is gated behind a discard confirm', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('wiki', 'Wiki');
    await page.getByTestId('wiki-article-row').filter({ hasText: displayName }).click();
    await page.getByTestId('wiki-edit').click();
    await expect(page.getByTestId('studio-wiki-editor-panel')).toBeVisible();

    const editable = page.locator('.tiptap-content[contenteditable="true"]');
    await editable.click();
    await editable.pressSequentially('mid-edit, never saved');
    await expect(editable).toContainText('mid-edit, never saved');

    // Switch focus back to the sibling `wiki` tab (still mounted — we never closed it) and open
    // the OTHER article. wiki-editor is a singleton, so this retargets the SAME dock tab via
    // updateParameters rather than opening a second one.
    await page.locator('.dv-default-tab', { hasText: /^Wiki$/ }).click();
    await expect(page.getByTestId('studio-wiki-panel')).toBeVisible();
    await page.getByTestId('wiki-article-row').filter({ hasText: otherDisplayName }).click();
    await page.getByTestId('wiki-edit').click();

    await expect(page.getByText('Discard unsaved changes?')).toBeVisible();
    // Cancel — the dirty article must still be showing, nothing switched.
    await page.getByText('Cancel').click();
    await expect(page.locator('.tiptap-content[contenteditable="true"]')).toContainText('mid-edit, never saved');

    // Now actually confirm the switch.
    await page.locator('.dv-default-tab', { hasText: /^Wiki$/ }).click();
    await page.getByTestId('wiki-article-row').filter({ hasText: otherDisplayName }).click();
    await page.getByTestId('wiki-edit').click();
    await page.getByText('Discard & switch').click();
    await expect(page.locator('.tiptap-content[contenteditable="true"]')).not.toContainText('mid-edit, never saved');
  });
});
