// The language row in the motif drawer — and, when the motif is yours, the paid
// translate (spec 2026-07-29-motif-i18n §5).
//
// The drawer renders the motif AS AUTHORED, not localized, and that is deliberate: it is
// the surface the owner edits from and the PATCH is whole-object, so showing a
// translation here and saving would write the translated wording onto the source row and
// destroy the original. This component is how the drawer can still be honest about
// language without becoming one of the translations — it names the original outright and
// lists which languages exist beside it, each flagged when the source has moved since.
//
// The buy affordance appears only for a motif you OWN. The platform's own motifs ship in
// every supported language for free and are refused server-side; a public motif someone
// else owns must be adopted first. Both cases say so rather than showing nothing — an
// affordance that always 403s is worse than none, and a missing one with no explanation
// is the bug that this repo keeps re-learning.
//
// Render + local run-config only; the flow lives in useMotifTranslate.
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { motifApi } from '../api';
import { CostConfirmCard } from './CostConfirmCard';
import { ModelRolePicker } from '../../../campaigns/components/ModelRolePicker';
import { useMotifTranslate } from '../hooks/useMotifTranslate';
import { MOTIF_TRANSLATE_LANGUAGES, type Motif, type MotifTranslateLanguage } from '../types';

type Props = {
  motif: Motif;
  /** Whether this caller may BUY a translation — which is exactly the set they may EDIT,
   *  and deliberately so: the server allows a motif you own OR a book's SHARED row you
   *  hold EDIT on. Gating this on ownership alone would have shut every collaborator out
   *  of a capability the backend grants them — a backend permission with no UI path is
   *  the same dead-capability shape as no permission at all.
   *
   *  Excluded either way: a SYSTEM motif (its translations are System tier — seeded,
   *  admin-managed, shared by every user; a user write there is the kinds bug) and
   *  someone else's public motif (adopt it first, which clones it into your tier). */
  canTranslate: boolean;
  token: string | null;
  bookId?: string | null;
};

const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English', vi: 'Tiếng Việt', ja: '日本語', ko: '한국어',
  'zh-CN': '简体中文', 'zh-TW': '繁體中文', es: 'Español', 'pt-BR': 'Português (Brasil)',
  fr: 'Français', de: 'Deutsch', ru: 'Русский', id: 'Bahasa Indonesia',
  ms: 'Bahasa Melayu', th: 'ไทย', tr: 'Türkçe', ar: 'العربية', hi: 'हिन्दी',
};
const label = (code: string) => LANGUAGE_LABELS[code] ?? code;

