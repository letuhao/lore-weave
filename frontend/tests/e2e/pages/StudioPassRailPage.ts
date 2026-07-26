// S3 Page Object — the Writing Studio's Pass Rail (`plan-passes`) + Planner surfaces. Opens panels
// via the command palette (the reachability contract), and exposes the rail ledger, the run picker,
// the checkpoint review (content + PF-7 seed gate + approve), and the planner repair strip locators.
import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

export class StudioPassRailPage {
  readonly page: Page;
  readonly palette: Locator;
  readonly railPanel: Locator;
  readonly runPicker: Locator;
  readonly footer: Locator;
  readonly cursor: Locator;
  readonly relink: Locator;

  constructor(page: Page) {
    this.page = page;
    this.palette = page.getByRole('dialog').getByPlaceholder('Type a command…');
    this.railPanel = page.getByTestId('studio-plan-passes-panel');
    this.runPicker = page.getByTestId('plan-passes-run-picker');
    this.footer = page.getByTestId('plan-passes-footer');
    this.cursor = page.getByTestId('plan-passes-cursor');
    this.relink = page.getByTestId('plan-passes-relink');
  }

  async gotoStudio(bookId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/studio`);
    await expect(this.page.getByText('Writing Studio').first()).toBeVisible();
  }

  /** Open a studio panel via the command palette (⌘⇧P → "Studio: Open <name>"). */
  async openPanel(name: string): Promise<void> {
    await this.page.keyboard.press('Control+Shift+P');
    const item = this.page.getByRole('button', { name: new RegExp(`Studio: Open ${name}`, 'i') });
    await item.first().click();
  }

  async openPassRail(): Promise<void> {
    await this.openPanel('Pass Rail');
    await expect(this.railPanel).toBeVisible();
  }

  // ── the ledger ──
  passRow(passId: string): Locator { return this.page.getByTestId(`pass-row-${passId}`); }
  runButton(passId: string): Locator { return this.page.getByTestId(`pass-run-${passId}`); }
  reviewButton(passId: string): Locator { return this.page.getByTestId(`pass-review-${passId}`); }
  blockedTag(passId: string): Locator { return this.page.getByTestId(`pass-blocked-${passId}`); }
  viewButton(passId: string): Locator { return this.page.getByTestId(`pass-view-${passId}`); }

  async selectRun(idPrefix: string): Promise<void> {
    await this.runPicker.selectOption({ label: new RegExp(`^${idPrefix}`) as unknown as string }).catch(async () => {
      // selectOption by label regex isn't supported; fall back to the value whose text starts with the prefix
      const opt = this.runPicker.locator('option', { hasText: idPrefix });
      await this.runPicker.selectOption(await opt.getAttribute('value') ?? '');
    });
  }

  // ── the checkpoint review (M4-CP) ──
  readonly review = {
    root: () => this.page.getByTestId('pass-checkpoint-review'),
    content: () => this.page.getByTestId('review-content'),
    castList: () => this.page.getByTestId('artifact-cast'),
    rawJson: () => this.page.getByTestId('artifact-json'),
    seedGate: () => this.page.getByTestId('review-seed-gate'),
    applySeed: () => this.page.getByTestId('review-apply-seed'),
    approve: () => this.page.getByTestId('review-approve'),
    reject: () => this.page.getByTestId('review-reject'),
  };

  // ── the planner ──
  readonly planner = {
    open: () => this.openPanel('Planner'),
    proposeBlindNote: () => this.page.getByTestId('plan-propose-blind-note'),
    groundedNote: () => this.page.getByTestId('plan-grounded-note'),          // PROPOSE-BLIND affirmation
    groundToggle: () => this.page.getByTestId('plan-ground-toggle'),          // "Continue this book"
    groundCheckbox: () => this.page.getByTestId('plan-ground-checkbox'),
    passRailLink: () => this.page.getByTestId('planner-open-pass-rail'),
    runsTab: () => this.page.getByTestId('plan-tab-list'),
    runTab: () => this.page.getByTestId('plan-tab-run'),
    showArchived: () => this.page.getByTestId('plan-runs-show-archived'),
    repairStrip: () => this.page.getByTestId('plan-repair-strip'),
    autofixButton: () => this.page.getByTestId('plan-repair-autofix'),
    repairConfirm: () => this.page.getByTestId('plan-repair-confirm-btn'),
  };
}
