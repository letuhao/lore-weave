// M2 view — the platform home (the super-app front door). The assistant hero is STATIC (renders
// regardless of the /v1/home fetch) so the front door never blanks; the jump-back-in tiles + the
// activity preview render by their degrade status. Mobile-first; on desktop it centres in the
// dashboard column. Bound to useHome (logic) — view only.
import { Link } from 'react-router-dom';
import { NotebookPen, BookOpen, ListChecks, Bell, ChevronRight, Globe2, Factory, Brain, Grid3x3 } from 'lucide-react';
import { useSheetRoute } from '@/components/shared/Sheet';
import { useHome } from '../hooks/useHome';
import { DegradeTile } from './DegradeTile';
import { AllAppsDrawer, APPS_SHEET_ID } from './AllAppsDrawer';

// Distinct destinations (each a real route) — no duplicate targets.
const LAUNCHER = [
  { to: '/books', icon: BookOpen, label: 'Library' },
  { to: '/worlds', icon: Globe2, label: 'Worlds' },
  { to: '/knowledge', icon: Brain, label: 'Knowledge' },
  { to: '/campaigns', icon: Factory, label: 'Campaigns' },
];

export function PlatformHomePage() {
  const { data, isLoading, refetch } = useHome();
  const { openSheet } = useSheetRoute();
  const tiles = data?.tiles;
  const loading = isLoading && !tiles;

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-4 pb-6" data-testid="platform-home">
      {/* Assistant hero — static, always renders (the front door never blanks). */}
      <Link
        to="/assistant"
        data-testid="home-assistant-hero"
        className="flex items-center gap-3 rounded-2xl border border-primary/30 bg-primary/10 p-4 transition-colors hover:bg-primary/15"
      >
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <NotebookPen className="h-6 w-6" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-serif text-base font-semibold">Your assistant</span>
          <span className="block text-sm text-muted-foreground">Journal your day, review what you captured.</span>
        </span>
        <ChevronRight className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
      </Link>

      {data?.stale && (
        <p className="text-center text-xs text-muted-foreground">Showing your last-loaded home.</p>
      )}

      {/* Activity preview */}
      <DegradeTile
        status={tiles?.activity.status ?? 'degraded'}
        loading={loading}
        title="Activity"
        emptyText="You're all caught up."
        onRetry={refetch}
        action={
          <Link to="/activity" className="flex items-center gap-1 text-xs text-primary" data-testid="home-activity-link">
            See all <ChevronRight className="h-3 w-3" />
          </Link>
        }
      >
        <Link to="/activity" className="flex items-center gap-2 text-sm" data-testid="home-unread">
          <Bell className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          {tiles?.activity.data?.unread ?? 0} unread
        </Link>
      </DegradeTile>

      {/* Jump back in — recent books */}
      <DegradeTile
        status={tiles?.books.status ?? 'degraded'}
        loading={loading}
        title="Jump back in"
        emptyText="Nothing recent yet. Start a book from the Library."
        onRetry={refetch}
      >
        <ul className="flex flex-col gap-1">
          {tiles?.books.data?.map((b, i) => (
            <li key={b.id || `book-${i}`}>
              <Link
                to={`/books/${b.id}`}
                className="flex min-h-[44px] items-center gap-2 rounded-md px-2 hover:bg-secondary"
              >
                <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="truncate text-sm">{b.title}</span>
              </Link>
            </li>
          ))}
        </ul>
      </DegradeTile>

      {/* Recent jobs */}
      <DegradeTile
        status={tiles?.jobs.status ?? 'degraded'}
        loading={loading}
        title="Recent work"
        emptyText="No background jobs running."
        onRetry={refetch}
        action={
          <Link to="/jobs" className="flex items-center gap-1 text-xs text-primary">
            All jobs <ChevronRight className="h-3 w-3" />
          </Link>
        }
      >
        <ul className="flex flex-col gap-1">
          {tiles?.jobs.data?.map((j, i) => (
            <li key={j.id || `job-${i}`} className="flex min-h-[36px] items-center gap-2 px-2 text-sm">
              <ListChecks className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="truncate">{j.kind ?? 'Job'}</span>
              <span className="ml-auto text-xs text-muted-foreground">{j.status}</span>
            </li>
          ))}
        </ul>
      </DegradeTile>

      {/* Launcher */}
      <section className="grid grid-cols-4 gap-2" data-testid="home-launcher">
        {LAUNCHER.map((l) => (
          <Link
            key={l.label}
            to={l.to}
            className="flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl border border-border bg-card text-[11px] text-muted-foreground hover:text-foreground"
          >
            <l.icon className="h-5 w-5" aria-hidden="true" />
            {l.label}
          </Link>
        ))}
        <button
          type="button"
          data-testid="home-all-apps"
          onClick={() => openSheet(APPS_SHEET_ID)}
          className="flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl border border-border bg-card text-[11px] text-muted-foreground hover:text-foreground"
        >
          <Grid3x3 className="h-5 w-5" aria-hidden="true" />
          All apps
        </button>
      </section>

      <AllAppsDrawer />
    </div>
  );
}
