import { Navigate, useParams } from 'react-router-dom';

import { JobsStreamProvider } from '../context/JobsStreamProvider';
import { JobMonitor } from '../components/JobMonitor';
import { useJob } from '../hooks/useJob';

/** /jobs/:service/:jobId — generic job detail. A campaign job redirects to the
 *  existing campaign monitor (kept as-is); everything else renders JobMonitor. */
function DetailBody({ service, jobId }: { service: string; jobId: string }) {
  const detail = useJob(service, jobId);
  if (detail.data?.kind === 'campaign') {
    return <Navigate to={`/campaigns/${jobId}`} replace />;
  }
  return <JobMonitor service={service} jobId={jobId} />;
}

export function JobDetailPage() {
  const { service = '', jobId = '' } = useParams();
  return (
    <JobsStreamProvider>
      <DetailBody service={service} jobId={jobId} />
    </JobsStreamProvider>
  );
}
