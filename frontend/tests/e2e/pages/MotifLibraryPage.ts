// Page Object for the S4 `motif-library` dock panel + the scene-inspector Motifs section.
// Locator list = the test surface = the data-testid contract.
import type { Page, Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';

export class MotifLibraryPage {
  readonly page: Page;
  readonly studio: StudioPage;
  readonly panel: Locator;
  readonly view: Locator;
  readonly newButton: Locator;
  readonly mineButton: Locator;
  readonly search: Locator;
  readonly empty: Locator;
  readonly detailDrawer: Locator;
  readonly loadMore: Locator;
  readonly truncated: Locator;
  readonly graphToggle: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);
    this.panel = page.getByTestId('studio-motif-library-panel');
    this.view = page.getByTestId('motif-library-view');
    this.newButton = page.getByTestId('motif-new');
    this.mineButton = page.getByTestId('motif-mine');
    this.search = page.getByTestId('motif-search');
    this.empty = page.getByTestId('motif-empty');
    this.detailDrawer = page.getByTestId('motif-detail-drawer');
    this.loadMore = page.getByTestId('motif-load-more');
    this.truncated = page.getByTestId('motif-list-truncated');
    this.graphToggle = page.getByTestId('motif-graph-toggle');
  }

  async open(bookId: string): Promise<void> {
    await this.studio.goto(bookId);
    await this.studio.openPanel('motif-library', 'motif');
  }

  scopeTab(scope: 'my' | 'book' | 'shared' | 'system' | 'catalog' | 'drafts'): Locator {
    return this.page.getByTestId(`motif-scope-${scope}`);
  }
  card(id: string): Locator { return this.page.getByTestId(`motif-card-${id}`); }
  cardOpen(id: string): Locator { return this.page.getByTestId(`motif-card-open-${id}`); }
  cardAdopt(id: string): Locator { return this.page.getByTestId(`motif-card-adopt-${id}`); }
  anyCard(): Locator { return this.page.locator('[data-testid^="motif-card-open-"]'); }

  // create (inline form)
  get createName(): Locator { return this.page.getByTestId('motif-create-name'); }
  get createCode(): Locator { return this.page.getByTestId('motif-create-code'); }
  get createSubmit(): Locator { return this.page.getByTestId('motif-create-submit'); }

  async createMotif(name: string, code: string): Promise<void> {
    await this.newButton.click();
    await this.createName.fill(name);
    await this.createCode.fill(code);
    await this.createSubmit.click();
  }

  // graph section (inside the detail drawer)
  get graphEdges(): Locator { return this.page.getByTestId('motif-graph-edge'); }
  get graphAddToggle(): Locator { return this.page.getByTestId('motif-graph-add-toggle'); }
  get graphKind(): Locator { return this.page.getByTestId('motif-graph-kind'); }
  get graphNeighbor(): Locator { return this.page.getByTestId('motif-graph-neighbor'); }
  get graphAddSubmit(): Locator { return this.page.getByTestId('motif-graph-add-submit'); }
  get graphAddError(): Locator { return this.page.getByTestId('motif-graph-add-error'); }
  get graphEmpty(): Locator { return this.page.getByTestId('motif-graph-empty'); }
}
