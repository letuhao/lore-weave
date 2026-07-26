// EC-3d — the active-Work preference: which Work (canonical or a dị bản) the user is
// editing for THIS book, on THIS account. A per-user, per-book DURABLE server pref
// (/v1/me/preferences, key `lw_active_work.<bookId>`), NOT the bus alone (a reload
// would drop back to canon), NOT work.settings (that blob is per-book + SHARED — one
// user switching would move every collaborator, the entity_kinds tenancy bug), NOT
// localStorage (CLAUDE.md: UI state that must persist → server).
//
// Implemented with the useTimezone effect pattern (load-from-server on mount), NOT
// react-query — the ~13 Work-resolution sites that consume it include hooks/components
// whose unit tests mock useWorkResolution and render WITHOUT a QueryClientProvider; a
// useQuery here would break every one of them. A module-level listener set lets the
// "Switch to" write fan out to every mounted useActiveWorkId instance (react-query's
// invalidate, done by hand).
import { useCallback, useEffect, useState } from 'react';
import { loadPrefFromServer, savePrefToServer } from '@/lib/syncPrefs';

export function activeWorkPrefKey(bookId: string): string {
  return `lw_active_work.${bookId}`;
}

// Reload fan-out: useSetActiveWork.switchTo() notifies every mounted reader after a
// durable write, so a "Switch to" moves the whole studio without a shared query cache.
// Exported so the Lane-B effect for an AGENT switch (composition_switch_active_work — it wrote the
// pref server-side) can re-trigger the same in-process re-read the human's switch does.
const reloadListeners = new Set<() => void>();
export function notifyActiveWorkChanged(): void {
  reloadListeners.forEach((l) => l());
}

// In-flight dedup: ~13 Work-resolution sites each mount useActiveWorkId, and without
// react-query's cache they would each fire an identical GET /v1/me/preferences on
// studio mount. Coalesce concurrent loads for the same book onto one request (cleared
// on settle, so a later mount / a post-switch reload refetches fresh — no staleness).
const inflightByBook = new Map<string, Promise<string | null>>();
function fetchActiveWorkId(bookId: string, token: string | null): Promise<string | null> {
  const existing = inflightByBook.get(bookId);
  if (existing) return existing;
  const p = loadPrefFromServer<string>(activeWorkPrefKey(bookId), token)
    .then((v) => v ?? null)
    .catch(() => null)
    .finally(() => inflightByBook.delete(bookId));
  inflightByBook.set(bookId, p);
  return p;
}

/** The active-Work project id for this book (undefined while loading, null = unset ⇒ canonical). */
export function useActiveWorkId(bookId: string | undefined, token: string | null) {
  const [data, setData] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    if (!bookId || !token) {
      setData(undefined);
      return;
    }
    let cancelled = false;
    const load = async () => {
      const v = await fetchActiveWorkId(bookId, token);
      if (!cancelled) setData(v);
    };
    void load();
    reloadListeners.add(load);
    return () => {
      cancelled = true;
      reloadListeners.delete(load);
    };
  }, [bookId, token]);

  // Mimic react-query's `{ data }` shape so call sites read `const { data } = ...`.
  return { data };
}

/**
 * "Switch to" — durably set (or clear, with null) the active Work for this book, then
 * fan the change out to every mounted useActiveWorkId so the whole studio re-resolves.
 * Server is SoT: the notify fires only AFTER the write settles.
 */
export function useSetActiveWork(bookId: string | undefined, token: string | null) {
  const [isSwitching, setIsSwitching] = useState(false);
  const switchTo = useCallback(
    async (projectId: string | null): Promise<boolean> => {
      if (!bookId) return false;
      setIsSwitching(true);
      try {
        const ok = await savePrefToServer(activeWorkPrefKey(bookId), projectId, token);
        if (ok) notifyActiveWorkChanged();
        return ok;
      } finally {
        setIsSwitching(false);
      }
    },
    [bookId, token],
  );
  return { switchTo, isSwitching };
}
