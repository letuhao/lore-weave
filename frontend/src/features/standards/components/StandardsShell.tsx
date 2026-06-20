import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Tags, Boxes, ListTree, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { GenresPanel } from './GenresPanel';
import { KindsPanel } from './KindsPanel';
import { AttributesPanel } from './AttributesPanel';
import { TrashDrawer } from './TrashDrawer';

export type StandardsTab = 'genres' | 'kinds' | 'attributes';
export const STANDARDS_TABS: StandardsTab[] = ['genres', 'kinds', 'attributes'];

const TAB_ICON: Record<StandardsTab, React.ComponentType<{ className?: string }>> = {
  genres: Tags,
  kinds: Boxes,
  attributes: ListTree,
};

/** The Standards Library shell: tab bar + the active panel. View-only; panels own data. */
export function StandardsShell({ tab }: { tab: StandardsTab }) {
  const { t } = useTranslation('standards');
  const [trashOpen, setTrashOpen] = useState(false);

  return (
    <div data-testid="standards-shell">
      <div className="mb-4 flex items-center justify-between border-b">
        <nav className="flex gap-0" role="tablist" aria-label={t('tabs_aria')}>
        {STANDARDS_TABS.map((id) => {
          const Icon = TAB_ICON[id];
          return (
            <Link
              key={id}
              to={`/standards/${id}`}
              role="tab"
              aria-selected={tab === id}
              className={cn(
                '-mb-px flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
                tab === id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
              data-testid={`standards-tab-${id}`}
            >
              <Icon className="h-3.5 w-3.5" />
              {t(`tab.${id}`)}
            </Link>
          );
        })}
        </nav>
        <button onClick={() => setTrashOpen(true)} className="mb-1 inline-flex items-center gap-1 rounded border px-2.5 py-1 text-[12px] font-medium text-muted-foreground hover:text-foreground" data-testid="standards-trash-open">
          <Trash2 className="h-3.5 w-3.5" />
          {t('trash.open')}
        </button>
      </div>

      {tab === 'genres' && <GenresPanel />}
      {tab === 'kinds' && <KindsPanel />}
      {tab === 'attributes' && <AttributesPanel />}

      {trashOpen && <TrashDrawer onClose={() => setTrashOpen(false)} />}
    </div>
  );
}
