import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { ModelRolePicker } from '../ModelRolePicker';
import { invalidateUserModelsCache } from '@/components/model-picker';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

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

const M1 = {
  user_model_id: 'm1', provider_credential_id: 'c1', provider_kind: 'openai',
  provider_model_name: 'gpt-4o', alias: 'My GPT', is_active: true, is_favorite: false,
  capability_flags: {}, tags: [], created_at: '2026-01-01T00:00:00Z',
};

function renderPicker(props: Partial<Parameters<typeof ModelRolePicker>[0]> = {}) {
  return render(
    <ModelRolePicker capability="chat" label="Translator" value={null} onChange={() => {}} {...props} />,
  );
}

const trigger = () => screen.getByRole('combobox');

describe('ModelRolePicker (W5 — shared ModelPicker wrapper)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    invalidateUserModelsCache();
  });

  it('lists the user models for the given capability (active-only, server-side filter)', async () => {
    listUserModelsMock.mockResolvedValue({ items: [M1] });
    renderPicker();
    await waitFor(() => expect(trigger()).toBeInTheDocument());
    fireEvent.click(trigger());
    expect(await screen.findByRole('option', { name: /My GPT/ })).toBeInTheDocument();
    expect(listUserModelsMock).toHaveBeenCalledWith('tok', { include_inactive: false, capability: 'chat' });
  });

  it('renders an orphan row when the value is not in the fetched list', async () => {
    // value points at a model the registry no longer returns → must still show the truth,
    // not silently fall back to "None".
    listUserModelsMock.mockResolvedValue({ items: [M1] });
    renderPicker({ value: 'deleted-model' });
    await waitFor(() => expect(trigger()).toHaveTextContent('modelPicker.orphan'));
  });

  it('offers a None option that emits null', async () => {
    listUserModelsMock.mockResolvedValue({ items: [M1] });
    const onChange = vi.fn();
    renderPicker({ value: 'm1', onChange });
    await waitFor(() => expect(trigger()).toHaveTextContent('My GPT'));
    fireEvent.click(trigger());
    fireEvent.click(await screen.findByRole('option', { name: 'matrix.none' }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('empty registry → the capability-specific matrix.empty hint (custom emptyState)', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    renderPicker({ capability: 'rerank' });
    expect(await screen.findByText('matrix.empty')).toBeInTheDocument();
  });

  it('D-S5C-PICKER-DEDUP: two pickers of the same capability share ONE fetch', async () => {
    listUserModelsMock.mockResolvedValue({ items: [M1] });
    render(
      <>
        <ModelRolePicker capability="chat" label="Translator" value={null} onChange={() => {}} />
        <ModelRolePicker capability="chat" label="Verifier" value={null} onChange={() => {}} />
      </>,
    );
    await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(2));
    // the shared useUserModels module cache dedupes the identical (token, capability) fetch.
    expect(listUserModelsMock).toHaveBeenCalledTimes(1);
  });
});
