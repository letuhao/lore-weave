import { test, expect } from '@playwright/test';
import { AssistantPage } from '../pages/AssistantPage';
import { loginViaUI } from '../helpers/auth';

// QC Track-B — S1: the CORE loop, now unblocked by the F-QC-1 fix (the assistant auto-creates its diary
// session, so a real user can just type + journal). Drive it end-to-end on the built image: land in the
// ready chat → type a substantive diary message → End my day → the distiller (real gemma) produces a diary
// entry in the review. Slow (real LLM ~30-90s), so a generous timeout; runs on the shared TEST account (the
// distill writes today's entry — test data). This is the headline "does journaling actually work" proof.
test.describe('Assistant — end-of-day core loop (S1)', () => {
  test('type a diary note → End my day → a distilled entry appears', async ({ page }) => {
    test.setTimeout(180_000);
    await loginViaUI(page);
    const a = new AssistantPage(page);
    await a.goto();

    // The F-QC-1 fix: the assistant lands in a READY chat (no generic dialog). The input proves it.
    const input = page.getByTestId('chat-input-textarea');
    await expect(input, 'assistant auto-created a ready session (F-QC-1 fix)').toBeVisible({ timeout: 20_000 });

    // Journal a substantive day so the distiller has something real to work with.
    const note = 'Long day — I finally shipped the Q3 billing migration with Alice, and it is green now. Feeling relieved.';
    await input.fill(note);
    await page.getByTestId('chat-send-button').click();
    // The user turn is persisted + shown (we don't need to wait for the full LLM reply — distill reads the
    // user messages of the day).
    await expect(page.getByText('Q3 billing migration', { exact: false })).toBeVisible({ timeout: 30_000 });

    // End my day → the distiller runs on today's messages.
    await a.dismissNewChatDialog();
    await page.getByTestId('assistant-end-day').click();

    // The review surfaces a distilled entry (or an honest terminal state). Wait generously for the real LLM.
    const review = page.getByTestId('assistant-review');
    await expect(review).toBeVisible({ timeout: 150_000 });
    const entry = page.getByTestId('assistant-entry');
    await expect(entry, 'a distilled diary entry is produced from the day').toBeVisible({ timeout: 150_000 });

    // Capture the result for the record.
    await page.screenshot({ path: 'tests/e2e/test-results/journey/06-endofday-entry.png', fullPage: true });
    const text = (await entry.textContent()) ?? '';
    expect(text.trim().length, 'the entry has real distilled prose').toBeGreaterThan(20);
  });
});
