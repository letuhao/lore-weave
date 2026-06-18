import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// C3 (BL-10) — the EditModelModal "Test" action for a rerank model renders the
// real /v1/rerank result (ranked-docs + top score), not just a generic OK. The
// global i18n mock returns the KEY with {{vars}} interpolated, so we assert the
// rerank-specific key surfaces.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test', user: { user_id: 'u1' } }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const verifyUserModelMock = vi.fn();
vi.mock('../api', async (orig) => {
  const actual = await orig<typeof import('../api')>();
  return {
    ...actual,
    providerApi: { ...actual.providerApi, verifyUserModel: (...a: unknown[]) => verifyUserModelMock(...a) },
  };
});

import { EditModelModal } from '../EditModelModal';

const RERANK_MODEL = {
  user_model_id: 'rr1',
  provider_credential_id: 'pc1',
  provider_kind: 'rerank_local',
  provider_model_name: 'bge-reranker-v2-m3',
  context_length: null,
  alias: 'My Reranker',
  is_active: true,
  is_favorite: false,
  capability_flags: { rerank: true },
  tags: [],
  notes: '',
} as never;

describe('EditModelModal rerank Test (C3)', () => {
  beforeEach(() => verifyUserModelMock.mockReset());

  it('renders ranked scores when a rerank model is tested', async () => {
    verifyUserModelMock.mockResolvedValue({
      verified: true,
      latency_ms: 12,
      capability: 'rerank',
      scores: [
        { index: 1, relevance_score: 0.95 },
        { index: 2, relevance_score: 0.4 },
        { index: 0, relevance_score: 0.02 },
      ],
      top_index: 1,
      top_score: 0.95,
    });
    render(<EditModelModal model={RERANK_MODEL} onClose={() => {}} onUpdated={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'model_modal.edit.verify' }));
    // rerank-specific result key (NOT the generic verify_ok) — interpolated count survives
    await waitFor(() =>
      expect(screen.getByText(/model_modal\.edit\.verify_ok_rerank/)).toBeInTheDocument(),
    );
    expect(verifyUserModelMock).toHaveBeenCalledWith('tok-test', 'rr1');
  });

  it('falls back to the generic OK text for a non-rerank model', async () => {
    verifyUserModelMock.mockResolvedValue({ verified: true, latency_ms: 8, capability: 'chat' });
    render(<EditModelModal model={{ ...RERANK_MODEL, capability_flags: { chat: true } } as never} onClose={() => {}} onUpdated={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'model_modal.edit.verify' }));
    await waitFor(() =>
      expect(screen.getByText(/model_modal\.edit\.verify_ok($|[^_])/)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/verify_ok_rerank/)).toBeNull();
  });
});
