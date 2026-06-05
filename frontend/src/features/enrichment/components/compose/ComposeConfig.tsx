import { useTranslation } from 'react-i18next';
import { ShieldCheck, AlertTriangle } from 'lucide-react';
import { useUserModels } from '../../hooks/useUserModels';
import { H0Marker } from '../badges';
import type { ComposeDimension } from '../../types';

/** Author-pickable techniques for grounded modes (context/files). retrieval=P1,
 *  fabrication=P2, recook=P3 (P2/P3 are eval-gate-locked server-side). */
export const COMPOSE_TECHNIQUES = ['retrieval', 'fabrication', 'recook'] as const;

export interface ComposeConfigValue {
  genModel: string;
  embedModel: string;
  maxSpend: string; // raw input; '' = no cap
  topK: number;
  /** Output technique for grounded modes (context/files). Default 'retrieval'. */
  technique: string;
  /** Dimension picker (#1): the chosen dimension ids, or null = "auto" (server
   *  derives — enrich all missing). [] (manual + none) is allowed (BE no-ops). */
  requestedDimensions: string[] | null;
}

interface Props {
  value: ComposeConfigValue;
  onChange: (v: ComposeConfigValue) => void;
  /** Show the technique selector (the grounded modes context/files; draft forces
   *  compose_draft and intent uses its resolved technique). */
  showTechnique?: boolean;
  /** The target kind's dimensions for the picker; empty → picker hidden (auto). */
  dimensions?: ComposeDimension[];
}

/** Shared compose output config — generation + embedding model pickers (BYOK via
 *  provider-registry), cost-cap, top-K — plus the ①②③④ copyright-safety strip and
 *  the H0 chip. (Mode D does no retrieval, but the embedding model is still required
 *  by the async runner — see deferral D-COMPOSE-S1-EMBED-REF.) View-only. */
export function ComposeConfig({ value, onChange, showTechnique = false, dimensions = [] }: Props) {
  const { t } = useTranslation('enrichment');
  const gens = useUserModels('chat');
  const embeds = useUserModels('embedding');

  const gateLocked = value.technique === 'fabrication' || value.technique === 'recook';
  const auto = value.requestedDimensions === null;
  const selected = new Set(value.requestedDimensions ?? []);
  const toggleAuto = (on: boolean) =>
    onChange({ ...value, requestedDimensions: on ? null : dimensions.map((d) => d.id) });
  const toggleDim = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange({ ...value, requestedDimensions: dimensions.map((d) => d.id).filter((x) => next.has(x)) });
  };

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
      {showTechnique && (
        <div className="flex flex-wrap items-center gap-3 border-t pt-2 text-xs">
          <label className="flex items-center gap-1">
            <span className="text-muted-foreground">{t('compose.config.technique')}</span>
            <select
              value={value.technique}
              onChange={(e) => onChange({ ...value, technique: e.target.value })}
              data-testid="compose-technique"
              className="rounded border bg-background px-2 py-1"
            >
              {COMPOSE_TECHNIQUES.map((tech) => (
                <option key={tech} value={tech}>
                  {t(`compose.config.technique_opt.${tech}`)}
                </option>
              ))}
            </select>
          </label>
          {gateLocked && (
            <span
              className="inline-flex items-center gap-1 text-amber-600"
              data-testid="compose-eval-gate-warning"
            >
              <AlertTriangle className="h-3.5 w-3.5" />
              {t('compose.config.eval_gate_warning')}
            </span>
          )}
        </div>
      )}

      {dimensions.length > 0 && (
        <div className="space-y-2 border-t pt-2 text-xs">
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => toggleAuto(e.target.checked)}
              data-testid="compose-dims-auto"
            />
            <span className="text-muted-foreground">{t('compose.config.dimensions.auto')}</span>
          </label>
          {!auto && (
            <div className="flex flex-wrap gap-1.5" data-testid="compose-dims-picker">
              {dimensions.map((d) => {
                const on = selected.has(d.id);
                return (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => toggleDim(d.id)}
                    aria-pressed={on}
                    className={`rounded-full border px-2 py-0.5 ${
                      on ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground'
                    }`}
                  >
                    {d.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 border-t pt-2">
        <ShieldCheck className="h-3.5 w-3.5 text-primary" />
        <span className="text-[11px] text-muted-foreground">{t('compose.safety')}</span>
        <H0Marker />
      </div>
    </div>
  );
}
