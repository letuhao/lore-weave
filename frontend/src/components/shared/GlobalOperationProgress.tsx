import { useSyncExternalStore } from 'react';
import { useIsFetching, useIsMutating } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import {
  getOperationSnapshot,
  subscribeToOperations,
} from '@/lib/operationTracker';

/**
 * App-wide feedback for network work. Feature screens still keep their local
 * skeletons/spinners, while this shell-level indicator covers requests that
 * start from a dialog, toolbar, upload, or direct apiJson call and would
 * otherwise leave the user wondering whether anything happened.
 */
export function GlobalOperationProgress() {
  const fetching = useIsFetching();
  const mutating = useIsMutating();
  const direct = useSyncExternalStore(
    subscribeToOperations,
    getOperationSnapshot,
    getOperationSnapshot,
  );
  const active = fetching > 0 || mutating > 0 || direct.active > 0;
  if (!active) return null;

  const writing = mutating > 0 || direct.writes > 0;
  const label = writing ? 'Сохраняем изменения…' : 'Загружаем…';

  return (
    <div
      className="pointer-events-none fixed inset-x-0 top-0 z-[100]"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={label}
      data-testid="global-operation-progress"
    >
      <div className="h-1 overflow-hidden bg-primary/20">
        <div className="h-full w-1/3 bg-primary motion-safe:animate-[global-operation-progress_1.1s_ease-in-out_infinite]" />
      </div>
      <div className="fixed right-4 top-4 inline-flex items-center gap-2 rounded-full border bg-background/95 px-3 py-1.5 text-xs font-medium text-foreground shadow-lg backdrop-blur">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" aria-hidden="true" />
        <span>{label}</span>
      </div>
    </div>
  );
}
