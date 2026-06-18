// C24 (dị bản M0) — the 2-layer grounding decoration for a DERIVATIVE Work's
// grounding tab (view). Lists the canon entities (from the SOURCE project) each
// tagged INHERITED (base) or OVERRIDDEN (delta) via the REAL override set, with a
// legend, plus the read-only reference-spine surfacing.
//
// LOCKED constraints honoured:
//  • Reference spine = original chapters listed READ-ONLY as adaptable reference —
//    NOT auto-inserted into the draft. There is NO "insert"/"paste into draft"
//    affordance here; the writer adapts manually.
//  • Badges reflect REAL override state (ctx.classify over the submitted set) — an
//    OVERRIDDEN entity is never shown INHERITED.
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { knowledgeApi } from '../../knowledge/api';
import { booksApi } from '../../books/api';
import type { DerivativeContext } from '../hooks/useDerivativeContext';
import { GroundingLayerBadge, GroundingLayerLegend } from './GroundingLayerBadge';

type Props = {
  ctx: DerivativeContext;
  /** The SOURCE Work's project_id — canon entities to classify come from here. */
  sourceProjectId: string;
  bookId: string;
  token: string | null;
};

export function DerivativeGroundingLayers({ ctx, sourceProjectId, bookId, token }: Props) {
  const { t } = useTranslation('composition');
  const entities = useQuery({
    queryKey: ['composition', 'derive-layer-entities', sourceProjectId],
    queryFn: () => knowledgeApi.listEntities({ project_id: sourceProjectId, limit: 50, sort_by: 'mention_count' }, token!),
    enabled: !!sourceProjectId && !!token && ctx.isDerivative,
    select: (d) => d.entities,
  });
  // Reference spine — original chapters UP TO the branch point, READ-ONLY.
  const chapters = useQuery({
    queryKey: ['composition', 'derive-spine', bookId],
    queryFn: () => booksApi.listChapters(token!, bookId, { lifecycle_state: 'active', limit: 500, offset: 0 }),
    enabled: !!bookId && !!token && ctx.isDerivative,
    select: (d) =>
      [...d.items]
        .sort((a, b) => a.sort_order - b.sort_order)
        .filter((c) => ctx.branchPoint == null || c.sort_order <= ctx.branchPoint),
  });

  if (!ctx.isDerivative) return null;

  return (
    <div className="flex flex-col gap-3 p-3 text-sm" data-testid="derivative-grounding-layers">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          {t('derive.layersTitle', { defaultValue: 'Canon layers' })}
        </span>
        <GroundingLayerLegend />
      </div>
      <ul className="flex flex-col gap-1" data-testid="derivative-layer-list">
        {(entities.data ?? []).map((e) => (
          <li key={e.id} data-testid={`derivative-layer-entity-${e.id}`} className="flex items-center justify-between gap-2 rounded border border-neutral-100 px-2 py-1 dark:border-neutral-800">
            <span className="truncate">{e.name} <span className="text-xs text-neutral-400">({e.kind})</span></span>
            <GroundingLayerBadge layer={ctx.classify(e.id)} />
          </li>
        ))}
        {entities.data?.length === 0 && (
          <li className="px-2 py-2 text-xs text-neutral-500">{t('derive.noCanonEntities', { defaultValue: 'No canon entities to inherit yet.' })}</li>
        )}
      </ul>

      {/* Read-only reference spine — adapt manually, never auto-inserted. */}
      <div data-testid="derivative-reference-spine" className="rounded border border-neutral-200 dark:border-neutral-700">
        <div className="border-b border-neutral-200 px-2 py-1 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:border-neutral-700">
          {t('derive.referenceSpine', { defaultValue: 'Reference spine (read-only)' })}
        </div>
        <p className="px-2 py-1 text-xs text-neutral-500">
          {t('derive.referenceSpineHint', { defaultValue: 'Original chapters up to your branch point — adapt them manually. They are not inserted into your draft.' })}
        </p>
        <ul className="max-h-40 overflow-y-auto">
          {(chapters.data ?? []).map((c) => (
            <li key={c.chapter_id} data-testid={`reference-spine-chapter-${c.chapter_id}`} className="flex items-center justify-between px-2 py-1 text-xs">
              <span className="truncate">{c.sort_order + 1}. {c.title || c.original_filename}</span>
              {/* read-only: a link to OPEN the original for reading — never an
                  "insert into draft" action (LOCKED no-auto-insert). */}
              <a
                href={`/books/${bookId}/chapters/${c.chapter_id}/read`}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-600 hover:underline dark:text-indigo-400"
              >
                {t('derive.openReference', { defaultValue: 'Open' })}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
