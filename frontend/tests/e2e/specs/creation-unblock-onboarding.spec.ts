import { test, expect } from '@playwright/test';
import { WorldWorkspacePage } from '../pages/WorldWorkspacePage';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, listWorlds, deleteWorld } from '../helpers/api';

// Creation-unblock RAID (G5) — onboarding's "Build a world" promise was broken
// because it routed to /worlds, which then dead-ended at the empty, un-populatable
// workspace (G1). With G1 landed it's a real funnel. This scenario walks the WHOLE
// funnel in a browser: onboarding intent → create a world → land in a workspace
// that exposes the populate CTAs (no longer a dead-end).
test.describe('Creation-unblock — onboarding "Build a world" funnel (G5)', () => {
  test('intent → /worlds → create world → usable workspace with populate CTAs', async ({ page, request }) => {
    test.setTimeout(90_000);
    const token = await getAccessToken(request);
    const worldName = `E2E onboarding ${Date.now()}`;
    let worldId: string | undefined;
    try {
      await loginViaUI(page);

      // /onboarding/new forces the intent fork regardless of the seen-flag.
      await page.goto('/onboarding/new');
      await expect(page.getByTestId('intent-screen')).toBeVisible();

      // "Build a world" routes into the world container (the funnel entry).
      await page.getByTestId('intent-world').click();
      await page.waitForURL('**/worlds', { timeout: 15_000 });
      await expect(page.getByTestId('worlds-browser')).toBeVisible();

      // Create a world through the UI — on submit it lands DIRECTLY in the new
      // world's workspace (the funnel's payoff), no extra click.
      await page.getByTestId('create-world-button').click();
      await page.getByTestId('create-world-name').fill(worldName);
      await page.getByTestId('create-world-submit').click();
      await page.waitForURL(/\/worlds\/[0-9a-fA-F-]{36}$/, { timeout: 15_000 });
      worldId = page.url().split('/worlds/')[1];
      expect(worldId, 'created world id from the workspace URL').toBeTruthy();

      // The workspace is USABLE (populate CTAs + rollups present), not the old
      // empty dead-end. (Sanity-check the world is real via the API too.)
      const worlds = await listWorlds(request, token);
      expect(worlds.items.some((w) => w.world_id === worldId), 'world persisted server-side').toBe(true);
      const ws = new WorldWorkspacePage(page);
      await expect(ws.populateActions).toBeVisible();
      await expect(ws.addBookButton).toBeVisible();
      await expect(ws.graphSection).toBeVisible();
      await expect(ws.timelineSection).toBeVisible();
    } finally {
      if (worldId) await deleteWorld(request, token, worldId).catch(() => {});
    }
  });
});
