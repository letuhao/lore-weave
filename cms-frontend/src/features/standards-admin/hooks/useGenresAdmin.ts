import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  createSystemGenre,
  deleteSystemGenre,
  listSystemGenres,
  updateSystemGenre,
} from '../api';
import { describeError } from '../errors';
import type { GenreCreate, GenreUpdate } from '../types';

const KEY = ['system-genres'];

export function useGenresAdmin() {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const list = useQuery({
    queryKey: KEY,
    queryFn: () => listSystemGenres(accessToken),
  });

  const invalidate = useCallback(() => qc.invalidateQueries({ queryKey: KEY }), [qc]);

  const create = useMutation({
    mutationFn: (body: GenreCreate) => createSystemGenre(accessToken, body),
    onSuccess: (g) => {
      setStatus({ kind: 'ok', text: `Created genre “${g.name}”.` });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: GenreUpdate }) =>
      updateSystemGenre(accessToken, id, body),
    onSuccess: (g) => {
      setStatus({ kind: 'ok', text: `Saved genre “${g.name}”.` });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteSystemGenre(accessToken, id),
    onSuccess: () => {
      setStatus({ kind: 'ok', text: 'Deleted genre.' });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const clearStatus = useCallback(() => setStatus(null), []);

  return { list, create, update, remove, status, clearStatus };
}
