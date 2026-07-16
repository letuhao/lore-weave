import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { IDockviewPanelProps } from 'dockview-react';
import { invalidateUserModelsCache } from '@/components/model-picker';

// W5 — PlannerPanel now renders THE shared ModelPicker (the bespoke plan-forge
// picker is deleted). These tests lock the migrated behaviors: llm mode requires a
// model, the favorite/first model is auto-picked as a DERIVED default, and the
// picked model_ref reaches createRun.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/studio/host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'b1' }),
  // AddModelCta (rendered by the no-models empty state) reads the OPTIONAL host for its DOCK-7
  // branch; PlannerPanel is a studio dock panel, so return the same host as useStudioHost.
  useOptionalStudioHost: () => ({ bookId: 'b1' }),
  useRegisterStudioTool: vi.fn(),
}));

const createRun = vi.fn();
const loadRun = vi.fn();
const resetRun = vi.fn();
vi.mock('../../hooks/usePlanRun', () => ({
  usePlanRun: () => ({
    run: null, busy: false, polling: false, error: null,
    selfCheck: null, validation: null, compileResult: null,
    createRun, loadRun, resetRun, runSelfCheck: vi.fn(), runValidate: vi.fn(), runCompile: vi.fn(),
  }),
}));

// D-PLANFORGE-NO-RESUME follow-up — the new "Runs" tab (default view) fetches its own
// list independently of usePlanRun; empty by default so these pre-existing propose-flow
// tests (which switch to the "Run" tab) aren't affected by it.
const listRuns = vi.fn();
vi.mock('../../api', () => ({
  planForgeApi: { listRuns: (...a: unknown[]) => listRuns(...a) },
}));

const listUserModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: (...a: unknown[]) => listUserModelsMock(...a),
      patchFavorite: vi.fn(),
    },
  };
});
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

import { PlannerPanel } from '../PlannerPanel';

function model(id: string, alias: string, favorite = false) {
  return {
    user_model_id: id, provider_credential_id: 'c1', provider_kind: 'lm_studio',
    provider_model_name: id, alias, is_active: true, is_favorite: favorite,
    capability_flags: {}, tags: [], created_at: '2026-01-01T00:00:00Z',
  };
}

function renderPanel() {
  const props = { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
  // MemoryRouter: the zero-models default empty state renders AddModelCta (a router Link).
  return render(
    <MemoryRouter>
      <PlannerPanel {...props} />
    </MemoryRouter>,
  );
}

describe('PlannerPanel model picker (W5 shared ModelPicker)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    invalidateUserModelsCache();
    listRuns.mockResolvedValue({ items: [], next_cursor: null });
  });

  it('rules mode (explicitly chosen) proposes without any model', () => {
    // D-PLANFORGE-GENERAL-VALIDATE: 'rules' is no longer the default (it's a
    // fixture-only parser), but it must still work when the writer picks it.
    listUserModelsMock.mockResolvedValue({ items: [] });
    renderPanel();
    fireEvent.click(screen.getByTestId('plan-tab-run'));
    fireEvent.click(screen.getByTestId('plan-mode-rules'));
    fireEvent.change(screen.getByTestId('plan-source-input'), { target: { value: '# system' } });
    fireEvent.click(screen.getByTestId('plan-propose-btn'));
    expect(createRun).toHaveBeenCalledWith({ source_markdown: '# system', mode: 'rules' });
  });

  it('defaults to llm mode on open (D-PLANFORGE-GENERAL-VALIDATE)', async () => {
    listUserModelsMock.mockResolvedValue({ items: [model('m-first', 'First'), model('m-fav', 'Fav', true)] });
    renderPanel();
    fireEvent.click(screen.getByTestId('plan-tab-run'));
    // Never clicks plan-mode-llm — the model picker appearing proves llm is
    // already the active mode by default.
    await waitFor(() => {
      const trigger = within(screen.getByTestId('plan-model-picker')).getByRole('combobox');
      expect(trigger).toHaveTextContent('Fav');
    });
  });

  it('never auto-picks a model with an explicit non-chat capability flag (D-PLANFORGE-MODEL-AUTOPICK)', async () => {
    const reranker = {
      ...model('m-rerank', 'bge-reranker-v2-m3'),
      capability_flags: { _capability: 'chat', rerank: true },
    };
    const chatModel = model('m-chat', 'Real Chat Model');
    listUserModelsMock.mockResolvedValue({ items: [reranker, chatModel] });
    renderPanel();
    fireEvent.click(screen.getByTestId('plan-tab-run'));
    await waitFor(() => {
      const trigger = within(screen.getByTestId('plan-model-picker')).getByRole('combobox');
      expect(trigger).toHaveTextContent('Real Chat Model');
    });
  });

  it('llm mode auto-picks the FAVORITE model as the derived default and proposes with it', async () => {
    listUserModelsMock.mockResolvedValue({ items: [model('m-first', 'First'), model('m-fav', 'Fav', true)] });
    renderPanel();
    fireEvent.click(screen.getByTestId('plan-tab-run'));
    fireEvent.change(screen.getByTestId('plan-source-input'), { target: { value: '# system' } });
    fireEvent.click(screen.getByTestId('plan-mode-llm'));
    // the shared picker fetched (capability=chat, active-only) and the favorite shows on the trigger
    await waitFor(() => {
      const trigger = within(screen.getByTestId('plan-model-picker')).getByRole('combobox');
      expect(trigger).toHaveTextContent('Fav');
    });
    expect(listUserModelsMock).toHaveBeenCalledWith('tok', { include_inactive: false, capability: 'chat' });
    const propose = screen.getByTestId('plan-propose-btn') as HTMLButtonElement;
    expect(propose.disabled).toBe(false);
    fireEvent.click(propose);
    expect(createRun).toHaveBeenCalledWith({ source_markdown: '# system', mode: 'llm', model_ref: 'm-fav' });
  });

  it('llm mode with NO models keeps Propose disabled', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    renderPanel();
    fireEvent.click(screen.getByTestId('plan-tab-run'));
    fireEvent.change(screen.getByTestId('plan-source-input'), { target: { value: '# system' } });
    fireEvent.click(screen.getByTestId('plan-mode-llm'));
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    await waitFor(() =>
      expect((screen.getByTestId('plan-propose-btn') as HTMLButtonElement).disabled).toBe(true));
  });

  it('an explicit pick from the listbox overrides the derived default', async () => {
    listUserModelsMock.mockResolvedValue({ items: [model('m-first', 'First'), model('m-fav', 'Fav', true)] });
    renderPanel();
    fireEvent.click(screen.getByTestId('plan-tab-run'));
    fireEvent.change(screen.getByTestId('plan-source-input'), { target: { value: '# system' } });
    fireEvent.click(screen.getByTestId('plan-mode-llm'));
    const picker = () => within(screen.getByTestId('plan-model-picker'));
    await waitFor(() => expect(picker().getByRole('combobox')).toHaveTextContent('Fav'));
    fireEvent.click(picker().getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /First/ }));
    await waitFor(() => expect(picker().getByRole('combobox')).toHaveTextContent('First'));
    fireEvent.click(screen.getByTestId('plan-propose-btn'));
    expect(createRun).toHaveBeenCalledWith({ source_markdown: '# system', mode: 'llm', model_ref: 'm-first' });
  });
});

