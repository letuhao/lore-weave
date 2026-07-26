import { render, screen, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...args: unknown[]) => apiJson(...args), apiBase: () => '' }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'admin-rs256' }) }));

import { AdminConfirmCard } from './AdminConfirmCard';
import type { ToolCallRecord } from '../types';

const record: ToolCallRecord = {
  tool: 'glossary_confirm_action',
  ok: true,
  pending: true,
  runId: 'run-1',
  toolCallId: 'tc-1',
  args: { confirm_token: 'ct-1', descriptor: 'system_create', title: 'Add steampunk genre' },
};

beforeEach(() => apiJson.mockReset());
afterEach(() => vi.clearAllMocks());

describe('AdminConfirmCard', () => {
  it('previews against the ADMIN endpoint on mount (non-consuming)', async () => {
    apiJson.mockResolvedValueOnce({ title: 'Add steampunk genre', preview_rows: [] });
    render(<AdminConfirmCard record={record} onResume={vi.fn()} />);
    await waitFor(() =>
      expect(apiJson).toHaveBeenCalledWith('/v1/glossary/actions/admin/preview', {
        method: 'POST',
        token: 'admin-rs256',
        body: JSON.stringify({ confirm_token: 'ct-1' }),
      }),
    );
  });

  it('Confirm POSTs to the ADMIN confirm endpoint (not the user /actions/confirm) then resumes action_done', async () => {
    apiJson.mockResolvedValueOnce({}); // preview on mount
    const onResume = vi.fn();
    render(<AdminConfirmCard record={record} onResume={onResume} />);

    apiJson.mockResolvedValueOnce({}); // confirm
    await act(async () => {
      screen.getByText('Confirm').click();
    });

    const confirmCall = apiJson.mock.calls.find((c) => c[0] === '/v1/glossary/actions/admin/confirm');
    expect(confirmCall).toBeTruthy();
    expect(confirmCall![1]).toMatchObject({ method: 'POST', token: 'admin-rs256' });
    // It must NEVER hit the user confirm path.
    expect(apiJson.mock.calls.some((c) => c[0] === '/v1/glossary/actions/confirm')).toBe(false);
    await waitFor(() => expect(onResume).toHaveBeenCalledWith('run-1', 'tc-1', 'action_done'));
  });

  it('a 422 confirm resumes token_expired (re-proposable)', async () => {
    apiJson.mockResolvedValueOnce({}); // preview
    const onResume = vi.fn();
    render(<AdminConfirmCard record={record} onResume={onResume} />);

    apiJson.mockRejectedValueOnce(Object.assign(new Error('expired'), { status: 422 }));
    await act(async () => {
      screen.getByText('Confirm').click();
    });
    await waitFor(() => expect(onResume).toHaveBeenCalledWith('run-1', 'tc-1', 'token_expired'));
  });

  it('Cancel resumes cancelled without any confirm call', async () => {
    apiJson.mockResolvedValueOnce({}); // preview
    const onResume = vi.fn();
    render(<AdminConfirmCard record={record} onResume={onResume} />);

    await act(async () => {
      screen.getByText('Cancel').click();
    });
    expect(apiJson.mock.calls.some((c) => c[0] === '/v1/glossary/actions/admin/confirm')).toBe(false);
    expect(onResume).toHaveBeenCalledWith('run-1', 'tc-1', 'cancelled');
  });
});
