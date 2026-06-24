import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { CollaboratorsPanel } from '../CollaboratorsPanel';

// ── mocks ────────────────────────────────────────────────────────────
const h = vi.hoisted(() => ({
  list: vi.fn(),
  invite: vi.fn(),
  changeRole: vi.fn(),
  remove: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listCollaborators: (...a: unknown[]) => h.list(...a),
    inviteCollaborator: (...a: unknown[]) => h.invite(...a),
    changeCollaboratorRole: (...a: unknown[]) => h.changeRole(...a),
    removeCollaborator: (...a: unknown[]) => h.remove(...a),
  },
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => (o?.email ? `${k}:${o.email}` : k) }),
}));
vi.mock('sonner', () => ({ toast: { success: (m: string) => h.toastSuccess(m), error: (m: string) => h.toastError(m) } }));

const aCollaborator = (over: Record<string, unknown> = {}) => ({
  user_id: 'u-123456789', role: 'edit', granted_by: 'owner', created_at: '', updated_at: '',
  display_name: 'Ada Lovelace', ...over,
});

beforeEach(() => Object.values(h).forEach((fn) => fn.mockReset()));

describe('CollaboratorsPanel (E0-5)', () => {
  it('renders enriched collaborators (display_name + role)', async () => {
    h.list.mockResolvedValue({ collaborators: [aCollaborator()] });
    render(<CollaboratorsPanel bookId="b1" />);
    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument();
  });

  it('renders NOTHING for a non-owner (403 → owner-only panel hidden)', async () => {
    h.list.mockRejectedValue(Object.assign(new Error('forbidden'), { status: 403 }));
    const { container } = render(<CollaboratorsPanel bookId="b1" />);
    await waitFor(() => expect(h.list).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('invites by email then refetches', async () => {
    h.list.mockResolvedValue({ collaborators: [] });
    h.invite.mockResolvedValue({ user_id: 'u2', role: 'view', display_name: '' });
    render(<CollaboratorsPanel bookId="b1" />);
    await screen.findByText('collaborators.empty');
    fireEvent.change(screen.getByPlaceholderText('collaborators.email_placeholder'), {
      target: { value: 'bob@x.co' },
    });
    fireEvent.click(screen.getByText('collaborators.invite'));
    await waitFor(() => expect(h.invite).toHaveBeenCalledWith('tok', 'b1', { email: 'bob@x.co', role: 'view' }));
    expect(h.list).toHaveBeenCalledTimes(2); // initial + post-invite refetch
  });

  it('surfaces a clean "no such user" on a 404 invite', async () => {
    h.list.mockResolvedValue({ collaborators: [] });
    h.invite.mockRejectedValue(Object.assign(new Error('nope'), { status: 404 }));
    render(<CollaboratorsPanel bookId="b1" />);
    await screen.findByText('collaborators.empty');
    fireEvent.change(screen.getByPlaceholderText('collaborators.email_placeholder'), {
      target: { value: 'ghost@x.co' },
    });
    fireEvent.click(screen.getByText('collaborators.invite'));
    await waitFor(() => expect(h.toastError).toHaveBeenCalledWith('collaborators.no_such_user'));
  });

  it('removes a collaborator', async () => {
    h.list.mockResolvedValue({ collaborators: [aCollaborator()] });
    h.remove.mockResolvedValue({ status: 'revoked' });
    render(<CollaboratorsPanel bookId="b1" />);
    await screen.findByText('Ada Lovelace');
    fireEvent.click(screen.getByLabelText('collaborators.remove'));
    await waitFor(() => expect(h.remove).toHaveBeenCalledWith('tok', 'b1', 'u-123456789'));
  });
});
