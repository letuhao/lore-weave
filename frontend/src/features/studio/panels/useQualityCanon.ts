// Controller for the Studio Quality tab's `quality-canon` panel. Owns the THREE
// backend lenses the panel merges and the deep-link focus derivation; the panel
// itself only renders (features/<name>/hooks own logic, components render).
//
// The three lenses are three genuinely different questions, and keeping them
// straight is the whole reason this hook exists:
//
//   1. RULE violations   (composition `critic.violations[]`)  — "which author-declared
//      canon RULE does this passage contradict?"  Keyed by `rule_id`.
//   2. ENTITY continuity (composition `result.canon.violations[]`) — "is a character
//      marked gone still acting?"  Keyed by `entity_id`. Carries NO rule id.
//   3. KG extraction flags (knowledge-service) — contradictions found while building
//      the knowledge graph.
//
// 24 PH18 deep-links land here with a `focusRuleId` (from the Plan Hub's canon badge)
// and/or a `focusChapterId`. A focus HOISTS and HIGHLIGHTS — it never hides. And when
// the thing you came from has no findings we say so explicitly, rather than showing an
// unchanged list that silently pretends the link did something.
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { compositionApi } from '@/features/composition/api';
import { useQualityWork } from './useQualityWork';
import type { CanonIssue, RuleViolationItem } from '@/features/composition/types';
import { knowledgeApi, type CanonFlag } from '@/features/knowledge/api';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';

export interface CanonFocusParams {
  /** 24 PH18 — the canon_rule.id the Plan Hub badge was anchored to. */
  focusRuleId?: string | null;
  focusChapterId?: string | null;
}

export interface QualityCanonView {
  loading: boolean;
  hasError: boolean;
  compositionError: boolean;
  ruleError: boolean;
  extractionError: boolean;
  /** composition-service could not be reached at all — its two lanes are UNKNOWN, not clean. */
  compositionUnavailable: boolean;
  /** This book has no co-writer Work, so generation-time canon never ran. Also UNKNOWN, not clean. */
  noWork: boolean;
  /** True when neither composition lane was consulted. `empty` is impossible while this holds. */
  compositionUnknown: boolean;
  empty: boolean;
  ruleViolations: RuleViolationItem[];
  canonIssues: CanonIssue[];
  canonFlags: CanonFlag[];
  focusRuleId: string | null;
  focusChapterId: string | null;
  /** Rows matching the focused RULE. 0 while a rule is focused ⇒ say so. */
  ruleFocusHits: number;
  /** Rows matching the focused CHAPTER in the entity lane. */
  chapterFocusHits: number;
  /** The focused rule's text, if any row resolved it — null when the rule is gone. */
  focusRuleText: string | null;
  /** OUT-5 — the rule list is capped; `ruleCount` is the EXACT total. Never truncate silently. */
  ruleCapped: boolean;
  ruleCount: number;
}

/** Hoist the rows a focus matches to the top. Stable: a non-matching row keeps its
 *  relative order, so the list never reshuffles under the reader. */
function hoist<T>(rows: T[], matches: (row: T) => boolean, active: boolean): T[] {
  if (!active) return rows;
  return [...rows].sort((a, b) => Number(matches(b)) - Number(matches(a)));
}

