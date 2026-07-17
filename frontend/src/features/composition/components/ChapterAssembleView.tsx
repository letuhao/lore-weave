// LOOM chapter-assembly-modes (FE) — the "Assemble" tab (view).
//
// Runs chapter single-pass (B2) or stitch (B3) at CHAPTER granularity, shows the
// result in an editable preview, and captures the human gate (edit/regenerate/
// reject) → composition.generation_corrected → learning-service. Generates with
// persist=false (does NOT clobber the editor draft); Accept inserts via onAccept.
// Logic lives in useChapterAssembly; this renders only.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useCorrection } from '../hooks/useAutoGenerate';
import { useGenerateChapter, useSetAssemblyMode, useStitchChapter } from '../hooks/useChapterAssembly';
import { useCriticStateOptional } from '../context/CriticStateContext';
import { useAssembleStateOptional } from '../context/AssembleStateContext';
import { CanonGatePanel } from './CanonGatePanel';
import type { AssemblyMode, ChapterGeneration, CorrectionBody } from '../types';

type Props = {
  projectId: string;
  bookId: string;
  chapterId: string;
  modelRef: string;
  modelKind?: string;
  modelName?: string;
  settings: Record<string, unknown>;
  scenesAllDone: boolean;
  token: string | null;
  // Returns TRUE only when the assembled chapter actually landed in the editor. We keep the preview
  // (and skip the edit-correction) on false, so accepting a whole generated chapter before the Editor
  // is open on this chapter doesn't evaporate it (legacy co-mount always returns true).
  onAccept: (text: string) => boolean;
};

