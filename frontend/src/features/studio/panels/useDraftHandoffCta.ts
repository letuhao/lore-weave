// Code-driven drafting-handoff CTA. When the book has a DRAFTABLE plan (a plan run the authoring-run
// start-gate accepts — 'validated' or 'compiled'), the co-writer chat surfaces a "Start drafting →"
// affordance that opens Agent-Mode's New-run view.
//
// This is USER-driven (the writer clicks) + LOGIC-driven (this hook detects the state) — deliberately
// NOT an agent nav tool. `ui_open_studio_panel` was de-advertised 2026-07-25 ("GUI control is
// user/logic-driven, so agent-driven nav only cost tokens"); the chat agent stays a SUPPORTER and
// never drives the GUI. Same 'draftable' filter as useNewRunForm's plan picker (one definition of
// "a run can start"), and the SAME query key so opening the panel is a warm cache hit, not a refetch.
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { planForgeApi } from '@/features/plan-forge/api';

export function useDraftHandoffCta(bookId: string): { showStartDrafting: boolean } {
  const { accessToken } = useAuth();
  const plansQuery = useQuery({
    queryKey: ['plan-runs-for-authoring', bookId],
    queryFn: () => planForgeApi.listRuns(bookId, accessToken!, { limit: 50 }),
    enabled: !!accessToken && !!bookId,
  });
  const showStartDrafting = (plansQuery.data?.items ?? []).some(
    (p) => p.status === 'validated' || p.status === 'compiled',
  );
  return { showStartDrafting };
}
