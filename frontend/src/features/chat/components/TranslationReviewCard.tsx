import { useTranslation } from 'react-i18next';
import { Languages, Check, SkipForward } from 'lucide-react';
import { getLanguageName } from '@/lib/languages';
import type { ToolCallRecord } from '../types';

// S4 — translation-review card. The agent's `glossary_propose_translation` (target
// NAMES) and `glossary_propose_aliases` (per-language alias SETS) are class-W: they
// write DRAFT translations immediately (never overwriting a verified value), so they
// don't suspend the run for a confirm card. This read-only card makes that action
// visible inline — what was proposed, in which language, how many landed vs were
// skipped — so the human knows to go verify/edit the drafts in the Glossary editor
// (where AttrTranslationRow renders the draft/verified badge + the alias chip editor).

interface ProposeItem {
  entity_id?: string;
  value?: string;
  aliases?: string[];
}
interface TranslateArgs {
  book_id?: string;
  language_code?: string;
  items?: ProposeItem[];
}
interface ItemResult {
  entity_id?: string;
  status?: string;
  reason?: string;
}
interface TranslateResult {
  language_code?: string;
  written?: number;
  skipped?: number;
  results?: ItemResult[];
}

const PREVIEW_CAP = 8;

/** True for a completed (non-pending, ok) translation/alias propose tool call. */
export function isTranslationProposeCall(record: ToolCallRecord): boolean {
  return (
    !record.pending &&
    record.ok &&
    (record.tool === 'glossary_propose_translation' || record.tool === 'glossary_propose_aliases')
  );
}

export interface TranslationReviewSummary {
  isAliases: boolean;
  langName: string;
  values: string[];
  written: number;
  skipped: number;
}

/** Parse a completed translation/alias propose call into a renderable summary, or null
 *  when the record carries nothing to show (e.g. a replayed record that persisted only
 *  {tool, ok} without args/result). Callers route a null-summary record to the plain tool
 *  chip instead — never excluding it from BOTH the chip and the card (which would hide the
 *  tool call entirely). */
export function summarizeTranslationReview(record: ToolCallRecord): TranslationReviewSummary | null {
  const args = (record.args ?? {}) as TranslateArgs;
  const result = (record.result ?? {}) as TranslateResult;
  const isAliases = record.tool === 'glossary_propose_aliases';
  const lang = result.language_code || args.language_code || '';
  // The proposed values are the useful, human-readable payload (the translated
  // names / alias strings). Entity ids are opaque, so we surface the values.
  const values: string[] = (args.items ?? []).flatMap((it) =>
    isAliases ? (it.aliases ?? []) : it.value ? [it.value] : [],
  );
  const written = result.written ?? 0;
  const skipped = result.skipped ?? 0;
  if (values.length === 0 && written === 0 && skipped === 0) return null;
  return { isAliases, langName: lang ? getLanguageName(lang) : '', values, written, skipped };
}

export function TranslationReviewCard({ record }: { record: ToolCallRecord }) {
  const { t } = useTranslation('chat');
  const summary = summarizeTranslationReview(record);
  // Nothing meaningful to show → render nothing (the caller keeps it as a chip).
  if (!summary) return null;
  const { isAliases, langName, values, written, skipped } = summary;

  const shown = values.slice(0, PREVIEW_CAP);
  const overflow = values.length - shown.length;

  return (
    <div
      data-testid="translation-review-card"
      className="mt-1.5 space-y-1.5 rounded-md border border-blue-500/25 bg-blue-500/5 p-2 text-xs"
    >
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-blue-400">
        <Languages className="h-3 w-3" />
        {isAliases
          ? t('translation_review.header_aliases', { lang: langName })
          : t('translation_review.header', { lang: langName })}
        <span className="rounded bg-amber-400/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-amber-400">
          {t('translation_review.draft')}
        </span>
      </div>

      {shown.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {shown.map((v, i) => (
            <span key={`${v}-${i}`} className="rounded bg-background/70 px-1.5 py-0.5 text-[11px] text-foreground/90">
              {v}
            </span>
          ))}
          {overflow > 0 && (
            <span className="px-1 py-0.5 text-[11px] text-muted-foreground">
              {t('translation_review.more', { count: overflow })}
            </span>
          )}
        </div>
      )}

      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1 text-emerald-500">
          <Check className="h-3 w-3" />
          {t('translation_review.written', { count: written })}
        </span>
        {skipped > 0 && (
          <span className="inline-flex items-center gap-1">
            <SkipForward className="h-3 w-3" />
            {t('translation_review.skipped', { count: skipped })}
          </span>
        )}
        <span className="flex-1" />
        <span>{t('translation_review.verify_hint')}</span>
      </div>
    </div>
  );
}
