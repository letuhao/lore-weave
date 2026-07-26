// M2 + DF1 — the platform home, rebuilt to the mobile-home draft: a greeting top bar, the assistant
// hero (the first feature) with a Start-talking CTA + mic + a privacy status line, a horizontal
// "jump back in" rail of rich per-workshop cards, the app launcher, and an inline recent-activity
// feed. The assistant hero is STATIC (always renders → the front door never blanks); the tiles/feed
// render by their degrade status. Bound to useHome + useActivity (logic) — view only.
import { Link } from 'react-router-dom';
import {
  Sparkles, ArrowRight, Mic, BookOpen, Languages, Globe2, Search, Bell, ChevronRight, Grid3x3, Brain,
  Factory, NotebookPen, ListChecks,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { useHome } from '../hooks/useHome';
import { useActivity } from '../hooks/useActivity';
import { AllAppsDrawer, APPS_SHEET_ID } from './AllAppsDrawer';
import { useSheetRoute } from '@/components/shared/Sheet';
import type { HomeBook, HomeJob } from '../types';

const LAUNCHER = [
  { to: '/books', icon: BookOpen, label: 'Write' },
  { to: '/worlds', icon: Globe2, label: 'Worlds' },
  { to: '/knowledge', icon: Brain, label: 'Knowledge' },
  { to: '/campaigns', icon: Factory, label: 'Campaigns' },
];

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}
function today(): string {
  return new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
}
function timeAgo(iso?: string): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(diff)) return '';
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const hr = Math.floor(m / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

export function PlatformHomePage() {
  const { user } = useAuth();
  const { data, isLoading, refetch } = useHome();
  const { openSheet } = useSheetRoute();
  const activity = useActivity();
  const tiles = data?.tiles;
  const name = (user?.display_name || user?.email || '').split(/[ @]/)[0];
  const initial = (user?.display_name || user?.email || 'U').charAt(0).toUpperCase();
  const unread = tiles?.activity.data?.unread ?? activity.unread ?? 0;

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-4 pb-6" data-testid="platform-home">
      {/* Top bar — avatar · greeting+date · search · notifications */}
      <div className="flex items-center gap-3">
        <Link
          to="/you"
          aria-label="Your account"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/20 text-base font-semibold text-primary"
        >
          {initial}
        </Link>
        <div className="min-w-0 flex-1">
          <div className="truncate font-serif text-base font-semibold">
            {greeting()}{name ? `, ${name}` : ''}
          </div>
          <div className="text-xs text-muted-foreground">{today()}</div>
        </div>
        <Link to="/browse" aria-label="Search" className="flex h-10 w-10 items-center justify-center rounded-full text-muted-foreground hover:bg-secondary">
          <Search className="h-5 w-5" aria-hidden="true" />
        </Link>
        <Link to="/activity" aria-label={`Notifications, ${unread} unread`} className="relative flex h-10 w-10 items-center justify-center rounded-full text-muted-foreground hover:bg-secondary">
          <Bell className="h-5 w-5" aria-hidden="true" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Link>
      </div>

      {/* Assistant hero — the first feature (static, never blanks) */}
      <div className="rounded-2xl border border-primary/25 bg-primary/10 p-4" data-testid="home-assistant-hero">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" /> Your assistant
        </span>
        <h2 className="mt-2 font-serif text-xl font-semibold">Talk through your day.</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          I&apos;ll quietly notice the people, projects and decisions — kept private, saved only when you review.
        </p>
        <div className="mt-3 flex items-center gap-2">
          <Link
            to="/assistant"
            data-testid="home-start-talking"
            className="flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
          >
            Start talking <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <Link
            to="/assistant"
            aria-label="Talk by voice"
            className="flex h-11 w-11 items-center justify-center rounded-xl border border-primary/30 text-primary hover:bg-primary/10"
          >
            <Mic className="h-5 w-5" aria-hidden="true" />
          </Link>
        </div>
        <div className="mt-2.5 flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
          Kept private · saved only when you review
        </div>
      </div>

      {/* Jump back in — horizontal rail of rich per-workshop cards */}
      <section>
        <SectionHead title="Jump back in" to="/books" action="See all" />
        {isLoading && !tiles ? (
          <p className="px-1 text-sm text-muted-foreground">Loading…</p>
        ) : tiles?.books.status === 'degraded' && tiles?.jobs.status === 'degraded' ? (
          <RetryLine onRetry={refetch} />
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-1" data-testid="home-jump-back-in">
            {(tiles?.books.data ?? []).map((b, i) => <BookCard key={b.id || `b${i}`} book={b} />)}
            {(tiles?.jobs.data ?? []).map((j, i) => <JobCard key={j.id || `j${i}`} job={j} />)}
            {(tiles?.books.data?.length ?? 0) === 0 && (tiles?.jobs.data?.length ?? 0) === 0 && (
              <p className="px-1 text-sm text-muted-foreground">Nothing recent yet — start a book from the Library.</p>
            )}
          </div>
        )}
      </section>

      {/* Do something — the launcher + All apps */}
      <section>
        <SectionHead title="Do something" />
        <div className="grid grid-cols-5 gap-2" data-testid="home-launcher">
          {LAUNCHER.map((l) => (
            <Link key={l.label} to={l.to} className="flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl border border-border bg-card text-[11px] text-muted-foreground hover:text-foreground">
              <l.icon className="h-5 w-5" aria-hidden="true" />
              {l.label}
            </Link>
          ))}
          <button type="button" data-testid="home-all-apps" onClick={() => openSheet(APPS_SHEET_ID)} className="flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl border border-border bg-card text-[11px] text-muted-foreground hover:text-foreground">
            <Grid3x3 className="h-5 w-5" aria-hidden="true" />
            All apps
          </button>
        </div>
      </section>

      {/* Recent — inline activity feed preview */}
      <section>
        <SectionHead title="Recent" to="/activity" action="See all" />
        <div className="flex flex-col gap-2" data-testid="home-recent-feed">
          {activity.isLoading ? (
            <p className="px-1 text-sm text-muted-foreground">Loading…</p>
          ) : activity.items.length === 0 ? (
            <p className="px-1 text-sm text-muted-foreground">You&apos;re all caught up.</p>
          ) : (
            activity.items.slice(0, 3).map((it) => (
              <Link key={it.id} to="/activity" className="flex items-start gap-3 rounded-lg border border-border bg-card p-3">
                <span className={cn('mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full', !it.read_at ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground')}>
                  <Bell className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{it.title}</span>
                  <span className="block text-[11px] text-muted-foreground">{it.category} · {timeAgo(it.created_at)}</span>
                </span>
              </Link>
            ))
          )}
        </div>
      </section>

      <AllAppsDrawer />
    </div>
  );
}

function SectionHead({ title, to, action }: { title: string; to?: string; action?: string }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h2 className="text-sm font-semibold">{title}</h2>
      {to && action && (
        <Link to={to} className="flex items-center gap-1 text-xs text-primary">
          {action} <ChevronRight className="h-3 w-3" />
        </Link>
      )}
    </div>
  );
}

function RetryLine({ onRetry }: { onRetry: () => void }) {
  return (
    <p className="px-1 text-sm text-muted-foreground">
      Couldn&apos;t load right now.{' '}
      <button type="button" onClick={onRetry} className="text-primary underline-offset-2 hover:underline">Retry</button>
    </p>
  );
}

function BookCard({ book }: { book: HomeBook }) {
  return (
    <Link to={`/books/${book.id}`} className="flex w-44 shrink-0 flex-col gap-1 rounded-xl border border-border bg-card p-3">
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-primary">
        <NotebookPen className="h-3.5 w-3.5" aria-hidden="true" /> Writing
      </span>
      <span className="truncate text-sm font-medium">{book.title}</span>
      <span className="text-xs text-muted-foreground">Updated {timeAgo(book.updated_at)}</span>
    </Link>
  );
}

function JobCard({ job }: { job: HomeJob }) {
  const label = (job.kind || 'job').replace(/_/g, ' ');
  return (
    <Link to="/jobs" className="flex w-44 shrink-0 flex-col gap-1 rounded-xl border border-border bg-card p-3">
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-accent">
        <ListChecks className="h-3.5 w-3.5" aria-hidden="true" /> {label}
      </span>
      <span className="truncate text-sm font-medium capitalize">{label}</span>
      <span className="text-xs capitalize text-muted-foreground">{job.status ?? 'running'}</span>
    </Link>
  );
}
