import { useEffect } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompositionPanel } from '../CompositionPanel';
import { WorkspaceLayoutProvider } from '../../context/WorkspaceLayoutContext';

// Visibility-transition regression (CLAUDE.md "never conditionally unmount
// stateful components"): the sub-panels must stay MOUNTED across a tab switch —
// toggled with CSS `hidden`, not ternary-unmounted — so in-progress generation/
// edit state survives. We mock each sub-panel to (a) drop a stable testid and
// (b) bump a per-panel MOUNT counter on mount; a remount (the bug) would bump it.

const mounts = vi.hoisted(() => ({ compose: 0, cowriter: 0, assemble: 0, planner: 0, beats: 0, graph: 0, cast: 0, relmap: 0, timeline: 0, arc: 0, worldmap: 0, grounding: 0, references: 0, style: 0, canon: 0, critic: 0, progress: 0, quality: 0, flywheel: 0, settings: 0 }));

function mockPanel(name: keyof typeof mounts) {
  return function Mock() {
    useEffect(() => {
      mounts[name] += 1;
    }, []);
    return <div data-testid={`mock-${name}`}>{name}</div>;
  };
}

vi.mock('../ComposeView', () => ({ ComposeView: mockPanel('compose') }));
vi.mock('../CoWriterChat', () => ({ CoWriterChat: mockPanel('cowriter') }));
vi.mock('../ChapterAssembleView', () => ({ ChapterAssembleView: mockPanel('assemble') }));
vi.mock('../PlannerView', () => ({ PlannerView: mockPanel('planner') }));
vi.mock('../BeatSheetView', () => ({ BeatSheetView: mockPanel('beats') }));
vi.mock('../SceneGraphCanvas', () => ({ SceneGraphCanvas: mockPanel('graph') }));
vi.mock('../CastCodexPanel', () => ({ CastCodexPanel: mockPanel('cast') }));
vi.mock('../RelationshipMap', () => ({ RelationshipMap: mockPanel('relmap') }));
vi.mock('../TimelineView', () => ({ TimelineView: mockPanel('timeline') }));
vi.mock('../CharacterArcView', () => ({ CharacterArcView: mockPanel('arc') }));
vi.mock('../WorldMap', () => ({ WorldMap: mockPanel('worldmap') }));
vi.mock('../GroundingPanel', () => ({ GroundingPanel: mockPanel('grounding') }));
vi.mock('../ReferencesPanel', () => ({ ReferencesPanel: mockPanel('references') }));
vi.mock('../StyleVoicePanel', () => ({ StyleVoicePanel: mockPanel('style') }));
vi.mock('../CanonRulesPanel', () => ({ CanonRulesPanel: mockPanel('canon') }));
vi.mock('../CriticPanel', () => ({ CriticPanel: mockPanel('critic') }));
vi.mock('../ProgressPanel', () => ({ ProgressPanel: mockPanel('progress') }));
vi.mock('../QualityPanel', () => ({ QualityPanel: mockPanel('quality') }));
vi.mock('../FlywheelPanel', () => ({ FlywheelPanel: mockPanel('flywheel') }));
vi.mock('../CompositionSettingsView', () => ({ CompositionSettingsView: mockPanel('settings') }));

const work = { project_id: 'proj-1', book_id: 'b', settings: {} as Record<string, unknown> };
// Controllable resolution state — lets a test reproduce the pop-out's COLD-cache path
// (isLoading:true first render → resolved next render), which exposed the rules-of-hooks
// crash (a hook below the `if (resolution.isLoading) return`). Defaults to resolved.
const wr = vi.hoisted(() => ({ loading: false }));
vi.mock('../../hooks/useWork', () => ({
  useWorkResolution: () => (wr.loading ? { data: undefined, isLoading: true } : { data: { status: 'found', work }, isLoading: false }),
  useCreateWork: () => ({ mutate: vi.fn(), isPending: false }),
  useChapterScenes: () => ({ data: [{ id: 's1', title: 'Scene 1', status: 'done' }] }),
  useCreateScene: () => ({ mutate: vi.fn(), isPending: false }),
  useSetSceneStatus: () => ({ mutate: vi.fn(), isPending: false }),
  usePendingWorkResolver: () => ({ state: 'idle', start: vi.fn(), retry: vi.fn() }),
}));
// W5 — the shared ModelPicker also imports getUserModelMeta from this module, so
// the mock must spread the real module (an object literal would break it).
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: { listUserModels: vi.fn().mockResolvedValue({ items: [] }), patchFavorite: vi.fn() },
  };
});
// W5 — the shared useUserModels/ModelPicker read the token from useAuth.
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

