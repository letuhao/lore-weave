// Studio `quality-corrections` — DISPLAY-ONLY port of CorrectionStatsTable behind QualityWorkGate.
// Tests: registers openable; mounts the table with the resolved project; offers the Set-up-co-writer
// CTA on a fresh book; an errored stats fetch is `unavailable` (we could not look), never a false empty.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const useWorkResolution = vi.fn();
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: (bookId: string, token: string | null) => useWorkResolution(bookId, token),
  useCreateWork: () => ({ mutateAsync: vi.fn().mockResolvedValue({ project_id: 'proj-new' }), isPending: false }),
  usePendingWorkResolver: () => ({ state: 'idle', start: vi.fn(), retry: vi.fn() }),
}));
vi.mock('@/features/composition/hooks/useActiveWork', () => ({ useActiveWorkId: () => ({ data: undefined }) }));

const useCorrectionStats = vi.fn();
vi.mock('@/features/composition/hooks/useCorrectionStats', () => ({
  useCorrectionStats: () => useCorrectionStats(),
}));
vi.mock('@/features/composition/components/CorrectionStatsTable', () => ({
  CorrectionStatsTable: ({ stats }: { stats: { by_mode: unknown[] } }) => (
    <div data-testid="stub-correction-stats" data-modes={String((stats.by_mode ?? []).length)} />
  ),
}));

import { QualityCorrectionsPanel } from '../QualityCorrectionsPanel';

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
  useCorrectionStats.mockReset();
  useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'p1' } } });
});

describe('QualityCorrectionsPanel', () => {
  it('registers with the host as an openable studio tool', () => {
    useCorrectionStats.mockReturnValue({ isLoading: false, isError: false, data: { by_mode: [] } });
    withHost('b1', <QualityCorrectionsPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('quality-corrections')).not.toBeNull();
  });

  it('mounts the correction-stats table once a Work + stats resolve', () => {
    useCorrectionStats.mockReturnValue({ isLoading: false, isError: false, data: { by_mode: [{ mode: 'auto' }] } });
    withHost('b1', <QualityCorrectionsPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-correction-stats')).toBeInTheDocument();
  });

  it('an errored stats fetch is UNAVAILABLE, never a false empty/clean', () => {
    useCorrectionStats.mockReturnValue({ isLoading: false, isError: true, data: undefined });
    withHost('b1', <QualityCorrectionsPanel {...dockProps()} />);
    expect(screen.getByTestId('quality-corrections-unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-correction-stats')).toBeNull();
  });

  it('offers the Set-up-co-writer CTA on a fresh (no-work) book', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    useCorrectionStats.mockReturnValue({ isLoading: false, isError: false, data: undefined });
    withHost('b1', <QualityCorrectionsPanel {...dockProps()} />);
    expect(screen.getByTestId('quality-corrections-no-work')).toBeInTheDocument();
    expect(screen.getByTestId('work-setup-cta')).toBeInTheDocument();
  });
});
