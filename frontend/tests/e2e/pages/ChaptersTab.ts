import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

export interface ChapterCreateInput {
  title?: string;
  language: string;
  body?: string;
}

export class ChaptersTab {
  readonly page: Page;
  readonly addButton: Locator;
  readonly titleInput: Locator;
  readonly languageInput: Locator;
  readonly bodyInput: Locator;
  readonly createSubmit: Locator;
  readonly createCancel: Locator;

  constructor(page: Page) {
    this.page = page;
    this.addButton = page.getByTestId('chapter-add-button');
    this.titleInput = page.getByTestId('chapter-title-input');
    this.languageInput = page.getByTestId('chapter-language-input');
    this.bodyInput = page.getByTestId('chapter-body-input');
    this.createSubmit = page.getByTestId('chapter-create-submit');
    this.createCancel = page.getByTestId('chapter-create-cancel');
  }

  async openAddDialog(): Promise<void> {
    await this.addButton.click();
    await expect(this.languageInput).toBeVisible();
  }

  async createChapter(input: ChapterCreateInput): Promise<void> {
    await this.openAddDialog();
    if (input.title) {
      await this.titleInput.fill(input.title);
    }
    await this.languageInput.fill(input.language);
    if (input.body) {
      await this.bodyInput.fill(input.body);
    }
    await this.createSubmit.click();
    // App auto-navigates to /books/:bookId/chapters/:chapterId/edit on success
    await this.page.waitForURL(/\/books\/[^/]+\/chapters\/[^/]+\/edit/, { timeout: 15_000 });
  }

  chapterRow(titleSubstring: string): Locator {
    return this.page.getByTestId('chapter-title-cell').filter({ hasText: titleSubstring });
  }
}
