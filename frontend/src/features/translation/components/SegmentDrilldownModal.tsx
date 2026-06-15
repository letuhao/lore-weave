import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, RefreshCw, Check, AlertCircle, History } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getLanguageName } from '@/lib/languages';
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

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="flex max-h-[85vh] w-full max-w-md flex-col rounded-lg border bg-background shadow-xl"
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-label={t('segments.title')}
        >
          <div className="border-b px-5 py-4">
            <h2 className="text-sm font-semibold">{t('segments.title')}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {(target.title || target.chapterId.slice(0, 8))} · {getLanguageName(target.lang)}
            </p>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
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
          </div>

          <div className="flex items-center justify-between gap-2 border-t px-5 py-3">
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
        </div>
      </div>
    </>
  );
}
