// Batch translate for the motif library — the other half of the user-paid path.
//
// The engine has always taken 1..50 items per job and the MCP tool has always taken an
// array; the only thing missing was somewhere to pick more than one. A capability wired
// at the engine and unreachable at the surface is the shape this repo keeps re-learning,
// so this is the surface.
//
// Two rules it exists to hold, both learned from the single-item path:
//
//   · A batch is never narrowed AFTER the fact. Only rows the caller may actually
//     translate are selectable, and the count in the button is the count that will be
//     charged. Letting someone select twelve and then quoting two — or worse, quoting
//     twelve and translating two — is the silent-truncation bug with a price tag on it.
//   · Results are PER ITEM (CAT-3). "Done" hides that item 7 of 10 came back untranslated
//     or that three were already current and cost nothing.
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CostConfirmCard } from './CostConfirmCard';
import { ModelRolePicker } from '../../../campaigns/components/ModelRolePicker';
import { useMotifTranslate } from '../hooks/useMotifTranslate';
import { MOTIF_TRANSLATE_LANGUAGES, type MotifTranslateLanguage } from '../types';

/** The engine's own per-job ceiling. Stated in the UI BEFORE the spend rather than
 *  applied silently server-side — a batch that quietly drops its tail is exactly what
 *  the per-item result contract exists to prevent. */
export const BATCH_TRANSLATE_CAP = 50;

const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English', vi: 'Tiếng Việt', ja: '日本語', ko: '한국어',
  'zh-CN': '简体中文', 'zh-TW': '繁體中文', es: 'Español', 'pt-BR': 'Português (Brasil)',
  fr: 'Français', de: 'Deutsch', ru: 'Русский', id: 'Bahasa Indonesia',
  ms: 'Bahasa Melayu', th: 'ไทย', tr: 'Türkçe', ar: 'العربية', hi: 'हिन्दी',
};
const label = (code: string) => LANGUAGE_LABELS[code] ?? code;

type Props = {
  /** The ids the user has ticked — already filtered to what they may translate. */
  selectedIds: string[];
  /** How many rows on screen are NOT selectable, so the absence is explained rather
   *  than just observed (the built-ins are free in every language; a public motif must
   *  be adopted first). */
  notSelectableCount: number;
  token: string | null;
  bookId?: string | null;
  onDone: () => void;
  onCancel: () => void;
};

