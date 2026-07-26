// #20_agent_mode.md §2 (New run config) — controller. Owns the plan pick,
// ordered chapter scope, budget/level/allowlist, the pause_after_each_unit
// toggle, and the create+gate flow. No JSX (MVC: hooks own logic).
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { planForgeApi } from '@/features/plan-forge/api';
import { useBootstrap } from '@/features/plan-forge/hooks/useBootstrap';
import { useUserModels } from '@/components/model-picker';
import { isChatSafeDefault } from '@/features/ai-models/api';
import { booksApi, type Chapter } from '@/features/books/api';
import { authoringRunsApi, errorDetail } from '@/features/composition/authoringRuns/api';
import { computeGateChecks, allGateChecksPass } from '@/features/composition/authoringRuns/gateChecks';
import type { CreateAuthoringRunBody } from '@/features/composition/authoringRuns/types';

// MUST be a subset of the backend's ALLOWLISTABLE_TOOLS (authoring_run_service.py) — create() validates
// each against that closed set and 422s the WHOLE run on any stray name. The prior default shipped two
// that aren't in it ('composition_read_outline' → it's 'composition_list_outline'; 'glossary_lookup' →
// not allowlistable at all), so a default-config run could never be created. Draft-write + the two reads
// it drafts from.
const DEFAULT_TOOL_ALLOWLIST = ['composition_write_prose', 'composition_list_outline', 'composition_get_prose'];

