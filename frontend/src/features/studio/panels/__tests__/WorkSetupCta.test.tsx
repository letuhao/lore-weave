// D0 — the Studio Work-creation CTA. Reuses useCreateWork + usePendingWorkResolver; must:
//  · create idempotently on click, · drive the backfill poll ONLY for a pending (null-project) Work,
//  · surface an error toast, never a silent stall, · offer retry when the poll gives up.
// Gate: the CTA appears ONLY on `no-work` (never `unavailable` — that would invite a DUPLICATE Work)
// and ONLY when bookId is threaded through.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => {
  const mutateAsync = vi.fn();
  return {
    mutateAsync,
    create: { mutateAsync, isPending: false },
    resolver: { state: 'idle' as 'idle' | 'resolving' | 'failed', start: vi.fn(), retry: vi.fn() },
    toastError: vi.fn(),
  };
});

vi.mock('@/features/composition/hooks/useWork', () => ({
  useCreateWork: () => mocks.create,
  usePendingWorkResolver: () => mocks.resolver,
}));
vi.mock('sonner', () => ({ toast: { error: mocks.toastError } }));

import { WorkSetupCta } from '../WorkSetupCta';
import { QualityWorkGate } from '../QualityNoWorkState';

beforeEach(() => {
  mocks.mutateAsync.mockReset();
  mocks.resolver.start.mockReset();
  mocks.resolver.retry.mockReset();
  mocks.resolver.state = 'idle';
  mocks.create.isPending = false;
  mocks.toastError.mockReset();
});

describe('WorkSetupCta', () => {
  it('creates a Work on click', async () => {
    mocks.mutateAsync.mockResolvedValue({ project_id: 'proj-1' });
    render(<WorkSetupCta bookId="b1" token="tok" />);
    fireEvent.click(screen.getByTestId('work-setup-cta'));
    await waitFor(() => expect(mocks.mutateAsync).toHaveBeenCalledTimes(1));
  });

  it('does NOT poll when the created Work is already project-backed', async () => {
    mocks.mutateAsync.mockResolvedValue({ project_id: 'proj-1', id: 'w1' });
    render(<WorkSetupCta bookId="b1" token="tok" />);
    fireEvent.click(screen.getByTestId('work-setup-cta'));
    await waitFor(() => expect(mocks.mutateAsync).toHaveBeenCalled());
    expect(mocks.resolver.start).not.toHaveBeenCalled();
  });

  it('drives the backfill poll for a PENDING (null-project) Work by its surrogate id', async () => {
    mocks.mutateAsync.mockResolvedValue({ project_id: null, id: 'w1' });
    render(<WorkSetupCta bookId="b1" token="tok" />);
    fireEvent.click(screen.getByTestId('work-setup-cta'));
    await waitFor(() => expect(mocks.resolver.start).toHaveBeenCalledWith('w1'));
  });

  it('surfaces an error toast when creation fails — never a silent stall', async () => {
    mocks.mutateAsync.mockRejectedValue(new Error('boom'));
    render(<WorkSetupCta bookId="b1" token="tok" />);
    fireEvent.click(screen.getByTestId('work-setup-cta'));
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled());
  });

  it('surfaces an error (never a silent no-op) when the created Work has neither a project nor an id', async () => {
    mocks.mutateAsync.mockResolvedValue({ project_id: null, id: null });
    render(<WorkSetupCta bookId="b1" token="tok" />);
    fireEvent.click(screen.getByTestId('work-setup-cta'));
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled());
    expect(mocks.resolver.start).not.toHaveBeenCalled();
  });

  it('disables the CTA when there is no auth token', () => {
    render(<WorkSetupCta bookId="b1" token={null} />);
    expect(screen.getByTestId('work-setup-cta')).toBeDisabled();
  });

  it('disables the CTA while a create/poll is in flight', () => {
    mocks.resolver.state = 'resolving';
    render(<WorkSetupCta bookId="b1" token="tok" />);
    expect(screen.getByTestId('work-setup-cta')).toBeDisabled();
  });

  it('offers retry when the backfill poll gave up', () => {
    mocks.resolver.state = 'failed';
    render(<WorkSetupCta bookId="b1" token="tok" />);
    expect(screen.getByTestId('work-setup-failed')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('work-setup-retry'));
    expect(mocks.resolver.retry).toHaveBeenCalledTimes(1);
  });
});

describe('QualityWorkGate — CTA placement', () => {
  it('offers the CTA on no-work when bookId is threaded', () => {
    render(<QualityWorkGate state={{ kind: 'no-work' }} testIdPrefix="q" bookId="b1" token="tok" />);
    expect(screen.getByTestId('work-setup-cta')).toBeInTheDocument();
  });

  it('does NOT offer the CTA on unavailable (would invite a duplicate Work)', () => {
    render(<QualityWorkGate state={{ kind: 'unavailable' }} testIdPrefix="q" bookId="b1" token="tok" />);
    expect(screen.queryByTestId('work-setup-cta')).toBeNull();
    expect(screen.getByTestId('q-unavailable')).toBeInTheDocument();
  });

  it('renders no-work without a CTA when bookId is absent (backward-compatible)', () => {
    render(<QualityWorkGate state={{ kind: 'no-work' }} testIdPrefix="q" />);
    expect(screen.getByTestId('q-no-work')).toBeInTheDocument();
    expect(screen.queryByTestId('work-setup-cta')).toBeNull();
  });
});
