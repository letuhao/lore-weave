import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EpisodeTranslationPanel } from '../EpisodeTranslationPanel';
import { useCanonical, useCanonicalTranslation } from '../../hooks/useTemporalReads';
import { useAsOf } from '../../context/AsOfContext';
import { useGlossaryDisplayLanguage } from '@/features/glossary/hooks/useGlossaryDisplayLanguage';
import type { CanonicalSnapshot, CanonicalTranslation } from '../../types';

// i18n stub that honors BOTH the (key, 'Default {{x}}', opts) and the (key, {x, defaultValue}) forms.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, def?: string | Record<string, unknown>, opts?: Record<string, unknown>) => {
      const vars = (typeof def === 'object' ? def : opts) as Record<string, unknown> | undefined;
      const base =
        typeof def === 'string'
          ? def
          : (vars?.defaultValue as string | undefined) ?? _k;
      if (!vars) return base;
      return base.replace(/\{\{(\w+)\}\}/g, (_m, name) => String(vars[name] ?? ''));
    },
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: (opts: { queryKey: unknown[] }) => {
    const key = opts.queryKey[0];
    if (key === 'book-orig-lang') return { data: { original_language: 'zh' } };
    if (key === 'glossary-translation-languages') return { data: { languages: ['en', 'vi'] } };
    return { data: undefined };
  },
}));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }) }));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: { listTranslationLanguages: vi.fn() } }));
vi.mock('@/features/books/api', () => ({ booksApi: { getBook: vi.fn() } }));
vi.mock('@/features/glossary/hooks/useGlossaryDisplayLanguage', () => ({
  useGlossaryDisplayLanguage: vi.fn(),
}));
vi.mock('../../hooks/useTemporalReads', () => ({
  useCanonical: vi.fn(),
  useCanonicalTranslation: vi.fn(),
}));
vi.mock('../../context/AsOfContext', () => ({ useAsOf: vi.fn() }));

const mockCanonical = vi.mocked(useCanonical);
const mockCanonicalTr = vi.mocked(useCanonicalTranslation);
const mockAsOf = vi.mocked(useAsOf);
const mockDisplayLang = vi.mocked(useGlossaryDisplayLanguage);
const setDisplayLanguage = vi.fn();

function setCanonical(canonical: CanonicalSnapshot | null, extra: Partial<ReturnType<typeof useCanonical>> = {}) {
  mockCanonical.mockReturnValue({ canonical, isLoading: false, error: null, ...extra } as ReturnType<typeof useCanonical>);
}
function setTranslation(translation: CanonicalTranslation | null, extra: Partial<ReturnType<typeof useCanonicalTranslation>> = {}) {
  mockCanonicalTr.mockReturnValue({ translation, isLoading: false, error: null, ...extra } as ReturnType<typeof useCanonicalTranslation>);
}
function setLang(displayLanguage: string, apiDisplayLanguage: string | undefined) {
  mockDisplayLang.mockReturnValue({ displayLanguage, setDisplayLanguage, apiDisplayLanguage, loaded: true });
}

const PROPS = { bookId: 'book-123', entityId: 'ent-456' };

describe('EpisodeTranslationPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAsOf.mockReturnValue({ asOf: undefined, setAsOf: vi.fn() });
    setCanonical({ entity_id: 'ent-456', content: '李四，金丹期修士。' });
    setTranslation(null);
    setLang('zh', undefined); // default: original/as-authored selected
  });

  it('shows the ORIGINAL canonical when the selected language is the source (no LLM call)', () => {
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-content')).toHaveTextContent('李四，金丹期修士。');
    expect(mockCanonical).toHaveBeenLastCalledWith('book-123', 'ent-456', undefined);
    // translation hook is called but disabled (apiDisplayLanguage undefined)
    expect(mockCanonicalTr).toHaveBeenLastCalledWith('book-123', 'ent-456', undefined, undefined);
    expect(screen.queryByTestId('episode-translation-badge')).not.toBeInTheDocument();
  });

  it('renders the translated content + cached badge when ready', () => {
    setLang('en', 'en');
    setTranslation({
      entity_id: 'ent-456', language_code: 'en', content: 'Li Si, a Golden Core cultivator.',
      translated: true, status: 'ready', cached: true,
    });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-content')).toHaveTextContent('Li Si, a Golden Core cultivator.');
    expect(screen.getByTestId('episode-translation-badge')).toHaveTextContent('cached');
    expect(mockCanonicalTr).toHaveBeenLastCalledWith('book-123', 'ent-456', 'en', undefined);
  });

  it('shows the translating indicator (with original content) while the fill runs', () => {
    setLang('en', 'en');
    setTranslation({
      entity_id: 'ent-456', language_code: 'en', content: '李四，金丹期修士。', translated: false, status: 'translating',
    });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-translating')).toBeInTheDocument();
    expect(screen.getByTestId('episode-translation-content')).toHaveTextContent('李四，金丹期修士。');
  });

  it('shows a "set a translation model" message on a no_model failure', () => {
    setLang('en', 'en');
    setTranslation({
      entity_id: 'ent-456', language_code: 'en', content: '李四，金丹期修士。', translated: false,
      status: 'failed', error_code: 'no_model',
    });
    render(<EpisodeTranslationPanel {...PROPS} />);
    const failed = screen.getByTestId('episode-translation-failed');
    expect(failed).toHaveTextContent(/Translation Settings/i);
    // still shows the original context underneath
    expect(screen.getByTestId('episode-translation-content')).toHaveTextContent('李四，金丹期修士。');
  });

  it('renders the empty state on an unbuildable translation', () => {
    setLang('en', 'en');
    setTranslation({ entity_id: 'ent-456', language_code: 'en', content: '', translated: false, status: 'unbuildable' });
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('episode-translation-content')).not.toBeInTheDocument();
  });

  it('renders the language selector (Original + coverage langs) and commits a change', () => {
    render(<EpisodeTranslationPanel {...PROPS} />);
    const select = screen.getByTestId('episode-translation-language') as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(['zh', 'en', 'vi']); // original (zh) first, then coverage
    fireEvent.change(select, { target: { value: 'en' } });
    expect(setDisplayLanguage).toHaveBeenCalledWith('en');
  });

  it('labels the as-of (head → latest, ordinal → chapter N)', () => {
    const { rerender } = render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-asof')).toHaveTextContent('latest');
    mockAsOf.mockReturnValue({ asOf: 5, setAsOf: vi.fn() });
    rerender(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.getByTestId('episode-translation-asof')).toHaveTextContent('chapter 5');
  });

  it('no longer renders the old honest pending-note (the feature is real now)', () => {
    render(<EpisodeTranslationPanel {...PROPS} />);
    expect(screen.queryByTestId('episode-translation-pending-note')).not.toBeInTheDocument();
  });
});
