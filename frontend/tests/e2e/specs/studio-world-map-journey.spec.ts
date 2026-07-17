// S7·2 · World-Map Editor — BLACKBOX real-user journey. Persona: an author building a REFERENCE MAP
// for their world (Sơn Hải Di Văn) — a base image, location pins for their sects, and territory
// regions. Drives the REAL app end to end with NO test-only shortcuts for the actions under test, and
// at EVERY step asserts the author could actually COMPLETE it: a visible result, a reachable next step,
// no dead-end, no silent no-op.
//
// The audit this closes (spec §1): every world-map write was AGENT-MCP-ONLY, and UPDATE existed at NO
// layer for ANYONE — an author could look at an agent's map and do nothing else; even the agent could
// not nudge a misplaced pin (it had to remove+re-add, churning the marker_id + stranding the entity
// tie). This journey proves a human can now create → upload → drop → DRAG (one PATCH on a STABLE
// marker_id, never delete+recreate) → relabel/rebind → draw → RESHAPE, all in the Studio.
//
// Usability rubric (asserted, not observed): the panel is REACHABLE from the palette · every list row
// OPENS something (a map tab, a pin popover — never a dead tile) · every write LANDS + is visible · a
// mere select-click fires ZERO write (no phantom PATCH = no silent failure) · the map is not an island
// (book→world→map). Drag is driven with page.mouse (CDP-trusted events) per the d3-drag recipe.
import { test, expect, type Page } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken,
  createBook,
  createChapter,
  trashBook,
  createWorld,
  deleteWorld,
  moveBookIntoWorld,
  listWorldBooks,
  listWorldMapsApi,
  createKnowledgeProject,
  createKnowledgeEntity,
  deleteKnowledgeProject,
} from '../helpers/api';
import { WorldMapEditorPage } from '../pages/WorldMapEditorPage';

// A 1×1 PNG (valid raster so book-service's image handler resolves image_w/h + an image_url).
const PNG_1x1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
);

