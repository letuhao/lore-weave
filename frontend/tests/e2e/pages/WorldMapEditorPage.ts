// Page Object for the S7·2 `world-map` dock panel (the World-Map Editor). The locator list IS the
// test surface = the data-testid contract, all grepped from features/world/components/WorldMapEditor.tsx
// + studio/panels/WorldMapEditorPanel.tsx (root `studio-world-map-panel`).
//
// The panel resolves its subject from props.params, then an in-panel WORLD picker → MAP rail. Opened by
// bare id from the Command Palette (no params) it shows the world picker first — the same live path a
// real author takes. A pin/vertex DRAG must be driven with page.mouse (CDP = trusted events) — d3-style
// pointer capture ignores synthetic events; see [[playwright-cdp-mouse-drives-d3-drag]].
import type { Page, Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';

export class WorldMapEditorPage {
  readonly page: Page;
  readonly studio: StudioPage;
  readonly panel: Locator;         // studio-world-map-panel (dock root)
  readonly editor: Locator;        // world-map-editor (full body — only when a map is selected)
  readonly worldPicker: Locator;   // world-map-world-picker
  readonly empty: Locator;         // world-map-empty ("draw the world your story lives in")
  readonly error: Locator;         // world-map-error
  readonly toolrail: Locator;
  readonly rail: Locator;          // world-map-rail (map list)
  readonly newMap: Locator;        // world-map-new (+ New map — same testid in empty state & rail)
  readonly upload: Locator;        // world-map-upload button
  readonly fileInput: Locator;     // world-map-file-input (hidden <input type=file>)
  readonly canvas: Locator;        // world-map-canvas
  readonly noImage: Locator;       // world-map-no-image placeholder
  readonly footer: Locator;        // world-map-footer (counts)
  readonly regionsSvg: Locator;    // world-map-regions overlay
  readonly regionDraft: Locator;   // world-map-region-draft (pts counter while drawing)
  readonly regionFinish: Locator;  // world-map-region-finish
  readonly markerPopover: Locator;
  readonly markerLabel: Locator;
  readonly markerSource: Locator;
  readonly markerEntity: Locator;
  readonly markerSave: Locator;
  readonly markerUnbind: Locator;
  readonly markerDelete: Locator;
  readonly regionPopover: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);
    this.panel = page.getByTestId('studio-world-map-panel');
    this.editor = page.getByTestId('world-map-editor');
    this.worldPicker = page.getByTestId('world-map-world-picker');
    this.empty = page.getByTestId('world-map-empty');
    this.error = page.getByTestId('world-map-error');
    this.toolrail = page.getByTestId('world-map-toolrail');
    this.rail = page.getByTestId('world-map-rail');
    this.newMap = page.getByTestId('world-map-new');
    this.upload = page.getByTestId('world-map-upload');
    this.fileInput = page.getByTestId('world-map-file-input');
    this.canvas = page.getByTestId('world-map-canvas');
    this.noImage = page.getByTestId('world-map-no-image');
    this.footer = page.getByTestId('world-map-footer');
    this.regionsSvg = page.getByTestId('world-map-regions');
    this.regionDraft = page.getByTestId('world-map-region-draft');
    this.regionFinish = page.getByTestId('world-map-region-finish');
    this.markerPopover = page.getByTestId('world-map-marker-popover');
    this.markerLabel = page.getByTestId('world-map-marker-label');
    this.markerSource = page.getByTestId('world-map-marker-source');
    this.markerEntity = page.getByTestId('world-map-marker-entity');
    this.markerSave = page.getByTestId('world-map-marker-save');
    this.markerUnbind = page.getByTestId('world-map-marker-unbind');
    this.markerDelete = page.getByTestId('world-map-marker-delete');
    this.regionPopover = page.getByTestId('world-map-region-popover');
  }

  /** Open the panel via the Command Palette (⌘⇧P → "world map" → Enter) — the real-user path. */
  async open(bookId: string): Promise<void> {
    await this.studio.goto(bookId);
    await this.studio.openPanel('world-map', 'world map');
  }

  // world picker
  worldOption(worldId: string): Locator { return this.page.getByTestId(`world-map-world-${worldId}`); }

  // tool rail
  mode(m: 'select' | 'pin' | 'region'): Locator { return this.page.getByTestId(`world-map-mode-${m}`); }

  // map rail
  mapTab(mapId: string): Locator { return this.page.getByTestId(`world-map-tab-${mapId}`); }

  // markers (id is a server uuid, unknown until dropped — query by prefix)
  anyMarker(): Locator { return this.page.locator('[data-testid^="world-map-marker-"]'); }
  marker(markerId: string): Locator { return this.page.getByTestId(`world-map-marker-${markerId}`); }

  // regions
  regionPolygons(): Locator { return this.regionsSvg.locator('polygon'); }
  vertex(i: number): Locator { return this.page.getByTestId(`world-map-vertex-${i}`); }

  /** Drive a real drag with page.mouse (CDP-trusted events) — from a source element's centre to an
   *  absolute (targetX,targetY). Synthetic PointerEvents / browser_drag do NOT drive pointer-capture
   *  drags ([[playwright-cdp-mouse-drives-d3-drag]]); the stepped move fires the pointermove the
   *  component's `movedRef` guard requires to treat the gesture as a drag (not a bare select-click). */
  async dragTo(source: Locator, targetX: number, targetY: number, steps = 14): Promise<void> {
    const b = await source.boundingBox();
    if (!b) throw new Error('drag source has no bounding box');
    await this.page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
    await this.page.mouse.down();
    await this.page.mouse.move(targetX, targetY, { steps });
    await this.page.mouse.up();
  }
}
