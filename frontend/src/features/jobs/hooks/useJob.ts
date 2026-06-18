import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { jobsApi } from '../api';

/** One job's detail (owner-scoped; 404 anti-oracle on not-found-or-not-owned). */
export function useJob(service: string, jobId: string) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['jobs', 'detail', service, jobId],
    queryFn: () => jobsApi.get(service, jobId, accessToken!),
    enabled: !!accessToken && !!service && !!jobId,
  });
}
