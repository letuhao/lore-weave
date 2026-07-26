// RAID C1 — SteeringPanel: resolves book_id from the StudioHost book context (with a params
// fallback), registers + self-titles its dock tab, and renders a hint when there's no book.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { SteeringPanel } from '../SteeringPanel';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }) }));
// Stub the manager so the panel test stays about book-id resolution + chrome, not the CRUD stack.
vi.mock('@/features/steering/components/SteeringManager', () => ({
  SteeringManager: ({ bookId }: { bookId: string }) => <div data-testid="steering-manager-stub" data-book={bookId} />,
}));

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps(params?: Record<string, unknown>) {
  return { api: { setTitle: vi.fn() }, params } as unknown as IDockviewPanelProps;
}
const withHost = (bookId: string, ui: ReactNode) =>
  render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);

beforeEach(() => { hostRef = null; vi.clearAllMocks(); });

describe('SteeringPanel', () => {
  it('resolves book_id from the host context and renders the manager', () => {
    const props = dockProps();
    withHost('b1', <SteeringPanel {...props} />);
    const stub = screen.getByTestId('steering-manager-stub');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <SteeringPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('steering')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('steering')!.commandId).toBe('studio.openPanel.steering');
  });

  it('falls back to params.book_id when the host has no book', () => {
    withHost('', <SteeringPanel {...dockProps({ book_id: 'b2' })} />);
    expect(screen.getByTestId('steering-manager-stub').getAttribute('data-book')).toBe('b2');
  });

  it('renders a hint when there is no book context at all', () => {
    withHost('', <SteeringPanel {...dockProps()} />);
    expect(screen.queryByTestId('steering-manager-stub')).toBeNull();
    expect(screen.getByTestId('studio-steering-panel').textContent).toBe('steering.noBook');
  });
});