import { invalidateUserModelsCache } from '@/components/model-picker';

beforeEach(() => {
  invalidateUserModelsCache();  // W5 — the module-level fetch cache must not leak across tests
  localStorage.clear();   // T5.4 — the dock flag/layout must not leak across tests
  wr.loading = false;     // default resolved; the cold-cache test flips this
  mounts.compose = mounts.cowriter = mounts.assemble = mounts.planner = mounts.beats = mounts.graph = mounts.cast = mounts.relmap = mounts.timeline = mounts.arc = mounts.worldmap = mounts.grounding = mounts.references = mounts.style = mounts.canon = mounts.critic = mounts.progress = mounts.quality = mounts.flywheel = mounts.settings = 0;
});

function renderPanel(initialEntries: string[] = ['/books/b']) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <CompositionPanel bookId="b" chapterId="c" token="tok" onAccept={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// T5.4 M2 — render with the windowing flag ON (a WorkspaceLayoutProvider + the
// localStorage flag set), so CompositionPanel shows the DockRail instead of the
// fixed strip. ComposeView etc. are mocked above, so no LiveStateProvider is needed.
function renderDockPanel() {
  localStorage.setItem('loom.workspace.enabled', 'true');
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/books/b']}>
        <WorkspaceLayoutProvider>
          <CompositionPanel bookId="b" chapterId="c" token="tok" onAccept={vi.fn()} />
        </WorkspaceLayoutProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const wrapperOf = (name: string) => screen.getByTestId(`mock-${name}`).parentElement;

describe('CompositionPanel sub-tab CSS-hidden (visibility-transition)', () => {
  it('mounts ALL nineteen sub-panels (none ternary-unmounted), only the active one visible', () => {
    renderPanel();
    for (const name of ['compose', 'cowriter', 'assemble', 'planner', 'beats', 'graph', 'cast', 'relmap', 'timeline', 'arc', 'worldmap', 'grounding', 'references', 'style', 'canon', 'progress', 'quality', 'flywheel', 'settings']) {
      expect(screen.getByTestId(`mock-${name}`)).toBeInTheDocument();
    }
    // compose is the default tab → visible; the rest (incl. planner) carry `hidden`.
    expect(wrapperOf('compose')).not.toHaveClass('hidden');
    expect(wrapperOf('assemble')).toHaveClass('hidden');
    expect(wrapperOf('planner')).toHaveClass('hidden');
    expect(wrapperOf('grounding')).toHaveClass('hidden');
  });

  it('the Planner tab stays mounted across a tab round-trip (a half-edited plan survives)', () => {
    renderPanel();
    expect(mounts.planner).toBe(1); // mounted once, hidden
    fireEvent.click(screen.getByTestId('composition-subtab-planner'));
    expect(wrapperOf('planner')).not.toHaveClass('hidden');
    fireEvent.click(screen.getByTestId('composition-subtab-compose'));
    // planner stayed in the DOM (a ternary-unmount would have dropped its draft).
    expect(screen.getByTestId('mock-planner')).toBeInTheDocument();
    expect(mounts.planner).toBe(1);
  });

  it('a tab round-trip toggles visibility WITHOUT remounting (state survives)', () => {
    renderPanel();
    expect(mounts.compose).toBe(1);
    expect(mounts.assemble).toBe(1); // already mounted, just hidden

    fireEvent.click(screen.getByTestId('composition-subtab-assemble'));
    expect(wrapperOf('assemble')).not.toHaveClass('hidden');
    expect(wrapperOf('compose')).toHaveClass('hidden');
    // compose stayed mounted (still in the DOM) — the actual invariant.
    expect(screen.getByTestId('mock-compose')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('composition-subtab-compose'));
    expect(wrapperOf('compose')).not.toHaveClass('hidden');
    // round-trip did NOT remount either panel (a ternary would have).
    expect(mounts.compose).toBe(1);
    expect(mounts.assemble).toBe(1);
  });

  it('the Power-view button opens the full-screen overlay and Back-to-editor closes it (T5.5)', () => {
    renderPanel();
    expect(screen.queryByTestId('power-view-overlay')).toBeNull(); // closed by default
    fireEvent.click(screen.getByTestId('composition-power-view-btn'));
    // overlay portals to document.body; screen queries the whole document
    expect(screen.getByTestId('power-view-overlay')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('power-view-close'));
    expect(screen.queryByTestId('power-view-overlay')).toBeNull(); // unmounted (fresh-each-open)
  });
});

// Overflow-containment regression: in a narrow (resizable) right panel the 16-tab
// strip and the tab content must stay INSIDE the panel — the strip scrolls
// horizontally (no-shrink tabs) and content wraps/scrolls, never escaping the
// viewport. We assert the structural classes that enforce this.
describe('CompositionPanel overflow containment (narrow right panel)', () => {
  it('the tab strip scrolls horizontally with non-shrinking tabs', () => {
    renderPanel();
    const strip = screen.getByTestId('composition-subtabs');
    expect(strip).toHaveClass('overflow-x-auto');
    // each tab refuses to shrink so labels stay readable; the row scrolls instead.
    const tab = screen.getByTestId('composition-subtab-settings');
    expect(tab).toHaveClass('shrink-0');
    expect(tab).toHaveClass('whitespace-nowrap');
  });

  it('the content wrapper contains wide content (min-w-0 + overflow + wrap)', () => {
    renderPanel();
    const content = screen.getByTestId('composition-content');
    expect(content).toHaveClass('min-w-0');
    expect(content).toHaveClass('overflow-auto');
    expect(content.className).toContain('[overflow-wrap:anywhere]');
  });
});

// T5.4 M2 — with the windowing flag ON, the fixed strip is replaced by the DockRail
// but every panel stays MOUNTED (the no-remount invariant must survive the swap), and
// the active panel is driven by the per-device layout.
describe('CompositionPanel dock mode (T5.4 M2)', () => {
  it('renders the DockRail instead of the fixed strip, with all panels still mounted', () => {
    renderDockPanel();
    expect(screen.getByTestId('composition-dock-rail')).toBeInTheDocument();
    expect(screen.queryByTestId('composition-subtabs')).toBeNull();   // fixed strip replaced
    // every sub-panel is still mounted (CSS-hidden), exactly like the fixed-strip mode
    for (const name of ['compose', 'cast', 'grounding', 'references', 'settings']) {
      expect(screen.getByTestId(`mock-${name}`)).toBeInTheDocument();
    }
    expect(wrapperOf('compose')).not.toHaveClass('hidden');   // layout default active = compose
  });

  it('clicking a dock tab changes the active panel WITHOUT remounting (state survives)', () => {
    renderDockPanel();
    expect(mounts.cast).toBe(1);
    fireEvent.click(screen.getByTestId('dock-select-cast'));
    expect(wrapperOf('cast')).not.toHaveClass('hidden');
    expect(wrapperOf('compose')).toHaveClass('hidden');
    fireEvent.click(screen.getByTestId('dock-select-compose'));
    expect(wrapperOf('compose')).not.toHaveClass('hidden');
    expect(mounts.cast).toBe(1);            // never remounted across the switch
    expect(mounts.compose).toBe(1);
  });

  it('clamps a persisted active that is gated-out (threads disabled) so the pane is never blank (/review-impl MED)', () => {
    // a layout that was saved with active='threads' while it was enabled; the test
    // Work has no narrative_thread_enabled → threads is gated out of the dock now.
    localStorage.setItem('loom.workspace.enabled', 'true');
    localStorage.setItem('loom.workspace.layout', JSON.stringify({
      version: 1, active: 'threads',
      panels: { compose: { placement: 'dock', order: 0 }, threads: { placement: 'dock', order: 15 } },
    }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/books/b']}>
          <WorkspaceLayoutProvider>
            <CompositionPanel bookId="b" chapterId="c" token="tok" onAccept={vi.fn()} />
          </WorkspaceLayoutProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // active clamps to the first VISIBLE panel (compose) — the content pane shows it,
    // not a blank (the threads div is gated off, so active='threads' would render nothing)
    expect(wrapperOf('compose')).not.toHaveClass('hidden');
    expect(screen.queryByTestId('dock-tab-threads')).toBeNull();
  });

  it('hiding the active panel drops its tab and refocuses another (content never blank)', () => {
    renderDockPanel();
    fireEvent.click(screen.getByTestId('dock-hide-compose'));   // hide the active panel
    expect(screen.queryByTestId('dock-tab-compose')).toBeNull(); // gone from the rail
    expect(screen.getByTestId('mock-compose')).toBeInTheDocument(); // but still MOUNTED
    // another panel became active (the content pane isn't blank)
    expect(wrapperOf('compose')).toHaveClass('hidden');
  });

  it('floating a panel re-parents it into a window and removes its dock tab; docking restores it (M3)', () => {
    renderDockPanel();
    expect(screen.getByTestId('dock-tab-cast')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('dock-float-cast'));
    // the panel left the rail and now lives in a floating window (content re-parented,
    // not duplicated — still exactly one mock-cast in the tree)
    expect(screen.queryByTestId('dock-tab-cast')).toBeNull();
    expect(screen.getByTestId('floating-window')).toBeInTheDocument();
    expect(screen.getAllByTestId('mock-cast')).toHaveLength(1);
    // dock it back → window closes, rail tab returns
    fireEvent.click(screen.getByTestId('floating-window-dock'));
    expect(screen.queryByTestId('floating-window')).toBeNull();
    expect(screen.getByTestId('dock-tab-cast')).toBeInTheDocument();
  });

  it('floating the ACTIVE panel advances dock focus so the content pane is not blank (M3)', () => {
    renderDockPanel();   // compose is active by default
    fireEvent.click(screen.getByTestId('dock-float-compose'));
    expect(screen.queryByTestId('dock-tab-compose')).toBeNull();      // compose floated out of the rail
    expect(screen.getByTestId('floating-window')).toBeInTheDocument();
    // the next docked panel (cowriter, order 1) is now active — the pane isn't blank
    expect(wrapperOf('cowriter')).not.toHaveClass('hidden');
  });
});

describe('CompositionPanel solo / OS pop-out mode (T5.4 M4)', () => {
  function renderSolo(panel: string) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/books/b']}>
          <CompositionPanel bookId="b" chapterId="c" token="tok" onAccept={vi.fn()} soloPanel={panel as never} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('solo mode renders ONLY the one panel — no rail, no other panels mounted', () => {
    renderSolo('cast');
    expect(screen.getByTestId('mock-cast')).toBeInTheDocument();
    expect(wrapperOf('cast')).not.toHaveClass('hidden');         // the solo panel is visible
    expect(screen.queryByTestId('composition-dock-rail')).toBeNull();
    expect(screen.queryByTestId('composition-subtabs')).toBeNull();
    // the other panels are NOT mounted in the popout (only the solo one)
    expect(screen.queryByTestId('mock-compose')).toBeNull();
    expect(screen.queryByTestId('mock-grounding')).toBeNull();
  });

  it('D-S1-COMPOSE-ASSEMBLE-VISUAL-SAMENESS: the what-if promote chrome is HIDDEN in the assemble solo panel but PRESENT in scene-compose', () => {
    // chapter-assemble stitches DONE scenes — what-if exploration is a scene-drafting concern, so
    // its promote row is dropped there, which also distinguishes it from the near-identical scene-compose.
    renderSolo('assemble');
    expect(screen.queryByTestId('composition-whatif-promote')).toBeNull();

    renderSolo('compose');
    expect(screen.getByTestId('composition-whatif-promote')).toBeInTheDocument();
  });

  it('survives a cold-cache loading→resolved transition (the pop-out path) without a rules-of-hooks crash', async () => {
    // Live-smoke caught this: the pop-out is a SEPARATE React root with a COLD react-query
    // cache, so useWorkResolution is isLoading on first render (early return → fewer hooks),
    // then resolves (full render → the hooks below the return). With acceptProse/ws NOT
    // hoisted this threw "rendered more hooks". The opener masked it (its cache is warm).
    wr.loading = true;
    localStorage.setItem('loom.workspace.enabled', 'true');
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const ui = (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/books/b']}>
          <WorkspaceLayoutProvider>
            <CompositionPanel bookId="b" chapterId="c" token="tok" onAccept={vi.fn()} />
          </WorkspaceLayoutProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
    const { rerender } = render(ui);                 // loading render (Hint, fewer hooks pre-fix)
    expect(screen.queryByTestId('mock-compose')).toBeNull();
    wr.loading = false;
    expect(() => rerender(ui)).not.toThrow();         // resolved render — pre-fix this crashed
    expect(await screen.findByTestId('mock-compose')).toBeInTheDocument();
  });

  it('popping a panel out opens an OS window and unmounts it from the opener (M4)', () => {
    const win = { closed: false, close: vi.fn() } as unknown as Window;
    const open = vi.spyOn(window, 'open').mockReturnValue(win);
    renderDockPanel();
    expect(screen.getByTestId('mock-cast')).toBeInTheDocument();   // mounted while docked
    fireEvent.click(screen.getByTestId('dock-popout-cast'));
    // a real OS window opened for the popped panel…
    expect(open).toHaveBeenCalledTimes(1);
    expect(String(open.mock.calls[0][0])).toContain('panel=cast');
    // …and the panel left BOTH the rail and the opener content area (it lives in the window)
    expect(screen.queryByTestId('dock-tab-cast')).toBeNull();
    expect(screen.queryByTestId('mock-cast')).toBeNull();
    open.mockRestore();
  });
});
