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
  // 🔴 MISSING, and it took the whole file down with it: `DefaultModelsCard` renders a composer
  // row (`DefaultModelsCard.tsx:166`), so it imports `COMPOSER_CAPABILITY` from `./api`. A
  // `vi.mock` factory REPLACES the module wholesale, so a constant the factory forgets does not
  // fall back to the real one — it is simply undefined, and vitest fails the import with
  // "No COMPOSER_CAPABILITY export is defined on the ../api mock".
  //
  // Completed from the real value (`api.ts:113`) rather than invented, which is the point: a mock
  // that drifts from its module tests a module that does not exist. Third time this exact shape
  // has appeared in this repo — react-i18next missing `initReactI18next`, sonner missing `error`,
  // and now this.
  COMPOSER_CAPABILITY: 'composer',
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
    // FOUR rows, not three: chat, rerank, planner, composer — in that order
    // (`DefaultModelsCard.tsx` 119 / 134 / 148 / 166). The composer row was added to the
    // component and this count was left at 3, which is what actually failed here; the missing
    // mock constant above was only what stopped the file importing at all.
    //
    // Composer APPENDS, so every index this file already uses still points where it did — that
    // is checked against the component rather than assumed, because `openRow(0)` and `openRow(2)`
    // below would silently test the wrong row if a future row were inserted rather than appended.
    expect(triggers).toHaveLength(4);
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
