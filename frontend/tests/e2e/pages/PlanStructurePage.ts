// Page Object for the S2 (Plan & Structure) dock panels: arc-inspector (32), arc-templates (34) and
// the 拆文 Import & Deconstruct section (34 §4.3). Locator list = the test surface = the data-testid
// contract (tests/e2e/CONVENTIONS.md). Panels open via the Command Palette, the live user path.
import { expect, type Page, type Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';

export class PlanStructurePage {
  readonly page: Page;
  readonly studio: StudioPage;

  // ── arc-inspector ──
  readonly inspectorPanel: Locator;
  readonly picker: Locator;
  readonly body: Locator;
  readonly emptyBook: Locator;
  readonly fTitle: Locator;
  readonly fGoal: Locator;
  readonly fStatus: Locator;
  readonly writeError: Locator;
  readonly archive: Locator;
  readonly restore: Locator;
  readonly archivedBanner: Locator;

  // ── arc-templates ──
  readonly templatesPanel: Locator;
  readonly newButton: Locator;
  readonly createCode: Locator;
  readonly createName: Locator;
  readonly createShare: Locator;
  readonly createSubmit: Locator;
  readonly templatesEmpty: Locator;
  readonly detail: Locator;
  readonly back: Locator;
  readonly driftSection: Locator;

  // ── 拆文 ──
  readonly deconstructSection: Locator;
  readonly deconstructCopyright: Locator;
  readonly pasteTitle: Locator;
  readonly pasteContent: Locator;
  readonly pasteSubmit: Locator;
  readonly deconstructRun: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);

    this.inspectorPanel = page.getByTestId('studio-arc-inspector-panel');
    this.picker = page.getByTestId('arc-inspector-picker');
    this.body = page.getByTestId('arc-inspector-body');
    this.emptyBook = page.getByTestId('arc-inspector-empty-book');
    this.fTitle = page.getByTestId('arc-f-title');
    this.fGoal = page.getByTestId('arc-f-goal');
    this.fStatus = page.getByTestId('arc-f-status');
    this.writeError = page.getByTestId('arc-inspector-write-error');
    this.archive = page.getByTestId('arc-archive');
    this.restore = page.getByTestId('arc-restore');
    this.archivedBanner = page.getByTestId('arc-inspector-archived');

    this.templatesPanel = page.getByTestId('studio-arc-templates-panel');
    this.newButton = page.getByTestId('arc-new');
    this.createCode = page.getByTestId('arc-create-code');
    this.createName = page.getByTestId('arc-create-name');
    this.createShare = page.getByTestId('arc-create-share');
    this.createSubmit = page.getByTestId('arc-create-submit');
    this.templatesEmpty = page.getByTestId('arc-templates-empty');
    this.detail = page.getByTestId('arc-template-detail');
    this.back = page.getByTestId('arc-back');
    this.driftSection = page.getByTestId('arc-drift-section');

    this.deconstructSection = page.getByTestId('import-deconstruct-section');
    this.deconstructCopyright = page.getByTestId('deconstruct-copyright');
    this.pasteTitle = page.getByTestId('paste-title');
    this.pasteContent = page.getByTestId('paste-content');
    this.pasteSubmit = page.getByTestId('paste-submit');
    this.deconstructRun = page.getByTestId('deconstruct-run');
  }

  // ── openers ──
  async openInspector(bookId: string): Promise<void> {
    await this.studio.goto(bookId);
    await this.studio.openPanel('arc-inspector', 'arc inspector');
    await expect(this.inspectorPanel).toBeVisible();
  }

  async openTemplates(bookId: string): Promise<void> {
    await this.studio.goto(bookId);
    await this.studio.openPanel('arc-templates', 'arc templates');
    await expect(this.templatesPanel).toBeVisible();
  }

  // ── arc-inspector helpers ──
  async selectArc(arcId: string): Promise<void> {
    await this.picker.selectOption(arcId);
    await expect(this.body).toBeVisible();
  }

  /** Commit an inline field edit the way a user does — type then blur (onBlur → OCC edit). */
  async editField(field: Locator, value: string): Promise<void> {
    await field.click();
    await field.fill(value);
    await field.blur();
  }

  addTrackForm(): { key: Locator; label: Locator; submit: Locator; open: Locator } {
    return {
      open: this.page.getByTestId('arc-track-add'),
      key: this.page.getByTestId('arc-track-add-key'),
      label: this.page.getByTestId('arc-track-add-label'),
      submit: this.page.getByTestId('arc-track-add-submit'),
    };
  }
  trackRow(key: string): Locator { return this.page.getByTestId(`arc-track-${key}`); }

  // ── arc-templates helpers ──
  tab(view: 'library' | 'catalog' | 'deconstruct'): Locator {
    return this.page.getByTestId(`arc-tab-${view}`);
  }
  tier(key: 'all' | 'mine' | 'system' | 'book'): Locator {
    return this.page.getByTestId(`arc-tier-${key}`);
  }
  row(id: string): Locator { return this.page.getByTestId(`arc-row-${id}`); }
  tierChip(id: string): Locator { return this.page.getByTestId(`arc-tier-chip-${id}`); }
  archiveTemplate(id: string): Locator { return this.page.getByTestId(`arc-archive-${id}`); }
  adoptTemplate(id: string): Locator { return this.page.getByTestId(`arc-adopt-${id}`); }

  async createTemplate(code: string, name: string, shareToBook = false): Promise<void> {
    await this.newButton.click();
    await this.createCode.fill(code);
    await this.createName.fill(name);
    if (shareToBook) await this.createShare.check();
    await this.createSubmit.click();
  }
}
