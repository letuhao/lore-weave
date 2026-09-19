import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LoginPage } from '../pages/LoginPage';
import { BooksPage } from '../pages/BooksPage';
import { BookDetailPage } from '../pages/BookDetailPage';
import { ChaptersTab } from '../pages/ChaptersTab';
import { TEST_USER } from '../helpers/auth';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DRACULA_CH01 = readFileSync(
  resolve(__dirname, '../fixtures/dracula-ch01.txt'),
  'utf-8',
);

test.describe('Demo pipeline 3a — book + chapter foundation', () => {
  test('creates a Dracula book with Chapter 1 and verifies persistence', async ({ page }) => {
    // Unique title per run for isolation (no cleanup; tests accumulate)
    const bookTitle = `Dracula (E2E ${Date.now()})`;
    const chapterTitle = "Chapter I — Jonathan Harker's Journal";

    // 1. Login
    const login = new LoginPage(page);
    await login.goto();
    await login.login(TEST_USER.email, TEST_USER.password);
    await page.waitForURL('**/books');

    // 2. Create book
    const booksPage = new BooksPage(page);
    await booksPage.createBook({
      title: bookTitle,
      language: 'en',
      description: 'Bram Stoker, 1897. E2E demo pipeline test fixture.',
    });

    // 3. Verify book appears in list. Create lands in the Studio, so going back to the
    //    library is part of the journey now -- the CLAIM is unchanged: the book a writer
    //    just made is in their library and can be opened from it.
    await booksPage.goto();
    await expect(booksPage.bookRow(bookTitle)).toBeVisible({ timeout: 5_000 });

    // 4. Open book detail
    await booksPage.openBook(bookTitle);
    const detail = new BookDetailPage(page);
    await detail.expectTitle(bookTitle);

    // 5. Add chapter with full Dracula Ch.1 body
    const chapters = new ChaptersTab(page);
    await chapters.createChapter({
      title: chapterTitle,
      language: 'en',
      body: DRACULA_CH01,
    });

    // After create we land on an editor for the chapter just made. That is now the Studio
    // with the chapter selected (#18), so the route shape changed; the claim did not, and
    // this asserts MORE than before -- the URL must carry a chapter id, not merely end in
    // /edit.
    expect(page.url()).toMatch(/\/books\/[^/]+\/studio\?.*chapter=[0-9a-fA-F-]+/);

    // 6. Navigate back to book detail to verify chapter persisted in list
    await booksPage.goto();
    await booksPage.openBook(bookTitle);
    await detail.expectTitle(bookTitle);

    // 7. Assert chapter row visible (filter by stable substring of title)
    await expect(chapters.chapterRow("Jonathan Harker")).toBeVisible({ timeout: 5_000 });
  });
});
