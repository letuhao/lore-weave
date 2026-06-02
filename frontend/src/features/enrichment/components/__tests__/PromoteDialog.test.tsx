import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PromoteDialog } from '../PromoteDialog';
import type { Proposal } from '../../types';

const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    canonical_name: '玉虛宮',
    target_ref: null,
    technique: 'recook',
    ...over,
  } as Proposal);

function setup(over: {
  proposal?: Proposal | null;
  open?: boolean;
  busy?: boolean;
} = {}) {
  const onOpenChange = vi.fn();
  const onConfirm = vi.fn();
  render(
    <PromoteDialog
      proposal={over.proposal === undefined ? P() : over.proposal}
      open={over.open ?? true}
      busy={over.busy}
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
    />,
  );
  return { onOpenChange, onConfirm };
}

beforeEach(() => vi.clearAllMocks());

describe('PromoteDialog', () => {
  it('open=false: the dialog content is not rendered', () => {
    setup({ open: false });
    expect(screen.queryByTestId('enrichment-promote-dialog')).toBeNull();
  });

  it('open=true: renders the dialog with the proposal name + the H0 / responsibility copy', () => {
    setup({ open: true });
    expect(screen.getByTestId('enrichment-promote-dialog')).toBeInTheDocument();
    expect(screen.getByText('玉虛宮')).toBeInTheDocument();
    expect(screen.getByText('promote.h0')).toBeInTheDocument();
    expect(screen.getByText('promote.responsibility')).toBeInTheDocument();
  });

  it('falls back to target_ref when there is no canonical_name', () => {
    setup({ proposal: P({ canonical_name: null, target_ref: '哪吒' }) });
    expect(screen.getByText('哪吒')).toBeInTheDocument();
  });

  it('clicking the confirm button fires onConfirm', () => {
    const { onConfirm } = setup({ open: true });
    fireEvent.click(screen.getByTestId('enrichment-promote-confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('not busy: the confirm button shows the confirm label and is enabled', () => {
    setup({ open: true, busy: false });
    const confirm = screen.getByTestId('enrichment-promote-confirm');
    expect(confirm).toHaveTextContent('promote.confirm');
    expect(confirm).not.toBeDisabled();
  });

  it('busy: the confirm button shows the promoting label and is disabled', () => {
    setup({ open: true, busy: true });
    const confirm = screen.getByTestId('enrichment-promote-confirm');
    expect(confirm).toHaveTextContent('promote.promoting');
    expect(confirm).toBeDisabled();
  });
});
