// #20_agent_mode.md §4 (Gate check panel) — renders only in `gated` state.
import { useTranslation } from 'react-i18next';
import { GateChecklist } from './GateChecklist';
import type { GateCheckItem } from '@/features/composition/authoringRuns/gateChecks';

export function GateCheckPanel({ items }: { items: GateCheckItem[] }) {
  const { t } = useTranslation('composition');
  return (
    <div className="mb-3 rounded-md border p-3" data-testid="agent-mode-gate-panel">
      <h3 className="mb-2 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t('authoringRun.gate.title', { defaultValue: 'Gate check result' })}
      </h3>
      <GateChecklist items={items} />
    </div>
  );
}
