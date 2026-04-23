import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { Entity } from '../api';

// K19d.1 — presentational entities table. Row click + Enter/Space
// set selectedEntityId on the parent tab. a11y: rows are focusable
// buttons semantically (role="button" + tabIndex=0 + onKeyDown) so
// keyboard users can open the detail panel without a mouse.
//
// C5 (D-K19d-β-01) — dual render-tree for mobile. The desktop
// 6-column grid (1fr+120+160+96+96+120 ≈ 620px fixed width + 1fr)
// overflows horizontally on a 375px phone viewport. Below the md
// breakpoint we hide the desktop tree (`hidden md:block`) and
// render a card-per-row layout (`md:hidden`) showing Name + Kind
// primary with the secondary fields stacked beneath.
//
// Pure CSS switch (no `useIsMobile()`) keeps this a re-render-free,
// SSR-safe change; Tailwind's `hidden` → `display: none` removes
// the unused tree from the a11y tree too, so screen readers see
// exactly one tree per viewport.

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

function rowKeyHandler(onSelect: (id: string) => void, id: string) {
  return (ev: React.KeyboardEvent<HTMLButtonElement>) => {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      onSelect(id);
    }
  };
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
      {/* Desktop tree — 6-column grid. Hidden on < md. */}
      <div className="hidden md:block" data-testid="entities-table-desktop">
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
                  onKeyDown={rowKeyHandler(onSelect, e.id)}
                  className={cn(
                    'grid w-full grid-cols-[1fr_120px_160px_96px_96px_120px] items-center gap-3 px-3 py-2 text-left text-[12px] transition-colors hover:bg-muted/50',
                    selected && 'bg-primary/5 ring-1 ring-primary/30',
                  )}
                  // /review-impl LOW4: `entities-row` testid is
                  // desktop-only. Mobile tree uses the sibling
                  // `entities-row-mobile`. Tests that want total
                  // rendered-row count across both trees should
                  // query `findAllByTestId(/^entities-row/)`.
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

      {/* Mobile tree — card-per-row. Visible on < md.
          /review-impl LOW2: mobile cards drop the desktop's
          `role="row"` because there's no columnheader context on
          mobile — it just confuses screen readers. The underlying
          <button> conveys the "activatable item" semantics that
          matter. Also exposes the `-mobile` testid sibling to
          `entities-row` so tests can target either tree. */}
      <ul className="divide-y md:hidden" data-testid="entities-table-mobile">
        {entities.map((e) => {
          const selected = e.id === selectedEntityId;
          return (
            <li key={e.id}>
              <button
                type="button"
                onClick={() => onSelect(e.id)}
                onKeyDown={rowKeyHandler(onSelect, e.id)}
                className={cn(
                  'flex w-full flex-col gap-1 px-3 py-2 text-left transition-colors hover:bg-muted/50',
                  selected && 'bg-primary/5 ring-1 ring-primary/30',
                )}
                data-testid="entities-row-mobile"
                data-entity-id={e.id}
                aria-label={e.name}
              >
                <div className="flex items-baseline justify-between gap-2 text-[13px]">
                  <span className="min-w-0 truncate font-medium" title={e.name}>
                    {e.name}
                  </span>
                  <span className="shrink-0 text-[11px] uppercase tracking-wide text-muted-foreground">
                    {e.kind}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
                  <span className="tabular-nums">
                    {t('entities.table.col.mentions')}: {e.mention_count}
                  </span>
                  <span className="tabular-nums">
                    {formatConfidence(e.confidence)}
                  </span>
                  <span>{formatRelativeDate(e.updated_at)}</span>
                  <span className="min-w-0 truncate" title={e.project_id ?? ''}>
                    {e.project_id ?? t('entities.table.global')}
                  </span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
