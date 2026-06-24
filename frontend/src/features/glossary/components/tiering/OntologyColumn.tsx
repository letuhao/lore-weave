import { Plus } from 'lucide-react';
import type { Tier } from '../../tieringTypes';
import { TierChip } from './TierChip';

export interface ColumnRow {
  id: string;
  icon?: string;
  label: string;
  tier?: Tier; // provenance chip (omit to hide)
  meta?: string; // right-aligned count/note
  conflict?: boolean; // amber highlight (multi-genre keep-both)
}

type Props = {
  title: string;
  rows: ColumnRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew?: () => void;
  newLabel?: string;
  emptyText: string;
  disabled?: boolean; // e.g. column not yet selectable (no parent chosen)
};

/** One column of the Manage workspace drilldown (genres / kinds / attributes).
 *  Render-only; selection + data come from the parent (ManageWorkspace). */
export function OntologyColumn({
  title,
  rows,
  selectedId,
  onSelect,
  onNew,
  newLabel,
  emptyText,
  disabled,
}: Props) {
  return (
    <div className="flex min-h-[420px] flex-col rounded-lg border bg-card">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</span>
        {onNew && (
          <button
            type="button"
            onClick={onNew}
            disabled={disabled}
            title={newLabel}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-primary hover:bg-primary/10 disabled:opacity-40"
          >
            <Plus className="h-3 w-3" /> {newLabel}
          </button>
        )}
      </div>
      <div className="flex-1 overflow-auto p-1.5">
        {rows.length === 0 ? (
          <p className="px-2 py-3 text-xs text-muted-foreground">{emptyText}</p>
        ) : (
          <ul className="space-y-0.5">
            {rows.map((r) => {
              const active = r.id === selectedId;
              return (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(r.id)}
                    data-testid={`ontology-row-${r.id}`}
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                      active ? 'border-l-2 border-primary bg-primary/10' : 'hover:bg-secondary'
                    } ${r.conflict ? 'bg-amber-50 dark:bg-amber-950/30' : ''}`}
                  >
                    <span className="flex-1 truncate">
                      {r.icon ? `${r.icon} ` : ''}
                      {r.label}
                    </span>
                    {r.meta && <span className="font-mono text-[10px] text-muted-foreground">{r.meta}</span>}
                    {r.tier && <TierChip tier={r.tier} />}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
