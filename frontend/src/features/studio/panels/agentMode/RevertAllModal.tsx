// #20_agent_mode.md §7 (Revert-all) / D9. Direct Radix Dialog (not the shared
// ConfirmDialog wrapper — DOCK-9-compliant either way per the hygiene test,
// but this modal needs a scrollable affected-unit list AND a post-confirm
// PARTIAL-FAILURE result view that ConfirmDialog's fixed title/description
// shape can't render).
import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { RevertAllResult } from '@/features/composition/authoringRuns/types';

export interface AffectedUnit {
  unitIndex: number;
  chapterLabel: string;
  fromStatus: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  affected: AffectedUnit[];
  onConfirm: () => void;
  busy: boolean;
  result: RevertAllResult | null;
}

export function RevertAllModal({ open, onOpenChange, affected, onConfirm, busy, result }: Props) {
  const { t } = useTranslation('composition');

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          data-testid="agent-mode-revert-modal"
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-background p-5 shadow-2xl"
        >
          <Dialog.Close disabled={busy} className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30">
            <X className="h-4 w-4" />
          </Dialog.Close>
          <div className="mb-3 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 shrink-0 text-destructive" />
            <div>
              <Dialog.Title className="text-sm font-semibold">
                {t('authoringRun.revert.title', { defaultValue: 'Revert all drafted/accepted units?' })}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-muted-foreground">
                {t('authoringRun.revert.body', {
                  defaultValue:
                    'This rejects every drafted/accepted unit in reverse order and restores each chapter to its pre-run revision. This cannot be undone from this UI. Affected:',
                })}
              </Dialog.Description>
            </div>
          </div>

          {!result && (
            <ul data-testid="agent-mode-revert-list" className="mb-3 max-h-40 space-y-1 overflow-y-auto rounded-md border p-2 text-xs">
              {affected.length === 0 ? (
                <li className="text-muted-foreground">
                  {t('authoringRun.revert.none', { defaultValue: 'No drafted/accepted units to revert.' })}
                </li>
              ) : (
                affected.map((u) => (
                  <li key={u.unitIndex} data-testid="agent-mode-revert-list-item">
                    {t('authoringRun.queue.unitLabel', { index: u.unitIndex + 1, defaultValue: 'Unit {{index}}' })} · {u.chapterLabel} — {u.fromStatus} → rejected
                  </li>
                ))
              )}
            </ul>
          )}

          {result && (
            <div data-testid="agent-mode-revert-result" className="mb-3 rounded-md border p-2 text-xs">
              {result.failed_unit_index !== null ? (
                <>
                  <p className="font-semibold text-destructive">
                    {t('authoringRun.revert.partialTitle', { defaultValue: 'Revert stopped partway' })}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    {t('authoringRun.revert.partialBody', {
                      index: result.failed_unit_index + 1,
                      error: result.error,
                      count: result.reverted_unit_indexes.length,
                      defaultValue:
                        'Unit {{index}} failed to restore ({{error}}). {{count}} unit(s) reverted successfully before the stop; the run is left open (same state as before) so you can retry.',
                    })}
                  </p>
                </>
              ) : (
                <p className="font-semibold text-success">
                  {t('authoringRun.revert.successBody', {
                    count: result.reverted_unit_indexes.length,
                    defaultValue: 'All {{count}} unit(s) reverted; the run is now closed.',
                  })}
                </p>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2">
            {!result && (
              <>
                <Dialog.Close asChild>
                  <button disabled={busy} className="rounded-lg border px-3 py-1.5 text-xs disabled:opacity-40">
                    {t('authoringRun.revert.cancel', { defaultValue: 'Cancel' })}
                  </button>
                </Dialog.Close>
                <button
                  type="button"
                  data-testid="agent-mode-revert-confirm"
                  disabled={busy || affected.length === 0}
                  onClick={onConfirm}
                  className="rounded-lg bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground disabled:opacity-40"
                >
                  {busy
                    ? t('authoringRun.revert.reverting', { defaultValue: 'Reverting…' })
                    : t('authoringRun.revert.confirm', { defaultValue: 'Revert all' })}
                </button>
              </>
            )}
            {result && (
              <Dialog.Close asChild>
                <button data-testid="agent-mode-revert-close" className="rounded-lg border px-3 py-1.5 text-xs">
                  {t('authoringRun.revert.cancel', { defaultValue: 'Close' })}
                </button>
              </Dialog.Close>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
