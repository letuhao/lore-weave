import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Generalized class-C confirm card (spec §13): on mount it fetches a current-state
// preview (non-consuming), Confirm POSTs the token to the JWT-only
// /v1/glossary/actions/confirm and resumes with the real outcome (H6) — action_done
// on success, token_expired on 422 (expired/replay/drift), cancelled on Cancel.

const submitToolResult = vi.fn().mockResolvedValue('');
const confirmAction = vi.fn();
const previewAction = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: {
    confirmAction: (...a: unknown[]) => confirmAction(...a),
    previewAction: (...a: unknown[]) => previewAction(...a),
  },
}));

import { ConfirmCard } from '../ConfirmCard';
import type { ToolCallRecord } from '../../types';

function record(args: Record<string, unknown>): ToolCallRecord {
  return { tool: 'glossary_confirm_action', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args };
}

const delArgs = { confirm_token: 'tok123', descriptor: 'book_delete', title: 'Delete kind "Cultivation"' };

describe('ConfirmCard', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    confirmAction.mockReset();
    previewAction.mockReset();
    previewAction.mockResolvedValue({
      descriptor: 'book_delete',
      title: 'Delete kind "Cultivation"',
      preview_rows: [{ label: 'attributes deprecated', value: '3' }],
      destructive: true,
    });
  });

  it('fetches the current-state preview on mount and renders its rows', async () => {
    confirmAction.mockResolvedValue({});
    render(<ConfirmCard record={record(delArgs)} />);
    await waitFor(() => expect(previewAction).toHaveBeenCalledWith('tok123', 'tok'));
    await waitFor(() => expect(screen.getByText('attributes deprecated')).toBeInTheDocument());
  });

  it('confirm POSTs the token and resumes action_done', async () => {
    confirmAction.mockResolvedValue({});
    render(<ConfirmCard record={record(delArgs)} />);

    fireEvent.click(screen.getByText('actionConfirm.confirm'));

    await waitFor(() => expect(confirmAction).toHaveBeenCalledWith('tok123', 'tok'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('resumes token_expired when confirm returns 422 (expired/replay/drift)', async () => {
    confirmAction.mockRejectedValue(Object.assign(new Error('expired'), { status: 422 }));
    render(<ConfirmCard record={record(delArgs)} />);

    fireEvent.click(screen.getByText('actionConfirm.confirm'));

    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'token_expired'));
  });

  it('cancel resumes cancelled without a confirm POST', async () => {
    render(<ConfirmCard record={record(delArgs)} />);

    fireEvent.click(screen.getByText('actionConfirm.cancel'));

    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'cancelled'));
    expect(confirmAction).not.toHaveBeenCalled();
  });
});
