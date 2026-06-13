import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

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
    render(
      <MemoryRouter>
        <RerankModelPicker value={null} onChange={onChange} />
      </MemoryRouter>,
    );
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
    render(
      <MemoryRouter>
        <RerankModelPicker value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    const [, opts] = listUserModelsMock.mock.calls[0] as [string, { capability: string }];
    expect(opts.capability).toBe(RERANK_CAPABILITY);
  });

  it('selecting None clears the model (rerank optional → onChange null)', async () => {
    listUserModelsMock.mockResolvedValue({ items: [RERANK_MODEL] });
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <RerankModelPicker value="rr1" onChange={onChange} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(listUserModelsMock).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('shows the empty-state when the user has no rerank-capable models', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(
      <MemoryRouter>
        <RerankModelPicker value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await screen.findByText(/projects\.form\.rerankModelEmpty/);
  });

  // C1 (BL-1) — the "0 found" empty-state must point at the now-available
  // register path (C0 AddModelCta deep-links to /settings/providers + carries a
  // return) so a user who has no rerank model can register one in-flow, not hit
  // a dead text. Distinguishes a genuine zero-result from loading (CTA only
  // renders after the fetch resolves to an empty list).
  it('renders the AddModelCta register link in the empty-state (BL-1)', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(
      <MemoryRouter>
        <RerankModelPicker value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    const cta = await screen.findByRole('link');
    expect(cta.getAttribute('href')).toContain('/settings/providers');
    expect(cta.getAttribute('href')).toContain('return=');
  });

  it('does NOT show the empty-state CTA while still loading (no false empty)', async () => {
    // Pending (unresolved) fetch → component stays in loading; the empty-state +
    // CTA gate on models !== null, so neither should render yet. Use a CONTROLLED
    // deferred (resolve it before the test ends) — a never-resolving promise
    // wedges vitest teardown.
    let resolveFetch: (v: { items: never[] }) => void = () => {};
    listUserModelsMock.mockReturnValue(
      new Promise<{ items: never[] }>((res) => {
        resolveFetch = res;
      }),
    );
    render(
      <MemoryRouter>
        <RerankModelPicker value={null} onChange={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/projects\.form\.rerankModelEmpty/)).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();
    // settle so the env can tear down cleanly
    resolveFetch({ items: [] });
    await waitFor(() => expect(screen.queryByRole('link')).not.toBeNull());
  });

  it('renders an orphan option when the saved model left the registry', async () => {
    listUserModelsMock.mockResolvedValue({ items: [] });
    render(
      <MemoryRouter>
        <RerankModelPicker value="gone-uuid" onChange={vi.fn()} />
      </MemoryRouter>,
    );
    await screen.findByText(/projects\.form\.rerankModelOrphan/);
  });
});
