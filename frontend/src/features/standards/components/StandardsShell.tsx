import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Tags, Boxes, ListTree } from 'lucide-react';
import { cn } from '@/lib/utils';
import { GenresPanel } from './GenresPanel';
import { KindsPanel } from './KindsPanel';
import { AttributesPanel } from './AttributesPanel';

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

  return (
    <div data-testid="standards-shell">
      <nav className="mb-4 flex gap-0 border-b" role="tablist" aria-label={t('tabs_aria')}>
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

      {tab === 'genres' && <GenresPanel />}
      {tab === 'kinds' && <KindsPanel />}
      {tab === 'attributes' && <AttributesPanel />}
    </div>
  );
}
