import { useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { DockviewReadyEvent, DockviewApi } from 'dockview-react';

/** Per-book dockview layout (api.toJSON()). Per-device UI state → localStorage. */
const layoutKey = (bookId: string) => `lw_studio_layout_${bookId}`;

/**
 * Owns the dockview lifecycle for the studio: restore/seed the layout and persist every
 * change. Kept as a hook so the page stays a thin composition and future "add panel"
 * actions have a single home (via the returned api ref).
 */
export function useStudioLayout(bookId: string) {
  const { t } = useTranslation('studio');
  const apiRef = useRef<DockviewApi | null>(null);

  const onReady = useCallback((event: DockviewReadyEvent) => {
    const api = event.api;
    apiRef.current = api;

    // Persist on every layout change (add/move/split/resize/close). Registered BEFORE the
    // initial restore/seed so even the default layout is captured on first load.
    const disposable = api.onDidLayoutChange(() => {
      try { localStorage.setItem(layoutKey(bookId), JSON.stringify(api.toJSON())); } catch { /* quota */ }
    });

    // Restore the saved layout; fall back to a single Welcome panel. A saved layout that
    // references a panel no longer in the registry throws on fromJSON — guarded so a stale
    // layout degrades to the blank default instead of a crash.
    let restored = false;
    try {
      const saved = localStorage.getItem(layoutKey(bookId));
      if (saved) { api.fromJSON(JSON.parse(saved)); restored = true; }
    } catch { restored = false; }

    if (!restored) {
      api.addPanel({ id: 'welcome', component: 'welcome', title: t('welcome.tab', { defaultValue: 'Welcome' }) });
    }

    return () => disposable.dispose();
  }, [bookId, t]);

  return { onReady, apiRef };
}
