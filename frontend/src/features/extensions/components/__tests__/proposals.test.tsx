// M5 checklist §6 — ProposalsView was built (status filter/empty/error/approve/reject)
// but never tested. These assert the built behavior through the real hook → api boundary
// (memory checklist-is-self-report-enforce-by-tests: a tick needs an EFFECT test).
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({
  listProposals: vi.fn(),
  approveProposal: vi.fn(),
  rejectProposal: vi.fn(),
}));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { ProposalsView } from '../ProposalsView';

const proposal = (over: Record<string, unknown> = {}) => ({
  proposal_id: 'p1', action: 'create', slug: 'agent-skill', description: 'proposed',
  body_md: '# body', status: 'pending', reject_reason: '', from_session_id: '',
  from_session_label: '', created_at: '', expires_at: '', ...over,
});

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listProposals.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe('ProposalsView §6', () => {
  it('shows the empty state (and no cards)', async () => {
    render(<ProposalsView />);
    await waitFor(() => expect(screen.getByText(/No proposals/i)).toBeTruthy());
    expect(screen.queryByTestId('proposal-card')).toBeNull(); // empty ⇔ no cards
  });

  it('shows an error banner when the load fails', async () => {
    api.listProposals.mockRejectedValueOnce(new Error('load failed'));
    render(<ProposalsView />);
    await waitFor(() => expect(screen.getByText(/load failed/i)).toBeTruthy());
  });

  it('status filter re-queries with the chosen status', async () => {
    render(<ProposalsView />);
    await waitFor(() => expect(api.listProposals).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('proposals-status-filter'), { target: { value: 'approved' } });
    await waitFor(() => expect(api.listProposals.mock.calls.at(-1)?.[1]).toMatchObject({ status: 'approved' }));
  });

  it('approve → approveProposal; reject → rejectProposal (pending row only)', async () => {
    api.listProposals.mockResolvedValue({ items: [proposal()], total: 1, limit: 50, offset: 0 });
    api.approveProposal.mockResolvedValue({});
    api.rejectProposal.mockResolvedValue({});
    render(<ProposalsView />);
    await waitFor(() => expect(screen.getByTestId('proposal-card')).toBeTruthy());
    fireEvent.click(screen.getByTestId('proposal-approve'));
    await waitFor(() => expect(api.approveProposal).toHaveBeenCalledWith('test-token', 'p1'));
    fireEvent.click(screen.getByTestId('proposal-reject'));
    await waitFor(() => expect(api.rejectProposal).toHaveBeenCalledWith('test-token', 'p1', ''));
  });

  it('a non-pending proposal shows no approve/reject buttons', async () => {
    api.listProposals.mockResolvedValue({ items: [proposal({ status: 'approved' })], total: 1, limit: 50, offset: 0 });
    render(<ProposalsView />);
    await waitFor(() => expect(screen.getByTestId('proposal-card')).toBeTruthy());
    expect(screen.queryByTestId('proposal-approve')).toBeNull();
  });
});
