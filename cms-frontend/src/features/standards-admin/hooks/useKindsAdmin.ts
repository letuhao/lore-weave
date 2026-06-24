import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  createSystemKind,
  deleteSystemKind,
  listSystemKinds,
  updateSystemKind,
} from '../api';
import { describeError } from '../errors';
import type { KindCreate, KindUpdate } from '../types';

const KEY = ['system-kinds'];

export function useKindsAdmin() {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const list = useQuery({
    queryKey: KEY,
    queryFn: () => listSystemKinds(accessToken),
  });

  const invalidate = useCallback(() => qc.invalidateQueries({ queryKey: KEY }), [qc]);

  const create = useMutation({
    mutationFn: (body: KindCreate) => createSystemKind(accessToken, body),
    onSuccess: (k) => {
      setStatus({ kind: 'ok', text: `Created kind “${k.name}”.` });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: KindUpdate }) =>
      updateSystemKind(accessToken, id, body),
    onSuccess: (k) => {
      setStatus({ kind: 'ok', text: `Saved kind “${k.name}”.` });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteSystemKind(accessToken, id),
    onSuccess: () => {
      setStatus({ kind: 'ok', text: 'Deleted kind.' });
      invalidate();
    },
    onError: (err) => setStatus({ kind: 'err', text: describeError(err) }),
  });

  const clearStatus = useCallback(() => setStatus(null), []);

  return { list, create, update, remove, status, clearStatus };
}
