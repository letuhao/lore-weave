import { useTranslation } from 'react-i18next';
import type { AuthorStats, TranslatorStats } from './api';

type Achievement = { icon: string; label: string; highlight?: boolean };

function computeAchievements(
  author: AuthorStats,
  translator: TranslatorStats | null,
  followerCount: number,
): Achievement[] {
  const list: Achievement[] = [];

  if (author.total_books >= 1) {
    list.push({ icon: '\u{1F4DA}', label: `${author.total_books} Book${author.total_books > 1 ? 's' : ''} Published` });
  }
  if (author.total_readers >= 1000) {
    list.push({ icon: '\u{1F4D6}', label: `${Math.floor(author.total_readers / 1000)}K+ Readers` });
  } else if (author.total_readers >= 100) {
    list.push({ icon: '\u{1F31F}', label: '100+ Readers' });
  }
  if (followerCount >= 10) {
    list.push({ icon: '\u{1F465}', label: `${followerCount} Followers`, highlight: true });
  }
  if (translator && translator.languages.length >= 3) {
    list.push({ icon: '\u{1F310}', label: `${translator.languages.length}-Language Translator` });
  }
  if (translator && translator.total_chapters_done >= 50) {
    list.push({ icon: '\u{1F3C6}', label: '50+ Chapters Translated', highlight: true });
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
  const achievements = computeAchievements(author, translator, followerCount);

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
