import { test, expect } from '@playwright/test';
import {
  getAccessToken, createBook, trashBook, seedRichChapter, publishChapterApi, createCompositionWork,
} from '../helpers/api';
import { dbAvailable, seedPriorExtractionJob, countChaptersPendingJobs } from '../helpers/db';

// V0 scenario test U8 — the flywheel TRIGGER, asserted deterministically + fast at
// the DB layer (no LLM — the real extraction is slow + load-sensitive, and what we
// actually want to lock is the auto-drain DECISION, not the model output). Proves
// the exact composition→canon fix: worker-ai's _ensure_chapters_pending_jobs SKIPS
// a project with no prior extraction job (the gap — pendings pile up, no canon),
// but ENGAGES once the project has an extraction history (the flywheel). Exercises
// the real cross-service pipeline: book publish → knowledge arms extraction_pending
// → worker-ai poll decision. DB-gated only (no models needed).
test.describe('Composition flywheel trigger (U8) [db-assert]', () => {
  test('publish auto-drains only after the project has an extraction history', async ({ request }) => {
    test.setTimeout(120_000);
    test.skip(!dbAvailable(), 'needs the dev Postgres container');
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E flywheel ${Date.now()}`);
    const ch1 = await seedRichChapter(request, token, bookId, 'Chapter One',
      'Alice is a knight of the Northern Kingdom who serves Queen Mara.');
    const projectId = await createCompositionWork(request, token, bookId);

    try {
      // GAP — publish on a never-extracted project: knowledge arms the pending, but
      // worker-ai's auto-drain skips (no prior job → no model to reuse). After
      // several poll cycles there is still NO chapters_pending drain job.
      await publishChapterApi(request, token, bookId, ch1);
      await new Promise((r) => setTimeout(r, 22_000)); // ≥4 worker poll cycles (5s)
      expect(countChaptersPendingJobs(projectId),
        'a never-extracted project must NOT auto-drain (the bootstrap gap)').toBe(0);

      // FIX — give the project an extraction history; the next poll must now create
      // a chapters_pending drain for the still-unprocessed pending (the flywheel).
      seedPriorExtractionJob(projectId);
      const deadline = Date.now() + 60_000;
      let drained = false;
      while (Date.now() < deadline) {
        if (countChaptersPendingJobs(projectId) >= 1) { drained = true; break; }
        await new Promise((r) => setTimeout(r, 4000));
      }
      expect(drained, 'once a prior job exists, publish must auto-drain (flywheel)').toBe(true);
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
