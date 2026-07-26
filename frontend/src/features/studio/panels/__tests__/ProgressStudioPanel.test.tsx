// Studio `progress` — PORT of ProgressPanel behind QualityWorkGate (category editor). Tests: registers
// openable; mounts ProgressPanel with the resolved project; no-work → Set-up-co-writer CTA.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const useWorkResolution = vi.fn();
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: (b: string, t: string | null) => useWorkResolution(b, t),
  useCreateWork: () => ({ mutateAsync: vi.fn().mockResolvedValue({ project_id: 'proj-new' }), isPending: false }),
  usePendingWorkResolver: () => ({ state: 'idle', start: vi.fn(), retry: vi.fn() }),
}));
vi.mock('@/features/composition/hooks/useActiveWork', () => ({ useActiveWorkId: () => ({ data: undefined }) }));
vi.mock('@/features/composition/components/ProgressPanel', () => ({
  ProgressPanel: ({ projectId, bookId }: { projectId: string; bookId: string }) => (
    <div data-testid="stub-progress" data-project={projectId} data-book={bookId} />
  ),
}));

import { ProgressStudioPanel } from '../ProgressStudioPanel';

function dockProps() { return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps; }
let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }
function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>);
}

beforeEach(() => {
  hostRef = null;
  useWorkResolution.mockReset();
  useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'p1' } } });
});

describe('ProgressStudioPanel', () => {
  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <ProgressStudioPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('progress')).not.toBeNull();
  });

  it('mounts ProgressPanel with the resolved project + book once a Work exists', () => {
    withHost('b1', <ProgressStudioPanel {...dockProps()} />);
    const stub = screen.getByTestId('stub-progress');
    expect(stub).toHaveAttribute('data-project', 'p1');
    expect(stub).toHaveAttribute('data-book', 'b1');
  });

  it('offers the Set-up-co-writer CTA on a fresh (no-work) book', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1', <ProgressStudioPanel {...dockProps()} />);
    expect(screen.getByTestId('progress-no-work')).toBeInTheDocument();
    expect(screen.getByTestId('work-setup-cta')).toBeInTheDocument();
  });
});
