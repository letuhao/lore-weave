import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

const defaultGenres = ['Fantasy', 'Romance', 'Sci-Fi', 'Drama', 'Historical', 'Cultivation'];
const defaultLanguages = [
  { code: 'ja', label: '日本語' },
  { code: 'en', label: 'English' },
  { code: 'vi', label: 'Tiếng Việt' },
];

export function FilterChips({
  genre,
  language,
  onGenreChange,
  onLanguageChange,
}: {
  genre: string;
  language: string;
  onGenreChange: (g: string) => void;
  onLanguageChange: (l: string) => void;
}) {
  const { t } = useTranslation('leaderboard');

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Chip active={genre === ''} onClick={() => onGenreChange('')}>
        {t('filters.allGenres')}
      </Chip>
      {defaultGenres.map((g) => (
        <Chip key={g} active={genre === g} onClick={() => onGenreChange(g)}>
          {g}
        </Chip>
      ))}

      <div className="mx-1 h-5 w-px bg-border" />

      <Chip active={language === ''} onClick={() => onLanguageChange('')}>
        {t('filters.allLanguages')}
      </Chip>
      {defaultLanguages.map((l) => (
        <Chip key={l.code} active={language === l.code} onClick={() => onLanguageChange(l.code)}>
          {l.label}
        </Chip>
      ))}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-full border px-3.5 py-1 text-xs transition-colors',
        active
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-border text-muted-foreground hover:border-border/80 hover:text-foreground',
      )}
    >
      {children}
    </button>
  );
}
