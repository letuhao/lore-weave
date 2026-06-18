import { test, expect } from '@playwright/test';
import { WorldWorkspacePage } from '../pages/WorldWorkspacePage';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, trashBook,
  createWorld, deleteWorld, listWorldBooks, moveBookIntoWorld,
  createCompositionWork,
} from '../helpers/api';

// Creation-unblock RAID — the headline gap was the World workspace dead-end: after
// creating a world you landed on an empty living-world tree with NO way to add a
// book or branch a what-if. This scenario proves the populate loop (G1) + the
// graph/timeline rollups (G4 / D-WORLD-TIMELINE-ROLLUP) are wired end-to-end in a
// real browser — the exact coverage the RAID existed to close.
test.describe('Creation-unblock — world workspace populate + rollups (G1/G4)', () => {
  test('renders the workspace surfaces, attaches + creates books, routes a what-if', async ({ page, request }) => {
    test.setTimeout(90_000);
    const token = await getAccessToken(request);
    const ts = Date.now();
    const world = await createWorld(request, token, `E2E world ${ts}`);
    const existingTitle = `E2E attach ${ts}`;
    const existingBook = await createBook(request, token, existingTitle);
    const createdTitle = `E2E created ${ts}`;
    try {
      await loginViaUI(page);
      const ws = new WorldWorkspacePage(page);
      await ws.goto(world.world_id);

      // The workspace surfaces ALL the previously-missing affordances + rollups.
      await expect(ws.populateActions).toBeVisible();
      await expect(ws.addBookButton).toBeVisible();
      await expect(ws.graphSection).toBeVisible();
      await expect(ws.timelineSection).toBeVisible();

      // Empty world → the living tree is empty and "create a what-if" is gated
      // (decision ⑦ — a what-if needs a canon source).
      await expect(ws.livingEmpty).toBeVisible();
      await expect(ws.createWhatIfButton).toBeDisabled();

      // G1 — attach an EXISTING book by name (BookPicker) → it lands in the world.
      await ws.attachExistingBook(existingTitle);
      await expect.poll(async () => {
        const { items } = await listWorldBooks(request, token, world.world_id);
        return items.some((b) => b.book_id === existingBook);
      }, { timeout: 15_000 }).toBe(true);

      // G1 — create a NEW book inline → it's created + attached (two-step, no orphan).
      await ws.createAndAttachBook(createdTitle);
      await expect.poll(async () => {
        const { items } = await listWorldBooks(request, token, world.world_id);
        return items.some((b) => b.title === createdTitle);
      }, { timeout: 15_000 }).toBe(true);

      // G4 — the graph + timeline rollups render. A graph-less world unions to empty
      // (no extraction here — the honest M0 state the W2/W6 live-smokes also found),
      // so we assert the section's own empty hint OR a populated canvas.
      await expect(ws.graphHint.or(page.getByTestId('world-rollup-graph'))).toBeVisible();
      await expect(ws.timelineHint.or(page.getByTestId('world-timeline-list'))).toBeVisible();

      // G1 — with a CANON Work in the world, "create a what-if" routes into that
      // Work's studio (where the divergence wizard lives). Seed a work + reload.
      await createCompositionWork(request, token, existingBook);
      await ws.goto(world.world_id);
      await expect(ws.createWhatIfButton).toBeEnabled({ timeout: 15_000 });
      await ws.createWhatIfButton.click();
      await page.waitForURL(`**/books/${existingBook}?work=*`, { timeout: 15_000 });
    } finally {
      await deleteWorld(request, token, world.world_id);
      await trashBook(request, token, existingBook);
      // the inline-created book returns to standalone on world delete → trash it too.
      const { items } = await listWorldBooks(request, token, world.world_id).catch(() => ({ items: [] as Array<{ book_id: string; title: string }> }));
      const created = items.find((b) => b.title === createdTitle);
      if (created) await trashBook(request, token, created.book_id);
    }
  });

  // A focused second case: a world pre-seeded (via API) with a member book renders a
  // NON-empty living tree once that book has a Work — proving the tree reflects
  // server membership, not just the just-clicked optimistic state.
  test('a pre-seeded member book with a Work shows in the living-world tree', async ({ page, request }) => {
    test.setTimeout(60_000);
    const token = await getAccessToken(request);
    const ts = Date.now();
    const world = await createWorld(request, token, `E2E seeded ${ts}`);
    const book = await createBook(request, token, `E2E member ${ts}`);
    try {
      await moveBookIntoWorld(request, token, world.world_id, book);
      await createCompositionWork(request, token, book);
      await loginViaUI(page);
      const ws = new WorldWorkspacePage(page);
      await ws.goto(world.world_id);
      // the tree is NON-empty (the seeded book's canon Work) — not the dead-end.
      await expect(ws.livingTree).toBeVisible({ timeout: 15_000 });
      await expect(ws.livingEmpty).toBeHidden();
    } finally {
      await deleteWorld(request, token, world.world_id);
      await trashBook(request, token, book);
    }
  });
});
