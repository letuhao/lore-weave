import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '../../ai-models/api';
import {
  knowledgeApi,
  type EstimateExtractionPayload,
  type ExtractionJobScopeWire,
  type ExtractionStartPayload,
} from '../api';
import type { BenchmarkStatus, Project } from '../types';
import type { CostEstimate } from '../types/projectState';
import { EmbeddingModelPicker } from './EmbeddingModelPicker';

// K19a.5 — modal for starting an extraction job. Triggered from the
// DisabledCard's "Build graph" button (and replaces the K19a.4 toast-stub
// for `onStart`). Owns its own form state; calls /extraction/estimate
// reactively when scope or llm_model change; posts /extraction/start on
// confirm and hands the new job back to the parent via `onStarted`.
//
// Scope omits `glossary_sync` per K19a.5 plan (deferred D-K19a.5-06 when
// lore sync surfaces). `scope_range.chapter_range` omitted from MVP — BE
// preview honours it but runner doesn't (D-K16.2-02b). Budget context
// (monthly remaining) deferred to K19b.6.

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
  /** Fires after /extraction/start returns 201. The parent typically
   * invalidates the jobs query — the new job payload is provided for
   * callers that need it (e.g. optimistic state). */
  onStarted: () => void;
}

const ALL_SCOPES: ExtractionJobScopeWire[] = ['chapters', 'chat', 'all'];
const DECIMAL_REGEX = /^\d+(\.\d{1,2})?$/;
const ESTIMATE_DEBOUNCE_MS = 300;

// review-impl F1 — BE wraps 409 bodies as `{detail: {error_code, message, ...}}`
// (FastAPI default). apiJson only surfaces the top-level `.message`, which is
// undefined for that shape, so the thrown Error carries res.statusText
// ("Conflict") instead of the real explanation. Walk the attached `body`
// ourselves to pull the structured message when present. Exported for the
// unit test that proves the extraction logic works independent of i18n.
export function readBackendError(err: unknown): string {
  if (err instanceof Error) {
    const body = (err as Error & { body?: unknown }).body;
    if (body && typeof body === 'object') {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === 'string' && detail.length > 0) return detail;
      if (detail && typeof detail === 'object' && 'message' in detail) {
        const msg = (detail as { message?: unknown }).message;
        if (typeof msg === 'string' && msg.length > 0) return msg;
      }
    }
    if (err.message) return err.message;
  }
  return String(err);
}

