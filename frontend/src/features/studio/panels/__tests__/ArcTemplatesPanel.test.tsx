// 34 arc-templates panel — operable: browse (tier filter), the CRUD the library was missing
// (New/Adopt/Archive), and open a template's detail. Driven by a mock controller + stubbed motif
// components so the panel is tested in isolation from react-query/the timeline grid.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

const ctrl = vi.hoisted(() => ({ useArcTemplates: vi.fn() }));
const cat = vi.hoisted(() => ({ listCatalog: vi.fn(), getArcTemplateDrift: vi.fn() }));
const ph = vi.hoisted(() => ({ getArcs: vi.fn() }));
vi.mock('../useArcTemplates', () => ({ useArcTemplates: ctrl.useArcTemplates }));
vi.mock('../useStudioPanel', () => ({ useStudioPanel: () => {} }));
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => ({ bookId: 'b' }) }));
vi.mock('@/features/composition/motif/components/ArcTimelineEditor', () => ({ ArcTimelineEditor: () => <div data-testid="arc-timeline-stub" /> }));
vi.mock('@/features/composition/motif/components/ArcApplyPreview', () => ({ ArcApplyPreview: (p: { projectId: string | null }) => <div data-testid="arc-apply-stub" data-project={p.projectId ?? ''} /> }));
vi.mock('@/features/composition/arcImport/ImportDeconstructSection', () => ({ ImportDeconstructSection: () => <div data-testid="deconstruct-stub" /> }));
vi.mock('@/features/composition/arcTemplates/api', () => ({ listCatalog: cat.listCatalog, getArcTemplateDrift: cat.getArcTemplateDrift }));
vi.mock('@/features/plan-hub/api', () => ({ getArcs: ph.getArcs }));

