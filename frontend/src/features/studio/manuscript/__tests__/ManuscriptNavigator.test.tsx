import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { JumpResult, ManuscriptNode, ManuscriptRow } from '../types';

// Virtualizer needs a measured scroll element (0-sized in jsdom) — stub it to render every row.
vi.mock('@tanstack/react-virtual', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useVirtualizer: (opts: any) => ({
    getTotalSize: () => opts.count * 26,
    getVirtualItems: () => Array.from({ length: opts.count }, (_, index) => ({ index, start: index * 26, key: index })),
  }),
}));

// Mock the data hooks — the view is tested in isolation from fetching.
const hook = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../useManuscriptTree', () => ({ useManuscriptTree: () => hook.value }));
// The jump box is server-backed via useManuscriptJump; stub it (inactive by default).
const jump = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../useManuscriptJump', () => ({ useManuscriptJump: () => jump.value }));

import { ManuscriptNavigator } from '../ManuscriptNavigator';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';

const jumpBase = (over: Record<string, unknown> = {}) => ({
  query: '', setQuery: vi.fn(), results: [], searching: false, active: false, ...over,
});

const n = (id: string, kind: ManuscriptNode['kind'] = 'chapter', over: Partial<ManuscriptNode> = {}): ManuscriptNode => ({
  id, kind, title: `T-${id}`, number: kind === 'chapter' ? 5 : null, status: null, chapterId: id,
  hasChildren: kind !== 'scene', childCount: null, ...over,
});
const nodeRow = (node: ManuscriptNode, over: Partial<Extract<ManuscriptRow, { type: 'node' }>> = {}): ManuscriptRow =>
  ({ type: 'node', node, depth: 0, expanded: false, loading: false, ...over });
const moreRow = (over: Partial<Extract<ManuscriptRow, { type: 'more' }>> = {}): ManuscriptRow =>
  ({ type: 'more', parentKey: '', parentNodeId: null, depth: 0, ...over });
const skeletonRow = (over: Partial<Extract<ManuscriptRow, { type: 'skeleton' }>> = {}): ManuscriptRow =>
  ({ type: 'skeleton', depth: 0, key: 'sk-root-0', ...over });

const base = (over: Record<string, unknown> = {}) => ({
  source: 'chapters', rows: [] as ManuscriptRow[], total: null, error: null,
  counts: { arcs: null, chapters: null, scenes: null },
  toggleExpand: vi.fn(), loadMore: vi.fn(), collapseAll: vi.fn(), reload: vi.fn(), ...over,
});
const render_ = () => render(<ManuscriptNavigator bookId="b1" token="t" />);

beforeEach(() => { jump.value = jumpBase(); });