export function useNewRunForm(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();

  const plansQuery = useQuery({
    queryKey: ['plan-runs-for-authoring', bookId],
    queryFn: () => planForgeApi.listRuns(bookId, accessToken!, { limit: 50 }),
    enabled: !!accessToken && !!bookId,
  });
  // D3 — client-filter to plan runs the start-gate would actually accept.
  const approvedPlans = (plansQuery.data?.items ?? []).filter(
    (p) => p.status === 'validated' || p.status === 'compiled',
  );

  const chaptersQuery = useQuery({
    queryKey: ['book-toc-for-authoring', bookId],
    queryFn: () => booksApi.listChapters(accessToken!, bookId, {
      lifecycle_state: 'active', sort: 'sort_order', limit: 500,
    }),
    enabled: !!accessToken && !!bookId,
  });
  const chapters: Chapter[] = chaptersQuery.data?.items ?? [];

  const [planRunId, setPlanRunId] = useState('');
  const [scopeIds, setScopeIds] = useState<string[]>([]); // ORDER = run order
  const [budgetUsd, setBudgetUsd] = useState('4.00');
  const [level, setLevel] = useState<3 | 4>(3);
  const [toolAllowlist, setToolAllowlist] = useState<string[]>(DEFAULT_TOOL_ALLOWLIST);
  const [pauseAfterEachUnit, setPauseAfterEachUnit] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Materialise (the handoff bridge): a compiled plan's chapters live only in the composition
  // spec tree until bootstrap creates the real book chapters. Without them the scope picker is
  // empty and no run can start — so surface a one-click "Create chapters from this plan" here
  // instead of punting the writer to the Planner panel. Reuses the plan-forge bootstrap gate.
  const bootstrap = useBootstrap(bookId, accessToken ?? null);
  const [materializedCount, setMaterializedCount] = useState<number | null>(null);

  // The DRAFTING model. The seam hard-requires params.model_ref (a user_model UUID) and there is no
  // server-side default for this account — a run created without it gates fine but FAILS on the first
  // unit ("params.model_ref required"). Mirror the Planner's picker: a shared user-models fetch + a
  // derived favourite/first default (chat-safe), overridable by the writer.
  const [modelRef, setModelRef] = useState('');
  const models = useUserModels({ capability: 'chat', enabled: !!accessToken && !!bookId });
  const autoModelRef = useMemo(() => {
    const candidates = (models.models ?? []).filter(isChatSafeDefault);
    if (!candidates.length) return '';
    return (candidates.find((m) => m.is_favorite) ?? candidates[0]).user_model_id;
  }, [models.models]);
  const effectiveModelRef = modelRef || autoModelRef;

  // One-time default: select every book chapter (book order) once the TOC
  // loads. A ref guard so a later "uncheck everything" by the user is never
  // clobbered by a re-render (this is a synchronization-from-server-default
  // concern, not a reaction to a user action).
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current || chapters.length === 0) return;
    seededRef.current = true;
    setScopeIds(chapters.map((c) => c.chapter_id));
  }, [chapters]);

  // Also default the plan pick to the first approved plan once it loads.
  const planSeededRef = useRef(false);
  useEffect(() => {
    if (planSeededRef.current || approvedPlans.length === 0) return;
    planSeededRef.current = true;
    setPlanRunId(approvedPlans[0].id);
  }, [approvedPlans]);

  const toggleChapter = (chapterId: string) => {
    setScopeIds((prev) =>
      prev.includes(chapterId) ? prev.filter((id) => id !== chapterId) : [...prev, chapterId],
    );
  };

  const moveChapter = (index: number, direction: -1 | 1) => {
    setScopeIds((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const addAllowlistTool = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed || toolAllowlist.includes(trimmed)) return;
    setToolAllowlist((prev) => [...prev, trimmed]);
  };
  const removeAllowlistTool = (name: string) => {
    setToolAllowlist((prev) => prev.filter((t) => t !== name));
  };

  const bookChapterIds = chaptersQuery.data ? new Set(chapters.map((c) => c.chapter_id)) : null;
  const budgetNum = Number.parseFloat(budgetUsd) || 0;
  const selectedPlan = approvedPlans.find((p) => p.id === planRunId) ?? null;
  // Bootstrap PROPOSE needs a compiled package — only a 'compiled' plan can materialise chapters
  // ('validated' has no package yet). A busy bootstrap disables re-clicks.
  const canMaterialize = !!planRunId && selectedPlan?.status === 'compiled' && !bootstrap.busy;
  const gateChecks = computeGateChecks({
    planStatus: selectedPlan?.status ?? null,
    scopeIds,
    bookChapterIds,
    budgetUsd: budgetNum,
    toolAllowlist,
  });
  // A run can't draft without a model (the seam requires it), so block the create until one resolves.
  const canRunGateCheck = allGateChecksPass(gateChecks) && !!effectiveModelRef && !busy;

  /** create() then gate() — both real endpoints, in sequence (the backend has
   * no single "validate a draft config" call). Returns the new gated run's id
   * on success; throws with the real server message on failure (the run is
   * left in `draft`, reachable again from the Runs list, no gated state to
   * inspect since gate() is all-or-nothing and never partially applies). */
  const runGateCheck = async (): Promise<string> => {
    setBusy(true);
    setError(null);
    try {
      const body: CreateAuthoringRunBody = {
        book_id: bookId,
        plan_run_id: planRunId,
        level,
        scope: scopeIds,
        budget_usd: budgetUsd,
        tool_allowlist: toolAllowlist,
        // The drafting-seam inputs — without model_ref the run fails on its first unit.
        params: { model_source: 'user_model', model_ref: effectiveModelRef },
        background: false,
        pause_after_each_unit: pauseAfterEachUnit,
      };
      const created = await authoringRunsApi.create(body, accessToken!);
      await authoringRunsApi.gate(created.run_id, accessToken!);
      await qc.invalidateQueries({ queryKey: ['authoring-runs', bookId] });
      return created.run_id;
    } catch (e) {
      const msg = errorDetail(e);
      setError(msg);
      throw new Error(msg);
    } finally {
      setBusy(false);
    }
  };

  /** One-click materialise: create the book chapters the compiled plan implies, then refetch the
   * TOC so they appear in the scope picker (and auto-select via the seed effect — we clear the
   * seed guard so the freshly-created chapters get selected, safe because the list was empty). */
  const materializeChapters = async (): Promise<void> => {
    if (!planRunId) return;
    setMaterializedCount(null);
    const applied = await bootstrap.materialize(planRunId);
    if (!applied) return; // bootstrap.error holds the message (e.g. "adopt an ontology first")
    const created = Object.values(applied.applied_results ?? {}).filter(
      (r) => 'chapter_id' in r,
    ).length;
    setMaterializedCount(created);
    seededRef.current = false; // re-seed scope from the reloaded TOC (the new chapters)
    await qc.invalidateQueries({ queryKey: ['book-toc-for-authoring', bookId] });
  };

  return {
    plansQuery, approvedPlans, chaptersQuery, chapters,
    planRunId, setPlanRunId,
    scopeIds, toggleChapter, moveChapter,
    budgetUsd, setBudgetUsd,
    level, setLevel,
    toolAllowlist, addAllowlistTool, removeAllowlistTool,
    pauseAfterEachUnit, setPauseAfterEachUnit,
    gateChecks, canRunGateCheck, busy, error,
    runGateCheck,
    // drafting model
    modelRef, setModelRef, effectiveModelRef, modelsLoading: models.loading,
    // materialise handoff
    materializeChapters, canMaterialize,
    materializing: bootstrap.busy, materializeError: bootstrap.error, materializedCount,
  };
}
