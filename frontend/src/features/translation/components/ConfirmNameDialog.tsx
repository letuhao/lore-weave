import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { BookCheck, X } from 'lucide-react';
import { useConfirmName } from '../hooks/useConfirmName';

interface ConfirmNameDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookId: string;
  targetLang: string;
}

/**
 * M6a — capture a name correction and confirm it into the glossary (confidence
 * 'verified'). On success the glossary change flows through the M5c staleness
 * loop so the user can re-translate the affected chapters.
 */
export function ConfirmNameDialog({ open, onOpenChange, bookId, targetLang }: ConfirmNameDialogProps) {
  const { t } = useTranslation('translation');
  const { confirm, submitting } = useConfirmName(bookId, targetLang);
  const [sourceName, setSourceName] = useState('');
  const [correctedTarget, setCorrectedTarget] = useState('');

  async function handleSubmit() {
    const result = await confirm(sourceName, correctedTarget);
    if (result === 'confirmed') {
      toast.success(t('confirm_name.confirmed', { name: correctedTarget.trim() }));
      setSourceName('');
      setCorrectedTarget('');
      onOpenChange(false);
    } else {
      toast.error(t(`confirm_name.${result}`));
    }
  }

  const canSubmit = sourceName.trim() !== '' && correctedTarget.trim() !== '' && !submitting;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-background shadow-2xl">
          <Dialog.Close
            disabled={submitting}
            className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground/50 transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-30"
          >
            <X className="h-4 w-4" />
          </Dialog.Close>

          <div className="flex items-start gap-4 px-6 pt-6 pb-4">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-[#3da692]/10">
              <BookCheck className="h-5 w-5 text-[#3da692]" />
            </div>
            <div>
              <Dialog.Title className="text-base font-semibold leading-tight pr-6">
                {t('confirm_name.title')}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                {t('confirm_name.description', { lang: targetLang })}
              </Dialog.Description>
            </div>
          </div>

          <div className="space-y-3 px-6 pb-2">
            <label className="block text-xs font-medium text-muted-foreground">
              {t('confirm_name.source_label')}
              <input
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
                className="mt-1 w-full rounded-lg border bg-input px-3 py-2 text-sm text-foreground focus:border-ring focus:outline-none"
                placeholder={t('confirm_name.source_placeholder')}
              />
            </label>
            <label className="block text-xs font-medium text-muted-foreground">
              {t('confirm_name.target_label')}
              <input
                value={correctedTarget}
                onChange={(e) => setCorrectedTarget(e.target.value)}
                className="mt-1 w-full rounded-lg border bg-input px-3 py-2 text-sm text-foreground focus:border-ring focus:outline-none"
                placeholder={t('confirm_name.target_placeholder')}
              />
            </label>
          </div>

          <div className="flex justify-end gap-2 border-t px-6 py-4 mt-2">
            <Dialog.Close asChild>
              <button
                disabled={submitting}
                className="inline-flex items-center justify-center rounded-lg border px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
              >
                {t('confirm_name.cancel')}
              </button>
            </Dialog.Close>
            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {submitting ? t('confirm_name.submitting') : t('confirm_name.submit')}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
