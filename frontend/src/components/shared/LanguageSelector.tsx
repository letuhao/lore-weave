import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

const LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'vi', name: 'Tiếng Việt' },
  { code: 'ja', name: '日本語' },
  { code: 'zh-TW', name: '繁體中文' },
];

export function LanguageSelector({ className }: { className?: string }) {
  const { i18n } = useTranslation();
  const current = i18n.language;

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          onClick={() => void i18n.changeLanguage(lang.code)}
          className={cn(
            'rounded-md border px-4 py-2 text-sm font-medium transition-colors',
            current === lang.code || current.startsWith(lang.code)
              ? 'border-primary bg-primary/15 text-primary'
              : 'border-border text-foreground hover:bg-secondary',
          )}
        >
          {lang.name}
        </button>
      ))}
    </div>
  );
}
