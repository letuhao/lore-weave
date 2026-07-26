// Page Object for the S7-1 KG Entity Authoring surface — the `kg-entities` +
// `kg-graph` dock panels and the Create/Edit/Relation dialogs that mount INSIDE
// them (peers of EntityEditDialog). Locator list = the test surface = the
// data-testid contract (all ids grepped from the real components:
// EntitiesTab / CreateEntityDialog / EntityDetailPanel / EntityEditDialog /
// CreateRelationDialog / ProjectGraphView).
import type { Page, Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';
import type { AuthorableEntityKind } from '../../../src/features/knowledge/lib/entityKinds';

export class KgAuthoringPage {
  readonly page: Page;
  readonly studio: StudioPage;

  // panels
  readonly panel: Locator;        // studio-kg-entities-panel
  readonly graphPanel: Locator;   // studio-kg-graph-panel
  readonly graphView: Locator;    // project-graph-view

  // entities list toolbar
  readonly projectFilter: Locator;
  readonly newButton: Locator;
  readonly search: Locator;
  readonly table: Locator;

  // create-entity dialog
  readonly createName: Locator;
  readonly createKindGrid: Locator;
  readonly createConfirm: Locator;

  // detail slide-over
  readonly detail: Locator;
  readonly detailEdit: Locator;
  readonly detailLink: Locator;
  readonly detailArchive: Locator;
  readonly detailClose: Locator;
  readonly detailAliases: Locator;
  readonly detailOutgoing: Locator;

  // edit-entity dialog
  readonly editName: Locator;
  readonly editKind: Locator;
  readonly editAliases: Locator;
  readonly editConfirm: Locator;

  // create-relation dialog
  readonly relSubject: Locator;
  readonly relPredicate: Locator;
  readonly relObjectSearch: Locator;
  readonly relObjectList: Locator;
  readonly relConfirm: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);

    this.panel = page.getByTestId('studio-kg-entities-panel');
    this.graphPanel = page.getByTestId('studio-kg-graph-panel');
    this.graphView = page.getByTestId('project-graph-view');

    this.projectFilter = page.getByTestId('entities-filter-project');
    this.newButton = page.getByTestId('entities-new-button');
    this.search = page.getByTestId('entities-filter-search');
    this.table = page.getByTestId('entities-table');

    this.createName = page.getByTestId('entity-create-name');
    this.createKindGrid = page.getByTestId('entity-create-kind-grid');
    this.createConfirm = page.getByTestId('entity-create-confirm');

    this.detail = page.getByTestId('entity-detail-panel');
    this.detailEdit = page.getByTestId('entity-detail-edit');
    this.detailLink = page.getByTestId('entity-detail-link');
    this.detailArchive = page.getByTestId('entity-detail-archive');
    this.detailClose = page.getByTestId('entity-detail-close');
    this.detailAliases = page.getByTestId('entity-detail-aliases');
    this.detailOutgoing = page.getByTestId('entity-detail-outgoing');

    this.editName = page.getByTestId('entity-edit-name');
    this.editKind = page.getByTestId('entity-edit-kind');
    this.editAliases = page.getByTestId('entity-edit-aliases');
    this.editConfirm = page.getByTestId('entity-edit-confirm');

    this.relSubject = page.getByTestId('relation-create-subject');
    this.relPredicate = page.getByTestId('relation-create-predicate');
    this.relObjectSearch = page.getByTestId('relation-create-object-search');
    this.relObjectList = page.getByTestId('relation-create-object-list');
    this.relConfirm = page.getByTestId('relation-create-confirm');
  }

  /** Open the studio for a book, then the `kg-entities` panel via the Command
   *  Palette (the real-user path). */
  async openEntities(bookId: string): Promise<void> {
    await this.studio.goto(bookId);
    await this.studio.openPanel('kg-entities', 'Entities');
  }

  /** Open the `kg-graph` panel — assumes the studio is already mounted (opened
   *  as a second dock panel in the same session, no route hop). */
  async openGraph(): Promise<void> {
    await this.studio.openPanel('kg-graph', 'Knowledge Graph');
  }

  // The `kg-entities` panel opened from the palette is UNSCOPED, so it shows the
  // project `<select>`; a create needs a project tag, so pick it first (this
  // also scopes the list to just this project's entities — no dev-DB noise).
  async selectProject(projectId: string): Promise<void> {
    await this.projectFilter.selectOption(projectId);
  }

  /** Desktop list row for an entity by its visible name (the `entities-row`
   *  testid is desktop-only; the e2e viewport is desktop). A row must OPEN the
   *  detail — it is not a dead tile. */
  row(name: string): Locator {
    return this.page.getByTestId('entities-row').filter({ hasText: name });
  }

  /** Hand-author an entity via the toolbar `+ New Entity` dialog; `kind` is a
   *  CLOSED-SET radio-grid, never a free string. */
  async createEntity(name: string, kind: AuthorableEntityKind): Promise<void> {
    await this.newButton.click();
    await this.createName.fill(name);
    await this.page.getByTestId(`entity-create-kind-${kind}`).click();
    await this.createConfirm.click();
  }

  /** Open a list row's detail slide-over. */
  async openDetail(name: string): Promise<void> {
    await this.row(name).click();
  }

  /** Build a relation subject → predicate → object via the detail Link2 button. */
  async createRelation(
    predicate: string,
    objectSearch: string,
    objectId: string,
  ): Promise<void> {
    await this.detailLink.click();
    await this.relPredicate.selectOption(predicate);
    await this.relObjectSearch.fill(objectSearch);
    await this.relObjectList.waitFor({ state: 'visible' });
    await this.page.getByTestId(`relation-create-object-${objectId}`).click();
    await this.relConfirm.click();
  }

  /** A graph node (reuses the shared relmap-node primitive). */
  graphNode(): Locator {
    return this.page.getByTestId('relmap-node');
  }

  /** The sonner Undo action button (archive → Undo → restore round-trip). */
  toastUndo(): Locator {
    return this.page.locator('[data-sonner-toast] [data-button]').filter({ hasText: 'Undo' });
  }
}
