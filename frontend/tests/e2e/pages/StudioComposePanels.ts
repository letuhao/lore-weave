import { expect, type Page, type Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';

/**
 * Page object for the S1 Writing-Studio DOCK compose surface: the `scene-compose` draft loop, the
 * `chapter-assemble` loop, and the manuscript `editor` + its inline "Continue from cursor" ghost.
 *
 * These panels REUSE CompositionPanel's testids (compose-*, composition-*, assemble-*, inline-*), so
 * locators are SCOPED under each panel's root (`studio-scene-compose-panel` / `studio-chapter-assemble-panel`
 * / `studio-editor-panel`) to stay unambiguous when several are docked at once. Panels are opened the
 * real-user way — the Command Palette — via StudioPage.openPanel.
 */
export class StudioComposePanels {
  readonly page: Page;
  readonly studio: StudioPage;

  // scene-compose panel
  readonly sceneComposePanel: Locator;
  readonly setupButton: Locator;          // "Set up co-writer" (no Work yet)
  readonly sceneSelect: Locator;
  readonly addScene: Locator;
  readonly markDone: Locator;
  readonly modelSelect: Locator;
  readonly generate: Locator;
  readonly stop: Locator;
  readonly ghost: Locator;
  readonly accept: Locator;
  readonly regenerate: Locator;
  readonly discard: Locator;
  readonly divergeToggle: Locator;
  readonly candidateCards: Locator;
  readonly candidateUse: Locator;
  readonly needModel: Locator;
  readonly adaptButton: Locator;

  // chapter-assemble panel
  readonly assemblePanel: Locator;
  readonly assembleModelSelect: Locator;  // chapter-assemble is a SEPARATE CompositionPanel instance → its own model picker
  readonly assembleModePerScene: Locator;
  readonly assembleModeChapter: Locator;
  readonly generateChapter: Locator;
  readonly stitch: Locator;
  readonly assemblePreview: Locator;
  readonly assembleAccept: Locator;
  readonly assembleRegenerate: Locator;
  readonly assembleReject: Locator;
  readonly assembleError: Locator;

  // editor + inline ghost + publish
  readonly editorPanel: Locator;
  readonly editorContent: Locator;
  readonly inlineContinue: Locator;
  readonly inlineGhostText: Locator;
  readonly inlineAccept: Locator;
  readonly inlineEdit: Locator;
  readonly inlineDiscard: Locator;
  readonly publishButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);

    this.sceneComposePanel = page.getByTestId('studio-scene-compose-panel');
    this.setupButton = this.sceneComposePanel.getByTestId('composition-setup-button');
    this.sceneSelect = this.sceneComposePanel.getByTestId('composition-scene-select');
    this.addScene = this.sceneComposePanel.getByTestId('composition-add-scene');
    this.markDone = this.sceneComposePanel.getByTestId('composition-mark-done');
    this.modelSelect = this.sceneComposePanel.getByTestId('composition-model-select');
    this.generate = this.sceneComposePanel.getByTestId('compose-generate');
    this.stop = this.sceneComposePanel.getByTestId('compose-stop');
    this.ghost = this.sceneComposePanel.getByTestId('compose-ghost');
    this.accept = this.sceneComposePanel.getByTestId('compose-accept');
    this.regenerate = this.sceneComposePanel.getByTestId('compose-regenerate');
    this.discard = this.sceneComposePanel.getByTestId('compose-discard');
    this.divergeToggle = this.sceneComposePanel.getByTestId('compose-diverge-toggle').locator('input');
    this.candidateCards = this.sceneComposePanel.getByTestId('candidate-card');
    this.candidateUse = this.sceneComposePanel.getByTestId('candidate-use');
    this.needModel = this.sceneComposePanel.getByTestId('compose-need-model');
    this.adaptButton = this.sceneComposePanel.getByTestId('compose-adapt');

    this.assemblePanel = page.getByTestId('studio-chapter-assemble-panel');
    this.assembleModelSelect = this.assemblePanel.getByTestId('composition-model-select');
    this.assembleModePerScene = this.assemblePanel.getByTestId('assemble-mode-per_scene');
    this.assembleModeChapter = this.assemblePanel.getByTestId('assemble-mode-chapter');
    this.generateChapter = this.assemblePanel.getByTestId('assemble-generate-chapter');
    this.stitch = this.assemblePanel.getByTestId('assemble-stitch');
    this.assemblePreview = this.assemblePanel.getByTestId('assemble-preview');
    this.assembleAccept = this.assemblePanel.getByTestId('assemble-accept');
    this.assembleRegenerate = this.assemblePanel.getByTestId('assemble-regenerate');
    this.assembleReject = this.assemblePanel.getByTestId('assemble-reject');
    this.assembleError = this.assemblePanel.getByTestId('assemble-error');

    this.editorPanel = page.getByTestId('studio-editor-panel');
    this.editorContent = this.editorPanel.locator('.tiptap-content');
    this.inlineContinue = this.editorPanel.getByTestId('inline-continue');
    this.inlineGhostText = this.editorPanel.getByTestId('inline-ghost-text');
    this.inlineAccept = this.editorPanel.getByTestId('inline-accept');
    this.inlineEdit = this.editorPanel.getByTestId('inline-edit');
    this.inlineDiscard = this.editorPanel.getByTestId('inline-discard');
    this.publishButton = this.editorPanel.getByTestId('publish-button');
  }

  /** Open the studio, deep-linked to a chapter via `?chapter=` — this focuses the manuscript unit
   *  (opens the Editor on that chapter + sets the bus activeChapterId that scene-compose/chapter-
   *  assemble follow) WITHOUT depending on the navigator's tree (which switches to the composition
   *  outline once a Work exists). More deterministic than clicking a navigator row. */
  async gotoStudio(bookId: string, chapterId?: string): Promise<void> {
    const url = chapterId ? `/books/${bookId}/studio?chapter=${chapterId}` : `/books/${bookId}/studio`;
    await this.page.goto(url);
    await this.studio.activity('manuscript').waitFor({ state: 'attached' });
  }

  async openSceneCompose(): Promise<void> {
    await this.studio.openPanel('scene-compose', 'Scene Compose');
    await expect(this.sceneComposePanel).toBeVisible();
  }

  async openChapterAssemble(): Promise<void> {
    await this.studio.openPanel('chapter-assemble', 'Chapter Assemble');
    await expect(this.assemblePanel).toBeVisible();
  }

  async openEditor(): Promise<void> {
    await this.studio.openPanel('editor', 'Editor');
    await expect(this.editorPanel).toBeVisible();
  }

  /** Pick a model in the shared ModelPicker (W5 combobox; options carry data-model-id). */
  async pickModel(userModelId: string): Promise<void> {
    await this.pickModelIn(this.modelSelect, userModelId);
  }

  /** chapter-assemble is a distinct CompositionPanel instance with its OWN model picker — pick there. */
  async pickAssembleModel(userModelId: string): Promise<void> {
    await this.pickModelIn(this.assembleModelSelect, userModelId);
  }

  private async pickModelIn(scope: Locator, userModelId: string): Promise<void> {
    await scope.locator('[role="combobox"], button').first().click();
    await this.page.locator(`[role="option"][data-model-id="${userModelId}"]`).click();
  }

  /** Generate a V0 stream ghost + wait for real prose (poll — model-gated). */
  async generateGhost(timeout = 120_000): Promise<void> {
    await expect(this.generate).toBeEnabled();
    await this.generate.click();
    await expect(this.ghost).toBeVisible({ timeout });
    await expect.poll(async () => (await this.ghost.innerText()).trim().length, { timeout })
      .toBeGreaterThan(20);
    // stream settled → Accept available
    await expect(this.accept).toBeVisible({ timeout });
  }

  async editorText(): Promise<string> {
    return (await this.editorContent.innerText()).trim();
  }
}
