import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { Entity } from '../api';

// K19d.1 — presentational entities table. Row click + Enter/Space
// set selectedEntityId on the parent tab. a11y: rows are focusable
// buttons semantically (role="button" + tabIndex=0 + onKeyDown) so
// keyboard users can open the detail panel without a mouse.

export interface EntitiesTableProps {
  entities: Entity[];
  selectedEntityId: string | null;
  onSelect: (entityId: string) => void;
}

function formatConfidence(c: number): string {
  return `${Math.round(c * 100)}%`;
}

function formatRelativeDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function EntitiesTable({
  entities,
  selectedEntityId,
  onSelect,
}: EntitiesTableProps) {
  const { t } = useTranslation('knowledge');
  return (
    <div
      className="overflow-hidden rounded-md border"
      role="table"
      aria-label={t('entities.table.ariaLabel')}
      data-testid="entities-table"
    >
      <div
        role="row"
        className="grid grid-cols-[1fr_120px_160px_96px_96px_120px] gap-3 border-b bg-muted/50 px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground"
      >
        <span role="columnheader">{t('entities.table.col.name')}</span>
        <span role="columnheader">{t('entities.table.col.kind')}</span>
        <span role="columnheader">{t('entities.table.col.project')}</span>
        <span role="columnheader" className="text-right">
          {t('entities.table.col.mentions')}
        </span>
        <span role="columnheader" className="text-right">
          {t('entities.table.col.confidence')}
        </span>
        <span role="columnheader">{t('entities.table.col.updated')}</span>
      </div>
      <ul className="divide-y">
        {entities.map((e) => {
          const selected = e.id === selectedEntityId;
          return (
            <li key={e.id}>
              <button
                type="button"
                role="row"
                tabIndex={0}
                onClick={() => onSelect(e.id)}
                onKeyDown={(ev) => {
                  if (ev.key === 'Enter' || ev.key === ' ') {
                    ev.preventDefault();
                    onSelect(e.id);
                  }
                }}
                className={cn(
                  'grid w-full grid-cols-[1fr_120px_160px_96px_96px_120px] items-center gap-3 px-3 py-2 text-left text-[12px] transition-colors hover:bg-muted/50',
                  selected && 'bg-primary/5 ring-1 ring-primary/30',
                )}
                data-testid="entities-row"
                data-entity-id={e.id}
              >
                <span className="truncate font-medium" title={e.name}>
                  {e.name}
                </span>
                <span className="text-muted-foreground">{e.kind}</span>
                <span className="truncate text-muted-foreground" title={e.project_id ?? ''}>
                  {e.project_id ?? t('entities.table.global')}
                </span>
                <span className="text-right tabular-nums">
                  {e.mention_count}
                </span>
                <span className="text-right tabular-nums text-muted-foreground">
                  {formatConfidence(e.confidence)}
                </span>
                <span className="text-muted-foreground">
                  {formatRelativeDate(e.updated_at)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
