// Studio Quality tab — `quality-canon`: book-wide canon problems, merging THREE backend lenses
// (see useQualityCanon for what each one asks):
//   - composition critic      -> violations of an author-declared canon RULE (keyed by rule_id).
//   - composition canon-check -> entity continuity (a "gone" character still acting).
//   - knowledge extraction    -> contradictions flagged while building the KG.
// Logic lives in useQualityCanon; this file renders. Clicking a row that resolves to a chapter
// jumps there via the existing `focusManuscriptUnit` host action.
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { Skeleton } from '@/components/shared';
import type { CanonIssue, RuleViolationItem } from '@/features/composition/types';
import type { CanonFlag } from '@/features/knowledge/api';
import { useStudioHost } from '../host/StudioHostProvider';
import { useQualityCanon, type CanonFocusParams, type QualityCanonView } from './useQualityCanon';
import { useStudioPanel } from './useStudioPanel';

type T = (k: string, o?: Record<string, unknown>) => string;

const BANNER = 'rounded p-2 text-[11px]';
const WARN = `${BANNER} bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300`;
const INFO = `${BANNER} bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300`;
const FOCUS = `${BANNER} bg-sky-50 text-sky-800 dark:bg-sky-950 dark:text-sky-300`;
const ROW = 'flex items-start justify-between gap-2 rounded border p-2 text-[11px]';
const HIT = 'border-sky-400 bg-sky-50 ring-2 ring-sky-400 dark:border-sky-700 dark:bg-sky-950/40';
const BAD = 'border-rose-200 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/40';

export function QualityCanonPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-canon', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const v = useQualityCanon(host.bookId, accessToken, props.params as CanonFocusParams | undefined);

  const jump = (id: string | null | undefined) => id && host.focusManuscriptUnit(id);
  const jumpLabel = t('quality.jumpToChapter', { defaultValue: 'Open chapter' });

  if (v.loading) {
    return (
      <div data-testid="quality-canon-loading" className="space-y-3 p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return (
    <div data-testid="studio-quality-canon-panel" className="flex h-full min-h-0 flex-col gap-3 overflow-auto p-3 text-sm">
      <FocusBanner v={v} t={t as T} />

      <p className="text-[11px] text-neutral-400">
        {/* Text deliberately UNCHANGED: `scripts/i18n_translate.py` gap-fills only — it keeps a
            valid existing translation — so editing an `en` string that already has 17 translations
            leaves those 17 permanently stale. The new lane announces itself through the translated
            "Broken rules (N)" section header instead. */}
        {t('quality.canonIntro', {
          defaultValue: 'Advisory — confirmed contradictions with content marked gone/changed earlier in the book. Nothing here is applied automatically.',
        })}
      </p>

      {/* UNCONSULTED != CLEAN. Composition's two lanes never ran, so we say so rather than
          rendering an empty list that reads as "this book is fine". */}
      {v.compositionUnavailable && (
        <div data-testid="quality-canon-unavailable" className={WARN}>
          {t('quality.canonUnavailable', { defaultValue: 'Could not reach the co-writer service — generation-time canon findings are NOT included below.' })}
        </div>
      )}
      {v.noWork && (
        <div data-testid="quality-canon-no-work" className={INFO}>
          {t('quality.canonNoWork', { defaultValue: 'This book has no co-writer session yet, so generation-time canon checks have not run. Only knowledge-extraction findings are shown.' })}
        </div>
      )}
      {v.ruleError && (
        <div data-testid="quality-canon-rule-error" className={WARN}>
          {t('quality.canonRuleError', { defaultValue: 'Could not load canon-rule violations — try again.' })}
        </div>
      )}
      {v.compositionError && (
        <div data-testid="quality-canon-composition-error" className={WARN}>
          {t('quality.canonCompositionError', { defaultValue: 'Could not load canon issues from generation — try again.' })}
        </div>
      )}
      {v.extractionError && (
        <div data-testid="quality-canon-extraction-error" className={WARN}>
          {t('quality.canonExtractionError', { defaultValue: 'Could not load canon flags from knowledge extraction — try again.' })}
        </div>
      )}

      {v.empty && (
        <div data-testid="quality-canon-empty" className="p-4 text-center text-neutral-500">
          {t('quality.canonEmpty', { defaultValue: 'No canon issues found.' })}
        </div>
      )}

      {/* OUT-5 — a truncation the reader cannot see reads as completeness. */}
      {v.ruleCapped && (
        <div data-testid="quality-canon-rules-capped" className={INFO}>
          {t('quality.canonRulesCapped', {
            defaultValue: 'Showing the {{shown}} most recent of {{total}} broken rules.',
            shown: v.ruleViolations.length, total: v.ruleCount,
          })}
        </div>
      )}

      {v.ruleViolations.length > 0 && (
        <Section testId="quality-canon-rules-section" title={t('quality.canonFromRules', { defaultValue: 'Broken rules ({{n}})', n: v.ruleCount })}>
          {v.ruleViolations.map((r, i) => (
            <RuleRow key={`${r.job_id}:${r.rule_id ?? 'unattributed'}:${i}`} r={r}
                     focused={!!v.focusRuleId && r.rule_id === v.focusRuleId}
                     onJump={() => jump(r.chapter_id)} jumpLabel={jumpLabel}
                     onEditRule={r.rule_id ? () => host.openPanel('quality-canon-rules', { params: { focusRuleId: r.rule_id } }) : undefined}
                     t={t as T} />
          ))}
        </Section>
      )}

      {v.canonIssues.length > 0 && (
        <Section testId="quality-canon-composition-section" title={t('quality.canonFromGeneration', { defaultValue: 'From generation ({{n}})', n: v.canonIssues.length })}>
          {v.canonIssues.map((issue) => (
            <IssueRow key={issue.scene_id} issue={issue}
                      focused={!!v.focusChapterId && issue.chapter_id === v.focusChapterId}
                      onJump={() => jump(issue.chapter_id)} jumpLabel={jumpLabel} t={t as T} />
          ))}
        </Section>
      )}

      {v.canonFlags.length > 0 && (
        <Section testId="quality-canon-extraction-section" title={t('quality.canonFromExtraction', { defaultValue: 'From knowledge extraction ({{n}})', n: v.canonFlags.length })}>
          {v.canonFlags.map((flag) => <FlagRow key={flag.log_id} flag={flag} onJump={jump} jumpLabel={jumpLabel} />)}
        </Section>
      )}
    </div>
  );
}

