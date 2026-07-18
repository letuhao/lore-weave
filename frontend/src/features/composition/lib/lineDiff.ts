// S5-B4 — a minimal line-level diff for the branch prose audit (canon ↔ dị bản).
// LCS over lines → a merged sequence of context / deleted / added rows. Small texts
// (a scene), computed client-side; no dependency. Deterministic, pure, testable.
export type DiffRow = { type: 'ctx' | 'del' | 'add'; text: string };

function splitLines(s: string): string[] {
  // Trailing newline shouldn't add a phantom empty row.
  return s.replace(/\n+$/, '').split('\n');
}

/**
 * Diff `before` (canon) → `after` (dị bản) at line granularity. Unchanged lines are
 * `ctx`, lines only in `before` are `del`, lines only in `after` are `add`, in an order
 * that reads top-to-bottom (dels before the adds that replace them).
 */
export function lineDiff(before: string, after: string): DiffRow[] {
  const a = splitLines(before);
  const b = splitLines(after);
  const n = a.length;
  const m = b.length;
  // LCS length table.
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      rows.push({ type: 'ctx', text: a[i] });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      rows.push({ type: 'del', text: a[i] });
      i++;
    } else {
      rows.push({ type: 'add', text: b[j] });
      j++;
    }
  }
  while (i < n) rows.push({ type: 'del', text: a[i++] });
  while (j < m) rows.push({ type: 'add', text: b[j++] });
  return rows;
}

/** True when the two texts are identical after trailing-newline normalization. */
export function isUnchanged(before: string, after: string): boolean {
  return splitLines(before).join('\n') === splitLines(after).join('\n');
}
