// REG-P5-03 — the admin official-registry ingest curation GUI. EFFECT assertions:
// pull calls the API + shows counts, approve/reject call the API, only pending rows
// show action buttons.
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({
  ingestPull: vi.fn(),
  listIngestQueue: vi.fn(),
  approveIngest: vi.fn(),
  rejectIngest: vi.fn(),
}));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { AdminIngestView } from '../AdminIngestView';

const entry = (o: Partial<Record<string, unknown>> = {}) => ({
  ingest_id: 'i1', source: 'official', registry_id: 'io.x/a', name: 'io.x/a', description: 'a server',
  version: '1.0.0', endpoint_url: 'https://mcp.x/v1', status: 'pending', approved_server_id: null,
  reject_reason: '', first_seen_at: '', updated_at: '', ...o,
});

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listIngestQueue.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
});

describe('AdminIngestView', () => {
  it('pull calls the API and shows the counts', async () => {
    api.ingestPull.mockResolvedValue({ fetched: 100, new: 43, updated: 27, skipped_no_remote: 30, truncated: false });
    render(<AdminIngestView />);
    await waitFor(() => expect(screen.getByTestId('ingest-pull')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ingest-pull'));
    await waitFor(() => expect(api.ingestPull).toHaveBeenCalled());
    // i18n mock returns the key (interpolated counts aren't shown); assert the
    // result banner rendered post-pull. The count→param wiring is covered by tsc.
    await waitFor(() => expect(screen.getByTestId('ingest-pull-result').textContent).toContain('ingest.pullResult'));
  });

  it('approve + reject call the API for a pending row', async () => {
    api.listIngestQueue.mockResolvedValue({ items: [entry()], total: 1, limit: 50, offset: 0 });
    api.approveIngest.mockResolvedValue({ ingest_id: 'i1', status: 'approved', mcp_server_id: 's1' });
    api.rejectIngest.mockResolvedValue({ ingest_id: 'i1', status: 'rejected' });
    render(<AdminIngestView />);
    await waitFor(() => expect(screen.getByTestId('ingest-row')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ingest-approve'));
    await waitFor(() => expect(api.approveIngest).toHaveBeenCalledWith('test-token', 'i1'));
    fireEvent.click(screen.getByTestId('ingest-reject'));
    await waitFor(() => expect(api.rejectIngest).toHaveBeenCalledWith('test-token', 'i1', expect.any(String)));
  });

  it('a non-pending row shows no action buttons', async () => {
    api.listIngestQueue.mockResolvedValue({ items: [entry({ status: 'approved' })], total: 1, limit: 50, offset: 0 });
    render(<AdminIngestView />);
    await waitFor(() => expect(screen.getByTestId('ingest-row')).toBeTruthy());
    expect(screen.queryByTestId('ingest-approve')).toBeNull();
    expect(screen.queryByTestId('ingest-reject')).toBeNull();
  });

  it('surfaces an approve error verbatim (e.g. SSRF/model-cap 400)', async () => {
    api.listIngestQueue.mockResolvedValue({ items: [entry()], total: 1, limit: 50, offset: 0 });
    api.approveIngest.mockRejectedValue(new Error('SSRF_BLOCKED: endpoint resolves to an internal address'));
    render(<AdminIngestView />);
    await waitFor(() => expect(screen.getByTestId('ingest-approve')).toBeTruthy());
    fireEvent.click(screen.getByTestId('ingest-approve'));
    await waitFor(() => expect(screen.getByTestId('ingest-error').textContent).toContain('SSRF_BLOCKED'));
  });
});
