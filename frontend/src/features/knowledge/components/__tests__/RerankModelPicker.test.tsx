import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// D-RERANK-NOT-BYOK (S0b) — the rerank model picker: fetches the user's
// rerank-capability BYOK models and binds the project's rerank_model
// (user_model_id UUID). Rerank is OPTIONAL — empty selection ⇒ null.

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const listUserModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: {
    listUserModels: (...args: unknown[]) => listUserModelsMock(...args),
  },
}));

import { RerankModelPicker } from '../RerankModelPicker';
import { RERANK_CAPABILITY } from '@/features/settings/api';

const RERANK_MODEL = {
  user_model_id: 'rr1',
  provider_kind: 'cohere',
  provider_model_name: 'rerank-v3',
  alias: null,
};

describe('RerankModelPicker (D-RERANK-NOT-BYOK S0b)', () => {
  beforeEach(() => listUserModelsMock.mockReset());

  it('fetches rerank-CAPABILITY models and binds the chosen user_model_id', async () => {
    listUserModelsMock.mockResolvedValue({ items: [RERANK_MODEL] });
    const onChange = vi.fn();
    render(<RerankModelPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    // BYOK + capability-scoped — never a hardcoded model name.
    expect(listUserModelsMock).toHaveBeenCalledWith('tok-test', {
      capability: RERANK_CAPABILITY,
      include_inactive: false,
    });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'rr1' } });
    expect(onChange).toHaveBeenCalledWith('rr1');
  });

  // C0 rerank/reranker reconcile (BL-1) — spy-injection wiring guard. The picker
  // MUST filter on the SAME canonical token the rest of the platform uses; if a
  // future edit swaps the picker back to a divergent literal (e.g. 'reranker'),
  // the spy argument no longer equals RERANK_CAPABILITY and this fails — the
  // wire can't be silently dropped (nil-tolerant-wiring lesson).
  it('filters on the canonical RERANK_CAPABILITY token (not a divergent literal)', async () => {
    // The canonical value must be exactly what provider-registry tags rerank
    // models with and what RerankModelPicker/ModelRolePicker resolve.
    expect(RERANK_CAPABILITY).toBe('rerank');
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(<RerankModelPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    const [, opts] = listUserModelsMock.mock.calls[0] as [string, { capability: string }];
    expect(opts.capability).toBe(RERANK_CAPABILITY);
  });

  it('selecting None clears the model (rerank optional → onChange null)', async () => {
    listUserModelsMock.mockResolvedValue({ items: [RERANK_MODEL] });
    const onChange = vi.fn();
    render(<RerankModelPicker value="rr1" onChange={onChange} />);
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('shows the empty-state when the user has no rerank-capable models', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(<RerankModelPicker value={null} onChange={vi.fn()} />);
    await screen.findByText(/projects\.form\.rerankModelEmpty/);
  });

  it('renders an orphan option when the saved model left the registry', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(<RerankModelPicker value="gone-uuid" onChange={vi.fn()} />);
    await screen.findByText(/projects\.form\.rerankModelOrphan/);
  });
});
