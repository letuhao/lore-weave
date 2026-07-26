// REG-X-01 — the Activity log GUI. EFFECT assertions: rows render from the audit
// endpoint, and changing the kind/range filter re-queries with the new params.
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({ listAudit: vi.fn() }));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { ActivityView } from '../ActivityView';

const entry = (o: Partial<Record<string, unknown>> = {}) => ({
  audit_id: 'a1', at: new Date(Date.now() - 3600_000).toISOString(), actor_kind: 'user',
  kind: 'subagent', action: 'create', target_id: 's1', target_name: 'lore-scout', tier: 'user', detail: {}, ...o,
});

beforeEach(() => {
  api.listAudit.mockReset();
  api.listAudit.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe('ActivityView', () => {
  it('renders audit rows from the endpoint', async () => {
    api.listAudit.mockResolvedValue({ items: [entry()], total: 1, limit: 50, offset: 0 });
    render(<ActivityView />);
    await waitFor(() => expect(screen.getByTestId('activity-row')).toBeTruthy());
    const row = screen.getByTestId('activity-row').textContent ?? '';
    expect(row).toContain('subagent·create');
    expect(row).toContain('lore-scout');
    expect(row).toContain('activity.hoursAgo'); // relative-time key rendered (i18n mock returns keys)
  });

  it('shows the empty state when there is no activity', async () => {
    render(<ActivityView />);
    await waitFor(() => expect(screen.getByTestId('activity-empty')).toBeTruthy());
  });

  it('changing the kind filter re-queries with that kind', async () => {
    render(<ActivityView />);
    await waitFor(() => expect(api.listAudit).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('activity-kind'), { target: { value: 'mcp_server' } });
    await waitFor(() => expect(api.listAudit.mock.calls.some((c) => c[1]?.kind === 'mcp_server')).toBe(true));
  });

  it('changing the range filter re-queries with that range', async () => {
    render(<ActivityView />);
    await waitFor(() => expect(api.listAudit).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('activity-range'), { target: { value: '7d' } });
    await waitFor(() => expect(api.listAudit.mock.calls.some((c) => c[1]?.range === '7d')).toBe(true));
  });
});
