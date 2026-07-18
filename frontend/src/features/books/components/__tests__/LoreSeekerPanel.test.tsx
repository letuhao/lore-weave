import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LoreSeekerPanel } from '../LoreSeekerPanel';

// W11 lore-seeker — mocks the controller and proves the SPOILER GATE by effect: a reader with no
// position sees NO facts (fail-closed), an empty window shows "nothing revealed yet", and a
// windowed read renders exactly the facts the server returned (which are already chapter-limited).
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock('../../hooks/useLoreSeeker', () => ({ useLoreSeeker: (...a: unknown[]) => hook(...a) }));

const base = {
  projectId: 'p1',
  query: '',
  setQuery: vi.fn(),
  entities: [{ id: 'e1', name: 'Lâm Uyên', kind: 'character' }],
  isEntitiesLoading: false,
  selectedId: 'e1',
  select: vi.fn(),
  facts: [],
  windowAvailable: false,
  isFactsLoading: false,
  hasPosition: true,
};

describe('LoreSeekerPanel', () => {
  it('a reader with NO position sees no facts (fail-closed)', () => {
    hook.mockReturnValue({ ...base, hasPosition: false });
    render(<LoreSeekerPanel bookId="b1" chapterId="" />);
    expect(screen.getByTestId('lore-no-position')).toBeInTheDocument();
    expect(screen.queryByTestId('lore-fact-f1')).not.toBeInTheDocument();
  });

  it('an empty window (nothing revealed by this chapter) shows the keep-reading hint', () => {
    hook.mockReturnValue({ ...base, hasPosition: true, facts: [] });
    render(<LoreSeekerPanel bookId="b1" chapterId="c3" />);
    expect(screen.getByTestId('lore-nothing-yet')).toBeInTheDocument();
  });

  it('renders exactly the windowed facts the server returned', () => {
    hook.mockReturnValue({
      ...base,
      facts: [
        { id: 'f1', type: 'milestone', content: 'Married at the shrine.', confidence: 0.9, source_chapter: null, from_order: 1 },
      ],
      windowAvailable: true,
    });
    render(<LoreSeekerPanel bookId="b1" chapterId="c1" />);
    expect(screen.getByTestId('lore-fact-f1')).toHaveTextContent('Married at the shrine.');
    // and crucially NOT the no-position / nothing-yet fallbacks
    expect(screen.queryByTestId('lore-no-position')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lore-nothing-yet')).not.toBeInTheDocument();
  });

  it('typing in the search box drives the controller query', () => {
    const setQuery = vi.fn();
    hook.mockReturnValue({ ...base, setQuery });
    render(<LoreSeekerPanel bookId="b1" chapterId="c1" />);
    fireEvent.change(screen.getByTestId('lore-search'), { target: { value: 'Uyên' } });
    expect(setQuery).toHaveBeenCalledWith('Uyên');
  });
});
