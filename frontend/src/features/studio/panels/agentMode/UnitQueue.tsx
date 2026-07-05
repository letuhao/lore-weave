// #20_agent_mode.md §5 (Unit queue). Render-only.
import { useTranslation } from 'react-i18next';

export interface QueueRow {
  unit_index: number;
  chapterLabel: string;
  /** Real AuthoringRunUnitStatus, OR the synthetic 'in_progress' label used
   * while the run is running/gated/draft (the report endpoint 409s outside
   * report_ready/failed/paused/closed — see MissionControlView). */
  status: string;
  costUsd: string | null;
  severity: 'ok' | 'warn' | 'severe' | null;
  notReached: boolean;
}

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-secondary text-muted-foreground',
  in_progress: 'bg-info/10 text-info',
  drafted: 'bg-info/10 text-info',
  failed: 'bg-destructive/10 text-destructive',
  accepted: 'bg-success/10 text-success',
  rejected: 'bg-warning/10 text-warning',
};

const SEV_DOT: Record<string, string> = { ok: 'bg-success', warn: 'bg-warning', severe: 'bg-destructive' };

interface Props {
  rows: QueueRow[];
  currentUnit: number;
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

export function UnitQueue({ rows, currentUnit, selectedIndex, onSelect }: Props) {
  const { t } = useTranslation('composition');
  return (
    <div data-testid="agent-mode-unit-queue">
      <p className="mb-1.5 text-[10.5px] text-muted-foreground">
        {t('authoringRun.queue.hint', { defaultValue: 'Click a chapter to read its draft below.' })}
      </p>
      {rows.map((row) => {
        const isCurrent = row.unit_index === currentUnit;
        const isSelected = row.unit_index === selectedIndex;
        return (
          <div
            key={row.unit_index}
            data-testid="agent-mode-queue-row"
            data-unit-index={row.unit_index}
            onClick={() => onSelect(row.unit_index)}
            className={`mb-1.5 flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${
              isCurrent ? 'border-primary bg-primary/10' : ''
            } ${isSelected ? 'ring-1 ring-accent' : ''} ${row.notReached ? 'opacity-40' : ''}`}
          >
            <span className="w-5 text-center font-mono text-[10px] text-muted-foreground">{row.unit_index + 1}</span>
            <span className="flex-1 font-medium">{row.chapterLabel}</span>
            {row.severity && <span className={`h-1.5 w-1.5 rounded-full ${SEV_DOT[row.severity]}`} />}
            <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${STATUS_BADGE[row.status] ?? 'bg-secondary text-muted-foreground'}`}>
              {row.status.replace('_', ' ')}
            </span>
            <span className="w-12 text-right font-mono text-[10.5px] text-muted-foreground">
              {row.costUsd != null ? `$${row.costUsd}` : ''}
            </span>
          </div>
        );
      })}
    </div>
  );
}
