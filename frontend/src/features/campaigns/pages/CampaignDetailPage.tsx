import { useParams } from 'react-router-dom';
import { CampaignDetail } from '../components/CampaignDetail';

export function CampaignDetailPage() {
  const { campaignId } = useParams<{ campaignId: string }>();
  if (!campaignId) return null;
  return (
    <div className="p-6">
      <CampaignDetail campaignId={campaignId} />
    </div>
  );
}
