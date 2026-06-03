import { useTranslation } from 'react-i18next';
import { ShieldCheck } from 'lucide-react';
import { useUserModels } from '../../hooks/useUserModels';
import { H0Marker } from '../badges';

export interface ComposeConfigValue {
  genModel: string;
  embedModel: string;
  maxSpend: string; // raw input; '' = no cap
  topK: number;
}

interface Props {
  value: ComposeConfigValue;
  onChange: (v: ComposeConfigValue) => void;
}

/** Shared compose output config — generation + embedding model pickers (BYOK via
 *  provider-registry), cost-cap, top-K — plus the ①②③④ copyright-safety strip and
 *  the H0 chip. (Mode D does no retrieval, but the embedding model is still required
 *  by the async runner — see deferral D-COMPOSE-S1-EMBED-REF.) View-only. */
export function ComposeConfig({ value, onChange }: Props) {
  const { t } = useTranslation('enrichment');
  const gens = useUserModels('chat');
  const embeds = useUserModels('embedding');

  return (
    <div className="space-y-3 rounded-lg border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center gap-4 text-xs">
        <label className="flex items-center gap-1">
          <span className="text-muted-foreground">{t('compose.config.gen_model')}</span>
          <select
            value={value.genModel}
            onChange={(e) => onChange({ ...value, genModel: e.target.value })}
            data-testid="compose-gen-model"
            className="rounded border bg-background px-2 py-1"
          >
            <option value="">{t('compose.config.select_model')}</option>
            {gens.map((m) => (
              <option key={m.user_model_id} value={m.user_model_id}>
                {m.alias || m.provider_model_name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          <span className="text-muted-foreground">{t('compose.config.embed_model')}</span>
          <select
            value={value.embedModel}
            onChange={(e) => onChange({ ...value, embedModel: e.target.value })}
            data-testid="compose-embed-model"
            className="rounded border bg-background px-2 py-1"
          >
            <option value="">{t('compose.config.select_model')}</option>
            {embeds.map((m) => (
              <option key={m.user_model_id} value={m.user_model_id}>
                {m.alias || m.provider_model_name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          <span className="text-muted-foreground">{t('compose.config.max_spend')}</span>
          <input
            type="number"
            min={0}
            step="0.01"
            value={value.maxSpend}
            placeholder={t('compose.config.no_cap')}
            onChange={(e) => onChange({ ...value, maxSpend: e.target.value })}
            data-testid="compose-max-spend"
            className="w-20 rounded border bg-background px-2 py-1"
          />
        </label>
        <label className="flex items-center gap-1">
          <span className="text-muted-foreground">{t('compose.config.top_k')}</span>
          <input
            type="number"
            min={1}
            max={20}
            value={value.topK}
            onChange={(e) => onChange({ ...value, topK: Number(e.target.value) })}
            data-testid="compose-top-k"
            className="w-16 rounded border bg-background px-2 py-1"
          />
        </label>
      </div>
      <div className="flex items-center gap-2 border-t pt-2">
        <ShieldCheck className="h-3.5 w-3.5 text-primary" />
        <span className="text-[11px] text-muted-foreground">{t('compose.safety')}</span>
        <H0Marker />
      </div>
    </div>
  );
}
