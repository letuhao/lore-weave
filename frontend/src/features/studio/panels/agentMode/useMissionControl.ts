// #20_agent_mode.md §3-7 (Mission control) — controller. Owns the run/report/
// plan/chapter queries, the derived unit queue + selected-unit detail, the
// gate-check derivation, and every action (transitions, review, revert-all,
// pause-policy toggle, "open full diff"). No JSX (MVC: hooks own logic).
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { planForgeApi } from '@/features/plan-forge/api';
import { useStudioHost } from '../../host/StudioHostProvider';
import {
  useAuthoringRun, useAuthoringRunMutations, useAuthoringRunReport,
} from '@/features/composition/authoringRuns/hooks';
import { computeGateChecks, allGateChecksPass } from '@/features/composition/authoringRuns/gateChecks';
import { REPORTABLE_RUN_STATUSES, type RunAction } from '@/features/composition/authoringRuns/fsm';
import type { RevertAllResult } from '@/features/composition/authoringRuns/types';
import type { QueueRow } from './UnitQueue';
import type { SelectedUnitDetail } from './DiffReviewPanel';
import type { AffectedUnit } from './RevertAllModal';

export function useMissionControl(bookId: string, runId: string | null) {
  const { t } = useTranslation('composition');
  const { accessToken } = useAuth();
  const host = useStudioHost();

  const runQuery = useAuthoringRun(runId);
  const run = runQuery.data ?? null;

  const chaptersQuery = useQuery({
    queryKey: ['book-toc-for-authoring', bookId],
    queryFn: () => booksApi.listChapters(accessToken!, bookId, {
      lifecycle_state: 'active', sort: 'sort_order', limit: 500,
    }),
    enabled: !!accessToken && !!bookId,
  });
  const chapterLabel = (chapterId: string): string => {
    const c = chaptersQuery.data?.items.find((x) => x.chapter_id === chapterId);
    return c?.title || c?.original_filename || `${chapterId.slice(0, 8)}…`;
  };

  const reportEnabled = !!run && REPORTABLE_RUN_STATUSES.includes(run.status);
  const reportQuery = useAuthoringRunReport(runId, reportEnabled);

  const planQuery = useQuery({
    queryKey: ['plan-run-for-authoring-gate', bookId, run?.plan_run_id],
    queryFn: () => planForgeApi.getRun(bookId, run!.plan_run_id, accessToken!),
    enabled: !!accessToken && !!run,
  });

  const bookChapterIds = chaptersQuery.data ? new Set(chaptersQuery.data.items.map((c) => c.chapter_id)) : null;
  const gateChecks = run
    ? computeGateChecks({
      planStatus: planQuery.data?.status ?? null,
      scopeIds: run.scope,
      bookChapterIds,
      budgetUsd: Number.parseFloat(run.budget_usd) || 0,
      toolAllowlist: run.tool_allowlist,
    })
    : [];
  const gateChecksAllPass = allGateChecksPass(gateChecks);
  const startDisabledReason = run?.status === 'gated' && !gateChecksAllPass
    ? t('authoringRun.gate.startBlocked', { defaultValue: 'Fix the failing gate check(s) below first.' })
    : null;

  // Unit queue: the REAL per-unit ledger via /report when reachable
  // (report_ready/failed/paused/closed); otherwise SYNTHESIZED from
  // scope/current_unit — accurate because accept/reject can't happen outside
  // a reviewable run status anyway, so every completed index really is just
  // 'drafted' (never accepted/rejected yet) while running/gated/draft.
  const queueRows: QueueRow[] = useMemo(() => {
    if (!run) return [];
    if (reportQuery.data) {
      return reportQuery.data.units.map((u) => ({
        unit_index: u.unit_index,
        chapterLabel: chapterLabel(u.chapter_id),
        status: u.status,
        costUsd: u.cost_usd,
        severity: u.critic_verdict?.severity ?? null,
        notReached: run.status === 'failed' && u.status === 'pending' && u.unit_index > run.current_unit,
      }));
    }
    return run.scope.map((chapterId, i) => ({
      unit_index: i,
      chapterLabel: chapterLabel(chapterId),
      status: i < run.current_unit ? 'drafted' : i === run.current_unit && run.status === 'running' ? 'in_progress' : 'pending',
      costUsd: null,
      severity: null,
      notReached: false,
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }));
  }, [run, reportQuery.data, chaptersQuery.data]);

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const selectUnit = (i: number) => {
    if (!queueRows.length) return;
    setSelectedIndex(Math.max(0, Math.min(queueRows.length - 1, i)));
  };
  const navUnit = (delta: number) => {
    if (selectedIndex === null) { selectUnit(0); return; }
    selectUnit(selectedIndex + delta);
  };

  const selectedUnitDetail: SelectedUnitDetail | null = useMemo(() => {
    if (selectedIndex === null || !run) return null;
    const chapterId = run.scope[selectedIndex];
    if (!chapterId) return null;
    const reportRow = reportQuery.data?.units.find((u) => u.unit_index === selectedIndex) ?? null;
    const row = queueRows.find((r) => r.unit_index === selectedIndex);
    return {
      unitIndex: selectedIndex,
      chapterId,
      chapterLabel: chapterLabel(chapterId),
      status: row?.status ?? 'pending',
      preRevisionId: reportRow?.pre_revision_id ?? null,
      postRevisionId: reportRow?.post_revision_id ?? null,
      costUsd: reportRow?.cost_usd ?? null,
      errorMessage: reportRow?.error_message ?? null,
      criticVerdict: reportRow?.critic_verdict ?? null,
      downstreamUnitIndexes: reportRow?.downstream_unit_indexes ?? [],
      notReached: row?.notReached ?? false,
      // eslint-disable-next-line react-hooks/exhaustive-deps
    };
  }, [selectedIndex, run, reportQuery.data, queueRows]);

  const mutations = useAuthoringRunMutations(bookId, runId);

  const [revertOpen, setRevertOpen] = useState(false);
  const [revertResult, setRevertResult] = useState<RevertAllResult | null>(null);
  const affectedForRevert: AffectedUnit[] = (reportQuery.data?.units ?? [])
    .filter((u) => u.status === 'drafted' || u.status === 'accepted')
    .map((u) => ({ unitIndex: u.unit_index, chapterLabel: chapterLabel(u.chapter_id), fromStatus: u.status }));

  const runAction = (action: RunAction) => {
    if (action === 'revert-all') { setRevertResult(null); setRevertOpen(true); return; }
    if (action === 'gate') mutations.gate.mutate();
    else if (action === 'start') mutations.start.mutate();
    else if (action === 'pause') mutations.pause.mutate();
    else if (action === 'resume') mutations.resume.mutate();
    else if (action === 'close') mutations.close.mutate();
  };

  const confirmRevert = async () => {
    const result = await mutations.revertAll.mutateAsync();
    setRevertResult(result);
  };

  const openFullDiff = (chapterId: string, fromRevisionId: string, toRevisionId: string) => {
    host.openPanel('chapter-revision-compare', { params: { chapterId, fromRevisionId, toRevisionId } });
  };

  const acceptSelected = () => { if (selectedIndex !== null) mutations.acceptUnit.mutate(selectedIndex); };
  const rejectSelected = () => { if (selectedIndex !== null) mutations.rejectUnit.mutate(selectedIndex); };

  return {
    runQuery, run, gateChecks, gateChecksAllPass, startDisabledReason,
    queueRows, selectedIndex, selectUnit, navUnit, selectedUnitDetail,
    mutations, runAction,
    revertOpen, setRevertOpen, revertResult, affectedForRevert, confirmRevert,
    openFullDiff, acceptSelected, rejectSelected,
    reviewBusy: mutations.acceptUnit.isPending || mutations.rejectUnit.isPending,
  };
}
