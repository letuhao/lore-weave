import { useTranslation } from 'react-i18next';
import type { GlossaryEntityStat } from '../api';
import type { usePinning } from '../hooks/usePinning';

// C13 — build-wizard Step-2 glossary-pinning dual-list (VIEW only). Renders the
// available↔pinned lists + filters + auto-pin banner + per-window budget. All
// logic + state live in usePinning; this component just renders + emits events.

type Pinning = ReturnType<typeof usePinning>;

interface Props {
  pinning: Pinning;
}

function EntityChip({
  stat,
  action,
  actionLabel,
  onAction,
}: {
  stat: GlossaryEntityStat;
  action: 'pin' | 'unpin';
  actionLabel: string;
  onAction: (id: string) => void;
}) {
  const span =
    stat.first_chapter_index != null && stat.last_chapter_index != null
      ? `${stat.first_chapter_index}–${stat.last_chapter_index}`
      : '—';
  return (
    <li
      className="flex items-center justify-between gap-2 rounded border px-2 py-1 text-[12px]"
      data-testid={`pin-row-${stat.entity_id}`}
    >
      <span className="min-w-0 flex-1 truncate">
        <span className="font-medium">{stat.name}</span>{' '}
        <span className="text-muted-foreground">
          · {stat.kind} · ×{stat.mention_count} · ch {span} ·{' '}
          {Math.round(stat.coverage_pct * 100)}%
        </span>
      </span>
      <button
        type="button"
        onClick={() => onAction(stat.entity_id)}
        aria-label={`${actionLabel}: ${stat.name}`}
        data-testid={`pin-${action}-${stat.entity_id}`}
        className={[
          'shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium',
          action === 'pin'
            ? 'bg-primary text-primary-foreground hover:bg-primary/90'
            : 'border hover:bg-secondary',
        ].join(' ')}
      >
        {action === 'pin' ? '+' : '×'}
      </button>
    </li>
  );
}

export function PinningStep({ pinning }: Props) {
  const { t } = useTranslation('knowledge');
  const {
    statsQuery,
    available,
    pinned,
    kinds,
    filter,
    setFilter,
    pin,
    unpin,
    applySuggestions,
    pendingSuggestions,
    perWindowTokens,
  } = pinning;

  const PIN = 'projects.buildDialog.pinning';

  return (
    <div className="flex flex-col gap-3" data-testid="pinning-step">
      <p className="text-[12px] text-muted-foreground">{t(`${PIN}.intro`)}</p>

      {/* Auto-pin suggestion banner — only when there are unpinned candidates. */}
      {pendingSuggestions.length > 0 && (
        <div
          className="flex items-center justify-between gap-2 rounded-md border border-primary/40 bg-primary/5 px-3 py-2 text-[12px]"
          data-testid="autopin-banner"
        >
          <span>{t(`${PIN}.autopin`, { count: pendingSuggestions.length })}</span>
          <button
            type="button"
            onClick={applySuggestions}
            data-testid="autopin-apply"
            className="shrink-0 rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"
          >
            {t(`${PIN}.autopinApply`, { count: pendingSuggestions.length })}
          </button>
        </div>
      )}

      {statsQuery.isLoading && (
        <p className="text-[12px] text-muted-foreground">{t(`${PIN}.loading`)}</p>
      )}
      {statsQuery.error != null && (
        <p className="text-[12px] text-muted-foreground" data-testid="pinning-degraded">
          {t(`${PIN}.unavailable`)}
        </p>
      )}

      {/* Filters over the available list. */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={filter.search}
          onChange={(e) => setFilter({ ...filter, search: e.target.value })}
          placeholder={t(`${PIN}.searchPlaceholder`)}
          aria-label={t(`${PIN}.searchPlaceholder`)}
          className="min-w-[8rem] flex-1 rounded-md border bg-input px-2 py-1 text-[12px] outline-none focus:border-ring"
          data-testid="pinning-search"
        />
        <select
          value={filter.kind}
          onChange={(e) => setFilter({ ...filter, kind: e.target.value })}
          aria-label={t(`${PIN}.kindAll`)}
          className="rounded-md border bg-input px-2 py-1 text-[12px] outline-none focus:border-ring"
          data-testid="pinning-kind"
        >
          <option value="">{t(`${PIN}.kindAll`)}</option>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={0}
          inputMode="numeric"
          value={filter.minMentions || ''}
          onChange={(e) =>
            setFilter({ ...filter, minMentions: Number(e.target.value) || 0 })
          }
          placeholder={t(`${PIN}.minMentions`)}
          aria-label={t(`${PIN}.minMentions`)}
          className="w-20 rounded-md border bg-input px-2 py-1 text-[12px] outline-none focus:border-ring"
          data-testid="pinning-min-mentions"
        />
      </div>

      {/* Dual list: available ↔ pinned. */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <h5 className="text-[11px] font-medium text-muted-foreground">
            {t(`${PIN}.available`, { count: available.length })}
          </h5>
          <ul
            className="flex max-h-48 flex-col gap-1 overflow-y-auto"
            data-testid="pinning-available"
          >
            {available.map((s) => (
              <EntityChip
                key={s.entity_id}
                stat={s}
                action="pin"
                actionLabel={t(`${PIN}.pin`)}
                onAction={pin}
              />
            ))}
            {available.length === 0 && !statsQuery.isLoading && (
              <li className="text-[11px] text-muted-foreground">
                {t(`${PIN}.availableEmpty`)}
              </li>
            )}
          </ul>
        </div>
        <div className="flex flex-col gap-1">
          <h5 className="text-[11px] font-medium text-muted-foreground">
            {t(`${PIN}.pinned`, { count: pinned.length })}
          </h5>
          <ul
            className="flex max-h-48 flex-col gap-1 overflow-y-auto"
            data-testid="pinning-pinned"
          >
            {pinned.map((s) => (
              <EntityChip
                key={s.entity_id}
                stat={s}
                action="unpin"
                actionLabel={t(`${PIN}.unpin`)}
                onAction={unpin}
              />
            ))}
            {pinned.length === 0 && (
              <li className="text-[11px] text-muted-foreground">
                {t(`${PIN}.pinnedEmpty`)}
              </li>
            )}
          </ul>
        </div>
      </div>

      {/* Per-window token budget — the dominant pinned-injection cost driver. */}
      {pinned.length > 0 && (
        <p
          className="text-[11px] text-muted-foreground"
          data-testid="pinning-budget"
        >
          {t(`${PIN}.budget`, { tokens: perWindowTokens, count: pinned.length })}
        </p>
      )}
    </div>
  );
}
