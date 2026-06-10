import { useParams } from 'react-router-dom';
import { CampaignMonitor } from '../components/CampaignMonitor';

export function CampaignDetailPage() {
  const { campaignId } = useParams<{ campaignId: string }>();
  if (!campaignId) return null;
  return (
    <div className="p-6">
      <CampaignMonitor campaignId={campaignId} />
    </div>
  );
}
