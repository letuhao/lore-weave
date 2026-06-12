import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Corkboard, groupScenesByChapter, computeCardMove, type ChapterBand } from '../Corkboard';
import type { OutlineNode } from '../../types';

function node(over: Partial<OutlineNode>): OutlineNode {
  return {
    id: 'n', project_id: 'p', parent_id: null, kind: 'scene', rank: 'm', title: 'T',
    chapter_id: null, story_order: 0, status: 'outline', synopsis: '', version: 1, is_archived: false, ...over,
  };
}

// arc1 > { ch1 > [s1,s2], ch2 > [] }  (+ an archived scene that must be excluded)
const nodes: OutlineNode[] = [
  node({ id: 'arc1', kind: 'arc', parent_id: null, rank: 'a' }),
  node({ id: 'ch1', kind: 'chapter', parent_id: 'arc1', chapter_id: 'C1', rank: 'a', title: 'Ch1' }),
  node({ id: 'ch2', kind: 'chapter', parent_id: 'arc1', chapter_id: 'C2', rank: 'b', title: 'Ch2' }),
  node({ id: 's2', kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', story_order: 1, title: 'S2' }),
  node({ id: 's1', kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', story_order: 0, title: 'S1' }),
  node({ id: 'sx', kind: 'scene', parent_id: 'ch1', chapter_id: 'C1', story_order: 5, is_archived: true }),
];

describe('groupScenesByChapter (T1.1d)', () => {
  it('groups scenes under chapters in tree order, scenes by story_order, archived excluded', () => {
    const bands = groupScenesByChapter(nodes);
    expect(bands.map((b) => b.chapter.id)).toEqual(['ch1', 'ch2']); // chapters in rank order
    expect(bands[0].scenes.map((s) => s.id)).toEqual(['s1', 's2']); // story_order 0,1; archived sx dropped
    expect(bands[1].scenes).toEqual([]); // empty chapter still gets a band
  });
});

describe('computeCardMove (T1.1d)', () => {
  const bands = groupScenesByChapter(nodes);

  it('reorders within a chapter with arrayMove semantics (drop s2 onto s1 → first; drop s1 onto s2 → after s2)', () => {
    expect(computeCardMove(bands, 's2', 's1')).toEqual({ nodeId: 's2', new_parent_id: 'ch1', after_id: null });
    // downward drag: s1 takes s2's slot → lands AFTER s2 (not a no-op)
    expect(computeCardMove(bands, 's1', 's2')).toEqual({ nodeId: 's1', new_parent_id: 'ch1', after_id: 's2' });
  });

  it('reparents across chapters by dropping on an empty band (append)', () => {
    expect(computeCardMove(bands, 's1', 'band:ch2')).toEqual({ nodeId: 's1', new_parent_id: 'ch2', after_id: null });
  });

  it('reparents by dropping onto a card in another chapter', () => {
    // move s1 (ch1) onto s2 (ch1) is same-chapter; build a 2-chapter-with-cards case
    const b2: ChapterBand[] = [
      { chapter: node({ id: 'ca', kind: 'chapter' }), scenes: [node({ id: 'a1', parent_id: 'ca' })] },
      { chapter: node({ id: 'cb', kind: 'chapter' }), scenes: [node({ id: 'b1', parent_id: 'cb' }), node({ id: 'b2', parent_id: 'cb' })] },
    ];
    expect(computeCardMove(b2, 'a1', 'b2')).toEqual({ nodeId: 'a1', new_parent_id: 'cb', after_id: 'b1' });
  });

  it('returns null for a no-op (same node) and unknown ids', () => {
    expect(computeCardMove(bands, 's2', 's2')).toBeNull();
    expect(computeCardMove(bands, 'ghost', 's1')).toBeNull();
    expect(computeCardMove(bands, 's1', 'ghost')).toBeNull();
  });
});

describe('Corkboard component (T1.1d)', () => {
  const handlers = () => ({
    onSelect: vi.fn(), onAddCard: vi.fn(), onEditStart: vi.fn(), onEditCommit: vi.fn(),
    onEditCancel: vi.fn(), onArchive: vi.fn(), onCycleStatus: vi.fn(), onReorder: vi.fn(),
  });

  it('renders cards grouped into chapter bands + an empty band, and add-card fires', () => {
    const h = handlers();
    render(<Corkboard nodes={nodes} editingId={null} draggable {...h} />);
    expect(screen.getAllByTestId('corkboard-band')).toHaveLength(2);
    expect(screen.getAllByTestId('corkboard-card')).toHaveLength(2); // s1, s2 (archived excluded)
    expect(screen.getByTestId('corkboard-empty-band')).toBeInTheDocument(); // ch2 has no scenes
    fireEvent.click(screen.getAllByTestId('corkboard-add-card')[0]);
    expect(h.onAddCard).toHaveBeenCalledWith(expect.objectContaining({ id: 'ch1' }));
  });

  it('opens a scene on card click and cycles status', () => {
    const h = handlers();
    render(<Corkboard nodes={nodes} editingId={null} draggable {...h} />);
    fireEvent.click(screen.getAllByTestId('corkboard-card-open')[0]);
    expect(h.onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 's1' }));
    fireEvent.click(screen.getAllByTestId('corkboard-card-status')[0]);
    expect(h.onCycleStatus).toHaveBeenCalledWith(expect.objectContaining({ id: 's1' }), 'drafting'); // outline → drafting
  });

  it('edits a card (title + synopsis) on save', () => {
    const h = handlers();
    render(<Corkboard nodes={nodes} editingId="s1" draggable {...h} />);
    const title = screen.getByTestId('corkboard-card-title-input') as HTMLInputElement;
    const syn = screen.getByTestId('corkboard-card-synopsis-input') as HTMLTextAreaElement;
    fireEvent.change(title, { target: { value: 'New' } });
    fireEvent.change(syn, { target: { value: 'a synopsis' } });
    fireEvent.click(screen.getByTestId('corkboard-card-save'));
    expect(h.onEditCommit).toHaveBeenCalledWith(expect.objectContaining({ id: 's1' }), 'New', 'a synopsis');
  });

  it('shows an empty state when there are no chapters', () => {
    const h = handlers();
    render(<Corkboard nodes={[]} editingId={null} draggable {...h} />);
    expect(screen.getByTestId('corkboard-empty')).toBeInTheDocument();
  });
});
