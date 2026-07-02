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
  useRegisterStudioTool: vi.fn(),
}));

const createRun = vi.fn();
vi.mock('../../hooks/usePlanRun', () => ({
  usePlanRun: () => ({
    run: null, busy: false, polling: false, error: null,
    selfCheck: null, validation: null, compileResult: null,
    createRun, runSelfCheck: vi.fn(), runValidate: vi.fn(), runCompile: vi.fn(),
  }),
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
  });

  it('rules mode proposes without any model', () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    renderPanel();
    fireEvent.change(screen.getByTestId('plan-source-input'), { target: { value: '# system' } });
    fireEvent.click(screen.getByTestId('plan-propose-btn'));
    expect(createRun).toHaveBeenCalledWith({ source_markdown: '# system', mode: 'rules' });
  });

  it('llm mode auto-picks the FAVORITE model as the derived default and proposes with it', async () => {
    listUserModelsMock.mockResolvedValue({ items: [model('m-first', 'First'), model('m-fav', 'Fav', true)] });
    renderPanel();
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
    fireEvent.change(screen.getByTestId('plan-source-input'), { target: { value: '# system' } });
    fireEvent.click(screen.getByTestId('plan-mode-llm'));
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    await waitFor(() =>
      expect((screen.getByTestId('plan-propose-btn') as HTMLButtonElement).disabled).toBe(true));
  });

  it('an explicit pick from the listbox overrides the derived default', async () => {
    listUserModelsMock.mockResolvedValue({ items: [model('m-first', 'First'), model('m-fav', 'Fav', true)] });
    renderPanel();
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
