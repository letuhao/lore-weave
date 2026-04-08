import { Languages } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { LeaderboardTranslator } from './api';
import { RankMedal } from './RankMedal';

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] ?? '')
    .join('')
    .toUpperCase() || '?';
}

export function TranslatorList({
  translators,
  hasMore,
  onLoadMore,
  loading,
}: {
  translators: LeaderboardTranslator[];
  hasMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
}) {
  const { t } = useTranslation('leaderboard');
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      {translators.map((t) => (
        <div key={t.user_id} className="flex items-center gap-3.5 border-b px-4 py-3 last:border-b-0 hover:bg-card/80">
          <RankMedal rank={t.rank} />

          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
            {initials(t.display_name || 'U')}
          </div>

          <div className="min-w-0 flex-1">
            <span className="text-[13px] font-medium">{t.display_name || 'Unknown'}</span>
            <div className="mt-0.5 flex gap-1.5">
              <span className="inline-flex items-center gap-1 rounded bg-secondary px-2 py-px text-[10px] text-muted-foreground">
                <Languages className="h-2.5 w-2.5" />
                {t.total_chapters_done} chapters
              </span>
              <span className="inline-flex items-center gap-1 rounded bg-secondary px-2 py-px text-[10px] text-muted-foreground">
                {t.languages.length} language{t.languages.length !== 1 ? 's' : ''}
              </span>
            </div>
          </div>
        </div>
      ))}

      {hasMore && (
        <div className="border-t p-3 text-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loading}
            className="inline-flex items-center rounded-md border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
          >
            {t('ranking.showMore')}
          </button>
        </div>
      )}
    </div>
  );
}
