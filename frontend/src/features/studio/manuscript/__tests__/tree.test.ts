import { describe, expect, it } from 'vitest';
import { appendChildren, flatten, hasMore, setExpanded, setLoading } from '../tree';
import { ROOT_KEY, emptyTree, type ManuscriptNode } from '../types';

const node = (id: string, kind: ManuscriptNode['kind'] = 'chapter', over: Partial<ManuscriptNode> = {}): ManuscriptNode => ({
  id, kind, title: id, number: null, status: null, chapterId: id, hasChildren: kind !== 'scene', childCount: null, ...over,
});

describe('manuscript tree', () => {
  it('flattens an empty tree to nothing', () => {
    expect(flatten(emptyTree())).toEqual([]);
  });

  it('appends a root page and emits a `more` row when a cursor remains', () => {
    const t = appendChildren(emptyTree(), ROOT_KEY, [node('a'), node('b')], 'cursor2');
    const rows = flatten(t);
    expect(rows.map((r) => r.type)).toEqual(['node', 'node', 'more']);
    expect(hasMore(t, ROOT_KEY)).toBe(true);
  });

  it('no `more` row on the last page (null cursor)', () => {
    const t = appendChildren(emptyTree(), ROOT_KEY, [node('a')], null);
    expect(flatten(t).map((r) => r.type)).toEqual(['node']);
    expect(hasMore(t, ROOT_KEY)).toBe(false);
  });

  it('dedupes ids when a page overlaps a previous one (idempotent re-fetch)', () => {
    let t = appendChildren(emptyTree(), ROOT_KEY, [node('a'), node('b')], 'c');
    t = appendChildren(t, ROOT_KEY, [node('b'), node('c')], null); // b repeats
    const ids = flatten(t).filter((r) => r.type === 'node').map((r) => (r as { node: ManuscriptNode }).node.id);
    expect(ids).toEqual(['a', 'b', 'c']);
  });

  it('shows an expanded node’s loaded children at depth+1', () => {
    let t = appendChildren(emptyTree(), ROOT_KEY, [node('arc', 'arc')], null);
    t = appendChildren(t, 'arc', [node('ch1'), node('ch2')], null);
    t = setExpanded(t, 'arc', true);
    const rows = flatten(t);
    expect(rows.map((r) => (r.type === 'node' ? `${r.node.id}@${r.depth}` : 'more')))
      .toEqual(['arc@0', 'ch1@1', 'ch2@1']);
  });

  it('a collapsed node hides its children', () => {
    let t = appendChildren(emptyTree(), ROOT_KEY, [node('arc', 'arc')], null);
    t = appendChildren(t, 'arc', [node('ch1')], null);
    // expanded defaults to false → children not walked
    expect(flatten(t).map((r) => (r.type === 'node' ? r.node.id : 'more'))).toEqual(['arc']);
  });

  it('emits a `more` row under an expanded node that has further children', () => {
    let t = appendChildren(emptyTree(), ROOT_KEY, [node('arc', 'arc')], null);
    t = appendChildren(t, 'arc', [node('ch1')], 'childCursor');
    t = setExpanded(t, 'arc', true);
    const rows = flatten(t);
    // arc, ch1, then a `more` for arc's children
    expect(rows.map((r) => r.type)).toEqual(['node', 'node', 'more']);
    expect((rows[2] as { parentKey: string }).parentKey).toBe('arc');
  });

  it('emits shimmer skeletons while a parent’s FIRST page is loading (nothing loaded yet)', () => {
    // root loading, no children yet → two skeleton rows, no `more`.
    const t = setLoading(emptyTree(), ROOT_KEY, true);
    expect(flatten(t).map((r) => r.type)).toEqual(['skeleton', 'skeleton']);
  });

  it('a newly-expanded node that is loading shimmers under itself (depth+1)', () => {
    let t = appendChildren(emptyTree(), ROOT_KEY, [node('arc', 'arc')], null);
    t = setExpanded(t, 'arc', true);
    t = setLoading(t, 'arc', true); // expanded, children not loaded yet
    const rows = flatten(t);
    expect(rows.map((r) => r.type)).toEqual(['node', 'skeleton', 'skeleton']);
    expect((rows[1] as { depth: number }).depth).toBe(1);
  });

  it('once a page is loaded, a further cursor shows `more` NOT a skeleton (even mid second-page load)', () => {
    let t = appendChildren(emptyTree(), ROOT_KEY, [node('a')], 'cursor2');
    t = setLoading(t, ROOT_KEY, true); // loading the SECOND page
    // a row is already on screen → we page, not shimmer over it.
    expect(flatten(t).map((r) => r.type)).toEqual(['node', 'more']);
  });
});
