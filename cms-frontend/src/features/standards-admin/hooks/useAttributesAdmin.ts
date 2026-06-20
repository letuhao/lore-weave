import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  createSystemAttribute,
  deleteSystemAttribute,
  listSystemAttributes,
  listSystemGenres,
  listSystemKinds,
  updateSystemAttribute,
} from '../api';
import { describeError } from '../errors';
import type { AttributeCreate, AttributeUpdate } from '../types';

export function useAttributesAdmin(kindId: string, genreId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const kinds = useQuery({
    queryKey: ['system-kinds'],
    queryFn: () => listSystemKinds(accessToken),
  });

  const genres = useQuery({
    queryKey: ['system-genres'],
    queryFn: () => listSystemGenres(accessToken),
  });

  const selected = Boolean(kindId && genreId);
  const attrsKey = ['system-attributes', kindId, genreId];

  const attributes = useQuery({
    queryKey: attrsKey,
    queryFn: () => listSystemAttributes(accessToken, kindId, genreId),
    enabled: selected,
  });

  const invalidate = useCallback(
    () => qc.invalidateQueries({ queryKey: attrsKey }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [qc, kindId, genreId],
  );

  const create = useMutation({
    mutationFn: (body: AttributeCreate) => createSystemAttribute(accessToken, body),
    onSuccess: (a) => {
      setStatus({ kind: 'ok', text: `Created attribute “${a.name}”.` });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AttributeUpdate }) =>
      updateSystemAttribute(accessToken, id, body),
    onSuccess: (a) => {
      setStatus({ kind: 'ok', text: `Saved attribute “${a.name}”.` });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteSystemAttribute(accessToken, id),
    onSuccess: () => {
      setStatus({ kind: 'ok', text: 'Deleted attribute.' });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const clearStatus = useCallback(() => setStatus(null), []);

  return { kinds, genres, attributes, selected, create, update, remove, status, clearStatus };
}
