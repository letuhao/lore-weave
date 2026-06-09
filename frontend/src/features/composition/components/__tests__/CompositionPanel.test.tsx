import { useEffect } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompositionPanel } from '../CompositionPanel';

// Visibility-transition regression (CLAUDE.md "never conditionally unmount
// stateful components"): the sub-panels must stay MOUNTED across a tab switch —
// toggled with CSS `hidden`, not ternary-unmounted — so in-progress generation/
// edit state survives. We mock each sub-panel to (a) drop a stable testid and
// (b) bump a per-panel MOUNT counter on mount; a remount (the bug) would bump it.

const mounts = vi.hoisted(() => ({ compose: 0, assemble: 0, planner: 0, grounding: 0, canon: 0, quality: 0 }));

function mockPanel(name: keyof typeof mounts) {
  return function Mock() {
    useEffect(() => {
      mounts[name] += 1;
    }, []);
    return <div data-testid={`mock-${name}`}>{name}</div>;
  };
}

vi.mock('../ComposeView', () => ({ ComposeView: mockPanel('compose') }));
vi.mock('../ChapterAssembleView', () => ({ ChapterAssembleView: mockPanel('assemble') }));
vi.mock('../PlannerView', () => ({ PlannerView: mockPanel('planner') }));
vi.mock('../GroundingPanel', () => ({ GroundingPanel: mockPanel('grounding') }));
vi.mock('../CanonRulesPanel', () => ({ CanonRulesPanel: mockPanel('canon') }));
vi.mock('../QualityPanel', () => ({ QualityPanel: mockPanel('quality') }));

const work = { project_id: 'proj-1', book_id: 'b', settings: {} as Record<string, unknown> };
vi.mock('../../hooks/useWork', () => ({
  useWorkResolution: () => ({ data: { status: 'found', work }, isLoading: false }),
  useCreateWork: () => ({ mutate: vi.fn(), isPending: false }),
  useChapterScenes: () => ({ data: [{ id: 's1', title: 'Scene 1', status: 'done' }] }),
  useCreateScene: () => ({ mutate: vi.fn(), isPending: false }),
  useSetSceneStatus: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../../../ai-models/api', () => ({
  aiModelsApi: { listUserModels: vi.fn().mockResolvedValue({ items: [] }) },
}));

beforeEach(() => {
  mounts.compose = mounts.assemble = mounts.planner = mounts.grounding = mounts.canon = mounts.quality = 0;
});

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CompositionPanel bookId="b" chapterId="c" token="tok" onAccept={vi.fn()} />
    </QueryClientProvider>,
  );
}

const wrapperOf = (name: string) => screen.getByTestId(`mock-${name}`).parentElement;

describe('CompositionPanel sub-tab CSS-hidden (visibility-transition)', () => {
  it('mounts ALL six sub-panels (none ternary-unmounted), only the active one visible', () => {
    renderPanel();
    for (const name of ['compose', 'assemble', 'planner', 'grounding', 'canon', 'quality']) {
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
});
