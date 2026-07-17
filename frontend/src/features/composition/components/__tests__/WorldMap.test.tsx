import { render, screen, fireEvent, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorldMap } from '../WorldMap';
import { buildPlaceGraph, gridLayout } from '../../hooks/useWorldMap';
import type { Entity, EntityDetail, EntityRelation } from '../../../knowledge/api';

const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock('../../hooks/useWorldMap', async (orig) => ({
  ...(await orig<typeof import('../../hooks/useWorldMap')>()),
  useWorldMap: () => hook(),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

function place(id: string, name: string): Entity {
  return {
    id, user_id: 'u', project_id: 'kp1', name, canonical_name: name.toLowerCase(), kind: 'location',
    aliases: [], canonical_version: 1, source_types: ['manual'], confidence: 1, glossary_entity_id: null,
    anchor_score: 0, archived_at: null, archive_reason: null, evidence_count: 0, mention_count: 0,
    user_edited: false, version: 1, created_at: null, updated_at: null,
  };
}
function rel(id: string, s: string, o: string, sk = 'location', ok = 'location'): EntityRelation {
  return {
    id, subject_id: s, object_id: o, predicate: 'borders', confidence: 1, source_event_ids: [],
    source_chapter: null, valid_from: null, valid_until: null, pending_validation: false,
    created_at: null, updated_at: null, subject_name: s, subject_kind: sk, object_name: o, object_kind: ok,
  };
}
function detail(p: Entity, relations: EntityRelation[]): EntityDetail {
  return { entity: p, relations, relations_truncated: false, total_relations: relations.length };
}

describe('useWorldMap pure helpers (T2.5)', () => {
  it('buildPlaceGraph keeps ONLY location↔location edges, deduped', () => {
    const p1 = place('p1', 'Hollow Keep');
    const p2 = place('p2', 'The Ashlands');
    const details = {
      p1: detail(p1, [rel('r1', 'p1', 'p2'), rel('r2', 'p1', 'c9', 'location', 'character')]),
      p2: detail(p2, [rel('r1', 'p1', 'p2')]), // same edge from p2's side → deduped
    };
    const { nodes, edges } = buildPlaceGraph([p1, p2], details);
    expect(nodes.map((n) => n.id).sort()).toEqual(['p1', 'p2']);
    expect(edges.map((e) => e.id)).toEqual(['r1']); // r2 (→ character) dropped; r1 once
  });

  it('gridLayout lays ids out in rows of `cols` with non-negative coords', () => {
    const g = gridLayout(['a', 'b', 'c', 'd', 'e'], { cols: 2, gapX: 100, gapY: 100, pad: 10 });
    expect(g.a).toEqual({ x: 10, y: 10 });
    expect(g.b).toEqual({ x: 110, y: 10 });
    expect(g.c).toEqual({ x: 10, y: 110 }); // wraps to row 2
    expect(g.e).toEqual({ x: 10, y: 210 });
  });
});

describe('WorldMap (T2.5)', () => {
  const onViewCast = vi.fn();
  const createPlace = { mutate: vi.fn(), isPending: false };
  const linkPlaces = { mutate: vi.fn(), isPending: false };
  const deletePlace = { mutate: vi.fn(), isPending: false };
  const uploadBackdrop = { mutate: vi.fn(), isPending: false };
  const persistPositions = vi.fn();
  const applyLocal = vi.fn();

  const base = {
    knowledgeProjectId: 'kp1', projectLoading: false, placesLoading: false,
    nodes: [{ id: 'p1', name: 'Hollow Keep', kind: 'location' }, { id: 'p2', name: 'The Ashlands', kind: 'location' }],
    edges: [{ id: 'e1', from: 'p1', to: 'p2', predicate: 'borders', pending: false, confidence: 1 }],
    positions: { p1: { x: 40, y: 40 }, p2: { x: 260, y: 40 } },
    backdropUrl: null as string | null,
    applyLocal, localRef: { current: {} }, persistPositions,
    createPlace, linkPlaces, deletePlace, uploadBackdrop,
  };

  beforeEach(() => {
    onViewCast.mockReset(); createPlace.mutate.mockReset(); linkPlaces.mutate.mockReset();
    deletePlace.mutate.mockReset(); uploadBackdrop.mutate.mockReset(); hook.mockReturnValue(base);
  });

  const render0 = () => render(<WorldMap work={{} as never} bookId="b" chapterId="ch" token="t" onViewCast={onViewCast} />);
  const placeBody = (id: string) =>
    within(document.querySelector(`[data-place="${id}"]`) as HTMLElement).getByTestId('worldmap-node-body');

  it('renders places and their location↔location edges', () => {
    render0();
    expect(screen.getAllByTestId('worldmap-node')).toHaveLength(2);
    expect(screen.getAllByTestId('relmap-edge')).toHaveLength(1);
  });

  it('clicking a place (not link mode) opens it in the codex', () => {
    render0();
    fireEvent.pointerDown(placeBody('p1'), { clientX: 5, clientY: 5 });
    fireEvent.pointerUp(screen.getByTestId('worldmap-svg'));
    expect(onViewCast).toHaveBeenCalledWith('Hollow Keep');
  });

  it('add-place creates a location entity', () => {
    render0();
    fireEvent.change(screen.getByTestId('worldmap-add-input'), { target: { value: 'Emberfall' } });
    fireEvent.click(screen.getByTestId('worldmap-add'));
    expect(createPlace.mutate).toHaveBeenCalledWith('Emberfall', expect.anything());
  });

  it('link mode: pick two places + predicate → creates a relation, not a codex open', () => {
    render0();
    fireEvent.click(screen.getByTestId('worldmap-link-toggle'));
    fireEvent.pointerDown(placeBody('p1'), { clientX: 5, clientY: 5 });
    fireEvent.pointerUp(screen.getByTestId('worldmap-svg'));
    fireEvent.pointerDown(placeBody('p2'), { clientX: 5, clientY: 5 });
    fireEvent.pointerUp(screen.getByTestId('worldmap-svg'));
    fireEvent.click(screen.getByTestId('worldmap-link-confirm'));
    expect(linkPlaces.mutate).toHaveBeenCalledWith(
      { subjectId: 'p1', objectId: 'p2', predicate: 'borders' }, expect.anything(),
    );
    expect(onViewCast).not.toHaveBeenCalled(); // link-mode click ≠ codex open
  });

  const deleteBtn = (id: string) =>
    within(document.querySelector(`[data-place="${id}"]`) as HTMLElement).getByTestId('worldmap-node-delete');

  it('deleting a place: confirms, then fires the archive mutation with the node id', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render0();
    fireEvent.click(deleteBtn('p1'));
    expect(confirmSpy).toHaveBeenCalled();
    expect(deletePlace.mutate).toHaveBeenCalledWith('p1', expect.anything());
    confirmSpy.mockRestore();
  });

  it('deleting a place: declining the confirm does NOT fire the mutation (destructive guard)', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render0();
    fireEvent.click(deleteBtn('p2'));
    expect(confirmSpy).toHaveBeenCalled();
    expect(deletePlace.mutate).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('the delete button does NOT open the codex (isolated from the node body click)', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render0();
    fireEvent.click(deleteBtn('p1'));
    expect(onViewCast).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('renders the backdrop image when one is set', () => {
    hook.mockReturnValue({ ...base, backdropUrl: 'https://cdn/x/map.png' });
    render0();
    expect(screen.getByTestId('worldmap-backdrop-img')).toBeInTheDocument();
  });

  it('shows an empty hint when there are no places (toolbar still available)', () => {
    hook.mockReturnValue({ ...base, nodes: [], edges: [] });
    render0();
    expect(screen.getByTestId('worldmap-empty')).toBeInTheDocument();
    expect(screen.getByTestId('worldmap-add')).toBeInTheDocument();
  });

  it('shows the extract-first state with no knowledge project', () => {
    hook.mockReturnValue({ ...base, knowledgeProjectId: null, nodes: [], edges: [] });
    render0();
    expect(screen.getByText('wmap.noProject')).toBeInTheDocument();
    expect(screen.queryByTestId('worldmap-add')).not.toBeInTheDocument();
  });

  // S7-3 §4.3 — the backdrop upload is chapter-scoped; in the standalone place-graph dock panel
  // chapterId can be empty, and an upload against '' 404s. The leaf degrades: disable + hint.
  it('backdrop control is ENABLED when a chapter is open (legacy behavior — unchanged)', () => {
    render0(); // render0 passes chapterId="ch"
    expect(screen.getByTestId('worldmap-backdrop')).not.toBeDisabled();
  });

  it('backdrop control is DISABLED with a hint when there is no active chapter (§4.3 guard)', () => {
    render(<WorldMap work={{} as never} bookId="b" chapterId="" token="t" onViewCast={onViewCast} />);
    const btn = screen.getByTestId('worldmap-backdrop');
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('title', 'wmap.backdropNoChapter');
  });
});
