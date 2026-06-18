import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

// Creation-unblock RAID (W6/G3) — the book Settings tab's WORLD cross-link section
// (BookWorldSection). The shared WorldPicker IS the control: picking a world
// attaches the book; "Open in world" backlinks to the world workspace.
export class BookSettingsPage {
  readonly page: Page;
  readonly worldSection: Locator;
  readonly worldPickerCombo: Locator;
  readonly worldPickerSelected: Locator;
  readonly openInWorld: Locator;

  constructor(page: Page) {
    this.page = page;
    this.worldSection = page.getByTestId('book-world-section');
    this.worldPickerSelected = page.getByTestId('world-picker-selected');
    this.openInWorld = page.getByTestId('book-open-in-world');
    this.worldPickerCombo = this.worldSection.getByRole('combobox');
  }

  async goto(bookId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/settings`);
    await expect(this.worldSection).toBeVisible();
  }

  /** Pick a world by name in the WorldPicker → attaches the book (picker = control). */
  async attachToWorld(worldName: string): Promise<void> {
    await this.worldPickerCombo.click();
    await this.worldPickerCombo.fill(worldName);
    await this.page.getByRole('option', { name: worldName }).first().click();
  }
}
