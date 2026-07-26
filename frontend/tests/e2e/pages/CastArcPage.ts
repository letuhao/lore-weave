// Page Object for the S7-4 `cast` (Cast Codex) + `character-arc` dock panels.
// The locator list IS the test surface = the data-testid contract. Every id below
// was read from source, never invented:
//   CastCodexPanel.tsx        → composition-cast, cast-search, cast-new-entity,
//                                cast-load-more, cast-more-hint, cast-window-hint
//   CastEntityRow.tsx         → cast-row (+ data-entity/data-status), cast-row-toggle,
//                                cast-row-detail, cast-row-arc, cast-row-rename,
//                                cast-row-rename-input, cast-row-edit, cast-row-archive
//   CastPanel.tsx             → studio-cast-panel
//   CharacterArcView.tsx      → composition-arc, arc-character-select, arc-add-event,
//                                arc-empty, arc-svg, arc-relations
//   CharacterArcPanel.tsx     → studio-character-arc-panel
//   TimelineEventPoint.tsx    → timeline-event
//   EventEditDialog.tsx       → event-edit-title, event-edit-confirm
import { expect, type Page, type Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';

export class CastArcPage {
  readonly page: Page;
  readonly studio: StudioPage;

  // ── cast codex ──
  readonly castPanel: Locator;   // the dock wrapper
  readonly codex: Locator;       // the leaf CastCodexPanel root
  readonly search: Locator;
  readonly newEntity: Locator;
  readonly loadMore: Locator;
  readonly moreHint: Locator;
  readonly windowHint: Locator;

  // ── character arc ──
  readonly arcPanel: Locator;    // the dock wrapper
  readonly arcView: Locator;     // the leaf CharacterArcView root
  readonly arcSelect: Locator;
  readonly arcAddEvent: Locator;
  readonly arcEmpty: Locator;
  readonly arcSvg: Locator;
  readonly timelineEvent: Locator;

  // ── event-authoring dialog (reused knowledge dialog) ──
  readonly eventTitle: Locator;
  readonly eventConfirm: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);

    this.castPanel = page.getByTestId('studio-cast-panel');
    this.codex = page.getByTestId('composition-cast');
    this.search = page.getByTestId('cast-search');
    this.newEntity = page.getByTestId('cast-new-entity');
    this.loadMore = page.getByTestId('cast-load-more');
    this.moreHint = page.getByTestId('cast-more-hint');
    this.windowHint = page.getByTestId('cast-window-hint');

    this.arcPanel = page.getByTestId('studio-character-arc-panel');
    this.arcView = page.getByTestId('composition-arc');
    this.arcSelect = page.getByTestId('arc-character-select');
    this.arcAddEvent = page.getByTestId('arc-add-event');
    this.arcEmpty = page.getByTestId('arc-empty');
    this.arcSvg = page.getByTestId('arc-svg');
    this.timelineEvent = page.getByTestId('timeline-event');

    this.eventTitle = page.getByTestId('event-edit-title');
    this.eventConfirm = page.getByTestId('event-edit-confirm');
  }

  /** Land in the Studio for this book and open the `cast` dock panel via the
   *  Command Palette — the same live path a real user takes (no test shortcut). */
  async open(bookId: string): Promise<void> {
    await this.studio.goto(bookId);
    await this.studio.openPanel('cast', 'cast');
    await expect(this.castPanel).toBeVisible();
  }

  /** Re-focus the (already-open) cast tab — opening the arc panel stacks it over
   *  the codex, so a real user switches back before touching another cast row. */
  async focusCast(): Promise<void> {
    await this.studio.openPanel('cast', 'cast');
    await expect(this.castPanel).toBeVisible();
  }

  /** Re-focus the (already-open) character-arc tab via the palette. */
  async focusArc(): Promise<void> {
    await this.studio.openPanel('character-arc', 'character arc');
    await expect(this.arcPanel).toBeVisible();
  }

  // ── row-scoped locators (unique by the entity id on data-entity) ──
  row(entityId: string): Locator {
    return this.page.locator(`[data-testid="cast-row"][data-entity="${entityId}"]`);
  }
  rowToggle(entityId: string): Locator { return this.row(entityId).getByTestId('cast-row-toggle'); }
  rowDetail(entityId: string): Locator { return this.row(entityId).getByTestId('cast-row-detail'); }
  rowArc(entityId: string): Locator { return this.row(entityId).getByTestId('cast-row-arc'); }
  rowRename(entityId: string): Locator { return this.row(entityId).getByTestId('cast-row-rename'); }
  rowRenameInput(entityId: string): Locator { return this.row(entityId).getByTestId('cast-row-rename-input'); }

  /** Every rendered cast row (used to assert the count is honest, not truncated). */
  anyRow(): Locator { return this.page.locator('[data-testid="cast-row"]'); }
}
