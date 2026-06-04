import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

/** Page object for the standalone revision-compare route. */
export class RevisionComparePage {
  readonly page: Page;
  readonly leftSelect: Locator;
  readonly rightSelect: Locator;
  readonly modeSxs: Locator;
  readonly modeInline: Locator;
  readonly loadMore: Locator;
  readonly back: Locator;
  readonly needTwo: Locator;
  readonly same: Locator;
  readonly diffSxs: Locator;
  readonly diffInline: Locator;

  constructor(page: Page) {
    this.page = page;
    this.leftSelect = page.getByTestId('compare-left-select');
    this.rightSelect = page.getByTestId('compare-right-select');
    this.modeSxs = page.getByTestId('compare-mode-sxs');
    this.modeInline = page.getByTestId('compare-mode-inline');
    this.loadMore = page.getByTestId('compare-load-more');
    this.back = page.getByTestId('compare-back');
    this.needTwo = page.getByTestId('compare-need-two');
    this.same = page.getByTestId('compare-same');
    this.diffSxs = page.getByTestId('diff-sxs');
    this.diffInline = page.getByTestId('diff-inline');
  }

  async goto(bookId: string, chapterId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/chapters/${chapterId}/compare`);
  }

  /** Revision ids in a picker, in display order (newest first). */
  async optionValues(): Promise<string[]> {
    return this.leftSelect.locator('option').evaluateAll((opts) =>
      opts.map((o) => (o as HTMLOptionElement).value).filter(Boolean),
    );
  }

  /** Words highlighted as changed in the side-by-side view. */
  async changedWords(): Promise<string[]> {
    return this.diffSxs.locator('[data-changed="true"]').allInnerTexts();
  }

  async expectDiffVisible(): Promise<void> {
    await expect(this.diffSxs.or(this.diffInline)).toBeVisible();
  }
}
