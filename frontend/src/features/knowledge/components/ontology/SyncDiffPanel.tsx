import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { OntologyChip } from './OntologyChip';
import type { SyncChange, SyncChoice } from '../../types/ontology';

// Render-only sync diff (mirrors 06-sync.html). One row per upstream change with
// per-node keep_mine / take_theirs toggles + bulk actions. All decision state +
// the apply call live in useOntologySync; this only renders and emits callbacks.

const CHANGE_BADGE: Record<SyncChange['change'], { cls: string; key: string }> = {
  added: { cls: 'bg-emerald-100 text-emerald-700', key: 'sync.added' },
  modified: { cls: 'bg-amber-100 text-amber-700', key: 'sync.modified' },
  removed_upstream: { cls: 'bg-rose-100 text-rose-700', key: 'sync.removed' },
};

interface Props {
  changes: SyncChange[];
  hasUpdates: boolean;
  getChoice: (c: SyncChange) => SyncChoice;
  onSetDecision: (c: SyncChange, choice: SyncChoice) => void;
  onKeepAllMine: () => void;
  onTakeAllTheirs: () => void;
  onApply: () => void;
  isApplying: boolean;
  decidedCount: number;
}

export function SyncDiffPanel({
  changes,
  hasUpdates,
  getChoice,
  onSetDecision,
  onKeepAllMine,
  onTakeAllTheirs,
  onApply,
  isApplying,
  decidedCount,
}: Props) {
  const { t } = useTranslation('kgOntology');

  if (!hasUpdates) {
    return (
      <p className="text-[12px] text-muted-foreground" data-testid="sync-up-to-date">
        {t('sync.upToDate')}
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="sync-diff-panel">
      <div className="flex items-center justify-between">
        <b className="text-[13px]">{t('sync.updatesAvailable', { count: changes.length })}</b>
        <div className="flex gap-2 text-[12px]">
          <button
            type="button"
            onClick={onKeepAllMine}
            className="rounded-md border px-3 py-1.5"
            data-testid="sync-keep-all-mine"
          >
            {t('sync.keepAllMine')}
          </button>
          <button
            type="button"
            onClick={onTakeAllTheirs}
            className="rounded-md border px-3 py-1.5"
            data-testid="sync-take-all-theirs"
          >
            {t('sync.takeAllTheirs')}
          </button>
        </div>
      </div>

      <ul className="space-y-2">
        {changes.map((c) => {
          const badge = CHANGE_BADGE[c.change];
          const choice = getChoice(c);
          return (
            <li
              key={`${c.node_type}:${c.parent_code ?? ''}:${c.code}`}
              className="flex items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-[12px]"
              data-testid={`sync-change-${c.code}`}
            >
              <span className="flex items-center gap-2">
                <span className={cn('rounded px-1.5 text-[10px] font-bold', badge.cls)}>
                  {t(badge.key)}
                </span>
                <OntologyChip variant="edge">{c.code}</OntologyChip>
                <span className="text-muted-foreground">{c.node_type}</span>
                {c.fields_changed && c.fields_changed.length > 0 && (
                  <span className="text-muted-foreground">
                    {c.fields_changed.join(', ')}
                  </span>
                )}
              </span>
              <span className="flex gap-1 text-[11px]">
                <button
                  type="button"
                  onClick={() => onSetDecision(c, 'keep_mine')}
                  aria-pressed={choice === 'keep_mine'}
                  className={cn(
                    'rounded border px-2 py-0.5',
                    choice === 'keep_mine' && 'border-primary bg-primary/10 font-semibold',
                  )}
                  data-testid={`sync-keep-mine-${c.code}`}
                >
                  {t('sync.keepMine')}
                </button>
                <button
                  type="button"
                  onClick={() => onSetDecision(c, 'take_theirs')}
                  aria-pressed={choice === 'take_theirs'}
                  className={cn(
                    'rounded border px-2 py-0.5',
                    choice === 'take_theirs' && 'border-emerald-600 bg-emerald-600 text-white',
                  )}
                  data-testid={`sync-take-theirs-${c.code}`}
                >
                  {t('sync.takeTheirs')}
                </button>
              </span>
            </li>
          );
        })}
      </ul>

      <button
        type="button"
        onClick={onApply}
        disabled={isApplying || decidedCount === 0}
        className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-50"
        data-testid="sync-apply"
      >
        {t('sync.applyButton', { count: decidedCount })}
      </button>
    </div>
  );
}
