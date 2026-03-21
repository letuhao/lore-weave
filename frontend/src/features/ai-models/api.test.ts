import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiJson } from '@/api';
import { aiModelsApi } from './api';

vi.mock('@/api', () => ({
  apiJson: vi.fn(),
}));

describe('aiModelsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('delegates listProviders to apiJson with token', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({ items: [] });
    await aiModelsApi.listProviders('tok');
    expect(apiJson).toHaveBeenCalledWith('/v1/model-registry/providers', { token: 'tok' });
  });

  it('creates user model with JSON payload', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({
      user_model_id: 'um-1',
      provider_credential_id: 'pc-1',
      provider_kind: 'openai',
      provider_model_name: 'gpt-4o-mini',
      is_active: true,
      is_favorite: false,
      tags: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    await aiModelsApi.createUserModel('tok', {
      provider_credential_id: 'pc-1',
      provider_model_name: 'gpt-4o-mini',
      alias: 'Fast',
      tags: [{ tag_name: 'thinking', note: 'long-context' }],
    });
    expect(apiJson).toHaveBeenCalledWith('/v1/model-registry/user-models', {
      method: 'POST',
      token: 'tok',
      body: JSON.stringify({
        provider_credential_id: 'pc-1',
        provider_model_name: 'gpt-4o-mini',
        alias: 'Fast',
        tags: [{ tag_name: 'thinking', note: 'long-context' }],
      }),
    });
  });

  it('builds usage logs query params', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({ items: [], total: 0 });
    await aiModelsApi.listUsageLogs('tok', { limit: 10, offset: 5 });
    expect(apiJson).toHaveBeenCalledWith('/v1/model-billing/usage-logs?limit=10&offset=5', { token: 'tok' });
  });

  it('builds provider inventory refresh query param', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({ items: [] });
    await aiModelsApi.listProviderInventory('tok', 'pc-1', true);
    expect(apiJson).toHaveBeenCalledWith('/v1/model-registry/providers/pc-1/models?refresh=true', { token: 'tok' });
  });

  it('builds user model list filters', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({ items: [] });
    await aiModelsApi.listUserModels('tok', { only_favorites: true, include_inactive: false, provider_kind: 'openai' });
    expect(apiJson).toHaveBeenCalledWith(
      '/v1/model-registry/user-models?only_favorites=true&include_inactive=false&provider_kind=openai',
      { token: 'tok' },
    );
  });

  it('patches activation, favorite, and tags endpoints', async () => {
    vi.mocked(apiJson).mockResolvedValue({
      user_model_id: 'um-1',
      provider_credential_id: 'pc-1',
      provider_kind: 'openai',
      provider_model_name: 'gpt-4o-mini',
      is_active: true,
      is_favorite: false,
      tags: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    await aiModelsApi.patchUserModelActivation('tok', 'um-1', false);
    await aiModelsApi.patchUserModelFavorite('tok', 'um-1', true);
    await aiModelsApi.putUserModelTags('tok', 'um-1', [{ tag_name: 'tts', note: 'voice output' }]);

    expect(apiJson).toHaveBeenNthCalledWith(1, '/v1/model-registry/user-models/um-1/activation', {
      method: 'PATCH',
      token: 'tok',
      body: JSON.stringify({ is_active: false }),
    });
    expect(apiJson).toHaveBeenNthCalledWith(2, '/v1/model-registry/user-models/um-1/favorite', {
      method: 'PATCH',
      token: 'tok',
      body: JSON.stringify({ is_favorite: true }),
    });
    expect(apiJson).toHaveBeenNthCalledWith(3, '/v1/model-registry/user-models/um-1/tags', {
      method: 'PUT',
      token: 'tok',
      body: JSON.stringify({ tags: [{ tag_name: 'tts', note: 'voice output' }] }),
    });
  });

  it('calls usage summary/detail/account balance endpoints', async () => {
    vi.mocked(apiJson).mockResolvedValue({});

    await aiModelsApi.getUsageSummary('tok', 'last_7d');
    await aiModelsApi.getUsageLogDetail('tok', 'log-1');
    await aiModelsApi.getAccountBalance('tok');

    expect(apiJson).toHaveBeenNthCalledWith(1, '/v1/model-billing/usage-summary?period=last_7d', { token: 'tok' });
    expect(apiJson).toHaveBeenNthCalledWith(2, '/v1/model-billing/usage-logs/log-1', { token: 'tok' });
    expect(apiJson).toHaveBeenNthCalledWith(3, '/v1/model-billing/account-balance', { token: 'tok' });
  });

  it('propagates apiJson errors', async () => {
    const err = Object.assign(new Error('forbidden'), { status: 403, code: 'M03_LOG_DECRYPT_FORBIDDEN' });
    vi.mocked(apiJson).mockRejectedValueOnce(err);
    await expect(aiModelsApi.getUsageLogDetail('tok', 'log-2')).rejects.toMatchObject({
      message: 'forbidden',
      status: 403,
      code: 'M03_LOG_DECRYPT_FORBIDDEN',
    });
  });
});