describe('ManuscriptNavigator', () => {
  it('shows a loading state while the source resolves', () => {
    hook.value = base({ source: 'pending' });
    render_();
    expect(screen.getByTestId('manuscript-nav').textContent).toContain('manuscript.loading');
  });

  it('renders chapter rows + the footer chapter total (flat import → ch only)', () => {
    hook.value = base({ rows: [nodeRow(n('c1')), nodeRow(n('c2'))], counts: { arcs: null, chapters: 42, scenes: null } });
    render_();
    expect(screen.getByTestId('manuscript-row-c1')).toBeTruthy();
    expect(screen.getByTestId('manuscript-row-c2')).toBeTruthy();
    // footer stat uses the interpolation key (global i18n mock returns keys); no arc/scene for a flat book
    const totals = screen.getByTestId('manuscript-totals').textContent!;
    expect(totals).toContain('manuscript.statChapters');
    expect(totals).not.toContain('manuscript.statArcs');
    expect(totals).not.toContain('manuscript.statScenes');
  });

  it('outline book footer shows arc · ch · sc totals', () => {
    hook.value = base({ source: 'outline', rows: [nodeRow(n('arc1', 'arc'))], counts: { arcs: 1, chapters: 12, scenes: 35 } });
    render_();
    const totals = screen.getByTestId('manuscript-totals').textContent!;
    expect(totals).toContain('manuscript.statArcs');
    expect(totals).toContain('manuscript.statChapters');
    expect(totals).toContain('manuscript.statScenes');
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

  it('typing drives the shared jump hook (server-backed search, not a client filter)', () => {
    const setQuery = vi.fn();
    hook.value = base({ rows: [nodeRow(n('c1'))] });
    jump.value = jumpBase({ setQuery });
    render_();
    fireEvent.change(screen.getByTestId('manuscript-filter'), { target: { value: 'phoenix' } });
    expect(setQuery).toHaveBeenCalledWith('phoenix');
  });

  it('an active search REPLACES the tree with the server result list; the tree is hidden', () => {
    const results: JumpResult[] = [
      { id: 's9', kind: 'scene', title: 'Bị phản bội', number: null, status: 'done', chapterId: 'ch3', path: ['Arc I', 'Ch 0003'] },
    ];
    const loadMore = vi.fn();
    hook.value = base({ rows: [nodeRow(n('c1')), moreRow()], loadMore });
    jump.value = jumpBase({ query: 'phản', active: true, results });
    render_();
    // tree rows + auto-paging suppressed while searching…
    expect(screen.queryByTestId('manuscript-row-c1')).toBeNull();
    expect(loadMore).not.toHaveBeenCalled();
    // …and the server hit (a scene NOT in the loaded tree) shows with its breadcrumb.
    const hit = screen.getByTestId('manuscript-result-s9');
    expect(hit.textContent).toContain('Bị phản bội');
    expect(hit.textContent).toContain('Arc I › Ch 0003');
  });

  it('selecting a search result calls onSelect with the hit as a node', () => {
    const onSelect = vi.fn();
    hook.value = base({ rows: [] });
    jump.value = jumpBase({
      query: 'x', active: true,
      results: [{ id: 'ch7', kind: 'chapter', title: 'Huyết chiến', number: 7, status: null, chapterId: 'ch7', path: ['Arc I'] }],
    });
    render(<ManuscriptNavigator bookId="b1" token="t" onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId('manuscript-result-ch7'));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'ch7', kind: 'chapter' }));
  });

  it('an active search with no results shows the empty/searching state', () => {
    hook.value = base({ rows: [nodeRow(n('c1'))] });
    jump.value = jumpBase({ query: 'zzz', active: true, results: [], searching: false });
    render_();
    expect(screen.getByTestId('manuscript-results-empty').textContent).toContain('manuscript.noMatch');
  });

  // ── header actions ──────────────────────────────────────────────────────────
  it('Collapse-all and Reload header buttons call the hook actions', () => {
    const collapseAll = vi.fn();
    const reload = vi.fn();
    hook.value = base({ rows: [nodeRow(n('c1'))], collapseAll, reload });
    render_();
    fireEvent.click(screen.getByTestId('manuscript-collapse'));
    fireEvent.click(screen.getByTestId('manuscript-reload'));
    expect(collapseAll).toHaveBeenCalledOnce();
    expect(reload).toHaveBeenCalledOnce();
  });

  // The header button fires the handler it is GIVEN. That is all this component can honestly assert.
  //
  // ⚠ This test used to also assert `disabled === true` when no handler was passed, and called that
  // correct behaviour. It was the bug's accomplice: it injected its OWN `onNewChapter`, so it proved
  // the mechanism and could never prove the APP wires it. The real consumer (StudioSideBar) never
  // passed the prop, so the button was disabled 100% of the time in production while this stayed
  // green. Injecting a fake at the chokepoint cannot prove the chokepoint is wired — the wiring is
  // asserted in StudioSideBar.test.tsx, which mounts the CALLER.
  it('fires the handler it is given', () => {
    hook.value = base({ rows: [nodeRow(n('c1'))] });
    const onNewChapter = vi.fn();
    render(<ManuscriptNavigator bookId="b1" token="t" onNewChapter={onNewChapter} />);
    fireEvent.click(screen.getByTestId('manuscript-new'));
    expect(onNewChapter).toHaveBeenCalledOnce();
  });

  // ── visual data (mockup parity) ──────────────────────────────────────────────
  it('renders an arc as a roman numeral + its child-count badge', () => {
    hook.value = base({
      source: 'outline',
      rows: [nodeRow(n('arc1', 'arc', { childCount: 12 })), nodeRow(n('arc2', 'arc'))],
    });
    render_();
    // first arc → I, second → II (ordinal over the loaded list). `arc` is the i18n key.
    expect(screen.getByTestId('manuscript-row-arc1').textContent).toContain('arc I');
    expect(screen.getByTestId('manuscript-row-arc1').textContent).not.toContain('arc II');
    expect(screen.getByTestId('manuscript-row-arc2').textContent).toContain('arc II');
    expect(screen.getByTestId('manuscript-row-arc1').textContent).toContain('12'); // child badge
  });

  it('zero-pads a chapter number to 4 digits', () => {
    hook.value = base({ source: 'outline', rows: [nodeRow(n('c1', 'chapter', { number: 5 }))] });
    render_();
    expect(screen.getByTestId('manuscript-row-c1').textContent).toContain('0005');
  });

  it('renders shimmer skeleton rows and a window-position footer', () => {
    hook.value = base({ rows: [nodeRow(n('c1')), skeletonRow()], total: 10 });
    render_();
    expect(screen.getByTestId('manuscript-skeleton')).toBeTruthy();
    expect(screen.getByTestId('manuscript-window')).toBeTruthy();
  });

  // ── M3 (F2): the rail's own create-a-chapter door ───────────────────────────────────────────
  it('renders a "＋ Chapter" create button and fires onCreateChapter (flat book)', () => {
    const onCreateChapter = vi.fn();
    hook.value = base({ rows: [nodeRow(n('c1'))] }); // source 'chapters' by default
    render(<ManuscriptNavigator bookId="b1" token="t" onCreateChapter={onCreateChapter} />);
    fireEvent.click(screen.getByTestId('manuscript-chapter-new'));
    expect(onCreateChapter).toHaveBeenCalledOnce();
  });

  it('does NOT render the rail create button when no handler is wired', () => {
    hook.value = base({ rows: [nodeRow(n('c1'))] });
    render_();
    expect(screen.queryByTestId('manuscript-chapter-new')).toBeNull();
  });

  it('an empty book offers a "Start your first chapter" door that fires onCreateChapter', () => {
    const onCreateChapter = vi.fn();
    hook.value = base({ rows: [] });
    render(<ManuscriptNavigator bookId="b1" token="t" onCreateChapter={onCreateChapter} />);
    fireEvent.click(screen.getByTestId('manuscript-empty-create'));
    expect(onCreateChapter).toHaveBeenCalledOnce();
  });

  // ── M2 (F3): a cross-panel chapter mutation reloads the tree via the studio bus ──────────────
  it('reloads the tree when the studio bus signals a manuscript change — but NOT on mount', () => {
    const reload = vi.fn();
    hook.value = base({ rows: [nodeRow(n('c1'))], reload });
    // A tiny consumer that hands the test the host so it can publish the bus event.
    let publish: ((e: { type: 'manuscriptChanged' }) => void) | null = null;
    function Grab() { publish = useStudioHost().publish; return null; }
    render(
      <StudioHostProvider bookId="b1">
        <Grab />
        <ManuscriptNavigator bookId="b1" token="t" />
      </StudioHostProvider>,
    );
    expect(reload).not.toHaveBeenCalled(); // mount must not reload (the initial seq is 0)
    act(() => publish!({ type: 'manuscriptChanged' }));
    expect(reload).toHaveBeenCalledTimes(1); // the bump reloads exactly once
    act(() => publish!({ type: 'manuscriptChanged' }));
    expect(reload).toHaveBeenCalledTimes(2);
  });
});
