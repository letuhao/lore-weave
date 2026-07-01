// Bottom panel (toggle) — the VS Code "panel" analogue: Jobs / Generation / Issues. Bodies
// are stubs in the skeleton; each becomes a real feed as its producing feature is wired.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

type BottomTab = 'jobs' | 'generation' | 'issues';
const TABS: BottomTab[] = ['jobs', 'generation', 'issues'];

export function StudioBottomPanel({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation('studio');
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
      <div className="flex flex-1 items-center justify-center overflow-y-auto p-4 text-center text-[11px] text-muted-foreground">
        {t(`bottomStub.${tab}`, { defaultValue: 'Feed appears here once wired.' })}
      </div>
    </div>
  );
}
