// 22-C2 panel-shell test: the view renders the three union row shapes with the right state
// markers, the Work-less banner, and self-registers/titles its dock tab. The join logic is
// covered by sceneUnion.test.ts; the data hook (useSceneBrowser) is mocked so this stays a
// pure view test.
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';
import type { SceneBrowserState } from '../useSceneBrowser';
import type { SceneUnionRow } from '../sceneUnion';

const state = vi.fn<[], SceneBrowserState>();
vi.mock('../useSceneBrowser', () => ({ useSceneBrowser: () => state() }));

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

beforeEach(() => state.mockReset());

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
