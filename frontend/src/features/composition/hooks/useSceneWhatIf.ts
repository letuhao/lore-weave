// LOOM Composition (WS-B3 M1) — on-canvas scene what-if (ephemeral branch model).
//
// The controller for the dashed "what-if" branch drawn BESIDE canon on the Scene
// Graph. Per the spec (docs/specs/2026-06-26-scene-graph-whatif.md): the branch is
// EPHEMERAL — pure client state, NOTHING persisted until a future Promote step
// (M3). Discard drops it with zero residue (no Work, no outline nodes, no API call).
// M1 owns only the branch shape + entry/add/remove/discard + a pure layout helper;
// generation (M2) and promote (M3) build on this.
import { useCallback, useState } from 'react';
import type { Critic } from '../types';
import { NODE_H, NODE_W, type Pos } from '../components/sceneGraphLayout';

/** M2 — a generated alternate take (ghost prose + the job it came from + the critic
 *  judge dims). `ghost`/`jobId` set on generate; `judge` set after critique. */
export type WhatIfTake = { ghost: string; jobId: string; judge: Critic | null };

/** One ephemeral alternate scene in the branch. `id` is a CLIENT id (never an
 *  OutlineNode id) — these are not persisted until Promote. M2 adds the per-alt
 *  generation lifecycle (`status`) + the generated `take`. */
export type WhatIfAlt = {
  id: string;
  title: string;
  status: 'idle' | 'generating' | 'ready' | 'error';
  take?: WhatIfTake;
};

/** The ephemeral branch: anchored at a canon scene (its `story_order` becomes the
 *  derivative branch_point at Promote), holding ≥1 alternate takes drawn beside canon. */
export type WhatIfBranch = { anchorSceneId: string; alts: WhatIfAlt[] };

// Deterministic, process-unique client ids (no Date/Math.random — stable for tests).
let altSeq = 0;
function nextAltId(): string { return `wi-alt-${++altSeq}`; }

export type UseSceneWhatIf = {
  branch: WhatIfBranch | null;
  /** True while a what-if branch is open (suppresses link-create UI, shows branch tools). */
  active: boolean;
  /** Open a branch anchored at a canon scene, seeded with one alternate. */
  start: (anchorSceneId: string) => void;
  /** Append another alternate take to the open branch. */
  addAlt: () => void;
  /** Remove one alternate; discards the whole branch if it was the last. */
  removeAlt: (id: string) => void;
  /** M2 — patch one alternate's generation state (status / take / judge). No-op for
   *  an unknown id. */
  updateAlt: (id: string, patch: Partial<WhatIfAlt>) => void;
  /** Drop the branch entirely (zero residue). */
  discard: () => void;
};

export function useSceneWhatIf(): UseSceneWhatIf {
  const [branch, setBranch] = useState<WhatIfBranch | null>(null);

  const start = useCallback((anchorSceneId: string) => {
    setBranch({ anchorSceneId, alts: [{ id: nextAltId(), title: 'Alternate 1', status: 'idle' }] });
  }, []);

  const addAlt = useCallback(() => {
    setBranch((b) => (b ? { ...b, alts: [...b.alts, { id: nextAltId(), title: `Alternate ${b.alts.length + 1}`, status: 'idle' }] } : b));
  }, []);

  const removeAlt = useCallback((id: string) => {
    setBranch((b) => {
      if (!b) return b;
      const alts = b.alts.filter((a) => a.id !== id);
      return alts.length === 0 ? null : { ...b, alts };   // last alt removed → close the branch
    });
  }, []);

  const updateAlt = useCallback((id: string, patch: Partial<WhatIfAlt>) => {
    setBranch((b) => (b ? { ...b, alts: b.alts.map((a) => (a.id === id ? { ...a, ...patch } : a)) } : b));
  }, []);

  const discard = useCallback(() => setBranch(null), []);

  return { branch, active: branch !== null, start, addAlt, removeAlt, updateAlt, discard };
}

/** Pure layout: stack the branch's alternates in a lane to the RIGHT of the anchor so
 *  they read as a parallel branch beside canon (never overlapping the anchor). */
export function whatIfAltPositions(branch: WhatIfBranch, anchorPos: Pos): Record<string, Pos> {
  const out: Record<string, Pos> = {};
  const laneX = anchorPos.x + NODE_W + 80;
  branch.alts.forEach((a, i) => { out[a.id] = { x: laneX, y: anchorPos.y + i * (NODE_H + 24) }; });
  return out;
}

/** A dashed branch edge from the anchor scene to each alternate. `wi:true`
 *  discriminates it from a persisted SceneLink at render time. */
export type WhatIfEdge = { id: string; from_node_id: string; to_node_id: string; wi: true };

export function whatIfAltEdges(branch: WhatIfBranch): WhatIfEdge[] {
  return branch.alts.map((a) => ({
    id: `wie-${a.id}`, from_node_id: branch.anchorSceneId, to_node_id: a.id, wi: true,
  }));
}
