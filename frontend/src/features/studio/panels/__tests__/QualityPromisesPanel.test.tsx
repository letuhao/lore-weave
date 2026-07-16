// Studio Quality tab — QualityPromisesPanel: resolves the book's composition Work via
// useWorkResolution, shows loading/no-work states, and renders the real ThreadsPanel
// (DOCK-2 reuse) once a project resolves. ThreadsPanel's own behavior is tested in its
// own file — this test stays about THIS panel's wiring.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const useWorkResolution = vi.fn();
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: (bookId: string, token: string | null) => useWorkResolution(bookId, token),
  // D0 — the no-work branch now renders <WorkSetupCta>, which reuses these hooks.
  useCreateWork: () => ({ mutateAsync: vi.fn().mockResolvedValue({ project_id: 'proj-new' }), isPending: false }),
  usePendingWorkResolver: () => ({ state: 'idle', start: vi.fn(), retry: vi.fn() }),
}));

vi.mock('@/features/composition/components/ThreadsPanel', () => ({
  ThreadsPanel: ({ projectId, token, enabled }: { projectId: string; token: string | null; enabled: boolean }) => (
    <div data-testid="stub-threads-panel" data-project={projectId} data-token={token ?? ''} data-enabled={String(enabled)} />
  ),
}));

import { QualityPromisesPanel } from '../QualityPromisesPanel';

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string) {
  return render(<StudioHostProvider bookId={bookId}><QualityPromisesPanel {...dockProps()} /></StudioHostProvider>);
}

beforeEach(() => { useWorkResolution.mockReset(); });

describe('QualityPromisesPanel', () => {
  it('shows a loading state while the Work is resolving', () => {
    useWorkResolution.mockReturnValue({ isLoading: true, data: undefined });
    withHost('b1');
    expect(screen.getByTestId('quality-promises-loading')).toBeInTheDocument();
  });

  it('shows a no-work empty state when the book has no composition Work', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1');
    expect(screen.getByTestId('quality-promises-no-work')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-threads-panel')).toBeNull();
  });

  it('renders ThreadsPanel with the resolved project id and token, always enabled', () => {
    useWorkResolution.mockReturnValue({
      isLoading: false,
      data: { status: 'found', work: { project_id: 'proj-1' } },
    });
    withHost('b1');
    const stub = screen.getByTestId('stub-threads-panel');
    expect(stub).toHaveAttribute('data-project', 'proj-1');
    expect(stub).toHaveAttribute('data-token', 'tok');
    expect(stub).toHaveAttribute('data-enabled', 'true');
  });

  // /review-impl (D-04 follow-up) — `unavailable` means composition-service is DOWN. Rendering the
  // no-work sentence there tells the user "start composing a chapter first" when the data may well
  // exist and we simply could not look. Unconsulted is not empty. RUN-STATE DR-27.
  it('composition-service UNAVAILABLE is an ERROR, never the no-work empty state', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'unavailable', work: null } });
    withHost('b1');
    expect(screen.getByTestId('quality-promises-unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('quality-promises-no-work')).toBeNull();
    expect(screen.queryByTestId('stub-threads-panel')).toBeNull();
  });
});
