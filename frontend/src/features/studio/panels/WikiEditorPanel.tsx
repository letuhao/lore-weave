// 15_wiki_panels.md B2 — the `wiki-editor` dock panel: a params-retargeting singleton
// ({articleId, rightPanel?}), same precedent as `book-reader`/`json-editor`/`skill-editor`.
// hiddenFromPalette (opened only via the `wiki` panel's Edit/History buttons / host.openPanel,
// never the agent enum — there's no wiki_* MCP tool for an agent to target it with yet).
//
// B2b (G7 dirty-guard) — dockview's `openPanel` on an already-open singleton just calls
// `updateParameters` immediately (see StudioHostProvider.openPanel); it does not ask the panel
// whether that's safe. So the guard lives HERE: `target` is the articleId this panel actually
// RENDERS, kept separate from whatever `props.params` most recently asked for. A param change
// that would swap articles while the workspace reports itself dirty is staged in `pending`
// instead of applied immediately; a ConfirmDialog gates the actual swap. `key={target.articleId}`
// on WikiEditorWorkspace forces a clean remount on a confirmed switch — no manual state reset.
import { useEffect, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/shared';
import { WikiEditorWorkspace, type WikiEditorRightPanel } from '@/features/wiki/components/WikiEditorWorkspace';
import { clearWikiEditorDraft } from '@/features/wiki/lib/wikiEditorDraftCache';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

interface WikiEditorPanelParams {
  articleId?: unknown;
  rightPanel?: unknown;
}

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const rightPanelOf = (v: unknown): WikiEditorRightPanel | undefined =>
  v === 'infobox' || v === 'history' || v === 'suggestions' ? v : undefined;

interface Target {
  articleId: string | null;
  rightPanel?: WikiEditorRightPanel;
}

function readTarget(params: Record<string, unknown> | undefined): Target {
  const p = (params ?? {}) as WikiEditorPanelParams;
  return { articleId: str(p.articleId), rightPanel: rightPanelOf(p.rightPanel) };
}

export function WikiEditorPanel(props: IDockviewPanelProps) {
  useStudioPanel('wiki-editor', props.api);
  const { t } = useTranslation('wiki');
  const host = useStudioHost();

  const [target, setTarget] = useState<Target>(() => readTarget(props.params));
  const [pending, setPending] = useState<Target | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    const disp = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      const nt = readTarget(next);
      // Same article (or no article change at all — e.g. just a rightPanel retarget from the
      // History button while already viewing this article) never needs the guard.
      if (!dirty || nt.articleId === target.articleId) {
        setTarget(nt);
      } else {
        setPending(nt);
      }
    });
    return () => disp?.dispose?.();
  }, [props.api, dirty, target.articleId]);

  if (!target.articleId) {
    return (
      <div data-testid="studio-wiki-editor-panel" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('editorPanelEmpty', { defaultValue: 'Open an article from the Wiki panel to edit it here.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-wiki-editor-panel" className="h-full min-h-0">
      <WikiEditorWorkspace
        key={target.articleId}
        bookId={host.bookId}
        articleId={target.articleId}
        initialRightPanel={target.rightPanel}
        onBack={() => host.openPanel('wiki')}
        onDirtyChange={setDirty}
        onTitleChange={(title) => props.api.setTitle(title)}
      />
      {pending && (
        <ConfirmDialog
          open
          onOpenChange={(v) => { if (!v) setPending(null); }}
          title={t('discardTitle', { defaultValue: 'Discard unsaved changes?' })}
          description={t('discardSwitchDescription', {
            defaultValue: 'You have unsaved edits to this article. Switching to a different article will discard them.',
          })}
          confirmLabel={t('discardSwitchConfirm', { defaultValue: 'Discard & switch' })}
          variant="destructive"
          onConfirm={() => { clearWikiEditorDraft(); setTarget(pending); setPending(null); }}
        />
      )}
    </div>
  );
}
