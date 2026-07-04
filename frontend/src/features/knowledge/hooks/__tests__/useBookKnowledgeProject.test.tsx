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

  it('resolves the project whose book_id matches the given book', async () => {
    listProjectsMock.mockResolvedValue({
      items: [mkProject('standalone', null), mkProject('linked', 'book-1')],
      next_cursor: null,
    });
    renderHarness('book-1');
    await waitFor(() => expect(screen.getByTestId('project-id').textContent).toBe('linked'));
    expect(screen.getByTestId('project-name').textContent).toBe('linked');
  });

  it('returns null when no project links to the book (standalone-only projects)', async () => {
    listProjectsMock.mockResolvedValue({
      items: [mkProject('standalone-a', null), mkProject('standalone-b', null)],
      next_cursor: null,
    });
    renderHarness('book-1');
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));
    expect(screen.getByTestId('project-id').textContent).toBe('none');
  });

  it('re-resolves when bookId changes', async () => {
    listProjectsMock.mockResolvedValue({
      items: [mkProject('p-a', 'book-a'), mkProject('p-b', 'book-b')],
      next_cursor: null,
    });
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
