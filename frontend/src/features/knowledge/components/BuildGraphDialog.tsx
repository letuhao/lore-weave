import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import { AddModelCta } from '@/components/shared/AddModelCta';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '../../ai-models/api';
import {
  knowledgeApi,
  type EstimateExtractionPayload,
  type ExtractionJobScopeWire,
  type ExtractionStartPayload,
  type ExtractionTarget,
} from '../api';
import type { BenchmarkStatus, Project } from '../types';
import type { CostEstimate } from '../types/projectState';
import { readBackendError } from '../lib/readBackendError';
import { formatUSD } from '../lib/formatUSD';
import { canonicalTargets } from '../lib/targetPicker';
import { useUserCosts } from '../hooks/useUserCosts';
import { EmbeddingModelPicker } from './EmbeddingModelPicker';
import { TargetPicker } from './TargetPicker';
import { BuildWizardSteps, type WizardStep } from './BuildWizardSteps';
import { PinningStep } from './PinningStep';
import { usePinning } from '../hooks/usePinning';

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

/**
 * K19b.5 — optional pre-fill values for the retry flow. Any field
 * that's omitted falls back to the normal per-open defaults (book
 * project → scope="chapters", otherwise "all"; embedding_model from
 * the Project; empty llm_model / max_spend). Parent clears this by
 * passing `undefined` when reopening from a non-retry path.
 */
export interface BuildGraphInitialValues {
  scope?: ExtractionJobScopeWire;
  llmModel?: string;
  embeddingModel?: string | null;
  maxSpend?: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
  /** Fires after /extraction/start returns 201. The parent typically
   * invalidates the jobs query — the new job payload is provided for
   * callers that need it (e.g. optimistic state). */
  onStarted: () => void;
  /** K19b.5: pre-fill the form with a prior job's settings (retry
   *  flow). When present, values override per-open defaults. */
  initialValues?: BuildGraphInitialValues;
}

// C12c-b — `glossary_sync` joins the radio set now that C12c-a shipped
// BE support (new glossary-service paginated endpoint + worker-ai
// branch + knowledge-service sync endpoint). Same book_id gate as
// chapters: both rely on the project's linked book, so `availableScopes`
// below filters both when `project.book_id` is null. The BE's 422
// guard at start_extraction_job (C12c-a MED#1) is the authoritative
// check; this filter is UX so the user never offers an option the BE
// would reject.
const ALL_SCOPES: ExtractionJobScopeWire[] = ['chapters', 'chat', 'glossary_sync', 'all'];
const DECIMAL_REGEX = /^\d+(\.\d{1,2})?$/;
const ESTIMATE_DEBOUNCE_MS = 300;

// review-impl F7 (K19a.6) — `readBackendError` moved to a shared
// `../lib/readBackendError.ts` since multiple dialogs use it. Re-export
// here so existing call sites (unit tests) can keep their imports.
export { readBackendError } from '../lib/readBackendError';

