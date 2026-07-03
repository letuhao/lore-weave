import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { UserModel } from '@/features/ai-models/api';

// W5 — THE shared ModelPicker: search, favorites pinned, recents, capability
// filter, badges, keyboard nav, orphan + empty states.

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const listUserModelsMock = vi.fn();
const patchFavoriteMock = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: (...args: unknown[]) => listUserModelsMock(...args),
      patchFavorite: (...args: unknown[]) => patchFavoriteMock(...args),
    },
  };
});

// Server prefs: keep the recents machinery deterministic (localStorage-only).
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

import { ModelPicker } from '../ModelPicker';
import { invalidateUserModelsCache } from '../useUserModels';

function model(overrides: Partial<UserModel> & { user_model_id: string }): UserModel {
  return {
    provider_credential_id: 'cred-1',
    provider_kind: 'lm_studio',
    provider_model_name: overrides.user_model_id,
    context_length: null,
    alias: null,
    is_active: true,
    is_favorite: false,
    capability_flags: {},
    tags: [],
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const MODELS: UserModel[] = [
  model({
    user_model_id: 'fav-1',
    provider_kind: 'openai',
    provider_model_name: 'gpt-4o',
    is_favorite: true,
    context_length: 131072,
    capability_flags: { chat: true, tool_calling: true },
    pricing: { input_per_mtok: 2.5, output_per_mtok: 10 },
  }),
  model({
    user_model_id: 'local-1',
    provider_model_name: 'qwen2.5-7b-instruct',
    alias: 'Qwen 7B',
    context_length: 32768,
  }),
  model({
    user_model_id: 'local-2',
    provider_model_name: 'gemma-4-26b',
    capability_flags: { _capability: 'chat', _display_name: 'Gemma 26B' },
  }),
];

function openPicker() {
  fireEvent.click(screen.getByRole('combobox'));
}

describe('ModelPicker (W5 shared component)', () => {
  beforeEach(() => {
    listUserModelsMock.mockReset();
    patchFavoriteMock.mockReset();
    localStorage.clear();
    invalidateUserModelsCache();
  });

  it('fetches active-only + the passed capability (server-side filter)', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    expect(listUserModelsMock).toHaveBeenCalledWith('tok-test', {
      include_inactive: false,
      capability: 'chat',
    });
  });

  it('opens a listbox, pins favorites on top, groups the rest by provider', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await screen.findByRole('combobox');
    openPicker();
    const listbox = await screen.findByRole('listbox');
    expect(listbox).toBeInTheDocument();
    // Favorites section header + provider group header
    expect(screen.getByText('modelPicker.favorites')).toBeInTheDocument();
    expect(screen.getByText('lm_studio')).toBeInTheDocument();
    const options = screen.getAllByRole('option');
    // Favorite first (display name = provider_model_name, no alias)
    expect(options[0]).toHaveTextContent('gpt-4o');
    // alias + legacy _display_name honored
    expect(screen.getByText('Qwen 7B')).toBeInTheDocument();
    expect(screen.getByText('Gemma 26B')).toBeInTheDocument();
  });

  it('search filters by alias / model name / provider kind', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await screen.findByRole('combobox');
    openPicker();
    const search = await screen.findByLabelText('modelPicker.search');
    fireEvent.change(search, { target: { value: 'qwen' } });
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('Qwen 7B');
    // no match → empty message
    fireEvent.change(search, { target: { value: 'zzz-nope' } });
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByText('modelPicker.noResults')).toBeInTheDocument();
  });

  it('selecting an option emits its user_model_id and records a recent', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={onChange} />
      </MemoryRouter>,
    );
    await screen.findByRole('combobox');
    openPicker();
    fireEvent.click(await screen.findByText('Qwen 7B'));
    expect(onChange).toHaveBeenCalledWith('local-1');
    expect(JSON.parse(localStorage.getItem('lw.modelPicker.recents.chat.u1') ?? '[]')).toEqual(['local-1']);
  });

  it('shows a Recent section from stored recents (per capability, favorites excluded)', async () => {
    localStorage.setItem('lw.modelPicker.recents.chat.u1', JSON.stringify(['local-2', 'fav-1']));
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await screen.findByRole('combobox');
    openPicker();
    expect(await screen.findByText('modelPicker.recents')).toBeInTheDocument();
    const options = screen.getAllByRole('option');
    // Order: favorites (fav-1), then recents (local-2 only — fav-1 already pinned)
    expect(options[0]).toHaveTextContent('gpt-4o');
    expect(options[1]).toHaveTextContent('Gemma 26B');
  });

  it('star toggle PATCHes the favorite route optimistically', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    patchFavoriteMock.mockResolvedValue(model({ user_model_id: 'local-1', is_favorite: true }));
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await screen.findByRole('combobox');
    openPicker();
    const stars = await screen.findAllByLabelText('modelPicker.favorite');
    fireEvent.click(stars[0]);
    expect(patchFavoriteMock).toHaveBeenCalledWith('tok-test', expect.any(String), true);
    // optimistic: the model now renders in the Favorites section without refetch
    await waitFor(() => expect(screen.getAllByLabelText('modelPicker.unfavorite').length).toBeGreaterThan(1));
  });

  it('renders badges: context length and the $0-local hint', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await screen.findByRole('combobox');
    openPicker();
    // context-length badges render (test i18n returns the key; n is computed)
    expect((await screen.findAllByText('modelPicker.ctx')).length).toBeGreaterThanOrEqual(2);
    // lm_studio models get the $0-local hint
    expect(screen.getAllByText('modelPicker.free').length).toBeGreaterThanOrEqual(2);
    // priced remote model gets the $ hint
    expect(screen.getByText('$')).toBeInTheDocument();
  });

  it('keyboard: ArrowDown + Enter selects the active option', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={onChange} />
      </MemoryRouter>,
    );
    await screen.findByRole('combobox');
    openPicker();
    const search = await screen.findByLabelText('modelPicker.search');
    fireEvent.keyDown(search, { key: 'ArrowDown' });
    fireEvent.keyDown(search, { key: 'Enter' });
    // index 0 = favorite gpt-4o, ArrowDown → index 1 = Qwen 7B (first lm_studio)
    expect(onChange).toHaveBeenCalledWith('local-1');
  });

  it('allowNone renders a none option that emits null', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value="local-1" onChange={onChange} allowNone noneLabel="No model" />
      </MemoryRouter>,
    );
    await screen.findByRole('combobox');
    openPicker();
    fireEvent.click(await screen.findByText('No model'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('shows an orphan row when the saved value left the registry', async () => {
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value="gone-uuid" onChange={vi.fn()} />
      </MemoryRouter>,
    );
    const trigger = await screen.findByRole('combobox');
    await waitFor(() => expect(trigger).toHaveTextContent('modelPicker.orphan'));
    openPicker();
    expect(screen.getAllByText('modelPicker.orphan').length).toBeGreaterThanOrEqual(1);
  });

  it('zero models → empty state with the AddModelCta register link', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(
      <MemoryRouter>
        <ModelPicker capability="rerank" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    expect(await screen.findByText('modelPicker.empty')).toBeInTheDocument();
    const cta = screen.getByRole('link');
    expect(cta.getAttribute('href')).toContain('/settings/providers');
    expect(cta.getAttribute('href')).toContain('return=');
    // trigger disabled — nothing to pick
    expect(screen.getByRole('combobox')).toBeDisabled();
  });

  it('zero models with a custom emptyState renders the override', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(
      <MemoryRouter>
        <ModelPicker capability="rerank" value={null} onChange={vi.fn()} emptyState={<p>custom-empty</p>} />
      </MemoryRouter>,
    );
    expect(await screen.findByText('custom-empty')).toBeInTheDocument();
    expect(screen.queryByText('modelPicker.empty')).toBeNull();
  });

  it('fetch failure surfaces the error line', async () => {
    listUserModelsMock.mockRejectedValue(new Error('boom'));
    render(
      <MemoryRouter>
        <ModelPicker capability="chat" value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    expect(await screen.findByText('modelPicker.error')).toBeInTheDocument();
  });
});
