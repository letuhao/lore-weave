import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GroundingPanel } from '../GroundingPanel';
import type { Grounding, GroundingItem } from '../../types';

const { mockGrounding, setAction } = vi.hoisted(() => ({
  mockGrounding: { isLoading: false, data: undefined as unknown },
  setAction: vi.fn(),
}));
vi.mock('../../hooks/useWork', () => ({ useGrounding: () => mockGrounding }));
vi.mock('../../hooks/useGroundingPins', () => ({ useGroundingPins: () => ({ setAction, isPending: false }) }));

function grounding(over: Partial<Grounding> = {}): Grounding {
  return {
    blocks: {}, prompt: '', profile: { source_language: 'auto', voice: '', structure_pref: '' },
    token_count: 0, grounding_available: true, l4_dropped_no_position: 0, warnings: [],
    grounding_items: [], ...over,
  };
}

const item = (over: Partial<GroundingItem> & Pick<GroundingItem, 'type' | 'id'>): GroundingItem => ({
  label: 'x', pinned: false, excluded: false, ...over,
});

beforeEach(() => { setAction.mockReset(); mockGrounding.isLoading = false; mockGrounding.data = undefined; });

describe('GroundingPanel pin/exclude (T3.4)', () => {
  it('renders addressable items as rows; non-addressable blocks stay opaque, addressable ones are not duplicated', () => {
    mockGrounding.data = grounding({
      blocks: { present: 'Kael bio', lore: 'lore text', recent: 'prior prose' },
      grounding_items: [
        item({ type: 'present', id: 'g1', label: 'Kael: a knight' }),
        item({ type: 'lore', id: 'src1', label: 'a lore snippet' }),
      ],
    });
    render(<GroundingPanel projectId="p" sceneId="s" token="t" />);
    expect(screen.getByTestId('grounding-item-present-g1')).toBeTruthy();
    expect(screen.getByTestId('grounding-item-lore-src1')).toBeTruthy();
    // the non-addressable 'recent' block still renders…
    expect(screen.getByTestId('composition-grounding-block-recent')).toBeTruthy();
    // …but present/lore are shown as rows, NOT also as opaque blocks (no double-up)
    expect(screen.queryByTestId('composition-grounding-block-present')).toBeNull();
    expect(screen.queryByTestId('composition-grounding-block-lore')).toBeNull();
  });

  it('pin button calls setAction(item, "pin")', () => {
    const it0 = item({ type: 'present', id: 'g1' });
    mockGrounding.data = grounding({ grounding_items: [it0] });
    render(<GroundingPanel projectId="p" sceneId="s" token="t" />);
    fireEvent.click(screen.getByTestId('grounding-pin-g1'));
    expect(setAction).toHaveBeenCalledWith(it0, 'pin');
  });

  it('an already-pinned item un-pins (action "none")', () => {
    const it0 = item({ type: 'canon', id: 'r1', pinned: true });
    mockGrounding.data = grounding({ grounding_items: [it0] });
    render(<GroundingPanel projectId="p" sceneId="s" token="t" />);
    fireEvent.click(screen.getByTestId('grounding-pin-r1'));
    expect(setAction).toHaveBeenCalledWith(it0, 'none');
  });

  it('excluded row is dimmed and restores (action "none") on its exclude toggle', () => {
    const it0 = item({ type: 'lore', id: 'src1', excluded: true });
    mockGrounding.data = grounding({ grounding_items: [it0] });
    render(<GroundingPanel projectId="p" sceneId="s" token="t" />);
    expect(screen.getByTestId('grounding-item-lore-src1').className).toContain('opacity-50');
    fireEvent.click(screen.getByTestId('grounding-exclude-src1'));
    expect(setAction).toHaveBeenCalledWith(it0, 'none');
  });

  it('a non-excluded item excludes (action "exclude") on its exclude toggle', () => {
    const it0 = item({ type: 'present', id: 'g2' });
    mockGrounding.data = grounding({ grounding_items: [it0] });
    render(<GroundingPanel projectId="p" sceneId="s" token="t" />);
    fireEvent.click(screen.getByTestId('grounding-exclude-g2'));
    expect(setAction).toHaveBeenCalledWith(it0, 'exclude');
  });

  it('falls back to opaque addressable blocks when there are no grounding_items (legacy/derivative)', () => {
    mockGrounding.data = grounding({ blocks: { present: 'Kael bio', canon: 'rule' }, grounding_items: [] });
    render(<GroundingPanel projectId="p" sceneId="s" token="t" />);
    expect(screen.getByTestId('composition-grounding-block-present')).toBeTruthy();
    expect(screen.getByTestId('composition-grounding-block-canon')).toBeTruthy();
    expect(screen.queryByTestId('grounding-items-present')).toBeNull();
  });
});
