import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { useEnrichmentContext } from '../../context/EnrichmentContext';
import { useCompose } from '../../hooks/useCompose';
import type { ComposeTargetInput, ExpandMode } from '../../types';
import { ModeSelector, type ComposeMode } from './ModeSelector';
import { ComposeDraftForm } from './ComposeDraftForm';
import { ComposeTarget } from './ComposeTarget';
import { ComposeConfig, type ComposeConfigValue } from './ComposeConfig';

const DEFAULT_TARGET: ComposeTargetInput = {
  mode: 'existing',
  canonical_name: '',
  entity_kind: 'location',
  target_ref: '',
};
const DEFAULT_CONFIG: ComposeConfigValue = { genModel: '', embedModel: '', maxSpend: '', topK: 5 };

/** The "Tạo / Compose" panel — the controller for the unified input modes. Slice 1
 *  drives mode D (draft expansion): pick a target (existing | new) + paste a draft +
 *  expand mode + models, then run an async compose job (202 → worker → quarantined
 *  proposal). Mode A routes to the Gaps tab; B/C/F are disabled until slices 2–4.
 *  Owns the form state; the API call + invalidation live in useCompose. */
export function ComposePanel() {
  const { t } = useTranslation('enrichment');
  const { bookId, setActivePanel } = useEnrichmentContext();
  const { compose, composing } = useCompose(bookId);

  const [mode, setMode] = useState<ComposeMode>('draft');
  const [target, setTarget] = useState<ComposeTargetInput>(DEFAULT_TARGET);
  const [draftText, setDraftText] = useState('');
  const [expandMode, setExpandMode] = useState<ExpandMode>('rewrite');
  const [config, setConfig] = useState<ComposeConfigValue>(DEFAULT_CONFIG);

  const canRun =
    mode === 'draft' &&
    draftText.trim() !== '' &&
    target.canonical_name.trim() !== '' &&
    !!config.genModel &&
    !!config.embedModel &&
    !composing;

  const run = () => {
    // /review-impl #2: clamp the numeric inputs at the boundary so a cleared field
    // (Number('')→0 / NaN) can't send an out-of-range top_k (backend ge=1) or a
    // silent NaN→null spend. top_k → [1,20]; spend → a finite ≥0 number, else no cap.
    const spend = Number(config.maxSpend);
    const maxSpend =
      config.maxSpend.trim() !== '' && Number.isFinite(spend) && spend >= 0 ? spend : null;
    const topK = Math.min(20, Math.max(1, Math.trunc(Number(config.topK)) || 5));
    return compose({
      input_source: 'draft',
      target: {
        ...target,
        canonical_name: target.canonical_name.trim(),
        target_ref: target.mode === 'new' ? null : target.canonical_name.trim(),
      },
      draft_text: draftText.trim(),
      expand_mode: expandMode,
      generation_model_ref: config.genModel,
      embedding_model_ref: config.embedModel,
      max_spend_usd: maxSpend,
      top_k: topK,
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">{t('compose.title')}</h3>
        <p className="text-xs text-muted-foreground">{t('compose.subtitle')}</p>
      </div>

      <ModeSelector mode={mode} onSelect={setMode} onUseGaps={() => setActivePanel('gaps')} />

      {mode === 'draft' && (
        <>
          <ComposeTarget target={target} onChange={setTarget} />
          <ComposeDraftForm
            draftText={draftText}
            onDraftChange={setDraftText}
            expandMode={expandMode}
            onExpandModeChange={setExpandMode}
          />
          <ComposeConfig value={config} onChange={setConfig} />
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] text-muted-foreground">{t('compose.run_hint')}</p>
            <button
              type="button"
              onClick={() => void run()}
              disabled={!canRun}
              data-testid="compose-run"
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <Sparkles className="h-3.5 w-3.5" />
              {composing ? t('compose.composing') : t('compose.run')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
