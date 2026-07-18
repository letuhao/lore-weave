// M2 controller — the platform home. Reads the BFF /v1/home composition (which already applies the
// degrade contract server-side: per-tile status, never blank). react-query gives caching + a
// window-focus refresh; the view renders each tile by its status. CLAUDE.md MVC: logic here, the
// view only renders.
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { homeApi } from '../api';

export function useHome() {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['home'],
    queryFn: () => homeApi.getHome(accessToken),
    enabled: !!accessToken,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}
