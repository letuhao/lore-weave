// S7 · BLACKBOX real-user journey. Persona: an author who builds their knowledge
// graph BY HAND. The S7-A1/A2 audit found the KG was VIEW-RICH, AUTHOR-POOR — 13
// view panels + edit + merge, but every path to a NEW entity was agent-only
// (run extraction, or approve an agent proposal). A human could not hand-author a
// character, a relation, or retire a node. S7-1 drew the Create/Relation/Archive
// controls; this journey proves a signed-in human can now drive the whole loop
// end to end in the Studio, with NO test-only shortcut for the actions under test.
//
// Usability rubric (ASSERTED, not just observed): the surface is reachable from
// the palette · every write LANDS and is visible · a list row OPENS its detail
// (not a dead tile) · the kind is a CLOSED-SET enum, never free text · a relation
// edge lands · archive is NOT a one-way trap (Undo → restore round-trips) · the
// graph deep-links back to a detail (no island). Each STEP names the user intent
// and what the audit found ("was agent-only").
import { test, expect, type Page } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken,
  createBook,
  trashBook,
  createKnowledgeProject,
  deleteKnowledgeProject,
  createKnowledgeEntity,
} from '../helpers/api';
import { KgAuthoringPage } from '../pages/KgAuthoringPage';

test.describe('@s7 Studio · KG entity authoring journey (blackbox)', () => {
  let token: string;
  let bookId: string;
  let projectId: string;
  let objectEntityId = '';
  const stamp = Date.now();

  // The star of the journey — hand-authored via the UI in STEP 2.
  const HERO = '李慕白';
  const HERO_ALIAS = '青莲剑仙';
  // The relation target — seeded via the real API so the typeahead has something
  // to find. Name is ASCII-anchored (`Han Li`) so the server FTS typeahead search
  // ("Han") matches reliably, with the CJK form kept for realism.
  const OBJECT_NAME = 'Han Li 韓立';

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E KG-authoring ${stamp}`);
    // A knowledge project LINKED to the book — kg-graph resolves the book's
    // project (useBookKnowledgeProject); kg-entities scopes the create + list.
    const project = await createKnowledgeProject(
      request,
      token,
      `E2E KG-authoring project ${stamp}`,
      bookId,
    );
    projectId = project.project_id;
    // The pre-existing neighbour the author will LINK the hero to.
    const obj = await createKnowledgeEntity(request, token, projectId, OBJECT_NAME, 'character');
    objectEntityId = obj.id;
  });

  test.afterAll(async ({ request }) => {
    if (projectId) await deleteKnowledgeProject(request, token, projectId).catch(() => {});
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  const shot = (page: Page, name: string) =>
    page.screenshot({ path: `tests/e2e/test-results/kg-journey-${name}.png` }).catch(() => {});

  test('an author can build their knowledge graph BY HAND in the Studio (reachable + operable, no dead-ends)', async ({ page }) => {
    const kg = new KgAuthoringPage(page);

    // The Archive confirm is a native window.confirm — auto-accept it so the
    // archive action proceeds (the honest destructive-ish prompt is real; a human
    // clicks OK).
    page.on('dialog', (d) => d.accept().catch(() => {}));

    // ── STEP 1 · REACHABLE — "Where do I add a character?" reach kg-entities ─────
    await kg.openEntities(bookId);
    await expect(
      kg.panel,
      'STEP 1 (reachable) — the KG entities surface must be REACHABLE from the palette (audit: authoring was agent-only)',
    ).toBeVisible();
    // Scope to this book's project — the unscoped palette panel shows the project
    // picker, and a hand-authored node needs a project tag.
    await kg.selectProject(projectId);
    await shot(page, '1-entities-open');

    // ── STEP 2 · CRUD (create) — author a character; the kind is a CLOSED-SET ────
    // enum, and the write must actually LAND as a visible row (no silent no-op).
    await expect(
      kg.newButton,
      'STEP 2 — "+ New Entity" must be enabled once a project is chosen (the human Create the audit was missing)',
    ).toBeEnabled();
    await kg.newButton.click();
    await expect(
      kg.createKindGrid,
      'STEP 2 — kind must be a CLOSED-SET radio-grid, never a free <input> (the kind:"charcter" typo bug)',
    ).toBeVisible();
    await kg.createName.fill(HERO);
    await page.getByTestId('entity-create-kind-character').click();
    await kg.createConfirm.click();
    await expect(
      kg.row(HERO),
      'STEP 2 (write landed) — the hand-authored character must appear as a real list row',
    ).toBeVisible({ timeout: 10_000 });
    await shot(page, '2-created');

    // ── STEP 3 · OPERABLE — a row must OPEN its detail, not be a dead tile ───────
    await kg.openDetail(HERO);
    await expect(
      kg.detail,
      'STEP 3 (operable) — a list row must OPEN the detail slide-over, not be a dead tile',
    ).toBeVisible();
    await shot(page, '3-detail');

    // ── STEP 4 · CRUD (edit) — rename/alias, with kind an ENUM not free text ─────
    await kg.detailEdit.click();
    await expect(kg.editKind, 'STEP 4 — the edit dialog must open').toBeVisible();
    // The kind control is now a <select> enum (the free-<input> that silently
    // wrote kind:"charcter" is GONE) — prove it is a SELECT element.
    await expect(
      kg.editKind,
      'STEP 4 — kind must be an ENUM <select>, never free text',
    ).toHaveJSProperty('tagName', 'SELECT');
    // Add an alias (a real edit); the write must be visible afterward.
    await kg.editAliases.fill(`${HERO}\n${HERO_ALIAS}`);
    await kg.editConfirm.click();
    await expect(
      kg.detailAliases,
      'STEP 4 (write landed) — the added alias must show on the refreshed detail (no manual reload)',
    ).toContainText(HERO_ALIAS, { timeout: 10_000 });
    await shot(page, '4-edited');

    // ── STEP 5 · CRUD (relation) — link the hero to a second entity via Link2 ────
    // the edge must LAND and render in the detail's relation list.
    await kg.createRelation('ally_of', 'Han', objectEntityId);
    await expect(
      kg.detailOutgoing,
      'STEP 5 (write landed) — the new relation must render in the detail (edge created, was agent-propose-only)',
    ).toBeVisible({ timeout: 10_000 });
    await expect(kg.detailOutgoing).toContainText('ally_of');
    await shot(page, '5-relation');

    // ── STEP 6 · NO ONE-WAY TRAP — Archive → Undo toast → restore round-trip ─────
    await kg.detailArchive.click();
    // Archive closes the detail; the success toast offers Undo (restore).
    await expect(
      kg.detail,
      'STEP 6 — archiving retires the entity and closes its detail',
    ).toHaveCount(0, { timeout: 10_000 });
    await expect(
      kg.row(HERO),
      'STEP 6 — the archived entity leaves the active list',
    ).toHaveCount(0, { timeout: 10_000 });
    await expect(
      kg.toastUndo(),
      'STEP 6 (no silent failure) — archive must surface an Undo (restore), not be a one-way trap',
    ).toBeVisible();
    await kg.toastUndo().click();
    await expect(
      kg.row(HERO),
      'STEP 6 (restore round-trip) — Undo must RESTORE the entity to the active list',
    ).toBeVisible({ timeout: 10_000 });
    await shot(page, '6-archive-restore');

    // ── STEP 7 · LOOP-CONNECTED — the graph is not an island: node → detail ──────
    await kg.openGraph();
    await expect(
      kg.graphPanel,
      'STEP 7 — the knowledge graph must be REACHABLE from the palette',
    ).toBeVisible();
    // The freshly-authored entities + the relation give the subgraph real nodes.
    await expect(kg.graphView, 'STEP 7 — the graph must render (real nodes, not a blank canvas)').toBeVisible({ timeout: 15_000 });
    const firstNode = kg.graphNode().first();
    await expect(firstNode, 'STEP 7 — at least one graph node must render').toBeVisible({ timeout: 15_000 });
    await firstNode.click();
    await expect(
      kg.detail,
      'STEP 7 (loop-connected) — a graph node must DEEP-LINK to the entity detail, closing the loop back to authoring',
    ).toBeVisible({ timeout: 10_000 });
    await shot(page, '7-graph-deeplink');

    // ── VERDICT ──────────────────────────────────────────────────────────────
    // Reaching here proves: the KG authoring surface is reachable, a character was
    // hand-created (write landed), its row opened, an edit landed with a closed-set
    // kind enum, a relation edge was built, archive round-trips via Undo (no
    // one-way trap), and the graph deep-links back to detail — all Studio-only,
    // no dead-ends. The audit's "view-rich, author-poor / agent-only" gap is closed.
  });
});
