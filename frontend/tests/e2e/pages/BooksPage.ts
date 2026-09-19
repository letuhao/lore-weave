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
    // book-language-input is a LanguagePicker, i.e. a <select> of language CODES
    // (src/components/shared/LanguagePicker.tsx:57). The chapter form's twin is a real
    // <input>, which is why only this one moves off .fill().
    await this.languageInput.selectOption(input.language);
    if (input.description) {
      await this.descriptionInput.fill(input.description);
    }
    await this.createSubmit.click();
    // Creating a book NAVIGATES STRAIGHT INTO THE STUDIO for the new book -- it does not
    // return to the list (src/pages/BooksPage.tsx, and the unit test
    // BooksPage.createNavigate.test.tsx pins exactly that). A caller that wants the list
    // afterwards has to go back to it, the same as a person would.
    await this.page.waitForURL('**/books/*/studio', { timeout: 15_000 });
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
