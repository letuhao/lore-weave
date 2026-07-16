// Studio `quality-canon-rules` — the write half of `quality-canon`. A PORT: it mounts the existing
// CanonRulesPanel behind the shared QualityWorkGate. Tests: it registers as openable, mounts the CRUD
// component with the resolved project once a Work exists, and offers the Set-up-co-writer CTA (D0) on
// a fresh book so a GUI-only user can become operable without leaving the Studio.
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
vi.mock('@/features/composition/hooks/useActiveWork', () => ({
  useActiveWorkId: () => ({ data: undefined }),
}));
// The reverse-deep-link data source (violation counts); stub it so the panel doesn't do a real fetch.
vi.mock('../useQualityCanon', () => ({ useQualityCanon: () => ({ ruleViolations: [] }) }));

// The port reuses this component AS-IS; stub it so this test targets the wrapper (gate + wiring).
vi.mock('@/features/composition/components/CanonRulesPanel', () => ({
  CanonRulesPanel: ({ projectId, bookId }: { projectId: string; bookId: string }) => (
    <div data-testid="stub-canon-rules" data-project={projectId} data-book={bookId} />
  ),
}));

import { QualityCanonRulesPanel } from '../QualityCanonRulesPanel';

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
});

describe('QualityCanonRulesPanel', () => {
  it('registers with the host as an openable studio tool', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'p1' } } });
    withHost('b1', <QualityCanonRulesPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('quality-canon-rules')).not.toBeNull();
  });

  it('mounts the CanonRulesPanel write-half with the resolved project once a Work exists', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'p1' } } });
    withHost('b1', <QualityCanonRulesPanel {...dockProps()} />);
    const stub = screen.getByTestId('stub-canon-rules');
    expect(stub).toHaveAttribute('data-project', 'p1');
    expect(stub).toHaveAttribute('data-book', 'b1');
  });

  it('offers the Set-up-co-writer CTA on no-work (operable for a fresh book), not the CRUD', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1', <QualityCanonRulesPanel {...dockProps()} />);
    expect(screen.getByTestId('quality-canon-rules-no-work')).toBeInTheDocument();
    expect(screen.getByTestId('work-setup-cta')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-canon-rules')).toBeNull();
  });

  it('composition-service UNAVAILABLE is an error, never the no-work CTA', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'unavailable', work: null } });
    withHost('b1', <QualityCanonRulesPanel {...dockProps()} />);
    expect(screen.getByTestId('quality-canon-rules-unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('work-setup-cta')).toBeNull();
  });
});
