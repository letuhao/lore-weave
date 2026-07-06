import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

export interface BookCreateInput {
  title: string;
  language: string;
  description?: string;
}

export class BooksPage {
  readonly page: Page;
  readonly createButton: Locator;
  readonly titleInput: Locator;
  readonly languageInput: Locator;
  readonly descriptionInput: Locator;
  readonly createSubmit: Locator;
  readonly createCancel: Locator;

  constructor(page: Page) {
    this.page = page;
    this.createButton = page.getByTestId('book-create-button');
    this.titleInput = page.getByTestId('book-title-input');
    this.languageInput = page.getByTestId('book-language-input');
    this.descriptionInput = page.getByTestId('book-description-input');
    this.createSubmit = page.getByTestId('book-create-submit');
    this.createCancel = page.getByTestId('book-create-cancel');
  }

  async goto(): Promise<void> {
    await this.page.goto('/books');
  }

  async openCreateDialog(): Promise<void> {
    await this.createButton.click();
    await expect(this.titleInput).toBeVisible();
  }

  async createBook(input: BookCreateInput): Promise<void> {
    await this.openCreateDialog();
    await this.titleInput.fill(input.title);
    await this.languageInput.fill(input.language);
    if (input.description) {
      await this.descriptionInput.fill(input.description);
    }
    await this.createSubmit.click();
    await expect(this.titleInput).not.toBeVisible({ timeout: 5_000 });
  }

  bookRow(title: string): Locator {
    return this.page.getByTestId('book-row').filter({ hasText: title });
  }

  /**
   * Opens the classic book detail page (Chapters/Glossary/etc. tabs). #18 changed the row's
   * default click target to Writing Studio, so this navigates directly to the classic route
   * (stripping `/studio` off the row's href) instead of clicking — existing specs in this
   * suite exercise the classic BookDetailPage + ChaptersTab flow and stay unchanged.
   */
  async openBook(title: string): Promise<void> {
    const href = await this.bookRow(title).getAttribute('href');
    if (!href) throw new Error(`book row for "${title}" has no href`);
    await this.page.goto(href.replace(/\/studio$/, ''));
  }

  /** Opens the book directly into Writing Studio (#18's new default row-click target). */
  async openBookInStudio(title: string): Promise<void> {
    await this.bookRow(title).click();
  }
}
