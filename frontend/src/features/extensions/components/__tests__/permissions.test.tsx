// Track C WS-3 (D-C-ALLOWLIST-WRITE-ONLY) — the tool-consent management panel.
//
// The bug this closes: "Always allow" wrote a permanent grant that no screen could show
// and no action could take back. So the tests that matter are the ones asserting the
// user can SEE a grant and ACT on it — and, critically, that the panel re-reads the
// server after every write (a panel that optimistically shows "revoked" while the server
// still holds the grant would be lying about a permission, which is worse than the
// original defect).
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));

const api = vi.hoisted(() => ({
  listToolPermissions: vi.fn(),
  setToolPermission: vi.fn(),
  revokeToolPermission: vi.fn(),
  listToolCatalog: vi.fn(),
}));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { PermissionsView } from '../PermissionsView';

const perm = (over: Record<string, unknown> = {}) => ({
  tool_name: 'book_create', kind: 'mutation', decision: 'allow',
  created_at: '2026-07-12T00:00:00Z', ...over,
});

const catalogItem = (name: string) => ({
  name, domain: 'book', tier: 'A', description: `the ${name} tool`, visibility: 'discoverable',
});

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listToolPermissions.mockResolvedValue({ permissions: [] });
  api.listToolCatalog.mockResolvedValue({
    items: [catalogItem('book_create'), catalogItem('chapter_delete')],
  });
});

describe('PermissionsView', () => {
  it('shows the empty state when no standing permission has been granted', async () => {
    render(<PermissionsView />);
    await waitFor(() => expect(screen.getByTestId('perm-empty-allowed')).toBeTruthy());
    expect(screen.getByTestId('perm-empty-denied')).toBeTruthy();
  });

  it('lists a granted tool — the grant is finally VISIBLE', async () => {
    api.listToolPermissions.mockResolvedValue({ permissions: [perm()] });
    render(<PermissionsView />);
    await waitFor(() => expect(screen.getByTestId('perm-row-mutation-book_create')).toBeTruthy());
    expect(screen.getByTestId('perm-revoke-mutation-book_create')).toBeTruthy();
  });

  it('separates the spend consent from the write consent', async () => {
    api.listToolPermissions.mockResolvedValue({
      permissions: [perm(), perm({ tool_name: 'glossary_web_search', kind: 'spend' })],
    });
    render(<PermissionsView />);
    await waitFor(() => expect(screen.getByTestId('perm-row-spend-glossary_web_search')).toBeTruthy());
    expect(screen.getByTestId('perm-row-mutation-book_create')).toBeTruthy();
  });

  it('revoke calls the API and RE-READS the server (never an optimistic lie)', async () => {
    api.listToolPermissions.mockResolvedValue({ permissions: [perm()] });
    api.revokeToolPermission.mockResolvedValue(undefined);
    render(<PermissionsView />);
    await waitFor(() => expect(screen.getByTestId('perm-revoke-mutation-book_create')).toBeTruthy());

    // after the revoke, the server has nothing
    api.listToolPermissions.mockResolvedValue({ permissions: [] });
    fireEvent.click(screen.getByTestId('perm-revoke-mutation-book_create'));

    await waitFor(() => expect(api.revokeToolPermission).toHaveBeenCalledWith('test-token', 'book_create', 'mutation'));
    // the row is gone because we RE-FETCHED, not because we assumed
    await waitFor(() => expect(screen.getByTestId('perm-empty-allowed')).toBeTruthy());
    expect(api.listToolPermissions).toHaveBeenCalledTimes(2);
  });

  it('deny flips a granted tool into the blocked list', async () => {
    api.listToolPermissions.mockResolvedValue({ permissions: [perm()] });
    api.setToolPermission.mockResolvedValue(perm({ decision: 'deny' }));
    render(<PermissionsView />);
    await waitFor(() => expect(screen.getByTestId('perm-deny-mutation-book_create')).toBeTruthy());

    api.listToolPermissions.mockResolvedValue({ permissions: [perm({ decision: 'deny' })] });
    fireEvent.click(screen.getByTestId('perm-deny-mutation-book_create'));

    await waitFor(() =>
      expect(api.setToolPermission).toHaveBeenCalledWith('test-token', 'book_create', 'mutation', 'deny'),
    );
    await waitFor(() => expect(screen.getByTestId('perm-empty-allowed')).toBeTruthy());
  });

  it('a user can block a tool they have never been prompted for', async () => {
    api.setToolPermission.mockResolvedValue(perm({ tool_name: 'chapter_delete', decision: 'deny' }));
    render(<PermissionsView />);
    await waitFor(() => expect(screen.getByTestId('perm-new-tool-input')).toBeTruthy());
    await waitFor(() => expect(api.listToolCatalog).toHaveBeenCalled());

    fireEvent.change(screen.getByTestId('perm-new-tool-input'), { target: { value: 'chapter_delete' } });
    fireEvent.click(screen.getByTestId('perm-block-btn'));

    await waitFor(() =>
      expect(api.setToolPermission).toHaveBeenCalledWith('test-token', 'chapter_delete', 'mutation', 'deny'),
    );
  });

  it('a tool name that is not in the catalog cannot be blocked (no phantom "Never runs")', async () => {
    // A free-text box let a typo create a row the panel then rendered as
    // "Blocked - never runs" for a tool that does not exist: a security guarantee
    // about nothing.
    render(<PermissionsView />);
    await waitFor(() => expect(api.listToolCatalog).toHaveBeenCalled());

    fireEvent.change(screen.getByTestId('perm-new-tool-input'), { target: { value: 'book_craete' } });

    await waitFor(() => expect(screen.getByTestId('perm-unknown-tool')).toBeTruthy());
    expect((screen.getByTestId('perm-block-btn') as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByTestId('perm-block-btn'));
    expect(api.setToolPermission).not.toHaveBeenCalled();
  });

  it('a failed write surfaces an error AND resyncs — the row never shows a state the server rejected', async () => {
    api.listToolPermissions.mockResolvedValue({ permissions: [perm()] });
    api.revokeToolPermission.mockRejectedValue(new Error('boom'));
    render(<PermissionsView />);
    await waitFor(() => expect(screen.getByTestId('perm-revoke-mutation-book_create')).toBeTruthy());

    fireEvent.click(screen.getByTestId('perm-revoke-mutation-book_create'));

    await waitFor(() => expect(screen.getByTestId('perm-error')).toBeTruthy());
    // the grant is STILL shown, because it is still real
    expect(screen.getByTestId('perm-row-mutation-book_create')).toBeTruthy();
  });
});
