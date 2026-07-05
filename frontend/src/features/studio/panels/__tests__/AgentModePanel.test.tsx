// #20_agent_mode.md D1 — the ONE `agent-mode` panel with 3 internal views.
// Covers: tab switching (all 3 views stay mounted, CSS-hidden), the Runs list
// blocked banner + disabled "+ New run" (one-active-run-per-book), and the New
// Run view's real plan/chapter picker driving a real create+gate call.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listRuns = vi.fn();
const createRun = vi.fn();
const gateRun = vi.fn();
const getRun = vi.fn();
vi.mock('@/features/composition/authoringRuns/api', () => ({
  authoringRunsApi: {
    list: (...a: unknown[]) => listRuns(...a),
    create: (...a: unknown[]) => createRun(...a),
    gate: (...a: unknown[]) => gateRun(...a),
    get: (...a: unknown[]) => getRun(...a),
    report: vi.fn().mockRejectedValue(new Error('not reportable')),
    setPausePolicy: vi.fn(),
  },
  errorDetail: (e: unknown) => (e as Error).message,
}));

const listPlanRuns = vi.fn();
const getPlanRun = vi.fn();
vi.mock('@/features/plan-forge/api', () => ({
  planForgeApi: { listRuns: (...a: unknown[]) => listPlanRuns(...a), getRun: (...a: unknown[]) => getPlanRun(...a) },
}));

const listChapters = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { listChapters: (...a: unknown[]) => listChapters(...a), compareRevisions: vi.fn() },
}));

import { AgentModePanel } from '../AgentModePanel';

function dockProps(params?: Record<string, unknown>, onDidParametersChange?: (cb: (next: Record<string, unknown> | undefined) => void) => { dispose: () => void }): IDockviewPanelProps {
  return {
    api: { setTitle: vi.fn(), onDidParametersChange },
    params,
  } as unknown as IDockviewPanelProps;
}

function renderPanel(props: IDockviewPanelProps = dockProps()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId="b1">
        <AgentModePanel {...props} />
      </StudioHostProvider>
    </QueryClientProvider>,
  );
}

function runFixture(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run-1', book_id: 'b1', plan_run_id: 'plan-1', level: 3, scope: ['ch1'],
    budget_usd: '4.00', spent_usd: '0.00', tool_allowlist: ['composition_write_prose'],
    params: {}, breaker_state: {}, status: 'gated', current_unit: 0, error_message: null,
    background: false, created_at: null, updated_at: null, ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listRuns.mockResolvedValue({ items: [] });
  listPlanRuns.mockResolvedValue({ items: [{ id: 'plan-1', status: 'validated', book_id: 'b1', mode: 'rules', model_ref: null, source_checksum: null, active_job_id: null, job_status: null, error_detail: null, checkpoint_state: null, artifacts: [], created_at: '', updated_at: '' }] });
  // Mission control's gate-check recomputation independently fetches the run's plan status.
  getPlanRun.mockResolvedValue({ id: 'plan-1', status: 'validated' });
  listChapters.mockResolvedValue({
    items: [{ chapter_id: 'ch1', book_id: 'b1', title: 'Ch One', original_filename: '1.txt', original_language: 'en', content_type: 'text', byte_size: 1, sort_order: 1, lifecycle_state: 'active' }],
    total: 1,
  });
});

describe('AgentModePanel — nav tabs', () => {
  it('defaults to the Runs list view', () => {
    renderPanel();
    expect(screen.getByTestId('agent-mode-tab-list').getAttribute('aria-selected')).toBe('true');
    expect(screen.getByTestId('agent-mode-view-list').className).not.toMatch(/hidden/);
    expect(screen.getByTestId('agent-mode-view-new').className).toMatch(/hidden/);
  });

  it('switching tabs never unmounts a view (CSS hidden, not a ternary)', () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('agent-mode-tab-new'));
    // The list view's root is still IN THE DOM (just hidden), not removed.
    expect(screen.getByTestId('agent-mode-view-list')).toBeTruthy();
    expect(screen.getByTestId('agent-mode-view-list').className).toMatch(/hidden/);
    expect(screen.getByTestId('agent-mode-view-new').className).not.toMatch(/hidden/);
  });
});

describe('AgentModePanel — Runs list', () => {
  it('shows an empty state with zero runs', async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('agent-mode-runs-empty')).toBeTruthy());
  });

  it('blocks "+ New run" with a banner when an active run exists', async () => {
    listRuns.mockResolvedValue({ items: [runFixture({ status: 'running' })] });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('agent-mode-blocked-banner')).toBeTruthy());
    expect(screen.getByTestId('agent-mode-new-run-button')).toBeDisabled();
  });

  it('clicking a run row opens Mission control at that run', async () => {
    listRuns.mockResolvedValue({ items: [runFixture({ status: 'closed' })] });
    getRun.mockResolvedValue(runFixture({ status: 'closed' }));
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('agent-mode-run-row')).toBeTruthy());
    fireEvent.click(screen.getByTestId('agent-mode-run-row'));
    expect(screen.getByTestId('agent-mode-tab-mission').getAttribute('aria-selected')).toBe('true');
    await waitFor(() => expect(screen.getByTestId('agent-mode-mission-control')).toBeTruthy());
  });
});

