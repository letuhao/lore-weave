import type { Page, Locator } from '@playwright/test';

/** Page object for the chapter editor's Compose (Power) panel + the publish
 * affordance the chapter-gate controls. */
export class ChapterComposePanel {
  readonly page: Page;
  readonly workmodeSwitcher: Locator;
  readonly workmodeCompose: Locator;
  readonly setupButton: Locator;
  readonly sceneSelect: Locator;
  readonly addScene: Locator;
  readonly markDone: Locator;
  readonly publishButton: Locator;
  readonly editorialBadge: Locator;
  readonly titleInput: Locator;
  readonly saveButton: Locator;
  readonly modelSelect: Locator;
  readonly reasoningSelect: Locator;
  readonly generate: Locator;
  readonly stop: Locator;
  readonly regenerate: Locator;
  readonly discard: Locator;
  // slice 3 — controlled-auto K-candidate gate
  readonly divergeToggle: Locator;
  readonly candidatesView: Locator;
  readonly candidateCards: Locator;
  readonly candidateUse: Locator;
  readonly candidateEdit: Locator;
  readonly candidateEditBox: Locator;
  readonly candidateEditSave: Locator;
  readonly candidateWinnerBadge: Locator;
  readonly candidatesRegenerate: Locator;
  readonly candidatesReject: Locator;
  readonly needScene: Locator;
  readonly needModel: Locator;
  readonly reasoningBadge: Locator;
  readonly ghost: Locator;
  readonly accept: Locator;
  readonly critic: Locator;
  // sub-tabs
  readonly subtabGrounding: Locator;
  readonly subtabCanon: Locator;
  // grounding
  readonly groundingSignal: Locator;
  readonly groundingWarning: Locator;
  readonly groundingEmptyHint: Locator;
  // canon
  readonly canonInput: Locator;
  readonly canonScope: Locator;
  readonly canonAdd: Locator;
  readonly canonRules: Locator;
  readonly canonArchive: Locator;

  constructor(page: Page) {
    this.page = page;
    // Compose is now a Workmode (dropdown), not a right-panel tab.
    this.workmodeSwitcher = page.getByTestId('workmode-switcher');
    this.workmodeCompose = page.getByTestId('workmode-item-compose');
    this.setupButton = page.getByTestId('composition-setup-button');
    this.sceneSelect = page.getByTestId('composition-scene-select');
    this.addScene = page.getByTestId('composition-add-scene');
    this.markDone = page.getByTestId('composition-mark-done');
    this.publishButton = page.getByTestId('publish-button');
    this.editorialBadge = page.getByTestId('editorial-badge');
    this.titleInput = page.getByTestId('chapter-title-input');
    this.saveButton = page.getByTestId('chapter-save-button');
    this.modelSelect = page.getByTestId('composition-model-select');
    this.reasoningSelect = page.getByTestId('compose-reasoning');
    this.generate = page.getByTestId('compose-generate');
    this.stop = page.getByTestId('compose-stop');
    this.regenerate = page.getByTestId('compose-regenerate');
    this.discard = page.getByTestId('compose-discard');
    // slice 3 — the diverge toggle is a <label>; the checkbox is its <input>.
    this.divergeToggle = page.getByTestId('compose-diverge-toggle').locator('input');
    this.candidatesView = page.getByTestId('candidates-view');
    this.candidateCards = page.getByTestId('candidate-card');
    this.candidateUse = page.getByTestId('candidate-use');
    this.candidateEdit = page.getByTestId('candidate-edit');
    this.candidateEditBox = page.getByTestId('candidate-edit-box');
    this.candidateEditSave = page.getByTestId('candidate-edit-save');
    this.candidateWinnerBadge = page.getByTestId('candidate-winner-badge');
    this.candidatesRegenerate = page.getByTestId('candidates-regenerate');
    this.candidatesReject = page.getByTestId('candidates-reject');
    this.needScene = page.getByTestId('compose-need-scene');
    this.needModel = page.getByTestId('compose-need-model');
    this.reasoningBadge = page.getByTestId('compose-reasoning-badge');
    this.ghost = page.getByTestId('compose-ghost');
    this.accept = page.getByTestId('compose-accept');
    this.critic = page.getByTestId('compose-critic');
    this.subtabGrounding = page.getByTestId('composition-subtab-grounding');
    this.subtabCanon = page.getByTestId('composition-subtab-canon');
    this.groundingSignal = page.getByTestId('composition-grounding-signal');
    this.groundingWarning = page.getByTestId('composition-grounding-warning');
    this.groundingEmptyHint = page.getByTestId('composition-grounding-empty-hint');
    this.canonInput = page.getByTestId('composition-canon-input');
    this.canonScope = page.getByTestId('composition-canon-scope');
    this.canonAdd = page.getByTestId('composition-canon-add');
    this.canonRules = page.getByTestId('composition-canon-rule');
    this.canonArchive = page.getByTestId('composition-canon-archive');
  }

  async gotoEditor(bookId: string, chapterId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/chapters/${chapterId}/edit`);
  }

  /** Pick a model in the shared ModelPicker (W5) — the old native `<select>`
   * became a combobox trigger; options carry `data-model-id`. */
  async selectModel(userModelId: string): Promise<void> {
    await this.modelSelect.locator('[role="combobox"], button').first().click();
    await this.page.locator(`[role="option"][data-model-id="${userModelId}"]`).click();
  }

  async openComposeTab(): Promise<void> {
    await this.workmodeSwitcher.click();
    await this.workmodeCompose.click();
  }

  /** The canon-side editorial status as the badge sees it ('draft' | 'published'),
   * language-agnostic via the data-status attribute. */
  async badgeStatus(): Promise<string | null> {
    return this.editorialBadge.getAttribute('data-status');
  }

  /** Make the chapter dirty by appending to the title, then save and wait for the
   * clean state (Publish re-enables once not dirty). */
  async editTitleAndSave(suffix: string): Promise<void> {
    await this.titleInput.click();
    await this.titleInput.press('End');
    await this.titleInput.pressSequentially(suffix);
    await this.saveButton.click();
  }
}
