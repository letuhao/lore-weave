import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Check } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { LanguagePicker } from '@/components/shared/LanguagePicker';
import { TRANSLATION_TARGETS } from '@/lib/languages';
import { useBatchTranslate } from '../hooks/useBatchTranslate';
import type { TranslationCandidateEntity } from '../types';

// S4 — batch-translate dialog. Pick a target language, then fill draft translations for
// many entities at once. Writes via apply-translations (never overwrites a verified
// value) and shows the server's partial-failure report. The agent path
// (glossary_propose_translation) and this human path share the same draft semantics.
//
// DOCK-9 migration: hand-rolled `fixed inset-0` overlay replaced with the shared
// FormDialog (docs/standards/dockable-gui.md). `open` is a bare boolean prop —
// the parent conditionally mounts/unmounts this component — and `onClose` is
// called directly with no busy-guard, preserving the pre-migration behavior
// (this component never blocked dismissal while submitting).

export function BatchTranslateDialog({ bookId, onClose }: { bookId: string; onClose: () => void }) {
  const { t } = useTranslation('glossaryTiering');
  const bt = useBatchTranslate(bookId);
  // S7/D13: a closed-set picker replaces the free-text input + regex. The old code silently
  // no-op'd on a value the regex rejected; a picker can only emit a valid registry code, and
  // selecting one loads its candidates directly (no separate "Load" step to forget).
  const [lang, setLang] = useState('');

  return (
    <FormDialog
      open
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={t('batch_translate.title', { defaultValue: 'Batch translate' })}
      size="3xl"
      footer={
        <>
          <div className="mr-auto text-[11px] text-muted-foreground">
            {bt.result && (
              <span>
                {t('batch_translate.result', {
                  defaultValue: '{{w}} written · {{v}} kept (verified) · {{e}} empty · {{f}} failed',
                  w: bt.result.translated,
                  v: bt.result.skipped_verified,
                  e: bt.result.skipped_empty,
                  f: bt.result.failed.length,
                })}
              </span>
            )}
          </div>
          <button
            onClick={() => void bt.submit()}
            disabled={bt.submitting || !bt.targetLanguage || bt.candidates.length === 0}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {bt.submitting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
            {t('batch_translate.apply', { defaultValue: 'Apply translations' })}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {/* Language bar */}
        <div className="flex items-center gap-2 border-b pb-3">
          <label className="text-xs text-muted-foreground">
            {t('batch_translate.target_lang', { defaultValue: 'Target language' })}
          </label>
          <LanguagePicker
            value={lang}
            onChange={(code) => { setLang(code); if (code) bt.selectLanguage(code); }}
            codes={TRANSLATION_TARGETS.map((l) => l.code)}
            placeholder={t('batch_translate.select_lang', { defaultValue: 'Select…' })}
            aria-label={t('batch_translate.target_lang', { defaultValue: 'Target language' })}
            className="w-44 rounded border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />
          {bt.targetLanguage && (
            <span className="text-[11px] text-muted-foreground">
              {t('batch_translate.count', { defaultValue: '{{n}} entities to translate', n: bt.total })}
            </span>
          )}
        </div>

        {/* Body */}
        {bt.loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            <Loader2 className="mr-1 inline h-4 w-4 animate-spin" />
            {t('batch_translate.loading', { defaultValue: 'Loading…' })}
          </p>
        ) : bt.error ? (
          <p className="py-8 text-center text-sm text-destructive">{bt.error}</p>
        ) : !bt.targetLanguage ? (
          <p className="py-8 text-center text-xs italic text-muted-foreground">
            {t('batch_translate.pick_lang', { defaultValue: 'Pick a target language to begin.' })}
          </p>
        ) : bt.candidates.length === 0 ? (
          <p className="py-8 text-center text-xs italic text-muted-foreground">
            {t('batch_translate.none', { defaultValue: 'No untranslated entities for this language.' })}
          </p>
        ) : (
          <div className="space-y-3">
            {bt.candidates.map((ent) => (
              <EntityRow key={ent.entity_id} ent={ent} bt={bt} />
            ))}
          </div>
        )}
      </div>
    </FormDialog>
  );
}

function EntityRow({
  ent,
  bt,
}: {
  ent: TranslationCandidateEntity;
  bt: ReturnType<typeof useBatchTranslate>;
}) {
  return (
    <section className="rounded-lg border bg-card p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold">
        {ent.display_name || ent.entity_id}
        <span className="rounded-full bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-medium text-violet-400">
          {ent.kind_code}
        </span>
      </div>
      <div className="space-y-2">
        {ent.attributes.map((a) => (
          <label key={a.attr_value_id} className="block">
            <span className="mb-0.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <span className="font-mono">{a.code}</span>
              <span className="truncate italic">{a.original_value}</span>
              {a.existing_confidence && (
                <span className="rounded bg-amber-400/15 px-1 text-[9px] text-amber-400">{a.existing_confidence}</span>
              )}
            </span>
            <input
              value={bt.drafts[`${ent.entity_id}:${a.attr_value_id}`] ?? ''}
              onChange={(e) => bt.setDraft(ent.entity_id, a.attr_value_id, e.target.value)}
              className="w-full rounded-md border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring/40"
            />
          </label>
        ))}
      </div>
    </section>
  );
}