describe('AgentModePanel — D-AGENT-MODE-NOTIFY deep link', () => {
  it('opens directly on Mission control when mounted with a {runId} param (terminal-notification click)', async () => {
    getRun.mockResolvedValue(runFixture({ run_id: 'run-7', status: 'closed' }));
    renderPanel(dockProps({ runId: 'run-7' }));
    expect(screen.getByTestId('agent-mode-tab-mission').getAttribute('aria-selected')).toBe('true');
    await waitFor(() => expect(screen.getByTestId('agent-mode-mission-control')).toBeTruthy());
  });

  it('retargets to Mission control on a later params change (already-open singleton, DOCK-6)', async () => {
    getRun.mockResolvedValue(runFixture({ run_id: 'run-8', status: 'closed' }));
    let onChange: ((next: Record<string, unknown> | undefined) => void) | undefined;
    renderPanel(dockProps(undefined, (cb) => { onChange = cb; return { dispose: vi.fn() }; }));
    expect(screen.getByTestId('agent-mode-tab-list').getAttribute('aria-selected')).toBe('true');
    onChange?.({ runId: 'run-8' });
    await waitFor(() => expect(screen.getByTestId('agent-mode-tab-mission').getAttribute('aria-selected')).toBe('true'));
  });
});

describe('AgentModePanel — New run config', () => {
  it('renders the real plan picker and chapter checklist from mocked API data (not hardcoded)', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('agent-mode-tab-new'));
    await waitFor(() => expect(screen.getByTestId('agent-mode-plan-select')).toBeTruthy());
    expect(screen.getByText(/plan-1/)).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('agent-mode-chapter-check-ch1')).toBeTruthy());
    // "Ch One" legitimately appears twice (the checklist AND the derived run-order list).
    expect(screen.getAllByText('Ch One').length).toBeGreaterThan(0);
  });

  it('shows a plan-empty CTA when the book has zero approved plan runs', async () => {
    listPlanRuns.mockResolvedValue({ items: [] });
    renderPanel();
    fireEvent.click(screen.getByTestId('agent-mode-tab-new'));
    await waitFor(() => expect(screen.getByTestId('agent-mode-plan-empty')).toBeTruthy());
  });

  it('"Run gate check" creates then gates the run, landing on Mission control', async () => {
    createRun.mockResolvedValue(runFixture({ run_id: 'new-run', status: 'draft' }));
    gateRun.mockResolvedValue(runFixture({ run_id: 'new-run', status: 'gated' }));
    getRun.mockResolvedValue(runFixture({ run_id: 'new-run', status: 'gated' }));
    renderPanel();
    fireEvent.click(screen.getByTestId('agent-mode-tab-new'));
    await waitFor(() => expect(screen.getByTestId('agent-mode-chapter-check-ch1')).toBeTruthy());
    await waitFor(() => expect(screen.getByTestId('agent-mode-run-gate-check')).not.toBeDisabled());
    fireEvent.click(screen.getByTestId('agent-mode-run-gate-check'));
    await waitFor(() => expect(createRun).toHaveBeenCalled());
    expect(gateRun).toHaveBeenCalledWith('new-run', 'tok');
    await waitFor(() => expect(screen.getByTestId('agent-mode-tab-mission').getAttribute('aria-selected')).toBe('true'));
  });

  it('a failing gate check keeps the user on New Run with the real server error shown', async () => {
    createRun.mockResolvedValue(runFixture({ run_id: 'new-run', status: 'draft' }));
    gateRun.mockRejectedValue(Object.assign(new Error('budget_usd must be > 0'), { body: { detail: 'budget_usd must be > 0' } }));
    renderPanel();
    fireEvent.click(screen.getByTestId('agent-mode-tab-new'));
    await waitFor(() => expect(screen.getByTestId('agent-mode-chapter-check-ch1')).toBeTruthy());
    fireEvent.click(screen.getByTestId('agent-mode-run-gate-check'));
    await waitFor(() => expect(screen.getByTestId('agent-mode-gate-error')).toBeTruthy());
    expect(screen.getByTestId('agent-mode-tab-list').getAttribute('aria-selected')).toBe('false');
    expect(screen.getByTestId('agent-mode-tab-new').getAttribute('aria-selected')).toBe('true');
  });
});
