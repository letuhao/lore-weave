// S-12 — WorkflowProposalsView: the pending inbox whose approve mints a workflow
// (the loop registry_propose_workflow promised but had no UI for). Asserts through the
// real hook → api boundary (memory: a checklist tick needs an EFFECT test).
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({
  listProposals: vi.fn(),
  approveProposal: vi.fn(),
  rejectProposal: vi.fn(),
}));
vi.mock('@/features/workflows/api', () => ({ workflowsApi: api }));

import { WorkflowProposalsView } from '../WorkflowProposalsView';

const proposal = (over: Record<string, unknown> = {}) => ({
  proposal_id: 'wp1', action: 'create', slug: 'setup-world', title: 'Set up my world',
  description: 'proposed recipe', surfaces: ['chat'], inputs: {},
  steps: [{ id: 's1', tool: 'glossary_propose_entities', gate: 'confirm' }],
  notes_md: '# steps', status: 'pending', reject_reason: '',
  from_session_id: '', from_session_label: '', created_at: '', expires_at: '', ...over,
});

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listProposals.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe('WorkflowProposalsView (S-12)', () => {
  it('shows the empty state (and no cards)', async () => {
    render(<WorkflowProposalsView />);
    await waitFor(() => expect(screen.getByTestId('workflow-proposals-empty')).toBeTruthy());
    expect(screen.queryByTestId('workflow-proposal-card')).toBeNull();
  });

  it('approve → approveProposal; reject → rejectProposal (pending only)', async () => {
    api.listProposals.mockResolvedValue({ items: [proposal()], total: 1, limit: 50, offset: 0 });
    api.approveProposal.mockResolvedValue({});
    api.rejectProposal.mockResolvedValue({});
    render(<WorkflowProposalsView />);
    await waitFor(() => expect(screen.getByTestId('workflow-proposal-card')).toBeTruthy());
    fireEvent.click(screen.getByTestId('workflow-proposal-approve'));
    await waitFor(() => expect(api.approveProposal).toHaveBeenCalledWith('test-token', 'wp1'));
    fireEvent.click(screen.getByTestId('workflow-proposal-reject'));
    await waitFor(() => expect(api.rejectProposal).toHaveBeenCalledWith('test-token', 'wp1', ''));
  });

  it('renders the STEPS being approved (informed approval, not blind)', async () => {
    api.listProposals.mockResolvedValue({ items: [proposal()], total: 1, limit: 50, offset: 0 });
    render(<WorkflowProposalsView />);
    await waitFor(() => expect(screen.getByTestId('workflow-proposal-steps')).toBeTruthy());
    expect(screen.getByText('glossary_propose_entities')).toBeTruthy();
  });

  it('a non-pending proposal shows no approve/reject buttons', async () => {
    api.listProposals.mockResolvedValue({ items: [proposal({ status: 'approved' })], total: 1, limit: 50, offset: 0 });
    render(<WorkflowProposalsView />);
    await waitFor(() => expect(screen.getByTestId('workflow-proposal-card')).toBeTruthy());
    expect(screen.queryByTestId('workflow-proposal-approve')).toBeNull();
  });

  it('status filter re-queries with the chosen status', async () => {
    render(<WorkflowProposalsView />);
    await waitFor(() => expect(api.listProposals).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('workflow-proposals-status-filter'), { target: { value: 'approved' } });
    await waitFor(() => expect(api.listProposals.mock.calls.at(-1)?.[1]).toMatchObject({ status: 'approved' }));
  });
});
