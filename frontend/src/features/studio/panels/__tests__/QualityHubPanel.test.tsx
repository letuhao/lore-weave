// Studio Quality tab — QualityHubPanel: a DOCK-8 launcher (4 cards), each opening its own
// sibling panel via host.openPanel — never an internal view-switch.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const useWorkResolution = vi.fn();
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: (bookId: string, token: string | null) => useWorkResolution(bookId, token),
  // D0 — the no-work branch now renders <WorkSetupCta>, which reuses these hooks.
  useCreateWork: () => ({ mutateAsync: vi.fn().mockResolvedValue({ project_id: 'proj-new' }), isPending: false }),
  usePendingWorkResolver: () => ({ state: 'idle', start: vi.fn(), retry: vi.fn() }),
}));
// useQualityWork also reads the active-Work pref (9262ed53e) — a real useQuery; stub it.
vi.mock('@/features/composition/hooks/useActiveWork', () => ({
  useActiveWorkId: () => ({ data: undefined }),
}));

import { QualityHubPanel } from '../QualityHubPanel';

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => {
  hostRef = null;
  useWorkResolution.mockReset();
  useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
});

describe('QualityHubPanel', () => {
  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <QualityHubPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('quality')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('quality')!.commandId).toBe('studio.openPanel.quality');
  });

  it('renders exactly the 5 capability cards (canon-rules is the write half of canon)', () => {
    withHost('b1', <QualityHubPanel {...dockProps()} />);
    expect(screen.getByTestId('quality-hub-card-quality-promises')).toBeInTheDocument();
    expect(screen.getByTestId('quality-hub-card-quality-critic')).toBeInTheDocument();
    expect(screen.getByTestId('quality-hub-card-quality-coverage')).toBeInTheDocument();
    expect(screen.getByTestId('quality-hub-card-quality-canon')).toBeInTheDocument();
    expect(screen.getByTestId('quality-hub-card-quality-canon-rules')).toBeInTheDocument();
  });

  it('each card opens its own sibling panel via the host, never an internal view-switch', () => {
    withHost('b1', <QualityHubPanel {...dockProps()} />);
    const openPanelSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByTestId('quality-hub-card-quality-canon'));
    expect(openPanelSpy).toHaveBeenCalledWith('quality-canon');
  });

  it('shows a no-work hint when the book has no composition Work yet (canon still works either way)', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1', <QualityHubPanel {...dockProps()} />);
    expect(screen.getByTestId('quality-hub-no-work')).toBeInTheDocument();
    // The cards still render — canon issues don't need a composition Work.
    expect(screen.getByTestId('quality-hub-card-quality-canon')).toBeInTheDocument();
  });

  // /review-impl MED — the hub fronts all four quality panels, so it carried the same collapse:
  // `unavailable` (composition-service DOWN) rendered the "start composing a chapter first" hint.
  it('composition-service UNAVAILABLE shows an error, never the "go compose" hint', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'unavailable', work: null } });
    withHost('b1', <QualityHubPanel {...dockProps()} />);
    expect(screen.getByTestId('quality-hub-unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('quality-hub-no-work')).toBeNull();
  });
});
