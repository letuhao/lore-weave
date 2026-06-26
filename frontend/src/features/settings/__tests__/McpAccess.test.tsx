import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useState } from 'react';

// P1 — Settings → MCP access. The security-load-bearing bits: the secret is
// revealed exactly once and dropped on close (never re-shown), a new key
// defaults to the safe `read` scope, and a revoked key offers no revoke action.

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { McpCreateKeyDialog } from '../McpCreateKeyDialog';
import type { McpKey, McpKeyCreated, McpKeyCreatePayload } from '../api';

const CREATED: McpKeyCreated = {
  key_id: 'k1',
  name: 'agent',
  key: 'lw_pk_SUPERSECRETVALUE',
  key_prefix: 'lw_pk_abcdef',
  scopes: ['read'],
  created_at: '2026-06-26T00:00:00Z',
};

function DialogHarness({ onCreate }: { onCreate: (p: McpKeyCreatePayload) => Promise<McpKeyCreated | null> }) {
  const [open, setOpen] = useState(true);
  return (
    <div>
      <button onClick={() => setOpen(true)}>reopen</button>
      <McpCreateKeyDialog open={open} onOpenChange={setOpen} onCreate={onCreate} />
    </div>
  );
}

describe('McpCreateKeyDialog', () => {
  it('defaults to the read scope and reveals the secret once on create', async () => {
    const onCreate = vi.fn().mockResolvedValue(CREATED);
    render(<DialogHarness onCreate={onCreate} />);

    fireEvent.change(screen.getByPlaceholderText('mcp.create.name_ph'), { target: { value: 'agent' } });
    fireEvent.click(screen.getByRole('button', { name: 'mcp.create.submit' }));

    await waitFor(() => expect(screen.getByText('lw_pk_SUPERSECRETVALUE')).toBeInTheDocument());
    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'agent',
        scopes: ['read'],
        rate_limit_rpm: 60,
        spend_cap_usd: null,
        allow_self_confirm: false,
        expires_at: null,
      }),
    );
  });

  it('drops the secret on close — reopening shows the form, never the old secret', async () => {
    const onCreate = vi.fn().mockResolvedValue(CREATED);
    render(<DialogHarness onCreate={onCreate} />);

    fireEvent.change(screen.getByPlaceholderText('mcp.create.name_ph'), { target: { value: 'agent' } });
    fireEvent.click(screen.getByRole('button', { name: 'mcp.create.submit' }));
    await waitFor(() => expect(screen.getByText('lw_pk_SUPERSECRETVALUE')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'mcp.reveal.done' })); // close
    fireEvent.click(screen.getByRole('button', { name: 'reopen' })); // re-open

    expect(screen.queryByText('lw_pk_SUPERSECRETVALUE')).toBeNull();
    expect(screen.getByRole('button', { name: 'mcp.create.submit' })).toBeInTheDocument();
  });
});

// ── Tab list — revoke action only for active keys ─────────────────────────────
const ACTIVE: McpKey = {
  key_id: 'a1', name: 'live-agent', key_prefix: 'lw_pk_aaaaaa', scopes: ['read'],
  spend_cap_usd: null, rate_limit_rpm: 60, allow_self_confirm: false,
  status: 'active', last_used_at: null, expires_at: null, created_at: '2026-06-26T00:00:00Z',
};
const REVOKED: McpKey = { ...ACTIVE, key_id: 'r1', name: 'dead-agent', status: 'revoked' };

const revokeMock = vi.fn();
vi.mock('../useMcpKeys', () => ({
  useMcpKeys: () => ({ keys: [ACTIVE, REVOKED], loading: false, create: vi.fn(), revoke: revokeMock, refresh: vi.fn() }),
}));

import { McpAccessTab } from '../McpAccessTab';

describe('McpAccessTab', () => {
  beforeEach(() => revokeMock.mockReset());

  it('offers a revoke action only for active keys', () => {
    render(<McpAccessTab />);
    // The aria label interpolates the name → one button per ACTIVE key only.
    expect(screen.getByRole('button', { name: 'mcp.revoke_aria' })).toBeInTheDocument();
    const revokeButtons = screen.getAllByRole('button', { name: 'mcp.revoke_aria' });
    expect(revokeButtons).toHaveLength(1); // not for the revoked key
    expect(screen.getByText('live-agent')).toBeInTheDocument();
    expect(screen.getByText('dead-agent')).toBeInTheDocument();
  });
});
