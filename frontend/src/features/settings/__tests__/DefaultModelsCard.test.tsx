import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/shared/AddModelCta', () => ({ AddModelCta: () => null }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

const listUserModels = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: (...a: unknown[]) => listUserModels(...a),
      patchFavorite: vi.fn(),
    },
  };
});

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
import { invalidateUserModelsCache } from '@/components/model-picker';

beforeEach(() => {
  listUserModels.mockReset();
  getDefaults.mockReset();
  setDefault.mockReset();
  localStorage.clear();
  invalidateUserModelsCache();
  listUserModels.mockResolvedValue({
    items: [
      { user_model_id: 'm1', provider_kind: 'lm_studio', provider_model_name: 'bge-reranker', alias: null, is_active: true, is_favorite: false, tags: [], created_at: '2026-01-01T00:00:00Z' },
    ],
  });
  getDefaults.mockResolvedValue({ defaults: {} });
  setDefault.mockResolvedValue({});
});

// Rows render the shared ModelPicker (W5): [0] chat, [1] rerank, [2] planner.
async function openRow(index: number) {
  const triggers = await screen.findAllByRole('combobox');
  fireEvent.click(triggers[index]);
  return triggers[index];
}

describe('DefaultModelsCard', () => {
  it('lists chat + rerank + planner models and persists a selected default', async () => {
    render(<DefaultModelsCard />);
    await waitFor(() => expect(listUserModels).toHaveBeenCalledWith('tok', { capability: 'rerank', include_inactive: false }));
    // Chat row (W5) + planner (a role with no model flag → lists CHAT models);
    // the shared fetch cache dedupes the two identical chat queries.
    await waitFor(() => expect(listUserModels).toHaveBeenCalledWith('tok', { capability: 'chat', include_inactive: false }));
    // Embedding is intentionally not exposed yet (no consumer) → never queried.
    expect(listUserModels).not.toHaveBeenCalledWith('tok', { capability: 'embedding', include_inactive: false });

    const triggers = await screen.findAllByRole('combobox');
    expect(triggers).toHaveLength(3);
    // Row [1] = rerank: open + pick the model.
    fireEvent.click(triggers[1]);
    fireEvent.click(await screen.findByText('bge-reranker'));
    await waitFor(() => expect(setDefault).toHaveBeenCalledWith('tok', 'rerank', 'm1'));
  });

  it('persists a planner default under the planner capability', async () => {
    render(<DefaultModelsCard />);
    await openRow(2);
    fireEvent.click(await screen.findByText('bge-reranker'));
    await waitFor(() => expect(setDefault).toHaveBeenCalledWith('tok', 'planner', 'm1'));
  });

  it('persists a chat default under the chat capability (W5 new row)', async () => {
    render(<DefaultModelsCard />);
    await openRow(0);
    fireEvent.click(await screen.findByText('bge-reranker'));
    await waitFor(() => expect(setDefault).toHaveBeenCalledWith('tok', 'chat', 'm1'));
  });

  it('preloads the existing defaults from the server (trigger shows the model)', async () => {
    getDefaults.mockResolvedValue({ defaults: { rerank: 'm1', planner: 'm1' } });
    render(<DefaultModelsCard />);
    await waitFor(() => {
      const triggers = screen.getAllByRole('combobox');
      expect(triggers[1]).toHaveTextContent('bge-reranker');
      expect(triggers[2]).toHaveTextContent('bge-reranker');
    });
  });

  it('clearing via the none option persists null', async () => {
    getDefaults.mockResolvedValue({ defaults: { rerank: 'm1' } });
    render(<DefaultModelsCard />);
    await waitFor(() => expect(screen.getAllByRole('combobox')[1]).toHaveTextContent('bge-reranker'));
    await openRow(1);
    // "defaultModels.none" also renders as the other (unset) rows' trigger label
    // — target the listbox OPTION specifically.
    fireEvent.click(await screen.findByRole('option', { name: 'defaultModels.none' }));
    await waitFor(() => expect(setDefault).toHaveBeenCalledWith('tok', 'rerank', null));
  });
});
