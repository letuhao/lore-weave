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
  it('defaults to read tier + OD-5 domains and reveals the secret once on create', async () => {
    const onCreate = vi.fn().mockResolvedValue(CREATED);
    render(<DialogHarness onCreate={onCreate} />);

    fireEvent.change(screen.getByPlaceholderText('mcp.create.name_ph'), { target: { value: 'agent' } });
    fireEvent.click(screen.getByRole('button', { name: 'mcp.create.submit' }));

    await waitFor(() => expect(screen.getByText('lw_pk_SUPERSECRETVALUE')).toBeInTheDocument());
    // The composed scopes[]: read tier + the OD-5 default domains (book/glossary/knowledge).
    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'agent',
        scopes: ['read', 'domain:book', 'domain:glossary', 'domain:knowledge'],
        rate_limit_rpm: 60,
        spend_cap_usd: null,
        allow_self_confirm: false,
        expires_at: null,
      }),
    );
  });

  it('composes deselected domains out of the submitted scopes', async () => {
    const onCreate = vi.fn().mockResolvedValue(CREATED);
    render(<DialogHarness onCreate={onCreate} />);

    fireEvent.change(screen.getByPlaceholderText('mcp.create.name_ph'), { target: { value: 'agent' } });
    // Untick the two non-knowledge defaults → only domain:knowledge remains.
    fireEvent.click(screen.getByText('mcp.domain.book'));
    fireEvent.click(screen.getByText('mcp.domain.glossary'));
    fireEvent.click(screen.getByRole('button', { name: 'mcp.create.submit' }));

    await waitFor(() => expect(onCreate).toHaveBeenCalled());
    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({ scopes: ['read', 'domain:knowledge'] }),
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
const loadAuditMock = vi.fn();
vi.mock('../useMcpKeys', () => ({
  useMcpKeys: () => ({
    keys: [ACTIVE, REVOKED], loading: false, create: vi.fn(),
    revoke: revokeMock, refresh: vi.fn(), loadAudit: loadAuditMock,
  }),
}));

// P4 / OD-2: the approval panel (mounted in McpAccessTab) pulls in useMcpApprovals →
// useAuth. Mock it with a shared, mutable state so the tab tests render the panel as
// empty (→ null) and a dedicated panel test can inject a pending row.
const approvalsHoist = vi.hoisted(() => ({
  state: {
    approvals: [] as Array<Record<string, unknown>>,
    loading: false,
    busyId: null as string | null,
    approve: vi.fn(),
    deny: vi.fn(),
    refresh: vi.fn(),
  },
}));
vi.mock('../useMcpApprovals', () => ({ useMcpApprovals: () => approvalsHoist.state }));

import { McpAccessTab } from '../McpAccessTab';
import { McpApprovalsPanel } from '../McpApprovalsPanel';

describe('McpAccessTab', () => {
  beforeEach(() => {
    revokeMock.mockReset();
    loadAuditMock.mockReset();
  });

  it('offers a revoke action only for active keys', () => {
    render(<McpAccessTab />);
    // The aria label interpolates the name → one button per ACTIVE key only.
    expect(screen.getByRole('button', { name: 'mcp.revoke_aria' })).toBeInTheDocument();
    const revokeButtons = screen.getAllByRole('button', { name: 'mcp.revoke_aria' });
    expect(revokeButtons).toHaveLength(1); // not for the revoked key
    expect(screen.getByText('live-agent')).toBeInTheDocument();
    expect(screen.getByText('dead-agent')).toBeInTheDocument();
  });

  it('expands a key to show its call audit (H-O), fetching once per key', async () => {
    loadAuditMock.mockResolvedValue([
      { audit_id: 'au1', method: 'tools/call', tool_name: 'book_get', outcome: 'relayed', trace_id: null, created_at: '2026-06-28T00:00:00Z' },
      { audit_id: 'au2', method: 'tools/call', tool_name: 'kg_graph_query', outcome: 'denied_scope', trace_id: null, created_at: '2026-06-28T00:01:00Z' },
    ]);
    render(<McpAccessTab />);
    // Both keys offer the history toggle (audit is available even for a revoked key).
    const toggles = screen.getAllByRole('button', { name: 'mcp.audit.toggle_aria' });
    fireEvent.click(toggles[0]); // expand the active key

    await waitFor(() => expect(screen.getByText('book_get')).toBeInTheDocument());
    expect(screen.getByText('kg_graph_query')).toBeInTheDocument();
    // Outcome chips are localized.
    expect(screen.getByText('mcp.audit.outcome.relayed')).toBeInTheDocument();
    expect(screen.getByText('mcp.audit.outcome.denied_scope')).toBeInTheDocument();
    expect(loadAuditMock).toHaveBeenCalledWith('a1');
  });

  it('shows an empty state when a key has no recorded calls', async () => {
    loadAuditMock.mockResolvedValue([]);
    render(<McpAccessTab />);
    fireEvent.click(screen.getAllByRole('button', { name: 'mcp.audit.toggle_aria' })[0]);
    await waitFor(() => expect(screen.getByText('mcp.audit.empty')).toBeInTheDocument());
  });
});

// P4 / OD-2 — the owner's pending-approval panel.
describe('McpApprovalsPanel', () => {
  beforeEach(() => {
    approvalsHoist.state.approvals = [];
    approvalsHoist.state.busyId = null;
    approvalsHoist.state.approve = vi.fn();
    approvalsHoist.state.deny = vi.fn();
  });

  it('renders nothing when there are no pending approvals', () => {
    const { container } = render(<McpApprovalsPanel />);
    expect(container.querySelector('[data-testid="mcp-approvals-panel"]')).toBeNull();
  });

  it('renders a pending approval and wires Approve/Deny', () => {
    approvalsHoist.state.approvals = [
      { approval_id: 'ap1', key_id: 'abcdef0123', tool_name: 'composition_generate', domain: 'composition', preview: { title: 'Generate scene' }, cost_estimate_usd: 0.5, status: 'pending', expires_at: '2026-06-28T01:00:00Z', created_at: '2026-06-28T00:00:00Z' },
    ];
    render(<McpApprovalsPanel />);
    expect(screen.getByTestId('mcp-approvals-panel')).toBeInTheDocument();
    expect(screen.getByText('Generate scene')).toBeInTheDocument();
    expect(screen.getByText('composition_generate')).toBeInTheDocument();

    fireEvent.click(screen.getByText('mcp.approvals.approve'));
    expect(approvalsHoist.state.approve).toHaveBeenCalledWith('ap1');
    fireEvent.click(screen.getByText('mcp.approvals.deny'));
    expect(approvalsHoist.state.deny).toHaveBeenCalledWith('ap1');
  });
});
