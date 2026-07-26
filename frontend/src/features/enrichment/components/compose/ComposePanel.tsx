import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { useEnrichmentContext } from '../../context/EnrichmentContext';
import { useCompose } from '../../hooks/useCompose';
import { useBookEntities } from '../../hooks/useBookEntities';
import { useComposeDimensions } from '../../hooks/useComposeDimensions';
import { useUploads } from '../../hooks/useUploads';
import type { ComposeTargetInput, ContextLicense, ExpandMode } from '../../types';
import { ModeSelector, type ComposeMode } from './ModeSelector';
import { ComposeDraftForm } from './ComposeDraftForm';
import { ComposeContextForm } from './ComposeContextForm';
import { ComposeFilesForm } from './ComposeFilesForm';
import { ComposeIntentForm } from './ComposeIntentForm';
import { ComposeTarget } from './ComposeTarget';
import { ComposeConfig, type ComposeConfigValue } from './ComposeConfig';

const DEFAULT_TARGET: ComposeTargetInput = {
  mode: 'existing',
  canonical_name: '',
  entity_kind: 'location',
  target_ref: '',
};
const DEFAULT_CONFIG: ComposeConfigValue = {
  genModel: '',
  embedModel: '',
  maxSpend: '',
  topK: 5,
  technique: 'retrieval',
  requestedDimensions: null, // null = auto (server derives the dimensions)
};

interface ComposePanelProps {
  /** Cross-panel "use gaps" routing (mode A in ModeSelector). Defaults to the internal
   *  EnrichmentView tab-switch (`setActivePanel('gaps')`) so the classic tabbed
   *  EnrichmentTab shell keeps working unmodified (DOCK-2 — no fork). The standalone
   *  `enrichment-compose` studio dock panel has no sibling tab reading `activePanel`
   *  (each of the 6 dock panels mounts its own EnrichmentProvider instance), so it
   *  overrides this to a real `host.openPanel('enrichment-gaps')` jump — otherwise the
   *  button would silently no-op once split out of the tab strip. */
  onUseGaps?: () => void;
}

/** The "Tạo / Compose" panel — the controller for the unified input modes. Drives
 *  mode D (draft expansion) and mode C (paste-context): pick a target (existing | new)
 *  + provide the input (a draft, or pasted reference text + license) + models, then run
 *  an async compose job (202 → worker → quarantined proposal). Mode F (files) uploads
 *  files (extract+OCR), then grounds on them like context. Mode B (intent) resolves a
 *  free-text intent into a target (2-step: resolve→confirm→run). Mode A routes to the
 *  Gaps tab. Owns the form state; the API calls live in useCompose / useUploads. */
