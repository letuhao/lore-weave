import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useSceneWhatIf, whatIfAltPositions, whatIfAltEdges, type WhatIfBranch,
} from '../useSceneWhatIf';
import { NODE_W } from '../../components/sceneGraphLayout';

describe('useSceneWhatIf (WS-B3 M1 — ephemeral branch)', () => {
  it('starts inactive with no branch', () => {
    const { result } = renderHook(() => useSceneWhatIf());
    expect(result.current.active).toBe(false);
    expect(result.current.branch).toBeNull();
  });

  it('start() opens a branch anchored at the scene, seeded with one alternate', () => {
    const { result } = renderHook(() => useSceneWhatIf());
    act(() => result.current.start('scene-7'));
    expect(result.current.active).toBe(true);
    expect(result.current.branch?.anchorSceneId).toBe('scene-7');
    expect(result.current.branch?.alts).toHaveLength(1);
  });

  it('addAlt() appends; removeAlt() drops; removing the last alt closes the branch', () => {
    const { result } = renderHook(() => useSceneWhatIf());
    act(() => result.current.start('scene-1'));
    act(() => result.current.addAlt());
    expect(result.current.branch?.alts).toHaveLength(2);
    const firstId = result.current.branch!.alts[0].id;
    act(() => result.current.removeAlt(firstId));
    expect(result.current.branch?.alts).toHaveLength(1);
    const lastId = result.current.branch!.alts[0].id;
    act(() => result.current.removeAlt(lastId));
    expect(result.current.branch).toBeNull();        // last alt gone → branch closes
    expect(result.current.active).toBe(false);
  });

  it('discard() drops the whole branch (zero residue)', () => {
    const { result } = renderHook(() => useSceneWhatIf());
    act(() => result.current.start('scene-1'));
    act(() => result.current.discard());
    expect(result.current.branch).toBeNull();
  });
});

describe('whatIf layout helpers (pure)', () => {
  const branch: WhatIfBranch = { anchorSceneId: 'a', alts: [{ id: 'wi-1', title: 'Alternate 1' }, { id: 'wi-2', title: 'Alternate 2' }] };

  it('positions alternates in a lane to the RIGHT of the anchor, stacked', () => {
    const pos = whatIfAltPositions(branch, { x: 100, y: 50 });
    expect(pos['wi-1'].x).toBe(100 + NODE_W + 80);
    expect(pos['wi-1'].x).toBe(pos['wi-2'].x);          // same lane
    expect(pos['wi-2'].y).toBeGreaterThan(pos['wi-1'].y); // stacked vertically
  });

  it('builds a dashed edge from the anchor to each alternate', () => {
    const edges = whatIfAltEdges(branch);
    expect(edges).toHaveLength(2);
    expect(edges[0]).toMatchObject({ from_node_id: 'a', to_node_id: 'wi-1', wi: true });
    expect(edges[1]).toMatchObject({ from_node_id: 'a', to_node_id: 'wi-2', wi: true });
  });
});
