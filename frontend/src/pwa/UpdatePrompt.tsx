// M4 — the "new version" prompt (MB5). Shows only when a new SW is installed-and-waiting; the app
// is never hot-swapped silently. Accepting posts SKIP_WAITING (via applyUpdate) → controllerchange
// reloads into the new version.
import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { onUpdateReady, applyUpdate } from './registerSW';

export function UpdatePrompt() {
  const [ready, setReady] = useState(false);

  useEffect(() => onUpdateReady(() => setReady(true)), []);

  if (!ready) return null;

  return (
    <div
      role="status"
      data-testid="pwa-update-prompt"
      className="fixed inset-x-3 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-[60] mx-auto flex max-w-md items-center gap-3 rounded-xl border border-border bg-card p-3 shadow-lg"
    >
      <RefreshCw className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
      <span className="flex-1 text-sm">A new version of LoreWeave is ready.</span>
      <button
        type="button"
        onClick={applyUpdate}
        className="min-h-[40px] rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground"
      >
        Refresh
      </button>
    </div>
  );
}
