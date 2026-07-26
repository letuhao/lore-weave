// C24 (dị bản) — the 2-layer grounding decoration for a DERIVATIVE Work's
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
//
// WS-B2 adds the durable "now" delta on OVERRIDDEN rows. (B2c "Adapt with overrides"
// ghost-generate is NOT here — see D-DERIVATIVE-ADAPT-FROM-SOURCE: generate_chapter
// needs a scene plan in the derivative project, which the inherited spine chapters
// lack, so it needs a real "adapt-from-source-content" design, not a generate call.)
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

/** Render an override field value (the "now" of the delta). Override fields are
 *  authored as strings in practice, but `overridden_fields` is `dict[str, Any]` —
 *  stringify non-strings readably instead of rendering "[object Object]". */
function renderOverrideValue(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value);
}

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
        {(entities.data ?? []).map((e) => {
          // ID-SPACE (WS-B2 fix): the override set is keyed by the GLOSSARY anchor
          // (`glossary_entity_id`), NOT the knowledge node id (`e.id`) — classifying
          // by `e.id` made EVERY row read INHERITED (the override never matched). An
          // UNANCHORED entity has no anchor, so it can never be overridden (inherited).
          const anchorId = e.glossary_entity_id;
          const layer = anchorId ? ctx.classify(anchorId) : 'inherited';
          // B2b — the durable per-entity field delta (the "now" of was→now). The
          // source field ("was") is not in the list payload, so we surface the
          // authored override value truthfully rather than fabricate an old value.
          const delta = anchorId ? ctx.overrides[anchorId] : undefined;
          return (
            <li key={e.id} data-testid={`derivative-layer-entity-${e.id}`} className="flex flex-col gap-0.5 rounded border border-neutral-100 px-2 py-1 dark:border-neutral-800">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate">{e.name} <span className="text-xs text-neutral-400">({e.kind})</span></span>
                <GroundingLayerBadge layer={layer} />
              </div>
              {layer === 'overridden' && delta && (
                <div data-testid={`derivative-layer-delta-${e.id}`} className="flex flex-col gap-0.5 pl-1 text-xs">
                  {Object.entries(delta).map(([field, value]) => (
                    <span key={field} className="text-amber-700 dark:text-amber-300">
                      <span className="text-neutral-400">{field}: </span>
                      {t('derive.deltaNow', { defaultValue: 'now' })} → {renderOverrideValue(value)}
                    </span>
                  ))}
                </div>
              )}
            </li>
          );
        })}
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
