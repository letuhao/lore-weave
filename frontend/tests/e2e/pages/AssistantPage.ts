import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

// PoM for the Work Assistant surface (/assistant). On a desktop viewport the home strip renders (the
// mobile dock is the phone variant); the Journal/Memory sheets are addressable Radix dialogs shared by
// both. Covers the QC-plan surfaces: consent (S9), memory + data-rights (S2/S4/S5), autonomous (S10),
// new-epoch (S8), Practice nav (S7). Selectors are the data-testids shipped in the A1–A5 + debt-clear work.
export class AssistantPage {
  readonly page: Page;
  // strip / provisioning
  readonly greeting: Locator;
  readonly consentToggle: Locator;
  // affordances
  readonly openJournal: Locator;
  readonly openMemory: Locator;
  readonly practiceLink: Locator;
  // memory sheet
  readonly memorySheet: Locator;
  readonly memorySearch: Locator;
  readonly memoryList: Locator;
  readonly eraseAllZone: Locator;
  readonly eraseAllOpen: Locator;
  readonly eraseAllConfirm: Locator;
  readonly eraseAllDo: Locator;
  readonly eraseAllCancel: Locator;
  readonly newEpochZone: Locator;
  readonly newEpochOpen: Locator;
  readonly newEpochCancel: Locator;
  // autonomous
  readonly autonomousSettings: Locator;

  constructor(page: Page) {
    this.page = page;
    this.greeting = page.getByTestId('assistant-greeting');
    this.consentToggle = page.getByTestId('assistant-consent-toggle');
    this.openJournal = page.getByTestId('assistant-open-journal');
    this.openMemory = page.getByTestId('assistant-open-memory');
    this.practiceLink = page.getByTestId('assistant-practice-link');
    this.memorySheet = page.getByTestId('memory-sheet');
    this.memorySearch = page.getByTestId('memory-search');
    this.memoryList = page.getByTestId('memory-list');
    this.eraseAllZone = page.getByTestId('memory-erase-all');
    this.eraseAllOpen = page.getByTestId('memory-erase-all-open');
    this.eraseAllConfirm = page.getByTestId('memory-erase-all-confirm');
    this.eraseAllDo = page.getByTestId('memory-erase-all-do');
    this.eraseAllCancel = page.getByTestId('memory-erase-all-cancel');
    this.newEpochZone = page.getByTestId('memory-new-epoch');
    this.newEpochOpen = page.getByTestId('memory-new-epoch-open');
    this.newEpochCancel = page.getByTestId('memory-new-epoch-cancel');
    this.autonomousSettings = page.getByTestId('autonomous-settings');
  }

  /** Navigate to /assistant and wait until provisioning has surfaced the home strip. The chat surface
   *  auto-opens a "new chat" dialog for a fresh session (a full-screen modal that would intercept clicks
   *  on the strip); dismiss it so the assistant home is interactable. */
  async goto(): Promise<void> {
    await this.page.goto('/assistant');
    await expect(this.greeting).toBeVisible({ timeout: 20_000 }); // provisioning is idempotent-on-open
    await this.dismissNewChatDialog();
  }

  async dismissNewChatDialog(): Promise<void> {
    const dismiss = this.page.getByTestId('new-chat-dismiss');
    if (await dismiss.isVisible().catch(() => false)) {
      await dismiss.click();
      await expect(this.page.getByTestId('new-chat-dialog')).toBeHidden();
    }
  }

  /** One autonomous job toggle by kind (eod_distill | weekly_reflection | weekly_rollup | nudge | proactive_nudge). */
  autonomousToggle(kind: string): Locator {
    return this.page.getByTestId(`autonomous-toggle-${kind}`);
  }

  /** Click an autonomous toggle, dismissing the chat dialog first (it re-opens on strip re-renders). */
  async clickAutonomousToggle(kind: string): Promise<void> {
    await this.dismissNewChatDialog();
    await this.autonomousToggle(kind).click();
  }

  async openMemorySheet(): Promise<void> {
    // The chat's new-session dialog can re-open after provisioning re-renders <Chat>; clear it first so
    // its full-screen overlay doesn't intercept the click on the strip.
    await this.dismissNewChatDialog();
    await this.openMemory.click();
    await expect(this.memorySheet).toBeVisible();
  }

  /** Click the "Practice interview" link (dismissing the chat dialog first if it re-opened). */
  async gotoPractice(): Promise<void> {
    await this.dismissNewChatDialog();
    await this.practiceLink.click();
  }

  /** True when a role="switch" element is ON (aria-checked). */
  static async isOn(toggle: Locator): Promise<boolean> {
    return (await toggle.getAttribute('aria-checked')) === 'true';
  }
}
