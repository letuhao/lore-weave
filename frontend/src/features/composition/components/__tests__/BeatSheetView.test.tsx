import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BeatSheetView, buildBeatSheet } from '../BeatSheetView';
import type { OutlineNode, StructureTemplate } from '../../types';

const { tplHook, outlineHook, setBeatRole, invalidate, navigateFn } = vi.hoisted(() => ({
  tplHook: vi.fn(), outlineHook: vi.fn(), setBeatRole: { mutate: vi.fn() }, invalidate: vi.fn(), navigateFn: vi.fn(),
}));
vi.mock('../../hooks/usePlanner', () => ({ useStructureTemplates: () => tplHook() }));
vi.mock('../../hooks/useOutline', () => ({
  useOutline: () => outlineHook(),
  useOutlineMutations: () => ({ setBeatRole, invalidate }),
}));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateFn }));

function node(over: Partial<OutlineNode>): OutlineNode {
  return {
    id: 'n', project_id: 'p', parent_id: null, kind: 'scene', rank: 'm', title: 'T',
    chapter_id: null, story_order: 0, status: 'outline', synopsis: '', version: 1, is_archived: false, beat_role: null, ...over,
  };
}

const template: StructureTemplate = {
  id: 't1', name: 'Save the Cat',
  beats: [{ key: 'opening', purpose: 'set the tone' }, { key: 'catalyst', purpose: 'kick it off' }],
};
const nodes: OutlineNode[] = [
  node({ id: 's1', kind: 'scene', chapter_id: 'C1', beat_role: 'opening', status: 'done', title: 'Arrival' }),
  node({ id: 'ch1', kind: 'chapter', chapter_id: 'C2', beat_role: 'catalyst', status: 'outline', title: 'Ch2' }),
  node({ id: 's2', kind: 'scene', chapter_id: 'C1', beat_role: null, title: 'Loose' }),
  node({ id: 's3', kind: 'scene', chapter_id: 'C1', beat_role: 'stale_key', title: 'Stale' }), // beat_role not in template → unmapped
  node({ id: 'arx', kind: 'arc', beat_role: null, title: 'Arc' }), // arcs never participate
];

describe('buildBeatSheet (T1.2)', () => {
  it('joins beats↔beat_role, derives fill-state, and collects unmapped (null + stale key)', () => {
    const { beats, unmapped } = buildBeatSheet(template, nodes);
    expect(beats.map((b) => b.beat.key)).toEqual(['opening', 'catalyst']); // template order
    expect(beats[0].nodes.map((n) => n.id)).toEqual(['s1']);
    expect(beats[0].state).toBe('drafted'); // s1 done
    expect(beats[1].nodes.map((n) => n.id)).toEqual(['ch1']); // a chapter maps too
    expect(beats[1].state).toBe('empty'); // ch1 outline, not started
    expect(unmapped.map((n) => n.id)).toEqual(['s2', 's3']); // null + stale key; arc excluded
  });

  it('reports unplaced for a beat with no node, writing when one is in progress', () => {
    const { beats } = buildBeatSheet(template, [node({ id: 'x', beat_role: 'opening', status: 'drafting' })]);
    expect(beats[0].state).toBe('writing'); // drafting
    expect(beats[1].state).toBe('unplaced'); // no node maps to catalyst
  });

  it('returns empty for no template', () => {
    expect(buildBeatSheet(null, nodes)).toEqual({ beats: [], unmapped: [] });
  });
});

describe('BeatSheetView (T1.2)', () => {
  beforeEach(() => {
    setBeatRole.mutate.mockReset(); invalidate.mockReset(); navigateFn.mockReset();
    tplHook.mockReturnValue({ data: [template] });
    outlineHook.mockReturnValue({ data: nodes });
  });

  it('prompts to pick a template, then renders a card per beat with its state', () => {
    render(<BeatSheetView bookId="b" projectId="p" token="t" />);
    expect(screen.getByTestId('beats-empty')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('beats-template-select'), { target: { value: 't1' } });
    const cards = screen.getAllByTestId('beat-card');
    expect(cards.map((c) => c.getAttribute('data-beat'))).toEqual(['opening', 'catalyst']);
    expect(cards[0].getAttribute('data-state')).toBe('drafted');
  });

  it('assigns a beat via the a11y <select> (sends beat_role + version)', () => {
    render(<BeatSheetView bookId="b" projectId="p" token="t" />);
    fireEvent.change(screen.getByTestId('beats-template-select'), { target: { value: 't1' } });
    // the first mapped node chip is s1 (under "opening"); reassign it to catalyst
    fireEvent.change(screen.getAllByTestId('beat-node-select')[0], { target: { value: 'catalyst' } });
    expect(setBeatRole.mutate).toHaveBeenCalledWith(
      { nodeId: 's1', beatRole: 'catalyst', version: 1 },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
  });

  it('clears a beat via the unmap ✕ (beat_role → null)', () => {
    render(<BeatSheetView bookId="b" projectId="p" token="t" />);
    fireEvent.change(screen.getByTestId('beats-template-select'), { target: { value: 't1' } });
    fireEvent.click(screen.getAllByTestId('beat-node-unmap')[0]); // s1
    expect(setBeatRole.mutate).toHaveBeenCalledWith(
      { nodeId: 's1', beatRole: null, version: 1 },
      expect.objectContaining({ onError: expect.any(Function) }),
    );
  });

  it('jumps to a node’s chapter on click', () => {
    render(<BeatSheetView bookId="b" projectId="p" token="t" />);
    fireEvent.change(screen.getByTestId('beats-template-select'), { target: { value: 't1' } });
    fireEvent.click(screen.getAllByTestId('beat-node-open')[0]); // s1 → chapter C1
    expect(navigateFn).toHaveBeenCalledWith('/books/b/chapters/C1/edit');
  });
});