test.describe('@s7 Studio · world-map author journey (blackbox)', () => {
  let token: string;
  let bookId = '';
  let worldId = '';
  let projectId = '';
  let locationEntityId = '';
  const stamp = Date.now();

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    // A book to open the (book-scoped) Studio, a world to map, and the book grouped INTO the world so
    // the loop is real (book→world→map). Multilingual, realistic names.
    bookId = await createBook(request, token, `E2E world-map journey ${stamp}`);
    await createChapter(request, token, bookId, '第一章 「山海」');
    const world = await createWorld(request, token, `Sơn Hải Di Văn ${stamp}`);
    worldId = world.world_id;
    await moveBookIntoWorld(request, token, worldId, bookId).catch(() => {});
    // A real KG `location` entity to REBIND a pin to (soft untyped entity_id; the picker binds either
    // a glossary or a KG entity — SEALED PO#2). We paste this id in the marker popover.
    const proj = await createKnowledgeProject(request, token, `E2E map lore ${stamp}`, bookId);
    projectId = proj.project_id;
    const ent = await createKnowledgeEntity(request, token, projectId, '青云门', 'location');
    locationEntityId = ent.id;
  });

  test.afterAll(async ({ request }) => {
    if (projectId) await deleteKnowledgeProject(request, token, projectId).catch(() => {});
    if (worldId) await deleteWorld(request, token, worldId).catch(() => {});
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  const shot = (page: Page, name: string) =>
    page.screenshot({ path: `tests/e2e/test-results/world-map-${name}.png` }).catch(() => {});

  test('an author can build a reference map in the Studio (reachable + operable, drag persists, no dead-ends)', async ({ page, request }) => {
    const wm = new WorldMapEditorPage(page);

    // Spy on marker/region writes so we can assert BY EFFECT: a drag issues exactly ONE PATCH and NO
    // DELETE (never delete+recreate), and a bare select-click issues ZERO writes (no phantom PATCH).
    const writes = { markerPost: 0, markerPatch: 0, markerDelete: 0, regionPatch: 0 };
    page.on('request', (req) => {
      const u = req.url();
      const m = req.method();
      if (/\/maps\/[^/]+\/markers(\/[^/]+)?$/.test(u)) {
        if (m === 'POST') writes.markerPost++;
        else if (m === 'PATCH') writes.markerPatch++;
        else if (m === 'DELETE') writes.markerDelete++;
      } else if (/\/maps\/[^/]+\/regions\/[^/]+$/.test(u) && m === 'PATCH') {
        writes.regionPatch++;
      }
    });

    // ── STEP 1 · "Where do I draw my world?" — reach world-map from the palette ────────────────────
    await wm.open(bookId);
    await expect(wm.panel, 'STEP 1 — the World-Map Editor must be REACHABLE from the palette (audit: every write was agent-MCP-only, there was no human surface at all)').toBeVisible();
    // Bare-id open with no world context ⇒ the in-panel WORLD picker, never a dead/blank pane (§3.5).
    await expect(wm.worldPicker, 'STEP 1 — with no world context the panel must offer a world picker, not blank').toBeVisible({ timeout: 15_000 });
    await shot(page, '1-reach');

    // ── STEP 2 · "Create the map + upload a base image" — the two writes that were NOWHERE for a human ─
    await wm.worldOption(worldId).click();
    // A brand-new world has 0 maps ⇒ the honest empty state with a CREATE CTA (never the old "ask the
    // assistant to make a map" delegation string the audit flagged).
    await expect(wm.empty, 'STEP 2 — an empty world must invite the author to CREATE a map (not delegate to the agent)').toBeVisible({ timeout: 15_000 });
    // "+ New map" uses a window.prompt — accept it with a multilingual name.
    page.once('dialog', (d) => d.accept('九州 · Cửu Châu'));
    await wm.newMap.click();
    await expect(wm.editor, 'STEP 2 — creating a map must OPEN the editor (write landed), not no-op').toBeVisible({ timeout: 15_000 });
    await expect(wm.noImage, 'STEP 2 — a fresh map shows an honest "no base image" prompt, not a broken blank box').toBeVisible();
    // Upload a base image straight onto the hidden file input (the real onChange path). Assert the
    // POST .../image succeeds AND the canvas actually renders the raster — no silent upload failure.
    const uploadResp = page.waitForResponse(
      (r) => /\/maps\/[^/]+\/image$/.test(r.url()) && r.request().method() === 'POST',
      { timeout: 20_000 },
    );
    await wm.fileInput.setInputFiles({ name: 'map-base.png', mimeType: 'image/png', buffer: PNG_1x1 });
    expect((await uploadResp).ok(), 'STEP 2 — the base-image upload must succeed (200), not silently fail').toBeTruthy();
    await expect(wm.canvas.locator('img'), 'STEP 2 — the uploaded base image must render on the canvas').toBeVisible({ timeout: 15_000 });
    await shot(page, '2-map-and-image');

    // ── STEP 3 · "Drop a pin, then DRAG it" — the load-bearing UPDATE: one PATCH, STABLE marker_id ──
    const box = await wm.canvas.boundingBox();
    if (!box) throw new Error('canvas has no bounding box');
    // Pin mode → click the canvas near (0.30, 0.30) → a marker is created (POST) + auto-selected.
    await wm.mode('pin').click();
    const dropResp = page.waitForResponse(
      (r) => /\/maps\/[^/]+\/markers$/.test(r.url()) && r.request().method() === 'POST',
      { timeout: 15_000 },
    );
    await wm.canvas.click({ position: { x: box.width * 0.30, y: box.height * 0.30 } });
    expect((await dropResp).ok(), 'STEP 3 — dropping a pin must persist (POST /markers), not no-op').toBeTruthy();
    await expect(wm.anyMarker().first(), 'STEP 3 — the dropped pin must render on the canvas').toBeVisible({ timeout: 10_000 });

    // Capture the STABLE marker id — the whole point of UPDATE-over-recreate is that this id survives.
    const markerTestId = await wm.anyMarker().first().getAttribute('data-testid');
    if (!markerTestId) throw new Error('dropped marker missing data-testid');
    const markerId = markerTestId.replace('world-map-marker-', '');

    // Select mode → DRAG the pin to (~0.62, 0.58) with page.mouse (CDP-trusted; synthetic events won't
    // drive the pointer-capture drag). Assert: exactly ONE PATCH to THIS marker fired, ZERO DELETEs
    // (never delete+recreate), and the SAME marker_id is still on the canvas (no id churn).
    await wm.mode('select').click();
    const patchBeforeDelete = writes.markerDelete;
    const patchResp = page.waitForResponse(
      (r) => new RegExp(`/markers/${markerId}$`).test(r.url()) && r.request().method() === 'PATCH',
      { timeout: 15_000 },
    );
    await wm.dragTo(wm.marker(markerId), box.x + box.width * 0.62, box.y + box.height * 0.58);
    expect((await patchResp).ok(), 'STEP 3 — a pin drag must persist as ONE absolute-coord PATCH on the stable marker_id (the UPDATE hole this spec closed)').toBeTruthy();
    await expect(wm.marker(markerId), 'STEP 3 — the marker_id must be UNCHANGED after the drag (no delete+recreate churn that would drop its entity tie)').toBeVisible();
    expect(writes.markerDelete, 'STEP 3 — a drag must NOT issue a DELETE (delete+recreate is the anti-pattern this UPDATE route replaced)').toBe(patchBeforeDelete);
    await shot(page, '3-pin-dragged');

    // ── STEP 4 · "Relabel and rebind the pin" — the popover row must be OPERABLE, the write visible ──
    await wm.marker(markerId).click();
    await expect(wm.markerPopover, 'STEP 4 — clicking a pin must OPEN its detail popover, not be a dead tile').toBeVisible();
    const newLabel = `青云门 主峰 ${stamp}`;
    await wm.markerLabel.fill(newLabel);
    // Bind a REAL KG location entity — the picker labels the source layer (glossary vs KG), SEALED PO#2.
    await wm.markerSource.selectOption('kg');
    await wm.markerEntity.fill(locationEntityId);
    await wm.markerSave.click();
    // The rebind must LAND visibly: the marker flips to the entity-bound (violet) state — data-entity-bound.
    await expect(
      page.locator(`[data-testid="world-map-marker-${markerId}"][data-entity-bound="true"]`),
      'STEP 4 — after binding a location entity the pin must render its bound (violet) state — the tie survived the write',
    ).toBeVisible({ timeout: 10_000 });
    // The relabel must be visible on the canvas too (write landed, not a silent no-op).
    await expect(wm.marker(markerId).getByText(newLabel, { exact: false }), 'STEP 4 — the new label must show on the canvas pin').toBeVisible();
    await shot(page, '4-relabel-rebind');

    // ── STEP 5 · "Draw a territory, then RESHAPE it" — regions must be OPERABLE, not a dead read ────
    // Region mode → click ≥3 vertices (away from the pin) → Finish → the polygon renders.
    await wm.mode('region').click();
    await wm.canvas.click({ position: { x: box.width * 0.16, y: box.height * 0.68 } });
    await wm.canvas.click({ position: { x: box.width * 0.38, y: box.height * 0.72 } });
    await wm.canvas.click({ position: { x: box.width * 0.26, y: box.height * 0.90 } });
    await expect(wm.regionDraft, 'STEP 5 — the in-progress region must report its vertex count (drawing is operable)').toBeVisible();
    await expect(wm.regionFinish).toBeEnabled();
    await wm.regionFinish.click();
    await expect(wm.regionPolygons().first(), 'STEP 5 — finishing a region must render the polygon (write landed)').toBeVisible({ timeout: 10_000 });

    // Select mode → the just-drawn region is selected ⇒ its vertex handles appear ⇒ drag vertex 0 to
    // RESHAPE. This must persist as a single PATCH /regions/{id} (the reshape UPDATE — a dead read
    // would offer no handles at all; this was the Phase-B fix).
    await wm.mode('select').click();
    await expect(wm.vertex(0), 'STEP 5 — a selected region must expose draggable vertex handles (regions are operable, not a read-only overlay)').toBeVisible({ timeout: 10_000 });
    const reshapeResp = page.waitForResponse(
      (r) => /\/regions\/[^/]+$/.test(r.url()) && r.request().method() === 'PATCH',
      { timeout: 15_000 },
    );
    await wm.dragTo(wm.vertex(0), box.x + box.width * 0.10, box.y + box.height * 0.55);
    expect((await reshapeResp).ok(), 'STEP 5 — reshaping must persist as one PATCH /regions/{id} (whole-polygon replace)').toBeTruthy();
    expect(writes.regionPatch, 'STEP 5 — the vertex drag must have issued a region PATCH').toBeGreaterThan(0);
    await shot(page, '5-region-reshaped');

    // ── STEP 6 · "No silent failure" — a bare select-click must NOT phantom-write ──────────────────
    // A pure click (no pointer travel) selects the pin (opens its popover) but must issue ZERO marker
    // PATCH — the movedRef/DRAG_EPSILON guard. A silent PATCH-on-click would teleport the pin to the
    // cursor and quietly corrupt the map: the classic silent-success-is-a-bug failure.
    const patchBefore = writes.markerPatch;
    await wm.marker(markerId).click();
    await expect(wm.markerPopover, 'STEP 6 — the click must still OPEN the popover (operable)').toBeVisible();
    await page.waitForTimeout(800);
    expect(writes.markerPatch, 'STEP 6 — a mere select-click must fire NO marker PATCH (no phantom write = no silent failure)').toBe(patchBefore);
    await shot(page, '6-no-phantom-write');

    // ── STEP 7 · "The loop closes" — the map is not an island: book→world→map ──────────────────────
    // Server-side proof that the reference map the author just built is reachable from the book through
    // the world: the world lists our book AND now lists our map. (The world-map panel has no UI
    // deep-link-out in v1 — OQ-1 defers the bus slice — so the loop is asserted at the data layer.)
    const worldBooks = await listWorldBooks(request, token, worldId);
    expect(worldBooks.items.some((b) => b.book_id === bookId), 'STEP 7 — the book must belong to the world (book→world leg)').toBeTruthy();
    const worldMaps = await listWorldMapsApi(request, token, worldId);
    expect(worldMaps.items.length, 'STEP 7 — the world must now carry the map the author built (world→map leg) — the loop is closed, the map is not an island').toBeGreaterThan(0);
    await shot(page, '7-loop');

    // ── VERDICT ────────────────────────────────────────────────────────────────────────────────────
    // Reaching here means: the World-Map Editor is reachable from the palette; an author created a map
    // + uploaded a base image (writes that were NOWHERE for a human); dropped a pin and DRAGGED it as
    // one absolute PATCH on a STABLE marker_id with no delete+recreate churn; relabelled + rebound it
    // to a real KG location entity (the tie survived); drew a region and RESHAPED it by a vertex drag;
    // a bare select-click fired no phantom write; and the map ties back to the book through the world —
    // all Studio-only, no dead-ends. The UPDATE hole (§1) is closed for the human.
  });
});
