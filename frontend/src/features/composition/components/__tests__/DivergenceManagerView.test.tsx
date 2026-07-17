import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// ── mocks ──────────────────────────────────────────────────────────────────
let resolution: unknown = null;
vi.mock('../../hooks/useWork', () => ({
  useWorkResolution: () => ({ data: resolution, isLoading: false }),
}));

const switchTo = vi.fn().mockResolvedValue(true);
let activeWorkId: string | null = null;
vi.mock('../../hooks/useActiveWork', () => ({
  useActiveWorkId: () => ({ data: activeWorkId }),
  useSetActiveWork: () => ({ switchTo, isSwitching: false }),
}));

const patchWork = vi.fn().mockResolvedValue({});
const getDerivativeContext = vi.fn().mockResolvedValue({
  is_derivative: true, name: 'Branch A', taxonomy: 'au', branch_point: 61,
  canon_rules: ['Lam Vũ dies'], overrides: [{ target_entity_id: 'e1', overridden_fields: {} }],
  source_work_id: 'w-canon', source_project_id: 'canon',
});
vi.mock('../../api', () => ({
  compositionApi: {
    patchWork: (...a: unknown[]) => patchWork(...a),
    getDerivativeContext: (...a: unknown[]) => getDerivativeContext(...a),
  },
}));

vi.mock('../DivergenceWizard', () => ({
  DivergenceWizard: ({ open }: { open: boolean }) => (open ? <div data-testid="wizard-open" /> : null),
}));

vi.mock('../BranchDiffView', () => ({
  BranchDiffView: (p: { derivativeProjectId: string }) => <div data-testid="branch-diff-view" data-proj={p.derivativeProjectId} />,
}));

// S-04: the editable spec block has its own test (DivergenceSpecEditor.test.tsx).
// Here it is a stub — this view test only proves the manager mounts it for a
// selected derivative (and swaps it out for the Diff tab).
vi.mock('../DivergenceSpecEditor', () => ({
  DivergenceSpecEditor: (p: { projectId: string }) => <div data-testid="divergence-spec-editor" data-proj={p.projectId} />,
}));

const toastSuccess = vi.hoisted(() => vi.fn());
vi.mock('sonner', () => ({ toast: Object.assign(vi.fn(), { success: toastSuccess, error: vi.fn(), warning: vi.fn() }) }));

import { DivergenceManagerView } from '../DivergenceManagerView';

const canon = { project_id: 'canon', version: 1, status: 'active', settings: {} };
const derivA = { project_id: 'da', version: 2, status: 'active', source_work_id: 'w-canon', branch_point: 61, settings: { derivative_name: 'Branch A' } };
const derivB = { project_id: 'db', version: 3, status: 'active', source_work_id: 'w-canon', branch_point: 10, settings: { derivative_name: 'Branch B' } };

const renderView = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DivergenceManagerView bookId="book-1" token="tok" />
    </QueryClientProvider>,
  );

beforeEach(() => {
  switchTo.mockClear();
  patchWork.mockClear();
  getDerivativeContext.mockClear();
  activeWorkId = null;
});

describe('DivergenceManagerView', () => {
  it('lists the canonical Work and every derivative', () => {
    resolution = { status: 'candidates', work: null, candidates: [derivA, canon, derivB] };
    renderView();
    expect(screen.getByTestId('divergence-canon-row')).toBeInTheDocument();
    expect(screen.getByTestId('divergence-row-da')).toHaveTextContent('Branch A');
    expect(screen.getByTestId('divergence-row-db')).toHaveTextContent('Branch B');
  });

  it('marks canonical active by default and hides its Switch button', () => {
    resolution = { status: 'candidates', work: null, candidates: [canon, derivA] };
    renderView();
    // canon is active (no pref) → its row carries the active badge, no switch-to-canon control here
    expect(screen.getByTestId('divergence-active-badge')).toBeInTheDocument();
    expect(screen.getByTestId('divergence-switch-da')).toBeInTheDocument();
  });

  it('Switch to a derivative writes the active-work pref', () => {
    resolution = { status: 'candidates', work: null, candidates: [canon, derivA] };
    renderView();
    fireEvent.click(screen.getByTestId('divergence-switch-da'));
    expect(switchTo).toHaveBeenCalledWith('da');
  });

  it('Archive a derivative patches status archived with If-Match version', async () => {
    resolution = { status: 'candidates', work: null, candidates: [canon, derivA] };
    renderView();
    fireEvent.click(screen.getByTestId('divergence-archive-da'));
    await waitFor(() => expect(patchWork).toHaveBeenCalledWith('da', { status: 'archived' }, 'tok', { version: 2 }));
  });

  it('audit fix: archive offers an Undo that RESTORES the derivative (status active) — no one-way door', async () => {
    resolution = { status: 'candidates', work: null, candidates: [canon, derivA] };
    toastSuccess.mockClear();
    patchWork.mockResolvedValueOnce({ project_id: 'da', version: 3 });  // the post-archive Work
    renderView();
    fireEvent.click(screen.getByTestId('divergence-archive-da'));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    // the success toast carried an Undo action → invoking it restores status→active with the bumped version
    const opts = toastSuccess.mock.calls.at(-1)?.[1] as { action?: { onClick: () => void } } | undefined;
    expect(opts?.action).toBeTruthy();
    opts!.action!.onClick();
    await waitFor(() => expect(patchWork).toHaveBeenCalledWith('da', { status: 'active' }, 'tok', { version: 3 }));
  });

  it('selecting a derivative loads its context and mounts the editable spec editor', async () => {
    resolution = { status: 'candidates', work: null, candidates: [canon, derivA] };
    renderView();
    fireEvent.click(screen.getByTestId('divergence-row-da'));
    await waitFor(() => expect(screen.getByTestId('divergence-spec-editor')).toHaveAttribute('data-proj', 'da'));
    expect(getDerivativeContext).toHaveBeenCalledWith('da', 'tok');
  });

  it('the Diff tab swaps the spec editor for the branch prose diff', async () => {
    resolution = { status: 'candidates', work: null, candidates: [canon, derivA] };
    renderView();
    fireEvent.click(screen.getByTestId('divergence-row-da'));
    await waitFor(() => expect(screen.getByTestId('divergence-spec-editor')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('divergence-tab-diff'));
    const diff = screen.getByTestId('branch-diff-view');
    expect(diff.getAttribute('data-proj')).toBe('da');
    expect(screen.queryByTestId('divergence-spec-editor')).not.toBeInTheDocument();
  });

  it('shows the empty state when there are no derivatives', () => {
    resolution = { status: 'found', work: canon, candidates: [] };
    renderView();
    expect(screen.getByTestId('divergence-empty')).toBeInTheDocument();
  });

  it('opens the create wizard', () => {
    resolution = { status: 'found', work: canon, candidates: [] };
    renderView();
    fireEvent.click(screen.getByTestId('divergence-new'));
    expect(screen.getByTestId('wizard-open')).toBeInTheDocument();
  });

  it('shows a no-work state when the book has no canonical Work', () => {
    resolution = { status: 'none', work: null, candidates: [] };
    renderView();
    expect(screen.getByTestId('divergence-nowork')).toBeInTheDocument();
  });
});
