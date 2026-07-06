// #16 Phase 1, task 1.2 — Checkpoints section, ported from the legacy
// `features/composition/components/TurnCheckpoints.tsx` (render-only; logic lives in
// `useManuscriptCheckpoints`). Mounts inside `EditorPanel` as a collapsible section (matching
// legacy's placement above Revision History), not a separate dock panel — DOCK-2 (no fork of the
// panel-registration mechanism for a section that isn't a panel) / DOCK-10 (all state comes from
// the Tier-4 hoist via the parent-owned hook, this component owns no state of its own besides the
// transient "which row is pending confirmation" UI state).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RotateCcw, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/shared';
import type { CheckpointRestoreResult, ManuscriptCheckpoint } from './useManuscriptCheckpoints';

export function ManuscriptCheckpoints({
  checkpoints,
  /** True when the active chapter's hoist is dirty (`unit.isDirty`) — every visible checkpoint
   * belongs to the currently-open chapter (the caller passes `visibleCheckpoints`), so a single
   * flag covers the whole section instead of a per-row `isChapterDirty` re-check (G7). */
  isDirty,
  onRestore,
}: {
  checkpoints: ManuscriptCheckpoint[];
  isDirty: boolean;
  onRestore: (checkpointId: string) => Promise<CheckpointRestoreResult>;
}) {
  const { t } = useTranslation('studio');
  const [target, setTarget] = useState<ManuscriptCheckpoint | null>(null);

  if (checkpoints.length === 0) return null;

  const confirmRestore = async () => {
    if (!target) return;
    const result = await onRestore(target.id);
    if (result.ok) {
      toast.success(t('checkpoints.restored', { defaultValue: 'Restored to before the AI edit' }));
    } else {
      toast.error(result.message ?? t('checkpoints.restore_failed', { defaultValue: 'Could not restore this checkpoint.' }));
    }
    setTarget(null);
  };

  return (
    <div data-testid="studio-manuscript-checkpoints" className="flex-shrink-0 border-b">
      <div className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold text-muted-foreground">
        <Sparkles className="h-3 w-3 text-violet-500" />
        <span>{t('checkpoints.header', { defaultValue: 'AI edit checkpoints', count: checkpoints.length })}</span>
      </div>
      {isDirty && (
        <div data-testid="studio-manuscript-checkpoints-dirty-warning" className="px-3 pb-1.5 text-[10px] text-warning">
          {t('checkpoints.dirty_warning', {
            defaultValue: 'Save your current edits before restoring a checkpoint.',
          })}
        </div>
      )}
      <div className="max-h-40 overflow-y-auto">
        {checkpoints.map((cp) => {
          const disabled = !cp.preRevisionId || isDirty;
          const title = !cp.preRevisionId
            ? t('checkpoints.no_restore', { defaultValue: 'No earlier version to restore to' })
            : isDirty
              ? t('checkpoints.blocked_dirty', { defaultValue: 'Save your edits first — restoring would overwrite them' })
              : undefined;
          return (
            <div key={cp.id} data-testid="studio-manuscript-checkpoint-row" className="flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-card">
              <span className="min-w-0 flex-1 truncate text-muted-foreground" title={cp.snippet}>
                {cp.kind === 'replace'
                  ? t('checkpoints.replace', { defaultValue: 'Rewrote' })
                  : t('checkpoints.insert', { defaultValue: 'Inserted' })}
                {cp.count > 1 && <span className="ml-1 text-[10px] opacity-70">×{cp.count}</span>}
                {cp.snippet && <span className="ml-1.5 italic opacity-70">“{cp.snippet}”</span>}
              </span>
              <button
                type="button"
                data-testid="studio-manuscript-checkpoint-restore"
                disabled={disabled}
                title={title}
                onClick={() => setTarget(cp)}
                className="inline-flex items-center gap-1 text-primary hover:underline disabled:opacity-40 disabled:no-underline"
              >
                <RotateCcw className="h-3 w-3" />
                {t('checkpoints.restore', { defaultValue: 'Restore' })}
              </button>
            </div>
          );
        })}
      </div>

      <ConfirmDialog
        open={!!target}
        onOpenChange={(open) => { if (!open) setTarget(null); }}
        title={t('checkpoints.confirm_title', { defaultValue: 'Restore to before this AI edit?' })}
        description={t('checkpoints.confirm_desc', {
          defaultValue: 'The current draft is snapshotted first, so this is reversible from the revision history.',
        })}
        confirmLabel={t('checkpoints.restore', { defaultValue: 'Restore' })}
        variant="destructive"
        onConfirm={() => void confirmRestore()}
      />
    </div>
  );
}
