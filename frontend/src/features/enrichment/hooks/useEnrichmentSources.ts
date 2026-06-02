import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';

/** List + register the book's source corpora (the recook/retrieval material). The
 *  license tag governs recook admissibility (default-deny). */
export function useEnrichmentSources(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const { t } = useTranslation('enrichment');
  const [busy, setBusy] = useState(false);

  const query = useQuery({
    queryKey: ['enrichment-sources', bookId],
    queryFn: () => enrichmentApi.listSources(bookId, accessToken!),
    enabled: !!accessToken && !!bookId,
  });

  const register = async (body: { name: string; kind: string; license?: string }) => {
    setBusy(true);
    try {
      const s = await enrichmentApi.registerSource(bookId, body, accessToken!);
      toast.success(t('sources.registered'));
      qc.invalidateQueries({ queryKey: ['enrichment-sources', bookId] });
      return s;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  };

  return {
    ...query,
    items: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    register,
    busy,
  };
}
