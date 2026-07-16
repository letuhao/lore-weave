// M2 view — the unified activity feed. Keyset infinite scroll (load-more), a global mark-all-read,
// an unread badge, and honest empty/error states. Bound to useActivity (logic) — view only.
import { Bell, CheckCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useActivity } from '../hooks/useActivity';
import type { ActivityItem } from '../types';

function timeAgo(iso: string): string {
  // Lightweight relative time — the exact instant isn't the point on a feed.
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  if (Number.isNaN(then)) return '';
  const min = Math.floor(diff / 60_000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  return `${Math.floor(hr / 24)}d`;
}

export function ActivityPage() {
  const { items, unread, isLoading, error, hasMore, isFetchingMore, loadMore, markAllRead, markingAll } =
    useActivity();

  const needsYou = items.filter((i) => !i.read_at);
  const earlier = items.filter((i) => i.read_at);

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-3 pb-6" data-testid="activity-page">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-2 font-serif text-lg font-semibold">
          Activity
          {unread > 0 && (
            <span
              className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground"
              data-testid="activity-unread-badge"
            >
              {unread}
            </span>
          )}
        </h1>
        <button
          type="button"
          data-testid="activity-mark-all"
          disabled={markingAll || unread === 0}
          onClick={() => markAllRead()}
          className="flex min-h-[36px] items-center gap-1 rounded-md px-2 text-sm text-primary disabled:opacity-40"
        >
          <CheckCheck className="h-4 w-4" aria-hidden="true" />
          Mark all read
        </button>
      </div>

      {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="py-6 text-center text-sm text-destructive">Couldn&apos;t load your activity.</p>}
      {!isLoading && !error && items.length === 0 && (
        <p className="py-10 text-center text-sm text-muted-foreground">Nothing yet — your notifications land here.</p>
      )}

      {/* Grouped like the draft: unread items that want attention ("Needs you") above read/older
          items ("Earlier"). Unread is the data-driven proxy for "actionable". */}
      {needsYou.length > 0 && (
        <section data-testid="activity-needs-you">
          <GroupHead label="Needs you" />
          <ul className="flex flex-col gap-2">
            {needsYou.map((item) => (
              <ActivityRow key={item.id} item={item} />
            ))}
          </ul>
        </section>
      )}
      {earlier.length > 0 && (
        <section data-testid="activity-earlier">
          <GroupHead label="Earlier" />
          <ul className="flex flex-col gap-2">
            {earlier.map((item) => (
              <ActivityRow key={item.id} item={item} />
            ))}
          </ul>
        </section>
      )}

      {hasMore && (
        <button
          type="button"
          data-testid="activity-load-more"
          disabled={isFetchingMore}
          onClick={() => loadMore()}
          className="mx-auto min-h-[44px] rounded-md border border-border px-4 text-sm text-muted-foreground disabled:opacity-50"
        >
          {isFetchingMore ? 'Loading…' : 'Load more'}
        </button>
      )}
    </div>
  );
}

function GroupHead({ label }: { label: string }) {
  return (
    <h2 className="mb-2 mt-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</h2>
  );
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const unread = !item.read_at;
  return (
    <li
      className={cn(
        'flex items-start gap-3 rounded-lg border border-border bg-card p-3',
        unread && 'border-primary/40',
      )}
    >
      <span className={cn('mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full', unread ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground')}>
        <Bell className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{item.title}</span>
          {unread && <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
        </div>
        {item.body && <p className="truncate text-xs text-muted-foreground">{item.body}</p>}
        <p className="text-[11px] text-muted-foreground">
          {item.category} · {timeAgo(item.created_at)}
        </p>
      </div>
    </li>
  );
}