function qcWrap({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

import { ArcTemplatesPanel } from '../ArcTemplatesPanel';
import type { ArcTemplatesState } from '../useArcTemplates';
import type { IDockviewPanelProps } from 'dockview-react';

const MINE = { id: 'a1', code: 'c1', name: 'My Arc', owner_user_id: 'me', chapter_span: 12, genre_tags: ['xianxia'] };
const SYS = { id: 'a2', code: 'c2', name: 'Hero Journey', owner_user_id: null, chapter_span: 8, genre_tags: [] };

function makeState(over: Partial<ArcTemplatesState> = {}): ArcTemplatesState {
  return {
    token: 'tok', projectId: 'proj1', bookId: 'b', templates: [MINE, SYS] as never, truncated: false, totalInTier: 2,
    loading: false, isError: false,
    refetch: vi.fn(), tier: 'all', setTier: vi.fn(), selected: null, select: vi.fn(), meId: 'me',
    tierOf: (a) => (a.owner_user_id === null ? 'system' : a.owner_user_id === 'me' ? 'mine' : 'public'),
    busy: false, actionError: null, create: vi.fn().mockResolvedValue(undefined),
    adopt: vi.fn().mockResolvedValue(undefined), archive: vi.fn().mockResolvedValue(undefined),
    restore: vi.fn().mockResolvedValue(undefined), ...over,
  } as ArcTemplatesState;
}

const props = {} as IDockviewPanelProps;
beforeEach(() => ctrl.useArcTemplates.mockReset());

describe('ArcTemplatesPanel', () => {
  it('lists templates with tier chips + the right action per tier (archive mine, adopt others)', () => {
    ctrl.useArcTemplates.mockReturnValue(makeState());
    render(<ArcTemplatesPanel {...props} />);
    expect(screen.getByTestId('arc-row-a1')).toBeInTheDocument();
    expect(screen.getByTestId('arc-tier-chip-a1').textContent).toBe('motif.arc.templates.chipMine');
    expect(screen.getByTestId('arc-archive-a1')).toBeInTheDocument();   // own → archive
    expect(screen.getByTestId('arc-tier-chip-a2').textContent).toBe('motif.arc.templates.chipSystem');
    expect(screen.getByTestId('arc-adopt-a2')).toBeInTheDocument();     // not-own → adopt
  });

  it('New → create form → submit calls create (the CRUD the library was missing)', async () => {
    const state = makeState();
    ctrl.useArcTemplates.mockReturnValue(state);
    render(<ArcTemplatesPanel {...props} />);
    fireEvent.click(screen.getByTestId('arc-new'));
    fireEvent.change(screen.getByTestId('arc-create-code'), { target: { value: 'newcode' } });
    fireEvent.change(screen.getByTestId('arc-create-name'), { target: { value: 'New Arc' } });
    fireEvent.click(screen.getByTestId('arc-create-submit'));
    await waitFor(() => expect(state.create).toHaveBeenCalledWith({ code: 'newcode', name: 'New Arc', shareToBook: false }));
  });

  it('34a: the Book tier + a share-to-book create (the collaboration tier)', async () => {
    const state = makeState({ tier: 'book' });
    ctrl.useArcTemplates.mockReturnValue(state);
    render(<ArcTemplatesPanel {...props} />);
    expect(screen.getByTestId('arc-tier-book')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('arc-new'));
    // in the Book tier the share checkbox defaults ON → create targets the book's shared tier
    fireEvent.change(screen.getByTestId('arc-create-code'), { target: { value: 'shared' } });
    fireEvent.change(screen.getByTestId('arc-create-name'), { target: { value: 'Shared Arc' } });
    fireEvent.click(screen.getByTestId('arc-create-submit'));
    await waitFor(() => expect(state.create).toHaveBeenCalledWith({ code: 'shared', name: 'Shared Arc', shareToBook: true }));
  });

  it('S-08: the Archived tier shows a Restore action (not archive/adopt) that fires restore', () => {
    // In the Archived view every row is a soft-deleted own-row → the ONLY action is Restore. This
    // is the affordance that makes archived arcs a non-dead-end (before S-08 they were unreachable).
    const state = makeState({ tier: 'archived', templates: [MINE] as never });
    ctrl.useArcTemplates.mockReturnValue(state);
    render(<ArcTemplatesPanel {...props} />);
    expect(screen.getByTestId('arc-tier-archived')).toBeInTheDocument();   // the tab exists
    expect(screen.queryByTestId('arc-archive-a1')).toBeNull();             // no archive in archived view
    expect(screen.queryByTestId('arc-adopt-a1')).toBeNull();
    fireEvent.click(screen.getByTestId('arc-restore-a1'));
    expect(state.restore).toHaveBeenCalledWith('a1');
  });

  it('adopt/archive fire the controller actions', () => {
    const state = makeState();
    ctrl.useArcTemplates.mockReturnValue(state);
    render(<ArcTemplatesPanel {...props} />);
    fireEvent.click(screen.getByTestId('arc-adopt-a2'));
    expect(state.adopt).toHaveBeenCalledWith('a2');
    fireEvent.click(screen.getByTestId('arc-archive-a1'));
    expect(state.archive).toHaveBeenCalledWith('a1');
  });

  it('selecting a template opens the detail (timeline + apply-preview with the Work projectId)', async () => {
    ph.getArcs.mockResolvedValue({ arcs: [] });
    ctrl.useArcTemplates.mockReturnValue(makeState({ selected: MINE as never }));
    render(<ArcTemplatesPanel {...props} />, { wrapper: qcWrap });
    expect(screen.getByTestId('arc-template-detail')).toBeInTheDocument();
    expect(screen.getByTestId('arc-timeline-stub')).toBeInTheDocument();
    expect(screen.getByTestId('arc-apply-stub')).toHaveAttribute('data-project', 'proj1');
    // Drift: no arc uses this template yet → the honest "not applied" empty (not a blank).
    await waitFor(() => expect(screen.getByTestId('arc-drift-unapplied')).toBeInTheDocument());
  });

  it('34 §Drift: a materialized arc renders the STRUCTURED drift view (real ArcConformance shape)', async () => {
    // The report is the real ArcConformance (thread_progress/pacing/succession/unmaterialized) —
    // NOT the old fictional `thread_coverage` stub the <pre> mock used to feed (that shape never
    // came off the wire; the JSON dump hid it — the mock-hides-contract lesson this view fixes).
    ph.getArcs.mockResolvedValue({ arcs: [{ id: 'sn1', title: 'Rising Action', arc_template_id: 'a1' }] });
    cat.getArcTemplateDrift.mockResolvedValue({ state: 'ok', report: {
      scope: 'arc', available: true, coarse: true, causal_verified: false,
      arc_template_id: 'a1', arc_name: 'Rising Action', chapter_count: 3,
      thread_progress: [{ thread: 't1', label: 'Revenge', planned: 3, covered: 2, missing: [{ motif_code: 'rev.slap', ord: 2 }] }],
      pacing: { comparable: true, planned: [10, 50, 90], realized: [{ chapter_index: 1, avg_tension: 12, scenes: 2 }], max_drift: 8 },
      succession: { causal_verified: false, threads: [{ thread: 't1', label: 'Revenge', transitions: 2, legal: 2, unrelated: 0, violations: [] }] },
      unmaterialized: [],
    } });
    ctrl.useArcTemplates.mockReturnValue(makeState({ selected: MINE as never }));
    render(<ArcTemplatesPanel {...props} />, { wrapper: qcWrap });
    await waitFor(() => expect(screen.getByTestId('drift-arc-sn1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('drift-arc-sn1'));
    // the structured view renders (NOT the raw <pre>)…
    await waitFor(() => expect(screen.getByTestId('arc-drift-view')).toBeInTheDocument());
    expect(screen.queryByTestId('arc-drift-report')).not.toBeInTheDocument();
    // …with the derived summary (drift present, not the clean verdict) + the data-derived
    // per-thread coverage + the missing motif code. (Copy is i18n-keyed; assert on data +
    // testids here, and on interpolated copy in the view's own unit test.)
    expect(screen.getByTestId('arc-drift-summary')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-drift-clean')).not.toBeInTheDocument();
    expect(screen.getByTestId('arc-drift-thread-t1').textContent).toMatch(/2\/3/);
    expect(screen.getByTestId('arc-drift-missing-t1').textContent).toContain('rev.slap');
  });

  it('34/AT-2: the Catalog tab browses public templates + adopt', async () => {
    const state = makeState();
    ctrl.useArcTemplates.mockReturnValue(state);
    cat.listCatalog.mockResolvedValue({ items: [{ id: 'pub1', code: 'p', name: 'Public Arc', chapter_span: 10, genre_tags: ['xianxia'] }], total: 1 });
    render(<ArcTemplatesPanel {...props} />, { wrapper: qcWrap });
    fireEvent.click(screen.getByTestId('arc-tab-catalog'));
    await waitFor(() => expect(screen.getByTestId('arc-catalog')).toBeInTheDocument());
    expect(screen.getByText('Public Arc')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('catalog-adopt-pub1'));
    expect(state.adopt).toHaveBeenCalledWith('pub1');
  });

  it('§2.9 scale: a library over the render cap shows an honest "first N" truncation notice', () => {
    ctrl.useArcTemplates.mockReturnValue(makeState({ truncated: true, totalInTier: 640 }));
    render(<ArcTemplatesPanel {...props} />);
    expect(screen.getByTestId('arc-templates-truncated')).toBeInTheDocument();
  });

  it('empty / loading / error are distinct honest states', () => {
    ctrl.useArcTemplates.mockReturnValue(makeState({ templates: [] as never }));
    const { rerender } = render(<ArcTemplatesPanel {...props} />);
    expect(screen.getByTestId('arc-templates-empty')).toBeInTheDocument();
    ctrl.useArcTemplates.mockReturnValue(makeState({ loading: true }));
    rerender(<ArcTemplatesPanel {...props} />);
    expect(screen.getByTestId('arc-templates-loading')).toBeInTheDocument();
    ctrl.useArcTemplates.mockReturnValue(makeState({ isError: true }));
    rerender(<ArcTemplatesPanel {...props} />);
    expect(screen.getByText('motif.arc.templates.loadError')).toBeInTheDocument();
  });
});
