import type { Page, Locator } from '@playwright/test';

/** Page object for the chapter editor's Compose (Power) panel + the publish
 * affordance the chapter-gate controls. */
export class ChapterComposePanel {
  readonly page: Page;
  readonly composeTab: Locator;
  readonly setupButton: Locator;
  readonly sceneSelect: Locator;
  readonly addScene: Locator;
  readonly markDone: Locator;
  readonly publishButton: Locator;
  readonly modelSelect: Locator;
  readonly reasoningSelect: Locator;
  readonly generate: Locator;
  readonly ghost: Locator;
  readonly accept: Locator;
  readonly critic: Locator;

  constructor(page: Page) {
    this.page = page;
    this.composeTab = page.getByTestId('chapter-righttab-compose');
    this.setupButton = page.getByTestId('composition-setup-button');
    this.sceneSelect = page.getByTestId('composition-scene-select');
    this.addScene = page.getByTestId('composition-add-scene');
    this.markDone = page.getByTestId('composition-mark-done');
    this.publishButton = page.getByTestId('publish-button');
    this.modelSelect = page.getByTestId('composition-model-select');
    this.reasoningSelect = page.getByTestId('compose-reasoning');
    this.generate = page.getByTestId('compose-generate');
    this.ghost = page.getByTestId('compose-ghost');
    this.accept = page.getByTestId('compose-accept');
    this.critic = page.getByTestId('compose-critic');
  }

  async gotoEditor(bookId: string, chapterId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/chapters/${chapterId}/edit`);
  }

  async openComposeTab(): Promise<void> {
    await this.composeTab.click();
  }
}
