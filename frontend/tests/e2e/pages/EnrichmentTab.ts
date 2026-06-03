import type { Page, Locator } from '@playwright/test';

export type EnrichmentPanel = 'proposals' | 'gaps' | 'sources' | 'jobs' | 'settings';

/** Page object for the book's Enrichment tab (de-bias C3 GUI). */
export class EnrichmentTab {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  /** Navigate straight to the book's enrichment route (each tab is an explicit route). */
  async goto(bookId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/enrichment`);
  }

  tab(name: EnrichmentPanel): Locator {
    return this.page.getByTestId(`enrichment-tab-${name}`);
  }

  async openPanel(name: EnrichmentPanel): Promise<void> {
    await this.tab(name).click();
  }

  // ── Profile (Settings) sub-panel ─────────────────────────────────────────
  get worldview(): Locator {
    return this.page.getByTestId('profile-worldview');
  }
  get suggestButton(): Locator {
    return this.page.getByTestId('profile-suggest');
  }
  get saveButton(): Locator {
    return this.page.getByTestId('profile-save');
  }

  // ── Gaps sub-panel ───────────────────────────────────────────────────────
  get detectButton(): Locator {
    return this.page.getByTestId('enrichment-detect-gaps');
  }
  get extractFirstNotice(): Locator {
    return this.page.getByTestId('enrichment-gaps-extract-first');
  }
}
