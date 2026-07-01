import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ManuscriptNode, ManuscriptRow } from '../types';

// Virtualizer needs a measured scroll element (0-sized in jsdom) — stub it to render every row.
vi.mock('@tanstack/react-virtual', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useVirtualizer: (opts: any) => ({
    getTotalSize: () => opts.count * 26,
    getVirtualItems: () => Array.from({ length: opts.count }, (_, index) => ({ index, start: index * 26, key: index })),
  }),
}));

// Mock the data hook — the view is tested in isolation from fetching.
const hook = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../useManuscriptTree', () => ({ useManuscriptTree: () => hook.value }));

import { ManuscriptNavigator } from '../ManuscriptNavigator';

const n = (id: string, kind: ManuscriptNode['kind'] = 'chapter', over: Partial<ManuscriptNode> = {}): ManuscriptNode => ({
  id, kind, title: `T-${id}`, number: kind === 'chapter' ? 5 : null, status: null, chapterId: id, hasChildren: kind !== 'scene', ...over,
});
const nodeRow = (node: ManuscriptNode, over: Partial<Extract<ManuscriptRow, { type: 'node' }>> = {}): ManuscriptRow =>
  ({ type: 'node', node, depth: 0, expanded: false, loading: false, ...over });
const moreRow = (over: Partial<Extract<ManuscriptRow, { type: 'more' }>> = {}): ManuscriptRow =>
  ({ type: 'more', parentKey: '', parentNodeId: null, depth: 0, ...over });

const base = (over: Record<string, unknown> = {}) => ({
  source: 'chapters', rows: [] as ManuscriptRow[], total: null, error: null,
  toggleExpand: vi.fn(), loadMore: vi.fn(), ...over,
});
const render_ = () => render(<ManuscriptNavigator bookId="b1" token="t" />);

describe('ManuscriptNavigator', () => {
  it('shows a loading state while the source resolves', () => {
    hook.value = base({ source: 'pending' });
    render_();
    expect(screen.getByTestId('manuscript-nav').textContent).toContain('manuscript.loading');
  });

  it('renders chapter rows + the total', () => {
    hook.value = base({ rows: [nodeRow(n('c1')), nodeRow(n('c2'))], total: 42 });
    render_();
    expect(screen.getByTestId('manuscript-row-c1')).toBeTruthy();
    expect(screen.getByTestId('manuscript-row-c2')).toBeTruthy();
    // count uses the interpolation key (global i18n mock returns keys)
    expect(screen.getByTestId('manuscript-nav').textContent).toContain('manuscript.count');
  });

  it('selecting a chapter row calls onSelect (not toggle)', () => {
    const onSelect = vi.fn();
    hook.value = base({ rows: [nodeRow(n('c1'))] });
    render(<ManuscriptNavigator bookId="b1" token="t" onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId('manuscript-row-c1'));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'c1' }));
  });

  it('clicking an ARC row toggles expansion (arcs are not a select target)', () => {
    const toggleExpand = vi.fn();
    hook.value = base({ source: 'outline', rows: [nodeRow(n('arc1', 'arc'))], toggleExpand });
    render_();
    fireEvent.click(screen.getByTestId('manuscript-row-arc1'));
    expect(toggleExpand).toHaveBeenCalledWith('arc1');
  });

  it('the caret toggles a chapter without selecting it', () => {
    const toggleExpand = vi.fn();
    const onSelect = vi.fn();
    hook.value = base({ source: 'outline', rows: [nodeRow(n('c1'))], toggleExpand });
    render(<ManuscriptNavigator bookId="b1" token="t" onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId('manuscript-caret-c1'));
    expect(toggleExpand).toHaveBeenCalledWith('c1');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('auto-loads a `more` row when it renders (infinite paging)', () => {
    const loadMore = vi.fn();
    hook.value = base({ rows: [nodeRow(n('c1')), moreRow({ parentKey: '', parentNodeId: null })], loadMore });
    render_();
    expect(loadMore).toHaveBeenCalledWith('', null);
  });

  it('filtering shows only matching LOADED rows and drops `more` (no auto-page-all)', () => {
    const loadMore = vi.fn();
    hook.value = base({
      rows: [nodeRow(n('c1', 'chapter', { title: 'Dragon' })), nodeRow(n('c2', 'chapter', { title: 'Phoenix' })), moreRow()],
      loadMore,
    });
    render_();
    loadMore.mockClear();
    fireEvent.change(screen.getByTestId('manuscript-filter'), { target: { value: 'phoenix' } });
    expect(screen.queryByTestId('manuscript-row-c1')).toBeNull();
    expect(screen.getByTestId('manuscript-row-c2')).toBeTruthy();
    // `more` dropped while filtering → no auto-paging of the whole book
    expect(screen.queryByTestId('manuscript-more')).toBeNull();
    expect(loadMore).not.toHaveBeenCalled();
  });
});
