import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProvidersSection } from './ProvidersSection';

const listProviders = vi.fn();
const createProvider = vi.fn();
const listProviderInventory = vi.fn();
const listUserModels = vi.fn();
const createUserModel = vi.fn();
const patchUserModelActivation = vi.fn();
const patchUserModelFavorite = vi.fn();
const patchProvider = vi.fn();
const deleteProvider = vi.fn();
const patchUserModel = vi.fn();
const deleteUserModel = vi.fn();
const putUserModelTags = vi.fn();
const verifyUserModel = vi.fn();

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
    patchProvider: (...args: unknown[]) => patchProvider(...args),
    deleteProvider: (...args: unknown[]) => deleteProvider(...args),
    patchUserModel: (...args: unknown[]) => patchUserModel(...args),
    deleteUserModel: (...args: unknown[]) => deleteUserModel(...args),
    putUserModelTags: (...args: unknown[]) => putUserModelTags(...args),
    verifyUserModel: (...args: unknown[]) => verifyUserModel(...args),
  },
}));

const renderSection = () =>
  render(
    <MemoryRouter>
      <ProvidersSection />
    </MemoryRouter>,
  );

describe('ProvidersSection', () => {
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

    renderSection();

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

    renderSection();

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
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    fireEvent.change(screen.getByPlaceholderText('Tag name *'), { target: { value: 'thinking' } });
    fireEvent.change(screen.getByPlaceholderText('Note (optional)'), { target: { value: 'analysis' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    fireEvent.change(screen.getByPlaceholderText('Tag name *'), { target: { value: 'tts' } });
    fireEvent.change(screen.getByPlaceholderText('Note (optional)'), { target: { value: 'voice' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
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

    renderSection();

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

// ── shared fixtures ────────────────────────────────────────────────────────────

const providerWithSecret = {
  provider_credential_id: 'pc-1',
  provider_kind: 'openai',
  display_name: 'OpenAI Main',
  status: 'active',
  has_secret: true,
  endpoint_base_url: null,
};

const providerNoSecret = {
  provider_credential_id: 'pc-2',
  provider_kind: 'anthropic',
  display_name: 'Anthropic Team',
  status: 'active',
  has_secret: false,
  endpoint_base_url: null,
};

const ollamaProvider = {
  provider_credential_id: 'pc-3',
  provider_kind: 'ollama',
  display_name: 'Local Ollama',
  status: 'active',
  has_secret: false,
  endpoint_base_url: 'http://localhost:11434',
};

const openaiModel = {
  user_model_id: 'um-1',
  provider_credential_id: 'pc-1',
  provider_kind: 'openai',
  provider_model_name: 'gpt-4o-mini',
  alias: 'Fast',
  context_length: 16384,
  is_active: true,
  is_favorite: false,
  tags: [{ tag_name: 'chat', note: '' }],
  capability_flags: { chat: true, tool_calling: true, vision: false, thinking: false },
};

const ollamaModel = {
  user_model_id: 'um-2',
  provider_credential_id: 'pc-3',
  provider_kind: 'ollama',
  provider_model_name: 'llama3',
  alias: '',
  context_length: 4096,
  is_active: true,
  is_favorite: false,
  tags: [],
  capability_flags: { chat: true, tool_calling: false, vision: false, thinking: false },
};

const setupProviderEdit = async () => {
  listProviders.mockResolvedValue({ items: [providerWithSecret, providerNoSecret] });
  listProviderInventory.mockResolvedValue({ items: [] });
  listUserModels.mockResolvedValue({ items: [] });
  renderSection();
  await screen.findByText('OpenAI Main');
};

const setupModelEdit = async (models = [openaiModel]) => {
  listProviders.mockResolvedValue({ items: [providerWithSecret] });
  listProviderInventory.mockResolvedValue({ items: [] });
  listUserModels.mockResolvedValue({ items: models });
  renderSection();
  await screen.findByText('Fast');
};

// ── T17-T29: Provider edit/delete ─────────────────────────────────────────────

describe('ProvidersSection — provider edit/delete', () => {
  beforeEach(() => { vi.clearAllMocks(); cleanup(); });

  it('T17: each provider row shows [Edit] and [Delete] buttons', async () => {
    await setupProviderEdit();
    for (const id of ['pc-1', 'pc-2']) {
      const row = screen.getByTestId(`provider-row-${id}`);
      expect(within(row).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
      expect(within(row).getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    }
  });

  it('T18: click Edit → inline form appears pre-filled with display_name, endpoint_base_url, active', async () => {
    listProviders.mockResolvedValue({ items: [{ ...providerWithSecret, endpoint_base_url: 'https://my.api.com' }] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [] });
    renderSection();
    await screen.findByText('OpenAI Main');

    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('provider-edit-form-pc-1');
    expect(within(form).getByDisplayValue('OpenAI Main')).toBeInTheDocument();
    expect(within(form).getByDisplayValue('https://my.api.com')).toBeInTheDocument();
    expect((within(form).getByRole('checkbox', { name: 'Active' }) as HTMLInputElement).checked).toBe(true);
  });

  it('T19: has_secret=true → secret input placeholder is ·········', async () => {
    await setupProviderEdit();
    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('provider-edit-form-pc-1');
    const secretInput = within(form).getByPlaceholderText('·········');
    expect(secretInput).toBeInTheDocument();
    expect((secretInput as HTMLInputElement).value).toBe('');
  });

  it('T20: has_secret=false → secret input placeholder is "Enter API key / secret"', async () => {
    await setupProviderEdit();
    fireEvent.click(within(screen.getByTestId('provider-row-pc-2')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('provider-edit-form-pc-2');
    expect(within(form).getByPlaceholderText('Enter API key / secret')).toBeInTheDocument();
  });

  it('T21: leave secret blank + Save → patchProvider called WITHOUT secret field', async () => {
    patchProvider.mockResolvedValueOnce({ ...providerWithSecret });
    listProviders.mockResolvedValue({ items: [providerWithSecret] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [] });
    renderSection();
    await screen.findByText('OpenAI Main');

    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('provider-edit-form-pc-1');
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patchProvider).toHaveBeenCalled());
    const payload = patchProvider.mock.calls[0][2];
    expect(payload).not.toHaveProperty('secret');
  });

  it('T22: type new secret + Save → patchProvider called WITH secret', async () => {
    patchProvider.mockResolvedValueOnce({ ...providerWithSecret });
    listProviders.mockResolvedValue({ items: [providerWithSecret] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [] });
    renderSection();
    await screen.findByText('OpenAI Main');

    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('provider-edit-form-pc-1');
    fireEvent.change(within(form).getByPlaceholderText('·········'), { target: { value: 'new-key-123' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patchProvider).toHaveBeenCalled());
    const payload = patchProvider.mock.calls[0][2];
    expect(payload.secret).toBe('new-key-123');
  });

  it('T23: Save with empty display_name → patchProvider NOT called, error shown', async () => {
    listProviders.mockResolvedValue({ items: [providerWithSecret] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [] });
    renderSection();
    await screen.findByText('OpenAI Main');

    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('provider-edit-form-pc-1');
    fireEvent.change(within(form).getByDisplayValue('OpenAI Main'), { target: { value: '' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }));

    expect(patchProvider).not.toHaveBeenCalled();
    expect(within(form).getByText('Display name is required')).toBeInTheDocument();
  });

  it('T24: click Cancel on edit form → form closes, patchProvider NOT called', async () => {
    await setupProviderEdit();
    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('provider-edit-form-pc-1');
    fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByTestId('provider-edit-form-pc-1')).not.toBeInTheDocument();
    expect(patchProvider).not.toHaveBeenCalled();
  });

  it('T25: opening Edit on provider B while A is open → A collapses, B opens', async () => {
    await setupProviderEdit();
    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Edit' }));
    expect(screen.getByTestId('provider-edit-form-pc-1')).toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId('provider-row-pc-2')).getByRole('button', { name: 'Edit' }));
    expect(screen.queryByTestId('provider-edit-form-pc-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('provider-edit-form-pc-2')).toBeInTheDocument();
  });

  it('T26: click Delete → inline confirm shows provider display_name', async () => {
    await setupProviderEdit();
    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Delete' }));
    const confirm = screen.getByTestId('provider-delete-confirm-pc-1');
    expect(within(confirm).getByText('OpenAI Main')).toBeInTheDocument();
    expect(within(confirm).getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
  });

  it('T27: click Confirm delete → deleteProvider called with correct ID', async () => {
    deleteProvider.mockResolvedValueOnce(undefined);
    listProviders.mockResolvedValueOnce({ items: [providerWithSecret] }).mockResolvedValue({ items: [] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [] });
    renderSection();
    await screen.findByText('OpenAI Main');

    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Delete' }));
    fireEvent.click(within(screen.getByTestId('provider-delete-confirm-pc-1')).getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(deleteProvider).toHaveBeenCalledWith('token-1', 'pc-1'));
  });

  it('T28: deleting selected provider → selection cleared (model section shows no provider text)', async () => {
    deleteProvider.mockResolvedValueOnce(undefined);
    listProviders.mockResolvedValueOnce({ items: [providerWithSecret] }).mockResolvedValue({ items: [] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [] });
    renderSection();
    await screen.findByText('OpenAI Main');

    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Delete' }));
    fireEvent.click(within(screen.getByTestId('provider-delete-confirm-pc-1')).getByRole('button', { name: 'Confirm' }));

    await waitFor(() =>
      expect(screen.getByText('Select a provider connection above to continue.')).toBeInTheDocument(),
    );
  });

  it('T29: click Cancel on delete confirm → deleteProvider NOT called', async () => {
    await setupProviderEdit();
    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Delete' }));
    const confirm = screen.getByTestId('provider-delete-confirm-pc-1');
    fireEvent.click(within(confirm).getByRole('button', { name: 'Cancel' }));
    expect(deleteProvider).not.toHaveBeenCalled();
  });
});

// ── T30-T41: Model edit/delete ────────────────────────────────────────────────

describe('ProvidersSection — model edit/delete', () => {
  beforeEach(() => { vi.clearAllMocks(); cleanup(); });

  it('T30: each model row shows [Edit] and [Delete] buttons', async () => {
    await setupModelEdit();
    const row = screen.getByTestId('model-row-um-1');
    expect(within(row).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(within(row).getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('T31: click Edit on a model → form pre-filled with alias and flags', async () => {
    await setupModelEdit();
    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('model-edit-form-um-1');
    expect(within(form).getByDisplayValue('Fast')).toBeInTheDocument();
    expect((within(form).getByRole('checkbox', { name: 'chat' }) as HTMLInputElement).checked).toBe(true);
    expect((within(form).getByRole('checkbox', { name: 'tool_calling' }) as HTMLInputElement).checked).toBe(true);
    expect((within(form).getByRole('checkbox', { name: 'vision' }) as HTMLInputElement).checked).toBe(false);
  });

  it('T32: ollama model → context_length input visible in edit form', async () => {
    listProviders.mockResolvedValue({ items: [ollamaProvider] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [ollamaModel] });
    renderSection();
    await screen.findByText('llama3');

    fireEvent.click(within(screen.getByTestId('model-row-um-2')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('model-edit-form-um-2');
    expect(within(form).getByDisplayValue('4096')).toBeInTheDocument();
  });

  it('T33: openai model → context_length input NOT shown in edit form', async () => {
    await setupModelEdit();
    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('model-edit-form-um-1');
    expect(within(form).queryByLabelText('Context length')).not.toBeInTheDocument();
  });

  it('T34: Save model edit → patchUserModel called with alias and capability_flags', async () => {
    patchUserModel.mockResolvedValueOnce({ ...openaiModel, alias: 'Speed' });
    putUserModelTags.mockResolvedValueOnce({});
    listProviders.mockResolvedValue({ items: [providerWithSecret] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [openaiModel] });
    renderSection();
    await screen.findByText('Fast');

    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('model-edit-form-um-1');
    fireEvent.change(within(form).getByDisplayValue('Fast'), { target: { value: 'Speed' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patchUserModel).toHaveBeenCalledWith(
      'token-1', 'um-1',
      expect.objectContaining({ alias: 'Speed', capability_flags: expect.any(Object) }),
    ));
  });

  it('T35: Save model edit → putUserModelTags called with updated tags', async () => {
    patchUserModel.mockResolvedValueOnce(openaiModel);
    putUserModelTags.mockResolvedValueOnce({});
    listProviders.mockResolvedValue({ items: [providerWithSecret] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [openaiModel] });
    renderSection();
    await screen.findByText('Fast');

    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('model-edit-form-um-1');
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(putUserModelTags).toHaveBeenCalledWith('token-1', 'um-1', expect.any(Array)));
  });

  it('T36: click Cancel on model edit → form closes, APIs NOT called', async () => {
    await setupModelEdit();
    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Edit' }));
    const form = screen.getByTestId('model-edit-form-um-1');
    fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByTestId('model-edit-form-um-1')).not.toBeInTheDocument();
    expect(patchUserModel).not.toHaveBeenCalled();
    expect(putUserModelTags).not.toHaveBeenCalled();
  });

  it('T37: opening Edit on model B while model A is open → only one form visible', async () => {
    const modelB = { ...openaiModel, user_model_id: 'um-2', alias: 'Slow', provider_model_name: 'gpt-4.1' };
    listProviders.mockResolvedValue({ items: [providerWithSecret] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [openaiModel, modelB] });
    renderSection();
    await screen.findByText('Fast');

    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Edit' }));
    expect(screen.getByTestId('model-edit-form-um-1')).toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId('model-row-um-2')).getByRole('button', { name: 'Edit' }));
    expect(screen.queryByTestId('model-edit-form-um-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('model-edit-form-um-2')).toBeInTheDocument();
  });

  it('T38: opening model Edit while provider Edit is open → provider form collapses', async () => {
    listProviders.mockResolvedValue({ items: [providerWithSecret] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [openaiModel] });
    renderSection();
    await screen.findByText('OpenAI Main');

    fireEvent.click(within(screen.getByTestId('provider-row-pc-1')).getByRole('button', { name: 'Edit' }));
    expect(screen.getByTestId('provider-edit-form-pc-1')).toBeInTheDocument();

    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Edit' }));
    expect(screen.queryByTestId('provider-edit-form-pc-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('model-edit-form-um-1')).toBeInTheDocument();
  });

  it('T39: click Delete on model → inline confirm shows model alias', async () => {
    await setupModelEdit();
    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Delete' }));
    const confirm = screen.getByTestId('model-delete-confirm-um-1');
    expect(within(confirm).getByText('Fast')).toBeInTheDocument();
    expect(within(confirm).getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
  });

  it('T40: click Confirm delete model → deleteUserModel called with correct ID', async () => {
    deleteUserModel.mockResolvedValueOnce(undefined);
    listProviders.mockResolvedValue({ items: [providerWithSecret] });
    listProviderInventory.mockResolvedValue({ items: [] });
    listUserModels.mockResolvedValue({ items: [openaiModel] });
    renderSection();
    await screen.findByText('Fast');

    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Delete' }));
    fireEvent.click(within(screen.getByTestId('model-delete-confirm-um-1')).getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(deleteUserModel).toHaveBeenCalledWith('token-1', 'um-1'));
  });

  it('T41: click Cancel on model delete confirm → deleteUserModel NOT called', async () => {
    await setupModelEdit();
    fireEvent.click(within(screen.getByTestId('model-row-um-1')).getByRole('button', { name: 'Delete' }));
    const confirm = screen.getByTestId('model-delete-confirm-um-1');
    fireEvent.click(within(confirm).getByRole('button', { name: 'Cancel' }));
    expect(deleteUserModel).not.toHaveBeenCalled();
  });
});
