import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, AlertTriangle, ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { translationApi, type BookTranslationSettings, type BookCoverageResponse } from '@/features/translation/api';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { LANGUAGE_NAMES } from '@/lib/languages';
import { cn } from '@/lib/utils';
import { usePagedList } from '@/components/pagination/usePagedList';
import { Pager } from '@/components/pagination/Pager';
import { withTimeout } from '@/features/translation/lib/translationError';
import { TranslationErrorState } from '@/features/translation/components/TranslationErrorState';
import { FormDialog } from '@/components/shared/FormDialog';
import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';
import {
  classifyChapters,
  coverageMapFor,
  needsIds,
  type ChapterTxStatus,
} from '@/features/translation/lib/coverageClassify';

interface TranslateModalProps {
  open: boolean;
  onClose: () => void;
  bookId: string;
  onJobCreated: () => void;
  // When provided, the chapter list defaults to exactly these chapters (used by the
  // per-chapter version page's "re-translate" action) instead of "everything that
  // needs it".
  preselectedChapterIds?: string[];
  // T8/D6: when the matrix opens the modal from a language column, seed that language so
  // "Select affected → Translate Selected" targets the column the user was looking at,
  // instead of falling back to the book default.
  preselectedLang?: string;
}

const PAGE_SIZE = 100;
// T5: a hanging translation-service must not wedge the checklist forever — recover after this.
const CHAPTERS_TIMEOUT_MS = 15000;

// Fetch every active chapter, paging past the backend's 100-row cap so a 2000+
// chapter book is fully classified (not silently truncated to one page).
async function fetchAllChapters(token: string, bookId: string): Promise<Chapter[]> {
  const all: Chapter[] = [];
  let offset = 0;
  for (;;) {
    const resp = await booksApi.listChapters(token, bookId, {
      lifecycle_state: 'active',
      limit: PAGE_SIZE,
      offset,
    });
    all.push(...resp.items);
    // Stop on a short page, or once we've pulled the reported total. Fall back to
    // Infinity (not all.length) when total is absent so a missing count never
    // short-circuits the loop to a single page on a large book.
    if (resp.items.length < PAGE_SIZE || all.length >= (resp.total ?? Infinity)) break;
    offset += PAGE_SIZE;
  }
  return all;
}

const STATUS_BADGE: Record<ChapterTxStatus, string> = {
  untranslated: 'bg-muted text-muted-foreground',
  translated: 'bg-emerald-500/10 text-emerald-500',
  stale: 'bg-amber-500/10 text-amber-500',
  failed: 'bg-red-500/10 text-red-500',
  running: 'bg-sky-500/10 text-sky-500',
};

