// Page Object for the S4 `quality-conformance` dock panel (the beat-by-beat trace + re-run +
// regenerate + the loop-connect deep-link).
import type { Page, Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';

export class QualityConformancePage {
  readonly page: Page;
  readonly studio: StudioPage;
  readonly panel: Locator;
  readonly chapterPicker: Locator;
  readonly trace: Locator;
  readonly rerun: Locator;
  readonly noChapter: Locator;
  readonly empty: Locator;
  readonly emptyBindCta: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);
    this.panel = page.getByTestId('studio-quality-conformance-panel');
    this.chapterPicker = page.getByTestId('quality-conformance-chapter-picker');
    this.trace = page.getByTestId('conformance-trace-view');
    this.rerun = page.getByTestId('conformance-rerun');
    this.noChapter = page.getByTestId('quality-conformance-no-chapter');
    this.empty = page.getByTestId('conformance-empty');
    this.emptyBindCta = page.getByTestId('conformance-empty-bind-cta');
  }

  async open(bookId: string): Promise<void> {
    await this.studio.goto(bookId);
    await this.studio.openPanel('quality-conformance', 'conformance');
  }

  row(nodeId: string): Locator { return this.page.getByTestId(`conformance-row-${nodeId}`); }
  openScene(nodeId: string): Locator { return this.page.getByTestId(`conformance-open-scene-${nodeId}`); }
  regen(nodeId: string): Locator { return this.page.getByTestId(`conformance-regen-${nodeId}`); }
  anyOpenScene(): Locator { return this.page.locator('[data-testid^="conformance-open-scene-"]'); }
}
