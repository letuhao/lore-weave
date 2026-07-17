// Wave-4 (D-MOTIF-GRAPH-CANVAS) — the motif graph canvas: open the panel, DRAG a node with CDP
// stepped mouse (reactflow uses d3-drag internally, so synthetic/browser_drag events don't drive it —
// the [[playwright-cdp-mouse-drives-d3-drag]] recipe), and prove the position PERSISTS (the PATCH
// wrote it) via the graph API, then survives a reload. Seeds motifs + a link via the real gateway.
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, trashBook } from '../helpers/api';
import { seedMotif, createMotifLink } from '../helpers/motif';
import { StudioPage } from '../pages/StudioPage';

test.describe('@s4 Studio · motif-graph canvas', () => {
  let token: string;
  let bookId = '';
  let m1 = '';
  let m2 = '';
  const stamp = Date.now();

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E motif-graph ${stamp}`);
    // Motifs are the caller's own (user-tier, book-agnostic) — the graph shows the caller's own +
    // book-shared nodes, so a private motif appears in this book's graph without a book_id.
    m1 = await seedMotif(request, token, { code: `g.a.${stamp}`, name: `GraphA ${stamp}` });
    m2 = await seedMotif(request, token, { code: `g.b.${stamp}`, name: `GraphB ${stamp}` });
    await createMotifLink(request, token, m1, m2, 'precedes');
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('dragging a node persists its position (drag → PATCH → survives reload)', async ({ page, request }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('motif-graph', 'motif graph');
    await expect(page.getByTestId('motif-graph-canvas')).toBeVisible();

    // the reactflow node for m1 (RF stamps data-id on .react-flow__node)
    const node = page.locator(`.react-flow__node[data-id="${m1}"]`);
    await expect(node).toBeVisible();
    const box = await node.boundingBox();
    expect(box).not.toBeNull();

    // CDP stepped drag (trusted events drive d3-drag; a synthetic drag would no-op)
    const cx = box!.x + box!.width / 2;
    const cy = box!.y + box!.height / 2;
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    await page.mouse.move(cx + 160, cy + 110, { steps: 12 });
    await page.mouse.up();

    // the debounced PATCH persisted m1's position — assert via the graph API (drag → PATCH → DB)
    await expect.poll(async () => {
      const r = await request.get(`/v1/composition/books/${bookId}/motif-graph`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const d = await r.json();
      return Boolean(d.layout?.positions?.[m1]);
    }, { timeout: 5000 }).toBe(true);

    // and it survives a reload (the layout seeds the canvas from the stored positions)
    await page.reload();
    await studio.openPanel('motif-graph', 'motif graph');
    await expect(page.locator(`.react-flow__node[data-id="${m1}"]`)).toBeVisible();
  });
});
