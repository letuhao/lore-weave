import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// D-WX-PRECISION-FILTER-MODEL-ARCH — the precision-filter model picker: fetches the
// user's chat-capability BYOK models and binds the project's
// precision_filter.model_ref (user_model_id UUID). The default (None) option ⇒
// null = reuse the extraction model (BE fallback). NEVER a hardcoded/env model.
// W5: the control is now the shared ModelPicker (combobox trigger + listbox).

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

// W5 — ModelPicker also imports getUserModelMeta from this module: spread the
// actual module and only override the API surface.
const listUserModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: (...args: unknown[]) => listUserModelsMock(...args),
      patchFavorite: vi.fn(),
    },
  };
});

// ModelPicker persists recents via syncPrefs — stub the server round-trip.
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

import { PrecisionFilterModelPicker } from '../PrecisionFilterModelPicker';
import { invalidateUserModelsCache } from '@/components/model-picker';

const CHAT_MODEL = {
  user_model_id: 'fm1',
  provider_kind: 'lm_studio',
  provider_model_name: 'qwen2.5-7b-instruct',
  alias: null,
  is_active: true,
  is_favorite: false,
  capability_flags: { chat: true },
  tags: [],
  created_at: '2026-04-24T00:00:00Z',
};

/** Open the shared picker's listbox and click the option matching `name`. */
async function pickOption(name: string | RegExp) {
  fireEvent.click(await screen.findByRole('combobox'));
  fireEvent.click(await screen.findByRole('option', { name }));
}

describe('PrecisionFilterModelPicker (D-WX-PRECISION-FILTER-MODEL-ARCH)', () => {
  beforeEach(() => {
    listUserModelsMock.mockReset();
    // W5 — flush the shared fetch's module-level cache + recents cache.
    invalidateUserModelsCache();
    localStorage.clear();
  });

  it('fetches chat-CAPABILITY models and binds the chosen user_model_id', async () => {
    listUserModelsMock.mockResolvedValue({ items: [CHAT_MODEL] });
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <PrecisionFilterModelPicker value={null} onChange={onChange} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    // BYOK + capability-scoped — never a hardcoded/env model.
    expect(listUserModelsMock).toHaveBeenCalledWith('tok-test', {
      capability: 'chat',
      include_inactive: false,
    });
    await pickOption(/qwen2\.5-7b-instruct/);
    expect(onChange).toHaveBeenCalledWith('fm1');
  });

  it('selecting the default option clears the model (→ reuse extraction model)', async () => {
    listUserModelsMock.mockResolvedValue({ items: [CHAT_MODEL] });
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <PrecisionFilterModelPicker value="fm1" onChange={onChange} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    await pickOption('projects.extractionTuning.filterModelDefault');
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('renders an orphan row when the saved model left the registry', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(
      <MemoryRouter>
        <PrecisionFilterModelPicker value="gone-uuid" onChange={vi.fn()} />
      </MemoryRouter>,
    );
    // W5 — orphan handling moved into the shared ModelPicker (its own key).
    await screen.findByText(/modelPicker\.orphan/);
  });
});
