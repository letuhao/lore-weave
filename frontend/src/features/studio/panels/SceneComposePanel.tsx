// S1 · Manuscript & Compose (studio-completeness 2026-07-16) — the SCENE DRAFT LOOP as a
// first-class studio dock panel.
//
// Why this exists: the studio dock's `compose` panel is the AI co-writer CHAT; the rich
// draft → K-candidates → accept → revise → correction-capture loop (ComposeView) lived ONLY
// on the legacy ChapterEditorPage, so a dock author could not draft a scene through the GUI —
// they had to leave for the legacy page or drive it through the agent (MCP). This panel homes
// that loop (§0 ①/③ + the "cho có" bar §2).
//
// Reuse, not fork (DOCK-2): it mounts CompositionPanel in `soloPanel="compose"` mode — the SAME
// container the /composition/popout route already renders standalone — so the Work-resolution,
// scene selector, and model-precedence cascade come for free (no drift from that subtle logic).
// The ONE studio-specific wiring is the accept→editor handoff: legacy co-mounts ComposeView with
// its Tiptap editor, but in the dock the editor is a SEPARATE panel, so accepted prose is inserted
// through the module-singleton editorBridge (getEditorTarget) — the same seam the agent's
// propose_edit Apply and the popout insert-relay already use.
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { CompositionPanel } from '@/features/composition/components/CompositionPanel';
import { LiveStateProvider } from '@/features/composition/context/LiveStateContext';
import { useStudioHost, useRegisterStudioTool } from '../host/StudioHostProvider';
import { useManuscriptUnitMeta } from '../manuscript/unit/ManuscriptUnitProvider';
import { useAcceptIntoEditor } from './useAcceptIntoEditor';
import type { StudioToolRegistration } from '../host/types';

export function SceneComposePanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { bookId } = host;
  const { accessToken } = useAuth();
  // The active chapter is the studio bus's chapterId (set by the manuscript navigator / focus
  // seam), the SAME source the Editor panel follows — so the scene the writer drafts here and the
  // editor that receives the accepted prose are always the same chapter.
  const meta = useManuscriptUnitMeta();
  const chapterId = meta?.activeChapterId ?? null;

  // Register for the agent rack (#07a) so an agent on this surface owns the composition tool
  // family (draft/diverge/accept/correct), exactly like the co-writer `compose` panel does.
  const label = t('panels.scene-compose.title', { defaultValue: 'Scene Compose' });
  const registration = useMemo<StudioToolRegistration>(() => ({
    panelId: 'scene-compose',
    label,
    paletteCommand: t('palette.openPanel', { name: label, defaultValue: 'Studio: Open Scene Compose' }),
    commandId: 'studio.openPanel.scene-compose',
    description: t('panels.scene-compose.desc', { defaultValue: 'Draft a scene with AI candidates' }),
    mcpToolPrefixes: ['composition_'],
    skills: ['universal'],
  }), [t, label]);
  useRegisterStudioTool(registration);

  // Self-title the dock tab (an agent/palette open sets the raw id before this panel mounts).
  useEffect(() => {
    props.api.setTitle(label);
  }, [props.api, label]);

  // The accept→editor handoff (shared with chapter-assemble) — insert into the Editor holding THIS
  // chapter via the editorBridge singleton, with the no-editor / wrong-chapter guards.
  const onAccept = useAcceptIntoEditor(chapterId);

  if (!chapterId) {
    return (
      <div data-testid="studio-scene-compose-panel" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('sceneCompose.empty', { defaultValue: 'Select a chapter in the manuscript navigator to draft its scenes here.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-scene-compose-panel" className="flex h-full min-h-0 flex-col">
      {/* ComposeView's useLiveStream() throws without a LiveStateProvider. Match the legacy
          DOCKED path (WorkspaceShell.tsx) exactly: plain in-process stream, NO `forceShared`.
          forceShared routes the turn through the co-writer SharedWorker — correct ONLY for a
          genuine OS pop-out (a separate window, PopoutHost), where it was mis-borrowed from here;
          in a same-page dock panel it made the ghost silently not render on a production build. */}
      <LiveStateProvider token={accessToken}>
        <CompositionPanel
          bookId={bookId}
          chapterId={chapterId}
          token={accessToken}
          onAccept={onAccept}
          soloPanel="compose"
        />
      </LiveStateProvider>
    </div>
  );
}
