import { expect, type Page, type Locator } from '@playwright/test';
import { StudioPage } from './StudioPage';

/**
 * Page object for co-writing ONE chapter in the Writing Studio: the `scene-compose` dock panel
 * (scene picker, model/effort pickers, generate/diverge/accept loop, critic, divergence wizard), the
 * `editor` dock panel (manuscript body, Save, the Publish gate + editorial badge), and the two panels
 * that home what used to be the compose sub-tabs — Grounding (inside `scene-inspector`) and Canon
 * rules (`quality-canon-rules`).
 *
 * The Studio is the only writing surface: `/books/:bookId/chapters/:chapterId/edit` is a redirect to
 * `/books/:bookId/studio?chapter=:chapterId`. The Studio panels reuse CompositionPanel's testids, so
 * every locator is SCOPED under its panel root to stay unambiguous with several panels docked. The
 * panels share one dock group, so only the active tab is in the DOM's visible tree — `showEditor()` /
 * `openComposeTab()` bring the panel forward the way a user does, through the Command Palette.
 */
export class ChapterComposePanel {
  readonly page: Page;
  readonly studio: StudioPage;
  // scene-compose panel
  readonly sceneComposePanel: Locator;
  readonly setupButton: Locator;
  readonly sceneSelect: Locator;
  readonly addScene: Locator;
  readonly markDone: Locator;
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
  readonly divergenceLaunch: Locator;
  // editor panel
  readonly editorPanel: Locator;
  readonly editorContent: Locator;
  readonly saveButton: Locator;
  readonly dirtyIndicator: Locator;
  readonly publishButton: Locator;
  readonly editorialBadge: Locator;
  // grounding (scene-inspector panel)
  readonly sceneBrowserPanel: Locator;
  readonly sceneInspectorPanel: Locator;
  readonly groundingSignal: Locator;
  readonly groundingWarning: Locator;
  readonly groundingEmptyHint: Locator;
  // canon rules (quality-canon-rules panel)
  readonly canonRulesPanel: Locator;
  readonly canonInput: Locator;
  readonly canonScope: Locator;
  readonly canonAdd: Locator;
  readonly canonRules: Locator;
  readonly canonArchive: Locator;

  constructor(page: Page) {
    this.page = page;
    this.studio = new StudioPage(page);

    const sc = page.getByTestId('studio-scene-compose-panel');
    this.sceneComposePanel = sc;
    this.setupButton = sc.getByTestId('composition-setup-button');
    this.sceneSelect = sc.getByTestId('composition-scene-select');
    this.addScene = sc.getByTestId('composition-add-scene');
    this.markDone = sc.getByTestId('composition-mark-done');
    this.modelSelect = sc.getByTestId('composition-model-select');
    // The reasoning control is the shared AI-task EffortSelect -- a <button> that opens a
    // role="menu" (ComposeView.tsx, EffortSelect.tsx); setReasoning() picks the level.
    this.reasoningSelect = sc.getByTestId('effort-select');
    this.generate = sc.getByTestId('compose-generate');
    this.stop = sc.getByTestId('compose-stop');
    this.regenerate = sc.getByTestId('compose-regenerate');
    this.discard = sc.getByTestId('compose-discard');
    // the diverge toggle is a <label>; the checkbox is its <input>.
    this.divergeToggle = sc.getByTestId('compose-diverge-toggle').locator('input');
    this.candidatesView = sc.getByTestId('candidates-view');
    this.candidateCards = sc.getByTestId('candidate-card');
    this.candidateUse = sc.getByTestId('candidate-use');
    this.candidateEdit = sc.getByTestId('candidate-edit');
    this.candidateEditBox = sc.getByTestId('candidate-edit-box');
    this.candidateEditSave = sc.getByTestId('candidate-edit-save');
    this.candidateWinnerBadge = sc.getByTestId('candidate-winner-badge');
    this.candidatesRegenerate = sc.getByTestId('candidates-regenerate');
    this.candidatesReject = sc.getByTestId('candidates-reject');
    this.needScene = sc.getByTestId('compose-need-scene');
    this.needModel = sc.getByTestId('compose-need-model');
    this.reasoningBadge = sc.getByTestId('compose-reasoning-badge');
    this.ghost = sc.getByTestId('compose-ghost');
    this.accept = sc.getByTestId('compose-accept');
    // The critic result shows inline in the scene-compose panel, where the author accepted
    // (CompositionPanel in solo mode never defers it to a separate critic slot).
    this.critic = sc.getByTestId('compose-critic');
    this.divergenceLaunch = sc.getByTestId('divergence-launch');

    const ed = page.getByTestId('studio-editor-panel');
    this.editorPanel = ed;
    this.editorContent = ed.locator('.tiptap-content');
    this.saveButton = ed.getByTestId('studio-editor-save');
    this.dirtyIndicator = ed.getByTestId('studio-editor-dirty');
    this.publishButton = ed.getByTestId('publish-button');
    this.editorialBadge = ed.getByTestId('editorial-badge');

    this.sceneBrowserPanel = page.getByTestId('studio-scene-browser-panel');
    const si = page.getByTestId('studio-scene-inspector-panel');
    this.sceneInspectorPanel = si;
    this.groundingSignal = si.getByTestId('composition-grounding-signal');
    this.groundingWarning = si.getByTestId('composition-grounding-warning');
    this.groundingEmptyHint = si.getByTestId('composition-grounding-empty-hint');

    const cr = page.getByTestId('studio-quality-canon-rules-panel');
    this.canonRulesPanel = cr;
    this.canonInput = cr.getByTestId('composition-canon-input');
    this.canonScope = cr.getByTestId('composition-canon-scope');
    this.canonAdd = cr.getByTestId('composition-canon-submit');
    this.canonRules = cr.getByTestId('composition-canon-rule');
    this.canonArchive = cr.getByTestId('composition-canon-archive');
  }

