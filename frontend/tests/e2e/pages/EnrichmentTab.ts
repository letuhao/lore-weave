import type { Page, Locator } from '@playwright/test';

export type EnrichmentPanel = 'compose' | 'proposals' | 'gaps' | 'sources' | 'jobs' | 'settings';

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

  // ── Compose sub-panel (Slice 1 + 4 author controls) ──────────────────────
  composeMode(name: string): Locator {
    return this.page.getByTestId(`compose-mode-${name}`);
  }
  get targetNewToggle(): Locator {
    return this.page.getByTestId('compose-target-mode-new');
  }
  get targetName(): Locator {
    return this.page.getByTestId('compose-target-name');
  }
  get targetKind(): Locator {
    return this.page.getByTestId('compose-target-kind');
  }
  get contextText(): Locator {
    return this.page.getByTestId('compose-context-text');
  }
  get techniqueSelect(): Locator {
    return this.page.getByTestId('compose-technique');
  }
  get persistCorpus(): Locator {
    return this.page.getByTestId('compose-persist-corpus');
  }
  get dimsAuto(): Locator {
    return this.page.getByTestId('compose-dims-auto');
  }
  get dimsPicker(): Locator {
    return this.page.getByTestId('compose-dims-picker');
  }

  // ── Profile override editor (Slice 2 base rows) ──────────────────────────
  overrideKind(kind: string): Locator {
    return this.page.getByTestId(`override-kind-${kind}`);
  }
  overrideBase(kind: string): Locator {
    return this.page.getByTestId(`override-base-${kind}`);
  }
}
