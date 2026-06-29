// LOOM Composition (M5a / D-T5.5-MOBILE-SWITCHER) — the mobile Studio panel picker.
//
// On a ≤767px viewport the studio shows ONE panel at a time (no dock rail / float /
// popout). This replaces the rail with a single trigger (the active panel's name) that
// opens a bottom Sheet listing the available panels; selecting one drives the existing
// `selectTab` → `set-active`. Generic over string ids (decoupled from SubTab); the
// caller passes the visible-ids list (the `threads` gate already applied) + a labeller.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, X } from 'lucide-react';

export function MobilePanelSwitcher({ ids, active, onSelect, label }: {
  ids: string[];
  active: string;
  onSelect: (id: string) => void;
  label: (id: string) => string;
}) {
  const { t } = useTranslation('composition');
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const pick = (id: string) => { onSelect(id); setOpen(false); };

  return (
    <div className="border-b border-neutral-200 dark:border-neutral-700">
      <button
        type="button"
        data-testid="mobile-panel-switcher"
        aria-haspopup="dialog"
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-sm font-medium"
        onClick={() => setOpen(true)}
      >
        <span className="truncate">{label(active)}</span>
        <span className="flex shrink-0 items-center gap-1 text-xs text-neutral-500">
          {t('mobile.switchPanel', { defaultValue: 'Switch panel' })}
          <ChevronDown className="h-4 w-4" />
        </span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40 bg-black/50" onClick={() => setOpen(false)} />
          <div
            role="dialog"
            aria-label={t('mobile.panels', { defaultValue: 'Panels' })}
            data-testid="mobile-panel-sheet"
            className="fixed inset-x-0 bottom-0 z-50 max-h-[70vh] overflow-y-auto rounded-t-2xl border-t bg-background shadow-2xl"
          >
            <div className="sticky top-0 flex items-center justify-between border-b bg-card px-4 py-3">
              <h2 className="text-sm font-semibold">{t('mobile.panels', { defaultValue: 'Panels' })}</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={t('mobile.close', { defaultValue: 'Close' })}
                className="rounded p-1 hover:bg-secondary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <ul className="grid grid-cols-2 gap-1 p-3">
              {ids.map((id) => (
                <li key={id}>
                  <button
                    type="button"
                    data-testid={`mobile-panel-${id}`}
                    aria-current={id === active}
                    onClick={() => pick(id)}
                    className={`w-full rounded-md px-3 py-2.5 text-left text-sm ${
                      id === active ? 'bg-primary/15 font-medium text-primary' : 'hover:bg-secondary'
                    }`}
                  >
                    {label(id)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
