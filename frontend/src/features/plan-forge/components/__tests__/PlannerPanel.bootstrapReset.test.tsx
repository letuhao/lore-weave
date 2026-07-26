import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { IDockviewPanelProps } from 'dockview-react';

// /review-impl MED: recompiling the SAME run with a DIFFERENT arc must not leave
// the previous arc's stale bootstrap proposal on screen (the underlying package
// artifact just changed — an old diff no longer describes reality). Isolated from
// PlannerPanel.test.tsx's own mocks (a static run:null fixture there never renders
// BootstrapPanel at all) so this integration path gets its own real coverage.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/studio/host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'b1' }),
  useRegisterStudioTool: vi.fn(),
}));

const runCompile = vi.fn();
vi.mock('../../hooks/usePlanRun', () => ({
  usePlanRun: () => ({
    run: {
      id: 'r1', book_id: 'b1', status: 'compiled', mode: 'rules', model_ref: null,
      source_checksum: 'abc', active_job_id: null, job_status: null, error_detail: null,
      checkpoint_state: {}, arcs: [{ id: 'arc_1', title: 'Arc 1' }], artifacts: [],
      created_at: '', updated_at: '',
    },
    busy: false, polling: false, error: null,
    selfCheck: null, validation: null, compileResult: null,
    createRun: vi.fn(), loadRun: vi.fn(), resetRun: vi.fn(),
    runSelfCheck: vi.fn(), runValidate: vi.fn(), runCompile,
  }),
}));

const bootstrapReset = vi.fn();
const bootstrapPropose = vi.fn();
vi.mock('../../hooks/useBootstrap', () => ({
  useBootstrap: () => ({
    proposal: {
      id: 'p1', run_id: 'r1', book_id: 'b1', owner_user_id: 'u1', status: 'pending',
      diff: { new_chapters: [{ event_id: 'e1', title: 'Stale Chapter', ordinal: 1 }], new_glossary_entities: [] },
      applied_results: {}, error_detail: null, created_at: '', updated_at: '',
    },
    busy: false, error: null,
    propose: bootstrapPropose, approve: vi.fn(), reject: vi.fn(), apply: vi.fn(), reset: bootstrapReset,
  }),
}));

const listRuns = vi.fn();
vi.mock('../../api', () => ({
  planForgeApi: { listRuns: (...a: unknown[]) => listRuns(...a) },
}));

import { PlannerPanel } from '../PlannerPanel';

function renderPanel() {
  const props = { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
  return render(
    <MemoryRouter>
      <PlannerPanel {...props} />
    </MemoryRouter>,
  );
}

describe('PlannerPanel — bootstrap reset on recompile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listRuns.mockResolvedValue({ items: [], next_cursor: null });
  });

  it('clicking Compile (a different arc) resets the stale bootstrap proposal', () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('plan-tab-run'));
    // the stale proposal from a PRIOR arc is visible before recompiling
    expect(screen.getByTestId('bootstrap-panel').textContent).toContain('Stale Chapter');

    fireEvent.click(screen.getByTestId('plan-compile-btn'));

    expect(bootstrapReset).toHaveBeenCalledTimes(1);
    expect(runCompile).toHaveBeenCalledWith('arc_1');
  });
});
