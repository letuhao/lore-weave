import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

// Creation-unblock RAID — the world WORKSPACE (/worlds/:worldId). Covers the
// populate CTAs (G1), the graph + timeline rollups (G4 / D-WORLD-TIMELINE-ROLLUP),
// and the living-world tree. All access via data-testid (i18n/style-agnostic).
export class WorldWorkspacePage {
  readonly page: Page;
  readonly root: Locator;
  readonly loadError: Locator;
  // populate (G1)
  readonly populateActions: Locator;
  readonly addBookButton: Locator;
  readonly createWhatIfButton: Locator;
  readonly whatIfPicker: Locator;
  // add-book modal
  readonly addBookModeAttach: Locator;
  readonly addBookModeCreate: Locator;
  readonly addBookAttachPanel: Locator;
  readonly addBookCreatePanel: Locator;
  readonly addBookTitleInput: Locator;
  readonly addBookSubmit: Locator;
  readonly addBookError: Locator;
  // sections
  readonly livingTree: Locator;
  readonly livingEmpty: Locator;
  readonly graphSection: Locator;
  readonly graphHint: Locator;
  readonly timelineSection: Locator;
  readonly timelineHint: Locator;

  constructor(page: Page) {
    this.page = page;
    this.root = page.getByTestId('world-workspace');
    this.loadError = page.getByTestId('world-load-error');
    this.populateActions = page.getByTestId('world-populate-actions');
    this.addBookButton = page.getByTestId('world-add-book');
    this.createWhatIfButton = page.getByTestId('world-create-whatif');
    this.whatIfPicker = page.getByTestId('world-whatif-picker');
    this.addBookModeAttach = page.getByTestId('add-book-mode-attach');
    this.addBookModeCreate = page.getByTestId('add-book-mode-create');
    this.addBookAttachPanel = page.getByTestId('add-book-attach-panel');
    this.addBookCreatePanel = page.getByTestId('add-book-create-panel');
    this.addBookTitleInput = page.getByTestId('add-book-title-input');
    this.addBookSubmit = page.getByTestId('add-book-submit');
    this.addBookError = page.getByTestId('add-book-error');
    this.livingTree = page.getByTestId('living-world-tree');
    this.livingEmpty = page.getByTestId('living-world-empty');
    this.graphSection = page.getByTestId('world-graph-section');
    this.graphHint = page.getByTestId('world-graph-hint');
    this.timelineSection = page.getByTestId('world-timeline-section');
    this.timelineHint = page.getByTestId('world-timeline-hint');
  }

  async goto(worldId: string): Promise<void> {
    await this.page.goto(`/worlds/${worldId}`);
    await expect(this.root).toBeVisible();
  }

  /** Open the add-book modal and attach an existing book by name via the BookPicker. */
  async attachExistingBook(title: string): Promise<void> {
    await this.addBookButton.click();
    await expect(this.addBookAttachPanel).toBeVisible();
    const combo = this.addBookAttachPanel.getByRole('combobox');
    await combo.click();
    await combo.fill(title);
    await this.page.getByRole('option', { name: title }).first().click();
    await expect(this.addBookSubmit).toBeEnabled();
    await this.addBookSubmit.click();
  }

  /** Open the add-book modal, switch to "create new", and create+attach a book. */
  async createAndAttachBook(title: string): Promise<void> {
    await this.addBookButton.click();
    await this.addBookModeCreate.click();
    await expect(this.addBookCreatePanel).toBeVisible();
    await this.addBookTitleInput.fill(title);
    await expect(this.addBookSubmit).toBeEnabled();
    await this.addBookSubmit.click();
  }
}
