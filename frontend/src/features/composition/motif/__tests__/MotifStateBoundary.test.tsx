// W6 §7.1 — MotifStateBoundary state-matrix + MotifEmptyState forward-action.
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MotifStateBoundary } from '../components/MotifStateBoundary';
import { MotifEmptyState } from '../components/MotifEmptyState';

describe('MotifStateBoundary', () => {
  it('loading → skeleton (children not shown)', () => {
    render(<MotifStateBoundary isLoading skeleton="cards"><div>body</div></MotifStateBoundary>);
    expect(screen.getByTestId('motif-state-loading')).toBeInTheDocument();
    expect(screen.queryByText('body')).toBeNull();
  });

  it('error → retry banner with a forward action', () => {
    const onRetry = vi.fn();
    render(<MotifStateBoundary isError onRetry={onRetry}><div>body</div></MotifStateBoundary>);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('motif-state-retry'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('permission-locked → read-only lock + "Clone to edit" (the kinds-bug lesson)', () => {
    const onClone = vi.fn();
    render(<MotifStateBoundary permissionLocked onClone={onClone}><div>body</div></MotifStateBoundary>);
    expect(screen.getByTestId('motif-state-locked')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('motif-state-clone'));
    expect(onClone).toHaveBeenCalledTimes(1);
  });

  it('happy path → renders children', () => {
    render(<MotifStateBoundary><div data-testid="ok">body</div></MotifStateBoundary>);
    expect(screen.getByTestId('ok')).toBeInTheDocument();
  });
});

describe('MotifEmptyState (load-bearing first-run)', () => {
  it('reassures the seeds are present + offers two forward doors (never a dead end)', () => {
    const onNew = vi.fn();
    const onBrowse = vi.fn();
    render(<MotifEmptyState onNewMotif={onNew} onBrowseSystem={onBrowse} />);
    expect(screen.getByTestId('motif-empty')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('motif-empty-new'));
    fireEvent.click(screen.getByTestId('motif-empty-browse'));
    expect(onNew).toHaveBeenCalledTimes(1);
    expect(onBrowse).toHaveBeenCalledTimes(1);
  });
});
