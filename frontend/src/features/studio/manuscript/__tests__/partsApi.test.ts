import { describe, expect, it } from 'vitest';
import { groupChaptersByParts, type Part, type ChapterLike } from '../partsApi';

const part = (id: string, sort: number, over: Partial<Part> = {}): Part => ({
  part_id: id,
  book_id: 'b',
  title: id.toUpperCase(),
  path: id,
  sort_order: sort,
  lifecycle_state: 'active',
  ...over,
});

const ch = (id: string, sort: number, partId: string | null | undefined = undefined): ChapterLike => ({
  chapter_id: id,
  title: id,
  sort_order: sort,
  part_id: partId,
});

describe('groupChaptersByParts', () => {
  it('groups chapters under their active act, in part sort order', () => {
    const groups = groupChaptersByParts(
      [part('p2', 2), part('p1', 1)],
      [ch('c1', 1, 'p1'), ch('c2', 2, 'p2'), ch('c3', 3, 'p1')],
    );
    expect(groups.map((g) => g.partId)).toEqual(['p1', 'p2']); // sorted by part sort_order
    expect(groups[0].chapters.map((c) => c.chapter_id)).toEqual(['c1', 'c3']);
    expect(groups[1].chapters.map((c) => c.chapter_id)).toEqual(['c2']);
    expect(groups.some((g) => g.unassigned)).toBe(false); // every chapter homed → no bucket
  });

  it('orders chapters WITHIN a group by their own sort_order', () => {
    const groups = groupChaptersByParts([part('p1', 1)], [ch('late', 9, 'p1'), ch('early', 1, 'p1')]);
    expect(groups[0].chapters.map((c) => c.chapter_id)).toEqual(['early', 'late']);
  });

  it('drops null/undefined part_id chapters into a trailing Unassigned bucket', () => {
    const groups = groupChaptersByParts(
      [part('p1', 1)],
      [ch('homed', 1, 'p1'), ch('flatNull', 2, null), ch('flatUndef', 3)],
    );
    expect(groups).toHaveLength(2);
    const bucket = groups[groups.length - 1];
    expect(bucket.unassigned).toBe(true);
    expect(bucket.partId).toBeNull();
    expect(bucket.chapters.map((c) => c.chapter_id)).toEqual(['flatNull', 'flatUndef']);
  });

  it('treats a chapter pointing at a TRASHED or unknown act as Unassigned (never dropped)', () => {
    const groups = groupChaptersByParts(
      [part('p1', 1), part('pTrashed', 2, { lifecycle_state: 'trashed' })],
      [ch('a', 1, 'pTrashed'), ch('b', 2, 'ghost-id'), ch('c', 3, 'p1')],
    );
    // only the active part renders as a group; a+b fall to Unassigned (no chapter lost)
    expect(groups.filter((g) => !g.unassigned).map((g) => g.partId)).toEqual(['p1']);
    const bucket = groups.find((g) => g.unassigned)!;
    expect(bucket.chapters.map((c) => c.chapter_id).sort()).toEqual(['a', 'b']);
  });

  it('renders an empty act (a just-created act with no chapters yet)', () => {
    const groups = groupChaptersByParts([part('p1', 1)], []);
    expect(groups).toEqual([{ partId: 'p1', title: 'P1', unassigned: false, chapters: [] }]);
  });

  it('hides an empty Unassigned bucket by default, shows it with alwaysShowUnassigned', () => {
    expect(groupChaptersByParts([part('p1', 1)], [])).toHaveLength(1); // no bucket
    const withBucket = groupChaptersByParts([part('p1', 1)], [], { alwaysShowUnassigned: true });
    expect(withBucket[withBucket.length - 1].unassigned).toBe(true);
  });

  it('a legacy/flat book (no parts) shows only the Unassigned bucket', () => {
    const groups = groupChaptersByParts([], [ch('a', 1), ch('b', 2)]);
    expect(groups).toHaveLength(1);
    expect(groups[0].unassigned).toBe(true);
    expect(groups[0].chapters.map((c) => c.chapter_id)).toEqual(['a', 'b']);
  });

  it('does not mutate its inputs', () => {
    const parts = [part('p2', 2), part('p1', 1)];
    const chapters = [ch('c2', 2, 'p2'), ch('c1', 1, 'p1')];
    groupChaptersByParts(parts, chapters);
    expect(parts.map((p) => p.part_id)).toEqual(['p2', 'p1']); // original order intact
    expect(chapters.map((c) => c.chapter_id)).toEqual(['c2', 'c1']);
  });
});
