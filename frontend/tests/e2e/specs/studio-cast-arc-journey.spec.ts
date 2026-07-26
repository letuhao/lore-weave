// S7 · B — BLACKBOX real-user journey. Persona: a web-novel author reviewing their
// cast and one character's arc. The S7-4 audit called these panels "view-rich,
// author-poor": the Cast Codex was read/navigate-only and the Character Arc a pure
// view with 0 buttons — and BOTH were legacy-stranded on the retiring
// `ChapterEditorPage` sub-tab, never reachable as Studio dock panels. This journey
// drives the REAL app end to end and at EVERY step asserts the author could actually
// COMPLETE it — a row OPENS (not a dead tile), the arc deep-links to THAT character,
// clicking a different row RE-SUBJECTS the open arc (the tier-2 bus live-update), a
// rename LANDS under OCC, and "+ Add event" puts an event on the timeline. A step
// that renders a skeleton but does nothing = a FAIL here (the What-If lesson).
//
// Usability rubric (asserted, not observed): every read has a reachable write · every
// list row opens something · the deep-link resolves to the right subject · no step
// dead-ends · Studio-only (never the legacy editor sub-tab).
import { test, expect, type Page } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createKnowledgeProject, createKnowledgeEntity, deleteKnowledgeProject,
} from '../helpers/api';
import { CastArcPage } from '../pages/CastArcPage';

