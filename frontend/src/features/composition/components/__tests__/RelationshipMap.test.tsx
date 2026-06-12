import { render, screen, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RelationshipMap } from '../RelationshipMap';
import { buildGraph, radialLayout } from '../../hooks/useRelationshipMap';
import type { EntityDetail, EntityRelation } from '../../../knowledge/api';

// Partial-mock: keep the REAL pure buildGraph/radialLayout, override only the hook.
const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock('../../hooks/useRelationshipMap', async (orig) => ({
  ...(await orig<typeof import('../../hooks/useRelationshipMap')>()),
  useRelationshipMap: () => hook(),
}));

function rel(over: Partial<EntityRelation>): EntityRelation {
  return {
    id: 'r', subject_id: 's', object_id: 'o', predicate: 'knows', confidence: 0.9,
    source_event_ids: [], source_chapter: null, valid_from: null, valid_until: null,
    pending_validation: false, created_at: null, updated_at: null,
    subject_name: 'S', subject_kind: 'character', object_name: 'O', object_kind: 'character', ...over,
  };
}
function detail(id: string, name: string, kind: string, relations: EntityRelation[]): EntityDetail {
  return { entity: { id, name, kind } as EntityDetail['entity'], relations, relations_truncated: false, total_relations: relations.length };
}

describe('buildGraph (T2.2)', () => {
  it('assembles nodes (focus + neighbour stubs) and edges, deduped across accreted details', () => {
    const r1 = rel({ id: 'r1', subject_id: 'kael', object_id: 'mira', predicate: 'ally', subject_name: 'Kael', object_name: 'Mira' });
    const details = {
      kael: detail('kael', 'Kael', 'character', [r1]),
      mira: detail('mira', 'Mira', 'character', [r1]), // same edge from mira's side → deduped
    };
    const { nodes, edges, truncated } = buildGraph(details);
    expect(nodes.map((n) => n.id).sort()).toEqual(['kael', 'mira']);
    expect(edges.map((e) => e.id)).toEqual(['r1']); // one edge, not two
    expect(truncated).toBe(false);
  });

  it('derives neighbour stubs (name/kind from the relation) for un-fetched nodes + flags pending', () => {
    const r = rel({ id: 'r2', subject_id: 'kael', object_id: 'pact', predicate: 'member-of', pending_validation: true, object_name: 'Ashen Pact', object_kind: 'faction' });
    const { nodes, edges } = buildGraph({ kael: detail('kael', 'Kael', 'character', [r]) });
    expect(nodes.find((n) => n.id === 'pact')).toEqual({ id: 'pact', name: 'Ashen Pact', kind: 'faction' });
    expect(edges[0].pending).toBe(true);
  });

  it('caps the node set and flags truncation', () => {
    const rels = Array.from({ length: 70 }, (_, i) => rel({ id: `r${i}`, subject_id: 'hub', object_id: `n${i}` }));
    const { nodes, truncated } = buildGraph({ hub: detail('hub', 'Hub', 'character', rels) });
    expect(truncated).toBe(true);
    expect(nodes.length).toBe(60);
    expect(nodes[0].id).toBe('hub'); // focus kept first
  });
});

describe('radialLayout (T2.2)', () => {
  it('places focus at center, is deterministic, and normalises to non-negative coords', () => {
    const a = radialLayout(['kael', 'mira', 'pact'], 'kael');
    const b = radialLayout(['pact', 'kael', 'mira'], 'kael');
    expect(a).toEqual(b); // deterministic regardless of input order
    const xs = Object.values(a).map((p) => p.x);
    const ys = Object.values(a).map((p) => p.y);
    expect(Math.min(...xs)).toBe(24); // normalised to pad
    expect(Math.min(...ys)).toBe(24);
  });
});