export function ChapterAssembleView({
  projectId, bookId, chapterId, modelRef, modelKind, modelName, settings, scenesAllDone, token, onAccept,
}: Props) {
  const { t } = useTranslation('composition');
  const mode = (settings.assembly_mode as AssemblyMode) ?? 'per_scene';
  const gen = useGenerateChapter(token);
  const stitch = useStitchChapter(token);
  const setMode = useSetAssemblyMode(bookId, token);
  const correction = useCorrection(token);
  // WS-B1 — share the chapter's canon-gate verdict so the standing `critic` panel
  // surfaces it (chapter assembly has no per-dimension critique → critic: null).
  const criticState = useCriticStateOptional();

  // WS-D — the draft {result, edited, last} is owned by the cross-window
  // AssembleStateProvider when present (so a pop-out keeps an un-accepted draft);
  // falls back to local state in a bare mount (unit tests / no windowing host).
  const shared = useAssembleStateOptional();
  const [localResult, setLocalResult] = useState<ChapterGeneration | null>(null);
  const [localEdited, setLocalEdited] = useState('');
  const [localLast, setLocalLast] = useState<'chapter' | 'stitch'>('chapter');
  const result = shared ? shared.result : localResult;
  const edited = shared ? shared.edited : localEdited;
  const last = shared ? shared.last : localLast;
  const setResult = shared ? shared.setResult : setLocalResult;
  const setEdited = shared ? shared.setEdited : setLocalEdited;
  const setLast = shared ? shared.setLast : setLocalLast;

  const busy = gen.isPending || stitch.isPending;
  const params = { projectId, chapterId, modelRef, modelKind, modelName };
  const onResult = (r: ChapterGeneration) => {
    setResult(r);
    setEdited(r.text);
    if (r.canon) criticState?.setVerdict({ critic: null, canon: r.canon, jobId: r.job_id });
  };

  const runChapter = () => { setLast('chapter'); gen.mutate(params, { onSuccess: onResult }); };
  const runStitch = () => { setLast('stitch'); stitch.mutate(params, { onSuccess: onResult }); };
  const rerun = () => (last === 'stitch' ? runStitch() : runChapter());

  const correct = (body: CorrectionBody) => { if (result) correction.mutate({ jobId: result.job_id, body }); };
  const accept = () => {
    if (!result) return;
    // Insert first; if it failed (no editor open on this chapter in the dock) keep the preview and do
    // NOT capture a correction or clear — the writer can Accept again once the Editor is up.
    if (!onAccept(edited)) return;
    // edit-capture: only a REAL change is a correction (the BE 422s a zero-change
    // edit; accept-as-is is not a kind — H2 self-reinforcement guard).
    if (edited.trim() !== result.text.trim()) correct({ kind: 'edit', edited_text: edited });
    setResult(null);
  };
  const regenerate = () => { correct({ kind: 'regenerate' }); rerun(); };
  const reject = () => { correct({ kind: 'reject' }); setResult(null); };

  const errObj = (gen.error || stitch.error) as { body?: { detail?: { code?: string } } } | null;
  const errCode = errObj?.body?.detail?.code;
  const errMsg = !errObj ? '' :
    errCode === 'NO_CHAPTER_PLAN' ? t('errNoChapterPlan', { defaultValue: 'Decompose this chapter into scenes first.' }) :
    errCode === 'NO_SCENE_DRAFTS' ? t('errNoSceneDrafts', { defaultValue: 'No completed scene drafts to stitch yet.' }) :
    errCode === 'SCENES_NOT_DONE' ? t('errScenesNotDone', { defaultValue: 'Mark all scenes done before stitching.' }) :
    t('generateFailed', { defaultValue: 'Generation failed — try again.' });

  const canGen = !!modelRef && !busy;

  return (
    <div className="flex flex-col gap-2 p-3" data-testid="assemble-view">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-neutral-500">{t('assemblyMode', { defaultValue: 'Assembly mode' })}:</span>
        {(['per_scene', 'chapter'] as AssemblyMode[]).map((m) => (
          <button
            key={m}
            data-testid={`assemble-mode-${m}`}
            className={`rounded px-2 py-0.5 ${mode === m ? 'bg-indigo-600 text-white' : 'border border-neutral-300 dark:border-neutral-600'}`}
            disabled={setMode.isPending || mode === m}
            onClick={() => setMode.mutate({ projectId, currentSettings: settings, mode: m })}
          >
            {t(`assemblyMode_${m}`, { defaultValue: m === 'chapter' ? 'Chapter' : 'Per-scene' })}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          data-testid="assemble-generate-chapter"
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={!canGen}
          onClick={runChapter}
        >
          {gen.isPending ? t('generating', { defaultValue: 'Generating…' }) : t('generateChapter', { defaultValue: 'Generate chapter' })}
        </button>
        <button
          data-testid="assemble-stitch"
          className="rounded border border-indigo-500 px-3 py-1.5 text-sm text-indigo-600 disabled:opacity-50 dark:text-indigo-300"
          disabled={!canGen || !scenesAllDone}
          title={scenesAllDone
            ? t('stitchHint', { defaultValue: 'Merge the done scene drafts into one chapter' })
            : t('stitchNeedsDone', { defaultValue: 'All scenes must be done to stitch' })}
          onClick={runStitch}
        >
          {stitch.isPending ? t('stitching', { defaultValue: 'Stitching…' }) : t('stitchChapter', { defaultValue: 'Stitch chapter' })}
        </button>
        {!modelRef && <span className="self-center text-xs text-amber-600">{t('needModel', { defaultValue: 'Pick a model' })}</span>}
        {/* D-S1-GATE-REASON-INLINE: once a model IS picked, the only remaining stitch gate is
            scenes-done — surface it inline (not just the disabled button's tooltip). */}
        {modelRef && !scenesAllDone && (
          <span data-testid="assemble-stitch-blocked" className="self-center text-xs text-muted-foreground">
            {t('stitchNeedsDone', { defaultValue: 'All scenes must be done to stitch' })}
          </span>
        )}
      </div>

      {errMsg && <div data-testid="assemble-error" className="rounded bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950">{errMsg}</div>}

      {result?.canon && <CanonGatePanel canon={result.canon} onRevise={regenerate} />}

      {result && (
        <div className="flex flex-col gap-2">
          {result.degraded && (
            <span data-testid="assemble-degraded" className="self-start rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-700 dark:bg-amber-950 dark:text-amber-300">
              {t('stitchDegraded', { defaultValue: 'Stitch unavailable — raw concatenation' })}
            </span>
          )}
          <textarea
            data-testid="assemble-preview"
            className="w-full resize-y rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-600"
            rows={12}
            value={edited}
            onChange={(e) => setEdited(e.target.value)}
            aria-label={t('assemblePreview', { defaultValue: 'Assembled chapter (editable)' })}
          />
          <div className="flex gap-2">
            <button data-testid="assemble-accept" className="rounded bg-emerald-600 px-2.5 py-1 text-xs text-white" onClick={accept}>
              {t('accept', { defaultValue: 'Accept' })}
            </button>
            <button data-testid="assemble-regenerate" className="rounded border border-neutral-300 px-2.5 py-1 text-xs disabled:opacity-50 dark:border-neutral-600" disabled={busy} onClick={regenerate}>
              {t('regenerate', { defaultValue: 'Regenerate' })}
            </button>
            <button data-testid="assemble-reject" className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600" onClick={reject}>
              {t('discard', { defaultValue: 'Discard' })}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
