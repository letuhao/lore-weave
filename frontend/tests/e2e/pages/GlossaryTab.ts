import type { Page, Locator } from '@playwright/test';

export class GlossaryTab {
  readonly page: Page;
  readonly extractTrigger: Locator;
  readonly searchInput: Locator;

  constructor(page: Page) {
    this.page = page;
    this.extractTrigger = page.getByTestId('glossary-extract-trigger');
    this.searchInput = page.getByTestId('glossary-search-input');
  }

  async gotoForBook(bookId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/glossary`);
  }

  async search(query: string): Promise<void> {
    await this.searchInput.fill(query);
  }

  entityRow(textSubstring: string): Locator {
    return this.page.getByTestId('glossary-entity-row').filter({ hasText: textSubstring });
  }

  allEntityRows(): Locator {
    return this.page.getByTestId('glossary-entity-row');
  }
}
