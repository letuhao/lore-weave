import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';

type Props = {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
};

export function TagEditor({ tags, onChange, placeholder }: Props) {
  const { t } = useTranslation('settings');
  const [input, setInput] = useState('');

  function handleAdd() {
    const t = input.trim();
    if (t && !tags.includes(t)) {
      onChange([...tags, t]);
      setInput('');
    }
  }

  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium">{t('tags.label')}</label>
      {tags.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span key={tag} className="flex items-center gap-1 rounded border bg-secondary px-2 py-0.5 text-[11px] font-medium">
              {tag}
              <button
                onClick={() => onChange(tags.filter((x) => x !== tag))}
                aria-label={t('tags.remove_aria', { tag })}
                className="rounded-full p-0.5 hover:bg-destructive/20 hover:text-destructive"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-1.5">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAdd(); } }}
          placeholder={placeholder ?? t('tags.placeholder')}
          className="h-8 flex-1 rounded-md border bg-background px-2.5 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
        />
        <button
          onClick={handleAdd}
          disabled={!input.trim()}
          className="rounded-md border px-2.5 py-1 text-[11px] font-medium hover:bg-secondary disabled:opacity-50"
        >
          {t('tags.add')}
        </button>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {t('tags.hint')}
      </p>
    </div>
  );
}
