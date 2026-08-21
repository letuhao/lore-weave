import { useCallback, useEffect, useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, CheckCircle2, FileText, Loader2, RotateCcw, Upload, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import {
  booksApi,
  type EpubImportInspection,
  type EpubImportJob,
  type EpubImportReport,
  type EpubNavigationNode,
} from '@/features/books/api';

type Step = 'upload' | 'metadata' | 'chapters' | 'confirm' | 'progress' | 'report';
const STEPS: Step[] = ['upload', 'metadata', 'chapters', 'confirm', 'progress', 'report'];

interface EpubImportWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookId: string;
  onImported: () => void;
}

/**
 * EPUB V2 flow. It deliberately has no client-side deadline: the durable Book
 * job is authoritative and users can safely close this modal while it runs.
 */
export function EpubImportWizard({ open, onOpenChange, bookId, onImported }: EpubImportWizardProps) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [inspection, setInspection] = useState<EpubImportInspection | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [targetMode, setTargetMode] = useState<'existing_book' | 'new_book'>('existing_book');
  const [strategy, setStrategy] = useState<'append' | 'replace_all' | 'merge_by_source_key'>('append');
  const [metadataPolicy, setMetadataPolicy] = useState<Record<string, string>>({ title: 'keep_existing', description: 'keep_existing', language: 'keep_existing', subjects: 'merge' });
  const [useCover, setUseCover] = useState(true);
  const [importImages, setImportImages] = useState(true);
  const [importFootnotes, setImportFootnotes] = useState(true);
  const [preserveHierarchy, setPreserveHierarchy] = useState(true);
  const [retainSource, setRetainSource] = useState(true);
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const [job, setJob] = useState<EpubImportJob | null>(null);
  const [report, setReport] = useState<EpubImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setStep('upload'); setFile(null); setInspection(null); setSelected(new Set()); setTitles({});
    setTargetMode('existing_book'); setStrategy('append'); setMetadataPolicy({ title: 'keep_existing', description: 'keep_existing', language: 'keep_existing', subjects: 'merge' }); setUseCover(true); setImportImages(true); setImportFootnotes(true); setPreserveHierarchy(true); setRetainSource(true); setReplaceConfirmed(false); setJob(null); setReport(null);
    setBusy(false); setUploadPct(0); setError(null);
  }, []);

  useEffect(() => { if (open) reset(); }, [open, reset]);

  useEffect(() => {
    if (!open || !accessToken) return;
    const jobID = window.localStorage.getItem(`loreweave:epub-import-job:${bookId}`);
    if (!jobID) return;
    let cancelled = false;
    const restore = async () => {
      try {
        const restored = await booksApi.getEpubImportJob(accessToken, jobID);
        if (cancelled) return;
        setJob(restored);
        if (['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(restored.status)) {
          const restoredReport = await booksApi.getEpubImportReport(accessToken, jobID).catch(() => null);
          if (cancelled) return;
          setReport(restoredReport);
          setStep('report');
        } else {
          setStep('progress');
        }
      } catch (restoreError) {
        if (!cancelled) setError((restoreError as Error).message);
      }
    };
    void restore();
    return () => { cancelled = true; };
  }, [accessToken, bookId, open]);

  useEffect(() => {
    if (!accessToken || !job || !['queued', 'running', 'import_staging', 'cancelling'].includes(job.status)) return;
    const poll = async () => {
      try {
        const updated = await booksApi.getEpubImportJob(accessToken, job.job_id);
        setJob(updated);
        if (['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(updated.status)) {
          const nextReport = await booksApi.getEpubImportReport(accessToken, updated.job_id).catch(() => null);
          setReport(nextReport);
          setStep('report');
          if (updated.status.startsWith('completed')) onImported();
        }
      } catch (pollError) { setError((pollError as Error).message); }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 4000);
    return () => window.clearInterval(timer);
  }, [accessToken, job?.job_id, job?.status, onImported]);

  const leaves = useMemo(() => collectContentLeaves(inspection?.structure ?? []), [inspection]);
  const currentIndex = STEPS.indexOf(step);

  const inspect = async (nextFile: File) => {
    if (!accessToken) return;
    if (!nextFile.name.toLowerCase().endsWith('.epub')) { setError(t('epubImport.errors.extension')); return; }
    setFile(nextFile); setBusy(true); setError(null); setUploadPct(0);
    try {
      const result = await booksApi.inspectEpub(accessToken, nextFile, bookId, setUploadPct);
      setInspection(result);
      setSelected(new Set(collectContentLeaves(result.structure).filter((node) => node.selected).map((node) => node.source_key)));
      setStep('metadata');
    } catch (inspectError) { setError((inspectError as Error).message); }
    finally { setBusy(false); }
  };

  const beginImport = async () => {
    if (!accessToken || !inspection || selected.size === 0) return;
    setBusy(true); setError(null);
    try {
      const created = await booksApi.startEpubImport(accessToken, {
        source_id: inspection.source_id,
        target: targetMode === 'new_book' ? { mode: 'new_book' } : { mode: 'existing_book', book_id: bookId },
        strategy,
        metadata_policy: { ...metadataPolicy, title: targetMode === 'new_book' ? 'use_source' : metadataPolicy.title, cover: useCover ? 'use_source' : 'keep_existing' },
        selected_source_keys: [...selected],
        title_overrides: titles,
        options: { preserve_hierarchy: preserveHierarchy, import_images: importImages, import_footnotes: importFootnotes, retain_source: retainSource },
        destructive_confirmation: strategy !== 'replace_all' || replaceConfirmed,
      });
      window.localStorage.setItem(`loreweave:epub-import-job:${bookId}`, created.job_id);
      setJob({ job_id: created.job_id, book_id: created.book_id, source_id: inspection.source_id, status: created.status, progress_total: selected.size, progress_completed: 0, progress_failed: 0, chapters_created: 0, warnings: [], errors: [], resumable: false, cancellable: true, rollback_available: false });
      setStep('progress');
    } catch (startError) { setError((startError as Error).message); }
    finally { setBusy(false); }
  };

  const updateJob = async (action: 'cancel' | 'resume' | 'rollback') => {
    if (!accessToken || !job) return;
    setBusy(true); setError(null);
    try {
      if (action === 'cancel') await booksApi.cancelEpubImport(accessToken, job.job_id);
      if (action === 'resume') await booksApi.resumeEpubImport(accessToken, job.job_id);
      if (action === 'rollback') await booksApi.rollbackEpubImport(accessToken, job.job_id);
      setJob(await booksApi.getEpubImportJob(accessToken, job.job_id));
    } catch (actionError) { setError((actionError as Error).message); }
    finally { setBusy(false); }
  };

  if (!open) return null;
  return <Dialog.Root open onOpenChange={(next) => onOpenChange(next)}><Dialog.Portal>
    <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
    <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border bg-background shadow-xl">
      <header className="flex items-center justify-between border-b px-5 py-3"><div><Dialog.Title className="text-sm font-semibold">{t('epubImport.title')}</Dialog.Title><Dialog.Description className="text-xs text-muted-foreground">{t('epubImport.description')}</Dialog.Description></div><button aria-label={t('epubImport.close')} onClick={() => onOpenChange(false)} className="rounded p-1 hover:bg-secondary"><X className="h-4 w-4" /></button></header>
      <div className="flex gap-1 overflow-x-auto border-b px-4 py-2">{STEPS.map((item, index) => <span key={item} className={`whitespace-nowrap rounded px-2 py-1 text-[11px] ${index === currentIndex ? 'bg-primary/10 text-primary' : index < currentIndex ? 'text-muted-foreground' : 'text-muted-foreground/50'}`}>{index + 1}. {t(`epubImport.steps.${item}`)}</span>)}</div>
      <main className="min-h-0 flex-1 overflow-y-auto p-5">{error && <div className="mb-4 flex gap-2 rounded border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}
        {step === 'upload' && <label className="flex cursor-pointer flex-col items-center gap-3 rounded-lg border-2 border-dashed p-10 text-center hover:bg-secondary/40"><Upload className="h-7 w-7 text-muted-foreground" /><span className="text-sm font-medium">{file?.name ?? t('epubImport.chooseFile')}</span><span className="text-xs text-muted-foreground">{t('epubImport.fileHint')}</span><input data-testid="epub-import-file-input" className="hidden" type="file" accept=".epub" onChange={(event) => { const next = event.target.files?.[0]; if (next) void inspect(next); }} />{busy && <span className="flex items-center gap-2 text-xs"><Loader2 className="h-3 w-3 animate-spin" />{t('epubImport.inspecting', { percent: uploadPct })}</span>}</label>}
        {step === 'metadata' && inspection && <section className="space-y-4 text-sm"><div className="rounded border p-3"><p className="font-medium">{inspection.metadata.title || file?.name}</p><p className="text-xs text-muted-foreground">{inspection.metadata.creators?.join(', ') || t('epubImport.unknownAuthor')} · {inspection.metadata.language || 'und'} · {inspection.navigation_source}</p>{inspection.duplicate_source && <p className="mt-2 text-xs text-amber-600">{t('epubImport.duplicateSource')}</p>}</div><fieldset className="space-y-2"><legend className="text-xs font-medium">{t('epubImport.target')}</legend><label className="mr-4 text-xs"><input type="radio" checked={targetMode === 'existing_book'} onChange={() => setTargetMode('existing_book')} /> {t('epubImport.existingBook')}</label><label className="text-xs"><input type="radio" checked={targetMode === 'new_book'} onChange={() => setTargetMode('new_book')} /> {t('epubImport.newBook')}</label></fieldset><fieldset className="space-y-2"><legend className="text-xs font-medium">{t('epubImport.metadataPolicy')}</legend>{(['title', 'description', 'language', 'subjects'] as const).map((field) => <label className="mr-3 text-xs" key={field}>{t(`epubImport.metadata.${field}`)} <select data-testid={`epub-import-metadata-${field}`} value={metadataPolicy[field]} onChange={(event) => setMetadataPolicy((previous) => ({ ...previous, [field]: event.target.value }))}><option value="keep_existing">{t('epubImport.keepExisting')}</option><option value="use_source">{t('epubImport.useSource')}</option>{field === 'subjects' && <option value="merge">{t('epubImport.mergeSource')}</option>}</select></label>)}</fieldset><label className="block text-xs"><input type="checkbox" checked={useCover} onChange={(event) => setUseCover(event.target.checked)} /> {t('epubImport.applyCover')}</label></section>}
        {step === 'chapters' && inspection && <section className="space-y-3"><div className="flex items-center justify-between"><p className="text-sm font-medium">{t('epubImport.selectedChapters', { count: selected.size })}</p><button className="text-xs text-primary" onClick={() => setSelected(new Set(leaves.map((node) => node.source_key)))}>{t('epubImport.selectAll')}</button></div><div className="max-h-[42vh] space-y-1 overflow-y-auto rounded border p-2">{inspection.structure.map((node) => <TocNode key={node.source_key} node={node} selected={selected} titles={titles} onToggle={(key, enabled) => setSelected((previous) => { const next = new Set(previous); if (enabled) next.add(key); else next.delete(key); return next; })} onTitle={(key, title) => setTitles((previous) => ({ ...previous, [key]: title }))} />)}</div></section>}
        {step === 'confirm' && inspection && <section className="space-y-4 text-sm"><p>{t('epubImport.ready', { count: selected.size, title: inspection.metadata.title || file?.name })}</p><fieldset className="space-y-2"><legend className="text-xs font-medium">{t('epubImport.strategyLabel')}</legend>{(['append', 'merge_by_source_key', 'replace_all'] as const).map((item) => <label className="mr-4 text-xs" key={item}><input data-testid={`epub-import-strategy-${item}`} type="radio" checked={strategy === item} onChange={() => { setStrategy(item); setReplaceConfirmed(false); }} /> {t(`epubImport.strategy.${item}`)}</label>)}</fieldset><fieldset className="space-y-1"><legend className="text-xs font-medium">{t('epubImport.importOptions')}</legend>{([{ key: 'preserve_hierarchy', checked: preserveHierarchy, set: setPreserveHierarchy }, { key: 'import_images', checked: importImages, set: setImportImages }, { key: 'import_footnotes', checked: importFootnotes, set: setImportFootnotes }, { key: 'retain_source', checked: retainSource, set: setRetainSource }] as const).map((option) => <label className="block text-xs" key={option.key}><input data-testid={`epub-import-option-${option.key}`} type="checkbox" checked={option.checked} onChange={(event) => option.set(event.target.checked)} /> {t(`epubImport.options.${option.key}`)}</label>)}</fieldset>{strategy === 'replace_all' && <div className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs"><p>{t('epubImport.replaceWarning')}</p><label className="mt-2 block"><input data-testid="epub-import-replace-confirmation" type="checkbox" checked={replaceConfirmed} onChange={(event) => setReplaceConfirmed(event.target.checked)} /> {t('epubImport.replaceConfirmation')}</label></div>}</section>}
        {step === 'progress' && <section className="space-y-4"><div className="flex items-center gap-2"><Loader2 className="h-5 w-5 animate-spin text-primary" /><div><p className="text-sm font-medium">{job?.status ?? t('epubImport.queued')}</p><p className="text-xs text-muted-foreground">{job?.current_item?.title || t('epubImport.waiting')}</p></div></div><Progress done={job?.progress_completed ?? 0} total={job?.progress_total ?? selected.size} /><p className="text-xs text-muted-foreground">{t('epubImport.backgroundProgress')}</p>{job?.cancellable && <button disabled={busy} onClick={() => void updateJob('cancel')} className="rounded border px-3 py-1.5 text-xs">{t('epubImport.cancel')}</button>}</section>}
        {step === 'report' && <section className="space-y-4"><div className="flex gap-2"><CheckCircle2 className="h-5 w-5 text-green-600" /><div><p className="text-sm font-medium">{job?.status}</p><p data-testid="epub-import-report-summary" className="text-xs text-muted-foreground">{t('epubImport.reportSummary', { chapters: report?.chapters_created ?? job?.chapters_created ?? 0, warnings: report?.warnings?.length ?? 0 })}</p></div></div>{report?.warnings?.length ? <div data-testid="epub-import-report-warnings" className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs"><p className="mb-1 font-medium">{t('epubImport.warningDetails')}</p><pre className="max-h-28 overflow-auto whitespace-pre-wrap">{JSON.stringify(report.warnings, null, 2)}</pre></div> : null}{report?.errors?.length ? <pre className="max-h-28 overflow-auto rounded border bg-muted p-2 text-xs">{JSON.stringify(report.errors, null, 2)}</pre> : null}<div className="flex gap-2">{job?.resumable && <button data-testid="epub-import-resume" disabled={busy} onClick={() => void updateJob('resume')} className="rounded border px-3 py-1.5 text-xs"><RotateCcw className="mr-1 inline h-3 w-3" />{t('epubImport.resume')}</button>}{job?.rollback_available && <button data-testid="epub-import-rollback" disabled={busy} onClick={() => void updateJob('rollback')} className="rounded border border-destructive/50 px-3 py-1.5 text-xs text-destructive">{t('epubImport.rollback')}</button>}{targetMode === 'new_book' && job?.book_id && <button onClick={() => navigate(`/books/${job.book_id}`)} className="rounded border px-3 py-1.5 text-xs">{t('epubImport.openBook')}</button>}<button onClick={() => onOpenChange(false)} className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground">{t('epubImport.close')}</button></div></section>}
      </main>
      {(step === 'metadata' || step === 'chapters' || step === 'confirm') && <footer className="flex justify-between border-t p-3"><button className="rounded border px-3 py-1.5 text-xs" onClick={() => setStep(STEPS[Math.max(0, currentIndex - 1)])}>{t('epubImport.back')}</button><button data-testid="epub-import-next" disabled={busy || (step === 'chapters' && selected.size === 0) || (step === 'confirm' && strategy === 'replace_all' && !replaceConfirmed)} className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50" onClick={() => step === 'confirm' ? void beginImport() : setStep(STEPS[currentIndex + 1])}>{step === 'confirm' ? t('epubImport.start') : t('epubImport.continue')}</button></footer>}
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}

function TocNode({ node, selected, titles, onToggle, onTitle }: { node: EpubNavigationNode; selected: Set<string>; titles: Record<string, string>; onToggle: (key: string, enabled: boolean) => void; onTitle: (key: string, value: string) => void }) {
  const { t } = useTranslation('books');
  const contentLeaf = Boolean(node.source_href) && !(node.children?.length);
  return <div style={{ marginLeft: node.depth * 14 }} className="space-y-1"><div className="flex items-center gap-2 text-xs">{contentLeaf ? <input aria-label={t('epubImport.selectChapter', { title: node.title })} type="checkbox" checked={selected.has(node.source_key)} onChange={(event) => onToggle(node.source_key, event.target.checked)} /> : <span className="w-4" />}<span className="min-w-0 flex-1 truncate">{node.title || node.source_key}</span><span className="text-[10px] text-muted-foreground">{node.role}</span></div>{contentLeaf && <input className="ml-6 w-[calc(100%-1.5rem)] rounded border px-2 py-1 text-xs" value={titles[node.source_key] ?? node.title} onChange={(event) => onTitle(node.source_key, event.target.value)} />}{node.children?.map((child) => <TocNode key={child.source_key} node={child} selected={selected} titles={titles} onToggle={onToggle} onTitle={onTitle} />)}</div>;
}

function collectContentLeaves(nodes: EpubNavigationNode[]): EpubNavigationNode[] { return nodes.flatMap((node) => node.children?.length ? collectContentLeaves(node.children) : node.source_href ? [node] : []); }
function Progress({ done, total }: { done: number; total: number }) { const { t } = useTranslation('books'); const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0; return <div><div className="mb-1 flex justify-between text-xs"><span>{t('epubImport.progress', { done, total })}</span><span>{percent}%</span></div><div className="h-2 overflow-hidden rounded bg-muted"><div className="h-full bg-primary transition-all" style={{ width: `${percent}%` }} /></div></div>; }
