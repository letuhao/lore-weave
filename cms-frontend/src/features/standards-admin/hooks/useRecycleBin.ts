import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  listSystemTrash,
  restoreSystemAttribute,
  restoreSystemGenre,
  restoreSystemKind,
} from '../api';
import { describeError } from '../errors';

const KEY = ['system-trash'];

/** Controller for the System-tier recycle bin (G-C8): lists soft-deleted
 *  genres/kinds/attributes and restores them. A restore invalidates the bin AND
 *  the live list queries so the row reappears in its panel. Restoring an attribute
 *  whose parent kind/genre is still deprecated 422s — surfaced in the status banner. */
export function useRecycleBin() {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const list = useQuery({
    queryKey: KEY,
    queryFn: () => listSystemTrash(accessToken),
  });

  const afterRestore = useCallback(
    (label: string) => {
      setStatus({ kind: 'ok', text: `Restored ${label}.` });
      qc.invalidateQueries({ queryKey: KEY });
      qc.invalidateQueries({ queryKey: ['system-genres'] });
      qc.invalidateQueries({ queryKey: ['system-kinds'] });
      qc.invalidateQueries({ queryKey: ['system-attributes'] });
    },
    [qc],
  );
  const onError = useCallback((err: unknown) => setStatus({ kind: 'err', text: describeError(err) }), []);

  const restoreGenre = useMutation({
    mutationFn: (id: string) => restoreSystemGenre(accessToken, id),
    onSuccess: (g) => afterRestore(`genre “${g.name}”`),
    onError,
  });
  const restoreKind = useMutation({
    mutationFn: (id: string) => restoreSystemKind(accessToken, id),
    onSuccess: (k) => afterRestore(`kind “${k.name}”`),
    onError,
  });
  const restoreAttribute = useMutation({
    mutationFn: (id: string) => restoreSystemAttribute(accessToken, id),
    onSuccess: (a) => afterRestore(`attribute “${a.name}”`),
    onError,
  });

  const clearStatus = useCallback(() => setStatus(null), []);

  return { list, restoreGenre, restoreKind, restoreAttribute, status, clearStatus };
}
