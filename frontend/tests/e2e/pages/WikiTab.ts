import { expect, type Page, type Locator } from '@playwright/test';

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

  /** Generate wiki articles: open the dialog AND confirm it.
   *
   * 🔴 #268 — this used to click the Generate button and stop. That button only opens
   * `GenerateWikiDialog` (`WikiWorkspace.tsx:571` -> `openBatchGenerate` -> `setGenOpen(true)`);
   * nothing is generated until `wiki-gen-confirm` is pressed. So the caller waited for articles
   * that had never been requested, and it read as "generation is broken".
   *
   * Confirming is what a person does too, so this completes the flow rather than weakening the
   * claim. `canConfirm` needs a model or stub mode (`GenerateWikiDialog.tsx:166`), which the
   * dialog fills from the account default.
   */
  async generate(): Promise<void> {
    const empty = this.generateEmpty;
    if (await empty.isVisible().catch(() => false)) {
      await empty.click();
    } else {
      await this.generateHeader.click();
    }
    const confirm = this.page.getByTestId('wiki-gen-confirm');
    await confirm.waitFor({ state: 'visible', timeout: 15_000 });
    await expect(confirm, 'the generate dialog must be confirmable — a model or stub mode is required').toBeEnabled({ timeout: 15_000 });
    await confirm.click();
  }

  articleRow(textSubstring: string): Locator {
    return this.page.getByTestId('wiki-article-row').filter({ hasText: textSubstring });
  }

  allArticles(): Locator {
    return this.page.getByTestId('wiki-article-row');
  }
}
