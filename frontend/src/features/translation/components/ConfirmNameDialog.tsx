import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FormDialog } from '@/components/shared/FormDialog';
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

  // S9 (DOCK-9): the last hand-rolled `fixed inset-0` overlay in translation is now the shared
  // FormDialog — same chrome/scroll/a11y as every other dialog, and dockablePanelHygiene stays green.
  const footer = (
    <>
      <button
        onClick={() => onOpenChange(false)}
        disabled={submitting}
        className="inline-flex items-center justify-center rounded-lg border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
      >
        {t('confirm_name.cancel')}
      </button>
      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
      >
        {submitting ? t('confirm_name.submitting') : t('confirm_name.submit')}
      </button>
    </>
  );

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('confirm_name.title')}
      description={t('confirm_name.description', { lang: targetLang })}
      size="sm"
      footer={footer}
    >
      <div className="space-y-3">
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
    </FormDialog>
  );
}
