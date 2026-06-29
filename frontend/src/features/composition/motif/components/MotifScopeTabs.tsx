// W6 §3.4 — My library | Public catalog scope tabs. role=tablist + arrow-key nav
// (§5.1). Render-only.
import { useTranslation } from 'react-i18next';
import type { LibraryScope } from '../hooks/useMotifLibrary';

const TABS: LibraryScope[] = ['my', 'catalog', 'drafts'];
const TAB_DEFAULT: Record<LibraryScope, string> = {
  my: 'My library', catalog: 'Public catalog', drafts: 'Drafts',
};

export function MotifScopeTabs({ scope, onScope }: { scope: LibraryScope; onScope: (s: LibraryScope) => void }) {
  const { t } = useTranslation('composition');

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const i = TABS.indexOf(scope);
    const next = e.key === 'ArrowRight' ? (i + 1) % TABS.length : (i - 1 + TABS.length) % TABS.length;
    onScope(TABS[next]);
  };

  return (
    <div role="tablist" aria-label={t('motif.scope.label', { defaultValue: 'Motif scope' })} className="flex gap-1 border-b border-neutral-200 px-1 dark:border-neutral-700" onKeyDown={onKeyDown}>
      {TABS.map((s) => (
        <button
          key={s}
          role="tab"
          aria-selected={scope === s}
          tabIndex={scope === s ? 0 : -1}
          data-testid={`motif-scope-${s}`}
          className={`rounded-t px-3 py-1 text-xs ${scope === s ? 'bg-neutral-100 font-medium text-neutral-800 dark:bg-neutral-800 dark:text-neutral-100' : 'text-neutral-500'}`}
          onClick={() => onScope(s)}
        >
          {t(`motif.scope.${s}`, { defaultValue: TAB_DEFAULT[s] })}
        </button>
      ))}
    </div>
  );
}
