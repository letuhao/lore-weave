import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

export class BookDetailPage {
  readonly page: Page;
  readonly title: Locator;

  constructor(page: Page) {
    this.page = page;
    this.title = page.getByTestId('page-header-title');
  }

  async expectTitle(text: string): Promise<void> {
    await expect(this.title).toHaveText(text);
  }
}
