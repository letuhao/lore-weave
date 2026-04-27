import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LoginPage } from '../pages/LoginPage';
import { BooksPage } from '../pages/BooksPage';
import { ChaptersTab } from '../pages/ChaptersTab';
import { WikiTab } from '../pages/WikiTab';
import { TEST_USER } from '../helpers/auth';
import { getAccessToken } from '../helpers/api';
import { ensureLmStudioProvider, ensureLmStudioUserModel } from '../helpers/provider';
import {
  buildAutoExtractionProfile,
  createExtractionJob,
  pollUntilComplete,
} from '../helpers/extraction';
import { activateAllDraftEntities } from '../helpers/glossary';
import { extractBookIdFromUrl, extractChapterIdFromEditorUrl } from '../helpers/url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DRACULA_CH01 = readFileSync(
  resolve(__dirname, '../fixtures/dracula-ch01.txt'),
  'utf-8',
);

test.describe('Demo pipeline 3c — wiki article auto-generation from glossary', () => {
  // Includes Phase 3b extraction (~4 min) + wiki generate (sync, fast)
  test.setTimeout(420_000);

  test('generates wiki articles from extracted Dracula entities', async ({ page, request }) => {
    const bookTitle = `Dracula 3c (E2E ${Date.now()})`;
    const chapterTitle = "Chapter I — Jonathan Harker's Journal";

    page.on('dialog', (dialog) => void dialog.accept());

    // ── Setup via API ───────────────────────────────────────────────────
    const token = await getAccessToken(request);
    const providerId = await ensureLmStudioProvider(request, token);
    const modelRef = await ensureLmStudioUserModel(request, token, providerId);

    // ── UI: login + create book + create chapter ────────────────────────
    const login = new LoginPage(page);
    await login.goto();
    await login.login(TEST_USER.email, TEST_USER.password);
    await page.waitForURL('**/books');

    const booksPage = new BooksPage(page);
    await booksPage.createBook({ title: bookTitle, language: 'en' });
    await booksPage.openBook(bookTitle);
    const bookId = extractBookIdFromUrl(page.url());

    const chapters = new ChaptersTab(page);
    await chapters.createChapter({ title: chapterTitle, language: 'en', body: DRACULA_CH01 });
    const chapterId = extractChapterIdFromEditorUrl(page.url());

    // ── API extraction (entities prerequisite for wiki generate) ────────
    const profile = await buildAutoExtractionProfile(request, token, bookId);
    const jobId = await createExtractionJob(request, token, bookId, chapterId, modelRef, profile);
    const finalStatus = await pollUntilComplete(request, token, jobId, { timeoutMs: 300_000 });
    expect(finalStatus.status).toMatch(/^completed/);

    // ── Activate draft entities (wiki generate filters by status='active') ──
    const activated = await activateAllDraftEntities(request, token, bookId);
    expect(activated, 'expected at least 1 entity activated').toBeGreaterThan(0);

    // ── UI: navigate to wiki tab + generate stubs ───────────────────────
    const wiki = new WikiTab(page);
    await wiki.gotoForBook(bookId);

    // Empty state generate button should be visible (no articles yet)
    await expect(wiki.generateEmpty).toBeVisible({ timeout: 10_000 });
    await wiki.generate();

    // After generate, articles populate (sync API). Wait for first row.
    await expect(wiki.allArticles().first()).toBeVisible({ timeout: 15_000 });
    const articleCount = await wiki.allArticles().count();
    expect(articleCount, 'expected at least 1 wiki article generated').toBeGreaterThan(0);

    // Soft assertion: a wiki article for one of the well-known Dracula entities
    const knownEntities = ['Harker', 'Dracula', 'Carpathian', 'Bistritz', 'Jonathan'];
    const found: string[] = [];
    for (const name of knownEntities) {
      const count = await wiki.articleRow(name).count();
      if (count > 0) found.push(name);
    }
    expect(
      found.length,
      `expected wiki article for at least 1 of [${knownEntities.join(', ')}]; got ${articleCount} articles total but none matched`,
    ).toBeGreaterThan(0);
  });
});
