import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

import { useProjects } from '../useProjects';
import type { Project } from '../../types';

function mkProject(id: string): Project {
  return { project_id: id, name: id } as Project;
}

// A tiny harness component that surfaces what the hook returns.
function Harness() {
  const { items, hasMore, loadMore } = useProjects(false);
  return (
    <div>
      <ul data-testid="items">
        {items.map((p) => (
          <li key={p.project_id}>{p.project_id}</li>
        ))}
      </ul>
      <span data-testid="count">{items.length}</span>
      <span data-testid="has-more">{String(hasMore)}</span>
      <button data-testid="more" onClick={() => void loadMore()}>
        more
      </button>
    </div>
  );
}

function renderHarness() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <Harness />
    </QueryClientProvider>,
  );
}

describe('useProjects — real cursor pagination', () => {
  beforeEach(() => {
    listProjectsMock.mockReset();
  });

  it('accumulates pages beyond the first via the BE cursor', async () => {
    // Page 1 → 2 rows + a next_cursor; page 2 → 1 row + null cursor.
    listProjectsMock.mockImplementation((params: { cursor?: string | null }) => {
      if (!params.cursor) {
        return Promise.resolve({
          items: [mkProject('a'), mkProject('b')],
          next_cursor: 'CUR2',
        });
      }
      return Promise.resolve({
        items: [mkProject('c')],
        next_cursor: null,
      });
    });

    renderHarness();

    // First page resolves: 2 items, more available.
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('2'));
    expect(screen.getByTestId('has-more').textContent).toBe('true');

    // Load the next page — the list must grow past page 1 (the
    // anti-fake-pagination requirement).
    fireEvent.click(screen.getByTestId('more'));
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('3'));
    expect(screen.getByText('c')).toBeDefined();
    // Cursor exhausted ⇒ no more pages.
    expect(screen.getByTestId('has-more').textContent).toBe('false');

    // The second call passed the cursor from page 1.
    const secondCall = listProjectsMock.mock.calls[1][0];
    expect(secondCall.cursor).toBe('CUR2');
  });

  it('reports hasMore=false when the first page already has a null cursor', async () => {
    listProjectsMock.mockResolvedValue({
      items: [mkProject('only')],
      next_cursor: null,
    });
    renderHarness();
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('1'));
    expect(screen.getByTestId('has-more').textContent).toBe('false');
  });
});
