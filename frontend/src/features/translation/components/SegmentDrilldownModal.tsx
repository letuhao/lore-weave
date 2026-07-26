import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, RefreshCw, Check, AlertCircle, History } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getLanguageName } from '@/lib/languages';
import { FormDialog } from '@/components/shared/FormDialog';
import { useSegmentDrilldown } from '../hooks/useSegmentDrilldown';

interface Props {
  bookId: string;
  /** (chapter, language) being inspected; null → closed. */
  target: { chapterId: string; lang: string; title?: string } | null;
  onClose: () => void;
}

/** T2-M3 drill-down: per-segment translation status + "re-translate changed". */
export function SegmentDrilldownModal({ bookId, target, onClose }: Props) {
  const { t } = useTranslation('translation');
  const drill = useSegmentDrilldown(bookId, target, () => {
    toast.success(t('segments.retranslate_started'));
    onClose();
  });
  if (!target) return null;

  const footer = (
    <div className="flex w-full items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground">
        {t('segments.needs_count', { count: drill.needsCount })}
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={onClose}
          className="rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          {t('segments.close')}
        </button>
        <button
          onClick={drill.retranslate}
          disabled={drill.needsCount === 0 || drill.retranslating}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:brightness-110 disabled:opacity-50"
        >
          {drill.retranslating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          {t('segments.retranslate_changed', { count: drill.needsCount })}
        </button>
      </div>
    </div>
  );

  // DOCK-9 (docs/standards/dockable-gui.md): FormDialog replaces the previous hand-rolled
  // `fixed inset-0` backdrop+content pair — chrome-only migration, behavior/props unchanged.
  return (
    <FormDialog
      open
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={t('segments.title')}
      description={`${target.title || target.chapterId.slice(0, 8)} · ${getLanguageName(target.lang)}`}
      footer={footer}
    >
      {/* S2: a re-translate mutation failure must be visible — it was captured by the hook but
          never rendered, so a failed "re-translate changed" looked like nothing happened. */}
      {drill.retranslateError && (
        <div role="alert" data-testid="segment-retranslate-error" className="mb-3 flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11px] text-destructive">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          {t('segments.retranslate_failed')}
        </div>
      )}
      {drill.loading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : drill.error ? (
        <p className="py-6 text-center text-sm text-destructive">{drill.error}</p>
      ) : drill.segments.length === 0 ? (
        <p className="py-6 text-center text-xs text-muted-foreground">{t('segments.empty')}</p>
      ) : (
        <ul className="space-y-1.5">
          {drill.segments.map((s) => {
            const label = !s.translated
              ? t('segments.status_untranslated')
              : s.dirty
                ? t('segments.status_dirty')
                : s.stale
                  ? t('segments.status_stale')
                  : t('segments.status_clean');
            const Icon = !s.translated || s.dirty ? AlertCircle : s.stale ? History : Check;
            const tone = !s.translated || s.dirty
              ? 'text-amber-500'
              : s.stale
                ? 'text-sky-400'
                : 'text-green-500';
            return (
              <li
                key={s.segment_index}
                className={cn(
                  'flex items-center justify-between rounded-md border px-3 py-1.5 text-xs',
                  s.needs ? 'border-amber-500/30 bg-amber-500/[0.04]' : 'border-border',
                )}
              >
                <span className="font-mono text-muted-foreground">
                  #{s.segment_index + 1}
                  <span className="ml-2 opacity-60">
                    {t('segments.blocks_range', { from: s.start_block_index, to: s.end_block_index })}
                  </span>
                </span>
                <span className={cn('inline-flex items-center gap-1', tone)}>
                  <Icon className="h-3 w-3" strokeWidth={2.5} />
                  {label}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </FormDialog>
  );
}
