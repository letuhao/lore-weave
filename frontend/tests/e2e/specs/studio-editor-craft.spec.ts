import { test, expect, type Page } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// 16_chapter_editor_parity_and_retirement.md Phase 2 — editor-craft UX parity. These specs
// cover the pieces unit tests structurally can't: real dockview panel registration, a real
// data-testid `class`-driven toggle round-trip against the live TiptapEditor, and — the
// highest-value case — a REAL second OS window via window.open (Playwright `popup` event),
// which is exactly the boundary the /review-impl HIGH (silent-drop popout Apply) lived on.
// Grammar/glossary/heatmap/provenance content-level behavior (LanguageTool response, mention
// tinting, autocomplete insert) is covered by EditorPanel.test.tsx + component unit tests —
// this file proves the WIRING (button → live editor prop → visible DOM effect), not LLM/
// third-party-service content.
test.describe('Studio editor-craft UX (#16 Phase 2)', () => {
  let token: string;
  let bookId: string;
  let chapterId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E editor-craft ${Date.now()}`);
    chapterId = await createChapter(request, token, bookId, 'Craft chapter');
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('grammar/heatmap toggles flip on click', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await page.getByTestId(`manuscript-row-${chapterId}`).click();
    await expect(page.getByTestId('studio-editor-panel')).toBeVisible();

    // Grammar is a per-DEVICE persisted preference (localStorage, not per-chapter Tier-4
    // state) — its starting value here depends on whatever this browser profile last left it
    // at, so assert the TOGGLE behavior (flips, then flips back) rather than a fixed initial
    // value, which would make the test order-dependent on unrelated prior runs.
    const grammar = page.getByTestId('studio-editor-toggle-grammar');
    const heatmap = page.getByTestId('studio-editor-toggle-heatmap');
    const grammarWasActive = ((await grammar.getAttribute('class')) ?? '').includes('text-primary');
    const heatmapWasActive = ((await heatmap.getAttribute('class')) ?? '').includes('text-primary');

    await grammar.click();
    if (grammarWasActive) await expect(grammar).not.toHaveClass(/text-primary/);
    else await expect(grammar).toHaveClass(/text-primary/);

    await heatmap.click();
    if (heatmapWasActive) await expect(heatmap).not.toHaveClass(/text-primary/);
    else await expect(heatmap).toHaveClass(/text-primary/);

    // Flip back — leave the shared device preference as this test found it.
    await grammar.click();
    await heatmap.click();
  });

  test('focus mode hides the flanking Revision History strip', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await page.getByTestId(`manuscript-row-${chapterId}`).click();
    await expect(page.getByTestId('studio-editor-panel')).toBeVisible();
    // Present by default (not focus mode) — this is the real DOM effect the toggle controls,
    // not just the button's own CSS class.
    await expect(page.getByTestId('studio-revision-history')).toBeVisible();

    await page.getByTestId('studio-editor-toggle-focus').click();
    await expect(page.getByTestId('studio-revision-history')).toHaveCount(0);

    await page.getByTestId('studio-editor-toggle-focus').click();
    await expect(page.getByTestId('studio-revision-history')).toBeVisible();
  });

  test('Original Source toolbar button opens a read-only dock panel for this chapter', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await page.getByTestId(`manuscript-row-${chapterId}`).click();
    await expect(page.getByTestId('studio-editor-panel')).toBeVisible();

    await page.getByTestId('studio-editor-open-original-source').click();
    await expect(page.getByTestId('studio-original-source')).toBeVisible();
    // This chapter was created directly in the editor (no imported source) — the panel's own
    // empty-state copy, not a loading spinner left hanging or a raw fetch error.
    await expect(page.getByTestId('studio-original-source')).toContainText(/no original source/i, { timeout: 10_000 });
  });

  test('popout Compose opens a REAL OS window at /studio/popout, Dock-back closes it and re-enables Pop out', async ({ page, context }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await page.getByTestId(`manuscript-row-${chapterId}`).click();
    await expect(page.getByTestId('studio-editor-panel')).toBeVisible();
    await studio.openPanel('compose', 'Compose');
    await expect(page.getByTestId('studio-compose-panel')).toBeVisible();
    // A fresh Compose panel has no chat session yet — Chat's own "Start New Chat" dialog
    // covers the panel (including the Pop-out button) until a session exists. Creating one
    // is free (no LLM call happens until a message is sent).
    await page.getByRole('button', { name: 'Start Chat' }).click();

    const popoutButton = page.getByTestId('studio-compose-popout');
    await expect(popoutButton).toBeEnabled();
    // The app renders under React.StrictMode (main.tsx) — dev-only, double-invokes PopoutBridge's
    // open effect (open → cleanup closes it → open again), so `waitForEvent('popup')` can resolve
    // on a window that's already gone by the time it's used. Production builds don't double-invoke
    // effects, so this is a dev-server testing artifact, not a real popout bug — collect every new
    // page and use whichever one is still open once the churn settles.
    const newPages: Page[] = [];
    context.on('page', (p) => newPages.push(p));
    await popoutButton.click();
    await expect.poll(() => newPages.some((p) => !p.isClosed())).toBe(true);
    const popup = newPages.find((p) => !p.isClosed())!;
    await popup.waitForLoadState();
    expect(popup.url()).toContain('/studio/popout');
    expect(popup.url()).toContain(`chapter=${chapterId}`);
    await expect(popoutButton).toBeDisabled(); // opener-side: already popped out

    // The popout is a SEPARATE React root — its <Chat> doesn't inherit the opener's just-created
    // session, so it shows its own "Start New Chat" dialog first.
    await popup.getByRole('button', { name: 'Start Chat' }).click();

    const dockBack = popup.getByTestId('studio-popout-dock-back');
    await expect(dockBack).toBeVisible();
    // dockBack's handler calls window.close() itself, synchronously — race the wait against the
    // click (like the popup-open wait above) instead of awaiting the click first, or the 'close'
    // event can fire before the listener attaches.
    await Promise.all([popup.waitForEvent('close'), dockBack.click()]);

    // The opener re-enables Pop out once PopoutBridge's close-poll/dock-back message fires
    // onClosed — the same seam a real user relies on to get their window "back".
    await expect(popoutButton).toBeEnabled();
    // The studio in the original tab never navigated away — the popout is a second window,
    // not a route hop in this one.
    await expect(page).toHaveURL(new RegExp(`/books/${bookId}/studio$`));
  });
});
