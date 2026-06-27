import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const selectSession = vi.fn();
const setShowNewDialog = vi.fn();
const archiveSession = vi.fn();
let ctx: Record<string, unknown>;
vi.mock('../../providers', () => ({ useChatSession: () => ctx }));

import { SessionSwitcher } from '../SessionSwitcher';
import type { ChatSession } from '../../types';

function sess(id: string, projectId: string | null, title = id): ChatSession {
  return {
    session_id: id,
    title,
    project_id: projectId,
    model_ref: 'm',
    model_source: 'user_model',
    message_count: 0,
    status: 'active',
  } as ChatSession;
}

const A = sess('a', 'p1', 'Book One chat');
const B = sess('b', 'p1', 'Book One chat 2');
const C = sess('c', 'p2', 'Other book chat');

beforeEach(() => {
  selectSession.mockReset();
  setShowNewDialog.mockReset();
  archiveSession.mockReset();
  ctx = {
    sessions: [A, B, C],
    activeSession: A,
    sessionsLoading: false,
    selectSession,
    setShowNewDialog,
    archiveSession,
    modelNameMap: new Map(),
  };
});

describe('SessionSwitcher', () => {
  it('shows the active session title on the trigger', () => {
    render(<SessionSwitcher scopeProjectId="p1" />);
    expect(screen.getByTestId('session-switcher-trigger')).toHaveTextContent('Book One chat');
  });

  it('lists only this-project sessions when scoped (cross-book hidden)', () => {
    render(<SessionSwitcher scopeProjectId="p1" />);
    fireEvent.click(screen.getByTestId('session-switcher-trigger'));
    const opts = screen.getAllByRole('option').map((o) => o.textContent);
    expect(opts.some((tx) => tx?.includes('Book One chat 2'))).toBe(true);
    expect(opts.some((tx) => tx?.includes('Other book chat'))).toBe(false);
  });

  it('shows all sessions when scopeProjectId is omitted', () => {
    render(<SessionSwitcher />);
    fireEvent.click(screen.getByTestId('session-switcher-trigger'));
    expect(screen.getAllByRole('option')).toHaveLength(3);
  });

  it('always keeps the active session visible even if its project differs', () => {
    ctx.activeSession = C; // active belongs to p2, but we scope to p1
    render(<SessionSwitcher scopeProjectId="p1" />);
    fireEvent.click(screen.getByTestId('session-switcher-trigger'));
    const opts = screen.getAllByRole('option').map((o) => o.textContent);
    expect(opts.some((tx) => tx?.includes('Other book chat'))).toBe(true);
  });

  it('switches session on option click and closes', () => {
    render(<SessionSwitcher scopeProjectId="p1" />);
    fireEvent.click(screen.getByTestId('session-switcher-trigger'));
    fireEvent.click(screen.getByText('Book One chat 2'));
    expect(selectSession).toHaveBeenCalledWith(B);
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('opens the new-chat dialog via setShowNewDialog', () => {
    render(<SessionSwitcher scopeProjectId="p1" />);
    fireEvent.click(screen.getByTestId('session-switcher-trigger'));
    fireEvent.click(screen.getByText('switcher.new_chat'));
    expect(setShowNewDialog).toHaveBeenCalledWith(true);
  });

  it('archives a session without selecting it', () => {
    render(<SessionSwitcher scopeProjectId="p1" />);
    fireEvent.click(screen.getByTestId('session-switcher-trigger'));
    const archiveButtons = screen.getAllByRole('button', { name: 'sidebar.archive' });
    fireEvent.click(archiveButtons[0]);
    expect(archiveSession).toHaveBeenCalledWith('a');
    expect(selectSession).not.toHaveBeenCalled();
  });
});
