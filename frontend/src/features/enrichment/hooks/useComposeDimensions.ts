import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';
import type { ComposeDimension } from '../types';

/** The choosable dimensions for an entity KIND (#1 compose dimension picker).
 *  Best-effort — returns [] until loaded / on no auth / on error, so the picker
 *  degrades to "auto" (the server derives dimensions) rather than blocking the run.
 *  Keyed by (book, kind) so switching the target kind refetches its dimensions. */
export function useComposeDimensions(
  bookId: string,
  kind: string,
  opts: { base?: boolean } = {},
): ComposeDimension[] {
  const base = opts.base ?? false;
  const { accessToken } = useAuth();
  const { data } = useQuery({
    queryKey: ['compose-dimensions', bookId, kind, base],
    queryFn: () => enrichmentApi.listComposeDimensions(bookId, kind, accessToken!, base),
    enabled: !!accessToken && !!bookId && !!kind,
  });
  return data?.dimensions ?? [];
}
