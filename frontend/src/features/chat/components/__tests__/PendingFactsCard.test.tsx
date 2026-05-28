import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { PendingFact } from '../../types';

// K21-C (D8): the pending-facts review card.

const toastMocks = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

import { PendingFactsCard } from '../PendingFactsCard';

function fact(overrides: Partial<PendingFact> = {}): PendingFact {
  return {
    pending_fact_id: 'pf-1',
    user_id: 'u-1',
    project_id: 'proj-1',
    session_id: 's-1',
    fact_type: 'preference',
    fact_text: 'The user prefers tea over coffee.',
    created_at: '2026-05-17T00:00:00Z',
    ...overrides,
  };
}

describe('PendingFactsCard', () => {
  beforeEach(() => {
    toastMocks.error.mockReset();
  });

  it('renders nothing when the list is empty', () => {
    const { container } = render(
      <PendingFactsCard pendingFacts={[]} onConfirm={vi.fn()} onReject={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('pending-facts-card')).toBeNull();
  });

  it('renders a row per pending fact with its text and type', () => {
    render(
      <PendingFactsCard
        pendingFacts={[
          fact({ pending_fact_id: 'pf-1', fact_text: 'Likes tea.', fact_type: 'preference' }),
          fact({ pending_fact_id: 'pf-2', fact_text: 'Quit the guild.', fact_type: 'milestone' }),
        ]}
        onConfirm={vi.fn()}
        onReject={vi.fn()}
      />,
    );
    const rows = screen.getAllByTestId('pending-fact-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Likes tea.');
    expect(rows[0]).toHaveTextContent('Preference');
    expect(rows[1]).toHaveTextContent('Quit the guild.');
    expect(rows[1]).toHaveTextContent('Milestone');
  });

  it('calls onConfirm with the fact id when Confirm is clicked', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(
      <PendingFactsCard
        pendingFacts={[fact({ pending_fact_id: 'pf-9' })]}
        onConfirm={onConfirm}
        onReject={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('pending-fact-confirm'));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith('pf-9'));
  });

  it('calls onReject with the fact id when Reject is clicked', async () => {
    const onReject = vi.fn().mockResolvedValue(undefined);
    render(
      <PendingFactsCard
        pendingFacts={[fact({ pending_fact_id: 'pf-7' })]}
        onConfirm={vi.fn()}
        onReject={onReject}
      />,
    );
    fireEvent.click(screen.getByTestId('pending-fact-reject'));
    await waitFor(() => expect(onReject).toHaveBeenCalledWith('pf-7'));
  });

  it('toasts when a confirm action rejects', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('server down'));
    render(
      <PendingFactsCard
        pendingFacts={[fact()]}
        onConfirm={onConfirm}
        onReject={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('pending-fact-confirm'));
    await waitFor(() => expect(toastMocks.error).toHaveBeenCalled());
    expect(toastMocks.error.mock.calls[0][0]).toContain('server down');
  });

  it('falls back to the raw fact_type for an unmapped type', () => {
    render(
      <PendingFactsCard
        // @ts-expect-error — exercising the unmapped-type fallback path
        pendingFacts={[fact({ fact_type: 'mystery' })]}
        onConfirm={vi.fn()}
        onReject={vi.fn()}
      />,
    );
    expect(screen.getByTestId('pending-fact-row')).toHaveTextContent('mystery');
  });
});
