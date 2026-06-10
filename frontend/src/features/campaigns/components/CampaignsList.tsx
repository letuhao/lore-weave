import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import { useCampaigns } from '../hooks/useCampaignQueries';
import { StatusBadge } from './StatusBadge';

/** /campaigns landing (view): the user's campaigns + a New-campaign CTA. */
export function CampaignsList() {
  const { t } = useTranslation('campaigns');
  const { data, isLoading, error } = useCampaigns();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t('list.title', { defaultValue: 'Auto-Draft Campaigns' })}</h1>
        <Link to="/campaigns/new"
          className="inline-flex items-center gap-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          <Plus className="h-4 w-4" />
          {t('list.new', { defaultValue: 'New campaign' })}
        </Link>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">{t('list.loading', { defaultValue: 'Loading…' })}</p>}
      {error && <p className="text-sm text-destructive">{t('list.error', { defaultValue: 'Failed to load campaigns.' })}</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('list.empty', { defaultValue: 'No campaigns yet. Create one to batch-translate a book.' })}</p>
      )}

      {data && data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {data.map((c) => (
            <li key={c.campaign_id}>
              <Link to={`/campaigns/${c.campaign_id}`}
                className="flex items-center justify-between rounded-lg border p-4 hover:bg-accent">
                <span className="flex flex-col gap-1">
                  <span className="font-medium">{c.name}</span>
                  <span className="text-[12px] text-muted-foreground">
                    {t('list.chapters', { defaultValue: '{{count}} chapters', count: c.total_chapters })}
                    {c.budget_usd ? ` · $${Number(c.spent_usd).toFixed(2)} / $${Number(c.budget_usd).toFixed(2)}` : ` · $${Number(c.spent_usd).toFixed(2)}`}
                  </span>
                </span>
                <StatusBadge status={c.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
