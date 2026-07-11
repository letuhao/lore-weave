// 22-C2 panel-shell test: the view renders the three union row shapes with the right state
// markers, the Work-less banner, and self-registers/titles its dock tab. The join logic is
// covered by sceneUnion.test.ts; the data hook (useSceneBrowser) is mocked so this stays a
// pure view test.
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';
import type { SceneBrowserState } from '../useSceneBrowser';
import type { SceneUnionRow } from '../sceneUnion';

const state = vi.fn<[], SceneBrowserState>();
vi.mock('../useSceneBrowser', () => ({ useSceneBrowser: () => state() }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
// interpolate {{n}} in the defaultValue so the bulk-result string renders concrete numbers.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, o?: { defaultValue?: string } & Record<string, unknown>) =>
      (o?.defaultValue ?? _k).replace(/\{\{(\w+)\}\}/g, (_m, key) => String(o?.[key] ?? '')),
  }),
}));
// 26 IX-14 — the panel also reads conformance; mock it (default: nothing dirty).
const dirtyChapters = { current: new Set<string>() };
vi.mock('../useConformanceStatus', () => ({
  useConformanceStatus: () => ({
    status: null, dirtyChapters: dirtyChapters.current, staleChapterCount: 0,
    loading: false, error: null, refresh: vi.fn(),
  }),
}));
// 22-C2b — the panel drives the bulk controller; mock it so the view wiring is asserted in isolation
// (the real selection + partial-failure logic is covered by useSceneBulk.test).
const bulk = {
  selected: new Set<string>(), busy: false, result: null as null | { ok: number; conflicts: number; failed: number },
  toggle: vi.fn(), setMany: vi.fn(), clear: vi.fn(), apply: vi.fn(), trash: vi.fn(),
};
vi.mock('../useSceneBulk', () => ({ useSceneBulk: () => bulk }));

import { SceneBrowserPanel } from '../SceneBrowserPanel';

const row = (o: Partial<SceneUnionRow>): SceneUnionRow => ({
  shape: 'linked', key: 'k', index: null, spec: null, chapterId: 'c', sortOrder: 0, anchorLost: false, ...o,
});
const baseState = (o: Partial<SceneBrowserState>): SceneBrowserState => ({
  rows: [], loading: false, ready: true, error: null, intentUnavailable: false,
  workless: false, projectId: 'p', total: 0, hasMore: false, query: '',
  setQuery: vi.fn(), loadMore: vi.fn(), reload: vi.fn(), ...o,
});

function dockProps() { return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps; }
function withHost(ui: ReactNode) { return render(<StudioHostProvider bookId="book-1">{ui}</StudioHostProvider>); }

beforeEach(() => {
  state.mockReset(); dirtyChapters.current = new Set();
  bulk.selected = new Set(); bulk.busy = false; bulk.result = null;
  bulk.toggle.mockReset(); bulk.setMany.mockReset(); bulk.clear.mockReset(); bulk.apply.mockReset(); bulk.trash.mockReset();
});

