// M3 view — the "All apps" drawer: every workshop grouped, as an addressable sheet (?sheet=apps)
// so a deep link / Back behaves correctly. The mobile bottom bar only holds the 5 primaries; this
// is the full super-app directory. Pure view (static link registry).
import { Link } from 'react-router-dom';
import {
  BookOpen, Globe2, BookMarked, Search, NotebookPen, GraduationCap, Brain, Factory, ListChecks,
  Library, Trophy, Puzzle, BarChart3,
} from 'lucide-react';
import { Sheet, useSheetRoute } from '@/components/shared/Sheet';

export const APPS_SHEET_ID = 'apps';

const GROUPS: { title: string; apps: { to: string; icon: React.ElementType; label: string }[] }[] = [
  {
    title: 'Create',
    apps: [
      { to: '/books', icon: BookOpen, label: 'Library' },
      { to: '/worlds', icon: Globe2, label: 'Worlds' },
      { to: '/campaigns', icon: Factory, label: 'Campaigns' },
      { to: '/standards', icon: Library, label: 'Standards' },
    ],
  },
  {
    title: 'Assist',
    apps: [
      { to: '/assistant', icon: NotebookPen, label: 'Assistant' },
      { to: '/roleplay', icon: GraduationCap, label: 'Coaching' },
      { to: '/knowledge', icon: Brain, label: 'Knowledge' },
    ],
  },
  {
    title: 'Explore',
    apps: [
      { to: '/browse', icon: Search, label: 'Browse' },
      { to: '/leaderboard', icon: Trophy, label: 'Leaderboard' },
      { to: '/reading-history', icon: BookMarked, label: 'Reading' },
    ],
  },
  {
    title: 'Manage',
    apps: [
      { to: '/jobs', icon: ListChecks, label: 'Jobs' },
      { to: '/usage', icon: BarChart3, label: 'Usage' },
      { to: '/extensions', icon: Puzzle, label: 'Extensions' },
    ],
  },
];

export function AllAppsDrawer() {
  const { closeSheet } = useSheetRoute();
  return (
    <Sheet id={APPS_SHEET_ID} title="All apps" description="Every workshop in one place.">
      <div className="flex flex-col gap-4">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {group.title}
            </h3>
            <div className="grid grid-cols-4 gap-2">
              {group.apps.map((app, i) => (
                <Link
                  key={`${app.to}-${i}`}
                  to={app.to}
                  onClick={closeSheet}
                  className="flex min-h-[72px] flex-col items-center justify-center gap-1 rounded-xl border border-border bg-card text-[11px] text-muted-foreground hover:text-foreground"
                >
                  <app.icon className="h-5 w-5" aria-hidden="true" />
                  <span className="text-center leading-tight">{app.label}</span>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Sheet>
  );
}
