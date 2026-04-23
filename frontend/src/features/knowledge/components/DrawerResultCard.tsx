import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { DrawerSearchHit } from '../api';

// K19e.4 — presentational drawer result card. Rendered as a focusable
// button so keyboard users can open the detail slide-over via
// Enter/Space (matches K19d β EntitiesTable + K19e β TimelineEventRow).
// Click/toggle state lives in the parent tab — this component is
// purely display.

export interface DrawerResultCardProps {
  hit: DrawerSearchHit;
  onOpen: () => void;
}

const TEXT_PREVIEW_MAX = 160;

const SOURCE_TYPE_CLASSES: Record<string, string> = {
  chapter: 'bg-blue-500/10 text-blue-700 dark:text-blue-300',
  chat: 'bg-purple-500/10 text-purple-700 dark:text-purple-300',
  glossary: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
};

function formatMatchPercent(raw: number): string {
  // Clamp to [0, 100] — carries the K19e β L3 lesson (bad data import
  // should surface as 0% / 100% not -12% / 130%).
  const pct = Math.round(raw * 100);
  return `${Math.max(0, Math.min(100, pct))}%`;
}

function sourceIdShort(sourceId: string): string {
  return sourceId.length > 8 ? `…${sourceId.slice(-8)}` : sourceId;
}

function textPreview(text: string): string {
  if (text.length <= TEXT_PREVIEW_MAX) return text;
  return text.slice(0, TEXT_PREVIEW_MAX).trimEnd() + '…';
}

export function DrawerResultCard({ hit, onOpen }: DrawerResultCardProps) {
  const { t } = useTranslation('knowledge');
  const sourceClass =
    SOURCE_TYPE_CLASSES[hit.source_type] ??
    'bg-muted text-muted-foreground';

  return (
    <li data-testid="drawer-result">
      <button
        type="button"
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            onOpen();
          }
        }}
        aria-label={t('drawers.card.openLabel', {
          sourceType: hit.source_type,
          score: formatMatchPercent(hit.raw_score),
        })}
        className={cn(
          'grid w-full grid-cols-[auto_1fr_auto] items-start gap-3 px-3 py-2.5 text-left text-[12px] transition-colors hover:bg-muted/50',
        )}
        data-testid="drawer-result-card"
      >
        <span className="flex flex-col items-start gap-1">
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
              sourceClass,
            )}
            title={hit.source_type}
          >
            {hit.source_type}
          </span>
          {hit.is_hub && (
            <span
              className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700 dark:text-amber-300"
              title={t('drawers.card.hubHint')}
              data-testid="drawer-result-hub-badge"
            >
              {t('drawers.card.hubBadge')}
            </span>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            <span>
              {t('drawers.card.sourcePrefix')}{' '}
              <code>{sourceIdShort(hit.source_id)}</code>
            </span>
            {hit.chapter_index != null && (
              <span>
                · {t('drawers.card.chapterLabel', {
                  index: hit.chapter_index,
                })}
              </span>
            )}
            <span>· {t('drawers.card.chunkLabel', {
              index: hit.chunk_index,
            })}</span>
          </span>
          <span className="line-clamp-2 whitespace-pre-wrap break-words text-foreground">
            {textPreview(hit.text)}
          </span>
        </span>
        <span
          className="pt-[2px] text-right text-[11px] font-medium tabular-nums text-muted-foreground"
          title={t('drawers.card.matchLabel')}
        >
          {formatMatchPercent(hit.raw_score)}
        </span>
      </button>
    </li>
  );
}
