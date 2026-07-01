// #04a · Manuscript Rich editor — a THIN VIEW over the Tier-4 unit hoist. It owns no draft state:
// content comes from the hoist's loadedBody, edits flow back via setBody, ⌘S saves. Reuses the
// existing TiptapEditor AS-IS (no fork). Registers the 'editor' tool (agent rack) + the editorBridge
// so the chat's propose_edit (Lane C) can write into the studio editor.
import { useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { TiptapEditor, type TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import { registerEditorTarget } from '@/features/chat/context/editorBridge';
import { useStudioHost, useRegisterStudioTool } from '../host/StudioHostProvider';
import { useManuscriptUnit } from '../manuscript/unit/ManuscriptUnitProvider';
import type { StudioToolRegistration } from '../host/types';

export function EditorPanel(_props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { bookId } = useStudioHost();
  const unit = useManuscriptUnit();
  const localRef = useRef<TiptapEditorHandle | null>(null);
  const editorRef = unit?.editorRef ?? localRef;

  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId: 'editor',
    label: t('panels.editor.title', { defaultValue: 'Editor' }),
    paletteCommand: t('palette.openPanel', { name: t('panels.editor.title', { defaultValue: 'Editor' }), defaultValue: 'Studio: Open Editor' }),
    commandId: 'studio.openPanel.editor',
    description: t('panels.editor.desc', { defaultValue: 'Manuscript editor' }),
    mcpToolPrefixes: ['book_'],
  }), [t]);
  useRegisterStudioTool(registration);

  const chapterId = unit?.state.chapterId ?? null;

  // Register the studio editor as the propose_edit write-back target (Lane C). Cleared on unmount
  // / chapter change so a stale handle never receives a write.
  useEffect(() => {
    if (!chapterId) return;
    registerEditorTarget({ bookId, chapterId, handleRef: editorRef });
    return () => registerEditorTarget(null);
  }, [bookId, chapterId, editorRef]);

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
      <div data-testid="studio-editor-panel" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('editor.empty', { defaultValue: 'Select a chapter in the manuscript navigator to edit it here.' })}
      </div>
    );
  }

  const { state, isDirty, save, setBody } = unit;

  return (
    <div data-testid="studio-editor-panel" className="flex h-full min-h-0 flex-col">
      <div className="flex h-7 flex-shrink-0 items-center gap-2 border-b px-3 text-[11px] text-muted-foreground">
        <span data-testid="studio-editor-dirty" className={isDirty ? 'text-warning' : 'text-muted-foreground/60'}>
          {isDirty ? t('editor.unsaved', { defaultValue: '● unsaved' }) : t(`editor.state.${state.saveState}`, { defaultValue: state.saveState })}
        </span>
        <button
          type="button"
          data-testid="studio-editor-save"
          onClick={() => void save()}
          disabled={!isDirty || state.saveState === 'saving'}
          className="ml-auto rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground disabled:opacity-40"
        >
          {t('editor.save', { defaultValue: 'Save' })} <span className="font-mono text-[10px]">⌘S</span>
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <TiptapEditor
          ref={editorRef}
          content={state.loadedBody}
          onUpdate={(json, text) => setBody(json, text)}
        />
      </div>
    </div>
  );
}
