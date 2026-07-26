import { test, expect } from '@playwright/test';
import { BookSettingsPage } from '../pages/BookSettingsPage';
import { KnowledgeProjectOverviewPage } from '../pages/KnowledgeProjectOverviewPage';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, trashBook, getBookApi,
  createWorld, deleteWorld,
  createKnowledgeProject, deleteKnowledgeProject,
} from '../helpers/api';

// Creation-unblock RAID (G3) — the feature islands now cross-link. This scenario
// drives the two directions W6 + D-WORLD-PROJECT-BACKLINK added: (a) from the BOOK
// side, group a book into a world and open it; (b) from the KNOWLEDGE side, a
// project's Overview backlinks to its book and that book's world.
test.describe('Creation-unblock — book↔world↔project cross-links (G3)', () => {
  test('book settings attaches to a world + opens it; project overview backlinks to both', async ({ page, request }) => {
    test.setTimeout(90_000);
    const token = await getAccessToken(request);
    const ts = Date.now();
    const worldName = `E2E xlink ${ts}`;
    const world = await createWorld(request, token, worldName);
    const book = await createBook(request, token, `E2E xbook ${ts}`);
    const proj = await createKnowledgeProject(request, token, `E2E xproj ${ts}`, book);
    try {
      await loginViaUI(page);

      // ── 4a — BOOK → WORLD (BookWorldSection: the WorldPicker is the control) ──
      const settings = new BookSettingsPage(page);
      await settings.goto(book);
      await expect(settings.openInWorld).toBeHidden(); // standalone — no backlink yet

      await settings.attachToWorld(worldName);

      // the "Open in world" backlink appears (DOCK-7 — it's an onClick-driven button now,
      // not a raw <a href>; the click below proves it targets the right world workspace)…
      await expect(settings.openInWorld).toBeVisible({ timeout: 15_000 });
      // …and the server reflects the grouping (book.world_id set).
      await expect.poll(async () => (await getBookApi(request, token, book)).world_id, { timeout: 15_000 })
        .toBe(world.world_id);

      // the backlink navigates into the world workspace.
      await settings.openInWorld.click();
      await page.waitForURL(`**/worlds/${world.world_id}`, { timeout: 15_000 });
      await expect(page.getByTestId('world-workspace')).toBeVisible();

      // ── 4b — KNOWLEDGE PROJECT → BOOK + WORLD (Overview backlinks) ──
      const overview = new KnowledgeProjectOverviewPage(page);
      await overview.goto(proj.project_id);
      await expect(overview.bookLink).toBeVisible({ timeout: 15_000 });
      await expect(overview.bookLink).toHaveAttribute('href', `/books/${book}`);
      // the world link is present BECAUSE the book is now grouped into the world.
      await expect(overview.worldLink).toBeVisible();
      await expect(overview.worldLink).toHaveAttribute('href', `/worlds/${world.world_id}`);
    } finally {
      await deleteKnowledgeProject(request, token, proj.project_id).catch(() => {});
      await deleteWorld(request, token, world.world_id).catch(() => {});
      await trashBook(request, token, book).catch(() => {});
    }
  });
});
