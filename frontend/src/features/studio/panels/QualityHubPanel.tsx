// Studio Quality tab — `quality` hub (DOCK-8 launcher pattern, same shape as the
// Knowledge hub): 4 static cards, each opening its own sibling capability panel.
// Not a monolithic tabbed panel — critic scores / promise ledger / promise
// coverage / canon issues are 4 genuinely distinct data sources (see the plan
// doc's reality map), so each is its own dock panel a la kg-overview/kg-entities/….
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { useQualityWork } from './useQualityWork';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

const CARDS = [
  { panelId: 'quality-promises', icon: '🔓', titleKey: 'promisesTitle', descKey: 'promisesDesc' },
  { panelId: 'quality-critic', icon: '🎯', titleKey: 'criticTitle', descKey: 'criticDesc' },
  { panelId: 'quality-coverage', icon: '📖', titleKey: 'coverageTitle', descKey: 'coverageDesc' },
  { panelId: 'quality-canon', icon: '⚠️', titleKey: 'canonTitle', descKey: 'canonDesc' },
] as const;

export function QualityHubPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  // The hub fronts all four quality panels, so the same rule applies here: telling the user to
  // "start composing a chapter first" when composition-service is simply DOWN is a wrong answer,
  // not a nudge — and it invites a duplicate Work. One gate, shared with the panels themselves.
  const work = useQualityWork(host.bookId, accessToken);

  return (
    <div data-testid="studio-quality-hub-panel" className="h-full min-h-0 overflow-auto p-4">
      {work.kind === 'unavailable' && (
        <p data-testid="quality-hub-unavailable" className="mb-3 text-xs text-amber-700 dark:text-amber-300">
          {t('quality.hubUnavailable', {
            defaultValue: 'Could not reach the co-writer service, so promises, critic scores and story coverage cannot be loaded right now. This is NOT a clean bill of health.',
          })}
        </p>
      )}
      {work.kind === 'no-work' && (
        <p data-testid="quality-hub-no-work" className="mb-3 text-xs text-neutral-500">
          {t('quality.hubNoWorkHint', {
            defaultValue: 'Promises, critic scores, and story coverage need a co-writer session — start composing a chapter first. Canon issues below still work either way.',
          })}
        </p>
      )}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {CARDS.map((c) => (
          <button
            key={c.panelId}
            type="button"
            data-testid={`quality-hub-card-${c.panelId}`}
            className="flex flex-col items-start gap-1 rounded border border-neutral-200 p-3 text-left hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
            onClick={() => host.openPanel(c.panelId)}
          >
            <span className="text-lg" aria-hidden>{c.icon}</span>
            <span className="text-sm font-medium">{t(`quality.${c.titleKey}`, { defaultValue: c.titleKey })}</span>
            <span className="text-xs text-neutral-500">{t(`quality.${c.descKey}`, { defaultValue: c.descKey })}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
