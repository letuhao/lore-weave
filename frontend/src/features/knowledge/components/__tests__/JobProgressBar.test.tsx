import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { JobProgressBar } from '../JobProgressBar';
import type { ExtractionJobStatus } from '../../types/projectState';

function props(overrides: {
  status?: ExtractionJobStatus;
  itemsProcessed?: number;
  itemsTotal?: number | null;
  costSpentUsd?: string;
  maxSpendUsd?: string | null;
} = {}) {
  return {
    status: overrides.status ?? ('running' as ExtractionJobStatus),
    itemsProcessed: overrides.itemsProcessed ?? 0,
    itemsTotal: overrides.itemsTotal === undefined ? 10 : overrides.itemsTotal,
    costSpentUsd: overrides.costSpentUsd ?? '0.00',
    maxSpendUsd: overrides.maxSpendUsd === undefined ? '5.00' : overrides.maxSpendUsd,
  };
}

describe('JobProgressBar', () => {
  it('renders correct percentage from items_processed / items_total', () => {
    render(<JobProgressBar {...props({ itemsProcessed: 3, itemsTotal: 10 })} />);
    const bar = screen.getByTestId('job-progress-bar');
    expect(bar.getAttribute('aria-valuenow')).toBe('30');
  });

  it('forces 100% when status=complete regardless of items', () => {
    render(
      <JobProgressBar
        {...props({ status: 'complete', itemsProcessed: 3, itemsTotal: 10 })}
      />,
    );
    const bar = screen.getByTestId('job-progress-bar');
    expect(bar.getAttribute('aria-valuenow')).toBe('100');
  });

  it('renders indeterminate shimmer when items_total is null and status is active', () => {
    render(
      <JobProgressBar {...props({ status: 'running', itemsTotal: null })} />,
    );
    expect(screen.queryByTestId('job-progress-indeterminate')).toBeInTheDocument();
    expect(screen.getByText(/0 \/ —/)).toBeInTheDocument();
  });

  it('omits the max-spend suffix when max_spend_usd is null (unlimited budget)', () => {
    render(
      <JobProgressBar {...props({ costSpentUsd: '1.25', maxSpendUsd: null })} />,
    );
    const cost = screen.getByTestId('job-progress-cost');
    expect(cost.textContent).toBe('$1.25');
    expect(cost.textContent).not.toContain('/');
  });

  it('formats large costs with locale grouping via Intl.NumberFormat', () => {
    render(
      <JobProgressBar
        {...props({ costSpentUsd: '1234.5', maxSpendUsd: '10000' })}
      />,
    );
    const cost = screen.getByTestId('job-progress-cost');
    // Node's default ICU delivers "$1,234.50 / $10,000.00" (en-US locale);
    // the exact glyph for the grouping separator is locale-dependent, so
    // we just assert structural markers instead of the literal chars.
    expect(cost.textContent).toContain('$1');
    expect(cost.textContent).toContain('1,234');
    expect(cost.textContent).toContain('10,000');
    expect(cost.textContent).toContain('/');
  });

  it('renders aria-label with progress percent for determinate bars', () => {
    render(
      <JobProgressBar {...props({ itemsProcessed: 3, itemsTotal: 10 })} />,
    );
    const bar = screen.getByTestId('job-progress-bar');
    expect(bar.getAttribute('aria-label')).toBe('Job running, 30% complete');
  });

  it('renders aria-label "progress unknown" when indeterminate', () => {
    render(<JobProgressBar {...props({ itemsTotal: null })} />);
    const bar = screen.getByTestId('job-progress-bar');
    expect(bar.getAttribute('aria-label')).toBe('Job running, progress unknown');
  });

  it('applies status-specific colour class via data-status attribute', () => {
    const { rerender } = render(<JobProgressBar {...props({ status: 'failed' })} />);
    expect(screen.getByTestId('job-progress-bar').getAttribute('data-status')).toBe(
      'failed',
    );
    rerender(<JobProgressBar {...props({ status: 'paused' })} />);
    expect(screen.getByTestId('job-progress-bar').getAttribute('data-status')).toBe(
      'paused',
    );
  });

  it('clamps over-100 percentages to 100', () => {
    render(
      <JobProgressBar
        {...props({ status: 'running', itemsProcessed: 50, itemsTotal: 10 })}
      />,
    );
    expect(
      screen.getByTestId('job-progress-bar').getAttribute('aria-valuenow'),
    ).toBe('100');
  });
});
