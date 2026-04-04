import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const GUI_LANGUAGES = [
  { code: 'en', label: 'English', native: 'English' },
  { code: 'vi', label: 'Vietnamese', native: 'Tiếng Việt' },
  { code: 'ja', label: 'Japanese', native: '日本語' },
  { code: 'zh-TW', label: 'Traditional Chinese', native: '繁體中文' },
];

export function LanguageTab() {
  const { i18n } = useTranslation();
  const current = i18n.language;

  function handleChange(code: string) {
    i18n.changeLanguage(code);
    localStorage.setItem('lw_language', code);
    toast.success(`Language changed to ${GUI_LANGUAGES.find((l) => l.code === code)?.native ?? code}`);
  }

  return (
    <div>
      <div className="py-5">
        <h2 className="text-sm font-semibold">GUI Language</h2>
        <p className="mb-4 text-xs text-muted-foreground">
          Change the interface language. Content (books, chapters) is not affected.
        </p>
        <div className="flex flex-wrap gap-2">
          {GUI_LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => handleChange(lang.code)}
              className={cn(
                'rounded-md border px-4 py-2 text-[13px] font-medium transition-colors',
                current === lang.code || current.startsWith(lang.code + '-')
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'hover:bg-secondary',
              )}
            >
              {lang.native}
            </button>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">
          Currently: <strong>{GUI_LANGUAGES.find((l) => l.code === current || current.startsWith(l.code + '-'))?.native ?? current}</strong>
        </p>
      </div>
    </div>
  );
}