  /** Open the chapter in the Writing Studio via its `?chapter=` deep link — this focuses the
   *  manuscript unit (the Editor opens on the chapter, and scene-compose follows it) — and wait
   *  until the Editor has LOADED the chapter (Save exists only past the loaded gate). */
  async gotoStudio(bookId: string, chapterId: string): Promise<void> {
    await this.page.goto(`/books/${bookId}/studio?chapter=${chapterId}`);
    await this.studio.activity('manuscript').waitFor({ state: 'attached' });
    await expect(this.saveButton).toBeVisible({ timeout: 20_000 });
  }

  /** Pick a model in the shared ModelPicker (W5) — a combobox trigger; options carry
   *  `data-model-id`. */
  async selectModel(userModelId: string): Promise<void> {
    await this.modelSelect.locator('[role="combobox"], button').first().click();
    await this.page.locator(`[role="option"][data-model-id="${userModelId}"]`).click();
  }

  /** Set the reasoning/effort level. The control is a button + role="menu", so this opens it and
   *  picks the option; the level vocabulary is off|low|medium|high|auto
   *  (src/components/ai-task/effort.ts). */
  async setReasoning(level: 'off' | 'low' | 'medium' | 'high' | 'auto'): Promise<void> {
    await this.reasoningSelect.click();
    await this.page.getByTestId(`effort-select-opt-${level}`).click();
  }

  /** Open (or bring forward) the Scene Compose dock panel via the Command Palette. */
  async openComposeTab(): Promise<void> {
    await this.studio.openPanel('scene-compose', 'Scene Compose');
    await expect(this.sceneComposePanel).toBeVisible();
  }

  /** Bring the Editor dock panel (body, Save, Publish, editorial badge) forward via the palette. */
  async showEditor(): Promise<void> {
    await this.studio.openPanel('editor', 'Editor');
    await expect(this.saveButton).toBeVisible();
  }

  /** Grounding for a scene: select the scene the real way (Scene Browser row → the bus opens the
   *  Scene Inspector, whose Grounding section runs the packer for that scene). */
  async openGroundingForScene(sceneTitle: string): Promise<void> {
    await this.studio.openPanel('scene-browser', 'Scene Browser');
    await expect(this.sceneBrowserPanel).toBeVisible();
    await this.sceneBrowserPanel.getByTestId('scene-browser-row').filter({ hasText: sceneTitle }).first().click();
    await expect(this.sceneInspectorPanel).toBeVisible({ timeout: 10_000 });
  }

  /** Open the Canon Rules panel (the write half of Quality → Canon). */
  async openCanonRules(): Promise<void> {
    await this.studio.openPanel('quality-canon-rules', 'Canon Rules');
    await expect(this.canonRulesPanel).toBeVisible({ timeout: 10_000 });
  }

  /** The canon-side editorial status as the badge sees it ('draft' | 'published'),
   * language-agnostic via the data-status attribute. */
  async badgeStatus(): Promise<string | null> {
    return this.editorialBadge.getAttribute('data-status');
  }

  /** Make the chapter dirty by typing at the end of the manuscript body (no save). The Studio
   *  editor has no chapter-title field; the body is the chapter's editable draft. */
  async dirtyBody(suffix: string): Promise<void> {
    await this.editorContent.click();
    await this.page.keyboard.press('ControlOrMeta+End');
    await this.page.keyboard.type(suffix);
    await expect(this.saveButton).toBeEnabled();
  }

  /** Edit the manuscript body, then Save (Publish re-enables once not dirty). */
  async editBodyAndSave(suffix: string): Promise<void> {
    await this.dirtyBody(suffix);
    await this.saveButton.click();
  }
}
