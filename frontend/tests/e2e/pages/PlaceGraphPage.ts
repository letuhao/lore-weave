// Page Object for the S7-3 `place-graph` dock panel — the studio host around the composition
// <WorldMap> leaf. Locator list = the test surface = the data-testid contract, grepped from the
// REAL components: PlaceGraphPanel.tsx (wrapper states) + WorldMap.tsx / PlaceNode.tsx / RelationEdge.tsx
// (the leaf toolbar + graph). The panel was operable-but-STRANDED on the legacy ChapterEditorPage;
// this Page Object drives the ported, palette-reachable surface the real user now sees.
import type { Page, Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';

export class PlaceGraphPage {
  readonly page: Page;
  readonly studio: StudioPage;

  // wrapper (PlaceGraphPanel.tsx)
  readonly panel: Locator;
  readonly noWork: Locator;
  readonly setupCowriter: Locator;
  readonly authorOther: Locator;

  // leaf toolbar + graph (WorldMap.tsx)
  readonly worldmap: Locator;
  readonly addInput: Locator;
  readonly addButton: Locator;
  readonly linkToggle: Locator;
  readonly linkBar: Locator;
  readonly predicate: Locator;
  readonly linkConfirm: Locator;
  readonly linkCancel: Locator;
  readonly backdropButton: Locator;
  readonly empty: Locator;
  readonly svg: Locator;
  readonly edges: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);
    this.panel = page.getByTestId('studio-place-graph-panel');
    this.noWork = page.getByTestId('place-graph-nowork');
    this.setupCowriter = page.getByTestId('place-graph-setup-cowriter');
    this.authorOther = page.getByTestId('place-graph-author-other');

    this.worldmap = page.getByTestId('composition-worldmap');
    this.addInput = page.getByTestId('worldmap-add-input');
    this.addButton = page.getByTestId('worldmap-add');
    this.linkToggle = page.getByTestId('worldmap-link-toggle');
    this.linkBar = page.getByTestId('worldmap-linkbar');
    this.predicate = page.getByTestId('worldmap-predicate');
    this.linkConfirm = page.getByTestId('worldmap-link-confirm');
    this.linkCancel = page.getByTestId('worldmap-link-cancel');
    this.backdropButton = page.getByTestId('worldmap-backdrop');
    this.empty = page.getByTestId('worldmap-empty');
    this.svg = page.getByTestId('worldmap-svg');
    this.edges = page.getByTestId('relmap-edge');
  }

  /** Navigate to the book's studio and open `place-graph` via the Command Palette — the real-user way. */
  async open(bookId: string): Promise<void> {
    await this.studio.goto(bookId);
    await this.studio.openPanel('place-graph', 'place');
  }

  /** The `<g>` node wrapper (carries `transform` + `data-place`) for a place, matched by its label. */
  node(name: string): Locator {
    return this.page.getByTestId('worldmap-node').filter({ hasText: name });
  }

  /** The clickable/draggable node body (role=button, aria-label=name). */
  nodeBody(name: string): Locator {
    return this.page.getByTestId('worldmap-node-body').filter({ hasText: name });
  }

  /** Add a place through the live toolbar (the real +Place write → knowledgeApi.createEntity). */
  async addPlace(name: string): Promise<void> {
    await this.addInput.fill(name);
    await this.addButton.click();
  }

  /** Enter link mode, select two nodes, pick a predicate, and confirm (real createRelation POST). */
  async linkPlaces(nameA: string, nameB: string, predicate: 'contains' | 'borders' | 'route_to'): Promise<void> {
    await this.linkToggle.click();
    await this.nodeBody(nameA).click();
    await this.nodeBody(nameB).click();
    await this.linkBar.waitFor({ state: 'visible' });
    await this.predicate.selectOption(predicate);
    await this.linkConfirm.click();
  }

  /** Parse the `<g transform="translate(x, y)">` of a node — used to prove a drag persisted. */
  async nodePos(name: string): Promise<{ x: number; y: number }> {
    const tf = await this.node(name).getAttribute('transform');
    const m = /translate\(\s*([-\d.]+)[ ,]+([-\d.]+)/.exec(tf ?? '');
    if (!m) throw new Error(`node "${name}" has no parseable transform: ${tf}`);
    return { x: Number(m[1]), y: Number(m[2]) };
  }

  /** Drag a node by (dx,dy) using the trusted low-level mouse (GraphCanvas listens to pointer
   *  events; page.mouse dispatches real ones — d3/pointer-drag needs trusted events, synthetic
   *  browser_drag misses the 5px threshold). Moves in steps so `moved` flips past the threshold. */
  async dragNode(name: string, dx: number, dy: number): Promise<void> {
    const box = await this.nodeBody(name).boundingBox();
    if (!box) throw new Error(`node "${name}" has no bounding box (not rendered?)`);
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await this.page.mouse.move(cx, cy);
    await this.page.mouse.down();
    await this.page.mouse.move(cx + dx / 2, cy + dy / 2, { steps: 6 });
    await this.page.mouse.move(cx + dx, cy + dy, { steps: 6 });
    await this.page.mouse.up();
  }
}
