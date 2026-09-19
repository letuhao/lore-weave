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
    // On success the app opens the new chapter IN THE WRITING STUDIO --
    // /books/:bookId/studio?chapter=:id -- the only chapter editor (the retired
    // /chapters/:id/edit route just redirects there). #18 retargeted chapter and book entry to the
    // Studio on purpose (the classic book detail page is still reachable and writing-studio.spec.ts
    // pins that separately). The CLAIM: creating a chapter lands you
    // where you can edit it, and the URL must carry the chapter that was just made.
    await this.page.waitForURL(/\/books\/[^/]+\/studio\?.*chapter=[0-9a-fA-F-]+/, { timeout: 15_000 });
  }

  chapterRow(titleSubstring: string): Locator {
    return this.page.getByTestId('chapter-title-cell').filter({ hasText: titleSubstring });
  }
}
