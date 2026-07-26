import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// W5 — NewChatDialog renders the shared ModelPicker with capability="chat"
// (the fix for rerankers/embedders being offered in the chat picker) and
// preselects the user's default chat model when set.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

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

const getDefaultsMock = vi.fn();
vi.mock('@/features/settings/api', () => ({
  CHAT_CAPABILITY: 'chat',
  defaultModelsApi: { get: (...args: unknown[]) => getDefaultsMock(...args) },
}));

import { NewChatDialog } from '../NewChatDialog';
import { invalidateUserModelsCache } from '@/components/model-picker';

const MODELS = [
  { user_model_id: 'chat-1', provider_credential_id: 'c', provider_kind: 'lm_studio', provider_model_name: 'gemma-26b', alias: null, is_active: true, is_favorite: false, capability_flags: {}, tags: [], created_at: '2026-01-01T00:00:00Z' },
  { user_model_id: 'chat-2', provider_credential_id: 'c', provider_kind: 'lm_studio', provider_model_name: 'qwen-7b', alias: null, is_active: true, is_favorite: false, capability_flags: {}, tags: [], created_at: '2026-01-01T00:00:00Z' },
];

describe('NewChatDialog (W5 shared ModelPicker)', () => {
  beforeEach(() => {
    listUserModelsMock.mockReset();
    getDefaultsMock.mockReset();
    localStorage.clear();
    invalidateUserModelsCache();
    listUserModelsMock.mockResolvedValue({ items: MODELS });
    getDefaultsMock.mockResolvedValue({ defaults: {} });
  });

  it('fetches CHAT-capability models only (reranker-in-chat-picker fix)', async () => {
    render(
      <MemoryRouter>
        <NewChatDialog open onClose={vi.fn()} onCreate={vi.fn()} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    expect(listUserModelsMock).toHaveBeenCalledWith('tok-test', {
      include_inactive: false,
      capability: 'chat',
    });
  });

  it('preselects the first model (server order = favorites first) when no default is set', async () => {
    render(
      <MemoryRouter>
        <NewChatDialog open onClose={vi.fn()} onCreate={vi.fn()} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveTextContent('gemma-26b'));
  });

  it('preselects the user default chat model when set and listed', async () => {
    getDefaultsMock.mockResolvedValue({ defaults: { chat: 'chat-2' } });
    render(
      <MemoryRouter>
        <NewChatDialog open onClose={vi.fn()} onCreate={vi.fn()} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveTextContent('qwen-7b'));
  });

  it('creates the session with the picked model', async () => {
    const onCreate = vi.fn();
    render(
      <MemoryRouter>
        <NewChatDialog open onClose={vi.fn()} onCreate={onCreate} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveTextContent('gemma-26b'));
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /qwen-7b/ }));
    fireEvent.click(screen.getByText('new.start_chat'));
    expect(onCreate).toHaveBeenCalledWith('chat-2', undefined, undefined);
  });
});
