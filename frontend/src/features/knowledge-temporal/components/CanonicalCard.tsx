import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useAsOf } from '../context/AsOfContext';
import { useCanonical } from '../hooks/useTemporalReads';

export interface TemporalSurfaceProps {
  bookId: string;
  entityId: string;
}

/**
 * X6c — Canonical card: the entity's AS-OF folded canonical (useCanonical), keyed to the shared
 * AsOf story-time. Renders the folded `content` prose, a status chip (current/stale/unbuildable),
 * and an "as of chapter N" / "current" label. Degrades, never crashes: an `unbuildable` status or
 * a `canon-content` source surfaces a subtle degrade note; a failed read shows an inline message.
 */
export function CanonicalCard({ bookId, entityId }: TemporalSurfaceProps) {
  const { t } = useTranslation('knowledge');
  const { asOf } = useAsOf();
  const { canonical, isLoading, error } = useCanonical(bookId, entityId, asOf);

  if (isLoading) {
    return (
      <section
        data-testid="canonical-card"
        className="space-y-2"
        aria-busy="true"
      >
        <div className="flex items-center gap-2">
          <div className="h-4 w-16 animate-pulse rounded bg-muted" />
          <div className="h-3 w-24 animate-pulse rounded bg-muted" />
        </div>
        <div className="h-3 w-full animate-pulse rounded bg-muted" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-muted" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
      </section>
    );
  }

  if (error) {
    return (
      <section
        data-testid="canonical-card"
        role="alert"
        className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
      >
        {t('temporal.canonical.loadFailed', 'Could not load the canonical for this point in the story.')}
      </section>
    );
  }

  const status = canonical?.canonical_status ?? 'current';
  const isUnbuildable = status === 'unbuildable';
  // 'snapshot' = a fresh fold; 'canon-content' = the degrade fallback to authored canon.
  const isDegradeSource = canonical?.source === 'canon-content';

  // as_of_ordinal: -1 is the cold-start sentinel; treat anything <0 or nullish as "current head".
  const ordinal = canonical?.as_of_ordinal;
  const hasOrdinal = typeof ordinal === 'number' && ordinal >= 0;

  return (
    <section data-testid="canonical-card" className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip status={status} t={t} />
        <span
          className="text-[11px] text-muted-foreground"
          data-testid="canonical-asof-label"
        >
          {hasOrdinal
            ? t('temporal.canonical.asOfChapter', { ordinal, defaultValue: 'As of chapter {{ordinal}}' })
            : t('temporal.canonical.current', 'current')}
        </span>
        {isDegradeSource && !isUnbuildable && (
          <span
            className="text-[10px] text-muted-foreground/80"
            data-testid="canonical-source-note"
            title={t(
              'temporal.canonical.sourceCanonContentHint',
              'Showing authored canon (no folded snapshot for this point).',
            )}
          >
            {t('temporal.canonical.sourceCanonContent', 'authored canon')}
          </span>
        )}
      </div>

      {isUnbuildable || !canonical?.content ? (
        <p
          className="rounded-md border border-dashed px-3 py-3 text-[12px] text-muted-foreground"
          data-testid="canonical-unbuildable"
        >
          {t(
            'temporal.canonical.unbuildable',
            'Synthesis unavailable here — degrade-safe.',
          )}
        </p>
      ) : (
        <p
          className={cn(
            'whitespace-pre-wrap text-[12px] leading-relaxed',
            status === 'stale' && 'text-foreground/90',
          )}
          data-testid="canonical-content"
        >
          {canonical.content}
        </p>
      )}
    </section>
  );
}

function StatusChip({
  status,
  t,
}: {
  status: string;
  t: ReturnType<typeof useTranslation>['t'];
}) {
  const map: Record<string, { cls: string; label: string }> = {
    current: {
      cls: 'bg-muted text-muted-foreground',
      label: t('temporal.canonical.status.current', 'current'),
    },
    stale: {
      cls: 'bg-warning/20 text-warning',
      label: t('temporal.canonical.status.stale', 'stale'),
    },
    unbuildable: {
      cls: 'bg-muted/60 text-muted-foreground/70',
      label: t('temporal.canonical.status.unbuildable', 'unavailable'),
    },
  };
  const cfg = map[status] ?? map.current;
  return (
    <span
      data-testid="canonical-status"
      data-status={status}
      className={cn(
        'rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide',
        cfg.cls,
      )}
    >
      {cfg.label}
    </span>
  );
}
