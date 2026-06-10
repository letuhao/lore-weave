import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ModelRolePicker } from '../ModelRolePicker';
import { aiModelsApi } from '../../../ai-models/api';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../../ai-models/api', () => ({ aiModelsApi: { listUserModels: vi.fn() } }));

const M1 = {
  user_model_id: 'm1', provider_credential_id: 'c1', provider_kind: 'openai',
  provider_model_name: 'gpt-4o', alias: 'My GPT', is_active: true, is_favorite: false,
  tags: [], created_at: '',
};

describe('ModelRolePicker', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists the user models for the given capability', async () => {
    (aiModelsApi.listUserModels as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [M1] });
    render(<ModelRolePicker capability="chat" label="Translator" value={null} onChange={() => {}} />);
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'My GPT (gpt-4o)' })).toBeInTheDocument());
    expect(aiModelsApi.listUserModels).toHaveBeenCalledWith('tok', { capability: 'chat', include_inactive: false });
  });

  it('renders a synthetic orphan option when the value is not in the fetched list', async () => {
    // value points at a model the registry no longer returns → must still show the truth,
    // not silently fall back to "None".
    (aiModelsApi.listUserModels as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [M1] });
    render(<ModelRolePicker capability="chat" label="Translator" value="deleted-model" onChange={() => {}} />);
    await waitFor(() => expect(screen.getByText('matrix.orphan')).toBeInTheDocument());
  });
});
