// Studio Quality tab — QualityCriticPanel: resolves the book's composition Work, offers a
// chapter picker (booksApi.listChapters) + model picker, and renders QualityReportSection
// (DOCK-2 reuse) only once BOTH a project resolved AND a chapter is picked (no book-wide
// critic aggregation exists — see the plan doc's reality map).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const useWorkResolution = vi.fn();
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: (bookId: string, token: string | null) => useWorkResolution(bookId, token),
}));

const listChapters = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { listChapters: (...args: unknown[]) => listChapters(...args) },
}));

vi.mock('@/features/composition/components/QualityReportSection', () => ({
  QualityReportSection: ({ projectId, chapterId, modelRef }: { projectId: string; chapterId: string; modelRef: string }) => (
    <div data-testid="stub-quality-report" data-project={projectId} data-chapter={chapterId} data-model={modelRef} />
  ),
}));

vi.mock('@/components/model-picker', () => ({
  ModelPicker: ({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) => (
    <button data-testid="stub-model-picker" data-value={value ?? ''} onClick={() => onChange('model-1')}>pick</button>
  ),
}));

import { QualityCriticPanel } from '../QualityCriticPanel';

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId={bookId}><QualityCriticPanel {...dockProps()} /></StudioHostProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useWorkResolution.mockReset();
  listChapters.mockReset();
  listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Chapter One', sort_order: 1 }], total: 1 });
});

describe('QualityCriticPanel', () => {
  it('shows a loading state while the Work is resolving', () => {
    useWorkResolution.mockReturnValue({ isLoading: true, data: undefined });
    withHost('b1');
    expect(screen.getByTestId('quality-critic-loading')).toBeInTheDocument();
  });

  it('shows a no-work empty state when the book has no composition Work', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1');
    expect(screen.getByTestId('quality-critic-no-work')).toBeInTheDocument();
  });

  it('shows a pick-a-chapter hint before any chapter is selected, never rendering the report', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    withHost('b1');
    expect(screen.getByTestId('quality-critic-no-chapter')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-quality-report')).toBeNull();
  });

  it('renders the quality report once a chapter + model are picked, scoped to the resolved project', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    withHost('b1');

    await waitFor(() => expect(screen.getByRole('option', { name: 'Chapter One' })).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('quality-critic-chapter-picker'), { target: { value: 'ch1' } });
    fireEvent.click(screen.getByTestId('stub-model-picker'));

    const stub = screen.getByTestId('stub-quality-report');
    expect(stub).toHaveAttribute('data-project', 'proj-1');
    expect(stub).toHaveAttribute('data-chapter', 'ch1');
    expect(stub).toHaveAttribute('data-model', 'model-1');
  });

  // /review-impl: no silent cap — a book with more chapters than the picker's LIMIT must say so.
  it('shows a truncation hint when the book has more chapters than the picker limit', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Chapter One', sort_order: 1 }], total: 800 });
    withHost('b1');
    await waitFor(() => expect(screen.getByTestId('quality-critic-chapters-truncated')).toBeInTheDocument());
  });

  it('shows no truncation hint when every chapter fits within the picker limit', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    listChapters.mockResolvedValue({ items: [{ chapter_id: 'ch1', title: 'Chapter One', sort_order: 1 }], total: 1 });
    withHost('b1');
    await waitFor(() => expect(screen.getByRole('option', { name: 'Chapter One' })).toBeInTheDocument());
    expect(screen.queryByTestId('quality-critic-chapters-truncated')).toBeNull();
  });

  // /review-impl (D-04 follow-up) — `unavailable` means composition-service is DOWN. Rendering the
  // no-work sentence there tells the user "start composing a chapter first" when the data may well
  // exist and we simply could not look. Unconsulted is not empty. RUN-STATE DR-27.
  it('composition-service UNAVAILABLE is an ERROR, never the no-work empty state', () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'unavailable', work: null } });
    withHost('b1');
    expect(screen.getByTestId('quality-critic-unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('quality-critic-no-work')).toBeNull();
  });
});
