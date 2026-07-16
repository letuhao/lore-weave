import { test, expect } from '@playwright/test';
import { StudioComposePanels } from '../pages/StudioComposePanels';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createCompositionWork, createCompositionScene, setWorkDefaultModel, listChatModels,
} from '../helpers/api';

// S1-B3 — the studio Editor's inline "Continue from cursor" ghost now FEEDS the correction flywheel
// (the one Dead capability the audit found: it generated but never posted a correction). MODEL-GATED.
test.describe('Studio editor inline-ghost correction capture (S1-B3) [model-gated]', () => {
  let token: string;
  let bookId: string;
  let chapterId: string;
  let drafter: string | undefined;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    const chatModels = await listChatModels(request, token);
    drafter = (chatModels.find((m) => /Qwen2\.5 7B|non-reasoning|fast/i.test(m.provider_model_name ?? m.alias ?? ''))
      ?? chatModels[0])?.user_model_id;
    bookId = await createBook(request, token, `E2E s1-inline ${Date.now()}`);
    chapterId = await createChapter(request, token, bookId, 'Inline chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    await createCompositionScene(request, token, projectId, chapterId, 'Opening scene');
    // The inline "Continue" is gated on a RESOLVED default model (the test account has none).
    if (drafter) await setWorkDefaultModel(request, token, projectId, drafter);
  });

  test.afterAll(async ({ request }) => {
    await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(() => {
    test.skip(!drafter, 'needs LM Studio + ≥1 chat-tagged user-model');
    test.setTimeout(180_000);
  });

  async function streamInlineGhost(s: StudioComposePanels): Promise<void> {
    await s.editorContent.click(); // focus the editor + set a real caret before "Continue from cursor"
    await expect(s.inlineContinue).toBeEnabled();
    await s.inlineContinue.click();
    await expect(s.inlineGhostText).toBeVisible({ timeout: 120_000 });
    await expect.poll(async () => (await s.inlineGhostText.innerText()).trim().length, { timeout: 120_000 })
      .toBeGreaterThan(20);
  }

  // ORDER MATTERS: the Accept path runs FIRST (a CLEAN full-stream generation, no mid-stream stop), then
  // the Discard path runs LAST. Discard clicks stop mid-stream, which disconnects the LLM mid-response and
  // can wedge a local LM Studio queue (see lesson lm-studio-queue-wedge); keeping it last means the wedge
  // can never starve a sibling test in this file.
  test('Accept does NOT post a correction (H2 self-reinforcement guard)', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId);
    await s.openEditor();
    await streamInlineGhost(s);

    let correctionFired = false;
    page.on('response', (r) => {
      if (/\/jobs\/.+\/correction/.test(r.url()) && r.request().method() === 'POST') correctionFired = true;
    });
    await s.inlineAccept.click({ force: true });
    // Accept commits the ghost into the doc + closes the overlay (a real signal to wait on, not a sleep).
    await expect(s.inlineGhostText).toHaveCount(0);
    // …and it was NOT captured as a correction (accept-as-is is not a dissatisfaction signal — H2).
    expect(correctionFired).toBe(false);
  });

  test('Continue → inline ghost streams at the caret → Discard posts a REJECT correction', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId); // opens the editor on this chapter
    await s.openEditor();
    await streamInlineGhost(s);

    const correction = page.waitForResponse(
      (r) => /\/jobs\/.+\/correction/.test(r.url()) && r.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await s.inlineDiscard.click({ force: true }); // fixed-position caret overlay may sit outside the viewport
    const resp = await correction;
    expect(resp.status()).toBeGreaterThanOrEqual(200);
    expect(resp.status()).toBeLessThan(300);
  });
});
