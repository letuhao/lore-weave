// Studio Quality tab — QualityCanonPanel: merges composition's canon-issues (generation-time
// contradictions) with knowledge's canon-flags (extraction-time contradictions) into one list,
// and jumps to a chapter via the existing focusManuscriptUnit host action (no new bus event).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const useWorkResolution = vi.fn();
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: (bookId: string, token: string | null) => useWorkResolution(bookId, token),
}));

const useBookKnowledgeProject = vi.fn();
vi.mock('@/features/knowledge/hooks/useBookKnowledgeProject', () => ({
  useBookKnowledgeProject: (bookId: string) => useBookKnowledgeProject(bookId),
}));

const getCanonIssues = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: { getCanonIssues: (...args: unknown[]) => getCanonIssues(...args) },
}));

const listCanonFlags = vi.fn();
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: { listCanonFlags: (...args: unknown[]) => listCanonFlags(...args) },
}));

import { QualityCanonPanel } from '../QualityCanonPanel';

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function withHost(bookId: string, ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hostRef = null;
  useWorkResolution.mockReset();
  useBookKnowledgeProject.mockReset();
  getCanonIssues.mockReset();
  listCanonFlags.mockReset();
  useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
  useBookKnowledgeProject.mockReturnValue({ project: null, projectId: null, isLoading: false });
  getCanonIssues.mockResolvedValue({ items: [] });
  listCanonFlags.mockResolvedValue({ flags: [] });
});

describe('QualityCanonPanel', () => {
  it('shows an empty state when neither source has any issues', async () => {
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('quality-canon-empty')).toBeInTheDocument());
  });

  it('lists a composition (generation-time) issue with a jump-to-chapter action', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    getCanonIssues.mockResolvedValue({
      items: [{ scene_id: 's1', scene_title: 'Scene A', chapter_id: 'ch1', job_id: 'j1', created_at: 'x', status: 'checked', violations: [{ why: 'Alice is gone but present' }] }],
    });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-composition-item')).toBeInTheDocument());
    expect(screen.getByText(/Alice is gone but present/)).toBeInTheDocument();

    const jumpSpy = vi.spyOn(hostRef!, 'focusManuscriptUnit');
    fireEvent.click(screen.getByTestId('quality-canon-jump'));
    expect(jumpSpy).toHaveBeenCalledWith('ch1');
  });

  it('lists a knowledge (extraction-time) flag, resolving chapter_id from context.source_id', async () => {
    useBookKnowledgeProject.mockReturnValue({ project: { project_id: 'kproj-1' }, projectId: 'kproj-1', isLoading: false });
    listCanonFlags.mockResolvedValue({
      flags: [{
        log_id: 1, job_id: 'j1', user_id: 'u1', level: 'warning',
        message: "Canon check: 'Alice' referenced as active despite being marked gone",
        context: { event: 'pass2_canon_flag', source_type: 'chapter', source_id: 'ch-99', name: 'Alice' },
        created_at: 'x',
      }],
    });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-extraction-item')).toBeInTheDocument());
    const jumpSpy = vi.spyOn(hostRef!, 'focusManuscriptUnit');
    fireEvent.click(screen.getByTestId('quality-canon-jump'));
    expect(jumpSpy).toHaveBeenCalledWith('ch-99');
  });

  it('renders both sources together when both have issues', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    useBookKnowledgeProject.mockReturnValue({ project: { project_id: 'kproj-1' }, projectId: 'kproj-1', isLoading: false });
    getCanonIssues.mockResolvedValue({
      items: [{ scene_id: 's1', scene_title: 'Scene A', chapter_id: 'ch1', job_id: 'j1', created_at: 'x', status: 'checked', violations: [] }],
    });
    listCanonFlags.mockResolvedValue({
      flags: [{ log_id: 1, job_id: 'j2', user_id: 'u1', level: 'warning', message: 'flag', context: { event: 'pass2_canon_flag' }, created_at: 'x' }],
    });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => {
      expect(screen.getByTestId('quality-canon-composition-section')).toBeInTheDocument();
      expect(screen.getByTestId('quality-canon-extraction-section')).toBeInTheDocument();
    });
  });

  // /review-impl: a fetch error must never silently render as "no issues" — that's a
  // false-negative (the checker didn't run, it isn't clean).
  it('shows an error banner (never the empty state) when the composition query fails', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    getCanonIssues.mockRejectedValue(new Error('boom'));
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('quality-canon-composition-error')).toBeInTheDocument());
    expect(screen.queryByTestId('quality-canon-empty')).toBeNull();
  });

  it('shows an error banner (never the empty state) when the extraction query fails', async () => {
    useBookKnowledgeProject.mockReturnValue({ project: { project_id: 'kproj-1' }, projectId: 'kproj-1', isLoading: false });
    listCanonFlags.mockRejectedValue(new Error('boom'));
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('quality-canon-extraction-error')).toBeInTheDocument());
    expect(screen.queryByTestId('quality-canon-empty')).toBeNull();
  });
});
