import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { DiaryPendingFact } from '../../types';
import { DiaryFactInbox } from '../DiaryFactInbox';

function fact(overrides: Partial<DiaryPendingFact> = {}): DiaryPendingFact {
  return {
    pending_fact_id: 'pf-1',
    user_id: 'u-1',
    project_id: 'proj-1',
    session_id: null,
    fact_type: 'statement',
    fact_text: '[statement] Sarah said the Q3 budget is frozen. (2026-06-15)',
    created_at: '2026-06-15T00:00:00Z',
    subject: 'Sarah',
    predicate: 'said',
    object: 'the Q3 budget is frozen',
    event_date: '2026-06-15',
    provenance: 'user',
    ...overrides,
  };
}

const noop = () => {};

describe('DiaryFactInbox', () => {
  it('renders nothing when the inbox is empty (not an alarming empty state)', () => {
    const { container } = render(
      <DiaryFactInbox facts={[]} isLoading={false} error={null} pendingId={null} onConfirm={noop} onReject={noop} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the structured subject·predicate·object when present, and the date/kind', () => {
    render(
      <DiaryFactInbox facts={[fact()]} isLoading={false} error={null} pendingId={null} onConfirm={noop} onReject={noop} />,
    );
    expect(screen.getByTestId('diary-fact-text').textContent).toContain('Sarah · said · the Q3 budget is frozen');
    expect(screen.getByText(/statement · 2026-06-15/)).toBeTruthy();
  });

  it('falls back to the raw fact_text when there is no structured trio', () => {
    render(
      <DiaryFactInbox
        facts={[fact({ subject: null, object: null, fact_text: 'A coarse fact.' })]}
        isLoading={false}
        error={null}
        pendingId={null}
        onConfirm={noop}
        onReject={noop}
      />,
    );
    expect(screen.getByTestId('diary-fact-text').textContent).toBe('A coarse fact.');
  });

  it('confirm/dismiss call back with the fact id', () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();
    render(
      <DiaryFactInbox facts={[fact()]} isLoading={false} error={null} pendingId={null} onConfirm={onConfirm} onReject={onReject} />,
    );
    fireEvent.click(screen.getByTestId('diary-fact-confirm'));
    fireEvent.click(screen.getByTestId('diary-fact-reject'));
    expect(onConfirm).toHaveBeenCalledWith('pf-1');
    expect(onReject).toHaveBeenCalledWith('pf-1');
  });

  it('disables both buttons for the row being mutated', () => {
    render(
      <DiaryFactInbox facts={[fact()]} isLoading={false} error={null} pendingId={'pf-1'} onConfirm={noop} onReject={noop} />,
    );
    expect((screen.getByTestId('diary-fact-confirm') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('diary-fact-reject') as HTMLButtonElement).disabled).toBe(true);
  });
});
