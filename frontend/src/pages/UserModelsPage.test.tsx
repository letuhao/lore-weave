import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { UserModelsPage } from './UserModelsPage';

const listProviders = vi.fn();
const createProvider = vi.fn();
const listProviderInventory = vi.fn();
const listUserModels = vi.fn();
const createUserModel = vi.fn();
const patchUserModelActivation = vi.fn();
const patchUserModelFavorite = vi.fn();

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'token-1' }),
}));

vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: {
    listProviders: (...args: unknown[]) => listProviders(...args),
    createProvider: (...args: unknown[]) => createProvider(...args),
    listProviderInventory: (...args: unknown[]) => listProviderInventory(...args),
    listUserModels: (...args: unknown[]) => listUserModels(...args),
    createUserModel: (...args: unknown[]) => createUserModel(...args),
    patchUserModelActivation: (...args: unknown[]) => patchUserModelActivation(...args),
    patchUserModelFavorite: (...args: unknown[]) => patchUserModelFavorite(...args),
  },
}));

describe('UserModelsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  it('renders unified provider and model sections', async () => {
    listProviders.mockResolvedValue({
      items: [{ provider_credential_id: 'pc-1', provider_kind: 'openai', display_name: 'OpenAI Main', status: 'active' }],
    });
    listProviderInventory.mockResolvedValue({ items: [{ provider_model_name: 'gpt-4o-mini', context_length: 128000 }] });
    listUserModels.mockResolvedValue({
      items: [
        {
          user_model_id: 'um-1',
          provider_credential_id: 'pc-1',
          provider_kind: 'openai',
          provider_model_name: 'gpt-4o-mini',
          alias: 'Fast',
          is_active: true,
          is_favorite: false,
          tags: [{ tag_name: 'thinking', note: 'long context' }],
        },
      ],
    });

    render(<UserModelsPage />);

    expect(await screen.findByText('Provider connections')).toBeInTheDocument();
    expect(await screen.findByText('Models for selected provider')).toBeInTheDocument();
    expect(await screen.findByText('Quick filters')).toBeInTheDocument();
    expect(await screen.findByText('Fast')).toBeInTheDocument();
    expect(await screen.findByText('gpt-4o-mini')).toBeInTheDocument();
    expect(await screen.findByText(/thinking\(long context\)/)).toBeInTheDocument();
  });

  it('supports one-screen flow create provider -> select/create model -> toggle states', async () => {
    listProviders
      .mockResolvedValueOnce({
        items: [{ provider_credential_id: 'pc-1', provider_kind: 'openai', display_name: 'OpenAI Main', status: 'active' }],
      })
      .mockResolvedValue({
        items: [
          { provider_credential_id: 'pc-1', provider_kind: 'openai', display_name: 'OpenAI Main', status: 'active' },
          { provider_credential_id: 'pc-2', provider_kind: 'anthropic', display_name: 'Anthropic Team', status: 'active' },
        ],
      });
    createProvider.mockResolvedValueOnce({ provider_credential_id: 'pc-2' });
    listProviderInventory.mockResolvedValue({ items: [{ provider_model_name: 'claude-3-7-sonnet', context_length: 200000 }] });
    listUserModels.mockResolvedValue({
      items: [
        {
          user_model_id: 'um-1',
          provider_credential_id: 'pc-2',
          provider_kind: 'anthropic',
          provider_model_name: 'claude-3-7-sonnet',
          is_active: true,
          is_favorite: false,
          tags: [],
        },
      ],
    });
    createUserModel.mockResolvedValueOnce({});
    patchUserModelActivation.mockResolvedValueOnce({});
    patchUserModelFavorite.mockResolvedValueOnce({});

    render(<UserModelsPage />);

    fireEvent.change(await screen.findByPlaceholderText('Connection display name'), { target: { value: 'Anthropic Team' } });
    fireEvent.change(screen.getByPlaceholderText('Secret/API key (required)'), { target: { value: 'sk-demo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add provider' }));

    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith('token-1', {
        provider_kind: 'openai',
        display_name: 'Anthropic Team',
        secret: 'sk-demo',
        endpoint_base_url: undefined,
      }),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'claude-3-7-sonnet' }));
    fireEvent.change(screen.getByPlaceholderText('Alias (optional)'), { target: { value: 'Reasoner' } });
    fireEvent.change(screen.getByPlaceholderText('Tags format: tag:note, tag2:note2'), {
      target: { value: 'thinking:analysis, tts:voice' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Register model' }));

    await waitFor(() =>
      expect(createUserModel).toHaveBeenCalledWith('token-1', {
        provider_credential_id: 'pc-2',
        provider_model_name: 'claude-3-7-sonnet',
        context_length: 200000,
        alias: 'Reasoner',
        tags: [
          { tag_name: 'thinking', note: 'analysis' },
          { tag_name: 'tts', note: 'voice' },
        ],
      }),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Set inactive' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Favorite' }));

    await waitFor(() => expect(patchUserModelActivation).toHaveBeenCalledWith('token-1', 'um-1', false));
    await waitFor(() => expect(patchUserModelFavorite).toHaveBeenCalledWith('token-1', 'um-1', true));
  });

  it('passes quick filter params to listUserModels', async () => {
    listProviders.mockResolvedValue({
      items: [{ provider_credential_id: 'pc-1', provider_kind: 'openai', display_name: 'OpenAI Main', status: 'active' }],
    });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [] });

    render(<UserModelsPage />);

    fireEvent.click(await screen.findByLabelText('Only favorites'));
    fireEvent.click(screen.getByLabelText('Include inactive'));

    await waitFor(() =>
      expect(listUserModels).toHaveBeenLastCalledWith('token-1', {
        only_favorites: true,
        include_inactive: false,
        provider_kind: 'openai',
      }),
    );
  });
});