export function TranslateModal({ open, onClose, bookId, onJobCreated, preselectedChapterIds, preselectedLang }: TranslateModalProps) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  // DOCK-7 — reachable both from the classic TranslationTab/ChaptersTab route pages AND from
  // inside the studio's `translation`/`chapter-browser` dock panels (this modal is already
  // reused in-studio today). A bare navigate('/settings') would tear down the whole studio (and
  // every other open dock tab) just to add a model — branch like ExtractionWizard's handleClose.
  const studioHost = useOptionalStudioHost();
  const openModelSettings = () => {
    onClose();
    if (studioHost) studioHost.openPanel('settings', { params: { tab: 'providers' } });
    else navigate('/settings');
  };
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [coverage, setCoverage] = useState<BookCoverageResponse | null>(null);
  const [settings, setSettings] = useState<BookTranslationSettings | null>(null);
  // T5: only the chapter checklist is network-bound — the pickers render immediately. This
  // state scopes loading/error to that region so a slow/dead service can't wedge the whole modal.
  const [chaptersLoading, setChaptersLoading] = useState(true);
  const [chaptersError, setChaptersError] = useState<unknown>(null);
  // True once the fast metadata (coverage + settings + language seed) has settled, so the
  // default-selection effect below doesn't race the chapter list and seed "all" before it
  // knows which chapters are already translated.
  const [metaReady, setMetaReady] = useState(false);
  const seededRef = useRef(false);           // D7: seed pickers once, never clobber a user choice
  const seededSelectionRef = useRef(false);  // seed the default chapter selection once per open

  // Shared model fetch (W5) — translation drives an LLM, so chat capability.
  // Active-only is the shared hook's default; fetch only while the modal is open.
  const { models } = useUserModels({ capability: 'chat', enabled: open });
  const userModels = models ?? [];

  const [selectedChapters, setSelectedChapters] = useState<Set<string>>(new Set());
  const [selectedLang, setSelectedLang] = useState('');
  const [selectedModelRef, setSelectedModelRef] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Quality verification (V3) + re-translate controls
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [verifyEnabled, setVerifyEnabled] = useState(false);
  const [verifierModelRef, setVerifierModelRef] = useState('');
  const [qaDepth, setQaDepth] = useState<'rule_only' | 'standard' | 'thorough'>('standard');
  const [maxQaRounds, setMaxQaRounds] = useState(2);
  const [forceRetranslate, setForceRetranslate] = useState(false);
  // Enable model reasoning (thinking) for the translation LLM. Default OFF.
  const [thinkingEnabled, setThinkingEnabled] = useState(false);

  const presetKey = (preselectedChapterIds ?? []).join(',');

  // Chapters in stable reading order + shared page-through pagination.
  const sortedChapters = useMemo(
    () => [...chapters].sort((a, b) => a.sort_order - b.sort_order),
    [chapters],
  );
  const { page, setPage, pageCount, start, pageItems: pageChapters } = usePagedList(sortedChapters, PAGE_SIZE);

  // T5/D8: the chapter checklist is the ONLY network-bound region. Timed so a *hanging*
  // dependency (not just a rejecting one) recovers into an inline error + Retry instead of a
  // permanent "Loading chapters…" wedge. Retry re-runs exactly this.
  const loadChapters = useCallback(() => {
    if (!accessToken) return;
    setChaptersError(null);
    setChaptersLoading(true);
    withTimeout(fetchAllChapters(accessToken, bookId), CHAPTERS_TIMEOUT_MS)
      .then((chs) => setChapters(chs))
      .catch((e) => setChaptersError(e))
      .finally(() => setChaptersLoading(false));
  }, [accessToken, bookId]);

  useEffect(() => {
    if (!open || !accessToken) return;
    seededRef.current = false;
    seededSelectionRef.current = false;
    setMetaReady(false);
    setPage(0);
    // Reset the advanced overrides for this open — the component stays mounted (rendered with
    // an `open` prop), so without this a one-off force-retranslate/verifier choice would carry
    // into the next, unrelated translate.
    setAdvancedOpen(false);
    setVerifyEnabled(false);
    setVerifierModelRef('');
    setQaDepth('standard');
    setMaxQaRounds(2);
    setForceRetranslate(false);
    setThinkingEnabled(false);
    // D6: the caller-pinned language applies immediately (settings fills the rest below).
    setSelectedLang(preselectedLang || '');
    setSelectedModelRef('');
    // D8: seed the selection from the caller-pinned ids immediately — the ids are already known,
    // so submit works even if the chapter list below fails or hangs.
    if (preselectedChapterIds && preselectedChapterIds.length > 0) {
      setSelectedChapters(new Set(preselectedChapterIds));
      seededSelectionRef.current = true;
    } else {
      setSelectedChapters(new Set());
    }

    // Fast metadata — coverage + settings need no big fetch, so the pickers render without
    // waiting on the chapter list (T5). Seed lang/model ONCE, and never clobber a value the
    // user picked meanwhile (D7 — functional set keeps a non-empty prev).
    let cancelled = false;
    Promise.all([
      translationApi.getBookCoverage(accessToken, bookId).catch(() => null),
      translationApi.getBookSettings(accessToken, bookId).catch(() => null),
    ]).then(([cov, bkSettings]) => {
      if (cancelled) return;
      setCoverage(cov);
      setSettings(bkSettings);
      if (!seededRef.current) {
        seededRef.current = true;
        setSelectedLang((prev) => prev || preselectedLang || bkSettings?.target_language || '');
        setSelectedModelRef((prev) => prev || bkSettings?.model_ref || '');
      }
      setMetaReady(true);
    });

    loadChapters();
    return () => { cancelled = true; };
    // presetKey (not the array identity) gates re-runs so an inline `[chapterId]` prop doesn't
    // trigger a refetch loop while the modal is open. loadChapters is stable per (token,bookId).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, accessToken, bookId, presetKey]);

  // Default chapter selection = "everything that needs work" for the current language, seeded
  // ONCE per open and only when the caller did not pin a selection (keeps the user in control).
  useEffect(() => {
    if (!open || seededSelectionRef.current || chapters.length === 0 || !metaReady) return;
    const cells = coverageMapFor(coverage, selectedLang);
    const { byId } = classifyChapters(chapters.map((c) => c.chapter_id), cells);
    setSelectedChapters(new Set(needsIds(byId)));
    seededSelectionRef.current = true;
  }, [open, chapters, coverage, selectedLang, metaReady]);

  // Per-chapter status + aggregate counts for the selected language.
  const { byId: statusById, counts } = useMemo(() => {
    const cells = coverageMapFor(coverage, selectedLang);
    return classifyChapters(sortedChapters.map((c) => c.chapter_id), cells);
  }, [coverage, selectedLang, sortedChapters]);

  const neededIds = useMemo(() => needsIds(statusById), [statusById]);

  const toggleChapter = (id: string) => {
    setSelectedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Quick-select: replace selection with every chapter of a status group (or all/none).
  const selectByStatus = (status: ChapterTxStatus | 'all' | 'none' | 'needs') => {
    if (status === 'none') return setSelectedChapters(new Set());
    if (status === 'all') return setSelectedChapters(new Set(sortedChapters.map((c) => c.chapter_id)));
    if (status === 'needs') return setSelectedChapters(new Set(neededIds));
    const ids = sortedChapters.map((c) => c.chapter_id).filter((id) => statusById.get(id) === status);
    setSelectedChapters(new Set(ids));
  };

  const handleSaveSettings = async (lang: string, modelRef: string) => {
    if (!accessToken) return;
    try {
      // PATCH: send only the fields we're changing. The backend keeps every omitted
      // field at its stored value (atomic COALESCE upsert), so this never clobbers
      // custom prompts and we don't echo back the whole settings object.
      const payload: Record<string, unknown> = { model_source: 'user_model' };
      if (lang) payload.target_language = lang;
      if (modelRef) payload.model_ref = modelRef;
      const updated = await translationApi.putBookSettings(accessToken, bookId, payload);
      setSettings(updated);
    } catch (e) {
      // Persisting the book default is best-effort (the job carries its own overrides),
      // but surface the failure instead of swallowing it.
      toast.error(t('translate.settings_save_failed', { error: (e as Error).message }));
    }
  };

  const handleLangChange = (lang: string) => {
    setSelectedLang(lang);
    // Re-target the default selection to the chapters that need work in the new
    // language (unless the caller pinned a specific set via preselectedChapterIds).
    if (!(preselectedChapterIds && preselectedChapterIds.length > 0)) {
      const cells = coverageMapFor(coverage, lang);
      const { byId } = classifyChapters(sortedChapters.map((c) => c.chapter_id), cells);
      setSelectedChapters(new Set(needsIds(byId)));
    }
    void handleSaveSettings(lang, selectedModelRef);
  };

  const handleModelChange = (modelRef: string) => {
    setSelectedModelRef(modelRef);
    void handleSaveSettings(selectedLang, modelRef);
  };

  const submitJob = async (chapterIds: string[], force: boolean) => {
    if (!accessToken || !selectedLang || !selectedModelRef || chapterIds.length === 0 || submitting) return;
    setSubmitting(true);
    try {
      await translationApi.createJob(accessToken, bookId, {
        chapter_ids: chapterIds,
        // Fix-C: pass the selection directly so the job succeeds even if the
        // best-effort settings save above failed.
        target_language: selectedLang,
        model_source: 'user_model',
        model_ref: selectedModelRef,
        // Quality verification: the verify→correct loop only runs in pipeline v3,
        // so opting in forces v3 + carries the QA config. The verifier model is
        // optional (falls back to the translator when omitted).
        ...(verifyEnabled
          ? {
              pipeline_version: 'v3' as const,
              qa_depth: qaDepth,
              max_qa_rounds: maxQaRounds,
              ...(verifierModelRef
                ? { verifier_model_source: 'user_model', verifier_model_ref: verifierModelRef }
                : {}),
            }
          : {}),
        force_retranslate: force,
        // D-TRANSLATE-REASONING-TOGGLE — per-job reasoning enable/disable.
        thinking_enabled: thinkingEnabled,
      });
      toast.success(t('translate.job_started', { count: chapterIds.length }));
      onJobCreated();
      onClose();
    } catch (e) {
      const err = e as Error & { code?: string };
      if (err.code === 'TRANSL_NO_MODEL_CONFIGURED') {
        toast.error(t('translate.no_model_configured'));
      } else {
        toast.error(err.message || t('translate.failed'));
      }
    }
    setSubmitting(false);
  };

  if (!open) return null;

  const availableLangs = Object.entries(LANGUAGE_NAMES);
  const selectedModel = userModels.find((m) => m.user_model_id === selectedModelRef);
  const configReady = !!selectedLang && !!selectedModelRef;
  const canSubmitSelected = configReady && selectedChapters.size > 0 && !submitting;
  const canSubmitNeeded = configReady && neededIds.length > 0 && !submitting;

  const STATUS_KEYS: { status: ChapterTxStatus; count: number }[] = [
    { status: 'untranslated', count: counts.untranslated },
    { status: 'stale', count: counts.stale },
    { status: 'failed', count: counts.failed },
    { status: 'running', count: counts.running },
    { status: 'translated', count: counts.translated },
  ];

  const footer = (
    <>
      <button
        onClick={onClose}
        className="rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
      >
        {t('translate.cancel')}
      </button>
      <button
        onClick={() => void submitJob([...selectedChapters], forceRetranslate)}
        disabled={!canSubmitSelected}
        className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {t('translate.submit_selected', { count: selectedChapters.size })}
      </button>
    </>
  );

  // DOCK-9 (docs/standards/dockable-gui.md): FormDialog replaces the previous hand-rolled
  // `fixed inset-0` backdrop+content pair — this is a chrome-only migration, all existing
  // behavior/props are preserved. `open` is passed as the literal `true` here (we've already
  // early-returned above when the prop is false), same as ExtractionWizard's Dialog.Root.
  return (
    <FormDialog
      open
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={t('translate.title')}
      description={t('translate.subtitle')}
      size="2xl"
      footer={footer}
    >
        <div className="space-y-4">
          {/* Language + Model row */}
              <div className="grid grid-cols-2 gap-3">
                {/* Language */}
                <div>
                  <label className="mb-1 block text-xs font-medium">{t('translate.target_language')}</label>
                  <select
                    value={selectedLang}
                    onChange={(e) => handleLangChange(e.target.value)}
                    className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                  >
                    <option value="">{t('translate.select_language')}</option>
                    {availableLangs.map(([code, name]) => (
                      <option key={code} value={code}>{name} ({code})</option>
                    ))}
                  </select>
                </div>

                {/* Model */}
                <div>
                  <label className="mb-1 block text-xs font-medium">{t('translate.model')}</label>
                  <ModelPicker
                    capability="chat"
                    value={selectedModelRef || null}
                    onChange={(id) => handleModelChange(id ?? '')}
                    placeholder={t('translate.select_model')}
                    ariaLabel={t('translate.model')}
                    emptyState={
                      <div className="flex h-9 items-center rounded-md border border-dashed bg-background px-3 text-[11px] text-muted-foreground">
                        {t('translate.no_models')}{' '}
                        <button
                          type="button"
                          onClick={openModelSettings}
                          className="ml-1 text-primary hover:underline"
                        >
                          {t('translate.add_in_settings')}
                        </button>
                      </div>
                    }
                  />
                </div>
              </div>

              {/* Model info */}
              {selectedModel && (
                <p className="text-[10px] text-muted-foreground -mt-2">
                  {selectedModel.provider_kind} — <span className="font-mono">{selectedModel.provider_model_name}</span>
                </p>
              )}

              {/* Warning: missing config */}
              {!configReady && (
                <div className="flex items-center gap-2 rounded-md border border-amber-400/20 bg-amber-400/5 px-3 py-2">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                  <p className="text-[11px] text-amber-400">
                    {!selectedLang && !selectedModelRef
                      ? t('translate.warn_both')
                      : !selectedLang
                        ? t('translate.warn_language')
                        : t('translate.warn_model')}
                  </p>
                </div>
              )}

              {/* Summary + primary "translate what needs it" action */}
              {selectedLang && (
                <div className="rounded-md border bg-card/40 px-3 py-3">
                  <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
                    <span className="font-medium">{t('translate.summary_total', { count: counts.total })}</span>
                    {STATUS_KEYS.filter((s) => s.count > 0).map((s) => (
                      <span key={s.status} className="inline-flex items-center gap-1">
                        <span className={cn('h-1.5 w-1.5 rounded-full', STATUS_BADGE[s.status].split(' ')[0])} />
                        {t(`translate.status_${s.status}`)}: {s.count}
                      </span>
                    ))}
                  </div>
                  {neededIds.length > 0 ? (
                    <button
                      onClick={() => void submitJob(neededIds, false)}
                      disabled={!canSubmitNeeded}
                      className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      {t('translate.translate_needed', { count: neededIds.length })}
                    </button>
                  ) : (
                    // Everything is already translated — the primary "translate needed"
                    // CTA is gone, which left re-translation a dead-end (buried behind
                    // Advanced → Force). Offer a direct force-retranslate of the SELECTED
                    // chapters (the per-chapter page preselects this chapter) so making a
                    // fresh translation is always one click, not a hunt.
                    <div className="space-y-1.5">
                      <p className="text-[11px] text-emerald-500">{t('translate.needs_none')}</p>
                      <button
                        onClick={() => void submitJob([...selectedChapters], true)}
                        disabled={!configReady || selectedChapters.size === 0 || submitting}
                        className="inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-primary/40 bg-primary/5 px-4 py-2 text-xs font-medium text-primary hover:bg-primary/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        data-testid="translate-retranslate-selected"
                      >
                        {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        {t('translate.retranslate_selected', {
                          count: selectedChapters.size,
                          defaultValue: 'Re-translate selected ({{count}})',
                        })}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Advanced: quality verification (V3) + re-translate */}
              <div className="rounded-md border">
                <button
                  type="button"
                  onClick={() => setAdvancedOpen((o) => !o)}
                  className="flex w-full items-center gap-1.5 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {advancedOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  {t('translate.advanced')}
                </button>
                {advancedOpen && (
                  <div className="space-y-3 border-t px-3 py-3">
                    {/* Verify toggle */}
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={verifyEnabled}
                        onChange={(e) => setVerifyEnabled(e.target.checked)}
                        className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-primary"
                      />
                      <span className="flex flex-col gap-0.5">
                        <span className="inline-flex items-center gap-1 text-xs font-medium">
                          <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                          {t('translate.verify_enable')}
                        </span>
                        <span className="text-[10px] text-muted-foreground">{t('translate.verify_hint')}</span>
                      </span>
                    </label>

                    {verifyEnabled && (
                      <div className="space-y-3 border-l-2 border-border pl-3">
                        {/* Verifier model */}
                        <div>
                          <label className="mb-1 block text-[11px] font-medium">{t('translate.verifier_model')}</label>
                          <ModelPicker
                            capability="chat"
                            value={verifierModelRef || null}
                            onChange={(id) => setVerifierModelRef(id ?? '')}
                            allowNone
                            noneLabel={t('translate.verifier_default')}
                            ariaLabel={t('translate.verifier_model')}
                            compact
                          />
                        </div>
                        {/* QA depth + rounds */}
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="mb-1 block text-[11px] font-medium">{t('translate.qa_depth')}</label>
                            <select
                              value={qaDepth}
                              onChange={(e) => setQaDepth(e.target.value as typeof qaDepth)}
                              className="h-8 w-full rounded-md border bg-background px-2 text-[12px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                            >
                              <option value="rule_only">{t('translate.qa_depth_rule_only')}</option>
                              <option value="standard">{t('translate.qa_depth_standard')}</option>
                              <option value="thorough">{t('translate.qa_depth_thorough')}</option>
                            </select>
                          </div>
                          <div>
                            <label className="mb-1 block text-[11px] font-medium">{t('translate.qa_rounds')}</label>
                            <input
                              type="number"
                              min={1}
                              max={5}
                              value={maxQaRounds}
                              onChange={(e) => setMaxQaRounds(Math.min(5, Math.max(1, Number(e.target.value) || 1)))}
                              className="h-8 w-full rounded-md border bg-background px-2 text-[12px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                            />
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Force re-translate */}
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={forceRetranslate}
                        onChange={(e) => setForceRetranslate(e.target.checked)}
                        className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-primary"
                      />
                      <span className="flex flex-col gap-0.5">
                        <span className="text-xs font-medium">{t('translate.force_retranslate')}</span>
                        <span className="text-[10px] text-muted-foreground">{t('translate.force_retranslate_hint')}</span>
                      </span>
                    </label>

                    {/* Enable model reasoning (thinking) — default OFF. */}
                    <label className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={thinkingEnabled}
                        onChange={(e) => setThinkingEnabled(e.target.checked)}
                        className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-primary"
                        data-testid="translate-thinking-toggle"
                      />
                      <span className="flex flex-col gap-0.5">
                        <span className="text-xs font-medium">
                          {t('translate.reasoning_enable', { defaultValue: 'Enable model reasoning (thinking)' })}
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          {t('translate.reasoning_hint', {
                            defaultValue:
                              'Off by default — hidden thinking can burn the output budget on local models. Enable for hard passages on a reasoning model.',
                          })}
                        </span>
                      </span>
                    </label>
                  </div>
                )}
              </div>

              {/* Chapter selection */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-xs font-medium text-muted-foreground">
                    {t('translate.chapters', { selected: selectedChapters.size, total: sortedChapters.length })}
                  </label>
                </div>
                {chaptersLoading ? (
                  <div className="flex items-center justify-center py-8" data-testid="translate-chapters-loading">
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    <span className="ml-2 text-xs text-muted-foreground">{t('translate.loading_chapters')}</span>
                  </div>
                ) : chaptersError ? (
                  // T5/D9: a rejecting OR hanging chapter fetch recovers here with a typed
                  // message + Retry, scoped to the checklist — the pickers above stay usable, and
                  // if a selection was preselected the footer submit stays enabled (D8).
                  <TranslationErrorState compact error={chaptersError} onRetry={loadChapters} />
                ) : (
                  <>
                {/* Quick-select chips */}
                <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                  <span className="text-muted-foreground">{t('translate.quick_label')}</span>
                  <button onClick={() => selectByStatus('needs')} className="rounded-full border px-2 py-0.5 hover:bg-secondary">
                    {t('translate.chip_needs')} ({neededIds.length})
                  </button>
                  <button onClick={() => selectByStatus('untranslated')} className="rounded-full border px-2 py-0.5 hover:bg-secondary">
                    {t('translate.status_untranslated')} ({counts.untranslated})
                  </button>
                  <button onClick={() => selectByStatus('stale')} className="rounded-full border px-2 py-0.5 hover:bg-secondary">
                    {t('translate.status_stale')} ({counts.stale})
                  </button>
                  <button onClick={() => selectByStatus('failed')} className="rounded-full border px-2 py-0.5 hover:bg-secondary">
                    {t('translate.status_failed')} ({counts.failed})
                  </button>
                  <button onClick={() => selectByStatus('all')} className="rounded-full border px-2 py-0.5 hover:bg-secondary">
                    {t('translate.chip_all')}
                  </button>
                  <button onClick={() => selectByStatus('none')} className="rounded-full border px-2 py-0.5 hover:bg-secondary">
                    {t('translate.chip_none')}
                  </button>
                </div>
                <div className="max-h-48 overflow-y-auto rounded-md border">
                  {pageChapters.map((ch, i) => {
                    const status = statusById.get(ch.chapter_id) ?? 'untranslated';
                    return (
                      <label
                        key={ch.chapter_id}
                        className={cn(
                          'flex items-center gap-3 px-3 py-2 text-xs cursor-pointer hover:bg-card transition-colors',
                          i < pageChapters.length - 1 && 'border-b',
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={selectedChapters.has(ch.chapter_id)}
                          onChange={() => toggleChapter(ch.chapter_id)}
                          className="h-3.5 w-3.5 rounded border-border accent-primary"
                        />
                        <span className="w-8 text-right font-mono text-muted-foreground">
                          {start + i + 1}
                        </span>
                        <span className="flex-1 line-clamp-1">
                          {ch.title || ch.original_filename || t('translate.untitled')}
                        </span>
                        <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium', STATUS_BADGE[status])}>
                          {t(`translate.status_${status}`)}
                        </span>
                      </label>
                    );
                  })}
                </div>
                <Pager
                  page={page}
                  pageCount={pageCount}
                  onPageChange={setPage}
                  className="mt-2 justify-center"
                  labels={{ page: t('translate.page'), prev: t('translate.prev'), next: t('translate.next') }}
                />
                  </>
                )}
              </div>
            </div>
    </FormDialog>
  );
}
