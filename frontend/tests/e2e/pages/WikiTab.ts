import type { Page, Locator } from '@playwright/test';

export class WikiTab {
  readonly page: Page;
  readonly generateEmpty: Locator;
  readonly generateHeader: Locator;

  constructor(page: Page) {
    this.page = page;
    this.generateEmpty = page.getByTestId('wiki-generate-empty');
    this.generateHeader = page.getByTestId('wiki-generate-trigger');
  }

  async gotoForBook(bookId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/wiki`);
  }

  /** Click the visible generate button (empty-state if no articles, header otherwise). */
  async generate(): Promise<void> {
    const empty = this.generateEmpty;
    if (await empty.isVisible().catch(() => false)) {
      await empty.click();
      return;
    }
    await this.generateHeader.click();
  }

  articleRow(textSubstring: string): Locator {
    return this.page.getByTestId('wiki-article-row').filter({ hasText: textSubstring });
  }

  allArticles(): Locator {
    return this.page.getByTestId('wiki-article-row');
  }
}