export function BuildGraphDialog({ open, onOpenChange, project, onStarted }: Props) {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();

  // Default scope: `chapters` if the project is linked to a book, else
  // `all`. Users can still switch freely.
  const defaultScope: ExtractionJobScopeWire = project.book_id ? 'chapters' : 'all';

  const [scope, setScope] = useState<ExtractionJobScopeWire>(defaultScope);
  const [llmModel, setLlmModel] = useState<string>('');
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(
    project.embedding_model ?? null,
  );
  const [maxSpend, setMaxSpend] = useState<string>('');
  const [starting, setStarting] = useState(false);
  // 300 ms debounced copy of (scope, llmModel) — prevents a burst of
  // /estimate calls on rapid toggles. React-Query keyed by the debounced
  // tuple auto-cancels stale requests on key change.
  const [debounced, setDebounced] = useState<{ scope: ExtractionJobScopeWire; llm: string }>({
    scope: defaultScope,
    llm: '',
  });

  // Reset form every time the dialog opens. Keeps per-open defaults
  // clean even if the user leaves values behind from a prior attempt.
  useEffect(() => {
    if (!open) return;
    setScope(defaultScope);
    setLlmModel('');
    setEmbeddingModel(project.embedding_model ?? null);
    setMaxSpend('');
    setStarting(false);
    setDebounced({ scope: defaultScope, llm: '' });
  }, [open, defaultScope, project.embedding_model]);

  // Debounce scope/llm changes into `debounced`.
  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(
      () => setDebounced({ scope, llm: llmModel }),
      ESTIMATE_DEBOUNCE_MS,
    );
    return () => window.clearTimeout(handle);
  }, [open, scope, llmModel]);

  // Fetch the user's chat-capable models for the LLM dropdown.
  const modelsQuery = useQuery<{ items: UserModel[] }>({
    queryKey: ['ai-models', 'chat'],
    queryFn: () =>
      aiModelsApi.listUserModels(accessToken!, { capability: 'chat', include_inactive: false }),
    enabled: open && !!accessToken,
    staleTime: 60_000,
  });

  // Auto-estimate when we have a debounced llm_model + scope.
  const estimateQuery = useQuery<CostEstimate>({
    queryKey: [
      'knowledge',
      'estimate',
      project.project_id,
      debounced.scope,
      debounced.llm,
    ],
    queryFn: () => {
      const payload: EstimateExtractionPayload = {
        scope: debounced.scope,
        llm_model: debounced.llm,
      };
      return knowledgeApi.estimateExtraction(project.project_id, payload, accessToken!);
    },
    enabled: open && !!accessToken && debounced.llm !== '',
    staleTime: 30_000,
    retry: false,
  });

  // review-impl F6 — pre-flight benchmark gate. BE /extraction/start
  // returns 409 if the user's chosen embedding_model has no passing
  // K17.9 run. Rather than let the click fail, fetch the same signal
  // the picker badge uses (shared queryKey with EmbeddingModelPicker —
  // react-query dedupes) and disable Confirm when we know the gate
  // would reject. Races (badge passed, gate fails) still surface via
  // the F1 body-extraction path.
  const benchmarkQuery = useQuery<BenchmarkStatus>({
    queryKey: ['knowledge', 'benchmark-status', project.project_id, embeddingModel],
    queryFn: () =>
      knowledgeApi.getBenchmarkStatus(project.project_id, embeddingModel, accessToken!),
    enabled: open && !!accessToken && !!embeddingModel,
    staleTime: 60_000,
    retry: false,
  });

  const maxSpendValid = maxSpend === '' || DECIMAL_REGEX.test(maxSpend);
  const benchmarkOk =
    !benchmarkQuery.data ||
    (benchmarkQuery.data.has_run && benchmarkQuery.data.passed);
  const canConfirm =
    !starting &&
    llmModel !== '' &&
    embeddingModel !== null &&
    embeddingModel !== '' &&
    maxSpendValid &&
    benchmarkOk;

  const handleConfirm = async () => {
    if (!accessToken || !embeddingModel) return;
    if (!maxSpendValid) return;
    setStarting(true);
    try {
      const payload: ExtractionStartPayload = {
        scope,
        llm_model: llmModel,
        embedding_model: embeddingModel,
        ...(maxSpend !== '' ? { max_spend_usd: maxSpend } : {}),
      };
      await knowledgeApi.startExtraction(project.project_id, payload, accessToken);
      onStarted();
      onOpenChange(false);
    } catch (err) {
      toast.error(
        t('projects.buildDialog.startFailed', { error: readBackendError(err) }),
      );
    } finally {
      setStarting(false);
    }
  };

  const chatModels = useMemo(() => modelsQuery.data?.items ?? [], [modelsQuery.data]);
  // review-impl F2 — BE estimate+start treat `chapters` scope as a
  // book-only code path; a project with `book_id=null` would run a
  // no-op job. Hide the radio option in that case so the UI can't
  // select it.
  const availableScopes = useMemo(
    () => ALL_SCOPES.filter((s) => s !== 'chapters' || !!project.book_id),
    [project.book_id],
  );

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('projects.buildDialog.title')}
      description={t('projects.buildDialog.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={starting}
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-secondary disabled:opacity-60"
          >
            {t('projects.buildDialog.cancel')}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {starting
              ? t('projects.buildDialog.starting')
              : t('projects.buildDialog.confirm')}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {/* Scope selector */}
        <fieldset className="flex flex-col gap-1">
          <legend className="text-xs font-medium text-muted-foreground">
            {t('projects.buildDialog.scope.label')}
          </legend>
          <div className="flex flex-wrap gap-3 pt-1">
            {availableScopes.map((s) => (
              <label key={s} className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="scope"
                  value={s}
                  checked={scope === s}
                  onChange={() => setScope(s)}
                />
                <span>{t(`projects.buildDialog.scope.${s}`)}</span>
              </label>
            ))}
          </div>
          {!project.book_id && (
            <span className="text-[11px] text-muted-foreground">
              {t('projects.buildDialog.scope.noBookHint')}
            </span>
          )}
        </fieldset>

        {/* LLM model */}
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('projects.buildDialog.llmModel.label')}
          </span>
          <select
            value={llmModel}
            onChange={(e) => setLlmModel(e.target.value)}
            disabled={modelsQuery.isLoading}
            className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring disabled:opacity-60"
          >
            <option value="">
              {modelsQuery.isLoading
                ? t('projects.buildDialog.llmModel.loading')
                : t('projects.buildDialog.llmModel.placeholder')}
            </option>
            {/* review-impl F7 — two providers can register the same
                provider_model_name (e.g. openai/gpt-5 + proxy/gpt-5).
                `value` must round-trip bare model name because the BE
                `extraction_jobs.llm_model` column stores bare name; the
                label disambiguates visually. Resolution of which
                credential runs the job is BE-side user-model lookup. */}
            {chatModels.map((m) => {
              const label = m.alias
                ? `${m.alias} (${m.provider_model_name})`
                : `${m.provider_kind}/${m.provider_model_name}`;
              return (
                <option key={m.user_model_id} value={m.provider_model_name}>
                  {label}
                </option>
              );
            })}
          </select>
          {!modelsQuery.isLoading && chatModels.length === 0 && (
            <span className="text-[11px] text-muted-foreground">
              {t('projects.buildDialog.llmModel.empty')}
            </span>
          )}
        </label>

        {/* Embedding model (reuse K12.4 picker) */}
        <EmbeddingModelPicker
          value={embeddingModel}
          onChange={setEmbeddingModel}
          projectId={project.project_id}
        />

        {/* Max spend */}
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('projects.buildDialog.maxSpend.label')}
          </span>
          <input
            type="text"
            inputMode="decimal"
            value={maxSpend}
            onChange={(e) => setMaxSpend(e.target.value)}
            placeholder="0.00"
            aria-invalid={!maxSpendValid}
            className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring aria-[invalid=true]:border-destructive"
          />
          <span className="text-[11px] text-muted-foreground">
            {t('projects.buildDialog.maxSpend.hint')}
          </span>
          {!maxSpendValid && (
            <span className="text-[11px] text-destructive">
              {t('projects.buildDialog.maxSpend.invalid')}
            </span>
          )}
        </label>

        {/* Estimate preview */}
        <div className="rounded-md border border-dashed p-3">
          <h4 className="mb-1 text-xs font-medium text-muted-foreground">
            {t('projects.buildDialog.estimate.heading')}
          </h4>
          {debounced.llm === '' && (
            <p className="text-[12px] text-muted-foreground">
              {t('projects.buildDialog.estimate.pickLlmFirst')}
            </p>
          )}
          {debounced.llm !== '' && estimateQuery.isLoading && (
            <p className="text-[12px] text-muted-foreground">
              {t('projects.buildDialog.estimate.loading')}
            </p>
          )}
          {debounced.llm !== '' && estimateQuery.error && (
            <p className="text-[12px] text-destructive">
              {t('projects.buildDialog.estimate.failed', {
                error: readBackendError(estimateQuery.error),
              })}
            </p>
          )}
          {estimateQuery.data && (
            <div className="flex flex-col gap-0.5 text-[12px]">
              <span>
                {t('projects.buildDialog.estimate.cost', {
                  low: estimateQuery.data.estimated_cost_usd_low,
                  high: estimateQuery.data.estimated_cost_usd_high,
                })}
              </span>
              <span>
                {t('projects.buildDialog.estimate.items', {
                  chapters: estimateQuery.data.items.chapters,
                  turns: estimateQuery.data.items.chat_turns,
                  tokens: estimateQuery.data.estimated_tokens,
                })}
              </span>
              <span className="text-muted-foreground">
                {t('projects.buildDialog.estimate.duration', {
                  seconds: estimateQuery.data.estimated_duration_seconds,
                })}
              </span>
            </div>
          )}
        </div>
      </div>
    </FormDialog>
  );
}
