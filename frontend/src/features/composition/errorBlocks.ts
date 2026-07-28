// Error blocks (atom-edit Phase D) — API + the OFFSET BRIDGE.
//
// THE HARD PART is not the API, it is the coordinate systems. The editor works in ProseMirror
// positions (which count node boundaries); the backend stores offsets into the FLATTENED text
// that `tiptap_doc_to_text` produces (each top-level block's `_text`, joined by a blank line).
// A mark computed in the wrong space points at the wrong prose, and the co-writer then confidently
// edits a passage the author never complained about.
//
// So the flattening here mirrors the backend's byte-for-byte: `addTextSnapshots` is the same
// helper that writes the `_text` snapshots the backend reads back, so
// `blocks.map(b => b._text).join('\n\n')` IS `tiptap_doc_to_text(doc)`.
//
// Offsets can still drift for a block containing inline atoms (an image contributes one PM
// position but its alt text to `_text`). That degrades SAFELY: the server re-validates
// `text[start:end] === quote` and re-anchors by quote when it disagrees, so a drift costs a
// re-anchor, never a corrupted splice.
import type { JSONContent } from '@tiptap/react';
import type { Editor } from '@tiptap/react';

import { addTextSnapshots } from '@/lib/tiptap-utils';
import { apiJson } from '../../api';

const BASE = '/v1/composition';

export type ErrorBlockKind =
  | 'continuity' | 'voice' | 'pacing' | 'fact' | 'logic' | 'style' | 'other';
export type ErrorBlockStatus =
  | 'open' | 'proposed' | 'resolved' | 'dismissed' | 'orphaned';

export interface ErrorBlock {
  id: string;
  project_id: string;
  chapter_id: string | null;
  job_id: string | null;
  start_offset: number;
  end_offset: number;
  quote: string;
  source_fingerprint: string;
  source: string;
  kind: ErrorBlockKind;
  note: string;
  desired: string | null;
  status: ErrorBlockStatus;
  version: number;
  created_at?: string;
}

/** The statuses that still want the author's attention. `orphaned` counts: the mark was not
 *  resolved, we just lost track of the prose it pointed at, and hiding it would read as done. */
export const OPEN_STATUSES: ReadonlySet<ErrorBlockStatus> = new Set([
  'open', 'proposed', 'orphaned',
]);

/** Flatten a Tiptap doc exactly as the backend's `tiptap_doc_to_text` does. */
export function flattenDoc(doc: JSONContent): string {
  const snapped = addTextSnapshots(doc);
  return (snapped.content ?? [])
    .map((b) => (b as { _text?: string })._text ?? '')
    .join('\n\n');
}

/** A stable id for one exact flattening, mirroring the server's `fingerprint()` shape.
 *
 *  Not cryptographic and not required to match the server's hash — it only has to CHANGE when
 *  the flattening changes. The server compares a block's stored fingerprint with the one it
 *  computes now; equal means the offsets are still meaningful, different means the whole
 *  coordinate space moved and only `quote` may be trusted. A cheap 32-bit rolling hash is
 *  sufficient for that and avoids pulling a crypto dependency into the editor path. */
export function fingerprintText(text: string): string {
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
    h2 = Math.imul(h2 + c + i, 0x85ebca6b) >>> 0;
  }
  return `fnv:${h1.toString(16).padStart(8, '0')}${h2.toString(16).padStart(8, '0')}:${text.length}`;
}

export interface SelectionSpan {
  start: number;
  end: number;
  quote: string;
  fingerprint: string;
}

/**
 * Translate the editor's current selection into FLAT-TEXT coordinates.
 *
 * Returns null when the selection is empty or is only whitespace — an anchorless mark is a mark
 * the server can never re-locate, so it must never be created in the first place.
 */
export function selectionToSpan(editor: Editor): SelectionSpan | null {
  const { from, to } = editor.state.selection;
  if (to <= from) return null;

  const flat = flattenDoc(editor.getJSON());
  const blocks = flat.split('\n\n');

  // Walk to the top-level block holding `from`, then add the offset inside it. Deriving the
  // start from the BLOCK INDEX (rather than searching the flat text for the quote) is what
  // keeps a repeated line — "She nodded." three times in one chapter — unambiguous.
  const $from = editor.state.doc.resolve(from);
  const blockIndex = $from.depth === 0 ? 0 : $from.index(0);
  let start = 0;
  for (let i = 0; i < blockIndex && i < blocks.length; i++) start += blocks[i].length + 2;
  start += $from.depth === 0 ? 0 : from - $from.start(1);

  const quote = editor.state.doc.textBetween(from, to, '\n\n');
  if (!quote.trim()) return null;

  return { start, end: start + quote.length, quote, fingerprint: fingerprintText(flat) };
}

/** Minimal shape of the bits of a ProseMirror node this module reads — avoids importing
 *  `@tiptap/pm/model` types into a file the API layer also uses. */
interface PMNodeLike {
  childCount: number;
  child(i: number): { textContent: string; nodeSize: number };
  textBetween(from: number, to: number, sep?: string): string;
}

