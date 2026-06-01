import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';

// ARCH-1 C5 — the additive `embedded` flag on ChatSessionProvider must gate
// router navigation: page mode navigates on selectSession; embedded mode does
// not (the host owns the active session, there's no chat route).

const navigateMock = vi.fn();
let urlSessionId: string | undefined;
vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
  useParams: () => ({ sessionId: urlSessionId }),
}));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('sonner', () => ({ toast: { info: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/features/settings/api', () => ({
  providerApi: { listUserModels: () => Promise.resolve({ items: [] }) },
}));
vi.mock('../hooks/useSessions', () => ({
  useSessions: () => ({
    sessions: [],
    isLoading: false,
    refresh: vi.fn(),
    createSession: vi.fn(),
    renameSession: vi.fn(),
    archiveSession: vi.fn(),
    deleteSession: vi.fn(),
    togglePin: vi.fn(),
  }),
}));

import { ChatSessionProvider, useChatSession } from '../providers/ChatSessionContext';
import type { ChatSession } from '../types';

const session = { session_id: 's-1' } as ChatSession;

function Probe() {
  const { selectSession, activeSession } = useChatSession();
  return (
    <div>
      <span data-testid="active">{activeSession?.session_id ?? 'none'}</span>
      <button onClick={() => selectSession(session)}>select</button>
    </div>
  );
}

describe('ChatSessionProvider — embedded nav gate', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    urlSessionId = undefined;
  });

  it('page mode: selectSession navigates to the chat route', () => {
    render(
      <ChatSessionProvider>
        <Probe />
      </ChatSessionProvider>,
    );
    act(() => {
      screen.getByText('select').click();
    });
    expect(screen.getByTestId('active').textContent).toBe('s-1');
    expect(navigateMock).toHaveBeenCalledWith('/chat/s-1', { replace: true });
  });

  it('embedded mode: selectSession sets state WITHOUT navigating', () => {
    render(
      <ChatSessionProvider embedded>
        <Probe />
      </ChatSessionProvider>,
    );
    act(() => {
      screen.getByText('select').click();
    });
    expect(screen.getByTestId('active').textContent).toBe('s-1');
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
