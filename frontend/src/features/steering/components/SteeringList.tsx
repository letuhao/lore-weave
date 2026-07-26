// Render-only list of steering entries: name · mode badge · enabled toggle, with edit/delete.
// "Add" disables at the per-book row cap (20) with a note. No logic — all callbacks come from
// the SteeringManager which owns state via useSteering.
import { useTranslation } from 'react-i18next';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { STEERING_LIMITS, type SteeringEntry } from '../types';

interface Props {
  entries: SteeringEntry[];
  atCap: boolean;
  onAdd: () => void;
  onEdit: (entry: SteeringEntry) => void;
  onToggleEnabled: (entry: SteeringEntry) => void;
  onDelete: (entry: SteeringEntry) => void;
}

export function SteeringList({ entries, atCap, onAdd, onEdit, onToggleEnabled, onDelete }: Props) {
  const { t } = useTranslation('studio');
  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex flex-shrink-0 items-center gap-2 border-b px-3 py-2">
        <span className="text-[11px] text-muted-foreground">
          {t('steering.count', { n: entries.length, max: STEERING_LIMITS.maxRows })}
        </span>
        <button
          type="button" data-testid="steering-add" disabled={atCap} onClick={onAdd}
          className="ml-auto flex items-center gap-1 rounded bg-primary px-2 py-1 text-[12px] text-primary-foreground hover:opacity-90 disabled:opacity-40"
        >
          <Plus className="h-3.5 w-3.5" /> {t('steering.add')}
        </button>
      </div>
      {atCap && (
        <p data-testid="steering-cap-note" className="px-3 py-1 text-[11px] text-warning">
          {t('steering.capReached', { max: STEERING_LIMITS.maxRows })}
        </p>
      )}

      {entries.length === 0 ? (
        <p data-testid="steering-empty" className="p-6 text-center text-[12px] text-muted-foreground">
          {t('steering.empty')}
        </p>
      ) : (
        <ul className="min-h-0 flex-1 overflow-auto">
          {entries.map((e) => (
            <li
              key={e.id} data-testid={`steering-row-${e.id}`}
              className="flex items-center gap-2 border-b px-3 py-2"
            >
              <button
                type="button" data-testid={`steering-toggle-${e.id}`}
                aria-pressed={e.enabled} onClick={() => onToggleEnabled(e)}
                title={t(e.enabled ? 'steering.disable' : 'steering.enable')}
                className={cn(
                  'h-4 w-7 flex-shrink-0 rounded-full p-0.5 transition-colors',
                  e.enabled ? 'bg-primary' : 'bg-muted',
                )}
              >
                <span className={cn('block h-3 w-3 rounded-full bg-white transition-transform', e.enabled && 'translate-x-3')} />
              </button>
              <span className={cn('truncate text-[13px]', !e.enabled && 'text-muted-foreground line-through')}>{e.name}</span>
              <span className="ml-auto flex-shrink-0 rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                {t(`steering.mode.${e.inclusion_mode}`)}
              </span>
              <button
                type="button" data-testid={`steering-edit-${e.id}`} onClick={() => onEdit(e)}
                title={t('steering.form.edit')} className="rounded p-1 hover:bg-secondary"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                type="button" data-testid={`steering-delete-${e.id}`} onClick={() => onDelete(e)}
                title={t('steering.form.delete')} className="rounded p-1 text-destructive hover:bg-secondary"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
