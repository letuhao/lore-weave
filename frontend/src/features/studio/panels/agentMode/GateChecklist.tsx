// Pure render of a GateCheckItem[] (#20_agent_mode.md §2/§4). Shared by
// NewRunView's pre-flight checklist and MissionControlView's post-gate panel
// so both surfaces render the identical real derivation.
import { useTranslation } from 'react-i18next';
import type { GateCheckItem } from '@/features/composition/authoringRuns/gateChecks';

const LABEL_KEYS: Record<GateCheckItem['id'], string> = {
  plan: 'authoringRun.gate.checkPlan',
  scope: 'authoringRun.gate.checkScope',
  budget: 'authoringRun.gate.checkBudget',
  allowlist: 'authoringRun.gate.checkAllowlist',
};
const LABEL_DEFAULTS: Record<GateCheckItem['id'], string> = {
  plan: 'Plan exists and is approved',
  scope: 'Scope chapters exist & are orderable',
  budget: 'Budget declared (> $0)',
  allowlist: 'Tool allowlist configured',
};

export function GateChecklist({ items }: { items: GateCheckItem[] }) {
  const { t } = useTranslation('composition');
  return (
    <div data-testid="agent-mode-gate-checklist">
      {items.map((item) => (
        <div
          key={item.id}
          data-testid={`agent-mode-gate-check-${item.id}`}
          data-passed={item.passed}
          className="flex items-center gap-2 border-b py-1.5 text-xs last:border-b-0"
        >
          <span className={item.passed ? 'font-bold text-success' : 'font-bold text-destructive'}>
            {item.passed ? '✓' : '✕'}
          </span>
          <span>{t(LABEL_KEYS[item.id], { defaultValue: LABEL_DEFAULTS[item.id] })}</span>
          <span className="ml-auto text-[10.5px] text-muted-foreground">{item.detail}</span>
        </div>
      ))}
    </div>
  );
}
