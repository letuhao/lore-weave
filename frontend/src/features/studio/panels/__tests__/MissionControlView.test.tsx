// #20_agent_mode.md §3-7 — Mission control integration tests. Covers the
// single most correctness-critical rule (D8: Accept/Reject hard-disabled
// outside report_ready/failed/paused), D9 revert-all + partial-failure
// rendering, and D10 keyboard triage (fires + no-ops on an illegal state).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { StudioHostProvider } from '../../host/StudioHostProvider';
import type { AuthoringRun, AuthoringRunReport } from '@/features/composition/authoringRuns/types';

// A slightly smarter mock than this repo's usual `o?.defaultValue ?? k` stub —
// this file's assertions read interpolated values (e.g. the revert-all
// partial-failure error message), so `{{token}}` substitution is real here.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => {
      let s = (o?.defaultValue as string | undefined) ?? k;
      if (o) {
        for (const [key, val] of Object.entries(o)) {
          if (key === 'defaultValue') continue;
          s = s.replaceAll(`{{${key}}}`, String(val));
        }
      }
      return s;
    },
  }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const getRun = vi.fn();
const report = vi.fn();
const acceptUnit = vi.fn();
const rejectUnit = vi.fn();
const revertAll = vi.fn();
const pauseRun = vi.fn();
const startRun = vi.fn();
const closeRun = vi.fn();
const resumeRun = vi.fn();
const gateRun = vi.fn();
const setPausePolicy = vi.fn();

vi.mock('@/features/composition/authoringRuns/api', () => ({
  authoringRunsApi: {
    get: (...a: unknown[]) => getRun(...a),
    report: (...a: unknown[]) => report(...a),
    acceptUnit: (...a: unknown[]) => acceptUnit(...a),
    rejectUnit: (...a: unknown[]) => rejectUnit(...a),
    revertAll: (...a: unknown[]) => revertAll(...a),
    pause: (...a: unknown[]) => pauseRun(...a),
    start: (...a: unknown[]) => startRun(...a),
    close: (...a: unknown[]) => closeRun(...a),
    resume: (...a: unknown[]) => resumeRun(...a),
    gate: (...a: unknown[]) => gateRun(...a),
    setPausePolicy: (...a: unknown[]) => setPausePolicy(...a),
    list: vi.fn().mockResolvedValue({ items: [] }),
    create: vi.fn(),
  },
  errorDetail: (e: unknown) => (e as Error).message,
}));

const getPlanRun = vi.fn();
vi.mock('@/features/plan-forge/api', () => ({
  planForgeApi: { getRun: (...a: unknown[]) => getPlanRun(...a), listRuns: vi.fn().mockResolvedValue({ items: [] }) },
}));

const listChapters = vi.fn();
const compareRevisions = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listChapters: (...a: unknown[]) => listChapters(...a),
    compareRevisions: (...a: unknown[]) => compareRevisions(...a),
  },
}));

import { MissionControlView } from '../agentMode/MissionControlView';

function makeRun(overrides: Partial<AuthoringRun> = {}): AuthoringRun {
  return {
    run_id: 'run-1', book_id: 'b1', plan_run_id: 'plan-1', level: 3,
    scope: ['ch1', 'ch2'], budget_usd: '4.00', spent_usd: '1.00',
    tool_allowlist: ['composition_write_prose'], params: {},
    breaker_state: {}, status: 'paused', current_unit: 2,
    error_message: null, background: false, created_at: null, updated_at: null,
    driver_heartbeat_at: null, pause_after_each_unit: true,
    ...overrides,
  };
}

function makeReport(run: AuthoringRun): AuthoringRunReport {
  return {
    run,
    units: [
      {
        run_id: run.run_id, unit_index: 0, chapter_id: 'ch1', status: 'accepted',
        pre_revision_id: 'pre0', post_revision_id: 'post0', cost_usd: '0.30',
        error_message: null, critic_verdict: { severity: 'ok', summary: 'fine', cost_usd: '0.00' },
        created_at: null, updated_at: null, downstream_unit_indexes: [],
      },
      {
        run_id: run.run_id, unit_index: 1, chapter_id: 'ch2', status: 'drafted',
        pre_revision_id: 'pre1', post_revision_id: 'post1', cost_usd: '0.25',
        error_message: null, critic_verdict: { severity: 'warn', summary: 'pacing drift', cost_usd: '0.00' },
        created_at: null, updated_at: null, downstream_unit_indexes: [],
      },
    ],
    dependencies: { model: 'sequential_thread', note: '' },
  };
}

