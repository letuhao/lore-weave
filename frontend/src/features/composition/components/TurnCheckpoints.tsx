// RAID C6 — the AI-edit checkpoint list (render-only; logic in useTurnCheckpoints).
// Sits above RevisionHistory: each row is a restore point captured just before an
// agent edit, so "undo what the AI just did" is one click instead of scrolling
// the full autosave revision wall.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RotateCcw, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/shared';
import type { TurnCheckpoint } from '../hooks/useTurnCheckpoints';

export function TurnCheckpoints({
  checkpoints,
  onRestore,
}: {
  checkpoints: TurnCheckpoint[];
  onRestore: (cp: TurnCheckpoint) => Promise<void> | void;
}) {
  const { t } = useTranslation('editor');
  const [target, setTarget] = useState<TurnCheckpoint | null>(null);

  if (checkpoints.length === 0) return null;

  const confirmRestore = async () => {
    if (!target) return;
    try {
      await onRestore(target);
      toast.success(t('checkpoint.restored', { defaultValue: 'Restored to before the AI edit' }));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setTarget(null);
    }
  };

  return (
    <div data-testid="turn-checkpoints" className="flex-shrink-0 border-b">
      <div className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-muted-foreground">
        <Sparkles className="h-3 w-3 text-violet-500" />
        <span>{t('checkpoint.header', { defaultValue: 'AI edit checkpoints', count: checkpoints.length })}</span>
      </div>
      <div className="max-h-44 overflow-y-auto">
        {checkpoints.map((cp) => (
          <div key={cp.id} data-testid="turn-checkpoint-row" className="flex items-center gap-2 px-4 py-2 text-xs hover:bg-card">
            <span className="min-w-0 flex-1 truncate text-muted-foreground" title={cp.snippet}>
              {cp.kind === 'polish'
                ? t('checkpoint.polish', { defaultValue: 'Polished' })
                : t('checkpoint.insert', { defaultValue: 'Inserted' })}
              {cp.count > 1 && <span className="ml-1 text-[10px] opacity-70">×{cp.count}</span>}
              {cp.snippet && <span className="ml-1.5 italic opacity-70">“{cp.snippet}”</span>}
            </span>
            <button
              type="button"
              data-testid="turn-checkpoint-restore"
              disabled={!cp.preRevisionId}
              title={cp.preRevisionId ? undefined : t('checkpoint.no_restore', { defaultValue: 'No earlier version to restore to' })}
              onClick={() => setTarget(cp)}
              className="inline-flex items-center gap-1 text-primary hover:underline disabled:opacity-40 disabled:no-underline"
            >
              <RotateCcw className="h-3 w-3" />
              {t('checkpoint.restore', { defaultValue: 'Restore' })}
            </button>
          </div>
        ))}
      </div>

      <ConfirmDialog
        open={!!target}
        onOpenChange={(open) => { if (!open) setTarget(null); }}
        title={t('checkpoint.confirm_title', { defaultValue: 'Restore to before this AI edit?' })}
        description={t('checkpoint.confirm_desc', { defaultValue: 'The current draft is snapshotted first, so this is reversible from the revision history.' })}
        confirmLabel={t('checkpoint.restore', { defaultValue: 'Restore' })}
        variant="destructive"
        onConfirm={() => void confirmRestore()}
      />
    </div>
  );
}