describe('SceneBrowserPanel (22-C2)', () => {
  it('renders the three union shapes with distinct state badges', () => {
    state.mockReturnValue(baseState({
      rows: [
        row({ key: 'lk', shape: 'linked', spec: { status: 'drafting', tension: 60, target_words: 900, title: 'Written' } as SceneUnionRow['spec'] }),
        row({ key: 'so', shape: 'spec_only', spec: { status: 'outline', title: 'Planned' } as SceneUnionRow['spec'] }),
        row({ key: 'io', shape: 'index_only', index: { title: 'Prose' } as SceneUnionRow['index'] }),
      ],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    const rows = screen.getAllByTestId('scene-browser-row');
    expect(rows.map((r) => r.getAttribute('data-shape'))).toEqual(['linked', 'spec_only', 'index_only']);
    expect(screen.getByTestId('scene-badge-spec-only')).toBeInTheDocument();
    expect(screen.getByTestId('scene-badge-index-only')).toBeInTheDocument();
    // the linked row shows its intent (status/tension), the index_only row greys it to em-dash
    expect(screen.getByText('Drafting')).toBeInTheDocument();
  });

  it('flags an anchor-lost index_only row distinctly from not-planned', () => {
    state.mockReturnValue(baseState({
      rows: [row({ key: 'io', shape: 'index_only', anchorLost: true, index: { title: 'Orphan' } as SceneUnionRow['index'] })],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-browser-anchor-lost')).toBeInTheDocument();
  });

  it('shows the Work-less banner when there is no plan', () => {
    state.mockReturnValue(baseState({ workless: true, rows: [row({ shape: 'index_only' })] }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-browser-workless')).toBeInTheDocument();
  });

  it('renders an empty state and a load-more control when applicable', () => {
    state.mockReturnValue(baseState({ rows: [], hasMore: false }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-browser-empty')).toBeInTheDocument();

    state.mockReturnValue(baseState({ rows: [row({})], hasMore: true }));
    const { getByTestId } = withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(getByTestId('scene-browser-load-more')).toBeInTheDocument();
  });

  it('shows a loading state (not the empty state) until ready, then the empty state', () => {
    // Review MED: "No scenes match" must NOT flash while Work resolution is still settling.
    state.mockReturnValue(baseState({ ready: false, rows: [] }));
    const { rerender, queryByTestId, getByTestId } = withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(getByTestId('scene-browser-loading')).toBeInTheDocument();
    expect(queryByTestId('scene-browser-empty')).toBeNull();

    state.mockReturnValue(baseState({ ready: true, rows: [] }));
    rerender(<StudioHostProvider bookId="book-1"><SceneBrowserPanel {...dockProps()} /></StudioHostProvider>);
    expect(getByTestId('scene-browser-empty')).toBeInTheDocument();
  });

  it('shows the soft intent-unavailable note (identity rows still render) when composition is down', () => {
    state.mockReturnValue(baseState({
      intentUnavailable: true,
      rows: [row({ shape: 'index_only', index: { title: 'Prose' } as SceneUnionRow['index'] })],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-browser-intent-unavailable')).toBeInTheDocument();
    expect(screen.getByTestId('scene-browser-row')).toBeInTheDocument(); // identity row survives
  });

  it('26-F: an amber "canon moved" chip renders only on rows whose chapter is dirty', () => {
    dirtyChapters.current = new Set(['ch-stale']);
    state.mockReturnValue(baseState({
      rows: [
        row({ key: 'a', shape: 'linked', chapterId: 'ch-stale', spec: { id: 'n1' } as SceneUnionRow['spec'] }),
        row({ key: 'b', shape: 'linked', chapterId: 'ch-fresh', spec: { id: 'n2' } as SceneUnionRow['spec'] }),
      ],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getAllByTestId('scene-browser-dirty')).toHaveLength(1); // only the stale-chapter row
  });

  it('22-C2b: a checkbox renders only on spec-backed rows, and toggling it selects the spec node', () => {
    state.mockReturnValue(baseState({
      rows: [
        row({ key: 'lk', shape: 'linked', spec: { id: 'n1', version: 2, status: 'drafting' } as SceneUnionRow['spec'] }),
        row({ key: 'io', shape: 'index_only', index: { title: 'Prose' } as SceneUnionRow['index'] }),
      ],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-browser-select-n1')).toBeInTheDocument();
    expect(screen.queryByTestId('scene-browser-select-undefined')).toBeNull(); // index_only has no checkbox
    fireEvent.click(screen.getByTestId('scene-browser-select-n1'));
    expect(bulk.toggle).toHaveBeenCalledWith('n1');
  });

  it('22-C2b: select-all toggles every spec-backed row (index_only excluded)', () => {
    state.mockReturnValue(baseState({
      rows: [
        row({ key: 'a', shape: 'linked', spec: { id: 'n1', version: 1 } as SceneUnionRow['spec'] }),
        row({ key: 'b', shape: 'spec_only', spec: { id: 'n2', version: 1, status: 'outline' } as SceneUnionRow['spec'] }),
        row({ key: 'c', shape: 'index_only', index: { title: 'x' } as SceneUnionRow['index'] }),
      ],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    fireEvent.click(screen.getByTestId('scene-browser-select-all'));
    expect(bulk.setMany).toHaveBeenCalledWith(['n1', 'n2'], true);
  });

  it('22-C2b: the bulk bar appears only when rows are selected; status applies to the selected targets', () => {
    bulk.selected = new Set(['n1']);
    state.mockReturnValue(baseState({
      rows: [row({ key: 'a', shape: 'linked', chapterId: 'c', sortOrder: 0, spec: { id: 'n1', version: 5, status: 'drafting' } as SceneUnionRow['spec'] })],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-browser-bulkbar')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('scene-browser-bulk-status'), { target: { value: 'done' } });
    expect(bulk.apply).toHaveBeenCalledWith([{ id: 'n1', version: 5 }], { status: 'done' });
    fireEvent.click(screen.getByTestId('scene-browser-bulk-trash'));
    expect(bulk.trash).toHaveBeenCalledWith([{ id: 'n1', version: 5 }]);

    // retarget words commits a positive integer on blur; blank/non-positive is ignored.
    const words = screen.getByTestId('scene-browser-bulk-words');
    fireEvent.blur(words, { target: { value: '' } });
    expect(bulk.apply).not.toHaveBeenCalledWith([{ id: 'n1', version: 5 }], { target_words: expect.anything() });
    fireEvent.blur(words, { target: { value: '1200' } });
    expect(bulk.apply).toHaveBeenCalledWith([{ id: 'n1', version: 5 }], { target_words: 1200 });
  });

  it('22-C2b: the bar counts only ACTIONABLE (visible+selected) targets, not off-screen selections', () => {
    // n2 is selected but filtered out of view; the bar should count only the visible selected n1.
    bulk.selected = new Set(['n1', 'n2']);
    state.mockReturnValue(baseState({
      rows: [row({ key: 'a', shape: 'linked', spec: { id: 'n1', version: 1 } as SceneUnionRow['spec'] })],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-browser-bulk-count').textContent).toMatch(/1 selected/);
    fireEvent.change(screen.getByTestId('scene-browser-bulk-status'), { target: { value: 'done' } });
    expect(bulk.apply).toHaveBeenCalledWith([{ id: 'n1', version: 1 }], { status: 'done' }); // only the visible one
  });

  it('22-C2b: a fractional target-words value (rounds to 0) is ignored, never zeroing scenes', () => {
    bulk.selected = new Set(['n1']);
    state.mockReturnValue(baseState({ rows: [row({ key: 'a', shape: 'linked', spec: { id: 'n1', version: 1 } as SceneUnionRow['spec'] })] }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    fireEvent.blur(screen.getByTestId('scene-browser-bulk-words'), { target: { value: '0.3' } });
    expect(bulk.apply).not.toHaveBeenCalled(); // 0.3 → round 0 → ignored (would have zeroed target_words)
    fireEvent.blur(screen.getByTestId('scene-browser-bulk-words'), { target: { value: '1200' } });
    expect(bulk.apply).toHaveBeenCalledWith([{ id: 'n1', version: 1 }], { target_words: 1200 });
  });

  it('22-C2b: the partial-failure result stays visible AFTER a run, when the selection is cleared', () => {
    // review HIGH: runBulk sets result AND clears the selection in one commit. The tally must NOT
    // be gated on the (now empty) selection — it renders as its own banner. Drives the REAL
    // post-apply state (selected empty, result set), not the impossible selected+result pairing.
    bulk.selected = new Set(); bulk.result = { ok: 3, conflicts: 1, failed: 0 };
    state.mockReturnValue(baseState({ rows: [row({ key: 'a', shape: 'linked', spec: { id: 'n1', version: 1 } as SceneUnionRow['spec'] })] }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.queryByTestId('scene-browser-bulkbar')).toBeNull(); // selection cleared → no action bar
    expect(screen.getByTestId('scene-browser-bulk-result').textContent).toMatch(/3 updated.*1 conflicted/); // but the tally shows
  });

  it('22-C2b: the result banner is absent when there is no result (no stray banner)', () => {
    state.mockReturnValue(baseState({ rows: [row({ key: 'a', shape: 'linked', spec: { id: 'n1', version: 1 } as SceneUnionRow['spec'] })] }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.queryByTestId('scene-browser-bulk-result')).toBeNull();
  });

  it('22-C2b: a per-row select checkbox is labelled with its scene title (a11y)', () => {
    state.mockReturnValue(baseState({
      rows: [row({ key: 'a', shape: 'linked', spec: { id: 'n1', version: 1, title: 'The Duel' } as SceneUnionRow['spec'] })],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    expect(screen.getByTestId('scene-browser-select-n1').getAttribute('aria-label')).toMatch(/The Duel/);
  });

  it('22-C3: a spec-backed row is clickable-to-inspect; an index_only row is not', () => {
    // The publish/openPanel effect is GUI glue verified live in the browser smoke; here we pin the
    // affordance: only rows with a spec node carry the cursor + a click handler.
    state.mockReturnValue(baseState({
      rows: [
        row({ key: 'lk', shape: 'linked', spec: { id: 'node-9', status: 'drafting' } as SceneUnionRow['spec'] }),
        row({ key: 'io', shape: 'index_only', index: { title: 'Prose' } as SceneUnionRow['index'] }),
      ],
    }));
    withHost(<SceneBrowserPanel {...dockProps()} />);
    const rows = screen.getAllByTestId('scene-browser-row');
    expect(rows[0].className).toContain('cursor-pointer');  // spec-backed → inspectable
    expect(rows[1].className).not.toContain('cursor-pointer'); // index_only → not
  });
});