export function ComposePanel({ onUseGaps }: ComposePanelProps = {}) {
  const { t } = useTranslation('enrichment');
  const { bookId, setActivePanel } = useEnrichmentContext();
  const { compose, composing, resolveIntent, resolving } = useCompose(bookId);
  const entities = useBookEntities(bookId); // existing-target autocomplete (best-effort)

  const [mode, setMode] = useState<ComposeMode>('draft');
  const [target, setTarget] = useState<ComposeTargetInput>(DEFAULT_TARGET);
  const [draftText, setDraftText] = useState('');
  const [expandMode, setExpandMode] = useState<ExpandMode>('rewrite');
  const [contextText, setContextText] = useState('');
  const [contextLicense, setContextLicense] = useState<ContextLicense>('public_domain');
  const [filesLicense, setFilesLicense] = useState<ContextLicense>('public_domain');
  const [filesResponsibility, setFilesResponsibility] = useState(false);
  const [persistCorpus, setPersistCorpus] = useState(false); // #7: keep paste/files as a curated source
  const uploads = useUploads(bookId);
  const [intentText, setIntentText] = useState('');
  const [intentTechnique, setIntentTechnique] = useState('fabrication');
  const [intentRationale, setIntentRationale] = useState('');
  const [intentDimensions, setIntentDimensions] = useState<string[]>([]);
  const [config, setConfig] = useState<ComposeConfigValue>(DEFAULT_CONFIG);

  // #1/#2: grounded modes (context/files/intent) offer the dimension picker; the
  // technique selector is for the corpus-grounded modes (context/files). Draft uses
  // expand_mode + compose_draft; intent uses its resolved technique.
  const grounded = mode === 'context' || mode === 'files' || mode === 'intent';
  const dimensions = useComposeDimensions(bookId, target.entity_kind);

  const showComposer = mode === 'draft' || mode === 'context' || mode === 'files' || mode === 'intent';
  const targetOk = target.canonical_name.trim() !== '';
  const canRun =
    !composing &&
    targetOk &&
    !!config.genModel &&
    ((mode === 'draft' && draftText.trim() !== '') ||
      // mode C embeds the paste → embed model REQUIRED + copyrighted is refused.
      (mode === 'context' &&
        contextText.trim() !== '' &&
        !!config.embedModel &&
        contextLicense !== 'copyrighted') ||
      // mode F: ≥1 ready upload + embed model + license OK + responsibility acknowledged.
      (mode === 'files' &&
        uploads.readyIds.length > 0 &&
        !!config.embedModel &&
        filesLicense !== 'copyrighted' &&
        filesResponsibility) ||
      // mode B: a confirmed target (resolved or edited); embed only if the resolved
      // technique is retrieval (fabrication needs none).
      (mode === 'intent' && (intentTechnique !== 'retrieval' || !!config.embedModel)));

  const canResolveIntent = intentText.trim() !== '' && !!config.genModel && !resolving;

  // review-impl #1: dimension ids are per-kind, so a pick made for one kind is stale
  // after switching kinds (it would silently match nothing → a no-op run). Reset the
  // picker to auto whenever the target kind changes. Explicit handler (no useEffect).
  const handleTargetChange = (next: ComposeTargetInput) => {
    if (next.entity_kind !== target.entity_kind && config.requestedDimensions !== null) {
      setConfig((c) => ({ ...c, requestedDimensions: null }));
    }
    setTarget(next);
  };

  const handleResolveIntent = async () => {
    const r = await resolveIntent(intentText.trim(), config.genModel);
    if (!r) return;
    // Route through handleTargetChange so a resolved kind that differs from the
    // current one resets a stale dimension pick (review-impl #1).
    handleTargetChange({
      mode: r.target.mode,
      canonical_name: r.target.canonical_name,
      entity_kind: r.target.entity_kind,
      target_ref: r.target.mode === 'new' ? null : r.target.canonical_name,
    });
    setIntentTechnique(r.technique);
    setIntentRationale(r.rationale);
    setIntentDimensions(r.dimensions ?? []);
  };

  const run = () => {
    // /review-impl #2: clamp the numeric inputs at the boundary so a cleared field
    // (Number('')→0 / NaN) can't send an out-of-range top_k (backend ge=1) or a
    // silent NaN→null spend. top_k → [1,20]; spend → a finite ≥0 number, else no cap.
    const spend = Number(config.maxSpend);
    const maxSpend =
      config.maxSpend.trim() !== '' && Number.isFinite(spend) && spend >= 0 ? spend : null;
    const topK = Math.min(20, Math.max(1, Math.trunc(Number(config.topK)) || 5));
    const targetInput: ComposeTargetInput = {
      ...target,
      canonical_name: target.canonical_name.trim(),
      target_ref: target.mode === 'new' ? null : target.canonical_name.trim(),
      // #1: send the dimension pick only for grounded modes, and only when the
      // author actually narrowed to ≥1 dim. null (auto) OR an empty manual list →
      // omit, so the server derives the dimensions (prior behavior) — "deselect all"
      // means "no narrowing", never "enrich nothing" (review-impl #2).
      requested_dimensions:
        grounded && config.requestedDimensions && config.requestedDimensions.length > 0
          ? config.requestedDimensions
          : undefined,
    };
    if (mode === 'context') {
      return compose({
        input_source: 'context',
        target: targetInput,
        context_text: contextText.trim(),
        context_license: contextLicense,
        persist_corpus: persistCorpus, // #7: keep as a curated source vs ephemeral
        technique: config.technique, // #2: author-chosen technique (retrieval|fabrication|recook)
        generation_model_ref: config.genModel,
        embedding_model_ref: config.embedModel || undefined,
        max_spend_tokens: maxSpend,
        top_k: topK,
      });
    }
    if (mode === 'files') {
      return compose({
        input_source: 'files',
        target: targetInput,
        upload_ids: uploads.readyIds,
        persist_corpus: persistCorpus, // #7
        technique: config.technique, // #2
        generation_model_ref: config.genModel,
        embedding_model_ref: config.embedModel || undefined,
        max_spend_tokens: maxSpend,
        top_k: topK,
      });
    }
    if (mode === 'intent') {
      return compose({
        input_source: 'intent',
        target: targetInput,
        intent_text: intentText.trim() || undefined,
        technique: intentTechnique,
        generation_model_ref: config.genModel,
        embedding_model_ref: config.embedModel || undefined,
        max_spend_tokens: maxSpend,
        top_k: topK,
      });
    }
    return compose({
      input_source: 'draft',
      target: targetInput,
      draft_text: draftText.trim(),
      expand_mode: expandMode,
      generation_model_ref: config.genModel,
      // omit when unset → the BE treats embed as optional for draft.
      embedding_model_ref: config.embedModel || undefined,
      max_spend_tokens: maxSpend,
      top_k: topK,
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">{t('compose.title')}</h3>
        <p className="text-xs text-muted-foreground">{t('compose.subtitle')}</p>
      </div>

      <ModeSelector mode={mode} onSelect={setMode} onUseGaps={onUseGaps ?? (() => setActivePanel('gaps'))} />

      {showComposer && (
        <>
          {mode === 'intent' && (
            <ComposeIntentForm
              intentText={intentText}
              onIntentChange={setIntentText}
              onResolve={() => void handleResolveIntent()}
              resolving={resolving}
              canResolve={canResolveIntent}
              rationale={intentRationale}
              resolvedTechnique={intentRationale ? intentTechnique : null}
              dimensions={intentDimensions}
            />
          )}
          <ComposeTarget target={target} onChange={handleTargetChange} entities={entities} />
          {mode === 'draft' && (
            <ComposeDraftForm
              draftText={draftText}
              onDraftChange={setDraftText}
              expandMode={expandMode}
              onExpandModeChange={setExpandMode}
            />
          )}
          {mode === 'context' && (
            <ComposeContextForm
              contextText={contextText}
              onContextTextChange={setContextText}
              license={contextLicense}
              onLicenseChange={setContextLicense}
            />
          )}
          {mode === 'files' && (
            <ComposeFilesForm
              items={uploads.items}
              onAddFiles={(files) => files.forEach((f) => void uploads.upload(f, filesLicense))}
              onRemove={uploads.remove}
              license={filesLicense}
              onLicenseChange={setFilesLicense}
              responsibilityChecked={filesResponsibility}
              onResponsibilityChange={setFilesResponsibility}
            />
          )}
          {(mode === 'context' || mode === 'files') && (
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={persistCorpus}
                onChange={(e) => setPersistCorpus(e.target.checked)}
                data-testid="compose-persist-corpus"
              />
              {t('compose.save_corpus')}
            </label>
          )}
          <ComposeConfig
            value={config}
            onChange={setConfig}
            showTechnique={mode === 'context' || mode === 'files'}
            dimensions={grounded ? dimensions : []}
          />
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
