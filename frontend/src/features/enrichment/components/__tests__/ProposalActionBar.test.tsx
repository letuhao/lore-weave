import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProposalActionBar } from '../ProposalActionBar';
import type { Proposal } from '../../types';

const P = (review_status: string): Proposal => ({ review_status } as Proposal);

function setup(review_status: string, busy = false) {
  const handlers = {
    onPromote: vi.fn(),
    onApprove: vi.fn(),
    onReject: vi.fn(),
    onEdit: vi.fn(),
    onRetract: vi.fn(),
  };
  render(<ProposalActionBar proposal={P(review_status)} busy={busy} {...handlers} />);
  return handlers;
}

beforeEach(() => vi.clearAllMocks());

describe('ProposalActionBar', () => {
  it('promoted: shows the promoted note + a Retract button that fires onRetract', () => {
    const h = setup('promoted');
    expect(screen.getByText('actions.already_promoted')).toBeInTheDocument();
    expect(screen.queryByTestId('enrichment-promote-trigger')).toBeNull();
    fireEvent.click(screen.getByTestId('enrichment-retract-trigger'));
    expect(h.onRetract).toHaveBeenCalledTimes(1);
  });

  it('rejected: shows the rejected note and no action buttons', () => {
    setup('rejected');
    expect(screen.getByText('actions.rejected_note')).toBeInTheDocument();
    expect(screen.queryByTestId('enrichment-promote-trigger')).toBeNull();
    expect(screen.queryByTestId('enrichment-retract-trigger')).toBeNull();
  });

  it('proposed: shows Promote + Approve + Edit + Reject', () => {
    setup('proposed');
    expect(screen.getByTestId('enrichment-promote-trigger')).toBeInTheDocument();
    expect(screen.getByText('actions.approve')).toBeInTheDocument();
    expect(screen.getByText('actions.edit')).toBeInTheDocument();
    expect(screen.getByText('actions.reject')).toBeInTheDocument();
  });

  it('approved: hides Approve but still shows Promote', () => {
    setup('approved');
    expect(screen.getByTestId('enrichment-promote-trigger')).toBeInTheDocument();
    expect(screen.queryByText('actions.approve')).toBeNull();
  });

  it('Promote / Approve / Edit fire their callbacks', () => {
    const h = setup('proposed');
    fireEvent.click(screen.getByTestId('enrichment-promote-trigger'));
    fireEvent.click(screen.getByText('actions.approve'));
    fireEvent.click(screen.getByText('actions.edit'));
    expect(h.onPromote).toHaveBeenCalledTimes(1);
    expect(h.onApprove).toHaveBeenCalledTimes(1);
    expect(h.onEdit).toHaveBeenCalledTimes(1);
  });

  it('Reject opens a reason form; confirming forwards the trimmed reason', () => {
    const h = setup('proposed');
    fireEvent.click(screen.getByText('actions.reject'));
    expect(screen.getByTestId('enrichment-reject-form')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('enrichment-reject-reason'), {
      target: { value: '  off-canon  ' },
    });
    fireEvent.click(screen.getByTestId('enrichment-reject-confirm'));
    expect(h.onReject).toHaveBeenCalledWith('off-canon');
  });

  it('Reject with an empty reason forwards undefined', () => {
    const h = setup('proposed');
    fireEvent.click(screen.getByText('actions.reject'));
    fireEvent.click(screen.getByTestId('enrichment-reject-confirm'));
    expect(h.onReject).toHaveBeenCalledWith(undefined);
  });

  it('Reject form Cancel returns to the action buttons without rejecting', () => {
    const h = setup('proposed');
    fireEvent.click(screen.getByText('actions.reject'));
    fireEvent.click(screen.getByText('actions.cancel'));
    expect(screen.queryByTestId('enrichment-reject-form')).toBeNull();
    expect(screen.getByTestId('enrichment-promote-trigger')).toBeInTheDocument();
    expect(h.onReject).not.toHaveBeenCalled();
  });

  it('busy disables the primary actions', () => {
    setup('proposed', true);
    expect(screen.getByTestId('enrichment-promote-trigger')).toBeDisabled();
  });
});
