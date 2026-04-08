import { Star, Languages } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { LeaderboardAuthor, LeaderboardTranslator } from './api';
import { RankMedal } from './RankMedal';

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] ?? '')
    .join('')
    .toUpperCase() || '?';
}

function formatCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export function QuickStatsCards({
  authors,
  translators,
  onViewAuthors,
  onViewTranslators,
}: {
  authors: LeaderboardAuthor[];
  translators: LeaderboardTranslator[];
  onViewAuthors: () => void;
  onViewTranslators: () => void;
}) {
  const { t } = useTranslation('leaderboard');
  const top3Authors = authors.slice(0, 3);
  const top3Translators = translators.slice(0, 3);

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {/* Top Authors */}
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <span className="text-[13px] font-semibold">{t('quickStats.topAuthors')}</span>
          <button onClick={onViewAuthors} className="text-[10px] text-muted-foreground hover:text-foreground">
            {t('quickStats.viewAll')} &rarr;
          </button>
        </div>
        {top3Authors.map((a) => (
          <div key={a.user_id} className="flex items-center gap-3 border-b px-4 py-2.5 last:border-b-0">
            <RankMedal rank={a.rank} size="sm" />
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
              {initials(a.display_name || 'U')}
            </div>
            <div className="flex-1">
              <span className="text-[13px] font-medium">{a.display_name || 'Unknown'}</span>
              <div className="mt-0.5 flex gap-1.5">
                <span className="rounded bg-secondary px-2 py-px text-[10px] text-muted-foreground">
                  {a.total_books} book{a.total_books !== 1 ? 's' : ''}
                </span>
                <span className="rounded bg-secondary px-2 py-px text-[10px] text-muted-foreground">
                  {formatCount(a.readers)} readers
                </span>
                {a.avg_rating > 0 && (
                  <span className="inline-flex items-center gap-0.5 rounded bg-secondary px-2 py-px text-[10px] text-muted-foreground">
                    <Star className="h-2.5 w-2.5 fill-primary text-primary" />
                    {a.avg_rating.toFixed(1)} avg
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Top Translators */}
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <span className="text-[13px] font-semibold">{t('quickStats.topTranslators')}</span>
          <button onClick={onViewTranslators} className="text-[10px] text-muted-foreground hover:text-foreground">
            {t('quickStats.viewAll')} &rarr;
          </button>
        </div>
        {top3Translators.map((tr) => (
          <div key={tr.user_id} className="flex items-center gap-3 border-b px-4 py-2.5 last:border-b-0">
            <RankMedal rank={tr.rank} size="sm" />
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
              {initials(tr.display_name || 'U')}
            </div>
            <div className="flex-1">
              <span className="text-[13px] font-medium">{tr.display_name || 'Unknown'}</span>
              <div className="mt-0.5 flex gap-1.5">
                <span className="inline-flex items-center gap-0.5 rounded bg-secondary px-2 py-px text-[10px] text-muted-foreground">
                  <Languages className="h-2.5 w-2.5" />
                  {tr.total_chapters_done} chapters
                </span>
                <span className="rounded bg-secondary px-2 py-px text-[10px] text-muted-foreground">
                  {tr.languages.length} language{tr.languages.length !== 1 ? 's' : ''}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
