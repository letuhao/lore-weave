import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ConfirmDialogAction {
  label: string;
  onClick: () => void | Promise<void>;
  loading?: boolean;
}

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  /** Shown above the confirm button. When provided, buttons stack vertically. */
  extraAction?: ConfirmDialogAction;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  variant?: 'destructive' | 'default';
  loading?: boolean;
  /** Custom icon node. Pass false to suppress the default destructive icon. */
  icon?: React.ReactNode | false;
  /**
   * AWS-style typed confirmation: when set, the user must TYPE this exact phrase
   * (paste is blocked) before the confirm button enables. Use for irreversible
   * destructive ops (e.g. a KG rebuild that deletes thousands of entities).
   */
  confirmationPhrase?: string;
  /** Label above the typed-confirmation input. */
  confirmationLabel?: string;
}

export function ConfirmDialog({
  open, onOpenChange, title, description,
  extraAction,
  confirmLabel = 'Confirm', cancelLabel = 'Cancel',
  onConfirm, variant = 'default', loading,
  icon,
  confirmationPhrase,
  confirmationLabel,
}: ConfirmDialogProps) {
  const stacked = !!extraAction;
  const [typed, setTyped] = useState('');
  // Clear the typed value whenever the dialog opens/closes so a prior match
  // can't carry over to the next destructive action.
  useEffect(() => { setTyped(''); }, [open]);
  const phraseOk = !confirmationPhrase || typed.trim() === confirmationPhrase;

  const defaultIcon = variant === 'destructive'
    ? <AlertTriangle className="h-5 w-5 text-destructive" />
    : null;

  const resolvedIcon = icon === false ? null : (icon ?? defaultIcon);
  const iconBg = variant === 'destructive' ? 'bg-destructive/10' : 'bg-amber-500/10';
  const iconColor = variant === 'destructive' ? 'text-destructive' : 'text-amber-500';

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-background shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">

          {/* Close button — disabled while an async confirm is in flight
              (K19a.6 F4) so users can't dismiss the dialog and leave the
              parent holding a phantom submitting state. */}
          <Dialog.Close
            disabled={loading}
            className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground/50 transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30"
          >
            <X className="h-4 w-4" />
          </Dialog.Close>

          {/* Header */}
          <div className="flex items-start gap-4 px-6 pt-6 pb-4">
            {resolvedIcon && (
              <div className={cn('flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full', iconBg)}>
                <span className={iconColor}>{resolvedIcon}</span>
              </div>
            )}
            <div>
              <Dialog.Title className="text-base font-semibold leading-tight pr-6">{title}</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                {description}
              </Dialog.Description>
            </div>
          </div>

          {/* AWS-style typed confirmation (paste blocked) */}
          {confirmationPhrase && (
            <div className="px-6 pb-2">
              <label className="mb-1 block text-xs text-muted-foreground">
                {confirmationLabel ?? `Type ${confirmationPhrase} to confirm`}
              </label>
              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                onPaste={(e) => e.preventDefault()}
                disabled={loading}
                autoComplete="off"
                spellCheck={false}
                data-testid="confirm-phrase-input"
                aria-label={confirmationLabel ?? `Type ${confirmationPhrase} to confirm`}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>
          )}

          {/* Actions */}
          <div className={cn('border-t px-6 py-4', stacked ? 'flex flex-col gap-2' : 'flex justify-end gap-2')}>
            {extraAction && (
              <button
                onClick={() => void extraAction.onClick()}
                disabled={extraAction.loading}
                className="inline-flex w-full items-center justify-center rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {extraAction.loading ? 'Saving…' : extraAction.label}
              </button>
            )}

            <button
              onClick={onConfirm}
              disabled={loading || !phraseOk}
              className={cn(
                'inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-50',
                stacked ? 'w-full border border-destructive/30 text-destructive hover:bg-destructive/10' :
                  variant === 'destructive'
                    ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                    : 'bg-primary text-primary-foreground hover:bg-primary/90',
              )}
            >
              {confirmLabel}
            </button>

            {/* K19a.6 review-impl F4 — Cancel is disabled (and hidden
                from the pointer) while the confirm action is in flight.
                Without this the button stays clickable but the parent's
                open-change guard silently blocks it, confusing the user. */}
            <Dialog.Close asChild>
              <button
                disabled={loading}
                className={cn(
                  'inline-flex items-center justify-center rounded-lg border px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50',
                  stacked ? 'w-full' : '',
                )}
              >
                {cancelLabel}
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