// D-PLANFORGE-NO-RESUME — the actual bug this closes: usePlanRun never fetched past runs on
// mount, so reopening the Planner (or a fresh page load) looked exactly like the run was never
// made even though it exists server-side. These tests lock the fix: a real "Runs" tab, default
// view, backed by the server list.
describe('PlannerPanel — Runs list (D-PLANFORGE-NO-RESUME)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    invalidateUserModelsCache();
  });

  function runFixture(overrides: Record<string, unknown> = {}) {
    return {
      id: 'run-1', book_id: 'b1', status: 'proposed', mode: 'rules', model_ref: null,
      source_checksum: 'abc', active_job_id: null, job_status: null, error_detail: null,
      checkpoint_state: null, arcs: [], artifacts: [], created_at: '2026-07-01T00:00:00Z', updated_at: '', ...overrides,
    };
  }

  it('defaults to the Runs list view, not a blank propose form', () => {
    listRuns.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel();
    expect(screen.getByTestId('plan-tab-list').getAttribute('aria-selected')).toBe('true');
    expect(screen.getByTestId('planner-view-list').className).not.toMatch(/hidden/);
    expect(screen.getByTestId('planner-view-run').className).toMatch(/hidden/);
  });

  it('shows an empty state with zero runs (the bug this fixes: no longer indistinguishable from "never used")', async () => {
    listRuns.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('plan-runs-empty')).toBeTruthy());
  });

  it('lists real past runs fetched from the server on mount', async () => {
    listRuns.mockResolvedValue({ items: [runFixture(), runFixture({ id: 'run-2', status: 'failed' })], next_cursor: null });
    renderPanel();
    await waitFor(() => expect(screen.getAllByTestId('plan-run-row')).toHaveLength(2));
    expect(listRuns).toHaveBeenCalledWith('b1', 'tok', { limit: 50, includeArchived: false });
  });

  it('clicking a run row loads it and switches to the Run tab', async () => {
    listRuns.mockResolvedValue({ items: [runFixture()], next_cursor: null });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('plan-run-row')).toBeTruthy());
    fireEvent.click(screen.getByTestId('plan-run-row'));
    expect(loadRun).toHaveBeenCalledWith('run-1');
    expect(screen.getByTestId('plan-tab-run').getAttribute('aria-selected')).toBe('true');
  });

  it('"+ New propose" resets the current run and switches to the Run tab', async () => {
    listRuns.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('plan-new-run-button')).toBeTruthy());
    fireEvent.click(screen.getByTestId('plan-new-run-button'));
    expect(resetRun).toHaveBeenCalled();
    expect(screen.getByTestId('plan-tab-run').getAttribute('aria-selected')).toBe('true');
  });

  it('switching tabs never unmounts a view (CSS hidden, not a ternary)', () => {
    listRuns.mockResolvedValue({ items: [], next_cursor: null });
    renderPanel();
    fireEvent.click(screen.getByTestId('plan-tab-run'));
    expect(screen.getByTestId('planner-view-list')).toBeTruthy();
    expect(screen.getByTestId('planner-view-list').className).toMatch(/hidden/);
    expect(screen.getByTestId('planner-view-run').className).not.toMatch(/hidden/);
  });
});