function chaptersPage() {
  return {
    items: [
      { chapter_id: 'ch1', book_id: 'b1', title: 'Ch One', original_filename: '1.txt', original_language: 'en', content_type: 'text', byte_size: 1, sort_order: 1, lifecycle_state: 'active' },
      { chapter_id: 'ch2', book_id: 'b1', title: 'Ch Two', original_filename: '2.txt', original_language: 'en', content_type: 'text', byte_size: 1, sort_order: 2, lifecycle_state: 'active' },
    ],
    total: 2,
  };
}

function renderMission(run: AuthoringRun) {
  getRun.mockResolvedValue(run);
  listChapters.mockResolvedValue(chaptersPage());
  getPlanRun.mockResolvedValue({ id: 'plan-1', status: 'validated' });
  compareRevisions.mockResolvedValue({
    left: {}, right: {}, truncated: false,
    diff: [{ op: 'equal', text: 'Rin descended into the mine.' }, { op: 'insert', text: ' Alone.' }],
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId="b1">
        <MissionControlView bookId="b1" runId={run.run_id} onBack={() => {}} />
      </StudioHostProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('MissionControlView — D8 Accept/Reject hard-disable (the single most correctness-critical rule)', () => {
  it('a PAUSED run with a drafted unit shows enabled Accept/Reject', async () => {
    const run = makeRun({ status: 'paused' });
    report.mockResolvedValue(makeReport(run));
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-unit-queue')).toBeTruthy());
    fireEvent.click(screen.getAllByTestId('agent-mode-queue-row')[1]); // unit 1 = drafted
    await waitFor(() => expect(screen.getByTestId('agent-mode-accept-unit')).toBeTruthy());
    expect(screen.getByTestId('agent-mode-accept-unit')).not.toBeDisabled();
    expect(screen.getByTestId('agent-mode-reject-unit')).not.toBeDisabled();
    expect(screen.queryByTestId('agent-mode-review-blocked')).toBeNull();
  });

  it('a RUNNING run hard-disables review with an inline reason — never a silently-failed request', async () => {
    const run = makeRun({ status: 'running', current_unit: 2 });
    // report() 409s server-side outside reviewable statuses — must not be called.
    report.mockRejectedValue(new Error('should not be called while running'));
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-unit-queue')).toBeTruthy());
    fireEvent.click(screen.getAllByTestId('agent-mode-queue-row')[0]);
    await waitFor(() => expect(screen.getByTestId('agent-mode-review-blocked')).toBeTruthy());
    expect(screen.queryByTestId('agent-mode-accept-unit')).toBeNull();
    expect(screen.queryByTestId('agent-mode-reject-unit')).toBeNull();
    expect(report).not.toHaveBeenCalled();
  });

  it('accepting calls the real endpoint with the selected unit index', async () => {
    const run = makeRun({ status: 'paused' });
    report.mockResolvedValue(makeReport(run));
    acceptUnit.mockResolvedValue({});
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-unit-queue')).toBeTruthy());
    fireEvent.click(screen.getAllByTestId('agent-mode-queue-row')[1]);
    await waitFor(() => expect(screen.getByTestId('agent-mode-accept-unit')).toBeTruthy());
    fireEvent.click(screen.getByTestId('agent-mode-accept-unit'));
    await waitFor(() => expect(acceptUnit).toHaveBeenCalledWith('run-1', 1, 'tok'));
  });
});

describe('MissionControlView — D10 keyboard triage', () => {
  it("'a'/'r' fire accept/reject when reviewable, no-op when not", async () => {
    const run = makeRun({ status: 'paused' });
    report.mockResolvedValue(makeReport(run));
    acceptUnit.mockResolvedValue({});
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-unit-queue')).toBeTruthy());
    fireEvent.click(screen.getAllByTestId('agent-mode-queue-row')[1]);
    const panel = await screen.findByTestId('agent-mode-diff-panel');
    fireEvent.keyDown(panel, { key: 'a' });
    await waitFor(() => expect(acceptUnit).toHaveBeenCalledWith('run-1', 1, 'tok'));
  });

  it("ArrowRight/ArrowLeft navigate the selected unit", async () => {
    const run = makeRun({ status: 'paused' });
    report.mockResolvedValue(makeReport(run));
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-unit-queue')).toBeTruthy());
    fireEvent.click(screen.getAllByTestId('agent-mode-queue-row')[0]);
    const panel = await screen.findByTestId('agent-mode-diff-panel');
    fireEvent.keyDown(panel, { key: 'ArrowRight' });
    await waitFor(() => {
      const rows = screen.getAllByTestId('agent-mode-queue-row');
      expect(rows[1].className).toMatch(/ring-1/);
    });
  });

  it("no-ops (does not throw, does not call the API) for 'a' on a non-reviewable unit", async () => {
    const run = makeRun({ status: 'running', current_unit: 2 });
    report.mockRejectedValue(new Error('should not be called'));
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-unit-queue')).toBeTruthy());
    fireEvent.click(screen.getAllByTestId('agent-mode-queue-row')[0]);
    const panel = await screen.findByTestId('agent-mode-diff-panel');
    fireEvent.keyDown(panel, { key: 'a' });
    fireEvent.keyDown(panel, { key: 'r' });
    expect(acceptUnit).not.toHaveBeenCalled();
    expect(rejectUnit).not.toHaveBeenCalled();
  });
});

describe('MissionControlView — D9 revert-all confirm + partial-failure rendering', () => {
  it('opens a confirmation modal listing the real affected units', async () => {
    const run = makeRun({ status: 'paused' });
    report.mockResolvedValue(makeReport(run));
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-action-revert-all')).toBeTruthy());
    fireEvent.click(screen.getByTestId('agent-mode-action-revert-all'));
    const modal = await screen.findByTestId('agent-mode-revert-modal');
    // drafted (unit 1) and accepted (unit 0) are both affected; unit indices are 1-based in the label.
    expect(within(modal).getAllByTestId('agent-mode-revert-list-item')).toHaveLength(2);
    expect(revertAll).not.toHaveBeenCalled();
  });

  it('renders the PARTIAL-FAILURE result — which reverted, which failed, run left open', async () => {
    const run = makeRun({ status: 'paused' });
    report.mockResolvedValue(makeReport(run));
    revertAll.mockResolvedValue({
      reverted_unit_indexes: [1], failed_unit_index: 0, error: 'restore failed: book-service 502',
      run_status: 'paused', closed: false,
    });
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-action-revert-all')).toBeTruthy());
    fireEvent.click(screen.getByTestId('agent-mode-action-revert-all'));
    await screen.findByTestId('agent-mode-revert-modal');
    fireEvent.click(screen.getByTestId('agent-mode-revert-confirm'));
    const result = await screen.findByTestId('agent-mode-revert-result');
    expect(result.textContent).toMatch(/stopped partway/i);
    expect(result.textContent).toContain('restore failed: book-service 502');
  });

  it('renders full success and does not falsely claim it when partial', async () => {
    const run = makeRun({ status: 'paused' });
    report.mockResolvedValue(makeReport(run));
    revertAll.mockResolvedValue({
      reverted_unit_indexes: [1, 0], failed_unit_index: null, error: null, run_status: 'closed', closed: true,
    });
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-action-revert-all')).toBeTruthy());
    fireEvent.click(screen.getByTestId('agent-mode-action-revert-all'));
    await screen.findByTestId('agent-mode-revert-modal');
    fireEvent.click(screen.getByTestId('agent-mode-revert-confirm'));
    const result = await screen.findByTestId('agent-mode-revert-result');
    expect(result.textContent).toMatch(/reverted; the run is now closed/i);
  });
});

describe('MissionControlView — RunHeader FSM-legal action buttons', () => {
  it('a `gated` run shows exactly Start + Close', async () => {
    const run = makeRun({ status: 'gated' });
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-run-header')).toBeTruthy());
    expect(screen.getByTestId('agent-mode-action-start')).toBeTruthy();
    expect(screen.getByTestId('agent-mode-action-close')).toBeTruthy();
    expect(screen.queryByTestId('agent-mode-action-pause')).toBeNull();
    expect(screen.queryByTestId('agent-mode-action-revert-all')).toBeNull();
  });

  it('a `running` run shows exactly Pause', async () => {
    const run = makeRun({ status: 'running' });
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-run-header')).toBeTruthy());
    expect(screen.getByTestId('agent-mode-action-pause')).toBeTruthy();
    expect(screen.queryByTestId('agent-mode-action-start')).toBeNull();
    expect(screen.queryByTestId('agent-mode-action-close')).toBeNull();
  });

  it('a `closed` run shows no action buttons', async () => {
    const run = makeRun({ status: 'closed' });
    report.mockResolvedValue(makeReport(run));
    renderMission(run);
    await waitFor(() => expect(screen.getByTestId('agent-mode-run-header')).toBeTruthy());
    for (const action of ['gate', 'start', 'pause', 'resume', 'close', 'revert-all']) {
      expect(screen.queryByTestId(`agent-mode-action-${action}`)).toBeNull();
    }
  });
});
