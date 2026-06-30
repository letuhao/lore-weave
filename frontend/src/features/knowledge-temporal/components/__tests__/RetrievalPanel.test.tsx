import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RetrievalPanel } from '../RetrievalPanel';
import { useRetrieve } from '../../hooks/useTemporalReads';
import { useAsOf } from '../../context/AsOfContext';
import type { RetrieveResponse } from '../../types';

// i18n: honor the inline default fallback (2nd arg) the components pass — interpolate {{x}}.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, def?: string | object, opts?: Record<string, unknown>) => {
      const base = typeof def === 'string' ? def : _k;
      const vars = (typeof def === 'object' ? def : opts) as Record<string, unknown> | undefined;
      if (!vars) return base;
      return base.replace(/\{\{(\w+)\}\}/g, (_m, name) => String(vars[name] ?? ''));
    },
  }),
}));

vi.mock('../../hooks/useTemporalReads', () => ({
  useRetrieve: vi.fn(),
}));

vi.mock('../../context/AsOfContext', () => ({
  useAsOf: vi.fn(),
}));

const mockUseRetrieve = vi.mocked(useRetrieve);
const mockUseAsOf = vi.mocked(useAsOf);

type RetrieveReturn = {
  items: RetrieveResponse['items'];
  temporalCapability: RetrieveResponse['temporal_capability'];
  isLoading: boolean;
  error: Error | null;
};

function setRetrieve(partial: Partial<RetrieveReturn>) {
  mockUseRetrieve.mockReturnValue({
    items: [],
    temporalCapability: undefined,
    isLoading: false,
    error: null,
    ...partial,
  } as ReturnType<typeof useRetrieve>);
}

const PROPS = { bookId: 'book-123', entityId: 'ent-456' };

describe('RetrievalPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAsOf.mockReturnValue({ asOf: undefined, setAsOf: vi.fn() });
    setRetrieve({});
  });

  it('shows the type-to-search prompt and does NOT enable the fetch with an empty query', () => {
    render(<RetrievalPanel {...PROPS} />);
    expect(screen.getByTestId('retrieval-empty-prompt')).toBeInTheDocument();
    // body is null (query empty) → hook gated off
    expect(mockUseRetrieve).toHaveBeenLastCalledWith('book-123', null);
  });

  it('enables the fetch with the debounced query (passing as_of from context)', async () => {
    mockUseAsOf.mockReturnValue({ asOf: 7, setAsOf: vi.fn() });
    render(<RetrievalPanel {...PROPS} />);
    fireEvent.change(screen.getByTestId('retrieval-input'), {
      target: { value: 'sword' },
    });
    await waitFor(() => {
      expect(mockUseRetrieve).toHaveBeenLastCalledWith('book-123', {
        query: 'sword',
        as_of: 7,
      });
    });
  });

  it('renders a loading skeleton while fetching', async () => {
    setRetrieve({ isLoading: true });
    render(<RetrievalPanel {...PROPS} />);
    fireEvent.change(screen.getByTestId('retrieval-input'), {
      target: { value: 'mage' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('retrieval-loading')).toBeInTheDocument(),
    );
  });

  it('renders results with a relevance chip and chapter when present', async () => {
    setRetrieve({
      items: [
        { id: 's1', text: 'The hero drew the blade.', score: 0.82, chapter_id: 'ch-3' },
        { id: 's2', text: 'A quieter scene.', score: 0.41 },
      ],
    });
    render(<RetrievalPanel {...PROPS} />);
    fireEvent.change(screen.getByTestId('retrieval-input'), {
      target: { value: 'blade' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('retrieval-results')).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId('retrieval-result')).toHaveLength(2);
    expect(screen.getByText('The hero drew the blade.')).toBeInTheDocument();
    const chips = screen.getAllByTestId('retrieval-score');
    expect(chips[0]).toHaveTextContent('82%');
    // chapter only on the first row
    expect(screen.getAllByTestId('retrieval-chapter')).toHaveLength(1);
  });

  it('renders defensively when a segment has no text/score/chapter', async () => {
    setRetrieve({ items: [{ id: 's1' }] });
    render(<RetrievalPanel {...PROPS} />);
    fireEvent.change(screen.getByTestId('retrieval-input'), {
      target: { value: 'x' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('retrieval-result')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('retrieval-score')).not.toBeInTheDocument();
    expect(screen.queryByTestId('retrieval-chapter')).not.toBeInTheDocument();
  });

  it('shows the empty (no-results) state', async () => {
    setRetrieve({ items: [] });
    render(<RetrievalPanel {...PROPS} />);
    fireEvent.change(screen.getByTestId('retrieval-input'), {
      target: { value: 'nothing' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('retrieval-no-results')).toBeInTheDocument(),
    );
  });

  it('shows the temporal-unsupported note when the KG cannot honor as_of', async () => {
    setRetrieve({
      items: [{ id: 's1', text: 'hi', score: 0.5 }],
      temporalCapability: { kg: 'temporal_unsupported' },
    });
    render(<RetrievalPanel {...PROPS} />);
    fireEvent.change(screen.getByTestId('retrieval-input'), {
      target: { value: 'hello' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('retrieval-temporal-note')).toBeInTheDocument(),
    );
  });

  it('hides the temporal note when the KG DOES honor as_of', async () => {
    setRetrieve({
      items: [{ id: 's1', text: 'hi', score: 0.5 }],
      temporalCapability: { kg: 'ordinal_valid_time' },
    });
    render(<RetrievalPanel {...PROPS} />);
    fireEvent.change(screen.getByTestId('retrieval-input'), {
      target: { value: 'hello' },
    });
    // wait for the debounced query to land (results appear), then assert no note
    await waitFor(() =>
      expect(screen.getByTestId('retrieval-results')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('retrieval-temporal-note')).not.toBeInTheDocument();
  });

  it('shows the error state', async () => {
    setRetrieve({ error: new Error('boom') });
    render(<RetrievalPanel {...PROPS} />);
    fireEvent.change(screen.getByTestId('retrieval-input'), {
      target: { value: 'q' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('retrieval-error')).toHaveTextContent('boom'),
    );
  });
});
