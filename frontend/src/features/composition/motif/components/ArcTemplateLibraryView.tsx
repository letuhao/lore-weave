// W10 arc-timeline — the ARC-TEMPLATE library surface. Lists the caller's visible arc
// templates; selecting one opens the timeline editor (thread × chapter grid / mobile
// list) + the apply-preview. Holds ONLY view-state (which arc is open); logic lives in
// the hooks. Surfaced inside the motif dock panel via the Motifs|Arcs kind-toggle.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MotifStateBoundary } from './MotifStateBoundary';
import { ArcTimelineEditor } from './ArcTimelineEditor';
import { ArcApplyPreview } from './ArcApplyPreview';
import { ArcConformancePanel } from './ArcConformancePanel';
import { useArcLibrary } from '../hooks/useArcLibrary';
import { currentUserId } from '../currentUser';
import type { ArcTemplate } from '../arcTypes';

export function ArcTemplateLibraryView({ token, projectId, modelRef }: { token: string | null; projectId?: string | null; modelRef?: string | null }) {
  const { t } = useTranslation('composition');
  const lib = useArcLibrary(token);
  const [openArc, setOpenArc] = useState<ArcTemplate | null>(null);
  const me = currentUserId();

  if (openArc) {
    return (
      <div data-testid="arc-template-detail" className="flex h-full flex-col">
        <button
          type="button"
          data-testid="arc-back"
          className="self-start px-2 py-1 text-[11px] text-amber-700 hover:underline dark:text-amber-300"
          onClick={() => setOpenArc(null)}
        >
          ← {t('motif.arc.backToList', { defaultValue: 'All arc templates' })}
        </button>
        <div className="min-h-0 flex-1 overflow-auto">
          <ArcTimelineEditor arcId={openArc.id} token={token} />
          <div className="p-2">
            <ArcApplyPreview arc={openArc} token={token} projectId={projectId} />
          </div>
          {/* post-materialize: the coarse structural diff of realized vs this template. */}
          <div className="border-t border-neutral-200 p-2 dark:border-neutral-700">
            <ArcConformancePanel projectId={projectId} arcTemplateId={openArc.id} token={token} modelRef={modelRef} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="arc-template-library" className="flex h-full flex-col p-2">
      <MotifStateBoundary isLoading={lib.isLoading} isError={lib.isError} onRetry={() => lib.refetch()} skeleton="cards">
        {(lib.data ?? []).length === 0 ? (
          <p data-testid="arc-library-empty" className="p-4 text-center text-xs text-neutral-500">
            {t('motif.arc.libraryEmpty', { defaultValue: 'No arc templates yet. Adopt one from the catalog, or import a story to deconstruct.' })}
          </p>
        ) : (
          <ul className="flex flex-col gap-1">
            {(lib.data ?? []).map((arc) => (
              <li key={arc.id}>
                <button
                  type="button"
                  data-testid={`arc-row-${arc.id}`}
                  className="flex w-full items-center justify-between gap-2 rounded border border-neutral-200 px-2 py-1.5 text-left hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  onClick={() => setOpenArc(arc)}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium">{arc.name}</span>
                    <span className="block truncate text-[10px] text-neutral-500">
                      {t('motif.arc.chapterCount', { count: arc.chapter_span ?? 0, defaultValue: '{{count}} chapters' })}
                      {arc.genre_tags.length > 0 ? ` · ${arc.genre_tags.join(', ')}` : ''}
                    </span>
                  </span>
                  <span data-testid={`arc-tier-${arc.id}`} className="shrink-0 rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-500 dark:bg-neutral-700 dark:text-neutral-300">
                    {arc.owner_user_id === null
                      ? t('motif.tier.system', { defaultValue: 'System' })
                      : arc.owner_user_id === me
                        ? t('motif.tier.user', { defaultValue: 'Mine' })
                        : t('motif.tier.public', { defaultValue: 'Public' })}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </MotifStateBoundary>
    </div>
  );
}
