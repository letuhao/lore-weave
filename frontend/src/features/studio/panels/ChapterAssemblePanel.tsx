// S1 · Manuscript & Compose (studio-completeness 2026-07-16) — the CHAPTER ASSEMBLE loop as a
// first-class studio dock panel: single-pass "Generate chapter" or "Stitch" the done scene drafts
// into one chapter, review the editable preview, and accept it into the manuscript. It is also the
// SECOND correction producer (edit/regenerate/reject → generation_correction → learning-service).
//
// Like scene-compose, this homes a sub-tab of the legacy ChapterEditorPage/CompositionPanel as a
// dock panel by reusing CompositionPanel in `soloPanel="assemble"` mode (DOCK-2, no fork). The
// provider stack mirrors the proven /composition/popout host (PopoutHost) MINUS `forceShared`
// (that is for a real OS pop-out window; in a same-page dock panel it silently breaks streaming):
//   • LiveStateProvider   — assemble itself doesn't stream, but it matches the legacy nesting and
//                           is harmless (DockSlot returns null for the non-solo compose slot, so
//                           ComposeView never mounts here).
//   • AssembleStateProvider — owns the in-progress {result, edited} draft above the panel so an
//                             un-accepted assemble survives a dock float (WS-D), same as legacy.
// Accept routes to the Editor via the shared editorBridge handoff (useAcceptIntoEditor).
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { CompositionPanel } from '@/features/composition/components/CompositionPanel';
import { LiveStateProvider } from '@/features/composition/context/LiveStateContext';
import { AssembleStateProvider } from '@/features/composition/context/AssembleStateContext';
import { useStudioHost, useRegisterStudioTool } from '../host/StudioHostProvider';
import { useManuscriptUnitMeta } from '../manuscript/unit/ManuscriptUnitProvider';
import { useAcceptIntoEditor } from './useAcceptIntoEditor';
import type { StudioToolRegistration } from '../host/types';

export function ChapterAssemblePanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { bookId } = host;
  const { accessToken } = useAuth();
  const meta = useManuscriptUnitMeta();
  const chapterId = meta?.activeChapterId ?? null;

  const label = t('panels.chapter-assemble.title', { defaultValue: 'Chapter Assemble' });
  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId: 'chapter-assemble',
    label,
    paletteCommand: t('palette.openPanel', { name: label, defaultValue: 'Studio: Open Chapter Assemble' }),
    commandId: 'studio.openPanel.chapter-assemble',
    description: t('panels.chapter-assemble.desc', { defaultValue: 'Assemble or stitch scenes into a chapter' }),
    mcpToolPrefixes: ['composition_'],
    skills: ['universal'],
  }), [t, label]);
  useRegisterStudioTool(registration);

  useEffect(() => {
    props.api.setTitle(label);
  }, [props.api, label]);

  const onAccept = useAcceptIntoEditor(chapterId);

  if (!chapterId) {
    return (
      <div data-testid="studio-chapter-assemble-panel" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('chapterAssemble.empty', { defaultValue: 'Select a chapter in the manuscript navigator to assemble it here.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-chapter-assemble-panel" className="flex h-full min-h-0 flex-col">
      <LiveStateProvider token={accessToken}>
        <AssembleStateProvider bookId={bookId} chapterId={chapterId}>
          <CompositionPanel
            bookId={bookId}
            chapterId={chapterId}
            token={accessToken}
            onAccept={onAccept}
            soloPanel="assemble"
          />
        </AssembleStateProvider>
      </LiveStateProvider>
    </div>
  );
}
