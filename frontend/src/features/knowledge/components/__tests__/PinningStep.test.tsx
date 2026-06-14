import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { GlossaryEntityStat } from '../../api';
import { PinningStep } from '../PinningStep';
import type { usePinning } from '../../hooks/usePinning';

// t returns the key (+ interpolations stripped) so assertions key off testids.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

function s(p: Partial<GlossaryEntityStat>): GlossaryEntityStat {
  return {
    entity_id: 'e',
    name: 'X',
    kind: 'character',
    mention_count: 1,
    first_chapter_index: 1,
    last_chapter_index: 1,
    coverage_pct: 0,
    ...p,
  };
}

type Pinning = ReturnType<typeof usePinning>;

function makePinning(over: Partial<Pinning>): Pinning {
  return {
    statsQuery: { isLoading: false, error: null } as never,
    chapterCount: 100,
    available: [],
    pinned: [],
    kinds: [],
    filter: { search: '', kind: '', minMentions: 0 },
    setFilter: vi.fn(),
    pin: vi.fn(),
    unpin: vi.fn(),
    applySuggestions: vi.fn(),
    reset: vi.fn(),
    pinnedIdList: [],
    pendingSuggestions: [],
    perWindowTokens: 0,
    ...over,
  } as Pinning;
}

describe('PinningStep', () => {
  it('renders available rows and pins on click', () => {
    const pin = vi.fn();
    const pinning = makePinning({
      available: [s({ entity_id: 'pangu', name: 'PanGu' })],
      pin,
    });
    render(<PinningStep pinning={pinning} />);
    expect(screen.getByTestId('pin-row-pangu')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('pin-pin-pangu'));
    expect(pin).toHaveBeenCalledWith('pangu');
  });

  it('renders the auto-pin banner when there are pending suggestions', () => {
    const applySuggestions = vi.fn();
    const pinning = makePinning({
      pendingSuggestions: ['pangu', 'nuwa'],
      applySuggestions,
    });
    render(<PinningStep pinning={pinning} />);
    expect(screen.getByTestId('autopin-banner')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('autopin-apply'));
    expect(applySuggestions).toHaveBeenCalled();
  });

  it('hides the auto-pin banner when nothing is pending', () => {
    render(<PinningStep pinning={makePinning({ pendingSuggestions: [] })} />);
    expect(screen.queryByTestId('autopin-banner')).not.toBeInTheDocument();
  });

  it('shows the per-window budget when entities are pinned', () => {
    const pinning = makePinning({
      pinned: [s({ entity_id: 'pangu', name: 'PanGu' })],
      pinnedIdList: ['pangu'],
      perWindowTokens: 50,
    });
    render(<PinningStep pinning={pinning} />);
    expect(screen.getByTestId('pinning-budget')).toBeInTheDocument();
  });

  it('unpins on click in the pinned list', () => {
    const unpin = vi.fn();
    const pinning = makePinning({
      pinned: [s({ entity_id: 'pangu', name: 'PanGu' })],
      pinnedIdList: ['pangu'],
      unpin,
    });
    render(<PinningStep pinning={pinning} />);
    fireEvent.click(screen.getByTestId('pin-unpin-pangu'));
    expect(unpin).toHaveBeenCalledWith('pangu');
  });

  it('degrades gracefully when stats are unavailable', () => {
    const pinning = makePinning({
      statsQuery: { isLoading: false, error: new Error('boom') } as never,
    });
    render(<PinningStep pinning={pinning} />);
    expect(screen.getByTestId('pinning-degraded')).toBeInTheDocument();
  });
});
