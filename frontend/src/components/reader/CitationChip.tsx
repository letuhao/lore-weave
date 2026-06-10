import { useState, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useCitationContext } from './CitationContext';

/**
 * wiki-llm M7a — the anti-hallucination trust chip. Renders a citation mark's
 * `[n]` as a focusable superscript chip; on hover/focus it opens a self-contained
 * popover (NO live fetch — it uses the `snippet` captured at generation time)
 * showing the cited source + relevance + a "jump to source" link into the
 * chapter reader at the exact block (raw-search precise-scroll, P3-A). The link
 * appears only when the book context + a chapter anchor are known; otherwise the
 * popover still surfaces the snippet so the claim is auditable.
 */
export interface CitationAttrs {
  n?: number | null;
  cite_id?: string | null;
  source_type?: string | null;
  chapter_id?: string | null;
  block_index?: number | null;
  score?: number | null;
  snippet?: string | null;
}

export function CitationChip({
  attrs,
  children,
}: {
  attrs: CitationAttrs;
  children?: React.ReactNode;
}) {
  const { t } = useTranslation('reader');
  const { bookId } = useCitationContext();
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<number | null>(null);

  const show = useCallback(() => {
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    setOpen(true);
  }, []);
  const hide = useCallback(() => {
    closeTimer.current = window.setTimeout(() => setOpen(false), 120);
  }, []);

  const n = attrs.n ?? '?';
  const sourceType = attrs.source_type || 'passage';
  const jumpTo =
    bookId && attrs.chapter_id
      ? `/books/${bookId}/chapters/${attrs.chapter_id}/read${
          attrs.block_index != null ? `?block=${attrs.block_index}` : ''
        }`
      : null;

  return (
    // Focus handling lives on the WRAP (React's onFocus/onBlur bubble) so the
    // popover stays open while focus is anywhere inside it — letting a keyboard
    // user tab from the chip INTO the jump link. onBlur only hides when focus
    // leaves the wrap entirely (relatedTarget check).
    <span
      className="citation-chip-wrap"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) hide();
      }}
    >
      <button
        type="button"
        className="citation-chip"
        aria-label={t('citation.aria', { n })}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {/* the covered text — "[n]" in the body, "[n] label" in References — so
            the chip is correct in BOTH places (the body's separate superscript
            mark makes it a superscript chip; References stay full-size). */}
        {children}
      </button>
      {open && (
        <span className="citation-popover" role="tooltip" onMouseEnter={show} onMouseLeave={hide}>
          <span className="citation-popover-head">
            <span className={`citation-source citation-source-${sourceType}`}>
              {t(`citation.source.${sourceType}`, { defaultValue: sourceType })}
            </span>
            {attrs.score != null && attrs.score >= 0 && attrs.score <= 1 && (
              <span className="citation-score" title={t('citation.relevance')}>
                {Math.round(attrs.score * 100)}%
              </span>
            )}
          </span>
          {attrs.snippet && <span className="citation-snippet">{attrs.snippet}</span>}
          {jumpTo && (
            <Link className="citation-jump" to={jumpTo}>
              {t('citation.jump')}
            </Link>
          )}
        </span>
      )}
    </span>
  );
}