export function BuildGraphDialog({
  open,
  onOpenChange,
  project,
  onStarted,
  initialValues,
}: Props) {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  // Default scope: `chapters` if the project is linked to a book, else
  // `all`. Users can still switch freely.
  const defaultScope: ExtractionJobScopeWire = project.book_id ? 'chapters' : 'all';
  // K19b.5: initialValues overrides the per-open defaults so the
  // retry flow can land the user on their prior settings.
  // C12c-b /review-impl LOW#1: if the prior job's scope is no longer
  // available (book was unlinked between job creation and retry),
  // fall back to defaultScope so the radios always have one checked.
  // Mirrors the `availableScopes` filter condition below.
  const rawOpenScope = initialValues?.scope ?? defaultScope;
  const openScope: ExtractionJobScopeWire =
    (rawOpenScope === 'chapters' || rawOpenScope === 'glossary_sync') && !project.book_id
      ? defaultScope
      : rawOpenScope;
  const openLlm = initialValues?.llmModel ?? '';
  const openEmbedding =
    initialValues?.embeddingModel !== undefined
      ? initialValues.embeddingModel
      : project.embedding_model ?? null;
  const openMaxSpend = initialValues?.maxSpend ?? '';

  const [scope, setScope] = useState<ExtractionJobScopeWire>(openScope);
  const [llmModel, setLlmModel] = useState<string>(openLlm);
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(openEmbedding);
  const [maxSpend, setMaxSpend] = useState<string>(openMaxSpend);
  // KG-EMB-PERSIST — the embedding model the project ACTUALLY has persisted.
  // The benchmark-run + extract gates read the project's STORED model (not the
  // dropdown's local value), so a model the user merely picks here is inert
  // until it's written through. We track the committed model separately so we
  // can (a) persist a FIRST-time selection immediately (non-destructive: no
  // graph yet) and (b) refuse to silently switch an already-set model here
  // (that wipes the graph — it stays in ChangeModelDialog's confirmed flow).
  const [committedModel, setCommittedModel] = useState<string | null>(
    project.embedding_model ?? null,
  );
  const [persistingEmbedding, setPersistingEmbedding] = useState(false);
  // C12a (D-K19a.5-04) — chapter-range picker. Shown only when
  // scope=='chapters'. Both inputs required together; BE 422s on
  // partial range. Empty inputs → no range filter (full scope).
  const [chapterRangeFrom, setChapterRangeFrom] = useState<string>('');
  const [chapterRangeTo, setChapterRangeTo] = useState<string>('');
  const [starting, setStarting] = useState(false);
  // C12 — wizard step + Step-1 target picker + concurrency. Empty target
  // selection ⇒ omit `targets` from the payload ⇒ BE runs all passes
  // (back-compat). The picker enforces the dependent auto-include in-UI.
  const [wizardStep, setWizardStep] = useState<WizardStep>(1);
  const [targets, setTargets] = useState<ExtractionTarget[]>([]);
  const [concurrency, setConcurrency] = useState<string>('');
  // C13 — glossary pinning controller (owns the pinned-set + stats query).
  // Stats fetch is gated on the dialog being open AND a linked book existing
  // (the BE 422s no_book otherwise; pinning has no meaning without a book).
  const pinning = usePinning(project.project_id, open && !!project.book_id);

  // D-K19a.5-03 (cleared in K19b.6): user-wide monthly remaining hint
  // shown near the max_spend input so the user knows how much headroom
  // they have under their aggregate cap before setting a per-job cap.
  // Silently hides when no user-wide cap is set or when the costs
  // query errors — we don't want to fail-closed the BuildDialog on a
  // cost-summary fetch hiccup.
  const { costs: userCosts } = useUserCosts();
  // 300 ms debounced copy of (scope, llmModel) — prevents a burst of
  // /estimate calls on rapid toggles. React-Query keyed by the debounced
  // tuple auto-cancels stale requests on key change.
  const [debounced, setDebounced] = useState<{ scope: ExtractionJobScopeWire; llm: string }>({
    scope: openScope,
    llm: openLlm,
  });

  // Reset form every time the dialog opens. Keeps per-open defaults
  // clean even if the user leaves values behind from a prior attempt.
  useEffect(() => {
    if (!open) return;
    setScope(openScope);
    setLlmModel(openLlm);
    setMaxSpend(openMaxSpend);
    setChapterRangeFrom('');
    setChapterRangeTo('');
    setStarting(false);
    // C12 — reset wizard to Step 1 + clear target/concurrency per open.
    setWizardStep(1);
    setTargets([]);
    setConcurrency('');
    // C13 — clear the pinned-set + filters per open.
    pinning.reset();
    setDebounced({ scope: openScope, llm: openLlm });
    // `openScope` / `openLlm` / `openMaxSpend` already fold in both `project`
    // + `initialValues` — listing them directly keeps the effect's dependency
    // graph tight without introducing stale-closure risk on `initialValues`
    // swaps mid-mount. KG-EMB-PERSIST: `openEmbedding` is intentionally NOT a
    // dep here — persisting a first-time embedding selection updates
    // `project.embedding_model`, which would otherwise re-run this whole reset
    // and clobber the LLM/scope the user already chose. The embedding value is
    // reset by its own effect below.
  }, [open, openScope, openLlm, openMaxSpend]);

  // KG-EMB-PERSIST — reset/sync the embedding selection independently of the
  // form reset above, so a persisted-model refetch doesn't wipe the LLM/scope.
  useEffect(() => {
    if (open) setEmbeddingModel(openEmbedding);
  }, [open, openEmbedding]);

  // Keep `committedModel` in lockstep with the project's stored model — on open
  // and after a persist+refetch lands a fresh `project.embedding_model`.
  useEffect(() => {
    if (open) setCommittedModel(project.embedding_model ?? null);
  }, [open, project.embedding_model]);

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

  // C12a — parse chapter-range inputs. Must be declared BEFORE the
  // estimate useQuery that references it. Both-empty = full scope
  // (no filter sent). Both-set + from ≤ to = valid bounded range.
  // Any other state is invalid (partial, non-integer, negative,
  // reversed).
  const chapterRange = useMemo<
    { valid: boolean; range: [number, number] | null }
  >(() => {
    const fromTrim = chapterRangeFrom.trim();
    const toTrim = chapterRangeTo.trim();
    if (!fromTrim && !toTrim) return { valid: true, range: null };
    if (!fromTrim || !toTrim) return { valid: false, range: null };
    const f = Number(fromTrim);
    const t = Number(toTrim);
    if (
      !Number.isInteger(f) || !Number.isInteger(t) || f < 0 || t < 0 || f > t
    ) {
      return { valid: false, range: null };
    }
    return { valid: true, range: [f, t] };
  }, [chapterRangeFrom, chapterRangeTo]);
  const chapterRangeValid = scope !== 'chapters' || chapterRange.valid;

  // Auto-estimate when we have a debounced llm_model + scope.
  // C12a: queryKey also captures the resolved chapter_range so the
  // estimate refreshes as the user adjusts the range (preview honours
  // it via the T2-close-6 scope_range branch). Non-chapters scope
  // omits the range from the payload entirely.
  const estimateRangeKey =
    debounced.scope === 'chapters' && chapterRange.range
      ? chapterRange.range.join('-')
      : 'none';
  // C13 — pinned count drives the pinned-injection cost line; include it in the
  // estimate key so the preview refreshes as the user pins/unpins.
  const pinnedCount = pinning.pinnedIdList.length;
  const estimateQuery = useQuery<CostEstimate>({
    queryKey: [
      'knowledge',
      'estimate',
      project.project_id,
      debounced.scope,
      debounced.llm,
      estimateRangeKey,
      pinnedCount,
    ],
    queryFn: () => {
      const payload: EstimateExtractionPayload = {
        scope: debounced.scope,
        llm_model: debounced.llm,
        ...(debounced.scope === 'chapters' && chapterRange.range
          ? { scope_range: { chapter_range: chapterRange.range } }
          : {}),
        ...(pinnedCount > 0 ? { pinned_count: pinnedCount } : {}),
      };
      return knowledgeApi.estimateExtraction(project.project_id, payload, accessToken!);
    },
    enabled:
      open
      && !!accessToken
      && debounced.llm !== ''
      && chapterRangeValid,
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
  // C12 — concurrency: blank ⇒ omit (default). Else an integer in [1, 64]
  // (matches the BE Field(ge=1, le=64)).
  const concurrencyValid = (() => {
    if (concurrency.trim() === '') return true;
    const n = Number(concurrency);
    return Number.isInteger(n) && n >= 1 && n <= 64;
  })();
  const hasEmbedding = embeddingModel !== null && embeddingModel !== '';
  // C5: while the benchmark status is still loading for a selected embedding
  // model, we don't yet KNOW if the gate passes — treat it as not-ok so Confirm
  // can't enable-too-early (adversary focus), then settle to the real verdict.
  const benchmarkLoading = hasEmbedding && benchmarkQuery.isLoading;
  const benchmarkOk =
    !benchmarkQuery.data ||
    (benchmarkQuery.data.has_run && benchmarkQuery.data.passed);
  // C5 (KN-1/BL-16): the golden-set benchmark is a VISIBLE gate — extraction
  // stays disabled until a passing benchmark exists (the EmbeddingModelPicker
  // renders the status badge + Run-benchmark button for this same project/model).
  const llmEmpty = !modelsQuery.isLoading && (modelsQuery.data?.items?.length ?? 0) === 0;

  const canConfirm =
    !starting &&
    llmModel !== '' &&
    hasEmbedding &&
    maxSpendValid &&
    chapterRangeValid &&
    concurrencyValid &&
    !benchmarkLoading &&
    benchmarkOk;

  // C5: name the missing precondition so a disabled Confirm is never a mystery.
  const disabledReason: string | null = (() => {
    if (starting) return null;
    if (llmModel === '') return t('projects.buildDialog.disabled.pickLlm', { defaultValue: 'Pick an extraction LLM model.' });
    if (!hasEmbedding) return t('projects.buildDialog.disabled.pickEmbedding', { defaultValue: 'Pick an embedding model.' });
    if (benchmarkLoading) return t('projects.buildDialog.disabled.checkingBenchmark', { defaultValue: 'Checking the embedding benchmark…' });
    if (!benchmarkOk) return t('projects.buildDialog.disabled.benchmarkRequired', { defaultValue: 'Run the golden-set benchmark and pass it to enable extraction (above).' });
    if (!maxSpendValid) return t('projects.buildDialog.disabled.fixMaxSpend', { defaultValue: 'Enter a valid spending cap.' });
    if (!chapterRangeValid) return t('projects.buildDialog.disabled.fixRange', { defaultValue: 'Fix the chapter range.' });
    if (!concurrencyValid) return t('projects.buildDialog.disabled.fixConcurrency', { defaultValue: 'Parallel calls must be 1–64.' });
    return null;
  })();

  // KG-EMB-PERSIST — persist a FIRST-time embedding selection to the project the
  // moment it's chosen, so the benchmark-run + extract gates (which read the
  // project's STORED model, never this dropdown's local value) line up. Without
  // this, picking a model here was inert: Run-benchmark 409'd `no_embedding_model`
  // and the extract gate never cleared (bugs 2.1 + 2.2). A model SWAP on an
  // already-configured project is destructive (wipes the graph) and is refused
  // here — it belongs in ChangeModelDialog's confirmed flow.
  const handleEmbeddingChange = async (v: string | null) => {
    setEmbeddingModel(v); // keep the dropdown responsive regardless
    if (!accessToken) return;
    if (!v || v === committedModel) return; // cleared or unchanged → nothing to persist
    if (committedModel) {
      // A different model is already persisted. Switching it deletes the graph,
      // so don't do it silently — bounce back and point at the safe path.
      setEmbeddingModel(committedModel);
      toast.error(
        t('projects.buildDialog.embedding.changeViaDialog', {
          defaultValue:
            'This project already has an embedding model. Use “Change model” to switch it — that rebuilds the graph.',
        }),
      );
      return;
    }
    // First-time set on a project with no model yet → non-destructive (empty graph).
    setPersistingEmbedding(true);
    try {
      await knowledgeApi.updateEmbeddingModel(project.project_id, v, accessToken, {
        confirm: true,
      });
      setCommittedModel(v);
      await queryClient.invalidateQueries({ queryKey: ['knowledge-projects'] });
      await queryClient.invalidateQueries({
        queryKey: ['knowledge', 'benchmark-status', project.project_id],
      });
      toast.success(
        t('projects.buildDialog.embedding.saved', {
          defaultValue:
            'Embedding model saved — run the benchmark below to enable extraction.',
        }),
      );
    } catch (err) {
      setEmbeddingModel(committedModel); // revert local pick on failure
      toast.error(
        t('projects.buildDialog.embedding.saveFailed', {
          defaultValue: 'Could not save the embedding model: {{error}}',
          error: readBackendError(err),
        }),
      );
    } finally {
      setPersistingEmbedding(false);
    }
  };

  const handleConfirm = async () => {
    if (!accessToken || !embeddingModel) return;
    if (!maxSpendValid) return;
    if (!chapterRangeValid) return;
    if (!concurrencyValid) return;
    setStarting(true);
    try {
      // C12 — post the user's RAW selection (deduped/canonical), NOT the
      // entities-auto-included set: the BE/SDK add `entities` at runtime as a
      // mandatory anchor pass, and they key the recovery/filter-disable LOCK
      // off the user's EXPLICIT request. Baking `entities` in here would make a
      // relations-only build read as "entities requested" and wrongly keep
      // recovery/filter on. Empty ⇒ omit `targets` ⇒ all passes (back-compat).
      const postedTargets = canonicalTargets(targets);
      const payload: ExtractionStartPayload = {
        scope,
        llm_model: llmModel,
        embedding_model: embeddingModel,
        ...(maxSpend !== '' ? { max_spend_usd: maxSpend } : {}),
        // C12a: include chapter_range only on chapters scope + when
        // both inputs are set. Matches BE `EstimateRequest.scope_range`
        // shape — runner honours the range via D-K16.2-02b gating.
        ...(scope === 'chapters' && chapterRange.range
          ? { scope_range: { chapter_range: chapterRange.range } }
          : {}),
        // C12 — only send when a subset was actually picked.
        ...(postedTargets.length > 0 ? { targets: postedTargets } : {}),
        ...(concurrency.trim() !== ''
          ? { concurrency_level: Number(concurrency) }
          : {}),
        // C13 — pinned glossary entity ids (force-injected into every window's
        // known_entities). Only send when the user pinned at least one.
        ...(pinning.pinnedIdList.length > 0
          ? { pinned_glossary_entity_ids: pinning.pinnedIdList }
          : {}),
      };
      await knowledgeApi.startExtraction(project.project_id, payload, accessToken);
      // KN-5 (C7) — post-submit feedback: confirm the build actually
      // started. The state card also flips to "Building…" via the
      // onStarted() jobs-query invalidation, but a toast removes any
      // doubt that the click registered (the prior flow was silent).
      toast.success(t('projects.buildDialog.startSuccess'));
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
  // C12c-b: extends the filter to also hide `glossary_sync` when the
  // project has no linked book. Both scopes require book_id — BE 422s
  // on `glossary_sync + null book_id` (C12c-a MED#1), and `chapters`
  // has always required one. The single `noBookHint` below covers
  // both.
  const availableScopes = useMemo(
    () => ALL_SCOPES.filter(
      (s) => (s !== 'chapters' && s !== 'glossary_sync') || !!project.book_id,
    ),
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
          {/* C5: name the missing precondition next to a disabled Confirm. */}
          {disabledReason && (
            <span
              className="mr-auto self-center text-[11px] text-muted-foreground"
              data-testid="build-graph-disabled-reason"
            >
              {disabledReason}
            </span>
          )}
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
      {/* C12 — 3-step wizard shell. Step bodies use CSS `hidden` (not
          conditional unmount) so form/picker state survives step switches
          per the FE no-unmount rule. */}
      <BuildWizardSteps step={wizardStep} onStepChange={setWizardStep}>
        {/* ── Step 1 — scope + models + targets + concurrency ── */}
        <div
          className={`flex flex-col gap-4 ${wizardStep === 1 ? '' : 'hidden'}`}
          data-testid="build-wizard-body-1"
        >
        {/* R5 (KN-1/BL-16) — leading prerequisite checklist so the build chain
            (LLM → embedding → passing benchmark) is visible up front with a
            ✓/✗/⋯ per item, not just a disabled-Confirm reason at the bottom. */}
        <ul
          className="flex flex-col gap-1 rounded-md border border-border/60 bg-muted/30 p-2 text-[11px]"
          data-testid="build-graph-prereqs"
        >
          <PrereqRow
            ok={llmModel !== ''}
            label={t('projects.buildDialog.prereq.llm', {
              defaultValue: 'Extraction LLM model selected',
            })}
          />
          <PrereqRow
            ok={hasEmbedding}
            label={t('projects.buildDialog.prereq.embedding', {
              defaultValue: 'Embedding model selected',
            })}
          />
          <PrereqRow
            ok={!!(hasEmbedding && benchmarkOk && !benchmarkLoading)}
            pending={benchmarkLoading}
            label={
              benchmarkLoading
                ? t('projects.buildDialog.prereq.benchmarkChecking', {
                    defaultValue: 'Checking the embedding benchmark…',
                  })
                : !hasEmbedding
                  ? t('projects.buildDialog.prereq.benchmarkPending', {
                      defaultValue: 'Embedding benchmark passing (pick a model first)',
                    })
                  : benchmarkOk
                    ? t('projects.buildDialog.prereq.benchmarkPassed', {
                        defaultValue: 'Embedding benchmark passing',
                      })
                    : t('projects.buildDialog.prereq.benchmarkRequired', {
                        defaultValue:
                          'Embedding benchmark passing — run it from the model picker below',
                      })
            }
          />
        </ul>
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

        {/* C12a (D-K19a.5-04) — Chapter range picker. Only rendered
            for scope=chapters. Empty inputs = full scope (no filter
            sent). Both-set + from ≤ to = valid bounded range. BE
            runner now honours this via D-K16.2-02b handler gating. */}
        {scope === 'chapters' && (
          <fieldset
            className="flex flex-col gap-1"
            data-testid="build-graph-chapter-range"
          >
            <legend className="text-xs font-medium text-muted-foreground">
              {t('projects.buildDialog.chapterRange.label')}
            </legend>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={0}
                inputMode="numeric"
                value={chapterRangeFrom}
                onChange={(ev) => setChapterRangeFrom(ev.target.value)}
                placeholder={t('projects.buildDialog.chapterRange.from')}
                aria-label={t('projects.buildDialog.chapterRange.from')}
                className="w-24 rounded-md border bg-input px-2 py-1.5 text-sm outline-none focus:border-ring"
                data-testid="build-graph-chapter-range-from"
              />
              <span className="text-xs text-muted-foreground">—</span>
              <input
                type="number"
                min={0}
                inputMode="numeric"
                value={chapterRangeTo}
                onChange={(ev) => setChapterRangeTo(ev.target.value)}
                placeholder={t('projects.buildDialog.chapterRange.to')}
                aria-label={t('projects.buildDialog.chapterRange.to')}
                className="w-24 rounded-md border bg-input px-2 py-1.5 text-sm outline-none focus:border-ring"
                data-testid="build-graph-chapter-range-to"
              />
            </div>
            {!chapterRangeValid && (
              <span
                role="alert"
                className="text-[11px] text-destructive"
                data-testid="build-graph-chapter-range-invalid"
              >
                {t('projects.buildDialog.chapterRange.invalid')}
              </span>
            )}
            <span className="text-[11px] text-muted-foreground">
              {t('projects.buildDialog.chapterRange.hint')}
            </span>
          </fieldset>
        )}

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
            {chatModels.map((m) => {
              const label = m.alias
                ? `${m.alias} (${m.provider_model_name})`
                : `${m.provider_kind}/${m.provider_model_name}`;
              return (
                <option key={m.user_model_id} value={m.user_model_id}>
                  {label}
                </option>
              );
            })}
          </select>
          {llmEmpty && (
            // C5 (KN-1/BL-16): no chat model → in-flow AddModelCta (deep-link +
            // return), not a dead-end. Resolved from provider-registry; no literal.
            <span className="flex flex-col gap-1 text-[11px] text-muted-foreground">
              {t('projects.buildDialog.llmModel.empty')}
              <AddModelCta capability="chat" variant="link" />
            </span>
          )}
        </label>

        {/* Embedding model (reuse K12.4 picker). KG-EMB-PERSIST: persist a
            first-time selection through `handleEmbeddingChange` so benchmark +
            extract (which read the project's stored model) actually see it. */}
        <EmbeddingModelPicker
          value={embeddingModel}
          onChange={(v) => void handleEmbeddingChange(v)}
          disabled={persistingEmbedding}
          projectId={project.project_id}
        />

        {/* C12 — Step-1 target picker. Empty selection ⇒ all passes. */}
        <TargetPicker selected={targets} onChange={setTargets} />

        {/* C12 — concurrency cap (optional). */}
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('projects.buildDialog.concurrency.label')}
          </span>
          <input
            type="number"
            min={1}
            max={64}
            inputMode="numeric"
            value={concurrency}
            onChange={(e) => setConcurrency(e.target.value)}
            aria-invalid={!concurrencyValid}
            placeholder="—"
            className="w-24 rounded-md border bg-input px-2 py-1.5 text-sm outline-none focus:border-ring aria-[invalid=true]:border-destructive"
            data-testid="build-concurrency"
          />
          <span className="text-[11px] text-muted-foreground">
            {t('projects.buildDialog.concurrency.hint')}
          </span>
        </label>
        </div>

        {/* ── Step 2 — glossary pinning dual-list (C13) ── */}
        <div
          className={`flex flex-col gap-3 ${wizardStep === 2 ? '' : 'hidden'}`}
          data-testid="build-wizard-body-2"
        >
          {project.book_id ? (
            <PinningStep pinning={pinning} />
          ) : (
            <p className="rounded-md border border-dashed p-3 text-[12px] text-muted-foreground">
              {t('projects.buildDialog.pinning.noBook')}
            </p>
          )}
        </div>

        {/* ── Step 3 — budget + estimate ── */}
        <div
          className={`flex flex-col gap-4 ${wizardStep === 3 ? '' : 'hidden'}`}
          data-testid="build-wizard-body-3"
        >
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
          {/* D-K19a.5-03: surface user-wide monthly remaining so the
              user can size this job's cap against their aggregate
              budget. Hidden when no user-wide cap is set (null). */}
          {userCosts?.monthly_remaining_usd != null && (
            <span
              className="text-[11px] text-muted-foreground"
              data-testid="build-dialog-monthly-remaining"
            >
              {t('projects.buildDialog.maxSpend.monthlyRemaining', {
                amount: formatUSD(userCosts.monthly_remaining_usd),
              })}
            </span>
          )}
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
              {/* C13 — pinned-injection cost as its OWN line (the dominant
                  driver — pinned_count × ~50 × num_windows). Shown only when
                  the user pinned something. */}
              {(estimateQuery.data.estimated_pinned_tokens ?? 0) > 0 && (
                <span data-testid="estimate-pinned-line">
                  {t('projects.buildDialog.estimate.pinned', {
                    tokens: estimateQuery.data.estimated_pinned_tokens,
                    count: pinnedCount,
                  })}
                </span>
              )}
              <span className="text-muted-foreground">
                {t('projects.buildDialog.estimate.duration', {
                  seconds: estimateQuery.data.estimated_duration_seconds,
                })}
              </span>
            </div>
          )}
        </div>
        </div>
      </BuildWizardSteps>
    </FormDialog>
  );
}

/** One row of the R5 build-prerequisite checklist: ✓ (met) / ✗ (missing) /
 * ⋯ (still checking). View-only — gating stays in `canConfirm`. */
function PrereqRow({
  ok,
  pending,
  label,
}: {
  ok: boolean;
  pending?: boolean;
  label: string;
}) {
  const mark = pending ? '⋯' : ok ? '✓' : '✗';
  const color = pending
    ? 'text-muted-foreground'
    : ok
      ? 'text-green-600 dark:text-green-400'
      : 'text-destructive';
  return (
    <li className="flex items-center gap-1.5">
      <span className={`font-semibold ${color}`} aria-hidden>
        {mark}
      </span>
      <span className={ok || pending ? 'text-foreground' : 'text-muted-foreground'}>
        {label}
      </span>
    </li>
  );
}
