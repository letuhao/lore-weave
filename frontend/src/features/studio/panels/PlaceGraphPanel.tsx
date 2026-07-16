// S7-3 · Place Graph — the studio dock host for the ONE fully-operable World/KG authoring surface.
//
// A PORT, not a build (spec docs/specs/2026-07-01-writing-studio/s7-3-place-graph.md): the whole
// leaf (<WorldMap> + useWorldMap) already ships and every action works (add place → createEntity,
// link → createRelation, drag-persist, backdrop). It was STRANDED on the legacy ChapterEditorPage's
// `worldmap` sub-tab, reachable from no dock panel / palette / agent enum. This ~thin host makes it
// reachable, exactly like ComposePanel hosts <Chat> (DOCK-2 one-implementation-two-hosts — no fork).
//
// The wrapper owns the two states the leaf assumes away (§4.2): no composition Work (the leaf reads
// `work.settings.world_map` and would crash on a null Work), and it feeds the bus `activeChapterId`
// for the (chapter-scoped) backdrop bucket. The leaf itself renders loading / no-project / empty.
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { WorldMap } from '@/features/composition/components/WorldMap';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { useStudioHost, useStudioBusSelector } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function PlaceGraphPanel(props: IDockviewPanelProps) {
  useStudioPanel('place-graph', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  // The backdrop upload is chapter-scoped (uploadChapterMedia). Read the active chapter off the bus —
  // no new bus slice (contrast arc-inspector, which needed activeArcId). Empty ⇒ the leaf's §4.3 guard
  // disables Backdrop with a hint; the graph itself needs no chapter.
  const activeChapterId = useStudioBusSelector((s) => s.activeChapterId);

  // useWorkResolution resolves to the ENVELOPE `WorkResolution {status, work, candidates}`, NOT a bare
  // Work — resolve the ACTIVE Work (EC-3d: per-book pref, else canonical) so the place graph follows a
  // "Switch to" a dị bản. The leaf reads `work.settings.world_map`, so mounting it with a null Work
  // would crash — the wrapper intercepts that below.
  const workQ = useWorkResolution(host.bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(host.bookId, accessToken);
  const work = resolveActiveWork(workQ.data, activeWorkId);

  // Deep-links (§4.1, S3). onViewCast → the s7-4 `cast` panel with a search prefill (OQ-1:
  // CastCodexPanel already accepts a `search` prop; params.search is the settled key). "Author other
  // kinds" → the existing `kg-entities` panel (OQ-2: s7-1 authoring mounts inside it, no new id).
  // Both degrade to a graceful no-op if the sibling panel isn't registered (openPanel try/catch).
  const viewCast = (name: string) => host.openPanel('cast', { params: { search: name } });
  const authorOtherKinds = () => host.openPanel('kg-entities');

  if (workQ.isLoading && !work) {
    return (
      <div
        data-testid="studio-place-graph-panel"
        className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground"
      >
        {t('panels.place-graph.loading', { defaultValue: 'Loading world map…' })}
      </div>
    );
  }

  // ⭐NEW state (§4.2): the book has no composition Work. NEVER mount <WorldMap> with a null work.
  if (!work) {
    return (
      <div
        data-testid="studio-place-graph-panel"
        className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-sm text-muted-foreground"
      >
        <p data-testid="place-graph-nowork">
          {t('panels.place-graph.noWork', {
            defaultValue: 'Set up the co-writer in Compose to arrange places.',
          })}
        </p>
        <button
          type="button"
          data-testid="place-graph-setup-cowriter"
          className="rounded border px-3 py-1 text-xs hover:bg-secondary hover:text-foreground"
          onClick={() => host.openPanel('compose')}
        >
          {t('panels.place-graph.openCompose', { defaultValue: 'Open Compose' })}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="studio-place-graph-panel" className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1">
        <WorldMap
          work={work}
          bookId={host.bookId}
          chapterId={activeChapterId ?? ''}
          token={accessToken}
          onViewCast={viewCast}
        />
      </div>
      {/* Draft state ③ — bridge to authoring the OTHER entity kinds (characters/items/…) this
          location-only graph deliberately excludes (buildPlaceGraph drops non-location endpoints). */}
      <div className="flex flex-shrink-0 items-center justify-end border-t px-3 py-1.5 text-[11px]">
        <button
          type="button"
          data-testid="place-graph-author-other"
          className="rounded px-1.5 py-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
          onClick={authorOtherKinds}
        >
          {t('panels.place-graph.authorOther', { defaultValue: 'Author other kinds →' })}
        </button>
      </div>
    </div>
  );
}
