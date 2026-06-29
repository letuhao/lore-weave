// W10 — the materialize action (D-W10-APPLY-PLANNER-MATERIALIZE): commit button →
// POST …/arc/materialize; a 409 surfaces a "Replace existing" affordance that re-POSTs
// with replace:true; the result summarizes the committed tree + unresolved/folded motifs.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { ArcMaterializeAction } from '../components/ArcMaterializeAction';
import type { ArcTemplate } from '../arcTypes';

const ARC = { id: 'A1', name: 'Revenge' } as ArcTemplate;

const RESULT = (over: Record<string, unknown> = {}) => ({
  arc_id: 'arc-node', arc_template_id: 'A1', chapter_ids: ['c1', 'c2'],
  scene_ids: ['s1', 's2', 's3'], motif_applications: 3, scenes_total: 3,
  beats_distributed: 3, unresolved_placements: [], drop_merge_report: [], replay: false, ...over,
});

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => apiJson.mockReset());

describe('ArcMaterializeAction', () => {
  it('commits the arc onto the work and summarizes the committed tree', async () => {
    apiJson.mockResolvedValueOnce(RESULT());
    render(<ArcMaterializeAction arc={ARC} projectId="p1" token="tok" rosterBindings={{ protagonist: 'Lin' }} />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('arc-materialize-run'));
    await waitFor(() => expect(screen.getByTestId('arc-materialize-result')).toBeInTheDocument());
    const call = apiJson.mock.calls[0];
    expect(call[0]).toBe('/v1/composition/works/p1/arc/materialize');
    const body = JSON.parse((call[1] as { body: string }).body);
    expect(body).toEqual({ arc_template_id: 'A1', roster_bindings: { protagonist: 'Lin' }, replace: false });
    // once committed, the run button is replaced by the result summary (no re-commit).
    expect(screen.queryByTestId('arc-materialize-run')).toBeNull();
  });

  it('a 409 offers Replace, which re-commits with replace:true', async () => {
    apiJson
      .mockRejectedValueOnce(Object.assign(new Error('planned'), { status: 409 }))
      .mockResolvedValueOnce(RESULT());
    render(<ArcMaterializeAction arc={ARC} projectId="p1" token="tok" rosterBindings={{}} />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('arc-materialize-run'));
    await waitFor(() => expect(screen.getByTestId('arc-materialize-conflict')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('arc-materialize-replace'));
    await waitFor(() => expect(screen.getByTestId('arc-materialize-result')).toBeInTheDocument());
    const replaceBody = JSON.parse((apiJson.mock.calls[1][1] as { body: string }).body);
    expect(replaceBody.replace).toBe(true);
  });

  it('surfaces unresolved + scale-folded motifs (§12.6 never silent)', async () => {
    apiJson.mockResolvedValueOnce(RESULT({
      unresolved_placements: [{ motif_code: 'ghost', thread: 'combat', reason: 'motif_not_visible' }],
      drop_merge_report: [{ kind: 'merged', motif_code: 'x', thread: 'combat', src_span_start: 2, src_span_end: 2, into_motif_code: 'y', reason: 'folded' }],
    }));
    render(<ArcMaterializeAction arc={ARC} projectId="p1" token="tok" rosterBindings={{}} />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('arc-materialize-run'));
    await waitFor(() => expect(screen.getByTestId('arc-materialize-unresolved')).toBeInTheDocument());
    expect(screen.getByTestId('arc-materialize-folded')).toBeInTheDocument();
  });

  it('a non-conflict error shows the error message', async () => {
    apiJson.mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 500 }));
    render(<ArcMaterializeAction arc={ARC} projectId="p1" token="tok" rosterBindings={{}} />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('arc-materialize-run'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.queryByTestId('arc-materialize-conflict')).toBeNull();
  });
});
