import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// S-11 — the studio-host extensions to the reused RawSearchPanel: an injected onJump (open the
// in-dock editor instead of navigating to the reader route) + an initialQuery seed. The rest of
// RawSearchPanel's behaviour is unchanged and covered elsewhere.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k, i18n: { language: 'en' } }),
}));

const navigate = vi.hoisted(() => vi.fn());
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

const raw = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../hooks/useRawSearch', () => ({ useRawSearch: () => raw.value }));
vi.mock('../../hooks/useIndexDrafts', () => ({
  useIndexDrafts: () => ({ isOwner: false, indexDrafts: vi.fn(), isIndexing: false, result: null, error: null }),
}));
vi.mock('../../hooks/useDebouncedValue', () => ({ useDebouncedValue: (v: string) => v }));

// Stub the result card to a button that fires the panel's onJump with a known chapter/block.
vi.mock('../RawSearchResultCard', () => ({
  RawSearchResultCard: ({ onJump }: { onJump: (c: string, b?: number) => void }) => (
    <button data-testid="stub-jump" onClick={() => onJump('ch-x', 2)}>jump</button>
  ),
}));

import { RawSearchPanel } from '../RawSearchPanel';

const ONE_HIT = { hits: [{ chapterId: 'ch-x', matchType: 'lexical', location: { blockIndex: 2 } }], disabled: false, isFetching: false, error: null, degraded: {} };

describe('RawSearchPanel — S-11 studio host extensions', () => {
  beforeEach(() => {
    navigate.mockClear();
    raw.value = ONE_HIT;
  });

  it('initialQuery seeds the query box', () => {
    render(<RawSearchPanel bookId="b-1" initialQuery="the tower" />);
    expect(screen.getByTestId('raw-search-input')).toHaveValue('the tower');
  });

  it('with an injected onJump, a hit calls it instead of navigating to the reader route', () => {
    const onJump = vi.fn();
    render(<RawSearchPanel bookId="b-1" onJump={onJump} />);
    fireEvent.click(screen.getByTestId('stub-jump'));
    expect(onJump).toHaveBeenCalledWith('ch-x', 2);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('without onJump (standalone page), a hit navigates to the reader route (unchanged default)', () => {
    render(<RawSearchPanel bookId="b-1" />);
    fireEvent.click(screen.getByTestId('stub-jump'));
    expect(navigate).toHaveBeenCalledWith('/books/b-1/chapters/ch-x/read?block=2');
  });
});
