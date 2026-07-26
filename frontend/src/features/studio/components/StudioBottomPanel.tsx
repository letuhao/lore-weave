// Bottom panel (toggle) — the VS Code "panel" analogue: Jobs / Generation / Issues.
// S-10 O3: Issues is now a real ranked problems feed (StudioIssuesFeed); Jobs / Generation launch the
// existing jobs feed (jobs-list panel) instead of a dead stub.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useStudioHost } from '../host/StudioHostProvider';
import { StudioIssuesFeed } from './StudioIssuesFeed';

type BottomTab = 'jobs' | 'generation' | 'issues';
const TABS: BottomTab[] = ['jobs', 'generation', 'issues'];

export function StudioBottomPanel({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation('studio');
  const { openPanel } = useStudioHost();
  const [tab, setTab] = useState<BottomTab>('jobs');

  return (
    <div data-testid="studio-bottom" className="flex h-[168px] flex-shrink-0 flex-col border-t bg-card">
      <div className="flex h-8 flex-shrink-0 items-stretch border-b">
        {TABS.map((tb) => (
          <button
            key={tb}
            type="button"
            onClick={() => setTab(tb)}
            className={cn(
              'relative px-3 text-xs font-medium transition-colors',
              tab === tb
                ? 'text-foreground after:absolute after:inset-x-0 after:top-0 after:h-0.5 after:bg-primary'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`bottom.${tb}`, { defaultValue: tb })}
          </button>
        ))}
        <div className="flex-1" />
        <button
          type="button"
          onClick={onClose}
          title={t('bottom.collapse', { defaultValue: 'Collapse panel' })}
          className="flex w-8 items-center justify-center text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {tab === 'issues' ? (
          <StudioIssuesFeed />
        ) : (
          // Jobs / Generation — the existing jobs feed lives in its own dock panel; launch it rather
          // than fork a second feed here (the stub said "wired later"; this wires it).
          <div className="flex flex-1 flex-col items-center justify-center gap-2 p-4 text-center text-[11px] text-muted-foreground">
            <p>{t(`bottom.launch.${tab}`, { defaultValue: 'The jobs feed opens in its own panel.' })}</p>
            <button
              type="button"
              data-testid={`studio-bottom-open-jobs-${tab}`}
              onClick={() => openPanel('jobs-list', { focus: true })}
              className="rounded border px-3 py-1 text-[11px] text-foreground/80 hover:bg-secondary hover:text-foreground"
            >
              {t('bottom.openJobs', { defaultValue: 'Open the Jobs panel' })}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
