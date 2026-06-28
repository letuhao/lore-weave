// W6 §3.4 — the motif library DOCK PANEL (scope tabs + facets + list). Orchestrates
// children + holds ONLY view-state (which drawer/modal is open); the logic lives in
// the hooks. Re-skinned to the studio dark tokens (§2.2). The library is the hub:
// detail is a drawer, create is an inline form, adopt is a modal — none are routes.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MotifStateBoundary } from './MotifStateBoundary';
import { MotifEmptyState } from './MotifEmptyState';
import { MotifScopeTabs } from './MotifScopeTabs';
import { MotifFacetRail } from './MotifFacetRail';
import { MotifCard } from './MotifCard';
import { MotifDetailDrawer } from './MotifDetailDrawer';
import { MotifQuickCreateForm } from './MotifQuickCreateForm';
import { AdoptTargetModal } from './AdoptTargetModal';
import { ArcTemplateLibraryView } from './ArcTemplateLibraryView';
import { useMotifLibrary } from '../hooks/useMotifLibrary';
import { useMotifDetail } from '../hooks/useMotifDetail';
import { useMotifQuickCreate } from '../hooks/useMotifQuickCreate';
import { useAdoptFlow } from '../hooks/useAdoptFlow';
import { useMotifSimpleMode } from '../context/MotifSimpleModeContext';
import { currentUserId } from '../currentUser';

type Props = {
  token: string | null;
  meUserId?: string | null;
  /** The current work, when the panel is mounted inside a project — enables the arc
   *  "Materialize to this book" commit action (D-W10-APPLY-PLANNER-MATERIALIZE). */
  projectId?: string | null;
};

