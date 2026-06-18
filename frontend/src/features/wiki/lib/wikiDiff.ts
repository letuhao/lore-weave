// W1 — wiki suggestion diff helpers (pure, unit-tested).
//
// An AI-regenerated suggestion (the clobber-guard files one when a human-edited
// article is regenerated) stores an ENVELOPE in `diff_json`:
//   { body_json: <TipTap doc>, generation_status, generation_provenance? }
// i.e. a full proposed body, NOT a precomputed line diff. To show the human "what
// changed" we flatten both bodies to lines and run an LCS diff client-side.
import type { JSONContent } from '@tiptap/react';

export interface WikiAiRegenEnvelope {
  body_json: { content?: JSONContent[] } & Record<string, unknown>;
  generation_status: string;
  generation_provenance?: unknown;
}

/** Discriminate the AI-regen envelope from a (hypothetical) community field-diff —
 * mirrors the glossary BE discriminator (body_json present AND a string
 * generation_status; a plain TipTap doc / field diff has neither). Returns the
 * typed envelope or null. */
export function asAiRegenEnvelope(
  diff: Record<string, unknown> | null | undefined,
): WikiAiRegenEnvelope | null {
  if (!diff) return null;
  const body = diff['body_json'];
  const status = diff['generation_status'];
  if (body && typeof body === 'object' && typeof status === 'string') {
    return diff as unknown as WikiAiRegenEnvelope;
  }
  return null;
}

function nodeText(node: JSONContent): string {
  if (node.type === 'text') return node.text ?? '';
  const kids = node.content;
  if (!Array.isArray(kids)) return '';
  return kids.map(nodeText).join('');
}

/** Flatten a TipTap doc to one trimmed line per top-level block (list items each
 * become their own line). Empty lines are dropped. Granularity that reads well in
 * a block-level prose diff. */
export function tiptapToLines(doc: unknown): string[] {
  const content = (doc as { content?: JSONContent[] } | null | undefined)?.content;
  if (!Array.isArray(content)) return [];
  const lines: string[] = [];
  for (const block of content) {
    if (block.type === 'bulletList' || block.type === 'orderedList') {
      for (const item of block.content ?? []) {
        const t = nodeText(item).trim();
        if (t) lines.push(t);
      }
    } else {
      const t = nodeText(block).trim();
      if (t) lines.push(t);
    }
  }
  return lines;
}

export type DiffRow = { type: 'ctx' | 'del' | 'add'; text: string };

/** Classic LCS line diff → context / deletion / addition rows (old→new). */
export function diffLines(oldLines: string[], newLines: string[]): DiffRow[] {
  const n = oldLines.length;
  const m = newLines.length;
  // dp[i][j] = LCS length of oldLines[i:] vs newLines[j:]
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = oldLines[i] === newLines[j]
        ? dp[i + 1][j + 1] + 1
        : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (oldLines[i] === newLines[j]) {
      rows.push({ type: 'ctx', text: oldLines[i] });
      i++; j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push({ type: 'del', text: oldLines[i] });
      i++;
    } else {
      rows.push({ type: 'add', text: newLines[j] });
      j++;
    }
  }
  while (i < n) rows.push({ type: 'del', text: oldLines[i++] });
  while (j < m) rows.push({ type: 'add', text: newLines[j++] });
  return rows;
}
