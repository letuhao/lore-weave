// #16 Phase 2 (2.7) — Media Version History dock panel. Per-resource retargeting panel (dock id
// `media-version-history:{chapterId}:{blockId}`, component 'media-version-history'): mirrors the
// json-editor precedent (12 R3/R4) — each (chapter, block) pair gets its OWN tab; re-opening the
// same block focuses the existing tab (host.openPanel dedup by dock id). Replaces legacy
// ChapterEditorPage's internal `versionHistory ? <VersionHistoryPanel/> : <TiptapEditor/>`
// page-swap with a genuine sibling dock panel per DOCK-8 (one capability = one panel, no
// internal page-replacement) — `VersionHistoryPanel` itself is reused AS-IS (DOCK-2), not
// forked. hiddenFromPalette (DOCK-6): opened only from the "history" button inside an
// image/video NodeView (via EditorPanel's `onOpenHistory`/`onOpenVideoHistory` wiring), never
// the command palette or an agent MCP tool.
//
// NOT registered via useRegisterStudioTool, matching JsonEditorPanel's own J1 rationale: this
// is a multi-instance singleton component (many tabs can be open at once, one per block) — a
// shared registry entry keyed by panelId would have each instance's mount/unmount clobber the
// others' registration.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { VersionHistoryPanel } from '@/components/editor/VersionHistoryPanel';

interface MediaVersionHistoryParams {
  bookId?: unknown;
  chapterId?: unknown;
  blockId?: unknown;
  blockTitle?: unknown;
  currentMediaUrl?: unknown;
}

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function MediaVersionHistoryPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();

  // Retarget on EVERY updateParameters (R3 singleton; same lesson as JsonEditorPanel/SettingsPanel
  // — the event fires on every call, so re-opening the same block still lands the right params).
  const p = (props.params ?? {}) as MediaVersionHistoryParams;
  const [target, setTarget] = useState({
    bookId: str(p.bookId),
    chapterId: str(p.chapterId),
    blockId: str(p.blockId),
    blockTitle: str(p.blockTitle) ?? '',
    currentMediaUrl: str(p.currentMediaUrl),
  });
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      const np = (next ?? {}) as MediaVersionHistoryParams;
      setTarget({
        bookId: str(np.bookId),
        chapterId: str(np.chapterId),
        blockId: str(np.blockId),
        blockTitle: str(np.blockTitle) ?? '',
        currentMediaUrl: str(np.currentMediaUrl),
      });
    });
    return () => d?.dispose?.();
  }, [props.api]);

  // Self-title (DOCK-5) — the block's own title, like json-editor's J1 per-instance titling.
  useEffect(() => {
    const label = t('panels.media-version-history.title', { defaultValue: 'Version History' });
    props.api.setTitle(target.blockTitle ? `${label} · ${target.blockTitle}` : label);
  }, [props.api, t, target.blockTitle]);

  if (!accessToken || !target.bookId || !target.chapterId || !target.blockId) {
    return (
      <div data-testid="studio-media-version-history" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('panels.media-version-history.empty', { defaultValue: 'No media block selected.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-media-version-history" className="flex h-full min-h-0 flex-col">
      <VersionHistoryPanel
        token={accessToken}
        bookId={target.bookId}
        chapterId={target.chapterId}
        blockId={target.blockId}
        blockTitle={target.blockTitle}
        currentMediaUrl={target.currentMediaUrl}
        onClose={() => props.api.close()}
        onRestore={() => {
          // Matches legacy ChapterEditorPage's own onRestore (ChapterEditorPage.tsx:677-681),
          // which likewise does not push the restored version back into the live document —
          // there is no `restoreMediaVersion` API and no cross-panel bus event for it yet. This
          // is a pre-existing gap in the legacy behavior, not a regression introduced here;
          // wiring an actual restore-into-document flow is future work (would need a DOCK-4 bus
          // event to the owning EditorPanel/block, tracked separately from this migration).
        }}
      />
    </div>
  );
}
