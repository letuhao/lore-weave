import * as Dialog from '@radix-ui/react-dialog';
import { useTranslation } from 'react-i18next';
import { Sparkles, ShieldCheck, X } from 'lucide-react';
import { TechniqueBadge, H0Marker } from './badges';
import type { Proposal } from '../types';

/** The ④ copyright-safety gate — the explicit, author-only act that turns an
 *  enriched variant into canon. The copy spells out H0 (this becomes canon) and the
 *  author's responsibility for source licensing (the volitional-actor liability
 *  shift). This is the e2e's promote target. */
export function PromoteDialog({
  proposal,
  open,
  onOpenChange,
  onConfirm,
  busy,
}: {
  proposal: Proposal | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onConfirm: () => void;
  busy?: boolean;
}) {
  const { t } = useTranslation('enrichment');
  const name = proposal?.canonical_name || proposal?.target_ref || '';

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px]" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-background shadow-2xl"
          data-testid="enrichment-promote-dialog"
        >
          <Dialog.Close
            disabled={busy}
            className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground/50 transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-30"
          >
            <X className="h-4 w-4" />
          </Dialog.Close>

          <div className="px-6 pb-4 pt-6">
            <div className="mb-3 flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
              <Dialog.Title className="text-base font-semibold">{t('promote.title')}</Dialog.Title>
            </div>

            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="font-serif text-lg font-semibold">{name}</span>
              {proposal && <TechniqueBadge technique={proposal.technique} />}
              <H0Marker />
            </div>

            <Dialog.Description className="text-sm text-muted-foreground">
              {t('promote.h0')}
            </Dialog.Description>

            <div className="mt-3 flex items-start gap-2 rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
              <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
              <span>{t('promote.responsibility')}</span>
            </div>
          </div>

          <div className="flex justify-end gap-2 border-t px-6 py-4">
            <Dialog.Close asChild>
              <button
                disabled={busy}
                className="rounded-lg border px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
              >
                {t('actions.cancel')}
              </button>
            </Dialog.Close>
            <button
              onClick={onConfirm}
              disabled={busy}
              data-testid="enrichment-promote-confirm"
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              <Sparkles className="h-4 w-4" />
              {busy ? t('promote.promoting') : t('promote.confirm')}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
