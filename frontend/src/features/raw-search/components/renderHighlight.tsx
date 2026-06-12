import type { ReactNode } from 'react';

// Render a snippet with the book-service-provided match spans wrapped in <mark>.
//
// `ranges` are Unicode CODE-POINT offsets into `snippet` (book-service emits
// rune offsets — review-impl MED-2). We index by code point via Array.from so
// supplementary-plane characters (e.g. CJK Ext-B 𠮷, U+20000+) don't misalign;
// a naive String.slice (UTF-16) would split surrogate pairs and shift the mark.
//
// Empty `ranges` (a trigram-only hit with no exact substring) → plain text.
export function renderHighlight(snippet: string, ranges: number[][]): ReactNode[] {
  if (!ranges || ranges.length === 0) return [snippet];
  const cp = Array.from(snippet); // code points, not UTF-16 units
  const out: ReactNode[] = [];
  let cursor = 0;
  // Sort by start so the cursor walk is correct even if Phase-3 returns spans
  // out of order (FE-MULTIRANGE); the cursor-max below absorbs any overlap.
  const sorted = [...ranges].sort((a, b) => a[0] - b[0]);
  sorted.forEach(([start, end], i) => {
    const s = Math.max(0, Math.min(start, cp.length));
    const e = Math.max(s, Math.min(end, cp.length));
    if (s > cursor) out.push(cp.slice(cursor, s).join(''));
    if (e > s) {
      out.push(
        <mark
          key={i}
          className="rounded bg-yellow-500/25 px-0.5 text-foreground"
        >
          {cp.slice(s, e).join('')}
        </mark>,
      );
    }
    cursor = Math.max(cursor, e);
  });
  if (cursor < cp.length) out.push(cp.slice(cursor).join(''));
  return out;
}
