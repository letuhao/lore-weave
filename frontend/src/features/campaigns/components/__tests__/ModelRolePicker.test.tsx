import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ModelRolePicker } from '../ModelRolePicker';
import { aiModelsApi } from '../../../ai-models/api';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../../ai-models/api', () => ({ aiModelsApi: { listUserModels: vi.fn() } }));

const M1 = {
  user_model_id: 'm1', provider_credential_id: 'c1', provider_kind: 'openai',
  provider_model_name: 'gpt-4o', alias: 'My GPT', is_active: true, is_favorite: false,
  tags: [], created_at: '',
};

// Fresh client per render so the per-capability cache doesn't leak across tests.
function renderPicker(props: Partial<Parameters<typeof ModelRolePicker>[0]> = {}) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ModelRolePicker capability="chat" label="Translator" value={null} onChange={() => {}} {...props} />
    </QueryClientProvider>,
  );
}

describe('ModelRolePicker', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists the user models for the given capability', async () => {
    (aiModelsApi.listUserModels as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [M1] });
    renderPicker();
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'My GPT (gpt-4o)' })).toBeInTheDocument());
    expect(aiModelsApi.listUserModels).toHaveBeenCalledWith('tok', { capability: 'chat', include_inactive: false });
  });

  it('renders a synthetic orphan option when the value is not in the fetched list', async () => {
    // value points at a model the registry no longer returns → must still show the truth,
    // not silently fall back to "None".
    (aiModelsApi.listUserModels as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [M1] });
    renderPicker({ value: 'deleted-model' });
    await waitFor(() => expect(screen.getByText('matrix.orphan')).toBeInTheDocument());
  });

  it('D-S5C-PICKER-DEDUP: two pickers of the same capability share ONE fetch', async () => {
    (aiModelsApi.listUserModels as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [M1] });
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <ModelRolePicker capability="chat" label="Translator" value={null} onChange={() => {}} />
        <ModelRolePicker capability="chat" label="Verifier" value={null} onChange={() => {}} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getAllByRole('option', { name: 'My GPT (gpt-4o)' })).toHaveLength(2));
    // react-query dedups the identical ['campaign-byok-models','chat'] key → one request.
    expect(aiModelsApi.listUserModels).toHaveBeenCalledTimes(1);
  });
});
