import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, AlertTriangle, ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { translationApi, type BookTranslationSettings, type BookCoverageResponse } from '@/features/translation/api';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { LANGUAGE_NAMES } from '@/lib/languages';
import { cn } from '@/lib/utils';
import { usePagedList } from '@/components/pagination/usePagedList';
import { Pager } from '@/components/pagination/Pager';
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
}

const PAGE_SIZE = 100;

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

export function TranslateModal({ open, onClose, bookId, onJobCreated, preselectedChapterIds }: TranslateModalProps) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [coverage, setCoverage] = useState<BookCoverageResponse | null>(null);
  const [settings, setSettings] = useState<BookTranslationSettings | null>(null);
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);

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

  const presetKey = (preselectedChapterIds ?? []).join(',');

  // Chapters in stable reading order + shared page-through pagination.
  const sortedChapters = useMemo(
    () => [...chapters].sort((a, b) => a.sort_order - b.sort_order),
    [chapters],
  );
  const { page, setPage, pageCount, start, pageItems: pageChapters } = usePagedList(sortedChapters, PAGE_SIZE);

  useEffect(() => {
    if (!open || !accessToken) return;
    setLoading(true);
    setPage(0);
    Promise.all([
      fetchAllChapters(accessToken, bookId),
      translationApi.getBookCoverage(accessToken, bookId).catch(() => null),
      translationApi.getBookSettings(accessToken, bookId).catch(() => null),
      aiModelsApi.listUserModels(accessToken).catch(() => ({ items: [] })),
    ])
      .then(([chs, cov, bkSettings, modelsResp]) => {
        setChapters(chs);
        setCoverage(cov);
        setSettings(bkSettings);
        setUserModels(modelsResp.items.filter((m) => m.is_active));
        const lang = bkSettings?.target_language || '';
        setSelectedLang(lang);
        setSelectedModelRef(bkSettings?.model_ref || '');
        // Default selection: caller-scoped chapters (per-chapter re-translate) when
        // given, else everything that needs translation for the default language.
        const preset = preselectedChapterIds?.filter((id) => chs.some((c) => c.chapter_id === id));
        if (preset && preset.length > 0) {
          setSelectedChapters(new Set(preset));
        } else {
          const cells = coverageMapFor(cov, lang);
          const { byId } = classifyChapters(chs.map((c) => c.chapter_id), cells);
          setSelectedChapters(new Set(needsIds(byId)));
        }
        // Reset the advanced overrides each time the modal opens — it stays mounted
        // (rendered with an `open` prop), so without this a one-off force-retranslate
        // or verifier choice would silently carry into the next, unrelated translate.
        setAdvancedOpen(false);
        setVerifyEnabled(false);
        setVerifierModelRef('');
        setQaDepth('standard');
        setMaxQaRounds(2);
        setForceRetranslate(false);
      })
      .catch((e) => toast.error((e as Error).message))
      .finally(() => setLoading(false));
    // presetKey (not the array identity) gates re-runs so an inline `[chapterId]`
    // prop doesn't trigger a refetch loop while the modal is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, accessToken, bookId, presetKey]);

  // Per-chapter status + aggregate counts for the selected language.
  const { byId: statusById, counts } = useMemo(() => {
    const cells = coverageMapFor(coverage, selectedLang);
    return classifyChapters(sortedChapters.map((c) => c.chapter_id), cells);
  }, [coverage, selectedLang, sortedChapters]);

  const neededIds = useMemo(() => needsIds(statusById), [statusById]);

  // Group models by provider
  const modelsByProvider = useMemo(() => {
    const map = new Map<string, UserModel[]>();
    for (const m of userModels) {
      const key = m.provider_kind;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(m);
    }
    return map;
  }, [userModels]);

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

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-lg border bg-background shadow-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="border-b px-5 py-4">
            <h2 className="text-sm font-semibold">{t('translate.title')}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">{t('translate.subtitle')}</p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              <span className="ml-2 text-xs text-muted-foreground">{t('translate.loading_chapters')}</span>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
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
                  {userModels.length === 0 ? (
                    <div className="flex h-9 items-center rounded-md border border-dashed bg-background px-3 text-[11px] text-muted-foreground">
                      {t('translate.no_models')}{' '}
                      <Link to="/settings" onClick={onClose} className="ml-1 text-primary hover:underline">
                        {t('translate.add_in_settings')}
                      </Link>
                    </div>
                  ) : (
                    <select
                      value={selectedModelRef}
                      onChange={(e) => handleModelChange(e.target.value)}
                      className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                    >
                      <option value="">{t('translate.select_model')}</option>
                      {Array.from(modelsByProvider.entries()).map(([provider, models]) => (
                        <optgroup key={provider} label={provider}>
                          {models.map((m) => (
                            <option key={m.user_model_id} value={m.user_model_id}>
                              {m.alias || m.provider_model_name}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  )}
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
                          <select
                            value={verifierModelRef}
                            onChange={(e) => setVerifierModelRef(e.target.value)}
                            className="h-8 w-full rounded-md border bg-background px-2 text-[12px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                          >
                            <option value="">{t('translate.verifier_default')}</option>
                            {Array.from(modelsByProvider.entries()).map(([provider, models]) => (
                              <optgroup key={provider} label={provider}>
                                {models.map((m) => (
                                  <option key={m.user_model_id} value={m.user_model_id}>
                                    {m.alias || m.provider_model_name}
                                  </option>
                                ))}
                              </optgroup>
                            ))}
                          </select>
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
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-end gap-2 border-t px-5 py-3">
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
          </div>
        </div>
      </div>
    </>
  );
}
