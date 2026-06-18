import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/shared/AddModelCta', () => ({ AddModelCta: () => null }));

const listUserModels = vi.fn();
vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: { listUserModels: (...a: unknown[]) => listUserModels(...a) },
}));

const getDefaults = vi.fn();
const setDefault = vi.fn();
vi.mock('../api', () => ({
  RERANK_CAPABILITY: 'rerank',
  EMBEDDING_CAPABILITY: 'embedding',
  defaultModelsApi: {
    get: (...a: unknown[]) => getDefaults(...a),
    set: (...a: unknown[]) => setDefault(...a),
  },
}));

import { DefaultModelsCard } from '../DefaultModelsCard';

beforeEach(() => {
  listUserModels.mockReset();
  getDefaults.mockReset();
  setDefault.mockReset();
  listUserModels.mockResolvedValue({
    items: [
      { user_model_id: 'm1', provider_kind: 'lm_studio', provider_model_name: 'bge-reranker', alias: null, is_active: true },
    ],
  });
  getDefaults.mockResolvedValue({ defaults: {} });
  setDefault.mockResolvedValue({});
});

describe('DefaultModelsCard', () => {
  it('lists rerank models and persists a selected default', async () => {
    render(<DefaultModelsCard />);
    await waitFor(() => expect(listUserModels).toHaveBeenCalledWith('tok', { capability: 'rerank', include_inactive: false }));
    // Embedding is intentionally not exposed yet (no consumer) → never queried.
    expect(listUserModels).not.toHaveBeenCalledWith('tok', { capability: 'embedding', include_inactive: false });

    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: 'm1' } });

    await waitFor(() => expect(setDefault).toHaveBeenCalledWith('tok', 'rerank', 'm1'));
  });

  it('preloads the existing rerank default from the server', async () => {
    getDefaults.mockResolvedValue({ defaults: { rerank: 'm1' } });
    render(<DefaultModelsCard />);
    await waitFor(() => {
      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('m1');
    });
  });
});