export interface PMRange { from: number; to: number }

/**
 * The INVERSE of `selectionToSpan`: a stored flat span → a ProseMirror range to decorate.
 *
 * Walks top-level blocks accumulating BOTH coordinates at once (flat characters and PM
 * positions), so the mapping never has to search the text for the quote — which is what keeps a
 * repeated line unambiguous in this direction too.
 *
 * Returns null when the span cannot be placed. The caller must then NOT decorate: a highlight
 * drawn over the wrong words is worse than no highlight, because it tells the author their
 * complaint is attached to prose it is not attached to.
 */
export function flatSpanToPM(doc: PMNodeLike, start: number, end: number): PMRange | null {
  if (end <= start || start < 0) return null;
  let flat = 0;
  let pmPos = 0;
  for (let i = 0; i < doc.childCount; i++) {
    const node = doc.child(i);
    const len = node.textContent.length;
    if (start >= flat && start < flat + len) {
      const contentStart = pmPos + 1;          // +1 steps inside the block's open token
      const from = contentStart + (start - flat);
      // Clamp to this block: a span that ran past a block boundary is not decorable as one
      // contiguous range, and silently truncating it would highlight less than was marked.
      if (end - flat > len) return null;
      return { from, to: contentStart + (end - flat) };
    }
    flat += len + 2;                            // the "\n\n" the flattening joins blocks with
    pmPos += node.nodeSize;
  }
  return null;
}

/** Map a block to a decorable range, VERIFYING the text still matches before trusting it.
 *
 *  The offsets and the document can disagree (an edit above the mark, a doc whose `_text`
 *  snapshots were rebuilt). Rather than decorate blind, confirm the range really contains the
 *  quote and otherwise report it as drifted, so the UI can say "this mark lost its place"
 *  instead of pointing at the wrong sentence. */
export function resolveBlockRange(doc: PMNodeLike, block: ErrorBlock): PMRange | null {
  const range = flatSpanToPM(doc, block.start_offset, block.end_offset);
  if (!range) return null;
  return doc.textBetween(range.from, range.to, '\n\n') === block.quote ? range : null;
}

// ── API ────────────────────────────────────────────────────────────────

export const errorBlocksApi = {
  list(
    projectId: string, chapterId: string, token: string,
    opts?: { status?: ErrorBlockStatus },
  ): Promise<{ blocks: ErrorBlock[]; open_count: number }> {
    const q = opts?.status ? `?status=${encodeURIComponent(opts.status)}` : '';
    return apiJson(`${BASE}/works/${projectId}/chapters/${chapterId}/error-blocks${q}`, { token });
  },

  create(
    projectId: string, chapterId: string,
    body: {
      start_offset: number; end_offset: number; quote: string; source_fingerprint: string;
      kind: ErrorBlockKind; note: string; desired?: string | null;
      draft_version?: number | null; job_id?: string | null;
    },
    token: string,
  ): Promise<ErrorBlock> {
    return apiJson(`${BASE}/works/${projectId}/chapters/${chapterId}/error-blocks`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },

  patch(
    blockId: string, body: { kind?: ErrorBlockKind; note?: string; desired?: string | null },
    version: number, token: string,
  ): Promise<ErrorBlock> {
    return apiJson(`${BASE}/error-blocks/${blockId}`, {
      method: 'PATCH', body: JSON.stringify(body), token,
      headers: { 'If-Match': String(version) },
    });
  },

  resolve(blockId: string, token: string, body?: { resolution?: string; proposal_id?: string }):
    Promise<ErrorBlock> {
    return apiJson(`${BASE}/error-blocks/${blockId}/resolve`, {
      method: 'POST', body: JSON.stringify(body ?? {}), token,
    });
  },

  dismiss(blockId: string, token: string, body?: { resolution?: string }): Promise<ErrorBlock> {
    return apiJson(`${BASE}/error-blocks/${blockId}/dismiss`, {
      method: 'POST', body: JSON.stringify(body ?? {}), token,
    });
  },

  /** The reverse of resolve/dismiss — a block closed by mistake. Without this the close was
   *  one-way, and the agent's undo hint pointed at a read that reverted nothing. */
  reopen(blockId: string, token: string): Promise<ErrorBlock> {
    return apiJson(`${BASE}/error-blocks/${blockId}/reopen`, { method: 'POST', token });
  },

  /** Soft-archive the mark itself — distinct from resolve/dismiss, which CLOSE it and keep it as
   *  a decision. This is "I marked the wrong passage", so the mark should stop existing. */
  remove(blockId: string, token: string): Promise<ErrorBlock> {
    return apiJson(`${BASE}/error-blocks/${blockId}`, { method: 'DELETE', token });
  },

  /** F3 — the undo `remove` owes. Shipped alongside it rather than after the first call site
   *  appears, because that is the order that keeps going wrong: the delete lands, the restore is
   *  "obvious later", and the author is left with an archived row nothing can reach. */
  restore(blockId: string, token: string): Promise<ErrorBlock> {
    return apiJson(`${BASE}/error-blocks/${blockId}/restore`, { method: 'POST', token });
  },
};
