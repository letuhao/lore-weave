import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';

/** Count the raw mentions in a summarize attribute's stored value. The value is the
 * write-synced cache of the active items — a JSON array for a list attr, or a bare
 * scalar. A non-array, non-empty value counts as one mention. */
export function countRawMentions(raw: string): number {
  const v = (raw ?? '').trim();
  if (!v) return 0;
  if (v.startsWith('[')) {
    try {
      const arr = JSON.parse(v);
      if (Array.isArray(arr)) return arr.filter((x) => String(x).trim() !== '').length;
    } catch {
      /* fall through to scalar */
    }
  }
  return 1;
}

/**
 * #26/#7 — the summarize (merge-rewrite) attribute body. Renders the LLM-synthesized
 * canonical value as the headline (the user's clean, deduped description) and tucks the
 * raw mentions — the lossless provenance the canonical was built from — under a collapsed
 * "sources" disclosure. When no canonical has been synthesized yet, it shows a pending hint
 * (the end-of-extraction-job pass fills it in) while still exposing the raw card.
 */
export function SummarizeAttrBody({
  canonicalValue,
  canonicalDirty,
  rawValue,
  rawCard,
}: {
  canonicalValue?: string | null;
  canonicalDirty?: boolean;
  rawValue: string;
  rawCard: ReactNode;
}) {
  const { t } = useTranslation('entityEditor');
  const canonical = (canonicalValue ?? '').trim();
  const rawCount = countRawMentions(rawValue);

  return (
    <div className="space-y-2">
      {canonical ? (
        <div className="rounded-md border border-info/30 bg-info/5 px-3 py-2">
          <div className="mb-1 flex items-center gap-1.5">
            <Sparkles className="h-3 w-3 text-info" />
            <span className="text-[10px] font-semibold uppercase tracking-wide text-info">
              {t('summarize.canonical_label')}
            </span>
            {canonicalDirty && (
              <span className="text-[10px] text-muted-foreground">· {t('summarize.pending_dirty')}</span>
            )}
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{canonical}</p>
        </div>
      ) : (
        <p className="px-1 text-xs text-muted-foreground">
          {rawCount > 0 ? t('summarize.pending_new') : t('summarize.empty')}
        </p>
      )}

      <details className="group">
        <summary className="cursor-pointer select-none text-[11px] text-muted-foreground hover:text-foreground">
          {t('summarize.sources', { count: rawCount })}
        </summary>
        <div className="mt-2">{rawCard}</div>
      </details>
    </div>
  );
}
