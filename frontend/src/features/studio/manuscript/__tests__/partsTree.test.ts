import { describe, expect, it } from 'vitest';
import { buildPartsTree, chapterDisplayTitle, PART_UNASSIGNED_ID } from '../partsTree';
import { flatten } from '../tree';
import type { Part, ChapterLike } from '../partsApi';

const part = (id: string, sort: number, title: string): Part => ({
  part_id: id, book_id: 'b', title, path: id, sort_order: sort, lifecycle_state: 'active',
});
const ch = (id: string, sort: number, partId: string | null = null): ChapterLike => ({
  chapter_id: id, title: id, sort_order: sort, part_id: partId,
});

describe('buildPartsTree', () => {
  it('produces act group headers with nested chapters + a trailing Unassigned bucket', () => {
    const t = buildPartsTree(
      [part('p1', 1, 'Act I'), part('p2', 2, 'Act II')],
      [ch('c1', 1, 'p1'), ch('c2', 2, 'p2'), ch('flat', 3, null)],
    );
    const rows = flatten(t);
    // depth-0 = the three group headers (p1, p2, Unassigned), each 'part'; chapters at depth 1.
    const nodes = rows.filter((r) => r.type === 'node') as Extract<typeof rows[number], { type: 'node' }>[];
    const heads = nodes.filter((r) => r.depth === 0);
    expect(heads.map((r) => r.node.id)).toEqual(['p1', 'p2', PART_UNASSIGNED_ID]);
    expect(heads.every((r) => r.node.kind === 'part')).toBe(true);
    // acts expanded by default → chapters visible under their act
    const c1 = nodes.find((r) => r.node.id === 'c1')!;
    expect(c1.depth).toBe(1);
    expect(c1.node.kind).toBe('chapter');
    // no lazy-load affordances (fully loaded)
    expect(rows.some((r) => r.type === 'more' || r.type === 'skeleton')).toBe(false);
  });

  it('marks the Unassigned bucket via status and keeps it even when empty', () => {
    const t = buildPartsTree([part('p1', 1, 'Act I')], [ch('c1', 1, 'p1')]);
    const bucket = t.nodes[PART_UNASSIGNED_ID];
    expect(bucket).toBeDefined();
    expect(bucket.status).toBe('unassigned');
    expect(bucket.hasChildren).toBe(false); // empty bucket → no caret, still a drop target
  });

  it('a flat book with no acts shows only the Unassigned bucket holding every chapter', () => {
    const t = buildPartsTree([], [ch('a', 1), ch('b', 2)]);
    const rows = flatten(t).filter((r) => r.type === 'node') as any[];
    expect(rows[0].node.id).toBe(PART_UNASSIGNED_ID);
    expect(t.childrenOf[PART_UNASSIGNED_ID]).toEqual(['a', 'b']);
  });

  it('an empty act renders as a childless group header (no caret, count 0)', () => {
    const t = buildPartsTree([part('p1', 1, 'Empty Act')], []);
    expect(t.nodes['p1'].hasChildren).toBe(false);
    expect(t.nodes['p1'].childCount).toBe(0);
  });
});

describe('chapterDisplayTitle (F4 — never leak the storage filename)', () => {
  it('returns the chapter title when it has one', () => {
    expect(chapterDisplayTitle({ title: 'The rounding', sort_order: 1 })).toBe('The rounding');
  });

  it('falls back to a "Chapter {n}" label — NEVER the editor-<uuid>.txt filename', () => {
    const out = chapterDisplayTitle({ title: '', sort_order: 5, original_filename: 'editor-2d0fc71f.txt' } as any);
    expect(out).not.toContain('editor-');
    expect(out).not.toContain('.txt');
    expect(out).toBeTruthy();
  });

  it('treats a whitespace-only title as unnamed (still no filename leak)', () => {
    const out = chapterDisplayTitle({ title: '   ', sort_order: 2, original_filename: 'editor-x.txt' } as any);
    expect(out).not.toContain('editor-');
  });

  it('buildPartsTree renders an untitled chapter without its filename', () => {
    const t = buildPartsTree([], [{ chapter_id: 'c1', title: '', sort_order: 1, part_id: null, original_filename: 'editor-abc.txt' } as any]);
    expect(t.nodes['c1'].title).not.toContain('editor-');
    expect(t.nodes['c1'].title).not.toContain('.txt');
  });
});
