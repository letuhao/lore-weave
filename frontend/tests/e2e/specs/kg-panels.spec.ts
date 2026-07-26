import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, trashBook, createKnowledgeProject, deleteKnowledgeProject,
  createKnowledgeEntity,
} from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// 14_kg_panels.md — the 13 Knowledge/KG dock panels (hub + 12 capability panels), each opened
// live through the Command Palette (the same path a real user takes). This is the "LIVE gate"
// this codebase's other dockable waves rely on: unit tests prove wiring in isolation, but only
// opening the real panel through the real palette against a real backend catches a catalog/
// registration/data-flow bug a mock can't. Two books are seeded: `bookLinked` has a KG project
// (proves the book-scoped resolution + real-data path), `bookBare` has none (proves the empty
// state). Building a full graph (extraction/embedding) is deliberately out of scope here — slow,
// LLM-cost-bearing, and not needed to prove the panels mount/register/resolve correctly.
test.describe('Knowledge/KG dock panels', () => {
  let token: string;
  let bookLinked: string;
  let bookBare: string;
  let projectId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookLinked = await createBook(request, token, `E2E KG linked ${Date.now()}`);
    bookBare = await createBook(request, token, `E2E KG bare ${Date.now()}`);
    const project = await createKnowledgeProject(request, token, `E2E KG project ${Date.now()}`, bookLinked);
    projectId = project.project_id;
    await createKnowledgeEntity(request, token, projectId, 'Seraphine Vale', 'character');
  });

  test.afterAll(async ({ request }) => {
    if (projectId) await deleteKnowledgeProject(request, token, projectId).catch(() => { /* best effort */ });
    if (bookLinked) await trashBook(request, token, bookLinked).catch(() => { /* best effort */ });
    if (bookBare) await trashBook(request, token, bookBare).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  // Every panel opens via the palette and mounts its content — the core catalog/register/
  // dockview-component wiring, proven live for all 13 in one pass.
  const PANELS: { id: string; search: string; testid: string }[] = [
    { id: 'knowledge', search: 'Knowledge', testid: 'studio-knowledge-hub-panel' },
    { id: 'kg-overview', search: 'Overview', testid: 'studio-kg-overview-panel' },
    { id: 'kg-entities', search: 'Entities', testid: 'studio-kg-entities-panel' },
    { id: 'kg-timeline', search: 'Timeline', testid: 'studio-kg-timeline-panel' },
    { id: 'kg-evidence', search: 'Evidence', testid: 'studio-kg-evidence-panel' },
    { id: 'kg-gap', search: 'Gap Report', testid: 'studio-kg-gap-panel' },
    { id: 'kg-proposals', search: 'Proposals', testid: 'studio-kg-proposals-panel' },
    { id: 'kg-schema', search: 'Schema', testid: 'studio-kg-schema-panel' },
    { id: 'kg-graph', search: 'Knowledge Graph', testid: 'studio-kg-graph-panel' },
    { id: 'kg-insights', search: 'Mining Insights', testid: 'studio-kg-insights-panel' },
    { id: 'kg-jobs', search: 'Extraction Jobs', testid: 'studio-kg-jobs-panel' },
    { id: 'kg-bio', search: 'Global Bio', testid: 'studio-kg-bio-panel' },
    { id: 'kg-privacy', search: 'Privacy', testid: 'studio-kg-privacy-panel' },
  ];

  for (const p of PANELS) {
    test(`${p.id} opens via the Command Palette and mounts`, async ({ page }) => {
      const studio = new StudioPage(page);
      await studio.goto(bookLinked);
      await studio.openPanel(p.id, p.search);
      await expect(page.getByTestId(p.testid)).toBeVisible();
    });
  }

  test('kg-overview resolves the linked project and shows its real data', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookLinked);
    await studio.openPanel('kg-overview', 'Overview');
    await expect(page.getByTestId('shell-overview')).toBeVisible();
    await expect(page.getByTestId('shell-overview-missing')).toHaveCount(0);
  });

  test('kg-overview shows the empty state for a book with no linked KG project', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookBare);
    await studio.openPanel('kg-overview', 'Overview');
    // KgOverviewPanel's OWN no-project empty state (rendered before OverviewSection ever
    // mounts) — distinct from OverviewSection's internal `shell-overview-missing`, which
    // only fires when a project prop resolves to null through a DIFFERENT caller path.
    await expect(page.getByTestId('kg-overview-no-project')).toBeVisible();
    await expect(page.getByTestId('studio-kg-overview-panel')).toHaveCount(0);
  });

  test('kg-entities (global, no scopedProjectId) finds an entity created via the API', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookLinked);
    await studio.openPanel('kg-entities', 'Entities');
    await expect(page.getByTestId('studio-kg-entities-panel')).toBeVisible();
    // The shared dev DB carries hundreds of entities across every project (this is a real,
    // populated environment, not a clean fixture) — search narrows to just the one this
    // test created, rather than assuming it lands on page 1 of the unfiltered global list.
    await page.getByTestId('entities-filter-search').fill('Seraphine');
    // Both a desktop `entities-row` and a `entities-row-mobile` render simultaneously (CSS
    // hides one per breakpoint) — scope to the desktop row so the text match stays strict.
    await expect(page.getByTestId('entities-row').getByText('Seraphine Vale')).toBeVisible();
  });

  // DOCK-7 proof: OverviewSection's book backlink used to be a hard-coded <Link>; it's now a
  // callback wired through the studio link resolver (F3). `/books/:id` isn't in studioLinks.ts's
  // PATH_PANELS (no "book detail" dock panel exists), so it resolves "external" — a new tab,
  // never a route hop that would unmount the studio.
  test("kg-overview's book backlink opens the classic book page in a NEW TAB, studio stays mounted", async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookLinked);
    await studio.openPanel('kg-overview', 'Overview');
    const [popup] = await Promise.all([
      page.waitForEvent('popup'),
      page.getByTestId('overview-book-link').click(),
    ]);
    await popup.waitForLoadState();
    expect(popup.url()).toContain(`/books/${bookLinked}`);
    await popup.close();
    // the studio in the original tab never navigated away
    await expect(page).toHaveURL(new RegExp(`/books/${bookLinked}/studio$`));
    await expect(studio.dockview).toBeVisible();
  });
});
