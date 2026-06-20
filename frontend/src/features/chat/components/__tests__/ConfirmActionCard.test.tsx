import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// MCP fan-out (C-CONFIRM) — the GENERIC confirm card: domain selects the confirm
// endpoint; on mount it previews (non-consuming); Confirm POSTs the token and
// resumes with the real outcome (H6). H2: with items[] it renders ONE card with
// N rows + a single Apply.

const submitToolResult = vi.fn().mockResolvedValue('');
const confirmAction = vi.fn();
const previewAction = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('../../actionsApi', () => ({
  actionsApi: {
    confirmAction: (...a: unknown[]) => confirmAction(...a),
    previewAction: (...a: unknown[]) => previewAction(...a),
  },
}));

import { ConfirmActionCard } from '../ConfirmActionCard';
import type { ToolCallRecord } from '../../types';

function record(args: Record<string, unknown>): ToolCallRecord {
  return { tool: 'confirm_action', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args };
}

const baseArgs = { confirm_token: 'tok123', descriptor: 'book.publish', title: 'Publish chapter', domain: 'book' };

describe('ConfirmActionCard', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    confirmAction.mockReset();
    previewAction.mockReset();
    previewAction.mockResolvedValue({
      descriptor: 'book.publish', title: 'Publish chapter',
      preview_rows: [{ label: 'chapter', value: 'Chapter 5' }], destructive: false,
    });
  });

  it('previews against the domain on mount', async () => {
    confirmAction.mockResolvedValue({});
    render(<ConfirmActionCard record={record(baseArgs)} />);
    await waitFor(() => expect(previewAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(screen.getByText('Chapter 5')).toBeInTheDocument());
  });

  it('confirm POSTs the token to the domain and resumes action_done', async () => {
    confirmAction.mockResolvedValue({});
    render(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('book', 'tok123', 'tok'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('resumes token_expired on a 422', async () => {
    confirmAction.mockRejectedValue(Object.assign(new Error('expired'), { status: 422 }));
    render(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.confirm'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'token_expired'));
  });

  it('cancel resumes cancelled without a confirm POST', async () => {
    render(<ConfirmActionCard record={record(baseArgs)} />);
    fireEvent.click(screen.getByText('actionConfirm.cancel'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'cancelled'));
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it('H2: a batch (items[]) renders ONE card with N rows and a single Apply', async () => {
    previewAction.mockResolvedValue({ descriptor: 'book.publish_batch', title: 'Publish 3 drafts', preview_rows: null, destructive: false });
    confirmAction.mockResolvedValue({});
    render(<ConfirmActionCard record={record({
      ...baseArgs, descriptor: 'book.publish_batch',
      items: [{ title: 'Chapter 1' }, { title: 'Chapter 2' }, { title: 'Chapter 3' }],
    })} />);

    // exactly ONE card
    expect(screen.getAllByTestId('confirm-action-card')).toHaveLength(1);
    // N rows
    const rows = screen.getByTestId('confirm-batch-rows').querySelectorAll('li');
    expect(rows).toHaveLength(3);
    expect(screen.getByText('Chapter 2')).toBeInTheDocument();
    // a SINGLE Apply (Confirm all) commits the whole batch with one token
    fireEvent.click(screen.getByText('actionConfirm.confirm_all'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });
});
