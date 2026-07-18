// Activity bar (fixed) — the far-left icon rail that switches the Side Bar's navigator.
// Clicking the active one collapses the side bar (VS Code behaviour, handled in the hook).
import { useTranslation } from 'react-i18next';
import { BookOpen, BookMarked, Network, Search, BadgeCheck, Settings, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { ACTIVITY_VIEWS, type ActivityView } from '../types';

const ICONS: Record<ActivityView, LucideIcon> = {
  manuscript: BookOpen,
  plan: Network, // 24 PH25 — the Plan navigator: the same dataset as the Hub canvas, at list density
  bible: BookMarked,
  search: Search,
  quality: BadgeCheck,
};

interface Props {
  bookId: string;
  activeView: ActivityView;
  sidebarCollapsed: boolean;
  onSelect: (view: ActivityView) => void;
}

export function StudioActivityBar({ bookId, activeView, sidebarCollapsed, onSelect }: Props) {
  const { t } = useTranslation('studio');
  return (
    <div className="flex w-[52px] flex-shrink-0 flex-col items-center gap-1 border-r bg-card py-2">
      {ACTIVITY_VIEWS.map((view) => {
        const Icon = ICONS[view];
        const active = view === activeView && !sidebarCollapsed;
        return (
          <button
            key={view}
            type="button"
            data-testid={`studio-activity-${view}`}
            aria-pressed={active}
            onClick={() => onSelect(view)}
            title={t(`activity.${view}`, { defaultValue: view })}
            className={cn(
              'relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors',
              active
                ? 'bg-primary/15 text-primary before:absolute before:-left-2 before:top-2 before:bottom-2 before:w-0.5 before:rounded before:bg-primary'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
            )}
          >
            <Icon className="h-5 w-5" />
          </button>
        );
      })}

      <div className="flex-1" />

      <Link
        to={`/books/${bookId}/settings`}
        title={t('settings', { defaultValue: 'Book settings' })}
        className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <Settings className="h-5 w-5" />
      </Link>
    </div>
  );
}
