import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Glossary-assistant P4 — the Tier-S schema-confirm card: Confirm POSTs the
// token to the JWT-only /v1/glossary/schema/confirm and resumes with the real
// outcome (H6) — schema_created on 201, token_expired on 422, cancelled on Cancel.

const submitToolResult = vi.fn().mockResolvedValue('');
const confirmSchema = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: { confirmSchema: (...a: unknown[]) => confirmSchema(...a) },
}));

import { SchemaConfirmCard } from '../SchemaConfirmCard';
import type { ToolCallRecord } from '../../types';

function record(args: Record<string, unknown>): ToolCallRecord {
  return { tool: 'glossary_confirm_schema', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args };
}

const kindArgs = { confirm_token: 'tok123', op: 'kind', summary: 'Create kind "Power System"' };

describe('SchemaConfirmCard', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    confirmSchema.mockReset();
  });

  it('confirm POSTs the token and resumes schema_created', async () => {
    confirmSchema.mockResolvedValue({});
    render(<SchemaConfirmCard record={record(kindArgs)} />);

    fireEvent.click(screen.getByText('schemaConfirm.confirm'));

    await waitFor(() => expect(confirmSchema).toHaveBeenCalledWith('tok123', 'tok'));
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'schema_created'),
    );
  });

  it('resumes token_expired when confirm returns 422', async () => {
    confirmSchema.mockRejectedValue(Object.assign(new Error('expired'), { status: 422 }));
    render(<SchemaConfirmCard record={record(kindArgs)} />);

    fireEvent.click(screen.getByText('schemaConfirm.confirm'));

    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'token_expired'),
    );
  });

  it('cancel resumes cancelled without a POST', async () => {
    render(<SchemaConfirmCard record={record(kindArgs)} />);

    fireEvent.click(screen.getByText('schemaConfirm.cancel'));

    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'cancelled'),
    );
    expect(confirmSchema).not.toHaveBeenCalled();
  });
});
