import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CriticPanel } from '../CriticPanel';
import type { CriticVerdict } from '../../context/CriticStateContext';

// Mock the shared store + the (optional) live stream + the critique hook so the
// panel can be exercised in isolation (mirrors ComposeView.test's harness).
const { mockShared, mockStream, mockCritique } = vi.hoisted(() => ({
  mockShared: { verdict: null as CriticVerdict | null, setVerdict: vi.fn() },
  mockStream: { value: null as null | { jobId: string | null; ghost: string } },
  mockCritique: {
    critique: { mutate: vi.fn(), data: undefined as unknown, isPending: false },
    dismiss: { mutate: vi.fn() },
  },
}));
vi.mock('../../context/CriticStateContext', () => ({ useCriticStateOptional: () => mockShared }));
vi.mock('../../context/LiveStateContext', () => ({ useLiveStreamOptional: () => mockStream.value }));
vi.mock('../../hooks/useCritique', () => ({ useCritique: () => mockCritique }));

beforeEach(() => {
  vi.clearAllMocks();
  mockShared.verdict = null;
  mockStream.value = null;
  mockCritique.critique.data = undefined;
  mockCritique.critique.isPending = false;
});

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CriticPanel token="tok" />
    </QueryClientProvider>,
  );
}

describe('CriticPanel (WS-B1 — standing continuity critic)', () => {
  it('renders the shared verdict (critic dimensions) from the store', () => {
    mockShared.verdict = {
      critic: { coherence: 8, voice_match: 7, pacing: 6, canon_consistency: 9, violations: [] },
      canon: null,
      jobId: 'job-1',
    };
    renderPanel();
    // The extracted CriticFlags renders the dimension chips.
    expect(screen.getByTestId('compose-critic')).toBeTruthy();
    expect(screen.getByText(/coherence/)).toBeTruthy();
    expect(screen.queryByTestId('critic-empty')).toBeNull();
  });

  it('shows the empty state when there is no verdict and no jobId', () => {
    renderPanel();
    expect(screen.getByTestId('critic-empty')).toBeTruthy();
    expect(screen.queryByTestId('compose-critic')).toBeNull();
  });

  it('disables "re-check" when there is no live ghost to re-critique', () => {
    mockStream.value = { jobId: 'job-1', ghost: '' };
    renderPanel();
    expect(screen.getByTestId('critic-recheck').hasAttribute('disabled')).toBe(true);
  });

  it('enables "re-check" and runs the critique on the current ghost', () => {
    mockStream.value = { jobId: 'job-9', ghost: 'a live draft to re-check' };
    renderPanel();
    const btn = screen.getByTestId('critic-recheck') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    btn.click();
    expect(mockCritique.critique.mutate).toHaveBeenCalledWith({ jobId: 'job-9', passage: 'a live draft to re-check' });
  });
});
