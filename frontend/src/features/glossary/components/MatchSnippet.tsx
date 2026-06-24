import { useTranslation } from 'react-i18next';
import { type EntityMatch } from '../types';

/**
 * Renders a raw-search hit's verbatim snippet with the matched span(s) marked.
 * Highlights are CODE-POINT (rune) offsets from the backend, so we slice via
 * Array.from (code-point iteration) — UTF-16 `.slice` would split CJK/astral
 * characters and mis-align the highlight.
 */
export function MatchSnippet({ match }: { match: EntityMatch }) {
  const { t } = useTranslation('books');
  const chars = Array.from(match.snippet ?? '');
  const hls = [...(match.highlights ?? [])]
    .filter((h) => Array.isArray(h) && h.length === 2 && h[1] > h[0])
    .sort((a, b) => a[0] - b[0]);

  const parts: { text: string; hl: boolean }[] = [];
  let cursor = 0;
  for (const [s, e] of hls) {
    const start = Math.max(s, cursor);
    if (start > cursor) parts.push({ text: chars.slice(cursor, start).join(''), hl: false });
    if (e > start) parts.push({ text: chars.slice(start, e).join(''), hl: true });
    cursor = Math.max(cursor, e);
  }
  if (cursor < chars.length) parts.push({ text: chars.slice(cursor).join(''), hl: false });

  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] text-muted-foreground" data-testid="glossary-match-snippet">
      <span className="rounded bg-secondary px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide">
        {t(`glossary.match_field.${match.field_code}`, { defaultValue: match.field_code })}
      </span>
      <span className="truncate">
        {parts.map((p, i) =>
          p.hl ? (
            <mark key={i} className="rounded-sm bg-amber-400/30 text-foreground">{p.text}</mark>
          ) : (
            <span key={i}>{p.text}</span>
          ),
        )}
      </span>
    </span>
  );
}
