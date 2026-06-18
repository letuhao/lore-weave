import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, listChatModels, createChatSession, deleteChatSession,
} from '../helpers/api';

// Creation-unblock RAID (G2/W4) — the chat session settings used a raw <select> for
// the project memory link; W4 replaced it with the reusable ProjectPicker (a
// search-by-name combobox, mirror of BookPicker/WorldPicker). This proves the swap
// landed in the running UI. (The sibling WorldPicker is exercised by the cross-link
// scenario, where picking a world in book Settings attaches the book.)
test.describe('Creation-unblock — reusable pickers (G2)', () => {
  test('chat session settings shows the ProjectPicker combobox (not a raw select)', async ({ page, request }) => {
    test.setTimeout(60_000);
    const token = await getAccessToken(request);
    const models = await listChatModels(request, token);
    test.skip(models.length < 1, 'needs a chat model to create a session');
    const session = await createChatSession(request, token, models[0].user_model_id, `E2E picker ${Date.now()}`);
    try {
      await loginViaUI(page);
      await page.goto(`/chat/${session.session_id}`);

      // open the per-session settings panel (where the project memory link lives)
      await page.getByTestId('chat-session-settings-button').click();

      // the project link is now the ProjectPicker — a search combobox, empty=valid
      // ("no project" default) — NOT the old <select>.
      const picker = page.getByTestId('project-picker-input');
      await expect(picker).toBeVisible({ timeout: 15_000 });
      await expect(picker).toHaveAttribute('role', 'combobox');
    } finally {
      await deleteChatSession(request, token, session.session_id).catch(() => {});
    }
  });
});