/** A deep-link says what it focused — and ADMITS when it matched nothing. But it may only claim
 *  "nothing has broken this rule" if the rule lane actually ran; otherwise that is a false-clean. */
function FocusBanner({ v, t }: { v: QualityCanonView; t: T }) {
  if (v.focusRuleId) {
    return (
      <div data-testid="quality-canon-rule-focus" className={FOCUS}>
        {v.ruleFocusHits > 0
          ? t('quality.canonRuleFocused', {
              defaultValue: 'Showing violations of the rule you came from first ({{n}}): “{{rule}}”',
              n: v.ruleFocusHits,
              rule: v.focusRuleText ?? t('quality.canonRuleUnnamed', { defaultValue: 'that rule' }),
            })
          : v.compositionUnknown
            ? t('quality.canonRuleFocusUnknown', { defaultValue: 'The rule you came from could not be checked, because the co-writer service is unavailable. It may still be broken somewhere — this is not a result.' })
            : t('quality.canonRuleFocusedEmpty', { defaultValue: 'The rule you came from has no open violations. It is anchored here, but nothing has broken it.' })}
      </div>
    );
  }
  if (!v.focusChapterId) return null;
  return (
    <div data-testid="quality-canon-focus" className={FOCUS}>
      {v.chapterFocusHits > 0
        ? t('quality.canonFocused', { defaultValue: 'Showing the chapter you came from first ({{n}} finding(s)).', n: v.chapterFocusHits })
        : v.compositionUnknown
          ? t('quality.canonRuleFocusUnknown', { defaultValue: 'The rule you came from could not be checked, because the co-writer service is unavailable. It may still be broken somewhere — this is not a result.' })
          : t('quality.canonFocusedEmpty', { defaultValue: 'The chapter you came from has no canon findings here.' })}
    </div>
  );
}

