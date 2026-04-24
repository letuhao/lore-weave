import type { ReactNode } from 'react';
import { createElement } from 'react';

// C8 (D-K19e-γb-01) — wrap each query-term substring in the text with
// <mark> for drawer-search result cards.
//
// Design decisions:
//   - Whitespace split on the query → OR-pattern regex.
//   - Tokens < 2 chars dropped. Keeps highlighting meaningful and
//     regex engine cheap. CJK single-char users lose highlighting on
//     one-char searches — documented trade-off, revisit if real users
//     complain. (Typical search is 2+ chars anyway.)
//   - Case-insensitive match; original case preserved in render.
//   - Regex special chars escaped — no ReDoS, no literal-match bypass.
//   - Returns ReactNode[] so callers `{highlightTokens(...)}` drop in
//     directly; React escapes the text nodes so no XSS surface.
//
// Not exported as a React component because the consumer
// (DrawerResultCard) already has JSX and prefers an inline array.

export function highlightTokens(text: string, query: string): ReactNode[] {
  const rawTokens = query.split(/\s+/).filter((t) => t.length >= 2);
  if (rawTokens.length === 0) return [text];
  const escaped = rawTokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const re = new RegExp(`(${escaped.join('|')})`, 'gi');
  // String.split with a capturing group: odd indices are the matches.
  return text.split(re).map((part, i) =>
    i % 2 === 1
      ? createElement(
          'mark',
          {
            key: i,
            className:
              'bg-yellow-500/25 text-foreground rounded px-0.5',
          },
          part,
        )
      : part,
  );
}
