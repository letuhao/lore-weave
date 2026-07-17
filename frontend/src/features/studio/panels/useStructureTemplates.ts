// S-01 · structure-templates panel controller (hook). Story structures are PER-USER (no book/
// project scope), so this needs only the token — simpler than the arc/motif panels. Owns the
// list + selection + the clone mutation (slice B's entry point from empty). Slice C adds beat
// editing; slice D adds use-in-decompose + archive/restore.
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { Beat, StructureTemplate } from '@/features/composition/types';

// C3 — a stable classification of a write failure, so the panel shows a human sentence instead of
// the raw `(error as Error).message` (an OCC conflict used to surface as "…status 412"). The hook
// maps the code → a localized string via i18n. Mirrors usePlanner's `asPlannerError` status read.
export type StructTplErrorCode = 'conflict' | 'duplicate' | 'blank' | 'unknown';
export function classifyStructTplError(e: unknown): StructTplErrorCode {
  const status = (e as { status?: number } | null)?.status;
  if (status === 412 || status === 428) return 'conflict'; // OCC / missing If-Match — someone edited it
  if (status === 409) return 'duplicate';                  // UNIQUE(owner,name)
  if (status === 422) return 'blank';                      // name failed the non-empty validator
  return 'unknown';
}

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
  // S-01b slice 2 — author a brand-new own template from scratch (draft-first: no server row until Save).
  isCreating: boolean;
  startCreate: () => void;
  cancelCreate: () => void;
  creating: boolean;
  create: (patch: { name: string; kind?: string; beats?: Beat[] }) => void;
  // slice C — save edits to an OWN template (name + kind + beats), OCC-guarded.
  saving: boolean;
  saveError: string | null;
  save: (id: string, version: number, patch: { name?: string; kind?: string; beats?: Beat[] }) => void;
  // slice D — archive/restore an OWN template + show-archived toggle.
  showArchived: boolean;
  setShowArchived: (v: boolean) => void;
  archive: (id: string) => void;
  restore: (id: string) => void;
}

export function useStructureTemplates(): StructureTemplatesState {
  const { accessToken } = useAuth();
  const { t } = useTranslation('studio');
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  // C3 — map a classified write error to a human, localized sentence.
  const mapErr = (e: unknown): string => {
    const code = classifyStructTplError(e);
    const fallback: Record<StructTplErrorCode, string> = {
      conflict: 'This structure changed elsewhere — reload and reapply your edits.',
      duplicate: 'You already have a structure with that name.',
      blank: "A structure needs a name.",
      unknown: (e as Error)?.message || 'Something went wrong — please try again.',
    };
    return t(`structTpl.err.${code}`, { defaultValue: fallback[code] });
  };

  const q = useQuery({
    queryKey: ['structure-templates', showArchived],
    queryFn: () => compositionApi.listTemplates(accessToken!, showArchived),
    enabled: !!accessToken,
  });

  const templates = q.data ?? [];
  const builtins = useMemo(() => templates.filter((t) => t.owner_user_id == null), [templates]);
  const mine = useMemo(() => templates.filter((t) => t.owner_user_id != null), [templates]);

  const cloneMut = useMutation({
    mutationFn: (templateId: string) => compositionApi.cloneTemplate(templateId, accessToken!),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ['structure-templates'] });
      setIsCreating(false);
      setSelectedId(created.id);   // land on the fresh copy so the user SEES the result
    },
  });

  // S-01b slice 2 — create a brand-new own template. Draft-first: the editor holds a local draft and
  // only calls this on Save, so an abandoned "+ New" never leaves an untitled server row.
  const createMut = useMutation({
    mutationFn: (patch: { name: string; kind?: string; beats?: Beat[] }) =>
      compositionApi.createTemplate(patch, accessToken!),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ['structure-templates'] });
      setIsCreating(false);
      setSelectedId(created.id);   // land on the freshly-authored structure
      toast.success(t('structTpl.toast.created', { defaultValue: 'Structure created' }));
    },
  });

  const saveMut = useMutation({
    mutationFn: (v: { id: string; version: number; patch: { name?: string; beats?: Beat[] } }) =>
      compositionApi.updateTemplate(v.id, v.version, v.patch, accessToken!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['structure-templates'] });
      toast.success(t('structTpl.toast.saved', { defaultValue: 'Structure saved' }));
    },
  });
  const archiveMut = useMutation({
    mutationFn: (id: string) => compositionApi.archiveTemplate(id, accessToken!),
    onSuccess: (_r, id) => {
      qc.invalidateQueries({ queryKey: ['structure-templates'] });
      if (selectedId === id) setSelectedId(null);   // it left the default list
      toast.success(t('structTpl.toast.archived', { defaultValue: 'Structure archived' }));
    },
  });
  const restoreMut = useMutation({
    mutationFn: (id: string) => compositionApi.restoreTemplate(id, accessToken!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['structure-templates'] });
      toast.success(t('structTpl.toast.restored', { defaultValue: 'Structure restored' }));
    },
  });

  const selected = templates.find((t) => t.id === selectedId) ?? null;

  return {
    builtins, mine,
    isLoading: q.isLoading,
    error: q.error ? (q.error as Error).message : null,
    selectedId,
    // Selecting an existing row exits create-mode (the two are mutually exclusive views).
    select: (id: string) => { setIsCreating(false); setSelectedId(id); },
    selected,
    cloning: cloneMut.isPending,
    clone: (id) => cloneMut.mutate(id),
    isCreating,
    startCreate: () => { setIsCreating(true); setSelectedId(null); },
    cancelCreate: () => setIsCreating(false),
    creating: createMut.isPending,
    create: (patch) => createMut.mutate(patch),
    saving: saveMut.isPending,
    // In create-mode the editor surfaces the create mutation's error; otherwise the save error.
    saveError: isCreating
      ? (createMut.error ? mapErr(createMut.error) : null)
      : (saveMut.error ? mapErr(saveMut.error) : null),
    save: (id, version, patch) => saveMut.mutate({ id, version, patch }),
    showArchived, setShowArchived,
    archive: (id) => archiveMut.mutate(id),
    restore: (id) => restoreMut.mutate(id),
  };
}
