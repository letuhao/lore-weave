// S5 · Derivative manuscript FORK — the editor isolation proof (D-S5-DERIVATIVE-MANUSCRIPT-FORK).
// The product decision was FORK: a dị bản gets its OWN manuscript per chapter. This drives the real
// editor on a derivative and proves — through the browser + the gateway — that editing the branch
// writes the WORK-scoped draft and leaves CANON byte-unchanged, then merges back.
//
// Run against the isolated S5 build:
//   PLAYWRIGHT_BASE_URL=http://localhost:5399 npx playwright test studio-derivative-fork
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook, saveDraft,
  createCompositionWork, createDerivative,
} from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

const V1 = '/v1';

test.describe('S5 · derivative manuscript fork — branch edits isolated from canon (live)', () => {
  let token = '';
  let bookId = '';
  let chapterId = '';
  let srcProject = '';
  let derivProject = '';
  let seedFailed = false;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `S5 fork e2e ${Date.now()}`);
    chapterId = await createChapter(request, token, bookId, 'Ch1');
    srcProject = await createCompositionWork(request, token, bookId);
    // Seed canon prose so the isolation is visible (canon body must not change under a branch edit).
    await saveDraft(request, token, bookId, chapterId, 'CANON prose seed', 1, 'seed canon');
    try {
      const d = await createDerivative(request, token, srcProject, { name: `Fork ${Date.now()}`, branchPoint: 0 });
      derivProject = d.project_id;
      // Make the dị bản the active Work for this book (server pref — the same key useSetActiveWork
      // writes) so the editor resolves onto it deterministically. The switch UI itself is covered by
      // studio-divergence.spec; this spec is about the editor's fork isolation.
      const pr = await request.patch(`${V1}/me/preferences`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { prefs: { [`lw_active_work.${bookId}`]: derivProject } },
      });
      if (!pr.ok()) throw new Error(`set active-work pref → ${pr.status()}`);
    } catch (e) {
      seedFailed = true;
      // eslint-disable-next-line no-console
      console.warn('[s5-fork] derivative seed failed — skipping:', (e as Error).message);
    }
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test('editing a chapter on a dị bản forks it; canon stays byte-unchanged; then merge promotes it', async ({ page, request }) => {
    test.skip(seedFailed, 'derivative seed unavailable (knowledge partition outage)');
    test.setTimeout(90_000);

    // Capture canon's body BEFORE anything (the isolation baseline).
    const canonBefore = await (await request.get(`${V1}/books/${bookId}/chapters/${chapterId}/draft`, {
      headers: { Authorization: `Bearer ${token}` },
    })).json();
    const canonBodyBefore = JSON.stringify(canonBefore.body);

    // 1 · The dị bản is already the active Work (set via the server pref in beforeAll). Open the
    //     chapter in the editor via deep-link (the navigator shows the outline once a Work exists).
    await loginViaUI(page);
    const studio = new StudioPage(page);
    await page.goto(`/books/${bookId}/studio?chapter=${chapterId}`);
    await studio.activity('manuscript').waitFor({ state: 'attached' });
    await studio.openPanel('editor', 'Editor');
    // Wait for the LOADED editor (the Save affordance exists only past the chapter-loaded gate — the
    // empty-state view shares the panel testid but has no Save button).
    await expect(page.getByTestId('studio-editor-save')).toBeVisible({ timeout: 20_000 });

    // 2 · Before editing: the banner says this chapter still MIRRORS canon (inherited, not forked).
    await expect(page.getByTestId('studio-editor-derivative-guard')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('studio-editor-fork-state')).toContainText(/mirrors canon|FORKS it/i);

    // 4 · Type into the manuscript editor + save (⌘S / the Save affordance).
    const content = page.locator('.tiptap-content').first();
    await content.click();
    await page.keyboard.type(' BRANCH divergent line');
    await page.getByTestId('studio-editor-save').click();
    // let the save round-trip land
    await expect(page.getByTestId('studio-editor-fork-state')).toContainText(/FORKED|isolated/i, { timeout: 15_000 });

    // 5 · THE ISOLATION PROOF (via the gateway): the WORK draft holds the branch edit, and CANON is
    //     byte-unchanged.
    const wd = await (await request.get(`${V1}/composition/works/${derivProject}/chapters/${chapterId}/work-draft`, {
      headers: { Authorization: `Bearer ${token}` },
    })).json();
    expect(wd.forked).toBe(true);
    expect(JSON.stringify(wd.body)).toContain('BRANCH divergent line');

    const canonAfter = await (await request.get(`${V1}/books/${bookId}/chapters/${chapterId}/draft`, {
      headers: { Authorization: `Bearer ${token}` },
    })).json();
    expect(JSON.stringify(canonAfter.body)).toBe(canonBodyBefore);   // canon untouched by the branch edit
    expect(JSON.stringify(canonAfter.body)).not.toContain('BRANCH divergent line');

    // 6 · Merge the fork into canon (two-step confirm) → canon now holds the branch prose.
    const mergeBtn = page.getByTestId('studio-editor-merge-canon');
    await expect(mergeBtn).toBeVisible();
    await mergeBtn.click();                                  // arm the confirm
    await expect(mergeBtn).toContainText(/confirm/i);
    await mergeBtn.click();                                  // confirm the merge
    await expect(async () => {
      const merged = await (await request.get(`${V1}/books/${bookId}/chapters/${chapterId}/draft`, {
        headers: { Authorization: `Bearer ${token}` },
      })).json();
      expect(JSON.stringify(merged.body)).toContain('BRANCH divergent line');
    }).toPass({ timeout: 15_000 });
  });
});
