import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LoginPage } from '../pages/LoginPage';
import { BooksPage } from '../pages/BooksPage';
import { ChaptersTab } from '../pages/ChaptersTab';
import { GlossaryTab } from '../pages/GlossaryTab';
import { TEST_USER } from '../helpers/auth';
import { getAccessToken } from '../helpers/api';
import { ensureLmStudioProvider, ensureLmStudioUserModel } from '../helpers/provider';
import {
  buildAutoExtractionProfile,
  createExtractionJob,
  pollUntilComplete,
} from '../helpers/extraction';
import { extractBookIdFromUrl, extractChapterIdFromEditorUrl } from '../helpers/url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DRACULA_CH01 = readFileSync(
  resolve(__dirname, '../fixtures/dracula-ch01.txt'),
  'utf-8',
);

test.describe('Demo pipeline 3b — LM Studio glossary extraction', () => {
  // LLM extraction takes 30-90s for a 5700-word chapter; allow generous timeout
  test.setTimeout(360_000);

  test('extracts canon entities from Dracula Ch.1 via LM Studio Qwen3', async ({ page, request }) => {
    const bookTitle = `Dracula 3b (E2E ${Date.now()})`;
    const chapterTitle = "Chapter I — Jonathan Harker's Journal";

    // Auto-accept any beforeunload prompts (chapter editor unsaved-changes guard)
    page.on('dialog', (dialog) => void dialog.accept());

    // ── Setup via API: provider + user_model (idempotent) ───────────────
    const token = await getAccessToken(request);
    const providerId = await ensureLmStudioProvider(request, token);
    const modelRef = await ensureLmStudioUserModel(request, token, providerId);

    // ── UI: login + create book + create chapter (reuse Phase 3a flow) ──
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

    // ── API-driven extraction (skip wizard UI for determinism) ──────────
    const profile = await buildAutoExtractionProfile(request, token, bookId);
    expect(Object.keys(profile).length, 'expected at least one auto-selected kind').toBeGreaterThan(0);

    const jobId = await createExtractionJob(request, token, bookId, chapterId, modelRef, profile);

    // ── Wait for completion (Qwen3 35B on chapter ~30-90s typical) ──────
    const finalStatus = await pollUntilComplete(request, token, jobId, { timeoutMs: 300_000 });
    expect(finalStatus.status, `extraction did not complete cleanly (status=${finalStatus.status})`).toMatch(
      /^completed/,
    );

    // ── Verify entities surfaced in glossary UI ─────────────────────────
    const glossary = new GlossaryTab(page);
    await glossary.gotoForBook(bookId);

    const allRows = glossary.allEntityRows();
    await expect(allRows.first()).toBeVisible({ timeout: 15_000 });
    const entityCount = await allRows.count();
    expect(entityCount, 'expected at least 1 entity extracted').toBeGreaterThan(0);

    // Soft assertion: at least 1 of the well-known Dracula Ch.1 entities present
    // (LLM nondeterminism — exact set varies; require any one of these)
    const knownEntities = ['Harker', 'Dracula', 'Carpathian', 'Bistritz', 'Jonathan'];
    const found: string[] = [];
    for (const name of knownEntities) {
      const count = await glossary.entityRow(name).count();
      if (count > 0) found.push(name);
    }
    expect(
      found.length,
      `expected at least 1 of [${knownEntities.join(', ')}] extracted; got entities count=${entityCount} but none matched`,
    ).toBeGreaterThan(0);
  });
});
