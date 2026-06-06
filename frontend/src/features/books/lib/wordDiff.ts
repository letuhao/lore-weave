// Word-level diff between two single lines — a presentation refinement for the
// side-by-side view (the server diff is line-level). LCS over whitespace-split
// tokens; returns, for each side, the tokens tagged changed/unchanged so a
// changed delete-line vs its paired insert-line can highlight only the words
// that actually differ.

import type { DiffLine } from '../types';

export type WordToken = { text: string; changed: boolean };

// CJK ranges (Chinese/Japanese/Korean + fullwidth + kana). These scripts don't
// put spaces between words, so a `\S+` token would swallow a whole line and the
// word-level highlight would be useless — split each CJK char as its own token.
const CJK = '\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uac00-\\ud7af\\uf900-\\ufaff\\uff00-\\uffef';
const TOKEN_RE = new RegExp(`[${CJK}]|[^${CJK}\\s]+|\\s+`, 'g');

// Tokenize losslessly: a single CJK char, OR a run of non-CJK-non-space (a Latin
// word), OR a whitespace run. Re-joining the tokens reproduces the input.
function tokenize(s: string): string[] {
  return s.match(TOKEN_RE) ?? [];
}

/**
 * Returns [leftTokens, rightTokens]. A token is `changed:false` when it is part
 * of the longest common subsequence of the two token streams, else `true`.
 */
export function wordDiff(a: string, b: string): [WordToken[], WordToken[]] {
  const at = tokenize(a);
  const bt = tokenize(b);
  const n = at.length;
  const m = bt.length;

  // LCS DP table.
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = at[i] === bt[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }

  const left: WordToken[] = [];
  const right: WordToken[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (at[i] === bt[j]) {
      left.push({ text: at[i], changed: false });
      right.push({ text: bt[j], changed: false });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      left.push({ text: at[i], changed: true });
      i++;
    } else {
      right.push({ text: bt[j], changed: true });
      j++;
    }
  }
  for (; i < n; i++) left.push({ text: at[i], changed: true });
  for (; j < m; j++) right.push({ text: bt[j], changed: true });
  return [left, right];
}

// A row in the side-by-side view: a left cell and/or a right cell. `change`
// rows carry word-level tokens; pure delete/insert rows have one side only.
export type SideCell = { text: string; words?: WordToken[] };
export type SideRow = {
  type: 'equal' | 'change' | 'delete' | 'insert';
  left?: SideCell;
  right?: SideCell;
};

/**
 * Aligns the server line-diff into left/right rows for side-by-side rendering.
 * Equal lines occupy one row on both sides. A run of deletes+inserts is a change
 * block whose lines are paired (delete[k] ↔ insert[k]) with word-level diff;
 * unpaired deletes are left-only rows, unpaired inserts right-only rows.
 */
export function alignSideBySide(diff: DiffLine[]): SideRow[] {
  const rows: SideRow[] = [];
  let i = 0;
  while (i < diff.length) {
    if (diff[i].op === 'equal') {
      rows.push({ type: 'equal', left: { text: diff[i].text }, right: { text: diff[i].text } });
      i++;
      continue;
    }
    const dels: string[] = [];
    const ins: string[] = [];
    while (i < diff.length && diff[i].op === 'delete') dels.push(diff[i++].text);
    while (i < diff.length && diff[i].op === 'insert') ins.push(diff[i++].text);
    const max = Math.max(dels.length, ins.length);
    for (let k = 0; k < max; k++) {
      const l = k < dels.length ? dels[k] : undefined;
      const r = k < ins.length ? ins[k] : undefined;
      if (l !== undefined && r !== undefined) {
        const [lw, rw] = wordDiff(l, r);
        rows.push({ type: 'change', left: { text: l, words: lw }, right: { text: r, words: rw } });
      } else if (l !== undefined) {
        rows.push({ type: 'delete', left: { text: l } });
      } else if (r !== undefined) {
        rows.push({ type: 'insert', right: { text: r } });
      }
    }
  }
  return rows;
}
