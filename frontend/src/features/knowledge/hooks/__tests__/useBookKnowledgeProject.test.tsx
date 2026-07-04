import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok' }),
}));

const listProjectsMock = vi.fn();
vi.mock('../../api', () => ({
  knowledgeApi: {
    listProjects: (...args: unknown[]) => listProjectsMock(...args),
  },
}));

import { useBookKnowledgeProject } from '../useBookKnowledgeProject';
import type { Project } from '../../types';

function mkProject(id: string, bookId: string | null): Project {
  return { project_id: id, name: id, book_id: bookId } as Project;
}

// The BE filters server-side on `book_id` (14_kg_panels.md /review-impl fix — a client-side
// `.find()` over an unfiltered, paginated list could silently miss a project past the first
// page). This mock behaves like the real endpoint: it only returns rows matching the
// `book_id` param it was called with, proving the hook actually sends the filter rather than
// relying on the caller pre-narrowing `items`.
function mockServerFilteredBy(all: Project[]) {
  listProjectsMock.mockImplementation((params: { book_id?: string }) =>
    Promise.resolve({
      items: params.book_id ? all.filter((p) => p.book_id === params.book_id) : all,
      next_cursor: null,
    }),
  );
}

function Harness({ bookId }: { bookId: string }) {
  const { project, projectId, isLoading } = useBookKnowledgeProject(bookId);
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="project-id">{projectId ?? 'none'}</span>
      <span data-testid="project-name">{project?.name ?? 'none'}</span>
    </div>
  );
}

function renderHarness(bookId: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Harness bookId={bookId} />
    </QueryClientProvider>,
  );
}

describe('useBookKnowledgeProject', () => {
  beforeEach(() => {
    listProjectsMock.mockReset();
  });

  it('sends book_id as a server-side filter param (not a client-side .find() over an unfiltered page)', async () => {
    mockServerFilteredBy([mkProject('standalone', null), mkProject('linked', 'book-1')]);
    renderHarness('book-1');
    await waitFor(() => expect(screen.getByTestId('project-id').textContent).toBe('linked'));
    expect(listProjectsMock).toHaveBeenCalledWith(
      expect.objectContaining({ book_id: 'book-1' }),
      'tok',
    );
  });

  it('resolves the project whose book_id matches the given book', async () => {
    mockServerFilteredBy([mkProject('standalone', null), mkProject('linked', 'book-1')]);
    renderHarness('book-1');
    await waitFor(() => expect(screen.getByTestId('project-id').textContent).toBe('linked'));
    expect(screen.getByTestId('project-name').textContent).toBe('linked');
  });

  it('resolves correctly even when the matching project would be past the first page for an unfiltered list', async () => {
    // 150 standalone projects (past a 100-item page) + the one linked project. If this hook
    // ever regressed to fetching everything and filtering client-side, only the first page
    // would be searched and this project could be silently missed.
    const filler = Array.from({ length: 150 }, (_, i) => mkProject(`filler-${i}`, null));
    mockServerFilteredBy([...filler, mkProject('linked', 'book-1')]);
    renderHarness('book-1');
    await waitFor(() => expect(screen.getByTestId('project-id').textContent).toBe('linked'));
  });

  it('returns null when no project links to the book (standalone-only projects)', async () => {
    mockServerFilteredBy([mkProject('standalone-a', null), mkProject('standalone-b', null)]);
    renderHarness('book-1');
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));
    expect(screen.getByTestId('project-id').textContent).toBe('none');
  });

  it('re-resolves when bookId changes', async () => {
    mockServerFilteredBy([mkProject('p-a', 'book-a'), mkProject('p-b', 'book-b')]);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <Harness bookId="book-a" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('project-id').textContent).toBe('p-a'));

    rerender(
      <QueryClientProvider client={qc}>
        <Harness bookId="book-b" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('project-id').textContent).toBe('p-b'));
  });
});
