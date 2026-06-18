import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createCompositionWork, createKnowledgeEntity,
} from '../helpers/api';

// Creation-unblock RAID (D-079) — a DISCOVERED (unanchored) entity in the divergence
// wizard's Step 3 used to only show a "promote it in the Entities tab first" hint,
// forcing the user out of the wizard. D-079 added an inline "Anchor & override"
// button. This scenario seeds a discovered entity, opens the wizard, and proves the
// inline anchor affordance is present (and, when glossary is healthy, that anchoring
// reveals the override input). No LLM — the wizard, listEntities and promote (C9
// glossary draft + anchor) are all model-free.
test.describe('Creation-unblock — divergence inline anchor & override (D-079)', () => {
  test('a discovered entity offers inline "Anchor & override" in the wizard', async ({ page, request }) => {
    test.setTimeout(90_000);
    const token = await getAccessToken(request);
    const ts = Date.now();
    const book = await createBook(request, token, `E2E div ${ts}`);
    const chapter = await createChapter(request, token, book, 'Ch1');
    const projectId = await createCompositionWork(request, token, book);
    const ent = await createKnowledgeEntity(request, token, projectId, `Ghost${ts}`, 'character');
    // sanity: the seeded entity is DISCOVERED (no glossary anchor) — the input to D-079.
    expect(ent.glossary_entity_id, 'seeded entity is unanchored/discovered').toBeFalsy();
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(book, chapter);
      await panel.openComposeTab();

      // launch the divergence wizard from the canon Work, advance to Step 3.
      await page.getByTestId('divergence-launch').click();
      await page.getByTestId('divergence-next').click(); // → 2
      await page.getByTestId('divergence-next').click(); // → 3
      await expect(page.getByTestId('divergence-step-3')).toBeVisible();

      // D-079 — the discovered entity offers the inline anchor button (not just a hint).
      const anchorBtn = page.getByTestId(`divergence-anchor-${ent.id}`);
      await expect(anchorBtn).toBeVisible({ timeout: 15_000 });

      // Anchor it → the C9 promote anchors it → the row flips to an override input.
      await anchorBtn.click();
      await expect(page.locator('[data-testid^="divergence-override-input-"]'))
        .toBeVisible({ timeout: 25_000 });
    } finally {
      await trashBook(request, token, book).catch(() => {});
    }
  });
});
