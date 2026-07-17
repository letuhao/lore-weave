// S-01 · structure-templates panel controller (hook). Story structures are PER-USER (no book/
// project scope), so this needs only the token — simpler than the arc/motif panels. Owns the
// list + selection + the clone mutation (slice B's entry point from empty). Slice C adds beat
// editing; slice D adds use-in-decompose + archive/restore.
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { Beat, StructureTemplate } from '@/features/composition/types';

export interface StructureTemplatesState {
  builtins: StructureTemplate[];
  mine: StructureTemplate[];
  isLoading: boolean;
  error: string | null;
  selectedId: string | null;
  select: (id: string) => void;
  selected: StructureTemplate | null;
  cloning: boolean;
  clone: (templateId: string) => void;      // slice B — copy a built-in/any into my tier
  // slice C — save edits to an OWN template (name + beats), OCC-guarded.
  saving: boolean;
  saveError: string | null;
  save: (id: string, version: number, patch: { name?: string; beats?: Beat[] }) => void;
}

export function useStructureTemplates(includeArchived = false): StructureTemplatesState {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ['structure-templates', includeArchived],
    queryFn: () => compositionApi.listTemplates(accessToken!, includeArchived),
    enabled: !!accessToken,
  });

  const templates = q.data ?? [];
  const builtins = useMemo(() => templates.filter((t) => t.owner_user_id == null), [templates]);
  const mine = useMemo(() => templates.filter((t) => t.owner_user_id != null), [templates]);

  const cloneMut = useMutation({
    mutationFn: (templateId: string) => compositionApi.cloneTemplate(templateId, accessToken!),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ['structure-templates'] });
      setSelectedId(created.id);   // land on the fresh copy so the user SEES the result
    },
  });

  const saveMut = useMutation({
    mutationFn: (v: { id: string; version: number; patch: { name?: string; beats?: Beat[] } }) =>
      compositionApi.updateTemplate(v.id, v.version, v.patch, accessToken!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['structure-templates'] }),
  });

  const selected = templates.find((t) => t.id === selectedId) ?? null;

  return {
    builtins, mine,
    isLoading: q.isLoading,
    error: q.error ? (q.error as Error).message : null,
    selectedId, select: setSelectedId, selected,
    cloning: cloneMut.isPending,
    clone: (id) => cloneMut.mutate(id),
    saving: saveMut.isPending,
    saveError: saveMut.error ? (saveMut.error as Error).message : null,
    save: (id, version, patch) => saveMut.mutate({ id, version, patch }),
  };
}