test.describe('@s7 Studio · cast + character-arc author journey (blackbox)', () => {
  let token: string;
  let bookId: string;
  let projectId = '';
  const stamp = Date.now();

  // Multilingual cast, seeded via the REAL create route (S7 built it) so the codex
  // has rows grouped by kind. Two characters give the deep-link (open one) AND the
  // re-subject (click a different one); a location proves the grouping is real.
  let liId = '';       // 李慕白 — the character we open, rename, and add an event to
  let hanId = '';      // 韩立 / Hàn Lập — the DIFFERENT character the arc re-subjects to
  let sectId = '';     // 青云门 — a location, so the codex shows ≥2 kind groups

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E cast-arc journey ${stamp}`);
    // a chapter = a reading position the panels can window story-state against.
    await createChapter(request, token, bookId, 'Chapter 12 「青云初上」');
    // the cast reads the book's KG entities — a book needs a knowledge project first.
    const proj = await createKnowledgeProject(request, token, `cast-arc ${stamp}`, bookId);
    projectId = proj.project_id;
    liId = (await createKnowledgeEntity(request, token, projectId, `李慕白 ${stamp}`, 'character')).id;
    hanId = (await createKnowledgeEntity(request, token, projectId, `韩立 ${stamp}`, 'character')).id;
    sectId = (await createKnowledgeEntity(request, token, projectId, `青云门 ${stamp}`, 'location')).id;
  });

  test.afterAll(async ({ request }) => {
    if (projectId) await deleteKnowledgeProject(request, token, projectId).catch(() => {});
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  const shot = (page: Page, name: string) =>
    page.screenshot({ path: `tests/e2e/test-results/cast-arc-${name}.png` }).catch(() => {});

  test('an author can review the cast + a character arc in the Studio (reachable, operable, no dead-ends)', async ({ page }) => {
    const cast = new CastArcPage(page);

    // ── STEP 1 · reachable — "Where is my cast?" reach the Cast Codex from the palette ──
    // Audit: the codex was legacy-ChapterEditorPage-only; S7-4 ported it to a dock panel.
    await cast.open(bookId);
    await expect(cast.codex, 'STEP 1 (reachable) — the Cast Codex must open from the palette (was legacy sub-tab only)').toBeVisible();
    await shot(page, '1-codex-open');

    // ── STEP 2 · operable — the seeded cast shows, grouped by kind; a row OPENS ──────────
    // Every list row must open something (the What-If lesson): the toggle expands lazy detail.
    await expect(cast.row(liId), 'STEP 2 (operable) — my seeded character 李慕白 must appear as a real row').toBeVisible();
    await expect(cast.row(hanId), 'STEP 2 (operable) — the second character 韩立 must appear').toBeVisible();
    await expect(cast.row(sectId), 'STEP 2 (operable) — the location 青云门 must appear (a second kind group)').toBeVisible();
    await cast.rowToggle(liId).click();
    await expect(cast.rowDetail(liId), 'STEP 2 (operable) — a row must OPEN its detail, not be a dead tile').toBeVisible();
    await cast.rowToggle(liId).click(); // collapse again to keep the list tidy
    await shot(page, '2-grouped-cast');

    // ── STEP 3 · honest count — no dead-end truncation ──────────────────────────────────
    // We seeded well under the 200 keyset cap, so the codex must NOT show a "Load more"
    // truncation banner — the count is complete and honest (a >200 cast would append a
    // real keyset page instead; either way the list is never a silent dead-end).
    await expect(cast.moreHint, 'STEP 3 (no dead-end) — under the cap there is no truncation banner; the count is honest').toHaveCount(0);
    await expect(cast.loadMore, 'STEP 3 (no dead-end) — no "Load more" dead-end when the whole cast fits').toHaveCount(0);
    expect(await cast.anyRow().count(), 'STEP 3 — all seeded rows are rendered, none swallowed').toBeGreaterThanOrEqual(3);

    // ── STEP 4 · deep-link — click a cast row's arc glyph → character-arc opens on THAT entity ──
    // This is the seam that breaks SILENTLY if ported without a payload (DP-5). Verify by
    // EFFECT: the arc panel mounts AND its picker is on the character we clicked, not roster[0].
    await cast.rowArc(liId).click();
    await expect(cast.arcPanel, 'STEP 4 (deep-link) — the arc glyph must open the character-arc panel').toBeVisible();
    await expect(cast.arcView, 'STEP 4 (deep-link) — the arc view renders (not a blank pane)').toBeVisible();
    await expect(cast.arcSelect, 'STEP 4 (deep-link) — the arc must be SUBJECTED to 李慕白 (the row I clicked), not the roster default').toHaveValue(liId);
    await shot(page, '4-arc-deeplink');

    // ── STEP 5 · re-subject — click a DIFFERENT cast row while the arc is open → it switches ──
    // The tier-2 bus live-update: opening the arc stacked it over the codex, so switch back,
    // click 韩立's arc glyph, and the ALREADY-OPEN arc must re-subject (not stay on 李慕白).
    await cast.focusCast();
    await cast.rowArc(hanId).click();
    await cast.focusArc();
    await expect(cast.arcSelect, 'STEP 5 (re-subject) — clicking a different row must RE-SUBJECT the open arc to 韩立 (bus live-update), not stay stranded on 李慕白').toHaveValue(hanId);
    await shot(page, '5-arc-resubject');

    // ── STEP 6 · CRUD — a light edit lands: inline rename under OCC ──────────────────────
    // The whole point of S7-4: the cast was read-only for humans (agent-authored only).
    // Rename 李慕白 inline; the write must LAND and be visible (no silent no-op).
    await cast.focusCast();
    const renamed = `李慕白·改 ${stamp}`;
    await cast.rowRename(liId).click();
    await expect(cast.rowRenameInput(liId), 'STEP 6 (CRUD) — the rename affordance must exist (audit: the row was agent-only, no human write)').toBeVisible();
    await cast.rowRenameInput(liId).fill(renamed);
    await cast.rowRenameInput(liId).press('Enter');
    await expect(
      cast.castPanel.getByText(renamed, { exact: false }),
      'STEP 6 (no silent failure) — the renamed cast member must show its new name (the OCC write landed + refreshed)',
    ).toBeVisible({ timeout: 10_000 });
    await shot(page, '6-renamed');

    // ── STEP 7 · loop-connected — "+ Add event" on the arc → the event lands on the timeline ──
    // The arc was a pure view with 0 buttons; S7-4 wired event authoring. The arc is on 韩立
    // (from STEP 5) with no events yet, so it shows the empty state; adding one must put a
    // real point on the timeline — closing the read→author loop, not dead-ending on a view.
    await cast.focusArc();
    await expect(cast.arcEmpty, 'STEP 7 (precondition) — 韩立 has no events yet, so the arc shows its honest empty state').toBeVisible();
    await expect(cast.arcAddEvent, 'STEP 7 (operable) — the arc must offer "+ Add event" (was a 0-button view)').toBeVisible();
    await cast.arcAddEvent.click();
    await expect(cast.eventTitle, 'STEP 7 — the event-authoring dialog must open (reused knowledge dialog)').toBeVisible();
    await cast.eventTitle.fill(`韩立 breaks through to Foundation ${stamp}`);
    await cast.eventConfirm.click();
    await expect(
      cast.timelineEvent.first(),
      'STEP 7 (loop-connected) — the authored event must appear on the arc timeline (the write landed + the arc refreshed), not vanish',
    ).toBeVisible({ timeout: 15_000 });
    await shot(page, '7-event-added');

    // ── VERDICT ─────────────────────────────────────────────────────────────────────────
    // Reaching here means: the Cast Codex is reachable + operable (rows open), the arc
    // deep-links to the clicked character AND re-subjects on the bus, a human rename lands
    // under OCC, and "+ Add event" closes the read→author loop — all Studio dock panels,
    // no legacy sub-tab, no dead-ends. The audit's ❌❌❌ (Create/Edit view-only) rows flip.
  });
});
