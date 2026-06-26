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
  PLANNER_CAPABILITY: 'planner',
  CHAT_CAPABILITY: 'chat',
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
  it('lists rerank + planner models and persists a selected default', async () => {
    render(<DefaultModelsCard />);
    await waitFor(() => expect(listUserModels).toHaveBeenCalledWith('tok', { capability: 'rerank', include_inactive: false }));
    // Planner is a role with no model flag → it lists CHAT models.
    await waitFor(() => expect(listUserModels).toHaveBeenCalledWith('tok', { capability: 'chat', include_inactive: false }));
    // Embedding is intentionally not exposed yet (no consumer) → never queried.
    expect(listUserModels).not.toHaveBeenCalledWith('tok', { capability: 'embedding', include_inactive: false });

    // Two rows now: [0] rerank, [1] planner.
    const selects = await screen.findAllByRole('combobox');
    expect(selects).toHaveLength(2);
    fireEvent.change(selects[0], { target: { value: 'm1' } });
    await waitFor(() => expect(setDefault).toHaveBeenCalledWith('tok', 'rerank', 'm1'));
  });

  it('persists a planner default under the planner capability', async () => {
    render(<DefaultModelsCard />);
    const selects = await screen.findAllByRole('combobox');
    fireEvent.change(selects[1], { target: { value: 'm1' } });
    await waitFor(() => expect(setDefault).toHaveBeenCalledWith('tok', 'planner', 'm1'));
  });

  it('preloads the existing rerank + planner defaults from the server', async () => {
    getDefaults.mockResolvedValue({ defaults: { rerank: 'm1', planner: 'm1' } });
    render(<DefaultModelsCard />);
    await waitFor(() => {
      const selects = screen.getAllByRole('combobox') as HTMLSelectElement[];
      expect(selects[0].value).toBe('m1');
      expect(selects[1].value).toBe('m1');
    });
  });
});