export function useQualityCanon(
  bookId: string,
  accessToken: string | null,
  params: CanonFocusParams | undefined,
): QualityCanonView {
  const focusRuleId = params?.focusRuleId ?? null;
  const focusChapterId = params?.focusChapterId ?? null;

  // ONE gate (useQualityWork) — it knows `unavailable` from `no-work`, and that `candidates` means
  // Works EXIST. This hook used to re-derive that, and got `candidates` wrong.
  const work = useQualityWork(bookId, accessToken);
  const projectId = work.kind === 'ready' ? work.projectId : null;
  const enabled = !!projectId && !!accessToken;

  const rulesQ = useQuery({
    queryKey: ['studio', 'quality-canon', 'rules', projectId],
    queryFn: () => compositionApi.getRuleViolations(projectId!, accessToken!),
    enabled,
  });
  const issuesQ = useQuery({
    queryKey: ['studio', 'quality-canon', 'composition', projectId],
    queryFn: () => compositionApi.getCanonIssues(projectId!, accessToken!),
    enabled,
  });

  const { projectId: knowledgeProjectId, isLoading: knowledgeProjectLoading } =
    useBookKnowledgeProject(bookId);
  const flagsQ = useQuery({
    queryKey: ['studio', 'quality-canon', 'knowledge', knowledgeProjectId],
    queryFn: () => knowledgeApi.listCanonFlags(knowledgeProjectId!, accessToken!),
    enabled: !!knowledgeProjectId && !!accessToken,
  });

  const allRules = useMemo(() => rulesQ.data?.items ?? [], [rulesQ.data]);
  const allIssues = useMemo(() => issuesQ.data?.items ?? [], [issuesQ.data]);
  const canonFlags = flagsQ.data?.flags ?? [];

  const ruleViolations = useMemo(
    () => hoist(allRules, (r) => r.rule_id === focusRuleId, !!focusRuleId),
    [allRules, focusRuleId],
  );
  const canonIssues = useMemo(
    () => hoist(allIssues, (i) => i.chapter_id === focusChapterId, !!focusChapterId),
    [allIssues, focusChapterId],
  );

  const ruleFocusHits = focusRuleId
    ? allRules.filter((r) => r.rule_id === focusRuleId).length
    : 0;
  const chapterFocusHits = focusChapterId
    ? allIssues.filter((i) => i.chapter_id === focusChapterId).length
    : 0;
  const focusRuleText = focusRuleId
    ? allRules.find((r) => r.rule_id === focusRuleId && r.rule_text)?.rule_text ?? null
    : null;

  // ── UNCONSULTED != CLEAN (the bug this hook exists to not have) ───────────────────────────
  // Both composition lanes are `enabled: !!projectId`. With no project they never run, so they
  // resolve to [] with no error — and a naive `empty` would then render "No canon issues found"
  // over a book whose canon was never checked at all. That is a false-negative, and it is not
  // hypothetical: a Work created while knowledge-service was down is `pending_project_backfill`
  // (NULL project_id) and the resolver EXCLUDES it, so this is the state of a real book.
  //   `unavailable` = composition-service is down       -> UNKNOWN (an error, not an absence)
  //   any other non-`found` = this book has no Work yet  -> UNKNOWN (nothing has run)
  // The sibling quality panels (promises/critic/coverage) already render QualityNoWorkState here.
  // The knowledge-extraction lane is INDEPENDENT of the Work and still renders either way.
  const compositionUnavailable = work.kind === 'unavailable';
  const noWork = work.kind === 'no-work';
  const compositionUnknown = compositionUnavailable || noWork;

  // A fetch error must NEVER render as "no issues" either — same false-negative, louder.
  const hasError = rulesQ.isError || issuesQ.isError || flagsQ.isError || compositionUnavailable;
  const empty =
    !hasError && !compositionUnknown &&
    ruleViolations.length === 0 && canonIssues.length === 0 && canonFlags.length === 0;

  return {
    loading:
      work.kind === 'loading' ||
      knowledgeProjectLoading ||
      (!!projectId && (rulesQ.isLoading || issuesQ.isLoading)) ||
      (!!knowledgeProjectId && flagsQ.isLoading),
    hasError,
    compositionError: issuesQ.isError,
    ruleError: rulesQ.isError,
    extractionError: flagsQ.isError,
    compositionUnavailable,
    noWork,
    compositionUnknown,
    empty,
    ruleViolations,
    canonIssues,
    canonFlags,
    focusRuleId,
    focusChapterId,
    ruleFocusHits,
    chapterFocusHits,
    focusRuleText,
    ruleCapped: rulesQ.data?.capped ?? false,
    ruleCount: rulesQ.data?.count ?? allRules.length,
  };
}