export function MotifBatchTranslateBar({
  selectedIds, notSelectableCount, token, bookId, onDone, onCancel,
}: Props) {
  const { t, i18n } = useTranslation('composition');
  const uiLang = (MOTIF_TRANSLATE_LANGUAGES as readonly string[]).includes(i18n.language)
    ? (i18n.language as MotifTranslateLanguage)
    : 'en';
  const [target, setTarget] = useState<MotifTranslateLanguage>(uiLang);
  const [model, setModel] = useState<string | null>(null);
  const tr = useMotifTranslate(token);
  const busy = tr.mint.isPending || tr.confirm.isPending;

  const overCap = selectedIds.length > BATCH_TRANSLATE_CAP;
  // Per-item outcomes, grouped. A batch reports what happened to each item, and the
  // groups matter: "already current" means the user was NOT charged for it, which is a
  // different fact from "translated" and must not be folded into a total.
  const summary = useMemo(() => {
    const rows = tr.result?.results ?? [];
    const by: Record<string, number> = {};
    for (const r of rows) by[r.status] = (by[r.status] ?? 0) + 1;
    const echoed = rows.reduce((n, r) => n + (r.echoed?.length ?? 0), 0);
    return { by, echoed, total: rows.length };
  }, [tr.result]);

  return (
    <div
      data-testid="motif-batch-translate"
      className="border-b border-amber-300 bg-amber-50/60 p-2 text-xs dark:border-amber-800 dark:bg-amber-950/20"
    >
      {!tr.result && (
        <div className="flex flex-wrap items-center gap-2">
          <span data-testid="motif-batch-count" className="font-medium text-amber-800 dark:text-amber-200">
            {t('motif.batch.selected', {
              defaultValue: '{{count}} selected',
              count: selectedIds.length,
            })}
          </span>

          {notSelectableCount > 0 && (
            // Say why the rest have no checkbox. A row you cannot act on with no reason
            // given reads as a broken list.
            <span data-testid="motif-batch-excluded" className="text-neutral-500">
              {t('motif.batch.excluded', {
                defaultValue: '{{count}} not yours to translate (built-ins are already free in every language; adopt a public one first)',
                count: notSelectableCount,
              })}
            </span>
          )}

          <label className="flex items-center gap-1">
            <span className="text-neutral-500">
              {t('motif.language.translateTo', { defaultValue: 'Translate to' })}
            </span>
            <select
              data-testid="motif-batch-target"
              className="rounded border border-neutral-300 px-1 py-0.5 dark:border-neutral-600 dark:bg-neutral-800"
              value={target}
              disabled={busy}
              onChange={(e) => setTarget(e.target.value as MotifTranslateLanguage)}
            >
              {MOTIF_TRANSLATE_LANGUAGES.map((l) => (
                <option key={l} value={l}>{label(l)}</option>
              ))}
            </select>
          </label>

          <ModelRolePicker
            capability="chat"
            label={t('motif.language.model', { defaultValue: 'Translation model' })}
            value={model}
            onChange={setModel}
            disabled={busy}
          />

          <button
            type="button"
            data-testid="motif-batch-run"
            className="rounded border border-amber-500 px-2 py-0.5 text-amber-700 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
            disabled={!model || busy || selectedIds.length === 0 || overCap}
            onClick={() => model && tr.mint.mutate({
              ids: selectedIds, targetLanguage: target, bookId, modelRef: model,
            })}
          >
            {tr.mint.isPending
              ? t('motif.language.estimating', { defaultValue: 'Estimating…' })
              : t('motif.batch.run', {
                defaultValue: 'Translate {{count}}…',
                count: selectedIds.length,
              })}
          </button>

          <button type="button" data-testid="motif-batch-cancel" className="text-neutral-500 underline" onClick={onCancel}>
            {t('motif.action.cancel', { defaultValue: 'Cancel' })}
          </button>

          {overCap && (
            // Refuse BEFORE the estimate, naming the ceiling. The engine caps the batch
            // server-side either way; discovering that after paying is the bad version.
            <p data-testid="motif-batch-over-cap" role="alert" className="w-full text-rose-600 dark:text-rose-400">
              {t('motif.batch.overCap', {
                defaultValue: 'At most {{cap}} motifs per translation job — deselect {{over}}.',
                cap: BATCH_TRANSLATE_CAP,
                over: selectedIds.length - BATCH_TRANSLATE_CAP,
              })}
            </p>
          )}

          <p className="w-full text-neutral-500">
            {t('motif.language.youPay', {
              defaultValue: 'Your own motifs are never translated automatically — this runs on your model, at your cost.',
            })}
          </p>
        </div>
      )}

      {tr.estimate && (
        <div className="mt-2 max-w-md">
          {tr.estimate.skipped > 0 && (
            <p data-testid="motif-batch-skipped" className="mb-1 text-amber-700 dark:text-amber-300">
              {t('motif.language.skipped', {
                defaultValue: '{{count}} of the motifs you picked are not yours to translate and are not included.',
                count: tr.estimate.skipped,
              })}
            </p>
          )}
          <CostConfirmCard
            estimate={tr.estimate}
            whatItDoes={t('motif.batch.confirmWhat', {
              defaultValue: 'Translate {{count}} motif(s) to {{lang}} using your model.',
              count: selectedIds.length,
              lang: label(target),
            })}
            confirming={tr.confirm.isPending}
            onConfirm={() => tr.confirm.mutate()}
            onCancel={tr.cancel}
          />
        </div>
      )}

      {tr.result && (
        <div data-testid="motif-batch-result" className="flex flex-col gap-1">
          <p className="font-medium text-amber-800 dark:text-amber-200">
            {t('motif.batch.doneTitle', {
              defaultValue: '{{written}} of {{total}} translated to {{lang}}',
              written: tr.result.written,
              total: summary.total,
              lang: label(tr.result.target_language),
            })}
          </p>
          {/* Every distinct outcome named. Folding "already current — you were not
              charged" into a total would hide the one fact a paying user most wants. */}
          <ul className="flex flex-col gap-0.5 text-neutral-600 dark:text-neutral-300">
            {Object.entries(summary.by)
              .filter(([status]) => status !== 'translated')
              .map(([status, n]) => (
                <li key={status} data-testid={`motif-batch-outcome-${status}`}>
                  {n} × {t(`motif.language.outcome.${status}`, { defaultValue: status })}
                </li>
              ))}
          </ul>
          {summary.echoed > 0 && (
            <p data-testid="motif-batch-echoed" className="text-amber-700 dark:text-amber-300">
              {t('motif.language.echoed', {
                defaultValue: '{{count}} field(s) came back untranslated — your model may not handle this language well.',
                count: summary.echoed,
              })}
            </p>
          )}
          <button
            type="button"
            data-testid="motif-batch-close"
            className="self-start text-neutral-500 underline"
            onClick={() => { tr.reset(); onDone(); }}
          >
            {t('motif.action.close', { defaultValue: 'Close' })}
          </button>
        </div>
      )}

      {(tr.mint.isError || tr.confirm.isError) && (
        <p data-testid="motif-batch-error" role="alert" className="mt-1 text-rose-600 dark:text-rose-400">
          {tr.isQuota
            ? t('motif.language.quota', { defaultValue: 'Spending limit reached.' })
            : ((tr.error as Error | null)?.message
              || t('motif.language.failed', { defaultValue: 'Translation failed.' }))}
        </p>
      )}
    </div>
  );
}
