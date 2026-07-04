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
    await this.paletteInput.fill(searchTerm);
    const entry = this.page.getByTestId(`palette-entry-studio.openPanel.${panelId}`);
    await entry.waitFor({ state: 'visible' });
    await entry.click();
    await expect(this.commandPaletteModal).toHaveCount(0);
  }
}
