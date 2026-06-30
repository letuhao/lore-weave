import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EpisodeTranslationPanel } from '../EpisodeTranslationPanel';
import { useCanonical } from '../../hooks/useTemporalReads';
import { useAsOf } from '../../context/AsOfContext';
import type { CanonicalSnapshot } from '../../types';

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
  useCanonical: vi.fn(),
}));

vi.mock('../../context/AsOfContext', () => ({
  useAsOf: vi.fn(),
}));

const mockUseCanonical = vi.mocked(useCanonical);
const mockUseAsOf = vi.mocked(useAsOf);

type CanonicalReturn = {
  canonical: CanonicalSnapshot | null;
  isLoading: boolean;
  error: Error | null;
};

function setCanonical(partial: Partial<CanonicalReturn>) {
  mockUseCanonical.mockReturnValue({
    canonical: null,
    isLoading: false,
    error: null,
    ...partial,
  } as ReturnType<typeof useCanonical>);
}

const PROPS = { bookId: 'book-123', entityId: 'ent-456' };

describe('EpisodeTranslationPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAsOf.mockReturnValue({ asOf: undefined, setAsOf: vi.fn() });
    setCanonical({});
  });

  it('always renders the honest pending-translation note', () => {
    setCanonical({ canonical: { entity_id: 'ent-456', content: 'some context' } });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-pending-note')).toBeInTheDocument();
  });

  it('renders the as-of canonical content as the temporal context', () => {
    setCanonical({
      canonical: { entity_id: 'ent-456', content: 'The mage at chapter 5.' },
    });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-content')).toHaveTextContent(
      'The mage at chapter 5.',
    );
  });

  it('passes the as_of from context to useCanonical and labels it', () => {
    mockUseAsOf.mockReturnValue({ asOf: 5, setAsOf: vi.fn() });
    setCanonical({ canonical: { entity_id: 'ent-456', content: 'x' } });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(mockUseCanonical).toHaveBeenLastCalledWith('book-123', 'ent-456', 5);
    expect(screen.getByTestId('episode-translation-asof')).toHaveTextContent('chapter 5');
  });

  it('labels the head as latest when as_of is undefined', () => {
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(mockUseCanonical).toHaveBeenLastCalledWith('book-123', 'ent-456', undefined);
    expect(screen.getByTestId('episode-translation-asof')).toHaveTextContent('latest');
  });

  it('renders a loading skeleton', () => {
    setCanonical({ isLoading: true });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('episode-translation-content')).not.toBeInTheDocument();
  });

  it('renders the error state', () => {
    setCanonical({ error: new Error('kaboom') });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-error')).toHaveTextContent('kaboom');
  });

  it('renders the empty state when canonical content is blank', () => {
    setCanonical({ canonical: { entity_id: 'ent-456', content: '   ' } });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-empty')).toBeInTheDocument();
    // and the pending note is still present (honesty over a fake feature)
    expect(screen.getByTestId('episode-translation-pending-note')).toBeInTheDocument();
  });

  it('does NOT fabricate translated text — content is only the canonical snapshot', () => {
    setCanonical({ canonical: null });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.queryByTestId('episode-translation-content')).not.toBeInTheDocument();
    expect(screen.getByTestId('episode-translation-empty')).toBeInTheDocument();
  });
});
