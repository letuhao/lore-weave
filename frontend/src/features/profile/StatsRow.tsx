import { useTranslation } from 'react-i18next';
import type { AuthorStats, TranslatorStats } from './api';

type Props = {
  author: AuthorStats;
  translator: TranslatorStats | null;
  followerCount: number;
};

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

export function StatsRow({ author, translator, followerCount }: Props) {
  const { t } = useTranslation('profile');

  const stats = [
    { value: author.total_books, label: t('stats.books'), color: 'var(--primary)' },
    {
      value: translator ? translator.total_chapters_done : 0,
      label: t('stats.chaptersTranslated'),
    },
    { value: author.total_readers, label: t('stats.totalReaders') },
    { value: followerCount, label: t('stats.followers') },
  ];

  return (
    <div
      className="grid gap-px border border-[var(--border)] rounded-lg overflow-hidden mb-6"
      style={{ gridTemplateColumns: `repeat(${stats.length}, 1fr)`, background: 'var(--border)' }}
    >
      {stats.map((s, i) => (
        <div key={i} className="text-center py-3 px-2" style={{ background: 'var(--card)' }}>
          <div
            className="text-xl font-bold font-mono"
            style={{ color: s.color }}
          >
            {formatNum(s.value)}
          </div>
          <div className="text-[10px] text-[var(--muted-fg)] mt-0.5">{s.label}</div>
        </div>
      ))}
    </div>
  );
}
