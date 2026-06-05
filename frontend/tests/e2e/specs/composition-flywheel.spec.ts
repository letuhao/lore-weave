import { test, expect } from '@playwright/test';
import {
  getAccessToken, createBook, trashBook, seedRichChapter, publishChapterApi,
  createCompositionWork, listChatModels, findEmbeddingModelId, startKnowledgeExtraction,
} from '../helpers/api';
import { queryDb, dbAvailable, seedEmbeddingBenchmark } from '../helpers/db';

// V0 scenario test U8 — the flywheel MECHANISM, asserted deterministically at the
// DB layer (grounding-availability itself is a packer/spoiler-window concern with
// its own 31 unit tests; the flywheel is the extraction + auto-drain pipeline).
// MODEL-GATED + SLOW (real LLM extraction, ~3-5 min). Proves: (a) a manual
// knowledge-extraction bootstrap runs to completion (registers the project's
// model), and (b) publishing a NEW chapter then AUTO-DRAINS with no manual step —
// the composition→canon flywheel a never-extracted project can't do (see
// D-COMP-CANON-BOOTSTRAP-HINT). Skipped when LM Studio / the DB are absent.
test.describe('Composition flywheel mechanism (U8) [model-gated · slow]', () => {
  test('bootstrap extraction completes, then a later publish auto-drains', async ({ request }) => {
    test.setTimeout(420_000);
    test.skip(!dbAvailable(), 'needs the dev Postgres container');
    const token = await getAccessToken(request);
    const chatModels = await listChatModels(request, token);
    const embeddingId = await findEmbeddingModelId(request, token);
    test.skip(chatModels.length < 1 || !embeddingId, 'needs a chat drafter + an embedding model + LM Studio');
    const llmId = (chatModels.find((m) => /qwen3\.6-35b/.test(m.provider_model_name)) ?? chatModels[0]).user_model_id;

    const bookId = await createBook(request, token, `E2E flywheel ${Date.now()}`);
    const ch1 = await seedRichChapter(request, token, bookId, 'Chapter One',
      'Alice is a knight of the Northern Kingdom. She serves Queen Mara and carries the Sword of Dawn. ' +
      'She met Bob, a merchant from the southern city of Veil.');
    const ch2 = await seedRichChapter(request, token, bookId, 'Chapter Two',
      'In the city of Veil, Bob opened his shop at dawn and counted the coins from the harvest fair.');
    const projectId = await createCompositionWork(request, token, bookId);

    try {
      // (a) publish ch1 + bootstrap a manual extraction. Seed a passing embedding
      // benchmark first (an orthogonal quality gate — see the helper).
      await publishChapterApi(request, token, bookId, ch1);
      seedEmbeddingBenchmark(projectId, embeddingId!);
      await startKnowledgeExtraction(request, token, projectId, llmId, embeddingId!);

      // bootstrap runs to completion → the project now has a registered model
      const completed = await poll(() =>
        queryDb('loreweave_knowledge',
          `SELECT status FROM extraction_jobs WHERE project_id='${projectId}' AND scope='all' ORDER BY created_at DESC LIMIT 1`,
        ).trim() === 'complete', 300_000);
      expect(completed, 'the bootstrap extraction should complete').toBe(true);

      // (b) publish ch2 — with a prior job registered, the auto-drain must process
      // its pending row WITHOUT any manual extraction (the flywheel).
      await publishChapterApi(request, token, bookId, ch2);
      const drained = await poll(() =>
        queryDb('loreweave_knowledge',
          `SELECT processed_at IS NOT NULL FROM extraction_pending WHERE aggregate_id='${ch2}' AND aggregate_type='chapter' ORDER BY created_at DESC LIMIT 1`,
        ).trim() === 't', 180_000);
      expect(drained, 'ch2 publish should auto-drain once a model is registered').toBe(true);
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});

/** Poll a synchronous predicate until true or timeout (for DB-status checks). */
async function poll(fn: () => boolean, timeoutMs: number, intervalMs = 8000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { if (fn()) return true; } catch { /* transient */ }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}
