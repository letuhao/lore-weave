// S7-3 · Place Graph — BLACKBOX real-user journey. Persona: a web-novel author mapping their
// cultivation world's places (青云门 the sect, 幽冥谷 the valley) and the roads between them. Drives the
// REAL app end to end with NO test-only shortcuts for the actions under test, and at EVERY step asserts
// the user could actually COMPLETE it — a visible node, a rendered edge, a persisted drag, a reachable
// next step. This surface is the one *positive* anomaly the S7 audit inverted: it was FULLY OPERABLE but
// STRANDED on the legacy ChapterEditorPage's `worldmap` sub-tab — reachable from no dock panel, no
// palette entry, no agent enum. The port made it reachable; this journey proves reachable + operable +
// loop-connected (a place-node → Cast) with no dead-ends, Studio-only.
//
// Usability rubric (asserted, not just observed): the panel is reachable from the palette · the toolbar
// writes actually land (create place, link places) · a graph node is draggable AND the drag persists
// server-side (shared across devices, not localStorage) · the deep-links out are live (author-other →
// kg-entities; a place-node → Cast) · a book with no co-writer Work degrades to an HONEST hint, not a blank.
import { test, expect, type Page } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createCompositionWork, createKnowledgeProject,
} from '../helpers/api';
import { PlaceGraphPage } from '../pages/PlaceGraphPage';

