// #04a · Manuscript Rich editor — a THIN VIEW over the Tier-4 unit hoist. It owns no draft state:
// content comes from the hoist's loadedBody, edits flow back via setBody, ⌘S saves. Reuses the
// existing TiptapEditor AS-IS (no fork). Registers the 'editor' tool (agent rack) + the editorBridge
// so the chat's propose_edit (Lane C) can write into the studio editor.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { compositionApi } from '@/features/composition/api';
import type { IDockviewPanelProps } from 'dockview-react';
import { TiptapEditor, type TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import { registerEditorTarget } from '@/features/chat/context/editorBridge';
import { useAuth } from '@/auth';
import { useGrammarEnabled } from '@/hooks/useGrammarCheck';
import { useFocusMode } from '@/features/composition/hooks/useFocusMode';
import { useMentionHeatmap } from '@/features/composition/hooks/useMentionHeatmap';
import { useProvenance } from '@/features/composition/hooks/useProvenance';
import { ProvenanceToolbar } from '@/features/composition/components/ProvenanceToolbar';
import { ProvenanceTag } from '@/features/composition/components/ProvenanceTag';
import { SelectionToolbar } from '@/features/composition/components/SelectionToolbar';
import { InlineAiLayer } from '@/features/composition/components/InlineAiLayer';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { aiModelsApi } from '@/features/ai-models/api';
import { glossaryApi } from '@/features/glossary/api';
import type { EntityNameEntry } from '@/features/glossary/types';
import { GlossaryTooltip } from '@/components/editor/GlossaryTooltip';
import { GlossaryAutocomplete } from '@/components/editor/GlossaryAutocomplete';
import { useGlossaryQuickCreate } from '@/components/editor/useGlossaryQuickCreate';
import { usePopoutInsertRelay } from '@/features/composition/hooks/usePopoutInsertRelay';
import { onPasteToEditor } from '@/features/chat/utils/pasteToEditor';
import { useIsMobile } from '@/hooks/useIsMobile';
import { cn } from '@/lib/utils';
import { useStudioHost, useRegisterStudioTool, useStudioBusSelector } from '../host/StudioHostProvider';
import { useManuscriptUnit } from '../manuscript/unit/ManuscriptUnitProvider';
import { useChapterDoor } from '../manuscript/useChapterDoor';
import { useManuscriptCheckpoints } from '../manuscript/unit/useManuscriptCheckpoints';
import { ManuscriptCheckpoints } from '../manuscript/unit/ManuscriptCheckpoints';
import { SceneRail } from '../manuscript/SceneRail';
import { RevisionHistorySection } from './RevisionHistorySection';
import { EditorPublishGate } from './EditorPublishGate';
import type { StudioToolRegistration } from '../host/types';

export function EditorPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { bookId } = host;
  const unit = useManuscriptUnit();
  // M3 (F2) — the empty state must not dead-end a newcomer: offer the same "start writing" door the
  // Plan Hub / rail use (create a chapter + open it here), not just "go find a chapter that isn't there".
  const chapterDoor = useChapterDoor(bookId);
  // #16 1.2 — wraps the hoist's applyProposedEdit so every AI-apply captures a pre-edit
  // restore point BEFORE writing. The wrapped function (not unit.applyProposedEdit directly)
  // is what gets handed to registerEditorTarget below — same seam, now checkpoint-aware.
  const checkpoints = useManuscriptCheckpoints(bookId, unit);
  const localRef = useRef<TiptapEditorHandle | null>(null);
  const editorRef = unit?.editorRef ?? localRef;
  // #12 M-C — Scene Rail visibility: null = auto (open when scenes exist), boolean = user choice.
  const [railChoiceState, setRailChoiceState] = useState<boolean | null>(null);
  // #16 Phase 4 (M6) — must sit above the `!unit || !chapterId` early return below (Rules of
  // Hooks: every hook this component calls must run on every render, chapter-loaded or not).
  const isMobile = useIsMobile();
  // #16 2.1/2.2/2.3 — editor-craft toggles ported from the legacy ChapterEditorPage. Each is a
  // pure prop-thread into the shared TiptapEditor (grammar/focus) or a ref-push effect (heatmap) —
  // no new editor capability, just wiring the host was missing (see spec 16 Phase 2 kickoff audit).
  const { accessToken } = useAuth();
  const [grammarEnabled, setGrammarEnabled] = useGrammarEnabled();
  const { focusMode, toggle: toggleFocus } = useFocusMode();
  const [heatmapEnabled, setHeatmapEnabled] = useState(false);
  // #16 2.4 — glossary inline decoration + `[[` autocomplete.
  const [glossaryEnabled, setGlossaryEnabled] = useState(true);
  const [glossaryEntities, setGlossaryEntities] = useState<EntityNameEntry[]>([]);
  // Scoped to THIS panel's own editor container (a querySelector against `document` would grab
  // whichever chapter tab's `.tiptap-content` happens to be first in the DOM — the same
  // multi-instance landmine flagged for item #10's upload-context singleton).
  const editorContainerRef = useRef<HTMLDivElement | null>(null);
  const [editorEl, setEditorEl] = useState<HTMLElement | null>(null);
  // D-S5-DERIVATIVE-MANUSCRIPT-FORK — two-step confirm for merging a forked chapter into canon.
  const [mergeConfirm, setMergeConfirm] = useState(false);
  const [merging, setMerging] = useState(false);

  const label = t('panels.editor.title', { defaultValue: 'Editor' });
  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId: 'editor',
    label,
    paletteCommand: t('palette.openPanel', { name: label, defaultValue: 'Studio: Open Editor' }),
    commandId: 'studio.openPanel.editor',
    description: t('panels.editor.desc', { defaultValue: 'Manuscript editor' }),
    mcpToolPrefixes: ['book_'],
  }), [t, label]);
  useRegisterStudioTool(registration);

  // Self-title the dock tab from the localized label. openPanel sets the title at addPanel time,
  // before this panel mounts — so an agent/navigator open (no catalog title opt) shows the raw
  // 'editor' id until the panel claims its own title here (also keeps it correct across a locale swap).
  useEffect(() => {
    props.api.setTitle(label);
  }, [props.api, label]);

  const chapterId = unit?.state.chapterId ?? null;

  // Register the studio editor as the propose_edit write-back target (Lane C). Cleared on unmount
  // / chapter change so a stale handle never receives a write. #16 P1: also hand over the
  // Tier-4 hoist's own applyProposedEdit action — ProposeEditCard prefers it over reaching into
  // the raw handle directly (same underlying write, now hoist-owned per spec 08/09). #16 1.2:
  // the CHECKPOINT-WRAPPED version, not unit.applyProposedEdit directly — same signature, captures
  // a pre-edit restore point on every successful write before delegating.
  const applyProposedEdit = checkpoints.applyProposedEdit;
  useEffect(() => {
    if (!chapterId || !applyProposedEdit) return;
    registerEditorTarget({ bookId, chapterId, handleRef: editorRef, applyProposedEdit });
    return () => registerEditorTarget(null);
  }, [bookId, chapterId, editorRef, applyProposedEdit]);

  // #16 2.8 — prose accepted in a popped-out Compose window has no editor of its own; relay
  // lands here via the SAME checkpoint-wrapped seam as the docked propose_edit Apply path, so
  // a popout-relayed insert still captures a Checkpoints restore point. /review-impl HIGH fix:
  // return the real result so usePopoutInsertRelay can ack it back to the popout — this fires
  // only while THIS EditorPanel is still subscribed to the popout's (bookId, chapterId) channel
  // (the effect re-keys on chapterId), so a chapter switch here correctly stops acking instead
  // of silently swallowing the popout's edit.
  usePopoutInsertRelay(bookId, chapterId ?? '', (text, model) => checkpoints.applyProposedEdit({
    operation: 'insert_at_cursor',
    text,
    provenance: { source: 'ai', status: 'unreviewed', model: model ?? null, ts: new Date().toISOString() },
  }));

  // D-COMPOSE-SEND-TO-EDITOR gap fix — Compose's "Send to Editor" (message menu + Output card)
  // fired this event with NO listener anywhere in the codebase (checked: not even the legacy
  // ChapterEditorPage ever wired it — a dead button since it was authored, not a regression).
  // Studio's 'editor' dock panel is a SINGLETON (one hoisted ManuscriptUnitProvider per book,
  // retargeted by chapter switch — unlike per-chapter multi-instance panels like json-editor), so
  // a plain window-scoped listener is safe: exactly one EditorPanel is ever mounted to receive it.
  // Same checkpoint-wrapped seam as the popout relay above, so a Send-to-Editor insert is also
  // restorable via Checkpoints.
  useEffect(() => onPasteToEditor(({ text }) => {
    checkpoints.applyProposedEdit({
      operation: 'insert_at_cursor',
      text,
      provenance: { source: 'ai', status: 'unreviewed', model: null, ts: new Date().toISOString() },
    });
  }), [checkpoints]);

  // #16 2.7 — wire this panel's own upload context onto the editor instance it owns
  // (editor.storage.mediaUpload, NOT a module singleton — each dockview EditorPanel tab gets
  // its own copy so concurrently-open chapters never cross-attribute uploads/history).
  useEffect(() => {
    if (!accessToken || !bookId || !chapterId) return;
    const openHistory = (blockId: string, blockTitle: string, mediaSrc: string | null) => {
      host.openPanel(`media-version-history:${chapterId}:${blockId}`, {
        component: 'media-version-history',
        title: `${t('panels.media-version-history.title', { defaultValue: 'Version History' })} · ${blockTitle}`,
        params: { bookId, chapterId, blockId, blockTitle, currentMediaUrl: mediaSrc },
      });
    };
    editorRef.current?.setUploadContext({
      token: accessToken, bookId, chapterId, onOpenHistory: openHistory, onOpenVideoHistory: openHistory,
    });
    return () => editorRef.current?.setUploadContext(null);
  }, [accessToken, bookId, chapterId, editorRef, host, t]);

  // #16 2.3 — mention heatmap: windowed to THIS chapter's per-chapter mention_count (glossary),
  // tinting the canonical name AND every alias so alias-heavy (CJK) prose still lights up.
  const heatmap = useMentionHeatmap(bookId, chapterId ?? undefined, accessToken);
  useEffect(() => {
    const terms = (heatmap.data ?? []).flatMap((h) => [h.name, ...h.aliases].map((name) => ({ name, band: h.band })));
    editorRef.current?.setHeatmapTerms(terms);
  }, [heatmap.data, editorRef]);
  useEffect(() => {
    editorRef.current?.setHeatmapEnabled(heatmapEnabled);
  }, [heatmapEnabled, editorRef]);

  // #16 2.4 — load once per (book, token); push into the editor via the existing ref methods.
  useEffect(() => {
    if (!accessToken || !bookId) return;
    let cancelled = false;
    glossaryApi.listEntityNames(bookId, accessToken).then((entries) => {
      if (cancelled) return;
      setGlossaryEntities(entries);
      editorRef.current?.setGlossaryEntities(entries);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [accessToken, bookId, editorRef]);
  useEffect(() => {
    editorRef.current?.setGlossaryEnabled(glossaryEnabled);
  }, [glossaryEnabled, editorRef]);
  // Re-capture the container's own `.tiptap-content` node after the editor (re)mounts —
  // chapter switches remount the underlying ProseMirror view.
  useEffect(() => {
    const timer = setTimeout(() => {
      setEditorEl(editorContainerRef.current?.querySelector<HTMLElement>('.tiptap-content') ?? null);
    }, 100);
    return () => clearTimeout(timer);
  }, [chapterId]);
  // #16 2.6 — Selection Toolbar (Rewrite/Expand/Describe) + Inline AI layer (Continue from
  // cursor). Both render-prop slots already exist on TiptapEditor untouched — the missing piece
  // was resolving projectId/sceneId/default-model, not new editor capability.
  const workResolution = useWorkResolution(bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(bookId, accessToken);
  // EC-3d: the ACTIVE Work (per-book pref, else canonical) so the editor follows a
  // "Switch to" a dị bản instead of always loading canon.
  const composeWork = resolveActiveWork(workResolution.data, activeWorkId);
  const composeProjectId = composeWork?.project_id ?? null;
  // D-S5-DERIVATIVE-MANUSCRIPT-FORK — promote THIS forked chapter into canon. Two-step confirm
  // (the first click arms it). The branch keeps its own version; only canon is overwritten.
  const handleMergeToCanon = async () => {
    if (!mergeConfirm) { setMergeConfirm(true); return; }
    if (!composeProjectId || !chapterId) return;
    setMerging(true);
    try {
      await compositionApi.mergeWorkChapterToCanon(composeProjectId, chapterId, accessToken);
      toast.success(t('editor.mergeDone', { defaultValue: 'Merged into canon — the branch keeps its own version.' }));
      setMergeConfirm(false);
    } catch (e) {
      const conflict = (e as { status?: number }).status === 409;
      toast[conflict ? 'warning' : 'error'](conflict
        ? t('editor.mergeConflict', { defaultValue: 'Canon changed since — reopen the chapter and merge again.' })
        : t('editor.mergeFailed', { defaultValue: 'Could not merge — try again.' }));
    } finally { setMerging(false); }
  };
  const chatModels = useQuery({
    queryKey: ['composition', 'chat-models'],
    queryFn: () => aiModelsApi.listUserModels(accessToken!, { capability: 'chat' }),
    enabled: !!accessToken,
    select: (d) => d.items.filter((m) => m.is_active),
  });
  const persistedDefaultModel =
    typeof composeWork?.settings?.default_model_ref === 'string' ? composeWork.settings.default_model_ref : null;
  const soleChatModel = chatModels.data?.length === 1 ? chatModels.data[0].user_model_id : null;
  const composeDefaultModel = persistedDefaultModel ?? soleChatModel;
  const composeDefaultModelMeta = chatModels.data?.find((m) => m.user_model_id === composeDefaultModel);
  // Same scene the Scene Rail highlights (studio bus, not a second local selection) — falls
  // back to this chapter's first scene so Continue works before the writer ever touches the rail.
  const activeSceneId = useStudioBusSelector((s) => s.activeSceneId);
  const effectiveSceneId = activeSceneId || unit?.state.scenes[0]?.id || null;

  // Insert via a real ProseMirror transaction (insertAtCursor, already on the handle) instead of
  // legacy's document.execCommand('insertText', ...) — execCommand fires a synthetic DOM input
  // event outside Tiptap's own transaction pipeline, which risks desyncing the hoist's dirty-state
  // tracking (setBody's addTextSnapshots guard). Note: like legacy, this does NOT delete the typed
  // `[[query` trigger text (GlossaryAutocomplete's from/to are DOM-walked text offsets, not real
  // ProseMirror positions a range-replace could trust) — inherited limitation, not a new regression.
  const handleInsertGlossaryEntity = (_from: number, _to: number, name: string) => {
    editorRef.current?.insertAtCursor(name);
  };

  // S-10 O7 (PO D-d) — the `[[`-create flow: typing `[[NewName` + picking a kind creates the KG entity
  // and inserts it (same insert path as picking an existing one). undefined until the Work's project
  // resolves, so GlossaryAutocomplete hides "＋ Create" rather than offering a create that would fail.
  const handleCreateGlossaryEntity = useGlossaryQuickCreate(
    composeProjectId,
    accessToken,
    (name) => handleInsertGlossaryEntity(0, 0, name),
  );

  // #16 2.5 — AI-provenance review UI. Mark-writing already works (Lane-C applyProposedEdit
  // threads ProvenanceAttrs) — this is purely the missing review affordance (unreviewed count,
  // toggle-visible, mark-all-reviewed). docJson drives the recompute on every doc mutation.
  const provenance = useProvenance(editorRef, unit?.state.workingBody ?? unit?.state.loadedBody ?? null);

  // ⌘S / Ctrl+S → save the unit (never the browser "save page").
  useEffect(() => {
    if (!unit) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void unit.save();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [unit]);

  if (!unit || !chapterId) {
    return (
      <div data-testid="studio-editor-panel" className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <button
          type="button"
          data-testid="editor-empty-start-chapter"
          disabled={!chapterDoor.startNewChapter || chapterDoor.creating}
          onClick={() => chapterDoor.startNewChapter?.()}
          className="rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition hover:brightness-105 disabled:opacity-50"
        >
          {chapterDoor.creating
            ? t('editor.startingChapter', { defaultValue: 'Creating…' })
            : `＋  ${t('editor.startFirstChapter', { defaultValue: 'Start your first chapter' })}`}
        </button>
        <p className="text-xs text-muted-foreground">
          {t('editor.empty', { defaultValue: 'Select a chapter in the manuscript navigator to edit it here.' })}
        </p>
      </div>
    );
  }

  const { state, isDirty, save, setBody } = unit;
  const hasScenes = state.scenes.length > 0;
  // #12 M-C — the Scene Rail (metadata-first scene layer). Auto-shows when the chapter HAS
  // scenes; the user can toggle it; an explicit choice wins over the auto-default.
  // #16 Phase 4 (M6) — on a narrow viewport the rail's fixed w-56 leaves too little room for
  // prose (a real chapter's words wrapped one-per-line in live testing), so the auto-default
  // starts closed on mobile; the toggle button still opens it on demand.
  const railChoice = railChoiceState;
  const railOpen = railChoice ?? (hasScenes && !isMobile);

  return (
    <div data-testid="studio-editor-panel" className="flex h-full min-h-0 flex-col">
      {/* D-S5-DERIVATIVE-MANUSCRIPT-FORK — a dị bản now has its OWN manuscript per chapter
          (work-scoped draft; the ManuscriptUnitProvider routes load/save there). Signal the real
          isolation state — inherited (still mirrors canon, editing forks it) vs forked (isolated) —
          and offer Merge-to-canon on a forked chapter. Canon is never touched by editing here. */}
      {unit?.state.isDerivative ? (
        <div
          data-testid="studio-editor-derivative-guard"
          className="flex flex-shrink-0 flex-wrap items-center gap-1.5 border-b border-amber-300 bg-amber-50 px-3 py-1 text-[11px] text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200"
        >
          <span data-testid="studio-editor-fork-state">
            ⑂ {unit.state.forked
              ? t('editor.derivativeForked', { defaultValue: "On a what-if version — this chapter is FORKED, isolated from canon. Edits save to the branch; canon stays untouched." })
              : t('editor.derivativeInherit', { defaultValue: "On a what-if version — this chapter still mirrors canon. Editing here FORKS it into the branch (canon stays untouched)." })}
          </span>
          {unit.state.forked && (
            <button
              type="button"
              data-testid="studio-editor-merge-canon"
              disabled={merging}
              onClick={handleMergeToCanon}
              onBlur={() => setMergeConfirm(false)}
              className="ml-auto rounded border border-amber-400 px-1.5 py-0.5 hover:bg-amber-100 disabled:opacity-50 dark:hover:bg-amber-900/40"
            >
              {merging
                ? t('editor.merging', { defaultValue: 'Merging…' })
                : mergeConfirm
                  ? t('editor.mergeConfirm', { defaultValue: 'Confirm — overwrite canon' })
                  : t('editor.mergeToCanon', { defaultValue: 'Merge to canon' })}
            </button>
          )}
        </div>
      ) : null}
      <div className="flex h-7 flex-shrink-0 items-center gap-2 overflow-x-auto whitespace-nowrap border-b px-3 text-[11px] text-muted-foreground">
        <span data-testid="studio-editor-dirty" className={isDirty ? 'text-warning' : 'text-muted-foreground/60'}>
          {isDirty ? t('editor.unsaved', { defaultValue: '● unsaved' }) : t(`editor.state.${state.saveState}`, { defaultValue: state.saveState })}
        </span>
        {/* #16 2.1/2.2/2.3 — editor-craft toggles (grammar/focus/heatmap), ported from the legacy
            chapter editor. Persisted per-device (localStorage), not per-chapter Tier-4 state. */}
        <button
          type="button"
          data-testid="studio-editor-toggle-grammar"
          onClick={() => setGrammarEnabled(!grammarEnabled)}
          className={cn('ml-auto rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground', grammarEnabled && 'text-primary')}
        >
          {t('editor.grammar', { defaultValue: 'Grammar' })}
        </button>
        <button
          type="button"
          data-testid="studio-editor-toggle-heatmap"
          onClick={() => setHeatmapEnabled((v) => !v)}
          className={cn('rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground', heatmapEnabled && 'text-primary')}
        >
          {t('editor.heatmap', { defaultValue: 'Heatmap' })}
        </button>
        {/* #16 2.4 gap fix — glossaryEnabled existed but had no visible control; defaulted on
            with no way for the user to turn it off (e.g. while proofreading raw prose). */}
        <button
          type="button"
          data-testid="studio-editor-toggle-glossary"
          onClick={() => setGlossaryEnabled((v) => !v)}
          className={cn('rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground', glossaryEnabled && 'text-primary')}
        >
          {t('editor.glossary', { defaultValue: 'Glossary' })}
        </button>
        <button
          type="button"
          data-testid="studio-editor-toggle-focus"
          onClick={toggleFocus}
          className={cn('rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground', focusMode && 'text-primary')}
        >
          {t('editor.focus', { defaultValue: 'Focus' })}
        </button>
        <button
          type="button"
          data-testid="studio-editor-toggle-scenes"
          onClick={() => setRailChoiceState(!railOpen)}
          className={cn('rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground', railOpen && 'text-primary')}
        >
          {t('sceneRail.toggle', { defaultValue: 'Scenes' })} {hasScenes ? state.scenes.length : ''}
        </button>
        {/* #12 S4/J1 — the "option" editor duality: open THIS unit in the generic json-editor.
            Per-resource dock id (J1 multi-instance): each chapter gets its OWN tab; re-opening
            the same chapter focuses it. Same shared document — edits mirror live. */}
        <button
          type="button"
          data-testid="studio-editor-open-json"
          onClick={() => host.openPanel(`json-editor:loreweave.manuscript-unit.v1:${chapterId}`, {
            component: 'json-editor',
            title: `${t('panels.json-editor.title', { defaultValue: 'JSON' })} · ${chapterId.slice(0, 8)}`,
            params: { docType: 'loreweave.manuscript-unit.v1', resourceId: chapterId },
          })}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground"
        >
          {t('jsonEditor.openAs', { defaultValue: 'Open as JSON' })}
        </button>
        {/* #16 2.11 — read-only original (untranslated) source viewer, opened per-chapter. */}
        <button
          type="button"
          data-testid="studio-editor-open-original-source"
          onClick={() => host.openPanel(`original-source:${chapterId}`, {
            component: 'original-source',
            title: `${t('panels.original-source.title', { defaultValue: 'Original Source' })} · ${chapterId.slice(0, 8)}`,
            params: { bookId, chapterId },
          })}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground"
        >
          {t('panels.original-source.title', { defaultValue: 'Original Source' })}
        </button>
        {/* D-CHAPTER-READER-MODE — one-click "read this chapter" entry point, reusing the
            EXISTING book-reader singleton panel (14_utility_panels.md Phase C4) rather than
            forking a second reader implementation. It's a params-retargeting singleton — opening
            it with THIS chapter just retargets whatever reader tab is already open (or creates
            one), same as a Books-panel row click does for another book. */}
        <button
          type="button"
          data-testid="studio-editor-open-reader"
          onClick={() => host.openPanel('book-reader', { params: { bookId, chapterId } })}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground"
        >
          {t('panels.book-reader.title', { defaultValue: 'Reader' })}
        </button>
        {/* #16 Phase 3 — one-click Translate quick-access for the currently-open chapter
            (legacy's Workmode-tab convenience), opens the version-management panel scoped to
            this chapter instead of requiring a trip through the Translation matrix. */}
        <button
          type="button"
          data-testid="studio-editor-open-translate"
          // D11 (spec 29): open the BARE `translation-versions` id — the params-retargeting
          // singleton — the same id the `translation` panel uses, so the editor and the matrix
          // share ONE dock tab (retargeted per open) instead of minting a per-chapter override tab.
          onClick={() => host.openPanel('translation-versions', { params: { chapterId } })}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground"
        >
          {t('editor.translate', { defaultValue: 'Translate' })}
        </button>
        <button
          type="button"
          data-testid="studio-editor-save"
          onClick={() => void save()}
          disabled={!isDirty || state.saveState === 'saving'}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground disabled:opacity-40"
        >
          {t('editor.save', { defaultValue: 'Save' })} <span className="font-mono text-[10px]">⌘S</span>
        </button>
        {/* #16 1.4 — Publish Gate, reused as-is from the legacy chapter editor (DOCK-2, no fork). */}
        <div className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
        <EditorPublishGate bookId={bookId} chapterId={chapterId} draftVersion={state.version} dirty={isDirty} />
      </div>
      {/* #16 1.2 — Checkpoints strip (pre-edit restore points for every AI apply on this chapter). */}
      <ManuscriptCheckpoints
        checkpoints={checkpoints.visibleCheckpoints}
        isDirty={isDirty}
        onRestore={checkpoints.restore}
      />
      {/* #16 2.5 — self-hides when there's nothing unreviewed and the underlay is already on. */}
      <div className="px-3 pt-1">
        <ProvenanceToolbar
          visible={provenance.visible}
          unreviewedCount={provenance.unreviewedCount}
          onToggleVisible={provenance.toggleVisible}
          onMarkAllReviewed={provenance.markAllReviewed}
        />
      </div>
      <ProvenanceTag />
      <div className="flex min-h-0 flex-1">
        <div ref={editorContainerRef} className="min-h-0 min-w-0 flex-1 overflow-auto">
          <TiptapEditor
            ref={editorRef}
            content={state.loadedBody}
            onUpdate={(json, text) => setBody(json, text)}
            grammarEnabled={grammarEnabled}
            focusMode={focusMode}
            selectionMenu={composeProjectId
              ? (ed) => <SelectionToolbar editor={ed} projectId={composeProjectId} sceneContext={effectiveSceneId} token={accessToken} />
              : undefined}
            aiLayer={composeProjectId
              ? (ed) => (
                <InlineAiLayer
                  editor={ed}
                  projectId={composeProjectId}
                  sceneId={effectiveSceneId}
                  modelRef={composeDefaultModel ?? null}
                  modelKind={composeDefaultModelMeta?.provider_kind}
                  modelName={composeDefaultModelMeta?.provider_model_name}
                  token={accessToken}
                />
              )
              : undefined}
          />
        </div>
        {/* #16 2.2 — focus mode hides the flanking panels (matches legacy's side-panel-hiding
            behavior) so the writer's attention stays on the manuscript. */}
        {!focusMode && railOpen && <SceneRail />}
        {/* #16 1.3 — Revision History, a self-toggling right-edge strip (reads the hoist itself). */}
        {!focusMode && <RevisionHistorySection />}
      </div>
      {/* #16 2.4 — glossary hover tooltip + `[[` autocomplete, scoped to this panel's own editor. */}
      {glossaryEnabled && <GlossaryTooltip bookId={bookId} />}
      {/* S-10 O7 — the `[[`-create flow is now wired (onCreateNew). It's undefined until the Work's
          project resolves, so GlossaryAutocomplete still HIDES "＋ Create" rather than offering a
          create that would fail — the 2026-07-17 audit's no-dead-affordance rule still holds. */}
      {glossaryEnabled && (
        <GlossaryAutocomplete
          entities={glossaryEntities}
          editorEl={editorEl}
          onInsertEntity={handleInsertGlossaryEntity}
          onCreateNew={handleCreateGlossaryEntity}
        />
      )}
    </div>
  );
}
