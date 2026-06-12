import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { MergeCandidate } from '../../types';

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const hookMocks = vi.hoisted(() => ({
  confirm: vi.fn(),
  dismiss: vi.fn(),
  undo: vi.fn(),
  state: { candidates: [] as unknown[], total: 0, isLoading: false, error: null as unknown },
}));
vi.mock('../../hooks/useMergeCandidates', () => ({
  useMergeCandidates: () => ({
    candidates: hookMocks.state.candidates,
    total: hookMocks.state.total,
    isLoading: hookMocks.state.isLoading,
    error: hookMocks.state.error,
    refetch: vi.fn(),
    confirm: hookMocks.confirm,
    dismiss: hookMocks.dismiss,
    undo: hookMocks.undo,
  }),
}));

import { MergeCandidatePanel } from '../MergeCandidatePanel';

const candidate = (): MergeCandidate => ({
  candidate_id: 'c1',
  kind_code: 'character',
  score: 0.82,
  rationale: 'coref cluster',
  evidence: [],
  suggested_winner_entity_id: 'g-jiang',
  status: 'proposed',
  created_at: '2026-06-07T00:00:00Z',
  members: [
    { entity_id: 'g-jiang', name: '姜子牙', aliases: ['子牙'], chapter_link_count: 50 },
    { entity_id: 'g-taigong', name: '太公望', aliases: [], chapter_link_count: 20 },
  ],
});

function renderPanel() {
  return render(<MergeCandidatePanel bookId="book-1" onClose={vi.fn()} />);
}

beforeEach(() => {
  hookMocks.confirm.mockReset().mockResolvedValue(['j1']);
  hookMocks.dismiss.mockReset().mockResolvedValue(undefined);
  hookMocks.undo.mockReset().mockResolvedValue(undefined);
  Object.values(toastMocks).forEach((m) => m.mockReset());
  hookMocks.state = { candidates: [candidate()], total: 1, isLoading: false, error: null };
});

describe('MergeCandidatePanel', () => {
  it('renders the cluster members', () => {
    renderPanel();
    expect(screen.getByText('姜子牙')).toBeInTheDocument();
    expect(screen.getByText('太公望')).toBeInTheDocument();
  });

  it('defaults the winner radio to the suggested winner', () => {
    renderPanel();
    expect(screen.getByTestId('merge-winner-g-jiang')).toBeChecked();
    expect(screen.getByTestId('merge-winner-g-taigong')).not.toBeChecked();
  });

  it('confirm merges into the default suggested winner + toasts', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('merge-confirm-c1'));
    await waitFor(() => expect(hookMocks.confirm).toHaveBeenCalledTimes(1));
    const [, winnerId] = hookMocks.confirm.mock.calls[0];
    expect(winnerId).toBe('g-jiang');
    expect(toastMocks.success).toHaveBeenCalled();
  });

  it('confirm respects a changed winner pick', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('merge-winner-g-taigong'));
    fireEvent.click(screen.getByTestId('merge-confirm-c1'));
    await waitFor(() => expect(hookMocks.confirm).toHaveBeenCalledTimes(1));
    expect(hookMocks.confirm.mock.calls[0][1]).toBe('g-taigong');
  });

  it('shows an info toast (not success) when nothing actually merged', async () => {
    // review-impl MED-1: all losers skipped/failed server-side → confirm
    // returns [] → must NOT claim a successful merge.
    hookMocks.confirm.mockResolvedValue([]);
    renderPanel();
    fireEvent.click(screen.getByTestId('merge-confirm-c1'));
    await waitFor(() => expect(hookMocks.confirm).toHaveBeenCalledTimes(1));
    expect(toastMocks.info).toHaveBeenCalledWith('merge_candidates.toast_none');
    expect(toastMocks.success).not.toHaveBeenCalled();
  });

  it('dismiss calls the dismiss action + toasts', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('merge-dismiss-c1'));
    await waitFor(() => expect(hookMocks.dismiss).toHaveBeenCalledTimes(1));
    expect(toastMocks.success).toHaveBeenCalled();
  });

  it('shows the empty state when there are no candidates', () => {
    hookMocks.state = { candidates: [], total: 0, isLoading: false, error: null };
    renderPanel();
    expect(screen.getByText('merge_candidates.empty_title')).toBeInTheDocument();
  });
});
