import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OutlineTree, flattenOutline } from '../OutlineTree';
import type { OutlineNode } from '../../types';

// Mock the work-resolution + outline read hooks; the component resolves the Work
// from bookId and reads GET /outline. Tests assert tree-build, nav, current
// marker, empty, and collapse via test-ids/attributes (real i18n → defaultValues).
const { workHook, outlineHook } = vi.hoisted(() => ({ workHook: vi.fn(), outlineHook: vi.fn() }));
vi.mock('../../hooks/useWork', () => ({ useWorkResolution: () => workHook() }));
vi.mock('../../hooks/useOutline', () => ({ useOutline: (...a: unknown[]) => outlineHook(...a) }));

function node(over: Partial<OutlineNode>): OutlineNode {
  return {
    id: 'n', project_id: 'p', parent_id: null, kind: 'scene', rank: 'm', title: 'T',
    chapter_id: null, story_order: 0, status: 'outline', synopsis: '', version: 1, ...over,
  };
}

function mountWith(nodes: OutlineNode[]) {
  workHook.mockReturnValue({ data: { status: 'found', work: { project_id: 'proj' } }, isLoading: false });
  outlineHook.mockReturnValue({ data: nodes, isLoading: false });
}

beforeEach(() => { workHook.mockReset(); outlineHook.mockReset(); });

describe('flattenOutline (T1.1a)', () => {
  it('builds a depth-annotated pre-order tree ordered by story_order', () => {
    const nodes = [
      node({ id: 'arc', kind: 'arc', parent_id: null, story_order: 0 }),
      node({ id: 'ch1', kind: 'chapter', parent_id: 'arc', story_order: 0 }),
      node({ id: 's2', kind: 'scene', parent_id: 'ch1', story_order: 1, title: 'S2' }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', story_order: 0, title: 'S1' }),
    ];
    const rows = flattenOutline(nodes, new Set());
    expect(rows.map((r) => r.node.id)).toEqual(['arc', 'ch1', 's1', 's2']); // s1 before s2 by story_order
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 2, 2]);
    expect(rows.find((r) => r.node.id === 'arc')!.hasChildren).toBe(true);
    expect(rows.find((r) => r.node.id === 's1')!.hasChildren).toBe(false);
  });

  it('collapsing a parent skips its children', () => {
    const nodes = [
      node({ id: 'ch1', kind: 'chapter', parent_id: null, story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', story_order: 0 }),
    ];
    expect(flattenOutline(nodes, new Set(['ch1'])).map((r) => r.node.id)).toEqual(['ch1']);
  });

  it('orders siblings without story_order by rank (chapters), nulls last (REVIEW-IMPL MED-3)', () => {
    const nodes = [
      node({ id: 'arc', kind: 'arc', parent_id: null, story_order: null, rank: 'a' }),
      node({ id: 'chB', kind: 'chapter', parent_id: 'arc', story_order: null, rank: 'b' }),
      node({ id: 'chA', kind: 'chapter', parent_id: 'arc', story_order: null, rank: 'a' }),
      // a legacy scene with a story_order sorts before its null-story_order sibling
      node({ id: 'sNull', kind: 'scene', parent_id: 'chA', story_order: null, rank: 'a' }),
      node({ id: 'sOrd', kind: 'scene', parent_id: 'chA', story_order: 5, rank: 'z' }),
    ];
    const rows = flattenOutline(nodes, new Set());
    expect(rows.map((r) => r.node.id)).toEqual(['arc', 'chA', 'sOrd', 'sNull', 'chB']);
  });

  it('renders a duplicate id only once (defensive seen-guard)', () => {
    const dup = node({ id: 'x', parent_id: null });
    expect(flattenOutline([dup, dup], new Set()).filter((r) => r.node.id === 'x')).toHaveLength(1);
  });
});

describe('OutlineTree (T1.1a)', () => {
  it('renders rows + navigates to a node\'s chapter on click', () => {
    mountWith([node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', title: 'Ch One', story_order: 0 })]);
    const onNav = vi.fn();
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={onNav} />);
    const rows = screen.getAllByTestId('outline-node');
    expect(rows.length).toBeGreaterThan(0);
    fireEvent.click(rows[0]);
    expect(onNav).toHaveBeenCalledWith('C1');
  });

  it('marks the current chapter', () => {
    mountWith([
      node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', story_order: 0 }),
      node({ id: 'ch2', kind: 'chapter', parent_id: null, chapter_id: 'C2', story_order: 1 }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C2" onNavigateChapter={vi.fn()} />);
    const current = screen.getAllByTestId('outline-node').find((r) => r.className.includes('border-l-primary'));
    expect(current).toBeTruthy();
  });

  it('shows the empty state with no outline', () => {
    mountWith([]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.getByTestId('outline-empty')).toBeInTheDocument();
  });

  it('collapses children when the chevron is clicked', () => {
    mountWith([
      node({ id: 'ch1', kind: 'chapter', parent_id: null, chapter_id: 'C1', story_order: 0 }),
      node({ id: 's1', kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', story_order: 0 }),
    ]);
    render(<OutlineTree bookId="b" token="t" currentChapterId="C1" onNavigateChapter={vi.fn()} />);
    expect(screen.getAllByTestId('outline-node')).toHaveLength(2);
    fireEvent.click(screen.getByTestId('outline-toggle'));
    expect(screen.getAllByTestId('outline-node')).toHaveLength(1); // scene hidden
  });
});
