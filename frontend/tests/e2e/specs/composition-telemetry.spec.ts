import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createCompositionWork, createCompositionScene, createOutlineNode, setSceneStatus,
} from '../helpers/api';
import { queryComposition, dbAvailable } from '../helpers/db';

// V0 scenario test B3.3 — scene_committed telemetry. DB-backed: the outbox row has
// no read API, so we assert it directly in loreweave_composition.outbox_events via
// the dev Postgres container. Login keeps the auth context consistent with the
// other specs; the assertions are API-driven + DB-verified.
test.describe('Composition telemetry (B3.3) [db-assert]', () => {
  test('scene_committed is emitted once on mark-done, never on re-mark or for a non-scene node', async ({ page, request }) => {
    test.skip(!dbAvailable(), 'needs the dev Postgres container (infra-postgres-1)');
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E telemetry ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Telemetry chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    const sceneId = await createCompositionScene(request, token, projectId, chapterId, 'Scene');
    const beatId = await createOutlineNode(request, token, projectId, 'beat', 'Beat');
    try {
      await loginViaUI(page);
      const sceneRows = () => Number(queryComposition(
        `SELECT count(*) FROM outbox_events WHERE event_type='composition.scene_committed' AND payload->>'scene_id'='${sceneId}'`,
      ));

      // before any commit → no telemetry
      expect(sceneRows()).toBe(0);

      // mark the scene done → exactly ONE scene_committed row
      await setSceneStatus(request, token, sceneId, 'done');
      expect(sceneRows()).toBe(1);

      // re-mark an already-done scene (no real transition) → NO new row
      await setSceneStatus(request, token, sceneId, 'done');
      expect(sceneRows()).toBe(1);

      // a non-scene node marked done → no scene_committed for it (kind gate).
      // The patch may be a no-op or rejected; either way it must emit nothing.
      try { await setSceneStatus(request, token, beatId, 'done'); } catch { /* non-scene reject is fine */ }
      const beatRows = Number(queryComposition(
        `SELECT count(*) FROM outbox_events WHERE event_type='composition.scene_committed' AND payload->>'scene_id'='${beatId}'`,
      ));
      expect(beatRows).toBe(0);
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
