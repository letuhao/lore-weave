import { JobsStreamProvider } from '../context/JobsStreamProvider';
import { JobsList } from '../components/JobsList';
import { JobsMobile } from '../components/mobile/JobsMobile';
import { useIsMobile } from '@/features/knowledge/hooks/useIsMobile';

/** /jobs route shell — the unified Jobs dashboard. One SSE connection (provider)
 *  feeds both the desktop table and the dedicated mobile card list. */
export function JobsPage() {
  const isMobile = useIsMobile();
  return (
    <JobsStreamProvider>{isMobile ? <JobsMobile /> : <JobsList />}</JobsStreamProvider>
  );
}
