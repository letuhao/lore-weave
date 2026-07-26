import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { RawSearchPanel } from '@/features/raw-search/components/RawSearchPanel';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { SemanticSearchList } from '../search/SemanticSearchList';

// S-11 — the studio `search` activity-view's dock panel. Two modes over the ALREADY-COMPLETE
// search backends: TEXT (story_search via the reused RawSearchPanel) and SEMANTIC (memory_search
// via the thin SemanticSearchList). Both deep-link a hit into the in-dock editor
// (host.focusManuscriptUnit) instead of navigating away — the operability point (the search view
// is a way INTO the manuscript, not a dead-end results list).
//
// Query + mode seed from props.params (the search rail passes what the user typed) and follow
// every updateParameters call (BookReaderPanel precedent). A new rail query remounts the inner
// component (key=query) so it re-seeds cleanly.

type SearchMode = 'text' | 'semantic';
interface SearchPanelParams {
  query?: string;
  mode?: SearchMode;
}

export function SearchPanel(props: IDockviewPanelProps) {
  useStudioPanel('search', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const { projectId, isLoading: isProjectLoading } = useBookKnowledgeProject(host.bookId);

  const [params, setParams] = useState<SearchPanelParams>((props.params as SearchPanelParams | undefined) ?? {});
  useEffect(() => {
    const disp = props.api.onDidParametersChange?.((p: Record<string, unknown> | undefined) => {
      setParams((p as SearchPanelParams | undefined) ?? {});
    });
    return () => disp?.dispose?.();
  }, [props.api]);

  // The rail seeds the mode; a local toggle lets the user switch in-panel afterward.
  const [mode, setMode] = useState<SearchMode>(params.mode ?? 'text');
  useEffect(() => {
    if (params.mode) setMode(params.mode);
  }, [params.mode]);

  const query = params.query ?? '';
  const openChapter = (chapterId: string) => host.focusManuscriptUnit(chapterId);

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3" data-testid="search-panel">
      <div className="flex rounded-md border p-0.5 self-start" role="group" aria-label={t('search.modeLabel', { defaultValue: 'Search mode' })}>
        {(['text', 'semantic'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            aria-pressed={mode === m}
            data-testid={`search-mode-${m}`}
            className={cn(
              'rounded px-3 py-1 text-xs font-medium transition-colors',
              mode === m ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`search.mode.${m}`, { defaultValue: m === 'text' ? 'Text' : 'Semantic' })}
          </button>
        ))}
      </div>

      {mode === 'text' ? (
        // Reused AS-IS (DOCK-2, no fork). onJump opens the in-dock editor; initialQuery seeds from
        // the rail. key=query remounts on a new rail query so the seed re-applies.
        <RawSearchPanel
          key={`text:${query}`}
          bookId={host.bookId}
          onJump={openChapter}
          initialQuery={query}
        />
      ) : (
        <SemanticSearchList
          key={`sem:${query}`}
          projectId={accessToken ? projectId : null}
          isProjectLoading={isProjectLoading}
          initialQuery={query}
          onOpenChapter={openChapter}
        />
      )}
    </div>
  );
}
