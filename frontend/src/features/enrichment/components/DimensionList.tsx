import { useTranslation } from 'react-i18next';
import type { Proposal } from '../types';

/** The per-dimension generated lore (历史 / 地理 / 文化 / …) rendered as cards. The
 *  structured map lives in provenance_json.dimensions; falls back to the raw content
 *  summary if absent. */
export function DimensionList({ proposal }: { proposal: Proposal }) {
  const { t } = useTranslation('enrichment');
  const dims = proposal.provenance_json?.dimensions ?? {};
  const entries = Object.entries(dims);

  if (entries.length === 0) {
    return (
      <pre className="whitespace-pre-wrap font-serif text-sm leading-relaxed text-foreground">
        {proposal.content}
      </pre>
    );
  }

  return (
    <div className="space-y-2" data-testid="enrichment-dimensions">
      <p className="text-[11px] text-muted-foreground">
        {t('detail.dimensions', { count: entries.length })}
      </p>
      {entries.map(([dim, text]) => (
        <div key={dim} className="rounded-lg border bg-card px-3 py-2">
          <div className="mb-0.5 text-[11px] font-medium text-primary">{dim}</div>
          <p className="font-serif text-sm leading-relaxed text-foreground">{text}</p>
        </div>
      ))}
    </div>
  );
}