function RuleRow({ r, focused, onJump, jumpLabel, onEditRule, t }: {
  r: RuleViolationItem; focused: boolean; onJump: () => void; jumpLabel: string;
  onEditRule?: () => void; t: T;
}) {
  return (
    <li data-testid="quality-canon-rule-item" data-focused={focused ? 'true' : undefined}
        className={`${ROW} ${focused ? HIT : BAD}`}>
      <div className="flex flex-col gap-0.5">
        {/* An unresolved rule (archived, or an id the judge paraphrased) is labelled as such — the
            finding is REAL, and hiding it would fake a clean book. */}
        <span className="font-medium text-rose-700 dark:text-rose-300">
          {r.rule_text ?? t('quality.canonRuleGone', { defaultValue: 'A rule that no longer exists' })}
        </span>
        <span className="text-rose-600 dark:text-rose-400">⚠ {r.why || r.span}</span>
        <span className="text-neutral-500">{r.scene_title || t('quality.untitledScene', { defaultValue: 'Untitled scene' })}</span>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {r.chapter_id && <JumpButton onClick={onJump} tone="bg-rose-600" label={jumpLabel} />}
        {/* Deep-link (spec §4): a resolvable rule can be jumped to in Canon rules to fix it — the
            write half of "what's broken → fix the rule". Unresolvable (archived) rules have no id. */}
        {r.rule_id && onEditRule && (
          <button
            type="button"
            data-testid="quality-canon-edit-rule"
            onClick={onEditRule}
            className="rounded border border-rose-300 px-1.5 py-0.5 text-[10px] text-rose-700 hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/40"
          >
            {t('quality.editRule', { defaultValue: 'Edit rule' })}
          </button>
        )}
      </div>
    </li>
  );
}

function IssueRow({ issue, focused, onJump, jumpLabel, t }: {
  issue: CanonIssue; focused: boolean; onJump: () => void; jumpLabel: string; t: T;
}) {
  return (
    <li data-testid="quality-canon-composition-item" data-focused={focused ? 'true' : undefined}
        className={`${ROW} ${focused ? HIT : BAD}`}>
      <div className="flex flex-col gap-0.5">
        <span className="font-medium text-rose-700 dark:text-rose-300">
          {issue.scene_title || t('quality.untitledScene', { defaultValue: 'Untitled scene' })}
        </span>
        {issue.violations.map((vi, i) => (
          <span key={i} className="text-rose-600 dark:text-rose-400">⚠ {vi.why || vi.name}</span>
        ))}
      </div>
      {issue.chapter_id && <JumpButton onClick={onJump} tone="bg-rose-600" label={jumpLabel} />}
    </li>
  );
}

function FlagRow({ flag, onJump, jumpLabel }: {
  flag: CanonFlag; onJump: (id: string) => void; jumpLabel: string;
}) {
  const chapterId = flag.context.source_type === 'chapter' ? String(flag.context.source_id ?? '') : null;
  return (
    <li data-testid="quality-canon-extraction-item"
        className={`${ROW} border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40`}>
      <span className="text-amber-700 dark:text-amber-300">⚠ {flag.message}</span>
      {chapterId && <JumpButton onClick={() => onJump(chapterId)} tone="bg-amber-600" label={jumpLabel} />}
    </li>
  );
}

function Section({ title, testId, children }: { title: string; testId: string; children: React.ReactNode }) {
  return (
    <section data-testid={testId} className="flex flex-col gap-1">
      <h3 className="text-xs font-medium text-neutral-600 dark:text-neutral-300">{title}</h3>
      <ul className="flex flex-col gap-1">{children}</ul>
    </section>
  );
}

function JumpButton({ onClick, tone, label }: { onClick: () => void; tone: string; label: string }) {
  return (
    <button type="button" data-testid="quality-canon-jump"
            className={`shrink-0 rounded px-2 py-0.5 text-white ${tone}`} onClick={onClick}>
      {label}
    </button>
  );
}
