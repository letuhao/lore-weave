import { test, expect } from '@playwright/test';
import {
  getAccessToken, ensureUserB, createBook, createChapter, trashBook,
  seedChapterWithRevisions, createCompositionWork, createCompositionScene, listRevisionIds,
} from '../helpers/api';

// V0 scenario tests B9.1 / B2.4 / B6.3 / B8.10 — cross-user isolation (A1 / SEC2).
// Asserted at the API boundary (the strongest form): user B must not resolve,
// read, ground, or compare ANY of user A's composition / revision data. User A
// owns the seeded book; user B is a distinct account.
test.describe('Composition cross-user isolation (B9.1/B2.4/B6.3/B8.10)', () => {
  test('user B cannot resolve, list, ground, or compare user A\'s data', async ({ request }) => {
    const tokenA = await getAccessToken(request);
    const tokenB = await ensureUserB(request);
    const authB = { headers: { Authorization: `Bearer ${tokenB}` } };

    // user A seeds: book + chapter (2 revisions) + Work + scene
    const { bookId, chapterId } = await seedChapterWithRevisions(request, tokenA, ['rev one', 'rev two']);
    const projectId = await createCompositionWork(request, tokenA, bookId);
    const sceneId = await createCompositionScene(request, tokenA, projectId, chapterId, 'Scene A');
    const revIds = await listRevisionIds(request, tokenA, bookId, chapterId);
    expect(revIds.length).toBeGreaterThanOrEqual(2);

    try {
      // B2.4 — resolving A's book Work as B must NOT leak A's project. The resolve
      // is JWT-forwarded → for B the book has no project → a "none" result (200)
      // or an access error; either way A's project_id must never appear.
      const resolve = await request.get(`/v1/composition/books/${bookId}/work`, authB);
      if (resolve.ok()) {
        expect(JSON.stringify(await resolve.json())).not.toContain(projectId);
      } else {
        expect([401, 403, 404]).toContain(resolve.status());
      }

      // B9.1 — B cannot read A's outline (scenes are user-scoped; M5 isolation)
      const outline = await request.get(`/v1/composition/works/${projectId}/outline`, authB);
      expect([401, 403, 404]).toContain(outline.status());

      // B6.3 — B cannot ground A's scene (SEC2 owns_book chokepoint → 404)
      const grounding = await request.get(
        `/v1/composition/works/${projectId}/scenes/${sceneId}/grounding`, authB,
      );
      expect([401, 403, 404]).toContain(grounding.status());

      // B8.10 — B cannot compare A's revisions even with valid ids (ownership join)
      const compare = await request.get(
        `/v1/books/${bookId}/chapters/${chapterId}/revisions/compare?left=${revIds[1]}&right=${revIds[0]}`,
        authB,
      );
      expect([401, 403, 404]).toContain(compare.status());
    } finally {
      await trashBook(request, tokenA, bookId);
    }
  });
});
