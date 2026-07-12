import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// RAID C2 (DR-C2 §4) — the Write-mode Tier-A approval card: a `tool_approval`
// suspension ({kind, tool, args, tier} riding the pending-tool-call surface)
// renders the tool name + pretty args + tier badge with Approve once / Always
// allow / Deny, each resuming via the standard tool-results endpoint with the
// matching outcome. The card performs NO API call of its own — the server
// executes on resume.

const submitToolResult = vi.fn().mockResolvedValue('');

vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));

import { ToolApprovalCard, isToolApprovalRecord } from '../ToolApprovalCard';
import type { ToolCallRecord } from '../../types';

function approvalRecord(overrides: Partial<ToolCallRecord> = {}): ToolCallRecord {
  return {
    tool: 'book_create',
    ok: true,
    pending: true,
    runId: 'r1',
    toolCallId: 'c1',
    args: {
      kind: 'tool_approval',
      tool: 'book_create',
      args: { title: 'My Book' },
      tier: 'A',
    },
    ...overrides,
  };
}

describe('ToolApprovalCard', () => {
  beforeEach(() => submitToolResult.mockClear());

  it('renders the tool name, pretty args and tier badge', () => {
    render(<ToolApprovalCard record={approvalRecord()} />);
    const card = screen.getByTestId('tool-approval-card');
    expect(card.getAttribute('data-tool')).toBe('book_create');
    expect(screen.getByText('book_create')).toBeInTheDocument();
    // pretty-printed args
    expect(screen.getByText(/"title": "My Book"/)).toBeInTheDocument();
    expect(screen.getByTestId('tool-approval-tier')).toBeInTheDocument();
  });

  it('Approve once resumes approved_once', async () => {
    render(<ToolApprovalCard record={approvalRecord()} />);
    fireEvent.click(screen.getByText('toolApproval.approve_once'));
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'approved_once'),
    );
  });

  it('Always allow resumes approved_always', async () => {
    render(<ToolApprovalCard record={approvalRecord()} />);
    fireEvent.click(screen.getByText('toolApproval.always_allow'));
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'approved_always'),
    );
  });

  it('Deny resumes denied', async () => {
    render(<ToolApprovalCard record={approvalRecord()} />);
    fireEvent.click(screen.getByText('toolApproval.deny'));
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'denied'),
    );
  });

  it('Never allow resumes denied_always (D3 — persistent deny from the card)', async () => {
    render(<ToolApprovalCard record={approvalRecord()} />);
    fireEvent.click(screen.getByText('toolApproval.never_allow'));
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'denied_always'),
    );
  });

  it('a decision is single-shot — the buttons collapse to a status line', async () => {
    render(<ToolApprovalCard record={approvalRecord()} />);
    fireEvent.click(screen.getByText('toolApproval.deny'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('toolApproval.approve_once')).toBeNull();
    expect(screen.getByText('toolApproval.denied')).toBeInTheDocument();
  });

  it('Never allow collapses to an undoable status line', async () => {
    render(<ToolApprovalCard record={approvalRecord()} />);
    fireEvent.click(screen.getByText('toolApproval.never_allow'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('toolApproval.never_allow')).toBeNull();
    expect(screen.getByText('toolApproval.never_allowed')).toBeInTheDocument();
  });
});

describe('isToolApprovalRecord', () => {
  it('matches only a pending record carrying the kind marker', () => {
    expect(isToolApprovalRecord(approvalRecord())).toBe(true);
    // completed record with same args — not a suspension
    expect(isToolApprovalRecord(approvalRecord({ pending: false }))).toBe(false);
    // ordinary pending frontend tool — no kind marker
    expect(
      isToolApprovalRecord({
        tool: 'propose_edit', ok: true, pending: true,
        args: { operation: 'insert_at_cursor', text: 'x' },
      }),
    ).toBe(false);
    // no args at all
    expect(isToolApprovalRecord({ tool: 'book_create', ok: true, pending: true })).toBe(false);
  });
});
