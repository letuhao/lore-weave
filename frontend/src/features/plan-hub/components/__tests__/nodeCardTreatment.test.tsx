// The MERGED coordinator — the graph's chapter/scene cards wear the SAME readable lane treatment as
// the redesign (status → fill/dot colour; authorship → serif human / mono machine). This is what makes
// "the graph card IS the lane card": one card, whether it sits on the zoom/pan canvas or in a lane row.
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider } from 'reactflow';
import { ChapterNode } from '../ChapterNode';
import { SceneNode } from '../SceneNode';
import type { NodeContent, NodePosition } from '../../types';
import type { PlanNodeData } from '../nodePresentation';

const pos = (shape: 'chapter' | 'scene'): NodePosition => ({
  id: 'n1', shape, laneId: 'arc1', x: 0, y: 0, width: 208, collapsed: false, storyOrder: 0,
});

const content = (o: Partial<NodeContent>): NodeContent => ({
  title: 'A chapter', status: 'outline', kind: 'chapter', tension: null, beatRole: null,
  chapterId: 'bc-1', castIds: [], castCount: 0, source: 'authored', ...o,
});

function renderNode(Comp: typeof ChapterNode | typeof SceneNode, data: Partial<PlanNodeData>) {
  render(
    <ReactFlowProvider>
      <Comp id="n1" type="chapter" data={data as never} selected={false} zIndex={1}
        isConnectable={false} xPos={0} yPos={0} dragging={false} />
    </ReactFlowProvider>,
  );
}

describe('merged card treatment (status colour + authorship font)', () => {
  it('a DONE authored chapter → success tint + serif title', () => {
    renderNode(ChapterNode, { node: pos('chapter'), content: content({ title: 'The rounding', status: 'done', source: 'authored' }), overlay: null, selected: false });
    const card = screen.getByTestId('plan-node-chapter-n1');
    expect(card.getAttribute('data-status')).toBe('done');
    expect(card.getAttribute('data-source')).toBe('authored');
    expect(card.className).toContain('hsl(var(--success))');
    expect(screen.getByText('The rounding').className).toContain('font-serif');
  });

  it('a planforge chapter reads as MACHINE → mono title (authored is the ONLY human value)', () => {
    renderNode(ChapterNode, { node: pos('chapter'), content: content({ title: 'AI draft', status: 'drafting', source: 'planforge' }), overlay: null, selected: false });
    const card = screen.getByTestId('plan-node-chapter-n1');
    expect(card.getAttribute('data-source')).toBe('mined'); // planforge → machine
    expect(card.className).toContain('bg-primary/10'); // drafting tint
    expect(screen.getByText('AI draft').className).toContain('font-mono');
  });

  it('an EMPTY chapter → dashed transparent card', () => {
    renderNode(ChapterNode, { node: pos('chapter'), content: content({ status: 'empty' }), overlay: null, selected: false });
    expect(screen.getByTestId('plan-node-chapter-n1').className).toContain('border-dashed');
  });

  it('a scene card carries the same coding', () => {
    renderNode(SceneNode, { node: pos('scene'), content: content({ title: 'Cold open', kind: 'scene', status: 'done', source: 'decompiled' }), overlay: null, selected: false });
    const card = screen.getByTestId('plan-node-scene-n1');
    expect(card.getAttribute('data-status')).toBe('done');
    expect(card.getAttribute('data-source')).toBe('mined'); // decompiled → machine
    expect(screen.getByText('Cold open').className).toContain('font-mono');
  });
});
