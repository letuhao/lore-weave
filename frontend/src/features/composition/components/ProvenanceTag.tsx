// LOOM Composition (T5.3) — AI-provenance hover tag.
// A tiny floating label shown over a provenance span on hover: "AI · <model> ·
// unreviewed/reviewed" + a hint to click to review. All data is read straight
// from the span's data-* attributes (no fetch) — mirrors GlossaryTooltip's
// document-level mouseover pattern, scoped to `.provenance-mark`.
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

type Tag = { x: number; y: number; status: string; source: string; model: string | null };

export function ProvenanceTag() {
  const { t } = useTranslation('composition');
  const [tag, setTag] = useState<Tag | null>(null);

  const onOver = useCallback((e: MouseEvent) => {
    const el = (e.target as HTMLElement).closest('.provenance-mark') as HTMLElement | null;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setTag({
      x: rect.left,
      y: rect.top - 6,
      status: el.dataset.status || 'unreviewed',
      source: el.dataset.source || 'ai',
      model: el.dataset.model || null,
    });
  }, []);

  const onOut = useCallback((e: MouseEvent) => {
    const el = (e.target as HTMLElement).closest('.provenance-mark');
    if (el) setTag(null);
  }, []);

  useEffect(() => {
    document.addEventListener('mouseover', onOver);
    document.addEventListener('mouseout', onOut);
    return () => {
      document.removeEventListener('mouseover', onOver);
      document.removeEventListener('mouseout', onOut);
    };
  }, [onOver, onOut]);

  if (!tag) return null;
  const sourceLabel = tag.source === 'ai' ? t('provenance.ai', { defaultValue: 'AI' }) : tag.source;
  const statusLabel =
    tag.status === 'reviewed'
      ? t('provenance.reviewed', { defaultValue: 'reviewed' })
      : t('provenance.unreviewed', { defaultValue: 'unreviewed' });

  return (
    <div
      data-testid="provenance-tag"
      className="pointer-events-none fixed z-[100] -translate-y-full rounded bg-neutral-900/90 px-2 py-1 text-[11px] text-white shadow-lg"
      style={{ left: tag.x, top: tag.y }}
    >
      <span className="font-semibold">{sourceLabel}</span>
      {tag.model && <span className="text-neutral-300"> · {tag.model}</span>}
      <span className="text-neutral-300"> · {statusLabel}</span>
      {tag.status !== 'reviewed' && (
        <span className="ml-1 text-neutral-400">{t('provenance.clickToReview', { defaultValue: '(click to review)' })}</span>
      )}
    </div>
  );
}
