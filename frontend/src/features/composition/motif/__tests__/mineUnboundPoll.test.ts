// BE-7c guard — a Work-LESS motif-mine must poll the OWNER-scoped /motif-jobs/{id},
// NOT the Work-gated /jobs/{id}. The Wave-0 session added `create_unbound` + the
// /motif-jobs route + get_motif_job, but left `mineConfirm` polling `getJob` → /jobs/{id},
// which gates on a Work that a mine job does not have ⇒ 404 forever, after the user paid.
// (Phase-0 /review-impl finding, fixed in-phase.) This test reds on the pre-fix wiring.
import { describe, expect, it, beforeEach, vi } from 'vitest';

const calls: string[] = [];

vi.mock('../../../../api', () => ({
  apiBase: () => '',
  apiJson: vi.fn((url: string) => {
    calls.push(url);
    if (url.includes('/actions/confirm')) return Promise.resolve({ job_id: 'j1', status: 'pending' });
    if (url.includes('/motif-jobs/j1')) {
      return Promise.resolve({ id: 'j1', status: 'completed', result: { mined: 2, motif_ids: ['a', 'b'], below_gate: 0 } });
    }
    // The bug: the mine poll hitting the Work-gated route. Fail loudly if it ever does.
    if (/\/jobs\/j1(\?|$)/.test(url)) throw new Error(`unbound mine polled the Work-gated /jobs route: ${url}`);
    return Promise.resolve({});
  }),
}));

import { motifApi } from '../api';

describe('BE-7c — a Work-less motif-mine polls the owner-scoped route', () => {
  beforeEach(() => { calls.length = 0; });

  it('mineConfirm polls /motif-jobs/{id}, never /jobs/{id}', async () => {
    const res = await motifApi.mineConfirm('tok', 'jwt');
    expect(res).toMatchObject({ mined: 2, motif_ids: ['a', 'b'] });
    expect(calls.some((u) => u.includes('/motif-jobs/j1'))).toBe(true);
    expect(calls.some((u) => /\/jobs\/j1(\?|$)/.test(u))).toBe(false);
  });
});
