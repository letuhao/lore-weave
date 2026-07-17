// S-04 — the controller for EDITING a derivative's divergence deltas (spec +
// entity overrides) AFTER derive. Before S-04 these were frozen at derive-time and
// DivergenceManagerView showed them read-only ("archive and re-derive to change
// it"). This hook owns the mutations + the two reads the editor needs:
//   • entity_override ROWS (with id — the derivative-context projection omits it,
//     but PATCH/DELETE need it)
//   • the source project's canon entities, so an "override another entity" picker
//     keys the target on the GLOSSARY anchor (`glossary_entity_id`) — the SAME
//     id-space the wizard + packer use. Overriding an UNANCHORED entity would write
//     an id the present-lens never matches (a silent no-op), so the picker offers
//     only anchored entities (mirrors DivergenceWizardSteps Step3).
import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import { knowledgeApi } from '../../knowledge/api';
import type { DivergenceSpecPatch } from '../types';

export function useDivergenceSpecEditor(
  projectId: string | null,
  sourceProjectId: string | null,
  token: string | null,
) {
  const qc = useQueryClient();

  const overrides = useQuery({
    queryKey: ['composition', 'entity-overrides', projectId],
    queryFn: () => compositionApi.listEntityOverrides(projectId!, token!),
    enabled: !!projectId && !!token,
    select: (d) => d.overrides,
  });

  // Source canon entities — the override picker keys on glossary_entity_id (anchor).
  const entities = useQuery({
    queryKey: ['composition', 'derive-entities', sourceProjectId],
    queryFn: () =>
      knowledgeApi.listEntities({ project_id: sourceProjectId!, limit: 50, sort_by: 'mention_count' }, token!),
    enabled: !!sourceProjectId && !!token,
    select: (d) => d.entities,
  });

  // anchor id → entity, so an override row (which stores only the anchor id) renders
  // with a human name instead of a raw UUID.
  const entityByAnchor = useMemo(() => {
    const map = new Map<string, { name: string; kind: string }>();
    for (const e of entities.data ?? []) {
      if (e.glossary_entity_id) map.set(e.glossary_entity_id, { name: e.name, kind: e.kind });
    }
    return map;
  }, [entities.data]);

  // The refresh both sides need: the durable spec projection (drives the manager's
  // spec panel) AND the override rows (drive this editor's list).
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['composition', 'derivative-context', projectId] });
    qc.invalidateQueries({ queryKey: ['composition', 'entity-overrides', projectId] });
  };

  const patchSpec = useMutation({
    mutationFn: (body: DivergenceSpecPatch) => compositionApi.patchDivergenceSpec(projectId!, body, token!),
    onSuccess: refresh,
  });
  const addOverride = useMutation({
    mutationFn: (v: { target: string; fields: Record<string, unknown> }) =>
      compositionApi.addEntityOverride(projectId!, { target_entity_id: v.target, overridden_fields: v.fields }, token!),
    onSuccess: refresh,
  });
  const updateOverride = useMutation({
    mutationFn: (v: { id: string; fields: Record<string, unknown> }) =>
      compositionApi.updateEntityOverride(projectId!, v.id, { overridden_fields: v.fields }, token!),
    onSuccess: refresh,
  });
  const removeOverride = useMutation({
    mutationFn: (id: string) => compositionApi.deleteEntityOverride(projectId!, id, token!),
    onSuccess: refresh,
  });

  // Anchored source entities NOT already overridden — the "override another entity" options.
  const overriddenTargets = useMemo(
    () => new Set((overrides.data ?? []).map((o) => o.target_entity_id)),
    [overrides.data],
  );
  const addableEntities = useMemo(
    () =>
      (entities.data ?? []).filter(
        (e) => e.glossary_entity_id && !overriddenTargets.has(e.glossary_entity_id),
      ),
    [entities.data, overriddenTargets],
  );

  // Part A — the POV-anchor picker offers EVERY anchored source entity (a POV can be
  // any character, unlike an override which is one-per-target). Keyed on the glossary
  // anchor (`glossary_entity_id`) — the id-space divergence_spec.pov_anchor stores.
  const anchoredEntities = useMemo(
    () => (entities.data ?? []).filter((e) => e.glossary_entity_id),
    [entities.data],
  );

  return {
    overrides,
    entityByAnchor,
    addableEntities,
    anchoredEntities,
    patchSpec,
    addOverride,
    updateOverride,
    removeOverride,
  };
}
