import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { DrawerSearchHit } from '../api';

// K19e.4 — slide-over detail panel for a :Passage drawer. The BE
// already returned the full ``text`` on the list response (no detail
// endpoint exists by design — the passage body fits in the search
// payload). Rendering-only; no second BE call.
//
// Mirrors the K19d β EntityDetailPanel Radix Dialog pattern so users
// get the same focus-trap + ESC behaviour on any slide-over.

export interface DrawerDetailPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  hit: DrawerSearchHit | null;
}

function formatMatchPercent(raw: number): string {
  const pct = Math.round(raw * 100);
  return `${Math.max(0, Math.min(100, pct))}%`;
}

function formatCreatedAt(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function DrawerDetailPanel({
  open,
  onOpenChange,
  hit,
}: DrawerDetailPanelProps) {
  const { t } = useTranslation('knowledge');

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-40 bg-black/40 animate-in fade-in"
          data-testid="drawer-detail-overlay"
        />
        <Dialog.Content
          className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col overflow-hidden bg-card shadow-xl animate-in slide-in-from-right"
          aria-describedby={undefined}
          data-testid="drawer-detail-panel"
        >
          <header className="flex items-center justify-between border-b px-4 py-3">
            <Dialog.Title className="font-serif text-sm font-semibold">
              {t('drawers.detail.title')}
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label={t('drawers.detail.close')}
                title={t('drawers.detail.close')}
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
                data-testid="drawer-detail-close"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </header>

          {hit && (
            <div className="flex-1 overflow-y-auto px-4 py-3 text-[12px]">
              <dl className="mb-4 grid grid-cols-[100px_1fr] gap-y-1.5 gap-x-3">
                <dt className="text-muted-foreground">
                  {t('drawers.detail.sourceType')}
                </dt>
                <dd className="font-mono">{hit.source_type}</dd>

                <dt className="text-muted-foreground">
                  {t('drawers.detail.sourceId')}
                </dt>
                <dd className="truncate font-mono" title={hit.source_id}>
                  {hit.source_id}
                </dd>

                <dt className="text-muted-foreground">
                  {t('drawers.detail.chunkIndex')}
                </dt>
                <dd className="tabular-nums">{hit.chunk_index}</dd>

                {hit.chapter_index != null && (
                  <>
                    <dt className="text-muted-foreground">
                      {t('drawers.detail.chapterIndex')}
                    </dt>
                    <dd className="tabular-nums">{hit.chapter_index}</dd>
                  </>
                )}

                <dt className="text-muted-foreground">
                  {t('drawers.detail.matchScore')}
                </dt>
                <dd className="tabular-nums">
                  {formatMatchPercent(hit.raw_score)}
                </dd>

                {hit.is_hub && (
                  <>
                    <dt className="text-muted-foreground">
                      {t('drawers.detail.hubLabel')}
                    </dt>
                    <dd
                      className="text-amber-700 dark:text-amber-300"
                      data-testid="drawer-detail-hub"
                    >
                      {t('drawers.detail.hubValue')}
                    </dd>
                  </>
                )}

                {hit.created_at && (
                  <>
                    <dt className="text-muted-foreground">
                      {t('drawers.detail.createdAt')}
                    </dt>
                    <dd>{formatCreatedAt(hit.created_at)}</dd>
                  </>
                )}
              </dl>

              <section>
                <h4 className="mb-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                  {t('drawers.detail.text')}
                </h4>
                <p className="whitespace-pre-wrap break-words text-foreground">
                  {hit.text}
                </p>
              </section>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