export function MotifTranslateAction({ motif, canTranslate, token, bookId }: Props) {
  const { t, i18n } = useTranslation('composition');
  // Default the target to what the reader is already reading the app in — that is the
  // language they discovered the gap in.
  const uiLang = (MOTIF_TRANSLATE_LANGUAGES as readonly string[]).includes(i18n.language)
    ? (i18n.language as MotifTranslateLanguage)
    : 'en';
  const [target, setTarget] = useState<MotifTranslateLanguage>(uiLang);
  const [model, setModel] = useState<string | null>(null);
  // The buy form is DISCLOSED, not always-on. The drawer's resting state is the language
  // row; a model picker sitting open under every motif is clutter, and mounting one
  // eagerly drags an auth-provider dependency into a surface that is otherwise pure
  // render (it broke the drawer's own tests, which is the honest signal that the default
  // state was wrong).
  const [buying, setBuying] = useState(false);
  // The hook invalidates ['composition','motif'], which prefix-matches the inventory
  // query below — so a completed translate refreshes this row without extra wiring.
  const tr = useMotifTranslate(token);
  const busy = tr.mint.isPending || tr.confirm.isPending;

  // What already exists. The drawer shows the motif AS AUTHORED — deliberately, since it
  // is the edit surface and the PATCH is whole-object — so the inventory is how it can
  // report the reader's language without silently becoming it.
  const inventory = useQuery({
    queryKey: ['composition', 'motif', motif.id, 'translations', bookId ?? null],
    queryFn: () => motifApi.motifTranslations(motif.id, token!, bookId),
    enabled: !!token,
  });
  const rows = inventory.data?.translations ?? [];
  const have = rows.find((r) => r.language_code === target);
  const haveUi = rows.find((r) => r.language_code === uiLang);
  const missingUi = uiLang !== motif.original_language && !haveUi;

  // `force` when a translation already exists and is merely STALE: the server would
  // otherwise (correctly) decline to charge again, and staleness is exactly the case
  // where charging again is what the user is asking for.
  const staleTarget = !!have?.stale;
  const outcome = tr.result?.results?.[0];

  return (
    <div data-testid="motif-language" className="rounded border border-neutral-200 p-2 text-xs dark:border-neutral-700">
      <div className="flex flex-wrap items-center gap-1">
        {/* Always stated, never inferred. A caller — reader or model prompt — must never
            receive this text without knowing what language it is in; the bug this layer
            replaces briefed an English book in Vietnamese and said nothing. */}
        <span className="text-neutral-500">
          {t('motif.language.writtenIn', { defaultValue: 'Written in' })}
        </span>
        <span data-testid="motif-language-current" className="rounded bg-neutral-200 px-1.5 py-0.5 dark:bg-neutral-700">
          {label(motif.original_language)}
        </span>
        {rows.map((r) => (
          <span
            key={r.language_code}
            data-testid={`motif-language-have-${r.language_code}`}
            title={r.source === 'authored'
              ? t('motif.language.authored', { defaultValue: 'hand-written translation' })
              : (r.translated_by ?? '')}
            className={r.stale
              ? 'rounded bg-amber-100 px-1.5 py-0.5 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
              : 'rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'}
          >
            {label(r.language_code)}
            {r.stale ? ` · ${t('motif.language.staleShort', { defaultValue: 'outdated' })}` : ''}
          </span>
        ))}
        {missingUi && (
          <span data-testid="motif-language-fallback" className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
            {t('motif.language.missingYours', {
              defaultValue: 'not in {{lang}} — it falls back to the original',
              lang: label(uiLang),
            })}
          </span>
        )}
      </div>

      {!canTranslate && missingUi && (
        // Say WHY there is no button. A missing affordance with no explanation is the
        // bug; a stated reason is the fix (the same call the drawer's Edit control makes).
        <p data-testid="motif-language-not-yours" className="mt-1 text-neutral-500">
          {motif.owner_user_id == null
            ? t('motif.language.systemFree', {
              defaultValue: 'Built-in motifs are provided in every supported language — this one has no translation for your language yet.',
            })
            : t('motif.language.adoptFirst', {
              defaultValue: 'Adopt this motif into your library to translate it.',
            })}
        </p>
      )}

      {canTranslate && token && !buying && !tr.estimate && !tr.result && (
        <div className="mt-1 flex flex-col gap-0.5">
          <button
            type="button"
            data-testid="motif-translate-open"
            className="self-start rounded border border-amber-500 px-2 py-0.5 text-amber-700 hover:bg-amber-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
            onClick={() => setBuying(true)}
          >
            {t('motif.language.translate', { defaultValue: 'Translate…' })}
          </button>
          <p className="text-neutral-500">
            {t('motif.language.youPay', {
              defaultValue: 'Your own motifs are never translated automatically — this runs on your model, at your cost.',
            })}
          </p>
        </div>
      )}

      {canTranslate && token && buying && !tr.estimate && !tr.result && (
        <div className="mt-2 flex flex-col gap-1">
          <label className="flex items-center gap-1">
            <span className="text-neutral-500">
              {t('motif.language.translateTo', { defaultValue: 'Translate to' })}
            </span>
            <select
              data-testid="motif-language-target"
              className="rounded border border-neutral-300 px-1 py-0.5 dark:border-neutral-600 dark:bg-neutral-800"
              value={target}
              disabled={busy}
              onChange={(e) => setTarget(e.target.value as MotifTranslateLanguage)}
            >
              {MOTIF_TRANSLATE_LANGUAGES.filter((l) => l !== motif.original_language).map((l) => (
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
            data-testid="motif-translate-btn"
            className="self-start rounded border border-amber-500 px-2 py-0.5 text-amber-700 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
            // A fresh translation already exists: the server would decline to charge for
            // it anyway, so do not offer a button whose only outcome is "you were not
            // charged". A STALE one is different — re-buying it is the point.
            disabled={!model || busy || (!!have && !have.stale)}
            onClick={() => model && tr.mint.mutate({
              motifIds: [motif.id], targetLanguage: target, bookId,
              force: staleTarget, modelRef: model,
            })}
          >
            {tr.mint.isPending
              ? t('motif.language.estimating', { defaultValue: 'Estimating…' })
              : have && !have.stale
                ? t('motif.language.alreadyHave', { defaultValue: 'Already translated' })
                : staleTarget
                  ? t('motif.language.retranslate', { defaultValue: 'Re-translate…' })
                  : t('motif.language.translate', { defaultValue: 'Translate…' })}
          </button>
          <button type="button" data-testid="motif-translate-cancel" className="self-start text-neutral-500 underline" onClick={() => setBuying(false)}>
            {t('motif.action.cancel', { defaultValue: 'Cancel' })}
          </button>
        </div>
      )}

      {tr.estimate && (
        <div className="mt-2">
          {/* The server drops ids the caller may not translate, so the batch it quotes can
              be smaller than the one they picked. Quoting a narrowed batch without saying
              so is a silent no-op with a price tag on it. */}
          {tr.estimate.skipped > 0 && (
            <p data-testid="motif-translate-skipped" className="mb-1 text-amber-700 dark:text-amber-300">
              {t('motif.language.skipped', {
                defaultValue: '{{count}} of the motifs you picked are not yours to translate and are not included.',
                count: tr.estimate.skipped,
              })}
            </p>
          )}
          <CostConfirmCard
            estimate={tr.estimate}
            whatItDoes={t('motif.language.confirmWhat', {
              defaultValue: 'Translate this motif to {{lang}} using your model.',
              lang: label(target),
            })}
            confirming={tr.confirm.isPending}
            onConfirm={() => tr.confirm.mutate()}
            onCancel={tr.cancel}
          />
        </div>
      )}

      {outcome && (
        <div data-testid="motif-translate-result" className="mt-2 flex flex-col gap-0.5">
          <p className={outcome.status === 'translated' ? 'text-emerald-700 dark:text-emerald-400' : 'text-neutral-500'}>
            {t(`motif.language.outcome.${outcome.status}`, {
              defaultValue: OUTCOME_FALLBACK[outcome.status] ?? outcome.status,
              lang: label(tr.result!.target_language),
            })}
          </p>
          {/* Reported, never silently retried: the user has already paid for one pass,
              so a second one would double their spend without asking. */}
          {!!outcome.echoed?.length && (
            <p data-testid="motif-translate-echoed" className="text-amber-700 dark:text-amber-300">
              {t('motif.language.echoed', {
                defaultValue: '{{count}} field(s) came back untranslated — your model may not handle this language well.',
                count: outcome.echoed.length,
              })}
            </p>
          )}
          <button type="button" className="self-start text-neutral-500 underline" onClick={() => { tr.reset(); setBuying(false); }}>
            {t('motif.language.again', { defaultValue: 'Translate another language' })}
          </button>
        </div>
      )}

      {(tr.mint.isError || tr.confirm.isError) && (
        <p data-testid="motif-translate-error" role="alert" className="mt-1 text-rose-600 dark:text-rose-400">
          {tr.isQuota
            ? t('motif.language.quota', { defaultValue: 'Spending limit reached.' })
            : ((tr.error as Error | null)?.message
              || t('motif.language.failed', { defaultValue: 'Translation failed.' }))}
        </p>
      )}
    </div>
  );
}

// Each outcome is a DISTINCT thing that happened, and the user paid (or deliberately did
// not) for each — collapsing them into "done" would hide that they were charged nothing
// for an already-fresh translation, or that a hand-written one was protected.
const OUTCOME_FALLBACK: Record<string, string> = {
  translated: 'Translated to {{lang}}.',
  already_original: 'This motif is already written in that language.',
  already_translated: 'Already translated and still current — you were not charged.',
  authored_kept: 'A hand-written translation exists and was kept.',
  nothing_to_translate: 'This motif has no text to translate.',
  not_translatable: 'This motif is not yours to translate.',
  model_failed: 'Your model returned nothing usable — nothing was saved.',
  failed: 'Translation failed.',
  cancelled: 'Cancelled before this motif was translated — you were not charged for it.',
};