test.describe('@s7 Studio · place-graph author journey (blackbox)', () => {
  let token: string;
  let bookId: string;       // fully set up: Work + chapter + knowledge project → the graph is operable
  let noWorkBookId: string; // deliberately has NO composition Work → the wrapper's honest no-Work state
  const stamp = Date.now();

  const SECT = `青云门 ${stamp}`;   // the protagonist's sect
  const VALLEY = `幽冥谷 ${stamp}`; // a rival valley — the second place, linked by a road

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);

    // The operable book: a Work (so the wrapper mounts <WorldMap>, not the no-Work hint), a chapter
    // (so the manuscript exists), and a knowledge project bound to the book (so useKnowledgeProjectId
    // resolves and the toolbar goes live — the leaf hides +Place until a project exists). We seed the
    // PROJECT but NOT the places: the journey adds 青云门/幽冥谷 itself through the real toolbar, proving
    // the create write lands from an empty graph.
    bookId = await createBook(request, token, `E2E place-graph ${stamp}`);
    await createChapter(request, token, bookId, '第一章 「入门」');
    await createCompositionWork(request, token, bookId);
    await createKnowledgeProject(request, token, `世界观 ${stamp}`, bookId);

    // A second book with NO Work — its place-graph must render the honest "set up the co-writer" state,
    // never a blank pane or a crash on `work.settings.world_map`.
    noWorkBookId = await createBook(request, token, `E2E place-graph no-work ${stamp}`);
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
    if (noWorkBookId) await trashBook(request, token, noWorkBookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  const shot = (page: Page, name: string) =>
    page.screenshot({ path: `tests/e2e/test-results/place-graph-${name}.png` }).catch(() => {});

  test('an author maps their world (reachable + operable, drag persists, loop-connected, no dead-ends)', async ({ page }) => {
    const pg = new PlaceGraphPage(page);

    // ── STEP 1 · "Where do I map my world?" — reach place-graph from the Command Palette ─────────────
    // The audit's whole finding: this surface worked but was legacy-page-only. Reachability is the fix.
    await pg.open(bookId);
    await expect(
      pg.panel,
      'STEP 1 (reachable) — place-graph must open from the palette; the audit found it operable but STRANDED (legacy sub-tab only, no dock/palette/agent route)',
    ).toBeVisible();
    await expect(pg.worldmap, 'STEP 1 — the ported <WorldMap> leaf must mount inside the dock host').toBeVisible();
    // A fresh knowledge project has no places yet — the honest empty state, with the toolbar still live.
    await expect(pg.empty, 'STEP 1 — an empty project says so (not blank) while +Place stays operable').toBeVisible();
    await expect(pg.addButton, 'STEP 1 — the +Place toolbar is live even when empty (a project exists)').toBeVisible();
    await shot(page, '1-reachable');

    // ── STEP 2 · "Add my sect" — a create write must actually LAND as a node (no silent no-op) ────────
    await pg.addPlace(SECT);
    await expect(
      pg.nodeBody(SECT),
      'STEP 2 (CRUD) — adding a place must render a real node (createEntity landed), not a silent no-op',
    ).toBeVisible({ timeout: 10_000 });
    await shot(page, '2-first-place');

    // ── STEP 3 · "Add the rival valley, then draw the road between them" — link must be OPERABLE ───────
    await pg.addPlace(VALLEY);
    await expect(pg.nodeBody(VALLEY), 'STEP 3 — the second place must render before linking').toBeVisible({ timeout: 10_000 });
    // Enter link-mode, pick both endpoints, choose the `route_to` predicate, confirm → an edge renders.
    // NOTE: the edge is an SVG <g> — Playwright's toBeVisible() is unreliable on SVG groups (no CSS box),
    // so we assert the committed edge is ATTACHED (data-pending="false" ⇒ the createRelation write landed).
    await pg.linkPlaces(SECT, VALLEY, 'route_to');
    await expect(
      pg.edges.first(),
      'STEP 3 (operable) — picking two places + a predicate + Link must render the relation edge (createRelation landed)',
    ).toBeAttached({ timeout: 10_000 });
    await expect(
      page.locator('[data-testid="relmap-edge"][data-predicate="route_to"][data-pending="false"]').first(),
      'STEP 3 — the committed edge must carry the chosen `route_to` predicate (the closed-set picker agreed with the write)',
    ).toBeAttached({ timeout: 10_000 });
    await shot(page, '3-linked');

    // ── STEP 4 · "Arrange the map" — a node must DRAG and the position must PERSIST server-side ────────
    // The draft's "↳ PATCH work.settings.world_map.positions": onNodeDragEnd → persistPositions →
    // a composition Work-settings PATCH (shared across devices, NOT localStorage). Prove BOTH the local
    // move AND the round-trip: drag, wait for the PATCH, reopen the panel fresh, assert it stuck.
    const before = await pg.nodePos(SECT);
    const patchWait = page.waitForResponse(
      (r) => /\/v1\/composition\/works\/[^/]+$/.test(r.url()) && r.request().method() === 'PATCH' && r.ok(),
      { timeout: 15_000 },
    );
    await pg.dragNode(SECT, 200, 150);
    const afterDrag = await pg.nodePos(SECT);
    expect(
      afterDrag.x,
      'STEP 4 (operable) — dragging must move the node locally (GraphCanvas pointer-drag responded)',
    ).toBeGreaterThan(before.x + 80);
    await patchWait; // the drag-end persisted to work.settings.world_map.positions (the server round-trip)
    await shot(page, '4-dragged');

    // reopen the panel FRESH — a fresh mount seeds positions from the persisted settings, not the grid
    // auto-layout. If persistence failed, the node would snap back to its (32,32)-ish grid slot.
    await pg.open(bookId);
    await expect(pg.nodeBody(SECT)).toBeVisible({ timeout: 10_000 });
    const afterReload = await pg.nodePos(SECT);
    expect(
      afterReload.x,
      'STEP 4 (no-silent-failure) — after a full reopen the dragged position must PERSIST (work.settings PATCH round-tripped), not reset to the grid',
    ).toBeGreaterThan(before.x + 80);
    await shot(page, '4b-persisted');

    // ── STEP 5 · "The map is not an island" — the deep-links out must be LIVE (loop-connected) ─────────
    // 5a — "Author other kinds →": this location-only graph deliberately excludes characters/items;
    // the bridge opens the general entity-authoring surface (kg-entities). Audit: the graph had no way
    // to reach the OTHER kinds — an island. The port wires it.
    await pg.authorOther.click();
    await expect(
      page.getByTestId('studio-kg-entities-panel'),
      'STEP 5a (loop-connected) — "Author other kinds →" must open the kg-entities panel (not a dead label)',
    ).toBeVisible({ timeout: 10_000 });
    await shot(page, '5a-author-other');

    // 5b — clicking a place (out of link-mode) opens it in the Cast codex (onViewCast deep-link). Re-open
    // place-graph (5a switched the active tab), then click the sect node → the Cast panel mounts.
    await pg.open(bookId);
    await expect(pg.nodeBody(SECT)).toBeVisible({ timeout: 10_000 });
    await pg.nodeBody(SECT).click(); // NOT in link-mode → onNodeActivate → onViewCast(name) → openPanel('cast')
    await expect(
      page.getByTestId('studio-cast-panel'),
      'STEP 5b (loop-connected) — clicking a place must open it in the Cast codex (a node is a door, not a dead tile)',
    ).toBeVisible({ timeout: 10_000 });
    await shot(page, '5b-cast');

    // ── STEP 6 · "A book with no co-writer" — the empty-precondition state must be HONEST, not blank ───
    // The leaf reads `work.settings.world_map` and would crash on a null Work; the wrapper intercepts
    // with an honest hint + a reachable next step (Open Compose). Assert the hint AND the escape hatch.
    await pg.open(noWorkBookId);
    await expect(
      pg.noWork,
      'STEP 6 (no-silent-failure) — a book with no Work must show the honest "set up the co-writer" hint, never a blank/crashed pane',
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      pg.setupCowriter,
      'STEP 6 — the no-Work state must offer a reachable next step (Open Compose), not dead-end',
    ).toBeVisible();
    await shot(page, '6-no-work');

    // ── VERDICT ───────────────────────────────────────────────────────────────────────────────────
    // Reaching here proves: place-graph is palette-reachable, its toolbar writes land (place + edge),
    // a node drags AND the arrangement persists server-side, both deep-links out are live (kg-entities +
    // Cast), and the no-Work precondition degrades honestly — all Studio-only, no dead-ends. The surface
    // that was operable-but-stranded is now operable-AND-reachable.
  });
});
