// W6 §3.4 — My library | Public catalog scope tabs. role=tablist + arrow-key nav
// (§5.1). Render-only.
import { useTranslation } from 'react-i18next';
import type { LibraryScope } from '../hooks/useMotifLibrary';

const TABS: LibraryScope[] = ['my', 'book', 'shared', 'system', 'catalog', 'drafts', 'archived'];
const TAB_DEFAULT: Record<LibraryScope, string> = {
  my: 'Mine', book: 'Book', shared: 'Shared', system: 'System',
  catalog: 'Public catalog', drafts: 'Drafts', archived: 'Archived',
};
// Book + Shared are per-book tiers — disabled (and skipped by arrow-nav) without a book.
const BOOK_TABS = new Set<LibraryScope>(['book', 'shared']);

export function MotifScopeTabs(
  { scope, onScope, hasBook = false }:
  { scope: LibraryScope; onScope: (s: LibraryScope) => void; hasBook?: boolean },
) {
  const { t } = useTranslation('composition');
  const enabledTabs = TABS.filter((s) => hasBook || !BOOK_TABS.has(s));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const i = enabledTabs.indexOf(scope);
    const from = i < 0 ? 0 : i;
    const next = e.key === 'ArrowRight' ? (from + 1) % enabledTabs.length : (from - 1 + enabledTabs.length) % enabledTabs.length;
    onScope(enabledTabs[next]);
  };

  return (
    <div role="tablist" aria-label={t('motif.scope.label', { defaultValue: 'Motif scope' })} className="flex gap-1 border-b border-neutral-200 px-1 dark:border-neutral-700" onKeyDown={onKeyDown}>
      {TABS.map((s) => {
        const disabled = BOOK_TABS.has(s) && !hasBook;
        return (
          <button
            key={s}
            type="button"
            role="tab"
            aria-selected={scope === s}
            disabled={disabled}
            title={disabled ? t('motif.scope.needsBook', { defaultValue: 'Open a book to see its motifs' }) : undefined}
            tabIndex={scope === s ? 0 : -1}
            data-testid={`motif-scope-${s}`}
            className={`rounded-t px-3 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-40 ${scope === s ? 'bg-neutral-100 font-medium text-neutral-800 dark:bg-neutral-800 dark:text-neutral-100' : 'text-neutral-500'}`}
            onClick={() => !disabled && onScope(s)}
          >
            {t(`motif.scope.${s}`, { defaultValue: TAB_DEFAULT[s] })}
          </button>
        );
      })}
    </div>
  );
}
