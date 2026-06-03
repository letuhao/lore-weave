import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { Proposal } from '../types';

/** Below this count the dimensions collapse behind a "show more" expander, so a
 *  5-dimension draft doesn't dominate the detail pane (LE-066). */
const COLLAPSE_AT = 3;

/** The per-dimension generated lore (历史 / 地理 / 文化 / …) rendered as cards. The
 *  structured map lives in provenance_json.dimensions; falls back to the raw content
 *  summary if absent. */
export function DimensionList({ proposal }: { proposal: Proposal }) {
  const { t } = useTranslation('enrichment');
  const [expanded, setExpanded] = useState(false);
  const dims = proposal.provenance_json?.dimensions ?? {};
  const entries = Object.entries(dims);

  if (entries.length === 0) {
    return (
      <pre className="whitespace-pre-wrap font-serif text-sm leading-relaxed text-foreground">
        {proposal.content}
      </pre>
    );
  }

  const collapsible = entries.length > COLLAPSE_AT;
  const shown = collapsible && !expanded ? entries.slice(0, COLLAPSE_AT) : entries;
  const hidden = entries.length - COLLAPSE_AT;

  return (
    <div className="space-y-2" data-testid="enrichment-dimensions">
      <p className="text-[11px] text-muted-foreground">
        {t('detail.dimensions', { count: entries.length })}
      </p>
      {shown.map(([dim, text]) => (
        <div key={dim} className="rounded-lg border bg-card px-3 py-2">
          <div className="mb-0.5 text-[11px] font-medium text-primary">{dim}</div>
          <p className="font-serif text-sm leading-relaxed text-foreground">{text}</p>
        </div>
      ))}
      {collapsible && (
        <button
          onClick={() => setExpanded((v) => !v)}
          data-testid="enrichment-dimensions-toggle"
          className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
        >
          {expanded ? (
            <>
              <ChevronUp className="h-3 w-3" /> {t('detail.show_less')}
            </>
          ) : (
            <>
              <ChevronDown className="h-3 w-3" /> {t('detail.show_more', { count: hidden })}
            </>
          )}
        </button>
      )}
    </div>
  );
}