describe('RelationshipMap (T2.2)', () => {
  const setFocus = vi.fn();
  const toggleExpand = vi.fn();
  const r1 = rel({ id: 'r1', subject_id: 'kael', object_id: 'mira', predicate: 'ally', subject_name: 'Kael', object_name: 'Mira' });
  const r2 = rel({ id: 'r2', subject_id: 'kael', object_id: 'pact', predicate: 'member-of', pending_validation: true, object_name: 'Ashen Pact', object_kind: 'faction' });

  const base = {
    projectId: 'kp1', projectLoading: false,
    entities: [{ id: 'kael', name: 'Kael' }, { id: 'mira', name: 'Mira' }],
    entitiesLoading: false,
    focusId: 'kael', setFocus, expanded: [] as string[], toggleExpand,
    details: { kael: detail('kael', 'Kael', 'character', [r1, r2]) },
    detailsLoading: false,
  };

  beforeEach(() => { setFocus.mockReset(); toggleExpand.mockReset(); hook.mockReturnValue(base); });

  const bodyOf = (id: string) =>
    within(document.querySelector(`[data-entity="${id}"]`) as HTMLElement).getByTestId('relmap-node-body');

  it('renders the focus + neighbours as nodes and the relations as edges (pending distinct)', () => {
    render(<RelationshipMap bookId="b" token="t" />);
    expect(screen.getAllByTestId('relmap-node')).toHaveLength(3); // kael + mira + pact
    const edges = screen.getAllByTestId('relmap-edge');
    expect(edges).toHaveLength(2);
    expect(edges.find((e) => e.getAttribute('data-predicate') === 'member-of')!.getAttribute('data-pending')).toBe('true');
    // focus node carries data-focus.
    expect(document.querySelector('[data-entity="kael"]')!.getAttribute('data-focus')).toBe('true');
  });

  it('clicking a neighbour re-focuses', () => {
    render(<RelationshipMap bookId="b" token="t" />);
    fireEvent.pointerDown(bodyOf('mira'), { clientX: 5, clientY: 5 });
    fireEvent.pointerUp(screen.getByTestId('relmap-svg'));
    expect(setFocus).toHaveBeenCalledWith('mira');
  });

  it('the ⊞ button accretes a node without re-focusing', () => {
    render(<RelationshipMap bookId="b" token="t" />);
    fireEvent.click(within(document.querySelector('[data-entity="mira"]') as HTMLElement).getByTestId('relmap-expand'));
    expect(toggleExpand).toHaveBeenCalledWith('mira');
    expect(setFocus).not.toHaveBeenCalled();
  });

  it('the focus picker re-focuses', () => {
    render(<RelationshipMap bookId="b" token="t" />);
    fireEvent.change(screen.getByTestId('relmap-focus-select'), { target: { value: 'mira' } });
    expect(setFocus).toHaveBeenCalledWith('mira');
  });

  it('surfaces the current focus as a picker option even when it is not in the entity list', () => {
    // /review-impl MED-1: refocus onto a neighbour not in the (capped) entity list
    // — the picker must still show it, not blank out.
    hook.mockReturnValue({ ...base, focusId: 'mira', entities: [{ id: 'kael', name: 'Kael' }] });
    render(<RelationshipMap bookId="b" token="t" />);
    const select = screen.getByTestId('relmap-focus-select') as HTMLSelectElement;
    expect(select.value).toBe('mira');
    expect(select.querySelector('option[value="mira"]')?.textContent).toBe('Mira');
  });

  it('shows a no-relations hint when the focus has no edges', () => {
    hook.mockReturnValue({ ...base, details: { kael: detail('kael', 'Kael', 'character', []) } });
    render(<RelationshipMap bookId="b" token="t" />);
    expect(screen.getByTestId('relmap-empty')).toBeInTheDocument();
  });

  it('shows the extract-first state when there is no knowledge project', () => {
    hook.mockReturnValue({ ...base, projectId: null, entities: [] });
    render(<RelationshipMap bookId="b" token="t" />);
    expect(screen.getByText('relations.noProject')).toBeInTheDocument();
  });
});
