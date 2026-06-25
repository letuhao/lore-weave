// C24 (dị bản) — derivative-studio CONTEXT controller. Resolves whether the open
// Work is a DERIVATIVE (dị bản) and, if so, surfaces the data the studio banner +
// the 2-layer grounding badges + the divergence-spec popover need:
//   • source_work_id + branch_point (on the Work itself, C23)
//   • source_project_id (resolved server-side — the source's project, not its id)
//   • the OVERRIDDEN entity set + per-entity field delta (G2)
//   • taxonomy / pov_anchor / canon_rule[] (the divergence spec)
//
// WS-B2 (durable): these now come from the DURABLE read-back endpoint
// (GET /works/{project_id}/derivative-context), which reads the persisted
// divergence_spec + entity_override[] — the SAME substrate the packer applies.
// This SUPERSEDES the prior derive-time react-query cache (lost on reload): the
// banner chips, spec popover, and was→now deltas now survive a page reload / new
// session. An entity is OVERRIDDEN iff its id is in the override set, else INHERITED.
import { useQuery } from '@tanstack/react-query';
import { compositionApi } from '../api';
import type { DivergenceTaxonomy, Work } from '../types';

export type GroundingLayer = 'inherited' | 'overridden';

/** The query key for a derivative Work's durable context. Exported so the derive /
 *  promote mutations can invalidate it (force a fresh read of the new spec). */
export function derivativeContextKey(derivativeProjectId: string): readonly unknown[] {
  return ['composition', 'derivative-context', derivativeProjectId];
}

/** Pure classifier — the single source of truth for the badge layer. An entity is
 *  OVERRIDDEN iff it is in the derivative's override set; otherwise INHERITED.
 *  NOTE (WS-B2 id-space): the override set is keyed by the GLOSSARY anchor
 *  (`glossary_entity_id`), not the knowledge node id — callers must classify with
 *  the anchor id, never the node id, or every row reads INHERITED. */
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
  /** The SOURCE project whose canon entities the studio classifies. null when not
   *  a derivative (or the source could not be resolved). */
  sourceProjectId: string | null;
  /** The set of OVERRIDDEN (delta) entity ids — keyed by glossary anchor. */
  overrideIds: ReadonlySet<string>;
  /** WS-B2 — per-entity field delta (target_entity_id → {field: newValue}), for
   *  the was→now grounding rows + the spec popover. */
  overrides: Record<string, Record<string, unknown>>;
  /** WS-B2 — the divergence spec fields, for the banner chips + popover. */
  taxonomy: DivergenceTaxonomy | null;
  povAnchor: string | null;
  canonRules: string[];
  classify: (entityId: string) => GroundingLayer;
  /** True while the durable context is being fetched (derivative only). */
  isLoading: boolean;
};

const EMPTY_OVERRIDE_SET: ReadonlySet<string> = new Set<string>();

export function useDerivativeContext(
  work: Work | null | undefined,
  token: string | null,
): DerivativeContext {
  const isDerivative = !!work?.source_work_id;
  const derivativeProjectId = isDerivative ? work?.project_id : undefined;

  // WS-B2 — read the DURABLE spec for THIS derivative project. Disabled for a
  // greenfield Work (no source) so we never fetch on the common path.
  const ctxQ = useQuery({
    queryKey: derivativeProjectId
      ? derivativeContextKey(derivativeProjectId)
      : ['composition', 'derivative-context', '__none__'],
    queryFn: () => compositionApi.getDerivativeContext(derivativeProjectId!, token!),
    enabled: !!derivativeProjectId && !!token,
  });

  const data = isDerivative ? ctxQ.data : undefined;
  const overrides: Record<string, Record<string, unknown>> = {};
  for (const ov of data?.overrides ?? []) {
    overrides[ov.target_entity_id] = ov.overridden_fields;
  }
  const overrideIds = data ? new Set<string>(Object.keys(overrides)) : EMPTY_OVERRIDE_SET;

  return {
    isDerivative,
    sourceWorkId: work?.source_work_id ?? null,
    branchPoint: work?.branch_point ?? data?.branch_point ?? null,
    sourceProjectId: data?.source_project_id ?? null,
    overrideIds,
    overrides,
    taxonomy: data?.taxonomy ?? null,
    povAnchor: data?.pov_anchor ?? null,
    canonRules: data?.canon_rules ?? [],
    classify: (entityId: string) => classifyGroundingLayer(entityId, overrideIds),
    isLoading: isDerivative && ctxQ.isLoading,
  };
}
