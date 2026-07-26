// Studio `flywheel` — PORT of FlywheelPanel behind QualityWorkGate with the deep-link RETARGET
// (onOpenCast/Timeline/Relations → host.openPanel, not the legacy in-page selectTab). Tests: registers
// openable; mounts FlywheelPanel with the project; the three deep-links open S7's dock panels; no-work → CTA.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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
// Stub FlywheelPanel: expose the three retarget callbacks so the test can fire them.
vi.mock('@/features/composition/components/FlywheelPanel', () => ({
  FlywheelPanel: ({ projectId, onOpenCast, onOpenTimeline, onOpenRelations }: {
    projectId: string;
    onOpenCast: (n?: string) => void; onOpenTimeline: () => void; onOpenRelations: () => void;
  }) => (
    <div data-testid="stub-flywheel" data-project={projectId}>
      <button data-testid="fw-cast" onClick={() => onOpenCast('Mộ Thanh')}>cast</button>
      <button data-testid="fw-timeline" onClick={onOpenTimeline}>timeline</button>
      <button data-testid="fw-relations" onClick={onOpenRelations}>relations</button>
    </div>
  ),
}));

import { FlywheelStudioPanel } from '../FlywheelStudioPanel';

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

describe('FlywheelStudioPanel', () => {
  it('registers with the host as an openable studio tool', () => {
    withHost('b1', <FlywheelStudioPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('flywheel')).not.toBeNull();
  });

  it('mounts FlywheelPanel with the resolved project', () => {
    withHost('b1', <FlywheelStudioPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-flywheel')).toHaveAttribute('data-project', 'p1');
  });

  it('retargets the deep-links to S7 dock panels (not the legacy in-page selectTab)', () => {
    withHost('b1', <FlywheelStudioPanel {...dockProps()} />);
    const spy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByTestId('fw-cast'));
    fireEvent.click(screen.getByTestId('fw-timeline'));
    fireEvent.click(screen.getByTestId('fw-relations'));
    expect(spy).toHaveBeenCalledWith('cast', { params: { focusName: 'Mộ Thanh' } });
    expect(spy).toHaveBeenCalledWith('kg-timeline');
    expect(spy).toHaveBeenCalledWith('kg-graph');
  });

  it('offers the Set-up-co-writer CTA on a fresh (no-work) book', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1', <FlywheelStudioPanel {...dockProps()} />);
    expect(screen.getByTestId('flywheel-no-work')).toBeInTheDocument();
    expect(screen.getByTestId('work-setup-cta')).toBeInTheDocument();
  });
});
