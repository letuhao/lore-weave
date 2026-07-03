// C6 hunk-review — split a proposed prose REWRITE into accept/reject hunks.
//
// A `replace_selection` proposal replaces the selected span (OLD) with the
// agent's rewrite (NEW). Instead of an all-or-nothing Apply, we diff the two,
// group consecutive changes into HUNKS, and let the human accept/reject each,
// then reconstruct the text that actually gets written.
//
// Granularity is SENTENCE, not line, and deliberately so: ProseMirror hands the
// chat the selection via `textBetween(from,to,' ')`, which collapses block
// breaks to spaces — so paragraph "lines" don't survive the trip, but sentences
// do. A prose rewrite also reads naturally as "these sentences changed". We
// reuse the existing LCS line-diff (wikiDiff.diffLines) over the sentence units.
//
// Reconstruction preserves PARAGRAPH breaks that exist in the NEW proposal: each
// unit remembers whether a newline followed it in its source, so a partial accept
// rejoins with '\n\n' at those seams instead of flattening the rewrite to one
// run-on blob (the OLD side is inherently space-joined — see above — so rejected
// hunks stay single-spaced, matching the pre-existing whole-text behavior).

import { diffLines } from '@/features/wiki/lib/wikiDiff';

/** A sentence unit + whether a paragraph break (newline) followed it in the source. */
export interface Unit {
  text: string;
  breakAfter: boolean;
}

/** One contiguous run of changes surrounded by unchanged text. `oldUnits` is the
 *  removed sentences (empty ⇒ a pure insertion), `newUnits` the added sentences
 *  (empty ⇒ a pure deletion). Accepting the hunk keeps NEW; rejecting keeps OLD. */
export interface ProseHunk {
  id: number;
  oldUnits: Unit[];
  newUnits: Unit[];
}

/** An ordered piece of the reconstruction: either unchanged context, or a
 *  reference to a hunk whose accept/reject decision picks its units. */
export type HunkSegment = { kind: 'ctx'; unit: Unit } | { kind: 'hunk'; id: number };

export interface HunkModel {
  hunks: ProseHunk[];
  segments: HunkSegment[];
}

// Sentence enders. CJK enders (。！？) usually have NO trailing space, so we split
// with a zero-width look-behind right after them; Latin enders (.!?…), possibly
// followed by closing quotes/brackets, split on the whitespace that follows —
// but NOT when the next word is lowercase (dialogue tags `"Run!" she said`,
// abbreviations `e.g. foo`, which aren't real boundaries); newline runs always
// split (paragraph breaks).
const SENTENCE_SPLIT = /(?<=[。！？])|(?<=[.!?…]["'”’」』】）)\]]*)\s+(?![a-z])|\n+/;
// A split boundary that consumed a newline run — the unit before it ends a paragraph.
const NEWLINE_BOUNDARY = /\n/;

/** Split prose into trimmed sentence units, each tagged whether a paragraph break
 *  (a newline run) separated it from the NEXT unit. */
export function splitUnits(text: string): Unit[] {
  const normalized = text.replace(/\r\n?/g, '\n');
  // Capture the separators so we can tell which boundaries were paragraph breaks.
  const parts = normalized.split(new RegExp(`(${SENTENCE_SPLIT.source})`));
  const units: Unit[] = [];
  // split-with-capture yields [chunk, sep, chunk, sep, …]; a zero-width lookbehind
  // boundary produces an empty/undefined sep.
  for (let i = 0; i < parts.length; i += 2) {
    const raw = (parts[i] ?? '').trim();
    const sep = parts[i + 1] ?? '';
    if (!raw) continue;
    units.push({ text: raw, breakAfter: NEWLINE_BOUNDARY.test(sep) });
  }
  // The final unit ends the text — a trailing break is meaningless.
  if (units.length) units[units.length - 1].breakAfter = false;
  return units;
}

/** Split prose into trimmed sentence strings (the display/diff view of splitUnits). */
export function splitSentences(text: string): string[] {
  return splitUnits(text).map((u) => u.text);
}

/** Diff OLD→NEW at sentence granularity and group the changes into hunks. The
 *  break metadata is recovered by walking both unit streams in lockstep with the
 *  diff rows (each ctx consumes one old + one new; a del one old; an add one new). */
export function buildHunks(oldText: string, newText: string): HunkModel {
  const oldUnits = splitUnits(oldText);
  const newUnits = splitUnits(newText);
  const rows = diffLines(oldUnits.map((u) => u.text), newUnits.map((u) => u.text));
  const hunks: ProseHunk[] = [];
  const segments: HunkSegment[] = [];
  let oi = 0;
  let ni = 0;
  let i = 0;
  while (i < rows.length) {
    if (rows[i].type === 'ctx') {
      // Prefer the NEW side's break flag so the rewrite's paragraph structure wins.
      segments.push({ kind: 'ctx', unit: newUnits[ni] });
      oi++;
      ni++;
      i++;
      continue;
    }
    // A maximal run of del/add rows is one hunk.
    const oldHunk: Unit[] = [];
    const newHunk: Unit[] = [];
    while (i < rows.length && rows[i].type !== 'ctx') {
      if (rows[i].type === 'del') oldHunk.push(oldUnits[oi++]);
      else newHunk.push(newUnits[ni++]);
      i++;
    }
    const id = hunks.length;
    hunks.push({ id, oldUnits: oldHunk, newUnits: newHunk });
    segments.push({ kind: 'hunk', id });
  }
  return { hunks, segments };
}

/** Join units with a single space, or a blank line where a paragraph break
 *  followed (preserving the NEW proposal's structure). */
function joinUnits(units: Unit[]): string {
  let out = '';
  units.forEach((u, i) => {
    out += u.text;
    if (i < units.length - 1) out += u.breakAfter ? '\n\n' : ' ';
  });
  return out;
}

/** Reconstruct the final replacement text: context is kept, each hunk contributes
 *  its NEW units when accepted, its OLD units when rejected. */
export function reconstruct(model: HunkModel, accepted: ReadonlySet<number>): string {
  const seq: Unit[] = [];
  for (const seg of model.segments) {
    if (seg.kind === 'ctx') {
      seq.push(seg.unit);
    } else {
      const h = model.hunks[seg.id];
      seq.push(...(accepted.has(seg.id) ? h.newUnits : h.oldUnits));
    }
  }
  return joinUnits(seq);
}
