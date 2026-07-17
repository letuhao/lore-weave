// EC-3 — the divergence (dị bản) MANAGE controller. The panel is a manage surface,
// NOT a wizard launcher: the LIST already exists (candidates[] off the resolution
// route) and nothing surfaced it. Verbs:
//   LIST    — canonical (selectCanonicalWork) + derivatives (selectDerivatives)
//   READ    — the selected derivative's durable spec (getDerivativeContext)
//   CREATE  — DivergenceWizard (branches from canonical), wired in the view
//   SWITCH  — useSetActiveWork (the EC-3d per-book pref; moves the whole studio)
//   ARCHIVE — patchWork {status:'archived'} + If-Match (412 → reload, never clobber)
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import { useWorkResolution } from './useWork';
import { useActiveWorkId, useSetActiveWork } from './useActiveWork';
import { selectCanonicalWork, selectDerivatives } from '../workSelect';
import type { Work } from '../types';

export function derivativeName(w: Work): string | null {
  const n = (w.settings as { derivative_name?: unknown } | undefined)?.derivative_name;
  return typeof n === 'string' && n.trim() ? n : null;
}

export function useDivergenceManager(bookId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  const resolution = useWorkResolution(bookId, token);
  const { data: activeWorkId } = useActiveWorkId(bookId, token);
  const { switchTo, isSwitching } = useSetActiveWork(bookId, token);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const { candidates, canonical, derivatives } = useMemo(() => {
    const d = resolution.data;
    const c: Work[] =
      d?.status === 'candidates' ? d.candidates
        : d?.status === 'found' && d.work ? [d.work]
          : [];
    return { candidates: c, canonical: selectCanonicalWork(c), derivatives: selectDerivatives(c) };
  }, [resolution.data]);

  // The active Work = the pref if it still resolves, else canonical (EC-3d fallback).
  const activeProjectId =
    (activeWorkId && candidates.some((w) => w.project_id === activeWorkId) ? activeWorkId : null)
    ?? canonical?.project_id
    ?? null;

  const selected = derivatives.find((d) => d.project_id === selectedProjectId) ?? null;
  const spec = useQuery({
    queryKey: ['composition', 'derivative-context', selectedProjectId],
    queryFn: () => compositionApi.getDerivativeContext(selectedProjectId!, token!),
    enabled: !!selectedProjectId && !!token,
  });

  const archive = useMutation({
    mutationFn: (w: Work) =>
      compositionApi.patchWork(w.project_id, { status: 'archived' }, token!, { version: w.version }),
    // Both success and a 412 conflict resolve by reloading the list from the server —
    // an archived Work drops out of resolve_by_book; a 412 carried the current row, so
    // the freshest truth is a refetch, never a guess.
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] });
    },
  });

  // Audit fix — archive was a ONE-WAY door (the branch dropped out of the list with no
  // way back). Restore flips status→active (the reverse op the backend already supports);
  // wired as an Undo action on the archive toast. Takes the post-archive Work (its bumped
  // version) so the If-Match matches.
  const restore = useMutation({
    mutationFn: (w: Work) =>
      compositionApi.patchWork(w.project_id, { status: 'active' }, token!, { version: w.version }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] });
    },
  });

  const isArchiveConflict = (archive.error as { status?: number } | null)?.status === 412;

  return {
    resolution,
    canonical,
    derivatives,
    activeProjectId,
    selected,
    selectedProjectId,
    setSelectedProjectId,
    spec,
    archive,
    restore,
    isArchiveConflict,
    switchTo,
    isSwitching,
    invalidate: () => qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] }),
  };
}