export function MotifLibraryView({ token, meUserId: meProp, projectId }: Props) {
  const { t } = useTranslation('composition');
  const me = meProp ?? currentUserId();
  const { simple, toggle } = useMotifSimpleMode();
  const lib = useMotifLibrary(token);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [showFilters, setShowFilters] = useState(false);   // mobile filter sheet (§5.5)
  const [kind, setKind] = useState<'motifs' | 'arcs'>('motifs');   // W10 — motif vs arc-template library

  const detail = useMotifDetail(openId, me, token);
  const quickCreate = useMotifQuickCreate(token, (m) => { setCreating(false); setOpenId(m.id); });
  const adopt = useAdoptFlow(token);

  return (
    <div data-testid="motif-library-view" className="flex h-full flex-col">
      {/* W10 — library kind: motifs vs arc templates (the meso structure layer) */}
      <div role="tablist" aria-label={t('motif.kind.label', { defaultValue: 'Library' })} className="flex items-center gap-1 px-1 pt-1">
        <button type="button" role="tab" aria-selected={kind === 'motifs'} data-testid="motif-kind-motifs" className={`rounded px-2 py-0.5 text-[11px] ${kind === 'motifs' ? 'bg-amber-600 text-white' : 'border border-neutral-300 dark:border-neutral-600'}`} onClick={() => setKind('motifs')}>
          {t('motif.kind.motifs', { defaultValue: 'Motifs' })}
        </button>
        <button type="button" role="tab" aria-selected={kind === 'arcs'} data-testid="motif-kind-arcs" className={`rounded px-2 py-0.5 text-[11px] ${kind === 'arcs' ? 'bg-amber-600 text-white' : 'border border-neutral-300 dark:border-neutral-600'}`} onClick={() => setKind('arcs')}>
          {t('motif.kind.arcs', { defaultValue: 'Arc templates' })}
        </button>
      </div>

      {kind === 'arcs' ? (
        <div className="min-h-0 flex-1 overflow-auto">
          <ArcTemplateLibraryView token={token} projectId={projectId} />
        </div>
      ) : (
      <>
      {/* header: scope tabs + simple-mode toggle + new-motif */}
      <div className="flex items-center justify-between gap-2 px-1 pt-1">
        <MotifScopeTabs scope={lib.scope} onScope={lib.setScope} />
        <div className="flex items-center gap-1">
          <button type="button" aria-pressed={simple} data-testid="motif-simple-toggle" className="rounded border border-neutral-300 px-2 py-0.5 text-[11px] dark:border-neutral-600" onClick={toggle}>
            {simple ? t('motif.mode.simple', { defaultValue: 'Simple' }) : t('motif.mode.expert', { defaultValue: 'Expert' })}
          </button>
          <button type="button" data-testid="motif-new" className="rounded bg-amber-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-amber-700" onClick={() => setCreating(true)}>
            + {t('motif.action.newMotif', { defaultValue: 'New motif' })}
          </button>
        </div>
      </div>

      {/* search */}
      <div className="flex items-center gap-1 p-1">
        <input
          data-testid="motif-search"
          aria-label={t('motif.search', { defaultValue: 'Search motifs' })}
          className="min-w-0 flex-1 rounded border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-600 dark:bg-neutral-800"
          placeholder={t('motif.search', { defaultValue: 'Search motifs' })}
          value={lib.search}
          onChange={(e) => lib.setSearch(e.target.value)}
        />
        <button type="button" data-testid="motif-filter-toggle" className="rounded border border-neutral-300 px-2 py-1 text-xs sm:hidden dark:border-neutral-600" onClick={() => setShowFilters((v) => !v)}>
          {t('motif.facet.filters', { defaultValue: 'Filters' })}
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* facet rail — left column desktop; toggled sheet on mobile (§5.5) */}
        <div className={`w-44 shrink-0 overflow-auto border-r border-neutral-200 dark:border-neutral-700 ${showFilters ? 'block' : 'hidden'} sm:block`}>
          <MotifFacetRail facets={lib.facets} available={lib.available} onSetFacet={lib.setFacet} onClear={lib.clearFacets} />
        </div>

        {/* list */}
        <div className="min-w-0 flex-1 overflow-auto p-2">
          <MotifStateBoundary isLoading={lib.isLoading} isError={lib.isError} onRetry={() => lib.refetch()} skeleton="cards">
            {lib.isEmpty ? (
              <MotifEmptyState onNewMotif={() => setCreating(true)} onBrowseSystem={() => { lib.setScope('my'); lib.setFacet('tier', 'system'); }} />
            ) : lib.motifs.length === 0 ? (
              <p data-testid="motif-no-match" className="p-4 text-center text-xs text-neutral-500">{t('motif.list.noMatch', { defaultValue: 'No motifs match — clear filters.' })}</p>
            ) : (
              <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
                {lib.motifs.map((m) => (
                  <MotifCard key={m.id} motif={m} meUserId={me} onOpen={setOpenId} onAdopt={adopt.begin} />
                ))}
              </div>
            )}
          </MotifStateBoundary>
        </div>
      </div>

      {/* inline create form (mount-on-open) */}
      {creating && (
        <div className="border-t border-neutral-200 dark:border-neutral-700">
          <MotifQuickCreateForm ctrl={quickCreate} onCancel={() => setCreating(false)} />
        </div>
      )}

      {/* detail drawer (mount-on-open) */}
      {openId && (
        <MotifDetailDrawer
          motif={detail.motif}
          meUserId={me}
          readOnly={detail.readOnly}
          isLoading={detail.isLoading}
          isError={detail.isError}
          onClose={() => setOpenId(null)}
          onClone={(id) => { setOpenId(null); adopt.begin(id); }}
        />
      )}

      {/* adopt modal (mount-on-open) */}
      <AdoptTargetModal
        open={adopt.isOpen}
        estimate={adopt.estimate}
        quota={adopt.quota}
        minting={adopt.mint.isPending}
        confirming={adopt.confirm.isPending}
        onMint={() => adopt.mint.mutate()}
        onConfirm={() => adopt.confirm.mutate()}
        onCancel={adopt.cancel}
      />
      </>
      )}
    </div>
  );
}
