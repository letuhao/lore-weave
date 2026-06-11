// LOOM Composition (T2.4) — the Character Arc's "relations now" strip: the focus
// entity's current 1-hop RELATES_TO as compact chips, direction-aware (mirrors the
// Cast codex). Pending-validation edges are dashed. Render-only.
import { useTranslation } from 'react-i18next';
import type { EntityRelation } from '../../knowledge/api';

export function ArcRelationsStrip({ entityId, relations }: { entityId: string; relations: EntityRelation[] }) {
  const { t } = useTranslation('composition');
  if (relations.length === 0) {
    return (
      <div data-testid="arc-relations" className="px-3 py-1 text-[11px] text-muted-foreground">
        <span className="font-medium">{t('chararc.relations_now', { defaultValue: 'relations now' })}:</span>{' '}
        <span className="italic text-muted-foreground/60">{t('chararc.no_relations', { defaultValue: 'none' })}</span>
      </div>
    );
  }
  return (
    <div data-testid="arc-relations" className="flex flex-wrap items-center gap-1 px-3 py-1 text-[11px]">
      <span className="font-medium text-muted-foreground">{t('chararc.relations_now', { defaultValue: 'relations now' })}:</span>
      {relations.slice(0, 10).map((r) => {
        const outgoing = r.subject_id === entityId;
        const other = outgoing ? (r.object_name ?? r.object_id) : (r.subject_name ?? r.subject_id);
        return (
          <span
            key={r.id}
            data-testid="arc-relation"
            data-pending={r.pending_validation ? 'true' : 'false'}
            className={
              'rounded border px-1.5 py-0.5 ' +
              (r.pending_validation ? 'border-dashed text-muted-foreground' : 'border-border')
            }
            title={`${r.subject_name ?? r.subject_id} ${r.predicate} ${r.object_name ?? r.object_id}`}
          >
            {outgoing ? <>{r.predicate} → {other}</> : <>{other} → {r.predicate}</>}
          </span>
        );
      })}
    </div>
  );
}
