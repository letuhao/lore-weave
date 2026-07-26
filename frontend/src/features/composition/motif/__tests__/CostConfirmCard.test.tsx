// W6 §7.1 — CostConfirmCard: shows the $ estimate; Confirm disables while pending
// (no double-spend); Cancel works.
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CostConfirmCard } from '../components/CostConfirmCard';
import type { CostEstimate } from '../types';

const est: CostEstimate = {
  confirm_token: 'tok', descriptor: 'composition.conformance_run',
  est_usd: 0.0234, est_tokens: 1200, quota_remaining: 49,
};

describe('CostConfirmCard', () => {
  it('renders the $ estimate + token count + quota', () => {
    render(<CostConfirmCard estimate={est} whatItDoes="do thing" confirming={false} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('motif-cost-usd').textContent).toBe('$0.02');
    expect(screen.getByText('1,200')).toBeInTheDocument();
    expect(screen.getByText('49')).toBeInTheDocument();
  });

  it('Confirm fires the callback; disabled while confirming (no double-spend)', () => {
    const onConfirm = vi.fn();
    const { rerender } = render(<CostConfirmCard estimate={est} whatItDoes="x" confirming={false} onConfirm={onConfirm} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('motif-cost-confirm-btn'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    // re-render in the pending state → the button is disabled (idempotency guard)
    rerender(<CostConfirmCard estimate={est} whatItDoes="x" confirming onConfirm={onConfirm} onCancel={vi.fn()} />);
    expect(screen.getByTestId('motif-cost-confirm-btn')).toBeDisabled();
  });

  it('Cancel fires the callback', () => {
    const onCancel = vi.fn();
    render(<CostConfirmCard estimate={est} whatItDoes="x" confirming={false} onConfirm={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByTestId('motif-cost-cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
