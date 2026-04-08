import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { AuthorStats, TranslatorStats } from './api';

type Achievement = { icon: string; label: string; highlight?: boolean };

function computeAchievements(
  t: TFunction,
  author: AuthorStats,
  translator: TranslatorStats | null,
  followerCount: number,
): Achievement[] {
  const list: Achievement[] = [];

  if (author.total_books >= 1) {
    list.push({ icon: '\u{1F4DA}', label: t('achievement.booksPublished', { count: author.total_books }) });
  }
  if (author.total_readers >= 1000) {
    list.push({ icon: '\u{1F4D6}', label: t('achievement.kReaders', { count: Math.floor(author.total_readers / 1000) }) });
  } else if (author.total_readers >= 100) {
    list.push({ icon: '\u{1F31F}', label: t('achievement.hundredReaders') });
  }
  if (followerCount >= 10) {
    list.push({ icon: '\u{1F465}', label: t('achievement.followers', { count: followerCount }), highlight: true });
  }
  if (translator && translator.languages.length >= 3) {
    list.push({ icon: '\u{1F310}', label: t('achievement.multiLangTranslator', { count: translator.languages.length }) });
  }
  if (translator && translator.total_chapters_done >= 50) {
    list.push({ icon: '\u{1F3C6}', label: t('achievement.fiftyChapters'), highlight: true });
  }

  return list;
}

type Props = {
  author: AuthorStats;
  translator: TranslatorStats | null;
  followerCount: number;
};

export function AchievementBar({ author, translator, followerCount }: Props) {
  const { t } = useTranslation('profile');
  const achievements = computeAchievements(t, author, translator, followerCount);

  if (achievements.length === 0) return null;

  return (
    <div className="mb-6">
      <h3 className="text-[13px] font-semibold mb-2.5">{t('achievements')}</h3>
      <div className="flex flex-wrap gap-1.5">
        {achievements.map((a, i) => (
          <div
            key={i}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border text-[11px] transition-colors ${
              a.highlight
                ? 'border-[rgba(232,168,50,0.3)] bg-[var(--primary-muted)]'
                : 'border-[var(--border)] hover:border-[var(--border-hover)] hover:bg-[var(--card-hover)]'
            }`}
          >
            <span className="text-sm">{a.icon}</span>
            <span className={`font-medium ${a.highlight ? 'text-[var(--primary)]' : ''}`}>
              {a.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
