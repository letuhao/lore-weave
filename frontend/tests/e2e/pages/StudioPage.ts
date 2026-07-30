import { expect, type Page, type Locator } from '@playwright/test';
import type { ActivityView } from '../../../src/features/studio/types';

/** Page object for the Writing Studio (v2) frame. */
export class StudioPage {
  readonly page: Page;
  readonly commandPalette: Locator;
  readonly sidebar: Locator;
  readonly dockview: Locator;
  readonly bottom: Locator;
  readonly toggleBottom: Locator;
  // Palettes (#06a / #06b) + the shared shell input.
  readonly quickOpen: Locator;
  readonly commandPaletteModal: Locator;
  readonly paletteInput: Locator;

  constructor(page: Page) {
    this.page = page;
    this.commandPalette = page.getByTestId('studio-command-palette');
    this.sidebar = page.getByTestId('studio-sidebar');
    // The dock wrapper carries a stable testid (dockview's own dv-* classes are not part of
    // our contract). Targeting the wrapper is robust across dockview version bumps.
    this.dockview = page.getByTestId('studio-dock');
    this.bottom = page.getByTestId('studio-bottom');
    this.toggleBottom = page.getByTestId('studio-toggle-bottom');
    this.quickOpen = page.getByTestId('quick-open');
    this.commandPaletteModal = page.getByTestId('command-palette');
    this.paletteInput = page.getByTestId('palette-input');
  }

  activity(view: ActivityView): Locator {
    return this.page.getByTestId(`studio-activity-${view}`);
  }

  async goto(bookId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/studio`);
    // The activity bar is always present regardless of navigator/collapse state.
    await this.activity('manuscript').waitFor({ state: 'attached' });
  }

  /** Open a dock panel via the Command Palette (⌘⇧P → search title → Enter), the
   *  same live path a real user takes. `paletteEntryId` is the registered
   *  `commandId` (`studio.openPanel.<panelId>`), typed by `useStudioPanel`. */
  async openPanel(panelId: string, searchTerm: string): Promise<void> {
    await this.page.keyboard.press('ControlOrMeta+Shift+P');
    await this.commandPaletteModal.waitFor({ state: 'visible' });
    const entry = this.page.getByTestId(`palette-entry-studio.openPanel.${panelId}`);
    await this.paletteInput.fill(searchTerm);
    // `filterCommands` matches the LOCALIZED label only (`c.label.includes(q)` — not the id,
    // not the description), so an English `searchTerm` matches nothing the moment the
    // account's UI language is not English. That is not theoretical: the test account runs in
    // Vietnamese, and `studio-motif-graph.spec.ts` had been failing on exactly this — the
    // palette answered "Không có lệnh phù hợp" to "motif graph" — so the whole canvas spec
    // was red before it asserted anything about the canvas.
    //
    // An empty query lists EVERY command, so fall back to picking the entry out of the full
    // list. Still a real user path (open the palette, find the command, click it), and it
    // does not depend on what language the user happens to be reading in.
    if (!(await entry.isVisible().catch(() => false))) {
      await this.paletteInput.fill('');
      await entry.scrollIntoViewIfNeeded();
    }
    await entry.waitFor({ state: 'visible' });
    await entry.click();
    await expect(this.commandPaletteModal).toHaveCount(0);
  }

  /** Close a dock tab by its CURRENT title text — dockview's default tab renders a
   *  `.dv-default-tab-action` close button (no data-testid; this is dockview's own DOM, not
   *  ours) inside the `.dv-default-tab` carrying that title. 15_wiki_panels.md's DOCK-10
   *  /review-impl fix needs this: closing (not just switching away from) a dock tab is a real
   *  unmount dockview performs, and no existing spec had exercised that path before. */
  async closePanel(title: string): Promise<void> {
    const tab = this.page.locator('.dv-default-tab', { hasText: title });
    await tab.waitFor({ state: 'visible' });
    // dockview hides the close affordance (.dv-default-tab-action) on INACTIVE tabs until hover;
    // hovering first lets us close a background tab (not just the active one), a real user action.
    await tab.hover();
    await tab.locator('.dv-default-tab-action').click({ force: true });
  }
}
