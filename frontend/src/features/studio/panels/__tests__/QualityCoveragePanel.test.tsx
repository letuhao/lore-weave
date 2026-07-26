// Studio Quality tab — QualityCoveragePanel: resolves the book's composition Work, offers a
// model picker (BookPromiseCoverageSection's underlying hook needs a modelRef to enable its
// Run button), and renders BookPromiseCoverageSection (DOCK-2 reuse) once a project resolves.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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
// useQualityWork also reads the active-Work pref (9262ed53e) — a real useQuery; stub it.
vi.mock('@/features/composition/hooks/useActiveWork', () => ({
  useActiveWorkId: () => ({ data: undefined }),
}));

vi.mock('@/features/composition/components/BookPromiseCoverageSection', () => ({
  BookPromiseCoverageSection: ({ projectId, token, modelRef }: { projectId: string; token: string | null; modelRef: string }) => (
    <div data-testid="stub-coverage-section" data-project={projectId} data-token={token ?? ''} data-model={modelRef} />
  ),
}));

vi.mock('@/components/model-picker', () => ({
  ModelPicker: ({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) => (
    <button data-testid="stub-model-picker" data-value={value ?? ''} onClick={() => onChange('model-1')}>pick</button>
  ),
}));

import { QualityCoveragePanel } from '../QualityCoveragePanel';

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string) {
  return render(<StudioHostProvider bookId={bookId}><QualityCoveragePanel {...dockProps()} /></StudioHostProvider>);
}

beforeEach(() => { useWorkResolution.mockReset(); });

describe('QualityCoveragePanel', () => {
  it('shows a loading state while the Work is resolving', () => {
    useWorkResolution.mockReturnValue({ isLoading: true, data: undefined });
    withHost('b1');
    expect(screen.getByTestId('quality-coverage-loading')).toBeInTheDocument();
  });

  it('shows a no-work empty state when the book has no composition Work', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1');
    expect(screen.getByTestId('quality-coverage-no-work')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-coverage-section')).toBeNull();
  });

  it('renders the model picker + coverage section, forwarding the picked model into the section', () => {
    useWorkResolution.mockReturnValue({
      isLoading: false,
      data: { status: 'found', work: { project_id: 'proj-1' } },
    });
    withHost('b1');
    expect(screen.getByTestId('stub-coverage-section')).toHaveAttribute('data-model', '');
    fireEvent.click(screen.getByTestId('stub-model-picker'));
    expect(screen.getByTestId('stub-coverage-section')).toHaveAttribute('data-model', 'model-1');
    expect(screen.getByTestId('stub-coverage-section')).toHaveAttribute('data-project', 'proj-1');
  });

  // /review-impl (D-04 follow-up) — `unavailable` means composition-service is DOWN. Rendering the
  // no-work sentence there tells the user "start composing a chapter first" when the data may well
  // exist and we simply could not look. Unconsulted is not empty. RUN-STATE DR-27.
  it('composition-service UNAVAILABLE is an ERROR, never the no-work empty state', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'unavailable', work: null } });
    withHost('b1');
    expect(screen.getByTestId('quality-coverage-unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('quality-coverage-no-work')).toBeNull();
    expect(screen.queryByTestId('stub-coverage-section')).toBeNull();
  });

  // /review-impl HIGH — `candidates` means Works EXIST, we just need to pick one. Every other
  // consumer (CompositionPanel, OutlineTree, usePublishGate, useSceneBrowser) resolves it by taking
  // the first. My first cut of the shared gate dropped it into `no-work`, so a book WITH works was
  // told "start composing a chapter first" — inviting the duplicate Work that useSceneBrowser's own
  // comment warns about. AMBIGUOUS IS NOT ABSENT.
  it('CANDIDATES resolves to the first Work — never the no-work CTA', () => {
    useWorkResolution.mockReturnValue({
      isLoading: false,
      data: { status: 'candidates', work: null, candidates: [{ project_id: 'cand-1' }] },
    });
    withHost('b1');
    expect(screen.queryByTestId('quality-coverage-no-work')).toBeNull();
    expect(screen.queryByTestId('quality-coverage-unavailable')).toBeNull();
    // …and it resolved to the RIGHT one, not merely "something rendered".
    expect(screen.getByTestId('stub-coverage-section')).toHaveAttribute('data-project', 'cand-1');
  });
});
