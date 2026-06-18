// C24 (dị bản M0) — derivative-studio CONTEXT controller. Resolves whether the
// open Work is a DERIVATIVE (dị bản) and, if so, surfaces the data the studio banner
// + the 2-layer grounding badges need:
//   • source_work_id + branch_point (on the Work itself, C23)
//   • the OVERRIDDEN entity set (G2 delta) — the `entity_override[]` the wizard
//     persisted at derive time. M0 has NO BE read endpoint for overrides (C23
//     persists only; reading them is C25's packer concern), and the brief scopes
//     OUT any new BE API. So the studio reads the REAL override set the wizard
//     submitted, stashed in the query cache at derive time (`derivativeOverridesKey`).
//     This is the actual persisted delta (the BE stored exactly these ids) — the
//     badge reflects real state, never a guess.
//
// An entity is INHERITED (base / source project ≤ branch) UNLESS its id is in the
// override set, in which case it is OVERRIDDEN (delta). The classifier is a pure fn
// so the badge decorator + tests share one source of truth.
import { useQuery } from '@tanstack/react-query';
import type { Work } from '../types';

export type GroundingLayer = 'inherited' | 'overridden';

/** What the wizard stashes for a freshly-spawned derivative so the studio can
 *  render REAL state without a (scoped-out) BE read endpoint: the SOURCE project
 *  (whose canon entities are classified) + the submitted OVERRIDDEN entity-id set. */
export type DerivativeMeta = {
  sourceProjectId: string;
  overrideIds: string[];
};

/** The query key under which the wizard stashes the derivative metadata. Exported
 *  so the wizard writes the SAME key. */
export function derivativeOverridesKey(derivativeProjectId: string): readonly unknown[] {
  return ['composition', 'derivative-meta', derivativeProjectId];
}

/** Pure classifier — the single source of truth for the badge layer. An entity is
 *  OVERRIDDEN iff it is in the derivative's override set; otherwise INHERITED. */
export function classifyGroundingLayer(
  entityId: string,
  overrideIds: ReadonlySet<string>,
): GroundingLayer {
  return overrideIds.has(entityId) ? 'overridden' : 'inherited';
}

export type DerivativeContext = {
  isDerivative: boolean;
  sourceWorkId: string | null;
  branchPoint: number | null;
  /** The SOURCE project whose canon entities the studio classifies (known this
   *  session via the wizard's stash). null when not known. */
  sourceProjectId: string | null;
  /** The set of OVERRIDDEN (delta) entity ids — empty for a non-derivative or when
   *  the override set isn't known this session. */
  overrideIds: ReadonlySet<string>;
  classify: (entityId: string) => GroundingLayer;
};

export function useDerivativeContext(work: Work | null | undefined): DerivativeContext {
  const isDerivative = !!work?.source_work_id;
  const derivativeProjectId = isDerivative ? work?.project_id : undefined;

  // Read the metadata the wizard stashed for THIS derivative project (real submitted
  // delta + source project). `enabled:false` — we never fetch; the cache is the source.
  const metaQ = useQuery<DerivativeMeta | undefined>({
    queryKey: derivativeProjectId
      ? derivativeOverridesKey(derivativeProjectId)
      : ['composition', 'derivative-meta', '__none__'],
    queryFn: () => undefined,
    enabled: false,
  });

  const meta = isDerivative ? metaQ.data : undefined;
  const overrideIds = new Set<string>(meta?.overrideIds ?? []);

  return {
    isDerivative,
    sourceWorkId: work?.source_work_id ?? null,
    branchPoint: work?.branch_point ?? null,
    sourceProjectId: meta?.sourceProjectId ?? null,
    overrideIds,
    classify: (entityId: string) => classifyGroundingLayer(entityId, overrideIds),
  };
}
