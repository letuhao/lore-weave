import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: {
      user_id: 'u1',
      email: 'a@b',
      display_name: null,
      avatar_url: null,
    },
  }),
}));

const searchDrawersMock = vi.fn();
const listProjectsMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      searchDrawers: (...args: unknown[]) => searchDrawersMock(...args),
      listProjects: (...args: unknown[]) => listProjectsMock(...args),
    },
  };
});

import { RawDrawersTab } from '../RawDrawersTab';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const HIT_DUEL = {
  id: 'pg-duel',
  project_id: 'p-1',
  source_type: 'chapter',
  source_id: 'ch-12-aaaa-bbbb',
  chunk_index: 0,
  text:
    'The bridge was slick with rain when Kai unsheathed his blade and ' +
    'called out Zhao.',
  is_hub: false,
  chapter_index: 12,
  created_at: null,
  raw_score: 0.87,
};

const HIT_REVEAL = {
  ...HIT_DUEL,
  id: 'pg-reveal',
  text: 'Master Kai whispered the forgotten name to the sky.',
  raw_score: 0.73,
};

class ApiError extends Error {
  status: number;
  body: { detail: { error_code: string; message: string; retryable: boolean } };
  constructor(
    status: number,
    errorCode: string,
    message: string,
    retryable: boolean,
  ) {
    super(message);
    this.status = status;
    this.body = {
      detail: { error_code: errorCode, message, retryable },
    };
  }
}

async function selectProject(projectId: string): Promise<HTMLSelectElement> {
  // useProjects loads async; the project options aren't in the DOM on
  // first render. Wait for an option to appear before firing the
  // change event — otherwise the change silently falls back to the
  // blank value and the filter never updates.
  await screen.findByRole('option', { name: 'Crimson Echoes' });
  const select = screen.getByTestId(
    'drawers-filter-project',
  ) as HTMLSelectElement;
  fireEvent.change(select, { target: { value: projectId } });
  return select;
}

describe('RawDrawersTab', () => {
  beforeEach(() => {
    searchDrawersMock.mockReset();
    listProjectsMock.mockReset();
    listProjectsMock.mockResolvedValue({
      items: [
        { project_id: 'p-1', name: 'Crimson Echoes' },
      ],
      next_cursor: null,
    });
  });

  it('renders the no-project prompt before any project is selected', async () => {
    render(<RawDrawersTab />, { wrapper: Wrapper });
    await screen.findByTestId('drawers-no-project');
    expect(searchDrawersMock).not.toHaveBeenCalled();
  });

  it('renders the short-query hint for queries below min length', async () => {
    searchDrawersMock.mockResolvedValue({
      hits: [],
      embedding_model: 'bge-m3',
    });
    render(<RawDrawersTab />, { wrapper: Wrapper });
    await selectProject('p-1');
    fireEvent.change(screen.getByTestId('drawers-search-input'), {
      target: { value: 'ab' },
    });
    await screen.findByTestId('drawers-short-query');
    expect(searchDrawersMock).not.toHaveBeenCalled();
  });

  it('renders hits and opens the detail slide-over on click', async () => {
    searchDrawersMock.mockResolvedValue({
      hits: [HIT_DUEL, HIT_REVEAL],
      embedding_model: 'bge-m3',
    });
    render(<RawDrawersTab />, { wrapper: Wrapper });
    await selectProject('p-1');
    fireEvent.change(screen.getByTestId('drawers-search-input'), {
      target: { value: 'bridge duel' },
    });
    const cards = await screen.findAllByTestId('drawer-result-card');
    expect(cards).toHaveLength(2);
    expect(screen.queryByTestId('drawer-detail-panel')).toBeNull();
    fireEvent.click(cards[0]);
    await screen.findByTestId('drawer-detail-panel');
    // Close button resets state.
    fireEvent.click(screen.getByTestId('drawer-detail-close'));
    await waitFor(() => {
      expect(screen.queryByTestId('drawer-detail-panel')).toBeNull();
    });
  });

  it('renders the not-indexed banner when embedding_model is null', async () => {
    searchDrawersMock.mockResolvedValue({
      hits: [],
      embedding_model: null,
    });
    render(<RawDrawersTab />, { wrapper: Wrapper });
    await selectProject('p-1');
    fireEvent.change(screen.getByTestId('drawers-search-input'), {
      target: { value: 'bridge' },
    });
    await screen.findByTestId('drawers-not-indexed');
  });

  it('shows Retry button for retryable 502 and refetches on click', async () => {
    searchDrawersMock.mockRejectedValueOnce(
      new ApiError(502, 'provider_error', 'timeout', true),
    );
    render(<RawDrawersTab />, { wrapper: Wrapper });
    await selectProject('p-1');
    fireEvent.change(screen.getByTestId('drawers-search-input'), {
      target: { value: 'bridge' },
    });
    const retry = await screen.findByTestId('drawers-retry');
    // Now set up a success response for the retry.
    searchDrawersMock.mockResolvedValueOnce({
      hits: [HIT_DUEL],
      embedding_model: 'bge-m3',
    });
    fireEvent.click(retry);
    await screen.findByTestId('drawers-list');
  });

  it('debounces rapid keystrokes into a single BE call (review-impl L1)', async () => {
    // Guard against a regression that drops SEARCH_DEBOUNCE_MS to 0
    // or accidentally removes the useDebounced wrapper — either would
    // fire one BE embed call per keystroke. We fire 5 rapid
    // ``fireEvent.change`` events synchronously (well within the
    // 300 ms debounce window), then wait for the BE to be called at
    // all. The test DOES use real timers — fake timers interact badly
    // with react-query's internal setTimeout-based state machine and
    // lead to cross-test timeouts.
    searchDrawersMock.mockResolvedValue({
      hits: [],
      embedding_model: 'bge-m3',
    });
    render(<RawDrawersTab />, { wrapper: Wrapper });
    await selectProject('p-1');
    const input = screen.getByTestId('drawers-search-input');
    fireEvent.change(input, { target: { value: 'b' } });
    fireEvent.change(input, { target: { value: 'br' } });
    fireEvent.change(input, { target: { value: 'bri' } });
    fireEvent.change(input, { target: { value: 'brid' } });
    fireEvent.change(input, { target: { value: 'bridge' } });
    await waitFor(
      () => {
        expect(searchDrawersMock).toHaveBeenCalled();
      },
      { timeout: 1500 },
    );
    // Only ONE BE call survives — not 5. If a regression set the
    // debounce to 0 ms, each of the five onChange events would have
    // triggered its own call and this assertion would fail.
    expect(searchDrawersMock).toHaveBeenCalledTimes(1);
    expect(searchDrawersMock.mock.calls[0][0]).toEqual(
      expect.objectContaining({ project_id: 'p-1', query: 'bridge' }),
    );
  });

  it('shows fix-config hint (no Retry button) for non-retryable 502', async () => {
    searchDrawersMock.mockRejectedValueOnce(
      new ApiError(
        502,
        'embedding_dim_mismatch',
        'dim mismatch',
        false,
      ),
    );
    render(<RawDrawersTab />, { wrapper: Wrapper });
    await selectProject('p-1');
    fireEvent.change(screen.getByTestId('drawers-search-input'), {
      target: { value: 'bridge' },
    });
    await screen.findByTestId('drawers-error');
    expect(screen.queryByTestId('drawers-retry')).toBeNull();
  });
});
